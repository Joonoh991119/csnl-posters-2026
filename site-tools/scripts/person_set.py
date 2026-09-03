#!/usr/bin/env python3
"""참가자 한 명의 정보를 기록한다 — 인터뷰 결과 JSON → people/<id>.json + 자산 복사.

  python3 scripts/person_set.py --payload /tmp/jop.json [--root ./poster-site] [--allow-new]

없는 항목은 그냥 빼면 된다. 링크드인이 없거나 서플이 없거나 레퍼런스가 없는 사람은
그 섹션 없이 페이지가 그려진다 — 빈 제목만 남는 자리는 만들지 않는다.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitelib import (  # noqa: E402
    load_config, parse_date, paths, poster_geometry, read_json, slug, write_json,
)

EMAIL_RE = re.compile(r"^([^@\s]+)@([^@\s]+\.[^@\s]+)$")


def norm_email(value):
    if not value:
        return None
    if isinstance(value, dict):
        u, d = value.get("user"), value.get("domain")
        return {"user": u, "domain": d} if u and d else None
    m = EMAIL_RE.match(str(value).strip())
    if not m:
        raise SystemExit(f"이메일 형식이 아니다: {value}")
    return {"user": m.group(1), "domain": m.group(2)}


def norm_url(value, label):
    if not value:
        return ""
    v = str(value).strip()
    if not v.startswith(("http://", "https://")):
        v = "https://" + v
    if label == "linkedin" and "linkedin.com" not in v:
        print(f"  경고: LinkedIn URL 로 보이지 않는다 — {v}")
    return v


def copy_asset(src: Path, dst_dir: Path, name: str) -> str:
    src = Path(src).expanduser()
    if not src.exists():
        raise SystemExit(f"파일이 없다: {src}")
    dst_dir.mkdir(parents=True, exist_ok=True)
    target = dst_dir / f"{name}{src.suffix.lower()}"
    shutil.copy2(src, target)
    return target.name


def main() -> int:
    ap = argparse.ArgumentParser(description="참가자 정보 기록")
    ap.add_argument("--payload", required=True)
    ap.add_argument("--root", default=None)
    ap.add_argument("--allow-new", action="store_true", help="명부에 없는 사람도 추가한다")
    a = ap.parse_args()

    pth = paths(a.root)
    cfg = load_config(a.root)
    data = read_json(Path(a.payload))

    pid = data.get("id") or slug(data.get("initials") or data.get("name_en") or data.get("name", ""))
    roster = {p["id"]: p for p in cfg.get("participants", [])}
    if pid not in roster:
        matches = [p for p in cfg.get("participants", [])
                   if pid in (slug(p.get("name_en") or ""), slug(p.get("initials") or ""), slug(p.get("name") or ""))]
        if matches:
            pid = matches[0]["id"]
        elif a.allow_new:
            entry = {"id": pid, "initials": data.get("initials", ""), "name": data.get("name", ""),
                     "name_en": data.get("name_en", ""),
                     "poster_no": data.get("poster_no") or f"P{len(cfg['participants']) + 1}",
                     "order": len(cfg["participants"]) + 1}
            cfg["participants"].append(entry)
            roster[pid] = entry
            write_json(pth["config"], cfg)
            print(f"  명부에 추가: {pid}")
        else:
            raise SystemExit(
                f"명부에 없는 참가자다: {pid}\n"
                f"  명부: {', '.join(roster) or '(비어 있음)'}\n"
                "  새로 넣으려면 --allow-new"
            )
    base = roster[pid]
    adir = pth["assets"] / pid

    conf_in = data.get("conference", {}) or {}
    d1, d2 = parse_date(conf_in.get("date")), parse_date(conf_in.get("date_end"))
    if d1 and d2 and d2 < d1:
        raise SystemExit("학회 종료일이 시작일보다 빠르다.")

    poster_in = data.get("poster", {}) or {}
    poster = {"title": poster_in.get("title") or "", "title_en": poster_in.get("title_en") or ""}
    if poster_in.get("path"):
        poster["file"] = copy_asset(Path(poster_in["path"]), adir, "poster")
        info = poster_geometry(adir / poster["file"])
        if info:
            poster["kind"] = info["kind"]
            poster["orientation"] = info["orientation"]
            for k in ("w_mm", "h_mm", "w_px", "h_px"):
                if info.get(k):
                    poster[k] = info[k]
            # 실측이 끝났으면 기본값을 끼워 넣지 않는다. 알려진 규격에 안 맞으면 규격은 '없음' 이다 —
            # 1422×933 mm 짜리를 'A0' 라고 표시하면 페이지가 방문자에게 거짓말을 한다.
            poster["size"] = info["size_label"] or ""
            poster["size_label"] = info["size_label"] or ""
            if info["kind"] == "pdf":
                print(f"  포스터 실측: {info['w_mm']:.0f} × {info['h_mm']:.0f} mm "
                      f"({info['size_label'] or '규격 미상'}, {info['orientation']})")
                if not info["size_label"]:
                    print("  경고: 알려진 규격(A0/A1/90×120cm/36×48in)과 15% 이상 다르다. "
                          "학회 인쇄 규정을 다시 확인할 것.")
            else:
                print(f"  포스터(이미지) {info['w_px']} × {info['h_px']} px, {info['orientation']}"
                      + (f" — 비율이 {info['size_label']} 와 같다" if info["size_label"] else ""))
                print("  참고: 이미지는 물리 크기를 알 수 없다. 비율로만 규격을 추정했다. "
                      "인쇄용 원본은 PDF 로 따로 보관할 것.")
        else:
            poster["orientation"] = poster_in.get("orientation") or cfg["defaults"].get("orientation") or "portrait"
            poster["size"] = poster_in.get("size") or cfg["defaults"].get("poster_size", "")
            print("  경고: 파일에서 크기를 못 읽었다. 방향은 입력값을 따른다.")
    elif poster_in.get("orientation"):
        poster["orientation"] = poster_in["orientation"]
        poster["size"] = poster_in.get("size") or cfg["defaults"].get("poster_size", "")

    supp = []
    for i, s in enumerate(data.get("supplementary") or [], start=1):
        if not s.get("path"):
            continue
        name = f"supp/{i:02d}-{slug(s.get('title') or Path(s['path']).stem)}"
        (adir / "supp").mkdir(parents=True, exist_ok=True)
        fname = copy_asset(Path(s["path"]), adir / "supp", Path(name).name)
        supp.append({"title": s.get("title") or Path(s["path"]).stem,
                     "note": s.get("note") or "", "file": f"supp/{fname}"})

    refs = []
    for r in data.get("references") or []:
        if isinstance(r, str):
            r = {"text": r}
        text = (r.get("text") or "").strip()
        if not (text or r.get("doi") or r.get("url")):
            continue
        refs.append({"text": text, "doi": (r.get("doi") or "").strip(),
                     "url": (r.get("url") or "").strip()})

    c_in = data.get("contact", {}) or {}
    contact = {}
    em = norm_email(c_in.get("email"))
    if em:
        contact["email"] = em
    for key in ("linkedin", "scholar", "site", "profile_url"):
        if c_in.get(key):
            contact[key] = norm_url(c_in[key], key)

    person = {
        "id": pid,
        "initials": data.get("initials") or base.get("initials") or "",
        "name": data.get("name") or base.get("name") or "",
        "name_en": data.get("name_en") or base.get("name_en") or "",
        "poster_no": data.get("poster_no") or base.get("poster_no") or "",
        "affiliation": data.get("affiliation") or cfg["defaults"].get("affiliation") or "",
        "authors": data.get("authors") or "",
        "abstract": data.get("abstract") or "",
        "conference": {
            "name": conf_in.get("name") or cfg["defaults"].get("conference") or "",
            "short": conf_in.get("short") or cfg["defaults"].get("conference_short") or "",
            "date": conf_in.get("date") or "",
            "date_end": conf_in.get("date_end") or "",
            "session": conf_in.get("session") or "",
            "city": conf_in.get("city") or "",
            "venue": conf_in.get("venue") or "",
        },
        "poster": poster,
        "supplementary": supp,
        "references": refs,
        "contact": contact,
        "updated": date.today().isoformat(),
    }
    write_json(pth["people"] / f"{pid}.json", person)

    print(f"기록 완료 → people/{pid}.json")
    missing = []
    if not person["conference"]["name"]:
        missing.append("학회명")
    if not person["poster"].get("title"):
        missing.append("포스터 제목")
    if not person["poster"].get("file"):
        missing.append("포스터 PDF")
    if not person["conference"]["date"]:
        missing.append("학회 날짜")
    if not person["poster_no"]:
        missing.append("포스터 번호")
    print(f"  선택 항목: 서플 {len(supp)}건 · 레퍼런스 {len(refs)}건 · "
          f"이메일 {'있음' if contact.get('email') else '없음'} · "
          f"LinkedIn {'있음' if contact.get('linkedin') else '없음'}")
    if missing:
        print(f"  아직 비어 있는 필수 항목: {', '.join(missing)}")
    print("\n다음: /poster-site:build 로 다시 그린다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
