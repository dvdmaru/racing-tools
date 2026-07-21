#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-f1-invariants.py — 對 L1 sqlite 斷言計畫 §4.3 的 I1–I9，外加 I10。

★ 核心規則（計畫 §4.4）：**不變量不是「必須全過」，是「失敗的集合必須恰好等於
   data/f1/known_exceptions.json 宣告的例外集合」。多一個少一個都整體 fail。**

   這把「不知道自己不知道」變成可觀測：每個「我覺得這個例外沒關係」都必須被寫下、
   具名、可被 review。⚠️ 計畫 §十二警告：查不出歷史原因的失敗**留在報告的「未解」區、
   不要草草塞進例外清單合法化**——那等於用這個機制把錯誤漂白。本腳本不做核准，
   status=pending_review 的例外由後續審查者稽核。

不變量對照表（granularity 與預期失敗）：
  I1  每季 driver_standings 已列名 position == 1..N 無重複無缺號        （預期 0 失敗）
  I2  每季 勝場(results position_text='1') == 有賽果的場數               （shared drive 會失敗）
  I3  每季 Σ(driver_standings.wins) == 有賽果的場數                     （shared drive 會失敗）
  I4  每季 Σ(driver_standings.wins) == count(results position_text='1') （雙路徑，預期 0 失敗）
  I5  全庫 實體表不存任何跨季聚合欄；統計 value==len(detail) 自洽        （預期 0 失敗）
  I6  每季 逐車手 毛積分(results+sprint 加總) == 官方 standings 積分     （扣分制賽季會失敗）
  I7  每季 排定的每場(races) 都有賽果(results)                          （進行中賽季會失敗）
  I8  全庫 results 依 status 分組計數 == entities/status.json 的計數      （獨立 oracle，預期 0 失敗）
  I9  每季 Σ(driver wins) == Σ(constructor wins)（兩榜都在的季）         （Indy 500 年代會失敗）
  I10 每季 榜首(position=1) 即冠軍 —— 進行中賽季榜首≠冠軍               （進行中賽季會失敗）

I4/I8 最有價值：兩條來源不同的路徑算同一個數字，是沒有外部 oracle 時最接近 oracle 的東西。
⚠️ 所有內部不變量都抓不到「定義層」系統性錯誤（例：把桿位定義成 grid=1）——那是維基
   對照與 known_exceptions 具名斷言存在的理由。

用法：
  python3 scripts/check-f1-invariants.py                 # 人可讀摘要 + 判定 exit code
  python3 scripts/check-f1-invariants.py --json out.json # 另存結構化報告
  python3 scripts/check-f1-invariants.py --db /tmp/x.sqlite
exit code：0 = 失敗集合恰好等於宣告例外集合；1 = 不匹配（有未宣告失敗或宣告了沒發生的）。
"""
import argparse
import importlib.util
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "f1" / "raw"
DEFAULT_DB = ROOT / "data" / "f1" / "db.sqlite"
EXCEPTIONS = ROOT / "data" / "f1" / "known_exceptions.json"


def _ensure_db(db_path):
    """db 不存在就用 build-f1-db.py 現建（保證斷言的是最新 L1）。"""
    db_path = pathlib.Path(db_path)
    if not db_path.exists():
        spec = importlib.util.spec_from_file_location(
            "build_f1_db", ROOT / "scripts" / "build-f1-db.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.build(str(db_path))
    return sqlite3.connect(str(db_path))


def _key(invariant, scope):
    """失敗／宣告的比對鍵：只由 (invariant, scope) 決定，reason/evidence 不參與。"""
    return invariant + "|" + json.dumps(scope, sort_keys=True, ensure_ascii=False)


def _v(invariant, scope, detail):
    return {"invariant": invariant, "scope": scope, "detail": detail,
            "key": _key(invariant, scope)}


# ---------------------------------------------------------------------------
# 各不變量：回傳 violation list
# ---------------------------------------------------------------------------

def _races_with_results(cur):
    return dict(cur.execute(
        "SELECT season, count(DISTINCT round) FROM results GROUP BY season").fetchall())


def inv_I1(cur):
    """每季 driver_standings 已列名 position 集合 == 1..N。"""
    out = []
    seasons = [r[0] for r in cur.execute(
        "SELECT DISTINCT season FROM driver_standings ORDER BY season")]
    for s in seasons:
        pos = [r[0] for r in cur.execute(
            "SELECT position FROM driver_standings WHERE season=? AND position IS NOT NULL",
            (s,))]
        n = len(pos)
        if sorted(pos) != list(range(1, n + 1)):
            out.append(_v("I1", {"season": s},
                          {"ranked": n, "positions_sorted": sorted(pos)}))
    return out


def inv_I2(cur):
    """每季 勝場列數(position_text='1') == 有賽果的場數。"""
    out = []
    rwr = _races_with_results(cur)
    wins = dict(cur.execute(
        "SELECT season, count(*) FROM results WHERE position_text='1' GROUP BY season"))
    for s, races in sorted(rwr.items()):
        w = wins.get(s, 0)
        if w != races:
            out.append(_v("I2", {"season": s}, {"winner_rows": w, "races_with_results": races}))
    return out


def inv_I3(cur):
    """每季 Σ(driver_standings.wins) == 有賽果的場數。"""
    out = []
    rwr = _races_with_results(cur)
    sw = dict(cur.execute(
        "SELECT season, sum(wins) FROM driver_standings GROUP BY season"))
    for s, races in sorted(rwr.items()):
        w = sw.get(s, 0) or 0
        if w != races:
            out.append(_v("I3", {"season": s}, {"standings_wins_sum": w, "races_with_results": races}))
    return out


def inv_I4(cur):
    """每季 Σ(driver_standings.wins) == count(results position_text='1')。雙路徑。"""
    out = []
    sw = dict(cur.execute("SELECT season, sum(wins) FROM driver_standings GROUP BY season"))
    rw = dict(cur.execute(
        "SELECT season, count(*) FROM results WHERE position_text='1' GROUP BY season"))
    for s in sorted(set(sw) | set(rw)):
        a = sw.get(s, 0) or 0
        b = rw.get(s, 0)
        if a != b:
            out.append(_v("I4", {"season": s}, {"standings_wins_sum": a, "results_winner_rows": b}))
    return out


# I5 的實體表白名單：這些表**只准**放身分欄，不准放任何跨季聚合統計欄
#（career wins/championships/poles… 一律必須由 detail 表 COUNT/SUM 得出，不預存純量）。
I5_ENTITY_COLS = {
    "drivers": {"driver_id", "code", "permanent_number", "given_name",
                "family_name", "dob", "nationality", "url"},
    "constructors": {"constructor_id", "name", "nationality", "url"},
    "circuits": {"circuit_id", "name", "locality", "country", "lat", "lng", "url"},
    "seasons": {"year", "url", "status"},
}


def inv_I5(cur):
    """實體表不得預存跨季聚合欄；且 championships 為 COUNT(detail) 自洽。

    這是 f1stats「不存任何 int 統計欄位、數字一律 len()」紀律的 db 版本斷言。
    """
    out = []
    for tbl, allowed in I5_ENTITY_COLS.items():
        cols = {r[1] for r in cur.execute(f"PRAGMA table_info({tbl})")}
        extra = cols - allowed
        if extra:
            out.append(_v("I5", {"table": tbl},
                          {"unexpected_aggregate_columns": sorted(extra)}))
    # 自洽性：任取一位多冠車手，championships 的 value 必等於明細列數
    did = "michael_schumacher"
    rows = cur.execute(
        "SELECT ds.season FROM driver_standings ds JOIN seasons s ON s.year=ds.season "
        "WHERE ds.driver_id=? AND ds.position=1 AND s.status='completed'", (did,)).fetchall()
    value = cur.execute(
        "SELECT count(*) FROM driver_standings ds JOIN seasons s ON s.year=ds.season "
        "WHERE ds.driver_id=? AND ds.position=1 AND s.status='completed'", (did,)).fetchone()[0]
    if value != len(rows):
        out.append(_v("I5", {"consistency": did},
                      {"value": value, "len_detail": len(rows)}))
    return out


def inv_I6(cur):
    """每季 逐車手 毛積分(results+sprint 加總) == 官方 driver_standings.points。

    毛積分＝把該車手該季所有正賽＋衝刺賽的 points 欄直接加總（不重建任何積分制度，
    只加 raw 已有的欄）。與官方最終積分相等 ⟺ 該季沒有對該車手扣分。**不相等的季就是
    扣分制(best-N)賽季**——這正是 §4.2 閉合測試預期在 non-dropped-scores 季全過的意思。
    """
    out = []
    # 逐 (season, driver) 毛積分
    gross = {}
    for s, d, p in cur.execute("SELECT season, driver_id, sum(points) FROM results GROUP BY season, driver_id"):
        gross[(s, d)] = (gross.get((s, d), 0.0) or 0.0) + (p or 0.0)
    for s, d, p in cur.execute("SELECT season, driver_id, sum(points) FROM sprint_results GROUP BY season, driver_id"):
        gross[(s, d)] = (gross.get((s, d), 0.0) or 0.0) + (p or 0.0)
    seasons = [r[0] for r in cur.execute("SELECT DISTINCT season FROM driver_standings ORDER BY season")]
    for s in seasons:
        mism = []
        for d, off in cur.execute(
                "SELECT driver_id, points FROM driver_standings WHERE season=?", (s,)):
            g = gross.get((s, d), 0.0)
            if abs(g - (off or 0.0)) > 1e-9:
                mism.append({"driver_id": d, "gross": round(g, 3), "official": off})
        if mism:
            out.append(_v("I6", {"season": s},
                          {"drivers_with_dropped_scores": len(mism),
                           "sample": sorted(mism, key=lambda x: x["driver_id"])[:3]}))
    return out


def inv_I7(cur):
    """每季 races 表排定的每場都要有 results（全域缺漏偵測）。"""
    out = []
    scheduled = {}
    for s, r in cur.execute("SELECT season, round FROM races"):
        scheduled.setdefault(s, set()).add(r)
    have = {}
    for s, r in cur.execute("SELECT DISTINCT season, round FROM results"):
        have.setdefault(s, set()).add(r)
    for s in sorted(scheduled):
        missing = sorted(scheduled[s] - have.get(s, set()))
        if missing:
            out.append(_v("I7", {"season": s},
                          {"scheduled": len(scheduled[s]), "with_results": len(have.get(s, set())),
                           "missing_rounds": missing}))
    return out


def inv_I8(cur):
    """全庫 results 依 status 分組計數 == entities/status.json 的計數（獨立 oracle）。

    status.json 是 API 伺服器端對全庫賽果的 status 頻率彙整，與我們逐檔落地的路徑
    完全獨立。逐 status 相等 ⟺ offset 分頁沒漏行沒重複。sprint 不計入（實測 status.json
    僅涵蓋正賽）。
    """
    oracle = {s["status"]: int(s["count"])
              for s in json.loads((RAW / "entities" / "status.json").read_text(encoding="utf-8"))["Status"]}
    got = dict(cur.execute("SELECT status, count(*) FROM results GROUP BY status"))
    out = []
    for st in sorted(set(oracle) | set(got)):
        if oracle.get(st, 0) != got.get(st, 0):
            out.append(_v("I8", {"status": st},
                          {"results_count": got.get(st, 0), "status_json_count": oracle.get(st, 0)}))
    return out


def inv_I9(cur):
    """每季 Σ(driver wins) == Σ(constructor wins)（兩榜都存在的季）。"""
    out = []
    dw = dict(cur.execute("SELECT season, sum(wins) FROM driver_standings GROUP BY season"))
    cw = dict(cur.execute("SELECT season, sum(wins) FROM constructor_standings GROUP BY season"))
    for s in sorted(set(dw) & set(cw)):
        a = dw.get(s, 0) or 0
        b = cw.get(s, 0) or 0
        if a != b:
            out.append(_v("I9", {"season": s}, {"driver_wins": a, "constructor_wins": b}))
    return out


def inv_I10(cur):
    """每季 榜首(position=1) 即冠軍——進行中賽季的榜首是『目前領先』不是冠軍。

    比照 f1stats._is_completed：seasons.status='in_progress' 的季，其榜首不得計為冠軍。
    這條把「進行中賽季誤算一冠」那類 bug 變成具名、可觀測的斷言（2026 是唯一 in_progress）。
    driver / constructor 兩個冠軍各自斷言。
    """
    out = []
    for champ, tbl, idcol in (("driver", "driver_standings", "driver_id"),
                              ("constructor", "constructor_standings", "constructor_id")):
        rows = cur.execute(
            f"SELECT ds.season, ds.{idcol}, s.status FROM {tbl} ds "
            f"JOIN seasons s ON s.year=ds.season WHERE ds.position=1 ORDER BY ds.season").fetchall()
        for season, ent, status in rows:
            if status != "completed":
                out.append(_v("I10", {"season": season, "championship": champ},
                              {"leader": ent, "season_status": status,
                               "note": "榜首為目前領先者，賽季未完成不計冠軍"}))
    return out


ALL_INVARIANTS = [inv_I1, inv_I2, inv_I3, inv_I4, inv_I5,
                  inv_I6, inv_I7, inv_I8, inv_I9, inv_I10]


# ---------------------------------------------------------------------------
# 主流程：跑全部 → 對照 known_exceptions
# ---------------------------------------------------------------------------

def load_declared(path=EXCEPTIONS):
    if not pathlib.Path(path).exists():
        return []
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8")).get("exceptions", [])


def run(cur, declared):
    """回傳結構化報告 dict。核心判定：unexpected 與 missing 都空 → passed。"""
    failures = []
    per_inv = {}
    for fn in ALL_INVARIANTS:
        vs = fn(cur)
        inv_name = fn.__name__.replace("inv_", "")
        per_inv[inv_name] = [{"scope": v["scope"], "detail": v["detail"]} for v in vs]
        failures.extend(vs)

    actual = {v["key"]: v for v in failures}
    declared_map = {_key(e["invariant"], e["scope"]): e for e in declared}

    unexpected = sorted(set(actual) - set(declared_map))         # 失敗了但沒宣告 → 危險
    missing = sorted(set(declared_map) - set(actual))            # 宣告了但沒發生 → 過期例外
    matched = sorted(set(actual) & set(declared_map))
    pending = sorted(k for k in matched
                     if declared_map[k].get("status") == "pending_review")

    return {
        "passed": not unexpected and not missing,
        "summary": {
            "total_failures": len(actual),
            "declared_exceptions": len(declared_map),
            "matched": len(matched),
            "unexpected_failures": len(unexpected),
            "missing_declarations": len(missing),
            "pending_review": len(pending),
        },
        "unexpected_failures": [actual[k] for k in unexpected],
        "missing_declarations": [{"key": k, **declared_map[k]} for k in missing],
        "matched": [{"key": k, "invariant": actual[k]["invariant"],
                     "scope": actual[k]["scope"],
                     "declared_reason": declared_map[k].get("reason"),
                     "declared_status": declared_map[k].get("status"),
                     "detail": actual[k]["detail"]} for k in matched],
        "per_invariant_failure_counts": {k: len(v) for k, v in per_inv.items()},
    }


def _print_human(rep):
    s = rep["summary"]
    print("=" * 68)
    print("F1 不變量檢查（規則：失敗集合必須恰好等於宣告例外集合）")
    print("=" * 68)
    print("各不變量失敗數：")
    for k in ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9", "I10"):
        print(f"  {k:4s} {rep['per_invariant_failure_counts'].get(k, 0)}")
    print(f"\n總失敗 {s['total_failures']}　宣告例外 {s['declared_exceptions']}　"
          f"匹配 {s['matched']}")
    print(f"未宣告失敗 {s['unexpected_failures']}　過期宣告 {s['missing_declarations']}　"
          f"待審核例外 {s['pending_review']}")

    if rep["unexpected_failures"]:
        print("\n🔴 未宣告的失敗（未解——不要塞進例外清單漂白，先查歷史原因）：")
        for v in rep["unexpected_failures"]:
            print(f"    {v['invariant']} {v['scope']} → {v['detail']}")
    if rep["missing_declarations"]:
        print("\n⚠️  宣告了卻沒發生的例外（過期，該從清單移除）：")
        for v in rep["missing_declarations"]:
            print(f"    {v['key']}（{v.get('reason')}）")

    print("\n" + ("✅ 通過：失敗集合恰好等於宣告例外集合。"
                  if rep["passed"] else "❌ 未通過：失敗集合與宣告例外集合不匹配。"))
    if rep["summary"]["pending_review"]:
        print(f"（{rep['summary']['pending_review']} 條例外仍 pending_review，"
              f"等後續審查者核准——本腳本不做核准。）")


def main():
    ap = argparse.ArgumentParser(description="I1–I10 不變量檢查 vs known_exceptions")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--exceptions", default=str(EXCEPTIONS))
    ap.add_argument("--json", help="另存結構化報告到此路徑")
    a = ap.parse_args()
    con = _ensure_db(a.db)
    con.row_factory = None
    try:
        rep = run(con.cursor(), load_declared(a.exceptions))
    finally:
        con.close()
    if a.json:
        pathlib.Path(a.json).write_text(
            json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_human(rep)
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
