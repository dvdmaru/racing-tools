---
slug: f1-101-grid-to-finish
type: "guide"
date: "2026-10-13"
topic_ref: "manual"
title: "賽果表的結果差，能直接當成超車數嗎？拿 2025 墨西哥城這一場來讀"
subtitle: "本站把 grid 顯示為發車位；把它減去同一列的 position，得到的是本站自訂的結果差，本文能查的資料源文件沒有定義它。單看這個數字，讀不出超了幾台，也讀不出配速。"
lede: "2025 年墨西哥城大獎賽這一場，把本站資料庫（2026-10-13 查詢）每一列的 grid（本站顯示為發車位）減去同一列的 position，貝爾曼和阿爾本都是 +5；這個結果差是本站自訂的，本文能查的資料源文件沒有定義它。2025 墨西哥城這一場 20 列的 grid 與 position 都恰好是 1 到 20，兩人反方向的車都是 0 台，所以 +5 各對應 5 台 grid 比他小、position 比他大的車：阿爾本那 5 台裡有 4 台的狀態欄寫著 Retired，貝爾曼那 5 台一台也沒有。"
---

# 賽果表的結果差，能直接當成超車數嗎？拿 2025 墨西哥城這一場來讀

2025 年墨西哥城大獎賽的賽果表上，有 2 列的數字長得一樣。

貝爾曼那一列：grid 欄 9，position 欄 4。阿爾本那一列：grid 欄 17，position 欄 12。兩列都是 grid 減 position，得數都是 +5。

+5 看起來像「進步 5 名」。但 2 個 +5 的組成不一樣。阿爾本的 +5 對應 5 台車，其中 4 台的狀態欄寫著 Retired。貝爾曼的 +5 也對應 5 台車，一台 Retired 也沒有。

這個 +5 是誰算的、怎麼拆，要從資料源說起。

## 「進步幾名」是誰算出來的？

賽果表每台車一列。本文會用到 5 個欄位：grid、position、position_text、laps、status。

本站的賽季頁把 grid 顯示成「從第 N 位發車」，所以本文叫它發車位。把 grid 減去同一列的 position，得到的就是本文說的結果差。這是本站自訂的算法。本文能查的資料源文件，沒有這兩欄的正式定義，也沒有定義這個差值。

本站資料庫的 results 表，沒有逐圈名次、超車事件和圈速欄位。所以結果差能告訴你的，只有 2 個欄位差多少。誰超過誰，它答不出來。這一場跑得好不好，單看這個數字也下不了結論。

資料取自本站賽果資料庫，查詢日 2026-10-13。墨西哥城這一場的 grid、position 等 6 欄，和資料源 Jolpica 的同場快照逐列相同，欄位清單見文末。

## 結果差拆成台數來看

結果差可以拆成 2 個台數相減：「grid 比他小、position 比他大」的台數，減去「grid 比他大、position 比他小」的台數。

這個拆法有個前提：那一場的 grid 與 position，要各自恰好是 1 到 N，每個數字各出現一次。2025 年墨西哥城這一場的 N 是 20。

貝爾曼與阿爾本，反方向的車都是 0 台，所以兩個 +5 都是 5 減 0。差別在那 5 台的狀態欄，見下圖。

<figure class="diagram">
<svg viewBox="0 0 420 296" role="img" aria-label="示意圖：2025 年墨西哥城大獎賽，貝爾曼與阿爾本兩人結果差的組成，以狀態欄區分">
<title>2025 墨西哥城：貝爾曼與阿爾本的結果差組成示意</title>
<desc>2025 年墨西哥城大獎賽這一場（本站資料庫與 Jolpica 賽果快照，2026-10-13 取得），貝爾曼與阿爾本的本站自訂結果差（同一列的 grid，本站顯示為發車位，減去 position；本文能查的資料源文件未定義）都是 +5；這一場 grid 與 position 都恰為 1 到 20，兩人反方向的車都是 0 台，所以 +5 各對應 5 台 grid 比他小、position 比他大的車。左欄貝爾曼：皮亞斯特里、安東內利、羅素、漢米爾頓為 Finished，哈賈爾為 Lapped。右欄阿爾本：哈賈爾為 Lapped，塞恩斯、阿隆索、霍肯伯格、勞森為 Retired。狀態取自資料源 status 欄；圖不表示這些車何時、如何換位。</desc>
<rect class="d-surface d-line-s" x="4" y="4" width="412" height="288" rx="10"/>
<text class="d-fg" x="20" y="30" font-size="15">貝爾曼／阿爾本：grid 比他小、</text>
<text class="d-fg" x="20" y="50" font-size="15">position 比他大的車與狀態欄</text>
<text class="d-fg" x="20" y="82" font-size="15">貝爾曼</text>
<text class="d-fg" x="220" y="82" font-size="15">阿爾本</text>
<rect class="d-none d-line-s" x="14" y="92" width="192" height="26" rx="5"/>
<text class="d-fg" x="24" y="111" font-size="14">皮亞斯特里</text>
<text class="d-fg" x="118" y="111" font-size="14">Finished</text>
<rect class="d-none d-line-s" x="14" y="124" width="192" height="26" rx="5"/>
<text class="d-fg" x="24" y="143" font-size="14">安東內利</text>
<text class="d-fg" x="118" y="143" font-size="14">Finished</text>
<rect class="d-none d-line-s" x="14" y="156" width="192" height="26" rx="5"/>
<text class="d-fg" x="24" y="175" font-size="14">羅素</text>
<text class="d-fg" x="118" y="175" font-size="14">Finished</text>
<rect class="d-none d-line-s" x="14" y="188" width="192" height="26" rx="5"/>
<text class="d-fg" x="24" y="207" font-size="14">漢米爾頓</text>
<text class="d-fg" x="118" y="207" font-size="14">Finished</text>
<rect class="d-none d-line-s" x="14" y="220" width="192" height="26" rx="5"/>
<text class="d-fg" x="24" y="239" font-size="14">哈賈爾</text>
<text class="d-fg" x="118" y="239" font-size="14">Lapped</text>
<rect class="d-none d-line-s" x="214" y="92" width="192" height="26" rx="5"/>
<text class="d-fg" x="224" y="111" font-size="14">哈賈爾</text>
<text class="d-fg" x="318" y="111" font-size="14">Lapped</text>
<rect class="d-none d-accent-s" x="214" y="124" width="192" height="26" rx="5" stroke-width="3"/>
<text class="d-fg" x="224" y="143" font-size="14">塞恩斯</text>
<text class="d-fg" x="318" y="143" font-size="14">Retired</text>
<rect class="d-none d-accent-s" x="214" y="156" width="192" height="26" rx="5" stroke-width="3"/>
<text class="d-fg" x="224" y="175" font-size="14">阿隆索</text>
<text class="d-fg" x="318" y="175" font-size="14">Retired</text>
<rect class="d-none d-accent-s" x="214" y="188" width="192" height="26" rx="5" stroke-width="3"/>
<text class="d-fg" x="224" y="207" font-size="14">霍肯伯格</text>
<text class="d-fg" x="318" y="207" font-size="14">Retired</text>
<rect class="d-none d-accent-s" x="214" y="220" width="192" height="26" rx="5" stroke-width="3"/>
<text class="d-fg" x="224" y="239" font-size="14">勞森</text>
<text class="d-fg" x="318" y="239" font-size="14">Retired</text>
<text class="d-fg" x="20" y="274" font-size="14">粗外框：狀態欄是 Retired</text>
</svg>
<figcaption>圖：2025 年墨西哥城大獎賽這一場，貝爾曼與阿爾本的本站自訂結果差（同一列的 grid，本站顯示為發車位，減去 position；本文能查的資料源文件未定義）都是 +5；這一場 grid 與 position 都恰為 1 到 20，兩人反方向的車都是 0 台，所以 +5 各可拆成 5 台 grid 比他小、position 比他大的車。資料出自本站賽果資料庫與 Jolpica 賽果快照（2026-10-13 取得），自行計算；狀態取自資料源 status 欄，不代表這些車是被超越或自行退後。本站依資料庫與快照自行整理的示意，非依比例。</figcaption>
</figure>

同一個 +5，組成可以差這麼多。反過來，結果差是 0 也不代表什麼都沒發生。安東內利 grid 6、position 6，結果差是 0。可是 grid 比他小、position 比他大的車有 2 台，反方向也有 2 台。這個 0 是 2 減 2。

阿爾本那 4 台 Retired，在退賽之前有沒有在場上被他超過？表上查不到。貝爾曼那 5 台也一樣：沒有 Retired，不代表都是在場上被他超過。每台車只有一列，沒有中間的紀錄。

阿爾本那 5 台裡有 4 台 Retired，是墨西哥城這一場的樣子，不是通則。同樣的拆法放到 2025 年第 9 站，組成就不一樣：霍肯伯格 grid 15、position 5，結果差是 +10。grid 比他小、position 比他大的 10 台車裡，Retired 是 2 台，反方向是 0 台。本站資料庫在那一場只有 19 列，grid 與 position 各為 1 到 19，拆法照樣成立。

## position 欄有數字，就等於有名次嗎？

有 55 列的 position 欄寫著整數，position_text 欄卻是 R、D 或 W。

範圍是本站資料庫 2025 年賽季的正賽結果，共 479 列，衝刺賽不在內。這 479 列的 position 欄全是整數。R、D、W 對應的 status，依序是 Retired、Disqualified、Did not start。

所以本文寫「從第 X 到第 Y」，只用 position_text 是數字的其餘 424 列。

這 424 列裡，還有 5 列的狀態是 Retired。光看 position_text 還不夠，status 與 laps 要一起看。

## 負的結果差，狀態欄和圈數怎麼讀

墨西哥城這一場，結果差是 −5 的有 4 列。把它們排在一起：

| 車手 | grid | position | position_text | 狀態 | 圈數 |
| --- | --- | --- | --- | --- | --- |
| 漢米爾頓 | 3 | 8 | 8 | Finished | 71 |
| 哈賈爾 | 8 | 13 | 13 | Lapped | 70 |
| 塞恩斯 | 12 | 17 | 17 | Retired | 67 |
| 勞森 | 15 | 20 | R | Retired | 5 |

表：2025 年墨西哥城大獎賽這一場，本站自訂結果差（同一列的 grid，本站顯示為發車位，減去 position；本文能查的資料源文件未定義）為 −5 的 4 列，自行計算。本站依資料庫自行整理的示意，非依比例。

4 列的 −5 一模一樣，狀態與圈數卻有 4 種。

塞恩斯和勞森都是 Retired，寫法卻不同。塞恩斯的 position_text 是數字 17，可以寫成「從第 12 位到第 17 位」，後面要接上 Retired 和 67 圈。勞森只跑了 5 圈，position_text 是 R。這一列不寫成「第 20 名」，−5 也不拿來描述他。

沒跑完為什麼還可能有名次，是分類規則的題目，見[F1 成績表怎麼讀：沒跑完的維斯塔潘，為什麼排第 20 名](/articles/f1-101-classification/)。回到這張表：同樣是 −5，要連同狀態欄和圈數一起讀。

## 換位事件在哪裡看？OpenF1 的 overtakes 怎麼定義

賽果表一列一台車。哪台車在哪一圈換了位，這張表沒有。

想看換位事件，得換一個資料源。OpenF1 有一組獨立的 overtakes 資料。OpenF1 的文件自述為非官方專案（unofficial project），與 Formula 1 公司無關。

它的文件把 overtake 定義成一位車手與另一位車手交換位置。文件寫明「This includes both on-track passes and position changes resulting from pit stops or post-race penalties」。場上超越算，進站造成的換位算，賽後罰則造成的換位也算。文件另外寫到，這份資料只在正賽提供，也可能不完整。

OpenF1 的 overtake 是一次一次的事件。本站的結果差，是 2 個欄位相減的淨值。兩者量的不是同一種東西。

## 常見問題

### 結果差是正數，就代表超了那麼多台車嗎？

這張表讀不出來。把同一列的 grid（本站顯示為發車位）減 position，得到的是本站自訂的結果差，本文能查的資料源文件沒有定義它。本站資料庫的 results 表，也沒有逐圈名次或超車事件欄位。2025 年墨西哥城這一場（20 列的 grid 與 position 都恰為 1 到 20），阿爾本的 +5 對應 5 台 grid 比他小、position 比他大的車，反方向是 0 台，其中 4 台狀態是 Retired。它們退賽前有沒有在場上被他超過，表上查不到。怎麼拆，見上面拆成台數的那一節。

### position 欄有數字，就代表有名次嗎？

不一定。本站資料庫 2025 年賽季正賽 479 列裡，55 列的 position_text 是 R、D 或 W，position 欄照樣有整數。position_text 是數字、能寫「第 X 到第 Y」的是其餘 424 列，其中另有 5 列狀態是 Retired。要寫「第幾名」，先看 position_text，再看狀態與圈數。

### 同一列的 grid 與 position 相同，代表比賽中沒有換位嗎？

這張表看不出來。結果表每台車只有一列，沒有比賽中間的紀錄。2025 年墨西哥城這一場，20 列的 grid 與 position 都恰為 1 到 20。安東內利 grid 6、position 6，本站自訂的結果差（同一列的 grid，本站顯示為發車位，減去 position；本文能查的資料源文件未定義）是 0：grid 比他大、position 比他小的有 2 台，grid 比他小、position 比他大的也有 2 台。

### 不同場比賽的進步名次，可以直接比嗎？

先數那一場有幾列。本站資料庫 2025 年第 9 站賽果只有 19 列，其餘 23 站各 20 列。缺的是排位表裡有、賽果表沒有的斯托爾，原因在本文能查的資料裡查無。列數不同，本站自訂的結果差（同一列的 grid，本站顯示為發車位，減去 position；本文能查的資料源文件未定義）可能的範圍也不同。跨場比較前，先揭露各場的結果列數；本文不把列數不同場次的結果差，直接當成同一尺度。

## 接下來看什麼

- [F1 成績表怎麼讀：沒跑完的維斯塔潘，為什麼排第 20 名](/articles/f1-101-classification/)：為什麼退賽也可能有名次
- [諾里斯這 10 圈四人之中最快，名次卻只有第 7](/articles/f1-101-race-pace-reading/)：名次差之外，圈速要另外看
- [F1 為什麼很難超車：髒空氣，以及 2026 年新增的幫手](/articles/f1-101-overtaking/)：超車為什麼難
- [F1 排位賽怎麼淘汰：三節、兩次砍人、一個發車位置](/articles/f1-101-qualifying/)：發車位置的另一頭

## 資料來源

一手來源：本文沒有引用 FIA 規章條文。

本站資料：

- 本站賽果資料庫（results 表，2025 年正賽），2026-10-13 唯讀查詢；本站 [各站賽果](/results/)
- 本站賽季頁的顯示慣例：grid 為數字時顯示「從第 N 位發車」（本站程式碼，無公開網址）

資料服務文件：

- [Jolpica Ergast 相容 API：2025 年第 20 站賽果](https://api.jolpi.ca/ergast/f1/2025/20/results.json)（快照取得 2026-10-13）
- [OpenF1 文件：Overtakes 一節](https://openf1.org/docs/)（OpenF1 自述為非官方專案，與 Formula 1 公司無關；快照取得 2026-10-13）

二手來源：本文未使用媒體報導。

查證日 2026-10-13。限制：本文能查的資料源文件沒有 grid、position 等欄位的正式定義，結果差（同一列的 grid，本站顯示為發車位，減去 position）是本站自訂的算法。數字限本站資料庫 2025 年正賽，以及第 20 站（墨西哥城）與第 9 站兩場；第 20 站 20 列的 driver_id、grid、position、position_text、laps、status 6 欄，與 Jolpica 快照的對應欄位逐列相同。結果差、台數拆解與 424 列等計數是自行計算，Retired 以資料源 status 欄的字面值計，包含 position_text 為數字的 Retired 列。OpenF1 對 overtakes 的說明取自其文件，本文沒有查它在 2025 墨西哥城這一場的實際資料。
