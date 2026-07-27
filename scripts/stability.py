#!/usr/bin/env python3
"""成績變動追蹤：把「我們對自己數字複查了幾次、有沒有變」變成頁面上看得到的東西。

存在理由（Charlie 2026-07-27，20 年 F1 車迷的觀察）：賽果會因賽後判罰改變，
以前台灣車迷常常要等到下一場才知道獎杯易主。現在媒體多了，但媒體彼此不一致
（實例：R11 羅素完賽名次 ESPN 寫第 6、motorsport.com 寫第 7，我們用積分算術定案是第 7）。
所以這個站要提供的不是「新聞」，是**收據**：這個數字我們查過幾次、什麼時候查的、有沒有變。

三條設計紀律（違反任何一條，這個功能就變成假象）：

1. **零新資料源。** 全部來自 facts/reconcile-log.jsonl（我們自己跑的複查）
   ＋ data/<season>/results/round-<n>.json（算冠軍衝線時刻）＋ data/errata.json。
   不引入媒體、不生成內容。

2. **fail-honest。** 查不到就回 unknown 並在頁面上寫「未經複查」，
   **絕不因為沒有變動紀錄就顯示「穩定」**（見 [[feedback_status_ui_fail_honest]]）。

3. **講清楚偵測範圍。** 比對的是「資料源 vs 我們的快照」，不是「賽事單位有沒有開罰」。
   不改變名次或積分的罰款、警告、調查中案件都偵測不到，資料源同步官方判決也可能有延遲。

⚠️ 時數一律以**冠軍衝線**為基準。reconcile.py 原本印「賽後約 N 小時」卻是拿開賽時間算的，
   R11 差 1.7 小時（距開賽 13.60h vs 距衝線 11.93h），2026-07-27 查核桌抓到並已修。
"""
import datetime
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = ROOT / "facts" / "reconcile-log.jsonl"
ERRATA = ROOT / "data" / "errata.json"
TPE = datetime.timezone(datetime.timedelta(hours=8))


def _finish_utc(season, rnd):
    """冠軍衝線時刻＝開賽 ＋ 冠軍完賽總時間。任何一項缺就回 None，不猜。"""
    p = ROOT / "data" / str(season) / "results" / f"round-{rnd}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

    def find(o):
        if isinstance(o, dict):
            if "Results" in o and "date" in o:
                return o
            for v in o.values():
                r = find(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = find(v)
                if r:
                    return r
    race = find(d)
    if not race or not race.get("time") or not race.get("Results"):
        return None
    millis = race["Results"][0].get("Time", {}).get("millis")
    if not millis:
        return None
    start = datetime.datetime.fromisoformat(
        f"{race['date']}T{race['time'].replace('Z', '+00:00')}")
    return start + datetime.timedelta(milliseconds=int(millis))


def _checks(season, rnd):
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("season") == season and d.get("round") == rnd:
            out.append(d)
    return sorted(out, key=lambda x: x.get("checked_at", ""))


def _errata(slug):
    if not ERRATA.exists():
        return []
    try:
        items = json.loads(ERRATA.read_text(encoding="utf-8"))
    except Exception:
        return []
    return sorted([e for e in items if e.get("slug") == slug],
                  key=lambda e: e.get("at", ""))


def status(slug, season=None, rnd=None):
    """這篇文章的成績變動狀態。season/rnd 為 None＝非賽事文型，只回勘誤。"""
    errata = _errata(slug)
    checks = _checks(season, rnd) if (season and rnd) else []
    fin = _finish_utc(season, rnd) if (season and rnd) else None

    changed = None                      # None＝無法確認，不是「沒變」
    if checks:
        changed = any(not c.get("stable", False) for c in checks)

    # dateModified 取「勘誤時間」與「偵測到變動的複查時間」的較晚者；都沒有就 None
    stamps = [e["at"][:10] for e in errata if e.get("at")]
    stamps += [c["checked_at"][:10] for c in checks
               if not c.get("stable", False) and c.get("checked_at")]
    last_modified = max(stamps) if stamps else None

    rows = []
    for c in checks:
        try:
            ck = datetime.datetime.fromisoformat(c["checked_at"])
        except Exception:
            continue
        n = len(c.get("result_changes", [])) + len(c.get("standings_changes", []))
        rows.append({
            "at_tpe": ck.astimezone(TPE),
            "since_h": (ck - fin).total_seconds() / 3600 if fin else None,
            "stable": bool(c.get("stable", False)),
            "n_changes": n,
        })

    return {
        "slug": slug,
        "is_race_article": bool(season and rnd),
        "has_checks": bool(rows),
        "checks": rows,
        "changed": changed,
        "errata": errata,
        "last_modified": last_modified,
        "finish_tpe": fin.astimezone(TPE) if fin else None,
        "last_check_tpe": rows[-1]["at_tpe"] if rows else None,
    }


def headline(st):
    """標題下那一行的文字與狀態碼。狀態碼決定視覺強度——平常必須安靜。

    回 (state, text)；state ∈ {"changed","stable","unchecked","errata-only",""}
    """
    bits = []
    if st["last_check_tpe"]:
        bits.append(f"資料截至 {st['last_check_tpe']:%Y-%m-%d %H:%M}")

    if st["changed"]:
        n = sum(r["n_changes"] for r in st["checks"])
        bits.append(f"賽後複查偵測到 {n} 筆成績變動")
        state = "changed"
    elif st["has_checks"]:
        bits.append(f"賽後已複查 {len(st['checks'])} 次，無變動")
        state = "stable"
    elif st["is_race_article"]:
        bits.append("本頁成績尚未複查")
        state = "unchecked"
    else:
        state = ""

    if st["errata"]:
        bits.append(f"本頁有 {len(st['errata'])} 則勘誤")
        if not state:
            state = "errata-only"

    return state, " ・ ".join(bits)


# ---------- HTML ----------

def status_line_html(st):
    """標題下的一行。沒東西可講就回空字串——不要為了版面一致而擠出一行廢話。"""
    state, text = headline(st)
    if not text:
        return ""
    cls = {"changed": "is-changed", "stable": "is-stable",
           "unchecked": "is-unchecked", "errata-only": "is-errata"}.get(state, "")
    anchor = ' <a href="#rs-h">詳情 ↓</a>' if (st["has_checks"] or st["errata"]) else ""
    return f'<div class="art-status {cls}"><span>{text}{anchor}</span></div>'


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def block_html(st):
    """文末完整區塊。非賽事文型且無勘誤就整個不出現。"""
    if not st["is_race_article"] and not st["errata"]:
        return ""

    if st["has_checks"]:
        items = []
        for r in st["checks"]:
            since = f"＋{r['since_h']:.1f} 小時" if r["since_h"] is not None else "時距無法計算"
            state = ('<span class="rs-ok">— 無變動</span>' if r["stable"]
                     else f'<span class="rs-chg">偵測到 {r["n_changes"]} 筆變動</span>')
            items.append(f'<li><span class="rs-when">{since}</span>'
                         f'<span class="rs-at">{r["at_tpe"]:%Y-%m-%d %H:%M}</span>{state}</li>')
        checks_html = f'<ul class="rs-list">{"".join(items)}</ul>'
    elif st["is_race_article"]:
        checks_html = ('<p class="rs-none">尚無複查紀錄——本頁成績自發布後<strong>未經複查</strong>，'
                       '不代表沒有變動。</p>')
    else:
        checks_html = ""

    err_html = ""
    if st["errata"]:
        lis = "".join(f'<li><span class="rs-at">{_esc(e.get("at",""))}</span>'
                      f'{_esc(e.get("what",""))}</li>' for e in st["errata"])
        err_html = f'<div class="rs-sub"><h3>本頁勘誤</h3><ul class="rs-list rs-err">{lis}</ul></div>'

    meta_rows = ['<div><dt>資料來源</dt><dd>jolpica-f1（Ergast 相容）</dd></div>']
    if st["finish_tpe"]:
        meta_rows.append(f'<div><dt>冠軍衝線</dt><dd>{st["finish_tpe"]:%Y-%m-%d %H:%M}</dd></div>')
    meta_rows.append('<div><dt>最後複查</dt><dd>'
                     + (f'{st["last_check_tpe"]:%Y-%m-%d %H:%M}（台北時間）'
                        if st["last_check_tpe"] else "無法確認")
                     + '</dd></div>')

    checks_sec = f'<div class="rs-sub"><h3>複查紀錄</h3>{checks_html}</div>' if checks_html else ""
    caveat = ('<p class="rs-caveat"><strong>這個追蹤偵測得到什麼、偵測不到什麼</strong>：'
              '它比對的是「資料源現在的數字」與「本頁採用的快照」是否一致，'
              '<strong>不是「賽事單位有沒有開罰」</strong>。不改變名次或積分的罰款、警告、'
              '調查中案件，這裡看不到；資料源同步官方判決本身也可能有延遲，其幅度我們尚未量測。'
              '因此「無變動」的正確讀法是「截至該時刻，來源與本頁一致」，不是「沒有判罰」。</p>'
              ) if st["is_race_article"] else ""

    return f"""<section class="rs-box" aria-labelledby="rs-h">
  <h2 id="rs-h">成績變動追蹤</h2>
  <p class="rs-intro">賽果會因賽後判罰而改變。這一區公開我們對本站數字的每一次複查，
  包含查了幾次、什麼時候查的、有沒有變。</p>
  <dl class="rs-meta">{"".join(meta_rows)}</dl>
  {checks_sec}
  {err_html}
  {caveat}
</section>"""
