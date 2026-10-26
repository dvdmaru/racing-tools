#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-10-27 站台補強回歸測試：跑序、資料頁實體互鏈、賽曆訂閱（.ics）、標題。

由來（GSC／GA4 2026-07-28～10-25）：
- 「f1積分」12,128 次曝光有 8,723 次派給首頁 → 首頁標題不再以「積分榜」開頭。
- 積分榜 15,301 次曝光卻沒有一條實體連結 → 表格裡的車手／車隊名點得進百科頁。
- 賽曆是第一名落地頁、互動率 33% → 頁首下一站倒數＋全季 .ics 訂閱。
- 百科段排在 build-articles 之後 → 新一站的互鏈與 llms.txt 永遠慢一週（PR #128 實測）。

跑法：python3 -m unittest discover -s tests -v
"""
import datetime
import importlib.util
import json
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


rc = _load("racinglib_hardening", "racinglib.py")
cal = _load("gen_racing_calendar_hardening", "gen-racing-calendar.py")


# ---------- 跑序：百科段必須在 build-articles 與週更三頁之前 ----------

class PipelineOrderTests(unittest.TestCase):
    def setUp(self):
        src = (ROOT / "scripts" / "update-racing.py").read_text(encoding="utf-8")
        # 只看 main() 的呼叫點：docstring 與註解裡也會出現這些名字
        self.main = src[src.index("\ndef main("):]

    def test_encyclopedia_before_build_articles_and_gens(self):
        i_enc = self.main.index("encyclopedia_step(full=")
        for call in ('script("build-articles.py")', 'script("gen-racing-standings.py"',
                     'script("gen-racing-calendar.py"', 'script("gen-racing-results.py"'):
            self.assertLess(i_enc, self.main.index(call),
                            f"百科段必須在 {call} 之前——後者讀百科落地的 sitemap part 決定有頁才連")

    def test_build_sitemap_still_after_everything(self):
        i_sitemap = self.main.index('script("build-sitemap.py")')
        for call in ("encyclopedia_step(full=", 'script("build-articles.py")',
                     'script("gen-racing-results.py"'):
            self.assertLess(self.main.index(call), i_sitemap, call)


# ---------- 資料頁實體互鏈：有頁才連 ----------

class EntityLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.orig_override = rc.SITEMAP_PARTS_OVERRIDE
        self.orig_published = rc.ENCYCLOPEDIA_PUBLISHED
        self.orig_slugs = rc._SLUGS
        self.addCleanup(setattr, rc, "SITEMAP_PARTS_OVERRIDE", self.orig_override)
        self.addCleanup(setattr, rc, "ENCYCLOPEDIA_PUBLISHED", self.orig_published)
        self.addCleanup(setattr, rc, "_SLUGS", self.orig_slugs)
        rc.SITEMAP_PARTS_OVERRIDE = self.tmp
        rc.ENCYCLOPEDIA_PUBLISHED = True
        rc._SLUGS = {"drivers": {"antonelli": "antonelli", "tsunoda": "yuki-tsunoda"},
                     "constructors": {"mercedes": "mercedes"}}
        (self.tmp / "drivers.txt").write_text(
            f"{rc.BASE}/drivers/\n{rc.BASE}/drivers/antonelli/\n", encoding="utf-8")
        (self.tmp / "constructors.txt").write_text(
            f"{rc.BASE}/constructors/mercedes/\n", encoding="utf-8")

    def test_page_in_part_is_linked(self):
        self.assertEqual(rc.entity_href("drivers", "antonelli"), "/drivers/antonelli/")
        self.assertEqual(rc.entity_href("constructors", "mercedes"), "/constructors/mercedes/")
        html = rc.entity_link("安東內利", "drivers", "antonelli")
        self.assertEqual(html, '<a class="ent" href="/drivers/antonelli/">安東內利</a>')

    def test_registered_slug_without_page_is_not_linked(self):
        """反向：slug 已註冊≠頁面已生成。只信 sitemap part，否則就是死連結。"""
        self.assertEqual(rc.entity_href("drivers", "tsunoda"), "")
        self.assertEqual(rc.entity_link("Tsunoda", "drivers", "tsunoda"), "Tsunoda")

    def test_unregistered_or_empty_id_is_not_linked(self):
        self.assertEqual(rc.entity_href("drivers", "nobody"), "")
        self.assertEqual(rc.entity_href("drivers", ""), "")
        self.assertEqual(rc.entity_href("circuits", "monza"), "")

    def test_unpublished_encyclopedia_links_nothing(self):
        rc.ENCYCLOPEDIA_PUBLISHED = False
        self.assertEqual(rc.entity_href("drivers", "antonelli"), "")

    def test_missing_part_links_nothing(self):
        (self.tmp / "drivers.txt").unlink()
        self.assertEqual(rc.entity_href("drivers", "antonelli"), "")


class GeneratedPagesLinkTests(unittest.TestCase):
    """產物層：committed 的資料頁表格裡每條實體連結都必須指向 sitemap part 裡的頁（零死連結）。"""

    PAGES = ("standings/index.html", "results/index.html", "calendar/index.html", "index.html")

    def test_every_entity_link_resolves(self):
        if not rc.ENCYCLOPEDIA_PUBLISHED:
            self.skipTest("百科未公開")
        known = set(rc.read_sitemap_part("drivers")) | set(rc.read_sitemap_part("constructors"))
        for page in self.PAGES:
            p = rc.PUB / page
            if not p.exists():
                continue
            hrefs = re.findall(r'class="ent" href="([^"]+)"', p.read_text(encoding="utf-8"))
            self.assertTrue(hrefs, f"{page} 沒有任何實體連結")
            dead = sorted({h for h in hrefs if f"{rc.BASE}{h}" not in known})
            self.assertEqual(dead, [], f"{page} 有死連結")


# ---------- 賽曆訂閱（.ics） ----------

def _race(rnd, date, time, sprint=False):
    r = {"season": "2026", "round": str(rnd), "raceName": "Mexico City Grand Prix",
         "Circuit": {"circuitId": "rodriguez", "circuitName": "Autódromo Hermanos Rodríguez",
                     "Location": {"locality": "Mexico City", "country": "Mexico"}},
         "date": date, "time": time,
         "FirstPractice": {"date": "2026-10-30", "time": "18:30:00Z"},
         "Qualifying": {"date": "2026-10-31", "time": "21:00:00Z"}}
    if sprint:
        r["Sprint"] = {"date": "2026-10-31", "time": "17:00:00Z"}
    return r


class IcsTests(unittest.TestCase):
    def setUp(self):
        self.races = [_race(19, "2026-11-01", "20:00:00Z", sprint=True)]
        self.ics = cal.build_ics(2026, self.races)

    def test_crlf_and_line_length(self):
        raw = self.ics.encode("utf-8")
        self.assertTrue(raw.startswith(b"BEGIN:VCALENDAR\r\n"))
        self.assertTrue(raw.endswith(b"END:VCALENDAR\r\n"))
        self.assertEqual(raw.replace(b"\r\n", b"").count(b"\n"), 0, "不得有裸 LF")
        for line in raw.split(b"\r\n"):
            self.assertLessEqual(len(line), 75, line)
            line.decode("utf-8")  # 折行不得切斷多位元組字元

    def test_one_event_per_session_in_utc(self):
        unfolded = self.ics.replace("\r\n ", "")
        self.assertEqual(unfolded.count("BEGIN:VEVENT"), 4)  # FP1、衝刺賽、排位、正賽
        self.assertIn("UID:2026-r19-race@racing.twtools.cc", unfolded)
        self.assertIn("DTSTART:20261101T200000Z", unfolded)
        self.assertIn("DTEND:20261101T220000Z", unfolded)
        # 台北時間寫在描述：UTC 11/1 20:00 ＝ 台北 11/2（一）04:00
        self.assertIn("台北時間 11/2（一）04:00", unfolded)

    def test_deterministic(self):
        """verify-deploy 比對整檔 byte：同一份資料 build 兩次必須一字不差（DTSTAMP 不得用現在時刻）。"""
        self.assertEqual(self.ics, cal.build_ics(2026, self.races))
        self.assertIn("DTSTAMP:20260101T000000Z", self.ics)

    def test_text_escaping(self):
        self.assertEqual(cal._ics_escape("a,b;c\\d\ne"), "a\\,b\\;c\\\\d\\ne")

    def test_session_without_time_is_skipped(self):
        race = _race(19, "2026-11-01", "20:00:00Z")
        race["Qualifying"] = {"date": "2026-10-31"}
        keys = [k for k, *_ in cal.race_sessions(race)]
        self.assertEqual(keys, ["FirstPractice", "Race"])


class NextRaceTests(unittest.TestCase):
    def test_next_race_skips_finished_and_past(self):
        races = [_race(18, "2026-10-25", "20:00:00Z"), _race(19, "2026-11-01", "20:00:00Z")]
        today = datetime.date(2026, 10, 27)
        self.assertEqual(cal.next_race(races, {}, today)["round"], "19")
        self.assertEqual(cal.next_race(races, {19: {"Results": []}}, today), None)

    def test_next_block_carries_sessions_for_client_countdown(self):
        html = cal.next_race_html(_race(19, "2026-11-01", "20:00:00Z"))
        m = re.search(r'data-sessions="([^"]+)"', html)
        sessions = json.loads(m.group(1).replace("&quot;", '"'))
        self.assertEqual(sessions[-1], {"n": "正賽", "t": "2026-11-01T20:00:00Z", "m": 120})
        self.assertIn("11/2（一）04:00", html)  # 沒有 JS 也看得到台北時間
        self.assertEqual(cal.next_race_html(None), "")

    def test_subscribe_links(self):
        html = cal.subscribe_html(2026)
        self.assertIn('href="webcal://racing.twtools.cc/calendar/f1-2026-taipei.ics"', html)
        self.assertIn("cid=webcal%3A%2F%2Fracing.twtools.cc%2Fcalendar%2Ff1-2026-taipei.ics", html)
        self.assertIn('href="/calendar/f1-2026-taipei.ics" download', html)


# ---------- 分站敘事：grid＝0 不推定成維修道起跑 ----------

class GridZeroNarrativeTests(unittest.TestCase):
    """0 在資料源文件裡沒有定義（站內 f1-101-grid-data-reading 明寫）；敘事只陳述欄位值。"""

    def _narrative(self, grid, laps="58"):
        gs = _load("gen_racing_seasons_hardening", "gen-racing-seasons.py")
        winner = {"position": "1", "positionText": "1", "grid": grid, "laps": laps, "points": "25",
                  "status": "Finished", "Driver": {"driverId": "x", "givenName": "Test", "familyName": "Driver"}}
        gs.round_full_results = lambda y, r: [winner]
        gs._round_results = lambda y, r: {"raceName": "Test Grand Prix"}
        gs.round_podium = lambda y, r: [winner, None, None]
        gs.round_retirements = lambda y, r: []
        return gs.round_narrative(2026, 1)[0]

    def test_grid_zero_states_field_value_only(self):
        line = self._narrative("0")
        self.assertNotIn("維修道", line)
        self.assertIn("完成 58 圈奪下分站冠軍", line)
        self.assertNotIn(" 、", line)
        self.assertIn("發車欄記為 0", line)

    def test_numeric_grid_unchanged(self):
        line = self._narrative("4")
        self.assertIn("從第 4 位發車、完成 58 圈奪下分站冠軍", line)
        self.assertNotIn("記為 0", line)


# ---------- 通用分享卡 ----------

class ShareCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.addCleanup(setattr, rc, "PUB", rc.PUB)
        rc.PUB = self.tmp

    def test_card_only_when_file_exists(self):
        self.assertEqual(rc.share_card_url("site"), "")
        self.assertEqual(rc.og_image_meta(""), "")
        (self.tmp / "share").mkdir()
        (self.tmp / "share" / "site.png").write_bytes(b"png")
        self.assertEqual(rc.share_card_url("site"), f"{rc.BASE}/share/site.png")
        self.assertEqual(rc.share_card_url("guide"), "")

    def test_page_shell_falls_back_to_site_card(self):
        (self.tmp / "share").mkdir()
        (self.tmp / "share" / "site.png").write_bytes(b"png")
        html = rc.page_shell("t", "d", f"{rc.BASE}/x/", "", "", "home")
        self.assertIn(f'<meta property="og:image" content="{rc.BASE}/share/site.png">', html)
        own = rc.page_shell("t", "d", f"{rc.BASE}/x/", "", "", "home", og_image="https://e/x.png")
        self.assertIn('content="https://e/x.png"', own)
        self.assertNotIn("share/site.png", own)

    def test_committed_cards_are_full_size_png(self):
        import struct
        for rel in rc.SHARE_CARDS.values():
            raw = (ROOT / "public-racing" / rel).read_bytes()
            self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n", rel)
            self.assertEqual(struct.unpack(">II", raw[16:24]), (2400, 1260), rel)


# ---------- 標題：首頁不跟積分榜頁搶「積分」 ----------

class TitleTests(unittest.TestCase):
    def test_home_title_does_not_lead_with_standings(self):
        site = json.loads((ROOT / "config" / "site.json").read_text(encoding="utf-8"))
        self.assertNotIn("積分", site["home_title"])

    def test_standings_title_carries_round(self):
        src = (ROOT / "scripts" / "gen-racing-standings.py").read_text(encoding="utf-8")
        self.assertIn("截至第 {rnd} 站", src)


if __name__ == "__main__":
    unittest.main()
