#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update-racing.py — racing.twtools.cc 每週自動重建編排器。

自動化節奏是「週」不是「日」：GH Actions 排台北週一 06:00（歐洲週日夜賽後）＋
sprint 週末加跑六、日＋workflow_dispatch 手動。非賽週跑了沒新資料 → 安靜跳過
（fetch_racing.py exit 3 = 無變化 → 不重建、不部署、CI 綠燈結束）。

跑序鐵則（sitemap manifest 化，M0 後）：
  1. fetch_racing all：積分榜+賽曆+賽果快照（exit 3 = 無新資料 → 安靜跳過，除非 --force）
  2. build-articles：文章+首頁 dashboard+寫 sitemap part（articles）
  3. 各 gen-*：standings / calendar / results，各自寫自己的 sitemap part
  3b. build-sitemap：合併全部 part → public-racing/sitemap.xml
  4.（可選）wrangler deploy；成功後 IndexNow ping 本次變動頁

部署需非互動憑證：CLOUDFLARE_API_TOKEN（本機從 ~/.config/cloudflare/ 檔案讀，永不印出；
CI 走 repo secrets）。未設 token 且未加 --deploy 時只重建不部署。

用法：
  python3 scripts/update-racing.py                # 有新資料才重建，不部署
  python3 scripts/update-racing.py --force        # 無視快照比對強制重建
  python3 scripts/update-racing.py --deploy       # 重建 + wrangler deploy
"""
import argparse
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable
BASE_URL = "https://racing.twtools.cc"

FAILED = []


def run(args, label, allow_exit=()):
    print(f"\n▶ {label}: {' '.join(str(a) for a in args)}", flush=True)
    r = subprocess.run(args, cwd=str(ROOT))
    if r.returncode != 0 and r.returncode not in allow_exit:
        print(f"  ⚠️  {label} exit={r.returncode}（繼續跑完其餘步驟；結尾以非零狀態離開）", flush=True)
        FAILED.append(label)
    return r.returncode


def script(name, *extra):
    return [PY, str(ROOT / "scripts" / name), *extra]


def _indexnow_changed_urls():
    """本次 build 實際變動的頁面 URL（IndexNow 只推變動）。靠 git：public-racing/ 產物有
    commit、CI checkout 乾淨 → build 後髒檔＝本次變動。new_urls＝untracked 新頁（部署前
    404，是「真 live」的 poll 訊號；既有頁永遠 200 不能當訊號）。"""
    # -uall：porcelain 預設把整個新目錄縮成一行「?? dir/」，新文章頁的 index.html 會被漏掉
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", "public-racing"],
                         cwd=str(ROOT), capture_output=True, text=True).stdout
    urls, new = set(), []
    for line in out.splitlines():
        status, path = line[:2], line[3:].strip().strip('"')
        u = None
        if path.endswith("index.html"):
            rel = path[len("public-racing/"):-len("index.html")]
            u = f"{BASE_URL}/{rel}"
        elif path.endswith("llms.txt"):
            u = f"{BASE_URL}/llms.txt"
        if u:
            urls.add(u)
            if status == "??":
                new.append(u)
    return sorted(urls), new


def _encyclopedia_published():
    """讀 config/encyclopedia.json 的 published（單一開關）。缺檔／壞檔＝未公開（default-deny）。"""
    import json
    try:
        cfg = json.loads((ROOT / "config" / "encyclopedia.json").read_text(encoding="utf-8"))
        return cfg.get("published", False) is True
    except (OSError, ValueError):
        return False


def encyclopedia_step(full=False):
    """百科段（dormant wiring；M7）。跑序後追加，published gate 包住。

    published:false → 整段跳過（不 refresh、不重生、不寫 sitemap part、不進 IndexNow），
    只印一行訊息；週更三頁行為與改動前完全一致（byte-identical）。
    published:true → refresh-current（增量抓當季 raw＋rebuild db＋invariants）→ 選擇性重生
    （facts-hash：只重生受新資料影響的頁）→ 寫 seasons/drivers sitemap part。重生的頁落進
    public-racing/，由既有 git-diff 機制自動納入部署後 IndexNow。

    ★ 分層 fail：百科層任何失敗＝醒目告警但**不**進 FAILED、**不**擋週更三頁的 fail-fast 部署。
      （週更頁失敗＝禁部署照舊；百科層失敗＝跳過百科並告警。）
    """
    if not _encyclopedia_published():
        print("\n⏸  百科線未公開（config/encyclopedia.json published:false）→ 整段跳過（週更三頁不受影響）",
              flush=True)
        return

    print("\n📚 百科段（published:true）：當季橋接 → 選擇性重生 → sitemap part", flush=True)
    # 1. 當季新賽果增量橋接（自帶 rebuild db + invariants；exit 0=無新資料或成功、1=不變量擋線）
    rc_ref = subprocess.run(script("refresh-f1-current.py"), cwd=str(ROOT)).returncode
    if rc_ref != 0:
        print(f"\n⚠️  🔴 百科層：當季橋接/不變量未過（exit={rc_ref}）→ 跳過百科重生，"
              f"**週更三頁不受影響**", flush=True)
        return
    # 2. 選擇性重生（--full 透傳）＋寫 sitemap part（僅 published）。前置三 gate 由本步自跑。
    argv = script("regen-encyclopedia.py", "--publish")
    if full:
        argv.append("--full")
    rc_regen = subprocess.run(argv, cwd=str(ROOT)).returncode
    if rc_regen != 0:
        print("\n⚠️  🔴 百科層：選擇性重生前置 gate 未過 → 跳過百科，**週更三頁不受影響**", flush=True)
        return
    print("✅ 百科段完成（變更頁已進 public-racing，隨部署由 IndexNow 自動推送）", flush=True)


def indexnow_after_deploy():
    """best-effort：任何失敗只警告、不擋 pipeline。帶瀏覽器樣 UA（runner 裸 UA 會被 CF 擋）。"""
    try:
        urls, new = _indexnow_changed_urls()
        if not urls:
            print("\n⏭  IndexNow：本次 build 無頁面變動，不 ping", flush=True)
            return
        if new:
            probe, last = new[0], "?"
            for i in range(12):
                try:
                    req = urllib.request.Request(probe, headers={
                        "User-Agent": "Mozilla/5.0 (compatible; racing-tools-deploy-probe/1.0)"})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        last = str(r.status)
                        if r.status == 200:
                            print(f"\n🌐 IndexNow：新頁 {probe} 已 live（第 {i + 1} 次探測）", flush=True)
                            break
                except urllib.error.HTTPError as e:
                    last = str(e.code)
                except Exception as e:
                    last = type(e).__name__
                time.sleep(5)
            else:
                print(f"\n⚠️  IndexNow：新頁 {probe} 探測未見 200（最後狀態 {last}），仍續行 ping", flush=True)
        r = subprocess.run(["node", str(ROOT / "scripts" / "indexnow-ping.mjs"), *urls], cwd=str(ROOT))
        if r.returncode != 0:
            print("⚠️  IndexNow ping 失敗（best-effort，不擋 pipeline）", flush=True)
    except Exception as e:
        print(f"⚠️  IndexNow 步驟例外（忽略）：{e}", flush=True)


def main():
    import json
    season_default = 2026
    try:
        season_default = int(json.loads((ROOT / "config" / "site.json").read_text(encoding="utf-8"))["season"])
    except (OSError, ValueError, KeyError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=season_default)
    ap.add_argument("--force", action="store_true", help="無視快照比對強制重建")
    ap.add_argument("--deploy", action="store_true", help="重建後 wrangler deploy")
    ap.add_argument("--full", action="store_true",
                    help="百科段全量重生（忽略 per-page 指紋；透傳 regen-encyclopedia.py --full）")
    args = ap.parse_args()
    s = str(args.season)

    print(f"🏁 update-racing · season={s} · force={args.force} · deploy={args.deploy}")

    # 1. 抓資料；exit 3 = 無新資料 → 非 force 時安靜跳過（非賽週的每週 cron 走這裡）
    rcode = run(script("fetch_racing.py", "all", "--season", s), "fetch racing data", allow_exit=(3,))
    if rcode == 3 and not args.force:
        print("\n😴 無新資料（非賽週或賽果未出）→ 安靜跳過，不重建不部署")
        return

    # 2. build-articles（文章+首頁+整個覆寫 sitemap）——必須在各 gen-* 之前
    run(script("build-articles.py"), "build-articles (home + sitemap)")

    # 3. 各 generator 寫自己的 sitemap part
    run(script("gen-racing-standings.py", "--season", s), "gen standings")
    run(script("gen-racing-calendar.py", "--season", s), "gen calendar")
    run(script("gen-racing-results.py", "--season", s), "gen results")

    # 3c. 百科段（dormant；published gate）——在 build-sitemap 之前，好讓 published 時的
    # seasons/drivers sitemap part 一併被合併。published:false＝整段跳過，sitemap 與改動前一致。
    # 百科層失敗自我隔離（不進 FAILED），絕不拖垮週更三頁的 fail-fast 部署。
    encyclopedia_step(full=args.full)

    # 3b. 合併全部 sitemap part → public-racing/sitemap.xml（三個 gen-* 之後、hard gate 之前）
    run(script("build-sitemap.py"), "build sitemap")

    # 4.（可選）部署；pin wrangler 版本（CI 帶著 CLOUDFLARE_API_TOKEN，防供應鏈）。
    # hard gate：任何抓取/建置步驟失敗 → 禁止部署（build 步驟照跑收集診斷，但壞產物不上線）。
    if FAILED:
        print(f"\n⛔ {len(FAILED)} 個前置步驟失敗（{'、'.join(FAILED)}）→ 禁止部署，正式站維持上一版", flush=True)
        sys.exit(1)
    if args.deploy or os.environ.get("CLOUDFLARE_API_TOKEN"):
        rc_dep = run(["npx", "wrangler@4.108.0", "deploy", "-c", "wrangler-racing.jsonc"], "wrangler deploy")
        if rc_dep == 0:
            indexnow_after_deploy()
    else:
        print("\n⏭  未 --deploy 且無 CLOUDFLARE_API_TOKEN → 只重建未部署。")

    if FAILED:
        print(f"\n❌ update-racing 完成但 {len(FAILED)} 步失敗：{'、'.join(FAILED)}", flush=True)
        sys.exit(1)
    print("\n✅ update-racing done")


if __name__ == "__main__":
    main()
