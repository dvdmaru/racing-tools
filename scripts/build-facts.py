#!/usr/bin/env python3
"""build-facts.py — 賽事內容線的第 ① 步：把寫稿要用的事實做成結構化 facts pack。

寫手（Sonnet 子代理）只准讀這份 JSON，禁 free recall。所以這裡的責任不只是「把數字倒出來」，
還要把**判斷規則算進資料層**——名次進退、退賽原因、積分榜領先權有沒有易主、哪些話不能寫，
全部變成欄位或 rule_notes。寫手需要填的洞越少，幻覺的空間就越小。

用法：
    python3 scripts/build-facts.py race-recap --round 11
    python3 scripts/build-facts.py race-recap --round 11 --season 2026

輸出：facts/race-recap-<season>-r<NN>.json

⚠️ 這份 pack 是「寫稿輸入」，不是「查核依據」。發布前的對帳一律走 check-facts.py，
   那支會重新打一次 API——用同一份資料驗自己等於幫錯誤蓋章。
"""
import argparse
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import racinglib as rc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
FACTS_DIR = ROOT / "facts"

# 正賽積分表（前十）。放這裡是為了讓 before/after 推導可驗證，不是給寫手抄的。
POINTS_RACE = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
POINTS_SPRINT = {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}

RULE_NOTES = [
    "本檔所有數字皆來自 jolpica-f1 API 落地快照；文中每一個數字都必須在本檔找得到，禁止憑記憶補。",
    "戰報只寫「發生了什麼」，不寫「為什麼」。輪胎策略、車隊決策、失誤歸因屬於賽後分析文型，不進戰報。",
    "紀錄型主張（本季最大、史上第一、隊史新高）除非本檔有 record_claims 支撐，否則一律降成畫面描述。",
    "車隊的內部意圖不可斷言；只能描述可觀察事實（進站圈數、名次變化、完賽狀態）。",
    "人名／車隊／賽道／站名一律中英對照（站規），中文在前、原文在後。",
    "站名不出現 F1 字樣；不引用官方素材；賽車紅用 #d63a2f。",
    "status 欄位的英文原文（Accident／Engine／+1 Lap）不要直譯成因果句，未完賽一律寫「未完賽」並附原因原文。",
]


def _die(msg):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def _points_of(entry, table):
    """以 API 給的 points 為準；缺漏才用名次表回推（回推值會標記出來）。"""
    raw = entry.get("points")
    if raw not in (None, ""):
        return float(raw), False
    try:
        pos = int(entry.get("position") or 0)
    except (TypeError, ValueError):
        return 0.0, True
    return float(table.get(pos, 0)), True


def _driver_block(d):
    return {
        "driver_id": d.get("driverId", ""),
        "code": d.get("code", ""),
        "zh": rc.driver_zh(d),
        "en_full": f"{d.get('givenName','')} {d.get('familyName','')}".strip(),
        "en_family": d.get("familyName", ""),
        "nationality": d.get("nationality", ""),
    }


def _team_block(c):
    return {
        "constructor_id": c.get("constructorId", ""),
        "zh": rc.team_zh(c.get("name", "")),
        "en": c.get("name", ""),
    }


def _accumulate(results_list, upto_round):
    """從落地的 results 檔累加積分，回 (driver_totals, constructor_totals)。
    用途不是取代 API standings，是拿來對帳——兩者對不上就代表有賽後判罰或快照過期，
    寧可當場報錯也不要讓寫手拿到自相矛盾的 before/after。"""
    dt, ct = {}, {}
    for rnd, race, sprint in results_list:
        if rnd > upto_round:
            continue
        for entry_src, table in ((race, POINTS_RACE), (sprint, POINTS_SPRINT)):
            if not entry_src:
                continue
            for e in entry_src.get("Results") or entry_src.get("SprintResults") or []:
                pts, _ = _points_of(e, table)
                did = (e.get("Driver") or {}).get("driverId", "")
                cid = (e.get("Constructor") or {}).get("constructorId", "")
                dt[did] = dt.get(did, 0.0) + pts
                ct[cid] = ct.get(cid, 0.0) + pts
    return dt, ct


def _standings_rows(standings_json, kind):
    """落地的 standings 快照 → [{id, zh, en, points, wins, position}]。

    快照外殼是 {season, fetched_at, data_through_round, standings:{DriverStandings:[...]}}，
    不是 Ergast 原生的 MRData 包裝——取錯層會拿到空 list，而空 list 會讓下游的一致性檢查
    真空通過（沒有元素自然沒有 mismatch）。所以取不到一律拋錯，不回空。
    """
    key = "DriverStandings" if kind == "driver" else "ConstructorStandings"
    inner = (standings_json or {}).get("standings") or {}
    raw = inner.get(key)
    if raw is None:  # 相容 Ergast 原生外殼
        lists = ((standings_json or {}).get("MRData", {})
                 .get("StandingsTable", {}).get("StandingsLists") or [])
        raw = lists[0].get(key) if lists else None
    if not raw:
        _die(f"讀不到 {key}——積分榜快照結構與預期不符，拒絕產生 facts pack"
             "（空榜會讓 before/after 與一致性檢查全部真空通過）")
    rows = []
    for r in raw:
        if kind == "driver":
            d = r.get("Driver") or {}
            ident, zh, en = d.get("driverId", ""), rc.driver_zh(d), d.get("familyName", "")
            team = ((r.get("Constructors") or [{}])[-1]).get("name", "")
        else:
            c = r.get("Constructor") or {}
            ident, zh, en, team = c.get("constructorId", ""), rc.team_zh(c.get("name", "")), c.get("name", ""), ""
        rows.append({
            "id": ident, "zh": zh, "en": en, "team_en": team,
            "position": int(r.get("position") or 0),
            "points": float(r.get("points") or 0),
            "wins": int(r.get("wins") or 0),
        })
    return rows


def _derive_before(rows, delta, top=5):
    """賽後榜 − 本站得分 ＝ 賽前榜。重排序後回前 N 名。
    直接減比讀舊快照可靠：舊快照的時間戳未必落在該站之前。"""
    before = []
    for r in rows:
        b = dict(r)
        b["points"] = round(r["points"] - delta.get(r["id"], 0.0), 2)
        before.append(b)
    before.sort(key=lambda x: (-x["points"], x["position"]))
    for i, b in enumerate(before, 1):
        b["position"] = i
    return before[:top]


def build_race_recap(season, rnd):
    results = rc.load_results(season)
    by_round = {r: (race, sprint) for r, race, sprint in results}
    if rnd not in by_round or by_round[rnd][0] is None:
        have = sorted(r for r, race, _ in results if race)
        _die(f"round {rnd} 的正賽結果尚未落地（現有完賽輪次：{have}）——排程還沒抓到就不要先寫稿")
    race, sprint = by_round[rnd]

    entries = race.get("Results") or []
    if len(entries) < 10:
        _die(f"round {rnd} 只有 {len(entries)} 筆完賽紀錄，資料不完整，拒絕產生 facts pack")

    circuit = race.get("Circuit") or {}
    cid = circuit.get("circuitId", "")

    # ---- 逐車結果（含名次進退，這是戰報的骨幹） ----
    rows, dnf, movers = [], [], []
    fastest = None
    for e in entries:
        d, c = e.get("Driver") or {}, e.get("Constructor") or {}
        try:
            pos = int(e.get("position") or 0)
        except (TypeError, ValueError):
            pos = 0
        try:
            grid = int(e.get("grid") or 0)
        except (TypeError, ValueError):
            grid = 0
        pts, inferred = _points_of(e, POINTS_RACE)
        status = e.get("status", "")
        ptext = e.get("positionText", "")
        # 完賽與否看 positionText 而非 status：positionText 是名次就代表獲判完賽名次，
        # "R" 才是退賽。status="Lapped" 的車手是被套圈但有完賽名次，寫成「退賽」是事實錯誤。
        classified = ptext.isdigit()
        # grid 0＝從維修站出發，名次進退對它沒有意義，不進 movers 排行
        gain = (grid - pos) if grid > 0 and pos > 0 and classified else None
        row = {
            "position": pos, "position_text": ptext,
            "driver": _driver_block(d), "constructor": _team_block(c),
            "grid": grid, "grid_note": "從維修站出發" if grid == 0 else "",
            "laps": int(e.get("laps") or 0),
            "status": status,
            "classified": classified,
            "finish_state": ("完賽" if status == "Finished" else
                             "完賽（遭套圈）" if classified else "未完賽"),
            "time": (e.get("Time") or {}).get("time", ""),
            "points": pts, "points_inferred": inferred,
            "grid_to_finish": gain,
        }
        fl = e.get("FastestLap") or {}
        if str(fl.get("rank")) == "1":
            fastest = {"driver": _driver_block(d), "constructor": _team_block(c),
                       "lap": int(fl.get("lap") or 0),
                       "time": (fl.get("Time") or {}).get("time", "")}
        rows.append(row)
        if not classified:
            dnf.append({"driver": _driver_block(d), "constructor": _team_block(c),
                        "laps": row["laps"], "status": status,
                        "note": "status 為英文原文，不要直譯成因果句"})
        if gain is not None:
            movers.append(row)

    movers.sort(key=lambda r: r["grid_to_finish"], reverse=True)

    # ---- 積分榜 before / after ----
    ds = rc.load_data(season, "driver-standings.json")
    cs = rc.load_data(season, "constructor-standings.json")
    d_rows, c_rows = _standings_rows(ds, "driver"), _standings_rows(cs, "constructor")

    d_delta = {}
    c_delta = {}
    for e in entries:
        pts, _ = _points_of(e, POINTS_RACE)
        d_delta[(e.get("Driver") or {}).get("driverId", "")] = \
            d_delta.get((e.get("Driver") or {}).get("driverId", ""), 0.0) + pts
        cid_ = (e.get("Constructor") or {}).get("constructorId", "")
        c_delta[cid_] = c_delta.get(cid_, 0.0) + pts

    # 對帳：API 榜 vs 從結果檔累加，對不上就是快照跨了輪次或有賽後判罰
    acc_d, acc_c = _accumulate(results, rnd)
    mismatch = [r["id"] for r in d_rows[:10]
                if abs(r["points"] - acc_d.get(r["id"], 0.0)) > 0.01]
    # 快照涵蓋到第幾輪必須等於本站——jolpica 的 standings round 欄位會指向「即將到來」的
    # 輪次，拿錯輪的榜去減本站得分，before/after 會整組錯位而且看起來很合理。
    through = (ds or {}).get("data_through_round")
    if through is not None and int(through) != rnd:
        _die(f"積分榜快照涵蓋到第 {through} 輪，但要寫的是第 {rnd} 輪——"
             "輪次錯位會讓 before/after 整組錯，先讓排程補齊再產 pack")
    integrity = {
        "standings_data_through_round": through,
        "standings_match_accumulated": not mismatch,
        "mismatched_driver_ids": mismatch,
        "note": ("積分榜與逐站累加一致" if not mismatch else
                 "⚠️ 積分榜與逐站累加不一致——可能是賽後判罰或快照落在別的輪次；"
                 "before/after 數字在人工確認前不得寫進文章"),
    }

    d_before = _derive_before(d_rows, d_delta)
    c_before = _derive_before(c_rows, c_delta)
    leader_change = bool(d_before and d_rows and d_before[0]["id"] != d_rows[0]["id"])

    # ---- 下一站 ----
    sched = rc.load_data(season, "schedule.json") or {}
    races = sched.get("races") or sched.get("Races") or []
    nxt = None
    for r in races:
        if int(r.get("round") or 0) == rnd + 1:
            nxt = {"round": rnd + 1, "zh": rc.race_zh(r.get("raceName", "")),
                   "en": r.get("raceName", ""), "date": r.get("date", ""),
                   "taipei": rc.taipei_disp(r.get("date", ""), r.get("time", "")),
                   "circuit_zh": rc.circuit_zh((r.get("Circuit") or {}).get("circuitId", "")),
                   "has_sprint": bool(r.get("Sprint"))}
            break

    pack = {
        "_type": "race-recap",
        "season": season,
        "round": rnd,
        "generated_from": "data/{}/results/round-{:02d}.json + driver/constructor-standings.json".format(season, rnd),
        "source": "jolpica-f1 API（Ergast 相容）落地快照",
        "rule_notes": RULE_NOTES,
        "integrity": integrity,
        "race": {
            "name_zh": rc.race_zh(race.get("raceName", "")),
            "name_en": race.get("raceName", ""),
            "circuit_zh": rc.circuit_zh(cid, circuit.get("circuitName", "")),
            "circuit_en": circuit.get("circuitName", ""),
            "locality": (circuit.get("Location") or {}).get("locality", ""),
            "country": (circuit.get("Location") or {}).get("country", ""),
            "date": race.get("date", ""),
            "taipei": rc.taipei_disp(race.get("date", ""), race.get("time", "")),
            "total_laps": max((r["laps"] for r in rows), default=0),
            "entries": len(rows),
        },
        "winner": rows[0] if rows else None,
        "podium": rows[:3],
        "top10": rows[:10],
        "full_results": rows,
        "fastest_lap": fastest,
        "dnf": dnf,
        "dnf_count": len(dnf),
        "biggest_gainers": movers[:3],
        "biggest_losers": [m for m in movers[-3:] if m["grid_to_finish"] < 0][::-1],
        "sprint": ({"results": [
            {"position": int(e.get("position") or 0),
             "driver": _driver_block(e.get("Driver") or {}),
             "constructor": _team_block(e.get("Constructor") or {}),
             "points": _points_of(e, POINTS_SPRINT)[0]}
            for e in (sprint.get("SprintResults") or sprint.get("Results") or [])[:8]]}
            if sprint else None),
        "standings": {
            "drivers_after": d_rows[:5],
            "drivers_before": d_before,
            "constructors_after": c_rows[:5],
            "constructors_before": c_before,
            "leader_change": leader_change,
            "driver_gap_after": (round(d_rows[0]["points"] - d_rows[1]["points"], 2)
                                 if len(d_rows) > 1 else None),
            "driver_gap_before": (round(d_before[0]["points"] - d_before[1]["points"], 2)
                                  if len(d_before) > 1 else None),
        },
        "next_race": nxt,
        "record_claims": [],  # 需要紀錄型主張時人工填入並附來源，空的就代表「不准寫」
    }
    return pack


def main():
    ap = argparse.ArgumentParser(description="產生寫稿用的 facts pack")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("race-recap", help="賽後戰報 facts pack")
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--season", type=int, default=rc.SEASON)
    args = ap.parse_args()

    if args.cmd == "race-recap":
        pack = build_race_recap(args.season, args.round)
        FACTS_DIR.mkdir(exist_ok=True)
        out = FACTS_DIR / f"race-recap-{args.season}-r{args.round:02d}.json"
        out.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"✅ {out.relative_to(ROOT)}")
        print(f"   {pack['race']['name_zh']}｜{pack['race']['entries']} 車完賽紀錄"
              f"｜退賽 {pack['dnf_count']}｜積分榜領先易主：{'是' if pack['standings']['leader_change'] else '否'}")
        if not pack["integrity"]["standings_match_accumulated"]:
            print(f"   ⚠️ {pack['integrity']['note']}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
