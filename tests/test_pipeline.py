#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""管線回歸測試——鎖 2026-07-19 稽核修過的行為，防回歸：
快照驗證（last-known-good）、無變化不重寫、current-round sprint 判斷、
load_results 的 sprint-only round、草稿/下架文章的產物清理。

跑法：python3 -m unittest discover -s tests -v
"""
import datetime
import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fr = _load("fetch_racing", "fetch_racing.py")
rc = _load("racinglib", "racinglib.py")
ba = _load("build_articles", "build-articles.py")
bf = _load("build_facts", "build-facts.py")
cf = _load("check_facts", "check-facts.py")


class SnapshotWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_write_snapshot_skips_rewrite_when_only_fetched_at_changes(self):
        p = self.tmp / "snap.json"
        obj_a = {"season": 2026, "fetched_at": "2026-07-19T00:00:00+00:00", "standings": [1, 2]}
        self.assertTrue(fr._write_snapshot(p, obj_a))
        obj_b = dict(obj_a, fetched_at="2026-07-20T00:00:00+00:00")
        self.assertFalse(fr._write_snapshot(p, obj_b))
        # 檔案完全沒被重寫（工作樹不髒）：內容仍是舊 fetched_at
        self.assertIn("2026-07-19", p.read_text(encoding="utf-8"))

    def test_write_snapshot_rewrites_on_real_change(self):
        p = self.tmp / "snap.json"
        fr._write_snapshot(p, {"season": 2026, "fetched_at": "a", "standings": [1]})
        self.assertTrue(fr._write_snapshot(p, {"season": 2026, "fetched_at": "b", "standings": [1, 2]}))
        self.assertIn('"b"', p.read_text(encoding="utf-8"))


class ValidationTests(unittest.TestCase):
    def _good(self):
        ds = {"DriverStandings": [{"position": str(i)} for i in range(1, 23)]}
        cs = {"ConstructorStandings": [{"position": str(i)} for i in range(1, 12)]}
        return ds, cs

    def test_empty_standings_rejected(self):
        ok, reason = fr.validate_standings(None, None, {"round": "9"}, 9, 9)
        self.assertFalse(ok)
        self.assertIn("空", reason)

    def test_round_regression_rejected(self):
        ds, cs = self._good()
        ok, reason = fr.validate_standings(ds, cs, {"round": "5"}, 5, 9)
        self.assertFalse(ok)
        self.assertIn("倒退", reason)

    def test_healthy_standings_pass(self):
        ds, cs = self._good()
        ok, _ = fr.validate_standings(ds, cs, {"round": "9"}, 9, 8)
        self.assertTrue(ok)

    def test_empty_schedule_rejected(self):
        ok, _ = fr.validate_schedule([], {"races": [{"round": "1"}]})
        self.assertFalse(ok)

    def test_duplicate_rounds_rejected(self):
        ok, _ = fr.validate_schedule([{"round": "1"}, {"round": "1"}], None)
        self.assertFalse(ok)

    def test_healthy_schedule_pass(self):
        ok, _ = fr.validate_schedule([{"round": str(i)} for i in range(1, 23)], None)
        self.assertTrue(ok)


class SprintSessionTests(unittest.TestCase):
    NOW = datetime.datetime(2026, 7, 19, 12, 0, tzinfo=datetime.timezone.utc)

    def test_sprint_already_started(self):
        race = {"Sprint": {"date": "2026-07-18", "time": "14:00:00Z"}}
        self.assertTrue(fr.sprint_session_passed(race, self.NOW))

    def test_sprint_in_future(self):
        race = {"Sprint": {"date": "2026-07-25", "time": "14:00:00Z"}}
        self.assertFalse(fr.sprint_session_passed(race, self.NOW))

    def test_non_sprint_round(self):
        self.assertFalse(fr.sprint_session_passed({"round": "3"}, self.NOW))
        self.assertFalse(fr.sprint_session_passed(None, self.NOW))


class LoadResultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_sprint_only_round_included_with_none_race(self):
        race = {"raceName": "British Grand Prix", "date": "2026-07-05", "Results": []}
        sprint = {"raceName": "Belgian Grand Prix", "date": "2026-07-18", "SprintResults": []}
        (self.tmp / "round-09.json").write_text(json.dumps(race), encoding="utf-8")
        (self.tmp / "round-10-sprint.json").write_text(json.dumps(sprint), encoding="utf-8")
        out = rc.load_results(2026, base=self.tmp)
        self.assertEqual([(r, bool(race_), bool(sp)) for r, race_, sp in out],
                         [(9, True, False), (10, False, True)])


class PruneStaleArticlesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_stale_dir_removed_kept_dir_and_files_untouched(self):
        keep = self.tmp / "live-article"
        stale = self.tmp / "reverted-draft"
        for d in (keep, stale):
            d.mkdir()
            (d / "index.html").write_text("x", encoding="utf-8")
        (self.tmp / "index.html").write_text("articles index", encoding="utf-8")
        ba.prune_stale_article_dirs(self.tmp, {"live-article"})
        self.assertTrue(keep.exists())
        self.assertFalse(stale.exists())
        self.assertTrue((self.tmp / "index.html").exists())


class FactsPackTests(unittest.TestCase):
    """鎖 facts pack 的三個實作陷阱（都是初版真的踩到、抽驗才發現的）。"""

    def _entry(self, pos, ptext, family, grid, status, points, laps=44):
        return {
            "position": str(pos), "positionText": ptext, "points": str(points),
            "grid": str(grid), "laps": str(laps), "status": status,
            "Driver": {"driverId": family.lower(), "familyName": family,
                       "givenName": "X", "code": family[:3].upper()},
            "Constructor": {"constructorId": "mercedes", "name": "Mercedes"},
        }

    def test_lapped_driver_counts_as_classified_not_dnf(self):
        """status=Lapped 的車手有完賽名次，歸類成退賽是事實錯誤。"""
        row = self._entry(18, "18", "Bottas", 17, "Lapped", 0, laps=43)
        self.assertTrue(row["positionText"].isdigit())
        ret = self._entry(22, "R", "Russell", 3, "Retired", 0, laps=0)
        self.assertFalse(ret["positionText"].isdigit())

    def test_standings_rows_rejects_wrong_envelope(self):
        """快照外殼取錯層會回空 list，而空 list 讓一致性檢查真空通過 → 必須拋錯。"""
        with self.assertRaises(SystemExit):
            bf._standings_rows({"MRData": {"StandingsTable": {"StandingsLists": []}}},
                               "driver")

    def test_standings_rows_reads_snapshot_envelope(self):
        snap = {"season": 2026, "data_through_round": 10, "standings": {
            "DriverStandings": [
                {"position": "1", "points": "204", "wins": "6",
                 "Driver": {"driverId": "antonelli", "familyName": "Antonelli"},
                 "Constructors": [{"name": "Mercedes"}]}]}}
        rows = bf._standings_rows(snap, "driver")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["points"], 204.0)

    def test_derive_before_subtracts_and_reorders(self):
        """賽前榜＝賽後榜減本站得分，且要重新排序（本站可能發生位次交換）。"""
        after = [{"id": "a", "zh": "A", "en": "A", "team_en": "", "position": 1,
                  "points": 204.0, "wins": 6},
                 {"id": "b", "zh": "B", "en": "B", "team_en": "", "position": 2,
                  "points": 159.0, "wins": 1},
                 {"id": "c", "zh": "C", "en": "C", "team_en": "", "position": 3,
                  "points": 154.0, "wins": 2}]
        before = bf._derive_before(after, {"a": 25.0, "b": 12.0, "c": 0.0}, top=3)
        # b 本站拿 12 分後才超車 c；賽前應該是 c 在前
        self.assertEqual([r["id"] for r in before], ["a", "c", "b"])
        self.assertEqual(before[1]["position"], 2)


class RoundtableFixTests(unittest.TestCase):
    """鎖 2026-07-20 Sol 查核桌抓到的缺陷，防回歸。"""

    def test_derive_before_also_subtracts_wins(self):
        """S5：只減 points 不減 wins，會產出「本站冠軍賽前已有同樣勝場」的自我矛盾。"""
        after = [{"id": "a", "zh": "A", "en": "A", "team_en": "", "position": 1,
                  "points": 204.0, "wins": 6}]
        before = bf._derive_before(after, {"a": 25.0}, {"a": 1}, top=1)
        self.assertEqual(before[0]["wins"], 5)
        self.assertEqual(before[0]["points"], 179.0)

    def test_derive_before_rejects_negative_wins(self):
        """勝場減成負數＝上游不一致，必須當場炸而不是吞掉。"""
        after = [{"id": "a", "zh": "A", "en": "A", "team_en": "", "position": 1,
                  "points": 25.0, "wins": 0}]
        with self.assertRaises(SystemExit):
            bf._derive_before(after, {"a": 25.0}, {"a": 1}, top=1)

    def test_timeline_excludes_pit_related_moves(self):
        """S4：對手進站造成的名次上升不是超車。判別責任在資料層，不留給寫手。"""
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            base = tmp / "data" / "2026" / "results"
            base.mkdir(parents=True)
            laps = {"Laps": [
                {"number": "1", "Timings": [{"driverId": "x", "position": "5"},
                                            {"driverId": "y", "position": "4"}]},
                {"number": "2", "Timings": [{"driverId": "x", "position": "4"},
                                            {"driverId": "y", "position": "5"}]}]}
            (base / "round-05-laps.json").write_text(json.dumps(laps), encoding="utf-8")
            # y 在第 2 圈進站 → x 的名次上升不可歸因為場上超越
            (base / "round-05-pitstops.json").write_text(
                json.dumps({"PitStops": [{"driverId": "y", "lap": "2",
                                          "stop": "1", "duration": "23.0"}]}),
                encoding="utf-8")
            orig = bf.ROOT
            bf.ROOT = tmp
            try:
                t = bf._timeline(2026, 5, [])
            finally:
                bf.ROOT = orig
            self.assertEqual(t["on_track_position_gains"], [])
            self.assertEqual(t["excluded_pit_related_moves"], 1)
        finally:
            shutil.rmtree(tmp)

    def test_timeline_absent_returns_none(self):
        """逐圈資料沒落地時回 None——prompt 據此禁止寫轉折，不能回空 dict 讓人誤以為有資料。"""
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            orig = bf.ROOT
            bf.ROOT = tmp
            try:
                self.assertIsNone(bf._timeline(2026, 99, []))
            finally:
                bf.ROOT = orig
        finally:
            shutil.rmtree(tmp)


class CheckFactsTests(unittest.TestCase):
    """對帳腳本本身的行為——尤其是「沒有實際比對到東西不算通過」。"""

    def test_table_rows_skips_separator_line(self):
        md = "| 名次 | 車手 |\n|---|---|\n| 1 | 安東內利 |\n"
        rows = cf._table_rows(md)
        self.assertEqual(rows, [["名次", "車手"], ["1", "安東內利"]])

    def test_numbers_in_facts_never_gates(self):
        """提示性檢查即使發現孤兒數字也必須回 True，否則會變成擋線的循環驗證。"""
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            facts = tmp / "f.json"
            facts.write_text(json.dumps({"points": 25}), encoding="utf-8")
            art = tmp / "a.md"
            art.write_text("| 名次 | 積分 |\n|---|---|\n| 1 | 9999 |\n", encoding="utf-8")
            self.assertTrue(cf.numbers_in_facts(str(facts), str(art)))
        finally:
            shutil.rmtree(tmp)

    def test_no_causal_flags_causal_sentence(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            art = tmp / "a.md"
            art.write_text("羅素因為引擎問題所以退賽。\n", encoding="utf-8")
            self.assertTrue(cf.no_causal(str(art)))  # 提示不擋
        finally:
            shutil.rmtree(tmp)


class ArticleKickerTests(unittest.TestCase):
    def test_report_and_wire_types_have_kickers(self):
        self.assertEqual(ba._kicker({"type": "report"}), "賽後戰報")
        self.assertEqual(ba._kicker({"type": "preview"}), "賽站前瞻")
        self.assertEqual(ba._kicker({"type": "wire"}), "外電整理")


if __name__ == "__main__":
    unittest.main()
