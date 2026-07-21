#!/usr/bin/env python3
"""fetch-f1-history.py — 一次性歷史 backfill（與 fetch_racing.py 的當季週更完全分離）。

落地到 data/f1/raw/，原樣保存 + _meta。歷史資料抓一次就凍結，週更不碰。
resumable：已存在的檔跳過，--force 覆寫。

Phase 0 用到的 phase：
  standings  — 逐季車手榜(77) + 車隊榜(69)，這是算「幾冠」的唯一來源
  season     — 指定年的賽程 + 逐站賽果 + 該年兩榜（--year）
  driver     — 指定車手的生涯賽果（--driver，可多次）

rate limit：jolpica burst 4/s、sustained 500/hr。實作＝雙層節流：
  ① 每請求最小間隔 0.45s（burst 層）
  ② sliding window：任一小時窗口內 ≤450 請求，滿了就睡到窗口滾出（sustained 層）
小量抓取（<450 req）只有 ① 生效、速度不變；全量 backfill 自動被 ② 壓到約 75 分鐘。
"""
import argparse
import collections
import json
import pathlib
import ssl
import sys
import time
import urllib.error
import urllib.request

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "f1" / "raw"
BASE = "https://api.jolpi.ca/ergast/f1"
UA = "racing-tools/1.0 (racing.twtools.cc; non-commercial encyclopedia backfill)"


class Fetcher:
    def __init__(self, pause=0.45, hourly=450):
        self.pause = pause      # burst 層：每請求最小間隔
        self.hourly = hourly    # sustained 層：一小時窗口上限（jolpica 500/hr，留餘裕）
        self._last = 0.0
        self._stamps = collections.deque()  # 每次實際發出請求的時間戳（含 retry）
        self.n = 0

    def _throttle(self):
        wait = self.pause - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        now = time.monotonic()
        while self._stamps and now - self._stamps[0] > 3600:
            self._stamps.popleft()
        if len(self._stamps) >= self.hourly:
            s = 3600 - (now - self._stamps[0]) + 1
            print(f"  ⏳ 滑動窗口達 {self.hourly}/hr → 睡 {int(s)}s", flush=True)
            time.sleep(s)

    def get(self, path, params=""):
        url = f"{BASE}/{path}.json{params}"
        delay = 5
        for attempt in range(5):
            self._throttle()
            self._last = time.monotonic()
            self._stamps.append(self._last)
            self.n += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                    ra = e.headers.get("Retry-After")
                    s = int(ra) if (ra or "").isdigit() else delay
                    print(f"  ⏳ HTTP {e.code} {path} → {s}s", flush=True)
                    time.sleep(s)
                    delay = min(delay * 2, 180)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < 4:
                    print(f"  ⏳ net err {path} → {delay}s", flush=True)
                    time.sleep(delay)
                    delay = min(delay * 2, 180)
                    continue
                raise

    def paged(self, path, table_key, item_key, cache=None):
        """翻頁抓完整；回 (items, total)。空頁但未到 total → 拋錯（不返回半份）。

        cache 給目錄路徑時，每頁落地即 checkpoint（resumable 硬需求）；
        呼叫端在整個 phase 驗證通過後自行清掉 cache 目錄。
        """
        items, offset, total = [], 0, 0
        while True:
            cp = (cache / f"{offset:06d}.json") if cache else None
            if cp and cp.exists():
                d = json.loads(cp.read_text(encoding="utf-8"))
            else:
                d = self.get(path, f"?limit=100&offset={offset}")
                if cp:
                    cp.parent.mkdir(parents=True, exist_ok=True)
                    cp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            m = d["MRData"]
            total = int(m.get("total") or 0)
            container = m.get(table_key, {})
            rows = container.get(item_key, []) if isinstance(container, dict) else []
            if not rows:
                if offset < total:
                    raise RuntimeError(f"{path}: offset {offset} < total {total} 卻空頁")
                break
            items.extend(rows)
            offset += 100
            if offset >= total:
                break
        return items, total


def _write(path, obj, url, force=False):
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    obj["_meta"] = {"url": url, "fetched_at": _now(), "backfill": True}
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def _now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _standings_full(f, path, key):
    """分頁抓完整一季 standings；空頁但未達 total → 拋錯，不寫半份。

    ⚠️ 2026-07-22 教訓：單發 ?limit=100 曾把 1952、1953 車手榜（Indy 500 年代破百人）
    靜默截斷在 100 筆整。冠軍在第 1 筆所以「幾冠」沒被污染，但 raw 層的定位是
    凍結的完整自有資料庫，缺行等於違反它存在的理由。
    """
    rows, offset, meta = [], 0, None
    while True:
        d = f.get(path, f"?limit=100&offset={offset}")
        m = d["MRData"]
        total = int(m.get("total") or 0)
        lists = m["StandingsTable"]["StandingsLists"]
        page = lists[0].get(key, []) if lists else []
        if meta is None and lists:
            meta = {k: v for k, v in lists[0].items() if k != key}
        rows.extend(page)
        offset += 100
        if offset >= total or not page:
            break
    if len(rows) != total:
        raise RuntimeError(f"{path}: 抓到 {len(rows)} 筆但 total={total}")
    return {**(meta or {}), key: rows}


def phase_standings(f, force):
    seasons, _ = f.paged("seasons", "SeasonTable", "Seasons")
    years = [int(s["season"]) for s in seasons]
    print(f"seasons: {years[0]}–{years[-1]}（{len(years)}）")
    wrote = 0
    for y in years:
        dp = RAW / "standings" / f"driver-{y}.json"
        if force or not dp.exists():
            obj = _standings_full(f, f"{y}/driverstandings", "DriverStandings")
            if not obj.get("season"):
                obj["season"] = str(y)
            _write(dp, obj, f"{BASE}/{y}/driverstandings.json", force)
            wrote += 1
        cp = RAW / "standings" / f"constructor-{y}.json"
        if force or not cp.exists():
            obj = _standings_full(f, f"{y}/constructorstandings", "ConstructorStandings")
            if obj.get("ConstructorStandings"):
                _write(cp, obj, f"{BASE}/{y}/constructorstandings.json", force)
        if wrote % 10 == 0 and wrote:
            print(f"  … {y} 已抓，累計 {f.n} req", flush=True)
    print(f"standings 完成，{f.n} req")


def phase_season(f, year, force):
    d = f.get(f"{year}", "?limit=100")
    races = d["MRData"]["RaceTable"]["Races"]
    _write(RAW / f"season-{year}-schedule.json", {"season": str(year), "Races": races},
           f"{BASE}/{year}.json", force)
    print(f"{year}: {len(races)} 站")
    for r in races:
        rnd = int(r["round"])
        rp = RAW / "results" / f"{year}-{rnd:02d}.json"
        if force or not rp.exists():
            rd = f.get(f"{year}/{rnd}/results", "?limit=100")
            rr = rd["MRData"]["RaceTable"]["Races"]
            if rr:
                _write(rp, rr[0], f"{BASE}/{year}/{rnd}/results.json", force)
    print(f"  {year} 賽果完成，累計 {f.n} req")


def phase_global_rounds(f, endpoint, list_key, outdir, label):
    """全域端點（/results、/qualifying、/sprint）翻頁抓完 → 合併成逐場檔。

    分頁以「結果列」計，一場比賽可能被切在兩頁 → 以 (season, round) 合併。
    合併後總列數必須 == API total（I8 的 fetch 端版本），過了才落地、才清 page cache。
    """
    cache = RAW / "_pages" / endpoint
    races, total = f.paged(endpoint, "RaceTable", "Races", cache=cache)
    merged, order = {}, []
    for r in races:
        key = (int(r["season"]), int(r["round"]))
        if key not in merged:
            base = {k: v for k, v in r.items() if k != list_key}
            base[list_key] = []
            merged[key] = base
            order.append(key)
        merged[key][list_key].extend(r.get(list_key, []))
    rows = sum(len(v[list_key]) for v in merged.values())
    if rows != total:
        raise RuntimeError(f"{endpoint}: 合併後 {rows} 列 != total {total}")
    for (y, rnd) in order:
        _write(outdir / f"{y}-{rnd:02d}.json", merged[(y, rnd)],
               f"{BASE}/{endpoint}.json", force=True)
    import shutil
    shutil.rmtree(cache, ignore_errors=True)
    print(f"{label}: {total} 列 → {len(order)} 場檔，累計 {f.n} req", flush=True)


def phase_entities(f, force):
    """實體清單與全賽程（單檔落地）。API 的 total 是唯一真 oracle，抓短即拋錯。"""
    for path, tk, ik, fname in [
        ("drivers", "DriverTable", "Drivers", "drivers.json"),
        ("constructors", "ConstructorTable", "Constructors", "constructors.json"),
        ("circuits", "CircuitTable", "Circuits", "circuits.json"),
        ("seasons", "SeasonTable", "Seasons", "seasons.json"),
        ("status", "StatusTable", "Status", "status.json"),
        ("races", "RaceTable", "Races", "races.json"),
    ]:
        items, total = f.paged(path, tk, ik)
        if len(items) != total:
            raise RuntimeError(f"{path}: {len(items)} != total {total}")
        _write(RAW / "entities" / fname, {ik: items, "total": total},
               f"{BASE}/{path}.json", True)
        print(f"  {path}: {total}", flush=True)


def phase_driver(f, did, force):
    items, total = f.paged(f"drivers/{did}/results", "RaceTable", "Races")
    _write(RAW / "drivers" / f"{did}-results.json",
           {"driverId": did, "total": total, "Races": items},
           f"{BASE}/drivers/{did}/results.json", force)
    info = f.get(f"drivers/{did}")
    drv = info["MRData"]["DriverTable"]["Drivers"]
    _write(RAW / "drivers" / f"{did}.json", drv[0] if drv else {},
           f"{BASE}/drivers/{did}.json", force)
    print(f"  {did}: {total} 場生涯賽果")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True,
                    choices=["standings", "season", "driver", "all-phase0", "all-history"])
    ap.add_argument("--year", type=int)
    ap.add_argument("--driver", action="append", default=[])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    f = Fetcher()

    if a.phase == "standings":
        phase_standings(f, a.force)
    elif a.phase == "season":
        phase_season(f, a.year, a.force)
    elif a.phase == "driver":
        for d in a.driver:
            phase_driver(f, d, a.force)
    elif a.phase == "all-phase0":
        phase_standings(f, a.force)
        for y in (2002, 2026):
            phase_season(f, y, a.force)
        for d in ("michael_schumacher", "hamilton", "senna", "max_verstappen"):
            phase_driver(f, d, a.force)
        print(f"\n✅ Phase 0 backfill 完成，共 {f.n} requests")
    elif a.phase == "all-history":
        # M1 全量：standings 已抓的檔會自動跳過；全域端點合併驗證後落地
        phase_standings(f, a.force)
        phase_entities(f, a.force)
        phase_global_rounds(f, "results", "Results", RAW / "results", "全庫正賽賽果")
        phase_global_rounds(f, "qualifying", "QualifyingResults",
                            RAW / "qualifying", "全庫排位")
        phase_global_rounds(f, "sprint", "SprintResults", RAW / "sprint", "全庫衝刺賽")
        print(f"\n✅ M1 全量 backfill 完成，共 {f.n} requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
