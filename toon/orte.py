"""Schauplätze: aus Bauteilen (toon/bausteine.py) zusammengesetzt, beschrieben in toon/orte/<name>.yaml.

Bühne 1440 × 2560 (totale); Füße der Figuren bei BODEN_Y = 2000. Die Tageszeit färbt alles einheitlich.
Zusatzangaben je Ort: sitze (x-Positionen von Sitzgelegenheiten), eingang_links/rechts (woher Figuren kommen).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from toon.bausteine import BAUSTEINE
from toon.geo import mix

BUEHNE_B, BUEHNE_H = 1440, 2560
BODEN_Y = 2000
TINT = {"morgen": ("#FFE2B8", 0.10), "tag": None, "abend": ("#FF9A4D", 0.22), "nacht": ("#1D2B57", 0.45)}
ORDNER = Path(__file__).resolve().parent / "orte"


def lade(name: str) -> dict:
    return yaml.safe_load((ORDNER / f"{name}.yaml").read_text(encoding="utf-8"))


def zeichne_ort(pen, name: str, zeit: str = "tag") -> None:
    d = lade(name)
    pen.tint = TINT[zeit] if d.get("tageslicht", True) else None
    for el in d["elemente"]:
        el = dict(el)
        typ = el.pop("typ")
        if typ == "himmel" or "zeit" in BAUSTEINE[typ].__code__.co_varnames:
            el.setdefault("zeit", zeit)
        BAUSTEINE[typ](pen, **el)
    pen.tint = None
    b = d.get("bodenfarbe", "#B9825A")
    pen.boden = mix(b, TINT[zeit][0], TINT[zeit][1]) if TINT[zeit] else b


class _Orte(dict):
    def __missing__(self, key):
        if (ORDNER / f"{key}.yaml").exists():
            return lambda pen, zeit="tag": zeichne_ort(pen, key, zeit)
        raise KeyError(key)

    def __contains__(self, key):
        return (ORDNER / f"{key}.yaml").exists()


ORTE = _Orte()


def alle() -> list[str]:
    return sorted(p.stem for p in ORDNER.glob("*.yaml"))
