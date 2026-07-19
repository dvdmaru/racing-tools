# Design v2「計時螢幕 × 亮色莫蘭迪」交付快照

來源：claude.ai/design 專案「F1 數據站 UI 優化」（1f9dc8c3-5a4e-4cc3-9810-6b2a53d5b104）。
完整五頁 mock 存在該專案 mocks/；此處只留 tokens.css 與 CHANGES.md 當工程側依據。
套皮實作：scripts/racinglib.py（tokens/header/表格共用層）。standings 頁零標記改動；
home/calendar/article 的標記級改動（.nr-* 看板、.ses chips、.art-toc）尚未實作，見 CHANGES.md。

## v2.2「定案 D：深色重心」（2026-07-19 第二輪）
mock 更新：每主題獨立暖色調文字系＋--ink 深色錨（header/表頭/切換器深色底）、五主題 accent 全換
（紅/綠/金/橘/藍）。token 快照以 scripts/racinglib.py 的 _theme_tokens_css() 為準（verbatim）。
⚠️ IP 紅線改動：mock carbon accent #e10600＝F1 官方品牌色精確色號、label「F1 紅」→
實作改 #d63a2f「賽車紅」（等效視覺、非官方色號）。此處 tokens.css 為 v2（莫蘭迪紫）歷史快照。
