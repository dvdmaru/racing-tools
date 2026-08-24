#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-season-intros.py v3：導言第二批（2026-08-23 查核桌）暴露的三個缺口回歸測試。

每個缺口一組**陽性（會抓／改對）＋陰性（不誤抓／不漂移）**，fixture 全用真實賽季：

  H5 除名不建模        → 1997（舒馬克 78 分遭年度除名 position_text='D'，Frentzen 官方 P2 42 分）
  H6 clinch 事後之明   → 1978（Peterson R14 蒙札事故，舊口徑把 Andretti 封王算成 R13）
                         1961（von Trips R7 身亡，具名例外撐住 R7 不漂到 R8）
  H7 clinch 同分未套 countback → 1957（方吉歐 R6 德國站同分靠勝場封王）
                                 1988（Senna R15 鈴鹿同分靠第 8 勝封王，H7 的獨立佐證）

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import pathlib
import shutil
import sqlite3
import tempfile
import unittest
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


chk = _load("check_season_intros_h5_h7", "check-season-intros.py")
cc = _load("crosscheck_standings_for_h5_h7", "crosscheck-standings.py")


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(chk.DB_PATH)
        self.addCleanup(self.con.close)

    def _forked_db(self, statements):
        """複製 db.sqlite 到 temp 後套 UPDATE，回新 connection（模擬髒資料）。"""
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


# ---------------------------------------------------------------- H5
class Hole5DisqualificationNotModelled(_DbCase):
    """H5：年度除名要進重算 oracle，否則官方 P2 驗不過、被除名者反而佔著 P2。"""

    def test_positive_1997_runner_up_frentzen_now_verifies(self):
        """陽性：1997 官方 P2 Frentzen 42 分——舊 oracle 把 78 分的舒馬克排在 P2，這條驗不過。"""
        ok, actual, detail = chk.verify_claim(
            self.con, self._claim(1997, kind="runner_up_points", driver="frentzen", value=42))
        self.assertTrue(ok, f"1997 官方 P2 應該驗得過（{detail}＝{actual}）")
        self.assertEqual(actual["driver"], "frentzen")

    def test_positive_1997_driver_position_frentzen_is_p2(self):
        """陽性：driver_position frentzen=2 要過（重算順位須與官方一致）。"""
        ok, actual, _ = chk.verify_claim(
            self.con, self._claim(1997, kind="driver_position", driver="frentzen", value=2))
        self.assertTrue(ok)
        self.assertEqual(actual, 2)

    def test_positive_excluded_driver_has_no_season_rank(self):
        """陽性：被除名者不佔年度順位；宣稱他是第 2 直接判錯，且訊息要講清楚原因。"""
        oracle = chk.SeasonOracle(self.con, 1997)
        self.assertEqual(oracle.excluded, {"michael_schumacher"})
        self.assertIsNone(oracle.rank("michael_schumacher"))
        ok, _actual, detail = chk.verify_claim(
            self.con, self._claim(1997, kind="driver_position",
                                  driver="michael_schumacher", value=2))
        self.assertFalse(ok)
        self.assertIn("除名", detail)

    def test_positive_unknown_position_text_marker_is_rejected(self):
        """陽性（default-deny）：不認得的 position_text 標記不准默默當一般車手，整季判錯。"""
        con = self._forked_db([
            ("UPDATE driver_standings SET position_text='Z' "
             "WHERE season=2002 AND driver_id='michael_schumacher'", ())])
        errors = chk.check_year(2002, con)
        self.assertTrue(any("不認得的 position_text" in e for e in errors), errors)

    def test_negative_season_without_disqualification_ranks_unchanged(self):
        """陰性：沒有除名標記的賽季，排名與「未過濾」的重算逐鍵相同（過濾器必須是 no-op）。"""
        for year in (1996, 1998, 2002, 2019):
            oracle = chk.SeasonOracle(self.con, year)
            self.assertEqual(oracle.excluded, set(), f"{year} 不該有除名標記")
            unfiltered = cc._rank(oracle.points(), oracle.finishes)
            self.assertEqual(oracle.rank(), unfiltered, f"{year} 排名被 H5 過濾器改動了")

    def test_negative_disqualification_does_not_rewrite_mid_season_table(self):
        """陰性：除名是賽季後才發生的，末站前的即時累計榜不得把他抹掉（否則是另一種事後之明）。"""
        oracle = chk.SeasonOracle(self.con, 1997)
        through = oracle.rank_through(oracle.last_round - 1)
        self.assertEqual(through.get("michael_schumacher"), 1,
                         "1997 末站前舒馬克確實領先，即時累計榜不該剔除他")
        self.assertEqual(through.get("villeneuve"), 2)


# ---------------------------------------------------------------- H6
class Hole6ClinchHindsight(_DbCase):
    """H6：對手上限不准用「他之後實際沒再出賽」回推；只認「該站當下已確定退出」的具名例外。"""

    def test_positive_1978_r13_is_not_a_clinch(self):
        """陽性：R13 當下 Peterson 上限 78 ＞ Andretti 保底 63，舊口徑算出的 R13 必須被拒。"""
        oracle = chk.SeasonOracle(self.con, 1978)
        floor = oracle._segments(oracle.round_points["mario_andretti"], 13)
        rival = oracle._segments({**{r: v for r, v in oracle.round_points["peterson"].items() if r <= 13},
                                  **{f: oracle._ceiling() for f in (14, 15, 16)}})
        self.assertEqual((floor, rival), (63.0, 78.0))
        self.assertNotEqual(oracle.clinch("mario_andretti")[0], 13, "R13 是事後之明的產物")
        ok, _actual, _detail = chk.verify_claim(
            self.con, self._claim(1978, kind="clinch_round", driver="mario_andretti", value=13))
        self.assertFalse(ok, "clinch_round=13 是舊 oracle 的錯值，不該再被放行")

    def test_positive_1978_clinch_is_monza_r14(self):
        """陽性：Peterson 在 R14 蒙札事故後不再參賽，Andretti 保底 64 ＞ Lauda 上限 62 → R14。"""
        self.assertEqual(chk.SeasonOracle(self.con, 1978).clinch("mario_andretti"), (14, 2))

    def test_positive_named_exception_is_not_clairvoyant(self):
        """陽性（不得預知）：R6 時 von Trips 的 R7 事故還沒發生，R7／R8 都還要算進他的上限。"""
        oracle = chk.SeasonOracle(self.con, 1961)
        self.assertEqual(oracle._rival_future_rounds("trips", 6), [7, 8])
        self.assertEqual(oracle._rival_future_rounds("trips", 7), [])

    def test_positive_without_named_exception_clinch_falls_back_to_conservative(self):
        """陽性：拿掉具名例外後，1978 退回保守的 R15——不會退回事後之明的 R13。"""
        original = dict(chk.SEASON_ENDING_EVENTS)
        chk.SEASON_ENDING_EVENTS.pop((1978, "peterson"))
        self.addCleanup(chk.SEASON_ENDING_EVENTS.update, original)
        self.assertEqual(chk.SeasonOracle(self.con, 1978).clinch("mario_andretti"), (15, 1))

    def test_negative_1961_stays_second_to_last_round(self):
        """陰性：1961 具名例外（von Trips R7 身亡）撐住 R7，既有 clinch_from_end=2 不得漂移。"""
        oracle = chk.SeasonOracle(self.con, 1961)
        self.assertEqual(oracle.clinch("phil_hill"), (7, 1))
        ok, actual, detail = chk.verify_claim(
            self.con, self._claim(1961, kind="clinch_from_end", driver="phil_hill", value=2))
        self.assertTrue(ok, f"{detail}＝{actual}")

    def test_negative_2002_clinch_unchanged(self):
        """陰性：2002 沒有中途退出者，H6 不得改動既有的 (11, 6)。"""
        self.assertEqual(chk.SeasonOracle(self.con, 2002).clinch("michael_schumacher"), (11, 6))

    def test_negative_1970_clinch_unchanged(self):
        """陰性：1970 的例外落在冠軍本人（Rindt）身上，只影響對手集合的那條規則不該波及。"""
        self.assertEqual(chk.SeasonOracle(self.con, 1970).clinch("rindt"), (12, 1))


# ---------------------------------------------------------------- H7
class Hole7ClinchCountback(_DbCase):
    """H7：積分可追平時要比 countback，且對手的 countback 要用理論最佳而不是他現實的勝場。"""

    def test_positive_1957_clinch_is_german_gp_r6(self):
        """陽性：R6 方吉歐保底 34 ＝ Musso 上限 34，勝場 4 ＞ 2（理論最佳）→ 當站封王。"""
        oracle = chk.SeasonOracle(self.con, 1957)
        floor = oracle._segments(oracle.round_points["fangio"], 6)
        rival = oracle._segments({**{r: v for r, v in oracle.round_points["musso"].items() if r <= 6},
                                  **{f: oracle._ceiling() for f in (7, 8)}})
        self.assertEqual((floor, rival), (34.0, 34.0), "這一站正是同分的臨界點")
        self.assertEqual(oracle.clinch("fangio"), (6, 2))

    def test_positive_1957_old_value_r7_is_rejected(self):
        """陽性：舊 oracle 的 R7（嚴格大於才算鎖定）必須被拒。"""
        ok, _actual, _detail = chk.verify_claim(
            self.con, self._claim(1957, kind="clinch_round", driver="fangio", value=7))
        self.assertFalse(ok, "clinch_round=7 是 H7 造成的延後值")
        ok6, _a, detail6 = chk.verify_claim(
            self.con, self._claim(1957, kind="clinch_round", driver="fangio", value=6))
        self.assertTrue(ok6, detail6)

    def test_positive_1988_senna_clinches_at_suzuka_r15(self):
        """陽性（獨立佐證）：1988 Senna R15 保底 87 ＝ Prost 上限 87，第 8 勝在 countback 勝出。"""
        oracle = chk.SeasonOracle(self.con, 1988)
        self.assertEqual(oracle.clinch("senna"), (15, 1))
        self.assertEqual(oracle.finishes_through("senna", 15)[1], 8)
        self.assertEqual(oracle.finishes_through("prost", 15)[1], 6)

    def test_positive_rival_countback_uses_theoretical_best_not_actual(self):
        """陽性：對手要追平上限就得剩餘站全勝，countback 必須按理論最佳算。

        1957 R6 的 Musso 現實上一勝未得；若拿他的**現實**勝場來比，只要冠軍有 1 勝就會被判鎖定。
        用理論最佳（0 勝 ＋ 剩餘 2 站各記一勝＝2 勝）才會正確地擋下來。
        """
        oracle = chk.SeasonOracle(self.con, 1957)
        floor = 34.0
        rival_points = oracle.round_points["musso"]
        self.assertEqual(oracle.finishes_through("musso", 6)[1], 0, "Musso 到 R6 為止零勝")
        self.assertTrue(oracle._rival_settled(
            "fangio", floor, Counter({1: 4}), "musso", rival_points, 6, oracle._ceiling()))
        self.assertFalse(oracle._rival_settled(
            "fangio", floor, Counter({1: 1}), "musso", rival_points, 6, oracle._ceiling()),
            "1 勝 ＜ 對手理論最佳的 2 勝，不該判為鎖定")

    def test_positive_countback_dead_heat_is_not_a_clinch(self):
        """陽性（default-deny）：countback 完全同階＝分不出先後，不算鎖定。"""
        self.assertIsNone(chk.SeasonOracle._countback_wins(Counter({1: 2, 2: 1}),
                                                           Counter({1: 2, 2: 1})))

    def test_negative_non_tie_seasons_unchanged(self):
        """陰性：沒有同分臨界點的賽季，clinch 值一個都不准漂。"""
        expected = {(1959, "jack_brabham"): (9, 0), (1991, "senna"): (15, 1),
                    (2000, "michael_schumacher"): (16, 1), (2005, "alonso"): (17, 2),
                    (2019, "hamilton"): (19, 2), (2025, "norris"): (24, 0)}
        for (year, driver), want in expected.items():
            self.assertEqual(chk.SeasonOracle(self.con, year).clinch(driver), want, f"{year} 漂移")


# ---------------------------------------------------------------- 全篇不得翻紅
class ApprovedIntrosStayGreen(_DbCase):
    """v3 三道修補之後，已核准導言（2026-08-24 第三批後 40 篇）必須維持全綠、零豁免。"""

    def test_all_approved_intros_green(self):
        years = sorted(int(p.stem) for p in chk.CONTENT.glob("*.md") if p.stem.isdigit())
        self.assertEqual(len(years), 52, "導言篇數變了，這條斷言要跟著重新確認")
        failures = {y: chk.check_year(y, self.con) for y in years}
        self.assertEqual({y: e for y, e in failures.items() if e}, {})


if __name__ == "__main__":
    unittest.main()
