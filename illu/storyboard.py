"""Storyboard v4 (Weg 1): schnelle Shots mit je einer KI-Illustration, Erzähltext, Kamera und Anzeigen.

Format (stories/<slug>/teil-NN.illu.yaml):

    geschichte, teil, titel, version: 4
    shots:
      - id: s01                     # eindeutig
        ort: strasse                # aus story.yaml › orte
        figuren: [jonas]            # aus story.yaml › figuren (höchstens 2, Ort zählt als 3. Referenz)
        bild: "english prompt"      # was im Bild zu sehen ist (Pose, Ausdruck, Requisiten, Licht)
        bild_von: s03               # statt bild: Bild eines früheren Shots erneut nutzen (andere Kamera Pflicht)
        kamera: ran                 # ran | raus | links | rechts | hoch | runter | ruhig
        fokus: [0.5, 0.4]           # Bildpunkt (0–1), auf den die Kamera zielt
        text: "…"                   # gesprochener Satz (Erzähler oder Figur)
        sprecher: erzaehler         # oder Figuren-Schlüssel (muss im Bild sein)
        emotion: begeistert         # optional, siehe toon.ton.EMOTION
        wort: "ZEHNTAUSEND"         # optional: rot hervorgehobenes Wort (sonst *wort* im Text)
        werte: {geld: {zu: 10000}}  # optional: Anzeigen ändern (zu | delta | items)
        zeige: [schulden]           # optional: Anzeige ohne Änderung einblenden
        popup: "+10.000 €"          # optional: gelber Ausruf
        sfx: [kasse]                # optional: Geräusche aus toon.ton.effekt
        entscheidung: true          # nur letzter Shot
    entscheidung: {frage, optionen: {1: {text, effekte}, 2: …, 3: …}, standard}
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import yaml

from csu.state import StateError, apply, check_choice_effects, effects_to_events

ROOT = Path(__file__).resolve().parent.parent
STIL = ROOT / "config" / "illustration.yaml"
MERKMALE = ("alter", "gesicht", "frisur", "haarfarbe", "haut", "kleidung", "koerper", "kurz")
# Wörter, die Bildmodelle zu (Fantasie-)Schrift verleiten – Text kommt ausschließlich aus der Pipeline
SCHRIFT_WOERTER = re.compile(r"\b(text|texts|writing|written|words?|lettering|letters on|logo|logos|label|labels|"
                             r"caption|numbers?|price tag|headline|sign saying|reads?)\b", re.I)
SFX = ("papier", "posaune", "kasse", "schritt", "stuhl", "glocke", "tuer", "whoosh", "jubel")


def stil() -> dict:
    return yaml.safe_load(STIL.read_text(encoding="utf-8"))


def pfad(slug: str, teil: int) -> Path:
    return ROOT / "stories" / slug / f"teil-{teil:02d}.illu.yaml"


def laden(slug: str, teil: int) -> dict:
    return normalisieren(yaml.safe_load(pfad(slug, teil).read_text(encoding="utf-8")))


def normalisieren(sb: dict) -> dict:
    """bild_von-Shots übernehmen Ort und Figuren ihres Quell-Shots."""
    by = {}
    for s in sb.get("shots") or []:
        q = by.get(s.get("bild_von"))
        if q:
            s.setdefault("ort", q.get("ort"))
            s.setdefault("figuren", q.get("figuren"))
        by[s.get("id")] = s
    return sb


def woerter(text: str) -> list[str]:
    return [w for w in re.sub(r"\[[^\]]*\]", " ", text).split() if re.search(r"\w", w)]


def schaetze_dauer(shot: dict, st: dict) -> float:
    """Geschätzte Shot-Länge vor der Vertonung (danach zählt die echte Tonlänge)."""
    s = st["shot"]
    n = len(woerter(shot.get("text", "")))
    sprech = n / float(s["woerter_pro_s"]) if n else 0.0
    return max(float(shot.get("dauer", 0) or 0), sprech + s["vorlauf_s"] + s["nachlauf_s"], s["min_s"])


def schluesselwort(shot: dict) -> str | None:
    if shot.get("wort"):
        return str(shot["wort"]).upper()
    m = re.search(r"\*([^*]+)\*", shot.get("text", ""))
    return m.group(1).upper() if m else None


def verlauf(story: dict, sb: dict, start: dict) -> list[dict]:
    """Werte vor/nach jedem Shot (Rechnung über csu.state.apply – dieselben Regeln wie in der alten Pipeline)."""
    werte = copy.deepcopy(start)
    out = []
    for shot in sb["shots"]:
        aend = []
        for key, spec in (shot.get("werte") or {}).items():
            spec = spec if isinstance(spec, dict) else {"zu": spec}
            vor, nach = apply(werte, story["hud"], key, zu=spec.get("zu"), delta=spec.get("delta"),
                              items=spec.get("items"))
            aend.append({"key": key, "vor": vor, "nach": nach})
        out.append({"id": shot["id"], "aenderungen": aend, "werte": copy.deepcopy(werte)})
    return out


def pruefen(story: dict, sb: dict, start: dict, st: dict | None = None) -> list[str]:
    st = st or stil()
    f: list[str] = []
    shots = sb.get("shots") or []
    if sb.get("version") != 4:
        f.append("version: 4 fehlt")
    if not shots:
        return f + ["keine Shots"]
    gesehen: dict[str, dict] = {}
    gesehen_figuren: set[str] = set()
    bilder: dict[str, str] = {}
    for i, s in enumerate(shots):
        sid = s.get("id") or f"#{i + 1}"
        if sid in gesehen:
            f.append(f"{sid}: id doppelt")
        if s.get("ort") not in story.get("orte", {}):
            f.append(f"{sid}: unbekannter Ort {s.get('ort')}")
        figs = s.get("figuren") or []
        for fg in figs:
            if fg not in story.get("figuren", {}):
                f.append(f"{sid}: unbekannte Figur {fg}")
            elif fg not in gesehen_figuren:
                fehlt = [k for k in MERKMALE if not (story["figuren"][fg].get("merkmale") or {}).get(k)]
                if fehlt:
                    f.append(f"Figur {fg}: Charakterbibel unvollständig (merkmale: {', '.join(fehlt)})")
                gesehen_figuren.add(fg)
        if len(figs) > st["max_referenzen"] - 1:
            f.append(f"{sid}: höchstens {st['max_referenzen'] - 1} Figuren je Bild (Ort ist die dritte Referenz)")
        if s.get("bild_von"):
            q = gesehen.get(s["bild_von"])
            if not q:
                f.append(f"{sid}: bild_von {s['bild_von']} ist kein früherer Shot")
            elif (q.get("kamera"), q.get("fokus")) == (s.get("kamera"), s.get("fokus")):
                f.append(f"{sid}: wiederverwendetes Bild braucht eine andere Kamera oder einen anderen Fokus")
            elif s.get("figuren", q.get("figuren")) != q.get("figuren"):
                f.append(f"{sid}: bild_von zeigt andere Figuren als angegeben")
        else:
            b = " ".join(str(s.get("bild", "")).split())
            if SCHRIFT_WOERTER.search(b):
                f.append(f"{sid}: Bildbeschreibung verlangt Schrift ({SCHRIFT_WOERTER.search(b).group(0)!r}) – "
                         "Text kommt nur als Overlay")
            if len(b.split()) < 6:
                f.append(f"{sid}: Bildbeschreibung fehlt oder ist zu knapp (mind. 6 Wörter, englisch)")
            elif b.lower() in bilder:
                f.append(f"{sid}: gleiches Bild wie {bilder[b.lower()]} – bild_von mit anderer Kamera nutzen")
            bilder[b.lower()] = sid
        if s.get("kamera", "ran") not in st["kamera_arten"]:
            f.append(f"{sid}: Kamera {s.get('kamera')} unbekannt ({', '.join(st['kamera_arten'])})")
        fok = s.get("fokus", [0.5, 0.45])
        if not (isinstance(fok, list) and len(fok) == 2 and all(0 <= float(v) <= 1 for v in fok)):
            f.append(f"{sid}: fokus muss [x, y] mit Werten 0–1 sein")
        sp = s.get("sprecher", "erzaehler")
        if sp != "erzaehler" and sp not in figs:
            f.append(f"{sid}: Sprecher {sp} ist nicht im Bild")
        d = schaetze_dauer(s, st)
        if d > (9.0 if s.get("entscheidung") else st["shot"]["max_s"]):
            f.append(f"{sid}: ~{d:.1f} s zu lang (max. {st['shot']['max_s']} s) – Satz auf zwei Shots teilen")
        for k in list(s.get("werte") or {}) + list(s.get("zeige") or []):
            if k not in story.get("hud", {}):
                f.append(f"{sid}: unbekannte Anzeige {k}")
        for n in s.get("sfx") or []:
            if n not in SFX:
                f.append(f"{sid}: Geräusch {n} unbekannt ({', '.join(SFX)})")
        if s.get("entscheidung") and i != len(shots) - 1:
            f.append(f"{sid}: entscheidung nur im letzten Shot")
        gesehen[sid] = s
    if not shots[-1].get("entscheidung"):
        f.append("letzter Shot braucht entscheidung: true")
    for a, b in zip(shots, shots[1:]):
        if not b.get("bild_von") and a.get("ort") == b.get("ort") and a.get("figuren") == b.get("figuren") \
                and a.get("kamera") == b.get("kamera") and a.get("kamera") == "ruhig":
            f.append(f"{b.get('id')}: zwei ruhige Shots derselben Einstellung hintereinander")
    gesamt = sum(schaetze_dauer(s, st) + (1.6 if s.get("entscheidung") else 0) for s in shots)
    if not st["folge"]["min_s"] <= gesamt <= st["folge"]["max_s"]:
        f.append(f"Gesamtlänge ~{gesamt:.0f} s außerhalb {st['folge']['min_s']}–{st['folge']['max_s']} s")
    try:
        v = verlauf(story, sb, start)
    except StateError as exc:
        return f + [f"Anzeigen: {exc}"]
    ent = sb.get("entscheidung") or {}
    if len(ent.get("optionen") or {}) != 3:
        f.append("entscheidung braucht genau 3 Optionen")
    else:
        f += check_choice_effects(story, v[-1]["werte"], ent)
        for nr, opt in ent["optionen"].items():
            for ev in effects_to_events(opt.get("effekte")):
                if ev["key"] not in story["hud"]:
                    f.append(f"Option {nr}: unbekannte Anzeige {ev['key']}")
    return f
