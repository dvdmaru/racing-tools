#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-zh-review-pack.py — 百科線 M6：Charlie 譯名裁決包（data/f1/zh-review-pack.md）。

把 fetch-zh-candidates 的候選（data/f1/zh-candidates.json，全 pending）整理成好編輯的
markdown table，分四批（車手／車隊／賽道／歷史站名），每列：
  原文 | zhwiki 候選（zh-tw 變體） | 變體轉換 | 備註（明顯大陸譯名者標警語）| ✅ 核准譯名（空白待填）

Charlie 逐批核准後，把「✅ 核准譯名」欄填好 → 另立 migration append 進四張表（status:approved）。
本檔只讀 candidates 快取、不抓網路、不改任何譯名表。

用法：python3 scripts/gen-zh-review-pack.py
"""
import collections
import datetime
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "f1" / "zh-candidates.json"
OUT = ROOT / "data" / "f1" / "zh-review-pack.md"

BATCHES = [
    ("driver", "車手", "Ergast familyName"),
    ("constructor", "車隊", "constructor 名"),
    ("circuit", "賽道", "circuitName"),
    ("race", "歷史站名", "raceName"),
]


def _esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def note_for(v: dict) -> str:
    if v["status"] != "pending":
        return ""
    warns = []
    if v.get("raw_had_simplified"):
        warns.append("⚠️來源為簡體條目")
    if v.get("variant_converted"):
        warns.append("字形已轉繁（用詞未必台版）")
    else:
        warns.append("variant 未轉換（zhwiki 原樣）")
    # zhwiki 常是大陸譯名，統一提醒
    warns.append("zhwiki 多為大陸譯法，需人工確認")
    return "；".join(warns)


def main():
    doc = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {"candidates": {}}
    cand = doc.get("candidates", {})

    lines = []
    lines.append("# F1 譯名裁決包（Charlie 逐批核准用）")
    lines.append("")
    lines.append(f"> 產生時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}　"
                 f"來源：`data/f1/zh-candidates.json`（zhwiki + wikidata + variant=zh-tw）")
    lines.append("")
    lines.append("**用法**：候選全部是 `pending`，對頁面完全不可見。逐列在「✅ 核准譯名」欄填入你定版的繁中譯名"
                 "（可直接採候選、可改、可留空表示暫不核准）。填好後交回，會另立 migration 把核准列 append 進"
                 "四張譯名表（`status:approved`）並重生受影響頁——**現有 approved 值一律不動（append-only）**。")
    lines.append("")
    lines.append("> ⚠️ zhwiki 標題常是**大陸譯名**；`variant=zh-tw` 只轉字形（奥→奧）不轉用詞選擇"
                 "（范吉奧≠台版方吉歐）。候選僅供參考，請以台灣慣例定版。")
    lines.append("")

    # 統計
    total_stat = collections.Counter()
    per_batch = {}
    for ns, _, _ in BATCHES:
        rows = sorted([v for v in cand.values() if v["namespace"] == ns], key=lambda v: v["id"])
        pend = [v for v in rows if v["status"] == "pending"]
        nf = [v for v in rows if v["status"] != "pending"]
        per_batch[ns] = (rows, pend, nf)
        total_stat["pending"] += len(pend)
        total_stat["not_found"] += len(nf)

    lines.append("## 總覽")
    lines.append("")
    lines.append("| 批次 | 有候選(pending) | 查無(not_found) | 小計 |")
    lines.append("|---|--:|--:|--:|")
    for ns, zh_label, _ in BATCHES:
        rows, pend, nf = per_batch[ns]
        lines.append(f"| {zh_label} | {len(pend)} | {len(nf)} | {len(rows)} |")
    lines.append(f"| **合計** | **{total_stat['pending']}** | **{total_stat['not_found']}** | "
                 f"**{total_stat['pending'] + total_stat['not_found']}** |")
    lines.append("")

    for ns, zh_label, src_label in BATCHES:
        rows, pend, nf = per_batch[ns]
        lines.append(f"## {zh_label}（{src_label}）")
        lines.append("")
        if not rows:
            lines.append("_（無此批資料——尚未抓取或全數已有 approved 譯名。）_")
            lines.append("")
            continue
        lines.append("| id | 原文 | zhwiki 候選（zh-tw） | 備註 | ✅ 核准譯名 |")
        lines.append("|---|---|---|---|---|")
        for v in pend:
            lines.append(f"| `{_esc(v['id'])}` | {_esc(v['en'])} | {_esc(v.get('zh_variant_tw') or '')} "
                         f"| {_esc(note_for(v))} |  |")
        # not_found 集中列在批次尾（沒有候選，仍列出讓 Charlie 知道哪些要人工補）
        if nf:
            lines.append("")
            nf_ids = "、".join(f"`{v['id']}`（{_esc(v['en'])}）" for v in nf)
            lines.append(f"**查無 zhwiki 候選（{len(nf)}，需人工補或留原文）**：{nf_ids}")
        lines.append("")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"📝 裁決包 → {OUT}")
    print(f"   pending={total_stat['pending']}  not_found={total_stat['not_found']}")


if __name__ == "__main__":
    main()
