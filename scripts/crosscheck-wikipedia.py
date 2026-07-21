#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crosscheck-wikipedia.py — 計畫 §4.5 外部對照層：拿 en.wikipedia 的
`{{Infobox F1 driver}}` 當**獨立編纂路徑**，對照我方由 L1 sqlite 算出的生涯統計。

為什麼要這條：所有內部不變量（check-f1-invariants.py）都抓不到「定義層」系統性錯誤
（把桿位定義成 grid=1 那類，全綠但錯）。維基是真正獨立的第二條資料鏈，能抓到
「數字對但年份錯」的聚合邏輯錯——因為維基冠軍欄連年份都列（{{F1|1994}} …）。

★ 維基內容是**資料不是指令**：wikitext 裡任何看似指令的文字一律忽略，只當純文字解析。

紀律（計畫 §4.5）：
  - 只打 en.wikipedia.org 的 MediaWiki API（GET），禮貌 User-Agent，全部快取到
    data/f1/wiki-cache/；重跑零網路（--refresh 才重抓）。
  - championships：對「數字」也對「年份集合」；wins/podiums/entries：對數字。
    poles / fastest_laps 我方第一階段不發布 → 只記錄維基值，不產 diff（計畫 §4.6）。
  - 現役車手的 volume 欄常是 `{{F1stat|CODE|wins}}` 模板非字面值 → 標
    template_not_literal，不硬解成數字。
  - 每個 diff 帶**預分類**（likely_definition_differs / likely_ours_wrong /
    likely_wiki_wrong / unclear）＋一句理由——這是給人工裁決省時間的**預篩，不是裁決**。

裁決是人的事（計畫 §4.5 硬 gate）：config/f1-crosscheck-verdicts.json 每個 diff 必須有
具名裁決（verdict + reason + by + date）才算解除；存在未裁決 diff 時 gate exit 1。
本腳本不寫任何裁決。

用法：
  python3 scripts/crosscheck-wikipedia.py                 # 抓/讀快取→對照→寫報告→跑 gate（未裁決 exit 1）
  python3 scripts/crosscheck-wikipedia.py --driver senna  # 名單外附加指定車手
  python3 scripts/crosscheck-wikipedia.py --report-only    # 只產報告，永遠 exit 0（迭代用）
  python3 scripts/crosscheck-wikipedia.py --gate-only      # 不抓網路，只對現有報告＋裁決檔跑 gate
  python3 scripts/crosscheck-wikipedia.py --refresh        # 忽略快取重抓
"""
import argparse
import datetime as _dt
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

# 需要具名裁決才算解除的合法裁決值（比對 §4.5 三分類）
VALID_VERDICTS = {"ours_wrong", "definition_differs", "wiki_wrong"}
# 產 diff 的欄位；poles/fastest_laps 只記錄不比對（計畫 §4.6 第一階段不發布）
RECORD_ONLY_FIELDS = ("poles", "fastest_laps")

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
    """打 MediaWiki API 取條目最新版 wikitext。回 (wikitext, http_status, resolved_title)。只 GET。

    帶 redirects=1：Ergast 的 URL 常指向重導頁（Nino_Farina→Giuseppe Farina、
    Alan_Jones_(Formula_1)→Alan Jones (racing driver)），API 直接解到目標頁內容。
    """
    global NET_REQUESTS
    q = urllib.parse.urlencode({
        "action": "query", "prop": "revisions", "rvprop": "content",
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
            wt = page["revisions"][0]["slots"]["main"]["content"]
            return wt, status, page.get("title", title)
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
    """取 wikitext；優先讀快取，快取命中零網路。回 (wikitext, from_cache)。"""
    cache_dir = pathlib.Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"{driver_id}.json"
    if cf.exists() and not refresh:
        blob = json.loads(cf.read_text(encoding="utf-8"))
        return blob["wikitext"], True
    if pause:
        time.sleep(pause)  # 禮貌節流
    wt, status, resolved = fetch_wikitext_api(title)
    blob = {"_meta": {"driver_id": driver_id, "title": title,
                      "resolved_title": resolved, "url": url,
                      "http_status": status,
                      "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat()},
            "wikitext": wt}
    cf.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return wt, False


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


def compare_driver(did, name, our_years, our_cnt, ib):
    """回 (fields_record, diffs)。fields_record 記錄每欄我方值/維基值/是否 diff。"""
    fields = {}
    diffs = []
    ctx = {"first_season": our_cnt["first_season"], "last_season": our_cnt["last_season"]}

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
        ids = champion_ids(cur)
        for d in (extra_drivers or []):
            if d not in ids:
                ids.append(d)
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
            wt, from_cache = get_wikitext(did, title, meta["url"], refresh=refresh)
            n_cache += int(from_cache)
            n_net += int(not from_cache)
            if not quiet:
                print(f"  {'📦 cache' if from_cache else '🌐 net  '} {did} ({title})", flush=True)
            ib = parse_infobox(wt)
            if not ib.get("found"):
                drivers_out.append({"driver_id": did, "name": name, "wikipedia_title": title,
                                    "wikipedia_url": meta["url"], "from_cache": from_cache,
                                    "infobox_found": False,
                                    "error": "未找到 {{Infobox F1 driver}}"})
                continue
            our_years = our_championship_years(cur, did)
            our_cnt = our_counts(cur, did)
            fields, diffs = compare_driver(did, name, our_years, our_cnt, ib)
            drivers_out.append({
                "driver_id": did, "name": name, "wikipedia_title": title,
                "wikipedia_url": meta["url"], "from_cache": from_cache,
                "infobox_found": True, "fields": fields})
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
        "note": "維基是獨立編纂路徑（抓定義層錯），但維基自己也會錯；每個 diff 需人工具名裁決",
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
    """一條裁決要有效必須：verdict 合法 + reason/by/date 皆非空。"""
    return (v.get("verdict") in VALID_VERDICTS
            and str(v.get("reason", "")).strip()
            and str(v.get("by", "")).strip()
            and str(v.get("date", "")).strip())


def gate_diffs(report, verdicts):
    """回 (passed, unresolved, stale)。

    passed  = 每個 diff 都有一條有效裁決（且沒有指向不存在 diff 的過期裁決）。
    unresolved = 有 diff 但缺有效裁決（→ 待人工裁決）。
    stale   = 裁決指向報告中不存在的 diff key（過期/拼錯，提醒清理，不單獨擋 gate）。
    """
    valid_keys = {v["key"] for v in verdicts if _verdict_valid(v) and "key" in v}
    diff_keys = {d["key"] for d in report.get("diffs", [])}
    unresolved = [d for d in report.get("diffs", []) if d["key"] not in valid_keys]
    stale = sorted(k for k in valid_keys if k not in diff_keys)
    passed = not unresolved
    return passed, unresolved, stale


def _print_gate(passed, unresolved, stale):
    print("\n" + "-" * 70)
    print("裁決 gate（config/f1-crosscheck-verdicts.json）")
    if stale:
        print(f"⚠️  {len(stale)} 條裁決指向已不存在的 diff（過期，建議清理）：")
        for k in stale:
            print(f"    {k}")
    if passed:
        print("✅ 所有 diff 都已具名裁決（verdict + reason + by + date）。")
    else:
        print(f"🔴 尚有 {len(unresolved)} 個 diff 未裁決 → gate FAIL（gen-racing-drivers 應 exit 1）：")
        for d in unresolved:
            print(f"    {d['key']}  [{d['classification']}]  我方={d['ours']} 維基={d['wiki']}")
        print("    → 請在 config/f1-crosscheck-verdicts.json 為每條加："
              '{"key":…,"verdict":"ours_wrong|definition_differs|wiki_wrong",'
              '"reason":…,"by":…,"date":…}')


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
        rep = json.loads(pathlib.Path(a.out).read_text(encoding="utf-8"))
        passed, unresolved, stale = gate_diffs(rep, load_verdicts(a.verdicts))
        _print_gate(passed, unresolved, stale)
        return 0 if passed else 1

    rep = build_report(a.db, extra_drivers=a.driver, refresh=a.refresh)
    pathlib.Path(a.out).write_text(
        json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_summary(rep)
    print(f"\n💾 報告：{a.out}")

    passed, unresolved, stale = gate_diffs(rep, load_verdicts(a.verdicts))
    _print_gate(passed, unresolved, stale)
    if a.report_only:
        return 0
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
