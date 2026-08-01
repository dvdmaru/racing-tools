#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""賽曆頁渲染回歸——譯名 fallback 不得重複印原文，賽季敘述不得寫死站數加減。

由來（2026-08-01）：巴林站移師馬來西亞雪邦，jolpica 新增賽事名稱
「Bahrain Grand Prix in Malaysia」，2026 賽曆由 22 站變 23 站。這一次改動同時引爆了
兩顆早就埋好、但在此之前永遠不會響的地雷：

1. **譯名 fallback 重複**：賽曆卡片無條件輸出 `race_zh(name)` 後再補一個
   `<span class="en">name</span>`。譯名表命中時沒問題；命中不到時 `race_zh` 回原文，
   於是同一列印兩次英文。建站以來每個賽事名稱都有譯名，所以這條路徑從未被走到。
2. **站數敘述自我矛盾**：FAQ 寫「{n_races} 站。原公布 24 站…取消且不遞補，縮為 {n_races} 站」，
   其中 n_races 是動態算的、敘述是寫死的。變成 23 站那天，這句話會當著讀者的面算錯數。

兩者都屬同一類：**可變的量交給資料、寫死的字只描述事件**。測試釘的是這條規則。

跑法：python3 -m unittest discover -s tests -v
"""
import datetime
import importlib.util
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cal = _load("gen_racing_calendar", "gen-racing-calendar.py")
rc = _load("racinglib_cal", "racinglib.py")


def _race(name, cid="sepang", circuit="Sepang International Circuit"):
    """最小可渲染的賽事物件（欄位對齊 jolpica races.json）。"""
    return {
        "round": "16", "raceName": name, "date": "2026-10-04", "time": "07:00:00Z",
        "Circuit": {"circuitId": cid, "circuitName": circuit,
                    "Location": {"locality": "Kuala Lumpur", "country": "Malaysia"}},
    }


class RaceNameFallbackTests(unittest.TestCase):
    """沒有核准譯名時顯示原文＝誠實 fallback；但原文只能出現一次。"""

    def _card(self, name):
        return cal.build_cards([_race(name)], {}, datetime.date(2026, 8, 1))

    def test_untranslated_name_appears_exactly_once(self):
        name = "Totally Unmapped Grand Prix"
        self.assertNotIn(name, rc.RACE_ZH, "前提壞了：這個名稱不該有核准譯名")
        html = self._card(name)
        self.assertEqual(html.count(name), 1, f"未譯名稱被印了不只一次：\n{html}")

    def test_untranslated_name_emits_no_empty_en_span(self):
        """重複時的具體症狀是多一個 .en span——連 span 都不該出現。"""
        html = self._card("Totally Unmapped Grand Prix")
        self.assertNotIn('<span class="en">', html)

    def test_translated_name_still_shows_both(self):
        """反向：有譯名時中英仍要並列，別把守衛寫成一律不出原文。"""
        name = "Japanese Grand Prix"
        self.assertIn(name, rc.RACE_ZH, "前提壞了：這個名稱應該有核准譯名")
        html = self._card(name)
        self.assertIn(rc.RACE_ZH[name], html)
        self.assertIn(f'<span class="en">{name}</span>', html)

    def test_guard_would_catch_the_2026_r16_regression(self):
        """真正引爆這顆雷的那個名稱，逐字釘住。

        它在 race-zh.json 是 status=pending（等 Charlie 裁決譯名），
        所以現在必然走 fallback 路徑；哪天核准了，上面那條 translated 測試接手。
        """
        html = self._card("Bahrain Grand Prix in Malaysia")
        self.assertEqual(html.count("Bahrain Grand Prix in Malaysia"), 1)


class SeasonNarrativeTests(unittest.TestCase):
    """FAQ 的賽季敘述不得寫死站數的加減。"""

    def test_faq_does_not_hardcode_a_race_count(self):
        """對 2026 餵入不同站數，敘述句不得出現與 n_races 無關的裸站數。

        「原公布 24 站」是**歷史事實**、允許寫死；會漂的是「縮為 N 站」那種
        由 24 減出來的結果。所以斷言：把 24（歷史值）與 n_sprints（另一個動態值）
        濾掉之後，剩下的「N 站」全部等於 n_races。
        """
        sprints = 6
        for n in (22, 23, 25):
            answer = dict(cal.page_faq(2026, n, sprints))["2026 F1 賽季共有幾站？"]
            counts = {int(x) for x in re.findall(r"(\d+) 站", answer)} - {24, sprints}
            self.assertEqual(
                counts, {n},
                f"n_races={n} 時敘述出現了對不上的站數 {sorted(counts)}：{answer}")

    def test_faq_reports_the_count_it_was_given(self):
        self.assertTrue(dict(cal.page_faq(2026, 23, 6))["2026 F1 賽季共有幾站？"]
                        .startswith("23 站。"))

    def test_the_count_assertion_can_actually_fail(self):
        """反向：如果敘述真的寫死了別的站數，上面那條要抓得到。

        全綠有兩種解釋——「敘述是動態的」或「斷言根本沒在看」。這條排除後者。
        """
        fake = "23 站。賽季原公布 24 站，取消兩站後縮為 22 站。其中 6 站為衝刺賽。"
        counts = {int(x) for x in re.findall(r"(\d+) 站", fake)} - {24, 6}
        self.assertNotEqual(counts, {23}, "斷言寫壞了：它連寫死的 22 都放行")

    def test_non_2026_season_gets_no_hardcoded_narrative(self):
        """賽季敘述綁 2026；換季後自動退場，不會把舊聞帶到新賽季。"""
        answer = dict(cal.page_faq(2027, 24, 6))["2027 F1 賽季共有幾站？"]
        for word in ("巴林", "沙烏地", "雪邦", "馬來西亞"):
            self.assertNotIn(word, answer)


class RaceZhRegistryTests(unittest.TestCase):
    """race-zh.json 的 pending 條目對頁面不可見（default-deny）。"""

    def test_pending_entry_is_not_visible_to_pages(self):
        raw = json.loads((ROOT / "scripts" / "race-zh.json").read_text(encoding="utf-8"))
        pending = [k for k, v in raw.items()
                   if isinstance(v, dict) and v.get("status") == "pending"]
        for k in pending:
            self.assertNotIn(k, rc.RACE_ZH, f"pending 譯名不該被頁面用到：{k}")

    def test_new_2026_r16_name_is_registered(self):
        """就算還沒核准，名稱本身要在表裡——否則沒人知道有待辦。"""
        raw = json.loads((ROOT / "scripts" / "race-zh.json").read_text(encoding="utf-8"))
        self.assertIn("Bahrain Grand Prix in Malaysia", raw)


if __name__ == "__main__":
    unittest.main()
