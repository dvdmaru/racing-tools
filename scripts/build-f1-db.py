#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-f1-db.py — L0 raw → L1 sqlite（data/f1/db.sqlite）。

計畫 §三 的 L1 normalized 層：由 L0 raw 決定性重建，不 commit、可隨時重建。

三條硬紀律：
  1. **100% 離線**：只讀 data/f1/raw/，一個網路請求都不發。
  2. **決定性重建**：連跑兩次，`sqlite3 db.sqlite .dump` 必須逐 byte 相同。
     作法＝固定 CREATE 順序、固定 INSERT 排序、代理主鍵用自己的計數器依排序指派、
     完全不寫時間戳（raw 的 _meta.fetched_at 一律丟棄，不進 db）。
  3. **兩個必寫進註解的坑**（計畫 §三／§十二）：
       坑 A：DNF 車手的 `position` **仍有值**（那是分類名次），`positionText` 才是 'R'。
             **勝場判定一律用 position_text='1'，絕不能用 position=1。**
       坑 B：`points` 必須是 REAL——1950 年代 shared drive（兩人共駕一台車）帶 .5 分。
             用 INTEGER 會把 4.5 靜默截成 4，污染生涯積分與閉合測試。

用法：
  python3 scripts/build-f1-db.py                    # 產出 data/f1/db.sqlite
  python3 scripts/build-f1-db.py --db /tmp/x.sqlite # 指定輸出（測試用）
"""
import argparse
import glob
import json
import os
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "f1" / "raw"
DEFAULT_DB = ROOT / "data" / "f1" / "db.sqlite"


# ---------------------------------------------------------------------------
# 讀取工具（純讀，永不寫、永不連網）
# ---------------------------------------------------------------------------

def _load(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _entity_list(fname, key):
    return _load(RAW / "entities" / fname)[key]


def _sorted_race_files(subdir):
    """回傳 (season, round, path)，以 (season, round) 決定性排序。

    檔名格式 YYYY-RR.json；排序鍵用解析出的整數，不靠字串排序（避免補零陷阱）。
    """
    out = []
    for p in sorted(glob.glob(str(RAW / subdir / "*.json"))):
        stem = os.path.basename(p)[:-5]  # 去掉 .json
        season_s, round_s = stem.split("-")
        out.append((int(season_s), int(round_s), p))
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def _i(v):
    """字串轉 int；空／None／非數字回 None（存進 nullable INTEGER 欄）。"""
    if v is None:
        return None
    s = str(v).strip()
    return int(s) if s.lstrip("-").isdigit() else None


def _r(v):
    """字串轉 REAL；空／None 回 0.0。points 專用——坑 B。"""
    if v is None or str(v).strip() == "":
        return 0.0
    return float(v)


# ---------------------------------------------------------------------------
# Schema（計畫 §三 九表 + sprint_results）
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE seasons (
    year        INTEGER PRIMARY KEY,
    url         TEXT,
    status      TEXT NOT NULL          -- 'completed' | 'in_progress'（見 seasons_status）
);
CREATE TABLE circuits (
    circuit_id  TEXT PRIMARY KEY,
    name        TEXT,
    locality    TEXT,
    country     TEXT,
    lat         REAL,
    lng         REAL,
    url         TEXT
);
CREATE TABLE drivers (
    driver_id        TEXT PRIMARY KEY,
    code             TEXT,
    permanent_number TEXT,
    given_name       TEXT,
    family_name      TEXT,
    dob              TEXT,
    nationality      TEXT,
    url              TEXT
);
CREATE TABLE constructors (
    constructor_id  TEXT PRIMARY KEY,
    name            TEXT,
    nationality     TEXT,
    url             TEXT
);
CREATE TABLE races (
    season      INTEGER NOT NULL,
    round       INTEGER NOT NULL,
    name        TEXT,
    date        TEXT,
    circuit_id  TEXT,
    url         TEXT,
    PRIMARY KEY (season, round)
);
-- results / qualifying / sprint_results 用代理主鍵 id：
--   同一位車手可能在一場比賽出現兩列（1950s 中途換車接手，實測 83 例），
--   所以 (season,round,driver_id) 不唯一，不能當主鍵。id 由建置端依排序計數指派，
--   讓 .dump 決定性（rowid == id == 插入序）。
CREATE TABLE results (
    id            INTEGER PRIMARY KEY,
    season        INTEGER NOT NULL,
    round         INTEGER NOT NULL,
    number        TEXT,
    position      INTEGER,             -- 坑 A：DNF 也有分類名次，可能非 NULL
    position_text TEXT NOT NULL,       -- 坑 A：勝場判定唯一依據＝position_text='1'
    points        REAL NOT NULL,       -- 坑 B：REAL，shared drive 有 .5
    driver_id     TEXT NOT NULL,
    constructor_id TEXT,
    grid          INTEGER,
    laps          INTEGER,
    status        TEXT
);
CREATE TABLE qualifying (
    id            INTEGER PRIMARY KEY,
    season        INTEGER NOT NULL,
    round         INTEGER NOT NULL,
    number        TEXT,
    position      INTEGER,
    driver_id     TEXT NOT NULL,
    constructor_id TEXT,
    q1            TEXT,
    q2            TEXT,
    q3            TEXT
);
CREATE TABLE sprint_results (
    id            INTEGER PRIMARY KEY,
    season        INTEGER NOT NULL,
    round         INTEGER NOT NULL,
    number        TEXT,
    position      INTEGER,             -- 坑 A 同理
    position_text TEXT NOT NULL,       -- 勝場＝position_text='1'
    points        REAL NOT NULL,       -- 坑 B 同理
    driver_id     TEXT NOT NULL,
    constructor_id TEXT,
    grid          INTEGER,
    laps          INTEGER,
    status        TEXT
);
CREATE TABLE driver_standings (
    season          INTEGER NOT NULL,
    position        INTEGER,           -- 未列名（positionText='-'/'D'）者為 NULL
    position_text   TEXT NOT NULL,
    points          REAL NOT NULL,     -- 坑 B：官方冠軍積分（已扣分制的最終值）
    wins            INTEGER NOT NULL,
    driver_id       TEXT NOT NULL,
    constructor_ids TEXT,              -- 該季效力車隊（逗號連接，排序後）
    PRIMARY KEY (season, driver_id)
);
CREATE TABLE constructor_standings (
    season          INTEGER NOT NULL,
    position        INTEGER,
    position_text   TEXT NOT NULL,
    points          REAL NOT NULL,
    wins            INTEGER NOT NULL,
    constructor_id  TEXT NOT NULL,
    PRIMARY KEY (season, constructor_id)
);
"""


# ---------------------------------------------------------------------------
# 各表填充
# ---------------------------------------------------------------------------

def _scheduled_rounds_by_season():
    """entities/races.json：每季排定的 round 集合（含 2026 尚未跑的未來場）。"""
    by = {}
    for r in _entity_list("races.json", "Races"):
        by.setdefault(int(r["season"]), set()).add(int(r["round"]))
    return by


def _result_rounds_by_season():
    """實際有賽果檔的 round 集合。"""
    by = {}
    for s, rd, _ in _sorted_race_files("results"):
        by.setdefault(s, set()).add(rd)
    return by


def _season_status():
    """賽季完成度：所有排定 round 都有賽果 → completed；否則 in_progress。

    這是 f1stats._is_completed 的 db 版本，用意相同——**進行中賽季的榜首是
    『目前領先』不是『冠軍』**（2026 只跑到第 10 站）。實測只有 2026 是 in_progress。
    用 entities/races.json 當排程來源（涵蓋全 77 季，比 schedule 快照完整）。
    """
    sched = _scheduled_rounds_by_season()
    ran = _result_rounds_by_season()
    status = {}
    for year, rounds in sched.items():
        got = ran.get(year, set())
        status[year] = "completed" if rounds and rounds <= got else "in_progress"
    return status


def _fill_seasons(cur):
    status = _season_status()
    rows = []
    for s in _entity_list("seasons.json", "Seasons"):
        year = int(s["season"])
        rows.append((year, s.get("url"), status.get(year, "completed")))
    rows.sort(key=lambda t: t[0])
    cur.executemany("INSERT INTO seasons VALUES (?,?,?)", rows)


def _fill_circuits(cur):
    rows = []
    for c in _entity_list("circuits.json", "Circuits"):
        loc = c.get("Location", {})
        rows.append((c["circuitId"], c.get("circuitName"), loc.get("locality"),
                     loc.get("country"), _r(loc.get("lat")) if loc.get("lat") else None,
                     _r(loc.get("long")) if loc.get("long") else None, c.get("url")))
    rows.sort(key=lambda t: t[0])
    cur.executemany("INSERT INTO circuits VALUES (?,?,?,?,?,?,?)", rows)


def _fill_drivers(cur):
    rows = []
    for d in _entity_list("drivers.json", "Drivers"):
        rows.append((d["driverId"], d.get("code"), d.get("permanentNumber"),
                     d.get("givenName"), d.get("familyName"), d.get("dateOfBirth"),
                     d.get("nationality"), d.get("url")))
    rows.sort(key=lambda t: t[0])
    cur.executemany("INSERT INTO drivers VALUES (?,?,?,?,?,?,?,?)", rows)


def _fill_constructors(cur):
    rows = []
    for c in _entity_list("constructors.json", "Constructors"):
        rows.append((c["constructorId"], c.get("name"), c.get("nationality"), c.get("url")))
    rows.sort(key=lambda t: t[0])
    cur.executemany("INSERT INTO constructors VALUES (?,?,?,?)", rows)


def _fill_races(cur):
    rows = []
    for r in _entity_list("races.json", "Races"):
        rows.append((int(r["season"]), int(r["round"]), r.get("raceName"),
                     r.get("date"), r.get("Circuit", {}).get("circuitId"), r.get("url")))
    rows.sort(key=lambda t: (t[0], t[1]))
    cur.executemany("INSERT INTO races VALUES (?,?,?,?,?,?)", rows)


def _fill_race_table(cur, subdir, list_key, table, is_qual):
    """results / sprint_results / qualifying 共用填充。

    依 (season, round) 排序檔案、檔內保持 JSON 陣列原序，id 由計數器依此序指派——
    這是 .dump 決定性的關鍵：兩次建置的插入序完全相同 → rowid 相同 → dump 相同。
    """
    rows = []
    idc = 0
    for season, rnd, path in _sorted_race_files(subdir):
        data = _load(path)
        for row in data.get(list_key, []):
            idc += 1
            drv = row.get("Driver", {}).get("driverId")
            con = row.get("Constructor", {}).get("constructorId")
            if is_qual:
                rows.append((idc, season, rnd, row.get("number"),
                             _i(row.get("position")), drv, con,
                             row.get("Q1"), row.get("Q2"), row.get("Q3")))
            else:
                rows.append((idc, season, rnd, row.get("number"),
                             _i(row.get("position")), row.get("positionText"),
                             _r(row.get("points")), drv, con,
                             _i(row.get("grid")), _i(row.get("laps")), row.get("status")))
    if is_qual:
        cur.executemany(f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    else:
        cur.executemany(f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def _fill_driver_standings(cur):
    rows = []
    for p in sorted(glob.glob(str(RAW / "standings" / "driver-*.json"))):
        year = int(os.path.basename(p)[len("driver-"):-len(".json")])
        for row in _load(p).get("DriverStandings", []):
            cons = sorted(c.get("constructorId", "") for c in row.get("Constructors", []))
            rows.append((year, _i(row.get("position")), row.get("positionText", ""),
                         _r(row.get("points")), _i(row.get("wins")) or 0,
                         row["Driver"]["driverId"], ",".join(cons)))
    rows.sort(key=lambda t: (t[0], t[5]))
    cur.executemany("INSERT INTO driver_standings VALUES (?,?,?,?,?,?,?)", rows)


def _fill_constructor_standings(cur):
    rows = []
    for p in sorted(glob.glob(str(RAW / "standings" / "constructor-*.json"))):
        year = int(os.path.basename(p)[len("constructor-"):-len(".json")])
        for row in _load(p).get("ConstructorStandings", []):
            rows.append((year, _i(row.get("position")), row.get("positionText", ""),
                         _r(row.get("points")), _i(row.get("wins")) or 0,
                         row["Constructor"]["constructorId"]))
    rows.sort(key=lambda t: (t[0], t[5]))
    cur.executemany("INSERT INTO constructor_standings VALUES (?,?,?,?,?,?)", rows)


def build(db_path):
    db_path = pathlib.Path(db_path)
    if db_path.exists():
        db_path.unlink()          # 全量重建，不做增量（決定性）
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.executescript(SCHEMA)
        _fill_seasons(cur)
        _fill_circuits(cur)
        _fill_drivers(cur)
        _fill_constructors(cur)
        _fill_races(cur)
        n_res = _fill_race_table(cur, "results", "Results", "results", False)
        n_qual = _fill_race_table(cur, "qualifying", "QualifyingResults", "qualifying", True)
        n_spr = _fill_race_table(cur, "sprint", "SprintResults", "sprint_results", False)
        _fill_driver_standings(cur)
        _fill_constructor_standings(cur)
        con.commit()
        counts = {t: cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in (
            "seasons", "circuits", "drivers", "constructors", "races",
            "results", "qualifying", "sprint_results",
            "driver_standings", "constructor_standings")}
        counts["driver_standings_seasons"] = cur.execute(
            "SELECT count(DISTINCT season) FROM driver_standings").fetchone()[0]
        counts["constructor_standings_seasons"] = cur.execute(
            "SELECT count(DISTINCT season) FROM constructor_standings").fetchone()[0]
    finally:
        con.close()
    return counts


def main():
    ap = argparse.ArgumentParser(description="L0 raw → L1 sqlite（決定性、離線）")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="輸出 sqlite 路徑")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    counts = build(a.db)
    if not a.quiet:
        print(f"✅ 建置完成：{a.db}")
        for k, v in counts.items():
            print(f"  {k:32s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
