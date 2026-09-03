#!/usr/bin/env python3
"""poster-site 정적 사이트 빌더.

config.json + people/*.json + assets/ → dist/ (순수 HTML/CSS/JS, 빌드 도구 없음).

원칙
  · 없는 것은 그리지 않는다. 링크드인·서플·레퍼런스·초록은 전부 선택 항목이고,
    비어 있으면 그 섹션 자체가 사라진다 (빈 제목만 남는 페이지를 만들지 않는다).
  · 아직 정보를 안 낸 참가자도 명부에는 남는다 — '준비 중' 카드로. 커널을 열어 두는 방식이다.
  · 포스터 방향과 비율은 파일에서 읽는다 (PDF 는 MediaBox, 이미지는 픽셀).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitelib import (  # noqa: E402
    esc, fmt_date_range, frame_vars, human_size, load_config, load_people,
    make_preview, paths, poster_geometry, window_state,
)

TPL = Path(__file__).resolve().parent.parent / "templates"


# ---------------------------------------------------------------- 조각
def head(title: str, desc: str, css: str, noindex: bool, og: dict | None = None) -> str:
    og = og or {}
    tags = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        '<meta name="color-scheme" content="light dark">',
        f"<title>{esc(title)}</title>",
        f'<meta name="description" content="{esc(desc)}">',
    ]
    if noindex:
        tags.append('<meta name="robots" content="noindex, nofollow">')
    tags += [
        f'<meta property="og:title" content="{esc(og.get("title", title))}">',
        f'<meta property="og:description" content="{esc(og.get("desc", desc))}">',
        '<meta property="og:type" content="website">',
    ]
    if og.get("image"):
        tags.append(f'<meta property="og:image" content="{esc(og["image"])}">')
    tags.append(f'<link rel="stylesheet" href="{css}">')
    return "\n  ".join(tags)


def btn(label: str, href: str, primary=False, external=False, extra="") -> str:
    cls = "btn btn-primary" if primary else "btn"
    ext = ' <span class="ext" aria-hidden="true">↗</span>' if external else ""
    tgt = ' target="_blank" rel="noopener"' if external else ""
    return f'<a class="{cls}" href="{esc(href)}"{tgt} {extra}>{esc(label)}{ext}</a>'


def chip(text: str, strong: str = "") -> str:
    inner = (f"<b>{esc(strong)}</b> " if strong else "") + esc(text)
    return f'<li class="chip">{inner}</li>'


def size_chip(poster: dict) -> str:
    """규격 칩 문구. 측정한 사실만 적는다.

    알려진 규격에 맞지 않으면 규격 이름을 붙이지 않는다 — 실제 mm 는 포스터 아래에 따로 찍힌다.
    이미지 포스터는 물리 크기를 모르므로 '비율' 이라고 밝힌다.
    """
    o = {"portrait": "세로", "landscape": "가로"}.get(poster.get("orientation"), "")
    label = poster.get("size_label") or poster.get("size") or ""
    kind = poster.get("kind")
    if label and kind == "image":
        return f"{label} 비율 · {o}".strip(" ·")
    if label:
        return f"{label} {o}".strip()
    return o


def person_display(p: dict) -> tuple[str, str]:
    name = p.get("name") or p.get("name_en") or p.get("initials") or p.get("id", "")
    sub = p.get("name_en") if p.get("name") and p.get("name_en") else ""
    return name, sub


def conf_label(p: dict) -> str:
    c = p.get("conference", {}) or {}
    return c.get("short") or c.get("name") or ""


def is_live(p: dict) -> bool:
    """본인이 아직 공개에 동의하지 않은 제출은 명부에만 남기고 페이지를 만들지 않는다.

    people/<id>.json 에 "publish": false 를 두면 '준비 중' 카드로 남는다.
    다른 사람의 포스터를 대신 올려 두고 본인 확인을 기다릴 때 쓴다.
    """
    return p.get("publish", True) is not False


def ordered(cfg: dict) -> list[dict]:
    return sorted(cfg.get("participants", []),
                  key=lambda x: (x.get("order", 99), str(x.get("poster_no", ""))))


# ---------------------------------------------------------------- index
def build_index(cfg: dict, people: dict[str, dict], out: Path) -> None:
    site = cfg.get("site", {})
    title = site.get("title") or site.get("lab_short") or "Poster pages"
    lab = site.get("lab_name") or site.get("lab_short") or ""

    cards = []
    for part in ordered(cfg):
        pid = part["id"]
        p = people.get(pid)
        if p and not is_live(p):
            p = None
        pno = esc(part.get("poster_no") or "")
        name, sub = person_display(p or part)
        name_block = (f'<span class="card-name">{esc(name)}'
                      + (f'<span class="en">{esc(sub)}</span>' if sub else "") + "</span>")
        if not p:
            cards.append(
                '<div class="card pending" aria-disabled="true">'
                '<div class="thumb none">준비 중</div>'
                f'<div class="card-body"><div class="card-top"><span class="pno">{pno}</span>{name_block}</div>'
                '<p class="card-title">아직 정보가 등록되지 않았습니다.</p>'
                '<div class="card-foot"><span class="state">준비 중</span></div></div></div>'
            )
            continue
        poster = p.get("poster", {}) or {}
        thumb = poster.get("thumb") or poster.get("preview")
        thumb_html = (f'<div class="thumb"><img src="files/{esc(pid)}/{esc(thumb)}" alt="" loading="lazy"></div>'
                      if thumb else '<div class="thumb none">미리보기 없음</div>')
        foot = []
        if conf_label(p):
            foot.append(esc(conf_label(p)))
        when = fmt_date_range((p.get("conference", {}) or {}).get("date"),
                              (p.get("conference", {}) or {}).get("date_end"))
        if when:
            foot.append(esc(when))
        t = poster.get("title") or ""
        cards.append(
            f'<a class="card" href="p/{esc(pid)}.html">{thumb_html}'
            f'<div class="card-body"><div class="card-top"><span class="pno">{pno}</span>{name_block}</div>'
            + (f'<p class="card-title">{esc(t)}</p>' if t else "")
            + f'<div class="card-foot">{"".join(f"<span>{x}</span>" for x in foot)}</div></div></a>'
        )

    links = []
    if site.get("members_url"):
        links.append(btn("Lab members", site["members_url"], primary=True, external=True))
    if site.get("lab_home_url"):
        links.append(btn("연구실 홈", site["lab_home_url"], external=True))

    chips = []
    for c in sorted({conf_label(p) for p in people.values() if conf_label(p)}):
        chips.append(chip(c))
    w = cfg.get("window", {}) or {}
    if w.get("start") or w.get("end"):
        chips.append(chip(fmt_date_range(w.get("start"), w.get("end")), "게시"))

    ready, total = len(people), len(cfg.get("participants", []))
    html = f"""<!DOCTYPE html>
<html lang="{esc(site.get('locale', 'ko'))}">
<head>
  {head(title, f"{lab} 포스터 페이지", "assets/site.css", site.get("noindex", True),
        {"title": title, "desc": f"{lab} · 학회 포스터 {total}편"})}
</head>
<body>
<a class="skip" href="#main">본문으로 건너뛰기 / Skip to content</a>
<div class="banner" id="window-banner" hidden role="status"></div>

<header class="hero"><div class="wrap">
  <p class="eyebrow">{esc(lab)}</p>
  <h1>{esc(title)}</h1>
  {f'<p class="lede">{esc(site.get("lede"))}</p>' if site.get("lede") else ""}
  <ul class="chips">{"".join(chips)}</ul>
  <div class="actions">{"".join(links)}</div>
</div></header>

<main id="main"><div class="wrap">
  <section class="section">
    <h2>Posters · {ready} / {total}</h2>
    {'<div class="grid">' + "".join(cards) + '</div>' if cards
     else '<p class="empty-note">참가자가 아직 등록되지 않았습니다.</p>'}
  </section>
</div></main>

<footer class="foot"><div class="wrap">
  <p>{esc(lab)}</p>
  {f'<p>게시 기간 {esc(fmt_date_range(w.get("start"), w.get("end")))}</p>' if (w.get("start") or w.get("end")) else ""}
  <p>학회 기간 동안만 열어 두는 임시 페이지입니다. 자료의 저작권은 각 저자에게 있습니다.</p>
  {f'<p>{esc(site.get("contact_note"))}</p>' if site.get("contact_note") else ""}
</div></footer>

<script>window.__SITE__ = {json.dumps({"window": cfg.get("window", {})}, ensure_ascii=False)};</script>
<script src="assets/site.js"></script>
</body>
</html>
"""
    (out / "index.html").write_text(html, encoding="utf-8")


# ---------------------------------------------------------------- person
def build_person(cfg: dict, p: dict, out: Path, files_rel: str, nav: dict) -> None:
    site = cfg.get("site", {})
    pid = p["id"]
    name, sub = person_display(p)
    poster = p.get("poster", {}) or {}
    conf = p.get("conference", {}) or {}
    title = poster.get("title") or f"{name} 포스터"

    metas = []
    if conf.get("name") or conf.get("short"):
        metas.append(chip(conf.get("name") or conf.get("short")))
    when = fmt_date_range(conf.get("date"), conf.get("date_end"))
    if when:
        metas.append(chip(when))
    if p.get("poster_no"):
        metas.append(chip(p["poster_no"], "포스터"))
    if conf.get("session"):
        metas.append(chip(conf["session"]))
    if conf.get("venue") or conf.get("city"):
        metas.append(chip(conf.get("venue") or conf.get("city")))
    spec = size_chip(poster)
    if spec:
        metas.append(chip(spec))

    ratio, ratio_n = frame_vars(poster)
    fstyle = f"--poster-ratio: {ratio}; --poster-ar: {ratio_n}"
    pdf_rel = f"{files_rel}/{pid}/{poster['file']}" if poster.get("file") else ""
    prev_rel = f"{files_rel}/{pid}/{poster['preview']}" if poster.get("preview") else ""

    if prev_rel:
        frame = (f'<button class="poster-frame" style="{fstyle}" data-zoom="{esc(prev_rel)}" '
                 f'aria-label="포스터 크게 보기 / Enlarge poster">'
                 f'<img src="{esc(prev_rel)}" alt="{esc(title)} 포스터">'
                 f'<span class="zoom-hint">확대 +</span></button>')
    elif pdf_rel:
        frame = ('<div class="poster-frame empty"><p>미리보기 이미지가 없습니다.</p>'
                 '<p>아래 버튼으로 원본 파일을 열어 주세요.</p></div>')
    else:
        frame = '<div class="poster-frame empty"><p>포스터 파일이 아직 등록되지 않았습니다.</p></div>'

    pactions = []
    if pdf_rel:
        kind = "PDF" if poster["file"].lower().endswith(".pdf") else "원본"
        pactions.append(btn(f"포스터 {kind} 열기", pdf_rel, primary=True, external=True))
        pactions.append(btn("내려받기", pdf_rel, extra="download"))
    pmeta = []
    if poster.get("w_mm") and poster.get("h_mm"):
        pmeta.append(f'{poster["w_mm"]:.0f} × {poster["h_mm"]:.0f} mm')
    elif poster.get("w_px") and poster.get("h_px"):
        pmeta.append(f'{poster["w_px"]} × {poster["h_px"]} px')
    if poster.get("bytes"):
        pmeta.append(human_size(poster["bytes"]))

    sections = []
    if p.get("abstract"):
        sections.append('<section class="section"><h2>Abstract</h2>'
                        f'<div class="prose"><p>{esc(p["abstract"])}</p></div></section>')

    supp = [s for s in (p.get("supplementary") or []) if s.get("file")]
    if supp:
        items = []
        for s in supp:
            rel = f"{files_rel}/{pid}/{s['file']}"
            bits = [Path(s["file"]).suffix.lstrip(".").upper()]
            if s.get("bytes"):
                bits.append(human_size(s["bytes"]))
            items.append(
                '<li class="item"><div class="body">'
                f'<p class="name">{esc(s.get("title") or Path(s["file"]).name)}</p>'
                + (f'<p class="note">{esc(s.get("note"))}</p>' if s.get("note") else "")
                + f'<p class="meta">{esc(" · ".join(bits))}</p></div>'
                f'<span class="dl">{btn("열기", rel, external=True)}</span></li>'
            )
        sections.append('<section class="section"><h2>Supplementary</h2>'
                        '<ul class="list">' + "".join(items) + "</ul></section>")

    refs = [r for r in (p.get("references") or []) if (r.get("text") or r.get("doi") or r.get("url"))]
    if refs:
        items = []
        for r in refs:
            line = esc(r.get("text") or "")
            link = r.get("url") or (f"https://doi.org/{r['doi']}" if r.get("doi") else "")
            if link:
                items.append(f'<li>{line} <a href="{esc(link)}" target="_blank" rel="noopener">'
                             f'{esc(r.get("doi") or link)}</a></li>')
            else:
                items.append(f"<li>{line}</li>")
        sections.append('<section class="section"><h2>References</h2>'
                        '<ol class="refs">' + "".join(items) + "</ol></section>")

    contact = p.get("contact", {}) or {}
    cbtns = []
    email = contact.get("email") or {}
    if email.get("user") and email.get("domain"):
        cbtns.append(f'<a class="btn btn-primary" id="mail-{esc(pid)}" href="#" aria-disabled="true" '
                     f'data-eu="{esc(email["user"])}" data-ed="{esc(email["domain"])}">'
                     f'이메일 <span data-email-text></span></a>')
        cbtns.append(f'<button class="btn" type="button" data-copy="#mail-{esc(pid)}">주소 복사</button>')
    for key, label in (("linkedin", "LinkedIn"), ("scholar", "Google Scholar"),
                       ("site", "Personal site"), ("profile_url", "연구실 프로필")):
        if contact.get(key):
            cbtns.append(btn(label, contact[key], external=True))
    if cbtns:
        sections.append('<section class="section"><h2>Contact</h2>'
                        f'<div class="actions">{"".join(cbtns)}</div></section>')

    def step(target, label, aria):
        if not target:
            return f'<span class="step" aria-disabled="true" aria-label="{aria}">{label}</span>'
        return f'<a class="step" href="{esc(target)}.html" aria-label="{aria}">{label}</a>'

    html = f"""<!DOCTYPE html>
<html lang="{esc(site.get('locale', 'ko'))}">
<head>
  {head(f"{p.get('poster_no', '')} {name} · {title}".strip(), title, "../assets/site.css",
        site.get("noindex", True),
        {"title": title, "desc": f"{name} · {conf_label(p)}", "image": prev_rel})}
</head>
<body>
<a class="skip" href="#main">본문으로 건너뛰기 / Skip to content</a>
<div class="banner" id="window-banner" hidden role="status"></div>

<nav class="topbar"><div class="wrap">
  <a class="back" href="../index.html">← 목록</a>
  <span class="here">{esc(p.get('poster_no', ''))} · {esc(name)}</span>
  <span class="stepper">
    {step(nav.get('prev'), '‹', '이전 포스터 / Previous poster')}
    {step(nav.get('next'), '›', '다음 포스터 / Next poster')}
  </span>
</div></nav>

<main id="main"><div class="wrap">
  <header class="person-head">
    <p class="eyebrow">{esc(conf_label(p))}</p>
    <h1>{esc(title)}</h1>
    {f'<p class="title-en">{esc(poster.get("title_en"))}</p>' if poster.get("title_en") else ""}
    <p class="byline">{esc(p.get("authors") or name)}</p>
    {f'<p class="affil">{esc(p.get("affiliation"))}</p>' if p.get("affiliation") else ""}
    <ul class="metabar">{"".join(metas)}</ul>
  </header>

  <div class="poster-panel">
    {frame}
    <div class="poster-meta">{"".join(f"<span>{m}</span>" for m in pmeta)}</div>
    <div class="actions">{"".join(pactions)}</div>
  </div>

  {"".join(sections)}
</div></main>

<footer class="foot"><div class="wrap">
  <p>{esc(site.get('lab_name') or site.get('lab_short') or '')}</p>
  <p>학회 기간 동안만 열어 두는 임시 페이지입니다. 포스터와 부속 자료의 저작권은 저자에게 있습니다.</p>
</div></footer>

<div class="lightbox" id="lightbox" role="dialog" aria-modal="true" aria-label="포스터 확대 보기">
  <div class="lb-bar">
    <button class="lb-btn" type="button" data-lb="scale">100%</button>
    <button class="lb-btn" type="button" data-lb="close">닫기 ✕</button>
  </div>
  <div class="stage"><img alt="{esc(title)} 포스터 확대"></div>
</div>

<script>window.__SITE__ = {json.dumps({"window": cfg.get("window", {})}, ensure_ascii=False)};</script>
<script src="../assets/site.js"></script>
</body>
</html>
"""
    (out / "p").mkdir(parents=True, exist_ok=True)
    (out / "p" / f"{pid}.html").write_text(html, encoding="utf-8")


# ---------------------------------------------------------------- 자산
def _thumb(src: Path, dst: Path, long_edge: int = 720) -> bool:
    if shutil.which("sips"):
        r = subprocess.run(["sips", "-s", "format", "jpeg", "-Z", str(long_edge),
                            str(src), "--out", str(dst)], capture_output=True)
        if r.returncode == 0 and dst.exists():
            return True
    for m in ("magick", "convert"):
        if shutil.which(m):
            r = subprocess.run([m, str(src), "-resize", f"{long_edge}x{long_edge}",
                                "-quality", "80", str(dst)], capture_output=True)
            if r.returncode == 0 and dst.exists():
                return True
    return False


def stage_assets(pth: dict, p: dict, dist: Path, do_preview: bool, long_edge: int) -> list[str]:
    """assets/<id>/ 를 dist/files/<id>/ 로 옮기고, 없으면 미리보기와 썸네일을 만든다."""
    notes = []
    pid = p["id"]
    src, dst = pth["assets"] / pid, dist / "files" / pid
    if not src.exists():
        return [f"{pid}: assets/{pid}/ 없음 — 파일 링크가 비어 있게 된다"]
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_dir() or item.name.startswith("."):
            continue
        target = dst / item.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)

    poster = p.get("poster", {}) or {}
    if poster.get("file"):
        f = dst / poster["file"]
        if f.exists():
            poster["bytes"] = f.stat().st_size
            info = poster_geometry(f)
            if info:
                poster["kind"] = info["kind"]
                for k in ("w_mm", "h_mm", "w_px", "h_px"):
                    if info.get(k):
                        poster[k] = info[k]
                poster.setdefault("size_label", info["size_label"] or "")
                if poster.get("orientation") and poster["orientation"] != info["orientation"]:
                    notes.append(f"{pid}: 등록된 방향({poster['orientation']})과 실측"
                                 f"({info['orientation']})이 다르다 — 파일을 따랐다")
                poster["orientation"] = info["orientation"]
            prev = poster.get("preview")
            if do_preview and (not prev or not (dst / prev).exists()):
                out_jpg = dst / "preview.jpg"
                tool = make_preview(f, out_jpg, long_edge)
                if tool:
                    made = out_jpg if out_jpg.exists() else next(
                        (q for q in dst.glob("preview.*") if q.suffix != ".pdf"), out_jpg)
                    poster["preview"] = made.name
                    notes.append(f"{pid}: 미리보기 생성 ({tool})")
                else:
                    notes.append(f"{pid}: 미리보기 도구가 없다 (pdftoppm / magick / sips / qlmanage). "
                                 "PDF 버튼만 나온다 — brew install poppler 로 해결된다")
            if poster.get("preview"):
                th = dst / "thumb.jpg"
                if _thumb(dst / poster["preview"], th):
                    poster["thumb"] = th.name
                else:
                    poster["thumb"] = poster["preview"]
        else:
            notes.append(f"{pid}: {poster['file']} 이 assets/{pid}/ 에 없다")

    for s in p.get("supplementary") or []:
        if s.get("file"):
            f = dst / s["file"]
            if f.exists():
                s["bytes"] = f.stat().st_size
            else:
                notes.append(f"{pid}: supplementary {s['file']} 이 없다")
    return notes


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="poster-site 정적 사이트 빌드")
    ap.add_argument("--root", default=None, help="poster-site 작업 디렉터리 (기본: ./poster-site)")
    ap.add_argument("--no-preview", action="store_true", help="포스터 미리보기 이미지를 만들지 않는다")
    ap.add_argument("--long-edge", type=int, default=1800, help="미리보기 긴 변 픽셀 (기본 1800)")
    a = ap.parse_args()

    pth = paths(a.root)
    cfg = load_config(a.root)
    people = {p["id"]: p for p in load_people(a.root)}
    dist = pth["dist"]
    if dist.exists():
        shutil.rmtree(dist)
    (dist / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TPL / "site.css", dist / "assets" / "site.css")
    shutil.copy2(TPL / "site.js", dist / "assets" / "site.js")
    (dist / ".nojekyll").write_text("", encoding="utf-8")

    live = {k: v for k, v in people.items() if is_live(v)}
    held = [k for k in people if k not in live]
    seq = [x["id"] for x in ordered(cfg) if x["id"] in live]
    notes = []
    for i, pid in enumerate(seq):
        p = people[pid]
        notes += stage_assets(pth, p, dist, not a.no_preview, a.long_edge)
        build_person(cfg, p, dist, "../files",
                     {"prev": seq[i - 1] if i > 0 else None,
                      "next": seq[i + 1] if i + 1 < len(seq) else None})
    for pid, p in live.items():            # 명부에 없는 제출자도 페이지는 만든다
        if pid not in seq:
            notes += stage_assets(pth, p, dist, not a.no_preview, a.long_edge)
            build_person(cfg, p, dist, "../files", {})

    build_index(cfg, live, dist)

    state, days = window_state(cfg)
    total = len(cfg.get("participants", []))
    print(f"빌드 완료 → {dist}")
    print(f"  참가자 {len(live)} / {total} 공개" + (f" (보류 {len(held)}명: {', '.join(held)})" if held else ""))
    label = {"before": "게시 전", "open": "게시 중", "closed": "게시 종료", "unset": "게시기간 미설정"}[state]
    print(f"  게시 상태: {label}" + (f" (D-{days})" if state == "open" and days is not None else ""))
    for n in notes:
        print(f"  · {n}")
    missing = [x["id"] for x in cfg.get("participants", []) if x["id"] not in live]
    if missing:
        print(f"  · 정보 미제출: {', '.join(missing)} — '준비 중' 카드로 남겨 뒀다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
