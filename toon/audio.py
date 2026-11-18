"""Fröhliche Kinder-Musik und Soundeffekte – komplett selbst erzeugt.

Kein Sample, keine Bibliothek, keine Lizenzfrage: Alles wird hier mathematisch erzeugt
(Marimba-artige Töne, Ukulele-Zupfen, weiche Percussion). Damit gibt es auch keine
Content-ID-Konflikte auf YouTube.
"""
from __future__ import annotations

import numpy as np

from .media import SR

NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# Fröhliche Akkordfolge I – V – vi – IV (Pop/Kinderlied-Klassiker)
PROGRESSION = [(0, 4, 7), (7, 11, 14), (9, 12, 16), (5, 9, 12)]


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / max(decay, 1e-4))


def _freq(semitone: float, base: str = "C", octave: int = 4) -> float:
    midi = 12 * (octave + 1) + NOTE[base] + semitone
    return 440.0 * 2 ** ((midi - 69) / 12)


def marimba(freq: float, dur: float = 0.35) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * 4 * freq * t) * np.exp(-t * 30)
    return tone * _env(n, 0.003, 0.18)


def pluck(freq: float, dur: float = 0.6) -> np.ndarray:
    """Karplus-Strong – klingt wie eine kleine Ukulele."""
    n = int(dur * SR)
    period = max(2, int(SR / freq))
    rng = np.random.default_rng(int(freq * 100))
    buf = rng.uniform(-1, 1, period)
    out = np.empty(n)
    for i in range(n):
        out[i] = buf[i % period]
        buf[i % period] = 0.5 * (buf[i % period] + buf[(i + 1) % period]) * 0.996
    return out * 0.6


def shaker(dur: float = 0.08) -> np.ndarray:
    n = int(dur * SR)
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1, n)
    noise = noise - np.convolve(noise, np.ones(8) / 8, mode="same")  # nur Höhen
    return noise * _env(n, 0.002, 0.03) * 0.25


def _place(track: np.ndarray, sample: np.ndarray, at: float, gain: float) -> None:
    i = int(at * SR)
    if i >= len(track):
        return
    j = min(len(track), i + len(sample))
    track[i:j] += sample[: j - i] * gain


def make_music(duration: float, bpm: float = 112, key: str = "C") -> np.ndarray:
    track = np.zeros(int(duration * SR) + 1)
    beat = 60.0 / bpm
    melody_steps = [0, 4, 7, 4, 9, 7, 4, 2]   # einfache, sangbare Linie
    t, step = 0.0, 0
    while t < duration:
        bar = int(t / (4 * beat))
        chord = PROGRESSION[bar % len(PROGRESSION)]
        pos = step % 8
        if pos in (0, 4):
            for k, semi in enumerate(chord):
                _place(track, pluck(_freq(semi, key, 3)), t + 0.012 * k, 0.22)
        root = chord[0]
        _place(track, marimba(_freq(root + melody_steps[step % len(melody_steps)], key, 5)), t, 0.18 if pos % 2 == 0 else 0.1)
        _place(track, shaker(), t + beat / 2, 0.5)
        t += beat / 2
        step += 1
    peak = np.max(np.abs(track)) or 1.0
    fade = np.minimum(1.0, np.minimum(np.arange(len(track)), len(track) - np.arange(len(track))) / (1.5 * SR))
    return track / peak * 0.8 * fade


# ---------------------------------------------------------------- Soundeffekte
def sfx(name: str) -> np.ndarray:
    """Soundeffekt, auf höchstens 0,9 Spitze begrenzt."""
    s = _sfx(name)
    peak = float(np.max(np.abs(s))) or 1.0
    return s * min(1.0, 0.9 / peak)


def _sfx(name: str) -> np.ndarray:
    n = int(0.6 * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(len(name))
    if name == "boing":
        f = 180 + 420 * np.exp(-t * 6) * (1 + 0.3 * np.sin(2 * np.pi * 14 * t))
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.002, 0.25) * 0.6
    if name in ("plopp", "ploing"):
        f = 900 * np.exp(-t * (20 if name == "plopp" else 8)) + 200
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.001, 0.08 if name == "plopp" else 0.2) * 0.6
    if name == "vogelzwitschern":
        out = np.zeros(int(2.0 * SR))
        for k in range(6):
            m = int(0.12 * SR)
            tt = np.arange(m) / SR
            f = 3200 + 900 * np.sin(2 * np.pi * (18 + 3 * k) * tt)
            _place(out, np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(m, 0.004, 0.05) * 0.3, 0.25 * k + rng.uniform(0, 0.08), 1)
        return out
    if name == "fluegelschlag":
        out = np.zeros(int(0.9 * SR))
        for k in range(4):
            m = int(0.15 * SR)
            noise = rng.normal(0, 1, m)
            noise = np.convolve(noise, np.ones(40) / 40, mode="same")
            _place(out, noise * _env(m, 0.01, 0.06) * 2.0, 0.2 * k, 1)
        return out
    if name == "pfeifen":
        f = 1200 + 600 * np.sin(np.pi * t / t[-1])
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.03, 0.4) * 0.35
    if name in ("staunen", "jubel"):
        out = np.zeros(n)
        for k, semi in enumerate((0, 4, 7, 12) if name == "jubel" else (0, 3, 7)):
            _place(out, marimba(_freq(semi, "C", 5), 0.4), 0.07 * k, 0.5)
        return out
    raise KeyError(f"Unbekannter Soundeffekt {name}")


SFX_NAMES = ("boing", "plopp", "ploing", "vogelzwitschern", "fluegelschlag", "pfeifen", "staunen", "jubel")
