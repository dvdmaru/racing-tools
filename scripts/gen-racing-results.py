#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-racing-results.py — /results/ 各站賽果 hub（已完賽站全分類名次，含衝刺賽）。

單頁 hub＋錨點：每站一個區塊（正賽全 22 名分類＋sprint 站附衝刺賽前 8），CSS-only 摺疊
（<details>），server-rendered——crawler 與 AI 引擎看得到全部表格。退賽（status != Finished
且無 +laps）如實標原因；名次/積分照 API 官方分類。

⚠️ 跑序：先 build-articles.py（覆寫 sitemap）再跑本腳本 re-merge。
用法：python3 scripts/gen-racing-results.py [--season 2026]
"""
import argparse
import html as html_lib
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("racinglib", ROOT / "scripts" / "racinglib.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

RES_CSS = """
.res-block { margin-bottom: 14px; border:1px solid var(--line); border-radius:12px; background:var(--surface); overflow:hidden; }
.res-block summary { cursor:pointer; padding: 14px 16px; display:flex; gap:14px; align-items:baseline; flex-wrap:wrap; list-style:none; }
.res-block summary::-webkit-details-marker { display:none; }
.res-block summary:hover { background: var(--surface-2); }
.res-rnd { font-family:var(--font-mono); font-size:13px; color:var(--accent); font-style:italic; font-weight:700; }
.res-name { font-weight:800; font-size:16px; }
.res-name .en { color:var(--faint); font-size:12px; font-weight:500; margin-left:6px; }
.res-win { color:var(--dim); font-size:13px; margin-left:auto; }
.res-win b { color:var(--accent); }
.res-body { padding: 0 16px 14px; }
.res-sec { font-family:var(--font-mono); font-size:12px; letter-spacing:2px; color:var(--dim); text-transform:uppercase; margin: 12px 0 2px; }
.res-pending { color:var(--dim); font-size:13px; margin: 10px 0 4px; }
"""


def result_table(race_results):
    rows = ""
    for res in race_results:
        drv = res["Driver"]
        lead = ' class="lead"' if res.get("position") == "1" else ""
        t = res.get("Time", {}).get("time", "")
        status = res.get("status", "")
        if not t:
            t = f'<span class="st-status">{html_lib.escape(status)}</span>'
        fl = res.get("FastestLap", {})
        fl_mark = " ⏱" if fl.get("rank") == "1" else ""
        rows += (f'<tr{lead}><td class="rk">{res.get("positionText", res.get("position",""))}</td>'
                 f'<td class="l nm">{rc.driver_zh(drv)}{fl_mark}</td>'
                 f'<td class="l">{rc.team_zh(res["Constructor"]["name"])}</td>'
                 f'<td>{res.get("grid","")}</td><td>{t}</td>'
                 f'<td class="std-pts">{res.get("points","")}</td></tr>')
    return ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
            '<th class="rk">#</th><th class="l">車手</th><th class="l">車隊</th>'
            '<th>發車</th><th>時間/狀態</th><th>積分</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>')


def build_blocks(results):
    blocks = []
    last_rnd = results[-1][0]
    for rnd, race, sprint in reversed(results):  # 最新在前
        sprint_sec = (f'<div class="res-sec">衝刺賽（前 8 名計分）</div>'
                      f'{result_table(sprint.get("SprintResults", [])[:8])}') if sprint else ""
        if race:
            w = race["Results"][0]
            src, d = race, race["date"]
            win = (f'<span class="res-win">冠軍 <b>{rc.driver_zh(w["Driver"])}</b>｜'
                   f'{rc.team_zh(w["Constructor"]["name"])}</span>')
            body = sprint_sec + f'<div class="res-sec">正賽分類</div>{result_table(race["Results"])}'
        else:
            # sprint-only round：衝刺賽已跑、正賽未跑（六/日排程的中間態），先發衝刺賽果
            sw = sprint.get("SprintResults", [{}])[0]
            src, d = sprint, sprint.get("date", "")
            win = (f'<span class="res-win">衝刺賽冠軍 <b>{rc.driver_zh(sw["Driver"])}</b>｜'
                   f'{rc.team_zh(sw["Constructor"]["name"])}</span>') if sw.get("Driver") else ""
            body = sprint_sec + '<p class="res-pending">正賽尚未進行；賽後首次自動重建會補上完整正賽分類。</p>'
        blocks.append(
            f'<details class="res-block" id="round-{rnd:02d}"{" open" if rnd == last_rnd else ""}>'
            f'<summary><span class="res-rnd">Rd{rnd}</span>'
            f'<span class="res-name">{rc.race_zh(src["raceName"])}<span class="en">{html_lib.escape(src["raceName"])} · {d}</span></span>'
            f'{win}'
            f'</summary><div class="res-body">{body}</div></details>')
    return "\n".join(blocks)


def page_faq(season, n_done):
    return [
        (f"{season} 賽季目前跑了幾站？",
         f"本頁收錄 {n_done} 站已完賽分類，每站含全部完賽與退賽車手的官方名次；"
         "衝刺賽週末另附衝刺賽前 8 名。新賽果於賽後首個台北時間週一早上自動更新。"),
        ("表格裡的「⏱」代表什麼？",
         "該站最快單圈。2025 年起最快單圈不再獲得積分加分，此處僅作紀錄標示。"),
        ("退賽車手的名次怎麼算？",
         "依官方分類：完賽距離達 90% 以上者照圈數排名，其餘標註退賽原因（如事故、機械故障）；"
         "名次欄「R」表示退賽（Retired）。"),
        ("賽後改判會反映在這裡嗎？",
         "會。本頁每週重建時會重抓最近一站的官方分類，FIA 賽後加罰或取消成績會在下一次更新自動回寫；"
         "如遇爭議結果，請以 FIA 正式文件為準。"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=rc.SEASON)
    args = ap.parse_args()
    season = args.season

    results = rc.load_results(season)
    if not results:
        raise SystemExit("❌ 缺賽果快照；先跑 python3 scripts/fetch_racing.py results")

    canonical = f"{rc.BASE}/results/"
    n_done = sum(1 for _, race, _ in results if race)  # sprint-only round 不算完賽
    faq = page_faq(season, n_done)
    latest_rnd, latest_race, latest_sprint = results[-1]
    latest_name = rc.race_zh((latest_race or latest_sprint)["raceName"])
    latest_note = "" if latest_race else "，衝刺賽果已出、正賽待跑"
    body = (f'<h1 class="pg-h1">F1 {season} 各站賽果</h1>'
            f'<div class="pg-sub">已完賽 <b>{n_done}</b> 站的官方分類（最新：第 {latest_rnd} 站'
            f'{latest_name}{latest_note}），含發車位、完賽時間/狀態、積分；'
            '衝刺賽週末附衝刺賽結果。點站名展開完整表格。</div>'
            + build_blocks(results)
            + rc.faq_html(faq)
            + ('<p class="asof-note">資料來源：jolpica-f1（Ergast 相容公開 API），官方分類；'
               '每次抓取均落地 JSON 快照為自有歷史庫。本頁每週自動重建。'
               '本站為非官方資料整理站，無任何官方授權。</p>'))

    coll = {"@type": "CollectionPage", "@id": canonical, "url": canonical,
            "name": f"F1 {season} 各站賽果", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{rc.BASE}/#website"}}
    jsonld = rc.graph_ld([rc.org_node(), rc.website_node(), coll,
                          rc.breadcrumb_node([("首頁", f"{rc.BASE}/"), ("賽果", canonical)]),
                          rc.faq_node(faq, canonical)])
    desc = (f"F1 {season} 賽季各站正賽與衝刺賽官方分類結果（已完賽 {n_done} 站），"
            "台灣慣用繁中譯名，每週自動更新。")

    out = rc.PUB / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(
        rc.page_shell(f"F1 {season} 各站賽果", desc, canonical, jsonld, body,
                      "results", extra_css=RES_CSS),
        encoding="utf-8")
    print("✅ public-racing/results/index.html")
    rc.sitemap_merge([canonical], "/results/")


if __name__ == "__main__":
    main()
