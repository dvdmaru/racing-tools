#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-season-intros.py — 人工賽季導言的機械對帳（v3：v2 補查核桌 SOL-VERDICT-5 的四個結構性漏洞
H1–H4，v3 再補導言第二批實戰暴露的 H5 除名／H6 clinch 事後之明／H7 clinch 同分 countback）。

v1 對 content/seasons/<year>.md 做兩層 gate：(1) 導言裡每個阿拉伯數字都要落在 facts pack
verified claim 的**值集合**內；(2) 每條 verified claim 按 kind 對 data/f1/db.sqlite 重查。
2026-08-13 的對抗式查核（SOL-VERDICT-5）證明這兩層合起來仍會放行錯的稿子，列出四個漏洞：

  H1 oracle 循環引用：champion_points／runner_up_points 只回讀 driver_standings，而 facts pack
     的值也抄自同一張表。1976 該表存 hunt 66／lauda 64（官方與逐站加總都是 69／68），錯值與錯
     oracle 互相印證，checker 全綠。
  H2 driver 欄位未綁定數值查詢：只按「年度＋順位」查值，pack 寫錯車手 ID 仍會綠。
  H3 正文數字只做值集合成員檢查：數字只要「存在於某條 claim 的值」就放行，沒有綁到出現位置，
     同值 token 被移植到別的主張（乃至「F1」的 1）都抓不到。
  H4 並列順位未驗：2007 Hamilton／Alonso 同為 109 分，官方順位是 P2／P3（countback 分出），
     pack 若寫「並列第二」checker 沒有任何驗證路徑。

v2 的四道對應修補（全部只加檢查、不放寬既有 gate）：

  H1 → 三層 provenance：
       (a) **L1 斷言**：db.sqlite 必須是套過 data/f1/standings-overrides.json（by=charlie）
           的 L1。若某季有裁決卻讀到 L0 raw 值 → 直接判錯（防有人把 checker 指回 raw）。
       (b) **獨立重算 oracle**：points／wins／position 另用 `results`＋`sprint_results`＋
           data/f1/scoring-rules.json 的捨分規則重算一次（重用 crosscheck-standings.py 的
           `_apply_segments`／`_rank`，含 countback）。standings 與重算不一致 → 判錯。
           這條就是 1976 案例的抓手：L0 的 66／64 與逐站重算 69／68 對不上。
       (c) **外部快照對照**：data/f1/standings-crosscheck-report.json（en.wikipedia 快照，
           coverage 1950–1990）。claim 讀到的 (table, entity, field) 若在該報告有 diff 而未被
           已核准 override 解決 → 判錯。不在 coverage 內的賽季→報告標「單一來源」提醒，不假裝驗過。
  H2 → 實體綁定改成**必填**：champion_points 等 kind 沒寫 driver／constructor → 直接判錯
       （v1 是「有寫才驗」，等於預設不驗）。
  H3 → 正文數字改成**位置綁定**：claim 需宣告 `anchors`（正文逐字片段）；正文每一個數字出現
       位置都必須落在某個 anchor 區間內，且該 claim 的值要等於那個數字。沒有 anchor 覆蓋的數字
       ＝未綁定，判錯。夾在英數 token 裡的數字（F1、V10、MP4）另走 `non_statistical_tokens`
       具名白名單，未具名一律判錯。
  H4 → 順位詞進對帳：正文的「第 N」「倒數第 N」「並列第 N」也要被 anchor 綁到順位型 claim；
       新增 `tied_position`（真的並列才過）與 `countback_order`（同分循序，必須由 countback
       重算解釋得出該順序）。正文出現同分字眼（並列／同列／同分／相同積分）而 pack 沒有任一條
       tie 型 claim → 判錯。

2026-08-23 導言第二批實戰又暴露三個缺口（v3 補）：

  H5 除名不建模：重算 oracle 純以積分排序，不看 driver_standings.position_text='D'（賽季結束後
     遭年度除名）。1997 舒馬克的 78 分被排進 P2，Frentzen（官方 P2、42 分）的 runner_up_points／
     driver_position 因此驗不過。
  H6 clinch 事後之明：對手上限原本只算「該對手實際還有出賽的站次」，等於用賽季結束後才知道的
     資訊回推當下。1978 Peterson 在 R14 蒙札事故後不再出賽，舊口徑把 Andretti 的封王算成 R13——
     但 R13 當下 Peterson 上限 78 ＞ Andretti 保底 63，根本沒鎖定。
  H7 clinch 同分未套 countback：舊判準是 `floor > best_rival` 嚴格大於，積分理論上可追平時沒有
     比 countback。1957 方吉歐在第 6 站德國站就封王（同分時勝場多者勝），舊 oracle 延後到第 7 站。

v3 的三道對應修補（同樣只加檢查、不放寬既有 gate）：

  H5 → **除名建模**：`SeasonOracle` 從 driver_standings 讀 `position_text` 這個**分類標記**
       （只讀標記，不讀 points／position 的值，故不構成 H1 的值循環引用——「賽季結束後遭除名」
       是治理事實，results 層沒有這個訊號，沒有別的地方可讀）。標記 ∈ EXCLUDED_POSITION_TEXTS
       者從年度排名中剔除，其餘車手順位往前遞補；標記既非數字、也不在具名清單內 → 判錯
       （default-deny：不認得的標記不准默默當成一般車手）。
       射程界線：只影響**年度最終排名** `rank()`。`rank_through()`（末站前的即時累計榜）與
       `clinch()` 的對手集合**不套用**——1997 的除名是賽季結束後才發生的，賽季進行中舒馬克是
       貨真價實的對手，把他從當下的榜上抹掉才是另一種事後之明。
  H6 → **對手上限一律用剩餘排程站次封頂**，不再看「他之後實際有沒有出賽」。唯一的例外是
       SEASON_ENDING_EVENTS：在**該站賽事當下**已身故／確定退出賽季的車手，自該站起不再計——
       而且只有在評估站次 rnd ≥ 該站時才適用（rnd < 該站時事件還沒發生，不得預知）。
       ⚠️ results.status 撐不起這個判定：1961 von Trips（R7 蒙札）與 1978 Peterson（R14 蒙札）
       的 status 都只是泛用的 `Accident`，與 Moss 1960、Hunt 1973 這些傷退／退出完全同字串；
       全庫只有 3 列 `Fatal accident`（1970 rindt／1974 koinigg／1982 paletti）。因此改用
       **具名例外清單＋理由＋來源**（比照站規 default-deny），並把 FATAL_STATUSES 一併納入，
       未來資料若標了致命狀態不必改清單。
  H7 → clinch 判準改 `floor >= best_rival`，**同分時比 countback**：對手若要追平上限就必須把
       剩餘站次全數拿下，因此對手的 countback 要用**理論最佳**（現有完賽分布 ＋ 剩餘站次各記
       一勝）來比，不能拿他現實中的勝場數比。冠軍側則用保底情境（此後不再得分＝現有分布）。
       countback 完全同階（分不出先後）→ 不算鎖定（default-deny）。

已知邊界（誠實聲明，不得解讀為已驗）：
  - 1991 年起沒有外部 standings 快照，points 仍是單一來源（jolpica）＋逐站重算兩腿，報告會標。
  - SEASON_ENDING_EVENTS 是**人工具名清單**，只補到目前對帳到的賽季；沒登記的季末退出者一律
    照「剩餘排程站次全額封頂」處理（保守：只會把 clinch 算得比實際晚，不會提早放行）。
  - clinch 的對手上限含當季所有出現在 results 的車手。1950 年代的 Indy 500 站次對歐洲車手來說
    實際上不可能參賽，但「他不會去」是排程外知識，機械層不假設——同樣是保守方向。
  - 非數字、非順位的語意主張（因果、心理狀態、「首位／唯一」類全稱詞）機械層驗不了，仍須
    對抗式人工查核。全綠只代表「數字與順位這兩層沒抓到錯」。

用法：
  python3 scripts/check-season-intros.py                # 掃 content/seasons/ 全部導言
  python3 scripts/check-season-intros.py 2002 2021      # 只掃指定年份
  python3 scripts/check-season-intros.py --scaffold 1958  # 印未綁定的數字／順位詞與候選 anchor
"""
import importlib.util
import json
import pathlib
import re
import sqlite3
import sys
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "seasons"
DB_PATH = ROOT / "data" / "f1" / "db.sqlite"
OVERRIDES_PATH = ROOT / "data" / "f1" / "standings-overrides.json"
CROSSCHECK_PATH = ROOT / "data" / "f1" / "standings-crosscheck-report.json"
SCORING_PATH = ROOT / "data" / "f1" / "scoring-rules.json"

# 阿拉伯數字 token（含小數：395.5、371.33）。
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
# 英數混排 token（F1、V10、MP4、W12）：裡面的數字不是統計值，要另外具名白名單。
ALNUM_RE = re.compile(r"[A-Za-z]+\d+(?:\.\d+)?[A-Za-z]*|\d+[A-Za-z]+")
# 順位詞：可帶「倒數／並列／同列」前綴，數字可為阿拉伯或中文。
ORD_RE = re.compile(r"(倒數|並列|同列)?第\s*([0-9]+|[一二三四五六七八九十]+)")
# 同分字眼：出現就必須有 tie 型 claim 撐。
TIE_WORDS = ("並列", "同列", "同分", "相同積分", "同積分", "積分相同")

CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# ---- H5：standings 的 position_text 分類標記 --------------------------------
# 只有這三類被認得；其餘一律判錯（default-deny：不認得的標記不准默默當一般車手處理）。
UNRANKED_POSITION_TEXT = "-"            # 無積分／未列入年度榜（全庫 1463 列，points 皆為 0）
EXCLUDED_POSITION_TEXTS = {"D", "E"}    # 賽季結束後遭年度除名（1997 michael_schumacher='D'）

# ---- H6：在「該站賽事當下」即確定不再參賽的具名例外清單 ----------------------
# 為什麼要人工具名：results.status 撐不起這個判定。全庫只有 3 列 'Fatal accident'，而 1961
# von Trips 與 1978 Peterson 的 status 都只是泛用的 'Accident'——與 1960 Moss、1973 Hunt 這些
# 傷退後復出的完全同字串。沒有這張表就只剩「他之後沒再出賽」這個事後之明（＝H6 本身）。
# 每筆都要有理由與來源；沒登記的一律用「剩餘排程站次全額封頂」（保守方向）。
SEASON_ENDING_EVENTS = {
    (1961, "trips"): {"round": 7, "reason": "義大利站正賽事故身亡",
                      "source": "en.wikipedia 1961 Italian Grand Prix"},
    (1970, "rindt"): {"round": 10, "reason": "義大利站賽事週末事故身亡",
                      "source": "results.status='Fatal accident'"},
    (1973, "cevert"): {"round": 15, "reason": "美國站排位賽事故身亡",
                       "source": "en.wikipedia 1973 United States Grand Prix"},
    (1974, "koinigg"): {"round": 15, "reason": "美國站正賽事故身亡",
                        "source": "results.status='Fatal accident'"},
    (1975, "donohue"): {"round": 12, "reason": "奧地利站熱身賽事故，兩日後不治",
                        "source": "en.wikipedia 1975 Austrian Grand Prix"},
    (1978, "peterson"): {"round": 14, "reason": "義大利站起跑事故重傷，翌日不治",
                         "source": "en.wikipedia 1978 Italian Grand Prix"},
    (1982, "villeneuve"): {"round": 5, "reason": "比利時站排位賽事故身亡",
                           "source": "en.wikipedia 1982 Belgian Grand Prix"},
    (1982, "paletti"): {"round": 8, "reason": "加拿大站起跑碰撞身亡",
                        "source": "results.status='Fatal accident'"},
}
# 資料層若已標成致命狀態，不必等人補清單（清單與這裡取較早的站次）。
FATAL_STATUSES = {"Fatal accident"}

# ---- kind 分類 -------------------------------------------------------------
REQUIRE_DRIVER = {"champion_points", "runner_up_points", "champion_wins", "driver_position",
                  "driver_podiums", "clinch_round", "clinch_remaining", "clinch_from_end",
                  "rank_before_final", "career_titles", "race_finish_position"}
REQUIRE_CONSTRUCTOR = {"constructor_wins"}
REQUIRE_DRIVERS = {"tied_before_final", "tied_position", "countback_order"}
# 可以覆蓋「第 N」這種順位詞的 kind
ORDINAL_KINDS = {"driver_position", "race_finish_position", "clinch_round", "season_rounds",
                 "career_titles", "rank_before_final", "earliest_race", "champion_wins",
                 "driver_podiums", "constructor_wins", "countback_order"}
FROM_END_KINDS = {"clinch_from_end"}
TIE_ORDINAL_KINDS = {"tied_position"}
TIE_KINDS = {"tied_position", "countback_order", "tied_before_final"}
# 「榜首＝冠軍」類聚合：賽季沒跑完就不成立（2026 進行中）。
SEASON_MUST_BE_COMPLETE = {"champion_points", "runner_up_points", "champion_wins", "career_titles",
                           "clinch_round", "clinch_remaining", "clinch_from_end",
                           "tied_position", "countback_order", "driver_position"}
KNOWN_KINDS = (REQUIRE_DRIVER | REQUIRE_CONSTRUCTOR | REQUIRE_DRIVERS |
               {"season_exists", "earliest_season", "season_rounds",
                "no_constructor_championship", "earliest_race"})


def _num(x):
    """數值正規化：整值回 int（77.0→77）、非整值回 float（395.5）。"""
    f = float(x)
    return int(f) if f.is_integer() else f


def _cn_num(text):
    """中文數字→int（只需 1–99；『十』『十二』『二十』『二十二』）。無法解析回 None。"""
    if text.isdigit():
        return int(text)
    if not text or any(ch not in CN_DIGITS for ch in text):
        return None
    if "十" not in text:
        return CN_DIGITS[text] if len(text) == 1 else None
    head, _, tail = text.partition("十")
    tens = CN_DIGITS[head] if head else 1
    ones = CN_DIGITS[tail] if tail else 0
    return tens * 10 + ones


def extract_numbers(text: str):
    """回導言文中所有阿拉伯數字 token 的正規化數值 list（保留重複，供錯誤定位）。"""
    return [_num(m.group(0)) for m in NUM_RE.finditer(text)]


def number_occurrences(text: str):
    """回 [(start, end, value, in_token)]；in_token＝該數字夾在 F1／V10 這類英數 token 裡。"""
    token_spans = [(m.start(), m.end(), m.group(0)) for m in ALNUM_RE.finditer(text)]
    out = []
    for m in NUM_RE.finditer(text):
        holder = next((tok for s, e, tok in token_spans if s <= m.start() and m.end() <= e), None)
        out.append((m.start(), m.end(), _num(m.group(0)), holder))
    return out


def ordinal_occurrences(text: str):
    """回 [(start, end, raw, value, modifier)]；modifier ∈ {None,'倒數','並列','同列'}。"""
    out = []
    for m in ORD_RE.finditer(text):
        value = _cn_num(m.group(2))
        if value is None:
            continue
        out.append((m.start(), m.end(), m.group(0), value, m.group(1)))
    return out


# ---------- 獨立重算 oracle（H1-b）：results＋捨分規則，不碰 standings ----------

def _load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_CC = None


def _cc():
    """延遲載入 crosscheck-standings.py，重用它的捨分套用與 countback 排名。"""
    global _CC
    if _CC is None:
        _CC = _load_module("crosscheck_standings_shared", "crosscheck-standings.py")
    return _CC


def _scoring_rules():
    if not SCORING_PATH.exists():
        return {}
    return json.loads(SCORING_PATH.read_text(encoding="utf-8")).get("seasons", {})


class SeasonOracle:
    """一季的獨立重算：逐站 results（＋sprint）套當年捨分規則，再以 countback 排名。

    這條路徑完全不讀 driver_standings，因此可以與 standings 互相打臉——1976 的 66／64 就是
    在這裡與 69／68 對不上而被抓出來的。
    """

    def __init__(self, con, year):
        self.con = con
        self.year = int(year)
        self.round_points = defaultdict(lambda: defaultdict(float))
        self.finishes = defaultdict(Counter)
        self.entered = defaultdict(set)
        self.round_finish = defaultdict(dict)   # driver → {round: 完賽名次}（供 clinch 的 countback）
        row = con.execute("SELECT MAX(round) FROM races WHERE season=?", (self.year,)).fetchone()
        self.last_round = int(row[0]) if row and row[0] else 0
        # H6：資料層已標致命狀態者，自該站起不再計（與具名清單取較早者）。
        self.season_ending = {}
        for (season, did), item in SEASON_ENDING_EVENTS.items():
            if int(season) == self.year:
                self.season_ending[did] = int(item["round"])
        for rnd, did, pts, ptext, status in con.execute(
                "SELECT round, driver_id, points, position_text, status FROM results WHERE season=?",
                (self.year,)):
            self.round_points[did][rnd] += float(pts or 0)
            self.entered[did].add(rnd)
            if str(ptext).isdigit() and float(pts or 0) > 0:
                self.finishes[did][int(ptext)] += 1
                self.round_finish[did][rnd] = int(ptext)
            if status in FATAL_STATUSES:
                self.season_ending[did] = min(self.season_ending.get(did, rnd), rnd)
        # H5：年度除名標記（只讀 position_text 這個分類欄，不讀 points／position 的值）。
        self.excluded, self.unknown_markers = set(), []
        for did, ptext in con.execute(
                "SELECT driver_id, position_text FROM driver_standings WHERE season=?", (self.year,)):
            text = "" if ptext is None else str(ptext).strip()
            if text.isdigit() or text == UNRANKED_POSITION_TEXT:
                continue
            if text.upper() in EXCLUDED_POSITION_TEXTS:
                self.excluded.add(did)
            else:
                self.unknown_markers.append((did, ptext))
        for rnd, did, pts in con.execute(
                "SELECT round, driver_id, points FROM sprint_results WHERE season=?", (self.year,)):
            self.round_points[did][rnd] += float(pts or 0)
        rules = _scoring_rules().get(str(self.year), {})
        self.rule = (rules or {}).get("driver") or {"segments": [{"rounds": [1, None], "best": None}]}
        self.has_scoring_rule = bool((rules or {}).get("driver"))
        self._points = None
        self._rank = None
        raced = con.execute("SELECT COUNT(DISTINCT round) FROM results WHERE season=?",
                            (self.year,)).fetchone()
        # 「這季跑完沒」：排程站數與已有 results 的站數不等＝進行中，榜首≠冠軍。
        self.complete = bool(self.last_round) and int((raced and raced[0]) or 0) == self.last_round

    # --- 基礎 ---
    def _segments(self, round_points, upto=None):
        pts = round_points if upto is None else {r: v for r, v in round_points.items() if r <= upto}
        return _cc()._apply_segments(pts, self.rule["segments"], self.last_round)

    def points(self, driver=None):
        if self._points is None:
            self._points = {d: self._segments(rp) for d, rp in self.round_points.items()}
        return self._points if driver is None else self._points.get(driver)

    def rank(self, driver=None):
        """年度最終排名。H5：遭年度除名者（position_text='D'）不佔位，其後車手往前遞補。"""
        if self._rank is None:
            points = {d: v for d, v in self.points().items() if d not in self.excluded}
            finishes = defaultdict(Counter, {d: c for d, c in self.finishes.items()
                                             if d not in self.excluded})
            self._rank = _cc()._rank(points, finishes)
        return self._rank if driver is None else self._rank.get(driver)

    def wins(self, driver):
        return self.con.execute(
            "SELECT COUNT(*) FROM results WHERE season=? AND driver_id=? AND position_text='1'",
            (self.year, driver)).fetchone()[0]

    # --- 衍生 ---
    def rank_through(self, upto):
        """截至第 upto 站（含）的累計排名（同樣走捨分＋countback）。"""
        points = {d: self._segments(rp, upto) for d, rp in self.round_points.items()}
        finishes = defaultdict(Counter)
        for rnd, did, pts, ptext in self.con.execute(
                "SELECT round, driver_id, points, position_text FROM results "
                "WHERE season=? AND round<=?", (self.year, upto)):
            if str(ptext).isdigit() and float(pts or 0) > 0:
                finishes[did][int(ptext)] += 1
        return _cc()._rank(points, finishes)

    def _ceiling(self):
        r = self.con.execute("SELECT MAX(points) FROM results WHERE season=?", (self.year,)).fetchone()
        s = self.con.execute("SELECT MAX(points) FROM sprint_results WHERE season=?",
                             (self.year,)).fetchone()
        return float((r and r[0]) or 0) + float((s and s[0]) or 0)

    def finishes_through(self, driver, upto):
        """截至第 upto 站（含）的完賽名次分布 Counter。"""
        return Counter(pos for rnd, pos in self.round_finish[driver].items() if rnd <= upto)

    def _rival_future_rounds(self, other, rnd):
        """H6：對手在第 rnd 站之後**還可能出賽**的排程站次。

        預設＝剩餘全部排程站次（不看他之後實際有沒有出賽，那是事後之明）。唯一例外是
        SEASON_ENDING_EVENTS／FATAL_STATUSES 登記的「該站當下已身故／確定退出」，且只有在
        評估站次已經走到那一站（rnd ≥ end）才適用——rnd 更早時事件還沒發生，不得預知。
        """
        end = self.season_ending.get(other)
        stop = self.last_round + 1
        if end is not None and rnd >= end:
            stop = end
        return [f for f in range(rnd + 1, self.last_round + 1) if f < stop]

    def clinch(self, driver):
        """回 (clinch_round, remaining)：冠軍首次「保底積分壓過所有對手理論上限」的那一站。

        ⚠️ 三項具名假設（寫死在這裡，不要偷偷改）：
          1. （H6）對手上限用**剩餘排程站次**封頂；只有具名清單登記的「該站當下已身故／確定
             退出」自該站起不再計，且不得預知（rnd ＜ 該站時照樣全額封頂）。
          2. （H7）判準是 `floor >= 對手上限`：同分時比 countback。對手要追平上限就得把剩餘
             站次全拿，所以他的 countback 用**理論最佳**（現有分布＋每個剩餘站次各記一勝）；
             冠軍側用保底情境（此後不再得分＝現有分布）。完全同階＝分不出先後＝不算鎖定。
          3. 捨分季一律套當年 segments，不是純累加。
        """
        if not self.last_round or driver not in self.round_points:
            return None, None
        ceiling = self._ceiling()
        for rnd in range(1, self.last_round + 1):
            floor = self._segments(self.round_points[driver], rnd)
            champ_finishes = self.finishes_through(driver, rnd)
            if all(self._rival_settled(driver, floor, champ_finishes, other, rp, rnd, ceiling)
                   for other, rp in self.round_points.items() if other != driver):
                return rnd, self.last_round - rnd
        return None, None

    def _rival_settled(self, driver, floor, champ_finishes, other, rival_points, rnd, ceiling):
        """這名對手在第 rnd 站後是否已經追不上（含 H7 的同分 countback）。"""
        future = self._rival_future_rounds(other, rnd)
        hypo = {r: v for r, v in rival_points.items() if r <= rnd}
        for f in future:
            hypo[f] = ceiling
        best = self._segments(hypo)
        if floor > best:
            return True
        if floor < best:
            return False
        # 同分：對手要打到這個上限就得剩餘站次全勝，countback 用他的理論最佳分布比。
        rival_finishes = self.finishes_through(other, rnd)
        rival_finishes[1] += len(future)
        return self._countback_wins(champ_finishes, rival_finishes) is True

    @staticmethod
    def _countback_wins(a, b):
        """countback：依序比 1 勝數、2 名數…；True＝a 勝出、False＝敗、None＝完全同階。"""
        for pos in range(1, max(list(a) + list(b) + [0]) + 1):
            if a[pos] != b[pos]:
                return a[pos] > b[pos]
        return None

    def countback_beats(self, first, second):
        """countback：依序比 1 勝數、2 名數…；回 True＝first 勝出，False＝敗，None＝完全同階。"""
        return self._countback_wins(self.finishes[first], self.finishes[second])


# ---------- L0／L1／外部快照 provenance（H1-a、H1-c） ----------

def _approved_overrides(season):
    if not OVERRIDES_PATH.exists():
        return []
    blob = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    rows = blob.get("overrides", blob) if isinstance(blob, dict) else blob
    return [o for o in rows if o.get("by") == "charlie" and int(o.get("season", -1)) == int(season)]


_CROSSCHECK = None


def _crosscheck():
    global _CROSSCHECK
    if _CROSSCHECK is None:
        _CROSSCHECK = (json.loads(CROSSCHECK_PATH.read_text(encoding="utf-8"))
                       if CROSSCHECK_PATH.exists() else {"seasons": [], "diffs": []})
    return _CROSSCHECK


def _external_covered(season):
    return any(int(s.get("season", -1)) == int(season) for s in _crosscheck().get("seasons", []))


def _external_diffs(season):
    """回 {(table, entity_id, field): diff}——外部維基快照與 jolpica 不一致的欄位。"""
    out = {}
    for d in _crosscheck().get("diffs", []):
        if int(d.get("season", -1)) == int(season):
            out[(d["table"], d["entity_id"], d["field"])] = d
    return out


def _db_standings_value(con, table, season, entity_id, field):
    key = "driver_id" if table == "driver_standings" else "constructor_id"
    row = con.execute(f"SELECT {field} FROM {table} WHERE season=? AND {key}=?",
                      (season, entity_id)).fetchone()
    return row[0] if row else None


def check_l1_applied(con, season):
    """H1-a：db.sqlite 必須是 L1（已套 by=charlie 的裁決）。回 (errors, applied_desc)。"""
    errors, applied = [], []
    for item in _approved_overrides(season):
        table, field, entity = item["table"], item["field"], item["entity_id"]
        actual = _db_standings_value(con, table, int(item["season"]), entity, field)
        applied.append(f"{table}.{entity}.{field}={item['value']}（raw {item['raw_value']}）")
        if actual is None:
            errors.append(f"[{season}] 裁決覆寫的列在 db 找不到：{table} {entity} {field}")
        elif abs(float(actual) - float(item["value"])) > 1e-9:
            got = "L0 raw" if abs(float(actual) - float(item["raw_value"])) <= 1e-9 else repr(actual)
            errors.append(
                f"[{season}] 對帳器讀到的不是 L1：{table} {entity} {field}={got}，"
                f"應為裁決值 {item['value']}（先跑 build-f1-db.py 重建 db.sqlite）")
    return errors, applied


def _standings_reads(claim):
    """回這條 claim 會讀到的 standings 欄位 [(table, entity_id, field)]（供外部快照對照）。"""
    kind, reads = claim.get("kind"), []
    driver = claim.get("driver")
    if kind in {"champion_points", "runner_up_points"} and driver:
        reads += [("driver_standings", driver, "points"), ("driver_standings", driver, "position")]
    elif kind == "champion_wins" and driver:
        reads += [("driver_standings", driver, "wins"), ("driver_standings", driver, "position")]
    elif kind in {"driver_position", "career_titles"} and driver:
        reads.append(("driver_standings", driver, "position"))
    for d in claim.get("drivers", []) or []:
        reads += [("driver_standings", d, "points"), ("driver_standings", d, "position")]
    return reads


def check_external_corroboration(season, claims):
    """H1-c：claim 讀到的 standings 欄位若在維基快照有未解決的 diff → 判錯。"""
    if not _external_covered(season):
        return []
    diffs = _external_diffs(season)
    resolved = {(o["table"], o["entity_id"], o["field"]) for o in _approved_overrides(season)}
    errors, seen = [], set()
    for c in claims:
        for key in _standings_reads(c):
            if key in seen or key not in diffs or key in resolved:
                continue
            seen.add(key)
            d = diffs[key]
            errors.append(
                f"[{season}] 外部快照不符且無裁決覆寫：{key[0]} {key[1]}.{key[2]} "
                f"jolpica={d.get('jolpica')} wiki={d.get('wiki')} "
                f"（revid {d.get('source_revid')}；claim kind={c.get('kind')}）")
    return errors


# ---------- 每種 claim kind 的重查 ----------

def _q1(con, sql, args=()):
    row = con.execute(sql, args).fetchone()
    return row[0] if row else None


def verify_claim(con, claim, oracle=None):
    """回 (ok, actual, detail)。actual = 重查值；standings 型另與獨立重算 oracle 對照。"""
    kind = claim.get("kind")
    yr = claim["_season"]
    if oracle is None:
        oracle = SeasonOracle(con, yr)
    want = _num(claim["value"])

    def eq(actual):
        if actual is None:
            return False, actual
        return _num(actual) == want, _num(actual)

    if kind not in KNOWN_KINDS:
        return False, None, f"未知 kind：{kind}"
    # H2：實體綁定必填
    if kind in REQUIRE_DRIVER and not claim.get("driver"):
        return False, None, f"{kind} 缺 driver 欄位（實體綁定必填）"
    if kind in REQUIRE_CONSTRUCTOR and not claim.get("constructor"):
        return False, None, f"{kind} 缺 constructor 欄位（實體綁定必填）"
    if kind in REQUIRE_DRIVERS and len(claim.get("drivers") or []) < 2:
        return False, None, f"{kind} 需要 drivers 清單（至少兩人）"
    # 衍生統計紀律：「榜首＝冠軍」類聚合必先問「這季跑完沒」。
    if kind in SEASON_MUST_BE_COMPLETE and not oracle.complete:
        return False, None, f"{kind}：{yr} 賽季尚未跑完（榜首≠冠軍），這類 claim 不成立"

    if kind == "season_exists":
        return (*eq(_q1(con, "SELECT year FROM seasons WHERE year=?", (yr,))), "seasons.year")
    if kind == "earliest_season":
        return (*eq(_q1(con, "SELECT MIN(year) FROM seasons")), "MIN(seasons.year)")
    if kind == "earliest_race":
        first_season = _q1(con, "SELECT MIN(year) FROM seasons")
        if int(first_season or -1) != int(yr):
            return False, first_season, "本季不是最早賽季，撐不起「第一場比賽」"
        return (*eq(_q1(con, "SELECT MIN(round) FROM races WHERE season=?", (yr,))),
                "MIN(races.round) of earliest season")
    if kind == "season_rounds":
        return (*eq(_q1(con, "SELECT MAX(round) FROM races WHERE season=?", (yr,))), "MAX(races.round)")
    if kind in {"champion_points", "runner_up_points", "champion_wins"}:
        pos = 1 if kind != "runner_up_points" else 2
        field = "wins" if kind == "champion_wins" else "points"
        row = con.execute(f"SELECT {field}, driver_id FROM driver_standings "
                          "WHERE season=? AND position=?", (yr, pos)).fetchone()
        ok, actual = eq(row[0] if row else None)
        did = row[1] if row else None
        if did != claim["driver"]:
            return False, {"value": actual, "driver": did}, \
                f"driver_standings P{pos} 的車手是 {did}，pack 寫 {claim['driver']}"
        # H1-b：獨立重算對照
        recomputed = oracle.wins(did) if kind == "champion_wins" else oracle.points(did)
        if recomputed is None or _num(recomputed) != _num(actual):
            return False, {"standings": actual, "recomputed": recomputed}, \
                (f"standings 與逐站重算不符（{did} {field}：standings={actual}、"
                 f"results 重算={recomputed}）")
        if oracle.rank(did) != pos:
            return False, {"standings_position": pos, "recomputed_position": oracle.rank(did)}, \
                f"順位與重算不符（{did} 重算為 P{oracle.rank(did)}）"
        return ok, {"value": actual, "driver": did, "recomputed": recomputed}, \
            f"driver_standings P{pos} {field}＋逐站重算"
    if kind == "driver_position":
        did = claim["driver"]
        if did in oracle.excluded:
            return False, None, f"{did} 在 {yr} 遭年度除名（position_text='D'），沒有年度順位可宣稱"
        got = _q1(con, "SELECT position FROM driver_standings WHERE season=? AND driver_id=?", (yr, did))
        ok, actual = eq(got)
        if ok and oracle.rank(did) != want:
            return False, {"standings": actual, "recomputed": oracle.rank(did)}, \
                f"順位與逐站重算不符（{did} 重算為 P{oracle.rank(did)}）"
        return ok, actual, f"driver_standings position {did}＋重算"
    if kind == "driver_podiums":
        did = claim["driver"]
        return (*eq(_q1(con, "SELECT COUNT(*) FROM results WHERE season=? AND driver_id=? "
                             "AND position_text IN ('1','2','3')", (yr, did))), f"COUNT podiums {did}")
    if kind == "race_finish_position":
        did, rnd = claim["driver"], claim.get("round")
        if rnd in (None, "final"):
            rnd = oracle.last_round
        got = _q1(con, "SELECT position_text FROM results WHERE season=? AND round=? AND driver_id=?",
                  (yr, int(rnd), did))
        if got is None or not str(got).isdigit():
            return False, got, f"{did} 在 R{rnd} 無完賽名次（position_text={got!r}）"
        return (*eq(int(got)), f"results R{rnd} {did} position_text")
    if kind == "constructor_wins":
        cid = claim["constructor"]
        return (*eq(_q1(con, "SELECT COUNT(*) FROM results WHERE season=? AND constructor_id=? "
                             "AND position_text='1'", (yr, cid))), f"COUNT wins {cid}")
    if kind == "no_constructor_championship":
        return (*eq(_q1(con, "SELECT COUNT(*) FROM constructor_standings WHERE season=?", (yr,))),
                "COUNT constructor_standings")
    if kind in {"clinch_round", "clinch_remaining", "clinch_from_end"}:
        rnd, rem = oracle.clinch(claim["driver"])
        if rnd is None:
            return False, None, "無法算出 clinch（該車手無逐站資料）"
        actual = {"clinch_round": rnd, "clinch_remaining": rem,
                  "clinch_from_end": oracle.last_round - rnd + 1}[kind]
        return (*eq(actual), f"{kind}（捨分規則＋剩餘排程站次封頂＋同分 countback）")
    if kind == "rank_before_final":
        did = claim["driver"]
        if oracle.last_round < 2:
            return False, None, "賽季不足兩站，無末站前排名"
        got = oracle.rank_through(oracle.last_round - 1).get(did)
        return (*eq(got), f"末站前累計排名 {did}")
    if kind == "career_titles":
        did = claim["driver"]
        return (*eq(_q1(con, "SELECT COUNT(*) FROM driver_standings "
                             "WHERE driver_id=? AND position=1 AND season<=?", (did, yr))),
                f"生涯冠軍季數 {did}（≤{yr}）")
    if kind == "tied_before_final":
        vals = [_num(oracle._segments(oracle.round_points[d], oracle.last_round - 1))
                for d in claim["drivers"]]
        ok = all(v == want for v in vals) and len(set(vals)) == 1
        return ok, vals, "末站前累計積分（捨分規則）"
    if kind == "tied_position":
        rows = {d: con.execute("SELECT position, points FROM driver_standings "
                               "WHERE season=? AND driver_id=?", (yr, d)).fetchone()
                for d in claim["drivers"]}
        if any(r is None for r in rows.values()):
            return False, rows, "有車手不在 driver_standings"
        positions = {d: r[0] for d, r in rows.items()}
        points = {d: _num(r[1]) for d, r in rows.items()}
        if len(set(points.values())) != 1:
            return False, points, "宣稱並列但積分不同"
        if set(positions.values()) != {want}:
            return False, positions, \
                (f"宣稱並列第 {want} 但正式順位是 {positions}"
                 "（同分時本站資料採循序位，不是共享位）")
        return True, positions, "tied_position（同分且同順位）"
    if kind == "countback_order":
        order = claim["drivers"]
        rows = {d: con.execute("SELECT position, points FROM driver_standings "
                               "WHERE season=? AND driver_id=?", (yr, d)).fetchone()
                for d in order}
        if any(r is None for r in rows.values()):
            return False, rows, "有車手不在 driver_standings"
        points = {d: _num(rows[d][1]) for d in order}
        positions = {d: rows[d][0] for d in order}
        if len(set(points.values())) != 1:
            return False, points, "countback_order 只適用同分；這些車手積分不同"
        expected = list(range(want, want + len(order)))
        if [positions[d] for d in order] != expected:
            return False, positions, f"順位不是宣稱的 {expected}"
        for first, second in zip(order, order[1:]):
            beats = oracle.countback_beats(first, second)
            if beats is None:
                return False, positions, f"{first} 與 {second} 的完賽名次分布完全相同，countback 分不出先後"
            if not beats:
                return False, positions, f"countback 重算顯示 {second} 應排在 {first} 之前"
            if oracle.rank(first) >= oracle.rank(second):
                return False, {"recomputed": {d: oracle.rank(d) for d in order}}, "重算排名與宣稱順序不符"
        return True, positions, "countback_order（同分＋countback 重算解釋得出順序）"
    return False, None, f"未處理 kind：{kind}"


# ---------- 位置綁定（H3／H4） ----------

def _anchor_spans(text, claims):
    """回 [(start, end, claim)]：每條 claim 的每個 anchor 在正文中的所有出現位置。"""
    spans, errors = [], []
    for c in claims:
        for anchor in c.get("anchors") or []:
            if not anchor:
                continue
            hits = [m.start() for m in re.finditer(re.escape(anchor), text)]
            if not hits:
                errors.append(f"anchor 在正文找不到（claim kind={c.get('kind')}）：{anchor!r}")
            for start in hits:
                spans.append((start, start + len(anchor), c))
    return spans, errors


def check_bindings(year, text, verified, ok_claims, pack):
    """H3＋H4：正文每個數字／順位詞都要被 anchor 綁到通過重查的 claim。"""
    errors = []
    spans, anchor_errors = _anchor_spans(text, verified)
    errors += [f"[{year}] {e}" for e in anchor_errors]
    allow_tokens = set(pack.get("non_statistical_tokens") or [])

    def covering(start, end):
        return [c for s, e, c in spans if s <= start and end <= e]

    # (H3) 數字位置綁定
    for start, end, value, holder in number_occurrences(text):
        if holder is not None:
            if holder not in allow_tokens:
                errors.append(
                    f"[{year}] 數字 {value} 夾在 token {holder!r} 裡（型號／名稱，不是統計值）："
                    f"要嘛改寫，要嘛在 facts pack 的 non_statistical_tokens 具名列出")
            continue
        cover = covering(start, end)
        if not cover:
            errors.append(f"[{year}] 數字 {value}（位置 {start}）沒有任何 claim 的 anchor 綁定"
                          f"：{text[max(0, start - 8):end + 8]!r}")
            continue
        for c in cover:
            if _num(c["value"]) != value:
                errors.append(f"[{year}] 數字 {value} 綁到值為 {c['value']} 的 claim"
                              f"（kind={c.get('kind')}）：anchor 圈錯範圍")
            elif c not in ok_claims:
                errors.append(f"[{year}] 數字 {value} 綁到未通過重查的 claim（kind={c.get('kind')}）")

    # (H4) 順位詞綁定
    for start, end, raw, value, modifier in ordinal_occurrences(text):
        cover = covering(start, end)
        if not cover:
            errors.append(f"[{year}] 順位詞 {raw!r} 沒有 claim 的 anchor 綁定"
                          f"（順位必須綁到 standings／完賽名次查詢）")
            continue
        for c in cover:
            kind = c.get("kind")
            if modifier == "倒數":
                allowed = FROM_END_KINDS
            elif modifier in {"並列", "同列"}:
                allowed = TIE_ORDINAL_KINDS
            else:
                allowed = ORDINAL_KINDS
            if kind not in allowed:
                errors.append(f"[{year}] 順位詞 {raw!r} 綁到 kind={kind}，"
                              f"該修飾語只接受 {sorted(allowed)}")
            elif _num(c["value"]) != value:
                errors.append(f"[{year}] 順位詞 {raw!r} 綁到值為 {c['value']} 的 claim（kind={kind}）")
            elif c not in ok_claims:
                errors.append(f"[{year}] 順位詞 {raw!r} 綁到未通過重查的 claim（kind={kind}）")

    # (H4) 同分字眼必須有 tie 型 claim
    hit_words = [w for w in TIE_WORDS if w in text]
    if hit_words and not any(c.get("kind") in TIE_KINDS for c in ok_claims):
        errors.append(f"[{year}] 正文出現同分字眼 {hit_words}，但 facts pack 沒有任何通過重查的 "
                      f"tie 型 claim（{sorted(TIE_KINDS)}）")
    return errors


# ---------- 單篇對帳 ----------

def check_year(year: int, con):
    """回 list[str] 錯誤訊息（空＝全綠）。"""
    errors = []
    md = CONTENT / f"{year}.md"
    facts = CONTENT / f"{year}.facts.json"
    if not md.exists():
        return [f"[{year}] 缺導言檔 {md.relative_to(ROOT)}"]
    if not facts.exists():
        return [f"[{year}] 缺 facts pack {facts.relative_to(ROOT)}"]

    text = md.read_text(encoding="utf-8")
    pack = json.loads(facts.read_text(encoding="utf-8"))
    claims = pack.get("claims", [])
    season = int(pack.get("season", year))

    # 字數檢查（120–200，含標點；不計 ASCII 空白＝盤古之白/千分位空格）
    char_n = len(text.strip().replace(" ", ""))
    if not (120 <= char_n <= 200):
        errors.append(f"[{year}] 導言字數 {char_n} 不在 120–200（含標點、不計盤古之白）")

    verified = [{**c, "_season": season} for c in claims if c.get("verified") is True]
    value_set = {_num(c["value"]) for c in verified}

    # (H1-a) db 必須是 L1
    l1_errors, _applied = check_l1_applied(con, season)
    errors += l1_errors

    # (1) 值集合成員（v1 的舊層，保留：anchor 綁定是額外一層，不取代）
    for n in extract_numbers(text):
        if n not in value_set:
            errors.append(f"[{year}] 裸奔數字 {n}：未對應任何 verified claim（值集合 {sorted(value_set, key=str)}）")

    # (2) verified claim 重查（含 H2 實體必填、H1-b 獨立重算）
    oracle = SeasonOracle(con, season)
    # (H5) default-deny：standings 出現不認得的 position_text 標記 → 判錯，不准默默當一般車手
    for did, ptext in oracle.unknown_markers:
        errors.append(f"[{year}] driver_standings 有不認得的 position_text 標記：{did}={ptext!r}"
                      f"（認得的：數字、{UNRANKED_POSITION_TEXT!r}、"
                      f"{sorted(EXCLUDED_POSITION_TEXTS)}；要嘛具名納入、要嘛修資料）")
    ok_claims = []
    for c in verified:
        try:
            ok, actual, detail = verify_claim(con, c, oracle)
        except Exception as e:  # noqa: BLE001
            errors.append(f"[{year}] claim kind={c.get('kind')} 重查失敗：{e}")
            continue
        if ok:
            ok_claims.append(c)
        else:
            errors.append(f"[{year}] claim kind={c.get('kind')} value={c['value']} "
                          f"與重查不符（{detail}＝{actual}）")

    # (H1-c) 外部快照對照
    errors += check_external_corroboration(season, verified)

    # (H3／H4) 位置綁定
    errors += check_bindings(year, text, verified, ok_claims, pack)
    return errors


def season_notes(con, year):
    """回該季的 provenance 標註字串 list（印在報告裡，讓「哪些季被覆寫過」看得見）。"""
    notes = []
    applied = _approved_overrides(year)
    if applied:
        notes.append(f"裁決覆寫 {len(applied)} 筆："
                     + "／".join(f"{o['entity_id']}.{o['field']} {o['raw_value']}→{o['value']}"
                                 for o in applied))
    notes.append("外部快照已覆蓋" if _external_covered(year) else "⚠ 無外部快照（standings 單一來源）")
    oracle = SeasonOracle(con, year)
    if not oracle.has_scoring_rule:
        notes.append("無捨分規則登記（重算採全站累加）")
    if oracle.excluded:
        notes.append("年度除名（不佔年度順位）：" + "／".join(sorted(oracle.excluded)))
    if oracle.season_ending:
        notes.append("clinch 具名例外（自該站起不再計）："
                     + "／".join(f"{d} R{r}" for d, r in sorted(oracle.season_ending.items())))
    return notes


# ---------- scaffold（產 anchor 骨架，供 facts pack 遷移／新篇撰寫） ----------

def scaffold(year, con):
    md, facts = CONTENT / f"{year}.md", CONTENT / f"{year}.facts.json"
    if not md.exists() or not facts.exists():
        print(f"[{year}] 缺檔，略過")
        return
    text = md.read_text(encoding="utf-8")
    pack = json.loads(facts.read_text(encoding="utf-8"))
    verified = [{**c, "_season": int(pack.get("season", year))}
                for c in pack.get("claims", []) if c.get("verified") is True]
    spans, _ = _anchor_spans(text, verified)
    print(f"── {year} ──")
    for start, end, value, holder in number_occurrences(text):
        if holder or any(s <= start and end <= e for s, e, _ in spans):
            continue
        cands = [c.get("kind") for c in verified if _num(c["value"]) == value] or ["（無同值 claim）"]
        print(f"  數字 {value}  建議 anchor {text[max(0, start - 6):end + 4]!r}  候選 kind={cands}")
    for start, end, raw, value, modifier in ordinal_occurrences(text):
        if any(s <= start and end <= e for s, e, _ in spans):
            continue
        print(f"  順位 {raw!r} (value={value}, modifier={modifier})  "
              f"建議 anchor {text[max(0, start - 4):end + 6]!r}")


def main(argv):
    do_scaffold = "--scaffold" in argv
    argv = [a for a in argv if a != "--scaffold"]
    if not DB_PATH.exists():
        print(f"❌ 找不到 {DB_PATH}（先跑 build-f1-db.py）")
        return 1
    if argv:
        years = [int(a) for a in argv]
    else:
        years = sorted(int(p.stem) for p in CONTENT.glob("*.md") if p.stem.isdigit())
    if not years:
        print("（content/seasons/ 無導言檔，略過）")
        return 0

    con = sqlite3.connect(DB_PATH)
    if do_scaffold:
        for y in years:
            scaffold(y, con)
        con.close()
        return 0

    all_errors = []
    print("賽季導言機械對帳（v3：L1 斷言＋逐站重算＋外部快照＋位置綁定＋並列驗證＋除名建模＋無事後之明 clinch）：")
    for y in years:
        errs = check_year(y, con)
        notes = "；".join(season_notes(con, y))
        if errs:
            all_errors += errs
            print(f"  ✗ {y}：{len(errs)} 項不符  [{notes}]")
        else:
            print(f"  ✓ {y}：全綠  [{notes}]")
    con.close()

    if all_errors:
        print("\n對帳失敗：")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    print(f"\n共 {len(years)} 篇導言全綠。⚠️ 全綠只代表數字與順位兩層沒抓到錯，"
          f"非數字語意主張仍須對抗式人工查核。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
