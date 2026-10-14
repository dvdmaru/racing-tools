---
slug: f1-101-pit-stop-table-reading
type: "guide"
date: "2026-10-13"
topic_ref: "manual"
title: "新加坡這張進站表，拆得出車輛靜止了多久嗎？"
subtitle: "OpenF1 和 Jolpica 的進站欄位各自怎麼定義、兩邊能不能互相替代、空值該怎麼讀：拿 2026 新加坡正賽和 2025 墨西哥城正賽的快照逐筆對照。"
lede: "2026 新加坡正賽，漢米爾頓第 18 圈進站。OpenF1（非官方資料服務）的 lane_duration 記 24.0 秒，文件稱這是車在維修區車道內的時間。Jolpica（另一個資料源）的 duration 記 24.048 秒，文件寫這個時間包含維修區入口、出口與紅旗時間（原文附 if necessary）。兩家文件沒有宣告共用的起訖線。以上數字取自本站 2026-10-13 取得的快照。OpenF1 自稱與 Formula 1 公司無關，本文比較的是兩個資料源的欄位，不以它們冒充官方計時定義。"
---

# 新加坡這張進站表，拆得出車輛靜止了多久嗎？

2026 年新加坡正賽，漢米爾頓第 18 圈進站。

OpenF1 的進站表上，這一筆有三個看起來都像「進站時間」的欄位。`lane_duration` 是 24.0，`pit_duration` 也是 24.0，`stop_duration` 是空的。

OpenF1 自稱是非官方專案，與 Formula 1 公司無關。同一圈在另一個資料源 Jolpica 的紀錄是 24.048。

以上都取自 2026-10-13 取得的快照。這篇只讀欄位：每一欄量的是哪一段，兩個資料源能不能互相替代，空白的欄位怎麼讀。

## 漢米爾頓第 18 圈那一筆，量的是哪一段？

先看 24.0。OpenF1 文件把 `lane_duration` 寫成「The time spent in the pit lane, in seconds.」，也就是車在維修區車道內的時間。這句沒有提入口或出口。

同一列的 `pit_duration` 也是 24.0，但它不是第二段計時。OpenF1 文件（2026-10-13 快照）標示 `pit_duration` 已棄用，內容與 `lane_duration` 相同，並寫明 2026 賽季結束時移除。2026 新加坡正賽的 25 筆進站，這兩欄逐筆相等（本站自行計算）。

所以那一列的兩個 24.0，是同一個值寫了兩次。兩個都不是文件所稱的靜止進站時間。文件把靜止進站時間放在另一欄 `stop_duration`，第 3 節再看它。

## 換成 Jolpica，能拿到靜止時間嗎？

在新加坡這一場，換成 Jolpica，仍然拿不到 OpenF1 文件所稱的靜止進站時間。

2026 新加坡正賽、本站 2026-10-13 取得的兩份快照，以車手姓名加圈號配對，25 筆全部配上。Jolpica 的 `duration` 每一筆都比 OpenF1 的 `lane_duration` 多 0.001 到 0.098 秒（本站自行計算）。

兩家文件的措辭不一樣。OpenF1 寫的是車道內的時間。Jolpica 對 `duration` 的說明是「Duration of the stop, including pit entry, exit and red flag time, if necessary (MM:ss.sss)」，意思是停站的持續時間，包含維修區入口、出口與紅旗時間。if necessary 這個條件語管到哪幾項，文件沒有寫。

再換一場。2025 墨西哥城正賽的兩份快照各 27 筆，姓名加圈號配上 27 組。25 組兩源完全相同。其餘兩組是塞恩斯第 46 圈差 0.046 秒、第 56 圈差 0.069 秒，Jolpica 都比較大（本站自行計算）。

兩場的數字都很接近，讀起來像同一個數。但兩欄從哪裡量到哪裡，要看文件。兩家文件都沒有宣告兩欄等價，也沒有宣告共用的起訖線。光靠數字接近，還不能說兩欄量的是同一段。

## `stop_duration` 這一欄怎麼讀

OpenF1 文件把 `stop_duration` 定義為「The stationary pit stop time, in seconds.」，也就是靜止進站時間，並寫明這一欄只從 2024 美國大獎賽起提供。

2026 新加坡正賽、本站 2026-10-13 取得的 OpenF1 快照中，這一欄 25 筆全是空值（null）。OpenF1 文件沒有說明原因。

同一批快照裡的 2025 墨西哥城正賽，27 筆中有 25 筆有值。OpenF1 文件自己的範例列取自這一場：車號 16、第 31 圈，`lane_duration` 是 22.215 秒，`stop_duration` 是 2.2 秒。

<figure class="diagram">
<svg viewBox="0 0 420 208" role="img" aria-label="示意：OpenF1（非官方資料服務）文件範例列，2025 墨西哥城正賽、車號 16、第 31 圈的兩個欄位值：lane_duration 22.215 秒、stop_duration 2.2 秒；取自 2026-10-13 文件快照；本站依文件範例製作的示意，非依比例。">
<title>OpenF1 進站時間欄位示意</title>
<desc>OpenF1（非官方資料服務）文件範例列：2025 墨西哥城正賽、車號 16、第 31 圈。lane_duration 22.215 秒，文件定義為維修區車道內的時間；stop_duration 2.2 秒，文件定義為靜止進站時間。取自 2026-10-13 文件快照；本站依文件範例製作的示意，非依比例。</desc>
<rect class="d-surface d-line-s" x="4" y="4" width="412" height="200" rx="10"/>
<text class="d-fg" x="20" y="30" font-size="15">OpenF1（非官方）文件範例列</text>
<text class="d-fg" x="20" y="52" font-size="14">2025 墨西哥城正賽｜文件快照 2026-10-13</text>
<text class="d-fg" x="20" y="72" font-size="14">車號 16｜第 31 圈｜非依比例</text>
<rect class="d-surface d-line-s" x="14" y="88" width="392" height="50" rx="8"/>
<rect class="d-accent d-line-s" x="26" y="102" width="22" height="22" rx="4"/>
<text class="d-fg" x="60" y="118" font-size="15">lane_duration　22.215 秒</text>
<rect class="d-surface d-line-s" x="14" y="148" width="392" height="50" rx="8"/>
<rect class="d-accent d-line-s" x="26" y="162" width="22" height="22" rx="4"/>
<text class="d-fg" x="60" y="178" font-size="15">stop_duration　2.2 秒</text>
</svg>
<figcaption>圖：OpenF1（非官方資料服務）文件範例列，2025 墨西哥城正賽車號 16 第 31 圈：lane_duration 22.215 秒、stop_duration 2.2 秒（2026-10-13 文件快照）。在 2026 新加坡正賽的 OpenF1 快照（2026-10-13 取得）中，stop_duration 25 筆皆為空值，OpenF1 文件未說明原因。本站依文件範例與快照製作的示意，非依比例。</figcaption>
</figure>

所以「拆不出靜止時間」，說的是新加坡這一場。墨西哥城那一場多數筆有值；其他場次的情形，這兩場看不出來。文件只說這一欄從 2024 美國大獎賽起提供，沒有說每一場、每一筆都有值。

墨西哥城那 2 筆空值，正是塞恩斯的第 46 圈和第 56 圈，也就是兩源有差的那兩筆。

兩場還有一個共同點：`stop_duration` 空著的列，`lane_duration` 都只有一位小數；有值的列是兩到三位（本站自行計算）。兩份文件都沒有解釋這個現象。

## 這張表沒寫的事

新加坡這 25 筆裡，`lane_duration` 最長的是博塔斯第 28 圈的 29.2 秒，中位數是 24.3 秒（2026 新加坡 OpenF1 快照，本站自行計算）。表上看得出這一筆比中位數長，看不出長在哪裡。

也不能直接把車道時間讀成進站損失。OpenF1 文件寫的是車道內的時間，Jolpica 文件寫的是停站持續時間，兩邊都沒有把這一欄定義成損失。

進站損失怎麼估，同一場新加坡的另一篇有算：[新加坡站第 39 圈虛擬安全車期間，勒克萊爾進站，漢米爾頓則留在場上](/articles/f1-2026-r17-singapore-ferrari-strategy-ledger/)。那篇自己標明，估算含新舊胎差，不是純進站損失。

## 想把兩張表接起來，鑰匙用哪一欄？

OpenF1 的進站列用車號（`driver_number`）標車手，Jolpica 的進站列用 `driverId`。圈號欄則分別叫 `lap_number` 和 `lap`。

車號看起來最直接，但 2025 墨西哥城那份快照有兩人對不上。Jolpica 賽果的 `permanentNumber`，維斯塔潘是 3，OpenF1 車手表記 1。諾里斯在 Jolpica 賽果是 1，在 OpenF1 是 4。已取得的快照與文件都沒有說明原因。

這兩場改用車手姓名加圈號配對。兩場配完之後，兩邊都沒有剩下的列，也沒有重複的「車手加圈號」。這個做法只適用這兩份快照，不是所有資料源的通用鍵。

## 常見問題

### 表上的進站秒數是換胎時間嗎？

不能直接這樣讀。OpenF1（非官方資料服務）文件把 `lane_duration` 定義為車在維修區車道內的時間；Jolpica 文件把 `duration` 寫成停站持續時間，包含維修區入口、出口與紅旗時間（原文附 if necessary）。OpenF1 另有 `stop_duration` 一欄，文件定義為靜止進站時間。以上依本站 2026-10-13 取得的文件快照。

### stop_duration 為什麼是空的？

2026 新加坡正賽、本站 2026-10-13 取得的 OpenF1（非官方資料服務）快照中，這一欄 25 筆都是空值，OpenF1 文件沒有說明原因；文件只寫這一欄從 2024 美國大獎賽起才提供。對照的 2025 墨西哥城正賽（同批快照），27 筆中 25 筆有值。

### pit_duration 和 lane_duration 差在哪？

OpenF1（非官方資料服務）文件（2026-10-13 快照）標示 `pit_duration` 已棄用、內容與 `lane_duration` 相同，並寫明 2026 賽季結束時移除。

### 兩個資料源的進站時間一樣嗎？

在 2026 新加坡正賽、本站 2026-10-13 取得的兩份快照中，以車手姓名加圈號配對 25 筆，Jolpica `duration` 每筆都比 OpenF1 `lane_duration` 多 0.001 到 0.098 秒（本站自行計算）。這只說明這一場。OpenF1（非官方資料服務）文件稱這一欄是維修區車道內的時間，Jolpica 文件寫含入口、出口與紅旗時間（原文附 if necessary），兩家沒有宣告兩欄等價或共用起訖線。

## 接下來看什麼

- [先進站的人為什麼有時反而贏：F1 進站策略的 undercut 與 overcut](/articles/f1-101-pit-stop-strategy/)：進站分成哪兩段、undercut 與 overcut
- [F1 維修區的規矩：一般情況下技師在內側車道動手，出站要看綠燈](/articles/f1-101-pit-lane/)：維修區限速與停車位
- [新加坡站第 39 圈虛擬安全車期間，勒克萊爾進站，漢米爾頓則留在場上](/articles/f1-2026-r17-singapore-ferrari-strategy-ledger/)：同一場新加坡，進站多掉幾秒怎麼估
- [諾里斯這 10 圈四人之中最快，名次卻只有第 7](/articles/f1-101-race-pace-reading/)：用圈速與進站紀錄讀一場比賽

## 資料來源

資料服務文件：

- [OpenF1 文件](https://openf1.org/docs/)：`pit` 端點的 `lane_duration`、`pit_duration`（deprecated）、`stop_duration` 欄位定義。OpenF1 自述為非官方專案，與 Formula 1 公司無關。
- [Jolpica pitstops 端點文件](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/pitstops.md)：`lap`、`stop`、`duration` 欄位定義。
- 2026 新加坡正賽（OpenF1 session_key 11388）：[OpenF1 pit](https://api.openf1.org/v1/pit?session_key=11388)、[OpenF1 drivers](https://api.openf1.org/v1/drivers?session_key=11388)、[OpenF1 sessions](https://api.openf1.org/v1/sessions?session_key=11388)、[Jolpica pitstops](https://api.jolpi.ca/ergast/f1/2026/17/pitstops.json)。
- 2025 墨西哥城正賽（OpenF1 session_key 9877）：[OpenF1 pit](https://api.openf1.org/v1/pit?session_key=9877)、[OpenF1 drivers](https://api.openf1.org/v1/drivers?session_key=9877)、[OpenF1 sessions](https://api.openf1.org/v1/sessions?session_key=9877)、[Jolpica pitstops](https://api.jolpi.ca/ergast/f1/2025/20/pitstops.json)。

二手來源：本文未使用媒體報導作為事實依據。

查證日 2026-10-13。限制說明：

- 上列文件與資料都是本站在 2026-10-13 12:00–12:10（台北）取得的快照。文中的欄位定義依快照當時的文件措辭轉述，「`pit_duration` 將在 2026 賽季結束時移除」也是快照當時 OpenF1 文件所述。
- OpenF1 自述為非官方專案、與 Formula 1 公司無關；Jolpica 文件是該資料源自己的說明。本文比較的是這兩個資料源在指定快照中的欄位，不以它們冒充 FIA 或 Formula 1 的官方計時定義。
- Jolpica 文件寫 `duration` 包含維修區入口、出口與紅旗時間，原文附 if necessary；文件沒有界定這個條件修飾哪幾項。
- 逐筆比較只涵蓋 2026 新加坡正賽與 2025 墨西哥城正賽這兩場。兩個資料源以車手姓名加圈號配對；這個配對法只適用於這兩份快照，不是所有資料源的通用鍵。
- 兩場的逐筆配對與 Jolpica `duration` − OpenF1 `lane_duration` 差值（新加坡 25 筆、墨西哥城 27 筆）、新加坡 `lane_duration` 的最長值與中位數、小數位數觀察，都是本站依快照自行計算，不是來源原話。
- 2026 新加坡正賽、本站 2026-10-13 取得的 OpenF1 快照中，`stop_duration`（文件定義為靜止進站時間）25 筆皆為空值，OpenF1 文件沒有說明原因；同批的 2025 墨西哥城快照 27 筆中 25 筆有值。
- 2025 墨西哥城那份 Jolpica 賽果快照中，維斯塔潘、諾里斯兩人的 `permanentNumber` 與 OpenF1 drivers 快照的車號不一致；已取得的兩份快照與 Jolpica pitstops 文件都沒有說明原因。
- 本站資料庫沒有進站表，文中的逐筆進站時間只取自上列快照。
