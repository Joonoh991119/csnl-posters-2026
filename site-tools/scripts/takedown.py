#!/usr/bin/env python3
"""게시 종료 — dist 를 안내 페이지 하나로 갈아 끼운다. 원본 자료는 건드리지 않는다.

  python3 scripts/takedown.py [--root ./poster-site] [--purge]

--purge 는 dist 를 통째로 지운다. people/ 과 assets/ 는 어느 쪽이든 남는다.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitelib import esc, fmt_date_range, load_config, paths  # noqa: E402

TOMB = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<main id="main"><div class="wrap">
  <header class="site-head">
    <p class="eyebrow">{lab}</p>
    <h1>게시가 종료되었습니다</h1>
    <p class="lede">{title} 의 포스터 페이지는 {window} 동안만 열려 있었습니다.
    자료가 필요하시면 저자에게 직접 연락해 주세요.</p>
    <div class="actions">{link}</div>
  </header>
</div></main>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="poster-site 게시 종료")
    ap.add_argument("--root", default=None)
    ap.add_argument("--purge", action="store_true", help="dist 를 통째로 지운다")
    a = ap.parse_args()

    pth = paths(a.root)
    cfg = load_config(a.root)
    dist = pth["dist"]
    site = cfg.get("site", {})
    w = cfg.get("window", {}) or {}

    if a.purge:
        if dist.exists():
            shutil.rmtree(dist)
        print(f"dist 삭제 완료 ({dist})")
    else:
        css = dist / "assets" / "site.css"
        keep = css.read_text(encoding="utf-8") if css.exists() else None
        if dist.exists():
            shutil.rmtree(dist)
        (dist / "assets").mkdir(parents=True, exist_ok=True)
        if keep:
            css.write_text(keep, encoding="utf-8")
        else:
            src = Path(__file__).resolve().parent.parent / "templates" / "site.css"
            shutil.copy2(src, css)
        link = ""
        if site.get("lab_home_url"):
            link = (f'<a class="btn btn-primary" href="{esc(site["lab_home_url"])}" '
                    f'target="_blank" rel="noopener">연구실 홈 <span class="ext">↗</span></a>')
        (dist / "index.html").write_text(
            TOMB.format(title=esc(site.get("title", "")), lab=esc(site.get("lab_short") or site.get("lab_name") or ""),
                        window=esc(fmt_date_range(w.get("start"), w.get("end")) or "학회 기간"), link=link),
            encoding="utf-8")
        (dist / ".nojekyll").write_text("", encoding="utf-8")
        print(f"안내 페이지로 교체 완료 ({dist / 'index.html'})")

    print("\n원본은 그대로 남아 있다: people/, assets/")
    d = cfg.get("deploy", {}) or {}
    if d.get("url"):
        print(f"\n배포본도 내려야 한다 — {d['url']}")
        print("  git 배포라면: dist 를 다시 커밋·푸시하면 위 안내 페이지로 바뀐다")
        print("  완전히 내리려면 GitHub Pages 를 끄거나 저장소를 private 으로 돌린다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
