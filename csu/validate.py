"""Kostenlose Prüfung von Geschichten und Folgen – läuft vor jedem bezahlten Schritt."""
from __future__ import annotations

import re

from csu.state import StateError, check_choice_effects, initial_state, simulate

TAG = re.compile(r"@([a-z0-9_]+)")
CHARS_PER_SECOND = 14.0      # deutsches Sprechtempo (Erzähler, ElevenLabs v3) – konservativ
LINE_GAP = 0.25


def tags_in(text: str) -> list[str]:
    return list(dict.fromkeys(TAG.findall(text or "")))


def speech_seconds(scene: dict) -> float:
    lines = ([scene["erzaehler"]] if scene.get("erzaehler") else []) + [d["text"] for d in scene.get("dialog") or []]
    return sum(len(t) / CHARS_PER_SECOND + LINE_GAP for t in lines)


def ref_sources(story: dict) -> dict[str, str]:
    out = {}
    for group in ("figuren", "orte"):
        for key, d in (story.get(group) or {}).items():
            if d.get("ref_tag"):
                out[d["ref_tag"]] = d["reference_prompt"]
    return out


def validate_story(story: dict) -> list[str]:
    errs = []
    for f in ("slug", "titel", "thema", "teile", "figuren", "orte", "hud", "anzeige", "musik"):
        if f not in story:
            errs.append(f"{story.get('slug')}: Feld {f} fehlt")
    for key in story.get("anzeige", []):
        if key not in story.get("hud", {}):
            errs.append(f"{story.get('slug')}: Anzeige {key} ohne hud-Definition")
    for key, fig in (story.get("figuren") or {}).items():
        if fig.get("voice") and not re.fullmatch(r"[A-Za-z0-9]{20}", str(fig["voice"].get("voice_id", ""))):
            errs.append(f"{story['slug']}: {key} hat keine gültige voice_id")
    try:
        initial_state(story)
    except StateError as exc:
        errs.append(str(exc))
    entwurf = story.get("teil_01_entwurf")
    if entwurf:
        errs += [f"{story['slug']} Entwurf: {e}" for e in _check_choices(entwurf.get("entscheidung") or {})]
    return errs


def _check_choices(ent: dict) -> list[str]:
    errs = []
    opts = ent.get("optionen") or {}
    if sorted(int(k) for k in opts) != [1, 2, 3]:
        errs.append("Entscheidung braucht genau die Optionen 1, 2 und 3")
    if int(ent.get("standard", 0)) not in (1, 2, 3):
        errs.append("Entscheidung: standard muss 1, 2 oder 3 sein")
    if not ent.get("frage"):
        errs.append("Entscheidung: frage fehlt")
    return errs


def validate_episode(story: dict, ep: dict, state: dict, ziel=(60, 90)) -> tuple[list[str], list[str], dict]:
    """Rückgabe (Fehler, Warnungen, Info). Fehler blockieren jede bezahlte Produktion."""
    errs, warns = [], []
    slug = story["slug"]
    if ep.get("geschichte") != slug:
        errs.append(f"Folge gehört zu {ep.get('geschichte')}, nicht zu {slug}")
    if int(ep.get("teil", 0)) != int(state["naechster_teil"]):
        errs.append(f"Teil {ep.get('teil')} passt nicht zum Stand (nächster Teil: {state['naechster_teil']})")
    sources = ref_sources(story)
    figuren = story.get("figuren") or {}
    total = 0.0
    ids = set()
    scenes = ep.get("szenen") or []
    for s in scenes:
        sid = s.get("id", "?")
        if sid in ids:
            errs.append(f"{sid}: doppelte Szenen-ID")
        ids.add(sid)
        for f in ("dauer", "keyframe_prompt", "motion_prompt"):
            if not s.get(f):
                errs.append(f"{sid}: Feld {f} fehlt")
        dauer = float(s.get("dauer", 0))
        if not 2 <= dauer <= 10:
            errs.append(f"{sid}: dauer {dauer}s außerhalb 2–10 s (Runway-Clip max. 10 s)")
        for t in tags_in(s.get("keyframe_prompt", "")):
            if t not in sources:
                errs.append(f"{sid}: unbekannter Referenz-Tag @{t}")
        if len(tags_in(s.get("keyframe_prompt", ""))) > 3:
            warns.append(f"{sid}: mehr als 3 Referenzen – nur die ersten 3 werden genutzt")
        for d in s.get("dialog") or []:
            fig = figuren.get(d.get("figur"))
            if not fig or not fig.get("voice"):
                errs.append(f"{sid}: Figur {d.get('figur')} unbekannt oder ohne Stimme")
        sp = speech_seconds(s)
        if sp > dauer + 1.5:
            warns.append(f"{sid}: Sprechtext ≈{sp:.1f}s > Szene {dauer:.0f}s – Szene wird automatisch verlängert")
        total += max(dauer, sp + 0.4)
    if not scenes:
        errs.append("keine Szenen")
    elif not scenes[-1].get("entscheidung"):
        errs.append("letzte Szene muss entscheidung: true haben (Cliffhanger mit Auswahl)")
    if not ziel[0] <= total <= ziel[1]:
        errs.append(f"geschätzte Länge {total:.0f}s außerhalb {ziel[0]}–{ziel[1]} s")
    errs += _check_choices(ep.get("entscheidung") or {})
    info = {"laenge_s": round(total, 1), "szenen": len(scenes)}
    try:
        events, werte = simulate(story, state, ep)
        info["ereignisse"] = events
        info["endwerte"] = werte
        errs += check_choice_effects(story, werte, ep.get("entscheidung") or {})
    except StateError as exc:
        errs.append(f"Statusanzeigen: {exc}")
    return errs, warns, info
