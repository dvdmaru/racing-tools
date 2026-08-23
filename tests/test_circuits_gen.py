#!/usr/bin/env python3
"""全 78 條賽道 /circuits/ 生成器、gate、公式與管線接線回歸。

鏡射 tests/test_constructors_gen.py 的三道 gate（頁面存在／中英對照／禁字與 IP 紅線），
每一道都配一條反向測試（MUST_NOT_HIT）——只有正向斷言的 gate，寫壞了會永遠亮綠。
第四道是本頁群獨有的：**連結目標必存在**。賽道頁的冠軍欄會提到 116 位分站冠軍車手與
47 支車隊，其中只有 53 位／11 支有實體頁；把沒頁的也連出去，就是全站最容易量產死連結
的地方。
"""
import importlib.util
import json
import pathlib
import re
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


regen = _load("regen_circuit_tests", "regen-encyclopedia.py")
bsm = _load("build_sitemap_circuit_tests", "build-sitemap.py")
ci, rc, fs, gs, dr, cg = regen.ci, regen.rc, regen.fs, regen.gs, regen.dr, regen.cg

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# 禁字：站規「不寫官方認證」那條的字面化。IP 紅線的另一半（不用會徽／隊徽／官方照片／
# 賽道官方圖）在靜態頁上的可檢查形式＝本頁群零圖片、零外部圖床。
FORBIDDEN_WORDS = ("官方認證", "官方授權", "官方合作", "官方認可", "官方賽道圖")
NO_ZH_CIRCUITS = ("charade", "dallas", "dijon", "essarts", "galvez", "jarama",
                  "monsanto", "montjuic", "mosport", "nivelles", "riverside", "tremblant")


def _render_all(target):
    old = ci.PUB
    ci.PUB = target
    con = fs.connect_db()
    try:
        ci.render_index(con)
        for cid in ci.CIRCUIT_IDS:
            ci.gen_circuit(cid, con)
    finally:
        con.close()
        ci.PUB = old


_RENDERED = []


def _rendered_dir():
    """全 79 頁只渲染一次，四個測試類共用（每類各渲一次＝同樣的東西跑四遍）。"""
    if not _RENDERED:
        tmp = pathlib.Path(tempfile.mkdtemp())
        _render_all(tmp)
        _RENDERED.append(tmp)
    return _RENDERED[0]


def tearDownModule():
    for tmp in _RENDERED:
        shutil.rmtree(tmp, ignore_errors=True)


def _body(html):
    """只取 container 內、頁尾連結區之前的內容——頁殼的 footer 不是本生成器的產物。"""
    inner = html.split('<div class="container">', 1)[1]
    return inner.split('<div class="article-footer">', 1)[0]


class _Rendered(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = _rendered_dir()
        cls.index = (cls.dir / "circuits" / "index.html").read_text(encoding="utf-8")

    def page(self, cid):
        return (self.dir / "circuits" / ci.circuit_slug(cid) / "index.html").read_text(
            encoding="utf-8")


# ---------- gate ①：註冊表／統計不變量 ----------

class RegistryAndStatGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = fs.connect_db()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_registry_is_exact_db_circuit_set(self):
        db_ids = [r[0] for r in self.con.execute(
            "SELECT circuit_id FROM circuits ORDER BY circuit_id")]
        self.assertEqual(ci.CIRCUIT_IDS, db_ids)
        self.assertEqual(len(ci.CIRCUIT_IDS), 78)
        self.assertTrue(ci.gate_registry(self.con))

    def test_extra_and_missing_registry_both_fail(self):
        """反向：多一條／少一條都必須被擋（雙向全等不是單向包含）。"""
        self.assertFalse(ci.gate_registry(self.con, list(ci.CIRCUIT_IDS) + ["extra_track"]))
        self.assertFalse(ci.gate_registry(self.con, list(ci.CIRCUIT_IDS[:-1])))

    def test_slugs_are_kebab_case_and_unique(self):
        slugs = [ci.circuit_slug(cid) for cid in ci.CIRCUIT_IDS]
        for slug in slugs:
            self.assertRegex(slug, SLUG_RE, slug)
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_unregistered_circuit_raises_keyerror(self):
        with self.assertRaises(KeyError):
            ci.circuit_slug("monza_typo")

    def test_stat_gate_green_and_values_equal_detail_lengths(self):
        self.assertTrue(ci.gate_stats(self.con))
        for cid in ci.CIRCUIT_IDS:
            s = ci.circuit_summary(cid, self.con)
            self.assertEqual(s["hosted"]["value"], len(s["hosted"]["detail"]), cid)

    def test_unheld_race_in_a_stat_is_rejected(self):
        """反向：把「尚未舉行」的分站混進統計明細，gate ② 必須失敗。

        這是站規「進行中賽季的排程不是戰績」的機械化——沒有這條，實作把 races 全部
        算進去也一樣全綠。
        """
        real = ci.circuit_summary

        def poisoned(cid, con):
            s = real(cid, con)
            if cid == "monza":
                s["hosted"]["detail"] = s["hosted"]["detail"] + [
                    {"season": 2026, "round": 13, "race": "X", "held": False,
                     "winners": [], "source": "x"}]
                s["hosted"]["value"] = len(s["hosted"]["detail"])
            return s

        ci.circuit_summary = poisoned
        try:
            self.assertFalse(ci.gate_stats(self.con, ["monza"]))
        finally:
            ci.circuit_summary = real

    def test_2026_pending_round_is_excluded_from_hosted_count(self):
        s = ci.circuit_summary("monza", self.con)
        scheduled = self.con.execute(
            "SELECT count(*) FROM races WHERE circuit_id='monza'").fetchone()[0]
        self.assertEqual(len(s["pending"]), 1)
        self.assertEqual(s["hosted"]["value"], scheduled - 1)

    def test_circuit_with_no_race_yet_is_honest_not_empty(self):
        """2026 新賽道（madring）一場都還沒跑：統計是 0，不是被藏起來或假裝有資料。"""
        s = ci.circuit_summary("madring", self.con)
        self.assertEqual(s["hosted"]["value"], 0)
        self.assertEqual(s["driver_wins"], {})
        self.assertIsNone(s["first_season"])

    def test_shared_drive_race_credits_both_drivers_once_each(self):
        """1957 英國站兩位車手接力同一台車，資料源列兩筆冠軍：兩位都算，車隊只算一次。"""
        s = ci.circuit_summary("aintree", self.con)
        race = [r for r in s["held"] if r["season"] == 1957][0]
        self.assertEqual(len(race["winners"]), 2)
        self.assertEqual({w["driver_id"] for w in race["winners"]}, {"brooks", "moss"})
        for did in ("brooks", "moss"):
            self.assertEqual(len([r for r in s["driver_wins"][did] if r["season"] == 1957]), 1,
                             did)
        # 車隊同場只能記一次——不然一場比賽會替 Vanwall 生出兩座分站冠軍。
        self.assertEqual(len([r for r in s["constructor_wins"]["vanwall"]
                              if r["season"] == 1957]), 1)
        self.assertEqual(sum(len(v) for v in s["constructor_wins"].values()),
                         s["hosted"]["value"],
                         "車隊勝場總和必須等於已舉行分站數（同場去重後每站剛好一隊）")

    def test_leaderboard_keeps_ties_at_the_cutoff(self):
        rows = ci.leaderboard({f"d{i}": [1] * 3 for i in range(8)}, limit=5)
        self.assertEqual(len(rows), 8, "同分者被切掉＝排行榜在說謊")

    def test_leaderboard_is_sorted_and_capped_when_no_tie(self):
        counts = {"a": [1] * 9, "b": [1] * 8, "c": [1] * 7, "d": [1] * 6,
                  "e": [1] * 5, "f": [1] * 4, "g": [1] * 3}
        rows = ci.leaderboard(counts, limit=5)
        self.assertEqual([k for k, _ in rows], ["a", "b", "c", "d", "e"])


# ---------- gate ②：頁面存在 ----------

class GenerationTests(_Rendered):
    def test_index_and_all_78_pages_exist(self):
        self.assertEqual(len(list((self.dir / "circuits").rglob("index.html"))), 79)
        for cid in ci.CIRCUIT_IDS:
            slug = ci.circuit_slug(cid)
            self.assertIn(f'href="/circuits/{slug}/"', self.index)
            self.assertTrue((self.dir / "circuits" / slug / "index.html").is_file())

    def test_index_sorted_by_hosted_count_desc(self):
        counts = [int(n) for n in re.findall(
            r'<td class="mono">(\d+)</td><td class="mono">', self.index)]
        self.assertEqual(len(counts), 78)
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_published_field_and_two_withheld_fields(self):
        html = self.page("monza")
        self.assertIn('<div class="stat-l">承辦分站</div>', html)
        for label in ("桿位", "最快圈"):
            self.assertIsNotNone(re.search(
                rf'<div class="stat na">.*?<div class="stat-l">{label}</div>', html, re.S),
                f"{label} 必須是明確的「不發布」卡，不能悄悄消失")
        self.assertEqual(html.count("怎麼算的"), 1)

    def test_every_page_has_the_four_sections_and_one_h1(self):
        for cid in ci.CIRCUIT_IDS:
            html = self.page(cid)
            heads = re.findall(r'<h2 class="sec-title">(.*?)</h2>', html)
            self.assertEqual(heads, ["歷年最多勝車手", "歷年最多勝車隊", "承辦分站", "方法說明"], cid)
            self.assertEqual(len(re.findall(r"<h1", html)), 1, cid)

    def test_hosting_table_lists_every_scheduled_round(self):
        con = fs.connect_db()
        try:
            for cid in ("monza", "monaco", "madring", "zeltweg"):
                n = con.execute("SELECT count(*) FROM races WHERE circuit_id=?",
                                (cid,)).fetchone()[0]
                body = _body(self.page(cid))
                table = body.rsplit("<tbody>", 1)[1]
                self.assertEqual(table.count("<tr>"), n, cid)
        finally:
            con.close()

    def test_pending_round_is_labelled_not_counted(self):
        html = self.page("monza")
        self.assertIn('<span class="pending">尚未舉行</span>', html)
        self.assertIn("不計入", html)

    def test_no_race_yet_circuit_says_so(self):
        html = self.page("madring")
        self.assertIn("尚無資料", html)
        self.assertIn('<div class="stat-v mono">0<', html)

    def test_data_gap_disclosure_is_on_every_page(self):
        """1950 年代資料由志願者社群維護——這句話必須在每一頁，不能只寫在索引。"""
        for cid in ci.CIRCUIT_IDS:
            html = self.page(cid)
            self.assertIn("志願者社群", html, cid)
            self.assertIn("jolpica", html, cid)

    def test_jsonld_place_and_breadcrumb(self):
        html = self.page("monza")
        self.assertIn('"@type":"Place"', html)
        self.assertIn('"addressCountry":"Italy"', html)
        self.assertIn('"@type":"BreadcrumbList"', html)

    def test_two_runs_byte_identical(self):
        other = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other)
        _render_all(other)
        left = {str(p.relative_to(self.dir)): p.read_bytes()
                for p in self.dir.rglob("index.html")}
        right = {str(p.relative_to(other)): p.read_bytes() for p in other.rglob("index.html")}
        self.assertEqual(left, right)


# ---------- gate ③：中英對照 ----------

class BilingualTests(_Rendered):
    def test_approved_translation_pairs_with_original(self):
        html = self.page("monza")
        self.assertIn('蒙札賽道<span class="zh-en">　Autodromo Nazionale di Monza</span>', html)

    def test_circuit_without_approved_zh_shows_original_only(self):
        """反向：12 條沒有核准譯名的賽道必須只出現原文，不得自翻。"""
        for cid in NO_ZH_CIRCUITS:
            self.assertIsNone(ci.approved_zh(cid), cid)
            h1 = re.search(r"<h1[^>]*>(.*?)</h1>", self.page(cid), re.S).group(1)
            self.assertIn('class="en-only"', h1, cid)
            self.assertNotIn("zh-en", h1, cid)

    def test_every_rendered_zh_comes_from_the_approved_table(self):
        approved = set(rc.CIRCUIT_ZH.values())
        translated = [c for c in ci.CIRCUIT_IDS if ci.approved_zh(c)]
        for cid in translated:
            self.assertIn(ci.approved_zh(cid), approved, cid)
        self.assertEqual(len(translated), 66)
        self.assertEqual(len(ci.CIRCUIT_IDS) - len(translated), len(NO_ZH_CIRCUITS))

    def test_index_shows_both_scripts(self):
        self.assertIn('class="zh-en"', self.index)
        self.assertIn('class="en-only"', self.index)
        self.assertIn(f'<span class="mono">{len(NO_ZH_CIRCUITS)}</span> 條尚無核准譯名',
                      self.index)


# ---------- gate ④：禁字與 IP 紅線 ----------

def ip_violations(html):
    """回這一頁踩到的紅線清單（空 list＝乾淨）。正向與反向測試共用同一支偵測器。"""
    bad = []
    for word in FORBIDDEN_WORDS:
        if word in html:
            bad.append(f"禁字：{word}")
    if "<img" in html or "background-image" in html:
        bad.append("頁面出現圖片（會徽／隊徽／官方照片／賽道官方圖的載體）")
    for tag, pattern in (("title", r"<title>(.*?)</title>"), ("h1", r"<h1[^>]*>(.*?)</h1>")):
        for text in re.findall(pattern, html, re.S):
            if re.search(r"\bF1\b|FORMULA\s*1", text, re.I):
                bad.append(f"{tag} 出現 F1 字樣：{text[:40]}")
    return bad


class IpRedlineTests(_Rendered):
    def test_no_page_trips_the_redline(self):
        for cid in ci.CIRCUIT_IDS:
            self.assertEqual(ip_violations(_body(self.page(cid))), [], cid)
        self.assertEqual(ip_violations(_body(self.index)), [])

    def test_title_layer_is_also_clean(self):
        for cid in ci.CIRCUIT_IDS:
            html = self.page(cid)
            title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
            self.assertEqual(ip_violations(f"<title>{title}</title>"), [], cid)

    def test_detector_actually_catches_violations(self):
        """反向：偵測器對合成違例必須有反應，否則上面兩條是空轉。"""
        self.assertTrue(ip_violations("<p>本站經官方認證</p>"))
        self.assertTrue(ip_violations('<p><img src="/logo.png"></p>'))
        self.assertTrue(ip_violations("<title>F1 賽道大全</title>"))
        self.assertTrue(ip_violations('<h1 class="x">FORMULA 1 Circuits</h1>'))
        self.assertEqual(ip_violations("<title>蒙札賽道承辦紀錄</title>"), [])

    def test_body_text_may_still_reference_the_series(self):
        """紅線在站名層與素材層，不在內文指涉層——偵測器不該擴張到內文。"""
        self.assertEqual(ip_violations("<p>這是一級方程式的賽道之一</p>"), [])


# ---------- gate ⑤（本頁群獨有）：連結目標必存在 ----------

class LinkTargetTests(_Rendered):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.universe = (
            {f"/seasons/{y}/" for y in range(gs.FIRST_YEAR, gs.LAST_YEAR + 1)}
            | {f"/drivers/{rc.driver_slug(d)}/" for d in dr.DRIVER_IDS}
            | {f"/constructors/{rc.constructor_slug(c)}/" for c in cg.CONSTRUCTOR_IDS}
            | {f"/circuits/{ci.circuit_slug(c)}/" for c in ci.CIRCUIT_IDS}
            | {"/seasons/", "/drivers/", "/constructors/", "/circuits/"})

    def test_every_entity_link_points_at_a_page_that_exists(self):
        prefixes = ("/seasons/", "/drivers/", "/constructors/", "/circuits/")
        checked = 0
        for cid in ci.CIRCUIT_IDS:
            body = _body(self.page(cid))
            for href in re.findall(r'href="(/[^"]*)"', body):
                if href.startswith(prefixes):
                    self.assertIn(href, self.universe, f"{cid} 連到不存在的頁：{href}")
                    checked += 1
        self.assertGreater(checked, 1000, "掃到的連結太少，這條斷言可能沒真的在看")

    def test_index_links_only_to_generated_circuit_pages(self):
        for href in re.findall(r'href="(/circuits/[^"]*)"', _body(self.index)):
            self.assertIn(href, self.universe)

    def test_pageless_winners_are_plain_text_not_links(self):
        """反向：資料庫裡有 116 位分站冠軍、只有 53 位有頁；沒頁的那些必須是純文字。"""
        con = fs.connect_db()
        try:
            pageless_driver = next(
                r[0] for r in con.execute(
                    "SELECT DISTINCT driver_id FROM results WHERE position_text='1' "
                    "ORDER BY driver_id") if r[0] not in dr.DRIVER_IDS)
            pageless_team = next(
                r[0] for r in con.execute(
                    "SELECT DISTINCT constructor_id FROM results WHERE position_text='1' "
                    "ORDER BY constructor_id") if r[0] not in cg.CONSTRUCTOR_IDS)
        finally:
            con.close()
        self.assertNotIn("<a ", ci.driver_link(pageless_driver, "X"))
        self.assertNotIn("<a ", ci.constructor_link(pageless_team, "X"))
        self.assertIn("<a ", ci.driver_link("hamilton", "X"))
        self.assertIn("<a ", ci.constructor_link("ferrari", "X"))

    def test_out_of_range_season_is_not_linked(self):
        self.assertNotIn("<a ", ci.season_link(gs.FIRST_YEAR - 1, "X"))
        self.assertNotIn("<a ", ci.season_link(gs.LAST_YEAR + 1, "X"))
        self.assertIn("<a ", ci.season_link(gs.LAST_YEAR, "X"))

    def test_a_pageless_winner_really_appears_unlinked_on_a_page(self):
        """沒有這條，上面兩條可能在驗一個實際上不會發生的情境。"""
        body = _body(self.page("charade"))
        self.assertIn("Lotus-Climax", body)
        self.assertNotIn('href="/constructors/', body.split("Lotus-Climax")[0][-160:])


# ---------- 管線接線 ----------

class PipelineWiringTests(unittest.TestCase):
    def test_sitemap_urls_have_index_plus_78(self):
        urls = regen.enumerate_circuit_urls()
        self.assertEqual(len(urls), 79)
        self.assertEqual(urls[0], f"{rc.BASE}/circuits/")

    def test_circuits_is_a_named_sitemap_owner(self):
        """未列名的 part 雖然照收，但排序不確定；百科線四個頁群都要具名。"""
        self.assertIn("circuits", bsm.OWNERS)

    def test_regen_owner_is_the_circuit_generator(self):
        source = (ROOT / "scripts" / "regen-encyclopedia.py").read_text(encoding="utf-8")
        self.assertIn("ci.gen_circuit(cid, con)", source)
        self.assertIn('rc.write_sitemap_part("circuits", enumerate_circuit_urls())', source)

    def test_fingerprints_carry_circuits_and_index(self):
        con = fs.connect_db()
        try:
            fp = regen.compute_fingerprints(con)
        finally:
            con.close()
        self.assertEqual(set(fp["circuits"]), set(ci.CIRCUIT_IDS))
        self.assertIn("circuits", fp["indices"])

    def test_missing_circuits_key_regenerates_everything(self):
        """缺鍵＝沒有指紋＝該頁群全部重生（default-deny）；不得被當成「沒變動所以跳過」。"""
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        fp_path = tmp / "fingerprints.json"
        self.assertEqual(regen.load_fingerprints(fp_path).get("circuits"), {})

        con = fs.connect_db()
        try:
            cur = regen.compute_fingerprints(con)
            prev = {k: v for k, v in cur.items() if k != "circuits"}
            prev["indices"] = {k: v for k, v in cur["indices"].items() if k != "circuits"}
            fp_path.write_text(json.dumps(prev), encoding="utf-8")
            rendered = []
            originals = (regen.ci.render_index, regen.ci.gen_circuit,
                         regen.gs.render_index, regen.gs._render_one_season,
                         regen.dr.render_index, regen.dr.gen_driver,
                         regen.cg.render_index, regen.cg.gen_constructor,
                         regen.gs.render_round, regen.save_fingerprints)
            regen.ci.render_index = lambda c: "circuits-index"
            regen.ci.gen_circuit = lambda cid, c: rendered.append(cid) or {"slug": cid}
            regen.gs.render_index = lambda built: "index"
            regen.gs._render_one_season = lambda year, urls, rounds: None
            regen.dr.render_index = lambda c: "drivers"
            regen.dr.gen_driver = lambda did, c: {"slug": did}
            regen.cg.render_index = lambda c: "constructors"
            regen.cg.gen_constructor = lambda cid, c: {"slug": cid}
            regen.gs.render_round = lambda *a: "round"
            regen.save_fingerprints = lambda *a, **k: None
            try:
                res = regen.selective_regen(con, fp_path=fp_path)
            finally:
                (regen.ci.render_index, regen.ci.gen_circuit,
                 regen.gs.render_index, regen.gs._render_one_season,
                 regen.dr.render_index, regen.dr.gen_driver,
                 regen.cg.render_index, regen.cg.gen_constructor,
                 regen.gs.render_round, regen.save_fingerprints) = originals
        finally:
            con.close()
        self.assertEqual(res["changed_circuits"], list(ci.CIRCUIT_IDS))
        self.assertTrue(res["index_circuits"])
        self.assertEqual(rendered, list(ci.CIRCUIT_IDS))
        self.assertEqual(res["changed_drivers"], [], "只缺 circuits 鍵，不該連別的頁群一起重生")

    def test_zh_table_edit_invalidates_circuit_fingerprints(self):
        """改譯名時 db 一個 byte 都不會動——不切譯名表就會靜默 stale。"""
        con = fs.connect_db()
        try:
            before = regen.compute_fingerprints(con)["circuits"]
            original = regen._file_sha
            regen._file_sha = lambda p: ("deadbeef" if str(p).endswith("circuit-zh.json")
                                         else original(p))
            try:
                after = regen.compute_fingerprints(con)["circuits"]
            finally:
                regen._file_sha = original
        finally:
            con.close()
        self.assertNotEqual(before, after)

    def test_driver_roster_change_invalidates_circuit_fingerprints(self):
        con = fs.connect_db()
        try:
            before = regen.compute_fingerprints(con)["circuits"]
            original = regen.DRIVER_ROSTER
            regen.DRIVER_ROSTER = pathlib.Path("/nonexistent/roster.json")
            try:
                after = regen.compute_fingerprints(con)["circuits"]
            finally:
                regen.DRIVER_ROSTER = original
        finally:
            con.close()
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
