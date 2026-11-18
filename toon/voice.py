"""Deutsche Figurenstimmen – kostenlos mit Piper (MIT) und CC0-Stimmen.

* Modelle: rhasspy/piper-voices auf Hugging Face (Lizenzen siehe MODELS).
* Figuren klingen unterschiedlich über Tonhöhe (rubberband, formant-schonend) und Tempo.
* Ohne Piper (z. B. in Tests oder ohne Internet) entsteht ein Platzhalter in Satzlänge,
  damit Timing, Lippenbewegung und Schnitt trotzdem geprüft werden können.
"""
from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

import numpy as np

from .media import SR, run, write_wav

log = logging.getLogger(__name__)
HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
VOICES_DIR = Path(__file__).resolve().parent.parent / "voices"

# Nur Stimmen mit klarer, kommerziell nutzbarer Lizenz.
MODELS = {
    "de_DE-kerstin-low": ("de/de_DE/kerstin/low", "CC0 1.0"),
    "de_DE-thorsten_emotional-medium": ("de/de_DE/thorsten_emotional/medium", "CC0 1.0"),
    "de_DE-thorsten-high": ("de/de_DE/thorsten/high", "CC0 1.0"),
}


def model_file(model: str) -> Path:
    return VOICES_DIR / f"{model}.onnx"


def download_model(model: str) -> Path:
    if model not in MODELS:
        raise KeyError(f"Stimme {model} ist nicht freigegeben (Lizenz ungeprüft)")
    target = model_file(model)
    if target.exists() and Path(str(target) + ".json").exists():
        return target
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    base = f"{HF_BASE}/{MODELS[model][0]}/{model}.onnx"
    for url, dest in ((base, target), (base + ".json", Path(str(target) + ".json"))):
        log.info("Lade %s", url)
        with urllib.request.urlopen(url, timeout=180) as r:  # noqa: S310 (feste HTTPS-URL)
            dest.write_bytes(r.read())
    return target


def piper_available() -> bool:
    try:
        import piper  # noqa: F401
        return True
    except Exception:
        return False


def _piper_wav(text: str, model: str, speaker: str | None, out: Path) -> Path:
    import json

    from piper import PiperVoice, SynthesisConfig

    path = download_model(model)
    voice = PiperVoice.load(str(path))
    cfg_json = json.loads(Path(str(path) + ".json").read_text(encoding="utf-8"))
    sid = (cfg_json.get("speaker_id_map") or {}).get(speaker) if speaker else None
    chunks = [c.audio_float_array.astype(np.float32)
              for c in voice.synthesize(text, syn_config=SynthesisConfig(speaker_id=sid))]
    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    raw = out.with_suffix(".raw.wav")
    write_wav(raw, audio, voice.config.sample_rate)
    return raw


def placeholder_wav(text: str, out: Path, base_hz: float = 220.0) -> Path:
    """Silbenartiger Platzhalter: ~12 Zeichen pro Sekunde, Lautstärke pulsiert wie Sprache."""
    dur = max(0.6, len(text) / 12.0)
    t = np.arange(int(dur * SR)) / SR
    syllables = 0.5 + 0.5 * np.sin(2 * np.pi * 4.0 * t) ** 2
    tone = 0.25 * np.sin(2 * np.pi * base_hz * t) * syllables
    fade = np.minimum(1.0, np.minimum(t, dur - t) / 0.03)
    return write_wav(out, tone * fade)


def speak(text: str, voice_cfg: dict, out: Path, use_piper: bool | None = None) -> dict:
    """Erzeugt eine Dialogzeile als WAV (48 kHz, Stereo) mit Figuren-Tonhöhe und -Tempo."""
    out.parent.mkdir(parents=True, exist_ok=True)
    use_piper = piper_available() if use_piper is None else use_piper
    pitch = float(voice_cfg.get("pitch", 1.0))
    tempo = float(voice_cfg.get("tempo", 1.0))
    if use_piper:
        raw = _piper_wav(text, voice_cfg["model"], voice_cfg.get("speaker"), out)
        source = f"piper:{voice_cfg['model']}"
    else:
        raw = placeholder_wav(text, out.with_suffix(".raw.wav"), 220.0 * pitch)
        source = "platzhalter"
        pitch = 1.0  # Platzhalter hat die Tonhöhe schon
    chain = ["aformat=sample_rates=48000:channel_layouts=stereo"]
    if abs(pitch - 1.0) > 1e-3:
        chain.append(f"rubberband=pitch={pitch:.4f}:formant=preserved")
    if abs(tempo - 1.0) > 1e-3:
        chain.append(f"atempo={tempo:.4f}")
    chain.append("silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                 "silenceremove=start_periods=1:start_threshold=-50dB,areverse")
    try:
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-af", ",".join(chain),
             "-c:a", "pcm_s16le", str(out)])
    except Exception:
        # Ohne librubberband: klassische Tonhöhenänderung über Abtastrate (leicht "heller")
        chain[1:2] = [f"asetrate={int(48000 * pitch)},aresample=48000,atempo={1 / pitch:.4f}"] if abs(pitch - 1) > 1e-3 else []
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-af", ",".join(chain),
             "-c:a", "pcm_s16le", str(out)])
    raw.unlink(missing_ok=True)
    return {"file": str(out), "source": source, "pitch": pitch, "tempo": tempo}
