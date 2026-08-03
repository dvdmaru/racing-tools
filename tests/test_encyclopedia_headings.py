#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""百科頁標題層級回歸測試（缺口 ⑥）。

背景：百科三種頁型（賽季總覽／賽季實體子頁／分站頁／車手頁／車隊頁）原本 h1×1、h2×0、
h3×0——區塊小標是 <div class="sec-title"> 撐的，沒有語意層級。站上做了 llms.txt／JSON-LD／
IndexNow 一整套 GEO/AEO，但頁面沒有文件大綱，AI 引擎抽段落抓不到結構、螢幕閱讀器也跑不出
目錄。修法是把 sec-title 的載體換成 <h2>（純語意層，class 不動、視覺不動）。

鎖住：
- 每頁恰好一個 h1。
- 每個有區塊的百科頁至少一個 h2；區塊小標的載體是 h2 不是 div。
- 不准跳級：沒有 h2 就不准出現 h3；出現 h3 時前面必須先有 h2。
- 視覺零變化的**必要條件**：.sec-title 的 CSS 必須顯式指定 font-size / font-weight / margin
  （h2 的 UA 預設值只靠全域 `*{margin:0}` reset 補不完，字級與粗細得靠 class 覆寫）。
- h2 的可見文字＝原本 div 的可見文字（沒有新增/刪除任何字）——列出各頁型的預期小標集合。

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import pathlib
import re
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dr = _load("gen_racing_drivers", "gen-racing-drivers.py")
rc, fs, gs, p0 = dr.rc, dr.fs, dr.gs, dr.p0

TAG_RE = re.compile(r"<(h[1-6])\b[^>]*>(.*?)</\1>", re.S)


def _headings(html):
    """回 [(level, 純文字)]，只看 <body> 之後（<head> 沒有標題元素，但保險起見切掉）。"""
    body = html.split("<body>", 1)[-1]
    out = []
    for lvl, inner in TAG_RE.findall(body):
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", inner)).strip()
        out.append((int(lvl[1]), txt))
    return out


def _counts(html):
    h = _headings(html)
    return {lvl: sum(1 for l, _ in h if l == lvl) for lvl in (1, 2, 3)}


class _Rendered(unittest.TestCase):
    """整站三 owner 的代表樣本渲染一次，供各測試共用（含 in-progress／<1958／sprint 變體）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        orig = (rc.PUB, gs.PUB, p0.PUB, dr.PUB)
        rc.PUB = gs.PUB = p0.PUB = dr.PUB = cls.tmp
        try:
            gs.render_index(set(range(gs.FIRST_YEAR, gs.LAST_YEAR + 1)))
            urls = []
            for y in sorted(set(rc.ROUND_YEARS)):
                gs._render_one_season(y, urls, set(rc.ROUND_YEARS))
            gs._render_one_season(1950, urls, set())   # <1958：無車隊榜變體
            con = fs.connect_db()
            try:
                dr.render_index(con)
                dr.gen_driver("michael_schumacher", con)
            finally:
                con.close()
            p0.main()
        finally:
            rc.PUB, gs.PUB, p0.PUB, dr.PUB = orig
        cls.pages = {str(p.relative_to(cls.tmp)): p.read_text(encoding="utf-8")
                     for p in cls.tmp.rglob("index.html")}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)


class HeadingHierarchyTests(_Rendered):
    def test_every_page_has_exactly_one_h1(self):
        bad = {rel: _counts(h)[1] for rel, h in self.pages.items() if _counts(h)[1] != 1}
        self.assertEqual(bad, {}, f"h1 數量不是 1 的頁：{list(bad.items())[:5]}")

    def test_no_level_skip_anywhere(self):
        """h1 → h3 跳級掃描：任一 h3 之前必須已出現過 h2。"""
        bad = []
        for rel, html in self.pages.items():
            seen_h2 = False
            for lvl, txt in _headings(html):
                if lvl == 2:
                    seen_h2 = True
                elif lvl >= 3 and not seen_h2:
                    bad.append((rel, txt))
                    break
        self.assertEqual(bad, [], f"標題跳級：{bad[:5]}")

    def test_section_headings_are_h2_not_div(self):
        """sec-title 的載體必須是 h2；殘留 <div class="sec-title"> 就是漏改。"""
        left = [rel for rel, h in self.pages.items() if '<div class="sec-title"' in h]
        self.assertEqual(left, [], f"仍有 div 版區塊小標：{left[:5]}")
        for rel, html in self.pages.items():
            n_sec = html.count('class="sec-title"')
            n_h2 = _counts(html)[2]
            self.assertEqual(n_sec, n_h2, f"{rel}: sec-title {n_sec} 個但 h2 {n_h2} 個")

    def test_content_pages_actually_have_sections(self):
        """五種內容頁型都要有 h2（索引型頁面本來就只有 h1＋一張表，不強加）。"""
        expect = {
            "seasons/2002/index.html": {"賽季速寫", "冠軍之爭", "積分榜", "各站冠軍", "全季退賽圖鑑"},
            "seasons/2002/drivers/michael-schumacher/index.html": {"逐站成績", "賽季速寫", "退賽紀錄"},
            "seasons/2002/teams/ferrari/index.html": {"車手貢獻拆解", "車隊逐站積分", "賽季速寫", "退賽紀錄"},
            "seasons/2002/rounds/1/index.html": {"頒獎台", "賽況速寫", "正賽完整名次", "退賽名單"},
            "drivers/michael-schumacher/index.html": {"生涯時間軸", "效力車隊", "方法說明"},
            "constructors/ferrari/index.html": {"奪冠賽季"},
        }
        for rel, want in expect.items():
            self.assertIn(rel, self.pages, f"樣本頁沒渲染出來：{rel}")
            got = {t for lvl, t in _headings(self.pages[rel]) if lvl == 2}
            self.assertTrue(want <= got, f"{rel} 缺 h2 小標：{want - got}")

    def test_in_progress_and_sprint_variants_also_have_h2(self):
        """進行中賽季、含衝刺賽的分站頁也要有大綱（變體不能漏改）。"""
        variants = [r for r in self.pages
                    if r.startswith(f"seasons/{rc.SEASON}/") or r.startswith("seasons/1950/")]
        self.assertTrue(variants, "應該有進行中賽季與 1950 的樣本")
        for rel in variants:
            self.assertGreaterEqual(_counts(self.pages[rel])[2], 1, f"{rel} 沒有任何 h2")

    def test_h2_text_is_plain_section_label_not_smuggled_content(self):
        """h2 只承載原本的區塊小標；不得夾帶整段內文（＝有人拿 h2 當版面用）。"""
        long_ones = [(rel, t) for rel, html in self.pages.items()
                     for lvl, t in _headings(html) if lvl == 2 and len(t) > 20]
        self.assertEqual(long_ones, [], f"h2 文字過長，疑似不是小標：{long_ones[:3]}")


class SecTitleCssCompensationTests(unittest.TestCase):
    """視覺零變化的必要條件：h2 的 UA 預設值必須被 .sec-title 全部蓋掉。"""

    def setUp(self):
        m = re.search(r"^\.sec-title\{([^}]*)\}", p0.ENTITY_CSS, re.M)
        self.assertIsNotNone(m, "ENTITY_CSS 找不到 .sec-title 規則")
        self.decl = m.group(1)

    def test_overrides_ua_font_and_margin(self):
        for prop in ("font-size", "font-weight", "margin"):
            self.assertIn(f"{prop}:", self.decl,
                          f".sec-title 必須顯式指定 {prop}，否則 h2 的瀏覽器預設值會漏出來")

    def test_global_reset_zeroes_element_margins(self):
        """全域 `*{margin:0;padding:0}` 是 h2 上下 margin 不冒出來的另一半保障。"""
        self.assertRegex(rc.SHARED_TOKENS_CSS, r"\*\s*\{[^}]*margin:\s*0")

    def test_no_element_bound_selector_for_sec_title(self):
        """任何 `div.sec-title` 這種綁元素名的選擇器都會在改成 h2 後靜默失效。"""
        css = (rc.SHARED_CSS_TEXT + p0.ENTITY_CSS + gs.SEASON_CSS)
        self.assertNotIn("div.sec-title", css)


if __name__ == "__main__":
    unittest.main()
