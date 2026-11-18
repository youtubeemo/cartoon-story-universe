"""Bewegungsbibliothek und Auswertung der Figurenspuren (alles wiederverwendbar, deterministisch).

* Haltungen (halten, bis die nächste kommt; weicher Übergang 0,35 s): stehen, brief_lesen, arme_verschraenkt, …
* Einzelaktionen (kehren zur Haltung zurück): jubeln (Sprung mit Stauchen/Strecken), nicken, kopfschuetteln, …
* Automatisch: Atmen, Blinzeln (zufällig, reproduzierbar), Blick zum Gesprächspartner, Kopfbewegung beim Sprechen.
* Ausdrücke werden weich überblendet (Brauen, Lider, Mundkrümmung).
"""
from __future__ import annotations

import math
import random

from toon.figur import AUSDRUCK, STANDARD_POSE, Zustand

UEBERGANG = 0.35

HALTUNGEN = {
    "stehen":            {},
    "brief_lesen":       {"al": (-18, 98), "ar": (-18, 98), "kopf": 6, "_requisit": "brief"},
    "brief_hoch":        {"al": (-30, 112), "ar": (-30, 112), "kopf": -4, "_requisit": "brief"},
    "brief_sinken":      {"al": (6, 45), "ar": (6, 45), "kopf": 10, "torso": 4, "bob": 14, "_requisit": "brief"},
    "karte_halten":      {"ar": (-10, 100), "kopf": 5, "_requisit": "karte", "_hand": "r"},
    "arme_verschraenkt": {"al": (-28, 112), "ar": (-28, 112), "kopf": -3},
    "haende_hueften":    {"al": (38, -105), "ar": (38, -105), "torso": 0},
    "zeigen":            {"ar": (82, 6)},
    "nachdenken":        {"ar": (-12, 150), "al": (-20, 100), "kopf": 8},
    "schultern_haengen": {"al": (3, 3), "ar": (3, 3), "kopf": 10, "torso": 4, "bob": 14},
    "achselzucken":      {"al": (48, -95), "ar": (48, -95), "kopf": -8, "bob": -6},
    "arme_hoch":         {"al": (155, 15), "ar": (155, 15)},
}

# Einzelaktionen: Dauer und Funktion u∈[0,1] → Zusatzwerte
def _jubeln(u: float) -> dict:
    if u < 0.18:                        # Ausholen (stauchen)
        k = u / 0.18
        return {"squash": 1 - 0.08 * k, "bob": 18 * k, "arme": 0.0}
    if u < 0.62:                        # Sprung (strecken)
        k = (u - 0.18) / 0.44
        return {"squash": 1.06 - 0.06 * k, "bob": -150 * math.sin(math.pi * k), "arme": 1.0}
    k = (u - 0.62) / 0.38               # Landung
    return {"squash": 1 - 0.07 * math.sin(math.pi * min(1, k * 2)), "bob": 12 * math.sin(math.pi * k), "arme": 1.0 - k * 0}


EINZEL = {
    "jubeln": 1.1,
    "nicken": 0.7,
    "kopfschuetteln": 0.9,
    "erschrecken": 0.5,
    "winken": 1.4,
    "seufzen": 1.2,
}


def ease(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def _mix_pose(a: dict, b: dict, f: float) -> dict:
    out = {}
    for k in STANDARD_POSE:
        va, vb = a.get(k, STANDARD_POSE[k]), b.get(k, STANDARD_POSE[k])
        if isinstance(va, tuple):
            out[k] = tuple(x + (y - x) * f for x, y in zip(va, vb))
        else:
            out[k] = va + (vb - va) * f
    return out


def _pose(name: str) -> dict:
    p = dict(STANDARD_POSE)
    p.update({k: v for k, v in HALTUNGEN[name].items() if not k.startswith("_")})
    return p


def _mix_expr(a: str, b: str, f: float) -> dict:
    ea, eb = AUSDRUCK[a], AUSDRUCK[b]
    out = {k: ea.get(k, 0) + (eb.get(k, 0) - ea.get(k, 0)) * f for k in ("brow_y", "brow_a", "lid", "eye", "curve")}
    out["asym"] = (eb if f > 0.5 else ea).get("asym", False)
    return out


class Spur:
    """Alle Ereignisse einer Figur über die ganze Folge (globale Zeit)."""

    def __init__(self, name: str, seed: int):
        self.name = name
        self.haltungen: list[tuple[float, str]] = [(0.0, "stehen")]
        self.ausdruecke: list[tuple[float, str]] = [(0.0, "neutral")]
        self.einzel: list[tuple[float, str]] = []
        self.sprechen: list[tuple[float, float]] = []        # (start, ende)
        self.mund: list[tuple[float, float, str]] = []       # (start, ende, form)
        rnd = random.Random(seed)
        t, self.blinks = 1.0 + rnd.random(), []
        while t < 3600:
            self.blinks.append(t)
            t += 2.2 + rnd.random() * 3.2

    @staticmethod
    def _aktiv(liste, t):
        cur, prev, t0 = liste[0][1], liste[0][1], 0.0
        for ts, v in liste:
            if ts <= t:
                prev, cur, t0 = cur, v, ts
        return prev, cur, t0

    def zustand(self, t: float, x: float, y: float, blick_x: float | None, s: float = 1.0) -> Zustand:
        prev, cur, t0 = self._aktiv(self.haltungen, t)
        f = ease((t - t0) / UEBERGANG)
        pose = _mix_pose(_pose(prev), _pose(cur), f)
        req_name = cur if f > 0.5 else prev
        requisit = HALTUNGEN[req_name].get("_requisit")
        hand = HALTUNGEN[req_name].get("_hand", "beide")

        ep, ec, te = self._aktiv(self.ausdruecke, t)
        expr = _mix_expr(ep, ec, ease((t - te) / 0.2))

        # Atmen
        pose["squash"] *= 1 + 0.009 * math.sin(2 * math.pi * t / 3.4)
        pose["kopf"] += 1.2 * math.sin(2 * math.pi * t / 4.1)

        # Einzelaktionen
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
                    a, b = pose[k]
                    pose[k] = (a + (155 - a) * arm, b + (15 - b) * arm)
            elif name == "nicken":
                pose["bob"] += 4 * math.sin(2 * math.pi * u * 2)
                pose["kopf"] += 7 * math.sin(2 * math.pi * u * 2)
            elif name == "kopfschuetteln":
                pose["kopf"] += 9 * math.sin(2 * math.pi * u * 3)
            elif name == "erschrecken":
                pose["bob"] -= 40 * math.sin(math.pi * u)
                pose["squash"] *= 1 + 0.05 * math.sin(math.pi * u)
            elif name == "winken":
                a = ease(min(1, u / 0.15)) * (1 - ease((u - 0.85) / 0.15))
                pose["ar"] = (pose["ar"][0] + (140 - pose["ar"][0]) * a, 25 + 30 * math.sin(2 * math.pi * u * 4) * a)
            elif name == "seufzen":
                pose["bob"] += 10 * math.sin(math.pi * u)
                pose["kopf"] += 6 * math.sin(math.pi * u)

        # Sprechen: Mund + leichte Kopfbewegung
        mund = "X"
        for a, b, form in self.mund:
            if a <= t < b:
                mund = form
                break
        spricht = any(a <= t < b for a, b in self.sprechen)
        if spricht:
            pose["kopf"] += 2.5 * math.sin(2 * math.pi * t * 1.7)
            pose["torso"] += 1.0 * math.sin(2 * math.pi * t * 0.9)

        # Blinzeln
        blink = 0.0
        for tb in self.blinks:
            if tb - 0.08 <= t <= tb + 0.1:
                blink = 1 - abs(t - tb) / 0.1
                break
            if tb > t:
                break
        dreh = 0.0 if blick_x is None else max(-0.5, min(0.5, (blick_x - x) / 500))
        z = Zustand(x=x, y=y, s=s, pose=pose, ausdruck=expr, blinzeln=max(0.0, blink), mund=mund,
                    blick=(0.0 if blick_x is None else (0.75 if blick_x > x else -0.75), 0.0),
                    kopf_dreh=dreh, requisit=requisit, requisit_hand=hand)
        return z
