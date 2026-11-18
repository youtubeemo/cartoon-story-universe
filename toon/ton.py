"""Ton: Stimmen (Piper kostenlos / ElevenLabs nach Freigabe), Lippensync (Rhubarb), Musik, Soundeffekte, Mischung."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import numpy as np

from toon import audio as synth
from toon.media import SR, duration, read_wav_mono, write_wav
from toon.voice import speak

ERZAEHLER = {"piper": "de_DE-thorsten-high", "pitch": 1.0}


def stimme(text: str, cfg: dict, out: Path, platzhalter: bool = False) -> dict:
    """Eine Sprachzeile als WAV. cfg aus figuren/*.yaml → stimme."""
    vcfg = {"model": cfg.get("piper", "de_DE-thorsten-high"), "speaker": cfg.get("sprecher"),
            "pitch": cfg.get("pitch", 1.0), "tempo": cfg.get("tempo", 1.0)}
    info = speak(text, vcfg, out, use_piper=False if platzhalter else None)
    info["dauer"] = duration(Path(info["file"]))
    return info


# ------------------------------------------------------------------ Lippensync
RHUBARB = os.environ.get("RHUBARB_BIN", "")


def mundformen(wav: Path, text: str) -> tuple[list[tuple[float, float, str]], str]:
    """[(start, ende, form)] relativ zum Zeilenbeginn. Rhubarb (präzise, Phonem-Erkennung) oder Lautstärke-Ersatz."""
    if RHUBARB and Path(RHUBARB).exists():
        txt = wav.with_suffix(".txt")
        txt.write_text(text, encoding="utf-8")
        out = wav.with_suffix(".rhubarb.json")
        subprocess.run([RHUBARB, "-f", "json", "-r", "phonetic", "--extendedShapes", "GHX", "-q",
                        "-o", str(out), str(wav)], check=True, capture_output=True)
        cues = json.loads(out.read_text())["mouthCues"]
        return [(float(c["start"]), float(c["end"]), c["value"]) for c in cues], "rhubarb"
    return _lautstaerke(wav), "lautstaerke"


def _lautstaerke(wav: Path, fps: int = 30) -> list[tuple[float, float, str]]:
    a, sr = read_wav_mono(wav)
    hop = sr // fps
    n = max(1, len(a) // hop)
    rms = np.array([np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms / max(rms.max(), 1e-9))
    out = []
    for i, v in enumerate(db):
        form = "X" if v < -32 else "B" if v < -20 else "C" if v < -10 else "D"
        if i % 7 == 3 and form in ("C", "D"):
            form = "E"
        out.append((i / fps, (i + 1) / fps, form))
    return out


# ------------------------------------------------------------------ Musik und Effekte
def musik(dauer: float, bpm: float, out: Path) -> Path:
    return write_wav(out, synth.make_music(dauer + 1, bpm=bpm) * 0.8)


def _env(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / max(d, 1e-4))


def effekt(name: str, out: Path) -> Path:
    if name in synth.SFX_NAMES:
        return write_wav(out, synth.sfx(name))
    n = int(SR * {"papier": 0.7, "posaune": 2.0, "kasse": 0.6}.get(name, 0.5))
    t = np.arange(n) / SR
    rng = np.random.default_rng(7)
    if name == "papier":
        noise = rng.standard_normal(n)
        noise = np.convolve(noise, np.ones(6) / 6, mode="same")
        y = noise * (0.4 + 0.6 * (np.sin(2 * np.pi * 9 * t) > 0)) * _env(n, 0.01, 0.35) * 0.35
    elif name == "posaune":   # „wah-wah-wah-waah“
        y = np.zeros(n)
        for k, (f0, dur) in enumerate(((330, 0.4), (311, 0.4), (294, 0.4), (277, 0.8))):
            s0, m = int(sum(d for _, d in ((330, 0.4), (311, 0.4), (294, 0.4))[:k]) * SR), int(dur * SR)
            tt = np.arange(m) / SR
            f = f0 * (1 + 0.012 * np.sin(2 * np.pi * 5.5 * tt)) * (1 - (0.06 * tt / dur if k == 3 else 0))
            ph = 2 * np.pi * np.cumsum(f) / SR
            tone = sum(np.sin(h * ph) / h for h in (1, 2, 3, 4, 5)) * _env(m, 0.04, dur * 0.9)
            y[s0:s0 + m] += tone[: max(0, min(m, n - s0))] * 0.35
    elif name == "kasse":
        y = sum(np.sin(2 * np.pi * f * t) for f in (1800, 2400, 3150)) * _env(n, 0.002, 0.18) * 0.25
    else:
        raise KeyError(f"Unbekannter Effekt {name}")
    return write_wav(out, np.clip(y, -0.9, 0.9))


def mischen(stimmen: list[tuple[Path, float]], effekte: list[tuple[Path, float]], musik_wav: Path | None,
            gesamt: float, out: Path) -> Path:
    """Stimmen + Effekte an exakten Zeitpunkten, Musik mit automatischer Absenkung unter Sprache, −14 LUFS."""
    cmd, parts, vlabels, elabels = ["ffmpeg", "-y", "-v", "error"], [], [], []
    i = 0
    for f, at in stimmen:
        cmd += ["-i", str(f)]
        ms = int(at * 1000)
        parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms}[v{i}]")
        vlabels.append(f"[v{i}]")
        i += 1
    for f, at in effekte:
        cmd += ["-i", str(f)]
        ms = int(at * 1000)
        parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms},volume=0.7[e{i}]")
        elabels.append(f"[e{i}]")
        i += 1
    parts.append(f"{''.join(vlabels)}amix=inputs={len(vlabels)}:normalize=0,apad,atrim=0:{gesamt},asplit=2[voc][sc]")
    bus = "[voc]"
    if elabels:
        parts.append(f"{''.join(elabels)}amix=inputs={len(elabels)}:normalize=0,apad,atrim=0:{gesamt}[fx]")
    if musik_wav:
        cmd += ["-i", str(musik_wav)]
        parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{gesamt},volume=0.35,"
                     f"afade=t=out:st={max(0, gesamt - 1.5)}:d=1.5[mu]")
        parts.append("[mu][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
        bus += "[duck]"
    else:
        parts.append("[sc]anullsink")
    if elabels:
        bus += "[fx]"
    n = bus.count("[")
    parts.append(f"{bus}amix=inputs={n}:normalize=0,atrim=0:{gesamt},loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    subprocess.run(cmd + ["-filter_complex", ";".join(parts), "-map", "[out]", "-ar", "48000", str(out)], check=True)
    return out
