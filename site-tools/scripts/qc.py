#!/usr/bin/env python3
"""브라우저·화면 폭·테마를 가로질러 사이트를 점검한다.

  python3 scripts/qc.py --root ./poster-site [--engines chromium,firefox,webkit]

playwright 가 있으면 쓰고, 없으면 그 사실을 말하고 조용히 끝낸다 (필수 의존성이 아니다).
  pip install playwright && python3 -m playwright install chromium firefox webkit

무엇을 잡나
  · 가로 스크롤 — 좁은 화면에서 지면이 밀리는 것
  · 깨진 이미지 — 경로가 틀렸거나 파일이 안 올라간 것
  · 작은 탭 타깃 — 손가락으로 못 누르는 버튼 (40px 미만)
  · 페이지 오류 — 콘솔에 뜬 예외
  · 동작 — 포스터 확대(열기·100%·닫기), 이메일 조립, 이전/다음

마지막 항목이 있는 이유: CSS 클래스 이름을 바꾸면서 JS 선택자를 안 고쳐 확대가
조용히 죽은 적이 있다. 화면만 봐서는 멀쩡했다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitelib import paths  # noqa: E402

VIEWS = [("320", 320, 568), ("390", 390, 844), ("834", 834, 1112), ("1440", 1440, 900)]

CHECK = """() => {
  const vw = document.documentElement.clientWidth;
  const imgs = [...document.querySelectorAll('img')];
  return {
    overflow: document.documentElement.scrollWidth - vw,
    broken: imgs.filter(i => i.complete && i.naturalWidth === 0)
                .map(i => i.getAttribute('src') || '(src 없음)'),
    tiny: [...document.querySelectorAll('a.btn,button.btn,.step,.lb-btn')]
      .filter(b => { const r = b.getBoundingClientRect(); return r.height > 0 && r.height < 40; })
      .map(b => (b.textContent || '').trim().slice(0, 14)),
  };
}"""


def main() -> int:
    ap = argparse.ArgumentParser(description="poster-site 교차 브라우저 점검")
    ap.add_argument("--root", default=None)
    ap.add_argument("--engines", default="chromium,firefox,webkit")
    a = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 가 없어 건너뛴다. 화면 점검을 하려면:")
        print("  pip install playwright && python3 -m playwright install chromium firefox webkit")
        return 0

    dist = paths(a.root)["dist"]
    if not (dist / "index.html").exists():
        raise SystemExit(f"dist 가 없다: {dist}\n  먼저 build_site.py")

    pages = [("index", dist / "index.html")]
    for f in sorted((dist / "p").glob("*.html")):
        pages.append((f.stem, f))

    problems: list[str] = []
    checked = 0
    with sync_playwright() as pw:
        for eng in [e.strip() for e in a.engines.split(",") if e.strip()]:
            try:
                br = getattr(pw, eng).launch()
            except Exception as e:
                print(f"  {eng}: 실행 파일이 없다 — 건너뛴다 ({str(e)[:50]})")
                continue
            for scheme in ("light", "dark"):
                for vname, w, h in VIEWS:
                    ctx = br.new_context(viewport={"width": w, "height": h}, color_scheme=scheme)
                    pg = ctx.new_page()
                    errs: list[str] = []
                    pg.on("pageerror", lambda e: errs.append(str(e)[:70]))
                    for name, f in pages:
                        pg.goto(f.resolve().as_uri())
                        pg.wait_for_timeout(180)
                        r = pg.evaluate(CHECK)
                        checked += 1
                        where = f"{eng}/{vname}/{scheme}/{name}"
                        if r["overflow"] > 0:
                            problems.append(f"{where}: 가로 스크롤 +{r['overflow']}px")
                        for s in r["broken"]:
                            problems.append(f"{where}: 이미지가 안 뜬다 — {s}")
                        for s in r["tiny"]:
                            problems.append(f"{where}: 탭 타깃이 40px 미만 — '{s}'")
                    for e in errs:
                        problems.append(f"{eng}/{vname}/{scheme}: 페이지 오류 — {e}")
                    ctx.close()

            # ---- 동작 확인 (한 조합만) ----
            ctx = br.new_context(viewport={"width": 390, "height": 844})
            pg = ctx.new_page()
            target = next((f for n, f in pages if n not in ("index",)
                           and "data-zoom" in f.read_text(encoding="utf-8")), None)
            if target:
                pg.goto(target.resolve().as_uri())
                pg.wait_for_timeout(300)
                pg.click(".plate")
                pg.wait_for_timeout(400)
                if not pg.evaluate("document.getElementById('lightbox').classList.contains('on')"):
                    problems.append(f"{eng}: 포스터를 눌러도 확대가 열리지 않는다")
                else:
                    pg.click('[data-lb="scale"]')
                    pg.wait_for_timeout(250)
                    if not pg.evaluate("document.querySelector('#lightbox img').classList.contains('full')"):
                        problems.append(f"{eng}: 확대에서 100% 토글이 듣지 않는다")
                    pg.keyboard.press("Escape")
                    pg.wait_for_timeout(200)
                    if pg.evaluate("document.getElementById('lightbox').classList.contains('on')"):
                        problems.append(f"{eng}: ESC 로 확대가 닫히지 않는다")
                mail = pg.evaluate("document.querySelector('[data-eu]')?.getAttribute('href') || ''")
                if mail and not mail.startswith("mailto:"):
                    problems.append(f"{eng}: 이메일 주소가 조립되지 않았다")
            ctx.close()
            br.close()

    print(f"=== poster-site 화면 점검 — {checked}회 확인 ===")
    if not problems:
        print("문제 없음. 브라우저·화면 폭·테마를 가로질러 같은 화면이 나온다.")
        return 0
    print(f"\n문제 {len(problems)}건")
    for p in problems[:40]:
        print("  ✘", p)
    if len(problems) > 40:
        print(f"  … 외 {len(problems) - 40}건")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
