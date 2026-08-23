#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""容錯放流程：每頁的回報入口、GitHub 回報表單、/errata/ 公開勘誤索引。

## 由來（2026-08-23）

這個站的定位是「不假裝零錯誤，而是把改正過程攤開」：每頁「回報錯誤」→ default-deny
裁決（查不到可靠出處就不改）→ 修 facts 層 → 公開勘誤紀錄＋具名致謝。

7/21 定位定案後，實際只做了第三段的一半：`stability.py` 會把 `data/errata.json` 渲染在
**兩篇文章頁**上。全站零回報入口、沒有勘誤索引頁、沒有致謝欄。也就是說前兩段對讀者
不存在——讀者發現錯誤時無處可講，而我們會把「沒人回報」讀成「沒有錯」。

## 這裡釘的四件事

1. **入口在 footer＝每一頁都有**。它不放 config/site.json 的 footer_links：那份清單少一條
   沒人會發現，而這條是回報通道本身（理由寫在 racinglib.errata_entry_html 上方）。
2. **反向測試**。拿掉入口，斷言必須真的變紅——否則這個檔就是本站踩過的「gate 太寬但全綠」。
3. **/errata/ 頁的欄位真的渲染**，含 credit=null → 顯示「站方自查」。
4. **表單真的存在且可解析**，而且 footer 連結指到的 template 檔名必須真的在 repo 裡
   （連結指向不存在的 template，GitHub 會靜默退回一般 issue 表單，沒有任何一層會叫）。

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import pathlib
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rc = _load("racinglib", "racinglib.py")
ba = _load("build_articles", "build-articles.py")
SITE = json.loads((ROOT / "config" / "site.json").read_text(encoding="utf-8"))


class FooterEntryTests(unittest.TestCase):
    """每一頁的頁尾都要有回報入口與勘誤紀錄連結。"""

    def test_footer_has_report_link(self):
        html = rc.site_footer_html(SITE)
        self.assertIn("回報錯誤", html)
        self.assertIn(rc.ERRATA_REPORT_URL, html)

    def test_footer_has_errata_index_link(self):
        self.assertIn(f'href="{rc.ERRATA_INDEX_PATH}"', rc.site_footer_html(SITE))

    def test_external_link_carries_noopener_and_no_nofollow(self):
        html = rc.errata_entry_html()
        self.assertIn('rel="noopener"', html)
        self.assertIn('target="_blank"', html)
        self.assertNotIn("nofollow", html)

    def test_every_page_type_gets_it_via_page_shell(self):
        """七種頁型都走 page_shell，所以一處改全站生效——這裡釘住那個假設。"""
        shell = rc.page_shell("t", "d", f"{rc.BASE}/x/", "", "<p>x</p>", "home")
        self.assertIn("回報錯誤", shell)

    def test_removing_the_entry_actually_turns_this_red(self):
        """反向：入口拿掉後，上面幾條斷言必須不成立。

        全綠有兩種可能——入口真的在，或斷言比對到別的東西（例如頁面別處剛好有這三個字）。
        沒有這條，這個檔會在入口被刪掉的那天照樣全綠。
        """
        orig = rc.errata_entry_html
        self.addCleanup(setattr, rc, "errata_entry_html", orig)
        rc.errata_entry_html = lambda: ""
        html = rc.site_footer_html(SITE)
        self.assertNotIn("回報錯誤", html)
        self.assertNotIn(rc.ERRATA_REPORT_URL, html)

    def test_report_url_is_not_the_site_itself(self):
        """回報要落到收得到的地方（GitHub issue），不是站內某個沒人看的頁。"""
        self.assertNotEqual(urlsplit(rc.ERRATA_REPORT_URL).netloc,
                            urlsplit(SITE["base"]).netloc)


class IssueTemplateTests(unittest.TestCase):
    """.github/ISSUE_TEMPLATE/errata.yml 要能被解析，且欄位齊全。"""

    @classmethod
    def setUpClass(cls):
        cls.name = parse_qs(urlsplit(rc.ERRATA_REPORT_URL).query)["template"][0]
        cls.path = ROOT / ".github" / "ISSUE_TEMPLATE" / cls.name

    def test_template_file_the_link_points_at_exists(self):
        """連結寫 template=errata.yml，檔案就必須真的叫那個名字。

        指到不存在的 template 時 GitHub 只會安靜地退回一般 issue 表單——
        使用者看到的是空白框，而我們這邊沒有任何訊號。
        """
        self.assertTrue(self.path.exists(), f"連結指向不存在的 template：{self.name}")

    def test_yaml_parses(self):
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)
        self.assertTrue(data.get("name"))
        self.assertTrue(data.get("description"))

    def test_required_fields_present(self):
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        ids = {b.get("id") for b in data["body"]}
        for field in ("page_url", "seen", "expected", "source"):
            self.assertIn(field, ids, f"回報表單缺欄位：{field}")

    def test_three_core_fields_are_mandatory(self):
        """頁面網址／看到的值／認為正確的值缺一不可——少任何一個都查不動。"""
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        req = {b["id"]: b.get("validations", {}).get("required", False)
               for b in data["body"] if b.get("id")}
        for field in ("page_url", "seen", "expected"):
            self.assertTrue(req[field], f"{field} 應為必填")
        # 出處不設必填：門檻拉太高會讓讀者放棄回報；沒出處我們自己查，只是慢一點。
        self.assertFalse(req["source"])


class ErrataDataSchemaTests(unittest.TestCase):
    """data/errata.json 的 schema：credit 這個 key 一定要在（值可以是 null）。"""

    ITEMS = json.loads((ROOT / "data" / "errata.json").read_text(encoding="utf-8"))

    def test_required_keys(self):
        for e in self.ITEMS:
            for key in ("slug", "at", "what", "credit"):
                self.assertIn(key, e, f"勘誤 {e.get('at')} 缺 {key} 欄")

    def test_credit_key_distinguishes_null_from_missing(self):
        """`credit: null`（站方自查）與「沒有 credit 欄」（忘了記）不是同一件事。

        用 .get() 讓兩者塌成同一個顯示值，日後就分不出來，具名致謝也就無從稽核。
        """
        for e in self.ITEMS:
            self.assertTrue(e["credit"] is None or isinstance(e["credit"], str))


class ErrataPageTests(unittest.TestCase):
    """/errata/ 索引頁：欄位要渲染、零筆要誠實、不准藏頁。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.orig_pub = rc.PUB
        rc.PUB = self.tmp                       # shared css 落到 tmp，不碰產物目錄
        self.addCleanup(setattr, rc, "PUB", self.orig_pub)
        self.orig_load = ba.load_errata
        self.addCleanup(setattr, ba, "load_errata", self.orig_load)

    def _render(self, items, articles=None):
        ba.load_errata = lambda: items
        return ba.render_errata_page(articles or [])

    def test_renders_every_field(self):
        html = self._render([{
            "slug": "demo", "at": "2026-08-20 09:00", "what": "把甲改成乙。",
            "was": "甲", "now": "乙", "source": "https://example.org/doc",
            "credit": "某位讀者",
        }], articles=[{"slug": "demo", "meta": {"title": "示範文章"}}])
        for expect in ("2026-08-20 09:00", "示範文章", "甲 → 乙",
                       "把甲改成乙。", "https://example.org/doc", "某位讀者"):
            self.assertIn(expect, html)
        self.assertIn('href="https://racing.twtools.cc/articles/demo/"', html)

    def test_null_credit_shows_self_audit(self):
        html = self._render([{"slug": "demo", "at": "2026-08-20 09:00",
                              "what": "自己查到的。", "credit": None}])
        self.assertIn("站方自查", html)

    def test_named_credit_is_not_overwritten_by_self_audit(self):
        """反向：有具名致謝時不准還顯示「站方自查」——否則致謝欄等於裝飾。"""
        html = self._render([{"slug": "demo", "at": "2026-08-20 09:00",
                              "what": "讀者指出的。", "credit": "某位讀者"}])
        self.assertIn("某位讀者", html)
        self.assertNotIn("站方自查</div>", html)

    def test_zero_entries_says_so_instead_of_hiding(self):
        html = self._render([])
        self.assertIn("尚無勘誤", html)
        self.assertIn("勘誤紀錄", html)          # 頁還在，不是 404

    def test_unpublished_slug_is_not_linked(self):
        """勘誤指向的文章目前沒發布時，只顯示文字不給連結（不掛 404）。"""
        html = self._render([{"slug": "gone", "at": "2026-08-20 09:00",
                              "what": "x", "credit": None}])
        self.assertIn("該頁目前未公開", html)
        self.assertNotIn('href="https://racing.twtools.cc/articles/gone/"', html)

    def test_entries_use_the_quote_zone_class(self):
        """勘誤逐筆包在 rs-list rs-err 裡：check-site-facts 的 quote_zones 靠它排除引用。

        勘誤的職責就是複述原本錯的寫法（「縮為 22 站」）。換掉 class，事實 gate 會
        當場對自己的勘誤頁報錯，而修法多半會變成「把引用改掉」——那就毀了勘誤本身。
        """
        html = self._render([{"slug": "demo", "at": "2026-08-20 09:00",
                              "what": "原文寫「縮為 22 站」。", "credit": None}])
        self.assertIn('<ul class="rs-list rs-err">', html)

    def test_page_is_in_sitemap_part(self):
        part = (ROOT / "data" / "sitemap-parts" / "articles.txt").read_text(encoding="utf-8")
        self.assertIn(f"{rc.BASE}/errata/", part.split())

    def test_built_page_exists(self):
        p = ROOT / "public-racing" / "errata" / "index.html"
        self.assertTrue(p.exists(), "public-racing/errata/index.html 沒被 build 出來")
        self.assertIn("勘誤紀錄", p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
