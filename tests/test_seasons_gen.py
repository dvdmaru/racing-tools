#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3 賽季頁生成器回歸測試（gen-racing-seasons.py）。

鎖住四條驗收條件與踩過的錯：
- 進行中賽季不顯示冠軍（把榜首當冠軍的錯）。
- 退賽明細 value == len(detail)（衍生數字紀律）。
- 分差 == 兩列 standings 積分之差（SOURCED − SOURCED）。
- 產出 HTML 除 page_shell 白名單（theme init / GA / JSON-LD）外零 script、零 client fetch；
  外連只限白名單 host（維基 sameAs 與 page_shell 資產）。
- 預設不寫 sitemap part；--publish 才寫。

跑法：python3 -m unittest discover -s tests -v
"""
import argparse
import importlib.util
import pathlib
import re
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


g = _load("gen_racing_seasons", "gen-racing-seasons.py")
rc = g.rc
fs = g.fs

# 外連白名單：JSON-LD 的維基 sameAs／schema.org context ＋ page_shell 既有資產（字型/GA/姊妹站/本站）
ALLOWED_HOSTS = {
    "fonts.googleapis.com", "fonts.gstatic.com", "www.googletagmanager.com",
    "schema.org", "en.wikipedia.org",
    "racing.twtools.cc", "twtools.cc", "aire.twtools.cc", "tree.twtools.cc",
    "foootball.twtools.cc", "baseball.twtools.cc", "dvdmaru.com",
}


class IndexInProgressTests(unittest.TestCase):
    """索引頁：進行中賽季不顯示冠軍。"""

    def test_completed_season_shows_champion(self):
        row = g.index_row(2002)
        self.assertFalse(row["in_progress"])
        self.assertIsNotNone(row["driver_champ"])
        self.assertEqual(row["driver_champ"]["id"], "michael_schumacher")
        self.assertIsNotNone(row["constructor_champ"])

    def test_real_in_progress_season_hides_champion(self):
        # 2026 進行中（fs._is_completed=False）——榜首是領先不是冠軍
        row = g.index_row(2026)
        self.assertTrue(row["in_progress"])
        self.assertIsNone(row["driver_champ"])
        self.assertIsNone(row["constructor_champ"])

    def test_in_progress_rounds_cell_shows_ran_over_scheduled(self):
        # T-01（查核桌）：進行中賽季「分站數」須呈現 已跑/全季，不得只給已跑站次
        row = g.index_row(2026)
        self.assertGreater(row["scheduled"], row["rounds"])  # 22 > 10
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig_rc, orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig_rc), setattr(g, "PUB", orig_g)))
        g.render_index()
        html = (tmp / "seasons" / "index.html").read_text(encoding="utf-8")
        self.assertIn(f'{row["rounds"]} / {row["scheduled"]}', html)

    def test_monkeypatched_incomplete_hides_champion(self):
        orig = fs._is_completed
        fs._is_completed = lambda y: False
        try:
            row = g.index_row(2002)  # 合成：即使有 2002 榜也不得吐冠軍
            self.assertTrue(row["in_progress"])
            self.assertIsNone(row["driver_champ"])
            self.assertIsNone(row["constructor_champ"])
        finally:
            fs._is_completed = orig

    def test_index_html_marks_in_progress_not_champion(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig_rc, orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig_rc), setattr(g, "PUB", orig_g)))
        g.render_index()
        html = (tmp / "seasons" / "index.html").read_text(encoding="utf-8")
        self.assertIn("進行中", html)  # 2026 那列
        # 2026 那列不得出現「奪冠」語意的積分冠軍名（榜首 antonelli 不得被當冠軍呈現於冠軍欄）
        self.assertNotRegex(html, r"2026[^<]*安東內利")


class RetirementDisciplineTests(unittest.TestCase):
    """退賽分布：value == len(detail)（衍生數字紀律）。"""

    def test_every_category_value_equals_len_detail(self):
        cats = g.season_retirements(2002)
        self.assertTrue(cats)
        for c in cats:
            self.assertEqual(c["value"], len(c["detail"]),
                             f"{c['status']} value 與明細筆數不符")

    def test_finisher_classification(self):
        self.assertTrue(g.is_finisher("Finished"))
        self.assertTrue(g.is_finisher("+1 Lap"))
        self.assertTrue(g.is_finisher("+3 Laps"))
        self.assertFalse(g.is_finisher("Engine"))
        self.assertFalse(g.is_finisher("Collision"))
        self.assertFalse(g.is_finisher("Disqualified"))

    def test_total_retirements_matches_independent_count(self):
        # 獨立重數：直接掃 raw results，非完賽者計數，應等於各類 value 加總
        import glob
        import json
        indep = 0
        for f in sorted(glob.glob(str(g.RAW / "results" / "2002-*.json"))):
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            for r in data.get("Results", []):
                if not g.is_finisher(r.get("status", "")):
                    indep += 1
        self.assertEqual(sum(c["value"] for c in g.season_retirements(2002)), indep)


class PointsGapTests(unittest.TestCase):
    """分差 == 兩列 standings 積分之差。"""

    def test_gap_equals_difference_of_two_standings(self):
        import json
        with open(g.RAW / "standings" / "driver-2002.json", encoding="utf-8") as fh:
            ds = json.load(fh)["DriverStandings"]
        champ = int(ds[0]["points"])
        second = int(ds[1]["points"])
        c, s, gap = g.points_gap(2002)
        self.assertEqual(c, champ)
        self.assertEqual(s, second)
        self.assertEqual(gap, champ - second)
        self.assertEqual(gap, c - s)  # 只做減法


class NarrativeTests(unittest.TestCase):
    """規則化敘事句：模板+資料，每個數字都能在頁面明細找到。"""

    def test_narrative_numbers_are_sourced(self):
        lines = g.season_narrative(2002)
        joined = "".join(lines)
        _, _, gap = g.points_gap(2002)
        total = sum(c["value"] for c in g.season_retirements(2002))
        self.assertIn("17 站", joined)          # 分站數
        self.assertIn(f"{gap} 分", joined)       # 分差
        self.assertIn(f"{total} 人次", joined)   # 退賽總數
        # 冠軍譯名走已核准來源（phase0）——不得只有原文
        self.assertIn("麥可・舒馬克", joined)

    def test_narrative_v2_constructor_breakdown_sentence(self):
        joined = "".join(g.season_narrative(2002))
        # 車隊句含 Σ 拆解（禁手寫，數字皆通過 gate）
        self.assertIn("144 分＋Rubens Barrichello 77 分", joined)
        self.assertIn("221 分拿下", joined)
        # 冠軍之爭補句：第二、第三名（名字照譯名紀律 fallback→原文）
        self.assertIn("積分榜第二名為 Rubens Barrichello（77 分）", joined)
        self.assertIn("第三名 Juan Pablo Montoya（50 分）", joined)


class ChampionshipRaceTests(unittest.TestCase):
    """冠軍之爭累計線：終點必等官方積分（自我 oracle 硬 gate）；對不上則整張不畫。"""

    def test_cumulative_endpoints_equal_official_points(self):
        leaders, ok = g.cumulative_leaders(2002)
        self.assertTrue(ok)
        self.assertEqual(len(leaders), 3)
        expected = {"michael_schumacher": 144, "barrichello": 77, "montoya": 50}
        for l in leaders:
            self.assertEqual(l["final"], expected[l["driver_id"]],
                             f"{l['driver_id']} 累計終點 {l['final']} != 官方 {expected[l['driver_id']]}")
            self.assertEqual(l["final"], l["official"])  # 終點==官方最終積分

    def test_chart_rendered_when_gate_passes(self):
        chart = g._championship_race_chart(2002)
        self.assertIn("<polyline", chart)
        self.assertIn("champ-chart", chart)
        self.assertIn("#d63a2f", chart)   # 冠軍紅粗線

    def test_dropped_scores_gate_hides_whole_chart(self):
        # 合成 dropped-scores：把榜首官方積分灌水，使逐站累計終點對不上 → 整張不畫、出誠實 note
        orig = g._driver_standings
        def fake(year):
            ds = [dict(x) for x in orig(year)]
            ds[0]["points"] = str(int(ds[0]["points"]) + 999)
            return ds
        g._driver_standings = fake
        try:
            leaders, ok = g.cumulative_leaders(2002)
            self.assertFalse(ok)  # 硬 gate 觸發
            chart = g._championship_race_chart(2002)
            self.assertNotIn("<polyline", chart)  # 整張不畫
            self.assertNotIn("<svg", chart)
            self.assertIn("best-N", chart)         # 誠實 note
            self.assertIn("不重建", chart)
        finally:
            g._driver_standings = orig


class ConstructorBreakdownTests(unittest.TestCase):
    """車隊拆解：Σ(各車手) == 官方車隊積分才顯示；對不上則不顯示拆解。"""

    def test_all_2002_constructors_sum_matches(self):
        b = g.constructor_breakdowns(2002)
        # 2002 全 11 隊皆應對得上
        for cid, info in b.items():
            self.assertTrue(info["ok"], f"{cid} Σ={info['sum']} != 官方{info['official']}")
        # 冠軍隊 Σ 明細
        self.assertEqual(b["ferrari"]["sum"], 221)
        parts = {p["driver_id"]: p["points"] for p in b["ferrari"]["parts"]}
        self.assertEqual(parts["michael_schumacher"], 144)
        self.assertEqual(parts["barrichello"], 77)
        self.assertEqual(144 + 77, 221)  # 144+77=221 gate

    def test_breakdown_shown_when_sum_matches(self):
        b = g.constructor_breakdowns(2002)
        html = g._std_constructor_table(g._constructor_standings(2002), b)
        # 11 隊全 ok → 11 條拆解列
        self.assertEqual(html.count('class="brk"'), 11)
        self.assertIn("144", html)
        self.assertIn("77", html)

    def test_breakdown_hidden_on_sum_mismatch(self):
        cs = g._constructor_standings(2002)
        b_all = g.constructor_breakdowns(2002)
        # 合成不等：把冠軍隊官方積分灌水，使 Σ 對不上 → 該隊不顯示拆解
        orig = g._constructor_standings
        def fake(year):
            out = [dict(x) for x in orig(year)]
            out[0] = {**out[0], "Constructor": out[0]["Constructor"],
                      "points": str(int(out[0]["points"]) + 500)}
            return out
        g._constructor_standings = fake
        try:
            b_broken = g.constructor_breakdowns(2002)
            self.assertFalse(b_broken["ferrari"]["ok"])
            html_broken = g._std_constructor_table(cs, b_broken)
            # 冠軍隊拆解被隱藏 → brk 列少一條（11 → 10）
            self.assertEqual(g._std_constructor_table(cs, b_all).count('class="brk"'), 11)
            self.assertEqual(html_broken.count('class="brk"'), 10)
        finally:
            g._constructor_standings = orig


class RetirementFramingTests(unittest.TestCase):
    """全季退賽圖鑑：節標題與副標明示統計全部車手（非僅冠軍）。"""

    def test_section_title_and_scope_note(self):
        cats = g.season_retirements(2002)
        html = g._retirement_chart(cats, 2002)
        self.assertIn("非僅冠軍", html)
        self.assertIn("2002 年", html)
        # N 位曾未完賽車手：從資料算，須為正整數且 <span> 呈現
        n = len({d["driver_id"] for c in cats for d in c["detail"]})
        self.assertGreater(n, 1)
        self.assertIn(f"全部 {n} 位", html)


class NoScriptNoFetchTests(unittest.TestCase):
    """零 client fetch／除白名單外零 script；外連只限白名單 host。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.orig_rc, self.orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", self.orig_rc), setattr(g, "PUB", self.orig_g)))
        g.render_season(2002)
        self.html = (self.tmp / "seasons" / "2002" / "index.html").read_text(encoding="utf-8")

    def test_no_client_fetch_apis(self):
        for banned in ("fetch(", "XMLHttpRequest", "WebSocket", ".ajax"):
            self.assertNotIn(banned, self.html, f"頁面出現 client fetch 特徵：{banned}")

    def test_only_whitelisted_scripts(self):
        blocks = re.findall(r"<script[^>]*>.*?</script>", self.html, re.S)
        self.assertTrue(blocks)
        for b in blocks:
            ok = ('application/ld+json' in b            # JSON-LD 資料
                  or 'googletagmanager.com/gtag' in b    # GA async（page_shell）
                  or 'gtag(' in b                        # GA config（page_shell）
                  or 'rc-theme' in b                     # theme 預載（防 FOUC）
                  or 'setTheme' in b or 'THEMES' in b)   # theme 切換器
            self.assertTrue(ok, f"非白名單 script：{b[:80]}")

    def test_tabs_are_css_only(self):
        # tabgroup 用 radio + :checked，無 JS；頁面應有 radio input 與 .tablabels
        self.assertIn('type="radio"', self.html)
        self.assertIn('tablabels', self.html)

    def test_external_hosts_whitelisted(self):
        hosts = set(re.findall(r"https?://([a-zA-Z0-9.-]+)", self.html))
        extra = hosts - ALLOWED_HOSTS
        self.assertFalse(extra, f"出現白名單外的外連 host：{extra}")

    def test_jsonld_has_sportsevent_with_place(self):
        # JSON-LD 型別選擇：每站一個 SportsEvent，含 Place（有座標才放 geo）
        self.assertIn('"@type":"SportsEvent"', self.html)
        self.assertIn('"@type":"Place"', self.html)
        self.assertIn('"@type":"GeoCoordinates"', self.html)  # 2002 schedule 有 lat/long


class OverviewFullFieldTests(unittest.TestCase):
    """v3 總覽＝中性：完整車手榜（全部車手，非前幾名）＋各站冠軍列表。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.orig_rc, self.orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", self.orig_rc), setattr(g, "PUB", self.orig_g)))
        g.render_season(2002)
        self.html = (self.tmp / "seasons" / "2002" / "index.html").read_text(encoding="utf-8")

    def test_full_driver_standings_has_all_drivers(self):
        ds = g._driver_standings(2002)
        self.assertGreaterEqual(len(ds), 20, "2002 應有 20+ 車手")
        # 每一位車手（含墊底者）都要出現在頁面上——不是只有前幾名
        for e in ds:
            fam = e["Driver"].get("familyName", "")
            self.assertIn(fam, self.html, f"完整車手榜缺 {fam}")

    def test_round_winners_section_present_and_complete(self):
        self.assertIn("各站冠軍", self.html)
        winners = g.round_winners(2002)
        self.assertEqual(len(winners), 17)  # 2002 全 17 站都有冠軍
        # 每站冠軍列（R01..R17）都在頁上
        for w in winners:
            self.assertIn(f'R{w["round"]:02d}', self.html)

    def test_overview_is_neutral_labeled(self):
        self.assertIn("中性總覽", self.html)

    def test_hero_champion_chips_link_to_season_subpages(self):
        # 選擇即 URL：2002 頁 hero 點冠軍名，進的是「他的 2002」子頁，不是生涯頁
        hero = self.html.split('class="ident"')[1].split("</div>")[0]
        self.assertIn('/seasons/2002/drivers/michael-schumacher/', hero)
        self.assertIn('/seasons/2002/teams/ferrari/', hero)


class SubpageScopeTests(unittest.TestCase):
    """子頁生成範圍：只為『有實體頁（phase0 seed）且該季有參賽』者生成。"""

    def test_2002_subpage_entities_are_data_driven(self):
        dids, cids = g.season_subpage_entities(2002)
        # 車手：只有舒馬克（其餘 seed 車手 2002 未參賽）
        self.assertIn("michael_schumacher", dids)
        for absent in ("hamilton", "senna", "max_verstappen"):
            self.assertNotIn(absent, dids, f"{absent} 2002 未參賽，不應生成子頁")
        # 車隊：法拉利＋麥拉倫（賓士/紅牛 2002 不存在）
        self.assertIn("ferrari", cids)
        self.assertIn("mclaren", cids)
        for absent in ("mercedes", "red_bull"):
            self.assertNotIn(absent, cids, f"{absent} 2002 不存在，不應生成子頁")

    def test_subpage_paths_match_entities(self):
        paths = g.subpage_paths(2002)
        self.assertIn("seasons/2002/drivers/michael-schumacher", paths)
        self.assertIn("seasons/2002/teams/ferrari", paths)
        self.assertIn("seasons/2002/teams/mclaren", paths)
        # 未參賽者不得有子頁路徑
        self.assertNotIn("seasons/2002/drivers/hamilton", paths)


class NoDeadLinkTests(unittest.TestCase):
    """總覽頁上所有 /seasons/2002/(drivers|teams)/ 連結都有對應生成檔（無死連結）。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.orig_rc, self.orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", self.orig_rc), setattr(g, "PUB", self.orig_g)))
        # 產出總覽 + 全部子頁
        g.render_season(2002)
        for did in g.season_subpage_entities(2002)[0]:
            g.render_driver_subpage(2002, did)
        for cid in g.season_subpage_entities(2002)[1]:
            g.render_team_subpage(2002, cid)
        self.html = (self.tmp / "seasons" / "2002" / "index.html").read_text(encoding="utf-8")

    def test_every_subpage_link_has_a_generated_file(self):
        links = set(re.findall(r'href="(/seasons/2002/(?:drivers|teams)/[a-z0-9-]+/)"', self.html))
        self.assertTrue(links, "總覽頁應至少有一個子頁連結")
        for l in links:
            f = self.tmp / l.strip("/") / "index.html"
            self.assertTrue(f.is_file(), f"死連結：{l} 無對應生成檔")

    def test_non_subpage_drivers_are_plain_text_not_links(self):
        # 沒有子頁的車手（如 Barrichello）不得出現指向其子頁的連結
        self.assertNotIn('href="/seasons/2002/drivers/barrichello/"', self.html)


class DriverSubpageTests(unittest.TestCase):
    """車手子頁：17 站逐站表、麵包屑、回連總覽＋實體頁、季末卡數字 SOURCED（value==len detail）。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.orig_rc, self.orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", self.orig_rc), setattr(g, "PUB", self.orig_g)))
        g.render_driver_subpage(2002, "michael_schumacher")
        self.html = (self.tmp / "seasons" / "2002" / "drivers"
                     / "michael-schumacher" / "index.html").read_text(encoding="utf-8")

    def test_seventeen_round_table(self):
        races = g.driver_season_races(2002, "michael_schumacher")
        self.assertEqual(len(races), 17)
        rows = re.findall(r'<td class="rk mono">R\d\d</td>', self.html)
        self.assertEqual(len(rows), 17)

    def test_breadcrumb_and_backlinks(self):
        self.assertIn('class="crumbs"', self.html)
        self.assertIn('href="https://racing.twtools.cc/seasons/2002/"', self.html)  # 回總覽
        self.assertIn('href="https://racing.twtools.cc/drivers/michael-schumacher/"', self.html)  # 實體頁

    def test_season_card_wins_equal_detail_count(self):
        card = g.driver_season_card(2002, "michael_schumacher")
        # value == len(detail)：wins/podiums/entries 皆由明細筆數產生
        self.assertEqual(len(card["wins"]), 11)
        self.assertEqual(len(card["podiums"]), 17)  # 2002 MS 站站頒獎台
        self.assertEqual(len(card["entries"]), 17)
        # 官方 wins 欄與明細筆數一致（自我 oracle）
        self.assertEqual(int(card["official_wins"]), len(card["wins"]))

    def test_no_retirement_honest_note(self):
        # MS 2002 全季完賽 → 誠實顯示無退賽
        self.assertEqual(g.driver_retirements(2002, "michael_schumacher"), [])
        self.assertIn("無退賽紀錄", self.html)

    def test_unique_title(self):
        self.assertIn("<title>麥可・舒馬克（Michael Schumacher）｜2002 賽季成績", self.html)


class TeamSubpageTests(unittest.TestCase):
    """車隊子頁：Σ gate（過→顯示拆解；不過→隱藏＋誠實註記）、逐站積分對帳、退賽。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.orig_rc, self.orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", self.orig_rc), setattr(g, "PUB", self.orig_g)))

    def _render(self, cid="ferrari"):
        g.render_team_subpage(2002, cid)
        slug = rc.constructor_slug(cid)
        return (self.tmp / "seasons" / "2002" / "teams" / slug / "index.html").read_text(encoding="utf-8")

    def test_ferrari_sigma_gate_shows_breakdown(self):
        html = self._render("ferrari")
        self.assertIn("Σ 合計", html)
        self.assertIn("221", html)      # 官方車隊積分
        self.assertIn("144", html)      # 舒馬克貢獻
        self.assertIn("77", html)       # 巴里切羅貢獻

    def test_round_points_sum_equals_official(self):
        rounds = g.team_round_points(2002, "ferrari")
        official = int([r for r in g._constructor_standings(2002)
                        if r["Constructor"]["constructorId"] == "ferrari"][0]["points"])
        self.assertEqual(sum(r["points"] for r in rounds), official)

    def test_sigma_gate_hidden_on_mismatch(self):
        # 合成 Σ 對不上：灌水官方車隊積分 → 拆解段隱藏 + 誠實註記
        orig = g._constructor_standings
        def fake(year):
            out = [dict(x) for x in orig(year)]
            for i, r in enumerate(out):
                if r["Constructor"]["constructorId"] == "ferrari":
                    out[i] = {**r, "points": str(int(r["points"]) + 500)}
            return out
        g._constructor_standings = fake
        try:
            html = self._render("ferrari")
            self.assertNotIn("Σ 合計", html)         # 拆解段整段隱藏
            self.assertIn("不顯示", html)             # 誠實註記
        finally:
            g._constructor_standings = orig

    def test_team_retirements_sourced(self):
        rets = g.team_retirements(2002, "mclaren")
        # 每筆都帶來源檔與 status 原文
        for d in rets:
            self.assertTrue(d["source"].endswith(".json"))
            self.assertFalse(g.is_finisher(d["status"]))


class Phase0SeasonOwnershipTests(unittest.TestCase):
    """頁面歸屬權清理：phase0 不再生成 season 頁；實體頁連結指向子頁。"""

    @classmethod
    def setUpClass(cls):
        cls.p0 = _load("gen_racing_entities_phase0", "gen-racing-entities-phase0.py")

    def test_phase0_no_longer_generates_season_pages(self):
        self.assertFalse(hasattr(self.p0, "gen_season"),
                         "phase0 不應再有 gen_season（/seasons/** 歸 seasons 生成器所有）")

    def test_phase0_source_has_no_season_write(self):
        src = (ROOT / "scripts" / "gen-racing-entities-phase0.py").read_text(encoding="utf-8")
        # 不得再有寫 seasons 頁的 write_page(["seasons", ...]) 呼叫
        self.assertNotIn('write_page(["seasons"', src)

    def test_ms_entity_page_links_to_driver_subpage(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = self.p0.PUB
        self.p0.PUB = tmp
        self.addCleanup(lambda: setattr(self.p0, "PUB", orig))
        self.p0.gen_driver("michael_schumacher")
        html = (tmp / "drivers" / "michael-schumacher" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/seasons/2002/drivers/michael-schumacher/"', html)

    def test_ferrari_entity_page_links_to_team_subpage(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = self.p0.PUB
        self.p0.PUB = tmp
        self.addCleanup(lambda: setattr(self.p0, "PUB", orig))
        self.p0.gen_constructor("ferrari")
        html = (tmp / "constructors" / "ferrari" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/seasons/2002/teams/ferrari/"', html)


class SitemapGatingTests(unittest.TestCase):
    """M3 預設不寫 sitemap part；--publish 才寫。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.orig_rc, self.orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", self.orig_rc), setattr(g, "PUB", self.orig_g)))
        self.calls = []
        self.orig_ws = rc.write_sitemap_part
        rc.write_sitemap_part = lambda owner, urls: self.calls.append((owner, urls))
        self.addCleanup(lambda: setattr(rc, "write_sitemap_part", self.orig_ws))

    def _run(self, argv):
        orig = argparse.ArgumentParser.parse_args
        import sys
        old = sys.argv
        sys.argv = ["gen-racing-seasons.py"] + argv
        try:
            g.main()
        finally:
            sys.argv = old
            argparse.ArgumentParser.parse_args = orig

    def test_default_does_not_write_sitemap(self):
        self._run(["--index-only"])
        self.assertEqual(self.calls, [])

    def test_publish_writes_sitemap(self):
        self._run(["--index-only", "--publish"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], "seasons")

    def test_no_sitemap_flag_forces_off_even_with_publish(self):
        self._run(["--index-only", "--publish", "--no-sitemap"])
        self.assertEqual(self.calls, [])

    def test_publish_part_includes_all_three_page_types(self):
        # --publish（非 index-only）：總覽索引＋賽季總覽＋車手子頁＋車隊子頁全進 part
        self._run(["--season", "2002", "--publish"])
        self.assertEqual(len(self.calls), 1)
        urls = self.calls[0][1]
        self.assertIn(f"{rc.BASE}/seasons/2002/", urls)
        self.assertIn(f"{rc.BASE}/seasons/2002/drivers/michael-schumacher/", urls)
        self.assertIn(f"{rc.BASE}/seasons/2002/teams/ferrari/", urls)
        self.assertIn(f"{rc.BASE}/seasons/2002/teams/mclaren/", urls)


if __name__ == "__main__":
    unittest.main()
