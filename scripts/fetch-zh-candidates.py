#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch-zh-candidates.py — 百科線 M6：zhwiki 半自動譯名候選抓取（全部 pending，一條都不直上）。

對「無 approved 譯名」的實體抓 zhwiki 條目標題當**候選**，供 Charlie 逐批裁決（見 zh-review-pack.md）。
絕不自動 approve、絕不自譯補洞——抓不到就標 not_found，不硬湊。

抓取鏈（每個實體）：
  en.wikipedia 條目標題 → pageprops 取 wikibase_item(Q-id) → wikidata sitelink 取 zhwiki 標題
  → zh.wikipedia parse?variant=zh-tw 取變體轉換後標題。

範圍（四批，皆「champion / 全量」等百科主體且無 approved 譯名）：
  driver     ：35 位冠軍車手中無 approved 者。       en 標題取 driver.url。
  constructor：歷屆車隊冠軍中無 approved 者。         en 標題取 constructor.url。
  circuit    ：全 78 賽道中無 approved 者。            en 標題取 circuit.url。
  race（站名）：全站名中無 approved 者。               en 標題＝raceName 本身（通用 GP 條目，非逐年頁）。

⚠️ zhwiki 常是大陸譯名、variant 轉換對 F1 人名覆蓋不全——候選只是參考，一律寫 status:"pending"。
   variant 轉換只改字形（奥→奧），不改用詞選擇（范吉奧≠台版方吉歐）；故另標 raw 是否含簡體、
   variant 是否真的轉換過，供 review-pack 標警語。

禮貌 / resumable：
  - 全域節流 ≤1 req/s。
  - 候選落 data/f1/zh-candidates.json 快取；重跑跳過已有（--refresh 才重抓）。
  - 任一步失敗 → status:"not_found"，不重試轟炸（單一嘗試 + 少量 transient 退避）。

用法：
  python3 scripts/fetch-zh-candidates.py                # 抓全部四批（跳過快取已有）
  python3 scripts/fetch-zh-candidates.py --only driver  # 只抓某批
  python3 scripts/fetch-zh-candidates.py --limit 5      # 只抓前 N 個未快取（試跑用）
  python3 scripts/fetch-zh-candidates.py --refresh      # 忽略快取，全部重抓
"""
import argparse
import datetime
import json
import pathlib
import ssl
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "f1" / "raw" / "entities"
DB = ROOT / "data" / "f1" / "db.sqlite"
REPORT = ROOT / "data" / "f1" / "crosscheck-report.json"
CACHE = ROOT / "data" / "f1" / "zh-candidates.json"

EN_API = "https://en.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
ZH_API = "https://zh.wikipedia.org/w/api.php"
UA = "racing-tools/1.0 (racing.twtools.cc; non-commercial encyclopedia zh-name candidates)"

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # CI ubuntu 有系統 CA
    SSL_CTX = ssl.create_default_context()

# 簡繁差異抽查字（與 check-zh.py 同源精神；只收繁體正字不會出現的簡化字，判 raw 是否簡體條目）。
SIMPLIFIED_CHARS = set(
    "车马门东过这时样国话说见对觉学会员书写"
    "买卖专业务实现应该队级红纪约纳线组织终"
    "汉铁银钟锋镇钱针赛资费贵产两个称荣龙凤")

_LAST_REQ = [0.0]
_REQ_COUNT = [0]
MIN_INTERVAL = 1.0  # 秒；全域 ≤1 req/s


def _throttle():
    dt = time.time() - _LAST_REQ[0]
    if dt < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - dt)
    _LAST_REQ[0] = time.time()
    _REQ_COUNT[0] += 1


def _get(base, params, retries=2):
    """GET JSON；節流 + 少量 transient 退避。全失敗回 None（呼叫端標 not_found，不硬湊）。"""
    url = base + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries + 1):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25, context=SSL_CTX) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            return None
        except (urllib.error.URLError, TimeoutError, ValueError):
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
    return None


def _title_from_url(url: str) -> str:
    """en.wikipedia URL → 條目標題（unquote、底線轉空白）。"""
    frag = url.rstrip("/").split("/wiki/")[-1]
    return urllib.parse.unquote(frag).replace("_", " ")


def _strip_tags(s: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", s).strip()


def fetch_one(en_title: str):
    """en 標題 → 候選 dict（不含 namespace/id/en，由呼叫端補）。抓不到回 status:not_found。"""
    rec = {"en_title": en_title, "wikidata": None, "zh_title_raw": None,
           "zh_variant_tw": None, "variant_converted": False,
           "raw_had_simplified": False, "status": "not_found", "fail_stage": "net"}
    # 1) en pageprops → Q-id
    d = _get(EN_API, {"action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
                      "titles": en_title, "format": "json", "redirects": 1})
    if not d:
        return rec  # fail_stage=net（transient；rerun 會重試）
    pages = d.get("query", {}).get("pages", {})
    qid = None
    for pg in pages.values():
        qid = pg.get("pageprops", {}).get("wikibase_item")
    if not qid:
        rec["fail_stage"] = "no_wikidata_item"  # deterministic not_found
        return rec
    rec["wikidata"] = qid
    # 2) wikidata sitelink → zhwiki 標題
    d2 = _get(WD_API, {"action": "wbgetentities", "ids": qid, "props": "sitelinks", "format": "json"})
    if not d2:
        return rec
    sl = d2.get("entities", {}).get(qid, {}).get("sitelinks", {})
    zh_raw = sl.get("zhwiki", {}).get("title")
    if not zh_raw:
        rec["fail_stage"] = "no_zhwiki_sitelink"  # deterministic not_found
        return rec
    rec["zh_title_raw"] = zh_raw
    rec["raw_had_simplified"] = any(c in SIMPLIFIED_CHARS for c in zh_raw)
    # 3) zh.wikipedia parse?variant=zh-tw → 變體轉換後標題
    d3 = _get(ZH_API, {"action": "parse", "page": zh_raw, "prop": "displaytitle",
                       "variant": "zh-tw", "format": "json", "redirects": 1})
    zh_tw = zh_raw
    if d3 and "parse" in d3:
        dt = _strip_tags(d3["parse"].get("displaytitle", "")) or zh_raw
        zh_tw = dt
    rec["zh_variant_tw"] = zh_tw
    rec["variant_converted"] = (zh_tw != zh_raw)
    rec["status"] = "pending"  # ★ 一律 pending，絕不自動 approve
    rec.pop("fail_stage", None)  # 成功 → 清掉初始化的 net 標記，避免快取殘留誤導
    return rec


# ---------- 目標清單 ----------

def _approved_ids(fn):
    d = json.loads((ROOT / "scripts" / fn).read_text(encoding="utf-8"))
    out = set()
    for k, v in d.items():
        if k.startswith("_"):
            continue
        if isinstance(v, str) or (isinstance(v, dict) and v.get("status") == "approved"):
            out.add(k)
    return out


def build_targets(conn):
    """回 [(namespace, id, en_text, en_title)]（四批，無 approved 者）。"""
    targets = []
    # driver：35 冠軍 - approved（含 phase0 seed）
    champ = json.loads(REPORT.read_text(encoding="utf-8"))["coverage"]["expected_champion_ids"]
    drv_appr = _approved_ids("driver-zh.json") | {"michael_schumacher", "hamilton", "senna", "max_verstappen"}
    drivers = {r["driver_id"]: r for r in conn.execute("SELECT driver_id, given_name, family_name, url FROM drivers")}
    for did in champ:
        if did in drv_appr:
            continue
        r = drivers.get(did)
        if not r:
            continue
        targets.append(("driver", did, (r["family_name"] or did),
                        _title_from_url(r["url"]) if r["url"] else f"{r['given_name']} {r['family_name']}".strip()))
    # constructor：車隊冠軍 - approved（含 phase0 seed）
    team_appr = _approved_ids("team-zh.json") | {"ferrari", "mclaren", "mercedes", "red_bull"}
    cons = {r["constructor_id"]: r for r in conn.execute("SELECT constructor_id, name, url FROM constructors")}
    champ_cons = [r["constructor_id"] for r in conn.execute(
        "SELECT DISTINCT constructor_id FROM constructor_standings WHERE position=1 ORDER BY constructor_id")]
    for cid in champ_cons:
        if cid in team_appr:
            continue
        r = cons.get(cid)
        en_text = (r["name"] if r else cid)
        en_title = _title_from_url(r["url"]) if (r and r["url"]) else (r["name"] if r else cid)
        targets.append(("constructor", cid, en_text, en_title))
    # circuit：全 78 - approved
    circ_appr = _approved_ids("circuit-zh.json")
    for r in conn.execute("SELECT circuit_id, name, url FROM circuits ORDER BY circuit_id"):
        if r["circuit_id"] in circ_appr:
            continue
        targets.append(("circuit", r["circuit_id"], (r["name"] or r["circuit_id"]),
                        _title_from_url(r["url"]) if r["url"] else (r["name"] or r["circuit_id"])))
    # race（站名）：distinct raceName - approved；en 標題＝raceName 本身（通用條目）
    race_appr = _approved_ids("race-zh.json")
    for r in conn.execute("SELECT DISTINCT name FROM races ORDER BY name"):
        nm = r["name"]
        if not nm or nm in race_appr:
            continue
        targets.append(("race", nm, nm, nm))
    return targets


# ---------- 快取 ----------

def load_cache():
    if not CACHE.exists():
        return {"_meta": {}, "candidates": {}}
    return json.loads(CACHE.read_text(encoding="utf-8"))


def save_cache(doc):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["driver", "constructor", "circuit", "race"])
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 個未快取（試跑）")
    ap.add_argument("--refresh", action="store_true", help="忽略快取全部重抓")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        targets = build_targets(conn)
    finally:
        conn.close()
    if args.only:
        targets = [t for t in targets if t[0] == args.only]

    doc = load_cache()
    cache = doc.setdefault("candidates", {})

    # 「已定案」＝pending 或 deterministic not_found（no_wikidata_item / no_zhwiki_sitelink）；
    # 純網路失敗（fail_stage=net）不算定案 → rerun 自動重試（非重試轟炸：每次跑仍只單輪）。
    def settled(key):
        v = cache.get(key)
        if not v:
            return False
        if v["status"] == "pending":
            return True
        return v.get("fail_stage") in ("no_wikidata_item", "no_zhwiki_sitelink")

    todo = [t for t in targets if args.refresh or not settled(f"{t[0]}:{t[1]}")]
    if args.limit:
        todo = todo[:args.limit]

    print(f"🌐 目標 {len(targets)}、已定案 {sum(1 for t in targets if settled(f'{t[0]}:{t[1]}'))}、"
          f"本次抓 {len(todo)}（含重試 transient；節流 ≤1 req/s）")
    done = 0
    for ns, eid, en_text, en_title in todo:
        rec = fetch_one(en_title)
        rec = {"namespace": ns, "id": eid, "en": en_text, **rec,
               "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
        cache[f"{ns}:{eid}"] = rec
        done += 1
        tag = rec["status"] if rec["status"] == "pending" else f"not_found({rec.get('fail_stage','net')})"
        conv = "·變體轉換" if rec.get("variant_converted") else ""
        simp = "·簡體源" if rec.get("raw_had_simplified") else ""
        print(f"  [{done}/{len(todo)}] {ns}:{eid} → {rec.get('zh_variant_tw') or '—'}  [{tag}{conv}{simp}]")
        if done % 10 == 0:  # 定期落盤，resumable
            save_cache(doc)

    # summary
    by = {}
    for k, v in cache.items():
        ns = v["namespace"]
        b = by.setdefault(ns, {"pending": 0, "not_found": 0, "simp": 0, "total": 0})
        b["total"] += 1
        b["pending" if v["status"] == "pending" else "not_found"] += 1
        if v.get("raw_had_simplified"):
            b["simp"] += 1
    doc["_meta"] = {
        "generated_from": "en.wikipedia + wikidata + zh.wikipedia(variant=zh-tw)",
        "note": "候選一律 status:pending，供 Charlie 裁決；絕不自動 approve。",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "requests_this_run": _REQ_COUNT[0],
        "summary": by,
    }
    save_cache(doc)
    print(f"\n📊 快取統計（累計）：")
    for ns in ("driver", "constructor", "circuit", "race"):
        b = by.get(ns)
        if b:
            print(f"   {ns:12s} pending={b['pending']:3d}  not_found={b['not_found']:3d}  "
                  f"簡體源={b['simp']:3d}  total={b['total']:3d}")
    print(f"   本次 API 請求 {_REQ_COUNT[0]}　→ 快取 {CACHE}")


if __name__ == "__main__":
    main()
