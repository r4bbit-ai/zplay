"""Rotating vinyl disc renderer (truecolour half-block pixels).

No image -> a vector 'skeleton svg' label (dashed rings + music note).
With image(s) -> the picture is mapped onto the label and spins with the disc.
"""
from __future__ import annotations

import math
from functools import lru_cache

try:
    from PIL import Image as _Image
except Exception:            # pragma: no cover
    _Image = None

IMG_N = 108                  # label texture resolution
LABEL_R = 0.46               # label radius (fraction of disc radius)
HOLE_R = 0.055
RIM_R = 0.955


def has_pil() -> bool:
    return _Image is not None


@lru_cache(maxsize=8)
def _texture(path: str, mtime: float, n: int = IMG_N):
    """Square RGB texture as a flat bytes buffer, or None."""
    if _Image is None:
        return None
    try:
        im = _Image.open(path)
        im = im.convert("RGB")
        w, h = im.size
        s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
        im = im.resize((n, n), _Image.BILINEAR)
        return im.tobytes()
    except Exception:
        return None


def texture(path: str | None):
    if not path:
        return None
    try:
        import os
        return _texture(path, os.path.getmtime(path))
    except Exception:
        return None


@lru_cache(maxsize=8)
def _geometry(w: int, h: int):
    """Per-pixel (dx, dy) in disc space for a w x h cell area (h*2 pixels)."""
    ph = h * 2
    d = min(w, ph)
    cx, cy = w / 2.0, ph / 2.0
    r = d / 2.0
    grid = []
    for py in range(ph):
        dy = (py + 0.5 - cy) / r
        row = []
        for px in range(w):
            dx = (px + 0.5 - cx) / r
            row.append((dx, dy))
        grid.append(row)
    return grid


def _note_shape(x: float, y: float) -> bool:
    """Vector music note inside the label (x,y in -1..1 label space)."""
    # note head (tilted ellipse)
    hx, hy = x + 0.34, y - 0.42
    a = hx * 0.94 + hy * 0.34
    b = -hx * 0.34 + hy * 0.94
    if (a / 0.36) ** 2 + (b / 0.26) ** 2 <= 1.0:
        return True
    # stem
    if 0.24 <= x <= 0.38 and -0.62 <= y <= 0.32:
        return True
    # flag
    if 0.30 <= x <= 0.78 and -0.62 <= y <= -0.18:
        if (y + 0.62) <= (0.78 - x) * 1.15:
            return True
    return False


def render(w: int, h: int, angle: float, img_path: str | None, shape: str,
           accent, pulse: float = 0.0, grain: bool = True, glow: bool = True,
           ascii_only: bool = False, playing: bool = True):
    """Return a list of h ANSI strings drawing the disc."""
    if w < 6 or h < 3:
        return ["" for _ in range(max(0, h))]
    grid = _geometry(w, h)
    tex = texture(img_path)
    ca, sa = math.cos(-angle), math.sin(-angle)
    scale = 1.0 / (1.0 + 0.05 * pulse)          # beat pulse = disc grows
    ar, ag, ab = accent
    rows = []
    ph = h * 2
    pix = [[None] * w for _ in range(ph)]

    for py in range(ph):
        grow = grid[py]
        prow = pix[py]
        for px in range(w):
            dx, dy = grow[px]
            dx *= scale
            dy *= scale
            rx = dx * ca - dy * sa
            ry = dx * sa + dy * ca
            if shape == "square":
                r = max(abs(rx), abs(ry))
                rr = r
            else:
                rr = math.sqrt(dx * dx + dy * dy)
                r = rr
            if r > 1.0:
                continue
            if r <= HOLE_R:
                prow[px] = (8, 8, 10)
                continue
            if r > RIM_R:
                k = 0.6 + 0.4 * (1.0 - (r - RIM_R) / (1.0 - RIM_R))
                prow[px] = (int(60 * k), int(60 * k), int(68 * k))
                continue
            if r <= LABEL_R:
                lx, ly = rx / LABEL_R, ry / LABEL_R
                if tex is not None:
                    sx = int((lx + 1.0) * 0.5 * (IMG_N - 1))
                    sy = int((ly + 1.0) * 0.5 * (IMG_N - 1))
                    sx = 0 if sx < 0 else (IMG_N - 1 if sx >= IMG_N else sx)
                    sy = 0 if sy < 0 else (IMG_N - 1 if sy >= IMG_N else sy)
                    o = (sy * IMG_N + sx) * 3
                    prow[px] = (tex[o], tex[o + 1], tex[o + 2])
                else:
                    # ---- skeleton "svg" label ----
                    lr = math.sqrt(lx * lx + ly * ly)
                    base = 46 + int(26 * (1.0 - lr))
                    col = (base, base, base + 6)
                    th = math.atan2(ly, lx)
                    if 0.80 <= lr <= 0.90:      # dashed outer ring
                        if int((th + math.pi) / (math.pi / 14)) % 2 == 0:
                            col = (int(ar * 0.75) + 30, int(ag * 0.75) + 30, int(ab * 0.75) + 30)
                    elif 0.60 <= lr <= 0.645:   # thin ring
                        col = (110, 110, 118)
                    elif _note_shape(lx, ly):
                        col = (min(255, ar + 40), min(255, ag + 40), min(255, ab + 40))
                    prow[px] = col
                continue
            # ---- vinyl body ----
            v = 20
            if grain:
                v += int(7 * (0.5 + 0.5 * math.sin(r * 165.0)))
                v += int(4 * (0.5 + 0.5 * math.sin(r * 47.0 + 1.7)))
            if glow:
                th = math.atan2(ry, rx)
                lobe = math.cos(2.0 * th)
                if lobe > 0:
                    v += int(52 * (lobe ** 6))
            prow[px] = (v, v, min(255, v + 4))

    if ascii_only:
        for py in range(ph):
            pass

    for y in range(h):
        top = pix[2 * y]
        bot = pix[2 * y + 1]
        parts = []
        last = None
        for x in range(w):
            t, b = top[x], bot[x]
            if t is None and b is None:
                if last is not None:
                    parts.append("\x1b[0m")
                    last = None
                parts.append(" ")
                continue
            if ascii_only:
                c = t or b
                key = ("a", c)
                if key != last:
                    parts.append(f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m")
                    last = key
                parts.append("#")
                continue
            if t is not None and b is not None:
                key = ("h", t, b)
                if key != last:
                    parts.append(f"\x1b[38;2;{t[0]};{t[1]};{t[2]}m"
                                 f"\x1b[48;2;{b[0]};{b[1]};{b[2]}m")
                    last = key
                parts.append("\u2580")
            elif t is not None:
                key = ("t", t)
                if key != last:
                    parts.append(f"\x1b[0m\x1b[38;2;{t[0]};{t[1]};{t[2]}m")
                    last = key
                parts.append("\u2580")
            else:
                key = ("b", b)
                if key != last:
                    parts.append(f"\x1b[0m\x1b[38;2;{b[0]};{b[1]};{b[2]}m")
                    last = key
                parts.append("\u2584")
        parts.append("\x1b[0m")
        rows.append("".join(parts))
    return rows
