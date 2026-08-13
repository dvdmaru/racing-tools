#!/usr/bin/env python3
"""2026 全 11 隊 /constructors/ 生成器、gate、公式與管線接線回歸。"""
import importlib.util
import json
import pathlib
import re
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


regen = _load("regen_constructor_tests", "regen-encyclopedia.py")
cg, rc, fs, gs, dr, p0 = regen.cg, regen.rc, regen.fs, regen.gs, regen.dr, regen.p0


def _approved_copy(src, key):
    tmp = pathlib.Path(tempfile.mkdtemp())
    data = json.loads(pathlib.Path(src).read_text(encoding="utf-8"))
    for row in data[key].values():
        row["approved_by"] = "charlie-test"
    path = tmp / "approved.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return tmp, path


def _render_all(target):
    old = cg.PUB
    cg.PUB = target
    con = fs.connect_db()
    try:
        cg.render_index(con)
        for cid in cg.CONSTRUCTOR_IDS:
            cg.gen_constructor(cid, con)
    finally:
        con.close()
        cg.PUB = old


class RosterAndGoldenGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(cg.REPORT.read_text(encoding="utf-8"))
        cls.golden = json.loads(cg.GOLDEN.read_text(encoding="utf-8"))["constructors"]

    def test_canonical_roster_is_exact_2026_db_set(self):
        con = fs.connect_db()
        try:
            self.assertTrue(cg.roster_exact(con))
            self.assertEqual(cg.db_roster(con), cg.CONSTRUCTOR_IDS)
        finally:
            con.close()
        self.assertEqual(len(cg.CONSTRUCTOR_IDS), 11)

    def test_extra_and_missing_roster_both_fail(self):
        con = fs.connect_db()
        try:
            self.assertFalse(cg.roster_exact(con, list(cg.CONSTRUCTOR_IDS) + ["extra_team"]))
            self.assertFalse(cg.roster_exact(con, list(cg.CONSTRUCTOR_IDS[:-1])))
        finally:
            con.close()

    def test_all_eleven_as_of_r11(self):
        self.assertEqual({tuple(v["as_of"].values()) for v in self.golden.values()}, {(2026, 11)})

    def test_pending_golden_rejected_with_synthetic_fixture(self):
        tmp, approved = _approved_copy(cg.GOLDEN, "constructors")
        self.addCleanup(shutil.rmtree, tmp)
        data = json.loads(approved.read_text(encoding="utf-8"))
        data["constructors"]["ferrari"]["approved_by"] = "PENDING-charlie"
        approved.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(cg.gate_golden(approved))

    def test_approved_synthetic_golden_passes(self):
        tmp, approved = _approved_copy(cg.GOLDEN, "constructors")
        self.addCleanup(shutil.rmtree, tmp)
        self.assertTrue(cg.gate_golden(approved))

    def test_pending_verdict_rejected_with_synthetic_fixture(self):
        cc = _load("constructor_crosscheck_fixture", "crosscheck-constructors.py")
        report = json.loads(cg.REPORT.read_text(encoding="utf-8"))
        verdicts = json.loads(cg.VERDICTS.read_text(encoding="utf-8"))
        # repo 現況不當斷言；先把所有裁決合成核准，再只留一筆 PENDING 驗行為。
        for row in verdicts["verdicts"]:
            row["by"] = "charlie-test"
        verdicts["verdicts"][0]["by"] = "PENDING-charlie"
        self.assertFalse(cc.gate_diffs(report, verdicts))


class FormulaOracleTests(unittest.TestCase):
    """至少三隊以獨立 SQL 驗算四欄，SQL 不呼叫 f1stats 實作。"""

    def test_four_fields_against_independent_sql_for_three_teams(self):
        con = fs.connect_db()
        try:
            for cid in ("ferrari", "mclaren", "aston_martin"):
                got = cg._computed_row(cid, con, cg.AS_OF)
                champ = con.execute(
                    "SELECT count(*) FROM constructor_standings cs JOIN seasons s ON s.year=cs.season "
                    "WHERE cs.constructor_id=? AND cs.position=1 AND s.status='completed' AND cs.season<=2026",
                    (cid,)).fetchone()[0]
                years = [r[0] for r in con.execute(
                    "SELECT cs.season FROM constructor_standings cs JOIN seasons s ON s.year=cs.season "
                    "WHERE cs.constructor_id=? AND cs.position=1 AND s.status='completed' AND cs.season<=2026 "
                    "ORDER BY cs.season", (cid,))]
                wins = con.execute(
                    "SELECT count(*) FROM (SELECT DISTINCT season,round FROM results "
                    "WHERE constructor_id=? AND position_text='1' AND (season<2026 OR season=2026 AND round<=11))",
                    (cid,)).fetchone()[0]
                podiums = con.execute(
                    "SELECT count(*) FROM (SELECT DISTINCT season,round,position_text,number FROM results "
                    "WHERE constructor_id=? AND position_text IN ('1','2','3') "
                    "AND (season<2026 OR season=2026 AND round<=11))", (cid,)).fetchone()[0]
                entries = con.execute(
                    "SELECT count(*) FROM (SELECT DISTINCT season,round FROM results "
                    "WHERE constructor_id=? AND (season<2026 OR season=2026 AND round<=11))", (cid,)).fetchone()[0]
                self.assertEqual(got, {"championships_count": champ, "championships_years": years,
                                       "wins": wins, "podiums": podiums, "entries": entries}, cid)
        finally:
            con.close()

    def test_values_always_equal_detail_lengths(self):
        con = fs.connect_db()
        try:
            for cid in cg.CONSTRUCTOR_IDS:
                career = fs.constructor_career_db(cid, con, as_of=cg.AS_OF)
                champ = fs.constructor_championships_db(cid, con, as_of=cg.AS_OF)
                for stat in (career["wins"], career["podiums"], career["entries"], champ):
                    self.assertEqual(stat["value"], len(stat["detail"]))
                    self.assertIn(stat["formula"], fs.FORMULAS)
        finally:
            con.close()

    def test_win_formula_uses_position_text(self):
        source = (ROOT / "scripts" / "f1stats.py").read_text(encoding="utf-8")
        self.assertIn('r["position_text"] == "1"', source)
        self.assertNotIn('r["position"] == 1', source)


class GenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        _render_all(cls.tmp)
        cls.index = (cls.tmp / "constructors" / "index.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_index_and_all_eleven_pages_exist(self):
        self.assertEqual(len(list((self.tmp / "constructors").rglob("index.html"))), 12)
        for cid in cg.CONSTRUCTOR_IDS:
            slug = rc.constructor_slug(cid)
            self.assertIn(f'href="/constructors/{slug}/"', self.index)
            self.assertTrue((self.tmp / "constructors" / slug / "index.html").is_file())

    def test_index_sorted_by_2026_standings_and_champion_badges(self):
        hrefs = re.findall(r'<td><a href="/constructors/([^/]+)/">', self.index)
        self.assertEqual(hrefs, ["mercedes", "ferrari", "mclaren", "red-bull", "rb", "alpine",
                                 "haas", "audi", "williams", "aston-martin", "cadillac"])
        self.assertEqual(self.index.count('class="chip">世界冠軍'), 5)

    def test_four_publish_fields_and_three_forbidden_fields(self):
        html = (self.tmp / "constructors" / "ferrari" / "index.html").read_text(encoding="utf-8")
        for label in ("車隊世界冠軍", "分站勝場", "頒獎台", "參賽場次"):
            self.assertIn(f'<div class="stat-l">{label}</div>', html)
        for label in ("桿位", "最快圈", "生涯積分"):
            self.assertIsNotNone(re.search(
                rf'<div class="stat na">.*?<div class="stat-l">{label}</div>', html, re.S))
        self.assertEqual(html.count("怎麼算的"), 4)

    def test_zero_champion_team_has_participation_timeline(self):
        html = (self.tmp / "constructors" / "aston-martin" / "index.html").read_text(encoding="utf-8")
        self.assertIn("參賽時間軸", html)
        self.assertIn('class="yr on', html)
        self.assertNotIn('class="yr champ', html)

    def test_jsonld_sports_team_sameas(self):
        html = (self.tmp / "constructors" / "ferrari" / "index.html").read_text(encoding="utf-8")
        self.assertIn('"@type":"SportsTeam"', html)
        self.assertIn('"sameAs":["https://en.wikipedia.org/wiki/Scuderia_Ferrari"]', html)

    def test_approved_translations_and_original_preservation(self):
        self.assertIn("Alpine F1 Team", self.index)
        self.assertIn("Racing Bulls", self.index)
        self.assertNotIn("阿爾派", self.index)
        con = fs.connect_db()
        try:
            for cid in cg.CONSTRUCTOR_IDS:
                self.assertIsNotNone(cg.approved_zh(cid, fs.constructor_meta_db(cid, con)["name"]))
        finally:
            con.close()

    def test_two_runs_byte_identical(self):
        other = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other)
        _render_all(other)
        left = {str(p.relative_to(self.tmp)): p.read_bytes() for p in self.tmp.rglob("index.html")}
        right = {str(p.relative_to(other)): p.read_bytes() for p in other.rglob("index.html")}
        self.assertEqual(left, right)


class OwnershipAndDownstreamTests(unittest.TestCase):
    def test_phase0_has_no_constructor_writer(self):
        for name in ("CONSTRUCTORS", "gen_constructor", "render_index", "main"):
            self.assertFalse(hasattr(p0, name), name)

    def test_2026_season_subpages_include_eleven_and_2002_includes_williams(self):
        self.assertEqual(set(gs.season_subpage_entities(2026)[1]), set(cg.CONSTRUCTOR_IDS))
        self.assertIn("williams", gs.season_subpage_entities(2002)[1])

    def test_all_current_driver_team_chips_are_links(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        old = dr.PUB
        dr.PUB = tmp
        con = fs.connect_db()
        try:
            for did in dr.ACTIVE_IDS:
                dr.gen_driver(did, con)
        finally:
            con.close()
            dr.PUB = old
        for page in tmp.rglob("index.html"):
            html = page.read_text(encoding="utf-8")
            block = html.split('<h2 class="sec-title">效力車隊</h2>', 1)[1].split('</div>', 1)[0]
            for cid in cg.CONSTRUCTOR_IDS:
                if rc.constructor_slug(cid) in block:
                    self.assertIn(f'href="/constructors/{rc.constructor_slug(cid)}/"', block)

    def test_regen_owner_is_constructor_generator(self):
        source = (ROOT / "scripts" / "regen-encyclopedia.py").read_text(encoding="utf-8")
        self.assertIn("cg.gen_constructor(cid, con)", source)
        self.assertNotIn("p0.gen_constructor", source)

    def test_sitemap_urls_have_index_plus_eleven(self):
        urls = regen.enumerate_constructor_urls()
        self.assertEqual(len(urls), 12)
        self.assertEqual(urls[0], f"{rc.BASE}/constructors/")


if __name__ == "__main__":
    unittest.main()
