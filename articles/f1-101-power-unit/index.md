---
slug: "f1-101-power-unit"
type: "guide"
date: "2026-09-25"
topic_ref: "manual"
title: "F1 動力單元是什麼：引擎、馬達與電池怎麼分工，決定車手何時有力氣"
subtitle: "F1 賽車裡那顆「引擎」，在規章裡是一整套動力單元：1600cc V6 內燃機、渦輪、350 kW 電動馬達、電池與控制電子。電池一次只能動用 4 MJ，馬達的力氣還會隨車速變小，這套分工決定了車手在一圈裡什麼時候有電可用。"
lede: "F1 賽車裡那顆「引擎」，其實是一整套動力單元：內燃機負責一部分推力，電動馬達與電池補上另一部分。車手在一圈裡什麼時候有力氣，就看這套東西怎麼分工：電池一次只能動用 4 MJ，馬達的力氣還會隨車速變小，沒啟用 Overtake 模式時，時速過了約 290 公里就開始縮水。"
---

# F1 動力單元是什麼：引擎、馬達與電池怎麼分工，決定車手何時有力氣

沒有啟用 Overtake 模式時，時速一到 345 公里，FIA 規章給電動馬達的功率就是 0。

同一台馬達，在時速約 290 公里以下可以用滿 350 kW。車手的油門一路踩到底，但是到了 345 km/h，推車的就只剩內燃機。這不是故障，而是 2026 年技術規章寫好的一條曲線。

要看懂這條曲線，得先放下「F1 引擎就是一顆引擎」的想像。規章管的單位是一整套動力單元（Power Unit，簡稱 PU），內燃機只是其中一塊。這篇要講的就是這套分工：內燃機和電動馬達一起推車，而電池能動用多少電、馬達在什麼車速還有力氣，決定了車手在一圈裡什麼時候有電可用。

## F1 的「引擎」在規章裡是一整套動力單元，內燃機只是六類元件之一

要知道誰在推車、誰在存電，先得把「引擎」拆開。FIA 2026 年技術規章對動力單元的定義是：內燃機與渦輪增壓器（含附屬件）、能量回收系統（Energy Recovery System，簡稱 ERS），以及讓它們隨時能運作的作動系統與控制電子。

拆開來看，規章把動力單元分成六類受管制的元件：ICE（內燃機）、TC（渦輪增壓器）、EXH（排氣）、MGU-K（電動馬達，也能發電）、ES（電池組）、PU-CE（動力單元控制電子）。每一類都有自己的數量限制（運動規章另外替附屬件設了額度），後面講罰則時會再用到這六個縮寫。

內燃機的規格寫得很死：四行程、排氣量 1600cc、六個汽缸排成 90 度的 V 型，渦輪只准用一顆。燃料也改成「先進永續燃料」（Advanced Sustainable fuel），為什麼要改，可以看[2026 新規則指南](/articles/f1-2026-rules-guide/)。

所以轉播裡說「法拉利引擎」「賓士引擎」，指的其實是這一整套：內燃機、渦輪、馬達、電池與控制電子，由同一家廠商供應。

## 能推動車輪的只有兩處：內燃機與電動馬達

六類元件裡，真正能把車往前推的只有兩個。規章 C5.2.1 寫得很直接：除了內燃機與 ERS-K，任何裝置都不准用來推動賽車，也不准用來回充能量。

ERS-K 是什麼？規章的定義是「ERS 中唯一被允許推動賽車的部分」，核心就是電動馬達 MGU-K。MGU-K 的 K 是 Kinetic，也就是動能。它加速時當馬達推車，煞車時則把減速的動能收回來。

電池組（ES）只負責存電，自己不推車。規章對 ES 的定義是「ERS 中儲存能量的部分」。

2025 年以前，動力單元還有第二套回收系統 MGU-H，H 是 Heat，負責從排氣氣流裡回收能量。F1 官方網站的說法是，這套系統「被視為多餘」而取消。2026 年的規章只准內燃機與 ERS-K 推進或回充，所以排氣的能量不再被收進電池。

電動馬達的直流電功率上限是 350 kW（C5.2.7）。F1 官方新聞稿的說法是，舊制的 MGU-K 只有 120 kW，新的「將近三倍」。

<figure class="diagram">
<svg viewBox="0 0 420 444" role="img" aria-label="動力單元能量流向：燃料進內燃機，內燃機與 MGU-K 兩處推動後輪；煞車與部分油門時 MGU-K 發電回充電池，電池再放電給 MGU-K">
<title>2026 年 F1 動力單元能量流向</title>
<desc>左上是燃料，向下箭頭進入內燃機與渦輪。右上是電池（ES），右側中間是 MGU-K 電動馬達。電池到 MGU-K 有一條向下的放電箭頭，MGU-K 到電池有一條向上的回充箭頭。內燃機與 MGU-K 各有一條向下箭頭指向後輪，代表只有這兩處能推動賽車。後輪到 MGU-K 有一條向上箭頭，代表煞車時 MGU-K 把動能收回。內燃機到 MGU-K 有一條橫向箭頭，代表部分油門時也能帶動 MGU-K 發電。2026 年沒有 MGU-H，排氣的能量不再回收進電池。圖中沒有功率數字。</desc>
<rect class="d-surface d-line-s" x="20" y="20" width="170" height="52" rx="10"/>
<text class="d-fg" x="105" y="52" font-size="17" text-anchor="middle">燃料</text>
<rect class="d-surface d-line-s" x="230" y="20" width="170" height="52" rx="10"/>
<text class="d-fg" x="315" y="52" font-size="17" text-anchor="middle">電池（ES）</text>
<line class="d-dim-s" x1="105" y1="74" x2="105" y2="118" stroke-width="2"/>
<polygon class="d-dim" points="97,116 113,116 105,128"/>
<line class="d-dim-s" x1="290" y1="74" x2="290" y2="118" stroke-width="2"/>
<polygon class="d-dim" points="282,116 298,116 290,128"/>
<text class="d-fg" x="246" y="106" font-size="14">放電</text>
<line class="d-dim-s" x1="350" y1="128" x2="350" y2="86" stroke-width="2"/>
<polygon class="d-dim" points="342,86 358,86 350,74"/>
<text class="d-fg" x="358" y="106" font-size="14">回充</text>
<rect class="d-surface d-line-s" x="20" y="130" width="170" height="52" rx="10"/>
<text class="d-fg" x="105" y="162" font-size="17" text-anchor="middle">內燃機＋渦輪</text>
<rect class="d-surface d-line-s" x="230" y="130" width="170" height="52" rx="10"/>
<text class="d-fg" x="315" y="162" font-size="17" text-anchor="middle">MGU-K 馬達</text>
<line class="d-dim-s" x1="192" y1="156" x2="218" y2="156" stroke-width="2"/>
<polygon class="d-dim" points="218,149 218,163 229,156"/>
<line class="d-dim-s" x1="150" y1="184" x2="150" y2="238" stroke-width="2"/>
<polygon class="d-dim" points="142,236 158,236 150,248"/>
<line class="d-dim-s" x1="270" y1="184" x2="270" y2="238" stroke-width="2"/>
<polygon class="d-dim" points="262,236 278,236 270,248"/>
<line class="d-dim-s" x1="295" y1="248" x2="295" y2="196" stroke-width="2"/>
<polygon class="d-dim" points="287,196 303,196 295,184"/>
<text class="d-fg" x="210" y="222" font-size="14" text-anchor="middle">兩處推進</text>
<text class="d-fg" x="305" y="222" font-size="14">煞車回收</text>
<rect class="d-surface d-line-s" x="110" y="250" width="200" height="52" rx="10"/>
<text class="d-fg" x="210" y="282" font-size="17" text-anchor="middle">後輪</text>
<text class="d-fg" x="30" y="340" font-size="14">橫向箭頭：部分油門時，</text>
<text class="d-fg" x="30" y="362" font-size="14">內燃機也能帶動 MGU-K 發電。</text>
<text class="d-fg" x="30" y="394" font-size="14">2026 年沒有 MGU-H，</text>
<text class="d-fg" x="30" y="416" font-size="14">排氣的能量不再回收進電池。</text>
</svg>
<figcaption>圖：2026 年 F1 動力單元的能量流向，依 FIA 2026 技術規章 C5.2 與動力單元定義繪製。本站示意圖，非依比例、非實測。</figcaption>
</figure>

這張圖可以用兩條路來讀。第一條路是燃料進內燃機，內燃機推後輪。第二條路是一個循環：煞車時後輪的動能經 MGU-K 變成電，存進電池，加速時電池再放電給 MGU-K 推後輪。部分油門時，內燃機也能帶動 MGU-K 發電。兩條路最後都落在後輪上。

官方還有一句很好記的口語：「車子用的動力，大約一半來自電、一半來自內燃機。」這是 F1 官方對設計目標的說法，規章裡並沒有 50/50 這一條。舊世代的電力大約只占兩成，新舊世代的對照表可以看[2026 新規則指南](/articles/f1-2026-rules-guide/)。

## 電池一次只能動用 4 MJ，每圈卻最多能回充 8.5 MJ

馬達要有電才能出力，而電要從電池來。這裡出現第一組讓新手困惑的數字。

電池能動用的電，只有一個 4 MJ 的「窗口」（MJ 是百萬焦耳，一種能量單位）：最高電量與最低電量的差，在賽道上任何時候都不可超過 4 MJ（C5.2.9）。

可是每一圈能回充的電，上限是 8.5 MJ（C5.2.10）。

每圈可以收回來的電，比電池一次能動用的窗口還大。這兩條合起來，有一種讀法：電不能一次存滿再慢慢花，而是必須在同一圈裡邊充邊用。煞車收回來的電，要在接下來的加速段放出去，窗口空出來之後，下一個彎才收得進新的電。這是從兩條規章推出來的解讀，規章本身沒有這一句。

電從哪裡來？F1 官方解釋 2026 年新詞時寫到，賽車會在煞車、部分油門與收油時回充電池。

8.5 MJ 也不是每一站都一樣。FIA 判定某一站每圈收不到那麼多電時，可以把上限降到 7 MJ；排位賽與衝刺排位賽還能再往下降，最低到 4 MJ，但這是下限，不是每站排位賽的固定值，一季最多 12 站可以這樣降，其中降到低於 5 MJ 的最多 4 站（運動規章 B7.2.1c）。

看到 8.5 MJ，最容易想歪的是「電池一圈可以放出 8.5 MJ」。其實 8.5 MJ 是回充的上限。放電這一側要看兩件事：一是 4 MJ 的電量窗口，二是下一節那條隨車速下降的功率曲線。

## 車速越快，電動馬達能給的力氣越少

350 kW 是絕對上限，不是整圈都拿得到。規章 C5.2.8 把馬達的可用功率寫成一條跟車速掛鉤的公式。

在 Overtake 模式沒有啟用的時候，公式分成三段：

| 車速 | 馬達可用功率上限 |
| --- | --- |
| 低於 340 km/h | 1800 減 5 倍車速（kW） |
| 340 km/h 起，未滿 345 km/h | 6900 減 20 倍車速（kW） |
| 345 km/h 以上 | 0 |

把車速代進第一段公式，時速約 290 公里以下，算出來的數字比 350 大，所以馬達還是以 350 kW 為上限，可以用滿。過了約 290 km/h，車速越高，公式給的功率越低，到 345 km/h 歸零。

所以馬達的完整力氣，出現在出彎加速、車速還沒爬到約 290 km/h 之前。車速再往上，推車的比重就一路移回內燃機身上。開頭那個「油門踩到底，馬達卻沒有功率」的畫面，就是這條公式的第三段。

FIA 可以依賽道調整這條曲線（運動規章 B7.2.1b），所以每一站的實際數字不一定和上表完全一樣。

起跑還有一條限制：從發車格靜止起跑時，車速要先到 50 km/h，MGU-K 才可以使用（FIA 標準電子控制單元為了維持最低加速度而介入時例外）。起跑的其他流程，可以看[F1 正賽怎麼起跑](/articles/f1-101-race-start/)。

## Overtake 模式換上一條更晚才歸零的功率曲線

2026 年的超車輔助叫 Overtake 模式。規章的定義是一種「允許額外回充，並改用另一條 ERS-K 最大功率曲線」的模式。

Overtake 啟用時，馬達的功率上限改成「7100 減 20 倍車速」kW，車速一到 355 km/h 就歸零。依公式代入，時速約 337.5 公里以下都還能用滿 350 kW。沒有啟用時，約 290 km/h 就開始縮水。兩條曲線對照起來，Overtake 讓完整的電力後援多撐了一段車速。

什麼時候能用？運動規章寫的是，車手要等控制電子通知 Overtake「已啟用且已啟動」才能用。正賽中，車手過偵測線時與前車的差距要小於「偵測間距」，才會在啟動線啟用。F1 官方的口語說法是「在偵測點與前車相距一秒內」。規章本身沒有寫死一秒，偵測間距由 FIA 在賽前逐站公告。

偵測線怎麼量差距，請看[計時、定位與賽事控制](/articles/f1-tech-timing-positioning-race-control/)；Overtake 在超車時扮演什麼角色，請看[F1 為什麼很難超車](/articles/f1-101-overtaking/)。

## 一位車手一季只有 4 具內燃機，第一次超額就退 10 格

動力單元不是壞了就換。運動規章先給每位車手一季的元件基本額度（B8.2.2），另一條再規定 2026 年錦標賽每一類多給 1 個額外額度（B8.2.3），所以每位車手實際可用的數量如下：

| 元件 | 2026 年可用數量 |
| --- | --- |
| ICE（內燃機） | 4 |
| TC（渦輪增壓器） | 4 |
| EXH（排氣） | 4 |
| ES（電池組） | 3 |
| PU-CE（控制電子） | 3 |
| MGU-K（電動馬達） | 3 |
| 附屬件 | 6 |

F1 官方網站的寫法也一致：每位車手最多 4 具內燃機與渦輪、3 個 MGU-K、電池組與控制電子，以及 4 組排氣。

超過額度就要罰。同一類元件第一次超額，正賽起跑格位退 10 位；之後同一類每再多用一次，退 5 位，逐次累計（B8.2.8）。罰退和其他罰則的差別，整理在[F1 罰則怎麼判](/articles/f1-101-penalties/)。

FIA 會替相關的動力單元元件上封條，比賽期間只能使用已經封印的元件；正賽後還會替用過的 ICE、TC、MGU-K 再加封條，避免車隊在兩站之間運轉或拆解。

所以 4 具內燃機是一整季要分著用的額度。哪一站換新元件、哪一站接受罰退，是車隊在賽季中要算的帳。

## 2026 年只有五家動力單元廠商，同一套動力單元會裝在好幾隊車上

2026 年供應動力單元的廠商共有五家。依 F1 官方網站與 The Race 的整理，對應如下：

| 動力單元廠商 | 使用的車隊 |
| --- | --- |
| 賓士 | 賓士、威廉斯、Alpine、麥拉倫 |
| 法拉利 | 法拉利、哈斯、凱迪拉克 |
| Red Bull Powertrains（紅牛與福特合作） | 紅牛（Red Bull Racing）、Racing Bulls |
| 本田（Honda） | 奧斯頓馬丁 |
| 奧迪 | 奧迪 |

凱迪拉克是 2026 年加入的新車隊。F1 官方寫到，凱迪拉克車尾裝的是法拉利的動力單元，連變速箱也一起用法拉利的；它計畫在 2029 年換成自家引擎。

所以轉播說「賓士動力的車隊」，指的是賓士、威廉斯、Alpine、麥拉倫這四隊。它們各自打造車身，但車尾那套內燃機、馬達與電池，來自同一家廠商。

## 常見問題

### F1 賽車算是油電混合車嗎？

算。2026 年的動力單元同時有內燃機與電動馬達，兩者都能推動後輪，電池負責存電。F1 官方的口語說法是動力大約一半來自電、一半來自內燃機，但規章裡沒有 50/50 的條文。

### 電池一圈可以放出 8.5 MJ 的電嗎？

不行。8.5 MJ 是每圈回充的上限，電池最高與最低電量的差在賽道上不可超過 4 MJ。放電還受到隨車速下降的功率曲線限制，時速 345 公里以上馬達功率是 0（Overtake 未啟用時）。

### 2026 年為什麼沒有 MGU-H？

MGU-H 是舊制從排氣回收能量的系統。F1 官方說它被視為多餘而取消；2026 年規章只准內燃機與 ERS-K 推進賽車或回充能量。

### 一位車手一季能用幾具引擎？

2026 年每位車手可用 4 具內燃機，也就是基本額度 3 具再加 1 個額外額度。同一類元件第一次超額，正賽起跑格位退 10 位，之後每次退 5 位。

## 接下來看什麼

- [一輛 F1 賽車由什麼組成：從車鼻到尾翼，一張零件地圖](/articles/f1-101-car-anatomy/)
- [F1 為什麼很難超車：髒空氣、煞車點，以及 2026 年新增的幫手](/articles/f1-101-overtaking/)
- [2026 F1 新規則完全指南](/articles/f1-2026-rules-guide/)

## 資料來源

一手來源（FIA 規章與 F1 官方）：

- [FIA，《2026 Formula 1 Regulations, Section C Technical, Issue 20》（2026-08-05）](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_c_technical_-_iss_20_-_2026-08-05.pdf) （Appendix C1 Part B 動力單元、PU 元件、ERS-K、電池組、先進永續成分與 Overtake 定義；C5.1 內燃機；C5.2.1 推進限制；C5.2.7 至 C5.2.12 馬達功率、功率曲線、電量窗口、回充上限與起跑；C5.3 渦輪；C16.1.2 燃料）
- [FIA，《2026 Formula 1 Regulations, Section B Sporting, Issue 08》（2026-08-05）](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_08_-_2026-08-05_7.pdf) （B7.2 Overtake 與回充降值場次、B8.2 元件額度、罰退與封條）
- [F1 官方，《2026 regulations explained: All you need to know about F1's new power units》](https://www.formula1.com/en/latest/article/2026-regulations-explained-all-you-need-to-know-about-f1s-new-power-units.14jfv7a36905uDJDdNyfQd) （MGU-H 取消、MGU-K 由 120 kW 到 350 kW、電力占比目標、永續燃料、廠商與車隊對應）
- [F1 官方，《The beginner's guide to the 2026 regulations》](https://www.formula1.com/en/latest/article/the-beginners-guide-to-the-2026-regulations.6j0tS0hrHG2T01tpmK6XYz) （「大約一半電、一半內燃」的口語說法）
- [F1 官方，《Explained: The new key terms for Formula 1's new-for-2026 rules》](https://www.formula1.com/en/latest/article/explained-the-new-key-terms-for-formula-1s-new-for-2026-rules.3T5BU6TC9quGcIpGzoWkY0) （Overtake 一秒內啟動、回充時機）
- [F1 官方，《How many power unit components has each driver used in 2026 so far?》](https://www.formula1.com/en/latest/article/how-many-power-unit-components-has-each-driver-used-in-2026-so-far.6DLZYWn0uEpsB0409mFRTF) （2026 年元件可用數量）
- [F1 官方，《Explained: Everything you need to know about Cadillac's 2026 entry》](https://www.formula1.com/en/latest/article/explained-everything-you-need-to-know-about-cadillacs-2026-entry-into.7h3SiUnYcbpjoRUJ9VsL2H) （凱迪拉克使用法拉利動力單元與變速箱、2029 年自家引擎計畫）

二手來源（媒體）：

- [The Race，《2026 F1 team engines》](https://www.the-race.com/formula-1/2026-f1-team-engines/) （Racing Bulls 使用 Red Bull Powertrains 動力單元）

查證日：2026-09-25。規章數字以 Section C Issue 20 與 Section B Issue 08（皆為 2026-08-05 版）為準。限制：電池容量、電壓與重量沒有查到一手數字，內燃機的功率在規章裡也沒有數字，所以文中都沒有寫；一圈之中具體在哪些彎回充、在哪些直線放電，也沒有找到官方圖，因此沒有舉賽道實例。
