#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-encyclopedia-freshness.py — 百科資料層 vs 週更資料層的賽曆同步 gate。

## 為什麼需要這一支（2026-08-03 事故）

這站有**兩層各自獨立的資料**在講同一件事：

  - 百科層　`data/f1/raw/` → `data/f1/db.sqlite`（凍結快照，由 refresh-f1-current.py 增量推進）
  - 週更層　`data/<season>/`（fetch_racing.py 每週重抓）

巴林站移師雪邦、2026 從 22 站變 23 站之後，週更層當天就變成 23 站，百科層卻停在
7/21 的 22 站快照整整兩週沒人發現。原因很單純：**沒有任何東西在比對這兩層。**

上週為了同型問題（同一事實全站兩個值）建的 `check-site-facts.py` 補不到這塊地——
它掃的是 `public-racing/` 產物與 `articles/` 文字，**掃不到 sqlite**。百科層在
`config/encyclopedia.json` 的 `published:false` 期間又完全不產頁，於是連間接的痕跡
都不會留下：這塊地在公開日之前是零守衛的，而公開日當天才發現賽曆錯一站，
就是帶著錯資料上線。

## 設計取捨

1. **比對兩個獨立落地的資料源，不比對推算值。** 站數、每站 round→raceName、
   已完賽場數，三項都是各自那層直接讀得到的東西。`check-site-facts.py` 的教訓是
   它自己的推算值先錯（見該檔 compute_truths 註解），所以這裡刻意不算「剩餘站數」
   這類衍生值——衍生值要驗的是它的算式，不是這支 gate 的職責。

2. **不判誰對誰錯，只判「不一致」。** 兩層都可能是落後的那一邊（百科沒跑 refresh／
   週更當週還沒抓）。gate 的職責是叫人來看，不是自己選一邊當真值——自動挑一邊
   同步過去，等於把「兩層獨立驗證」這件事本身廢掉。

3. **季別從 `config/site.json` 的 `season` 讀。** 換季只改那一個檔，這支跟著走；
   寫死年份的 gate 換季當天就會開始驗錯的東西。

4. **輸入缺一不可，缺了就是 FAIL 不是 PASS。** db 或 schedule 讀不到 → exit 1。
   「找不到檔案就安靜通過」是 gate 腐蝕的標準死法（永遠亮綠＝沒在看）。

## 這支守得住什麼／守不住什麼

守：兩層的站數不同、同一 round 指向不同分站、已完賽場數不同步（＝百科少吃了一場賽果）。
不守：兩層**同時**錯（都源自 jolpica，上游改錯它看不出來——那是
      crosscheck-wikipedia.py 與 known_exceptions 具名斷言的職責）；
      單場賽果的內容對錯（那是 check-f1-invariants.py 的 I1–I12）。

用法：
    python3 scripts/check-encyclopedia-freshness.py
    python3 scripts/check-encyclopedia-freshness.py --season 2026
    python3 scripts/check-encyclopedia-freshness.py --db /tmp/x.sqlite --data-dir /tmp/data
exit code：0 = 兩層一致；1 = 不一致或輸入缺漏。
"""
import argparse
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "f1" / "db.sqlite"
DEFAULT_DATA = ROOT / "data"


class InputMissing(Exception):
    """輸入檔缺漏。單獨一類，因為它要走 FAIL 而不是「沒東西可比＝通過」。"""


def db_calendar(db_path, season):
    """百科層賽曆：{round: raceName}。"""
    db_path = pathlib.Path(db_path)
    if not db_path.exists():
        raise InputMissing(f"找不到百科資料庫 {db_path}")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT round, name FROM races WHERE season=? ORDER BY round", (season,)
        ).fetchall()
        done = con.execute(
            "SELECT count(DISTINCT round) FROM results WHERE season=?", (season,)
        ).fetchone()[0]
    finally:
        con.close()
    return {int(r): n for r, n in rows}, int(done)


def schedule_calendar(data_dir, season):
    """週更層賽曆：{round: raceName}。round/season 在該層是字串，統一轉 int 再比。"""
    p = pathlib.Path(data_dir) / str(season) / "schedule.json"
    if not p.exists():
        raise InputMissing(f"找不到週更賽曆 {p}")
    races = json.loads(p.read_text(encoding="utf-8"))["races"]
    return {int(r["round"]): r.get("raceName") for r in races}


def schedule_completed(data_dir, season):
    """週更層已完賽場數＝正賽賽果檔數。

    ⚠️ glob 一定要 `round-[0-9][0-9].json`。寫成 `round-*.json` 會把
    `round-02-sprint.json` / `round-10-laps.json` / `round-10-pitstops.json`
    一起數進去——`check-site-facts.py` 的 compute_truths 就是這樣把 11 站算成 19 站的
    （見該檔註解）。同一個坑不踩第二次。
    """
    d = pathlib.Path(data_dir) / str(season) / "results"
    if not d.exists():
        return 0            # 賽季開跑前沒有 results 目錄，這是正常狀態不是缺輸入
    return len(list(d.glob("round-[0-9][0-9].json")))


def compare(db_cal, db_done, sched_cal, sched_done):
    """回人看得懂的問題清單（空清單＝一致）。兩邊都印出來，不預設誰是對的。"""
    problems = []

    if len(db_cal) != len(sched_cal):
        problems.append(
            f"站數不一致：百科 db {len(db_cal)} 站，週更 schedule.json {len(sched_cal)} 站")

    for rnd in sorted(set(db_cal) | set(sched_cal)):
        a, b = db_cal.get(rnd), sched_cal.get(rnd)
        if a == b:
            continue
        if a is None:
            problems.append(f"第 {rnd} 站：百科 db 沒有這一站，週更是「{b}」")
        elif b is None:
            problems.append(f"第 {rnd} 站：週更 schedule.json 沒有這一站，百科是「{a}」")
        else:
            problems.append(f"第 {rnd} 站對不上：百科「{a}」vs 週更「{b}」")

    if db_done != sched_done:
        problems.append(
            f"已完賽場數不一致：百科 db {db_done} 場，週更 results/round-NN.json {sched_done} 場"
            "（百科較少＝refresh-f1-current.py 沒跟上）")

    return problems


def run(db_path, data_dir, season):
    """回 (problems, note)。note 是印給人看的脈絡，不影響判定。"""
    db_cal, db_done = db_calendar(db_path, season)
    sched_cal = schedule_calendar(data_dir, season)
    sched_done = schedule_completed(data_dir, season)
    note = (f"百科 db：{len(db_cal)} 站／{db_done} 場有賽果　"
            f"週更層：{len(sched_cal)} 站／{sched_done} 場有賽果")
    return compare(db_cal, db_done, sched_cal, sched_done), note


def main():
    ap = argparse.ArgumentParser(
        description="百科 db.sqlite 與週更 data/<season>/ 的賽曆同步檢查。")
    ap.add_argument("--season", type=int, help="預設讀 config/site.json 的 season")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA))
    args = ap.parse_args()

    season = args.season or json.loads(
        (ROOT / "config" / "site.json").read_text(encoding="utf-8"))["season"]

    print(f"🔎 百科／週更兩層賽曆同步檢查（season={season}）")
    try:
        problems, note = run(args.db, args.data_dir, season)
    except InputMissing as e:
        # 讀不到就是 FAIL：安靜通過的 gate 等於沒有 gate。
        print(f"⛔ {e}\n   輸入缺漏一律判失敗——沒東西可比不等於一致。")
        return 1
    print(f"   {note}")

    if problems:
        print(f"\n⛔ {len(problems)} 處不一致：")
        for p in problems:
            print(f"  ❌ {p}")
        print("\n   兩層講同一件事就只能有一個值。處理順序："
              "①先確認哪一層落後（多半是百科沒跑 refresh-f1-current.py）"
              "②補跑該層的更新 ③兩層都對之後再重生頁面。"
              "\n   ⚠️ 不要直接把其中一層覆蓋成另一層——那會把兩層互相驗證這件事本身廢掉。")
        return 1

    print("\n✅ 百科層與週更層賽曆一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
