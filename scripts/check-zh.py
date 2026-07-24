#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-zh.py — 百科線 M6：譯名一致性 gate（三條硬規則 exit 1 即擋，接進測試）。

三條硬規則（任一違例且不在允許清單 → exit 1）：
  ① 同一原文（namespace + id）不得有兩個 approved 譯名（跨四張表 + phase0 seed）。
     車手比較採「姓氏正規化」（取 ・/· 最後一段），故全名 seed 與姓氏表只要姓氏一致即不算衝突；
     用字分歧（漢 vs 韓）才算。
  ② 同一 approved 譯名不得對應兩個不同「實體」（M. / R. 舒馬克必須可區分）。
     車隊的「顯示名 + id」是同一實體的別名（team-zh 兩種鍵都指同隊），正規化後不算違例。
  ③ 已 approved 條目 append-only：對照 git HEAD 的四張表，approved 條目的 zh 值不得變更、
     不得刪除（新增 OK）。HEAD 若為舊 flat 格式，相容視為 approved。

允許清單（config/zh-legacy-conflicts.json）：格式升級前既存的「歷史遺留衝突」（如 hamilton
的漢/韓兩譯，兩者皆 approved-live 不可逕改）→ 規則①降級為 warning 並列出。新衝突不得靠加清單繞過。

附帶掃描（report-only，不 exit 1，供 Charlie 知悉）：
  - approved 值含簡體字（常見簡繁差異字抽查）。
  - approved 值含港式用詞 watchlist（如「冼拿」＝ Senna 港譯，phase0 已核准不動）。

用法：
  python3 scripts/check-zh.py            # 實跑；有 error → exit 1
  python3 scripts/check-zh.py --quiet    # 只印 error/warning 摘要
"""
import argparse
import collections
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TABLES = {
    "driver": "driver-zh.json",
    "constructor": "team-zh.json",
    "race": "race-zh.json",
    "circuit": "circuit-zh.json",
}
ALLOWLIST = ROOT / "config" / "zh-legacy-conflicts.json"

# phase0 已核准 seed（4 車手全名 + 4 車隊）——與 gen-racing-entities-phase0.py ZH 同源，
# 皆 approved-live。這裡硬帶一份鏡射（避免 import phase0 的產頁副作用）；若兩處分歧，
# 規則①本身會抓到（phase0 seed 也是一個 approved 來源）。
PHASE0_ZH = {
    "driver": {
        "michael_schumacher": "麥可・舒馬克",
        "hamilton": "路易斯・漢米爾頓",
        "senna": "艾爾頓・冼拿",
        "max_verstappen": "麥克斯・維斯塔潘",
    },
    "constructor": {
        "ferrari": "法拉利",
        "mclaren": "麥拉倫",
        "mercedes": "賓士",
        "red_bull": "紅牛",
    },
}

# 常見「簡體字」抽查表：刻意只收在繁體正字中『不會出現』的簡化字（避免 后/里/系/发 等兩用或
# 敏感字誤報）。命中只列報告、不擋。譯名多為音譯，命中率低是預期。
SIMPLIFIED_CHARS = set(
    "车马门东过这时样国话说见对觉学会员书写"   # 車馬門東過這時樣國話說見對覺學會員書寫
    "买卖专业务实现应该队级红纪约纳线组织终"   # 買賣專業務實現應該隊級紅紀約納線組織終
    "汉铁银钟锋镇钱针赛资费贵产两个称荣龙凤"   # 漢鐵銀鐘鋒鎮錢針賽資費貴產兩個稱榮龍鳳
)

# 港式用詞 watchlist（人工確認清單；命中只列報告不擋。冼拿＝Senna 港譯，phase0 已核准不動）。
HK_TERM_WATCHLIST = {
    "冼拿": "Senna 的港式譯名（phase0 已核准不動；台灣多作『冼拿/塞納』，列此供 Charlie 知悉）",
    "舒麻加": "Schumacher 的港式譯名",
    "麥拿倫": "McLaren 的港式譯名（台灣作『麥拉倫』）",
}


# ---------- 載入 ----------

def _approved_from_table(raw: dict):
    """一張表 raw dict → {id: zh}（只收 approved；相容舊 flat 字串）。"""
    out = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        if isinstance(v, str):
            out[k] = v
        elif isinstance(v, dict) and v.get("status") == "approved" and v.get("zh"):
            out[k] = v["zh"]
    return out


def load_tables():
    """回 {namespace: {id: zh}}（四張表的 approved 條目）。"""
    tabs = {}
    for ns, fn in TABLES.items():
        p = SCRIPTS / fn
        raw = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        tabs[ns] = _approved_from_table(raw)
    return tabs


def load_head_tables():
    """git HEAD 的四張表 → {namespace: {id: zh}}（規則③的基準；相容舊 flat 格式）。
    非 git 環境或檔案不存在於 HEAD → 該表回空（視為全新，無 append-only 約束）。"""
    tabs = {}
    for ns, fn in TABLES.items():
        try:
            blob = subprocess.run(
                ["git", "show", f"HEAD:scripts/{fn}"],
                cwd=str(ROOT), capture_output=True, text=True, check=True).stdout
            raw = json.loads(blob)
            tabs[ns] = _approved_from_table(raw)
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            tabs[ns] = {}
    return tabs


def load_allowlist():
    if not ALLOWLIST.exists():
        return {}
    doc = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    return {(c["namespace"], c["id"]): c for c in doc.get("conflicts", [])}


def _is_resolved(allowlist, ns, k):
    """已裁決收斂條目（allowlist 內帶 resolved 欄）——衝突已由 Charlie 定案並在同一 migration
    改齊雙方，清單條目僅留審計軌跡 → gate 對其既不 error 也不 warning。"""
    c = allowlist.get((ns, k))
    return bool(c and c.get("resolved"))


# ---------- 正規化 ----------

_MIDDOTS = "・·‧•"


def family_norm(zh: str) -> str:
    """車手姓氏正規化：取 ・/· 分隔後的最後一段（全名 → 姓氏）；無分隔回原字串。"""
    for d in _MIDDOTS:
        if d in zh:
            return zh.split(d)[-1]
    return zh


def team_entity_key(key: str) -> str:
    """車隊別名正規化：顯示名與 id 收斂成同一實體鍵（strip ' F1 Team'、去空白底線、小寫）。"""
    k = key.replace(" F1 Team", "")
    return k.lower().replace(" ", "").replace("_", "")


def compare_key(ns: str, zh: str) -> str:
    """規則①比較用鍵：車手取姓氏正規化（全名 seed 與姓氏表指同一人時不誤判衝突），其餘用 zh 原值。
    ⚠️ 規則②不可用此鍵——同姓不同人（Graham/Damon/Phil Hill 皆姓氏『希爾』）會被姓氏正規化
    誤判成碰撞。規則②改用完整 zh 值（見 rule2_collisions），符合 docstring『M./R. 舒馬克必須可
    區分』的原意：全名不同即為不同實體，僅當兩實體的完整譯名逐字相同才算碰撞。"""
    return family_norm(zh) if ns == "driver" else zh


# ---------- 三規則 ----------

def collect_sources(tabs, phase0=PHASE0_ZH):
    """回 [(namespace, id, zh, source_label)]（四張表 + phase0 seed 的所有 approved）。"""
    src = []
    for ns, d in tabs.items():
        for k, zh in d.items():
            src.append((ns, k, zh, f"{TABLES[ns]}"))
    for ns, d in phase0.items():
        for k, zh in d.items():
            src.append((ns, k, zh, "phase0-seed"))
    return src


def rule1_conflicts(sources, allowlist):
    """規則①：同一 (ns,id) 有 ≥2 個不同比較鍵 → 衝突。回 (errors, warnings)。"""
    by_id = collections.defaultdict(list)
    for ns, k, zh, label in sources:
        by_id[(ns, k)].append((zh, label))
    errors, warnings = [], []
    for (ns, k), vals in sorted(by_id.items()):
        keys = {compare_key(ns, zh) for zh, _ in vals}
        if len(keys) > 1:
            if _is_resolved(allowlist, ns, k):
                continue  # 已裁決收斂：不 error 也不 warning（清單條目僅留審計軌跡）
            detail = "；".join(f"{zh}（{label}）" for zh, label in vals)
            msg = f"[規則①] 同一原文 {ns}:{k} 有多個 approved 譯名 → {detail}"
            if (ns, k) in allowlist:
                warnings.append(f"{msg} 〔歷史遺留·已在允許清單〕")
            else:
                errors.append(msg)
    return errors, warnings


def rule2_collisions(sources, allowlist):
    """規則②：同 namespace 內，同一比較鍵(譯名) 對應 ≥2 個不同實體 → 碰撞。"""
    by_name = collections.defaultdict(dict)  # (ns, zh) -> {entity_key: (id, zh, label)}
    for ns, k, zh, label in sources:
        # 規則②用完整 zh 值當鍵（不做姓氏正規化）：同姓不同人（多位『希爾』/『羅斯堡』）全名相異
        # → 不同鍵 → 不算碰撞；僅當兩個不同實體的完整譯名逐字相同才觸發（真正不可區分）。
        ck = zh
        ent = team_entity_key(k) if ns == "constructor" else k
        by_name[(ns, ck)].setdefault(ent, (k, zh, label))
    errors, warnings = [], []
    for (ns, ck), ents in sorted(by_name.items()):
        if len(ents) > 1:
            ids = [v[0] for v in ents.values()]
            if any(_is_resolved(allowlist, ns, i) for i in ids):
                continue  # 已裁決收斂：不 error 也不 warning
            detail = "、".join(f"{k}={zh}" for (k, zh, _label) in ents.values())
            msg = f"[規則②] 譯名『{ck}』（{ns}）對應多個實體 → {detail}"
            # 允許清單以 (ns,id) 具名；規則②碰撞若涉及的任一 id 在清單 → 降 warning
            if any((ns, i) in allowlist for i in ids):
                warnings.append(f"{msg} 〔歷史遺留·已在允許清單〕")
            else:
                errors.append(msg)
    return errors, warnings


def rule3_append_only(head_tabs, cur_tabs):
    """規則③：HEAD 的 approved 條目在現行版本必須存在且 zh 不變（新增 OK）。"""
    errors = []
    for ns in TABLES:
        head = head_tabs.get(ns, {})
        cur = cur_tabs.get(ns, {})
        for k, zh in sorted(head.items()):
            if k not in cur:
                errors.append(f"[規則③] {ns}:{k} 在 HEAD 為 approved（{zh}）但現行版本已刪除 — 違反 append-only")
            elif cur[k] != zh:
                errors.append(f"[規則③] {ns}:{k} 的 approved 譯名被變更：HEAD『{zh}』→ 現行『{cur[k]}』 — 違反 append-only")
    return errors


def scan_simplified(tabs):
    hits = []
    for ns, d in tabs.items():
        for k, zh in sorted(d.items()):
            bad = [c for c in zh if c in SIMPLIFIED_CHARS]
            if bad:
                hits.append(f"{ns}:{k}=『{zh}』含疑似簡體字 {bad}")
    return hits


def scan_hk_terms(tabs, phase0=PHASE0_ZH):
    hits = []
    allsrc = collect_sources(tabs, phase0)
    for ns, k, zh, label in allsrc:
        for term, note in HK_TERM_WATCHLIST.items():
            if term in zh:
                hits.append(f"{ns}:{k}=『{zh}』（{label}）命中港式 watchlist『{term}』：{note}")
    return hits


# ---------- 執行 ----------

def run_checks(tabs=None, head_tabs=None, allowlist=None, phase0=PHASE0_ZH):
    """回 dict：errors / warnings / scans。呼叫端據 errors 是否為空決定 exit code。"""
    tabs = tabs if tabs is not None else load_tables()
    head_tabs = head_tabs if head_tabs is not None else load_head_tables()
    allowlist = allowlist if allowlist is not None else load_allowlist()
    sources = collect_sources(tabs, phase0)

    e1, w1 = rule1_conflicts(sources, allowlist)
    e2, w2 = rule2_collisions(sources, allowlist)
    e3 = rule3_append_only(head_tabs, tabs)

    return {
        "errors": e1 + e2 + e3,
        "warnings": w1 + w2,
        "scans": {
            "simplified": scan_simplified(tabs),
            "hk_terms": scan_hk_terms(tabs, phase0),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    res = run_checks()

    print("🔎 譯名一致性 gate（check-zh）")
    if res["warnings"]:
        print(f"\n⚠️  warnings（{len(res['warnings'])}，不擋）：")
        for w in res["warnings"]:
            print(f"   - {w}")
    scans = res["scans"]
    if scans["simplified"]:
        print(f"\n🈶 疑似簡體字（report-only，{len(scans['simplified'])}）：")
        for s in scans["simplified"]:
            print(f"   - {s}")
    if scans["hk_terms"]:
        print(f"\n🇭🇰 港式用詞 watchlist（report-only，{len(scans['hk_terms'])}）：")
        for s in scans["hk_terms"]:
            print(f"   - {s}")
    if res["errors"]:
        print(f"\n❌ errors（{len(res['errors'])}，擋線）：")
        for e in res["errors"]:
            print(f"   - {e}")
        print(f"\n⛔ 一致性 gate 失敗（{len(res['errors'])} 個 error）")
        sys.exit(1)
    print(f"\n✅ 一致性 gate 通過（0 error，{len(res['warnings'])} warning，"
          f"{len(scans['simplified'])} 簡體命中，{len(scans['hk_terms'])} 港式命中）")


if __name__ == "__main__":
    main()
