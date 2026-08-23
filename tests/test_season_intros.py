#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M6 第二棒：人工賽季導言回歸測試。

鎖住三件事：
1. 機械對帳（check-season-intros.py）：四篇導言真跑全綠；竄改導言數字 / 竄改 verified claim
   值 → 對帳抓到（合成 tamper）。
2. 核准 gate（default-deny）：未核准/sha 不符不渲染（合成驗證）；四篇皆已由 Charlie 核准
   （2002＝7/23、其餘三篇＝7/24），現狀鎖防誤刪。
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


# 已核准 16 篇（config/approved.json 的 season-intro-* 條目；2026-08-23 重簽 facts hash）
APPROVED_YEARS = [1950, 1958, 1961, 1964, 1976, 1984, 1986, 1988,
                  1994, 2002, 2007, 2008, 2010, 2012, 2016, 2021]


def _synthetic_entry(year, content_dir=CONTENT):
    """合成一筆「當下檔案狀態」的核准條目（.md＋facts pack 兩個 sha 都綁）。"""
    e = {"slug": f"season-intro-{year}", "article_sha256": _sha(content_dir / f"{year}.md")}
    fp = content_dir / f"{year}.facts.json"
    if fp.exists():
        e["facts_sha256"] = _sha(fp)
    return e


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

    def test_rank_claim_binds_value_to_driver(self):
        good = {"kind": "champion_points", "value": 144, "driver": "michael_schumacher",
                "_season": 2002}
        bad = {**good, "driver": "barrichello"}
        self.assertTrue(chk.verify_claim(self.con, good)[0])
        self.assertFalse(chk.verify_claim(self.con, bad)[0])

    def test_driver_position_kind_distinguishes_equal_points(self):
        # 2007 Hamilton/Alonso 都是 109 分，但正式順位為 P2/P3。
        hamilton = {"kind": "driver_position", "value": 2, "driver": "hamilton", "_season": 2007}
        alonso_wrong = {"kind": "driver_position", "value": 2, "driver": "alonso", "_season": 2007}
        self.assertTrue(chk.verify_claim(self.con, hamilton)[0])
        self.assertFalse(chk.verify_claim(self.con, alonso_wrong)[0])


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
        approved = {"season-intro-2002": _synthetic_entry(2002)}
        approved_html = self._render_year(2002, approved)
        block = g.approved_intro_html(2002, approved)
        self.assertTrue(block)
        self.assertEqual(approved_html.replace(block, ""), unapproved)

    def test_synthetic_approval_renders_intro_at_top(self):
        approved = {"season-intro-2002": _synthetic_entry(2002)}
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


class FactsBindingGateTests(unittest.TestCase):
    """核准綁定的第二條腿：facts pack 也要 sha 全等（2026-08-23 Charlie 裁決）。

    原本 approved.json 記了 `facts_sha256` 但消費端只驗 `article_sha256`——那個欄位是
    死字串。實害在 PR #53 現形：anchor 遷移一次改了 16 篇 facts pack，16 個
    facts_sha256 全部過期，而 16 篇導言照常渲染，沒有任何一層會叫。核准的語意是
    「這段文字，連同它宣稱的那組事實與那份機械對帳，被人看過」，只綁 .md 綁不住它。

    正向（16 篇真的還在渲染）與反向（facts 改一個位元組就不渲染）都要有：
    只測反向的話，把 gate 寫成「一律不渲染」也全綠。
    """

    def setUp(self):
        # 改 facts 檔要在副本上動——INTRO_DIR 指向 content/seasons/，直接改真檔會污染 repo。
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.content = self.tmp / "seasons"
        shutil.copytree(CONTENT, self.content)

    def _use_copy(self):
        orig = g.INTRO_DIR
        g.INTRO_DIR = self.content
        self.addCleanup(setattr, g, "INTRO_DIR", orig)

    def test_all_sixteen_approved_intros_still_render(self):
        """陰性：真 config／真檔案下，16 篇一篇都不能掉（重簽有沒有簽好，看這條）。"""
        approved = g._load_approved()
        missing = [y for y in APPROVED_YEARS if not g.approved_intro_html(y, approved)]
        self.assertEqual(missing, [], f"這幾季的導言不渲染了：{missing}")

    def test_real_config_records_current_facts_sha_for_all_sixteen(self):
        """陰性（資料層）：approved.json 記的 facts hash＝現行 facts pack 的 hash。"""
        approved = g._load_approved()
        stale = [y for y in APPROVED_YEARS
                 if approved[g.INTRO_SLUG.format(year=y)].get("facts_sha256")
                 != _sha(CONTENT / f"{y}.facts.json")]
        self.assertEqual(stale, [], f"facts_sha256 過期：{stale}")

    def test_one_byte_change_in_facts_pack_kills_the_intro(self):
        """陽性：facts pack 改一個位元組 → 該季導言不渲染（.md 一個字都沒動）。"""
        self._use_copy()
        approved = {"season-intro-2002": _synthetic_entry(2002, self.content)}
        self.assertTrue(g.approved_intro_html(2002, approved), "改動前應該要渲染")
        fp = self.content / "2002.facts.json"
        fp.write_bytes(fp.read_bytes() + b" ")   # 一個位元組
        self.assertEqual(g.approved_intro_html(2002, approved), "")

    def test_approval_without_facts_hash_is_denied(self):
        """陽性：facts pack 在、核准沒綁 hash → default-deny（不是「沒記就當通過」）。"""
        entry = _synthetic_entry(2002)
        for variant in ({k: v for k, v in entry.items() if k != "facts_sha256"},
                        {**entry, "facts_sha256": None},
                        {**entry, "facts_sha256": "0" * 64}):
            self.assertEqual(g.approved_intro_html(2002, {"season-intro-2002": variant}), "")

    def test_seasons_without_facts_pack_keep_article_only_binding(self):
        """反向：沒有 facts pack 的舊條目維持原行為（gate 只准補檢查，不准連累無辜）。"""
        self._use_copy()
        (self.content / "2002.facts.json").unlink()
        entry = {"slug": "season-intro-2002",
                 "article_sha256": _sha(self.content / "2002.md")}
        self.assertTrue(g.approved_intro_html(2002, {"season-intro-2002": entry}))

    def test_article_binding_still_enforced(self):
        """反向：加了 facts 這條腿，不准把原本那條腿弄鬆。"""
        self._use_copy()
        entry = _synthetic_entry(2002, self.content)
        md = self.content / "2002.md"
        md.write_bytes(md.read_bytes() + b" ")
        self.assertEqual(g.approved_intro_html(2002, {"season-intro-2002": entry}), "")


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
        # 有 approved 譯名者用譯名；無者用原文。抽驗：舒馬克/塞納/維斯塔潘/漢米爾頓/法拉利/麥拉倫 用譯名；
        # 無譯名者（Barrichello/Alfa Romeo）維持原文、不得出現自譯中文名。
        # ⚠️ Fangio/Farina/Prost 於 2026-07-23 M6 已回填 approved 譯名，但既有導言草稿仍以原文書寫
        #    （草稿是靜態 .md、不隨譯名表變動）；下方 banned 清單相應排除這三個新 approved 值。
        self.assertIn("麥可・舒馬克", self._text(2002))
        self.assertIn("艾爾頓・塞納", self._text(1988))
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
