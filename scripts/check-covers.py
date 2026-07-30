#!/usr/bin/env python3
"""封面數字對帳 gate。

存在理由（這是本站 gate 體系裡的一個實質漏洞）：
封面是 PNG，**站上所有既有 gate 都掃不到它**——`verify-sources` 掃 markdown、
`verify-recap`／`verify-standings` 重打 API 對帳正文，沒有一道看得見圖裡的像素。
於是封面成了唯一可以合法印出「文章沒說過的數字」的地方，而它同時是分享卡、
索引卡與內文頂圖，比正文更多人先看到。這正是本站踩過的
「自動內容的手動靜態檔＝staleness 炸彈」那一族。

做法：把封面 HTML 的**可見文字**抽出來，逐一比對該篇文章的 index.md。
封面上出現、文章裡沒有的數字字面，一律擋下；真有正當理由的要寫進
`design/covers/covers.json` 的 `allow`，附理由（default-deny，比照 approved.json）。

⚠️ 這道 gate 的宣稱邊界（不要當成它擋得住的事）：
  ① 它只驗**數字字面出現過**，不驗語意。封面把「早 17 分鐘」寫成「晚 17 分鐘」照樣會過。
  ② 它掃 HTML 文字，不掃 PNG。HTML 改了沒重新 render，它抓不到——那由
     render-covers.py 的 --check 負責（比對 PNG 是否比 HTML 舊）。
  ③ 文章寫「千分之一秒」而封面寫「0.001 秒」時它會擋。這是**設計如此**：
     兩種寫法無法互相印證，該由人決定改哪一邊。
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
COVER_DIR = ROOT / "design" / "covers"
ARTICLES = ROOT / "articles"

# 數字字面：整數、千分位、小數、時刻（15:36:56）、成績（1:39:56.180）
NUM = re.compile(r"\d[\d,]*(?:[:.]\d+)*")


def visible_text(html):
    """只留可見文字：拿掉註解、<style>／<script> 區塊，再拿掉所有標籤（含屬性）。

    屬性一定要一起拿掉——`style="left:11.858%"`、`viewBox="0 0 2140 340"`、
    `flex:15` 裡的數字都不是給讀者看的，掃進來只會製造假警報，
    而假警報會訓練出「這道檢查一向紅、忽略它」的習慣（本站 7/30 在 check_links 踩過）。
    """
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"<[^>]*>", " ", html)


def article_body(slug):
    path = ARTICLES / slug / "index.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def appears(token, text):
    """數字要以「獨立數字」出現，不能是別的數字的一截。

    否則 `4` 會被 `2026` 裡的 4 滿足，等於這道 gate 對所有一位數失效。

    ⚠️ 邊界必須含冒號。初版寫成 `(?<![\\d.])…(?![\\d.])`，於是封面寫 `15:36`
    會被正文的 `15:36:56` 滿足——**截斷的時刻假性通過**，而截斷時刻正是這種圖最容易
    寫錯的東西（本檔的反向測試第一次跑就抓到這個洞）。同理 `7` 不該被 `16:07:01` 滿足。
    """
    return re.search(r"(?<![\d.:])" + re.escape(token) + r"(?![\d.:])", text) is not None


def check_one(entry):
    slug, name = entry["slug"], entry["html"]
    html_path = COVER_DIR / name
    if not html_path.exists():
        print(f"❌ {slug}：找不到封面 HTML {name}")
        return False
    body = article_body(slug)
    if body is None:
        print(f"❌ {slug}：找不到 articles/{slug}/index.md")
        return False

    allow = entry.get("allow", {})
    text = visible_text(html_path.read_text(encoding="utf-8"))
    missing = []
    for token in dict.fromkeys(NUM.findall(text)):   # 去重但保留出現順序，訊息比較好讀
        if token in allow or appears(token, body):
            continue
        missing.append(token)

    if missing:
        print(f"❌ {slug}（{name}）：封面上有 {len(missing)} 個數字在文章裡找不到")
        for t in missing:
            ctx = re.search(r".{0,28}" + re.escape(t) + r".{0,28}", text, re.S)
            snippet = " ".join(ctx.group(0).split()) if ctx else t
            print(f"   ・{t}　← 封面內容：…{snippet}…")
        print("   → 改封面、改文章，或在 covers.json 的 allow 裡具名並寫理由。")
        return False

    print(f"✅ {slug}（{name}）：可見數字 {len(set(NUM.findall(text)))} 種全部見於正文"
          + (f"，另有 {len(allow)} 項具名例外" if allow else ""))
    return True


def main():
    ap = argparse.ArgumentParser(description="比對封面 HTML 的可見數字是否都出現在對應文章裡")
    ap.add_argument("--slug", help="只檢查單一篇")
    args = ap.parse_args()

    manifest = json.loads((COVER_DIR / "covers.json").read_text(encoding="utf-8"))
    entries = manifest["covers"]
    if args.slug:
        entries = [e for e in entries if e["slug"] == args.slug]
        if not entries:
            print(f"❌ covers.json 裡沒有 slug={args.slug}")
            return 1

    ok = all(check_one(e) for e in entries)
    print("—" * 40)
    print("封面數字對帳：全部通過" if ok else "封面數字對帳：有未通過項，見上方")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
