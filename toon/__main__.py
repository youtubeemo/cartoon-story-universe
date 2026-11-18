"""python -m toon probe   [--storyboard …] [--out …] [--platzhalter] [--standbilder 30,200,400]

Kostenlos: Piper-Stimmen (CC0), Rhubarb-Lippensync (MIT), synthetische Musik/Effekte, eigenes Rig, FFmpeg.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from csu.hud import build_ass  # noqa: E402  (Statusanzeigen/Untertitel aus der bestehenden Pipeline)
from csu.state import apply, initial_state  # noqa: E402
from toon import render, szene, ton  # noqa: E402


def _cues(text: str, start: float, dur: float, erzaehler: bool, max_chars: int = 32) -> list[dict]:
    words, chunks, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            chunks.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    chunks.append(cur)
    total = sum(len(c) for c in chunks) or 1
    out, t = [], start
    for c in chunks:
        d = dur * len(c) / total
        out.append({"start": round(t, 2), "end": round(t + d, 2), "text": c, "erzaehler": erzaehler})
        t += d
    return out


def probe(a) -> None:
    t0 = time.time()
    sb = yaml.safe_load(Path(a.storyboard).read_text(encoding="utf-8"))
    errs = szene.pruefen(sb)
    if errs:
        raise SystemExit("Storyboard-Prüfung:\n  " + "\n  ".join(errs))
    out = Path(a.out)
    (out / "ton").mkdir(parents=True, exist_ok=True)
    figuren = szene.lade_figuren({f for e in sb["einstellungen"] for f in e["figuren"]})
    lipsync_art = set()

    def ton_fn(sprecher, text, key):
        cfg = figuren[sprecher]["stimme"] if sprecher else ton.ERZAEHLER
        info = ton.stimme(text, cfg, out / "ton" / f"{key}.wav", platzhalter=a.platzhalter)
        formen, art = ton.mundformen(Path(info["file"]), text) if sprecher else ([], "-")
        lipsync_art.add(art)
        return Path(info["file"]), info["dauer"], formen

    tl = szene.zeitleiste(sb, ton_fn)
    if a.standbilder:
        for f in [int(x) for x in a.standbilder.split(",")]:
            render.standbild(tl, f, out / f"standbild_{f:04d}.png")
        print(f"Standbilder in {out}")
        return

    effekte = [(ton.effekt(n, out / "ton" / f"sfx_{i}_{n}.wav"), at) for i, (n, at) in enumerate(tl["effekte"])]
    musik = ton.musik(tl["gesamt"], sb.get("musik", {}).get("bpm", 100), out / "ton" / "musik.wav")
    mix = ton.mischen(tl["stimmen"], effekte, musik, tl["gesamt"], out / "ton" / "mischung.wav")

    story = yaml.safe_load((ROOT / "stories" / sb["geschichte"] / "story.yaml").read_text(encoding="utf-8"))
    st = initial_state(story)
    werte = dict(st["werte"])
    events = []
    for h in tl["hud"]:
        b, n = apply(werte, story["hud"], h["key"], zu=h.get("zu"), delta=h.get("delta"))
        events.append({"t": h["t"], "key": h["key"], "vorher": b, "nachher": n})
    cues = [c for x in tl["cues"] for c in _cues(x["text"], x["start"], x["dauer"], x["erzaehler"])]
    ass = out / "overlay.ass"
    ass.write_text(build_ass(story, st["werte"], events, tl["gesamt"], cues, None, sb["titel"]), encoding="utf-8")

    t1 = time.time()
    ziel = out / "animationsprobe.mp4"
    render.video(tl, mix, ass, ziel, prozesse=a.prozesse)
    bericht = {"datei": str(ziel), "laenge_s": tl["gesamt"], "einstellungen": len(tl["einstellungen"]),
               "lippensync": sorted(lipsync_art), "stimmen": "platzhalter" if a.platzhalter else "piper",
               "renderzeit_s": round(time.time() - t1, 1), "gesamtzeit_s": round(time.time() - t0, 1),
               "sekunden_pro_videosekunde": round((time.time() - t1) / tl["gesamt"], 2)}
    (out / "bericht.json").write_text(json.dumps(bericht, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(bericht, indent=2, ensure_ascii=False))


def main() -> None:
    p = argparse.ArgumentParser(prog="toon")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("probe")
    s.add_argument("--storyboard", default=str(ROOT / "probe" / "animationsprobe.yaml"))
    s.add_argument("--out", default="ausgabe/probe")
    s.add_argument("--platzhalter", action="store_true", help="Töne statt Stimmen (nur Technik-Test)")
    s.add_argument("--standbilder", help="nur einzelne Bilder rendern, z. B. 30,200")
    s.add_argument("--prozesse", type=int, default=2)
    a = p.parse_args()
    {"probe": probe}[a.cmd](a)


if __name__ == "__main__":
    main()
