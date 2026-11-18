"""Wiederverwendbare Vektor-Bauteile für Schauplätze (Bühne 1440 × 2560, Boden ab „horizont“, Füße bei 2000).

Jedes Bauteil ist eine Funktion (pen, **parameter). Orte werden in toon/orte/*.yaml aus Bauteilen
zusammengesetzt – dadurch sehen Orte in jeder Folge gleich aus und neue Orte entstehen ohne Bildkosten.
"""
from __future__ import annotations

import math

import numpy as np

from toon.geo import M, bezier, capsule, ellipse, mix, rrect

I = M()
HIMMEL = {"morgen": ("#FFD9A8", "#BFE3F0"), "tag": ("#8FCDEE", "#D9F0FA"), "abend": ("#FF9F68", "#FFD08A"),
          "nacht": ("#141B36", "#2E3C66")}


def _rect(pen, x, y, w, h, c, outline=False, r=0):
    pen.poly(I, rrect(x, y, w, h, r), c, outline=outline)


def himmel(pen, zeit="tag", y0=0, y1=1700, x0=-20, x1=1460, sterne=None, sonne=True, wolken=True, **_):
    a, b = HIMMEL[zeit]
    tint, pen.tint = pen.tint, None
    n = 40
    for k in range(n):
        _rect(pen, x0, y0 + (y1 - y0) * k / n, x1 - x0, (y1 - y0) / n + 2, mix(a, b, k / (n - 1)))
    if zeit == "nacht" or sterne:
        rnd = np.random.default_rng(3)
        for _ in range(70):
            pen.dot(I, rnd.uniform(x0, x1), rnd.uniform(y0, y0 + (y1 - y0) * 0.7), rnd.uniform(2, 4.5), "#F4F1D0")
    if sonne:
        if zeit == "nacht":
            pen.poly(I, ellipse(x0 + (x1 - x0) * 0.78, y0 + (y1 - y0) * 0.18, 60, 60), "#F4F1D0", outline=False)
        elif zeit in ("abend", "morgen"):
            pen.poly(I, ellipse(x0 + (x1 - x0) * 0.25, y0 + (y1 - y0) * 0.62, 90, 90), "#FFE7A0", outline=False)
    if wolken and zeit != "nacht":
        for cx, cy in ((0.25, 0.18), (0.72, 0.3), (0.5, 0.08)):
            for dx, r in ((-60, 44), (0, 62), (62, 42)):
                pen.poly(I, ellipse(x0 + (x1 - x0) * cx + dx, y0 + (y1 - y0) * cy, r, r * 0.75), "#FFFFFF", outline=False)
    pen.tint = tint


def wand(pen, farbe="#F3E3C3", muster="streifen", y1=1700, akzent=None, **_):
    _rect(pen, -20, -20, 1480, y1 + 20, farbe)
    ak = akzent or mix(farbe, "#000000", 0.07)
    if muster == "streifen":
        for x in range(0, 1440, 120):
            _rect(pen, x, 0, 60, y1, ak)
    elif muster == "paneel":
        _rect(pen, -20, y1 - 520, 1480, 520, ak)
        for x in range(30, 1440, 180):
            pen.poly(I, rrect(x, y1 - 480, 140, 440, 10), mix(ak, "#000000", 0.06))
    elif muster == "stein":
        for row, y in enumerate(range(0, y1, 110)):
            for x in range(-120 + (row % 2) * 110, 1440, 220):
                pen.poly(I, rrect(x + 6, y + 6, 208, 98, 18), ak)
    elif muster == "holz":
        for x in range(0, 1440, 90):
            pen.line(I, [(x, 0), (x, y1)], mix(farbe, "#000000", 0.2), 4)
    elif muster == "metall":
        for y in range(0, y1, 340):
            pen.line(I, [(-10, y), (1450, y)], mix(farbe, "#000000", 0.25), 6)
            for x in range(40, 1440, 160):
                pen.dot(I, x, y + 24, 6, mix(farbe, "#000000", 0.3))
    elif muster == "tapete":
        for y in range(60, y1, 160):
            for x in range(60 + (y // 160 % 2) * 80, 1440, 160):
                pen.poly(I, ellipse(x, y, 14, 22), ak, outline=False)


def boden(pen, art="holz", farbe="#B9825A", y0=1700, **_):
    _rect(pen, -20, y0, 1480, 2600 - y0, farbe)
    dunkel = mix(farbe, "#000000", 0.16)
    if art in ("holz", "deck"):
        for k, y in enumerate(range(y0 + 30, 2600, 95)):
            pen.line(I, [(-10, y), (1450, y)], dunkel, 5)
            for x in range(((k * 170) % 340) - 340, 1440, 340):
                pen.line(I, [(x, y), (x, y + 95)], dunkel, 4)
    elif art == "pflaster":
        for row, y in enumerate(range(y0 + 10, 2600, 70)):
            for x in range(-60 + (row % 2) * 45, 1440, 90):
                pen.poly(I, rrect(x, y, 80, 60, 18), mix(farbe, "#FFFFFF", 0.08 * (row % 3)), outline=False)
                pen.poly(I, rrect(x, y, 80, 60, 18), None, lw=3)
    elif art == "fliesen":
        for row, y in enumerate(range(y0, 2600, 120)):
            for col, x in enumerate(range(0, 1440, 120)):
                if (row + col) % 2:
                    _rect(pen, x, y, 120, 120, dunkel)
    elif art in ("gras", "sand"):
        rnd = np.random.default_rng(5)
        for _ in range(160):
            x, y = rnd.uniform(0, 1440), rnd.uniform(y0 + 20, 2560)
            if art == "gras":
                pen.line(I, [(x, y), (x - 6, y - 22)], dunkel, 4)
                pen.line(I, [(x + 8, y), (x + 12, y - 18)], dunkel, 4)
            else:
                pen.dot(I, x, y, 3, dunkel)
    elif art == "metall":
        for y in range(y0 + 40, 2600, 160):
            pen.line(I, [(-10, y), (1450, y)], dunkel, 5)
        for x in range(80, 1440, 240):
            pen.line(I, [(x, y0), (x, 2600)], dunkel, 4)
    elif art == "teppich":
        pen.poly(I, rrect(160, y0 + 140, 1120, 640, 40), mix(farbe, "#8E2B3A", 0.6))
        pen.poly(I, rrect(220, y0 + 190, 1000, 540, 30), mix(farbe, "#E9C46A", 0.35))
    elif art == "wolken":
        for x in range(-100, 1600, 230):
            pen.poly(I, ellipse(x, y0 + 120, 170, 110), "#FFFFFF", outline=False)
    pen.line(I, [(-10, y0), (1450, y0)], None, 6)


def fenster(pen, x, y, w=400, h=560, zeit="tag", rahmen="#FFFFFF", rund=False, **_):
    if rund:
        r = w / 2
        tint, pen.tint = pen.tint, None
        pen.poly(I, ellipse(x + r, y + r, r, r), HIMMEL["nacht"][0])
        rnd = np.random.default_rng(int(x))
        for _ in range(25):
            a, rr = rnd.uniform(0, 6.28), rnd.uniform(0, r * 0.9)
            pen.dot(I, x + r + rr * math.cos(a), y + r + rr * math.sin(a), 3, "#F4F1D0")
        pen.tint = tint
        pen.line(I, np.vstack([ellipse(x + r, y + r, r, r, 60), ellipse(x + r, y + r, r, r, 60)[:1]]), rahmen, 26)
        return
    himmel(pen, zeit, y, y + h, x, x + w, wolken=True, sonne=False)
    pen.poly(I, rrect(x - 20, y - 20, w + 40, h + 40, 10), None)
    pen.line(I, [(x + w / 2, y - 10), (x + w / 2, y + h + 10)], rahmen, 16)
    pen.line(I, [(x - 10, y + h / 2), (x + w + 10, y + h / 2)], rahmen, 16)
    pen.poly(I, rrect(x - 40, y + h + 4, w + 80, 34, 8), mix(rahmen, "#8A5A3A", 0.6))


def tuer(pen, x, y1=1700, farbe="#8A5A3A", w=260, h=560, glocke=False, **_):
    pen.poly(I, rrect(x, y1 - h, w, h, 14), farbe)
    pen.poly(I, rrect(x + 30, y1 - h + 30, w - 60, h * 0.42, 10), mix(farbe, "#FFFFFF", 0.12))
    pen.poly(I, rrect(x + 30, y1 - h * 0.48, w - 60, h * 0.4, 10), mix(farbe, "#FFFFFF", 0.12))
    pen.poly(I, ellipse(x + w - 40, y1 - h / 2, 14, 14), "#E2B64A")
    if glocke:
        pen.line(I, [(x + w / 2, y1 - h - 60), (x + w / 2, y1 - h - 20)], None, 4)
        pen.poly(I, np.array([[x + w / 2 - 24, y1 - h - 20], [x + w / 2 + 24, y1 - h - 20], [x + w / 2 + 14, y1 - h - 60],
                              [x + w / 2 - 14, y1 - h - 60]]), "#E2B64A")


def regal(pen, x, y, w=380, ebenen=3, inhalt="buecher", **_):
    rnd = np.random.default_rng(int(x + y))
    farben = ["#E4572E", "#2EC4B6", "#F2B134", "#6B4FA0", "#3A7D44", "#2B3F73"]
    for k in range(ebenen):
        yy = y + k * 220
        _rect(pen, x, yy, w, 26, "#9C6A47", outline=True, r=6)
        cx = x + 20
        while cx < x + w - 50:
            if inhalt == "buecher":
                bw, bh = rnd.uniform(28, 46), rnd.uniform(110, 160)
                pen.poly(I, rrect(cx, yy - bh, bw, bh, 4), farben[int(rnd.integers(6))])
                cx += bw + 4
            elif inhalt == "flaschen":
                pen.poly(I, rrect(cx, yy - 120, 44, 120, 14), mix(farben[int(rnd.integers(6))], "#FFFFFF", 0.3))
                pen.poly(I, rrect(cx + 14, yy - 150, 16, 34, 4), "#9C6A47")
                cx += 64
            elif inhalt == "brot":
                pen.poly(I, ellipse(cx + 40, yy - 34, 40, 32), "#D9984C")
                cx += 92
            elif inhalt == "uhren":
                r = rnd.uniform(26, 44)
                pen.poly(I, ellipse(cx + r, yy - r - 6, r, r), "#FFF8E0")
                pen.line(I, [(cx + r, yy - r - 6), (cx + r, yy - 2 * r + 4)], None, 4)
                cx += 2 * r + 14
            elif inhalt == "glaeser":
                pen.poly(I, rrect(cx, yy - 80, 50, 80, 8), "#CFEFF5")
                cx += 66
            elif inhalt == "dosen":
                pen.poly(I, rrect(cx, yy - 90, 60, 90, 10), farben[int(rnd.integers(6))])
                cx += 74


def theke(pen, x, w=900, y1=1700, h=470, farbe="#A86B42", glas=True, **_):
    _rect(pen, x, y1 - h, w, 60, "#E9DCC6", outline=True, r=10)
    _rect(pen, x + 20, y1 - h + 60, w - 40, h - 60, farbe, outline=True)
    for xx in range(int(x) + 40, int(x + w) - 120, 150):
        pen.poly(I, rrect(xx, y1 - h + 90, 120, h - 120, 14), mix(farbe, "#FFFFFF", 0.1))
    if glas:
        pen.poly(I, rrect(x + 40, y1 - h - 100, w - 80, 100, 10), "#E4F5F8")
        for xx in range(int(x) + 100, int(x + w) - 60, 110):
            pen.poly(I, ellipse(xx, y1 - h - 25, 34, 18), "#E7B66B")


def ofen(pen, x, y1=1700, zeit="tag", **_):
    pen.poly(I, rrect(x, y1 - 1180, 400, 1200, 60), "#C9A04A")
    pen.poly(I, rrect(x + 40, y1 - 1140, 320, 70, 25), mix("#C9A04A", "#FFFFFF", 0.25))
    pen.poly(I, ellipse(x + 200, y1 - 720, 120, 120), "#3A2A22")
    pen.poly(I, ellipse(x + 200, y1 - 720, 96, 96), "#E9732C" if zeit != "nacht" else "#5A3A2A")
    for dx in (-90, 90):
        pen.poly(I, ellipse(x + 200 + dx, y1 - 450, 22, 22), "#8A6A2A")
    pen.poly(I, rrect(x + 150, y1 - 1400, 100, 230, 20), "#A9853A")


def hocker(pen, x, boden_y=2000, farbe="#9C6A47", **_):
    pen.poly(I, rrect(x - 90, boden_y - 175, 180, 34, 14), farbe)
    for dx in (-70, 50):
        pen.poly(I, rrect(x + dx, boden_y - 145, 20, 145, 6), mix(farbe, "#000000", 0.15))
    pen.line(I, [(x - 62, boden_y - 60), (x + 62, boden_y - 60)], mix(farbe, "#000000", 0.15), 10)


def stuhl(pen, x, boden_y=2000, farbe="#8E2B3A", lehne=True, **_):
    hocker(pen, x, boden_y, farbe)
    if lehne:
        pen.poly(I, rrect(x - 90, boden_y - 430, 30, 270, 10), farbe)
        pen.poly(I, rrect(x - 90, boden_y - 430, 170, 40, 14), farbe)


def tisch(pen, x, w=520, boden_y=1700, farbe="#9C6A47", h=330, **_):
    _rect(pen, x, boden_y - h, w, 36, farbe, outline=True, r=10)
    for xx in (x + 30, x + w - 60):
        _rect(pen, xx, boden_y - h + 36, 30, h - 36, mix(farbe, "#000000", 0.15), outline=True, r=6)


def lampe(pen, x, y=170, farbe="#2EC4B6", zeit="tag", **_):
    pen.line(I, [(x, -10), (x, y)], None, 6)
    pen.poly(I, np.array([[x - 80, y + 80], [x - 30, y], [x + 30, y], [x + 80, y + 80]]), farbe)
    pen.poly(I, ellipse(x, y + 82, 30, 14), "#FFF3B0" if zeit in ("abend", "nacht") else "#FFFBE6")


def bild(pen, x, y, w=260, h=330, farbe="#3A7D44", **_):
    pen.poly(I, rrect(x - 22, y - 22, w + 44, h + 44, 6), "#C9A04A")
    pen.poly(I, rrect(x, y, w, h, 2), mix(farbe, "#FFFFFF", 0.35))
    pen.poly(I, ellipse(x + w / 2, y + h * 0.42, w * 0.2, h * 0.17), mix(farbe, "#000000", 0.25))
    pen.poly(I, ellipse(x + w / 2, y + h * 0.95, w * 0.38, h * 0.32, 40, 180, 360), mix(farbe, "#000000", 0.25))


def standuhr(pen, x, y1=1700, **_):
    pen.poly(I, rrect(x, y1 - 900, 200, 900, 20), "#6B3E26")
    pen.poly(I, ellipse(x + 100, y1 - 760, 74, 74), "#FFF8E0")
    pen.line(I, [(x + 100, y1 - 760), (x + 100, y1 - 810)], None, 6)
    pen.line(I, [(x + 100, y1 - 760), (x + 140, y1 - 740)], None, 6)
    pen.poly(I, rrect(x + 50, y1 - 600, 100, 380, 30), "#4A2A1A")
    pen.poly(I, ellipse(x + 100, y1 - 300, 34, 34), "#E2B64A")


def kamin(pen, x, y1=1700, zeit="tag", **_):
    pen.poly(I, rrect(x, y1 - 620, 520, 620, 10), "#B5543B")
    pen.poly(I, rrect(x - 30, y1 - 660, 580, 60, 10), "#6B3E26")
    pen.poly(I, rrect(x + 110, y1 - 400, 300, 400, 120), "#2A1A14")
    feuer(pen, x + 260, y1 - 30, 1.0)


def feuer(pen, x, y, s=1.0, **_):
    for r, c in ((90, "#E4572E"), (64, "#F2B134"), (36, "#FFF3B0")):
        pen.poly(I, np.vstack([bezier((x - r * s, y), (x - r * s, y - 1.6 * r * s), (x, y - 2.2 * r * s), n=12),
                               bezier((x, y - 2.2 * r * s), (x + r * s, y - 1.6 * r * s), (x + r * s, y), n=12)]),
                 c, outline=(r == 90))
    if s > 0.5:
        for dx in (-60, 0, 60):
            pen.poly(I, capsule(x + dx - 40, y + 10, x + dx + 40, y - 6, 14), "#6B3E26")


def pflanze(pen, x, y1=1700, farbe="#3A7D44", **_):
    pen.poly(I, np.array([[x - 70, y1 - 180], [x + 70, y1 - 180], [x + 50, y1], [x - 50, y1]]), "#C96A3A")
    for a in (-60, -25, 0, 25, 60):
        pen.poly(M(x, y1 - 180, a), ellipse(0, -110, 34, 110), farbe)


def palme(pen, x, y1=1700, h=900, **_):
    pts = bezier((x, y1), (x + 40, y1 - h * 0.5), (x - 30, y1 - h * 0.8), (x + 20, y1 - h), 20)
    for k in range(len(pts) - 1):
        pen.poly(I, capsule(pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1], 34 - k * 0.6), "#8A5A3A")
    tx, ty = pts[-1]
    for a in (-150, -110, -60, -20, 30, 80):
        pen.poly(M(tx, ty, a), np.vstack([bezier((0, 0), (120, -60), (260, 20), n=10),
                                          bezier((260, 20), (120, 10), (0, 0), n=10)]), "#2E8B57")
    for dx in (-20, 20):
        pen.poly(I, ellipse(tx + dx, ty + 30, 26, 26), "#6B4A2A")


def baum(pen, x, y1=1700, farbe="#3A7D44", h=700, kahl=False, **_):
    pen.poly(I, rrect(x - 40, y1 - h * 0.55, 80, h * 0.55, 20), "#7A4E2D")
    if kahl:
        for a in (-40, -10, 25, 50):
            pen.poly(M(x, y1 - h * 0.5, a), capsule(0, 0, 0, -h * 0.45, 16, 6), "#5A3A2A")
        return
    for dx, dy, r in ((-140, -0.62, 170), (130, -0.66, 160), (0, -0.85, 210)):
        pen.poly(I, ellipse(x + dx, y1 + h * dy, r, r * 0.85), farbe)


def busch(pen, x, y1=1700, farbe="#2E8B57", **_):
    for dx, r in ((-90, 90), (0, 120), (90, 90)):
        pen.poly(I, ellipse(x + dx, y1 - r * 0.7, r, r * 0.8), farbe)


def haus(pen, x, w=520, h=1100, y1=1700, farbe="#E9C46A", dach="#B5543B", fenster_n=2, tuer_x=None,
         markise=None, **_):
    pen.poly(I, rrect(x, y1 - h, w, h, 0), farbe)
    pen.poly(I, np.array([[x - 30, y1 - h], [x + w / 2, y1 - h - 220], [x + w + 30, y1 - h]]), dach)
    for row in range(2):
        for col in range(fenster_n):
            fx = x + (col + 0.5) * w / fenster_n - 70
            fy = y1 - h + 120 + row * 320
            pen.poly(I, rrect(fx, fy, 140, 200, 8), "#BFE3F0")
            pen.line(I, [(fx + 70, fy), (fx + 70, fy + 200)], "#FFFFFF", 8)
    if tuer_x is not None:
        tuer(pen, x + tuer_x, y1, mix(dach, "#000000", 0.2), 200, 380)
    if markise:
        pen.poly(I, np.array([[x - 10, y1 - 470], [x + w + 10, y1 - 470], [x + w + 40, y1 - 370], [x - 40, y1 - 370]]),
                 markise)
        for k in range(8):
            if k % 2:
                xx = x - 40 + k * (w + 80) / 8
                pen.poly(I, np.array([[xx, y1 - 370], [xx + (w + 80) / 8, y1 - 370],
                                      [xx + (w + 80) / 8 - 6, y1 - 470], [xx - 6, y1 - 470]]), "#FFFFFF", outline=False)


def laterne(pen, x, y1=1700, zeit="tag", **_):
    pen.poly(I, rrect(x - 14, y1 - 760, 28, 760, 8), "#2B2B33")
    pen.poly(I, np.array([[x - 50, y1 - 760], [x + 50, y1 - 760], [x + 34, y1 - 860], [x - 34, y1 - 860]]),
             "#FFF3B0" if zeit in ("abend", "nacht") else "#D9F0FA")
    pen.poly(I, np.array([[x - 60, y1 - 860], [x + 60, y1 - 860], [x, y1 - 910]]), "#2B2B33")


def berg(pen, x, w=900, h=700, y1=1700, farbe="#7A9CC6", schnee=True, **_):
    pen.poly(I, np.array([[x, y1], [x + w / 2, y1 - h], [x + w, y1]]), farbe)
    if schnee:
        pen.poly(I, np.array([[x + w / 2 - 110, y1 - h + 160], [x + w / 2, y1 - h], [x + w / 2 + 110, y1 - h + 160],
                              [x + w / 2 + 40, y1 - h + 120], [x + w / 2 - 30, y1 - h + 170]]), "#FFFFFF")


def huegel(pen, x, w=1000, h=300, y1=1700, farbe="#7FB069", **_):
    pen.poly(I, ellipse(x + w / 2, y1, w / 2, h, 60, 180, 360), farbe)


def wasser(pen, y0=1500, y1=1760, farbe="#2EC4B6", **_):
    _rect(pen, -20, y0, 1480, y1 - y0, farbe)
    for k, y in enumerate(range(int(y0) + 40, int(y1), 70)):
        for x in range(-100 + (k % 2) * 90, 1500, 180):
            pen.line(I, bezier((x, y), (x + 40, y - 14), (x + 80, y), n=8), "#FFFFFF", 5)


def steg(pen, x, w=600, y=1750, **_):
    _rect(pen, x, y - 40, w, 60, "#9C6A47", outline=True)
    for xx in range(int(x) + 40, int(x + w), 150):
        _rect(pen, xx, y + 20, 26, 200, "#7A4E2D", outline=True)


def wrack(pen, x, y=1650, **_):
    m = M(x, y, -8)
    pen.poly(m, rrect(-260, -80, 520, 150, 70), "#F4F1E8")
    pen.poly(m, rrect(-260, -20, 520, 30, 0), "#E4572E")
    pen.poly(m, np.array([[-60, -80], [80, -80], [40, -150], [-20, -150]]), "#CFEFF5")
    pen.poly(m, np.array([[-80, -40], [-360, -10], [-360, 20], [-80, 10]]), "#E4572E")
    pen.poly(m, np.array([[230, -60], [320, -170], [340, -170], [300, -40]]), "#E4572E")
    pen.poly(m, rrect(-200, 90, 400, 40, 20), "#B0B6BE")


def felsen(pen, x, y1=1700, w=300, h=200, farbe="#8A8F99", **_):
    pen.poly(I, np.vstack([bezier((x, y1), (x + w * 0.1, y1 - h), (x + w * 0.6, y1 - h * 1.1), (x + w, y1), 14)]), farbe)


def saeule(pen, x, y1=1700, h=800, kaputt=False, **_):
    hh = h * (0.6 if kaputt else 1)
    pen.poly(I, rrect(x, y1 - hh, 110, hh, 6), "#D8D2C2")
    for k in range(1, 4):
        pen.line(I, [(x + k * 27, y1 - hh + 30), (x + k * 27, y1 - 30)], "#B8B0A0", 4)
    pen.poly(I, rrect(x - 20, y1 - hh - 40, 150, 40, 6), "#C8C0B0")


def wasserfall(pen, x, y0=600, y1=1700, **_):
    _rect(pen, x, y0, 160, y1 - y0, "#9ED9F0", outline=True)
    for xx in range(int(x) + 20, int(x) + 160, 40):
        pen.line(I, [(xx, y0 + 20), (xx, y1 - 20)], "#FFFFFF", 5)


def kaefig(pen, x, y, **_):
    pen.line(I, [(x, y - 120), (x, y - 60)], None, 5)
    pen.poly(I, ellipse(x, y + 40, 90, 110, 40, 180, 360), None)
    for dx in range(-80, 81, 32):
        pen.line(I, [(x + dx, y + 40 - math.sqrt(max(0, 1 - (dx / 90) ** 2)) * 110), (x + dx, y + 150)], "#C9A04A", 5)
    pen.poly(I, rrect(x - 95, y + 140, 190, 24, 8), "#C9A04A")


def konsole(pen, x, w=700, y1=1700, **_):
    pen.poly(I, np.array([[x, y1], [x + w, y1], [x + w - 40, y1 - 360], [x + 40, y1 - 360]]), "#5A6478")
    for k in range(3):
        sx = x + 70 + k * (w - 140) / 3
        pen.poly(I, rrect(sx, y1 - 330, (w - 180) / 3, 140, 10), "#1C2A3A")
        for j in range(4):
            pen.line(I, [(sx + 16, y1 - 310 + j * 30), (sx + 40 + j * 22, y1 - 310 + j * 30)], "#2EC4B6", 6)
    for k in range(8):
        pen.dot(I, x + 80 + k * (w - 160) / 7, y1 - 120, 12, ["#E4572E", "#F2B134", "#2EC4B6"][k % 3])


def rohre(pen, y=200, farbe="#8A94A6", **_):
    for k, yy in enumerate((y, y + 70)):
        pen.poly(I, rrect(-20, yy, 1480, 40, 20), mix(farbe, "#FFFFFF", 0.1 * k))
        for x in range(120, 1440, 300):
            pen.poly(I, rrect(x, yy - 8, 40, 56, 8), mix(farbe, "#000000", 0.2))


def luke(pen, x, y1=1700, **_):
    pen.poly(I, rrect(x, y1 - 640, 340, 640, 60), "#5A6478")
    pen.poly(I, rrect(x + 30, y1 - 610, 280, 580, 50), "#3E4658")
    pen.line(I, [(x + 170, y1 - 610), (x + 170, y1 - 30)], "#F2B134", 8)
    pen.poly(I, ellipse(x + 170, y1 - 360, 40, 40), "#E4572E")


def planet(pen, x, y, r=420, farbe="#3D7DCA", **_):
    tint, pen.tint = pen.tint, None
    pen.poly(I, ellipse(x, y, r, r), farbe, outline=False)
    for k in range(-3, 4):
        pen.poly(I, ellipse(x, y + k * r * 0.25, r * math.sqrt(max(0, 1 - (k * 0.25) ** 2)), 24),
                 mix(farbe, "#FFFFFF", 0.2), outline=False)
    pen.tint = tint


def marktstand(pen, x, w=700, y1=1700, markise="#E4572E", **_):
    _rect(pen, x, y1 - 420, w, 420, "#B97A4E", outline=True)
    _rect(pen, x - 20, y1 - 460, w + 40, 50, "#E9DCC6", outline=True, r=8)
    for xx in (x + 10, x + w - 40):
        _rect(pen, xx, y1 - 1100, 30, 640, "#7A4E2D", outline=True)
    for k in range(10):
        pen.poly(I, np.array([[x - 40 + k * (w + 80) / 10, y1 - 1100], [x - 40 + (k + 1) * (w + 80) / 10, y1 - 1100],
                              [x - 40 + (k + 1) * (w + 80) / 10, y1 - 980], [x - 40 + k * (w + 80) / 10, y1 - 980]]),
                 markise if k % 2 == 0 else "#FFFFFF")
    pen.poly(I, rrect(x + w * 0.62, y1 - 860, w * 0.3, 300, 10), "#2B2B33")


def kessel(pen, x, y1=1700, **_):
    pen.poly(I, ellipse(x, y1 - 180, 180, 170), "#3A3A44")
    pen.poly(I, ellipse(x, y1 - 330, 170, 34), "#6B8E3A")
    for dx in (-100, 0, 100):
        pen.poly(I, ellipse(x + dx, y1 - 400 - abs(dx) * 0.3, 40, 30), "#EEEEEE", outline=False)
    feuer(pen, x, y1 + 10, 0.6)


def hoehle(pen, x, y1=1700, w=500, h=420, **_):
    pen.poly(I, np.vstack([bezier((x, y1), (x + w * 0.05, y1 - h), (x + w * 0.95, y1 - h), (x + w, y1), 18)]), "#3A2A30")


def ballon(pen, farbe="#E4572E", **_):
    pen.poly(I, ellipse(720, -120, 900, 420), farbe)
    for k in range(-4, 5):
        pen.line(I, bezier((720 + k * 160, -500), (720 + k * 200, 0), (720 + k * 180, 280), n=12), "#FFFFFF", 10)
    for x in (200, 720, 1240):
        pen.line(I, [(x, 280), (x, 1200)], "#6B4A2A", 6)


def reling(pen, y=1650, **_):
    pen.poly(I, rrect(-20, y - 260, 1480, 34, 10), "#9C6A47")
    for x in range(20, 1440, 120):
        pen.poly(I, rrect(x, y - 240, 22, 240, 6), "#7A4E2D")


def steuerrad(pen, x, y, **_):
    for a in range(0, 360, 45):
        pen.poly(M(x, y, a), rrect(-8, -130, 16, 260, 6), "#7A4E2D")
    pen.line(I, np.vstack([ellipse(x, y, 100, 100, 48), ellipse(x, y, 100, 100, 48)[:1]]), "#9C6A47", 22)
    pen.poly(I, ellipse(x, y, 26, 26), "#C9A04A")


def werkbank(pen, x, w=760, boden_y=1700, **_):
    tisch(pen, x, w, boden_y, "#8A5A3A", 380)
    pen.poly(I, rrect(x + w * 0.65, boden_y - 560, 40, 180, 10), "#3A3A44")
    pen.poly(I, np.array([[x + w * 0.6, boden_y - 560], [x + w * 0.65 + 120, boden_y - 560],
                          [x + w * 0.65 + 60, boden_y - 620]]), "#2EC4B6")
    for k in range(5):
        pen.dot(I, x + 60 + k * 50, boden_y - 400, 10, "#B0B6BE")


def uhrenwand(pen, **kw):
    regal(pen, 120, 520, 1200, 3, "uhren")


def tram(pen, x, y1=1700, **_):
    pen.poly(I, rrect(x, y1 - 560, 900, 480, 40), "#C9A04A")
    pen.poly(I, rrect(x, y1 - 120, 900, 60, 10), "#6B3E26")
    for k in range(5):
        pen.poly(I, rrect(x + 40 + k * 170, y1 - 500, 130, 180, 10), "#BFE3F0")
    for dx in (160, 740):
        pen.poly(I, ellipse(x + dx, y1 - 50, 46, 46), "#2B2B33")
    pen.line(I, [(x + 450, y1 - 560), (x + 560, y1 - 900)], None, 6)


def litfass(pen, x, y1=1700, **_):
    pen.poly(I, rrect(x, y1 - 700, 220, 700, 30), "#2E7D6B")
    for k in range(3):
        pen.poly(I, rrect(x + 20, y1 - 640 + k * 200, 180, 170, 6), ["#E9C46A", "#E4572E", "#F4F1E8"][k])
    pen.poly(I, ellipse(x + 110, y1 - 720, 130, 40), "#1F5A4C")


def wolkenmeer(pen, y=1500, **_):
    for x in range(-150, 1600, 210):
        pen.poly(I, ellipse(x, y + (x % 3) * 20, 180, 120), "#FFFFFF", outline=False)


def schwebegipfel(pen, x, y, w=600, farbe="#8A8F99", **_):
    pen.poly(I, np.vstack([[[x, y], [x + w, y]], bezier((x + w, y), (x + w * 0.8, y + 300), (x + w * 0.5, y + 420),
                                                        (x + w * 0.3, y + 260), 14)]), farbe)
    pen.poly(I, rrect(x - 10, y - 40, w + 20, 60, 30), "#7FB069")


BAUSTEINE = {k: v for k, v in globals().items() if callable(v) and not k.startswith("_") and k not in ("M",
             "bezier", "capsule", "ellipse", "mix", "rrect")}
