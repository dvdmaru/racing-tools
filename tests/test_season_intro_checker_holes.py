#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-season-intros.py v2：SOL-VERDICT-5 四個結構性漏洞的回歸測試。

每個漏洞一組**陽性（會抓）＋陰性（不誤抓）**，fixture 用三個真案例：

  H1 oracle 循環引用 → 1976（L0 raw 66／64 vs 逐站重算 69／68）
  H2 driver 欄位未綁定 → 1958（champion_points 42 掛到 moss 身上）
  H3 正文數字只做值集合成員檢查 → 「F1 的 1」＋2016 的 385／380 對調
  H4 並列順位未驗 → 2007（Hamilton／Alonso 同 109 分，countback 分出 P2／P3）

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import pathlib
import shutil
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "seasons"


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


chk = _load("check_season_intros_holes", "check-season-intros.py")


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(chk.DB_PATH)
        self.addCleanup(self.con.close)

    def _forked_db(self, statements):
        """複製 db.sqlite 到 temp 後套用 UPDATE，回新 connection（模擬 L0／竄改資料）。"""
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        target = tmp / "db.sqlite"
        shutil.copy2(chk.DB_PATH, target)
        con = sqlite3.connect(target)
        for sql, args in statements:
            con.execute(sql, args)
        con.commit()
        self.addCleanup(con.close)
        return con

    def _claim(self, season, **kw):
        return {"_season": season, "verified": True, **kw}


# ---------------------------------------------------------------- H1
class Hole1OracleCircularity(_DbCase):
    """H1：對帳器不能只回讀 standings；1976 的 66／64 必須被逐站重算與 L1 斷言打臉。"""

    L0_1976 = [("UPDATE driver_standings SET points=66 WHERE season=1976 AND driver_id='hunt'", ()),
               ("UPDATE driver_standings SET points=64 WHERE season=1976 AND driver_id='lauda'", ())]

    def test_positive_l0_value_fails_recompute(self):
        """陽性：standings 被退回 L0 的 66，claim 也寫 66（v1 的自我印證）→ v2 抓到。"""
        con = self._forked_db(self.L0_1976)
        ok, actual, detail = chk.verify_claim(
            con, self._claim(1976, kind="champion_points", driver="hunt", value=66))
        self.assertFalse(ok, "L0 的 66 與逐站重算 69 不符，不該放行")
        self.assertIn("重算", detail)
        self.assertEqual(actual["recomputed"], 69)

    def test_positive_l1_assertion_detects_l0_database(self):
        """陽性：db 讀到的是 L0 raw 值 → L1 斷言直接判錯（有人把 checker 指回 raw 就會咬）。"""
        con = self._forked_db(self.L0_1976)
        errors, _applied = chk.check_l1_applied(con, 1976)
        self.assertTrue(errors)
        self.assertTrue(any("L0 raw" in e for e in errors), errors)

    def test_positive_external_snapshot_without_override_blocks(self):
        """陽性：拿掉裁決覆寫後，維基快照的 69 與 jolpica 的 66 對不上 → 判錯。"""
        con = self._forked_db(self.L0_1976)
        original = chk._approved_overrides
        chk._approved_overrides = lambda season: []
        self.addCleanup(lambda: setattr(chk, "_approved_overrides", original))
        errors = chk.check_external_corroboration(
            1976, [self._claim(1976, kind="champion_points", driver="hunt", value=66)])
        self.assertTrue(any("外部快照不符" in e for e in errors), errors)
        # 同一組條件下 L1 斷言也不再叫（沒有裁決可斷言），確認兩條腿是獨立的
        self.assertEqual(chk.check_l1_applied(con, 1976)[0], [])

    def test_negative_l1_value_passes_all_three_legs(self):
        """陰性：真 db（L1＝69／68）三條腿都過，不誤抓。"""
        ok, actual, _ = chk.verify_claim(
            self.con, self._claim(1976, kind="champion_points", driver="hunt", value=69))
        self.assertTrue(ok)
        self.assertEqual(actual["recomputed"], 69)
        self.assertEqual(chk.check_l1_applied(self.con, 1976)[0], [])
        self.assertEqual(chk.check_external_corroboration(
            1976, [self._claim(1976, kind="champion_points", driver="hunt", value=69)]), [])

    def test_negative_dropped_score_season_not_falsely_flagged(self):
        """陰性：捨分季（1958 best-6）逐站加總 49≠標準 42，但套捨分規則後相符——不得誤抓。"""
        ok, actual, detail = chk.verify_claim(
            self.con, self._claim(1958, kind="champion_points", driver="hawthorn", value=42))
        self.assertTrue(ok, f"1958 捨分季不該被誤判：{detail}／{actual}")
        raw_sum = self.con.execute(
            "SELECT SUM(points) FROM results WHERE season=1958 AND driver_id='hawthorn'").fetchone()[0]
        self.assertNotEqual(raw_sum, 42, "這條測試的前提是純加總確實不等於官方分")


# ---------------------------------------------------------------- H2
class Hole2EntityBinding(_DbCase):
    """H2：值查詢一定要綁到 pack 宣稱的實體。"""

    def test_positive_missing_driver_blocks(self):
        ok, _actual, detail = chk.verify_claim(
            self.con, self._claim(1958, kind="champion_points", value=42))
        self.assertFalse(ok, "沒寫 driver 就不該通過（v1 是有寫才驗＝預設不驗）")
        self.assertIn("driver", detail)

    def test_positive_wrong_driver_blocks(self):
        ok, _actual, detail = chk.verify_claim(
            self.con, self._claim(1958, kind="champion_points", driver="moss", value=42))
        self.assertFalse(ok)
        self.assertIn("hawthorn", detail)

    def test_positive_missing_constructor_blocks(self):
        ok, _actual, detail = chk.verify_claim(
            self.con, self._claim(1950, kind="constructor_wins", value=6))
        self.assertFalse(ok)
        self.assertIn("constructor", detail)

    def test_negative_correct_entity_passes(self):
        for claim in (self._claim(1958, kind="champion_points", driver="hawthorn", value=42),
                      self._claim(1958, kind="runner_up_points", driver="moss", value=41),
                      self._claim(1950, kind="constructor_wins", constructor="alfa", value=6)):
            ok, actual, detail = chk.verify_claim(self.con, claim)
            self.assertTrue(ok, f"{claim['kind']} 不該被誤抓：{detail}／{actual}")


# ---------------------------------------------------------------- H3
class Hole3PositionalBinding(_DbCase):
    """H3：正文數字要綁到出現位置，不是只查值集合。"""

    def _check_text(self, year, text, pack):
        verified = [{**c, "_season": year} for c in pack.get("claims", []) if c.get("verified")]
        oracle = chk.SeasonOracle(self.con, year)
        ok_claims = [c for c in verified if chk.verify_claim(self.con, c, oracle)[0]]
        return chk.check_bindings(year, text, verified, ok_claims, pack)

    def test_positive_digit_inside_alnum_token_blocks(self):
        """陽性：「F1 的 1」——v1 只要有任何 claim 值＝1 就放行；v2 要求具名。"""
        pack = {"claims": [{"kind": "champion_wins", "driver": "hawthorn", "value": 1,
                            "verified": True, "anchors": ["贏下 1 場"]}]}
        errors = self._check_text(1958, "霍索恩全季贏下 1 場，F1 的規則當年還在調整。", pack)
        self.assertTrue(any("F1" in e for e in errors), errors)

    def test_negative_named_token_passes(self):
        """陰性：把 F1 具名列進 non_statistical_tokens 就不再誤抓（具名例外，不是靜默放行）。"""
        pack = {"claims": [{"kind": "champion_wins", "driver": "hawthorn", "value": 1,
                            "verified": True, "anchors": ["贏下 1 場"]}],
                "non_statistical_tokens": ["F1"]}
        errors = self._check_text(1958, "霍索恩全季贏下 1 場，F1 的規則當年還在調整。", pack)
        self.assertEqual(errors, [], errors)

    def test_positive_swapped_numbers_blocks(self):
        """陽性：2016 把 385／380 對調——兩個值都還在值集合裡，v1 全綠；v2 因 anchor 失聯而抓到。"""
        pack = json.loads((CONTENT / "2016.facts.json").read_text(encoding="utf-8"))
        text = (CONTENT / "2016.md").read_text(encoding="utf-8")
        swapped = text.replace("以 385 分對 380 分", "以 380 分對 385 分")
        self.assertNotEqual(swapped, text, "fixture 前提：正文確實有這段")
        errors = self._check_text(2016, swapped, pack)
        self.assertTrue(errors, "數字對調必須被抓到")
        self.assertTrue(any("anchor 在正文找不到" in e or "沒有任何 claim" in e for e in errors), errors)

    def test_positive_swapped_numbers_with_updated_anchors_still_blocks(self):
        """陽性（更狠）：連 anchor 一起搬過去——anchor 都找得到了，仍要靠「值 vs 綁定位置」抓。

        沒有這條，前一條測的只是「anchor 失聯」，證明不了位置綁定本身會咬。
        """
        pack = json.loads((CONTENT / "2016.facts.json").read_text(encoding="utf-8"))
        text = (CONTENT / "2016.md").read_text(encoding="utf-8").replace(
            "以 385 分對 380 分", "以 380 分對 385 分")
        for claim in pack["claims"]:
            if claim.get("kind") == "champion_points":
                claim["anchors"] = ["以 380 分"]      # 冠軍分被綁到 380 那個位置
            if claim.get("kind") == "runner_up_points":
                claim["anchors"] = ["對 385 分"]
        errors = self._check_text(2016, text, pack)
        self.assertTrue(any("綁到值為" in e for e in errors), errors)

    def test_negative_real_2016_intro_passes(self):
        pack = json.loads((CONTENT / "2016.facts.json").read_text(encoding="utf-8"))
        text = (CONTENT / "2016.md").read_text(encoding="utf-8")
        self.assertEqual(self._check_text(2016, text, pack), [])

    def test_positive_unbound_ordinal_blocks(self):
        """陽性：正文冒出沒有 claim 撐的順位詞（第四名）→ 抓。"""
        pack = json.loads((CONTENT / "2016.facts.json").read_text(encoding="utf-8"))
        text = (CONTENT / "2016.md").read_text(encoding="utf-8").replace(
            "漢米爾頓分站勝場較多", "漢米爾頓在收官站只拿到第四名")
        errors = self._check_text(2016, text, pack)
        self.assertTrue(any("順位詞" in e for e in errors), errors)

    def test_negative_all_sixteen_intros_pass(self):
        """陰性：16 篇已核准導言在 v2 下仍全綠（新 gate 不是靠翻紅來證明自己有用）。"""
        red = {}
        for path in sorted(CONTENT.glob("*.md")):
            if not path.stem.isdigit():
                continue
            errs = chk.check_year(int(path.stem), self.con)
            if errs:
                red[path.stem] = errs
        self.assertEqual(red, {}, red)


# ---------------------------------------------------------------- H4
class Hole4TiedPositions(_DbCase):
    """H4：同分時「並列」與「循序＋countback」是兩種不同事實，必須各自可驗。"""

    def test_positive_false_tie_claim_blocks(self):
        """陽性：2007 宣稱 Hamilton／Alonso 並列第二 → 正式順位是 2／3，判錯。"""
        ok, actual, detail = chk.verify_claim(self.con, self._claim(
            2007, kind="tied_position", drivers=["hamilton", "alonso"], value=2))
        self.assertFalse(ok)
        self.assertIn("並列", detail)
        self.assertEqual(actual, {"hamilton": 2, "alonso": 3})

    def test_positive_tie_wording_without_tie_claim_blocks(self):
        """陽性：正文寫「並列第二」但 pack 沒有 tied_position → 順位詞綁不到，判錯。"""
        pack = json.loads((CONTENT / "2007.facts.json").read_text(encoding="utf-8"))
        text = (CONTENT / "2007.md").read_text(encoding="utf-8").replace(
            "同分比較下漢米爾頓列第二、阿隆索第三", "兩人並列第二")
        verified = [{**c, "_season": 2007} for c in pack["claims"] if c.get("verified")]
        oracle = chk.SeasonOracle(self.con, 2007)
        ok_claims = [c for c in verified if chk.verify_claim(self.con, c, oracle)[0]]
        errors = chk.check_bindings(2007, text, verified, ok_claims, pack)
        self.assertTrue(any("並列第二" in e for e in errors), errors)

    def test_positive_reversed_countback_order_blocks(self):
        """陽性：把 countback 順序寫反（Alonso 在前）→ 重算打臉。"""
        ok, _actual, detail = chk.verify_claim(self.con, self._claim(
            2007, kind="countback_order", drivers=["alonso", "hamilton"], value=2))
        self.assertFalse(ok)
        self.assertIn("順位", detail)

    def test_negative_true_countback_order_passes(self):
        ok, actual, _detail = chk.verify_claim(self.con, self._claim(
            2007, kind="countback_order", drivers=["hamilton", "alonso"], value=2))
        self.assertTrue(ok)
        self.assertEqual(actual, {"hamilton": 2, "alonso": 3})

    def test_negative_countback_evidence_is_independent(self):
        """陰性佐證：countback 不是抄 standings，是從 results 的完賽名次分布重算出來的。"""
        oracle = chk.SeasonOracle(self.con, 2007)
        self.assertTrue(oracle.countback_beats("hamilton", "alonso"))
        self.assertEqual(oracle.finishes["hamilton"][2], 5)
        self.assertEqual(oracle.finishes["alonso"][2], 4)

    def test_negative_real_tie_passes(self):
        """陰性：2021 末站前兩人真的同分 → tied_before_final 通過，不因新 gate 誤抓。"""
        ok, actual, detail = chk.verify_claim(self.con, self._claim(
            2021, kind="tied_before_final", drivers=["max_verstappen", "hamilton"], value=369.5))
        self.assertTrue(ok, f"{detail}／{actual}")


# ---------------------------------------------------------------- 其他不回退保證
class InProgressSeasonGuard(_DbCase):
    """衍生統計紀律：「榜首＝冠軍」類 claim 在賽季跑完前不成立（2026 進行中）。"""

    def test_positive_champion_claim_on_running_season_blocks(self):
        self.assertFalse(chk.SeasonOracle(self.con, 2026).complete, "fixture 前提：2026 尚未跑完")
        ok, _actual, detail = chk.verify_claim(self.con, self._claim(
            2026, kind="champion_points", driver="max_verstappen", value=1))
        self.assertFalse(ok)
        self.assertIn("尚未跑完", detail)

    def test_negative_finished_season_unaffected(self):
        self.assertTrue(chk.SeasonOracle(self.con, 2002).complete)
        ok, _actual, detail = chk.verify_claim(self.con, self._claim(
            2002, kind="champion_points", driver="michael_schumacher", value=144))
        self.assertTrue(ok, detail)


class ClinchIsScoringRuleAware(_DbCase):
    """clinch 改成捨分規則＋只計實際仍有出賽的對手；2002 的既有數值不得漂移。"""

    def test_2002_clinch_unchanged(self):
        oracle = chk.SeasonOracle(self.con, 2002)
        self.assertEqual(oracle.clinch("michael_schumacher"), (11, 6))

    def test_1961_clinch_from_end_is_second_to_last(self):
        oracle = chk.SeasonOracle(self.con, 1961)
        rnd, remaining = oracle.clinch("phil_hill")
        self.assertEqual((rnd, remaining), (7, 1))
        self.assertEqual(oracle.last_round - rnd + 1, 2)


if __name__ == "__main__":
    unittest.main()
