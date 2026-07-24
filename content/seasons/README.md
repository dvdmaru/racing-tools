# 賽季導言（人工，default-deny）

只為「有故事的季」寫 120–200 字人工導言，放賽季總覽頁（`/seasons/<year>/`）頂部、標題「編輯導言」。
機器每季自動產的「賽季速寫」照舊在下方；這裡的導言是**人工敘事**，走**核准後才上線**的 default-deny 管線，
和文章（`articles/`）共用 `config/approved.json` 的 sha256 綁定機制。

## 檔案

每個有導言的季有一組：

| 檔案 | 用途 |
|---|---|
| `content/seasons/<year>.md` | 導言正文（純文字一段，120–200 字含標點）。sha256 綁定核准。 |
| `content/seasons/<year>.facts.json` | facts pack：導言每個阿拉伯數字一條 claim，值由 sqlite/raw 查出。 |

facts pack 格式：

```json
{
  "season": 2002,
  "claims": [
    {"kind": "champion_points", "driver": "michael_schumacher",
     "text": "以 144 分作收", "value": 144, "verified": true,
     "source": "sqlite: SELECT points FROM driver_standings WHERE season=2002 AND position=1"}
  ],
  "external_history": ["屬常識性歷史背景、不進機械對帳的敘事句（越少越好）"]
}
```

- `verified: true` 的 claim：`scripts/check-season-intros.py` 依 `kind` 內建 sqlite 查詢**重算驗證**。
  支援 kind：`season_exists`、`earliest_season`、`season_rounds`、`champion_points`、`runner_up_points`、
  `champion_wins`、`driver_podiums`、`constructor_wins`、`no_constructor_championship`、
  `clinch_round`、`clinch_remaining`、`tied_before_final`。
- `external_history`：常識性歷史背景句（如「捨分制」「賽事總監制度改組」）。**不進機械對帳**，
  故這些句子**不得攜帶會被對帳的阿拉伯數字**（若攜帶，該數字會在導言正文被抓成裸奔，逼你補 verified claim）。

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
   ```
   全綠才往下走（裸奔數字 / verified claim 對不上 → exit 1）。
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
