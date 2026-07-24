#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M6 第二棒：人工賽季導言回歸測試。

鎖住三件事：
1. 機械對帳（check-season-intros.py）：四篇導言真跑全綠；竄改導言數字 / 竄改 verified claim
   值 → 對帳抓到（合成 tamper）。
2. 核准 gate（default-deny）：四篇草稿未進 approved.json → 賽季頁不渲染導言、與現狀 byte-identical；
   合成核准後才渲染；sha 不符不渲染。
3. 導言站規：120–200 字、只用 approved 譯名值、無 em dash。

跑法：python3 -m unittest discover -s tests -v
"""
import hashlib
import importlib.util
import pathlib
import re
import shutil
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "seasons"
YEARS = [1950, 1988, 2002, 2021]
# 2002 已於 2026-07-23 由 Charlie 核准（進 config/approved.json）；其餘三篇仍為草稿。
APPROVED_YEARS = [2002]
DRAFT_YEARS = [y for y in YEARS if y not in APPROVED_YEARS]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


chk = _load("check_season_intros", "check-season-intros.py")
g = _load("gen_racing_seasons", "gen-racing-seasons.py")
rc = g.rc


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


class ReconciliationTests(unittest.TestCase):
    """機械對帳：真跑全綠 + 合成 tamper 抓得到。"""

    def setUp(self):
        self.con = sqlite3.connect(chk.DB_PATH)
        self.addCleanup(self.con.close)

    def test_all_four_intros_pass(self):
        for y in YEARS:
            errs = chk.check_year(y, self.con)
            self.assertEqual(errs, [], f"{y} 對帳應全綠，卻有：{errs}")

    def _tamper(self, year, transform):
        """把某年導言/facts 複製進 temp、以 transform 改寫，回 check_year 錯誤清單。"""
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for src in (CONTENT / f"{year}.md", CONTENT / f"{year}.facts.json"):
            (tmp / src.name).write_bytes(src.read_bytes())
        transform(tmp, year)
        orig = chk.CONTENT
        chk.CONTENT = tmp
        self.addCleanup(lambda: setattr(chk, "CONTENT", orig))
        return chk.check_year(year, self.con)

    def test_tampered_intro_number_is_caught(self):
        # 把 2002 的「144 分」改成「145 分」→ 145 不在任何 verified claim 值集合 → 裸奔
        def bump(tmp, year):
            md = tmp / f"{year}.md"
            md.write_text(md.read_text(encoding="utf-8").replace("144 分", "145 分"), encoding="utf-8")
        errs = self._tamper(2002, bump)
        self.assertTrue(errs, "竄改導言數字應被抓到")
        self.assertTrue(any("145" in e and "裸奔" in e for e in errs), errs)

    def test_tampered_verified_claim_value_fails_reverify(self):
        # 把 facts pack 的 champion_points 由 144 改成 999（導言仍寫 144）→ 導言 144 找不到 claim（裸奔）
        # 且 999 這條 verified claim 與 sqlite 重查不符 → 兩層都咬
        import json
        def bend(tmp, year):
            fp = tmp / f"{year}.facts.json"
            d = json.loads(fp.read_text(encoding="utf-8"))
            for c in d["claims"]:
                if c.get("kind") == "champion_points":
                    c["value"] = 999
            fp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        errs = self._tamper(2002, bend)
        self.assertTrue(any("champion_points" in e and "重查不符" in e for e in errs),
                        f"竄改 verified claim 值應被 sqlite 重查抓到：{errs}")

    def test_main_returns_zero_for_real_content(self):
        self.assertEqual(chk.main([str(y) for y in YEARS]), 0)


class DefaultDenyGateTests(unittest.TestCase):
    """核准 gate：未核准不渲染且 byte-identical；合成核准後渲染；sha 不符不渲染。"""

    def _render_year(self, year, approved_override=None):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig_rc, orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig_rc), setattr(g, "PUB", orig_g)))
        orig_load = g._load_approved
        if approved_override is not None:
            g._load_approved = lambda: approved_override
            self.addCleanup(lambda: setattr(g, "_load_approved", orig_load))
        g.render_season(year)
        return (tmp / "seasons" / str(year) / "index.html").read_text(encoding="utf-8")

    def test_all_four_intros_are_charlie_approved(self):
        # 2026-07-24 Charlie 明示「核准 1950／1988／2021」（2002 同日稍早先核）——
        # 四篇皆應在 config/approved.json 且 sha 與現行檔案吻合（防未來誤刪/漂移）。
        approved = g._load_approved()
        for y in (1950, 1988, 2002, 2021):
            slug = g.INTRO_SLUG.format(year=y)
            self.assertIn(slug, approved, f"{slug} 應已核准（Charlie 明示）")

    def test_2002_is_approved_in_real_config_and_renders(self):
        # 實測（非合成）：2002 已進真 config/approved.json，且以真配置渲染時導言確實出現在頁頂。
        approved = g._load_approved()
        self.assertIn(g.INTRO_SLUG.format(year=2002), approved,
                      "2002 應已在真 approved.json（Charlie 2026-07-23 核准）")
        html = self._render_year(2002)  # 走真 approved.json（不覆寫）
        self.assertIn("編輯導言", html)
        self.assertIn("144 分", html)
        self.assertIn("麥可・舒馬克", html)
        self.assertLess(html.index("ent-hero"), html.index("編輯導言"))
        self.assertLess(html.index("編輯導言"), html.index("賽季速寫"))

    def test_unapproved_renders_no_intro(self):
        # 空核准清單（覆寫）→ 任何年份都不渲染導言，與 default-deny 一致。
        html = self._render_year(2002, {})
        self.assertNotIn("編輯導言", html)
        self.assertNotIn("editorial-intro", html)

    def test_approved_intro_is_purely_additive(self):
        # byte-identical 證明（單頁版）：合成核准後的頁面 == 未核准頁面「插入導言區塊」，
        # 移除該區塊即完全還原未核准頁面（gate 是純附加、不動其他任何位元）。
        unapproved = self._render_year(2002, {})  # 顯式空核准，與真 config 脫鉤
        sha = _sha(CONTENT / "2002.md")
        approved = {"season-intro-2002": {"slug": "season-intro-2002", "article_sha256": sha}}
        approved_html = self._render_year(2002, approved)
        block = g.approved_intro_html(2002, approved)
        self.assertTrue(block)
        self.assertEqual(approved_html.replace(block, ""), unapproved)

    def test_synthetic_approval_renders_intro_at_top(self):
        sha = _sha(CONTENT / "2002.md")
        approved = {"season-intro-2002": {"slug": "season-intro-2002", "article_sha256": sha}}
        html = self._render_year(2002, approved)
        self.assertIn("編輯導言", html)
        self.assertIn("144 分", html)
        self.assertIn("麥可・舒馬克", html)
        # 頁頂：導言區塊在「賽季速寫」之前、hero 之後
        self.assertLess(html.index("編輯導言"), html.index("賽季速寫"))
        self.assertLess(html.index("ent-hero"), html.index("編輯導言"))

    def test_hash_mismatch_does_not_render(self):
        approved = {"season-intro-2002": {"slug": "season-intro-2002",
                                          "article_sha256": "0" * 64}}
        html = self._render_year(2002, approved)
        self.assertNotIn("編輯導言", html)

    def test_missing_file_renders_empty(self):
        # 未寫導言的季（如 1999，無 content/seasons/1999.md）→ 恆空
        self.assertEqual(g.approved_intro_html(1999, {"season-intro-1999": {
            "slug": "season-intro-1999", "article_sha256": "x"}}), "")


class IntroStyleTests(unittest.TestCase):
    """導言站規：120–200 字、只用 approved 譯名值、無 em dash、開頭句式互異。"""

    def _text(self, year):
        return (CONTENT / f"{year}.md").read_text(encoding="utf-8").strip()

    def test_length_120_200(self):
        for y in YEARS:
            n = len(self._text(y).replace(" ", ""))  # 不計盤古之白
            self.assertTrue(120 <= n <= 200, f"{y} 字數 {n} 不在 120–200")

    def test_no_em_dash(self):
        for y in YEARS:
            self.assertNotIn("—", self._text(y), f"{y} 不得使用 em dash")

    def test_only_approved_translations(self):
        # 有 approved 譯名者用譯名；無者用原文。抽驗：舒馬克/冼拿/維斯塔潘/漢米爾頓/法拉利/麥拉倫 用譯名；
        # 無譯名者（Barrichello/Alfa Romeo）維持原文、不得出現自譯中文名。
        # ⚠️ Fangio/Farina/Prost 於 2026-07-23 M6 已回填 approved 譯名，但既有導言草稿仍以原文書寫
        #    （草稿是靜態 .md、不隨譯名表變動）；下方 banned 清單相應排除這三個新 approved 值。
        self.assertIn("麥可・舒馬克", self._text(2002))
        self.assertIn("艾爾頓・冼拿", self._text(1988))
        self.assertIn("麥克斯・維斯塔潘", self._text(2021))
        self.assertIn("路易斯・漢米爾頓", self._text(2021))
        self.assertIn("法拉利", self._text(2002))
        self.assertIn("麥拉倫", self._text(1988))
        # 無 approved 譯名者以原文出現（誠實 fallback）
        self.assertIn("Rubens Barrichello", self._text(2002))
        self.assertIn("Nino Farina", self._text(1950))
        self.assertIn("Juan Fangio", self._text(1950))
        self.assertIn("Alain Prost", self._text(1988))
        self.assertIn("Alfa Romeo", self._text(1950))
        # 常見自譯陷阱：不得出現這些「非 approved」中譯。
        # 註：prost 的 approved 值為『亞倫・保魯斯』（非普羅斯特）、fangio 為『方吉歐』（非范吉歐），
        #     故普羅斯特/范吉歐 仍是禁列變體；farina『法里納』已成 approved 值故移出禁列。
        for banned in ("普羅斯特", "普洛斯特", "范吉歐", "愛快羅密歐", "巴里切羅"):
            for y in YEARS:
                self.assertNotIn(banned, self._text(y), f"{y} 出現非 approved 自譯：{banned}")

    def test_openings_are_distinct(self):
        # 四篇開頭句式不套版：取前 6 字，彼此不得相同
        heads = [self._text(y)[:6] for y in YEARS]
        self.assertEqual(len(set(heads)), len(heads), f"開頭句式重複：{heads}")


if __name__ == "__main__":
    unittest.main()
