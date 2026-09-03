#!/usr/bin/env python3
"""최소 QR 인코더 — 바이트 모드, 버전 1–6, EC 레벨 M/Q. 표준 라이브러리만.

포스터에 붙일 QR 하나를 만드는 데 외부 패키지를 요구하고 싶지 않아서 직접 짰다.
버전 6(EC M 기준 108바이트)까지면 어떤 현실적인 URL 도 들어간다. 그보다 길면
주소를 줄이라고 말하는 편이 맞다 — 학회장에서 스캔되는 것이 목적이고,
버전이 올라갈수록 모듈이 작아져 카메라가 못 잡는다.

출력은 SVG(인쇄용 벡터)와 PNG(화면용). PNG 도 zlib 으로 직접 쓴다.
"""
from __future__ import annotations

import struct
import zlib

# (EC codewords per block, g1 blocks, g1 data cw, g2 blocks, g2 data cw)
BLOCKS = {
    (1, "M"): (10, 1, 16, 0, 0), (1, "Q"): (13, 1, 13, 0, 0),
    (2, "M"): (16, 1, 28, 0, 0), (2, "Q"): (22, 1, 22, 0, 0),
    (3, "M"): (26, 1, 44, 0, 0), (3, "Q"): (18, 2, 17, 0, 0),
    (4, "M"): (18, 2, 32, 0, 0), (4, "Q"): (26, 2, 24, 0, 0),
    (5, "M"): (24, 2, 43, 0, 0), (5, "Q"): (18, 2, 15, 2, 16),
    (6, "M"): (16, 4, 27, 0, 0), (6, "Q"): (24, 4, 19, 0, 0),
}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}
ECL_BITS = {"L": 0b01, "M": 0b00, "Q": 0b11, "H": 0b10}

# ---------------------------------------------------------------- GF(256)
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _gen_poly(n: int) -> list[int]:
    g = [1]
    for i in range(n):
        g2 = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            g2[j] ^= c
            g2[j + 1] ^= _mul(c, _EXP[i])
        g = g2
    return g


def _ec(data: list[int], n: int) -> list[int]:
    g = _gen_poly(n)
    rem = list(data) + [0] * n
    for i in range(len(data)):
        coef = rem[i]
        if coef:
            for j, gc in enumerate(g):
                rem[i + j] ^= _mul(gc, coef)
    return rem[len(data):]


# ---------------------------------------------------------------- 비트 조립
def _encode(text: str, version: int, ecl: str) -> list[int]:
    ecw, g1n, g1d, g2n, g2d = BLOCKS[(version, ecl)]
    total_data = g1n * g1d + g2n * g2d
    payload = text.encode("utf-8")

    bits: list[int] = []

    def put(value: int, length: int) -> None:
        for i in range(length - 1, -1, -1):
            bits.append((value >> i) & 1)

    put(0b0100, 4)                                   # 바이트 모드
    put(len(payload), 8 if version < 10 else 16)
    for b in payload:
        put(b, 8)

    cap = total_data * 8
    if len(bits) > cap:
        raise ValueError("데이터가 이 버전에 안 들어간다")
    put(0, min(4, cap - len(bits)))                  # 종료 패턴
    while len(bits) % 8:
        bits.append(0)
    words = [int("".join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    pad = [0xEC, 0x11]
    i = 0
    while len(words) < total_data:
        words.append(pad[i % 2])
        i += 1

    blocks, ecs = [], []
    pos = 0
    for count, size in ((g1n, g1d), (g2n, g2d)):
        for _ in range(count):
            blk = words[pos:pos + size]
            pos += size
            blocks.append(blk)
            ecs.append(_ec(blk, ecw))

    out: list[int] = []
    for i in range(max(len(b) for b in blocks)):
        for b in blocks:
            if i < len(b):
                out.append(b[i])
    for i in range(ecw):
        for e in ecs:
            out.append(e[i])
    return out


# ---------------------------------------------------------------- 배치
def _blank(size: int):
    return [[None] * size for _ in range(size)]


def _place_function(m, version: int) -> None:
    size = len(m)

    def finder(r0, c0):
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = r0 + r, c0 + c
                if 0 <= rr < size and 0 <= cc < size:
                    on = (0 <= r <= 6 and c in (0, 6)) or (0 <= c <= 6 and r in (0, 6)) \
                        or (2 <= r <= 4 and 2 <= c <= 4)
                    m[rr][cc] = 1 if on else 0

    finder(0, 0); finder(0, size - 7); finder(size - 7, 0)
    for i in range(size):
        if m[6][i] is None:
            m[6][i] = 1 if i % 2 == 0 else 0
        if m[i][6] is None:
            m[i][6] = 1 if i % 2 == 0 else 0
    centers = ALIGN[version]
    for r in centers:
        for c in centers:
            if (r < 8 and c < 8) or (r < 8 and c > size - 9) or (r > size - 9 and c < 8):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    m[r + dr][c + dc] = 1 if max(abs(dr), abs(dc)) != 1 else 0
    m[size - 8][8] = 1                                  # dark module
    for i in range(9):                                  # 포맷 정보 자리 예약
        if m[8][i] is None:
            m[8][i] = 0
        if m[i][8] is None:
            m[i][8] = 0
    for i in range(8):
        if m[8][size - 1 - i] is None:
            m[8][size - 1 - i] = 0
        if m[size - 1 - i][8] is None:
            m[size - 1 - i][8] = 0


def _mask_fn(k: int):
    return (
        lambda r, c: (r + c) % 2 == 0,
        lambda r, c: r % 2 == 0,
        lambda r, c: c % 3 == 0,
        lambda r, c: (r + c) % 3 == 0,
        lambda r, c: (r // 2 + c // 3) % 2 == 0,
        lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
        lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
        lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
    )[k]


def _penalty(m) -> int:
    size = len(m)
    score = 0
    for line in list(m) + [list(col) for col in zip(*m)]:      # 규칙 1
        run, prev = 1, line[0]
        for v in line[1:]:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run, prev = 1, v
        if run >= 5:
            score += 3 + (run - 5)
    for r in range(size - 1):                                   # 규칙 2
        for c in range(size - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    pat1 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    pat2 = list(reversed(pat1))
    for line in list(m) + [list(col) for col in zip(*m)]:       # 규칙 3
        for i in range(size - 10):
            seg = line[i:i + 11]
            if seg == pat1 or seg == pat2:
                score += 40
    dark = sum(sum(r) for r in m)                               # 규칙 4
    score += 10 * (abs(dark * 100 // (size * size) - 50) // 5)
    return score


def _format_bits(ecl: str, mask: int) -> int:
    data = (ECL_BITS[ecl] << 3) | mask
    v = data << 10
    for i in range(4, -1, -1):
        if v & (1 << (i + 10)):
            v ^= 0x537 << i
    return ((data << 10) | v) ^ 0x5412


def make_matrix(text: str, ecl: str = "Q", min_version: int = 1):
    """텍스트 → 0/1 행렬. 들어가는 가장 작은 버전을 고른다."""
    for version in range(max(1, min_version), 7):
        if (version, ecl) not in BLOCKS:
            continue
        try:
            words = _encode(text, version, ecl)
        except ValueError:
            continue
        size = version * 4 + 17
        m = _blank(size)
        _place_function(m, version)
        bits = [(w >> i) & 1 for w in words for i in range(7, -1, -1)]

        idx, col = 0, size - 1
        up = True
        while col > 0:
            if col == 6:
                col -= 1
            rows = range(size - 1, -1, -1) if up else range(size)
            for r in rows:
                for c in (col, col - 1):
                    if m[r][c] is None:
                        m[r][c] = bits[idx] if idx < len(bits) else 0
                        idx += 1
            up = not up
            col -= 2

        best, best_score = None, None
        for k in range(8):
            fn = _mask_fn(k)
            cand = [row[:] for row in m]
            reserved = _blank(size)
            _place_function(reserved, version)
            for r in range(size):
                for c in range(size):
                    if reserved[r][c] is None and fn(r, c):
                        cand[r][c] ^= 1
            fmt = _format_bits(ecl, k)
            for i in range(15):
                bit = (fmt >> i) & 1
                # 세로 사본 — 8열. i=0 이 최하위 비트고 위에서부터 내려간다.
                if i < 6:
                    cand[i][8] = bit
                elif i < 8:
                    cand[i + 1][8] = bit
                else:
                    cand[size - 15 + i][8] = bit
                # 가로 사본 — 8행. 오른쪽 끝에서부터 들어온다.
                if i < 8:
                    cand[8][size - i - 1] = bit
                elif i < 9:
                    cand[8][7] = bit
                else:
                    cand[8][15 - i - 1] = bit
            cand[size - 8][8] = 1
            s = _penalty(cand)
            if best_score is None or s < best_score:
                best, best_score = cand, s
        return best
    raise ValueError(f"URL 이 너무 길다 ({len(text.encode())} bytes). 버전 6 까지만 만든다 — 주소를 줄일 것.")


# ---------------------------------------------------------------- 출력
def to_svg(matrix, quiet: int = 4, module: int = 8, dark: str = "#000000",
           light: str = "#ffffff") -> str:
    n = len(matrix)
    side = (n + quiet * 2) * module
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{side}" height="{side}" '
             f'viewBox="0 0 {n + quiet * 2} {n + quiet * 2}" shape-rendering="crispEdges">',
             f'<rect width="100%" height="100%" fill="{light}"/>', f'<path fill="{dark}" d="']
    d = []
    for r, row in enumerate(matrix):
        c = 0
        while c < n:
            if row[c]:
                start = c
                while c < n and row[c]:
                    c += 1
                d.append(f"M{start + quiet} {r + quiet}h{c - start}v1h-{c - start}z")
            else:
                c += 1
    parts.append("".join(d))
    parts.append('"/></svg>\n')
    return "".join(parts)


def to_png(matrix, path, quiet: int = 4, module: int = 10) -> None:
    """1비트 흑백 PNG 를 zlib 으로 직접 쓴다."""
    n = len(matrix)
    side = (n + quiet * 2) * module
    rows = []
    for r in range(side):
        mr = r // module - quiet
        line = bytearray([0])                     # filter type 0
        for c in range(side):
            mc = c // module - quiet
            on = 0 <= mr < n and 0 <= mc < n and matrix[mr][mc]
            line.append(0 if on else 255)
        rows.append(bytes(line))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 0, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)
