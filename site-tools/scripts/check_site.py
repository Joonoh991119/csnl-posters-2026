#!/usr/bin/env python3
"""게시 전 점검 — 빠진 것, 안 맞는 것, 올리면 안 되는 것.

  python3 scripts/check_site.py [--root ./poster-site]

오류가 하나라도 있으면 종료코드 1. 경고만 있으면 0.
이 스크립트는 사람의 판단을 대신하지 않는다 — 미공개 데이터 여부는 저자만 안다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitelib import (  # noqa: E402
    human_size, load_config, load_people, parse_date, paths, poster_geometry, window_state,
)

# 학회별 포스터 규격 힌트. 규정이 바뀌면 이 표가 아니라 학회 공지가 옳다.
VENUE_HINTS = {
    "cbrain": ("portrait", "CBrain 은 A0 세로"),
    "ksbns": ("landscape", "KSBNS 는 A0 가로"),
}
GH_HARD_LIMIT = 100 * 1024 * 1024
BIG = 25 * 1024 * 1024


def main() -> int:
    ap = argparse.ArgumentParser(description="poster-site 점검")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()

    pth = paths(a.root)
    cfg = load_config(a.root)
    people = {p["id"]: p for p in load_people(a.root)}
    errors, warns, infos = [], [], []

    w = cfg.get("window", {}) or {}
    s, e = parse_date(w.get("start")), parse_date(w.get("end"))
    if not (s and e):
        warns.append("게시기간이 반쯤 비어 있다 — 종료일이 없으면 내릴 시점을 아무도 모른다")
    elif e < s:
        errors.append(f"게시 종료일({w['end']})이 시작일({w['start']})보다 빠르다")
    state, days = window_state(cfg)
    if state == "closed":
        warns.append(f"게시기간이 이미 {days}일 지났다 — /poster-site:takedown 을 쓸 시점")

    site = cfg.get("site", {}) or {}
    if not (site.get("lab_home_url") or site.get("members_url")):
        warns.append("lab_home_url 이 비어 있다 — 메인의 Lab homepage 버튼이 안 나온다")
    if not cfg.get("participants"):
        errors.append("참가자 명부가 비어 있다")

    for part in cfg.get("participants", []):
        pid = part["id"]
        who = f"{part.get('poster_no', '')} {pid}".strip()
        p = people.get(pid)
        if not p:
            infos.append(f"{who}: 아직 정보 미제출 ('준비 중' 카드로 나간다)")
            continue
        if p.get("publish") is False:
            infos.append(f"{who}: 자료는 있으나 공개 보류 상태다 — 본인이 확인하면 열린다")
            continue

        conf = p.get("conference", {}) or {}
        poster = p.get("poster", {}) or {}
        if not conf.get("name") and not conf.get("short"):
            errors.append(f"{who}: 학회명이 없다")
        if not conf.get("date"):
            warns.append(f"{who}: 학회 날짜가 없다 — 사람마다 다르므로 각자 넣어야 한다")
        if not p.get("poster_no"):
            errors.append(f"{who}: 포스터 번호가 없다")
        if not poster.get("title"):
            errors.append(f"{who}: 포스터 제목이 없다")

        if not poster.get("file"):
            errors.append(f"{who}: 포스터 PDF 가 없다")
        else:
            f = pth["assets"] / pid / poster["file"]
            if not f.exists():
                errors.append(f"{who}: {poster['file']} 이 assets/{pid}/ 에 없다")
            else:
                size = f.stat().st_size
                if size >= GH_HARD_LIMIT:
                    errors.append(f"{who}: 포스터 {human_size(size)} — GitHub 단일 파일 한도(100MB) 초과. "
                                  "gs -dPDFSETTINGS=/ebook 으로 다운샘플할 것")
                elif size >= BIG:
                    warns.append(f"{who}: 포스터 {human_size(size)} — 모바일에서 열기 무겁다. "
                                 "다운샘플을 권한다")
                info = poster_geometry(f)
                if info:
                    if info["kind"] == "pdf" and not info["size_label"]:
                        warns.append(f"{who}: 규격이 알려진 어느 것과도 15% 이상 다르다 "
                                     f"({info['w_mm']:.0f}×{info['h_mm']:.0f} mm, 비율 "
                                     f"{max(info['w_mm'], info['h_mm']) / min(info['w_mm'], info['h_mm']):.2f}). "
                                     "학회 인쇄 규정을 확인할 것")
                    if info["kind"] == "image":
                        infos.append(f"{who}: 포스터가 이미지다 ({info['w_px']}×{info['h_px']} px). "
                                     "화면용으로는 문제없지만 인쇄 원본은 PDF 로 따로 보관할 것")
                    key = (conf.get("short") or conf.get("name") or "").lower()
                    for token, (want, note) in VENUE_HINTS.items():
                        if token in key and info["orientation"] != want:
                            warns.append(f"{who}: {note} 로 알고 있는데 PDF 는 {info['orientation']} 다 — "
                                         "학회 공지를 다시 확인할 것")

        for sfile in p.get("supplementary") or []:
            if sfile.get("file") and not (pth["assets"] / pid / sfile["file"]).exists():
                errors.append(f"{who}: supplementary {sfile['file']} 이 없다")
        for r in p.get("references") or []:
            if not (r.get("text") or "").strip() and not r.get("doi") and not r.get("url"):
                warns.append(f"{who}: 내용이 빈 레퍼런스 항목이 있다")

        c = p.get("contact", {}) or {}
        if not c.get("email"):
            infos.append(f"{who}: 이메일 없음 (선택 항목)")
        if not c.get("linkedin"):
            infos.append(f"{who}: LinkedIn 없음 (선택 항목)")
        if not p.get("supplementary"):
            infos.append(f"{who}: supplementary 없음 (선택 항목 — 섹션이 안 그려진다)")
        if not p.get("references"):
            infos.append(f"{who}: references 없음 (선택 항목 — 섹션이 안 그려진다)")

    dist = pth["dist"]
    if dist.exists():
        newest_src = max((f.stat().st_mtime for f in list(pth["people"].glob("*.json"))
                          + [pth["config"]] if f.exists()), default=0)
        idx = dist / "index.html"
        if idx.exists() and idx.stat().st_mtime < newest_src:
            warns.append("dist 가 자료보다 오래됐다 — /poster-site:build 를 다시 돌릴 것")
        total = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file())
        infos.append(f"dist 총 용량 {human_size(total)}")
    else:
        warns.append("dist 가 아직 없다 — /poster-site:build 먼저")

    print("=== poster-site 점검 ===")
    for label, items, mark in (("오류", errors, "✘"), ("경고", warns, "!"), ("참고", infos, "·")):
        if items:
            print(f"\n[{label}]")
            for x in items:
                print(f"  {mark} {x}")
    print("\n[공개 전 사람이 판단할 것]")
    print("  · 이 포스터에 미공개 데이터·심사 중 결과가 들어 있는가")
    print("  · 공동저자와 지도교수가 온라인 공개에 동의했는가")
    print("  · 참여자 식별정보나 원자료가 서플에 섞여 있지 않은가")
    print(f"\n오류 {len(errors)} · 경고 {len(warns)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
