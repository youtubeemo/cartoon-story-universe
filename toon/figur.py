"""Wiederverwendbares 2D-Charakter-Rig (Cut-out) – eine Figur = eine YAML-Beschreibung.

Gelenke: Hüfte (Wippen, Stauchen), Oberkörper, Kopf (Neigen, Drehen), Schultern/Ellbogen, Hüften/Knie.
Gesicht: Augen mit Lidern (Blinzeln), Pupillen (Blickrichtung), Brauen (Ausdruck), Mund mit 9 Formen
(Rhubarb/Preston-Blair: A–H, X) plus Ausdrucks-Krümmung. Frisuren, Kleidung, Accessoires parametrisch.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from toon.geo import M, bezier, capsule, ellipse, mix, rrect

# Ausdrücke: Brauen (Höhe, Winkel der Innenseite), Oberlid (0 offen … 1 zu), Augengröße, Mundkrümmung
AUSDRUCK = {
    "neutral":     {"brow_y": -5,  "brow_a": -2,  "lid": 0.06, "eye": 1.0,  "curve": 0.45},
    "froh":        {"brow_y": -6,  "brow_a": -4,  "lid": 0.05, "eye": 1.0,  "curve": 1.0},
    "begeistert":  {"brow_y": -14, "brow_a": -6,  "lid": 0.0,  "eye": 1.12, "curve": 1.0},
    "ueberrascht": {"brow_y": -18, "brow_a": 0,   "lid": 0.0,  "eye": 1.18, "curve": 0.0},
    "traurig":     {"brow_y": -2,  "brow_a": 20,  "lid": 0.32, "eye": 0.95, "curve": -0.75},
    "besorgt":     {"brow_y": -6,  "brow_a": 14,  "lid": 0.15, "eye": 1.0,  "curve": -0.35},
    "wuetend":     {"brow_y": 4,   "brow_a": -24, "lid": 0.25, "eye": 0.95, "curve": -0.5},
    "skeptisch":   {"brow_y": 0,   "brow_a": -10, "lid": 0.35, "eye": 1.0,  "curve": -0.15, "asym": True},
    "verschmitzt": {"brow_y": -4,  "brow_a": -12, "lid": 0.3,  "eye": 1.0,  "curve": 0.7, "asym": True},
}
MUNDFORMEN = "ABCDEFGHX"

STANDARD_POSE = {"torso": 0.0, "kopf": 0.0, "bob": 0.0, "squash": 1.0,
                 "al": (10.0, 8.0), "ar": (10.0, 8.0), "bl": (3.0, 0.0), "br": (3.0, 0.0)}


@dataclass
class Zustand:
    x: float = 540
    y: float = 1700
    s: float = 1.0
    pose: dict = field(default_factory=lambda: dict(STANDARD_POSE))
    ausdruck: str = "neutral"
    blinzeln: float = 0.0          # 0 offen … 1 geschlossen
    mund: str = "X"
    blick: tuple = (0.0, 0.0)      # Pupillen −1 … 1
    kopf_dreh: float = 0.0         # −1 links … 1 rechts (3/4-Wirkung)
    requisit: str | None = None    # brief | karte | scheine
    requisit_hand: str = "beide"


class Figur:
    def __init__(self, d: dict):
        self.d = d
        self.g = float(d.get("groesse", 1.0))
        self.w = {"schlank": 0.88, "normal": 1.0, "kraeftig": 1.18}[d.get("koerper", "normal")]
        self.haut = d["haut"]
        self.haut_dunkel = mix(self.haut, "#7A4A3A", 0.18)

    # ------------------------------------------------------------- Skelett
    def _gelenke(self, z: Zustand) -> dict:
        g, w, p = self.g, self.w, z.pose
        root = M(z.x, z.y, 0, z.s, z.s * p["squash"])
        hip = root @ M(0, -300 * g + p["bob"])
        torso = hip @ M(0, 0, p["torso"])
        sh_y = -215 * g
        neck = torso @ M(0, sh_y)
        head = neck @ M(0, -12, p["kopf"]) @ M(0, -118 * g)
        out = {"root": root, "hip": hip, "torso": torso, "neck": neck, "head": head, "sh_y": sh_y}
        for side, key in ((-1, "al"), (1, "ar")):
            a, b = p[key]
            sh = torso @ M(side * 76 * w, sh_y + 22)
            up = sh @ M(0, 0, -side * a)
            elbow = up @ M(0, 112 * g)
            low = elbow @ M(0, 0, -side * b)
            out[key] = (up, low, low @ M(0, 108 * g))
        for side, key in ((-1, "bl"), (1, "br")):
            a, b = p[key]
            h = hip @ M(side * 38 * w, -6)
            up = h @ M(0, 0, -side * a)
            knee = up @ M(0, 150 * g)
            low = knee @ M(0, 0, side * b)
            out[key] = (up, low, low @ M(0, 148 * g))
        return out

    # ------------------------------------------------------------- Zeichnen
    def zeichne(self, pen, z: Zustand) -> None:
        d, g, w = self.d, self.g, self.w
        j = self._gelenke(z)
        top = d.get("jacke", {}).get("farbe", d["oberteil"]) if d.get("jacke") else d["oberteil"]
        haare = d.get("haare", {})

        # Bodenschatten
        pen.poly(M(z.x, z.y, 0, z.s, z.s), ellipse(0, 4, 120 * w, 22), mix(pen.boden or "#B9825A", "#000000", 0.25),
                 outline=False)
        self._haare(pen, j["head"], haare, z, hinten=True)
        if d.get("rucksack"):
            pen.poly(j["torso"], rrect(-82 * w, -205 * g, 164 * w, 175 * g, 40), d["rucksack"])

        # Beine + Schuhe
        for key in ("bl", "br"):
            up, low, foot = j[key]
            pen.poly(up, capsule(0, 0, 0, 150 * g, 31 * w, 27 * w), d["hose"])
            pen.poly(low, capsule(0, 0, 0, 146 * g, 27 * w, 24 * w), d["hose"])
            side = -1 if key == "bl" else 1
            pen.poly(foot, ellipse(side * 16, -2, 40, 21), d.get("schuhe", "#3A3A3A"))

        # Oberkörper
        t = j["torso"]
        body = np.vstack([bezier((-72 * w, 8), (-82 * w, -90 * g), (-92 * w, -170 * g), (-80 * w, -215 * g), 14),
                          bezier((-80 * w, -215 * g), (-30, -234 * g), (30, -234 * g), (80 * w, -215 * g), 10),
                          bezier((80 * w, -215 * g), (92 * w, -170 * g), (82 * w, -90 * g), (72 * w, 8), 14),
                          bezier((72 * w, 8), (20, 22), (-20, 22), (-72 * w, 8), 8)])
        pen.poly(t, body, top)
        if d.get("jacke", {}).get("offen"):
            inner = np.vstack([bezier((-26, -222 * g), (-20, -120 * g), (-22, -40), (-24, 12), 8),
                               bezier((24, 12), (22, -40), (20, -120 * g), (26, -222 * g), 8)])
            pen.poly(t, inner, d["jacke"].get("innen", "#FFFFFF"))
        if d.get("weste"):
            pen.poly(t, np.array([[-40, -200 * g], [40, -200 * g], [55, 0], [-55, 0]]), d["weste"])
        if d.get("krawatte"):
            pen.poly(t, np.array([[-9, -214 * g], [9, -214 * g], [14, -110 * g], [0, -85 * g], [-14, -110 * g]]),
                     d["krawatte"])
        if d.get("schuerze"):
            pen.poly(t, rrect(-58 * w, -150 * g, 116 * w, 190 * g, 22), d["schuerze"])
            pen.line(t, [(-44 * w, -150 * g), (-30, -222 * g)], d["schuerze"], 9)
            pen.line(t, [(44 * w, -150 * g), (30, -222 * g)], d["schuerze"], 9)
            pen.poly(t, rrect(-30, -90 * g, 60, 40, 8), mix(d["schuerze"], "#FFFFFF", 0.15))
        if d.get("rucksack"):
            for sx in (-1, 1):
                pen.line(t, [(sx * 52 * w, -222 * g), (sx * 60 * w, -110 * g)], d["rucksack"], 13)

        # Hals + Kopf
        pen.poly(j["neck"], rrect(-22, -30, 44, 40, 12), self.haut_dunkel)
        self._kopf(pen, j["head"], z, haare)

        # Arme, Hände, Requisit
        sleeve = d.get("aermel", top)
        for key in ("al", "ar"):
            up, low, hand = j[key]
            pen.poly(up, capsule(0, 0, 0, 112 * g, 23 * w, 21 * w), sleeve)
            pen.poly(low, capsule(0, 0, 0, 104 * g, 20 * w, 18 * w),
                     sleeve if d.get("lange_aermel", True) else self.haut)
            pen.poly(hand, ellipse(0, 8, 25, 26), self.haut)
            side = -1 if key == "al" else 1
            pen.poly(hand, ellipse(-side * 18, -2, 10, 13), self.haut)
        if z.requisit:
            self._requisit(pen, j, z)

    def _requisit(self, pen, j, z) -> None:
        hl = j["al"][2] @ np.array([0, 8, 1])  # Bühnenkoordinaten
        hr = j["ar"][2] @ np.array([0, 8, 1])
        if z.requisit_hand == "beide":
            cx, cy = (hl[:2] + hr[:2]) / 2
        else:
            cx, cy = (hr if z.requisit_hand == "r" else hl)[:2]
        m = M(cx, cy - 20 * z.s, -6, z.s, z.s)
        if z.requisit == "brief":
            # Blatt reicht von Hand zu Hand (die Hände halten die Ränder)
            hw = 60.0 if z.requisit_hand != "beide" else min(110.0, max(55.0, abs(hr[0] - hl[0]) / (2 * z.s * pen.scale / pen.scale) - 14))
            pen.poly(m, rrect(-hw, -80, 2 * hw, 150, 6), "#FBF8F0")
            for k in range(5):
                pen.line(m, [(-hw * 0.7, -52 + 22 * k), (hw * 0.63 - (k % 2) * 18, -52 + 22 * k)], "#9AA3AE", 4)
        elif z.requisit == "karte":
            pen.poly(m, rrect(-46, -28, 92, 56, 5), "#E9E2FF")
            pen.line(m, [(-30, -6), (24, -6)], "#6B4FA0", 5)
        elif z.requisit == "scheine":
            for k in range(3):
                pen.poly(m @ M(k * 6, -k * 6, k * 4), rrect(-55, -28, 110, 56, 5), "#9ED29A")

    # ------------------------------------------------------------- Kopf und Gesicht
    def _kopf(self, pen, h, z: Zustand, haare: dict) -> None:
        t = z.kopf_dreh
        ox = t * 22
        for sx in (-1, 1):   # Ohren
            pen.poly(h, ellipse(sx * (104 - sx * ox * 0.5), 8, 20, 26), self.haut)
        pen.poly(h, ellipse(0, 0, 112, 120, 72), self.haut)
        if self.d.get("sommersprossen"):
            for sx in (-1, 1):
                for k, (dx, dy) in enumerate(((52, 30), (64, 24), (58, 40), (72, 34))):
                    pen.dot(h, ox + sx * dx, dy, 3.2, mix(self.haut, "#B5651D", 0.55))
        for sx in (-1, 1):   # Wangen
            pen.poly(h, ellipse(ox + sx * 64, 42, 20, 12), mix(self.haut, "#E8707A", 0.35), outline=False)

        e = z.ausdruck if isinstance(z.ausdruck, dict) else AUSDRUCK.get(z.ausdruck, AUSDRUCK["neutral"])
        for sx in (-1, 1):
            self._auge(pen, h, ox + sx * 40 + t * 4 * sx, -8, e, z, sx)
        # Nase
        pen.poly(h, ellipse(ox * 1.35, 22, 12, 9), self.haut_dunkel)
        # Mund
        self._mund(pen, h @ M(ox * 1.15, 64, 0, 1.35, 1.35), 0, 0, z.mund, e["curve"])
        if self.d.get("schnurrbart"):
            for sx in (-1, 1):
                pen.poly(h, np.vstack([bezier((ox, 42), (ox + sx * 30, 34), (ox + sx * 52, 40), (ox + sx * 66, 28), 10),
                                       bezier((ox + sx * 66, 28), (ox + sx * 46, 50), (ox + sx * 20, 50), (ox, 48), 10)]),
                         self.d.get("schnurrbart_farbe", "#1B1B1F"))
        if self.d.get("brille"):
            for sx in (-1, 1):
                pen.line(h, ellipse(ox + sx * 40, -8, 36, 36, 40).tolist() + [ellipse(ox + sx * 40, -8, 36, 36, 40)[0].tolist()],
                         self.d["brille"], 6)
            pen.line(h, [(ox - 6, -10), (ox + 6, -10)], self.d["brille"], 6)
        self._haare(pen, h, haare, z, hinten=False)

    def _auge(self, pen, h, x, y, e, z, sx) -> None:
        rx, ry = 26 * e["eye"], 32 * e["eye"]
        pen.poly(h, ellipse(x, y, rx, ry, 40), "#FFFFFF")
        bx, by = z.blick
        pen.dot(h, x + bx * 8, y + by * 8 + 3, 12.5, self.d.get("augen", "#3B2A20"))
        pen.dot(h, x + bx * 8 + 4, y + by * 8 - 2, 4, "#FFFFFF")
        lid = max(e["lid"], z.blinzeln)
        if e.get("asym") and sx > 0:
            lid = min(1.0, lid + 0.15) if z.blinzeln < 0.5 else lid
        if lid > 0.02:
            cut = y - ry + 2 * ry * lid
            pts = ellipse(x, y, rx + 1, ry + 1, 40)
            top = pts[pts[:, 1] <= cut]
            if len(top) >= 3:
                order = np.argsort(np.arctan2(top[:, 1] - y, top[:, 0] - x))
                top = top[order]
                pen.poly(h, np.vstack([top, [[x + rx, cut], [x - rx, cut]]]), self.haut, outline=False)
                pen.line(h, [(x - rx * 0.98, cut), (x + rx * 0.98, cut)], None, 5)
        # Braue
        by_ = y - ry - 18 + e["brow_y"]
        a = e["brow_a"] * sx
        if e.get("asym") and sx > 0:
            by_ -= 10
            a *= -0.5
        inner, outer = (x - sx * 22, by_), (x + sx * 22, by_)
        m = M(x, by_, a) @ M(-x, -by_)
        pen.line(h @ m, bezier(inner, (x, by_ - 7), outer, n=8), self.d.get("haare", {}).get("farbe", "#2B2B2B"), 10)

    def _mund(self, pen, h, x, y, form: str, curve: float) -> None:
        dark, tongue, teeth = "#5A1E24", "#E06A78", "#FFFFFF"
        c = curve * 14
        if form in ("X", "A"):
            w = 30 if form == "X" else 24
            pen.line(h, bezier((x - w, y - c * 0.6), (x, y + c), (x + w, y - c * 0.6), n=12), None, 6)
            return
        dims = {"B": (26, 9), "C": (28, 17), "D": (32, 26), "E": (22, 20), "F": (13, 13),
                "G": (26, 10), "H": (28, 19)}[form]
        w, hgt = dims
        upper = bezier((x - w, y - c * 0.4), (x, y - hgt * 0.35 + c * 0.3), (x + w, y - c * 0.4), n=12)
        lower = bezier((x + w, y - c * 0.4), (x, y + hgt + c * 0.5), (x - w, y - c * 0.4), n=12)
        shape = np.vstack([upper, lower])
        pen.poly(h, shape, dark)
        if form in ("B", "C", "D", "G"):
            pen.poly(h, rrect(x - w * 0.7, y - hgt * 0.32 + c * 0.2, w * 1.4, max(4, hgt * 0.3), 3), teeth, outline=False)
        if form in ("C", "D", "H"):
            pen.poly(h, ellipse(x, y + hgt * (0.55 if form != "H" else 0.25), w * 0.55, hgt * 0.3), tongue, outline=False)
        pen.poly(h, shape, None)

    def _haare(self, pen, h, haare: dict, z: Zustand, hinten: bool) -> None:
        stil, col = haare.get("stil", "kurz"), haare.get("farbe", "#3B2A20")
        ox = z.kopf_dreh * 10
        if stil == "locken":
            if hinten:
                for a in range(160, 381, 22):
                    r = math.radians(a)
                    pen.poly(h, ellipse(ox + 108 * math.cos(r), -18 + 112 * math.sin(r), 38, 36, 24), col)
            else:
                for k, dx in enumerate((-70, -30, 12, 52, 84)):
                    pen.poly(h, ellipse(ox + dx, -104 + (k % 2) * 10, 36, 30, 24), col)
        elif stil in ("zopf", "bob", "kurz"):
            if hinten:
                if stil == "zopf":
                    for k in range(7):
                        pen.poly(h, ellipse(92 + k * 3, 60 + k * 46, 26 - k, 30, 20), col)
                if stil == "bob":
                    pen.poly(h, rrect(-128, -120, 256, 230, 90), col)
                else:
                    pen.poly(h, ellipse(0, -8, 120, 128, 60), col)
            else:
                cap = np.vstack([bezier((-112, -6), (-120, -120), (-30, -150), (ox + 20, -134), 16),
                                 bezier((ox + 20, -134), (60, -150), (122, -110), (112, -6), 16),
                                 bezier((112, -6), (96, -62), (60, -88), (ox + 10, -82), 12),
                                 bezier((ox + 10, -82), (-40, -92), (-90, -70), (-112, -6), 12)])
                pen.poly(h, cap, col)
        elif stil == "glatze":
            if not hinten:
                pen.line(h, bezier((-50, -96), (-20, -116), (20, -114), n=10), "#FFFFFF", 8)
