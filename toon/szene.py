"""Storyboard → durchgehende Zeitleiste (alle Einstellungen teilen EINE Handlung).

Format (siehe probe/animationsprobe.yaml):
  einstellungen: nummerierte Einstellungen mit Ort, Tageszeit, Kamera (feste Einstellungsgröße, keine Fahrt),
  Figuren mit Position, Übergang und einem Ablauf aus Beats. Beats laufen nacheinander; Sprechzeilen dauern so
  lange wie ihre Tonaufnahme. Haltung und Ausdruck jeder Figur bleiben über Einstellungsgrenzen erhalten –
  dadurch schließen Szenen logisch aneinander an.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from toon.anim import EINZEL, HALTUNGEN, Spur
from toon.figur import AUSDRUCK
from toon.geo import M
from toon.orte import BODEN_Y, BUEHNE_B, BUEHNE_H, ORTE

ROOT = Path(__file__).resolve().parent
KAMERA = {"totale": (1440, None), "halbtotale": (1080, None), "halbnah": (780, -470), "nah": (560, -560),
          "gross": (400, -640)}
UEBERGAENGE = ("schnitt", "anschluss", "ueberblendung", "abblende")
GAP = 0.22


@dataclass
class Einstellung:
    nr: int
    ort: str
    tageszeit: str
    kamera: str
    figuren: dict
    fokus: list
    uebergang: str
    start: float = 0.0
    ende: float = 0.0
    blick: dict = field(default_factory=dict)

    def view(self, ss: int = 2, W: int = 1080, H: int = 1920):
        w, dy = KAMERA[self.kamera]
        h = w * H / W
        xs = [self.figuren[f]["x"] for f in self.fokus] or [BUEHNE_B / 2]
        cx = sum(xs) / len(xs)
        if dy is None:
            # Füße bei ≈ 72 % der Bildhöhe → darunter freier Boden für Untertitel (über der TikTok-Leiste)
            y0 = BUEHNE_H - h if self.kamera == "totale" else BODEN_Y - 0.72 * h
        else:
            y0 = BODEN_Y + dy - h / 2
        x0 = min(max(0, cx - w / 2), BUEHNE_B - w)
        y0 = min(max(0, y0), BUEHNE_H - h)
        return M(0, 0, 0, ss * W / w, ss * H / h) @ M(-x0, -y0)


def lade_figuren(namen) -> dict:
    return {n: yaml.safe_load((ROOT / "figuren" / f"{n}.yaml").read_text(encoding="utf-8")) for n in namen}


def pruefen(sb: dict) -> list[str]:
    """Logikprüfung des Storyboards (kostenlos)."""
    errs, prev = [], None
    alle = set()
    for e in sb["einstellungen"]:
        alle |= set(e.get("figuren", {}))
    try:
        lade_figuren(alle)
    except FileNotFoundError as exc:
        errs.append(f"Figur fehlt: {exc}")
    for i, e in enumerate(sb["einstellungen"], 1):
        n = f"Einstellung {e.get('nr')}"
        if e.get("nr") != i:
            errs.append(f"{n}: Nummerierung lückenhaft")
        if e.get("ort") not in ORTE:
            errs.append(f"{n}: Ort {e.get('ort')} unbekannt")
        if e.get("kamera") not in KAMERA:
            errs.append(f"{n}: Kamera {e.get('kamera')} unbekannt ({', '.join(KAMERA)})")
        ue = e.get("uebergang", "schnitt")
        if ue not in UEBERGAENGE:
            errs.append(f"{n}: Übergang {ue} unbekannt")
        figs = set(e.get("figuren", {}))
        if prev is not None:
            if ue == "anschluss" and (e["ort"] != prev["ort"] or figs != set(prev.get("figuren", {}))):
                errs.append(f"{n}: Anschluss nur bei gleichem Ort und gleichen Figuren")
            if e["ort"] == prev["ort"] and figs == set(prev.get("figuren", {})) and e["kamera"] == prev["kamera"] \
                    and ue == "schnitt":
                errs.append(f"{n}: Sprung-Schnitt (gleiche Einstellung) – 'anschluss' oder andere Kamera")
            if e["ort"] == prev["ort"]:
                for f in figs & set(prev.get("figuren", {})):
                    if abs(e["figuren"][f]["x"] - prev["figuren"][f]["x"]) > 5 and not any(
                            b.get("figur") == f and b.get("geht_nach") for b in prev.get("ablauf", [])):
                        errs.append(f"{n}: {f} springt ohne Gang an eine andere Stelle")
        for b in e.get("ablauf", []):
            f = b.get("figur")
            if f and f not in figs:
                errs.append(f"{n}: {f} handelt, ist aber nicht im Bild")
            if b.get("haltung") and b["haltung"] not in HALTUNGEN:
                errs.append(f"{n}: Haltung {b['haltung']} unbekannt")
            if b.get("ausdruck") and b["ausdruck"] not in AUSDRUCK:
                errs.append(f"{n}: Ausdruck {b['ausdruck']} unbekannt")
            if b.get("aktion") and b["aktion"] not in EINZEL:
                errs.append(f"{n}: Aktion {b['aktion']} unbekannt")
        if e.get("kamera") in ("nah", "gross") and len(e.get("fokus", list(figs))) != 1:
            errs.append(f"{n}: nah/gross braucht genau eine Figur im Fokus")
        prev = e
    return errs


def zeitleiste(sb: dict, ton_fn) -> dict:
    """ton_fn(sprecher, text, schluessel) → (wav, dauer, mundformen). Gibt Einstellungen, Spuren, Ton, Untertitel."""
    alle = []
    for e in sb["einstellungen"]:
        for f in e.get("figuren", {}):
            if f not in alle:
                alle.append(f)
    spuren = {f: Spur(f, seed=zlib.crc32(f.encode()) % 1000) for f in alle}
    einst, stimmen, effekte, cues, hud = [], [], [], [], []
    t = 0.0
    for e in sb["einstellungen"]:
        ein = Einstellung(nr=e["nr"], ort=e["ort"], tageszeit=e.get("tageszeit", "tag"), kamera=e["kamera"],
                          figuren=e["figuren"], fokus=e.get("fokus", list(e["figuren"])),
                          uebergang=e.get("uebergang", "schnitt"), start=t, blick=e.get("blick", {}))
        cur = t + (0.5 if ein.uebergang in ("abblende", "ueberblendung") else 0.15)
        for k, b in enumerate(e.get("ablauf", [])):
            start = cur + float(b.get("warte", 0))
            f = b.get("figur")
            if b.get("haltung"):
                spuren[f].haltungen.append((start, b["haltung"]))
            if b.get("ausdruck"):
                spuren[f].ausdruecke.append((start, b["ausdruck"]))
            if b.get("aktion"):
                spuren[f].einzel.append((start, b["aktion"]))
            if b.get("sfx"):
                effekte.append((b["sfx"], start + float(b.get("sfx_versatz", 0))))
            if b.get("hud"):
                hud.append({**b["hud"], "t": start + 0.3})
            text, sprecher = (b.get("sagt"), f) if b.get("sagt") else (b.get("erzaehler"), None)
            dauer = 0.0
            if text:
                wav, dauer, formen = ton_fn(sprecher, text, f"E{e['nr']:02d}_B{k + 1:02d}")
                stimmen.append((wav, start))
                if sprecher:
                    spuren[sprecher].sprechen.append((start, start + dauer))
                    spuren[sprecher].mund += [(start + a, start + b_, s) for a, b_, s in formen]
                cues.append({"start": start, "dauer": dauer, "text": text, "erzaehler": sprecher is None})
            if b.get("parallel"):
                continue
            if text:
                cur = start + dauer + GAP
            elif b.get("aktion"):
                cur = start + max(float(b.get("pause", 0)), EINZEL[b["aktion"]] * 0.8)
            else:
                cur = start + float(b.get("pause", 0.35))
        t = cur + float(e.get("nachlauf", 0.45))
        ein.ende = t
        einst.append(ein)
    return {"einstellungen": einst, "spuren": spuren, "stimmen": stimmen, "effekte": effekte, "cues": cues,
            "hud": hud, "gesamt": round(t, 3), "figuren": lade_figuren(alle)}
