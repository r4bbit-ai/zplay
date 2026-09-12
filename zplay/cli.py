"""zplay command line interface. `zplay` with no args opens the TUI."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import config, disc, spectrum, themes
from .player import Player, PlayerError

VERSION = "1.0.0"

HELP = """\
\u25c9 \u30bc\u30c3\u30c8\u30d7\u30ec\u30a4  zplay {v} \u2014 retro terminal music deck

usage: zplay [command] [args]

  (no command)            open the player UI

 playback
  play [query|index]      play / resume, or play first match of query
  pause | resume | toggle
  next | prev | stop
  seek <+/-secs>          seek relative
  volume [0-130]          get / set volume
  shuffle [on|off]
  repeat [off|all|one]
  status                  what is playing now
  list [n]                list library tracks (default 30)
  search <query>          find tracks in the library

 library
  add-folder <path>       add a music directory
  folders                 list music directories
  remove-folder <path|#>  remove a directory
  scan                    rescan folders and reload the queue

 disc images
  add-image <path...>     add image files or a whole folder (copied in)
  images                  list images
  remove-image <path|#>
  clear-images
  image-mode [random|sequence|off]

 look & feel
  theme [name]            set bar colour theme (20 available)
  themes                  list all themes
  disk [circle|square]
  rotate [on|off]
  speed [0.1-4.0]
  bars [n|auto]
  set <key> <value>       set any config key
  config                  print current config
  doctor                  check dependencies
  version | help

keys inside the UI:  1/2/3 tabs \u00b7 space play/pause \u00b7 n/p track \u00b7 \u2190\u2192 seek
                     t theme \u00b7 i image \u00b7 d disk \u00b7 r spin \u00b7 s shuffle \u00b7 l loop \u00b7 ? help
"""


def out(*a):
    print(*a)


def _match(cfg, query: str):
    q = query.lower()
    lib = config.library(cfg)
    exact = [t for t in lib if q in Path(t).stem.lower()]
    return lib, (exact or [t for t in lib if q in t.lower()])


def cmd_status(p: Player):
    st = p.status()
    if not st.get("running"):
        out("zplay: not running")
        return 1
    icon = "\u2016" if st["paused"] else "\u25b6"
    from .ui import mmss
    out(f"{icon} {st['title']}")
    if st.get("artist"):
        out(f"  {st['artist']}")
    out(f"  {mmss(st['pos'])} / {mmss(st['dur'])}   "
        f"track {int(st['index']) + 1}/{st['count']}   vol {st['volume']}")
    if st.get("path"):
        out(f"  {st['path']}")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = config.load()
    if not argv:
        from . import ui
        return ui.run(cfg)

    cmd, args = argv[0], argv[1:]
    p = Player(cfg)

    def save():
        config.save(cfg)

    try:
        if cmd in ("help", "-h", "--help"):
            out(HELP.format(v=VERSION))
        elif cmd in ("version", "-v", "--version"):
            out(f"zplay {VERSION}")

        # ----------------------------------------------------- playback --
        elif cmd == "play":
            if args:
                q = " ".join(args)
                lib, hits = _match(cfg, q)
                if q.isdigit() and 0 < int(q) <= len(lib):
                    p.load_tracks(lib, int(q) - 1)
                    out("\u25b6 " + Path(lib[int(q) - 1]).name)
                elif hits:
                    p.load_tracks(lib, lib.index(hits[0]))
                    out("\u25b6 " + Path(hits[0]).name)
                else:
                    out(f"no match for {q!r}")
                    return 1
            else:
                p.play()
                cmd_status(p)
        elif cmd == "pause":
            p.pause()
        elif cmd in ("resume",):
            p.play()
        elif cmd in ("toggle", "pp"):
            p.toggle()
        elif cmd == "next":
            p.next()
            cmd_status(p)
        elif cmd in ("prev", "previous"):
            p.prev()
            cmd_status(p)
        elif cmd == "stop":
            p.stop()
            out("stopped")
        elif cmd == "seek":
            p.seek(float(args[0]) if args else 5)
        elif cmd in ("volume", "vol"):
            if args:
                out(f"volume {p.volume(int(args[0]))}")
                save()
            else:
                out(f"volume {p.status().get('volume', cfg['volume'])}")
        elif cmd == "shuffle":
            cfg["shuffle"] = (args[0].lower() in ("on", "true", "1", "yes")
                              if args else not cfg["shuffle"])
            save()
            if p.alive():
                p.cmd("playlist-shuffle" if cfg["shuffle"] else "playlist-unshuffle")
            out("shuffle " + ("on" if cfg["shuffle"] else "off"))
        elif cmd == "repeat":
            if args:
                v = args[0].lower()
                if v not in ("off", "all", "one"):
                    out("repeat: off | all | one")
                    return 1
                cfg["repeat"] = v
                save()
                if p.alive():
                    p.apply_modes()
            out("repeat " + cfg["repeat"])
        elif cmd == "status":
            return cmd_status(p)
        elif cmd in ("list", "ls"):
            lib = config.library(cfg)
            n = int(args[0]) if args and args[0].isdigit() else 30
            for i, t in enumerate(lib[:n], 1):
                out(f"{i:4d}. {Path(t).name}")
            if len(lib) > n:
                out(f"     \u2026 {len(lib) - n} more of {len(lib)}")
        elif cmd == "search":
            _, hits = _match(cfg, " ".join(args))
            for t in hits[:40]:
                out("  " + t)
            if not hits:
                out("no match")

        # ------------------------------------------------------ library --
        elif cmd in ("add-folder", "addfolder", "folder"):
            if not args:
                out("usage: zplay add-folder <path>")
                return 1
            ok, res = config.add_folder(cfg, args[0])
            if not ok:
                out(res)
                return 1
            save()
            out(f"\u2713 {res}  ({len(config.library(cfg))} tracks total)")
        elif cmd == "folders":
            for i, f in enumerate(cfg["folders"], 1):
                out(f"{i:3d}. {f}  ({len(config.scan_folder(Path(f)))} tracks)")
            if not cfg["folders"]:
                out("no folders yet \u2014 zplay add-folder ~/Music")
        elif cmd in ("remove-folder", "rmfolder"):
            if not args:
                return 1
            a = args[0]
            if a.isdigit() and 0 < int(a) <= len(cfg["folders"]):
                out("removed " + cfg["folders"].pop(int(a) - 1))
            else:
                tgt = str(config.expand(a))
                if tgt in cfg["folders"]:
                    cfg["folders"].remove(tgt)
                    out("removed " + tgt)
                else:
                    out("not found")
                    return 1
            save()
        elif cmd in ("scan", "rescan"):
            lib = config.library(cfg)
            out(f"{len(lib)} tracks")
            if p.alive():
                p.load_tracks(lib)

        # ------------------------------------------------------- images --
        elif cmd in ("add-image", "addimage", "add-images"):
            if not args:
                out("usage: zplay add-image <file|folder> ...")
                return 1
            added = config.add_images(cfg, args)
            save()
            for a in added:
                out("\u2713 " + a)
            out(f"{len(added)} image(s) added, {len(config.image_list(cfg))} total")
        elif cmd == "images":
            imgs = config.image_list(cfg)
            for i, im in enumerate(imgs, 1):
                out(f"{i:3d}. {im}")
            if not imgs:
                out("no images \u2014 the disc shows the skeleton label")
        elif cmd in ("remove-image", "rmimage"):
            a = args[0] if args else ""
            imgs = cfg["images"]
            if a.isdigit() and 0 < int(a) <= len(imgs):
                out("removed " + imgs.pop(int(a) - 1))
            elif a in imgs:
                imgs.remove(a)
                out("removed " + a)
            else:
                out("not found")
                return 1
            save()
        elif cmd == "clear-images":
            cfg["images"] = []
            save()
            out("images cleared")
        elif cmd == "image-mode":
            if args:
                if args[0] not in ("random", "sequence", "off"):
                    out("image-mode: random | sequence | off")
                    return 1
                cfg["image_mode"] = args[0]
                save()
            out("image-mode " + cfg["image_mode"])

        # ---------------------------------------------------- look/feel --
        elif cmd == "theme":
            if args:
                name = args[0].lower()
                if name not in themes.BY_NAME:
                    out("unknown theme. try: zplay themes")
                    return 1
                cfg["theme"] = name
                save()
            out("theme " + cfg["theme"])
        elif cmd == "themes":
            for t in themes.THEMES:
                sw = "".join(f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m\u2588\u2588"
                             for c in [t.color(i / 7.0, i, 8) for i in range(8)])
                mark = "\u25c9" if t.name == cfg["theme"] else " "
                out(f" {mark} {t.name:<9} {t.jp:<7} {sw}\x1b[0m")
        elif cmd in ("disk", "disc"):
            if args:
                if args[0] not in ("circle", "square"):
                    out("disk: circle | square")
                    return 1
                cfg["disk_shape"] = args[0]
                save()
            out("disk " + cfg["disk_shape"])
        elif cmd == "rotate":
            if args:
                cfg["rotate"] = args[0].lower() in ("on", "true", "1", "yes")
                save()
            out("rotate " + ("on" if cfg["rotate"] else "off"))
        elif cmd == "speed":
            if args:
                cfg["rotate_speed"] = max(0.1, min(4.0, float(args[0])))
                save()
            out(f"speed x{cfg['rotate_speed']:.2f}")
        elif cmd == "bars":
            if args:
                cfg["bars"] = 0 if args[0] == "auto" else max(0, min(128, int(args[0])))
                save()
            out("bars " + ("auto" if not cfg["bars"] else str(cfg["bars"])))
        elif cmd == "set":
            if len(args) < 2 or args[0] not in config.DEFAULTS:
                out("keys: " + ", ".join(sorted(config.DEFAULTS)))
                return 1
            k, raw = args[0], " ".join(args[1:])
            cur = config.DEFAULTS[k]
            if isinstance(cur, bool):
                val = raw.lower() in ("on", "true", "1", "yes")
            elif isinstance(cur, int):
                val = int(float(raw))
            elif isinstance(cur, float):
                val = float(raw)
            else:
                val = raw
            cfg[k] = val
            save()
            out(f"{k} = {val}")
        elif cmd == "config":
            import json
            out(json.dumps(cfg, indent=2, ensure_ascii=False))
            out("# " + str(config.CONFIG_FILE))
        elif cmd == "doctor":
            ok = True
            for tool, why, hard in (("mpv", "audio playback", True),
                                    ("ffmpeg", "spectrum analysis", False)):
                found = shutil.which(tool)
                ok = ok and (found or not hard)
                out(f"  [{'\u2713' if found else '\u2717'}] {tool:<8} {why}"
                    + ("" if found else f"   \u2192 sudo pacman -S {tool}"))
            out(f"  [{'\u2713' if disc.has_pil() else '\u2717'}] Pillow   disc images"
                + ("" if disc.has_pil() else "   \u2192 sudo pacman -S python-pillow"))
            out(f"  [{'\u2713' if spectrum.has_numpy() else '\u2717'}] numpy    real FFT bars"
                + ("" if spectrum.has_numpy() else "   \u2192 sudo pacman -S python-numpy (optional)"))
            out(f"  tracks: {len(config.library(cfg))}   images: {len(config.image_list(cfg))}")
            out(f"  socket: {p.path}   running: {p.alive()}")
            return 0 if ok else 1
        else:
            out(f"unknown command: {cmd}\n")
            out(HELP.format(v=VERSION))
            return 1
    except PlayerError as e:
        out(f"zplay: {e}")
        return 1
    except (ValueError, IndexError) as e:
        out(f"zplay: bad arguments ({e})")
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
