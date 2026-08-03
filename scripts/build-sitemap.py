#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-sitemap.py — 從 data/sitemap-parts/<owner>.txt 組出 public-racing/sitemap.xml。

M0 sitemap manifest 化：build-articles.py 與三個 gen-racing-*.py 各自只寫自己擁有的
part 檔（data/sitemap-parts/<owner>.txt，一行一 URL），不再靠字串比對 read-modify-write
整個 sitemap.xml（舊版 sitemap_merge 的跑序敏感、易踩踏問題）。本腳本依固定 owner 順序
讀取全部 part、去重保序、輸出最終 sitemap.xml。

owner 順序＝現行 sitemap.xml 的頁面分組順序（首頁/文章 → 積分榜 → 賽曆 → 賽果）。
某 owner 的 part 檔這次沒被重寫（該 generator 沒跑）→ 印警告、跳過；沿用磁碟上
（可能是上次 commit 留下）該 owner 既有的 part 內容——parts 檔進 git 即是保留機制。
parts 目錄整個不存在（從未跑過任何一個擁有者）→ exit 1，不生成殘缺 sitemap。

跑序：build-articles.py + 三個 gen-racing-*.py 之後、hard gate 之前。
用法：python3 scripts/build-sitemap.py
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("racinglib", ROOT / "scripts" / "racinglib.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

# 固定 owner 序，對應現行 sitemap.xml 的頁面分組順序。
# 後三個是百科線（regen-encyclopedia.py --publish 才寫；未公開時 part 檔不存在＝自然跳過）。
OWNERS = ["articles", "standings", "calendar", "results", "seasons", "drivers", "constructors"]
# 單一 sitemap.xml 的上限（sitemaps.org 慣例 50,000，抓保守值防邊界）；
# 現在遠用不到（M0 全站僅 7 個 URL），寫上防未來 entity 頁全量展開後爆量。
MAX_PER_SITEMAP = 45000


def _urlset_xml(urls) -> str:
    body = "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}</urlset>\n")


def _read_part(p: pathlib.Path) -> list:
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def collect_urls(parts_dir: pathlib.Path) -> list:
    """依 OWNERS 序讀 part；**未列名的 part 一律照收並告警**，絕不靜默丟棄。

    ☠️ 2026-08-03 事故：百科線接好之後，`regen-encyclopedia.py --publish` 確實寫出了
    seasons/drivers/constructors 三個 part 檔，但本檔的 OWNERS 只列了原本四個 owner，
    `collect_urls()` 照著名單讀 → **374 頁百科頁一頁都沒進 sitemap，而且全程零錯誤訊息**。
    建置全綠、part 檔躺在磁碟上、sitemap 少了 98% 的頁面，沒有任何一層會叫。

    所以這裡的預設方向是**收不是擋**：一個 part 檔存在，就代表某支生成器刻意宣告
    「這些 URL 要進 sitemap」。名單沒列到是名單的問題，不是那些 URL 的問題。
    未列名者附在已列名者之後（順序不確定但內容不漏），並印醒目告警要求補進 OWNERS。

    ⚠️ 反過來說，這裡**不能**改成 default-deny（只收名單內的）——那正是本次事故的成因。
    default-deny 該用在「例外清單」那種每筆都要具名理由的地方，不該用在辨識層。
    """
    urls, seen = [], set()
    for owner in OWNERS:
        p = parts_dir / f"{owner}.txt"
        if not p.exists():
            print(f"⚠️  sitemap part 缺席：{owner}（略過；沿用磁碟上既有內容——parts 進 git 即是保留機制）")
            continue
        seen.add(p.name)
        urls.extend(_read_part(p))

    stray = sorted(p for p in parts_dir.glob("*.txt") if p.name not in seen
                   and p.stem not in OWNERS)
    for p in stray:
        n = len(_read_part(p))
        print(f"🔴 sitemap part「{p.stem}」不在 OWNERS 名單裡（{n} 個 URL）——已照收，"
              f"但請把它加進 OWNERS 以固定排序。名單漏列曾讓整條百科線靜默缺席。")
        urls.extend(_read_part(p))

    return list(dict.fromkeys(urls))  # 去重保序


def main():
    parts_dir = ROOT / "data" / "sitemap-parts"
    if not parts_dir.exists():
        print(f"❌ {parts_dir} 不存在；先跑 build-articles.py 與三個 gen-racing-*.py 產生 sitemap parts",
              file=sys.stderr)
        sys.exit(1)

    urls = collect_urls(parts_dir)

    if len(urls) <= MAX_PER_SITEMAP:
        (rc.PUB / "sitemap.xml").write_text(_urlset_xml(urls), encoding="utf-8")
        print(f"🗺️  sitemap.xml → {len(urls)} URLs（manifest 合併：{'、'.join(OWNERS)}）")
        return

    # 防未來：URL 數超過單檔上限時切成 sitemap index + 多個子 sitemap。
    chunks = [urls[i:i + MAX_PER_SITEMAP] for i in range(0, len(urls), MAX_PER_SITEMAP)]
    index_entries = []
    for i, chunk in enumerate(chunks, start=1):
        fname = f"sitemap-{i}.xml"
        (rc.PUB / fname).write_text(_urlset_xml(chunk), encoding="utf-8")
        index_entries.append(f"  <sitemap><loc>{rc.BASE}/{fname}</loc></sitemap>\n")
    (rc.PUB / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{''.join(index_entries)}</sitemapindex>\n", encoding="utf-8")
    print(f"🗺️  sitemap index → {len(chunks)} 個子 sitemap（總 {len(urls)} URLs，超過單檔 {MAX_PER_SITEMAP} 上限）")


if __name__ == "__main__":
    main()
