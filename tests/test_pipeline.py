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


if __name__ == "__main__":
    unittest.main()
