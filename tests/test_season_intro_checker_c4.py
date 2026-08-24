#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-season-intros.py v4：導言第三批（2026-08-24 查核桌）暴露的 C4 缺口回歸測試。

C4 中文數詞繞過 gate。H3 的位置綁定只掃阿拉伯數字，寫手改中文數詞就整條繞開；
機械對帳全綠，靠對抗式人工查核才抓到。兩個實案：

  1991 初稿「四站」      → 統計值寫成中文數詞，NUM_RE 掃不到、anchor 綁不到
  第三批「三人爭冠」      → 同上，而且連「爭冠人數」這件事本身 checker 都沒有驗證路徑

對應兩道修補，每道都是**陽性（該抓的抓到）＋陰性（白名單／既有導言不誤殺）**成對：

  C4-a `check_cn_numerals`     → 中文數詞＋統計量詞硬 fail，慣用語走 CN_IDIOM_ALLOW 具名詞位
  C4-b `title_contenders`      → 爭冠人數用「末站前的積分數學可能性」驗，重用 clinch 機制

C4-b 的 1981 期望值（{Piquet, Reutemann, Laffite}）是先對 data/f1/db.sqlite 獨立 SQL 驗過才寫進來的，
不是抄轉述。驗法（1981 捨分規則 best 10，單站上限 = MAX(results.points) = 9）：

    SELECT MAX(round) FROM races WHERE season=1981;              -- 15
    SELECT MAX(points) FROM results WHERE season=1981;           -- 9.0
    SELECT round, driver_id, points FROM results WHERE season=1981 AND round<=14;
    -- 每位車手取單站分數的前 10 高相加 = 末站前保底；再把第 15 站補成 9 分後重取前 10 高 = 理論上限
    -- 保底：reutemann 49、piquet 48、laffite 43、jones 37、prost 37 …
    -- 上限：reutemann 58、piquet 57、laffite 52、jones 46、prost 46 …
    -- 追得上榜首保底 49 的只有 reutemann / piquet / laffite；jones 上限 46 < 49 → 已出局

跑法：python3 -m unittest discover -s tests -v
"""
import importlib.util
import pathlib
import sqlite3
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


chk = _load("check_season_intros_c4", "check-season-intros.py")

INTROS = sorted((p for p in chk.CONTENT.glob("*.md") if p.stem.isdigit()),
                key=lambda p: int(p.stem))


def _verdicts(text):
    return [(raw, verdict) for _s, _e, raw, verdict, _n in chk.cn_numeral_occurrences(text)]


# ================================================================ C4-a 陽性
class C4aCatchesChineseNumeralClaims(unittest.TestCase):
    """中文數詞＋統計量詞＝繞過 gate 的統計主張，一律硬 fail。"""

    def test_positive_1991_four_rounds_case(self):
        """實案一：1991 導言初稿的「四站」——阿拉伯數字 gate 完全掃不到。"""
        text = "塞納在末段四站連續奪冠，替麥拉倫鎖定冠軍。"
        self.assertEqual(_verdicts(text), [("四站", "violation")])
        self.assertTrue(chk.check_cn_numerals(1991, text))

    def test_positive_three_contenders_case(self):
        """實案二：第三批的「三人爭冠」。"""
        text = "末站前仍有三人爭冠，最後一站才分出勝負。"
        self.assertIn(("三人", "violation"), _verdicts(text))
        errors = chk.check_cn_numerals(1981, text)
        self.assertEqual(len(errors), 1, errors)

    def test_positive_error_message_tells_writer_what_to_do(self):
        """訊息必須指路：改阿拉伯數字＋掛 claim，別只說「錯了」。"""
        (msg,) = chk.check_cn_numerals(1991, "末段四站連續奪冠。")
        self.assertIn("阿拉伯數字", msg)
        self.assertIn("claim", msg)
        self.assertIn("CN_IDIOM_ALLOW", msg)

    def test_positive_default_deny_covers_unseen_quantifiers(self):
        """default-deny：沒在白名單裡的搭配一律違規，不必逐一登記「該抓」的形狀。"""
        for text in ("拿下五座世界冠軍", "全季贏下八場", "以十二分之差落敗",
                     "領先第二名九分", "由三隊瓜分勝利", "只跑了七圈"):
            with self.subTest(text=text):
                self.assertTrue(chk.check_cn_numerals(2000, text), f"{text} 應該被抓")

    def test_positive_whitelist_is_lexeme_scoped_not_a_loosened_regex(self):
        """白名單是**詞位**：放行「最後一站」不等於放行任何「一＋量詞」。"""
        self.assertEqual(_verdicts("最後一站澳洲大獎賽"), [("一站", "idiom")])
        for text in ("最後三站", "起手一站", "唯一一場", "第一週的一站"):
            with self.subTest(text=text):
                self.assertTrue(chk.check_cn_numerals(2000, text),
                                f"{text} 不在具名詞位裡，不該被放行")

    def test_positive_whitelist_entries_all_carry_a_reason(self):
        """每條白名單都要有理由字串（不准塞空白名單條目）。"""
        for lexeme, reason in chk.CN_IDIOM_ALLOW.items():
            with self.subTest(lexeme=lexeme):
                self.assertTrue(reason.strip(), f"{lexeme} 沒寫理由")


# ================================================================ C4-a 陰性
class C4aDoesNotOverfire(unittest.TestCase):
    """白名單詞位、順位詞、既有 40 篇導言都不得被誤殺。"""

    def test_negative_all_approved_intros_have_zero_violations(self):
        """40 篇已核准導言一條都不准紅——紅了就是真命中，要回報而不是靜默放寬。"""
        self.assertEqual(len(INTROS), 40, "導言篇數變了，這條斷言要重新確認")
        hits = {p.stem: chk.check_cn_numerals(int(p.stem), p.read_text(encoding="utf-8"))
                for p in INTROS}
        self.assertEqual({y: e for y, e in hits.items() if e}, {})

    def test_negative_every_whitelist_lexeme_is_attested_in_the_corpus(self):
        """白名單不准放沒有語料根據的條目（否則就是預先放寬）。"""
        corpus = "\n".join(p.read_text(encoding="utf-8") for p in INTROS)
        for lexeme in chk.CN_IDIOM_ALLOW:
            with self.subTest(lexeme=lexeme):
                self.assertIn(lexeme, corpus, f"{lexeme} 在 40 篇導言裡沒有實際命中")

    def test_negative_whitelist_lexemes_read_as_idiom_in_real_context(self):
        """每條白名單在**真實上下文**裡都要判成 idiom（不是只在孤立字串裡成立）。"""
        cases = {
            "最後一站": "1986 年最後一站澳洲大獎賽開賽前",
            "最後一圈": "的世界冠軍到最後一圈才確定",
            "每一站": "並在每一站都站上頒獎台",
            "這一季": "在這一季的賽事中喪生",
            "上一季": "延續上一季的冠軍對抗",
            "的一季": "再度奪下年度車手冠軍的一季",
            "唯一一座": "拿下生涯唯一一座世界冠軍",
            "是一場": "2002 年是一場近乎沒有懸念的賽季",
            "於一場": "克拉克於一場非世界錦標賽事故中喪生",
        }
        self.assertEqual(set(cases), set(chk.CN_IDIOM_ALLOW), "白名單與本測試的對照表不同步")
        for lexeme, sentence in cases.items():
            with self.subTest(lexeme=lexeme):
                self.assertEqual(chk.check_cn_numerals(2000, sentence), [])
                self.assertIn((lexeme, "idiom"),
                              [(n, v) for _s, _e, _r, v, n in chk.cn_numeral_occurrences(sentence)])

    def test_negative_ordinals_are_not_double_fired(self):
        """「第 N／倒數第 N／並列第 N」已由 ordinal_occurrences 開火，C4-a 不重複判錯。"""
        for text in ("維倫紐夫以第三名完賽", "在倒數第二站便已分出勝負",
                     "兩人並列第二名作收", "拿下生涯第三座世界冠軍", "拿下生涯第五冠"):
            with self.subTest(text=text):
                self.assertEqual(chk.check_cn_numerals(2007, text), [])
                self.assertTrue(any(v == "ordinal" for _r, v in _verdicts(text)), text)

    def test_negative_numeral_charset_is_reused_not_retyped(self):
        """字元集必須直接由 CN_DIGITS 導出（手敲字元集必出假陽性，這條是機械保險）。"""
        self.assertEqual(set(chk.CN_NUMERAL_CHARS), set(chk.CN_DIGITS))


# ================================================================ C4-b 陽性
class C4bTitleContendersMath(unittest.TestCase):
    """爭冠人數要用末站前的積分數學可能性驗，不是季末排名。"""

    def setUp(self):
        self.con = sqlite3.connect(chk.DB_PATH)
        self.addCleanup(self.con.close)

    def _claim(self, season, **kw):
        return {"_season": season, "verified": True, **kw}

    def test_positive_1981_survivor_set(self):
        """1981 末站（R15）前的數學存活集合 = {Piquet, Reutemann, Laffite}（見檔頭 SQL）。"""
        oracle = chk.SeasonOracle(self.con, 1981)
        result, why = oracle.contenders_before(15)
        self.assertIsNone(why)
        self.assertEqual(result["contenders"], {"piquet", "reutemann", "laffite"})
        self.assertEqual(result["leader"], "reutemann")
        self.assertEqual(result["leader_floor"], 49)
        self.assertEqual(result["through_round"], 14)

    def test_positive_1981_jones_is_mathematically_out(self):
        """瓊斯 R14 後保底 37、上限 46 ＜ Reutemann 保底 49——倒推成第三人是錯的。"""
        oracle = chk.SeasonOracle(self.con, 1981)
        floor = oracle._segments(oracle.round_points["jones"], 14)
        ceiling = oracle._ceiling()
        best = oracle._segments({**{r: v for r, v in oracle.round_points["jones"].items() if r <= 14},
                                 15: ceiling})
        self.assertEqual((floor, ceiling, best), (37.0, 9.0, 46.0))
        self.assertNotIn("jones", oracle.contenders_before(15)[0]["contenders"])

    def test_positive_1981_claim_verifies(self):
        ok, actual, detail = chk.verify_claim(self.con, self._claim(
            1981, kind="title_contenders", round=15, value=3,
            drivers=["piquet", "reutemann", "laffite"]))
        self.assertTrue(ok, f"{detail}＝{actual}")
        self.assertEqual(actual["count"], 3)

    def test_positive_wrong_members_are_rejected(self):
        """成員錯（把 Laffite 換成已出局的 Jones）→ 判錯，訊息要點出正確集合。"""
        ok, actual, detail = chk.verify_claim(self.con, self._claim(
            1981, kind="title_contenders", round=15, value=3,
            drivers=["piquet", "reutemann", "jones"]))
        self.assertFalse(ok)
        self.assertIn("laffite", detail)
        self.assertEqual(actual["recomputed"], ["laffite", "piquet", "reutemann"])

    def test_positive_wrong_count_is_rejected(self):
        """人數錯（成員對但寫 4 人）→ 判錯：人數與成員是兩條獨立的腿。"""
        ok, actual, detail = chk.verify_claim(self.con, self._claim(
            1981, kind="title_contenders", round=15, value=4,
            drivers=["piquet", "reutemann", "laffite"]))
        self.assertFalse(ok)
        self.assertEqual(actual, 3)
        self.assertIn("人數", detail)

    def test_positive_2010_non_dropped_scores_season(self):
        """非捨分季正例：2010 阿布達比站前 4 人數學上仍可能奪冠。

        獨立驗算（無捨分規則，純累加；單站上限 25）：R18 後 alonso 246、webber 238、
        vettel 231、hamilton 222；上限分別 271／263／256／247，全都 ≥ 領先者保底 246。
        """
        oracle = chk.SeasonOracle(self.con, 2010)
        self.assertFalse(oracle.has_scoring_rule, "2010 不該有捨分規則")
        result, _ = oracle.contenders_before(19)
        self.assertEqual(result["contenders"], {"alonso", "webber", "vettel", "hamilton"})
        self.assertEqual((result["leader"], result["leader_floor"]), ("alonso", 246))
        ok, actual, detail = chk.verify_claim(self.con, self._claim(
            2010, kind="title_contenders", round=19, value=4,
            drivers=["alonso", "webber", "vettel", "hamilton"]))
        self.assertTrue(ok, f"{detail}＝{actual}")

    def test_positive_season_ending_event_driver_is_not_a_contender(self):
        """SEASON_ENDING_EVENTS 已發生者不算爭冠者——1970 R11 前的 Rindt 雖仍居榜首。"""
        result, _ = chk.SeasonOracle(self.con, 1970).contenders_before(11)
        self.assertEqual(result["leader"], "rindt")
        self.assertEqual(result["excluded_by_event"], ["rindt"])
        self.assertNotIn("rindt", result["contenders"])

    def test_positive_round_out_of_range_is_rejected(self):
        """round 越界要說清楚，不准回一個看似合理的集合。"""
        oracle = chk.SeasonOracle(self.con, 1981)
        for bad in (1, 0, 17):
            with self.subTest(round=bad):
                result, why = oracle.contenders_before(bad)
                self.assertIsNone(result)
                self.assertIn("超出範圍", why)

    def test_positive_drivers_list_is_mandatory(self):
        """實體綁定必填（比照 H2）：沒寫 drivers 直接判錯。"""
        ok, _actual, detail = chk.verify_claim(self.con, self._claim(
            1981, kind="title_contenders", round=15, value=3))
        self.assertFalse(ok)
        self.assertIn("drivers", detail)

    def test_positive_text_claiming_a_count_without_a_claim_fails(self):
        """正文側：出現「爭冠＋人數」而 pack 無 title_contenders → 判錯。"""
        text = "1981 年末站前仍有 3 人爭冠，最後一站才分出勝負。"
        errors = chk.check_bindings(1981, text, [], [], {})
        self.assertTrue(any("title_contenders" in e for e in errors), errors)

    def test_positive_chinese_numeral_count_also_trips_the_text_rule(self):
        """中文數詞寫的人數同樣觸發正文側規則（C4-a 與 C4-b 各開一槍）。"""
        text = "末站前仍有三人爭冠。"
        self.assertTrue(any("title_contenders" in e for e in chk.check_bindings(1981, text, [], [], {})))
        self.assertTrue(chk.check_cn_numerals(1981, text))

    def test_positive_semantic_strength_is_possibility_not_certainty(self):
        """語意強度：訊息只能說「數學上仍可能」，不得升格成「必然奪冠」。"""
        _ok, _actual, detail = chk.verify_claim(self.con, self._claim(
            1981, kind="title_contenders", round=15, value=3,
            drivers=["piquet", "reutemann", "laffite"]))
        self.assertIn("非必然", detail)
        self.assertNotIn("必然奪冠", detail.replace("非必然", ""))


# ================================================================ C4-b 陰性
class C4bDoesNotOverfire(unittest.TestCase):
    """既有導言不得因為 C4-b 翻紅；順位詞不得被誤讀成人數。"""

    def setUp(self):
        self.con = sqlite3.connect(chk.DB_PATH)
        self.addCleanup(self.con.close)

    def test_negative_existing_intros_trigger_no_contender_rule(self):
        """8 篇寫了「冠軍之爭／爭冠」的導言都沒宣稱人數，不該被要求補 claim。"""
        for p in INTROS:
            text = p.read_text(encoding="utf-8")
            with self.subTest(year=p.stem):
                self.assertEqual(chk.contender_count_mentions(text), [])

    def test_negative_ordinal_near_a_trigger_is_not_a_count(self):
        """「第三名」是順位不是人數，即使緊貼「冠軍之爭」也不觸發（含「第十二名」這種兩位數）。"""
        for text in ("冠軍之爭中他以第三名完賽", "第十二名與冠軍之爭無關", "冠軍之爭裡第 3 名的他"):
            with self.subTest(text=text):
                self.assertEqual(chk.contender_count_mentions(text), [])

    def test_negative_count_far_from_trigger_is_not_linked(self):
        """離觸發詞太遠的人數詞不算同一個主張（鄰接窗）。"""
        far = "他贏下 3 人組成的隊內對決" + "，" * 40 + "冠軍之爭延燒到終點。"
        self.assertEqual(chk.contender_count_mentions(far), [])

    def test_negative_claim_present_silences_the_text_rule(self):
        """pack 有通過重查的 title_contenders 時，正文側不再開火。"""
        text = "末站前仍有 3 人爭冠。"
        ok_claim = {"kind": "title_contenders", "value": 3, "anchors": ["3 人爭冠"],
                    "drivers": ["piquet", "reutemann", "laffite"]}
        errors = chk.check_bindings(1981, text, [ok_claim], [ok_claim], {})
        self.assertEqual([e for e in errors if "title_contenders" in e], [])

    def test_negative_existing_clinch_values_do_not_drift(self):
        """C4-b 只讀不寫：既有 clinch 值一個都不准漂（重用 _rival_settled 不得有副作用）。"""
        expected = {(1957, "fangio"): (6, 2), (1961, "phil_hill"): (7, 1),
                    (1970, "rindt"): (12, 1), (1978, "mario_andretti"): (14, 2),
                    (1988, "senna"): (15, 1), (2002, "michael_schumacher"): (11, 6)}
        for (year, driver), want in expected.items():
            oracle = chk.SeasonOracle(self.con, year)
            oracle.contenders_before(oracle.last_round)
            with self.subTest(year=year):
                self.assertEqual(oracle.clinch(driver), want)

    def test_negative_all_approved_intros_stay_green(self):
        """v4 兩道修補之後，40 篇已核准導言仍須全綠、零豁免。"""
        failures = {int(p.stem): chk.check_year(int(p.stem), self.con) for p in INTROS}
        self.assertEqual({y: e for y, e in failures.items() if e}, {})


if __name__ == "__main__":
    unittest.main()
