#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""/constructors/ 接進重生管線的回歸測試（缺口 ③）。

背景：4 個車隊頁由 gen-racing-entities-phase0.py 生成，但 regen-encyclopedia.py 只列舉
seasons 與 drivers ——後果是①指紋機制看不到車隊頁（永遠不會被選擇性重生）②不進 sitemap
③沒有 /constructors/index.html，是「有內頁、沒入口」的孤兒區。本檔鎖住修好之後的行為。

頁面歸屬權不變（M3 v3）：/constructors/** 仍由 phase0 生成，regen 只負責「何時呼叫」與
「URL 進不進 sitemap」。所以這裡同時驗兩件事：phase0 真的產得出索引頁，且 regen 真的會叫它。

鎖住：
- /constructors/index.html 存在，連到全部 4 個車隊頁，且每條站內連結都有對應生成檔（無死連結）。
- 4 個車隊頁本身的站內深連結也無死連結（跨 owner：連到 /seasons/**）。
- 指紋：constructors 進 compute_fingerprints；資料沒變 → 零重生零重寫；車隊冠軍資料變 →
  只有那一隊 + 索引重生。
- 指紋切片刻意不含進行中賽季的即時積分：注入一筆當季賽果不得讓車隊頁被重寫（否則每週白刷）。
- 舊指紋檔沒有 constructors 鍵（本功能之前留下的）→ 視為沒指紋、全部重生（default-deny），
  不可被誤判成「沒變動所以跳過」。
- sitemap part 檔名＝constructors.txt（比照既有 articles/calendar/results/standings 慣例），
  且 --publish 才寫（未公開前不讓 URL 進 sitemap）。
- 索引頁只宣稱「本站目前整理過的車隊」，不可宣稱是完整車隊列表（站定位＝整理站，殘缺要標註）。

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import pathlib
import re
import shutil
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 一律借 regen 的模組圖（各生成器內部自己 importlib 載入；自己再載一份會 patch 不到 PUB）
re_mod = _load("regen_encyclopedia", "regen-encyclopedia.py")
rc, fs, gs, dr, p0 = re_mod.rc, re_mod.fs, re_mod.gs, re_mod.dr, re_mod.p0


def _con(db):
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    return c


def _graph(html):
    """取出頁面 JSON-LD 的 @graph 節點清單（compact JSON，不能用字串比對驗）。"""
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))["@graph"] if m else []


def _node(html, typ):
    return next((n for n in _graph(html) if n.get("@type") == typ), None)


# ---------- 1. 索引頁存在、連得完整、無死連結 ----------

class ConstructorsIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls._orig = (rc.PUB, p0.PUB)
        rc.PUB = p0.PUB = cls.tmp
        try:
            p0.main()
        finally:
            rc.PUB, p0.PUB = cls._orig
        cls.index = cls.tmp / "constructors" / "index.html"
        cls.html = cls.index.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_index_file_written(self):
        self.assertTrue(self.index.is_file(), "/constructors/index.html 必須存在（否則是孤兒區）")

    def test_index_links_every_constructor_page_and_none_is_dead(self):
        hrefs = set(re.findall(r'href="(/constructors/[^"]+)"', self.html))
        want = {f"/constructors/{rc.constructor_slug(c)}/" for c in p0.CONSTRUCTORS}
        self.assertEqual(want - hrefs, set(), f"索引沒連到：{want - hrefs}")
        for h in hrefs:
            self.assertTrue((self.tmp / h.strip("/") / "index.html").is_file(),
                            f"索引死連結：{h}")

    def test_canonical_and_breadcrumb_point_at_index(self):
        self.assertIn(f'<link rel="canonical" href="{rc.BASE}/constructors/">', self.html)
        # 車隊頁的麵包屑要經過 /constructors/（沒有索引頁之前它從首頁直接跳到該隊，中間那層是斷的）
        ferrari = (self.tmp / "constructors" / "ferrari" / "index.html").read_text(encoding="utf-8")
        crumbs = _node(ferrari, "BreadcrumbList")["itemListElement"]
        self.assertEqual([c["item"] for c in crumbs],
                         [f"{rc.BASE}/", f"{rc.BASE}/constructors/",
                          f"{rc.BASE}/constructors/ferrari/"])

    def test_itemlist_covers_all_constructors(self):
        lst = _node(self.html, "ItemList")
        self.assertIsNotNone(lst, "索引頁要有 ItemList JSON-LD（比照 /drivers/ 索引）")
        self.assertEqual(lst["numberOfItems"], len(p0.CONSTRUCTORS))
        urls = [i["url"] for i in lst["itemListElement"]]
        self.assertEqual(sorted(urls),
                         sorted(f"{rc.BASE}/constructors/{rc.constructor_slug(c)}/"
                                for c in p0.CONSTRUCTORS))

    def test_index_does_not_claim_to_be_a_complete_list(self):
        """站定位＝整理站不是百科：只能說「本站整理過的」，不可暗示是完整車隊列表。"""
        self.assertIn("不是完整的車隊列表", self.html)
        for lie in ("歷代所有車隊", "完整車隊名錄", "全部車隊"):
            self.assertNotIn(lie, self.html, f"索引頁不得宣稱涵蓋全部車隊：{lie}")

    def test_one_h1_and_no_level_skip(self):
        self.assertEqual(len(re.findall(r"<h1[ >]", self.html)), 1)
        # 沒有 h2 的頁面不得直接出現 h3（跳級）
        if not re.search(r"<h2[ >]", self.html):
            self.assertEqual(re.findall(r"<h3[ >]", self.html), [])

    def test_no_unapproved_self_translation_of_team_names(self):
        """譯名只走已核准來源；4 隊都有 phase0 已核准全名，必須中英並列（全形空格分隔）。"""
        for cid in p0.CONSTRUCTORS:
            zh = p0.ZH[cid]
            self.assertIn(zh, self.html, f"{cid} 的已核准譯名沒出現在索引")
        self.assertIn('<span class="zh-en">　', self.html, "中英對照要用全形空格分隔")


# ---------- 2. 全站死連結（含 /constructors/ 與 4 個車隊頁） ----------

class ConstructorsNoDeadLinkTests(unittest.TestCase):
    """整站三 owner 都建起來，掃 /constructors/ 全區的站內連結（跨 owner，資料驅動 gate）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        orig = (rc.PUB, gs.PUB, p0.PUB, dr.PUB)
        rc.PUB = gs.PUB = p0.PUB = dr.PUB = cls.tmp
        try:
            built = set(range(gs.FIRST_YEAR, gs.LAST_YEAR + 1))
            urls = [gs.render_index(built)]
            for year in range(gs.LAST_YEAR, gs.FIRST_YEAR - 1, -1):
                gs._render_one_season(year, urls, set(rc.ROUND_YEARS))
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

    def test_constructors_area_has_no_dead_internal_links(self):
        dead = []
        for f in (self.tmp / "constructors").rglob("index.html"):
            html = f.read_text(encoding="utf-8")
            for href in re.findall(r'href="(/(?:seasons|constructors|drivers)[^"#?]*)"', html):
                if not (self.tmp / href.strip("/") / "index.html").is_file():
                    dead.append((str(f.relative_to(self.tmp)), href))
        self.assertEqual(dead, [], f"/constructors/ 區死連結：{dead[:10]}")

    def test_other_pages_linking_to_constructors_still_resolve(self):
        """既有 27 個頁面連向 /constructors/<slug>/——接線後這些連結一條都不能斷。"""
        linkers, dead = set(), []
        for f in self.tmp.rglob("index.html"):
            html = f.read_text(encoding="utf-8")
            hrefs = re.findall(r'href="(/constructors/[^"#?]*)"', html)
            if hrefs:
                linkers.add(str(f.relative_to(self.tmp)))
            for href in hrefs:
                if not (self.tmp / href.strip("/") / "index.html").is_file():
                    dead.append((str(f.relative_to(self.tmp)), href))
        self.assertEqual(dead, [], f"連向車隊頁的死連結：{dead[:10]}")
        self.assertGreaterEqual(len(linkers), 20, "應有為數不少的頁面連向車隊頁")


# ---------- 3. 指紋 / 選擇性重生 ----------

class ConstructorFingerprintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.fp = self.tmp / "fp.json"
        self.pub = self.tmp / "pub"
        self._orig = (gs.PUB, dr.PUB, rc.PUB, p0.PUB)
        gs.PUB = dr.PUB = rc.PUB = p0.PUB = self.pub
        self.addCleanup(self._restore)
        self.db = self.tmp / "db.sqlite"
        shutil.copy(fs.DB, self.db)

    def _restore(self):
        gs.PUB, dr.PUB, rc.PUB, p0.PUB = self._orig

    def _regen(self, db=None, **kw):
        con = _con(db or self.db)
        try:
            return re_mod.selective_regen(con, fp_path=self.fp, **kw)
        finally:
            con.close()

    def _snapshot(self):
        return {p: (p.stat().st_mtime_ns, p.read_bytes())
                for p in (self.pub / "constructors").rglob("index.html")}

    def test_fingerprints_include_constructors(self):
        con = _con(self.db)
        try:
            fp = re_mod.compute_fingerprints(con)
        finally:
            con.close()
        self.assertEqual(set(fp["constructors"]), set(re_mod.CONSTRUCTOR_IDS))
        self.assertIn("constructors", fp["indices"])

    def test_full_build_creates_index_and_all_pages(self):
        res = self._regen(full=True)
        self.assertEqual(res["changed_constructors"], list(re_mod.CONSTRUCTOR_IDS))
        self.assertTrue(res["index_constructors"])
        self.assertTrue((self.pub / "constructors" / "index.html").is_file())
        for cid in re_mod.CONSTRUCTOR_IDS:
            self.assertTrue((self.pub / "constructors" / rc.constructor_slug(cid)
                             / "index.html").is_file())
        self.assertIn(f"{rc.BASE}/constructors/", res["changed_urls"])

    def test_no_data_change_zero_rewrite(self):
        self._regen(full=True)
        snap = self._snapshot()
        res = self._regen()
        self.assertEqual(res["changed_constructors"], [])
        self.assertFalse(res["index_constructors"])
        stale = [str(p) for p, (m, _) in snap.items() if p.stat().st_mtime_ns != m]
        self.assertEqual(stale, [], f"資料沒變不得重寫車隊頁：{stale}")

    def test_championship_change_regenerates_only_that_constructor(self):
        self._regen(full=True)
        snap = self._snapshot()
        db2 = self.tmp / "db2.sqlite"
        shutil.copy(self.db, db2)
        con = sqlite3.connect(str(db2))
        # 把 mclaren 某個非冠軍季改成第 1（＝多一座車隊冠軍）
        con.execute("UPDATE constructor_standings SET position=1 "
                    "WHERE constructor_id='mclaren' AND season=1997")
        con.commit()
        con.close()
        res = self._regen(db=db2)
        self.assertEqual(res["changed_constructors"], ["mclaren"])
        self.assertTrue(res["index_constructors"])
        rewritten = {p.parent.name for p, (m, _) in snap.items() if p.stat().st_mtime_ns != m}
        self.assertEqual(rewritten, {"mclaren", "constructors"},
                         f"只能重寫 mclaren 與索引，實際：{rewritten}")

    def test_in_progress_season_points_do_not_churn_constructor_pages(self):
        """指紋切片刻意排除進行中賽季的即時積分：每週新賽果不得讓車隊頁被白刷一次。"""
        self._regen(full=True)
        snap = self._snapshot()
        db2 = self.tmp / "db3.sqlite"
        shutil.copy(self.db, db2)
        con = sqlite3.connect(str(db2))
        year = con.execute("SELECT year FROM seasons WHERE status='in_progress' "
                           "ORDER BY year DESC").fetchone()
        if not year:
            self.skipTest("目前沒有進行中賽季")
        con.execute("UPDATE constructor_standings SET points=points+25 WHERE season=?", (year[0],))
        con.commit()
        con.close()
        res = self._regen(db=db2)
        self.assertEqual(res["changed_constructors"], [])
        stale = [str(p) for p, (m, _) in snap.items() if p.stat().st_mtime_ns != m]
        self.assertEqual(stale, [], f"進行中賽季積分變動不得重寫車隊頁：{stale}")

    def test_legacy_fingerprint_file_without_constructors_key_regenerates_all(self):
        """本功能之前留下的指紋檔沒有 constructors 鍵 → 必須視為「沒指紋」全部重生。"""
        self._regen(full=True)
        legacy = json.loads(self.fp.read_text(encoding="utf-8"))
        legacy.pop("constructors")
        legacy["indices"].pop("constructors")
        self.fp.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        res = self._regen()
        self.assertEqual(res["changed_constructors"], list(re_mod.CONSTRUCTOR_IDS))
        self.assertTrue(res["index_constructors"])
        # 賽季/車手不受波及（缺鍵只影響缺的那一群）
        self.assertEqual(res["changed_years"], [])
        self.assertEqual(res["changed_drivers"], [])


# ---------- 4. sitemap part ----------

class ConstructorsSitemapPartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self._orig_root = rc.ROOT
        rc.ROOT = self.tmp
        self.addCleanup(setattr, rc, "ROOT", self._orig_root)

    def test_part_name_follows_existing_convention(self):
        """既有 part 檔＝<owner>.txt（articles/calendar/results/standings）；車隊照 constructors.txt。"""
        rc.write_sitemap_part("constructors", re_mod.enumerate_constructor_urls())
        p = self.tmp / "data" / "sitemap-parts" / "constructors.txt"
        self.assertTrue(p.is_file())
        urls = p.read_text(encoding="utf-8").splitlines()
        self.assertEqual(urls[0], f"{rc.BASE}/constructors/", "索引 URL 要排第一（比照 drivers）")
        self.assertEqual(len(urls), len(re_mod.CONSTRUCTOR_IDS) + 1)

    def test_enumerate_is_complete_and_deterministic(self):
        a = re_mod.enumerate_constructor_urls()
        b = re_mod.enumerate_constructor_urls()
        self.assertEqual(a, b, "URL 列舉必須決定性（進 sitemap 的東西不能跑序敏感）")
        self.assertEqual(len(set(a)), len(a), "不得有重複 URL")


# ---------- 5. 決定性 ----------

class ConstructorsDeterminismTests(unittest.TestCase):
    def test_two_runs_byte_identical(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = (rc.PUB, p0.PUB)
        outs = []
        try:
            for i in (1, 2):
                d = tmp / f"run{i}"
                rc.PUB = p0.PUB = d
                p0.main()
                outs.append({str(p.relative_to(d)): p.read_bytes()
                             for p in d.rglob("index.html")})
        finally:
            rc.PUB, p0.PUB = orig
        self.assertEqual(outs[0], outs[1], "兩次生成必須 byte-identical")


if __name__ == "__main__":
    unittest.main()
