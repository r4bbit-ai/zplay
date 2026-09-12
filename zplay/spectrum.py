"""Offline spectrum analysis -> tiny cached band-energy timeline.

One ffmpeg pass per track (background thread), results cached under
~/.cache/zplay/spectrum. Uses numpy when available (real FFT), otherwise a
fast C-level peak-envelope fallback, so the player still animates without
any third party module.
"""
from __future__ import annotations

import hashlib
import math
import os
import shutil
import subprocess
import threading
from array import array
from pathlib import Path

from . import config

SR = 22050
FPS = 20
BANDS = 64
WIN = 1024

try:                       # optional, big speed/quality win
    import numpy as _np
except Exception:          # pragma: no cover
    _np = None


def has_numpy() -> bool:
    return _np is not None


def _cache_file(path: str) -> Path:
    try:
        st = os.stat(path)
        key = f"{path}:{st.st_size}:{int(st.st_mtime)}:{BANDS}:{FPS}:{1 if _np else 0}"
    except OSError:
        key = path
    h = hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:20]
    return config.SPEC_DIR / f"{h}.bin"


def _decode(path: str) -> bytes:
    if not shutil.which("ffmpeg"):
        return b""
    try:
        p = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-nostdin", "-i", path,
             "-vn", "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=300)
        return p.stdout
    except Exception:
        return b""


def _band_edges() -> list:
    lo, hi = 30.0, SR / 2.0
    edges = []
    for i in range(BANDS + 1):
        f = lo * (hi / lo) ** (i / BANDS)
        edges.append(int(f * WIN / SR))
    return edges


def _analyze_numpy(pcm: bytes) -> bytes:
    x = _np.frombuffer(pcm, dtype=_np.int16).astype(_np.float32) / 32768.0
    hop = SR // FPS
    n = max(0, (len(x) - WIN) // hop)
    if n <= 0:
        return b""
    win = _np.hanning(WIN).astype(_np.float32)
    idx = _np.arange(WIN)[None, :] + hop * _np.arange(n)[:, None]
    frames = x[idx] * win
    mag = _np.abs(_np.fft.rfft(frames, axis=1))
    edges = _band_edges()
    out = _np.zeros((n, BANDS), dtype=_np.float32)
    for b in range(BANDS):
        a, c = edges[b], max(edges[b] + 1, edges[b + 1])
        c = min(c, mag.shape[1])
        if a >= c:
            a = max(0, c - 1)
        out[:, b] = mag[:, a:c].mean(axis=1)
    out = _np.log10(1.0 + 90.0 * out)
    # gentle high frequency lift so treble bars stay visible
    tilt = _np.linspace(1.0, 1.9, BANDS, dtype=_np.float32)
    out *= tilt
    peak = float(_np.percentile(out, 99.5)) or 1.0
    out = _np.clip(out / peak, 0, 1) * 255.0
    return out.astype(_np.uint8).tobytes()


def _analyze_fallback(pcm: bytes) -> bytes:
    """No numpy: peak envelope + fixed spectral shape (cheap, C-level ops)."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    hop = SR // FPS
    n = len(samples) // hop
    if n <= 0:
        return b""
    mv = memoryview(samples)
    env = []
    for i in range(n):
        chunk = mv[i * hop:(i + 1) * hop]
        if not len(chunk):
            env.append(0.0)
            continue
        pk = max(max(chunk), -min(chunk)) / 32768.0
        env.append(pk)
    top = max(env) or 1.0
    shape = [math.exp(-((b / BANDS) ** 1.35) * 2.4) for b in range(BANDS)]
    out = bytearray(n * BANDS)
    seed = 1234567
    slow = 0.0
    for i in range(n):
        e = env[i] / top
        slow = slow * 0.7 + e * 0.3
        for b in range(BANDS):
            seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
            jitter = 0.55 + 0.45 * ((seed >> 12) & 1023) / 1023.0
            v = e * shape[b] * jitter + slow * 0.25 * shape[b]
            out[i * BANDS + b] = min(255, int(v * 300))
    return bytes(out)


def analyze(path: str) -> Path | None:
    """Analyze (or reuse cache) and return the cache file path."""
    config.ensure_dirs()
    cf = _cache_file(path)
    if cf.exists() and cf.stat().st_size > 0:
        return cf
    pcm = _decode(path)
    if not pcm:
        return None
    data = _analyze_numpy(pcm) if _np is not None else _analyze_fallback(pcm)
    if not data:
        return None
    tmp = cf.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(cf)
    return cf


class Spectrum:
    """Holds the analysed timeline for the current track."""

    def __init__(self):
        self.path: str | None = None
        self.data: bytes = b""
        self.frames = 0
        self.ready = False
        self._thread: threading.Thread | None = None

    def load(self, path: str | None) -> None:
        if path == self.path:
            return
        self.path = path
        self.data = b""
        self.frames = 0
        self.ready = False
        if not path:
            return
        t = threading.Thread(target=self._work, args=(path,), daemon=True)
        self._thread = t
        t.start()

    def _work(self, path: str) -> None:
        cf = analyze(path)
        if cf and path == self.path:
            try:
                data = cf.read_bytes()
            except OSError:
                return
            if path == self.path:
                self.data = data
                self.frames = len(data) // BANDS
                self.ready = True

    def at(self, seconds: float) -> list:
        """Band levels 0..1 at a playback position (empty when not ready)."""
        if not self.ready or self.frames == 0:
            return []
        i = int(seconds * FPS)
        if i < 0:
            i = 0
        if i >= self.frames:
            i = self.frames - 1
        raw = self.data[i * BANDS:(i + 1) * BANDS]
        return [b / 255.0 for b in raw]
