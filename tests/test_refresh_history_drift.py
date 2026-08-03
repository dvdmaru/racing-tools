#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""refresh-f1-current「全庫單檔歷史零漂移」驗證的反向測試（鐵則① 2026-08-03 修訂）。

背景：舊鐵則①寫「只碰當季檔、歷史零改動」，但 db 的三個關鍵來源本質上都是**全庫單檔**，
當季有新資料時一定要動——entities/races.json（賽曆）、entities/status.json（I8 oracle）、
drivers/<id>-results.json（I5 發布側生涯檔）。因為被禁止，這支腳本就乾脆不動，於是它
「成功」跑完但 db 的賽曆永遠停在 backfill 當時（2026 由 22 站變 23 站是人手動補的）。
修法＝放寬成「可以更新，但落地前必須程式化驗證歷史零漂移」。

**全綠的 gate 分不出「乾淨」和「斷言壞掉」**，所以每一條驗證都要有一個證明它會擋的測試：
  ① 只有當季變動（22→23 站）→ 通過並落地
  ② 歷史某場消失 / 內容被改（日期、賽道）→ 中止，且**原檔不得被覆蓋**
  ③ 生涯檔：當季以外的明細變動 → 中止；只有當季新增 → 通過
  ④ status.json：計數變小 / 憑空多出歷史類別 / 增量超過當季能解釋的量 → 中止
  ⑤ 抓短（len != total）→ 中止（不落地半份）
  ⑥ 沒有既有檔可比對 → 略過該檔，不憑空生成全庫單檔
  ⑦ 實體清單缺角（當季新車手不在 drivers.json）→ 補完；既有成員被改 → 中止

跑法：python3 -m unittest discover -s tests
"""
import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rf = _load("refresh_f1_current", "refresh-f1-current.py")

SEASON = 2026


def _race(season, rnd, date, circuit="circ"):
    return {"season": str(season), "round": str(rnd), "raceName": f"R{rnd} GP",
            "Circuit": {"circuitId": circuit, "circuitName": "X"},
            "date": date, "url": "u"}


# 歷史 2 季各 2 場（凍結）＋ 當季 2 場
HIST = [_race(2024, 1, "2024-03-02"), _race(2024, 2, "2024-03-16"),
        _race(2025, 1, "2025-03-09"), _race(2025, 2, "2025-03-23")]
CUR2 = [_race(SEASON, 1, "2026-03-08"), _race(SEASON, 2, "2026-07-26")]
CUR3 = CUR2 + [_race(SEASON, 3, "2026-08-23", circuit="sepang")]

STATUS_OLD = [{"statusId": "1", "status": "Finished", "count": "100"},
              {"statusId": "3", "status": "Accident", "count": "20"}]


class FakeWholeDbFetcher:
    """只實作 sync_whole_db_files 會用到的 paged()。"""

    def __init__(self, races=None, status=None, careers=None, entities=None, short=None):
        self.races = races if races is not None else HIST + CUR3
        self.status = status if status is not None else STATUS_OLD
        self.careers = careers or {}
        self.entities = entities or {}
        self.short = short or set()      # 這些 path 回報 total 比實際多（模擬抓短）
        self.calls = []

    def paged(self, path, table_key, item_key, cache=None):
        self.calls.append(path)
        if path == "races":
            items = self.races
        elif path == "status":
            items = self.status
        elif path.startswith("drivers/") and path.endswith("/results"):
            items = self.careers.get(path.split("/")[1], [])
        elif path in self.entities:
            items = self.entities[path]
        else:
            raise AssertionError(f"unexpected paged path {path}")
        return items, len(items) + (1 if path in self.short else 0)


def _result_file(rnd, statuses=("Finished",), driver="hamilton",
                 constructor="mercedes", circuit="circ"):
    return {"season": str(SEASON), "round": str(rnd), "raceName": f"R{rnd} GP",
            "Circuit": {"circuitId": circuit, "circuitName": "X"},
            "date": "2026-07-26",
            "Results": [{"number": "44", "position": str(i + 1), "positionText": str(i + 1),
                         "points": "25", "Driver": {"driverId": driver},
                         "Constructor": {"constructorId": constructor},
                         "grid": "1", "laps": "50", "status": st}
                        for i, st in enumerate(statuses)]}


class WholeDbSyncTests(unittest.TestCase):

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.raw = self.tmp / "raw"
        for sub in ("results", "entities", "drivers"):
            (self.raw / sub).mkdir(parents=True)
        self._write(self.raw / "entities" / "races.json",
                    {"Races": HIST + CUR2, "total": len(HIST + CUR2)})
        self._write(self.raw / "entities" / "status.json",
                    {"Status": STATUS_OLD, "total": len(STATUS_OLD)})
        # 當季本地賽果：R1 Finished、R2 Finished + Accident
        self._write(self.raw / "results" / f"{SEASON}-01.json", _result_file(1))
        self._write(self.raw / "results" / f"{SEASON}-02.json",
                    _result_file(2, ("Finished", "Accident")))

    def _write(self, path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**obj, "_meta": {"url": "u", "fetched_at": "t"}},
                                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _races_on_disk(self):
        return json.loads((self.raw / "entities" / "races.json").read_text())["Races"]

    def _sync(self, f):
        return rf.sync_whole_db_files(SEASON, f, self.raw, [2])

    # ① 只有當季變動（22→23 站的縮影：當季 2→3 場）→ 通過並落地
    def test_current_season_growth_lands(self):
        updated, skipped = self._sync(FakeWholeDbFetcher())
        self.assertTrue(any("races.json" in u for u in updated), updated)
        self.assertEqual(len(self._races_on_disk()), len(HIST) + 3)

    # ①b 第二次跑內容不變 → 不重寫（無 timestamp churn）
    def test_idempotent_second_run_no_rewrite(self):
        self._sync(FakeWholeDbFetcher())
        b1 = (self.raw / "entities" / "races.json").read_bytes()
        updated, _ = self._sync(FakeWholeDbFetcher())
        self.assertFalse(any("races.json" in u for u in updated))
        self.assertEqual((self.raw / "entities" / "races.json").read_bytes(), b1)

    # ② 歷史某場消失 → 中止，且原檔不得被覆蓋
    def test_vanished_historical_race_aborts(self):
        f = FakeWholeDbFetcher(races=HIST[1:] + CUR3)
        before = (self.raw / "entities" / "races.json").read_bytes()
        with self.assertRaises(rf.HistoryDriftError) as ctx:
            self._sync(f)
        self.assertIn("消失", str(ctx.exception))
        self.assertEqual((self.raw / "entities" / "races.json").read_bytes(), before,
                         "驗證未過時原檔必須原封不動")

    # ②b 歷史某場的欄位被改（日期）→ 中止（只比場次數會漏掉這種）
    def test_changed_historical_field_aborts(self):
        tampered = [dict(r) for r in HIST]
        tampered[0]["date"] = "1999-01-01"
        with self.assertRaises(rf.HistoryDriftError) as ctx:
            self._sync(FakeWholeDbFetcher(races=tampered + CUR3))
        self.assertIn("內容變動", str(ctx.exception))

    # ②c 歷史憑空多出一場 → 中止
    def test_appeared_historical_race_aborts(self):
        with self.assertRaises(rf.HistoryDriftError):
            self._sync(FakeWholeDbFetcher(races=HIST + [_race(2024, 3, "2024-04-01")] + CUR3))

    # ③ 生涯檔：當季以外的明細變動 → 中止；只有當季新增 → 通過
    def test_career_file_history_drift_aborts(self):
        self._write(self.raw / "drivers" / "hamilton-results.json",
                    {"driverId": "hamilton", "total": 3, "Races": HIST[:2] + CUR2[:1]})
        drifted = [dict(r) for r in HIST[:2]]
        drifted[0]["raceName"] = "改過的名字"
        with self.assertRaises(rf.HistoryDriftError):
            self._sync(FakeWholeDbFetcher(
                careers={"hamilton": drifted + CUR2}))

    def test_career_file_current_season_growth_lands(self):
        self._write(self.raw / "drivers" / "hamilton-results.json",
                    {"driverId": "hamilton", "total": 3, "Races": HIST[:2] + CUR2[:1]})
        updated, _ = self._sync(FakeWholeDbFetcher(careers={"hamilton": HIST[:2] + CUR2}))
        self.assertTrue(any("hamilton-results.json" in u for u in updated), updated)
        d = json.loads((self.raw / "drivers" / "hamilton-results.json").read_text())
        self.assertEqual(len(d["Races"]), 4)

    # ④ status.json：三條方向性斷言各有一個反例
    def test_status_count_decrease_aborts(self):
        lower = [{"statusId": "1", "status": "Finished", "count": "99"},
                 {"statusId": "3", "status": "Accident", "count": "20"}]
        with self.assertRaises(rf.HistoryDriftError) as ctx:
            self._sync(FakeWholeDbFetcher(status=lower))
        self.assertIn("減為", str(ctx.exception))

    def test_status_phantom_history_category_aborts(self):
        phantom = STATUS_OLD + [{"statusId": "9", "status": "Withdrew", "count": "7"}]
        with self.assertRaises(rf.HistoryDriftError) as ctx:
            self._sync(FakeWholeDbFetcher(status=phantom))
        self.assertIn("Withdrew", str(ctx.exception))

    def test_status_increment_beyond_current_season_aborts(self):
        # 本地當季 Finished 只有 2 列，API 卻多了 5 → 增量無法被當季解釋
        toobig = [{"statusId": "1", "status": "Finished", "count": "105"},
                  {"statusId": "3", "status": "Accident", "count": "20"}]
        with self.assertRaises(rf.HistoryDriftError) as ctx:
            self._sync(FakeWholeDbFetcher(status=toobig))
        self.assertIn("增量", str(ctx.exception))

    def test_status_increment_within_current_season_lands(self):
        ok = [{"statusId": "1", "status": "Finished", "count": "102"},
              {"statusId": "3", "status": "Accident", "count": "21"}]
        updated, _ = self._sync(FakeWholeDbFetcher(status=ok))
        self.assertTrue(any("status.json" in u for u in updated), updated)

    def test_status_new_category_explained_by_current_season_lands(self):
        # 當季 R2 本地有 Accident；若新類別在本地當季賽果裡出現得了，就不算憑空
        self._write(self.raw / "results" / f"{SEASON}-02.json",
                    _result_file(2, ("Finished", "Engine")))
        ok = STATUS_OLD + [{"statusId": "5", "status": "Engine", "count": "1"}]
        updated, _ = self._sync(FakeWholeDbFetcher(status=ok))
        self.assertTrue(any("status.json" in u for u in updated), updated)

    # ⑤ 抓短（len != total）→ 中止，不落地半份
    def test_short_fetch_aborts(self):
        before = (self.raw / "entities" / "races.json").read_bytes()
        with self.assertRaises(rf.HistoryDriftError) as ctx:
            self._sync(FakeWholeDbFetcher(short={"races"}))
        self.assertIn("抓短", str(ctx.exception))
        self.assertEqual((self.raw / "entities" / "races.json").read_bytes(), before)

    # ⑥ 沒有既有檔可比對 → 略過，不憑空生成全庫單檔
    def test_missing_baseline_file_is_skipped_not_created(self):
        (self.raw / "entities" / "races.json").unlink()
        f = FakeWholeDbFetcher()
        updated, skipped = self._sync(f)
        self.assertTrue(any("races.json" in s for s in skipped), skipped)
        self.assertFalse((self.raw / "entities" / "races.json").exists())
        self.assertNotIn("races", f.calls, "沒有基準就連抓都不該抓")

    # ⑦ 實體清單缺角 → 補完（既有成員零變動）
    def test_entity_gap_is_filled(self):
        self._write(self.raw / "results" / f"{SEASON}-02.json",
                    _result_file(2, ("Finished",), driver="rookie"))
        self._write(self.raw / "entities" / "drivers.json",
                    {"Drivers": [{"driverId": "hamilton", "familyName": "H"}], "total": 1})
        f = FakeWholeDbFetcher(entities={"drivers": [
            {"driverId": "hamilton", "familyName": "H"},
            {"driverId": "rookie", "familyName": "R"}]})
        updated, _ = self._sync(f)
        self.assertTrue(any("drivers.json" in u for u in updated), updated)
        d = json.loads((self.raw / "entities" / "drivers.json").read_text())
        self.assertEqual({x["driverId"] for x in d["Drivers"]}, {"hamilton", "rookie"})

    # ⑦b 實體清單既有成員被改 → 中止（只准新增）
    def test_entity_existing_member_change_aborts(self):
        self._write(self.raw / "results" / f"{SEASON}-02.json",
                    _result_file(2, ("Finished",), driver="rookie"))
        self._write(self.raw / "entities" / "drivers.json",
                    {"Drivers": [{"driverId": "hamilton", "familyName": "H"}], "total": 1})
        f = FakeWholeDbFetcher(entities={"drivers": [
            {"driverId": "hamilton", "familyName": "改過"},
            {"driverId": "rookie", "familyName": "R"}]})
        with self.assertRaises(rf.HistoryDriftError) as ctx:
            self._sync(f)
        self.assertIn("內容變動", str(ctx.exception))

    # ⑦c 沒有缺角時完全不打實體端點（平時零請求）
    def test_no_entity_request_when_nothing_missing(self):
        self._write(self.raw / "entities" / "drivers.json",
                    {"Drivers": [{"driverId": "hamilton"}], "total": 1})
        f = FakeWholeDbFetcher()
        self._sync(f)
        self.assertNotIn("drivers", f.calls)


class MainAbortsOnDriftTests(unittest.TestCase):
    """main()：漂移驗證未過 → exit 1，且不重建 db、不進入頁面重生。"""

    def test_main_returns_1_on_drift(self):
        orig_refresh, orig_sync = rf.refresh, rf.sync_whole_db_files
        orig_verify, orig_fetcher = rf._rebuild_and_verify, rf.fh.Fetcher
        rebuilt = []
        rf.refresh = lambda *a, **k: ([2], False)
        rf.fh.Fetcher = lambda *a, **k: object()

        def boom(*a, **k):
            raise rf.HistoryDriftError("測試用漂移")
        rf.sync_whole_db_files = boom
        rf._rebuild_and_verify = lambda db: rebuilt.append(db) or True
        import sys
        old_argv = sys.argv
        sys.argv = ["refresh-f1-current.py"]
        try:
            self.assertEqual(rf.main(), 1)
            self.assertEqual(rebuilt, [], "驗證未過就不該重建 db")
        finally:
            rf.refresh, rf.sync_whole_db_files = orig_refresh, orig_sync
            rf._rebuild_and_verify, rf.fh.Fetcher = orig_verify, orig_fetcher
            sys.argv = old_argv


if __name__ == "__main__":
    unittest.main()
