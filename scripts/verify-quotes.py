#!/usr/bin/env python3
"""引文忠實度 gate：facts pack 裡的每一句外語引文，是否真的出現在來源快照裡。

存在理由（2026-09-04 實測事故，這道 gate 就是那次的產物）：
外部來源文的 facts pack 由指揮席建，引文由查核／研究席回報。他們回報的「逐字引句」
其實常常來自**網頁摘要**——摘要是模型改寫過的，字面與原文不同，但讀起來完全像引文。
那次事故裡，被指揮席自己標成「⭐⭐ 全篇最有價值」的三句 The Race 引文，
逐字比對後在原文中**一句都不存在**；理由整段是錯的（原文講的是 fuel-economy runs，
摘要寫成 talking point／shelf life）。稿子已經把它寫成一整節，差一步就上線。

☠️ 關鍵教訓：**站上原有的四道 gate 沒有一道看得見這件事。**
`verify-sources` 擋的是無名歸因（「專家認為」）與資料來源區塊，它不在乎引號裡的字
是不是真的出自那個來源——一句**掛著具名出處的假引文**可以全綠通過。
引文是外部來源文最核心的證據，而它原本是唯一零機械覆蓋的一層。

做法：
  1. 遞迴走訪 facts pack，收集所有 key 以 `verbatim` 開頭的字串值（verbatim、
     verbatim2、verbatim_full、commercial_context_verbatim…）。
  2. 對每一句，在快照目錄裡找有沒有任何一個檔逐字包含它（正規化後）。
     含省略號（… 或 ...）的引文拆成片段，要求**同一份快照**裡每一段都在——
     省略中段是正當引用，但片段散落在不同來源就是拼接，那是要擋的。
  3. 找不到就是紅燈，印出該句與它所屬的路徑。

正規化只做「不改變字義」的那幾種：HTML 實體、標籤、彎引號、各種破折號、
連續空白。⚠️ **刻意不做大小寫以外的模糊比對**——把 rock 比成 rocks 那種寬鬆比對
會讓這道 gate 變成裝飾品。寧可紅燈要人來看，不要綠燈騙人。

快照怎麼來（不進版控，因為是他人著作全文）：
    curl -sL -A "<UA>" -o <dir>/raw-<name>.html <url>
快照放本機或 CoWork 桌檔，路徑用 --snapshots 傳進來。

⚠️ 這道 gate 的邊界（不要當成它擋得住的事）：
  ① 它只驗**字面在快照裡出現過**，不驗那個快照是不是你以為的那篇文章
     （HTTP 200 不等於拿到對的文件）。快照身分要人自己看一眼。
  ② 它不驗**歸屬**：引文出自 A 媒體卻被標成 B 媒體，只要兩份快照都在目錄裡，
     它會綠。要擋這個得逐句綁定來源，目前刻意不做——先擋掉「整句不存在」這一類。
  ③ 它不驗中文翻譯對不對。翻錯是語意問題，機械擋不了。
  ④ 快照抓的是**今天**的網頁；文章事後被編輯過，原本命中的句子會變紅燈。
     那不是誤判，是真的要重新確認。

用法：
    python3 scripts/verify-quotes.py --facts facts/analysis-2027-race-distance.json \\
        --snapshots ~/…/roundtable/2026-09-04-racing-2027-race-distance/evidence
"""
import argparse
import html
import json
import pathlib
import re
import sys

# 至少這麼多字才當成「引文」。太短的片語（"broad agreement"）在任何快照裡都撈得到，
# 驗了也沒有鑑別力，反而製造安全感。
MIN_WORDS = 4


def normalise(s: str) -> str:
    """只做不改變字義的正規化。"""
    s = html.unescape(s)
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    for dash in ("—", "–", "‑"):
        s = s.replace(dash, "-")
    # 破折號寫法：原文常用 -- 或 -，引用者常改成 —。折成單一 -，
    # 這不改變字義，只吸收排版差異。
    s = re.sub(r"-{2,}", "-", s)
    s = s.replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


# 文章裡的引文一律包在全形引號「」內（站規）。抽出其中含足量英文字的，
# 就是要驗的外語引文；純中文的「」是強調或術語，不在本 gate 範圍。
QUOTED = re.compile(r"「([^」]+)」")


def article_quotes(md_text):
    """回傳 [(行號, 引文)]，只收英文字數達門檻的。"""
    out = []
    for ln, line in enumerate(md_text.split("\n"), 1):
        for m in QUOTED.finditer(line):
            q = m.group(1)
            if len(re.findall(r"[A-Za-z']+", q)) >= MIN_WORDS:
                out.append((ln, q))
    return out


def collect_quotes(node, path=""):
    """遞迴撿出所有 key 以 verbatim 開頭的字串值。"""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            here = f"{path}.{k}" if path else k
            if isinstance(v, str) and k.startswith("verbatim"):
                out.append((here, v))
            else:
                out.extend(collect_quotes(v, here))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(collect_quotes(v, f"{path}[{i}]"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", help="要驗的 facts pack（驗寫稿輸入）")
    ap.add_argument("--article", help="要驗的文章 index.md（驗成品輸出）")
    ap.add_argument("--snapshots", required=True,
                    help="來源快照目錄（raw-*.html 或 *.txt）")
    ap.add_argument("--min-words", type=int, default=MIN_WORDS)
    args = ap.parse_args()

    if not args.facts and not args.article:
        print("❌ 至少要給 --facts 或 --article 其中一個")
        return 2
    snap_dir = pathlib.Path(args.snapshots).expanduser()
    if not snap_dir.is_dir():
        print(f"❌ 快照目錄不存在：{snap_dir}")
        return 2

    snaps = {}
    for p in sorted(snap_dir.iterdir()):
        if p.suffix.lower() in (".html", ".htm", ".txt") and p.is_file():
            snaps[p.name] = normalise(p.read_text(encoding="utf-8", errors="replace"))
    if not snaps:
        print(f"❌ 快照目錄裡沒有 .html／.txt：{snap_dir}")
        return 2

    quotes = []
    if args.facts:
        pack = json.loads(pathlib.Path(args.facts).read_text(encoding="utf-8"))
        quotes += collect_quotes(pack)
    if args.article:
        md = pathlib.Path(args.article).read_text(encoding="utf-8")
        quotes += [(f"{args.article}:L{ln}", q) for ln, q in article_quotes(md)]
    checked = misses = 0
    print(f"🔎 引文忠實度 gate：{args.facts or ''} {args.article or ''}".rstrip())
    print(f"   快照 {len(snaps)} 份、verbatim 欄位 {len(quotes)} 個"
          f"（少於 {args.min_words} 個英文字的略過）\n")

    for path, quote in quotes:
        # 只驗外語引文：中文引文沒有「逐字快照」可比，是另一個題目。
        if len(re.findall(r"[A-Za-z']+", quote)) < args.min_words:
            continue
        checked += 1
        # 省略號＝引用者刻意略去中段。拆成片段，要求同一份快照裡每段都在。
        parts = [normalise(f) for f in re.split(r"\s*(?:\.{3}|…)\s*", quote)]
        parts = [f for f in parts if f]
        hits = [n for n, txt in snaps.items() if all(f in txt for f in parts)]
        if hits:
            print(f"✅ {path}\n   └ 命中 {hits[0]}")
        else:
            misses += 1
            print(f"❌ {path}\n   └ 快照中查無此句：{quote[:150]}"
                  f"{'…' if len(quote) > 150 else ''}")

    print(f"\n{checked} 句受檢，{checked - misses} 句逐字命中，{misses} 句沒有。")
    if misses:
        print("☠️ 有引文在來源快照裡找不到。最常見的原因是那句話來自**網頁摘要**"
              "而不是原文——摘要會改寫。回原文重取，不要微調引文去遷就。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
