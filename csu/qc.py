"""Automatische Qualitätskontrolle einer fertigen Folge (kostenlos, FFmpeg + Pillow).

Prüft: technische Werte (inkl. ECHTER Quellauflösung der Animationsclips), Ton (Lautheit, Spitzen, Lücken),
Untertitel (Überlappung, Lesetempo, Zeilenlänge), Szenenfolge (zufällige Schnitte innerhalb einer Szene,
Bruch an „anschluss“-Übergängen), Bildstabilität (Flackern/Morphing innerhalb einer Szene) und erstellt einen
Kontaktbogen (ein Bild je Szene) für die Sichtprüfung.

Grenze: Ob Figuren über Szenen hinweg wirklich gleich aussehen und ob ein Bild zur Handlung passt, kann diese
Prüfung NICHT beweisen. Dafür gibt es die KI-Bildprüfung (csu/vision.py) und die menschliche Storyboard-Freigabe.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SZENEN_SCHWELLE = 0.32       # ffmpeg scene score für „harter Bildwechsel“
TOLERANZ = 0.35              # s um eine geplante Szenengrenze
MAX_CPS = 20                 # Lesetempo Untertitel (Zeichen/s)


def _probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_name,codec_type,width,height,r_frame_rate,bit_rate,duration:format=duration,bit_rate",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def technisch(path: Path, W: int, H: int, FPS: int, ziel, quellclips: list[Path]) -> list[tuple]:
    info = _probe(path)
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    vbit = int(vs.get("bit_rate") or info["format"].get("bit_rate") or 0)
    out = [
        ((vs["width"], vs["height"]) == (W, H), "Auflösung", f"{vs['width']}×{vs['height']}, {vbit / 1e6:.1f} Mbit/s"),
        (vs["codec_name"] == "h264" and au is not None and au["codec_name"] == "aac", "Codecs",
         f"{vs['codec_name']}/{au['codec_name'] if au else '–'}"),
        (vs["r_frame_rate"] == f"{FPS}/1", "Bildrate", vs["r_frame_rate"]),
        (ziel[0] - 0.5 <= dur <= ziel[1] + 0.5, "Länge", f"{dur:.1f} s"),
    ]
    klein = []
    for c in quellclips:
        s = next(x for x in _probe(c)["streams"] if x["codec_type"] == "video")
        if s["width"] < W or s["height"] < H:
            klein.append(f"{c.stem} {s['width']}×{s['height']}")
    out.append((not klein, "Echte Quellauflösung der Animation",
                "alle Clips nativ 1080×1920" if not klein else "hochskaliert: " + ", ".join(klein[:4])))
    return out


def ton(path: Path, video_dur: float) -> list[tuple]:
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-map", "0:a", "-af",
                        "ebur128=peak=true,silencedetect=n=-45dB:d=1.5", "-f", "null", "-"],
                       capture_output=True, text=True)
    err = r.stderr
    m_i = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    m_p = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)
    lufs = float(m_i[-1]) if m_i else -99
    peak = float(m_p[-1]) if m_p else 0
    stille = [(float(a), float(b)) for a, b in re.findall(r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)", err)]
    stille = [(a, b) for a, b in stille if b < video_dur - 1.0]
    au = next((s for s in _probe(path)["streams"] if s["codec_type"] == "audio"), {})
    adur = float(au.get("duration") or 0)
    return [
        (-16.5 <= lufs <= -11.5, "Lautheit", f"{lufs:.1f} LUFS (Ziel −14)"),
        (peak <= -0.5, "Spitzenpegel", f"{peak:.1f} dBTP"),
        (not stille, "Tonlücken", "keine" if not stille else ", ".join(f"{a:.1f}–{b:.1f}s" for a, b in stille[:3])),
        (abs(adur - video_dur) < 0.3, "Ton-/Bildlänge", f"{adur:.2f}/{video_dur:.2f} s"),
    ]


def untertitel(cues: list[dict], total: float) -> list[tuple]:
    probleme = []
    for a, b in zip(cues, cues[1:]):
        if b["start"] < a["end"] - 0.02:
            probleme.append(f"Überlappung bei {b['start']:.1f}s")
    for c in cues:
        d = c["end"] - c["start"]
        if d <= 0 or c["end"] > total + 0.05:
            probleme.append(f"ungültige Zeit {c['start']:.1f}s")
        elif len(c["text"]) / d > MAX_CPS:
            probleme.append(f"zu schnell bei {c['start']:.1f}s ({len(c['text']) / d:.0f} Z/s)")
        if len(c["text"]) > 34:
            probleme.append(f"Zeile zu lang bei {c['start']:.1f}s")
    return [(not probleme, "Untertitel", f"{len(cues)} Einblendungen" if not probleme else "; ".join(probleme[:4]))]


def _schnitte(video: Path) -> list[float]:
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(video), "-vf",
                        f"select='gt(scene,{SZENEN_SCHWELLE})',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [float(t) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def szenenfolge(bild_ohne_overlay: Path, scenes: list[dict]) -> list[tuple]:
    cuts = _schnitte(bild_ohne_overlay)
    grenzen = {round(s["start"], 2): s for s in scenes[1:]}
    zufall, bruch = [], []
    for t in cuts:
        nah = [g for g in grenzen if abs(g - t) <= TOLERANZ]
        if not nah:
            sc = next((s for s in scenes if s["start"] <= t < s["start"] + s["dauer"]), None)
            zufall.append(f"{sc['id'] if sc else '?'} bei {t:.1f}s")
        elif grenzen[nah[0]]["uebergang"] == "anschluss":
            bruch.append(f"{grenzen[nah[0]]['id']}")
    return [
        (not zufall, "Keine zufälligen Bildwechsel", "ok" if not zufall else ", ".join(zufall[:5])),
        (not bruch, "Nahtlose Anschlüsse", "ok" if not bruch else "harter Bruch an " + ", ".join(bruch)),
    ]


def _frame(video: Path, t: float, w: int = 270) -> Image.Image:
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={w}:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    import io
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def _hist(img: Image.Image) -> np.ndarray:
    a = np.asarray(img.convert("HSV").resize((96, 170)))
    h, _, _ = np.histogram2d(a[..., 0].ravel(), a[..., 1].ravel(), bins=(18, 8), range=((0, 256), (0, 256)))
    h = h.ravel() / max(h.sum(), 1)
    return h


def bildstabilitaet(bild_ohne_overlay: Path, scenes: list[dict]) -> list[tuple]:
    """Innerhalb einer Szene darf sich die Farbverteilung nicht sprunghaft ändern (Morphing, Flackern, Stilbruch)."""
    auffaellig = []
    for s in scenes:
        ts = [s["start"] + s["dauer"] * f for f in (0.15, 0.5, 0.85)]
        hs = [_hist(_frame(bild_ohne_overlay, t, 160)) for t in ts]
        d = max(0.5 * np.abs(hs[0] - hs[1]).sum(), 0.5 * np.abs(hs[1] - hs[2]).sum())
        if d > 0.45:
            auffaellig.append(f"{s['id']} ({d:.2f})")
    return [(not auffaellig, "Bildstabilität innerhalb der Szenen",
             "ok" if not auffaellig else "starke Bildveränderung: " + ", ".join(auffaellig))]


def kontaktbogen(video: Path, scenes: list[dict], ep: dict, ziel: Path, spalten: int = 5) -> Path:
    """Ein Bild je Szene (Mitte) mit Nummer, Kamera und Handlung – für die Sichtprüfung im Bericht."""
    by_id = {s["id"]: s for s in ep["szenen"]}
    tiles = []
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 13)
        small = ImageFont.truetype("DejaVuSans.ttf", 11)
    except OSError:
        font = small = ImageFont.load_default()
    for sc in scenes:
        img = _frame(video, sc["start"] + sc["dauer"] / 2)
        tile = Image.new("RGB", (img.width, img.height + 54), "white")
        tile.paste(img, (0, 0))
        d = ImageDraw.Draw(tile)
        s = by_id[sc["id"]]
        d.text((4, img.height + 2), f"{s['nr']}. {s['kamera']} · {s['uebergang']} · {s['dauer']}s", fill="black",
               font=font)
        import textwrap
        for j, zeile in enumerate(textwrap.wrap(s["handlung"], 44)[:2]):
            d.text((4, img.height + 20 + 14 * j), zeile, fill="black", font=small)
        tiles.append(tile)
    w, h = tiles[0].size
    rows = (len(tiles) + spalten - 1) // spalten
    sheet = Image.new("RGB", (w * spalten, h * rows), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % spalten) * w, (i // spalten) * h))
    sheet.save(ziel, quality=88)
    return ziel


def pruefen(datei: Path, bild_ohne_overlay: Path, timeline: dict, ep: dict, quellclips: list[Path],
            W: int, H: int, FPS: int, ziel) -> dict:
    total = timeline["total"]
    checks = (technisch(datei, W, H, FPS, ziel, quellclips) + ton(datei, total)
              + untertitel(timeline["cues"], total) + szenenfolge(bild_ohne_overlay, timeline["scenes"])
              + bildstabilitaet(bild_ohne_overlay, timeline["scenes"]))
    return {"ok": all(c[0] for c in checks), "pruefungen": [{"ok": bool(o), "name": n, "detail": d}
                                                             for o, n, d in checks]}


def als_markdown(qc: dict) -> str:
    return "\n".join(f"- {'✅' if p['ok'] else '❌'} {p['name']}: {p['detail']}" for p in qc["pruefungen"])
