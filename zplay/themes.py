"""20 colour themes for the frequency bars / UI accents. Retro-JP palette."""
from __future__ import annotations

import colorsys

RGB = tuple


class Theme:
    __slots__ = ("name", "jp", "mode", "stops")

    def __init__(self, name: str, jp: str, mode: str, stops: list):
        self.name = name          # cli name
        self.jp = jp              # katakana/kanji label
        self.mode = mode          # vgrad | multi | rainbow
        self.stops = stops        # list of (r,g,b)

    # ---- colour lookup -------------------------------------------------
    def color(self, t: float, idx: int = 0, nbars: int = 1) -> RGB:
        """t = 0..1 height fraction; idx = bar index."""
        if self.mode == "rainbow":
            h = (idx / max(1, nbars)) % 1.0
            r, g, b = colorsys.hsv_to_rgb(h, 0.85, 0.45 + 0.55 * t)
            return (int(r * 255), int(g * 255), int(b * 255))
        if self.mode == "multi":
            base = self.stops[idx % len(self.stops)]
            k = 0.45 + 0.55 * t
            return (int(base[0] * k), int(base[1] * k), int(base[2] * k))
        return _grad(self.stops, t)

    def accent(self) -> RGB:
        if self.mode == "rainbow":
            return (236, 110, 173)
        return self.stops[len(self.stops) // 2] if self.stops else (220, 220, 220)

    def dim(self) -> RGB:
        a = self.accent()
        return (a[0] // 3 + 20, a[1] // 3 + 20, a[2] // 3 + 20)


def _grad(stops: list, t: float) -> RGB:
    if not stops:
        return (200, 200, 200)
    if len(stops) == 1:
        return stops[0]
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    x = t * (len(stops) - 1)
    i = int(x)
    if i >= len(stops) - 1:
        return stops[-1]
    f = x - i
    a, b = stops[i], stops[i + 1]
    return (int(a[0] + (b[0] - a[0]) * f),
            int(a[1] + (b[1] - a[1]) * f),
            int(a[2] + (b[2] - a[2]) * f))


# 20 themes ------------------------------------------------------------------
THEMES: list = [
    Theme("sakura",    "サクラ",   "vgrad", [(74, 24, 45), (156, 51, 92), (226, 106, 156), (255, 183, 213), (255, 236, 245)]),
    Theme("ume",       "ウメ",     "vgrad", [(56, 8, 40), (140, 20, 92), (214, 51, 140), (255, 122, 193), (255, 214, 236)]),
    Theme("momo",      "モモ",     "vgrad", [(92, 40, 40), (196, 96, 92), (245, 150, 128), (255, 200, 170), (255, 240, 226)]),
    Theme("matcha",    "マッチャ", "vgrad", [(18, 46, 24), (44, 104, 48), (96, 168, 74), (170, 214, 108), (226, 246, 178)]),
    Theme("take",      "タケ",     "vgrad", [(12, 48, 44), (22, 104, 92), (44, 164, 140), (120, 214, 186), (206, 250, 232)]),
    Theme("mint",      "ミント",   "vgrad", [(16, 58, 52), (30, 130, 112), (72, 196, 168), (150, 236, 210), (226, 255, 244)]),
    Theme("sora",      "ソラ",     "vgrad", [(14, 40, 72), (26, 92, 156), (62, 152, 226), (140, 206, 250), (222, 242, 255)]),
    Theme("ai",        "アイ",     "vgrad", [(12, 20, 62), (30, 48, 132), (66, 96, 208), (130, 160, 246), (212, 226, 255)]),
    Theme("ruri",      "ルリ",     "vgrad", [(8, 30, 70), (14, 74, 150), (26, 130, 214), (96, 190, 246), (206, 238, 255)]),
    Theme("fuji",      "フジ",     "vgrad", [(46, 30, 82), (94, 66, 164), (146, 118, 222), (196, 178, 248), (236, 228, 255)]),
    Theme("murasaki",  "ムラサキ", "vgrad", [(40, 12, 60), (98, 28, 140), (156, 66, 210), (206, 142, 246), (240, 214, 255)]),
    Theme("lavender",  "ラベンダー", "vgrad", [(52, 44, 84), (110, 96, 168), (168, 152, 226), (212, 202, 248), (242, 238, 255)]),
    Theme("yuyake",    "ユウヤケ", "vgrad", [(70, 14, 34), (168, 40, 44), (232, 100, 44), (250, 168, 78), (255, 226, 156)]),
    Theme("hinode",    "ヒノデ",   "vgrad", [(88, 16, 26), (196, 42, 52), (244, 108, 76), (255, 176, 110), (255, 236, 196)]),
    Theme("kohaku",    "コハク",   "vgrad", [(66, 34, 4), (150, 88, 14), (216, 146, 32), (246, 198, 90), (255, 238, 176)]),
    Theme("kin",       "キン",     "vgrad", [(58, 42, 8), (140, 110, 22), (206, 172, 52), (240, 216, 120), (255, 248, 200)]),
    Theme("sango",     "サンゴ",   "vgrad", [(84, 22, 40), (184, 56, 78), (238, 112, 108), (255, 170, 148), (255, 224, 206)]),
    Theme("kuro",      "クロ",     "vgrad", [(30, 30, 34), (78, 78, 84), (134, 134, 142), (190, 190, 198), (245, 245, 250)]),
    Theme("rainbow",   "ニジ",     "rainbow", []),
    Theme("multi",     "マルチ",   "multi", [(255, 92, 146), (255, 170, 64), (255, 236, 92), (110, 226, 128),
                                              (86, 200, 240), (120, 132, 246), (196, 118, 250), (255, 128, 208)]),
]

BY_NAME = {t.name: t for t in THEMES}
NAMES = [t.name for t in THEMES]


def get(name: str) -> Theme:
    return BY_NAME.get(str(name).lower(), BY_NAME["sakura"])


def next_theme(name: str, step: int = 1) -> str:
    try:
        i = NAMES.index(str(name).lower())
    except ValueError:
        i = 0
    return NAMES[(i + step) % len(NAMES)]
