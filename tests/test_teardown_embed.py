#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文章內嵌 3D 拆解頁（config/teardown.json）回歸測試。

釘住的東西：
1. 設定裡的每一篇都是已核准的真實文章，頁面檔與縮圖都在 articles/<slug>/。
2. 插入規則：只插一次、緊接在第一張 <figure> 之後；文章原稿（index.md）不動。
   負向控制：設定了卻缺檔、或文章沒有 <figure> → 建置中斷（fail loud，不安靜跳過）。
3. 已提交的產出（public-racing）與設定一致：入口恰好一個、在 SVG 示意圖後面、連結與縮圖指到真的檔案。
4. 3D 頁本身：noindex、lang zh-Hant、< 1 MB、不載任何外部資源（離線可開）、
   帶「依公開資料重繪的示意模型」聲明、不用 F1 官方品牌紅 #e10600（IP 裁決：沿用賽車紅 #d63a2f）。
5. 3D 頁不進 sitemap。

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_articles_td", ROOT / "scripts" / "build-articles.py")
ba = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ba)

EMBEDS = ba.load_teardown_embeds()
APPROVED = {e["slug"] for e in json.loads((ROOT / "config" / "approved.json").read_text(encoding="utf-8"))["approved"]}


class ConfigTests(unittest.TestCase):
    def test_has_at_least_one_embed(self):
        # 陽性對照：設定檔讀不到時，下面每一條都會「零筆通過」
        self.assertIn("f1-101-power-unit", EMBEDS)
        self.assertIn("f1-101-active-aero", EMBEDS)
        self.assertIn("f1-101-brakes", EMBEDS)

    def test_every_embed_is_an_approved_article_with_files(self):
        for slug, cfg in EMBEDS.items():
            with self.subTest(slug=slug):
                self.assertIn(slug, APPROVED)
                self.assertTrue((ROOT / "articles" / slug / "index.md").is_file())
                for key in ("page", "poster"):
                    self.assertTrue((ROOT / "articles" / slug / cfg[key]).is_file(), f"缺 {key}：{cfg[key]}")
                for key in ("title", "note", "alt"):
                    self.assertTrue(cfg.get(key, "").strip(), f"{key} 不可空白")


class InjectTests(unittest.TestCase):
    CFG = {"x": {"page": "p.html", "poster": "p.jpg", "title": "T", "note": "N", "alt": "A"}}

    def _with_files(self, files):
        tmp = tempfile.TemporaryDirectory()
        (pathlib.Path(tmp.name) / "x").mkdir()
        for f in files:
            (pathlib.Path(tmp.name) / "x" / f).write_text("x", encoding="utf-8")
        old = ba.SRC
        ba.SRC = pathlib.Path(tmp.name)
        self.addCleanup(lambda: (setattr(ba, "SRC", old), tmp.cleanup()))

    def test_inserted_once_right_after_first_figure(self):
        self._with_files(["p.html", "p.jpg"])
        body = "<p>a</p><figure class=\"diagram\">s1</figure><p>b</p><figure>s2</figure>"
        out = ba.inject_teardown(body, "x", self.CFG)
        self.assertEqual(out.count('class="teardown-cta"'), 1)
        self.assertLess(out.index("s1</figure>"), out.index("teardown-cta"))
        self.assertLess(out.index("teardown-cta"), out.index("<p>b</p>"))
        self.assertIn('href="/articles/x/p"', out)  # 不帶 .html（Cloudflare 會把 .html 轉址掉）
        self.assertIn('src="/articles/x/p.jpg"', out)

    def test_unconfigured_slug_untouched(self):
        body = "<figure>s</figure>"
        self.assertEqual(ba.inject_teardown(body, "other", self.CFG), body)

    def test_missing_page_fails_loud(self):
        self._with_files(["p.jpg"])
        with self.assertRaises(FileNotFoundError):
            ba.inject_teardown("<figure>s</figure>", "x", self.CFG)

    def test_missing_poster_fails_loud(self):
        self._with_files(["p.html"])
        with self.assertRaises(FileNotFoundError):
            ba.inject_teardown("<figure>s</figure>", "x", self.CFG)

    def test_no_figure_fails_loud(self):
        self._with_files(["p.html", "p.jpg"])
        with self.assertRaises(ValueError):
            ba.inject_teardown("<p>no figure</p>", "x", self.CFG)

    def test_text_is_escaped(self):
        self._with_files(["p.html", "p.jpg"])
        cfg = {"x": {**self.CFG["x"], "title": "<b>&"}}
        out = ba.inject_teardown("<figure>s</figure>", "x", cfg)
        self.assertIn("&lt;b&gt;&amp;", out)


class PublishedOutputTests(unittest.TestCase):
    def test_article_page_has_exactly_one_entry_after_the_diagram(self):
        for slug, cfg in EMBEDS.items():
            with self.subTest(slug=slug):
                html = (ROOT / "public-racing" / "articles" / slug / "index.html").read_text(encoding="utf-8")
                self.assertEqual(html.count('class="teardown-cta"'), 1)
                self.assertLess(html.index('<figure class="diagram">'), html.index('class="teardown-cta"'))
                stem = pathlib.Path(cfg["page"]).stem
                self.assertIn(f'href="/articles/{slug}/{stem}"', html)
                for key in ("page", "poster"):
                    out = ROOT / "public-racing" / "articles" / slug / cfg[key]
                    self.assertTrue(out.is_file(), f"產出缺 {out}")
                    self.assertEqual(out.read_bytes(), (ROOT / "articles" / slug / cfg[key]).read_bytes())

    def test_teardown_page_contract(self):
        for slug, cfg in EMBEDS.items():
            with self.subTest(slug=slug):
                p = ROOT / "articles" / slug / cfg["page"]
                html = p.read_text(encoding="utf-8")
                self.assertLess(p.stat().st_size, 1024 * 1024, "頁面要小於 1 MB")
                # 用 assertTrue(x in html)：assertIn 失敗時會把整頁 700 KB 印出來
                for must in ('<meta name="robots" content="noindex">', '<html lang="zh-Hant">', "依公開資料重繪的示意模型"):
                    self.assertTrue(must in html, f"3D 頁缺：{must}")
                self.assertFalse("e10600" in html.lower(), "F1 官方品牌紅不用（2026-07-19 IP 裁決）")
                # 「回到文章」要回到自己那篇（第二篇是照第一篇抄的，最容易留著別篇的連結）
                self.assertTrue(f'"/articles/{slug}/"' in html, "3D 頁的「回到文章」沒有指回這篇")
                for other in EMBEDS:
                    if other != slug:
                        self.assertFalse(f'"/articles/{other}/"' in html, f"3D 頁連回了別篇：{other}")
                # 離線可開：不載任何外部 script／stylesheet／字型
                self.assertIsNone(re.search(r'<script[^>]+src=|<link[^>]+href=|url\((["\']?)https?:', html))

    def test_teardown_page_not_in_sitemap(self):
        for slug, cfg in EMBEDS.items():
            stem = pathlib.Path(cfg["page"]).stem
            for part in (ROOT / "data" / "sitemap-parts").glob("*.txt"):
                self.assertNotIn(f"/articles/{slug}/{stem}", part.read_text(encoding="utf-8"), part.name)
            self.assertNotIn(f"/articles/{slug}/{stem}", (ROOT / "public-racing" / "sitemap.xml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
