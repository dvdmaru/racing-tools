#!/usr/bin/env python3
"""reconcile.py — 賽後判罰偵測：重抓賽果／積分榜，跟落地快照比對。

為什麼需要：F1 賽果會在賽後數小時到數天因判罰更動名次與積分。發布當下對的稿子，
之後可能變成錯的，而**沒有任何人會來通知我們**。管線其他所有檢查都是「發布前」的，
這支是唯一往後看的。

兩種用法：
  1. **量測**（現在）：跑幾次記錄「賽果多久之後才穩定」，那個數字決定重驗排程要多長。
     `python3 scripts/reconcile.py --round 10 --log`
  2. **執法**（S7，尚未接上）：偵測到變動時把受影響的 slug 移出 config/approved.json，
     下次 build 自動下架轉回待審。目前只報告不動作——`--enforce` 尚未實作。

⚠️ 這支測的是「資料源現在跟快照一不一樣」，**不是「FIA 有沒有開罰」**。
jolpica 是志願者專案，它同步 FIA 判決的延遲我們沒有量過。兩者不可混為一談。
"""
import argparse
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import racinglib as rc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG = ROOT / "facts" / "reconcile-log.jsonl"


def _results_key(res):
    out = {}
    for e in (res or {}).get("Results") or []:
        try:
            pos = int(e.get("position") or 0)
        except (TypeError, ValueError):
            continue
        out[pos] = {
            "driver": (e.get("Driver") or {}).get("driverId", ""),
            "position_text": e.get("positionText", ""),
            "status": e.get("status", ""),
            "points": float(e.get("points") or 0),
        }
    return out


def reconcile(season, rnd, write_log=False):
    import fetch_racing

    local_path = ROOT / "data" / str(season) / "results" / f"round-{rnd:02d}.json"
    if not local_path.exists():
        print(f"❌ 沒有本地快照可比對：{local_path}", file=sys.stderr)
        return None
    local = json.loads(local_path.read_text(encoding="utf-8"))

    src = fetch_racing.JolpicaSource()
    live = src.race_results(season, rnd)
    a, b = _results_key(local), _results_key(live)

    changes = []
    for pos in sorted(set(a) | set(b)):
        if a.get(pos) != b.get(pos):
            changes.append({"position": pos, "snapshot": a.get(pos), "live": b.get(pos)})

    # 積分榜獨立再比一次：判罰可能只改積分不改名次
    ds_path = ROOT / "data" / str(season) / "driver-standings.json"
    st_changes = []
    if ds_path.exists():
        snap = json.loads(ds_path.read_text(encoding="utf-8"))
        lm = {r["Driver"]["driverId"]: float(r["points"])
              for r in (snap.get("standings") or {}).get("DriverStandings", [])}
        live_st = src.standings_after_round(season, rnd)
        rm = {r["Driver"]["driverId"]: float(r["points"]) for r in live_st["driver"]}
        for k in sorted(set(lm) | set(rm)):
            if lm.get(k) != rm.get(k):
                st_changes.append({"driver": k, "snapshot": lm.get(k), "live": rm.get(k)})

    race = local.get("raceName", "")
    rec = {
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "season": season, "round": rnd, "race": race,
        "race_date": local.get("date", ""), "race_time": local.get("time", ""),
        "snapshot_fetched_at": (json.loads(ds_path.read_text(encoding="utf-8")).get("fetched_at")
                                if ds_path.exists() else None),
        "result_changes": changes,
        "standings_changes": st_changes,
        "stable": not changes and not st_changes,
    }

    hrs = ""
    try:
        start = rc.to_taipei(local.get("date", ""), local.get("time", ""))
        delta = datetime.datetime.now(datetime.timezone.utc) - start.astimezone(datetime.timezone.utc)
        hrs = f"（賽後約 {delta.total_seconds()/3600:.1f} 小時）"
    except Exception:
        pass

    print(f"{race} R{rnd}{hrs}")
    if rec["stable"]:
        print(f"✅ 與快照一致：{len(a)} 筆賽果、積分榜均無變動")
    else:
        print(f"⚠️ 偵測到 {len(changes)} 筆賽果變動、{len(st_changes)} 筆積分變動：")
        for c in changes[:10]:
            print(f"   P{c['position']}  快照={c['snapshot']}  →  現在={c['live']}")
        for c in st_changes[:10]:
            print(f"   {c['driver']}  {c['snapshot']} → {c['live']}")
        print("   ⚠️ 已發布的稿子若引用了這些數字，現在是錯的。")

    if write_log:
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"   已記錄 → {LOG.relative_to(ROOT)}")
    return rec


def main():
    ap = argparse.ArgumentParser(description="賽後判罰偵測（重抓 vs 快照）")
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--season", type=int, default=rc.SEASON)
    ap.add_argument("--log", action="store_true", help="把這次結果附加進 reconcile-log.jsonl")
    args = ap.parse_args()
    rec = reconcile(args.season, args.round, args.log)
    if rec is None:
        return 2
    return 0 if rec["stable"] else 1


if __name__ == "__main__":
    sys.exit(main())
