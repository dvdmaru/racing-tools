#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文章內文不得混入簡體專用字（零星漏網的把關）。

為什麼有這支：2026-09-28 新手村第五批，`f1-101-circuit-grade` 的「賽曆」有 7 處寫成簡體「賽历」，
橫跨正文與兩張 SVG；多輪異源審稿（agy／Terra）不檢查字元集，`check-zh.py` 也沒抓到——
**因為 `check-zh.py` 是譯名表一致性 gate，只掃車手／車隊／分站／賽道名四張表，從來不掃文章內文**，
它報「0 簡體命中」對文章完全沒有資訊量。全域 hook `check-tw-wording.py` 另有簡體指紋，
但它的設計是「整篇是簡體」才報（≥6 字且佔 CJK 1.5% 以上），零星幾個字一律放行。
所以「繁體文章裡零星混進幾個簡體字」原本沒有任何一道閘。本測試補這個洞。

字集：取自 check-tw-wording.py 的 SIMP_FINGERPRINT（出現在真實簡體樣本、且在 699 個已知繁體檔
中從未出現）＋「历」（賽历）。刻意剔除在繁體正字裡也有獨立用法或易誤報的兩用字（見 AMBIGUOUS）。

⚠️ 新增例外請寫進 ALLOWED，且必須附理由（例如某篇刻意對照簡繁字形）。目前零例外。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTICLES = ROOT / "articles"

_FINGERPRINT = (
    "专丝两为举么买于亚从们价众优会传侧关兴养内写决况几刚创别卖厂厉发吁后吗"
    "喷团国圆块坞复够实对尴属岁帅帮广张强当忆战换据摇数旧时显术柜欢毕湾滚满"
    "热现确种红纤纸线组细绍经给续维缝网胶节莱蓝虽蛮装裤见观觉计认让议讯讲论"
    "设识试话诞该详语说请谁调贵费车转轻较边过还进连适钱铜销长门问间队际随隐"
    "难顺题觉环认识产资职离独开点记东头变梦学个这来样没"
    "凭选择译结户闭并启状"
)
# 繁體裡也有獨立用法、或在正文容易當成正字的兩用字：一律不列入，避免誤報。
AMBIGUOUS = set("于么几后吁复发")
SIMPLIFIED_ONLY = (set(_FINGERPRINT) | {"历"}) - AMBIGUOUS

# 例外：{文章 slug: 理由}。目前沒有任何一篇需要。
ALLOWED: dict = {}


def mask(line: str) -> str:
    """遮掉行內程式碼與網址（與全域 hook 相同的遮法）。"""
    line = re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), line)
    return re.sub(r"https?://\S+|www\.\S+", lambda m: " " * len(m.group(0)), line)


def scan_text(text: str):
    """回 [(行號, 字, 該行前 40 字)]。"""
    hits = []
    for i, raw in enumerate(text.split("\n"), 1):
        line = mask(raw)
        for ch in line:
            if ch in SIMPLIFIED_ONLY:
                hits.append((i, ch, raw.strip()[:40]))
    return hits


class SimplifiedCharScanner(unittest.TestCase):
    def test_positive_control_catches_the_0928_leak(self):
        """陽性對照：9/28 的漏網字「历」必須被抓到，而且是逐字抓到。"""
        self.assertIn("历", SIMPLIFIED_ONLY)
        hits = scan_text("2024 年：中國大獎賽重返 F1 賽历")
        self.assertEqual([h[1] for h in hits], ["历"])

    def test_positive_control_every_char_is_detected_individually(self):
        """陽性對照 2：字集裡每一個字單獨出現都抓得到（防止 set 被改壞卻沒人發現）。"""
        self.assertGreaterEqual(len(SIMPLIFIED_ONLY), 150)
        for ch in sorted(SIMPLIFIED_ONLY):
            with self.subTest(ch=ch):
                self.assertEqual([h[1] for h in scan_text(f"示例{ch}示例")], [ch])

    def test_negative_control_traditional_text_passes(self):
        """陰性對照：正確的繁體與兩用字不誤報（台灣／平台／公里／站群／皇后／賽曆／歷史）。"""
        ok = "台灣 平台 公里 站群 皇后 賽曆 歷史 於是 什麼 幾乎 發車 後來 吁請 回復 複雜 維斯塔潘 國殤"
        self.assertEqual(scan_text(ok), [])
        self.assertTrue(AMBIGUOUS.isdisjoint(SIMPLIFIED_ONLY))

    def test_code_and_urls_are_masked(self):
        """行內程式碼與網址不算（與全域 hook 相同）。"""
        self.assertEqual(scan_text("範例 `这个` 與 https://example.com/这/个 皆不計"), [])

    def test_no_article_contains_simplified_only_chars(self):
        """真實樹：articles/*/index.md 每一篇（含 frontmatter、SVG 文字）零簡體專用字。"""
        bad = {}
        files = sorted(ARTICLES.glob("*/index.md"))
        self.assertGreater(len(files), 50, "沒掃到文章，測試本身失效")
        for f in files:
            slug = f.parent.name
            if slug in ALLOWED:
                continue
            hits = scan_text(f.read_text(encoding="utf-8"))
            if hits:
                bad[slug] = hits[:5]
        msg = "\n".join(
            f"  {slug}: " + "；".join(f"L{n}『{c}』{ctx}" for n, c, ctx in hs)
            for slug, hs in bad.items()
        )
        self.assertEqual(bad, {}, f"文章混入簡體專用字（改成繁體正字；若刻意對照請加 ALLOWED 並附理由）：\n{msg}")


if __name__ == "__main__":
    unittest.main()
