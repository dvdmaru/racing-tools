#!/usr/bin/env python3
"""/constructors/ 2026 全 11 隊索引與車隊頁的唯一 owner。

發布欄位只有車隊世界冠軍、分站勝場、頒獎台、參賽場次。桿位、最快圈、生涯積分不發。
產頁前依序執行 invariants、Wikipedia verdicts、golden as_of 三道 gate；任一失敗即零頁生成。
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
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rc = _load("racinglib_constructor_gen", "racinglib.py")
fs = _load("f1stats_constructor_gen", "f1stats.py")
p0 = _load("phase0_constructor_components", "gen-racing-entities-phase0.py")
gs = _load("seasons_constructor_links", "gen-racing-seasons.py")
# 與車手／分站頁共用同一份 interlink 實例，正反向判定表不分岔。
il = gs.il

BASE = rc.BASE
PUB = ROOT / "public-racing"
DB = ROOT / "data" / "f1" / "db.sqlite"
REPORT = ROOT / "data" / "f1" / "constructor-crosscheck-report.json"
VERDICTS = ROOT / "config" / "f1-constructor-verdicts.json"
GOLDEN = ROOT / "tests" / "golden_constructor_stats.json"
AS_OF = {"season": 2026, "round": 11}
esc = html_lib.escape

_COVERAGE = json.loads(REPORT.read_text(encoding="utf-8"))["coverage"]
CONSTRUCTOR_IDS = _COVERAGE["expected_constructor_ids"]
CHAMPION_IDS = [cid for cid in CONSTRUCTOR_IDS if
                json.loads(GOLDEN.read_text(encoding="utf-8"))["constructors"][cid]["championships_count"]]


# ---------- 前置三 gate ----------

def db_roster(con):
    return [r[0] for r in con.execute(
        "SELECT DISTINCT constructor_id FROM results WHERE season=2026 ORDER BY constructor_id")]


def roster_exact(con, expected=None):
    """canonical report roster 與 DB 2026 roster 雙向全等；多一隊／少一隊都失敗。"""
    expected = list(CONSTRUCTOR_IDS if expected is None else expected)
    actual = db_roster(con)
    if actual != expected or len(expected) != len(set(expected)):
        print(f"🔴 constructor roster 非雙向全等：多 {sorted(set(actual)-set(expected))}　"
              f"缺 {sorted(set(expected)-set(actual))}")
        return False
    return True


def gate_invariants(db=None, exceptions=None):
    argv = [sys.executable, str(SCRIPTS / "check-f1-invariants.py")]
    if db:
        argv += ["--db", str(db)]
    if exceptions:
        argv += ["--exceptions", str(exceptions)]
    if subprocess.run(argv).returncode != 0:
        return False
    con = fs.connect_db(db)
    try:
        return roster_exact(con)
    finally:
        con.close()


def gate_verdicts(db=None, report=None, verdicts=None):
    argv = [sys.executable, str(SCRIPTS / "crosscheck-constructors.py"), "--gate-only",
            "--db", str(db or DB), "--out", str(report or REPORT),
            "--verdicts", str(verdicts or VERDICTS)]
    return subprocess.run(argv).returncode == 0


def _computed_row(cid, con, as_of):
    career = fs.constructor_career_db(cid, con, as_of=as_of)
    champ = fs.constructor_championships_db(cid, con, as_of=as_of)
    return {"championships_count": champ["value"],
            "championships_years": [d["season"] for d in champ["detail"]],
            "wins": career["wins"]["value"], "podiums": career["podiums"]["value"],
            "entries": career["entries"]["value"]}


def gate_golden(golden_path=None, con=None, db=None):
    golden = json.loads(pathlib.Path(golden_path or GOLDEN).read_text(encoding="utf-8"))["constructors"]
    own = con is None
    con = con or fs.connect_db(db)
    try:
        if set(golden) != set(CONSTRUCTOR_IDS) or not roster_exact(con):
            print("🔴 constructor golden roster 與 canonical roster 不全等")
            return False
        bad_as_of = [cid for cid in CONSTRUCTOR_IDS if golden[cid].get("as_of") != AS_OF]
        if bad_as_of:
            print(f"🔴 11 隊 as_of 必須全為 {{2026,11}}：{bad_as_of}")
            return False
        pending = [cid for cid in CONSTRUCTOR_IDS
                   if str(golden[cid].get("approved_by", "")).upper().startswith("PENDING")]
        if pending:
            print(f"🔴 constructor golden gate FAIL：{len(pending)} 隊 PENDING-charlie：{pending}")
            return False
        diffs = []
        for cid in CONSTRUCTOR_IDS:
            got = _computed_row(cid, con, golden[cid]["as_of"])
            for field in ("championships_count", "championships_years", "wins", "podiums", "entries"):
                if golden[cid].get(field) != got[field]:
                    diffs.append((cid, field, golden[cid].get(field), got[field]))
        if diffs:
            print(f"🔴 constructor golden gate FAIL：{len(diffs)} 欄與 as_of 重算不符")
            for row in diffs[:20]:
                print(f"    {row[0]} {row[1]}: golden={row[2]} 現值={row[3]}")
            return False
        return True
    finally:
        if own:
            con.close()


def run_gates(db=None, exceptions=None, report=None, verdicts=None, golden_path=None):
    print("=" * 70)
    print("車隊頁前置三 gate（任一不綠 → 零產出）")
    print("=" * 70)
    if not gate_invariants(db, exceptions):
        print("🔴 gate ① invariants／roster 未通過 → 中止。")
        return False
    if not gate_verdicts(db, report, verdicts):
        print("🔴 gate ② Wikipedia 裁決未通過 → 中止。")
        return False
    if not gate_golden(golden_path, db=db):
        print("🔴 gate ③ golden 未通過 → 中止。")
        return False
    print("✅ 三 gate 全綠，開始產頁。")
    return True


# ---------- 統計與頁面 ----------

def approved_zh(cid, name):
    """譯名只走 team-zh.json approved-only；Alpine／Racing Bulls 會原文保留。"""
    return rc.TEAM_ZH.get(cid) or rc.TEAM_ZH.get(name)


def constructor_summary(cid, con):
    meta = fs.constructor_meta_db(cid, con)
    career = fs.constructor_career_db(cid, con)
    champ = fs.constructor_championships_db(cid, con)
    return {"cid": cid, "slug": rc.constructor_slug(cid), "meta": meta,
            "zh": approved_zh(cid, meta["name"]), "name": meta["name"],
            "career": career, "champ": champ,
            "champ_years": [d["season"] for d in champ["detail"]],
            "championships": champ["value"], "wins": career["wins"]["value"],
            "podiums": career["podiums"]["value"], "entries": career["entries"]["value"]}


def _season_href(cid, slug):
    def href(year):
        if not (gs.FIRST_YEAR <= year <= gs.LAST_YEAR):
            return None
        if cid in gs.season_subpage_entities(year)[1]:
            return f"/seasons/{year}/teams/{slug}/"
        return f"/seasons/{year}/"
    return href


def sports_team_ld(summary, url):
    node = {"@type": "SportsTeam", "name": summary["zh"] or summary["name"],
            "url": url, "sameAs": [summary["meta"]["url"]] if summary["meta"].get("url") else []}
    if summary["zh"] and summary["zh"] != summary["name"]:
        node["alternateName"] = summary["name"]
    return node


def write_page(path_parts, title, desc, jsonld, body):
    canonical = f"{BASE}/{'/'.join(path_parts)}/"
    html = rc.page_shell(title, desc, canonical, jsonld, body,
                         active="", extra_css=p0.ENTITY_CSS)
    out = PUB
    for part in path_parts:
        out = out / part
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    return canonical


def gen_constructor(cid, con):
    summary = constructor_summary(cid, con)
    slug, zh, name = summary["slug"], summary["zh"], summary["name"]
    seasons = fs.constructor_seasons_db(cid, con)
    url = f"{BASE}/constructors/{slug}/"
    identity = []
    if summary["meta"].get("nationality"):
        identity.append(f"<span>國籍 {esc(summary['meta']['nationality'])}</span>")
    if seasons:
        identity.append(f'<span>參賽賽季 <span class="mono">{seasons[0]}–{seasons[-1]}</span></span>')
    hero = f"""<div class="ent-hero">
  <p class="ent-kicker">車隊檔案 · Constructor</p>
  <h1 class="ent-h1">{p0.pair(zh, name)}</h1>
  <div class="ident">{"".join(identity)}</div>
</div>"""
    cards = (p0.stat_card("車隊世界冠軍", summary["champ"], unit=" 次") +
             p0.stat_card("分站勝場", summary["career"]["wins"], unit=" 勝") +
             p0.stat_card("頒獎台", summary["career"]["podiums"], unit=" 次") +
             p0.stat_card("參賽場次", summary["career"]["entries"], unit=" 站") +
             p0.unavailable_card("桿位", "後續補（定義與資料範圍見方法說明）") +
             p0.unavailable_card("最快圈", "後續補（定義與資料範圍見方法說明）") +
             p0.unavailable_card("生涯積分", "後續補（定義與資料範圍見方法說明）"))
    timeline = p0.career_timeline(seasons, summary["champ_years"], _season_href(cid, slug))
    years = "、".join(map(str, summary["champ_years"])) or "—"
    body = f"""{hero}
<div class="stat-grid">{cards}</div>
<h2 class="sec-title">參賽時間軸</h2>
<p class="note">跑過的賽季填色，車隊世界冠軍年加深紅並加粗。{summary['championships']} 座冠軍：{esc(years)}。</p>
{timeline}
{il.team_related_articles_html(cid, esc=esc)}
<h2 class="sec-title">方法說明</h2>
<p class="note">車隊世界錦標賽自 1958 年才設立，1950–57 沒有車隊冠軍制度；勝場以最終名次為第 1 的不重複分站計，
頒獎台以完賽車次計（一場兩車進前三就是 2 次），參賽場次是不重複且有正賽結果的分站。所有數字都由明細筆數產生。<br>
<b>桿位、最快圈、生涯積分暫不發布</b>，待定義與資料邊界另案完成。</p>"""
    ld = rc.graph_ld([rc.org_node(), rc.website_node(),
                      rc.breadcrumb_node([("首頁", BASE + "/"), ("車隊", BASE + "/constructors/"),
                                          (zh or name, url)]), sports_team_ld(summary, url)])
    # Alpine／Racing Bulls 刻意保留原文（見 approved_zh），標題模板若直接黏中文會變成
    # 「Alpine車隊生涯數據」。rc.phrase() 在羅馬字／數字結尾時補盤古之白。
    disp = zh or name
    write_page(["constructors", slug], rc.phrase(disp, "車隊生涯數據"),
               rc.phrase(disp, "的車隊世界冠軍、分站勝場、頒獎台與參賽場次，每個數字可回溯官方來源。"),
               ld, body)
    return summary


def _index_rows(con):
    positions = {r["constructor_id"]: r["position"] for r in con.execute(
        "SELECT constructor_id, position FROM constructor_standings WHERE season=2026")}
    rows = [constructor_summary(cid, con) for cid in CONSTRUCTOR_IDS]
    rows.sort(key=lambda row: (positions.get(row["cid"], 9999), row["cid"]))
    return rows


def render_index(con):
    rows = _index_rows(con)
    table_rows = []
    for rank, row in enumerate(rows, 1):
        badge = ' <span class="chip">世界冠軍</span>' if row["cid"] in CHAMPION_IDS else ""
        table_rows.append(f"""<tr><td class="mono rk">{rank}</td>
<td><a href="/constructors/{row['slug']}/">{p0.pair(row['zh'], row['name'])}</a>{badge}</td>
<td>{esc(row['meta']['nationality'])}</td><td class="mono">{row['championships']}</td>
<td class="mono">{row['wins']}</td><td class="mono">{row['podiums']}</td><td class="mono">{row['entries']}</td></tr>""")
    table = ("<table class=\"std-tbl\"><thead><tr><th>#</th><th>車隊</th><th>國籍</th>"
             "<th>車隊冠軍</th><th>分站勝場</th><th>頒獎台</th><th>參賽場次</th></tr></thead>"
             f"<tbody>{''.join(table_rows)}</tbody></table>")
    body = f"""<div class="ent-hero"><p class="ent-kicker">2026 車隊名錄 · Constructors</p>
<h1 class="ent-h1">2026 現役車隊<span class="zh-en">　Constructors</span></h1>
<p class="ident"><span>依 2026 車隊積分榜排序，共 <span class="mono">{len(rows)}</span> 隊。</span></p></div>
{table}
<p class="note">本頁涵蓋 2026 現役 11 隊，不包含已退出的歷史冠軍車隊。點車隊名可查看四個可回溯欄位；
車隊冠軍制度始於 1958 年。譯名只採 team-zh.json 已核准值，Alpine／Racing Bulls 刻意保留原文。</p>"""
    items = [{"@type": "ListItem", "position": i,
              "url": f"{BASE}/constructors/{row['slug']}/", "name": row["zh"] or row["name"]}
             for i, row in enumerate(rows, 1)]
    ld = rc.graph_ld([rc.org_node(), rc.website_node(),
                      rc.breadcrumb_node([("首頁", BASE + "/"), ("車隊", BASE + "/constructors/")]),
                      {"@type": "ItemList", "name": "2026 現役車隊", "numberOfItems": len(items),
                       "itemListElement": items}])
    return write_page(["constructors"], "2026 現役車隊名錄",
                      "2026 現役 11 支一級方程式車隊：車隊冠軍、分站勝場、頒獎台與參賽場次。",
                      ld, body)


def main():
    ap = argparse.ArgumentParser(description="產出 /constructors/ 2026 全 11 隊索引與車隊頁。")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--no-sitemap", action="store_true")
    ap.add_argument("--skip-gates", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.skip_gates and not run_gates():
        return 1
    con = fs.connect_db()
    try:
        urls = [render_index(con)]
        for cid in CONSTRUCTOR_IDS:
            row = gen_constructor(cid, con)
            urls.append(f"{BASE}/constructors/{row['slug']}/")
    finally:
        con.close()
    if args.publish and not args.no_sitemap:
        rc.write_sitemap_part("constructors", urls)
    print(f"共 {len(urls)} 頁。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
