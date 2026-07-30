# racing-tools — 賽車數據誌 (racing.twtools.cc)

@RACING「賽車數據誌」F1 資料站的獨立 repo。100% 靜態、server-rendered、零 client fetch
（為被 AI 引用設計，GEO/AEO）。架構 clone 自 baseball-tools（三層：資料 adapter＋JSON
快照 → 數據頁/文章管線 → CF Worker），2026-07-19 建站。

**品牌紅線**：站名/域名不含 F1 字樣（「F1」「FORMULA 1」為 Formula One Licensing 註冊
商標），內文行文指涉性使用可正常提及。零官方素材：不用官方 logo/字體/照片/車隊塗裝視覺，
封面一律自製數據視覺（HTML → headless Chrome PNG），車手肖像不用，賽道圖如自繪需註明
依公開資料重繪。全站 footer 掛非官方 disclaimer。

## 站別 / 部署

- 網址：https://racing.twtools.cc（Cloudflare Workers static-assets，worker `racing-tools`，
  帳號 charlie.chien2019 / `2f123fdee05d453c8a077b6ba541c45d`）。
- 部署：`CLOUDFLARE_API_TOKEN=$(cat ~/.config/cloudflare/foootball-tools-2019.token) CLOUDFLARE_ACCOUNT_ID=2f123fdee05d453c8a077b6ba541c45d npx wrangler deploy -c wrangler-racing.jsonc </dev/null`
  （token 需 `Workers Scripts:Edit`；custom domain 由 wrangler routes 自動建 DNS＋憑證）。

## 資料來源

- **jolpica-f1 API**（`api.jolpi.ca/ergast/f1/`，免金鑰、Ergast 相容）：積分榜、賽曆、賽果。
  rate limit：4 req/s burst、500 req/hr（官方 docs）；每輪抓取約 6-10 request。
- 資料層走 adapter 介面（`scripts/fetch_racing.py` 的 `DataSource`）保留換源彈性；
  每次抓取落 `data/<season>/` JSON 快照＋dated history 當自有歷史庫。
- ⚠️ Ergast schema 陷阱：season-level standings 的 `round` 欄可能指向未跑的下一站，
  「資料截至第 N 站」一律以 `last/results` 的 round 為準。

## 每週更新（不是每日）

- `.github/workflows/racing-weekly.yml`：台北週一 06:00 主更新＋sprint 週末加跑台北六、日
  06:00＋`workflow_dispatch`。非賽週 fetch 比對快照無變化 → 安靜跳過（exit 3，不重建不部署）。
- 需 repo secrets：`CLOUDFLARE_API_TOKEN`／`CLOUDFLARE_ACCOUNT_ID`（jolpica 免金鑰，資料層零 secrets）。
- 手動：`python3 scripts/update-racing.py --deploy`（跑序鐵則見該檔 docstring）。

## 建置

```
python3 scripts/update-racing.py            # fetch → 全站重建（不部署）
python3 scripts/build-articles.py           # 只重建文章+首頁（會整個覆寫 sitemap）
python3 scripts/gen-racing-standings.py     # /standings/（re-merge sitemap）
python3 scripts/gen-racing-calendar.py      # /calendar/ 台北時間賽曆
python3 scripts/gen-racing-results.py       # /results/
```

sitemap 已改為 manifest 合併（M0）：每支生成器只寫自己的 `data/sitemap-parts/<owner>.txt`，
最後由 `python3 scripts/build-sitemap.py` 合併成 `public-racing/sitemap.xml`。
所以**跑序不再是鐵則**，但 `build-sitemap.py` 一定要在所有生成器之後跑一次——
只跑 `build-articles.py` 不會更新 `sitemap.xml`。
（舊版 README 寫的「build-articles 先跑並覆寫 sitemap」已不符現況，2026-07-30 更正。）

需 Python `markdown`、Node/`npx wrangler`、headless Chrome（封面用）。

## 封面

站規：封面一律自製數據視覺，不用官方素材與車手肖像。每張封面畫的是**該篇自己的核心發現**
（例：戰報畫 70 圈的領跑權條帶、藍旗稿畫 11 條旗與對象實際被套圈時刻的落差）。

```
design/covers/base.css        # 共用設計 token（版面、字級、accent #d63a2f）
design/covers/cover-*.html    # 一篇一張，viz 各自定義
design/covers/covers.json     # slug ↔ 封面 HTML 綁定 + 具名例外（default-deny）
python3 scripts/render-covers.py          # 產缺的／比 HTML 舊的（--force 全部重產）
python3 scripts/render-covers.py --check  # 只檢查 PNG 是否比 HTML 舊（僅本機有效，勿進 CI）
python3 scripts/check-covers.py           # 封面可見數字必須都出現在該篇正文
```

`articles/<slug>/cover.png` 一存在，`build-articles.py` 就自動掛上 og:image、
Twitter large card、內文頂圖與 `/articles/` 索引卡圖——不需要改任何設定。

⚠️ **封面裡的數字繞過站上所有既有 gate**（`verify-*` 都掃 markdown，掃不到 PNG）。
`check-covers.py` 就是補這個縫，並且已透過 `tests/test_check_covers.py` 進入部署前擋線。
它只驗「數字字面出現過」，不驗語意——把「早 17 分鐘」寫成「晚 17 分鐘」它照樣會過。

## 草稿 gate

`config/draft-exclude.json` 的 `exclude` 列的 slug 會被 build-articles 跳過
（不進 index/feed/sitemap/首頁/個別頁）。未 cross-check 完的稿子先加進去，審完移除即發布。

## 譯名

`scripts/driver-zh.json`／`team-zh.json` 為全站譯名單一資料源（台灣慣用定版，依據見
`articles/f1-2026-names-glossary/`）。改譯名改這兩檔，全站數據頁自動生效。

## 驗證部署（不要自己挑哨兵字串）

```bash
# 先 build（本站排程是雲端重建後直接 wrangler 部署，產物不 commit 回 main，
# repo 裡那份是舊的），再比對
python3 scripts/verify-deploy.py public-racing/index.html public-racing/standings/index.html
```

拿本機剛 build 好的檔案跟線上**整檔 byte 比對**，不符會印出第一個差異點的前後文。

⚠️ 不要用「grep 一個自己想的關鍵字」驗部署：本站群為此踩過 5 次以上，
每次都是挑到的字串在舊版本裡也存在（CSS class 名、佔位符隊名、404 fallback 頁的品牌字、
上個 commit 已上線的卡片摘要、被 HTML 標籤截斷的字串）→ 假陽性，以為驗過了。
HTTP 200 同樣不能當訊號：deterministic static build 幾乎永遠回 200。
