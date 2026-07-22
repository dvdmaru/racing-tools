#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M0 地基重構回歸測試——CSS 外部化、sitemap manifest 化、譯名表 JSON 化、slug 註冊表。

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
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


rc = _load("racinglib_m0", "racinglib.py")
bsm = _load("build_sitemap_m0", "build-sitemap.py")


# ---------- CSS 外部化：shared_css_href() ----------

class SharedCssHrefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.orig_pub = rc.PUB
        self.orig_shared = rc.SHARED_CSS_TEXT
        rc.PUB = self.tmp
        self.addCleanup(setattr, rc, "PUB", self.orig_pub)
        self.addCleanup(setattr, rc, "SHARED_CSS_TEXT", self.orig_shared)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_deterministic_href_and_identical_bytes(self):
        href1 = rc.shared_css_href()
        href2 = rc.shared_css_href()
        self.assertEqual(href1, href2)
        content1 = (self.tmp / "assets" / href1.rsplit("/", 1)[-1]).read_bytes()
        content2 = (self.tmp / "assets" / href2.rsplit("/", 1)[-1]).read_bytes()
        self.assertEqual(content1, content2)

    def test_hash_file_written_under_assets(self):
        href = rc.shared_css_href()
        self.assertTrue(href.startswith("/assets/rc-"))
        fname = href.rsplit("/", 1)[-1]
        fpath = self.tmp / "assets" / fname
        self.assertTrue(fpath.is_file())
        self.assertEqual(fpath.read_text(encoding="utf-8"), rc.SHARED_CSS_TEXT)

    def test_shared_css_text_assembly_order_dark_anchor_last(self):
        self.assertTrue(rc.SHARED_CSS_TEXT.endswith(rc.DARK_ANCHOR_CSS))
        self.assertEqual(
            rc.SHARED_CSS_TEXT,
            rc.SHARED_TOKENS_CSS + rc.THEME_SWITCH_CSS + rc.SITE_HEADER_CSS
            + rc.DATA_CSS + rc.ARTICLE_CSS + rc.DARK_ANCHOR_CSS)

    def test_old_css_versions_pruned_keep_latest_two(self):
        """換版時 assets/ 只留『這次新版＋前一版』兩份，防部署中途切版舊頁 404；
        更舊的必須被清掉。"""
        rc.SHARED_CSS_TEXT = "body{color:red}"
        href1 = rc.shared_css_href()
        rc.SHARED_CSS_TEXT = "body{color:blue}"
        href2 = rc.shared_css_href()
        rc.SHARED_CSS_TEXT = "body{color:green}"
        href3 = rc.shared_css_href()

        files = {p.name for p in (self.tmp / "assets").glob("rc-*.css")}
        fname1 = href1.rsplit("/", 1)[-1]
        fname2 = href2.rsplit("/", 1)[-1]
        fname3 = href3.rsplit("/", 1)[-1]
        self.assertEqual(len(files), 2)
        self.assertIn(fname2, files)
        self.assertIn(fname3, files)
        self.assertNotIn(fname1, files)

    def test_unchanged_content_does_not_rewrite_existing_file(self):
        href = rc.shared_css_href()
        fpath = self.tmp / "assets" / href.rsplit("/", 1)[-1]
        mtime_before = fpath.stat().st_mtime_ns
        rc.shared_css_href()
        self.assertEqual(fpath.stat().st_mtime_ns, mtime_before)


# ---------- sitemap manifest：write_sitemap_part / build-sitemap.py ----------

class WriteSitemapPartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.orig_root = rc.ROOT
        rc.ROOT = self.tmp
        self.addCleanup(setattr, rc, "ROOT", self.orig_root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_writes_one_url_per_line_with_trailing_newline(self):
        rc.write_sitemap_part("standings", ["https://x/standings/"])
        p = self.tmp / "data" / "sitemap-parts" / "standings.txt"
        self.assertEqual(p.read_text(encoding="utf-8"), "https://x/standings/\n")

    def test_multi_url_part_preserves_order(self):
        urls = ["https://x/", "https://x/articles/", "https://x/articles/a/"]
        rc.write_sitemap_part("articles", urls)
        p = self.tmp / "data" / "sitemap-parts" / "articles.txt"
        self.assertEqual(p.read_text(encoding="utf-8").splitlines(), urls)

    def test_unchanged_content_skips_rewrite(self):
        rc.write_sitemap_part("results", ["https://x/results/"])
        p = self.tmp / "data" / "sitemap-parts" / "results.txt"
        mtime_before = p.stat().st_mtime_ns
        rc.write_sitemap_part("results", ["https://x/results/"])
        self.assertEqual(p.stat().st_mtime_ns, mtime_before)

    def test_real_change_rewrites(self):
        rc.write_sitemap_part("calendar", ["https://x/calendar/"])
        p = self.tmp / "data" / "sitemap-parts" / "calendar.txt"
        rc.write_sitemap_part("calendar", ["https://x/calendar/", "https://x/calendar/#extra"])
        self.assertEqual(
            p.read_text(encoding="utf-8").splitlines(),
            ["https://x/calendar/", "https://x/calendar/#extra"])


class BuildSitemapMergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.pub = self.tmp / "public-racing"
        self.parts = self.tmp / "data" / "sitemap-parts"
        self.pub.mkdir(parents=True)
        self.parts.mkdir(parents=True)
        self.orig_root = bsm.ROOT
        self.orig_pub = bsm.rc.PUB
        bsm.ROOT = self.tmp
        bsm.rc.PUB = self.pub
        self.addCleanup(setattr, bsm, "ROOT", self.orig_root)
        self.addCleanup(setattr, bsm.rc, "PUB", self.orig_pub)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _write_part(self, owner, urls):
        (self.parts / f"{owner}.txt").write_text(
            "".join(f"{u}\n" for u in urls), encoding="utf-8")

    def _sitemap_urls(self):
        content = (self.pub / "sitemap.xml").read_text(encoding="utf-8")
        return re.findall(r"<loc>([^<]+)</loc>", content)

    def test_merge_dedup_preserves_owner_order(self):
        self._write_part("articles", ["https://x/", "https://x/articles/"])
        self._write_part("standings", ["https://x/standings/"])
        # 刻意放一個跟 standings 重複的 URL 測去重（保序：第一次出現位置）
        self._write_part("calendar", ["https://x/standings/", "https://x/calendar/"])
        self._write_part("results", ["https://x/results/"])
        bsm.main()
        self.assertEqual(
            self._sitemap_urls(),
            ["https://x/", "https://x/articles/", "https://x/standings/",
             "https://x/calendar/", "https://x/results/"])

    def test_missing_owner_part_warns_but_does_not_crash(self):
        self._write_part("articles", ["https://x/"])
        # standings / calendar / results 三個 part 都缺席
        bsm.main()  # 不應拋例外
        self.assertEqual(self._sitemap_urls(), ["https://x/"])

    def test_missing_parts_dir_exits_1(self):
        shutil.rmtree(self.parts)
        with self.assertRaises(SystemExit) as ctx:
            bsm.main()
        self.assertEqual(ctx.exception.code, 1)

    def test_url_set_equals_union_of_four_parts(self):
        self._write_part("articles", ["https://x/", "https://x/articles/"])
        self._write_part("standings", ["https://x/standings/"])
        self._write_part("calendar", ["https://x/calendar/"])
        self._write_part("results", ["https://x/results/"])
        bsm.main()
        expected = {"https://x/", "https://x/articles/", "https://x/standings/",
                    "https://x/calendar/", "https://x/results/"}
        self.assertEqual(set(self._sitemap_urls()), expected)


class SitemapCallSiteTests(unittest.TestCase):
    """確認 racinglib 不再提供舊版 sitemap_merge，且三個 gen-* 都已改走新介面。"""

    def test_sitemap_merge_removed(self):
        self.assertFalse(hasattr(rc, "sitemap_merge"))

    def test_write_sitemap_part_exists(self):
        self.assertTrue(callable(rc.write_sitemap_part))

    def test_gen_scripts_use_write_sitemap_part_not_old_merge(self):
        for fname, owner in (("gen-racing-standings.py", "standings"),
                              ("gen-racing-calendar.py", "calendar"),
                              ("gen-racing-results.py", "results")):
            src = (ROOT / "scripts" / fname).read_text(encoding="utf-8")
            self.assertNotIn("sitemap_merge", src, fname)
            self.assertIn(f'rc.write_sitemap_part("{owner}"', src, fname)

    def test_update_racing_runs_build_sitemap_after_gens_before_deploy_gate(self):
        src = (ROOT / "scripts" / "update-racing.py").read_text(encoding="utf-8")
        i_results = src.index('gen-racing-results.py')
        i_sitemap = src.index('build-sitemap.py')
        i_gate = src.index("if FAILED:")
        self.assertTrue(i_results < i_sitemap < i_gate,
                         "build-sitemap 必須在三個 gen-* 之後、hard gate 之前執行")


# ---------- 譯名表搬 JSON：等價性（凍結 24+22 條內容） ----------

class RaceCircuitZhMigrationTests(unittest.TestCase):
    OLD_RACE_ZH = {
        "Australian Grand Prix": "澳洲站", "Chinese Grand Prix": "中國站",
        "Japanese Grand Prix": "日本站", "Miami Grand Prix": "邁阿密站",
        "Canadian Grand Prix": "加拿大站", "Monaco Grand Prix": "摩納哥站",
        "Barcelona Grand Prix": "巴塞隆納站", "Austrian Grand Prix": "奧地利站",
        "British Grand Prix": "英國站", "Belgian Grand Prix": "比利時站",
        "Hungarian Grand Prix": "匈牙利站", "Dutch Grand Prix": "荷蘭站",
        "Italian Grand Prix": "義大利站", "Spanish Grand Prix": "西班牙站（馬德里）",
        "Azerbaijan Grand Prix": "亞塞拜然站", "Singapore Grand Prix": "新加坡站",
        "United States Grand Prix": "美國站", "Mexico City Grand Prix": "墨西哥城站",
        "Brazilian Grand Prix": "巴西站", "Las Vegas Grand Prix": "拉斯維加斯站",
        "Qatar Grand Prix": "卡達站", "Abu Dhabi Grand Prix": "阿布達比站",
        "Bahrain Grand Prix": "巴林站", "Saudi Arabian Grand Prix": "沙烏地站",
    }

    OLD_CIRCUIT_ZH = {
        "albert_park": "亞伯特公園賽道（墨爾本）", "shanghai": "上海國際賽車場",
        "suzuka": "鈴鹿賽道", "miami": "邁阿密國際賽道",
        "villeneuve": "維倫紐夫賽道（蒙特婁）", "monaco": "摩納哥街道賽道",
        "catalunya": "加泰隆尼亞賽道（巴塞隆納）", "red_bull_ring": "紅牛環（史匹爾柏格）",
        "silverstone": "銀石賽道", "spa": "斯帕賽道（Spa-Francorchamps）",
        "hungaroring": "匈牙利賽道（Hungaroring）", "zandvoort": "贊德沃特賽道",
        "monza": "蒙札賽道", "madring": "馬德里賽道（Madring）",
        "baku": "巴庫街道賽道", "marina_bay": "濱海灣街道賽道（新加坡）",
        "americas": "美洲賽道（奧斯汀）", "rodriguez": "羅德里格斯兄弟賽道（墨西哥城）",
        "interlagos": "英特拉哥斯賽道（聖保羅）", "vegas": "拉斯維加斯街道賽道",
        "losail": "羅賽爾國際賽道", "yas_marina": "亞斯碼頭賽道（阿布達比）",
    }

    def test_race_zh_count_and_content_frozen(self):
        self.assertEqual(len(rc.RACE_ZH), 24)
        self.assertEqual(rc.RACE_ZH, self.OLD_RACE_ZH)

    def test_circuit_zh_count_and_content_frozen(self):
        self.assertEqual(len(rc.CIRCUIT_ZH), 22)
        self.assertEqual(rc.CIRCUIT_ZH, self.OLD_CIRCUIT_ZH)

    def test_race_zh_json_file_has_no_escaped_unicode(self):
        text = (ROOT / "scripts" / "race-zh.json").read_text(encoding="utf-8")
        self.assertNotIn("\\u", text)

    def test_circuit_zh_json_file_has_no_escaped_unicode(self):
        text = (ROOT / "scripts" / "circuit-zh.json").read_text(encoding="utf-8")
        self.assertNotIn("\\u", text)

    def test_hardcoded_dicts_removed_from_racinglib_source(self):
        src = (ROOT / "scripts" / "racinglib.py").read_text(encoding="utf-8")
        self.assertNotIn('"Australian Grand Prix"', src)
        self.assertNotIn('"albert_park"', src)


# ---------- slug 註冊表 ----------

class SlugRegistryTests(unittest.TestCase):
    SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

    def test_seed_drivers_resolve(self):
        for did, expect in (("michael_schumacher", "michael-schumacher"),
                            ("hamilton", "hamilton"), ("senna", "senna"),
                            ("max_verstappen", "max-verstappen")):
            self.assertEqual(rc.driver_slug(did), expect)

    def test_seed_constructors_resolve(self):
        for cid, expect in (("ferrari", "ferrari"), ("mclaren", "mclaren"),
                            ("mercedes", "mercedes"), ("red_bull", "red-bull")):
            self.assertEqual(rc.constructor_slug(cid), expect)

    def test_unregistered_driver_raises_keyerror(self):
        with self.assertRaises(KeyError):
            rc.driver_slug("verstappen_max_typo")

    def test_unregistered_constructor_raises_keyerror(self):
        with self.assertRaises(KeyError):
            rc.constructor_slug("not_registered")

    def test_all_slugs_kebab_case(self):
        for group in ("drivers", "constructors"):
            for slug in rc._SLUGS[group].values():
                self.assertRegex(slug, self.SLUG_RE, f"{group}: {slug}")

    def test_driver_slugs_are_unique(self):
        slugs = list(rc._SLUGS["drivers"].values())
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_constructor_slugs_are_unique(self):
        slugs = list(rc._SLUGS["constructors"].values())
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_driver_ids_are_unique(self):
        ids = list(rc._SLUGS["drivers"].keys())
        self.assertEqual(len(ids), len(set(ids)))

    def test_constructor_ids_are_unique(self):
        ids = list(rc._SLUGS["constructors"].keys())
        self.assertEqual(len(ids), len(set(ids)))

    def test_slugs_json_is_append_only_comment_present(self):
        raw = (ROOT / "data" / "f1" / "slugs.json").read_text(encoding="utf-8")
        self.assertIn("append-only", raw)


if __name__ == "__main__":
    unittest.main()
