"""Bildberechnung: jede Einstellung hat eine feste Kamera (keine künstlichen Fahrten); Hintergrund einmal je
Einstellung, Figuren je Bild. 2× Supersampling → saubere Kanten. Ausgabe direkt in FFmpeg (1080×1920, 30 fps)."""
from __future__ import annotations

import subprocess
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image

from toon.tiere import figur_fuer
from toon.geo import Pen
from toon.orte import BODEN_Y, ORTE

W, H, SS = 1080, 1920, 2
_TL = None
_BG: dict = {}
_FIG: dict = {}
FADE = 0.4


def _init(tl):
    global _TL, _FIG
    _TL = tl
    _FIG = {n: figur_fuer(d) for n, d in tl["figuren"].items()}


def _einstellung(t: float):
    for i, e in enumerate(_TL["einstellungen"]):
        if e.start <= t < e.ende or i == len(_TL["einstellungen"]) - 1:
            return i, e
    return 0, _TL["einstellungen"][0]


def _hintergrund(e):
    if e.nr not in _BG:
        img = Image.new("RGB", (W * SS, H * SS), "white")
        pen = Pen(img, e.view(SS))
        ORTE[e.ort](pen, e.tageszeit)
        _BG[e.nr] = (img, pen.boden)
    return _BG[e.nr]


def _partner(e, name: str):
    """Nächste andere Figur auf der Bühne (für Zuwendung im Gespräch)."""
    def fn(t):
        me = _TL["spuren"][name].x(t)
        xs = [_TL["spuren"][o].x(t) for o in e.figuren if o != name]
        xs = [x for x in xs if -150 < x < 1590]
        return min(xs, key=lambda x: abs(x - me)) if xs else None
    return fn


def _blickziel(e, name: str, t: float):
    for o in e.figuren:                       # wer gerade spricht, wird angesehen
        if o != name and _TL["spuren"][o].spricht(t):
            return _TL["spuren"][o].x(t)
    return _partner(e, name)(t)


def bild(f: int, fps: int = 30) -> bytes:
    t = f / fps
    i, e = _einstellung(t)
    bg, boden = _hintergrund(e)
    img = bg.copy()
    pen = Pen(img, e.view(SS))
    pen.boden = boden
    for name in sorted(e.figuren, key=lambda n: _TL["spuren"][n].x(t)):
        sp = _TL["spuren"][name]
        if not -320 < sp.x(t) < 1760:
            continue
        z = sp.zustand(t, BODEN_Y, _partner(e, name), _blickziel(e, name, t))
        _FIG[name].zeichne(pen, z)
    out = img.reduce(SS)
    # Blenden (Abblende / Überblendung über Schwarz)
    k = 1.0
    if e.uebergang in ("abblende", "ueberblendung"):
        k = min(k, (t - e.start) / FADE)
    nxt = _TL["einstellungen"][i + 1] if i + 1 < len(_TL["einstellungen"]) else None
    if nxt is None or nxt.uebergang in ("abblende", "ueberblendung"):
        k = min(k, (e.ende - t) / FADE)
    if k < 1:
        arr = (np.asarray(out, dtype=np.float32) * max(0.0, k)).astype(np.uint8)
        return arr.tobytes()
    return out.tobytes()


def standbild(tl, f: int, ziel: Path, fps: int = 30) -> Path:
    _init(tl)
    Image.frombytes("RGB", (W, H), bild(f, fps)).save(ziel)
    return ziel


def video(tl, ton: Path, ass: Path | None, ziel: Path, fps: int = 30, prozesse: int = 2, crf: int = 17) -> Path:
    n = int(round(tl["gesamt"] * fps))
    vf = [f"ass={ass}"] if ass else []
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
           "-i", "-", "-i", str(ton)] + (["-vf", ",".join(vf)] if vf else []) + [
           "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", "-t", f"{tl['gesamt']:.3f}", str(ziel)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(prozesse, initializer=_init, initargs=(tl,)) as pool:
        for frame in pool.imap(bild, range(n), chunksize=6):
            proc.stdin.write(frame)
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("FFmpeg-Fehler beim Kodieren")
    return ziel
