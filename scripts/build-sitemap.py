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
OWNERS = ["articles", "standings", "calendar", "results"]
# 單一 sitemap.xml 的上限（sitemaps.org 慣例 50,000，抓保守值防邊界）；
# 現在遠用不到（M0 全站僅 7 個 URL），寫上防未來 entity 頁全量展開後爆量。
MAX_PER_SITEMAP = 45000


def _urlset_xml(urls) -> str:
    body = "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}</urlset>\n")


def collect_urls(parts_dir: pathlib.Path) -> list:
    urls = []
    for owner in OWNERS:
        p = parts_dir / f"{owner}.txt"
        if not p.exists():
            print(f"⚠️  sitemap part 缺席：{owner}（略過；沿用磁碟上既有內容——parts 進 git 即是保留機制）")
            continue
        lines = [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        urls.extend(lines)
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
