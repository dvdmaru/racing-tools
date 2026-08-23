#!/usr/bin/env python3
"""/circuits/ 全 78 條賽道索引與賽道頁的唯一 owner。

四大實體（賽季／車手／車隊／賽道）的最後一塊。發布欄位只有「承辦分站」與由承辦明細
聚合出來的最多勝車手／車隊；桿位與最快圈**不發**（站規第一階段：寫不出定義與資料邊界
的數字就上不了頁）。

三件事跟車隊頁刻意同構：
  ① 頁殼走 rc.page_shell + p0.ENTITY_CSS，中英對照走 p0.pair（譯名只採 circuit-zh.json
     的 approved 值，無譯名就只顯示原文，絕不自翻）。
  ② 所有數字都是明細 list 的 len()，沒有任何 int 欄位可以被單獨改壞。
  ③ 站內連結只連**已經存在的頁**：賽季頁 1950–當季全有；車手／車隊頁只有各自 canonical
     roster 裡那幾位有。不在名單裡的冠軍車手／車隊一律純文字，寧漏不錯連。

⚠️ 與車隊頁不同：本頁群沒有 golden／Wikipedia 裁決那兩道外部 gate（賽道沒有對應的
crosscheck 產物）。取而代之的是本檔自己的兩道內部 gate：slug 註冊表與 db circuits 表
雙向全等、以及所有統計 value==len(detail)。任一不綠 → 零頁生成。
"""
import argparse
import html as html_lib
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rc = _load("racinglib_circuit_gen", "racinglib.py")
fs = _load("f1stats_circuit_gen", "f1stats.py")
p0 = _load("phase0_circuit_components", "gen-racing-entities-phase0.py")
gs = _load("seasons_circuit_links", "gen-racing-seasons.py")

BASE = rc.BASE
PUB = ROOT / "public-racing"
DB = ROOT / "data" / "f1" / "db.sqlite"
esc = html_lib.escape

# 有實體頁的車手／車隊唯一名單來源＝各自的 canonical crosscheck report（與 gen-racing-drivers.py
# ／gen-racing-constructors.py 同源）。這裡只讀不寫；名單變動會經由 regen 指紋讓賽道頁失效。
DRIVER_REPORT = ROOT / "data" / "f1" / "crosscheck-report.json"
CONSTRUCTOR_REPORT = ROOT / "data" / "f1" / "constructor-crosscheck-report.json"
DRIVER_PAGE_IDS = frozenset(
    json.loads(DRIVER_REPORT.read_text(encoding="utf-8"))["coverage"]["expected_driver_ids"])
CONSTRUCTOR_PAGE_IDS = frozenset(
    json.loads(CONSTRUCTOR_REPORT.read_text(encoding="utf-8"))["coverage"]["expected_constructor_ids"])

# slug 註冊表（append-only，data/f1/slugs.json 的 circuits 命名空間）＝賽道頁名單的
# canonical 來源。用註冊表而不是「當下 db 有什麼就產什麼」，是因為 URL 一旦發布就不能改；
# db 與註冊表分岔時由 gate_registry 擋下，不靜默多產／少產。
_CIRCUIT_SLUGS = rc._SLUGS.get("circuits", {})
CIRCUIT_IDS = sorted(_CIRCUIT_SLUGS)

# 排行榜取前幾名（同分者一併列出，不因為排序穩定就把並列的人切掉）
TOP_N = 5


def circuit_slug(cid):
    if cid not in _CIRCUIT_SLUGS:
        raise KeyError(f"賽道 slug 未註冊：{cid}（append-only 註冊表 data/f1/slugs.json）")
    return _CIRCUIT_SLUGS[cid]


def approved_zh(cid):
    """譯名只走 circuit-zh.json approved-only；12 條沒有核准譯名的賽道會原文保留。"""
    return rc.CIRCUIT_ZH.get(cid)


def display_name(zh, name):
    """頁面文案裡指涉這條賽道的名字：有核准譯名用譯名，沒有就用原文。

    ⚠️ 標題與描述的模板刻意**不再自己接「賽道」二字**。66 條核准譯名幾乎都自帶那個
    名詞，接了就變成「蒙札賽道賽道承辦紀錄」（第一版真的產出 50/78 頁疊字）。
    改成 endswith("賽道") 判斷也修不好：「亞伯特公園賽道（墨爾本）」名詞不在字尾、
    「上海國際賽車場」與「紅牛環（史匹爾柏格）」名詞根本不是「賽道」二字——所以正解是
    模板不帶這個名詞，而不是在生成器裡追加特例清單。
    """
    return zh or name


_LATIN_TAIL = re.compile(r"[0-9A-Za-z)\]]$")


def phrase(head, tail):
    """名稱後面直接接中文的組字：結尾是拉丁字母／數字時補盤古之白（站規：中英之間留白）。"""
    return f"{head} {tail}" if _LATIN_TAIL.search(head or "") else f"{head}{tail}"


# ---------- 資料層（全部由 db 明細推導；value 一律 len()） ----------

def _stat(zh_def, coverage, detail):
    """統計欄位唯一建構路徑：value 由 len(detail) 產生，不接受外部傳入的數字。

    ⚠️ 沒有沿用 f1stats._stat／p0.stat_card 的 formula 註冊表，是因為那份註冊表
    （FORMULAS / FORMULA_ZH）屬於車手與車隊頁；在共用模組裡塞賽道專用的公式 id
    會讓兩條線互相牽動。這裡改成把中文定義直接帶在 stat 裡，語意一樣、耦合更少。
    """
    return {"value": len(detail), "zh_def": zh_def, "coverage": coverage, "detail": detail}


def circuit_meta_db(cid, con):
    row = con.execute(
        "SELECT circuit_id, name, locality, country, url FROM circuits WHERE circuit_id=?",
        (cid,)).fetchone()
    if row is None:
        raise KeyError(f"db circuits 表查無此賽道：{cid}")
    return {"circuit_id": row["circuit_id"], "name": row["name"] or cid,
            "locality": row["locality"] or "", "country": row["country"] or "",
            "url": row["url"] or ""}


def circuit_races_db(cid, con):
    """此賽道承辦過（或賽曆已列入）的所有分站，含冠軍車手／車隊明細。

    held=False＝賽曆列入但一筆正賽結果都還沒有（進行中賽季的未來站）。這種列會出現在
    承辦清單裡並標「尚未舉行」，但**不進任何統計**——把未來的排程算成戰績是站規禁止的。
    """
    winners = {}
    for r in con.execute(
            "SELECT r.season AS season, r.round AS round, r.driver_id AS driver_id, "
            "       r.constructor_id AS constructor_id "
            "FROM results r JOIN races ra ON ra.season=r.season AND ra.round=r.round "
            "WHERE ra.circuit_id=? AND r.position_text='1' "
            "ORDER BY r.season, r.round, r.id", (cid,)):
        winners.setdefault((r["season"], r["round"]), []).append(
            {"driver_id": r["driver_id"], "constructor_id": r["constructor_id"]})
    rows = []
    for ra in con.execute(
            "SELECT ra.season AS season, ra.round AS round, ra.name AS name, "
            "       (SELECT count(*) FROM results x "
            "        WHERE x.season=ra.season AND x.round=ra.round) AS result_rows "
            "FROM races ra WHERE ra.circuit_id=? ORDER BY ra.season, ra.round", (cid,)):
        key = (ra["season"], ra["round"])
        rows.append({
            "season": ra["season"], "round": ra["round"],
            "race": ra["name"] or f"Round {ra['round']}",
            "held": ra["result_rows"] > 0,
            "winners": winners.get(key, []),
            "source": f"data/f1/raw/results/{ra['season']}-{ra['round']:02d}.json",
        })
    return rows


def circuit_summary(cid, con):
    meta = circuit_meta_db(cid, con)
    races = circuit_races_db(cid, con)
    held = [r for r in races if r["held"]]
    pending = [r for r in races if not r["held"]]
    hosted = _stat("賽曆列入且已有正賽賽果的分站數（尚未舉行的排程不計）",
                   "1950-2026", [dict(r) for r in held])
    # ⚠️ 共同駕駛的一場會有兩筆冠軍列。兩位車手各記一勝（他們真的各贏了一次），但
    # **車隊同場只能記一次**——不然一場比賽會替車隊生出兩座分站冠軍。同 id 在同一場
    # 重複出現一律去重，兩邊都做（車手側目前資料不會發生，但不靠「目前不會」當保證）。
    drv, con_ = {}, {}
    for r in held:
        for bucket, key in ((drv, "driver_id"), (con_, "constructor_id")):
            seen = set()
            for w in r["winners"]:
                eid = w[key]
                if not eid or eid in seen:
                    continue
                seen.add(eid)
                bucket.setdefault(eid, []).append(dict(r))
    seasons = sorted({r["season"] for r in held})
    return {"cid": cid, "slug": circuit_slug(cid), "meta": meta,
            "zh": approved_zh(cid), "name": meta["name"],
            "races": races, "held": held, "pending": pending, "hosted": hosted,
            "driver_wins": drv, "constructor_wins": con_,
            "first_season": seasons[0] if seasons else None,
            "last_season": seasons[-1] if seasons else None}


def leaderboard(counts, limit=TOP_N):
    """(id, detail list) 依勝場遞減、id 遞增排序；切在第 limit 名，與其同分者一併保留。"""
    rows = sorted(counts.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    if len(rows) > limit:
        cutoff = len(rows[limit - 1][1])
        rows = [row for i, row in enumerate(rows) if i < limit or len(row[1]) == cutoff]
    return rows


# ---------- 前置 gate（任一不綠 → 零產出） ----------

def gate_registry(con, expected=None):
    """slug 註冊表與 db circuits 表雙向全等；多一條／少一條都失敗。"""
    expected = list(CIRCUIT_IDS if expected is None else expected)
    actual = [r[0] for r in con.execute("SELECT circuit_id FROM circuits ORDER BY circuit_id")]
    if actual != expected or len(expected) != len(set(expected)):
        print(f"🔴 circuit 註冊表非雙向全等：多 {sorted(set(actual) - set(expected))}　"
              f"缺 {sorted(set(expected) - set(actual))}")
        return False
    slugs = [_CIRCUIT_SLUGS[cid] for cid in expected]
    if len(slugs) != len(set(slugs)):
        print("🔴 circuit slug 有重複（URL 會互相覆蓋）")
        return False
    return True


def gate_stats(con, circuit_ids=None):
    """所有統計 value 必須等於明細筆數；未舉行的分站不得混進任何統計。"""
    bad = []
    for cid in (CIRCUIT_IDS if circuit_ids is None else circuit_ids):
        s = circuit_summary(cid, con)
        if s["hosted"]["value"] != len(s["hosted"]["detail"]):
            bad.append((cid, "hosted"))
        if any(not r["held"] for r in s["hosted"]["detail"]):
            bad.append((cid, "hosted 含未舉行分站"))
        for did, detail in s["driver_wins"].items():
            if any(not r["held"] for r in detail):
                bad.append((cid, f"driver_wins/{did} 含未舉行分站"))
        for tid, detail in s["constructor_wins"].items():
            if any(not r["held"] for r in detail):
                bad.append((cid, f"constructor_wins/{tid} 含未舉行分站"))
    if bad:
        print(f"🔴 circuit 統計不變量 FAIL：{len(bad)} 處")
        for row in bad[:20]:
            print(f"    {row[0]} {row[1]}")
        return False
    return True


def run_gates(con=None, db=None):
    print("=" * 70)
    print("賽道頁前置兩 gate（任一不綠 → 零產出）")
    print("=" * 70)
    own = con is None
    con = con or fs.connect_db(db)
    try:
        if not gate_registry(con):
            print("🔴 gate ① slug 註冊表／db roster 未通過 → 中止。")
            return False
        if not gate_stats(con):
            print("🔴 gate ② 統計不變量未通過 → 中止。")
            return False
    finally:
        if own:
            con.close()
    print("✅ 兩 gate 全綠，開始產頁。")
    return True


# ---------- 站內連結（只連已存在的頁；不存在就純文字） ----------

def season_link(year, label_html):
    if gs.FIRST_YEAR <= year <= gs.LAST_YEAR:
        return f'<a href="/seasons/{year}/">{label_html}</a>'
    return label_html


def driver_link(did, label_html):
    if did in DRIVER_PAGE_IDS and did in rc._SLUGS.get("drivers", {}):
        return f'<a href="/drivers/{rc.driver_slug(did)}/">{label_html}</a>'
    return label_html


def constructor_link(cid, label_html):
    if cid in CONSTRUCTOR_PAGE_IDS and cid in rc._SLUGS.get("constructors", {}):
        return f'<a href="/constructors/{rc.constructor_slug(cid)}/">{label_html}</a>'
    return label_html


# ---------- 顯示名（中英對照；譯名 approved-only） ----------

def driver_label(did, con):
    meta = con.execute(
        "SELECT given_name, family_name FROM drivers WHERE driver_id=?", (did,)).fetchone()
    en = " ".join(x for x in ((meta["given_name"] or ""), (meta["family_name"] or "")) if x) if meta else did
    return p0.pair(rc.DRIVER_ZH.get(did) or p0.ZH.get(did), en or did)


def constructor_label(cid, con):
    meta = con.execute(
        "SELECT name FROM constructors WHERE constructor_id=?", (cid,)).fetchone()
    name = (meta["name"] if meta else "") or cid
    return p0.pair(rc.TEAM_ZH.get(cid) or rc.TEAM_ZH.get(name), name)


# ---------- 視覺元件 ----------

CIRCUIT_CSS = """
.pending{color:var(--faint)}
.tbl-wrap{overflow-x:auto}
.lead-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;margin:8px 0}
"""


def stat_card(label, stat, unit=""):
    """一張統計卡。結構與 p0.stat_card 同型，但中文定義直接讀 stat['zh_def']
    （見 _stat 的註解：不把賽道公式塞進車手／車隊那份共用註冊表）。"""
    detail = stat["detail"]
    rows = "".join(
        f'<li title="來源檔：{esc(d["source"])}"><span class="mono">{d["season"]}</span> '
        f'{esc(d["race"])}</li>' for d in detail[:80])
    more = f'<li class="more">…以下省略，共 {len(detail)} 筆</li>' if len(detail) > 80 else ""
    return f"""<div class="stat">
  <div class="stat-v mono">{stat["value"]}<span class="unit">{unit}</span></div>
  <div class="stat-l">{label}</div>
  <details class="how">
    <summary>怎麼算的</summary>
    <div class="how-body">
      <p class="formula"><b>定義</b>　{esc(stat["zh_def"])}<span class="cov">資料涵蓋 {esc(stat["coverage"])}</span></p>
      <ol class="detail-list">{rows}{more}</ol>
      <p class="prov">數字＝上列明細的筆數，不另行維護。每筆對應一份官方原始資料檔（滑鼠停留可見檔名）。</p>
    </div>
  </details>
</div>"""


def hosting_table(summary, con):
    """承辦分站清單（新到舊）。冠軍車手／車隊只在該實體有頁時才連結。"""
    rows = []
    for r in sorted(summary["races"], key=lambda x: (-x["season"], -x["round"])):
        season_cell = season_link(r["season"], str(r["season"]))
        if not r["held"]:
            drv_cell = team_cell = '<span class="pending">尚未舉行</span>'
        elif not r["winners"]:
            drv_cell = team_cell = '<span class="pending">資料源未收錄</span>'
        else:
            drv_cell = "、".join(
                driver_link(w["driver_id"], driver_label(w["driver_id"], con))
                for w in r["winners"] if w["driver_id"])
            teams, seen = [], set()
            for w in r["winners"]:
                if w["constructor_id"] and w["constructor_id"] not in seen:
                    seen.add(w["constructor_id"])
                    teams.append(constructor_link(
                        w["constructor_id"], constructor_label(w["constructor_id"], con)))
            team_cell = "、".join(teams) or '<span class="pending">資料源未收錄</span>'
        rows.append(f'<tr><td class="mono">{season_cell}</td><td>{esc(r["race"])}</td>'
                    f'<td>{drv_cell}</td><td>{team_cell}</td></tr>')
    return ('<div class="tbl-wrap"><table class="std-tbl"><thead><tr><th>賽季</th><th>大獎賽</th>'
            '<th>分站冠軍</th><th>冠軍車隊</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _leader_table(head, rows, label_of, link_of):
    if not rows:
        return '<p class="note">尚無資料。</p>'
    body = "".join(
        f'<tr><td class="mono rk">{i}</td><td>{link_of(key, label_of(key))}</td>'
        f'<td class="mono">{len(detail)}</td></tr>'
        for i, (key, detail) in enumerate(rows, 1))
    return ('<div class="tbl-wrap"><table class="std-tbl"><thead><tr><th>#</th>'
            f'<th>{head}</th><th>本賽道勝場</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


# ---------- JSON-LD ----------

def place_ld(summary, url):
    zh, name = summary["zh"], summary["name"]
    node = {"@type": "Place", "name": zh or name, "url": url}
    if zh and zh != name:
        node["alternateName"] = name
    addr = {"@type": "PostalAddress"}
    if summary["meta"]["locality"]:
        addr["addressLocality"] = summary["meta"]["locality"]
    if summary["meta"]["country"]:
        addr["addressCountry"] = summary["meta"]["country"]
    if len(addr) > 1:
        node["address"] = addr
    if summary["meta"]["url"]:
        node["sameAs"] = [summary["meta"]["url"]]
    return node


# ---------- 產頁 ----------

def write_page(path_parts, title, desc, jsonld, body):
    canonical = f"{BASE}/{'/'.join(path_parts)}/"
    html = rc.page_shell(title, desc, canonical, jsonld, body,
                         active="", extra_css=p0.ENTITY_CSS + CIRCUIT_CSS)
    out = PUB
    for part in path_parts:
        out = out / part
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    return canonical


METHOD_NOTE = (
    "<b>資料來源</b>　jolpica-f1（Ergast 相容）公開資料。1950 年代的歷史賽果由志願者社群"
    "維護、並非官方發布，缺漏與口徑差異都可能存在；本頁只呈現資料源實際收錄的內容，"
    "查不到就寫「資料源未收錄」，不補、不推估。<br>"
    "<b>承辦分站</b>　賽曆列入且已有正賽賽果的分站；賽曆已列入但尚未舉行者在清單裡標"
    "「尚未舉行」，不計入任何統計。<br>"
    "<b>分站冠軍</b>　以正賽最終名次為第 1 計。1950 年代有共同駕駛（兩位車手接力同一台車），"
    "資料源會列兩筆冠軍，本頁兩位都列，最多勝也各記一次；車隊則同場去重計一次。<br>"
    "<b>2026 賽季尚未結束</b>　表中的 2026 列是個別分站的結果，本頁不發布任何賽季冠軍類數字。<br>"
    "<b>桿位、最快圈暫不發布</b>，待定義與資料邊界另案完成。<br>"
    "<b>譯名</b>　只採 circuit-zh.json 已核准值；未核准者只顯示原文，不自行翻譯。<br>"
    "<b>站內連結</b>　只連已經存在的頁；沒有專頁的車手／車隊以純文字呈現。"
)


def gen_circuit(cid, con):
    summary = circuit_summary(cid, con)
    slug, zh, name = summary["slug"], summary["zh"], summary["name"]
    url = f"{BASE}/circuits/{slug}/"
    identity = []
    if summary["meta"]["country"]:
        identity.append(f'<span>國家 {esc(summary["meta"]["country"])}</span>')
    if summary["meta"]["locality"]:
        identity.append(f'<span>地點 {esc(summary["meta"]["locality"])}</span>')
    if summary["first_season"]:
        identity.append('<span>承辦賽季 <span class="mono">'
                        f'{summary["first_season"]}–{summary["last_season"]}</span></span>')
    hero = f"""<div class="ent-hero">
  <p class="ent-kicker">賽道檔案 · Circuit</p>
  <h1 class="ent-h1">{p0.pair(zh, name)}</h1>
  <div class="ident">{"".join(identity)}</div>
</div>"""
    cards = (stat_card("承辦分站", summary["hosted"], unit=" 站") +
             p0.unavailable_card("桿位", "後續補（定義與資料範圍見方法說明）") +
             p0.unavailable_card("最快圈", "後續補（定義與資料範圍見方法說明）"))
    pending_note = ""
    if summary["pending"]:
        years = "、".join(str(r["season"]) for r in summary["pending"])
        pending_note = (f'<p class="note">賽曆已列入但尚未舉行：'
                        f'<span class="mono">{len(summary["pending"])}</span> 站（{esc(years)}），'
                        "清單裡標「尚未舉行」，不計入統計。</p>")
    drv_rows = leaderboard(summary["driver_wins"])
    team_rows = leaderboard(summary["constructor_wins"])
    body = f"""{hero}
<div class="stat-grid">{cards}</div>
<h2 class="sec-title">歷年最多勝車手</h2>
{_leader_table("車手", drv_rows, lambda k: driver_label(k, con), driver_link)}
<h2 class="sec-title">歷年最多勝車隊</h2>
{_leader_table("車隊", team_rows, lambda k: constructor_label(k, con), constructor_link)}
<h2 class="sec-title">承辦分站</h2>
{pending_note}
{hosting_table(summary, con)}
<h2 class="sec-title">方法說明</h2>
<p class="note">{METHOD_NOTE}</p>"""
    ld = rc.graph_ld([rc.org_node(), rc.website_node(),
                      rc.breadcrumb_node([("首頁", BASE + "/"), ("賽道", BASE + "/circuits/"),
                                          (zh or name, url)]), place_ld(summary, url)])
    disp = display_name(zh, name)
    write_page(["circuits", slug], phrase(disp, "承辦紀錄"),
               phrase(disp, "歷年承辦的每一場大獎賽、分站冠軍與冠軍車隊，以及本賽道最多勝的車手與車隊。"),
               ld, body)
    return summary


def _index_rows(con):
    rows = [circuit_summary(cid, con) for cid in CIRCUIT_IDS]
    rows.sort(key=lambda row: (-row["hosted"]["value"], row["cid"]))
    return rows


def render_index(con):
    rows = _index_rows(con)
    table_rows = []
    for rank, row in enumerate(rows, 1):
        span = (f'{row["first_season"]}–{row["last_season"]}'
                if row["first_season"] else "—")
        table_rows.append(
            f'<tr><td class="mono rk">{rank}</td>'
            f'<td><a href="/circuits/{row["slug"]}/">{p0.pair(row["zh"], row["name"])}</a></td>'
            f'<td>{esc(row["meta"]["country"])}</td><td>{esc(row["meta"]["locality"])}</td>'
            f'<td class="mono">{row["hosted"]["value"]}</td><td class="mono">{span}</td></tr>')
    table = ('<div class="tbl-wrap"><table class="std-tbl"><thead><tr><th>#</th><th>賽道</th>'
             '<th>國家</th><th>地點</th><th>承辦分站</th><th>承辦賽季</th></tr></thead>'
             f'<tbody>{"".join(table_rows)}</tbody></table></div>')
    no_zh = [row for row in rows if not row["zh"]]
    body = f"""<div class="ent-hero"><p class="ent-kicker">賽道名錄 · Circuits</p>
<h1 class="ent-h1">歷年賽道<span class="zh-en">　Circuits</span></h1>
<p class="ident"><span>資料源收錄過的賽道共 <span class="mono">{len(rows)}</span> 條，依承辦分站數排序。</span></p></div>
{table}
<p class="note">承辦分站＝賽曆列入且已有正賽賽果的分站，尚未舉行的排程不計入。譯名只採 circuit-zh.json 已核准值，其中 <span class="mono">{len(no_zh)}</span> 條尚無核准譯名，只顯示原文，不自行翻譯。點賽道名可查看該賽道歷年承辦的每一場大獎賽與冠軍。</p>"""
    items = [{"@type": "ListItem", "position": i,
              "url": f"{BASE}/circuits/{row['slug']}/", "name": row["zh"] or row["name"]}
             for i, row in enumerate(rows, 1)]
    ld = rc.graph_ld([rc.org_node(), rc.website_node(),
                      rc.breadcrumb_node([("首頁", BASE + "/"), ("賽道", BASE + "/circuits/")]),
                      {"@type": "ItemList", "name": "歷年賽道", "numberOfItems": len(items),
                       "itemListElement": items}])
    return write_page(["circuits"], "歷年賽道名錄",
                      "資料源收錄過的每一條賽道：承辦分站數、承辦賽季、國家與地點。",
                      ld, body)


def main():
    ap = argparse.ArgumentParser(description="產出 /circuits/ 全賽道索引與賽道頁。")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--no-sitemap", action="store_true")
    ap.add_argument("--skip-gates", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    con = fs.connect_db()
    try:
        if not args.skip_gates and not run_gates(con):
            return 1
        urls = [render_index(con)]
        for cid in CIRCUIT_IDS:
            row = gen_circuit(cid, con)
            urls.append(f"{BASE}/circuits/{row['slug']}/")
    finally:
        con.close()
    if args.publish and not args.no_sitemap:
        rc.write_sitemap_part("circuits", urls)
    print(f"共 {len(urls)} 頁。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
