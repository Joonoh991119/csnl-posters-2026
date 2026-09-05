#!/usr/bin/env python3
"""서플 HTML 문서를 사이트 지면에 얹을 수 있는 조각으로 바꾼다.

원본은 대개 MATLAB·노트북·에디터가 뱉은 자립형 HTML 이다. 그대로 올리면 사이트와
따로 노는 페이지가 하나 생기고, base64 로 박힌 그림 때문에 학회장 모바일에서 몇 MB 를 받는다.
그래서 셋을 한다 — 본문만 꺼내고, 그림을 파일로 빼고, 죽은 링크를 정리한다.

  from supplement import render
  html, notes = render(src_text, img_dir=Path(...), img_rel="../files/jop/supp")
"""
from __future__ import annotations

import base64
import difflib
import re
import unicodedata
from pathlib import Path

DROP_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.S | re.I)
DROP_VOID = re.compile(r"<(link|meta|base)\b[^>]*>", re.I)
DROP_ON = re.compile(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
BODY = re.compile(r"<body[^>]*>(.*)</body>", re.S | re.I)
DATA_IMG = re.compile(r'src="data:image/(png|jpe?g|gif|webp);base64,([^"]+)"', re.I)
HEADING = re.compile(r"<(h[1-6])([^>]*)>(.*?)</\1>", re.S | re.I)
ANCHOR = re.compile(r'<a\b([^>]*?)href="([^"]+)"([^>]*)>(.*?)</a>', re.S | re.I)
TAGS = re.compile(r"<[^>]+>")


def slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", TAGS.sub(" ", text)).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t or "section"


MEDIA = re.compile(r"<(video|audio)\b([^>]*)>(.*?)</\1\s*>", re.S | re.I)
SRC_ATTR = re.compile(r'src="([^"]+)"', re.I)
LOCAL_IMG = re.compile(r'<img\b([^>]*?)src="(?!data:|https?:|//)([^"]+)"([^>]*)>', re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", TAGS.sub("", s)).strip(" .·—-").lower()


def _bare(s: str) -> str:
    """비교용 — 숫자와 문장부호를 뺀다. 소속 표시 1, † 같은 것 때문에 같은 줄이 달라 보인다."""
    return re.sub(r"[^a-z\u00c0-\u024f]+", "", _norm(s))


def _same(a: str, b: str) -> bool:
    if a == b:
        return True
    ba, bb = _bare(a), _bare(b)
    if ba and bb and (ba == bb or difflib.SequenceMatcher(None, ba, bb).ratio() >= 0.88):
        return True
    return False


def strip_front_matter(body: str, dupes: list[str]) -> tuple[str, int]:
    """문서 맨 앞의 제목 블록을 걷어낸다.

    사이트 지면이 이미 제목·저자·소속을 머리에 달아 준다. 원본이 같은 것을 한 번 더
    적어 두면 페이지가 두 번 시작한다. 첫 h1 과, 그 뒤에서 우리가 이미 아는 값과
    글자까지 같은 문단만 지운다 — 모르는 문장은 건드리지 않는다.
    """
    dupes = [_norm(d) for d in dupes]
    head_end = min([x for x in (body.find("<h2"), body.find("<hr"), body.find('<div class="toc"'))
                    if x != -1] or [len(body)])
    head, rest = body[:head_end], body[head_end:]
    removed = 0
    new_head, pos = [], 0
    for m in re.finditer(r"<(h1|p)\b[^>]*>.*?</\1\s*>", head, re.S | re.I):
        chunk = m.group(0)
        text = _norm(chunk)
        drop = m.group(1).lower() == "h1" or any(_same(text, d) for d in dupes)
        new_head.append(head[pos:m.start()])
        if drop:
            removed += 1
        else:
            new_head.append(chunk)
        pos = m.end()
    new_head.append(head[pos:])
    return "".join(new_head) + rest, removed


def render(src: str, img_dir: Path, img_rel: str, asset_dir: Path | None = None,
           dupes: list[str] | None = None) -> tuple[str, list[str]]:
    """(본문 HTML, 사람이 읽을 메모) 를 돌려준다.

    asset_dir 은 원본 HTML 이 있던 폴더다. 거기 실제로 있는 파일만 사이트로 옮기고,
    없는 것은 깨진 플레이어나 X 표시 대신 한 줄 설명으로 바꾼다.
    """
    notes: list[str] = []
    m = BODY.search(src)
    body = m.group(1) if m else src
    body = DROP_BLOCK.sub("", body)
    body = DROP_VOID.sub("", body)
    body = DROP_ON.sub("", body)

    if dupes:
        body, cut = strip_front_matter(body, [d for d in dupes if d])
        if cut:
            notes.append(f"문서 앞머리에서 제목 블록 {cut}줄을 걷어냈다 — 페이지 머리가 이미 같은 것을 말한다")

    # ---- 그림을 파일로 빼낸다 ----
    img_dir.mkdir(parents=True, exist_ok=True)
    saved: dict[str, str] = {}
    count = 0

    def take(mm):
        nonlocal count
        count += 1
        ext = "jpg" if mm.group(1).lower().startswith("jpe") else mm.group(1).lower()
        raw = base64.b64decode(mm.group(2))
        name = f"figure-{count:02d}.{ext}"
        (img_dir / name).write_bytes(raw)
        saved[str(count)] = name
        return f'src="{img_rel}/{name}" loading="lazy"'

    body = DATA_IMG.sub(take, body)
    if count:
        total = sum((img_dir / n).stat().st_size for n in saved.values())
        notes.append(f"그림 {count}개를 파일로 빼냈다 ({total / 1e6:.1f} MB) — "
                     "본문에 base64 로 박혀 있으면 모바일에서 그만큼을 한 번에 받는다")

    # ---- 제목에 id 를 새로 붙인다 ----
    ids: list[str] = []

    def head(mm):
        tag, attrs, inner = mm.group(1), mm.group(2), mm.group(3)
        sid = slug(inner)
        base, n = sid, 2
        while sid in ids:
            sid, n = f"{base}-{n}", n + 1
        ids.append(sid)
        attrs = re.sub(r'\sid="[^"]*"', "", attrs)
        return f'<{tag}{attrs} id="{sid}">{inner}</{tag}>'

    body = HEADING.sub(head, body)

    # ---- 링크 정리 ----
    dead_anchor, dead_file, fixed = [], [], 0
    figure_names = list(saved.values())

    def link(mm):
        nonlocal fixed
        pre, href, post, text = mm.group(1), mm.group(2), mm.group(3), mm.group(4)
        if href.startswith("#"):
            target = href[1:]
            if target in ids:
                return mm.group(0)
            first = "-".join(target.split("-")[:2])          # figure-s1, table-s1 …
            hit = next((i for i in ids if i.startswith(first)), None)
            if not hit:
                close = difflib.get_close_matches(target, ids, n=1, cutoff=0.55)
                hit = close[0] if close else None
            if hit:
                fixed += 1
                return f'<a{pre}href="#{hit}"{post}>{text}</a>'
            dead_anchor.append(target)
            return f"<span>{text}</span>"
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", href) or href.startswith("//"):
            return mm.group(0)                               # 외부 링크는 그대로
        stem = Path(href).stem.lower()
        for name in figure_names:                            # figures/FigureS4_x.png → 빼낸 파일
            if stem in name.lower() or name.split(".")[0] in stem:
                return f'<a{pre}href="{img_rel}/{name}"{post}>{text}</a>'
        idx = re.search(r"figures?/[^/]*?s(\d+)", href, re.I)
        if idx and saved.get(idx.group(1)):
            return f'<a{pre}href="{img_rel}/{saved[idx.group(1)]}"{post}>{text}</a>'
        dead_file.append(href)
        return f"<span>{text}</span>"                        # 없는 파일로 보내지 않는다

    # ---- 비디오·오디오: 파일이 있으면 옮기고, 없으면 설명으로 바꾼다 ----
    missing_media: list[str] = []
    moved_media = 0

    def media(mm):
        nonlocal moved_media
        tag, attrs, inner = mm.group(1), mm.group(2), mm.group(3)
        srcs = SRC_ATTR.findall(attrs) + SRC_ATTR.findall(inner)
        local = [s for s in srcs if not re.match(r"^(data:|https?:|//)", s)]
        if not local:
            return mm.group(0)
        keep = []
        for s in local:
            f = (asset_dir / s) if asset_dir else None
            if f and f.is_file():
                dst = img_dir / Path(s).name
                dst.write_bytes(f.read_bytes())
                keep.append((s, f"{img_rel}/{Path(s).name}"))
                moved_media += 1
            else:
                missing_media.append(s)
        if not keep:
            return ('<p class="missing">이 온라인 사본에는 포함되지 않았습니다.</p>'
                    if False else
                    '<p class="missing">Not included in this online copy.</p>')
        out = mm.group(0)
        for old, new in keep:
            out = out.replace(f'src="{old}"', f'src="{new}"')
        return out

    body = MEDIA.sub(media, body)
    if moved_media:
        notes.append(f"미디어 {moved_media}개를 사이트로 옮겼다")
    if missing_media:
        uniq = sorted(set(missing_media))
        notes.append(f"파일이 없어 플레이어를 뺀 미디어 {len(uniq)}건: " + ", ".join(uniq[:4])
                     + (" …" if len(uniq) > 4 else "")
                     + " — assets 에 넣고 다시 빌드하면 그대로 살아난다")

    # ---- 일반 <img> 상대경로도 실제 파일이면 옮긴다 ----
    def local_img(mm):
        pre, href, post = mm.group(1), mm.group(2), mm.group(3)
        f = (asset_dir / href) if asset_dir else None
        if f and f.is_file():
            dst = img_dir / Path(href).name
            dst.write_bytes(f.read_bytes())
            return f'<img{pre}src="{img_rel}/{Path(href).name}"{post}>'
        return f'<img{pre}src="{img_rel}/{Path(href).name}"{post}>' if False else mm.group(0)

    body = LOCAL_IMG.sub(local_img, body)

    body = ANCHOR.sub(link, body)

    # 넓은 표는 좁은 화면에서 지면을 밀어낸다 — 표만 따로 가로 스크롤시킨다
    wrapped = re.sub(r"(<table\b.*?</table\s*>)", r'<div class="table-wrap">\1</div>', body,
                     flags=re.S | re.I)
    if wrapped != body:
        body = wrapped
    if fixed:
        notes.append(f"본문 안 목차 링크 {fixed}개가 지금 제목과 어긋나 있어 다시 이었다")
    if dead_anchor:
        notes.append("가리키는 제목이 없어 링크를 뗀 앵커: " + ", ".join(sorted(set(dead_anchor))))
    if dead_file:
        uniq = sorted(set(dead_file))
        notes.append(f"파일이 없어 링크를 뗀 것 {len(uniq)}건: " + ", ".join(uniq[:6])
                     + (" …" if len(uniq) > 6 else ""))
    return body.strip(), notes
