#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crosscheck-wikipedia.py 回歸測試（純函式，零網路）。

鎖四件事（計畫 §4.5）：
  1. Infobox parser 容錯——{{F1 |2001}} 多餘空白、{{F1stat}} 模板非字面值、
     championships 年份解析、races 欄 entries/starts 口徑、巢狀 Le Mans module 不外洩。
  2. 比對邏輯——championships 對「數字」也對「年份集合」（抓數字對年份錯）；
     poles/fastest_laps 只記錄不產 diff。
  3. 裁決 gate 的**反向測試**：有 diff 但裁決檔空 → 必 FAIL；裁決缺欄/值非法 → 仍未解除。
  4. 具名裁決齊全 → gate PASS；過期裁決（指向不存在 diff）被標 stale 但不擋已解決的 gate。

跑法：python3 -m unittest discover -s tests
"""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cc = _load("crosscheck_wikipedia", "crosscheck-wikipedia.py")


# 一個貼近真實的 {{Infobox F1 driver}}（含巢狀 module2 = Le Mans，測不外洩）
SCHUMACHER_BOX = """{{Infobox F1 driver
| embed         = yes
| nationality   = {{flagicon|GER}} [[Formula One drivers from Germany|German]]
| years         = {{F1|1991}}–{{F1|2006}}, {{F1|2010}}–{{F1|2012}}
| teams         = [[Jordan Grand Prix|Jordan]], [[Benetton Formula|Benetton]]
| races         = 308 (306 starts)
| championships = 7 ({{F1|1994}}, {{F1|1995}}, {{F1|2000}}, {{F1 |2001}}, {{F1|2002}}, {{F1|2003}}, {{F1|2004}})
| wins          = 91
| podiums       = 155
| points        = 1566
| poles         = 68
| fastest_laps  = 77
| last_race     = {{F1GP||2012 Brazilian}}
| module2       = {{Infobox Le Mans driver
| embed       = yes
| years       = {{24hLM|1991}}
| best_finish = 5th
| class_wins  = 0
}}
}}"""

# 現役車手：volume 欄是 {{F1stat}} 模板，但 championships 仍字面 + 年份
NORRIS_BOX = """{{Infobox F1 driver
| embed         = yes
| races         = {{F1stat|NOR|entries}} ({{F1stat|NOR|starts}} starts)
| championships = 1 ({{F1|2025}})
| wins          = {{F1stat|NOR|wins}}
| podiums       = {{F1stat|NOR|podiums}}
| poles         = {{F1stat|NOR|poles}}
| fastest_laps  = {{F1stat|NOR|fastest laps}}
}}"""


class ParamSplitTests(unittest.TestCase):
    def test_find_infobox_brace_matched_includes_module(self):
        box = cc.find_infobox("lead text\n" + SCHUMACHER_BOX + "\nmore text")
        self.assertTrue(box.startswith("{{Infobox F1 driver"))
        self.assertTrue(box.rstrip().endswith("}}"))

    def test_nested_module_params_do_not_leak_to_top_level(self):
        """巢狀 Le Mans module 的 best_finish/class_wins 不得被當成 F1 頂層參數。"""
        params = cc.parse_params(cc.find_infobox(SCHUMACHER_BOX))
        self.assertIn("races", params)
        self.assertIn("championships", params)
        self.assertNotIn("best finish", params)     # 屬 module2 內層
        self.assertNotIn("class wins", params)
        # module2 整塊是「一個」頂層參數值，其內層 pipe 不外洩
        self.assertIn("module2", params)
        self.assertIn("Le Mans driver", params["module2"])

    def test_key_normalization_underscore_and_case(self):
        params = cc.parse_params(cc.find_infobox(SCHUMACHER_BOX))
        self.assertIn("fastest laps", params)        # fastest_laps → "fastest laps"


class ChampionshipParseTests(unittest.TestCase):
    def test_year_whitespace_variant_tolerated(self):
        """{{F1 |2001}} 的多餘空白必須容錯（計畫 §4.5 明列）。"""
        r = cc.parse_championships_field(
            "7 ({{F1|1994}}, {{F1|1995}}, {{F1|2000}}, {{F1 |2001}}, {{F1|2002}}, {{F1|2003}}, {{F1|2004}})")
        self.assertEqual(r["count"], 7)
        self.assertEqual(r["years"], [1994, 1995, 2000, 2001, 2002, 2003, 2004])
        self.assertFalse(r["template_not_literal"])

    def test_single_championship(self):
        r = cc.parse_championships_field("1 ({{F1|2016}})")
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["years"], [2016])

    def test_active_driver_championship_literal_even_when_volume_is_template(self):
        """現役車手 championships 常仍字面（"1 ({{F1|2025}})"），要照樣抓到年份。"""
        r = cc.parse_championships_field("1 ({{F1|2025}})")
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["years"], [2025])

    def test_years_deduped_and_sorted(self):
        r = cc.parse_championships_field("2 ({{F1|2006}}, {{F1|2005}}, {{F1|2005}})")
        self.assertEqual(r["years"], [2005, 2006])


class VolumeFieldParseTests(unittest.TestCase):
    def test_literal_int(self):
        r = cc.parse_int_field("91")
        self.assertEqual(r["value"], 91)
        self.assertFalse(r["template_not_literal"])

    def test_f1stat_template_marks_not_literal(self):
        r = cc.parse_int_field("{{F1stat|NOR|wins}}")
        self.assertTrue(r["template_not_literal"])
        self.assertIsNone(r["value"])

    def test_int_field_strips_ref_noise(self):
        r = cc.parse_int_field("68<ref name=x>stuff</ref>")
        self.assertEqual(r["value"], 68)

    def test_races_entries_and_starts_split(self):
        r = cc.parse_races_field("308 (306 starts)")
        self.assertEqual(r["entries"], 308)
        self.assertEqual(r["starts"], 306)
        self.assertFalse(r["template_not_literal"])

    def test_races_all_starts_equal(self):
        r = cc.parse_races_field("206 (206 starts)")
        self.assertEqual(r["entries"], 206)
        self.assertEqual(r["starts"], 206)

    def test_races_template_not_literal(self):
        r = cc.parse_races_field("{{F1stat|NOR|entries}} ({{F1stat|NOR|starts}} starts)")
        self.assertTrue(r["template_not_literal"])
        self.assertIsNone(r["entries"])


class ParseInfoboxTests(unittest.TestCase):
    def test_full_infobox_all_fields(self):
        ib = cc.parse_infobox(SCHUMACHER_BOX)
        self.assertTrue(ib["found"])
        self.assertEqual(ib["championships"]["count"], 7)
        self.assertEqual(ib["championships"]["years"][:2], [1994, 1995])
        self.assertEqual(ib["wins"]["value"], 91)
        self.assertEqual(ib["podiums"]["value"], 155)
        self.assertEqual(ib["entries"]["entries"], 308)
        self.assertEqual(ib["entries"]["starts"], 306)
        self.assertEqual(ib["poles"]["value"], 68)
        self.assertEqual(ib["fastest_laps"]["value"], 77)

    def test_active_driver_volume_all_template(self):
        ib = cc.parse_infobox(NORRIS_BOX)
        self.assertTrue(ib["found"])
        self.assertTrue(ib["wins"]["template_not_literal"])
        self.assertTrue(ib["entries"]["template_not_literal"])
        self.assertEqual(ib["championships"]["count"], 1)      # champs 仍字面
        self.assertEqual(ib["championships"]["years"], [2025])

    def test_no_f1_infobox_returns_not_found(self):
        self.assertFalse(cc.parse_infobox("#REDIRECT [[Giuseppe Farina]]")["found"])
        self.assertFalse(cc.parse_infobox("just prose, no template")["found"])


class CompareTests(unittest.TestCase):
    """compare_driver：不碰 db，直接餵我方值 + 解析後 infobox。"""

    def _our(self, wins, podiums, entries, first=1990, last=2010):
        return {"wins": wins, "podiums": podiums, "entries": entries,
                "first_season": first, "last_season": last}

    def test_no_diff_when_all_match(self):
        ib = cc.parse_infobox(SCHUMACHER_BOX)
        years = [1994, 1995, 2000, 2001, 2002, 2003, 2004]
        _, diffs = cc.compare_driver("michael_schumacher", "Michael Schumacher",
                                     years, self._our(91, 155, 308, 1991, 2012), ib)
        # entries 308==308、wins/podiums/champs 全對 → 零 diff
        self.assertEqual(diffs, [])

    def test_championships_year_mismatch_detected(self):
        """數字對但年份錯：count 都是 7，但我方少一年多一年 → 產 championships_years diff。"""
        ib = cc.parse_infobox(SCHUMACHER_BOX)
        wrong_years = [1994, 1995, 2000, 2001, 2002, 2003, 1999]  # 2004→1999
        _, diffs = cc.compare_driver("michael_schumacher", "MSC",
                                     wrong_years, self._our(91, 155, 308, 1991, 2012), ib)
        keys = {d["field"] for d in diffs}
        self.assertIn("championships_years", keys)
        yd = [d for d in diffs if d["field"] == "championships_years"][0]
        self.assertEqual(yd["ours_only"], [1999])
        self.assertEqual(yd["wiki_only"], [2004])

    def test_championships_count_mismatch_detected(self):
        ib = cc.parse_infobox(SCHUMACHER_BOX)
        _, diffs = cc.compare_driver("x", "X", [1994, 1995],
                                     self._our(91, 155, 308, 1991, 2012), ib)
        self.assertIn("championships_count", {d["field"] for d in diffs})

    def test_poles_fastest_laps_never_produce_diff(self):
        ib = cc.parse_infobox(SCHUMACHER_BOX)
        years = [1994, 1995, 2000, 2001, 2002, 2003, 2004]
        fields, diffs = cc.compare_driver("msc", "MSC", years,
                                          self._our(91, 155, 308, 1991, 2012), ib)
        self.assertEqual([d for d in diffs if d["field"] in ("poles", "fastest_laps")], [])
        self.assertIsNone(fields["poles"]["ours"])          # 只記錄維基值
        self.assertEqual(fields["poles"]["wiki"], 68)

    def test_template_volume_field_produces_no_diff(self):
        """現役 {{F1stat}} 欄不硬解、不產 diff。"""
        ib = cc.parse_infobox(NORRIS_BOX)
        _, diffs = cc.compare_driver("norris", "Lando Norris", [2025],
                                     self._our(11, 40, 130, 2019, 2026), ib)
        self.assertEqual([d for d in diffs if d["field"] in ("wins", "podiums", "entries")], [])

    def test_entries_diff_classified_definition_differs(self):
        ib = cc.parse_infobox(SCHUMACHER_BOX)   # races 308
        years = [1994, 1995, 2000, 2001, 2002, 2003, 2004]
        _, diffs = cc.compare_driver("x", "X", years,
                                     self._our(91, 155, 300, 1991, 2012), ib)  # entries 300≠308
        ed = [d for d in diffs if d["field"] == "entries"]
        self.assertEqual(len(ed), 1)
        self.assertEqual(ed[0]["classification"], "likely_definition_differs")

    def test_low_volume_classified_ours_wrong(self):
        """我方 wins 低於維基 → 偏低通常是漏列 → likely_ours_wrong。"""
        ib = cc.parse_infobox(SCHUMACHER_BOX)   # wins 91
        years = [1994, 1995, 2000, 2001, 2002, 2003, 2004]
        _, diffs = cc.compare_driver("x", "X", years,
                                     self._our(90, 155, 308, 1991, 2012), ib)
        wd = [d for d in diffs if d["field"] == "wins"][0]
        self.assertEqual(wd["classification"], "likely_ours_wrong")


class GateTests(unittest.TestCase):
    """裁決硬 gate 的反向測試——計畫 §4.5 + 2026-07-22 Sol 審 S0-2 收硬後的機器保證。

    硬 gate＝解除一個 diff 需：verdict∈{definition_differs,wiki_wrong}（ours_wrong 不解除）
    + reason/by/date 非空 + 綁定 bound_ours/bound_wiki/definition_id/wiki_revid 全部吻合當前 report；
    另加 stale 裁決（指向不存在 diff）比照 invariants exact-set 整體 FAIL。
    """

    def _report(self):
        return {"diffs": [
            {"driver_id": "fangio", "field": "entries", "ours": 51, "wiki": 52,
             "classification": "likely_definition_differs", "reason": "x", "key": "fangio|entries",
             "definition_id": "results_distinct_races", "wiki_revid": 111},
            {"driver_id": "senna", "field": "entries", "ours": 161, "wiki": 162,
             "classification": "likely_definition_differs", "reason": "x", "key": "senna|entries",
             "definition_id": "results_distinct_races", "wiki_revid": 222},
        ]}

    def _bound_verdict(self, key, ours, wiki, revid, verdict="definition_differs",
                       reason="口徑差", by="charlie", date="2026-07-21",
                       definition_id="results_distinct_races"):
        """一條綁定完整的裁決（預設能解除對應 diff）。"""
        return {"key": key, "verdict": verdict, "reason": reason, "by": by, "date": date,
                "definition_id": definition_id, "bound_ours": ours, "bound_wiki": wiki,
                "wiki_revid": revid}

    def _both_valid(self):
        return [self._bound_verdict("fangio|entries", 51, 52, 111),
                self._bound_verdict("senna|entries", 161, 162, 222)]

    # ---- 基本行為 ----

    def test_empty_verdicts_fails_all_diffs(self):
        passed, unresolved, stale = cc.gate_diffs(self._report(), [])
        self.assertFalse(passed)
        self.assertEqual(len(unresolved), 2)
        self.assertTrue(all(d["_gate_status"] == "no_verdict" for d in unresolved))

    def test_all_bound_verdicts_pass(self):
        passed, unresolved, stale = cc.gate_diffs(self._report(), self._both_valid())
        self.assertTrue(passed)
        self.assertEqual(unresolved, [])
        self.assertEqual(stale, [])

    def test_partial_verdicts_still_fail(self):
        passed, unresolved, _ = cc.gate_diffs(
            self._report(), [self._bound_verdict("fangio|entries", 51, 52, 111)])
        self.assertFalse(passed)
        self.assertEqual([d["key"] for d in unresolved], ["senna|entries"])

    def test_invalid_verdict_value_does_not_resolve(self):
        bad = self._bound_verdict("fangio|entries", 51, 52, 111, verdict="looks_fine")
        passed, unresolved, _ = cc.gate_diffs(
            self._report(), [bad, self._bound_verdict("senna|entries", 161, 162, 222)])
        self.assertFalse(passed)
        self.assertIn("fangio|entries", [d["key"] for d in unresolved])

    def test_missing_required_field_does_not_resolve(self):
        for missing in ("reason", "by", "date"):
            v = self._bound_verdict("fangio|entries", 51, 52, 111)
            v[missing] = ""
            passed, unresolved, _ = cc.gate_diffs(
                self._report(), [v, self._bound_verdict("senna|entries", 161, 162, 222)])
            self.assertFalse(passed, f"缺 {missing} 應仍未解除")
            self.assertIn("fangio|entries", [d["key"] for d in unresolved])

    # ---- Sol S0-2 三個 PoC 反例（改值後舊裁決必 FAIL / ours_wrong 必 FAIL / 純 stale 必 FAIL）----

    def test_poc_altered_diff_value_invalidates_old_verdict(self):
        """Sol PoC：diff 值被改成荒謬值（ascari ours=999999, wiki=-123），
        綁 51/52 的舊裁決必須失效 → binding_drift → FAIL。"""
        rep = self._report()
        rep["diffs"][0]["ours"] = 999999
        rep["diffs"][0]["wiki"] = -123
        passed, unresolved, _ = cc.gate_diffs(rep, self._both_valid())
        self.assertFalse(passed)
        drift = [d for d in unresolved if d["key"] == "fangio|entries"]
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0]["_gate_status"], "binding_drift")

    def test_poc_ours_wrong_never_resolves(self):
        """Sol PoC：仍存在的 diff 掛 ours_wrong（結構完整）也不得放行 → ours_wrong_hold → FAIL。"""
        v = self._bound_verdict("fangio|entries", 51, 52, 111, verdict="ours_wrong",
                                reason="我方確實少算一場")
        passed, unresolved, _ = cc.gate_diffs(
            self._report(), [v, self._bound_verdict("senna|entries", 161, 162, 222)])
        self.assertFalse(passed)
        hold = [d for d in unresolved if d["key"] == "fangio|entries"]
        self.assertEqual(len(hold), 1)
        self.assertEqual(hold[0]["_gate_status"], "ours_wrong_hold")

    def test_poc_pure_stale_verdict_fails(self):
        """Sol PoC：報告零 diff、只留一條指向不存在 diff 的裁決 → stale → 單獨即 FAIL。"""
        passed, unresolved, stale = cc.gate_diffs(
            {"diffs": []}, [self._bound_verdict("ghost|wins", 1, 2, 999)])
        self.assertFalse(passed)
        self.assertEqual(unresolved, [])
        self.assertEqual(stale, ["ghost|wins"])

    # ---- 綁定各欄的失效 ----

    def test_definition_id_mismatch_invalidates(self):
        v = self._bound_verdict("fangio|entries", 51, 52, 111, definition_id="wrong_def")
        passed, unresolved, _ = cc.gate_diffs(
            self._report(), [v, self._bound_verdict("senna|entries", 161, 162, 222)])
        self.assertFalse(passed)
        self.assertIn("fangio|entries", [d["key"] for d in unresolved])

    def test_wiki_revid_mismatch_invalidates(self):
        """維基版本變動（revid 不符）→ 裁決失效，逼人工重看新版。"""
        v = self._bound_verdict("fangio|entries", 51, 52, 999)   # revid 應為 111
        passed, unresolved, _ = cc.gate_diffs(
            self._report(), [v, self._bound_verdict("senna|entries", 161, 162, 222)])
        self.assertFalse(passed)
        drift = [d for d in unresolved if d["key"] == "fangio|entries"][0]
        self.assertEqual(drift["_gate_status"], "binding_drift")

    def test_missing_binding_fields_does_not_resolve(self):
        """舊格式裁決（無 bound_* 欄）不得解除任何 diff。"""
        legacy = {"key": "fangio|entries", "verdict": "definition_differs",
                  "reason": "x", "by": "charlie", "date": "2026-07-21"}
        passed, unresolved, _ = cc.gate_diffs(
            self._report(), [legacy, self._bound_verdict("senna|entries", 161, 162, 222)])
        self.assertFalse(passed)
        self.assertIn("fangio|entries", [d["key"] for d in unresolved])

    def test_stale_alongside_resolved_still_fails(self):
        """即使兩個真 diff 都被解除，多一條 stale 裁決仍整體 FAIL（exact-set）。"""
        verdicts = self._both_valid() + [self._bound_verdict("ghost|entries", 1, 2, 3)]
        passed, unresolved, stale = cc.gate_diffs(self._report(), verdicts)
        self.assertFalse(passed)
        self.assertEqual(unresolved, [])
        self.assertEqual(stale, ["ghost|entries"])


class RealVerdictsTests(unittest.TestCase):
    """對真實裁決檔＋（若存在）真實報告的整合斷言。"""

    def test_real_verdicts_are_named_and_bound(self):
        """每條真實裁決必須具名完整，且帶齊綁定欄（definition_id/bound_ours/bound_wiki/wiki_revid）。"""
        allowed = {"ours_wrong", "definition_differs", "wiki_wrong"}
        verdicts = cc.load_verdicts()
        self.assertGreater(len(verdicts), 0)
        for v in verdicts:
            for field in ("key", "verdict", "reason", "by", "date"):
                self.assertTrue(str(v.get(field, "")).strip(), f"{v.get('key')} 缺 {field}")
            self.assertIn(v["verdict"], allowed, v["key"])
            for field in ("definition_id", "bound_ours", "bound_wiki", "wiki_revid"):
                self.assertIsNotNone(v.get(field), f"{v['key']} 缺綁定欄 {field}")

    def test_real_report_gate_passes_if_report_present(self):
        """有 report 時，真實裁決應能對其通過硬 gate（回歸鎖：本 PR 的已核准狀態）。"""
        import json
        if not cc.REPORT.exists():
            self.skipTest("crosscheck-report.json 未生成，略過整合驗證")
        rep = json.loads(cc.REPORT.read_text(encoding="utf-8"))
        passed, unresolved, stale = cc.gate_diffs(rep, cc.load_verdicts())
        self.assertTrue(passed, f"未解={[d['key'] for d in unresolved]} stale={stale}")


if __name__ == "__main__":
    unittest.main()
