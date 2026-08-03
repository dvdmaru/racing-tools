#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""refresh-f1-current.py — 百科線 M7：當季新賽果增量橋接（raw 層）。

現況兩層資料互不相通：
  - 百科（/seasons/·/drivers/）讀 data/f1/raw/（7 月凍結快照，2026 到 R10）。
  - 週更三頁（fetch_racing.py）讀 data/<season>/（另一層，逐週刷新）。
本腳本橋接這道縫：**只把當季（config/encyclopedia.json 的 current_season）的新賽果增量抓進
data/f1/raw/**，讓百科的凍結庫能跟上賽季推進。歷史季（1950–當季前一年）一律不碰、凍結不動。

鐵則：
  1. 只碰**當季檔**（results / sprint / standings / schedule 的 current_season 檔）＋**全庫單檔**，
     且全庫單檔落地前必須先程式化驗證**歷史零漂移**，驗不過就中止落地並回報（不靜默覆蓋）。

     ⚠️ 2026-08-03 修訂（原文是「只碰當季檔，歷史零改動」）：db 的三個關鍵來源本質上都是
     **全庫單檔**，當季有新資料時一定要動它們——
       · data/f1/raw/entities/races.json     全 77 季賽曆單檔（build-f1-db 的 races 表來源）
       · data/f1/raw/entities/status.json    I8 的 oracle（全庫 status 計數單檔）
       · data/f1/raw/drivers/<id>-results.json  I5 雙路徑的發布側生涯檔（跨賽季）
     舊鐵則禁止碰它們，這支腳本就乾脆不動 → 它「成功」跑完但 db 的賽曆永遠停在 backfill
     當時（2026 由 22 站變 23 站是人手動補進去的）。修法不是解禁，是把「不准動」換成
     「動之前先證明歷史沒漂移」：
       · races.json：1950..(當季−1) 逐場比對，任何新增/消失/欄位差異即中止
       · 生涯檔：當季以外的明細零變動（逐場逐欄）
       · status.json：計數不得減少、不得憑空多出歷史沒有的類別、增量不得超過當季本地賽果
         能解釋的量。⚠️ **不**把計數改成本地推算——那會讓 I8 變成自己比自己的恆真式；
         這裡仍以 API 計數為準，只做方向性漂移防線，精確比對留給 I8。
  2. 落地格式與 fetch-f1-history.py 完全一致（沿用其 Fetcher / _write / _standings_full）——
     build-f1-db.py 讀得動、跑兩次 byte-identical（既有 round 檔 resumable 跳過；schedule/
     standings 內容不變不重寫）。
  3. jolpica 賽後灌資料有延遲（實測 ~9h）：某站排定日已過但賽果尚未出現 → 安靜跳過（不重試
     轟炸）。整季無任何新賽果 → exit 0＋訊息，不重建 db、不跑不變量。
  4. 有新賽果 → 刷新該季 standings + schedule → rebuild db.sqlite → 跑 check-f1-invariants.py；
     失敗集合 != 宣告例外 → exit 1 且不進入頁面重生（把壞資料擋在頁面外）。

用法：
  python3 scripts/refresh-f1-current.py            # 增量抓 current_season 新賽果
  python3 scripts/refresh-f1-current.py --season 2026
  python3 scripts/refresh-f1-current.py --no-invariants   # 只更新 raw，不 rebuild/驗（測試用）
"""
import argparse
import collections
import datetime
import importlib.util
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
RAW = ROOT / "data" / "f1" / "raw"
DEFAULT_DB = ROOT / "data" / "f1" / "db.sqlite"


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rc = _load("racinglib", "racinglib.py")
fh = _load("fetch_f1_history", "fetch-f1-history.py")   # Fetcher / _write / _standings_full / _now


def _content_no_meta(obj):
    """比對用：去掉 _meta（含每次都變的 fetched_at）後的內容。"""
    return {k: v for k, v in obj.items() if k != "_meta"}


def _write_if_changed(path, obj, url):
    """內容（去 _meta）與現檔相同 → 不重寫（保留原 bytes，idempotent）；不同或新檔 → 寫。

    回 True＝有寫。schedule/standings 走這條，避免無謂的 timestamp churn。
    """
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            if _content_no_meta(old) == _content_no_meta({**obj}):
                return False
        except (OSError, ValueError):
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {**obj, "_meta": {"url": url, "fetched_at": fh._now(), "backfill": True}}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def _today():
    return datetime.datetime.now(datetime.timezone.utc).date()


# ---------------------------------------------------------------------------
# 全庫單檔：歷史零漂移驗證（鐵則① 2026-08-03 修訂的落地）
# ---------------------------------------------------------------------------

class HistoryDriftError(RuntimeError):
    """全庫單檔的歷史區段出現差異 → 中止落地。

    刻意**不**自行修補、不部分寫入、不降級成 warning：歷史漂移要嘛是上游改了資料、
    要嘛是本地檔壞了，兩種都需要人看過再決定，不該由週更腳本自己吞掉。
    """


def _read_raw(path):
    """讀已落地的 raw 單檔；不存在或壞掉回 None（＝沒有可比對的基準）。"""
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _by_race_key(races):
    """[(season, round)] → race dict。重複鍵即上游資料異常，直接拋。"""
    out = {}
    for r in races:
        k = (int(r["season"]), int(r["round"]))
        if k in out:
            raise HistoryDriftError(f"重複場次 {k}")
        out[k] = r
    return out


def _diff_frozen_races(old_races, new_races, season, label):
    """比對 old/new 兩份逐場清單在「season 以外」的區段；有任何差異就拋。

    比對單位是**整個 race dict**（逐欄），不是只比場次數——只比數量的話，改日期、換賽道、
    改 url 都會靜默通過。
    """
    old = {k: v for k, v in _by_race_key(old_races).items() if k[0] != season}
    new = {k: v for k, v in _by_race_key(new_races).items() if k[0] != season}
    vanished = sorted(set(old) - set(new))
    appeared = sorted(set(new) - set(old))
    changed = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    if vanished or appeared or changed:
        raise HistoryDriftError(
            f"{label} 歷史區段漂移：消失 {len(vanished)} 場{vanished[:5]}、"
            f"憑空多出 {len(appeared)} 場{appeared[:5]}、內容變動 {len(changed)} 場{changed[:5]}")
    return len(old)


def _status_counts(status_list):
    return {s["status"]: int(s["count"]) for s in status_list}


def _local_season_status_dist(raw_dir, season):
    """本地當季賽果檔的 status 分布（用來界定「增量最多能被解釋到多少」）。"""
    dist = collections.Counter()
    for p in sorted((pathlib.Path(raw_dir) / "results").glob(f"{season}-*.json")):
        d = _read_raw(p) or {}
        for row in d.get("Results", []):
            dist[row.get("status")] += 1
    return dist


def _verify_status_increment(old_status, new_status, local_cur_dist, season):
    """status.json：增量必須能被當季新場次解釋。

    三條方向性斷言（都是不等式，故對「上一輪中途失敗、這一輪補跑」是自癒的，不會卡死成
    永遠亮紅）：
      ① 任一類別的計數不得減少——歷史賽果不會消失。
      ② 不得出現舊檔沒有、當季本地賽果也沒有的新類別——憑空多出歷史類別。
      ③ 任一類別的增量不得超過本地當季賽果能解釋的量。
    ⚠️ 這裡**不**把 status.json 的計數改成本地推算：那會讓 I8 從「兩個來源對帳」退化成
       自己比自己的恆真式。精確的逐類別相等留給 I8，本函式只擋方向性漂移。
    """
    old_c, new_c = _status_counts(old_status), _status_counts(new_status)
    problems = []
    for st in sorted(set(old_c) | set(new_c)):
        o, n = old_c.get(st, 0), new_c.get(st, 0)
        if n < o:
            problems.append(f"「{st}」計數由 {o} 減為 {n}（歷史賽果不該消失）")
        elif st not in old_c and not local_cur_dist.get(st):
            problems.append(f"「{st}」是舊檔沒有的新類別，但 {season} 本地賽果裡也沒有它")
        elif n - o > local_cur_dist.get(st, 0):
            problems.append(f"「{st}」增量 {n - o} > {season} 本地賽果能解釋的 "
                            f"{local_cur_dist.get(st, 0)}")
    if problems:
        raise HistoryDriftError("entities/status.json 增量無法被當季解釋：" + "；".join(problems))
    return sum(new_c.values()) - sum(old_c.values())


def _diff_additive_entities(old_items, new_items, id_key, label):
    """實體清單（drivers/constructors/circuits）：既有成員逐欄不變、只准新增。"""
    old = {i[id_key]: i for i in old_items}
    new = {i[id_key]: i for i in new_items}
    vanished = sorted(set(old) - set(new))
    changed = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    if vanished or changed:
        raise HistoryDriftError(
            f"{label} 既有成員漂移：消失 {vanished[:5]}、內容變動 {changed[:5]}")
    return sorted(set(new) - set(old))


# 實體清單：(API path, table key, item key, id 欄, 落地檔名)
ENTITY_SPECS = {
    "drivers": ("drivers", "DriverTable", "Drivers", "driverId", "drivers.json"),
    "constructors": ("constructors", "ConstructorTable", "Constructors",
                     "constructorId", "constructors.json"),
    "circuits": ("circuits", "CircuitTable", "Circuits", "circuitId", "circuits.json"),
}


def _referenced_ids(raw_dir, season):
    """當季本地賽果／賽程引用到的實體 id（用來偵測實體清單缺角 → I11 會紅）。"""
    ref = {"drivers": set(), "constructors": set(), "circuits": set()}
    for p in sorted((pathlib.Path(raw_dir) / "results").glob(f"{season}-*.json")):
        d = _read_raw(p) or {}
        cid = (d.get("Circuit") or {}).get("circuitId")
        if cid:
            ref["circuits"].add(cid)
        for row in d.get("Results", []):
            if (row.get("Driver") or {}).get("driverId"):
                ref["drivers"].add(row["Driver"]["driverId"])
            if (row.get("Constructor") or {}).get("constructorId"):
                ref["constructors"].add(row["Constructor"]["constructorId"])
    return ref


def sync_whole_db_files(season, f, raw_dir, new_rounds):
    """全庫單檔同步：驗歷史零漂移 → 過了才落地。回已更新檔案的清單。

    驗證失敗 → 拋 HistoryDriftError（呼叫端印紅字並 exit 1，不進入頁面重生）。
    找不到既有檔（沒有可比對的基準）→ 略過該檔並註記，**不**憑空生成全庫單檔。
    """
    raw_dir = pathlib.Path(raw_dir)
    updated, skipped = [], []

    # ① entities/races.json：全 77 季賽曆單檔（db 的 races 表來源）
    p = raw_dir / "entities" / "races.json"
    old = _read_raw(p)
    if old is None:
        skipped.append("entities/races.json（無既有檔可比對）")
    else:
        items, total = f.paged("races", "RaceTable", "Races")
        if len(items) != total:
            raise HistoryDriftError(f"races：抓到 {len(items)} 筆但 total={total}（抓短不落地）")
        n = _diff_frozen_races(old.get("Races", []), items, season, "entities/races.json")
        if _write_if_changed(p, {"Races": items, "total": total}, f"{fh.BASE}/races.json"):
            updated.append(f"entities/races.json（歷史 {n} 場逐場比對零漂移 → 全庫 {total} 場）")

    # ② entities/status.json：I8 的 oracle
    p = raw_dir / "entities" / "status.json"
    old = _read_raw(p)
    if old is None:
        skipped.append("entities/status.json（無既有檔可比對）")
    else:
        items, total = f.paged("status", "StatusTable", "Status")
        if len(items) != total:
            raise HistoryDriftError(f"status：抓到 {len(items)} 筆但 total={total}（抓短不落地）")
        delta = _verify_status_increment(old.get("Status", []), items,
                                         _local_season_status_dist(raw_dir, season), season)
        if _write_if_changed(p, {"Status": items, "total": total}, f"{fh.BASE}/status.json"):
            updated.append(f"entities/status.json（增量 +{delta} 列可由 {season} 當季賽果解釋）")

    # ③ drivers/<id>-results.json：I5 雙路徑的發布側生涯檔（只刷有本地檔的車手）
    for p in sorted((raw_dir / "drivers").glob("*-results.json")):
        did = p.name[: -len("-results.json")]
        old = _read_raw(p)
        if old is None:
            skipped.append(f"drivers/{p.name}（讀不到）")
            continue
        items, total = f.paged(f"drivers/{did}/results", "RaceTable", "Races")
        if len(items) != total:
            raise HistoryDriftError(f"{did} 生涯檔：抓到 {len(items)} 筆但 total={total}")
        n = _diff_frozen_races(old.get("Races", []), items, season, f"drivers/{p.name}")
        if _write_if_changed(p, {"driverId": did, "total": total, "Races": items},
                             f"{fh.BASE}/drivers/{did}/results.json"):
            updated.append(f"drivers/{p.name}（{season} 以外 {n} 場零變動 → 生涯 {total} 場）")

    # ④ 實體清單缺角補完：當季新賽果可能帶進新車手/新車隊/新賽道，缺了 I11 就會紅。
    #    只在真的偵測到缺角時才抓（平時零請求），且既有成員必須逐欄不變、只准新增。
    ref = _referenced_ids(raw_dir, season)
    for kind, (path, tk, ik, id_key, fname) in ENTITY_SPECS.items():
        p = raw_dir / "entities" / fname
        old = _read_raw(p)
        if old is None:
            continue                       # 沒基準就不碰（同 ①②）
        have = {i[id_key] for i in old.get(ik, [])}
        missing = sorted(ref[kind] - have)
        if not missing:
            continue
        items, total = f.paged(path, tk, ik)
        if len(items) != total:
            raise HistoryDriftError(f"{path}：抓到 {len(items)} 筆但 total={total}")
        added = _diff_additive_entities(old.get(ik, []), items, id_key, f"entities/{fname}")
        still = sorted(set(missing) - set(added) - have)
        if still:
            raise HistoryDriftError(f"entities/{fname} 補完後仍缺 {still}（上游也沒有）")
        if _write_if_changed(p, {ik: items, "total": total}, f"{fh.BASE}/{path}.json"):
            updated.append(f"entities/{fname}（新增 {added}，既有成員零變動）")

    return updated, skipped


def refresh(season, f, raw_dir=RAW, today=None):
    """增量抓 season 的新賽果進 raw_dir。回 (new_rounds:list[int], schedule_changed:bool)。

    f＝fetch-f1-history 的 Fetcher（或測試用的 fake，需有 .get(path, params)）。
    只碰 season 檔；不 rebuild db、不跑不變量（那些由 main 在有新資料時才做）。
    """
    today = today or _today()
    base = fh.BASE
    raw_dir = pathlib.Path(raw_dir)

    # 1. 當季賽程（含各站日期，判定「是否已到比賽日」）
    sd = f.get(f"{season}", "?limit=100")
    races = sd["MRData"]["RaceTable"]["Races"]

    existing = {int(p.stem.split("-")[1])
                for p in (raw_dir / "results").glob(f"{season}-*.json")}

    new_rounds, skipped = [], []
    for r in sorted(races, key=lambda x: int(x["round"])):
        rnd = int(r["round"])
        if rnd in existing:
            continue                       # resumable：已有賽果檔跳過
        rdate = r.get("date")
        if rdate:
            try:
                if datetime.date.fromisoformat(rdate) > today:
                    continue               # 比賽尚未舉行 → 不打 API
            except ValueError:
                pass
        # 到了比賽日之後才嘗試抓賽果
        rd = f.get(f"{season}/{rnd}/results", "?limit=100")
        rr = rd["MRData"]["RaceTable"]["Races"]
        if rr and rr[0].get("Results"):
            fh._write(raw_dir / "results" / f"{season}-{rnd:02d}.json", rr[0],
                      f"{base}/{season}/{rnd}/results.json", force=True)
            new_rounds.append(rnd)
            # 衝刺賽（並非每站都有；空回應＝該站無衝刺賽 → 不寫）
            spd = f.get(f"{season}/{rnd}/sprint", "?limit=100")
            spr = spd["MRData"]["RaceTable"]["Races"]
            if spr and spr[0].get("SprintResults"):
                fh._write(raw_dir / "sprint" / f"{season}-{rnd:02d}.json", spr[0],
                          f"{base}/{season}/{rnd}/sprint.json", force=True)
        else:
            skipped.append(rnd)            # 賽後資料尚未灌入 → 安靜跳過（不重試）

    if skipped:
        print(f"  ⏳ R{skipped}：排定日已過但 jolpica 尚未提供賽果 → 安靜跳過（不重試轟炸）",
              flush=True)

    schedule_changed = False
    if new_rounds:
        # 2. 有新賽果才刷新該季 standings + schedule（內容不變不重寫）
        schedule_changed = _write_if_changed(
            raw_dir / f"season-{season}-schedule.json",
            {"season": str(season), "Races": races}, f"{base}/{season}.json")
        drv = fh._standings_full(f, f"{season}/driverstandings", "DriverStandings")
        if not drv.get("season"):
            drv["season"] = str(season)
        _write_if_changed(raw_dir / "standings" / f"driver-{season}.json", drv,
                          f"{base}/{season}/driverstandings.json")
        con = fh._standings_full(f, f"{season}/constructorstandings", "ConstructorStandings")
        if con.get("ConstructorStandings"):
            if not con.get("season"):
                con["season"] = str(season)
            _write_if_changed(raw_dir / "standings" / f"constructor-{season}.json", con,
                              f"{base}/{season}/constructorstandings.json")
    return new_rounds, schedule_changed


def _rebuild_and_verify(db_path):
    """rebuild db.sqlite → check-f1-invariants.py。回 True＝不變量通過。"""
    bdb = _load("build_f1_db", "build-f1-db.py")
    bdb.build(str(db_path))
    print("  ✅ db.sqlite 已重建", flush=True)
    rc_inv = subprocess.run(
        [sys.executable, str(SCRIPTS / "check-f1-invariants.py"), "--db", str(db_path)]
    ).returncode
    return rc_inv == 0


def main():
    ap = argparse.ArgumentParser(description="當季新賽果增量橋接（只碰當季 raw；歷史凍結）。")
    ap.add_argument("--season", type=int, default=rc.CURRENT_SEASON,
                    help="橋接的當季年份（預設 config/encyclopedia.json 的 current_season）")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--no-invariants", action="store_true",
                    help="只更新 raw，不 rebuild db、不跑不變量（測試/除錯用）")
    a = ap.parse_args()

    print(f"🔄 refresh-f1-current · season={a.season}（只碰當季，歷史凍結）", flush=True)
    f = fh.Fetcher()
    try:
        new_rounds, sched_changed = refresh(a.season, f, RAW)
    except Exception as e:                 # noqa: BLE001 — 網路/解析失敗不炸整條週更
        print(f"⚠️  refresh 抓取失敗（{type(e).__name__}: {e}）→ 當季不更新，續行", flush=True)
        return 2

    if not new_rounds:
        print(f"😴 {a.season} 無新賽果（非賽週或賽果未灌入）→ 安靜跳過，不重建 db、不跑不變量")
        return 0

    print(f"🆕 {a.season} 新增賽果：R{new_rounds}"
          f"{'（賽程亦更新）' if sched_changed else ''}", flush=True)

    # 全庫單檔同步（賽曆 / I8 oracle / 生涯檔 / 實體清單）：驗歷史零漂移過了才落地。
    # 不做這步，db 的賽曆會永遠停在 backfill 當時（見鐵則①的 2026-08-03 修訂）。
    try:
        updated, skipped = sync_whole_db_files(a.season, f, RAW, new_rounds)
    except HistoryDriftError as e:
        print(f"🔴 全庫單檔歷史零漂移驗證未過 → 中止落地，不重建 db、不進入頁面重生\n   {e}",
              flush=True)
        return 1
    for line in updated:
        print(f"  📦 已更新 {line}", flush=True)
    for line in skipped:
        print(f"  ⏭  略過 {line}", flush=True)
    if not updated:
        print("  📦 全庫單檔內容無變化（不重寫）", flush=True)

    if a.no_invariants:
        print("  ⏭  --no-invariants：只更新 raw，未 rebuild/驗", flush=True)
        return 0
    if not _rebuild_and_verify(a.db):
        print("🔴 不變量未通過（失敗集合 != 宣告例外）→ exit 1，不進入頁面重生", flush=True)
        return 1
    print("✅ 當季橋接完成，db 已重建且不變量通過", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
