#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_racing.py — racing.twtools.cc 資料層（adapter 介面 + jolpica-f1 實作）。

jolpica 是志願者專案、有停運風險 → 資料層走 adapter 介面（DataSource），未來換源
（OpenF1、自建爬蟲）只需新增一個 class，頁面生成端不動。每次抓取都落地 JSON 快照到
data/<season>/，dated 副本進 data/<season>/history/ 當自有歷史庫——即使上游消失，
本站已發布過的數據不受影響。

jolpica rate limit（官方 docs/rate_limits.md）：burst 4 req/s、sustained 500 req/hr。
本腳本每輪完整抓取約 6-10 個 request，加 0.35s 間距 + 429/5xx 指數退避，遠低於限。

Ergast 相容 schema 注意：season-level standings 的 round 欄位可能指向「即將進行」的
一站（實測 2026-07-19：正賽當天早上 round 標 10、積分實為 round 9 完賽後）→
「資料截至第幾站」一律以 last/results 的 round 為準，不信 standings 的 round。

用法：
  python3 scripts/fetch_racing.py all --season 2026     # 積分榜+賽曆+全部已完賽站賽果
  python3 scripts/fetch_racing.py standings --season 2026
  python3 scripts/fetch_racing.py schedule --season 2026
  python3 scripts/fetch_racing.py results --season 2026 [--force]
"""
import argparse
import datetime
import json
import pathlib
import ssl
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UA = "racing-tools/1.0 (racing.twtools.cc; non-commercial data page)"

# macOS python.org 版 Python 常缺系統 CA bundle → 有 certifi 就用（CI ubuntu 無害）
try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()


class DataSource:
    """資料源介面：頁面生成端只依賴這些方法與回傳形狀（Ergast 相容 dict）。"""

    def driver_standings(self, season): raise NotImplementedError
    def constructor_standings(self, season): raise NotImplementedError
    def schedule(self, season): raise NotImplementedError
    def race_results(self, season, rnd): raise NotImplementedError
    def sprint_results(self, season, rnd): raise NotImplementedError
    def latest_race(self, season): raise NotImplementedError


class JolpicaSource(DataSource):
    BASE = "https://api.jolpi.ca/ergast/f1"

    def __init__(self, pause=0.35):
        self.pause = pause
        self._last_req = 0.0

    def _get(self, path, params=""):
        """GET + JSON parse；429/5xx 指數退避重試（外部 API 鐵則），請求間 0.35s 間距。"""
        url = f"{self.BASE}/{path}.json{params}"
        wait = self.pause - (time.monotonic() - self._last_req)
        if wait > 0:
            time.sleep(wait)
        delay = 5
        for attempt in range(5):
            self._last_req = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                    retry_after = e.headers.get("Retry-After")
                    sleep_s = int(retry_after) if (retry_after or "").isdigit() else delay
                    print(f"  ⏳ HTTP {e.code} on {path} → retry in {sleep_s}s", flush=True)
                    time.sleep(sleep_s)
                    delay = min(delay * 2, 180)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < 4:
                    print(f"  ⏳ network error on {path} → retry in {delay}s", flush=True)
                    time.sleep(delay)
                    delay = min(delay * 2, 180)
                    continue
                raise

    def driver_standings(self, season):
        d = self._get(f"{season}/driverstandings")
        lists = d["MRData"]["StandingsTable"]["StandingsLists"]
        return lists[0] if lists else None

    def constructor_standings(self, season):
        d = self._get(f"{season}/constructorstandings")
        lists = d["MRData"]["StandingsTable"]["StandingsLists"]
        return lists[0] if lists else None

    def schedule(self, season):
        d = self._get(f"{season}", "?limit=100")
        return d["MRData"]["RaceTable"]["Races"]

    def race_results(self, season, rnd):
        d = self._get(f"{season}/{rnd}/results", "?limit=100")
        races = d["MRData"]["RaceTable"]["Races"]
        return races[0] if races else None

    def sprint_results(self, season, rnd):
        d = self._get(f"{season}/{rnd}/sprint", "?limit=100")
        races = d["MRData"]["RaceTable"]["Races"]
        return races[0] if races else None

    def latest_race(self, season):
        """最近一場「已有正賽賽果」的比賽（round 權威值——見模組 docstring）。"""
        d = self._get(f"{season}/last/results", "?limit=100")
        races = d["MRData"]["RaceTable"]["Races"]
        return races[0] if races else None


def _write(path: pathlib.Path, obj, history=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, indent=2)
    changed = (not path.exists()) or path.read_text(encoding="utf-8") != txt
    path.write_text(txt, encoding="utf-8")
    print(f"  💾 {path.relative_to(ROOT)}{'' if changed else '（無變化）'}")
    if history and changed:
        today = datetime.date.today().isoformat()
        h = path.parent / "history" / f"{today}-{path.name}"
        h.parent.mkdir(parents=True, exist_ok=True)
        h.write_text(txt, encoding="utf-8")
        print(f"  🗄  {h.relative_to(ROOT)}")
    return changed


def _strip_volatile(obj):
    """比較用：去掉每次抓取必變的欄位（fetched_at），避免假性「有變化」。"""
    return {k: v for k, v in obj.items() if k != "fetched_at"} if isinstance(obj, dict) else obj


def _write_snapshot(path, obj, history=False):
    """同 _write，但 changed 判定忽略 fetched_at（否則每次跑都判定有變、安靜跳過永不觸發）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, indent=2)
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            old = None
        changed = _strip_volatile(old) != _strip_volatile(obj)
    else:
        changed = True
    path.write_text(txt, encoding="utf-8")
    print(f"  💾 {path.relative_to(ROOT)}{'' if changed else '（無變化）'}")
    if history and changed:
        today = datetime.date.today().isoformat()
        h = path.parent / "history" / f"{today}-{path.name}"
        h.parent.mkdir(parents=True, exist_ok=True)
        h.write_text(txt, encoding="utf-8")
        print(f"  🗄  {h.relative_to(ROOT)}")
    return changed


def fetch_standings(src, season):
    base = DATA / str(season)
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    ds = src.driver_standings(season)
    cs = src.constructor_standings(season)
    latest = src.latest_race(season)
    data_round = int(latest["round"]) if latest else 0
    ch1 = _write_snapshot(base / "driver-standings.json",
                          {"season": season, "fetched_at": fetched_at,
                           "data_through_round": data_round, "standings": ds}, history=True)
    ch2 = _write_snapshot(base / "constructor-standings.json",
                          {"season": season, "fetched_at": fetched_at,
                           "data_through_round": data_round, "standings": cs}, history=True)
    return (ch1 or ch2), data_round, latest


def fetch_schedule(src, season):
    races = src.schedule(season)
    return _write_snapshot(DATA / str(season) / "schedule.json",
                           {"season": season, "races": races}, history=True), races


def fetch_results(src, season, latest_round, races, force=False):
    """抓 1..latest_round 的正賽賽果（+ sprint 站的衝刺賽果）。已完賽站結果原則上不變，
    檔案已存在就跳過；最新一站每次重抓（FIA 賽後改判/失格會回寫）。--force 全重抓。"""
    base = DATA / str(season) / "results"
    sprint_rounds = {int(r["round"]) for r in races if "Sprint" in r}
    changed = False
    for rnd in range(1, latest_round + 1):
        p = base / f"round-{rnd:02d}.json"
        if force or (not p.exists()) or rnd == latest_round:
            res = src.race_results(season, rnd)
            if res:
                changed |= _write(p, res)
        sp = base / f"round-{rnd:02d}-sprint.json"
        if rnd in sprint_rounds and (force or not sp.exists()):
            res = src.sprint_results(season, rnd)
            if res:
                changed |= _write(sp, res)
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["all", "standings", "schedule", "results"])
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    src = JolpicaSource()
    season = args.season
    print(f"🏁 fetch_racing · {args.cmd} · season={season}")

    changed = False
    races = []
    if args.cmd in ("all", "schedule", "results"):
        sch_changed, races = fetch_schedule(src, season)
        changed |= sch_changed
    if args.cmd in ("all", "standings"):
        st_changed, data_round, _ = fetch_standings(src, season)
        changed |= st_changed
    if args.cmd in ("all", "results"):
        if args.cmd == "results":
            latest = src.latest_race(season)
            data_round = int(latest["round"]) if latest else 0
        changed |= fetch_results(src, season, data_round, races, force=args.force)

    print(f"{'🔄 有新資料' if changed else '😴 無新資料'}")
    # exit code 供 update-racing.py 的安靜跳過邏輯用：0=有變化、3=無變化
    sys.exit(0 if changed else 3)


if __name__ == "__main__":
    main()
