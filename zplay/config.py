"""zplay configuration + library helpers (stdlib only)."""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

APP = "zplay"
HOME = Path.home()
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / APP
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local" / "share")) / APP
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / APP
CONFIG_FILE = CONFIG_DIR / "config.json"
IMAGE_DIR = DATA_DIR / "images"
SPEC_DIR = CACHE_DIR / "spectrum"
PLAYLIST_FILE = CACHE_DIR / "playlist.m3u"

AUDIO_EXT = {
    ".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wav",
    ".wma", ".aiff", ".aif", ".alac", ".mka", ".mp4",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}

DEFAULTS = {
    "folders": [],
    "images": [],
    "theme": "sakura",
    "disk_shape": "circle",     # circle | square
    "rotate": True,
    "rotate_speed": 1.0,
    "image_mode": "random",     # random | sequence | off
    "shuffle": False,
    "repeat": "all",            # off | one | all
    "volume": 80,
    "fps": 20,
    "bars": 0,                  # 0 = auto (fit width)
    "mirror": False,            # mirrored frequency bars
    "peaks": True,              # falling peak caps
    "petals": True,             # sakura petal rain
    "pulse": True,              # beat reactive disc
    "glow": True,               # sheen / glow highlights
    "grain": True,              # vinyl groove texture
    "ascii_only": False,        # pure-ASCII fallback glyphs
    "zen": False,               # hide chrome
    "disk_size": 0,             # 0 = auto
    "start_screen": 1,
    "seek_step": 5,
}


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, DATA_DIR, CACHE_DIR, IMAGE_DIR, SPEC_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    ensure_dirs()
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text("utf-8")))
        except Exception:
            pass
    # keep unknown keys out, keep defaults for missing
    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)
    return cfg


def save(cfg: dict) -> None:
    ensure_dirs()
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    tmp.replace(CONFIG_FILE)


def expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()


# ---------------------------------------------------------------- library ---
def scan_folder(folder: Path) -> list[str]:
    out: list[str] = []
    try:
        for root, dirs, files in os.walk(folder, followlinks=True):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if Path(f).suffix.lower() in AUDIO_EXT:
                    out.append(os.path.join(root, f))
    except Exception:
        pass
    return out


def library(cfg: dict) -> list[str]:
    """All tracks from every configured folder, sorted, de-duplicated."""
    seen: set[str] = set()
    out: list[str] = []
    for folder in cfg.get("folders", []):
        for t in sorted(scan_folder(Path(folder))):
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


def image_list(cfg: dict) -> list[str]:
    return [p for p in cfg.get("images", []) if os.path.exists(p)]


def pick_image(cfg: dict, current: str | None = None) -> str | None:
    imgs = image_list(cfg)
    if not imgs or cfg.get("image_mode") == "off":
        return None
    if cfg.get("image_mode") == "sequence":
        if current in imgs:
            return imgs[(imgs.index(current) + 1) % len(imgs)]
        return imgs[0]
    if len(imgs) > 1 and current in imgs:
        choices = [i for i in imgs if i != current]
        return random.choice(choices)
    return random.choice(imgs)


def add_images(cfg: dict, paths, copy: bool = True) -> list[str]:
    """Register image files (or every image inside a folder)."""
    ensure_dirs()
    added: list[str] = []
    files: list[Path] = []
    for raw in paths:
        p = expand(raw)
        if p.is_dir():
            for f in sorted(p.iterdir()):
                if f.suffix.lower() in IMAGE_EXT:
                    files.append(f)
        elif p.is_file() and p.suffix.lower() in IMAGE_EXT:
            files.append(p)
    for f in files:
        dest = f
        if copy:
            dest = IMAGE_DIR / f.name
            n = 1
            while dest.exists() and dest.stat().st_size != f.stat().st_size:
                dest = IMAGE_DIR / f"{f.stem}-{n}{f.suffix}"
                n += 1
            if not dest.exists():
                dest.write_bytes(f.read_bytes())
        s = str(dest)
        if s not in cfg["images"]:
            cfg["images"].append(s)
            added.append(s)
    return added


def add_folder(cfg: dict, raw: str) -> tuple[bool, str]:
    p = expand(raw)
    if not p.is_dir():
        return False, f"not a directory: {p}"
    s = str(p)
    if s in cfg["folders"]:
        return False, f"already added: {s}"
    cfg["folders"].append(s)
    return True, s
