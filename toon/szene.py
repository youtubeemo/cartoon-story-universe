"""Storyboard v3 → eine durchgehende Zeitleiste. Alle Einstellungen teilen EINE Handlung:
Positionen, Haltungen, Ausdrücke, Requisiten und Sitzen bleiben über Schnitte erhalten.

Einstellung: nr, ort, tageszeit, kamera (feste Einstellungsgröße), fokus, uebergang, figuren (Startposition
nur beim ersten Auftritt bzw. Ortswechsel; „auftritt: rechts/links“ = kommt von außerhalb), ablauf (Beats).

Beat-Felder (beliebig kombinierbar):
  figur, sagt | erzaehler, haltung, ausdruck, aktion, geht_nach (x) | geht_zu (Figur) | geht_ab (links/rechts),
  dreht (links/rechts/vorne/halblinks/halbrechts/zu), setzt_sich (Sitz), steht_auf, nimmt (Requisit), legt_ab,
  gibt {an, requisit}, sfx, hud, pause, warte, parallel, erst_bewegen
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from toon import orte as ORTMOD
from toon.anim import EINZEL, HALTUNGEN, SCHRITT, TEMPO, Spur
from toon.figur import AUSDRUCK
from toon.geo import M
from toon.orte import BODEN_Y, BUEHNE_B, BUEHNE_H, ORTE

ROOT = Path(__file__).resolve().parent
KAMERA = {"totale": (1440, None), "halbtotale": (1080, None), "halbnah": (780, -470), "nah": (560, -560),
          "gross": (400, -640)}
UEBERGAENGE = ("schnitt", "anschluss", "ueberblendung", "abblende")
REQUISITEN = {"brief", "karte", "scheine", "tasse", "lupe", "taschenuhr", "pfanne", "fernrohr", "werkzeug",
              "kokosnuss", "kartenteil"}
DREH = {"links": -86.0, "rechts": 86.0, "vorne": 0.0, "halblinks": -35.0, "halbrechts": 35.0}
GAP, GAP_FRAGE = 0.3, 0.45


@dataclass
class Einstellung:
    nr: int
    ort: str
    tageszeit: str
    kamera: str
    figuren: list
    fokus: list
    uebergang: str
    start: float = 0.0
    ende: float = 0.0
    rahmen_x: tuple = (540.0, 540.0)

    def view(self, ss: int = 2, W: int = 1080, H: int = 1920):
        w, dy = KAMERA[self.kamera]
        h = w * H / W
        cx = sum(self.rahmen_x) / 2
        if dy is None:
            y0 = BUEHNE_H - h if self.kamera == "totale" else BODEN_Y - 0.72 * h
        else:
            y0 = BODEN_Y + dy - h / 2
        x0 = min(max(0, cx - w / 2), BUEHNE_B - w)
        y0 = min(max(0, y0), BUEHNE_H - h)
        return M(0, 0, 0, ss * W / w, ss * H / h) @ M(-x0, -y0)


def lade_figuren(namen) -> dict:
    return {n: yaml.safe_load((ROOT / "figuren" / f"{n}.yaml").read_text(encoding="utf-8")) for n in namen}


def _figuren_der_folge(sb):
    alle = []
    for e in sb["einstellungen"]:
        for f in e.get("figuren", {}):
            if f not in alle:
                alle.append(f)
    return alle


def _startx(spec: dict) -> float:
    return spec.get("x", -200 if spec.get("auftritt") == "links" else 1640)


# ------------------------------------------------------------------------- Logikprüfung
def pruefen(sb: dict) -> list[str]:
    errs = []
    try:
        lade_figuren(_figuren_der_folge(sb))
    except FileNotFoundError as exc:
        return [f"Figur fehlt: {exc}"]
    pos, halt, sitz, ort_vorher, prev = {}, {}, {}, None, None
    for i, e in enumerate(sb["einstellungen"], 1):
        n = f"Einstellung {e.get('nr')}"
        if e.get("nr") != i:
            errs.append(f"{n}: Nummerierung lückenhaft")
        ort = e.get("ort")
        if ort not in ORTE:
            errs.append(f"{n}: Ort {ort} unbekannt ({', '.join(ORTMOD.alle())})")
            continue
        sitze = ORTMOD.lade(ort).get("sitze", {})
        if e.get("kamera") not in KAMERA:
            errs.append(f"{n}: Kamera {e.get('kamera')} unbekannt")
        ue = e.get("uebergang", "schnitt")
        if ue not in UEBERGAENGE:
            errs.append(f"{n}: Übergang {ue} unbekannt")
        figs = list(e.get("figuren", {}))
        if ort != ort_vorher:
            pos, sitz = {}, {}
            if ue == "anschluss":
                errs.append(f"{n}: Anschluss bei Ortswechsel nicht möglich")
        elif prev and ue == "schnitt" and e.get("kamera") == prev.get("kamera") \
                and sorted(e.get("fokus", figs)) == sorted(prev.get("fokus", list(prev.get("figuren", {})))):
            errs.append(f"{n}: Sprung-Schnitt (gleiche Einstellung wie davor) – 'anschluss' oder andere Kamera")
        for f, spec in e.get("figuren", {}).items():
            spec = spec or {}
            if f in pos and "x" in spec and abs(spec["x"] - pos[f]) > 5:
                errs.append(f"{n}: {f} springt von x={pos[f]:.0f} nach x={spec['x']} ohne zu gehen")
            if f not in pos:
                if "x" not in spec and "auftritt" not in spec:
                    errs.append(f"{n}: {f} braucht beim ersten Auftritt x oder auftritt")
                pos[f] = _startx(spec)
                halt.setdefault(f, spec.get("requisit"))
                sitz[f] = bool(spec.get("sitzt"))
        if e.get("kamera") in ("nah", "gross") and len(e.get("fokus", figs)) != 1:
            errs.append(f"{n}: nah/gross braucht genau eine Figur im Fokus")
        for b in e.get("ablauf", []):
            f = b.get("figur")
            if f and f not in figs:
                errs.append(f"{n}: {f} handelt, ist aber nicht in der Einstellung")
                continue
            for key, menge in (("haltung", HALTUNGEN), ("ausdruck", AUSDRUCK), ("aktion", EINZEL)):
                if b.get(key) and b[key] not in menge:
                    errs.append(f"{n}: {key} „{b[key]}“ unbekannt")
            if b.get("sagt") and not f:
                errs.append(f"{n}: „sagt“ ohne Figur")
            bewegt = "geht_nach" in b or b.get("geht_zu") or b.get("geht_ab")
            if bewegt and sitz.get(f):
                errs.append(f"{n}: {f} geht los, sitzt aber noch")
            if "geht_nach" in b:
                pos[f] = float(b["geht_nach"])
            if b.get("geht_zu"):
                if b["geht_zu"] not in figs:
                    errs.append(f"{n}: geht_zu {b['geht_zu']} nicht in der Einstellung")
                else:
                    o = pos[b["geht_zu"]]
                    pos[f] = o + (-230 if pos[f] < o else 230)
            if b.get("geht_ab"):
                pos[f] = -260 if b["geht_ab"] == "links" else 1700
            if b.get("setzt_sich"):
                if b["setzt_sich"] not in sitze:
                    errs.append(f"{n}: Sitz „{b['setzt_sich']}“ gibt es in {ort} nicht ({', '.join(sitze) or 'keine'})")
                else:
                    pos[f], sitz[f] = float(sitze[b["setzt_sich"]]), True
            if b.get("steht_auf"):
                if not sitz.get(f):
                    errs.append(f"{n}: {f} steht auf, sitzt aber nicht")
                sitz[f] = False
            if b.get("nimmt"):
                if b["nimmt"] not in REQUISITEN:
                    errs.append(f"{n}: Requisit {b['nimmt']} unbekannt")
                halt[f] = b["nimmt"]
            if b.get("legt_ab"):
                halt[f] = None
            if b.get("gibt"):
                an, req = b["gibt"].get("an"), b["gibt"].get("requisit")
                if an not in figs:
                    errs.append(f"{n}: gibt an {an}, der ist nicht da")
                elif halt.get(f) != req:
                    errs.append(f"{n}: {f} gibt {req}, hält aber {halt.get(f)}")
                elif abs(pos[f] - pos[an]) > 320:
                    errs.append(f"{n}: {f} und {an} stehen zu weit auseinander für eine Übergabe")
                else:
                    halt[f], halt[an] = None, req
        ort_vorher, prev = ort, e
    return errs


# ------------------------------------------------------------------------- Zeitleiste
def zeitleiste(sb: dict, ton_fn) -> dict:
    """ton_fn(sprecher, text, schluessel) → (wav, dauer, mundformen)."""
    figuren = lade_figuren(_figuren_der_folge(sb))
    spuren: dict[str, Spur] = {}
    einst, stimmen, effekte, cues, hud = [], [], [], [], []
    t, ort_vorher = 0.0, None

    for e in sb["einstellungen"]:
        ort = e["ort"]
        sitze = ORTMOD.lade(ort).get("sitze", {})
        figs = list(e.get("figuren", {}))
        for f, spec in e.get("figuren", {}).items():
            spec = spec or {}
            if f not in spuren:
                spuren[f] = Spur(f, seed=zlib.crc32(f.encode()) % 1000, x0=_startx(spec))
                if spec.get("requisit"):
                    spuren[f].requisiten.append((0.0, spec["requisit"]))
                if spec.get("sitzt"):
                    spuren[f].sitzen.append([-1.0, None])
            elif ort != ort_vorher:
                spuren[f].gaenge.append((t, t + 1e-3, spuren[f].x(t), _startx(spec)))
            if spec.get("blick") in DREH:
                spuren[f].drehungen.append((t, DREH[spec["blick"]]))
        ein = Einstellung(nr=e["nr"], ort=ort, tageszeit=e.get("tageszeit", "tag"), kamera=e["kamera"], figuren=figs,
                          fokus=e.get("fokus", figs), uebergang=e.get("uebergang", "schnitt"), start=t)
        cur = t + (0.55 if ein.uebergang in ("abblende", "ueberblendung") else 0.2)

        for k, b in enumerate(e.get("ablauf", [])):
            start = cur + float(b.get("warte", 0))
            f = b.get("figur")
            sp = spuren.get(f)
            ende = start
            ziel = None
            if "geht_nach" in b:
                ziel = float(b["geht_nach"])
            elif b.get("geht_zu"):
                ox = spuren[b["geht_zu"]].x(start)
                ziel = ox + (-230 if sp.x(start) < ox else 230)
            elif b.get("geht_ab"):
                ziel = -260.0 if b["geht_ab"] == "links" else 1700.0
            elif b.get("setzt_sich") and abs(sp.x(start) - sitze[b["setzt_sich"]]) > 15:
                ziel = float(sitze[b["setzt_sich"]])
            if ziel is not None:
                x0 = sp.x(start)
                dauer = max(0.6, abs(ziel - x0) / TEMPO)
                sp.gaenge.append((start, start + dauer, x0, ziel))
                for s_ in range(1, int(abs(ziel - x0) // SCHRITT) + 1):
                    effekte.append(("schritt", start + dauer * s_ * SCHRITT / abs(ziel - x0)))
                ende = start + dauer
                if b.get("setzt_sich"):    # am Sitz umdrehen, dann setzen
                    sp.drehungen.append((ende, 30.0 if ziel < BUEHNE_B / 2 else -30.0))
                    ende += 0.3
            if b.get("setzt_sich"):
                sp.sitzen.append([ende, None])
                effekte.append(("stuhl", ende + 0.45))
                ende += 0.65
                sp.drehungen.append((ende, None))
            if b.get("steht_auf"):
                for s_ in reversed(sp.sitzen):
                    if s_[1] is None:
                        s_[1] = start
                        break
                ende = max(ende, start + 0.65)
            if b.get("dreht"):
                d = b["dreht"]
                sp.drehungen.append((start, DREH.get(d)))
                ende = max(ende, start + 0.35)
            nach = ende if ziel is not None else start
            if b.get("haltung"):
                sp.haltungen.append((nach, b["haltung"]))
            if b.get("ausdruck"):
                sp.ausdruecke.append((start, b["ausdruck"]))
            if b.get("aktion"):
                sp.einzel.append((nach, b["aktion"]))
            if b.get("nimmt"):
                sp.requisiten.append((start, b["nimmt"]))
            if b.get("legt_ab"):
                sp.requisiten.append((start, None))
            if b.get("gibt"):
                an = spuren[b["gibt"]["an"]]
                sp.reichen.append((start, start + 1.1))
                an.reichen.append((start + 0.25, start + 1.1))
                sp.requisiten.append((start + 0.62, None))
                an.requisiten.append((start + 0.62, b["gibt"]["requisit"]))
                effekte.append(("papier", start + 0.55))
                ende = max(ende, start + 1.15)
            if b.get("sfx"):
                effekte.append((b["sfx"], start + float(b.get("sfx_versatz", 0))))
            if b.get("hud"):
                hud.append({**b["hud"], "t": start + 0.3})

            text, sprecher = (b.get("sagt"), f) if b.get("sagt") else (b.get("erzaehler"), None)
            if text:
                tstart = (ende if b.get("erst_bewegen") else start) + (0.15 if sprecher is None else 0.0)
                wav, dauer, formen = ton_fn(sprecher, text, f"E{e['nr']:02d}_B{k + 1:02d}", b.get("ton") or b.get("ausdruck"))
                stimmen.append((wav, tstart))
                if sprecher:
                    spuren[sprecher].sprechen.append((tstart, tstart + dauer, text))
                    spuren[sprecher].mund += [(tstart + a, tstart + b_, s) for a, b_, s in formen]
                cues.append({"start": tstart, "dauer": dauer, "text": text, "erzaehler": sprecher is None})
                ende = max(ende, tstart + dauer + (GAP_FRAGE if text.rstrip().endswith("?") else GAP))
            if b.get("parallel"):
                continue
            if b.get("aktion") and not text:
                ende = max(ende, nach + EINZEL[b["aktion"]] * 0.85)
            cur = max(ende, start + float(b.get("pause", 0.0 if (text or ziel is not None or b.get("gibt")) else 0.4)))
        t = cur + float(e.get("nachlauf", 0.45))
        ein.ende = t
        xs = []
        for f in ein.fokus:
            for tt in (ein.start + 0.01, (ein.start + t) / 2, t - 0.01):
                x = spuren[f].x(tt)
                if -60 < x < BUEHNE_B + 60:
                    xs.append(x)
        ein.rahmen_x = (min(xs), max(xs)) if xs else (BUEHNE_B / 2, BUEHNE_B / 2)
        einst.append(ein)
        ort_vorher = ort
    return {"einstellungen": einst, "spuren": spuren, "stimmen": stimmen,
            "effekte": sorted(effekte, key=lambda x: x[1]), "cues": cues, "hud": hud, "gesamt": round(t, 3),
            "figuren": figuren}
