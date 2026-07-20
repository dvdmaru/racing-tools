#!/usr/bin/env python3
"""驗證線上內容 == repo 內容（整檔比對，不用人想的哨兵字串）。

為什麼存在
----------
「驗部署」這件事在本站群復發過 5 次以上，每次都是同一個根因的不同變種：
人挑一個字串當哨兵，而那個字串**在舊版本裡也存在** → 假陽性，以為驗過了。

  2026-06-07 poll `post-nav-link`   → 那是 CSS class 定義，舊版就有
  2026-06-30 驗 R32 比分用「巴拉圭」 → 隊名在舊 build 的佔位符就有
  2026-07-02 驗 llms.txt 用品牌字     → 命中的是 404 fallback 頁
  2026-07-13 驗側欄用工具名          → 命中的是上個 commit 已上線的卡片
  2026-07-20 驗 banner 用含 <b> 的字串 → 標籤斷開，內容其實在，誤判沒上線

HTTP 200 也不能當訊號：本站是 deterministic static build，頁面幾乎永遠 200
（見 .github/workflows/indexnow.yml 的同款理由）。

正解是**不要挑字串**：拿 repo 裡剛 build 出來的檔案跟線上整檔比對。
baseline 來自檔案，不來自人的記憶，所以沒有「挑錯哨兵」這個失敗模式。

用法
----
    python3 scripts/verify-deploy.py public/standings/index.html
    python3 scripts/verify-deploy.py public/articles/*/index.html
    python3 scripts/verify-deploy.py --timeout 300 public/index.html
    python3 scripts/verify-deploy.py --site https://example.com public/index.html

站台自動解析：站內 config/site.json 或 config/sites.json → 內建對照表；
--site 或 SITE 環境變數可覆寫。本檔在四個站台間逐字相同，移植即複製。

⚠️ 比對的 baseline 是「本機這一份檔案」，所以它必須是**剛 build 出來的那一份**。
   foootball 把 public/ 產物 commit 進 repo，checkout 出來就能直接驗；
   baseball／basketball／racing 的排程是雲端重建後直接 wrangler 部署、
   **產物不 commit 回 main**，repo 裡那份是舊的，不先 build 就驗必然假警報。

不符時印出第一個差異點的前後文（診斷用，不是只給 pass/fail），
全部相符 exit 0，逾時仍不符 exit 1。
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
UA = "verify-deploy/1.0 (+twtools static site deploy check)"

# 本檔在四個站台之間逐字相同（foootball / baseball / basketball / racing），
# 站別靠下面的自動解析決定，所以移植就是單純複製，不需逐站改碼。
DEFAULT_SITES = {
    "foootball-tools": "https://foootball.twtools.cc",
    "baseball-tools": "https://baseball.twtools.cc",
    "basketball-tools": "https://basketball.twtools.cc",
    "racing-tools": "https://racing.twtools.cc",
}
# repo 目錄名 → config/sites.json 的 key（足球站在共用設定裡叫 soccer）
SPORT_KEYS = {"foootball-tools": "soccer", "baseball-tools": "baseball",
              "basketball-tools": "basketball", "racing-tools": "racing"}


def repo_name() -> str:
    """認得 worktree：路徑是 <repo>/.claude/worktrees/<name>，ROOT.name 不是 repo 名。"""
    for part in ROOT.parts:
        if part in DEFAULT_SITES:
            return part
    return ROOT.name


def resolve_site(cli_site: str | None) -> str:
    """順序：--site / SITE env → 站內既有 config → 內建對照表。
    先讀 config 是為了域名若異動時不必改這支腳本。"""
    if cli_site:
        return cli_site.rstrip("/")
    env = os.environ.get("SITE")
    if env:
        return env.rstrip("/")
    repo = repo_name()
    single = ROOT / "config" / "site.json"          # racing
    if single.exists():
        try:
            base = json.loads(single.read_text(encoding="utf-8")).get("base")
            if base:
                return base.rstrip("/")
        except (json.JSONDecodeError, OSError):
            pass
    multi = ROOT / "config" / "sites.json"          # baseball / basketball
    if multi.exists():
        try:
            data = json.loads(multi.read_text(encoding="utf-8"))
            base = (data.get(SPORT_KEYS.get(repo, ""), {}) or {}).get("base")
            if base:
                return base.rstrip("/")
        except (json.JSONDecodeError, OSError):
            pass
    if repo in DEFAULT_SITES:
        return DEFAULT_SITES[repo]
    print(f"❌ 認不出站台（repo={repo}），請用 --site 指定", file=sys.stderr)
    sys.exit(2)


SITE = ""  # 由 main() 解析後填入


def path_to_url(p: pathlib.Path) -> str:
    """public/standings/index.html → <SITE>/standings/  ；public/index.html → <SITE>/"""
    rel = p.resolve().relative_to(ROOT)
    parts = list(rel.parts)
    if not parts:
        raise ValueError(f"無法對應 URL：{p}")
    parts = parts[1:]  # 去掉 public/ 或 public-<sport>/ 這層
    if parts and parts[-1] == "index.html":
        parts = parts[:-1]
        return f"{SITE}/" + ("/".join(parts) + "/" if parts else "")
    return f"{SITE}/" + "/".join(parts)


def fetch(url: str, cache_bust: bool) -> bytes:
    """用 curl 而不是 urllib：launchd 用的 framework Python 沒有系統憑證鏈，
    urllib 會在 CERTIFICATE_VERIFY_FAILED 掛掉。curl 在 macOS 與 GH Actions 都在，
    且 .github/workflows/indexnow.yml 的部署驗證也是走 curl，行為一致。"""
    u = url
    if cache_bust:
        u += ("&" if "?" in u else "?") + f"cb={int(time.time() * 1000)}"
    r = subprocess.run(
        ["curl", "-sSL", "--max-time", "30", "-H", f"User-Agent: {UA}",
         "-H", "Cache-Control: no-cache", u],
        capture_output=True,
    )
    if r.returncode != 0:
        raise OSError(f"curl exit {r.returncode}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def describe_diff(live: bytes, local: bytes, url: str) -> str:
    """指出第一個差異點在哪，附前後文——讓人看得出是『沒部署』還是『部署了但內容不同』。"""
    lines = [f"   線上 {len(live)} bytes / repo {len(local)} bytes"]
    n = min(len(live), len(local))
    i = next((k for k in range(n) if live[k] != local[k]), n)
    if i == n and len(live) != len(local):
        lines.append(f"   前 {n} bytes 相同，之後長度不同（可能是舊版被截斷或多了內容）")
        return "\n".join(lines)
    ctx = 90
    lo, hi = max(0, i - ctx), i + ctx
    lines.append(f"   第一個差異在 byte {i}：")
    lines.append(f"     線上… {live[lo:hi].decode('utf-8', 'replace')!r}")
    lines.append(f"     repo… {local[lo:hi].decode('utf-8', 'replace')!r}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="線上內容 == repo 內容 整檔比對")
    ap.add_argument("paths", nargs="+", help="repo 內已 build 的檔案路徑")
    ap.add_argument("--timeout", type=int, default=180,
                    help="等部署上線的總秒數（預設 180，CF Pages 通常 30s–3min）")
    ap.add_argument("--interval", type=int, default=10, help="輪詢間隔秒數（預設 10）")
    ap.add_argument("--no-cache-bust", action="store_true", help="不加 ?cb= 查詢參數")
    ap.add_argument("--site", default=None, help="站台 base URL（預設自動解析）")
    args = ap.parse_args()

    global SITE
    SITE = resolve_site(args.site)

    targets = []
    for raw in args.paths:
        p = pathlib.Path(raw)
        if not p.is_file():
            print(f"❌ 檔案不存在：{raw}（要先 build）", file=sys.stderr)
            return 2
        targets.append((p, p.read_bytes(), path_to_url(p)))

    print(f"🔍 比對 {len(targets)} 個檔案 vs {SITE}（整檔 byte 比對，逾時 {args.timeout}s）")

    pending = list(targets)
    deadline = time.time() + args.timeout
    last_err = {}
    attempt = 0

    while pending:
        attempt += 1
        still = []
        for p, local, url in pending:
            try:
                live = fetch(url, not args.no_cache_bust)
            except OSError as e:
                last_err[url] = f"抓取失敗：{e}"
                still.append((p, local, url))
                continue
            if live == local:
                print(f"✅ {url}")
            else:
                last_err[url] = describe_diff(live, local, url)
                still.append((p, local, url))
        pending = still
        if not pending:
            break
        if time.time() >= deadline:
            break
        print(f"⏳ 尚有 {len(pending)} 個未同步（第 {attempt} 次），{args.interval}s 後重試…")
        time.sleep(args.interval)

    if pending:
        print(f"\n❌ 逾時仍不相符（{len(pending)} 個）：", file=sys.stderr)
        for _, _, url in pending:
            print(f" · {url}", file=sys.stderr)
            print(last_err.get(url, "   （無診斷資訊）"), file=sys.stderr)
        print("\n可能原因：CF Pages 尚未部署完成／部署未觸發（squash-merge 曾漏觸發）／"
              "本機產物不是最新（先跑 build）。", file=sys.stderr)
        print("⚠️  baseball／basketball／racing 的排程是「雲端重建後直接 wrangler 部署、"
              "不把產物 commit 回 main」，拿 repo 裡的舊產物比對必然不符——"
              "這三站要先在本機跑過該站的 build 再驗，否則本工具自己會變成假警報。",
              file=sys.stderr)
        return 1

    print(f"\n✅ 全部相符：線上內容與 repo 一致（{len(targets)} 個檔案）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
