#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""migrate-facts-anchors.py — 把既有 16 篇 facts pack 遷移到 check-season-intros.py v2 的 schema。

v2 把「正文數字只做值集合成員檢查」改成**位置綁定**：claim 要宣告 `anchors`（正文逐字片段），
正文每個數字／順位詞都必須落在某個 anchor 區間內。順位詞（第 N／倒數第 N／並列第 N）另外只接受
順位型 kind，因此有些篇要補 driver_position／race_finish_position／clinch_from_end／
rank_before_final／career_titles／countback_order／earliest_race 這些新 claim。

本腳本是**冪等**的：anchors 依 (kind, 實體) 對位覆寫，新 claim 依 (kind, 實體, value) 去重。
重跑不會產生重複條目，也就等於「16 篇 facts pack 的重生腳本」。

  python3 scripts/migrate-facts-anchors.py --dry-run   # 只印 diff 摘要
  python3 scripts/migrate-facts-anchors.py             # 落盤
  python3 scripts/check-season-intros.py               # 遷移後跑對帳

⚠️ 這裡的 anchor 與新 claim 是**人工對位**的產物（實體歸屬機器猜不準），不是自動推導；
   新增的每一條 claim 都仍要通過 v2 的 sqlite 重查，寫錯實體會當場翻紅，不是放行。
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "seasons"

# key＝(kind, entity)；entity 取 driver／constructor，沒有就 None。
PLAN = {
    1950: {
        "anchors": {
            ("season_exists", None): ["1950 年"],
            ("season_rounds", None): ["全季 7 站"],
            ("constructor_wins", "alfa"): ["包辦其中 6 場"],
            ("champion_points", "farina"): ["以 30 分"],
            ("runner_up_points", "fangio"): ["的 27 分"],
        },
        "new": [
            {"kind": "earliest_race", "text": "世界錦標賽的第一場比賽（最早賽季的第 1 站）",
             "value": 1, "verified": True, "anchors": ["第一場比賽"],
             "source": "sqlite: MIN(seasons.year)=1950 且 MIN(races.round WHERE season=1950)=1"},
        ],
    },
    1958: {
        "anchors": {
            ("season_exists", None): ["1958 年"],
            ("champion_wins", "hawthorn"): ["贏下 1 場正賽"],
            ("champion_points", "hawthorn"): ["以 42 分"],
            ("runner_up_points", "moss"): ["的 41 分"],
        },
        "new": [
            {"kind": "driver_position", "driver": "moss", "text": "Moss 年度順位第二", "value": 2,
             "verified": True, "anchors": ["仍屈居第二"],
             "source": "sqlite: SELECT position FROM driver_standings WHERE season=1958 AND driver_id='moss'"},
        ],
    },
    1961: {
        "anchors": {
            ("season_exists", None): ["1961 年"],
            ("season_rounds", None): ["全季 8 站"],
            ("champion_wins", "phil_hill"): ["拿下 2 場分站冠軍"],
            ("champion_points", "phil_hill"): ["以 34 分"],
            ("runner_up_points", "trips"): ["的 33 分"],
            ("constructor_wins", "ferrari"): ["以 5 場分站冠軍"],
        },
        "new": [
            {"kind": "clinch_from_end", "driver": "phil_hill",
             "text": "車手冠軍在倒數第二站（R7 義大利站）分出勝負", "value": 2, "verified": True,
             "anchors": ["在倒數第二站"],
             "source": "逐站重算：捨分規則＋只計實際仍有出賽的對手，clinch=R7、全季 8 站"},
        ],
    },
    1964: {
        "anchors": {
            ("season_exists", None): ["1964 年"],
            ("champion_points", "surtees"): ["以 40 分"],
            ("runner_up_points", "hill"): ["的 39 分"],
        },
        "new": [],
    },
    1976: {
        "anchors": {("season_exists", None): ["1976 年"]},
        "comment": (
            "1976 賽季導言 facts pack。⚠️歷史註記：jolpica L0 的 driver_standings 1976 冠亞軍積分為 "
            "hunt 66／lauda 64，與逐站 results 重算及英文維基（revid 1366923268）的 69／68 不符；"
            "2026-08-13 Charlie 裁決已把這兩筆寫進 data/f1/standings-overrides.json，build-f1-db.py "
            "會在建 db 時套用，故 db.sqlite 讀到的是 L1 的 69／68。check-season-intros.py v2 另外用 "
            "results＋scoring-rules.json 重算與外部快照兩條腿交叉驗這兩個值，不再只回讀 standings。"
            "本篇正文仍不引用冠軍積分數字（維持核准當下的文字，改稿要重走核准），"
            "champion_points／runner_up_points 兩條 claim 保持移除狀態。"
            "1976 R16 日本站分站冠軍實為 mario_andretti，hunt 該站 position_text='3'；"
            "正文『跑到第三名』由 race_finish_position claim（driver=hunt, round=16, value=3）綁定驗證。"),
        "new": [
            {"kind": "race_finish_position", "driver": "hunt", "round": 16,
             "text": "亨特在日本站（R16）以第三名完賽", "value": 3, "verified": True,
             "anchors": ["跑到第三名"],
             "source": "sqlite: SELECT position_text FROM results WHERE season=1976 AND round=16 AND driver_id='hunt'"},
        ],
    },
    1984: {
        "anchors": {
            ("season_exists", None): ["1984 年"],
            ("season_rounds", None): ["16 站"],
            ("constructor_wins", "mclaren"): ["拿下 12 場勝利"],
            ("champion_points", "lauda"): ["勞達以 72 分"],
            ("runner_up_points", "prost"): ["對 71.5 分"],
        },
        "new": [],
    },
    1986: {
        "anchors": {
            ("season_exists", None): ["1986 年"],
            ("champion_points", "prost"): ["以 72 分"],
            ("runner_up_points", "mansell"): ["對 70 分"],
        },
        "new": [],
    },
    1988: {
        "anchors": {
            ("season_exists", None): ["1988 年"],
            ("season_rounds", None): ["16 站"],
            ("constructor_wins", "mclaren"): ["拿下 15 場勝利"],
            ("champion_points", "senna"): ["以 90 分"],
            ("runner_up_points", "prost"): ["的 87 分"],
        },
        "new": [],
    },
    1994: {
        "anchors": {
            ("season_exists", None): ["1994 年"],
            ("champion_wins", "michael_schumacher"): ["拿下 8 場分站冠軍"],
            ("champion_points", "michael_schumacher"): ["以 92 分"],
            ("runner_up_points", "damon_hill"): ["對 91 分"],
        },
        "new": [],
    },
    2002: {
        "anchors": {
            ("season_exists", None): ["2002 年"],
            ("season_rounds", None): ["在 17 站裡"],
            ("champion_wins", "michael_schumacher"): ["贏下 11 場"],
            ("clinch_round", "michael_schumacher"): ["第 11 站奪冠"],
            ("clinch_remaining", "michael_schumacher"): ["還剩 6 站"],
            ("champion_points", "michael_schumacher"): ["以 144 分"],
            ("runner_up_points", "barrichello"): ["（77 分）"],
        },
        "sources": {
            ("clinch_round", "michael_schumacher"):
                "clinch 計算（v2）：逐站積分套當季捨分規則，對手上限只計其實際仍有出賽的站次；"
                "首個「冠軍保底分 ＞ 所有對手理論上限」的站次（見 check-season-intros.py SeasonOracle.clinch）",
            ("clinch_remaining", "michael_schumacher"):
                "clinch 計算（v2）：同上，remaining＝總站數 − clinch 站次",
        },
        "new": [
            {"kind": "driver_position", "driver": "barrichello", "text": "巴瑞契羅年度順位第二",
             "value": 2, "verified": True, "anchors": ["第二名的隊友"],
             "source": "sqlite: SELECT position FROM driver_standings WHERE season=2002 AND driver_id='barrichello'"},
        ],
    },
    2007: {
        "anchors": {
            ("season_exists", None): ["2007 年"],
            ("champion_wins", "raikkonen"): ["第 6 場分站冠軍"],
            ("champion_points", "raikkonen"): ["以 110 分"],
            ("runner_up_points", "hamilton"): ["同以 109 分"],
        },
        "new": [
            {"kind": "driver_position", "driver": "hamilton", "text": "漢米爾頓年度順位第二",
             "value": 2, "verified": True, "anchors": ["漢米爾頓列第二"],
             "source": "sqlite: SELECT position FROM driver_standings WHERE season=2007 AND driver_id='hamilton'"},
            {"kind": "driver_position", "driver": "alonso", "text": "阿隆索年度順位第三",
             "value": 3, "verified": True, "anchors": ["阿隆索第三"],
             "source": "sqlite: SELECT position FROM driver_standings WHERE season=2007 AND driver_id='alonso'"},
            {"kind": "countback_order", "drivers": ["hamilton", "alonso"],
             "text": "兩人同為 109 分，順位由 countback（第二名完賽 5 次對 4 次）分出：P2／P3",
             "value": 2, "verified": True,
             "source": "sqlite results 完賽名次分布重算 countback；driver_standings position=2／3"},
        ],
    },
    2008: {
        "anchors": {
            ("season_exists", None): ["2008 年"],
            ("champion_points", "hamilton"): ["以 98 分"],
            ("runner_up_points", "massa"): ["對 97 分"],
        },
        "new": [
            {"kind": "race_finish_position", "driver": "hamilton", "round": 18,
             "text": "漢米爾頓在巴西站（R18）以第五名完賽", "value": 5, "verified": True,
             "anchors": ["以第五名"],
             "source": "sqlite: SELECT position_text FROM results WHERE season=2008 AND round=18 AND driver_id='hamilton'"},
        ],
    },
    2010: {
        "anchors": {
            ("season_exists", None): ["2010 年"],
            ("champion_points", "vettel"): ["以 256 分"],
            ("runner_up_points", "alonso"): ["的 252 分"],
        },
        "new": [
            {"kind": "rank_before_final", "driver": "vettel", "text": "末站前累計排名第三",
             "value": 3, "verified": True, "anchors": ["末站前排名第三"],
             "source": "逐站重算：截至 R18 的累計積分＋countback 排名"},
        ],
    },
    2012: {
        "anchors": {
            ("season_exists", None): ["2012 年"],
            ("season_rounds", None): ["戰滿 20 站"],
            ("champion_points", "vettel"): ["以 281 分"],
            ("runner_up_points", "alonso"): ["的 278 分"],
        },
        "new": [
            {"kind": "career_titles", "driver": "vettel", "text": "維特爾生涯第三座世界冠軍",
             "value": 3, "verified": True, "anchors": ["個人第三座世界冠軍"],
             "source": "sqlite: COUNT(driver_standings WHERE driver_id='vettel' AND position=1 AND season<=2012)"},
        ],
    },
    2016: {
        "anchors": {
            ("season_exists", None): ["2016 年"],
            ("champion_points", "rosberg"): ["以 385 分"],
            ("runner_up_points", "hamilton"): ["對 380 分"],
        },
        "new": [],
    },
    2021: {
        "anchors": {
            ("season_exists", None): ["2021 年"],
            ("season_rounds", None): ["第 22 站"],
            ("champion_points", "max_verstappen"): ["以 395.5 分"],
            ("runner_up_points", "hamilton"): ["對 387.5 分"],
        },
        "new": [],
    },
}


def _entity(claim):
    return claim.get("driver") or claim.get("constructor")


def _same_claim(a, b):
    return (a.get("kind") == b.get("kind") and _entity(a) == _entity(b)
            and (a.get("drivers") or []) == (b.get("drivers") or [])
            and a.get("value") == b.get("value"))


def migrate(year, plan, dry_run=False):
    path = CONTENT / f"{year}.facts.json"
    if not path.exists():
        return [f"[{year}] 缺 facts pack，略過"]
    pack = json.loads(path.read_text(encoding="utf-8"))
    claims = pack.setdefault("claims", [])
    changes = []

    if plan.get("comment") and pack.get("_comment") != plan["comment"]:
        pack["_comment"] = plan["comment"]
        changes.append(f"[{year}] _comment 更新（v1 的過期敘述）")

    for (kind, entity), source in (plan.get("sources") or {}).items():
        target = next((c for c in claims if c.get("kind") == kind and _entity(c) == entity), None)
        if target is not None and target.get("source") != source:
            target["source"] = source
            changes.append(f"[{year}] source {kind}/{entity} 更新")

    for (kind, entity), anchors in plan["anchors"].items():
        target = next((c for c in claims if c.get("kind") == kind and _entity(c) == entity), None)
        if target is None:
            changes.append(f"[{year}] ⚠ 找不到 claim kind={kind} entity={entity}，anchor 未套用")
            continue
        if target.get("anchors") != anchors:
            target["anchors"] = anchors
            changes.append(f"[{year}] anchors {kind}/{entity} ← {anchors}")

    for new in plan["new"]:
        if any(_same_claim(c, new) for c in claims):
            existing = next(c for c in claims if _same_claim(c, new))
            if existing.get("anchors") != new.get("anchors"):
                existing["anchors"] = new.get("anchors")
                changes.append(f"[{year}] anchors {new['kind']} ← {new.get('anchors')}")
            continue
        claims.append(dict(new))
        changes.append(f"[{year}] ＋claim {new['kind']} value={new['value']}")

    if changes and not dry_run:
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes


def main(argv):
    ap = argparse.ArgumentParser(description="facts pack v2 anchor 遷移（冪等）")
    ap.add_argument("years", type=int, nargs="*", help="只遷移指定年份（預設全部）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    years = args.years or sorted(PLAN)
    total = 0
    for y in years:
        if y not in PLAN:
            print(f"[{y}] 無遷移計畫，略過")
            continue
        for line in migrate(y, PLAN[y], args.dry_run):
            print(line)
            total += 1
    print(f"\n{'[dry-run] ' if args.dry_run else ''}共 {total} 項變更。"
          f"接著跑：python3 scripts/check-season-intros.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
