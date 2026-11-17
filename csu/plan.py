"""Auftragsplan einer Folge (reine Daten, sendet nichts) + Kostenschätzung.

Nutzt die geprüften Bausteine aus storyhouse-originals: Job, Preistabelle, Spezifikationsprüfung.
Abgenommene Referenzbilder (assets/refs/<slug>/<tag>.png) und die Musik je Geschichte
(assets/music/<slug>.mp3) werden wiederverwendet – sie kosten nur beim allerersten Mal.
"""
from __future__ import annotations

import hashlib
import zlib
from dataclasses import dataclass, field

from csu.common import MUSIC, REFS, budget, production, storyhouse_import
from csu.validate import ref_sources, tags_in

storyhouse_import()
from storyhouse import elevenlabs_spec as el_spec  # noqa: E402
from storyhouse.budget import BudgetConfig, Pricing, with_margin  # noqa: E402
from storyhouse.plan import Job  # noqa: E402
from storyhouse.runway_spec import snap_duration  # noqa: E402

IMAGE_RATIO = "1080:1920"
MAX_REFS = 3


def _seed(key: str) -> int:
    return zlib.crc32(key.encode()) % 4294967295


def _clean(t: str) -> str:
    return " ".join(str(t).split())


@dataclass
class EpisodePlan:
    slug: str
    teil: int
    profil: str
    jobs: list = field(default_factory=list)
    frozen_refs: dict = field(default_factory=dict)   # Job-ID -> Pfad (0 €)
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


def build_plan(story: dict, ep: dict, pricing: Pricing, profil: str | None = None) -> EpisodePlan:
    prod = production()
    profil = profil or prod.get("profil", "test")
    prof = pricing.profile(profil)
    style, motion_style = _clean(prod["stil"]["global"]), _clean(prod["stil"]["bewegung"])
    slug = story["slug"]
    plan = EpisodePlan(slug=slug, teil=int(ep["teil"]), profil=profil)
    sources = ref_sources(story)

    def add(job: Job) -> None:
        job.validate()
        plan.jobs.append(job)

    # 1) Referenzbilder (Figuren + Orte) – nur, wenn noch kein abgenommenes Bild im Repo liegt
    needed = []
    for s in ep["szenen"]:
        for t in tags_in(s["keyframe_prompt"])[:MAX_REFS]:
            if t not in needed:
                needed.append(t)
    ref_id = {}
    for tag in needed:
        frozen = REFS / slug / f"{tag}.png"
        if frozen.exists():
            ref_id[tag] = f"REF_{tag}_{hashlib.sha256(frozen.read_bytes()).hexdigest()[:8]}"
            plan.frozen_refs[ref_id[tag]] = str(frozen)
            continue
        ref_id[tag] = f"REF_{tag}"
        model = prof["reference_image_model"]
        add(Job(id=ref_id[tag], kind="image", model=model, ext="png", credits=pricing.image_credits(model),
                payload={"model": model, "promptText": _clean(f"{sources[tag]} {style}")[:1000],
                         "ratio": IMAGE_RATIO, "seed": _seed(f"{slug}-ref-{tag}")}))
    if plan.frozen_refs:
        plan.notes.append(f"{len(plan.frozen_refs)} Referenzbilder aus dem Repo wiederverwendet (0 €)")

    # 2) Keyframes + 3) Bewegtbild je Szene
    for s in ep["szenen"]:
        tags = tags_in(s["keyframe_prompt"])[:MAX_REFS]
        refs = [{"uri": f"{{{{out:{ref_id[t]}}}}}", "tag": t} for t in tags]
        model = prof["keyframe_model"] if refs else prof["reference_image_model"]  # *_turbo braucht Referenzen
        add(Job(id=f"KF_{s['id']}", kind="image", model=model, scene=s["id"], ext="png",
                credits=pricing.image_credits(model),
                depends=[ref_id[t] for t in tags if ref_id[t] not in plan.frozen_refs],
                payload={"model": model, "promptText": _clean(f"{s['keyframe_prompt']} {style}")[:1000],
                         "ratio": IMAGE_RATIO, **({"referenceImages": refs} if refs else {}),
                         "seed": _seed(f"{slug}-{ep['teil']}-kf-{s['id']}")}))
        vmodel = prof["video_model"]
        dur = snap_duration(vmodel, float(s["dauer"]))
        add(Job(id=f"VID_{s['id']}", kind="video", model=vmodel, scene=s["id"], ext="mp4",
                credits=pricing.video_credits(vmodel, dur), depends=[f"KF_{s['id']}"],
                payload={"model": vmodel, "promptImage": f"{{{{out:KF_{s['id']}}}}}",
                         "promptText": _clean(f"{s['motion_prompt']}. {motion_style}")[:1000],
                         "ratio": prod["video"]["generierung_ratio"], "duration": dur,
                         "seed": _seed(f"{slug}-{ep['teil']}-vid-{s['id']}")}))

    # 4) Stimmen (ElevenLabs) – Erzähler + Figuren
    for s in ep["szenen"]:
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
        # 5) Soundeffekte
        sfx_model = pricing.elevenlabs_model("sfx")
        for i, fx in enumerate(s.get("sfx") or []):
            add(Job(id=f"SFX_{s['id']}_{i + 1}", kind="sfx", model=sfx_model, scene=s["id"], ext="mp3",
                    provider="elevenlabs", path=el_spec.SFX_PATH,
                    credits=pricing.el_sfx_credits(sfx_model, float(fx["dauer"])),
                    payload={"text": _clean(fx["prompt"]), "model_id": sfx_model,
                             "duration_seconds": float(fx["dauer"]), "loop": False, "prompt_influence": 0.4}))

    # 6) Musik – einmal je Geschichte, danach aus dem Repo
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
    else:
        plan.notes.append("Keine Musik: Lizenzprüfung Eleven Music offen (budget.yaml) und keine Datei in assets/music/")
    return plan


def estimate(plan: EpisodePlan, pricing: Pricing, cfg: BudgetConfig) -> dict:
    eur = plan.eur(pricing, cfg)
    return {"runway_credits": round(plan.credits("runway")), "elevenlabs_credits": round(plan.credits("elevenlabs")),
            "eur": round(eur, 2), "eur_mit_puffer": round(with_margin(eur, cfg), 2), "auftraege": len(plan.jobs)}
