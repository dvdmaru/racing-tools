#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4-B 分站頁生成器回歸測試（gen-racing-seasons.py 的 /seasons/<year>/rounds/<n>/）。

範圍只做 2002（17 站）＋2026（已跑站，資料驅動非硬編）。鎖住驗收硬條件與踩過的錯：
- 分站頁站數＝有正賽 results 的站（資料驅動）：2002 恰 17、2026 恰為已跑站數。
- 完整名次表含<全部>參賽車手（2002 R01 應 22 車），positionText 原樣（R/D/W…）。
- 退賽判定用 positionText（is_classified）而非 status：2026 'Lapped' 同時套在完賽名次者與
  真退賽者身上，唯 positionText 誠實區分——完賽名次的落圈車手不得被列為退賽。
- 敘事層存在且每個數字對得上明細（grid/圈數/積分＝冠軍列；未完賽數＝退賽名單筆數；
  最大宗 status＝退賽名單分佈）。
- 退賽區與「本站無退賽」誠實分支。
- 上／下一站邊界：頭站無上一站、尾站無下一站，禁死連結。
- sprint 區塊只在有 sprint 資料的站出現（2026 R2 有、2002 全季無、2026 R1 無檔）。
- JSON-LD 單一 SportsEvent 含 startDate＋location Place＋geo（賽道經緯度）＋sameAs 維基。
- 交叉連結雙向：總覽「各站冠軍」／車手子頁／車隊子頁的站次連往分站頁（同 gate，無死連結）。
- 決定性：同一頁跑兩次 byte-identical。

跑法：python3 -m unittest discover -s tests -v
"""
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


def _count_result_files(year):
    return len(list((g.RAW / "results").glob(f"{year}-*.json")))


class RoundScopeTests(unittest.TestCase):
    """分站頁範圍＝有正賽 results 的站（資料驅動，非硬編 10）。"""

    def test_2002_has_seventeen_rounds(self):
        self.assertEqual(g.season_round_numbers(2002), list(range(1, 18)))
        self.assertEqual(len(g.season_round_numbers(2002)), _count_result_files(2002))

    def test_2026_round_count_is_data_driven(self):
        rounds = g.season_round_numbers(2026)
        # 不硬編 10：以實際 results 檔數為準（隨每週資料更新自動增加）
        self.assertEqual(len(rounds), _count_result_files(2026))
        self.assertEqual(rounds, list(range(1, len(rounds) + 1)))

    def test_round_page_paths_match_round_numbers(self):
        paths = g.round_page_paths(2002)
        self.assertEqual(len(paths), 17)
        self.assertIn("seasons/2002/rounds/1", paths)
        self.assertIn("seasons/2002/rounds/17", paths)
        self.assertNotIn("seasons/2002/rounds/18", paths)


class FullResultsTableTests(unittest.TestCase):
    """完整名次表：全部參賽車手（2002 R01 應 22 車）、positionText 原樣。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.orig = (rc.PUB, g.PUB)
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", self.orig[0]), setattr(g, "PUB", self.orig[1])))
        g.render_round(2002, 1)
        self.html = (self.tmp / "seasons" / "2002" / "rounds" / "1" / "index.html").read_text(encoding="utf-8")

    def test_all_22_participants_present(self):
        results = g.round_full_results(2002, 1)
        self.assertEqual(len(results), 22, "2002 R01 應 22 車")
        rows = re.findall(r'<td class="rk">[^<]*</td>', self.html)
        self.assertEqual(len(rows), 22, "完整名次表列數須等於全部參賽車手")
        # 每位車手（含墊底/退賽者）都在頁上
        for res in results:
            self.assertIn(res["Driver"]["familyName"], self.html)

    def test_position_text_verbatim(self):
        # 2002 R01（大車禍）有 R（退賽）名次——positionText 原樣呈現
        pts = {(r.get("positionText") or r.get("position")) for r in g.round_full_results(2002, 1)}
        self.assertIn("R", pts)
        self.assertIn('<td class="rk">R</td>', self.html)


class RetirementClassificationTests(unittest.TestCase):
    """退賽判定用 positionText（is_classified），不用 status——2026 'Lapped' 陷阱。"""

    def test_is_classified_uses_position_text(self):
        self.assertTrue(g.is_classified({"positionText": "7", "status": "Lapped"}))
        self.assertTrue(g.is_classified({"positionText": "1", "status": "Finished"}))
        self.assertFalse(g.is_classified({"positionText": "R", "status": "Lapped"}))
        self.assertFalse(g.is_classified({"positionText": "W", "status": "Did not start"}))

    def test_2026_lapped_classified_not_in_retirements(self):
        rets = g.round_retirements(2026, 1)
        ret_ids = {d["driver_id"] for d in rets}
        # Bearman（P7, Lapped, 完賽名次）不得被列為退賽
        self.assertNotIn("bearman", ret_ids)
        # Stroll（positionText R, status Lapped, 僅 43 圈）＝真退賽，必在名單
        self.assertIn("stroll", ret_ids)
        # 全部退賽者 positionText 皆非數字
        for r in g.round_full_results(2026, 1):
            pt = r.get("positionText") or r.get("position")
            in_ret = r["Driver"]["driverId"] in ret_ids
            self.assertEqual(in_ret, not str(pt).isdigit())

    def test_cross_frame_note_on_retirement_list(self):
        # 口徑說明：分站頁（positionText）與總覽退賽圖鑑（status）算法不同，頁上必須明講
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig_rc, orig_g = rc.PUB, g.PUB
        rc.PUB = g.PUB = tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig_rc), setattr(g, "PUB", orig_g)))
        # 2002 R03 有「status 故障但獲完賽名次」案例（Räikkönen P12 Wheel rim）——口徑差異實際存在的站
        g.render_round(2002, 3)
        html = (tmp / "seasons" / "2002" / "rounds" / "3" / "index.html").read_text(encoding="utf-8")
        self.assertIn("口徑說明", html)
        self.assertIn("兩者口徑不同", html)

    def test_no_retirement_honest_branch(self):
        # 合成全員完賽（全部 positionText 數字）→ 誠實「本站無退賽」分支
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = (rc.PUB, g.PUB, g.round_full_results)
        rc.PUB = g.PUB = tmp

        def all_finished(year, rnd):
            out = [dict(r) for r in orig[2](year, rnd)]
            for i, r in enumerate(out):
                out[i] = {**r, "positionText": str(i + 1)}
            return out
        g.round_full_results = all_finished
        self.addCleanup(lambda: (setattr(rc, "PUB", orig[0]), setattr(g, "PUB", orig[1]),
                                 setattr(g, "round_full_results", orig[2])))
        g.render_round(2002, 2)
        html = (tmp / "seasons" / "2002" / "rounds" / "2" / "index.html").read_text(encoding="utf-8")
        self.assertIn("無退賽", html)
        self.assertEqual(g.round_retirements(2002, 2), [])


class NarrativeTests(unittest.TestCase):
    """敘事層：至少三句，每個數字對得上頁面明細。"""

    def test_narrative_min_three_lines(self):
        self.assertGreaterEqual(len(g.round_narrative(2002, 1)), 3)
        self.assertGreaterEqual(len(g.round_narrative(2026, 2)), 3)

    def test_numbers_match_detail(self):
        year, rnd = 2026, 1
        results = g.round_full_results(year, rnd)
        joined = "".join(g.round_narrative(year, rnd))
        winner = next(r for r in results if (r.get("positionText") or r.get("position")) == "1")
        # 冠軍發車位、圈數、積分都在敘事且在明細（冠軍列）
        self.assertIn(f'從第 {winner["grid"]} 位發車', joined)
        self.assertIn(f'完成 {winner["laps"]} 圈', joined)
        self.assertIn(f'進帳 {winner["points"]} 分', joined)
        # 未完賽數 == 退賽名單筆數
        rets = g.round_retirements(year, rnd)
        self.assertIn(f'{len(rets)} 位未完賽', joined)
        # 參賽總數 == 完整名次表列數
        self.assertIn(f'共 {len(results)} 位車手參賽', joined)

    def test_top_status_count_equals_bucket(self):
        year, rnd = 2026, 2
        rets = g.round_retirements(year, rnd)
        from collections import Counter
        cnt = Counter(d["status"] for d in rets)
        top_status, top_n = max(cnt.items(), key=lambda kv: (kv[1], kv[0]))
        joined = "".join(g.round_narrative(year, rnd))
        self.assertIn(f'「{g.name_plain(g.STATUS_ZH.get(top_status), top_status)}」者 {top_n} 位', joined)

    def test_every_round_page_has_narrative(self):
        # thin-content guard：每個分站頁都要有敘事段落
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = (rc.PUB, g.PUB)
        rc.PUB = g.PUB = tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig[0]), setattr(g, "PUB", orig[1])))
        for rnd in g.season_round_numbers(2026):
            g.render_round(2026, rnd)
            html = (tmp / "seasons" / "2026" / "rounds" / str(rnd) / "index.html").read_text(encoding="utf-8")
            self.assertIn('class="narrative"', html)


class PodiumTests(unittest.TestCase):
    def test_podium_top_three(self):
        pod = g.round_podium(2002, 1)
        self.assertEqual(len(pod), 3)
        self.assertEqual(pod[0]["positionText"], "1")
        self.assertEqual(pod[1]["positionText"], "2")
        self.assertEqual(pod[2]["positionText"], "3")

    def test_podium_block_rendered(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = (rc.PUB, g.PUB)
        rc.PUB = g.PUB = tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig[0]), setattr(g, "PUB", orig[1])))
        g.render_round(2002, 1)
        html = (tmp / "seasons" / "2002" / "rounds" / "1" / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="podium"', html)
        self.assertIn("冠軍", html)
        self.assertIn("亞軍", html)
        self.assertIn("季軍", html)


class SprintBlockTests(unittest.TestCase):
    """sprint 區塊只在有 sprint 資料的站出現。"""

    def _render(self, year, rnd):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = (rc.PUB, g.PUB)
        rc.PUB = g.PUB = tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig[0]), setattr(g, "PUB", orig[1])))
        g.render_round(year, rnd)
        return (tmp / "seasons" / str(year) / "rounds" / str(rnd) / "index.html").read_text(encoding="utf-8")

    def test_2026_r2_has_sprint(self):
        self.assertTrue(g.round_sprint(2026, 2))
        self.assertIn("衝刺賽", self._render(2026, 2))

    def test_2026_r1_no_sprint_file_no_block(self):
        self.assertFalse(g.round_sprint(2026, 1))
        self.assertNotIn("衝刺賽", self._render(2026, 1))

    def test_2002_no_sprint_all_season(self):
        for rnd in g.season_round_numbers(2002):
            self.assertFalse(g.round_sprint(2002, rnd), f"2002 R{rnd} 不應有 sprint")
        self.assertNotIn("衝刺賽", self._render(2002, 5))


class RoundNavBoundaryTests(unittest.TestCase):
    """上／下一站：頭站無上一站、尾站無下一站，中間站雙向；禁死連結。"""

    def _render(self, year, rnd):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = (rc.PUB, g.PUB)
        rc.PUB = g.PUB = tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig[0]), setattr(g, "PUB", orig[1])))
        g.render_round(year, rnd)
        return (tmp / "seasons" / str(year) / "rounds" / str(rnd) / "index.html").read_text(encoding="utf-8")

    def test_first_round_no_prev(self):
        html = self._render(2026, 1)
        self.assertNotIn("/seasons/2026/rounds/0/", html)
        self.assertIn('class="rn-x rn-prev"', html)   # 上一站佔位空格
        self.assertIn("/seasons/2026/rounds/2/", html)  # 有下一站

    def test_last_ran_round_no_next(self):
        # 2026 已跑到 R10：R10 沒有下一站（R11 尚未跑、無頁）
        last = g.season_round_numbers(2026)[-1]
        html = self._render(2026, last)
        self.assertNotIn(f"/seasons/2026/rounds/{last + 1}/", html)
        self.assertIn('class="rn-x rn-next"', html)
        self.assertIn(f"/seasons/2026/rounds/{last - 1}/", html)  # 有上一站

    def test_middle_round_both(self):
        html = self._render(2002, 9)
        self.assertIn("/seasons/2002/rounds/8/", html)
        self.assertIn("/seasons/2002/rounds/10/", html)


class JsonLdTests(unittest.TestCase):
    """JSON-LD：BreadcrumbList ＋ 單一 SportsEvent（startDate＋Place＋geo＋sameAs）。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        orig = (rc.PUB, g.PUB)
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig[0]), setattr(g, "PUB", orig[1])))
        g.render_round(2002, 1)
        self.html = (self.tmp / "seasons" / "2002" / "rounds" / "1" / "index.html").read_text(encoding="utf-8")

    def test_single_sportsevent_with_geo(self):
        self.assertEqual(self.html.count('"@type":"SportsEvent"'), 1)
        self.assertIn('"@type":"Place"', self.html)
        self.assertIn('"@type":"GeoCoordinates"', self.html)
        self.assertIn('"startDate":"2002-03-03"', self.html)
        self.assertIn('"@type":"BreadcrumbList"', self.html)

    def test_sameas_wikipedia_only(self):
        # sameAs 放維基（誠實 fallback）；外連 host 僅白名單
        self.assertIn("en.wikipedia.org", self.html)
        hosts = set(re.findall(r"https?://([a-zA-Z0-9.-]+)", self.html))
        allowed = {
            "fonts.googleapis.com", "fonts.gstatic.com", "www.googletagmanager.com",
            "schema.org", "en.wikipedia.org",
            "racing.twtools.cc", "twtools.cc", "aire.twtools.cc", "tree.twtools.cc",
            "foootball.twtools.cc", "baseball.twtools.cc", "dvdmaru.com",
        }
        self.assertFalse(hosts - allowed, f"白名單外 host：{hosts - allowed}")


class NoScriptTests(unittest.TestCase):
    """零 client JS：除 page_shell 白名單（theme/GA/JSON-LD）外無 script、無 fetch。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        orig = (rc.PUB, g.PUB)
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig[0]), setattr(g, "PUB", orig[1])))
        g.render_round(2026, 2)
        self.html = (self.tmp / "seasons" / "2026" / "rounds" / "2" / "index.html").read_text(encoding="utf-8")

    def test_no_client_fetch(self):
        for banned in ("fetch(", "XMLHttpRequest", "WebSocket", ".ajax"):
            self.assertNotIn(banned, self.html)

    def test_only_whitelisted_scripts(self):
        for b in re.findall(r"<script[^>]*>.*?</script>", self.html, re.S):
            ok = ('application/ld+json' in b or 'googletagmanager.com/gtag' in b
                  or 'gtag(' in b or 'rc-theme' in b or 'setTheme' in b or 'THEMES' in b)
            self.assertTrue(ok, f"非白名單 script：{b[:80]}")


class CrossLinkTests(unittest.TestCase):
    """交叉連結雙向：總覽各站冠軍／車手子頁／車隊子頁的站次連往分站頁（同 gate）。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        orig = (rc.PUB, g.PUB)
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig[0]), setattr(g, "PUB", orig[1])))
        self.rpaths = g.round_page_paths(2002)

    def test_overview_links_rounds_when_scoped(self):
        g.render_season(2002, self.rpaths)
        html = (self.tmp / "seasons" / "2002" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/seasons/2002/rounds/1/"', html)
        self.assertIn('href="/seasons/2002/rounds/17/"', html)

    def test_overview_no_round_links_when_unscoped(self):
        # 未給 round_paths（該季不在 rounds-for 範圍）→ 各站冠軍表無分站頁連結
        g.render_season(2002)
        html = (self.tmp / "seasons" / "2002" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('href="/seasons/2002/rounds/', html)

    def test_driver_subpage_links_rounds(self):
        g.render_driver_subpage(2002, "michael_schumacher", self.rpaths)
        html = (self.tmp / "seasons" / "2002" / "drivers" / "michael-schumacher"
                / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/seasons/2002/rounds/1/"', html)

    def test_team_subpage_links_rounds(self):
        g.render_team_subpage(2002, "ferrari", self.rpaths)
        html = (self.tmp / "seasons" / "2002" / "teams" / "ferrari"
                / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/seasons/2002/rounds/1/"', html)

    def test_round_page_links_back_to_subpage_and_overview(self):
        # 分站頁完整名次表：有子頁的車手／車隊連往該季子頁（同 gate）＋回連總覽
        g.render_round(2002, 1, self.rpaths, g.subpage_paths(2002))
        html = (self.tmp / "seasons" / "2002" / "rounds" / "1" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/seasons/2002/drivers/michael-schumacher/"', html)  # 舒馬克有子頁
        self.assertIn('href="/seasons/2002/teams/ferrari/"', html)
        self.assertIn('href="https://racing.twtools.cc/seasons/2002/"', html)   # 回連總覽


class DeterminismAndDeadLinkTests(unittest.TestCase):
    """決定性（兩次 byte-identical）＋全站含分站頁死連結掃描=0（2002＋2026 full pipeline 子集）。"""

    def test_round_page_deterministic(self):
        def render():
            tmp = pathlib.Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, tmp)
            orig = (rc.PUB, g.PUB)
            rc.PUB = g.PUB = tmp
            try:
                g.render_round(2026, 2)
                return (tmp / "seasons" / "2026" / "rounds" / "2" / "index.html").read_bytes()
            finally:
                rc.PUB, g.PUB = orig
        self.assertEqual(render(), render())

    def test_no_dead_links_with_round_pages(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        orig = (rc.PUB, g.PUB)
        rc.PUB = g.PUB = tmp
        try:
            built = set(range(g.FIRST_YEAR, g.LAST_YEAR + 1))
            urls = [g.render_index(built)]
            for year in (2002, 2026):
                g._render_one_season(year, urls, {2002, 2026})
        finally:
            rc.PUB, g.PUB = orig
        dead = []
        for f in tmp.glob("seasons/2002/**/index.html"):
            for href in re.findall(r'href="(/seasons/2002/[^"]*)"', f.read_text(encoding="utf-8")):
                if not (tmp / href.strip("/") / "index.html").is_file():
                    dead.append((str(f), href))
        for f in tmp.glob("seasons/2026/**/index.html"):
            for href in re.findall(r'href="(/seasons/2026/[^"]*)"', f.read_text(encoding="utf-8")):
                if not (tmp / href.strip("/") / "index.html").is_file():
                    dead.append((str(f), href))
        self.assertEqual(dead, [], f"死連結：{dead[:10]}")


class RoundCliTests(unittest.TestCase):
    """CLI --rounds-for：生成分站頁；--publish 時分站頁 URL 進 sitemap part。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        orig = (rc.PUB, g.PUB)
        rc.PUB = g.PUB = self.tmp
        self.addCleanup(lambda: (setattr(rc, "PUB", orig[0]), setattr(g, "PUB", orig[1])))
        self.calls = []
        self.orig_ws = rc.write_sitemap_part
        rc.write_sitemap_part = lambda owner, urls: self.calls.append((owner, urls))
        self.addCleanup(lambda: setattr(rc, "write_sitemap_part", self.orig_ws))

    def _run(self, argv):
        import sys
        old = sys.argv
        sys.argv = ["gen-racing-seasons.py"] + argv
        try:
            g.main()
        finally:
            sys.argv = old

    def test_rounds_for_generates_pages(self):
        self._run(["--season", "2002", "--rounds-for", "2002"])
        for rnd in (1, 9, 17):
            self.assertTrue((self.tmp / "seasons" / "2002" / "rounds" / str(rnd) / "index.html").is_file())

    def test_publish_includes_round_urls_in_sitemap(self):
        self._run(["--season", "2002", "--rounds-for", "2002", "--publish"])
        self.assertEqual(len(self.calls), 1)
        urls = self.calls[0][1]
        self.assertIn(f"{rc.BASE}/seasons/2002/rounds/1/", urls)
        self.assertIn(f"{rc.BASE}/seasons/2002/rounds/17/", urls)

    def test_default_no_round_pages(self):
        self._run(["--season", "2002"])
        self.assertFalse((self.tmp / "seasons" / "2002" / "rounds").exists())


if __name__ == "__main__":
    unittest.main()
