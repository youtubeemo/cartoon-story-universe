"""Produktionsablauf in drei Phasen mit Freigaben (alle kostenpflichtigen Schritte über die zentrale Kasse).

  vorlagen    Charaktervorlagen (vorne/seite/dreiviertel) + Ortsbilder einer Geschichte → Bogen zur Abnahme
  storyboard  Drehbuch (falls nötig) → Logikprüfung → Startbilder je Szene → KI-Bildprüfung → Bogen zur Abnahme
  animation   nur mit freigegebenem Storyboard: Bewegung, Stimmen, SFX, Musik → Schnitt → Qualitätskontrolle
  auto        täglicher Betrieb: animiert ein freigegebenes Storyboard, sonst Storyboard für den heutigen Tag

Keine Phase startet ohne paid_rendering_enabled + (Bestätigungsphrase oder taeglich_aktiv).
Keine automatischen Wiederholungen. Bezahlte Zwischenergebnisse bleiben im Cache.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import time
from pathlib import Path

from csu.common import (MUSIC, REFS, ROOT, budget, episode_path, load_episode, load_story, production,
                        storyhouse_import, write_json)
from csu.freigabe import freigegebene_vorlagen, freigegebenes_storyboard, storyboard_ordner
from csu.kasse import BudgetStopp, Kasse, git_sync
from csu.state import load_state, save_state
from csu.validate import validate_episode

storyhouse_import()
from storyhouse.budget import ApprovalError, BudgetError, Pricing, SpendGuard  # noqa: E402
from storyhouse.elevenlabs import ElevenLabsClient, ElevenLabsError, check_subscription  # noqa: E402
from storyhouse.runway import RunwayClient, RunwayError  # noqa: E402

STOPP = (BudgetStopp, BudgetError, ApprovalError, RunwayError, ElevenLabsError, ValueError)


def _summary(text: str) -> None:
    print(text)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


class Lauf:
    """Gemeinsamer Rahmen: Freigaben, Kasse, Clients, Buchung."""

    def __init__(self, a, phase: str):
        self.a, self.phase, self.b = a, phase, budget()
        self.t0 = time.time()
        self.d = dt.date.fromisoformat(a.datum) if a.datum else dt.date.today()
        self.run = os.environ.get("GITHUB_RUN_ID") or f"lokal-{int(self.t0)}"
        self.kasse = Kasse(float(self.b.get("monatsbudget_eur") or 0), monat=self.d.strftime("%Y-%m"))
        self.pricing = Pricing.load(ROOT / "config" / "pricing.yaml")
        from csu.plan import budget_config
        self.cfg = budget_config()
        self.out = Path(a.out)
        self.out.mkdir(parents=True, exist_ok=True)

    def gate(self, was: str) -> None:
        b = self.b
        grund = None
        if not b["paid_rendering_enabled"]:
            grund = "Kostenpflichtige Produktion ist nicht freigegeben (paid_rendering_enabled: false)."
        elif self.a.geplant and not b["taeglich_aktiv"]:
            grund = "Tägliche Produktion ist nicht freigegeben (taeglich_aktiv: false)."
        elif not self.a.geplant and self.a.bestaetigung.strip() != b["approval_phrase"]:
            grund = "Bestätigungsphrase fehlt oder ist falsch."
        elif self.kasse.reserviert > 0:
            grund = ("Offene Reservierung eines früheren Laufs – erst mit `python -m csu kasse --aufloesen RUN "
                     "--tatsaechlich EUR` klären.")
        if grund:
            _summary(f"## ⏸ {was}: keine Ausführung\n\n**Grund:** {grund}\n\n{self.kasse.stand()}\n\n"
                     "Es sind keine Kosten entstanden.")
            raise SystemExit(0)

    def reservieren(self, eur: float, zweck: str) -> None:
        self.kasse.reservieren(self.run, eur, zweck)
        git_sync(f"Kasse: Reservierung {zweck}", ["state"])

    def clients(self, runway_credits: float, el_credits: float, needs_music: bool, limit_eur: float) -> dict:
        g_rw = SpendGuard(limit_eur=limit_eur, pricing=self.pricing, cfg=self.cfg,
                          log_path=self.out / "ausgaben_runway.json", provider="runway")
        el_cap = self.pricing.credits_to_eur(el_credits, self.cfg, "elevenlabs") * 1.3 + 0.5
        g_el = SpendGuard(limit_eur=el_cap, pricing=self.pricing, cfg=self.cfg,
                          log_path=self.out / "ausgaben_elevenlabs.json", provider="elevenlabs")
        rw = RunwayClient(os.environ.get("RUNWAYML_API_SECRET", ""), g_rw)
        el = ElevenLabsClient(os.environ.get("ELEVENLABS_API_KEY", ""), g_el)
        saldo = rw.credit_balance()
        if saldo is None or saldo < runway_credits:
            raise BudgetStopp(f"Runway-Guthaben {saldo} Credits < benötigt {runway_credits:.0f}. Kein automatischer "
                              "Nachkauf – bitte manuell aufladen.")
        if el_credits > 0:
            check_subscription(el.subscription(), el_credits, self.cfg, needs_music=needs_music)
        self.guards = (g_rw, g_el)
        return {"runway": rw, "elevenlabs": el}

    def buchen(self, notiz: str, rw_credits: float, el_credits: float) -> None:
        g_rw, g_el = self.guards
        self.kasse.buchen(self.run, "runway", g_rw.spent_eur, rw_credits, notiz)
        if el_credits:
            self.kasse.buchen(self.run, "elevenlabs", 0.0, el_credits, "im Abo enthalten")
        self.kasse.aufloesen(self.run)

    def stopp(self, exc: Exception) -> None:
        self.kasse.aufloesen(self.run)
        _summary(f"## ⛔ {self.phase} gestoppt ({self.d})\n\n{exc}\n\n{self.kasse.stand()}")
        raise SystemExit(1)

    def release(self, tag: str, titel: str, dateien: list[str], bericht: Path, *, prerelease=False, draft=False):
        write_json(self.out / "release.json", {"tag": tag, "titel": titel, "dateien": dateien,
                                               "bericht": str(bericht), "prerelease": prerelease, "draft": draft})


def _ki_ref_bogen(slug: str, tags: list[str], ziel: Path) -> Path:
    from csu.vision import bogen
    files = [(t, REFS / slug / f"{t}.png") for t in tags if (REFS / slug / f"{t}.png").exists()]
    bogen(files, spalten=6, kachel_b=260).save(ziel, quality=88)
    return ziel


# ======================================================================= Phase: Vorlagen
def vorlagen(a) -> None:
    from csu.plan import vorlagen_jobs
    from csu.render import run_jobs
    lauf = Lauf(a, "Vorlagen")
    story = load_story(a.geschichte)
    slug = story["slug"]
    lauf.gate(f"Charaktervorlagen {story['titel']}")
    plan = vorlagen_jobs(story, lauf.pricing)
    vorhanden = freigegebene_vorlagen(slug)
    plan.jobs = [j for j in plan.jobs if j.id[4:] not in vorhanden]
    if not plan.jobs:
        _summary(f"Alle Vorlagen von {story['titel']} sind bereits freigegeben – nichts zu tun, 0 €.")
        return
    try:
        rw = lauf.pricing.credits_to_eur(plan.credits("runway"), lauf.cfg, "runway")
        reserve = round(rw * (1 + float(lauf.b["safety_margin"])), 2)
        clients = lauf.clients(plan.credits("runway"), 0, False, reserve)
        lauf.reservieren(reserve, f"Vorlagen {slug}")
    except STOPP as exc:
        lauf.stopp(exc)
    ok = False
    try:
        files = run_jobs(plan, clients, lauf.out / "roh", ROOT / ".cache" / "auftraege")
        ok = True
    finally:
        lauf.buchen(f"Vorlagen {slug}", plan.credits("runway"), 0)
        if not ok:
            _summary(f"## ⛔ Vorlagen abgebrochen\n\n{lauf.kasse.stand()}")
    ziel = REFS / slug
    ziel.mkdir(parents=True, exist_ok=True)
    for jid, f in files.items():
        if jid.startswith("REF_"):
            shutil.copy2(f, ziel / f"{jid[4:]}.png")
    from csu.plan import vorlagen_tags
    bogen = _ki_ref_bogen(slug, vorlagen_tags(story), lauf.out / f"vorlagen_{slug}.jpg")
    kosten = lauf.kasse.run_kosten(lauf.run)
    rep = ROOT / "berichte" / f"{lauf.d}_vorlagen_{slug}.md"
    rep.parent.mkdir(exist_ok=True)
    rep.write_text(f"# Charaktervorlagen: {story['titel']}\n\nNeu erzeugt: {len(plan.jobs)} Bilder · Kosten "
                   f"{sum(kosten.values()):.2f} € · {lauf.kasse.stand()}\n\nBitte den Bogen ansehen. Freigabe: "
                   f"`python -m csu freigeben vorlagen --geschichte {slug}` (oder Claude bitten).\n", encoding="utf-8")
    _summary(rep.read_text(encoding="utf-8"))
    lauf.release(f"vorlagen-{slug}-{lauf.d}", f"Vorlagen zur Abnahme: {story['titel']}", [str(bogen)], rep,
                 prerelease=True)


# ======================================================================= Phase: Storyboard
def storyboard(a, slug: str | None = None) -> None:
    from csu.cli import resolve_vote, slot_for
    from csu.plan import build_plan
    from csu.render import run_jobs
    from csu.voting import decide, fetch_youtube_comments, parse_manual, tally
    lauf = Lauf(a, "Storyboard")
    slug = slug or a.geschichte or slot_for(lauf.d)
    story = load_story(slug)
    st = load_state(story)
    teil = st["naechster_teil"]
    lauf.gate(f"Storyboard {story['titel']} Teil {teil}")
    print(resolve_vote(story, st, a.youtube_video_id, a.tiktok_stimmen, decide, fetch_youtube_comments,
                       parse_manual, tally))
    save_state(st)
    try:
        if not episode_path(slug, teil).exists():
            if not lauf.b["drehbuch_api_aktiv"]:
                raise BudgetStopp(f"Drehbuch Teil {teil} fehlt und drehbuch_api_aktiv ist false.")
            from csu.script import generate, max_cost_eur
            lauf.reservieren(max_cost_eur(), f"Drehbuch {slug} {teil}")
            res = generate(story, st)
            lauf.kasse.buchen(lauf.run, "anthropic", res["eur"], None, "Drehbuch")
            lauf.kasse.aufloesen(lauf.run)
        ep = load_episode(slug, teil)
        errs, _, _ = validate_episode(story, ep, st, tuple(production()["video"]["ziel_sekunden"]))
        if errs:
            raise BudgetStopp("Storyboard-Logikprüfung nicht bestanden – keine Bildkosten:\n  " + "\n  ".join(errs))
        plan = build_plan(story, ep, lauf.pricing, phase="storyboard",
                          storyboard=freigegebenes_storyboard(slug, teil))
        from csu.vision import max_cost_eur as vision_eur
        rw = lauf.pricing.credits_to_eur(plan.credits("runway"), lauf.cfg, "runway")
        reserve = round(rw * (1 + float(lauf.b["safety_margin"])), 2)
        clients = lauf.clients(plan.credits("runway"), 0, False, reserve)
        lauf.reservieren(reserve + (vision_eur() if lauf.b.get("ki_bildpruefung") else 0), f"Storyboard {slug} {teil}")
    except STOPP as exc:
        save_state(st)
        lauf.stopp(exc)
    ok = False
    try:
        files = run_jobs(plan, clients, lauf.out / "roh", ROOT / ".cache" / "auftraege")
        ok = True
    finally:
        g_rw, _ = lauf.guards
        lauf.kasse.buchen(lauf.run, "runway", g_rw.spent_eur, plan.credits("runway"), f"Storyboard {slug} {teil}")
        if not ok:
            lauf.kasse.aufloesen(lauf.run)
            _summary(f"## ⛔ Storyboard abgebrochen\n\n{lauf.kasse.stand()}")
    ordner = storyboard_ordner(slug, teil)
    ordner.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    for jid, f in files.items():
        if jid.startswith("KF_"):
            Image.open(f).convert("RGB").save(ordner / f"{jid}.jpg", quality=92)
    bilder = {p.stem: str(p) for p in sorted(ordner.glob("KF_*.jpg"))}

    ki = None
    if lauf.b.get("ki_bildpruefung"):
        from csu import vision
        ki = vision.pruefen(story, ep, freigegebene_vorlagen(slug), bilder)
        lauf.kasse.buchen(lauf.run, "anthropic", _anthropic_eur(ki.get("usage", {})), None, "KI-Bildprüfung")
        write_json(ordner / "ki_pruefung.json", ki)
    lauf.kasse.aufloesen(lauf.run)

    from csu.vision import bogen as mk_bogen
    labels = {s["id"]: f"{s['nr']}. {s['kamera']}" for s in ep["szenen"]}
    sheet = lauf.out / f"storyboard_{slug}_teil-{teil:02d}.jpg"
    mk_bogen([(labels[k[3:]], Path(p)) for k, p in bilder.items()], spalten=5, kachel_b=300).save(sheet, quality=88)
    st["storyboard"] = {"teil": teil, "status": "wartet_auf_freigabe" if not ki or ki["gesamt_ok"] else "ki_abgelehnt",
                        "datum": str(lauf.d)}
    save_state(st)
    kosten = lauf.kasse.run_kosten(lauf.run)
    zeilen = [f"# Storyboard: {story['titel']} – Teil {teil}: {ep['titel']}", "",
              f"Kosten {sum(kosten.values()):.2f} € · {lauf.kasse.stand()}", "", "| Nr | Ort | Figuren | Kamera | Handlung |",
              "|---|---|---|---|---|"]
    zeilen += [f"| {s['nr']} | {s['ort']} | {', '.join(s['figuren'])} | {s['kamera']}/{s['kamerabewegung']} | "
               f"{s['handlung']} |" for s in ep["szenen"]]
    if ki:
        zeilen += ["", f"**KI-Bildprüfung:** {'bestanden' if ki['gesamt_ok'] else 'NICHT bestanden'} – "
                       f"{ki.get('zusammenfassung', '')}"]
        zeilen += [f"- Szene {s['nr']}: {s.get('probleme')}" for s in ki.get("szenen", []) if not s.get("ok")]
    zeilen += ["", f"Freigabe nach Sichtung: `python -m csu freigeben storyboard --geschichte {slug} --teil {teil}`"]
    rep = ROOT / "berichte" / f"{lauf.d}_storyboard_{slug}_teil-{teil:02d}.md"
    rep.parent.mkdir(exist_ok=True)
    rep.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    _summary(rep.read_text(encoding="utf-8"))
    lauf.release(f"storyboard-{slug}-teil-{teil:02d}-{lauf.d}", f"Storyboard zur Abnahme: {story['titel']} Teil {teil}",
                 [str(sheet)], rep, prerelease=True)


def _anthropic_eur(usage: dict) -> float:
    from csu.script import cost_eur
    return cost_eur(usage)


# ======================================================================= Phase: Animation
def animation(a, slug: str | None = None) -> None:
    from csu import qc
    from csu.cli import slot_for
    from csu.plan import build_plan
    from csu.render import assemble, run_jobs
    lauf = Lauf(a, "Animation")
    slug = slug or a.geschichte or slot_for(lauf.d)
    story = load_story(slug)
    st = load_state(story)
    teil = st["naechster_teil"]
    lauf.gate(f"Animation {story['titel']} Teil {teil}")
    try:
        ep = load_episode(slug, teil)
        if not ep:
            raise BudgetStopp(f"Kein Drehbuch für Teil {teil}")
        errs, _, info = validate_episode(story, ep, st, tuple(production()["video"]["ziel_sekunden"]))
        if errs:
            raise BudgetStopp("Logikprüfung nicht bestanden:\n  " + "\n  ".join(errs))
        sb = freigegebenes_storyboard(slug, teil)
        need = {f"KF_{s['id']}" for s in ep["szenen"] if s["uebergang"] != "anschluss"}
        if lauf.b.get("storyboard_freigabe_erforderlich", True) and not need <= set(sb):
            raise BudgetStopp(f"Storyboard Teil {teil} ist nicht (vollständig) freigegeben – keine Animationskosten.")
        plan = build_plan(story, ep, lauf.pricing, phase="animation", storyboard=sb)
        rw = lauf.pricing.credits_to_eur(plan.credits("runway"), lauf.cfg, "runway")
        reserve = round(rw * (1 + float(lauf.b["safety_margin"])), 2)
        if reserve > float(lauf.b["max_pro_video_eur"]):
            raise BudgetStopp(f"Folge würde bis zu {reserve:.2f} € kosten (> max_pro_video_eur).")
        clients = lauf.clients(plan.credits("runway"), plan.credits("elevenlabs"),
                               any(j.kind == "music" for j in plan.jobs), reserve)
        lauf.reservieren(reserve, f"Animation {slug} {teil}")
    except STOPP as exc:
        lauf.stopp(exc)
    ok = False
    try:
        files = run_jobs(plan, clients, lauf.out / "roh", ROOT / ".cache" / "auftraege")
        ok = True
    finally:
        lauf.buchen(f"Animation {slug} Teil {teil}", plan.credits("runway"), plan.credits("elevenlabs"))
        save_state(st)
        if not ok:
            _summary(f"## ⛔ Animation abgebrochen – keine automatische Wiederholung\n\n{lauf.kasse.stand()}")
    if "MUSIC_story" in files:
        MUSIC.mkdir(parents=True, exist_ok=True)
        shutil.copy2(files["MUSIC_story"], MUSIC / f"{slug}.mp3")
    music = Path(plan.musik_datei) if plan.musik_datei else files.get("MUSIC_story")

    v = production()["video"]
    filename = f"{lauf.d}_{slug}_teil-{teil:02d}.mp4"
    res = assemble(story, ep, json.loads(json.dumps(st["werte"])), info["ereignisse"], files, music, lauf.out,
                   filename)
    tl = res["timeline"]
    quellen = [files[f"VID_{s['id']}"] for s in ep["szenen"]]
    pr = qc.pruefen(Path(res["datei"]), lauf.out / "schnitt" / "bild.mp4", tl, ep, quellen,
                    v["breite"], v["hoehe"], v["fps"], v["ziel_sekunden"])
    bogen = qc.kontaktbogen(Path(res["datei"]), tl["scenes"], ep, lauf.out / f"kontaktbogen_{slug}_teil-{teil:02d}.jpg")

    kosten = lauf.kasse.run_kosten(lauf.run)
    cost = round(sum(kosten.values()), 2)
    if pr["ok"]:   # Stand nur nach bestandener Qualitätskontrolle fortschreiben
        wahl = ep["entscheidung"]
        st["werte"] = info["endwerte"]
        st["verlauf"].append({"teil": teil, "datum": str(lauf.d), "datei": filename, "titel": ep["titel"],
                              "wahl_davor": (st.get("offene_entscheidung") or {}).get("option"),
                              "werte_danach": info["endwerte"], "eur": cost})
        st["offene_entscheidung"] = {"teil": teil, "frage": wahl["frage"], "standard": wahl["standard"],
                                     "optionen": {str(k): v for k, v in wahl["optionen"].items()}, "option": None}
        st["naechster_teil"] = teil + 1
        st.pop("storyboard", None)
    st["letzte_qc"] = {"teil": teil, "datum": str(lauf.d), "ok": pr["ok"]}
    save_state(st)

    tag = f"{lauf.d}-{slug}-teil-{teil:02d}"
    repo = os.environ.get("GITHUB_REPOSITORY", "youtubeemo/cartoon-story-universe")
    url = f"https://github.com/{repo}/releases/download/{tag}/{filename}"
    rep = ROOT / "berichte" / f"{lauf.d}_{slug}_teil-{teil:02d}.md"
    rep.parent.mkdir(exist_ok=True)
    rep.write_text("\n".join([
        f"# {story['titel']} – Teil {teil}: {ep['titel']}", "",
        ("**Download (MP4):** " + url) if pr["ok"] else
        "**⚠ Qualitätskontrolle NICHT bestanden – Entwurf, nicht freigegeben.**", "",
        f"Länge {res['laenge_s']:.1f} s · Produktionszeit {(time.time() - lauf.t0) / 60:.1f} min · "
        f"Kosten {cost:.2f} € (Runway {kosten.get('runway', 0):.2f} €; ElevenLabs im Abo) · {lauf.kasse.stand()}",
        "", "## Automatische Qualitätskontrolle", qc.als_markdown(pr), "",
        "Hinweis: Die automatische Kontrolle beweist keine gute Animation – bitte den Kontaktbogen und das Video "
        "ansehen.", *([f"Hinweis: {n}" for n in plan.notes])]) + "\n", encoding="utf-8")
    _summary(rep.read_text(encoding="utf-8"))
    lauf.release(tag, f"{story['titel']} – Teil {teil}: {ep['titel']}", [res["datei"], str(bogen)], rep,
                 draft=not pr["ok"])


# ======================================================================= Täglicher Betrieb
def auto(a) -> None:
    from csu.cli import slot_for
    from csu.kasse import jetzt
    d = dt.date.fromisoformat(a.datum) if a.datum else dt.date.today()
    if a.geplant and jetzt().hour < 5:
        print("Zeitplan: in Deutschland ist es noch vor 05:00 – Sommerzeit-Termin, Ende ohne Kosten.")
        return
    from csu.common import story_slugs
    for sl in story_slugs():   # zuerst ein bereits freigegebenes Storyboard animieren
        st = load_state(load_story(sl))
        sb = st.get("storyboard") or {}
        if sb.get("teil") == st["naechster_teil"] and freigegebenes_storyboard(sl, sb["teil"]):
            return animation(a, sl)
    return storyboard(a, slot_for(d))
