"""Wiederverwendbare Vektor-Hintergründe. Bühne 1440 × 2560 (totale); Boden vorne ab y ≈ 1700, Füße ≈ 2000.

Jeder Ort ist eine Funktion; die Tageszeit färbt alles einheitlich um (morgen/tag/abend/nacht).
Vektor statt Bild: jede Einstellungsgröße bleibt scharf, Orte kosten nichts und sehen in jeder Folge gleich aus.
"""
from __future__ import annotations

import numpy as np

from toon.geo import M, ellipse, mix, rrect

BUEHNE_B, BUEHNE_H = 1440, 2560
BODEN_Y = 2000
TINT = {"morgen": ("#FFE2B8", 0.10), "tag": None, "abend": ("#FF9A4D", 0.22), "nacht": ("#1D2B57", 0.45)}
HIMMEL = {"morgen": ("#FFD9A8", "#BFE3F0"), "tag": ("#9FD6F2", "#D9F0FA"), "abend": ("#FF9F68", "#FFD08A"),
          "nacht": ("#1A2240", "#2E3C66")}
I = M()


def _himmel(pen, x, y, w, h, zeit):
    a, b = HIMMEL[zeit]
    tint, pen.tint = pen.tint, None
    for k in range(32):
        pen.poly(I, rrect(x, y + h * k / 32, w, h / 32 + 2, 0), mix(a, b, k / 31), outline=False)
    if zeit == "nacht":
        pen.poly(I, ellipse(x + w * 0.72, y + h * 0.25, 46, 46), "#F4F1D0", outline=False)
    else:
        for cx, cy in ((0.3, 0.3), (0.7, 0.55)):
            for dx, r in ((-40, 34), (0, 46), (44, 32)):
                pen.poly(I, ellipse(x + w * cx + dx, y + h * cy, r, r * 0.8), "#FFFFFF", outline=False)
    pen.tint = tint


def backstube(pen, zeit: str = "tag") -> None:
    pen.tint = TINT[zeit]
    # Wand + Boden
    pen.poly(I, rrect(-20, -20, 1480, 1740, 0), "#F3E3C3", outline=False)
    for x in range(0, 1440, 120):
        pen.poly(I, rrect(x, 0, 60, 1700, 0), "#EED9B3", outline=False)
    pen.poly(I, rrect(-20, 1700, 1480, 900, 0), "#B9825A", outline=False)
    for k, y in enumerate(range(1730, 2600, 95)):
        pen.line(I, [(-10, y), (1450, y)], "#9C6A47", 5)
        for x in range(((k * 170) % 340) - 340, 1440, 340):
            pen.line(I, [(x, y), (x, y + 95)], "#9C6A47", 4)
    pen.line(I, [(-10, 1700), (1450, 1700)], None, 7)
    # Fenster
    _himmel(pen, 560, 390, 400, 600, zeit)
    pen.poly(I, rrect(540, 370, 440, 640, 10), None)
    pen.line(I, [(760, 380), (760, 1000)], "#FFFFFF", 16)
    pen.line(I, [(550, 690), (970, 690)], "#FFFFFF", 16)
    pen.poly(I, rrect(520, 1000, 480, 34, 8), "#C98F5E")
    # Ofen (Messing)
    pen.poly(I, rrect(70, 520, 400, 1200, 60), "#C9A04A")
    pen.poly(I, rrect(110, 560, 320, 70, 25), mix("#C9A04A", "#FFFFFF", 0.25))
    pen.poly(I, ellipse(270, 980, 120, 120), "#3A2A22")
    pen.poly(I, ellipse(270, 980, 96, 96), "#E9732C" if zeit != "nacht" else "#5A3A2A")
    for dx in (-90, 90):
        pen.poly(I, ellipse(270 + dx, 1250, 22, 22), "#8A6A2A")
    pen.poly(I, rrect(220, 300, 100, 230, 20), "#A9853A")
    # Regal mit Brot
    for y in (420, 640, 860):
        pen.poly(I, rrect(1040, y, 380, 26, 6), "#9C6A47")
        for k, x in enumerate(range(1075, 1400, 82)):
            if k % 2:
                pen.poly(I, ellipse(x, y - 34, 40, 32), "#D9984C")
                pen.line(I, [(x - 18, y - 46), (x - 4, y - 26)], "#B5763A", 5)
                pen.line(I, [(x + 4, y - 50), (x + 18, y - 30)], "#B5763A", 5)
            else:
                pen.poly(I, rrect(x - 36, y - 62, 72, 62, 22), "#E2AE62")
    # Theke
    pen.poly(I, rrect(520, 1230, 940, 60, 10), "#E9DCC6")
    pen.poly(I, rrect(540, 1290, 900, 420, 0), "#A86B42")
    for x in range(560, 1440, 150):
        pen.poly(I, rrect(x, 1320, 120, 350, 14), "#B97A4E")
    pen.poly(I, rrect(560, 1130, 860, 100, 10), mix("#CFEFF5", "#FFFFFF", 0.4))
    for x in range(620, 1400, 110):
        pen.poly(I, ellipse(x, 1205, 34, 18), "#E7B66B")
    # Lampen
    for x in (380, 1100):
        pen.line(I, [(x, -10), (x, 170)], None, 6)
        pen.poly(I, np.array([[x - 80, 250], [x - 30, 170], [x + 30, 170], [x + 80, 250]]), "#2EC4B6")
        pen.poly(I, ellipse(x, 252, 30, 14), "#FFF3B0" if zeit in ("abend", "nacht") else "#FFFBE6")
    pen.tint = None
    pen.boden = mix("#B9825A", TINT[zeit][0], TINT[zeit][1]) if TINT[zeit] else "#B9825A"


ORTE = {"backstube": backstube}
