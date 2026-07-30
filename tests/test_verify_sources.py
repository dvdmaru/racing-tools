#!/usr/bin/env python3
"""verify-sources（外部來源文 gate）的 fixture 測試。

存在理由：這道 gate 在 2026-07-30 一天之內被抓到三次「太寬」——
  ① 對已上線的規則指南全綠，但那篇實際有兩處無名歸因（作者席自查）
  ② 藍旗故障稿是靠 regex 漏接通過的（「有媒體」「有報導」「會有人問」都沒抓到）
  ③ 查核桌第十七戰審稿席實測，再回報八種常見句型 MISS
每一次的正解都是「補 regex＋補測試」，不是放寬。沒有測試的話，
regex 會在下一次有人覺得誤殺時被默默改鬆，而且沒人會發現。

⚠️ 這裡同時測 **應命中** 與 **不應命中**。只測前者的話，
把 pattern 寫成 `.` 也會全過（比照 no_causal 的反向測試教訓）。
"""
import importlib.util
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("checkfacts", ROOT / "scripts" / "check-facts.py")
cf = importlib.util.module_from_spec(_spec)
sys.modules["checkfacts"] = cf
_spec.loader.exec_module(cf)


def hits(text):
    return [p for p in cf.VAGUE_ATTRIBUTION if re.search(p, text)]


class TestVagueAttribution(unittest.TestCase):
    # 應命中：全部是「看起來有出處、實際無法追查」的句型
    MUST_HIT = [
        "專家認為這套系統很脆弱",
        "業界人士指出問題出在通訊層",
        "有分析認為這是史上首見",
        "據了解，罰則已經送出",
        "外界普遍認為這是系統問題",
        "甚至有一種說法是這是史上第一次",          # 規則指南實際命中
        "改動規模被普遍拿來與 2014 年相比",         # 規則指南實際命中
        "有媒體明白寫了他們向 FIA 詢問",            # 藍旗稿實際命中
        "另有轉播評論提到 GPS 追蹤中斷",            # 藍旗稿實際命中
        "會有人問是不是攻擊",                       # 藍旗稿實際命中
        "傳聞稱系統早就有問題",                     # 第十七戰回報 MISS
        "知情人士透露判罰另有內情",                 # 第十七戰回報 MISS
        "多家媒體指出賽會已經介入",                 # 第十七戰回報 MISS
        "媒體稱該系統當日全程失效",                 # 第十七戰回報 MISS
        "報導稱停用發生在第九圈",                   # 第十七戰回報 MISS
        "據報該功能已恢復",                         # 第十七戰回報 MISS
        "市場認為這會影響轉播權價格",               # 第十七戰回報 MISS
        "消息人士指出調查已經啟動",
        "據消息人士稱判罰另有內情",                 # R2 指出仍漏接「稱」
    ]

    # 不應命中：否定句、具名歸因、以及本站明示為推論的寫法
    MUST_NOT_HIT = [
        "到現在還沒有人說明的事",                   # 否定句，意思與無名歸因相反
        "未有人指出這個問題",
        "無人說明技術根因",
        "FIA 沒有就此發表任何說明",
        "Formula1.com 的說明是系統被停用",
        "貝爾曼賽後表示當天狀況很糟",
        "本站推論，信賴度中等",
        "據報告書記載，罰則為 5 秒",                # 「據報告」不是「據報」
        "賽事控制紀錄顯示最後一條藍旗在 15:36:56",
    ]

    def test_must_hit(self):
        for s in self.MUST_HIT:
            with self.subTest(s=s):
                self.assertTrue(hits(s), f"應被擋卻漏接：{s}")

    def test_must_not_hit(self):
        for s in self.MUST_NOT_HIT:
            with self.subTest(s=s):
                self.assertFalse(hits(s), f"誤殺：{s}（命中 {hits(s)}）")


class TestSourceSection(unittest.TestCase):
    """來源段落的三項存在性檢查。fail-closed：缺任何一項都不能過。"""

    def _run(self, body):
        """⚠️ 必須離開 with 區塊後才呼叫 gate——在區塊內呼叫時檔案尚未 flush，
        gate 讀到空檔案、回報「缺資料來源段落」，看起來像 gate 有 bug 實際是測試有 bug。
        （初版就這樣寫，害我先去懷疑 gate。）"""
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                         encoding="utf-8") as f:
            f.write("---\nslug: t\n---\n" + body)
            path = f.name
        return cf.verify_sources(path)

    def test_missing_section_fails(self):
        self.assertFalse(self._run("正文沒有來源段落。"))

    def test_missing_date_fails(self):
        self.assertFalse(self._run("## 資料來源\n[來源](https://example.com)\n"))

    def test_missing_link_fails(self):
        self.assertFalse(self._run("## 資料來源\n查證日 2026-07-30。\n"))

    def test_complete_passes(self):
        self.assertTrue(self._run("## 資料來源\n[來源](https://example.com)　查證日 2026-07-30。\n"))

    def _run_raw(self, full_text):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                         encoding="utf-8") as f:
            f.write(full_text)
            path = f.name
        return cf.verify_sources(path)

    SRC = "\n## 資料來源\n[來源](https://example.com)　查證日 2026-07-30。\n"

    def test_frontmatter_weasel_is_caught(self):
        """subtitle／lede 的無名歸因必須被擋。

        ⚠️ 這是 2026-07-30 發現的覆蓋缺口：原本掃描用 `_body_of()`，
        會把 frontmatter 整塊剝掉，於是 title／subtitle／lede 從來沒被任何語意 gate 掃過——
        而那三個欄位進 meta description、OG card、首頁摘錄與 RSS，比正文更多人看到。
        """
        for field in ("subtitle", "lede", "title"):
            with self.subTest(field=field):
                self.assertFalse(self._run_raw(
                    f'---\nslug: t\n{field}: "專家認為這套系統早就該換掉了。"\n---\n'
                    f"正文完全乾淨。{self.SRC}"))

    def test_machine_frontmatter_fields_not_scanned(self):
        """slug／date／type 是機器欄位，不該被語意 regex 掃到（避免誤殺）。"""
        self.assertTrue(self._run_raw(
            '---\nslug: has-people-said-something\ntype: "guide"\ndate: "2026-07-30"\n---\n'
            f"正文乾淨。{self.SRC}"))

    def test_known_gap_unrelated_link_still_passes(self):
        """⚠️ 已知覆蓋缺口，刻意用測試記錄下來，不要誤以為 gate 擋得住這個。

        一篇通篇無源因果、文末掛一個不相關 URL 的稿子**照樣會過**（第十七戰審稿席指出）。
        這是本 gate 的宣稱邊界：它只是格式 lint，取代不了人工 cross-check。
        若哪天真的實作了逐主張出處檢查，這個測試應該翻成 assertFalse。
        """
        self.assertTrue(self._run(
            "系統故障導致判罰失準，這顯然是架構問題。\n\n"
            "## 資料來源\n[不相關連結](https://example.com/cats)　查證日 2026-07-30。\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
