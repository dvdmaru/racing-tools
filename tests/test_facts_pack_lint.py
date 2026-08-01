#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""facts pack gate 的回歸測試（lint-pack ／ verify-numbers）。

由來（2026-08-01）：本站所有 gate 原本都跑在**稿子**上，沒有一道跑在 **facts pack** 上。
而雪邦那篇連退兩輪，兩次的根因都在 facts pack：

- thesis 被寫成「指出外電錯在哪」→ 寫手照做，整篇變糾正稿（記憶 W19）
- facts pack 只管事實不管聲音 → 連出兩版同樣的報告腔（記憶 W20）
- 「一停就是二十七年」是寫手自己做減法算的（正確為 28，且 1975 年還有一屆非錦標賽）

骨架與聲音是在派工那一刻決定的，改稿階段都是在補。所以 gate 往上游移。

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cf = _load("check_facts_pack", "check-facts.py")

GOOD_VOICE = {
    "headline_style": "標題自己就是一個事實，不是分類標籤。",
    "forbidden_meta": "❌「本文只能標出處，無法獨立核實」→ ✅「這是媒體轉述的說法。」",
    "referent_policy": "指代具體，發稿前 grep 那次／後者。",
}
MINIMAL = {"thesis": "名稱與舉辦地本來就是兩條線。",
           "voice": GOOD_VOICE,
           "must_not_claim": ["不得推測動機"]}


def lint(pack):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False)
        path = f.name
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = cf.lint_pack(path)
    return ok, buf.getvalue()


class LintPackBlocks(unittest.TestCase):
    """正向：該擋的要擋。"""

    def test_minimal_valid_pack_passes(self):
        ok, _ = lint(MINIMAL)
        self.assertTrue(ok)

    def test_missing_voice_blocks(self):
        p = dict(MINIMAL); p.pop("voice")
        ok, out = lint(p)
        self.assertFalse(ok)
        self.assertIn("缺 voice", out)

    def test_missing_must_not_claim_blocks(self):
        p = dict(MINIMAL); p.pop("must_not_claim")
        ok, out = lint(p)
        self.assertFalse(ok)
        self.assertIn("must_not_claim", out)

    def test_voice_without_before_after_blocks(self):
        """W20 的教訓：只寫『口語一點』這種形容詞，寫手做不到。"""
        p = dict(MINIMAL)
        p["voice"] = dict(GOOD_VOICE, forbidden_meta="正文請口語一點，不要太官腔")
        ok, out = lint(p)
        self.assertFalse(ok)
        self.assertIn("before→after", out)

    def test_reserved_word_trap_blocks(self):
        """☠️ 我自己種過的歧義：facts pack 用「本站」指一場比賽。"""
        p = dict(MINIMAL)
        p["items"] = [{"claim": "巴林方取得本站全部收益"}]
        ok, out = lint(p)
        self.assertFalse(ok)
        self.assertIn("保留詞誤用", out)

    def test_debunking_thesis_warns(self):
        """W19：thesis 以『某方寫錯』為主軸 → 警告（不擋，但要看得到）。"""
        p = dict(MINIMAL, thesis="外電說這是史上第一次，本站查了發現錯了。")
        ok, out = lint(p)
        self.assertTrue(ok, "這是警告不是擋線")
        self.assertIn("糾正稿", out)


class LintPackDoesNotOverreach(unittest.TestCase):
    """反向：不該擋的不要擋，否則 gate 會被關掉。"""

    def test_ordinary_thesis_produces_no_warning(self):
        """⚠️ 斷言要挑對目標：腳本結尾固定會印一行能力邊界聲明（也帶 ⚠️），
        拿整份輸出找 ⚠️ 會永遠命中。這裡只看**縮排過的 pack 層警告**。"""
        ok, out = lint(MINIMAL)
        self.assertTrue(ok)
        pack_warnings = [ln for ln in out.splitlines() if ln.startswith("  ⚠️")]
        self.assertEqual(pack_warnings, [])

    def test_reserved_word_allows_legitimate_site_reference(self):
        """「本站賽事資料庫」是正當用法，不能一律禁「本站」。"""
        p = dict(MINIMAL)
        p["items"] = [{"claim": "本站賽事資料庫涵蓋 1950 年起的世界錦標賽賽事"}]
        ok, out = lint(p)
        self.assertTrue(ok, out)


class VerifyNumbers(unittest.TestCase):
    """寫手不做算術：稿內數字必須在 facts pack 找得到來源。"""

    def _run(self, pack, article_body):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
            fp = f.name
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(article_body)
            ap = f.name
        buf = io.StringIO()
        with redirect_stdout(buf):
            cf.verify_numbers(fp, ap)
        return buf.getvalue()

    def test_flags_number_absent_from_pack(self):
        """「一停就是二十七年」那一類：寫手自己算出來的數字。"""
        out = self._run(dict(MINIMAL, gap="1954 到 1982"), "瑞士站一停就是 27 年。")
        self.assertIn("27", out)
        self.assertIn("不在 facts pack", out)

    def test_number_present_in_pack_passes(self):
        out = self._run(dict(MINIMAL, gap_years=28), "前後相隔 28 年。")
        self.assertIn("每個數字都能在 facts pack 找到來源", out)

    def test_link_urls_do_not_produce_noise(self):
        """連結裡的數字不是內文主張，不該被當成寫手算的。"""
        out = self._run(MINIMAL, "見[來源](https://example.com/news/12433/13519453/x)。")
        self.assertIn("每個數字都能在 facts pack 找到來源", out)


if __name__ == "__main__":
    unittest.main()
