---
slug: f1-101-active-aero
type: "guide"
date: "2026-09-26"
topic_ref: "manual"
title: "F1 主動空力：翼片只有兩個位置，被通知才能用，低抓地時只准前翼動"
subtitle: "官方入門文寫新系統「所有車、所有時間都可用」，規章的條件窄得多：要被通知已啟用、翼片要完全在啟動區內，宣告低抓地條件後只准前翼部分啟用。這篇把 2026 年主動空力的條文拆開來讀。"
lede: "formula1.com 說 2026 年的主動空力所有車、所有時間都可用，可是規章裡有一串條件：只有兩個固定位置、要被通知已啟用、翼片要完全位於啟動區內，低抓地時還只准前翼動。看轉播時，這串條件能解釋為什麼直線上不是每輛車都放平翼片。"
---

# F1 主動空力：翼片只有兩個位置，被通知才能用，低抓地時只准前翼動

formula1.com 的 2026 年空力入門文有一句話：新系統「所有車、所有時間都可以使用」（原文：The new system is useable by all of the cars, all of the time）。

這句話是拿來對比 DRS 的。DRS 從 2011 年起就有，只有落後前車 1 秒內的追擊車，才能在指定直線上用。

讀起來像是每輛車、每條直線，翼片想放平就放平。

規章寫得窄很多。車手要先被通知「已啟用」，翼片要完全位於啟動區內，賽事總監宣告低抓地條件之後，還只准前翼動。

這篇把條文一條一條拆開，講 2026 年的主動空力怎麼動、什麼時候才能動。條文取自 2026-08-05 版的 Section B 與 Section C。

## 動的是前翼與後翼襟翼，Straight Mode 就是攻角變小

規章把會動的車身叫「車手可調車身」（Driver Adjustable Bodywork）。內容包含兩項：前翼元件的攻角調整，和後翼襟翼的攻角調整，兩者都由 FIA 標準 ECU 控制（B7.1.1 a）。Section C 談到可動車身時，也只列這兩處（C3.10.10、C3.11.6）。

所以會動的不只後翼。前翼也動。攻角是什麼，見[一輛 F1 賽車由什麼組成：從車鼻到尾翼，一張零件地圖](/articles/f1-101-car-anatomy/)。

翼片有兩個位置，分別叫 Corner Mode 與 Straight Mode。Straight Mode 的位置，攻角比 Corner Mode 小。前翼是主翼片與（或）副翼片攻角變小，後翼是襟翼攻角變小（C3.10.10 n；C3.11.6 c）。

規章只寫「攻角變小」，沒有寫角度數字。

formula1.com 用百葉窗來比喻：葉片「關閉」時提供下壓力，也帶來大量阻力；「打開」時，阻力與下壓力都減少。

這是新手最常漏掉的一半。Straight Mode 減的不只是阻力，下壓力也一起少了。至於實際差多少，規章與官方頁都沒有數字。下壓力本身的原理見[F1 賽車真的能倒著開在天花板上嗎？下壓力讓車越快越黏地](/articles/f1-101-downforce/)。

前翼為什麼也要動？formula1.com 的解釋是：更好地調整車身姿態、提供更多穩定性，與後翼的動作互相配合。文中還提到，車隊本來就常在車庫與進站時手動調前翼來平衡車子。這是官方的說法，規章沒有寫理由。

規章對整個空氣動力章節（C3）寫下的首要目標，是促進近距離競爭：減少一輛車跟在另一輛後面時的空力性能損失（C3.2.1 a）。這是整章的目標，不是專指主動空力。

名稱也有一段歷史。據 RaceFans 2025-12-17 報導，F1 簡化了 2026 年新技術的對外用語，兩個狀態改稱 Corner 與 Straight 模式，原本的 Manual Override Mode 改稱 Overtake Mode。Overtake 是動力單元額外電力的規則，另一套系統，見[F1 為什麼很難超車：髒空氣，以及 2026 年新增的幫手](/articles/f1-101-overtaking/)。

## 只有兩個位置，沒有「開一半」

規章的寫法是：除了調整系統失效，或兩個位置之間的切換過程，前翼主副翼片與後翼襟翼只能待在那兩個位置（C3.10.10 t；C3.11.6 h）。例外只有這兩種。

位置也不是車隊自己調的。前翼與後翼襟翼的可調部分，都由 FIA 標準 ECU 控制，連致動器都算在內（C8.2.1）。所以賽道上不存在「開一半」這種檔位。

幅度也被固定住：每次切到 Straight Mode，攻角減小的量都一樣（除非被實體擋塊限制住），用完之後翼片要回到原來的 Corner Mode 位置（C3.10.10；C3.11.6 c）。

硬體上也有限制：前翼由最多兩個致動器驅動，後翼襟翼由單一致動器驅動，每個致動器都配位置感測器，兩處都有實體擋塊，防止翼片轉出規定範圍（C3.10.10；C3.11.6）。

## 前翼單獨動叫部分啟用，前後翼都動才叫完全啟用

規章用兩個翼片各在哪個位置，定義了三種狀態（B7.1.1 b、c、d）：

- 停用：前翼元件與後翼襟翼都在 Corner Mode 位置。
- 部分啟用：前翼元件在 Straight Mode，後翼襟翼仍在 Corner Mode。
- 完全啟用：車手下指令後，前翼元件與後翼襟翼都在 Straight Mode。

<figure class="diagram">
<svg viewBox="0 0 420 266" role="img" aria-label="車手可調車身的三種狀態：停用是前後翼都在 Corner Mode，部分啟用是前翼 Straight Mode、後翼 Corner Mode，完全啟用是前後翼都在 Straight Mode">
<title>車手可調車身的三種狀態</title>
<desc>由上到下三張卡片。停用：前翼元件在 Corner Mode，後翼襟翼在 Corner Mode。部分啟用：前翼元件在 Straight Mode，後翼襟翼在 Corner Mode。完全啟用：前翼元件在 Straight Mode，後翼襟翼在 Straight Mode。Straight Mode 的攻角比 Corner Mode 小。</desc>
<rect class="d-surface d-line-s" x="4" y="4" width="412" height="258" rx="10"/>
<text class="d-fg" x="20" y="30" font-size="15">前翼與後翼襟翼各在哪個位置</text>
<rect class="d-surface d-line-s" x="14" y="44" width="392" height="62" rx="8"/>
<rect class="d-accent" x="14" y="44" width="8" height="62" rx="3"/>
<text class="d-fg" x="36" y="70" font-size="15">停用</text>
<text class="d-dim" x="36" y="94" font-size="14">前翼 Corner Mode　後翼 Corner Mode</text>
<rect class="d-surface d-line-s" x="14" y="114" width="392" height="62" rx="8"/>
<rect class="d-accent" x="14" y="114" width="8" height="62" rx="3"/>
<text class="d-fg" x="36" y="140" font-size="15">部分啟用</text>
<text class="d-dim" x="36" y="164" font-size="14">前翼 Straight Mode　後翼 Corner Mode</text>
<rect class="d-surface d-line-s" x="14" y="184" width="392" height="62" rx="8"/>
<rect class="d-accent" x="14" y="184" width="8" height="62" rx="3"/>
<text class="d-fg" x="36" y="210" font-size="15">完全啟用</text>
<text class="d-dim" x="36" y="234" font-size="14">前翼 Straight Mode　後翼 Straight Mode</text>
</svg>
<figcaption>圖：車手可調車身的三種狀態，依 2026 年 FIA 運動規章 B7.1.1 b、c、d 整理。本站示意圖，非依比例、非實測。</figcaption>
</figure>

規章把翼片離開 Corner Mode 的整段期間稱為「部署狀態」（State of Deployment）：從車手下指令起，到 ECU 停用、翼片回到原位為止。指令來自車手本人，至於用方向盤上哪顆按鈕，規章沒有寫。

## 車手得先被通知「已啟用」，翼片還得完全在啟動區內

車手不能想開就開。規章寫：車手只有在透過控制電子系統（Control Electronics）被通知「已啟用」時，才可以完全或部分啟用車手可調車身（B7.1.2 a）。誰決定「已啟用」、什麼時候啟用，B7.1 沒有寫。

第二道條件在 Section C。前翼與後翼襟翼只有在車輛靜止，或完全位於啟動區（Activation Zone）內時，才可處於部署狀態（C3.10.10 w；C3.11.6 j）。

啟動區是 FIA 訂的，賽前至少 4 週會通知所有車隊，每個啟動區的起點在賽道至少一側要有標示牌（B7.1.1 e、f）。規章沒有寫終點怎麼標，也沒有說啟動區資訊一定對外公開，各站啟動區在哪裡、有幾個、多長，條文都沒有列。

回頭看官方那句「所有車、所有時間都可用」。它對比的是 DRS 的落後 1 秒內、指定直線。B7.1.2 a 的條件確實沒有寫與前車的距離。但「所有時間」不能照字面讀成任何時候：被通知已啟用、完全在啟動區內，這兩道條件仍然在。

## 宣告低抓地條件後，只准前翼部分啟用

第三道限制看賽道狀況。賽事總監可以隨時、自行裁量宣告「低抓地條件」（Low Grip Conditions），宣告時會以「LOW GRIP CONDITIONS」的訊息發給所有車隊（B1.5.12 a）。

宣告之後，車手可調車身只允許在低抓地啟動區（Low Grip Activation Zones）內做部分啟用（B7.1.2 b）。部分啟用就是前翼在 Straight Mode、後翼留在 Corner Mode。低抓地啟動區的資訊，同樣是賽前至少 4 週提供給車隊。

所以低抓地條件下，後翼襟翼不能打到 Straight Mode。

規章寫的是「低抓地條件」，沒有直接寫「下雨」。下雨是不是就會宣告低抓地，條文沒有說，不要把兩個詞畫等號。雨天賽道上的其他規則，見[下雨的 F1 怎麼跑：雨胎、安全車起跑，還有比賽被叫停的時候](/articles/f1-101-wet-weather/)。

Overtake 與 Straight Mode 是兩套分開的規則，在同一情境下寫法不同：

- 低抓地條件下，Overtake 停用（B7.2.2 d）；Straight Mode 則是只准部分啟用（B7.1.2 b）。
- 安全車出動時，Overtake 停用，要等安全車駛入維修區入口道（Pit Entry Road）之後，所有賽車都通過終點線（the Line）才重新啟用；賽事總監也可以基於安全停用 Overtake（B7.2.2）。
- B7.1 的車手可調車身條文，沒有寫安全車出動時 Straight Mode 怎麼處理。條文沒寫，這裡就不下結論。安全車的規則見[安全車與紅旗：賽道出事時，比賽怎麼降速、又怎麼中止](/articles/f1-101-safety-car/)。

<figure class="diagram">
<svg viewBox="0 0 420 340" role="img" aria-label="用 Straight Mode 的三道關卡：被通知已啟用，翼片在啟動區內或車輛靜止，低抓地條件下只准前翼部分啟用，全部過關後由車手下指令切換">
<title>用 Straight Mode 要過的關卡</title>
<desc>由上到下四張卡片。第 1 關：車手透過控制電子系統被通知已啟用。第 2 關：翼片完全位於啟動區內，或車輛靜止。第 3 關：沒有宣告低抓地條件才可完全啟用，宣告後只准前翼在低抓地啟動區內部分啟用。最後一張：車手下指令，由 FIA 標準 ECU 控制翼片切到 Straight Mode。</desc>
<rect class="d-surface d-line-s" x="4" y="4" width="412" height="332" rx="10"/>
<text class="d-fg" x="20" y="30" font-size="15">車手下指令之前，先過三關</text>
<rect class="d-surface d-line-s" x="14" y="44" width="392" height="62" rx="8"/>
<text class="d-fg" x="28" y="70" font-size="15">第 1 關：被通知「已啟用」</text>
<text class="d-dim" x="28" y="94" font-size="14">透過控制電子系統收到通知</text>
<rect class="d-surface d-line-s" x="14" y="114" width="392" height="62" rx="8"/>
<text class="d-fg" x="28" y="140" font-size="15">第 2 關：完全在啟動區內，或車輛靜止</text>
<text class="d-dim" x="28" y="164" font-size="14">啟動區資訊賽前 4 週提供給車隊</text>
<rect class="d-surface d-line-s" x="14" y="184" width="392" height="62" rx="8"/>
<text class="d-fg" x="28" y="210" font-size="15">第 3 關：沒有宣告低抓地條件</text>
<text class="d-dim" x="28" y="234" font-size="14">宣告後只准前翼在低抓地啟動區部分啟用</text>
<rect class="d-surface d-accent-s" x="14" y="254" width="392" height="68" rx="8"/>
<text class="d-fg" x="28" y="280" font-size="15">車手下指令，切到 Straight Mode</text>
<text class="d-dim" x="28" y="304" font-size="14">由 FIA 標準 ECU 控制翼片</text>
</svg>
<figcaption>圖：用 Straight Mode 要過的條件，依 2026 年 FIA 運動規章 B7.1.2 a、b 與技術規章 C3.10.10 w、C3.11.6 j 整理。本站示意圖，非依比例、非實測。</figcaption>
</figure>

## 兩個位置之間切換不得超過 400 毫秒，系統失效要回到 Corner Mode

翼片從一個位置切到另一個位置，時間上限是 400 毫秒（C3.10.10 o；C3.11.6 d）。前翼與後翼襟翼都適用。

這是上限，不是實際的平均時間。計時從 ECU 發出換模式指令那一刻起，算到位置感測器確認翼片到位。規章與官方頁都沒有給實測切換時間。

失效怎麼辦？規章要求設計上做到：調整系統失效時，翼片會回到 Corner Mode 位置（C3.10.10 v；C3.11.6 i）。

這是對設計的要求，條文沒有寫失效發生時，賽事實際怎麼處理，別讀成「失效就一定安全」。

Straight Mode 以外，前翼還有另一種調整：只能在車輛靜止時用工具進行，不受 ECU 控制，主翼片最多偏移 30 毫米、副翼片最多偏移 60 毫米，而且不得使攻角減小（C3.10.10）。這和賽道上的兩位置系統是兩回事，車隊在車庫與進站時調前翼，就屬於這一類。

最後是版本。依 2026-08-05 版 Section B，2027 與 2028 的變更段沒有列出 B7.1；Section C Issue 20 沒有這類變更段。本篇的條文都是 2026 現行條款。

## 常見問題

### 主動空力是新版 DRS 嗎？

不是同一套規則。DRS 只讓落後前車 1 秒內的追擊車在指定直線使用。Straight Mode 的條件是車手被通知已啟用、翼片完全位於啟動區內（B7.1.2 a；C3.10.10 w；C3.11.6 j），B7.1.2 a 沒有寫與前車的距離。動的翼片也不同：前翼元件與後翼襟翼都是車手可調車身。

### 前後翼的角度可以自己調嗎？

賽道上不行。除了系統失效與切換過程，翼片只能待在 Corner Mode 與 Straight Mode 兩個位置，由 FIA 標準 ECU 控制。車隊能做的另一種調整，是車輛靜止時用工具調整前翼，幅度有 30 毫米與 60 毫米的上限。

### 低抓地條件下還能用 Straight Mode 嗎？

只能部分用。賽事總監宣告低抓地條件之後，車手可調車身只允許在低抓地啟動區內做部分啟用，也就是前翼動、後翼襟翼不動。規章寫的是「低抓地條件」，沒有直接寫下雨。

### 主動空力系統壞了會怎樣？

規章要求設計上做到：調整系統失效時，翼片回到 Corner Mode 位置。但條文只規定設計，沒有寫失效當下比賽怎麼處理。

## 接下來看什麼

- [F1 為什麼很難超車：髒空氣，以及 2026 年新增的幫手](/articles/f1-101-overtaking/)
- [F1 賽車真的能倒著開在天花板上嗎？下壓力讓車越快越黏地](/articles/f1-101-downforce/)
- [一輛 F1 賽車由什麼組成：從車鼻到尾翼，一張零件地圖](/articles/f1-101-car-anatomy/)
- [下雨的 F1 怎麼跑：雨胎、安全車起跑，還有比賽被叫停的時候](/articles/f1-101-wet-weather/)

## 資料來源

一手來源（FIA 規章）：

- [FIA 2026 F1 Regulations, Section B [Sporting], Issue 08（2026-08-05）](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_08_-_2026-08-05_7.pdf)：B1.5.12 低抓地條件、B7.1 車手可調車身與啟動區、B7.2.2 Overtake 的啟用與停用、2027 與 2028 變更段
- [FIA 2026 F1 Regulations, Section C [Technical], Issue 20（2026-08-05）](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_c_technical_-_iss_20_-_2026-08-05.pdf)：C3.2、C3.10.10、C3.11.6、C8.2.1 與「State of Deployment」定義

官方說明：

- [formula1.com：2026 regulations explained, all you need to know about F1's new aerodynamics](https://www.formula1.com/en/latest/article/2026-regulations-explained-all-you-need-to-know-about-f1s-new-aerodynamics.7IAt0auc32UkCEFE5ypkTB)

二手來源：

- [RaceFans：Forget the Manual Override Mode, F1 renames its new 2026 technologies（2025-12-17）](https://www.racefans.net/2025/12/17/forget-the-manual-override-mode-f1-renames-its-new-2026-technologies/)

查證日：2026-09-26。限制：官方入門文「所有車、所有時間都可用」比規章寬，正文已並列規章條件；Straight Mode 的實際攻角、阻力與圈速差、各站啟動區的位置與長度、安全車出動時 Straight Mode 的處理，規章與官方頁都沒有寫，文中不寫數字；RaceFans 文中提到的舊名稱彼此不一致，文中不寫舊名；2026 賽季主動空力的實際故障或判罰案例沒有查到官方原文，文中不寫。
