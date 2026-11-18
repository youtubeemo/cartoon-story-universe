"""Wiederverwendbares 2D-Charakter-Rig (Cut-out, „2,5D“) – eine Figur = eine YAML-Beschreibung.

Jede Figur ist eine flache Puppe, deren Teile auf einem einfachen 3D-Gerüst sitzen:
* Körperdrehung φ (−90° Profil links … 0° vorne … +90° Profil rechts) – stufenlos, dadurch fließende
  Übergänge zwischen Vorder-, Dreiviertel- und Seitenansicht. Kopf kann sich zusätzlich drehen.
* Arme/Beine: je zwei Segmente mit Richtung (seitlich a, vorwärts f) → echte Verkürzung, nahes/fernes Glied
  wird vor/hinter dem Körper gezeichnet (Gehen, Sitzen, Übergeben, Verschränken).
* Gesicht auf einer Kugel: Augen, Nase, Mund, Ohren, Brauen wandern mit der Drehung; im Profil ragt die Nase heraus.
* 9 Mundformen (A–H, X), Ausdrucksparameter, Blinzeln, Blickrichtung, Frisuren, Kleidung, Hüte, Brillen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from toon.geo import M, bezier, capsule, ellipse, mix, rrect

AUSDRUCK = {
    "neutral":     {"brow_y": -5,  "brow_a": -2,  "lid": 0.06, "eye": 1.0,  "curve": 0.45, "unten": 0.0},
    "froh":        {"brow_y": -8,  "brow_a": -4,  "lid": 0.0,  "eye": 1.0,  "curve": 1.0,  "unten": 0.25},
    "begeistert":  {"brow_y": -16, "brow_a": -6,  "lid": 0.0,  "eye": 1.14, "curve": 1.0,  "unten": 0.2},
    "ueberrascht": {"brow_y": -20, "brow_a": 0,   "lid": 0.0,  "eye": 1.2,  "curve": 0.0,  "unten": 0.0},
    "traurig":     {"brow_y": -4,  "brow_a": 20,  "lid": 0.34, "eye": 0.95, "curve": -0.8, "unten": 0.0},
    "besorgt":     {"brow_y": -8,  "brow_a": 15,  "lid": 0.14, "eye": 1.0,  "curve": -0.4, "unten": 0.0},
    "wuetend":     {"brow_y": 4,   "brow_a": -26, "lid": 0.24, "eye": 0.95, "curve": -0.55, "unten": 0.1},
    "skeptisch":   {"brow_y": -2,  "brow_a": -10, "lid": 0.34, "eye": 1.0,  "curve": -0.15, "unten": 0.0, "asym": True},
    "verschmitzt": {"brow_y": -5,  "brow_a": -12, "lid": 0.28, "eye": 1.0,  "curve": 0.75, "unten": 0.2, "asym": True},
    "entschlossen": {"brow_y": 0,  "brow_a": -14, "lid": 0.12, "eye": 1.0,  "curve": 0.1,  "unten": 0.0},
    "aengstlich":  {"brow_y": -14, "brow_a": 22,  "lid": 0.0,  "eye": 1.15, "curve": -0.5, "unten": 0.0},
}
MUNDFORMEN = "ABCDEFGHX"

# Gliedmaßen: (a1, f1, a2, f2) = Oberarm/Oberschenkel und Unterarm/Unterschenkel, Winkel in Grad
#   a = seitlich nach außen (negativ = vor den Körper nach innen), f = nach vorne (negativ = nach hinten)
STANDARD_POSE = {"torso": 0.0, "kopf": 0.0, "bob": 0.0, "squash": 1.0, "nicken": 0.0,
                 "al": (9.0, 4.0, 6.0, 14.0), "ar": (9.0, 4.0, 6.0, 14.0),
                 "bl": (3.0, 0.0, 2.0, 0.0), "br": (3.0, 0.0, 2.0, 0.0)}


@dataclass
class Zustand:
    x: float = 540
    y: float = 2000
    s: float = 1.0
    phi: float = 0.0               # Körperdrehung in Grad
    kopf_phi: float = 0.0          # zusätzliche Kopfdrehung
    pose: dict = field(default_factory=lambda: dict(STANDARD_POSE))
    ausdruck: object = "neutral"
    blinzeln: float = 0.0
    mund: str = "X"
    blick: tuple = (0.0, 0.0)
    requisit: str | None = None
    requisit_hand: str = "nah"     # nah | beide
    haar_schwung: float = 0.0


def _richtung(a: float, f: float) -> np.ndarray:
    a, f = math.radians(a), math.radians(f)
    return np.array([math.sin(a) * math.cos(f), math.cos(a) * math.cos(f), math.sin(f)])


class Figur:
    def __init__(self, d: dict):
        self.d = d
        self.g = float(d.get("groesse", 1.0))
        self.w = {"schlank": 0.88, "normal": 1.0, "kraeftig": 1.18, "rund": 1.3}[d.get("koerper", "normal")]
        self.haut = d.get("haut", "#F2C9A8")
        self.haut_dunkel = mix(self.haut, "#7A4A3A", 0.18)

    # ------------------------------------------------------------- Projektion
    @staticmethod
    def _proj(p: np.ndarray, phi: float) -> tuple[float, float, float]:
        """Körper-3D (x seitlich, y nach unten, z nach vorn) → Bildschirm (X, Y) und Tiefe (zur Kamera positiv)."""
        c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
        return p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c

    def _glied(self, base3: np.ndarray, l1: float, l2: float, pose: tuple, seite: int):
        a1, f1, a2, f2 = pose
        d1 = _richtung(a1, f1) * np.array([seite, 1, 1])
        d2 = _richtung(a2, f2) * np.array([seite, 1, 1])
        j = base3 + d1 * l1
        return base3, j, j + d2 * l2

    def _glieder(self, z: Zustand) -> dict:
        g, w, p = self.g, self.w, z.pose
        out = {}
        for key, seite, base, l1, l2 in (
                ("bl", -1, np.array([-38.0 * w, -6, 0]), 150 * g, 148 * g),
                ("br", 1, np.array([38.0 * w, -6, 0]), 150 * g, 148 * g),
                ("al", -1, np.array([-78.0 * w, -215 * g + 22, 0]), 112 * g, 106 * g),
                ("ar", 1, np.array([78.0 * w, -215 * g + 22, 0]), 112 * g, 106 * g)):
            pts = [self._proj(q, z.phi) for q in self._glied(base, l1, l2, p[key], seite)]
            out[key] = (pts, sum(q[2] for q in pts) / 3, seite)
        return out

    # ------------------------------------------------------------- Zeichnen
    def zeichne(self, pen, z: Zustand) -> None:
        d, g, w, p = self.d, self.g, self.w, z.pose
        phi = z.phi
        cphi, sphi = math.cos(math.radians(phi)), math.sin(math.radians(phi))
        root = M(z.x, z.y, 0, z.s, z.s * p["squash"])
        hip = root @ M(0, -300 * g + p["bob"])
        torso = hip @ M(0, 0, p["torso"])
        sh_y = -215 * g
        top = d.get("jacke", {}).get("farbe", d["oberteil"]) if d.get("jacke") else d["oberteil"]
        sleeve = d.get("aermel", top)
        glieder = self._glieder(z)
        frames = {"bl": hip, "br": hip, "al": torso, "ar": torso}

        def zeichne_bein(key):
            pts, _, seite = glieder[key]
            (x0, y0, _), (x1, y1, _), (x2, y2, _) = pts
            f = frames[key]
            pen.poly(f, capsule(x0, y0, x1, y1, 31 * w, 27 * w), d["hose"])
            pen.poly(f, capsule(x1, y1, x2, y2, 27 * w, 24 * w), d["hose"])
            vor = 18 * sphi if abs(sphi) > 0.3 else seite * 14
            pen.poly(f, ellipse(x2 + vor, y2 + 4, 40, 21), d.get("schuhe", "#3A3A3A"))

        def zeichne_arm(key):
            pts, _, seite = glieder[key]
            (x0, y0, _), (x1, y1, _), (x2, y2, _) = pts
            f = frames[key]
            pen.poly(f, capsule(x0, y0, x1, y1, 23 * w, 21 * w), sleeve)
            pen.poly(f, capsule(x1, y1, x2, y2, 20 * w, 18 * w), sleeve if d.get("lange_aermel", True) else self.haut)
            pen.poly(f, ellipse(x2, y2 + 6, 25, 26), self.haut)
            daumen = 16 * sphi if abs(sphi) > 0.3 else -seite * 18
            pen.poly(f, ellipse(x2 + daumen, y2 - 4, 10, 13), self.haut)

        pen.poly(M(z.x, z.y, 0, z.s, z.s), ellipse(0, 4, 120 * w, 22), mix(pen.boden or "#B9825A", "#000000", 0.25),
                 outline=False)
        head = torso @ M(0, sh_y) @ M(0, -12, p["kopf"]) @ M(0, -118 * g + p.get("nicken", 0))
        hphi = phi + z.kopf_phi
        self._haare(pen, head, z, hphi, hinten=True)
        if d.get("rucksack") and abs(sphi) > 0.2:
            rx = -sphi * 70
            pen.poly(torso, rrect(rx - 60, -205 * g, 120, 175 * g, 40), d["rucksack"])

        order = sorted(glieder, key=lambda k: glieder[k][1])
        for k in order:
            if glieder[k][1] < -8:
                (zeichne_bein if k.startswith("b") else zeichne_arm)(k)
        for k in ("bl", "br"):
            if glieder[k][1] >= -8:
                zeichne_bein(k)

        bw = 80 * w * abs(cphi) + 50 * w * abs(sphi)
        hw = 72 * w * abs(cphi) + 48 * w * abs(sphi)
        body = np.vstack([bezier((-hw, 8), (-hw - 10, -90 * g), (-bw - 12, -170 * g), (-bw, -215 * g), 14),
                          bezier((-bw, -215 * g), (-30, -234 * g), (30, -234 * g), (bw, -215 * g), 10),
                          bezier((bw, -215 * g), (bw + 12, -170 * g), (hw + 10, -90 * g), (hw, 8), 14),
                          bezier((hw, 8), (20, 22), (-20, 22), (-hw, 8), 8)])
        if d.get("mantel"):
            pen.poly(torso, np.vstack([bezier((-hw - 4, 0), (-hw - 34, 120), (-hw - 26, 170), (-hw + 6, 178), 8),
                                       bezier((hw - 6, 178), (hw + 26, 170), (hw + 34, 120), (hw + 4, 0), 8)]), d["mantel"])
        pen.poly(torso, body, top)
        vx = bw * sphi * 0.8
        fw = max(0.25, abs(cphi))
        if d.get("jacke", {}).get("offen"):
            pen.poly(torso, rrect(vx - 24 * fw, -224 * g, 48 * fw, 234 * g, 8), d["jacke"].get("innen", "#FFFFFF"))
        if d.get("weste"):
            pen.poly(torso, np.array([[vx - 42 * fw, -205 * g], [vx + 42 * fw, -205 * g], [vx + 56 * fw, 0],
                                      [vx - 56 * fw, 0]]), d["weste"])
        if d.get("krawatte"):
            pen.poly(torso, np.array([[vx - 9 * fw, -214 * g], [vx + 9 * fw, -214 * g], [vx + 14 * fw, -110 * g],
                                      [vx, -85 * g], [vx - 14 * fw, -110 * g]]), d["krawatte"])
        if d.get("schuerze"):
            pen.poly(torso, rrect(vx - 60 * w * fw, -150 * g, 120 * w * fw, 195 * g, 22), d["schuerze"])
            pen.line(torso, [(vx - 40 * fw, -150 * g), (vx - 28 * fw, -222 * g)], d["schuerze"], 9)
            pen.line(torso, [(vx + 40 * fw, -150 * g), (vx + 28 * fw, -222 * g)], d["schuerze"], 9)
        if d.get("guertel"):
            pen.poly(torso, rrect(-hw - 2, -30, 2 * hw + 4, 26, 6), d["guertel"])
        if d.get("streifen"):
            for yy in (-150, -90):
                pen.poly(torso, rrect(-bw, yy * g, 2 * bw, 16, 4), d["streifen"], outline=False)
        if d.get("knoepfe"):
            for yy in (-180, -130, -80):
                pen.dot(torso, vx, yy * g, 7, d["knoepfe"])
        if d.get("rucksack") and abs(sphi) <= 0.6:
            for sx in (-1, 1):
                pen.line(torso, [(vx + sx * 52 * w * fw, -222 * g), (vx + sx * 60 * w * fw, -110 * g)], d["rucksack"], 13)

        pen.poly(torso @ M(0, sh_y), rrect(-22, -30, 44, 40, 12), self.haut_dunkel)
        self._kopf(pen, head, z, hphi)
        if d.get("schulter_vogel"):
            self._vogel(pen, torso @ M(-60 * w * cphi, sh_y - 40), d["schulter_vogel"], z)

        for k in order:
            if k.startswith("a") and glieder[k][1] >= -8:
                zeichne_arm(k)
        if z.requisit:
            self._requisit(pen, glieder, frames, z)

    def _vogel(self, pen, m, farbe, z) -> None:
        pen.poly(m, ellipse(0, -20, 26, 34), farbe)
        pen.poly(m, ellipse(4, -58, 20, 20), farbe)
        pen.poly(m, np.array([[20, -60], [38, -52], [20, -48]]), "#F2B134")
        pen.dot(m, 8, -62, 4, "#1B1B1F")
        pen.poly(m, np.array([[-10, 10], [-24, 40], [4, 12]]), mix(farbe, "#000000", 0.2))

    def hand_position(self, z: Zustand) -> tuple[float, float]:
        """Bühnenkoordinaten der kameranahen Hand (für Übergaben)."""
        glieder = self._glieder(z)
        key = max(("al", "ar"), key=lambda k: glieder[k][1])
        x, y, _ = glieder[key][0][2]
        a = math.radians(z.pose["torso"])
        xr, yr = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
        return z.x + xr * z.s, z.y + (-300 * self.g + z.pose["bob"] + yr) * z.s * z.pose["squash"]

    def _requisit(self, pen, glieder, frames, z) -> None:
        def hand(k):
            x, y, _ = glieder[k][0][2]
            return (frames[k] @ np.array([x, y + 6, 1]))[:2]
        hl, hr = hand("al"), hand("ar")
        if z.requisit_hand == "beide":
            cx, cy = (hl + hr) / 2
            span = abs(hr[0] - hl[0]) / max(z.s, 1e-6)
        else:
            cx, cy = hand(max(("al", "ar"), key=lambda k: glieder[k][1]))
            span = 0
        m = M(cx, cy - 18 * z.s, -4, z.s, z.s)
        zeichne_requisit(pen, m, z.requisit, span if z.requisit_hand == "beide" else 0)

    # ------------------------------------------------------------- Kopf und Gesicht
    @staticmethod
    def _kugel(theta: float, hphi: float, r: float = 108) -> tuple[float, float]:
        a = theta + math.radians(hphi)
        return r * math.sin(a), math.cos(a)

    def _kopf(self, pen, h, z: Zustand, hphi: float) -> None:
        d = self.d
        e = z.ausdruck if isinstance(z.ausdruck, dict) else AUSDRUCK.get(z.ausdruck, AUSDRUCK["neutral"])
        sp = math.sin(math.radians(hphi))
        ohren = [self._kugel(th, hphi, 104) for th in (-math.pi / 2, math.pi / 2)]
        for x, dep in ohren:
            if -0.3 < dep <= 0.5:
                pen.poly(h, ellipse(x, 8, 20 - 6 * abs(dep), 26), self.haut)
        pen.poly(h, ellipse(0, 0, 112, 120, 72), self.haut)
        for x, dep in ohren:      # im Profil liegt das nahe Ohr auf der Kopfseite
            if dep > 0.5:
                pen.poly(h, ellipse(x, 8, 17, 25), self.haut)
                pen.line(h, bezier((x - 5, -4), (x + 6, 8), (x - 3, 20), n=6), self.haut_dunkel, 4)
        if d.get("backenbart"):
            for th in (-1.2, 1.2):
                x, dep = self._kugel(th, hphi, 100)
                if dep > -0.2:
                    pen.poly(h, ellipse(x, 40, 30 * (0.5 + 0.5 * max(dep, 0)), 46), d["backenbart"])
        if d.get("sommersprossen"):
            for th in (-0.62, 0.62):
                x, dep = self._kugel(th, hphi)
                if dep > 0.1:
                    for dx, dy in ((-8, 30), (4, 24), (0, 40), (12, 34)):
                        pen.dot(h, x + dx * dep, dy, 3.2, mix(self.haut, "#B5651D", 0.55))
        for th in (-0.6, 0.6):
            x, dep = self._kugel(th, hphi)
            if dep > 0.15:
                pen.poly(h, ellipse(x, 44, 20 * dep, 12), mix(self.haut, "#E8707A", 0.32), outline=False)
        for sx, th in ((-1, -0.38), (1, 0.38)):
            x, dep = self._kugel(th, hphi)
            if dep > 0.08:
                self._auge(pen, h, x, -8, e, z, sx, dep)
        x, _ = self._kugel(0, hphi, 112)
        if abs(sp) > 0.55:
            sg = 1 if sp > 0 else -1
            pen.poly(h, np.array([[x - sg * 12, 0], [x + sg * 26, 26], [x - sg * 6, 34]]), self.haut)
        else:
            pen.poly(h, ellipse(x * 0.95, 22, 12, 9), self.haut_dunkel)
        mx, mdep = self._kugel(0, hphi, 96)
        breite = 0.5 + 0.5 * max(0.0, mdep)
        self._mund(pen, h @ M(mx, 66, 0, 1.55 * breite, 1.55), z.mund, e["curve"])
        if d.get("schnurrbart"):
            for sx in (-1, 1):
                ex = mx + sx * 60 * breite
                pen.poly(h, np.vstack([bezier((mx, 44), (mx + sx * 30 * breite, 36), (ex - sx * 10, 42), (ex, 30), 10),
                                       bezier((ex, 30), (ex - sx * 18, 52), (mx + sx * 18 * breite, 52), (mx, 50), 10)]),
                         d.get("schnurrbart_farbe", "#1B1B1F"))
        if d.get("bart"):
            pen.poly(h, np.vstack([bezier((mx - 70 * breite, 44), (mx - 60 * breite, 124), (mx + 60 * breite, 124),
                                          (mx + 70 * breite, 44), 16),
                                   bezier((mx + 70 * breite, 44), (mx + 30, 96), (mx - 30, 96), (mx - 70 * breite, 44), 10)]),
                     d["bart"])
        self._accessoires(pen, h, z, hphi)
        self._haare(pen, h, z, hphi, hinten=False)
        hut = d.get("hut")
        if hut:
            self._hut(pen, h, hut, sp)

    def _accessoires(self, pen, h, z, hphi) -> None:
        d = self.d
        eyes = [self._kugel(th, hphi) for th in (-0.38, 0.38)]
        brille = d.get("brille")
        if brille:
            farbe = brille.get("farbe", "#1B1B1F") if isinstance(brille, dict) else brille
            art = brille.get("art", "rund") if isinstance(brille, dict) else "rund"
            y = -98 if art in ("flieger", "lupe") else -8
            if art in ("flieger", "schweiss", "lupe"):
                pen.line(h, [(-110, y), (110, y)], "#5A3A2A", 9)
            for x, dep in eyes:
                if dep > 0.08:
                    rx = 36 * (0.35 + 0.65 * dep)
                    if art in ("flieger", "schweiss", "lupe"):
                        pen.poly(h, ellipse(x, y, rx, 30), "#7FC8E8" if art != "lupe" else "#CFEFF5")
                    ring = ellipse(x, y, rx, 34 if art == "rund" else 30, 40)
                    pen.line(h, np.vstack([ring, ring[:1]]), farbe, 7)
            if eyes[0][1] > 0.08 and eyes[1][1] > 0.08 and art == "rund":
                pen.line(h, [(eyes[0][0] + 30, y - 2), (eyes[1][0] - 30, y - 2)], farbe, 6)
        if d.get("monokel"):
            x, dep = eyes[1]
            if dep > 0.08:
                ring = ellipse(x, -8, 36 * dep + 6, 36, 30)
                pen.line(h, np.vstack([ring, ring[:1]]), "#C9A04A", 6)
                pen.line(h, bezier((x + 30 * dep, 10), (x + 40, 80), (x + 10, 140), n=10), "#C9A04A", 3)
        if d.get("augenklappe"):
            x, dep = eyes[0]
            pen.line(h, [(-110, -66), (110, -12)], "#1B1B1F", 6)
            if dep > 0.08:
                pen.poly(h, ellipse(x, -8, 32 * (0.4 + 0.6 * dep), 30), "#1B1B1F")
        if d.get("headset"):
            pen.line(h, bezier((-104, 10), (-104, -150), (104, -150), (104, 10), 16), "#3A3A44", 10)
            x, dep = self._kugel(-math.pi / 2, hphi, 104)
            if dep > -0.3:
                pen.poly(h, ellipse(x, 10, 16, 24), "#E4572E")
                pen.line(h, bezier((x, 30), (x + 20, 70), (x + 60, 72), n=8), "#3A3A44", 5)

    def _hut(self, pen, h, hut, sp) -> None:
        art, farbe = hut["art"], hut["farbe"]
        if art == "dreispitz":
            pen.poly(h, np.array([[-150, -90], [sp * 20, -190], [150, -90], [60 + sp * 30, -110], [-60 + sp * 30, -110]]),
                     farbe)
            pen.poly(h, ellipse(sp * 40, -112, 70, 10), mix(farbe, "#FFFFFF", 0.2))
        elif art == "glocke":
            pen.poly(h, bezier((-118, -50), (-120, -175), (120, -175), (118, -50), 18), farbe)
            pen.poly(h, rrect(-130 + sp * 10, -62, 260, 22, 10), farbe)
            pen.poly(h, rrect(-110, -82, 220, 14, 5), mix(farbe, "#000000", 0.25))
        elif art == "helm":
            pen.poly(h, bezier((-126, 14), (-132, -172), (132, -172), (126, 14), 20), farbe)
            pen.poly(h, rrect(-104 + sp * 30, -64, 208, 30, 8), mix(farbe, "#000000", 0.3))
            pen.poly(h, ellipse(-sp * 30, -172, 22, 42), hut.get("feder", "#E4572E"))
        elif art == "dutt":
            pen.poly(h, ellipse(-sp * 50, -132, 40, 34), farbe)
        elif art == "muetze":
            pen.poly(h, bezier((-112, -40), (-110, -150), (110, -150), (112, -40), 16), farbe)

    def _auge(self, pen, h, x, y, e, z, sx, dep) -> None:
        rx, ry = 27 * e["eye"] * (0.35 + 0.65 * dep), 33 * e["eye"]
        pen.poly(h, ellipse(x, y, rx, ry, 40), "#FFFFFF")
        bx, by = z.blick
        px = x + bx * 9 * (0.4 + 0.6 * dep)
        pen.dot(h, px, y + by * 9 + 4, 13 * (0.5 + 0.5 * dep), self.d.get("augen", "#3B2A20"))
        pen.dot(h, px + 4, y + by * 9 - 2, 4, "#FFFFFF")
        lid = max(e["lid"], z.blinzeln)
        if e.get("asym") and sx > 0 and z.blinzeln < 0.5:
            lid = min(1.0, lid + 0.15)
        if lid > 0.02:
            cut = y - ry + 2 * ry * lid
            pts = ellipse(x, y, rx + 1, ry + 1, 40)
            top = pts[pts[:, 1] <= cut]
            if len(top) >= 3:
                top = top[np.argsort(np.arctan2(top[:, 1] - y, top[:, 0] - x))]
                pen.poly(h, np.vstack([top, [[x + rx, cut], [x - rx, cut]]]), self.haut, outline=False)
                pen.line(h, [(x - rx * 0.98, cut), (x + rx * 0.98, cut)], None, 5)
        if e.get("unten", 0) > 0.05 and z.blinzeln < 0.3:
            yb = y + ry - 4
            pen.line(h, bezier((x - rx * 0.8, yb), (x, yb - 12 * e["unten"]), (x + rx * 0.8, yb), n=8), None, 4)
        by_ = y - ry - 18 + e["brow_y"]
        a = e["brow_a"] * sx
        if e.get("asym") and sx > 0:
            by_ -= 10
            a *= -0.5
        bw = 23 * (0.4 + 0.6 * dep)
        m = M(x, by_, a) @ M(-x, -by_)
        haare = self.d.get("haare", {})
        pen.line(h @ m, bezier((x - sx * bw, by_), (x, by_ - 7), (x + sx * bw, by_), n=8),
                 haare.get("brauen", haare.get("farbe", "#2B2B2B")), 10)

    @staticmethod
    def _mund(pen, h, form: str, curve: float) -> None:
        dark, tongue, teeth = "#5A1E24", "#E06A78", "#FFFFFF"
        c = curve * 12
        if form in ("X", "A"):
            w = 22 if form == "X" else 17
            pen.line(h, bezier((-w, -c * 0.6), (0, c), (w, -c * 0.6), n=12), None, 4.5)
            if curve > 0.7 and form == "X":
                for sx in (-1, 1):
                    pen.line(h, [(sx * w * 0.95, -c * 0.6 - 3), (sx * (w + 4), -c * 0.6 + 4)], None, 3.5)
            return
        w, hgt = {"B": (19, 7), "C": (21, 13), "D": (24, 21), "E": (16, 16), "F": (10, 10),
                  "G": (19, 8), "H": (21, 15)}[form]
        upper = bezier((-w, -c * 0.4), (0, -hgt * 0.35 + c * 0.25), (w, -c * 0.4), n=12)
        lower = bezier((w, -c * 0.4), (0, hgt + c * 0.45), (-w, -c * 0.4), n=12)
        shape = np.vstack([upper, lower])
        pen.poly(h, shape, dark, lw=4.5)
        if form in ("B", "C", "D", "G"):
            pen.poly(h, rrect(-w * 0.72, -hgt * 0.3 + c * 0.15, w * 1.44, max(3.5, hgt * 0.3), 3), teeth, outline=False)
        if form == "G":
            pen.poly(h, rrect(-w * 0.6, hgt * 0.15, w * 1.2, 4, 2), "#E8A8A8", outline=False)
        if form in ("C", "D", "H"):
            pen.poly(h, ellipse(0, hgt * (0.58 if form != "H" else 0.2), w * 0.55, hgt * 0.3), tongue, outline=False)
        pen.poly(h, shape, None, lw=4.5)

    def _haare(self, pen, h, z: Zustand, hphi: float, hinten: bool) -> None:
        haare = self.d.get("haare", {})
        stil, col = haare.get("stil", "kurz"), haare.get("farbe", "#3B2A20")
        sp = math.sin(math.radians(hphi))
        sw = z.haar_schwung
        if stil == "locken":
            for th in np.linspace(-math.pi, math.pi, 17)[:-1]:
                for y, rr in ((-104, 112), (-56, 118)):
                    x, dep = self._kugel(th, hphi, rr)
                    if hinten and dep < 0.25:
                        pen.poly(h, ellipse(x, y - (8 if y < -80 else 0) + sw * 0.3, 36, 32, 24), col)
                    elif not hinten and dep >= 0.25 and y < -80:
                        pen.poly(h, ellipse(x, y - 8 + sw * 0.3, 36, 32, 24), col)
                    elif not hinten and dep < -0.2 and abs(sp) > 0.35:   # Hinterkopf im Profil
                        pen.poly(h, ellipse(x * 0.9, y + 6 + sw * 0.3, 38, 36, 24), col)
            if not hinten:
                for th in (-0.7, -0.3, 0.1, 0.5):
                    x, dep = self._kugel(th, hphi, 100)
                    if dep > 0.2:
                        pen.poly(h, ellipse(x, -106 + sw * 0.4, 34, 28, 24), col)
            return
        if stil == "glatze":
            if not hinten:
                pen.line(h, bezier((-50 + sp * 30, -96), (-20 + sp * 30, -116), (20 + sp * 30, -114), n=10), "#FFFFFF", 8)
                for th in (-math.pi / 2, math.pi / 2):
                    x, dep = self._kugel(th, hphi, 98)
                    if dep > -0.2:
                        pen.poly(h, ellipse(x, -20, 18, 34), col)
            return
        if hinten:
            if stil == "zopf":
                bx = -sp * 70 + (40 if abs(sp) < 0.3 else 0)
                for k in range(7):
                    pen.poly(h, ellipse(bx + sw * k * 0.6, 60 + k * 46, 26 - k, 30, 20), col)
            if stil in ("bob", "lang"):
                tief = 110 if stil == "bob" else 260
                pen.poly(h, rrect(-128 - sp * 10, -122, 256, 120 + tief, 90), col)
            elif stil == "pferdeschwanz":
                bx = -sp * 110
                pen.poly(h, capsule(bx, -60, bx - sp * 30 + sw, 120, 32, 18), col)
            elif stil == "undercut":
                return
            pen.poly(h, ellipse(-sp * 16, -8, 120, 128, 60), col)
            return
        ox = sp * 60
        if stil == "undercut":
            pen.poly(h, np.vstack([bezier((-96, -60), (-90, -150), (60 + ox, -170), (110, -80), 14),
                                   bezier((110, -80), (60 + ox, -110), (0 + ox, -100), (-96, -60), 10)]), col)
            return
        cap = np.vstack([bezier((-112, -6), (-120, -120), (-30 + ox * 0.3, -150), (ox * 0.4 + 20, -134), 16),
                         bezier((ox * 0.4 + 20, -134), (60 + ox * 0.3, -150), (122, -110), (112, -6), 16),
                         bezier((112, -6), (96 - min(0, ox) * 1.2, -62), (60 + ox, -88), (ox + 10, -82), 12),
                         bezier((ox + 10, -82), (-40 + ox, -92), (-90 - max(0, ox) * 1.2, -70), (-112, -6), 12)])
        pen.poly(h, cap, col)
        if abs(sp) > 0.35:
            sg = 1 if sp > 0 else -1
            back = np.vstack([bezier((sg * 30, -124), (-sg * 60, -140), (-sg * 126, -60), (-sg * 112, 20), 14),
                              bezier((-sg * 112, 20), (-sg * 70, 10), (-sg * 40, -30), (-sg * 10, -60), 10)])
            pen.poly(h, back, col)


def zeichne_requisit(pen, m, r: str, span: float = 0) -> None:
    """Requisiten – auch für Übergaben und als Gegenstand im Raum verwendbar."""
    if r == "brief":
        hw = min(110.0, max(55.0, span / 2 - 14)) if span else 52
        pen.poly(m, rrect(-hw, -78, 2 * hw, 140, 6), "#FBF8F0")
        for k in range(5):
            pen.line(m, [(-hw * 0.7, -50 + 21 * k), (hw * 0.63 - (k % 2) * 16, -50 + 21 * k)], "#9AA3AE", 4)
    elif r == "karte":
        pen.poly(m, rrect(-44, -28, 88, 54, 5), "#E9E2FF")
        pen.line(m, [(-28, -6), (22, -6)], "#6B4FA0", 5)
        pen.line(m, [(-28, 10), (8, 10)], "#6B4FA0", 4)
    elif r == "scheine":
        for k in range(3):
            pen.poly(m @ M(k * 6, -k * 6, k * 4), rrect(-55, -28, 110, 56, 5), "#9ED29A")
    elif r == "tasse":
        pen.poly(m, rrect(-26, -40, 52, 56, 10), "#FFFFFF")
        pen.line(m, bezier((26, -28), (48, -20), (26, 0), n=8), None, 7)
    elif r == "lupe":
        pen.line(m, [(0, 0), (34, 34)], "#6B4A2A", 12)
        pen.poly(m, ellipse(-14, -14, 30, 30), "#CFEFF5")
    elif r == "taschenuhr":
        pen.poly(m, ellipse(0, 0, 30, 30), "#E2B64A")
        pen.poly(m, ellipse(0, 0, 22, 22), "#FFF8E0")
        pen.line(m, [(0, 0), (0, -14)], None, 4)
        pen.line(m, [(0, 0), (10, 4)], None, 4)
    elif r == "pfanne":
        pen.line(m, [(0, 0), (-60, 10)], "#3A3A3A", 12)
        pen.poly(m, ellipse(36, 0, 46, 18), "#4A4A4A")
    elif r == "fernrohr":
        pen.poly(m, np.array([[-60, -12], [60, -18], [60, 18], [-60, 12]]), "#C9A04A")
    elif r == "werkzeug":
        pen.line(m, [(-30, 30), (30, -30)], "#8A8A8A", 12)
        pen.poly(m, ellipse(30, -30, 16, 16), "#8A8A8A")
    elif r == "kokosnuss":
        pen.poly(m, ellipse(0, 0, 30, 28), "#6B4A2A")
    elif r == "kartenteil":
        pen.poly(m, np.array([[-40, -30], [36, -36], [44, 28], [-34, 34]]), "#E9D8A6")
        pen.line(m, [(-20, -10), (0, 10), (20, -6)], "#B5651D", 4)
