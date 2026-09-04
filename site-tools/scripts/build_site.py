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
    esc, fmt_date_en, fmt_date_range, frame_vars, human_size, load_config, load_people,
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


HOME_ICON = ('<svg class="ico" viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" '
             'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
             'stroke-linejoin="round"><path d="M2 6.6 8 2l6 4.6"/>'
             '<path d="M3.4 7.6V13a.6.6 0 0 0 .6.6h8a.6.6 0 0 0 .6-.6V7.6"/>'
             '<path d="M6.4 13.6V9.4h3.2v4.2"/></svg>')


def authors_html(p: dict) -> str:
    """저자 전원을 적고, 발표자만 굵게. 저널이 발표 저자를 표시하는 방식 그대로다.

    authors 가 비어 있으면 그 사람 이름만 남는다 — 없는 저자를 지어내지 않는다.
    """
    line = (p.get("authors") or "").strip()
    if not line:
        return esc(p.get("name_en") or p.get("name") or "")
    who = (p.get("name_en") or "").strip()
    out = []
    for token in [x.strip() for x in line.split(",")]:
        if not token:
            continue
        if who and token.casefold() == who.casefold():
            out.append(f"<b>{esc(token)}</b>")
        else:
            out.append(esc(token))
    return ", ".join(out)


def qr_block(pid: str, url: str, rel: str, has: bool) -> str:
    """발표자가 자기 QR 을 가져가는 자리. 복사·내려받기 둘 다 둔다.

    make_qr.py 가 아직 안 돌았으면 아무것도 그리지 않는다 — 빈 상자를 남기지 않는다.
    """
    if not has:
        return ""
    return (
        '<section class="section"><h2>QR</h2><div class="qr-block">'
        f'<img class="qr" src="{rel}/{esc(pid)}.svg" width="132" height="132" '
        f'alt="QR code linking to this page">'
        '<div class="qr-side">'
        '<p class="note">Scan to open this page on a phone, or take the code for '
        'your poster, slides or handout.</p>'
        '<div class="actions">'
        f'<button class="btn btn-primary" type="button" data-qr-copy="{rel}/{esc(pid)}.png">'
        'Copy image</button>'
        f'<a class="btn" href="{rel}/{esc(pid)}.svg" download>SVG (print)</a>'
        f'<a class="btn" href="{rel}/{esc(pid)}.png" download>PNG</a>'
        '</div>'
        f'<p class="url">{esc(url)}</p>'
        '</div></div></section>'
    )


def fact(text: str, label: str = "") -> str:
    """dateline 한 조각. 라벨은 저널 표기처럼 굵은 소형 텍스트로 앞에 붙는다."""
    return (f"<span>{f'<b>{esc(label)}</b> ' if label else ''}{esc(text)}</span>")


def joined(parts: list[str]) -> str:
    sep = '<span class="sep" aria-hidden="true">·</span>'
    return sep.join(parts)


def person_display(p: dict) -> tuple[str, str]:
    """(주 표기, 보조 표기). 사이트 언어가 영어라 영문 이름이 앞에 온다.

    영문 이름이 없으면 한글 이름이 주 표기가 된다 — 없는 것을 지어내지 않는다.
    """
    en, ko = p.get("name_en"), p.get("name")
    main = en or ko or p.get("initials") or p.get("id", "")
    sub = ko if (en and ko) else ""
    return main, sub


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
def build_index(cfg: dict, people: dict[str, dict], out: Path, has_index_qr: bool = False) -> None:
    site = cfg.get("site", {})
    title = site.get("title") or site.get("lab_short") or "Posters"
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
                      + (f' <span class="en">{esc(sub)}</span>' if sub else "") + "</span>")
        if not p:
            cards.append(
                '<div class="card pending" aria-disabled="true">'
                '<div class="thumb none">Pending</div>'
                f'<div class="card-body"><div class="card-top"><span class="pno">{pno}</span>{name_block}</div>'
                '<p class="card-title">Not submitted yet.</p></div></div>'
            )
            continue
        poster = p.get("poster", {}) or {}
        thumb = poster.get("thumb") or poster.get("preview")
        thumb_html = (f'<div class="thumb"><img src="files/{esc(pid)}/{esc(thumb)}" alt="" loading="lazy"></div>'
                      if thumb else '<div class="thumb none">No preview</div>')
        foot = []
        if conf_label(p):
            foot.append(esc(conf_label(p)))
        when = fmt_date_en((p.get("conference", {}) or {}).get("date"),
                           (p.get("conference", {}) or {}).get("date_end"))
        if when:
            foot.append(esc(when))
        ttl = poster.get("title") or ""
        cards.append(
            f'<a class="card" href="p/{esc(pid)}.html">{thumb_html}'
            # 발표자 이름은 아래 저자 줄이 담당한다 — 상단은 번호만 둔다
            f'<div class="card-body"><div class="card-top"><span class="pno">{pno}</span></div>'
            + (f'<p class="card-title">{esc(ttl)}</p>' if ttl else "")
            + f'<p class="card-authors">{authors_html(p)}</p>'
            + f'<div class="card-foot">{"".join(f"<span>{x}</span>" for x in foot)}</div></div></a>'
        )

    home = site.get("lab_home_url") or site.get("members_url") or ""
    links = []
    if home:
        links.append(
            f'<a class="btn btn-primary" href="{esc(home)}" target="_blank" rel="noopener">'
            f'{HOME_ICON}Lab homepage <span class="ext" aria-hidden="true">↗</span></a>'
        )

    facts = []
    confs = sorted({conf_label(p) for p in people.values() if conf_label(p)})
    if confs:
        facts.append(fact(", ".join(confs), "Meetings"))
    w = cfg.get("window", {}) or {}
    if w.get("start") or w.get("end"):
        facts.append(fact(fmt_date_en(w.get("start"), w.get("end")), "Online"))
    roster_ids = {x["id"] for x in cfg.get("participants", [])}
    extras = [p for pid, p in people.items() if pid not in roster_ids]
    for p in sorted(extras, key=lambda x: str(x.get("poster_no", ""))):
        pid = p["id"]
        poster = p.get("poster", {}) or {}
        thumb = poster.get("thumb") or poster.get("preview")
        thumb_html = (f'<div class="thumb"><img src="files/{esc(pid)}/{esc(thumb)}" alt="" loading="lazy"></div>'
                      if thumb else '<div class="thumb none">No preview</div>')
        foot = [x for x in (esc(conf_label(p)),
                            esc(fmt_date_en((p.get("conference", {}) or {}).get("date"),
                                            (p.get("conference", {}) or {}).get("date_end")))) if x]
        cards.append(
            f'<a class="card" href="p/{esc(pid)}.html">{thumb_html}'
            f'<div class="card-body"><div class="card-top">'
            f'<span class="pno">{esc(p.get("poster_no") or "")}</span></div>'
            + (f'<p class="card-title">{esc(poster.get("title") or "")}</p>' if poster.get("title") else "")
            + f'<p class="card-authors">{authors_html(p)}</p>'
            + f'<div class="card-foot">{"".join(f"<span>{x}</span>" for x in foot)}</div></div></a>'
        )

    shown = sum(1 for x in cfg.get("participants", []) if x["id"] in people) + len(extras)
    ready, total = shown, len(cfg.get("participants", [])) + len(extras)
    facts.append(fact(f"{ready} of {total} posted", "Posters"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  {head(title, f"{lab} — conference posters", "assets/site.css", site.get("noindex", True),
        {"title": title, "desc": f"{lab} — {total} conference posters"})}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<div class="banner" id="window-banner" hidden role="status"></div>

<header class="masthead"><div class="wrap">
  <p class="imprint">{esc(lab)}</p>
  <h1>{esc(title)}</h1>
  {f'<p class="lede">{esc(site.get("lede"))}</p>' if site.get("lede") else ""}
  <ul class="rule-list">{"".join(f"<li>{f}</li>" for f in facts)}</ul>
  <div class="actions">{"".join(links)}</div>
</div></header>

<main id="main"><div class="wrap">
  <section class="section">
    <h2>Posters</h2>
    {'<div class="grid">' + "".join(cards) + '</div>' if cards
     else '<p class="empty-note">No participants registered yet.</p>'}
  </section>
  {qr_block("index", (cfg.get("deploy", {}) or {}).get("url", "") or "", "qr", has_index_qr)}
</div></main>

<footer class="foot"><div class="wrap">
  <p>{esc(lab)}</p>
  {f'<p>Online {esc(fmt_date_en(w.get("start"), w.get("end")))}.</p>' if (w.get("start") or w.get("end")) else ""}
  <p>A temporary page kept open for the duration of the meeting.
     Copyright in each poster and its supplementary material remains with its authors.</p>
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
    title = poster.get("title") or f"Poster — {name}"

    # dateline: 학회 · 날짜 · 세션 · 장소 — 표가 아니라 한 줄로. 저널의 발행 정보 줄과 같다.
    line = []
    if conf.get("name") or conf.get("short"):
        line.append(fact(conf.get("name") or conf.get("short")))
    when = fmt_date_en(conf.get("date"), conf.get("date_end"))
    if when:
        line.append(fact(when))
    if conf.get("session"):
        line.append(fact(conf["session"]))
    if conf.get("venue") or conf.get("city"):
        line.append(fact(conf.get("venue") or conf.get("city")))

    ratio, ratio_n = frame_vars(poster)
    fstyle = f"--poster-ratio: {ratio}; --poster-ar: {ratio_n}"
    file_rel = f"{files_rel}/{pid}/{poster['file']}" if poster.get("file") else ""
    prev_rel = f"{files_rel}/{pid}/{poster['preview']}" if poster.get("preview") else ""

    if prev_rel:
        plate = (f'<button class="plate" style="{fstyle}" data-zoom="{esc(prev_rel)}" '
                 f'aria-label="Enlarge poster">'
                 f'<img src="{esc(prev_rel)}" alt="Poster: {esc(title)}">'
                 f'<span class="zoom">Zoom</span></button>')
    elif file_rel:
        plate = ('<div class="plate empty"><p>No preview image was generated.</p>'
                 '<p>Open the original file below.</p></div>')
    else:
        plate = '<div class="plate empty"><p>The poster file has not been uploaded yet.</p></div>'

    pactions = []
    if file_rel:
        kind = "PDF" if poster["file"].lower().endswith(".pdf") else "image"
        pactions.append(btn(f"Open original ({kind})", file_rel, primary=True, external=True))
        pactions.append(btn("Download", file_rel, extra="download"))

    sections = []
    if p.get("abstract"):
        sections.append('<section class="section"><h2>Abstract</h2>'
                        f'<p class="abstract">{esc(p["abstract"])}</p></section>')

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
                f'<span class="dl">{btn("Open", rel, external=True)}</span></li>'
            )
        sections.append('<section class="section"><h2>Supplementary</h2>'
                        '<ul class="list">' + "".join(items) + "</ul></section>")

    refs = [r for r in (p.get("references") or []) if (r.get("text") or r.get("doi") or r.get("url"))]
    if refs:
        items = []
        for r in refs:
            body = esc(r.get("text") or "")
            link = r.get("url") or (f"https://doi.org/{r['doi']}" if r.get("doi") else "")
            if link:
                body += f' <a href="{esc(link)}" target="_blank" rel="noopener">{esc(r.get("doi") or link)}</a>'
            items.append(f"<li>{body}</li>")
        sections.append('<section class="section"><h2>References</h2>'
                        '<ol class="refs">' + "".join(items) + "</ol></section>")

    contact = p.get("contact", {}) or {}
    cbtns = []
    email = contact.get("email") or {}
    if email.get("user") and email.get("domain"):
        cbtns.append(f'<a class="btn btn-primary" id="mail-{esc(pid)}" href="#" aria-disabled="true" '
                     f'data-eu="{esc(email["user"])}" data-ed="{esc(email["domain"])}">'
                     f'Email <span data-email-text></span></a>')
        cbtns.append(f'<button class="btn" type="button" data-copy="#mail-{esc(pid)}">Copy address</button>')
    for key, label in (("linkedin", "LinkedIn"), ("scholar", "Google Scholar"),
                       ("site", "Personal site"), ("profile_url", "Lab profile")):
        if contact.get(key):
            cbtns.append(btn(label, contact[key], external=True))
    if cbtns:
        sections.append('<section class="section"><h2>Contact</h2>'
                        f'<div class="actions">{"".join(cbtns)}</div></section>')

    base = (cfg.get("deploy", {}) or {}).get("url", "").rstrip("/")
    sections.append(qr_block(pid, f"{base}/p/{pid}.html" if base else f"p/{pid}.html",
                             "../qr", bool(nav.get("qr"))))

    def step(target, label, aria):
        if not target:
            return f'<span class="step" aria-disabled="true" aria-label="{aria}">{label}</span>'
        return f'<a class="step" href="{esc(target)}.html" aria-label="{aria}">{label}</a>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  {head(f"{p.get('poster_no', '')} {name} — {title}".strip(), title, "../assets/site.css",
        site.get("noindex", True),
        {"title": title, "desc": f"{name} — {conf_label(p)}", "image": prev_rel})}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<div class="banner" id="window-banner" hidden role="status"></div>

<nav class="topbar"><div class="wrap">
  <a class="back" href="../index.html">← All posters</a>
  <span class="here">{esc(p.get('poster_no', ''))} · {esc(name)}</span>
  <span class="stepper">
    {step(nav.get('prev'), '‹', 'Previous poster')}
    {step(nav.get('next'), '›', 'Next poster')}
  </span>
</div></nav>

<main id="main">
  <article class="article"><div class="wrap">
    <p class="eyebrow">{esc(p.get('poster_no', ''))}{' · ' if p.get('poster_no') and conf_label(p) else ''}{esc(conf_label(p))}</p>
    <h1>{esc(title)}</h1>
    {f'<p class="subtitle">{esc(poster.get("title_en"))}</p>' if poster.get("title_en") else ""}
    <p class="byline">{authors_html(p)}</p>
    {f'<p class="affil">{esc(p.get("affiliation"))}</p>' if p.get("affiliation") else ""}
    {f'<p class="dateline">{joined(line)}</p>' if line else ""}

    <div class="figure">
      {plate}
      <div class="actions">{"".join(pactions)}</div>
    </div>
  </div></article>

  <div class="wrap">{"".join(sections)}</div>
</main>

<footer class="foot"><div class="wrap">
  <p>{esc(site.get('lab_name') or site.get('lab_short') or '')}</p>
  <p>A temporary page kept open for the duration of the meeting.
     Copyright in the poster and its supplementary material remains with its authors.</p>
</div></footer>

<div class="lightbox" id="lightbox" role="dialog" aria-modal="true" aria-label="Poster, enlarged">
  <div class="lb-bar">
    <button class="lb-btn" type="button" data-lb="scale">100%</button>
    <button class="lb-btn" type="button" data-lb="close">Close ✕</button>
  </div>
  <div class="stage"><img alt="Poster: {esc(title)}"></div>
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
        # GitHub 웹 UI 로 올리면 폴더를 못 만들어 파일이 assets/ 바로 밑에 떨어진다.
        # 그때 조용히 빈 페이지를 내지 않고 주워 와서 제자리에 놓는다.
        loose = []
        for key in [(p.get("poster", {}) or {}).get("file")] + \
                   [s.get("file") for s in (p.get("supplementary") or [])]:
            if key and (pth["assets"] / Path(key).name).is_file():
                loose.append(pth["assets"] / Path(key).name)
        if loose:
            src.mkdir(parents=True, exist_ok=True)
            for f in loose:
                shutil.move(str(f), str(src / f.name))
            notes.append(f"{pid}: assets/ 바로 밑에 있던 파일 {len(loose)}개를 assets/{pid}/ 로 옮겼다 "
                         "(웹 UI 업로드는 폴더를 못 만든다)")
        else:
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
                    if tool == "copy":
                        notes.append(f"{pid}: 축소 도구가 없어 원본을 그대로 미리보기로 썼다 "
                                     f"({human_size(made.stat().st_size)}) — 학회장 모바일에서 무겁다. "
                                     "imagemagick 또는 sips 가 필요하다")
                    else:
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
                    if (dst / poster["preview"]).stat().st_size > 400_000:
                        notes.append(f"{pid}: 썸네일을 못 만들어 목록 카드가 "
                                     f"{human_size((dst / poster['preview']).stat().st_size)} 이미지를 "
                                     "그대로 불러온다 — imagemagick 을 깔면 해결된다")
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
    qr_src = pth["root"] / "qr"
    qr_have: set[str] = set()
    if qr_src.is_dir():
        (dist / "qr").mkdir(parents=True, exist_ok=True)
        for f in qr_src.iterdir():
            if f.suffix.lower() in (".svg", ".png") and f.is_file():
                shutil.copy2(f, dist / "qr" / f.name)
                qr_have.add(f.stem)

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
                      "next": seq[i + 1] if i + 1 < len(seq) else None,
                      "qr": pid in qr_have})
    for pid, p in live.items():            # 명부에 없는 제출자도 페이지는 만든다
        if pid not in seq:
            notes += stage_assets(pth, p, dist, not a.no_preview, a.long_edge)
            build_person(cfg, p, dist, "../files", {"qr": pid in qr_have})

    build_index(cfg, live, dist, "index" in qr_have)

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
