"""Standings override layer and external parser regression tests (synthetic fixtures only)."""
import contextlib
import importlib.util
import io
import json
import pathlib
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build = _load("build_f1_db_overrides", "build-f1-db.py")
cross = _load("crosscheck_standings_test", "crosscheck-standings.py")
shared = _load("standings_overrides_shared_test", "standings_overrides.py")


def _item(**changes):
    row = {"table": "driver_standings", "season": 1976, "entity_id": "hunt",
           "field": "points", "raw_value": 66.0, "value": 69.0,
           "source_revid": 123, "source_url": "https://en.wikipedia.org/wiki/X",
           "reason": "synthetic", "by": "charlie", "date": "2026-08-13"}
    row.update(changes)
    return row


class OverrideLayerTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute("CREATE TABLE driver_standings "
                         "(season INTEGER, position INTEGER, position_text TEXT, points REAL, "
                         "wins INTEGER, driver_id TEXT, constructor_ids TEXT)")
        self.con.execute("CREATE TABLE constructor_standings "
                         "(season INTEGER, position INTEGER, position_text TEXT, points REAL, "
                         "wins INTEGER, constructor_id TEXT)")
        self.con.execute("INSERT INTO driver_standings VALUES (1976,1,'1',66,6,'hunt','mclaren')")
        self.addCleanup(self.con.close)
        self.lookup = lambda table, season, entity, field: 66.0

    def test_pending_is_default_denied(self):
        n = build.apply_standings_overrides(
            self.con.cursor(), [_item(by="PENDING-charlie")], raw_lookup=self.lookup)
        self.assertEqual(n, 0)
        self.assertEqual(self.con.execute("SELECT points FROM driver_standings").fetchone()[0], 66.0)

    def test_rejected_charlie_is_default_denied(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            n = build.apply_standings_overrides(
                self.con.cursor(), [_item(by="rejected-charlie")], raw_lookup=self.lookup)
        self.assertEqual(n, 0)
        self.assertEqual(self.con.execute("SELECT points FROM driver_standings").fetchone()[0], 66.0)
        self.assertIn("'rejected-charlie'", stderr.getvalue())

    def test_charlie_is_applied(self):
        n = build.apply_standings_overrides(
            self.con.cursor(), [_item(by="charlie")], raw_lookup=self.lookup)
        self.assertEqual(n, 1)
        self.assertEqual(self.con.execute("SELECT points FROM driver_standings").fetchone()[0], 69.0)

    def test_unknown_by_is_default_denied(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            n = build.apply_standings_overrides(
                self.con.cursor(), [_item(by="charlei")], raw_lookup=self.lookup)
        self.assertEqual(n, 0)
        self.assertEqual(self.con.execute("SELECT points FROM driver_standings").fetchone()[0], 66.0)
        self.assertIn("'charlei'", stderr.getvalue())

    def test_raw_drift_fails(self):
        with self.assertRaisesRegex(RuntimeError, "drift"):
            build.apply_standings_overrides(
                self.con.cursor(), [_item()], raw_lookup=lambda *args: 67.0)

    def test_stale_non_pending_override_fails(self):
        with self.assertRaisesRegex(RuntimeError, "已過期"):
            build.apply_standings_overrides(
                self.con.cursor(), [_item(value=66.0)], raw_lookup=self.lookup)

    def test_document_adapter_maps_position_text_to_jolpica_camel_case(self):
        document = {"DriverStandings": [{
            "position": "1", "positionText": "1", "points": "66", "wins": "6",
            "Driver": {"driverId": "hunt"}, "Constructors": []}]}
        item = _item(field="position_text", raw_value="1", value="D")
        n = shared.apply_standings_overrides_to_document(
            document, "driver_standings", 1976, [item])
        self.assertEqual(n, 1)
        self.assertEqual(document["DriverStandings"][0]["positionText"], "D")
        self.assertNotIn("position_text", document["DriverStandings"][0])


class WikiParserTests(unittest.TestCase):
    def test_mixed_fraction_ignores_parenthetical_total(self):
        self.assertEqual(cross._num("42 (57+1⁄7)"), 42.0)
        self.assertAlmostEqual(cross._num("11 1⁄3"), 11 + 1 / 3)
        self.assertAlmostEqual(cross._num("25+1⁄7 (26+9⁄14)"), 25 + 1 / 7)

    def test_tied_position_marker_inherits_previous_position(self):
        html = """<h3>World Drivers' Championship standings</h3>
        <table><tr><td><table class='wikitable'><tr><th>Pos</th><th>Driver</th><th>Pts</th></tr>
        <tr><td>9</td><td>A Driver</td><td>4</td></tr>
        <tr><td>=[1]</td><td>B Driver</td><td>4</td></tr></table></td></tr></table>"""
        rows = cross.parse_standings({"html": html})["driver"]
        self.assertEqual([r["position"] for r in rows], [9, 9])


if __name__ == "__main__":
    unittest.main()
