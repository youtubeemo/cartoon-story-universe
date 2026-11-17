"""Kostenlose Betriebsprüfung – KEIN kostenpflichtiger API-Aufruf.

* Schnitt-Prüfung: Platzhalter (Testbild + Sinuston, lokal mit FFmpeg erzeugt) laufen durch den echten Schnitt
  inkl. Anzeigen, Untertitel, Auswahlkarte und Qualitätsprüfung. Das Ergebnis wird danach gelöscht.
* API-Prüfung: nur kostenlose Lese-Endpunkte (Runway /v1/organization, ElevenLabs /v1/user/subscription und
  /v1/voices/{id}, Anthropic /v1/models). Es wird nichts generiert.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from csu.common import load_episode, load_story, production, story_slugs
from csu.plan import speech_items
from csu.state import initial_state, simulate
from csu.validate import CHARS_PER_SECOND


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def schnitt_pruefung() -> dict:
    from csu.render import assemble
    story = load_story("die-letzten-10000")
    ep = load_episode("die-letzten-10000", 1)
    st = initial_state(story)
    events, _ = simulate(story, st, ep)
    tmp = Path(tempfile.mkdtemp(prefix="csu-pruefung-"))
    files: dict[str, Path] = {}
    try:
        for s in ep["szenen"]:
            p = tmp / f"VID_{s['id']}.mp4"
            _ff("-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=24:duration=5", "-c:v", "libx264", "-preset",
                "ultrafast", str(p))
            files[f"VID_{s['id']}"] = p
            for it in speech_items(story, s):
                q = tmp / f"{it['id']}.mp3"
                _ff("-f", "lavfi", "-i", f"sine=frequency=440:duration={len(it['text']) / CHARS_PER_SECOND:.2f}",
                    str(q))
                files[it["id"]] = q
            for i, fx in enumerate(s.get("sfx") or []):
                q = tmp / f"SFX_{s['id']}_{i + 1}.mp3"
                _ff("-f", "lavfi", "-i", f"sine=frequency=880:duration={fx['dauer']}", str(q))
                files[f"SFX_{s['id']}_{i + 1}"] = q
        music = tmp / "musik.mp3"
        _ff("-f", "lavfi", "-i", "sine=frequency=220:duration=30", str(music))
        res = assemble(story, ep, st["werte"], events, files, music, tmp / "out", "pruefung.mp4")
        return res["qc"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)   # kein Probevideo aufbewahren


def _get(url: str, headers: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


def api_pruefung(runway_bedarf: float, el_monatsbedarf: float) -> list[tuple[bool, str]]:
    from csu.plan import budget_config
    from storyhouse.budget import Pricing, SpendGuard  # noqa: F401
    from storyhouse.elevenlabs import check_subscription
    out: list[tuple[bool, str]] = []
    rw, el, an = (os.environ.get(k, "") for k in ("RUNWAYML_API_SECRET", "ELEVENLABS_API_KEY", "ANTHROPIC_API_KEY"))

    # Runway – Guthaben (kostenlos)
    if rw:
        code, d = _get("https://api.dev.runwayml.com/v1/organization",
                       {"Authorization": f"Bearer {rw}", "X-Runway-Version": "2024-11-06"})
        bal = d.get("creditBalance")
        ok = code == 200 and bal is not None and float(bal) >= runway_bedarf
        out.append((ok, f"Runway: HTTP {code}, Guthaben {bal} Credits (nächste Folge braucht ≈ {runway_bedarf:.0f})"))
    else:
        out.append((False, "Runway: Secret RUNWAYML_API_SECRET fehlt"))

    # ElevenLabs – Tarif, Lizenz, Overage, Restkontingent, Stimmen (kostenlos)
    if el:
        code, sub = _get("https://api.elevenlabs.io/v1/user/subscription", {"xi-api-key": el})
        try:
            info = check_subscription(sub if code == 200 else None, el_monatsbedarf, budget_config(), needs_music=True)
            out.append((True, f"ElevenLabs: Tarif {sub.get('tier')}, {int(sub['character_limit'] - sub['character_count'])}"
                              f" Credits frei, keine Nachberechnung ({info if isinstance(info, str) else 'ok'})"))
        except Exception as exc:  # noqa: BLE001
            out.append((False, f"ElevenLabs: {exc}"))
        voices = {production()["sprecher"]["voice_id"]}
        for slug in story_slugs():
            voices |= {f["voice"]["voice_id"] for f in load_story(slug)["figuren"].values() if f.get("voice")}
        missing = [v for v in sorted(voices)
                   if _get(f"https://api.elevenlabs.io/v1/voices/{v}", {"xi-api-key": el})[0] != 200]
        out.append((not missing, f"ElevenLabs-Stimmen: {len(voices) - len(missing)}/{len(voices)} verfügbar"
                                 + (f", fehlend: {', '.join(missing)}" if missing else "")))
    else:
        out.append((False, "ElevenLabs: Secret ELEVENLABS_API_KEY fehlt"))

    # Anthropic – Schlüssel und Modell (Models-API, kostenlos)
    if an:
        from csu.common import budget
        modell = budget()["anthropic"]["modell"]
        code, d = _get("https://api.anthropic.com/v1/models?limit=100",
                       {"x-api-key": an, "anthropic-version": "2023-06-01"})
        ids = [m.get("id") for m in d.get("data", [])]
        out.append((code == 200 and modell in ids, f"Anthropic: HTTP {code}, Modell {modell} "
                                                    f"{'verfügbar' if modell in ids else 'NICHT gefunden: ' + ', '.join(ids[:6])}"))
    else:
        out.append((False, "Anthropic: Secret ANTHROPIC_API_KEY fehlt"))
    return out
