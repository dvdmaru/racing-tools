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
    """裁決硬 gate 的反向測試——計畫 §4.5 + Sol S0-2 + 覆核 §4 + 終輪 R1/R2/R3。

    硬 gate＝解除一個 diff 需：verdict∈{definition_differs,wiki_wrong}（ours_wrong 不解除）
    + reason/by/date 非空 + wiki_revid 非 null + canonical bound_fingerprint 吻合 + 同 key 恰好一條；
    另加 stale exact-set FAIL、report 不完整 fail closed（車手 error/infobox 缺/**身分集合不符**/
    schema 缺塊/keyless verdict）。gate_diffs 回 4 元組 (passed, unresolved, stale, faults)。
    """

    def _diff(self, driver_id, ours, wiki, revid, starts=None,
              definition_id="results_distinct_races", classification="likely_definition_differs"):
        d = {"driver_id": driver_id, "field": "entries", "ours": ours, "wiki": wiki,
             "classification": classification, "reason": "x", "key": f"{driver_id}|entries",
             "definition_id": definition_id, "wiki_revid": revid}
        if starts is not None:
            d["wiki_starts"] = starts
        return d

    def _report(self, diffs=None, champions=None, extra_driver_entries=None):
        """把 diffs 包成**完整** report（含 drivers + coverage 身分 manifest），預設通過 report 級檢查。

        champions：成功車手身分集合（default＝diffs 涉及的車手）。extra_driver_entries：
        額外 driver dict（可帶 error/infobox_found=False，用來測 fail-closed）。
        """
        if diffs is None:
            diffs = [self._diff("fangio", 51, 52, 111, starts=51),
                     self._diff("senna", 161, 162, 222, starts=161)]
        if champions is None:
            champions = sorted({d["driver_id"] for d in diffs})
        drivers = [{"driver_id": c, "infobox_found": True} for c in champions]
        if extra_driver_entries:
            drivers = drivers + list(extra_driver_entries)
        return {"diffs": diffs, "drivers": drivers,
                "coverage": {"expected_champion_count": len(champions),
                             "expected_champion_ids": sorted(champions),
                             "extra_driver_ids": []}}

    def _verdict_for(self, diff, verdict="definition_differs", reason="口徑差",
                     by="charlie", date="2026-07-21"):
        """對某個 diff 產生一條「綁定吻合」的裁決（含 canonical bound_fingerprint）。"""
        return {"key": diff["key"], "verdict": verdict, "reason": reason, "by": by, "date": date,
                "definition_id": diff["definition_id"], "bound_ours": diff["ours"],
                "bound_wiki": diff["wiki"], "wiki_revid": diff["wiki_revid"],
                "bound_fingerprint": cc.diff_fingerprint(diff)}

    def _both_valid(self, rep):
        return [self._verdict_for(d) for d in rep["diffs"]]

    # ---- 基本行為 ----

    def test_empty_verdicts_fails_all_diffs(self):
        rep = self._report()
        passed, unresolved, stale, faults = cc.gate_diffs(rep, [])
        self.assertFalse(passed)
        self.assertEqual(len(unresolved), 2)
        self.assertTrue(all(d["_gate_status"] == "no_verdict" for d in unresolved))

    def test_all_bound_verdicts_pass(self):
        rep = self._report()
        passed, unresolved, stale, faults = cc.gate_diffs(rep, self._both_valid(rep))
        self.assertTrue(passed, f"unresolved={unresolved} stale={stale} faults={faults}")
        self.assertEqual((unresolved, stale, faults), ([], [], []))

    def test_partial_verdicts_still_fail(self):
        rep = self._report()
        passed, unresolved, stale, faults = cc.gate_diffs(rep, [self._verdict_for(rep["diffs"][0])])
        self.assertFalse(passed)
        self.assertEqual([d["key"] for d in unresolved], ["senna|entries"])

    def test_invalid_verdict_value_does_not_resolve(self):
        rep = self._report()
        bad = self._verdict_for(rep["diffs"][0], verdict="looks_fine")
        passed, unresolved, *_ = cc.gate_diffs(rep, [bad, self._verdict_for(rep["diffs"][1])])
        self.assertFalse(passed)
        self.assertIn("fangio|entries", [d["key"] for d in unresolved])

    def test_missing_required_field_does_not_resolve(self):
        rep = self._report()
        for missing in ("reason", "by", "date"):
            v = self._verdict_for(rep["diffs"][0])
            v[missing] = ""
            passed, unresolved, *_ = cc.gate_diffs(rep, [v, self._verdict_for(rep["diffs"][1])])
            self.assertFalse(passed, f"缺 {missing} 應仍未解除")
            self.assertIn("fangio|entries", [d["key"] for d in unresolved])

    # ---- 首輪 S0-2 三個 PoC（改值/ours_wrong/純 stale）----

    def test_regression_altered_diff_value_invalidates_old_verdict(self):
        """diff 值改成荒謬值後，綁舊 fingerprint 的裁決失效 → binding_drift → FAIL。"""
        rep = self._report()
        verdicts = self._both_valid(rep)          # 先對「原始」diff 綁定
        rep["diffs"][0]["ours"] = 999999
        rep["diffs"][0]["wiki"] = -123
        passed, unresolved, *_ = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        drift = [d for d in unresolved if d["key"] == "fangio|entries"]
        self.assertEqual(drift[0]["_gate_status"], "binding_drift")

    def test_regression_ours_wrong_never_resolves(self):
        rep = self._report()
        v = self._verdict_for(rep["diffs"][0], verdict="ours_wrong", reason="我方確實少算一場")
        passed, unresolved, *_ = cc.gate_diffs(rep, [v, self._verdict_for(rep["diffs"][1])])
        self.assertFalse(passed)
        hold = [d for d in unresolved if d["key"] == "fangio|entries"]
        self.assertEqual(hold[0]["_gate_status"], "ours_wrong_hold")

    def test_regression_pure_stale_verdict_fails(self):
        ghost = self._diff("ghost", 1, 2, 999)
        passed, unresolved, stale, faults = cc.gate_diffs(
            {"diffs": [], "drivers": [],
             "coverage": {"expected_champion_count": 0, "expected_champion_ids": [],
                          "extra_driver_ids": []}},
            [self._verdict_for(ghost)])
        self.assertFalse(passed)
        self.assertEqual(unresolved, [])
        self.assertEqual(stale, ["ghost|entries"])

    # ---- 覆核 §4 新反例：report 不完整 fail closed ----

    def test_recheck_driver_error_fails_even_if_all_diffs_resolved(self):
        """Sol 覆核反證：一位車手 parser error + 其餘 diff 皆有效裁決 → 仍必須 FAIL。"""
        rep = self._report(extra_driver_entries=[
            {"driver_id": "clark", "error": "parser error", "infobox_found": False}])
        verdicts = self._both_valid(rep)
        passed, unresolved, stale, faults = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        self.assertTrue(any("clark" in f for f in faults))

    def test_recheck_infobox_missing_fails(self):
        rep = self._report(extra_driver_entries=[{"driver_id": "clark", "infobox_found": False}])
        verdicts = self._both_valid(rep)
        passed, *_ , faults = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        self.assertTrue(any("infobox 缺失" in f for f in faults))

    def test_recheck_missing_coverage_field_fails(self):
        rep = self._report()
        verdicts = self._both_valid(rep)
        del rep["coverage"]["expected_champion_count"]
        passed, *_ , faults = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)

    # ---- 終輪 R1：coverage 驗身分集合，不只驗列數 ----

    def test_r1_duplicate_row_hidden_shortfall_fails(self):
        """Sol 終輪 PoC①：35 列藏 34 人（c 換成重複的 b）→ rows!=unique → FAIL（含 --gate-only 無 DB）。"""
        rep = self._report(diffs=[], champions=["a", "b", "c"])
        rep["drivers"] = [{"driver_id": "a", "infobox_found": True},
                          {"driver_id": "b", "infobox_found": True},
                          {"driver_id": "b", "infobox_found": True}]   # c 不見了、b 重複
        passed, _, _, faults = cc.gate_diffs(rep, [])
        self.assertFalse(passed)
        self.assertTrue(any("重複列" in f for f in faults))
        # DB 權威模式也要 FAIL
        passed2, *_ = cc.gate_diffs(rep, [], db_champion_ids=["a", "b", "c"])
        self.assertFalse(passed2)

    def test_r1_missing_champion_fails(self):
        rep = self._report(diffs=[], champions=["a", "b", "c"])
        rep["drivers"] = [{"driver_id": "a", "infobox_found": True},
                          {"driver_id": "b", "infobox_found": True}]   # c 漏驗
        passed, _, _, faults = cc.gate_diffs(rep, [])
        self.assertFalse(passed)
        self.assertTrue(any("身分" in f or "exact-set" in f for f in faults))

    def test_r1_extra_person_fails(self):
        rep = self._report(diffs=[], champions=["a", "b"])
        rep["drivers"].append({"driver_id": "z", "infobox_found": True})   # 多一個不在 manifest
        passed, _, _, faults = cc.gate_diffs(rep, [])
        self.assertFalse(passed)

    def test_r1_db_manifest_mismatch_default_mode_fails(self):
        """Sol 終輪 PoC②：移除 alonso 並自報 expected 34；default 模式從 DB 現算 35 → 抓到。"""
        rep = self._report(diffs=[], champions=["a", "b"])       # report 自報 2 人（缺 c）
        passed, _, _, faults = cc.gate_diffs(rep, [], db_champion_ids=["a", "b", "c"])
        self.assertFalse(passed)
        self.assertTrue(any("DB" in f for f in faults))

    def test_r1_clean_identity_passes_both_modes(self):
        rep = self._report(diffs=[], champions=["a", "b", "c"])
        self.assertTrue(cc.gate_diffs(rep, [])[0])                       # --gate-only
        self.assertTrue(cc.gate_diffs(rep, [], db_champion_ids=["a", "b", "c"])[0])  # default

    # ---- 終輪 R3：schema fail closed ----

    def test_r3_missing_diffs_block_fails(self):
        rep = self._report()
        verdicts = self._both_valid(rep)
        del rep["diffs"]
        passed, *_ , faults = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        self.assertTrue(any("`diffs`" in f for f in faults))

    def test_r3_missing_drivers_block_fails(self):
        rep = self._report()
        verdicts = self._both_valid(rep)
        del rep["drivers"]
        passed, *_ , faults = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        self.assertTrue(any("`drivers`" in f for f in faults))

    def test_r3_missing_coverage_block_fails(self):
        rep = self._report()
        verdicts = self._both_valid(rep)
        del rep["coverage"]
        passed, *_ , faults = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        self.assertTrue(any("`coverage`" in f for f in faults))

    def test_r3_keyless_verdict_fails(self):
        """缺 key 的裁決不得被 silently 忽略 → fault → FAIL。"""
        rep = self._report()
        verdicts = self._both_valid(rep) + [
            {"verdict": "definition_differs", "reason": "x", "by": "c", "date": "2026-07-21"}]
        passed, *_ , faults = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        self.assertTrue(any("缺 key" in f for f in faults))

    # ---- 第五輪 §3 新反例 ----

    def test_r5_gate_only_coherent_drop_champion_fails_with_db(self):
        """Sol §3 S0-2：report 自洽地移除一位冠軍（drivers+manifest+count 同步）；
        --gate-only 現在也帶 DB → DB 現算集合仍完整 → exact-set 不符 → FAIL。"""
        rep = self._report(diffs=[], champions=["a", "b"])   # 自洽地只剩 2 人
        passed, _, _, faults = cc.gate_diffs(rep, [], db_champion_ids=["a", "b", "c"])
        self.assertFalse(passed)
        self.assertTrue(any("DB" in f for f in faults))

    def test_r5_diffs_wrong_type_fails(self):
        """Sol §3 S0-1：diffs 是 {} 不是 list → 不得 silently 轉空 → FAIL。"""
        rep = self._report()
        rep["diffs"] = {}
        passed, _, _, faults = cc.gate_diffs(rep, [], db_champion_ids=["fangio", "senna"])
        self.assertFalse(passed)
        self.assertTrue(any("`diffs` 型別錯" in f for f in faults))

    def test_r5_drivers_wrong_type_fails(self):
        rep = self._report()
        rep["drivers"] = {}
        passed, _, _, faults = cc.gate_diffs(rep, self._both_valid(rep),
                                             db_champion_ids=["fangio", "senna"])
        self.assertFalse(passed)
        self.assertTrue(any("`drivers` 型別錯" in f for f in faults))

    def test_r5_coverage_wrong_type_fails(self):
        rep = self._report()
        verdicts = self._both_valid(rep)
        rep["coverage"] = []
        passed, _, _, faults = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        self.assertTrue(any("`coverage` 型別錯" in f for f in faults))

    def test_r5_verdicts_wrong_type_fails(self):
        rep = self._report()
        passed, _, _, faults = cc.gate_diffs(rep, {}, db_champion_ids=["fangio", "senna"])
        self.assertFalse(passed)
        self.assertTrue(any("verdicts 型別錯" in f for f in faults))

    def test_r5_duplicate_diff_key_fails(self):
        """Sol §3 S1-1：同一 diff 原樣複製成第 N 筆（21 rows / 20 keys）→ FAIL。"""
        rep = self._report()
        verdicts = self._both_valid(rep)                       # 先綁原始 diffs
        rep["diffs"] = rep["diffs"] + [dict(rep["diffs"][0])]   # 複製第一筆
        passed, _, _, faults = cc.gate_diffs(rep, verdicts, db_champion_ids=["fangio", "senna"])
        self.assertFalse(passed)
        self.assertTrue(any("diff key 重複" in f for f in faults))

    def test_f1_diff_driver_id_key_mismatch_fails(self):
        """Sol 五輪 F1：diff 的 driver_id 改成別人、key 不動 → 身分矛盾 → FAIL。"""
        rep = self._report()
        verdicts = self._both_valid(rep)
        rep["diffs"][0]["driver_id"] = "alonso"   # key 仍是原車手的 <id>|<field>
        passed, _, _, faults = cc.gate_diffs(rep, verdicts,
                                             db_champion_ids=["fangio", "senna"])
        self.assertFalse(passed)
        self.assertTrue(any("身分矛盾" in f for f in faults))

    def test_f1_diff_missing_driver_id_fails(self):
        """Sol 五輪 F1：diff 缺 driver_id → FAIL（不得靜默通過）。"""
        rep = self._report()
        verdicts = self._both_valid(rep)
        del rep["diffs"][0]["driver_id"]
        passed, _, _, faults = cc.gate_diffs(rep, verdicts,
                                             db_champion_ids=["fangio", "senna"])
        self.assertFalse(passed)
        self.assertTrue(any("缺 driver_id" in f for f in faults))

    def test_r5_expected_count_value_mismatch_fails(self):
        """Sol §3 S1-2：expected_champion_count=999 其餘不動 → count != len(unique ids) → FAIL。"""
        rep = self._report()
        verdicts = self._both_valid(rep)
        rep["coverage"]["expected_champion_count"] = 999
        passed, _, _, faults = cc.gate_diffs(rep, verdicts,
                                             db_champion_ids=["fangio", "senna"])
        self.assertFalse(passed)
        self.assertTrue(any("expected_champion_count(999)" in f for f in faults))

    def test_r5_manifest_duplicate_id_fails(self):
        rep = self._report()
        verdicts = self._both_valid(rep)
        rep["coverage"]["expected_champion_ids"] = ["fangio", "senna", "senna"]
        rep["coverage"]["expected_champion_count"] = 3
        passed, _, _, faults = cc.gate_diffs(rep, verdicts,
                                             db_champion_ids=["fangio", "senna"])
        self.assertFalse(passed)
        self.assertTrue(any("重複 id" in f for f in faults))

    def test_r5_driver_missing_id_fails(self):
        rep = self._report(extra_driver_entries=[{"infobox_found": True}])   # 無 driver_id
        passed, _, _, faults = cc.gate_diffs(rep, self._both_valid(rep),
                                             db_champion_ids=["fangio", "senna"])
        self.assertFalse(passed)
        self.assertTrue(any("driver_id" in f for f in faults))

    def test_r5_diff_missing_key_fails(self):
        rep = self._report()
        verdicts = self._both_valid(rep)                       # 先綁原始 diffs
        rep["diffs"] = rep["diffs"] + [{"driver_id": "x", "field": "entries", "ours": 1, "wiki": 2}]
        passed, _, _, faults = cc.gate_diffs(rep, verdicts, db_champion_ids=["fangio", "senna"])
        self.assertFalse(passed)
        self.assertTrue(any("非空 key" in f for f in faults))

    def test_recheck_diff_without_definition_id_fails(self):
        rep = self._report()
        verdicts = self._both_valid(rep)
        del rep["diffs"][0]["definition_id"]
        passed, unresolved, *_ = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        inv = [d for d in unresolved if d["key"] == "fangio|entries"][0]
        self.assertEqual(inv["_gate_status"], "invalid_diff")

    def test_recheck_definition_id_not_in_registry_fails(self):
        rep = self._report([self._diff("fangio", 51, 52, 111, definition_id="ghost_def"),
                            self._diff("senna", 161, 162, 222)])
        verdicts = self._both_valid(rep)
        passed, unresolved, *_ = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        self.assertIn("fangio|entries",
                      [d["key"] for d in unresolved if d["_gate_status"] == "invalid_diff"])

    # ---- 覆核 §4 新反例：null revid 互解 ----

    def test_recheck_null_revid_mutual_does_not_resolve(self):
        """diff.wiki_revid=None 且 verdict.wiki_revid=None 不得互解 → invalid_diff → FAIL。"""
        d0 = self._diff("fangio", 51, 52, None, starts=51)
        d1 = self._diff("senna", 161, 162, 222, starts=161)
        rep = self._report([d0, d1])
        v0 = self._verdict_for(d0)      # 其 wiki_revid 也是 None
        self.assertIsNone(v0["wiki_revid"])
        passed, unresolved, *_ = cc.gate_diffs(rep, [v0, self._verdict_for(d1)])
        self.assertFalse(passed)
        inv = [d for d in unresolved if d["key"] == "fangio|entries"][0]
        self.assertEqual(inv["_gate_status"], "invalid_diff")

    # ---- 覆核 §4 新反例：同 key 多裁決 ----

    def test_recheck_duplicate_verdict_same_key_fails(self):
        """同 key 放 ours_wrong + definition_differs 兩條 → 不得因 any() 放行 → FAIL。"""
        rep = self._report()
        v_ok = self._verdict_for(rep["diffs"][0])
        v_dup = self._verdict_for(rep["diffs"][0], verdict="ours_wrong")
        passed, unresolved, stale, faults = cc.gate_diffs(
            rep, [v_ok, v_dup, self._verdict_for(rep["diffs"][1])])
        self.assertFalse(passed)
        self.assertTrue(any("同 key 多筆" in f for f in faults))
        self.assertIn("fangio|entries",
                      [d["key"] for d in unresolved if d["_gate_status"] == "duplicate_verdict"])

    # ---- 覆核 §4 新反例：fingerprint 抓 wiki_starts / classification ----

    def test_recheck_only_wiki_starts_change_invalidates(self):
        """只改 wiki_starts（理由實際依賴它）→ fingerprint 變 → 舊裁決失效 → FAIL。"""
        rep = self._report()
        verdicts = self._both_valid(rep)
        rep["diffs"][0]["wiki_starts"] = 999
        passed, unresolved, *_ = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        self.assertEqual([d for d in unresolved if d["key"] == "fangio|entries"][0]["_gate_status"],
                         "binding_drift")

    def test_recheck_only_classification_change_invalidates(self):
        rep = self._report()
        verdicts = self._both_valid(rep)
        rep["diffs"][0]["classification"] = "likely_ours_wrong"
        passed, unresolved, *_ = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)

    def test_r2_only_reason_change_invalidates(self):
        """Sol 終輪 S1-1：只改 diff.reason（其餘不動）→ fingerprint 變 → 舊裁決失效 → FAIL。"""
        rep = self._report()
        verdicts = self._both_valid(rep)
        rep["diffs"][0]["reason"] = "完全相反的 synthetic rationale"
        passed, unresolved, *_ = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        self.assertEqual([d for d in unresolved if d["key"] == "fangio|entries"][0]["_gate_status"],
                         "binding_drift")

    def test_recheck_registry_content_change_invalidates(self):
        """公式內容改了但 definition_id 沒升版 → registry sha 變 → fingerprint 變 → 舊裁決失效。"""
        rep = self._report()
        verdicts = self._both_valid(rep)     # 綁定當下的 registry sha
        did = rep["diffs"][0]["definition_id"]
        orig = cc.DEFINITION_REGISTRY[did]
        cc.DEFINITION_REGISTRY[did] = {**orig, "formula": orig["formula"] + " (改過)"}
        try:
            passed, unresolved, *_ = cc.gate_diffs(rep, verdicts)
        finally:
            cc.DEFINITION_REGISTRY[did] = orig
        self.assertFalse(passed)

    # ---- 其他綁定 ----

    def test_legacy_verdict_without_fingerprint_does_not_resolve(self):
        rep = self._report()
        legacy = {"key": "fangio|entries", "verdict": "definition_differs",
                  "reason": "x", "by": "charlie", "date": "2026-07-21",
                  "definition_id": "results_distinct_races", "bound_ours": 51,
                  "bound_wiki": 52, "wiki_revid": 111}   # 無 bound_fingerprint
        passed, unresolved, *_ = cc.gate_diffs(rep, [legacy, self._verdict_for(rep["diffs"][1])])
        self.assertFalse(passed)
        self.assertIn("fangio|entries", [d["key"] for d in unresolved])

    def test_stale_alongside_resolved_still_fails(self):
        rep = self._report()
        verdicts = self._both_valid(rep) + [self._verdict_for(self._diff("ghost", 1, 2, 3))]
        passed, unresolved, stale, faults = cc.gate_diffs(rep, verdicts)
        self.assertFalse(passed)
        self.assertEqual(unresolved, [])
        self.assertEqual(stale, ["ghost|entries"])


class RealVerdictsTests(unittest.TestCase):
    """對真實裁決檔＋真實報告的整合斷言。"""

    def test_real_verdicts_are_named_and_bound(self):
        """每條真實裁決具名完整且帶齊綁定欄（含 bound_fingerprint）。"""
        allowed = {"ours_wrong", "definition_differs", "wiki_wrong"}
        verdicts = cc.load_verdicts()
        self.assertGreater(len(verdicts), 0)
        for v in verdicts:
            for field in ("key", "verdict", "reason", "by", "date"):
                self.assertTrue(str(v.get(field, "")).strip(), f"{v.get('key')} 缺 {field}")
            self.assertIn(v["verdict"], allowed, v["key"])
            for field in ("definition_id", "bound_ours", "bound_wiki", "wiki_revid", "bound_fingerprint"):
                self.assertIsNotNone(v.get(field), f"{v['key']} 缺綁定欄 {field}")

    def test_real_report_gate_passes(self):
        """真實 report + 真實裁決必須通過硬 gate（含 DB 權威身分比對，R1）。

        report 是本 PR 決定入版控的提交物（釘 revid 的外部原始快照，比照 raw 層）；
        因此**不再 skip**——report 不存在＝提交物不完整＝視為失敗（覆核最低條件 5）。
        """
        import json
        self.assertTrue(cc.REPORT.exists(),
                        "crosscheck-report.json 必須存在並入版控（跑 crosscheck-wikipedia.py 產生）")
        rep = json.loads(cc.REPORT.read_text(encoding="utf-8"))
        db = cc.db_champion_ids() if cc.DEFAULT_DB.exists() else None
        passed, unresolved, stale, faults = cc.gate_diffs(rep, cc.load_verdicts(), db_champion_ids=db)
        self.assertTrue(passed, f"未解={[d['key'] for d in unresolved]} stale={stale} faults={faults}")

    def test_real_report_identity_manifest_matches_db(self):
        """report 的 expected_champion_ids 必須與 DB 現算冠軍集合逐一相符（身分 manifest 完整）。"""
        import json
        if not cc.DEFAULT_DB.exists():
            self.skipTest("db.sqlite 不存在")
        rep = json.loads(cc.REPORT.read_text(encoding="utf-8"))
        self.assertEqual(set(rep["coverage"]["expected_champion_ids"]),
                         set(cc.db_champion_ids()))


class GateOnlyCliTests(unittest.TestCase):
    """第五輪 fix1：--gate-only 走 CLI 也必須讀 DB；db 缺席＝FAIL closed。"""

    SCRIPT = ROOT / "scripts" / "crosscheck-wikipedia.py"

    def _run(self, *args):
        import subprocess, sys
        return subprocess.run([sys.executable, str(self.SCRIPT), *args],
                              capture_output=True, text=True)

    def test_gate_only_passes_with_real_db(self):
        if not (cc.REPORT.exists() and cc.DEFAULT_DB.exists()):
            self.skipTest("report 或 db 不存在")
        r = self._run("--gate-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_gate_only_missing_db_fails_closed(self):
        """--gate-only 指向不存在的 db → exit 1（不退回 report 自證）。"""
        r = self._run("--gate-only", "--db", "/tmp/__no_such_db__.sqlite")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail closed", r.stdout + r.stderr)

    def test_gate_only_catches_coherent_drop_via_cli(self):
        """把真實 report 自洽地移除一位冠軍寫到暫存檔，--gate-only（帶真實 DB）必須 exit 1。"""
        import json, tempfile, os
        if not (cc.REPORT.exists() and cc.DEFAULT_DB.exists()):
            self.skipTest("report 或 db 不存在")
        rep = json.loads(cc.REPORT.read_text(encoding="utf-8"))
        # 挑一位「沒有 diff」的冠軍（比照 Sol PoC 的 alonso），移除後只剩 coverage 身分不符
        diff_drivers = {d["driver_id"] for d in rep["diffs"]}
        no_diff = sorted(c for c in rep["coverage"]["expected_champion_ids"] if c not in diff_drivers)
        victim = no_diff[0]
        rep["drivers"] = [d for d in rep["drivers"] if d.get("driver_id") != victim]
        rep["coverage"]["expected_champion_ids"] = [
            i for i in rep["coverage"]["expected_champion_ids"] if i != victim]
        rep["coverage"]["expected_champion_count"] = len(rep["coverage"]["expected_champion_ids"])
        fd, tmp = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(rep, f, ensure_ascii=False)
            r = self._run("--gate-only", "--out", tmp)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("DB 現算冠軍集合不符", r.stdout + r.stderr)
        finally:
            os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
