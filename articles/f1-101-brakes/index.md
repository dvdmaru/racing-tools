---
slug: "f1-101-brakes"
type: "guide"
date: "2026-09-25"
topic_ref: "manual"
title: "F1 煞車怎麼運作：攝氏 1,000 度的高溫，還有 2026 年分擔更多減速的後輪馬達"
subtitle: "煞車盤的工作窗口通常只有攝氏 350 到 550 度，重煞時卻能衝破 1,000 度。2026 年後輪煞車沒有被拿掉，而是讓電動馬達分擔更多減速，煞車力道仍以車手踩出的壓力為基準。"
lede: "車手踩同一根踏板，前輪由液壓煞車減速，後輪則協調機械煞車與馬達回收。後輪電控停用時，踏板相連的主缸仍須能提供液壓；F1 也禁止防鎖死系統（ABS），車手得自己掌握鎖死的邊界。"
---

# F1 煞車怎麼運作：攝氏 1,000 度的高溫，還有 2026 年分擔更多減速的後輪馬達

Brembo 的 2026 年蒙札站模擬裡，賽車以 318 km/h 衝向 1 號彎，3.22 秒後只剩 87 km/h。這幾秒鐘既要減速，也要處理煞車盤上的高溫；後輪還得把一部分動能交給馬達回收。

車手踩的是同一根踏板，前輪液壓煞車、後輪機械煞車與能量回收卻各有分工。要看懂 F1 煞車，先跟著踏板的力量走，再看系統如何把熱散掉。本文引用的各站減速數字是供應商 Brembo 的模擬或預估。

## 蒙札 1 號彎的踏板負載，模擬達 111 公斤

Brembo 是替 F1 車隊供應煞車系統的義大利廠商。這次模擬還列出 153 公尺的煞車距離、111 公斤踏板負載，以及 3.8 g 的最大減速。g 是重力加速度的倍數，3.8 g 描述的是減速度。這些是賽前模擬，並非車手當天的實測。

腳下的力量要經過液壓系統，才會送到車輪。

## 一根踏板推兩個主缸，前後油路各自獨立

一輛 F1 賽車只准有一套煞車系統（動力單元除外）。車手的腳下只有一根踏板，踏板推動兩個主缸：一個主缸管兩個前輪的油路，另一個管兩個後輪的油路（C11.1.1）。

主缸是把腳踩出來的力量轉成油壓的零件。兩條油路各自獨立，設計成任一條失效時，踏板仍然能操作另一條的煞車。

車手也要自己掌握鎖死的邊界。規章（C11.4.1）禁止任何設計成在車手踩踏板時防止車輪鎖死的煞車系統，也就是 ABS。防鎖死系統是一種在車輪快要鎖住時自動放鬆油壓的裝置，F1 不准裝。另一條（C11.4.2）規定，煞車系統不得設計成讓卡鉗壓力高於車手踩踏板產生的壓力，後輪煞車控制系統是例外，另有壓力上限。

還有一條跟調整有關的規定（C11.1.4）：煞車系統在賽道上的任何變更或調節，必須由車手直接身體操作，或由後輪煞車控制系統完成，不得預先設定。

卡鉗的材料與活塞數等零件細節，規章也有規定，而且卡鉗、煞車盤等主要零件的設計規格開放給所有車隊（C11.7）。

## 後輪由馬達與機械煞車一起減速

2026 年能量回收分擔更多後輪減速，機械煞車仍須獨立達到規章要求。

C11.1.1 的原文是，在沒有動力單元或 MGU-K 協助的情況下，每個後輪的煞車系統必須提供至少 2500 牛頓米的煞車扭力，而且這個扭力要在卡鉗壓力不超過 150 barG 的條件下達到。牛頓米是扭力的單位，barG 是壓力的單位。Brembo 的 2026 規則頁也寫同樣的 2500 Nm 與 150 bar。換句話說，馬達幫不上忙的時候，機械煞車還是要夠用。

那馬達到底做什麼？MGU-K 是動力單元裡的電動馬達，煞車時它反過來當發電機，把減速的動能收回電池，過程叫能量回收。後輪由馬達與機械煞車分擔減速，不是 2026 年才開始，F1 官方 2014 年的技術解說就在講這套做法（見下文）。2026 年變的是量：Brembo 說，MGU-K 的功率從 120 kW 提高到 350 kW，回收能力提高近三倍，讓後輪減速更多。動力單元的整體分工，可以看[F1 動力單元是什麼](/articles/f1-101-power-unit/)；新規則的整體改動，看[2026 新規則指南](/articles/f1-2026-rules-guide/)。

要讓馬達的減速和機械煞車湊在一起，靠的是後輪的「電動控制系統」，也就是所謂的線傳煞車（brake-by-wire，簡稱 BBW）。C11.6 的規定是，後輪煞車壓力可以由電動控制系統提供，但不能超過車手同時在後主缸產生壓力的 1.2 倍；系統由電子控制單元控制；電控停用時，連著踏板的液壓主缸仍然能把壓力送到後輪。

<figure class="diagram">
<svg viewBox="0 0 420 530" role="img" aria-label="F1 煞車分工示意：一根踏板推兩個主缸，前主缸直接連前輪煞車，後主缸經電控系統連後輪煞車，後輪的動能再由 MGU-K 回收進電池">
<title>F1 煞車與能量回收分工示意</title>
<desc>最上方是煞車踏板，往下分成兩個主缸。左邊的前主缸用踏板壓力直接連到前輪煞車，全程只有液壓。右邊的後主缸經過後輪電控系統再連到後輪煞車，電控系統送出的壓力最多是車手同時在後主缸產生壓力的 1.2 倍。後輪煞車下方是 MGU-K 馬達，煞車時把後輪的動能回收，再向左回充給電池。前輪只有機械煞車，後輪則是機械煞車加馬達回收。圖中沒有溫度或扭力數字。</desc>
<rect class="d-surface d-line-s" x="135" y="20" width="150" height="44" rx="10"/>
<text class="d-fg" x="210" y="48" font-size="17" text-anchor="middle">煞車踏板</text>
<line class="d-dim-s" x1="155" y1="66" x2="155" y2="96" stroke-width="2"/>
<polygon class="d-dim" points="147,96 163,96 155,110"/>
<line class="d-dim-s" x1="265" y1="66" x2="265" y2="96" stroke-width="2"/>
<polygon class="d-dim" points="257,96 273,96 265,110"/>
<rect class="d-surface d-line-s" x="20" y="112" width="170" height="52" rx="10"/>
<text class="d-fg" x="105" y="144" font-size="17" text-anchor="middle">前主缸</text>
<rect class="d-surface d-line-s" x="230" y="112" width="170" height="52" rx="10"/>
<text class="d-fg" x="315" y="144" font-size="17" text-anchor="middle">後主缸</text>
<line class="d-dim-s" x1="105" y1="166" x2="105" y2="296" stroke-width="2"/>
<polygon class="d-dim" points="97,296 113,296 105,310"/>
<text class="d-fg" x="118" y="240" font-size="14">踏板壓力直達</text>
<line class="d-dim-s" x1="315" y1="166" x2="315" y2="196" stroke-width="2"/>
<polygon class="d-dim" points="307,196 323,196 315,210"/>
<rect class="d-surface d-line-s" x="230" y="212" width="170" height="52" rx="10"/>
<text class="d-fg" x="315" y="244" font-size="17" text-anchor="middle">後輪電控系統</text>
<line class="d-dim-s" x1="315" y1="266" x2="315" y2="296" stroke-width="2"/>
<polygon class="d-dim" points="307,296 323,296 315,310"/>
<text class="d-fg" x="304" y="284" font-size="14" text-anchor="end">最多為車手</text>
<text class="d-fg" x="304" y="302" font-size="14" text-anchor="end">後主缸壓力的 1.2 倍</text>
<rect class="d-surface d-line-s" x="20" y="312" width="170" height="52" rx="10"/>
<text class="d-fg" x="105" y="344" font-size="17" text-anchor="middle">前輪煞車</text>
<rect class="d-surface d-line-s" x="230" y="312" width="170" height="52" rx="10"/>
<text class="d-fg" x="315" y="344" font-size="17" text-anchor="middle">後輪煞車</text>
<line class="d-dim-s" x1="315" y1="366" x2="315" y2="380" stroke-width="2"/>
<polygon class="d-dim" points="307,380 323,380 315,394"/>
<text class="d-fg" x="326" y="386" font-size="14">回收動能</text>
<rect class="d-surface d-line-s" x="230" y="396" width="170" height="52" rx="10"/>
<text class="d-fg" x="315" y="428" font-size="17" text-anchor="middle">MGU-K 馬達</text>
<rect class="d-surface d-line-s" x="20" y="396" width="170" height="52" rx="10"/>
<text class="d-fg" x="105" y="428" font-size="17" text-anchor="middle">電池</text>
<line class="d-dim-s" x1="228" y1="422" x2="206" y2="422" stroke-width="2"/>
<polygon class="d-dim" points="206,415 206,429 192,422"/>
<text class="d-fg" x="210" y="412" font-size="14" text-anchor="middle">回充</text>
<text class="d-fg" x="30" y="486" font-size="14">後輪：液壓煞車加馬達回收</text>
<text class="d-fg" x="30" y="508" font-size="14">前輪：只有液壓煞車</text>
</svg>
<figcaption>圖：F1 前後輪煞車與能量回收的分工，依 FIA 2026 技術規章 C11 與 Brembo 的說明繪製。本站示意圖，非依比例、非實測。</figcaption>
</figure>

前輪的路徑是踏板、主缸、液壓煞車。後輪則多了電控協調與馬達回收；電控停用時，後主缸仍須能將踏板產生的壓力送到後輪。

F1 官方 2014 年一篇技術解說，講的是同一套後輪線傳煞車的原理：電控單元依車手要求的煞車平衡，以及馬達回收造成的減速量，減少送到後輪的油壓。這篇文章是 2014 年的，不是 2026 年專文，但基本概念一樣。

## 碳碳盤重煞可超過攝氏 1,000 度，冷卻靠氣流與盤孔

Brembo 說，2026 年的碟盤仍用碳碳複合材料（carbon-carbon，C/C），卡鉗用含少量鋰的鋁材。規章 C15.4.c 允許碳碳作摩擦材料，也允許陶瓷基複合材料，並未要求煞車盤一定用碳纖維。

碳煞車需要溫度，也怕過熱。Brembo 列的正常工作窗口通常是攝氏 350 到 550 度，重煞時碳碳盤卻可超過攝氏 1,000 度；F1 官方 2021 年技術文章也提過這個高溫。工作窗口與瞬間峰值是不同定義。

盤上的孔用來冷卻，避免高溫造成煞車力衰退（fading）。Brembo 對往年的回顧列出：2012 年每片 600 孔，2017 到 2018 年起達 1,260 孔，2020 年前盤另有 1,470 孔、7 排的高冷卻版本。這是歷史演變，不能拿來當 2026 年孔數。

冷卻與保溫也受規章限制。C11.5 禁用液體冷卻煞車；C10.8.3.d 禁止以加熱完整車輪、輪轂或煞車為目的或有此效果的裝置、系統或程序，替熱煞車保溫也在禁令內，只有合規輪胎保溫毯與開車本身例外。

Brembo 說，感測器讓車隊即時掌握碟盤與來令片溫度、煞車壓力、主缸行程，協助車手管理溫度與平衡。資料傳回維修區的方式，見[車隊無線電與遙測](/articles/f1-101-team-radio-telemetry/)。

## 車手能調前後煞車比例，仍要自己處理鎖死

煞車平衡（brake balance／brake bias）是前後輪的煞車力分配。F1 官方詞彙表說，車手開車途中就能調整，例如往後移，以避免前輪鎖死。這種調整並沒有替賽車加上 ABS。

F1 官方曾以 2021 年賓士（Mercedes）方向盤解釋：正常行駛時前軸約占 52 到 53%，背面的 brake magic 按鍵則據信可切到前軸約 86.5%。後者用於暖胎圈或安全車帶領期間，並非比賽設定。這是當年單一車隊的例子，2026 年介面與可調範圍未有可引用的官方資料。

煞車力往前或往後分，會連到車手感受到的[轉向不足與轉向過度](/articles/f1-101-car-balance/)。對車隊而言，能煞多重之外，還要看整圈承受多久。

## 巴庫評為 5 分，單一重煞數字卻和摩納哥相近

Brembo 替每一站的煞車難度打 1 到 5 分。同樣是 2026 年的模擬，巴庫和摩納哥的最難一彎，力道其實差不多：

| 站別與彎 | 車速變化 | 煞車距離 | 踏板負載 | 最大減速 |
| --- | --- | --- | --- | --- |
| 蒙札 1 號彎 | 318 降到 87 km/h（3.22 秒） | 153 公尺 | 111 公斤 | 3.8 g |
| 巴庫 1 號彎 | 313 降到 140 km/h（2.13 秒） | 123 公尺 | 115 公斤 | 3.9 g |
| 摩納哥 Sainte Devote 彎 | 276 降到 132 km/h（1.67 秒） | 91 公尺 | 114 公斤 | 4 g |

三個彎，踏板負載都落在 111 到 115 公斤之間，減速都在 3.8 到 4 g 之間。可是 Brembo 給巴庫的難度是滿分 5 分，摩納哥只有 2 分。

整圈資料提供另一個比較角度。巴庫每圈煞車 10 次，合計 18.5 秒；其中只有 2 次屬於 Hard 等級，但總量仍讓它拿到 5 分。摩納哥每圈煞 9 次、約 16.3 秒，占比賽時間的 23%，其中 2 次是 High 等級、3 次是 Medium、4 次是 Light，評分是 2。蒙札的評分是 3，每圈煞 5 次，合計不到 8.5 秒。

所以煞車有多難，不只看最猛的那一彎有多猛，也看整圈要煞幾次、每次煞多久。

## Brembo 的兩個跨年對照，2026 年踩得較輕、距離較長

Brembo 在蒙札站說明中表示，2026 年單座車的特性，讓車手與煞車所需的力量較低。這是對整車特性的說明，不能把變化全算到能量回收。

Brembo 把 2025 年與 2026 年同一個彎的模擬值放在一起比。下表的 2026 蒙札數值是 Brembo 寫的預估值（expected）：

| 站別與彎 | 年份 | 最大減速 | 踏板負載 | 煞車距離 | 煞車時間 |
| --- | --- | --- | --- | --- | --- |
| 蒙札 4 號彎 | 2025 | 4.5 g | 159 公斤 | 107 公尺 | 2.02 秒 |
| 蒙札 4 號彎 | 2026 | 約 3.7 g | 約 108 公斤 | 121 公尺 | 2.29 秒 |
| 摩納哥隧道後的減速彎 | 2025 | 4.5 g | 145 公斤 | 91 公尺 | 2.06 秒 |
| 摩納哥隧道後的減速彎 | 2026 | 3 g | 86 公斤 | 136 公尺 | 2.87 秒 |

Brembo 特別註明，摩納哥那個彎的減速幅度和去年幾乎一樣，煞車距離卻從 91 公尺拉長到 136 公尺。蒙札 4 號彎的減速幅度甚至更小，煞車距離也一樣從 107 公尺拉長到 121 公尺。

也就是說，至少在 Brembo 比較的這兩個彎，2026 年車手踩得比較輕，煞車距離與時間反而變長。煞車點與超車的關係，可以看[F1 為什麼很難超車](/articles/f1-101-overtaking/)。

## 後盤仍有尺寸、材料與作業限制

規章對煞車盤的尺寸畫了很細的界線（C11.3）：每個輪子只有一片煞車盤，最大厚度 34 mm；前盤直徑在 325 到 345 mm 之間，後盤在 260 到 280 mm 之間；冷卻孔的最小直徑是 2.5 mm；每輪一或兩對煞車皮。

Brembo 對 2026 年的變動有簡潔的整理：前盤的最大直徑放大 15 mm；後盤的最大直徑不變，厚度上限由 2025 年的 32 mm 增加到 34 mm；冷卻孔最小直徑由 3 mm 降到 2.5 mm；後盤最小直徑是 260 mm。2025 年的對照值，這次只有 Brembo 一個來源。

後盤變厚，也會增加重量。Brembo 說車隊會設法降低重量影響，也在考慮同一套後盤連用兩場比賽的可能性。這是「考慮」，不是已經確定的做法。

至於一套盤能用多久，Brembo 對前一代規章的說法是，碟盤的磨耗很低，多數情況一套可以用兩個比賽週末。2026 年的實際數字，這次沒有查到。

封閉管制（parc fermé）期間，煞車的摩擦材料可以取下、量測、重新裝上；起跑程序等幾種程序被暫停時，在恢復之前也可以更換前後煞車周圍的風道（B5.14.4）。封閉管制的完整規則，看[封閉管制是什麼](/articles/f1-101-parc-ferme/)。

## 漢米爾頓在西班牙站說踏板「踩下去一格」，原因連車手自己都說不知道

前面講的都是煞車正常運作的樣子。踏板反應出問題時是什麼樣子，可以看漢米爾頓的例子。

2026 年西班牙大獎賽在馬德里的 Madring 賽道舉行，漢米爾頓（Lewis Hamilton）跑了 7 圈就進站退賽。F1 官方網站刊出他事後的說明，大意是：在 5 號彎踩煞車，車子開始減速，接著踏板「踩下去一格」，車子突然沒有平常那麼快的減速。之後踏板回來了，幾個彎以後，踏板又變長。

他也說了一句：「我真的不知道這是從哪裡來的。」

官方報導沒有給出技術解釋，成因沒有查到證實，所以不能說這是線傳煞車的故障，也不能說是過熱。能確定的只有他描述的症狀：車手踩下去的位置，和車子減速的程度，突然對不上了。

## 常見問題

### F1 賽車有防鎖死系統（ABS）嗎？

沒有。FIA 規章明文禁止任何設計成在車手踩踏板時防止車輪鎖死的煞車系統，也禁止把煞車系統設計成讓卡鉗壓力高於車手踩踏板所產生的壓力，唯一的例外是後輪煞車控制系統。

### 規章規定 F1 煞車盤一定要用碳纖維嗎？

沒有這樣規定。規章的材料條款只寫碳碳複合材料可以用於摩擦材料，同一條也允許陶瓷基複合材料。Brembo 說，2026 年的碟盤仍然是碳碳材質。

### 2026 年後輪煞車被拿掉了嗎？

沒有。規章要求在沒有動力單元或 MGU-K 協助的情況下，每個後輪仍要能提供至少 2500 牛頓米的煞車扭力。後輪煞車壓力可以由電動控制系統提供，但不能超過車手同時在後主缸產生壓力的 1.2 倍。

### F1 煞車盤能有多熱？

Brembo 說，碳煞車系統正常的工作溫度窗口通常在攝氏 350 到 550 度之間，重煞時碳碳盤可以超過攝氏 1,000 度。

## 接下來看什麼

- [F1 動力單元是什麼：引擎、馬達與電池如何合起來推動賽車](/articles/f1-101-power-unit/)
- [轉向不足與轉向過度：車手嘴裡的『車頭推』和『車尾滑』是什麼意思](/articles/f1-101-car-balance/)
- [F1 為什麼很難超車：髒空氣、煞車點，以及 2026 年新增的幫手](/articles/f1-101-overtaking/)

## 資料來源

一手來源（FIA 規章與官方）：

- [FIA，《2026 Formula 1 Regulations, Section C Technical, Issue 20》（2026-08-05）](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_c_technical_-_iss_20_-_2026-08-05.pdf) （C10.8.3.d 加熱禁令、C11.1 至 C11.7 煞車系統、C15.4.c 摩擦材料）
- [FIA，《2026 Formula 1 Regulations, Section B Sporting, Issue 08》（2026-08-05）](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_08_-_2026-08-05_7.pdf) （B5.14.4 暫停程序、附則 B2 封閉管制下的煞車作業）
- [F1 官方，《Hamilton explains brake issues that caused Spanish GP retirement》](https://www.formula1.com/en/latest/article/had-the-car-to-fight-for-a-win-hamilton-explains-brake-issues-that-caused-spanish-gp-retirement.3NzWcY1clsL8KQPyc9ONqm) （漢米爾頓對西班牙站煞車問題的自述）
- [F1 官方，《F1 glossary A-E》](https://www.formula1.com/en/latest/article/f1-glossary-a-e.1MFONigMlQSbSQtpP7YCy2) （煞車平衡定義）
- [F1 官方，《Technical analysis: brake-by-wire systems explained》（2014）](https://www.formula1.com/en/latest/article/technical-analysis-brake-by-wire-systems-explained.1XQiBCFqA6WYZwLmb3JLxi) （前後煞車力偏置、後輪電控單元減壓）
- [F1 官方，《Tech Tuesday: what is the magic brake setting》（2021）](https://www.formula1.com/en/latest/article/tech-tuesday-what-is-the-magic-brake-setting-that-cost-hamilton-in-baku-and.79Mw4XSrxksy7jen3CE8FX) （賓士方向盤煞車平衡選擇器、brake magic、碳盤超過攝氏 1,000 度）
- [F1 官方，《Explained: The new key terms for Formula 1's new-for-2026 rules》](https://www.formula1.com/en/latest/article/explained-the-new-key-terms-for-formula-1s-new-for-2026-rules.3T5BU6TC9quGcIpGzoWkY0) （回充時機）

二手來源（供應商說明，數字為 Brembo 自己的模擬或預估）：

- [Brembo，《Formula 1 2026 rules》](https://www.brembo.com/en/motorsport/formula1/f1-rules-2026) （2026 年煞車尺寸變動、MGU-K 功率、碳碳盤材質、後盤連用兩場的可能）
- [Brembo，《Ventilation holes》](https://www.brembo.com/en/motorsport/formula1/ventilation-holes) （工作溫度窗口、冷卻孔演變）
- [Brembo，《Formula 1》](https://www.brembo.com/en/motorsport/formula1) （感測器監看、前一代規章下的碟盤壽命）
- [Brembo，《Monza 2026 Brake Facts》](https://www.brembo.com/en/motorsport/formula1/2026/facts-monza-2026) （蒙札 1 號彎與 4 號彎模擬）
- [Brembo，《Baku 2026 Brake Facts》](https://www.brembo.com/en/motorsport/formula1/2026/facts-baku-2026) （巴庫難度 5 分與 1 號彎模擬）
- [Brembo，《Monaco 2026 Brake Facts》](https://www.brembo.com/en/motorsport/formula1/2026/facts-monaco-2026) （摩納哥難度 2 分、Sainte Devote 彎與隧道後減速彎模擬）

查證日：2026-09-25。限制：Brembo 各站的減速、踏板負載與煞車距離都是模擬或預估，不含煞車盤溫度；2026 年煞車平衡的調整範圍與方向盤介面、一個週末用幾套盤、後輪線傳煞車的手感，都沒有查到官方說法；漢米爾頓在西班牙站的煞車問題成因尚未證實，文中只寫他自己描述的症狀。
