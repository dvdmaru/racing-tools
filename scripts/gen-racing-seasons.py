#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-racing-seasons.py — 百科線 M3：/seasons/（77 季索引）＋ /seasons/2002/（單一賽季頁，定調用）。

server-rendered、零 client fetch（除 page_shell 既有 theme init inline script 外零 JS）；
tabs 一律走 racinglib 的 CSS-only tabgroup。實體專屬視覺（stat 卡、賽季弧線、退賽橫條圖、
「怎麼算的」展開、pair 中英對照）沿用 Phase 0 原型（gen-racing-entities-phase0.py），
直接 import 重用，不複製、不改動 phase0（它還要跑出互連的另一端 /drivers/、/constructors/）。

★ 衍生數字紀律（承 f1stats 圓桌教訓）：每個統計 value == len(detail)，或直接取自官方
  standings（SOURCED）。只做加減可驗的衍生（分差、退賽數）——不做「封王站/clinch」類複雜衍生。
  分差 = 兩個 SOURCED 積分之差，附「怎麼算的」展開回指兩列 standings。

★ 譯名誠實 fallback：譯名只准來自 driver-zh.json／team-zh.json（racinglib 載入）＋ Phase 0
  已核准 8 實體（phase0 ZH dict）。查無譯名 → 只留原文（照 phase0 pair()）。嚴禁自譯人名/隊名。
  退賽 status 的中文只是「共通名詞 gloss」（引擎/碰撞…）且一律並列原文；status 原文在明細中
  逐字呈現、不直譯因果（不把「Engine」寫成「引擎爆缸導致退賽」）。

★ JSON-LD 型別選擇（賽季頁）：採「每站一個 top-level SportsEvent 節點」，不採「整季一個
  SportsEvent」也不採「ItemList 包 SportsEvent」。理由：
  (1) 每場大獎賽是單一場地、單一日期的真實事件，1:1 對映 SportsEvent 的必填 startDate +
      location(Place+geo)，Google Event/SportsEvent rich result 能直接解析每一站；
  (2) 「整季一個 SportsEvent」會被迫給一個橫跨十餘國、數月的單一 location/startDate——那是
      捏造，違反誠實紀律，故棄用；
  (3) top-level 節點（而非塞進 ItemList.itemListElement）因為 Google 的 Event 解析器辨識
      獨立 Event 節點、卻不會從 ItemList 內抽取 event，top-level 讓每站都具 rich-result 資格；
  (4) 座標僅在 raw schedule 的 Circuit.Location 有 lat/long 時輸出，沒有就不放（不假裝）；
  (5) 全部與 org/website/CollectionPage/breadcrumb 掛在共用 @graph。sameAs 放維基、不放 image、
      不放任何官方素材連結。
  索引頁則用 ItemList（導覽型清單語意較貼切；每項 url 只填已存在的頁）。

★ sitemap part（M0 manifest 機制）：owner=seasons，但 **M3 預設不寫**——頁面未公開前 sitemap
  不得出現這些 URL（避免 GSC 抓到尚未定調的頁）。只有 --publish 才寫 data/sitemap-parts/seasons.txt；
  --no-sitemap 為顯式關閉（與預設同義，供 pipeline 明示用）。

用法：
  python3 scripts/gen-racing-seasons.py                 # 索引 + 2002 賽季頁（不寫 sitemap）
  python3 scripts/gen-racing-seasons.py --season 2002   # 同上，明示賽季
  python3 scripts/gen-racing-seasons.py --index-only     # 只重建索引
  python3 scripts/gen-racing-seasons.py --publish        # 公開時才加：寫 sitemap part
"""
import argparse
import hashlib
import html as html_lib
import importlib.util
import json
import math
import pathlib
import re
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rc = _load("racinglib", "racinglib.py")
fs = _load("f1stats", "f1stats.py")
# Phase 0 當視覺元件庫用：import 只載模組（main 在 __main__ 下不執行），不寫任何檔、不改 phase0
p0 = _load("gen_racing_entities_phase0", "gen-racing-entities-phase0.py")

RAW = ROOT / "data" / "f1" / "raw"
PUB = rc.PUB
BASE = rc.BASE
esc = html_lib.escape

FIRST_YEAR, LAST_YEAR = 1950, rc.SEASON  # 1950–2026

# ---------- 譯名解析（誠實 fallback；phase0 8 實體 overlay 在 racinglib 表之上） ----------
_P0_DRIVER_ZH = {k: v for k, v in p0.ZH.items()
                 if k in ("michael_schumacher", "hamilton", "senna", "max_verstappen")}
_P0_TEAM_ZH = {k: v for k, v in p0.ZH.items()
               if k in ("ferrari", "mclaren", "mercedes", "red_bull")}
DRIVER_ZH = {**rc.DRIVER_ZH, **_P0_DRIVER_ZH}
TEAM_ZH_BY_ID = {**{k: v for k, v in rc.TEAM_ZH.items()}, **_P0_TEAM_ZH}


def zh_driver(did):
    return DRIVER_ZH.get(did)  # None → 誠實只留原文


def zh_team(cid, name):
    return TEAM_ZH_BY_ID.get(cid) or rc.TEAM_ZH.get(name)


def _driver_full(drv):
    return f'{drv.get("givenName", "")} {drv.get("familyName", "")}'.strip()


def driver_pair(drv):
    """車手中英對照 html（phase0 pair：zh 缺就只留原文的 en-only span）。"""
    return p0.pair(zh_driver(drv.get("driverId", "")), _driver_full(drv))


def team_pair(cid, name):
    return p0.pair(zh_team(cid, name), name)


def name_plain(zh, en):
    """敘事句用的純文字姓名：有譯名 → 「譯名（原文）」，無 → 只原文。"""
    return f"{zh}（{en}）" if zh else en


# ---------- 資料讀取 ----------

def _load_json(p):
    return p0._load(p)


def _driver_standings(year):
    p = RAW / "standings" / f"driver-{year}.json"
    return _load_json(p).get("DriverStandings", []) if p.exists() else []


def _constructor_standings(year):
    p = RAW / "standings" / f"constructor-{year}.json"
    return _load_json(p).get("ConstructorStandings", []) if p.exists() else []


def _schedule(year):
    p = RAW / f"season-{year}-schedule.json"
    return _load_json(p).get("Races", []) if p.exists() else []


def _season_rounds(year):
    """分站數 = standings 檔的 round 欄（該季最終站次，SOURCED）；抓不到退回 schedule 長度。"""
    p = RAW / "standings" / f"driver-{year}.json"
    if p.exists():
        r = _load_json(p).get("round")
        if r:
            return int(r)
    return len(_schedule(year))


def _sprint_results(year, rnd):
    """該站衝刺賽賽果（若資料源有；2002 無 → 空 list）。納入累計積分／車隊拆解以求通用。

    ⚠️ 路徑＝data/f1/raw/sprint/<year>-<rnd>.json（不是 results/sprint/）。2002 無 sprint 故
    舊路徑筆誤長期潛伏；2021 起 sprint 季若漏掉這批分，冠軍之爭累計圖終點會對不上官方積分
    而被硬 gate 誤判成 dropped-scores（實測 2021–2026 全因此假陰性）——修正後 sprint 季 gate 過。"""
    p = RAW / "sprint" / f"{year}-{rnd:02d}.json"
    if p.exists():
        d = _load_json(p)
        return d.get("SprintResults") or d.get("Results", [])
    return []


def _fmt(v):
    """積分顯示：整數不帶小數（77.0 → 77）；非整數保留最短表示（1950s 共駕 .5 分照實呈現）。"""
    f = float(v)
    return str(int(f)) if f.is_integer() else f"{f:g}"


def _num(v):
    """數值正規化：整值回 int（144.0→144）、非整值回 float（71.5）。
    1950s 共駕與 1984 等半分年代積分帶 .5，一律不得 int() 硬轉（會 ValueError 或抹掉半分）。"""
    f = float(v)
    return int(f) if f.is_integer() else f


# ---------- 冠軍之爭：前三名逐站累計積分（含硬 gate：終點必等官方最終積分） ----------

def cumulative_leaders(year, top_n=3):
    """回 (leaders, ok)。leaders = 最終積分榜前 top_n 車手，各帶逐站累計積分 series。

    累計來源：逐站 raw results 的 points 欄累加（若有 sprint_results 一併納入，通用性）。
    ok（自我 oracle 硬 gate）：每條線最後一點恰等於官方最終積分榜該車手 points 才 True——
    dropped-scores（best-N 記分）年代逐站累計 ≠ 官方積分，任一條對不上 → ok=False → 不畫圖。
    """
    ds = _driver_standings(year)
    top = ds[:top_n]
    ids = [e["Driver"].get("driverId", "") for e in top]
    idset = set(ids)
    rounds = _season_rounds(year)
    cum = {i: 0.0 for i in ids}
    series = {i: [] for i in ids}
    for rnd in range(1, rounds + 1):
        rp = RAW / "results" / f"{year}-{rnd:02d}.json"
        if rp.exists():
            for res in _load_json(rp).get("Results", []):
                did = res.get("Driver", {}).get("driverId")
                if did in idset:
                    cum[did] += float(res.get("points") or 0)
        for sres in _sprint_results(year, rnd):
            did = sres.get("Driver", {}).get("driverId")
            if did in idset:
                cum[did] += float(sres.get("points") or 0)
        for i in ids:
            series[i].append((rnd, cum[i]))
    leaders, ok = [], True
    for e in top:
        did = e["Driver"].get("driverId", "")
        official = _num(e["points"])  # 半分年代（1975/1984/2021…）不得 int() 硬轉
        final = series[did][-1][1] if series[did] else 0.0
        if abs(final - float(official)) > 1e-9:
            ok = False  # 硬 gate：逐站累計對不上官方積分（best-N 年代）
        drv = e["Driver"]
        leaders.append({
            "driver_id": did, "zh": zh_driver(did), "en": _driver_full(drv),
            "family": drv.get("familyName", ""), "official": official,
            "series": series[did], "final": final,
        })
    return leaders, ok


# ---------- 車隊積分拆解：各車手 results+sprint 積分加總（Σ gate：==官方車隊積分才顯示） ----------

def constructor_breakdowns(year):
    """回 dict[constructorId] -> {parts:[{driver_id,zh,en,family,points}], sum, official, ok}。

    parts = 該季效力該隊全部車手、各自 results（+sprint 若有）積分加總，人多至少排序。
    ok = Σ(parts) 恰等官方車隊積分。1958–78「只計最佳車等」年代對不上 → ok=False → 不顯示拆解
    （官方車隊分與逐車手加總不同義，硬湊會捏造）。2002 全 11 隊應皆 ok。
    """
    cs = _constructor_standings(year)
    official = {r["Constructor"]["constructorId"]: _num(r["points"]) for r in cs}
    rounds = _season_rounds(year)
    agg = defaultdict(lambda: defaultdict(float))
    drv_obj = {}

    def _accum(res):
        cid = res.get("Constructor", {}).get("constructorId")
        drv = res.get("Driver", {})
        did = drv.get("driverId")
        if cid and did:
            agg[cid][did] += float(res.get("points") or 0)
            drv_obj.setdefault(did, drv)

    for rnd in range(1, rounds + 1):
        rp = RAW / "results" / f"{year}-{rnd:02d}.json"
        if rp.exists():
            for res in _load_json(rp).get("Results", []):
                _accum(res)
        for sres in _sprint_results(year, rnd):
            _accum(sres)
    out = {}
    for cid, drs in agg.items():
        total = sum(drs.values())
        off = official.get(cid)
        ok = off is not None and abs(total - float(off)) < 1e-9
        parts = []
        for did, pts in sorted(drs.items(), key=lambda x: (-x[1], x[0])):
            drv = drv_obj.get(did, {})
            parts.append({"driver_id": did, "zh": zh_driver(did), "en": _driver_full(drv),
                          "family": drv.get("familyName", ""), "points": pts})
        out[cid] = {"parts": parts, "sum": total, "official": off, "ok": ok}
    return out


def _nice_ticks(maxv):
    """回 (step, top)：y 軸整數刻度間距與頂值，取 3–5 段（0／50／100／150 這類）。"""
    for step in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        top = math.ceil(maxv / step) * step if maxv > 0 else step
        if 3 <= top / step <= 5:
            return step, top
    step = 1000
    return step, math.ceil(max(maxv, 1) / step) * step


# ---------- 索引頁資料列（進行中賽季不顯示冠軍——踩過把榜首當冠軍的錯） ----------

def index_row(year):
    """回一季的索引資料。未完賽（fs._is_completed=False）→ champion 一律 None、in_progress=True。"""
    completed = fs._is_completed(year)
    ds = _driver_standings(year)
    cs = _constructor_standings(year)
    # 進行中賽季：rounds 是「已完成站次」不是全季總站數（查核桌 T-01）——
    # 另帶 scheduled 供索引頁顯示「10 / 22」，避免讀者把已跑站次誤讀為全季分站數。
    row = {"year": year, "rounds": _season_rounds(year),
           "scheduled": len(_schedule(year)),
           "in_progress": not completed,
           "driver_champ": None, "constructor_champ": None}
    if completed:
        if ds:
            d = ds[0]["Driver"]
            row["driver_champ"] = {"id": d.get("driverId", ""), "zh": zh_driver(d.get("driverId", "")),
                                   "en": _driver_full(d), "drv": d}
        if cs:
            c = cs[0]["Constructor"]
            row["constructor_champ"] = {"id": c.get("constructorId", ""),
                                        "zh": zh_team(c.get("constructorId", ""), c.get("name", "")),
                                        "en": c.get("name", "")}
    return row


# ---------- 退賽原因分布（§8-3；value == len(detail) 紀律） ----------

def is_finisher(status):
    """完賽判定：status 為 'Finished' 或 '+N Lap(s)'（落後圈數完賽）為完賽；其餘皆算未完賽。"""
    return status == "Finished" or bool(re.match(r"^\+\d+ Lap", status))


# status → 共通名詞 gloss（不是因果直譯；label 一律並列原文，明細逐字呈現 status 原文）
STATUS_ZH = {
    "Engine": "引擎", "Collision": "碰撞", "Spun off": "打滑失控", "Hydraulics": "液壓",
    "Gearbox": "變速箱", "Suspension": "懸吊", "Accident": "事故", "Brakes": "煞車",
    "Mechanical": "機械", "Transmission": "傳動", "Electrical": "電路", "Clutch": "離合器",
    "Driveshaft": "傳動軸", "Throttle": "節氣門", "Disqualified": "取消資格",
    "Overheating": "過熱", "Power loss": "動力流失", "Exhaust": "排氣", "Rear wing": "尾翼",
    "Safety": "安全考量", "Broken wing": "尾翼損壞", "Fuel": "燃油", "Wheel rim": "輪圈",
    "Fuel pressure": "燃油壓力", "Oil pressure": "機油壓力", "Wheel": "輪組",
    "Electronics": "電子系統", "Drivetrain": "動力傳動", "Ignition": "點火", "Injury": "傷勢",
    "Chassis": "底盤", "Steering": "轉向", "Injured": "傷勢",
    # 近代賽果登記事由（2020s 資料源用語）：Retired＝退賽、Did not start＝未發車、
    # Lapped＝落後圈數（此 gloss 僅用於「未列入完賽名次」的落圈退賽者，見 is_classified 註）。
    "Retired": "退賽", "Did not start": "未發車", "Lapped": "落後圈數",
    "Withdrew": "退出", "Did not qualify": "未通過排位", "Not classified": "未列名次",
}


def season_retirements(year):
    """回退賽分類 [{status, zh, value(=len detail), detail:[{round,race,driver_id,driver}]}]，
    人次由多至少排序。value 一律 len(detail)，總數 = 各類 value 加總。"""
    sched_name = {int(r["round"]): r["raceName"] for r in _schedule(year)}
    buckets = {}
    for rnd in range(1, _season_rounds(year) + 1):
        rp = RAW / "results" / f"{year}-{rnd:02d}.json"
        if not rp.exists():
            continue
        data = _load_json(rp)
        race_name = data.get("raceName") or sched_name.get(rnd, f"Round {rnd}")
        for res in data.get("Results", []):
            status = res.get("status", "")
            if is_finisher(status):
                continue
            drv = res.get("Driver", {})
            buckets.setdefault(status, []).append({
                "round": rnd, "race": race_name,
                "driver_id": drv.get("driverId", ""), "driver": _driver_full(drv),
                "source": f"data/f1/raw/results/{year}-{rnd:02d}.json",
            })
    cats = [{"status": s, "zh": STATUS_ZH.get(s), "value": len(d), "detail": d}
            for s, d in buckets.items()]
    cats.sort(key=lambda c: (-c["value"], c["status"]))
    return cats


# ---------- 分差（SOURCED − SOURCED，附回指） ----------

def points_gap(year):
    """回 (champ_pts, second_pts, gap)；gap = 冠軍積分 − 第二名積分（兩列 standings 之差）。"""
    ds = _driver_standings(year)
    if len(ds) < 2:
        return (_num(ds[0]["points"]) if ds else 0, 0, 0)
    champ = _num(ds[0]["points"])
    second = _num(ds[1]["points"])
    return champ, second, _num(champ - second)  # 1984：72 − 71.5 ＝ 0.5，不得抹成整數


# ---------- 規則化敘事句（模板 + 資料，非 LLM；每個數字都能在頁面明細找到） ----------

def season_narrative(year):
    """回 list[str] 純文字敘事句。名字用「譯名（原文）」或只原文（誠實 fallback）。

    進行中賽季（fs._is_completed=False）：一律進行時態、榜首＝「暫居」而非「奪冠」、
    末句標「賽季進行中・每週自動更新」；不得出現「奪下世界冠軍」「累計積分」等已定案語。
    無車隊榜的年代（<1958）：略過車隊句（誠實不寫不存在的錦標賽）。"""
    ds = _driver_standings(year)
    cs = _constructor_standings(year)
    rounds = _season_rounds(year)
    champ_pts, second_pts, gap = points_gap(year)
    in_progress = not fs._is_completed(year)
    cd = ds[0]["Driver"] if ds else {}
    champ_name = name_plain(zh_driver(cd.get("driverId", "")), _driver_full(cd))
    lines = []

    if in_progress:
        scheduled = len(_schedule(year))
        if len(ds) >= 2:
            sd = ds[1]["Driver"]
            second_name = name_plain(zh_driver(sd.get("driverId", "")), _driver_full(sd))
            lines.append(
                f"{year} 賽季進行中，全季排定 {scheduled} 站、目前已完成 {rounds} 站。"
                f"{champ_name} 以 {champ_pts} 分暫居車手積分榜首，"
                f"領先第二名 {second_name} {gap} 分（榜首＝目前領先，非冠軍）。")
        elif ds:
            lines.append(
                f"{year} 賽季進行中，全季排定 {scheduled} 站、目前已完成 {rounds} 站，"
                f"目前由 {champ_name}（{champ_pts} 分）暫居車手積分榜首。")
        if len(ds) >= 3:
            s2, s3 = ds[1]["Driver"], ds[2]["Driver"]
            s2n = name_plain(zh_driver(s2.get("driverId", "")), _driver_full(s2))
            s3n = name_plain(zh_driver(s3.get("driverId", "")), _driver_full(s3))
            lines.append(
                f"目前積分榜第二名為 {s2n}（{ds[1]['points']} 分）、"
                f"第三名 {s3n}（{ds[2]['points']} 分）。")
        if cs:
            cc = cs[0]["Constructor"]
            cid = cc.get("constructorId", "")
            cons_name = name_plain(zh_team(cid, cc.get("name", "")), cc.get("name", ""))
            lines.append(f"車隊積分榜目前由 {cons_name}（{cs[0]['points']} 分）暫居第一。")
        cats = season_retirements(year)
        total_ret = sum(c["value"] for c in cats)
        if cats:
            top = cats[0]
            top_label = name_plain(top["zh"], top["status"])
            lines.append(
                f"至今全季正賽共 {total_ret} 人次未完賽（完賽名次為 Finished 或落後圈數者不計），"
                f"其中登記事由為「{top_label}」者 {top['value']} 次為最多。")
        lines.append("本賽季尚未結束，以上為目前官方積分榜與賽果快照，賽季進行中・每週自動更新。")
        return lines

    if len(ds) >= 2:
        sd = ds[1]["Driver"]
        second_name = name_plain(zh_driver(sd.get("driverId", "")), _driver_full(sd))
        lines.append(
            f"{year} 賽季共 {rounds} 站。{champ_name} 以 {champ_pts} 分奪下車手世界冠軍，"
            f"領先第二名 {second_name} {gap} 分。")
    elif ds:
        lines.append(f"{year} 賽季共 {rounds} 站，車手世界冠軍為 {champ_name}（{champ_pts} 分）。")
    # 冠軍之爭補句：積分榜第二、第三名（名字照譯名紀律 fallback）
    if len(ds) >= 3:
        s2, s3 = ds[1]["Driver"], ds[2]["Driver"]
        s2n = name_plain(zh_driver(s2.get("driverId", "")), _driver_full(s2))
        s3n = name_plain(zh_driver(s3.get("driverId", "")), _driver_full(s3))
        lines.append(
            f"積分榜第二名為 {s2n}（{ds[1]['points']} 分）、第三名 {s3n}（{ds[2]['points']} 分）。")
    if cs:
        cc = cs[0]["Constructor"]
        cid = cc.get("constructorId", "")
        cons_name = name_plain(zh_team(cid, cc.get("name", "")), cc.get("name", ""))
        # 拆解掛在冠軍車隊敘事句：各車手 results+sprint 積分加總，通過 Σ gate 才附（禁手寫）
        brk = constructor_breakdowns(year).get(cid)
        if brk and brk["ok"] and brk["parts"]:
            parts_txt = "＋".join(f"{p['en']} {_fmt(p['points'])} 分" for p in brk["parts"])
            lines.append(f"車隊世界冠軍由 {cons_name} 以 {cs[0]['points']} 分拿下（{parts_txt}）。")
        else:
            lines.append(f"車隊世界冠軍由 {cons_name} 以 {cs[0]['points']} 分拿下。")
    cats = season_retirements(year)
    total_ret = sum(c["value"] for c in cats)
    if cats:
        top = cats[0]
        top_label = name_plain(top["zh"], top["status"])
        lines.append(
            f"全季正賽共 {total_ret} 人次未完賽（完賽名次為 Finished 或落後圈數者不計），"
            f"其中登記事由為「{top_label}」者 {top['value']} 次為最多。")
    return lines


# ---------- v3 子頁：選了車手／車隊（/seasons/<year>/drivers|teams/<slug>/） ----------
# 「選擇即 URL」：總覽頁＝沒選任何實體；點榜內某車手＝選了他＝進他的賽季子頁。
# 子頁生成範圍（防頁數爆炸）：只為「有實體頁的對象」（phase0 HAS_PAGE／DRIVERS／CONSTRUCTORS）
# 中「該季有參賽」者生成。slug 一律走 racinglib slugs.json（查不到就 fail，不自創）。


def season_subpage_entities(year):
    """回 (driver_ids, constructor_ids)：seed 實體（phase0 有頁）且該季有參賽者，
    依 phase0 名單順序。資料驅動——不硬編 2002 名單。"""
    ds_ids = {e["Driver"].get("driverId") for e in _driver_standings(year)}
    cs_ids = {r["Constructor"].get("constructorId") for r in _constructor_standings(year)}
    dids = [d for d in p0.DRIVERS if d in ds_ids]
    cids = [c for c in p0.CONSTRUCTORS if c in cs_ids]
    return dids, cids


def subpage_paths(year):
    """回該季所有子頁的根相對路徑集合（不含前導斜線），供總覽頁連結 gate（無死連結）。"""
    dids, cids = season_subpage_entities(year)
    paths = set()
    for did in dids:
        paths.add(f"seasons/{year}/drivers/{rc.driver_slug(did)}")
    for cid in cids:
        paths.add(f"seasons/{year}/teams/{rc.constructor_slug(cid)}")
    return paths


def _drv_subpage_link(drv, year, paths):
    """總覽榜內車手名：有子頁 → 連子頁；無 → 純文字（禁死連結）。"""
    did = drv.get("driverId", "")
    label = driver_pair(drv)
    if did in rc._SLUGS.get("drivers", {}):
        path = f"seasons/{year}/drivers/{rc.driver_slug(did)}"
        if path in paths:
            return f'<a href="/{path}/">{label}</a>'
    return label


def _team_subpage_link(cid, name, year, paths):
    label = team_pair(cid, name)
    if cid in rc._SLUGS.get("constructors", {}):
        path = f"seasons/{year}/teams/{rc.constructor_slug(cid)}"
        if path in paths:
            return f'<a href="/{path}/">{label}</a>'
    return label


# ---------- 各站冠軍列表（round／大獎賽／冠軍車手／車隊；SOURCED，position==1） ----------

def round_winners(year):
    """回 [{round, race, race_pair_html, wiki, driver, constructor}]，取每站正賽 position==1。"""
    sched = {int(r["round"]): r for r in _schedule(year)}
    out = []
    for rnd in range(1, _season_rounds(year) + 1):
        rp = RAW / "results" / f"{year}-{rnd:02d}.json"
        if not rp.exists():
            continue
        data = _load_json(rp)
        race_name = data.get("raceName") or sched.get(rnd, {}).get("raceName", f"Round {rnd}")
        winner = None
        for res in data.get("Results", []):
            if res.get("position") == "1" or res.get("positionText") == "1":
                winner = res
                break
        if not winner:
            continue
        out.append({
            "round": rnd, "race": race_name,
            "wiki": sched.get(rnd, {}).get("url", ""),
            "driver": winner.get("Driver", {}),
            "constructor": winner.get("Constructor", {}),
        })
    return out


def _round_winners_table(year, paths, round_paths=None):
    """各站冠軍表。round_paths（已生成分站頁集合）非空時，站次(R nn)與大獎賽名連往該站分站頁
    （同 gate：只連已生成的頁，無死連結）；無分站頁的季維持純文字。"""
    round_paths = round_paths or set()
    winners = round_winners(year)
    rows = []
    for w in winners:
        rnd = w["round"]
        rp = rc.race_pair(w["race"])
        rpath = f"seasons/{year}/rounds/{rnd}"
        if rpath in round_paths:
            round_cell = f'<a href="/{rpath}/" class="mono">R{rnd:02d}</a>'
            race_cell = f'<a href="/{rpath}/">{rp}</a>'
        else:
            round_cell = f'R{rnd:02d}'
            race_cell = rp
        drv_link = _drv_subpage_link(w["driver"], year, paths)
        c = w["constructor"]
        team_link = _team_subpage_link(c.get("constructorId", ""), c.get("name", ""), year, paths)
        rows.append(
            f'<tr><td class="rk mono">{round_cell}</td>'
            f'<td class="l">{race_cell}</td>'
            f'<td class="l nm">{drv_link}</td>'
            f'<td class="l">{team_link}</td></tr>')
    return ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
            '<th class="rk">站</th><th class="l">大獎賽</th>'
            '<th class="l">分站冠軍</th><th class="l">車隊</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


# ---------- v3 子頁：車手視角資料（逐站成績／季末數據卡／退賽；皆 SOURCED 或 value==len detail） ----------

def driver_season_races(year, did):
    """回該車手該季逐站成績 [{round, race, race_pair, grid, pos, points, status, source}]。"""
    sched = {int(r["round"]): r["raceName"] for r in _schedule(year)}
    out = []
    for rnd in range(1, _season_rounds(year) + 1):
        rp = RAW / "results" / f"{year}-{rnd:02d}.json"
        if not rp.exists():
            continue
        data = _load_json(rp)
        race_name = data.get("raceName") or sched.get(rnd, f"Round {rnd}")
        for res in data.get("Results", []):
            if res.get("Driver", {}).get("driverId") != did:
                continue
            out.append({
                "round": rnd, "race": race_name,
                "grid": res.get("grid", ""),
                "pos": res.get("position") or res.get("positionText", ""),
                "points": res.get("points", "0"),
                "status": res.get("status", ""),
                "source": f"data/f1/raw/results/{year}-{rnd:02d}.json",
            })
    return out


def driver_season_card(year, did):
    """回季末數據卡數字（皆 SOURCED / value==len detail）：
    final_pos／points（取自最終榜列）＋ wins／podiums／entries（逐場明細筆數）。"""
    ds = _driver_standings(year)
    row = next((e for e in ds if e["Driver"].get("driverId") == did), None)
    races = driver_season_races(year, did)
    wins = [r for r in races if str(r["pos"]) == "1"]
    podiums = [r for r in races if str(r["pos"]) in ("1", "2", "3")]
    return {
        "final_pos": (row.get("position") or row.get("positionText", "")) if row else "",
        "points": row["points"] if row else "0",
        "official_wins": row.get("wins", "0") if row else "0",
        "wins": wins, "podiums": podiums, "entries": races,
    }


def driver_retirements(year, did):
    """回該車手該季退賽明細 [{round, race, status, source}]（非完賽者）。無則空 list。"""
    out = []
    for r in driver_season_races(year, did):
        if not is_finisher(r["status"]):
            out.append({"round": r["round"], "race": r["race"],
                        "status": r["status"], "source": r["source"]})
    return out


# ---------- v3 子頁：車隊視角資料 ----------

def team_round_points(year, cid):
    """回該隊逐站積分 [{round, race, points, drivers:[{driver,points}]}]，含 sprint（若有）。
    總和 == 官方車隊積分（Σ gate 的逐站版；render 時附誠實對帳）。"""
    sched = {int(r["round"]): r["raceName"] for r in _schedule(year)}
    out = []
    for rnd in range(1, _season_rounds(year) + 1):
        rp = RAW / "results" / f"{year}-{rnd:02d}.json"
        drivers = defaultdict(float)
        name_of = {}
        found = False
        if rp.exists():
            data = _load_json(rp)
            race_name = data.get("raceName") or sched.get(rnd, f"Round {rnd}")
            for res in data.get("Results", []):
                if res.get("Constructor", {}).get("constructorId") == cid:
                    found = True
                    drv = res.get("Driver", {})
                    drivers[drv.get("driverId", "")] += float(res.get("points") or 0)
                    name_of[drv.get("driverId", "")] = _driver_full(drv)
        else:
            race_name = sched.get(rnd, f"Round {rnd}")
        for sres in _sprint_results(year, rnd):
            if sres.get("Constructor", {}).get("constructorId") == cid:
                found = True
                drv = sres.get("Driver", {})
                drivers[drv.get("driverId", "")] += float(sres.get("points") or 0)
                name_of.setdefault(drv.get("driverId", ""), _driver_full(drv))
        if not found:
            continue
        parts = [{"driver_id": d, "driver": name_of.get(d, d), "points": p}
                 for d, p in sorted(drivers.items(), key=lambda x: (-x[1], x[0]))]
        out.append({"round": rnd, "race": race_name,
                    "points": sum(drivers.values()), "drivers": parts})
    return out


def team_retirements(year, cid):
    """回該隊該季退賽明細 [{round, race, driver, status, source}]。"""
    sched = {int(r["round"]): r["raceName"] for r in _schedule(year)}
    out = []
    for rnd in range(1, _season_rounds(year) + 1):
        rp = RAW / "results" / f"{year}-{rnd:02d}.json"
        if not rp.exists():
            continue
        data = _load_json(rp)
        race_name = data.get("raceName") or sched.get(rnd, f"Round {rnd}")
        for res in data.get("Results", []):
            if res.get("Constructor", {}).get("constructorId") != cid:
                continue
            status = res.get("status", "")
            if is_finisher(status):
                continue
            drv = res.get("Driver", {})
            out.append({"round": rnd, "race": race_name,
                        "driver": _driver_full(drv), "status": status,
                        "source": f"data/f1/raw/results/{year}-{rnd:02d}.json"})
    return out


# ---------- M4-B 分站頁資料層（/seasons/<year>/rounds/<n>/；只做 2002＋2026 已跑站） ----------

def _round_results(year, rnd):
    """回該站正賽 results 檔（dict）或 None（未跑／無檔）。"""
    p = RAW / "results" / f"{year}-{rnd:02d}.json"
    return _load_json(p) if p.exists() else None


def season_round_numbers(year):
    """該季<有正賽 results 檔>的站次（升冪）。分站頁只為這些站生成——資料驅動、非硬編：
    2002＝1–17；2026＝目前已跑站（R1–R10，隨每週資料更新自動增加）。"""
    return [rnd for rnd in range(1, _season_rounds(year) + 1)
            if (RAW / "results" / f"{year}-{rnd:02d}.json").exists()]


def round_page_paths(year):
    """該季所有分站頁根相對路徑集合（不含前導斜線），供交叉連結 gate（無死連結）。"""
    return {f"seasons/{year}/rounds/{rnd}" for rnd in season_round_numbers(year)}


def is_classified(res):
    """完賽（＝獲official 完賽名次）判定：positionText 為純數字。分站頁退賽名單以此判定。

    ⚠️ 為何分站頁用 positionText 而非 is_finisher(status)：2026 資料源把 'Lapped' 同時套在
    <獲完賽名次、落後圈數者>（P7–P16，positionText 為數字）與<真正退賽者>（如 Stroll，
    positionText='R'、僅跑 43/58 圈）身上——status 兩者相同、不可靠。唯 positionText 誠實區分
    「是否列入完賽名次」。這與『+N Lap 落圈完賽者算完賽』的 2002 慣例語意一致（落圈但完賽）。
    （總覽頁 season_retirements 仍沿用 status-based is_finisher，兩頁框架不同、各自 SOURCED；
     詳見交付回報的裁決點。）"""
    return str(res.get("positionText") or res.get("position") or "").isdigit()


def round_full_results(year, rnd):
    """回該站全部參賽車手賽果（原始名次順序，含 R/D/W 等未完賽者），供完整名次表。"""
    data = _round_results(year, rnd) or {}
    return data.get("Results", [])


def round_podium(year, rnd):
    """回 [p1, p2, p3]（各為該名次的 result dict 或 None）；positionText 1/2/3。"""
    pod = {}
    for res in round_full_results(year, rnd):
        pt = res.get("positionText") or res.get("position")
        if pt in ("1", "2", "3") and pt not in pod:
            pod[pt] = res
    return [pod.get("1"), pod.get("2"), pod.get("3")]


def round_retirements(year, rnd):
    """回該站未完賽（未列入完賽名次＝positionText 非數字）車手明細，依原始名次順序。
    誠實標「本站無退賽」由 render 端依 len==0 分支處理。"""
    out = []
    for res in round_full_results(year, rnd):
        if is_classified(res):
            continue
        drv = res.get("Driver", {})
        cons = res.get("Constructor", {})
        out.append({
            "driver_id": drv.get("driverId", ""), "driver": _driver_full(drv),
            "driver_obj": drv, "constructor": cons,
            "pos": res.get("positionText") or res.get("position", ""),
            "status": res.get("status", ""),
            "source": f"data/f1/raw/results/{year}-{rnd:02d}.json",
        })
    return out


def round_sprint(year, rnd):
    """回該站衝刺賽賽果（data/f1/raw/sprint/<year>-<rnd>.json 存在才有；2002 全季無 → 空）。"""
    return _sprint_results(year, rnd)


def round_narrative(year, rnd):
    """回 list[str] 分站敘事句（模板＋資料，非 LLM）。每個數字都能在本頁明細表找到：
    grid/圈數/積分＝冠軍列；參賽/未完賽數＝完整名次表列數與退賽名單筆數；最大宗 status＝退賽名單。"""
    results = round_full_results(year, rnd)
    data = _round_results(year, rnd) or {}
    race_name = data.get("raceName", f"Round {rnd}")
    winner = next((r for r in results
                   if (r.get("positionText") or r.get("position")) == "1"), None)
    lines = []
    if winner:
        wdrv = winner.get("Driver", {})
        wname = name_plain(zh_driver(wdrv.get("driverId", "")), _driver_full(wdrv))
        grid = str(winner.get("grid", "") or "")
        laps = str(winner.get("laps", "") or "")
        pts = winner.get("points", "0")
        if grid == "0":
            start = "自維修道（發車位 0）起跑"
        elif grid.isdigit():
            start = f"從第 {grid} 位發車"
        else:
            start = "起跑"
        lap_txt = f"、完成 {laps} 圈" if laps else ""
        lines.append(f"{year} {rc.race_zh(race_name)}由 {wname} {start}{lap_txt}奪下分站冠軍，"
                     f"單場進帳 {pts} 分。")
    pod = round_podium(year, rnd)
    if pod[1] is not None and pod[2] is not None:
        p2, p3 = pod[1].get("Driver", {}), pod[2].get("Driver", {})
        p2n = name_plain(zh_driver(p2.get("driverId", "")), _driver_full(p2))
        p3n = name_plain(zh_driver(p3.get("driverId", "")), _driver_full(p3))
        lines.append(f"亞軍為 {p2n}、季軍為 {p3n}，三人同登頒獎台。")
    n_entries = len(results)
    rets = round_retirements(year, rnd)
    n_dnf = len(rets)
    n_class = n_entries - n_dnf
    lines.append(f"本站共 {n_entries} 位車手參賽，其中 {n_class} 位獲完賽名次、"
                 f"{n_dnf} 位未完賽（未列入完賽名次者）。")
    if rets:
        cnt = defaultdict(int)
        for d in rets:
            cnt[d["status"]] += 1
        top_status, top_n = max(cnt.items(), key=lambda kv: (kv[1], kv[0]))
        gloss = name_plain(STATUS_ZH.get(top_status), top_status)
        lines.append(f"未完賽者中，賽果登記事由為「{gloss}」者 {top_n} 位為最多"
                     "（status 為原文，本站不直譯退賽因果）。")
    else:
        lines.append("本站全員獲完賽名次，無退賽紀錄。")
    return lines


# ---------- 渲染：索引頁 /seasons/ ----------

def _index_champ_cell(champ):
    if champ is None:
        return '<span class="dim">—</span>'
    return p0.pair(champ["zh"], champ["en"])


def _index_has_page(year, built_years):
    """索引該連哪些年：--all 模式傳入 built_years（全 77 季皆有頁）；
    單季模式（built_years=None）沿用 phase0 HAS_PAGE（目前只有 2002）——不連未生成的頁（無死連結）。"""
    if built_years is not None:
        return year in built_years
    return f"seasons/{year}" in p0.HAS_PAGE


def render_index(built_years=None):
    rows_html = []
    urls = []
    for year in range(LAST_YEAR, FIRST_YEAR - 1, -1):  # 新到舊
        row = index_row(year)
        year_cell = (f'<a href="/seasons/{year}/"><span class="mono">{year}</span></a>'
                     if _index_has_page(year, built_years)
                     else f'<span class="mono">{year}</span>')
        if row["in_progress"]:
            dchamp = '<span class="ip">進行中</span>'
            cchamp = '<span class="ip">進行中</span>'
            # T-01：進行中賽季顯示「已跑 / 全季」，避免把已跑站次誤讀為全季分站數
            rounds_cell = f'{row["rounds"]} / {row["scheduled"]}'
        else:
            dchamp = _index_champ_cell(row["driver_champ"])
            cchamp = _index_champ_cell(row["constructor_champ"])
            rounds_cell = str(row["rounds"])
        rows_html.append(
            f'<tr><td class="l">{year_cell}</td>'
            f'<td class="l">{dchamp}</td>'
            f'<td class="l">{cchamp}</td>'
            f'<td class="mono">{rounds_cell}</td></tr>')
    table = ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
             '<th class="l">賽季</th><th class="l">車手世界冠軍</th>'
             '<th class="l">車隊世界冠軍</th><th>分站數</th>'
             f'</tr></thead><tbody>{"".join(rows_html)}</tbody></table></div>')

    canonical = f"{BASE}/seasons/"
    intro = (f'<div class="pg-sub">一級方程式 <b>{FIRST_YEAR}–{LAST_YEAR}</b> 共 '
             f'<b>{LAST_YEAR - FIRST_YEAR + 1}</b> 個賽季的車手與車隊世界冠軍、分站數一覽。'
             '進行中的賽季只顯示「進行中」不列冠軍（榜首＝目前領先，非冠軍）。'
             '中文名採台灣慣用譯名並附原文，查無定版譯名者誠實只列原文。</div>')
    if built_years is not None and all(y in built_years for y in range(FIRST_YEAR, LAST_YEAR + 1)):
        avail_txt = '全部 <b>77</b> 季均已建詳細頁（點賽季年份進入）。'
    else:
        avail_txt = '目前僅 <b>2002</b> 賽季已建詳細頁（可點）；其餘賽季詳細頁陸續補上。'
    note = (f'<p class="note">{avail_txt}'
            '冠軍認定一律取自資料源該季<b>最終官方積分榜</b>榜首，本站不自行計算。'
            '分站數取自積分榜快照的最終站次（round）欄；'
            '進行中賽季顯示「已跑站次 / 全季排定站數」。'
            '車隊世界錦標賽 <b>1958</b> 年才設立，此前賽季車隊冠軍欄以「—」誠實留空。</p>')
    body = (f'<h1 class="pg-h1">歷屆賽季</h1>{intro}{table}{note}')

    # JSON-LD：org+website+CollectionPage+breadcrumb+ItemList（url 只填已存在的頁）
    items = []
    for i, year in enumerate(range(LAST_YEAR, FIRST_YEAR - 1, -1)):
        el = {"@type": "ListItem", "position": i + 1, "name": f"{year} 一級方程式賽季"}
        if _index_has_page(year, built_years):
            el["url"] = f"{BASE}/seasons/{year}/"
        items.append(el)
    coll = {"@type": "CollectionPage", "@id": canonical, "url": canonical,
            "name": f"歷屆一級方程式賽季（{FIRST_YEAR}–{LAST_YEAR}）", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{BASE}/#website"}}
    item_list = {"@type": "ItemList", "name": f"F1 賽季列表 {FIRST_YEAR}–{LAST_YEAR}",
                 "numberOfItems": len(items), "itemListElement": items}
    jsonld = rc.graph_ld([rc.org_node(), rc.website_node(), coll,
                          rc.breadcrumb_node([("首頁", f"{BASE}/"), ("賽季", canonical)]),
                          item_list])
    desc = (f"一級方程式 {FIRST_YEAR}–{LAST_YEAR} 歷屆賽季車手與車隊世界冠軍、分站數索引，"
            "台灣慣用繁中譯名＋原文對照。")
    html = rc.page_shell("歷屆一級方程式賽季總覽", desc, canonical, jsonld, body,
                         active="", extra_css=p0.ENTITY_CSS + SEASON_CSS)
    out = PUB / "seasons"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ /seasons/　（{LAST_YEAR - FIRST_YEAR + 1} 季）")
    return canonical


# ---------- 渲染：單一賽季頁 /seasons/2002/ ----------

def _std_driver_table(ds, year=None, paths=None):
    """完整車手積分榜（全部車手，不只前幾名）。有子頁的車手名連子頁，無則純文字（禁死連結）。"""
    paths = paths or set()
    rows = []
    for r in ds:
        drv = r["Driver"]
        lead = ' class="lead"' if r.get("position") == "1" else ""
        cons = (r.get("Constructors") or [{}])[-1]
        link = (_drv_subpage_link(drv, year, paths) if year is not None else driver_pair(drv))
        tlink = (_team_subpage_link(cons.get("constructorId", ""), cons.get("name", ""), year, paths)
                 if year is not None else team_pair(cons.get("constructorId", ""), cons.get("name", "")))
        pos = r.get("position") or r.get("positionText", "")
        rows.append(
            f'<tr{lead}><td class="rk">{pos}</td>'
            f'<td class="l nm">{link}</td>'
            f'<td class="l">{tlink}</td>'
            f'<td class="std-pts">{r["points"]}</td><td>{r.get("wins", "0")}</td></tr>')
    return ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
            '<th class="rk">#</th><th class="l">車手</th><th class="l">車隊</th>'
            '<th>積分</th><th>分站冠軍</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def _std_constructor_table(cs, breakdowns=None, year=None, paths=None):
    """車隊積分榜。breakdowns（constructor_breakdowns 回傳）通過 Σ gate 的車隊，
    在該列下加一行小字拆解「＝ 車手A NNN ＋ 車手B NN」；對不上（best-car 年代）則不顯示拆解。
    有子頁的車隊名連子頁，無則純文字（禁死連結）。"""
    breakdowns = breakdowns or {}
    paths = paths or set()
    rows = []
    for r in cs:
        c = r["Constructor"]
        cid = c.get("constructorId", "")
        lead = ' class="lead"' if r.get("position") == "1" else ""
        link = (_team_subpage_link(cid, c.get("name", ""), year, paths)
                if year is not None else team_pair(cid, c.get("name", "")))
        pos = r.get("position") or r.get("positionText", "")
        rows.append(
            f'<tr{lead}><td class="rk">{pos}</td>'
            f'<td class="l nm">{link}</td>'
            f'<td class="std-pts">{r["points"]}</td><td>{r.get("wins", "0")}</td></tr>')
        brk = breakdowns.get(cid)
        # Σ gate：拆解各項之和恰等官方車隊積分才顯示；對不上（1958–78 只計最佳車等年代）不顯示
        if brk and brk["ok"] and brk["parts"]:
            seg = "　＋　".join(
                f'<span title="{esc(name_plain(p["zh"], p["en"]))} '
                f'積分＝該季逐站正賽 points 加總（含 sprint 若有），Σ 恰等官方車隊積分">'
                f'{p0.pair(p["zh"], p["en"])} <b>{_fmt(p["points"])}</b></span>'
                for p in brk["parts"])
            rows.append(
                f'<tr class="brk"><td></td><td class="l" colspan="3">'
                f'<span class="brk-txt">＝　{seg}</span></td></tr>')
    return ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
            '<th class="rk">#</th><th class="l">車隊</th><th>積分</th><th>分站冠軍</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


# ---------- 冠軍之爭：前三名累計積分多線圖（SVG，零 JS；終點對不上官方積分則整張不畫） ----------

def _championship_race_chart(year):
    leaders, ok = cumulative_leaders(year)
    in_progress = not fs._is_completed(year)
    if in_progress:
        note_ok = ('<p class="note">下圖是<b>目前積分榜前三名</b>車手的逐站<b>累計積分</b>對決：'
                   'x 軸＝分站（第 1 站至目前最後一站），y 軸＝累計積分（0 在底部）。'
                   '累計由逐站正賽（含衝刺賽，若有）的 points 相加而得，'
                   '因此<b>每條線的終點恰為該車手目前的官方積分</b>。'
                   '賽季進行中・每週自動更新。</p>')
    else:
        note_ok = ('<p class="note">下圖是該季<b>最終積分榜前三名</b>車手的逐站<b>累計積分</b>對決：'
                   'x 軸＝分站（第 1 站至最後一站），y 軸＝累計積分（0 在底部）。'
                   '累計由逐站正賽（含衝刺賽，若該季有）的 points 相加而得，'
                   '因此<b>每條線的終點恰為該車手的官方最終積分</b>——三條線終點高低即最終名次差距。</p>')
    # 硬 gate：任一條線終點對不上官方積分（best-N／dropped-scores 年代）→ 整張不畫，改誠實 note
    if not ok or len(leaders) < 2:
        return ('<p class="note">該季採計分制捨分規則（僅計最佳數場成績的 best-N／dropped-scores），'
                '逐站累計與官方最終積分不同義，本站不重建冠軍之爭累計圖（硬湊會畫出錯圖）。</p>')

    W, H = 680, 320
    padL, padR, padT, padB = 56, 138, 16, 30
    rounds = max(p[0] for l in leaders for p in l["series"])
    maxpts = max(l["final"] for l in leaders)
    step, top = _nice_ticks(maxpts)
    plotW, plotH = W - padL - padR, H - padT - padB
    xs = (lambda r: padL + ((r - 1) / (rounds - 1) if rounds > 1 else 0) * plotW)
    ys = lambda v: (H - padB) - (v / top) * plotH

    # y 軸整數刻度：文字放繪圖區外側（x < padL，text-anchor end），不與線重疊
    grid = []
    v = 0
    while v <= top + 1e-9:
        y = ys(v)
        grid.append(f'<line x1="{padL}" y1="{y:.1f}" x2="{W-padR}" y2="{y:.1f}" class="cc-grid"/>')
        grid.append(f'<text x="{padL-10}" y="{y+4:.1f}" text-anchor="end" class="cc-axis">{int(v)}</text>')
        v += step
    # x 軸分站標（首、末與均分幾站）
    xlabs = []
    for r in sorted(set([1, rounds] + list(range(1, rounds + 1, max(1, rounds // 5))))):
        xlabs.append(f'<text x="{xs(r):.1f}" y="{H-padB+18:.1f}" text-anchor="middle" '
                     f'class="cc-xlab">R{r}</text>')

    # 冠軍 #d63a2f 粗線 2.5；第二第三 accent 明度階（不對應車隊塗裝），線寬 1.8
    palette = [("#d63a2f", 2.5), ("#e8837a", 1.8), ("#b9a09d", 1.8)]
    lines_svg, labels = [], []
    for i, l in enumerate(leaders):
        color, sw = palette[i] if i < len(palette) else ("#b9a09d", 1.8)
        poly = " ".join(f"{xs(r):.1f},{ys(vv):.1f}" for r, vv in l["series"])
        lines_svg.append(f'<polyline points="{poly}" fill="none" stroke="{color}" '
                         f'stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>')
        lr, lv = l["series"][-1]
        name = l["zh"] or l["family"] or l["en"]  # approved 譯名優先，否則原文姓氏
        labels.append({"x": xs(lr) + 9, "y": ys(lv), "name": name,
                       "pts": l["final"], "color": color})
    # 右端名字直接標；靠太近時往下推，避免相疊
    labels.sort(key=lambda d: d["y"])
    for i in range(1, len(labels)):
        if labels[i]["y"] - labels[i - 1]["y"] < 15:
            labels[i]["y"] = labels[i - 1]["y"] + 15
    lab_svg = "".join(
        f'<text x="{d["x"]:.1f}" y="{d["y"]+4:.1f}" text-anchor="start" '
        f'class="cc-name" fill="{d["color"]}">{esc(d["name"])}'
        f'<tspan class="cc-pts" dx="4">{_fmt(d["pts"])}</tspan></text>'
        for d in labels)

    svg = (f'<svg viewBox="0 0 {W} {H}" class="champ-chart" role="img" '
           f'aria-label="{year} 賽季最終積分榜前三名車手逐站累計積分走勢">'
           + "".join(grid) + "".join(xlabs) + "".join(lines_svg) + lab_svg + '</svg>')
    return note_ok + svg


def _gap_details(year, champ_pts, second_pts, gap, champ_name, second_name, in_progress=False):
    board = "目前官方車手積分榜" if in_progress else "該季最終官方車手積分榜"
    lead_lbl = "目前領先者" if in_progress else "冠軍"
    return f"""<details class="how">
  <summary>怎麼算的</summary>
  <div class="how-body">
    <ol class="detail-list">
      <li title="來源檔：data/f1/raw/standings/driver-{year}.json#pos1">{lead_lbl} {esc(champ_name)}：<b>{_fmt(champ_pts)}</b> 分（{board}榜首）</li>
      <li title="來源檔：data/f1/raw/standings/driver-{year}.json#pos2">第二名 {esc(second_name)}：<b>{_fmt(second_pts)}</b> 分（同榜第 2 名）</li>
    </ol>
    <p class="prov">分差 ＝ {_fmt(champ_pts)} − {_fmt(second_pts)} ＝ <b>{_fmt(gap)}</b>。兩個數字皆直接取自{board}，本站只做減法。</p>
  </div>
</details>"""


def _retirement_chart(cats, year):
    if not cats:
        return '<p class="note">本季無退賽紀錄可聚合。</p>'
    maxv = max(c["value"] for c in cats)
    total = sum(c["value"] for c in cats)
    n_drivers = len({d["driver_id"] for c in cats for d in c["detail"]})  # 涉及退賽的車手數（從資料算）
    rows = []
    for c in cats:
        pct = c["value"] / maxv * 100
        label = f'{c["zh"]}<span class="rt-en">　{esc(c["status"])}</span>' if c["zh"] else f'<span class="rt-en">{esc(c["status"])}</span>'
        detail = "".join(
            f'<li title="來源檔：{esc(d["source"])}"><span class="mono">R{d["round"]:02d}</span> '
            f'{esc(d["race"])} · {esc(d["driver"])} · <span class="rt-status">{esc(c["status"])}</span></li>'
            for d in c["detail"])
        rows.append(
            f'<details class="rt"><summary>'
            f'<span class="rt-label">{label}</span>'
            f'<span class="rt-bar"><span class="rt-fill" style="width:{pct:.1f}%"></span></span>'
            f'<span class="rt-n mono">{c["value"]}</span></summary>'
            f'<ol class="detail-list rt-detail">{detail}</ol></details>')
    head = (f'<p class="note">本節統計 {year} 年<b>全部 {n_drivers} 位</b>曾未完賽車手的紀錄'
            f'（<b>非僅冠軍</b>）：全季正賽共 <b>{total}</b> 人次未完賽，依登記事由（status）分類如下。'
            '每一類的數字＝下方展開明細的筆數；明細逐筆列出<b>第幾站、車手、status 原文</b>，'
            'status 不直譯因果（例如 <span class="rt-status">Engine</span> 僅為賽果登記事由，'
            '非本站對退賽機制的斷言）。</p>')
    return head + '<div class="rt-chart">' + "".join(rows) + '</div>'


def _race_event_nodes(year, schedule, season_url):
    nodes = []
    for r in schedule:
        circ = r.get("Circuit", {})
        loc = circ.get("Location", {})
        place = {"@type": "Place", "name": circ.get("circuitName", "")}
        addr = {"@type": "PostalAddress"}
        if loc.get("locality"):
            addr["addressLocality"] = loc["locality"]
        if loc.get("country"):
            addr["addressCountry"] = loc["country"]
        if len(addr) > 1:
            place["address"] = addr
        if loc.get("lat") and loc.get("long"):
            place["geo"] = {"@type": "GeoCoordinates",
                            "latitude": loc["lat"], "longitude": loc["long"]}
        node = {"@type": "SportsEvent", "name": f'{year} {r.get("raceName", "")}',
                "sport": "Formula One", "eventStatus": "https://schema.org/EventScheduled",
                "location": place, "isPartOf": {"@id": f"{season_url}#page"}}
        if r.get("date"):
            node["startDate"] = r["date"]
        if r.get("url"):
            node["sameAs"] = r["url"]  # 維基（誠實 fallback：只放公開百科，不放官方素材）
        nodes.append(node)
    return nodes


# ---------- 人工賽季導言：default-deny 核准 gate（沿用 config/approved.json 的 sha256 綁定機制） ----------
# 只為「有故事的季」寫 120–200 字人工導言（content/seasons/<year>.md），流程＝facts pack → 主寫 →
# 機械對帳（scripts/check-season-intros.py）→ Charlie 人工核准。核准＝在 config/approved.json 補一筆
# slug="season-intro-<year>"、article_sha256＝該 .md 原始 bytes 的 sha256 的條目（同文章 gate 的綁定）。
# 未核准 / 檔案被竄改（sha 不符）→ approved_intro_html 回空字串 → 賽季頁與現狀 byte-identical。
INTRO_DIR = ROOT / "content" / "seasons"
INTRO_SLUG = "season-intro-{year}"


def _load_approved():
    """讀 config/approved.json，回 slug→entry dict。缺檔＝default-deny（回空）。"""
    p = ROOT / "config" / "approved.json"
    if not p.exists():
        return {}
    entries = json.loads(p.read_text(encoding="utf-8")).get("approved", [])
    out = {}
    for e in entries:
        slug = e.get("slug")
        if slug:
            out[slug] = e
    return out


def _intro_path(year):
    return INTRO_DIR / f"{year}.md"


def approved_intro_html(year, approved=None):
    """回該季導言的 HTML 區塊字串；未核准 / sha 不符 / 無檔 → 回 ""（→ 頁面 byte-identical）。

    區塊沿用既有 narrative 風格（.narrative），頂部標「編輯導言」語意的 sec-title。
    回傳字串以「\\n\\n<div ...>」開頭，供 render_season 以 {hero}{intro}\\n{stat} 插入——
    intro=="" 時 body 與導入本功能前完全相同（不新增任何位元）。
    """
    md = _intro_path(year)
    if not md.exists():
        return ""
    approved = _load_approved() if approved is None else approved
    entry = approved.get(INTRO_SLUG.format(year=year))
    if not entry:
        return ""  # default-deny：未列入核准清單
    want = entry.get("article_sha256", "")
    actual = hashlib.sha256(md.read_bytes()).hexdigest()
    if not want or want != actual:
        return ""  # 檔案被竄改或核准 sha 對不上 → 不渲染（現狀）
    prose = md.read_text(encoding="utf-8").strip()
    paras = "".join(f"<p>{esc(p.strip())}</p>" for p in prose.split("\n\n") if p.strip())
    return (f'\n\n<div class="sec-title">編輯導言</div>'
            f'\n<div class="narrative editorial-intro">{paras}</div>')


def render_season(year, round_paths=None):
    ds = _driver_standings(year)
    cs = _constructor_standings(year)
    sched = _schedule(year)
    # 韌性：車手榜是最低要求（1950 起皆有）；車隊榜 1958 才有→<1958 hide 車隊榜（非 crash）
    if not ds:
        raise SystemExit(f"❌ 缺 {year} 車手積分榜資料（driver-{year}.json）")
    in_progress = not fs._is_completed(year)   # 2026：不再拒產，改 in-progress 變體
    has_cons = bool(cs)                         # <1958：車隊世界錦標賽尚未創立

    canonical = f"{BASE}/seasons/{year}/"
    rounds = _season_rounds(year)
    scheduled = len(sched)
    champ_pts, second_pts, gap = points_gap(year)
    cd = ds[0]["Driver"]
    champ_zh, champ_en = zh_driver(cd.get("driverId", "")), _driver_full(cd)
    sd = ds[1]["Driver"] if len(ds) > 1 else {}
    # 領先者 chip：選擇即 URL——優先連「該季子頁」；無子頁季 fallback 生涯實體頁（無頁→純文字）。
    _hero_paths = subpage_paths(year)
    champ_link = _drv_subpage_link(cd, year, _hero_paths)
    if "<a " not in champ_link:
        champ_link = p0.internal_link(f'drivers/{cd.get("driverId", "").replace("_", "-")}',
                                      driver_pair(cd))
    cons_link = ""
    if has_cons:
        cc = cs[0]["Constructor"]
        cons_link = _team_subpage_link(cc.get("constructorId", ""), cc.get("name", ""), year, _hero_paths)
        if "<a " not in cons_link:
            cons_link = p0.internal_link(f'constructors/{cc.get("constructorId", "").replace("_", "-")}',
                                         team_pair(cc.get("constructorId", ""), cc.get("name", "")))

    # Hero（in_progress：進行中 tag＋已跑/排定＋「目前領先」非「冠軍」；<1958：無車隊冠軍格）
    if in_progress:
        rounds_line = f'<span>已跑 / 排定 <span class="mono">{rounds} / {scheduled}</span></span>'
        lead_line = f'<span>目前領先 {champ_link}</span>'
        cons_line = (f'<span>車隊領先 {cons_link}</span>' if has_cons else "")
        h1 = f'{year} 賽季<span class="ip-tag">進行中</span>'
        kicker = "賽季 · Season · 進行中"
    else:
        rounds_line = f'<span>分站數 <span class="mono">{rounds}</span></span>'
        lead_line = f'<span>車手冠軍 {champ_link}</span>'
        cons_line = (f'<span>車隊冠軍 {cons_link}</span>' if has_cons
                     else '<span class="dim">車隊冠軍 —（車隊世界錦標賽 1958 年才創立）</span>')
        h1 = f'{year} 賽季'
        kicker = "賽季 · Season"
    banner = ('<p class="ip-banner">本頁為進行中賽季：榜首＝目前領先非冠軍，數據為目前官方快照，'
              '賽季進行中・每週自動更新。</p>') if in_progress else ""
    hero = f"""<div class="ent-hero">
  <p class="ent-kicker">{kicker}</p>
  <h1 class="ent-h1">{h1}</h1>
  <div class="ident">
    {rounds_line}
    {lead_line}
    {cons_line}
  </div>
</div>{banner}"""

    # Hero stat 卡（in_progress 用「目前領先者」語意，完賽用「冠軍」語意）
    champ_name_plain = name_plain(champ_zh, champ_en)
    second_name_plain = name_plain(zh_driver(sd.get("driverId", "")), _driver_full(sd)) if sd else "—"
    if in_progress:
        pts_lbl, pts_why = "目前領先者積分", f"{esc(champ_name_plain)}，取自目前官方車手積分榜榜首（賽季進行中）。"
        wins_lbl, wins_why = "目前分站冠軍數", "取自目前積分榜的 wins 欄（本季至今分站冠軍場次）。"
    else:
        pts_lbl, pts_why = "冠軍最終積分", f"{esc(champ_name_plain)}，取自該季最終車手積分榜榜首。"
        wins_lbl, wins_why = "冠軍當季分站冠軍", "取自積分榜的 wins 欄（該季分站冠軍場次）。"
    stat_cards = f"""<div class="stat-grid">
  <div class="stat"><div class="stat-v mono">{_fmt(champ_pts)}<span class="unit"> 分</span></div>
    <div class="stat-l">{pts_lbl}</div>
    <p class="na-why">{pts_why}</p></div>
  <div class="stat"><div class="stat-v mono">{_fmt(gap)}<span class="unit"> 分</span></div>
    <div class="stat-l">領先第二名</div>
    {_gap_details(year, champ_pts, second_pts, gap, champ_name_plain, second_name_plain, in_progress)}</div>
  <div class="stat"><div class="stat-v mono">{ds[0].get("wins", "0")}<span class="unit"> 勝</span></div>
    <div class="stat-l">{wins_lbl}</div>
    <p class="na-why">{wins_why}</p></div>
</div>"""

    # 冠軍之爭：前三名逐站累計積分多線圖（硬 gate，dropped-scores 對不上→整張不畫，改誠實 note）
    champ_race = _championship_race_chart(year)

    # v3：總覽頁＝沒選任何實體。榜內與各站冠軍表內，有子頁的車手/車隊名連對應子頁（選擇即 URL）
    paths = subpage_paths(year)

    # 積分榜 tabs（CSS-only，全列不只前十）；車隊 tab 帶車手貢獻拆解（Σ gate）
    # <1958：無車隊榜→只放車手 tab（誠實隱藏車隊積分榜，非畫空表）
    breakdowns = constructor_breakdowns(year)
    tab_list = [("drv", "車手積分榜", _std_driver_table(ds, year, paths), "")]
    if has_cons:
        tab_list.append(("con", "車隊積分榜", _std_constructor_table(cs, breakdowns, year, paths), ""))
    tabs = rc.tabgroup("ss", tab_list)
    cons_hidden_note = ("" if has_cons else
                        '<p class="note">車隊世界錦標賽 <b>1958</b> 年才創立，'
                        f'{year} 賽季<b>無官方車隊積分榜</b>，本站據此不顯示車隊榜與車隊子頁（不憑逐車手加總捏造）。</p>')

    # 各站冠軍列表（round／大獎賽／冠軍車手／車隊）；有分站頁的季，站次與大獎賽名連往分站頁
    winners_table = _round_winners_table(year, paths, round_paths)
    has_round_pages = bool(round_paths)

    # 全季退賽圖鑑
    cats = season_retirements(year)
    chart = _retirement_chart(cats, year)

    # 人工賽季導言（default-deny）：僅在該季導言檔存在且 sha256 在 approved.json 內才吐區塊，
    # 否則回 ""，body 與導入本功能前 byte-identical（只為「有故事的季」放頁頂）。
    intro_block = approved_intro_html(year)

    # 規則化敘事句（in_progress 判斷在 season_narrative 內部；每個數字都在頁面明細可回溯）
    narr = "".join(f"<p>{esc(s)}</p>" for s in season_narrative(year))

    race_title = "積分之爭（進行中）" if in_progress else "冠軍之爭"
    winners_scope = (f"目前已完成 {rounds} 站" if in_progress else f"全季 {rounds} 站")
    board_txt = ("目前官方積分榜（賽季進行中，每週自動更新）" if in_progress
                 else "最終官方積分榜")

    body = f"""{hero}{intro_block}
{stat_cards}

<div class="sec-title">賽季速寫</div>
<div class="narrative">{narr}</div>

<div class="sec-title">{race_title}</div>
{champ_race}

<div class="sec-title">積分榜</div>
{tabs}
{cons_hidden_note}

<div class="sec-title">各站冠軍</div>
<p class="note">{winners_scope}的分站冠軍車手與車隊。{'<b>站次與大獎賽名可點</b>進入該站分站頁（完整正賽名次、頒獎台、退賽）；' if has_round_pages else ''}<b>紅色可點</b>的名字已建該季子頁——點某位車手／車隊，就進入「以他為主角」的該季視角頁（逐站成績、車手貢獻拆解、退賽）。</p>
{winners_table}

<div class="sec-title">全季退賽圖鑑</div>
{chart}

<p class="note">積分與名次直接取自資料源的該季<b>{board_txt}</b>，不經本站計算。
本頁為<b>中性總覽</b>（沒有選定任何車手／車隊）；選了某位實體＝進入其賽季子頁。
退賽分類的每個數字皆可展開回指來源賽果檔。</p>
"""

    coll = {"@type": "CollectionPage", "@id": f"{canonical}#page", "url": canonical,
            "name": f"{year} 一級方程式賽季總覽", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{BASE}/#website"}}
    jsonld = rc.graph_ld(
        [rc.org_node(), rc.website_node(), coll,
         rc.breadcrumb_node([("首頁", f"{BASE}/"), ("賽季", f"{BASE}/seasons/"),
                             (f"{year} 賽季", canonical)])]
        + _race_event_nodes(year, sched, canonical))
    gap_txt = ("目前領先第二名 " if in_progress else "對第二名分差 ") + f"{_fmt(gap)} 分"
    desc = (f"{year} 一級方程式賽季總覽：車手" + ("與車隊" if has_cons else "") + "積分榜、前三名"
            f"累計積分對決、{gap_txt}與全季退賽圖鑑，每個數字可回溯官方來源。")
    html = rc.page_shell(f"{year} 一級方程式賽季總覽", desc, canonical, jsonld, body,
                         active="", extra_css=p0.ENTITY_CSS + SEASON_CSS)
    out = PUB / "seasons" / str(year)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    tag = "進行中" if in_progress else f"領先 {_fmt(gap)}"
    print(f"  ✓ /seasons/{year}/　{champ_en} {_fmt(champ_pts)}分（{tag}）· "
          f"{len(cats)} 類退賽{'' if has_cons else ' · 無車隊榜'}")
    return canonical


# ---------- 渲染：v3 子頁 麵包屑 ----------

def _crumbs(year, leaf):
    """視覺麵包屑：首頁 › 賽季 › <year> › <leaf>（末層純文字）。零 JS。"""
    return (f'<nav class="crumbs" aria-label="breadcrumb">'
            f'<a href="/">首頁</a><span>›</span>'
            f'<a href="/seasons/">賽季</a><span>›</span>'
            f'<a href="/seasons/{year}/">{year}</a><span>›</span>'
            f'<span class="cur">{leaf}</span></nav>')


# ---------- 渲染：/seasons/<year>/drivers/<slug>/（選了車手） ----------

def render_driver_subpage(year, did, round_paths=None):
    round_paths = round_paths or set()
    ds = _driver_standings(year)
    row = next((e for e in ds if e["Driver"].get("driverId") == did), None)
    if not row:
        raise SystemExit(f"❌ {did} 未出現在 {year} 車手積分榜——不應為其生成子頁")
    drv = row["Driver"]
    slug = rc.driver_slug(did)
    canonical = f"{BASE}/seasons/{year}/drivers/{slug}/"
    entity_url = f"{BASE}/drivers/{slug}/"
    overview_url = f"{BASE}/seasons/{year}/"
    zh, en = zh_driver(did), _driver_full(drv)
    name_disp = p0.pair(zh, en)
    name_txt = name_plain(zh, en)
    in_progress = not fs._is_completed(year)
    board = "目前車手積分榜" if in_progress else "最終車手積分榜"
    pos_lbl = "目前積分榜名次" if in_progress else "車手積分榜名次"

    card = driver_season_card(year, did)
    races = card["entries"]
    rets = driver_retirements(year, did)

    # 季末數據卡（final_pos／points SOURCED；wins／podiums／entries = 明細筆數，value==len detail）
    stat_cards = f"""<div class="stat-grid">
  <div class="stat"><div class="stat-v mono">{esc(str(card["final_pos"]))}</div>
    <div class="stat-l">{pos_lbl}</div>
    <p class="na-why">取自 {year} {board}該車手所在列。</p></div>
  <div class="stat"><div class="stat-v mono">{card["points"]}<span class="unit"> 分</span></div>
    <div class="stat-l">當季積分</div>
    <p class="na-why">取自{board}該車手 points 欄。</p></div>
  <div class="stat"><div class="stat-v mono">{len(card["wins"])}<span class="unit"> 勝</span></div>
    <div class="stat-l">分站冠軍</div>
    <p class="na-why">＝下方逐站成績中名次為第 1 的場次筆數（官方 wins 欄：{card["official_wins"]}）。</p></div>
  <div class="stat"><div class="stat-v mono">{len(card["podiums"])}<span class="unit"> 次</span></div>
    <div class="stat-l">頒獎台</div>
    <p class="na-why">＝逐站成績中名次為前三的場次筆數。</p></div>
  <div class="stat"><div class="stat-v mono">{len(races)}<span class="unit"> 站</span></div>
    <div class="stat-l">出賽</div>
    <p class="na-why">＝資料源有此車手賽果紀錄的場次筆數。</p></div>
</div>"""

    # 逐站成績表（round／大獎賽／發車位／完賽名次／積分／status 原文）
    rrows = []
    for r in races:
        rp = rc.race_pair(r["race"])
        rpath = f'seasons/{year}/rounds/{r["round"]}'
        rnd_cell = (f'<a href="/{rpath}/">R{r["round"]:02d}</a>'
                    if rpath in round_paths else f'R{r["round"]:02d}')
        rrows.append(
            f'<tr><td class="rk mono">{rnd_cell}</td>'
            f'<td class="l">{rp}</td>'
            f'<td class="mono">{esc(str(r["grid"]))}</td>'
            f'<td class="mono">{esc(str(r["pos"]))}</td>'
            f'<td class="std-pts">{esc(str(r["points"]))}</td>'
            f'<td class="l"><span class="rt-status" title="來源檔：{esc(r["source"])}">{esc(r["status"])}</span></td></tr>')
    races_table = ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
                   '<th class="rk">站</th><th class="l">大獎賽</th><th>發車位</th>'
                   '<th>完賽名次</th><th>積分</th><th class="l">賽果登記</th>'
                   f'</tr></thead><tbody>{"".join(rrows)}</tbody></table></div>')

    # 車手視角敘事（模板＋SOURCED 數字；in_progress 一律進行時態、無「奪冠」定案語）
    n_wins, n_pod = len(card["wins"]), len(card["podiums"])
    if in_progress:
        lines = [f"{name_txt} 在進行中的 {year} 賽季至今出賽 {len(races)} 站，"
                 f"以 {card['points']} 分暫居車手積分榜第 {card['final_pos']} 位（榜次為目前領先，非最終名次）。"]
        lines.append(f"至今拿下 {n_wins} 場分站冠軍、{n_pod} 次頒獎台。")
        if rets:
            lines.append(f"其中 {len(rets)} 站未完賽（賽果登記事由逐站列於下方，本站不直譯退賽因果）。")
        else:
            lines.append("至今每一站皆完賽，無退賽紀錄。")
        lines.append("賽季進行中・每週自動更新。")
    else:
        lines = [f"{name_txt} 在 {year} 賽季出賽 {len(races)} 站，"
                 f"以 {card['points']} 分名列車手世界冠軍積分榜第 {card['final_pos']} 位。"]
        lines.append(f"全季拿下 {n_wins} 場分站冠軍、{n_pod} 次頒獎台。")
        if rets:
            lines.append(f"其中 {len(rets)} 站未完賽（賽果登記事由逐站列於下方，本站不直譯退賽因果）。")
        else:
            lines.append("全季每一站皆完賽，無退賽紀錄。")
    narr = "".join(f"<p>{esc(s)}</p>" for s in lines)

    # 該車手的退賽（如有）
    if rets:
        ret_items = "".join(
            f'<li title="來源檔：{esc(d["source"])}"><span class="mono">R{d["round"]:02d}</span> '
            f'{esc(rc.race_zh(d["race"]) if rc.race_zh(d["race"]) != d["race"] else d["race"])} · '
            f'<span class="rt-status">{esc(d["status"])}</span></li>'
            for d in rets)
        ret_html = (f'<p class="note">本季共 <b>{len(rets)}</b> 站未完賽，'
                    'status 為賽果登記事由原文，本站不直譯因果。</p>'
                    f'<ol class="detail-list">{ret_items}</ol>')
    else:
        ret_html = '<p class="note">本季<b>無退賽紀錄</b>——每一站皆完賽。</p>'

    ip_tag = '<span class="ip-tag">進行中</span>' if in_progress else ""
    body = f"""{_crumbs(year, name_txt)}
<div class="ent-hero">
  <p class="ent-kicker">賽季車手視角 · {year} Season · Driver</p>
  <h1 class="ent-h1">{name_disp}<span class="sub-year">　{year}</span>{ip_tag}</h1>
  <div class="ident">
    <span>賽季 <a href="{overview_url}">{year} 總覽</a></span>
    <span>生涯頁 <a href="{entity_url}">{esc(zh or en)}</a></span>
  </div>
</div>
{stat_cards}

<div class="sec-title">逐站成績</div>
<p class="note">{name_txt} {year} 賽季<b>每一站</b>的發車位、完賽名次、積分與賽果登記事由（status 原文，不直譯因果）。積分與名次直接取自官方賽果檔。</p>
{races_table}

<div class="sec-title">賽季速寫</div>
<div class="narrative">{narr}</div>

<div class="sec-title">退賽紀錄</div>
{ret_html}

<p class="note">本頁是「選了 {name_txt}」的 {year} 賽季視角。回到 <a href="{overview_url}">{year} 賽季總覽</a>（中性、含完整積分榜）或前往 <a href="{entity_url}">{esc(zh or en)} 生涯頁</a>。</p>
"""

    about = {"@type": "Person", "name": zh or en,
             "alternateName": en if zh else None}
    if drv.get("url"):
        about["sameAs"] = drv["url"]  # 維基（資料源給的 URL，不捏造）
    about = {k: v for k, v in about.items() if v}
    page = {"@type": "WebPage", "@id": f"{canonical}#page", "url": canonical,
            "name": f"{name_txt}：{year} 賽季成績", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{BASE}/#website"}, "about": about}
    jsonld = rc.graph_ld(
        [rc.org_node(), rc.website_node(), page,
         rc.breadcrumb_node([("首頁", f"{BASE}/"), ("賽季", f"{BASE}/seasons/"),
                             (f"{year} 賽季", overview_url), (name_txt, canonical)])])
    desc = (f"{name_txt} 在 {year} 一級方程式賽季的逐站成績（發車位、完賽名次、積分）、"
            f"季末數據（{n_wins} 勝、{n_pod} 頒獎台）與退賽紀錄，每個數字可回溯官方賽果。")
    html = rc.page_shell(f"{name_txt}｜{year} 賽季成績", desc, canonical, jsonld, body,
                         active="", extra_css=p0.ENTITY_CSS + SEASON_CSS)
    out = PUB / "seasons" / str(year) / "drivers" / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ /seasons/{year}/drivers/{slug}/　{len(races)} 站 · {n_wins} 勝 · {len(rets)} 退賽")
    return canonical


# ---------- 渲染：/seasons/<year>/teams/<slug>/（選了車隊） ----------

def render_team_subpage(year, cid, round_paths=None):
    round_paths = round_paths or set()
    cs = _constructor_standings(year)
    row = next((r for r in cs if r["Constructor"].get("constructorId") == cid), None)
    if not row:
        raise SystemExit(f"❌ {cid} 未出現在 {year} 車隊積分榜——不應為其生成子頁")
    cons = row["Constructor"]
    name = cons.get("name", cid)
    slug = rc.constructor_slug(cid)
    canonical = f"{BASE}/seasons/{year}/teams/{slug}/"
    entity_url = f"{BASE}/constructors/{slug}/"
    overview_url = f"{BASE}/seasons/{year}/"
    zh = zh_team(cid, name)
    name_txt = name_plain(zh, name)
    name_disp = p0.pair(zh, name)
    in_progress = not fs._is_completed(year)

    official = _num(row["points"])  # 半分年代（1975/1991/2021…）不得 int() 硬轉
    brk = constructor_breakdowns(year).get(cid, {})
    rounds_pts = team_round_points(year, cid)
    rets = team_retirements(year, cid)

    # 車手貢獻拆解（Σ gate：Σ(車手)==官方車隊積分才顯示；不過就整段隱藏＋誠實註記）
    if brk and brk.get("ok") and brk.get("parts"):
        parts_rows = "".join(
            f'<tr><td class="l nm">{p0.pair(p["zh"], p["en"])}</td>'
            f'<td class="std-pts">{_fmt(p["points"])}</td></tr>'
            for p in brk["parts"])
        breakdown_html = (
            f'<p class="note">{year} 賽季 {name_txt} 的官方車隊積分 <b>{_fmt(official)}</b> 分，'
            '＝旗下車手逐站正賽（含衝刺賽，若有）積分加總。以下各車手貢獻之和恰等官方車隊積分'
            '（Σ gate 通過才顯示此段）：</p>'
            '<div class="tbl-scroll"><table class="std-table"><thead><tr>'
            '<th class="l">車手</th><th>積分貢獻</th></tr></thead><tbody>'
            f'{parts_rows}'
            f'<tr class="lead"><td class="l"><b>Σ 合計</b></td>'
            f'<td class="std-pts"><b>{_fmt(brk["sum"])}</b></td></tr>'
            f'</tbody></table></div>')
    else:
        breakdown_html = (
            '<p class="note">該季車隊積分採「僅計最佳車等」記分（Σ 各車手 ≠ 官方車隊積分），'
            '逐車手加總與官方車隊積分不同義，本站<b>不顯示</b>車手貢獻拆解（硬湊會捏造）。</p>')

    # 車隊逐站積分（每站該隊得分；總和對帳官方車隊積分）
    total_rounds = sum(r["points"] for r in rounds_pts)
    sum_ok = abs(total_rounds - official) < 1e-9
    trows = []
    for r in rounds_pts:
        contrib = "、".join(f'{esc(d["driver"])} {_fmt(d["points"])}' for d in r["drivers"] if d["points"])
        rpath = f'seasons/{year}/rounds/{r["round"]}'
        rnd_cell = (f'<a href="/{rpath}/">R{r["round"]:02d}</a>'
                    if rpath in round_paths else f'R{r["round"]:02d}')
        trows.append(
            f'<tr><td class="rk mono">{rnd_cell}</td>'
            f'<td class="l">{rc.race_pair(r["race"])}</td>'
            f'<td class="std-pts">{_fmt(r["points"])}</td>'
            f'<td class="l brk-txt">{contrib or "—"}</td></tr>')
    scope_word = "目前逐站" if in_progress else "全季逐站"
    round_note = (f'<p class="note">{scope_word}積分之和 <b>{_fmt(total_rounds)}</b> 分'
                  f'{"＝" if sum_ok else "≠"}官方車隊積分 <b>{_fmt(official)}</b> 分'
                  f'{"（對帳通過）" if sum_ok else "（資料源記分制差異，僅供參考）"}。'
                  '每站積分＝該站旗下車手正賽（含衝刺賽，若有）積分加總。</p>')
    rounds_table = (round_note + '<div class="tbl-scroll"><table class="std-table"><thead><tr>'
                    '<th class="rk">站</th><th class="l">大獎賽</th><th>車隊積分</th>'
                    '<th class="l">車手貢獻</th>'
                    f'</tr></thead><tbody>{"".join(trows)}</tbody></table></div>')

    # 車隊視角敘事（in_progress 進行時態、「暫居」非「名列」；末句標進行中）
    pos = row.get("position") or row.get("positionText", "")
    if in_progress:
        lines = [f"{name_txt} 在進行中的 {year} 賽季以 {_fmt(official)} 分暫居車隊積分榜第 {pos} 位"
                 "（榜次為目前領先，非最終名次）。"]
    else:
        lines = [f"{name_txt} 在 {year} 賽季以 {_fmt(official)} 分名列車隊世界冠軍積分榜第 {pos} 位。"]
    if brk and brk.get("ok") and brk.get("parts"):
        parts_txt = "、".join(f'{p["en"]} {_fmt(p["points"])} 分' for p in brk["parts"])
        lines.append(f"車隊積分由旗下車手加總而成：{parts_txt}。")
    scope2 = "至今旗下" if in_progress else "全季旗下"
    if rets:
        lines.append(f"{scope2}車手共 {len(rets)} 人次未完賽（逐站列於下方，status 為原文，不直譯因果）。")
    else:
        lines.append(f"{scope2}車手無未完賽紀錄。")
    if in_progress:
        lines.append("賽季進行中・每週自動更新。")
    narr = "".join(f"<p>{esc(s)}</p>" for s in lines)

    # 該隊退賽
    if rets:
        ret_items = "".join(
            f'<li title="來源檔：{esc(d["source"])}"><span class="mono">R{d["round"]:02d}</span> '
            f'{esc(rc.race_zh(d["race"]) if rc.race_zh(d["race"]) != d["race"] else d["race"])} · '
            f'{esc(d["driver"])} · <span class="rt-status">{esc(d["status"])}</span></li>'
            for d in rets)
        ret_html = (f'<p class="note">本季旗下車手共 <b>{len(rets)}</b> 人次未完賽，'
                    'status 為賽果登記事由原文，本站不直譯因果。</p>'
                    f'<ol class="detail-list">{ret_items}</ol>')
    else:
        ret_html = '<p class="note">本季旗下車手<b>無退賽紀錄</b>。</p>'

    ip_tag = '<span class="ip-tag">進行中</span>' if in_progress else ""
    body = f"""{_crumbs(year, name_txt)}
<div class="ent-hero">
  <p class="ent-kicker">賽季車隊視角 · {year} Season · Constructor</p>
  <h1 class="ent-h1">{name_disp}<span class="sub-year">　{year}</span>{ip_tag}</h1>
  <div class="ident">
    <span>賽季 <a href="{overview_url}">{year} 總覽</a></span>
    <span>車隊頁 <a href="{entity_url}">{esc(zh or name)}</a></span>
  </div>
</div>

<div class="sec-title">車手貢獻拆解</div>
{breakdown_html}

<div class="sec-title">車隊逐站積分</div>
{rounds_table}

<div class="sec-title">賽季速寫</div>
<div class="narrative">{narr}</div>

<div class="sec-title">退賽紀錄</div>
{ret_html}

<p class="note">本頁是「選了 {name_txt}」的 {year} 賽季視角。回到 <a href="{overview_url}">{year} 賽季總覽</a>（中性、含完整積分榜）或前往 <a href="{entity_url}">{esc(zh or name)} 車隊頁</a>。</p>
"""

    about = {"@type": "SportsTeam", "name": zh or name,
             "alternateName": name if zh else None}
    if cons.get("url"):
        about["sameAs"] = cons["url"]
    about = {k: v for k, v in about.items() if v}
    page = {"@type": "WebPage", "@id": f"{canonical}#page", "url": canonical,
            "name": f"{name_txt}：{year} 賽季", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{BASE}/#website"}, "about": about}
    jsonld = rc.graph_ld(
        [rc.org_node(), rc.website_node(), page,
         rc.breadcrumb_node([("首頁", f"{BASE}/"), ("賽季", f"{BASE}/seasons/"),
                             (f"{year} 賽季", overview_url), (name_txt, canonical)])])
    desc = (f"{name_txt} 在 {year} 一級方程式賽季的車手貢獻拆解（Σ 恰等官方車隊積分 {_fmt(official)} 分）、"
            f"逐站積分與退賽紀錄，每個數字可回溯官方賽果。")
    html = rc.page_shell(f"{name_txt}｜{year} 賽季", desc, canonical, jsonld, body,
                         active="", extra_css=p0.ENTITY_CSS + SEASON_CSS)
    out = PUB / "seasons" / str(year) / "teams" / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ /seasons/{year}/teams/{slug}/　{_fmt(official)} 分 · Σgate={'ok' if brk.get('ok') else 'hidden'} · {len(rets)} 退賽")
    return canonical


# ---------- 渲染：/seasons/<year>/rounds/<n>/（單場分站頁；M4-B，只做 2002＋2026 已跑站） ----------

def _round_full_results_table(year, rnd, sub_paths):
    """完整正賽名次表：全部參賽車手（positionText 原樣：R/D/W…）、車手、車隊、發車位、圈數、
    status 原文、積分。車手／車隊名沿用 subpage_paths gate 連該季子頁（無子頁純文字）。"""
    rows = []
    for res in round_full_results(year, rnd):
        drv = res.get("Driver", {})
        cons = res.get("Constructor", {})
        pos = res.get("positionText") or res.get("position", "")
        lead = ' class="lead"' if pos == "1" else ""
        dl = _drv_subpage_link(drv, year, sub_paths)
        tl = _team_subpage_link(cons.get("constructorId", ""), cons.get("name", ""), year, sub_paths)
        src = f"data/f1/raw/results/{year}-{rnd:02d}.json"
        rows.append(
            f'<tr{lead}><td class="rk">{esc(str(pos))}</td>'
            f'<td class="l nm">{dl}</td>'
            f'<td class="l">{tl}</td>'
            f'<td class="mono">{esc(str(res.get("grid", "")))}</td>'
            f'<td class="mono">{esc(str(res.get("laps", "")))}</td>'
            f'<td class="l"><span class="rt-status" title="來源檔：{esc(src)}">{esc(res.get("status", ""))}</span></td>'
            f'<td class="std-pts">{esc(str(res.get("points", "0")))}</td></tr>')
    return ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
            '<th class="rk">名次</th><th class="l">車手</th><th class="l">車隊</th>'
            '<th>發車位</th><th>圈數</th><th class="l">賽果登記</th><th>積分</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def _podium_block(year, rnd):
    pod = round_podium(year, rnd)
    if not (pod[0] and pod[1] and pod[2]):
        return '<p class="note">本站頒獎台資料不完整，改見下方完整名次表。</p>'
    medals = [("1", "冠軍", "🥇"), ("2", "亞軍", "🥈"), ("3", "季軍", "🥉")]
    cards = []
    for (res, (pt, lbl, medal)) in zip(pod, medals):
        drv = res.get("Driver", {})
        cons = res.get("Constructor", {})
        cards.append(
            f'<div class="pod pod-{pt}"><div class="pod-rk">{medal} {lbl}</div>'
            f'<div class="pod-nm">{driver_pair(drv)}</div>'
            f'<div class="pod-tm">{team_pair(cons.get("constructorId", ""), cons.get("name", ""))}</div>'
            f'<div class="pod-pt mono">{esc(str(res.get("points", "0")))} 分</div></div>')
    return f'<div class="podium">{"".join(cards)}</div>'


def _sprint_block(year, rnd):
    """衝刺賽區塊（資料驅動）：sprint 檔存在才輸出。2002 全季無 → 回空字串（整段不出現）。"""
    sprint = round_sprint(year, rnd)
    if not sprint:
        return ""
    rows = []
    src = f"data/f1/raw/sprint/{year}-{rnd:02d}.json"
    for res in sprint:
        drv = res.get("Driver", {})
        cons = res.get("Constructor", {})
        pos = res.get("positionText") or res.get("position", "")
        lead = ' class="lead"' if pos == "1" else ""
        rows.append(
            f'<tr{lead}><td class="rk">{esc(str(pos))}</td>'
            f'<td class="l nm">{driver_pair(drv)}</td>'
            f'<td class="l">{team_pair(cons.get("constructorId", ""), cons.get("name", ""))}</td>'
            f'<td class="mono">{esc(str(res.get("grid", "")))}</td>'
            f'<td class="l"><span class="rt-status">{esc(res.get("status", ""))}</span></td>'
            f'<td class="std-pts">{esc(str(res.get("points", "0")))}</td></tr>')
    table = ('<div class="tbl-scroll"><table class="std-table"><thead><tr>'
             '<th class="rk">名次</th><th class="l">車手</th><th class="l">車隊</th>'
             '<th>發車位</th><th class="l">賽果登記</th><th>衝刺積分</th>'
             f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    note = (f'<p class="note">本站設有<b>衝刺賽（Sprint）</b>，以下為衝刺賽完整名次與積分'
            f'（來源：<span class="mono">{esc(src)}</span>），與上方正賽分開計分。</p>')
    return f'<div class="sec-title">衝刺賽</div>{note}{table}'


def _round_nav(year, rnd):
    """上一站／下一站導覽：只連該季已生成的分站頁；邊界站單向、禁死連結。"""
    rounds_all = season_round_numbers(year)
    sched = {int(r["round"]): r for r in _schedule(year)}
    idx = rounds_all.index(rnd)
    prev_rnd = rounds_all[idx - 1] if idx > 0 else None
    next_rnd = rounds_all[idx + 1] if idx < len(rounds_all) - 1 else None

    def _cell(rn, arrow, side):
        if rn is None:
            return f'<span class="rn-x rn-{side}"></span>'
        nm = rc.race_zh(sched.get(rn, {}).get("raceName", f"Round {rn}"))
        return (f'<a class="rn-lk rn-{side}" href="/seasons/{year}/rounds/{rn}/">'
                f'<span class="rn-dir">{arrow}</span>'
                f'<span class="rn-r mono">R{rn:02d}</span> {esc(nm)}</a>')
    return (f'<nav class="round-nav" aria-label="分站導覽">'
            f'{_cell(prev_rnd, "← 上一站", "prev")}'
            f'{_cell(next_rnd, "下一站 →", "next")}</nav>')


def render_round(year, rnd, round_paths=None, sub_paths=None):
    data = _round_results(year, rnd)
    if not data:
        raise SystemExit(f"❌ 缺 {year} R{rnd} 正賽 results（{year}-{rnd:02d}.json）")
    if sub_paths is None:
        sub_paths = subpage_paths(year)
    results = data.get("Results", [])
    sched = {int(r["round"]): r for r in _schedule(year)}
    srow = sched.get(rnd, {})
    circ = srow.get("Circuit", {}) or data.get("Circuit", {}) or {}
    loc = circ.get("Location", {})
    race_name = data.get("raceName") or srow.get("raceName", f"Round {rnd}")
    date = data.get("date") or srow.get("date", "")
    wiki = srow.get("url") or data.get("url", "")
    in_progress = not fs._is_completed(year)

    canonical = f"{BASE}/seasons/{year}/rounds/{rnd}/"
    overview_url = f"{BASE}/seasons/{year}/"
    race_disp = rc.race_pair(race_name)
    circ_disp = rc.circuit_pair(circ.get("circuitId", ""), circ.get("circuitName", "")) if circ else ""

    winner = next((r for r in results if (r.get("positionText") or r.get("position")) == "1"), None)
    w_name_txt = ""
    if winner:
        wdrv = winner.get("Driver", {})
        w_name_txt = name_plain(zh_driver(wdrv.get("driverId", "")), _driver_full(wdrv))

    # Hero / 麵包屑
    crumbs = (f'<nav class="crumbs" aria-label="breadcrumb">'
              f'<a href="/">首頁</a><span>›</span>'
              f'<a href="/seasons/">賽季</a><span>›</span>'
              f'<a href="/seasons/{year}/">{year}</a><span>›</span>'
              f'<span class="cur">R{rnd:02d}</span></nav>')
    ident_bits = [f'<span>第 <span class="mono">{rnd}</span> 站</span>']
    if circ_disp:
        ident_bits.append(f'<span>賽道 {circ_disp}</span>')
    if loc.get("country"):
        locality = f'{loc.get("locality")}・' if loc.get("locality") else ""
        ident_bits.append(f'<span>{esc(locality)}{esc(loc["country"])}</span>')
    if date:
        ident_bits.append(f'<span>日期 <span class="mono">{esc(date)}</span></span>')
    ip_tag = '<span class="ip-tag">進行中</span>' if in_progress else ""
    hero = f"""<div class="ent-hero">
  <p class="ent-kicker">分站 · {year} Season · Round {rnd}</p>
  <h1 class="ent-h1">{race_disp}<span class="sub-year">　{year}</span>{ip_tag}</h1>
  <div class="ident">
    <span>賽季 <a href="{overview_url}">{year} 總覽</a></span>
    {"".join(ident_bits)}
  </div>
</div>"""

    nav = _round_nav(year, rnd)
    podium = _podium_block(year, rnd)
    results_table = _round_full_results_table(year, rnd, sub_paths)
    sprint_html = _sprint_block(year, rnd)
    narr = "".join(f"<p>{esc(s)}</p>" for s in round_narrative(year, rnd))

    # 退賽名單（is_classified 判定；誠實「本站無退賽」分支）
    rets = round_retirements(year, rnd)
    if rets:
        ret_items = "".join(
            f'<li title="來源檔：{esc(d["source"])}">'
            f'{esc(d["driver"])}（{team_pair(d["constructor"].get("constructorId", ""), d["constructor"].get("name", ""))}）'
            f' · <span class="rt-status">{esc(d["status"])}</span></li>'
            for d in rets)
        ret_html = (f'<p class="note">本站共 <b>{len(rets)}</b> 位車手未完賽（未列入完賽名次），'
                    'status 為賽果登記事由原文，本站不直譯退賽因果。</p>'
                    f'<ol class="detail-list">{ret_items}</ol>'
                    '<p class="note">口徑說明：本名單以官方<b>是否列入完賽名次</b>（positionText）判定；'
                    'status 登記為故障事由但仍獲完賽名次者（跑滿分類距離），列於上方名次表而不在此列。'
                    '賽季總覽的「全季退賽圖鑑」以 status 事由計數，兩者口徑不同、各自可回溯。</p>')
    else:
        ret_html = '<p class="note">本站<b>無退賽</b>——全部參賽車手皆獲完賽名次。</p>'

    body = f"""{crumbs}
{hero}
{nav}

<div class="sec-title">頒獎台</div>
{podium}

<div class="sec-title">賽況速寫</div>
<div class="narrative">{narr}</div>

<div class="sec-title">正賽完整名次</div>
<p class="note">{year} {race_disp}正賽全部參賽車手名次。名次欄為官方 positionText 原樣（<span class="rt-status">R</span>＝退賽、<span class="rt-status">D</span>＝取消資格、<span class="rt-status">W</span>＝未出賽等）；發車位、圈數、積分與 status 皆逐字取自官方賽果檔。有該季子頁的車手／車隊名<b>可點</b>進入其賽季視角頁。</p>
{results_table}
{sprint_html}

<div class="sec-title">退賽名單</div>
{ret_html}

<p class="note">本頁為 {year} 賽季第 {rnd} 站的單場分站頁。所有數字直接取自官方正賽{('與衝刺賽 ' if sprint_html else '')}賽果檔，可回溯來源；回到 <a href="{overview_url}">{year} 賽季總覽</a>。</p>
"""

    # JSON-LD：BreadcrumbList ＋ 單一 SportsEvent（name/startDate/location Place＋geo/sameAs 維基）
    events = _race_event_nodes(year, [srow] if srow else [], canonical)
    for ev in events:
        ev["@id"] = f"{canonical}#event"
        ev["url"] = canonical
        ev["isPartOf"] = {"@id": f"{BASE}/#website"}  # 掛在 graph 內真實 website 節點（非 dangling #page）
    jsonld = rc.graph_ld(
        [rc.org_node(), rc.website_node(),
         rc.breadcrumb_node([("首頁", f"{BASE}/"), ("賽季", f"{BASE}/seasons/"),
                             (f"{year} 賽季", overview_url), (f"R{rnd:02d}", canonical)])]
        + events)
    win_txt = f"{w_name_txt} 奪冠，" if w_name_txt else ""
    desc = (f"{year} {rc.race_zh(race_name)}（第 {rnd} 站）正賽完整名次、頒獎台、"
            f"{'衝刺賽、' if sprint_html else ''}退賽名單與賽況速寫，{win_txt}每個數字可回溯官方賽果。")
    html = rc.page_shell(f"{year} {rc.race_zh(race_name)}｜第 {rnd} 站賽果",
                         desc, canonical, jsonld, body,
                         active="", extra_css=p0.ENTITY_CSS + SEASON_CSS)
    out = PUB / "seasons" / str(year) / "rounds" / str(rnd)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ /seasons/{year}/rounds/{rnd}/　{rc.race_zh(race_name)} · "
          f"{len(results)} 車 · {len(rets)} 退賽{' · sprint' if sprint_html else ''}")
    return canonical


# ---------- 賽季頁專屬 CSS（走 page_shell 的 extra_css，不進 SHARED_CSS_TEXT） ----------
# 與 phase0 ENTITY_CSS 併用；只新增索引/敘事/退賽橫條圖需要的樣式，零圖檔零 JS。
SEASON_CSS = """
.dim{color:var(--faint)}
.ip{color:var(--accent);font-weight:700;font-size:12.5px}
.ip-tag{display:inline-block;margin-left:10px;padding:2px 9px;border-radius:11px;background:var(--accent);color:#fff;font-size:12px;font-weight:800;font-family:'Chakra Petch',sans-serif;vertical-align:middle}
.ip-banner{margin:8px 0 2px;padding:9px 14px;border-radius:8px;background:var(--surface-2);border-left:3px solid var(--accent);font-size:13px;color:var(--fg-soft);line-height:1.7}
.narrative{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:8px;padding:14px 18px;margin:10px 0}
.narrative p{font-size:14.5px;color:var(--fg-soft);line-height:1.9;margin:0 0 6px}
.narrative p:last-child{margin-bottom:0}
.rt-chart{display:flex;flex-direction:column;gap:6px;margin:10px 0}
details.rt{background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden}
details.rt>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:12px;padding:9px 14px}
details.rt>summary::-webkit-details-marker{display:none}
details.rt>summary::before{content:'▸';color:var(--dim);font-size:11px;flex:none;transition:transform .15s}
details.rt[open]>summary::before{transform:rotate(90deg)}
.rt-label{flex:none;width:150px;font-size:13px;color:var(--fg);font-weight:600}
.rt-en{color:var(--faint);font-size:11px;font-weight:500}
.rt-bar{flex:1;height:14px;background:var(--surface-2);border-radius:7px;overflow:hidden;min-width:60px}
.rt-fill{display:block;height:100%;background:var(--accent);border-radius:7px}
.rt-n{flex:none;width:34px;text-align:right;color:var(--accent);font-weight:800;font-size:14px;font-variant-numeric:tabular-nums}
.rt-detail{margin:2px 14px 12px;max-height:260px}
.rt-status{font-family:'Chakra Petch',monospace;color:var(--dnf);font-size:12px}
@media(max-width:640px){.rt-label{width:104px;font-size:12px}.rt-en{display:block}}
.champ-chart{width:100%;height:auto;background:var(--surface);border:1px solid var(--line);border-radius:10px;margin:8px 0;padding:6px 4px}
.cc-grid{stroke:var(--line-2);stroke-width:1;stroke-dasharray:3 3}
.cc-axis{fill:var(--faint);font-size:11px;font-family:'Chakra Petch',monospace;font-variant-numeric:tabular-nums}
.cc-xlab{fill:var(--faint);font-size:10px;font-family:'Chakra Petch',monospace}
.cc-name{font-size:13px;font-weight:750;font-family:'Chakra Petch',sans-serif}
.cc-pts{font-size:11px;font-weight:600;font-variant-numeric:tabular-nums;opacity:.85}
tr.brk td{padding-top:0;padding-bottom:9px;border-top:none}
.brk-txt{font-size:11.5px;color:var(--faint);line-height:1.6}
.brk-txt b{color:var(--fg-soft);font-variant-numeric:tabular-nums;font-family:'Chakra Petch',monospace}
.brk-txt .zh-en{font-size:.82em}
.crumbs{display:flex;flex-wrap:wrap;align-items:center;gap:6px;font-size:12.5px;color:var(--faint);margin:2px 0 14px}
.crumbs a{color:var(--accent);text-decoration:none}
.crumbs a:hover{text-decoration:underline}
.crumbs span{color:var(--line-2)}
.crumbs .cur{color:var(--fg-soft);font-weight:600}
.ent-h1 .sub-year{font-size:.5em;color:var(--dim);font-weight:700;font-family:'Chakra Petch',monospace}
.round-nav{display:flex;justify-content:space-between;gap:10px;margin:2px 0 18px}
.rn-lk{flex:1;display:flex;flex-direction:column;gap:2px;text-decoration:none;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:9px 14px;font-size:13px;color:var(--fg);max-width:48%}
.rn-lk:hover{border-color:var(--accent);color:var(--accent)}
.rn-next{align-items:flex-end;text-align:right}
.rn-dir{font-size:11px;color:var(--accent);font-family:'Chakra Petch',monospace;letter-spacing:.04em}
.rn-r{color:var(--faint);font-size:11px;margin-right:4px}
.rn-x{flex:1;max-width:48%}
.podium{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:12px 0 4px}
.pod{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;border-top:3px solid var(--line-2)}
.pod-1{border-top-color:var(--accent);box-shadow:0 1px 3px var(--sheet-shadow)}
.pod-rk{font-size:13px;font-weight:800;color:var(--fg-soft);font-family:'Chakra Petch',sans-serif}
.pod-nm{font-size:16px;font-weight:750;margin:8px 0 2px;color:var(--fg)}
.pod-tm{font-size:12.5px;color:var(--fg-soft)}
.pod-pt{font-size:13px;color:var(--accent);font-weight:700;margin-top:6px;font-variant-numeric:tabular-nums}
@media(max-width:520px){.round-nav{flex-direction:column}.rn-lk,.rn-x{max-width:none}.rn-next{align-items:flex-start;text-align:left}}
"""


# ---------- CLI ----------

def _render_one_season(year, urls, round_years=frozenset()):
    """單季總覽＋其 seed 子頁（有實體頁且該季有參賽者，防頁數爆炸）。
    year ∈ round_years：另生成該季分站頁（只做有正賽 results 的站），並把總覽／子頁的
    站次交叉連往分站頁（同 gate）。"""
    round_paths = round_page_paths(year) if year in round_years else None
    urls.append(render_season(year, round_paths))
    dids, cids = season_subpage_entities(year)  # <1958：cids 為空→無車隊子頁（Σ gate 無 oracle）
    for did in dids:
        urls.append(render_driver_subpage(year, did, round_paths))
    for cid in cids:
        urls.append(render_team_subpage(year, cid, round_paths))
    if year in round_years:
        sub_paths = subpage_paths(year)
        for rnd in season_round_numbers(year):
            urls.append(render_round(year, rnd, round_paths, sub_paths))


def main():
    ap = argparse.ArgumentParser(description="產出 /seasons/ 索引與賽季頁（M3→M4）。")
    ap.add_argument("--season", type=int, default=2002, help="要建的單一賽季頁年份（預設 2002）")
    ap.add_argument("--all", action="store_true",
                    help="展開全部 77 季（1950–2026）：索引＋各季總覽＋各季 seed 子頁")
    ap.add_argument("--index-only", action="store_true", help="只重建 /seasons/ 索引")
    ap.add_argument("--rounds-for", type=int, nargs="+", metavar="YEAR", default=None,
                    help="為指定季生成單場分站頁 /seasons/<year>/rounds/<n>/（只生成有正賽 results 的站）。"
                         "省略＝用 config/encyclopedia.json 的 round_years（單一來源）；"
                         "pipeline 無需再明列，改設定即可。")
    ap.add_argument("--publish", action="store_true",
                    help="公開時才加：寫 data/sitemap-parts/seasons.txt（預設不寫，頁面未公開前不進 sitemap）")
    ap.add_argument("--no-sitemap", action="store_true", help="顯式關閉 sitemap part（與預設同義，供 pipeline 明示）")
    args = ap.parse_args()

    # round_years 單一來源＝config/encyclopedia.json：
    #   明列 --rounds-for → 以 CLI 為準（含空集覆寫，供測試/除錯）
    #   --all（pipeline 模式）省略 → 用 config round_years（不再硬編 --rounds-for 2002 2026）
    #   單季 debug 模式省略 → 空集（不自動產分站頁，保留既有預設行為）
    if args.rounds_for is not None:
        round_years = set(args.rounds_for)
    elif args.all:
        round_years = set(rc.ROUND_YEARS)
    else:
        round_years = set()
    print("賽季頁：")
    if args.all:
        # --all：索引連全部 77 季（built_years＝全域）；再逐季（新到舊）產總覽＋子頁（＋分站頁）
        built = set(range(FIRST_YEAR, LAST_YEAR + 1))
        urls = [render_index(built)]
        if not args.index_only:
            for year in range(LAST_YEAR, FIRST_YEAR - 1, -1):
                _render_one_season(year, urls, round_years)
    else:
        urls = [render_index()]
        if not args.index_only:
            _render_one_season(args.season, urls, round_years)

    if args.publish and not args.no_sitemap:
        rc.write_sitemap_part("seasons", urls)
    else:
        print("  ⏸  未寫 sitemap part（預設）：頁面未公開前不讓 URL 進 sitemap；公開時改用 --publish。")
    print(f"共 {len(urls)} 頁。")


if __name__ == "__main__":
    main()
