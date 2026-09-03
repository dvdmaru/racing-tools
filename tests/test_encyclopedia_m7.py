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
import os
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


re_mod = _load("regen_encyclopedia", "regen-encyclopedia.py")
refresh_mod = _load("refresh_f1_current", "refresh-f1-current.py")
# ⚠️ 一律借 regen 的模組圖，別自己再 _load 一份 racinglib/f1stats：各生成器內部各自 importlib
# 載入，自己載的那份跟它們用的不是同一個物件，patch PUB 不會生效，assets/sitemap part 會寫進
# 真的 repo 去（2026-08-03 實際踩過：跑測試在 public-racing/ 與 data/sitemap-parts/ 留下產物）。
rc, fs = re_mod.rc, re_mod.fs
dr = re_mod.dr
gs = re_mod.gs
p0 = re_mod.p0


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
        data = json.loads(dr.GOLDEN.read_text(encoding="utf-8"))
        cls.golden = data["drivers"]
        for row in cls.golden.values():
            if str(row.get("approved_by", "")).startswith("PENDING"):
                row["approved_by"] = "charlie-test"
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.approved_golden = cls.tmp / "golden.json"
        cls.approved_golden.write_text(json.dumps(data), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_every_champion_has_as_of(self):
        for did in dr.DRIVER_IDS:
            self.assertIn("as_of", self.golden[did], f"{did} 缺 as_of")
            ao = self.golden[did]["as_of"]
            self.assertIn("season", ao)
            self.assertIn("round", ao)

    def test_active_drivers_as_of_frozen_at_snapshot(self):
        for did in dr.ACTIVE_IDS:
            self.assertEqual(self.golden[did]["as_of"], {"season": 2026, "round": 11},
                             f"{did} 為現役車手，as_of 應凍結在 2026/11")

    def test_golden_gate_green_in_approved_steady_state(self):
        # 2026-08-13 Charlie 全批核准擴編裁決包後，真實 repo 狀態的 gate 應為綠。
        self.assertTrue(dr.gate_golden())

    def test_golden_gate_rejects_synthetic_pending(self):
        # PENDING 拒絕行為用合成 fixture 守（不綁 repo 暫態）：任一條 PENDING → gate 紅。
        data = json.loads(self.approved_golden.read_text(encoding="utf-8"))
        first = next(iter(data["drivers"]))
        data["drivers"][first]["approved_by"] = "PENDING-charlie"
        bad = self.tmp / "golden-pending.json"
        bad.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(dr.gate_golden(golden_path=bad))

    def test_golden_gate_green_after_synthetic_approval(self):
        self.assertTrue(dr.gate_golden(golden_path=self.approved_golden))

    def test_new_result_does_not_break_gate(self):
        # 合成塞活躍車手 as_of 之後的新賽果（2026 R12）→ 全量現值變、as_of 截斷值不變 → gate 仍綠
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        db = _copy_db(tmp)
        _inject_result(db, "hamilton", 2026, 12, position_text="1")
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
        try:
            # 全量現值：勝場 +1
            full = fs.driver_career_db("hamilton", con)
            self.assertEqual(full["wins"]["value"], self.golden["hamilton"]["wins"] + 1)
            # as_of 截斷（2026/11）：不含 R12 → 與 golden 一致 → gate 綠
            trunc = fs.driver_career_db("hamilton", con, as_of={"season": 2026, "round": 11})
            self.assertEqual(trunc["wins"]["value"], self.golden["hamilton"]["wins"])
            self.assertTrue(dr.gate_golden(con=con, golden_path=self.approved_golden),
                            "新賽果（as_of 之後）不得使 golden gate 變紅")
        finally:
            con.close()

    def test_tampering_within_as_of_window_reddens_gate(self):
        # 篡改 as_of<= 的歷史（塞一場 2005 勝場給 hamilton，2005<=2026/11）→ 截斷值變 → gate 紅
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        db = _copy_db(tmp)
        _inject_result(db, "hamilton", 2005, 99, position_text="1")
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
        try:
            self.assertFalse(dr.gate_golden(con=con, golden_path=self.approved_golden),
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
        # ⚠️ 一律用 re_mod.pub_override：自己列 PUB 名單會漏（漏過 ci＝circuits，
        # 害全套測試把 79 個賽道頁寫進版控產物目錄）。新增 owner 只改 PAGE_OWNERS。
        self._pub_ctx = re_mod.pub_override(self.pub)
        self._pub_ctx.__enter__()
        self.dbA = _copy_db(self.tmp)

    def tearDown(self):
        self._pub_ctx.__exit__(None, None, None)

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
        self.assertEqual(res["changed_constructors"], [])
        self.assertFalse(res["index_seasons"])
        self.assertFalse(res["index_drivers"])
        self.assertFalse(res["index_constructors"])
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
        # 變更集合精確：當季 2026、車手 hamilton、其車隊 Mercedes 與三個索引。
        self.assertEqual(res["changed_years"], [2026])
        self.assertEqual(res["changed_drivers"], ["hamilton"])
        self.assertTrue(res["index_seasons"])
        self.assertTrue(res["index_drivers"])
        self.assertEqual(res["changed_constructors"], ["mercedes"])
        self.assertTrue(res["index_constructors"])
        # 賽道線：2026 第 11 站在匈牙利站，多一個本賽道勝場 → 該賽道頁與賽道索引都要變。
        # ☠️ 2026-09-03 之前這三行不存在，而且下面的預期集合也沒有 circuits——不是因為
        # 賽道頁真的沒變，是因為 ci.PUB 沒被重導，賽道頁被寫到**版控裡的產物目錄**去了，
        # 這個暫存目錄裡自然看不到。斷言看起來全綠，其實整條賽道線不在射程內。
        self.assertEqual(res["changed_circuits"], ["hungaroring"])
        self.assertTrue(res["index_circuits"])

        rewritten = {str(p.relative_to(self.pub)) for p, (m, _) in snap.items()
                     if p.stat().st_mtime_ns != m}
        # 每個被重寫的頁只能屬於預期集合
        def _expected(rel):
            return (rel.startswith("seasons/2026/") or rel == "seasons/index.html"
                    or rel == "drivers/index.html" or rel == "drivers/hamilton/index.html"
                    or rel == "constructors/index.html"
                    or rel == "constructors/mercedes/index.html"
                    or rel == "circuits/index.html"
                    or rel == "circuits/hungaroring/index.html")
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
        # 非受影響賽道頁零重寫（只有匈牙利站該動）
        for p, (m, b) in snap.items():
            rel = str(p.relative_to(self.pub))
            if rel.startswith("circuits/") and rel not in (
                    "circuits/index.html", "circuits/hungaroring/index.html"):
                self.assertEqual(p.stat().st_mtime_ns, m, f"非受影響賽道頁被重寫：{rel}")
                self.assertEqual(p.read_bytes(), b, f"非受影響賽道頁內容變動：{rel}")
        # 預期集合確有重寫（2026 總覽 + hamilton 頁 + 匈牙利站 + 索引）
        self.assertIn("seasons/2026/index.html", rewritten)
        self.assertIn("drivers/hamilton/index.html", rewritten)
        self.assertIn("drivers/index.html", rewritten)
        self.assertIn("constructors/mercedes/index.html", rewritten)
        self.assertIn("constructors/index.html", rewritten)
        self.assertIn("circuits/hungaroring/index.html", rewritten)
        self.assertIn("circuits/index.html", rewritten)

    def test_full_flag_ignores_fingerprints(self):
        self._full_build()
        con = self._con(self.dbA)
        try:
            res = re_mod.selective_regen(con, full=True, fp_path=self.fp)
        finally:
            con.close()
        self.assertEqual(len(res["changed_years"]), gs.LAST_YEAR - gs.FIRST_YEAR + 1)
        self.assertEqual(len(res["changed_drivers"]), len(dr.DRIVER_IDS))
        self.assertEqual(len(res["changed_constructors"]), len(re_mod.CONSTRUCTOR_IDS))

    def test_publish_writes_sitemap_parts(self):
        # ☠️ 2026-09-03 之前這個測試寫進**版控裡**的 data/sitemap-parts/，再手動還原
        # 存下來的三個檔（seasons／drivers／constructors）——publish 區塊其實寫四個，
        # circuits 不在那份手寫清單裡，於是每跑一次全套測試就把 circuits.txt 永久改寫一次。
        # 現在整段 save/restore 拿掉：setUp 的 pub_override 已把 part 目錄一起導到 tmp。
        # 測試不該碰真目錄，即使會還原也不行——行程中途死掉就留髒，而且 mtime churn 會讓
        # mtime 型探針失去判別力（見 TestsDoNotTouchRepoArtifactsTests）。
        parts = rc.sitemap_parts_dir()
        self.assertFalse(parts.is_relative_to(ROOT / "data"),
                         f"part 目錄沒被導開，還指著版控目錄：{parts}")
        sp, dp, cp = parts / "seasons.txt", parts / "drivers.txt", parts / "constructors.txt"
        con = self._con(self.dbA)
        try:
            re_mod.selective_regen(con, full=True, fp_path=self.fp, publish=True)
        finally:
            con.close()
        self.assertTrue(sp.exists() and dp.exists() and cp.exists())
        s_urls = sp.read_text(encoding="utf-8").splitlines()
        self.assertIn(f"{rc.BASE}/seasons/", s_urls)
        self.assertIn(f"{rc.BASE}/seasons/2002/rounds/1/", s_urls)
        d_urls = dp.read_text(encoding="utf-8").splitlines()
        self.assertIn(f"{rc.BASE}/drivers/", d_urls)
        self.assertEqual(len([u for u in d_urls if u != f"{rc.BASE}/drivers/"]),
                         len(dr.DRIVER_IDS))
        # 車隊：索引 URL 必須在（沒有它 /constructors/ 就是進不了 sitemap 的孤兒區）
        c_urls = cp.read_text(encoding="utf-8").splitlines()
        self.assertIn(f"{rc.BASE}/constructors/", c_urls)
        self.assertEqual(len([u for u in c_urls if u != f"{rc.BASE}/constructors/"]),
                         len(re_mod.CONSTRUCTOR_IDS))
        # circuits 也是 publish 區塊的一員——它當年被漏掉正是這個測試會弄髒 repo 的原因，
        # 所以連同斷言一起補上，避免又變成「寫了但沒人驗」的那一個。
        self.assertIn(f"{rc.BASE}/circuits/",
                      (parts / "circuits.txt").read_text(encoding="utf-8").splitlines())


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
        orig_sync = refresh_mod.sync_whole_db_files
        refresh_mod.refresh = lambda *a, **k: ([11], False)
        refresh_mod._rebuild_and_verify = lambda db: False
        # sync_whole_db_files 用真 Fetcher 打網路——不 mock 會讓本測試逃逸到真實 DNS
        # （離線環境直接 ERROR，線上環境則白打一輪外部請求）。
        refresh_mod.sync_whole_db_files = lambda *a, **k: ([], [])
        old_argv = sys.argv
        sys.argv = ["refresh-f1-current.py"]
        try:
            self.assertEqual(refresh_mod.main(), 1)
        finally:
            refresh_mod.refresh = orig_refresh
            refresh_mod._rebuild_and_verify = orig_verify
            refresh_mod.sync_whole_db_files = orig_sync
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
    """published gate 的雙向行為。

    ☠️ 2026-08-03 改寫：這三條原本直接斷言「現在的設定必須是 published:false」，
    那是 M7 交付當下的正確守門（確保 dormant wiring 沒有提前點亮），但**它把測試綁死在
    一個遲早要改的設定值上**——公開日一到，測試就會紅，而紅的原因是「我們照計畫公開了」。
    這種測試只能被刪掉，於是它守的東西也一起消失。

    改成**兩個方向都測、而且不依賴當下的設定值**：把 flag patch 成 False 驗全暗、
    patch 成 True 驗真的會動。這樣不管站上是公開還是未公開，gate 本身的行為都有人守。
    """

    def _run_step_with(self, published):
        calls = []
        orig_pub, orig_run = ur._encyclopedia_published, ur.subprocess.run
        ur._encyclopedia_published = lambda: published
        ur.subprocess.run = lambda *a, **k: calls.append(a) or _Ret(0)
        try:
            ur.encyclopedia_step(full=False)
        finally:
            ur._encyclopedia_published, ur.subprocess.run = orig_pub, orig_run
        return calls

    def test_missing_or_broken_config_is_treated_as_unpublished(self):
        """default-deny：設定檔讀不到／壞掉一律當未公開，絕不 fail-open 把百科點亮。"""
        orig = ur.ROOT
        ur.ROOT = pathlib.Path(tempfile.mkdtemp())   # 沒有 config/encyclopedia.json
        try:
            self.assertFalse(ur._encyclopedia_published())
        finally:
            shutil.rmtree(ur.ROOT, ignore_errors=True)
            ur.ROOT = orig

    def test_published_false_step_is_noop(self):
        self.assertEqual(self._run_step_with(False), [],
                         "published:false 時百科段不得執行任何子步驟")

    def test_published_true_step_actually_runs(self):
        """反向：全暗測試若沒有這條配對，實作可以永遠不動而三條測試全綠。"""
        self.assertTrue(self._run_step_with(True),
                        "published:true 時百科段必須真的執行子步驟")

    def test_published_false_writes_no_encyclopedia_sitemap_parts(self):
        parts = ROOT / "data" / "sitemap-parts"
        before = {p.name for p in parts.glob("*.txt")}
        # ⚠️ 一定要 patch 成 False 再跑：published:true 時直接呼叫會**真的觸發全量重生**
        # （改寫前這條就是這樣，只因為 part 檔早已存在才沒被發現）。
        self._run_step_with(False)
        after = {p.name for p in parts.glob("*.txt")}
        for name in ("seasons.txt", "drivers.txt", "constructors.txt"):
            self.assertNotIn(name, after - before)

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


# ============================================================
# 6. 測試不得寫進版控產物（2026-09-03；2026-08-03 同型事故的復發）
# ============================================================

class TestsDoNotTouchRepoArtifactsTests(unittest.TestCase):
    """釘住：全量重生在 pub_override 之下，一個位元組都不准落到**任何**版控輸出目錄。

    病灶（2026-09-03，同一族三犯）：
      ① 測試把 PUB 逐一列名重導，漏了 ci（circuits owner）→ 每跑一次全套測試就有 79 個
         賽道頁被寫進版控產物，而且是測試合成資料庫產生的（含捏造的共同優勝者）。
      ② `selective_regen(publish=True)` 寫四個 sitemap part，但當年那個測試的手動還原清單
         只有三個 → circuits.txt 每跑一次就被永久改寫一次。
      ③ 探針的掃描範圍被手寫成只有 public-racing/ → 上面②在探針下完全隱形。

    ⭐ 射程一律從 `re_mod.OUTPUT_ROOTS` 推導，**不在這裡列舉目錄**——斷言若自己列舉，
    它就是第四份手寫清單，下一個輸出目標照樣會漏。
    """

    # 攔截點清單（單一來源）：(物件, 屬性名, 目的地是第幾個引數)。
    # os.replace／os.rename／shutil.move 都是 (src, dst)＝目的地在第 2 個。
    # ⭐ 攔截測試與「攔截清單把關」那道掃描**都從這一份推導**——實測過：這兩處若各寫一份，
    # 把攔截清單縮小而忘了同步縮小掃描的白名單，掃描就不會叫，缺陷完全隱形。
    _INTERCEPTED_WRITES = (
        (pathlib.Path, "write_text", 0), (pathlib.Path, "write_bytes", 0),
        (pathlib.Path, "rename", 1), (pathlib.Path, "replace", 1),
        (os, "replace", 1), (os, "rename", 1),
        (shutil, "move", 1), (shutil, "copy", 1), (shutil, "copy2", 1),
    )

    def _real_roots(self):
        """尚未重導時的真實輸出根目錄（＝版控裡那幾個）。"""
        return {name: getter() for name, getter in re_mod.OUTPUT_ROOTS.items()}

    @staticmethod
    def _snap(root):
        root = pathlib.Path(root)
        if not root.exists():
            return {}
        return {p: (p.stat().st_mtime_ns, p.stat().st_size)
                for p in root.rglob("*") if p.is_file()}

    def test_full_regen_under_override_leaves_repo_artifacts_untouched(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        pub = tmp / "pub"
        real = self._real_roots()
        self.assertIn("sitemap_parts", real,
                      "OUTPUT_ROOTS 少了 sitemap_parts，本測試的射程會退回只驗頁面")
        before = {name: self._snap(root) for name, root in real.items()}

        con = sqlite3.connect(str(_copy_db(tmp)))
        con.row_factory = sqlite3.Row
        redirected = {}
        try:
            # publish=True 才會寫 sitemap part——用最大射程跑，否則驗不到②那一型。
            with re_mod.pub_override(pub):
                # 重導後的實際路徑一律從註冊表取回，不在測試裡寫死目錄名。
                redirected = {name: pathlib.Path(getter())
                              for name, getter in re_mod.OUTPUT_ROOTS.items()}
                re_mod.selective_regen(con, full=True, fp_path=tmp / "fp.json",
                                       publish=True)
        finally:
            con.close()

        for name, root in real.items():
            after = self._snap(root)
            touched = sorted(str(p) for p, v in after.items() if before[name].get(p) != v)
            added = sorted(str(p) for p in after if p not in before[name])
            self.assertEqual(touched, [], f"重生改寫了版控輸出（{name}）：{touched[:5]}")
            self.assertEqual(added, [], f"重生新增了版控輸出（{name}）：{added[:5]}")

        # 陽性對照：證明上面的「零改動」不是因為根本沒生成任何東西。
        # 少了這一段，把 selective_regen 改成 return 也會全綠。
        for kind in ("seasons", "drivers", "constructors", "circuits"):
            self.assertTrue(any((pub / kind).rglob("index.html")),
                            f"重生沒有產出 {kind} 頁，前面的零改動不成立")
        # 陽性對照（sitemap part 那一路）：part 檔要真的落在被導開的目錄裡。
        parts = redirected["sitemap_parts"]
        self.assertTrue(any(parts.glob("*.txt")),
                        f"publish=True 沒有把 sitemap part 寫到被導開的目錄 {parts}，"
                        "前面的零改動不成立")

    def test_no_write_target_lands_inside_the_repo_during_regen(self):
        """攔寫入端本身：重生期間每一個「要寫到哪」都不准落在 repo 裡。

        為什麼還要這一道（前兩道不夠）：
        ・「零改動」那道靠比 mtime，對**內容相同就跳過**的寫入端（`write_sitemap_part`）
          是盲的——目標指著版控目錄但內容剛好一樣時它靜默 no-op，mtime 不動、測試全綠。
          實測：把 pub_override 的 parts 重導拿掉，那道測試仍然全綠。
        ・「重導」那道只驗 `OUTPUT_ROOTS` 裡列到的目標，**註冊表本身漏一個就驗不到**。
        這一道不依賴 mtime、也不依賴註冊表完整，所以能擋住「新增了輸出目標又忘了註冊」。

        ⚠️ 已知邊界（三條，都是「這道 gate 主張的範圍」的一部分，不是缺點）：
        ① 攔截點清單見 `_INTERCEPTED_WRITES`；走 `open(..., "w")` 的寫入攔不到。
        ② **只涵蓋本行程**。測試若用 `subprocess.run` 真的跑生成器，寫入發生在子行程，
           monkeypatch 完全看不到（姊妹站 baseball 2026-09-03 實測：同樣攔九個原語跑全套
           只抓到 6 次，2,866 個被寫的檔一個都沒看到，因為它的洩漏正是子行程）。
           racing 目前唯一會 spawn 腳本的測試是 `test_crosscheck` 跑
           `crosscheck-wikipedia.py --gate-only`，該分支在任何寫入之前就 return（已逐行查過），
           所以沒有暴露；但**新增會 spawn 腳本的測試時，這道 gate 不會替你把關**。
        ③ 只涵蓋 `selective_regen` 這一段，不涵蓋 build-articles 等其他管線。
        跨行程的那一層目前靠**手動**的整棵工作樹哨兵探針（在「輸出已知過期」狀態下跑全套，
        比 content-hash 與 mtime），不是自動測試——這一點也要算進「這道 gate 沒守到什麼」。
        ☠️ **攔截點清單本身也是一份手寫清單**（＝本檔一再踩到的那個形狀的遞歸實例）：
        原子寫入（寫 tmp 再 `os.replace`）是這類攔截的標準死角，而且它是**好的工程實踐**，
        所以愈成熟的程式愈會踩到——可靠性做得好的那條寫入路徑剛好是攔不到的那條。
        因此清單不能只靠「記得加」：`test_regen_path_uses_only_intercepted_write_primitives`
        會靜態掃描重生路徑上的腳本，用到清單以外的寫入原語就當場紅燈。
        """
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        pub = tmp / "pub"
        repo = pathlib.Path(ROOT).resolve()
        seen = []

        patches = self._INTERCEPTED_WRITES
        originals = [(obj, name, getattr(obj, name)) for obj, name, _ in patches]

        def make_spy(fn, dest_idx):
            def spy(*a, **k):
                if len(a) > dest_idx:
                    seen.append(pathlib.Path(a[dest_idx]).resolve())
                return fn(*a, **k)
            return spy

        orig_part = re_mod.rc.write_sitemap_part

        def spy_part(owner, urls):
            # 這一支即使不實際寫檔也要記——它的「目標目錄」才是我們要驗的東西
            # （內容相同就跳過，真正的寫入不會發生，但目標指著哪裡才是重點）。
            seen.append((re_mod.rc.sitemap_parts_dir() / f"{owner}.txt").resolve())
            return orig_part(owner, urls)

        con = sqlite3.connect(str(_copy_db(tmp)))
        con.row_factory = sqlite3.Row
        for obj, name, dest_idx in patches:
            setattr(obj, name, make_spy(getattr(obj, name), dest_idx))
        re_mod.rc.write_sitemap_part = spy_part
        try:
            with re_mod.pub_override(pub):
                re_mod.selective_regen(con, full=True, fp_path=tmp / "fp.json",
                                       publish=True)
        finally:
            for obj, name, fn in originals:
                setattr(obj, name, fn)
            re_mod.rc.write_sitemap_part = orig_part
            con.close()

        inside = sorted({str(p) for p in seen if p.is_relative_to(repo)
                         and not p.is_relative_to(tmp.resolve())})
        self.assertEqual(inside, [], f"重生把寫入目標指向 repo 內：{inside[:5]}")
        # 陽性對照：spy 真的攔到東西了，否則「零命中」只是因為沒攔到任何寫入。
        self.assertGreater(len(seen), 100,
                           f"spy 只攔到 {len(seen)} 次寫入，太少＝攔截沒生效，"
                           "前面的零命中不成立")

    def test_regen_path_uses_only_intercepted_write_primitives(self):
        """重生路徑上的腳本只准用「攔得到」的寫入原語。

        ☠️ 這道是給**攔截點清單本身**把關的——上一道的攔截清單是手寫的，而
        `os.replace`（寫 tmp 再原子換上）恰恰是這類攔截的標準死角，**而且它是好的工程實踐**，
        所以愈成熟的程式愈可能改用它。真的改了而沒有同步擴充攔截清單，上一道會安靜失效：
        它仍然全綠，只是什麼都沒攔到。

        racing 目前零原子寫入（實查 `os.replace`／`os.rename`／`shutil.move` 皆零命中），
        所以這是**潛在**而非現行的洞。這道測試的作用就是讓它在變成現行的洞那一刻紅燈。

        掃描對象由模組圖推導（不手寫檔名清單）：`PAGE_OWNERS` 與 regen 自己的原始碼。
        """
        import types
        # ⭐ 白名單從攔截清單推導，不另寫一份（實測：兩份各寫時，縮小攔截清單而忘了縮小
        # 白名單，這道掃描就不會叫——缺陷完全隱形）。
        intercepted = {name for _, name, _ in self._INTERCEPTED_WRITES}
        # 已知會繞過攔截的寫入原語。用到就必須先擴充上一道的 patches 清單。
        risky = {
            "os.replace": "os.replace", "os.rename": "os.rename",
            "shutil.move": "shutil.move", "shutil.copy": "shutil.copy",
            "shutil.copy2": "shutil.copy2", "os.link": "os.link",
            "os.symlink": "os.symlink", "os.truncate": "os.truncate",
        }
        sources = {}
        for name, obj in vars(re_mod).items():
            if isinstance(obj, types.ModuleType) and obj in re_mod.PAGE_OWNERS:
                f = getattr(obj, "__file__", None)
                if f:
                    sources[name] = pathlib.Path(f)
        sources["regen_encyclopedia"] = pathlib.Path(re_mod.__file__)
        self.assertGreaterEqual(len(sources), 5,
                                f"只掃到 {len(sources)} 份原始碼，模組圖推導壞了，"
                                "本測試等於沒掃")

        offenders = []
        for mod, path in sorted(sources.items()):
            src = path.read_text(encoding="utf-8")
            code = "\n".join(l for l in src.split("\n")
                             if not l.lstrip().startswith("#"))
            for pattern, label in risky.items():
                if pattern in code and label.split(".")[-1] not in intercepted:
                    offenders.append(f"{mod}({path.name}) 用了 {label}")
        self.assertEqual(offenders, [],
                         "重生路徑用了攔截清單以外的寫入原語，"
                         "上一道攔截測試會安靜失效——請先把它加進 patches："
                         f"{offenders}")

    def test_pub_override_redirects_every_registered_output_root(self):
        """`OUTPUT_ROOTS` 裡每一個輸出根目錄，在 pub_override 之下都必須指到 target 底下。

        這道測試補的是「註冊表加了新目標，但 pub_override 忘了重導它」——
        那種情況下上面那道測試會拿真目錄當 target 去比對，看起來仍然全綠。
        """
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        target = tmp / "pub"
        outside = []
        with re_mod.pub_override(target):
            for name, getter in re_mod.OUTPUT_ROOTS.items():
                root = pathlib.Path(getter()).resolve()
                if not root.is_relative_to(tmp.resolve()):
                    outside.append((name, str(root)))
        self.assertEqual(outside, [],
                         f"pub_override 沒有重導這些已註冊的輸出根目錄：{outside}")

    def test_page_owners_covers_every_module_with_a_pub(self):
        """PAGE_OWNERS 要涵蓋 regen 模組圖裡每一個有 PUB 屬性的生成器模組。

        新增一個 owner 卻忘了加進 PAGE_OWNERS，pub_override 就會再漏一次——
        這道測試就是為了讓那個「忘了」當場紅燈，而不是等到產物被偷寫。
        """
        import types
        have_pub = {name for name, obj in vars(re_mod).items()
                    if isinstance(obj, types.ModuleType) and hasattr(obj, "PUB")}
        covered = {name for name, obj in vars(re_mod).items()
                   if isinstance(obj, types.ModuleType) and obj in re_mod.PAGE_OWNERS}
        self.assertEqual(have_pub - covered, set(),
                         f"有 PUB 卻不在 PAGE_OWNERS：{sorted(have_pub - covered)}")


if __name__ == "__main__":
    unittest.main()
