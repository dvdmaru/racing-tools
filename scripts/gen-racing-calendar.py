#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-racing-calendar.py — /calendar/ 台北時間賽曆頁（台灣讀者剛需，內容 6 件套之 ③）。

全季賽曆：每站正賽/排位/衝刺賽的台北時間（UTC+8 換算自 jolpica 的 UTC session 時刻），
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
import json
import pathlib
import urllib.parse

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
.cal-next { border:1px solid var(--accent-line); border-radius:14px; padding:16px 18px; margin: 4px 0 14px;
  background: var(--accent-soft); }
.cal-next .k { font-family:var(--font-mono); font-size:11px; letter-spacing:2px; color:var(--accent); }
.cal-next .nm { font-weight:800; font-size:19px; margin-top:2px; }
.cal-next .nm .en { color:var(--faint); font-size:12px; font-weight:500; margin-left:6px; }
.cal-next .when { margin-top:6px; font-size:14px; color:var(--fg-soft); }
.cal-next .when b { color:var(--accent); font-family:var(--font-mono); font-size:17px; }
.cal-next .cd { margin-top:6px; font-size:14px; font-weight:700; }
.cal-next .cd:empty { display:none; }
.cal-sub { border:1px dashed var(--line-2); border-radius:12px; padding:12px 16px; margin: 0 0 18px;
  font-size:13.5px; color:var(--dim); }
.cal-sub .btns { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
.cal-sub .btns a { display:inline-block; border:1px solid var(--accent-line); color:var(--accent); border-radius:999px;
  padding:7px 14px; text-decoration:none; font-weight:700; font-size:13.5px; }
.cal-sub .btns a:hover, .cal-sub .btns a:focus-visible { background: var(--accent-soft); }
/* 手機（2026-10-27 iPhone 13 模擬）：三欄把中間欄擠到冠軍徽章直排、一張已完賽卡約 330px 高，
   下一站前面要滑過 18 張。改兩欄（站次｜內容），正賽時刻落到內容下方；已完賽站不再列練習與排位時刻。 */
@media (max-width: 640px) {
  .cal-card { grid-template-columns: 40px 1fr; padding: 12px 14px; gap: 2px 12px; }
  .cal-race { grid-column: 2; text-align: left; }
  .cal-race .d { display: inline; margin-right: 6px; }
  .cal-sessions { grid-column: 1 / 3; }
  .cal-card.done .cal-sessions { display: none; }
  .badge { margin-left: 6px; }
  /* 冠軍徽章：站規讓 .zh-en 在 ≤640px 換成區塊（表格用），在小框裡會擠成四行；這裡改成名字下方一行 */
  .badge.win { display: block; margin: 4px 0 0; border: 0; padding: 0; font-size: 12.5px; letter-spacing: 0;
    font-family: var(--font-ui); }
  .badge.win .zh-en { display: inline; }
}
"""

# ---------- 行事曆訂閱（.ics，2026-10-27） ----------
# 賽曆是全站第一名的落地頁，但多數人查完時間就走（GA4 90 天互動率 33%、每次 1.1 頁）。
# 訂閱一次＝整季每一節都進手機行事曆，改期時訂閱端自動更新。
# 時間一律寫 UTC（DTSTART…Z），由使用者的行事曆換算成裝置所在時區；台北時間另寫在描述裡。
# ☠️ 內容必須 deterministic：verify-deploy 比對本機 build 與線上整檔 byte，
#    DTSTAMP 若寫「現在時刻」，每次 build 都不同＝工具永遠報差異。DTSTAMP 固定為賽季元旦。
SESSION_SPECS = (  # (schedule key, 中文名, 預估長度分鐘；官方不公布結束時刻，只能估)
    ("FirstPractice", "練習一", 60), ("SecondPractice", "練習二", 60),
    ("ThirdPractice", "練習三", 60), ("SprintQualifying", "衝刺排位", 45),
    ("Sprint", "衝刺賽", 60), ("Qualifying", "排位賽", 60),
)
RACE_MINUTES = 120


def ics_filename(season):
    return f"f1-{season}-taipei.ics"


def _utc(date_str, time_str):
    if not date_str or not time_str:
        return None
    return datetime.datetime.fromisoformat(f"{date_str}T{time_str.replace('Z', '')}+00:00")


def race_sessions(race):
    """一站的所有場次 → [(key, 中文名, UTC datetime, 分鐘)]，依開始時間排序；沒有時刻的場次略過。"""
    out = []
    for key, zh, minutes in SESSION_SPECS:
        s = race.get(key) or {}
        dt = _utc(s.get("date"), s.get("time"))
        if dt:
            out.append((key, zh, dt, minutes))
    dt = _utc(race.get("date"), race.get("time"))
    if dt:
        out.append(("Race", "正賽", dt, RACE_MINUTES))
    return sorted(out, key=lambda x: x[2])


def _ics_escape(text):
    """RFC 5545 §3.3.11 TEXT：反斜線、分號、逗號、換行要跳脫。"""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_fold(line):
    """RFC 5545 §3.1：每行 ≤75 octets，續行以一個空白開頭。按 UTF-8 octet 切，不切斷多位元組字元。"""
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        limit = 75 if not out else 74  # 續行的前導空白佔 1 octet
        if size + n > limit:
            out.append(cur)
            cur, size = "", 0
        cur += ch
        size += n
    out.append(cur)
    return "\r\n ".join(out)


def build_ics(season, races):
    stamp = f"{season}0101T000000Z"
    cal_url = f"{rc.BASE}/calendar/"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//racing.twtools.cc//F1 calendar//ZH-TW",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:F1 {season} 賽程（賽車數據誌）", "X-WR-TIMEZONE:Asia/Taipei",
             f"X-WR-CALDESC:{_ics_escape(f'F1 {season} 全季練習、排位、衝刺賽與正賽時刻。非官方整理，改期以主辦方公告為準。')}",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for race in races:
        rnd = int(race["round"])
        name = rc.race_zh(race["raceName"])
        circuit = rc.circuit_zh(race["Circuit"]["circuitId"], race["Circuit"]["circuitName"])
        for key, zh, dt, minutes in race_sessions(race):
            end = dt + datetime.timedelta(minutes=minutes)
            tpe = rc.taipei_disp(dt.date().isoformat(), dt.strftime("%H:%M:%SZ"))
            desc = (f"第 {rnd} 站{name}・{zh}。台北時間 {tpe}。"
                    f"結束時間為估計值。賽曆與賽果：{cal_url}")
            lines += ["BEGIN:VEVENT",
                      f"UID:{season}-r{rnd:02d}-{key.lower()}@racing.twtools.cc",
                      f"DTSTAMP:{stamp}",
                      f"DTSTART:{dt:%Y%m%dT%H%M%SZ}",
                      f"DTEND:{end:%Y%m%dT%H%M%SZ}",
                      f"SUMMARY:{_ics_escape(f'F1 {name}｜{zh}')}",
                      f"LOCATION:{_ics_escape(circuit)}",
                      f"DESCRIPTION:{_ics_escape(desc)}",
                      f"URL:{cal_url}",
                      "TRANSP:TRANSPARENT",
                      "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "".join(_ics_fold(line) + "\r\n" for line in lines)


def subscribe_html(season):
    https_url = f"{rc.BASE}/calendar/{ics_filename(season)}"
    webcal = "webcal://" + https_url.split("://", 1)[1]
    google = "https://calendar.google.com/calendar/render?cid=" + urllib.parse.quote(webcal, safe="")
    return ('<div class="cal-sub" id="subscribe"><b>把全季賽程加進手機行事曆</b>：練習、排位、衝刺賽、正賽一次加入，'
            '時間依你的裝置時區顯示（在台灣就是台北時間）；賽程改期時，訂閱的行事曆會自動更新。'
            '<div class="btns">'
            f'<a href="{webcal}">iPhone／Mac 訂閱</a>'
            f'<a href="{html_lib.escape(google)}" target="_blank" rel="noopener">Google 日曆訂閱</a>'
            f'<a href="/calendar/{ics_filename(season)}" download>下載 .ics 檔</a>'
            '</div></div>')


def next_race(races, results_by_round, today):
    """與 build_cards 同一條規則：第一個沒有正賽結果、且日期不早於今天的站。"""
    for race in races:
        if (not results_by_round.get(int(race["round"]))
                and datetime.date.fromisoformat(race["date"]) >= today):
            return race
    return None


# 倒數只能在瀏覽器算：本頁每週才重建一次，寫死在 HTML 裡的「還有 N 天」隔天就錯。
# 沒有 JS 時只看得到伺服器端印好的台北時間，資訊不缺。比賽結束到下次重建之間不會停在
# 「0 分」，改顯示本站已結束。
NEXT_JS = """(function(){var el=document.querySelector('[data-cal-next]');if(!el)return;
var ss=JSON.parse(el.getAttribute('data-sessions')||'[]'),out=el.querySelector('.cd');if(!out)return;
function f(ms){var m=Math.floor(ms/60000),d=Math.floor(m/1440),h=Math.floor(m%1440/60),mm=m%60;
return(d?d+' 天 ':'')+(d||h?h+' 小時 ':'')+mm+' 分';}
function tick(){var now=Date.now();for(var i=0;i<ss.length;i++){var st=Date.parse(ss[i].t),en=st+ss[i].m*60000;
if(now<st){out.textContent=ss[i].n+'還有 '+f(st-now);return;}
if(now<en){out.textContent=ss[i].n+'進行中';return;}}
out.textContent='本站已結束，賽果於下次自動更新時補上';}
tick();setInterval(tick,30000);})();"""


def next_race_html(race):
    if not race:
        return ""
    rnd = int(race["round"])
    name_en = html_lib.escape(race["raceName"])
    name_zh = html_lib.escape(rc.race_zh(race["raceName"]))
    name_html = name_zh if name_zh == name_en else f'{name_zh}<span class="en">{name_en}</span>'
    sessions = [{"n": zh, "t": dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "m": minutes}
                for _, zh, dt, minutes in race_sessions(race)]
    data = html_lib.escape(json.dumps(sessions, ensure_ascii=False), quote=True)
    sprint = "（衝刺賽週末）" if "Sprint" in race else ""
    return (f'<div class="cal-next" data-cal-next data-sessions="{data}">'
            '<div class="k">NEXT · 下一站</div>'
            f'<div class="nm">Rd{rnd} {name_html}{sprint}</div>'
            f'<div class="when">正賽 · 台北時間 <b>{rc.taipei_disp(race["date"], race.get("time"))}</b></div>'
            '<div class="cd" aria-live="polite"></div>'
            '</div>'
            f'<script>{NEXT_JS}</script>')


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
            badge = (f'<span class="badge win">冠軍 {rc.entity_link(rc.driver_pair(w["Driver"]), "drivers", w["Driver"].get("driverId", ""))}｜'
                     f'{rc.entity_link(rc.team_pair(w["Constructor"]["name"]), "constructors", w["Constructor"].get("constructorId", ""))}</span>')
        elif not next_marked and d >= today:
            cls, next_marked = " next", True
            badge = '<span class="badge">下一站</span>'
        if "Sprint" in race:
            badge += '<span class="badge">SPRINT</span>'
        race_dt = rc.taipei_disp(race["date"], race.get("time"))
        cid = race["Circuit"]["circuitId"]
        loc = race["Circuit"]["Location"]
        # ⚠️ 沒有核准譯名時 race_zh() 回原文（誠實 fallback），此時**不能再補一次原文**，
        # 否則同一列會印兩次英文名。2026 R16「Bahrain Grand Prix in Malaysia」是第一個
        # 觸發此路徑的賽事名稱（新增賽事名稱進 race-zh.json 前必然經過 pending 階段）。
        # 這裡的守衛與 racinglib.race_pair 同一條規則，只是賽曆頁用自己的 .en 樣式。
        name_en = html_lib.escape(race["raceName"])
        name_zh = html_lib.escape(rc.race_zh(race["raceName"]))
        name_html = name_zh if name_zh == name_en else f'{name_zh}<span class="en">{name_en}</span>'
        cards.append(
            f'<div class="cal-card{cls}">'
            f'<div class="cal-rnd">Rd<b>{rnd}</b></div>'
            f'<div><div class="cal-name">{name_html}{badge}</div>'
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
        # ⚠️ 這段敘述**不要再寫死站數的加減**。原文是「原公布 24 站…取消且不遞補，縮為 22 站」，
        # 而 n_races 是從賽曆資料動態算的：2026-07-27 巴林站確定移師雪邦後 API 變 23 站，
        # 這句就會自己長成「23 站。原公布 24 站…縮為 23 站」＝當著讀者的面算錯數。
        # 規則：可變的量一律交給 n_races/n_sprints，寫死的部分只描述**發生過的事件**。
        count_a = (f"{n_races} 站。賽季原公布 24 站，巴林站與沙烏地站於 2026 年 3 月因中東情勢"
                   f"宣布不在原定的 4 月舉行；其後巴林站確定移師馬來西亞雪邦國際賽道，"
                   f"於 10 月 2 至 4 日補辦並沿用「巴林大獎賽」名稱，沙烏地站未再排入賽曆。"
                   f"3 月澳洲墨爾本揭幕、12 月阿布達比收官，其中 {n_sprints} 站為衝刺賽（sprint）週末。")
    else:
        count_a = f"{n_races} 站，其中 {n_sprints} 站為衝刺賽（sprint）週末。詳細場次以官方公布賽曆為準。"
    faqs = [
        (f"{season} F1 賽季共有幾站？", count_a),
        ("表上的時間是哪個時區？",
         "全部是台北時間（UTC+8），由官方公布的 UTC 場次時刻換算，含正賽、排位賽、練習賽與衝刺賽。"
         "歐洲賽站正賽多在台北時間週日晚間 8 到 10 點，美洲賽站多在週一凌晨。"),
    ]
    if season == 2026:
        # ⚠️ 外電普遍寫「F1 首次把大獎賽與地理位置分開」——**本站不採用這句**。
        # 用本站賽事資料（1950 年起 1,172 場、56 種賽事名稱）實查，名稱國別與舉辦國不符的
        # 先例至少 29 場：聖馬利諾站 26 屆全在義大利、盧森堡站 2 屆全在德國、1982 瑞士站在法國。
        # 可支撐的「第一次」只有更窄的那個：名稱同時寫出兩個地名。降強度後才寫。
        faqs.append(("為什麼比賽在馬來西亞舉行，卻叫「巴林大獎賽」？",
                     "因為移動的是舉辦地點，不是這場大獎賽的權利歸屬。巴林方負擔主辦費用並保有賽事收益、"
                     "冠名贊助商未更動，官方全稱為 Formula 1 Gulf Air Bahrain Grand Prix in Malaysia；"
                     "雪邦國際賽道是承辦場地，馬來西亞負擔在地籌辦成本，這一站仍計為巴林站。"
                     "名稱與舉辦地不符在 F1 並非首例——聖馬利諾大獎賽 26 屆全在義大利伊莫拉舉行、"
                     "盧森堡大獎賽 2 屆都在德國紐柏林、1982 年瑞士大獎賽辦在法國第戎；"
                     "但就 1950 年以來的世界錦標賽賽事而言，把兩個地名同時寫進正式名稱的，這是第一次。"))
        faqs.append(("為什麼 2026 年西班牙有兩站？",
                     "巴塞隆納加泰隆尼亞賽道續辦一站（6 月），馬德里新建的 Madring 市街賽道 9 月首辦，"
                     "後者掛正式名稱「西班牙大獎賽」。兩站都在西班牙，是 2026 賽曆的特例。"))
    faqs.append(("怎麼把 F1 賽程加進手機行事曆？",
                 "本頁上方有訂閱連結：iPhone／Mac 點「iPhone／Mac 訂閱」，Google 日曆點「Google 日曆訂閱」，"
                 "其他行事曆可下載 .ics 檔匯入。訂閱後全季練習、排位、衝刺賽、正賽都會出現在行事曆裡，"
                 "時間依裝置時區顯示；賽程改期時訂閱的行事曆會自動更新，下載匯入的則不會。"))
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
            + next_race_html(next_race(races, results_by_round, today))
            + subscribe_html(season)
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
    (out / ics_filename(season)).write_bytes(build_ics(season, races).encode("utf-8"))
    print(f"✅ public-racing/calendar/{ics_filename(season)}")
    rc.write_sitemap_part("calendar", [canonical])


if __name__ == "__main__":
    main()
