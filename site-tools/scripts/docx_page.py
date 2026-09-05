#!/usr/bin/env python3
"""docx 를 사이트 지면에 얹을 본문 HTML 로 바꾼다. 표준 라이브러리만.

수식과 첨자를 흘리지 않는 것이 이 파일의 전부다. docx 에서 글자만 뽑으면
F_c 는 "Fc" 가 되고 Park¹ 은 "Park1" 이 되며 𝔼 는 "E" 가 된다 — 초록이 조용히 틀린다.
그래서 w:vertAlign(위·아래 첨자), w:b, w:i, 그리고 m:oMath 안의 m:scr(서체 변형)까지 읽는다.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"

# m:scr 서체 변형 → 유니크한 글자로. 스타일이 아니라 글자 자체가 뜻을 갖는다.
_DS_UPPER = {"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"}


def _variant(ch: str, scr: str) -> str:
    if not ch.isascii() or not ch.isalpha():
        return ch
    o = ord(ch)
    upper = ch.isupper()
    idx = o - (ord("A") if upper else ord("a"))
    if scr == "double-struck":
        if upper and ch in _DS_UPPER:
            return _DS_UPPER[ch]
        return chr((0x1D538 if upper else 0x1D552) + idx)
    if scr == "script":
        return chr((0x1D49C if upper else 0x1D4B6) + idx)
    if scr == "fraktur":
        return chr((0x1D504 if upper else 0x1D51E) + idx)
    if scr == "sans-serif":
        return chr((0x1D5A0 if upper else 0x1D5BA) + idx)
    if scr == "monospace":
        return chr((0x1D670 if upper else 0x1D68A) + idx)
    return ch


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _run_html(r: ET.Element) -> str:
    pr = r.find(f"{W}rPr")
    b = pr is not None and pr.find(f"{W}b") is not None
    i = pr is not None and pr.find(f"{W}i") is not None
    va = pr.find(f"{W}vertAlign") if pr is not None else None
    va = va.get(f"{W}val") if va is not None else None

    out = []
    for node in r:
        tag = node.tag
        if tag == f"{W}t":
            out.append(esc(node.text or ""))
        elif tag in (f"{W}tab",):
            out.append(" ")
        elif tag in (f"{W}br", f"{W}cr"):
            out.append("<br>")
        elif tag == f"{W}noBreakHyphen":
            out.append("&#8209;")
    text = "".join(out)
    if not text:
        return ""
    if b:
        text = f"<strong>{text}</strong>"
    if i:
        text = f"<em>{text}</em>"
    if va == "superscript":
        text = f"<sup>{text}</sup>"
    elif va == "subscript":
        text = f"<sub>{text}</sub>"
    return text


def _math_html(om: ET.Element) -> str:
    """m:oMath → 인라인 수식 조각.

    Word 는 한 수식을 여러 조각으로 쪼개 본문과 번갈아 넣는 일이 잦다
    (예: Fc( · 𝔼 · [θ|m]) ). 조각을 의미 있는 MathML 로 되살리려면 추측이 필요해서,
    읽기 순서를 그대로 두고 글자 변형만 정확히 옮긴다.
    """
    parts = []
    for r in om.iter(f"{M}r"):
        pr = r.find(f"{M}rPr")
        scr = pr.find(f"{M}scr") if pr is not None else None
        scr = scr.get(f"{M}val") if scr is not None else ""
        for t in r.findall(f"{M}t"):
            s = t.text or ""
            parts.append("".join(_variant(c, scr) for c in s) if scr else s)
    body = esc("".join(parts))
    return f'<span class="math">{body}</span>' if body.strip() else ""


def _para_html(p: ET.Element) -> str:
    chunks = []
    for node in p:
        if node.tag == f"{W}r":
            chunks.append(_run_html(node))
        elif node.tag in (f"{M}oMath", f"{M}oMathPara"):
            chunks.append(_math_html(node))
        elif node.tag == f"{W}hyperlink":
            inner = "".join(_run_html(r) for r in node.findall(f"{W}r"))
            if inner:
                chunks.append(inner)
    text = "".join(chunks).strip()
    return f"<p>{text}</p>" if text else ""


def _table_html(tbl: ET.Element) -> str:
    rows = []
    for tr in tbl.findall(f"{W}tr"):
        cells = []
        for tc in tr.findall(f"{W}tc"):
            inner = "".join(_para_html(p) for p in tc.findall(f"{W}p"))
            cells.append(f"<td>{inner or '&nbsp;'}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    if not rows:
        return ""
    return '<div class="table-wrap"><table>' + "".join(rows) + "</table></div>"


def render(path: Path) -> tuple[str, list[str]]:
    """(본문 HTML, 메모)"""
    notes: list[str] = []
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
        media = [n for n in z.namelist() if n.startswith("word/media/")]
    root = ET.fromstring(xml)
    body = root.find(f"{W}body")
    out = []
    for node in list(body):
        if node.tag == f"{W}p":
            out.append(_para_html(node))
        elif node.tag == f"{W}tbl":
            out.append(_table_html(node))
    html = "\n".join(x for x in out if x)

    n_math = len(root.findall(f".//{M}oMath"))
    n_sub = len(root.findall(f".//{W}vertAlign"))
    if n_math or n_sub:
        notes.append(f"수식 조각 {n_math}개와 첨자 {n_sub}개를 살려서 옮겼다")
    if media:
        notes.append(f"docx 안에 그림 {len(media)}개가 있다 — 이 변환기는 글과 표만 옮긴다")
    return html, notes
