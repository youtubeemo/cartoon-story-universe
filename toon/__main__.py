"""2D-Pipeline (toon) – Befehle:

  python -m toon probe  --storyboard … [--stimmen elevenlabs|piper|platzhalter] [--credit-grenze N] [--max-sekunden S]
  python -m toon folge  --geschichte SLUG [--stimmen …] [--bestaetigung …] [--geplant] [--datum …]
  python -m toon pruefen  (kostenlos: alle Figuren, Orte, Storyboards)

ElevenLabs nur im Abo, mit harter Credit-Obergrenze, kostenloser Vorprüfung und Archiv gegen Doppelzahlung.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from csu.hud import build_ass  # noqa: E402
from csu.state import apply, effects_to_events, load_state, save_state  # noqa: E402
from toon import render, szene, ton  # noqa: E402
from toon.validate_zeit import schaetze  # noqa: E402


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


def _el_text(text: str, emotion: str | None, voice: dict) -> str:
    tag = ton.EMOTION.get(emotion or "")
    return f"{tag} {text}" if tag and voice.get("model", "eleven_v3") == "eleven_v3" else text


def produzieren(sb: dict, out: Path, dateiname: str, stimmen: str, grenze: int, min_s: float, max_s: float,
                story: dict, start_werte: dict, start_effekte: list | None = None, nur_standbilder=None) -> dict:
    t0 = time.time()
    errs = szene.pruefen(sb)
    if errs:
        raise SystemExit("Storyboard-Prüfung:\n  " + "\n  ".join(errs))
    geschaetzt = schaetze(sb)
    if max_s and not (min_s - 3 <= geschaetzt <= max_s):
        raise SystemExit(f"Geschätzte Länge {geschaetzt:.1f} s außerhalb {min_s}–{max_s} s – keine Kosten entstanden.")
    (out / "ton").mkdir(parents=True, exist_ok=True)
    figuren = szene.lade_figuren(szene._figuren_der_folge(sb))

    budget = ton.CreditBudget(grenze)
    if stimmen == "elevenlabs":
        geplant = 0
        for e in sb["einstellungen"]:
            for b in e.get("ablauf", []):
                txt = b.get("sagt") or b.get("erzaehler")
                if txt:
                    f = b.get("figur") if b.get("sagt") else None
                    voice = ton.el_stimme_fuer(figuren[f] if f else None, f)
                    t_el = _el_text(txt, b.get("ton") or b.get("ausdruck"), voice)
                    if not ton._archiv_pfad(voice, t_el).exists():
                        geplant += ton.el_credits(t_el)
        budget.pruefen(geplant)
        vor = ton.el_vorpruefung(geplant) if geplant else {"tarif": "-", "frei": "-"}
        print(f"ElevenLabs: geplant {geplant} Credits (Grenze {grenze}), Abo {vor['tarif']}, frei {vor['frei']}")

    arten = set()

    def ton_fn(sprecher, text, key, emotion=None):
        wav = out / "ton" / f"{key}.wav"
        if stimmen == "elevenlabs":
            voice = ton.el_stimme_fuer(figuren[sprecher] if sprecher else None, sprecher)
            info = ton.elevenlabs(_el_text(text, emotion, voice), voice, wav, budget)
        else:
            cfg = figuren[sprecher].get("stimme", {}) if sprecher else ton.ERZAEHLER_PIPER
            info = ton.stimme(text, cfg, wav, platzhalter=(stimmen == "platzhalter"))
        formen, art = ton.mundformen(Path(info["file"]), text) if sprecher else ([], "-")
        arten.add(art)
        return Path(info["file"]), info["dauer"], formen

    tl = szene.zeitleiste(sb, ton_fn)
    if nur_standbilder:
        for f in nur_standbilder:
            render.standbild(tl, f, out / f"standbild_{f:04d}.png")
        return {"standbilder": str(out)}
    if max_s and tl["gesamt"] > max_s + 0.5:
        raise SystemExit(f"Länge {tl['gesamt']:.1f} s > {max_s} s – kein Render.")

    effekte = [(ton.effekt(n, out / "ton" / f"sfx_{i:03d}_{n}.wav", variante=i), at, ton.LAUTSTAERKE.get(n, 0.6))
               for i, (n, at) in enumerate(tl["effekte"])]
    musik = ton.musik(tl["gesamt"], sb.get("musik", {}).get("stimmung", "verschmitzt"), out / "ton" / "musik.wav")
    mix = ton.mischen(tl["stimmen"], effekte, musik, tl["gesamt"], out / "ton" / "mischung.wav")

    werte = json.loads(json.dumps(start_werte))
    events = []
    for ev in start_effekte or []:
        b, n = apply(werte, story["hud"], ev["key"], delta=ev.get("delta"), items=ev.get("items"))
        events.append({"t": 0.8, "key": ev["key"], "vorher": b, "nachher": n, "quelle": ev.get("quelle")})
    for h in tl["hud"]:
        b, n = apply(werte, story["hud"], h["key"], zu=h.get("zu"), delta=h.get("delta"), items=h.get("items"))
        events.append({"t": h["t"], "key": h["key"], "vorher": b, "nachher": n})
    cues = [c for x in tl["cues"] for c in _cues(x["text"], x["start"], x["dauer"], x["erzaehler"])]
    wahl = None
    if sb.get("entscheidung"):
        letzte = tl["einstellungen"][-1]
        wahl = {**sb["entscheidung"], "start": letzte.start + 0.4}
        wahl["optionen"] = {int(k): v for k, v in wahl["optionen"].items()}
        cues = [c for c in cues if c["start"] < wahl["start"]]
    ass = out / "overlay.ass"
    ass.write_text(build_ass(story, start_werte, events, tl["gesamt"], cues, wahl, sb["titel"]), encoding="utf-8")

    t1 = time.time()
    ziel = out / dateiname
    render.video(tl, mix, ass, ziel, prozesse=int(os.environ.get("TOON_PROZESSE", "2")))
    from csu import qc
    pruef = (qc.technisch(ziel, 1080, 1920, 30, (min_s if max_s else 1, max_s or 999), [])
             + qc.ton(ziel, tl["gesamt"]) + qc.untertitel(cues, tl["gesamt"]))
    bericht = {"datei": str(ziel), "laenge_s": tl["gesamt"], "einstellungen": len(tl["einstellungen"]),
               "lippensync": sorted(x for x in arten if x != "-"), "stimmen": stimmen,
               "elevenlabs_credits": budget.verbraucht, "elevenlabs_wiederverwendet": budget.wiederverwendet,
               "renderzeit_s": round(time.time() - t1, 1), "gesamtzeit_s": round(time.time() - t0, 1),
               "endwerte": werte,
               "qualitaetskontrolle": [{"ok": bool(o), "pruefung": n, "detail": d} for o, n, d in pruef]}
    (out / "bericht.json").write_text(json.dumps(bericht, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in bericht.items() if k != "endwerte"}, indent=2, ensure_ascii=False))
    if not all(o for o, _, _ in pruef):
        raise SystemExit("Qualitätskontrolle nicht bestanden")
    return bericht


def _story(slug: str) -> dict:
    return yaml.safe_load((ROOT / "stories" / slug / "story.yaml").read_text(encoding="utf-8"))


def cmd_probe(a) -> None:
    sb = yaml.safe_load(Path(a.storyboard).read_text(encoding="utf-8"))
    story = _story(sb["geschichte"])
    from csu.state import initial_state
    produzieren(sb, Path(a.out), a.dateiname, a.stimmen, a.credit_grenze, 0, a.max_sekunden, story,
                initial_state(story)["werte"],
                nur_standbilder=[int(x) for x in a.standbilder.split(",")] if a.standbilder else None)


def cmd_folge(a) -> None:
    """Tagesfolge: Freigaben → Abstimmung → Drehbuch (falls nötig) → Prüfung → Stimmen → Render → QC → Stand."""
    from csu.common import budget
    from csu.kasse import BudgetStopp, Kasse, git_sync
    from toon import drehbuch
    b = budget()
    d = dt.date.fromisoformat(a.datum) if a.datum else dt.date.today()
    story = _story(a.geschichte)
    st = load_state(story)
    teil = st["naechster_teil"]
    sb_pfad = drehbuch.pfad(story["slug"], teil)
    kostet = a.stimmen == "elevenlabs" or not sb_pfad.exists()
    if a.geplant and not b["taeglich_aktiv"]:
        raise SystemExit("Tägliche Produktion ist nicht freigegeben (taeglich_aktiv: false). 0 €.")
    if kostet and (not b["paid_rendering_enabled"] or (not a.geplant and a.bestaetigung.strip() != b["approval_phrase"])):
        raise SystemExit("Kostenpflichtige Schritte (ElevenLabs/Claude) nicht freigegeben – Abbruch, 0 €.")

    from csu.cli import resolve_vote
    from csu.voting import decide, fetch_youtube_comments, parse_manual, tally
    print(resolve_vote(story, st, a.youtube_video_id, a.tiktok_stimmen, decide, fetch_youtube_comments,
                       parse_manual, tally))
    save_state(st)
    if not sb_pfad.exists():
        if not b["drehbuch_api_aktiv"]:
            raise SystemExit(f"Storyboard {sb_pfad.name} fehlt und drehbuch_api_aktiv ist false.")
        from csu.script import max_cost_eur
        kasse = Kasse(float(b.get("monatsbudget_eur") or 0), monat=d.strftime("%Y-%m"))
        run = os.environ.get("GITHUB_RUN_ID") or f"lokal-{int(time.time())}"
        try:
            kasse.reservieren(run, max_cost_eur(), f"Drehbuch {story['slug']} {teil}")
            git_sync("Kasse: Reservierung Drehbuch", ["state"])
        except BudgetStopp as exc:
            raise SystemExit(str(exc))
        res = drehbuch.generieren(story, st, ROOT / "probe" / "animationsprobe2.yaml")
        kasse.buchen(run, "anthropic", res["eur"], None, "Drehbuch v3")
        kasse.aufloesen(run)
    sb = yaml.safe_load(sb_pfad.read_text(encoding="utf-8"))
    wahl = st.get("offene_entscheidung") or {}
    start_effekte = [{**e, "quelle": f"Eure Wahl: {wahl['option']}"} for e in effects_to_events(wahl.get("effekte"))] \
        if wahl.get("option") else []
    name = f"{d}_{story['slug']}_teil-{teil:02d}.mp4"
    grenze = int(b.get("elevenlabs_max_credits_pro_folge", 2500))
    bericht = produzieren(sb, Path(a.out), name, a.stimmen, grenze, 60, 90, story, st["werte"], start_effekte)
    st["werte"] = bericht["endwerte"]
    st["verlauf"].append({"teil": teil, "datum": str(d), "datei": name, "titel": sb["titel"],
                          "wahl_davor": wahl.get("option"), "werte_danach": bericht["endwerte"],
                          "elevenlabs_credits": bericht["elevenlabs_credits"]})
    e = sb["entscheidung"]
    st["offene_entscheidung"] = {"teil": teil, "frage": e["frage"], "standard": e["standard"],
                                 "optionen": {str(k): v for k, v in e["optionen"].items()}, "option": None}
    st["naechster_teil"] = teil + 1
    save_state(st)
    tag = f"{d}-{story['slug']}-teil-{teil:02d}"
    (Path(a.out) / "release.json").write_text(json.dumps({"tag": tag, "datei": bericht["datei"], "dateiname": name,
                                                          "titel": f"{story['titel']} – Teil {teil}: {sb['titel']}"},
                                                         ensure_ascii=False), encoding="utf-8")


def cmd_pruefen(a) -> None:
    """Kostenlos: jede Figur und jeder Ort lässt sich zeichnen, alle Storyboards bestehen die Logikprüfung."""
    from PIL import Image
    from toon.anim import Spur
    from toon.geo import M, Pen
    from toon.orte import ORTE, alle
    from toon.tiere import figur_fuer
    fehler = []
    for o in alle():
        try:
            ORTE[o](Pen(Image.new("RGB", (90, 160)), M(0, 0, 0, 1 / 16, 1 / 16)), "tag")
        except Exception as exc:  # noqa: BLE001
            fehler.append(f"Ort {o}: {exc}")
    for f in sorted((ROOT / "toon" / "figuren").glob("*.yaml")):
        try:
            pen = Pen(Image.new("RGB", (90, 160)), M(0, 0, 0, 1 / 16, 1 / 16))
            figur_fuer(yaml.safe_load(f.read_text())).zeichne(pen, Spur("x", 1, 500).zustand(0.5, 2000, 900, 900))
        except Exception as exc:  # noqa: BLE001
            fehler.append(f"Figur {f.stem}: {exc}")
    for p in list((ROOT / "probe").glob("*.yaml")) + list((ROOT / "stories").glob("*/toon/*.yaml")):
        fehler += [f"{p.name}: {e}" for e in szene.pruefen(yaml.safe_load(p.read_text(encoding="utf-8")))]
    print("\n".join(fehler) or "✓ alle Figuren, Orte und Storyboards in Ordnung")
    if fehler:
        raise SystemExit(1)


def main() -> None:
    p = argparse.ArgumentParser(prog="toon")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("probe")
    s.add_argument("--storyboard", default=str(ROOT / "probe" / "animationsprobe2.yaml"))
    s.add_argument("--out", default="ausgabe/probe")
    s.add_argument("--dateiname", default="animationsprobe.mp4")
    s.add_argument("--stimmen", choices=["elevenlabs", "piper", "platzhalter"], default="piper")
    s.add_argument("--credit-grenze", type=int, default=0)
    s.add_argument("--max-sekunden", type=float, default=0)
    s.add_argument("--standbilder")
    s = sub.add_parser("folge")
    s.add_argument("--geschichte", required=True)
    s.add_argument("--datum")
    s.add_argument("--stimmen", choices=["elevenlabs", "piper"], default="elevenlabs")
    s.add_argument("--bestaetigung", default="")
    s.add_argument("--geplant", action="store_true")
    s.add_argument("--youtube-video-id")
    s.add_argument("--tiktok-stimmen")
    s.add_argument("--out", default="ausgabe/folge")
    sub.add_parser("pruefen")
    a = p.parse_args()
    if a.cmd == "probe" and a.stimmen == "elevenlabs" and a.credit_grenze <= 0:
        raise SystemExit("--credit-grenze angeben (z. B. 300)")
    {"probe": cmd_probe, "folge": cmd_folge, "pruefen": cmd_pruefen}[a.cmd](a)


if __name__ == "__main__":
    main()
