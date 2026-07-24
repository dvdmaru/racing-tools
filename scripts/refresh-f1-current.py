#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""refresh-f1-current.py — 百科線 M7：當季新賽果增量橋接（raw 層）。

現況兩層資料互不相通：
  - 百科（/seasons/·/drivers/）讀 data/f1/raw/（7 月凍結快照，2026 到 R10）。
  - 週更三頁（fetch_racing.py）讀 data/<season>/（另一層，逐週刷新）。
本腳本橋接這道縫：**只把當季（config/encyclopedia.json 的 current_season）的新賽果增量抓進
data/f1/raw/**，讓百科的凍結庫能跟上賽季推進。歷史季（1950–當季前一年）一律不碰、凍結不動。

鐵則：
  1. 只碰當季檔（results / sprint / standings / schedule 的 current_season 檔），歷史零改動。
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
