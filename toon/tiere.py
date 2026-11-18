"""Rigs für nicht-menschliche Figuren: Hund (Pixel), Roboter (BOLT), Drache (Glut).

Gleiche Schnittstelle wie toon.figur.Figur (zeichne(pen, Zustand)) – damit laufen Gehen, Drehen,
Blinzeln, Blick und Lippensync über dieselben Spuren. Gangzyklus kommt aus pose["bl"]/["br"].
"""
from __future__ import annotations

import math

import numpy as np

from toon.geo import M, bezier, capsule, ellipse, mix

OFFEN = {"X": 0.0, "A": 0.0, "B": 0.3, "C": 0.6, "D": 1.0, "E": 0.7, "F": 0.35, "G": 0.3, "H": 0.6}


def _schatten(pen, z, b):
    pen.poly(M(z.x, z.y, 0, z.s, z.s), ellipse(0, 4, b, 20), mix(pen.boden or "#B9825A", "#000000", 0.25),
             outline=False)


def _auge(pen, m, x, y, r, z, farbe="#2B1D16"):
    pen.poly(m, ellipse(x, y, r, r * 1.15), "#FFFFFF")
    pen.dot(m, x + z.blick[0] * r * 0.35, y + 3, r * 0.5, farbe)
    pen.dot(m, x + z.blick[0] * r * 0.35 + 4, y - 3, r * 0.17, "#FFFFFF")
    if z.blinzeln > 0.05:
        cut = y - r * 1.15 + 2.3 * r * z.blinzeln
        pen.poly(m, np.array([[x - r - 1, y - r * 1.2], [x + r + 1, y - r * 1.2], [x + r + 1, cut], [x - r - 1, cut]]),
                 pen._lid if hasattr(pen, "_lid") else "#E9963F", outline=False)
        pen.line(m, [(x - r, cut), (x + r, cut)], None, 4)


class Hund:
    def __init__(self, d: dict):
        self.d = d

    def zeichne(self, pen, z) -> None:
        d = self.d
        fell, hell = d["fell"], d["fell_hell"]
        pen._lid = fell
        _schatten(pen, z, 130)
        sg = 1 if z.phi >= 0 else -1
        m = M(z.x, z.y + z.pose["bob"] * 0.5 * z.s, 0, sg * z.s, z.s)
        th = z.pose["bl"][1]
        offen = OFFEN.get(z.mund, 0)
        wedel = 25 * math.sin(z.pose["kopf"] * 3.0)
        if abs(z.phi) < 25:        # Vorderansicht
            pen.poly(m, ellipse(0, -120, 120, 90), fell)
            pen.poly(m, ellipse(0, -100, 70, 70), hell)
            for dx in (-60, 60):
                pen.poly(m, capsule(dx, -70, dx, -10, 22), fell)
                pen.poly(m, ellipse(dx, -8, 26, 14), hell)
            self._kopf(pen, m @ M(0, -230), z, True, offen)
            return
        pen.poly(m @ M(-150, -150, -40 + wedel), ellipse(0, -30, 18, 40), fell)
        for k, (dx, ph) in enumerate(((-100, 1), (-60, -1), (60, 1), (100, -1))):
            a = th * ph * 0.9
            pen.poly(m @ M(dx, -90, -a), capsule(0, 0, 0, 80, 20, 18), mix(fell, "#000000", 0.12 * (k % 2)))
            pen.poly(m @ M(dx, -90, -a), ellipse(6, 84, 24, 12), hell)
        pen.poly(m, ellipse(0, -130, 165, 72), fell)
        pen.poly(m, ellipse(30, -100, 110, 36), hell, outline=False)
        pen.poly(m, ellipse(0, -130, 165, 72), None)
        self._kopf(pen, m @ M(150, -210), z, False, offen)

    def _kopf(self, pen, m, z, vorne, offen):
        d = self.d
        fell, hell = d["fell"], d["fell_hell"]
        for dx, a in ((-50, -18), (50, 18)) if vorne else ((-30, -8), (10, 14)):
            pen.poly(m @ M(dx, -70, a), np.array([[-30, 20], [0, -80], [30, 20]]), fell)
        pen.poly(m, ellipse(0, 0, 90, 82), fell)
        pen.poly(m, ellipse(0 if vorne else 46, 30, 58 if vorne else 52, 40), hell)
        if offen > 0:
            pen.poly(m, ellipse(0 if vorne else 56, 62, 26, 10 + 18 * offen), "#5A1E24")
            pen.poly(m, ellipse(0 if vorne else 56, 70 + 10 * offen, 14, 8 + 6 * offen), "#E06A78", outline=False)
        pen.poly(m, ellipse(0 if vorne else 92, 14, 16, 12), "#1B1B1F")
        for x in ((-32, 32) if vorne else (24,)):
            _auge(pen, m, x, -14, 15, z)
        pen.poly(m @ M(0, 64), np.array([[-60, 0], [60, 0], [0, 40]]) if vorne else np.array([[-60, 10], [40, 0], [-10, 36]]),
                 d["halstuch"])


class Roboter:
    def __init__(self, d: dict):
        self.d = d

    def zeichne(self, pen, z) -> None:
        d = self.d
        schwebe = 18 * math.sin(z.pose["kopf"] * 2.4)
        pen._lid = d["schale"]
        _schatten(pen, z, 80)
        m = M(z.x, z.y - 330 * z.s + schwebe * z.s + z.pose["bob"] * 0.3 * z.s, 0, z.s, z.s)
        sp = math.sin(math.radians(z.phi))
        for sx in (-1, 1):   # Ärmchen
            ax = sx * 120 * math.cos(math.radians(z.phi)) + 0
            arm_a = sx * (30 + z.pose["al" if sx < 0 else "ar"][1] * 0.6)
            pen.poly(m @ M(ax, 20, arm_a), capsule(0, 0, 0, 90, 12), mix(d["schale"], "#000000", 0.2))
            pen.poly(m @ M(ax, 20, arm_a) @ M(0, 95), ellipse(0, 0, 18, 14), d["akzent"])
        pen.line(m, [(sp * 20, -120), (sp * 30, -190)], None, 6)
        pen.poly(m, ellipse(sp * 30, -196, 16, 16), d["akzent"])
        pen.poly(m, ellipse(0, 0, 130, 125), d["schale"])
        pen.poly(m, ellipse(0, 60, 128, 60, 40, 0, 180), d["akzent"], outline=False)
        pen.poly(m, ellipse(0, 0, 130, 125), None)
        ex = sp * 60
        pen.poly(m, ellipse(ex, -20, 62 * (0.6 + 0.4 * abs(math.cos(math.radians(z.phi)))), 60), "#1C2A3A")
        r = 34 * (1 - 0.8 * z.blinzeln)
        pen.poly(m, ellipse(ex + z.blick[0] * 10, -20, 34, max(3, r)), d["auge"], outline=False)
        pen.dot(m, ex + z.blick[0] * 10 + 10, -30, 8, "#FFFFFF")
        offen = OFFEN.get(z.mund, 0)
        for k in range(5):     # LED-Mund
            an = abs(k - 2) < 1 + offen * 2.6 if offen > 0 else k == 2
            pen.poly(m, ellipse(ex - 40 + k * 20, 60, 7, 7 + 8 * offen * (1 - abs(k - 2) / 3)),
                     d["auge"] if an else "#3E4658", outline=False)


class Drache:
    def __init__(self, d: dict):
        self.d = d

    def zeichne(self, pen, z) -> None:
        d = self.d
        pen._lid = d["schuppen"]
        _schatten(pen, z, 110)
        sg = 1 if z.phi >= 0 else -1
        m = M(z.x, z.y + z.pose["bob"] * 0.6 * z.s, 0, sg * z.s, z.s * z.pose["squash"])
        flap = 25 * math.sin(z.pose["kopf"] * 4.0)
        offen = OFFEN.get(z.mund, 0)
        pen.poly(m, np.vstack([bezier((-60, -60), (-200, -40), (-260, -120), (-230, -160), 10),
                               bezier((-230, -160), (-210, -110), (-140, -90), (-40, -110), 10)]), d["schuppen"])
        pen.poly(m @ M(-20, -260, -30 - flap), np.array([[0, 0], [-170, -120], [-130, -20], [-150, 30]]), d["fluegel"])
        th = z.pose["bl"][1]
        for dx, ph in ((-40, 1), (40, -1)):
            pen.poly(m @ M(dx, -90, -th * ph), capsule(0, 0, 0, 80, 26, 22), d["schuppen"])
            pen.poly(m @ M(dx, -90, -th * ph), ellipse(10, 84, 30, 14), mix(d["schuppen"], "#000000", 0.2))
        pen.poly(m, ellipse(0, -190, 110, 130), d["schuppen"])
        pen.poly(m, ellipse(25, -170, 62, 100), d["bauch"])
        pen.poly(m @ M(0, -260, 30 - flap), np.array([[0, 0], [150, -140], [120, -30], [150, 20]]), d["fluegel"])
        h = m @ M(40, -380)
        for dx in (-40, 20):
            pen.poly(h @ M(dx, -70, 20), np.array([[-14, 10], [0, -46], [14, 10]]), "#FFF4E6")
        pen.poly(h, ellipse(0, 0, 100, 88), d["schuppen"])
        pen.poly(h, ellipse(70, 26, 62, 40), d["schuppen"])
        if offen > 0:
            pen.poly(h, ellipse(86, 52, 40, 8 + 22 * offen), "#5A1E24")
            pen.poly(h, ellipse(86, 60 + 10 * offen, 20, 6 + 6 * offen), "#E06A78", outline=False)
        pen.dot(h, 118, 14, 6, "#6B2E1A")
        _auge(pen, h, 4, -18, 26, z, "#6B2E1A")


def figur_fuer(d: dict):
    from toon.figur import Figur
    return {"hund": Hund, "roboter": Roboter, "drache": Drache}.get(d.get("typ"), Figur)(d)
