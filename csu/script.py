"""Drehbuch der nächsten Folge per Claude-API (nur wenn budget.yaml drehbuch_api_aktiv: true).

Ein Aufruf pro Folge, keine automatische Wiederholung. Das Ergebnis wird kostenlos geprüft
(csu.validate); ist es ungültig, bricht der Lauf ab, bevor Runway/ElevenLabs Geld kosten.
"""
from __future__ import annotations

import json
import os
import urllib.request

import yaml

from csu.common import STORIES, budget, episode_path, load_episode

SYSTEM = """Du schreibst Folgen einer deutschen 2D-Cartoon-Serie im Hochformat (TikTok/Shorts), 60–90 Sekunden.
Antworte NUR mit gültigem YAML im exakt gleichen Schema wie die Beispiel-Folge. Regeln:
- 12–15 Szenen, je 3–9 s; letzte Szene hat `entscheidung: true` (Cliffhanger, Erzähler fragt nach 1, 2 oder 3).
- keyframe_prompt und motion_prompt auf Englisch, Figuren/Orte NUR über @ref_tag aus der Story-Bibel, max. 3 Tags.
- Erzähler- und Dialogtexte auf Deutsch, kurz (≤ 14 Zeichen pro Sekunde Szenendauer), Zahlen ausgeschrieben.
- Die Folge setzt GENAU die gewählte Option der letzten Folge fort (ihre Effekte werden automatisch angezeigt –
  nicht erneut als hud-Ereignis eintragen).
- hud-Ereignisse nur mit Schlüsseln aus der Story-Bibel; jede Änderung muss vom aktuellen Stand aus möglich sein
  (keine negativen Werte, Prozent 0–100). Inventar: items: ["+Name"] / ["-Name"].
- Genau drei Optionen 1/2/3 mit kurzen Texten und rechnerisch möglichen Effekten, plus `standard`.
- Kein Text im Bild, keine echten Marken oder Personen."""


def build_prompt(story: dict, state: dict) -> str:
    teil = state["naechster_teil"]
    beispiel = (STORIES / "die-letzten-10000" / "teil-01.yaml").read_text(encoding="utf-8")
    prev = load_episode(story["slug"], teil - 1) if teil > 1 else None
    return "\n\n".join([
        "## Story-Bibel\n" + yaml.safe_dump(story, allow_unicode=True, sort_keys=False),
        "## Aktueller Stand (vor dieser Folge)\n" + json.dumps(state, ensure_ascii=False, indent=1),
        "## Vorherige Folge\n" + (yaml.safe_dump(prev, allow_unicode=True, sort_keys=False) if prev else "(keine)"),
        "## Beispiel-Folge (Schema)\n" + beispiel,
        f"## Auftrag\nSchreibe Teil {teil} von {story['teile']} (Handlung: {story['handlung'].get(teil, '')})."
        + (" Dies ist das FINALE: Geschichte abschließen; Entscheidung = welche neue Geschichte als Nächstes."
           if teil == story["teile"] else ""),
    ])


def max_cost_eur() -> float:
    """Höchstmögliche Kosten eines Drehbuch-Aufrufs (inkl. USt., ungünstiger Kurs) – wird vorab reserviert."""
    b = budget()
    a = b["anthropic"]
    usd = a["max_input_tokens"] / 1e6 * a["usd_input_mtok"] + a["max_output_tokens"] / 1e6 * a["usd_output_mtok"]
    return round(usd * float(b["eur_per_usd"]) * (1 + float(b["vat_rate"])), 4)


def cost_eur(usage: dict) -> float:
    b = budget()
    a = b["anthropic"]
    usd = (usage.get("input_tokens", 0) / 1e6 * a["usd_input_mtok"]
           + usage.get("output_tokens", 0) / 1e6 * a["usd_output_mtok"])
    return round(usd * float(b["eur_per_usd"]) * (1 + float(b["vat_rate"])), 4)


def generate(story: dict, state: dict, api_key: str | None = None) -> dict:
    """Ein einziger Aufruf, keine Wiederholung. Rückgabe {pfad, usage, eur}."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY fehlt")
    a = budget()["anthropic"]
    prompt = build_prompt(story, state)
    if (len(prompt) + len(SYSTEM)) / 3.0 > a["max_input_tokens"]:   # konservativ: 3 Zeichen je Token
        raise SystemExit("Drehbuch-Anfrage wäre größer als die reservierte Tokenmenge – Abbruch vor dem Senden.")
    body = {"model": a["modell"], "max_tokens": int(a["max_output_tokens"]),
            "system": SYSTEM, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    text = "".join(b.get("text", "") for b in data.get("content", []))
    text = text.strip().removeprefix("```yaml").removeprefix("```").removesuffix("```").strip()
    path = episode_path(story["slug"], state["naechster_teil"])
    path.write_text(text + "\n", encoding="utf-8")
    usage = data.get("usage", {})
    print(f"Drehbuch geschrieben: {path.name} (Tokens ein/aus: {usage.get('input_tokens')}/{usage.get('output_tokens')})")
    return {"pfad": str(path), "usage": usage, "eur": cost_eur(usage)}
