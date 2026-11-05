#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""車手世界冠軍「封王即算」定義回歸測試（2026-11-03 Charlie 裁決）。

本站車手世界冠軍＝賽季已完成且車手榜第 1，**或**進行中賽季已在數學上封王。
判定只有一份：scripts/f1stats.py 的 driver_title_clinched()（純函式）＋兩條資料組裝路徑
（driver_title_clinched_json／driver_title_clinched_db）。這裡鎖：

- 純函式的陽性與陰性（剩餘場次調多、差距縮小、平手、只有一人上榜、負數場次）。
- 2026 真實資料：安東內利已封王，JSON 路徑與 DB 路徑結果一致。
- 已完成賽季的冠軍完全不變（35 位、每人次數與舊 SQL 定義逐一相同）。
- 車隊冠軍不變（進行中賽季的車隊榜首不計）。
- 不變量 I5 雙路徑在新定義下仍一致；全站冠軍 36 位在報告、圖、DB 一致。

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import math
import pathlib
import sqlite3
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "f1" / "db.sqlite"


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fs = _load("f1stats_title_clinch", "f1stats.py")
bf = _load("build_facts_title_clinch", "build-facts.py")

OLD_COMPLETED_SQL = ("SELECT ds.season, ds.driver_id FROM driver_standings ds "
                     "JOIN seasons s ON s.year=ds.season "
                     "WHERE ds.position=1 AND s.status='completed' ORDER BY ds.season, ds.driver_id")


class PureJudgementTests(unittest.TestCase):
    """driver_title_clinched()：保守判定，嚴格大於，平手不算。"""

    def test_points_table_comes_from_existing_table(self):
        self.assertEqual(fs._points_maxima(),
                         (max(bf.POINTS_RACE.values()), max(bf.POINTS_SPRINT.values())))
        self.assertEqual(fs._points_maxima(), (25, 8))

    def test_2026_after_r19_numbers_clinched(self):
        # 2026 R19 後：安東內利 380、維斯塔潘 261，剩 R20–R23 四站、無衝刺賽：261＋100＝361 < 380
        hit = fs.driver_title_clinched(
            [("antonelli", 380), ("max_verstappen", 261), ("hamilton", 259)], 4, 0)
        self.assertEqual(hit["driver_id"], "antonelli")
        self.assertEqual(hit["remaining_max"], 100)
        self.assertEqual(hit["rival_id"], "max_verstappen")
        self.assertEqual(hit["rival_points"] + hit["remaining_max"], 361)

    def test_more_remaining_races_not_clinched(self):
        # 陰性：同樣積分但剩 5 站 → 261＋125＝386 ≥ 380，追得上
        self.assertIsNone(fs.driver_title_clinched([("antonelli", 380), ("max_verstappen", 261)], 5, 0))

    def test_remaining_sprints_count(self):
        # 陰性：4 站正賽＋3 場衝刺賽 → 261＋100＋24＝385 ≥ 380
        self.assertIsNone(fs.driver_title_clinched([("antonelli", 380), ("max_verstappen", 261)], 4, 3))
        # 陽性：只多 2 場衝刺賽 → 261＋116＝377 < 380
        self.assertIsNotNone(fs.driver_title_clinched([("antonelli", 380), ("max_verstappen", 261)], 4, 2))

    def test_smaller_gap_not_clinched(self):
        self.assertIsNone(fs.driver_title_clinched([("antonelli", 350), ("max_verstappen", 261)], 4, 0))

    def test_tie_with_ceiling_not_clinched(self):
        # 平手（領先者＝對手全拿上限）不算；多 1 分才算
        self.assertIsNone(fs.driver_title_clinched([("a", 361), ("b", 261)], 4, 0))
        self.assertEqual(fs.driver_title_clinched([("a", 362), ("b", 261)], 4, 0)["driver_id"], "a")

    def test_tied_leaders_never_clinched(self):
        self.assertIsNone(fs.driver_title_clinched([("a", 100), ("b", 100)], 0, 0))

    def test_rival_is_best_other_regardless_of_order(self):
        hit = fs.driver_title_clinched([("c", 10), ("b", 200), ("a", 380)], 4, 0)
        self.assertEqual((hit["driver_id"], hit["rival_id"]), ("a", "b"))

    def test_lone_driver_still_compared_with_zero_plus_remaining(self):
        self.assertIsNone(fs.driver_title_clinched([("a", 100)], 4, 0))
        self.assertEqual(fs.driver_title_clinched([("a", 101)], 4, 0)["driver_id"], "a")
        self.assertIsNone(fs.driver_title_clinched([], 0, 0))

    def test_negative_remaining_rejected(self):
        with self.assertRaises(ValueError):
            fs.driver_title_clinched([("a", 1)], -1, 0)


@unittest.skipUnless(DB.exists(), "db.sqlite 不存在（先跑 build-f1-db.py）")
class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = fs.connect_db()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_2026_antonelli_clinched_both_paths_agree(self):
        j = fs.driver_title_clinched_json(2026)
        d = fs.driver_title_clinched_db(self.con, 2026)
        self.assertIsNotNone(j)
        self.assertEqual(j, d, "JSON 路徑與 DB 路徑的封王判定必須一致")
        self.assertEqual(j["driver_id"], "antonelli")
        self.assertGreater(j["points"], j["rival_points"] + j["remaining_max"])

    def test_2026_not_clinched_when_schedule_longer(self):
        # 陰性：把剩餘正賽加到足以追上（≥ 差距／25 站）→ 兩條路徑都不封王
        hit = fs.driver_title_clinched_json(2026)
        need = math.ceil((hit["points"] - hit["rival_points"]) / 25) - hit["remaining_races"]
        races, sprints = fs._schedule_rounds(2026)
        extra = {max(races) + i for i in range(1, need + 1)}
        orig = fs._schedule_rounds
        fs._schedule_rounds = lambda y: (races | extra, sprints) if y == 2026 else orig(y)
        try:
            self.assertIsNone(fs.driver_title_clinched_json(2026))
            self.assertIsNone(fs.driver_title_clinched_db(self.con, 2026))
            self.assertEqual(fs.driver_championships_db("antonelli", self.con)["value"], 0)
            self.assertEqual(fs.driver_championships("antonelli")["value"], 0)
        finally:
            fs._schedule_rounds = orig

    def test_missing_schedule_fails_closed(self):
        orig = fs._schedule_rounds
        fs._schedule_rounds = lambda y: None
        try:
            self.assertIsNone(fs.driver_title_clinched_json(2026))
            self.assertIsNone(fs.driver_title_clinched_db(self.con, 2026))
        finally:
            fs._schedule_rounds = orig

    def test_completed_seasons_unchanged(self):
        """已完成賽季：冠軍列與舊定義（completed 且 position=1）逐列相同；35 位、各人次數不變。"""
        old = [tuple(r) for r in self.con.execute(OLD_COMPLETED_SQL).fetchall()]
        rows = fs.driver_title_rows_db(self.con)
        self.assertEqual([(s, d) for s, d, _p, _w, c in rows if not c], old)
        self.assertEqual(len({d for _s, d in old}), 35)
        clinched = [(s, d) for s, d, _p, _w, c in rows if c]
        self.assertEqual(clinched, [(2026, "antonelli")])
        self.assertEqual(len({d for _s, d, *_ in rows}), 36)
        # 各人次數（舊定義）＝新定義去掉封王季
        for did in {d for _s, d in old}:
            want = [s for s, d in old if d == did]
            got = [x["season"] for x in fs.driver_championships_db(did, self.con)["detail"]
                   if not x.get("clinched")]
            self.assertEqual(got, want, did)

    def test_antonelli_championship_both_paths(self):
        db = fs.driver_championships_db("antonelli", self.con)
        js = fs.driver_championships("antonelli")
        self.assertEqual(db["formula"], fs.DRIVER_TITLE_FORMULA)
        self.assertEqual([x["season"] for x in db["detail"]], [2026])
        self.assertEqual([x["season"] for x in js["detail"]], [2026])
        self.assertTrue(db["detail"][0]["clinched"])
        self.assertTrue(js["detail"][0]["clinched"])
        # as_of 截斷粒度是賽季：as_of 落在 2025 → 不含 2026
        self.assertEqual(fs.driver_championships_db(
            "antonelli", self.con, as_of={"season": 2025, "round": 24})["value"], 0)

    def test_json_and_db_paths_agree_for_every_champion(self):
        champs = sorted({d for _s, d, *_ in fs.driver_title_rows_db(self.con)})
        for did in champs:
            self.assertEqual([x["season"] for x in fs.driver_championships(did)["detail"]],
                             [x["season"] for x in fs.driver_championships_db(did, self.con)["detail"]],
                             did)

    def test_constructor_championships_unchanged(self):
        """車隊冠軍不動：仍只認已完成賽季；2026 車隊榜首不計。"""
        rows = self.con.execute(
            "SELECT cs.constructor_id, count(*) FROM constructor_standings cs "
            "JOIN seasons s ON s.year=cs.season WHERE cs.position=1 AND s.status='completed' "
            "GROUP BY cs.constructor_id").fetchall()
        for cid, n in rows:
            self.assertEqual(fs.constructor_championships_db(cid, self.con)["value"], n, cid)
            self.assertEqual(fs.constructor_championships(cid)["value"], n, cid)
        leader = self.con.execute(
            "SELECT constructor_id FROM constructor_standings WHERE season=2026 AND position=1").fetchone()[0]
        self.assertNotIn(2026, [x["season"] for x in fs.constructor_championships_db(leader, self.con)["detail"]])
        self.assertNotIn(2026, [x["season"] for x in fs.constructor_championships(leader)["detail"]])

    def test_invariant_i5_dualpath_consistent(self):
        inv = _load("check_f1_invariants_title_clinch", "check-f1-invariants.py")
        con = sqlite3.connect(str(DB))
        try:
            self.assertEqual(inv._i5_dualpath_check(con.cursor()), [])
            self.assertEqual(inv._db_driver_stats(con.cursor(), "antonelli")["championships"], 1)
        finally:
            con.close()

    def test_crosscheck_champion_ids_36(self):
        cc = _load("crosscheck_wikipedia_title_clinch", "crosscheck-wikipedia.py")
        ids = cc.db_champion_ids()
        self.assertEqual(len(ids), 36)
        self.assertIn("antonelli", ids)
        con = sqlite3.connect(str(DB))
        try:
            self.assertEqual(cc.our_championship_years(con.cursor(), "antonelli"), [2026])
        finally:
            con.close()
        self.assertEqual(cc.FIELD_DEFINITION_ID["championships_count"], fs.DRIVER_TITLE_FORMULA)
        self.assertNotIn("count_seasons_driver_standing_eq_1", cc.DEFINITION_REGISTRY)
        self.assertNotIn("count_seasons_driver_standing_eq_1", fs.FORMULAS)


if __name__ == "__main__":
    unittest.main()
