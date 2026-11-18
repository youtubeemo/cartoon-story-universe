"""Bezahlter Lauf (nur nach Freigabe) und kostenloser Schnitt mit FFmpeg.

Reihenfolge: ElevenLabs zuerst (billig) → Runway-Bilder → Runway-Videos. Jeder Auftrag geht durch den
SpendGuard aus storyhouse (Budget VOR dem Senden, Preisabgleich danach). Keine automatischen Wiederholungen:
schlägt etwas fehl, bricht der Lauf ab; bereits bezahlte Ergebnisse liegen im Cache und kosten beim
nächsten Lauf nichts mehr.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from csu.common import production, write_json
from csu.hud import build_ass
from csu.plan import EpisodePlan, speech_items

GAP = 0.2          # Pause zwischen Sprechzeilen
TAIL = 0.4         # Luft am Szenenende
EVENT_AT = 1.0     # HUD-Ereignis ~1 s nach Szenenbeginn, mehrere im Abstand von 1 s


# ---------------------------------------------------------------- bezahlte Aufträge
def _job_keys(jobs) -> dict[str, str]:
    keys: dict[str, str] = {}
    for j in jobs:  # Plan ist topologisch sortiert
        h = hashlib.sha256(json.dumps([j.kind, j.model, j.path, j.payload, sorted(keys.get(d, d) for d in j.depends)],
                                      sort_keys=True).encode()).hexdigest()[:24]
        keys[j.id] = h
    return keys


def run_jobs(plan: EpisodePlan, clients: dict, raw: Path, cache: Path, log=print) -> dict[str, Path]:
    from storyhouse import ffmpeg as sff
    from storyhouse.runway import download

    raw.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    files: dict[str, Path] = {}
    for jid, path in plan.frozen_refs.items():
        files[jid] = Path(path)
        outputs[jid] = sff.image_to_data_uri(Path(path))
    keys = _job_keys(plan.jobs)
    ordered = [j for j in plan.jobs if j.provider == "elevenlabs"] + [j for j in plan.jobs if j.provider != "elevenlabs"]
    for job in ordered:
        cached = cache / f"{keys[job.id]}.{job.ext}"
        dest = raw / f"{job.id}.{job.ext}"
        if cached.exists():
            log(f"↺ {job.id} aus dem Cache (0 €)")
            files[job.id] = Path(shutil.copy2(cached, dest))
        else:
            log(f"→ {job.id} ({job.provider}/{job.model}, ~{job.credits:.0f} Credits)")
            if job.provider == "elevenlabs":
                files[job.id] = clients["elevenlabs"].run_job(job, dest)
            else:
                files[job.id] = download(clients["runway"].run_job(job, outputs), dest)
            shutil.copy2(files[job.id], cached)
        if job.kind == "image":
            outputs[job.id] = sff.image_to_data_uri(files[job.id])
        if job.kind == "video":   # letztes Bild → Startbild einer folgenden „anschluss“-Szene (kostenlos)
            lf = raw / f"LF_{job.id}.jpg"
            _run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.05", "-i", str(files[job.id]), "-frames:v", "1",
                  "-q:v", "2", str(lf)])
            files[f"LF_{job.id}"] = lf
            outputs[f"LF_{job.id}"] = sff.image_to_data_uri(lf)
    return files


# ---------------------------------------------------------------- Schnitt (kostenlos)
def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg-Fehler: {' '.join(cmd[:6])} …\n{r.stderr[-1500:]}")


def probe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def _cues(text: str, start: float, dur: float, erzaehler: bool, max_chars: int = 32) -> list[dict]:
    words, chunks, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            chunks.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        chunks.append(cur)
    total = sum(len(c) for c in chunks) or 1
    out, t = [], start
    for c in chunks:
        d = dur * len(c) / total
        out.append({"start": round(t, 2), "end": round(t + d, 2), "text": c, "erzaehler": erzaehler})
        t += d
    return out


def timeline(story: dict, ep: dict, files: dict[str, Path], events: list[dict]) -> dict:
    """Berechnet echte Szenenlängen (aus den Tondateien), Ton-Startzeiten, Untertitel und HUD-Zeitpunkte."""
    t = 0.0
    scenes, audio, cues, hud_events, choice = [], [], [], [], None
    for s in ep["szenen"]:
        cursor = 0.3
        for it in speech_items(story, s):
            d = probe_duration(files[it["id"]])
            audio.append({"file": files[it["id"]], "at": t + cursor, "vol": 1.0})
            if not s.get("entscheidung"):   # Auswahlkarte zeigt die Frage bereits – kein doppelter Text
                cues += _cues(it["text"], t + cursor, d, it["erzaehler"])
            cursor += d + GAP
        dur = max(float(s["dauer"]), cursor + TAIL)
        for i, fx in enumerate(s.get("sfx") or []):
            f = files.get(f"SFX_{s['id']}_{i + 1}")
            if f:
                audio.append({"file": f, "at": t + float(fx.get("at", 0)), "vol": 0.55})
        k = 0
        for ev in events:
            if ev["szene"] == s["id"]:
                hud_events.append({**ev, "t": round(t + min(EVENT_AT + k, dur - 0.9), 2)})
                k += 1
        if s.get("entscheidung"):
            choice = {**ep["entscheidung"], "start": t + 0.4}
        scenes.append({"id": s["id"], "start": round(t, 3), "dauer": round(dur, 3), "uebergang": s["uebergang"]})
        t += dur
    return {"scenes": scenes, "audio": audio, "cues": cues, "events": hud_events, "choice": choice, "total": round(t, 3)}


def assemble(story: dict, ep: dict, start_werte: dict, events: list[dict], files: dict[str, Path],
             music: Path | None, out_dir: Path, filename: str) -> dict:
    prod = production()
    v = prod["video"]
    W, H, FPS = v["breite"], v["hoehe"], v["fps"]
    work = out_dir / "schnitt"
    work.mkdir(parents=True, exist_ok=True)
    tl = timeline(story, ep, files, events)

    # 1) Szenen: 1080×1920, 30 fps, exakte Länge (bei Bedarf letztes Bild halten)
    segs = []
    scs = tl["scenes"]
    for i, sc in enumerate(scs):
        clip = files[f"VID_{sc['id']}"]
        seg = work / f"{sc['id']}.mp4"
        fades = ""
        if sc["uebergang"] == "abblende":
            fades += ",fade=t=in:st=0:d=0.6"
        elif sc["uebergang"] == "ueberblendung":
            fades += ",fade=t=in:st=0:d=0.4"
        nxt = scs[i + 1]["uebergang"] if i + 1 < len(scs) else "ende"
        if nxt == "ueberblendung":
            fades += f",fade=t=out:st={sc['dauer'] - 0.4:.2f}:d=0.4"
        elif nxt in ("abblende", "ende"):
            fades += f",fade=t=out:st={sc['dauer'] - 0.6:.2f}:d=0.6"
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-vf",
              f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS},"
              f"tpad=stop_mode=clone:stop_duration=10,trim=duration={sc['dauer']},setpts=PTS-STARTPTS,setsar=1"
              f"{fades}",
              "-an", "-c:v", "libx264", "-preset", v["preset"], "-crf", "14", "-pix_fmt", "yuv420p", str(seg)])
        segs.append(seg)
    lst = work / "liste.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in segs), encoding="utf-8")
    video = work / "bild.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(video)])

    # 2) Ton: Stimmen + SFX an exakten Zeitpunkten, Musik geloopt und abgesenkt, Lautheit -14 LUFS
    total = tl["total"]
    cmd = ["ffmpeg", "-y", "-v", "error"]
    parts = []
    for i, a in enumerate(tl["audio"]):
        cmd += ["-i", str(a["file"])]
        ms = int(a["at"] * 1000)
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms},volume={a['vol']}[a{i}]")
    n = len(tl["audio"])
    labels = "".join(f"[a{i}]" for i in range(n))
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        parts.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total},volume=0.16,"
                     f"afade=t=in:d=1,afade=t=out:st={max(0, total - 2.5)}:d=2.5[m]")
        labels += "[m]"
        n += 1
    parts.append(f"{labels}amix=inputs={n}:normalize=0:duration=longest,apad,atrim=0:{total},"
                 f"loudnorm=I={v['lautheit_lufs']}:TP=-1.5:LRA=11[out]")
    mix = work / "ton.wav"
    _run(cmd + ["-filter_complex", ";".join(parts), "-map", "[out]", "-ar", "48000", str(mix)])

    # 3) Overlay: Statusanzeigen, Untertitel, Titel, Auswahlkarte
    ass = work / "overlay.ass"
    ass.write_text(build_ass(story, start_werte, tl["events"], total, tl["cues"], tl["choice"],
                             f"Teil {ep['teil']}: {ep['titel']}"), encoding="utf-8")

    # 4) Export: H.264 + AAC, faststart (sofort abspielbar auf dem iPhone)
    out = out_dir / filename
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(video.resolve()), "-i", str(mix.resolve()),
          "-vf", f"ass={ass.resolve()}", "-map", "0:v", "-map", "1:a",
          "-c:v", "libx264", "-preset", v["preset"], "-crf", str(v["crf"]), "-profile:v", "high",
          "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", v["audio_bitrate"], "-ar", "48000",
          "-movflags", "+faststart", "-t", str(total), str(out.resolve())])
    write_json(out_dir / "timeline.json", {**tl, "audio": [{**a, "file": str(a["file"])} for a in tl["audio"]]})
    return {"datei": str(out), "laenge_s": total, "timeline": tl}
