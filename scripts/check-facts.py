#!/usr/bin/env python3
"""check-facts.py — 賽事內容線的第 ③ 步：稿子發布前的機械對帳。

**設計原則：高價值那幾支一律重新打 API，不拿 facts pack 驗自己。**
用產稿的同一份資料去驗稿，錯誤只會被蓋章通過——facts pack 抓錯輪次、快照過期、
欄位取錯層，這些正是最需要被抓到的問題，而它們在「自我比對」裡永遠是綠的。
所以：
  verify-recap    → 重打 jolpica API，逐列比對文章表格（**擋 gate**）
  numbers-in-facts → 比對本地 facts pack，找孤兒數字（**只提示，永不擋**）
  no-causal       → 掃戰報裡的因果句（**只提示**，regex 判斷不夠硬，交人判）

用法：
    python3 scripts/check-facts.py verify-recap --round 11 --article articles/<slug>/index.md
    python3 scripts/check-facts.py numbers-in-facts --facts facts/race-recap-2026-r11.json --article ...
    python3 scripts/check-facts.py no-causal --article ...
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import racinglib as rc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_article(path):
    p = pathlib.Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        print(f"❌ 找不到文章：{path}", file=sys.stderr)
        sys.exit(2)
    return p.read_text(encoding="utf-8")


def _table_rows(text):
    """抽出 markdown 表格的資料列（去掉表頭與分隔線），回 [[cell, ...]]。"""
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        rows.append(cells)
    return rows


# ---------- ① 重打 API 的硬 gate ----------

def verify_recap(season, rnd, article_path):
    """重新向 jolpica 要一次該站賽果，逐一比對文章表格裡的名次／車手／積分。"""
    import fetch_racing  # 延後 import：只有這支需要網路

    src = fetch_racing.JolpicaSource()
    print(f"🌐 重新抓取 {season} 第 {rnd} 站賽果（不使用本地快照）…")
    live = src.race_results(season, rnd)
    entries = (live or {}).get("Results") or []
    if len(entries) < 10:
        print(f"❌ API 回傳 {len(entries)} 筆結果，資料不足以驗證", file=sys.stderr)
        return False

    # 建索引：以車手姓氏原文與中譯兩種寫法都可命中（站規是中英對照）
    by_pos = {}
    for e in entries:
        d = e.get("Driver") or {}
        try:
            pos = int(e.get("position") or 0)
        except (TypeError, ValueError):
            continue
        by_pos[pos] = {
            "zh": rc.driver_zh(d),
            "family": d.get("familyName", ""),
            "code": d.get("code", ""),
            "points": float(e.get("points") or 0),
            "team_zh": rc.team_zh((e.get("Constructor") or {}).get("name", "")),
            "team_en": (e.get("Constructor") or {}).get("name", ""),
            "grid": str(e.get("grid") or ""),
        }

    text = _load_article(article_path)
    checked = 0
    problems = []
    for cells in _table_rows(text):
        if not cells:
            continue
        m = re.fullmatch(r"\**(\d{1,2})\**", cells[0])
        if not m:
            continue
        pos = int(m.group(1))
        truth = by_pos.get(pos)
        if not truth:
            problems.append(f"名次 {pos}：API 無此名次")
            continue
        row_text = " ".join(cells)
        checked += 1

        # 車手：中譯或原文姓氏任一命中即可
        if truth["zh"] not in row_text and truth["family"] not in row_text:
            problems.append(
                f"名次 {pos}：文章寫「{cells[1] if len(cells) > 1 else '?'}」，"
                f"API 為 {truth['zh']}／{truth['family']}")

        # 車隊：只在該列有出現車隊欄位時才驗（有些表格不列車隊）
        if truth["team_en"] and truth["team_zh"] not in row_text and truth["team_en"] not in row_text:
            # 該列若完全沒有車隊資訊就跳過，不當成錯
            if any(t["team_zh"] in row_text or t["team_en"] in row_text for t in by_pos.values()):
                problems.append(f"名次 {pos}：車隊與 API 不符（API 為 {truth['team_zh']}／{truth['team_en']}）")

        # 積分：文章若列了積分欄，數字必須完全相同
        nums = {n for n in re.findall(r"\d+(?:\.\d+)?", row_text)}
        pts = truth["points"]
        pts_s = str(int(pts)) if float(pts).is_integer() else str(pts)
        if pts > 0 and re.search(r"積分|分\b|points", text, re.I) and pts_s not in nums:
            problems.append(f"名次 {pos}：積分 {pts_s} 在該列找不到（API 值）")

    if checked == 0:
        print("❌ 文章裡找不到任何可比對的名次表格列——對帳未實際執行，不算通過",
              file=sys.stderr)
        return False

    print(f"   比對了 {checked} 列")
    if problems:
        print(f"❌ {len(problems)} 處與 API 不符：", file=sys.stderr)
        for p in problems:
            print(f"   · {p}", file=sys.stderr)
        return False
    print("✅ 表格逐列與 API 一致")
    return True


# ---------- ② 提示性檢查（永不擋 gate） ----------

def _flatten_nums(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            _flatten_nums(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flatten_nums(v, out)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, (int, float)):
        out.add(str(int(obj)) if float(obj).is_integer() else str(obj))
    elif isinstance(obj, str):
        for n in re.findall(r"\d+(?:\.\d+)?", obj):
            out.add(n)


def numbers_in_facts(facts_path, article_path):
    p = pathlib.Path(facts_path)
    if not p.is_absolute():
        p = ROOT / p
    pack = json.loads(p.read_text(encoding="utf-8"))
    known = set()
    _flatten_nums(pack, known)

    text = _load_article(article_path)
    body = re.sub(r"^---.*?^---", "", text, flags=re.S | re.M)  # 去 frontmatter
    orphans = []
    for cells in _table_rows(body):
        for n in re.findall(r"\d+(?:\.\d+)?", " ".join(cells)):
            if n not in known and len(n) > 1:  # 個位數雜訊太多，略過
                orphans.append(n)
    if orphans:
        print(f"⚠️ 表格中有 {len(set(orphans))} 個數字不在 facts pack 裡："
              f"{sorted(set(orphans))[:20]}")
        print("   （提示性檢查，不擋發布——但每一個都要人工確認來源）")
    else:
        print("✅ 表格數字全部能在 facts pack 中找到")
    return True  # 刻意永遠回 True：這支是提示，不是 gate


CAUSAL_PATTERNS = [
    r"因為[^，。]{2,20}(?:所以|才|導致)", r"由於[^，。]{2,20}(?:才|導致|使得)",
    r"導致", r"策略失誤", r"車隊決定", r"車隊選擇了", r"錯估", r"失算",
    r"如果[^，。]{2,20}就(?:能|會|可以)",
]


def no_causal(article_path):
    """戰報禁因果。regex 抓不準，所以只列出來交人判斷，不擋 gate。"""
    text = _load_article(article_path)
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for pat in CAUSAL_PATTERNS:
            for m in re.finditer(pat, line):
                hits.append(f"L{i}: …{line[max(0, m.start()-12):m.end()+12]}…")
    if hits:
        print(f"⚠️ {len(hits)} 處疑似因果／臆測句（戰報文型應只寫「發生了什麼」）：")
        for h in hits[:20]:
            print(f"   · {h}")
        print("   （提示性檢查，交人判斷；屬於賽後分析的內容請移到分析文）")
    else:
        print("✅ 未偵測到因果／臆測句式")
    return True


def main():
    ap = argparse.ArgumentParser(description="發布前機械對帳")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("verify-recap", help="重打 API 逐列驗證戰報表格（擋 gate）")
    p1.add_argument("--round", type=int, required=True)
    p1.add_argument("--season", type=int, default=rc.SEASON)
    p1.add_argument("--article", required=True)

    p2 = sub.add_parser("numbers-in-facts", help="找不在 facts pack 裡的孤兒數字（提示）")
    p2.add_argument("--facts", required=True)
    p2.add_argument("--article", required=True)

    p3 = sub.add_parser("no-causal", help="掃戰報裡的因果句（提示）")
    p3.add_argument("--article", required=True)

    args = ap.parse_args()
    if args.cmd == "verify-recap":
        ok = verify_recap(args.season, args.round, args.article)
    elif args.cmd == "numbers-in-facts":
        ok = numbers_in_facts(args.facts, args.article)
    else:
        ok = no_causal(args.article)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
