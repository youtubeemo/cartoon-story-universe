"""Auftragspläne (reine Daten, sendet nichts) + Kostenschätzung.

Drei Phasen, jede mit eigener Freigabe:
  vorlagen    – Charaktervorlagen (vorne/seite/dreiviertel) und Ortsbilder, einmal je Geschichte
  storyboard  – ein Startbild je Szene (nur bei schnitt/ueberblendung/abblende), aus freigegebenen Vorlagen
  animation   – Bewegung je Szene aus freigegebenem Storyboard, Stimmen, SFX, Musik

Abgenommene Dateien (Vorlagen, Storyboard-Bilder, Musik) werden als „eingefroren“ übergeben und kosten 0 €.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from pathlib import Path

from csu.common import MUSIC, budget, production, storyhouse_import
from csu.freigabe import freigegebene_vorlagen
from csu.validate import VIEW_SUFFIX, ref_tag, scene_refs, stil

storyhouse_import()
from storyhouse import elevenlabs_spec as el_spec  # noqa: E402
from storyhouse.budget import BudgetConfig, Pricing, with_margin  # noqa: E402
from storyhouse.plan import Job  # noqa: E402
from storyhouse.runway_spec import snap_duration  # noqa: E402

IMAGE_RATIO = "1080:1920"


def _seed(key: str) -> int:
    return zlib.crc32(key.encode()) % 4294967295


def _clean(t: str) -> str:
    return " ".join(str(t).split())


@dataclass
class EpisodePlan:
    slug: str
    teil: int
    profil: str
    phase: str
    jobs: list = field(default_factory=list)
    frozen_refs: dict = field(default_factory=dict)   # Job-ID -> Pfad (0 €): Vorlagen, Storyboard-Bilder
    musik_datei: str | None = None
    notes: list = field(default_factory=list)

    def credits(self, provider: str) -> float:
        return sum(j.credits for j in self.jobs if j.provider == provider)

    def eur(self, pricing: Pricing, cfg: BudgetConfig) -> float:
        return sum(pricing.credits_to_eur(self.credits(p), cfg, p) for p in ("runway", "elevenlabs"))


def budget_config() -> BudgetConfig:
    b = budget()
    per_video = float(b["max_pro_video_eur"])
    total = min(200.0, max(per_video, float(b.get("monatsbudget_eur") or 0)))
    return BudgetConfig(
        paid_rendering_enabled=bool(b["paid_rendering_enabled"]),
        total_budget_eur=total, max_per_run_eur=min(per_video, total),
        safety_margin=float(b["safety_margin"]), eur_per_usd=float(b["eur_per_usd"]),
        vat_rate=float(b["vat_rate"]), warn_at_fraction=0.75, approval_phrase=str(b["approval_phrase"]),
        el_require_commercial_license=bool(b["elevenlabs"]["require_commercial_license"]),
        el_music_license_confirmed=bool(b["elevenlabs"]["music_license_confirmed"]),
    )


def speech_items(story: dict, scene: dict) -> list[dict]:
    """Sprechtexte einer Szene in Reihenfolge: Erzähler, dann Dialog."""
    sp = production()["sprecher"]
    out = []
    if scene.get("erzaehler"):
        out.append({"id": f"TTS_{scene['id']}_N", "text": scene["erzaehler"], "erzaehler": True, "voice": sp})
    for i, d in enumerate(scene.get("dialog") or []):
        out.append({"id": f"TTS_{scene['id']}_D{i + 1}", "text": d["text"], "erzaehler": False,
                    "figur": d["figur"], "voice": story["figuren"][d["figur"]]["voice"]})
    return out


# ------------------------------------------------------------------ Phase 1: Vorlagen
def vorlagen_jobs(story: dict, pricing: Pricing, profil: str | None = None) -> EpisodePlan:
    st = stil()
    prof = pricing.profile(profil or production().get("profil", "qualitaet"))
    model = prof["reference_image_model"]
    plan = EpisodePlan(slug=story["slug"], teil=0, profil=profil or production().get("profil"), phase="vorlagen")
    look, avoid = _clean(st["look_kurz"]), _clean(st["verboten"])
    for key, fig in story["figuren"].items():
        base = _clean(fig["reference_prompt"])
        vorne = ref_tag(key, "vorne")
        plan.jobs.append(Job(id=f"REF_{vorne}", kind="image", model=model, ext="png",
                             credits=pricing.image_credits(model),
                             payload={"model": model, "ratio": IMAGE_RATIO, "seed": _seed(f"{story['slug']}-{vorne}"),
                                      "promptText": _clean(f"Character design sheet of {fig['name']}: {base} "
                                                           f"{st['ansichten']['vorne']}. {st['vorlage_hintergrund']}. "
                                                           f"{look} Avoid: {avoid}")[:1000]}))
        for ansicht in ("seite", "dreiviertel"):
            tag = ref_tag(key, ansicht)
            plan.jobs.append(Job(
                id=f"REF_{tag}", kind="image", model=model, ext="png", credits=pricing.image_credits(model),
                depends=[f"REF_{vorne}"],
                payload={"model": model, "ratio": IMAGE_RATIO, "seed": _seed(f"{story['slug']}-{tag}"),
                         "referenceImages": [{"uri": f"{{{{out:REF_{vorne}}}}}", "tag": vorne}],
                         "promptText": _clean(f"The exact same character as @{vorne}, identical design, colors, "
                                              f"proportions and outfit, {st['ansichten'][ansicht]}. "
                                              f"{st['vorlage_hintergrund']}. {look}")[:1000]}))
    for key, ort in story["orte"].items():
        plan.jobs.append(Job(id=f"REF_{key[:16]}", kind="image", model=model, ext="png",
                             credits=pricing.image_credits(model),
                             payload={"model": model, "ratio": IMAGE_RATIO, "seed": _seed(f"{story['slug']}-{key}"),
                                      "promptText": _clean(f"Background layout, no characters: {ort['reference_prompt']} "
                                                           f"{look} Avoid: {avoid}")[:1000]}))
    return plan


def vorlagen_tags(story: dict) -> list[str]:
    tags = [ref_tag(k, a) for k in story["figuren"] for a in VIEW_SUFFIX]
    return tags + [k[:16] for k in story["orte"]]


# ------------------------------------------------------------------ Phase 2+3: Storyboard und Animation
def _kf_prompt(story: dict, s: dict) -> str:
    st = stil()
    refs = scene_refs(story, s)
    who = "; ".join(f"@{t} is {d}" for t, d in refs if not d.startswith("Ort"))
    where = next((f"Location: @{t}." for t, d in refs if d.startswith("Ort")), "")
    return _clean(f"{s['bild']}. {st['kamera'][s['kamera']]}. {st['tageszeit'][s['tageszeit']]}. "
                  f"{('Characters: ' + who + '.') if who else 'No characters.'} {where} "
                  f"Exactly these characters, no others. {st['look_kurz']} Avoid: {st['verboten']}")[:1000]


def _vid_prompt(s: dict) -> str:
    st = stil()
    talk = st["sprechen"] if s.get("dialog") else ""
    return _clean(f"{s['bewegung']}. Camera: {st['kamerabewegung'][s['kamerabewegung']]}. {talk} "
                  f"{st['bewegung']}")[:1000]


def build_plan(story: dict, ep: dict, pricing: Pricing, profil: str | None = None, phase: str = "animation",
               storyboard: dict[str, str] | None = None, schaetzung: bool = False) -> EpisodePlan:
    """phase storyboard: nur Startbilder. phase animation: alles außer bereits freigegebenen Startbildern."""
    prod = production()
    profil = profil or prod.get("profil", "qualitaet")
    prof = pricing.profile(profil)
    slug = story["slug"]
    plan = EpisodePlan(slug=slug, teil=int(ep["teil"]), profil=profil, phase=phase)
    vorlagen = freigegebene_vorlagen(slug)
    storyboard = storyboard or {}

    def add(job: Job) -> None:
        job.validate()
        plan.jobs.append(job)

    for tag, path in vorlagen.items():
        plan.frozen_refs[f"REF_{tag}"] = path
    scenes = ep["szenen"]
    needed = {t for s in scenes if s["uebergang"] != "anschluss" for t, _ in scene_refs(story, s)}
    missing = sorted(needed - set(vorlagen))
    if schaetzung:              # nur Kostenschätzung: fehlende Vorlagen/Startbilder als vorhanden annehmen
        for t in missing:
            plan.frozen_refs[f"REF_{t}"] = "(Schätzung)"
        missing = []
    if missing:
        raise ValueError(f"Nicht freigegebene/fehlende Vorlagen: {', '.join(missing)} – erst Phase „vorlagen“")

    # Startbilder je Szene (anschluss-Szenen beginnen mit dem letzten Bild der vorigen Szene)
    for s in scenes:
        if s["uebergang"] == "anschluss":
            continue
        kid = f"KF_{s['id']}"
        if kid in storyboard:
            plan.frozen_refs[kid] = storyboard[kid]
            continue
        if phase == "animation" and schaetzung:
            plan.frozen_refs[kid] = "(Schätzung)"
            continue
        if phase == "animation":
            raise ValueError(f"{kid}: kein freigegebenes Storyboard-Bild – erst Phase „storyboard“")
        refs = [{"uri": f"{{{{out:REF_{t}}}}}", "tag": t} for t, _ in scene_refs(story, s)]
        model = prof["keyframe_model"]
        add(Job(id=kid, kind="image", model=model, scene=s["id"], ext="png", credits=pricing.image_credits(model),
                payload={"model": model, "promptText": _kf_prompt(story, s), "ratio": IMAGE_RATIO,
                         "referenceImages": refs, "seed": _seed(f"{slug}-{ep['teil']}-kf-{s['id']}")}))
    if phase == "storyboard":
        return plan

    # Bewegung je Szene
    vmodel = prof["video_model"]
    ratio = prod["video"]["generierung_ratio"][vmodel]
    prev = None
    for s in scenes:
        first = f"{{{{out:LF_VID_{prev['id']}}}}}" if s["uebergang"] == "anschluss" else f"{{{{out:KF_{s['id']}}}}}"
        dur = snap_duration(vmodel, float(s["dauer"]))
        payload = {"model": vmodel, "promptText": _vid_prompt(s), "ratio": ratio, "duration": dur,
                   "seed": _seed(f"{slug}-{ep['teil']}-vid-{s['id']}")}
        payload["promptImage"] = [{"uri": first, "position": "first"}] if vmodel.startswith("veo") else first
        if vmodel.startswith("veo"):
            payload["audio"] = False          # Ton kommt von ElevenLabs
        add(Job(id=f"VID_{s['id']}", kind="video", model=vmodel, scene=s["id"], ext="mp4",
                credits=pricing.video_credits(vmodel, dur),
                depends=[f"VID_{prev['id']}"] if s["uebergang"] == "anschluss" else [],
                payload=payload))
        prev = s

    # Stimmen, Soundeffekte (ElevenLabs, im Abo)
    for s in scenes:
        for it in speech_items(story, s):
            v = it["voice"]
            model = v.get("model") or pricing.elevenlabs_model("tts")
            body = {"text": it["text"], "model_id": model,
                    "voice_settings": {"stability": float(v.get("stability", 0.5))},
                    "seed": _seed(f"{slug}-{ep['teil']}-{it['id']}")}
            if el_spec.TTS_MODELS.get(model, {}).get("language_code"):
                body["language_code"] = "de"
            add(Job(id=it["id"], kind="tts", model=model, scene=s["id"], ext="mp3", provider="elevenlabs",
                    path=el_spec.tts_path(str(v["voice_id"])), credits=pricing.el_tts_credits(model, it["text"]),
                    payload=body))
        sfx_model = pricing.elevenlabs_model("sfx")
        for i, fx in enumerate(s.get("sfx") or []):
            add(Job(id=f"SFX_{s['id']}_{i + 1}", kind="sfx", model=sfx_model, scene=s["id"], ext="mp3",
                    provider="elevenlabs", path=el_spec.SFX_PATH,
                    credits=pricing.el_sfx_credits(sfx_model, float(fx["dauer"])),
                    payload={"text": _clean(fx["prompt"]), "model_id": sfx_model,
                             "duration_seconds": float(fx["dauer"]), "loop": False, "prompt_influence": 0.4}))

    music = MUSIC / f"{slug}.mp3"
    if music.exists():
        plan.musik_datei = str(music)
    elif budget_config().el_music_license_confirmed:
        mm = pricing.elevenlabs_model("music")
        add(Job(id="MUSIC_story", kind="music", model=mm, ext="mp3", provider="elevenlabs", path=el_spec.MUSIC_PATH,
                credits=pricing.el_music_credits(mm, 90.0),
                payload={"prompt": _clean(story["musik"]), "model_id": mm, "music_length_ms": 90000,
                         "force_instrumental": True}))
        plan.notes.append("Musik wird einmalig erzeugt und danach wiederverwendet")
    return plan


def estimate(plan: EpisodePlan, pricing: Pricing, cfg: BudgetConfig) -> dict:
    eur = plan.eur(pricing, cfg)
    rw = pricing.credits_to_eur(plan.credits("runway"), cfg, "runway")
    return {"runway_credits": round(plan.credits("runway")), "elevenlabs_credits": round(plan.credits("elevenlabs")),
            "runway_eur": round(rw, 2), "eur": round(eur, 2), "eur_mit_puffer": round(with_margin(eur, cfg), 2),
            "auftraege": len(plan.jobs)}


def storyboard_dir(slug: str, teil: int) -> Path:
    from csu.common import ROOT
    return ROOT / "assets" / "storyboards" / slug / f"teil-{teil:02d}"
