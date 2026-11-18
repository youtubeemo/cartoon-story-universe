"""Vektor-Grundformen und Zeichenstift (Pillow, 2× Supersampling für saubere Kanten).

Alles wird als Polygon in Bühnenkoordinaten beschrieben und erst beim Zeichnen mit der Kameramatrix
transformiert – dadurch bleibt jede Einstellungsgröße (totale … gross) gestochen scharf.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import ImageDraw


def M(tx: float = 0, ty: float = 0, rot: float = 0, sx: float = 1, sy: float = 1) -> np.ndarray:
    """Affine Matrix: erst skalieren, dann drehen (Grad), dann verschieben."""
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    return np.array([[c * sx, -s * sy, tx], [s * sx, c * sy, ty], [0, 0, 1]], dtype=float)


def apply(m: np.ndarray, pts) -> np.ndarray:
    p = np.asarray(pts, dtype=float)
    return p @ m[:2, :2].T + m[:2, 2]


def ellipse(cx: float, cy: float, rx: float, ry: float, n: int = 56, a0: float = 0, a1: float = 360) -> np.ndarray:
    t = np.radians(np.linspace(a0, a1, n, endpoint=(a1 - a0) < 360))
    return np.stack([cx + rx * np.cos(t), cy + ry * np.sin(t)], axis=1)


def capsule(x0: float, y0: float, x1: float, y1: float, r0: float, r1: float | None = None, n: int = 14) -> np.ndarray:
    """Abgerundetes Glied von (x0,y0) nach (x1,y1), Radius r0 → r1."""
    r1 = r0 if r1 is None else r1
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    a = ellipse(x1, y1, r1, r1, n, ang - 90, ang + 90)
    b = ellipse(x0, y0, r0, r0, n, ang + 90, ang + 270)
    return np.vstack([a, b])


def rrect(x: float, y: float, w: float, h: float, r: float, n: int = 8) -> np.ndarray:
    r = min(r, w / 2, h / 2)
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        pts.append(ellipse(cx, cy, r, r, n, a0, a0 + 90))
    return np.vstack(pts)


def bezier(p0, p1, p2, p3=None, n: int = 20) -> np.ndarray:
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2 = map(np.asarray, (p0, p1, p2))
    if p3 is None:
        return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2
    p3 = np.asarray(p3)
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3


def rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a: str | tuple, b: str | tuple, f: float) -> tuple:
    a = rgb(a) if isinstance(a, str) else a
    b = rgb(b) if isinstance(b, str) else b
    return tuple(int(round(a[i] + (b[i] - a[i]) * f)) for i in range(3))


class Pen:
    """Zeichnet transformierte Polygone mit einheitlicher Kontur (Stilbibel: gleiche Linienstärke überall)."""

    def __init__(self, img, view: np.ndarray, line: float = 5.0, ink: str = "#1B1B1F", tint=None):
        self.d = ImageDraw.Draw(img)
        self.view = view
        self.scale = math.sqrt(abs(np.linalg.det(view[:2, :2])))
        self.lw = max(1, int(round(line * self.scale)))
        self.ink = rgb(ink)
        self.tint = tint          # (farbe, stärke) für Tageszeit
        self.boden = None         # Bodenfarbe des Ortes (für Schatten)

    def col(self, c):
        c = rgb(c) if isinstance(c, str) else c
        return mix(c, self.tint[0], self.tint[1]) if self.tint else c

    def poly(self, m, pts, fill, outline: bool = True, lw: float | None = None) -> None:
        p = apply(self.view @ m, pts)
        w = self.lw if lw is None else max(1, int(round(lw * self.scale)))
        xy = [tuple(q) for q in p]
        if fill is not None:
            self.d.polygon(xy, fill=self.col(fill))
        if outline:
            self.d.line(xy + [xy[0]], fill=self.ink, width=w, joint="curve")

    def line(self, m, pts, color=None, lw: float | None = None) -> None:
        p = apply(self.view @ m, pts)
        w = self.lw if lw is None else max(1, int(round(lw * self.scale)))
        self.d.line([tuple(q) for q in p], fill=self.ink if color is None else self.col(color), width=w, joint="curve")

    def dot(self, m, x, y, r, color) -> None:
        self.poly(m, ellipse(x, y, r, r, 16), color, outline=False)
