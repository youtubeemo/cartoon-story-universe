"""Bewegungsbibliothek und Auswertung der Figurenspuren (deterministisch, wiederverwendbar).

Spuren je Figur über die ganze Folge (globale Zeit):
* Position (Gehen mit Schrittzyklus), Drehung φ (weiche Wendungen; beim Gehen Profil),
* Sitzen/Aufstehen (0,6 s), Haltungen (Armposen, 0,35 s Übergang), Einzelaktionen,
* Requisiten inkl. Übergaben (Hand zu Hand), Ausdrücke (weich überblendet),
* automatisch: Atmen, Gewichtsverlagerung, Blinzeln (auch bei Drehungen), Sprechgesten, Nicken am
  Satzende, Brauen-Betonung auf offenen Vokalen, Haarschwung.
"""
from __future__ import annotations

import math
import random

from toon.figur import AUSDRUCK, STANDARD_POSE, Zustand

UEBERGANG = 0.35
DREH = 0.35
SITZ = 0.6
SCHRITT = 115.0       # Bühnen-px je Schritt
TEMPO = 250.0         # Gehgeschwindigkeit px/s

# Haltungen: "arme" (beide), "nah"/"fern" (kameranaher/-ferner Arm), Rumpf/Kopf/Hüfte, Requisit
HALTUNGEN = {
    "stehen":            {},
    "brief_lesen":       {"arme": (-8, 35, -55, 70), "kopf": 7, "_requisit": "brief", "_hand": "beide"},
    "brief_hoch":        {"arme": (-10, 55, -40, 95), "kopf": -3, "_requisit": "brief", "_hand": "beide"},
    "brief_sinken":      {"arme": (4, 20, -20, 45), "kopf": 12, "torso": 3, "bob": 10, "_requisit": "brief",
                          "_hand": "beide"},
    "karte_ansehen":     {"nah": (-5, 40, -30, 100), "kopf": 8},
    "arme_verschraenkt": {"arme": (-6, 25, -88, 18), "kopf": -3},
    "haende_hueften":    {"arme": (38, -12, -42, -12)},
    "zeigen":            {"nah": (18, 80, 14, 86)},
    "nachdenken":        {"nah": (-12, 32, -25, 158), "fern": (-6, 22, -86, 16), "kopf": 8},
    "schultern_haengen": {"arme": (2, -4, 2, 2), "kopf": 11, "torso": 3, "bob": 12},
    "achselzucken":      {"arme": (32, 18, 52, 58), "kopf": -9, "bob": -5},
    "arme_hoch":         {"arme": (162, 8, 172, 6)},
    "haende_ausbreiten": {"arme": (42, 28, 72, 40)},
    "haende_vor_mund":   {"arme": (-12, 30, -30, 150), "kopf": 4},
    "faust":             {"nah": (20, 30, 10, 140)},
    "tasse_halten":      {"nah": (-4, 30, -20, 95), "_requisit": "tasse"},
    "lupe_halten":       {"nah": (6, 50, -10, 120), "_requisit": "lupe"},
    "taschenuhr_halten": {"nah": (-6, 45, -30, 105), "kopf": 8, "_requisit": "taschenuhr"},
}
SITZBEINE = (6.0, 88.0, 4.0, 0.0)
SITZARME = (8.0, 40.0, 4.0, 82.0)
REICHEN = (12.0, 68.0, 8.0, 80.0)
EINZEL = {"jubeln": 1.1, "nicken": 0.7, "kopfschuetteln": 0.9, "erschrecken": 0.5, "winken": 1.4,
          "seufzen": 1.2, "lachen": 1.2, "stampfen": 0.6, "zusammenzucken": 0.4}


def ease(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def glocke(u: float) -> float:
    return math.sin(math.pi * max(0.0, min(1.0, u)))


def _lerp(a, b, f):
    if isinstance(a, tuple):
        return tuple(x + (y - x) * f for x, y in zip(a, b))
    return a + (b - a) * f


def _jubeln(u: float) -> dict:
    if u < 0.18:
        k = u / 0.18
        return {"squash": 1 - 0.08 * k, "bob": 18 * k}
    if u < 0.62:
        k = (u - 0.18) / 0.44
        return {"squash": 1.06 - 0.06 * k, "bob": -150 * math.sin(math.pi * k)}
    k = (u - 0.62) / 0.38
    return {"squash": 1 - 0.07 * math.sin(math.pi * min(1, k * 2)), "bob": 12 * math.sin(math.pi * k)}


def _pose(name: str, nah_ist_links: bool) -> dict:
    h = HALTUNGEN[name]
    p = dict(STANDARD_POSE)
    for k in ("torso", "kopf", "bob"):
        if k in h:
            p[k] = h[k]
    if "arme" in h:
        p["al"] = p["ar"] = tuple(map(float, h["arme"]))
    nah, fern = ("al", "ar") if nah_ist_links else ("ar", "al")
    if "nah" in h:
        p[nah] = tuple(map(float, h["nah"]))
    if "fern" in h:
        p[fern] = tuple(map(float, h["fern"]))
    return p


def _mix_expr(a: str, b: str, f: float) -> dict:
    ea, eb = AUSDRUCK[a], AUSDRUCK[b]
    out = {k: ea.get(k, 0) + (eb.get(k, 0) - ea.get(k, 0)) * f
           for k in ("brow_y", "brow_a", "lid", "eye", "curve", "unten")}
    out["asym"] = (eb if f > 0.5 else ea).get("asym", False)
    return out


class Spur:
    """Alle Ereignisse einer Figur über die ganze Folge."""

    def __init__(self, name: str, seed: int, x0: float = 540):
        self.name = name
        self.haltungen: list[tuple[float, str]] = [(0.0, "stehen")]
        self.ausdruecke: list[tuple[float, str]] = [(0.0, "neutral")]
        self.einzel: list[tuple[float, str]] = []
        self.sprechen: list[tuple[float, float, str]] = []
        self.mund: list[tuple[float, float, str]] = []
        self.gaenge: list[tuple[float, float, float, float]] = []
        self.drehungen: list[tuple[float, float | None]] = [(0.0, None)]   # None = zum Partner
        self.sitzen: list[list] = []                                       # [hinsetzen, aufstehen|None]
        self.reichen: list[tuple[float, float]] = []
        self.requisiten: list[tuple[float, str | None]] = [(0.0, None)]
        self.x0 = x0
        self.seed = seed
        rnd = random.Random(seed)
        t, self.blinks = 0.8 + rnd.random(), []
        while t < 3600:
            self.blinks.append(t)
            t += 2.0 + rnd.random() * 3.0

    @staticmethod
    def _aktiv(liste, t):
        cur, prev, t0 = liste[0][1], liste[0][1], 0.0
        for ts, v in liste:
            if ts <= t:
                prev, cur, t0 = cur, v, ts
        return prev, cur, t0

    def x(self, t: float) -> float:
        x = self.x0
        for t0, t1, a, b in self.gaenge:
            if t >= t1:
                x = b
            elif t >= t0:
                u = (t - t0) / max(t1 - t0, 1e-6)
                # sanftes Anfahren/Abbremsen, sonst konstante Geschwindigkeit
                ue = 0.12
                if u < ue:
                    k = u * u / (2 * ue * (1 - ue))
                elif u > 1 - ue:
                    k = 1 - (1 - u) ** 2 / (2 * ue * (1 - ue))
                else:
                    k = (u - ue / 2) / (1 - ue)
                return a + (b - a) * k
        return x

    def geht(self, t: float):
        for g in self.gaenge:
            if g[0] <= t < g[1]:
                return g
        return None

    def sitzt(self, t: float) -> float:
        v = 0.0
        for a, b in self.sitzen:
            if a <= t:
                v = ease((t - a) / SITZ)
            if b is not None and b <= t:
                v = 1 - ease((t - b) / SITZ)
        return v

    def spricht(self, t: float):
        for a, b, txt in self.sprechen:
            if a <= t < b:
                return a, b, txt
        return None

    def _ziel_phi(self, t: float, partner_x) -> float:
        g = self.geht(t)
        if g:
            return 86.0 if g[3] > g[2] else -86.0
        _, d, _ = self._aktiv(self.drehungen, t)
        if d is not None:
            return float(d)
        if partner_x is None:
            return 0.0
        px = partner_x(t) if callable(partner_x) else partner_x
        return 0.0 if px is None else (30.0 if px > self.x(t) else -30.0)

    def phi(self, t: float, partner_x) -> tuple[float, bool]:
        now = self._ziel_phi(t, partner_x)
        for k in range(1, 12):
            tt = t - DREH * k / 11
            if tt < 0:
                break
            zt = self._ziel_phi(tt, partner_x)
            if abs(zt - now) > 1:
                el = DREH * (k - 0.5) / 11
                return zt + (now - zt) * ease(el / DREH), True
        return now, False

    def zustand(self, t: float, y: float, partner_x, blick_x: float | None, s: float = 1.0) -> Zustand:
        x = self.x(t)
        phi, dreht = self.phi(t, partner_x)
        nah_links = phi >= 0
        nah = "al" if nah_links else "ar"

        prev, cur, t0 = self._aktiv(self.haltungen, t)
        f = ease((t - t0) / UEBERGANG)
        pa, pb = _pose(prev, nah_links), _pose(cur, nah_links)
        pose = {k: _lerp(pa[k], pb[k], f) for k in pa}
        hn = HALTUNGEN[cur if f > 0.5 else prev]
        requisit, hand = hn.get("_requisit"), hn.get("_hand", "nah")
        eigen = self._aktiv(self.requisiten, t)[1]
        if eigen and not requisit:
            requisit, hand = eigen, "nah"

        pose["squash"] *= 1 + 0.009 * math.sin(2 * math.pi * t / 3.4)
        pose["kopf"] += 1.3 * math.sin(2 * math.pi * t / 4.3)
        pose["torso"] += 0.8 * math.sin(2 * math.pi * t / 6.1)

        sitz = self.sitzt(t)
        if sitz > 0:
            for k in ("bl", "br"):
                pose[k] = _lerp(pose[k], SITZBEINE, sitz)
            if cur == "stehen":
                for k in ("al", "ar"):
                    pose[k] = _lerp(pose[k], SITZARME, sitz)
            pose["bob"] += 132 * sitz
            # beim Hinsetzen/Aufstehen kurz nach vorn beugen
            pose["torso"] += 10 * glocke(sitz) * (1 if phi >= 0 else -1)

        g = self.geht(t)
        schwung = 0.0
        if g:
            p = math.pi * abs(x - g[2]) / SCHRITT
            st = math.sin(p)
            amp = min(1.0, (t - g[0]) / 0.2, (g[1] - t) / 0.2)
            for k, sg in (("bl", 1), ("br", -1)):
                th = 28 * st * sg * amp
                knie = max(0.0, 38 * math.sin(p + (0 if sg > 0 else math.pi) + math.pi / 2)) * amp
                pose[k] = (3.0, th, 2.0, th - knie)
            if cur == "stehen" or hn.get("_requisit") is None and "arme" not in hn:
                for k, sg in (("al", -1), ("ar", 1)):
                    if k == nah and eigen:
                        continue
                    pose[k] = (8.0, 22 * st * sg * amp, 6.0, 22 * st * sg * amp + 18)
            pose["bob"] -= 7 * abs(math.cos(p)) * amp
            pose["torso"] += 2.5 * (1 if g[3] > g[2] else -1) * amp
            schwung = 6 * st * amp

        for a, b in self.reichen:
            if a <= t <= b:
                pose[nah] = _lerp(pose[nah], REICHEN, min(1.0, glocke((t - a) / (b - a)) * 1.6))

        for ts, name in self.einzel:
            u = (t - ts) / EINZEL[name]
            if not 0 <= u <= 1:
                continue
            if name == "jubeln":
                j = _jubeln(u)
                pose["squash"] *= j["squash"]
                pose["bob"] += j["bob"]
                arm = ease(min(1, u / 0.2)) * (1 - ease((u - 0.85) / 0.15))
                for k in ("al", "ar"):
                    pose[k] = _lerp(pose[k], (160.0, 8.0, 170.0, 6.0), arm)
                schwung = -j["bob"] * 0.05
            elif name == "nicken":
                pose["nicken"] += 9 * math.sin(2 * math.pi * u * 2)
                pose["kopf"] += 3 * math.sin(2 * math.pi * u * 2)
            elif name == "kopfschuetteln":
                pose["kopf"] += 10 * math.sin(2 * math.pi * u * 3)
            elif name in ("erschrecken", "zusammenzucken"):
                pose["bob"] -= (40 if name == "erschrecken" else 18) * glocke(u)
                pose["squash"] *= 1 + 0.05 * glocke(u)
                for k in ("al", "ar"):
                    pose[k] = _lerp(pose[k], (40.0, 30.0, 80.0, 40.0), glocke(u) * 0.8)
            elif name == "winken":
                a = ease(min(1, u / 0.15)) * (1 - ease((u - 0.85) / 0.15))
                pose[nah] = _lerp(pose[nah], (150.0, 10.0, 130 + 30 * math.sin(2 * math.pi * u * 4), 10.0), a)
            elif name == "seufzen":
                pose["bob"] += 10 * glocke(u)
                pose["kopf"] += 7 * glocke(u)
                pose["squash"] *= 1 - 0.015 * glocke(u)
            elif name == "lachen":
                pose["bob"] += 6 * abs(math.sin(2 * math.pi * u * 4))
                pose["kopf"] -= 6 * glocke(u)
            elif name == "stampfen":
                pose["bob"] -= 20 * glocke(u * 2) if u < 0.5 else 0
                pose["squash"] *= 1 - 0.05 * glocke(u)

        mund = "X"
        for a, b, form in self.mund:
            if a <= t < b:
                mund = form
                break
        brow = 0.0
        sp = self.spricht(t)
        if sp:
            a, b, txt = sp
            pose["kopf"] += 2.5 * math.sin(2 * math.pi * t * 1.6)
            pose["torso"] += 1.2 * math.sin(2 * math.pi * t * 0.8)
            if mund in ("D", "C"):
                brow = -5
            if cur == "stehen" and not g and sitz < 0.5 and not any(ra <= t <= rb for ra, rb in self.reichen):
                rnd = random.Random(self.seed * 1000 + int(a * 10))
                art = "beide" if txt.rstrip().endswith("!") else rnd.choice(["nah", "nah", "fern"])
                k = glocke(min(1.0, (t - a) / max(0.6, b - a) * 1.15)) * 0.8
                if art == "beide":
                    for kk in ("al", "ar"):
                        pose[kk] = _lerp(pose[kk], (40.0, 30.0, 66.0, 42.0), k)
                else:
                    kk = nah if art == "nah" else ("ar" if nah == "al" else "al")
                    if not (kk == nah and eigen):
                        pose[kk] = _lerp(pose[kk], (22.0, 45.0, 30.0, 70.0), k)
            if b - t < 0.35 and txt.rstrip()[-1:] in ".!":
                pose["nicken"] += 6 * glocke((t - (b - 0.35)) / 0.35)

        ep, ec, te = self._aktiv(self.ausdruecke, t)
        expr = _mix_expr(ep, ec, ease((t - te) / 0.22))
        expr["brow_y"] += brow

        blink = 0.0
        for tb in self.blinks:
            if tb - 0.08 <= t <= tb + 0.1:
                blink = 1 - abs(t - tb) / 0.1
                break
            if tb > t:
                break
        if dreht and not g:
            blink = max(blink, 0.75)

        kopf_phi = 0.0
        if blick_x is not None and not g:
            richtung = 1 if blick_x > x else -1
            kopf_phi = max(-20.0, min(20.0, richtung * 50 - phi)) * 0.4
        return Zustand(x=x, y=y, s=s, phi=phi, kopf_phi=kopf_phi, pose=pose, ausdruck=expr, blinzeln=max(0.0, blink),
                       mund=mund, blick=(0.0 if blick_x is None else (0.7 if blick_x > x else -0.7), 0.0),
                       requisit=requisit, requisit_hand=hand, haar_schwung=schwung)
