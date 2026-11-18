"""Kostenlose Längenschätzung eines Storyboards (vor jedem Stimmaufruf)."""
from __future__ import annotations

from pathlib import Path

from toon import szene

ZEICHEN_PRO_SEKUNDE = 13.0


def schaetze(sb: dict) -> float:
    def fake(sprecher, text, key, emotion=None):
        d = len(text) / ZEICHEN_PRO_SEKUNDE + 0.25
        return Path("/dev/null"), d, [(0.0, d, "C")]
    return szene.zeitleiste(sb, fake)["gesamt"]
