#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""百科線站內入口的 gate 測試。

## 由來（2026-08-03，公開前實查）

百科三個索引頁做完了、374 頁生成了、sitemap part 也寫了，但**站內沒有任何一條連結
指向它們**：導覽列 5 個項目零命中、首頁零命中、既有的積分榜/賽曆/賽果/文章頁零命中。

這不是小事，因為這個站已經因為同一個病吃過虧：2026-07 在 GSC 被判
`URL is unknown to Google`、三個月只被檢索 1 次，robots／HTTP／sitemap 全部正常，
真因是**全網域零連入**。修法是 PR #31 補姊妹站互連。

如果百科公開時站內零連入，等於把那個錯誤在自己站內再犯一次——只是這次規模是 374 頁。

## 這裡釘的兩個方向（缺一不可，而且互相拉扯）

1. **未公開時不准有連結** — 百科頁在 published:false 時根本不生成，導覽列或首頁若
   無條件輸出 `/seasons/`，全站每頁都會掛一條 404。
2. **公開時一定要有連結** — 只靠 sitemap 與 IndexNow 曝光而站內零連入，就是上面那個病。

單獨測任何一個方向都會漏：只測 ①，實作可以永遠不輸出連結（全暗）也全綠；
只測 ②，實作可以無條件輸出（未公開時掛 404）也全綠。所以兩個方向都要有測試。

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# 百科四線的索引頁。/circuits/ 2026-08-23 建、2026-08-24 補上首頁磁磚——在那之前
# 首頁磁磚只有三塊，賽道線在首頁零連入（站內只剩導覽列與頁尾兩個 surface）。
# 首頁磁磚（build-articles.render_home）與全站導覽（racinglib）是兩個 owner，
# 但該連到的東西是同一組，所以共用這一份清單：任何一線漏掉哪個 surface 都會紅。
ENCYCLOPEDIA_INDEXES = ("/seasons/", "/drivers/", "/constructors/", "/circuits/")

ENCYCLOPEDIA_NAV_ENTRIES = ENCYCLOPEDIA_INDEXES


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rc = _load("racinglib", "racinglib.py")


class NavGateTests(unittest.TestCase):
    """導覽列：`requires: encyclopedia` 的項目只在公開時出現。"""

    def setUp(self):
        self.orig = rc.ENCYCLOPEDIA_PUBLISHED
        self.addCleanup(setattr, rc, "ENCYCLOPEDIA_PUBLISHED", self.orig)

    def test_hidden_when_unpublished(self):
        rc.ENCYCLOPEDIA_PUBLISHED = False
        self.assertNotIn("/seasons/", rc.site_header_html("home"))

    def test_shown_when_published(self):
        rc.ENCYCLOPEDIA_PUBLISHED = True
        self.assertIn("/seasons/", rc.site_header_html("home"))

    def test_ordinary_nav_items_unaffected_by_the_gate(self):
        """反向：gate 只該擋帶 requires 的項目，不該波及其他項目。

        寫太寬的話「未公開」會變成「導覽列少一半」，而且不會有人立刻發現。
        """
        for pub in (True, False):
            rc.ENCYCLOPEDIA_PUBLISHED = pub
            html = rc.site_header_html("home")
            for href in ("/standings/", "/calendar/", "/results/", "/articles/"):
                self.assertIn(href, html, f"published={pub} 時漏了 {href}")

    def test_config_marks_encyclopedia_nav_with_requires(self):
        """設定檔本身要標記，否則 gate 沒有作用對象（實作對了、資料沒接上）。"""
        nav = json.loads((ROOT / "config" / "site.json").read_text(encoding="utf-8"))["nav"]
        enc = [n for n in nav if n.get("href") in ENCYCLOPEDIA_INDEXES]
        self.assertTrue(enc, "導覽列沒有任何百科入口")
        for n in enc:
            self.assertEqual(n.get("requires"), "encyclopedia",
                             f"{n['href']} 沒標 requires，未公開時會掛 404")


class HomepageEntryTests(unittest.TestCase):
    """首頁：公開後三個索引都要連得到；未公開則一條都不能出現。"""

    def setUp(self):
        self.ba = _load("build_articles", "build-articles.py")
        self.orig = self.ba.rc.ENCYCLOPEDIA_PUBLISHED
        self.addCleanup(setattr, self.ba.rc, "ENCYCLOPEDIA_PUBLISHED", self.orig)

    def _home(self, published):
        # 文章清單在 main() 裡就地組裝，沒有獨立載入器；tile 區塊與文章無關，傳空清單即可。
        self.ba.rc.ENCYCLOPEDIA_PUBLISHED = published
        return self.ba.render_home([])

    def test_no_encyclopedia_links_when_unpublished(self):
        html = self._home(False)
        for href in ENCYCLOPEDIA_INDEXES:
            self.assertNotIn(f'href="{href}"', html,
                             f"未公開卻連向 {href}——那是一條 404")

    def test_all_four_indexes_linked_when_published(self):
        html = self._home(True)
        for href in ENCYCLOPEDIA_INDEXES:
            self.assertIn(f'href="{href}"', html,
                          f"公開了卻沒有連向 {href} 的站內入口")

    def test_circuit_tile_count_comes_from_the_sitemap_part(self):
        """賽道磁磚上的條數必須跟實際頁數同步——寫死的數字新賽道一加就永遠錯。"""
        part = (ROOT / "data" / "sitemap-parts" / "circuits.txt").read_text(
            encoding="utf-8").splitlines()
        urls = [u.strip() for u in part if u.strip()]
        n = len([u for u in urls if not u.rstrip("/").endswith("/circuits")])
        self.assertGreater(n, 0, "circuits sitemap part 是空的，測試前提不成立")
        self.assertIn(f"{n} 條賽道", self._home(True))

    def test_circuit_tile_count_follows_a_doctored_part(self):
        """反向：拿掉幾條賽道 URL，磁磚上的數字必須跟著變。

        不做這一條的話，上面那個斷言在「實作把 78 寫死」的情況下照樣是綠的
        （78 剛好等於今天的真實條數），gate 等於裝飾。
        """
        orig = self.ba._part_urls
        self.addCleanup(setattr, self.ba, "_part_urls", orig)
        trimmed = orig("circuits")[:-3]
        expect = len([u for u in trimmed
                      if u.rstrip("/") != f"{self.ba.BASE}/circuits"])
        self.ba._part_urls = lambda owner: trimmed if owner == "circuits" else orig(owner)
        html = self._home(True)
        self.assertIn(f"{expect} 條賽道", html)
        self.assertNotIn(f"{expect + 3} 條賽道", html)


class ReachabilityTests(unittest.TestCase):
    """☠️ 這一條才是真正要守的東西：公開後百科不得只靠 sitemap 曝光。

    上面兩組測的是「程式有沒有照 flag 走」，這一條測的是**實際產物**——
    如果哪天有人重構首頁、把那段 tile 拿掉，上面的 gate 測試可能還是綠的
    （flag 邏輯沒壞），但站內入口實際上消失了。
    """

    def test_published_build_reaches_every_index_from_home(self):
        cfg = json.loads((ROOT / "config" / "encyclopedia.json").read_text(encoding="utf-8"))
        if cfg.get("published") is not True:
            self.skipTest("百科未公開；未公開狀態由 NavGateTests／HomepageEntryTests 把關")
        home = ROOT / "public-racing" / "index.html"
        self.assertTrue(home.exists(), "首頁產物不存在，無法驗連通性")
        html = home.read_text(encoding="utf-8")
        missing = [h for h in ENCYCLOPEDIA_INDEXES if f'href="{h}"' not in html]
        self.assertEqual(missing, [],
                         f"已公開的首頁產物連不到：{missing}——374 頁只剩 sitemap 一條路")


class SiteWideEncyclopediaEntriesTests(unittest.TestCase):
    """導覽列與頁尾：百科四線各要有一個入口，且兩處都受 published gate。

    ☠️ 為什麼頁尾也要測：2026-08-23 建 /circuits/ 時，78 頁賽道頁在站內的入口是 0
    ——索引頁只能從 sitemap 或直接輸入網址進入，正是本站 2026-07 被 GSC 判
    「URL is unknown to Google」那個病的同一形狀。導覽列與頁尾是唯一出現在**每一頁**
    的兩個 surface，缺一條就是少一整線的站內連入。
    """

    def setUp(self):
        self.orig = rc.ENCYCLOPEDIA_PUBLISHED
        self.addCleanup(setattr, rc, "ENCYCLOPEDIA_PUBLISHED", self.orig)
        self.site = json.loads((ROOT / "config" / "site.json").read_text(encoding="utf-8"))

    def _missing(self, html):
        return [h for h in ENCYCLOPEDIA_NAV_ENTRIES if f'href="{h}"' not in html]

    def test_nav_has_all_four_encyclopedia_entries(self):
        rc.ENCYCLOPEDIA_PUBLISHED = True
        self.assertEqual(self._missing(rc.site_header_html("home", self.site)), [])

    def test_footer_has_all_four_encyclopedia_entries(self):
        rc.ENCYCLOPEDIA_PUBLISHED = True
        self.assertEqual(self._missing(rc.site_footer_html(self.site)), [])

    def test_removing_one_entry_turns_the_check_red(self):
        """反向：從設定檔拿掉任一條，上面兩個檢查都必須抓到（否則斷言是裝飾）。"""
        rc.ENCYCLOPEDIA_PUBLISHED = True
        for href in ENCYCLOPEDIA_NAV_ENTRIES:
            doctored = dict(self.site)
            doctored["nav"] = [n for n in self.site["nav"] if n.get("href") != href]
            doctored["footer_links"] = [l for l in self.site["footer_links"]
                                        if l.get("href") != href]
            self.assertIn(href, self._missing(rc.site_header_html("home", doctored)),
                          f"導覽列拿掉 {href} 卻沒被抓到")
            self.assertIn(href, self._missing(rc.site_footer_html(doctored)),
                          f"頁尾拿掉 {href} 卻沒被抓到")

    def test_all_four_hidden_when_unpublished(self):
        """未公開時兩處都不准出現——頁尾漏 gate＝全站每頁四條 404。"""
        rc.ENCYCLOPEDIA_PUBLISHED = False
        for html in (rc.site_header_html("home", self.site), rc.site_footer_html(self.site)):
            for href in ENCYCLOPEDIA_NAV_ENTRIES:
                self.assertNotIn(f'href="{href}"', html, f"未公開卻連向 {href}")

    def test_non_encyclopedia_footer_links_survive_the_gate(self):
        """反向：gate 只該擋帶 requires 的項目。寫太寬＝未公開時頁尾少一半，沒人會發現。"""
        for pub in (True, False):
            rc.ENCYCLOPEDIA_PUBLISHED = pub
            html = rc.site_footer_html(self.site)
            for href in ("/standings/", "/calendar/", "/articles/", rc.ERRATA_INDEX_PATH):
                self.assertIn(href, html, f"published={pub} 時頁尾漏了 {href}")

    def test_config_marks_every_encyclopedia_entry_with_requires(self):
        """設定檔沒標 requires＝gate 沒有作用對象（實作對了、資料沒接上）。"""
        for field in ("nav", "footer_links"):
            items = [i for i in self.site[field]
                     if i.get("href") in ENCYCLOPEDIA_NAV_ENTRIES]
            self.assertEqual(len(items), len(ENCYCLOPEDIA_NAV_ENTRIES),
                             f"{field} 的百科入口數不對")
            for i in items:
                self.assertEqual(i.get("requires"), "encyclopedia",
                                 f'{field} 的 {i["href"]} 沒標 requires，未公開時會掛 404')


if __name__ == "__main__":
    unittest.main()
