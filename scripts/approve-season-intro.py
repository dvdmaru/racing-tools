#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""approve-season-intro.py — Charlie 核准某年賽季導言的 migration（把 sha256 寫進 approved.json）。

default-deny：導言檔（content/seasons/<year>.md）存在不代表會渲染；必須經此工具把該檔當下的
sha256 補進 config/approved.json 的 approved 清單（slug="season-intro-<year>"），賽季頁才會渲染
導言區塊。任何後續對 .md 的位元改動都會使 sha 失效、頁面自動退回無導言狀態（need 重新核准）。

★ 護欄：核准前一律先跑 scripts/check-season-intros.py 對該年對帳；不過就拒絕核准（--force 可略過，
   但那是繞過機械對帳、不建議）。approved_by 預設 charlie，可 --by 覆寫。

用法：
  python3 scripts/approve-season-intro.py 2002              # 對帳→核准 2002
  python3 scripts/approve-season-intro.py 2002 1950 1988    # 一次核准多年
  python3 scripts/approve-season-intro.py 2002 --dry-run    # 只印會寫入的條目，不落盤
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
APPROVED = ROOT / "config" / "approved.json"
CONTENT = ROOT / "content" / "seasons"


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _reconcile(year):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check-season-intros.py"), str(year)],
                       capture_output=True, text=True)
    return r.returncode == 0, r.stdout + r.stderr


def main(argv):
    ap = argparse.ArgumentParser(description="核准賽季導言：sha256 寫入 config/approved.json。")
    ap.add_argument("years", type=int, nargs="+", help="要核准的賽季年份")
    ap.add_argument("--by", default="charlie", help="approved_by（預設 charlie）")
    ap.add_argument("--force", action="store_true", help="略過機械對帳（不建議）")
    ap.add_argument("--dry-run", action="store_true", help="只印，不落盤")
    args = ap.parse_args(argv)

    doc = json.loads(APPROVED.read_text(encoding="utf-8"))
    entries = doc.setdefault("approved", [])
    by_slug = {e.get("slug"): e for e in entries}

    now = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    for year in args.years:
        md = CONTENT / f"{year}.md"
        if not md.exists():
            print(f"❌ {year}：缺 {md.relative_to(ROOT)}")
            return 1
        if not args.force:
            ok, out = _reconcile(year)
            if not ok:
                print(f"❌ {year}：機械對帳未過，拒絕核准。\n{out}")
                return 1
            print(f"✓ {year}：機械對帳通過")
        slug = f"season-intro-{year}"
        entry = {
            "slug": slug,
            "article_sha256": _sha(md),
            "facts_sha256": _sha(CONTENT / f"{year}.facts.json") if (CONTENT / f"{year}.facts.json").exists() else None,
            "check_report_sha256": None,
            "approved_by": args.by,
            "approved_at": now,
            "note": f"{year} 賽季人工導言核准",
        }
        if slug in by_slug:
            by_slug[slug].update(entry)
            print(f"  ↻ 更新既有核准條目 {slug}")
        else:
            entries.append(entry)
            print(f"  ＋ 新增核准條目 {slug}  sha={entry['article_sha256'][:12]}…")

    if args.dry_run:
        print("\n[dry-run] 未落盤。將寫入：")
        print(json.dumps({"approved": entries}, ensure_ascii=False, indent=2))
        return 0
    APPROVED.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n已寫入 {APPROVED.relative_to(ROOT)}。重生賽季頁即會渲染導言：")
    print("  python3 scripts/gen-racing-seasons.py --all --rounds-for 2002 2026")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
