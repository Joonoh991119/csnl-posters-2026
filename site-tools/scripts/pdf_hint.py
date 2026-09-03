#!/usr/bin/env python3
"""포스터 파일에서 제목·저자·포스터 번호 후보를 뽑는다. 확인용 초안이지 정답이 아니다.

  python3 scripts/pdf_hint.py <poster.pdf>

포스터는 다단 조판이라 텍스트 추출 순서가 뒤섞인다. 그래서 이 스크립트는 값을 확정하지 않고
후보만 내놓는다. 인터뷰에서 사람에게 그대로 보여 주고 확인을 받는다 —
초록에 제출한 제목과 글자가 달라지면 안 되기 때문이다.

이메일은 주소를 찍지 않고 몇 건 있었는지만 알린다. 포스터에 적힌 주소를 본인 확인 없이
공개 페이지로 옮기지 않는다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PNO = re.compile(r"\b(P-?\s?\d{1,4}|[A-Z]{1,3}-\d{1,4})\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
SUPER = re.compile(r"[¹²³⁴⁵⁶⁷⁸⁹*†‡]")
AFFIL_HINT = re.compile(r"(University|Department|Institute|Laboratory|Lab\b|대학교|학과|연구실)", re.I)


def first_page_text(pdf: Path) -> str | None:
    if not shutil.which("pdftotext"):
        return None
    try:
        r = subprocess.run(["pdftotext", "-f", "1", "-l", "1", "-layout", str(pdf), "-"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def analyse(text: str) -> dict:
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    head = lines[:14]

    pno = None
    for ln in head[:6]:
        m = PNO.search(ln)
        if m:
            pno = m.group(1).replace(" ", "")
            break

    title, authors = None, None
    for ln in head[:6]:
        body = PNO.sub("", ln).strip(" |·-")
        # 저자와 소속이 한 줄에 파이프로 붙어 나오는 판형이 많다 — 앞쪽만 본다
        lead = re.split(r"\s*\|\s*", body)[0].strip()
        if SUPER.search(lead) and (lead.count(",") >= 1 or " and " in lead) and 1 < len(lead.split()) < 22 \
                and not AFFIL_HINT.search(lead):
            authors = authors or lead
            continue
        if len(body.split()) < 5 or AFFIL_HINT.search(body) or EMAIL.search(body):
            continue
        if title is None:
            title = body
    if title is None:
        cands = [PNO.sub("", ln).strip(" |·-") for ln in head[:6]]
        cands = [c for c in cands if len(c.split()) >= 5]
        title = max(cands, key=len) if cands else None
    if authors:
        authors = re.split(r"\s*\|\s*", authors)[0]
        authors = SUPER.sub("", authors).strip(" ,")

    return {
        "poster_no": pno,
        "title": title,
        "authors": authors,
        "emails_found": len(set(EMAIL.findall("\n".join(head)))),
    }


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("사용법: pdf_hint.py <poster.pdf>")
    pdf = Path(sys.argv[1]).expanduser()
    if not pdf.exists():
        raise SystemExit(f"파일이 없다: {pdf}")
    if pdf.suffix.lower() != ".pdf":
        print(json.dumps({"note": "PDF 가 아니라 텍스트를 뽑을 수 없다. 제목·저자는 직접 물어야 한다."},
                         ensure_ascii=False, indent=2))
        return 0
    text = first_page_text(pdf)
    if text is None:
        print(json.dumps({"note": "pdftotext 가 없다 (brew install poppler). 제목·저자는 직접 물어야 한다."},
                         ensure_ascii=False, indent=2))
        return 0
    out = analyse(text)
    out["note"] = ("후보일 뿐이다. 다단 조판이라 순서가 뒤섞인다 — 사람에게 그대로 보여 주고 "
                   "확인받은 뒤에만 쓴다.")
    if out["emails_found"]:
        out["email_note"] = (f"포스터에 이메일 {out['emails_found']}건이 있다. 주소는 찍지 않는다 — "
                             "공개 페이지에 넣을지는 본인에게 묻는다.")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
