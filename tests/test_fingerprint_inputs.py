"""Fingerprint inputs that previously left selective encyclopedia regeneration stale."""
import hashlib
import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


regen = _load("regen_fingerprint_inputs", "regen-encyclopedia.py")


class FingerprintInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.intros = self.tmp / "intros"
        self.intros.mkdir()
        self.intro = self.intros / "2002.md"
        self.intro.write_text("approved intro v1", encoding="utf-8")
        self.approved = {"season-intro-2002": {"article_sha256": self._sha(self.intro)}}
        self.orig_intro_dir = regen.gs.INTRO_DIR
        self.orig_approved = regen.gs._load_approved
        regen.gs.INTRO_DIR = self.intros
        regen.gs._load_approved = lambda: self.approved
        self.addCleanup(self._restore_intro)
        self.con = regen.fs.connect_db()
        self.addCleanup(self.con.close)

    @staticmethod
    def _sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _restore_intro(self):
        regen.gs.INTRO_DIR = self.orig_intro_dir
        regen.gs._load_approved = self.orig_approved

    def test_intro_edit_changes_only_its_season_and_regenerates_only_that_year(self):
        before = regen.compute_fingerprints(self.con)
        fp = self.tmp / "fingerprints.json"
        fp.write_text(json.dumps(before), encoding="utf-8")
        self.intro.write_text("approved intro v2", encoding="utf-8")

        rendered = []
        originals = (regen.gs._render_one_season, regen.gs.render_index,
                     regen.dr.render_index, regen.dr.gen_driver,
                     regen.cg.render_index, regen.cg.gen_constructor,
                     regen.gs.render_round, regen.save_fingerprints)
        regen.gs._render_one_season = lambda year, urls, rounds: rendered.append(year)
        regen.gs.render_index = lambda built: "index"
        regen.dr.render_index = lambda con: "drivers"
        regen.dr.gen_driver = lambda did, con: {"slug": did}
        regen.cg.render_index = lambda con: "constructors"
        regen.cg.gen_constructor = lambda cid, con: {"slug": cid}
        regen.gs.render_round = lambda *args: "round"
        regen.save_fingerprints = lambda *args, **kwargs: None
        try:
            result = regen.selective_regen(self.con, fp_path=fp)
        finally:
            (regen.gs._render_one_season, regen.gs.render_index,
             regen.dr.render_index, regen.dr.gen_driver,
             regen.cg.render_index, regen.cg.gen_constructor,
             regen.gs.render_round, regen.save_fingerprints) = originals
        self.assertEqual(result["changed_years"], [2002])
        self.assertEqual(rendered, [2002])

    def test_constructor_roster_file_changes_driver_fingerprints(self):
        roster = self.tmp / "constructor-roster.json"
        roster.write_text("{}", encoding="utf-8")
        original = regen.CONSTRUCTOR_ROSTER
        regen.CONSTRUCTOR_ROSTER = roster
        try:
            before = regen.compute_fingerprints(self.con)
            roster.write_text('{"changed":true}', encoding="utf-8")
            after = regen.compute_fingerprints(self.con)
        finally:
            regen.CONSTRUCTOR_ROSTER = original
        self.assertNotEqual(before["drivers"], after["drivers"])
        self.assertEqual(before["seasons"], after["seasons"])

    def test_adjudicated_override_is_fingerprinted_only_for_affected_season(self):
        override_slice = regen._season_override_slice(1976)
        self.assertEqual(override_slice["renderer"], "preserve-raw-json-type-v1")
        rows = override_slice["rows"]
        self.assertEqual(len(rows), 6)
        self.assertIn({"table": "driver_standings", "season": 1976,
                       "entity_id": "hunt", "field": "points",
                       "raw_value": 66.0, "value": 69.0, "by": "charlie"}, rows)
        self.assertEqual(regen._season_override_slice(2026), [],
                         "無裁決的當季不得因歷史 override 白刷")


if __name__ == "__main__":
    unittest.main()
