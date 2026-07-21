#!/usr/bin/env python3
"""f1stats.py — 生涯統計聚合（Phase 0 / 未來 M2 共用）。

★ 核心紀律（2026-07-20 圓桌 wins-bug 的教訓）：**不存任何 int 統計欄位。**
每個統計都是一個「明細 list」，數字一律 len()。這樣「賽前狀態」只能對明細 filter，
不可能對總計做減法——那個減法正是昨天產出「冠軍賽前已有同樣勝場」的來源。

每個統計欄位帶：value(=len(detail)) / kind / formula / coverage / detail(含來源路徑)。
頁面只讀這個結構，寫不出定義的欄位不上線。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "f1" / "raw"


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def _completed_seasons():
    """只有『已跑完』的賽季，其榜首才算冠軍。

    ⚠️ 進行中的賽季（本例 2026 只跑 10/22 站）榜首是『目前領先』不是『冠軍』，
    算進去會多給一座（2026-07-21 抓到：賓士被算成 9 冠、安東內利被算成一座車手冠軍）。
    判定：某季有 results 檔的最大 round == 該季 schedule 的站數，才算跑完。
    抓不到 schedule 的老賽季一律視為已完成（歷史資料是凍結的）。
    """
    done = set()
    for p in sorted((RAW / "standings").glob("driver-*.json")):
        year = int(p.stem.split("-")[1])
        sched = RAW / f"season-{year}-schedule.json"
        if not sched.exists():
            done.add(year)  # 沒抓 schedule 的歷史季視為完成
            continue
        planned = len(json.loads(sched.read_text(encoding="utf-8")).get("Races", []))
        ran = [int(rp.stem.split("-")[1]) for rp in (RAW / "results").glob(f"{year}-*.json")]
        if ran and max(ran) >= planned:
            done.add(year)
    return done


COMPLETED = None


def _is_completed(year):
    global COMPLETED
    if COMPLETED is None:
        COMPLETED = _completed_seasons()
    # 只有實際抓了 schedule+results 的年才判斷；其餘（未抓明細的歷史季）預設完成
    sched = RAW / f"season-{year}-schedule.json"
    return year in COMPLETED or not sched.exists()


def _stat(kind, formula, coverage, detail):
    """統計欄位的唯一建構路徑。value 一律由 len(detail) 產生，不接受外部傳入。"""
    return {"value": len(detail), "kind": kind, "formula": formula,
            "coverage": coverage, "detail": detail}


# ---------- 車手生涯（來源：drivers/<id>-results.json 逐場） ----------

def driver_career(did):
    src = f"data/f1/raw/drivers/{did}-results.json"
    races = _load(RAW / "drivers" / f"{did}-results.json")["Races"]

    def rows_where(pred):
        # ⚠️ 一場可能有多筆 Results（1950s 共駕/中途換車）——必須逐筆掃，
        # 只讀 [0] 會漏掉排在後面的勝場列（2026-07-21 維基對照輪抓到的潛伏 bug）
        out = []
        for r in races:
            for res in (r.get("Results") or []):
                if pred(res.get("positionText", ""), res):
                    out.append({"season": int(r["season"]), "round": int(r["round"]),
                                "race": r["raceName"], "pos": res.get("positionText"),
                                "source": f"{src}#{r['season']}-{r['round']}"})
        return out

    def distinct_races():
        # 出賽＝不重複場次：共駕一場兩列計一場（Fangio 58 列/51 場的教訓）。
        # 資料源不含未過排位（DNQ）的報名——這是與維基 races 欄的已知口徑差。
        seen, out = set(), []
        for r in races:
            key = (int(r["season"]), int(r["round"]))
            if key in seen or not r.get("Results"):
                continue
            seen.add(key)
            out.append({"season": key[0], "round": key[1], "race": r["raceName"],
                        "pos": r["Results"][0].get("positionText"),
                        "source": f"{src}#{r['season']}-{r['round']}"})
        return out

    wins = rows_where(lambda pt, _: pt == "1")
    podiums = rows_where(lambda pt, _: pt in ("1", "2", "3"))
    entries = distinct_races()
    # ⚠️ 「先發場次 starts」已移除（2026-07-21）：grid=="0" 在 Ergast 是 pit lane 起跑
    # （＝有出賽），不是「未上場」。實測 Verstappen 2016 摩納哥（pit lane 起跑後撞車退賽）
    # 被舊公式錯扣一場。DNS/withdrawn 的判定還纏著 positionText 'W'/status 多種表示法，
    # 寫不出精確定義的欄位不進 lib——這裡曾放過一版錯的，M2 要做 starts 先過定義關。

    return {
        "driver_id": did,
        "championships": None,  # 由 driver_championships() 從逐季榜補，見下
        "wins": _stat("derived", "results_position_text_eq_1", "1950-2026", wins),
        "podiums": _stat("derived", "results_position_text_in_123", "1950-2026", podiums),
        "entries": _stat("derived", "results_distinct_races", "1950-2026", entries),
    }


def driver_championships(did):
    """冠軍＝逐季『車手榜』position=='1'（不是勝場！）。來源是 standings 層，與賽果層獨立。"""
    detail = []
    for p in sorted((RAW / "standings").glob("driver-*.json")):
        year = int(p.stem.split("-")[1])
        data = _load(p)
        if not _is_completed(year):
            continue  # 進行中的賽季榜首是「領先」不是「冠軍」
        for row in data.get("DriverStandings", []):
            if row.get("Driver", {}).get("driverId") == did and row.get("position") == "1":
                detail.append({"season": year, "points": row.get("points"),
                               "wins_that_year": row.get("wins"),
                               "source": f"data/f1/raw/standings/driver-{year}.json#pos1"})
    return _stat("derived", "count_seasons_driver_standing_eq_1", "1950-2026", detail)


def driver_seasons(did):
    """該車手參賽過的所有賽季（用於生涯時間軸）。"""
    races = _load(RAW / "drivers" / f"{did}-results.json")["Races"]
    return sorted({int(r["season"]) for r in races})


# ---------- 車隊生涯（來源：standings/constructor-<year>.json 逐季） ----------

def constructor_championships(cid):
    detail = []
    for p in sorted((RAW / "standings").glob("constructor-*.json")):
        year = int(p.stem.split("-")[1])
        data = _load(p)
        if not _is_completed(year):
            continue  # 進行中的賽季榜首是「領先」不是「冠軍」
        for row in data.get("ConstructorStandings", []):
            if row.get("Constructor", {}).get("constructorId") == cid and row.get("position") == "1":
                detail.append({"season": year, "points": row.get("points"),
                               "wins_that_year": row.get("wins"),
                               "source": f"data/f1/raw/standings/constructor-{year}.json#pos1"})
    return _stat("derived", "count_seasons_constructor_standing_eq_1", "1958-2026", detail)


if __name__ == "__main__":
    import sys
    did = sys.argv[1] if len(sys.argv) > 1 else "michael_schumacher"
    c = driver_career(did)
    champ = driver_championships(did)
    print(f"{did}:")
    print(f"  冠軍 {champ['value']}（{[d['season'] for d in champ['detail']]}）")
    print(f"  勝場 {c['wins']['value']} / 頒獎台 {c['podiums']['value']} / 出賽 {c['entries']['value']}")
    print(f"  參賽賽季 {driver_seasons(did)[0]}–{driver_seasons(did)[-1]}")
