"""Bildaufträge für Weg 1 und ihre Kosten – rein rechnerisch, ohne API-Aufruf.

* Referenzblätter (Figuren, Orte) entstehen einmal je Geschichte und liegen danach unter
  assets/illu/<slug>/ref_<tag>.png – jede weitere Folge nutzt sie kostenlos.
* Je Shot ein Bild (gen4_image, 1080:1920) mit bis zu drei Referenzen: Ort + bis zu zwei Figuren.
  Fertige Bilder liegen unter assets/illu/<slug>/<hash>.png und werden nie zweimal bezahlt.
"""
from __future__ import annotations

import hashlib
import json
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from illu.storyboard import stil

ROOT = Path(__file__).resolve().parent.parent
ARCHIV = ROOT / "assets" / "illu"


def _clean(t: str) -> str:
    return " ".join(str(t).split())


def _seed(key: str) -> int:
    return zlib.crc32(key.encode()) % 4294967295


@dataclass
class Auftrag:
    id: str
    prompt: str
    refs: list[str] = field(default_factory=list)      # Auftrags-IDs der Referenzbilder (Tag = ID ohne REF_)
    seed: int = 0
    datei: Path | None = None
    fest: bool = False                                  # freigegebene Referenz (referenzen.yaml) – nie neu erzeugt

    def schluessel(self, modell: str, ref_dateien: list[str] | None = None) -> str:
        teile = [modell, self.prompt, self.refs, self.seed] + ([ref_dateien] if ref_dateien else [])
        return hashlib.sha256(json.dumps(teile).encode()).hexdigest()[:20]


TAG = re.compile(r"^[a-z][a-z0-9_]{2,15}$")       # Runway: 3–16 Zeichen, ^[a-z][a-z0-9_]+$
FELDER = ("alter", "gesicht", "frisur", "haarfarbe", "haut", "kleidung", "koerper", "kurz")


def figur_text(fig: dict, kurz: bool = False) -> str:
    """Verbindliche Charakterbeschreibung aus story.yaml › figuren › merkmale."""
    m = fig["merkmale"]
    if kurz:   # für Shots: Alter, Haare, Haut, Kleidung in einer Zeile (Prompt-Grenze 1000 Zeichen)
        return m["kurz"]
    en = ("age", "face", "hairstyle", "hair colour", "skin", "clothes", "body")
    return "; ".join(f"{e}: {m[k]}" for e, k in zip(en, FELDER))


def aktuell(pfad: Path) -> Path:
    """Retuschierte Fassung (illu/retusche.py) hat Vorrang vor dem Original."""
    r = pfad.with_suffix(".ret.png")
    return r if r.exists() else pfad


def freigegebene_referenzen(slug: str) -> dict[str, Path]:
    """stories/<slug>/referenzen.yaml: Tag → freigegebene Datei. Nur diese dürfen in Shots verwendet werden."""
    p = ROOT / "stories" / slug / "referenzen.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {k: ARCHIV / slug / v for k, v in (d or {}).items()}


def _ref(tag: str, prompt: str, refs: list[str], seed: int, ordner: Path, fest: dict[str, Path], modell: str):
    if tag in fest:
        return Auftrag(f"REF_{tag}", prompt, refs=refs, seed=seed, datei=fest[tag], fest=True)
    a = Auftrag(f"REF_{tag}", prompt, refs=refs, seed=seed)
    a.datei = ordner / f"ref_{tag}_{a.schluessel(modell)[:10]}.png"     # neuer Prompt → neue Datei, alte bleibt
    return a


def auftraege(story: dict, sb: dict, st: dict | None = None) -> list[Auftrag]:
    st = st or stil()
    slug = story["slug"]
    ordner = ARCHIV / slug
    benutzt_f = list(dict.fromkeys(f for s in sb["shots"] for f in s.get("figuren") or []))
    benutzt_o = list(dict.fromkeys(s["ort"] for s in sb["shots"]))
    anker = ROOT / st["stil_anker"].format(slug=slug) if st.get("stil_anker") else None
    hat_anker = bool(anker and anker.exists())
    atag = st.get("stil_anker_tag", "stilbild")
    fest = freigegebene_referenzen(slug)
    modell = st["bildmodell"]
    stilsatz = f"Draw in exactly the art style of @{atag} (style only, ignore its content). " if hat_anker else ""
    out: list[Auftrag] = []
    for tag in benutzt_f:
        fig = story["figuren"][tag]
        out.append(_ref(tag, _clean(f"{st['stil_vorne']} {stilsatz}{st['figur_blatt']} {fig['name']}: "
                                    f"{figur_text(fig)}."), [f"REF_{atag}"] if hat_anker else [],
                        _seed(f"{slug}-illu2-{tag}"), ordner, fest, modell))
    for tag in benutzt_o:
        out.append(_ref(tag, _clean(f"{st['stil_vorne']} {stilsatz}{st['ort_blatt']} "
                                    f"{story['orte'][tag]['reference_prompt']} {st['stil_hinten']}"),
                        [f"REF_{atag}"] if hat_anker else [], _seed(f"{slug}-illu2-{tag}"), ordner, fest, modell))
    for s in sb["shots"]:
        if s.get("bild_von"):
            continue
        figs = s.get("figuren") or []
        refs = [f"REF_{s['ort']}"] + [f"REF_{f}" for f in figs]
        namen = " ".join(f"@{f} is {story['figuren'][f]['name']} ({figur_text(story['figuren'][f], kurz=True)})."
                         for f in figs)
        stilsatz = ""
        if hat_anker and len(refs) < st["max_referenzen"]:
            refs.append(f"REF_{atag}")
            stilsatz = f"Art style exactly like @{atag} (style only, not its content). "
        prompt = _clean(f"{st['stil_vorne']} {stilsatz}Setting: @{s['ort']}. "
                        f"{namen if namen else 'No characters.'} {s['bild']}. {st['stil_hinten']}")
        a = Auftrag(f"IMG_{s['id']}", prompt, refs=refs, seed=_seed(f"{slug}-{sb['teil']}-{s['id']}"))
        by = {x.id: x.datei.name for x in out}
        by[f"REF_{atag}"] = anker.name if hat_anker else ""
        a.datei = ordner / f"{a.schluessel(modell, [by.get(r, r) for r in refs])}.png"   # neue Referenz → neues Bild
        out.append(a)
    if hat_anker:
        out.insert(0, Auftrag(f"REF_{atag}", "(eigener Stilanker, wird nicht erzeugt)", datei=anker, fest=True))
    return out


def pruefe_auftraege(auftr: list[Auftrag], st: dict | None = None) -> list[str]:
    """Kostenlos: Werden die Referenzbilder wirklich als Eingabebilder übergeben und im Prompt angesprochen?"""
    st = st or stil()
    f: list[str] = []
    ids = {a.id for a in auftr}
    for a in auftr:
        if len(a.prompt) > st["max_prompt_zeichen"]:
            f.append(f"{a.id}: Prompt {len(a.prompt)} > {st['max_prompt_zeichen']} Zeichen")
        if len(a.refs) > st["max_referenzen"]:
            f.append(f"{a.id}: {len(a.refs)} Referenzen > {st['max_referenzen']}")
        for r in a.refs:
            tag = r[4:]
            if not TAG.match(tag):
                f.append(f"{a.id}: Tag {tag} ungültig (3–16 Zeichen, a–z, 0–9, _)")
            if r not in ids:
                f.append(f"{a.id}: Referenz {r} hat keinen Auftrag/keine Datei")
            if f"@{tag}" not in a.prompt:
                f.append(f"{a.id}: Referenz @{tag} wird im Prompt nicht angesprochen")
        if a.id.startswith("IMG_") and not a.refs:
            f.append(f"{a.id}: keine Referenzbilder")
    return f


def bild_fuer(sb: dict, auftr: list[Auftrag]) -> dict[str, Path]:
    """Shot-ID → Bilddatei (auch für bild_von)."""
    by = {a.id: a.datei for a in auftr}
    out: dict[str, Path] = {}
    for s in sb["shots"]:
        out[s["id"]] = out[s["bild_von"]] if s.get("bild_von") else aktuell(by[f"IMG_{s['id']}"])
    return out


def kosten(auftr: list[Auftrag], st: dict | None = None, nur_offene: bool = True) -> dict:
    """Credits/€ nach config/pricing.yaml und config/budget.yaml (USt + Sicherheitsaufschlag wie die Kasse)."""
    st = st or stil()
    preise = yaml.safe_load((ROOT / "config" / "pricing.yaml").read_text(encoding="utf-8"))
    b = yaml.safe_load((ROOT / "config" / "budget.yaml").read_text(encoding="utf-8"))
    m = preise["image"][st["bildmodell"]]
    if not m.get("verified"):
        raise ValueError(f"Preis für {st['bildmodell']} nicht bestätigt")
    offen = [a for a in auftr if not a.fest and not (nur_offene and a.datei and a.datei.exists())]
    credits = len(offen) * int(m["credits_per_image"])
    eur = credits * float(preise["usd_per_credit"]) * float(b["eur_per_usd"]) * (1 + float(b["vat_rate"]))
    return {"bilder": len(offen), "referenzen": sum(a.id.startswith("REF_") for a in offen),
            "shots": sum(a.id.startswith("IMG_") for a in offen), "credits": credits,
            "eur": round(eur, 2), "eur_reserve": round(eur * (1 + float(b["safety_margin"])), 2)}
