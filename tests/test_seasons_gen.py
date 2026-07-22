#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3 賽季頁生成器回歸測試（gen-racing-seasons.py）。

鎖住四條驗收條件與踩過的錯：
- 進行中賽季不顯示冠軍（把榜首當冠軍的錯）。
- 退賽明細 value == len(detail)（衍生數字紀律）。
- 分差 == 兩列 standings 積分之差（SOURCED − SOURCED）。
- 產出 HTML 除 page_shell 白名單（theme init / GA / JSON-LD）外零 script、零 client fetch；
  外連只限白名單 host（維基 sameAs 與 page_shell 資產）。
- 預設不寫 sitemap part；--publish 才寫。

跑法：python3 -m unittest discover -s tests -v
"""
import argparse
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


g = _load("gen_racing_seasons", "gen-racing-seasons.py")
rc = g.rc
fs = g.fs

# 外連白名單：JSON-LD 的維基 sameAs／schema.org context ＋ page_shell 既有資產（字型/GA/姊妹站/本站）
ALLOWED_HOSTS = {
    "fonts.googleapis.com", "fonts.gstatic.com", "www.googletagmanager.com",
    "schema.org", "en.wikipedia.org",
    "racing.twtools.cc", "twtools.cc", "aire.twtools.cc", "tree.twtools.cc",
    "foootball.twtools.cc", "baseball.twtools.cc", "dvdmaru.com",
}


class IndexInProgressTests(unittest.TestCase):
    """索引頁：進行中賽季不顯示冠軍。"""

    def test_completed_season_shows_champion(self):
        row = g.index_row(2002)
        self.assertFalse(row["in_progress"])
        self.assertIsNotNone(row["driver_champ"])
        self.assertEqual(row["driver_champ"]["id"], "michael_schumacher")
        self.assertIsNotNone(row["constructor_champ"])

    def test_real_in_progress_season_hides_champion(self):
        # 2026 進行中（fs._is_completed=False）——榜首是領先不是冠軍
        row = g.index_row(2026)
        self.assertTrue(row["in_progress"])
        self.assertIsNone(row["driver_champ"])
        self.assertIsNone(row["constructor_champ"])

    def test_monkeypatched_incomplete_hides_champion(self):
        orig = fs._is_completed
        fs._is_completed = lambda y: False
        try:
            row = g.index_row(2002)  # 合成：即使有 2002 榜也不得吐冠軍
            self.assertTrue(row["in_progress"])
            self.assertIsNone(row["driver_champ"])
            self.assertIsNone(row["constructor_champ"])
        finally:
            fs._is_completed = orig

    def test_index_html_marks_in_progress_not_champion(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig_rc, orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig_rc), setattr(g, "PUB", orig_g)))
        g.render_index()
        html = (tmp / "seasons" / "index.html").read_text(encoding="utf-8")
        self.assertIn("進行中", html)  # 2026 那列
        # 2026 那列不得出現「奪冠」語意的積分冠軍名（榜首 antonelli 不得被當冠軍呈現於冠軍欄）
        self.assertNotRegex(html, r"2026[^<]*安東內利")


class RetirementDisciplineTests(unittest.TestCase):
    """退賽分布：value == len(detail)（衍生數字紀律）。"""

    def test_every_category_value_equals_len_detail(self):
        cats = g.season_retirements(2002)
        self.assertTrue(cats)
        for c in cats:
            self.assertEqual(c["value"], len(c["detail"]),
                             f"{c['status']} value 與明細筆數不符")

    def test_finisher_classification(self):
        self.assertTrue(g.is_finisher("Finished"))
        self.assertTrue(g.is_finisher("+1 Lap"))
        self.assertTrue(g.is_finisher("+3 Laps"))
        self.assertFalse(g.is_finisher("Engine"))
        self.assertFalse(g.is_finisher("Collision"))
        self.assertFalse(g.is_finisher("Disqualified"))

    def test_total_retirements_matches_independent_count(self):
        # 獨立重數：直接掃 raw results，非完賽者計數，應等於各類 value 加總
        import glob
        import json
        indep = 0
        for f in sorted(glob.glob(str(g.RAW / "results" / "2002-*.json"))):
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            for r in data.get("Results", []):
                if not g.is_finisher(r.get("status", "")):
                    indep += 1
        self.assertEqual(sum(c["value"] for c in g.season_retirements(2002)), indep)


class PointsGapTests(unittest.TestCase):
    """分差 == 兩列 standings 積分之差。"""

    def test_gap_equals_difference_of_two_standings(self):
        import json
        with open(g.RAW / "standings" / "driver-2002.json", encoding="utf-8") as fh:
            ds = json.load(fh)["DriverStandings"]
        champ = int(ds[0]["points"])
        second = int(ds[1]["points"])
        c, s, gap = g.points_gap(2002)
        self.assertEqual(c, champ)
        self.assertEqual(s, second)
        self.assertEqual(gap, champ - second)
        self.assertEqual(gap, c - s)  # 只做減法


class NarrativeTests(unittest.TestCase):
    """規則化敘事句：模板+資料，每個數字都能在頁面明細找到。"""

    def test_narrative_numbers_are_sourced(self):
        lines = g.season_narrative(2002)
        joined = "".join(lines)
        _, _, gap = g.points_gap(2002)
        total = sum(c["value"] for c in g.season_retirements(2002))
        self.assertIn("17 站", joined)          # 分站數
        self.assertIn(f"{gap} 分", joined)       # 分差
        self.assertIn(f"{total} 人次", joined)   # 退賽總數
        # 冠軍譯名走已核准來源（phase0）——不得只有原文
        self.assertIn("麥可・舒馬克", joined)


class NoScriptNoFetchTests(unittest.TestCase):
    """零 client fetch／除白名單外零 script；外連只限白名單 host。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.orig_rc, self.orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", self.orig_rc), setattr(g, "PUB", self.orig_g)))
        g.render_season(2002)
        self.html = (self.tmp / "seasons" / "2002" / "index.html").read_text(encoding="utf-8")

    def test_no_client_fetch_apis(self):
        for banned in ("fetch(", "XMLHttpRequest", "WebSocket", ".ajax"):
            self.assertNotIn(banned, self.html, f"頁面出現 client fetch 特徵：{banned}")

    def test_only_whitelisted_scripts(self):
        blocks = re.findall(r"<script[^>]*>.*?</script>", self.html, re.S)
        self.assertTrue(blocks)
        for b in blocks:
            ok = ('application/ld+json' in b            # JSON-LD 資料
                  or 'googletagmanager.com/gtag' in b    # GA async（page_shell）
                  or 'gtag(' in b                        # GA config（page_shell）
                  or 'rc-theme' in b                     # theme 預載（防 FOUC）
                  or 'setTheme' in b or 'THEMES' in b)   # theme 切換器
            self.assertTrue(ok, f"非白名單 script：{b[:80]}")

    def test_tabs_are_css_only(self):
        # tabgroup 用 radio + :checked，無 JS；頁面應有 radio input 與 .tablabels
        self.assertIn('type="radio"', self.html)
        self.assertIn('tablabels', self.html)

    def test_external_hosts_whitelisted(self):
        hosts = set(re.findall(r"https?://([a-zA-Z0-9.-]+)", self.html))
        extra = hosts - ALLOWED_HOSTS
        self.assertFalse(extra, f"出現白名單外的外連 host：{extra}")

    def test_jsonld_has_sportsevent_with_place(self):
        # JSON-LD 型別選擇：每站一個 SportsEvent，含 Place（有座標才放 geo）
        self.assertIn('"@type":"SportsEvent"', self.html)
        self.assertIn('"@type":"Place"', self.html)
        self.assertIn('"@type":"GeoCoordinates"', self.html)  # 2002 schedule 有 lat/long


class SitemapGatingTests(unittest.TestCase):
    """M3 預設不寫 sitemap part；--publish 才寫。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.orig_rc, self.orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", self.orig_rc), setattr(g, "PUB", self.orig_g)))
        self.calls = []
        self.orig_ws = rc.write_sitemap_part
        rc.write_sitemap_part = lambda owner, urls: self.calls.append((owner, urls))
        self.addCleanup(lambda: setattr(rc, "write_sitemap_part", self.orig_ws))

    def _run(self, argv):
        orig = argparse.ArgumentParser.parse_args
        import sys
        old = sys.argv
        sys.argv = ["gen-racing-seasons.py"] + argv
        try:
            g.main()
        finally:
            sys.argv = old
            argparse.ArgumentParser.parse_args = orig

    def test_default_does_not_write_sitemap(self):
        self._run(["--index-only"])
        self.assertEqual(self.calls, [])

    def test_publish_writes_sitemap(self):
        self._run(["--index-only", "--publish"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], "seasons")

    def test_no_sitemap_flag_forces_off_even_with_publish(self):
        self._run(["--index-only", "--publish", "--no-sitemap"])
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
