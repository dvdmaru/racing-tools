# 維斯塔潘巴西站格位歷史對照：受審草稿

2026-11-10（台北）。選題台2026-11-10:R1-18，cross-check。新文另計；舊文93/93結案狀態不變。

## 交付狀態
正文、2400×1260自製封面與本機正式模板預覽已備妥；原生Codex native-final及Claude訂閱Opus claude-r3均PASS，0未解finding。受審正文SHA：9c650dd1d655354011db5ca06972ea00200e0baf45ca470824bb0671c91174ed。
Claude R3照錄主位提供SHA，未自行執行hash；主位於呼叫前後自行計算相同SHA。不得宣稱Claude獨立算hash。

## 查核修正
- 官方Brazil P21→P2、71圈、+14.602；FIA Doc33罰退30格與Doc59最終P21交叉。
- 21−2=19僅兩欄差，不稱實際淨升19／19次超車；前方Bottas P17 DNS，Perez P22有起跑。未擅自替換為實際淨升18。
- 6筆歷史官方雙表＋本次Brazil；P20含、排除Indy500/pitlane/Sprint，表只稱案例對照，非最新全史完整次數。
- 表頭官方發車表列車數，不當實際starter；Brazil22格/21實際起跑。1985Australia官方賽果漏DSQ那列，不由結果列數推starter。
- Monza Antonelli P19奪冠不屬P20+；未採未核中文名（Watson/Laffite/Montoya維持原文）。
- 去掉終點差距反推過程句、方法學重複與怪句，新增FIA實記開局P13、lap5P8、lap38P2、lap45二停後P5再以P2完賽。
- ClaudeR2的以下/上表指向、正式聖保羅名稱與三次重述均修正；不相關pitlaneP3例刪除。

## 證據與限制
81項內容/封面/來源/引文/管線測試OK；no-causal、來源格式、譯名、article-gate及封面數字/主張錨定通過，18個官方來源HTTP200。
390/1440預覽頁寬等於視窗寬、單一H1、Article/4FAQ、封面載入、7資料列通過；手機表格局部可左右捲動、有鍵盤焦點。目檢封面、手機開場與桌面表格，非全頁逐像素/實機測試。預覽去GA/版位讀取且noindex；正文模板與樣式沿用站內程式，未改生成器。
資料庫1950–2026共26291結果列，但2026只至R19；新Brazil用官方補證，未更新賽果DB。R20機械reconcile尚無紀錄，模板顯示『尚未複查』，不冒稱資料層已落地。正式發布時應fetch核現況，依既有每站落地與簽核程序，不偽造複查記錄。
Claude走claude.ai訂閱登入，移除API/key/provider環境設定，API 0；第一次背景過長失敗原紀錄保留，獨立唯讀模式重試成功。冷讀使用訂閱席，不跑會走API的cold-read.py。

## 發布邊界
未改approved.json（與origin/main逐位元組相同）；新slug在draft-exclude，public-racing無新頁。未提交/推送/PR/合併/部署/IndexNow/GSC。
分支codex/racing-verstappen-brazil-20261110；基準2c68ec206bacdfd0dcb181a6656db699eb7a3699；復用既有managed工作區，不新建worktree/clone。待Charlie明示發布。
