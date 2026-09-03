#!/usr/bin/env python3
"""빌더를 콘텐츠 저장소로 복사한다 — CI 가 플러그인 없이도 사이트를 다시 세울 수 있게.

  python3 scripts/export_tools.py --repo ~/Projects/csnl-posters-2026 [--no-workflow]

콘텐츠 저장소는 이런 모양이 된다.

    poster-site/          config.json · people/ · assets/     ← 연구원들이 고치는 곳
    site-tools/           scripts/ · templates/ · VERSION     ← 이 스크립트가 넣는다
    .github/workflows/    deploy.yml                          ← push 되면 CI 가 빌드·배포

플러그인을 업데이트했으면 이 스크립트를 다시 돌려 site-tools 를 맞춘다.
연구원들은 site-tools 를 건드리지 않는다.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
SKIP = {"__pycache__", ".DS_Store"}


def copy_tree(src: Path, dst: Path) -> int:
    n = 0
    for item in src.rglob("*"):
        if any(part in SKIP for part in item.parts):
            continue
        if item.is_dir():
            continue
        target = dst / item.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="콘텐츠 저장소에 빌더를 넣는다")
    ap.add_argument("--repo", required=True, help="콘텐츠 저장소 경로")
    ap.add_argument("--no-workflow", action="store_true", help="GitHub Actions 워크플로를 건드리지 않는다")
    a = ap.parse_args()

    repo = Path(a.repo).expanduser().resolve()
    if not repo.exists():
        raise SystemExit(f"저장소 경로가 없다: {repo}")

    tools = repo / "site-tools"
    if tools.exists():
        shutil.rmtree(tools)
    n = copy_tree(PLUGIN / "scripts", tools / "scripts")
    n += copy_tree(PLUGIN / "templates", tools / "templates")

    version = "unknown"
    try:
        version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    except Exception:
        pass
    (tools / "VERSION").write_text(
        f"poster-site {version}\n동기화 {date.today().isoformat()}\n"
        "이 폴더는 플러그인에서 복사된 것이다. 여기서 고치지 말고 플러그인에서 고친 뒤\n"
        "/poster-site:publish --tools 로 다시 내보낸다.\n", encoding="utf-8")

    if not a.no_workflow:
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PLUGIN / "templates" / "ci" / "deploy.yml", wf / "deploy.yml")
        print(f"워크플로 → .github/workflows/deploy.yml")

    print(f"site-tools 동기화 완료 ({n}개 파일, poster-site {version})")
    print(f"  → {tools}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
