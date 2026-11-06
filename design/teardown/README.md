# teardown：可拆開的 3D 示意模型（原型）

新手村文章的互動 3D 補充。

| 篇 | 文章 | 原始碼 | 狀態 |
|---|---|---|---|
| 1 | `articles/f1-101-power-unit`（2026 動力單元） | `pu-2026-*` | 已上線（PR #138）：`/articles/f1-101-power-unit/pu-3d` |
| 2 | `articles/f1-101-active-aero`（2026 主動空力） | `aero-2026-*` | 接進文章（`/articles/f1-101-active-aero/aero-3d`） |

工具是 Claude Code skill [elvarofficial/teardown](https://github.com/elvarofficial/teardown)（MIT），
釘在 commit `a91262ac1109051e014662d42ecb0b7bc1f113b1`（2026-10-31），裝在 `~/.claude/skills/teardown`
（依賴 three 0.186.1、esbuild 0.28.1、playwright 1.58.2，`npm ci` 照 lockfile 裝）。

## 檔案

| 路徑 | 內容 |
|---|---|
| `build.mjs` | 打包器（改寫自 skill 的 `sims/build.mjs`）：內嵌站上的 Chakra Petch、中文走系統字型、`lang="zh-Hant"`、`noindex` |
| `fonts/` | Chakra Petch 拉丁子集 500／600／700（SIL OFL，Google Fonts） |
| `pu-2026-shared/kin.js` | 數學，沒有 three.js：規章數字、示意一圈、能量策略、曲柄連桿。載入時自我檢查規章數字 |
| `pu-2026-shared/pu.js` | 幾何：六類受管制元件＋傳動，實體／X 光／剖開／爆炸圖、聚焦單一零件 |
| `pu-2026-shared/stage.js` | 攝影棚、燈光、陰影、GTAO |
| `pu-2026-shared/console.js` | 中文控制台（專有名詞英文以全形空格接在後面，同生成頁慣例） |
| `pu-2026-shared/film.js` | 導覽腳本（一圈 45.5 秒）與 `render(t)` |
| `pu-2026-shared/live.js` | 互動頁：按鈕、拖曳、滾輪、閒置自動導覽 |
| `pu-2026-live/`、`pu-2026-film/` | 兩個入口；`pu-2026-smoke/` 是只有 3D 的幾何檢查頁 |

## 數字的來源

畫面上的規章數字只用文章已有、附條號的：MGU-K 350 kW（C5.2.7）、功率曲線（C5.2.8，含 Overtake 曲線）、
電量窗口 4 MJ（C5.2.9）、每圈回充上限 8.5 MJ（C5.2.10）、一季可用數量（運動規章 B8.2.2＋B8.2.3）。
一圈的車速、哪裡煞車、回收功率都是示意，畫面上標「示意」。`kin.js` 的 `SELF_CHECK` 在載入時驗規章數字。

模型是「依公開資料重繪的示意模型」：通用造型、零塗裝、零標誌，比例與零件位置不是實物。

### 主動空力（`aero-2026-shared/`）

結構照動力單元：`kin.js`（規則，沒有 three.js）、`car.js`（幾何）、`stage.js`、`console.js`、`film.js`、`live.js`。
一圈直接 import 動力單元的 `LAP`／`lapAt`，兩頁的車速對得上。

規則寫成一支 `stepAero(a, τ, dt, {enabled, lowGrip, fail})`，影片的整圈表與互動頁的即時累加共用：
三種狀態（B7.1.1 b、c、d）、已啟用通知（B7.1.2 a）、只在啟動區內部署（C3.10.10 w；C3.11.6 j）、
低抓地只准前翼（B7.1.2 b）、切換 ≤ 400 毫秒（C3.10.10 o；C3.11.6 d）、兩個位置（C3.10.10 t；C3.11.6 h）、
失效回 Corner Mode（C3.10.10 v；C3.11.6 i）。`SELF_CHECK` 對四種條件各跑一整圈驗這些條。
示意（畫面標「示意」）：三個啟動區的位置與長度、切換時間 300 毫秒、失效後到該區結束前停在 Corner。
**規章沒有攻角、阻力、下壓力的數字，畫面上一律不顯示**；翼片角度只是讓眼睛看得出兩個位置。

```
node design/teardown/build.mjs design/teardown/aero-2026-live design/teardown/aero-2026-film
```

## 指令

```
# 打包（輸出到目前資料夾的 teardown-out/dist/）
node design/teardown/build.mjs design/teardown/pu-2026-live design/teardown/pu-2026-film

# 截圖與錄影（用 skill 的 capture；CHROMIUM 可指向本機任一完整的 Chrome for Testing）
node ~/.claude/skills/teardown/sims/capture.mjs pu-2026-film --size 1600x900 --dpr 1 \
  --stills beats --timeline design/teardown/pu-2026-film/timeline.json --cols 3 --out teardown-out/beats.png
node ~/.claude/skills/teardown/sims/capture.mjs pu-2026-film --size 1600x900 --dpr 1.2 --out teardown-out/tour.mp4
```
