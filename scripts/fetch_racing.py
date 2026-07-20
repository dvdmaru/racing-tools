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


def active_season() -> int:
    """單一賽季設定源 config/site.json 的 season——換季只改一處，全管線跟著走。"""
    try:
        cfg = json.loads((ROOT / "config" / "site.json").read_text(encoding="utf-8"))
        return int(cfg["season"])
    except (OSError, ValueError, KeyError):
        return 2026

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

    def _paged(self, path, key):
        """翻頁抓完整資料集，回 (合併後的清單, total)。

        ⚠️ laps 單站約 870 筆、上限 100/頁，**不翻頁只會拿到前 2 圈而且沒有任何錯誤徵兆**——
        回傳結構完全正常、只是內容少了 95%。這種缺損下游看不出來，所以翻頁不是最佳化。
        """
        merged, offset, total = [], 0, 0
        while True:
            d = self._get(path, f"?limit=100&offset={offset}")
            m = d["MRData"]
            total = int(m.get("total") or 0)
            races = m["RaceTable"]["Races"]
            if not races:
                # 還沒翻完卻回空頁＝資料不完整。原本這裡直接 break 帶著半份資料返回，
                # 下游看到的結構完全正常（2026-07-20 圓桌覆核 S4）。
                if offset < total:
                    raise RuntimeError(
                        f"{path}: offset {offset} 尚未到 total {total} 卻回空頁，"
                        "資料不完整，拒絕返回半份結果")
                break
            merged.extend(races[0].get(key) or [])
            offset += 100
            if offset >= total:
                break
        return merged, total

    def race_laps(self, season, rnd):
        """逐圈計時（每圈含各車手該圈名次與圈速）。"""
        laps, total = self._paged(f"{season}/{rnd}/laps", "Laps")
        by_num = {}
        for lp in laps:  # 同一圈可能被切在兩頁，要合併 Timings 不是覆蓋
            n = int(lp.get("number") or 0)
            by_num.setdefault(n, []).extend(lp.get("Timings") or [])
        got = sum(len(v) for v in by_num.values())
        if got != total:
            raise RuntimeError(f"laps 筆數不符：合併後 {got} ≠ API total {total}")
        for n, timings in by_num.items():
            ids = [t.get("driverId") for t in timings]
            if len(ids) != len(set(ids)):
                raise RuntimeError(f"第 {n} 圈有重複車手紀錄，資料異常")
        nums = sorted(by_num)
        if nums and nums != list(range(nums[0], nums[-1] + 1)):
            raise RuntimeError(f"圈號不連續（缺洞）：{nums[:5]}…{nums[-5:]}")
        return {"season": season, "round": rnd, "records_total": total,
                "Laps": [{"number": n, "Timings": by_num[n]} for n in nums]}

    def race_pitstops(self, season, rnd):
        stops, total = self._paged(f"{season}/{rnd}/pitstops", "PitStops")
        if len(stops) != total:
            raise RuntimeError(f"pitstops 筆數不符：{len(stops)} ≠ API total {total}")
        return {"season": season, "round": rnd, "records_total": total, "PitStops": stops}

    def standings_after_round(self, season, rnd):
        """指定輪次結束後的積分榜——before/after 推導的獨立 oracle。

        推導值（賽後榜減本站得分）與這裡拿到的 round N-1 榜是兩條獨立路徑，
        對得起來才可信。同一個 helper 既產生又自我檢查，抓不到共同邏輯錯誤
        （2026-07-20 圓桌 S5）。
        """
        out = {}
        for kind, key in (("driver", "DriverStandings"),
                          ("constructor", "ConstructorStandings")):
            d = self._get(f"{season}/{rnd}/{kind}standings", "?limit=100")
            lists = d["MRData"]["StandingsTable"]["StandingsLists"]
            out[kind] = (lists[0].get(key) or []) if lists else []
        return out

    def latest_race(self, season):
        """最近一場「已有正賽賽果」的比賽（round 權威值——見模組 docstring）。"""
        d = self._get(f"{season}/last/results", "?limit=100")
        races = d["MRData"]["RaceTable"]["Races"]
        return races[0] if races else None


def _rel(path: pathlib.Path):
    """顯示用相對路徑；不在 repo 下（測試 tmp 目錄）就原樣印。"""
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def _write(path: pathlib.Path, obj, history=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, indent=2)
    changed = (not path.exists()) or path.read_text(encoding="utf-8") != txt
    if changed:  # 無變化不重寫：避免弄髒工作樹（否則本機每跑一次就出現假 diff）
        path.write_text(txt, encoding="utf-8")
    print(f"  💾 {_rel(path)}{'' if changed else '（無變化，未重寫）'}")
    if history and changed:
        today = datetime.date.today().isoformat()
        h = path.parent / "history" / f"{today}-{path.name}"
        h.parent.mkdir(parents=True, exist_ok=True)
        h.write_text(txt, encoding="utf-8")
        print(f"  🗄  {_rel(h)}")
    return changed


def _strip_volatile(obj):
    """比較用：去掉每次抓取必變的欄位（fetched_at），避免假性「有變化」。"""
    return {k: v for k, v in obj.items() if k != "fetched_at"} if isinstance(obj, dict) else obj


def _write_snapshot(path, obj, history=False):
    """同 _write，但 changed 判定忽略 fetched_at（否則每次跑都判定有變、安靜跳過永不觸發）。
    無變化時完全不重寫檔案——否則單純的 fetched_at 更新就會弄髒工作樹。"""
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
    if changed:
        path.write_text(txt, encoding="utf-8")
    print(f"  💾 {_rel(path)}{'' if changed else '（無變化，未重寫）'}")
    if history and changed:
        today = datetime.date.today().isoformat()
        h = path.parent / "history" / f"{today}-{path.name}"
        h.parent.mkdir(parents=True, exist_ok=True)
        h.write_text(txt, encoding="utf-8")
        print(f"  🗄  {_rel(h)}")
    return changed


def _load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def validate_standings(ds, cs, latest, data_round, prev_round):
    """快照寫入前驗證：API 回空殼或倒退時拒寫、保留 last-known-good。
    回 (ok, reason)。開季前 standings 本來就空——那時 prev 也不存在，不會誤判。"""
    if ds is None or cs is None:
        return False, "standings 為空（API 回空 StandingsLists）"
    if len(ds.get("DriverStandings", [])) < 10:
        return False, f"車手榜僅 {len(ds.get('DriverStandings', []))} 筆，不合理"
    if len(cs.get("ConstructorStandings", [])) < 5:
        return False, f"車隊榜僅 {len(cs.get('ConstructorStandings', []))} 筆，不合理"
    if latest is None and prev_round > 0:
        return False, "last/results 回空但既有快照已有賽果"
    if data_round < prev_round:
        return False, f"data_through_round 倒退（{prev_round} → {data_round}）"
    return True, ""


def validate_schedule(races, prev):
    rounds = [int(r.get("round", 0)) for r in (races or [])]
    if not rounds:
        return False, "schedule 為空"
    if len(set(rounds)) != len(rounds):
        return False, "schedule round 重複"
    if prev and prev.get("races") and len(rounds) < len(prev["races"]) - 2:
        return False, f"schedule 站數驟減（{len(prev['races'])} → {len(rounds)}）"
    return True, ""


def fetch_standings(src, season):
    base = DATA / str(season)
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    ds = src.driver_standings(season)
    cs = src.constructor_standings(season)
    latest = src.latest_race(season)
    data_round = int(latest["round"]) if latest else 0
    prev = _load_json(base / "driver-standings.json")
    prev_round = int(prev.get("data_through_round", 0)) if prev else 0
    ok, reason = validate_standings(ds, cs, latest, data_round, prev_round)
    if not ok and prev is not None:
        print(f"  🛑 standings 驗證未過（{reason}）→ 保留既有快照不覆寫", flush=True)
        return False, prev_round, None
    ch1 = _write_snapshot(base / "driver-standings.json",
                          {"season": season, "fetched_at": fetched_at,
                           "data_through_round": data_round, "standings": ds}, history=True)
    ch2 = _write_snapshot(base / "constructor-standings.json",
                          {"season": season, "fetched_at": fetched_at,
                           "data_through_round": data_round, "standings": cs}, history=True)
    return (ch1 or ch2), data_round, latest


def fetch_schedule(src, season):
    path = DATA / str(season) / "schedule.json"
    races = src.schedule(season)
    prev = _load_json(path)
    ok, reason = validate_schedule(races, prev)
    if not ok and prev is not None:
        print(f"  🛑 schedule 驗證未過（{reason}）→ 保留既有快照不覆寫", flush=True)
        return False, prev["races"]
    return _write_snapshot(path, {"season": season, "races": races}, history=True), races


def sprint_session_passed(race_entry, now_utc):
    """該站衝刺賽 session（UTC）是否已開跑——决定正賽前要不要抓 current-round sprint。"""
    sp = (race_entry or {}).get("Sprint")
    if not sp or not sp.get("date"):
        return False
    t = (sp.get("time") or "00:00:00Z").replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(f"{sp['date']}T{t}")
    except ValueError:
        return False
    return now_utc >= dt


def fetch_results(src, season, latest_round, races, force=False):
    """抓 1..latest_round 的正賽賽果（+ sprint 站的衝刺賽果）。已完賽站結果原則上不變，
    檔案已存在就跳過；最新一站每次重抓（FIA 賽後改判/失格會回寫，sprint 同理）。
    另外：下一站若是 sprint 站且衝刺賽已開跑（正賽還沒跑），單獨抓衝刺賽果——
    否則六/日排程在正賽前永遠抓不到當站衝刺賽。--force 全重抓。"""
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
        if rnd in sprint_rounds and (force or not sp.exists() or rnd == latest_round):
            res = src.sprint_results(season, rnd)
            if res:
                changed |= _write(sp, res)
    # 逐圈與進站：只抓最新一站（每站約 870 筆逐圈紀錄，全季重抓沒有必要也吃 rate limit）。
    # 這兩份是賽後戰報敘事的唯一可查證來源——沒有它們，「全場最大轉折」這種句子只能靠編。
    lp = base / f"round-{latest_round:02d}-laps.json"
    ps = base / f"round-{latest_round:02d}-pitstops.json"
    if force or not lp.exists():
        data = src.race_laps(season, latest_round)
        if data.get("Laps"):
            changed |= _write(lp, data)
    if force or not ps.exists():
        data = src.race_pitstops(season, latest_round)
        if data.get("PitStops"):
            changed |= _write(ps, data)

    nxt = latest_round + 1
    nxt_race = next((r for r in races if int(r.get("round", 0)) == nxt), None)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if nxt in sprint_rounds and sprint_session_passed(nxt_race, now_utc):
        res = src.sprint_results(season, nxt)
        if res:
            changed |= _write(base / f"round-{nxt:02d}-sprint.json", res)
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["all", "standings", "schedule", "results"])
    ap.add_argument("--season", type=int, default=active_season())
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
