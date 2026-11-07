#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""站群自有版位（scripts/adslots.py）回歸測試。

釘住 Charlie 2026-11-07 的裁定：
- 只有首頁主推位＋原生版位，原生每頁最多 2 則；不做彈窗。
- 「零 client fetch」站規的版位例外只限首頁與文章相關頁；百科／數據頁一律不放版位、不載版位程式。
- 預設卡標「推廣」、連結帶 noopener；版位程式不准用 innerHTML 類寫法（設定檔內容一律當純文字）。
- 曝光＝一半以上進畫面且停留 1 秒（GA4 view_promotion），點擊＝select_promotion。
"""
import importlib.util
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PUB = ROOT / "public-racing"

spec = importlib.util.spec_from_file_location("adslots_t", ROOT / "scripts" / "adslots.py")
ads = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ads)

SLOT_RE = re.compile(r'<a class="ad-slot[^"]*" data-ad-slot="([a-z_]+)"[^>]*>')
SCRIPT_RE = re.compile(r'<script src="(/assets/ad-[0-9a-f]{10}\.js)" defer></script>')


def _read(rel):
    return (PUB / rel).read_text(encoding="utf-8")


def _slots(html):
    return SLOT_RE.findall(html)


def _article_pages():
    return sorted((PUB / "articles").glob("*/index.html"))


class PlacementTests(unittest.TestCase):
    def test_home_has_one_hero_and_one_native(self):
        self.assertEqual(sorted(_slots(_read("index.html"))), ["home_hero", "native_list"])

    def test_articles_index_has_one_native(self):
        self.assertEqual(_slots(_read("articles/index.html")), ["native_list"])

    def test_every_article_has_exactly_one_end_slot(self):
        pages = _article_pages()
        self.assertGreater(len(pages), 0)
        for p in pages:
            with self.subTest(page=p.parent.name):
                self.assertEqual(_slots(p.read_text(encoding="utf-8")), ["native_end"])

    def test_native_at_most_two_per_page(self):
        for p in [PUB / "index.html", PUB / "articles" / "index.html"] + _article_pages():
            html = p.read_text(encoding="utf-8")
            n = sum(1 for s in _slots(html) if s.startswith("native"))
            self.assertLessEqual(n, 2, p)

    def test_hero_is_below_next_race_and_outside_h1(self):
        html = _read("index.html")
        h1_end = html.index("</h1>")
        nxt = html.index('class="next-race"')
        hero = html.index('data-ad-slot="home_hero"')
        self.assertLess(h1_end, hero)
        self.assertLess(nxt, hero)

    def test_native_list_is_third_card(self):
        html = _read("index.html")
        grid = html[html.index('<div class="idx-grid">'):]
        cards = re.findall(r'<a class="(idx-card|ad-slot[^"]*)"', grid)
        self.assertEqual(cards[2].split()[0], "ad-slot")
        self.assertTrue(all(c == "idx-card" for c in cards[:2]))


class NormalLookTests(unittest.TestCase):
    """沒有檔期時網站要跟原本一樣：版位隱藏、首頁照舊 6 篇文章。"""

    def test_all_slots_hidden_in_html(self):
        for p in [PUB / "index.html", PUB / "articles" / "index.html"] + _article_pages()[:5]:
            html = p.read_text(encoding="utf-8")
            for tag in re.findall(r'<a class="ad-slot[^>]*>', html):
                self.assertTrue(tag.endswith(" hidden>"), (p, tag))

    def test_home_keeps_six_articles_with_one_yield_card(self):
        html = _read("index.html")
        grid = html[html.index('<div class="idx-grid">'):]
        self.assertEqual(len(re.findall(r'<a class="idx-card"', grid)), 6)
        self.assertEqual(grid.count('data-ad-yield="native_list"'), 1)

    def test_preview_skips_ga_and_time_window(self):
        js = ads.JS_TEXT
        self.assertIn("ad-preview=1", js)
        self.assertIn("if(PREVIEW||typeof window.gtag!=='function')return;", js)
        self.assertIn("return PREVIEW||(a<=now&&now<b);", js)


class ScopeTests(unittest.TestCase):
    """版位例外只限首頁與文章相關頁：百科／數據頁不放版位、不載版位程式。"""
    NO_ADS = ["standings", "calendar", "results", "seasons", "drivers", "constructors",
              "circuits", "guide", "errata", "rounds"]

    def test_data_and_encyclopedia_pages_have_no_ads(self):
        checked = 0
        for d in self.NO_ADS:
            root = PUB / d
            if not root.exists():
                continue
            for p in root.rglob("index.html"):
                html = p.read_text(encoding="utf-8")
                with self.subTest(page=str(p.relative_to(PUB))):
                    self.assertNotIn("ad-slot", html)
                    self.assertIsNone(SCRIPT_RE.search(html))
                checked += 1
        self.assertGreater(checked, 50, "應該掃到大量百科／數據頁")


class MarkupTests(unittest.TestCase):
    def test_fallback_card_label_and_rel(self):
        for slot in ("home_hero", "native_list", "native_end"):
            h = ads.slot_html(slot)
            with self.subTest(slot=slot):
                self.assertIn('<span class="ad-label">推廣</span>', h)
                self.assertIn(' hidden>', h, "平常要隱藏：沒有檔期時網站維持原本的樣子")
                self.assertIn('rel="noopener"', h)
                self.assertIn('href="https://', h)
                self.assertNotIn("<h1", h)

    def test_unknown_slot_rejected(self):
        with self.assertRaises(ValueError):
            ads.slot_html("popup")

    def test_pages_reference_existing_script(self):
        for p in [PUB / "index.html", PUB / "articles" / "index.html", _article_pages()[0]]:
            m = SCRIPT_RE.search(p.read_text(encoding="utf-8"))
            self.assertIsNotNone(m, p)
            self.assertTrue((PUB / m.group(1).lstrip("/")).exists(), m.group(1))


class ScriptTests(unittest.TestCase):
    JS = ads.JS_TEXT

    def test_never_writes_html_from_config(self):
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(banned, self.JS)

    def test_reads_only_central_config(self):
        self.assertEqual(self.JS.count("fetch("), 1)
        self.assertIn('"https://twtools.cc/ad-slots.json"', self.JS)

    def test_viewability_rule(self):
        self.assertIn("IntersectionObserver", self.JS)
        self.assertIn("intersectionRatio>=0.5", self.JS)
        self.assertIn(",1000)", self.JS)
        self.assertIn("'view_promotion'", self.JS)
        self.assertIn("'select_promotion'", self.JS)

    def test_paid_links_marked_sponsored(self):
        self.assertIn("c.tier==='paid'?'sponsored noopener'", self.JS)
        self.assertIn("c.tier==='paid'?'贊助':'推廣'", self.JS)

    def test_https_only(self):
        self.assertIn("x.protocol==='https:'", self.JS)


if __name__ == "__main__":
    unittest.main()
