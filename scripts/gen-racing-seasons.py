#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-racing-seasons.py — 百科線 M3：/seasons/（77 季索引）＋ /seasons/2002/（單一賽季頁，定調用）。

server-rendered、零 client fetch（除 page_shell 既有 theme init inline script 外零 JS）；
tabs 一律走 racinglib 的 CSS-only tabgroup。實體專屬視覺（stat 卡、賽季弧線、退賽橫條圖、
「怎麼算的」展開、pair 中英對照）沿用 Phase 0 原型（gen-racing-entities-phase0.py），
直接 import 重用，不複製、不改動 phase0（它還要跑出互連的另一端 /drivers/、/constructors/）。

★ 衍生數字紀律（承 f1stats 圓桌教訓）：每個統計 value == len(detail)，或直接取自官方
  standings（SOURCED）。只做加減可驗的衍生（分差、退賽數）——不做「封王站/clinch」類複雜衍生。
  分差 = 兩個 SOURCED 積分之差，附「怎麼算的」展開回指兩列 standings。

★ 譯名誠實 fallback：譯名只准來自 driver-zh.json／team-zh.json（racinglib 載入）＋ Phase 0
  已核准 8 實體（phase0 ZH dict）。查無譯名 → 只留原文（照 phase0 pair()）。嚴禁自譯人名/隊名。
  退賽 status 的中文只是「共通名詞 gloss」（引擎/碰撞…）且一律並列原文；status 原文在明細中
  逐字呈現、不直譯因果（不把「Engine」寫成「引擎爆缸導致退賽」）。

★ JSON-LD 型別選擇（賽季頁）：採「每站一個 top-level SportsEvent 節點」，不採「整季一個
  SportsEvent」也不採「ItemList 包 SportsEvent」。理由：
  (1) 每場大獎賽是單一場地、單一日期的真實事件，1:1 對映 SportsEvent 的必填 startDate +
      location(Place+geo)，Google Event/SportsEvent rich result 能直接解析每一站；
  (2) 「整季一個 SportsEvent」會被迫給一個橫跨十餘國、數月的單一 location/startDate——那是
      捏造，違反誠實紀律，故棄用；
  (3) top-level 節點（而非塞進 ItemList.itemListElement）因為 Google 的 Event 解析器辨識
      獨立 Event 節點、卻不會從 ItemList 內抽取 event，top-level 讓每站都具 rich-result 資格；
  (4) 座標僅在 raw schedule 的 Circuit.Location 有 lat/long 時輸出，沒有就不放（不假裝）；
  (5) 全部與 org/website/CollectionPage/breadcrumb 掛在共用 @graph。sameAs 放維基、不放 image、
      不放任何官方素材連結。
  索引頁則用 ItemList（導覽型清單語意較貼切；每項 url 只填已存在的頁）。

★ sitemap part（M0 manifest 機制）：owner=seasons，但 **M3 預設不寫**——頁面未公開前 sitemap
  不得出現這些 URL（避免 GSC 抓到尚未定調的頁）。只有 --publish 才寫 data/sitemap-parts/seasons.txt；
  --no-sitemap 為顯式關閉（與預設同義，供 pipeline 明示用）。

用法：
  python3 scripts/gen-racing-seasons.py                 # 索引 + 2002 賽季頁（不寫 sitemap）
  python3 scripts/gen-racing-seasons.py --season 2002   # 同上，明示賽季
  python3 scripts/gen-racing-seasons.py --index-only     # 只重建索引
  python3 scripts/gen-racing-seasons.py --publish        # 公開時才加：寫 sitemap part
"""
import argparse
import html as html_lib
import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rc = _load("racinglib", "racinglib.py")
fs = _load("f1stats", "f1stats.py")
# Phase 0 當視覺元件庫用：import 只載模組（main 在 __main__ 下不執行），不寫任何檔、不改 phase0
p0 = _load("gen_racing_entities_phase0", "gen-racing-entities-phase0.py")

RAW = ROOT / "data" / "f1" / "raw"
PUB = rc.PUB
BASE = rc.BASE
esc = html_lib.escape

FIRST_YEAR, LAST_YEAR = 1950, rc.SEASON  # 1950–2026

# ---------- 譯名解析（誠實 fallback；phase0 8 實體 overlay 在 racinglib 表之上） ----------
_P0_DRIVER_ZH = {k: v for k, v in p0.ZH.items()
                 if k in ("michael_schumacher", "hamilton", "senna", "max_verstappen")}
_P0_TEAM_ZH = {k: v for k, v in p0.ZH.items()
               if k in ("ferrari", "mclaren", "mercedes", "red_bull")}
DRIVER_ZH = {**rc.DRIVER_ZH, **_P0_DRIVER_ZH}
TEAM_ZH_BY_ID = {**{k: v for k, v in rc.TEAM_ZH.items()}, **_P0_TEAM_ZH}


def zh_driver(did):
    return DRIVER_ZH.get(did)  # None → 誠實只留原文


def zh_team(cid, name):
    return TEAM_ZH_BY_ID.get(cid) or rc.TEAM_ZH.get(name)


def _driver_full(drv):
    return f'{drv.get("givenName", "")} {drv.get("familyName", "")}'.strip()


def driver_pair(drv):
    """車手中英對照 html（phase0 pair：zh 缺就只留原文的 en-only span）。"""
    return p0.pair(zh_driver(drv.get("driverId", "")), _driver_full(drv))


def team_pair(cid, name):
    return p0.pair(zh_team(cid, name), name)


def name_plain(zh, en):
    """敘事句用的純文字姓名：有譯名 → 「譯名（原文）」，無 → 只原文。"""
    return f"{zh}（{en}）" if zh else en


# ---------- 資料讀取 ----------

def _load_json(p):
    return p0._load(p)


def _driver_standings(year):
    p = RAW / "standings" / f"driver-{year}.json"
    return _load_json(p).get("DriverStandings", []) if p.exists() else []


def _constructor_standings(year):
    p = RAW / "standings" / f"constructor-{year}.json"
    return _load_json(p).get("ConstructorStandings", []) if p.exists() else []


def _schedule(year):
    p = RAW / f"season-{year}-schedule.json"
    return _load_json(p).get("Races", []) if p.exists() else []


def _season_rounds(year):
    """分站數 = standings 檔的 round 欄（該季最終站次，SOURCED）；抓不到退回 schedule 長度。"""
    p = RAW / "standings" / f"driver-{year}.json"
    if p.exists():
        r = _load_json(p).get("round")
        if r:
            return int(r)
    return len(_schedule(year))


# ---------- 索引頁資料列（進行中賽季不顯示冠軍——踩過把榜首當冠軍的錯） ----------

def index_row(year):
    """回一季的索引資料。未完賽（fs._is_completed=False）→ champion 一律 None、in_progress=True。"""
    completed = fs._is_completed(year)
    ds = _driver_standings(year)
    cs = _constructor_standings(year)
    # 進行中賽季：rounds 是「已完成站次」不是全季總站數（查核桌 T-01）——
    # 另帶 scheduled 供索引頁顯示「10 / 22」，避免讀者把已跑站次誤讀為全季分站數。
    row = {"year": year, "rounds": _season_rounds(year),
           "scheduled": len(_schedule(year)),
           "in_progress": not completed,
           "driver_champ": None, "constructor_champ": None}
    if completed:
        if ds:
            d = ds[0]["Driver"]
            row["driver_champ"] = {"id": d.get("driverId", ""), "zh": zh_driver(d.get("driverId", "")),
                                   "en": _driver_full(d), "drv": d}
        if cs:
            c = cs[0]["Constructor"]
            row["constructor_champ"] = {"id": c.get("constructorId", ""),
                                        "zh": zh_team(c.get("constructorId", ""), c.get("name", "")),
                                        "en": c.get("name", "")}
    return row


# ---------- 退賽原因分布（§8-3；value == len(detail) 紀律） ----------

def is_finisher(status):
    """完賽判定：status 為 'Finished' 或 '+N Lap(s)'（落後圈數完賽）為完賽；其餘皆算未完賽。"""
    return status == "Finished" or bool(re.match(r"^\+\d+ Lap", status))


# status → 共通名詞 gloss（不是因果直譯；label 一律並列原文，明細逐字呈現 status 原文）
STATUS_ZH = {
    "Engine": "引擎", "Collision": "碰撞", "Spun off": "打滑失控", "Hydraulics": "液壓",
    "Gearbox": "變速箱", "Suspension": "懸吊", "Accident": "事故", "Brakes": "煞車",
    "Mechanical": "機械", "Transmission": "傳動", "Electrical": "電路", "Clutch": "離合器",
    "Driveshaft": "傳動軸", "Throttle": "節氣門", "Disqualified": "取消資格",
    "Overheating": "過熱", "Power loss": "動力流失", "Exhaust": "排氣", "Rear wing": "尾翼",
    "Safety": "安全考量", "Broken wing": "尾翼損壞", "Fuel": "燃油", "Wheel rim": "輪圈",
    "Fuel pressure": "燃油壓力", "Oil pressure": "機油壓力", "Wheel": "輪組",
    "Electronics": "電子系統", "Drivetrain": "動力傳動", "Ignition": "點火", "Injury": "傷勢",
    "Chassis": "底盤", "Steering": "轉向", "Injured": "傷勢",
}


def season_retirements(year):
    """回退賽分類 [{status, zh, value(=len detail), detail:[{round,race,driver_id,driver}]}]，
    人次由多至少排序。value 一律 len(detail)，總數 = 各類 value 加總。"""
    sched_name = {int(r["round"]): r["raceName"] for r in _schedule(year)}
    buckets = {}
    for rnd in range(1, _season_rounds(year) + 1):
        rp = RAW / "results" / f"{year}-{rnd:02d}.json"
        if not rp.exists():
            continue
        data = _load_json(rp)
        race_name = data.get("raceName") or sched_name.get(rnd, f"Round {rnd}")
        for res in data.get("Results", []):
            status = res.get("status", "")
            if is_finisher(status):
                continue
            drv = res.get("Driver", {})
            buckets.setdefault(status, []).append({
                "round": rnd, "race": race_name,
                "driver_id": drv.get("driverId", ""), "driver": _driver_full(drv),
                "source": f"data/f1/raw/results/{year}-{rnd:02d}.json",
            })
    cats = [{"status": s, "zh": STATUS_ZH.get(s), "value": len(d), "detail": d}
            for s, d in buckets.items()]
    cats.sort(key=lambda c: (-c["value"], c["status"]))
    return cats


# ---------- 分差（SOURCED − SOURCED，附回指） ----------

def points_gap(year):
    """回 (champ_pts, second_pts, gap)；gap = 冠軍積分 − 第二名積分（兩列 standings 之差）。"""
    ds = _driver_standings(year)
    if len(ds) < 2:
        return (int(ds[0]["points"]) if ds else 0, 0, 0)
    champ = int(ds[0]["points"])
    second = int(ds[1]["points"])
    return champ, second, champ - second


# ---------- 規則化敘事句（模板 + 資料，非 LLM；每個數字都能在頁面明細找到） ----------

def season_narrative(year):
    """回 list[str] 純文字敘事句。名字用「譯名（原文）」或只原文（誠實 fallback）。"""
    ds = _driver_standings(year)
    cs = _constructor_standings(year)
    rounds = _season_rounds(year)
    champ_pts, second_pts, gap = points_gap(year)
    cd = ds[0]["Driver"] if ds else {}
    champ_name = name_plain(zh_driver(cd.get("driverId", "")), _driver_full(cd))
    lines = []
    if len(ds) >= 2:
        sd = ds[1]["Driver"]
        second_name = name_plain(zh_driver(sd.get("driverId", "")), _driver_full(sd))
        lines.append(
            f"{year} 賽季共 {rounds} 站。{champ_name} 以 {champ_pts} 分奪下車手世界冠軍，"
            f"領先第二名 {second_name} {gap} 分。")
    elif ds:
        lines.append(f"{year} 賽季共 {rounds} 站，車手世界冠軍為 {champ_name}（{champ_pts} 分）。")
    if cs:
        cc = cs[0]["Constructor"]
        cons_name = name_plain(zh_team(cc.get("constructorId", ""), cc.get("name", "")), cc.get("name", ""))
        lines.append(f"車隊世界冠軍由 {cons_name} 以 {cs[0]['points']} 分拿下。")
    cats = season_retirements(year)
    total_ret = sum(c["value"] for c in cats)
    if cats:
        top = cats[0]
        top_label = name_plain(top["zh"], top["status"])
        lines.append(
            f"全季正賽共 {total_ret} 人次未完賽（完賽名次為 Finished 或落後圈數者不計），"
            f"其中登記事由為「{top_label}」者 {top['value']} 次為最多。")
    return lines


# ---------- 渲染：索引頁 /seasons/ ----------

def _index_champ_cell(champ):
    if champ is None:
        return '<span class="dim">—</span>'
    return p0.pair(champ["zh"], champ["en"])


def render_index():
    rows_html = []
    urls = []
    for year in range(LAST_YEAR, FIRST_YEAR - 1, -1):  # 新到舊
        row = index_row(year)
        year_cell = (p0.internal_link(f"seasons/{year}", f'<span class="mono">{year}</span>')
                     if f"seasons/{year}" in p0.HAS_PAGE
                     else f'<span class="mono">{year}</span>')
        if row["in_progress"]:
            dchamp = '<span class="ip">進行中</span>'
            cchamp = '<span class="ip">進行中</span>'
            # T-01：進行中賽季顯示「已跑 / 全季」，避免把已跑站次誤讀為全季分站數
            rounds_cell = f'{row["rounds"]} / {row["scheduled"]}'
        else:
            dchamp = _index_champ_cell(row["driver_champ"])
            cchamp = _index_champ_cell(row["constructor_champ"])
            rounds_cell = str(row["rounds"])
        rows_html.append(
            f'<tr><td class="l">{year_cell}</td>'
            f'<td class="l">{dchamp}</td>'
            f'<td class="l">{cchamp}</td>'
            f'<td class="mono">{rounds_cell}</td></tr>')
    table = ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
             '<th class="l">賽季</th><th class="l">車手世界冠軍</th>'
             '<th class="l">車隊世界冠軍</th><th>分站數</th>'
             f'</tr></thead><tbody>{"".join(rows_html)}</tbody></table></div>')

    canonical = f"{BASE}/seasons/"
    intro = (f'<div class="pg-sub">一級方程式 <b>{FIRST_YEAR}–{LAST_YEAR}</b> 共 '
             f'<b>{LAST_YEAR - FIRST_YEAR + 1}</b> 個賽季的車手與車隊世界冠軍、分站數一覽。'
             '進行中的賽季只顯示「進行中」不列冠軍（榜首＝目前領先，非冠軍）。'
             '中文名採台灣慣用譯名並附原文，查無定版譯名者誠實只列原文。</div>')
    note = ('<p class="note">目前僅 <b>2002</b> 賽季已建詳細頁（可點）；其餘賽季詳細頁陸續補上。'
            '冠軍認定一律取自資料源該季<b>最終官方積分榜</b>榜首，本站不自行計算。'
            '分站數取自積分榜快照的最終站次（round）欄；'
            '進行中賽季顯示「已跑站次 / 全季排定站數」。</p>')
    body = (f'<h1 class="pg-h1">歷屆賽季</h1>{intro}{table}{note}')

    # JSON-LD：org+website+CollectionPage+breadcrumb+ItemList（url 只填已存在的頁）
    items = []
    for i, year in enumerate(range(LAST_YEAR, FIRST_YEAR - 1, -1)):
        el = {"@type": "ListItem", "position": i + 1, "name": f"{year} 一級方程式賽季"}
        if f"seasons/{year}" in p0.HAS_PAGE:
            el["url"] = f"{BASE}/seasons/{year}/"
        items.append(el)
    coll = {"@type": "CollectionPage", "@id": canonical, "url": canonical,
            "name": f"歷屆一級方程式賽季（{FIRST_YEAR}–{LAST_YEAR}）", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{BASE}/#website"}}
    item_list = {"@type": "ItemList", "name": f"F1 賽季列表 {FIRST_YEAR}–{LAST_YEAR}",
                 "numberOfItems": len(items), "itemListElement": items}
    jsonld = rc.graph_ld([rc.org_node(), rc.website_node(), coll,
                          rc.breadcrumb_node([("首頁", f"{BASE}/"), ("賽季", canonical)]),
                          item_list])
    desc = (f"一級方程式 {FIRST_YEAR}–{LAST_YEAR} 歷屆賽季車手與車隊世界冠軍、分站數索引，"
            "台灣慣用繁中譯名＋原文對照。")
    html = rc.page_shell("歷屆一級方程式賽季總覽", desc, canonical, jsonld, body,
                         active="", extra_css=p0.ENTITY_CSS + SEASON_CSS)
    out = PUB / "seasons"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ /seasons/　（{LAST_YEAR - FIRST_YEAR + 1} 季）")
    return canonical


# ---------- 渲染：單一賽季頁 /seasons/2002/ ----------

def _std_driver_table(ds):
    rows = []
    for r in ds:
        drv = r["Driver"]
        lead = ' class="lead"' if r.get("position") == "1" else ""
        cons = (r.get("Constructors") or [{}])[-1]
        link = p0.internal_link(f'drivers/{drv.get("driverId", "").replace("_", "-")}', driver_pair(drv))
        pos = r.get("position") or r.get("positionText", "")
        rows.append(
            f'<tr{lead}><td class="rk">{pos}</td>'
            f'<td class="l nm">{link}</td>'
            f'<td class="l">{team_pair(cons.get("constructorId", ""), cons.get("name", ""))}</td>'
            f'<td class="std-pts">{r["points"]}</td><td>{r.get("wins", "0")}</td></tr>')
    return ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
            '<th class="rk">#</th><th class="l">車手</th><th class="l">車隊</th>'
            '<th>積分</th><th>分站冠軍</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def _std_constructor_table(cs):
    rows = []
    for r in cs:
        c = r["Constructor"]
        lead = ' class="lead"' if r.get("position") == "1" else ""
        link = p0.internal_link(f'constructors/{c.get("constructorId", "").replace("_", "-")}',
                                team_pair(c.get("constructorId", ""), c.get("name", "")))
        pos = r.get("position") or r.get("positionText", "")
        rows.append(
            f'<tr{lead}><td class="rk">{pos}</td>'
            f'<td class="l nm">{link}</td>'
            f'<td class="std-pts">{r["points"]}</td><td>{r.get("wins", "0")}</td></tr>')
    return ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
            '<th class="rk">#</th><th class="l">車隊</th><th>積分</th><th>分站冠軍</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def _gap_details(year, champ_pts, second_pts, gap, champ_name, second_name):
    return f"""<details class="how">
  <summary>怎麼算的</summary>
  <div class="how-body">
    <ol class="detail-list">
      <li title="來源檔：data/f1/raw/standings/driver-{year}.json#pos1">冠軍 {esc(champ_name)}：<b>{champ_pts}</b> 分（該季最終車手積分榜榜首）</li>
      <li title="來源檔：data/f1/raw/standings/driver-{year}.json#pos2">第二名 {esc(second_name)}：<b>{second_pts}</b> 分（同榜第 2 名）</li>
    </ol>
    <p class="prov">分差 ＝ {champ_pts} − {second_pts} ＝ <b>{gap}</b>。兩個數字皆直接取自該季最終官方車手積分榜，本站只做減法。</p>
  </div>
</details>"""


def _retirement_chart(cats):
    if not cats:
        return '<p class="note">本季無退賽紀錄可聚合。</p>'
    maxv = max(c["value"] for c in cats)
    total = sum(c["value"] for c in cats)
    rows = []
    for c in cats:
        pct = c["value"] / maxv * 100
        label = f'{c["zh"]}<span class="rt-en">　{esc(c["status"])}</span>' if c["zh"] else f'<span class="rt-en">{esc(c["status"])}</span>'
        detail = "".join(
            f'<li title="來源檔：{esc(d["source"])}"><span class="mono">R{d["round"]:02d}</span> '
            f'{esc(d["race"])} · {esc(d["driver"])} · <span class="rt-status">{esc(c["status"])}</span></li>'
            for d in c["detail"])
        rows.append(
            f'<details class="rt"><summary>'
            f'<span class="rt-label">{label}</span>'
            f'<span class="rt-bar"><span class="rt-fill" style="width:{pct:.1f}%"></span></span>'
            f'<span class="rt-n mono">{c["value"]}</span></summary>'
            f'<ol class="detail-list rt-detail">{detail}</ol></details>')
    head = (f'<p class="note">全季正賽共 <b>{total}</b> 人次未完賽，依登記事由（status）分類如下。'
            '每一類的數字＝下方展開明細的筆數；明細逐筆列出<b>第幾站、車手、status 原文</b>，'
            'status 不直譯因果（例如 <span class="rt-status">Engine</span> 僅為賽果登記事由，'
            '非本站對退賽機制的斷言）。</p>')
    return head + '<div class="rt-chart">' + "".join(rows) + '</div>'


def _race_event_nodes(year, schedule, season_url):
    nodes = []
    for r in schedule:
        circ = r.get("Circuit", {})
        loc = circ.get("Location", {})
        place = {"@type": "Place", "name": circ.get("circuitName", "")}
        addr = {"@type": "PostalAddress"}
        if loc.get("locality"):
            addr["addressLocality"] = loc["locality"]
        if loc.get("country"):
            addr["addressCountry"] = loc["country"]
        if len(addr) > 1:
            place["address"] = addr
        if loc.get("lat") and loc.get("long"):
            place["geo"] = {"@type": "GeoCoordinates",
                            "latitude": loc["lat"], "longitude": loc["long"]}
        node = {"@type": "SportsEvent", "name": f'{year} {r.get("raceName", "")}',
                "sport": "Formula One", "eventStatus": "https://schema.org/EventScheduled",
                "location": place, "isPartOf": {"@id": f"{season_url}#page"}}
        if r.get("date"):
            node["startDate"] = r["date"]
        if r.get("url"):
            node["sameAs"] = r["url"]  # 維基（誠實 fallback：只放公開百科，不放官方素材）
        nodes.append(node)
    return nodes


def render_season(year):
    ds = _driver_standings(year)
    cs = _constructor_standings(year)
    sched = _schedule(year)
    if not ds or not cs:
        raise SystemExit(f"❌ 缺 {year} 積分榜資料（driver-{year}.json / constructor-{year}.json）")
    if not fs._is_completed(year):
        raise SystemExit(f"❌ {year} 尚未完賽——M3 賽季頁模板以已完賽季為前提（冠軍認定），拒絕產出。")

    canonical = f"{BASE}/seasons/{year}/"
    rounds = _season_rounds(year)
    champ_pts, second_pts, gap = points_gap(year)
    cd = ds[0]["Driver"]
    champ_zh, champ_en = zh_driver(cd.get("driverId", "")), _driver_full(cd)
    sd = ds[1]["Driver"] if len(ds) > 1 else {}
    champ_link = p0.internal_link(f'drivers/{cd.get("driverId", "").replace("_", "-")}',
                                  driver_pair(cd))
    cc = cs[0]["Constructor"]
    cons_link = p0.internal_link(f'constructors/{cc.get("constructorId", "").replace("_", "-")}',
                                 team_pair(cc.get("constructorId", ""), cc.get("name", "")))

    # Hero
    hero = f"""<div class="ent-hero">
  <p class="ent-kicker">賽季 · Season</p>
  <h1 class="ent-h1">{year} 賽季</h1>
  <div class="ident">
    <span>分站數 <span class="mono">{rounds}</span></span>
    <span>車手冠軍 {champ_link}</span>
    <span>車隊冠軍 {cons_link}</span>
  </div>
</div>"""

    # Hero stat 卡：冠軍積分 / 對第二名分差（分差附「怎麼算的」）
    champ_name_plain = name_plain(champ_zh, champ_en)
    second_name_plain = name_plain(zh_driver(sd.get("driverId", "")), _driver_full(sd)) if sd else "—"
    stat_cards = f"""<div class="stat-grid">
  <div class="stat"><div class="stat-v mono">{champ_pts}<span class="unit"> 分</span></div>
    <div class="stat-l">冠軍最終積分</div>
    <p class="na-why">{esc(champ_name_plain)}，取自該季最終車手積分榜榜首。</p></div>
  <div class="stat"><div class="stat-v mono">{gap}<span class="unit"> 分</span></div>
    <div class="stat-l">領先第二名</div>
    {_gap_details(year, champ_pts, second_pts, gap, champ_name_plain, second_name_plain)}</div>
  <div class="stat"><div class="stat-v mono">{ds[0].get("wins", "0")}<span class="unit"> 勝</span></div>
    <div class="stat-l">冠軍當季分站冠軍</div>
    <p class="na-why">取自積分榜的 wins 欄（該季分站冠軍場次）。</p></div>
</div>"""

    # 賽季弧線：冠軍逐站名次（reuse phase0 season_arc）
    dpos = []
    cdid = cd.get("driverId")
    for rnd in range(1, rounds + 1):
        rp = RAW / "results" / f"{year}-{rnd:02d}.json"
        if not rp.exists():
            continue
        for res in _load_json(rp).get("Results", []):
            if res.get("Driver", {}).get("driverId") == cdid:
                try:
                    dpos.append((rnd, int(res["position"])))
                except (ValueError, KeyError):
                    pass
    arc = p0.season_arc(cdid, dpos)

    # 積分榜 tabs（CSS-only，全列不只前十）
    tabs = rc.tabgroup("ss", [
        ("drv", "車手積分榜", _std_driver_table(ds), ""),
        ("con", "車隊積分榜", _std_constructor_table(cs), ""),
    ])

    # 退賽原因分布
    cats = season_retirements(year)
    chart = _retirement_chart(cats)

    # 規則化敘事句
    narr = "".join(f"<p>{esc(s)}</p>" for s in season_narrative(year))

    body = f"""{hero}
{stat_cards}

<div class="sec-title">賽季速寫</div>
<div class="narrative">{narr}</div>

<div class="sec-title">車手冠軍逐站名次</div>
<p class="note">x 軸＝分站、y 軸＝完賽名次（第 1 在上）。{p0.pair(champ_zh, champ_en)} 那條線壓在頂端的程度，就是那一季的統治力。</p>
{arc}

<div class="sec-title">積分榜</div>
{tabs}

<div class="sec-title">退賽原因分布</div>
{chart}

<p class="note">積分與名次直接取自資料源的該季<b>最終官方積分榜</b>，不經本站計算。
<b>紅色可點</b>的車手／車隊已建生涯頁——「查 {year} → 點進冠軍 → 看整個生涯」就是這條路徑；灰色為尚未建頁的實體，後續補上。
退賽分類的每個數字皆可展開回指來源賽果檔。</p>
"""

    coll = {"@type": "CollectionPage", "@id": f"{canonical}#page", "url": canonical,
            "name": f"{year} 一級方程式賽季總覽", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{BASE}/#website"}}
    jsonld = rc.graph_ld(
        [rc.org_node(), rc.website_node(), coll,
         rc.breadcrumb_node([("首頁", f"{BASE}/"), ("賽季", f"{BASE}/seasons/"),
                             (f"{year} 賽季", canonical)])]
        + _race_event_nodes(year, sched, canonical))
    desc = (f"{year} 一級方程式賽季總覽：車手與車隊積分榜、冠軍逐站名次走勢、"
            f"對第二名分差（{gap} 分）與全季退賽原因分布，每個數字可回溯官方來源。")
    html = rc.page_shell(f"{year} 一級方程式賽季總覽", desc, canonical, jsonld, body,
                         active="", extra_css=p0.ENTITY_CSS + SEASON_CSS)
    out = PUB / "seasons" / str(year)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ /seasons/{year}/　冠軍 {champ_en} {champ_pts}分（領先 {gap}）· {len(cats)} 類退賽")
    return canonical


# ---------- 賽季頁專屬 CSS（走 page_shell 的 extra_css，不進 SHARED_CSS_TEXT） ----------
# 與 phase0 ENTITY_CSS 併用；只新增索引/敘事/退賽橫條圖需要的樣式，零圖檔零 JS。
SEASON_CSS = """
.dim{color:var(--faint)}
.ip{color:var(--accent);font-weight:700;font-size:12.5px}
.narrative{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:8px;padding:14px 18px;margin:10px 0}
.narrative p{font-size:14.5px;color:var(--fg-soft);line-height:1.9;margin:0 0 6px}
.narrative p:last-child{margin-bottom:0}
.rt-chart{display:flex;flex-direction:column;gap:6px;margin:10px 0}
details.rt{background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden}
details.rt>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:12px;padding:9px 14px}
details.rt>summary::-webkit-details-marker{display:none}
details.rt>summary::before{content:'▸';color:var(--dim);font-size:11px;flex:none;transition:transform .15s}
details.rt[open]>summary::before{transform:rotate(90deg)}
.rt-label{flex:none;width:150px;font-size:13px;color:var(--fg);font-weight:600}
.rt-en{color:var(--faint);font-size:11px;font-weight:500}
.rt-bar{flex:1;height:14px;background:var(--surface-2);border-radius:7px;overflow:hidden;min-width:60px}
.rt-fill{display:block;height:100%;background:var(--accent);border-radius:7px}
.rt-n{flex:none;width:34px;text-align:right;color:var(--accent);font-weight:800;font-size:14px;font-variant-numeric:tabular-nums}
.rt-detail{margin:2px 14px 12px;max-height:260px}
.rt-status{font-family:'Chakra Petch',monospace;color:var(--dnf);font-size:12px}
@media(max-width:640px){.rt-label{width:104px;font-size:12px}.rt-en{display:block}}
"""


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="產出 /seasons/ 索引與單一賽季頁（M3）。")
    ap.add_argument("--season", type=int, default=2002, help="要建的單一賽季頁年份（預設 2002）")
    ap.add_argument("--index-only", action="store_true", help="只重建 /seasons/ 索引")
    ap.add_argument("--publish", action="store_true",
                    help="公開時才加：寫 data/sitemap-parts/seasons.txt（預設不寫，頁面未公開前不進 sitemap）")
    ap.add_argument("--no-sitemap", action="store_true", help="顯式關閉 sitemap part（與預設同義，供 pipeline 明示）")
    args = ap.parse_args()

    print("賽季頁（M3）：")
    urls = [render_index()]
    if not args.index_only:
        urls.append(render_season(args.season))

    if args.publish and not args.no_sitemap:
        rc.write_sitemap_part("seasons", urls)
    else:
        print("  ⏸  未寫 sitemap part（M3 預設）：頁面未公開前不讓 URL 進 sitemap；"
              "公開時改用 --publish。")
    print(f"共 {len(urls)} 頁：\n  " + "\n  ".join(urls))


if __name__ == "__main__":
    main()
