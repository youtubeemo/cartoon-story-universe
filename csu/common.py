"""Gemeinsame Pfade, YAML-Laden und Anbindung an storyhouse (API-Clients + Budgetwächter)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
STORIES = ROOT / "stories"
STATE = ROOT / "state"
REFS = ROOT / "assets" / "refs"
MUSIC = ROOT / "assets" / "music"

# storyhouse-originals wird in einer festen, geprüften Version eingebunden (scripts/storyhouse_holen.sh)
STORYHOUSE_COMMIT = "0c12b1d996d3438952477af7e546f43b287dcc94"
STORYHOUSE_DIR = Path(os.environ.get("STORYHOUSE_PATH", ROOT / "vendor" / "storyhouse-originals"))


def storyhouse_import() -> None:
    """Macht das Paket ``storyhouse`` importierbar (Runway/ElevenLabs-Clients, Preise, SpendGuard)."""
    p = str(STORYHOUSE_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)
    try:
        import storyhouse  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(f"storyhouse nicht gefunden ({p}) – scripts/storyhouse_holen.sh ausführen") from exc


def load_yaml(path: Path) -> Any:
    with Path(path).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def production() -> dict:
    return load_yaml(CONFIG / "production.yaml")


def budget() -> dict:
    return load_yaml(CONFIG / "budget.yaml")


def story_slugs() -> list[str]:
    return sorted(p.parent.name for p in STORIES.glob("*/story.yaml"))


def load_story(slug: str) -> dict:
    path = STORIES / slug / "story.yaml"
    if not path.exists():
        raise SystemExit(f"Geschichte {slug} fehlt ({path})")
    return load_yaml(path)


def episode_path(slug: str, part: int) -> Path:
    return STORIES / slug / f"teil-{part:02d}.yaml"


def load_episode(slug: str, part: int) -> dict | None:
    p = episode_path(slug, part)
    return load_yaml(p) if p.exists() else None


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fmt_num(v: float | int) -> str:
    """Deutsche Tausenderpunkte: 10000 -> 10.000"""
    return f"{int(round(v)):,}".replace(",", ".")
