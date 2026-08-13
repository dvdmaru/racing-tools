#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standings L0 raw + Charlie 裁決覆寫的共用讀取／套用層。

L0 JSON 永遠唯讀；只有 ``by == 'charlie'`` 的條目能進入 L1 或生成器記憶體。
SQLite 建置與直接讀 standings JSON 的生成器共用同一套 validation、drift gate
與 default-deny 判定，避免兩條輸出路徑再次分岔。
"""
import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "f1" / "raw"
OVERRIDES = ROOT / "data" / "f1" / "standings-overrides.json"

TABLES = {
    "driver_standings": {
        "filename": "driver-{season}.json",
        "rows_key": "DriverStandings",
        "entity_key": "Driver",
        "id_key": "driverId",
        "db_key": "driver_id",
    },
    "constructor_standings": {
        "filename": "constructor-{season}.json",
        "rows_key": "ConstructorStandings",
        "entity_key": "Constructor",
        "id_key": "constructorId",
        "db_key": "constructor_id",
    },
}
ALLOWED_FIELDS = {table: {"position", "position_text", "points", "wins"}
                  for table in TABLES}
REQUIRED_FIELDS = {"table", "season", "entity_id", "field", "raw_value", "value",
                   "source_revid", "source_url", "reason", "by", "date"}


def _load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _i(value):
    if value is None:
        return None
    text = str(value).strip()
    return int(text) if text.lstrip("-").isdigit() else None


def _json_field(field):
    """L1 snake_case 欄名 → jolpica L0 JSON 欄名。"""
    return "positionText" if field == "position_text" else field


def _field_value(row, field):
    json_field = _json_field(field)
    if json_field not in row:
        raise ValueError(f"standings override field 不存在於 raw：{field}")
    if field == "points":
        return float(row[json_field]) if str(row[json_field]).strip() else 0.0
    if field in {"position", "wins"}:
        return _i(row[json_field])
    return row[json_field]


def _same_value(a, b):
    """JSON/SQLite 數值容錯比對；字串欄仍逐字相等。"""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def load_override_rows(path=OVERRIDES):
    """讀 override envelope；檔案不存在時等同沒有裁決。"""
    path = pathlib.Path(path)
    if not path.exists():
        return []
    blob = _load(path)
    rows = blob.get("overrides") if isinstance(blob, dict) else blob
    if not isinstance(rows, list):
        raise ValueError("standings-overrides.json 必須是 {overrides:[...]} 或陣列")
    return rows


def _approved_rows(overrides, target_table=None, target_season=None):
    """回已具名核准且符合可選目標的條目；其他 by 一律 default-deny。"""
    approved = []
    skipped_by = set()
    for item in overrides:
        by = item.get("by")
        if by != "charlie":
            if by != "PENDING-charlie":
                skipped_by.add(repr(by))
            continue
        missing = sorted(REQUIRED_FIELDS - set(item))
        if missing:
            raise ValueError(f"standings override 缺欄位：{missing}")
        table, field = item["table"], item["field"]
        if table not in ALLOWED_FIELDS or field not in ALLOWED_FIELDS[table]:
            raise ValueError(f"standings override 目標不允許：{table}.{field}")
        if target_table is not None and table != target_table:
            continue
        if target_season is not None and int(item["season"]) != int(target_season):
            continue
        approved.append(item)
    if skipped_by:
        print("WARNING: standings overrides skipped non-PENDING non-charlie by values: "
              + ", ".join(sorted(skipped_by)), file=sys.stderr)
    return approved


def _apply_adjudicated(overrides, raw_lookup, current_lookup, update_value,
                        target_table=None, target_season=None):
    """共用套用核心：同一套白名單、raw drift、stale 與 L0→consumer gate。"""
    applied = 0
    for item in _approved_rows(overrides, target_table, target_season):
        table, field = item["table"], item["field"]
        season, entity_id = int(item["season"]), item["entity_id"]
        actual_raw = raw_lookup(table, season, entity_id, field)
        if not _same_value(actual_raw, item["raw_value"]):
            raise RuntimeError(
                f"standings override drift：{table} {season} {entity_id} {field} "
                f"raw={actual_raw!r}，裁決綁定={item['raw_value']!r}")
        if _same_value(item["value"], item["raw_value"]):
            raise RuntimeError(
                f"standings override 已過期：{table} {season} {entity_id} {field}")
        current = current_lookup(table, season, entity_id, field)
        if not _same_value(current, actual_raw):
            raise RuntimeError(
                f"standings override L0→L1 漂移：{table} {season} {entity_id} {field}")
        update_value(table, season, entity_id, field, item["value"])
        applied += 1
    return applied


def _table_config(table):
    try:
        return TABLES[table]
    except KeyError as exc:
        raise ValueError(f"override table 不允許：{table}") from exc


def _find_document_row(document, table, entity_id):
    cfg = _table_config(table)
    for row in document.get(cfg["rows_key"], []):
        if row.get(cfg["entity_key"], {}).get(cfg["id_key"]) == entity_id:
            return row
    raise ValueError(f"override entity 不存在於 raw：{table} {entity_id}")


def raw_standings_value(table, season, entity_id, field, raw_dir=RAW):
    """直接從唯讀 L0 standings JSON 取正規化值，供 drift gate 使用。"""
    cfg = _table_config(table)
    path = pathlib.Path(raw_dir) / "standings" / cfg["filename"].format(season=season)
    row = _find_document_row(_load(path), table, entity_id)
    try:
        return _field_value(row, field)
    except ValueError as exc:
        raise ValueError(f"override field 不存在於 raw：{table}.{field}") from exc


def apply_standings_overrides(cur, overrides, raw_dir=RAW, raw_lookup=None):
    """套用裁決到 SQLite cursor；保留 build-f1-db 的既有公開介面。"""
    lookup = raw_lookup or (
        lambda table, season, entity, field:
        raw_standings_value(table, season, entity, field, raw_dir))

    def current(table, season, entity, field):
        cfg = _table_config(table)
        row = cur.execute(
            f"SELECT {field} FROM {table} WHERE season=? AND {cfg['db_key']}=?",
            (season, entity)).fetchone()
        return row[0] if row is not None else None

    def update(table, season, entity, field, value):
        cfg = _table_config(table)
        cur.execute(
            f"UPDATE {table} SET {field}=? WHERE season=? AND {cfg['db_key']}=?",
            (value, season, entity))

    return _apply_adjudicated(overrides, lookup, current, update)


def apply_standings_overrides_to_document(document, table, season, overrides):
    """在記憶體副本套用裁決並回 applied count；傳入的 L0 document 不落盤。"""
    raw_document = copy.deepcopy(document)

    def find(doc, wanted_table, entity):
        if wanted_table != table:
            raise ValueError(f"override table 不允許：{wanted_table}")
        return _find_document_row(doc, wanted_table, entity)

    def raw_lookup(wanted_table, wanted_season, entity, field):
        if int(wanted_season) != int(season):
            raise ValueError(f"override season 不符：{wanted_season} != {season}")
        return _field_value(find(raw_document, wanted_table, entity), field)

    def current_lookup(wanted_table, wanted_season, entity, field):
        return _field_value(find(document, wanted_table, entity), field)

    def update(wanted_table, wanted_season, entity, field, value):
        row = find(document, wanted_table, entity)
        json_field = _json_field(field)
        # 生成器沿用 L0 JSON schema：standings 數字原本是字串，就維持字串，避免
        # 69 被無意顯示成 69.0；SQLite wrapper 仍寫 REAL/INTEGER，不受此分支影響。
        if isinstance(row.get(json_field), str) and isinstance(value, (int, float)):
            number = float(value)
            row[json_field] = str(int(number)) if number.is_integer() else repr(value)
        else:
            row[json_field] = value

    return _apply_adjudicated(overrides, raw_lookup, current_lookup, update,
                               target_table=table, target_season=season)


def load_adjudicated_standings_document(table, season, raw_dir=RAW, overrides=None,
                                         overrides_path=OVERRIDES):
    """讀一季 standings 並只在記憶體套用 Charlie 裁決；L0 檔案保持 untouched。"""
    cfg = _table_config(table)
    path = pathlib.Path(raw_dir) / "standings" / cfg["filename"].format(season=season)
    if not path.exists():
        return {}
    document = _load(path)
    rows = load_override_rows(overrides_path) if overrides is None else overrides
    apply_standings_overrides_to_document(document, table, int(season), rows)
    return document


def load_adjudicated_standings(table, season, raw_dir=RAW, overrides=None,
                                overrides_path=OVERRIDES):
    """回生成器可直接消費的已裁決 standings rows。"""
    cfg = _table_config(table)
    document = load_adjudicated_standings_document(
        table, season, raw_dir=raw_dir, overrides=overrides, overrides_path=overrides_path)
    return document.get(cfg["rows_key"], [])
