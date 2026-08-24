# 賽季導言（人工，default-deny）

只為「有故事的季」寫 120–200 字人工導言，放賽季總覽頁（`/seasons/<year>/`）頂部、標題「編輯導言」。
機器每季自動產的「賽季速寫」照舊在下方；這裡的導言是**人工敘事**，走**核准後才上線**的 default-deny 管線，
和文章（`articles/`）共用 `config/approved.json` 的 sha256 綁定機制。

## 檔案

每個有導言的季有一組：

| 檔案 | 用途 |
|---|---|
| `content/seasons/<year>.md` | 導言正文（純文字一段，120–200 字含標點）。sha256 綁定核准。 |
| `content/seasons/<year>.facts.json` | facts pack：導言每個阿拉伯數字與順位詞一條 claim，值由 sqlite 查出、並以 `anchors` 綁到正文位置。 |

facts pack 格式：

```json
{
  "season": 2002,
  "claims": [
    {"kind": "champion_points", "driver": "michael_schumacher",
     "text": "以 144 分作收", "value": 144, "verified": true,
     "anchors": ["以 144 分"],
     "source": "sqlite: SELECT points FROM driver_standings WHERE season=2002 AND position=1"}
  ],
  "non_statistical_tokens": [],
  "external_history": ["屬常識性歷史背景、不進機械對帳的敘事句（越少越好）"]
}
```

- `verified: true` 的 claim：`scripts/check-season-intros.py` 依 `kind` 內建 sqlite 查詢**重算驗證**。
  支援 kind（v2）：
  - 賽季層：`season_exists`、`earliest_season`、`earliest_race`、`season_rounds`、
    `no_constructor_championship`
  - 車手層：`champion_points`、`runner_up_points`、`champion_wins`、`driver_position`、
    `driver_podiums`、`race_finish_position`（需 `round`）、`career_titles`、`rank_before_final`
  - 車隊層：`constructor_wins`
  - 冠軍鎖定：`clinch_round`、`clinch_remaining`、`clinch_from_end`
  - 同分：`tied_before_final`、`tied_position`（真並列才過）、`countback_order`（同分循序，
    必須由 countback 重算解釋得出宣稱順序）
- **實體綁定必填**：車手層 kind 一定要寫 `driver`、車隊層一定要寫 `constructor`、同分類要寫 `drivers`。
  漏寫＝直接判錯（不是「有寫才驗」）。
- `anchors`：**正文逐字片段**清單。導言中每個阿拉伯數字與每個順位詞（第 N／倒數第 N／並列第 N）
  都必須落在某條 claim 的 anchor 區間內，且該 claim 的值要等於那個數字／順位。沒被 anchor 綁到＝判錯；
  綁到值不對的 claim 也判錯（這是「數字被移植到別的主張」的抓手）。
  順位詞另有修飾語規則：`倒數第 N` 只接受 `clinch_from_end`，`並列／同列第 N` 只接受 `tied_position`。
  正文只要出現同分字眼（並列／同列／同分／相同積分），pack 就必須有一條通過重查的同分類 claim。
- `non_statistical_tokens`：英數混排 token 的具名白名單（如 `F1`、`V10`、`MP4`）。夾在這類 token 裡的
  數字不是統計值，未具名一律判錯——避免「F1 的 1」被某條值為 1 的無關 claim 放行。
- `external_history`：常識性歷史背景句（如「捨分制」「賽事總監制度改組」）。**不進機械對帳**，
  故這些句子**不得攜帶會被對帳的阿拉伯數字**（若攜帶，該數字會在導言正文被抓成裸奔，逼你補 verified claim）。

### 對帳器 v2 的三層 provenance（2026-08-23，補 SOL-VERDICT-5 的 oracle 循環引用）

standings 型的值不再只回讀 `driver_standings`（1976 該表曾存 66／64，錯值與錯 oracle 互相印證）：

1. **L1 斷言**：`db.sqlite` 必須是套過 `data/f1/standings-overrides.json`（`by=charlie`）的 L1；
   讀到 L0 raw 值就判錯（先跑 `build-f1-db.py`）。
2. **逐站重算**：另用 `results`＋`sprint_results`＋`data/f1/scoring-rules.json` 的捨分規則重算
   points／wins／順位（含 countback），與 standings 對不上就判錯。
3. **外部快照**：`data/f1/standings-crosscheck-report.json`（en.wikipedia，coverage 1950–1990）。
   claim 讀到的欄位若在該報告有 diff 而未被已核准 override 解決 → 判錯。
   **1991 年起沒有外部快照**，對帳報告會逐季標示「⚠ 無外部快照（standings 單一來源）」——
   那不是全綠的一部分，是誠實聲明。

### 對帳器 v3 的三道修補（2026-08-24，補導言第二批實戰暴露的 H5／H6／H7）

1. **H5 除名建模**：`SeasonOracle.rank()` 會從 `driver_standings.position_text` 讀**分類標記**
   （只讀標記，不讀 points／position 的值，故不是 H1 的值循環引用——「賽季結束後遭年度除名」
   是治理事實，`results` 層沒有這個訊號）。認得的標記只有三類：數字、`-`（無積分未列榜）、
   `D`／`E`（年度除名）；其餘一律判錯。除名者不佔年度順位，其後車手往前遞補——1997 舒馬克
   的 78 分不再擋著 Frentzen 的官方 P2 42 分。
   **射程界線**：只影響年度最終排名。`rank_before_final`（末站前的即時累計榜）與 clinch 的
   對手集合**不套用**，因為 1997 的除名是賽季結束後才發生的。
2. **H6 clinch 不准有事後之明**：對手的理論上限一律用**剩餘排程站次**封頂，不再看「他之後
   實際還有沒有出賽」。唯一例外是 `SEASON_ENDING_EVENTS`（寫在 checker 裡的具名清單，每筆
   附理由與來源）：在該站賽事當下已身故／確定退出者自該站起不再計，而且只有評估到那一站
   之後才適用（更早的站次不得預知）。
   ⚠️ 為什麼要人工具名而不是讀 `results.status`：全庫只有 3 列 `Fatal accident`，1961
   von Trips 與 1978 Peterson 的 status 都只是泛用的 `Accident`，與傷退後復出者同字串。
3. **H7 clinch 同分套 countback**：判準由 `floor > 對手上限` 改成 `floor >= 對手上限`，同分時
   比 countback。對手要打到上限就得把剩餘站次全拿，所以他的 countback 用**理論最佳**（現有
   完賽分布 ＋ 剩餘站次各記一勝）；冠軍側用保底情境。完全同階＝分不出先後＝不算鎖定。
   1957 方吉歐因此正確落在第 6 站德國站（舊值第 7 站）。

三道修補後 28 篇已核准導言維持全綠、零豁免。28 季的 clinch 只有三季改變，且三季的 facts pack
都沒有 clinch claim（1957／1978 的鎖定站次語意已在第二批依裁決刪除）：

| 賽季 | 冠軍 | v2 | v3 | 原因 |
|---|---|---|---|---|
| 1957 | Fangio | R7 | **R6**（德國站） | H7 同分 countback |
| 1978 | Andretti | R13 | **R14**（義大利站） | H6 事後之明 |
| 1988 | Senna | R16 | **R15**（日本站） | H7 同分 countback |

三個新值都與史實相符（方吉歐在紐柏林封王、Andretti 在蒙札封王、Senna 在鈴鹿以該季第 8 勝封王），
是 v3 的獨立佐證，不是漂移。

⚠️ 全綠只代表「數字與順位這兩層沒抓到錯」。非數字語意主張（因果、心理狀態、「首位／唯一／最」類
全稱詞、事件順序）機械層驗不了，仍須對抗式人工查核。

## 寫作站規

- 繁體中文、全形標點、數字阿拉伯化 + 盤古之白（中英/中數之間空格）。
- 譯名**只用四張 approved 表**（`driver-zh.json`／`team-zh.json`／`race-zh.json`／`circuit-zh.json`）
  + phase0 seed 的值；查無定版譯名者**用原文**（如 Fangio、Prost、Alfa Romeo）。嚴禁自譯人名/隊名。
- 不用「見證了」「堪稱」「值得一提」等套話、不用 em dash、避免 AI 腔（rule of three、空泛總結）。
- 每個數字與事實主張都要對得到 facts pack 的 claim。
- 中立紀律（爭議季）：只寫事實層句子、不評對錯、爭議雙方都不背書。

## 流程（Charlie 審 → 核准 → 上線）

1. **主寫**：Claude 依 facts pack 寫 `<year>.md` 草稿（草稿**不進** `approved.json`）。
2. **機械對帳**：
   ```bash
   python3 scripts/check-season-intros.py            # 掃全部；或指定年份 ... 2002 2021
   python3 scripts/check-season-intros.py --scaffold 2002   # 列出還沒被 anchor 綁到的數字／順位詞
   ```
   全綠才往下走（裸奔數字 / 未綁定數字或順位詞 / verified claim 對不上 → exit 1）。
   `--scaffold` 只是把缺口與候選 kind 印出來給人對位，**不會自動幫你寫 anchor**——實體歸屬要人判。
3. **Charlie 審稿 / 改稿**：直接改 `<year>.md`。改完再跑一次 step 2（改了字 sha 就變，核准要重來）。
4. **核准**（Charlie 說「核准 2002」時）——migration 把當下 sha256 寫進 `config/approved.json`：
   ```bash
   python3 scripts/approve-season-intro.py 2002        # 先自動對帳，過了才寫入
   python3 scripts/approve-season-intro.py 2002 --dry-run   # 只預覽會寫入的條目
   ```
   會新增一筆 `{"slug": "season-intro-2002", "article_sha256": "<sha>", "approved_by": "charlie", ...}`。
5. **重生**：
   ```bash
   python3 scripts/gen-racing-seasons.py --all --rounds-for 2002 2026
   ```
   `render_season` 只在「導言檔存在**且** sha256 在 `approved.json` 內」才渲染導言區塊。

## default-deny 保證

- **未核准 / 檔案被竄改（sha 不符）→ 賽季頁與現狀 byte-identical**（導言區塊回空字串，不動任何其他位元）。
- 核准者不應與產稿者相同（比照文章 gate 精神；`approved_by` 記名存證）。
- 移除 `approved.json` 內某季條目 → 下次重生該季頁自動退回無導言狀態。
