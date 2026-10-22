# Interlagos 賽道百科：受審草稿交接

選題 `2026-10-22:R1`（18分），slug `f1-interlagos-sao-paulo-grand-prix-guide`。新稿，不計入舊文18/93風格回修。狀態：完整稿、封面與來源已審，未合併／未部署；使用者「部署」後立即「按錯」撤回，因此不構成發布授權。

R1逐年原件矩陣＋Opus歸屬席→R1b全結案→40初稿凍結→Codex與Claude雙R2→60修正→全新上下文冷讀→80編輯→Codex與Claude雙R3 Content/Artifact GO→82只改官方canonical href及來源清單空行→Opus增量GO。指揮／寫作由Codex主session；Agy預設模型quota用盡、無有效內容回覆，異源席改Claude Max訂閱。API呼叫0；未使用API fallback。查核桌 `roundtable/2026-10-22-racing-interlagos`，完整版交付 `Charlie/2026-10-22/racing-interlagos`。

母體42場：1973–77、1979–80、1990–2019、2021–25；排除里約1978/1981–89、1972非計分與2020未辦。42列姓名逐格重核；2021正式桿位Bottas、2022Magnussen（當年FIA政策＋F1實施說明／排位賽報），不從grid=1推pole。2022年度官方pole表誤列Russell、2025官方circuit-facts摘要錯列2021Verstappen均留研究衝突證據，不採為本文正式pole。1990–92同一排位table含預排位P1，不能取第一筆。

2026官方時程查證10/22；本站非Sprint。聖保羅UTC−3轉台北UTC+8快11小時，正賽台北11/9（一）01:00預定開跑，不保證結束。當前賽道4.309km、71圈、305.879km；FIA歷史布局40m限Junção T12至T1煞車點。Prost六場巴西GP勝利只有1990在本站；Michael Schumacher本文42場4勝最高。未核准歷史中文名沿英文，沒有新增譯名。

封面自製數據HTML→PNG，2400×1260，不用官方素材。數值4/3/3/3，母體42、截至2025、Interlagos與只列前四名都明確。兩席R2/R3實看PNG；Codex獨立算SHA，Claude明確未自行算SHA，主席補機械對版。

本機969測試通過（80版156.489秒），82為來源href與空行增量，來源／封面lint另跑，PR CI驗最終commit。草稿排除建置實驗證：沒有新slug文字／頁面輸出；approved.json逐位元未變，draft-exclude明列本slug。Chrome390/1440無整頁溢出、封面2400px載入，三表6/8/36行（含表頭），FAQ/schema5題。9正文站內目標HTTP200；95官方來源目標94個HTTP200、市府curl403但Chrome實際可讀並封存DOM原文。最後單一canonical替換也實抓HTTP200，主文到Next Up前與原頁相同，推薦新聞變動不算本文事實變動。

上線仍須針對本稿取得明確指示。發布前重新查官方2026時程，再依最終SHA簽核、移出draft-exclude、沿既有離線建置／測試與racing-weekly手動部署流程，不做未授權fetch落地賽果。合併／CI不等於部署，正式URL整檔與版面驗證後才可回報上線。本稿尚未操作GSC。

最終對版：
{
  "state": "reviewed unsigned draft; publication not authorized",
  "slug": "f1-interlagos-sao-paulo-grand-prix-guide",
  "article_sha256": "858bf3b188627f9e074851321a0c7f82eccac754877a360da656ffab373a87e6",
  "facts_sha256": "6a9f0f621a40f095fdec9d8f772547091b7a10744e5d47a0c49f7deb1ece3056",
  "cover_png_sha256": "50b17234688fb480f91e1aced01055e5ddb9595df2db8bf373006012007bf346",
  "cover_html_sha256": "62300b21fb419e054edcd069943c6d9fcbced23442616b74b8d9eda5822e2294",
  "base": "d3e59e4e1be0fd58af54102ab670b1dc26886a47",
  "worktree": "/Users/charlie.chien/Github-Repo/racing-tools/.claude/worktrees/interlagos-guide-20261022",
  "approved_json_unchanged": true,
  "explicit_draft_exclusion": true,
  "review_closure": "desk/84-final-closure.md",
  "reviewed_80_plus_href_only_82_delta": true,
  "api_calls": 0,
  "merged": false,
  "deployed": false,
  "gsc_operated": false,
  "old_article_restyle_count_unchanged": "18/93 done;75 remaining"
}
