#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M5 車手頁生成器回歸測試（gen-racing-drivers.py）。

鎖住驗收條件與紅線：
- 前置三 gate（invariants／verdicts／golden）各自的 exit-1 行為：合成壞 invariant／抽走一條
  verdict／篡改 golden 一值 → gate False（且 main 走 gate 失敗時零產出）。
- 35 冠軍＋2026 現役 22 人的聯集 53 頁全生成，雙分區索引完整。
- §4.6 紅線：桿位／最快圈／生涯積分不得以「數據形式」出現在任何頁（只允許 na 佔位卡）。
- golden value == len(detail)（衍生數字紀律）。
- 譯名誠實 fallback（無譯名者原文-only + 頁尾註明；seed 有全名譯名）。
- 全站死連結掃描 = 0（車手頁對 seasons/constructors 的深連結都有對應生成檔）。
- 決定性：跑兩次 byte-identical。
- phase0 不再產車手頁。
- 零 client fetch／除白名單外零 script；外連只限白名單 host；JSON-LD 不放 image。

跑法：python3 -m unittest discover -s tests -v
"""
import argparse
import importlib.util
import json
import pathlib
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dr = _load("gen_racing_drivers", "gen-racing-drivers.py")
rc = dr.rc
fs = dr.fs
p0 = dr.p0
gs = dr.gs
cg = _load("gen_racing_constructors_for_driver_tests", "gen-racing-constructors.py")

# 姊妹站那段從 rc.SISTER_SITES 推導，不手抄（原本三個測試檔各一份，加一站要改四處）。
ALLOWED_HOSTS = {
    "fonts.googleapis.com", "fonts.gstatic.com", "www.googletagmanager.com",
    "schema.org", "en.wikipedia.org", "racing.twtools.cc",
} | {urlsplit(u).netloc for _, u in rc.SISTER_SITES}
FORBIDDEN_LABELS = ("桿位", "最快圈", "生涯積分")
ALLOWED_STAT_LABELS = ("世界冠軍", "分站冠軍", "頒獎台", "參賽場次")


def _render_all(tmp, con=None):
    """把索引 + champion ∪ active 的 53 車手頁渲染進 tmp，回傳 {slug: html}。"""
    own = con is None
    con = con or fs.connect_db()
    orig = dr.PUB
    dr.PUB = tmp
    try:
        dr.render_index(con)
        out = {}
        for did in dr.DRIVER_IDS:
            s = dr.gen_driver(did, con)
            out[s["slug"]] = (tmp / "drivers" / s["slug"] / "index.html").read_text(encoding="utf-8")
        return out
    finally:
        dr.PUB = orig
        if own:
            con.close()


# ---------- gate exit-1 行為 ----------

def _approved_copy(src, tmp, key):
    data = json.loads(src.read_text(encoding="utf-8"))
    for row in data[key].values() if isinstance(data[key], dict) else data[key]:
        if str(row.get("approved_by", row.get("by", ""))).startswith("PENDING"):
            if "approved_by" in row:
                row["approved_by"] = "charlie-test"
            else:
                row["by"] = "charlie-test"
    out = tmp / src.name
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return out


class GatePassTests(unittest.TestCase):
    """基礎不變量綠；2026-08-13 Charlie 全批核准後，真實 repo 的三 gate 均應綠。
    PENDING 拒絕行為由合成 fixture 測試守（本 class 下方與 test_crosscheck），不綁 repo 暫態。"""

    def test_invariants_gate_passes(self):
        self.assertTrue(dr.gate_invariants())

    def test_verdicts_gate_green_in_approved_steady_state(self):
        self.assertTrue(dr.gate_verdicts())

    def test_golden_gate_green_in_approved_steady_state(self):
        self.assertTrue(dr.gate_golden())

    def test_run_gates_all_green_in_approved_steady_state(self):
        self.assertTrue(dr.run_gates())

    def test_golden_gate_rejects_synthetic_pending(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        data = json.loads(dr.GOLDEN.read_text(encoding="utf-8"))
        first = next(iter(data["drivers"]))
        data["drivers"][first]["approved_by"] = "PENDING-charlie"
        bad = tmp / "golden-pending.json"
        bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(dr.gate_golden(golden_path=bad))

    def test_verdicts_gate_rejects_synthetic_pending(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        data = json.loads(dr.VERDICTS.read_text(encoding="utf-8"))
        data["verdicts"][0]["by"] = "PENDING-charlie"
        bad = tmp / "verdicts-pending.json"
        bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(dr.gate_verdicts(verdicts=bad))

    def test_both_pending_gates_pass_after_synthetic_approval(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        verdicts = _approved_copy(dr.VERDICTS, tmp, "verdicts")
        golden = _approved_copy(dr.GOLDEN, tmp, "drivers")
        self.assertTrue(dr.gate_verdicts(verdicts=verdicts))
        self.assertTrue(dr.gate_golden(golden_path=golden))


class InvariantGateFailTests(unittest.TestCase):
    """合成壞 invariant → gate ① False（零產出）。"""

    def test_broken_db_fails_invariant_gate(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        bad = tmp / "bad.sqlite"
        shutil.copy(dr.DB, bad)
        con = sqlite3.connect(str(bad))
        # 灌水某位車手某場積分 → 該季 gross ≠ 官方 standings（I6 mismatch，未宣告失敗）
        con.execute("UPDATE results SET points = points + 50 "
                    "WHERE id = (SELECT id FROM results WHERE position_text='1' LIMIT 1)")
        con.commit()
        con.close()
        self.assertFalse(dr.gate_invariants(db=bad),
                         "合成壞 invariant 應使 gate ① 失敗")

    def test_main_zero_output_when_gates_fail(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig_pub, orig_gates = dr.PUB, dr.run_gates
        dr.PUB = tmp
        dr.run_gates = lambda *a, **k: False
        old_argv = sys.argv
        sys.argv = ["gen-racing-drivers.py"]
        try:
            rcode = dr.main()
        finally:
            dr.PUB, dr.run_gates = orig_pub, orig_gates
            sys.argv = old_argv
        self.assertEqual(rcode, 1)
        self.assertFalse((tmp / "drivers").exists(), "gate 失敗時不得產任何頁")


class VerdictGateFailTests(unittest.TestCase):
    """抽走一條 verdict → gate ② False（未裁決 diff）。"""

    def test_missing_verdict_fails_gate(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        data = json.loads(dr.VERDICTS.read_text(encoding="utf-8"))
        for v in data["verdicts"]:
            if str(v.get("by", "")).startswith("PENDING"):
                v["by"] = "charlie-test"
        data["verdicts"] = data["verdicts"][1:]  # 抽掉第一條
        bad = tmp / "verdicts.json"
        bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(dr.gate_verdicts(verdicts=bad),
                         "抽走一條 verdict 後應有未解 diff → gate ② 失敗")


class GoldenGateFailTests(unittest.TestCase):
    """篡改 golden 一值 → gate ③ False。"""

    def test_tampered_golden_fails_gate(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        data = json.loads(dr.GOLDEN.read_text(encoding="utf-8"))
        for row in data["drivers"].values():
            if str(row.get("approved_by", "")).startswith("PENDING"):
                row["approved_by"] = "charlie-test"
        data["drivers"]["fangio"]["wins"] += 1  # 竄改一值
        bad = tmp / "golden.json"
        bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(dr.gate_golden(golden_path=bad),
                         "golden 值被竄改後應與 f1stats 現值不符 → gate ③ 失敗")

    def test_golden_list_mismatch_fails_gate(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        data = json.loads(dr.GOLDEN.read_text(encoding="utf-8"))
        data["drivers"].pop("fangio")  # 名單缺一人
        bad = tmp / "golden.json"
        bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(dr.gate_golden(golden_path=bad))

    def test_active_champion_stale_as_of_fails_gate(self):
        """現役冠軍即使具名核准，仍不得沿用落後 roster 的自洽凍結值。"""
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        approved = _approved_copy(dr.GOLDEN, tmp, "drivers")
        data = json.loads(approved.read_text(encoding="utf-8"))
        data["drivers"]["alonso"]["entries"] = 438
        data["drivers"]["alonso"]["as_of"] = {"season": 2026, "round": 10}
        approved.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(dr.gate_golden(golden_path=approved),
                         "現役冠軍 as_of 落後現役 roster 時點時，gate 必須拒絕")


# ---------- golden 紀律 ----------

class GoldenDisciplineTests(unittest.TestCase):
    """golden value == len(detail)（衍生數字紀律）；且與 golden 凍結值一致。"""

    @classmethod
    def setUpClass(cls):
        cls.con = fs.connect_db()
        cls.golden = json.loads(dr.GOLDEN.read_text(encoding="utf-8"))["drivers"]

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_value_equals_len_detail_and_matches_golden(self):
        """☠️ 這條原本漏傳 `as_of`，是從 2026-07-23 核准 golden 起就潛伏的 bug。

        golden 是 **as_of 凍結值**：活躍車手凍結在 {2026, R11}，設計上新賽果不該打破 gate
        （生成器的 `gate_golden()` 有正確傳 as_of）。但這裡拿**全量現值**去比凍結值，
        於是第一場新賽果（2026 R11 匈牙利）一進來就爆——alonso entries 439 撞 golden 438。

        它整整潛伏了 11 天沒被發現，因為在那之前百科資料庫是凍結的、根本沒有新賽果。
        **一個永遠沒有新輸入的測試，綠不代表它會動。**
        """
        for did in dr.DRIVER_IDS:
            as_of = self.golden[did].get("as_of")
            car = fs.driver_career_db(did, self.con, as_of=as_of)
            champ = fs.driver_championships_db(did, self.con, as_of=as_of)
            for key, stat in (("wins", car["wins"]), ("podiums", car["podiums"]),
                              ("entries", car["entries"]), ("championships", champ)):
                self.assertEqual(stat["value"], len(stat["detail"]),
                                 f"{did} {key} value 與明細筆數不符")
                self.assertEqual(stat["value"], self.golden[did][key],
                                 f"{did} {key} 與 golden 不符")
            self.assertEqual([d["season"] for d in champ["detail"]],
                             self.golden[did]["championship_years"])

    def test_golden_covers_exact_union(self):
        self.assertEqual(set(self.golden), set(dr.DRIVER_IDS))
        self.assertEqual(len(self.golden), 53)


# ---------- 產出完整性 ----------

class GenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.pages = _render_all(cls.tmp)
        cls.index = (cls.tmp / "drivers" / "index.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_all_53_driver_pages_generated(self):
        self.assertEqual(len(self.pages), 53)
        for did in dr.DRIVER_IDS:
            slug = rc.driver_slug(did)
            self.assertTrue((self.tmp / "drivers" / slug / "index.html").is_file(),
                            f"{did} 車手頁未生成")

    def test_index_lists_all_35_with_links(self):
        for did in dr.CHAMPION_IDS:
            slug = rc.driver_slug(did)
            self.assertIn(f'href="/drivers/{slug}/"', self.index, f"索引缺 {slug}")

    def test_index_itemlist_has_35(self):
        m = re.search(r'"@type":"ItemList".*?"numberOfItems":(\d+)', self.index)
        self.assertTrue(m)
        self.assertEqual(int(m.group(1)), 35)
        # ListItem = ItemList 的 35 + BreadcrumbList 的 2（首頁／車手）
        self.assertEqual(self.index.count('"@type":"ListItem"'), 59)

    def test_active_section_lists_all_22(self):
        self.assertIn("2026 現役陣容", self.index)
        for did in dr.ACTIVE_IDS:
            self.assertIn(f'href="/drivers/{rc.driver_slug(did)}/"', self.index)

    def test_publish_fields_present_and_numeric(self):
        # 抽 fangio：四發布欄位皆為數字 stat-v
        h = self.pages["fangio"]
        for label in ALLOWED_STAT_LABELS:
            self.assertIn(f'<div class="stat-l">{label}</div>', h)

    def test_person_and_breadcrumb_jsonld_no_image(self):
        h = self.pages["fangio"]
        self.assertIn('"@type":"Person"', h)
        self.assertIn('"@type":"BreadcrumbList"', h)
        # sameAs = 維基；不放 image、不捏造欄位
        self.assertIn("en.wikipedia.org", h)
        self.assertNotIn('"image"', h)

    def test_each_number_has_how_details(self):
        # 每個發布數字掛 CSS-only <details>「怎麼算的」
        h = self.pages["fangio"]
        self.assertGreaterEqual(h.count("怎麼算的"), 4)
        self.assertIn("<details", h)


# ---------- §4.6 紅線：三欄位不以數據形式出現 ----------

class Section46RedlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.pages = _render_all(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def _stat_blocks(self, html):
        """回 [(is_na, value, label)]：每張 stat 卡的類別／stat-v 值／stat-l 標籤。"""
        out = []
        for m in re.finditer(
                r'<div class="stat( na)?">\s*<div class="stat-v mono">(.*?)</div>\s*'
                r'<div class="stat-l">([^<]*)</div>', html, re.S):
            na = bool(m.group(1))
            val = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            out.append((na, val, m.group(3)))
        return out

    def test_forbidden_fields_never_as_data(self):
        for slug, html in self.pages.items():
            blocks = self._stat_blocks(html)
            self.assertTrue(blocks, f"{slug} 無 stat 卡")
            for na, val, label in blocks:
                if label in FORBIDDEN_LABELS:
                    self.assertTrue(na, f"{slug} 的「{label}」不是 na 卡（不得以數據形式出現）")
                    self.assertEqual(val, "—", f"{slug}「{label}」stat-v 應為 —，實得 {val!r}")

    def test_forbidden_labels_have_no_numeric_value(self):
        # grep 級：任何數字型 stat-v 的標籤只能是四個發布欄位之一
        for slug, html in self.pages.items():
            for na, val, label in self._stat_blocks(html):
                if val.isdigit():
                    self.assertIn(label, ALLOWED_STAT_LABELS,
                                  f"{slug}：數字欄位「{label}」不在發布白名單")
                    self.assertNotIn(label, FORBIDDEN_LABELS)

    def test_forbidden_fields_marked_followup(self):
        h = self.pages["fangio"]
        self.assertIn("後續補", h)


# ---------- 譯名誠實 fallback ----------

class TranslationFallbackTests(unittest.TestCase):
    # M6（2026-07-23）回填後 35 位冠軍全數具 approved 譯名（含 ascari＝阿爾貝托・阿斯卡里），
    # 誠實 fallback 路徑不再由任何冠軍頁觸發。改以一位無譯名的非冠軍車手（barrichello）驗證
    # fallback 渲染——臨時注入 slug（不動 append-only 真表 data/f1/slugs.json）。
    UNTR = "barrichello"

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.pages = _render_all(cls.tmp)
        cls.con = fs.connect_db()
        cls._slug_injected = cls.UNTR not in rc._SLUGS.get("drivers", {})
        if cls._slug_injected:
            rc._SLUGS.setdefault("drivers", {})[cls.UNTR] = cls.UNTR
        cls.tmp2 = pathlib.Path(tempfile.mkdtemp())
        orig = dr.PUB
        dr.PUB = cls.tmp2
        try:
            s = dr.gen_driver(cls.UNTR, cls.con)
            cls.untr_html = (cls.tmp2 / "drivers" / s["slug"] / "index.html").read_text(encoding="utf-8")
        finally:
            dr.PUB = orig

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)
        shutil.rmtree(cls.tmp2)
        if cls._slug_injected:
            rc._SLUGS["drivers"].pop(cls.UNTR, None)
        cls.con.close()

    def test_untranslated_driver_is_original_only(self):
        # barrichello 無 approved 譯名 → 中文欄位整個不出現、只留原文 + 頁尾註明
        self.assertIsNone(dr.resolve_zh(self.UNTR))
        h = self.untr_html
        self.assertIn('<span class="en-only">Rubens Barrichello</span>', h)
        self.assertIn("尚無定版繁中譯名", h)

    def test_seed_driver_has_approved_fullname(self):
        # hamilton 2026-07-23 收斂為『漢』米爾頓（全站統一用字）
        h = self.pages["hamilton"]
        self.assertIn("路易斯・漢米爾頓", h)
        self.assertNotIn("路易斯・韓密爾頓", h)
        self.assertNotIn("尚無定版繁中譯名", h)

    def test_no_self_translation_for_unknown(self):
        # fallback 不得憑空生一個中文名（title 用原文）
        h = self.untr_html
        self.assertIn("<title>Rubens Barrichello生涯數據", h)

    def test_all_champions_have_approved_translation(self):
        # M6 回填後：35 位冠軍全數具 approved 譯名（誠實 fallback 不再由任何冠軍頁觸發）。
        missing = [c for c in dr.CHAMPION_IDS if dr.resolve_zh(c) is None]
        self.assertEqual(missing, [], f"仍有冠軍無譯名：{missing}")


# ---------- 零 client JS／外連白名單 ----------

class NoScriptNoFetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.pages = _render_all(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_no_client_fetch(self):
        for slug, h in self.pages.items():
            for banned in ("fetch(", "XMLHttpRequest", "WebSocket", ".ajax"):
                self.assertNotIn(banned, h, f"{slug} 出現 client fetch：{banned}")

    def test_only_whitelisted_scripts(self):
        h = self.pages["fangio"]
        for b in re.findall(r"<script[^>]*>.*?</script>", h, re.S):
            ok = ('application/ld+json' in b or 'googletagmanager.com/gtag' in b
                  or 'gtag(' in b or 'rc-theme' in b or 'setTheme' in b or 'THEMES' in b)
            self.assertTrue(ok, f"非白名單 script：{b[:80]}")

    def test_external_hosts_whitelisted(self):
        for slug, h in self.pages.items():
            hosts = set(re.findall(r"https?://([a-zA-Z0-9.-]+)", h))
            self.assertFalse(hosts - ALLOWED_HOSTS, f"{slug} 白名單外外連：{hosts - ALLOWED_HOSTS}")


# ---------- 決定性 ----------

class DeterminismTests(unittest.TestCase):
    def test_existing_champion_pages_gain_only_current_constructor_links(self):
        """本棒允許效力車隊區新增 2026 車隊連結；其餘頁面內容必須不動。"""
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        con = fs.connect_db()
        old_pub = dr.PUB
        dr.PUB = tmp
        try:
            for did in dr.CHAMPION_IDS:
                row = dr.gen_driver(did, con)
                rel = pathlib.Path("drivers") / row["slug"] / "index.html"
                new = (tmp / rel).read_text(encoding="utf-8")
                old = (old_pub / rel).read_text(encoding="utf-8")
                def without_links(value):
                    return re.sub(r'<a href="/constructors/[^\"]+/">([^<]+)</a>',
                                  r'<span class="rel-off">\1</span>', value)
                self.assertEqual(without_links(new), without_links(old),
                                 f"效力車隊連結外意外改動既有冠軍頁：{did}")
        finally:
            dr.PUB = old_pub
            con.close()

    def test_two_runs_byte_identical(self):
        a = pathlib.Path(tempfile.mkdtemp())
        b = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, a)
        self.addCleanup(shutil.rmtree, b)
        con = fs.connect_db()
        try:
            _render_all(a, con)
            _render_all(b, con)
        finally:
            con.close()
        for f in a.rglob("index.html"):
            rel = f.relative_to(a)
            self.assertEqual(f.read_bytes(), (b / rel).read_bytes(),
                             f"非決定性：{rel} 兩次不一致")


# ---------- phase0 歸屬權清理 ----------

class Phase0OwnershipTests(unittest.TestCase):
    def test_phase0_no_gen_driver(self):
        self.assertFalse(hasattr(p0, "gen_driver"),
                         "phase0 不應再有 gen_driver（/drivers/** 歸 gen-racing-drivers）")

    def test_phase0_source_has_no_driver_write(self):
        src = (ROOT / "scripts" / "gen-racing-entities-phase0.py").read_text(encoding="utf-8")
        self.assertNotIn('write_page(["drivers"', src)

    def test_phase0_has_no_page_owner_main(self):
        self.assertFalse(hasattr(p0, "main"), "phase0 只保留常數與元件，不應再是頁面 owner")


# ---------- 全站死連結掃描 = 0 ----------

class NoDeadLinkTests(unittest.TestCase):
    """車手頁對 seasons／constructors 的深連結都有對應生成檔（跨 owner，資料驅動 gate）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        # 渲染整站三 owner（同一 pipeline 現實）：seasons（77 季 + 2002/2026 分站）、
        # constructors（新 owner 11 隊）、drivers（53）。
        orig = (rc.PUB, gs.PUB, p0.PUB, dr.PUB, cg.PUB)
        rc.PUB = gs.PUB = p0.PUB = dr.PUB = cg.PUB = cls.tmp
        try:
            built = set(range(gs.FIRST_YEAR, gs.LAST_YEAR + 1))
            urls = [gs.render_index(built)]
            for year in range(gs.LAST_YEAR, gs.FIRST_YEAR - 1, -1):
                gs._render_one_season(year, urls, {2002, 2026})
            con = fs.connect_db()
            try:
                cg.render_index(con)
                for cid in cg.CONSTRUCTOR_IDS:
                    cg.gen_constructor(cid, con)
                dr.render_index(con)
                for did in dr.DRIVER_IDS:
                    dr.gen_driver(did, con)
            finally:
                con.close()
        finally:
            rc.PUB, gs.PUB, p0.PUB, dr.PUB, cg.PUB = orig

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_driver_pages_have_no_dead_internal_links(self):
        dead = []
        for f in (self.tmp / "drivers").rglob("index.html"):
            html = f.read_text(encoding="utf-8")
            for href in re.findall(r'href="(/(?:seasons|constructors|drivers)/[^"]*)"', html):
                if not (self.tmp / href.strip("/") / "index.html").is_file():
                    dead.append((f.parent.name, href))
        self.assertEqual(dead, [], f"車手頁死連結：{dead[:10]}")

    def test_seed_timeline_links_subpage_nonseed_links_overview(self):
        ms = (self.tmp / "drivers" / "michael-schumacher" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/seasons/2002/drivers/michael-schumacher/"', ms)  # seed → 子頁
        fangio = (self.tmp / "drivers" / "fangio" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/seasons/1957/"', fangio)                          # 非 seed → 總覽
        self.assertNotIn('/seasons/1957/drivers/fangio/', fangio)

    def test_detail_rows_link_round_pages_where_available(self):
        ms = (self.tmp / "drivers" / "michael-schumacher" / "index.html").read_text(encoding="utf-8")
        self.assertRegex(ms, r'href="/seasons/2002/rounds/\d+/"')  # 2002 有分站頁 → 明細深連


if __name__ == "__main__":
    unittest.main()
