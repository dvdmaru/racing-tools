#!/usr/bin/env python3
"""check-facts.py — 賽事內容線的第 ③ 步：稿子發布前的機械對帳。

**設計原則一：高價值檢查重新打 API，不拿 facts pack 驗自己。**
用產稿的同一份資料去驗稿，錯誤只會被蓋章通過——facts pack 抓錯輪次、快照過期、
欄位取錯層，這些正是最需要被抓到的問題，而它們在「自我比對」裡永遠是綠的。

**設計原則二：檢查的通過條件必須涵蓋 prompt contract，不能只涵蓋容易驗的部分。**
（2026-07-20 Sol 查核桌 S2/S3：初版的硬 gate 只要求「比對到 ≥1 列」，於是一篇
只有一列前十表、發車位寫 999、正文寫「第 9999 圈」的稿子拿到了綠燈。
「驗了一部分」的成功訊息比沒有檢查更危險，因為它讓人以為驗過了。）

三支檢查，**全部擋 gate**；要放行個別項目必須寫進 config/facts-waivers.json 並附理由：
  verify-recap  重打 jolpica API，前十表逐格比對（名次集合／車手／車隊／發車位／積分）
  verify-body   全文數字必須對得到 facts pack
  no-causal     戰報禁因果；命中即擋，除非該句已列入豁免

用法：
    python3 scripts/check-facts.py verify-all --round 11 --facts facts/... --article articles/<slug>/index.md
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import racinglib as rc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
WAIVER_PATH = ROOT / "config" / "facts-waivers.json"

# 表格欄位辨識：靠表頭關鍵字，不靠欄位順序（順序會改，語意不會）
COL_KEYS = {
    "position": ("名次", "排名", "pos"),
    "driver": ("車手", "driver"),
    "team": ("車隊", "constructor", "team"),
    "grid": ("發車", "起跑", "grid"),
    "points": ("積分", "得分", "points"),
}


def _resolve(path):
    p = pathlib.Path(path)
    return p if p.is_absolute() else ROOT / p


def _load_article(path):
    p = _resolve(path)
    if not p.exists():
        print(f"❌ 找不到文章：{path}", file=sys.stderr)
        sys.exit(2)
    return p.read_text(encoding="utf-8")


def _slug_of(text, fallback=""):
    m = re.search(r"^slug:\s*\"?([A-Za-z0-9_-]+)\"?\s*$", text, re.M)
    return m.group(1) if m else fallback


def _body_of(text):
    return re.sub(r"\A---.*?\n---\s*\n", "", text, flags=re.S)


def _load_waivers(slug):
    if not WAIVER_PATH.exists():
        return {"numbers": [], "causal": []}
    data = json.loads(WAIVER_PATH.read_text(encoding="utf-8"))
    entry = data.get(slug) or {}
    return {"numbers": [str(x) for x in (entry.get("numbers") or [])],
            "causal": list(entry.get("causal") or [])}


def _tables(text):
    """回 [[cells,...], ...] 的表格清單（每個表格是一組連續的 | 行，去分隔線）。"""
    tables, cur = [], []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                cur.append(cells)
        else:
            if cur:
                tables.append(cur)
                cur = []
    if cur:
        tables.append(cur)
    return tables


def _table_rows(text):
    """所有表格的資料列攤平（保留給提示性檢查用）。"""
    return [r for t in _tables(text) for r in t]


def _find_result_table(text):
    """找出前十完賽表：表頭同時含「名次」與「車手」語意的那張。回 (colmap, rows)。"""
    for tbl in _tables(text):
        if not tbl:
            continue
        header = [c.lower() for c in tbl[0]]
        colmap = {}
        for field, keys in COL_KEYS.items():
            for i, h in enumerate(header):
                if any(k in h for k in keys):
                    colmap[field] = i
                    break
        if "position" in colmap and "driver" in colmap:
            return colmap, tbl[1:]
    return None, []


def _cell(row, colmap, field):
    i = colmap.get(field)
    if i is None or i >= len(row):
        return None
    return re.sub(r"\*+", "", row[i]).strip()


# ---------- ① 重打 API 的硬 gate（S2 修正版） ----------

def verify_recap(season, rnd, article_path, expect=10):
    """重新向 jolpica 要一次該站賽果，對前十表**逐格**比對。

    與初版的差別（Sol S2）：
      · 名次集合必須恰好是 1..expect，各出現一次——缺列、重列、只寫一列都擋
      · 車手、車隊、發車位、積分逐格比對，不是「整列文字裡有沒有出現」
      · 表格找不到、欄位缺失一律 fail closed
    """
    import fetch_racing  # 延後 import：只有這支需要網路

    src = fetch_racing.JolpicaSource()
    print(f"🌐 重新抓取 {season} 第 {rnd} 站賽果（不使用本地快照）…")
    live = src.race_results(season, rnd)
    entries = (live or {}).get("Results") or []
    if len(entries) < expect:
        print(f"❌ API 回傳 {len(entries)} 筆結果，不足 {expect} 筆，無法驗證", file=sys.stderr)
        return False

    truth = {}
    for e in entries:
        d = e.get("Driver") or {}
        try:
            pos = int(e.get("position") or 0)
        except (TypeError, ValueError):
            continue
        pts = float(e.get("points") or 0)
        truth[pos] = {
            "zh": rc.driver_zh(d), "family": d.get("familyName", ""),
            "code": d.get("code", ""),
            "team_zh": rc.team_zh((e.get("Constructor") or {}).get("name", "")),
            "team_en": (e.get("Constructor") or {}).get("name", ""),
            "grid": str(e.get("grid") or ""),
            "points": str(int(pts)) if pts.is_integer() else str(pts),
        }

    text = _load_article(article_path)
    colmap, rows = _find_result_table(_body_of(text))
    if colmap is None:
        print("❌ 找不到前十完賽表（需要表頭同時含「名次」與「車手」）——"
              "對帳未實際執行，不算通過", file=sys.stderr)
        return False

    problems = []
    seen = []
    for row in rows:
        raw = _cell(row, colmap, "position")
        if raw is None or not raw.isdigit():
            continue
        seen.append(int(raw))

    want = list(range(1, expect + 1))
    if sorted(seen) != want:
        missing = [p for p in want if p not in seen]
        dup = sorted({p for p in seen if seen.count(p) > 1})
        extra = sorted({p for p in seen if p not in want})
        print(f"❌ 前十表名次集合不正確：缺 {missing}／重複 {dup}／多出 {extra}",
              file=sys.stderr)
        return False

    for row in rows:
        raw = _cell(row, colmap, "position")
        if raw is None or not raw.isdigit():
            continue
        pos = int(raw)
        t = truth.get(pos)
        if not t:
            problems.append(f"名次 {pos}：API 無此名次")
            continue

        drv = _cell(row, colmap, "driver") or ""
        if t["zh"] not in drv and t["family"] not in drv:
            problems.append(f"名次 {pos} 車手：文章「{drv}」≠ API {t['zh']}／{t['family']}")

        if "team" in colmap:
            tm = _cell(row, colmap, "team") or ""
            if t["team_zh"] not in tm and t["team_en"] not in tm:
                problems.append(f"名次 {pos} 車隊：文章「{tm}」≠ API {t['team_zh']}／{t['team_en']}")

        if "grid" in colmap:
            g = _cell(row, colmap, "grid") or ""
            gnum = re.sub(r"[^\d]", "", g)
            if gnum != t["grid"]:
                problems.append(f"名次 {pos} 發車位：文章「{g}」≠ API {t['grid']}")

        if "points" in colmap:
            p = _cell(row, colmap, "points") or ""
            pnum = re.sub(r"[^\d.]", "", p)
            if pnum.rstrip(".") != t["points"]:
                problems.append(f"名次 {pos} 積分：文章「{p}」≠ API {t['points']}")

    print(f"   前十表 {len(seen)} 列、{len(colmap)} 個欄位逐格比對")
    if problems:
        print(f"❌ {len(problems)} 處與 API 不符：", file=sys.stderr)
        for pr in problems:
            print(f"   · {pr}", file=sys.stderr)
        return False
    print("✅ 前十表與 API 逐格一致")
    return True


# ---------- ② 全文數字必須有來源（S3 修正版） ----------

def _flatten_nums(obj, out):
    if isinstance(obj, bool):
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _flatten_nums(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flatten_nums(v, out)
    elif isinstance(obj, (int, float)):
        out.add(str(int(obj)) if float(obj).is_integer() else str(obj))
    elif isinstance(obj, str):
        for n in re.findall(r"\d+(?:\.\d+)?", obj):
            out.add(n)


def verify_body(facts_path, article_path):
    """全文（不只表格）每個數字都要能在 facts pack 找到，否則擋。

    初版只掃表格且永遠回 True——所以正文寫「第 9999 圈」完全不會被發現（Sol S3）。
    正文才是寫手最容易憑印象補數字的地方，把它排除在檢查外等於防線開了個正門。
    """
    pack = json.loads(_resolve(facts_path).read_text(encoding="utf-8"))
    known = set()
    _flatten_nums(pack, known)

    text = _load_article(article_path)
    slug = _slug_of(text)
    waived = set(_load_waivers(slug)["numbers"])
    body = _body_of(text)
    body = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body)  # 連結網址不算內容數字

    orphans = {}
    for m in re.finditer(r"\d+(?:\.\d+)?", body):
        n = m.group(0)
        if len(n) < 2 or n in known or n in waived:
            continue
        ctx = body[max(0, m.start() - 14):m.end() + 14].replace("\n", " ")
        orphans.setdefault(n, ctx)

    if orphans:
        print(f"❌ {len(orphans)} 個數字在 facts pack 中找不到來源：", file=sys.stderr)
        for n, ctx in list(orphans.items())[:20]:
            print(f"   · {n}  …{ctx}…", file=sys.stderr)
        print(f"   確認無誤者請寫進 {WAIVER_PATH.relative_to(ROOT)} 的 "
              f"\"{slug}\".numbers 並附理由。", file=sys.stderr)
        return False
    print("✅ 全文數字均可對到 facts pack")
    return True


# ---------- ③ 戰報禁因果（S3 修正版：命中即擋，要放行須豁免） ----------

CAUSAL_PATTERNS = [
    r"因為[^，。]{2,20}(?:所以|才|導致)", r"由於[^，。]{2,20}(?:才|導致|使得)",
    r"導致", r"策略失誤", r"車隊決定", r"車隊選擇了", r"錯估", r"失算",
    r"如果[^，。]{2,20}就(?:能|會|可以)",
    r"軟胎", r"硬胎", r"中性胎", r"輪胎策略", r"安全車",  # 資料源根本沒有這些
]


def no_causal(article_path):
    """戰報只寫「發生了什麼」。命中即擋——但擋的是「尚未裁決的命中」，不是句子本身。

    regex 確實會誤殺，所以出路不是降級成提示（初版做法，等於永不擋），
    而是要求每個命中都被處理掉：刪除、改寫、或寫進豁免清單附理由。
    """
    text = _load_article(article_path)
    slug = _slug_of(text)
    waived = _load_waivers(slug)["causal"]
    hits = []
    for i, line in enumerate(_body_of(text).splitlines(), 1):
        for pat in CAUSAL_PATTERNS:
            for m in re.finditer(pat, line):
                frag = line[max(0, m.start() - 12):m.end() + 12]
                if any(w in line for w in waived):
                    continue
                hits.append(f"L{i}: …{frag}…")
    if hits:
        print(f"❌ {len(hits)} 處未裁決的因果／無源主張：", file=sys.stderr)
        for h in hits[:20]:
            print(f"   · {h}", file=sys.stderr)
        print("   戰報只寫「發生了什麼」。請刪除、改寫，或寫進 "
              f"{WAIVER_PATH.relative_to(ROOT)} 的 \"{slug}\".causal 並附理由。",
              file=sys.stderr)
        return False
    print("✅ 無未裁決的因果／無源主張")
    return True


def _sha(path):
    return hashlib.sha256(_resolve(path).read_bytes()).hexdigest()


def verify_all(season, rnd, facts_path, article_path):
    results = [
        ("verify-recap", verify_recap(season, rnd, article_path)),
        ("verify-body", verify_body(facts_path, article_path)),
        ("no-causal", no_causal(article_path)),
    ]
    failed = [n for n, ok in results if not ok]
    print()
    print(f"article sha256 = {_sha(article_path)}")
    print(f"facts   sha256 = {_sha(facts_path)}")
    if failed:
        print(f"⛔ {len(failed)} 項未通過（{'、'.join(failed)}）→ 不得進入核准流程",
              file=sys.stderr)
        return False
    print("✅ 三項全過。可提請人工 cross-check（機械對帳通過 ≠ 內容正確）")
    return True


def main():
    ap = argparse.ArgumentParser(description="發布前機械對帳（三項全部擋 gate）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name, need in (("verify-recap", "rf"), ("verify-body", "fa"),
                       ("no-causal", "a"), ("verify-all", "rfa")):
        p = sub.add_parser(name)
        if "r" in need:
            p.add_argument("--round", type=int, required=True)
            p.add_argument("--season", type=int, default=rc.SEASON)
        if "f" in need:
            p.add_argument("--facts", required=True)
        p.add_argument("--article", required=True)

    args = ap.parse_args()
    if args.cmd == "verify-recap":
        ok = verify_recap(args.season, args.round, args.article)
    elif args.cmd == "verify-body":
        ok = verify_body(args.facts, args.article)
    elif args.cmd == "no-causal":
        ok = no_causal(args.article)
    else:
        ok = verify_all(args.season, args.round, args.facts, args.article)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
