"""Freigaben für Charaktervorlagen und Storyboards.

Eine Freigabe ist eine Datei ``freigabe.yaml`` mit dem SHA-256 jedes abgenommenen Bildes. Nur Bilder, deren
Prüfsumme passt, werden verwendet – ein nachträglich ausgetauschtes Bild gilt automatisch als NICHT freigegeben.
Freigaben setzt ausschließlich ein Mensch (per ``python -m csu freigeben …`` nach Sichtung).
"""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import yaml

from csu.common import REFS, ROOT

BILD = (".png", ".jpg")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _approved(folder: Path) -> dict[str, str]:
    f = folder / "freigabe.yaml"
    if not f.exists():
        return {}
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    out = {}
    for name, sha in (data.get("dateien") or {}).items():
        p = folder / name
        if p.exists() and _sha(p) == sha:
            out[p.stem] = str(p)
    return out


def freigegebene_vorlagen(slug: str) -> dict[str, str]:
    """{tag: pfad} der abgenommenen Charakter-/Ortsvorlagen."""
    return _approved(REFS / slug)


def storyboard_ordner(slug: str, teil: int) -> Path:
    return ROOT / "assets" / "storyboards" / slug / f"teil-{teil:02d}"


def freigegebenes_storyboard(slug: str, teil: int) -> dict[str, str]:
    """{KF_Sxx: pfad} der abgenommenen Startbilder."""
    return _approved(storyboard_ordner(slug, teil))


def freigeben(folder: Path, nur: list[str] | None = None, notiz: str = "") -> list[str]:
    files = sorted(p for p in folder.iterdir() if p.suffix in BILD and (not nur or p.stem in nur))
    if not files:
        raise SystemExit(f"Keine Bilder in {folder}")
    data = {"freigegeben_am": dt.datetime.now().isoformat(timespec="seconds"), "notiz": notiz,
            "dateien": {p.name: _sha(p) for p in files}}
    (folder / "freigabe.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return [p.name for p in files]
