#!/usr/bin/env python3
"""gen-racing-entities-phase0.py — Phase 0 實體頁探針（4 車手 + 4 車隊 + 2002 賽季頁）。

目的：讓 Charlie 先看到一個實體頁長什麼樣，再決定要不要投入 M0 地基與全量展開。
用 racinglib 的站台外殼（暗底/賽車紅/header/footer/非官方 disclaimer），
實體專屬視覺（生涯時間軸、賽季弧線、「怎麼算的」展開）暫放本檔，走通後再升進 racinglib。

★ 每個衍生數字都掛可展開的來源明細（計畫 §4.8）——寫不出定義的數字就上不了頁。
"""
import html as html_lib
import importlib.util
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_lib(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rc = _load_lib("racinglib", "racinglib.py")
fs = _load_lib("f1stats", "f1stats.py")

RAW = ROOT / "data" / "f1" / "raw"
PUB = ROOT / "public-racing"
BASE = rc.BASE
esc = html_lib.escape

# Phase 0 名單
DRIVERS = ["michael_schumacher", "hamilton", "senna", "max_verstappen"]
CONSTRUCTORS = ["ferrari", "mclaren", "mercedes", "red_bull"]

# Phase 0 譯名（歷史實體全無譯名，站規要中英對照 → 這批人工填，未填者誠實留原文）
ZH = {
    "michael_schumacher": "麥可・舒馬克", "hamilton": "路易斯・韓密爾頓",
    "senna": "艾爾頓・冼拿", "max_verstappen": "麥克斯・維斯塔潘",
    "ferrari": "法拉利", "mclaren": "麥拉倫", "mercedes": "賓士", "red_bull": "紅牛",
}

# 賽車紅明度階（做賽季弧線用；刻意不對應任何車隊塗裝）
INK = {"red": "#d63a2f", "amber": "#e8b04b", "muted": "#868d97"}

# formula id → 給讀者看的中文定義（頁面永不直接印 formula id / raw 檔路徑）
FORMULA_ZH = {
    "count_seasons_driver_standing_eq_1":
        "每個賽季結束時的官方車手積分榜，此車手名列第 1 的賽季數",
    "count_seasons_constructor_standing_eq_1":
        "每個賽季結束時的官方車隊積分榜，此車隊名列第 1 的賽季數",
    "results_position_text_eq_1":
        "生涯每一場正賽的官方賽果中，最終名次為第 1 的場次數",
    "results_position_text_in_123":
        "生涯每一場正賽的官方賽果中，最終名次為前三的場次數",
    "results_distinct_races":
        "官方賽果中有此車手紀錄的不重複場次數（同場共同駕駛計一場；資料源未收錄未通過排位的報名）",
}

# Phase 0 已建頁的實體（站內連結只指向存在的頁；沒建頁的實體顯示為不可點的灰 chip）
# slug 走 M0 append-only 註冊表（data/f1/slugs.json）——這 8 個正是該表的 seed。
HAS_PAGE = ({f"drivers/{rc.driver_slug(d)}" for d in DRIVERS}
            | {f"constructors/{rc.constructor_slug(c)}" for c in CONSTRUCTORS}
            | {"seasons/2002"})


def internal_link(path, label_html):
    """站內連結一律根相對路徑（本機預覽與正式站都通），且只連已存在的頁。"""
    if path in HAS_PAGE:
        return f'<a href="/{path}/">{label_html}</a>'
    return f'<span class="rel-off">{label_html}</span>'


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


# ---------- 賽季子頁 deep-link（v3：選擇即 URL） ----------
# 實體頁的時間軸連到「該實體在該賽季的視角子頁」（/seasons/<y>/drivers|teams/<slug>/），
# 而非泛指賽季總覽。子頁的實際生成方 = gen-racing-seasons.py（owner=seasons）；此處只在
# 「該季有總覽頁（seasons/<y> ∈ HAS_PAGE）且該實體該季有參賽」時，才把年格連向子頁——
# 兩邊用同一條規則（總覽頁存在 ＋ 該季參賽），因此不會連到未生成的子頁（無死連結）。

def _overview_years():
    return sorted(int(m.group(1)) for p in HAS_PAGE
                  for m in [re.fullmatch(r"seasons/(\d+)", p)] if m)


def _driver_in_season(did, year):
    p = RAW / "standings" / f"driver-{year}.json"
    if not p.exists():
        return False
    return any(r.get("Driver", {}).get("driverId") == did
               for r in _load(p).get("DriverStandings", []))


def _constructor_in_season(cid, year):
    p = RAW / "standings" / f"constructor-{year}.json"
    if not p.exists():
        return False
    return any(r.get("Constructor", {}).get("constructorId") == cid
               for r in _load(p).get("ConstructorStandings", []))


def _season_href(kind, entity_id, slug):
    """回一個 href(year) 函式：該季無總覽頁 → None（年格不可點）；
    有總覽頁且該實體該季參賽 → 子頁；有總覽頁但沒參賽 → 泛指總覽頁。"""
    years = set(_overview_years())
    in_season = _driver_in_season if kind == "drivers" else _constructor_in_season

    def href(y):
        if y not in years:
            return None
        if in_season(entity_id, y):
            return f"/seasons/{y}/{kind}/{slug}/"
        return f"/seasons/{y}/"
    return href


def pair(zh, en):
    """中文＋原文並列（站規）。zh 缺就誠實只留原文，不假裝。"""
    if not zh:
        return f'<span class="en-only">{esc(en)}</span>'
    return f'{esc(zh)}<span class="zh-en">　{esc(en)}</span>'


# ---------- 視覺元件 ----------

def _detail_row(d):
    """明細一筆＝一句人話；raw 檔路徑收進 hover tooltip，不直接印在頁面上。"""
    src = esc(d.get("source", ""))
    yr = d.get("season", "")
    if "race" in d:  # 逐場型（勝場/頒獎台/出賽）
        pos = str(d.get("pos", ""))
        postxt = f"（第 {pos} 名）" if pos.isdigit() and pos != "1" else ""
        return (f'<li title="來源檔：{src}"><span class="mono">{yr}</span> '
                f'{esc(d.get("race", ""))}{postxt}</li>')
    # 逐季型（世界冠軍）
    extra = []
    if d.get("points"):
        extra.append(f'{d["points"]} 分')
    if d.get("wins_that_year"):
        extra.append(f'當年 {d["wins_that_year"]} 勝')
    tail = f'<span class="sub">　{esc("、".join(extra))}</span>' if extra else ""
    return (f'<li title="來源檔：{src}"><span class="mono">{yr}</span> '
            f'世界冠軍{tail}</li>')


def stat_card(label, stat, unit="", note=""):
    """一張統計卡：大數字 + CSS-only 展開的『怎麼算的』。"""
    v = stat["value"]
    detail = stat.get("detail", [])
    rows = "".join(_detail_row(d) for d in detail[:80])
    more = f'<li class="more">…以下省略，共 {len(detail)} 筆</li>' if len(detail) > 80 else ""
    zh_def = FORMULA_ZH.get(stat["formula"], stat["formula"])
    return f"""<div class="stat">
  <div class="stat-v mono">{v}<span class="unit">{unit}</span></div>
  <div class="stat-l">{label}</div>
  <details class="how">
    <summary>怎麼算的</summary>
    <div class="how-body">
      <p class="formula"><b>定義</b>　{esc(zh_def)}<span class="cov">資料涵蓋 {esc(stat["coverage"])}</span></p>
      <ol class="detail-list">{rows}{more}</ol>
      <p class="prov">數字＝上列明細的筆數，不另行維護。每筆對應一份官方原始資料檔（滑鼠停留可見檔名）。</p>
    </div>
  </details>
</div>"""


def unavailable_card(label, why):
    return f"""<div class="stat na">
  <div class="stat-v mono">—</div>
  <div class="stat-l">{label}</div>
  <p class="na-why">{esc(why)}</p>
</div>"""


def career_timeline(seasons, champ_years, season_href=None):
    """參賽賽季時間軸：跑過的年填色，冠軍年加粗標記。零圖檔。
    season_href(year)→href/None 決定年格連往哪（v3：連該實體的賽季子頁）；未給則沿用舊行為
    （有總覽頁的年份連泛指總覽頁）。回 None 的年格不可點。"""
    if not seasons:
        return ""
    lo, hi = seasons[0], seasons[-1]
    champ = set(champ_years)
    played = set(seasons)
    cells = []
    for y in range(lo, hi + 1):
        cls = "yr"
        if y in champ:
            cls += " champ"
        elif y in played:
            cls += " on"
        else:
            cls += " off"
        label = f"{y}" if (y in champ or y == lo or y == hi) else ""
        inner = f"<span>{label}</span>"
        if season_href is not None:
            href = season_href(y)
        else:
            href = f"/seasons/{y}/" if f"seasons/{y}" in HAS_PAGE else None
        if href:
            cells.append(f'<a class="{cls} lk" href="{href}" '
                         f'title="{y} 賽季頁">{inner}</a>')
        else:
            cells.append(f'<div class="{cls}" title="{y}">{inner}</div>')
    return f'<div class="timeline">{"".join(cells)}</div>'


# ---------- Person / Constructor JSON-LD ----------

def person_ld(driver, url, wiki):
    return {
        "@type": "Person", "name": ZH.get(driver["driverId"]) or f'{driver.get("givenName","")} {driver.get("familyName","")}'.strip(),
        "alternateName": f'{driver.get("givenName","")} {driver.get("familyName","")}'.strip(),
        "jobTitle": "賽車手", "nationality": driver.get("nationality", ""),
        "birthDate": driver.get("dateOfBirth", ""), "url": url,
        "sameAs": [driver.get("url")] if driver.get("url") else [],
    }


# ---------- CSS（Phase 0 專屬，走 page_shell 的 extra_css） ----------

ENTITY_CSS = """
.ent-hero{padding:8px 0 20px;border-bottom:1px solid var(--line-2);margin-bottom:22px}
.ent-kicker{font-family:'Chakra Petch',monospace;font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent);margin:0 0 8px;font-weight:600}
.ent-h1{font-size:clamp(26px,5vw,40px);line-height:1.05;margin:0 0 10px;font-weight:800;color:var(--fg)}
.ent-h1 .zh-en{font-size:.55em;color:var(--dim);font-weight:600;margin-left:8px}
.en-only{color:var(--dim)}
.ident{display:flex;flex-wrap:wrap;gap:8px 22px;color:var(--fg-soft);font-size:14px;margin:6px 0 0}
.ident .mono{font-variant-numeric:tabular-nums;font-family:'Chakra Petch',monospace}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px;margin:20px 0}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px 16px 10px;border-top:3px solid var(--accent);box-shadow:0 1px 3px var(--sheet-shadow)}
.stat.na{border-top-color:var(--line-2);opacity:.7;box-shadow:none}
.stat-v{font-size:40px;font-weight:800;line-height:1;font-variant-numeric:tabular-nums;color:var(--fg);font-family:'Chakra Petch',sans-serif}
.stat.na .stat-v{color:var(--faint)}
.stat-v .unit{font-size:15px;font-weight:600;color:var(--fg-soft);margin-left:4px}
.stat-l{font-size:13px;color:var(--fg-soft);margin-top:6px;font-weight:600}
.na-why{font-size:12px;color:var(--dim);margin:8px 0 4px;line-height:1.5}
.how{margin-top:10px}
.how summary{cursor:pointer;font-size:12px;color:var(--accent);font-family:'Chakra Petch',monospace;letter-spacing:.03em}
.how-body{margin-top:8px;font-size:12.5px}
.formula{color:var(--fg-soft);margin:0 0 6px;line-height:1.6}
.formula .cov{display:block;font-size:11px;color:var(--faint);margin-top:2px}
.detail-list{margin:0;padding-left:18px;max-height:220px;overflow:auto}
.detail-list li{margin:3px 0;color:var(--fg-soft);cursor:help}
.detail-list .sub{font-size:11px;color:var(--faint)}
.detail-list .more{list-style:none;color:var(--faint)}
.prov{font-size:11px;color:var(--faint);margin:8px 0 2px;line-height:1.5}
.sec-title{font-size:18px;font-weight:750;margin:30px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--accent-line);color:var(--fg)}
.timeline{display:flex;flex-wrap:wrap;gap:3px;margin:8px 0}
.yr{width:36px;height:36px;border-radius:5px;display:flex;align-items:center;justify-content:center;font-size:9px;font-family:'Chakra Petch',monospace;color:var(--dim)}
.yr.off{background:var(--surface-2)}
.yr.on{background:var(--accent-soft);color:var(--accent-bright)}
.yr.champ{background:var(--accent);color:var(--accent-ink);font-weight:800;box-shadow:0 0 0 2px var(--accent-glow)}
a.yr.lk{text-decoration:none;cursor:pointer}
a.yr.lk:hover{outline:2px solid var(--accent);outline-offset:1px;transform:translateY(-1px)}
.arc{width:100%;height:auto;background:var(--surface);border:1px solid var(--line);border-radius:10px;margin:8px 0;padding:4px}
.arc-line{fill:none;stroke:var(--accent);stroke-width:2.5}
.arc circle{fill:var(--accent)}
.arc .grid{stroke:var(--line-2);stroke-width:1;stroke-dasharray:3 3}
.arc .axis{fill:var(--faint);font-size:9px;font-family:monospace}
.rel{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.rel a{background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:6px 14px;font-size:13px;text-decoration:none;color:var(--fg)}
.rel a:hover{border-color:var(--accent);color:var(--accent)}
.rel .rel-off{background:var(--surface-2);border:1px dashed var(--line);border-radius:20px;padding:6px 14px;font-size:13px;color:var(--faint)}
.std-tbl a{color:var(--accent);text-decoration:none;font-weight:600}
.std-tbl a:hover{text-decoration:underline}
.std-tbl .rel-off{color:inherit}
.ident a{color:var(--accent);text-decoration:none}
.ident .rel-off{color:inherit}
.note{font-size:12.5px;color:var(--fg-soft);background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:8px;padding:12px 16px;margin:14px 0;max-width:none}
.note b{color:var(--fg)}
.std-tbl{width:100%;border-collapse:collapse;font-size:14px}
.std-tbl th,.std-tbl td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left}
.std-tbl thead th{font-family:'Chakra Petch',monospace;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--fg-soft);background:var(--surface-2)}
.std-tbl tbody tr:hover td{background:var(--accent-soft)}
.std-tbl .mono{font-variant-numeric:tabular-nums;font-family:'Chakra Petch',monospace}
"""


def write_page(path_parts, title, desc, jsonld, body):
    canonical = f"{BASE}/{'/'.join(path_parts)}/"
    html = rc.page_shell(title, desc, canonical, jsonld, body,
                         active="", extra_css=ENTITY_CSS)
    out = PUB
    for p in path_parts:
        out = out / p
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    return canonical


# ---------- 車手頁 ----------

def gen_driver(did):
    drv = _load(RAW / "drivers" / f"{did}.json")
    career = fs.driver_career(did)
    champ = fs.driver_championships(did)
    seasons = fs.driver_seasons(did)
    champ_years = [d["season"] for d in champ["detail"]]
    zh = ZH.get(did)
    name_full = f'{drv.get("givenName","")} {drv.get("familyName","")}'.strip()

    # 生涯車隊（drove_for 邊）
    races = _load(RAW / "drivers" / f"{did}-results.json")["Races"]
    teams = []
    for r in races:
        c = (r.get("Results") or [{}])[0].get("Constructor", {})
        cid = c.get("constructorId")
        if cid and cid not in [t[0] for t in teams]:
            teams.append((cid, c.get("name", cid)))

    slug = rc.driver_slug(did)
    url = f"{BASE}/drivers/{slug}/"

    hero = f"""<div class="ent-hero">
  <p class="ent-kicker">車手檔案 · Driver</p>
  <h1 class="ent-h1">{pair(zh, name_full)}</h1>
  <div class="ident">
    <span>國籍 {esc(drv.get('nationality',''))}</span>
    <span>生日 <span class="mono">{esc(drv.get('dateOfBirth',''))}</span></span>
    <span>參賽賽季 <span class="mono">{seasons[0]}–{seasons[-1]}</span></span>
  </div>
</div>"""

    cards = (
        stat_card("世界冠軍", champ, unit=" 次") +
        stat_card("分站冠軍", career["wins"], unit=" 勝") +
        stat_card("頒獎台", career["podiums"], unit=" 次") +
        stat_card("出賽", career["entries"], unit=" 站") +
        unavailable_card("桿位", "資料源的 grid 是實際起跑位（含罰退）不是排位第一，2003 前排位資料不可靠 → 第一階段不發") +
        unavailable_card("最快圈", "FastestLap 欄位 2004 起才有 → 本站算不出完整生涯值") +
        unavailable_card("生涯積分", "有兩種都對的定義（各季最終榜 vs 逐場加總），差異在 1950–90 → 待定義後補")
    )

    tl = career_timeline(seasons, champ_years, _season_href("drivers", did, slug))
    rel = "".join(internal_link(f'constructors/{cid.replace("_", "-")}',
                                esc(ZH.get(cid) or name))
                  for cid, name in teams)

    body = f"""{hero}
<div class="stat-grid">{cards}</div>

<div class="sec-title">生涯時間軸</div>
<p class="note">跑過的賽季填色，<b>世界冠軍年加深紅並加粗</b>。{len(champ_years)} 座冠軍：{esc('、'.join(map(str,champ_years))) or '—'}</p>
{tl}

<div class="sec-title">效力車隊</div>
<div class="rel">{rel}</div>
<p class="note">灰色車隊＝本階段尚未建頁，後續補上。時間軸中<b>可點的年份</b>會進入該車手<b>在該賽季</b>的成績頁（本階段先做 2002）。</p>

<p class="note">本頁每個數字旁的「怎麼算的」可展開，逐筆列出來源賽季與賽站。
統計一律由明細筆數產生，不獨立維護——這是為了防止「總計與明細各自維護」造成的錯。</p>
"""
    ld = rc.graph_ld([rc.org_node(), rc.website_node(),
                      rc.breadcrumb_node([("首頁", BASE + "/"), ("車手", url)]),
                      person_ld(drv, url, drv.get("url"))])
    write_page(["drivers", slug], f"{zh or name_full}生涯數據",
               f"{zh or name_full}的世界冠軍、分站冠軍、頒獎台與生涯時間軸，每個數字可回溯來源。",
               ld, body)
    print(f"  ✓ /drivers/{slug}/　{champ['value']}冠 {career['wins']['value']}勝 {career['podiums']['value']}台")
    return {"slug": slug, "champ": champ["value"], "wins": career["wins"]["value"],
            "podiums": career["podiums"]["value"], "zh": zh, "en": name_full}


# ---------- 車隊頁 ----------

def gen_constructor(cid):
    champ = fs.constructor_championships(cid)
    champ_years = [d["season"] for d in champ["detail"]]
    zh = ZH.get(cid)
    slug = rc.constructor_slug(cid)
    url = f"{BASE}/constructors/{slug}/"
    # 名稱從任一季榜取
    name = cid
    for p in sorted((RAW / "standings").glob("constructor-*.json")):
        for row in _load(p).get("ConstructorStandings", []):
            c = row.get("Constructor", {})
            if c.get("constructorId") == cid:
                name = c.get("name", cid)
                break
        if name != cid:
            break

    yrs = sorted(champ_years)
    tl = (career_timeline(list(range(yrs[0], yrs[-1] + 1)), champ_years,
                          _season_href("teams", cid, slug)) if yrs else "")

    hero = f"""<div class="ent-hero">
  <p class="ent-kicker">車隊檔案 · Constructor</p>
  <h1 class="ent-h1">{pair(zh, name)}</h1>
</div>"""
    body = f"""{hero}
<div class="stat-grid">{stat_card("車隊世界冠軍", champ, unit=" 次")}
  {unavailable_card("分站冠軍", "第一階段先做冠軍數，車隊分站勝場待逐場聚合後補")}
  {unavailable_card("成立年份 / 引擎供應", "資料源只給名稱與國籍，這些要另找來源（維基/官方）")}</div>
<div class="sec-title">奪冠賽季</div>
<p class="note">{len(champ_years)} 座車隊冠軍：{esc('、'.join(map(str,champ_years))) or '—'}</p>
{tl}
"""
    ld = rc.graph_ld([rc.org_node(), rc.website_node(),
                      rc.breadcrumb_node([("首頁", BASE + "/"), ("車隊", url)]),
                      {"@type": "SportsTeam", "name": zh or name, "alternateName": name, "url": url}])
    write_page(["constructors", slug], f"{zh or name}車隊冠軍史",
               f"{zh or name}的車隊世界冠軍與奪冠賽季。", ld, body)
    print(f"  ✓ /constructors/{slug}/　{champ['value']} 座車隊冠軍")


# 賽季頁（/seasons/**）v3 起一律歸 gen-racing-seasons.py 所有（總覽頁＋車手/車隊子頁）；
# phase0 只管實體頁（/drivers/、/constructors/）。原 gen_season() 已移除，避免兩支都寫
# /seasons/<year>/index.html（後寫者贏）的歸屬權衝突。


def main():
    print("車手頁：")
    for d in DRIVERS:
        gen_driver(d)
    print("車隊頁：")
    for c in CONSTRUCTORS:
        gen_constructor(c)


if __name__ == "__main__":
    main()
