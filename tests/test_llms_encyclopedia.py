#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llms.txt 的百科區段：清單必須推導、數字必須推算、沒接上的線不准假裝有。

## 由來（2026-08-23）

`public-racing/llms.txt` 原本只列首頁／standings／calendar／results／articles 五條，
`/seasons/`、`/drivers/`、`/constructors/` **一條都沒有**——那是全站 97% 的頁面。
照著 llms.txt 讀的引擎會以為這個站只有 5 個資料頁加 10 篇文章。

## 這裡釘三件事

1. **清單推導自單一資料源**（`data/sitemap-parts/<owner>.txt`，即 regen-encyclopedia
   的 `enumerate_*_urls()` 落地輸出）。手寫清單只會「對某一批完工」，之後靜默腐蝕。
2. **數字一律推算**。llms.txt 曾寫死「全季 22 站」，賽曆一變就永遠錯下去
   （2026-08-01 事故，check-site-facts.py 因此誕生）。
3. **存在才列**。part 檔不在＝那條線還沒接上，llms.txt 不准先列出 404。
   反過來，part 檔一旦出現就必須自動被列進去，不需要有人回來改這支程式。

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ba = _load("build_articles", "build-articles.py")
rc = ba.rc
BASE = ba.BASE


class PartsAreTheSingleSource(unittest.TestCase):
    """百科 URL 全部來自 sitemap part，一條不多、一條不少。"""

    def setUp(self):
        self.orig = rc.ENCYCLOPEDIA_PUBLISHED
        rc.ENCYCLOPEDIA_PUBLISHED = True
        self.addCleanup(setattr, rc, "ENCYCLOPEDIA_PUBLISHED", self.orig)

    def test_every_part_url_appears(self):
        out = ba.render_encyclopedia_llms()
        for owner, _label, _path, _gist in ba.ENCYCLOPEDIA_LINES:
            for url in ba._part_urls(owner):
                self.assertIn(url, out, f"{owner} 的 {url} 沒進 llms.txt")

    def test_no_url_outside_the_parts(self):
        """反向：llms.txt 百科段不准冒出 part 裡沒有的 URL（手寫殘留／拼錯）。"""
        known = set()
        for owner, _l, _p, _g in ba.ENCYCLOPEDIA_LINES:
            known |= set(ba._part_urls(owner))
        listed = {line[2:].strip() for line in ba.render_encyclopedia_llms().splitlines()
                  if line.startswith("- ") and not line.startswith("- [")}
        self.assertEqual(listed - known, set())

    def test_three_encyclopedia_lines_present_in_built_llms_txt(self):
        """產物實查：三條百科線的索引頁都要出現在 public-racing/llms.txt。"""
        txt = (ROOT / "public-racing" / "llms.txt").read_text(encoding="utf-8")
        for path in ("/seasons/", "/drivers/", "/constructors/"):
            self.assertIn(f"{BASE}{path}", txt, f"llms.txt 缺 {path}")


class NumbersAreComputed(unittest.TestCase):
    """任何進 llms.txt 的數字都必須由這次讀到的清單算出來。"""

    def setUp(self):
        self.orig_pub = rc.ENCYCLOPEDIA_PUBLISHED
        self.orig_dir = ba.PARTS_DIR
        rc.ENCYCLOPEDIA_PUBLISHED = True
        self.addCleanup(setattr, rc, "ENCYCLOPEDIA_PUBLISHED", self.orig_pub)
        self.addCleanup(setattr, ba, "PARTS_DIR", self.orig_dir)

    def _fake_parts(self, mapping):
        import tempfile
        tmp = pathlib.Path(tempfile.mkdtemp())
        for owner, urls in mapping.items():
            (tmp / f"{owner}.txt").write_text("".join(f"{u}\n" for u in urls), encoding="utf-8")
        ba.PARTS_DIR = tmp
        return tmp

    def test_page_count_follows_the_list(self):
        self._fake_parts({"drivers": [f"{BASE}/drivers/", f"{BASE}/drivers/a/",
                                      f"{BASE}/drivers/b/"]})
        self.assertIn("共 3 頁", ba.render_encyclopedia_llms())

    def test_page_count_changes_when_the_list_changes(self):
        """反向：清單少一頁，數字必須跟著變——不然那個「3」可能是寫死的。"""
        self._fake_parts({"drivers": [f"{BASE}/drivers/", f"{BASE}/drivers/a/"]})
        out = ba.render_encyclopedia_llms()
        self.assertIn("共 2 頁", out)
        self.assertNotIn("共 3 頁", out)

    def test_season_span_is_derived_from_urls(self):
        self._fake_parts({"seasons": [f"{BASE}/seasons/", f"{BASE}/seasons/1999/",
                                      f"{BASE}/seasons/2001/"]})
        self.assertIn("涵蓋 1999 至 2001 年", ba.render_encyclopedia_llms())

    def test_no_race_count_claim_in_encyclopedia_block(self):
        """百科段不准出現「N 站」這種當季事實宣稱（check-site-facts 管的正是它）。"""
        import re
        self.assertIsNone(re.search(r"[0-9]\s*站", ba.render_encyclopedia_llms()))


class ExistOnlyGate(unittest.TestCase):
    """part 檔存在才列；不存在不列；published:false 全段不出現。"""

    def setUp(self):
        self.orig_pub = rc.ENCYCLOPEDIA_PUBLISHED
        self.orig_dir = ba.PARTS_DIR
        self.addCleanup(setattr, rc, "ENCYCLOPEDIA_PUBLISHED", self.orig_pub)
        self.addCleanup(setattr, ba, "PARTS_DIR", self.orig_dir)
        import tempfile
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        ba.PARTS_DIR = self.tmp
        rc.ENCYCLOPEDIA_PUBLISHED = True

    def test_missing_part_is_not_listed(self):
        (self.tmp / "seasons.txt").write_text(f"{BASE}/seasons/\n", encoding="utf-8")
        out = ba.render_encyclopedia_llms()
        self.assertIn("/seasons/", out)
        self.assertNotIn("/circuits/", out)   # 該線還沒接上 → 不准先列 404

    def test_new_part_is_picked_up_without_code_change(self):
        """circuits part 一出現就要自動被列——這是「存在才列」的另一半。"""
        (self.tmp / "circuits.txt").write_text(
            f"{BASE}/circuits/\n{BASE}/circuits/monza/\n", encoding="utf-8")
        out = ba.render_encyclopedia_llms()
        self.assertIn(f"{BASE}/circuits/monza/", out)

    def test_nothing_when_encyclopedia_unpublished(self):
        (self.tmp / "seasons.txt").write_text(f"{BASE}/seasons/\n", encoding="utf-8")
        rc.ENCYCLOPEDIA_PUBLISHED = False
        self.assertEqual(ba.render_encyclopedia_llms(), "")


class SourceAttribution(unittest.TestCase):
    """每個區段都要講清楚資料源與出處，不是只丟一串 URL。"""

    def setUp(self):
        self.orig = rc.ENCYCLOPEDIA_PUBLISHED
        rc.ENCYCLOPEDIA_PUBLISHED = True
        self.addCleanup(setattr, rc, "ENCYCLOPEDIA_PUBLISHED", self.orig)

    def test_each_section_states_jolpica_and_provenance(self):
        out = ba.render_encyclopedia_llms()
        sections = [b for b in out.split("## ") if b.strip()]
        self.assertGreaterEqual(len(sections), 3)
        for sec in sections:
            self.assertIn("jolpica-f1", sec)
            self.assertIn("志願者維護的開源專案", sec)
            self.assertIn("來源快照檔", sec)


if __name__ == "__main__":
    unittest.main()
