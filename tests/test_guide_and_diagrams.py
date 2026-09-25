#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 新手村基建回歸測試：內嵌 SVG 通道＋/guide/ 入口頁＋文末導覽＋各入口的 published gate。

釘住的東西：
1. SVG 通道：markdown（extra＋sane_lists）原樣放行 figure/svg；互鏈全鏈（車手→分站→車隊）
   不會把 <a> 塞進 <text>／<title>／<desc>／figcaption；摘要不取圖。
2. /guide/：只列 approved 且已 build 的 slug、空層級不渲染、順序依 guide.json、零死連結。
3. published gate：未公開時導覽／首頁磚／llms.txt 全暗，公開後全亮（負向控制＝兩邊都測）。
4. 文章頁：在 guide 內的 slug 文末有「新手村 · 回入口頁」＋同層上一篇／下一篇；不在的沒有。

fixture 一律自帶，不讀 config/guide.json 的真實 slugs（上線前它是空的）。
"""
import importlib.util
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

import markdown as md_lib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


sys.path.insert(0, str(ROOT / "scripts"))   # build-articles 內 `import stability`
ba = _load("build_articles_guide_test", "build-articles.py")
rc = ba.rc
il = ba.il

# ☠️ page_shell 會把共用 CSS 寫進 rc.PUB/assets（並清舊檔）——測試必須導去 tmp，
# 否則跑測試就會動到版控裡的 public-racing/assets。
_TMP = tempfile.TemporaryDirectory()
_orig_pub = rc.PUB


def setUpModule():
    rc.PUB = pathlib.Path(_TMP.name)


def tearDownModule():
    rc.PUB = _orig_pub
    _TMP.cleanup()

FIGURE = """<figure class="diagram">
<svg viewBox="0 0 640 260" role="img" aria-label="示意：維斯塔潘與法拉利的位置">
<title>示意圖</title>
<desc>維斯塔潘在法拉利前方</desc>
<g>
<rect class="d-surface d-line-s" x="10" y="10" width="620" height="240" rx="12"/>
<text class="d-fg" x="30" y="60">維斯塔潘</text>
<text class="d-dim" x="30" y="100">法拉利</text>
</g>
</svg>
<figcaption>圖：維斯塔潘與法拉利</figcaption>
</figure>"""


def art(slug, title, date="2026-09-01", typ="guide"):
    return {"slug": slug, "meta": {"title": title, "date": date, "type": typ},
            "excerpt": f"{title}的摘要內容" * 3}


ARTICLES = [art("a-one", "第一篇 F1 入門"), art("a-two", "第二篇 賽車構造"),
            art("a-three", "第三篇 進站策略"), art("outsider", "不在新手村的文章")]

FIXTURE = {
    "published": True,
    "title": "F1 新手村",
    "intro": "測試用簡介。",
    "levels": [
        {"id": "race", "title": "看懂比賽", "blurb": "比賽怎麼進行。",
         "slugs": ["a-two", "a-one", "unapproved-x", "a-one"]},
        {"id": "car", "title": "看懂賽車", "blurb": "空層級不該出現。", "slugs": ["not-built"]},
        {"id": "strategy", "title": "看懂策略", "slugs": ["a-three"]},
        {"id": "data", "title": "看懂數據", "slugs": []},
    ],
}


def has_pangu_gap(s):
    """中文與英數之間缺半形空格（title/description 會被站上測試掃）。"""
    return bool(re.search(r"[一-鿿][A-Za-z0-9]|[A-Za-z0-9][一-鿿]", s))


class SvgChannelTests(unittest.TestCase):
    def _md(self, body):
        return md_lib.markdown(body, extensions=["extra", "sane_lists"])

    def test_markdown_passes_figure_through_verbatim(self):
        out = self._md("前文一段。\n\n" + FIGURE + "\n\n後文一段。\n")
        self.assertIn(FIGURE, out)
        self.assertIn("<p>前文一段。</p>", out)
        self.assertIn("<p>後文一段。</p>", out)

    def test_markdown_tolerates_blank_line_inside_figure(self):
        """規則寫「內部不得有空行」是保險；實測 markdown 對單一空行也原樣放行（釘住現況）。"""
        fig = FIGURE.replace("<title>", "\n<title>")
        self.assertIn(fig, self._md("前\n\n" + fig + "\n\n後\n"))

    def test_full_link_chain_never_touches_svg(self):
        """車手→分站→車隊三支互鏈器串起來跑（同 build 順序）：圖內零 <a>，圖外同名照連。"""
        html = self._md("<p>x</p>\n\n" + FIGURE + "\n\n維斯塔潘與法拉利在正文出現。\n")
        html, drivers = il.linkify(html)
        html, _rounds = il.linkify_rounds(html, 2026)
        html, teams = il.linkify_teams(html)
        fig = html[html.index("<figure"):html.index("</figure>")]
        self.assertNotIn("<a ", fig)
        self.assertIn(FIGURE, html, "圖區塊必須 byte 原樣")
        self.assertTrue(drivers and teams, "圖外正文的同名仍要被連（陰性對照）")
        self.assertIn("<a ", html[html.index("</figure>"):])

    def test_excerpt_skips_figure_paragraph(self):
        body = FIGURE + "\n\n這是第一段真正的文字。\n"
        self.assertEqual(rc.extract_excerpt(body), "這是第一段真正的文字。")

    def test_diagram_css_and_theme_variables(self):
        css = rc.ARTICLE_CSS
        for needle in (".prose figure.diagram", "figure.diagram svg", "max-width: 100%", "height: auto",
                       "figcaption", "var(--dim)"):
            self.assertIn(needle, css)
        for cls, var in (("d-fg", "--fg"), ("d-dim", "--dim"), ("d-line", "--line-2"),
                         ("d-accent", "--accent"), ("d-surface", "--surface")):
            self.assertRegex(css, rf"\.{cls}\s*\{{\s*fill:\s*var\({var}\)")
            self.assertRegex(css, rf"\.{cls}-s\s*\{{\s*stroke:\s*var\({var}\)")

    def test_author_rules_documented(self):
        doc = (ROOT / "scripts" / "prompts" / "external-sourced.md").read_text(encoding="utf-8")
        self.assertIn("示意圖（SVG）", doc)
        for needle in ("viewBox", "<title>", "<desc>", "role=\"img\"", "aria-label", "空行", "d-accent"):
            self.assertIn(needle, doc)


class GuideLevelsTests(unittest.TestCase):
    def test_only_built_slugs_in_guide_order_and_empty_levels_dropped(self):
        got = [(lv["id"], [a["slug"] for a in items]) for lv, items in ba.guide_levels(ARTICLES, FIXTURE)]
        self.assertEqual(got, [("race", ["a-two", "a-one"]), ("strategy", ["a-three"])])

    def test_no_articles_means_no_levels(self):
        self.assertEqual(ba.guide_levels([], FIXTURE), [])

    def test_shipped_config_structure_and_slugs_resolve(self):
        """出貨設定：四個層級固定；每個 slug 必須對到真實存在的 articles/<slug>/index.md，且全庫不重複。
        （published 開關是上線決定，不在這裡釘死；入口頁本身只列 approved 且已 build 的 slug。）"""
        g = rc.load_guide_config()
        self.assertEqual([lv["id"] for lv in g["levels"]], ["race", "car", "strategy", "data"])
        self.assertEqual([lv["title"] for lv in g["levels"]],
                         ["看懂比賽", "看懂賽車", "看懂策略", "看懂數據"])
        slugs = [s for lv in g["levels"] for s in lv["slugs"]]
        self.assertEqual(len(slugs), len(set(slugs)), "同一篇不可出現在兩個層級或重複")
        for s in slugs:
            self.assertTrue((ba.ROOT / "articles" / s / "index.md").exists(), f"guide.json 的 {s} 找不到文章檔")


class GuideIndexPageTests(unittest.TestCase):
    def setUp(self):
        self.html = ba.render_guide_index(ARTICLES, FIXTURE)

    def test_head_metadata(self):
        self.assertIn('<link rel="canonical" href="https://racing.twtools.cc/guide/">', self.html)
        self.assertIn("<title>F1 新手村 | 賽車數據誌</title>", self.html)
        self.assertIn('<meta property="og:title" content="F1 新手村">', self.html)
        self.assertIn('<meta property="og:url" content="https://racing.twtools.cc/guide/">', self.html)
        self.assertIn('name="description"', self.html)
        self.assertIn('"BreadcrumbList"', self.html)

    def test_pangu_in_title_desc_og(self):
        for pat in (r"<title>(.*?)</title>", r'name="description" content="(.*?)"',
                    r'og:title" content="(.*?)"', r'og:description" content="(.*?)"'):
            s = re.search(pat, self.html).group(1)
            self.assertFalse(has_pangu_gap(s), s)

    def test_lists_only_built_slugs_and_no_dead_links(self):
        links = re.findall(r'href="/articles/([^/"]+)/"', self.html)
        self.assertEqual(links, ["a-two", "a-one", "a-three"])
        self.assertNotIn("unapproved-x", self.html)
        self.assertNotIn("not-built", self.html)
        self.assertNotIn("outsider", self.html)

    def test_empty_levels_not_rendered(self):
        self.assertIn("看懂比賽", self.html)
        self.assertIn("看懂策略", self.html)
        body = self.html[self.html.index('<h1 class="idx-h1">'):self.html.index('<div class="article-footer">')]
        self.assertNotIn("看懂賽車", body)
        self.assertNotIn('id="lv-car"', body)
        self.assertNotIn("空層級不該出現", body)
        self.assertNotIn("看懂數據", body)

    def test_kicker_reuses_guide_label(self):
        self.assertIn("長青指南", self.html)

    def test_zero_articles_renders_placeholder_not_empty_shell(self):
        html = ba.render_guide_index([], FIXTURE)
        self.assertIn("新手村整理中", html)
        self.assertNotIn('class="gd-level"', html)
        self.assertNotIn("/articles/a-one/", html)

    def test_active_nav_key_is_guide(self):
        with mock.patch.object(rc, "GUIDE_PUBLISHED", True):
            html = ba.render_guide_index(ARTICLES, FIXTURE)
        self.assertRegex(html, r'<a href="/guide/" class="active">新手村</a>')


class GuideNavOnArticleTests(unittest.TestCase):
    def test_middle_article_has_prev_next_and_back_link(self):
        h = ba.guide_nav_html("a-one", ARTICLES, FIXTURE)
        self.assertIn('href="/guide/"', h)
        self.assertIn("新手村 · 回入口頁", h)
        self.assertIn('href="/articles/a-two/"', h)      # 同層上一篇
        self.assertNotIn("a-three", h)                    # 不同層不算下一篇
        self.assertIn("看懂比賽 第 2 / 2 篇", h)

    def test_first_article_has_only_next(self):
        h = ba.guide_nav_html("a-two", ARTICLES, FIXTURE)
        self.assertIn("新手村下一篇", h)
        self.assertNotIn("新手村上一篇", h)

    def test_non_guide_article_gets_nothing(self):
        self.assertEqual(ba.guide_nav_html("outsider", ARTICLES, FIXTURE), "")

    def test_unbuilt_neighbour_is_never_linked(self):
        h = ba.guide_nav_html("a-one", ARTICLES, FIXTURE)
        self.assertNotIn("unapproved-x", h)

    def test_render_article_places_guide_nav_before_timeline_nav(self):
        a = ARTICLES[0]
        gn = ba.guide_nav_html("a-one", ARTICLES, FIXTURE)
        with_g = ba.render_article(a["meta"], "<p>內文</p>", "a-one", a["excerpt"], [],
                                   prev_nav=ARTICLES[1], next_nav=None, guide_nav=gn)
        self.assertLess(with_g.index('class="guide-nav"'), with_g.index('class="art-nav"'))
        # 陰性對照：不帶 guide_nav 的文章輸出裡完全沒有這塊（既有文章 byte 不變的前提）
        without = ba.render_article(a["meta"], "<p>內文</p>", "a-one", a["excerpt"], [],
                                    prev_nav=ARTICLES[1], next_nav=None)
        self.assertNotIn("guide-nav", without.replace(".guide-nav", ""))
        # 「新手村」三字會出現在全站導覽列（published＝true 時），所以只驗文末導覽區塊獨有的字串
        self.assertNotIn("新手村 · 回入口頁", without)


class PublishedGateTests(unittest.TestCase):
    def test_nav_item_visible_follows_guide_flag(self):
        item = {"label": "新手村", "href": "/guide/", "key": "guide", "requires": "guide"}
        with mock.patch.object(rc, "GUIDE_PUBLISHED", False):
            self.assertFalse(rc.nav_item_visible(item))
            self.assertNotIn('href="/guide/"', rc.site_header_html("home"))
        with mock.patch.object(rc, "GUIDE_PUBLISHED", True):
            self.assertTrue(rc.nav_item_visible(item))
            self.assertIn('<a href="/guide/">新手村</a>', rc.site_header_html("home"))

    def test_site_json_nav_declares_guide_gate(self):
        nav = [n for n in rc.SITE["nav"] if n.get("href") == "/guide/"]
        self.assertEqual(len(nav), 1)
        self.assertEqual((nav[0]["label"], nav[0]["key"], nav[0].get("requires")),
                         ("新手村", "guide", "guide"))

    def test_encyclopedia_gate_unchanged(self):
        enc = {"href": "/drivers/", "requires": "encyclopedia"}
        with mock.patch.object(rc, "ENCYCLOPEDIA_PUBLISHED", False):
            self.assertFalse(rc.nav_item_visible(enc))
        with mock.patch.object(rc, "ENCYCLOPEDIA_PUBLISHED", True):
            self.assertTrue(rc.nav_item_visible(enc))
        self.assertTrue(rc.nav_item_visible({"href": "/articles/"}))

    def test_llms_line_gated(self):
        with mock.patch.object(rc, "GUIDE_PUBLISHED", False):
            self.assertNotIn("/guide/", ba.render_llms_txt(ARTICLES))
        with mock.patch.object(rc, "GUIDE_PUBLISHED", True):
            txt = ba.render_llms_txt(ARTICLES)
        self.assertIn("[F1 新手村](https://racing.twtools.cc/guide/)", txt)

    def test_home_tile_gated(self):
        with mock.patch.object(rc, "GUIDE_PUBLISHED", False):
            self.assertNotIn('href="/guide/"', ba.render_home(ARTICLES))
        with mock.patch.object(rc, "GUIDE_PUBLISHED", True):
            home = ba.render_home(ARTICLES)
        self.assertIn('<a class="tile" href="/guide/">', home)


if __name__ == "__main__":
    unittest.main()
