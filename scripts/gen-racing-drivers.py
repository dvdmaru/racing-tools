#!/usr/bin/env python3
"""gen-racing-drivers.py — 百科線 M5：/drivers/（35 人索引）＋ /drivers/<slug>/（35 位歷代車手冠軍頁）。

頁面歸屬權：/drivers/** 全歸本生成器（phase0 的車手頁生成已移除，比照 M3 對 season 頁的清理）；
phase0 只留 /constructors/**。視覺元件（stat 卡、生涯時間軸、中英對照 hero、「怎麼算的」展開、
ENTITY_CSS）沿用 phase0 元件庫——importlib 載入共用，不重寫。統計一律走 f1stats 的 **DB 路徑**
（data/f1/db.sqlite 的 results / driver_standings），value==len(detail)。

★ 前置三 gate（產頁前，任一不綠 exit 1 且零產出）：
  ① check-f1-invariants.py 通過（失敗三元組集合＝宣告例外集合）
  ② crosscheck-wikipedia.py --gate-only（每個 diff 有 fingerprint 吻合的具名裁決）
  ③ golden 全綠（tests/golden_driver_stats.json 逐欄凍結值；M7 起改「as_of 迴歸」——
    比對重算到每位車手 as_of 時點的統計 vs 凍結值，活躍車手 as_of={2026,10}，新賽果不動 gate。
    換季/定期由 Charlie 重核准後手動推進 as_of＋更新凍結值，流程見 golden _meta.as_of_policy）

★ 發布欄位（只此、不可多，計畫 §4）：世界冠軍（含年份）、分站冠軍、頒獎台、參賽場次。
  §4.6 紅線：桿位／最快圈／生涯積分**不發**——標「後續補」。

用法：
  python3 scripts/gen-racing-drivers.py            # 產 /drivers/ 索引＋35 人頁（不寫 sitemap）
  python3 scripts/gen-racing-drivers.py --publish  # 公開時才加：寫 data/sitemap-parts/drivers.txt
  python3 scripts/gen-racing-drivers.py --no-sitemap
"""
import argparse
import html as html_lib
import importlib.util
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rc = _load("racinglib", "racinglib.py")
fs = _load("f1stats", "f1stats.py")
p0 = _load("gen_racing_entities_phase0", "gen-racing-entities-phase0.py")
gs = _load("gen_racing_seasons", "gen-racing-seasons.py")

BASE = rc.BASE
PUB = ROOT / "public-racing"
esc = html_lib.escape

FIRST_YEAR, LAST_YEAR = gs.FIRST_YEAR, gs.LAST_YEAR
# 哪些季有分站頁（明細列可深連分站頁）——單一來源＝config/encyclopedia.json 的 round_years
# （與 seasons 管線 --rounds-for 同源）；其餘季明細連季總覽。
ROUND_YEARS = set(rc.ROUND_YEARS)

REPORT = ROOT / "data" / "f1" / "crosscheck-report.json"
VERDICTS = ROOT / "config" / "f1-crosscheck-verdicts.json"
GOLDEN = ROOT / "tests" / "golden_driver_stats.json"
DB = ROOT / "data" / "f1" / "db.sqlite"

# 35 人名單的 canonical 來源＝crosscheck-report 的 coverage.expected_champion_ids（非硬編）。
CHAMPION_IDS = json.loads(REPORT.read_text(encoding="utf-8"))["coverage"]["expected_champion_ids"]

# 已核准的全名譯名：4 位 seed（phase0 已上線＝PR merge 核准過）。其餘走 driver-zh.json 的已核准
# 姓氏譯名（2026-07-19 定版）；兩者皆無 → 誠實 fallback（中文欄位整個不出現，只留原文，頁尾註明）。
SEED_ZH = {k: v for k, v in p0.ZH.items() if k in ("michael_schumacher", "hamilton",
                                                    "senna", "max_verstappen")}


def resolve_zh(did):
    """approved-only 譯名解析：seed 全名 → driver-zh 姓氏 → None（誠實 fallback）。不自譯。"""
    if did in SEED_ZH:
        return SEED_ZH[did]
    if did in rc.DRIVER_ZH:
        return rc.DRIVER_ZH[did]
    return None


# ---------- 前置三 gate ----------

def gate_invariants(db=None, exceptions=None):
    argv = [sys.executable, str(SCRIPTS / "check-f1-invariants.py")]
    if db:
        argv += ["--db", str(db)]
    if exceptions:
        argv += ["--exceptions", str(exceptions)]
    return subprocess.run(argv).returncode == 0


def gate_verdicts(db=None, report=None, verdicts=None):
    argv = [sys.executable, str(SCRIPTS / "crosscheck-wikipedia.py"), "--gate-only",
            "--db", str(db or DB), "--out", str(report or REPORT),
            "--verdicts", str(verdicts or VERDICTS)]
    return subprocess.run(argv).returncode == 0


def _computed_row(did, con, as_of=None):
    car = fs.driver_career_db(did, con, as_of=as_of)
    champ = fs.driver_championships_db(did, con, as_of=as_of)
    return {
        "championships": champ["value"],
        "championship_years": [d["season"] for d in champ["detail"]],
        "wins": car["wins"]["value"],
        "podiums": car["podiums"]["value"],
        "entries": car["entries"]["value"],
    }


def gate_golden(golden_path=None, con=None):
    """as_of 迴歸 gate：比對「重算到每位車手 as_of 時點」的統計 vs golden 凍結值（非全量現值）。

    這樣新賽果讓活躍車手的全量 wins/entries 變動時，gate 仍綠（as_of 截斷把新資料擋在時點外）；
    唯有篡改 as_of 時點<=的歷史資料，或凍結值被動過，才紅。任一 diff → False（需人工重新
    核准才更新 golden＋推進 as_of）。缺 as_of 的車手回退為全量比對（相容舊 golden）。"""
    golden = json.loads((golden_path or GOLDEN).read_text(encoding="utf-8"))["drivers"]
    own = con is None
    con = con or fs.connect_db()
    try:
        diffs = []
        gset, cset = set(golden), set(CHAMPION_IDS)
        if gset != cset:
            print(f"🔴 golden 名單與 35 人冠軍名單不符：多 {sorted(gset - cset)}　缺 {sorted(cset - gset)}")
            return False
        for did in CHAMPION_IDS:
            want = golden[did]
            got = _computed_row(did, con, as_of=want.get("as_of"))
            for f in ("championships", "championship_years", "wins", "podiums", "entries"):
                if want.get(f) != got.get(f):
                    diffs.append((did, f, want.get(f), got.get(f)))
        if diffs:
            print(f"🔴 golden gate FAIL：{len(diffs)} 欄與凍結值不符（需人工重新核准才更新 golden）：")
            for did, f, w, g in diffs[:20]:
                print(f"    {did} {f}: golden={w} 現值={g}")
            return False
    finally:
        if own:
            con.close()
    return True


def run_gates(db=None, exceptions=None, report=None, verdicts=None, golden_path=None):
    print("=" * 70)
    print("前置三 gate（任一不綠 → 零產出）")
    print("=" * 70)
    print("① 不變量（check-f1-invariants.py）")
    if not gate_invariants(db, exceptions):
        print("🔴 gate ① 不變量未通過 → 中止，不產任何頁。")
        return False
    print("② 維基裁決（crosscheck-wikipedia.py --gate-only）")
    if not gate_verdicts(db, report, verdicts):
        print("🔴 gate ② 維基裁決未通過 → 中止，不產任何頁。")
        return False
    print("③ golden（tests/golden_driver_stats.json）")
    if not gate_golden(golden_path):
        print("🔴 gate ③ golden 未通過 → 中止，不產任何頁。")
        return False
    print("✅ 三 gate 全綠，開始產頁。")
    return True


# ---------- 深連結 gate（無死連結） ----------

_round_cache = {}
_subpage_cache = {}


def _round_paths(year):
    """該季分站頁集合——只在 ROUND_YEARS（管線實際生成分站頁的季）才有，其餘回空集。"""
    if year not in ROUND_YEARS:
        return set()
    if year not in _round_cache:
        _round_cache[year] = gs.round_page_paths(year)
    return _round_cache[year]


def _season_subpage_dids(year):
    """該季有子頁的車手集合（＝seasons 生成器的 season_subpage_entities；權威、非重寫規則）。"""
    if year not in _subpage_cache:
        _subpage_cache[year] = set(gs.season_subpage_entities(year)[0])
    return _subpage_cache[year]


def _detail_href(season, rnd):
    """明細列深連結：該站有分站頁 → 分站頁；否則 → 季總覽（全 77 季皆有）；季在宇宙外 → 不連。"""
    if season is None:
        return None
    if rnd is not None and f"seasons/{season}/rounds/{rnd}" in _round_paths(season):
        return f"/seasons/{season}/rounds/{rnd}/"
    if FIRST_YEAR <= season <= LAST_YEAR:
        return f"/seasons/{season}/"
    return None


def _season_href(did, slug):
    """時間軸年格深連結：seed 車手該季有子頁 → 子頁；否則 → 季總覽；季在宇宙外 → 不可點。"""
    def href(y):
        if not (FIRST_YEAR <= y <= LAST_YEAR):
            return None
        if did in _season_subpage_dids(y):
            return f"/seasons/{y}/drivers/{slug}/"
        return f"/seasons/{y}/"
    return href


# ---------- 視覺元件（沿用 phase0 CSS/類名；明細列加深連結 gate） ----------

def _detail_row(d):
    """一筆明細＝一句人話，連回該站分站頁或季總覽（死連結 gate）。raw 檔路徑收進 tooltip。"""
    src = esc(d.get("source", ""))
    yr = d.get("season", "")
    href = _detail_href(d.get("season"), d.get("round"))
    if "race" in d:  # 逐場型（勝場/頒獎台/出賽）
        pos = str(d.get("pos", ""))
        postxt = f"（第 {pos} 名）" if pos.isdigit() and pos != "1" else ""
        inner = f'<span class="mono">{yr}</span> {esc(d.get("race", ""))}{postxt}'
    else:  # 逐季型（世界冠軍）
        extra = []
        if d.get("points"):
            extra.append(f'{d["points"]} 分')
        if d.get("wins_that_year"):
            extra.append(f'當年 {d["wins_that_year"]} 勝')
        tail = f'<span class="sub">　{esc("、".join(extra))}</span>' if extra else ""
        inner = f'<span class="mono">{yr}</span> 世界冠軍{tail}'
    if href:
        inner = f'<a href="{href}">{inner}</a>'
    return f'<li title="來源檔：{src}">{inner}</li>'


def stat_card(label, stat, unit=""):
    """一張統計卡：大數字 + CSS-only 展開的『怎麼算的』（定義＋formula 中文＋coverage＋明細）。"""
    v = stat["value"]
    detail = stat.get("detail", [])
    rows = "".join(_detail_row(d) for d in detail[:80])
    more = f'<li class="more">…以下省略，共 {len(detail)} 筆</li>' if len(detail) > 80 else ""
    zh_def = p0.FORMULA_ZH.get(stat["formula"], stat["formula"])
    return f"""<div class="stat">
  <div class="stat-v mono">{v}<span class="unit">{unit}</span></div>
  <div class="stat-l">{label}</div>
  <details class="how">
    <summary>怎麼算的</summary>
    <div class="how-body">
      <p class="formula"><b>定義</b>　{esc(zh_def)}<span class="cov">資料涵蓋 {esc(stat["coverage"])}</span></p>
      <ol class="detail-list">{rows}{more}</ol>
      <p class="prov">數字＝上列明細的筆數，不另行維護。每筆連回該賽季／分站頁，並對應一份官方原始資料檔（滑鼠停留可見檔名）。</p>
    </div>
  </details>
</div>"""


# ---------- JSON-LD ----------

def person_ld(meta, zh, url):
    name_full = f'{meta.get("givenName", "")} {meta.get("familyName", "")}'.strip()
    node = {
        "@type": "Person", "name": zh or name_full,
        "jobTitle": "賽車手", "url": url,
        "sameAs": [meta["url"]] if meta.get("url") else [],
    }
    if zh and name_full and zh != name_full:
        node["alternateName"] = name_full
    if meta.get("nationality"):
        node["nationality"] = meta["nationality"]
    if meta.get("dateOfBirth"):
        node["birthDate"] = meta["dateOfBirth"]
    return node


# ---------- 效力車隊（drove_for 邊；只連已建頁的車隊，其餘灰 chip） ----------

def driver_constructors(did, con):
    seen = []
    for r in con.execute(
            "SELECT r.constructor_id AS cid, c.name AS name FROM results r "
            "LEFT JOIN constructors c ON c.constructor_id=r.constructor_id "
            "WHERE r.driver_id=? ORDER BY r.season, r.round, r.id", (did,)).fetchall():
        cid = r["cid"]
        if cid and cid not in [x[0] for x in seen]:
            seen.append((cid, r["name"] or cid))
    return seen


# ---------- 頁面寫出（沿用 page_shell + phase0 ENTITY_CSS，走本模組 PUB 供測試隔離） ----------

def write_page(path_parts, title, desc, jsonld, body):
    canonical = f"{BASE}/{'/'.join(path_parts)}/"
    html = rc.page_shell(title, desc, canonical, jsonld, body, active="", extra_css=p0.ENTITY_CSS)
    out = PUB
    for p in path_parts:
        out = out / p
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    return canonical


# ---------- 車手頁 ----------

def driver_summary(did, con):
    """索引/頁面共用的摘要數字（發布欄位）。"""
    meta = fs.driver_meta_db(did, con)
    career = fs.driver_career_db(did, con)
    champ = fs.driver_championships_db(did, con)
    return {
        "did": did, "slug": rc.driver_slug(did), "meta": meta,
        "zh": resolve_zh(did),
        "name_full": f'{meta.get("givenName", "")} {meta.get("familyName", "")}'.strip(),
        "career": career, "champ": champ,
        "champ_years": [d["season"] for d in champ["detail"]],
        "wins": career["wins"]["value"], "podiums": career["podiums"]["value"],
        "entries": career["entries"]["value"], "championships": champ["value"],
    }


def gen_driver(did, con):
    s = driver_summary(did, con)
    slug, meta, zh, name_full = s["slug"], s["meta"], s["zh"], s["name_full"]
    seasons = fs.driver_seasons_db(did, con)
    url = f"{BASE}/drivers/{slug}/"

    ident = [f"<span>國籍 {esc(meta.get('nationality', ''))}</span>" if meta.get("nationality") else ""]
    if meta.get("dateOfBirth"):
        ident.append(f'<span>生日 <span class="mono">{esc(meta["dateOfBirth"])}</span></span>')
    if seasons:
        ident.append(f'<span>參賽賽季 <span class="mono">{seasons[0]}–{seasons[-1]}</span></span>')

    hero = f"""<div class="ent-hero">
  <p class="ent-kicker">車手檔案 · Driver</p>
  <h1 class="ent-h1">{p0.pair(zh, name_full)}</h1>
  <div class="ident">
    {"".join(x for x in ident if x)}
  </div>
</div>"""

    cards = (
        stat_card("世界冠軍", s["champ"], unit=" 次") +
        stat_card("分站冠軍", s["career"]["wins"], unit=" 勝") +
        stat_card("頒獎台", s["career"]["podiums"], unit=" 次") +
        stat_card("參賽場次", s["career"]["entries"], unit=" 站") +
        # §4.6 紅線：三欄位不發，只標「後續補（定義與資料範圍見方法說明）」——不給任何數據形式的值。
        p0.unavailable_card("桿位", "後續補（定義與資料範圍見方法說明）") +
        p0.unavailable_card("最快圈", "後續補（定義與資料範圍見方法說明）") +
        p0.unavailable_card("生涯積分", "後續補（定義與資料範圍見方法說明）")
    )

    tl = p0.career_timeline(seasons, s["champ_years"], _season_href(did, slug))

    teams = driver_constructors(did, con)
    rel = "".join(p0.internal_link(f'constructors/{cid.replace("_", "-")}',
                                    esc(p0.ZH.get(cid) or rc.team_zh(name)))
                  for cid, name in teams)

    zh_note = ("" if zh else
               '<p class="note">此車手目前尚無定版繁中譯名，本頁暫以原文呈現（不自譯）；譯名補完見後續里程碑。</p>')

    body = f"""{hero}
<div class="stat-grid">{cards}</div>

<div class="sec-title">生涯時間軸</div>
<p class="note">跑過的賽季填色，<b>世界冠軍年加深紅並加粗</b>。{s["championships"]} 座冠軍：{esc('、'.join(map(str, s["champ_years"]))) or '—'}<br>
可點的年份會進入該賽季頁（{"該車手的賽季成績子頁" if did in gs.p0.DRIVERS else "該季總覽"}）。</p>
{tl}

<div class="sec-title">效力車隊</div>
<div class="rel">{rel or '<span class="rel-off">—</span>'}</div>
<p class="note">灰色車隊＝本階段尚未建頁，後續補上。</p>

<div class="sec-title">方法說明</div>
<p class="note">本頁只發布四個定義明確、可回溯到官方原始資料的欄位：世界冠軍、分站冠軍、頒獎台、參賽場次。
每個數字旁的「怎麼算的」可展開，逐筆列出來源賽季與賽站並連回對應頁。統計一律由明細筆數產生、不獨立維護。<br>
<b>桿位、最快圈、生涯積分暫不發布</b>：定義或資料範圍尚未定案（例如資料源的起跑位含罰退、最快圈欄位早年缺漏、生涯積分有兩種都成立的口徑），
寧缺勿濫，待定義確定後補上。{"" if zh else "　"}</p>
{zh_note}"""

    ld = rc.graph_ld([rc.org_node(), rc.website_node(),
                      rc.breadcrumb_node([("首頁", BASE + "/"), ("車手", BASE + "/drivers/"),
                                          (zh or name_full, url)]),
                      person_ld(meta, zh, url)])
    title = f"{zh or name_full}生涯數據"
    desc = f"{zh or name_full}的世界冠軍、分站冠軍、頒獎台與參賽場次，每個數字可回溯官方來源。"
    write_page(["drivers", slug], title, desc, ld, body)
    return s


# ---------- 索引頁 ----------

def _index_rows(con):
    rows = [driver_summary(did, con) for did in CHAMPION_IDS]
    # 決定性排序：冠軍多→勝場多→頒獎台多→出賽多→driverId（穩定 tiebreak）
    rows.sort(key=lambda s: (-s["championships"], -s["wins"], -s["podiums"],
                             -s["entries"], s["did"]))
    return rows


def render_index(con):
    rows = _index_rows(con)
    trs = []
    for i, s in enumerate(rows, 1):
        label = p0.pair(s["zh"], s["name_full"])
        trs.append(f"""<tr>
  <td class="mono rk">{i}</td>
  <td><a href="/drivers/{s['slug']}/">{label}</a></td>
  <td>{esc(s['meta'].get('nationality', ''))}</td>
  <td class="mono">{s['championships']}</td>
  <td class="mono">{s['wins']}</td>
  <td class="mono">{s['podiums']}</td>
  <td class="mono">{s['entries']}</td>
</tr>""")
    table = f"""<table class="std-tbl">
<thead><tr><th>#</th><th>車手</th><th>國籍</th><th>世界冠軍</th><th>分站冠軍</th><th>頒獎台</th><th>參賽場次</th></tr></thead>
<tbody>{"".join(trs)}</tbody>
</table>"""

    body = f"""<div class="ent-hero">
  <p class="ent-kicker">車手名錄 · Drivers</p>
  <h1 class="ent-h1">歷代世界冠軍<span class="zh-en">　World Champions</span></h1>
  <p class="ident"><span>共 <span class="mono">{len(rows)}</span> 位曾奪下車手世界冠軍的車手。每個數字皆可回溯官方原始資料。</span></p>
</div>
{table}
<p class="note">名單＝歷代車手世界冠軍（{FIRST_YEAR}–{LAST_YEAR}）。點車手名進入其生涯頁；每頁只發布定義明確、可回溯來源的欄位，
桿位／最快圈／生涯積分暫不發布（定義待定）。譯名採已核准來源，無定版譯名者暫以原文呈現，不自譯。</p>"""

    items = [{"@type": "ListItem", "position": i,
              "url": f"{BASE}/drivers/{s['slug']}/",
              "name": s["zh"] or s["name_full"]}
             for i, s in enumerate(rows, 1)]
    ld = rc.graph_ld([rc.org_node(), rc.website_node(),
                      rc.breadcrumb_node([("首頁", BASE + "/"), ("車手", BASE + "/drivers/")]),
                      {"@type": "ItemList", "name": "歷代車手世界冠軍",
                       "numberOfItems": len(items), "itemListElement": items}])
    return write_page(["drivers"], "歷代車手世界冠軍名錄",
                      f"一級方程式 {FIRST_YEAR}–{LAST_YEAR} 歷代車手世界冠軍名錄：世界冠軍、分站冠軍、頒獎台、參賽場次，每個數字可回溯官方來源。",
                      ld, body)


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="產出 /drivers/ 索引與 35 位車手頁（M5；前置三 gate）。")
    ap.add_argument("--publish", action="store_true",
                    help="公開時才加：寫 data/sitemap-parts/drivers.txt（預設不寫）")
    ap.add_argument("--no-sitemap", action="store_true", help="顯式關閉 sitemap part（與預設同義）")
    ap.add_argument("--skip-gates", action="store_true",
                    help=argparse.SUPPRESS)  # 僅供測試注入；正常管線一律跑三 gate
    args = ap.parse_args()

    if not args.skip_gates and not run_gates():
        return 1

    con = fs.connect_db()
    try:
        print("車手頁：")
        urls = [render_index(con)]
        for did in CHAMPION_IDS:
            s = gen_driver(did, con)
            urls.append(f"{BASE}/drivers/{s['slug']}/")
            print(f"  ✓ /drivers/{s['slug']}/　{s['championships']}冠 {s['wins']}勝 "
                  f"{s['podiums']}台 {s['entries']}站")
    finally:
        con.close()

    if args.publish and not args.no_sitemap:
        rc.write_sitemap_part("drivers", urls)
    else:
        print("  ⏸  未寫 sitemap part（預設）：頁面未公開前不讓 URL 進 sitemap；公開時改用 --publish。")
    print(f"共 {len(urls)} 頁。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
