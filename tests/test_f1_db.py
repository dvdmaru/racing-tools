#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 實體層（L1 sqlite + 不變量）回歸測試。

鎖的東西：
  1. build-f1-db 決定性——**同一 Python/SQLite/OS runtime** 下連建兩次，SQLite 檔 bytes
     與 dump 皆逐 byte 相同（不宣稱跨平台/跨版本；Sol S2-1）。`Connection.iterdump()`
     是 `sqlite3 db.sqlite .dump` CLI 的 Python 等價物，文件與測試統一用它。
  2. oracle 對數——十個表的筆數／季數必須等於 API total（唯一真 oracle）。
  3. 兩個坑——DNF 的 position 有值但 position_text 非 '1'；points 是 REAL 存得下 .5。
  4. 不變量機制本身——反向測試（失敗集合≠宣告集合必須整體 fail）＋指紋綁定：
     宣告範圍內的數值/成員被竄改（Sol S0-1 的 +1000）必須被指紋不符擋下。
  5. Sol 查核桌兩個 false-green 反例做成 regression：
     ① 1950 某列 points +1000 → 指紋不符 → FAIL；② 2026 R10 driver_id 改孤兒 → I11 → FAIL。
  6. I5 真雙路徑（f1stats 發布 vs db SQL）與 I11 referential integrity 真的抓得到錯。

跑法：python3 -m unittest discover -s tests
"""
import copy
import importlib.util
import pathlib
import shutil
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bdb = _load("build_f1_db", "build-f1-db.py")
inv = _load("check_f1_invariants", "check-f1-invariants.py")

# 全模組共用一顆 db，避免每個 test 重建（建置約數秒）。
_SHARED_DIR = None
_SHARED_DB = None


def setUpModule():
    global _SHARED_DIR, _SHARED_DB
    _SHARED_DIR = pathlib.Path(tempfile.mkdtemp())
    _SHARED_DB = _SHARED_DIR / "shared.sqlite"
    bdb.build(str(_SHARED_DB))


def tearDownModule():
    shutil.rmtree(_SHARED_DIR, ignore_errors=True)


def _dump(db_path):
    con = sqlite3.connect(str(db_path))
    try:
        return "\n".join(con.iterdump())
    finally:
        con.close()


def _mutated_copy(mutate):
    """複製共用 db 到 tmp、套用 mutate(cursor)、回傳新路徑（呼叫端自清）。"""
    tmp = pathlib.Path(tempfile.mkdtemp())
    dbp = tmp / "m.sqlite"
    shutil.copy2(_SHARED_DB, dbp)
    con = sqlite3.connect(str(dbp))
    try:
        mutate(con)
        con.commit()
    finally:
        con.close()
    return tmp, dbp


class OracleCountTests(unittest.TestCase):
    """API total 是唯一真 oracle；每個表對上它才算 backfill 完整。"""

    ORACLE = {
        "seasons": 77, "circuits": 78, "drivers": 881, "constructors": 214,
        "races": 1171, "results": 26093, "qualifying": 11190,
        "sprint_results": 568,
    }

    def setUp(self):
        self.con = sqlite3.connect(str(_SHARED_DB))

    def tearDown(self):
        self.con.close()

    def test_table_counts_match_oracle(self):
        for tbl, expected in self.ORACLE.items():
            got = self.con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
            self.assertEqual(got, expected, f"{tbl}: {got} != oracle {expected}")

    def test_standings_season_counts(self):
        d = self.con.execute("SELECT count(DISTINCT season) FROM driver_standings").fetchone()[0]
        c = self.con.execute("SELECT count(DISTINCT season) FROM constructor_standings").fetchone()[0]
        self.assertEqual(d, 77)   # 車手榜 1950–2026
        self.assertEqual(c, 69)   # 車廠榜 1958–2026（前八季無車廠錦標賽）


class DeterminismTests(unittest.TestCase):
    """限縮宣稱：同 runtime 決定性（Sol S2-1）。不主張跨 Python/SQLite/OS byte 重現。"""

    def test_two_builds_byte_identical_same_runtime(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            a, b = tmp / "a.sqlite", tmp / "b.sqlite"
            bdb.build(str(a))
            bdb.build(str(b))
            # ① SQLite 檔本身逐 byte 相同
            self.assertEqual(a.read_bytes(), b.read_bytes(),
                             "同 runtime 兩次建置的 SQLite 檔 bytes 不一致")
            # ② dump（iterdump == sqlite3 .dump 的 Python 等價物）逐 byte 相同
            self.assertEqual(_dump(a), _dump(b), "同 runtime 兩次建置的 dump 不一致")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PitfallTests(unittest.TestCase):
    """計畫 §三／§十二 明列的兩個坑，直接對 db 斷言。"""

    def setUp(self):
        self.con = sqlite3.connect(str(_SHARED_DB))

    def tearDown(self):
        self.con.close()

    def test_dnf_keeps_position_but_position_text_marks_retirement(self):
        """坑 A：DNF 車手 position（分類名次）仍有值，position_text 才是 'R'。"""
        n = self.con.execute(
            "SELECT count(*) FROM results WHERE position_text='R' AND position IS NOT NULL"
        ).fetchone()[0]
        self.assertGreater(n, 0, "應存在 position 有值但 position_text='R' 的退賽列")

    def test_win_defined_by_position_text_not_position(self):
        """勝場一律以 position_text='1' 計；用 position=1 會混入 DNF 分類第一。"""
        by_text = self.con.execute(
            "SELECT count(*) FROM results WHERE position_text='1'").fetchone()[0]
        # 1159 場正賽 + 3 個 shared drive 額外勝場列 = 1162
        self.assertEqual(by_text, 1162)

    def test_points_are_real_and_store_fractions(self):
        """坑 B：1950 年代 shared drive 有 .5 分，INTEGER 會截斷。"""
        frac = self.con.execute(
            "SELECT count(*) FROM results WHERE points != cast(points AS INTEGER)"
        ).fetchone()[0]
        self.assertGreater(frac, 0, "應存在帶小數的 points（shared drive .5）")
        sample = self.con.execute(
            "SELECT points FROM results WHERE points=4.5 LIMIT 1").fetchone()
        self.assertIsNotNone(sample)
        self.assertIsInstance(sample[0], float)


class InvariantMechanismTests(unittest.TestCase):
    """不變量檢查機制本身——反向測試（失敗集合≠宣告集合必須 fail）。"""

    def setUp(self):
        self.con = sqlite3.connect(str(_SHARED_DB))
        self.cur = self.con.cursor()
        self.declared = inv.load_declared()   # 真實（已封印指紋的）known_exceptions.json

    def tearDown(self):
        self.con.close()

    def test_declared_file_is_sealed(self):
        """known_exceptions.json 必須已封印指紋（否則指紋防線失效）。"""
        self.assertTrue(self.declared, "known_exceptions.json 沒有例外")
        self.assertTrue(all(e.get("fingerprint") for e in self.declared),
                        "有例外未封印 fingerprint——請跑 check-f1-invariants.py --seal")

    def test_real_failure_set_equals_declared_set(self):
        rep = inv.run(self.cur, self.declared)
        self.assertTrue(rep["passed"],
                        f"未預期失敗={rep['unexpected_failures']} 過期宣告={rep['missing_declarations']}")
        self.assertEqual(rep["summary"]["unexpected_failures"], 0)
        self.assertEqual(rep["summary"]["missing_declarations"], 0)
        self.assertEqual(rep["summary"]["fingerprint_mismatches"], 0)
        self.assertEqual(rep["summary"]["unsealed_declarations"], 0)
        self.assertEqual(rep["summary"]["unapproved_matched"], 0)   # Sol S0
        self.assertGreater(rep["summary"]["matched"], 0)

    def test_status_downgraded_to_pending_review_fails(self):
        """Sol 覆核 S0 反例①：把一條已匹配例外的 status 改回 pending_review → 整體 FAIL。"""
        d = copy.deepcopy(self.declared)
        d[0]["status"] = "pending_review"
        rep = inv.run(self.cur, d)
        self.assertFalse(rep["passed"])
        self.assertEqual(rep["summary"]["unapproved_matched"], 1)

    def test_stripping_approval_metadata_fails(self):
        """Sol 覆核 S0 反例②：保留 scope+fingerprint，抽掉核准 metadata → 整體 FAIL。"""
        d = copy.deepcopy(self.declared)
        for f in ("approved_by", "approved_date", "reason", "evidence"):
            d[0].pop(f, None)
        rep = inv.run(self.cur, d)
        self.assertFalse(rep["passed"])
        self.assertEqual(rep["summary"]["unapproved_matched"], 1)
        self.assertEqual(len(rep["unapproved_matched"][0]["problems"]), 4)

    def test_blank_reason_fails(self):
        """核准五欄任一空白字串也算缺失（非空要求含 strip）。"""
        d = copy.deepcopy(self.declared)
        d[0]["reason"] = "   "
        rep = inv.run(self.cur, d)
        self.assertFalse(rep["passed"])
        self.assertEqual(rep["summary"]["unapproved_matched"], 1)

    def test_duplicate_triple_pending_then_approved_fails(self):
        """Sol 終輪 S1-2 反例：同 triple 放「pending 在前、approved 在後」，dict 折疊後
        舊版只報 39 條 PASS；validate_declarations 現在偵測重複 triple + 條數不符 → FAIL。"""
        dup = copy.deepcopy(self.declared[0])
        dup["status"] = "pending_review"          # 同 triple、狀態不同（放在最前面）
        d = [dup] + copy.deepcopy(self.declared)  # 輸入 40 條
        rep = inv.run(self.cur, d)
        self.assertFalse(rep["passed"])
        self.assertGreaterEqual(rep["summary"]["declaration_schema_faults"], 1)
        self.assertEqual(rep["summary"]["declared_input"], 40)

    def test_duplicate_id_fails(self):
        """兩條宣告共用同一個 id（triple 不同）也必須 FAIL。"""
        extra = copy.deepcopy(self.declared[1])
        extra["id"] = self.declared[0]["id"]      # 借用 EX-001 的 id
        d = copy.deepcopy(self.declared) + [extra]
        rep = inv.run(self.cur, d)
        self.assertFalse(rep["passed"])
        self.assertTrue(any("重複 id" in f.get("problem", "")
                            for f in rep["declaration_schema_faults"]))

    def test_declaration_missing_required_field_fails(self):
        """缺 required 欄位（如 fingerprint/status）的宣告不得被靜默跳過。"""
        d = copy.deepcopy(self.declared)
        d[0].pop("fingerprint", None)
        rep = inv.run(self.cur, d)
        self.assertFalse(rep["passed"])
        self.assertTrue(any("缺 required" in f.get("problem", "")
                            for f in rep["declaration_schema_faults"]))

    def test_dropping_one_declaration_makes_it_fail(self):
        """反向①：少宣告一條 → 出現未宣告失敗 → 整體 fail。"""
        fewer = self.declared[1:]
        rep = inv.run(self.cur, fewer)
        self.assertFalse(rep["passed"])
        self.assertEqual(rep["summary"]["unexpected_failures"], 1)

    def test_adding_bogus_declaration_makes_it_fail(self):
        """反向②：宣告一條沒發生的例外 → 過期宣告 → 整體 fail。"""
        bogus = self.declared + [{
            "id": "EX-BOGUS", "invariant": "I2", "scope": {"season": 1999},
            "fingerprint": "0" * 64, "reason": "不存在的失敗", "status": "approved"}]
        rep = inv.run(self.cur, bogus)
        self.assertFalse(rep["passed"])
        self.assertEqual(rep["summary"]["missing_declarations"], 1)

    def test_empty_declarations_flags_all_failures_as_unexpected(self):
        """完全不宣告 → 全部 39 條都是未宣告失敗。"""
        rep = inv.run(self.cur, [])
        self.assertFalse(rep["passed"])
        self.assertEqual(rep["summary"]["unexpected_failures"], rep["summary"]["total_failures"])
        self.assertEqual(rep["summary"]["total_failures"], 39)

    def test_expected_per_invariant_failure_counts(self):
        """鎖住失敗分布，防某個不變量被無聲改壞（I1/I4/I5/I8/I11 應恆為 0）。"""
        rep = inv.run(self.cur, self.declared)
        c = rep["per_invariant_failure_counts"]
        self.assertEqual(c["I1"], 0)
        self.assertEqual(c["I4"], 0)    # 雙查詢路徑一致
        self.assertEqual(c["I5"], 0)    # f1stats vs db 雙路徑一致
        self.assertEqual(c["I8"], 0)    # status.json 獨立查詢路徑一致
        self.assertEqual(c["I11"], 0)   # 零孤兒外鍵
        self.assertEqual(c["I2"], 3)    # shared drives
        self.assertEqual(c["I6"], 27)   # dropped scores 1950–1990
        self.assertEqual(c["I9"], 3)    # Indy 500 1958–60


class SolReproRegressionTests(unittest.TestCase):
    """Sol 查核桌兩個 false-green 反例——修正後必須 FAIL（防回歸）。"""

    def test_i6_points_plus_1000_now_fails_on_fingerprint(self):
        """S0-1 反例①：1950 某列 points +1000，舊版命中同 scope 全綠；現在指紋不符 FAIL。"""
        def mut(con):
            rid = con.execute("SELECT id FROM results WHERE season=1950 AND points>0 "
                              "ORDER BY id LIMIT 1").fetchone()[0]
            con.execute("UPDATE results SET points=points+1000 WHERE id=?", (rid,))
        tmp, dbp = _mutated_copy(mut)
        try:
            con = sqlite3.connect(str(dbp))
            rep = inv.run(con.cursor(), inv.load_declared())
            con.close()
            self.assertFalse(rep["passed"])
            self.assertGreaterEqual(rep["summary"]["fingerprint_mismatches"], 1)
            self.assertTrue(any(m["scope"] == {"season": 1950}
                                for m in rep["fingerprint_mismatches"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_i6_tiny_epsilon_change_fails_no_round(self):
        """Sol 覆核 S1 反例：舊版 round(6) 讓 6.0→6.0000001 同指紋全綠；
        移除 round 後，1e-7 級變動也會改指紋 → FAIL。"""
        def mut(con):
            row = con.execute("SELECT id, points FROM results WHERE season=1950 AND points>0 "
                              "ORDER BY id LIMIT 1").fetchone()
            con.execute("UPDATE results SET points=? WHERE id=?", (row[1] + 1e-7, row[0]))
        tmp, dbp = _mutated_copy(mut)
        try:
            con = sqlite3.connect(str(dbp))
            rep = inv.run(con.cursor(), inv.load_declared())
            con.close()
            self.assertFalse(rep["passed"])
            self.assertGreaterEqual(rep["summary"]["fingerprint_mismatches"], 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_orphan_driver_now_fails_on_I11(self):
        """S1-1 反例②：2026 R10 一列 driver_id 改成不存在實體，現在 I11 抓到 FAIL。"""
        def mut(con):
            rid = con.execute(
                "SELECT id FROM results WHERE season=2026 AND round=10 AND points=0 "
                "AND position_text NOT IN ('1','2','3') ORDER BY id DESC LIMIT 1").fetchone()[0]
            con.execute("UPDATE results SET driver_id='__orphan_driver__' WHERE id=?", (rid,))
        tmp, dbp = _mutated_copy(mut)
        try:
            con = sqlite3.connect(str(dbp))
            rep = inv.run(con.cursor(), inv.load_declared())
            con.close()
            self.assertFalse(rep["passed"])
            self.assertEqual(rep["per_invariant_failure_counts"]["I11"], 1)
            self.assertTrue(any(v["invariant"] == "I11" and
                                "__orphan_driver__" in v["detail"].get("sample", [])
                                for v in rep["unexpected_failures"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class InvariantDetectionTests(unittest.TestCase):
    """把違規注入 db，確認對應不變量真的抓得到（不是永遠回綠）。"""

    def test_I1_detects_duplicated_standings_position(self):
        con = sqlite3.connect(":memory:")
        con.executescript(bdb.SCHEMA)
        con.executemany(
            "INSERT INTO driver_standings VALUES (?,?,?,?,?,?,?)",
            [(2050, 1, "1", 10.0, 1, "a", ""),
             (2050, 1, "1", 10.0, 0, "b", "")])   # 兩個 position=1 → I1 應抓到
        rep = inv.run(con.cursor(), [])
        self.assertIn("I1", [v["invariant"] for v in rep["unexpected_failures"]])
        con.close()

    def test_I5_dualpath_detects_missing_win_in_db(self):
        """S1-1：I5 現在是真雙路徑——刪掉 db 裡 Schumacher 一勝，f1stats(讀生涯檔)仍是 91，
        兩路徑不一致 → I5 抓到。舊版恆真式（同 SQL 比自己）抓不到。"""
        def mut(con):
            rid = con.execute("SELECT id FROM results WHERE driver_id='michael_schumacher' "
                              "AND position_text='1' ORDER BY id LIMIT 1").fetchone()[0]
            con.execute("UPDATE results SET position_text='2', position=2 WHERE id=?", (rid,))
        tmp, dbp = _mutated_copy(mut)
        try:
            con = sqlite3.connect(str(dbp))
            vs = inv.inv_I5(con.cursor())
            con.close()
            self.assertTrue(any(v["scope"].get("driver_id") == "michael_schumacher"
                                for v in vs), "I5 雙路徑應抓到 db 少一勝")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_I5_schema_check_detects_aggregate_column(self):
        """I5 結構面：drivers 表被塞進 career_wins 這種跨季聚合欄，必須抓到。"""
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE drivers (driver_id TEXT PRIMARY KEY, career_wins INTEGER)")
        con.execute("CREATE TABLE constructors (constructor_id TEXT)")
        con.execute("CREATE TABLE circuits (circuit_id TEXT)")
        con.execute("CREATE TABLE seasons (year INT, url TEXT, status TEXT)")
        vs = inv._i5_schema_check(con.cursor())
        self.assertTrue(any("career_wins" in v["detail"].get("unexpected_aggregate_columns", [])
                            for v in vs))
        con.close()

    def test_I11_detects_orphan_constructor(self):
        """I11：孤兒 constructor_id 必須抓到。"""
        con = sqlite3.connect(":memory:")
        con.executescript(bdb.SCHEMA)
        con.execute("INSERT INTO seasons VALUES (2050,'','completed')")
        con.execute("INSERT INTO races VALUES (2050,1,'X','2050-01-01','circ','')")
        con.execute("INSERT INTO circuits VALUES ('circ','C','L','Co',0.0,0.0,'')")
        con.execute("INSERT INTO drivers VALUES ('d','','','G','F','','','')")
        con.execute("INSERT INTO results VALUES "
                    "(1,2050,1,'1',1,'1',10.0,'d','__ghost_constructor__',1,10,'Finished')")
        vs = inv.inv_I11(con.cursor())
        self.assertTrue(any(v["invariant"] == "I11" and
                            "__ghost_constructor__" in v["detail"].get("sample", [])
                            for v in vs))
        con.close()


if __name__ == "__main__":
    unittest.main()
