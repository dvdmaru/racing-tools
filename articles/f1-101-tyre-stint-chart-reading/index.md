---
slug: f1-101-tyre-stint-chart-reading
type: "guide"
date: "2026-10-13"
topic_ref: "manual"
title: "OpenF1 輪胎分段圖：換色的地方，不一定對得上進站紀錄"
subtitle: "OpenF1 文件稱其為開放原始碼的非官方 F1 資料 API，且不隸屬 Formula 1 companies。把它 2026 新加坡正賽的 stint 紀錄和 pit 紀錄逐人對照，再拿 2025 墨西哥城正賽當對照場：OpenF1 的 Stints 欄位表記了圈段、配方原值與起始胎齡，但沒有磨耗或策略原因欄。"
lede: "OpenF1 把 2026 新加坡正賽切成 47 段 stint，22 位車手之間共有 25 個分段邊界，同一場的 pit 紀錄也剛好 25 筆；可是逐人對過，哈賈爾、阿隆索、斯托爾三人的邊界都在第 1 圈，pit 紀錄卻分別在第 33、35、26 圈。OpenF1 文件稱其為開放原始碼的非官方 API，且不隸屬 Formula 1 companies；這三筆為什麼對不上，OpenF1 文件與這批快照裡查無。"
---

# OpenF1 輪胎分段圖：換色的地方，不一定對得上進站紀錄

OpenF1 的 stint 表裡，哈賈爾在 2026 新加坡正賽的第一段只到第 1 圈為止，分段邊界就落在第 1 圈。

同一場的 pit 紀錄，哈賈爾的圈號是 33。

兩份紀錄都出自 OpenF1，指的卻是不同的圈。OpenF1 是開放原始碼的非官方 API，它的文件說自己不隸屬 Formula 1 companies。

只看圖，換色的位置看起來就是進站圈。要說哪位車手有幾筆 pit 紀錄、落在哪幾圈，得先把圖上的段界和 pit 紀錄逐人對過。

## 一個色塊畫的是 stint 紀錄的哪幾欄？

OpenF1 把 stint 定義為車手在一個 session 中持續駕駛的一段期間。每一段是資料表裡的一筆紀錄。

Stints 欄位表共有 8 欄。本站示意圖只用其中幾欄畫出一個色塊，這只是該筆紀錄的部分欄位。`lap_start` 是該段的起始圈，從 1 起算。`lap_end` 是該段最後完成的一圈。`compound` 是輪胎配方。`tyre_age_at_start` 是起始胎齡，定義留到後面一節。

這 8 欄裡沒有磨耗、抓地力、剩餘壽命或策略原因欄。所以「這一段為什麼在這一圈結束」，欄位表答不出來。

配方欄的值，本篇兩場快照裡都是 SOFT、MEDIUM、HARD 的原樣字串。文件沒有提供 C 編號的對照，圖上因此只寫原值。名稱和 C 編號的關係，在[F1 輪胎為什麼分軟中硬：同一款 C3，在澳洲站是硬胎，在日本站是軟胎](/articles/f1-101-tyres/)。

## 2026 新加坡的諾里斯與皮亞斯特里：分段邊界和 pit 紀錄逐圈相鄰

諾里斯在 2026 新加坡正賽的 pit 紀錄，圈號是 32。皮亞斯特里的 pit 紀錄，圈號是 33 和 41。

兩位車手 stint 紀錄的每個分段邊界，都能在 pit 紀錄裡找到緊鄰的圈號。到了這一步，才能拿段數去描述他們各有幾筆 pit 紀錄。這是核對之後的描述，不是從段數直接推出來的。

這裡只說兩個圈號「相鄰」。OpenF1 的 Pit 端點，文件說它提供車輛經過維修區的資料。可是 `lap_number` 欄只定義為 session 內的圈號，進站發生在那一圈的哪一刻，欄位沒有說。兩個數字也看不出車隊為什麼挑這一圈。

## 2026 新加坡這場：分段邊界和 pit 紀錄都是 25，逐人對卻有 3 位不同

這一場的 stint 表有 47 筆紀錄，涵蓋 22 位車手。47 減 22，得到 25 個分段邊界。這是本站自行計算的清點。同一場的 pit 紀錄也剛好 25 筆。

兩個總數相同，逐人對過卻有 3 位車手的邊界圈號和 pit 圈號不同。哈賈爾的邊界在第 1 圈，pit 紀錄在第 33 圈。阿隆索和斯托爾的邊界也在第 1 圈，pit 紀錄分別在第 35 圈和第 26 圈。其餘 19 位車手的邊界圈號和 pit 圈號相同。

這 3 筆為什麼對不上，OpenF1 文件與這批快照裡查無。

另一個資料源 Jolpica 的 API，也有一份 pit 圈號。它的 pitstops 端點在這一場同樣是 25 筆，圈號和 OpenF1 的 pit 紀錄逐筆相同。端點文件裡，每筆 pitstops 紀錄的欄位表沒有輪胎欄。本文只拿其中的 `lap` 欄核對圈號。哪一份紀錄反映實際換胎的圈數，這批資料判定不了。

因此「換色處就是 pit 紀錄的圈號」，在這一場有 3 個反例。單看圖，只能確定 stint 紀錄怎麼分段。下圖把四位車手並排。前兩列是諾里斯和皮亞斯特里。第三列是勞森，他的段界也和 pit 紀錄相鄰。最後一列是哈賈爾，段界和 pit 紀錄不相鄰。

<figure class="diagram">
<svg viewBox="0 0 420 392" role="img" aria-label="2026 新加坡正賽，OpenF1（開放原始碼的非官方 API，不隸屬 Formula 1 companies）stint 紀錄與 pit 紀錄對照：諾里斯、皮亞斯特里、勞森的分段邊界與 pit 圈相鄰；哈賈爾 stint 邊界在第 1 圈，pit 紀錄在第 33 圈，原因在 OpenF1 文件與這批快照裡查無。">
<title>輪胎分段與 pit 紀錄對照示意</title>
<desc>2026 新加坡正賽，OpenF1（開放原始碼的非官方 API，不隸屬 Formula 1 companies）stint 紀錄與 pit 紀錄對照：諾里斯、皮亞斯特里、勞森的分段邊界與 pit 圈相鄰；哈賈爾 stint 邊界在第 1 圈，pit 紀錄在第 33 圈，原因在 OpenF1 文件與這批快照裡查無。勞森第一段標的起始胎齡 3，是該段開始時那組胎已完成的圈數。色塊上的配方照 OpenF1 原值標示，欄位文件未提供 C 編號對照。</desc>
<rect class="d-surface d-line-s" x="4" y="4" width="412" height="384" rx="10"/>
<text class="d-fg" x="20" y="30" font-size="15">2026 新加坡正賽</text>
<text class="d-fg" x="20" y="62" font-size="14">諾里斯</text>
<text class="d-fg" x="400" y="62" font-size="14" text-anchor="end">pit 紀錄 第 32 圈</text>
<polygon class="d-accent d-line-s" points="198,68 214,68 206,78"/>
<rect class="d-surface d-line-s" x="20" y="80" width="186" height="22"/>
<rect class="d-line d-line-s" x="206" y="80" width="186" height="22"/>
<text class="d-fg" x="113" y="96" font-size="14" text-anchor="middle">SOFT</text>
<text class="d-fg" x="299" y="96" font-size="14" text-anchor="middle">MEDIUM</text>
<text class="d-fg" x="20" y="132" font-size="14">皮亞斯特里</text>
<text class="d-fg" x="400" y="132" font-size="14" text-anchor="end">pit 紀錄 第 33、41 圈</text>
<polygon class="d-accent d-line-s" points="192,138 208,138 200,148"/>
<polygon class="d-accent d-line-s" points="262,138 278,138 270,148"/>
<rect class="d-surface d-line-s" x="20" y="150" width="180" height="22"/>
<rect class="d-line d-line-s" x="200" y="150" width="70" height="22"/>
<rect class="d-surface d-line-s" x="270" y="150" width="122" height="22"/>
<text class="d-fg" x="110" y="166" font-size="14" text-anchor="middle">SOFT</text>
<text class="d-fg" x="235" y="166" font-size="14" text-anchor="middle">MEDIUM</text>
<text class="d-fg" x="331" y="166" font-size="14" text-anchor="middle">SOFT</text>
<text class="d-fg" x="20" y="202" font-size="14">勞森</text>
<text class="d-fg" x="400" y="202" font-size="14" text-anchor="end">pit 紀錄 第 31 圈</text>
<polygon class="d-accent d-line-s" points="192,208 208,208 200,218"/>
<rect class="d-surface d-line-s" x="20" y="220" width="180" height="22"/>
<rect class="d-line d-line-s" x="200" y="220" width="192" height="22"/>
<text class="d-fg" x="110" y="236" font-size="14" text-anchor="middle">SOFT</text>
<text class="d-fg" x="296" y="236" font-size="14" text-anchor="middle">MEDIUM</text>
<text class="d-fg" x="20" y="262" font-size="14">起始胎齡 3（已完成圈數）</text>
<text class="d-fg" x="20" y="302" font-size="14">哈賈爾</text>
<rect class="d-surface d-line-s" x="20" y="310" width="10" height="22"/>
<rect class="d-line d-line-s" x="30" y="310" width="362" height="22"/>
<text class="d-fg" x="211" y="326" font-size="14" text-anchor="middle">SOFT</text>
<line class="d-fg d-fg-s" x1="30" y1="332" x2="30" y2="344" stroke-width="2"/>
<polygon class="d-accent d-line-s" points="198,342 214,342 206,332"/>
<text class="d-fg" x="20" y="362" font-size="14">stint 邊界 第 1 圈</text>
<text class="d-fg" x="196" y="362" font-size="14">pit 紀錄 第 33 圈</text>
<text class="d-fg" x="20" y="382" font-size="14">兩者不同</text>
</svg>
<figcaption>圖：資料為 OpenF1（開放原始碼的非官方 API，不隸屬 Formula 1 companies）2026 新加坡正賽的 stint 與 pit 快照，2026-10-13 取得。色塊照 stint 紀錄原樣畫，交替填色只用來分段，三角形是 pit 紀錄的圈號；哈賈爾的 stint 邊界在第 1 圈、pit 紀錄在第 33 圈，原因在 OpenF1 文件與這批快照裡查無。本站依快照自行整理的示意，非依比例。</figcaption>
</figure>

## 起始胎齡這一欄記的是什麼？

圖裡勞森的第一段是 SOFT，第 1 到 31 圈，`tyre_age_at_start` 記 3。第二段是 MEDIUM，第 32 到 62 圈，記 0。

OpenF1 文件的定義是：該段開始時，輪胎已完成的圈數。所以 3 的意思是，OpenF1 記錄勞森的第一段開始時，那組胎已完成 3 圈。

這個欄位只記圈數，所以 3 不是磨耗量。那 3 圈在哪裡完成，欄位沒有說。輪胎還剩多少性能，欄位也沒有說。

輪胎套數的歸還規則，在[F1 輪胎歸還表：配到的乾胎，週末會被分批收走](/articles/f1-101-tyre-set-returns/)。用逐圈資料自己定義胎齡的另一種算法，在[諾里斯這 10 圈四人之中最快，名次卻只有第 7](/articles/f1-101-race-pace-reading/)，它的口徑和 OpenF1 這一欄不同。

## 色塊沒畫到終點

2026 新加坡正賽的 stint 表裡，22 位車手中有 12 位的最後一段 `lap_end` 不是 62，色塊比較短。

這 12 位車手在 Jolpica 成績表的狀態欄，有 8 位是 `Lapped`，4 位是 `Retired`。22 位車手的最後一段 `lap_end`，都和 Jolpica 成績表的圈數欄相同。

所以色塊比別人短，單看圖分不出是被套圈，還是退賽。要另看成績表的狀態欄。

## 換一場看：2025 墨西哥城的 27 個分段邊界與 pit 紀錄逐人對上

對照場是 2025 墨西哥城正賽。OpenF1 的 stint 表有 47 筆紀錄，涵蓋 20 位車手。47 減 20，得到 27 個分段邊界（本站自行計算）。pit 紀錄是 27 筆。逐人對過，邊界圈號和 pit 圈號沒有任何一位不同。Jolpica 的 pitstops 端點在這一場也是 27 筆，圈號與 OpenF1 逐筆相同。

塞恩斯在這一場有四段：MEDIUM 第 1 到 17 圈，SOFT 第 18 到 46 圈，SOFT 第 47 到 56 圈，SOFT 第 57 到 67 圈。他的 pit 紀錄有三筆，圈號是 17、46、56，正好是前三段的最後完成圈。

後三段的配方欄都是 SOFT。如果一張圖只按配方上色，這三段會連成一整塊同色，段界只能從分段本身找。

新加坡 22 位裡有 3 位對不上，墨西哥城 20 位裡沒有。這是兩場的結果。新加坡的 3 位不能升格成「OpenF1 常出錯」，墨西哥城的 0 位也不能升格成「通常可靠」。手上這一場的段界，要自己和 pit 紀錄逐人對過，才能寫哪位車手有幾筆 pit 紀錄。

## 常見問題

### stint 圖上的一段代表什麼？

OpenF1 把 stint 定義為車手在一個 session 中持續駕駛的一段期間（OpenF1 文件稱其為開放原始碼的非官方 API，且不隸屬 Formula 1 companies）。本站示意圖用該筆紀錄的起始圈、最後完成圈、配方原值與起始胎齡（該段開始時已完成的圈數）畫一個色塊，這只是部分欄位。本篇兩場快照（2026 新加坡、2025 墨西哥城正賽）的配方值以 SOFT、MEDIUM、HARD 原樣呈現，欄位文件未提供 C 編號對照；名稱怎麼對應，看[F1 輪胎為什麼分軟中硬：同一款 C3，在澳洲站是硬胎，在日本站是軟胎](/articles/f1-101-tyres/)。

### stint 圖的段數能直接換算成進站次數嗎？

不能直接換算。2026 新加坡這場，分段邊界數和 pit 紀錄數相同，都是 25，但有 3 位車手的邊界圈和 pit 圈不同，要逐人對 pit 紀錄。這 3 筆的原因，在 OpenF1 文件與這批快照裡查無。

### 起始胎齡代表輪胎磨耗了嗎？

不代表。OpenF1 把它定義為該段開始時已完成的圈數。這個欄位沒有說明那些圈在哪裡完成或剩餘性能，OpenF1 的 Stints 欄位表也沒有磨耗、抓地力或剩餘壽命欄。

### OpenF1 是官方資料嗎？

OpenF1 文件稱其為開放原始碼的非官方 API，且不隸屬 Formula 1 companies。

## 接下來看什麼

- [F1 輪胎為什麼分軟中硬：同一款 C3，在澳洲站是硬胎，在日本站是軟胎](/articles/f1-101-tyres/)：配方名稱與規則
- [先進站的人為什麼有時反而贏：F1 進站策略的 undercut 與 overcut](/articles/f1-101-pit-stop-strategy/)：進站的兩段時間與 undercut
- [F1 輪胎歸還表：配到的乾胎，週末會被分批收走](/articles/f1-101-tyre-set-returns/)：歸還套數
- [新加坡站第 39 圈虛擬安全車期間，勒克萊爾進站，漢米爾頓則留在場上](/articles/f1-2026-r17-singapore-ferrari-strategy-ledger/)：同一場的實戰

## 資料來源

一手來源：本文未引用 FIA 規章條文。

資料服務文件：

- [OpenF1 API 文件](https://openf1.org/docs/)：Introduction 自述為 unofficial project、not associated with the Formula 1 companies；Stints 與 Pit 兩節的欄位定義
- [OpenF1 sessions，2026 新加坡正賽（session_key=11388）](https://api.openf1.org/v1/sessions?session_key=11388)
- [OpenF1 stints，2026 新加坡正賽](https://api.openf1.org/v1/stints?session_key=11388)
- [OpenF1 pit，2026 新加坡正賽](https://api.openf1.org/v1/pit?session_key=11388)
- [OpenF1 sessions，2025 墨西哥城正賽（session_key=9877）](https://api.openf1.org/v1/sessions?session_key=9877)
- [OpenF1 stints，2025 墨西哥城正賽](https://api.openf1.org/v1/stints?session_key=9877)
- [OpenF1 pit，2025 墨西哥城正賽](https://api.openf1.org/v1/pit?session_key=9877)
- [Jolpica pitstops 端點說明](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/pitstops.md)
- [Jolpica 2026 年第 17 站 pitstops](https://api.jolpi.ca/ergast/f1/2026/17/pitstops.json)
- [Jolpica 2026 年第 17 站成績](https://api.jolpi.ca/ergast/f1/2026/17/results.json)
- [Jolpica pitstops，2025 墨西哥城正賽](https://api.jolpi.ca/ergast/f1/2025/20/pitstops.json)

二手來源：本文未使用媒體報導作為事實依據。

查證日：2026-10-13。限制：快照於 2026-10-13 取得，只涵蓋 2026 新加坡正賽（session 11388）與 2025 墨西哥城正賽（session 9877）兩場，比例與反例都只限這兩場。47 減 22、47 減 20 的分段邊界數，以及 3 位對不上、其餘 19 位相同、12 位最後一段不是第 62 圈等數字，是本站依快照自行計算。「查無」只指 OpenF1 文件與這批快照；OpenF1 與 Jolpica 各自的資料上游，文件與快照沒有說明。
