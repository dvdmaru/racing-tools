#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""退賽原因年代分布：SQL 獨立重算與 fail-closed 回歸測試。"""
import html
import importlib.util
import json
import pathlib
import re
import shutil
import sqlite3
import tempfile
import unittest
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP


ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "f1" / "db.sqlite"
CATEGORIES = ROOT / "data" / "f1" / "retirement-categories.json"
DECADES = tuple(range(1950, 2030, 10))


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "gen_racing_seasons_retirement_test", ROOT / "scripts" / "gen-racing-seasons.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


g = _load_generator()


def _display_tenths(counts, total):
    """獨立實作最大餘數法：整體固定為 1,000 個十分之一百分點。"""
    bases = [(n * 1000) // total for n in counts]
    remainders = [(n * 1000) % total for n in counts]
    missing = 1000 - sum(bases)
    order = sorted(range(len(counts)), key=lambda i: (-remainders[i], i))
    for i in order[:missing]:
        bases[i] += 1
    return bases


def _independent_sql():
    """只讀 SQLite 與 JSON，用 SQL GROUP BY／CASE 直算；不呼叫生成器統計。"""
    config = json.loads(CATEGORIES.read_text(encoding="utf-8"))
    categories = config["categories"]
    case_parts, params = [], []
    for category in categories:
        placeholders = ",".join("?" for _ in category["statuses"])
        case_parts.append(f"WHEN status IN ({placeholders}) THEN ?")
        params.extend(category["statuses"])
        params.append(category["id"])
    category_case = "CASE " + " ".join(case_parts) + " ELSE '__UNMAPPED__' END"
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        totals = {
            row[0]: {"starts": row[1], "retirements": row[2]}
            for row in con.execute(
                "SELECT (season / 10) * 10 AS decade, "
                "SUM(CASE WHEN position_text <> 'W' OR laps > 0 THEN 1 ELSE 0 END) AS starts, "
                "SUM(CASE WHEN position_text = 'R' THEN 1 ELSE 0 END) AS retirements "
                "FROM results WHERE season BETWEEN 1950 AND 2029 GROUP BY decade"
            )
        }
        grouped = con.execute(
            f"SELECT (season / 10) * 10 AS decade, {category_case} AS category_id, COUNT(*) "
            "FROM results WHERE season BETWEEN 1950 AND 2029 AND position_text = 'R' "
            "GROUP BY decade, category_id ORDER BY decade, category_id",
            params,
        ).fetchall()
    finally:
        con.close()

    counts_by_decade = {decade: Counter() for decade in DECADES}
    for decade, category_id, count in grouped:
        if category_id == "__UNMAPPED__":
            raise AssertionError(f"SQL oracle 發現未映射 status：{decade}")
        counts_by_decade[decade][category_id] = count

    expected = {}
    for decade in DECADES:
        starts = totals[decade]["starts"]
        retirements = totals[decade]["retirements"]
        counts = counts_by_decade[decade]
        ordered_counts = [counts[c["id"]] for c in categories]
        tenths = _display_tenths(ordered_counts, retirements)
        rate = (Decimal(retirements * 100) / Decimal(starts)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP)
        expected[decade] = {
            "starts": starts,
            "retirements": retirements,
            "rate": f"{rate:.1f}",
            "categories": {
                category["id"]: {"count": count, "percent": f"{tenth / 10:.1f}"}
                for category, count, tenth in zip(categories, ordered_counts, tenths)
            },
        }
    return categories, expected


def _render_index():
    tmp = pathlib.Path(tempfile.mkdtemp())
    old_g, old_rc = g.PUB, g.rc.PUB
    g.PUB = g.rc.PUB = tmp
    try:
        g.render_index(set(range(g.FIRST_YEAR, g.LAST_YEAR + 1)))
        return (tmp / "seasons" / "index.html").read_text(encoding="utf-8")
    finally:
        g.PUB, g.rc.PUB = old_g, old_rc
        shutil.rmtree(tmp)


class RetirementEraMappingTests(unittest.TestCase):
    def test_mapping_is_complete_unique_and_fail_closed(self):
        config = json.loads(CATEGORIES.read_text(encoding="utf-8"))
        mapped = [s for category in config["categories"] for s in category["statuses"]]
        self.assertEqual(len(mapped), len(set(mapped)), "同一 status 不得落入多個類別")

        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            actual = {
                row[0] for row in con.execute(
                    "SELECT DISTINCT status FROM results WHERE position_text = 'R'")
            }
        finally:
            con.close()
        self.assertEqual(actual, set(mapped))

        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            withdrew_after_laps = con.execute(
                "SELECT COUNT(*) FROM results WHERE position_text = 'W' AND laps > 0"
            ).fetchone()[0]
            non_w = con.execute(
                "SELECT COUNT(*) FROM results WHERE position_text <> 'W'"
            ).fetchone()[0]
        finally:
            con.close()
        self.assertGreater(withdrew_after_laps, 0, "fixture 應含 W 但已完成圈數的歷史案例")
        generated_starts = sum(row["starts"] for row in g.retirement_era_data())
        self.assertEqual(generated_starts, non_w + withdrew_after_laps,
                         "W 且 laps>0 已實際出賽，不得排除於分母")

        bad = json.loads(CATEGORIES.read_text(encoding="utf-8"))
        for category in bad["categories"]:
            if "Engine" in category["statuses"]:
                category["statuses"].remove("Engine")
                break
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        bad_path = tmp / "categories.json"
        bad_path.write_text(json.dumps(bad), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Engine"):
            g.retirement_era_data(categories_path=bad_path)

        bad_definition = json.loads(CATEGORIES.read_text(encoding="utf-8"))
        bad_definition["retirement_definition"] = "status != Finished"
        definition_path = tmp / "bad-definition.json"
        definition_path.write_text(json.dumps(bad_definition), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "retirement_definition"):
            g.retirement_era_data(categories_path=definition_path)

    def test_all_decade_buckets_exist(self):
        rows = g.retirement_era_data()
        self.assertEqual(tuple(row["decade"] for row in rows), DECADES)


class RetirementEraRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.categories, cls.expected = _independent_sql()
        cls.page = _render_index()
        match = re.search(
            r'<section class="retirement-eras" id="retirement-eras">(.*?)</section>',
            cls.page,
            re.S,
        )
        if not match:
            raise AssertionError("找不到 retirement-eras section")
        cls.section = match.group(1)

    def test_every_rendered_percentage_and_count_matches_independent_sql(self):
        articles = re.findall(
            r'<article class="re-era" data-decade="(\d+)" '
            r'data-starts="(\d+)" data-retirements="(\d+)" '
            r'data-retirement-rate="([0-9.]+)">(.*?)</article>',
            self.section,
            re.S,
        )
        self.assertEqual([int(row[0]) for row in articles], list(DECADES))
        for decade_s, starts_s, retirements_s, rate_s, body in articles:
            decade = int(decade_s)
            expected = self.expected[decade]
            self.assertEqual(int(starts_s), expected["starts"])
            self.assertEqual(int(retirements_s), expected["retirements"])
            self.assertEqual(rate_s, expected["rate"])
            segments = re.findall(
                r'<span class="re-seg re-c\d+" data-category="([^"]+)" '
                r'data-count="(\d+)" data-percent="([0-9.]+)"',
                body,
            )
            self.assertEqual(len(segments), len(self.categories))
            for category_id, count_s, percent_s in segments:
                cat_expected = expected["categories"][category_id]
                self.assertEqual(int(count_s), cat_expected["count"],
                                 f"{decade} {category_id} count")
                self.assertEqual(percent_s, cat_expected["percent"],
                                 f"{decade} {category_id} percent")

    def test_display_percentages_sum_to_exactly_100(self):
        for decade in DECADES:
            percentages = [
                Decimal(v["percent"])
                for v in self.expected[decade]["categories"].values()
            ]
            self.assertEqual(sum(percentages), Decimal("100.0"),
                             f"{decade} 最大餘數法後應恰為 100.0％")

    def test_narratives_use_the_same_calculated_numbers(self):
        for decade, expected in self.expected.items():
            engine = expected["categories"]["engine"]
            sentence = (
                f"{decade} 年代每 100 次出賽有 {expected['rate']} 次退賽，"
                f"其中引擎與動力占 {engine['percent']}％"
            )
            self.assertIn(sentence, html.unescape(self.section))

    def test_methodology_states_scope_denominators_and_rounding(self):
        text = html.unescape(re.sub(r"<[^>]+>", "", self.section))
        self.assertIn("完賽名次標記為「R」", text)
        self.assertIn("失格（D）、退出（W）、F 與 E 都不算退賽", text)
        self.assertIn("Lapped／+N Laps", text)
        self.assertIn("退賽數 ÷ 出賽人次", text)
        self.assertIn("W 且 0 圈者視為未正式起跑", text)
        self.assertIn("W 但已有完成圈數者仍算出賽", text)
        self.assertIn("該年代退賽數", text)
        self.assertIn("最大餘數法", text)
        self.assertIn("0.1 個百分點", text)
        self.assertNotIn("data/f1", self.section)
        self.assertNotIn("db.sqlite", self.section)

    def test_2020s_scope_is_explicit(self):
        self.assertIn("2020 年代（截至 2026 R11）", html.unescape(self.section))


if __name__ == "__main__":
    unittest.main()
