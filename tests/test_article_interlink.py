#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文章 ↔ 車手實體頁雙向互鏈 回歸測試（scripts/interlink.py）。

釘住的東西：
1. 正向：文章 HTML 的車手名連到**註冊表裡的**正確 slug。
2. strip-tags 純文字比對：互鏈只加標籤、不加字（文章頁與車手頁都驗）。
   ☠️ 這條同時是「源檔零改動」紅線的代理——已發布文章被 approved.json 以 sha256 凍結，
   互鏈只准動渲染後的 HTML；純文字一旦多出東西，就代表有人在往別的方向走。
3. 負向控制（缺這幾條就是假 gate）：標題／既有連結／表格／程式碼裡不連、歧義字串不連、
   沒有實體頁的車手不連、沒有 approved 譯名的不連、英文要求詞邊界。
4. 每位車手每篇只連第一次出現。
5. 指紋含 mention 映射：新增一篇提及某車手的文章 → 該車手指紋變 → 只有那一頁重生。
   同一組測試順便證明「db 切片完全沒變」——那正是原本會靜默 stale 的原因。
6. 死連結 0：車手頁列的相關報導、文章頁指向的車手頁，都要有對應的產出。

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


# ⚠️ 一律借 regen 的模組圖：各生成器內部各自 importlib 載入，自己再載一份 racinglib/
# interlink 會拿到**不同的物件**，patch 不生效、產物還會寫進真的 repo（M7 踩過）。
re_mod = _load("regen_encyclopedia", "regen-encyclopedia.py")
il = re_mod.il
rc = re_mod.rc
dr = re_mod.dr
fs = re_mod.fs
gs = re_mod.gs
p0 = re_mod.p0
ba = _load("build_articles", "build-articles.py")


def strip_tags(html):
    """把 HTML 化成純文字（比對「只多了標籤，沒多字」用）。"""
    return html_lib.unescape(re.sub(r"<[^>]+>", "", html))


# ============================================================
# 1. 判定表：誰可以被連、誰不行
# ============================================================

class LinkIndexRuleTests(unittest.TestCase):
    def setUp(self):
        il.clear_caches()
        self.addCleanup(il.clear_caches)
        self.index = il.link_index()

    def test_every_target_is_a_champion_with_a_page(self):
        champs = set(il.champion_ids())
        bad = {s: d for s, (d, _slug) in self.index.items() if d not in champs}
        self.assertEqual(bad, {}, f"連到沒有實體頁的車手：{bad}")

    def test_every_target_slug_matches_registry(self):
        bad = [(s, d, slug) for s, (d, slug) in self.index.items()
               if slug != rc.driver_slug(d)]
        self.assertEqual(bad, [], f"slug 與 data/f1/slugs.json 註冊表不符：{bad}")

    def test_driver_without_entity_page_is_never_linkable(self):
        """有 approved 譯名但沒建頁的現役車手（皮亞斯特里／勒克萊爾）不得出現在判定表。"""
        for zh in ("皮亞斯特里", "勒克萊爾", "安東內利", "羅素"):
            self.assertNotIn(zh, self.index, f"{zh} 沒有實體頁，不該可連")

    def test_ambiguous_short_names_are_dropped(self):
        """真實歧義：「希爾」對到三個人、「羅斯堡」對到兩個人 → 兩者都不連。"""
        amb = il.ambiguous_strings()
        self.assertGreaterEqual(len(amb.get("希爾", [])), 2, "「希爾」應該是歧義字串")
        self.assertGreaterEqual(len(amb.get("羅斯堡", [])), 2, "「羅斯堡」應該是歧義字串")
        for s in amb:
            self.assertNotIn(s, self.index, f"歧義字串 {s} 不得進判定表")

    def test_unique_short_name_is_linkable(self):
        """「舒馬克」在有頁的 35 人裡唯一 → 可連（規格點名的例子）。"""
        self.assertIn("舒馬克", self.index)
        self.assertEqual(self.index["舒馬克"][0], "michael_schumacher")

    def test_bare_english_surname_is_not_indexed(self):
        """單獨英文姓氏刻意不收（Button／Hunt／Jones 同時是普通英文單字）。"""
        for surname in ("Norris", "Button", "Hunt", "Jones", "Farina", "Hamilton"):
            self.assertNotIn(surname, self.index, f"單獨英文姓氏 {surname} 不該可連")
        self.assertIn("Lando Norris", self.index)
        self.assertIn("Jenson Button", self.index)

    def test_pending_translation_is_not_linkable(self):
        """只認 status=='approved'：把譯名改成 pending → 該字串必須從判定表消失。

        這條是「approved-only」規則的負向控制。少了它，判定表是不是真的在看 status
        完全分辨不出來（現況 51 條全是 approved，正向永遠綠）。
        """
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "scripts").mkdir()
        (tmp / "scripts" / "driver-zh.json").write_text(json.dumps({
            "norris": {"zh": "諾里斯", "src": "test", "status": "pending"},
            "alonso": {"zh": "阿隆索", "src": "test", "status": "approved"},
        }, ensure_ascii=False), encoding="utf-8")

        # ⚠️ 要 patch 的是 **il 自己那份** racinglib（各腳本各自 importlib 載入，
        #    re_mod.rc 與 il.rc 不是同一個物件）
        ilrc = il.rc
        orig_root, orig_zh = ilrc.ROOT, ilrc.DRIVER_ZH
        ilrc.ROOT = tmp
        ilrc.DRIVER_ZH = ilrc._load_zh("driver-zh.json")

        def restore():
            ilrc.ROOT, ilrc.DRIVER_ZH = orig_root, orig_zh
            il.clear_caches()

        self.addCleanup(restore)
        il.clear_caches()
        idx = il.link_index()
        self.assertNotIn("諾里斯", idx, "pending 譯名不得可連")
        self.assertIn("阿隆索", idx, "approved 譯名仍要可連（否則這條測的是別的東西）")


# ============================================================
# 2. linkify：正向 + 負向控制
# ============================================================

class LinkifyTests(unittest.TestCase):
    def setUp(self):
        il.clear_caches()
        self.addCleanup(il.clear_caches)

    def _link_hrefs(self, html):
        return re.findall(r'<a href="(/drivers/[^"]+)"', html)

    # --- 正向 ---

    def test_links_point_to_registered_slug(self):
        out, links = il.linkify("<p>維斯塔潘在最後一圈追上了諾里斯。</p>")
        self.assertEqual(self._link_hrefs(out),
                         ["/drivers/max-verstappen/", "/drivers/norris/"])
        self.assertEqual([d for d, _s, _t in links], ["max_verstappen", "norris"])

    def test_english_full_name_is_linked(self):
        out, _ = il.linkify("<p>Sebastian Vettel 在 2013 年封王。</p>")
        self.assertEqual(self._link_hrefs(out), ["/drivers/vettel/"])

    def test_longest_match_wins(self):
        """同一個位置有長短兩個候選 → 取長的，不能只連到尾巴那段。"""
        out, _ = il.linkify("<p>路易斯・漢米爾頓拿下第八冠。</p>")
        self.assertIn('<a href="/drivers/hamilton/">路易斯・漢米爾頓</a>', out)

    def test_link_carries_no_invented_class(self):
        """沿用站內既有樣式（.prose a），不自創 class。"""
        out, _ = il.linkify("<p>諾里斯奪冠。</p>")
        self.assertIn('<a href="/drivers/norris/">諾里斯</a>', out)
        self.assertNotIn("class=", out.split("<p>")[1])

    # --- 負向控制（缺這些就是假 gate）---

    def test_headings_are_not_linked(self):
        for tag in ("h1", "h2", "h3"):
            out, links = il.linkify(f"<{tag}>諾里斯奪冠</{tag}>")
            self.assertEqual(links, [], f"{tag} 標題內不得加連結")
            self.assertNotIn("<a ", out)

    def test_existing_anchor_is_not_nested(self):
        src = '<p>見 <a href="/seasons/2026/">諾里斯的 2026</a>。</p>'
        out, links = il.linkify(src)
        self.assertEqual(links, [])
        self.assertEqual(out, src)

    def test_table_content_is_not_linked(self):
        src = ('<div class="prose-tblwrap"><table><tbody><tr>'
               "<td>諾里斯</td><td>25</td></tr></tbody></table></div>")
        out, links = il.linkify(src)
        self.assertEqual(links, [])
        self.assertEqual(out, src)

    def test_code_is_not_linked(self):
        src = "<p><code>諾里斯</code></p>"
        self.assertEqual(il.linkify(src), (src, []))
        src2 = "<pre><code>driver = 諾里斯</code></pre>"
        self.assertEqual(il.linkify(src2), (src2, []))

    def test_text_after_protected_block_is_still_linked(self):
        """保護區收尾後要恢復可連——否則整篇文章會被第一個表格關掉（假的「沒錯連」）。"""
        src = "<h2>諾里斯</h2><p>諾里斯拿下第 11 站。</p>"
        out, links = il.linkify(src)
        self.assertEqual([d for d, _s, _t in links], ["norris"])
        self.assertIn('<p><a href="/drivers/norris/">諾里斯</a>拿下', out)

    def test_ambiguous_string_is_not_linked(self):
        out, links = il.linkify("<p>希爾與羅斯堡都拿過冠軍。</p>")
        self.assertEqual(links, [])
        self.assertNotIn("<a ", out)

    def test_driver_without_page_is_not_linked(self):
        out, links = il.linkify("<p>皮亞斯特里領跑 25 圈，勒克萊爾退後兩位。</p>")
        self.assertEqual(links, [])

    def test_english_requires_word_boundary(self):
        out, links = il.linkify("<p>Fernando Alonsoism 不是一個字。</p>")
        self.assertEqual(links, [], "英文候選必須守詞邊界，不得連黏在單字裡的片段")

    def test_only_first_occurrence_is_linked(self):
        out, links = il.linkify("<p>諾里斯</p><p>諾里斯</p><p>諾里斯與維斯塔潘</p>")
        self.assertEqual([d for d, _s, _t in links], ["norris", "max_verstappen"])
        self.assertEqual(len(self._link_hrefs(out)), 2)

    def test_first_occurrence_counts_only_linkable_positions(self):
        """第一次出現在表格裡 → 該次不算，下一個可連位置才連（且仍只連一次）。"""
        src = ("<table><tbody><tr><td>諾里斯</td></tr></tbody></table>"
               "<p>諾里斯從第 1 位發車。</p><p>諾里斯守住領先。</p>")
        out, links = il.linkify(src)
        self.assertEqual(len(self._link_hrefs(out)), 1)
        self.assertIn('<p><a href="/drivers/norris/">諾里斯</a>從第 1 位發車', out)

    def test_empty_index_is_a_noop(self):
        src = "<p>諾里斯</p>"
        self.assertEqual(il.linkify(src, index={}), (src, []))

    # --- strip-tags：只多標籤、不多字 ---

    def test_strip_tags_identical_on_synthetic_html(self):
        src = ("<p>諾里斯（Lando Norris）從第 1 位發車，維斯塔潘第 4。</p>"
               "<h2>諾里斯的一天</h2>"
               "<table><tbody><tr><td>漢米爾頓</td></tr></tbody></table>"
               "<p>漢米爾頓停了三次。</p>")
        out, links = il.linkify(src)
        self.assertTrue(links, "前提：這段至少要有連結，否則這條在測空氣")
        self.assertEqual(strip_tags(out), strip_tags(src))

    def test_strip_tags_identical_on_every_published_article(self):
        """真實文章逐篇：markdown 渲染結果 vs 互鏈後，純文字必須一模一樣。"""
        import markdown as md_lib
        arts = il.published_articles()
        self.assertTrue(arts, "前提：至少要有一篇已發布文章")
        linked_any = False
        for art in arts:
            body = rc.strip_h1(rc.parse_frontmatter(art["text"])[1])
            html = md_lib.markdown(body, extensions=["extra", "sane_lists"])
            out, links = il.linkify(html)
            linked_any = linked_any or bool(links)
            self.assertEqual(strip_tags(out), strip_tags(html),
                             f"{art['slug']}：互鏈改動了純文字內容")
        self.assertTrue(linked_any, "六篇文章全都零連結＝這條在測空氣")


# ============================================================
# 3. 反向：相關報導區塊
# ============================================================

class RelatedArticlesTests(unittest.TestCase):
    def setUp(self):
        il.clear_caches()
        self.addCleanup(il.clear_caches)

    def test_mentions_only_cover_published_articles(self):
        published = {a["slug"] for a in il.published_articles()}
        for did, arts in il.article_mentions().items():
            for a in arts:
                self.assertIn(a["slug"], published,
                              f"{did} 的相關報導列到未發布的 {a['slug']}")

    def test_published_set_matches_build_articles_own_gate(self):
        """反向掃描的發布判定必須與 build-articles.py 的 gate 同義（擋兩邊規則漂走）。

        用 ba 自己的 primitives 重算一次，而不是照抄我的實作。
        """
        approved = ba.load_approved_entries()
        excluded = ba.load_draft_excludes()
        expected = set()
        for d in sorted(ba.SRC.iterdir()):
            src = d / "index.md"
            if not d.is_dir() or not src.exists():
                continue
            slug = rc.parse_frontmatter(src.read_text(encoding="utf-8"))[0].get("slug", d.name)
            entry = approved.get(slug)
            if slug in excluded or entry is None:
                continue
            if entry.get("article_sha256") == ba.article_sha256(src):
                expected.add(slug)
        self.assertEqual({a["slug"] for a in il.published_articles()}, expected)

    def test_ambiguous_mention_is_not_attributed(self):
        """只提到歧義字串的文章不算任何人的相關報導（真實案例：巴林站文提到「希爾」）。"""
        bahrain = "f1-2026-bahrain-gp-in-malaysia"
        texts = {a["slug"]: a["text"] for a in il.published_articles()}
        self.assertIn("希爾", texts.get(bahrain, ""), "前提：這篇要真的提到「希爾」")
        for did, arts in il.article_mentions().items():
            self.assertNotIn(bahrain, [a["slug"] for a in arts],
                             f"歧義字串把 {bahrain} 掛到了 {did}")

    def test_section_absent_when_no_article_mentions_driver(self):
        """誠實 fallback：沒人提到就整個區塊不出現，不放「暫無」占位。"""
        silent = [d for d in il.champion_ids() if not il.driver_articles(d)]
        self.assertTrue(silent, "前提：要有沒被提及的車手")
        for did in silent:
            self.assertEqual(il.related_articles_html(did), "")

    def test_section_uses_existing_classes_and_h2(self):
        loud = [d for d in il.champion_ids() if il.driver_articles(d)]
        self.assertTrue(loud, "前提：要有被提及的車手")
        html = il.related_articles_html(loud[0])
        self.assertIn('<h2 class="sec-title">相關報導</h2>', html)
        self.assertIn('<div class="rel">', html)
        # 只准用既有 class，不自創視覺
        self.assertEqual(set(re.findall(r'class="([^"]+)"', html)), {"sec-title", "rel"})

    def test_section_is_newest_first_and_escaped(self):
        for did in il.champion_ids():
            arts = il.driver_articles(did)
            self.assertEqual([a["date"] for a in arts],
                             sorted((a["date"] for a in arts), reverse=True))


# ============================================================
# 4. 車手頁實際產出：區塊、純文字增量、死連結
# ============================================================

class DriverPageRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        il.clear_caches()
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.con = fs.connect_db()
        cls.with_arts = cls._render(cls.tmp / "with")
        # 對照組：把文章來源指到空目錄 → 相關報導區完全不存在的同一批頁
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
        orig = dr.PUB
        dr.PUB = pub
        try:
            out = {}
            for did in dr.CHAMPION_IDS:
                s = dr.gen_driver(did, cls.con)
                out[did] = (pub / "drivers" / s["slug"] / "index.html").read_text(encoding="utf-8")
            return out
        finally:
            dr.PUB = orig

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        shutil.rmtree(cls.tmp)
        il.clear_caches()

    def test_mentioned_drivers_have_the_section(self):
        mentioned = {d for d in dr.CHAMPION_IDS if il.article_mentions().get(d)}
        self.assertTrue(mentioned, "前提：至少要有一位車手被文章提到")
        for did in dr.CHAMPION_IDS:
            has = "相關報導" in self.with_arts[did]
            self.assertEqual(has, did in mentioned, f"{did} 的相關報導區出現與否不對")

    def test_section_links_every_mentioning_article(self):
        for did, arts in il.article_mentions().items():
            hrefs = re.findall(r'href="(/articles/[^"]+)"', self.with_arts[did])
            self.assertEqual(hrefs, [f"/articles/{a['slug']}/" for a in arts])

    def test_strip_tags_delta_is_exactly_the_new_section(self):
        """車手頁的純文字只多出「相關報導」區塊本身，其餘一字不差。"""
        for did in dr.CHAMPION_IDS:
            base = strip_tags(self.without_arts[did])
            new = strip_tags(self.with_arts[did])
            block = strip_tags(il.related_articles_html(did))
            if not block:
                self.assertEqual(new, base, f"{did}：沒有相關報導卻動到了純文字")
                continue
            self.assertIn(block, new, f"{did}：相關報導區塊沒出現在頁面上")
            self.assertEqual(new.replace(block, "", 1), base,
                             f"{did}：相關報導以外的純文字被動到了")

    def test_no_dead_article_links(self):
        """車手頁列的每一篇都要有實際產出目錄（public-racing 是 committed 產物）。"""
        pub = ROOT / "public-racing" / "articles"
        if not pub.exists():
            self.skipTest("public-racing 不在（乾淨 checkout）")
        dead = []
        for did, html in self.with_arts.items():
            for href in re.findall(r'href="(/articles/[^"]+)"', html):
                if not (ROOT / "public-racing" / href.strip("/") / "index.html").is_file():
                    dead.append((did, href))
        self.assertEqual(dead, [], f"相關報導死連結：{dead[:10]}")

    def test_article_pages_link_only_to_existing_driver_pages(self):
        pub = ROOT / "public-racing" / "articles"
        if not pub.exists():
            self.skipTest("public-racing 不在（乾淨 checkout）")
        slugs = {rc.driver_slug(d) for d in dr.CHAMPION_IDS}
        dead, total = [], 0
        for f in sorted(pub.glob("*/index.html")):
            for href in re.findall(r'href="/drivers/([^"/]+)/"', f.read_text(encoding="utf-8")):
                total += 1
                if href not in slugs:
                    dead.append((f.parent.name, href))
        self.assertEqual(dead, [], f"文章頁指向不存在的車手頁：{dead[:10]}")
        self.assertGreater(total, 0, "已發布文章零車手互鏈＝正向那半沒接上")


# ============================================================
# 5. 指紋：新文章要讓被提及的車手頁重生（本次的設計陷阱）
# ============================================================

FM = ("---\nslug: {slug}\ntype: report\ndate: {date}\n"
      'title: "{title}"\nsubtitle: "測試用合成文章。"\n---\n\n# {title}\n\n{body}\n')


class MentionFingerprintTests(unittest.TestCase):
    """☠️ 指紋只切 db.sqlite 時，新文章不會讓車手頁重生 → 相關報導永遠停在舊狀態。

    這組測試同時證明兩件事：mention 進了指紋（正向），以及 db 切片**真的沒變**（＝
    沒有這塊的話就是靜默 stale，不是「反正別的東西會帶到」）。
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

    def add_article(self, slug, body, date="2026-08-02", title="合成測試文"):
        d = self.arts / slug
        d.mkdir(parents=True, exist_ok=True)
        src = d / "index.md"
        src.write_text(FM.format(slug=slug, date=date, title=title, body=body), encoding="utf-8")
        self._entries.append({"slug": slug,
                              "article_sha256": hashlib.sha256(src.read_bytes()).hexdigest()})
        self._write_approved()
        il.clear_caches()

    def _fp(self, db=None):
        con = sqlite3.connect(str(db or self.db))
        con.row_factory = sqlite3.Row
        try:
            return re_mod.compute_fingerprints(con)
        finally:
            con.close()

    def _db_slice_hash(self, did):
        con = sqlite3.connect(str(self.db))
        con.row_factory = sqlite3.Row
        try:
            return re_mod._h(re_mod._driver_slice(con, did))
        finally:
            con.close()

    # --- 核心：新文章 → 被提及的車手指紋變 ---

    def test_new_article_changes_only_the_mentioned_driver_fingerprint(self):
        before = self._fp()
        db_before = self._db_slice_hash("fangio")

        self.add_article("synthetic-fangio", "方吉歐在 1957 年拿下第五冠。")
        after = self._fp()

        self.assertNotEqual(before["drivers"]["fangio"], after["drivers"]["fangio"],
                            "新增提及方吉歐的文章後，他的頁面指紋必須變")
        changed = [d for d in re_mod.CHAMPION_IDS
                   if before["drivers"][d] != after["drivers"][d]]
        self.assertEqual(changed, ["fangio"], f"只該有 fangio 變，實際：{changed}")

        # ☠️ 關鍵反證：db 切片一個 byte 都沒動——沒把 mention 納進指紋，這頁就永遠不會重生
        self.assertEqual(db_before, self._db_slice_hash("fangio"))
        self.assertEqual(before["seasons"], after["seasons"])
        self.assertEqual(before["constructors"], after["constructors"])

    def test_drivers_index_fingerprint_is_db_only(self):
        """/drivers/ 索引不渲染相關報導 → 發文章不得把索引白刷一次。"""
        before = self._fp()
        self.add_article("synthetic-fangio-2", "方吉歐五冠。")
        after = self._fp()
        self.assertEqual(before["indices"], after["indices"])

    def test_article_mentioning_nobody_changes_nothing(self):
        """負向控制：不提任何有頁車手的文章不得動到任何指紋（否則只是在數文章篇數）。"""
        before = self._fp()
        self.add_article("synthetic-none", "這篇只談輪胎溫度與煞車偏壓，沒有點名任何車手。")
        self.assertEqual(before, self._fp())

    def test_unapproved_article_does_not_change_fingerprint(self):
        """沒進 approved.json 的草稿不得影響指紋（也就不會出現在車手頁上）。"""
        before = self._fp()
        d = self.arts / "synthetic-draft"
        d.mkdir()
        (d / "index.md").write_text(
            FM.format(slug="synthetic-draft", date="2026-08-02", title="草稿",
                      body="方吉歐五冠。"), encoding="utf-8")
        il.clear_caches()
        self.assertEqual(before, self._fp())

    def test_title_change_of_existing_article_changes_fingerprint(self):
        """標題會渲染進相關報導 → 改標題也要讓該車手頁重生。"""
        self.add_article("synthetic-fangio-3", "方吉歐五冠。", title="舊標題")
        before = self._fp()
        self._entries = []
        self.add_article("synthetic-fangio-3", "方吉歐五冠。", title="新標題")
        self.assertNotEqual(before["drivers"]["fangio"], self._fp()["drivers"]["fangio"])

    # --- 端到端：只有那一頁被重寫，而且內容真的長出來了 ---

    def test_selective_regen_rewrites_only_that_driver_page(self):
        pub = self.tmp / "pub"
        fp = self.tmp / "fp.json"
        orig = (rc.PUB, gs.PUB, p0.PUB, dr.PUB)
        rc.PUB = gs.PUB = p0.PUB = dr.PUB = pub

        def regen(**kw):
            con = sqlite3.connect(str(self.db))
            con.row_factory = sqlite3.Row
            try:
                return re_mod.selective_regen(con, fp_path=fp, **kw)
            finally:
                con.close()

        try:
            regen(full=True)
            snap = {p: p.stat().st_mtime_ns
                    for p in (pub / "drivers").rglob("index.html")}
            self.assertEqual(regen()["changed_drivers"], [], "資料沒變不得重生")

            self.add_article("synthetic-fangio-e2e", "方吉歐在 1957 年拿下第五冠。",
                             title="方吉歐的第五冠")
            res = regen()
            self.assertEqual(res["changed_drivers"], ["fangio"])
            rewritten = {p.parent.name for p, m in snap.items()
                         if p.stat().st_mtime_ns != m}
            self.assertEqual(rewritten, {"fangio"},
                             f"只能重寫 fangio，實際：{sorted(rewritten)}")
            page = (pub / "drivers" / "fangio" / "index.html").read_text(encoding="utf-8")
            self.assertIn('<h2 class="sec-title">相關報導</h2>', page)
            self.assertIn('href="/articles/synthetic-fangio-e2e/"', page)
            self.assertIn("方吉歐的第五冠", page)
        finally:
            rc.PUB, gs.PUB, p0.PUB, dr.PUB = orig


if __name__ == "__main__":
    unittest.main()
