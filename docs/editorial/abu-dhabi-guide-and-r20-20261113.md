# 阿布達比賽道百科與R20資料落地

Charlie於2026-11-13明示上線，並授權一併修正歷史資料差異、補齊R20，查核通過後直接發布。新文另計，原93篇舊文改寫結案不變。

正文SHA `7bdcb4403ac5865ff6961d6bf8ba3cfeb601fb3344f82215d4d8f492fd9df5d9`，封面2400×1260。原生Codex與Claude訂閱Opus最終R3/R3b均PASS，0未解；Claude照錄主位SHA，非自行計算。發布不改受審正文。17屆2009–2025官方pole/result/grid、2026現行R23收官與五場台北時程、2021改建已核；2026賽果未發生，不寫入歷史表。

## 具名歷史更正
本地driverId=hayje的familyName誤為Lunger，F1官方1977南非同表分別列Brett Lunger與Boy Hayje，確證不是同人。只修正六個物件的familyName為Hayje：entities/drivers.json、standings/driver-1976.json與driver-1977.json、results/1976-12.json與1977-03.json與1977-07.json。ID、名次、車隊、圈數、積分與其餘身分欄不變。保留原_meta，當初快照資訊不偽寫成本次擷取；本次修正證據另存hayje-correction.json與原始備份。

R20補完時另遇8個既有實體stub（只有ID及姓名）的來源缺鍵差異；僅補上游新增鍵，既有鍵不變；手動補缺鍵階段保留順序，接續原同步流程寫回上游完整清單及新實體，因此最終順序跟隨來源（Hayje移回H），不宣稱原序不變。這是來源實體補齊，不宣告現役、正賽starter或正式永久車號。未改歷史漂移守衛、例外、既有golden、測試斷言邏輯或生成器。隨R20已賽，五個未賽/互鏈測試樣本從Interlagos推至vegas；三個精確名單計數55→56/24→25，退賽年代截至站次R19→R20；原assert與exact-set保留。R20首賽Rafael Camara依法定DB集合納入查核名單與slug（英文fallback）；新增R11基線全0的golden，既有值與as_of全保留。本輪整體R20落地授權涵蓋此必要擴編，未冒稱使用者另有逐值裁決。

沿既有refresh-f1-current更新2026 R20及全庫檔，歷史區段保護全開。原流程已寫R20後於entities階段中止，因此明確續跑原sync_whole_db_files(...,[20])及rebuild/invariants，而非以『已有檔跳過』假稱完整成功。

## 證據與發布
完整證據：CoWork/Charlie/2026-11-13/racing-abu-dhabi-guide；草稿HANDOFF/final保持歷史，以最終RELEASE-REPORT、PUBLISHED-HANDOFF及release-state為發布狀態。發布前需全套測試、兩遍建置、獨立資料審查與Claude訂閱發布差異審查。合併/CI不等於已部署；正式驗收後才回報上線。IndexNow通知與Google收錄分開，未授權代操作GSC。
