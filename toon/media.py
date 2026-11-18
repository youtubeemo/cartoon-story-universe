"""Kleine FFmpeg-/WAV-Helfer (nur Standardbibliothek + numpy)."""
from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path
from typing import Sequence

import numpy as np

SR = 48000


class MediaError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise MediaError(f"{tool} nicht gefunden – bitte installieren")


def run(cmd: Sequence[str]) -> None:
    proc = subprocess.run(list(cmd), capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise MediaError(f"FFmpeg fehlgeschlagen ({proc.returncode}): {' '.join(cmd[:6])} …\n{tail}")


def write_wav(path: Path, audio: np.ndarray, sr: int = SR) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(audio, -1.0, 1.0)
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    pcm = (data * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        raw = raw.reshape(-1, ch).mean(axis=1)
    return raw, sr


def duration(path: Path) -> float:
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                           str(path)], capture_output=True, text=True)
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:
        raise MediaError(f"{path}: Dauer nicht lesbar") from exc


def probe(path: Path) -> dict:
    import json

    proc = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
                           str(path)], capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), {})
    return {"width": v.get("width"), "height": v.get("height"), "video_codec": v.get("codec_name"),
            "audio_codec": a.get("codec_name"), "duration": float(data["format"]["duration"]),
            "video_duration": float(v["duration"]) if v.get("duration") else None,
            "audio_duration": float(a["duration"]) if a.get("duration") else None}
