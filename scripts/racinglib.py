#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""racinglib.py — racing.twtools.cc 共用庫（站身分/主題/頁面外殼/JSON-LD/解析器）。

架構 clone 自 baseball-tools 的 build-articles 共用層，收斂成單站版：
- 站身分單一資料源 config/site.json（GA4 未開通前 ga_id 缺席 → 不輸出 tag）
- 全暗色「計時螢幕」主題家族：碳黑底＋單一 accent（預設最速圈紫），localStorage 持久化。
  配色刻意避開任何車隊塗裝聯想（IP 紅線：零官方素材、不用車隊視覺）。
- JSON-LD helpers（org/website/breadcrumb/FAQ）；FAQ schema 永遠鏡射頁面可見文字。
- frontmatter / FAQ 解析器：FAQ 必須是「## 常見問題」下的 ### 問題 + 段落答案
  （### 才吐 schema——沿用 foootball/baseball 慣例）。
"""
import datetime
import html as html_lib
import json
import pathlib
import re
try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = json.loads((ROOT / "config" / "site.json").read_text(encoding="utf-8"))
# 單一賽季設定源：換季只改 site.json 的 season，首頁/資料頁/編排器全跟著走
SEASON = int(SITE.get("season", 2026))
BASE = SITE["base"]
PUB = ROOT / "public-racing"
TAIPEI = ZoneInfo("Asia/Taipei") if ZoneInfo else None


# ---------- GA4（未開通前 site.json 無 ga_id → 空字串，開通後填 id 即全站生效） ----------

def ga_snippet(site: dict = None) -> str:
    gid = (site or SITE).get("ga_id")
    if not gid:
        return "<!-- GA4: 待 property 開通後於 config/site.json 填 ga_id -->"
    return (
        "<!-- Google tag (gtag.js) -->\n"
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={gid}"></script>\n'
        "<script>\n"
        "  window.dataLayer = window.dataLayer || [];\n"
        "  function gtag(){dataLayer.push(arguments);}\n"
        "  gtag('js', new Date());\n"
        f"  gtag('config', '{gid}');\n"
        "</script>"
    )


# ---------- 主題家族（v2.2「定案 D：深色重心」；鍵 rc-theme） ----------
# Design 專案「F1 數據站 UI 優化」mocks/standings.html v2.2：亮色莫蘭迪底＋每主題暖色調文字系
# ＋--ink 深色錨（sticky header/表頭/切換器走深色，見 DARK_ANCHOR_CSS）。
# ⚠️ IP 紅線改動：mock 的 carbon accent 原為 #e10600（F1 官方品牌色精確色號、label「F1 紅」）
# → 依 IP 紅線改用非官方色號的賽車紅 #d63a2f、label「賽車紅」（2026-07-19，Charlie 可覆議）。
# RC_THEMES 只供切換器/JS 用：key, 中文 label, 圓點色（=該主題 accent）。
RC_THEMES = [
    ("carbon",   "賽車紅", "#d63a2f"),
    ("asphalt",  "灰綠",   "#1f9d6b"),
    ("midnight", "霧藍金", "#c8971f"),
    ("gravel",   "陶土",   "#d1652f"),
    ("silver",   "岩灰",   "#4f7cc9"),
]
RC_THEME_KEYS = [t[0] for t in RC_THEMES]


def _theme_tokens_css() -> str:
    """五主題 token 區塊（verbatim 自 v2.2 mock，僅 carbon accent 系依 IP 紅線換色號）。
    每主題有各自的 fg/line/shadow 暖色調與 --ink 深色錨，不再共用文字色。"""
    return """
:root[data-theme="carbon"] {
  --surface:#fdf7f7; --surface-2:#f8ecec; --surface-3:#f1e0e0;
  --fg:#241a1c; --fg-soft:#493c40; --dim:#786a6e; --faint:#a6989c;
  --line:rgba(90,20,20,0.12); --line-2:rgba(90,20,20,0.22);
  --sheet-shadow:rgba(150,30,30,0.13); --scrim:rgba(50,20,20,0.32);
  --bg:#f3e9e9; --bg-glow:#fbf3f3; --rc-header-bg:rgba(253,247,247,0.88);
  --accent:#d63a2f; --accent-bright:#b92f25; --accent-ink:#ffffff;
  --accent-soft:rgba(214,58,47,0.10); --accent-line:rgba(214,58,47,0.40); --accent-glow:rgba(214,58,47,0.32);
  --ink:#191114;
}
:root[data-theme="asphalt"] {
  --surface:#f4f8f6; --surface-2:#eaf1ee; --surface-3:#dee9e5;
  --fg:#22322c; --fg-soft:#42544c; --dim:#6f857b; --faint:#97ada3;
  --line:rgba(30,70,54,0.13); --line-2:rgba(30,70,54,0.24);
  --sheet-shadow:rgba(40,110,80,0.14); --scrim:rgba(20,50,38,0.32);
  --bg:#e6efeb; --bg-glow:#f0f7f4; --rc-header-bg:rgba(244,248,246,0.86);
  --accent:#1f9d6b; --accent-bright:#158a5c; --accent-ink:#f7fbfa;
  --accent-soft:rgba(31,157,107,0.13); --accent-line:rgba(31,157,107,0.42); --accent-glow:rgba(31,157,107,0.32);
  --ink:#10261f;
}
:root[data-theme="midnight"] {
  --surface:#faf7ef; --surface-2:#f2ede1; --surface-3:#e9e2d1;
  --fg:#33301f; --fg-soft:#54503a; --dim:#8a856c; --faint:#b0ab90;
  --line:rgba(80,66,20,0.13); --line-2:rgba(80,66,20,0.24);
  --sheet-shadow:rgba(150,120,40,0.15); --scrim:rgba(60,50,20,0.32);
  --bg:#f0eadb; --bg-glow:#f8f3e7; --rc-header-bg:rgba(250,247,239,0.86);
  --accent:#c8971f; --accent-bright:#b5851a; --accent-ink:#241c05;
  --accent-soft:rgba(200,151,31,0.14); --accent-line:rgba(200,151,31,0.42); --accent-glow:rgba(200,151,31,0.32);
  --ink:#241c0e;
}
:root[data-theme="gravel"] {
  --surface:#faf6f1; --surface-2:#f2ebe3; --surface-3:#e9dfd3;
  --fg:#3a271c; --fg-soft:#5a4536; --dim:#8f7863; --faint:#b59e8b;
  --line:rgba(90,50,20,0.13); --line-2:rgba(90,50,20,0.24);
  --sheet-shadow:rgba(160,90,40,0.15); --scrim:rgba(60,36,18,0.32);
  --bg:#f0eae2; --bg-glow:#f8f3ec; --rc-header-bg:rgba(250,246,241,0.86);
  --accent:#d1652f; --accent-bright:#bf5522; --accent-ink:#2a1408;
  --accent-soft:rgba(209,101,47,0.14); --accent-line:rgba(209,101,47,0.42); --accent-glow:rgba(209,101,47,0.32);
  --ink:#2a1a11;
}
:root[data-theme="silver"] {
  --surface:#f6f8f9; --surface-2:#edf0f2; --surface-3:#e2e7ea;
  --fg:#26313c; --fg-soft:#46515c; --dim:#728290; --faint:#9aa8b4;
  --line:rgba(30,60,90,0.13); --line-2:rgba(30,60,90,0.24);
  --sheet-shadow:rgba(40,90,150,0.14); --scrim:rgba(20,40,60,0.32);
  --bg:#eaeef1; --bg-glow:#f3f6f8; --rc-header-bg:rgba(246,248,249,0.88);
  --accent:#4f7cc9; --accent-bright:#3f6cbd; --accent-ink:#08161f;
  --accent-soft:rgba(79,124,201,0.14); --accent-line:rgba(79,124,201,0.42); --accent-glow:rgba(79,124,201,0.32);
  --ink:#161a22;
}
"""


SHARED_TOKENS_CSS = """
:root {
  --radius: 12px;
  --radius-sm: 8px;
  --font-display: 'Chakra Petch', 'Noto Sans TC', sans-serif;
  --font-ui: 'Archivo', 'Noto Sans TC', -apple-system, BlinkMacSystemFont, 'PingFang TC', 'Microsoft JhengHei', sans-serif;
  --font-mono: 'Chakra Petch', ui-monospace, 'SF Mono', Menlo, monospace;
  /* 頒獎台金屬色與狀態色（跨主題共用，非車隊色） */
  --p1:#c39b3e; --p2:#8fa0b5; --p3:#b3744b;
  --dnf:#c2605e;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  background: var(--bg); color: var(--fg); font-family: var(--font-ui);
  line-height: 1.6; -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
}
body {
  min-height: 100vh; padding: 0 16px 110px; position: relative;
  background: radial-gradient(130% 72% at 50% -12%, var(--bg-glow) 0%, transparent 56%), var(--bg);
}
body::before {
  content: ''; position: fixed; inset: 0; pointer-events: none; z-index: 0; mix-blend-mode: multiply; opacity: 0.5;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.05'/%3E%3C/svg%3E");
}
body::after { /* 起跑線：視窗頂部的速度光帶 */
  content: ''; position: fixed; top: 0; left: 0; right: 0; height: 2px; z-index: 200; pointer-events: none;
  background: linear-gradient(90deg, var(--accent) 0%, var(--accent-line) 40%, transparent 78%); opacity: .85;
}
a { color: var(--accent); } a:hover { color: var(--accent-bright); }
.container { max-width: 980px; margin: 0 auto; position: relative; z-index: 1; }
""" + _theme_tokens_css()

THEME_SWITCH_CSS = """
.theme-switch {
  position: fixed; top: 14px; right: 16px; z-index: 150;
  display: flex; align-items: center; gap: 11px;
  background: color-mix(in srgb, var(--surface) 86%, transparent);
  border: 1px solid var(--line); border-radius: 99px;
  padding: 7px 13px 7px 14px; box-shadow: 0 6px 22px rgba(70,70,90,0.16);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
}
.ts-label { font-family: var(--font-mono); font-size: 10px; letter-spacing: 1.5px; color: var(--dim); text-transform: uppercase; }
.ts-dots { display: flex; gap: 8px; }
.ts-dot {
  width: 19px; height: 19px; border-radius: 50%; padding: 0; cursor: pointer;
  background: var(--sw); border: 2px solid var(--surface);
  box-shadow: 0 0 0 1px var(--line-2);
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}
.ts-dot:hover { transform: scale(1.14); }
.ts-dot.active { box-shadow: 0 0 0 2px var(--sw); transform: scale(1.05); }
@media (max-width: 520px) {
  .theme-switch { top: 10px; right: 10px; padding: 6px 11px; gap: 9px; }
  .ts-label { display: none; }
}
"""

THEME_SWITCH_HTML = (
    '\n<div class="theme-switch">\n  <span class="ts-label">配色</span>\n  <div class="ts-dots">\n'
    + "".join(
        f'    <button class="ts-dot" data-theme="{k}" onclick="setTheme(\'{k}\')" style="--sw:{acc}" aria-label="{zh}"></button>\n'
        for k, zh, acc, *_ in RC_THEMES)
    + '  </div>\n</div>\n')

THEME_SWITCH_JS = f"""
const THEMES = {RC_THEME_KEYS};
function setTheme(t) {{
  if (!THEMES.includes(t)) t = 'carbon';
  document.documentElement.dataset.theme = t;
  try {{ localStorage.setItem('rc-theme', t); }} catch (e) {{}}
  document.querySelectorAll('.ts-dot').forEach(d => d.classList.toggle('active', d.dataset.theme === t));
}}
(function initTheme() {{
  let t = 'carbon';
  try {{ t = localStorage.getItem('rc-theme') || 'carbon'; }} catch (e) {{}}
  setTheme(t);
}})();
"""


# ---------- 站頭/站尾 ----------

SITE_HEADER_CSS = """
.site-header {
  position: sticky; top: 0; z-index: 30;
  display: flex; justify-content: space-between; align-items: center;
  gap: 14px 24px; flex-wrap: wrap;
  padding: 14px 0; margin-bottom: 34px;
  background: var(--rc-header-bg); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--line);
}
.brand-block { display: flex; flex-direction: column; gap: 5px; }
.brand-mark {
  font-family: var(--font-display); font-weight: 700; font-size: 26px; line-height: 1;
  color: var(--accent); letter-spacing: 2px; font-style: italic;
  text-decoration: none; transition: color 0.15s ease;
  display: inline-flex; align-items: center; gap: 9px;
}
.brand-mark::before { /* 自繪速度斜紋 */
  content: ''; width: 17px; height: 15px; flex: none;
  background: repeating-linear-gradient(-62deg, var(--accent) 0 3.5px, transparent 3.5px 8px);
}
.brand-mark:hover { color: var(--accent-bright); }
.brand-tag {
  font-family: var(--font-mono); font-size: 10.5px;
  letter-spacing: 2.5px; color: var(--dim); text-transform: uppercase;
}
.site-nav {
  display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
  font-family: var(--font-ui); font-size: 13px;
}
.site-nav a { color: var(--dim); text-decoration: none; letter-spacing: 1px; font-size: 13px;
  padding: 6px 13px; border-radius: 999px; transition: color 0.15s ease, background 0.15s ease; }
.site-nav a:hover { color: var(--accent); background: var(--accent-soft); }
.site-nav a.active { color: var(--accent-ink); background: var(--accent); font-weight: 700; }
@media (max-width: 580px) { .brand-mark { font-size: 21px; } }
.site-disclaimer { font-size: 11px; color: var(--faint); line-height: 1.7; text-align: center; max-width: 640px; margin: 18px auto 0; }
.site-disclaimer span { opacity: 0.75; }
.article-footer { margin-top: 64px; padding-top: 28px; border-top: 1px solid var(--line); text-align: center; }
.foot-links { display: flex; gap: 22px; justify-content: center; font-size: 13px; }
.foot-links a { color: var(--dim); text-decoration: none; }
.foot-links a:hover { color: var(--accent); }
"""

# 非官方聲明（全 surface footer）——商標紅線三層防護之一（另兩層：域名避 f1 字樣、零官方素材）
DISCLAIMER_HTML = (
    '<div class="site-disclaimer">本站為非官方賽車資訊站，與 Formula 1、FIA 及各車隊、車手均無任何關聯或授權；'
    '數據整理自公開來源並標註出處，賽道示意均依公開資料自行重繪。<br>'
    '<span>Unofficial fan-made site · Not affiliated with, endorsed by, or sponsored by '
    'Formula 1, Formula One Licensing BV, the FIA, or any team.</span></div>'
)

# twtools 生態系姊妹站互連（名稱取自各站現行 title；渲染時排除本站自己；自家內鏈不加 nofollow）
SISTER_SITES = [
    ("TWTools — 打工牛馬的線上工具箱", "https://twtools.cc/"),
    ("aire — AI Tool Atlas·AI 工具圖鑑", "https://aire.twtools.cc/"),
    ("樹洞21號 — 匿名 AI 心事平台", "https://tree.twtools.cc/"),
    ("@foootball — 2026 世界盃賽程", "https://foootball.twtools.cc/"),
    ("@baseball — 中職 CPBL＋MLB 深度戰報", "https://baseball.twtools.cc/"),
    ("dvdmaru — 把事實和敘事分開來看", "https://dvdmaru.com/"),
]


def sister_sites_html(site: dict = None) -> str:
    base = (site or SITE)["base"].rstrip("/") + "/"
    links = "　·　".join(
        f'<a href="{u}" style="color:var(--dim);text-decoration:none">{html_lib.escape(n)}</a>'
        for n, u in SISTER_SITES if u != base)
    return ('<div class="sister-sites" style="margin-top:12px;font-size:12px;'
            f'color:var(--dim);line-height:2;text-align:center">姊妹站　{links}</div>')


def site_header_html(active: str, site: dict = None) -> str:
    site = site or SITE
    parts = []
    for n in site.get("nav", []):
        cls = ' class="active"' if n.get("key") == active else ""
        parts.append(f'<a href="{n["href"]}"{cls}>{n["label"]}</a>')
    links = "\n      ".join(parts)
    return f"""
  <header class="site-header">
    <div class="brand-block">
      <a href="/" class="brand-mark">{site["brand_mark"]}</a>
      <div class="brand-tag">{site["brand_tag"]}</div>
    </div>
    <nav class="site-nav">
      {links}
    </nav>
  </header>
"""


def site_footer_html(site: dict = None) -> str:
    site = site or SITE
    link_parts = []
    for l in site.get("footer_links", []):
        target = ' target="_blank" rel="noopener"' if l.get("external") else ""
        link_parts.append(f'<a href="{l["href"]}"{target}>{l["label"]}</a>')
    links = "\n      ".join(link_parts)
    return f"""  <div class="article-footer">
    <div class="foot-links">
      {links}
    </div>
    {DISCLAIMER_HTML}
    {sister_sites_html(site)}
  </div>"""


# ---------- JSON-LD helpers ----------

def _ld(obj: dict) -> str:
    payload = obj if "@context" in obj else {"@context": "https://schema.org", **obj}
    return ('<script type="application/ld+json">'
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            + "</script>")


def graph_ld(nodes: list) -> str:
    nodes = [n for n in nodes if n]
    return _ld({"@context": "https://schema.org", "@graph": nodes}) if nodes else ""


def org_node(site: dict = None) -> dict:
    site = site or SITE
    base = site["base"]
    node = {"@type": "Organization", "@id": f"{base}/#org",
            "name": site["org_name"], "url": f"{base}/"}
    if site.get("org_same_as"):
        node["sameAs"] = site["org_same_as"]
    return node


def website_node(site: dict = None) -> dict:
    site = site or SITE
    base = site["base"]
    return {"@type": "WebSite", "@id": f"{base}/#website",
            "name": site["website_name"], "url": f"{base}/",
            "inLanguage": "zh-Hant", "publisher": {"@id": f"{base}/#org"}}


def breadcrumb_node(items: list) -> dict:
    elements = []
    for i, (name, url) in enumerate(items):
        el = {"@type": "ListItem", "position": i + 1, "name": name}
        if url:
            el["item"] = url
        elements.append(el)
    return {"@type": "BreadcrumbList", "itemListElement": elements}


def faq_node(pairs, page_url: str):
    """FAQPage schema——只鏡射頁面上真實可見的問答，不放編輯評分、不杜撰。"""
    if not pairs:
        return None
    return {"@type": "FAQPage", "@id": f"{page_url}#faq",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in pairs]}


# ---------- frontmatter / FAQ 解析（沿用 foootball/baseball 慣例） ----------

def parse_frontmatter(text: str):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if kv:
            k, v = kv.group(1), kv.group(2).strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            meta[k] = v
    return meta, text[m.end():]


def strip_h1(body: str) -> str:
    return re.sub(r"^#\s+.*\n+", "", body, count=1)


def _strip_inline_md(s: str) -> str:
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    return s.strip()


def parse_faq(body: str):
    """抽「## 常見問題」區塊的 ###-gated 問答（### 才吐 schema——非 ### 的內容不會進 FAQPage）。"""
    m = re.search(r"^##\s*常見問題.*?$(.*?)(?=^##\s|\Z)", body, re.S | re.M)
    if not m:
        return []
    section = m.group(1)
    pairs = []
    for qm in re.finditer(r"^###\s+(.+?)$\n(.*?)(?=^###\s|\Z)", section, re.S | re.M):
        q = _strip_inline_md(qm.group(1))
        a = _strip_inline_md(re.sub(r"\s+", " ", qm.group(2)))
        if q and a:
            pairs.append((q, a))
    return pairs


def extract_excerpt(body: str, length: int = 120) -> str:
    for para in body.split("\n\n"):
        p = _strip_inline_md(re.sub(r"\s+", " ", para)).strip()
        if p and not p.startswith("#") and not p.startswith("|") and not p.startswith("---"):
            return p[:length]
    return ""


# ---------- 台北時間 ----------

def to_taipei(date_str: str, time_str: str):
    """Ergast 的 date + time（UTC）→ 台北 datetime；time 缺席回 None。"""
    if not date_str or not time_str or TAIPEI is None:
        return None
    t = time_str.replace("Z", "")
    dt = datetime.datetime.fromisoformat(f"{date_str}T{t}+00:00")
    return dt.astimezone(TAIPEI)


WEEKDAY_ZH = ["一", "二", "三", "四", "五", "六", "日"]


def taipei_disp(date_str: str, time_str: str) -> str:
    """→「3/8（日）12:00」；無時間回「3/8」。"""
    dt = to_taipei(date_str, time_str)
    if dt is None:
        if date_str:
            d = datetime.date.fromisoformat(date_str)
            return f"{d.month}/{d.day}"
        return ""
    return f"{dt.month}/{dt.day}（{WEEKDAY_ZH[dt.weekday()]}）{dt:%H:%M}"


# ---------- 中文名對照（車手/車隊：scripts/driver-zh.json、team-zh.json；站名/賽道內建） ----------

def _load_zh(fname):
    p = ROOT / "scripts" / fname
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


DRIVER_ZH = _load_zh("driver-zh.json")
TEAM_ZH = _load_zh("team-zh.json")

RACE_ZH = {
    "Australian Grand Prix": "澳洲站", "Chinese Grand Prix": "中國站",
    "Japanese Grand Prix": "日本站", "Miami Grand Prix": "邁阿密站",
    "Canadian Grand Prix": "加拿大站", "Monaco Grand Prix": "摩納哥站",
    "Barcelona Grand Prix": "巴塞隆納站", "Austrian Grand Prix": "奧地利站",
    "British Grand Prix": "英國站", "Belgian Grand Prix": "比利時站",
    "Hungarian Grand Prix": "匈牙利站", "Dutch Grand Prix": "荷蘭站",
    "Italian Grand Prix": "義大利站", "Spanish Grand Prix": "西班牙站（馬德里）",
    "Azerbaijan Grand Prix": "亞塞拜然站", "Singapore Grand Prix": "新加坡站",
    "United States Grand Prix": "美國站", "Mexico City Grand Prix": "墨西哥城站",
    "Brazilian Grand Prix": "巴西站", "Las Vegas Grand Prix": "拉斯維加斯站",
    "Qatar Grand Prix": "卡達站", "Abu Dhabi Grand Prix": "阿布達比站",
    "Bahrain Grand Prix": "巴林站", "Saudi Arabian Grand Prix": "沙烏地站",
}

CIRCUIT_ZH = {
    "albert_park": "亞伯特公園賽道（墨爾本）", "shanghai": "上海國際賽車場",
    "suzuka": "鈴鹿賽道", "miami": "邁阿密國際賽道",
    "villeneuve": "維倫紐夫賽道（蒙特婁）", "monaco": "摩納哥街道賽道",
    "catalunya": "加泰隆尼亞賽道（巴塞隆納）", "red_bull_ring": "紅牛環（史匹爾柏格）",
    "silverstone": "銀石賽道", "spa": "斯帕賽道（Spa-Francorchamps）",
    "hungaroring": "匈牙利賽道（Hungaroring）", "zandvoort": "贊德沃特賽道",
    "monza": "蒙札賽道", "madring": "馬德里賽道（Madring）",
    "baku": "巴庫街道賽道", "marina_bay": "濱海灣街道賽道（新加坡）",
    "americas": "美洲賽道（奧斯汀）", "rodriguez": "羅德里格斯兄弟賽道（墨西哥城）",
    "interlagos": "英特拉哥斯賽道（聖保羅）", "vegas": "拉斯維加斯街道賽道",
    "losail": "羅賽爾國際賽道", "yas_marina": "亞斯碼頭賽道（阿布達比）",
}


def race_zh(name: str) -> str:
    return RACE_ZH.get(name, name)


def circuit_zh(cid: str, fallback: str = "") -> str:
    return CIRCUIT_ZH.get(cid, fallback or cid)


def driver_zh(driver: dict) -> str:
    """Ergast Driver dict → 繁中譯名（familyName 為主）；查無對照回原文姓氏。"""
    did = driver.get("driverId", "")
    if did in DRIVER_ZH:
        return DRIVER_ZH[did]
    return driver.get("familyName", did)


def team_zh(name_or_id: str) -> str:
    return TEAM_ZH.get(name_or_id, name_or_id)


# ---------- 中英對照（站規：人名／車隊／賽道／站名一律中英並列） ----------
# 譯名不統一是繁中賽車內容的老問題（同一車手台港陸三種寫法），並列原文讓讀者能自行對照、
# 也讓搜尋引擎與 AI 引擎兩種寫法都抓得到。窄表格用姓氏、寬版位用全名，靠 full 參數切換。

def _en(text: str) -> str:
    """原文附註 span；與中文之間用全形空格分隔（避免半形空格被壓掉）。"""
    return f'<span class="zh-en">　{html_lib.escape(text)}</span>' if text else ""


def driver_pair(driver: dict, full: bool = False) -> str:
    """中文譯名＋原文。full=True 給全名（寬表格如積分榜），否則只給姓氏（窄表格）。"""
    if full:
        en = f'{driver.get("givenName", "")} {driver.get("familyName", "")}'.strip()
    else:
        en = driver.get("familyName", "")
    zh = driver_zh(driver)
    return f"{zh}{_en(en)}" if en and en != zh else zh


def team_pair(name: str) -> str:
    zh = team_zh(name)
    return f"{zh}{_en(name)}" if name and name != zh else zh


def circuit_pair(cid: str, fallback: str = "") -> str:
    zh = circuit_zh(cid, fallback)
    return f"{zh}{_en(fallback)}" if fallback and fallback != zh else zh


def race_pair(name: str) -> str:
    zh = race_zh(name)
    return f"{zh}{_en(name)}" if name and name != zh else zh


# ---------- 資料快照讀取 ----------

def load_data(season: int, name: str):
    p = ROOT / "data" / str(season) / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load_results(season: int, base=None):
    """回 [(round:int, race_dict_or_None, sprint_dict_or_None)]，round 升冪。
    race=None＝sprint-only round（衝刺賽已跑、正賽未跑，六/日排程的中間態）——
    消費端判斷「已完賽」一律看 race 是否存在，不能只看 round 有沒有出現。"""
    base = base or (ROOT / "data" / str(season) / "results")
    out = []
    if not base.exists():
        return out
    rounds = {int(p.stem.split("-")[1])
              for pat in ("round-[0-9][0-9].json", "round-[0-9][0-9]-sprint.json")
              for p in base.glob(pat)}
    for rnd in sorted(rounds):
        rp = base / f"round-{rnd:02d}.json"
        race = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else None
        sp = base / f"round-{rnd:02d}-sprint.json"
        sprint = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None
        out.append((rnd, race, sprint))
    return out


# ---------- 頁面外殼 ----------

FONTS_HTML = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:ital,wght@0,400;0,600;0,700;1,700'
    '&family=Archivo:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">'
)

# 資料頁通用 CSS（表格/tabs/FAQ；與文章頁共用 tokens）
DATA_CSS = """
.pg-h1 { font-family: var(--font-display); font-size: clamp(28px,5vw,42px); line-height:1.15; margin: 4px 0 6px; font-style: italic; }
.pg-h1::after { content:''; display:block; width:74px; height:4px; margin-top:10px;
  background: repeating-linear-gradient(-62deg, var(--accent) 0 8px, transparent 8px 14px); }
.pg-sub { color: var(--fg-soft); font-size: 15px; margin: 12px 0 22px; }
.pg-sub b { color: var(--accent); }
.sec-h { font-family: var(--font-display); font-size: 20px; letter-spacing: .5px; margin: 40px 0 8px; font-style: italic;
  display:flex; align-items:center; gap:10px; }
.sec-h::before { content:''; width:15px; height:11px; flex:none;
  background: repeating-linear-gradient(-62deg, var(--accent) 0 3px, transparent 3px 7px); }
.tabs > input { position:absolute; opacity:0; width:0; height:0; }
.tablabels { display:flex; flex-wrap:wrap; gap:4px; margin: 8px 0 20px; border-bottom:1px solid var(--line); }
.tablabels label { cursor:pointer; padding:9px 18px; font-size:14.5px; font-weight:700; color:var(--dim);
  font-family: var(--font-display); font-style: italic; letter-spacing:.5px;
  border-bottom:2px solid transparent; margin-bottom:-1px; transition:color .15s, border-color .15s, background .15s; }
.tablabels label:hover { color: var(--fg); background: var(--accent-soft); }
.panel { display:none; }
/* 計時螢幕表格：表頭 mono 大寫、前三行金/銀/銅色條、領先者整行強調、數字 tabular */
.std-table { width:100%; border-collapse:collapse; margin: 8px 0 14px; font-size: 14.5px; }
.std-table th, .std-table td { padding: 10px 8px; text-align:center; border-bottom:1px solid var(--line); white-space:nowrap; }
.std-table thead th { font-family: var(--font-mono); color: var(--dim); font-weight:600; font-size:10.5px;
  letter-spacing:1.8px; text-transform:uppercase; border-bottom:1px solid var(--line-2); }
.std-table td.l, .std-table th.l { text-align:left; white-space:normal; }
/* 中英對照的原文附註（人名/車隊/賽道/站名共用；窄螢幕改成獨立一行避免撐爆表格） */
.zh-en { color: var(--faint); font-size: 12px; font-weight: 500; font-family: var(--font-ui); }
@media (max-width: 640px) { .zh-en { display:block; margin-left:0; font-size:11px; } }
.std-table td.rk { color:var(--dim); font-family:var(--font-mono); font-style:italic; font-weight:700; font-size:13px;
  font-variant-numeric: tabular-nums; }
.std-table tbody tr { transition: background .12s ease; }
.std-table tbody tr:hover { background: color-mix(in srgb, var(--surface-2) 60%, transparent); }
.std-table tbody tr:nth-child(1) { box-shadow: inset 3px 0 0 var(--p1); }
.std-table tbody tr:nth-child(2) { box-shadow: inset 3px 0 0 var(--p2); }
.std-table tbody tr:nth-child(3) { box-shadow: inset 3px 0 0 var(--p3); }
.std-table tbody tr:nth-child(1) td.rk { color: var(--p1); font-size:15px; }
.std-table tbody tr:nth-child(2) td.rk { color: var(--p2); font-size:15px; }
.std-table tbody tr:nth-child(3) td.rk { color: var(--p3); font-size:15px; }
.std-table tr.lead td { background: var(--accent-soft); }
.std-table tr.lead td.nm { font-weight:800; }
.std-pts { color: var(--accent); font-weight:800; font-family: var(--font-mono); font-size:15px; font-variant-numeric: tabular-nums; }
.st-status { color: var(--dnf); font-size:12px; font-style: italic; }
.tbl-scroll { overflow-x:auto; scrollbar-width: thin; scrollbar-color: var(--line-2) transparent; }
.asof-note { color:var(--dim); font-size:12.5px; line-height:1.6; margin: 24px 0 8px; border-top:1px solid var(--line); padding-top:14px; }
.pg-faq { margin-top: 8px; display: grid; gap: 10px; }
.pg-faq .qa { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 14px 18px; }
.pg-faq h3 { font-size: 15px; font-weight: 800; color: var(--fg); margin: 0 0 6px; line-height: 1.45; }
.pg-faq p { font-size: 13.5px; color: var(--fg-soft); line-height: 1.7; margin: 0; }
/* 場次時刻 chip（賽曆＋首頁看板共用；.q=排位 .s=衝刺 .race=正賽） */
.ses { display:inline-flex; align-items:baseline; gap:7px; border:1px solid var(--line); border-radius:6px;
  padding:4px 10px; background: color-mix(in srgb, var(--surface-2) 65%, transparent);
  font-family: var(--font-mono); font-size:12px; color:var(--fg-soft); white-space:nowrap; font-variant-numeric: tabular-nums; }
.ses b { font-family: var(--font-ui); font-weight:600; font-size:11px; color:var(--dim); }
.ses.q { border-color: var(--accent-line); } .ses.q b { color: var(--accent); }
.ses.s b { font-style: italic; color: var(--fg-soft); }
.ses.race { border-color: var(--accent); background: var(--accent-soft); } .ses.race b { color: var(--accent); }
"""

# 深色重心（v2.2 定案 D）：sticky header／表頭／切換器壓 --ink 深色，accent 點狀用。
# 必須排在所有元件 CSS 之後（覆寫 SITE_HEADER_CSS/DATA_CSS/THEME_SWITCH_CSS 的亮色版）。
DARK_ANCHOR_CSS = """
.site-header{background:var(--ink);border-bottom:1px solid rgba(255,255,255,.12)}
.brand-mark{color:#fff}
.brand-tag{color:rgba(255,255,255,.55)}
.site-nav a{color:rgba(255,255,255,.68)}
.site-nav a:hover{color:#fff;background:rgba(255,255,255,.12)}
.site-nav a.active{color:var(--accent-ink);background:var(--accent)}
.std-table thead th{background:var(--ink);color:rgba(255,255,255,.72);border-bottom-color:var(--ink)}
.theme-switch{background:var(--ink);border-color:rgba(255,255,255,.16)}
.ts-label{color:rgba(255,255,255,.6)}
.ts-dot{border-color:var(--ink)}
"""


def tabgroup(group: str, tabs) -> str:
    """CSS-only tabs（radio + :checked）：所有 panel 都在 DOM（GEO-safe，crawler 全看得到）。
    tabs = [(id, label, body_html, note_html_or_empty)]；第一個是預設。"""
    inputs = "".join(
        f'<input type="radio" name="{group}" id="{group}-{tid}"{" checked" if i == 0 else ""}>'
        for i, (tid, _, _, _) in enumerate(tabs))
    labels = "".join(f'<label for="{group}-{tid}">{lbl}</label>' for tid, lbl, _, _ in tabs)
    rules = "".join(
        f'#{group}-{tid}:checked~.tablabels label[for="{group}-{tid}"]'
        '{color:var(--accent);border-bottom-color:var(--accent)}'
        f'#{group}-{tid}:checked~.panel-{group}-{tid}{{display:block}}'
        for tid, _, _, _ in tabs)
    panels = "".join(
        f'<div class="panel panel-{group}-{tid}">{body}'
        + (f'<div class="asof-note" style="border-top:none;padding-top:0">{note}</div>' if note else "")
        + '</div>'
        for tid, _, body, note in tabs)
    return f'<style>{rules}</style><div class="tabs">{inputs}<div class="tablabels">{labels}</div>{panels}</div>'


def faq_html(pairs) -> str:
    qa = "".join(
        f'<div class="qa"><h3>{html_lib.escape(q)}</h3><p>{html_lib.escape(a)}</p></div>'
        for q, a in pairs)
    return f'<h2 class="sec-h">常見問題</h2><section class="pg-faq">{qa}</section>'


def page_shell(title: str, desc: str, canonical: str, jsonld: str, body: str,
               active: str, extra_css: str = "", og_image: str = "") -> str:
    """資料頁/列表頁共用外殼（文章頁另有 render；共用 tokens/header/footer/theme）。"""
    og_img = ""
    if og_image:
        og_img = (f'<meta property="og:image" content="{og_image}">\n'
                  '<meta property="og:image:width" content="1200">\n'
                  '<meta property="og:image:height" content="630">\n'
                  '<meta name="twitter:card" content="summary_large_image">\n'
                  f'<meta name="twitter:image" content="{og_image}">\n')
    return f"""<!DOCTYPE html>
<html lang="zh-Hant" data-theme="{SITE['default_theme']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_lib.escape(title)} | {SITE['title_suffix']}</title>
<meta name="description" content="{html_lib.escape(desc)}">
<meta property="og:title" content="{html_lib.escape(title)}">
<meta property="og:description" content="{html_lib.escape(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="{SITE['org_name']}">
<meta property="og:locale" content="zh_TW">
{og_img}<link rel="canonical" href="{canonical}">
{jsonld}
{FONTS_HTML}
{ga_snippet()}
<style>
{SHARED_TOKENS_CSS}
{THEME_SWITCH_CSS}
{SITE_HEADER_CSS}
{DATA_CSS}
{extra_css}
{DARK_ANCHOR_CSS}
</style>
</head>
<body>
{THEME_SWITCH_HTML}
<div class="container">{site_header_html(active)}
{body}
{site_footer_html()}
</div>
<script>{THEME_SWITCH_JS}</script>
</body>
</html>
"""


# ---------- sitemap re-merge（build-articles 整個覆寫 → 各 generator 只換自己的 path） ----------

def sitemap_merge(own_paths: list, drop_pattern: str):
    """own_paths: 本 generator 擁有的完整 URL list；drop_pattern: 從既有 sitemap 剔除的子字串。"""
    sm = PUB / "sitemap.xml"
    keep = [u for u in re.findall(r"<loc>([^<]+)</loc>", sm.read_text(encoding="utf-8"))
            if drop_pattern not in u] if sm.exists() else [f"{BASE}/"]
    urls = list(dict.fromkeys(keep + own_paths))
    body = "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
    sm.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                  f"{body}</urlset>\n", encoding="utf-8")
    print(f"🗺️  sitemap.xml → {len(urls)} URLs（re-merge {drop_pattern}）")
