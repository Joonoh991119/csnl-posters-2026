#!/usr/bin/env python3
"""dist 를 로컬 서버로 띄운다. PC 와 휴대폰에서 같이 확인하라고 LAN 주소도 찍는다.

  python3 scripts/preview.py [--root ./poster-site] [--port 8787]
"""
from __future__ import annotations

import argparse
import http.server
import socket
import socketserver
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitelib import paths  # noqa: E402


def lan_ip() -> str | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))  # TEST-NET-1, 실제로 나가지 않는다
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="poster-site 미리보기 서버")
    ap.add_argument("--root", default=None)
    ap.add_argument("--port", type=int, default=8787)
    a = ap.parse_args()

    dist = paths(a.root)["dist"]
    if not (dist / "index.html").exists():
        raise SystemExit(f"dist 가 없다: {dist}\n  먼저 /poster-site:build")

    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(dist))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", a.port), handler) as httpd:
        print(f"미리보기 서버 → http://localhost:{a.port}/")
        ip = lan_ip()
        if ip:
            print(f"같은 wifi 의 휴대폰에서 → http://{ip}:{a.port}/")
            print("  (모바일 확인용이다. 좁은 화면에서 카드가 한 줄로 떨어지는지, "
                  "포스터 미리보기가 화면을 넘지 않는지 본다)")
        print("Ctrl+C 로 종료")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n종료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
