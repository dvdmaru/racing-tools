#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-articles.py — racing.twtools.cc 主建置：文章管線＋首頁 dashboard＋sitemap/feed/llms.txt。

架構 clone 自 baseball-tools：
- articles/<slug>/index.md（frontmatter + markdown）→ public-racing/articles/<slug>/
- FAQ schema ###-gated：只有「## 常見問題」下的 ### 問答會進 FAQPage schema（鏡射可見文字）
- 草稿 gate：config/draft-exclude.json 列的 slug 完全不進輸出（index/feed/sitemap/頁面）
- 首頁 dashboard 讀 data/ 快照 server-render（積分速覽/下一站/最新賽果），零 client fetch
- llms.txt build-time 生成（手寫靜態檔＝staleness 炸彈）
- ⚠️ sitemap 由本腳本整個覆寫 → 各 gen-* 之後 re-merge 自己的 path（跑序鐵則）

用法：python3 scripts/build-articles.py
需要：pip install markdown
"""
import datetime
import html as html_lib
import importlib.util
import json
import pathlib
import re
import shutil
import sys

import markdown as md_lib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("racinglib", ROOT / "scripts" / "racinglib.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

SRC = ROOT / "articles"
PUB = rc.PUB
BASE = rc.BASE
SITE = rc.SITE
FEED_MAX = 20


def load_draft_excludes() -> set:
    p = ROOT / "config" / "draft-exclude.json"
    if not p.exists():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8")).get("exclude", []))


DRAFT_EXCLUDE = load_draft_excludes()


# ---------- 文章頁 CSS ----------

ARTICLE_CSS = """
.art-cover { width:100%; border-radius: var(--radius); margin: 8px 0 26px; display:block; }
.art-kicker { font-family: var(--font-mono); font-size: 12px; letter-spacing: 2.5px; color: var(--accent);
  text-transform: uppercase; margin-bottom: 10px; }
.art-h1 { font-family: var(--font-display); font-size: clamp(26px,4.6vw,40px); line-height: 1.22;
  margin: 0 0 14px; font-style: italic; }
.art-meta { color: var(--dim); font-size: 13px; margin-bottom: 26px; display:flex; gap:14px; flex-wrap:wrap; }
.art-lede { font-size: 16.5px; color: var(--fg-soft); line-height: 1.85; border-left: 3px solid var(--accent);
  padding: 4px 0 4px 18px; margin: 0 0 30px; }
.prose { font-size: 16px; line-height: 1.95; }
.prose h2 { font-family: var(--font-display); font-size: 23px; margin: 44px 0 14px; line-height:1.35; font-style: italic; }
.prose h3 { font-size: 17.5px; margin: 30px 0 10px; font-weight: 800; }
.prose p { margin: 0 0 18px; }
.prose strong { color: var(--fg); }
.prose a { color: var(--accent); }
.prose ul, .prose ol { margin: 0 0 18px 1.4em; }
.prose li { margin-bottom: 6px; }
.prose blockquote { border-left: 3px solid var(--line-2); color: var(--dim); padding-left: 16px; margin: 0 0 18px; }
.prose hr { border: none; border-top: 1px solid var(--line); margin: 34px 0; }
.prose table { width:100%; border-collapse: collapse; margin: 10px 0 22px; font-size: 14px; }
.prose th, .prose td { padding: 8px 8px; border-bottom: 1px solid var(--line); text-align: left; }
.prose th { color: var(--dim); font-weight: 600; font-size: 12.5px; white-space: nowrap; }
.prose .tbl-scroll, .prose-tblwrap { overflow-x: auto; }
.art-nav { display:flex; gap:12px; margin-top: 44px; }
.art-nav a { flex:1; border:1px solid var(--line); border-radius: 12px; padding: 12px 16px;
  text-decoration:none; color: var(--fg-soft); font-size: 13.5px; background: var(--surface); }
.art-nav a:hover { border-color: var(--accent-line); }
.art-nav .lbl { display:block; color: var(--dim); font-size: 11px; font-family: var(--font-mono);
  letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 4px; }
"""

INDEX_CSS = """
.rc-hero { padding: 6px 0 26px; }
.rc-hero h1 { font-family: var(--font-display); font-size: clamp(30px,5.4vw,50px); line-height: 1.16;
  margin-bottom: 14px; font-style: italic; }
.rc-hero p { color: var(--fg-soft); max-width: 640px; font-size: 15.5px; }
.dash-asof { margin-top: 14px; color: var(--dim); font-size: 12.5px; font-family: var(--font-mono); }
.dash-asof b { color: var(--accent); }
.rc-sec { display:flex; align-items:baseline; gap: 14px; margin: 36px 0 14px; }
.rc-sec h2 { font-family: var(--font-display); font-size: 21px; font-style: italic; }
.rc-sec .ln { flex:1; height:1px; background: var(--line); }
.rc-sec .tg { color: var(--dim); font-size: 12px; font-family: var(--font-mono); letter-spacing: 1px; }
.next-race { border:1px solid var(--accent-line); border-radius: var(--radius); background: var(--accent-soft);
  padding: 18px 20px; display:flex; gap: 18px; align-items:center; flex-wrap:wrap; }
.next-race .big { font-size: 19px; font-weight: 800; }
.next-race .big .en { color: var(--dim); font-weight: 500; font-size: 13px; margin-left: 8px; }
.next-race .when { margin-left:auto; text-align:right; font-family: var(--font-mono); }
.next-race .when b { color: var(--accent); font-size: 17px; }
.next-race .when span { display:block; color: var(--dim); font-size: 11.5px; }
.podium-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
.podium-card { border:1px solid var(--line); border-radius: 12px; padding: 14px 16px; background: var(--surface); }
.podium-card .pos { font-family: var(--font-mono); font-size: 12px; color: var(--accent); font-style: italic; font-weight: 700; }
.podium-card .who { font-weight: 800; font-size: 16px; margin: 4px 0 2px; }
.podium-card .team { color: var(--dim); font-size: 12.5px; }
.tiles { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.tile { display:flex; gap: 12px; align-items:center; border:1px solid var(--line); border-radius: 12px;
  padding: 14px 16px; text-decoration:none; color: var(--fg); background: var(--surface); transition: border-color .15s; }
.tile:hover { border-color: var(--accent-line); }
.tile .ic { font-size: 20px; }
.tile .tt { display:block; font-weight: 800; font-size: 14.5px; }
.tile .ds { display:block; color: var(--dim); font-size: 12px; }
.tile .go { margin-left:auto; color: var(--accent); }
.idx-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.idx-card { border:1px solid var(--line); border-radius: var(--radius); overflow:hidden; background: var(--surface);
  text-decoration:none; color: var(--fg); display:block; transition: border-color .15s, transform .15s; }
.idx-card:hover { border-color: var(--accent-line); transform: translateY(-2px); }
.idx-card img { width:100%; aspect-ratio: 1200/630; object-fit: cover; display:block; }
.idx-card .pad { padding: 14px 16px 16px; }
.idx-card .k { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 2px; color: var(--accent);
  text-transform: uppercase; }
.idx-card h3 { font-size: 16px; line-height: 1.45; margin: 6px 0 8px; }
.idx-card p { color: var(--dim); font-size: 13px; line-height: 1.7; }
.idx-card .dt { color: var(--faint); font-size: 11.5px; font-family: var(--font-mono); margin-top: 8px; }
.idx-h1 { font-family: var(--font-display); font-size: clamp(26px,4.6vw,38px); margin-bottom: 8px; font-style: italic; }
.idx-intro { color: var(--dim); font-size: 14px; margin-bottom: 26px; }
.rc-faq { display:grid; gap: 10px; }
.rc-faq .qa { background: var(--surface); border:1px solid var(--line); border-radius: 8px; padding: 14px 18px; }
.rc-faq h3 { font-size: 15px; font-weight: 800; margin: 0 0 6px; line-height: 1.45; }
.rc-faq p { font-size: 13.5px; color: var(--fg-soft); line-height: 1.7; margin: 0; }
"""


# ---------- 首頁 FAQ（可見問答＝schema 鏡射源） ----------

HOME_FAQ = [
    ("這個網站是做什麼的？",
     "賽車數據誌是非官方的繁體中文 F1 資訊站：積分榜、台北時間賽曆、各站賽果三個資料頁每週自動更新，"
     "加上規則解析、譯名對照等長青專題文章。內容面向台灣讀者，時間一律以台北時間標示。"),
    ("資料來源是什麼？",
     "數據來自 Ergast 相容的公開 API（jolpica-f1），每次抓取都落地 JSON 快照存檔；"
     "文章中的規則與事實逐項對照 FIA 與賽事官方說明查證後發布，並標註來源。"),
    ("多久更新一次？",
     "每週一台北時間早上自動更新（歐洲賽事週日夜賽後），衝刺賽週末加跑週六、週日；"
     "非賽週如無新資料則不變動。"),
    ("車手和車隊的中文名字為什麼跟別站不一樣？",
     "本站採台灣媒體慣用譯名（漢米爾頓、麥拉倫、賓士等），不用中國大陸或香港譯名系統；"
     "完整對照與依據見車手車隊譯名對照表。"),
]


# ---------- 文章渲染 ----------

def prune_stale_article_dirs(art_root: pathlib.Path, keep_slugs: set):
    """刪掉 public-racing/articles/ 下不屬於本次產出的目錄（草稿回收／文章下架）。"""
    if not art_root.exists():
        return
    for child in sorted(art_root.iterdir()):
        if child.is_dir() and child.name not in keep_slugs:
            shutil.rmtree(child)
            print(f"🗑  removed stale article output: {child.name}（草稿或已下架）")


def _kicker(meta):
    return {"feature": "深度專題", "guide": "長青指南", "reference": "對照表",
            "preview": "賽站前瞻", "recap": "賽後復盤"}.get(meta.get("type", "feature"), "專題")


def _date_disp(s):
    try:
        d = datetime.date.fromisoformat(str(s))
        return f"{d.year} 年 {d.month} 月 {d.day} 日"
    except ValueError:
        return str(s)


def render_article(meta, body_html, slug, excerpt, faq, prev_nav=None, next_nav=None):
    url = f"{BASE}/articles/{slug}/"
    title = meta.get("title", slug)
    desc = meta.get("subtitle", excerpt)[:300]
    cover = f"{url}cover.png" if (SRC / slug / "cover.png").exists() else ""
    lede = meta.get("lede", "")
    lede_html = f'<p class="art-lede">{html_lib.escape(lede)}</p>' if lede else ""
    cover_html = f'<img class="art-cover" src="cover.png" alt="{html_lib.escape(title)}">' if cover else ""

    nav_parts = []
    if prev_nav:
        nav_parts.append(f'<a href="/articles/{prev_nav["slug"]}/"><span class="lbl">← 前一篇</span>'
                         f'{html_lib.escape(prev_nav["meta"].get("title",""))[:40]}</a>')
    if next_nav:
        nav_parts.append(f'<a href="/articles/{next_nav["slug"]}/" style="text-align:right"><span class="lbl">後一篇 →</span>'
                         f'{html_lib.escape(next_nav["meta"].get("title",""))[:40]}</a>')
    nav_html = f'<div class="art-nav">{"".join(nav_parts)}</div>' if nav_parts else ""

    art_node = {
        "@type": "Article", "@id": f"{url}#article",
        "headline": title, "description": desc,
        "datePublished": meta.get("date", ""), "dateModified": meta.get("updated", meta.get("date", "")),
        "inLanguage": "zh-Hant", "mainEntityOfPage": url,
        "author": {"@type": "Organization", "name": SITE["org_name"]},
        "publisher": {"@id": f"{BASE}/#org"},
        "isAccessibleForFree": True,
    }
    if cover:
        art_node["image"] = cover
    jsonld = rc.graph_ld([rc.org_node(), rc.website_node(), art_node,
                          rc.breadcrumb_node([("首頁", f"{BASE}/"), ("文章", f"{BASE}/articles/"),
                                              (title, url)]),
                          rc.faq_node(faq, url)])
    og_img = ""
    if cover:
        og_img = (f'<meta property="og:image" content="{cover}">\n'
                  '<meta property="og:image:width" content="1200">\n'
                  '<meta property="og:image:height" content="630">\n'
                  '<meta name="twitter:card" content="summary_large_image">\n'
                  f'<meta name="twitter:image" content="{cover}">\n')

    return f"""<!DOCTYPE html>
<html lang="zh-Hant" data-theme="{SITE['default_theme']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_lib.escape(title)} | {SITE['title_suffix']}</title>
<meta name="description" content="{html_lib.escape(desc)}">
<meta property="og:title" content="{html_lib.escape(title)}">
<meta property="og:description" content="{html_lib.escape(desc)}">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="{SITE['org_name']}">
<meta property="og:locale" content="zh_TW">
{og_img}<link rel="canonical" href="{url}">
{jsonld}
{rc.FONTS_HTML}
{rc.ga_snippet()}
<style>
{rc.SHARED_TOKENS_CSS}
{rc.THEME_SWITCH_CSS}
{rc.SITE_HEADER_CSS}
{ARTICLE_CSS}
{rc.DARK_ANCHOR_CSS}
</style>
</head>
<body>
{rc.THEME_SWITCH_HTML}
<div class="container">{rc.site_header_html('articles')}
  <main>
  <div class="art-kicker">{_kicker(meta)}</div>
  <h1 class="art-h1">{html_lib.escape(title)}</h1>
  <div class="art-meta"><span>{_date_disp(meta.get('date',''))}</span><span>{SITE['org_name']}</span></div>
  {cover_html}
  {lede_html}
  <article class="prose">
{body_html}
  </article>
  {nav_html}
  </main>
{rc.site_footer_html()}
</div>
<script>{rc.THEME_SWITCH_JS}</script>
</body>
</html>
"""


# ---------- 首頁 dashboard ----------

def _standings_mini(season=rc.SEASON):
    ds = rc.load_data(season, "driver-standings.json")
    cs = rc.load_data(season, "constructor-standings.json")
    if not ds or not ds.get("standings"):
        return "", 0
    rnd = ds.get("data_through_round", 0)

    def rows_d():
        out = ""
        for s in ds["standings"]["DriverStandings"][:6]:
            cons = s["Constructors"][-1]["name"] if s["Constructors"] else ""
            lead = ' class="lead"' if s["position"] == "1" else ""
            out += (f'<tr{lead}><td class="rk">{s["position"]}</td>'
                    f'<td class="l nm">{rc.driver_pair(s["Driver"])}</td>'
                    f'<td class="l">{rc.team_pair(cons)}</td>'
                    f'<td class="std-pts">{s["points"]}</td></tr>')
        return out

    def rows_c():
        out = ""
        for s in cs["standings"]["ConstructorStandings"][:6]:
            lead = ' class="lead"' if s["position"] == "1" else ""
            out += (f'<tr{lead}><td class="rk">{s["position"]}</td>'
                    f'<td class="l nm">{rc.team_pair(s["Constructor"]["name"])}</td>'
                    f'<td class="std-pts">{s["points"]}</td></tr>')
        return out

    tabs = rc.tabgroup("hs", [
        ("drv", "車手 TOP 6",
         f'<table class="std-table"><thead><tr><th>#</th><th class="l">車手</th><th class="l">車隊</th><th>積分</th></tr></thead><tbody>{rows_d()}</tbody></table>',
         f'截至第 {rnd} 站賽後 · <a href="/standings/" style="color:var(--accent)">完整積分榜 →</a>'),
        ("con", "車隊 TOP 6",
         f'<table class="std-table"><thead><tr><th>#</th><th class="l">車隊</th><th>積分</th></tr></thead><tbody>{rows_c()}</tbody></table>',
         f'截至第 {rnd} 站賽後 · <a href="/standings/" style="color:var(--accent)">完整積分榜 →</a>'),
    ])
    return ('<div class="rc-sec"><h2>積分速覽</h2><span class="ln"></span>'
            '<span class="tg">車手 / 車隊</span></div>' + tabs), rnd


def _next_race_chip(season=rc.SEASON, today=None):
    sch = rc.load_data(season, "schedule.json")
    # 只算「正賽已完」的站——sprint-only round（衝刺賽先出）仍是下一站
    results = {r for r, race, _ in rc.load_results(season) if race}
    if not sch:
        return ""
    today = today or datetime.date.today()
    for race in sch["races"]:
        rnd = int(race["round"])
        d = datetime.date.fromisoformat(race["date"])
        if rnd not in results and d >= today:
            when = rc.taipei_disp(race["date"], race.get("time"))
            sprint = "（衝刺賽週末）" if "Sprint" in race else ""
            return (f'<div class="next-race"><div class="big">下一站　Rd{rnd} {rc.race_zh(race["raceName"])}{sprint}'
                    f'<span class="en">{html_lib.escape(race["raceName"])}</span></div>'
                    f'<div class="when"><span>正賽 · 台北時間</span><b>{when}</b></div></div>')
    return ""


def _latest_podium(season=rc.SEASON):
    results = rc.load_results(season)
    if not results:
        return ""
    rnd, race, sprint = results[-1]
    # sprint-only round：正賽未跑，先秀衝刺賽頒獎台（六/日排程的中間態）
    rows = race["Results"][:3] if race else (sprint or {}).get("SprintResults", [])[:3]
    if not rows:
        return ""
    label = "" if race else "衝刺賽"
    cards = ""
    for res in rows:
        cards += (f'<div class="podium-card"><div class="pos">P{res["position"]}</div>'
                  f'<div class="who">{rc.driver_pair(res["Driver"])}</div>'
                  f'<div class="team">{rc.team_pair(res["Constructor"]["name"])}</div></div>')
    name = rc.race_zh((race or sprint)["raceName"])
    return (f'<div class="rc-sec"><h2>最新賽果 · 第 {rnd} 站{name}{label}</h2>'
            '<span class="ln"></span>'
            '<a class="tg" href="/results/" style="text-decoration:none">全部賽果 →</a></div>'
            f'<div class="podium-grid">{cards}</div>')


def _idx_card(a):
    cover = (f'<img src="/articles/{a["slug"]}/cover.png" alt="" loading="lazy">'
             if (SRC / a["slug"] / "cover.png").exists() else "")
    m = a["meta"]
    return (f'<a class="idx-card" href="/articles/{a["slug"]}/">{cover}<div class="pad">'
            f'<span class="k">{_kicker(m)}</span>'
            f'<h3>{html_lib.escape(m.get("title", a["slug"]))}</h3>'
            f'<p>{html_lib.escape(a["excerpt"][:80])}…</p>'
            f'<div class="dt">{m.get("date","")}</div></div></a>')


def _faq_sec(pairs):
    qa = "".join(f'<div class="qa"><h3>{html_lib.escape(q)}</h3><p>{html_lib.escape(a)}</p></div>'
                 for q, a in pairs)
    return ('<div class="rc-sec"><h2>常見問題</h2><span class="ln"></span></div>'
            f'<section class="rc-faq">{qa}</section>')


def render_home(articles):
    standings_sec, rnd = _standings_mini()
    next_chip = _next_race_chip()
    podium_sec = _latest_podium()
    sch = rc.load_data(rc.SEASON, "schedule.json")
    n_races = f'{len(sch["races"])} 站' if sch and sch.get("races") else "全季"
    tiles = ('<div class="rc-sec"><h2>數據頁</h2><span class="ln"></span></div>'
             '<div class="tiles">'
             '<a class="tile" href="/standings/"><span class="ic">🏆</span>'
             '<span><span class="tt">積分榜</span><span class="ds">車手 · 車隊年度積分</span></span><span class="go">→</span></a>'
             '<a class="tile" href="/calendar/"><span class="ic">🗓️</span>'
             f'<span><span class="tt">賽曆 · 台北時間</span><span class="ds">{n_races}正賽/排位/衝刺時刻</span></span><span class="go">→</span></a>'
             '<a class="tile" href="/results/"><span class="ic">🏁</span>'
             '<span><span class="tt">各站賽果</span><span class="ds">完整官方分類 · 含衝刺賽</span></span><span class="go">→</span></a>'
             '</div>')
    art_sec = ""
    if articles:
        cards = "".join(_idx_card(a) for a in articles[:6])
        art_sec = ('<div class="rc-sec"><h2>深度文章</h2><span class="ln"></span>'
                   '<a class="tg" href="/articles/" style="text-decoration:none">全部文章 →</a></div>'
                   f'<div class="idx-grid">{cards}</div>')
    asof = (f'<div class="dash-asof">⏱ 數據截至第 <b>{rnd}</b> 站賽後 · 每週一台北時間自動更新</div>'
            if rnd else "")

    item_list = {"@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": f"{BASE}/articles/{a['slug']}/",
         "name": a["meta"].get("title", a["slug"])} for i, a in enumerate(articles)]}
    collection = {"@type": "CollectionPage", "@id": f"{BASE}/", "url": f"{BASE}/",
                  "name": SITE["website_name"], "inLanguage": "zh-Hant",
                  "isPartOf": {"@id": f"{BASE}/#website"}, "mainEntity": item_list}
    jsonld = rc.graph_ld([rc.org_node(), rc.website_node(), collection,
                          rc.breadcrumb_node([("首頁", f"{BASE}/")]),
                          rc.faq_node(HOME_FAQ, f"{BASE}/")])
    desc = ("F1 積分榜、台北時間賽曆、各站賽果——非官方繁體中文賽車數據站，"
            "台灣慣用譯名、每週自動更新，加上規則解析與深度專題。")
    body = f"""
  <section class="rc-hero">
    <h1>看懂 F1，<br>用台北時間。</h1>
    <p>積分榜 × 台北時間賽曆 × 各站賽果，每週自動更新；規則解析與譯名對照走深度長文。繁體中文、台灣慣用譯名。</p>
    {asof}
  </section>
  {next_chip}
  {standings_sec}
  {podium_sec}
  {tiles}
  {art_sec}
  {_faq_sec(HOME_FAQ)}"""
    # page_shell 會自動掛「 | 賽車數據誌」suffix → 這裡只給描述性前半，避免站名重複
    return rc.page_shell(SITE["website_name"].split("｜")[1],
                         desc, f"{BASE}/", jsonld, body, "home", extra_css=INDEX_CSS)


def render_articles_index(articles):
    url = f"{BASE}/articles/"
    cards = "".join(_idx_card(a) for a in articles)
    item_list = {"@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": f"{BASE}/articles/{a['slug']}/",
         "name": a["meta"].get("title", a["slug"])} for i, a in enumerate(articles)]}
    coll = {"@type": "CollectionPage", "@id": url, "url": url,
            "name": f"{SITE['org_name']} 深度文章", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{BASE}/#website"}, "mainEntity": item_list}
    jsonld = rc.graph_ld([rc.org_node(), rc.website_node(), coll,
                          rc.breadcrumb_node([("首頁", f"{BASE}/"), ("文章", url)])])
    body = (f'<h1 class="idx-h1">深度文章</h1>'
            f'<div class="idx-intro">規則解析 · 譯名對照 · 賽站專題——長文為主、逐項標註來源，共 {len(articles)} 篇、最新在前。</div>'
            f'<div class="idx-grid">{cards}</div>')
    return rc.page_shell("深度文章", f"賽車數據誌深度文章共 {len(articles)} 篇：F1 規則解析、譯名對照、賽站專題。",
                         url, jsonld, body, "articles", extra_css=INDEX_CSS)


# ---------- RSS ----------

def _rfc822(date_str):
    try:
        d = datetime.date.fromisoformat(str(date_str))
        return d.strftime("%a, %d %b %Y 00:00:00 +0800")
    except ValueError:
        return ""


def render_feed(articles):
    items = ""
    for a in articles[:FEED_MAX]:
        m = a["meta"]
        url = f"{BASE}/articles/{a['slug']}/"
        items += f"""  <item>
    <title>{html_lib.escape(m.get('title', a['slug']))}</title>
    <link>{url}</link>
    <guid>{url}</guid>
    <pubDate>{_rfc822(m.get('date',''))}</pubDate>
    <description>{html_lib.escape(m.get('subtitle', a['excerpt']))}</description>
  </item>
"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{html_lib.escape(SITE['feed_channel_title'])}</title>
  <link>{BASE}/</link>
  <description>{html_lib.escape(SITE['feed_channel_desc'])}</description>
  <language>zh-Hant</language>
{items}</channel>
</rss>
"""


# ---------- llms.txt（build-time 生成，永不 stale） ----------

def render_llms_txt(articles):
    art_lines = "\n".join(
        f"- [{a['meta'].get('title', a['slug'])}]({BASE}/articles/{a['slug']}/)"
        + (f"（{a['meta']['date']}）" if a["meta"].get("date") else "")
        for a in articles[:10])
    return f"""# 賽車數據誌（racing.twtools.cc）— F1 積分榜・台北時間賽曆・各站賽果

> 非官方的繁體中文一級方程式（F1）數據與內容站。提供車手/車隊積分榜、全季賽曆台北時間對照、各站官方分類賽果三個每週自動更新的資料頁，以及規則解析、譯名對照等長青專題。內容以繁體中文撰寫、台灣慣用譯名、台北時間標示，面向台灣讀者。

本站為獨立經營的資訊站，與 Formula 1、Formula One Licensing BV、FIA 及各車隊、車手均無任何官方關係，不使用官方標誌、字體、照片或車隊塗裝視覺，非商業性質。數據來源：Ergast 相容公開 API（jolpica-f1），每次抓取落地 JSON 快照；每週一台北時間自動更新，衝刺賽週末加跑週六日。

## 重點頁面

- [首頁數據儀表板]({BASE}/)：積分速覽、下一站台北時間、最新賽果。
- [積分榜]({BASE}/standings/)：車手與車隊年度積分，台灣慣用譯名＋原文對照。
- [賽曆 · 台北時間]({BASE}/calendar/)：全季 22 站正賽/排位/衝刺賽時刻換算台北時間（UTC+8）。
- [各站賽果]({BASE}/results/)：已完賽站完整官方分類（含衝刺賽）。
- [文章總覽]({BASE}/articles/)：規則解析與對照表長文，逐項標註來源。

## 最新文章

{art_lines}

## 文章與更新

- [RSS feed]({BASE}/feed.xml)：最新深度文章。
- 深度文章：3000 字以上的長文，規則與事實逐項對照 FIA/官方說明查證後發布。

## 使用說明

- 引用本站資料時，請註明資料為非官方整理、並以 FIA 及賽事官方公告為準。
- 內容僅供資訊參考；時間以台北時間（UTC+8）標示。
"""


# ---------- main build ----------

def build():
    if not SRC.exists():
        print(f"❌ {SRC} not found", file=sys.stderr)
        sys.exit(1)

    articles = []
    for d in sorted(SRC.iterdir()):
        if not d.is_dir() or not (d / "index.md").exists():
            continue
        text = (d / "index.md").read_text(encoding="utf-8")
        meta, body = rc.parse_frontmatter(text)
        meta.setdefault("slug", d.name)
        slug = meta["slug"]
        if slug in DRAFT_EXCLUDE:
            print(f"⏭  skip draft (pending review, excluded): {slug}")
            continue
        body = rc.strip_h1(body)
        excerpt = rc.extract_excerpt(body)
        faq = rc.parse_faq(body)
        body_html = md_lib.markdown(body, extensions=["extra", "sane_lists"])
        # 表格包 scroll wrapper（寬表在手機不撐破版面）
        body_html = body_html.replace("<table>", '<div class="prose-tblwrap"><table>').replace(
            "</table>", "</table></div>")
        out_dir = PUB / "articles" / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        for asset in d.iterdir():
            if asset.is_file() and asset.suffix != ".md":
                shutil.copy2(asset, out_dir / asset.name)
        articles.append({"slug": slug, "meta": meta, "excerpt": excerpt,
                         "faq": faq, "body_html": body_html, "out_dir": out_dir})

    # 真下架：曾上線後改回草稿或整篇移除的文章，輸出目錄必須刪掉——
    # 只從 index/sitemap 拿掉不算下架，知道網址的人仍讀得到（含 CI 乾淨 checkout 裡已 commit 的舊產物）
    prune_stale_article_dirs(PUB / "articles", {a["slug"] for a in articles})

    articles.sort(key=lambda a: (str(a["meta"].get("date", "")), a["slug"]), reverse=True)

    # prev/next（時間軸）
    for i, a in enumerate(articles):
        prev_nav = articles[i + 1] if i + 1 < len(articles) else None  # 較舊
        next_nav = articles[i - 1] if i > 0 else None                  # 較新
        html_out = render_article(a["meta"], a["body_html"], a["slug"], a["excerpt"], a["faq"],
                                  prev_nav=prev_nav, next_nav=next_nav)
        (a["out_dir"] / "index.html").write_text(html_out, encoding="utf-8")
        print(f"✅ {a['slug']}")

    PUB.mkdir(parents=True, exist_ok=True)
    (PUB / "index.html").write_text(render_home(articles), encoding="utf-8")
    (PUB / "articles").mkdir(parents=True, exist_ok=True)
    (PUB / "articles" / "index.html").write_text(render_articles_index(articles), encoding="utf-8")
    (PUB / "feed.xml").write_text(render_feed(articles), encoding="utf-8")
    (PUB / "llms.txt").write_text(render_llms_txt(articles), encoding="utf-8")
    (PUB / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")

    # base sitemap（整個覆寫；gen-* 之後 re-merge 自己的 path）
    urls = [f"{BASE}/", f"{BASE}/articles/"] + [f"{BASE}/articles/{a['slug']}/" for a in articles]
    body = "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
    (PUB / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}</urlset>\n", encoding="utf-8")
    print(f"🏠 index + articles index + feed + llms.txt + sitemap ({len(articles)} articles) → {PUB}/")


if __name__ == "__main__":
    build()
