#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I12「賽季宇宙覆蓋」攻擊情境回歸測試（Terra 盲測缺口）。

背景：I1–I11 全部以「被檢查表裡**實際出現**的賽季」當迭代宇宙（_seasons /
_races_with_results / races 表）——整季資料消失時迴圈直接空轉、檢查全綠。I12 反過來以
seasons 表為錨點宇宙做覆蓋斷言。本檔用合成 sqlite（照 test_f1_db.py 的 in-memory 慣例）
注入「整季消失」「錨點斷裂」等攻擊，證明：
  ① 整季 driver_standings/results 消失 → I12 抓到，而 I1 迭代宇宙空轉不叫（正是缺口）；
  ② seasons 錨點中間斷一年 → I12 anchor 抓到；
  ③ constructor_standings 缺 1958 前的年份 → I12 **不**誤報（史實：車隊冠軍 1958 才設立）；
  ④ 刪 1958 後的 constructor_standings 整季 → I12 抓到；
  ⑤ 完整合成資料 → I12 零 violation。

跑法：python3 -m unittest discover -s tests
"""
import importlib.util
import pathlib
import sqlite3
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bdb = _load("build_f1_db", "build-f1-db.py")
inv = _load("check_f1_invariants", "check-f1-invariants.py")


def _build_universe(years=range(1950, 1971), cs_since=1958):
    """合成一顆最小但**連續且逐季覆蓋**的 db：seasons 1950..1970、每季一場 race/result/
    driver_standings，constructor_standings 只從 cs_since 起（比照史實）。完整態下 I12 應零叫。"""
    con = sqlite3.connect(":memory:")
    con.executescript(bdb.SCHEMA)
    for y in years:
        con.execute("INSERT INTO seasons VALUES (?,?,?)", (y, "", "completed"))
        con.execute("INSERT INTO races VALUES (?,?,?,?,?,?)",
                    (y, 1, "GP", f"{y}-01-01", "circ", ""))
        con.execute("INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (y * 100 + 1, y, 1, "1", 1, "1", 9.0, "drv", "con", 1, 10, "Finished"))
        con.execute("INSERT INTO driver_standings VALUES (?,?,?,?,?,?,?)",
                    (y, 1, "1", 9.0, 1, "drv", "con"))
        if y >= cs_since:
            con.execute("INSERT INTO constructor_standings VALUES (?,?,?,?,?,?)",
                        (y, 1, "1", 9.0, 1, "con"))
    con.commit()
    return con


def _table_violation(vs, table):
    return [v for v in vs if v["scope"].get("table") == table]


def _anchor_violation(vs):
    return [v for v in vs if v["scope"].get("kind") == "anchor"]


class I12UniverseTests(unittest.TestCase):

    def setUp(self):
        self.con = _build_universe()
        self.cur = self.con.cursor()

    def tearDown(self):
        self.con.close()

    # ⑤ 完整合成資料 → 零 violation（其餘測試的基準）
    def test_complete_universe_zero_violations(self):
        self.assertEqual(inv.inv_I12(self.cur), [])

    # ① 整季 driver_standings 消失 → I12 叫；而 I1 迭代宇宙空轉不叫（正是缺口）
    def test_delete_driver_standings_season_fires_but_I1_is_blind(self):
        self.cur.execute("DELETE FROM driver_standings WHERE season=1960")
        self.con.commit()
        vs = inv.inv_I12(self.cur)
        hit = _table_violation(vs, "driver_standings")
        self.assertEqual(len(hit), 1)
        self.assertIn(1960, hit[0]["detail"]["sample"])
        # 缺口證明：I1 以 driver_standings 實際出現的季為宇宙，整季刪光後根本不迭代 1960 → 不叫
        i1 = inv.inv_I1(self.cur)
        self.assertFalse(any(v["scope"].get("season") == 1960 for v in i1),
                         "I1 對整季消失是盲區——這正是 I12 補的洞")

    # ② 整季 results 消失 → I12 叫
    def test_delete_results_season_fires(self):
        self.cur.execute("DELETE FROM results WHERE season=1955")
        self.con.commit()
        vs = inv.inv_I12(self.cur)
        hit = _table_violation(vs, "results")
        self.assertEqual(len(hit), 1)
        self.assertIn(1955, hit[0]["detail"]["sample"])

    # ③ seasons 錨點中間斷一年 → I12 anchor 叫（連續性斷裂）
    def test_seasons_continuity_gap_fires(self):
        self.cur.execute("DELETE FROM seasons WHERE year=1960")
        self.con.commit()
        vs = inv.inv_I12(self.cur)
        anchor = _anchor_violation(vs)
        self.assertEqual(len(anchor), 1)
        self.assertIn(1960, anchor[0]["detail"]["missing_years"])

    # ③b seasons 起點被抬高（min != 1950）→ I12 anchor 叫
    def test_seasons_min_not_1950_fires(self):
        self.cur.execute("DELETE FROM seasons WHERE year=1950")
        self.con.commit()
        anchor = _anchor_violation(inv.inv_I12(self.cur))
        self.assertEqual(len(anchor), 1)
        self.assertIn(1950, anchor[0]["detail"]["missing_years"])

    # ④ constructor_standings 缺 1958 前年份 → I12 不誤報（車隊冠軍 1958 才設立）
    def test_constructor_standings_missing_pre_1958_not_flagged(self):
        # 完整態下 constructor_standings 本就只有 1958+；1950–57 缺席是史實不是缺漏
        present = {r[0] for r in self.cur.execute(
            "SELECT DISTINCT season FROM constructor_standings")}
        self.assertFalse(any(y < 1958 for y in present))
        self.assertEqual(_table_violation(inv.inv_I12(self.cur), "constructor_standings"), [])

    # ④b 刪 1958 後的 constructor_standings 整季 → I12 叫
    def test_delete_constructor_standings_1970_fires(self):
        self.cur.execute("DELETE FROM constructor_standings WHERE season=1970")
        self.con.commit()
        hit = _table_violation(inv.inv_I12(self.cur), "constructor_standings")
        self.assertEqual(len(hit), 1)
        self.assertIn(1970, hit[0]["detail"]["sample"])

    # 指紋覆蓋：missing_seasons 成員變動必須改指紋（照既有 violation 精神）
    def test_missing_season_set_membership_changes_fingerprint(self):
        self.cur.execute("DELETE FROM results WHERE season=1955")
        self.con.commit()
        fp1 = _table_violation(inv.inv_I12(self.cur), "results")[0]["fingerprint"]
        self.cur.execute("DELETE FROM results WHERE season=1956")
        self.con.commit()
        fp2 = _table_violation(inv.inv_I12(self.cur), "results")[0]["fingerprint"]
        self.assertNotEqual(fp1, fp2, "缺漏季集合多一個成員必須改指紋")


if __name__ == "__main__":
    unittest.main()
