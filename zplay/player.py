"""Playback backend: a detached mpv daemon driven over a JSON IPC socket.

mpv keeps running between `zplay` invocations, so every CLI subcommand
(`zplay next`, `zplay pause`, ...) talks to the same player.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

from . import config


def socket_path() -> str:
    env = os.environ.get("ZPLAY_SOCKET")
    if env:
        return env
    run = os.environ.get("XDG_RUNTIME_DIR")
    if run and os.path.isdir(run):
        return os.path.join(run, "zplay.sock")
    return f"/tmp/zplay-{os.getuid()}.sock"


class PlayerError(RuntimeError):
    pass


class Player:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.path = socket_path()
        self._sock: socket.socket | None = None
        self._buf = b""
        self._rid = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------ socket --
    def _connect(self) -> socket.socket | None:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect(self.path)
            return s
        except OSError:
            return None

    def alive(self) -> bool:
        if self._sock:
            return True
        s = self._connect()
        if s:
            self._sock = s
            return True
        return False

    def start(self, quiet: bool = True) -> None:
        """Make sure an mpv daemon is running."""
        if self.alive():
            return
        if not shutil.which("mpv"):
            raise PlayerError("mpv not found. install it:  sudo pacman -S mpv")
        try:
            os.unlink(self.path)
        except OSError:
            pass
        cmd = [
            "mpv", "--idle=yes", "--no-video", "--no-terminal", "--really-quiet",
            "--audio-display=no", "--keep-open=no", "--gapless-audio=yes",
            f"--volume={int(self.cfg.get('volume', 80))}",
            f"--input-ipc-server={self.path}",
        ]
        with open(os.devnull, "wb") as null:
            subprocess.Popen(cmd, stdout=null, stderr=null, stdin=null,
                             start_new_session=True)
        for _ in range(60):
            time.sleep(0.05)
            if self.alive():
                break
        else:
            raise PlayerError("could not start mpv")
        self.apply_modes()

    def _send(self, payload: dict) -> dict | None:
        if not self.alive() or self._sock is None:
            return None
        try:
            self._sock.sendall((json.dumps(payload) + "\n").encode())
            deadline = time.time() + 2.0
            while time.time() < deadline:
                while b"\n" in self._buf:
                    line, self._buf = self._buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8", "replace"))
                    except Exception:
                        continue
                    if msg.get("request_id") == payload.get("request_id"):
                        return msg
                chunk = self._sock.recv(65536)
                if not chunk:
                    break
                self._buf += chunk
        except OSError:
            pass
        self._sock = None
        self._buf = b""
        return None

    def cmd(self, *args):
        with self._lock:
            self._rid += 1
            res = self._send({"command": list(args), "request_id": self._rid})
        return res.get("data") if res else None

    def get(self, prop, default=None):
        with self._lock:
            self._rid += 1
            res = self._send({"command": ["get_property", prop],
                              "request_id": self._rid})
        if res and res.get("error") == "success":
            return res.get("data")
        return default

    def set(self, prop, value):
        return self.cmd("set_property", prop, value)

    # ---------------------------------------------------------- playlist --
    def load_tracks(self, tracks: list, start: int = 0) -> None:
        if not tracks:
            raise PlayerError("no tracks found - add a folder first (zplay add-folder PATH)")
        self.start()
        config.ensure_dirs()
        with open(config.PLAYLIST_FILE, "w", encoding="utf-8") as fh:
            fh.write("#EXTM3U\n")
            for t in tracks:
                fh.write(t + "\n")
        self.cmd("loadlist", str(config.PLAYLIST_FILE), "replace")
        self.apply_modes()
        if self.cfg.get("shuffle"):
            self.cmd("playlist-shuffle")
        if start:
            self.set("playlist-pos", int(start))
        self.set("pause", False)

    def ensure_loaded(self) -> None:
        """Load the library into mpv if nothing is queued yet."""
        self.start()
        count = self.get("playlist-count", 0) or 0
        if count == 0:
            self.load_tracks(config.library(self.cfg))

    def apply_modes(self) -> None:
        rep = self.cfg.get("repeat", "all")
        self.set("loop-playlist", "inf" if rep == "all" else "no")
        self.set("loop-file", "inf" if rep == "one" else "no")
        self.set("volume", int(self.cfg.get("volume", 80)))

    # ---------------------------------------------------------- controls --
    def play(self):
        self.ensure_loaded()
        self.set("pause", False)

    def pause(self):
        self.set("pause", True)

    def toggle(self):
        self.ensure_loaded()
        self.cmd("cycle", "pause")

    def next(self):
        self.ensure_loaded()
        self.cmd("playlist-next", "force")
        self.set("pause", False)

    def prev(self):
        self.ensure_loaded()
        if (self.get("time-pos", 0) or 0) > 3:
            self.cmd("seek", 0, "absolute")
        else:
            self.cmd("playlist-prev", "force")
        self.set("pause", False)

    def seek(self, secs: float):
        self.cmd("seek", secs, "relative")

    def volume(self, v: int):
        v = max(0, min(130, int(v)))
        self.cfg["volume"] = v
        self.set("volume", v)
        return v

    def stop(self):
        if self.alive():
            self.cmd("quit")
        self._sock = None

    def jump(self, index: int):
        self.ensure_loaded()
        self.set("playlist-pos", int(index))
        self.set("pause", False)

    # ------------------------------------------------------------ status --
    def status(self) -> dict:
        if not self.alive():
            return {"running": False}
        path = self.get("path")
        return {
            "running": True,
            "path": path,
            "title": self.get("media-title") or (Path(path).stem if path else None),
            "artist": (self.get("metadata/by-key/Artist")
                       or self.get("metadata/by-key/ARTIST") or ""),
            "album": (self.get("metadata/by-key/Album")
                      or self.get("metadata/by-key/ALBUM") or ""),
            "pos": self.get("time-pos", 0.0) or 0.0,
            "dur": self.get("duration", 0.0) or 0.0,
            "paused": bool(self.get("pause", True)),
            "index": self.get("playlist-pos", -1),
            "count": self.get("playlist-count", 0) or 0,
            "volume": int(self.get("volume", self.cfg.get("volume", 80)) or 0),
        }
