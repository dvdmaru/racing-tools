#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-racing-standings.py — /standings/ 積分榜頁（車手榜＋車隊榜，CSS-only tabs）。

server-rendered、零 client fetch（GEO/AEO：crawler 看得到全部表格）。
資料讀 data/<season>/driver-standings.json、constructor-standings.json（jolpica 快照）。
「資料截至第 N 站」以快照內 data_through_round（來自 last/results）為準，
不用 standings 的 round 欄（該欄可能指向未跑的下一站——見 fetch_racing.py docstring）。

⚠️ 跑序：本腳本寫自己的 sitemap part（data/sitemap-parts/standings.txt）；
build-sitemap.py 需在三個 gen-* 都跑完後才合併出最終 sitemap.xml。
用法：python3 scripts/gen-racing-standings.py [--season 2026]
"""
import argparse
import html as html_lib
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("racinglib", ROOT / "scripts" / "racinglib.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)


def driver_table(standings):
    rows = ""
    for s in standings["DriverStandings"]:
        drv, cons = s["Driver"], s["Constructors"][-1] if s["Constructors"] else {}
        lead = ' class="lead"' if s["position"] == "1" else ""
        rows += (f'<tr{lead}><td class="rk">{s["position"]}</td>'
                 f'<td class="l nm">{rc.driver_pair(drv, full=True)}</td>'
                 f'<td class="l">{rc.team_pair(cons.get("name",""))}</td>'
                 f'<td class="std-pts">{s["points"]}</td><td>{s["wins"]}</td></tr>')
    return ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
            '<th class="rk">#</th><th class="l">車手</th><th class="l">車隊</th>'
            '<th>積分</th><th>分站冠軍</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>')


def constructor_table(standings):
    rows = ""
    for s in standings["ConstructorStandings"]:
        lead = ' class="lead"' if s["position"] == "1" else ""
        name = s["Constructor"]["name"]
        rows += (f'<tr{lead}><td class="rk">{s["position"]}</td>'
                 f'<td class="l nm">{rc.team_pair(name)}</td>'
                 f'<td class="std-pts">{s["points"]}</td><td>{s["wins"]}</td></tr>')
    return ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
            '<th class="rk">#</th><th class="l">車隊</th><th>積分</th><th>分站冠軍</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>')


def page_faq(season, rnd, race_name):
    return [
        (f"F1 {season} 積分榜多久更新一次？",
         f"本頁每週自動重建（歐洲賽事週日夜賽後、台北時間週一早上），資料來自 Ergast 相容的公開 API（jolpica-f1），"
         f"目前資料截至第 {rnd} 站{race_name}賽後。賽後若有 FIA 改判或加罰，下次重建會自動回寫。"),
        ("車手積分怎麼算？",
         "正賽前 10 名依 25、18、15、12、10、8、6、4、2、1 計分；衝刺賽（sprint）前 8 名依 8 至 1 計分。"
         "2025 年起最快單圈不再加分。車隊積分為兩位車手積分加總。"),
        ("為什麼車手名字的中文翻譯和其他網站不一樣？",
         "本站採台灣媒體慣用譯名（如漢米爾頓、麥拉倫），與中國大陸、香港的譯名系統不同；"
         "對照與依據見本站的車手車隊譯名對照表。"),
        ("這裡的數字和官方網站不一樣，該信哪個？",
         "本頁為定期重生的資料頁並標註資料截至站次；若與其他來源不同，多半是資料截點不同。"
         "如需最新積分請以 FIA 及賽事官方公布為準。"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=rc.SEASON)
    args = ap.parse_args()
    season = args.season

    ds = rc.load_data(season, "driver-standings.json")
    cs = rc.load_data(season, "constructor-standings.json")
    if not ds or not cs or not ds.get("standings"):
        raise SystemExit("❌ 缺積分榜快照；先跑 python3 scripts/fetch_racing.py standings")

    rnd = ds.get("data_through_round", 0)
    results = rc.load_results(season)
    race_name = ""
    for r, race, _ in results:
        if r == rnd and race:  # race=None＝sprint-only round，不會等於 data_through_round，但保險
            race_name = rc.race_zh(race["raceName"])

    canonical = f"{rc.BASE}/standings/"
    tabs = rc.tabgroup("st", [
        ("drv", "車手積分榜", driver_table(ds["standings"]), ""),
        ("con", "車隊積分榜", constructor_table(cs["standings"]), ""),
    ])
    faq = page_faq(season, rnd, race_name)
    asof = (f'<p class="asof-note">資料來源：jolpica-f1（Ergast 相容公開 API），每次抓取均落地快照存檔；'
            f'{season} 賽季，截至第 {rnd} 站{race_name}賽後。賽季進行中，積分逐站變動，'
            '本頁為每週定期重生之資料頁。本站為非官方資料整理站，無任何官方授權。</p>')
    body = (f'<h1 class="pg-h1">F1 {season} 積分榜</h1>'
            f'<div class="pg-sub">車手與車隊年度積分（截至第 <b>{rnd}</b> 站{race_name}賽後）。'
            '中文名採台灣慣用譯名，附原文對照。</div>'
            f'{tabs}{rc.faq_html(faq)}{asof}')
    coll = {"@type": "CollectionPage", "@id": canonical, "url": canonical,
            "name": f"F1 {season} 車手與車隊積分榜", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{rc.BASE}/#website"}}
    jsonld = rc.graph_ld([rc.org_node(), rc.website_node(), coll,
                          rc.breadcrumb_node([("首頁", f"{rc.BASE}/"), ("積分榜", canonical)]),
                          rc.faq_node(faq, canonical)])
    desc = (f"F1 {season} 賽季車手積分榜與車隊積分榜（截至第 {rnd} 站賽後），"
            "台灣慣用繁中譯名＋原文對照，每週自動更新。")

    out = rc.PUB / "standings"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(
        rc.page_shell(f"F1 {season} 積分榜（車手＋車隊）", desc, canonical, jsonld, body, "standings"),
        encoding="utf-8")
    print("✅ public-racing/standings/index.html")
    rc.write_sitemap_part("standings", [canonical])


if __name__ == "__main__":
    main()
