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
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "f1" / "raw"
DB = ROOT / "data" / "f1" / "db.sqlite"


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


# ---------- 車手生涯（DB 路徑：L1 db.sqlite 的 results/driver_standings） ----------
# 上面的 driver_career/championships/seasons 讀 per-driver 賽果檔（drivers/<id>-results.json），
# 只有 4 位 seed 車手落地了這類檔。M5 要為 35 位歷代冠軍產頁，故新增這條 **DB 路徑**：讀
# build-f1-db.py 落地的全庫 results/driver_standings 表，對全 35 人（乃至全 881 車手）都成立。
# 兩條路徑讀的是不同 raw 檔（per-driver 檔 ↔ 全庫 results/*.json），彼此獨立；I5 dualpath
# 已對 4 seed 證明兩者逐欄一致（見 check-f1-invariants.py），故 DB 路徑不是自證。
# 產出的統計結構與 file 路徑完全相同（value==len(detail)、同 formula id、同 coverage），
# 頁面元件（stat_card / career_timeline）無須分辨來源。

def _fmt_points(v):
    """積分顯示：整數去掉 .0，分數（.5/.33 shared-drive）原樣保留。"""
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f == int(f) else str(round(f, 2)).rstrip("0").rstrip(".")


def connect_db(db=None):
    con = sqlite3.connect(str(db or DB))
    con.row_factory = sqlite3.Row
    return con


def _race_detail(r):
    """一列賽果 → 明細 dict（逐場型）。source 指向全庫 results 原始檔。"""
    return {"season": r["season"], "round": r["round"],
            "race": r["name"] or f"Round {r['round']}",
            "pos": r["position_text"],
            "source": f"data/f1/raw/results/{r['season']}-{r['round']:02d}.json"}


def driver_career_db(did, con):
    """生涯勝場/頒獎台/出賽（DB 路徑）。value==len(detail)，明細帶來源與 season/round。"""
    rows = con.execute(
        "SELECT r.season AS season, r.round AS round, r.position_text AS position_text, "
        "       r.id AS id, ra.name AS name "
        "FROM results r LEFT JOIN races ra ON ra.season=r.season AND ra.round=r.round "
        "WHERE r.driver_id=? ORDER BY r.season, r.round, r.id", (did,)).fetchall()
    wins = [_race_detail(r) for r in rows if r["position_text"] == "1"]
    podiums = [_race_detail(r) for r in rows if r["position_text"] in ("1", "2", "3")]
    seen, entries = set(), []
    for r in rows:
        key = (r["season"], r["round"])
        if key in seen:
            continue  # 同場多列（1950s 共駕）計一場出賽（Fangio 58 列/51 場的教訓）
        seen.add(key)
        entries.append(_race_detail(r))
    return {
        "driver_id": did,
        "wins": _stat("derived", "results_position_text_eq_1", "1950-2026", wins),
        "podiums": _stat("derived", "results_position_text_in_123", "1950-2026", podiums),
        "entries": _stat("derived", "results_distinct_races", "1950-2026", entries),
    }


def driver_championships_db(did, con):
    """冠軍＝逐季車手榜 position==1 且該季已完成（DB 路徑）。與賽果層獨立（standings 表）。"""
    detail = []
    for r in con.execute(
            "SELECT ds.season AS season, ds.points AS points, ds.wins AS wins "
            "FROM driver_standings ds JOIN seasons s ON s.year=ds.season "
            "WHERE ds.driver_id=? AND ds.position=1 AND s.status='completed' "
            "ORDER BY ds.season", (did,)).fetchall():
        detail.append({"season": r["season"], "points": _fmt_points(r["points"]),
                       "wins_that_year": r["wins"],
                       "source": f"data/f1/raw/standings/driver-{r['season']}.json#pos1"})
    return _stat("derived", "count_seasons_driver_standing_eq_1", "1950-2026", detail)


def driver_seasons_db(did, con):
    """該車手參賽過的所有賽季（DB 路徑；用於生涯時間軸）。"""
    return sorted(r[0] for r in con.execute(
        "SELECT DISTINCT season FROM results WHERE driver_id=?", (did,)).fetchall())


def driver_meta_db(did, con):
    """車手身分欄（DB 路徑）：given/family name、國籍、生日、維基 URL。"""
    r = con.execute(
        "SELECT driver_id, given_name, family_name, nationality, dob, url "
        "FROM drivers WHERE driver_id=?", (did,)).fetchone()
    if r is None:
        raise KeyError(f"db 無此車手：{did}")
    return {"driverId": r["driver_id"], "givenName": r["given_name"] or "",
            "familyName": r["family_name"] or "", "nationality": r["nationality"] or "",
            "dateOfBirth": r["dob"] or "", "url": r["url"] or ""}


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
