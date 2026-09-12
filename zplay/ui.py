"""zplay TUI - retro japanese vibe, truecolour, stdlib only.

Screen 1: rotating disc + transport   Screen 2: frequency bars   Screen 3: settings
"""
from __future__ import annotations

import math
import os
import random
import select
import signal
import sys
import termios
import time
import tty
from pathlib import Path

from . import config, disc, spectrum, themes
from .player import Player, PlayerError

ESC = "\x1b"
RESET = "\x1b[0m"


def fg(c):
    return f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m"


def bold(s):
    return f"\x1b[1m{s}\x1b[22m"


def vislen(s: str) -> int:
    """Visible width, ignoring ANSI and counting CJK as 2 cells."""
    n, i = 0, 0
    while i < len(s):
        ch = s[i]
        if ch == "\x1b":
            j = s.find("m", i)
            i = (j + 1) if j != -1 else len(s)
            continue
        o = ord(ch)
        n += 2 if (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF or
                   0xAC00 <= o <= 0xD7A3 or 0xF900 <= o <= 0xFAFF or
                   0xFF00 <= o <= 0xFF60 or 0xFFE0 <= o <= 0xFFE6) else 1
        i += 1
    return n


def pad(s: str, w: int) -> str:
    d = w - vislen(s)
    return s + " " * d if d > 0 else s


def center(s: str, w: int) -> str:
    d = w - vislen(s)
    if d <= 0:
        return s
    left = d // 2
    return " " * left + s + " " * (d - left)


def clip(s: str, w: int) -> str:
    if vislen(s) <= w:
        return s
    out, n = [], 0
    for ch in s:
        cw = vislen(ch)
        if n + cw > w - 1:
            out.append("\u2026")
            break
        out.append(ch)
        n += cw
    return "".join(out)


def mmss(t: float) -> str:
    t = max(0, int(t or 0))
    return f"{t // 60:02d}:{t % 60:02d}"


BLOCKS = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
ASCII_BLOCKS = " .:-=+*#@"
PETALS = "\u273f\u2740\u00b7\u2734\u02da"


class App:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.player = Player(cfg)
        self.spec = spectrum.Spectrum()
        self.screen = int(cfg.get("start_screen", 1)) or 1
        self.angle = 0.0
        self.levels: list = []
        self.peaks: list = []
        self.image: str | None = None
        self.track: str | None = None
        self.status: dict = {"running": False}
        self.msg = ""
        self.msg_at = 0.0
        self.sel = 0
        self.prompt: dict | None = None
        self.help = False
        self.pulse = 0.0
        self.petals: list = []
        self.running = True
        self.resized = True
        self.w, self.h = 80, 24
        self._last_status = 0.0

    # ------------------------------------------------------------ notify --
    def notify(self, text: str):
        self.msg = text
        self.msg_at = time.time()

    # ------------------------------------------------------------- setup --
    def size(self):
        try:
            s = os.get_terminal_size()
            return max(40, s.columns), max(14, s.lines)
        except OSError:
            return 80, 24

    def run(self):
        fdin = sys.stdin.fileno()
        old = termios.tcgetattr(fdin)
        signal.signal(signal.SIGWINCH, lambda *_: setattr(self, "resized", True))
        try:
            tty.setraw(fdin)
            sys.stdout.write("\x1b[?1049h\x1b[?25l")
            self.loop()
        finally:
            termios.tcsetattr(fdin, termios.TCSADRAIN, old)
            sys.stdout.write("\x1b[?25h\x1b[?1049l" + RESET)
            sys.stdout.flush()
            config.save(self.cfg)

    # -------------------------------------------------------------- loop --
    def loop(self):
        fps = max(6, min(60, int(self.cfg.get("fps", 20))))
        dt = 1.0 / fps
        last = time.time()
        try:
            self.player.start()
            self.player.ensure_loaded()
        except PlayerError as e:
            self.notify(str(e))
        while self.running:
            now = time.time()
            step = now - last
            last = now
            self.read_keys()
            if now - self._last_status > 0.2:
                self._last_status = now
                self.poll()
            self.animate(step)
            self.draw()
            time.sleep(max(0.0, dt - (time.time() - now)))

    def poll(self):
        try:
            st = self.player.status()
        except Exception:
            st = {"running": False}
        self.status = st
        path = st.get("path")
        if path and path != self.track:
            self.track = path
            self.spec.load(path)
            new = config.pick_image(self.cfg, self.image)
            if new:
                self.image = new
            elif self.cfg.get("image_mode") == "off":
                self.image = None
        elif not path:
            self.track = None

    # ---------------------------------------------------------- animation --
    def animate(self, dt: float):
        st = self.status
        playing = st.get("running") and not st.get("paused", True)
        bands = self.spec.at(st.get("pos", 0.0)) if playing else []
        if not bands:
            bands = [0.0] * spectrum.BANDS
            if playing:  # analysis still running -> soft idle wave
                t = time.time()
                bands = [max(0.0, 0.25 * math.sin(t * 3 + i * 0.35) + 0.22)
                         for i in range(spectrum.BANDS)]
        if not self.levels or len(self.levels) != len(bands):
            self.levels = [0.0] * len(bands)
            self.peaks = [0.0] * len(bands)
        for i, v in enumerate(bands):
            cur = self.levels[i]
            self.levels[i] = v if v > cur else cur + (v - cur) * min(1.0, dt * 9.0)
            if self.levels[i] > self.peaks[i]:
                self.peaks[i] = self.levels[i]
            else:
                self.peaks[i] = max(0.0, self.peaks[i] - dt * 0.55)
        energy = sum(self.levels[:12]) / 12.0 if self.levels else 0.0
        self.pulse += (energy - self.pulse) * min(1.0, dt * 8.0)
        if self.cfg.get("rotate", True) and playing:
            self.angle += dt * 1.6 * float(self.cfg.get("rotate_speed", 1.0)) * (1 + 0.25 * self.pulse)
        if self.cfg.get("petals"):
            self.step_petals(dt, playing)

    def step_petals(self, dt: float, playing: bool):
        w, h = self.w, self.h
        target = 0 if not playing else max(4, w // 14)
        while len(self.petals) < target:
            self.petals.append({"x": random.uniform(0, w), "y": random.uniform(-h, h),
                                "vy": random.uniform(1.6, 5.0),
                                "dx": random.uniform(-1.2, 1.2),
                                "c": random.choice(PETALS)})
        while len(self.petals) > target:
            self.petals.pop()
        for p in self.petals:
            p["y"] += p["vy"] * dt
            p["x"] += math.sin(p["y"] * 0.8) * p["dx"] * dt
            if p["y"] > h - 2:
                p["y"] = -1.0
                p["x"] = random.uniform(0, w)

    # -------------------------------------------------------------- input --
    def read_keys(self):
        buf = ""
        while select.select([sys.stdin], [], [], 0)[0]:
            ch = os.read(sys.stdin.fileno(), 1024).decode("utf-8", "ignore")
            if not ch:
                break
            buf += ch
        i = 0
        while i < len(buf):
            c = buf[i]
            if c == ESC and buf[i:i + 3] in ("\x1b[A", "\x1b[B", "\x1b[C", "\x1b[D"):
                self.key({"A": "up", "B": "down", "C": "right", "D": "left"}[buf[i + 2]])
                i += 3
                continue
            if c == ESC:
                self.key("esc")
                i += 1
                continue
            self.key(c)
            i += 1

    def key(self, k: str):
        if self.prompt is not None:
            self.key_prompt(k)
            return
        if self.help and k not in ("?", "esc", "q"):
            self.help = False
            return
        cfg = self.cfg
        p = self.player
        try:
            if k in ("q", "\x03"):
                self.running = False
            elif k == "?":
                self.help = not self.help
            elif k in "123":
                self.screen = int(k)
            elif k == "\t":
                self.screen = self.screen % 3 + 1
            elif k == " ":
                p.toggle()
            elif k in ("n",):
                p.next()
            elif k in ("p", "b"):
                p.prev()
            elif k == "right" and self.screen != 3:
                p.seek(float(cfg.get("seek_step", 5)))
            elif k == "left" and self.screen != 3:
                p.seek(-float(cfg.get("seek_step", 5)))
            elif k in ("+", "="):
                self.notify(f"volume {p.volume(cfg.get('volume', 80) + 5)}")
            elif k == "-":
                self.notify(f"volume {p.volume(cfg.get('volume', 80) - 5)}")
            elif k == "t":
                cfg["theme"] = themes.next_theme(cfg["theme"])
                self.notify("theme " + cfg["theme"])
            elif k == "T":
                cfg["theme"] = themes.next_theme(cfg["theme"], -1)
                self.notify("theme " + cfg["theme"])
            elif k == "i":
                img = config.pick_image(cfg, self.image)
                self.image = img
                self.notify("image " + (Path(img).name if img else "none"))
            elif k == "d":
                cfg["disk_shape"] = "square" if cfg["disk_shape"] == "circle" else "circle"
                self.notify("disk " + cfg["disk_shape"])
            elif k == "r":
                cfg["rotate"] = not cfg.get("rotate", True)
                self.notify("rotate " + ("on" if cfg["rotate"] else "off"))
            elif k == "s":
                cfg["shuffle"] = not cfg.get("shuffle")
                if cfg["shuffle"]:
                    p.cmd("playlist-shuffle")
                else:
                    p.cmd("playlist-unshuffle")
                self.notify("shuffle " + ("on" if cfg["shuffle"] else "off"))
            elif k == "l":
                order = ["off", "all", "one"]
                cfg["repeat"] = order[(order.index(cfg.get("repeat", "all")) + 1) % 3]
                p.apply_modes()
                self.notify("repeat " + cfg["repeat"])
            elif k == "m":
                cfg["mirror"] = not cfg.get("mirror")
            elif k == "z":
                cfg["zen"] = not cfg.get("zen")
            elif self.screen == 3:
                self.key_settings(k)
        except PlayerError as e:
            self.notify(str(e))
        except Exception as e:                        # never crash the UI
            self.notify(f"error: {e}")

    # ------------------------------------------------------------ prompt --
    def key_prompt(self, k: str):
        pr = self.prompt
        if k == "esc":
            self.prompt = None
        elif k in ("\r", "\n"):
            val = pr["value"].strip()
            self.prompt = None
            if val:
                pr["done"](val)
        elif k in ("\x7f", "\b"):
            pr["value"] = pr["value"][:-1]
        elif k == "\x15":
            pr["value"] = ""
        elif k == "\t":
            pr["value"] = self.complete(pr["value"])
        elif k.isprintable():
            pr["value"] += k

    def complete(self, value: str) -> str:
        try:
            pth = Path(os.path.expanduser(value or "~/"))
            base, frag = (pth, "") if value.endswith("/") else (pth.parent, pth.name)
            cand = sorted(p.name for p in base.iterdir() if p.name.startswith(frag))
            if len(cand) == 1:
                out = base / cand[0]
                return str(out) + ("/" if out.is_dir() else "")
            if cand:
                pre = os.path.commonprefix(cand)
                return str(base / pre)
        except Exception:
            pass
        return value

    def ask(self, label: str, done, value: str = ""):
        self.prompt = {"label": label, "value": value, "done": done}

    # ---------------------------------------------------------- settings --
    def settings_items(self):
        c = self.cfg
        th = themes.get(c["theme"])
        return [
            ("add_folder", "\u30d5\u30a9\u30eb\u30c0  Add music folder", "\u21b5 enter path"),
            ("del_folder", "       Remove a folder", f"{len(c['folders'])} added"),
            ("rescan", "       Rescan library", "\u21b5"),
            ("add_image", "\u30a4\u30e1\u30fc\u30b8  Add image / folder", "\u21b5 enter path"),
            ("clear_images", "       Clear images", f"{len(config.image_list(c))} loaded"),
            ("image_mode", "       Image switching", c["image_mode"]),
            ("shape", "\u30c7\u30a3\u30b9\u30af  Disk style", c["disk_shape"]),
            ("rotate", "       Rotating effect", "on" if c["rotate"] else "off"),
            ("speed", "       Rotation speed", f"x{c['rotate_speed']:.2f}"),
            ("theme", "\u30ab\u30e9\u30fc  Bar colour theme", f"{th.name} {th.jp}"),
            ("bars", "       Bar count", "auto" if not c["bars"] else str(c["bars"])),
            ("mirror", "       Mirrored bars", "on" if c["mirror"] else "off"),
            ("peaks", "       Peak caps", "on" if c["peaks"] else "off"),
            ("petals", "\u30b5\u30af\u30e9  Petal rain", "on" if c["petals"] else "off"),
            ("pulse", "       Beat pulse disc", "on" if c["pulse"] else "off"),
            ("glow", "       Glow sheen", "on" if c["glow"] else "off"),
            ("grain", "       Vinyl grain", "on" if c["grain"] else "off"),
            ("ascii", "       ASCII-only mode", "on" if c["ascii_only"] else "off"),
            ("zen", "       Zen mode", "on" if c["zen"] else "off"),
            ("shuffle", "\u30d7\u30ec\u30a4  Shuffle", "on" if c["shuffle"] else "off"),
            ("repeat", "       Repeat", c["repeat"]),
            ("volume", "       Volume", str(c["volume"])),
            ("fps", "       Frame rate", str(c["fps"])),
        ]

    def key_settings(self, k: str):
        items = self.settings_items()
        if k == "up":
            self.sel = (self.sel - 1) % len(items)
            return
        if k == "down":
            self.sel = (self.sel + 1) % len(items)
            return
        key = items[self.sel][0]
        d = 1 if k in ("right", "\r", "\n") else (-1 if k == "left" else 0)
        if d == 0:
            return
        c = self.cfg
        enter = k in ("\r", "\n")
        if key == "add_folder" and enter:
            self.ask("music folder", self._do_add_folder, "~/")
        elif key == "del_folder" and enter:
            if c["folders"]:
                gone = c["folders"].pop()
                self.notify("removed " + gone)
                self.reload_library()
        elif key == "rescan" and enter:
            self.reload_library()
        elif key == "add_image" and enter:
            self.ask("image file or folder", self._do_add_image, "~/")
        elif key == "clear_images" and enter:
            c["images"] = []
            self.image = None
            self.notify("images cleared")
        elif key == "image_mode":
            order = ["random", "sequence", "off"]
            c["image_mode"] = order[(order.index(c["image_mode"]) + d) % 3]
        elif key == "shape":
            c["disk_shape"] = "square" if c["disk_shape"] == "circle" else "circle"
        elif key == "rotate":
            c["rotate"] = not c["rotate"]
        elif key == "speed":
            c["rotate_speed"] = round(min(4.0, max(0.1, c["rotate_speed"] + 0.1 * d)), 2)
        elif key == "theme":
            c["theme"] = themes.next_theme(c["theme"], d)
        elif key == "bars":
            c["bars"] = max(0, min(128, c["bars"] + 8 * d))
        elif key in ("mirror", "peaks", "petals", "pulse", "glow", "grain", "zen", "shuffle"):
            c[key] = not c[key]
            if key == "shuffle":
                self.player.cmd("playlist-shuffle" if c[key] else "playlist-unshuffle")
        elif key == "ascii":
            c["ascii_only"] = not c["ascii_only"]
        elif key == "repeat":
            order = ["off", "all", "one"]
            c["repeat"] = order[(order.index(c["repeat"]) + d) % 3]
            self.player.apply_modes()
        elif key == "volume":
            self.player.volume(c["volume"] + 5 * d)
        elif key == "fps":
            c["fps"] = max(6, min(60, c["fps"] + 2 * d))
        config.save(c)

    def _do_add_folder(self, val: str):
        ok, res = config.add_folder(self.cfg, val)
        self.notify(("added " + res) if ok else res)
        if ok:
            config.save(self.cfg)
            self.reload_library()

    def _do_add_image(self, val: str):
        added = config.add_images(self.cfg, [val])
        config.save(self.cfg)
        self.notify(f"{len(added)} image(s) added" if added else "no images found")
        if added and not self.image:
            self.image = added[0]

    def reload_library(self):
        tracks = config.library(self.cfg)
        try:
            if tracks:
                self.player.load_tracks(tracks)
                self.notify(f"{len(tracks)} tracks")
            else:
                self.notify("no audio files found")
        except PlayerError as e:
            self.notify(str(e))

    # --------------------------------------------------------------- draw --
    def draw(self):
        if self.resized:
            self.resized = False
            sys.stdout.write("\x1b[2J")
        self.w, self.h = self.size()
        w, h = self.w, self.h
        th = themes.get(self.cfg["theme"])
        lines: list = []
        zen = bool(self.cfg.get("zen"))
        if not zen:
            lines += self.header(w, th)
        body_h = h - len(lines) - (0 if zen else 3)
        if self.screen == 1:
            body = self.screen_disc(w, body_h, th)
        elif self.screen == 2:
            body = self.screen_viz(w, body_h, th)
        else:
            body = self.screen_settings(w, body_h, th)
        lines += body
        if not zen:
            lines += self.footer(w, th)
        if self.cfg.get("petals") and self.screen != 3:
            lines = self.overlay_petals(lines, w, h, th)
        if self.help:
            lines = self.overlay_help(lines, w, h, th)
        if self.prompt is not None:
            pr = self.prompt
            lines[-1] = clip(fg(th.accent()) + "\u25b6 " + pr["label"] + ": " + RESET +
                             pr["value"] + "\u2588" + "   (tab=complete  esc=cancel)", w)
        out = ["\x1b[H"]
        for i in range(h):
            s = lines[i] if i < len(lines) else ""
            out.append(s + "\x1b[K")
            if i < h - 1:
                out.append("\r\n")
        out.append(RESET)
        sys.stdout.write("".join(out))
        sys.stdout.flush()

    def header(self, w: int, th):
        a, dim = fg(th.accent()), fg(th.dim())
        tabs = []
        for i, (num, name) in enumerate(((1, "\u30c7\u30a3\u30b9\u30af DISC"),
                                         (2, "\u30cf\u30ec\u30c4 VIZ"),
                                         (3, "\u30bb\u30c3\u30c6\u30a4 CONF")), 1):
            sel = self.screen == num
            tabs.append((a + bold(f"[{num} {name}]") if sel else dim + f" {num} {name} ") + RESET)
        title = a + bold("\u25c9 \u30bc\u30c3\u30c8\u30d7\u30ec\u30a4  Z P L A Y") + RESET
        bar = title + "  " + " ".join(tabs)
        top = dim + "\u250c" + "\u2500" * (w - 2) + "\u2510" + RESET
        mid = dim + "\u2502" + RESET + clip(pad(" " + bar, w - 2), w - 2) + dim + "\u2502" + RESET
        bot = dim + "\u2514" + "\u2500" * (w - 2) + "\u2518" + RESET
        return [top, mid, bot]

    def footer(self, w: int, th):
        st = self.status
        a, dim = fg(th.accent()), fg(th.dim())
        pos, dur = st.get("pos", 0.0), st.get("dur", 0.0)
        frac = (pos / dur) if dur else 0.0
        barw = max(10, w - 20)
        fill = int(frac * barw)
        bar = a + "\u2501" * fill + RESET + dim + "\u2501" * max(0, barw - fill - 1) + RESET
        if fill < barw:
            bar = a + "\u2501" * fill + "\u25c9" + RESET + dim + "\u2501" * max(0, barw - fill - 1) + RESET
        prog = f" {mmss(pos)} " + bar + f" {mmss(dur)} "
        msg = self.msg if time.time() - self.msg_at < 3 else ""
        hint = ("space \u25b6\u2016  n/p trk  \u2190\u2192 seek  t theme  i image  "
                "d disk  r spin  s shuf  l loop  1/2/3 tabs  ? help  q quit")
        return [clip(prog, w),
                dim + clip(pad(" " + hint, w), w) + RESET,
                a + clip(pad(" " + msg, w), w) + RESET]

    # --------------------------------------------------------- screen 1 ---
    def screen_disc(self, w: int, h: int, th):
        st = self.status
        lines = []
        title = st.get("title") or "— no track —"
        artist = st.get("artist") or ""
        idx, cnt = st.get("index", -1), st.get("count", 0)
        a, dim = fg(th.accent()), fg(th.dim())
        info_h = 4
        disc_h = max(4, h - info_h)
        dw = min(w - 4, disc_h * 2)
        dh = max(3, min(disc_h, dw // 2))
        dw = dh * 2
        pulse = self.pulse if self.cfg.get("pulse") else 0.0
        rows = disc.render(dw, dh, self.angle if self.cfg.get("rotate") else 0.0,
                           self.image, self.cfg["disk_shape"], th.accent(),
                           pulse=pulse, grain=bool(self.cfg.get("grain")),
                           glow=bool(self.cfg.get("glow")),
                           ascii_only=bool(self.cfg.get("ascii_only")))
        padtop = max(0, (disc_h - dh) // 2)
        left = " " * max(0, (w - dw) // 2)
        lines += [""] * padtop
        for r in rows:
            lines.append(left + r)
        while len(lines) < disc_h:
            lines.append("")
        paused = st.get("paused", True)
        btn_prev, btn_play, btn_next = "<<", ("||" if not paused else "\u25b6 "), ">>"
        buttons = (dim + "\u3010" + RESET + a + btn_prev + RESET + dim + "\u3011  " + RESET +
                   dim + "\u3010" + RESET + a + bold(btn_play) + RESET + dim + "\u3011  " + RESET +
                   dim + "\u3010" + RESET + a + btn_next + RESET + dim + "\u3011" + RESET)
        lines.append(center(a + bold(clip(title, w - 4)) + RESET, w))
        sub = artist if artist else (Path(self.track).parent.name if self.track else "")
        extra = f"  \u2022  {idx + 1}/{cnt}" if cnt else ""
        lines.append(center(dim + clip(sub + extra, w - 4) + RESET, w))
        lines.append(center(buttons, w))
        return lines[:h]

    # --------------------------------------------------------- screen 2 ---
    def screen_viz(self, w: int, h: int, th):
        st = self.status
        a, dim = fg(th.accent()), fg(th.dim())
        head = 2
        gh = max(3, h - head)
        nb = int(self.cfg.get("bars") or 0)
        gap = 1
        maxbars = max(4, (w - 2) // (1 + gap))
        nb = maxbars if nb <= 0 else min(nb, maxbars)
        src = self.levels or [0.0] * spectrum.BANDS
        vals, pks = [], []
        for i in range(nb):
            lo = int(i * len(src) / nb)
            hi = max(lo + 1, int((i + 1) * len(src) / nb))
            vals.append(max(src[lo:hi]))
            pks.append(max(self.peaks[lo:hi]) if self.peaks else 0.0)
        mirror = bool(self.cfg.get("mirror"))
        rows_up = gh // 2 if mirror else gh
        glyphs = ASCII_BLOCKS if self.cfg.get("ascii_only") else BLOCKS
        steps = len(glyphs) - 1
        grid = [[" "] * (nb * (1 + gap)) for _ in range(gh)]
        colors = [[None] * (nb * (1 + gap)) for _ in range(gh)]

        def put(row, col, ch, col_rgb):
            if 0 <= row < gh and 0 <= col < len(grid[0]):
                grid[row][col] = ch
                colors[row][col] = col_rgb

        for i, v in enumerate(vals):
            x = i * (1 + gap)
            total = v * rows_up * steps
            full = int(total // steps)
            rem = int(total % steps)
            for r in range(full):
                t = (r + 1) / max(1, rows_up)
                c = th.color(t, i, nb)
                put(rows_up - 1 - r, x, glyphs[steps], c)
                if mirror:
                    put(rows_up + r, x, glyphs[steps], (c[0] // 2, c[1] // 2, c[2] // 2))
            if rem and full < rows_up:
                t = (full + 1) / max(1, rows_up)
                c = th.color(t, i, nb)
                put(rows_up - 1 - full, x, glyphs[rem], c)
                if mirror:
                    put(rows_up + full, x, glyphs[rem], (c[0] // 2, c[1] // 2, c[2] // 2))
            if self.cfg.get("peaks"):
                pr = int(pks[i] * rows_up)
                if pr > 0:
                    c = th.color(1.0, i, nb)
                    put(rows_up - min(rows_up, pr), x,
                        "-" if self.cfg.get("ascii_only") else "\u2594", c)
        lines = []
        left = " " * max(0, (w - nb * (1 + gap)) // 2)
        for r in range(gh):
            parts, last = [left], None
            for x in range(nb * (1 + gap)):
                ch, c = grid[r][x], colors[r][x]
                if ch == " " or c is None:
                    if last is not None:
                        parts.append(RESET)
                        last = None
                    parts.append(" ")
                    continue
                if c != last:
                    parts.append(f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m")
                    last = c
                parts.append(ch)
            parts.append(RESET)
            lines.append("".join(parts))
        title = st.get("title") or "— no track —"
        state = "\u25b6 PLAY" if st.get("running") and not st.get("paused", True) else "\u2016 PAUSE"
        info = (a + bold(clip(title, max(10, w - 34))) + RESET + dim +
                f"   {state}   \u30ab\u30e9\u30fc:{th.name} {th.jp}" +
                ("   \u5206\u6790\u4e2d\u2026" if (self.track and not self.spec.ready) else "") + RESET)
        return [center(info, w), ""] + lines[:max(0, h - 2)]

    # --------------------------------------------------------- screen 3 ---
    def screen_settings(self, w: int, h: int, th):
        a, dim = fg(th.accent()), fg(th.dim())
        items = self.settings_items()
        lines = [center(a + bold("\u2015\u2015 \u8a2d\u5b9a  SETTINGS \u2015\u2015") + RESET, w), ""]
        view_h = max(4, h - 8)
        start = max(0, min(self.sel - view_h // 2, len(items) - view_h))
        for i in range(start, min(len(items), start + view_h)):
            key, label, value = items[i]
            cursor = a + "\u276f " + RESET if i == self.sel else "  "
            lab = (bold(label) if i == self.sel else label)
            row = f"{cursor}{lab}"
            row = pad(row, max(34, w - 30))
            row += a + str(value) + RESET
            lines.append(clip("  " + row, w))
        lines.append("")
        folders = self.cfg["folders"]
        lines.append(dim + clip("  \u30d5\u30a9\u30eb\u30c0: " +
                                (", ".join(Path(f).name for f in folders) if folders else "none"), w) + RESET)
        lines.append(dim + clip(f"  \u30a4\u30e1\u30fc\u30b8: {len(config.image_list(self.cfg))}"
                                f"   \u66f2: {self.status.get('count', 0)}"
                                f"   config: {config.CONFIG_FILE}", w) + RESET)
        lines.append(dim + clip("  \u2191\u2193 move   \u2190\u2192 change   \u21b5 select/apply", w) + RESET)
        return lines[:h]

    # -------------------------------------------------------- overlays ----
    def overlay_petals(self, lines, w, h, th):
        c = th.accent()
        col = f"\x1b[38;2;{max(60, c[0] // 2)};{max(60, c[1] // 2)};{max(60, c[2] // 2)}m"
        out = list(lines)
        for p in self.petals:
            y, x = int(p["y"]), int(p["x"])
            if 0 <= y < min(len(out), h) and 0 <= x < w:
                s = out[y]
                if vislen(s) == 0:
                    out[y] = " " * x + col + p["c"] + RESET
        return out

    def overlay_help(self, lines, w, h, th):
        a, dim = fg(th.accent()), fg(th.dim())
        text = [
            "\u30d8\u30eb\u30d7  KEYS",
            "",
            "1 / 2 / 3 or Tab   disc / visualiser / settings",
            "space              play \u2022 pause",
            "n / p              next \u2022 previous track",
            "\u2190 \u2192                seek 5s",
            "+ / -              volume",
            "t / T              next / previous colour theme (20)",
            "i                  switch disc image now",
            "d                  disk style circle \u2194 square",
            "r                  rotation on / off",
            "s / l              shuffle / repeat mode",
            "m                  mirrored bars",
            "z                  zen mode (hide chrome)",
            "? / q              this help / quit",
        ]
        bw = min(w - 4, 58)
        top = max(0, (h - len(text) - 2) // 2)
        out = list(lines)
        while len(out) < h:
            out.append("")
        left = " " * max(0, (w - bw) // 2)
        box = [left + dim + "\u250c" + "\u2500" * (bw - 2) + "\u2510" + RESET]
        for t in text:
            box.append(left + dim + "\u2502" + RESET + a + clip(pad(" " + t, bw - 2), bw - 2) + RESET + dim + "\u2502" + RESET)
        box.append(left + dim + "\u2514" + "\u2500" * (bw - 2) + "\u2518" + RESET)
        for i, b in enumerate(box):
            if top + i < h:
                out[top + i] = b
        return out


# ------------------------------------------------------------ first run ---
BANNER = """\
\u256d\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u256e
\u2502   \u25c9  \u30bc\u30c3\u30c8\u30d7\u30ec\u30a4   Z P L A Y   terminal deck   \u2502
\u2570\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u256f"""


def first_run(cfg: dict) -> None:
    """Ask for a music folder the very first time zplay is opened."""
    if cfg.get("folders"):
        return
    print(BANNER)
    print("\n  \u521d\u56de\u8d77\u52d5 / first run \u2014 choose a music folder.")
    print("  (tab completion works, empty input = ~/Music)\n")
    try:
        import readline  # noqa: F401  enables editing + completion

        def _comp(text, state):
            p = os.path.expanduser(text)
            base, frag = os.path.split(p)
            base = base or "."
            try:
                opts = [os.path.join(base, f) + ("/" if os.path.isdir(os.path.join(base, f)) else "")
                        for f in os.listdir(base) if f.startswith(frag)]
            except OSError:
                opts = []
            return opts[state] if state < len(opts) else None

        readline.set_completer_delims(" \t\n")
        readline.parse_and_bind("tab: complete")
        readline.set_completer(_comp)
    except Exception:
        pass
    while True:
        try:
            raw = input("  \u30d5\u30a9\u30eb\u30c0 folder \u276f ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        raw = raw or "~/Music"
        ok, res = config.add_folder(cfg, raw)
        if ok:
            n = len(config.library(cfg))
            config.save(cfg)
            print(f"  \u2713 added {res}  ({n} tracks)")
            more = input("  add another folder? [y/N] ").strip().lower()
            if more.startswith("y"):
                continue
            print("  \u2665 tip: add images later with  zplay add-image ~/pics/cover.jpg\n")
            time.sleep(0.6)
            return
        print("  " + res)


def run(cfg: dict) -> int:
    first_run(cfg)
    if not sys.stdout.isatty():
        print("zplay: needs an interactive terminal", file=sys.stderr)
        return 1
    App(cfg).run()
    return 0
