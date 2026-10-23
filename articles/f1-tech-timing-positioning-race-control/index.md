---
slug: f1-tech-timing-positioning-race-control
type: "guide"
date: "2026-07-30"
title: "F1 計時與安全訊號怎麼分工？從通線紀錄到 VSC"
subtitle: "賽車通過終點線，要留下時間與身分；還在圈中，差距與位置也要更新。三個計時分段回答快慢，VSC 使用的安全分區則是另一種切法。"
lede: "轉播上的三個計時分段，不能拿來當作 VSC 的安全分區。計時應答器與路面線圈留下通線紀錄，定位系統追蹤車輛，VSC 則要求車手在更細的安全分區守住最低時間。"
---

# F1 計時與安全訊號怎麼分工？從通線紀錄到 VSC

一台 F1 賽車通過終點線，計時畫面隨即多了一筆成績。系統不只得知道有車經過，還得知道是哪一台、在什麼時刻經過。車繼續往前跑，這些問題也沒有結束：它和前車差多少？快車是不是正要追上慢車？如果出動虛擬安全車，它有沒有按要求減速？

這些問題需要的資料不同，不能只靠一個「GPS」或「計時器」把全部功能帶過。先從車通過終點線的那一刻看起。

## 車過了線，時間和身分都要留下來

FIA 2026 年技術規則 C8.15 要求，每台車裝設 2 個計時應答器（timing transponder），由官方指定的計時人員提供，並依指定文件安裝。

路面上也有設備。FIA 的《計時系統指引》把自動車輛識別系統描述為兩部分：車上的單元，以及埋在控制線路面裡的接收線圈。車與路面設備配合，讓通線紀錄能帶著車輛身分。

指引建議的控制線配置，還包括光電管與錄影攝影機。前者在車輛遮住光束時留下訊號，後者錄下車輛通過控制線的畫面；連同自動識別，這三項都應能記錄到千分之一秒。指引另外建議保留人工車輛識別。

## 還沒跑完一圈，差距已經在變

F1 官網的計時解說把一圈分成 3 個計時分段：第一、第二、第三分段。它們各自回答：這台車在哪一大段跑得快，哪一大段丟了時間。

但差距不必等到三個大分段的邊界才更新。F1 官網 2020 年的理想單圈分析說，三個計時分段底下，還會再切成較小的 loop，也叫 mini-sector。把同一位車手在同一場次裡，各個 loop 的最快時間加起來，就能組成理想單圈；這不一定是車手真正連續跑出過的一圈。

F1 官網 2019 年對 Live Timing 的說明則寫，Gap 與 Interval 欄位按 loop／segment 更新，大約每 200 公尺一次。

所以同一張畫面上，三個分段適合看一圈在哪裡快慢不同；更細的更新，則讓觀眾不必等到一個大分段結束，才知道兩車差距正在縮小。

## 車輛定位與安全通訊，要在車仍行進時工作

記下通線時間之外，賽事控制還需要追蹤車輛位置。2026 年技術規則 C8.11.1 要求的 marshalling system，包含車輛定位系統，以及賽事控制對車的雙向通訊系統，由 FIA 指定的供應商，依 FIA 訂定的規格提供。

一台車的通線紀錄，回答的是它何時通過某個位置；車輛定位與安全通訊，則把注意力放在仍行進中的車輛。當快車準備套圈，安全提示就不只是單獨一台車的問題，還得看它與前車的關係。

## 快車接近慢車，藍旗提示怎麼出現

以 2022 年摩納哥站的賽事總監指令 V2 為例：比賽中，快車追近到被套圈車輛後方 3.0 秒內時，系統先發預警，讓慢車的車隊提醒車手；差距到 1.2 秒內時，則會出示藍旗，並有藍色燈號面板、座艙燈與計時螢幕訊息。

收到提示的慢車車手，必須在第一個可行機會讓後車通過。預警讓車隊有時間提醒，正式訊號則把該採取行動的對象告知車手。

從車隊先收到預警，到車手看到正式訊號，這份指令把接近與讓車分成了前後兩步。3.0 秒與 1.2 秒是這一站的設定。

## VSC 不是整圈慢一點就好

虛擬安全車（VSC）出動後，規則要求的不是只把整圈跑慢。2026 年比賽規則 B5.12.2b，使用了另一種分區：安全分區（marshalling sector），定義為相鄰 FIA 燈號面板之間的那段賽道。

這和計時畫面的 3 個大分段不同。VSC 的最低時間要求落在這些更細的安全分區，而不是只看整圈平均。

條文要求所有車減速，並高於 FIA ECU 設定的最低時間：每個安全分區內至少一次符合，通過第一、第二安全車線時也都要符合。燈號面板轉綠的那一刻，車輛仍須高於這個最低時間。

條文列的是時間條件，不是速度下限。每個安全分區、兩條安全車線與轉綠瞬間，各有要滿足的要求；不是只用整圈跑得較慢，就能代替這些條件。

同樣是在追蹤一台車，成績計時要分辨快慢，安全規則則要車手在指定情況改變行動。3 個計時分段能告訴觀眾哪一大段跑得快，卻不能拿來取代 VSC 的安全分區。分清楚兩種切法，計時畫面與安全提示才不會被讀成同一件事。

若要接著看安全提示失效時的實際影響，另見[匈牙利站藍旗故障](/articles/f1-2026-r11-hungary-blue-flag-failure/)。

## 資料來源

查證日為 2026 年 10 月 23 日（台北時間）。本文使用下列 2026 年規則版本，搭配各自標明年份的官方解說與單站指令；公開資料不足以還原整套系統的端對端資料路徑。

- FIA：[2026 F1 Technical Regulations，Section C，Issue 19，2026-06-25](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_c_technical_-_iss_19_-_2026-06-25.pdf)，C8.11.1（定位與安全通訊）、C8.15（計時應答器）。
- FIA：[2026 F1 Sporting Regulations，Section B，Issue 07，2026-06-25](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_07_-_2026-06-25.pdf)，B5.12.2b（VSC 安全分區與最低時間）。
- FIA：[Timing System Guidelines](https://www.fia.com/sites/default/files/fia_timing_system_guidelines_v2.pdf)，PDF 頁尾為 Issue 1、October 2018，§1.1 設備定義與 §2.3 控制線配置建議；網址中的 v2 不作版次依據。
- FIA：[2022 Monaco Grand Prix — Race Director's Event Notes V2](https://www.fia.com/sites/default/files/decision-document/2022%20Monaco%20Grand%20Prix%20-%20Race%20Director's%20Event%20Notes%20V2.pdf)，§7（比賽套圈的預警、藍旗參數與提示）。
- Formula1.com：[Ideal lap — Bottas quickest but returning Hamilton poised to strike](https://www.formula1.com/en/latest/article/ideal-lap-bottas-quickest-but-returning-hamilton-poised-to-strike.410CbwkP3Rya1rvOtlc1yg)（2020 年，三個計時分段、loop 與理想單圈）。
- Formula1.com：[You speak, we listen — the latest F1 Live Timing improvements](https://www.formula1.com/en/latest/article/you-speak-we-listen-the-latest-f1-live-timing-improvements.G9HzG04abEZ7wSosVjUfg)（2019 年，Gap／Interval 更新的約 200 公尺說明）。
