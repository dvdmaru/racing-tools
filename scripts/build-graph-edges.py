#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-graph-edges.py — 百科線 M6：把 F1 圖的邊從 sqlite 一次物化成 data/f1/graph/edges.json。

**只做資料層，不做任何視覺**（不畫圖、不算佈局）。四種邊、單次 SQL、決定性輸出：

- won_championship  (driver → season)     ：逐季車手榜 position==1 且該季已完成
                                            （與 f1stats 冠軍定義一致：standings 層、非勝場）。
- drove_for         (driver → constructor)：per season，取自 results 的 distinct
                                            (season, driver_id, constructor_id)。
- raced_at          (driver → circuit)    ：distinct (driver_id, circuit_id)（賽果 join 賽事）。
- finished          (driver → race)       ：每一筆正賽賽果一條邊，帶 position（position_text，
                                            勝場判定的 canonical 欄位）。

決定性：每種邊都有顯式 ORDER BY，node id 前綴型別（driver:/season:/constructor:/circuit:/race:），
輸出 JSON 逐鍵穩定。跑兩次 byte-identical。檔頭 _meta 記錄來源、每型別筆數與 SQL 摘要。

節點 id 規則：
  driver:<driver_id>  season:<year>  constructor:<constructor_id>  circuit:<circuit_id>
  race:<season>-<round>

用法：python3 scripts/build-graph-edges.py            # 產 data/f1/graph/edges.json
      python3 scripts/build-graph-edges.py --check     # 只驗筆數與 sqlite 直查一致（不寫檔）
"""
import argparse
import json
import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "f1" / "db.sqlite"
OUT = ROOT / "data" / "f1" / "graph" / "edges.json"

# 每種邊：SQL（含顯式 ORDER BY，決定性）＋ row → edge dict 的映射。
EDGE_SPECS = {
    "won_championship": {
        "desc": "driver→season：逐季車手榜 position=1 且該季已完成",
        "sql": (
            "SELECT ds.driver_id AS driver_id, ds.season AS season "
            "FROM driver_standings ds JOIN seasons s ON s.year = ds.season "
            "WHERE ds.position = 1 AND s.status = 'completed' "
            "ORDER BY ds.season, ds.driver_id"
        ),
        "edge": lambda r: {
            "type": "won_championship",
            "from": f"driver:{r['driver_id']}",
            "to": f"season:{r['season']}",
        },
    },
    "drove_for": {
        "desc": "driver→constructor（per season）：results 的 distinct (season, driver, constructor)",
        "sql": (
            "SELECT DISTINCT season, driver_id, constructor_id FROM results "
            "WHERE constructor_id IS NOT NULL "
            "ORDER BY season, driver_id, constructor_id"
        ),
        "edge": lambda r: {
            "type": "drove_for",
            "from": f"driver:{r['driver_id']}",
            "to": f"constructor:{r['constructor_id']}",
            "season": r["season"],
        },
    },
    "raced_at": {
        "desc": "driver→circuit：distinct (driver, circuit)（賽果 join 賽事）",
        "sql": (
            "SELECT DISTINCT r.driver_id AS driver_id, ra.circuit_id AS circuit_id "
            "FROM results r JOIN races ra ON ra.season = r.season AND ra.round = r.round "
            "ORDER BY r.driver_id, ra.circuit_id"
        ),
        "edge": lambda r: {
            "type": "raced_at",
            "from": f"driver:{r['driver_id']}",
            "to": f"circuit:{r['circuit_id']}",
        },
    },
    "finished": {
        "desc": "driver→race：每一筆正賽賽果一條邊，帶 position（position_text）",
        "sql": (
            "SELECT season, round, driver_id, position_text FROM results "
            "ORDER BY season, round, "
            # position_text 可能是 '1'..'20' 或 'R'/'D'/'W' 等非數字——先按數字位序、"
            # 再按原文，維持穩定；driver_id 收尾保證唯一序。
            "CASE WHEN position_text GLOB '[0-9]*' THEN CAST(position_text AS INTEGER) "
            "ELSE 9999 END, position_text, driver_id"
        ),
        "edge": lambda r: {
            "type": "finished",
            "from": f"driver:{r['driver_id']}",
            "to": f"race:{r['season']}-{r['round']}",
            "season": r["season"],
            "round": r["round"],
            "position": r["position_text"],
        },
    },
}
EDGE_ORDER = ["won_championship", "drove_for", "raced_at", "finished"]


def collect(conn):
    """回 (edges:list, counts:dict)。edges 依 EDGE_ORDER 串接，每型別內走各自 ORDER BY。"""
    edges = []
    counts = {}
    for name in EDGE_ORDER:
        spec = EDGE_SPECS[name]
        rows = conn.execute(spec["sql"]).fetchall()
        block = [spec["edge"](r) for r in rows]
        counts[name] = len(block)
        edges.extend(block)
    return edges, counts


def build(check_only=False):
    if not DB.exists():
        raise SystemExit(f"⛔ 找不到 sqlite：{DB}（先跑 build-f1-db.py）")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        edges, counts = collect(conn)
    finally:
        conn.close()

    doc = {
        "_meta": {
            "generated_from": "data/f1/db.sqlite",
            "description": "F1 百科圖的邊物化（M6）；只有資料層、無視覺。node id 前綴型別。",
            "node_id_scheme": {
                "driver": "driver:<driver_id>",
                "season": "season:<year>",
                "constructor": "constructor:<constructor_id>",
                "circuit": "circuit:<circuit_id>",
                "race": "race:<season>-<round>",
            },
            "edge_types": {name: EDGE_SPECS[name]["desc"] for name in EDGE_ORDER},
            "edge_order": EDGE_ORDER,
            "counts": counts,
            "total": len(edges),
        },
        "edges": edges,
    }

    if check_only:
        print(f"筆數：{counts}　total={len(edges)}")
        return doc

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"🕸️  edges → {OUT}")
    for name in EDGE_ORDER:
        print(f"    {name:18s} {counts[name]:6d}")
    print(f"    {'TOTAL':18s} {len(edges):6d}")
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只印筆數，不寫檔")
    args = ap.parse_args()
    build(check_only=args.check)


if __name__ == "__main__":
    main()
