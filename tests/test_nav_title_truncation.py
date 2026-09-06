#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前／後篇導覽標題截斷（`build-articles._nav_title`）的回歸測試。

存在理由（2026-09-06 實測，全站既有缺陷，非單一篇引進）：
導覽標題原本是 `html_lib.escape(title)[:40]`，一行裡藏了兩個問題。

☠️ **① 硬切、無省略號、不避開數字 → 造出「看起來完整、意思卻相反」的片段。**
實測全站 22 條導覽有 9 條達到 40 字被硬切，其中 5 條切在數字串中間：

    〈…然後今天有人從第 19 位贏了〉→ 「…有人從第 1」   ＝讀起來像從竿位奪冠
    〈…4 人變成 5X…〉             → 「…人變成 5」
    〈…、50/50…〉                 → 「…、50/50」

沒有刪節號，讀者無從得知它被截斷了，於是把殘句當成完整敘述。
這屬於本站記過的「一個視覺通道只承載一種語意」與「狀態類 UI 要 fail-honest」那一族：
**截斷本身沒問題，看不出是截斷才是問題。**

☠️ **② 先 escape 再切 → 切點落在 HTML 實體中間會產出壞標記。**
標題含 `&`／`<`／`"` 且實體剛好跨過第 40 個字元時，`&quot;` 會被切成 `&qu`。
這一型在現有標題上還沒發作，屬於潛在缺陷；修法是先切原文、再 escape。

⚠️ 本檔同時測 **應該被截斷的** 與 **不該被動到的**。
只測前者的話，把函式寫成「永遠回傳空字串」也會全過。

跑法：python3 -m unittest discover -s tests -v
"""
import html as html_lib
import importlib.util
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("buildarticles",
                                               ROOT / "scripts" / "build-articles.py")
ba = importlib.util.module_from_spec(_spec)
sys.modules["buildarticles"] = ba
_spec.loader.exec_module(ba)

LIMIT = 40


def _old_behaviour(title, limit=LIMIT):
    """修正前的寫法，只用來當負向對照：證明本檔的斷言真的抓得到那個 bug。"""
    return html_lib.escape(title)[:limit]


class TestNoDanglingNumber(unittest.TestCase):
    """截斷後不得以數字結尾——那正是會產生反義片段的形狀。"""

    REAL_TITLES = [
        # 本輪這篇。硬切會變成「…有人從第 1」＝與全文論點相反。
        "義大利人在蒙札等了 60 年：42 位車手、182 次起跑，然後今天有人從第 19 位贏了",
        # 站上既有的兩篇，硬切後同樣以數字收尾。
        "巴林大獎賽移師馬來西亞：一個賽季裡同名的站從 4 人變成 5 人的替補名單問題",
        "F1 中文譯名對照：同一個人有三種寫法、50/50 的機率你會挑到哪一種寫法",
        # ☠️ 本函式第一版漏掉的形狀：切點落在「數字」與「空白」之間。
        # 先退數字（尾端是空白 → 沒命中）再退空白，會把數字重新露到最後。
        # 站上真實標題：〈…7 條早了 17 分鐘以上、2 條發給從未…〉硬切後是「…以上、2 」。
        "藍旗系統故障：11 條藍旗，7 條早了 17 分鐘以上、2 條發給從未被套圈的車手",
    ]

    def test_digit_followed_by_space_at_cut(self):
        """切點正好在「數字＋空白」上時，數字一樣不得留下。

        這條是第一版的漏網形狀，單獨列出來釘住。
        """
        for t in ["字" * 36 + "、2 條發給某人",
                  "字" * 35 + "共 12 個項目在後面"]:
            with self.subTest(title=t[:12]):
                self.assertFalse(re.search(r"\d…$", ba._nav_title(t)),
                                 f"刪節號前仍留著半截數字：{ba._nav_title(t)!r}")

    def test_never_ends_with_digit(self):
        for t in self.REAL_TITLES:
            with self.subTest(title=t[:20]):
                out = ba._nav_title(t)
                self.assertFalse(re.search(r"\d$", out),
                                 f"截斷後以數字結尾，會被讀成完整數值：{out!r}")

    def test_negative_control_old_behaviour_fails(self):
        """負向對照：修正前的寫法在同一組標題上必須至少有一筆以數字結尾。

        缺這條的話，上面那個斷言可能根本沒守到任何東西。
        """
        bad = [t for t in self.REAL_TITLES if re.search(r"\d$", _old_behaviour(t))]
        self.assertTrue(bad, "負向對照失效：舊寫法沒有任何一筆以數字結尾，"
                             "代表這組樣本沒有覆蓋到要守的缺陷，請換樣本")


class TestTruncationIsVisible(unittest.TestCase):
    """被截斷就要看得出來。"""

    def test_long_title_gets_ellipsis(self):
        t = "義大利人在蒙札等了 60 年：42 位車手、182 次起跑，然後今天有人從第 19 位贏了"
        self.assertTrue(ba._nav_title(t).endswith("…"))

    def test_negative_control_old_had_no_ellipsis(self):
        t = "義大利人在蒙札等了 60 年：42 位車手、182 次起跑，然後今天有人從第 19 位贏了"
        self.assertFalse(_old_behaviour(t).endswith("…"),
                         "負向對照失效：舊寫法本來就有刪節號的話，這條斷言沒有守到東西")

    def test_no_trailing_punctuation_before_ellipsis(self):
        """退掉數字後不要留下孤立的頓號／逗號，例如「…車手、…」。"""
        t = "A" * 36 + "、12345"
        self.assertNotIn("、…", ba._nav_title(t))


class TestShortTitlesUntouched(unittest.TestCase):
    """不該被動到的就一個字都不要動——否則「全部截斷」也會通過上面的測試。"""

    def test_short_title_unchanged(self):
        for t in ["短標題", "F1 2026 賽季規則指南", "A" * LIMIT]:
            with self.subTest(title=t):
                self.assertEqual(ba._nav_title(t), t)

    def test_boundary_41_is_truncated(self):
        t = "字" * (LIMIT + 1)
        out = ba._nav_title(t)
        self.assertNotEqual(out, t)
        self.assertTrue(out.endswith("…"))


class TestEscapeHappensAfterTruncation(unittest.TestCase):
    """先切原文再 escape：切點落在實體中間不得產出壞標記。"""

    def test_entity_never_split(self):
        # 讓 `"` 剛好落在第 40 個字元附近；舊寫法 escape 成 &quot; 後會被切斷。
        t = "字" * 38 + '"引號"' + "字" * 20
        rendered = html_lib.escape(ba._nav_title(t))
        # 壞實體的形狀＝有 & 開頭卻沒有對應的 ;
        for m in re.finditer(r"&[a-zA-Z#0-9]*", rendered):
            frag = rendered[m.start():m.start() + 10]
            self.assertIn(";", frag, f"切出半截 HTML 實體：{frag!r}")

    def test_negative_control_old_splits_entity(self):
        t = "字" * 38 + '"引號"' + "字" * 20
        old = _old_behaviour(t)
        tail = old[old.rfind("&"):] if "&" in old else ""
        self.assertTrue(tail and ";" not in tail,
                        "負向對照失效：舊寫法在這個樣本上沒有切斷實體，請換樣本")


if __name__ == "__main__":
    unittest.main()
