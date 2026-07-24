#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M7 百科線接週更管線 回歸測試。

鎖住 M7 的五塊交付與紅線：
  1. ROUND_YEARS 單一來源（config/encyclopedia.json）——seasons/drivers 同源。
  2. 當季橋接 refresh-f1-current：格式相容（build-f1-db 讀得動）、resumable/idempotent、
     安靜跳過（無新賽果 exit 0）、不變量擋線（失敗 → exit 1 不進頁面重生）。
  3. 選擇性重生（facts-hash）：合成塞一筆 2026 新賽果 → 恰好預期集合變更、1950–2025 零重寫。
  4. golden 活躍車手 as_of：新賽果不動 gate（as_of 截斷）、篡改 as_of<= 歷史 → gate 紅。
  5. update-racing dormant 接線：published:false 整段 skip 零副作用（byte-identical）；
     百科層失敗不進週更 FAILED、不擋部署（分層 fail）。

跑法：python3 -m unittest discover -s tests -v
"""
import copy
import importlib.util
import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rc = _load("racinglib", "racinglib.py")
fs = _load("f1stats", "f1stats.py")
re_mod = _load("regen_encyclopedia", "regen-encyclopedia.py")
refresh_mod = _load("refresh_f1_current", "refresh-f1-current.py")
dr = re_mod.dr
gs = re_mod.gs


# ---------- 共用：temp db 注入合成賽果 ----------

def _copy_db(tmp):
    db = tmp / "db.sqlite"
    shutil.copy(fs.DB, db)
    return db


def _inject_result(db, did, season, rnd, position_text="1", points=25.0, constructor="mercedes"):
    con = sqlite3.connect(str(db))
    maxid = con.execute("SELECT max(id) FROM results").fetchone()[0]
    con.execute(
        "INSERT INTO results (id,season,round,number,position,position_text,points,"
        "driver_id,constructor_id,grid,laps,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (maxid + 1, season, rnd, "44", int(position_text) if position_text.isdigit() else None,
         position_text, points, did, constructor, 1, 50, "Finished"))
    con.execute(
        "INSERT OR IGNORE INTO races (season,round,name,date,circuit_id,url) "
        "VALUES (?,?,?,?,?,?)", (season, rnd, "Synthetic GP", "2026-08-01", "synthetic", None))
    con.commit()
    con.close()


# ============================================================
# 1. ROUND_YEARS 單一來源
# ============================================================

class RoundYearsSingleSourceTests(unittest.TestCase):
    def test_config_round_years_loaded(self):
        self.assertEqual(rc.ROUND_YEARS, frozenset({2002, 2026}))

    def test_drivers_derives_from_config(self):
        self.assertEqual(dr.ROUND_YEARS, set(rc.ROUND_YEARS))

    def test_seasons_all_uses_config_round_years(self):
        # gen-racing-seasons --all（省略 --rounds-for）→ 用 config round_years（非硬編）
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = gs.PUB
        gs.PUB = tmp
        old_argv = sys.argv
        sys.argv = ["gen-racing-seasons.py", "--all"]
        try:
            gs.main()
        finally:
            gs.PUB = orig
            sys.argv = old_argv
        # 2002/2026 在 config round_years → 有分站頁；1950（不在）→ 無分站頁
        self.assertTrue((tmp / "seasons" / "2002" / "rounds" / "1" / "index.html").is_file())
        self.assertTrue((tmp / "seasons" / "2026" / "rounds" / "1" / "index.html").is_file())
        self.assertFalse((tmp / "seasons" / "1950" / "rounds").exists())

    def test_single_season_debug_mode_no_round_pages(self):
        # 單季 debug 模式（無 --all、無 --rounds-for）預設不產分站頁（保留既有行為）
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = gs.PUB
        gs.PUB = tmp
        old_argv = sys.argv
        sys.argv = ["gen-racing-seasons.py", "--season", "2002"]
        try:
            gs.main()
        finally:
            gs.PUB = orig
            sys.argv = old_argv
        self.assertFalse((tmp / "seasons" / "2002" / "rounds").exists())


# ============================================================
# 2. golden 活躍車手 as_of 截斷
# ============================================================

class GoldenAsOfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = json.loads(dr.GOLDEN.read_text(encoding="utf-8"))["drivers"]

    def test_every_champion_has_as_of(self):
        for did in dr.CHAMPION_IDS:
            self.assertIn("as_of", self.golden[did], f"{did} 缺 as_of")
            ao = self.golden[did]["as_of"]
            self.assertIn("season", ao)
            self.assertIn("round", ao)

    def test_active_drivers_as_of_frozen_at_snapshot(self):
        # 活躍車手（2026 有參賽）as_of 綁在快照邊界 {2026,10}
        con = fs.connect_db()
        try:
            for did in dr.CHAMPION_IDS:
                last = con.execute(
                    "SELECT max(season) FROM results WHERE driver_id=?", (did,)).fetchone()[0]
                if last == 2026:
                    self.assertEqual(self.golden[did]["as_of"], {"season": 2026, "round": 10},
                                     f"{did} 為活躍車手，as_of 應凍結在 2026/10")
        finally:
            con.close()

    def test_golden_gate_green_now(self):
        self.assertTrue(dr.gate_golden())

    def test_new_result_does_not_break_gate(self):
        # 合成塞活躍車手 as_of 之後的新賽果（2026 R11）→ 全量現值變、as_of 截斷值不變 → gate 仍綠
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        db = _copy_db(tmp)
        _inject_result(db, "hamilton", 2026, 11, position_text="1")
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
        try:
            # 全量現值：勝場 +1
            full = fs.driver_career_db("hamilton", con)
            self.assertEqual(full["wins"]["value"], self.golden["hamilton"]["wins"] + 1)
            # as_of 截斷（2026/10）：不含 R11 → 與 golden 一致 → gate 綠
            trunc = fs.driver_career_db("hamilton", con, as_of={"season": 2026, "round": 10})
            self.assertEqual(trunc["wins"]["value"], self.golden["hamilton"]["wins"])
            self.assertTrue(dr.gate_golden(con=con),
                            "新賽果（as_of 之後）不得使 golden gate 變紅")
        finally:
            con.close()

    def test_tampering_within_as_of_window_reddens_gate(self):
        # 篡改 as_of<= 的歷史（塞一場 2005 勝場給 hamilton，2005<=2026/10）→ 截斷值變 → gate 紅
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        db = _copy_db(tmp)
        _inject_result(db, "hamilton", 2005, 99, position_text="1")
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
        try:
            self.assertFalse(dr.gate_golden(con=con),
                             "as_of 窗口內的歷史被篡改應使 gate 變紅")
        finally:
            con.close()

    def test_truncation_is_filter_not_subtraction(self):
        # 截斷後 value 仍 == len(detail)（明細 filter，非總數減法）
        con = fs.connect_db()
        try:
            car = fs.driver_career_db("hamilton", con, as_of={"season": 2020, "round": 5})
            for k in ("wins", "podiums", "entries"):
                self.assertEqual(car[k]["value"], len(car[k]["detail"]))
        finally:
            con.close()


# ============================================================
# 3. 選擇性重生（facts-hash）
# ============================================================

class SelectiveRegenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.fp = self.tmp / "fp.json"
        self.pub = self.tmp / "pub"
        self._orig_pub = (gs.PUB, dr.PUB, rc.PUB)
        gs.PUB = dr.PUB = rc.PUB = self.pub
        self.dbA = _copy_db(self.tmp)

    def tearDown(self):
        gs.PUB, dr.PUB, rc.PUB = self._orig_pub

    def _con(self, db):
        c = sqlite3.connect(str(db))
        c.row_factory = sqlite3.Row
        return c

    def _full_build(self):
        con = self._con(self.dbA)
        try:
            re_mod.selective_regen(con, full=True, fp_path=self.fp)
        finally:
            con.close()
        return {p: (p.stat().st_mtime_ns, p.read_bytes())
                for p in self.pub.rglob("index.html")}

    def test_full_build_then_nochange_zero_rewrite(self):
        snap = self._full_build()
        self.assertGreater(len(snap), 300)
        self.assertTrue(self.fp.exists())
        con = self._con(self.dbA)
        try:
            res = re_mod.selective_regen(con, full=False, fp_path=self.fp)
        finally:
            con.close()
        self.assertEqual(res["changed_years"], [])
        self.assertEqual(res["changed_drivers"], [])
        self.assertFalse(res["index_seasons"])
        self.assertFalse(res["index_drivers"])
        rewritten = [str(p.relative_to(self.pub)) for p, (m, _) in snap.items()
                     if p.stat().st_mtime_ns != m]
        self.assertEqual(rewritten, [], f"無資料變動不得重寫任何頁：{rewritten[:5]}")

    def test_synthetic_2026_result_changes_exact_set(self):
        snap = self._full_build()
        dbB = self.tmp / "dbB.sqlite"
        shutil.copy(self.dbA, dbB)
        _inject_result(dbB, "hamilton", 2026, 11, position_text="1")
        con = self._con(dbB)
        try:
            res = re_mod.selective_regen(con, full=False, fp_path=self.fp)
        finally:
            con.close()
        # 變更集合精確：當季 2026 + 資料有變的車手 hamilton + 兩索引
        self.assertEqual(res["changed_years"], [2026])
        self.assertEqual(res["changed_drivers"], ["hamilton"])
        self.assertTrue(res["index_seasons"])
        self.assertTrue(res["index_drivers"])

        rewritten = {str(p.relative_to(self.pub)) for p, (m, _) in snap.items()
                     if p.stat().st_mtime_ns != m}
        # 每個被重寫的頁只能屬於預期集合
        def _expected(rel):
            return (rel.startswith("seasons/2026/") or rel == "seasons/index.html"
                    or rel == "drivers/index.html" or rel == "drivers/hamilton/index.html")
        stray = [r for r in rewritten if not _expected(r)]
        self.assertEqual(stray, [], f"重寫了預期集合外的頁：{stray[:10]}")
        # 1950–2025 歷史賽季頁 byte-identical 零重寫
        for p, (m, b) in snap.items():
            rel = str(p.relative_to(self.pub))
            if rel.startswith("seasons/") and not rel.startswith("seasons/2026/") \
                    and rel != "seasons/index.html":
                self.assertEqual(p.stat().st_mtime_ns, m, f"歷史賽季頁被重寫：{rel}")
                self.assertEqual(p.read_bytes(), b, f"歷史賽季頁內容變動：{rel}")
        # 非受影響車手頁零重寫
        for p, (m, b) in snap.items():
            rel = str(p.relative_to(self.pub))
            if rel.startswith("drivers/") and rel not in (
                    "drivers/index.html", "drivers/hamilton/index.html"):
                self.assertEqual(p.stat().st_mtime_ns, m, f"非受影響車手頁被重寫：{rel}")
        # 預期集合確有重寫（2026 總覽 + hamilton 頁 + 索引）
        self.assertIn("seasons/2026/index.html", rewritten)
        self.assertIn("drivers/hamilton/index.html", rewritten)
        self.assertIn("drivers/index.html", rewritten)

    def test_full_flag_ignores_fingerprints(self):
        self._full_build()
        con = self._con(self.dbA)
        try:
            res = re_mod.selective_regen(con, full=True, fp_path=self.fp)
        finally:
            con.close()
        self.assertEqual(len(res["changed_years"]), gs.LAST_YEAR - gs.FIRST_YEAR + 1)
        self.assertEqual(len(res["changed_drivers"]), len(dr.CHAMPION_IDS))

    def test_publish_writes_sitemap_parts(self):
        parts = ROOT / "data" / "sitemap-parts"
        sp, dp = parts / "seasons.txt", parts / "drivers.txt"
        pre = (sp.read_bytes() if sp.exists() else None, dp.read_bytes() if dp.exists() else None)
        self.addCleanup(self._restore, sp, dp, pre)
        con = self._con(self.dbA)
        try:
            re_mod.selective_regen(con, full=True, fp_path=self.fp, publish=True)
        finally:
            con.close()
        self.assertTrue(sp.exists() and dp.exists())
        s_urls = sp.read_text(encoding="utf-8").splitlines()
        self.assertIn(f"{rc.BASE}/seasons/", s_urls)
        self.assertIn(f"{rc.BASE}/seasons/2002/rounds/1/", s_urls)
        d_urls = dp.read_text(encoding="utf-8").splitlines()
        self.assertIn(f"{rc.BASE}/drivers/", d_urls)
        self.assertEqual(len([u for u in d_urls if u != f"{rc.BASE}/drivers/"]),
                         len(dr.CHAMPION_IDS))

    @staticmethod
    def _restore(sp, dp, pre):
        for p, b in ((sp, pre[0]), (dp, pre[1])):
            if b is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(b)


# ============================================================
# 4. 當季橋接 refresh-f1-current
# ============================================================

class FakeFetcher:
    """refresh 用的假 fetcher；依 path 分派回 jolpica 形狀。"""
    def __init__(self, schedule_races, results_by_round=None, standings_rows=None):
        self.schedule = schedule_races
        self.results = results_by_round or {}   # {rnd: race_dict_with_Results 或 None}
        self.standings = standings_rows if standings_rows is not None else [
            {"position": "1", "positionText": "1", "points": "100", "wins": "3",
             "Driver": {"driverId": "hamilton"}, "Constructors": [{"constructorId": "mercedes"}]}]
        self.calls = []

    def get(self, path, params=""):
        self.calls.append(path)
        if path.count("/") == 0:  # "{season}"
            return {"MRData": {"RaceTable": {"Races": self.schedule}}}
        if path.endswith("/results"):
            rnd = int(path.split("/")[1])
            race = self.results.get(rnd)
            return {"MRData": {"RaceTable": {"Races": [race] if race else []}}}
        if path.endswith("/sprint"):
            return {"MRData": {"RaceTable": {"Races": []}}}
        if path.endswith("driverstandings"):
            return {"MRData": {"total": str(len(self.standings)), "StandingsTable": {
                "StandingsLists": [{"season": "2026", "round": "11",
                                    "DriverStandings": self.standings}]}}}
        if path.endswith("constructorstandings"):
            return {"MRData": {"total": "1", "StandingsTable": {"StandingsLists": [
                {"season": "2026", "round": "11", "ConstructorStandings": [
                    {"position": "1", "positionText": "1", "points": "200", "wins": "3",
                     "Constructor": {"constructorId": "mercedes"}}]}]}}}
        raise AssertionError(f"unexpected path {path}")


def _race(rnd, date, with_results=True):
    r = {"season": "2026", "round": str(rnd), "raceName": f"R{rnd} GP",
         "Circuit": {"circuitId": "x", "circuitName": "X"}, "date": date, "time": "13:00:00Z"}
    if with_results:
        r["Results"] = [{"number": "44", "position": "1", "positionText": "1", "points": "25",
                         "Driver": {"driverId": "hamilton"},
                         "Constructor": {"constructorId": "mercedes"},
                         "grid": "1", "laps": "50", "status": "Finished"}]
    return r


class RefreshCurrentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.raw = self.tmp / "raw"
        (self.raw / "results").mkdir(parents=True)
        (self.raw / "sprint").mkdir(parents=True)
        (self.raw / "standings").mkdir(parents=True)
        # 既有 R10（凍結快照）：refresh 應 resumable 跳過
        (self.raw / "results" / "2026-10.json").write_text(
            json.dumps({"season": "2026", "round": "10", "Results": []}), encoding="utf-8")

    def test_quiet_skip_future_race(self):
        # R11 排定日在 today 之後 → 不打 results API、new_rounds 空（安靜跳過）
        f = FakeFetcher([_race(10, "2026-07-01"), _race(11, "2026-12-31")])
        new, _ = refresh_mod.refresh(2026, f, raw_dir=self.raw,
                                     today=refresh_mod.datetime.date(2026, 7, 24))
        self.assertEqual(new, [])
        self.assertNotIn("2026/11/results", f.calls)

    def test_quiet_skip_results_not_yet_ingested(self):
        # R11 排定日已過但 jolpica 尚未提供賽果（空 Results）→ new_rounds 空、不重試轟炸
        f = FakeFetcher([_race(11, "2026-07-20")],
                        results_by_round={11: None})
        new, _ = refresh_mod.refresh(2026, f, raw_dir=self.raw,
                                     today=refresh_mod.datetime.date(2026, 7, 24))
        self.assertEqual(new, [])
        self.assertEqual(f.calls.count("2026/11/results"), 1)  # 只試一次

    def test_new_result_written_format_compatible(self):
        f = FakeFetcher([_race(11, "2026-07-20")],
                        results_by_round={11: _race(11, "2026-07-20")})
        new, sched_changed = refresh_mod.refresh(2026, f, raw_dir=self.raw,
                                                 today=refresh_mod.datetime.date(2026, 7, 24))
        self.assertEqual(new, [11])
        out = self.raw / "results" / "2026-11.json"
        self.assertTrue(out.exists())
        d = json.loads(out.read_text(encoding="utf-8"))
        # 與 fetch-f1-history 落地格式一致：race dict + Results list + _meta.backfill
        for k in ("season", "round", "raceName", "Circuit", "date", "Results"):
            self.assertIn(k, d)
        self.assertTrue(d["_meta"]["backfill"])
        self.assertIsInstance(d["Results"], list)
        self.assertEqual(d["Results"][0]["Driver"]["driverId"], "hamilton")
        # 標準榜也刷新
        self.assertTrue((self.raw / "standings" / "driver-2026.json").exists())

    def test_idempotent_second_run_is_noop(self):
        f1 = FakeFetcher([_race(11, "2026-07-20")],
                         results_by_round={11: _race(11, "2026-07-20")})
        refresh_mod.refresh(2026, f1, raw_dir=self.raw,
                            today=refresh_mod.datetime.date(2026, 7, 24))
        b1 = (self.raw / "results" / "2026-11.json").read_bytes()
        # 第二次：R11 已存在 → resumable 跳過 → new 空、檔案 byte-identical
        f2 = FakeFetcher([_race(11, "2026-07-20")],
                         results_by_round={11: _race(11, "2026-07-20")})
        new2, _ = refresh_mod.refresh(2026, f2, raw_dir=self.raw,
                                      today=refresh_mod.datetime.date(2026, 7, 24))
        self.assertEqual(new2, [])
        self.assertEqual((self.raw / "results" / "2026-11.json").read_bytes(), b1)

    def test_main_invariants_fail_blocks_with_exit_1(self):
        # 有新賽果但不變量未過 → main exit 1（不進入頁面重生）
        orig_refresh = refresh_mod.refresh
        orig_verify = refresh_mod._rebuild_and_verify
        refresh_mod.refresh = lambda *a, **k: ([11], False)
        refresh_mod._rebuild_and_verify = lambda db: False
        old_argv = sys.argv
        sys.argv = ["refresh-f1-current.py"]
        try:
            self.assertEqual(refresh_mod.main(), 1)
        finally:
            refresh_mod.refresh = orig_refresh
            refresh_mod._rebuild_and_verify = orig_verify
            sys.argv = old_argv

    def test_main_no_new_data_exit_0(self):
        orig_refresh = refresh_mod.refresh
        refresh_mod.refresh = lambda *a, **k: ([], False)
        old_argv = sys.argv
        sys.argv = ["refresh-f1-current.py"]
        try:
            self.assertEqual(refresh_mod.main(), 0)
        finally:
            refresh_mod.refresh = orig_refresh
            sys.argv = old_argv


# ============================================================
# 5. update-racing dormant 接線（published gate + 分層 fail）
# ============================================================

ur = _load("update_racing", "update-racing.py")


class UpdateRacingDormantTests(unittest.TestCase):
    def test_config_published_is_false_now(self):
        self.assertFalse(ur._encyclopedia_published(),
                         "M7 交付時百科必須維持全暗（published:false）")

    def test_published_false_step_is_noop(self):
        # published:false → encyclopedia_step 不呼叫任何 subprocess、不寫 sitemap part
        calls = []
        orig = ur.subprocess.run
        ur.subprocess.run = lambda *a, **k: calls.append(a) or _Ret(0)
        try:
            ur.encyclopedia_step(full=False)
        finally:
            ur.subprocess.run = orig
        self.assertEqual(calls, [], "published:false 時百科段不得執行任何子步驟")

    def test_published_false_writes_no_encyclopedia_sitemap_parts(self):
        parts = ROOT / "data" / "sitemap-parts"
        before = {p.name for p in parts.glob("*.txt")}
        ur.encyclopedia_step(full=False)
        after = {p.name for p in parts.glob("*.txt")}
        # 不新增 seasons.txt / drivers.txt（byte-identical：sitemap 輸入不變）
        self.assertNotIn("seasons.txt", after - before)
        self.assertNotIn("drivers.txt", after - before)

    def test_encyclopedia_failure_does_not_touch_FAILED(self):
        # 分層 fail：published:true 但百科子步驟失敗 → 不進 FAILED、不擋週更三頁部署
        orig_pub = ur._encyclopedia_published
        orig_run = ur.subprocess.run
        ur._encyclopedia_published = lambda: True
        ur.subprocess.run = lambda *a, **k: _Ret(1)  # refresh 直接失敗
        ur.FAILED.clear()
        try:
            ur.encyclopedia_step(full=False)
            self.assertEqual(ur.FAILED, [], "百科層失敗不得進入週更 FAILED（不擋 fail-fast 部署）")
        finally:
            ur._encyclopedia_published = orig_pub
            ur.subprocess.run = orig_run

    def test_full_flag_passed_through(self):
        # published:true + full=True → regen-encyclopedia.py 帶 --full
        seen = []
        orig_pub = ur._encyclopedia_published
        orig_run = ur.subprocess.run
        ur._encyclopedia_published = lambda: True
        ur.subprocess.run = lambda args, **k: seen.append(args) or _Ret(0)
        try:
            ur.encyclopedia_step(full=True)
        finally:
            ur._encyclopedia_published = orig_pub
            ur.subprocess.run = orig_run
        regen_calls = [a for a in seen if any("regen-encyclopedia.py" in str(x) for x in a)]
        self.assertTrue(regen_calls)
        self.assertTrue(any("--full" in [str(x) for x in a] for a in regen_calls),
                        "--full 應透傳給 regen-encyclopedia.py")


class _Ret:
    def __init__(self, rc):
        self.returncode = rc


if __name__ == "__main__":
    unittest.main()
