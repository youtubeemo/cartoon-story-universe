"""Qualitätskontrolle der Weg-1-Bilder. Kein Bild gelangt ohne Status „ok“ oder „manuell_ok“ in eine Folge.

Stufen:
1. Lokal (kostenlos, immer): Format 1080×1920, lesbar, kein Beinahe-Duplikat eines anderen Shots.
2. Prüfbogen (kostenlos): Shot neben den Referenzbildern seiner Figuren + Merkmal-Checkliste – für Menschen und KI.
3. KI-Prüfung (kostenpflichtig, ≈ 0,016 € je Bild, nur im freigegebenen Bilder-Lauf): Claude vergleicht den Shot
   mit den Referenzen und der Charakterbibel – Alter, Gesicht, Frisur, Haarfarbe, Haut, Kleidung, Proportionen,
   Schrift im Bild, Gesichter auf Essen, fremde Figuren, 2D-Stil. Ein einziges „nein“ → Status „fehler“.
4. Manuelles Urteil (`python -m illu urteil …`) kann jedes Ergebnis überstimmen und wird protokolliert.

Grenzen: Lokale Farb- oder Texterkennung war im Test unzuverlässig (Tesseract fand in gemalten Bildern fast nur
Fehlalarme, Farbanteile unterscheiden Figuren nicht) und wird deshalb bewusst NICHT als Prüfung verwendet.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import io
import json
import os
import urllib.request
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

from illu import plan as bplan

ROOT = Path(__file__).resolve().parent.parent
OK = ("ok", "manuell_ok")
PRUEFPUNKTE_FIGUR = ("alter", "gesicht", "frisur", "haarfarbe", "haut", "kleidung", "proportionen")
PRUEFPUNKTE_BILD = ("kein_text", "keine_gesichter_auf_essen", "keine_fremden_figuren", "stil_2d", "passt_zur_handlung")


# ------------------------------------------------------------------ Status
def _pfad(slug: str) -> Path:
    return bplan.ARCHIV / slug / "qc.json"


def sha256(datei: Path) -> str:
    return hashlib.sha256(Path(datei).read_bytes()).hexdigest()


def laden(slug: str) -> dict:
    p = _pfad(slug)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def setzen(slug: str, datei: Path, status: str, gruende: list[str], quelle: str) -> None:
    """Jedes Urteil wird an die exakte Datei (SHA-256) gebunden und im Verlauf protokolliert – nie überschrieben."""
    datei = Path(datei)
    d = laden(slug)
    alt = d.get(datei.name) or {}
    eintrag = {"status": status, "gruende": gruende, "quelle": quelle,
               "zeit": dt.datetime.now().isoformat(timespec="seconds"), "sha256": sha256(datei)}
    eintrag["verlauf"] = (alt.get("verlauf") or []) + [{k: eintrag[k] for k in ("status", "gruende", "quelle", "zeit")}]
    d[datei.name] = eintrag
    p = _pfad(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def status(slug: str, datei: Path) -> dict:
    datei = Path(datei)
    eintrag = laden(slug).get(datei.name)
    if not eintrag:
        return {"status": "ungeprueft", "gruende": []}
    if not datei.exists() or eintrag.get("sha256") != sha256(datei):
        return {"status": "ungeprueft", "gruende": ["Datei seit dem Urteil verändert oder ohne Prüfsumme"]}
    return eintrag


def sperren_fehlende(story: dict, sb: dict, bilder: dict[str, Path]) -> list[str]:
    """Shots, deren Bild NICHT freigegeben ist (für `folge`: dann kein Schnitt)."""
    return [f"{sid}: {Path(p).name} → {status(story['slug'], p)['status']}"
            for sid, p in bilder.items() if status(story["slug"], p)["status"] not in OK]


# ------------------------------------------------------------------ 1. lokal
def _dhash(p: Path) -> int:
    im = Image.open(p).convert("L").resize((9, 16))
    bits = "".join("1" if im.getpixel((x, y)) > im.getpixel((x + 1, y)) else "0" for y in range(16) for x in range(8))
    return int(bits, 2)


def lokal(bilder: dict[str, Path]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    hashes: dict[str, int] = {}
    for sid, p in bilder.items():
        f: list[str] = []
        try:
            with Image.open(p) as im:
                if im.size != (1080, 1920):
                    f.append(f"Format {im.size[0]}×{im.size[1]} statt 1080×1920")
        except OSError as exc:
            out[sid] = [f"nicht lesbar: {exc}"]
            continue
        h = _dhash(p)
        for andere, h2 in hashes.items():
            if bilder[andere] != p and bin(h ^ h2).count("1") <= 6:
                f.append(f"fast identisch mit {andere}")
        hashes[sid] = h
        out[sid] = f
    return out


# ------------------------------------------------------------------ 2. Prüfbogen
def _font(n: int):
    return ImageFont.truetype(str(ROOT / "assets/fonts/Baloo2.ttf"), n)


def pruefbogen(story: dict, shot: dict, datei: Path, refs: dict[str, Path], ziel: Path) -> Path:
    figs = shot.get("figuren") or []
    kacheln = [("SHOT " + shot["id"], Path(datei))] + [(f"REFERENZ {f}", refs[f]) for f in figs
                                                        if f in refs and Path(refs[f]).exists()]
    b = 420
    bogen = Image.new("RGB", (b * len(kacheln), int(b * 16 / 9) + 40 + 320), "white")
    d = ImageDraw.Draw(bogen)
    for i, (titel, p) in enumerate(kacheln):
        bogen.paste(Image.open(p).convert("RGB").resize((b, int(b * 16 / 9))), (i * b, 40))
        d.text((i * b + 8, 6), titel, fill="black", font=_font(24))
    y = int(b * 16 / 9) + 50
    for f in figs:
        d.text((8, y), f"{story['figuren'][f]['name']}: {story['figuren'][f]['merkmale']['kurz']}"[:150],
               fill="black", font=_font(18))
        y += 28
    ziel.parent.mkdir(parents=True, exist_ok=True)
    bogen.save(ziel, quality=88)
    return ziel


# ------------------------------------------------------------------ 3. KI-Prüfung (kostenpflichtig)
def _b64(p: Path, kante: int = 768) -> str:
    im = Image.open(p).convert("RGB")
    im.thumbnail((kante, kante))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


KI_MAX_OUT = 600          # Antwort-Tokens je Aufruf (hart, max_tokens)
KI_TEXT_IN = 2500         # Obergrenze Text-Tokens je Aufruf
KI_BILD_IN = 1600         # Obergrenze je Bild (auf 768 px verkleinert ≈ 450 Tokens – großzügig gerechnet)


def _preise() -> tuple[float, float, float]:
    b = yaml.safe_load((ROOT / "config" / "budget.yaml").read_text(encoding="utf-8"))
    a = b["anthropic"]
    f = float(b["eur_per_usd"]) * (1 + float(b["vat_rate"]))
    return float(a["usd_input_mtok"]) * f / 1e6, float(a["usd_output_mtok"]) * f / 1e6, f


def ki_obergrenze_eur(bilder_im_aufruf: int) -> float:
    """Höchstmögliche Kosten EINES Prüfaufrufs (Eingabe gedeckelt durch Bildgröße/Text, Ausgabe durch max_tokens)."""
    pin, pout, _ = _preise()
    return round((KI_TEXT_IN + bilder_im_aufruf * KI_BILD_IN) * pin + KI_MAX_OUT * pout, 4)


def ki_kosten_eur(anzahl_bilder: int, refs_je_bild: int = 2) -> float:
    return round(anzahl_bilder * ki_obergrenze_eur(1 + refs_je_bild), 3)


class KIBudget:
    """Harte Grenze für die KI-Bildprüfung: vor jedem Aufruf wird die Obergrenze vorgemerkt; reicht sie nicht,
    wird NICHT geprüft (Bild bleibt gesperrt). Nach dem Aufruf zählen die echten Tokens; bei Fehlern die Obergrenze."""

    def __init__(self, limit_eur: float):
        self.limit, self.ausgegeben, self.tokens_in, self.tokens_out = max(0.0, float(limit_eur)), 0.0, 0, 0

    def reicht(self, bilder_im_aufruf: int) -> bool:
        return self.ausgegeben + ki_obergrenze_eur(bilder_im_aufruf) <= self.limit + 1e-9

    def buchen(self, usage: dict | None, bilder_im_aufruf: int) -> None:
        pin, pout, _ = _preise()
        if usage and "input_tokens" in usage:
            ti, to = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
            self.tokens_in, self.tokens_out = self.tokens_in + ti, self.tokens_out + to
            self.ausgegeben += ti * pin + to * pout
        else:                                   # Ausgang unklar → schlimmster Fall
            self.ausgegeben += ki_obergrenze_eur(bilder_im_aufruf)


def ki_pruefen(story: dict, shot: dict, datei: Path, refs: dict[str, Path],
               budget: KIBudget) -> tuple[bool | None, list[str]]:
    """EIN Aufruf je Bild – nur wenn das KI-Budget die Obergrenze des Aufrufs noch deckt.
    Rückgabe ok=True/False (geprüft) oder None (nicht geprüft → Bild bleibt gesperrt)."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None, ["KI-Prüfung nicht möglich (kein Schlüssel) – manuelles Urteil nötig"]
    n_bilder = 1 + sum(1 for f in shot.get("figuren") or [] if f in refs)
    if not budget.reicht(n_bilder):
        return None, ["KI-Prüfung übersprungen: freigegebenes Kostenlimit erreicht – manuelles Urteil nötig"]
    b = yaml.safe_load((ROOT / "config" / "budget.yaml").read_text(encoding="utf-8"))["anthropic"]
    figs = shot.get("figuren") or []
    inhalt: list[dict] = [{"type": "text", "text": f"Bild 1 = Shot {shot['id']}."}, _bild(datei)]
    bibel = {}
    for i, f in enumerate(f for f in figs if f in refs):
        inhalt += [{"type": "text", "text": f"Bild {i + 2} = freigegebene Referenz für {f}."}, _bild(refs[f])]
    for f in figs:
        bibel[f] = story["figuren"][f]["merkmale"]
    schema = {"figuren": {f: {k: True for k in PRUEFPUNKTE_FIGUR} | {"bemerkung": ""} for f in figs},
              **{k: True for k in PRUEFPUNKTE_BILD}, "bemerkung": ""}
    inhalt.append({"type": "text", "text": (
        "Du bist strenge Qualitätsprüfung einer 2D-Cartoon-Serie. Vergleiche Bild 1 mit den Referenzen und der "
        f"verbindlichen Charakterbibel {json.dumps(bibel, ensure_ascii=False)}. Geplanter Bildinhalt: "
        f"{shot.get('bild', '')!r}. Erwartete Figuren: {figs or 'keine'}. Setze einen Punkt nur dann auf true, wenn "
        "er eindeutig erfüllt ist: gleiches Alter (kein Kind statt Erwachsenem), gleiche Gesichtszüge, Frisur, "
        "Haarfarbe, Hautfarbe, Kleidung und Körperproportionen; kein_text = keinerlei Buchstaben/Fantasieschrift; "
        "keine_gesichter_auf_essen; keine_fremden_figuren = keine zusätzlichen Personen/Tiere; stil_2d = flacher "
        "2D-Cartoon mit Konturen, kein 3D-Render. Antworte NUR mit JSON nach diesem Schema: "
        + json.dumps(schema, ensure_ascii=False))})
    body = {"model": b["modell"], "max_tokens": KI_MAX_OUT, "messages": [{"role": "user", "content": inhalt}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
    except Exception as exc:                    # keine Wiederholung; Kosten im schlimmsten Fall verbucht
        budget.buchen(None, n_bilder)
        return None, [f"KI-Prüfung fehlgeschlagen ({type(exc).__name__}) – manuelles Urteil nötig"]
    budget.buchen(data.get("usage"), n_bilder)
    raw = "".join(x.get("text", "") for x in data.get("content", []))
    try:
        res = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except json.JSONDecodeError:
        return None, ["KI-Antwort nicht lesbar – manuelles Urteil nötig"]
    return auswerten(res, figs)


def _bild(p: Path) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(Path(p))}}


def auswerten(res: dict, figs: list[str]) -> tuple[bool, list[str]]:
    """Fehlende Punkte zählen als „nein“ – im Zweifel wird das Bild gesperrt."""
    gruende: list[str] = []
    for f in figs:
        r = (res.get("figuren") or {}).get(f) or {}
        for k in PRUEFPUNKTE_FIGUR:
            if r.get(k) is not True:
                gruende.append(f"{f}: {k} weicht ab" + (f" ({r.get('bemerkung')})" if r.get("bemerkung") else ""))
    for k in PRUEFPUNKTE_BILD:
        if res.get(k) is not True:
            gruende.append(f"Bild: {k} nicht erfüllt")
    if res.get("bemerkung") and gruende:
        gruende.append(str(res["bemerkung"]))
    return not gruende, gruende
