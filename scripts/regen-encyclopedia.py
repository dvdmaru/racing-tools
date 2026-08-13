#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regen-encyclopedia.py — 百科線 M7：選擇性重生（facts-hash / per-page 指紋）。

週更百科步驟只重生「受新資料影響的頁」——歷史頁（1950–當季前一年）凍結不重寫（mtime 不動）。

機制＝per-page 輸入指紋：每一頁（或頁群）對它所讀的 db.sqlite 切片算 SHA-256，存
data/f1/page-fingerprints.json。跑時重算現況指紋 vs 上次：
  - 指紋不變 → 完全不呼叫該頁的生成器 → 檔案零重寫（byte-identical、mtime 不動）。
  - 指紋變了 → 重生該頁群。
--full＝忽略指紋全量重生（首次公開全站建置、或指紋檔遺失時）。

頁群粒度：
  - 賽季 y：該年 results/sprint/qualifying/standings/races/status 切片 → _render_one_season(y)。
    當季（有新賽果）→ 指紋變 → 總覽＋seed 子頁＋（新）分站頁全部重生；歷史季指紋恆定 → 跳過。
  - 車手 did：該人 results＋driver_standings＋所涉賽季 status 切片 → gen_driver(did)。
  - 車隊 cid：該隊正賽明細＋已完成季冠軍榜＋身分欄切片 → gen-racing-constructors.py。
  - /seasons/ 索引：全年指紋的合成 → 任一年變則重生。/drivers/ 索引：雙 roster 聯集 53 人指紋的合成。
    /constructors/ 索引：11 隊指紋＋2026 積分榜名次的合成。

呼叫端（update-racing.py 的百科段）在 published 且有新資料時：依序跑車手與車隊的前置三 gate
（invariants／verdicts／golden as_of），全過才 selective_regen；回傳的變更頁 URL 供 IndexNow。
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FINGERPRINTS = ROOT / "data" / "f1" / "page-fingerprints.json"
CONSTRUCTOR_ROSTER = ROOT / "data" / "f1" / "constructor-crosscheck-report.json"


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


dr = _load("gen_racing_drivers", "gen-racing-drivers.py")
# 共用 dr 的模組圖（單一 gs/fs/rc/p0/il 實例；PUB 重導在測試裡才一致）
gs, fs, rc, p0, il = dr.gs, dr.fs, dr.rc, dr.p0, dr.il
cg = _load("gen_racing_constructors", "gen-racing-constructors.py")
# constructor owner 也綁到同一份模組圖，避免測試／管線的 PUB 與資料連線分岔。
cg.gs, cg.fs, cg.rc, cg.p0, cg.il = gs, fs, rc, p0, il
BASE = rc.BASE
CHAMPION_IDS = dr.CHAMPION_IDS
ACTIVE_IDS = dr.ACTIVE_IDS
DRIVER_IDS = dr.DRIVER_IDS
# 車隊頁名單的單一來源＝canonical constructor crosscheck report。
CONSTRUCTOR_IDS = cg.CONSTRUCTOR_IDS
FIRST_YEAR, LAST_YEAR = gs.FIRST_YEAR, gs.LAST_YEAR


# ---------- 指紋（db.sqlite 切片 → SHA-256） ----------

def _h(obj):
    """對任意可 JSON 化物件算決定性 SHA-256（sort_keys、無空白差異）。"""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _file_sha(path):
    p = pathlib.Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def _season_intro_slice(year):
    """季頁導言輸入：原始檔 sha＋目前是否通過 approved.json 綁定。"""
    path = gs._intro_path(year)
    actual = _file_sha(path)
    entry = gs._load_approved().get(gs.INTRO_SLUG.format(year=year), {}) if actual else {}
    return {"sha256": actual, "approved": bool(actual and entry.get("article_sha256") == actual)}


def _season_override_slice(year):
    """季頁 renderer 的非 DB 輸入：該季具名裁決。

    R1 曾先用修正後 DB 算 fingerprint、但季頁仍繞回 raw，導致「指紋新、HTML 舊」。
    只在實際有 Charlie 裁決的年份加入此 slice：受影響歷史季會失效重生，無裁決的
    當季（2026）與其他凍結頁不白刷。
    """
    fields = ("table", "season", "entity_id", "field", "raw_value", "value", "by")
    rows = [{key: item[key] for key in fields}
            for item in gs._ADJUDICATED_OVERRIDES
            if item.get("by") == "charlie" and int(item.get("season", -1)) == year]
    if not rows:
        return []
    return {"renderer": "preserve-raw-json-type-v1",
            "rows": sorted(rows, key=lambda row: (row["table"], row["entity_id"], row["field"]))}


def _year_slice(con, year):
    """賽季 year 的頁面所讀的 db 切片（決定性 tuple 序列）。

    ORDER BY 一律用唯一鍵（results/sprint/qualifying 用代理主鍵 id；standings 用實體 id；
    races 用 round）——避免用 nullable/非唯一欄（如 position）排序造成指紋抖動。
    """
    slc = {}
    for tbl, cols, order in (
        ("results",
         "id, round, position, position_text, points, driver_id, constructor_id, grid, laps, status, number",
         "id"),
        ("sprint_results",
         "id, round, position, position_text, points, driver_id, constructor_id, grid, laps, status, number",
         "id"),
        ("qualifying",
         "id, round, position, driver_id, constructor_id, q1, q2, q3, number", "id"),
        ("driver_standings",
         "position, position_text, points, wins, driver_id, constructor_ids", "driver_id"),
        ("constructor_standings",
         "position, position_text, points, wins, constructor_id", "constructor_id"),
        ("races", "round, name, date, circuit_id, url", "round"),
    ):
        rows = con.execute(
            f"SELECT {cols} FROM {tbl} WHERE season=? ORDER BY {order}", (year,)).fetchall()
        slc[tbl] = [tuple(r) for r in rows]
    st = con.execute("SELECT status FROM seasons WHERE year=?", (year,)).fetchone()
    slc["status"] = st[0] if st else None
    slc["season_intro"] = _season_intro_slice(year)
    overrides = _season_override_slice(year)
    if overrides:
        slc["standings_overrides"] = overrides
    return slc


def _driver_slice(con, did):
    """車手 did 的頁面所讀的 db 切片（生涯 results＋逐季榜＋所涉季 status＋身分欄）。"""
    results = con.execute(
        "SELECT season, round, position_text, points, constructor_id, id "
        "FROM results WHERE driver_id=? ORDER BY season, round, id", (did,)).fetchall()
    standings = con.execute(
        "SELECT season, position, position_text, points, wins, constructor_ids "
        "FROM driver_standings WHERE driver_id=? ORDER BY season", (did,)).fetchall()
    seasons = sorted({r[0] for r in results})
    status = con.execute(
        "SELECT year, status FROM seasons WHERE year IN (%s) ORDER BY year"
        % (",".join("?" * len(seasons)) or "NULL"), seasons).fetchall() if seasons else []
    meta = con.execute(
        "SELECT given_name, family_name, nationality, dob, url, code, permanent_number "
        "FROM drivers WHERE driver_id=?", (did,)).fetchone()
    return {"results": [tuple(r) for r in results],
            "standings": [tuple(r) for r in standings],
            "status": [tuple(r) for r in status],
            "meta": tuple(meta) if meta else None,
            # 車手頁 constructor chips 的可連名單來自這份 roster；其內容變更必須使頁面 stale。
            "constructor_roster_sha256": _file_sha(CONSTRUCTOR_ROSTER)}


def _constructor_slice(con, cid):
    """車隊頁實際讀取的正賽明細、已完成季冠軍榜、參賽季 status 與身分欄。"""
    results = con.execute(
        # number 參與 constructor_career_db 的頒獎台去重鍵，漏切會讓 number 修正後頁面靜默 stale。
        "SELECT season, round, position_text, number, id FROM results "
        "WHERE constructor_id=? ORDER BY season, round, id", (cid,)).fetchall()
    standings = con.execute(
        "SELECT season, position, points, wins FROM constructor_standings "
        "WHERE constructor_id=? ORDER BY season", (cid,)).fetchall()
    done = dict(con.execute("SELECT year, status FROM seasons").fetchall())
    meta = con.execute(
        "SELECT name, nationality, url FROM constructors WHERE constructor_id=?", (cid,)).fetchone()
    return {
        "results": [tuple(r) for r in results],
        "champ": [(r[0], r[2], r[3]) for r in standings
                  if r[1] == 1 and done.get(r[0]) == "completed"],
        "status": [(year, done.get(year)) for year in sorted({r[0] for r in results})],
        "meta": tuple(meta) if meta else None,
    }


def round_keys(round_years):
    """有分站頁的 (year, round) 全集（升冪）。站次表＝gs.season_round_numbers，不另抄判定。"""
    return [(y, r) for y in sorted(round_years) for r in gs.season_round_numbers(y)]


def compute_fingerprints(con, round_years=None):
    """回全站頁群指紋：{'seasons', 'rounds', 'drivers', 'constructors', 'indices'}。

    ⚠️ 車手頁／分站頁／車隊頁指紋＝**db 切片 ＋ 文章 mention 切片**兩塊。原本只切 db.sqlite，
    但這三種頁的「相關報導」讀的是 articles/：新發一篇提到實體的文章時 db 一個 byte 都沒動 →
    指紋不變 → 該頁不重生 → 相關報導區永遠停在舊狀態。這正是本站記憶裡「自動內容旁的靜默
    staleness」，所以把 mention 映射一起切進去（比照 _constructor_slice 只切「頁面真的會渲染
    的東西」）。

    ⚠️ 分站頁指紋刻意**獨立於賽季總覽頁**：發一篇提到某站的文章只該重生那一頁，
    該季總覽與 /seasons/ 索引一個 byte 都不該動（它們不渲染相關報導）。所以
    indices.seasons 仍只由 db-only 的 fp_years 合成，分站的 articles 切片不進去。
    """
    round_years = set(rc.ROUND_YEARS if round_years is None else round_years)
    fp_years = {str(y): _h(_year_slice(con, y)) for y in range(FIRST_YEAR, LAST_YEAR + 1)}
    # 分站頁掛在該季 db 切片之上：賽季資料一變（新賽果）該季全部分站頁本來就會重生，
    # 沿用同一個 hash 當底，行為與 M7 原本的「季變→_render_one_season 全季重生」一致。
    # round 本身也切進 hash：否則同一季內沒有相關報導的站會算出同一個值，
    # 指紋就不再「識別那一頁」（比對雖仍逐鍵、不會出錯，但一個認不出自己是誰的指紋遲早被誤用）
    fp_rounds = {f"{y}/{r}": _h({"round": [y, r], "db": fp_years[str(y)],
                                 "articles": il.round_articles_slice(y, r)})
                 for y, r in round_keys(round_years)}
    fp_drivers_db = {did: _h(_driver_slice(con, did)) for did in DRIVER_IDS}
    fp_drivers = {did: _h({"db": fp_drivers_db[did],
                           "articles": il.driver_articles_slice(did)})
                  for did in DRIVER_IDS}
    fp_cons_db = {cid: _h(_constructor_slice(con, cid)) for cid in CONSTRUCTOR_IDS}
    fp_cons = {cid: _h({"db": fp_cons_db[cid],
                        "articles": il.team_articles_slice(cid)})
               for cid in CONSTRUCTOR_IDS}
    return {
        "seasons": fp_years,
        "rounds": fp_rounds,
        "drivers": fp_drivers,
        "constructors": fp_cons,
        # 索引＝其成員指紋的合成；任一成員變 → 索引指紋變 → 索引重生
        "indices": {
            # /seasons/ 索引與各季總覽都不渲染相關報導 → **db-only**，
            # 免得發一篇文章就把索引與總覽白刷一次（內容一字不變的重寫正是指紋機制要避免的）
            "seasons": _h(sorted(fp_years.items())),
            "drivers": _h(sorted(fp_drivers_db.items())),
            # /constructors/ 索引不渲染相關報導，維持 db-only，避免發文章時白刷索引。
            "constructors": _h({"pages": sorted(fp_cons_db.items()),
                                  "standings_2026": [tuple(r) for r in con.execute(
                                      "SELECT constructor_id, position FROM constructor_standings "
                                      "WHERE season=2026 ORDER BY constructor_id")]}),
        },
    }


def load_fingerprints(path=FINGERPRINTS):
    """讀上次指紋。缺鍵（例如 constructors 是後加的）一律當「沒有指紋」→ 該頁群下次全部重生，
    不會被誤判成「沒變動所以跳過」（default-deny）。"""
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"seasons": {}, "drivers": {}, "constructors": {}, "indices": {}}


def save_fingerprints(fp, path=FINGERPRINTS):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------- 完整 URL 列舉（sitemap part 用；不 render） ----------

def enumerate_season_urls(round_years):
    urls = [f"{BASE}/seasons/"]
    for y in range(LAST_YEAR, FIRST_YEAR - 1, -1):
        urls.append(f"{BASE}/seasons/{y}/")
        for path in sorted(gs.subpage_paths(y)):
            urls.append(f"{BASE}/{path}/")
        if y in round_years:
            for path in sorted(gs.round_page_paths(y),
                               key=lambda s: int(s.rsplit("/", 1)[1])):
                urls.append(f"{BASE}/{path}/")
    return urls


def enumerate_driver_urls():
    return [f"{BASE}/drivers/"] + [f"{BASE}/drivers/{rc.driver_slug(d)}/" for d in DRIVER_IDS]


def enumerate_constructor_urls():
    return ([f"{BASE}/constructors/"]
            + [f"{BASE}/constructors/{rc.constructor_slug(c)}/" for c in CONSTRUCTOR_IDS])


# ---------- 選擇性重生 ----------

def selective_regen(con, full=False, round_years=None, fp_path=FINGERPRINTS,
                    publish=False):
    """只重生指紋變動的頁群。回 dict：changed_years/changed_drivers/changed_urls/…。

    con＝已連 db；round_years＝哪些季有分站頁（預設 config 的 round_years）；
    full＝忽略指紋全量重生；publish＝True 時（重）寫 seasons/drivers/constructors sitemap part
    （完整 URL 集，非只有這次變動的頁）。
    """
    round_years = set(rc.ROUND_YEARS if round_years is None else round_years)
    cur = compute_fingerprints(con, round_years)
    prev = load_fingerprints(fp_path)
    pv_years, pv_drivers, pv_idx = (prev.get("seasons", {}), prev.get("drivers", {}),
                                    prev.get("indices", {}))
    pv_cons, pv_rounds = prev.get("constructors", {}), prev.get("rounds", {})

    changed_years = [y for y in range(LAST_YEAR, FIRST_YEAR - 1, -1)
                     if full or cur["seasons"][str(y)] != pv_years.get(str(y))]
    changed_rounds = [k for k in cur["rounds"] if full or cur["rounds"][k] != pv_rounds.get(k)]
    changed_drivers = [d for d in DRIVER_IDS
                       if full or cur["drivers"][d] != pv_drivers.get(d)]
    changed_constructors = [c for c in CONSTRUCTOR_IDS
                            if full or cur["constructors"][c] != pv_cons.get(c)]
    idx_seasons_changed = full or cur["indices"]["seasons"] != pv_idx.get("seasons")
    idx_drivers_changed = full or cur["indices"]["drivers"] != pv_idx.get("drivers")
    idx_cons_changed = full or cur["indices"]["constructors"] != pv_idx.get("constructors")

    changed_urls = []

    # 賽季：索引 + 逐個變動年（歷史年指紋恆定 → 不在清單 → 完全不呼叫生成器 → 檔案不動）
    built = set(range(FIRST_YEAR, LAST_YEAR + 1))
    if idx_seasons_changed:
        changed_urls.append(gs.render_index(built))
    for y in changed_years:
        yurls = []
        gs._render_one_season(y, yurls, round_years)
        changed_urls.extend(yurls)

    # 分站：只補「該季 db 沒變、但相關報導變了」的那幾頁。
    # 該季 db 變過的年已由 _render_one_season 整季（含全部分站頁）重生，這裡跳過不重複寫。
    rendered_rounds = []
    for key in changed_rounds:
        y, r = (int(x) for x in key.split("/"))
        if y in changed_years:
            continue
        changed_urls.append(gs.render_round(y, r, gs.round_page_paths(y), gs.subpage_paths(y)))
        rendered_rounds.append(key)

    # 車手：索引 + 逐個變動車手
    if idx_drivers_changed:
        changed_urls.append(dr.render_index(con))
    for did in changed_drivers:
        s = dr.gen_driver(did, con)
        changed_urls.append(f"{BASE}/drivers/{s['slug']}/")

    # 車隊：索引 + 逐個變動車隊（唯一 owner＝gen-racing-constructors.py）
    if idx_cons_changed:
        changed_urls.append(cg.render_index(con))
    for cid in changed_constructors:
        s = cg.gen_constructor(cid, con)
        changed_urls.append(f"{BASE}/constructors/{s['slug']}/")

    save_fingerprints(cur, fp_path)

    if publish:
        rc.write_sitemap_part("seasons", enumerate_season_urls(round_years))
        rc.write_sitemap_part("drivers", enumerate_driver_urls())
        rc.write_sitemap_part("constructors", enumerate_constructor_urls())

    return {
        "changed_years": changed_years,
        "changed_rounds": changed_rounds,
        # 實際被單獨重寫的分站頁（changed_rounds 扣掉「整季重生已含」的那些）
        "rounds_rendered_standalone": rendered_rounds,
        "changed_drivers": changed_drivers,
        "changed_constructors": changed_constructors,
        "index_seasons": idx_seasons_changed,
        "index_drivers": idx_drivers_changed,
        "index_constructors": idx_cons_changed,
        "changed_urls": sorted(set(changed_urls)),
    }


def run(full=False, publish=False, skip_gates=False, fp_path=FINGERPRINTS):
    """CLI/orchestrator 入口：跑前置三 gate（as_of golden）→ selective_regen。回 (ok, result)。"""
    if not skip_gates:
        if not dr.run_gates():
            return False, None
        if not cg.run_gates():
            return False, None
    con = fs.connect_db()
    try:
        res = selective_regen(con, full=full, publish=publish, fp_path=fp_path)
    finally:
        con.close()
    return True, res


def main():
    ap = argparse.ArgumentParser(description="百科線選擇性重生（per-page 指紋；歷史頁不重寫）。")
    ap.add_argument("--full", action="store_true", help="忽略指紋全量重生（首次公開/指紋遺失）")
    ap.add_argument("--publish", action="store_true",
                    help="（重）寫 seasons/drivers/constructors sitemap part")
    ap.add_argument("--skip-gates", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    ok, res = run(full=a.full, publish=a.publish, skip_gates=a.skip_gates)
    if not ok:
        print("🔴 前置 gate 未過 → 零重生。", flush=True)
        return 1
    print(f"✅ 選擇性重生：變動賽季 {res['changed_years'] or '—'}；"
          f"單獨重生分站 {res['rounds_rendered_standalone'] or '—'}；"
          f"變動車手 {res['changed_drivers'] or '—'}；"
          f"變動車隊 {res['changed_constructors'] or '—'}；"
          f"索引(季/手/隊) {res['index_seasons']}/{res['index_drivers']}/{res['index_constructors']}；"
          f"變更頁 {len(res['changed_urls'])}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
