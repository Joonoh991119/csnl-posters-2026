#!/usr/bin/env python3
"""누가 냈고 누가 안 냈는지, 게시기간이 얼마나 남았는지."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitelib import fmt_date_range, load_config, load_people, paths, window_state  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="poster-site 현황")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()

    pth = paths(a.root)
    cfg = load_config(a.root)
    people = {p["id"]: p for p in load_people(a.root)}
    site = cfg.get("site", {})
    w = cfg.get("window", {}) or {}
    state, days = window_state(cfg)
    label = {"before": "게시 전", "open": "게시 중", "closed": "게시 종료", "unset": "기간 미설정"}[state]

    print(f"{site.get('title', '(제목 없음)')}")
    print(f"  게시기간  {fmt_date_range(w.get('start'), w.get('end')) or '(미정)'}  [{label}"
          + (f" · D-{days}]" if state == "open" and days is not None else "]"))
    print(f"  배포      {cfg.get('deploy', {}).get('url') or '(아직 배포 안 함)'}")
    print()
    print(f"  {'번호':<5} {'id':<12} {'이름':<12} {'상태':<8} 빠진 것")
    print(f"  {'-'*5} {'-'*12} {'-'*12} {'-'*8} {'-'*30}")
    for part in sorted(cfg.get("participants", []), key=lambda x: (x.get("order", 99),)):
        pid = part["id"]
        p = people.get(pid)
        name = (p or part).get("name") or (p or part).get("name_en") or part.get("initials") or ""
        if not p:
            print(f"  {part.get('poster_no', ''):<5} {pid:<12} {name:<12} {'미제출':<8} 전부")
            continue
        miss = []
        if not (p.get("conference", {}) or {}).get("name"):
            miss.append("학회명")
        if not (p.get("conference", {}) or {}).get("date"):
            miss.append("날짜")
        if not (p.get("poster", {}) or {}).get("title"):
            miss.append("제목")
        if not (p.get("poster", {}) or {}).get("file"):
            miss.append("PDF")
        opt = []
        if p.get("supplementary"):
            opt.append(f"supp {len(p['supplementary'])}")
        if p.get("references"):
            opt.append(f"ref {len(p['references'])}")
        if (p.get("contact", {}) or {}).get("linkedin"):
            opt.append("in")
        state_txt = "완료" if not miss else "부분"
        if p.get("publish") is False:
            state_txt = "보류"
        print(f"  {p.get('poster_no', ''):<5} {pid:<12} {name:<12} {state_txt:<8} "
              f"{', '.join(miss) if miss else '—'}"
              + (f"   ({', '.join(opt)})" if opt else ""))
    held = [k for k, v in people.items() if v.get("publish") is False]
    print(f"\n  등록 {len(people)} / {len(cfg.get('participants', []))}"
          + (f" · 공개 보류 {len(held)}명 ({', '.join(held)}) — 본인이 /poster-site:join 으로 확인하면 열린다"
             if held else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
