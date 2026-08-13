#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文章 ↔ 車隊頁互鏈：第三種實體、表格首格例外與反向 staleness 回歸。"""
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
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 借 regen 的單一模組圖，避免 patch 到另一份 interlink／PUB。
regen = _load("regen_team_interlink_tests", "regen-encyclopedia.py")
il, rc, fs, cg = regen.il, regen.rc, regen.fs, regen.cg


def strip_tags(value):
    return html_lib.unescape(re.sub(r"<[^>]+>", "", value))


class TeamIndexTests(unittest.TestCase):
    def setUp(self):
        il.clear_caches()
        self.addCleanup(il.clear_caches)

    def test_roster_and_targets_are_exactly_the_eleven_pages(self):
        report = json.loads((ROOT / "data/f1/constructor-crosscheck-report.json").read_text())
        expected = tuple(report["coverage"]["expected_constructor_ids"])
        self.assertEqual(il.constructor_ids(), expected)
        self.assertEqual(len(expected), 11)
        targets = {target[0] for target in il.team_link_index().values()
                   if target != il.TEAM_BLOCKER}
        self.assertEqual(targets, set(expected))
        for token, (cid, slug) in il.team_link_index().items():
            if (cid, slug) == il.TEAM_BLOCKER:
                continue
            self.assertEqual(slug, rc.constructor_slug(cid), token)

    def test_final_real_token_set_is_approved_zh_plus_official_names_only(self):
        expected = set()
        for cid in il.constructor_ids():
            expected.update(il.team_candidate_strings(cid))
        actual = {token for token, target in il.team_link_index().items()
                  if target != il.TEAM_BLOCKER}
        self.assertEqual(actual, expected - set(il.cross_namespace_collisions()))
        for risky_short in ("RB", "Haas", "Cadillac", "Bull", "Martin"):
            self.assertNotIn(risky_short, actual)

    def test_blockers_are_in_the_same_longest_match_index(self):
        idx = il.team_link_index()
        self.assertEqual(set(il.TEAM_BLOCKERS), {"紅牛環", "紅牛二隊", "Red Bull Ring"})
        for token in il.TEAM_BLOCKERS:
            self.assertEqual(idx[token], il.TEAM_BLOCKER)
        self.assertGreater(len("紅牛環"), len("紅牛"))
        self.assertGreater(len("Red Bull Ring"), len("Red Bull"))

    def test_cross_namespace_collision_is_dropped_from_both_sides(self):
        self.assertEqual(il.cross_namespace_collisions(), frozenset(),
                         "現況不應有車手／車隊 token 撞字")
        il._CACHE["driver_unique_index"] = {"Shared Name": ("driver", "driver")}
        il._CACHE["team_unique_index"] = {"Shared Name": ("team", "team")}
        il._CACHE.pop("link_index", None)
        il._CACHE.pop("team_link_index", None)
        self.assertNotIn("Shared Name", il.link_index(), "撞字必須從車手端丟棄")
        self.assertNotIn("Shared Name", il.team_link_index(), "撞字必須從車隊端丟棄")


class TeamLinkifyTests(unittest.TestCase):
    def setUp(self):
        il.clear_caches()
        self.addCleanup(il.clear_caches)

    def test_each_blocker_and_fullwidth_connector_prevent_wrong_links(self):
        src = ("<p>紅牛環、紅牛二隊、Red Bull Ring 都不是這裡要連的車隊；"
               "2002 年的麥拉倫－賓士是引擎供應寫法。</p>")
        out, links = il.linkify_teams(src)
        self.assertEqual(links, [("mclaren", "mclaren", "麥拉倫")])
        self.assertNotIn('/constructors/red-bull/', out)
        self.assertNotIn('/constructors/mercedes/', out)
        self.assertIn('<a href="/constructors/mclaren/">麥拉倫</a>－賓士', out)
        self.assertEqual(strip_tags(out), strip_tags(src))

    def test_blockers_and_connector_survive_inline_tag_boundaries(self):
        src = ("<p>紅牛<strong>環</strong>、Red Bull <em>Ring</em>；"
               "麥拉倫－<strong>賓士</strong>。</p>")
        out, links = il.linkify_teams(src)
        self.assertEqual(links, [("mclaren", "mclaren", "麥拉倫")])
        self.assertNotIn('/constructors/red-bull/', out)
        self.assertNotIn('/constructors/mercedes/', out)
        self.assertEqual(strip_tags(out), strip_tags(src))

    def test_first_td_links_second_td_and_th_do_not(self):
        src = ("<table><thead><tr><th>法拉利</th><th>紅牛</th></tr></thead><tbody>"
               "<tr><td>法拉利</td><td>紅牛</td></tr>"
               "<tr><th>備註</th><td><strong>賓士</strong></td><td>麥拉倫</td></tr>"
               "</tbody></table>")
        out, links = il.linkify_teams(src)
        self.assertEqual([cid for cid, _slug, _tok in links], ["ferrari", "mercedes"])
        self.assertIn('<td><a href="/constructors/ferrari/">法拉利</a></td>', out)
        self.assertIn('<th>法拉利</th>', out)
        self.assertIn('<td>紅牛</td>', out)
        self.assertIn('<td><strong><a href="/constructors/mercedes/">賓士</a></strong></td>', out)
        self.assertIn('<td>麥拉倫</td>', out)

    def test_table_is_fully_protected_when_flag_is_off(self):
        src = "<table><tr><td>法拉利</td><td>紅牛</td></tr></table>"
        idx = {"法拉利": ("ferrari", "ferrari")}
        out, hits = il._linkify(
            src, idx, href_of=lambda target: f"/constructors/{target[1]}/",
            key_of=lambda target: target[0], allow_table_first_td=False)
        self.assertEqual((out, hits), (src, []))

    def test_first_linkable_occurrence_wins_between_table_and_prose(self):
        table_first = "<table><tr><td>法拉利</td></tr></table><p>法拉利奪冠。</p>"
        out, links = il.linkify_teams(table_first)
        self.assertEqual(len(links), 1)
        self.assertIn('<td><a href="/constructors/ferrari/">法拉利</a></td>', out)
        self.assertIn('<p>法拉利奪冠。</p>', out)

        prose_first = "<p>法拉利奪冠。</p><table><tr><td>法拉利</td></tr></table>"
        out, links = il.linkify_teams(prose_first)
        self.assertEqual(len(links), 1)
        self.assertIn('<p><a href="/constructors/ferrari/">法拉利</a>奪冠。</p>', out)
        self.assertIn('<td>法拉利</td>', out)

    def test_driver_and_round_default_outputs_remain_byte_exact(self):
        driver_src = "<h2>諾里斯</h2><p>諾里斯追上維斯塔潘。</p><table><tr><td>諾里斯</td></tr></table>"
        driver_want = ('<h2>諾里斯</h2><p><a href="/drivers/norris/">諾里斯</a>追上'
                       '<a href="/drivers/max-verstappen/">維斯塔潘</a>。</p>'
                       '<table><tr><td>諾里斯</td></tr></table>')
        self.assertEqual(il.linkify(driver_src)[0], driver_want)

        round_src = "<h2>匈牙利站</h2><p>匈牙利站賽後。</p><table><tr><td>匈牙利站</td></tr></table>"
        round_want = ('<h2>匈牙利站</h2><p><a href="/seasons/2026/rounds/11/">匈牙利站</a>賽後。</p>'
                      '<table><tr><td>匈牙利站</td></tr></table>')
        self.assertEqual(il.linkify_rounds(round_src, 2026)[0], round_want)

    def test_existing_driver_and_round_links_are_protected_from_team_pass(self):
        src = ('<p><a href="/drivers/ferrari-driver/">Ferrari</a> '
               '<a href="/seasons/2026/rounds/8/">Red Bull</a> 法拉利</p>')
        out, links = il.linkify_teams(src)
        self.assertEqual(links, [("ferrari", "ferrari", "法拉利")])
        self.assertEqual(out.count("<a "), 3)
        self.assertNotIn("<a href=\"/constructors/ferrari/\"><a", out)


class SyntheticArticlesMixin:
    FM = "---\ntitle: {title}\ndate: {date}\nslug: {slug}\n---\n\n{body}\n"

    def make_store(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.arts = self.tmp / "articles"
        self.arts.mkdir()
        self.approved = self.tmp / "approved.json"
        self.exclude = self.tmp / "exclude.json"
        self.exclude.write_text('{"exclude": []}\n', encoding="utf-8")
        self.entries = []
        self._write_approved()

    def _write_approved(self):
        self.approved.write_text(json.dumps({"approved": self.entries}, ensure_ascii=False),
                                 encoding="utf-8")

    def add_article(self, slug, body, title="測試文章", date="2026-08-13"):
        folder = self.arts / slug
        folder.mkdir(exist_ok=True)
        src = folder / "index.md"
        src.write_text(self.FM.format(title=title, date=date, slug=slug, body=body), encoding="utf-8")
        self.entries = [entry for entry in self.entries if entry["slug"] != slug]
        self.entries.append({"slug": slug, "article_sha256": hashlib.sha256(src.read_bytes()).hexdigest()})
        self._write_approved()
        il.clear_caches()


class TeamReverseMentionTests(SyntheticArticlesMixin, unittest.TestCase):
    def setUp(self):
        self.make_store()
        il.clear_caches()
        self.addCleanup(il.clear_caches)

    def mentions(self):
        return il.team_mentions(self.arts, self.approved, self.exclude)

    def test_table_text_counts_as_reverse_mention(self):
        self.add_article("table-only", "| 車隊 | 分數 |\n|---|---:|\n| 法拉利 | 10 |")
        self.assertEqual([a["slug"] for a in self.mentions()["ferrari"]], ["table-only"])

    def test_blockers_and_connector_do_not_count_as_reverse_mentions(self):
        self.add_article("blocked", "紅牛環、紅牛二隊與 Red Bull Ring；麥拉倫－賓士。")
        mentions = self.mentions()
        self.assertNotIn("red_bull", mentions)
        self.assertNotIn("mercedes", mentions)
        self.assertEqual([a["slug"] for a in mentions["mclaren"]], ["blocked"])

    def test_markdown_inline_formatting_does_not_break_reverse_guards(self):
        self.add_article("blocked-format", "紅牛**環**、Red Bull *Ring*；麥拉倫－**賓士**。")
        mentions = self.mentions()
        self.assertNotIn("red_bull", mentions)
        self.assertNotIn("mercedes", mentions)
        self.assertEqual([a["slug"] for a in mentions["mclaren"]], ["blocked-format"])

    def test_reverse_helpers_and_html_use_shared_related_block(self):
        self.add_article("ferrari-story", "法拉利的故事。", title="法拉利故事")
        orig = (il.ARTICLES, il.APPROVED, il.DRAFT_EXCLUDE)
        il.ARTICLES, il.APPROVED, il.DRAFT_EXCLUDE = self.arts, self.approved, self.exclude
        self.addCleanup(setattr, il, "ARTICLES", orig[0])
        self.addCleanup(setattr, il, "APPROVED", orig[1])
        self.addCleanup(setattr, il, "DRAFT_EXCLUDE", orig[2])
        il.clear_caches()
        self.assertEqual(il.team_articles_slice("ferrari"),
                         [("ferrari-story", "法拉利故事", "2026-08-13")])
        html = il.team_related_articles_html("ferrari")
        self.assertIn('<h2 class="sec-title">相關報導</h2>', html)
        self.assertIn('href="/articles/ferrari-story/"', html)
        self.assertEqual(il.team_related_articles_html("audi"), "")


class TeamFingerprintTests(SyntheticArticlesMixin, unittest.TestCase):
    def setUp(self):
        self.make_store()
        self.db = self.tmp / "db.sqlite"
        shutil.copy(fs.DB, self.db)
        self.orig = (il.ARTICLES, il.APPROVED, il.DRAFT_EXCLUDE)
        il.ARTICLES, il.APPROVED, il.DRAFT_EXCLUDE = self.arts, self.approved, self.exclude
        il.clear_caches()
        self.addCleanup(self.restore)

    def restore(self):
        il.ARTICLES, il.APPROVED, il.DRAFT_EXCLUDE = self.orig
        il.clear_caches()

    def fp(self):
        con = sqlite3.connect(str(self.db))
        con.row_factory = sqlite3.Row
        try:
            return regen.compute_fingerprints(con)
        finally:
            con.close()

    def test_new_article_changes_only_mentioned_team_page_not_index(self):
        before = self.fp()
        self.add_article("ferrari-only", "表格：\n\n| 車隊 |\n|---|\n| 法拉利 |")
        after = self.fp()
        changed = [cid for cid in regen.CONSTRUCTOR_IDS
                   if before["constructors"][cid] != after["constructors"][cid]]
        self.assertEqual(changed, ["ferrari"])
        self.assertEqual(before["indices"]["constructors"], after["indices"]["constructors"])
        self.assertEqual(before["seasons"], after["seasons"])
        self.assertEqual(before["drivers"], after["drivers"])

    def test_result_number_change_invalidates_only_that_team_page(self):
        before = self.fp()
        con = sqlite3.connect(str(self.db))
        try:
            row = con.execute(
                "SELECT id, number FROM results WHERE constructor_id='ferrari' "
                "AND position_text IN ('1','2','3') AND number IS NOT NULL LIMIT 1").fetchone()
            self.assertIsNotNone(row)
            con.execute("UPDATE results SET number=? WHERE id=?", (str(row[1]) + "9", row[0]))
            con.commit()
        finally:
            con.close()
        after = self.fp()
        changed = [cid for cid in regen.CONSTRUCTOR_IDS
                   if before["constructors"][cid] != after["constructors"][cid]]
        self.assertEqual(changed, ["ferrari"])
        self.assertNotEqual(before["indices"]["constructors"], after["indices"]["constructors"])


class TeamPageRenderTests(unittest.TestCase):
    def setUp(self):
        il.clear_caches()
        self.addCleanup(il.clear_caches)

    def test_constructor_page_renders_all_actual_related_articles_before_method(self):
        arts = il.team_articles("ferrari")
        self.assertTrue(arts, "前提：8 篇已發布文章至少一篇提到法拉利")
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        old = cg.PUB
        cg.PUB = tmp
        try:
            con = fs.connect_db()
            try:
                cg.gen_constructor("ferrari", con)
            finally:
                con.close()
        finally:
            cg.PUB = old
        page = (tmp / "constructors/ferrari/index.html").read_text(encoding="utf-8")
        related_at = page.index('<h2 class="sec-title">相關報導</h2>')
        method_at = page.index('<h2 class="sec-title">方法說明</h2>')
        self.assertLess(related_at, method_at)
        for art in arts:
            self.assertIn(f'href="/articles/{art["slug"]}/"', page)


if __name__ == "__main__":
    unittest.main()
