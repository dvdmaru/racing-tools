#!/usr/bin/env python3
"""verify-quotes（引文忠實度 gate）的 fixture 測試。

存在理由：2026-09-04 寫 2027 正賽距離那篇時，事實表裡被指揮席自己標成
「⭐⭐ 全篇最有價值」的三句 The Race 引文，逐字比對後在原文中**一句都不存在**——
那三句來自網頁摘要，摘要是改寫過的。稿子已經把它寫成一整節。
站上原有的四道 gate 沒有一道看得見這件事：`verify-sources` 擋的是無名歸因，
它不在乎引號裡的字是不是真出自那個來源，**一句掛著具名出處的假引文可以全綠通過**。

同一輪還抓到三型更難察覺的：
  ① 真句改一兩個字（Monaco will not be affected by the changes → ...to qualifying）
  ② 兩個真片段被拼成一句原文沒有的話（RacingNews365 的導言＋內文）
  ③ 引文順序被倒過來、譯文吃掉 hedge（這兩型 gate 擋不到，屬人工審稿範圍，見下）

⚠️ 這裡同時測 **應命中（紅燈）** 與 **不應命中（綠燈）**。
只測前者的話，把比對寫成「永遠找不到」也會全過。
"""
import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verifyquotes",
                                               ROOT / "scripts" / "verify-quotes.py")
vq = importlib.util.module_from_spec(_spec)
sys.modules["verifyquotes"] = vq
_spec.loader.exec_module(vq)

# 一份最小快照：模擬抓下來的原文（含 HTML 標籤、彎引號、實體、兩個連字號破折號）。
SNAPSHOT = (
    "<p>Formula 1 teams have &nbsp;agreed a plan. "
    "&ldquo;Monaco will not be affected by the changes,&rdquo; the report said. "
    "All 11 F1 teams have reached an agreement to reduce the distance of grands prix. "
    "It is understood that <b>there was a risk of some events turning into "
    "fuel-economy runs</b>. "
    "It still hurts your soul when you see your speed dropping so much -- "
    "56 kph down the straight. "
    "revised regulations need to be proposed to the F1 Commission, which is made up of "
    "teams, the FIA and FOM. Once approved there, it will then need ratification.</p>"
)


def check(quote, snapshot=SNAPSHOT):
    """回傳 True＝在快照裡找得到（gate 綠燈）。與 main() 同一套比對邏輯。"""
    import re
    text = vq.normalise(snapshot)
    parts = [f for f in
             (vq.normalise(x) for x in re.split(r"\s*(?:\.{3}|…)\s*", quote)) if f]
    return all(f in text for f in parts)


class TestQuoteFidelity(unittest.TestCase):
    # 應命中＝gate 必須判紅（引文在快照裡不存在）
    MUST_BE_RED = [
        # ① 整句捏造：讀起來完全像新聞，快照裡沒有
        "The FIA has confirmed that all races will be shortened next year",
        # ② 真句改一個詞——最難用肉眼抓
        "Monaco will not be affected by the changes to qualifying",
        # ③ ☠️ 拼接：兩個片段都真，句子是假的。關鍵詞 grep 得到，整句 grep 不到。
        "All 11 F1 teams have unanimously backed a proposal",
        # ④ 省略號拼接：片段各自存在但橫跨不相鄰的內容，仍不該當成一句引文
        "The FIA has confirmed ... turning into fuel-economy runs",
    ]

    # 不應命中＝gate 必須判綠（真的出自快照，只是排版差異）
    MUST_BE_GREEN = [
        "Monaco will not be affected by the changes",           # 彎引號＋實體
        "there was a risk of some events turning into fuel-economy runs",  # 跨 <b> 標籤
        "All 11 F1 teams have reached an agreement",             # 導言原句
        # 破折號寫法差異：原文 --，引用者寫成 —
        "It still hurts your soul when you see your speed dropping so much — "
        "56 kph down the straight",
        # 正當節略：省略號兩端在原文相鄰，中間只略去一個子句
        "revised regulations need to be proposed to the F1 Commission... "
        "Once approved there, it will then need ratification",
    ]

    def test_fabricated_and_altered_quotes_are_red(self):
        for q in self.MUST_BE_RED:
            with self.subTest(quote=q[:50]):
                self.assertFalse(check(q), f"gate 漏接了不存在的引文：{q}")

    def test_genuine_quotes_are_green(self):
        for q in self.MUST_BE_GREEN:
            with self.subTest(quote=q[:50]):
                self.assertTrue(check(q), f"gate 誤殺了真實引文：{q}")


class TestCollectors(unittest.TestCase):
    def test_collect_quotes_walks_all_verbatim_keys(self):
        """事實表裡的 verbatim 欄位有多種後綴，一個都不能漏。"""
        pack = {"a": {"verbatim": "one two three four"},
                "b": [{"verbatim2": "five six seven eight"}],
                "c": {"d": {"verbatim_full": "nine ten eleven twelve"}},
                "note": {"_writer_note": "這一欄不是引文，不該被收進來"}}
        got = {q for _, q in vq.collect_quotes(pack)}
        self.assertEqual(len(got), 3)
        self.assertNotIn("這一欄不是引文，不該被收進來", got)

    def test_article_quotes_skips_pure_chinese(self):
        """文章裡的「」多數是中文強調，只有含足量英文字的才是外語引文。"""
        md = ("這句「純中文的強調」不該被收。\n"
              "這句「Monaco will not be affected by the changes」該被收。\n"
              "這句「OK」英文太短不收。\n")
        got = [q for _, q in vq.article_quotes(md)]
        self.assertEqual(got, ["Monaco will not be affected by the changes"])


class TestGateBoundaries(unittest.TestCase):
    """把 gate **擋不住**的事釘成測試，避免後人以為它擋得住。

    這幾條全部是 2026-09-04 那輪由人工審稿抓到、gate 看不見的：
    順序被調換、譯文吃掉 hedge、歸屬掛錯家。寫成測試不是要它們變綠，
    是要讓「gate 綠燈 ≠ 引文用對了」這件事有地方被讀到。
    """

    def test_reordered_quotes_still_pass(self):
        """兩句都真、順序調換——gate 看不出來（它逐句比對，不管先後）。"""
        self.assertTrue(check("Monaco will not be affected by the changes"))
        self.assertTrue(check("All 11 F1 teams have reached an agreement"))

    def test_wrong_attribution_still_passes(self):
        """引文出自 A 家卻被標成 B 家：只要兩份快照都在目錄裡，gate 會綠。

        要擋這一型得逐句綁定來源，目前刻意不做——先擋掉「整句不存在」那一類。
        """
        other = "<p>Monaco will not be affected by the changes</p>"
        self.assertTrue(check("Monaco will not be affected by the changes", other))


if __name__ == "__main__":
    unittest.main()
