# 第一批文章風格調整審閱紀錄

三篇先給事件或算例，再展開證據；刪除偏離主線的支線，來源方法集中於文末。標題、日期與slug維持原值。290公里封面同步正文口徑，封王算術SVG維持原樣。

Sonnet寫手 → 雙席R2及修正結案 → Opus冷讀與減法 → 雙席R3三篇GO；末次圖說／封面文字微調另經獨立結案。

最終來源SHA-256：

- `f1-101-championship-scenarios`：`5f649ecd426b75f11c694d8345fca3d68e931952bf013e93f2528214270c56e3`
- `f1-2026-r17-singapore-ferrari-strategy-ledger`：`2c19fd58d1bc22f3d3064c5b3b479da93ecfc16a16ccefa8833b48302e5e7531`
- `f1-2027-race-distance-290km`：`e89a9c7755b1e9b0941fd52987fec3c1f0d229a301a750ec6540231cd04433d9`

本PR僅供內容審閱。`approved.json`保留舊簽核，未產正式站輸出，未取得此次發布授權。取得Charlie授權後才重簽新雜湊、建置輸出與CI、合併／手動部署並驗收正式站。不可直接合併此草稿。

## 驗證

完整測試：基線966項全過；改稿後966項中964通過、2失敗（142.771秒）。失敗為`ApprovedArticlesAreStillApproved.test_every_approved_article_matches_its_recorded_sha`（正確擋下未重簽的三稿），以及`DeterminismTests.test_existing_champion_pages_gain_only_current_constructor_links`（車手頁相關文章變更）。後者的生成器`gen-racing-drivers.py:389`使用`interlink.related_articles_html`，其`published_articles`在`interlink.py:615`排除雜湊不符的新稿，所以與原公開頁比較會改變相關文章清單。兩項均保留失敗，沒有改簽核或放寬測試；正式發布前重簽／建置後必須再跑。

另已跑指南與圖表26項全過，兩篇封面主張及全站已登記事實檢查通過，`git diff --check`通過。測試日誌見`evidence/final-tests.log`。
