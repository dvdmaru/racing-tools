#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M6 回歸測試——譯名表格式升級相容層、check-zh 三規則 + legacy 允許清單、圖的邊一致性/決定性。

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import pathlib
import sqlite3
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rc = _load("racinglib_m6", "racinglib.py")
cz = _load("check_zh_m6", "check-zh.py")
edges_mod = _load("build_graph_edges_m6", "build-graph-edges.py")

DB = ROOT / "data" / "f1" / "db.sqlite"


# ---------- 1. 格式升級相容層：_load_zh ----------

class ZhFormatCompatTests(unittest.TestCase):
    def _write(self, tmp, obj):
        p = tmp / "driver-zh.json"
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return p

    def setUp(self):
        import tempfile
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.orig_root = rc.ROOT
        # _load_zh 讀 ROOT/scripts/<fname>；把 scripts 指到 tmp
        (self.tmp / "scripts").mkdir()
        self.addCleanup(setattr, rc, "ROOT", self.orig_root)

    def _load_from(self, obj):
        (self.tmp / "scripts" / "x-zh.json").write_text(
            json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        rc.ROOT = self.tmp
        return rc._load_zh("x-zh.json")

    def test_new_dict_approved_included(self):
        out = self._load_from({"a": {"zh": "甲", "src": "approved-live", "status": "approved"}})
        self.assertEqual(out, {"a": "甲"})

    def test_pending_excluded_invisible_to_pages(self):
        out = self._load_from({
            "a": {"zh": "甲", "src": "approved-live", "status": "approved"},
            "b": {"zh": "乙候選", "src": "zhwiki", "status": "pending"},
        })
        self.assertEqual(out, {"a": "甲"})
        self.assertNotIn("b", out)

    def test_legacy_flat_string_treated_approved(self):
        out = self._load_from({"a": "甲", "_comment": "x"})
        self.assertEqual(out, {"a": "甲"})

    def test_not_found_and_missing_zh_excluded(self):
        out = self._load_from({
            "a": {"zh": "甲", "status": "approved"},
            "nf": {"zh": None, "status": "not_found"},
            "nz": {"status": "approved"},
        })
        self.assertEqual(out, {"a": "甲"})


class ZhTablesAreUpgradedTests(unittest.TestCase):
    """四張表已升級成 dict 格式，且既有條目全為 approved（append-only 保存）。"""
    def test_all_four_tables_dict_format_approved(self):
        for fn in ("driver-zh.json", "team-zh.json", "race-zh.json", "circuit-zh.json"):
            raw = json.loads((ROOT / "scripts" / fn).read_text(encoding="utf-8"))
            entries = {k: v for k, v in raw.items() if not k.startswith("_")}
            self.assertTrue(entries, f"{fn} 應有條目")
            for k, v in entries.items():
                self.assertIsInstance(v, dict, f"{fn}:{k} 應為 dict")
                self.assertEqual(v.get("status"), "approved", f"{fn}:{k} 既有條目應 approved")
                self.assertTrue(v.get("zh"), f"{fn}:{k} 應有 zh")

    def test_reader_still_returns_expected_current_season_names(self):
        # 相容層對頁面透明：現行譯名讀出不變（byte-identical 頁面的根據）
        self.assertEqual(rc.DRIVER_ZH.get("hamilton"), "漢米爾頓")
        self.assertEqual(rc.TEAM_ZH.get("ferrari"), "法拉利")
        self.assertEqual(rc.RACE_ZH.get("Australian Grand Prix"), "澳洲站")
        self.assertEqual(rc.CIRCUIT_ZH.get("silverstone"), "銀石賽道")


# ---------- 2. check-zh 三規則 + legacy 允許清單 ----------

class CheckZhRuleTests(unittest.TestCase):
    EMPTY = {"driver": {}, "constructor": {}, "race": {}, "circuit": {}}

    def _run(self, tabs, head=None, allow=None, phase0=None):
        return cz.run_checks(
            tabs=tabs,
            head_tabs=head if head is not None else self.EMPTY,
            allowlist=allow if allow is not None else {},
            phase0=phase0 if phase0 is not None else {"driver": {}, "constructor": {}},
        )

    def test_rule1_conflict_across_sources_errors(self):
        # driver a：表姓氏「甲」vs phase0 全名「乙・丙」（姓氏丙）→ 用字分歧 → 衝突
        tabs = {**self.EMPTY, "driver": {"a": "甲"}}
        res = self._run(tabs, phase0={"driver": {"a": "乙・丙"}, "constructor": {}})
        self.assertTrue(any("規則①" in e for e in res["errors"]))

    def test_rule1_family_match_no_conflict(self):
        # driver a：表姓氏「維斯塔潘」vs phase0 全名「麥克斯・維斯塔潘」→ 姓氏一致 → 不算衝突
        tabs = {**self.EMPTY, "driver": {"a": "維斯塔潘"}}
        res = self._run(tabs, phase0={"driver": {"a": "麥克斯・維斯塔潘"}, "constructor": {}})
        self.assertFalse(any("規則①" in e for e in res["errors"]))

    def test_rule1_allowlisted_conflict_downgraded_to_warning(self):
        tabs = {**self.EMPTY, "driver": {"a": "甲"}}
        allow = {("driver", "a"): {"namespace": "driver", "id": "a"}}
        res = self._run(tabs, allow=allow, phase0={"driver": {"a": "乙・丙"}, "constructor": {}})
        self.assertFalse(any("規則①" in e for e in res["errors"]))
        self.assertTrue(any("規則①" in w for w in res["warnings"]))

    def test_rule2_same_name_two_entities_errors(self):
        # 兩個不同 driver id 對到逐字相同的譯名「舒馬克」→ 不可區分 → 碰撞
        tabs = {**self.EMPTY, "driver": {"michael_s": "舒馬克", "ralf_s": "舒馬克"}}
        res = self._run(tabs)
        self.assertTrue(any("規則②" in e for e in res["errors"]))

    def test_rule2_same_surname_distinct_fullname_not_flagged(self):
        # 同姓不同人：Graham/Damon/Phil Hill 姓氏皆「希爾」但全名相異 → 規則②不得誤判碰撞。
        # （回歸：舊版用姓氏正規化當鍵會把三位 Hill 判成同一實體碰撞；改用完整 zh 值後修正。）
        tabs = {**self.EMPTY, "driver": {
            "hill": "格拉漢姆・希爾", "damon_hill": "戴蒙・希爾", "phil_hill": "菲爾・希爾"}}
        res = self._run(tabs)
        self.assertFalse(any("規則②" in e for e in res["errors"]),
                         f"同姓不同人不應觸發規則②：{res['errors']}")

    def test_rule2_distinguishable_michael_ralf_schumacher_ok(self):
        # docstring 原意：M./R. 舒馬克全名相異即可區分 → 不碰撞。
        tabs = {**self.EMPTY, "driver": {
            "michael_schumacher": "麥可・舒馬克", "ralf_schumacher": "拉爾夫・舒馬克"}}
        res = self._run(tabs)
        self.assertFalse(any("規則②" in e for e in res["errors"]))

    def test_rule2_team_name_id_alias_not_flagged(self):
        # 車隊顯示名 + id 兩鍵同 zh ＝同一實體別名 → 不算碰撞
        tabs = {**self.EMPTY, "constructor": {"Ferrari": "法拉利", "ferrari": "法拉利"}}
        res = self._run(tabs)
        self.assertFalse(any("規則②" in e for e in res["errors"]))

    def test_rule3_changed_approved_value_errors(self):
        head = {**self.EMPTY, "driver": {"x": "原譯"}}
        tabs = {**self.EMPTY, "driver": {"x": "改譯"}}
        res = self._run(tabs, head=head)
        self.assertTrue(any("規則③" in e for e in res["errors"]))

    def test_rule3_deleted_approved_value_errors(self):
        head = {**self.EMPTY, "driver": {"x": "原譯"}}
        tabs = {**self.EMPTY, "driver": {}}
        res = self._run(tabs, head=head)
        self.assertTrue(any("規則③" in e for e in res["errors"]))

    def test_rule3_addition_ok(self):
        head = {**self.EMPTY, "driver": {"x": "原譯"}}
        tabs = {**self.EMPTY, "driver": {"x": "原譯", "y": "新增"}}
        res = self._run(tabs, head=head)
        self.assertFalse(any("規則③" in e for e in res["errors"]))

    def test_resolved_allowlist_entry_suppresses_warning(self):
        # 已裁決收斂條目（allowlist 帶 resolved 欄）：即便仍存在衝突，既不 error 也不 warning。
        tabs = {**self.EMPTY, "driver": {"a": "甲"}}
        allow = {("driver", "a"): {"namespace": "driver", "id": "a", "resolved": "甲"}}
        res = self._run(tabs, allow=allow, phase0={"driver": {"a": "乙・丙"}, "constructor": {}})
        self.assertFalse(any("規則①" in e for e in res["errors"]))
        self.assertFalse(any("規則①" in w for w in res["warnings"]),
                         "resolved 條目不應再出 warning")


class CheckZhLiveTests(unittest.TestCase):
    """實跑（真實表 + phase0 + 允許清單 + git HEAD）：hamilton 2026-07-23 已裁決收斂為『漢米爾頓』，
    phase0 seed 與 driver-zh 姓氏一致 → 0 error 且無 hamilton warning。"""
    def test_live_gate_passes_no_error_no_hamilton_warning(self):
        res = cz.run_checks()
        self.assertEqual(res["errors"], [], f"實跑不應有 error：{res['errors']}")
        self.assertFalse(any("hamilton" in w for w in res["warnings"]),
                         f"hamilton 已收斂，不應再出 warning：{res['warnings']}")

    def test_hamilton_single_translation_across_sources(self):
        # 收斂後 phase0 seed 與 driver-zh 的 hamilton 姓氏用字一致（皆『漢米爾頓』）。
        driver = cz.load_tables()["driver"]
        self.assertEqual(driver.get("hamilton"), "漢米爾頓")
        self.assertEqual(cz.family_norm(cz.PHASE0_ZH["driver"]["hamilton"]), "漢米爾頓")

    def test_allowlist_file_names_hamilton(self):
        allow = cz.load_allowlist()
        self.assertIn(("driver", "hamilton"), allow)

    def test_hamilton_allowlist_entry_is_resolved(self):
        allow = cz.load_allowlist()
        self.assertTrue(cz._is_resolved(allow, "driver", "hamilton"),
                        "hamilton 條目應標記為 resolved（審計軌跡保留）")


# ---------- 3. 圖的邊：一致性 + 決定性 ----------

class GraphEdgesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        cls.edges, cls.counts = edges_mod.collect(conn)
        conn.close()

    def _direct(self, sql):
        conn = sqlite3.connect(DB)
        n = conn.execute(sql).fetchone()[0]
        conn.close()
        return n

    def test_won_championship_count_matches_sqlite(self):
        n = self._direct("SELECT count(*) FROM driver_standings ds JOIN seasons s "
                         "ON s.year=ds.season WHERE ds.position=1 AND s.status='completed'")
        self.assertEqual(self.counts["won_championship"], n)

    def test_drove_for_count_matches_sqlite(self):
        n = self._direct("SELECT count(*) FROM (SELECT DISTINCT season, driver_id, constructor_id "
                         "FROM results WHERE constructor_id IS NOT NULL)")
        self.assertEqual(self.counts["drove_for"], n)

    def test_raced_at_count_matches_sqlite(self):
        n = self._direct("SELECT count(*) FROM (SELECT DISTINCT r.driver_id, ra.circuit_id "
                         "FROM results r JOIN races ra ON ra.season=r.season AND ra.round=r.round)")
        self.assertEqual(self.counts["raced_at"], n)

    def test_finished_count_matches_sqlite(self):
        n = self._direct("SELECT count(*) FROM results")
        self.assertEqual(self.counts["finished"], n)

    def test_total_equals_len(self):
        self.assertEqual(len(self.edges), sum(self.counts.values()))

    def test_node_id_scheme_prefixed(self):
        for e in self.edges[:200]:
            self.assertIn(":", e["from"])
            self.assertIn(":", e["to"])
            self.assertTrue(e["from"].startswith("driver:"))

    def test_deterministic_two_runs_identical(self):
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        e1, _ = edges_mod.collect(conn)
        e2, _ = edges_mod.collect(conn)
        conn.close()
        self.assertEqual(json.dumps(e1, ensure_ascii=False, sort_keys=True),
                         json.dumps(e2, ensure_ascii=False, sort_keys=True))

    def test_doc_has_meta_and_counts(self):
        doc = edges_mod.build(check_only=True)
        self.assertIn("_meta", doc)
        self.assertEqual(doc["_meta"]["total"], len(doc["edges"]))
        self.assertEqual(set(doc["_meta"]["counts"]), set(edges_mod.EDGE_ORDER))


if __name__ == "__main__":
    unittest.main()
