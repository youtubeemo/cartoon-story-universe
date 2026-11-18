"""Hintergrundmusik ohne Lizenzkosten: kleine, stimmige Arrangements je Stimmung (selbst erzeugt, frei nutzbar).

Akkordfolge + Bass + Begleitung + Melodiemotiv + Schlagwerk, sanfte Hüllkurven, Ein-/Ausblenden.
Stimmungen: verschmitzt (Pizzicato-Komödie), spannung, abenteuer, raetsel, weltraum, fantasie.
"""
from __future__ import annotations

import numpy as np

SR = 48000
STIMMUNG = {
    "verschmitzt": {"bpm": 104, "tonart": 60, "moll": False, "folge": [0, 5, 3, 4], "klang": "pizz", "drums": "besen"},
    "spannung":    {"bpm": 92,  "tonart": 57, "moll": True,  "folge": [0, 5, 3, 4], "klang": "pizz", "drums": "tick"},
    "abenteuer":   {"bpm": 116, "tonart": 62, "moll": False, "folge": [0, 4, 5, 3], "klang": "blech", "drums": "marsch"},
    "raetsel":     {"bpm": 80,  "tonart": 57, "moll": True,  "folge": [0, 3, 5, 4], "klang": "celesta", "drums": "besen"},
    "weltraum":    {"bpm": 96,  "tonart": 55, "moll": True,  "folge": [0, 5, 2, 4], "klang": "synth", "drums": "puls"},
    "fantasie":    {"bpm": 112, "tonart": 62, "moll": False, "folge": [0, 3, 4, 0], "klang": "laute", "drums": "tamburin"},
}
DUR, MOLL = [0, 2, 4, 5, 7, 9, 11], [0, 2, 3, 5, 7, 8, 10]


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _ton(f: float, dauer: float, klang: str, laut: float = 0.3) -> np.ndarray:
    n = int(SR * dauer)
    t = np.arange(n) / SR
    if klang == "pizz":
        y = sum(np.sin(2 * np.pi * f * h * t) / h ** 1.3 for h in range(1, 7)) * np.exp(-t * 9)
    elif klang == "celesta":
        y = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-t * 8)) * np.exp(-t * 3)
    elif klang == "blech":
        env = np.minimum(1, t / 0.04) * np.exp(-t * 2.5)
        y = sum(np.sin(2 * np.pi * f * h * t) * (0.8 ** h) for h in range(1, 9)) * env
    elif klang == "synth":
        env = np.minimum(1, t / 0.01) * np.exp(-t * 5)
        y = (2 * ((f * t) % 1) - 1) * env * 0.6
    elif klang == "laute":
        y = sum(np.sin(2 * np.pi * f * h * t) / h for h in range(1, 6)) * np.exp(-t * 6)
    elif klang == "pad":
        env = np.minimum(1, t / 0.3) * np.minimum(1, (dauer - t) / 0.3)
        y = sum(np.sin(2 * np.pi * f * h * t + h) / h ** 2 for h in range(1, 5)) * env
    elif klang == "bass":
        y = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 4) * np.minimum(1, t / 0.005)
    else:
        y = np.sin(2 * np.pi * f * t) * np.exp(-t * 5)
    return y * laut


def _drum(art: str) -> np.ndarray:
    n = int(SR * 0.25)
    t = np.arange(n) / SR
    rnd = np.random.default_rng(len(art))
    if art == "kick":
        return np.sin(2 * np.pi * (50 + 90 * np.exp(-t * 30)) * t) * np.exp(-t * 18) * 0.5
    if art == "snare":
        return rnd.standard_normal(n) * np.exp(-t * 22) * 0.18
    if art == "besen":
        return np.convolve(rnd.standard_normal(n), np.ones(4) / 4, "same") * np.exp(-t * 14) * 0.08
    if art == "hat":
        x = rnd.standard_normal(n)
        return (x - np.convolve(x, np.ones(3) / 3, "same")) * np.exp(-t * 60) * 0.12
    if art == "tick":
        return np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 120) * 0.12
    return np.zeros(n)


def _setzen(buf: np.ndarray, y: np.ndarray, t0: float) -> None:
    i = int(t0 * SR)
    if i >= len(buf):
        return
    k = min(len(y), len(buf) - i)
    buf[i:i + k] += y[:k]


def komponieren(dauer: float, stimmung: str = "verschmitzt", seed: int = 1) -> np.ndarray:
    p = STIMMUNG.get(stimmung, STIMMUNG["verschmitzt"])
    rnd = np.random.default_rng(seed)
    skala = MOLL if p["moll"] else DUR
    beat = 60.0 / p["bpm"]
    takt = 4 * beat
    buf = np.zeros(int(SR * (dauer + 2)))
    motiv = [int(x) for x in rnd.choice([0, 1, 2, 3, 4, 2, 1], 8)]
    t, k = 0.0, 0
    while t < dauer + takt:
        stufe = p["folge"][k % len(p["folge"])]
        grund = p["tonart"] + skala[stufe % 7] - 12
        akkord = [grund + 12 + skala[(stufe + i) % 7] - skala[stufe % 7] + (12 if (stufe + i) >= 7 else 0) for i in (0, 2, 4)]
        # Bass: Grundton + Quinte im Wechsel
        for b in range(4):
            _setzen(buf, _ton(_hz(grund - 12 + (7 if b % 2 else 0)), beat * 0.9, "bass", 0.35), t + b * beat)
        # Begleitung: Nachschläge
        for b in range(4):
            for n_ in akkord:
                _setzen(buf, _ton(_hz(n_), beat * 0.6, p["klang"], 0.07), t + b * beat + beat / 2)
        if p["klang"] in ("synth", "celesta"):
            _setzen(buf, sum(_ton(_hz(n_), takt, "pad", 0.05) for n_ in akkord), t)
        # Melodie jeden zweiten Takt (Motiv mit Variation), lässt Platz für Dialog
        if k % 2 == 1:
            for i, m in enumerate(motiv):
                if rnd.random() < 0.8:
                    hoehe = p["tonart"] + 12 + skala[(stufe + m) % 7]
                    _setzen(buf, _ton(_hz(hoehe), beat * 0.45, p["klang"], 0.11), t + i * beat / 2)
        # Schlagwerk
        for b in range(4):
            tb = t + b * beat
            if p["drums"] in ("marsch", "puls"):
                _setzen(buf, _drum("kick"), tb if b % 2 == 0 else tb + 9e9)
                _setzen(buf, _drum("snare"), tb if b % 2 else tb + 9e9)
            if p["drums"] == "besen":
                _setzen(buf, _drum("besen"), tb)
                _setzen(buf, _drum("besen"), tb + beat / 2)
            if p["drums"] in ("tick", "puls"):
                _setzen(buf, _drum("tick"), tb)
            if p["drums"] in ("marsch", "tamburin"):
                _setzen(buf, _drum("hat"), tb + beat / 2)
        t += takt
        k += 1
    y = buf[: int(SR * dauer)]
    fade = int(SR * 1.2)
    y[:fade] *= np.linspace(0, 1, fade)
    y[-fade:] *= np.linspace(1, 0, fade)
    return np.tanh(y * 1.4) * 0.7
