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
  - /seasons/ 索引：全年指紋的合成 → 任一年變則重生。/drivers/ 索引：35 人指紋的合成。

呼叫端（update-racing.py 的百科段）在 published 且有新資料時：先跑 dr 的前置三 gate
（invariants／verdicts／golden as_of），過了才 selective_regen；回傳的變更頁 URL 供 IndexNow。
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


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


dr = _load("gen_racing_drivers", "gen-racing-drivers.py")
# 共用 dr 的模組圖（單一 gs/fs/rc/p0 實例；PUB 重導在測試裡才一致）
gs, fs, rc, p0 = dr.gs, dr.fs, dr.rc, dr.p0
BASE = rc.BASE
CHAMPION_IDS = dr.CHAMPION_IDS
FIRST_YEAR, LAST_YEAR = gs.FIRST_YEAR, gs.LAST_YEAR


# ---------- 指紋（db.sqlite 切片 → SHA-256） ----------

def _h(obj):
    """對任意可 JSON 化物件算決定性 SHA-256（sort_keys、無空白差異）。"""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


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
            "meta": tuple(meta) if meta else None}


def compute_fingerprints(con):
    """回全站頁群指紋：{'seasons':{year:h}, 'drivers':{did:h}, 'indices':{'seasons':h,'drivers':h}}。"""
    fp_years = {str(y): _h(_year_slice(con, y)) for y in range(FIRST_YEAR, LAST_YEAR + 1)}
    fp_drivers = {did: _h(_driver_slice(con, did)) for did in CHAMPION_IDS}
    return {
        "seasons": fp_years,
        "drivers": fp_drivers,
        # 索引＝其成員指紋的合成；任一成員變 → 索引指紋變 → 索引重生
        "indices": {
            "seasons": _h(sorted(fp_years.items())),
            "drivers": _h(sorted(fp_drivers.items())),
        },
    }


def load_fingerprints(path=FINGERPRINTS):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"seasons": {}, "drivers": {}, "indices": {}}


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
    return [f"{BASE}/drivers/"] + [f"{BASE}/drivers/{rc.driver_slug(d)}/" for d in CHAMPION_IDS]


# ---------- 選擇性重生 ----------

def selective_regen(con, full=False, round_years=None, fp_path=FINGERPRINTS,
                    publish=False):
    """只重生指紋變動的頁群。回 dict：changed_years/changed_drivers/changed_urls/…。

    con＝已連 db；round_years＝哪些季有分站頁（預設 config 的 round_years）；
    full＝忽略指紋全量重生；publish＝True 時（重）寫 seasons/drivers sitemap part（完整 URL 集）。
    """
    round_years = set(rc.ROUND_YEARS if round_years is None else round_years)
    cur = compute_fingerprints(con)
    prev = load_fingerprints(fp_path)
    pv_years, pv_drivers, pv_idx = (prev.get("seasons", {}), prev.get("drivers", {}),
                                    prev.get("indices", {}))

    changed_years = [y for y in range(LAST_YEAR, FIRST_YEAR - 1, -1)
                     if full or cur["seasons"][str(y)] != pv_years.get(str(y))]
    changed_drivers = [d for d in CHAMPION_IDS
                       if full or cur["drivers"][d] != pv_drivers.get(d)]
    idx_seasons_changed = full or cur["indices"]["seasons"] != pv_idx.get("seasons")
    idx_drivers_changed = full or cur["indices"]["drivers"] != pv_idx.get("drivers")

    changed_urls = []

    # 賽季：索引 + 逐個變動年（歷史年指紋恆定 → 不在清單 → 完全不呼叫生成器 → 檔案不動）
    built = set(range(FIRST_YEAR, LAST_YEAR + 1))
    if idx_seasons_changed:
        changed_urls.append(gs.render_index(built))
    for y in changed_years:
        yurls = []
        gs._render_one_season(y, yurls, round_years)
        changed_urls.extend(yurls)

    # 車手：索引 + 逐個變動車手
    if idx_drivers_changed:
        changed_urls.append(dr.render_index(con))
    for did in changed_drivers:
        s = dr.gen_driver(did, con)
        changed_urls.append(f"{BASE}/drivers/{s['slug']}/")

    save_fingerprints(cur, fp_path)

    if publish:
        rc.write_sitemap_part("seasons", enumerate_season_urls(round_years))
        rc.write_sitemap_part("drivers", enumerate_driver_urls())

    return {
        "changed_years": changed_years,
        "changed_drivers": changed_drivers,
        "index_seasons": idx_seasons_changed,
        "index_drivers": idx_drivers_changed,
        "changed_urls": sorted(set(changed_urls)),
    }


def run(full=False, publish=False, skip_gates=False, fp_path=FINGERPRINTS):
    """CLI/orchestrator 入口：跑前置三 gate（as_of golden）→ selective_regen。回 (ok, result)。"""
    if not skip_gates and not dr.run_gates():
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
    ap.add_argument("--publish", action="store_true", help="（重）寫 seasons/drivers sitemap part")
    ap.add_argument("--skip-gates", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    ok, res = run(full=a.full, publish=a.publish, skip_gates=a.skip_gates)
    if not ok:
        print("🔴 前置 gate 未過 → 零重生。", flush=True)
        return 1
    print(f"✅ 選擇性重生：變動賽季 {res['changed_years'] or '—'}；"
          f"變動車手 {res['changed_drivers'] or '—'}；"
          f"索引(季/手) {res['index_seasons']}/{res['index_drivers']}；"
          f"變更頁 {len(res['changed_urls'])}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
