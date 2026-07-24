#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-season-intros.py — M6 第二棒：人工賽季導言的機械對帳。

對每篇 content/seasons/<year>.md 導言做兩層 gate：

  (1) 裸奔數字掃描：導言文中出現的每個阿拉伯數字（年份、分數、勝場、站數、含小數 395.5）
      都必須落在該篇 content/seasons/<year>.facts.json 之 **verified:true** claim 的值集合內。
      對不上 → 該數字裸奔 → 記一筆錯。

  (2) verified claim 重查：pack 內每個 verified:true 的 claim，按其 kind 走本檔內建的
      sqlite 查詢對 data/f1/db.sqlite **重算一次**，值對不上 → 記一筆錯。腳本不背書 pack 的
      claim value，一律以資料庫重查為準。

  external_history 句（常識性歷史背景，如「捨分制」「制度改組」）不進機械對帳；設計上這些句子
  不得攜帶被對帳的阿拉伯數字（若攜帶會在 (1) 被抓為裸奔，逼你改寫或補 verified claim）。

任一篇有錯 → 印出清單、exit 1；全綠 → exit 0。

用法：
  python3 scripts/check-season-intros.py            # 掃 content/seasons/ 全部導言
  python3 scripts/check-season-intros.py 2002 2021  # 只掃指定年份
"""
import json
import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "seasons"
DB_PATH = ROOT / "data" / "f1" / "db.sqlite"

# 阿拉伯數字 token（含小數：395.5、371.33）。中文序數（第二、前三）不含阿拉伯數字，不被擷取。
NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _num(x):
    """數值正規化：整值回 int（77.0→77）、非整值回 float（395.5）。比對前統一成 float。"""
    f = float(x)
    return int(f) if f.is_integer() else f


def extract_numbers(text: str):
    """回導言文中所有阿拉伯數字 token 的正規化數值 list（保留重複，供錯誤定位）。"""
    return [_num(m) for m in NUM_RE.findall(text)]


# ---------- 每種 claim kind 的 sqlite 重查（oracle）：回實際值，供與 pack value 比對 ----------

def _q1(con, sql, args=()):
    row = con.execute(sql, args).fetchone()
    return row[0] if row else None


def _season_max_single_race_points(con, year):
    """該季任一車手單場正賽最高得分（clinch 用的每場積分上限 proxy；2002＝10）。"""
    v = _q1(con, "SELECT MAX(points) FROM results WHERE season=?", (year,))
    return float(v or 0)


def _cumulative_through(con, year, driver_id, last_round):
    """該車手正賽＋衝刺賽積分累計至 last_round（含）。"""
    total = 0.0
    r = _q1(con, "SELECT COALESCE(SUM(points),0) FROM results "
                 "WHERE season=? AND driver_id=? AND round<=?", (year, driver_id, last_round))
    total += float(r or 0)
    s = _q1(con, "SELECT COALESCE(SUM(points),0) FROM sprint_results "
                 "WHERE season=? AND driver_id=? AND round<=?", (year, driver_id, last_round))
    total += float(s or 0)
    return total


def _clinch(con, year, driver_id):
    """回 (clinch_round, remaining)：逐站累計，首個「領先者領先第二名 ＞ 剩餘站數×單場最高分」的站次。
    領先者固定取該季最終冠軍（driver_id）；對不上（best-N 捨分季，累計≠官方）時仍以純累計計算，
    此 verifier 只用於明確 clinch 可算的季（呼叫方 pack 決定用不用）。"""
    total_rounds = int(_q1(con, "SELECT MAX(round) FROM races WHERE season=?", (year,)) or 0)
    ceiling = _season_max_single_race_points(con, year)
    # 該季有正賽 results 的參賽車手全集（含冠軍對手）
    others = [r[0] for r in con.execute(
        "SELECT DISTINCT driver_id FROM results WHERE season=? AND driver_id<>?", (year, driver_id))]
    for rnd in range(1, total_rounds + 1):
        lead = _cumulative_through(con, year, driver_id, rnd)
        rival_best = max((_cumulative_through(con, year, o, rnd) for o in others), default=0.0)
        remaining = total_rounds - rnd
        if lead - rival_best > remaining * ceiling:
            return rnd, remaining
    return None, None


def verify_claim(con, claim):
    """回 (ok, actual, detail)。actual = 資料庫重查值；ok = actual == claim['value']。"""
    kind = claim.get("kind")
    want = _num(claim["value"])
    year = None  # 由呼叫端注入（season）；這裡從 claim 或外層帶入

    def eq(actual):
        if actual is None:
            return False, actual
        return _num(actual) == want, _num(actual)

    yr = claim["_season"]
    if kind == "season_exists":
        got = _q1(con, "SELECT year FROM seasons WHERE year=?", (yr,))
        ok, actual = eq(got)
        return ok, actual, "seasons.year"
    if kind == "earliest_season":
        got = _q1(con, "SELECT MIN(year) FROM seasons")
        ok, actual = eq(got)
        return ok, actual, "MIN(seasons.year)"
    if kind == "season_rounds":
        got = _q1(con, "SELECT MAX(round) FROM races WHERE season=?", (yr,))
        ok, actual = eq(got)
        return ok, actual, "MAX(races.round)"
    if kind == "champion_points":
        got = _q1(con, "SELECT points FROM driver_standings WHERE season=? AND position=1", (yr,))
        ok, actual = eq(got)
        return ok, actual, "driver_standings P1 points"
    if kind == "runner_up_points":
        got = _q1(con, "SELECT points FROM driver_standings WHERE season=? AND position=2", (yr,))
        ok, actual = eq(got)
        return ok, actual, "driver_standings P2 points"
    if kind == "champion_wins":
        got = _q1(con, "SELECT wins FROM driver_standings WHERE season=? AND position=1", (yr,))
        ok, actual = eq(got)
        return ok, actual, "driver_standings P1 wins"
    if kind == "driver_podiums":
        did = claim["driver"]
        got = _q1(con, "SELECT COUNT(*) FROM results WHERE season=? AND driver_id=? "
                       "AND position_text IN ('1','2','3')", (yr, did))
        ok, actual = eq(got)
        return ok, actual, f"COUNT podiums {did}"
    if kind == "constructor_wins":
        cid = claim["constructor"]
        got = _q1(con, "SELECT COUNT(*) FROM results WHERE season=? AND constructor_id=? "
                       "AND position_text='1'", (yr, cid))
        ok, actual = eq(got)
        return ok, actual, f"COUNT wins {cid}"
    if kind == "no_constructor_championship":
        got = _q1(con, "SELECT COUNT(*) FROM constructor_standings WHERE season=?", (yr,))
        ok, actual = eq(got)
        return ok, actual, "COUNT constructor_standings"
    if kind == "clinch_round":
        rnd, _rem = _clinch(con, yr, claim["driver"])
        ok, actual = eq(rnd)
        return ok, actual, "clinch round"
    if kind == "clinch_remaining":
        _rnd, rem = _clinch(con, yr, claim["driver"])
        ok, actual = eq(rem)
        return ok, actual, "clinch remaining"
    if kind == "tied_before_final":
        total_rounds = int(_q1(con, "SELECT MAX(round) FROM races WHERE season=?", (yr,)) or 0)
        vals = [_cumulative_through(con, yr, d, total_rounds - 1) for d in claim["drivers"]]
        # 全員都等於 want 且彼此相等
        ok = all(_num(v) == want for v in vals) and len(set(vals)) == 1
        return ok, [_num(v) for v in vals], "cumulative before final"
    return False, None, f"未知 kind：{kind}"


# ---------- 單篇對帳 ----------

def check_year(year: int, con):
    """回 list[str] 錯誤訊息（空＝全綠）。"""
    errors = []
    md = CONTENT / f"{year}.md"
    facts = CONTENT / f"{year}.facts.json"
    if not md.exists():
        return [f"[{year}] 缺導言檔 {md.relative_to(ROOT)}"]
    if not facts.exists():
        return [f"[{year}] 缺 facts pack {facts.relative_to(ROOT)}"]

    text = md.read_text(encoding="utf-8")
    pack = json.loads(facts.read_text(encoding="utf-8"))
    claims = pack.get("claims", [])

    # 字數檢查（120–200，含標點；不計 ASCII 空白＝盤古之白/千分位空格）
    char_n = len(text.strip().replace(" ", ""))
    if not (120 <= char_n <= 200):
        errors.append(f"[{year}] 導言字數 {char_n} 不在 120–200（含標點、不計盤古之白）")

    verified = [c for c in claims if c.get("verified") is True]
    value_set = {_num(c["value"]) for c in verified}

    # (1) 裸奔數字：導言每個阿拉伯數字都要在 verified claim 值集合內
    for n in extract_numbers(text):
        if n not in value_set:
            errors.append(f"[{year}] 裸奔數字 {n}：未對應任何 verified claim（值集合 {sorted(value_set, key=str)}）")

    # (2) verified claim 重查
    for c in verified:
        c = {**c, "_season": pack.get("season", year)}
        try:
            ok, actual, detail = verify_claim(con, c)
        except Exception as e:  # noqa: BLE001
            errors.append(f"[{year}] claim kind={c.get('kind')} 重查失敗：{e}")
            continue
        if not ok:
            errors.append(f"[{year}] claim kind={c.get('kind')} value={c['value']} "
                          f"與 sqlite 重查不符（{detail}＝{actual}）")

    # external_history 句不得攜帶被對帳的阿拉伯數字裸奔（若有，設計上該補 verified claim）
    # —— 這裡不強制掃 external_history 字串（那是設計約束，非資料事實），僅保留註解說明。
    return errors


def main(argv):
    if not DB_PATH.exists():
        print(f"❌ 找不到 {DB_PATH}（先跑 build-f1-db.py）")
        return 1
    if argv:
        years = [int(a) for a in argv]
    else:
        years = sorted(int(p.stem) for p in CONTENT.glob("*.md")
                       if p.stem.isdigit())
    if not years:
        print("（content/seasons/ 無導言檔，略過）")
        return 0

    con = sqlite3.connect(DB_PATH)
    all_errors = []
    print("賽季導言機械對帳：")
    for y in years:
        errs = check_year(y, con)
        if errs:
            all_errors += errs
            print(f"  ✗ {y}：{len(errs)} 項不符")
        else:
            print(f"  ✓ {y}：全綠（每個數字對到 verified claim，且 claim 皆通過 sqlite 重查）")
    con.close()

    if all_errors:
        print("\n對帳失敗：")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    print(f"\n共 {len(years)} 篇導言全綠。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
