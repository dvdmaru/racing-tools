#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""interlink.py — 文章 ↔ 實體頁雙向互鏈的**單一規則層**（車手頁 ＋ 分站頁）。

兩個方向共用同一份判定表，避免兩邊各長一套規則後慢慢對不上：

  正向：文章 HTML 裡的車手名 → `/drivers/<slug>/`
        文章 HTML 裡的賽站名 → `/seasons/<year>/rounds/<n>/`
        （build-articles.py 在 markdown→HTML **之後**呼叫 linkify() / linkify_rounds()）
  反向：車手頁／分站頁的「相關報導」＝唯讀掃描 articles/<slug>/index.md 得到的提及映射
        （gen-racing-drivers.py 呼叫 driver_articles()；
          gen-racing-seasons.py 呼叫 round_related_articles_html()）

☠️ 紅線：已發布文章被 config/approved.json 以 sha256 凍結，改 articles/<slug>/index.md
一個 byte 整篇就會被 build gate 下架。所以正向互鏈**只動渲染後的 HTML**；本模組對
articles/ 與 config/approved.json 一律唯讀，永不寫入。

── 匹配紀律（寧漏勿錯連）─────────────────────────────────────────
1. 只認**已建頁**的 53 位車手（名單＝crosscheck-report 的 expected_driver_ids，
   與 gen-racing-drivers.py 同源；slug 走 data/f1/slugs.json 註冊表）。
2. 匹配字串只有三種來源，全部是「已核准」的既有資料，本模組不自譯、不做模糊姓氏推斷：
   ① 已核准繁中譯名（phase0 seed 全名 ＋ scripts/driver-zh.json 的 status=="approved"）
   ② ①裡含「・」者的末段（如「麥可・舒馬克」→「舒馬克」）——文章實務上寫的是這一段
   ③ 英文全名（givenName + familyName，取自 data/f1/raw/entities/drivers.json）
   ⚠️ **刻意不收單獨的英文姓氏**：Button / Hunt / Farina / Jones 同時是普通英文單字，
      本站又有技術類文章，收了就是等著誤連。站規是「中文為主、首次出現附原名」，
      中文名一定先出現，②已經接住了絕大多數；漏連比錯連便宜。
3. 一個字串在 53 人聯集裡對應**多人就整個丟掉**（真實案例：「希爾」對到 damon_hill /
   hill / phil_hill 三人、「羅斯堡」對到 keke_rosberg / rosberg 兩人 → 兩者都不連）。
4. 同一個位置有多個候選時取**最長匹配**（「路易斯・漢米爾頓」勝過「漢米爾頓」）。

── 分站頁那一半的匹配紀律（同樣寧漏勿錯連）───────────────────────
5. 只連**實際存在的分站頁**：年份限 config/encyclopedia.json 的 round_years（2002／2026），
   站次限 gen-racing-seasons.season_round_numbers()（＝有正賽 results 檔者，也就是生成器
   真的會建頁的那批，同一個函式、不另抄一份判定）。未完賽的場次沒有頁 → 不連。
6. 匹配字串只有一種：該場 raceName 的**已核准**中文站名（scripts/race-zh.json，approved-only，
   由 racinglib._load_zh 過濾）。不自譯、不截短（「西班牙站（馬德里）」不會退化成「西班牙站」）。
7. ☠️ **年份消歧**：「匈牙利站」在 2002（R13）與 2026（R11）各有一頁，光看字串永遠決定不了
   該連哪一年。判定唯一依據＝文章 frontmatter **明示**的 `season` 欄，且該年須是 round_year；
   沒有 season 欄 → 整篇不做分站互鏈。刻意**不用發布日期推年份**——實測既有六篇裡，
   f1-tech-timing-positioning-race-control（2026-07-30 發）文中的「摩納哥站」指的是 2022 那場、
   f1-2026-bahrain-gp-in-malaysia 的「義大利站」「馬來西亞大獎賽」是 1980–2000 年代的歷史脈絡；
   用發布年推就會把讀者送到錯的那一站。漏連比錯連便宜。
8. 「第 N 站」這類數字型指涉不連（可能是賽曆位置敘述而非指涉該場），只連具名站名。

── 快取 ────────────────────────────────────────────────────────
判定表與提及映射都吃檔案，程序內快取一次。測試改了 ARTICLES/APPROVED 等模組層路徑後
**必須呼叫 clear_caches()**，否則讀到的是上一輪的結果。
"""
import hashlib
import html as html_lib
import importlib.util
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rc = _load("racinglib", "racinglib.py")

# 資料來源（全部是 committed 檔；**不碰 db.sqlite**——它不進 git，build-articles.py
# 在乾淨 checkout／CI 上也要跑得起來）
REPORT = ROOT / "data" / "f1" / "crosscheck-report.json"
DRIVER_ENTITIES = ROOT / "data" / "f1" / "raw" / "entities" / "drivers.json"
ARTICLES = ROOT / "articles"
APPROVED = ROOT / "config" / "approved.json"
DRAFT_EXCLUDE = ROOT / "config" / "draft-exclude.json"

# 互鏈不進入的容器：既有連結（不巢狀）、標題（h1–h6）、程式碼、表格（表格有自己的
# 連結慣例，別攪）、script/style（JSON-LD 就在 script 裡）。
PROTECTED_TAGS = frozenset({
    "a", "code", "pre", "kbd", "samp", "script", "style", "table",
    "h1", "h2", "h3", "h4", "h5", "h6",
})

_TAG_SPLIT = re.compile(r"(<[^>]*>)")
_TAG_NAME = re.compile(r"</?\s*([A-Za-z][A-Za-z0-9]*)")
_ASCII_WORD = re.compile(r"[A-Za-z]")

_CACHE = {}

# 分站頁的「哪些站有頁／各站叫什麼」由 gen-racing-seasons 擁有（它就是建那些頁的人）。
# 本模組**不另抄一份判定**，只借它兩個純讀函式；gs 載入時會 bind_seasons() 把自己交進來，
# 沒 bind（例如 build-articles 只載 interlink）就 lazy load 一份——兩者都是唯讀資料讀取，
# 不寫檔、不碰 db.sqlite，重複載入無副作用。刻意用 lazy／注入而非 module-level import：
# gs 需要 il 的相關報導區塊、il 需要 gs 的站次表，module-level 互 import 會變循環。
_GS = None


def bind_seasons(mod):
    """由 gen-racing-seasons.py 呼叫，把分站頁資料源（season_round_numbers／_schedule）交給本模組。"""
    global _GS
    _GS = mod


def _gs():
    global _GS
    if _GS is None:
        _GS = _load("gen_racing_seasons", "gen-racing-seasons.py")
    return _GS


def clear_caches():
    """清掉判定表／提及映射快取（測試換過模組層路徑後必呼叫）。"""
    _CACHE.clear()


# ---------- 名單與譯名（與 gen-racing-drivers.py 同源，不另硬編） ----------

def champion_ids():
    """35 位歷代冠軍 id（canonical 來源＝crosscheck-report 的 coverage）。"""
    if "champion_ids" not in _CACHE:
        _CACHE["champion_ids"] = tuple(
            json.loads(REPORT.read_text(encoding="utf-8"))["coverage"]["expected_champion_ids"])
    return _CACHE["champion_ids"]


def driver_ids():
    """所有有實體頁的車手：歷代冠軍 ∪ 2026 現役。"""
    if "driver_ids" not in _CACHE:
        cov = json.loads(REPORT.read_text(encoding="utf-8"))["coverage"]
        _CACHE["driver_ids"] = tuple(cov["expected_driver_ids"])
    return _CACHE["driver_ids"]


def seed_zh():
    """phase0 已上線（＝PR merge 核准過）的四位 seed 全名譯名。"""
    if "seed_zh" not in _CACHE:
        p0 = _load("gen_racing_entities_phase0", "gen-racing-entities-phase0.py")
        _CACHE["seed_zh"] = {k: v for k, v in p0.ZH.items() if k in p0.DRIVERS}
    return _CACHE["seed_zh"]


def resolve_zh(did):
    """approved-only 譯名解析：seed 全名 → driver-zh 譯名 → None（誠實 fallback，不自譯）。"""
    seed = seed_zh()
    if did in seed:
        return seed[did]
    return rc.DRIVER_ZH.get(did)


def english_names():
    """{driver_id: "Given Family"}（raw entities 快照；db.sqlite 不進 git 故不從 db 取）。"""
    if "en_names" not in _CACHE:
        raw = json.loads(DRIVER_ENTITIES.read_text(encoding="utf-8"))["Drivers"]
        _CACHE["en_names"] = {
            d["driverId"]: f'{d.get("givenName", "")} {d.get("familyName", "")}'.strip()
            for d in raw}
    return _CACHE["en_names"]


def candidate_strings(did):
    """單一車手的候選匹配字串集合（尚未做唯一性過濾）。"""
    out = set()
    zh_forms = {resolve_zh(did), rc.DRIVER_ZH.get(did)} - {None, ""}
    for zh in zh_forms:
        out.add(zh)
        if "・" in zh:
            tail = zh.rsplit("・", 1)[1]
            if len(tail) >= 2:
                out.add(tail)
    en = english_names().get(did, "")
    if " " in en:                      # 只收英文全名，單獨姓氏刻意不收（見模組 docstring §2）
        out.add(en)
    return {s for s in out if len(s) >= 2}


def link_index():
    """{匹配字串: (driver_id, slug)}——只留在 53 人聯集裡**唯一**對應的字串。"""
    if "link_index" not in _CACHE:
        owners = {}
        for did in driver_ids():
            for s in candidate_strings(did):
                owners.setdefault(s, set()).add(did)
        _CACHE["link_index"] = {
            s: (next(iter(dids)), rc.driver_slug(next(iter(dids))))
            for s, dids in owners.items() if len(dids) == 1}
    return _CACHE["link_index"]


def ambiguous_strings():
    """對應到多人、因此**永不連**的字串（負向控制與稽核用）。"""
    owners = {}
    for did in driver_ids():
        for s in candidate_strings(did):
            owners.setdefault(s, set()).add(did)
    return {s: sorted(dids) for s, dids in owners.items() if len(dids) > 1}


def _compile(index):
    """最長匹配優先的單一 alternation（Python 的 | 是先到先贏，故長字串排前面）。"""
    ordered = sorted(index, key=lambda s: (-len(s), s))
    return re.compile("|".join(re.escape(s) for s in ordered))


def _pattern(index, cache_key=None):
    """cache_key=None（測試注入的自訂表）→ 不進快取，每次重編。"""
    if cache_key is None:
        return _compile(index)
    if cache_key not in _CACHE:
        _CACHE[cache_key] = _compile(index)
    return _CACHE[cache_key]


# ---------- 分站頁判定表（賽站名 → 該季某一站） ----------

def round_link_index(year):
    """{已核准中文站名: (year, round)}——只含該季**已建分站頁**的場次。

    year 不在 round_years（或為 None）→ 空表（整篇不做分站互鏈）。
    同一個中文站名在該季對到多站 → 整個丟掉（比照車手的歧義規則；現況兩季皆無此情形，
    但一季辦兩場同名比賽在 F1 史上發生過，留著這條才不會哪天默默錯連）。
    """
    if year is None or year not in rc.ROUND_YEARS:
        return {}
    key = ("round_index", year)
    if key not in _CACHE:
        gsm = _gs()
        built = set(gsm.season_round_numbers(year))   # ＝生成器真的會建頁的站次，同一個判定
        owners = {}
        for row in gsm._schedule(year):
            try:
                rnd = int(row.get("round"))
            except (TypeError, ValueError):
                continue
            if rnd not in built:
                continue                              # 未完賽／無 results ＝沒有頁 → 不連
            zh = rc.RACE_ZH.get(row.get("raceName", ""))   # approved-only（_load_zh 已過濾）
            if zh and len(zh) >= 2:
                owners.setdefault(zh, set()).add(rnd)
        _CACHE[key] = {zh: (year, next(iter(rnds)))
                       for zh, rnds in owners.items() if len(rnds) == 1}
    return _CACHE[key]


def article_round_season(meta):
    """文章的賽季脈絡（年份消歧的唯一依據）。回 int 或 None。

    只認 frontmatter 明示的 `season` 欄且該年有分站頁；查不到就 None＝不做分站互鏈。
    （為何不用發布日期推年份：見模組 docstring §7 的兩個真實反例。）
    """
    if not isinstance(meta, dict):
        return None
    try:
        year = int(str(meta.get("season", "")).strip())
    except (TypeError, ValueError):
        return None
    return year if year in rc.ROUND_YEARS else None


# ---------- 正向：文章 HTML → 車手頁連結 ----------

def _boundary_ok(text, start, end, token):
    """英文候選要求詞邊界；中文候選不需要（中文沒有空白邊界可用）。"""
    if not _ASCII_WORD.search(token):
        return True
    if start > 0 and _ASCII_WORD.match(text[start - 1]):
        return False
    if end < len(text) and _ASCII_WORD.match(text[end]):
        return False
    return True


def _linkify(body_html, index, href_of, key_of, cache_key=None):
    """保護區感知的行內連結替換——正向互鏈的**唯一**實作（車手與分站共用）。

    index＝{匹配字串: 目標值}；href_of(目標值)→URL；key_of(目標值)→去重鍵
    （每個鍵每篇只連第一次出現）。回 (html, [(目標值, 匹配字串), …]，依出現順序)。

    ⚠️ 兩種互鏈共用這支的理由：保護區（標題／既有 <a>／表格／code／JSON-LD）與「只連第一次」
    是同一組規則，各寫一份遲早只修到其中一份——分站互鏈要擋的正是「匈牙利站」出現在標題裡。
    連結不自帶 class：`.prose a` 已是站內既有的行內連結樣式。
    """
    if not index or not body_html:
        return body_html, []

    pat = _pattern(index, cache_key)
    hits = []
    used = set()

    def repl(m):
        token = m.group(0)
        target = index[token]
        key = key_of(target)
        if key in used or not _boundary_ok(m.string, m.start(), m.end(), token):
            return token
        used.add(key)
        hits.append((target, token))
        return f'<a href="{href_of(target)}">{token}</a>'

    out = []
    depth = 0
    for part in _TAG_SPLIT.split(body_html):
        if part.startswith("<") and part.endswith(">"):
            name = _TAG_NAME.match(part)
            if name and name.group(1).lower() in PROTECTED_TAGS:
                if part.startswith("</"):
                    depth = max(0, depth - 1)
                elif not part.rstrip(">").rstrip().endswith("/"):
                    depth += 1
            out.append(part)
            continue
        out.append(part if depth or not part.strip() else pat.sub(repl, part))
    return "".join(out), hits


def linkify(body_html, index=None):
    """在渲染後的文章 HTML 上加車手頁連結。回 (html, linked)。

    linked＝依出現順序的 [(driver_id, slug, matched_text)]。
    每位車手每篇**只連第一次出現**（連結灑滿版會稀釋每一條的權重，也難讀）。
    """
    index = link_index() if index is None else index
    key = "pattern" if index is link_index() else None   # 測試注入的自訂表不進快取
    out, hits = _linkify(body_html, index,
                         href_of=lambda t: f"/drivers/{t[1]}/",
                         key_of=lambda t: t[0], cache_key=key)
    return out, [(t[0], t[1], tok) for t, tok in hits]


def linkify_rounds(body_html, season, index=None):
    """在渲染後的文章 HTML 上加分站頁連結。回 (html, linked)。

    season＝該文的賽季脈絡（article_round_season 決定）；None → 原封不動回傳（寧漏勿錯連）。
    linked＝依出現順序的 [(year, round, matched_text)]；每篇每場次只連第一次出現。
    呼叫順序在 linkify() **之後**：先加的車手連結是 <a>（保護區），不會被巢狀包一層。
    """
    default = index is None
    index = round_link_index(season) if default else index
    key = ("round_pattern", season) if default and index else None
    out, hits = _linkify(body_html, index,
                         href_of=lambda t: f"/seasons/{t[0]}/rounds/{t[1]}/",
                         key_of=lambda t: t, cache_key=key)
    return out, [(t[0], t[1], tok) for t, tok in hits]


# ---------- 反向：車手頁「相關報導」 ----------

def _load_json(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def published_articles(articles_root=None, approved_path=None, draft_exclude_path=None):
    """已核准發布的文章（唯讀）。回 [{slug,title,date,text}]，新→舊。

    判定與 build-articles.py 的發布 gate 同義（default-deny）：資料夾有 index.md、
    不在 draft-exclude、在 approved.json 裡、且 article_sha256 完全命中。
    ⚠️ 只列真的會被輸出的文章——列到沒發布的就是在車手頁上掛死連結。
    （tests/test_article_interlink.py 有一條把這串與 build 實際產出的目錄對起來的 gate，
     擋兩邊規則日後各自漂走。）
    """
    root = pathlib.Path(articles_root or ARTICLES)
    approved = {}
    for entry in _load_json(approved_path or APPROVED, {}).get("approved", []):
        if isinstance(entry, dict) and entry.get("slug"):
            approved[entry["slug"]] = entry
    excluded = set(_load_json(draft_exclude_path or DRAFT_EXCLUDE, {}).get("exclude", []))

    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        src = d / "index.md"
        if not d.is_dir() or not src.exists():
            continue
        raw = src.read_bytes()
        meta, _ = rc.parse_frontmatter(raw.decode("utf-8"))
        slug = meta.get("slug") or d.name
        if slug in excluded or slug not in approved:
            continue
        if approved[slug].get("article_sha256", "") != hashlib.sha256(raw).hexdigest():
            continue
        out.append({"slug": slug, "title": meta.get("title", slug),
                    "date": str(meta.get("date", "")), "season": meta.get("season"),
                    "text": raw.decode("utf-8")})
    out.sort(key=lambda a: (a["date"], a["slug"]), reverse=True)
    return out


def article_mentions(articles_root=None, approved_path=None, draft_exclude_path=None):
    """{driver_id: [{slug,title,date}, …]}（新→舊）——哪些已發布文章提到哪位車手。

    提及＝index.md 原文（含 frontmatter 的標題／導言）出現任一「唯一對應」的匹配字串。
    歧義字串（「希爾」「羅斯堡」）一樣不算提及——寧可少列一篇，也不要把讀者送去錯的人。
    """
    key = ("mentions", str(articles_root or ARTICLES), str(approved_path or APPROVED),
           str(draft_exclude_path or DRAFT_EXCLUDE))
    if key in _CACHE:
        return _CACHE[key]
    index = link_index()
    out = {}
    for art in published_articles(articles_root, approved_path, draft_exclude_path):
        text = art["text"]
        hit = set()
        for token, (did, _slug) in index.items():
            if did in hit or token not in text:
                continue
            if not _ASCII_WORD.search(token) or re.search(
                    r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(token), text):
                hit.add(did)
        for did in hit:
            out.setdefault(did, []).append(
                {"slug": art["slug"], "title": art["title"], "date": art["date"]})
    _CACHE[key] = out
    return out


def driver_articles(did):
    """單一車手的相關報導（新→舊）。沒有就是空 list——區塊整個不出現，不放占位。"""
    return article_mentions().get(did, [])


def driver_articles_slice(did):
    """車手頁指紋要吃的 mention 切片（決定性 tuple 序列）。

    ⚠️ 這條存在的理由：車手頁的「相關報導」讀 articles/，但 regen-encyclopedia 的指紋
    原本只切 db.sqlite——新發一篇提到某車手的文章時該車手指紋不變 → 頁面不重生 →
    相關報導永遠停在舊狀態（自動內容旁的靜默 staleness）。把這塊納入指紋才會跟著動。
    """
    return [(a["slug"], a["title"], a["date"]) for a in driver_articles(did)]


def _related_block(arts, esc):
    """「相關報導」區塊的**唯一**渲染路徑（車手頁與分站頁共用）。空 list → 空字串。

    沿用既有 class：小標 `.sec-title`（2026-08-03 定的 h2 慣例）、清單用「效力車隊」
    同一組 `.rel` chip——不自創視覺、零新 CSS。
    """
    if not arts:
        return ""
    chips = "".join(
        f'<a href="/articles/{a["slug"]}/">{esc(a["title"])}'
        + (f'（{esc(a["date"])}）' if a["date"] else "")
        + "</a>"
        for a in arts)
    return (f'\n\n<h2 class="sec-title">相關報導</h2>\n'
            f'<div class="rel">{chips}</div>')


def related_articles_html(did, esc=html_lib.escape):
    """車手頁「相關報導」區塊。無任何文章提及 → 回空字串（區塊整個不出現，不放占位）。"""
    return _related_block(driver_articles(did), esc)


# ---------- 反向：分站頁「相關報導」 ----------

def round_mentions(articles_root=None, approved_path=None, draft_exclude_path=None):
    """{(year, round): [{slug,title,date}, …]}（新→舊）——哪些已發布文章提到哪一站。

    提及＝文章 frontmatter 明示 season（且該年有分站頁）＋ index.md 原文（含 frontmatter 的
    標題／導言）出現該季某場次的已核准中文站名。年份消歧與正向走**同一張** round_link_index，
    所以「文章連去哪一站」與「哪一站列這篇」永遠是同一個答案，不會各自漂。
    """
    key = ("round_mentions", str(articles_root or ARTICLES), str(approved_path or APPROVED),
           str(draft_exclude_path or DRAFT_EXCLUDE))
    if key in _CACHE:
        return _CACHE[key]
    out = {}
    for art in published_articles(articles_root, approved_path, draft_exclude_path):
        season = article_round_season(art)
        if season is None:
            continue                       # 無法確定年份 → 不掛到任何一站
        text = art["text"]
        hit = {target for token, target in round_link_index(season).items() if token in text}
        for target in sorted(hit):
            out.setdefault(target, []).append(
                {"slug": art["slug"], "title": art["title"], "date": art["date"]})
    _CACHE[key] = out
    return out


def round_articles(year, rnd):
    """單一分站的相關報導（新→舊）。沒有就是空 list——區塊整個不出現。"""
    return round_mentions().get((int(year), int(rnd)), [])


def round_articles_slice(year, rnd):
    """分站頁指紋要吃的 mention 切片（決定性 tuple 序列）。

    ⚠️ 同 driver_articles_slice 的理由：分站頁的「相關報導」讀 articles/，但 regen 的指紋
    只切 db.sqlite——新發一篇提到某站的文章時該站指紋不變 → 頁面不重生 → 相關報導永遠停在
    舊狀態。把這塊納入分站頁指紋才會跟著動（且只動那一頁，賽季總覽與索引不受影響）。
    """
    return [(a["slug"], a["title"], a["date"]) for a in round_articles(year, rnd)]


def round_related_articles_html(year, rnd, esc=html_lib.escape):
    """分站頁「相關報導」區塊。無任何文章提及 → 回空字串（區塊整個不出現，不放占位）。"""
    return _related_block(round_articles(year, rnd), esc)
