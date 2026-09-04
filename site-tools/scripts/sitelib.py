#!/usr/bin/env python3
"""poster-site 공용 라이브러리 — 경로, 스키마, PDF 판독, 미리보기 생성.

표준 라이브러리만 쓴다. 외부 도구(pdftoppm / magick / sips / qlmanage)는 있으면 쓰고
없으면 미리보기 없이 진행한다 — 사이트는 미리보기가 없어도 동작해야 한다.
"""
from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
import unicodedata
from datetime import date, datetime
from pathlib import Path

SCHEMA_VERSION = 1
PT_PER_MM = 72.0 / 25.4

# A0 = 841 x 1189 mm. 학회마다 재단이 조금씩 달라 15% 여유를 둔다.
KNOWN_SIZES = {
    "A0": (841.0, 1189.0),
    "A1": (594.0, 841.0),
    "A2": (420.0, 594.0),
    "36x48in": (914.4, 1219.2),
    "42x42in": (1066.8, 1066.8),
    "90x120cm": (900.0, 1200.0),
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


# ----------------------------------------------------------------- 경로
def site_root(root: str | Path | None = None) -> Path:
    """작업 루트. 기본값은 현재 디렉터리의 poster-site/."""
    if root:
        return Path(root).expanduser().resolve()
    return (Path.cwd() / "poster-site").resolve()


def paths(root: str | Path | None = None) -> dict[str, Path]:
    r = site_root(root)
    return {
        "root": r,
        "config": r / "config.json",
        "people": r / "people",
        "assets": r / "assets",
        "dist": r / "dist",
    }


# ----------------------------------------------------------------- json io
def read_json(p: Path) -> dict:
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def load_config(root=None) -> dict:
    p = paths(root)["config"]
    if not p.exists():
        raise SystemExit(
            "config.json 이 없다. 먼저 /poster-site:init 으로 사이트를 만든다.\n"
            f"  찾은 위치: {p}"
        )
    return read_json(p)


def load_people(root=None) -> list[dict]:
    d = paths(root)["people"]
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        try:
            out.append(read_json(f))
        except json.JSONDecodeError as e:
            raise SystemExit(f"{f.name} 을 읽을 수 없다: {e}")
    return out


# ----------------------------------------------------------------- 문자열
def slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t or "person"


def esc(text) -> str:
    """HTML 이스케이프. None 은 빈 문자열."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def parse_date(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            continue
    return None


def fmt_date_range(start, end=None) -> str:
    a, b = parse_date(start), parse_date(end)
    if not a:
        return str(start or "")
    if not b or b == a:
        return a.strftime("%Y.%m.%d")
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.strftime('%Y.%m.%d')}–{b.strftime('%d')}"
    if a.year == b.year:
        return f"{a.strftime('%Y.%m.%d')}–{b.strftime('%m.%d')}"
    return f"{a.strftime('%Y.%m.%d')}–{b.strftime('%Y.%m.%d')}"


# ----------------------------------------------------------------- PDF 판독
_MEDIABOX = re.compile(rb"/MediaBox\s*\[\s*([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s*\]")
_ROTATE = re.compile(rb"/Rotate\s+(-?\d+)")


def pdf_page_size(pdf: Path) -> dict | None:
    """첫 MediaBox 로 페이지 크기(mm)와 방향을 읽는다. 외부 도구 없이.

    반환: {"w_mm", "h_mm", "orientation", "size_label", "rotate"} 또는 None.
    """
    try:
        blob = Path(pdf).read_bytes()
    except OSError:
        return None
    m = _MEDIABOX.search(blob)
    if not m:
        return None
    x0, y0, x1, y1 = (float(v) for v in m.groups())
    w_pt, h_pt = abs(x1 - x0), abs(y1 - y0)
    r = _ROTATE.search(blob)
    rot = int(r.group(1)) % 360 if r else 0
    if rot in (90, 270):
        w_pt, h_pt = h_pt, w_pt
    w_mm, h_mm = w_pt / PT_PER_MM, h_pt / PT_PER_MM
    orientation = "landscape" if w_mm > h_mm else "portrait"

    label = _label_for(w_mm, h_mm)
    return {
        "w_mm": round(w_mm, 1),
        "h_mm": round(h_mm, 1),
        "orientation": orientation,
        "size_label": label,
        "rotate": rot,
    }


def image_size(path: Path) -> tuple[int, int] | None:
    """PNG / JPEG 픽셀 크기를 헤더에서 읽는다. 외부 라이브러리 없이."""
    try:
        blob = Path(path).read_bytes()
    except OSError:
        return None
    if blob[:8] == b"\x89PNG\r\n\x1a\n" and blob[12:16] == b"IHDR":
        w, h = struct.unpack(">II", blob[16:24])
        return int(w), int(h)
    if blob[:2] == b"\xff\xd8":                      # JPEG
        i, n = 2, len(blob)
        while i + 9 < n:
            if blob[i] != 0xFF:
                i += 1
                continue
            marker = blob[i + 1]
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = int.from_bytes(blob[i + 2:i + 4], "big")
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", blob[i + 5:i + 9])
                return int(w), int(h)
            i += 2 + seg
    return None


def _label_for(w: float, h: float) -> str | None:
    long_a, short_a = max(w, h), min(w, h)
    for name, (sw, sh) in KNOWN_SIZES.items():
        long_b, short_b = max(sw, sh), min(sw, sh)
        if abs(long_a - long_b) / long_b < 0.15 and abs(short_a - short_b) / short_b < 0.15:
            return name
    return None


def poster_geometry(path: Path) -> dict | None:
    """포스터 파일의 방향과 크기. PDF 는 mm, 이미지는 px + 비율만.

    포스터를 PDF 로만 내는 사람은 없다 — PowerPoint 에서 PNG 로 뽑아 오는 경우가 흔하다.
    이미지는 물리 크기를 알 수 없으므로 비율로만 규격을 추정하고, 그 사실을 kind 로 남긴다.
    """
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        info = pdf_page_size(path)
        if info:
            info["kind"] = "pdf"
        return info
    if path.suffix.lower() in IMAGE_EXT:
        wh = image_size(path)
        if not wh:
            return None
        w, h = wh
        ar = w / h if h else 1.0
        label = None
        for name, (sw, sh) in KNOWN_SIZES.items():
            known = (max(sw, sh) / min(sw, sh))
            if abs((max(w, h) / min(w, h)) - known) / known < 0.02:
                label = name
                break
        return {
            "w_px": w, "h_px": h, "w_mm": None, "h_mm": None,
            "orientation": "landscape" if w > h else "portrait",
            "size_label": label, "aspect": round(ar, 4), "rotate": 0, "kind": "image",
        }
    return None


def aspect(orientation: str, w_mm=None, h_mm=None) -> str:
    """CSS aspect-ratio 값. 실측이 있으면 그것을, 없으면 A0 기본."""
    if w_mm and h_mm:
        return f"{w_mm:.0f} / {h_mm:.0f}"
    return "1189 / 841" if orientation == "landscape" else "841 / 1189"


def aspect_num(orientation: str, w_mm=None, h_mm=None) -> float:
    """가로/세로 비를 소수로. CSS 에서 높이 상한을 너비 상한으로 환산할 때 쓴다.

    aspect-ratio 는 auto 인 축만 채운다. height 를 고정한 채 max-width 로 자르면
    비율이 깨지므로(가로 포스터가 세로로 늘어난다), 대신 너비 상한을
    (허용 높이 × 이 값) 으로 계산해 높이를 auto 로 남긴다.
    """
    if w_mm and h_mm and h_mm > 0:
        return round(float(w_mm) / float(h_mm), 4)
    return 1.4137 if orientation == "landscape" else 0.7074


# ----------------------------------------------------------------- 미리보기
def _run(cmd) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def make_preview(pdf: Path, out_jpg: Path, long_edge: int = 1600) -> str | None:
    """포스터 첫 페이지를 이미지로. 성공하면 도구 이름, 실패하면 None.

    A0 PDF 를 브라우저에 그대로 물리면 모바일에서 먹통이 된다. 미리보기 이미지가
    먼저 뜨고, 원본 PDF 는 버튼으로 연다 — 그게 이 함수가 있는 이유다.
    """
    pdf, out_jpg = Path(pdf), Path(out_jpg)
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    stem = out_jpg.with_suffix("")

    if pdf.suffix.lower() in IMAGE_EXT:          # 이미지 포스터 — 줄이기만 하면 된다
        if shutil.which("sips") and _run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82",
                                          "-Z", str(long_edge), str(pdf), "--out", str(out_jpg)]):
            if out_jpg.exists():
                return "sips"
        for magick in ("magick", "convert"):
            if shutil.which(magick) and _run([magick, str(pdf), "-resize",
                                              f"{long_edge}x{long_edge}", "-quality", "82", str(out_jpg)]):
                if out_jpg.exists():
                    return magick
        shutil.copy2(pdf, out_jpg.with_suffix(pdf.suffix.lower()))
        return "copy"
    
    if shutil.which("pdftoppm"):
        if _run(["pdftoppm", "-jpeg", "-jpegopt", "quality=82", "-r", "0",
                 "-scale-to", str(long_edge), "-f", "1", "-l", "1",
                 "-singlefile", str(pdf), str(stem)]):
            if out_jpg.exists():
                return "pdftoppm"
    for magick in ("magick", "convert"):
        if shutil.which(magick):
            base = [magick] if magick == "convert" else [magick]
            if _run(base + ["-density", "72", f"{pdf}[0]", "-resize",
                            f"{long_edge}x{long_edge}", "-quality", "82", str(out_jpg)]):
                if out_jpg.exists():
                    return magick
    if shutil.which("sips"):
        if _run(["sips", "-s", "format", "jpeg", "-Z", str(long_edge),
                 str(pdf), "--out", str(out_jpg)]):
            if out_jpg.exists():
                return "sips"
    if shutil.which("qlmanage"):
        tmp = out_jpg.parent / "_ql"
        tmp.mkdir(exist_ok=True)
        if _run(["qlmanage", "-t", "-s", str(long_edge), "-o", str(tmp), str(pdf)]):
            hits = list(tmp.glob("*.png"))
            if hits:
                shutil.move(str(hits[0]), str(out_jpg.with_suffix(".png")))
                shutil.rmtree(tmp, ignore_errors=True)
                return "qlmanage"
        shutil.rmtree(tmp, ignore_errors=True)
    return None


# ----------------------------------------------------------------- 게시기간
def window_state(cfg: dict, today: date | None = None) -> tuple[str, int | None]:
    """('before'|'open'|'closed'|'unset', 남은 일수)"""
    today = today or date.today()
    w = cfg.get("window") or {}
    s, e = parse_date(w.get("start")), parse_date(w.get("end"))
    if not s and not e:
        return "unset", None
    if s and today < s:
        return "before", (s - today).days
    if e and today > e:
        return "closed", (today - e).days
    return "open", ((e - today).days if e else None)


def frame_vars(poster: dict) -> tuple[str, float]:
    """포스터 dict → (CSS aspect-ratio 값, 가로세로비 소수).

    PDF 는 mm, 이미지는 px 를 쓴다. 둘 다 없으면 방향만 보고 A0 로 가정한다.
    """
    w = poster.get("w_mm") or poster.get("w_px")
    h = poster.get("h_mm") or poster.get("h_px")
    o = poster.get("orientation", "portrait")
    if w and h:
        return f"{float(w):.0f} / {float(h):.0f}", round(float(w) / float(h), 4)
    return aspect(o), aspect_num(o)


# ---------------------------------------------------------------- 영문 날짜
_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def fmt_date_en(start, end=None) -> str:
    """사이트에 찍히는 날짜. 저널 표기를 따른다 — '15–16 Oct 2026'.

    사이트 언어는 영어로 고정이라 화면용 날짜는 전부 이 함수를 지난다.
    (CLI 출력은 한국어라 fmt_date_range 를 그대로 쓴다.)
    """
    a, b = parse_date(start), parse_date(end)
    if not a:
        return str(start or "")
    if not b or b == a:
        return f"{a.day} {_MON[a.month - 1]} {a.year}"
    if a.year == b.year and a.month == b.month:
        return f"{a.day}–{b.day} {_MON[a.month - 1]} {a.year}"
    if a.year == b.year:
        return f"{a.day} {_MON[a.month - 1]} – {b.day} {_MON[b.month - 1]} {a.year}"
    return f"{a.day} {_MON[a.month - 1]} {a.year} – {b.day} {_MON[b.month - 1]} {b.year}"


def link_value(v) -> str:
    """연락처 링크를 문자열로 정규화한다.

    사람이 손으로 쓰면 {"url": "..."} 처럼 한 겹 싸서 넣는 일이 흔하다. 실제로 겪었고,
    그대로 두면 href 에 파이썬 dict 가 찍혀 버튼이 아무 데도 안 간다.
    문자열 · {url|href|link|value} · 리스트 첫 항목까지 받아 준다.
    """
    if not v:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for key in ("url", "href", "link", "value"):
            if v.get(key):
                return link_value(v[key])
        return ""
    if isinstance(v, (list, tuple)) and v:
        return link_value(v[0])
    return ""
