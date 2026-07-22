#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-racing-calendar.py — /calendar/ 台北時間賽曆頁（台灣讀者剛需，內容 6 件套之 ③）。

22 站全季賽曆：每站正賽/排位/衝刺賽的台北時間（UTC+8 換算自 jolpica 的 UTC session 時刻），
已完賽站標冠軍、下一站高亮。歐洲賽事多在台灣深夜/清晨——這頁存在的理由。
server-rendered、零 client fetch；sprint 站標記出自賽曆資料本身（有 Sprint session 即是）。

⚠️ 跑序：本腳本寫自己的 sitemap part（data/sitemap-parts/calendar.txt）；
build-sitemap.py 需在三個 gen-* 都跑完後才合併出最終 sitemap.xml。
用法：python3 scripts/gen-racing-calendar.py [--season 2026]
"""
import argparse
import datetime
import html as html_lib
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("racinglib", ROOT / "scripts" / "racinglib.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

CAL_CSS = """
.cal-card { border:1px solid var(--line); border-radius:12px; padding:14px 16px; margin-bottom:10px;
  display:grid; grid-template-columns: 52px 1fr auto; gap: 4px 14px; align-items:center;
  background: var(--surface); }
.cal-card.done { opacity: 0.78; }
.cal-card.next { border-color: var(--accent-line); box-shadow: 0 0 0 1px var(--accent-line); background: var(--accent-soft); }
.cal-rnd { font-family:var(--font-mono); font-size:12px; color:var(--dim); text-align:center; }
.cal-rnd b { display:block; font-size:20px; color:var(--accent); font-style:italic; }
.cal-name { font-weight:800; font-size:16px; }
.cal-name .en { color:var(--faint); font-size:12px; font-weight:500; margin-left:6px; }
.cal-circuit { color:var(--dim); font-size:12.5px; margin-top:2px; }
.cal-race { text-align:right; font-family:var(--font-mono); }
.cal-race b { color:var(--accent); font-size:15px; }
.cal-race .d { color:var(--dim); font-size:11.5px; display:block; }
.cal-sessions { grid-column: 2 / 4; color:var(--dim); font-size:12px; line-height:1.8; border-top:1px dashed var(--line); padding-top:6px; margin-top:4px; }
.cal-sessions b { color:var(--fg-soft); font-weight:600; }
.badge { display:inline-block; font-size:10.5px; font-family:var(--font-mono); letter-spacing:1px;
  border:1px solid var(--accent-line); color:var(--accent); border-radius:4px; padding:1px 6px; margin-left:8px; vertical-align:2px; }
.badge.win { border-color:var(--line-2); color:var(--fg-soft); }
.cal-legend { color:var(--dim); font-size:12.5px; margin: 6px 0 18px; }
"""


def session_line(race):
    parts = []
    for key, zh in (("FirstPractice", "練習一"), ("SecondPractice", "練習二"),
                    ("ThirdPractice", "練習三"), ("SprintQualifying", "衝刺排位"),
                    ("Sprint", "衝刺賽"), ("Qualifying", "排位賽")):
        s = race.get(key)
        if s:
            parts.append(f'<b>{zh}</b> {rc.taipei_disp(s.get("date"), s.get("time"))}')
    return "　·　".join(parts)


def build_cards(races, results_by_round, today):
    next_marked = False
    cards = []
    for race in races:
        rnd = int(race["round"])
        d = datetime.date.fromisoformat(race["date"])
        res = results_by_round.get(rnd)
        cls, badge = "", ""
        if res:
            cls = " done"
            w = res["Results"][0]
            badge = (f'<span class="badge win">冠軍 {rc.driver_pair(w["Driver"])}｜'
                     f'{rc.team_pair(w["Constructor"]["name"])}</span>')
        elif not next_marked and d >= today:
            cls, next_marked = " next", True
            badge = '<span class="badge">下一站</span>'
        if "Sprint" in race:
            badge += '<span class="badge">SPRINT</span>'
        race_dt = rc.taipei_disp(race["date"], race.get("time"))
        cid = race["Circuit"]["circuitId"]
        loc = race["Circuit"]["Location"]
        cards.append(
            f'<div class="cal-card{cls}">'
            f'<div class="cal-rnd">Rd<b>{rnd}</b></div>'
            f'<div><div class="cal-name">{rc.race_zh(race["raceName"])}'
            f'<span class="en">{html_lib.escape(race["raceName"])}</span>{badge}</div>'
            f'<div class="cal-circuit">{rc.circuit_pair(cid, race["Circuit"]["circuitName"])} · '
            f'{html_lib.escape(loc.get("locality",""))}, {html_lib.escape(loc.get("country",""))}</div></div>'
            f'<div class="cal-race"><span class="d">正賽（台北時間）</span><b>{race_dt}</b></div>'
            f'<div class="cal-sessions">{session_line(race)}</div>'
            '</div>')
    return "\n".join(cards)


def page_faq(season, n_races, n_sprints):
    # 賽季敘事（取消站、特例站）綁定年份——換季（改 site.json 的 season）後自動退場，
    # 新賽季有類似特例時在這裡按年份補。
    if season == 2026:
        count_a = (f"{n_races} 站。賽季原公布 24 站，巴林站與沙烏地站於 2026 年 3 月因中東情勢取消且不遞補，"
                   f"縮為 {n_races} 站；3 月澳洲墨爾本揭幕、12 月阿布達比收官。其中 {n_sprints} 站為衝刺賽（sprint）週末。")
    else:
        count_a = f"{n_races} 站，其中 {n_sprints} 站為衝刺賽（sprint）週末。詳細場次以官方公布賽曆為準。"
    faqs = [
        (f"{season} F1 賽季共有幾站？", count_a),
        ("表上的時間是哪個時區？",
         "全部是台北時間（UTC+8），由官方公布的 UTC 場次時刻換算，含正賽、排位賽、練習賽與衝刺賽。"
         "歐洲賽站正賽多在台北時間週日晚間 8 到 10 點，美洲賽站多在週一凌晨。"),
    ]
    if season == 2026:
        faqs.append(("為什麼 2026 年西班牙有兩站？",
                     "巴塞隆納加泰隆尼亞賽道續辦一站（6 月），馬德里新建的 Madring 市街賽道 9 月首辦，"
                     "後者掛正式名稱「西班牙大獎賽」。兩站都在西班牙，是 2026 賽曆的特例。"))
    faqs.append(("衝刺賽週末和一般週末有什麼不同？",
                 "衝刺賽週末只有一節自由練習，週五進行衝刺排位、週六先跑約 100 公里的衝刺賽（前 8 名計分 8 至 1 分），"
                 "之後才是正賽排位；週日正賽照常。一般週末則有三節練習加排位、正賽。"))
    return faqs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=rc.SEASON)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    args = ap.parse_args()
    season = args.season
    today = datetime.date.fromisoformat(args.today)

    sch = rc.load_data(season, "schedule.json")
    if not sch or not sch.get("races"):
        raise SystemExit("❌ 缺賽曆快照；先跑 python3 scripts/fetch_racing.py schedule")
    races = sch["races"]
    results_by_round = {r: race for r, race, _ in rc.load_results(season)}
    n_sprints = sum(1 for r in races if "Sprint" in r)

    canonical = f"{rc.BASE}/calendar/"
    faq = page_faq(season, len(races), n_sprints)
    done = sum(1 for v in results_by_round.values() if v)  # sprint-only round 不算完賽
    body = (f'<h1 class="pg-h1">F1 {season} 賽曆 · 台北時間</h1>'
            f'<div class="pg-sub">{season} 賽季全部 <b>{len(races)}</b> 站，正賽/排位/衝刺賽時刻均已換算為'
            f'<b>台北時間（UTC+8）</b>；已完賽 {done} 站標分站冠軍。</div>'
            '<div class="cal-legend">🏁 場次時刻依官方公布，如遇改期以主辦方最新公告為準。</div>'
            + build_cards(races, results_by_round, today)
            + rc.faq_html(faq)
            + ('<p class="asof-note">資料來源：jolpica-f1（Ergast 相容公開 API）；場次時刻為官方公布之 UTC 時間換算台北時間。'
               '本頁每週自動重建。本站為非官方資料整理站，無任何官方授權。</p>'))

    coll = {"@type": "CollectionPage", "@id": canonical, "url": canonical,
            "name": f"F1 {season} 賽曆（台北時間）", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{rc.BASE}/#website"}}
    # 賽站 SportsEvent（下一站起的未完賽站，最多 5 站——結構化資料給搜尋引擎的賽程訊號）
    events = []
    for race in races:
        if not results_by_round.get(int(race["round"])) and len(events) < 5:
            dt = rc.to_taipei(race["date"], race.get("time"))
            loc = race["Circuit"]["Location"]
            events.append({
                "@type": "SportsEvent", "name": f'F1 {rc.race_zh(race["raceName"])}',
                "startDate": dt.isoformat() if dt else race["date"],
                "eventStatus": "https://schema.org/EventScheduled",
                "location": {"@type": "Place",
                             "name": rc.circuit_zh(race["Circuit"]["circuitId"], race["Circuit"]["circuitName"]),
                             "address": {"@type": "PostalAddress",
                                         "addressLocality": loc.get("locality", ""),
                                         "addressCountry": loc.get("country", "")}},
                "sport": "Motorsport",
            })
    jsonld = rc.graph_ld([rc.org_node(), rc.website_node(), coll,
                          rc.breadcrumb_node([("首頁", f"{rc.BASE}/"), ("賽曆", canonical)]),
                          rc.faq_node(faq, canonical)] + events)
    desc = (f"F1 {season} 賽季 {len(races)} 站完整賽曆，正賽、排位賽、衝刺賽全部換算台北時間（UTC+8），"
            "含各站賽道資訊與分站冠軍，每週自動更新。")

    out = rc.PUB / "calendar"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(
        rc.page_shell(f"F1 {season} 賽曆 · 台北時間對照", desc, canonical, jsonld, body,
                      "calendar", extra_css=CAL_CSS),
        encoding="utf-8")
    print("✅ public-racing/calendar/index.html")
    rc.write_sitemap_part("calendar", [canonical])


if __name__ == "__main__":
    main()
