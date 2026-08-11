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

2026-08-11 新增**第二層：主張錨定**。數字對帳只管數字，但封面漂移不只發生在數字上
（姊妹站 basketball 實例：查核桌否決的「首創」留在封面上線，數字一個都沒錯）。
第二層問的是「封面上的每個說法，文章有沒有這樣說過」，找不到依據的片段要寫進
`covers.json` 的 `allow_claims` 具名放行。**這一層上線第一次跑就抓到一個線上錯誤**：
封面印「22 賽站」，文章寫「全季因此定為 23 站」——而數字層是**放行**的，因為文章裡
確實有「22」（指「22 台車」與一個網址 slug）。同一個數字、不同語境。

⚠️ 這道 gate 的宣稱邊界（不要當成它擋得住的事）：
  ① 它只驗**數字字面出現過**，不驗語意。封面把「早 17 分鐘」寫成「晚 17 分鐘」照樣會過。
  ② 它掃 HTML 文字，不掃 PNG。HTML 改了沒重新 render，它抓不到——那由
     render-covers.py 的 --check 負責（比對 PNG 是否比 HTML 舊）。
  ③ 文章寫「千分之一秒」而封面寫「0.001 秒」時它會擋。這是**設計如此**：
     兩種寫法無法互相印證，該由人決定改哪一邊。
  ④ ☠️ **重組既有詞彙造出的新主張抓不到。** 主張層驗的是「片段在文章出現過」，
     所以把文章裡各自存在的詞重新拼起來，它會全綠。實測：封面寫「F1 史上最大改版」
     **通過**——「史上」「最大」「改版」在文章裡都有，但文章原話是
     「至於『這是不是 F1 史上改動最大的一次』，本站沒有可引用的一手依據，所以不下這個判斷」，
     也就是文章**明確拒絕**下這個判斷。**封面的主張仍然要人讀過一次。**
  ⑤ 孤立一位數在有依據的語境下改動，數字層也可能放行（文章別處有那個數字即可）。
     要真正關掉 ④⑤ 需要中文斷詞與語意比對，屬另一個題目。
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


# ── 主張錨定（2026-08-11 新增的第二層）────────────────────────────────────
# 數字對帳只管數字。但封面漂移不只發生在數字上——姊妹站 basketball 的實例：
# 查核桌把「名人堂稱**首創**」判為過度主張，正文與 FAQ 全改成「創新者」，
# 封面沒改，帶著被否決的主張上線（數字一個都沒錯，所以數字 gate 全綠）。
# 這一層問的是：**封面上的每個說法，文章有沒有這樣說過？**

# SKIP：標點／分隔／拉丁字母。不計分、不報。
# ⚠️ 全形標點要跟半形一起列。漏了「／」會讓「圈數／共 70 圈」黏成「／共」這種
#    假片段——本站文案幾乎全用全形，只列半形等於這張表對本站無效（2026-08-11 實測）。
CLAIM_SKIP = set(" 　·・.,，、。：:；;！!？?—－-–—「」『』（）()【】[]/|×~〜%°"
                 "／＝＋＜＞＆＃＊％〜｜＄　"
                 "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")

# STOP：中文虛詞。不計分、不報，**而且不能單獨撐起一個錨點**——
# 允許任意 2 字子字串當錨點時，跨詞邊界的巧合片段（「的三」）會把真漂移
# （「三月」）整個掩蓋掉。錨點必須含 2 個以上實詞字。
# ⚠️ 程度副詞（最／更／很）刻意不列入——「史上最快」正是要擋的誇大詞。
CLAIM_STOP = set("的了是在和與也就都他她它我你這那之其而於及但個一到把被讓使或且則"
                 "又再才只已會後前上下中內外時年說有從對向跟等麼呢吧嗎過來去做為以")

MIN_CONTENT = 2          # 未錨定區含幾個實詞字才報
MIN_ANCHOR_CONTENT = 2   # 一個合法錨點至少要含幾個實詞字
MAX_PROBE = 12


def _is_content(ch):
    return ch not in CLAIM_SKIP and ch not in CLAIM_STOP


def _content_count(s):
    return sum(1 for ch in s if _is_content(ch))


def squash(s):
    """去掉所有空白，讓「1,335 勝」對得上「1,335勝」（盤古之白差異）。"""
    return re.sub(r"[\s　]+", "", s)


def unanchored_runs(cover, article):
    """回傳封面文案中錨不到文章的片段。

    ⚠️ 用 DP 求「未錨定實詞字數最小」的切法，**不可用貪婪最長匹配**：
    貪婪會為了吃下最長片段而拆散相鄰詞，把本來錨得到的內容誤報成漂移。
    局部最長 ≠ 整體最佳；gate 自己判定先錯，就會拿假陽性去指控別人。
    """
    n = len(cover)
    INF = float("inf")
    cost = [INF] * (n + 1)
    choice = [None] * (n + 1)
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        if not _is_content(cover[i]):
            cost[i], choice[i] = cost[i + 1], ("free", 1)
            continue
        best, bc = cost[i + 1] + 1, ("miss", 1)
        for L in range(2, min(MAX_PROBE, n - i) + 1):
            frag = cover[i:i + L]
            if _content_count(frag) < MIN_ANCHOR_CONTENT:
                continue
            if frag in article and cost[i + L] < best:
                best, bc = cost[i + L], ("hit", L)
        cost[i], choice[i] = best, bc

    runs, cur, i = [], "", 0
    while i < n:
        kind, L = choice[i]
        if kind == "miss":
            cur += cover[i]
        elif kind == "free":
            if cover[i] in CLAIM_SKIP:     # 標點切斷片段，不當膠水
                if _content_count(cur) >= MIN_CONTENT:
                    runs.append(cur.strip("".join(CLAIM_STOP)))
                cur = ""
            elif cur:
                cur += cover[i]
        else:
            if _content_count(cur) >= MIN_CONTENT:
                runs.append(cur.strip("".join(CLAIM_STOP)))
            cur = ""
        i += L
    if _content_count(cur) >= MIN_CONTENT:
        runs.append(cur.strip("".join(CLAIM_STOP)))
    return runs


# 版面 chrome：站名、欄目標籤、頁尾 disclaimer、圖表軸標與圖例。
# 這些在描述品牌或視覺編碼（「每段寬度＝領跑圈數」），不是對賽事的主張，
# 本來就不該出現在文章裡——不排除的話它們會變成永久紅燈，
# 而永久紅燈會訓練出「這道檢查一向紅」的習慣（本站 7/30 在 check_links 踩過）。
# （數字層不排除這些——那邊已校準過，圖例裡的年份數字仍該對帳。）
CHROME_CLASSES = ("brand", "tag", "foot", "lbl", "legend")


def claim_segments(html):
    """給主張層用的可見文字，**以元素邊界切段**回傳。

    ⚠️ 不可以把整張封面併成一串再比對：`visible_text` 用空白分隔各元素，
    若之後 squash 掉空白，相鄰元素的文字會被黏起來，產生「次數4」這種
    根本不存在於封面上的跨元素假片段（2026-08-11 實測）。
    以元素為單位切段後，段內仍 squash（吸收盤古之白差異），段間不相連。
    """
    for cls in CHROME_CLASSES:
        html = re.sub(r'<(\w+)[^>]*class="[^"]*\b' + cls + r'\b[^"]*".*?</\1>',
                      " ", html, flags=re.S)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]*>", "\n", html)          # 標籤→換行＝段界
    return [squash(seg) for seg in html.split("\n") if squash(seg)]


def check_claims(entry, html, body):
    """封面可見文字裡的說法，逐段對照文章。allow_claims 是具名例外（要寫理由）。"""
    allow = entry.get("allow_claims", {})
    art = squash(body)
    runs = []
    for seg in claim_segments(html):
        runs.extend(unanchored_runs(seg, art))
    missing = [r for r in dict.fromkeys(runs) if r not in allow]
    return missing, [r for r in dict.fromkeys(runs) if r in allow]


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

    bad_claims, allowed_claims = check_claims(entry, html_path.read_text(encoding="utf-8"), body)

    if missing:
        print(f"❌ {slug}（{name}）：封面上有 {len(missing)} 個數字在文章裡找不到")
        for t in missing:
            ctx = re.search(r".{0,28}" + re.escape(t) + r".{0,28}", text, re.S)
            snippet = " ".join(ctx.group(0).split()) if ctx else t
            print(f"   ・{t}　← 封面內容：…{snippet}…")
        print("   → 改封面、改文章，或在 covers.json 的 allow 裡具名並寫理由。")

    if bad_claims:
        print(f"❌ {slug}（{name}）：封面上有 {len(bad_claims)} 個說法文章從沒這樣說過")
        for t in bad_claims:
            print(f"   ・{t}")
        print("   → 改封面、改文章，或在 covers.json 的 allow_claims 裡具名並寫理由。")

    if missing or bad_claims:
        return False

    print(f"✅ {slug}（{name}）：可見數字 {len(set(NUM.findall(text)))} 種全部見於正文；"
          f"說法全部錨到文章"
          + (f"（數字例外 {len(allow)}、說法例外 {len(allowed_claims)}）"
             if allow or allowed_claims else ""))
    return True


def self_test():
    """主張層的陽性／陰性／見證測試。合成輸入，不依賴任何文章內容。"""
    ok = True
    # 刻意排布：「小巨蛋」與「的三季」分處兩句，否則「小巨蛋的三」會成為合法錨點，
    # 合成 1 會假性通過（移植時實際踩到：測試資料先錯，害我以為演算法壞了）。
    art = squash("賽程橫跨秋冬春的三季，決賽在小巨蛋舉行。"
                 "衛冕軍首輪籤選到最後一名，場館裡空氣稀薄。全季定為 23 站。")

    print("【陽性 1】文章沒說過的說法要抓到")
    r = unanchored_runs(squash("小巨蛋的三月"), art)
    print(f"  {'✓ 抓到 ' + str(r) if r else '✗ 沒抓到'}")
    ok &= bool(r)

    print("\n【陰性 1】虛詞不得單獨撐起錨點的反面：合法內容不可誤報")
    r = unanchored_runs(squash("衛冕軍首輪籤選到空氣"), art)
    print(f"  {'✓ 無假陽性' if not r else '✗ 貪婪／虛詞 bug 回歸：' + str(r)}")
    ok &= not r

    print("\n【陰性 2】全形標點要切斷片段，不可黏成跨欄假片段")
    r = unanchored_runs(squash("23 站／共 23 站"), art)
    print(f"  {'✓ 未黏出「／共」這類片段' if not r else '✗ ' + str(r)}")
    ok &= not r

    print("\n【見證】☠️ 重組既有詞彙的新主張抓不到（宣稱邊界 ④）")
    # 這條**期待抓不到**。哪天它開始抓到了（＝有人補了語意層），這條會亮警示，
    # 提醒把 docstring 的 ④ 一起刪掉——免得文件繼續說一個已經不成立的限制。
    art2 = squash("這是不是史上改動最大的一次，本站沒有依據，所以不下判斷。這次改版幅度很大。")
    r = unanchored_runs(squash("史上最大改版"), art2)
    print(f"  {'✓ 如宣稱般抓不到（缺口仍在，docstring 屬實）' if not r else '⚠️ 已能抓到 → 請更新宣稱邊界 ④：' + str(r)}")
    ok &= not r

    print("\n" + ("✅ 主張層自我測試全過" if ok else "❌ 主張層自我測試失敗"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="比對封面 HTML 的可見數字與說法是否都出現在對應文章裡")
    ap.add_argument("--slug", help="只檢查單一篇")
    ap.add_argument("--self-test", action="store_true", help="跑主張層的合成自我測試")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    manifest = json.loads((COVER_DIR / "covers.json").read_text(encoding="utf-8"))
    entries = manifest["covers"]
    if args.slug:
        entries = [e for e in entries if e["slug"] == args.slug]
        if not entries:
            print(f"❌ covers.json 裡沒有 slug={args.slug}")
            return 1

    # ⚠️ 不可以寫 all(check_one(e) for e in entries)——generator 會短路，
    #    第一篇不過就跳過其餘篇，把其他問題藏起來。先全跑完再彙總。
    results = [check_one(e) for e in entries]
    ok = all(results)
    print("—" * 40)
    print("封面數字對帳：全部通過" if ok else "封面數字對帳：有未通過項，見上方")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
