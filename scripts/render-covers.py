#!/usr/bin/env python3
"""封面 HTML → PNG（headless Chrome），2400×1260。

站規（README 第 9 行）：封面一律自製數據視覺，不用車手肖像；賽道圖如自繪需註明。
尺寸是 og:image 建議值 1200×630 的 2 倍，讓分享卡在高解析裝置上不糊。

用法：
    python3 scripts/render-covers.py                  # 產缺的與比 HTML 舊的
    python3 scripts/render-covers.py --slug <slug>     # 只產一張
    python3 scripts/render-covers.py --force           # 連已是最新的也重產
    python3 scripts/render-covers.py --check           # 不產圖，只檢查 PNG 是否比 HTML 舊

⚠️ 兩個必須知道的事：
  ① **字型走 Google Fonts CDN，render 需要連得上網。** 連不到時 Chrome 會靜默 fallback
     成系統字型，PNG 產得出來、但字完全不對——這是「產出成功但內容錯」的典型，
     ⚠️ **產完一定要看一次 PNG。** 這裡刻意沒有自動字型 gate，理由與兩次失敗的嘗試
     寫在下面 `_shoot` 前面的長註解——兩種寫法都給出假陰性。
  ② 改了封面 HTML 沒重新 render，`check-covers.py` 抓不到（它讀 HTML）。
     `--check` 就是補這個縫：PNG 比 HTML 舊就報。
     ⚠️ **`--check` 只在本機有意義，不要接進 CI。** git checkout 會把所有檔案的 mtime
     設成同一個時間，PNG 與 HTML 的新舊關係在 CI 裡不存在——接進去會得到一個永遠綠、
     或永遠紅的假 gate。CI 端的封面把關由 `tests/test_check_covers.py` 負責（數字對帳）。
"""
import argparse
import json
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
COVER_DIR = ROOT / "design" / "covers"
ARTICLES = ROOT / "articles"
W, H = 2400, 1260

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]


def find_chrome():
    for c in CHROME_CANDIDATES:
        if c and pathlib.Path(c).exists():
            return c
    return None


# 為什麼這裡**沒有**自動字型檢查（2026-07-30，兩種寫法各自被證明會說謊）
#
# 封面字型走 Google Fonts CDN。字型沒載到時 Chrome 會靜默 fallback 成系統字型，
# PNG 產得出來、尺寸也對、exit code 也是 0，只有字是錯的——很值得自動擋。試了兩次：
#
#   ① 渲染兩次比對（Chakra Petch vs 不存在的字型，PNG bytes 相同就判定沒生效）
#      → **假陰性**。探測頁很小，Chrome 在 `display=swap` 的字型到達前就截圖，兩張都是
#        fallback、hash 相同；而同一時間真正的封面渲染完全正確（肉眼確認）。
#   ② Python urllib 抓字型 CSS 當 pre-flight
#      → **假陰性**。本機 sandbox 有 TLS 攔截，urllib 一律 CERTIFICATE_VERIFY_FAILED，
#        但 curl 同一個 URL 回 200、Chrome 也確實載到了字型。
#
# 兩者的共同問題是「檢查者跟渲染者不是同一個 client」。假陰性比沒有檢查更糟：
# 它會訓練出「這個檢查一向紅、忽略它」的習慣，然後真的壞掉那天也沒人看。
# 所以這裡不放自動字型 gate——**產完看一次 PNG**。封面是給人看的東西，
# 字型錯掉在圖上一眼可見，這件事不值得用一個會說謊的檢查來代替。


def _shoot(chrome, html_path, out_path, w, h):
    """截圖並在檔案寫完後主動結束 Chrome。

    ⚠️ `--headless=new --screenshot` 在本機**會把 PNG 寫好卻不自己結束**（實測 45 秒、
    120 秒都不返回，但檔案早就在了）。所以不能用 `subprocess.run(timeout=…)` 等它——
    那會把「已經成功」誤判成失敗，然後讓人跑去改 render 參數找不存在的 bug。
    改成輪詢輸出檔：大小連續兩次不變就當寫完，然後主動 terminate。
    """
    if out_path.exists():
        out_path.unlink()
    with tempfile.TemporaryDirectory() as d:
        p = subprocess.Popen(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
             f"--user-data-dir={d}", f"--window-size={w},{h}",
             "--force-device-scale-factor=1",
             f"--screenshot={out_path}", html_path.resolve().as_uri()],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        last, stable, waited = -1, 0, 0.0
        while waited < 90:
            if p.poll() is not None:
                break
            if out_path.exists():
                size = out_path.stat().st_size
                stable = stable + 1 if size == last and size > 0 else 0
                last = size
                if stable >= 2:
                    break
            time.sleep(0.5)
            waited += 0.5
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    if not out_path.exists():
        return False, "Chrome 沒有產出檔案"
    dims = struct.unpack(">II", out_path.read_bytes()[16:24])
    if dims != (w, h):
        return False, f"尺寸不對：{dims[0]}×{dims[1]}，應為 {w}×{h}"
    return True, f"{dims[0]}×{dims[1]}　{out_path.stat().st_size / 1024:.0f}KB"


def render(chrome, html_path, out_path):
    return _shoot(chrome, html_path, out_path, W, H)


def main():
    ap = argparse.ArgumentParser(description="封面 HTML → PNG")
    ap.add_argument("--slug")
    ap.add_argument("--check", action="store_true", help="不產圖，只檢查 PNG 是否比 HTML 舊")
    ap.add_argument("--force", action="store_true",
                    help="連已是最新的封面也重產（預設只產缺的與比 HTML 舊的）")
    args = ap.parse_args()

    entries = json.loads((COVER_DIR / "covers.json").read_text(encoding="utf-8"))["covers"]
    if args.slug:
        entries = [e for e in entries if e["slug"] == args.slug]
        if not entries:
            print(f"❌ covers.json 裡沒有 slug={args.slug}")
            return 1

    if args.check:
        stale = []
        for e in entries:
            html, png = COVER_DIR / e["html"], ARTICLES / e["slug"] / "cover.png"
            if not png.exists():
                stale.append(f"{e['slug']}：沒有 cover.png")
            elif png.stat().st_mtime < html.stat().st_mtime:
                stale.append(f"{e['slug']}：cover.png 比 {e['html']} 舊，需重新 render")
        for s in stale:
            print("❌ " + s)
        print("✅ 封面 PNG 與 HTML 同步" if not stale else "→ 跑 render-covers.py 重新產圖")
        return 1 if stale else 0

    chrome = find_chrome()
    if not chrome:
        print("❌ 找不到 headless Chrome，無法產封面")
        return 1

    ok = True
    for e in entries:
        html = COVER_DIR / e["html"]
        if not html.exists():
            print(f"❌ {e['slug']}：找不到 {e['html']}")
            ok = False
            continue
        # 預設不重產已經最新的封面：已上線的 PNG 沒有理由因為字型版本漂移而換一份 byte，
        # 那只會製造看不出意義的 diff。要重產請明講 --force。
        png = ARTICLES / e["slug"] / "cover.png"
        if not args.force and png.exists() and png.stat().st_mtime >= html.stat().st_mtime:
            print(f"・{e['slug']}：已是最新，略過（--force 可強制重產）")
            continue
        out = ARTICLES / e["slug"] / "cover.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        good, msg = render(chrome, html, out)
        print(("✅ " if good else "❌ ") + f"{e['slug']}　{msg}")
        ok = ok and good

    print("—" * 40)
    print("封面產出完成" if ok else "封面產出有失敗項，見上方")
    if ok:
        print("⚠️ 請看一次產出的 PNG 確認字型有生效（沒有自動 gate，理由見本檔註解）")
        print("下一步：python3 scripts/check-covers.py　然後 build-articles.py + build-sitemap.py")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
