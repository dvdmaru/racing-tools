#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M5 車手頁生成器回歸測試（gen-racing-drivers.py）。

鎖住驗收條件與紅線：
- 前置三 gate（invariants／verdicts／golden）各自的 exit-1 行為：合成壞 invariant／抽走一條
  verdict／篡改 golden 一值 → gate False（且 main 走 gate 失敗時零產出）。
- 35 頁全生成 + 索引完整（含 ItemList 35）。
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

ALLOWED_HOSTS = {
    "fonts.googleapis.com", "fonts.gstatic.com", "www.googletagmanager.com",
    "schema.org", "en.wikipedia.org",
    "racing.twtools.cc", "twtools.cc", "aire.twtools.cc", "tree.twtools.cc",
    "foootball.twtools.cc", "baseball.twtools.cc", "dvdmaru.com",
}
FORBIDDEN_LABELS = ("桿位", "最快圈", "生涯積分")
ALLOWED_STAT_LABELS = ("世界冠軍", "分站冠軍", "頒獎台", "參賽場次")


def _render_all(tmp, con=None):
    """把索引 + 35 車手頁渲染進 tmp，回傳 {slug: html}。"""
    own = con is None
    con = con or fs.connect_db()
    orig = dr.PUB
    dr.PUB = tmp
    try:
        dr.render_index(con)
        out = {}
        for did in dr.CHAMPION_IDS:
            s = dr.gen_driver(did, con)
            out[s["slug"]] = (tmp / "drivers" / s["slug"] / "index.html").read_text(encoding="utf-8")
        return out
    finally:
        dr.PUB = orig
        if own:
            con.close()


# ---------- gate exit-1 行為 ----------

class GatePassTests(unittest.TestCase):
    """現況三 gate 全綠（回歸：任何一 gate 退化會在這裡先炸）。"""

    def test_invariants_gate_passes(self):
        self.assertTrue(dr.gate_invariants())

    def test_verdicts_gate_passes(self):
        self.assertTrue(dr.gate_verdicts())

    def test_golden_gate_passes(self):
        self.assertTrue(dr.gate_golden())

    def test_run_gates_all_green(self):
        self.assertTrue(dr.run_gates())


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
        for did in dr.CHAMPION_IDS:
            car = fs.driver_career_db(did, self.con)
            champ = fs.driver_championships_db(did, self.con)
            for key, stat in (("wins", car["wins"]), ("podiums", car["podiums"]),
                              ("entries", car["entries"]), ("championships", champ)):
                self.assertEqual(stat["value"], len(stat["detail"]),
                                 f"{did} {key} value 與明細筆數不符")
                self.assertEqual(stat["value"], self.golden[did][key],
                                 f"{did} {key} 與 golden 不符")
            self.assertEqual([d["season"] for d in champ["detail"]],
                             self.golden[did]["championship_years"])

    def test_golden_covers_exactly_35(self):
        self.assertEqual(set(self.golden), set(dr.CHAMPION_IDS))
        self.assertEqual(len(self.golden), 35)


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

    def test_all_35_driver_pages_generated(self):
        self.assertEqual(len(self.pages), 35)
        for did in dr.CHAMPION_IDS:
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
        self.assertEqual(self.index.count('"@type":"ListItem"'), 37)

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
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.pages = _render_all(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_untranslated_driver_is_original_only(self):
        # ascari 無 approved 譯名 → 中文欄位整個不出現、只留原文 + 頁尾註明
        self.assertIsNone(dr.resolve_zh("ascari"))
        h = self.pages["ascari"]
        self.assertIn('<span class="en-only">Alberto Ascari</span>', h)
        self.assertIn("尚無定版繁中譯名", h)

    def test_seed_driver_has_approved_fullname(self):
        h = self.pages["hamilton"]
        self.assertIn("路易斯・韓密爾頓", h)
        self.assertNotIn("尚無定版繁中譯名", h)

    def test_no_self_translation_for_unknown(self):
        # fallback 不得憑空生一個中文名（title 用原文）
        h = self.pages["ascari"]
        self.assertIn("<title>Alberto Ascari生涯數據", h)


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

    def test_phase0_main_generates_no_driver_pages(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = p0.PUB
        p0.PUB = tmp
        try:
            p0.main()
        finally:
            p0.PUB = orig
        self.assertFalse((tmp / "drivers").exists(), "phase0 不應再產 /drivers/")
        self.assertTrue((tmp / "constructors").exists(), "phase0 仍應產 /constructors/")


# ---------- 全站死連結掃描 = 0 ----------

class NoDeadLinkTests(unittest.TestCase):
    """車手頁對 seasons／constructors 的深連結都有對應生成檔（跨 owner，資料驅動 gate）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        # 渲染整站三 owner（同一 pipeline 現實）：seasons（77 季 + 2002/2026 分站）、
        # constructors（phase0 4 seed）、drivers（35）。
        orig = (rc.PUB, gs.PUB, p0.PUB, dr.PUB)
        rc.PUB = gs.PUB = p0.PUB = dr.PUB = cls.tmp
        try:
            built = set(range(gs.FIRST_YEAR, gs.LAST_YEAR + 1))
            urls = [gs.render_index(built)]
            for year in range(gs.LAST_YEAR, gs.FIRST_YEAR - 1, -1):
                gs._render_one_season(year, urls, {2002, 2026})
            p0.main()
            con = fs.connect_db()
            try:
                dr.render_index(con)
                for did in dr.CHAMPION_IDS:
                    dr.gen_driver(did, con)
            finally:
                con.close()
        finally:
            rc.PUB, gs.PUB, p0.PUB, dr.PUB = orig

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
