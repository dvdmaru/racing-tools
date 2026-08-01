#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨頁事實一致性 gate 的回歸測試。

由來（2026-08-01）：巴林站移師雪邦讓 2026 從 22 站變 23 站，同一個事實散在四處，
其中最難抓的是規則指南那句「賽季剩下的 13 站」——**由舊總數推算**，
grep「22 站」掃不到。check-site-facts.py 就是為了這一類而存在。

這裡釘三件事：
1. 它抓得到過期的宣稱（正向）
2. 它**不會**把正確的敘述誤判成錯（v1 曾經 446 個假陽性，全是這種）
3. allow 與序數這兩個豁免通道**只在該豁免的時候豁免**（反向）

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sf = _load("check_site_facts", "check-site-facts.py")
CFG = json.loads((ROOT / "config" / "site-facts.json").read_text(encoding="utf-8"))
TRUTHS = {"season_races": 23, "season_sprints": 6, "season_races_remaining": 12}


def check(text):
    return sf.check_text(text, CFG, TRUTHS)


class DetectsStaleClaims(unittest.TestCase):
    """正向：過期的宣稱要抓得到。"""

    def test_catches_stale_total(self):
        self.assertTrue(check("賽季原公布 24 站，因中東情勢縮為 22 站；3 月墨爾本揭幕。"))

    def test_catches_stale_faq_answer(self):
        self.assertTrue(check("2026 F1 賽季共有幾站？ 22 站。其中 6 站為衝刺賽週末。"))

    def test_catches_derived_remaining(self):
        """這是整支腳本存在的理由：推算值 grep 不到。"""
        bad = check("賽季剩下的 13 站，就是這套新公式繼續交卷的過程。")
        self.assertTrue(bad)
        self.assertEqual(bad[0][0], "season_races_remaining")

    def test_catches_stale_sprint_count(self):
        self.assertTrue(check("其中 8 站為衝刺賽（sprint）週末。"))


class DoesNotFlagCorrectProse(unittest.TestCase):
    """反向：v1 用 default-deny 掃出 446 個命中，全是這一類正確敘述。

    一個滿是假陽性的 gate 比沒有 gate 更糟——沒人讀，最後被關掉。
    """

    def test_correct_total_passes(self):
        self.assertFalse(check("全季因此定為 23 站：3 月澳洲墨爾本揭幕。"))

    def test_ordinal_position_is_not_a_total(self):
        self.assertFalse(check("雪邦排在賽曆第 16 站（R16），前一站是亞塞拜然大獎賽。"))

    def test_progress_counts_are_not_totals(self):
        for s in ("規則寫在紙上是一回事，跑了 9 站之後，上半季給出三個答案。",
                  "前 9 站賓士拿下 7 勝。",
                  "適用更低能量上限的場次由 8 站增為 12 站。",
                  "已完賽 11 站標為深色。"):
            self.assertFalse(check(s), f"誤判：{s}")

    def test_historical_original_count_is_not_current(self):
        """「原公布 24 站」是歷史事實，三處敘述都拿它當對照起點。"""
        self.assertFalse(check("2026 年賽曆原公布 24 站。"))


class ExemptionsAreNarrow(unittest.TestCase):
    """反向：豁免通道只在該豁免時豁免，不能變成掩蓋器。"""

    def test_allow_covers_the_quoted_report(self):
        quoted = ("2026 年 3 月，巴林站與沙烏地站被宣布不在原定的 4 月舉行。"
                  "Sky Sports 當時用的是「取消」（cancellation），寫賽曆因此縮減為 22 站。")
        self.assertFalse(check(quoted), "引述他人當時說法不該被判為本站宣稱現況")

    def test_allow_does_not_swallow_our_own_stale_claim(self):
        """同樣寫「縮減為 22 站」，但沒有那段引述脈絡時必須照抓。"""
        ours = "巴林站與沙烏地站取消後，賽曆縮減為 22 站。"
        self.assertTrue(check(ours), "allow 變成掩蓋器了")

    def test_allow_patterns_all_carry_a_reason(self):
        for a in CFG.get("allow", []):
            self.assertTrue(a.get("reason", "").strip(), f"allow 少了理由：{a['pattern']}")

    def test_exclusions_all_carry_a_reason(self):
        for e in CFG["scan"].get("exclude", []):
            self.assertTrue(e.get("reason", "").strip(), f"exclude 少了理由：{e['pattern']}")


class CompletedRoundCounting(unittest.TestCase):
    """☠️ 這支腳本自己踩過的坑：推算值的來源算錯。

    `compute_truths` 原本用 glob("round-*.json") 數已完賽站數，
    把 round-02-sprint / round-10-laps / round-10-pitstops 一起數了進去——
    19 個檔被當成 19 站跑完，剩餘站數算成 4（實際 12）。
    **抓推算值出錯的工具，自己的推算值先錯了。**
    """

    def test_only_plain_round_files_count_as_completed(self):
        res = ROOT / "data" / "2026" / "results"
        if not res.exists():
            self.skipTest("無 2026 賽果快照")
        plain = {f.name for f in res.glob("round-[0-9][0-9].json")}
        allf = {f.name for f in res.glob("round-*.json")}
        self.assertTrue(allf - plain, "前提壞了：快照裡應該有 sprint/laps/pitstops 這類附檔")
        for name in allf - plain:
            self.assertNotIn(name, plain)

    def test_truth_matches_plain_round_files(self):
        res = ROOT / "data" / "2026" / "results"
        if not res.exists():
            self.skipTest("無 2026 賽果快照")
        sched = json.loads(
            (ROOT / "data" / "2026" / "schedule.json").read_text(encoding="utf-8"))["races"]
        t = sf.compute_truths(2026)
        self.assertEqual(t["season_races"], len(sched))
        self.assertEqual(
            t["season_races_remaining"],
            len(sched) - len(list(res.glob("round-[0-9][0-9].json"))))


class QuoteZonesAreNarrow(unittest.TestCase):
    """引用區：勘誤區塊的職責就是引用原本錯的寫法，那些數字出現在頁面上是正確的。

    由來（2026-08-01）：修好規則指南後 gate 反而紅了，因為勘誤區塊寫著
    「原文寫…縮為 22 站」「文末『剩下的 13 站』」。
    ⚠️ 正確修法是**整段當引用區排除**，不是用 allow 逐條豁免——
    每次勘誤都要新增一條的話，例外清單遲早變成掩蓋器。
    """

    ERRATA = ('<ul class="rs-list rs-err">'
              '<li>原文寫「賽季縮為 22 站」，實際為 23 站。</li></ul>')

    def _strip(self, raw):
        cfg = CFG
        out = raw
        for qz in cfg.get("quote_zones", []):
            out = re.sub(qz["pattern"], " ", out, flags=re.S)
        return out

    def test_errata_block_is_stripped(self):
        self.assertFalse(check(self._strip(self.ERRATA)))

    def test_same_wrong_number_outside_errata_is_still_caught(self):
        """反向：引用區之外的同一句話必須照抓，否則排除範圍寫太寬。"""
        page = self.ERRATA + "<p>2026 賽季因此縮為 22 站。</p>"
        self.assertTrue(check(self._strip(page)), "引用區排除得太寬，把正文也蓋掉了")

    def test_quote_zones_all_carry_a_reason(self):
        for qz in CFG.get("quote_zones", []):
            self.assertTrue(qz.get("reason", "").strip(), f"quote_zone 少了理由：{qz['pattern']}")


class ApprovedArticlesAreStillApproved(unittest.TestCase):
    """已核准文章被改動卻沒重新核准 → 這裡要紅。

    由來（2026-08-01）：修規則指南的過期站數時發現一個沒人守的缺口——
    改了已核准文章而忘記更新 `approved.json`，build 只會印一行
    「approval invalidated (article_sha256 mismatch)」然後**把整篇文章下架**。
    網站少一篇文章比多一個錯字嚴重，而那一行訊息淹在建置日誌裡沒人看。

    所以把它變成機械擋線：sha 對不上就讓測試紅，PR 合不進去。
    **這條測試紅掉時不要去改測試**——正確做法是請 Charlie 看過改動後的文章，
    再把新的 sha256 寫進 `config/approved.json`（核准者不得與產稿者相同）。
    """

    def test_every_approved_article_matches_its_recorded_sha(self):
        import hashlib
        approved = json.loads(
            (ROOT / "config" / "approved.json").read_text(encoding="utf-8"))["approved"]
        drifted = []
        for e in approved:
            p = ROOT / "articles" / e["slug"] / "index.md"
            if not p.exists():
                continue  # 賽季導言等非 articles/ 型內容，另有測試把關
            actual = hashlib.sha256(p.read_bytes()).hexdigest()
            if actual != e["article_sha256"]:
                drifted.append(f"{e['slug']}\n        記錄 {e['article_sha256']}\n        實際 {actual}")
        self.assertEqual(
            drifted, [],
            "已核准文章被改過但沒重新核准，build 會把它們整篇下架：\n      " + "\n      ".join(drifted))


if __name__ == "__main__":
    unittest.main()
