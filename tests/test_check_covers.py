#!/usr/bin/env python3
"""check-covers.py（封面數字對帳 gate）的測試。

⚠️ 這份測試的重點是**反向**：證明 gate 真的會叫。
封面 gate 第一次跑就對五張封面全綠——那既可能是封面都對，也可能是 regex 寫壞了
什麼都掃不到，兩者從輸出看起來一模一樣。本站在 verify-sources 上已經吃過四次
「gate 太寬但全綠」（2026-07-30 一天內），所以這裡先釘住攔截點。

另一條紀律（本站 7/30 的教訓）：**驗 gate 要驗攔截點看得到的東西**。
所以下面測的是 `visible_text` 與 `appears` 這兩個實際做判斷的函式，
不是只跑一次 main() 看 exit code——那樣測在下游，零資訊還會誤報。
"""
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("checkcovers", ROOT / "scripts" / "check-covers.py")
cc = importlib.util.module_from_spec(_spec)
sys.modules["checkcovers"] = cc
_spec.loader.exec_module(cc)


class TestVisibleText(unittest.TestCase):
    def test_attribute_numbers_are_not_scanned(self):
        """屬性裡的數字不算可見文字。

        座標（left:11.858%）、viewBox、flex:15 全是排版參數，掃進來就是假警報，
        而假警報的代價是這道檢查被習慣性忽略。
        """
        text = cc.visible_text(
            '<svg viewBox="0 0 2140 340"><circle cx="253.8" cy="54" r="9"/></svg>'
            '<div style="flex:15;left:11.858%">諾里斯 34 圈</div>')
        self.assertEqual(set(cc.NUM.findall(text)), {"34"})

    def test_style_block_numbers_are_not_scanned(self):
        text = cc.visible_text('<style>h1{font-size:104px} .x{flex:25}</style><h1>11 條藍旗</h1>')
        self.assertEqual(set(cc.NUM.findall(text)), {"11"})

    def test_comment_numbers_are_not_scanned(self):
        text = cc.visible_text('<!-- 起跑 15:03:16 為推算值 --><p>格旗 16:43</p>')
        self.assertEqual(set(cc.NUM.findall(text)), {"16:43"})

    def test_visible_numbers_are_scanned(self):
        """正向：該掃到的要掃到，含時刻與成績格式。"""
        text = cc.visible_text('<p>15:36:56 與 1:39:56.180 以及 0.001 秒</p>')
        self.assertEqual(set(cc.NUM.findall(text)), {"15:36:56", "1:39:56.180", "0.001"})


class TestAppears(unittest.TestCase):
    def test_single_digit_not_satisfied_by_larger_number(self):
        """一位數不能被別的數字的一截滿足。

        少了邊界條件的話，`4` 會被正文裡任何一個 2026／400 滿足，
        等於這道 gate 對所有一位數失效——而封面上的大字幾乎都是一兩位數。
        """
        self.assertFalse(cc.appears("4", "2026 年賽季共 400 kW"))
        self.assertTrue(cc.appears("4", "共 4 位車手領跑過"))

    def test_timestamp_must_match_whole(self):
        self.assertFalse(cc.appears("15:36", "最後一條藍旗訊息是 15:36:56"))
        self.assertTrue(cc.appears("15:36:56", "最後一條藍旗訊息是 15:36:56"))

    def test_decimal_not_satisfied_by_prefix(self):
        self.assertFalse(cc.appears("22", "中位數 22.015 秒"))
        self.assertTrue(cc.appears("22.015", "中位數 22.015 秒"))

    def test_number_absent_is_absent(self):
        self.assertFalse(cc.appears("99", "全場 70 圈"))


class TestEndToEnd(unittest.TestCase):
    """跑真實 manifest：五張封面現況必須全過，且注入假數字必須被擋。"""

    def _entries(self):
        import json
        return json.loads((ROOT / "design" / "covers" / "covers.json")
                          .read_text(encoding="utf-8"))["covers"]

    def test_all_shipped_covers_pass(self):
        for e in self._entries():
            with self.subTest(slug=e["slug"]):
                self.assertTrue(cc.check_one(e))

    def test_injected_fake_number_is_caught(self):
        """把一個文章裡沒有的數字塞進封面副本，gate 必須擋下。

        這是整份測試的核心：沒有這一條，前面的全綠不構成任何保證。
        """
        import shutil
        import tempfile
        src = ROOT / "design" / "covers" / "cover-r11-report.html"
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d) / "cover-fake.html"
            html = src.read_text(encoding="utf-8").replace(
                "<span>領先易主次數</span>", "<span>領先易主 993 次</span>")
            tmp.write_text(html, encoding="utf-8")
            # check_one 從 COVER_DIR 取檔，所以把副本放進去再刪
            dst = cc.COVER_DIR / "cover-fake-for-test.html"
            shutil.copy2(tmp, dst)
            try:
                self.assertFalse(cc.check_one({
                    "slug": "f1-2026-r11-hungary-report",
                    "html": "cover-fake-for-test.html", "allow": {}}))
                # 而具名例外要能解除它——否則 allow 機制形同不存在
                self.assertTrue(cc.check_one({
                    "slug": "f1-2026-r11-hungary-report",
                    "html": "cover-fake-for-test.html",
                    "allow": {"993": "測試用具名例外"}}))
            finally:
                dst.unlink(missing_ok=True)

    def test_missing_article_fails(self):
        self.assertFalse(cc.check_one({
            "slug": "no-such-article", "html": "cover-r11-report.html", "allow": {}}))

    def test_missing_html_fails(self):
        self.assertFalse(cc.check_one({
            "slug": "f1-2026-r11-hungary-report", "html": "no-such-cover.html", "allow": {}}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
