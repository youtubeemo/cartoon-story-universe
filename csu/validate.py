"""Kostenlose Prüfung von Geschichten und Storyboards – läuft vor JEDEM bezahlten Schritt.

Storyboard-Format v2 (verbindlich): jede Szene hat Nummer, Ort, Figuren, Handlung, Bild, Kamera,
Kamerabewegung, Bewegung, Übergang, Tageszeit, Dauer; optional Erzähler, Dialog, SFX, Statusänderung.
Die Regeln erzwingen logische Übergänge (siehe ``_continuity``).
"""
from __future__ import annotations

import re

from csu.common import CONFIG, load_yaml
from csu.state import StateError, check_choice_effects, initial_state, simulate

CHARS_PER_SECOND = 14.0      # deutsches Sprechtempo (ElevenLabs v3) – konservativ
LINE_GAP = 0.25
VIEW_SUFFIX = {"vorne": "v", "seite": "s", "dreiviertel": "d"}
TAGESZEIT = ["morgen", "tag", "abend", "nacht"]
VEO_DAUERN = {4, 6, 8}
PFLICHT = ("nr", "ort", "figuren", "handlung", "bild", "kamera", "kamerabewegung", "bewegung", "uebergang",
           "tageszeit", "dauer")


def stil() -> dict:
    return load_yaml(CONFIG / "stil.yaml")


def speech_seconds(scene: dict) -> float:
    lines = ([scene["erzaehler"]] if scene.get("erzaehler") else []) + [d["text"] for d in scene.get("dialog") or []]
    return sum(len(t) / CHARS_PER_SECOND + LINE_GAP for t in lines) + (0.3 if lines else 0)


def ref_tag(figur: str, ansicht: str) -> str:
    return f"{figur[:13]}_{VIEW_SUFFIX[ansicht]}"


def scene_refs(story: dict, s: dict) -> list[tuple[str, str]]:
    """[(tag, Beschreibung)] – Figuren in der gewählten Ansicht, dann der Ort (max. 3 Referenzen)."""
    refs = []
    for f in s.get("figuren") or []:
        ansicht = (s.get("ansicht") or {}).get(f, "dreiviertel")
        refs.append((ref_tag(f, ansicht), f"{story['figuren'][f]['name']} ({ansicht})"))
    if len(refs) < 3:
        refs.append((s["ort"][:16], f"Ort {s['ort']}"))
    return refs[:3]


def validate_story(story: dict) -> list[str]:
    errs = []
    slug = story.get("slug")
    for f in ("slug", "titel", "thema", "teile", "figuren", "orte", "hud", "anzeige", "musik"):
        if f not in story:
            errs.append(f"{slug}: Feld {f} fehlt")
    for key in story.get("anzeige", []):
        if key not in story.get("hud", {}):
            errs.append(f"{slug}: Anzeige {key} ohne hud-Definition")
    for key, fig in (story.get("figuren") or {}).items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,12}", key):
            errs.append(f"{slug}: Figurenschlüssel {key} muss 2–13 Kleinbuchstaben/Ziffern haben")
        if not fig.get("reference_prompt"):
            errs.append(f"{slug}: {key} ohne reference_prompt")
        if fig.get("voice") and not re.fullmatch(r"[A-Za-z0-9]{20}", str(fig["voice"].get("voice_id", ""))):
            errs.append(f"{slug}: {key} hat keine gültige voice_id")
    for key in (story.get("orte") or {}):
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,15}", key):
            errs.append(f"{slug}: Ortsschlüssel {key} muss 3–16 Zeichen haben")
    try:
        initial_state(story)
    except StateError as exc:
        errs.append(str(exc))
    entwurf = story.get("teil_01_entwurf")
    if entwurf:
        errs += [f"{slug} Entwurf: {e}" for e in _check_choices(entwurf.get("entscheidung") or {})]
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


def _continuity(story: dict, scenes: list[dict]) -> list[str]:
    """Logische Szenenübergänge."""
    st = stil()
    errs, seen_orte = [], set()
    prev = None
    for s in scenes:
        sid, ue = s["id"], s.get("uebergang")
        if ue not in st["uebergaenge"]:
            errs.append(f"{sid}: uebergang {ue!r} unbekannt ({', '.join(st['uebergaenge'])})")
            continue
        if prev is None:
            if ue not in ("abblende", "schnitt"):
                errs.append(f"{sid}: erste Szene braucht uebergang abblende oder schnitt")
        else:
            same_place = s["ort"] == prev["ort"]
            if ue == "anschluss":
                if not same_place or sorted(s["figuren"]) != sorted(prev["figuren"]):
                    errs.append(f"{sid}: „anschluss“ nur bei gleichem Ort und gleichen Figuren wie {prev['id']}")
                if s["kamera"] != prev["kamera"] or s["tageszeit"] != prev["tageszeit"]:
                    errs.append(f"{sid}: „anschluss“ verlangt gleiche Kamera und Tageszeit wie {prev['id']}")
            if ue == "schnitt" and same_place and s["kamera"] == prev["kamera"] \
                    and sorted(s["figuren"]) == sorted(prev["figuren"]):
                errs.append(f"{sid}: Sprung-Schnitt (gleicher Ort, gleiche Figuren, gleiche Einstellung wie "
                            f"{prev['id']}) – „anschluss“ oder andere Einstellung verwenden")
            t_prev, t_now = TAGESZEIT.index(prev["tageszeit"]), TAGESZEIT.index(s["tageszeit"])
            if t_now < t_prev and ue not in ("ueberblendung", "abblende"):
                errs.append(f"{sid}: Tageszeit springt zurück ({prev['tageszeit']} → {s['tageszeit']}) "
                            "ohne Überblendung")
        if s["ort"] not in seen_orte and ue != "anschluss" and s["kamera"] not in ("totale", "halbtotale") \
                and s["figuren"]:
            # neuer Ort ohne Orientierung → nur erlaubt, wenn die Szene davor ihn schon gezeigt hat
            errs.append(f"{sid}: erster Auftritt von Ort „{s['ort']}“ braucht totale oder halbtotale (Orientierung)")
        seen_orte.add(s["ort"])
        prev = s
    return errs


def validate_episode(story: dict, ep: dict, state: dict, ziel=(60, 90)) -> tuple[list[str], list[str], dict]:
    """Rückgabe (Fehler, Warnungen, Info). Fehler blockieren jede bezahlte Produktion."""
    errs, warns = [], []
    st = stil()
    slug = story["slug"]
    if ep.get("geschichte") != slug:
        errs.append(f"Folge gehört zu {ep.get('geschichte')}, nicht zu {slug}")
    if int(ep.get("teil", 0)) != int(state["naechster_teil"]):
        errs.append(f"Teil {ep.get('teil')} passt nicht zum Stand (nächster Teil: {state['naechster_teil']})")
    figuren, orte = story.get("figuren") or {}, story.get("orte") or {}
    scenes = ep.get("szenen") or []
    if not 8 <= len(scenes) <= 16:
        errs.append(f"{len(scenes)} Szenen – erlaubt sind 8–16")
    total = 0.0
    for i, s in enumerate(scenes, 1):
        sid = s.get("id", f"#{i}")
        missing = [f for f in PFLICHT if s.get(f) in (None, "") and f != "figuren"]
        if "figuren" not in s:
            missing.append("figuren")
        if missing:
            errs.append(f"{sid}: Pflichtfelder fehlen: {', '.join(missing)}")
            continue
        if int(s["nr"]) != i:
            errs.append(f"{sid}: Nummerierung lückenhaft (erwartet {i})")
        if s["ort"] not in orte:
            errs.append(f"{sid}: Ort {s['ort']} nicht in der Story-Bibel")
        for f in s["figuren"]:
            if f not in figuren:
                errs.append(f"{sid}: Figur {f} nicht in der Story-Bibel")
        if len(s["figuren"]) > 3:
            errs.append(f"{sid}: höchstens 3 Figuren je Szene (Referenzlimit)")
        for f, a in (s.get("ansicht") or {}).items():
            if a not in VIEW_SUFFIX or f not in s["figuren"]:
                errs.append(f"{sid}: ansicht {f}: {a} ungültig")
        if s["kamera"] not in st["kamera"]:
            errs.append(f"{sid}: kamera {s['kamera']!r} unbekannt")
        if s["kamerabewegung"] not in st["kamerabewegung"]:
            errs.append(f"{sid}: kamerabewegung {s['kamerabewegung']!r} unbekannt (genau eine oder statisch)")
        if s["tageszeit"] not in TAGESZEIT:
            errs.append(f"{sid}: tageszeit muss {TAGESZEIT} sein")
        if int(s["dauer"]) not in VEO_DAUERN:
            errs.append(f"{sid}: dauer {s['dauer']} – erlaubt 4, 6 oder 8 s (Videomodell)")
        if re.search(r"@\w", s["bild"] + s["bewegung"]):
            errs.append(f"{sid}: keine @-Tags im Text – Figuren/Ort kommen aus den Feldern")
        if len(s["bewegung"].split()) < 5:
            errs.append(f"{sid}: bewegung zu knapp – konkrete Handlung beschreiben")
        for d in s.get("dialog") or []:
            if d.get("figur") not in s["figuren"]:
                errs.append(f"{sid}: {d.get('figur')} spricht, ist aber nicht im Bild")
            elif not figuren[d["figur"]].get("voice"):
                errs.append(f"{sid}: {d['figur']} hat keine Stimme")
        sp = speech_seconds(s)
        if sp > float(s["dauer"]) + 0.3:
            errs.append(f"{sid}: Sprechtext ≈{sp:.1f}s passt nicht in {s['dauer']}s – kürzen oder längere Szene")
        if len(s.get("hud") or []) > 1:
            errs.append(f"{sid}: höchstens eine Statusänderung je Szene")
        total += float(s["dauer"])
    if errs:
        return errs, warns, {}
    errs += _continuity(story, scenes)
    if not scenes[-1].get("entscheidung"):
        errs.append("letzte Szene muss entscheidung: true haben (Cliffhanger mit Auswahl)")
    if not ziel[0] <= total <= ziel[1]:
        errs.append(f"Länge {total:.0f}s außerhalb {ziel[0]}–{ziel[1]} s")
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
