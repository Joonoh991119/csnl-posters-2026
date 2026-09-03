#!/usr/bin/env python3
"""사이트 뼈대를 만든다 — config.json + 디렉터리 + 참가자 명부.

인터뷰로 받은 값을 JSON 파일 하나로 넘긴다:
  python3 scripts/site_init.py --payload /tmp/init.json [--root ./poster-site] [--force]

payload 예시는 templates/config.example.json 참고. 참가자는 이름만 있어도 된다 —
나머지는 각자 /poster-site:add 로 채운다. 그게 이 플러그인이 커널을 열어 두는 방식이다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitelib import SCHEMA_VERSION, parse_date, paths, read_json, slug, write_json  # noqa: E402


def build_participants(raw: list) -> list[dict]:
    out, seen = [], set()
    for i, item in enumerate(raw, start=1):
        if isinstance(item, str):
            item = {"name": item}
        # 이니셜을 우선한다 — 페이지 주소가 p/jop.html 처럼 짧고 사람이 기억할 수 있어야 한다
        pid = item.get("id") or slug(item.get("initials") or item.get("name_en") or item.get("name") or f"p{i}")
        base, n = pid, 2
        while pid in seen:
            pid, n = f"{base}-{n}", n + 1
        seen.add(pid)
        out.append({
            "id": pid,
            "initials": item.get("initials") or "",
            "name": item.get("name") or "",
            "name_en": item.get("name_en") or "",
            "poster_no": item.get("poster_no") or f"P{i}",
            "order": item.get("order") or i,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="poster-site 초기화")
    ap.add_argument("--payload", required=True, help="인터뷰 결과 JSON 파일")
    ap.add_argument("--root", default=None)
    ap.add_argument("--force", action="store_true", help="기존 config.json 을 덮어쓴다")
    a = ap.parse_args()

    payload = read_json(Path(a.payload))
    pth = paths(a.root)
    if pth["config"].exists() and not a.force:
        raise SystemExit(
            f"이미 사이트가 있다: {pth['config']}\n"
            "참가자만 추가하려면 config.json 의 participants 를 직접 늘리거나 --force 로 다시 만든다."
        )

    w = payload.get("window", {}) or {}
    s, e = parse_date(w.get("start")), parse_date(w.get("end"))
    if s and e and e < s:
        raise SystemExit(f"게시 종료일({w['end']})이 시작일({w['start']})보다 빠르다.")

    cfg = {
        "version": SCHEMA_VERSION,
        "site": {
            "title": payload.get("site", {}).get("title") or "Poster pages",
            "lab_name": payload.get("site", {}).get("lab_name") or "",
            "lab_short": payload.get("site", {}).get("lab_short") or "",
            "lede": payload.get("site", {}).get("lede") or "",
            "members_url": payload.get("site", {}).get("members_url") or "",
            "lab_home_url": payload.get("site", {}).get("lab_home_url") or "",
            "contact_note": payload.get("site", {}).get("contact_note") or "",
            "locale": payload.get("site", {}).get("locale") or "ko",
            "noindex": payload.get("site", {}).get("noindex", True),
        },
        "window": {"start": w.get("start") or "", "end": w.get("end") or "",
                   "timezone": w.get("timezone") or "Asia/Seoul"},
        "defaults": {
            "conference": payload.get("defaults", {}).get("conference") or "",
            "conference_short": payload.get("defaults", {}).get("conference_short") or "",
            "poster_size": payload.get("defaults", {}).get("poster_size") or "A0",
            "orientation": payload.get("defaults", {}).get("orientation") or "",
            "affiliation": payload.get("defaults", {}).get("affiliation") or "",
        },
        "participants": build_participants(payload.get("participants", [])),
        "deploy": {"kind": payload.get("deploy", {}).get("kind") or "github-pages",
                   "repo": payload.get("deploy", {}).get("repo") or "",
                   "url": payload.get("deploy", {}).get("url") or ""},
    }

    for d in ("people", "assets"):
        (pth["root"] / d).mkdir(parents=True, exist_ok=True)
    write_json(pth["config"], cfg)
    for part in cfg["participants"]:
        (pth["assets"] / part["id"]).mkdir(parents=True, exist_ok=True)

    print(f"사이트 생성 → {pth['root']}")
    print(f"  제목      {cfg['site']['title']}")
    print(f"  게시기간  {cfg['window']['start'] or '(미정)'} ~ {cfg['window']['end'] or '(미정)'}")
    print(f"  참가자    {len(cfg['participants'])}명")
    for p in cfg["participants"]:
        print(f"    {p['poster_no']:>4}  {p['id']:<12} {p['name'] or p['name_en'] or p['initials']}")
    print("\n다음: /poster-site:build 로 뼈대를 그리고, 각자 /poster-site:add 로 채운다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
