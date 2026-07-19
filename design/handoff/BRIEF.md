# racing.twtools.cc（賽車數據誌 @RACING）UI/UX 優化 brief

> 給 Claude Design：請先讀完本 brief，再看附上的五頁現況 HTML（自帶完整 CSS，直接開就能看）。
> 目標是「優化現有設計」不是砍掉重練——資訊架構與內容不動，視覺與體驗升級。

## 站是什麼

非官方繁體中文 F1 數據站（live：https://racing.twtools.cc）。三個每週自動更新的資料頁（積分榜/台北時間賽曆/各站賽果）＋首頁 dashboard＋長文（規則指南/譯名對照表）。受眾：台灣 F1 觀眾，主場景是「深夜/清晨查台北時間」與「賽後看積分」，手機為主。

## 🔴 不可違反的紅線（IP／法務）

1. 禁用任何 F1 官方素材：官方 logo、官方字體（Formula1 字體）、車隊 logo 與塗裝配色聯想、官方照片、車手肖像。
2. 站名品牌不得出現「F1」字樣（內文文字提及 OK）；brand mark 是「@RACING」＋「賽車數據誌」。
3. footer 的非官方 disclaimer（中英雙語）必須保留。
4. 配色避免對應到特定車隊（例如整套法拉利紅、麥拉倫橘 papaya）；現行「碳黑＋最速圈紫」自創系可演化但不可變成某車隊的視覺。

## 技術約束（mock 要能被套回，別破壞）

1. 全站 100% 靜態 server-rendered、零 client-side data fetch；所有內容必須在 DOM 裡（GEO/AEO 需求，crawler 與 AI 引擎要看得到全部表格）。
2. tabs 是 CSS-only（radio + :checked），results 頁用 <details>。可以改互動樣式，但不可引入需要 JS fetch 的元件；輕量裝飾性 JS 可接受。
3. 主題系統：:root[data-theme="…"] design tokens（--bg/--surface/--accent/--fg/--dim/--line 等），5 個暗色主題（carbon 預設/asphalt/midnight/gravel/silver），右上角圓點切換器。優化請「以 token 為單位」改，別寫死顏色。
4. 字體：Google Fonts 的 Chakra Petch（display/mono）＋ Archivo ＋ Noto Sans TC。可換，但必須是可自由使用的 webfont 且非 F1 官方字體。
5. 產出的 class 命名盡量沿用現有（.cal-card/.std-table/.podium-card/.tile/.idx-card/.pg-h1…），我們的 python generator 會保留邏輯、只套新皮。
6. 手機優先：表格已有 .tbl-scroll 橫向捲動 wrapper，寬表不可撐破版面。

## 希望優化的方向（依優先序）

1. **首頁 dashboard 的資訊層級**：「下一站＋台北時間」是全站最高頻需求，希望更有存在感（現在只是一條 chip）；倒數感、日期感可以更強。
2. **賽曆頁卡片**：22 張卡片略單調，已完賽/下一站/未來站的視覺區隔可以更清楚；session 時刻列（練習/排位/衝刺）的可掃讀性。
3. **積分榜/賽果表格**：數據表的可讀性與「計時螢幕」氛圍（P1-P3 的頒獎台感、積分領先者的強調、退賽 status 的處理）。
4. **文章頁排版**：長文（4000 字＋表格）的閱讀節奏、目錄/錨點導覽（可加，純 HTML anchor）。
5. **整體質感**：現在偏「乾淨但保守」，希望往「專業計時螢幕/賽道數據室」的方向加一點張力（速度感的斜體、賽道線意象的裝飾元素都可以，但要自繪、不可用官方素材）。

## 交付格式

- 每頁一個單檔 HTML mock（CSS inline，直接開能看），放 mocks/：home/calendar/standings/results/article。
- 一份 tokens.css（新的 design tokens，維持 :root[data-theme] 結構與 5 主題）。
- 一份 CHANGES.md：逐頁列「改了什麼、為什麼」，方便工程側套皮。
