#!/usr/bin/env python3
"""1950–1990 final standings external sweep and adjudicated override draft.

Only en.wikipedia.org is contacted. Every response is pinned by MediaWiki revid and cached under
data/f1/wiki-cache/seasons/. Replays are offline unless --refresh is requested. A season that cannot
be parsed or identity-matched is reported as UNPARSEABLE; it is never silently skipped.
"""
import argparse
import datetime as dt
import difflib
import json
import pathlib
import re
import sqlite3
import ssl
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from html.parser import HTMLParser

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "f1" / "db.sqlite"
CACHE = ROOT / "data" / "f1" / "wiki-cache" / "seasons"
RULES = ROOT / "data" / "f1" / "scoring-rules.json"
REPORT = ROOT / "data" / "f1" / "standings-crosscheck-report.json"
OVERRIDES = ROOT / "data" / "f1" / "standings-overrides.json"
ADJUDICATION = ROOT / "data" / "f1" / "standings-override-adjudication.md"
API = "https://en.wikipedia.org/w/api.php"
UA = "racing-tools/1.0 (racing.twtools.cc; non-commercial standings crosscheck)"
YEARS = range(1950, 1991)
POINT_EPSILON = 0.011  # jolpica rounds repeating shared-drive fractions to two decimals


class WikiTableParser(HTMLParser):
    """Small stdlib-only HTML table reader; CI needs no dependency beyond markdown."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heading_tag = None
        self.heading_buf = []
        self.heading = ""
        self.table_depth = 0
        self.capture_depth = None
        self.table = None
        self.tables = []
        self.row = None
        self.cell = None
        self.cell_tag = None
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"style", "script"}:
            self.ignored += 1
        if tag in {"h2", "h3", "h4"} and not self.table_depth:
            self.heading_tag, self.heading_buf = tag, []
        if tag == "table":
            self.table_depth += 1
            # Standings tables are often wrapped in a layout <table>; capture the first wikitable
            # at any depth, not only top-level tables.
            if self.table is None and "wikitable" in attrs.get("class", "").split():
                self.table = {"heading": self.heading, "rows": []}
                self.capture_depth = self.table_depth
        if self.table is not None and self.table_depth == self.capture_depth and tag == "tr":
            self.row = []
        if self.row is not None and tag in {"th", "td"}:
            self.cell, self.cell_tag = {"tag": tag, "text": [], "links": []}, tag
        if self.cell is not None and tag == "a":
            self.cell["links"].append({"href": attrs.get("href"), "title": attrs.get("title")})

    def handle_data(self, data):
        if self.ignored:
            return
        if self.heading_tag:
            self.heading_buf.append(data)
        if self.cell is not None:
            self.cell["text"].append(data)

    def handle_endtag(self, tag):
        if tag in {"style", "script"} and self.ignored:
            self.ignored -= 1
            return
        if self.heading_tag == tag:
            self.heading = _clean("".join(self.heading_buf))
            self.heading_tag, self.heading_buf = None, []
        if self.cell is not None and tag == self.cell_tag:
            self.cell["text"] = _clean("".join(self.cell["text"]))
            self.row.append(self.cell)
            self.cell, self.cell_tag = None, None
        if self.row is not None and tag == "tr":
            if self.row:
                self.table["rows"].append(self.row)
            self.row = None
        if tag == "table" and self.table_depth:
            if self.table is not None and self.table_depth == self.capture_depth:
                self.tables.append(self.table)
                self.table = None
                self.capture_depth = None
            self.table_depth -= 1


def _clean(s):
    return " ".join(str(s).replace("\xa0", " ").split())


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"\[[^]]*]", "", s)
    s = re.sub(r"\b(jr|sr)\.?\b", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _num(text):
    s = _clean(text).replace("−", "-").replace("½", " 1/2").replace("¼", " 1/4").replace("¾", " 3/4")
    s = s.replace("⁄", "/")
    s = re.sub(r"\[[^]]*]", "", s).replace("*", "").replace("†", "").replace("‡", "")
    # Standings often show championship points first and total earned points in parentheses.
    # The parenthetical may itself contain fractions (e.g. "42 (57+1/7)") and must not win parsing.
    s = re.sub(r"\([^)]*\)", "", s)
    plus_frac = re.search(r"(-?\d+(?:\.\d+)?)\s*\+\s*(\d+)\s*/\s*(\d+)", s)
    if plus_frac:
        return (float(plus_frac.group(1)) + float(plus_frac.group(2)) / float(plus_frac.group(3)))
    mixed = re.search(r"(-?\d+(?:\.\d+)?)\s+(\d+)\s*/\s*(\d+)", s)
    if mixed:
        return float(mixed.group(1)) + float(mixed.group(2)) / float(mixed.group(3))
    frac = re.search(r"(?<!\d)(\d+)\s*/\s*(\d+)", s)
    if frac:
        return float(frac.group(1)) / float(frac.group(2))
    m = re.search(r"-?\d+(?:\.\d+)?", s.replace(",", ""))
    return float(m.group()) if m else None


def _position(text):
    m = re.match(r"\s*(\d+)", text)
    return int(m.group(1)) if m else None


def fetch_snapshot(year, refresh=False, pause=0.35):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{year}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    title = f"{year} Formula One season"
    q = urllib.parse.urlencode({
        "action": "parse", "page": title, "redirects": "1", "prop": "text|wikitext|revid",
        "format": "json", "formatversion": "2"})
    delay = 5
    for attempt in range(5):
        if pause:
            time.sleep(pause)
        try:
            req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45, context=SSL_CTX) as res:
                payload, status = json.loads(res.read().decode("utf-8")), res.status
            if "error" in payload:
                raise RuntimeError(f"Wikipedia parse error {year}: {payload['error']}")
            page = payload["parse"]
            resolved = page["title"]
            blob = {
                "_meta": {"season": year, "title": title, "resolved_title": resolved,
                          "url": "https://en.wikipedia.org/wiki/" + resolved.replace(" ", "_"),
                          "http_status": status, "revid": page.get("revid"),
                          "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                "wikitext": page["wikitext"], "html": page["text"]}
            path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return blob
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < 4:
                retry = exc.headers.get("Retry-After", "")
                wait = int(retry) if retry.isdigit() else delay
                time.sleep(wait)
                delay = min(delay * 2, 180)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < 4:
                time.sleep(delay)
                delay = min(delay * 2, 180)
                continue
            raise
    raise RuntimeError(f"Wikipedia fetch exhausted: {year}")


def _pick_table(tables, entity):
    needles = ("driver",) if entity == "driver" else ("constructor", "manufacturer")
    candidates = []
    for table in tables:
        if not table["rows"]:
            continue
        header = " ".join(c["text"] for c in table["rows"][0]).lower()
        heading = table["heading"].lower()
        if ("standings" in heading and any(n in heading for n in needles) and "pos" in header
                and ("pts" in header or "points" in header)):
            candidates.append(table)
    if not candidates:
        return None
    return max(candidates, key=lambda t: len(t["rows"]))


def parse_standings(blob):
    parser = WikiTableParser()
    parser.feed(blob.get("html", ""))
    out = {}
    for entity in ("driver", "constructor"):
        table = _pick_table(parser.tables, entity)
        if table is None:
            out[entity] = None
            continue
        header = [c["text"].lower() for c in table["rows"][0]]
        pos_i = next((i for i, h in enumerate(header) if h.startswith("pos")), 0)
        entity_headers = (entity,) if entity == "driver" else ("constructor", "manufacturer")
        ent_i = next((i for i, h in enumerate(header) if any(x in h for x in entity_headers)), 1)
        rows = []
        last_position = None
        for cells in table["rows"][1:]:
            # Older tables contain decorative blank header cells that have no matching body cell;
            # final points is nevertheless always the last body cell.
            pts_i = len(cells) - 1
            if max(pos_i, ent_i, pts_i) >= len(cells):
                continue
            pos_text, name, points_text = cells[pos_i]["text"], cells[ent_i]["text"], cells[pts_i]["text"]
            points = _num(points_text)
            if not name or points is None:
                continue
            position = _position(pos_text)
            if position is not None:
                last_position = position
            elif pos_text.strip().startswith("="):
                position = last_position
            rows.append({"position": position, "position_text": pos_text,
                         "name": name, "points": points, "links": cells[ent_i]["links"]})
        out[entity] = rows or None
    return out


def _db_rows(con, table, year):
    if table == "driver_standings":
        sql = ("SELECT s.driver_id, d.given_name || ' ' || d.family_name, s.position, "
               "s.position_text, s.points, d.url FROM driver_standings s JOIN drivers d USING(driver_id) "
               "WHERE s.season=?")
    else:
        sql = ("SELECT s.constructor_id, c.name, s.position, s.position_text, s.points "
               ", c.url FROM constructor_standings s JOIN constructors c USING(constructor_id) WHERE s.season=?")
    return {r[0]: {"entity_id": r[0], "name": r[1], "position": r[2],
                   "position_text": r[3], "points": float(r[4]), "url": r[5]} for r in con.execute(sql, (year,))}


def _match_rows(wiki_rows, db_rows, table):
    unused = set(db_rows)
    matched, errors = {}, []
    engines = {"team", "ford", "honda", "renault", "bmw", "tag", "hart", "judd",
               "lamborghini", "alfa", "romeo", "motori", "moderni", "megatron",
               "yamaha", "subaru", "cosworth", "matra", "climax", "repco", "weslake",
               "maserati", "porsche"}
    constructor_aliases = {"larrousse": {"lola ford", "lola lamborghini"}}
    for row in wiki_rows or []:
        wn = _norm(row["name"])
        link_names = {_norm(x.get("title") or "") for x in row.get("links", []) if x.get("title")}
        direct = [e for e in unused if _norm(db_rows[e]["name"]) == wn]
        eid = direct[0] if len(direct) == 1 else None
        if eid is None and table == "constructor_standings":
            alias = [e for e in unused if wn in constructor_aliases.get(e, set())]
            if len(alias) == 1:
                eid = alias[0]
            else:
                wa = set(wn.split()) - engines
                core = []
                for e in unused:
                    da = set(_norm(db_rows[e]["name"]).split()) - engines
                    overlap = len(da & wa) / max(1, min(len(da), len(wa)))
                    if overlap == 1.0:
                        core.append(e)
                if len(core) == 1:
                    eid = core[0]
            if eid is None:
                url_exact = []
                for e in unused:
                    urln = _norm(urllib.parse.unquote((db_rows[e].get("url") or "").rsplit("/", 1)[-1]))
                    if urln and urln in link_names:
                        url_exact.append(e)
                if len(url_exact) == 1:
                    eid = url_exact[0]
        if eid is None and table == "driver_standings":
            url_exact = []
            for e in unused:
                dbn = _norm(db_rows[e]["name"])
                urln = _norm(urllib.parse.unquote((db_rows[e].get("url") or "").rsplit("/", 1)[-1]))
                if ((urln and urln in link_names)
                        or (dbn.split()[-1:] == wn.split()[-1:] and dbn.split()[-1:])):
                    url_exact.append(e)
            if len(url_exact) == 1:
                eid = url_exact[0]
        if eid is None:
            scores = sorted(((difflib.SequenceMatcher(
                None, wn, _norm(db_rows[e]["name"])).ratio(), e) for e in unused), reverse=True)
            if not scores or scores[0][0] < 0.80 or (len(scores) > 1 and scores[0][0] - scores[1][0] < 0.08):
                # Wikipedia often lists zero-point DNQ/DNS entrants that jolpica's final standings
                # endpoint omits. Record them as coverage notes, but they are not a comparable DB row.
                errors.append(f"wiki-only identity: {row['name']}")
                continue
            eid = scores[0][1]
        unused.remove(eid)
        matched[eid] = row
    # Wikipedia includes more zero-point non-classified entrants than jolpica in some years, and
    # vice versa. They are named coverage notes; only a missing classified/scoring DB row blocks.
    missing = sorted(e for e in unused
                     if db_rows[e]["position"] is not None or abs(db_rows[e]["points"]) > POINT_EPSILON)
    db_only_zero = sorted(set(unused) - set(missing))
    return matched, errors + [f"db-only zero-point identity: {e}" for e in db_only_zero], missing


def _apply_segments(round_points, segments, last_round):
    total = 0.0
    for seg in segments:
        start, end = seg["rounds"]
        end = last_round if end is None else end
        vals = [v for rnd, v in round_points.items() if start <= rnd <= end]
        vals.sort(reverse=True)
        best = seg.get("best")
        total += sum(vals if best is None else vals[:best])
    return total


def _rank(points, finishes):
    entities = sorted(points)
    max_finish = max((max(c.keys(), default=0) for c in finishes.values()), default=0)
    keys = {e: (round(points[e], 8),) + tuple(finishes[e][p] for p in range(1, max_finish + 1))
            for e in entities}
    ordered = sorted(entities, key=lambda e: keys[e], reverse=True)
    positions, previous, previous_position = {}, None, None
    for index, eid in enumerate(ordered, 1):
        if keys[eid] == previous:
            positions[eid] = previous_position
        else:
            positions[eid] = index
            previous_position = index
        previous = keys[eid]
    return positions


def recompute_driver(con, year, rule):
    rows = con.execute("SELECT round, driver_id, points, position_text FROM results WHERE season=?",
                       (year,)).fetchall()
    by = defaultdict(lambda: defaultdict(float))
    finishes = defaultdict(Counter)
    last = int(con.execute("SELECT MAX(round) FROM races WHERE season=?", (year,)).fetchone()[0])
    for rnd, eid, pts, ptext in rows:
        by[eid][rnd] += float(pts)
        # Countback compares scoring finishes; non-scoring lower finishes must not split drivers
        # whom the period table records as tied on identical counted results.
        if str(ptext).isdigit() and float(pts) > 0:
            finishes[eid][int(ptext)] += 1
    points = {eid: _apply_segments(rp, rule["segments"], last) for eid, rp in by.items()}
    return points, _rank(points, finishes)


def recompute_constructor(con, year, rule):
    if rule is None:
        return {}, {}
    excluded = set(rule.get("exclude_circuits", []))
    rows = con.execute(
        "SELECT x.round,x.constructor_id,x.position_text,x.position,r.circuit_id "
        "FROM results x JOIN races r ON r.season=x.season AND r.round=x.round WHERE x.season=?",
        (year,)).fetchall()
    by_round = defaultdict(lambda: defaultdict(list))
    finishes = defaultdict(Counter)
    schedule = rule["points_by_position"]
    # Half-points race detection uses the sum of winner driver points so shared drives do not look shortened.
    winner_sums = dict(con.execute(
        "SELECT round,SUM(points) FROM results WHERE season=? AND position_text='1' GROUP BY round", (year,)))
    driver_win = 9 if year >= 1961 else 8
    scale = {rnd: (0.5 if float(total) + 1e-9 < driver_win else 1.0)
             for rnd, total in winner_sums.items()}
    for rnd, eid, ptext, pos, circuit in rows:
        if circuit in excluded or not str(ptext).isdigit() or not pos or pos > len(schedule):
            continue
        pts = schedule[pos - 1] * scale.get(rnd, 1.0)
        by_round[eid][rnd].append(pts)
        finishes[eid][pos] += 1
    last = int(con.execute("SELECT MAX(round) FROM races WHERE season=?", (year,)).fetchone()[0])
    points = {}
    for eid, rounds in by_round.items():
        scored = {rnd: (max(vals) if rule.get("highest_car_only") else sum(vals))
                  for rnd, vals in rounds.items()}
        points[eid] = _apply_segments(scored, rule["segments"], last)
    return points, _rank(points, finishes)


def _equal(field, a, b):
    if a is None or b is None:
        return a is b
    if field == "points":
        return abs(float(a) - float(b)) <= POINT_EPSILON
    return a == b


def _compare_table(year, table, wiki_rows, con, recalculated, revid, url):
    db = _db_rows(con, table, year)
    matched, wiki_only, missing = _match_rows(wiki_rows, db, table)
    if missing:
        return [], wiki_only, ["missing wiki identities: " + ", ".join(missing)]
    rec_points, rec_positions = recalculated
    diffs = []
    for eid, wiki in matched.items():
        raw = db[eid]
        for field, rec in (("position", rec_positions.get(eid)), ("points", rec_points.get(eid))):
            raw_value, wiki_value = raw[field], wiki[field]
            # Wikipedia leaves zero-point non-classified entrants unranked; jolpica may assign a
            # display-only ordinal. No official position exists to override in that case.
            if field == "position" and wiki_value is None and abs(float(wiki["points"])) <= POINT_EPSILON:
                continue
            if _equal(field, raw_value, wiki_value):
                continue
            recommendation = "override" if (_equal(field, wiki_value, rec)
                                                  and not _equal(field, raw_value, rec)) else "UNRESOLVED"
            diffs.append({
                "table": table, "season": year, "entity_id": eid, "entity_name": raw["name"],
                "field": field, "jolpica": raw_value, "wiki": wiki_value, "recalculated": rec,
                "recommendation": recommendation, "source_revid": revid, "source_url": url})
    return diffs, wiki_only, []


def run(years=YEARS, refresh=False, offline=False, db_path=DB):
    rules = json.loads(RULES.read_text(encoding="utf-8"))["seasons"]
    con = sqlite3.connect(str(db_path))
    season_rows, all_diffs, reduced = [], [], []
    try:
        for year in years:
            try:
                path = CACHE / f"{year}.json"
                if offline and not path.exists():
                    raise RuntimeError("offline cache miss")
                blob = fetch_snapshot(year, refresh=refresh and not offline)
                parsed = parse_standings(blob)
                if parsed["driver"] is None or (year >= 1958 and parsed["constructor"] is None):
                    missing = [k for k in ("driver", "constructor" if year >= 1958 else "driver")
                               if parsed.get(k) is None]
                    raise RuntimeError("missing standings table: " + ", ".join(sorted(set(missing))))
                rule = rules[str(year)]
                driver_rec = recompute_driver(con, year, rule["driver"])
                d_diffs, d_notes, d_errors = _compare_table(
                    year, "driver_standings", parsed["driver"], con, driver_rec,
                    blob["_meta"]["revid"], blob["_meta"]["url"])
                c_diffs, c_notes, c_errors = [], [], []
                if year >= 1958:
                    constructor_rec = recompute_constructor(con, year, rule["constructor"])
                    c_diffs, c_notes, c_errors = _compare_table(
                        year, "constructor_standings", parsed["constructor"], con, constructor_rec,
                        blob["_meta"]["revid"], blob["_meta"]["url"])
                errors = d_errors + c_errors
                if errors:
                    raise RuntimeError("; ".join(errors))
                diffs = d_diffs + c_diffs
                all_diffs.extend(diffs)
                season_rows.append({"season": year, "status": "MATCH" if not diffs else f"{len(diffs)} diffs",
                                    "diff_count": len(diffs), "revid": blob["_meta"]["revid"],
                                    "drivers": len(parsed["driver"]),
                                    "constructors": len(parsed["constructor"] or []),
                                    "coverage_notes": d_notes + c_notes})
            except Exception as exc:  # named coverage reduction, never silent
                reduced.append({"season": year, "reason": str(exc)})
                season_rows.append({"season": year, "status": "UNPARSEABLE", "diff_count": None,
                                    "reason": str(exc)})
    finally:
        con.close()

    overrides = []
    for d in all_diffs:
        if d["recommendation"] != "override":
            continue
        overrides.append({
            "table": d["table"], "season": d["season"], "entity_id": d["entity_id"],
            "field": d["field"], "raw_value": d["jolpica"], "value": d["wiki"],
            "source_revid": d["source_revid"], "source_url": d["source_url"],
            "reason": "Wikipedia final standings equals independent results-plus-scoring-rule recomputation",
            "by": "PENDING-charlie", "date": "2026-08-13"})
    unresolved = [d for d in all_diffs if d["recommendation"] == "UNRESOLVED"]
    report = {
        "_meta": {"coverage": "1950-1990", "oracle": "en.wikipedia season final standings",
                  "scoring_rules": "data/f1/scoring-rules.json",
                  "note": "External snapshots break the former circular oracle; body-number value-set membership remains a documented checker limitation."},
        "coverage": {"expected_seasons": 41, "parsed_seasons": 41 - len(reduced),
                     "reduced_seasons": reduced},
        "summary": {"diffs": len(all_diffs), "suggested_overrides": len(overrides),
                    "unresolved": len(unresolved)},
        "seasons": season_rows, "diffs": all_diffs}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OVERRIDES.write_text(json.dumps({"_meta": {
        "policy": "default-deny; entries with by=PENDING-charlie are never applied",
        "generated_from": "data/f1/standings-crosscheck-report.json"},
        "overrides": overrides}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_adjudication(all_diffs, reduced)
    return report


def _fmt(v):
    if v is None:
        return "null"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _write_adjudication(diffs, reduced):
    unresolved = [d for d in diffs if d["recommendation"] == "UNRESOLVED"]
    lines = ["# Standings override 裁決包草稿", "", "## UNRESOLVED", ""]
    if unresolved:
        for d in unresolved:
            lines.append(f"- {d['season']} {d['table']} {d['entity_id']} {d['field']}："
                         f"jolpica {_fmt(d['jolpica'])}／維基 {_fmt(d['wiki'])}／重算 {_fmt(d['recalculated'])}")
    else:
        lines.append("- 無")
    lines += ["", "## Coverage 縮減", ""]
    lines += ([f"- {x['season']}：{x['reason']}" for x in reduced] or ["- 無"])
    lines += ["", "## 全部差異", "",
              "| 季 | 表 | 實體 | 欄位 | jolpica | 維基 | 規則重算 | 建議裁決 | 理由 |",
              "|---:|---|---|---|---:|---:|---:|---|---|"]
    for d in diffs:
        reason = ("維基與獨立重算一致、jolpica 不同" if d["recommendation"] == "override"
                  else "三方未形成可自動裁決的一致性")
        lines.append(f"| {d['season']} | {d['table']} | {d['entity_id']} | {d['field']} | "
                     f"{_fmt(d['jolpica'])} | {_fmt(d['wiki'])} | {_fmt(d['recalculated'])} | "
                     f"{d['recommendation']} | {reason} |")
    ADJUDICATION.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--season", type=int, action="append")
    ap.add_argument("--db", default=str(DB))
    args = ap.parse_args()
    report = run(args.season or YEARS, args.refresh, args.offline, pathlib.Path(args.db))
    print(json.dumps(report["summary"], ensure_ascii=False))
    if report["coverage"]["reduced_seasons"] or report["summary"]["unresolved"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
