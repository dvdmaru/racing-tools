#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-f1-invariants.py — 對 L1 sqlite 斷言 I1–I12 並對照 known_exceptions（指紋綁定）。

★ 核心規則（計畫 §4.4）：**不變量不是「必須全過」，是「失敗集合必須恰好等於
   data/f1/known_exceptions.json 宣告的例外集合」。多一個少一個都整體 FAIL。**

★ 指紋綁定（2026-07-21 Sol 查核桌 S0-1 反例的修正）：
   舊版比對鍵只鎖 (invariant, scope)，Sol 把 1950 某列 points 由 9 改成 1009，
   I6 detail 變 gross 1030 卻仍命中同一個 `I6|{"season":1950}` → 全綠。**任意差額被同季
   例外漂白。** 修法：每條失敗算一個 **canonical fingerprint**（sha256 蓋住 invariant＋
   scope＋完整判別明細），例外必須連指紋一起宣告；比對用 (invariant, scope, fingerprint)
   三元組。指紋由本腳本 `--seal` 從現況一次性產生、寫回 known_exceptions.json（只新增
   fingerprint 欄，approved_by/approved_date/reason/evidence 全部保留不動），比照
   config/approved.json 的 sha256 default-deny 精神。

   指紋覆蓋範圍（2026-07-21 Sol 覆核 S1 修正碰撞窗後的**實際保證**）：
   浮點值以**全精度字串**入指紋（不 round，1e-7 變動也會改指紋）；集合類明細（如 I11 孤兒）
   以 `count + 全集 sha256` 入指紋（不截斷，第 51 個以後成員換掉也會改指紋）。因此
   **任何數值或成員變動都會改指紋 → 三元組不匹配 → FAIL**。

★ 核准進 gate（2026-07-21 Sol 覆核 S0 修正）：
   指紋只證明「資料與封印當下相同」，不證明「這條例外已獲核准」。故通過條件除了三元組
   匹配，**每條 matched 例外還必須 status=='approved' 且 approved_by/approved_date/reason/
   evidence 五欄皆非空**；任一不符＝FAIL（未核准/被抽掉 metadata 的例外不得漂白失敗）。

★ 宣告清單 fail-closed（2026-07-21 Sol 終輪 S1-2 修正）：
   declared_map 用 dict 建立會把**同 triple 的重複宣告靜默折疊**——Sol 反證：39 條前插一條
   同 triple 的 pending_review，後面的 approved 覆寫它，輸入 40 條卻只報 39、gate PASS。
   故**建 dict 前先 `validate_declarations()`**：缺 required 欄位、id 重複、triple 重複、
   或輸入條數 != 納入條數，任一即整體 FAIL（不得靜默跳過或折疊）。

⚠️ 計畫 §十二警告：查不出歷史原因的失敗**留在報告的未解區、不要草草塞進例外清單漂白**。
   本腳本不做核准；status 仍由 Charlie 具名核准。

────────────────────────────────────────────────────────────────────────
每條不變量「守得住什麼／守不住什麼」（Sol S1-2 誠實化，不誇大覆蓋）：

  I1  每季 driver_standings 已列名 position == 1..N
        守：分頁漏行、名次缺號/重號。 不守：名次配給錯車手（集合仍完整就過）。
  I2  每季 勝場列(position_text='1') == 有賽果場數
        守：整季勝場列數量異常（shared drive）。 不守：勝者身分錯而每場仍一列。
  I3  每季 Σ(standings.wins) == 有賽果場數
        守：standings↔results 場數級不同步。 不守：勝場配給錯車手（總和不變）。
  I4  每季 Σ(standings.wins) == 勝場列數（雙查詢路徑）
        守：聚合/driver_id 對錯造成的總數級偏差。 不守：兩端同向錯、或只錯身分。
  I5  4 位有生涯檔車手：f1stats 發布路徑 vs db 獨立 SQL 逐欄比對＋實體表無聚合欄
        守：發布統計與 db 明細不一致、實體表被塞跨季聚合欄。 不守：兩個原始源同錯、
             未涵蓋的欄位（poles/fastest_laps/生涯積分/starts 皆未發布，不假裝比對）。
  I6  每季 逐車手 毛積分(results+sprint) == 官方 standings 積分；指紋鎖全體 mismatch 明細
        守：扣分制以外的任何積分竄改（含 §S0-1 的 +1000）。 不守：兩個源同步竄改。
  I7  每個 scheduled round 都有 result；指紋鎖缺漏 round 集合
        守：整場賽果缺漏。 不守：該場 result 的身分/內容錯。
  I8  results 依 status 分組計數 == entities/status.json（獨立查詢路徑，非獨立資料源）
        守：分頁漏行/重複造成的 status 級偏差。 不守：status 在列間互換、上游同錯。
  I9  每季 Σ(driver wins) == Σ(constructor wins)；指紋鎖未列名車廠的勝場列
        守：driver↔constructor 勝場歸屬的總數級偏差。 不守：歸屬互換而總數不變。
  I10 進行中賽季榜首固定產 violation（比照 f1stats._is_completed）
        守：把進行中賽季榜首誤計為冠軍。 不守：非直接斷言全庫 career championship 集合。
  I11 referential integrity：results/qualifying/sprint/standings/races 的
        driver_id/constructor_id/circuit_id/(season,round)/season 全部須存在於實體表
        守：孤兒外鍵（§S1-1 的 __orphan_driver__）。 不守：指向存在但錯誤的實體。
  I12 賽季宇宙覆蓋（Terra 盲測缺口）：seasons.year 連續 1950..max ＋ 每季覆蓋
        races/results/driver_standings（constructor_standings 只要求 >=1958）
        守：整季消失（I1–I11 以「實際出現的賽季」為迭代宇宙的盲區——整季空了迴圈空轉全綠）、
             seasons 錨點斷裂（缺年/重複/min!=1950）。 不守：上游 seasons.json 從源頭整批缺
             （僅靠 1950 下限與連續性部分防禦；若整段連 seasons 也一併消失、下限仍在則抓不到）。

I4/I8/I11 是**獨立查詢路徑**（不是獨立資料源，也不是完整 oracle）——沒有外部 oracle 時
最接近交叉驗證的東西。定義層系統性錯誤（例：把桿位定義成 grid=1）這些都抓不到，那是
維基外部對照與 known_exceptions 具名斷言存在的理由。
────────────────────────────────────────────────────────────────────────

用法：
  python3 scripts/check-f1-invariants.py                 # 檢查：三元組匹配才 exit 0
  python3 scripts/check-f1-invariants.py --json out.json # 另存結構化報告
  python3 scripts/check-f1-invariants.py --seal          # 一次性把現況指紋寫回例外清單
  python3 scripts/check-f1-invariants.py --db /tmp/x.sqlite
exit code：0 = 失敗三元組集合恰好等於宣告三元組集合；1 = 不匹配（未宣告/過期/指紋不符）。
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "f1" / "raw"
DEFAULT_DB = ROOT / "data" / "f1" / "db.sqlite"
EXCEPTIONS = ROOT / "data" / "f1" / "known_exceptions.json"

# 有生涯檔（drivers/<id>-results.json）的車手＝I5 雙路徑對照對象
I5_CROSSCHECK_DRIVERS = ("hamilton", "max_verstappen", "michael_schumacher", "senna")
# I5 有比對到的欄位；沒發布/沒精確定義的欄位明列於此、不假裝覆蓋（§4.6）
I5_COMPARED_FIELDS = ("wins", "podiums", "entries", "championships")
I5_UNCOVERED_FIELDS = ("poles", "fastest_laps", "career_points", "starts")


def _load_module(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ensure_db(db_path):
    db_path = pathlib.Path(db_path)
    if not db_path.exists():
        _load_module("build_f1_db", "build-f1-db.py").build(str(db_path))
    return sqlite3.connect(str(db_path))


# ---------------------------------------------------------------------------
# 指紋：canonical serialization → sha256
# ---------------------------------------------------------------------------

def _canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _num(x):
    """浮點以**全精度字串**入指紋（不 round；repr(float) 可 round-trip，1e-7 變動也會改）。

    Sol S1：舊版 round(6) 讓 6.0→6.0000001 同指紋（碰撞窗）。改成全精度字串後，
    同 runtime 讀同一 DB 值 → 同字串（決定性）；任何實際數值變動 → 不同字串 → 指紋變。
    """
    return repr(float(x))


def _set_hash(items):
    """集合類明細以 count + 全集 sha256 入指紋（不截斷；第 51 個以後換人也會改指紋）。"""
    canon = _canon(sorted(items))
    return {"count": len(items),
            "sha256": hashlib.sha256(canon.encode("utf-8")).hexdigest()}


def _scope_key(invariant, scope):
    return invariant + "|" + _canon(scope)


def _fingerprint(invariant, scope, fp_detail):
    """完整判別明細的 sha256。任何數值/成員變動 → 指紋變 → 三元組不匹配。"""
    return hashlib.sha256(
        _canon({"invariant": invariant, "scope": scope, "detail": fp_detail}).encode("utf-8")
    ).hexdigest()


def _v(invariant, scope, fp_detail):
    fp = _fingerprint(invariant, scope, fp_detail)
    return {"invariant": invariant, "scope": scope, "detail": fp_detail,
            "scope_key": _scope_key(invariant, scope), "fingerprint": fp,
            "triple": _scope_key(invariant, scope) + "@" + fp}


# ---------------------------------------------------------------------------
# 共用查詢
# ---------------------------------------------------------------------------

def _races_with_results(cur):
    return dict(cur.execute(
        "SELECT season, count(DISTINCT round) FROM results GROUP BY season").fetchall())


# ---------------------------------------------------------------------------
# 各不變量：回傳 violation list（每條帶完整 fp_detail）
# ---------------------------------------------------------------------------

def _seasons(cur, table):
    # 先物化成 list：同一 cursor 巢狀 execute 會重置外層 result set（單 cursor 陷阱）
    return [r[0] for r in cur.execute(
        f"SELECT DISTINCT season FROM {table} ORDER BY season").fetchall()]


def inv_I1(cur):
    out = []
    for s in _seasons(cur, "driver_standings"):
        rows = cur.execute(
            "SELECT position, driver_id FROM driver_standings "
            "WHERE season=? AND position IS NOT NULL ORDER BY position, driver_id", (s,)).fetchall()
        pos = [p for p, _ in rows]
        n = len(pos)
        if sorted(pos) != list(range(1, n + 1)):
            out.append(_v("I1", {"season": s},
                          {"ranked": n, "by_position": [[p, d] for p, d in rows]}))
    return out


def inv_I2(cur):
    out = []
    rwr = _races_with_results(cur)
    for s, races in sorted(rwr.items()):
        winners = sorted(d[0] for d in cur.execute(
            "SELECT driver_id FROM results WHERE season=? AND position_text='1'", (s,)))
        if len(winners) != races:
            out.append(_v("I2", {"season": s},
                          {"winner_driver_ids": winners, "races_with_results": races,
                           "delta": len(winners) - races}))
    return out


def inv_I3(cur):
    out = []
    rwr = _races_with_results(cur)
    for s, races in sorted(rwr.items()):
        per = sorted([d, w] for d, w in cur.execute(
            "SELECT driver_id, wins FROM driver_standings WHERE season=? AND wins>0", (s,)))
        total = sum(w for _, w in per)
        if total != races:
            out.append(_v("I3", {"season": s},
                          {"per_driver_wins": per, "races_with_results": races,
                           "delta": total - races}))
    return out


def inv_I4(cur):
    out = []
    sw = dict(cur.execute("SELECT season, sum(wins) FROM driver_standings GROUP BY season"))
    rw = dict(cur.execute(
        "SELECT season, count(*) FROM results WHERE position_text='1' GROUP BY season"))
    for s in sorted(set(sw) | set(rw)):
        a = sw.get(s, 0) or 0
        b = rw.get(s, 0)
        if a != b:
            out.append(_v("I4", {"season": s},
                          {"standings_wins_sum": a, "results_winner_rows": b, "delta": a - b}))
    return out


# --- I5：實體表白名單（結構）＋ 4 車手發布路徑 vs db 獨立 SQL（雙路徑） ---

I5_ENTITY_COLS = {
    "drivers": {"driver_id", "code", "permanent_number", "given_name",
                "family_name", "dob", "nationality", "url"},
    "constructors": {"constructor_id", "name", "nationality", "url"},
    "circuits": {"circuit_id", "name", "locality", "country", "lat", "lng", "url"},
    "seasons": {"year", "url", "status"},
}


def _i5_schema_check(cur):
    """實體表不得預存跨季聚合欄（career wins/championships…必須由 detail COUNT 得出）。"""
    out = []
    for tbl, allowed in I5_ENTITY_COLS.items():
        cols = {r[1] for r in cur.execute(f"PRAGMA table_info({tbl})")}
        extra = sorted(cols - allowed)
        if extra:
            out.append(_v("I5", {"kind": "schema", "table": tbl},
                          {"unexpected_aggregate_columns": extra}))
    return out


def _db_driver_stats(cur, did):
    """db 端獨立重算（來源＝global results/*.json 落地的 results 表 + driver_standings 表）。"""
    return {
        "wins": cur.execute(
            "SELECT count(*) FROM results WHERE driver_id=? AND position_text='1'", (did,)).fetchone()[0],
        "podiums": cur.execute(
            "SELECT count(*) FROM results WHERE driver_id=? AND position_text IN ('1','2','3')", (did,)).fetchone()[0],
        "entries": cur.execute(
            "SELECT count(DISTINCT season || '-' || round) FROM results WHERE driver_id=?", (did,)).fetchone()[0],
        "championships": cur.execute(
            "SELECT count(*) FROM driver_standings ds JOIN seasons s ON s.year=ds.season "
            "WHERE ds.driver_id=? AND ds.position=1 AND s.status='completed'", (did,)).fetchone()[0],
    }


def _i5_dualpath_check(cur):
    """f1stats 發布路徑（讀 per-driver 生涯檔）vs db SQL（讀 global 賽果表）逐欄比對。

    兩條路徑讀的是**不同 raw 檔**（drivers/<id>-results.json ↔ 全庫 results/*.json 落地的表），
    故為真雙路徑，不是同一 SQL 比自己（Sol S1-1 指出舊 I5 是恆真式）。
    只比對已發布且有精確定義的欄位；未涵蓋欄位（poles/fastest_laps/career_points/starts）
    明列不假裝。
    """
    f1 = _load_module("f1stats", "f1stats.py")
    out = []
    present = {r[0] for r in cur.execute("SELECT driver_id FROM drivers")}
    for did in I5_CROSSCHECK_DRIVERS:
        if did not in present:
            continue  # 合成測試 db 無此車手時略過（真實 db 一定有）
        try:
            car = f1.driver_career(did)
            champ = f1.driver_championships(did)
        except FileNotFoundError:
            continue
        pub = {"wins": car["wins"]["value"], "podiums": car["podiums"]["value"],
               "entries": car["entries"]["value"], "championships": champ["value"]}
        db = _db_driver_stats(cur, did)
        diffs = sorted([f, pub[f], db[f]] for f in I5_COMPARED_FIELDS if pub[f] != db[f])
        if diffs:
            out.append(_v("I5", {"kind": "dualpath", "driver_id": did},
                          {"field_publish_db": diffs}))
    return out


def inv_I5(cur):
    return _i5_schema_check(cur) + _i5_dualpath_check(cur)


def inv_I6(cur):
    """每季 逐車手 毛積分(results+sprint) == 官方 standings 積分；指紋鎖全體 mismatch。"""
    out = []
    gross = {}
    for s, d, p in cur.execute(
            "SELECT season, driver_id, sum(points) FROM results GROUP BY season, driver_id"):
        gross[(s, d)] = gross.get((s, d), 0.0) + (p or 0.0)
    for s, d, p in cur.execute(
            "SELECT season, driver_id, sum(points) FROM sprint_results GROUP BY season, driver_id"):
        gross[(s, d)] = gross.get((s, d), 0.0) + (p or 0.0)
    for s in _seasons(cur, "driver_standings"):
        mism = []
        for d, off in cur.execute(
                "SELECT driver_id, points FROM driver_standings WHERE season=?", (s,)).fetchall():
            g = gross.get((s, d), 0.0)
            if abs(g - (off or 0.0)) > 1e-9:
                # 全精度字串（Sol S1）：gross/official/delta 不 round，任何 1e-7 變動都改指紋
                mism.append([d, _num(g), _num(off or 0.0), _num(g - (off or 0.0))])
        if mism:
            out.append(_v("I6", {"season": s},
                          {"mismatches": sorted(mism), "count": len(mism)}))
    return out


def inv_I7(cur):
    out = []
    scheduled, have = {}, {}
    for s, r in cur.execute("SELECT season, round FROM races"):
        scheduled.setdefault(s, set()).add(r)
    for s, r in cur.execute("SELECT DISTINCT season, round FROM results"):
        have.setdefault(s, set()).add(r)
    for s in sorted(scheduled):
        missing = sorted(scheduled[s] - have.get(s, set()))
        if missing:
            out.append(_v("I7", {"season": s},
                          {"missing_rounds": missing, "scheduled": len(scheduled[s]),
                           "with_results": len(have.get(s, set()))}))
    return out


def inv_I8(cur):
    """results 依 status 分組計數 == entities/status.json（獨立查詢路徑）。"""
    oracle = {s["status"]: int(s["count"]) for s in json.loads(
        (RAW / "entities" / "status.json").read_text(encoding="utf-8"))["Status"]}
    got = dict(cur.execute("SELECT status, count(*) FROM results GROUP BY status"))
    out = []
    for st in sorted(set(oracle) | set(got)):
        if oracle.get(st, 0) != got.get(st, 0):
            out.append(_v("I8", {"status": st},
                          {"results_count": got.get(st, 0), "status_json_count": oracle.get(st, 0)}))
    return out


def inv_I9(cur):
    """每季 Σ(driver wins)==Σ(constructor wins)；指紋鎖未被計入車廠的勝場列。"""
    out = []
    dw = dict(cur.execute("SELECT season, sum(wins) FROM driver_standings GROUP BY season"))
    cw = dict(cur.execute("SELECT season, sum(wins) FROM constructor_standings GROUP BY season"))
    for s in sorted(set(dw) & set(cw)):
        a, b = dw.get(s, 0) or 0, cw.get(s, 0) or 0
        if a != b:
            credited = {c for (c, w) in cur.execute(
                "SELECT constructor_id, wins FROM constructor_standings WHERE season=? AND wins>0", (s,))}
            uncredited = sorted(
                [rnd, drv, con] for (rnd, drv, con) in cur.execute(
                    "SELECT round, driver_id, constructor_id FROM results "
                    "WHERE season=? AND position_text='1'", (s,))
                if con not in credited)
            out.append(_v("I9", {"season": s},
                          {"driver_wins": a, "constructor_wins": b, "delta": a - b,
                           "uncredited_winner_rows": uncredited}))
    return out


def inv_I10(cur):
    out = []
    for champ, tbl, idcol in (("driver", "driver_standings", "driver_id"),
                              ("constructor", "constructor_standings", "constructor_id")):
        for season, ent, status in cur.execute(
                f"SELECT ds.season, ds.{idcol}, s.status FROM {tbl} ds "
                f"JOIN seasons s ON s.year=ds.season WHERE ds.position=1 ORDER BY ds.season"):
            if status != "completed":
                out.append(_v("I10", {"season": season, "championship": champ},
                              {"leader": ent, "season_status": status}))
    return out


# --- I11：referential integrity（Sol S1-1，schema 無 FK，改用顯式斷言） ---

I11_CHECKS = [
    ("results", "driver_id", "drivers", "driver_id", False),
    ("results", "constructor_id", "constructors", "constructor_id", True),
    ("qualifying", "driver_id", "drivers", "driver_id", False),
    ("qualifying", "constructor_id", "constructors", "constructor_id", True),
    ("sprint_results", "driver_id", "drivers", "driver_id", False),
    ("sprint_results", "constructor_id", "constructors", "constructor_id", True),
    ("driver_standings", "driver_id", "drivers", "driver_id", False),
    ("constructor_standings", "constructor_id", "constructors", "constructor_id", False),
    ("races", "circuit_id", "circuits", "circuit_id", True),
]
I11_SEASON_TABLES = ["results", "qualifying", "sprint_results",
                     "driver_standings", "constructor_standings", "races"]
I11_RACE_TABLES = ["results", "qualifying", "sprint_results"]


def _i11_v(scope, items):
    """I11 violation：指紋鎖**全集** sha256（Sol S1，不因前 50 截斷而漏掉第 51 個換人）；
    human sample 另放 sample 欄、不影響指紋覆蓋（sha256 已蓋全集）。"""
    detail = {"orphans": _set_hash(items), "sample": sorted(items)[:50]}
    return _v("I11", scope, detail)


def inv_I11(cur):
    out = []
    for tbl, col, ref_tbl, ref_col, nullable in I11_CHECKS:
        null_ok = f" AND t.{col} IS NOT NULL" if nullable else ""
        orphans = [str(r[0]) for r in cur.execute(
            f"SELECT DISTINCT t.{col} FROM {tbl} t "
            f"LEFT JOIN {ref_tbl} r ON r.{ref_col}=t.{col} "
            f"WHERE r.{ref_col} IS NULL{null_ok}")]
        if orphans:
            out.append(_i11_v({"table": tbl, "column": col, "ref": ref_tbl}, orphans))
    for tbl in I11_SEASON_TABLES:
        orphans = [str(r[0]) for r in cur.execute(
            f"SELECT DISTINCT t.season FROM {tbl} t "
            f"LEFT JOIN seasons s ON s.year=t.season WHERE s.year IS NULL")]
        if orphans:
            out.append(_i11_v({"table": tbl, "column": "season", "ref": "seasons"}, orphans))
    for tbl in I11_RACE_TABLES:
        pairs = [[r[0], r[1]] for r in cur.execute(
            f"SELECT DISTINCT t.season, t.round FROM {tbl} t "
            f"LEFT JOIN races x ON x.season=t.season AND x.round=t.round WHERE x.season IS NULL")]
        if pairs:
            out.append(_i11_v({"table": tbl, "column": "season_round", "ref": "races"}, pairs))
    return out


# --- I12：賽季宇宙覆蓋（Terra 盲測缺口——整季消失時 I1–I11 迭代宇宙空轉全綠） ---

# 以 seasons 為宇宙必須逐季覆蓋的表；constructor_standings 只要求 >=1958（車隊冠軍
# 1958 年才設立，1950–57 沒有是史實不是缺漏）。qualifying/sprint_results 不納入
# （已知殘缺覆蓋：qualifying 1994 起才有——照 I5_UNCOVERED_FIELDS 的誠實精神不假裝）。
I12_COVERAGE_TABLES = [
    ("races", 1950),
    ("results", 1950),
    ("driver_standings", 1950),
    ("constructor_standings", 1958),
]


def inv_I12(cur):
    """賽季宇宙覆蓋（Terra 盲測缺口修補）。

    I1–I11 全部以「被檢查表裡**實際出現**的賽季」當迭代宇宙（_seasons / _races_with_results /
    races 表）——整季資料消失時迴圈直接空轉、檢查全綠。I12 反過來以 seasons 表為錨點宇宙：
      ① 錨點連續性：seasons.year 集合必須恰好等於 range(1950, max+1) 的連續整數（現況
         1950–2026 共 77 季）。缺年、重複、或 min != 1950 都產 violation。這條保護宇宙錨點本身。
      ② 各表覆蓋：以 seasons 表為宇宙，每一季必須出現在 races / results / driver_standings；
         constructor_standings 只要求 season >= 1958。
    """
    out = []
    years = [r[0] for r in cur.execute("SELECT year FROM seasons ORDER BY year")]
    got = set(years)
    # ① 錨點連續性（seasons 錨點本身；空表＝宇宙塌陷也產 violation）
    if not years:
        out.append(_v("I12", {"kind": "anchor"},
                      {"missing_years": [], "unexpected_years": [],
                       "has_duplicates": False, "min": None, "max": None, "empty": True}))
    else:
        expected = set(range(1950, max(years) + 1))
        if got != expected or len(years) != len(got) or min(years) != 1950:
            out.append(_v("I12", {"kind": "anchor"},
                          {"missing_years": sorted(expected - got),
                           "unexpected_years": sorted(got - expected),
                           "has_duplicates": len(years) != len(got),
                           "min": min(years), "max": max(years), "empty": False}))
    # ② 各表覆蓋（以 seasons 為宇宙，任何整季缺席都被抓）
    for tbl, since in I12_COVERAGE_TABLES:
        present = {r[0] for r in cur.execute(f"SELECT DISTINCT season FROM {tbl}")}
        missing = sorted({y for y in got if y >= since} - present)
        if missing:
            out.append(_v("I12", {"table": tbl},
                          {"missing_seasons": _set_hash(missing), "sample": missing[:50]}))
    return out


ALL_INVARIANTS = [inv_I1, inv_I2, inv_I3, inv_I4, inv_I5, inv_I6,
                  inv_I7, inv_I8, inv_I9, inv_I10, inv_I11, inv_I12]


# ---------------------------------------------------------------------------
# 對照 known_exceptions（三元組 = scope_key + fingerprint）
# ---------------------------------------------------------------------------

def load_declared(path=EXCEPTIONS):
    if not pathlib.Path(path).exists():
        return []
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8")).get("exceptions", [])


def _all_failures(cur):
    failures, per_inv = [], {}
    for fn in ALL_INVARIANTS:
        vs = fn(cur)
        per_inv[fn.__name__.replace("inv_", "")] = len(vs)
        failures.extend(vs)
    return failures, per_inv


# Sol S0：matched 例外必備且非空的核准 metadata（缺一即整體 FAIL）
REQUIRED_APPROVAL_FIELDS = ("approved_by", "approved_date", "reason", "evidence")


def _empty(val):
    """視為空：None、空字串、只有空白的字串。"""
    return val is None or (isinstance(val, str) and not val.strip()) or val == ""


# Sol 終輪 S1-2：宣告清單建 dict 前必須先 fail-closed 驗證的結構欄位
REQUIRED_DECL_FIELDS = ("id", "invariant", "scope", "status", "fingerprint")


def _decl_field_missing(e, f):
    v = e.get(f)
    if f == "scope":
        return not isinstance(v, dict) or not v   # scope 必須是非空 dict
    return _empty(v)


def _declared_triple(e):
    return _scope_key(e["invariant"], e["scope"]) + "@" + (e.get("fingerprint") or "<unsealed>")


def validate_declarations(declared):
    """建 declared_map 前 fail-closed 驗證（Sol 終輪 S1-2）。

    dict 會把同 triple 的重複宣告靜默折疊——Sol 反證：39 條前插一條同 triple 的
    pending_review，後面的 approved 覆寫它，輸入 40 條卻只報 39、gate PASS。修法：
    ①缺 required 欄位＝fault（不得跳過）②id 重複＝fault ③triple 重複＝fault
    ④輸入條數 != 納入 dict 條數＝fault。任一 fault → 整體 FAIL。
    """
    faults = []
    id_idx, triple_idx = {}, {}
    for i, e in enumerate(declared):
        missing = [f for f in REQUIRED_DECL_FIELDS if _decl_field_missing(e, f)]
        if missing:
            faults.append({"index": i, "id": e.get("id"),
                           "problem": f"缺 required 欄位 {missing}"})
            continue   # 缺結構欄位無法可靠構成 triple，記 fault 後不納入唯一性統計
        id_idx.setdefault(e["id"], []).append(i)
        triple_idx.setdefault(_declared_triple(e), []).append(i)
    for _id, idxs in sorted(id_idx.items()):
        if len(idxs) > 1:
            faults.append({"id": _id, "problem": f"重複 id（宣告 index {idxs}）"})
    for t, idxs in sorted(triple_idx.items()):
        if len(idxs) > 1:
            faults.append({"triple": t, "problem": f"重複 triple（宣告 index {idxs}）"})
    # ④ 折疊偵測：輸入條數 != 建 dict 後納入條數
    included = len({_declared_triple(e) for e in declared
                    if not any(_decl_field_missing(e, f) for f in REQUIRED_DECL_FIELDS)})
    valid_input = sum(1 for e in declared
                      if not any(_decl_field_missing(e, f) for f in REQUIRED_DECL_FIELDS))
    if included != valid_input:
        faults.append({"problem": f"輸入 {valid_input} 條有效宣告但納入 dict 僅 {included} 條"
                                  "（重複 triple 被折疊）"})
    return faults


def run(cur, declared):
    """核心判定：actual 三元組集合 == declared 三元組集合 → passed。"""
    failures, per_inv = _all_failures(cur)
    actual = {v["triple"]: v for v in failures}
    schema_faults = validate_declarations(declared)   # Sol S1-2：建 dict 前 fail-closed
    declared_map = {_declared_triple(e): e for e in declared}

    unexpected_keys = sorted(set(actual) - set(declared_map))
    missing_keys = sorted(set(declared_map) - set(actual))
    matched_keys = sorted(set(actual) & set(declared_map))

    declared_scopes = {}
    for e in declared:
        declared_scopes.setdefault(_scope_key(e["invariant"], e["scope"]), []).append(e)
    fingerprint_mismatch = []
    for k in unexpected_keys:
        v = actual[k]
        if v["scope_key"] in declared_scopes:
            fingerprint_mismatch.append({
                "invariant": v["invariant"], "scope": v["scope"], "scope_key": v["scope_key"],
                "actual_fingerprint": v["fingerprint"],
                "declared_fingerprints": [e.get("fingerprint") for e in declared_scopes[v["scope_key"]]],
                "detail": v["detail"]})

    pending = sorted(k for k in matched_keys
                     if declared_map[k].get("status") == "pending_review")
    unsealed = sorted(e.get("id") for e in declared if not e.get("fingerprint"))

    # Sol S0：核准進 gate——每條 matched 例外必須 status=approved 且五欄非空，否則整體 FAIL
    unapproved = []
    for k in matched_keys:
        e = declared_map[k]
        problems = []
        if e.get("status") != "approved":
            problems.append(f"status={e.get('status')!r}(需 approved)")
        for f in REQUIRED_APPROVAL_FIELDS:
            if _empty(e.get(f)):
                problems.append(f"{f} 缺失/空")
        if problems:
            unapproved.append({"id": e.get("id"), "invariant": e["invariant"],
                               "scope": e["scope"], "problems": problems})

    return {
        "passed": (not unexpected_keys and not missing_keys and not unapproved
                   and not schema_faults),
        "summary": {
            "total_failures": len(actual),
            "declared_input": len(declared),
            "declared_exceptions": len(declared_map),
            "matched": len(matched_keys),
            "unexpected_failures": len(unexpected_keys),
            "missing_declarations": len(missing_keys),
            "fingerprint_mismatches": len(fingerprint_mismatch),
            "unapproved_matched": len(unapproved),
            "declaration_schema_faults": len(schema_faults),
            "pending_review": len(pending),
            "unsealed_declarations": len(unsealed),
        },
        "unexpected_failures": [actual[k] for k in unexpected_keys],
        "missing_declarations": [{"triple": k, **declared_map[k]} for k in missing_keys],
        "fingerprint_mismatches": fingerprint_mismatch,
        "unapproved_matched": unapproved,
        "declaration_schema_faults": schema_faults,
        "matched": [{"invariant": actual[k]["invariant"], "scope": actual[k]["scope"],
                     "declared_reason": declared_map[k].get("reason"),
                     "declared_status": declared_map[k].get("status"),
                     "detail": actual[k]["detail"]} for k in matched_keys],
        "per_invariant_failure_counts": per_inv,
        "i5_uncovered_fields": list(I5_UNCOVERED_FIELDS),
    }


def seal(cur, exceptions_path):
    """從現況一次性把指紋寫回 known_exceptions.json（只新增 fingerprint 欄，其餘保留）。

    每條例外用 (invariant, scope) 對上實際失敗，寫入其 fingerprint。對不上的宣告→拒絕
    （過期宣告不得留）；有失敗但沒宣告→拒絕（未宣告失敗不得靜默 seal）。
    """
    doc = json.loads(pathlib.Path(exceptions_path).read_text(encoding="utf-8"))
    exceptions = doc.get("exceptions", [])
    failures, _ = _all_failures(cur)
    by_scope = {v["scope_key"]: v for v in failures}
    declared_scopes = {_scope_key(e["invariant"], e["scope"]) for e in exceptions}

    stale = [e["id"] for e in exceptions
             if _scope_key(e["invariant"], e["scope"]) not in by_scope]
    undeclared = sorted(sk for sk in by_scope if sk not in declared_scopes)
    if stale:
        raise SystemExit(f"❌ seal 拒絕：{len(stale)} 條過期宣告（無對應失敗）：{stale}")
    if undeclared:
        raise SystemExit(f"❌ seal 拒絕：{len(undeclared)} 個未宣告失敗：{undeclared}")

    for e in exceptions:
        v = by_scope[_scope_key(e["invariant"], e["scope"])]
        new, inserted = {}, False
        for k, val in e.items():
            if k == "fingerprint":
                continue
            new[k] = val
            if k == "evidence":
                new["fingerprint"] = v["fingerprint"]
                inserted = True
        if not inserted:
            new["fingerprint"] = v["fingerprint"]
        e.clear()
        e.update(new)
    pathlib.Path(exceptions_path).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(exceptions)


def _print_human(rep):
    s = rep["summary"]
    print("=" * 70)
    print("F1 不變量檢查（規則：失敗三元組集合＝宣告三元組集合，指紋綁定）")
    print("=" * 70)
    print("各不變量失敗數：")
    for k in ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9", "I10", "I11", "I12"):
        print(f"  {k:4s} {rep['per_invariant_failure_counts'].get(k, 0)}")
    print(f"\n總失敗 {s['total_failures']}　宣告例外 {s['declared_exceptions']}　匹配 {s['matched']}")
    print(f"未宣告失敗 {s['unexpected_failures']}　過期宣告 {s['missing_declarations']}　"
          f"指紋不符 {s['fingerprint_mismatches']}　未核准例外 {s['unapproved_matched']}　"
          f"宣告 schema 錯 {s['declaration_schema_faults']}　"
          f"未封印宣告 {s['unsealed_declarations']}　待審核 {s['pending_review']}")
    if rep["declaration_schema_faults"]:
        print("\n🔴 宣告清單 schema/唯一性錯（Sol S1-2：重複 triple 會被 dict 靜默折疊）：")
        for v in rep["declaration_schema_faults"]:
            print(f"    {v}")
    if rep["unapproved_matched"]:
        print("\n🔴 已匹配但未核准/缺 metadata 的例外（Sol S0：未核准不得漂白失敗）：")
        for v in rep["unapproved_matched"]:
            print(f"    {v['id']} {v['invariant']} {v['scope']} → {v['problems']}")
    if rep["fingerprint_mismatches"]:
        print("\n🔴 指紋不符（宣告範圍內數值/成員被竄改——這正是 S0-1 要擋的漂白）：")
        for v in rep["fingerprint_mismatches"]:
            print(f"    {v['invariant']} {v['scope']} → {v['detail']}")
    mismatch_scopes = {v["scope_key"] for v in rep["fingerprint_mismatches"]}
    other_unexpected = [v for v in rep["unexpected_failures"] if v["scope_key"] not in mismatch_scopes]
    if other_unexpected:
        print("\n🔴 未宣告的新失敗（未解——先查歷史原因，別塞進例外漂白）：")
        for v in other_unexpected:
            print(f"    {v['invariant']} {v['scope']} → {v['detail']}")
    if rep["missing_declarations"]:
        print("\n⚠️  宣告了卻沒發生的例外（過期或指紋過時）：")
        for v in rep["missing_declarations"]:
            print(f"    {v.get('id')} {v['invariant']} {v['scope']}")
    print("\nI5 未涵蓋欄位（不假裝比對）：", "、".join(rep["i5_uncovered_fields"]))
    print("\n" + ("✅ 通過：失敗三元組集合恰好等於宣告三元組集合。"
                  if rep["passed"] else "❌ 未通過：三元組集合不匹配。"))
    if s["unsealed_declarations"]:
        print(f"（{s['unsealed_declarations']} 條宣告尚未封印指紋，請先跑 --seal）")
    if s["pending_review"]:
        print(f"（{s['pending_review']} 條仍 pending_review，本腳本不做核准。）")


def main():
    ap = argparse.ArgumentParser(description="I1–I12 不變量檢查（指紋綁定）vs known_exceptions")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--exceptions", default=str(EXCEPTIONS))
    ap.add_argument("--json", help="另存結構化報告")
    ap.add_argument("--seal", action="store_true",
                    help="一次性把現況指紋寫回 known_exceptions.json（只新增 fingerprint 欄）")
    a = ap.parse_args()
    con = _ensure_db(a.db)
    try:
        cur = con.cursor()
        if a.seal:
            n = seal(cur, a.exceptions)
            print(f"✅ 已封印 {n} 條例外的指紋 → {a.exceptions}")
            return 0
        rep = run(cur, load_declared(a.exceptions))
    finally:
        con.close()
    if a.json:
        pathlib.Path(a.json).write_text(
            json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_human(rep)
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
