#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 實體層（L1 sqlite + 不變量）回歸測試。

鎖四件事：
  1. build-f1-db 決定性——連建兩次，.dump 必須逐 byte 相同。
  2. oracle 對數——十個表的筆數／季數必須等於 API total（唯一真 oracle）。
  3. 兩個坑——DNF 的 position 有值但 position_text 非 '1'；points 是 REAL 存得下 .5。
  4. 不變量機制本身——尤其是**反向測試**：失敗集合與宣告例外集合不匹配時
     （少宣告一條、或多宣告一條）必須整體 fail，不是「有過就好」。

跑法：python3 -m unittest discover -s tests
"""
import importlib.util
import pathlib
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
    import shutil
    shutil.rmtree(_SHARED_DIR, ignore_errors=True)


def _dump(db_path):
    con = sqlite3.connect(str(db_path))
    try:
        return "\n".join(con.iterdump())
    finally:
        con.close()


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
    def test_two_builds_are_byte_identical_dump(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            a, b = tmp / "a.sqlite", tmp / "b.sqlite"
            bdb.build(str(a))
            bdb.build(str(b))
            self.assertEqual(_dump(a), _dump(b),
                             "兩次建置的 .dump 不一致——L1 不可重現")
        finally:
            import shutil
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
        # 型別確認：Ascari 1953 半分賽季，某列 points 帶 .5
        sample = self.con.execute(
            "SELECT points FROM results WHERE points=4.5 LIMIT 1").fetchone()
        self.assertIsNotNone(sample)
        self.assertIsInstance(sample[0], float)


class InvariantMechanismTests(unittest.TestCase):
    """不變量檢查機制本身——重點在反向測試（失敗集合≠宣告集合必須 fail）。"""

    def setUp(self):
        self.con = sqlite3.connect(str(_SHARED_DB))
        self.cur = self.con.cursor()
        self.declared = inv.load_declared()   # 真實 known_exceptions.json

    def tearDown(self):
        self.con.close()

    def test_real_failure_set_equals_declared_set(self):
        rep = inv.run(self.cur, self.declared)
        self.assertTrue(rep["passed"],
                        f"未預期失敗={rep['unexpected_failures']} 過期宣告={rep['missing_declarations']}")
        self.assertEqual(rep["summary"]["unexpected_failures"], 0)
        self.assertEqual(rep["summary"]["missing_declarations"], 0)
        self.assertGreater(rep["summary"]["matched"], 0)

    def test_dropping_one_declaration_makes_it_fail(self):
        """反向①：少宣告一條 → 出現未宣告失敗 → 整體 fail。"""
        fewer = self.declared[1:]              # 拿掉第一條
        rep = inv.run(self.cur, fewer)
        self.assertFalse(rep["passed"])
        self.assertEqual(rep["summary"]["unexpected_failures"], 1)

    def test_adding_bogus_declaration_makes_it_fail(self):
        """反向②：宣告一條沒發生的例外 → 過期宣告 → 整體 fail。"""
        bogus = self.declared + [{
            "id": "EX-BOGUS", "invariant": "I2", "scope": {"season": 1999},
            "reason": "不存在的失敗", "status": "pending_review"}]
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
        """鎖住失敗分布，防某個不變量被無聲改壞（例如 I4/I8 應恆為 0）。"""
        rep = inv.run(self.cur, self.declared)
        c = rep["per_invariant_failure_counts"]
        self.assertEqual(c["I1"], 0)
        self.assertEqual(c["I4"], 0)   # 雙路徑一致
        self.assertEqual(c["I5"], 0)
        self.assertEqual(c["I8"], 0)   # status.json 獨立 oracle 一致
        self.assertEqual(c["I2"], 3)   # shared drives
        self.assertEqual(c["I9"], 3)   # Indy 500 1958–60


class InvariantDetectionTests(unittest.TestCase):
    """把違規注入一顆合成 db，確認對應不變量真的抓得到（不是永遠回綠）。"""

    def _mini(self):
        con = sqlite3.connect(":memory:")
        con.executescript(bdb.SCHEMA)
        return con

    def test_I1_detects_duplicated_standings_position(self):
        con = self._mini()
        con.executemany(
            "INSERT INTO driver_standings VALUES (?,?,?,?,?,?,?)",
            [(2050, 1, "1", 10.0, 1, "a", ""),
             (2050, 1, "1", 10.0, 0, "b", "")])   # 兩個 position=1 → I1 應抓到
        rep = inv.run(con.cursor(), [])
        keys = [v["invariant"] for v in rep["unexpected_failures"]]
        self.assertIn("I1", keys)
        con.close()

    def test_I5_detects_aggregate_column_on_entity_table(self):
        """若 drivers 表被塞進 career_wins 這種跨季聚合欄，I5 必須抓到。"""
        con = sqlite3.connect(":memory:")
        # 故意建一個帶違規欄的 drivers 表
        con.execute("CREATE TABLE drivers (driver_id TEXT PRIMARY KEY, career_wins INTEGER)")
        con.execute("CREATE TABLE driver_standings (season INT, position INT, "
                    "position_text TEXT, points REAL, wins INT, driver_id TEXT, constructor_ids TEXT)")
        con.execute("CREATE TABLE seasons (year INT, url TEXT, status TEXT)")
        con.execute("CREATE TABLE constructors (constructor_id TEXT)")
        con.execute("CREATE TABLE circuits (circuit_id TEXT)")
        con.execute("CREATE TABLE results (season INT, round INT, position_text TEXT, "
                    "points REAL, driver_id TEXT, status TEXT)")
        con.execute("CREATE TABLE sprint_results (season INT, round INT, driver_id TEXT, points REAL)")
        con.execute("CREATE TABLE constructor_standings (season INT, wins INT, constructor_id TEXT, position INT)")
        con.execute("CREATE TABLE races (season INT, round INT)")
        con.execute("CREATE TABLE qualifying (season INT, round INT)")
        vs = inv.inv_I5(con.cursor())
        self.assertTrue(any(v["invariant"] == "I5" and "career_wins" in
                            v["detail"].get("unexpected_aggregate_columns", [])
                            for v in vs))
        con.close()


if __name__ == "__main__":
    unittest.main()
