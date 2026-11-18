"""Ton: Stimmen, Lippensync, Musik, Geräusche, Mischung.

Stimmen:
* ElevenLabs (natürlich, im Creator-Abo): nur mit harter Credit-Obergrenze (CreditBudget). Vor dem ersten Aufruf
  wird kostenlos geprüft, ob die Credits im vorhandenen Abo enthalten sind (kein Free-Tarif, keine Nachberechnung,
  genug Restkontingent). Jede erzeugte Zeile wird unter assets/stimmen/ abgelegt und nie zweimal bezahlt.
* Piper (kostenlos, CC0) als Ersatz; Platzhalter-Töne nur für Technik-Tests.
Lippensync: Rhubarb (phonetische Erkennung) aus der WAV-Datei; Ersatz über Lautstärke.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import urllib.request
from pathlib import Path

import numpy as np
import yaml

from toon import musik as komponist
from toon.media import SR, duration, read_wav_mono, write_wav
from toon.voice import speak

ROOT = Path(__file__).resolve().parent.parent
STIMMEN_ARCHIV = ROOT / "assets" / "stimmen"
ERZAEHLER_PIPER = {"piper": "de_DE-thorsten-high", "pitch": 1.0}
EMOTION = {"begeistert": "[excited]", "froh": "[cheerfully]", "wuetend": "[angry]", "traurig": "[sad]",
           "skeptisch": "[skeptical]", "verschmitzt": "[mischievously]", "ueberrascht": "[surprised]",
           "besorgt": "[worried]", "aengstlich": "[nervous]", "entschlossen": "[firmly]"}


class CreditGrenze(RuntimeError):
    pass


class CreditBudget:
    """Harte Obergrenze für ElevenLabs-Credits eines Laufs (z. B. 300 für eine Probe)."""

    def __init__(self, grenze: int):
        self.grenze, self.verbraucht, self.wiederverwendet = int(grenze), 0, 0

    def pruefen(self, credits: int) -> None:
        if self.verbraucht + credits > self.grenze:
            raise CreditGrenze(f"ElevenLabs-Grenze: {self.verbraucht} + {credits} > {self.grenze} Credits – Abbruch")

    def buchen(self, credits: int) -> None:
        self.verbraucht += credits


def el_stimme_fuer(figur: dict | None, key: str | None) -> dict:
    """ElevenLabs-Stimme aus der Story-Bibel (Figur) bzw. production.yaml (Erzähler)."""
    if figur is None:
        return yaml.safe_load((ROOT / "config" / "production.yaml").read_text(encoding="utf-8"))["sprecher"]
    story = yaml.safe_load((ROOT / "stories" / figur["geschichte"] / "story.yaml").read_text(encoding="utf-8"))
    return story["figuren"][key]["voice"]


def el_credits(text: str) -> int:
    return len(text)   # eleven_v3 / multilingual_v2: 1 Credit je Zeichen (config/pricing.yaml, geprüft)


def el_vorpruefung(benoetigt: int) -> dict:
    """Kostenlos: Tarif, Restkontingent und Nachberechnung prüfen (über den geprüften storyhouse-Code)."""
    from csu.plan import budget_config
    from storyhouse.elevenlabs import check_subscription
    req = urllib.request.Request("https://api.elevenlabs.io/v1/user/subscription",
                                 headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        sub = json.loads(r.read())
    check_subscription(sub, benoetigt, budget_config(), needs_music=False)
    return {"tarif": sub.get("tier"), "frei": int(sub["character_limit"] - sub["character_count"])}


def _archiv_pfad(voice: dict, text: str) -> Path:
    key = hashlib.sha256(json.dumps([voice["voice_id"], voice.get("model", "eleven_v3"), text,
                                     voice.get("stability", 0.5)]).encode()).hexdigest()[:20]
    return STIMMEN_ARCHIV / f"{key}.mp3"


def elevenlabs(text: str, voice: dict, out_wav: Path, budget: CreditBudget) -> dict:
    mp3 = _archiv_pfad(voice, text)
    if mp3.exists():
        budget.wiederverwendet += 1
    else:
        c = el_credits(text)
        budget.pruefen(c)
        model = voice.get("model", "eleven_v3")
        body = {"text": text, "model_id": model, "voice_settings": {"stability": float(voice.get("stability", 0.5))}}
        if model in ("eleven_v3", "eleven_flash_v2_5", "eleven_turbo_v2_5"):
            body["language_code"] = "de"
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice['voice_id']}?output_format=mp3_44100_128",
            data=json.dumps(body).encode(), method="POST",
            headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            daten = r.read()
        budget.buchen(c)
        mp3.parent.mkdir(parents=True, exist_ok=True)
        mp3.write_bytes(daten)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-af",
                    "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                    "silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                    "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(out_wav)], check=True)
    return {"file": str(out_wav), "dauer": duration(out_wav), "quelle": "elevenlabs"}


def stimme(text: str, cfg: dict, out: Path, platzhalter: bool = False) -> dict:
    vcfg = {"model": cfg.get("piper", "de_DE-thorsten-high"), "speaker": cfg.get("sprecher"),
            "pitch": cfg.get("pitch", 1.0), "tempo": cfg.get("tempo", 1.0)}
    info = speak(text, vcfg, out, use_piper=False if platzhalter else None)
    info["dauer"] = duration(Path(info["file"]))
    return info


# ------------------------------------------------------------------ Lippensync
def mundformen(wav: Path, text: str) -> tuple[list[tuple[float, float, str]], str]:
    rhubarb = os.environ.get("RHUBARB_BIN", "")
    if rhubarb and Path(rhubarb).exists():
        out = wav.with_suffix(".rhubarb.json")
        subprocess.run([rhubarb, "-f", "json", "-r", "phonetic", "--extendedShapes", "GHX", "-q",
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


# ------------------------------------------------------------------ Musik und Geräusche
def musik(dauer: float, stimmung: str, out: Path) -> Path:
    return write_wav(out, komponist.komponieren(dauer + 0.5, stimmung))


def _env(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / max(d, 1e-4))


LAUTSTAERKE = {"schritt": 0.35, "stuhl": 0.5, "papier": 0.6, "glocke": 0.55, "tuer": 0.6, "posaune": 0.7,
               "kasse": 0.6, "whoosh": 0.45, "jubel": 0.7}


def effekt(name: str, out: Path, variante: int = 0) -> Path:
    rng = np.random.default_rng(7 + variante)
    dauern = {"papier": 0.7, "posaune": 2.0, "kasse": 0.6, "schritt": 0.18, "stuhl": 0.55, "glocke": 1.4,
              "tuer": 0.5, "whoosh": 0.5, "jubel": 0.9}
    n = int(SR * dauern.get(name, 0.5))
    t = np.arange(n) / SR
    if name == "papier":
        noise = np.convolve(rng.standard_normal(n), np.ones(6) / 6, mode="same")
        y = noise * (0.4 + 0.6 * (np.sin(2 * np.pi * 9 * t) > 0)) * _env(n, 0.01, 0.35) * 0.35
    elif name == "posaune":
        y = np.zeros(n)
        start = 0.0
        for k, (f0, dur) in enumerate(((330, 0.4), (311, 0.4), (294, 0.4), (277, 0.8))):
            s0, m = int(start * SR), int(dur * SR)
            tt = np.arange(m) / SR
            f = f0 * (1 + 0.012 * np.sin(2 * np.pi * 5.5 * tt)) * (1 - (0.06 * tt / dur if k == 3 else 0))
            ph = 2 * np.pi * np.cumsum(f) / SR
            tone = sum(np.sin(h * ph) / h for h in (1, 2, 3, 4, 5)) * _env(m, 0.04, dur * 0.9)
            y[s0:s0 + m] += tone[: max(0, min(m, n - s0))] * 0.35
            start += dur
    elif name == "kasse":
        y = sum(np.sin(2 * np.pi * f * t) for f in (1800, 2400, 3150)) * _env(n, 0.002, 0.18) * 0.25
    elif name == "schritt":
        f0 = 90 + 25 * (variante % 3)
        y = (np.sin(2 * np.pi * f0 * t) * _env(n, 0.002, 0.04) * 0.6
             + np.convolve(rng.standard_normal(n), np.ones(12) / 12, "same") * _env(n, 0.001, 0.03) * 0.5)
    elif name == "stuhl":
        f = 180 + 60 * np.sin(2 * np.pi * 3 * t)
        y = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * _env(n, 0.05, 0.25) * 0.12
        y += np.sin(2 * np.pi * 110 * t) * _env(n, 0.001, 0.05) * 0.4 * (t > 0.35)
    elif name == "glocke":
        y = sum(np.sin(2 * np.pi * f * t) * a for f, a in ((2093, 0.5), (2637, 0.3), (3520, 0.2), (4186, 0.1)))
        y = y * _env(n, 0.002, 0.45) * (1 + 0.6 * np.sin(2 * np.pi * 14 * t)) * 0.2
    elif name == "tuer":
        y = np.sin(2 * np.pi * 70 * t) * _env(n, 0.002, 0.08) * 0.7
        y += np.convolve(rng.standard_normal(n), np.ones(20) / 20, "same") * _env(n, 0.001, 0.06)
    elif name == "whoosh":
        noise = np.convolve(rng.standard_normal(n), np.ones(30) / 30, "same")
        y = noise * np.sin(np.pi * t / t[-1]) * 0.6
    elif name == "jubel":
        y = sum(np.sin(2 * np.pi * f * t) for f in (523, 659, 784, 1047)) * _env(n, 0.01, 0.4) * 0.12
    else:
        raise KeyError(f"Unbekannter Effekt {name}")
    return write_wav(out, np.clip(y, -0.9, 0.9))


def mischen(stimmen: list[tuple[Path, float]], effekte: list[tuple[Path, float, float]], musik_wav: Path | None,
            gesamt: float, out: Path) -> Path:
    """Stimmen + Effekte (Datei, Zeit, Lautstärke), Musik mit automatischer Absenkung unter Sprache, −14 LUFS."""
    cmd, parts, vlabels, elabels = ["ffmpeg", "-y", "-v", "error"], [], [], []
    i = 0
    for f, at in stimmen:
        cmd += ["-i", str(f)]
        ms = int(at * 1000)
        parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms}[v{i}]")
        vlabels.append(f"[v{i}]")
        i += 1
    for f, at, vol in effekte:
        cmd += ["-i", str(f)]
        ms = int(at * 1000)
        parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms},volume={vol}[e{i}]")
        elabels.append(f"[e{i}]")
        i += 1
    if not vlabels:
        raise ValueError("keine Sprachaufnahmen")
    parts.append(f"{''.join(vlabels)}amix=inputs={len(vlabels)}:normalize=0,apad,atrim=0:{gesamt},asplit=2[voc][sc]")
    bus = "[voc]"
    if elabels:
        parts.append(f"{''.join(elabels)}amix=inputs={len(elabels)}:normalize=0,apad,atrim=0:{gesamt}[fx]")
    if musik_wav:
        cmd += ["-i", str(musik_wav)]
        parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,apad,atrim=0:{gesamt},volume=0.5[mu]")
        parts.append("[mu][sc]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=500[duck]")
        bus += "[duck]"
    else:
        parts.append("[sc]anullsink")
    if elabels:
        bus += "[fx]"
    parts.append(f"{bus}amix=inputs={bus.count('[')}:normalize=0,atrim=0:{gesamt},loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    subprocess.run(cmd + ["-filter_complex", ";".join(parts), "-map", "[out]", "-ar", "48000", str(out)], check=True)
    return out
