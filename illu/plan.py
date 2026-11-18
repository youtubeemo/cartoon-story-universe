"""Bildaufträge für Weg 1 und ihre Kosten – rein rechnerisch, ohne API-Aufruf.

* Referenzblätter (Figuren, Orte) entstehen einmal je Geschichte und liegen danach unter
  assets/illu/<slug>/ref_<tag>.png – jede weitere Folge nutzt sie kostenlos.
* Je Shot ein Bild (gen4_image, 1080:1920) mit bis zu drei Referenzen: Ort + bis zu zwei Figuren.
  Fertige Bilder liegen unter assets/illu/<slug>/<hash>.png und werden nie zweimal bezahlt.
"""
from __future__ import annotations

import hashlib
import json
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

    def schluessel(self, modell: str) -> str:
        return hashlib.sha256(json.dumps([modell, self.prompt, self.refs, self.seed]).encode()).hexdigest()[:20]


def auftraege(story: dict, sb: dict, st: dict | None = None) -> list[Auftrag]:
    st = st or stil()
    slug = story["slug"]
    ordner = ARCHIV / slug
    benutzt_f = list(dict.fromkeys(f for s in sb["shots"] for f in s.get("figuren") or []))
    benutzt_o = list(dict.fromkeys(s["ort"] for s in sb["shots"]))
    out: list[Auftrag] = []
    for tag in benutzt_f:
        fig = story["figuren"][tag]
        out.append(Auftrag(f"REF_{tag}", _clean(f"{st['stil_vorne']} {st['figur_blatt']} {fig['reference_prompt']}"),
                           seed=_seed(f"{slug}-illu-{tag}"), datei=ordner / f"ref_{tag}.png"))
    for tag in benutzt_o:
        out.append(Auftrag(f"REF_{tag}", _clean(f"{st['stil_vorne']} {st['ort_blatt']} "
                                                f"{story['orte'][tag]['reference_prompt']}"),
                           seed=_seed(f"{slug}-illu-{tag}"), datei=ordner / f"ref_{tag}.png"))
    for s in sb["shots"]:
        if s.get("bild_von"):
            continue
        figs = s.get("figuren") or []
        namen = ", ".join(f"@{f} ({story['figuren'][f]['name']})" for f in figs)
        prompt = _clean(f"{st['stil_vorne']} Setting: @{s['ort']}. "
                        f"{('Characters: ' + namen + '. ') if namen else 'No characters. '}{s['bild']}. "
                        f"{st['stil_hinten']}")
        a = Auftrag(f"IMG_{s['id']}", prompt, refs=[f"REF_{s['ort']}"] + [f"REF_{f}" for f in figs],
                    seed=_seed(f"{slug}-{sb['teil']}-{s['id']}"))
        a.datei = ordner / f"{a.schluessel(st['bildmodell'])}.png"
        out.append(a)
    return out


def bild_fuer(sb: dict, auftr: list[Auftrag]) -> dict[str, Path]:
    """Shot-ID → Bilddatei (auch für bild_von)."""
    by = {a.id: a.datei for a in auftr}
    out: dict[str, Path] = {}
    for s in sb["shots"]:
        out[s["id"]] = out[s["bild_von"]] if s.get("bild_von") else by[f"IMG_{s['id']}"]
    return out


def kosten(auftr: list[Auftrag], st: dict | None = None, nur_offene: bool = True) -> dict:
    """Credits/€ nach config/pricing.yaml und config/budget.yaml (USt + Sicherheitsaufschlag wie die Kasse)."""
    st = st or stil()
    preise = yaml.safe_load((ROOT / "config" / "pricing.yaml").read_text(encoding="utf-8"))
    b = yaml.safe_load((ROOT / "config" / "budget.yaml").read_text(encoding="utf-8"))
    m = preise["image"][st["bildmodell"]]
    if not m.get("verified"):
        raise ValueError(f"Preis für {st['bildmodell']} nicht bestätigt")
    offen = [a for a in auftr if not (nur_offene and a.datei and a.datei.exists())]
    credits = len(offen) * int(m["credits_per_image"])
    eur = credits * float(preise["usd_per_credit"]) * float(b["eur_per_usd"]) * (1 + float(b["vat_rate"]))
    return {"bilder": len(offen), "referenzen": sum(a.id.startswith("REF_") for a in offen),
            "shots": sum(a.id.startswith("IMG_") for a in offen), "credits": credits,
            "eur": round(eur, 2), "eur_reserve": round(eur * (1 + float(b["safety_margin"])), 2)}
