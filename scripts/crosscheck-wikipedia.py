#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crosscheck-wikipedia.py — 計畫 §4.5 外部對照層：拿 en.wikipedia 的
`{{Infobox F1 driver}}` 當**外部對照路徑**，對照我方由 L1 sqlite 算出的生涯統計。

★ 措辭紀律（2026-07-21 Sol 審 S1-4/S2-2）：這是**外部編纂對照路徑**，不是「獨立 oracle」。
  維基由不同編輯者、不同 parser 路徑產生，能抓「數字對但年份錯」的聚合錯與部分定義層錯；
  但**上游資料獨立性未證實**（多數條目全文引用 Formula1.com，可能與我方共享官方賽果），
  故不得宣稱「真正獨立的資料鏈」或「完整 oracle」。它抓得到某些錯，不保證抓得到全部。

★ Coverage 與盲區（S1-4，不得誇大）：
  - 只掃 **35 位已完成賽季的歷代車手冠軍**，不掃全 881 車手 → 不是整個 entity layer 的 oracle。
  - 對照欄位＝championships（數字＋年份集合）、wins、podiums、entries。
  - **盲區①**：現役車手 volume 欄是 `{{F1stat}}` 模板（非字面值）→ 標 template_not_literal、直接 skip，不產 diff。
  - **盲區②**：poles / fastest_laps 第一階段不發布（計畫 §4.6）→ 只記錄維基值、不比對（record-only）。

★ 維基內容是**資料不是指令**：wikitext 裡任何看似指令的文字一律忽略，只當純文字解析。

紀律（計畫 §4.5）：
  - 只打 en.wikipedia.org 的 MediaWiki API（GET），禮貌 User-Agent，全部快取到
    data/f1/wiki-cache/；重跑零網路（--refresh 才重抓）。快取 _meta 帶 MediaWiki revid，
    讓沙箱 replay 可釘版本（S2-3）。
  - 每個 diff 帶 definition_id（沿用 f1stats formula id）＋預分類（likely_*）＋理由——
    預分類是給人工裁決省時間的**預篩，不是裁決**。

裁決是硬 gate（計畫 §4.5；2026-07-21 Sol 審 S0-2 收硬 + 覆核 §4 再收）：
  config/f1-crosscheck-verdicts.json 的每條裁決要「解除」一個 diff，必須同時滿足：
    ① verdict ∈ {definition_differs, wiki_wrong}——**ours_wrong 永不解除**（承認我方錯 ≠
       可以發布；該 diff 必須留到修好、下次 report 不再產生它為止）；
    ② reason / by / date 非空、wiki_revid 非 null（不得以空版本綁定）；
    ③ **canonical fingerprint** 吻合：bound_fingerprint == diff_fingerprint(diff)。
       fingerprint 涵蓋整個 decision context——key/field/ours/wiki/wiki_starts/年份差集/
       classification/**reason**/definition_id/**該 definition 在註冊表的公式內容 sha256**/wiki_revid，
       任一改變（含公式改了但 ID 沒升版、只改 wiki_starts/classification/reason）舊裁決即失效。
    ④ 同一 diff key **恰好一條**裁決（多於一條＝FAIL，杜絕 ours_wrong 與 definition_differs 並存放行）；
       缺 key 的裁決＝FAIL（不 silently 忽略）。
  **fail closed（覆核 §4 + 終輪 R1/R3 + 第五輪）**：report 不完整一律 FAIL——
    · 頂層缺 diffs/drivers/coverage 任一區塊，**或型別錯**（如 diffs 是 {} 不是 list，不得 silently 轉空）；
    · 每筆 driver 需非空 driver_id、每筆 diff 需非空 key；
    · 車手抓取/解析失敗、infobox 缺失；
    · **身分（非只列數）**：成功車手 driver_id 集合須與 coverage.expected_champion_ids exact-set 相等，
      且 rows==unique（重複列/漏人/多人皆 FAIL）；**default 與 --gate-only 都從 DB 現算集合比對**，
      report 自報 manifest 不可自證（db 缺席＝FAIL closed）；
    · expected_champion_count 必須 == len(unique expected_champion_ids)、manifest 內不得有重複 id；
    · **diff key 必須唯一**（同一 diff 複製一筆＝FAIL）；verdict 缺 key＝FAIL；
    · diff 缺 definition_id 或 definition_id 未在註冊表、diff.wiki_revid=null。
  指向「已不存在的 diff」的裁決＝stale，比照 invariants exact-set 整體 FAIL。
  → passed 僅在「零未解 diff、零 stale、零 report fault」時成立。
  本腳本**永不寫入裁決**（裁決是人的事）；只讀取、驗證。

gen-racing-drivers.py 接線（前置 gate；目前該檔尚未建，先在此定義契約）：
  產出頁面前應呼叫 `crosscheck-wikipedia.py --gate-only`，exit 0 才可續；exit 1 一律中止。
  與 invariants、golden 三 gate 並列，任一非零都不得產頁。

用法：
  python3 scripts/crosscheck-wikipedia.py                 # 抓/讀快取→對照→寫報告→跑硬 gate（未解 diff 或 stale 裁決 exit 1）
  python3 scripts/crosscheck-wikipedia.py --driver senna  # 名單外附加指定車手
  python3 scripts/crosscheck-wikipedia.py --report-only    # 只產報告，永遠 exit 0（迭代用）
  python3 scripts/crosscheck-wikipedia.py --gate-only      # 不抓網路，只對現有報告＋裁決檔跑硬 gate
  python3 scripts/crosscheck-wikipedia.py --refresh        # 忽略快取重抓（回填 revid；數值變動會如實列出）
"""
import argparse
import datetime as _dt
import hashlib
import json
import pathlib
import re
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # CI ubuntu 有系統 CA，macOS python.org 版靠 certifi
    SSL_CTX = ssl.create_default_context()

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "f1" / "raw"
DEFAULT_DB = ROOT / "data" / "f1" / "db.sqlite"
DRIVERS_JSON = RAW / "entities" / "drivers.json"
WIKI_CACHE = ROOT / "data" / "f1" / "wiki-cache"
VERDICTS = ROOT / "config" / "f1-crosscheck-verdicts.json"
REPORT = ROOT / "data" / "f1" / "crosscheck-report.json"

API = "https://en.wikipedia.org/w/api.php"
UA = "racing-tools/1.0 (racing.twtools.cc; non-commercial encyclopedia crosscheck)"

# 合法裁決值（§4.5 三分類）
VALID_VERDICTS = {"ours_wrong", "definition_differs", "wiki_wrong"}
# 「可解除 diff」的裁決值——**不含 ours_wrong**：承認我方錯不等於可以發布，
# 該 diff 必須留到資料修好、下次 report 不再產生它為止（Sol 審 S0-2 ①）。
RESOLVING_VERDICTS = {"definition_differs", "wiki_wrong"}
# 產 diff 的欄位；poles/fastest_laps 只記錄不比對（計畫 §4.6 第一階段不發布）
RECORD_ONLY_FIELDS = ("poles", "fastest_laps")

# definition_id 註冊表（S1-3）：沿用 f1stats.py 的 formula id，讓裁決綁定「用哪個定義算的」。
# 每個對照欄位對應一個 definition_id；裁決 bound 的 definition_id 必須與 report 相符才生效。
# ⚠️ entries 用 results_distinct_races（不重複、有賽果紀錄的場次），**不是**標準 GP entries——
#    這是遷就資料能力的口徑，維基 races 欄對此欄永遠只會產可預期 diff（Sol 審 S1-3）。
DEFINITION_REGISTRY = {
    "count_seasons_driver_standing_eq_1": {
        "formula": "count(seasons where driver_standings.position==1 and season completed)",
        "coverage": "1950-2026", "unit": "季"},
    "results_position_text_eq_1": {
        "formula": "count(results where position_text=='1')",
        "coverage": "1950-2026", "unit": "場"},
    "results_position_text_in_123": {
        "formula": "count(results where position_text in ('1','2','3'))",
        "coverage": "1950-2026", "unit": "場"},
    "results_distinct_races": {
        "formula": "count(distinct season-round where a results row exists)",
        "coverage": "1950-2026", "unit": "場",
        "caveat": "不重複、有賽果紀錄的場次；非標準 GP entries（不含未過排位/未起跑）"},
}
# report 的每個 diff field → definition_id
FIELD_DEFINITION_ID = {
    "championships_count": "count_seasons_driver_standing_eq_1",
    "championships_years": "count_seasons_driver_standing_eq_1",
    "wins": "results_position_text_eq_1",
    "podiums": "results_position_text_in_123",
    "entries": "results_distinct_races",
}

# 模組級網路計數：用來證明「第二次跑零網路請求」
NET_REQUESTS = 0


# ---------------------------------------------------------------------------
# MediaWiki API 取 wikitext（帶退避 + 快取）
# ---------------------------------------------------------------------------

def _title_from_url(url):
    """從 Ergast 帶的 en.wikipedia URL 取條目標題（保留底線，URL-decode）。"""
    frag = url.split("/wiki/", 1)[1]
    return urllib.parse.unquote(frag)


def fetch_wikitext_api(title):
    """打 MediaWiki API 取條目最新版 wikitext。回 (wikitext, http_status, resolved_title, revid)。只 GET。

    帶 redirects=1：Ergast 的 URL 常指向重導頁（Nino_Farina→Giuseppe Farina、
    Alan_Jones_(Formula_1)→Alan Jones (racing driver)），API 直接解到目標頁內容。
    rvprop 帶 ids：取回該版 revid（S2-3），讓快照 replay 可釘住 Wikipedia 版本、
    裁決可綁定「當時看的是哪一版」。
    """
    global NET_REQUESTS
    q = urllib.parse.urlencode({
        "action": "query", "prop": "revisions", "rvprop": "content|ids",
        "rvslots": "main", "format": "json", "formatversion": "2",
        "redirects": "1", "titles": title})
    url = f"{API}?{q}"
    delay = 5
    for attempt in range(5):
        NET_REQUESTS += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
                data = json.loads(r.read().decode("utf-8"))
                status = r.status
            page = data["query"]["pages"][0]
            if page.get("missing"):
                raise RuntimeError(f"維基條目不存在：{title}")
            rev = page["revisions"][0]
            wt = rev["slots"]["main"]["content"]
            revid = rev.get("revid")
            return wt, status, page.get("title", title), revid
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                ra = e.headers.get("Retry-After")
                s = int(ra) if (ra or "").isdigit() else delay
                print(f"  ⏳ HTTP {e.code} {title} → {s}s", flush=True)
                time.sleep(s)
                delay = min(delay * 2, 180)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < 4:
                print(f"  ⏳ net err {title} → {delay}s", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 180)
                continue
            raise


def get_wikitext(driver_id, title, url, cache_dir=WIKI_CACHE, refresh=False, pause=0.2):
    """取 wikitext；優先讀快取，快取命中零網路。回 (wikitext, from_cache, revid)。

    revid 從快取 _meta.revid 讀（舊快取無此欄則回 None，提示需 --refresh 回填）。
    """
    cache_dir = pathlib.Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"{driver_id}.json"
    if cf.exists() and not refresh:
        blob = json.loads(cf.read_text(encoding="utf-8"))
        return blob["wikitext"], True, blob.get("_meta", {}).get("revid")
    if pause:
        time.sleep(pause)  # 禮貌節流
    wt, status, resolved, revid = fetch_wikitext_api(title)
    blob = {"_meta": {"driver_id": driver_id, "title": title,
                      "resolved_title": resolved, "url": url,
                      "http_status": status, "revid": revid,
                      "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat()},
            "wikitext": wt}
    cf.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return wt, False, revid


# ---------------------------------------------------------------------------
# {{Infobox F1 driver}} 解析（容錯，計畫 §4.5）
# ---------------------------------------------------------------------------

def find_infobox(wikitext):
    """回傳 `{{Infobox F1 driver … }}` 整塊（含外層大括號），找不到回 None。

    以大括號配對切出整塊——這樣巢狀的 `module2 = {{Infobox Le Mans driver …}}`
    會整個被包在裡面（其內層參數屬更深 depth，parse_params 不會誤取）。
    """
    m = re.search(r"\{\{\s*Infobox\s+F1\s+driver", wikitext, re.IGNORECASE)
    if not m:
        return None
    i = m.start()
    depth = 0
    j = i
    while j < len(wikitext) - 1:
        two = wikitext[j:j + 2]
        if two == "{{":
            depth += 1
            j += 2
            continue
        if two == "}}":
            depth -= 1
            j += 2
            if depth == 0:
                return wikitext[i:j]
            continue
        j += 1
    return wikitext[i:]  # 沒配對到（罕見/截斷）——回到結尾，寧可多不要少


def parse_params(infobox):
    """把 infobox 頂層 `| key = value` 解析成 dict。

    只切**頂層** `|`（相對 infobox 內部 depth 0 的分隔符），因此
      championships = 7 ({{F1|1994}}, …)   裡 {{F1|1994}} 的 `|` 在 depth≥1 不會誤切；
      module2 = {{Infobox Le Mans driver | … }}  整個是一個參數值（內層 pipe 不外洩）。
    depth 同時計 `{{}}` 與 `[[]]`（維基連結內也可能有 `|`，如 [[a|b]]）。
    """
    body = infobox
    if body.startswith("{{"):
        body = body[2:]
    if body.endswith("}}"):
        body = body[:-2]
    parts, buf, depth = [], [], 0
    k = 0
    while k < len(body):
        two = body[k:k + 2]
        if two in ("{{", "[["):
            depth += 1
            buf.append(two)
            k += 2
            continue
        if two in ("}}", "]]"):
            depth = max(0, depth - 1)
            buf.append(two)
            k += 2
            continue
        ch = body[k]
        if ch == "|" and depth == 0:
            parts.append("".join(buf))
            buf = []
            k += 1
            continue
        buf.append(ch)
        k += 1
    parts.append("".join(buf))

    params = {}
    for seg in parts[1:]:  # parts[0] 是模板名（"Infobox F1 driver\n"）
        if "=" not in seg:
            continue
        key, _, val = seg.partition("=")
        # key 正規化：小寫、底線→空白、collapse 空白（fastest_laps / "fastest laps" 一致）
        nkey = re.sub(r"\s+", " ", key.strip().lower().replace("_", " ")).strip()
        params[nkey] = val.strip()
    return params


def _strip_noise(v):
    """去掉 <ref>…</ref>、<!--…-->、{{cn}} 這類雜訊，方便抓字面數字。"""
    v = re.sub(r"<ref[^>]*?/>", "", v, flags=re.I)
    v = re.sub(r"<ref.*?</ref>", "", v, flags=re.I | re.S)
    v = re.sub(r"<!--.*?-->", "", v, flags=re.S)
    return v.strip()


def is_f1stat_template(v):
    """現役車手 volume 欄常見 `{{F1stat|NOR|wins}}` → 非字面值。"""
    return bool(re.search(r"\{\{\s*F1stat\b", v, re.IGNORECASE))


def parse_int_field(value):
    """解析 wins/podiums/poles/fastest_laps 這種數值欄。

    回 dict：{"template_not_literal": bool, "value": int|None, "raw": 原值}
    """
    raw = value
    if is_f1stat_template(value):
        return {"template_not_literal": True, "value": None, "raw": raw}
    clean = _strip_noise(value)
    m = re.search(r"-?\d[\d,]*", clean)
    val = int(m.group(0).replace(",", "")) if m else None
    return {"template_not_literal": False, "value": val, "raw": raw}


def parse_races_field(value):
    """races 欄形如 `308 (306 starts)` 或 `{{F1stat|NOR|entries}} (…)`。

    entries = 括號前的數字；starts = 括號內 `N starts` 的數字（僅記錄）。
    回 {"template_not_literal","entries":int|None,"starts":int|None,"raw"}
    """
    raw = value
    if is_f1stat_template(value):
        return {"template_not_literal": True, "entries": None, "starts": None, "raw": raw}
    clean = _strip_noise(value)
    head = clean.split("(", 1)[0]
    me = re.search(r"-?\d[\d,]*", head)
    entries = int(me.group(0).replace(",", "")) if me else None
    ms = re.search(r"(\d[\d,]*)\s*starts", clean, re.IGNORECASE)
    starts = int(ms.group(1).replace(",", "")) if ms else None
    return {"template_not_literal": False, "entries": entries, "starts": starts, "raw": raw}


def parse_championships_field(value):
    """championships 欄形如 `7 ({{F1|1994}}, {{F1 |2001}}, …)`。

    容錯：`{{F1 |2001}}` 有多餘空白（計畫 §4.5 明列）。
    回 {"template_not_literal","count":int|None,"years":[int],"raw"}
    """
    raw = value
    tnl = is_f1stat_template(value)
    clean = _strip_noise(value)
    # 前導數字＝維基聲稱的冠軍數（現役也常是字面 "1"，即使 volume 欄是模板）
    mc = re.search(r"-?\d[\d,]*", clean.split("(", 1)[0])
    count = int(mc.group(0).replace(",", "")) if mc else None
    # 年份：{{F1|YYYY}} / {{F1 |YYYY}}（多餘空白容錯）；去重保序
    years, seen = [], set()
    for y in re.findall(r"\{\{\s*F1\s*\|\s*(\d{4})\s*\}\}", clean, re.IGNORECASE):
        yi = int(y)
        if yi not in seen:
            seen.add(yi)
            years.append(yi)
    # 後備：若沒有 {{F1|…}} 但括號內列了裸年份
    if not years:
        for y in re.findall(r"\b(19\d{2}|20\d{2})\b", clean.split("(", 1)[-1]):
            yi = int(y)
            if yi not in seen:
                seen.add(yi)
                years.append(yi)
    return {"template_not_literal": tnl, "count": count, "years": sorted(years), "raw": raw}


def parse_infobox(wikitext):
    """整合：回 {"found":bool, 各欄解析結果}。found=False 代表沒有 F1 driver infobox。"""
    box = find_infobox(wikitext)
    if box is None:
        return {"found": False}
    p = parse_params(box)
    out = {"found": True}
    out["championships"] = parse_championships_field(p.get("championships", ""))
    out["wins"] = parse_int_field(p.get("wins", ""))
    out["podiums"] = parse_int_field(p.get("podiums", ""))
    out["entries"] = parse_races_field(p.get("races", ""))
    out["poles"] = parse_int_field(p.get("poles", ""))
    out["fastest_laps"] = parse_int_field(p.get("fastest laps", ""))
    return out


# ---------------------------------------------------------------------------
# 我方值：由 L1 sqlite 算（定義同 f1stats.py 的 formula id，覆蓋全 35 冠軍）
# ---------------------------------------------------------------------------

def champion_ids(cur):
    """歷代車手冠軍：driver_standings position=1 且該季 completed（比照 I10）。"""
    return [r[0] for r in cur.execute(
        "SELECT DISTINCT ds.driver_id FROM driver_standings ds "
        "JOIN seasons s ON s.year=ds.season "
        "WHERE ds.position=1 AND s.status='completed' ORDER BY ds.driver_id")]


def db_champion_ids(db_path=DEFAULT_DB):
    """從 DB 現算歷代冠軍身分集合（排序）。gate 用它當權威 manifest，report 自報值不可自證（R1）。"""
    con = sqlite3.connect(str(db_path))
    try:
        return sorted(champion_ids(con.cursor()))
    finally:
        con.close()


def our_championship_years(cur, did):
    """冠軍年份集合＝該車手在 completed 賽季拿到 driver_standings position=1 的年份。

    定義同 f1stats.driver_championships（count_seasons_driver_standing_eq_1）。
    """
    return [r[0] for r in cur.execute(
        "SELECT ds.season FROM driver_standings ds JOIN seasons s ON s.year=ds.season "
        "WHERE ds.driver_id=? AND ds.position=1 AND s.status='completed' "
        "ORDER BY ds.season", (did,))]


def our_counts(cur, did):
    """wins/podiums/entries，定義逐字對齊 f1stats.driver_career 的 formula：
       wins=results_position_text_eq_1、podiums=..._in_123、entries=results_row_exists。
    另回 first/last season 供預分類判斷世代（shared-drive era）。
    """
    wins = cur.execute("SELECT count(*) FROM results WHERE driver_id=? AND position_text='1'", (did,)).fetchone()[0]
    podiums = cur.execute("SELECT count(*) FROM results WHERE driver_id=? AND position_text IN ('1','2','3')", (did,)).fetchone()[0]
    # 出賽＝不重複場次（共駕一場兩列計一場），與 f1stats.results_distinct_races 同口徑
    entries = cur.execute(
        "SELECT count(DISTINCT season || '-' || round) FROM results WHERE driver_id=?",
        (did,)).fetchone()[0]
    span = cur.execute("SELECT min(season), max(season) FROM results WHERE driver_id=?", (did,)).fetchone()
    return {"wins": wins, "podiums": podiums, "entries": entries,
            "first_season": span[0], "last_season": span[1]}


# ---------------------------------------------------------------------------
# 比對 + 預分類（§4.5：預篩不是裁決）
# ---------------------------------------------------------------------------

def _classify_volume(field, ours, wiki, ctx):
    """wins/podiums 的 diff 預分類。"""
    early = (ctx.get("first_season") or 9999) <= 1960
    if ours > wiki:
        if early:
            return ("likely_definition_differs",
                    f"我方{field}({ours})高於維基({wiki})；此車手 1950s 出賽，"
                    f"很可能是 shared-drive 額外勝場/頒獎台列的口徑差（明細應標 shared:true）")
        return ("unclear", f"我方{field}({ours})高於維基({wiki})，需查是否重複列或口徑差")
    return ("likely_ours_wrong",
            f"我方{field}({ours})低於維基({wiki})，偏低通常代表漏列，優先查我方明細")


def _classify_entries(ours, wiki_entries, wiki_starts, ctx):
    early = (ctx.get("first_season") or 9999) <= 1960
    hint = f"維基 races={wiki_entries}"
    if wiki_starts is not None:
        hint += f"（{wiki_starts} starts）"
    if ours == wiki_starts:
        return ("likely_definition_differs",
                f"我方 entries({ours}) 等於維基的 starts({wiki_starts})——口徑差："
                f"我方逐 results 列計數＝起跑場次，維基 races 欄取 entries（含未起跑）")
    if early and ours > (wiki_entries or 0):
        return ("likely_definition_differs",
                f"我方 entries({ours})>{hint}；1950s 常見 shared-drive/多列造成計數口徑差")
    return ("likely_definition_differs" if wiki_starts is not None else "unclear",
            f"我方 entries={ours} vs {hint}；races 欄本身含 entries/starts 兩口徑，"
            f"需確認我方 results_row_exists 對應哪一個")


def compare_driver(did, name, our_years, our_cnt, ib, wiki_revid=None):
    """回 (fields_record, diffs)。fields_record 記錄每欄我方值/維基值/是否 diff。

    wiki_revid：該條目的當前 MediaWiki revid，寫進每個 diff 供裁決綁定版本（S2-3）。
    """
    fields = {}
    diffs = []
    ctx = {"first_season": our_cnt["first_season"], "last_season": our_cnt["last_season"],
           "wiki_revid": wiki_revid}

    # -- championships：數字 + 年份集合兩條 --
    champ = ib["championships"]
    ours_n = len(our_years)
    fields["championships"] = {
        "ours_count": ours_n, "ours_years": our_years,
        "wiki_count": champ["count"], "wiki_years": champ["years"],
        "wiki_raw": champ["raw"], "template_not_literal": champ["template_not_literal"]}
    if champ["count"] is not None and champ["count"] != ours_n:
        cls, reason = ("unclear",
                       f"冠軍數不符：我方 {ours_n} vs 維基 {champ['count']}；"
                       f"需人工查賽季歸屬（這正是外部對照要抓的定義層錯）")
        diffs.append(_diff(did, name, "championships_count", ours_n, champ["count"], cls, reason))
    # 年份集合：只有當維基有列出年份才比（現役模板可能沒有）
    if champ["years"]:
        only_ours = sorted(set(our_years) - set(champ["years"]))
        only_wiki = sorted(set(champ["years"]) - set(our_years))
        if only_ours or only_wiki:
            cls = "unclear"
            reason = (f"冠軍數相同但年份集合不同（我方獨有 {only_ours}、維基獨有 {only_wiki}）——"
                      f"『數字對但年份錯』的聚合錯就長這樣，需人工逐年查"
                      if ours_n == (champ["count"] or ours_n)
                      else f"年份集合不同：我方獨有 {only_ours}、維基獨有 {only_wiki}")
            diffs.append(_diff(did, name, "championships_years",
                               our_years, champ["years"], cls, reason,
                               extra={"ours_only": only_ours, "wiki_only": only_wiki}))

    # -- wins / podiums --
    for field in ("wins", "podiums"):
        w = ib[field]
        ours_v = our_cnt[field]
        fields[field] = {"ours": ours_v, "wiki": w["value"], "wiki_raw": w["raw"],
                         "template_not_literal": w["template_not_literal"]}
        if w["template_not_literal"]:
            continue  # 現役 {{F1stat}} 模板，不硬解、不產 diff
        if w["value"] is not None and w["value"] != ours_v:
            cls, reason = _classify_volume(field, ours_v, w["value"], ctx)
            diffs.append(_diff(did, name, field, ours_v, w["value"], cls, reason))

    # -- entries（維基 races 欄）--
    e = ib["entries"]
    ours_e = our_cnt["entries"]
    fields["entries"] = {"ours": ours_e, "wiki_entries": e["entries"],
                         "wiki_starts": e["starts"], "wiki_raw": e["raw"],
                         "template_not_literal": e["template_not_literal"]}
    if not e["template_not_literal"] and e["entries"] is not None and e["entries"] != ours_e:
        cls, reason = _classify_entries(ours_e, e["entries"], e["starts"], ctx)
        diffs.append(_diff(did, name, "entries", ours_e, e["entries"], cls, reason,
                           extra={"wiki_starts": e["starts"]}))

    # -- poles / fastest_laps：只記錄，第一階段不發布 → 不產 diff（計畫 §4.6）--
    for field in RECORD_ONLY_FIELDS:
        w = ib[field]
        fields[field] = {"ours": None, "wiki": w["value"], "wiki_raw": w["raw"],
                         "template_not_literal": w["template_not_literal"],
                         "note": "第一階段不發布，僅記錄維基值不比對"}

    # 每個 diff 補綁定用欄位：definition_id（用哪個公式算的）＋ wiki_revid（看的是哪一版維基）。
    # 這兩個是硬 gate 綁定的一部分——裁決若 bound 的 definition_id/wiki_revid 與此不符即失效。
    for d in diffs:
        d["definition_id"] = FIELD_DEFINITION_ID.get(d["field"])
        d["wiki_revid"] = wiki_revid

    return fields, diffs


def _diff(did, name, field, ours, wiki, cls, reason, extra=None):
    d = {"driver_id": did, "driver_name": name, "field": field,
         "ours": ours, "wiki": wiki, "classification": cls, "reason": reason,
         "key": f"{did}|{field}"}
    if extra:
        d.update(extra)
    return d


# ---------------------------------------------------------------------------
# 報告
# ---------------------------------------------------------------------------

def build_report(db_path=DEFAULT_DB, extra_drivers=None, refresh=False, quiet=False):
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    try:
        champs = sorted(champion_ids(cur))       # DB 的 SELECT DISTINCT 結果，排序後＝身分 manifest
        expected_champion_count = len(champs)    # gate 用來驗涵蓋數是否足額（fail closed）
        ids = list(champs)
        extra_ids = []
        for d in (extra_drivers or []):
            if d not in ids:
                ids.append(d)
                extra_ids.append(d)
        drivers_meta = {r["driverId"]: r for r in
                        json.loads(DRIVERS_JSON.read_text(encoding="utf-8"))["Drivers"]}

        drivers_out, all_diffs = [], []
        n_cache = n_net = 0
        for did in ids:
            meta = drivers_meta.get(did)
            if not meta or "url" not in meta:
                drivers_out.append({"driver_id": did, "error": "drivers.json 缺 wikipedia url"})
                continue
            name = f"{meta.get('givenName','')} {meta.get('familyName','')}".strip()
            title = _title_from_url(meta["url"])
            wt, from_cache, revid = get_wikitext(did, title, meta["url"], refresh=refresh)
            n_cache += int(from_cache)
            n_net += int(not from_cache)
            if not quiet:
                print(f"  {'📦 cache' if from_cache else '🌐 net  '} {did} ({title}) rev={revid}", flush=True)
            ib = parse_infobox(wt)
            if not ib.get("found"):
                drivers_out.append({"driver_id": did, "name": name, "wikipedia_title": title,
                                    "wikipedia_url": meta["url"], "from_cache": from_cache,
                                    "wiki_revid": revid, "infobox_found": False,
                                    "error": "未找到 {{Infobox F1 driver}}"})
                continue
            our_years = our_championship_years(cur, did)
            our_cnt = our_counts(cur, did)
            fields, diffs = compare_driver(did, name, our_years, our_cnt, ib, wiki_revid=revid)
            drivers_out.append({
                "driver_id": did, "name": name, "wikipedia_title": title,
                "wikipedia_url": meta["url"], "from_cache": from_cache,
                "wiki_revid": revid, "infobox_found": True, "fields": fields})
            all_diffs.extend(diffs)
    finally:
        con.close()

    by_field, by_cls = {}, {}
    for d in all_diffs:
        by_field[d["field"]] = by_field.get(d["field"], 0) + 1
        by_cls[d["classification"]] = by_cls.get(d["classification"], 0) + 1
    tnl = sum(1 for dr in drivers_out if dr.get("infobox_found")
              for f in dr["fields"].values() if isinstance(f, dict) and f.get("template_not_literal"))

    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "source": "en.wikipedia.org MediaWiki API — {{Infobox F1 driver}}",
        "note": ("維基是**外部編纂對照路徑**（非獨立 oracle；上游可能共享官方賽果，獨立性未證實）；"
                 "能抓部分定義層/年份錯，維基自己也會錯；每個 diff 需人工具名+綁定裁決"),
        "coverage": {
            "scope": "35 位已完成賽季的歷代車手冠軍（非全 881 車手，非整個 entity layer）",
            "expected_champion_count": expected_champion_count,
            # 身分 manifest（R1）：DB SELECT DISTINCT 冠軍 id 排序後。gate 用它做 exact-set
            # 身分比對，不只比列數——藏一個重複列偽裝成足額會被抓（35 列 34 人 → FAIL）。
            "expected_champion_ids": champs,
            "extra_driver_ids": sorted(extra_ids),   # --driver 附加的非冠軍（default 為空）
            "compared_fields": ["championships(count+years)", "wins", "podiums", "entries"],
            "blind_spots": [
                "現役車手 volume 欄為 {{F1stat}} 模板 → template_not_literal，skip 不比對",
                "poles / fastest_laps 第一階段不發布 → record-only，只記錄不比對"]},
        "definition_registry": DEFINITION_REGISTRY,
        "network": {"from_cache": n_cache, "from_network": n_net,
                    "total_api_requests_this_run": NET_REQUESTS},
        "summary": {
            "drivers_checked": len(drivers_out),
            "diffs_total": len(all_diffs),
            "diffs_by_field": by_field,
            "diffs_by_classification": by_cls,
            "template_not_literal_field_count": tnl,
            "record_only_fields": list(RECORD_ONLY_FIELDS)},
        "diffs": all_diffs,
        "drivers": drivers_out,
    }


def _print_summary(rep):
    s = rep["summary"]
    print("=" * 70)
    print("維基百科外部對照報告（計畫 §4.5）")
    print("=" * 70)
    print(f"對照車手數 {s['drivers_checked']}　"
          f"快取 {rep['network']['from_cache']}　網路 {rep['network']['from_network']}　"
          f"本次 API 請求 {rep['network']['total_api_requests_this_run']}")
    print(f"diff 總數 {s['diffs_total']}")
    print(f"  依欄位　　 {s['diffs_by_field']}")
    print(f"  依預分類　 {s['diffs_by_classification']}")
    print(f"  template_not_literal 欄位數（現役車手）{s['template_not_literal_field_count']}")
    print(f"  只記錄不比對欄位 {s['record_only_fields']}（第一階段不發布）")
    if rep["diffs"]:
        print("\n最值得先看的 diff（前 12）：")
        for d in rep["diffs"][:12]:
            print(f"  [{d['classification']:24s}] {d['driver_id']}.{d['field']}: "
                  f"我方={d['ours']} 維基={d['wiki']}")


# ---------------------------------------------------------------------------
# 裁決 gate（計畫 §4.5 硬 gate）
# ---------------------------------------------------------------------------

def load_verdicts(path=VERDICTS):
    if not pathlib.Path(path).exists():
        return []
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8")).get("verdicts", [])


def _verdict_valid(v):
    """一條裁決結構完整：verdict 合法 + reason/by/date 皆非空。（僅結構，不含綁定。）"""
    return (v.get("verdict") in VALID_VERDICTS
            and str(v.get("reason", "")).strip()
            and str(v.get("by", "")).strip()
            and str(v.get("date", "")).strip())


def _registry_sha(definition_id):
    """該 definition 在註冊表的公式內容 sha256；未註冊回 None。

    綁進 fingerprint → 公式內容改了但 definition_id 沒升版，舊裁決也會失效（覆核 §4）。
    """
    reg = DEFINITION_REGISTRY.get(definition_id)
    if reg is None:
        return None
    return hashlib.sha256(
        json.dumps(reg, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def diff_fingerprint(diff):
    """canonical diff fingerprint（覆核 §4 S1 + 終輪 R2）：封印整個 decision context。

    涵蓋 key/field/ours/wiki/wiki_starts/年份差集/classification/**reason**/definition_id/
    該 definition 的公式內容 sha256/wiki_revid——任一改變舊裁決即失效。
    這比逐欄綁定強：抓得到「只改 wiki_starts/classification/reason」「公式改了 ID 沒升版」。
    ⚠️ reason 是裁決者當時看到的理由文字，屬 decision context 一部分（Sol 終輪 S1-1）。
    """
    did = diff.get("definition_id")
    payload = {
        "key": diff.get("key"),
        "field": diff.get("field"),
        "ours": diff.get("ours"),
        "wiki": diff.get("wiki"),
        "wiki_starts": diff.get("wiki_starts"),
        "ours_only": diff.get("ours_only"),
        "wiki_only": diff.get("wiki_only"),
        "classification": diff.get("classification"),
        "reason": diff.get("reason"),
        "definition_id": did,
        "definition_registry_sha256": _registry_sha(did),
        "wiki_revid": diff.get("wiki_revid"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _diff_binding_valid(diff):
    """diff 本身是否具備可被綁定裁決的最低結構（覆核 §4 fail closed）。回 (ok, why)。"""
    did = diff.get("definition_id")
    if not did:
        return False, "diff 缺 definition_id → fail closed"
    if did not in DEFINITION_REGISTRY:
        return False, f"definition_id 未在註冊表：{did} → fail closed"
    if diff.get("wiki_revid") is None:
        return False, "diff.wiki_revid=null（快取缺 revid，需 --refresh 回填）→ fail closed"
    return True, None


def _verdict_resolves(v, diff):
    """一條裁決能否「解除」某個 diff。回 (resolves: bool, why_not: str|None)。

    條件（Sol 審 S0-2 + 覆核 §4）：結構完整 + verdict∈可解除集（ours_wrong 永不解除）
    + wiki_revid 非 null + canonical fingerprint 吻合。任一不符＝不解除。
    """
    if not _verdict_valid(v):
        return False, "裁決結構不完整（verdict 非法或缺 reason/by/date）"
    if v["verdict"] == "ours_wrong":
        return False, "verdict=ours_wrong 永不解除——承認我方錯≠可發布，須修資料至 diff 消失"
    if v["verdict"] not in RESOLVING_VERDICTS:
        return False, f"verdict={v['verdict']} 不在可解除集"
    if v.get("wiki_revid") is None:
        return False, "裁決 wiki_revid=null——不得以空版本綁定（需重抓 revid 後重裁）"
    # 個別欄位先檢查，給人看得懂的錯誤訊息（fingerprint 是最終權威）
    if v.get("bound_ours") != diff.get("ours"):
        return False, f"bound_ours({v.get('bound_ours')})≠當前({diff.get('ours')})——我方值已變"
    if v.get("bound_wiki") != diff.get("wiki"):
        return False, f"bound_wiki({v.get('bound_wiki')})≠當前({diff.get('wiki')})——維基值已變"
    if v.get("definition_id") != diff.get("definition_id"):
        return False, f"definition_id 不符（{v.get('definition_id')}≠{diff.get('definition_id')}）"
    if v.get("wiki_revid") != diff.get("wiki_revid"):
        return False, f"wiki_revid({v.get('wiki_revid')})≠當前({diff.get('wiki_revid')})——維基版本已變"
    # 權威檢查：canonical fingerprint（涵蓋 wiki_starts/classification/公式內容 sha）
    want = v.get("bound_fingerprint")
    if not want:
        return False, "裁決缺 bound_fingerprint（舊格式，不接受——需重新綁定）"
    if want != diff_fingerprint(diff):
        return False, "bound_fingerprint 不符（decision context 已變：含 wiki_starts/classification/公式內容/版本）"
    return True, None


def gate_diffs(report, verdicts, db_champion_ids=None):
    """回 (passed, unresolved, stale, faults)。硬 gate（Sol 審 S0-2 + 覆核 §4 + 終輪 R1/R3）。

    passed     = 零未解 diff、零 stale 裁決、零 report fault。
    unresolved = diff 沒有被一條綁定吻合的裁決解除；每筆帶 `_gate_status`/`_gate_detail`：
                   invalid_diff / duplicate_verdict / no_verdict / ours_wrong_hold / binding_drift
    stale      = 裁決 key 指向報告中不存在的 diff → exact-set，單獨即 FAIL。
    faults     = report 級 fail-closed 問題——report 不完整不得被當成「沒有新問題」。

    db_champion_ids（R1 / 第五輪 fix1）：**權威身分集合**（build-f1-db 現算）。
      CLI 的 default 與 **--gate-only 都必須傳入**（gen-racing-drivers 管線裡 build-f1-db 先跑，
      db 必在；db 缺席由 main 判 FAIL closed）；此時 report.coverage.expected_champion_ids 必須
      與它 exact-set 相等，report 自報值不可自證。僅單元測試允許傳 None（純 schema 測試）。
    """
    faults = []

    # --- fix2：report 必須是物件，頂層 block 存在 + 型別正確（型別錯不得 silently 轉空）---
    if not isinstance(report, dict):
        return False, [], [], ["report 不是物件（dict）→ fail closed"]

    def _require(name, typ, typname):
        if name not in report:
            faults.append(f"report 缺頂層區塊 `{name}` → fail closed")
            return None
        val = report[name]
        if not isinstance(val, typ):
            faults.append(f"report.`{name}` 型別錯（需 {typname}，得 {type(val).__name__}）→ fail closed")
            return None
        return val

    diffs = _require("diffs", list, "list") or []
    drivers = _require("drivers", list, "list") or []
    cov = _require("coverage", dict, "dict") or {}
    if not isinstance(verdicts, list):
        faults.append(f"verdicts 型別錯（需 list，得 {type(verdicts).__name__}）→ fail closed")
        verdicts = []

    # --- fix2：每筆 entry 的 required 欄位驗齊 ---
    for i, dr in enumerate(drivers):
        if not isinstance(dr, dict) or not str(dr.get("driver_id", "")).strip():
            faults.append(f"drivers[{i}] 結構不正（需 dict + 非空 driver_id）→ fail closed")
    for i, d in enumerate(diffs):
        if not isinstance(d, dict) or not str(d.get("key", "")).strip():
            faults.append(f"diffs[{i}] 結構不正（需 dict + 非空 key）→ fail closed")

    # --- 覆核 §4：車手 error / infobox 缺失 ---
    for dr in drivers:
        if not isinstance(dr, dict):
            continue
        if dr.get("error"):
            faults.append(f"車手抓取/解析失敗：{dr.get('driver_id')}（{dr.get('error')}）")
        elif not dr.get("infobox_found"):
            faults.append(f"infobox 缺失：{dr.get('driver_id')}")

    # --- R1：coverage 驗「身分集合」不只驗列數 ---
    expected_count = cov.get("expected_champion_count")
    manifest_ids = cov.get("expected_champion_ids")
    extra_ids = cov.get("extra_driver_ids") or []
    ok_driver_ids = [dr.get("driver_id") for dr in drivers
                     if isinstance(dr, dict) and dr.get("infobox_found") and not dr.get("error")]
    if manifest_ids is None or expected_count is None:
        faults.append("report.coverage 缺 expected_champion_ids / expected_champion_count → fail closed")
    elif not isinstance(manifest_ids, list):
        faults.append("coverage.expected_champion_ids 型別錯（需 list）→ fail closed")
    else:
        # manifest 自身唯一
        if len(manifest_ids) != len(set(manifest_ids)):
            dups = sorted({i for i in manifest_ids if manifest_ids.count(i) > 1})
            faults.append(f"expected_champion_ids 內有重複 id → fail closed：{dups}")
        # fix4：count 必須等於 unique ids 數（不只驗存在）
        if expected_count != len(set(manifest_ids)):
            faults.append(f"expected_champion_count({expected_count}) != "
                          f"len(unique expected_champion_ids)({len(set(manifest_ids))}) → fail closed")
        # fix1/R1：report 自報 manifest 必須與 DB 現算集合 exact-set 相等（不可自證）
        if db_champion_ids is not None and set(manifest_ids) != set(db_champion_ids):
            miss = sorted(set(db_champion_ids) - set(manifest_ids))
            ext = sorted(set(manifest_ids) - set(db_champion_ids))
            faults.append(f"coverage.expected_champion_ids 與 DB 現算冠軍集合不符（DB 缺 {miss}、多 {ext}）")
        # 允許集合＝冠軍 manifest ∪ --driver 附加（default 時 extra 為空 → 純冠軍集合）
        allowed = set(manifest_ids) | set(extra_ids)
        rows = len(ok_driver_ids)
        uniq = set(ok_driver_ids)
        if rows != len(uniq):
            dups = sorted({i for i in ok_driver_ids if ok_driver_ids.count(i) > 1})
            faults.append(f"成功車手有重複列（rows={rows} != unique={len(uniq)}）：{dups}")
        if uniq != allowed:
            missing = sorted(allowed - uniq)
            extra = sorted(uniq - allowed)
            faults.append(f"成功車手身分集合 != 預期（缺 {missing}、多 {extra}）——身分 exact-set 失敗")

    # --- verdict schema + 同 key 恰好一條（建 dict 前先驗）---
    verdicts_by_key = {}
    for i, v in enumerate(verdicts):
        if not isinstance(v, dict) or "key" not in v or not str(v.get("key", "")).strip():
            faults.append(f"裁決缺 key 或結構不正（第 {i} 條）→ fail closed（不 silently 忽略）")
            continue
        verdicts_by_key.setdefault(v["key"], []).append(v)
    for k, lst in verdicts_by_key.items():
        if len(lst) > 1:
            faults.append(f"同 key 多筆裁決（需恰好一條）：{k}（{len(lst)} 筆）")

    # --- fix3：diff key 唯一性（建 diff_by_key 前驗；同一 diff 複製成第 N 筆必 FAIL）---
    diff_keys = [d.get("key") for d in diffs if isinstance(d, dict) and d.get("key")]
    dup_diff_keys = sorted({k for k in diff_keys if diff_keys.count(k) > 1})
    if dup_diff_keys:
        faults.append(f"diff key 重複（需唯一）：{dup_diff_keys} → fail closed")

    # --- F1（Sol 五輪）：diff 身分欄自洽——key 必須恰為 driver_id|field ---
    # 反證：把 ascari|entries 那筆的 driver_id 改成 alonso、key 不動，裁決照樣解除
    # → report 內部矛盾 false green。key 是裁決綁定的錨，身分欄不得與錨脫鉤。
    for d in diffs:
        if not isinstance(d, dict) or not str(d.get("key", "")).strip():
            continue  # 結構不正者已由上方 schema fault 記錄
        _did = str(d.get("driver_id", "")).strip()
        _fld = str(d.get("field", "")).strip()
        if not _did or not _fld:
            faults.append(f"diff 缺 driver_id/field（key={d['key']}）→ fail closed")
        elif d["key"] != f"{_did}|{_fld}":
            faults.append(
                f"diff 身分矛盾：key={d['key']} 但 driver_id|field={_did}|{_fld} → fail closed")

    diff_by_key = {d["key"]: d for d in diffs if isinstance(d, dict) and d.get("key")}
    unresolved = []
    for d in diffs:
        if not isinstance(d, dict) or not d.get("key"):
            continue   # 結構不正者已於上方記 schema fault
        ok, why = _diff_binding_valid(d)
        if not ok:
            unresolved.append({**d, "_gate_status": "invalid_diff", "_gate_detail": why})
            continue
        cand = verdicts_by_key.get(d["key"], [])
        if len(cand) > 1:
            unresolved.append({**d, "_gate_status": "duplicate_verdict",
                               "_gate_detail": f"{len(cand)} 條裁決指向同一 diff（需恰好一條）"})
            continue
        if cand and _verdict_resolves(cand[0], d)[0]:
            continue
        if not cand:
            status, detail = "no_verdict", "無對應裁決"
        else:
            detail = _verdict_resolves(cand[0], d)[1]
            status = "ours_wrong_hold" if cand[0].get("verdict") == "ours_wrong" else "binding_drift"
        unresolved.append({**d, "_gate_status": status, "_gate_detail": detail})

    stale = sorted(k for k in verdicts_by_key if k not in diff_by_key)
    passed = not unresolved and not stale and not faults
    return passed, unresolved, stale, faults


def _print_gate(passed, unresolved, stale, faults):
    print("\n" + "-" * 70)
    print("裁決硬 gate（config/f1-crosscheck-verdicts.json）")
    if faults:
        print(f"🔴 {len(faults)} 個 report 級問題（fail closed）：")
        for f in faults:
            print(f"    {f}")
    if stale:
        print(f"🔴 {len(stale)} 條裁決指向已不存在的 diff（stale）→ exact-set FAIL：")
        for k in stale:
            print(f"    {k}")
    if unresolved:
        print(f"🔴 {len(unresolved)} 個 diff 未解除 → gate FAIL（gen-racing-drivers --gate-only 應 exit 1）：")
        for d in unresolved:
            print(f"    {d['key']}  [{d.get('_gate_status')}]  我方={d['ours']} 維基={d['wiki']}"
                  f"  ← {d.get('_gate_detail')}")
        print("    → 每條需恰好一條 verdict∈{definition_differs,wiki_wrong}＋reason/by/date"
              "＋wiki_revid 非 null＋bound_fingerprint 吻合當前 report；"
              "ours_wrong 不解除（須修資料到 diff 消失）。")
    if passed:
        print("✅ 所有 diff 都被 fingerprint 吻合的唯一具名裁決解除；無 stale、無 report fault。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="維基百科外部對照 + 裁決 gate（計畫 §4.5）")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--driver", action="append", default=[], help="名單外附加指定車手（可多次）")
    ap.add_argument("--refresh", action="store_true", help="忽略快取重抓")
    ap.add_argument("--report-only", action="store_true", help="只產報告，永遠 exit 0")
    ap.add_argument("--gate-only", action="store_true", help="不抓網路，只對現有報告＋裁決檔跑 gate")
    ap.add_argument("--out", default=str(REPORT), help="報告輸出路徑")
    ap.add_argument("--verdicts", default=str(VERDICTS))
    a = ap.parse_args()

    if a.gate_only:
        # 第五輪 fix1：--gate-only 也必須取得 DB 冠軍集合（gen-racing-drivers 管線裡
        # build-f1-db 先跑，db 必在）。db 缺席＝FAIL closed，不退回 report 自證。
        if not pathlib.Path(a.db).exists():
            print("\n" + "-" * 70)
            print(f"🔴 --gate-only 需要 DB 權威冠軍集合，但 db 不存在：{a.db}\n"
                  f"    → fail closed（請先跑 build-f1-db.py）")
            return 1
        rep = json.loads(pathlib.Path(a.out).read_text(encoding="utf-8"))
        passed, unresolved, stale, faults = gate_diffs(
            rep, load_verdicts(a.verdicts), db_champion_ids=db_champion_ids(a.db))
        _print_gate(passed, unresolved, stale, faults)
        return 0 if passed else 1

    rep = build_report(a.db, extra_drivers=a.driver, refresh=a.refresh)
    pathlib.Path(a.out).write_text(
        json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_summary(rep)
    print(f"\n💾 報告：{a.out}")

    # default 模式：從 DB 現算權威冠軍集合傳入，強制 report manifest 與 DB exact-set 相等（R1）
    passed, unresolved, stale, faults = gate_diffs(
        rep, load_verdicts(a.verdicts), db_champion_ids=db_champion_ids(a.db))
    _print_gate(passed, unresolved, stale, faults)
    if a.report_only:
        return 0
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
