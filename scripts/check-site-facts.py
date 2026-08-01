#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-site-facts.py — 跨頁事實一致性 gate：同一個事實在全站只能有一個值。

## 為什麼需要這一支（2026-08-01 事故）

巴林站移師雪邦，2026 賽季從 22 站變 23 站。同一個事實當時散在四個地方，
每一處的失效方式都不一樣：

1. `gen-racing-calendar.py` 的 FAQ——**站數動態算、敘述寫死**，
   下一次週更會產出「23 站。賽季原公布 24 站…縮為 23 站」，當著讀者的面算錯數。
2. `build-articles.py` 寫的 `llms.txt`——寫死「全季 22 站」，永遠不會自己更新。
3. 已核准的 `f1-2026-rules-guide`——7 處「22 站」，sha256 凍結，沒有東西在監控它過期。
4. 同一篇文章的「賽季剩下的 13 站」——**由舊總數推算**（22 減已跑 9 站）。
   用關鍵字 grep「22 站」**掃不到它**。第 4 點才是這支腳本存在的真正理由。

## ⚠️ 這支腳本自己踩過的坑（v1 → v2）

v1 走 default-deny：抓出所有「數字＋量詞」，分類不出來就算命中。
**實測 446 個命中**，其中絕大多數是「跑了 9 站之後」「已完賽 11 站」
「由 8 站增為 12 站」這類完全正確的敘述。滿是假陽性的 gate 比沒有 gate 更糟——
沒人讀，最後一定被關掉。

v2 改成**登記制**：只有命中 `assert_patterns` 的數字才算「在宣稱這個事實」。
代價是新說法要補 pattern；補償是 `--audit` 會把所有沒被歸類的「N 站」列出來
供人週期性檢視——那是**報告不是 gate**，不影響 exit code。

## 兩種嚴重度，理由不同

- **產物與生成器輸出**（`public-racing/`）＝我們控制得了 → 不一致就 exit 1。
- **已核准文章**（`approved.json` 綁 sha256）＝改動會讓核准失效 →
  預設也 exit 1（本機／PR 擋住，不讓它被靜默引入），但 `--deploy` 降為警告。
  理由：週更排程清晨自動跑，這時擋下部署**不會讓錯的內容變對**（線上仍是舊那份），
  只會連帶讓賽果與積分榜停止更新。把錯誤攤在部署日誌上、讓人去重新核准，
  比癱瘓整條管線合理。

用法：
    python3 scripts/check-site-facts.py            # 本機／PR：全部視為錯誤
    python3 scripts/check-site-facts.py --deploy   # 部署：已核准文章降為警告
    python3 scripts/check-site-facts.py --audit    # 額外列出未歸類的數字（不影響 exit）
"""
import argparse
import glob
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "site-facts.json"
APPROVED = ROOT / "config" / "approved.json"

AUDIT_RE = re.compile(r"(?<![0-9])([0-9][0-9,]*)\s*站")
CTX = 36


def compute_truths(season: int, completed: int = None) -> dict:
    """事實的唯一計算來源。新增事實時**只能在這裡**加，不准在別處另算一份。"""
    p = ROOT / "data" / str(season) / "schedule.json"
    if not p.exists():
        print(f"⛔ 找不到 {p}，無法計算真值", file=sys.stderr)
        sys.exit(1)
    races = json.loads(p.read_text(encoding="utf-8"))["races"]
    res = ROOT / "data" / str(season) / "results"
    # ⚠️ 只數「round-NN.json」＝正賽賽果。這裡原本寫 glob("round-*.json")，
    # 會把 round-02-sprint / round-10-laps / round-10-pitstops 一起數進去：
    # 19 個檔被當成 19 站跑完，剩餘站數算成 4（實際 12）。
    # **這支腳本存在的理由就是抓推算值出錯，結果它自己的推算值先錯了**——
    # 推算值一律要驗，不能因為「看起來很合理」就放行。
    done = completed if completed is not None else (
        len([f for f in res.glob("round-[0-9][0-9].json")]) if res.exists() else 0)
    return {
        "season_races": len(races),
        "season_sprints": sum(1 for r in races if "Sprint" in r),
        "season_races_remaining": len(races) - done,
    }


def strip_html(text: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    return re.sub(r"<[^>]+>", " ", text)


def check_text(text: str, cfg: dict, truths: dict):
    """回 [(fact_id, claimed, truth, snippet)]，只含不一致的。"""
    bad = []
    allows = cfg.get("allow", [])
    for f in cfg["facts"]:
        truth = truths[f["id"]]
        for pat in f["assert_patterns"]:
            for m in re.finditer(pat, text):
                claimed = int(m.group(1).replace(",", ""))
                if claimed == truth:
                    continue
                s = max(0, m.start() - CTX)
                snippet = re.sub(r"\s+", " ", text[s:m.end() + CTX]).strip()
                # allow＝具名例外（比照 known_exceptions.json）：每一條都要寫理由。
                # 典型用途是「引述他人當時的說法」，那不是在宣稱現況。
                # ⚠️ 比對要用**比 snippet 更寬的視窗**：snippet 只留 CTX 字元，
                # 句首常被切掉，拿它比對會讓 allow 靜默失效（實測踩過）。
                wide = text[max(0, m.start() - 160):m.end() + 160]
                if any(re.search(a["pattern"], wide) for a in allows):
                    continue
                bad.append((f["id"], f["label"], claimed, truth, snippet))
    return bad


def audit_text(text: str, cfg: dict):
    """列出**沒有被任何 assert_pattern 認領**的「N 站」。報告用，不是 gate。"""
    claimed_spans = []
    for f in cfg["facts"]:
        for pat in f["assert_patterns"]:
            claimed_spans += [m.span() for m in re.finditer(pat, text)]
    out = []
    for m in AUDIT_RE.finditer(text):
        if any(a <= m.start() and m.end() <= b for a, b in claimed_spans):
            continue
        if re.search(r"第\s*$", text[max(0, m.start() - 3):m.start()]):
            continue  # 序數＝賽曆位置，不是總數
        s = max(0, m.start() - CTX)
        out.append(re.sub(r"\s+", " ", text[s:m.end() + CTX]).strip())
    return out


def approved_slugs() -> set:
    if not APPROVED.exists():
        return set()
    return {e["slug"] for e in json.loads(APPROVED.read_text(encoding="utf-8")).get("approved", [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int)
    ap.add_argument("--deploy", action="store_true", help="已核准文章降為警告")
    ap.add_argument("--audit", action="store_true", help="額外列出未歸類的數字")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    season = args.season or json.loads(
        (ROOT / "config" / "site.json").read_text(encoding="utf-8"))["season"]
    truths = compute_truths(season)

    print(f"🔎 跨頁事實一致性（season={season}）")
    for k, v in truths.items():
        print(f"   真值 {k} = {v}")

    approved = approved_slugs()
    errors, warnings, unclassified = [], [], []

    targets = []
    for pat in cfg["scan"]["sources"] + cfg["scan"]["products"]:
        targets += [pathlib.Path(p) for p in glob.glob(str(ROOT / pat), recursive=True)]
    # 排除「由資料庫逐頁算出」的頁：它們不會手寫漂移，而且講的常是別的賽季
    # （百科 /seasons/2023/ 寫「2023 賽季共 22 站」是對的）。範圍寫寬＝假陽性淹掉真訊號。
    excluded = set()
    for ex in cfg["scan"].get("exclude", []):
        excluded |= {pathlib.Path(p) for p in glob.glob(str(ROOT / ex["pattern"]), recursive=True)}
    targets = [t for t in targets if t not in excluded]

    for path in sorted(set(targets)):
        raw = path.read_text(encoding="utf-8", errors="replace")
        # 引用區：本頁勘誤這類「職責就是引用原本錯的寫法」的區塊，整段移除再檢查。
        # ⚠️ 不要改用 allow 逐條豁免——每次勘誤都要新增一條，例外清單會變成掩蓋器。
        for qz in cfg.get("quote_zones", []):
            raw = re.sub(qz["pattern"], " ", raw, flags=re.S)
        text = strip_html(raw) if path.suffix in (".html", ".htm") else raw
        rel = path.relative_to(ROOT).as_posix()
        frozen = rel.startswith("articles/") and path.parent.name in approved
        for fid, label, claimed, truth, snippet in check_text(text, cfg, truths):
            row = (rel, f"{label}應為 {truth}，這裡寫 {claimed}", snippet, frozen)
            (warnings if (frozen and args.deploy) else errors).append(row)
        if args.audit and rel.startswith("articles/"):
            for snippet in audit_text(text, cfg):
                unclassified.append((rel, snippet))

    def show(rows, mark):
        for rel, why, snippet, frozen in rows:
            tag = "（已核准文章，改動需重新核准）" if frozen else ""
            print(f"{mark} {rel}{tag}\n     {why}\n     …{snippet}…")

    print()
    if warnings:
        print(f"⚠️  已核准文章有 {len(warnings)} 處過期（部署不擋，但必須處理）：")
        show(warnings, "  ⚠️")
        print("   → 修文章後要重新核准 sha256，否則 build 會把文章擋回去。\n")
    if errors:
        print(f"⛔ {len(errors)} 處事實不一致：")
        show(errors, "  ❌")
        print("\n   同一個事實在全站只能有一個值。修法優先序："
              "①讓文字由資料算出來 ②算不出來就別寫死那個數字 "
              "③推算值（剩餘站數這類）優先改寫成不帶數字的說法，而不是把數字改對。")

    if args.audit:
        print(f"\n📋 未歸類的「N 站」共 {len(unclassified)} 處（報告，不影響 exit）：")
        for rel, snippet in unclassified:
            print(f"   · {rel}\n     …{snippet}…")
        print("   → 逐條看：若其中有在宣稱已登記的事實，就去 site-facts.json 補 assert_pattern。")

    if not errors and not warnings:
        print("✅ 全站事實一致")
    print("————————————————————————————————————————")
    print("⚠️ 本檢查只驗**已登記在 config/site-facts.json 的事實**，"
          "且只認得已登記的說法。沒登記的數字它看不見——這是設計取捨，見該檔 _design_v2。")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
