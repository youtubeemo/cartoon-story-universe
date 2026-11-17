"""Statuswerte je Geschichte: dauerhaft gespeichert, jede Änderung rechnerisch geprüft.

Eine Anzeige zeigt immer „vorher → nachher“. „vorher“ kommt IMMER aus dem gespeicherten Stand,
nie aus dem Drehbuch – damit stimmen alle Zahlen über sämtliche Fortsetzungen hinweg.
"""
from __future__ import annotations

import copy
from pathlib import Path

from csu.common import STATE, write_json

TYPES = {"geld", "prozent", "zahl", "tage", "stunden", "jahr", "sterne", "bruch", "inventar"}


class StateError(ValueError):
    pass


def bounds(d: dict) -> tuple[float | None, float | None]:
    typ = d["typ"]
    lo, hi = d.get("min"), d.get("max")
    if typ == "prozent":
        lo, hi = (0 if lo is None else lo), (100 if hi is None else hi)
    elif typ == "sterne":
        lo, hi = (0 if lo is None else lo), (5 if hi is None else hi)
    elif typ in ("tage", "stunden", "bruch") and lo is None:
        lo = 0
    return lo, hi


def initial_state(story: dict) -> dict:
    werte = {}
    for key, d in story["hud"].items():
        if d["typ"] not in TYPES:
            raise StateError(f"{story['slug']}: unbekannter Anzeigetyp {d['typ']} ({key})")
        werte[key] = list(d["start"]) if d["typ"] == "inventar" else d["start"]
    return {"geschichte": story["slug"], "naechster_teil": 1, "werte": werte,
            "offene_entscheidung": None, "verlauf": []}


def state_path(slug: str) -> Path:
    return STATE / f"{slug}.json"


def load_state(story: dict) -> dict:
    p = state_path(story["slug"])
    if p.exists():
        import json
        return json.loads(p.read_text(encoding="utf-8"))
    return initial_state(story)


def save_state(state: dict) -> None:
    write_json(state_path(state["geschichte"]), state)


def apply(werte: dict, hud: dict, key: str, *, zu=None, delta=None, items=None) -> tuple:
    """Wendet EINE Änderung an (in place). Rückgabe (vorher, nachher). Wirft StateError bei Regelverstoß."""
    if key not in hud:
        raise StateError(f"unbekannte Anzeige {key}")
    d = hud[key]
    before = copy.deepcopy(werte[key])
    if d["typ"] == "inventar":
        inv = list(before)
        for it in items or []:
            name = it[1:].strip()
            if it.startswith("+"):
                inv.append(name)
            elif it.startswith("-"):
                if name not in inv:
                    raise StateError(f"Inventar: „{name}“ ist nicht vorhanden ({inv})")
                inv.remove(name)
            else:
                raise StateError(f"Inventar-Eintrag braucht + oder -: {it}")
        werte[key] = inv
        return before, inv
    if (zu is None) == (delta is None):
        raise StateError(f"{key}: genau eines von „zu“ oder „delta“ angeben")
    after = zu if zu is not None else before + delta
    if not isinstance(after, int) or isinstance(after, bool):
        if float(after).is_integer():
            after = int(after)
        else:
            raise StateError(f"{key}: nur ganze Zahlen ({after})")
    lo, hi = bounds(d)
    if lo is not None and after < lo:
        raise StateError(f"{key}: {before} → {after} unterschreitet Minimum {lo}")
    if hi is not None and after > hi:
        raise StateError(f"{key}: {before} → {after} überschreitet Maximum {hi}")
    werte[key] = after
    return before, after


def effects_to_events(effekte: dict) -> list[dict]:
    """Entscheidungs-Effekte {geld: -600, inventar: ["+Seil"]} -> HUD-Ereignisse."""
    out = []
    for key, val in (effekte or {}).items():
        if isinstance(val, list):
            out.append({"key": key, "items": val})
        else:
            out.append({"key": key, "delta": val})
    return out


def simulate(story: dict, state: dict, episode: dict) -> tuple[list[dict], dict]:
    """Spielt Start-Effekte (letzte Zuschauerwahl) + alle HUD-Ereignisse der Folge durch.

    Rückgabe: (Ereignisse mit vorher/nachher je Szene, Endwerte). Ändert ``state`` nicht.
    """
    werte = copy.deepcopy(state["werte"])
    hud = story["hud"]
    events: list[dict] = []
    wahl = state.get("offene_entscheidung")
    if wahl and wahl.get("option"):
        for ev in effects_to_events(wahl.get("effekte")):
            b, a = apply(werte, hud, ev["key"], delta=ev.get("delta"), items=ev.get("items"))
            events.append({"szene": episode["szenen"][0]["id"], "key": ev["key"], "vorher": b, "nachher": a,
                           "quelle": f"Eure Wahl: {wahl['option']}"})
    for s in episode["szenen"]:
        for ev in s.get("hud") or []:
            try:
                b, a = apply(werte, hud, ev["key"], zu=ev.get("zu"), delta=ev.get("delta"), items=ev.get("items"))
            except StateError as exc:
                raise StateError(f"{s['id']}: {exc}") from exc
            events.append({"szene": s["id"], "key": ev["key"], "vorher": b, "nachher": a})
    return events, werte


def check_choice_effects(story: dict, werte: dict, entscheidung: dict) -> list[str]:
    """Jede der drei Optionen muss vom Endstand aus rechnerisch möglich sein."""
    errs = []
    for nr, opt in (entscheidung.get("optionen") or {}).items():
        trial = copy.deepcopy(werte)
        for ev in effects_to_events(opt.get("effekte")):
            try:
                apply(trial, story["hud"], ev["key"], delta=ev.get("delta"), items=ev.get("items"))
            except StateError as exc:
                errs.append(f"Option {nr}: {exc}")
    return errs

