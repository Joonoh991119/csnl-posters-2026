#!/usr/bin/env python3
"""참가자별 QR 코드를 만든다 — 인쇄용 SVG 와 화면용 PNG, 그리고 인쇄 시트 하나.

  python3 scripts/make_qr.py --root ./poster-site [--base-url https://...] [--ecl Q]

포스터에는 자기 페이지로 바로 가는 QR 을 붙인다. 목록으로 보내면 학회장에서
사람이 자기 포스터를 다시 찾아야 한다 — 그 한 단계가 스캔을 무산시킨다.

EC 레벨 기본값은 Q(30% 복원). 포스터는 구겨지고 조명이 나쁘고 각도가 비뚤다.
M 보다 모듈이 조금 커지지만 그만한 값을 한다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qr  # noqa: E402
from sitelib import esc, load_config, load_people, paths  # noqa: E402


def sheet_html(rows: list[dict], base: str) -> str:
    cards = "".join(
        f'<figure><img src="{esc(r["svg"])}" alt="QR for {esc(r["label"])}">'
        f'<figcaption><b>{esc(r["pno"])}</b> {esc(r["label"])}<br>'
        f'<span>{esc(r["url"])}</span></figcaption></figure>'
        for r in rows
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>QR codes — print sheet</title>
<style>
  body {{ font: 13px/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #16181c;
         margin: 28px; background: #fff; }}
  h1 {{ font-size: 17px; margin: 0 0 4px; }}
  p.note {{ color: #666c74; margin: 0 0 22px; max-width: 70ch; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 26px; }}
  figure {{ margin: 0; }}
  img {{ width: 100%; height: auto; border: 1px solid #e3e3df; display: block; }}
  figcaption {{ margin-top: 7px; font-size: 12px; line-height: 1.45; }}
  figcaption b {{ color: #c22f27; letter-spacing: .05em; }}
  figcaption span {{ color: #666c74; word-break: break-all; font-size: 11px; }}
  @media print {{ body {{ margin: 12mm; }} p.note {{ display: none; }} }}
</style></head><body>
<h1>QR codes — {esc(base)}</h1>
<p class="note">Print at 100%. On the poster, place the code at least 30 mm square with the
URL printed beside it in readable type — cameras fail often enough that the text matters.</p>
<div class="grid">{cards}</div>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="참가자별 QR 생성")
    ap.add_argument("--root", default=None)
    ap.add_argument("--base-url", default=None, help="배포 주소. 없으면 config 의 deploy.url")
    ap.add_argument("--ecl", default="Q", choices=["M", "Q"], help="오류 정정 수준 (기본 Q)")
    ap.add_argument("--module", type=int, default=12, help="PNG 모듈 픽셀 (기본 12)")
    a = ap.parse_args()

    pth = paths(a.root)
    cfg = load_config(a.root)
    people = {p["id"]: p for p in load_people(a.root)}
    base = (a.base_url or (cfg.get("deploy", {}) or {}).get("url") or "").rstrip("/")
    if not base:
        raise SystemExit(
            "배포 주소를 모른다. /poster-site:publish 로 먼저 올리거나 --base-url 을 준다."
        )

    out = pth["root"] / "qr"
    out.mkdir(parents=True, exist_ok=True)
    rows = []

    targets = [("index", base + "/", cfg.get("site", {}).get("title", "All posters"), "ALL")]
    for part in sorted(cfg.get("participants", []), key=lambda x: (x.get("order", 99),)):
        pid = part["id"]
        p = people.get(pid, part)
        label = p.get("name") or p.get("name_en") or part.get("initials") or pid
        targets.append((pid, f"{base}/p/{pid}.html", label, part.get("poster_no") or ""))

    for pid, url, label, pno in targets:
        m = qr.make_matrix(url, a.ecl)
        version = (len(m) - 17) // 4
        svg_path, png_path = out / f"{pid}.svg", out / f"{pid}.png"
        svg_path.write_text(qr.to_svg(m), encoding="utf-8")
        qr.to_png(m, png_path, module=a.module)
        rows.append({"svg": f"{pid}.svg", "label": label, "pno": pno or "—", "url": url})
        print(f"  {pno or '—':>6}  {pid:<8} v{version}-{a.ecl}  {len(m)}×{len(m)} modules  → qr/{pid}.svg + .png")

    (out / "sheet.html").write_text(sheet_html(rows, base), encoding="utf-8")
    print(f"\n{len(rows)}개 생성 → {out}")
    print(f"  인쇄 시트: {out / 'sheet.html'}")
    print("  포스터에는 SVG 를 넣는다 (벡터라 어떤 크기로 뽑아도 선명하다).")
    print("  최소 30mm 각, 옆에 URL 을 사람이 읽을 수 있게 같이 적을 것.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
