#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""部署管線的守門測試：人工核准拿掉了，機械擋線一道都不准少。

## 由來（2026-08-03）

`racing-weekly.yml` 原本在 update job 綁 `environment: production`，每次部署都要人按核准。
實測五次排程觸發只成功一次（設定當天 Charlie 人在旁邊），其餘四次**連一個步驟都沒執行**——
開機、卡在等核准、沒人注意到、被下次手動觸發擠掉。這個站真實的更新節奏因此是
「剛好有人在弄它的時候才更新」，而不是每週一自動更新。

一道需要人按、而那個人不在的 gate，不是 gate，是一個關掉的開關。
它比亮紅的 gate 更難發現，因為它「成功」的外觀就是什麼都沒發生。

## 這裡釘兩件事，而且必須一起釘

1. **人工核准不准被加回來** —— 加回來的預期效果是排程再次全部靜默停擺。
   要加回來的人得先刪掉這條測試，那就會讀到上面的理由。
2. **機械擋線不准跟著消失** —— 這才是重點。拿掉人工核准的正當性，
   完全建立在「該擋的還有東西在擋」之上。哪天有人順手拔掉一道機械 gate，
   這個 workflow 就變成真的沒人看了。第 1 條單獨存在是危險的，
   它會讓「拿掉核准」看起來像一個已經完成、不必再管的決定。

跑法：python3 -m unittest discover -s tests -v
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "racing-weekly.yml"
UPDATER = ROOT / "scripts" / "update-racing.py"

# 部署前必須跑到的機械擋線（update-racing.py 的跑序裡要看得到這些腳本）
REQUIRED_GATES = (
    "check-site-facts.py",        # 跨頁事實一致性
    "build-sitemap.py",           # sitemap 合併（漏收即整區缺席）
)


class NoHumanApprovalGate(unittest.TestCase):
    """人工核准已於 2026-08-03 移除；理由見本檔 docstring 與 workflow 註解。"""

    def setUp(self):
        self.yml = WORKFLOW.read_text(encoding="utf-8")

    def test_update_job_has_no_environment_protection(self):
        # 只看非註解行——workflow 註解裡刻意保留「environment: production」這串字說明歷史
        live = [ln for ln in self.yml.splitlines() if not ln.lstrip().startswith("#")]
        offending = [ln for ln in live if re.match(r"\s*environment:", ln)]
        self.assertEqual(
            offending, [],
            "部署 job 又被綁上 environment 人工核准。\n"
            "      加回去之前請先看 racing-weekly.yml 的註解：上次這樣做的結果是\n"
            "      五次排程只成功一次、其餘四次連一個步驟都沒跑過。\n"
            "      人在合併前的圓桌 cross-check 看內容，不在部署那一刻按按鈕。")

    def test_rationale_is_recorded_next_to_the_decision(self):
        """理由必須留在 workflow 檔裡，不能只活在某次對話或 PR 描述。

        決定的理由跟決定放在不同地方，等於沒有理由——下一個讀這個檔的人只會看到
        「這裡沒有核准」，然後很合理地想把它加上。
        """
        self.assertIn("environment: production", self.yml,
                      "註解裡應保留這串字說明曾經有過人工核准與為何移除")
        self.assertIn("圓桌", self.yml, "應寫明人工審查移到合併前的圓桌 cross-check")


class MechanicalGatesStillWired(unittest.TestCase):
    """拿掉人工核准的正當性建立在機械擋線還在——所以這裡必須跟上面成對存在。"""

    def setUp(self):
        self.src = UPDATER.read_text(encoding="utf-8")

    def test_required_gates_are_called_before_deploy(self):
        """⚠️ 比對「真正的呼叫點」而不是字串首次出現的位置。

        第一版用 `src.find("wrangler")` 抓部署位置，結果抓到的是檔頭 docstring 裡
        描述部署的那一句（偏移 540），於是每一道 gate 都被判定成「跑在部署之後」。
        測試自己踩了它要抓的那類錯：拿一個看似合理的定位方式，卻沒驗過它指到哪裡。
        """
        deploy = re.search(r'run\(\s*\[\s*"npx",\s*"wrangler', self.src)
        self.assertIsNotNone(deploy, "前提壞了：找不到 wrangler deploy 的呼叫點")
        for gate in REQUIRED_GATES:
            call = re.search(r'script\(\s*"%s"' % re.escape(gate), self.src)
            self.assertIsNotNone(call, f"{gate} 不在跑序裡了")
            self.assertLess(call.start(), deploy.start(),
                            f"{gate} 跑在部署之後＝形同虛設")

    def test_failed_steps_block_deploy(self):
        """任何前置步驟失敗 → 禁止部署。這是拿掉人工核准後最後的硬擋線。"""
        self.assertRegex(self.src, r"if FAILED:[\s\S]{0,400}?禁止部署",
                         "hard gate（前置失敗即禁止部署）不見了")

    def test_workflow_runs_unit_tests_before_deploy(self):
        """同上：比對 `run:` 實際步驟，不是註解裡提到的檔名。"""
        yml = WORKFLOW.read_text(encoding="utf-8")
        t = re.search(r"run:\s*python -m unittest", yml)
        d = re.search(r"run:\s*python scripts/update-racing\.py", yml)
        self.assertIsNotNone(t, "workflow 不再跑 unit tests")
        self.assertIsNotNone(d, "前提壞了：找不到部署步驟")
        self.assertLess(t.start(), d.start(), "unit tests 跑在部署之後＝擋不到東西")


if __name__ == "__main__":
    unittest.main()
