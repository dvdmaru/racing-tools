#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regen-encyclopedia.py — 百科線 M7：選擇性重生（facts-hash / per-page 指紋）。

週更百科步驟只重生「受新資料影響的頁」——歷史頁（1950–當季前一年）凍結不重寫（mtime 不動）。

機制＝per-page 輸入指紋：每一頁（或頁群）對它所讀的 db.sqlite 切片算 SHA-256，存
data/f1/page-fingerprints.json。跑時重算現況指紋 vs 上次：
  - 指紋不變 → 完全不呼叫該頁的生成器 → 檔案零重寫（byte-identical、mtime 不動）。
  - 指紋變了 → 重生該頁群。
--full＝忽略指紋全量重生（首次公開全站建置、或指紋檔遺失時）。

頁群粒度：
  - 賽季 y：該年 results/sprint/qualifying/standings/races/status 切片 → _render_one_season(y)。
    當季（有新賽果）→ 指紋變 → 總覽＋seed 子頁＋（新）分站頁全部重生；歷史季指紋恆定 → 跳過。
  - 車手 did：該人 results＋driver_standings＋所涉賽季 status 切片 → gen_driver(did)。
  - 車隊 cid：該隊正賽明細＋已完成季冠軍榜＋身分欄切片 → gen-racing-constructors.py。
  - 賽道 cid：該賽道承辦分站＋每站冠軍＋身分欄＋兩份 roster 與三張譯名表切片
    → gen-racing-circuits.py。
  - /seasons/ 索引：全年指紋的合成 → 任一年變則重生。/drivers/ 索引：雙 roster 聯集 53 人指紋的合成。
    /constructors/ 索引：11 隊指紋＋2026 積分榜名次的合成。

呼叫端（update-racing.py 的百科段）在 published 且有新資料時：依序跑車手與車隊的前置三 gate
（invariants／verdicts／golden as_of），全過才 selective_regen；回傳的變更頁 URL 供 IndexNow。
"""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FINGERPRINTS = ROOT / "data" / "f1" / "page-fingerprints.json"
CONSTRUCTOR_ROSTER = ROOT / "data" / "f1" / "constructor-crosscheck-report.json"
DRIVER_ROSTER = ROOT / "data" / "f1" / "crosscheck-report.json"


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


dr = _load("gen_racing_drivers", "gen-racing-drivers.py")
# 共用 dr 的模組圖（單一 gs/fs/rc/p0/il 實例；PUB 重導在測試裡才一致）
gs, fs, rc, p0, il = dr.gs, dr.fs, dr.rc, dr.p0, dr.il
cg = _load("gen_racing_constructors", "gen-racing-constructors.py")
# constructor owner 也綁到同一份模組圖，避免測試／管線的 PUB 與資料連線分岔。
cg.gs, cg.fs, cg.rc, cg.p0, cg.il = gs, fs, rc, p0, il
ci = _load("gen_racing_circuits", "gen-racing-circuits.py")
# 賽道 owner 同樣綁到同一份模組圖（PUB／db 連線不分岔，測試 patch PUB 才會一致）。
ci.gs, ci.fs, ci.rc, ci.p0 = gs, fs, rc, p0
BASE = rc.BASE
CHAMPION_IDS = dr.CHAMPION_IDS
ACTIVE_IDS = dr.ACTIVE_IDS
DRIVER_IDS = dr.DRIVER_IDS
# 車隊頁名單的單一來源＝canonical constructor crosscheck report。
CONSTRUCTOR_IDS = cg.CONSTRUCTOR_IDS
# 賽道頁名單的單一來源＝append-only slug 註冊表（與 db circuits 表由 ci.gate_registry 對齊）。
CIRCUIT_IDS = ci.CIRCUIT_IDS
FIRST_YEAR, LAST_YEAR = gs.FIRST_YEAR, gs.LAST_YEAR

# 會往磁碟寫頁面的模組全集（＝selective_regen 一次全量重生會碰到的 owner）。
# ☠️ 2026-09-03：測試把 PUB 逐一列名重導到 tmp，漏了 ci，於是每跑一次全套測試就把
# 79 個 circuits 頁**寫進版控裡的 public-racing/**。內容剛好一樣時 git status 看不出來
# （得比 mtime 才抓得到），所以它安靜活了很久；一旦產物與生成器有落差，跑測試會把落差
# 就地「治好」，讓 drift gate 失去意義。名單放在這裡＝新增 owner 時只有這一處要改。
PAGE_OWNERS = (rc, gs, p0, dr, cg, ci)

# 輸出根目錄註冊表（單一來源）：名稱 → 取得「現在實際會寫到哪」。
# ⭐ pub_override 依它重導、回歸測試依它決定要驗哪些目錄——**新增輸出目標只加在這裡一處**。
# ☠️ 為什麼要有這張表：同一份「輸出目標清單」在程式與測試各手寫一次，就會有一邊漏。
# 2026-09-03 同一病灶已三犯（測試重導 PUB 漏 ci／publish 寫 4 個 part 而還原清單只有 3 個／
# 探針掃描範圍手寫成只有 public-racing）。斷言若自己列舉目錄，它就是第四份手寫清單。
OUTPUT_ROOTS = {
    "pages": lambda: rc.PUB,
    "sitemap_parts": lambda: rc.sitemap_parts_dir(),
}


@contextlib.contextmanager
def pub_override(target):
    """把**所有輸出根目錄**導到 target 底下，離開時還原。測試一律用它，不要自己列名單。

    ☠️ 2026-09-03：這裡有兩個輸出根目錄，不是一個——
      ・頁面 → 各 owner 的 PUB（`target` 本身）
      ・sitemap part → `rc.sitemap_parts_dir()`（正式路徑 data/sitemap-parts/，**在 PUB 之外**）
    早一版只導 PUB，於是 `selective_regen(publish=True)` 仍把四個 part 寫進版控目錄；
    其中 seasons／drivers／constructors 被測試自己還原（只留 mtime churn），circuits 因為
    不在那份手寫還原清單裡而被永久改寫。⇒ **加新的輸出目標時要加在這裡**，
    不要在測試裡各自 save/restore。
    """
    orig = [m.PUB for m in PAGE_OWNERS]
    orig_parts = rc.SITEMAP_PARTS_OVERRIDE
    for m in PAGE_OWNERS:
        m.PUB = target
    rc.SITEMAP_PARTS_OVERRIDE = pathlib.Path(target) / "_sitemap-parts"
    try:
        yield target
    finally:
        for m, p in zip(PAGE_OWNERS, orig):
            m.PUB = p
        rc.SITEMAP_PARTS_OVERRIDE = orig_parts


# ---------- 指紋（db.sqlite 切片 → SHA-256） ----------

def _h(obj):
    """對任意可 JSON 化物件算決定性 SHA-256（sort_keys、無空白差異）。"""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _file_sha(path):
    p = pathlib.Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def _zh_sha256(*names):
    """把譯名表的內容 sha 切進頁面指紋。

    ☠️ 為什麼非有不可：譯名只存在 scripts/*-zh.json，**不在 db.sqlite 裡**。改一個譯名，
    db 一個 byte 都不會動 → db 切片的 sha 不變 → 選擇性重生判定該頁「沒變」→ 頁面上
    印的還是舊譯名，而且全綠、沒有任何一層會叫。這正是 gate 靜默腐蝕的形狀。

    只切「這個頁群真的會渲染」的那幾張表（default-deny）：多切一張＝那張表一改就白刷
    一整個頁群，少切一張＝那張表一改就靜默 stale。哪張表會被渲染以生成器實際讀的
    rc.*_ZH 為準，不憑印象。
    """
    return {name: _file_sha(SCRIPTS / name) for name in names}


def _season_intro_slice(year):
    """季頁導言輸入：原始檔 sha＋目前是否通過 approved.json 綁定。"""
    path = gs._intro_path(year)
    actual = _file_sha(path)
    entry = gs._load_approved().get(gs.INTRO_SLUG.format(year=year), {}) if actual else {}
    return {"sha256": actual, "approved": bool(actual and entry.get("article_sha256") == actual)}


def _season_override_slice(year):
    """季頁 renderer 的非 DB 輸入：該季具名裁決。

    R1 曾先用修正後 DB 算 fingerprint、但季頁仍繞回 raw，導致「指紋新、HTML 舊」。
    只在實際有 Charlie 裁決的年份加入此 slice：受影響歷史季會失效重生，無裁決的
    當季（2026）與其他凍結頁不白刷。
    """
    fields = ("table", "season", "entity_id", "field", "raw_value", "value", "by")
    rows = [{key: item[key] for key in fields}
            for item in gs._ADJUDICATED_OVERRIDES
            if item.get("by") == "charlie" and int(item.get("season", -1)) == year]
    if not rows:
        return []
    return {"renderer": "preserve-raw-json-type-v1",
            "rows": sorted(rows, key=lambda row: (row["table"], row["entity_id"], row["field"]))}


def _year_slice(con, year):
    """賽季 year 的頁面所讀的 db 切片（決定性 tuple 序列）。

    ORDER BY 一律用唯一鍵（results/sprint/qualifying 用代理主鍵 id；standings 用實體 id；
    races 用 round）——避免用 nullable/非唯一欄（如 position）排序造成指紋抖動。

    ⚠️ 譯名表 sha 也切進來（2026-08-24 補上，原本是洞）：賽季總覽／車手分頁／車隊分頁
    都印車手、車隊與分站三種譯名（gen-racing-seasons.py 的 DRIVER_ZH／TEAM_ZH_BY_ID
    ＋ rc.race_pair／rc.race_zh），改譯名時 db 一個 byte 都不會動，不切就是 415 頁靜默 stale。

    切三張、不切 circuit-zh.json：以生成器實際讀的東西為準逐張查過——
    ・driver-zh.json：`zh_driver()`（積分榜、各站冠軍、退賽明細）→ 切。
    ・team-zh.json：`zh_team()`（車隊榜、車手所屬車隊）→ 切。
    ・race-zh.json：`rc.race_pair()`／`rc.race_zh()`（各站冠軍表、車手／車隊分頁的逐站列）
      → 切。（PR #59 的反向測試曾假設「race-zh 沒有任何百科頁群渲染」，該前提對賽季線
      是錯的：2024 賽季總覽 HTML 裡就有「澳洲站」，本次一併更正該測試。）
    ・circuit-zh.json：整份 gen-racing-seasons.py 只有 `render_round()` 用 `rc.circuit_pair()`，
      賽季總覽與兩種分頁一個賽道譯名都不印（實測 2024 總覽 HTML 對 circuit-zh 全表零命中）
      → **不切**，改在 compute_fingerprints 的分站頁指紋上單獨掛，免得改一個賽道譯名
      就白刷整條賽季線。
    """
    slc = {}
    for tbl, cols, order in (
        ("results",
         "id, round, position, position_text, points, driver_id, constructor_id, grid, laps, status, number",
         "id"),
        ("sprint_results",
         "id, round, position, position_text, points, driver_id, constructor_id, grid, laps, status, number",
         "id"),
        ("qualifying",
         "id, round, position, driver_id, constructor_id, q1, q2, q3, number", "id"),
        ("driver_standings",
         "position, position_text, points, wins, driver_id, constructor_ids", "driver_id"),
        ("constructor_standings",
         "position, position_text, points, wins, constructor_id", "constructor_id"),
        ("races", "round, name, date, circuit_id, url", "round"),
    ):
        rows = con.execute(
            f"SELECT {cols} FROM {tbl} WHERE season=? ORDER BY {order}", (year,)).fetchall()
        slc[tbl] = [tuple(r) for r in rows]
    st = con.execute("SELECT status FROM seasons WHERE year=?", (year,)).fetchone()
    slc["status"] = st[0] if st else None
    slc["season_intro"] = _season_intro_slice(year)
    slc["zh_sha256"] = _zh_sha256("driver-zh.json", "team-zh.json", "race-zh.json")
    overrides = _season_override_slice(year)
    if overrides:
        slc["standings_overrides"] = overrides
    return slc


def _driver_slice(con, did):
    """車手 did 的頁面所讀的 db 切片（生涯 results＋逐季榜＋所涉季 status＋身分欄）。"""
    results = con.execute(
        "SELECT season, round, position_text, points, constructor_id, id "
        "FROM results WHERE driver_id=? ORDER BY season, round, id", (did,)).fetchall()
    standings = con.execute(
        "SELECT season, position, position_text, points, wins, constructor_ids "
        "FROM driver_standings WHERE driver_id=? ORDER BY season", (did,)).fetchall()
    seasons = sorted({r[0] for r in results})
    status = con.execute(
        "SELECT year, status FROM seasons WHERE year IN (%s) ORDER BY year"
        % (",".join("?" * len(seasons)) or "NULL"), seasons).fetchall() if seasons else []
    meta = con.execute(
        "SELECT given_name, family_name, nationality, dob, url, code, permanent_number "
        "FROM drivers WHERE driver_id=?", (did,)).fetchone()
    return {"results": [tuple(r) for r in results],
            "standings": [tuple(r) for r in standings],
            "status": [tuple(r) for r in status],
            "meta": tuple(meta) if meta else None,
            # 車手頁 constructor chips 的可連名單來自這份 roster；其內容變更必須使頁面 stale。
            "constructor_roster_sha256": _file_sha(CONSTRUCTOR_ROSTER),
            # 車手頁印兩種譯名：車手自己的（il.resolve_zh → driver-zh.json）與
            # 車隊 chips 的（rc.TEAM_ZH → team-zh.json）。賽道／分站名不印，故不切那兩張。
            "zh_sha256": _zh_sha256("driver-zh.json", "team-zh.json")}


def _constructor_slice(con, cid):
    """車隊頁實際讀取的正賽明細、已完成季冠軍榜、參賽季 status 與身分欄。"""
    results = con.execute(
        # number 參與 constructor_career_db 的頒獎台去重鍵，漏切會讓 number 修正後頁面靜默 stale。
        "SELECT season, round, position_text, number, id FROM results "
        "WHERE constructor_id=? ORDER BY season, round, id", (cid,)).fetchall()
    standings = con.execute(
        "SELECT season, position, points, wins FROM constructor_standings "
        "WHERE constructor_id=? ORDER BY season", (cid,)).fetchall()
    done = dict(con.execute("SELECT year, status FROM seasons").fetchall())
    meta = con.execute(
        "SELECT name, nationality, url FROM constructors WHERE constructor_id=?", (cid,)).fetchone()
    return {
        "results": [tuple(r) for r in results],
        "champ": [(r[0], r[2], r[3]) for r in standings
                  if r[1] == 1 and done.get(r[0]) == "completed"],
        "status": [(year, done.get(year)) for year in sorted({r[0] for r in results})],
        "meta": tuple(meta) if meta else None,
        # 車隊頁只印車隊自己的譯名（approved_zh → rc.TEAM_ZH → team-zh.json）：
        # 頁上沒有任何車手名或賽道名，所以只切這一張。
        "zh_sha256": _zh_sha256("team-zh.json"),
    }


def _circuit_slice(con, cid):
    """賽道頁實際渲染的東西：身分欄、承辦分站（含是否已舉行）、每站冠軍的車手／車隊名，
    加上決定「哪些連結連得出去」的兩份 roster 與三張譯名表。

    ⚠️ 譯名表的 sha 也切進來：賽道頁把賽道／車手／車隊三種名字都印在頁上，改譯名時
    db 一個 byte 都不會動，不切就會靜默 stale。車手頁、車隊頁與賽季／分站線 2026-08-24
    已補上同一道（原本都是既有的洞），全站五個頁群至此一致。
    """
    meta = con.execute(
        "SELECT name, locality, country, url FROM circuits WHERE circuit_id=?", (cid,)).fetchone()
    races = con.execute(
        "SELECT ra.season, ra.round, ra.name, "
        "       (SELECT count(*) FROM results x WHERE x.season=ra.season AND x.round=ra.round) "
        "FROM races ra WHERE ra.circuit_id=? ORDER BY ra.season, ra.round", (cid,)).fetchall()
    winners = con.execute(
        "SELECT r.season, r.round, r.driver_id, r.constructor_id, "
        "       d.given_name, d.family_name, c.name "
        "FROM results r JOIN races ra ON ra.season=r.season AND ra.round=r.round "
        "LEFT JOIN drivers d ON d.driver_id=r.driver_id "
        "LEFT JOIN constructors c ON c.constructor_id=r.constructor_id "
        "WHERE ra.circuit_id=? AND r.position_text='1' "
        "ORDER BY r.season, r.round, r.id", (cid,)).fetchall()
    return {
        "meta": tuple(meta) if meta else None,
        "races": [tuple(r) for r in races],
        "winners": [tuple(r) for r in winners],
        "driver_roster_sha256": _file_sha(DRIVER_ROSTER),
        "constructor_roster_sha256": _file_sha(CONSTRUCTOR_ROSTER),
        "zh_sha256": _zh_sha256("circuit-zh.json", "driver-zh.json", "team-zh.json"),
    }


def round_keys(round_years):
    """有分站頁的 (year, round) 全集（升冪）。站次表＝gs.season_round_numbers，不另抄判定。"""
    return [(y, r) for y in sorted(round_years) for r in gs.season_round_numbers(y)]


def compute_fingerprints(con, round_years=None):
    """回全站頁群指紋：{'seasons', 'rounds', 'drivers', 'constructors', 'indices'}。

    ⚠️ 車手頁／分站頁／車隊頁指紋＝**db 切片 ＋ 文章 mention 切片**兩塊。原本只切 db.sqlite，
    但這三種頁的「相關報導」讀的是 articles/：新發一篇提到實體的文章時 db 一個 byte 都沒動 →
    指紋不變 → 該頁不重生 → 相關報導區永遠停在舊狀態。這正是本站記憶裡「自動內容旁的靜默
    staleness」，所以把 mention 映射一起切進去（比照 _constructor_slice 只切「頁面真的會渲染
    的東西」）。

    ⚠️ 分站頁指紋刻意**獨立於賽季總覽頁**：發一篇提到某站的文章只該重生那一頁，
    該季總覽與 /seasons/ 索引一個 byte 都不該動（它們不渲染相關報導）。所以
    indices.seasons 仍只由 db-only 的 fp_years 合成，分站的 articles 切片不進去。
    """
    round_years = set(rc.ROUND_YEARS if round_years is None else round_years)
    fp_years = {str(y): _h(_year_slice(con, y)) for y in range(FIRST_YEAR, LAST_YEAR + 1)}
    # 分站頁掛在該季 db 切片之上：賽季資料一變（新賽果）該季全部分站頁本來就會重生，
    # 沿用同一個 hash 當底，行為與 M7 原本的「季變→_render_one_season 全季重生」一致。
    # round 本身也切進 hash：否則同一季內沒有相關報導的站會算出同一個值，
    # 指紋就不再「識別那一頁」（比對雖仍逐鍵、不會出錯，但一個認不出自己是誰的指紋遲早被誤用）
    # 分站頁比賽季線多印一種譯名：賽道名（render_round → rc.circuit_pair）。circuit-zh.json
    # 不進 _year_slice（賽季總覽與車手／車隊分頁都不印賽道名，切進去＝改一個賽道譯名白刷
    # 整條賽季線），只掛在分站頁這一層。
    fp_rounds = {f"{y}/{r}": _h({"round": [y, r], "db": fp_years[str(y)],
                                 "articles": il.round_articles_slice(y, r),
                                 "zh_sha256": _zh_sha256("circuit-zh.json")})
                 for y, r in round_keys(round_years)}
    fp_drivers_db = {did: _h(_driver_slice(con, did)) for did in DRIVER_IDS}
    fp_drivers = {did: _h({"db": fp_drivers_db[did],
                           "articles": il.driver_articles_slice(did)})
                  for did in DRIVER_IDS}
    fp_cons_db = {cid: _h(_constructor_slice(con, cid)) for cid in CONSTRUCTOR_IDS}
    fp_cons = {cid: _h({"db": fp_cons_db[cid],
                        "articles": il.team_articles_slice(cid)})
               for cid in CONSTRUCTOR_IDS}
    # 賽道頁不渲染相關報導 → db（＋roster／譯名表）only，發文章時不白刷。
    fp_circuits = {cid: _h(_circuit_slice(con, cid)) for cid in CIRCUIT_IDS}
    return {
        "seasons": fp_years,
        "rounds": fp_rounds,
        "drivers": fp_drivers,
        "constructors": fp_cons,
        "circuits": fp_circuits,
        # 索引＝其成員指紋的合成；任一成員變 → 索引指紋變 → 索引重生
        "indices": {
            # /seasons/ 索引與各季總覽都不渲染相關報導 → **db-only**，
            # 免得發一篇文章就把索引與總覽白刷一次（內容一字不變的重寫正是指紋機制要避免的）
            "seasons": _h(sorted(fp_years.items())),
            "drivers": _h(sorted(fp_drivers_db.items())),
            # /constructors/ 索引不渲染相關報導，維持 db-only，避免發文章時白刷索引。
            "constructors": _h({"pages": sorted(fp_cons_db.items()),
                                  "standings_2026": [tuple(r) for r in con.execute(
                                      "SELECT constructor_id, position FROM constructor_standings "
                                      "WHERE season=2026 ORDER BY constructor_id")]}),
            # /circuits/ 索引整張表（承辦分站數、承辦賽季、國家地點）都是各賽道頁指紋的函數，
            # 排序也是；成員全成合成即可，另外沒有索引專屬輸入。
            "circuits": _h(sorted(fp_circuits.items())),
        },
    }


def load_fingerprints(path=FINGERPRINTS):
    """讀上次指紋。缺鍵（例如 constructors 是後加的）一律當「沒有指紋」→ 該頁群下次全部重生，
    不會被誤判成「沒變動所以跳過」（default-deny）。"""
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"seasons": {}, "drivers": {}, "constructors": {}, "circuits": {}, "indices": {}}


def save_fingerprints(fp, path=FINGERPRINTS):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------- 完整 URL 列舉（sitemap part 用；不 render） ----------

def enumerate_season_urls(round_years):
    urls = [f"{BASE}/seasons/"]
    for y in range(LAST_YEAR, FIRST_YEAR - 1, -1):
        urls.append(f"{BASE}/seasons/{y}/")
        for path in sorted(gs.subpage_paths(y)):
            urls.append(f"{BASE}/{path}/")
        if y in round_years:
            for path in sorted(gs.round_page_paths(y),
                               key=lambda s: int(s.rsplit("/", 1)[1])):
                urls.append(f"{BASE}/{path}/")
    return urls


def enumerate_driver_urls():
    return [f"{BASE}/drivers/"] + [f"{BASE}/drivers/{rc.driver_slug(d)}/" for d in DRIVER_IDS]


def enumerate_constructor_urls():
    return ([f"{BASE}/constructors/"]
            + [f"{BASE}/constructors/{rc.constructor_slug(c)}/" for c in CONSTRUCTOR_IDS])


def enumerate_circuit_urls():
    return ([f"{BASE}/circuits/"]
            + [f"{BASE}/circuits/{ci.circuit_slug(c)}/" for c in CIRCUIT_IDS])


# ---------- 選擇性重生 ----------

def selective_regen(con, full=False, round_years=None, fp_path=FINGERPRINTS,
                    publish=False):
    """只重生指紋變動的頁群。回 dict：changed_years/changed_drivers/changed_urls/…。

    con＝已連 db；round_years＝哪些季有分站頁（預設 config 的 round_years）；
    full＝忽略指紋全量重生；publish＝True 時（重）寫 seasons/drivers/constructors/circuits
    sitemap part（完整 URL 集，非只有這次變動的頁）。
    """
    round_years = set(rc.ROUND_YEARS if round_years is None else round_years)
    cur = compute_fingerprints(con, round_years)
    prev = load_fingerprints(fp_path)
    pv_years, pv_drivers, pv_idx = (prev.get("seasons", {}), prev.get("drivers", {}),
                                    prev.get("indices", {}))
    pv_cons, pv_rounds = prev.get("constructors", {}), prev.get("rounds", {})
    pv_circ = prev.get("circuits", {})

    changed_years = [y for y in range(LAST_YEAR, FIRST_YEAR - 1, -1)
                     if full or cur["seasons"][str(y)] != pv_years.get(str(y))]
    changed_rounds = [k for k in cur["rounds"] if full or cur["rounds"][k] != pv_rounds.get(k)]
    changed_drivers = [d for d in DRIVER_IDS
                       if full or cur["drivers"][d] != pv_drivers.get(d)]
    changed_constructors = [c for c in CONSTRUCTOR_IDS
                            if full or cur["constructors"][c] != pv_cons.get(c)]
    changed_circuits = [c for c in CIRCUIT_IDS
                        if full or cur["circuits"][c] != pv_circ.get(c)]
    idx_seasons_changed = full or cur["indices"]["seasons"] != pv_idx.get("seasons")
    idx_drivers_changed = full or cur["indices"]["drivers"] != pv_idx.get("drivers")
    idx_cons_changed = full or cur["indices"]["constructors"] != pv_idx.get("constructors")
    idx_circ_changed = full or cur["indices"]["circuits"] != pv_idx.get("circuits")

    changed_urls = []

    # 賽季：索引 + 逐個變動年（歷史年指紋恆定 → 不在清單 → 完全不呼叫生成器 → 檔案不動）
    built = set(range(FIRST_YEAR, LAST_YEAR + 1))
    if idx_seasons_changed:
        changed_urls.append(gs.render_index(built))
    for y in changed_years:
        yurls = []
        gs._render_one_season(y, yurls, round_years)
        changed_urls.extend(yurls)

    # 分站：只補「該季 db 沒變、但相關報導變了」的那幾頁。
    # 該季 db 變過的年已由 _render_one_season 整季（含全部分站頁）重生，這裡跳過不重複寫。
    rendered_rounds = []
    for key in changed_rounds:
        y, r = (int(x) for x in key.split("/"))
        if y in changed_years:
            continue
        changed_urls.append(gs.render_round(y, r, gs.round_page_paths(y), gs.subpage_paths(y)))
        rendered_rounds.append(key)

    # 車手：索引 + 逐個變動車手
    if idx_drivers_changed:
        changed_urls.append(dr.render_index(con))
    for did in changed_drivers:
        s = dr.gen_driver(did, con)
        changed_urls.append(f"{BASE}/drivers/{s['slug']}/")

    # 車隊：索引 + 逐個變動車隊（唯一 owner＝gen-racing-constructors.py）
    if idx_cons_changed:
        changed_urls.append(cg.render_index(con))
    for cid in changed_constructors:
        s = cg.gen_constructor(cid, con)
        changed_urls.append(f"{BASE}/constructors/{s['slug']}/")

    # 賽道：索引 + 逐個變動賽道（唯一 owner＝gen-racing-circuits.py）
    if idx_circ_changed:
        changed_urls.append(ci.render_index(con))
    for cid in changed_circuits:
        s = ci.gen_circuit(cid, con)
        changed_urls.append(f"{BASE}/circuits/{s['slug']}/")

    save_fingerprints(cur, fp_path)

    if publish:
        rc.write_sitemap_part("seasons", enumerate_season_urls(round_years))
        rc.write_sitemap_part("drivers", enumerate_driver_urls())
        rc.write_sitemap_part("constructors", enumerate_constructor_urls())
        rc.write_sitemap_part("circuits", enumerate_circuit_urls())

    return {
        "changed_years": changed_years,
        "changed_rounds": changed_rounds,
        # 實際被單獨重寫的分站頁（changed_rounds 扣掉「整季重生已含」的那些）
        "rounds_rendered_standalone": rendered_rounds,
        "changed_drivers": changed_drivers,
        "changed_constructors": changed_constructors,
        "changed_circuits": changed_circuits,
        "index_seasons": idx_seasons_changed,
        "index_drivers": idx_drivers_changed,
        "index_constructors": idx_cons_changed,
        "index_circuits": idx_circ_changed,
        "changed_urls": sorted(set(changed_urls)),
    }


def run(full=False, publish=False, skip_gates=False, fp_path=FINGERPRINTS):
    """CLI/orchestrator 入口：跑前置三 gate（as_of golden）→ selective_regen。回 (ok, result)。"""
    if not skip_gates:
        if not dr.run_gates():
            return False, None
        if not cg.run_gates():
            return False, None
        if not ci.run_gates():
            return False, None
    con = fs.connect_db()
    try:
        res = selective_regen(con, full=full, publish=publish, fp_path=fp_path)
    finally:
        con.close()
    return True, res


def main():
    ap = argparse.ArgumentParser(description="百科線選擇性重生（per-page 指紋；歷史頁不重寫）。")
    ap.add_argument("--full", action="store_true", help="忽略指紋全量重生（首次公開/指紋遺失）")
    ap.add_argument("--publish", action="store_true",
                    help="（重）寫 seasons/drivers/constructors/circuits sitemap part")
    ap.add_argument("--skip-gates", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    ok, res = run(full=a.full, publish=a.publish, skip_gates=a.skip_gates)
    if not ok:
        print("🔴 前置 gate 未過 → 零重生。", flush=True)
        return 1
    print(f"✅ 選擇性重生：變動賽季 {res['changed_years'] or '—'}；"
          f"單獨重生分站 {res['rounds_rendered_standalone'] or '—'}；"
          f"變動車手 {res['changed_drivers'] or '—'}；"
          f"變動車隊 {res['changed_constructors'] or '—'}；"
          f"變動賽道 {res['changed_circuits'] or '—'}；"
          f"索引(季/手/隊/道) {res['index_seasons']}/{res['index_drivers']}"
          f"/{res['index_constructors']}/{res['index_circuits']}；"
          f"變更頁 {len(res['changed_urls'])}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
