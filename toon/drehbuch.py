"""Drehbuch-KI für Storyboard v3 (2D-Rig). Ein Claude-Aufruf je Folge, keine Wiederholung, Kosten über die Kasse.

Claude schreibt nur noch Handlung und Regie (Orte, Positionen, Gänge, Haltungen, Ausdrücke, Übergaben, Dialog) –
keine Bild-Prompts. Das Ergebnis wird kostenlos geprüft (Logik, Länge); ungültig = Abbruch vor Stimmkosten.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

import yaml

from toon import orte as ORTMOD
from toon.anim import EINZEL, HALTUNGEN
from toon.figur import AUSDRUCK
from toon.szene import KAMERA, REQUISITEN

ROOT = Path(__file__).resolve().parent.parent


def pfad(slug: str, teil: int) -> Path:
    return ROOT / "stories" / slug / "toon" / f"teil-{teil:02d}.yaml"


def system_prompt(story: dict) -> str:
    orte = {k: {"sitze": ORTMOD.lade(k).get("sitze", {})} for k in story["orte"] if k in ORTMOD.ORTE}
    return f"""Du bist Autor:in und Regie einer deutschen 2D-Cartoon-Serie (Hochformat, 60–90 Sekunden je Folge).
Antworte NUR mit gültigem YAML im Format der Beispiel-Folge (Storyboard v3). Verbindliche Regeln:
- 3–7 Einstellungen; je Einstellung: nr, ort, tageszeit, kamera, uebergang, fokus, figuren, ablauf.
- Orte (mit Sitzplätzen): {json.dumps(orte, ensure_ascii=False)}. Figuren-Schlüssel: {list(story['figuren'])}.
- kamera ∈ {list(KAMERA)} (feste Einstellung, keine Kamerafahrt); nah/gross nur mit genau einer Figur im fokus.
- uebergang ∈ schnitt, anschluss, ueberblendung, abblende; erste Einstellung abblende; Ortswechsel mit ueberblendung.
  Keine zwei aufeinanderfolgenden Einstellungen mit gleicher Kamera und gleichem Fokus.
- Startposition x (0–1440) NUR beim ersten Auftritt bzw. nach Ortswechsel; Figuren stehen ≥ 220 auseinander.
  Später ändern Figuren ihren Platz NUR durch geht_nach/geht_zu/geht_ab; „auftritt: rechts/links“ für Ankünfte.
- Beat-Felder: figur, sagt | erzaehler, haltung {list(HALTUNGEN)}, ausdruck {list(AUSDRUCK)}, aktion {list(EINZEL)},
  geht_nach, geht_zu, geht_ab, dreht, setzt_sich (nur vorhandene Sitze), steht_auf, nimmt/legt_ab/gibt
  (Requisiten {sorted(REQUISITEN)}; nur geben, was die Figur hält, Abstand ≤ 320), sfx, hud, pause, warte, parallel.
- Jede Handlung folgt sichtbar aus der vorigen (Ursache → Wirkung). Kurze, natürliche Sätze (≤ 90 Zeichen),
  echte Dialoge mit Reaktionen (Ausdruck, Aktion, Pause). Erzähler sparsam.
- Statusänderungen nur mit Schlüsseln aus der Story-Bibel (hud: {{key, zu|delta}}), rechnerisch möglich.
- Ende: Cliffhanger; Block `entscheidung` mit frage, optionen 1/2/3 (text, effekte) und standard.
- Die Folge setzt GENAU die gewählte Option der letzten Folge fort."""


def generieren(story: dict, state: dict, beispiel: Path) -> dict:
    """Ruft Claude auf (kostenpflichtig, ≈ 0,10 €). Aufrufer muss vorher über die Kasse reservieren."""
    from csu.common import budget
    from csu.script import cost_eur
    a = budget()["anthropic"]
    teil = state["naechster_teil"]
    vorher = pfad(story["slug"], teil - 1)
    user = "\n\n".join([
        "## Story-Bibel\n" + yaml.safe_dump(story, allow_unicode=True, sort_keys=False),
        "## Stand vor dieser Folge\n" + json.dumps(state, ensure_ascii=False),
        "## Vorige Folge\n" + (vorher.read_text(encoding="utf-8") if vorher.exists() else "(keine)"),
        "## Beispiel (Format)\n" + beispiel.read_text(encoding="utf-8"),
        f"## Auftrag\nSchreibe Teil {teil} von {story['teile']} ({story['handlung'].get(teil, '')})."])
    body = {"model": a["modell"], "max_tokens": int(a["max_output_tokens"]), "system": system_prompt(story),
            "messages": [{"role": "user", "content": user}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                          "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    text = "".join(b.get("text", "") for b in data.get("content", [])).strip()
    text = text.removeprefix("```yaml").removeprefix("```").removesuffix("```").strip()
    ziel = pfad(story["slug"], teil)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(text + "\n", encoding="utf-8")
    return {"pfad": str(ziel), "eur": cost_eur(data.get("usage", {})), "usage": data.get("usage", {})}
