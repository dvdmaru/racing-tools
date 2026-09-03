#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文章 ↔ 分站頁雙向互鏈 回歸測試（scripts/interlink.py 的 round 那一半）。

沿用車手互鏈（test_article_interlink.py）同一組紀律，另外釘住這條延伸獨有的風險：

☠️ **年份消歧**——「匈牙利站」在 2002（R13）與 2026（R11）各有一頁，字串本身決定不了年份。
   判定唯一依據＝文章 frontmatter 明示的 season。本檔最重要的一條負向測試就是
   「2026 的匈牙利文章不得連到 2002 那頁」；少了它，把年份寫死成任何一個值都會全綠。

其餘釘住的東西：
1. 正向：只連**已建頁**的場次（未完賽的荷蘭站 R12 沒有頁 → 不連）、只認 approved 中文站名。
2. 保護區真的擋得住：「匈牙利站」會出現在標題／H2 裡（真實素材：兩篇匈牙利文章的標題），
   標題內不得長出連結；表格／code／既有 <a> 同理。
3. 「第 N 站」數字型指涉不連。
4. strip-tags：互鏈前後文章純文字完全相同；分站頁只多出「相關報導」區塊本身。
5. 指紋：新增一篇提到某站的文章 → 該分站頁指紋變、該季總覽與 /seasons/ 索引指紋不變，
   且選擇性重生只重寫那一頁。
6. 死連結 0：文章指向的分站頁、分站頁列的文章，都要有對應產出。

跑法：python3 -m unittest discover -s tests -v
"""
import hashlib
import html as html_lib
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
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ⚠️ 一律借 regen 的模組圖（同 test_article_interlink 的理由）：各生成器內部各自 importlib
# 載入，自己再載一份 gs/interlink 會拿到**不同的物件**，patch 不生效、產物還會寫進真的 repo。
re_mod = _load("regen_encyclopedia", "regen-encyclopedia.py")
il = re_mod.il
rc = re_mod.rc
gs = re_mod.gs
dr = re_mod.dr
fs = re_mod.fs
p0 = re_mod.p0

HUNGARY_REPORT = "f1-2026-r11-hungary-report"
HUNGARY_BLUE_FLAG = "f1-2026-r11-hungary-blue-flag-failure"
# 2026-08-24 R12 已賽，樣本推進：荷蘭站戰報末段提「下一站」義大利站（R13，尚未完賽）
# ——拿真實素材頂替原本用 HUNGARY_REPORT 提荷蘭站當「未賽站」負向控制的那一段。
DUTCH_REPORT = "f1-2026-r12-dutch-report"


def strip_tags(html):
    return html_lib.unescape(re.sub(r"<[^>]+>", "", html))


def article_body_html(art):
    """照 build-articles.py 的順序把一篇真實文章渲染成 body HTML（尚未互鏈）。"""
    import markdown as md_lib
    body = rc.strip_h1(rc.parse_frontmatter(art["text"])[1])
    return md_lib.markdown(body, extensions=["extra", "sane_lists"])


def published_by_slug():
    return {a["slug"]: a for a in il.published_articles()}


# ============================================================
# 1. 判定表：哪一站可以被連
# ============================================================

class RoundLinkIndexTests(unittest.TestCase):
    def setUp(self):
        il.clear_caches()
        self.addCleanup(il.clear_caches)

    def test_hungary_resolves_per_year(self):
        """同一個站名在兩個 round_year 各對到不同站次——年份消歧的前提。"""
        self.assertEqual(il.round_link_index(2026)["匈牙利站"], (2026, 11))
        self.assertEqual(il.round_link_index(2002)["匈牙利站"], (2002, 13))

    def test_unraced_round_has_no_page_and_is_not_linkable(self):
        """2026-08-24 R12 已賽/tsunoda 擴編，樣本推進：R12 荷蘭站已完賽，
        改用 R13 義大利站尚未完賽＝沒有分站頁 → 判定表不得收（收了就是死連結）。"""
        idx = il.round_link_index(2026)
        self.assertNotIn("義大利站", idx)
        built = set(gs.season_round_numbers(2026))
        self.assertNotIn(13, built, "前提：R13 要真的還沒有頁，否則這條在測空氣")
        self.assertTrue(all(r in built for _y, r in idx.values()))

    def test_non_round_year_is_empty(self):
        """不在 config round_years 的賽季完全沒有分站頁 → 空表。"""
        for year in (2005, 1999, 2025, None):
            self.assertEqual(il.round_link_index(year), {})

    def test_every_token_is_an_approved_translation(self):
        """只認 race-zh.json 的 approved 值，不自譯、不截短。"""
        approved = set(rc.RACE_ZH.values())
        for year in (2002, 2026):
            for token in il.round_link_index(year):
                self.assertIn(token, approved, f"{token} 不是已核准站名")

    def test_targets_have_real_pages(self):
        pub = ROOT / "public-racing" / "seasons"
        if not pub.exists():
            self.skipTest("public-racing 不在（乾淨 checkout）")
        for year in (2002, 2026):
            for _tok, (y, r) in il.round_link_index(year).items():
                self.assertTrue((pub / str(y) / "rounds" / str(r) / "index.html").is_file(),
                                f"/seasons/{y}/rounds/{r}/ 沒有產出")


# ============================================================
# 2. 年份消歧：文章的賽季脈絡怎麼決定
# ============================================================

class ArticleSeasonTests(unittest.TestCase):
    def setUp(self):
        il.clear_caches()
        self.addCleanup(il.clear_caches)

    def test_explicit_season_frontmatter_wins(self):
        arts = published_by_slug()
        for slug in (HUNGARY_REPORT, HUNGARY_BLUE_FLAG):
            self.assertEqual(il.article_round_season(arts[slug]), 2026,
                             f"{slug} 的 frontmatter 明示 season: 2026")

    def test_article_without_season_is_never_linked(self):
        """☠️ 沒有 season 欄就不連——刻意不用發布日期推年份。

        真實反例（兩篇都是 2026 年發的）：
          f1-tech-timing-positioning-race-control 文中的「摩納哥站」指 2022 那場；
          f1-2026-bahrain-gp-in-malaysia 的「義大利站」是 1980–2000 年代的歷史脈絡。
        用發布年推就會把讀者送到 2026 的錯誤場次。
        """
        arts = published_by_slug()
        no_season = [s for s, a in arts.items() if not a.get("season")]
        self.assertTrue(no_season, "前提：要有沒宣告 season 的文章")
        for slug in no_season:
            self.assertIsNone(il.article_round_season(arts[slug]))
        # 而且這些文章確實提到了 round_year 有頁的站名——不是因為沒東西可連才空
        tokens = set(il.round_link_index(2026)) | set(il.round_link_index(2002))
        self.assertTrue(any(t in arts[s]["text"] for s in no_season for t in tokens),
                        "前提：無 season 的文章裡要有可連字串，否則這條在測空氣")

    def test_season_outside_round_years_is_none(self):
        self.assertIsNone(il.article_round_season({"season": "2019"}))
        self.assertIsNone(il.article_round_season({"season": ""}))
        self.assertIsNone(il.article_round_season({}))
        self.assertEqual(il.article_round_season({"season": "2002"}), 2002)


# ============================================================
# 3. linkify_rounds：正向 + 負向控制
# ============================================================

class LinkifyRoundsTests(unittest.TestCase):
    def setUp(self):
        il.clear_caches()
        self.addCleanup(il.clear_caches)
        self.arts = published_by_slug()

    def _hrefs(self, html):
        return re.findall(r'<a href="(/seasons/[^"]+)"', html)

    def _render(self, slug):
        art = self.arts[slug]
        html = article_body_html(art)
        out, linked = il.linkify_rounds(html, il.article_round_season(art))
        return html, out, linked

    # --- 正向（真實素材） ---

    def test_hungary_articles_link_to_2026_round_11(self):
        # 2026-08-24 R12 已賽，樣本推進：HUNGARY_REPORT 文末提到的「荷蘭站」（R12）
        # 現在已完賽、有頁 → 該篇應多連一次 R12，不再是「恰好連一次 R11」。
        # HUNGARY_BLUE_FLAG 沒提到荷蘭站，維持恰好連一次 R11。
        _src, out, linked = self._render(HUNGARY_REPORT)
        self.assertEqual(self._hrefs(out),
                         ["/seasons/2026/rounds/11/", "/seasons/2026/rounds/12/"],
                         f"{HUNGARY_REPORT} 應連到 R11 與 R12（荷蘭站已賽）")
        self.assertEqual(linked, [(2026, 11, "匈牙利站"), (2026, 12, "荷蘭站")])

        _src, out, linked = self._render(HUNGARY_BLUE_FLAG)
        self.assertEqual(self._hrefs(out), ["/seasons/2026/rounds/11/"],
                         f"{HUNGARY_BLUE_FLAG} 應恰好連一次 2026 R11")
        self.assertEqual(linked, [(2026, 11, "匈牙利站")])

    # --- ☠️ 最重要的負向控制：年份消歧 ---

    def test_2026_article_never_links_to_the_2002_hungarian_round(self):
        """2002 也有匈牙利站（R13）。2026 的文章連過去就是把讀者送到錯的比賽。"""
        self.assertEqual(il.round_link_index(2002)["匈牙利站"], (2002, 13),
                         "前提：2002 R13 要真的是匈牙利站，否則這條在測空氣")
        for slug in (HUNGARY_REPORT, HUNGARY_BLUE_FLAG):
            _src, out, _linked = self._render(slug)
            self.assertNotIn("/seasons/2002/", out, f"{slug} 連到了 2002 的場次")

    def test_same_text_with_2002_context_links_to_2002(self):
        """反面對照：同一段文字宣告 season 2002 → 連 2002 R13（證明消歧真的在看 season）。"""
        src = "<p>匈牙利站的結果如下。</p>"
        out26, _ = il.linkify_rounds(src, 2026)
        out02, _ = il.linkify_rounds(src, 2002)
        self.assertIn('href="/seasons/2026/rounds/11/"', out26)
        self.assertIn('href="/seasons/2002/rounds/13/"', out02)

    # --- 其餘負向控制 ---

    def test_unraced_round_is_not_linked(self):
        """2026-08-24 R12 已賽，樣本推進：改用 DUTCH_REPORT（R12 荷蘭站戰報），其文末
        提到「第 13 站是義大利站」——該站尚未完賽、沒有頁 → 不得連。"""
        art = self.arts[DUTCH_REPORT]
        self.assertIn("義大利站", art["text"], "前提：這篇要真的提到義大利站")
        _src, out, linked = self._render(DUTCH_REPORT)
        self.assertNotIn("/seasons/2026/rounds/13/", out)
        self.assertNotIn("義大利站</a>", out)
        self.assertEqual([t for _y, _r, t in linked], ["荷蘭站"])

    def test_headings_are_not_linked_using_the_real_title(self):
        """真實素材：文章標題就是「匈牙利站戰報：…」。標題內不得長連結，內文才連。"""
        title = self.arts[HUNGARY_REPORT]["title"]
        self.assertTrue(title.startswith("匈牙利站"), "前提：標題要以站名開頭")
        for tag in ("h1", "h2", "h3"):
            src = f"<{tag}>{title}</{tag}><p>匈牙利站的完賽名次如下。</p>"
            out, linked = il.linkify_rounds(src, 2026)
            self.assertEqual(len(self._hrefs(out)), 1, f"{tag}：只有內文那次可連")
            self.assertIn(f"<{tag}>{title}</{tag}>", out, f"{tag} 標題被動到了")
            self.assertEqual(linked, [(2026, 11, "匈牙利站")])

    def test_rendered_article_never_links_inside_a_heading(self):
        """真實文章逐篇：互鏈後的 HTML 裡，任何 h1–h6 內都不得出現分站連結。"""
        for slug, art in self.arts.items():
            html = article_body_html(art)
            out, _ = il.linkify_rounds(html, il.article_round_season(art))
            for heading in re.findall(r"<h[1-6][^>]*>.*?</h[1-6]>", out, re.S):
                self.assertNotIn("/seasons/", heading, f"{slug} 的標題內長出了分站連結")

    def test_existing_anchor_is_not_nested(self):
        src = '<p>見 <a href="/seasons/2026/">匈牙利站總覽</a>。</p>'
        self.assertEqual(il.linkify_rounds(src, 2026), (src, []))

    def test_table_and_code_are_not_linked(self):
        for src in ('<div class="prose-tblwrap"><table><tbody><tr>'
                    "<td>匈牙利站</td><td>70</td></tr></tbody></table></div>",
                    "<p><code>匈牙利站</code></p>",
                    "<pre><code>race = 匈牙利站</code></pre>"):
            self.assertEqual(il.linkify_rounds(src, 2026), (src, []))

    def test_numeric_round_reference_is_not_linked(self):
        """「第 11 站」歧義高（可能是賽曆位置敘述）→ 只連具名站名。"""
        src = "<p>這是 2026 賽季第 11 站，全季共 23 站。</p>"
        self.assertEqual(il.linkify_rounds(src, 2026), (src, []))

    def test_explicit_other_year_in_sentence_blocks_the_link(self):
        """☠️ 句子裡明寫的年份優先於 frontmatter 的 season（2026-08-31 諾里斯續約文實例）。

        原病灶：一篇 season: 2026 的文章寫「普羅斯特 1989 年澳洲站」，
        舊版連到 2026 年的澳洲站——讀者點進去看到的是另一場比賽。
        """
        for src in ("<p>普羅斯特 1989 年澳洲站就屬於這一類。</p>",
                    "<p>2022 年他在澳洲站超越了前人的場次。</p>",
                    "<p>他在 1998 年匈牙利站拿下分站冠軍。</p>"):
            out, linked = il.linkify_rounds(src, 2026)
            self.assertEqual((out, linked), (src, []), src)

    def test_same_year_as_season_still_links(self):
        """陽性對照：明寫的年份**就是**該文 season 時照連，否則上面那條會變成全面關閉互鏈。"""
        src = "<p>2026 年匈牙利站由諾里斯奪冠。</p>"
        out, linked = il.linkify_rounds(src, 2026)
        self.assertEqual(linked, [(2026, 11, "匈牙利站")])
        self.assertIn('href="/seasons/2026/rounds/11/"', out)

    def test_round_ordinal_without_year_still_links(self):
        """沒有明寫年份時維持原行為——「第 11 站匈牙利站」照連當季。"""
        src = "<p>第 11 站匈牙利站與第 9 站英國站。</p>"
        _, linked = il.linkify_rounds(src, 2026)
        self.assertEqual(linked, [(2026, 11, "匈牙利站"), (2026, 9, "英國站")])

    def test_only_first_occurrence_per_round(self):
        src = "<p>匈牙利站</p><p>匈牙利站</p><p>匈牙利站與英國站</p>"
        out, linked = il.linkify_rounds(src, 2026)
        self.assertEqual(linked, [(2026, 11, "匈牙利站"), (2026, 9, "英國站")])
        self.assertEqual(len(self._hrefs(out)), 2)

    def test_first_occurrence_counts_only_linkable_positions(self):
        src = ("<h2>匈牙利站戰報</h2><p>匈牙利站由諾里斯奪冠。</p><p>匈牙利站結束。</p>")
        out, _ = il.linkify_rounds(src, 2026)
        self.assertEqual(len(self._hrefs(out)), 1)
        self.assertIn('<p><a href="/seasons/2026/rounds/11/">匈牙利站</a>由諾里斯奪冠', out)

    def test_no_season_is_a_noop(self):
        src = "<p>匈牙利站與摩納哥站。</p>"
        self.assertEqual(il.linkify_rounds(src, None), (src, []))
        self.assertEqual(il.linkify_rounds(src, 2019), (src, []))
        self.assertEqual(il.linkify_rounds(src, 2026, index={}), (src, []))

    def test_driver_and_round_links_coexist(self):
        """兩層互鏈疊在同一篇上：先車手後分站，彼此不巢狀、不互相吃掉。"""
        src = "<p>諾里斯在匈牙利站奪冠。</p>"
        mid, dlinks = il.linkify(src)
        out, rlinks = il.linkify_rounds(mid, 2026)
        self.assertTrue(dlinks and rlinks)
        self.assertIn('<a href="/drivers/norris/">諾里斯</a>', out)
        self.assertIn('<a href="/seasons/2026/rounds/11/">匈牙利站</a>', out)
        self.assertEqual(out.count("<a "), 2)

    # --- strip-tags：只多標籤、不多字 ---

    def test_strip_tags_identical_on_every_published_article(self):
        linked_any = False
        for slug, art in self.arts.items():
            html = article_body_html(art)
            out, linked = il.linkify_rounds(html, il.article_round_season(art))
            linked_any = linked_any or bool(linked)
            self.assertEqual(strip_tags(out), strip_tags(html),
                             f"{slug}：分站互鏈改動了純文字內容")
        self.assertTrue(linked_any, "全部文章零分站連結＝這條在測空氣")


# ============================================================
# 4. 反向：分站頁「相關報導」
# ============================================================

class RoundRelatedArticlesTests(unittest.TestCase):
    def setUp(self):
        il.clear_caches()
        self.addCleanup(il.clear_caches)

    def test_mentions_only_cover_published_articles(self):
        published = {a["slug"] for a in il.published_articles()}
        for target, arts in il.round_mentions().items():
            for a in arts:
                self.assertIn(a["slug"], published, f"{target} 列到未發布的 {a['slug']}")

    def test_round_11_lists_both_hungary_articles_newest_first(self):
        """⚠️ 不斷言「恰好只有這兩篇」——mention-based 設計下，任何提到匈牙利站的
        新文章（例：上半季盤點）都會合法地加進來；快照式全等在第一個新輸入就會誤紅
        （2026-08-11 實際發生）。這裡釘的是穩定性質：兩篇 R11 專文必在、相對序新→舊、
        整個清單依日期遞減。"""
        arts = il.round_articles(2026, 11)
        slugs = [a["slug"] for a in arts]
        self.assertIn(HUNGARY_BLUE_FLAG, slugs)
        self.assertIn(HUNGARY_REPORT, slugs)
        self.assertLess(slugs.index(HUNGARY_BLUE_FLAG), slugs.index(HUNGARY_REPORT),
                        "藍旗專文（較新）應排在戰報（較舊）之前")
        self.assertEqual([a["date"] for a in arts],
                         sorted((a["date"] for a in arts), reverse=True))

    def test_2002_hungarian_round_has_no_mentions(self):
        """年份消歧的反向端：2002 R13 不得因為 2026 的文章而長出相關報導。"""
        self.assertEqual(il.round_articles(2002, 13), [])
        self.assertEqual(il.round_related_articles_html(2002, 13), "")

    def test_section_absent_when_no_article_mentions_the_round(self):
        silent = [(y, r) for y in sorted(rc.ROUND_YEARS)
                  for r in gs.season_round_numbers(y) if not il.round_articles(y, r)]
        self.assertTrue(silent, "前提：要有沒被提及的場次")
        for y, r in silent:
            self.assertEqual(il.round_related_articles_html(y, r), "")

    def test_section_uses_existing_classes_and_h2(self):
        html = il.round_related_articles_html(2026, 11)
        self.assertIn('<h2 class="sec-title">相關報導</h2>', html)
        self.assertIn('<div class="rel">', html)
        self.assertEqual(set(re.findall(r'class="([^"]+)"', html)), {"sec-title", "rel"})

    def test_forward_and_reverse_agree(self):
        """同一張判定表的兩端必須對得起來：文章連了某站 ⇔ 該站列了這篇。"""
        forward = {}
        for art in il.published_articles():
            html = article_body_html(art)
            _out, linked = il.linkify_rounds(html, il.article_round_season(art))
            for y, r, _t in linked:
                forward.setdefault((y, r), set()).add(art["slug"])
        for target, slugs in forward.items():
            listed = {a["slug"] for a in il.round_articles(*target)}
            self.assertTrue(slugs <= listed,
                            f"{target}：文章連過去了卻沒被列在相關報導（{slugs - listed}）")


# ============================================================
# 5. 分站頁實際產出：區塊位置、純文字增量、死連結
# ============================================================

class RoundPageRenderTests(unittest.TestCase):
    YEAR = 2026

    @classmethod
    def setUpClass(cls):
        il.clear_caches()
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.rounds = gs.season_round_numbers(cls.YEAR)
        cls.with_arts = cls._render(cls.tmp / "with")
        empty = cls.tmp / "empty-articles"
        empty.mkdir(parents=True)
        orig = il.ARTICLES
        il.ARTICLES = empty
        il.clear_caches()
        try:
            cls.without_arts = cls._render(cls.tmp / "without")
        finally:
            il.ARTICLES = orig
            il.clear_caches()

    @classmethod
    def _render(cls, pub):
        orig = (rc.PUB, gs.PUB)
        rc.PUB = gs.PUB = pub
        try:
            out = {}
            for rnd in cls.rounds:
                gs.render_round(cls.YEAR, rnd)
                out[rnd] = (pub / "seasons" / str(cls.YEAR) / "rounds" / str(rnd)
                            / "index.html").read_text(encoding="utf-8")
            return out
        finally:
            rc.PUB, gs.PUB = orig

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)
        il.clear_caches()

    def test_only_mentioned_rounds_have_the_section(self):
        mentioned = {r for r in self.rounds if il.round_articles(self.YEAR, r)}
        self.assertTrue(mentioned, "前提：至少要有一站被文章提到")
        for rnd in self.rounds:
            self.assertEqual("相關報導" in self.with_arts[rnd], rnd in mentioned,
                             f"R{rnd} 的相關報導區出現與否不對")

    def test_section_links_every_mentioning_article(self):
        for rnd in self.rounds:
            hrefs = re.findall(r'href="(/articles/[^"]+)"', self.with_arts[rnd])
            self.assertEqual(hrefs,
                             [f"/articles/{a['slug']}/"
                              for a in il.round_articles(self.YEAR, rnd)])

    def test_section_sits_before_the_page_closing_meta_note(self):
        """位置：內容區塊之後、方法／口徑說明類 meta 之前（不是黏在頁尾像補丁）。"""
        html = self.with_arts[11]
        pos_section = html.index('<h2 class="sec-title">相關報導</h2>')
        pos_ret = html.index('<h2 class="sec-title">退賽名單</h2>')
        pos_meta = html.index("本頁為 2026 賽季第 11 站的單場分站頁")
        self.assertLess(pos_ret, pos_section, "相關報導不得排在內容區塊之前")
        self.assertLess(pos_section, pos_meta, "相關報導不得排在頁尾 meta 說明之後")

    def test_strip_tags_delta_is_exactly_the_new_section(self):
        for rnd in self.rounds:
            base = strip_tags(self.without_arts[rnd])
            new = strip_tags(self.with_arts[rnd])
            block = strip_tags(il.round_related_articles_html(self.YEAR, rnd))
            if not block:
                self.assertEqual(new, base, f"R{rnd}：沒有相關報導卻動到了純文字")
                continue
            self.assertIn(block, new, f"R{rnd}：相關報導區塊沒出現在頁面上")
            self.assertEqual(new.replace(block, "", 1), base,
                             f"R{rnd}：相關報導以外的純文字被動到了")

    def test_no_dead_article_links(self):
        pub = ROOT / "public-racing" / "articles"
        if not pub.exists():
            self.skipTest("public-racing 不在（乾淨 checkout）")
        dead = []
        for rnd, html in self.with_arts.items():
            for href in re.findall(r'href="(/articles/[^"]+)"', html):
                if not (ROOT / "public-racing" / href.strip("/") / "index.html").is_file():
                    dead.append((rnd, href))
        self.assertEqual(dead, [], f"相關報導死連結：{dead[:10]}")

    def test_article_pages_link_only_to_existing_round_pages(self):
        pub = ROOT / "public-racing" / "articles"
        if not pub.exists():
            self.skipTest("public-racing 不在（乾淨 checkout）")
        dead, total = [], 0
        for f in sorted(pub.glob("*/index.html")):
            for href in re.findall(r'href="(/seasons/\d+/rounds/\d+/)"',
                                   f.read_text(encoding="utf-8")):
                total += 1
                if not (ROOT / "public-racing" / href.strip("/") / "index.html").is_file():
                    dead.append((f.parent.name, href))
        self.assertEqual(dead, [], f"文章頁指向不存在的分站頁：{dead[:10]}")
        self.assertGreater(total, 0, "已發布文章零分站互鏈＝正向那半沒接上")


# ============================================================
# 6. 指紋：新文章要讓被提及的分站頁重生（而且只有那一頁）
# ============================================================

FM = ("---\nslug: {slug}\ntype: report\ndate: {date}\n{season}"
      'title: "{title}"\nsubtitle: "測試用合成文章。"\n---\n\n# {title}\n\n{body}\n')


class RoundMentionFingerprintTests(unittest.TestCase):
    """☠️ 指紋只切 db.sqlite 時，新文章不會讓分站頁重生 → 相關報導永遠停在舊狀態。

    同時證明反面：該季總覽與 /seasons/ 索引指紋**一個 byte 都沒動**——分站頁的
    相關報導不該把整季 78 頁白刷一次。
    """

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.arts = self.tmp / "articles"
        self.arts.mkdir()
        self.approved = self.tmp / "approved.json"
        self.exclude = self.tmp / "draft-exclude.json"
        self.exclude.write_text(json.dumps({"exclude": []}), encoding="utf-8")
        self._entries = []
        self._write_approved()

        self._orig = (il.ARTICLES, il.APPROVED, il.DRAFT_EXCLUDE)
        il.ARTICLES, il.APPROVED, il.DRAFT_EXCLUDE = self.arts, self.approved, self.exclude
        il.clear_caches()
        self.addCleanup(self._restore)

        self.db = self.tmp / "db.sqlite"
        shutil.copy(fs.DB, self.db)

    def _restore(self):
        il.ARTICLES, il.APPROVED, il.DRAFT_EXCLUDE = self._orig
        il.clear_caches()

    def _write_approved(self):
        self.approved.write_text(json.dumps({"approved": self._entries}, ensure_ascii=False),
                                 encoding="utf-8")

    def add_article(self, slug, body, season="2026", date="2026-08-02", title="合成測試文"):
        d = self.arts / slug
        d.mkdir(parents=True, exist_ok=True)
        src = d / "index.md"
        src.write_text(FM.format(slug=slug, date=date, title=title, body=body,
                                 season=f"season: {season}\n" if season else ""),
                       encoding="utf-8")
        self._entries.append({"slug": slug,
                              "article_sha256": hashlib.sha256(src.read_bytes()).hexdigest()})
        self._write_approved()
        il.clear_caches()

    def _fp(self):
        con = sqlite3.connect(str(self.db))
        con.row_factory = sqlite3.Row
        try:
            return re_mod.compute_fingerprints(con)
        finally:
            con.close()

    # --- 核心：新文章 → 被提及的那一站指紋變，其餘全部不動 ---

    def test_new_article_changes_only_the_mentioned_round(self):
        before = self._fp()
        self.add_article("synthetic-hungary", "本站在匈牙利站的逐圈觀察。", season="2026")
        after = self._fp()

        self.assertNotEqual(before["rounds"]["2026/11"], after["rounds"]["2026/11"],
                            "新增提及匈牙利站的文章後，2026 R11 指紋必須變")
        changed = [k for k in after["rounds"] if before["rounds"][k] != after["rounds"][k]]
        self.assertEqual(changed, ["2026/11"], f"只該有 2026/11 變，實際：{changed}")

        # ☠️ 關鍵反證：季／索引／車手／車隊全部沒動——沒把 mention 納進分站指紋，
        #    這頁就永遠不會重生（也不能靠「反正整季會重刷」矇混過去）
        self.assertEqual(before["seasons"], after["seasons"])
        self.assertEqual(before["indices"], after["indices"])
        self.assertEqual(before["drivers"], after["drivers"])
        self.assertEqual(before["constructors"], after["constructors"])

    def test_season_2002_article_changes_only_the_2002_round(self):
        """年份消歧的指紋端：同一句話宣告 season 2002 → 只有 2002/13 變。"""
        before = self._fp()
        self.add_article("synthetic-hungary-2002", "1957 年那場之後的匈牙利站回顧。",
                         season="2002")
        after = self._fp()
        changed = [k for k in after["rounds"] if before["rounds"][k] != after["rounds"][k]]
        self.assertEqual(changed, ["2002/13"], f"只該有 2002/13 變，實際：{changed}")

    def test_article_without_season_changes_nothing(self):
        """負向控制：沒有 season 欄的文章提到站名也不得動到任何分站指紋。"""
        before = self._fp()
        self.add_article("synthetic-no-season", "談匈牙利站與摩納哥站的歷史。", season="")
        self.assertEqual(before["rounds"], self._fp()["rounds"])

    def test_article_mentioning_an_unraced_round_changes_nothing(self):
        """2026-08-24 R12 已賽，樣本推進：改用義大利站（R13，還沒有頁）
        → 提到它不得產生任何指紋變動。"""
        before = self._fp()
        self.add_article("synthetic-italy", "下一站義大利站的看點。", season="2026")
        self.assertEqual(before["rounds"], self._fp()["rounds"])

    def test_unapproved_article_does_not_change_fingerprint(self):
        before = self._fp()
        d = self.arts / "synthetic-draft"
        d.mkdir()
        (d / "index.md").write_text(
            FM.format(slug="synthetic-draft", date="2026-08-02", title="草稿",
                      season="season: 2026\n", body="匈牙利站草稿。"), encoding="utf-8")
        il.clear_caches()
        self.assertEqual(before, self._fp())

    def test_title_change_changes_the_round_fingerprint(self):
        """標題會渲染進相關報導 → 改標題也要讓該分站頁重生。"""
        self.add_article("synthetic-hungary-3", "匈牙利站短評。", title="舊標題")
        before = self._fp()
        self._entries = []
        self.add_article("synthetic-hungary-3", "匈牙利站短評。", title="新標題")
        self.assertNotEqual(before["rounds"]["2026/11"], self._fp()["rounds"]["2026/11"])

    # --- 端到端：只有那一頁被重寫 ---

    def test_selective_regen_rewrites_only_that_round_page(self):
        pub = self.tmp / "pub"
        fp = self.tmp / "fp.json"
        # ⚠️ 一律用 re_mod.pub_override：自己列 PUB 名單會漏（漏過 ci＝circuits，
        # 害全套測試把 79 個賽道頁寫進版控產物目錄）。新增 owner 只改 PAGE_OWNERS。
        pub_ctx = re_mod.pub_override(pub)
        pub_ctx.__enter__()

        def regen(**kw):
            con = sqlite3.connect(str(self.db))
            con.row_factory = sqlite3.Row
            try:
                return re_mod.selective_regen(con, fp_path=fp, **kw)
            finally:
                con.close()

        try:
            regen(full=True)
            snap = {p: p.stat().st_mtime_ns for p in (pub / "seasons").rglob("index.html")}
            self.assertEqual(regen()["changed_rounds"], [], "資料沒變不得重生")

            self.add_article("synthetic-hungary-e2e", "匈牙利站的逐圈觀察。",
                             season="2026", title="匈牙利站逐圈觀察")
            res = regen()
            self.assertEqual(res["changed_rounds"], ["2026/11"])
            self.assertEqual(res["rounds_rendered_standalone"], ["2026/11"])
            self.assertEqual(res["changed_years"], [], "賽季 db 沒變 → 總覽不得重生")
            rewritten = {str(p.relative_to(pub)) for p, m in snap.items()
                         if p.stat().st_mtime_ns != m}
            self.assertEqual(rewritten, {"seasons/2026/rounds/11/index.html"},
                             f"只能重寫 R11，實際：{sorted(rewritten)}")
            page = (pub / "seasons" / "2026" / "rounds" / "11"
                    / "index.html").read_text(encoding="utf-8")
            self.assertIn('<h2 class="sec-title">相關報導</h2>', page)
            self.assertIn('href="/articles/synthetic-hungary-e2e/"', page)
            self.assertIn("匈牙利站逐圈觀察", page)
        finally:
            pub_ctx.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
