#!/usr/bin/env python3
"""11 支 2026 現役車隊的 Wikipedia infobox 對照與 default-deny 裁決 gate。

維基只是一條外部編纂對照路徑，不是獨立 oracle。快照固定 MediaWiki revid；報告裡每個
diff 都必須有唯一、具名、指紋綁定且非 PENDING 的裁決才可解除。`ours_wrong` 永不解除。
"""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import re
import sqlite3
import sys
import time
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DB = ROOT / "data" / "f1" / "db.sqlite"
REPORT = ROOT / "data" / "f1" / "constructor-crosscheck-report.json"
VERDICTS = ROOT / "config" / "f1-constructor-verdicts.json"
CACHE = ROOT / "data" / "f1" / "wiki-cache" / "constructors"
AS_OF = {"season": 2026, "round": 11}


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fs = _load("f1stats_constructor_crosscheck", "f1stats.py")
cc = _load("driver_crosscheck_network", "crosscheck-wikipedia.py")

DEFINITION_REGISTRY = {
    "count_seasons_constructor_standing_eq_1": {
        "formula": "count(completed seasons where constructor_standings.position==1)",
        "coverage": "1958-2026", "unit": "季",
    },
    "constructor_results_position_text_eq_1_distinct_races": {
        "formula": "count(distinct season-round where position_text=='1')",
        "coverage": "1950-2026", "unit": "場",
    },
    "constructor_results_position_text_in_123_distinct_cars": {
        "formula": "count(distinct season-round-position_text-number where position_text in ('1','2','3'))",
        "coverage": "1950-2026", "unit": "完賽車次",
    },
    "constructor_results_distinct_races": {
        "formula": "count(distinct season-round where a constructor results row exists)",
        "coverage": "1950-2026", "unit": "場",
        "caveat": "有賽果的不重複場次；Wikipedia Races entered 可能含未起跑報名",
    },
}
FIELD_DEFINITION_ID = {
    "championships_count": "count_seasons_constructor_standing_eq_1",
    "championships_years": "count_seasons_constructor_standing_eq_1",
    "wins": "constructor_results_position_text_eq_1_distinct_races",
    "podiums": "constructor_results_position_text_in_123_distinct_cars",
    "entries": "constructor_results_distinct_races",
}
COMPARED_FIELDS = ("championships_count", "championships_years", "wins", "podiums", "entries")
RESOLVING_VERDICTS = {"definition_differs", "wiki_wrong"}
VALID_VERDICTS = RESOLVING_VERDICTS | {"ours_wrong"}


def connect(db=DB):
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    return con


def roster(con):
    return [r[0] for r in con.execute(
        "SELECT DISTINCT constructor_id FROM results WHERE season=2026 ORDER BY constructor_id")]


def computed(cid, con):
    career = fs.constructor_career_db(cid, con, as_of=AS_OF)
    champ = fs.constructor_championships_db(cid, con, as_of=AS_OF)
    return {
        "championships_count": champ["value"],
        "championships_years": [d["season"] for d in champ["detail"]],
        "wins": career["wins"]["value"],
        "podiums": career["podiums"]["value"],
        "entries": career["entries"]["value"],
    }


def title_from_url(url):
    return urllib.parse.unquote(url.split("/wiki/", 1)[1])


def _snapshot(path, *, entity_id=None, title, url, wikitext, status, resolved, revid):
    meta = {"title": title, "resolved_title": resolved, "url": url, "http_status": status,
            "revid": revid, "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if entity_id is not None:
        meta["constructor_id"] = entity_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"_meta": meta, "wikitext": wikitext}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def get_wikitext(cid, title, url, cache_dir=CACHE, refresh=False):
    path = pathlib.Path(cache_dir) / f"{cid}.json"
    if path.exists() and not refresh:
        blob = json.loads(path.read_text(encoding="utf-8"))
        return blob["wikitext"], True, blob["_meta"].get("revid")
    time.sleep(0.2)
    wt, status, resolved, revid = cc.fetch_wikitext_api(title)
    _snapshot(path, entity_id=cid, title=title, url=url, wikitext=wt, status=status,
              resolved=resolved, revid=revid)
    return wt, False, revid


def get_f1cstat(cache_dir=CACHE, refresh=False):
    path = pathlib.Path(cache_dir) / "_f1cstat.json"
    if path.exists() and not refresh:
        blob = json.loads(path.read_text(encoding="utf-8"))
        return blob["wikitext"], True, blob["_meta"].get("revid")
    time.sleep(0.2)
    title = "Template:F1cstat"
    wt, status, resolved, revid = cc.fetch_wikitext_api(title)
    _snapshot(path, title=title, url="https://en.wikipedia.org/wiki/Template:F1cstat",
              wikitext=wt, status=status, resolved=resolved, revid=revid)
    return wt, False, revid


def _balanced_template(text, start):
    depth, i = 0, start
    while i < len(text) - 1:
        pair = text[i:i + 2]
        if pair == "{{":
            depth += 1
            i += 2
        elif pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return text[start:i]
        else:
            i += 1
    return None


def find_infobox(wikitext):
    """優先 constructor infobox；沒有才取 team infobox，並回傳實際格式。"""
    for kind, pattern in (
        ("Infobox F1 constructor", r"\{\{\s*Infobox\s+F1\s+constructor\b"),
        ("Infobox F1 team", r"\{\{\s*Infobox\s+F1\s+team\b"),
    ):
        match = re.search(pattern, wikitext, re.I)
        if match:
            return _balanced_template(wikitext, match.start()), kind
    return None, None


def parse_params(infobox):
    """只切 infobox 最外層參數；巢狀模板內的 `|` 不會被誤切。"""
    out, depth, start = {}, 0, 2
    pieces = []
    i = 2
    while i < len(infobox) - 2:
        pair = infobox[i:i + 2]
        if pair == "{{":
            depth += 1
            i += 2
        elif pair == "}}" and depth:
            depth -= 1
            i += 2
        elif infobox[i] == "|" and depth == 0:
            pieces.append(infobox[start:i])
            start = i + 1
            i += 1
        else:
            i += 1
    pieces.append(infobox[start:-2])
    for piece in pieces[1:]:
        if "=" in piece:
            key, value = piece.split("=", 1)
            out[key.strip().lower()] = value.strip()
    return out


def parse_f1cstat_registry(wikitext):
    """解析 Template:F1cstat 的兩層 switch；只接受字面數字，其他值具名縮減 coverage。"""
    registry, code = {}, None
    for line in wikitext.splitlines():
        m = re.match(r"\s*\|\s*([A-Z0-9]{3})\s*=\s*\{\{.*#switch", line)
        if m:
            code = m.group(1)
            registry[code] = {}
            continue
        if code is not None:
            f = re.match(r"\s*\|\s*([a-z_]+)\s*=\s*(.*?)\s*$", line, re.I)
            if f:
                value = re.sub(r"\{\{Coltit\|.*?\}\}", "", f.group(2), flags=re.I).strip()
                if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
                    registry[code][f.group(1).lower()] = float(value) if "." in value else int(value)
            if line.strip() == "}}":
                code = None
    return registry


def _template_stat(raw, registry, expected_field):
    matches = re.findall(r"\{\{\s*F1cstat\s*\|\s*([A-Z0-9]{3})\s*\|\s*([a-z_]+)\s*\}\}",
                         raw, re.I)
    for code, field in matches:
        if field.lower() == expected_field:
            value = registry.get(code.upper(), {}).get(field.lower())
            return value, code.upper(), "F1cstat"
    m = re.search(r"(?<!\d)(\d+)(?:\.\d+)?", raw)
    return (int(m.group(1)), None, "literal") if m else (None, None, "unresolved")


def parse_infobox(wikitext, registry):
    infobox, kind = find_infobox(wikitext)
    if not infobox:
        return {"found": False, "infobox_type": None, "fields": {}, "reductions": ["infobox:not_found"]}
    params = parse_params(infobox)
    reductions = []
    champ_raw = params.get("cons_champ", "")
    count_match = re.search(r"(?<!\d)(\d+)", champ_raw)
    champ_count = int(count_match.group(1)) if count_match else 0
    champ_years = sorted({int(y) for y in re.findall(r"\{\{\s*F1\s*\|\s*(\d{4})\s*\}\}", champ_raw, re.I)})
    fields = {
        "championships_count": {"value": champ_count, "raw": champ_raw, "format": "literal"},
        "championships_years": {"value": champ_years, "raw": champ_raw, "format": "literal"},
    }
    for name, raw_key, template_field in (
        ("wins", "wins", "wins"), ("podiums", "podiums", "podiums"),
        ("entries", "races", "entries"),
    ):
        raw = params.get(raw_key, "")
        value, code, fmt = _template_stat(raw, registry, template_field)
        fields[name] = {"value": value, "raw": raw, "format": fmt, "f1cstat_code": code}
        if value is None:
            reductions.append(f"{name}:{raw or '<missing>'}")
    return {"found": True, "infobox_type": kind, "fields": fields, "reductions": reductions}


def _diff(cid, name, field, ours, wiki, revid):
    definition_id = FIELD_DEFINITION_ID[field]
    if field == "entries":
        classification = "likely_definition_differs"
        reason = (f"我方有賽果的不重複場次={ours}，維基 Races entered={wiki}；entered 與 results-row "
                  "存在口徑差，且歷史 constructor_id 邊界可能不同")
    elif field in ("wins", "podiums"):
        classification = "likely_entity_scope_differs"
        reason = (f"我方依 constructor_id 的完賽車次={ours}，維基 constructor infobox={wiki}；"
                  "優先檢查歷史 constructor_id／team identity 邊界，不先改數字")
    else:
        classification = "needs_adjudication"
        reason = f"我方={ours}，維基={wiki}；冠軍定義或歷史實體邊界需人工裁決"
    return {"constructor_id": cid, "constructor_name": name, "field": field,
            "ours": ours, "wiki": wiki, "classification": classification, "reason": reason,
            "key": f"{cid}|{field}", "definition_id": definition_id, "wiki_revid": revid}


def build_report(db_path=DB, cache_dir=CACHE, refresh=False, quiet=False):
    global_before = cc.NET_REQUESTS
    con = connect(db_path)
    constructors, diffs, reductions = [], [], []
    n_cache = n_network = 0
    template, template_cached, template_revid = get_f1cstat(cache_dir, refresh)
    registry = parse_f1cstat_registry(template)
    try:
        ids = roster(con)
        for cid in ids:
            meta = fs.constructor_meta_db(cid, con)
            title = title_from_url(meta["url"])
            wt, cached, revid = get_wikitext(cid, title, meta["url"], cache_dir, refresh)
            n_cache += int(cached)
            n_network += int(not cached)
            parsed = parse_infobox(wt, registry)
            own = computed(cid, con)
            row_fields = {}
            for field in COMPARED_FIELDS:
                wiki_info = parsed.get("fields", {}).get(field, {})
                wiki = wiki_info.get("value")
                row_fields[field] = {"ours": own[field], "wiki": wiki,
                                     "wiki_raw": wiki_info.get("raw"),
                                     "wiki_format": wiki_info.get("format"),
                                     "f1cstat_code": wiki_info.get("f1cstat_code")}
                if wiki is not None and own[field] != wiki:
                    diffs.append(_diff(cid, meta["name"], field, own[field], wiki, revid))
            for reduction in parsed.get("reductions", []):
                reductions.append(f"{cid}.{reduction}")
            constructors.append({"constructor_id": cid, "name": meta["name"],
                                 "wikipedia_title": title, "wikipedia_url": meta["url"],
                                 "from_cache": cached, "wiki_revid": revid,
                                 "infobox_found": parsed["found"],
                                 "infobox_type": parsed["infobox_type"], "fields": row_fields})
            if not quiet:
                print(f"  {'cache' if cached else 'net'} {cid} rev={revid} {parsed['infobox_type']}")
    finally:
        con.close()
    by_field, by_class = {}, {}
    for diff in diffs:
        by_field[diff["field"]] = by_field.get(diff["field"], 0) + 1
        by_class[diff["classification"]] = by_class.get(diff["classification"], 0) + 1
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "en.wikipedia.org MediaWiki API — {{Infobox F1 constructor}} / {{Infobox F1 team}}",
        "note": "維基是外部編纂對照路徑，不是獨立 oracle；diff 必須具名且綁定 revid 裁決",
        "coverage": {"scope": "2026 grid 的 11 個 constructor_id",
                     "expected_constructor_count": len(constructors),
                     "expected_constructor_ids": [r["constructor_id"] for r in constructors],
                     "compared_fields": ["championships(count+years)", "wins", "podiums", "entries"],
                     "as_of": AS_OF, "f1cstat_template_revid": template_revid,
                     "f1cstat_coverage_reductions": sorted(reductions),
                     "blind_spots": ["Wikipedia 與 Jolpica 可能共享上游資料",
                                     "歷史 team／constructor_id 身分連續性不在本批修正"]},
        "definition_registry": DEFINITION_REGISTRY,
        "network": {"from_cache": n_cache, "from_network": n_network,
                    "f1cstat_from_cache": template_cached,
                    "total_api_requests_this_run": cc.NET_REQUESTS - global_before},
        "summary": {"constructors_checked": len(constructors), "diffs_total": len(diffs),
                    "diffs_by_field": by_field, "diffs_by_classification": by_class,
                    "f1cstat_coverage_reduction_count": len(reductions)},
        "diffs": diffs, "constructors": constructors,
    }


def _registry_sha(definition_id):
    return hashlib.sha256(json.dumps(DEFINITION_REGISTRY[definition_id], sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def diff_fingerprint(diff):
    payload = {k: diff.get(k) for k in (
        "key", "field", "ours", "wiki", "classification", "reason", "definition_id", "wiki_revid")}
    payload["definition_registry_sha256"] = _registry_sha(diff["definition_id"])
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def gate_diffs(report, verdict_doc, db_path=DB):
    faults = []
    con = connect(db_path)
    try:
        ids = roster(con)
        expected = report.get("coverage", {}).get("expected_constructor_ids", [])
        if ids != expected or len(ids) != 11 or len(set(expected)) != 11:
            faults.append(f"roster 非 2026 DB 雙向全等：db={ids} report={expected}")
        rows = report.get("constructors", [])
        if [r.get("constructor_id") for r in rows] != expected:
            faults.append("constructors 逐隊列與 coverage roster 不全等")
        if report.get("coverage", {}).get("as_of") != AS_OF:
            faults.append("coverage.as_of 必須是 {2026,11}")
        if report.get("coverage", {}).get("f1cstat_coverage_reductions"):
            faults.append("存在未解析的 Wikipedia 欄位 coverage 縮減")
        for row in rows:
            cid = row.get("constructor_id")
            if not row.get("infobox_found"):
                faults.append(f"{cid} infobox 未找到")
                continue
            own = computed(cid, con)
            for field in COMPARED_FIELDS:
                info = row.get("fields", {}).get(field)
                if not info or info.get("wiki") is None:
                    faults.append(f"{cid}.{field} 缺對照值")
                elif info.get("ours") != own[field]:
                    faults.append(f"{cid}.{field} report ours 已過期")
    finally:
        con.close()

    diffs = report.get("diffs", [])
    diff_map = {d.get("key"): d for d in diffs}
    if len(diff_map) != len(diffs) or None in diff_map:
        faults.append("diff key 缺失或重複")
    verdicts = verdict_doc.get("verdicts", [])
    verdict_map = {v.get("key"): v for v in verdicts}
    if len(verdict_map) != len(verdicts) or None in verdict_map:
        faults.append("verdict key 缺失或重複")
    if set(verdict_map) != set(diff_map):
        faults.append(f"verdict/diff exact-set 不符：缺 {sorted(set(diff_map)-set(verdict_map))} "
                      f"多 {sorted(set(verdict_map)-set(diff_map))}")
    for key, diff in diff_map.items():
        verdict = verdict_map.get(key, {})
        if verdict.get("verdict") not in VALID_VERDICTS:
            faults.append(f"{key} verdict 非法")
            continue
        if str(verdict.get("by", "")).upper().startswith("PENDING"):
            faults.append(f"{key} by=PENDING-charlie")
        if verdict.get("verdict") not in RESOLVING_VERDICTS:
            faults.append(f"{key} verdict={verdict.get('verdict')} 不解除 diff")
        for field in ("reason", "by", "date", "definition_id", "bound_fingerprint"):
            if not str(verdict.get(field, "")).strip():
                faults.append(f"{key} 缺 {field}")
        for vf, df in (("bound_ours", "ours"), ("bound_wiki", "wiki"),
                       ("wiki_revid", "wiki_revid"), ("definition_id", "definition_id")):
            if verdict.get(vf) != diff.get(df):
                faults.append(f"{key} {vf} 綁定失效")
        if verdict.get("bound_fingerprint") != diff_fingerprint(diff):
            faults.append(f"{key} bound_fingerprint 綁定失效")
    if faults:
        print(f"constructor verdict gate FAIL：{len(faults)} 項")
        for fault in faults[:30]:
            print(f"  - {fault}")
        return False
    print("constructor verdict gate PASS")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=pathlib.Path, default=DB)
    ap.add_argument("--out", type=pathlib.Path, default=REPORT)
    ap.add_argument("--verdicts", type=pathlib.Path, default=VERDICTS)
    ap.add_argument("--cache-dir", type=pathlib.Path, default=CACHE)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--gate-only", action="store_true")
    args = ap.parse_args()
    if args.gate_only:
        try:
            report = json.loads(args.out.read_text(encoding="utf-8"))
            verdicts = json.loads(args.verdicts.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"constructor verdict gate FAIL：{exc}")
            return 1
        return 0 if gate_diffs(report, verdicts, args.db) else 1
    report = build_report(args.db, args.cache_dir, args.refresh)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"constructors={report['summary']['constructors_checked']} "
          f"diffs={report['summary']['diffs_total']} requests={report['network']['total_api_requests_this_run']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
