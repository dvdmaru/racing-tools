#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I7／I13 賽程完整性反向測試（2026-08-03 EX-034 結構性修正的證據）。

背景：舊 I7 對**所有**排定 round 主張「必須有賽果」，於是進行中賽季必然失敗，只能靠
EX-034 這條具名例外遮住；而該例外的判別明細綁著會動的數字（排定站數、已完賽站數），
每跑完一站指紋就失效 → gate 恆紅 → 百科安靜凍結。修法是把混在一起的訊號拆成兩條：

  I7  凍結賽季（最新賽季以前）每個排定 round 都必須有賽果（不看日期）。
  I13 到期未出賽果：正賽日 UTC 日終 + RESULT_GRACE_HOURS 已過而仍無賽果的場次。

**全綠的 gate 分不出「乾淨」和「斷言壞掉」**，所以每一條新斷言都必須有一個證明它會失敗
的測試。本檔即那些反例：
  ① 全部一致 → I7/I13 皆綠（基準，其餘測試的對照組）
  ② 刪掉一場已完賽的賽果 → I13 紅（凍結季同時被 I7 抓到＝多路徑重疊，非漏抓）
  ③ 未來場次沒有賽果 → I13 **不**紅（這是正常狀態，不是異常）
  ④ 寬限窗：剛跑完還在 48h 內 → 不紅；跨過 48h 仍無賽果 → 紅
  ⑤ 進行中賽季不再讓 I7 失敗（EX-034 得以整條移除的直接證據）
  ⑥ 指紋不含「現在時刻」：同資料在不同時刻取指紋必須相同（否則例外又會每次失效）
  ⑦ I7 的射程不用 seasons.status（那會變恆真式）：狀態被寫成 completed 也照樣抓缺漏
  ⑧ 無賽果又日期壞掉 → 走 undated 通道明說「無法判定」，不假裝綠也不假裝到期

跑法：python3 -m unittest discover -s tests
"""
import datetime
import importlib.util
import pathlib
import sqlite3
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UTC = datetime.timezone.utc


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bdb = _load("build_f1_db", "build-f1-db.py")
inv = _load("check_f1_invariants", "check-f1-invariants.py")

NOW = datetime.datetime(2026, 8, 3, 12, 0, tzinfo=UTC)

# 2025＝凍結季（2 站全跑完）、2026＝最新賽季（R1/R2 已跑完，R3 在未來）
FROZEN, LATEST = 2025, 2026


def _mk(races_with_results=((FROZEN, 1, "2025-03-09", True),
                            (FROZEN, 2, "2025-03-23", True),
                            (LATEST, 1, "2026-03-08", True),
                            (LATEST, 2, "2026-07-26", True),
                            (LATEST, 3, "2026-08-23", False))):
    """合成最小 db：(season, round, date, has_result) 四元組直接描述賽程與賽果。"""
    con = sqlite3.connect(":memory:")
    con.executescript(bdb.SCHEMA)
    for y in (FROZEN, LATEST):
        con.execute("INSERT INTO seasons VALUES (?,?,?)", (y, "", "completed"))
    rid = 0
    for season, rnd, date, has_result in races_with_results:
        con.execute("INSERT INTO races VALUES (?,?,?,?,?,?)",
                    (season, rnd, f"R{rnd} GP", date, "circ", ""))
        if has_result:
            rid += 1
            con.execute("INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rid, season, rnd, "1", 1, "1", 25.0, "drv", "con", 1, 50, "Finished"))
    con.commit()
    return con


def _seasons_of(vs, kind=None):
    return sorted(v["scope"]["season"] for v in vs
                  if kind is None or v["scope"].get("kind") == kind)


class ScheduleFreshnessTests(unittest.TestCase):

    def setUp(self):
        self.con = _mk()
        self.cur = self.con.cursor()

    def tearDown(self):
        self.con.close()

    # ① 基準：資料一致時兩條都綠
    def test_consistent_universe_is_green(self):
        self.assertEqual(inv.inv_I7(self.cur), [])
        self.assertEqual(inv.inv_I13(self.cur, now=NOW), [])

    # ② 刪掉一場已完賽的賽果 → I13 必須紅
    def test_deleting_completed_race_result_fires_I13(self):
        self.cur.execute("DELETE FROM results WHERE season=? AND round=2", (LATEST,))
        self.con.commit()
        vs = inv.inv_I13(self.cur, now=NOW)
        self.assertEqual(_seasons_of(vs, "overdue"), [LATEST])
        self.assertEqual(vs[0]["detail"]["overdue_rounds"], [2])
        self.assertEqual(vs[0]["detail"]["grace_hours"], inv.RESULT_GRACE_HOURS)

    # ②b 凍結季的歷史賽果消失 → I13 與 I7 同時紅（刻意重疊的多路徑，比照 I2/I3/I4）
    def test_deleting_frozen_season_result_fires_both_I7_and_I13(self):
        self.cur.execute("DELETE FROM results WHERE season=? AND round=1", (FROZEN,))
        self.con.commit()
        self.assertEqual(_seasons_of(inv.inv_I7(self.cur)), [FROZEN])
        self.assertEqual(_seasons_of(inv.inv_I13(self.cur, now=NOW), "overdue"), [FROZEN])

    # ③ 未來場次沒有賽果 → 必須不紅（正常狀態，不是異常）
    def test_future_race_without_result_does_not_fire(self):
        # 基準 db 的 LATEST R3（2026-08-23）本來就是未來場次且無賽果
        self.assertEqual(inv.inv_I13(self.cur, now=NOW), [])
        # 再加一場更遠的未來賽事，仍然不叫
        self.cur.execute("INSERT INTO races VALUES (?,?,?,?,?,?)",
                         (LATEST, 4, "R4 GP", "2026-12-06", "circ", ""))
        self.con.commit()
        self.assertEqual(inv.inv_I13(self.cur, now=NOW), [])
        self.assertEqual(inv.inv_I7(self.cur), [])

    # ④ 寬限窗：實測 jolpica 賽後灌檔延遲 ~1.3–9 小時，48h 內不得誤報
    def test_grace_window_boundary(self):
        self.cur.execute("DELETE FROM results WHERE season=? AND round=2", (LATEST,))
        self.con.commit()
        race_day_end = datetime.datetime(2026, 7, 27, 0, 0, tzinfo=UTC)  # 正賽日 UTC 日終
        grace = datetime.timedelta(hours=inv.RESULT_GRACE_HOURS)
        # 寬限內（差一分鐘到期）→ 不叫
        self.assertEqual(inv.inv_I13(self.cur, now=race_day_end + grace
                                     - datetime.timedelta(minutes=1)), [])
        # 到期 → 叫
        self.assertEqual(len(inv.inv_I13(self.cur, now=race_day_end + grace)), 1)

    # ⑤ 進行中賽季不再讓 I7 失敗（EX-034 得以整條移除的直接證據）
    def test_in_progress_season_no_longer_fires_I7(self):
        # LATEST 只有 3 站中的 2 站有賽果——舊 I7 會叫，新 I7 不叫
        scheduled = self.cur.execute(
            "SELECT count(*) FROM races WHERE season=?", (LATEST,)).fetchone()[0]
        ran = self.cur.execute(
            "SELECT count(DISTINCT round) FROM results WHERE season=?", (LATEST,)).fetchone()[0]
        self.assertGreater(scheduled, ran)
        self.assertEqual(inv.inv_I7(self.cur), [])

    # ⑥ 指紋不得含「現在時刻」——否則具名例外會每跑一次就失效（EX-034 的病）
    def test_fingerprint_is_time_independent(self):
        self.cur.execute("DELETE FROM results WHERE season=? AND round=2", (LATEST,))
        self.con.commit()
        # +10 天：期間沒有別的場次跨過到期線（R3 於 2026-08-26 才到期），故到期集合不變
        later = NOW + datetime.timedelta(days=10)
        a = inv.inv_I13(self.cur, now=NOW)[0]["fingerprint"]
        b = inv.inv_I13(self.cur, now=later)[0]["fingerprint"]
        self.assertEqual(a, b, "同一份資料、同一組到期場次，在不同時刻必須是同一個指紋")

    # ⑥b 但缺漏場次集合變動仍必須改指紋（指紋沒有因為去掉時間而變鬆）
    def test_fingerprint_changes_when_overdue_set_changes(self):
        self.cur.execute("DELETE FROM results WHERE season=? AND round=2", (LATEST,))
        self.con.commit()
        a = inv.inv_I13(self.cur, now=NOW)[0]["fingerprint"]
        self.cur.execute("DELETE FROM results WHERE season=? AND round=1", (LATEST,))
        self.con.commit()
        b = inv.inv_I13(self.cur, now=NOW)[0]["fingerprint"]
        self.assertNotEqual(a, b)

    # ⑦ I7 射程不得取自 seasons.status（那是由「所有 round 都有賽果」推得 → 恆真式）
    def test_I7_scope_not_derived_from_seasons_status(self):
        self.cur.execute("DELETE FROM results WHERE season=? AND round=1", (FROZEN,))
        self.cur.execute("UPDATE seasons SET status='completed' WHERE year=?", (FROZEN,))
        self.con.commit()
        self.assertEqual(_seasons_of(inv.inv_I7(self.cur)), [FROZEN],
                         "status 被寫成 completed 仍必須抓到缺漏，否則 I7 是恆真式")

    # ⑦b I7 不看日期：日期壞掉的凍結季缺漏仍要抓到（date 損壞不得 fail-open）
    def test_I7_still_fires_when_date_is_corrupted(self):
        self.cur.execute("DELETE FROM results WHERE season=? AND round=1", (FROZEN,))
        self.cur.execute("UPDATE races SET date='' WHERE season=? AND round=1", (FROZEN,))
        self.con.commit()
        self.assertEqual(_seasons_of(inv.inv_I7(self.cur)), [FROZEN])

    # ⑧ 無賽果又日期無法解析 → undated 通道明說「無法判定」（fail-honest，不猜）
    def test_unparseable_date_without_result_reports_undated(self):
        self.cur.execute("UPDATE races SET date=NULL WHERE season=? AND round=3", (LATEST,))
        self.con.commit()
        vs = inv.inv_I13(self.cur, now=NOW)
        self.assertEqual(_seasons_of(vs, "undated"), [LATEST])
        self.assertEqual(vs[0]["detail"]["undated_rounds"], [3])
        self.assertEqual(_seasons_of(vs, "overdue"), [])

    # ⑧b 但日期壞掉而**有**賽果的場次不得製造假紅
    def test_unparseable_date_with_result_is_silent(self):
        self.cur.execute("UPDATE races SET date='not-a-date' WHERE season=? AND round=1",
                         (LATEST,))
        self.con.commit()
        self.assertEqual(inv.inv_I13(self.cur, now=NOW), [])


class RealDbScheduleFreshnessTests(unittest.TestCase):
    """真實 db：I13 必須是綠的（若紅＝當季管線真的斷了，不是測試壞了）。"""

    @classmethod
    def setUpClass(cls):
        db = ROOT / "data" / "f1" / "db.sqlite"
        if not db.exists():
            raise unittest.SkipTest("data/f1/db.sqlite 不存在")
        cls.con = sqlite3.connect(str(db))

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_no_overdue_race_in_real_db(self):
        vs = inv.inv_I13(self.con.cursor())
        self.assertEqual(vs, [], f"有到期未出賽果的場次：{[v['detail'] for v in vs]}")

    def test_I13_is_registered_in_all_invariants(self):
        self.assertIn("I13", inv.INVARIANT_IDS)
        self.assertIn(inv.inv_I13, inv.ALL_INVARIANTS)

    def test_no_exception_declares_I7_or_I13(self):
        """EX-034 已整條移除；I7/I13 都是恆真斷言，不該再有任何具名例外遮住它們。"""
        declared = inv.load_declared()
        self.assertEqual([e["id"] for e in declared
                          if e["invariant"] in ("I7", "I13")], [])


if __name__ == "__main__":
    unittest.main()
