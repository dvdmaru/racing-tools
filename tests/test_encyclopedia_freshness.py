#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""百科／週更兩層賽曆同步 gate 的回歸測試。

由來（2026-08-03）：巴林站移師雪邦後週更層當天變 23 站，百科 db.sqlite 停在
7/21 的 22 站快照兩週沒人發現——因為沒有東西在比對這兩層。
check-encyclopedia-freshness.py 就是補這塊地。

這裡釘四件事：
1. 一致的時候**不能**報錯（假陽性的 gate 沒人讀，最後一定被關掉）
2. 抓得到站數不同、同一 round 指向不同分站、已完賽場數落後
3. **這道 gate 真的會失敗**——對一致的 fixture 做窮舉擾動，每一種都必須紅。
   全綠的 gate 分不出「乾淨」和「斷言壞掉」，所以要有東西證明它會叫。
4. 輸入讀不到時走 FAIL 而不是靜默通過

全部在 tmpdir 建合成 db 與合成 data 目錄，**不碰真的 data/f1/db.sqlite**。

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ce = _load("check_encyclopedia_freshness", "check-encyclopedia-freshness.py")

SEASON = 2026
# 縮小版的真實情境：R16 就是那站插進來的巴林／雪邦，其後整體 +1。
CALENDAR = [
    (14, "Spanish Grand Prix"),
    (15, "Azerbaijan Grand Prix"),
    (16, "Bahrain Grand Prix in Malaysia"),
    (17, "Singapore Grand Prix"),
    (18, "Abu Dhabi Grand Prix"),
]
COMPLETED = 3


def make_db(path, calendar, completed_rounds):
    """建一個只有本 gate 讀得到的兩張表的合成 db。"""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE races (season INT, round INT, name TEXT)")
    con.execute("CREATE TABLE results (season INT, round INT, driver_id TEXT)")
    con.executemany("INSERT INTO races VALUES (?,?,?)",
                    [(SEASON, r, n) for r, n in calendar])
    # 每站塞兩列，確認 gate 數的是 DISTINCT round 而不是賽果列數
    con.executemany("INSERT INTO results VALUES (?,?,?)",
                    [(SEASON, r, d) for r in completed_rounds for d in ("a", "b")])
    con.commit()
    con.close()


def make_data_dir(root, calendar, completed_rounds, extra_files=()):
    """建合成週更層：schedule.json ＋ results/round-NN.json。"""
    d = pathlib.Path(root) / str(SEASON)
    (d / "results").mkdir(parents=True, exist_ok=True)
    (d / "schedule.json").write_text(json.dumps({
        "season": str(SEASON),
        # 週更層的 round/season 是字串，這裡刻意照抄真實型別
        "races": [{"season": str(SEASON), "round": str(r), "raceName": n}
                  for r, n in calendar],
    }, ensure_ascii=False), encoding="utf-8")
    for r in completed_rounds:
        (d / "results" / f"round-{r:02d}.json").write_text("{}", encoding="utf-8")
    for name in extra_files:
        (d / "results" / name).write_text("{}", encoding="utf-8")
    return pathlib.Path(root)


class FreshnessGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.db = self.root / "db.sqlite"
        self.done = list(range(14, 14 + COMPLETED))

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, db_cal=None, db_done=None, sc_cal=None, sc_done=None, extra=()):
        make_db(self.db, db_cal or CALENDAR, db_done or self.done)
        data = make_data_dir(self.root / "data", sc_cal or CALENDAR,
                             sc_done or self.done, extra)
        return ce.run(self.db, data, SEASON)[0]

    # --- 反向：一致就不准報錯 ---

    def test_consistent_is_clean(self):
        self.assertEqual(self.build(), [])

    def test_sprint_and_lap_files_are_not_counted_as_races(self):
        """`round-*.json` 會把 sprint/laps/pitstops 一起數進去——check-site-facts.py
        踩過這個坑（11 站被算成 19 站）。這裡放進那些雜訊檔，仍必須乾淨。"""
        problems = self.build(extra=("round-14-sprint.json", "round-15-laps.json",
                                     "round-15-pitstops.json", "round-16-sprint.json"))
        self.assertEqual(problems, [])

    # --- 正向：各種對不上都要抓到 ---

    def test_race_count_mismatch_is_caught(self):
        problems = self.build(db_cal=CALENDAR[:-1])
        self.assertTrue(any("站數不一致" in p for p in problems), problems)

    def test_round_shift_caught_even_when_count_matches(self):
        """真實病灶：百科少了插進來的那站，其後整體錯位。站數相同也必須抓到。"""
        shifted = [(14, "Spanish Grand Prix"), (15, "Azerbaijan Grand Prix"),
                   (16, "Singapore Grand Prix"), (17, "Abu Dhabi Grand Prix"),
                   (18, "Qatar Grand Prix")]
        problems = self.build(db_cal=shifted)
        self.assertEqual(len(shifted), len(CALENDAR))       # 前提：站數一樣
        self.assertFalse(any("站數不一致" in p for p in problems), problems)
        self.assertTrue(any("第 16 站對不上" in p for p in problems), problems)

    def test_completed_count_mismatch_is_caught(self):
        problems = self.build(db_done=self.done[:-1])
        self.assertTrue(any("已完賽場數不一致" in p for p in problems), problems)

    # --- 證明這道 gate 真的會叫：對一致的 fixture 窮舉擾動 ---

    def test_every_single_mutation_is_detected(self):
        """一致 fixture 的每一種單點擾動都必須被抓到。

        全綠的 gate 分不出「資料乾淨」和「斷言根本沒在跑」。這個掃描就是那個分辨器：
        任何一種擾動漏掉，代表 gate 在那個維度是瞎的。
        """
        mutations = []
        for i, (rnd, name) in enumerate(CALENDAR):
            bad = list(CALENDAR)
            bad[i] = (rnd, name + "（改過）")
            mutations.append((f"改第 {rnd} 站名稱", {"db_cal": bad}))
            mutations.append((f"週更改第 {rnd} 站名稱", {"sc_cal": bad}))
        mutations += [
            ("百科少一站", {"db_cal": CALENDAR[:-1]}),
            ("週更少一站", {"sc_cal": CALENDAR[:-1]}),
            ("百科多一站", {"db_cal": CALENDAR + [(19, "Extra Grand Prix")]}),
            ("週更多一站", {"sc_cal": CALENDAR + [(19, "Extra Grand Prix")]}),
            ("百科少一場賽果", {"db_done": self.done[:-1]}),
            ("週更少一場賽果", {"sc_done": self.done[:-1]}),
        ]
        for label, kwargs in mutations:
            with self.subTest(mutation=label):
                self.tearDown()         # 每個擾動用乾淨的 tmpdir 重建（最後一輪由外層收）
                self.setUp()
                self.assertNotEqual(self.build(**kwargs), [],
                                    f"擾動「{label}」沒有被抓到＝gate 在這個維度是瞎的")

    # --- 輸入缺漏＝FAIL，不是靜默通過 ---

    def test_missing_db_raises(self):
        make_data_dir(self.root / "data", CALENDAR, self.done)
        with self.assertRaises(ce.InputMissing):
            ce.run(self.root / "nope.sqlite", self.root / "data", SEASON)

    def test_missing_schedule_raises(self):
        make_db(self.db, CALENDAR, self.done)
        with self.assertRaises(ce.InputMissing):
            ce.run(self.db, self.root / "empty-data", SEASON)

    def test_main_exits_nonzero_on_missing_input(self):
        """缺輸入時 main 必須回 1。這條擋的是「找不到檔案就當通過」那種腐蝕。"""
        argv = sys.argv
        sys.argv = ["check-encyclopedia-freshness.py", "--season", str(SEASON),
                    "--db", str(self.root / "nope.sqlite"),
                    "--data-dir", str(self.root / "empty-data")]
        try:
            self.assertEqual(ce.main(), 1)
        finally:
            sys.argv = argv

    def test_main_exits_zero_when_consistent(self):
        make_db(self.db, CALENDAR, self.done)
        data = make_data_dir(self.root / "data", CALENDAR, self.done)
        argv = sys.argv
        sys.argv = ["check-encyclopedia-freshness.py", "--season", str(SEASON),
                    "--db", str(self.db), "--data-dir", str(data)]
        try:
            self.assertEqual(ce.main(), 0)
        finally:
            sys.argv = argv


class RealDataTest(unittest.TestCase):
    """真實資料應該是一致的（唯讀，不改動 db.sqlite）。

    這條同時是「gate 不會對真實資料亂叫」的假陽性防線。
    """

    def test_real_repo_is_consistent(self):
        season = json.loads(
            (ROOT / "config" / "site.json").read_text(encoding="utf-8"))["season"]
        db = ROOT / "data" / "f1" / "db.sqlite"
        if not db.exists():
            self.skipTest("db.sqlite 不在（乾淨 checkout）")
        problems, _ = ce.run(db, ROOT / "data", season)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
