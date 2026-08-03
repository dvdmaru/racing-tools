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

ENCYCLOPEDIA_INDEXES = ("/seasons/", "/drivers/", "/constructors/")


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

    def test_all_three_indexes_linked_when_published(self):
        html = self._home(True)
        for href in ENCYCLOPEDIA_INDEXES:
            self.assertIn(f'href="{href}"', html,
                          f"公開了卻沒有連向 {href} 的站內入口")


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


if __name__ == "__main__":
    unittest.main()
