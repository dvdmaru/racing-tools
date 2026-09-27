"""〈安東內利逐站封王算術〉的數字對帳（巴庫站後版，2026-09-27）。

facts/analysis-antonelli-clinch-arithmetic.json 的 derived_values 是指揮位腳本（閉式公式）的產出；
本檔用**另一套實作**（逐站模擬，不用封閉式）從同一份 own_data 重算一次並逐格比對。
兩套實作各自寫成，不共用程式碼：其中一套有算術錯，這裡就會紅。

⚠️ 它驗的是「表內數字彼此一致、且與 own_data 一致」；own_data 本身是否等於 jolpica／F1 官網，
是產稿當天（2026-09-27，R15 落地後）另外對過的（23 位車手逐人與積分榜一致、前 8 名對 F1 官網），本檔不重打網路。
2026-09-21 舊版（第 1–14 站、領先差 81）已由本版取代。
"""
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACK = ROOT / "facts" / "analysis-antonelli-clinch-arithmetic.json"
ARTICLE = ROOT / "articles" / "f1-2026-antonelli-clinch-arithmetic" / "index.md"

GP2 = 18      # 正賽第 2 名
SPR2 = 7      # 衝刺賽第 2 名


def load():
    return json.loads(PACK.read_text(encoding="utf-8"))


class Model:
    """逐站模擬版。cal＝[(round, is_sprint)]，lead0＝現況領先差。"""

    def __init__(self, cal, lead0):
        self.cal = list(cal)
        self.lead0 = lead0

    @staticmethod
    def win(sp):
        return 25 + (8 if sp else 0)

    @staticmethod
    def second(sp):
        return GP2 + (SPR2 if sp else 0)

    def left_after(self, idx):
        return sum(self.win(sp) for _, sp in self.cal[idx + 1:])

    def rows(self):
        out = []
        run_best = self.lead0
        run_second = 0
        for i, (rnd, sp) in enumerate(self.cal):
            run_best += self.win(sp)               # 安東內利全勝、羅素零分
            run_second += self.second(sp)          # 羅素每場第 2 的累計
            line = self.left_after(i) + 1
            can = run_best >= line
            # 安東內利全勝時，羅素從第一個未賽站到這一站合計最多可拿：
            # 領先差 = lead0 + 安東全勝累計 - 羅素累計 >= line
            gained = run_best - self.lead0
            allow = gained - (line - self.lead0)
            out.append(dict(rnd=rnd, M=line - 1, T=line, need=max(line - self.lead0, 0), lead_max=run_best,
                            feasible=can, allow_raw=allow if can else None, russell_cap=run_second,
                            binding=bool(can and allow < run_second)))
        return out

    def path(self, ant, rus):
        """ant/rus 是 (is_sprint)->得分 的函式；回傳（封王站, 季末領先差）。"""
        lead, first = self.lead0, None
        for i, (rnd, sp) in enumerate(self.cal):
            lead += ant(sp) - rus(sp)
            if first is None and lead > self.left_after(i):
                first = rnd
        return first, lead


class ClinchArithmeticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load()
        cls.dv = cls.pack["derived_values"]
        cal = [(c["round"], c["sprint_weekend"]) for c in cls.pack["own_data"]["remaining_calendar"]]
        cls.cal8 = cal
        tot = cls.pack["own_data"]["standings_after_r15"]
        cls.lead0 = tot["antonelli"] - tot["russell"]
        cls.m8 = Model(cal, cls.lead0)

    # ── own_data 自洽 ──
    def test_weekend_points_sum_to_standings(self):
        wp = self.pack["own_data"]["weekend_points"]
        tot = self.pack["own_data"]["standings_after_r15"]
        self.assertEqual(sum(w["ant"] for w in wp.values()), tot["antonelli"])
        self.assertEqual(sum(w["rus"] for w in wp.values()), tot["russell"])
        self.assertEqual(sum(w["ham"] for w in wp.values()), tot["hamilton"])
        self.assertEqual(len(wp), 15)

    def test_lead_and_remaining_points(self):
        self.assertEqual(self.dv["lead_after_r15"], self.lead0)
        self.assertEqual(self.lead0, 66)
        self.assertEqual([r for r, _ in self.cal8], list(range(16, 24)))
        self.assertEqual(sum(Model.win(sp) for _, sp in self.cal8), 208)
        self.assertEqual(sum(1 for _, sp in self.cal8 if sp), 1)

    # ── 主表 ──
    def test_main_table_matches_independent_model(self):
        mine = self.m8.rows()
        theirs = self.dv["main_table"]
        self.assertEqual(len(mine), len(theirs))
        for a, b in zip(mine, theirs):
            self.assertEqual(a["rnd"], b["rnd"])
            for k in ("M", "T", "need", "lead_max", "feasible", "russell_cap", "binding"):
                self.assertEqual(a[k], b[k], f"第 {a['rnd']} 站 {k}")
            self.assertEqual(a["allow_raw"], b["allow_raw"], f"第 {a['rnd']} 站 allow_raw")

    def test_earliest_feasible_round_per_calendar(self):
        # 照舊 8 站、22 站：最早是第 18 站（美國）；兩站都不跑的 21 站：最早是第 17 站（新加坡）。
        want = {8: 18, 7: 18, 6: 17}
        for name, c in self.dv["calendars"].items():
            n = c["n"]
            m = Model(self.cal8[:n], self.lead0)
            rows = m.rows()
            first = next(r for r in rows if r["feasible"])
            self.assertEqual(first["rnd"], want[n], name)
            self.assertEqual(c["earliest"], want[n], name)
            prev = [r for r in rows if not r["feasible"]][-1]
            self.assertEqual(c["short_by"], prev["T"] - prev["lead_max"], name)
            self.assertEqual(c["short_round"], prev["rnd"], name)
            self.assertEqual(c["earliest_need"], first["need"], name)
            self.assertEqual(c["earliest_allow"], first["allow_raw"], name)
            self.assertEqual(c["earliest_cap"], first["russell_cap"], name)
            self.assertEqual(c["earliest_binding"], first["binding"], name)

    def test_headline_numbers(self):
        r = {x["rnd"]: x for x in self.m8.rows()}
        # 新加坡不再可能：安東內利雪邦、新加坡全勝，領先差最多 124，封王線 151（差 27）
        self.assertFalse(r[16]["feasible"])
        self.assertFalse(r[17]["feasible"])
        self.assertEqual((r[17]["lead_max"], r[17]["T"]), (124, 151))
        # 美國站：三個週末要淨賺 60，羅素合計上限 23（比他每場第 2 的累計 61 小）
        self.assertEqual((r[18]["need"], r[18]["allow_raw"], r[18]["russell_cap"]), (60, 23, 61))
        self.assertTrue(r[18]["binding"])
        self.assertEqual((r[19]["allow_raw"], r[19]["russell_cap"]), (73, 79))
        self.assertTrue(r[19]["binding"])
        # 第 20 站起「不受限」：算術上限大於羅素每場第 2 的累計
        for k in range(20, 24):
            self.assertFalse(r[k]["binding"], k)
        self.assertEqual([r[k]["russell_cap"] for k in range(20, 24)], [97, 115, 133, 151])
        # 第 21 站起現有 66 分領先本身就大過剩餘可得分
        self.assertEqual([r[k]["need"] for k in range(21, 24)], [0, 0, 0])
        self.assertEqual(r[20]["need"], 10)

    # ── 三條路徑 ──
    def test_three_paths(self):
        a = self.m8.path(Model.win, Model.second)      # 安東全勝、羅素每場第 2
        b = self.m8.path(Model.second, Model.win)      # 羅素全勝、安東每場第 2
        self.assertEqual(a, (20, 123))
        self.assertEqual(b, (23, 9))
        # 丙：領先固定 66，第一個 66 > 剩餘可得分 的站
        cflat = next(rnd for i, (rnd, _) in enumerate(self.cal8) if self.lead0 > self.m8.left_after(i))
        self.assertEqual(cflat, 21)
        sc = self.dv["scenarios_main"]
        self.assertEqual(sc["甲 安東全勝／羅素每場第2"], [20, 123])
        self.assertEqual(sc["乙 羅素全勝／安東每場第2"], [23, 9])
        self.assertEqual(sc["丙 領先不變"][0], 21)

    def test_all_second_place_totals_and_guarantee(self):
        tot = self.pack["own_data"]["standings_after_r15"]
        pool = sum(Model.second(sp) for _, sp in self.cal8)
        self.assertEqual(pool, 151)
        rus_max = tot["russell"] + 208
        self.assertEqual(rus_max, 444)
        self.assertEqual(rus_max + 1 - tot["antonelli"], 143)
        self.assertEqual(tot["antonelli"] + pool - rus_max, 9)
        g = self.dv["guarantee_points"]
        self.assertEqual((g["russell_max_total"], g["antonelli_needs_more"], g["all_second_place_total"]), (444, 143, 151))

    def test_path_a_holds_against_every_named_rival(self):
        """路徑甲（安東全勝、其餘依序第 2…第 7）在第 20 站對每位對手的領先差都大於剩餘可得分。"""
        tot = self.pack["own_data"]["standings_after_r15"]
        order = ["russell", "hamilton", "norris", "leclerc", "max_verstappen", "piastri"]
        gp = [18, 15, 12, 10, 8, 6]
        sp = [7, 6, 5, 4, 3, 2]
        idx = next(i for i, (rnd, _) in enumerate(self.cal8) if rnd == 20)
        a_total = tot["antonelli"] + sum(Model.win(s) for _, s in self.cal8[: idx + 1])
        left = self.m8.left_after(idx)
        self.assertEqual(left, 75)
        for pos, name in enumerate(order):
            gain = sum(gp[pos] + (sp[pos] if s else 0) for _, s in self.cal8[: idx + 1])
            self.assertGreater(a_total - (tot[name] + gain), left, name)

    def test_rivals_cap_at_round18(self):
        """美國站（第 18 站）安東內利前三個週末全勝時，各對手在這三個週末最多還能拿的分數。"""
        tot = self.pack["own_data"]["standings_after_r15"]
        idx = next(i for i, (rnd, _) in enumerate(self.cal8) if rnd == 18)
        a_total = tot["antonelli"] + sum(Model.win(s) for _, s in self.cal8[: idx + 1])
        line = self.m8.left_after(idx) + 1
        self.assertEqual((a_total, line), (385, 126))
        got = self.dv["rivals_cap_at_round18"]
        self.assertEqual(got["antonelli_after_round18_all_wins"], 385)
        for name in ("russell", "hamilton", "norris", "leclerc", "max_verstappen", "piastri"):
            self.assertEqual(got["cap"][name], a_total - line - tot[name], name)
        self.assertEqual(got["cap"]["russell"], 23)
        self.assertEqual(got["cap"]["hamilton"], 60)

    # ── 賽曆縮水 ──
    def test_calendar_variants(self):
        want = {
            8: dict(M=208, rus_max=444, need=143, a=(20, 123), b=(23, 9), pool=151),
            7: dict(M=183, rus_max=419, need=118, a=(19, 116), b=(22, 16), pool=133),
            6: dict(M=158, rus_max=394, need=93, a=(18, 109), b=(20, 23), pool=115),
        }
        tot = self.pack["own_data"]["standings_after_r15"]
        for name, c in self.dv["calendars"].items():
            n = c["n"]
            w = want[n]
            m = Model(self.cal8[:n], self.lead0)
            self.assertEqual(sum(Model.win(s) for _, s in m.cal), w["M"], name)
            self.assertEqual(tot["russell"] + w["M"], w["rus_max"], name)
            self.assertEqual(w["rus_max"] + 1 - tot["antonelli"], w["need"], name)
            self.assertEqual(m.path(Model.win, Model.second), w["a"], name)
            self.assertEqual(m.path(Model.second, Model.win), w["b"], name)
            self.assertEqual(sum(Model.second(s) for _, s in m.cal), w["pool"], name)
            self.assertEqual((c["M_after15"], c["russell_max"], c["need_guarantee"]), (w["M"], w["rus_max"], w["need"]), name)
            self.assertEqual(tuple(c["甲"]), w["a"], name)
            self.assertEqual(tuple(c["乙"]), w["b"], name)
            self.assertEqual(c["second_pool"], w["pool"], name)
        # 22 站時新加坡只差 2 分（領先差最多 124、封王線 126）
        c7 = next(c for c in self.dv["calendars"].values() if c["n"] == 7)
        self.assertEqual((c7["short_by"], c7["short_round"]), (2, 17))

    # ── 實測包絡（暴力窗口） ──
    def test_envelope_windows(self):
        wp = self.pack["own_data"]["weekend_points"]
        net = [wp[str(k)]["ant"] - wp[str(k)]["rus"] for k in range(1, 16)]
        self.assertEqual(sum(net), 66)

        def best(w):
            return max((sum(net[i:i + w]), i + 1, i + w) for i in range(len(net) - w + 1))

        def worst(w):
            return min((sum(net[i:i + w]), i + 1, i + w) for i in range(len(net) - w + 1))

        env = self.dv["envelope_vs_russell"]
        self.assertEqual(tuple(env["best3"]), best(3))
        self.assertEqual(tuple(env["worst3"]), worst(3))
        self.assertEqual(tuple(env["best4"]), best(4))
        self.assertEqual(best(3), (59, 4, 6))
        self.assertEqual(worst(3), (-43, 7, 9))
        self.assertEqual(best(4), (72, 3, 6))
        d = self.dv["best3_detail"]
        self.assertEqual((d["ant"], d["rus"], d["net"], d["max_per_driver"], d["sprints"]), (84, 25, 59, 91, 2))
        d = self.dv["worst3_detail"]
        self.assertEqual((d["ant"], d["rus"], d["net"]), (23, 66, -43))
        # 美國站：三個週末要 60、今年三週末最好 59
        self.assertEqual(60 - best(3)[0], 1)

    def test_hamilton_envelope(self):
        """對漢米爾頓：領先差 103 拉到封王線 126，三個週末淨賺 23 即可；他今年對漢米爾頓三週末最好 51（第 12–14 站）。"""
        wp = self.pack["own_data"]["weekend_points"]
        net = [wp[str(k)]["ant"] - wp[str(k)]["ham"] for k in range(1, 16)]
        self.assertEqual(sum(net), 103)
        env = self.dv["envelope_vs_hamilton"]
        self.assertEqual(env["per_round"], net)
        best3 = max((sum(net[i:i + 3]), i + 1, i + 3) for i in range(len(net) - 2))
        self.assertEqual(tuple(env["best3"]), best3)
        self.assertEqual(best3, (51, 12, 14))
        tot = self.pack["own_data"]["standings_after_r15"]
        self.assertEqual(tot["antonelli"] - tot["hamilton"], 103)
        self.assertEqual(126 - 103, 23)

    def test_lead_after_rounds(self):
        wp = self.pack["own_data"]["weekend_points"]
        cum = 0
        lead = {}
        for k in range(1, 16):
            cum += wp[str(k)]["ant"] - wp[str(k)]["rus"]
            lead[k] = cum
        self.assertEqual((lead[13], lead[14], lead[15]), (66, 81, 66))
        self.assertEqual(self.dv["lead_after_round"]["15"], 66)

    # ── 年齡 ──
    def test_ages(self):
        import datetime as dt
        last_bday = dt.date(2026, 8, 25)
        for label, d in (("美國站 2026-10-25", dt.date(2026, 10, 25)), ("阿布達比站 2026-12-06", dt.date(2026, 12, 6))):
            self.assertEqual(self.dv["age"][label], [20, (d - last_bday).days], label)
        self.assertEqual(self.dv["age"]["美國站 2026-10-25"], [20, 61])
        vet = (dt.date(2010, 11, 14) - dt.date(2010, 7, 3)).days
        self.assertEqual(self.dv["age"]["Vettel 2010-11-14 (出生 1987-07-03)"], [23, vet])
        self.assertEqual(vet, 134)

    # ── 文章 ↔ 事實表（文章存在時才驗） ──
    def test_article_states_the_load_bearing_numbers(self):
        if not ARTICLE.exists():
            self.skipTest("文章尚未進 repo")
        body = ARTICLE.read_text(encoding="utf-8")
        for token in ("66", "60", "59", "23", "126", "143", "151", "123", "27", "134", "61", "103"):
            self.assertIn(token, body, f"文章缺承重數字 {token}")


if __name__ == "__main__":
    unittest.main()
