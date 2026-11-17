"""Befehle:  python -m csu <befehl>

  heute        Welche Geschichte/welcher Teil ist heute dran?           (kostenlos)
  validate     Alle Geschichten + vorhandenen Folgen prüfen             (kostenlos)
  estimate     Kosten einer Folge aus dem echten Auftragsplan           (kostenlos)
  kosten       Hochrechnung pro Video und Monat                         (kostenlos)
  abstimmen    Zuschauerwahl auswerten und speichern                    (kostenlos)
  produzieren  Tageslauf: Wahl → Drehbuch → Prüfung → Render → MP4      (KOSTENPFLICHTIG, nur nach Freigabe)
  kasse        Monatsbudget, Reservierungen, Nachbuchung                (kostenlos)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from csu.common import (ROOT, STATE, budget, episode_path, load_episode, load_story, production, story_slugs,
                        write_json)
from csu.state import effects_to_events, load_state, save_state
from csu.validate import validate_episode, validate_story

SLOT_FILE = STATE / "wochenplan.json"


# ---------------------------------------------------------------- Plan
def slot_for(date: dt.date) -> str:
    prod = production()
    slots = {int(k): v for k, v in prod["wochenplan"].items()}
    if SLOT_FILE.exists():
        slots.update({int(k): v for k, v in json.loads(SLOT_FILE.read_text()).items()})
    slug = slots[date.weekday()]
    story = load_story(slug)
    if load_state(story)["naechster_teil"] > story["teile"]:  # Finale gelaufen → nächste Geschichte
        queue = list(prod.get("warteschlange") or [])
        used = set(slots.values())
        nxt = next((q for q in queue if q not in used), None)
        if not nxt:
            raise SystemExit(f"{slug} ist beendet und die Warteschlange ist leer – neue Geschichte anlegen")
        slots[date.weekday()] = nxt
        write_json(SLOT_FILE, {str(k): v for k, v in slots.items()})
        slug = nxt
    return slug


def cmd_heute(a) -> None:
    d = dt.date.fromisoformat(a.datum) if a.datum else dt.date.today()
    slug = slot_for(d)
    story = load_story(slug)
    st = load_state(story)
    print(f"{d} ({['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][d.weekday()]}): {story['titel']} – Teil {st['naechster_teil']}"
          f" von {story['teile']}; Drehbuch {'vorhanden' if episode_path(slug, st['naechster_teil']).exists() else 'fehlt'}")


# ---------------------------------------------------------------- Prüfung
def cmd_validate(a) -> None:
    errors = 0
    for slug in story_slugs():
        story = load_story(slug)
        errs = validate_story(story)
        st = load_state(story)
        ep = load_episode(slug, st["naechster_teil"])
        warns, info = [], {}
        if ep:
            e2, warns, info = validate_episode(story, ep, st, tuple(production()["video"]["ziel_sekunden"]))
            errs += e2
        mark = "✗" if errs else "✓"
        extra = f" · Teil {st['naechster_teil']}: ≈{info.get('laenge_s')} s, {info.get('szenen')} Szenen" if ep else ""
        print(f"{mark} {slug}{extra}")
        for e in errs:
            print(f"   FEHLER: {e}")
        for w in warns:
            print(f"   Hinweis: {w}")
        errors += len(errs)
    if errors:
        sys.exit(1)


# ---------------------------------------------------------------- Kosten
def _plan_for(slug: str, profil: str | None = None):
    from csu.plan import Pricing, budget_config, build_plan, estimate
    story = load_story(slug)
    st = load_state(story)
    ep = load_episode(slug, st["naechster_teil"])
    if not ep:
        raise SystemExit(f"Drehbuch Teil {st['naechster_teil']} von {slug} fehlt")
    pricing = Pricing.load(ROOT / "config" / "pricing.yaml")
    cfg = budget_config()
    plan = build_plan(story, ep, pricing, profil)
    return story, st, ep, plan, pricing, cfg, estimate(plan, pricing, cfg)


def cmd_estimate(a) -> None:
    _, _, _, plan, _, _, est = _plan_for(a.geschichte, a.profil)
    print(json.dumps({"profil": plan.profil, **est, "hinweise": plan.notes}, indent=2, ensure_ascii=False))


def cmd_kosten(a) -> None:
    """Hochrechnung aus dem echten Plan von Teil 1 „Die letzten 10.000 €“ (ohne Referenzen/Musik = Dauerbetrieb)."""
    rows = []
    for profil in ("test", "final"):
        _, _, _, plan, pricing, cfg, _ = _plan_for("die-letzten-10000", profil)
        runway_once = sum(j.credits for j in plan.jobs if j.id.startswith("REF_"))
        rw = plan.credits("runway") - runway_once
        el = plan.credits("elevenlabs") - sum(j.credits for j in plan.jobs if j.id == "MUSIC_story")
        rw_eur = pricing.credits_to_eur(rw, cfg, "runway")
        for quote in (1.0, 1.5):
            per_video = rw_eur * quote
            rows.append((profil, quote, rw * quote, el, per_video, per_video * 30))
    print("| Profil | Nachdrehquote | Runway-Credits/Video | ElevenLabs-Credits/Video | Runway €/Video inkl. USt. | Runway €/Monat (30) |")
    print("|---|---:|---:|---:|---:|---:|")
    for p, q, rw, el, v, m in rows:
        print(f"| {p} | {q:.1f}× | {rw:,.0f} | {el:,.0f} | {v:.2f} € | {m:.0f} € |")


# ---------------------------------------------------------------- Abstimmung
def cmd_abstimmen(a) -> None:
    from csu.voting import decide, fetch_youtube_comments, parse_manual, tally
    story = load_story(a.geschichte)
    st = load_state(story)
    print(resolve_vote(story, st, a.youtube_video_id, a.manuell, decide, fetch_youtube_comments, parse_manual, tally))
    save_state(st)


def resolve_vote(story, st, yt_id, manual, decide, fetch, parse_manual, tally) -> str:
    wahl = st.get("offene_entscheidung")
    if not wahl or wahl.get("option"):
        return "Keine offene Entscheidung."
    from collections import Counter
    counts = Counter()
    yt_id = yt_id or wahl.get("youtube_video_id")
    key = os.environ.get("YOUTUBE_API_KEY")
    quelle = []
    if yt_id and key:
        try:
            counts += tally(fetch(yt_id, key), {os.environ.get("YOUTUBE_CHANNEL_ID", "")})
            quelle.append("YouTube")
        except Exception as exc:  # Kommentare nicht zuverlässig abrufbar → Standardoption
            quelle.append(f"YouTube nicht abrufbar ({type(exc).__name__})")
    if manual:
        counts += parse_manual(manual)
        quelle.append("TikTok (manuell)")
    option, grund = decide(counts, int(wahl["standard"]), int(budget().get("min_stimmen", 5)))
    wahl.update({"option": option, "effekte": wahl["optionen"][str(option)]["effekte"],
                 "stimmen": {str(k): counts[k] for k in (1, 2, 3)}, "grund": grund, "quellen": quelle})
    return f"Entscheidung Teil {st['naechster_teil'] - 1}: Option {option} – {grund}"


# ---------------------------------------------------------------- Produktion
def _summary(text: str) -> None:
    """Kurzbericht in die GitHub-Actions-Zusammenfassung (kostenlos)."""
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def _gesperrt(grund: str, d, story, teil, kasse) -> None:
    _summary(f"## ⏸ Keine Produktion am {d}\n\n{story['titel']} – Teil {teil} wäre dran.\n\n"
             f"**Grund:** {grund}\n\n{kasse.stand()}\n\nEs sind keine Kosten entstanden.")
    raise SystemExit(0)


def cmd_produzieren(a) -> None:
    import time
    from csu.kasse import BudgetStopp, Kasse, git_sync
    from csu.common import storyhouse_import
    from csu.voting import decide, fetch_youtube_comments, parse_manual, tally
    storyhouse_import()
    from storyhouse.budget import ApprovalError, BudgetError
    from storyhouse.elevenlabs import ElevenLabsError
    from storyhouse.runway import RunwayError
    t_start = time.time()
    b = budget()
    d = dt.date.fromisoformat(a.datum) if a.datum else dt.date.today()
    slug = slot_for(d)
    story = load_story(slug)
    st = load_state(story)
    teil = st["naechster_teil"]
    kasse = Kasse(float(b.get("monatsbudget_eur") or 0), monat=d.strftime("%Y-%m"))
    run = os.environ.get("GITHUB_RUN_ID") or f"lokal-{int(t_start)}"
    print(f"== {d}: {story['titel']} – Teil {teil} · {kasse.stand()}")

    # 1) Freigaben – fail-closed, VOR jedem kostenpflichtigen Schritt (gesperrt = Erfolg ohne Kosten)
    if not b["paid_rendering_enabled"]:
        _gesperrt("Kostenpflichtige Produktion ist noch nicht freigegeben (paid_rendering_enabled: false).",
                  d, story, teil, kasse)
    if a.geplant and not b["taeglich_aktiv"]:
        _gesperrt("Tägliche Produktion ist noch nicht freigegeben (taeglich_aktiv: false).", d, story, teil, kasse)
    if not a.geplant and a.bestaetigung.strip() != b["approval_phrase"]:
        raise SystemExit("Bestätigungsphrase fehlt oder falsch. Keine Kosten entstanden.")
    if kasse.reserviert > 0:
        raise SystemExit("Es gibt eine offene Reservierung eines früheren Laufs – erst prüfen und mit "
                         "`python -m csu kasse --aufloesen RUN --tatsaechlich EUR` bereinigen. Keine Kosten entstanden.")

    # 2) Zuschauerwahl der Vorfolge (kostenlos)
    wahl_text = resolve_vote(story, st, a.youtube_video_id, a.tiktok_stimmen, decide, fetch_youtube_comments,
                             parse_manual, tally)
    print(wahl_text)
    save_state(st)

    try:
        # 3) Drehbuch (Claude-API, Höchstkosten vorher reserviert)
        if not episode_path(slug, teil).exists():
            if not b["drehbuch_api_aktiv"]:
                _gesperrt(f"Drehbuch Teil {teil} fehlt und drehbuch_api_aktiv ist false.", d, story, teil, kasse)
            from csu.script import generate, max_cost_eur
            kasse.reservieren(run, max_cost_eur(), "Drehbuch (Claude-API, Höchstwert)")
            git_sync(f"Kasse: Reservierung Drehbuch {d}", ["state"])
            res = generate(story, st)
            kasse.buchen(run, "anthropic", res["eur"], None,
                         f"{res['usage'].get('input_tokens')}/{res['usage'].get('output_tokens')} Tokens")
            kasse.aufloesen(run)
        ep = load_episode(slug, teil)
        errs, warns, info = validate_episode(story, ep, st, tuple(production()["video"]["ziel_sekunden"]))
        for w in warns:
            print("Hinweis:", w)
        if errs:
            raise BudgetStopp("Drehbuch ungültig – Abbruch vor Runway/ElevenLabs:\n  " + "\n  ".join(errs))

        # 4) Kosten planen und Höchstbetrag reservieren
        from storyhouse.budget import SpendGuard
        from storyhouse.elevenlabs import ElevenLabsClient, check_subscription
        from storyhouse.runway import RunwayClient
        _, _, _, plan, pricing, cfg, est = _plan_for(slug)
        rw_eur = pricing.credits_to_eur(plan.credits("runway"), cfg, "runway")
        reserve = round(rw_eur * (1 + float(b["safety_margin"])), 2)
        print(f"Runway: {plan.credits('runway'):.0f} Credits ≈ {rw_eur:.2f} € · Reservierung {reserve:.2f} € · "
              f"ElevenLabs: {plan.credits('elevenlabs'):.0f} Credits (im Abo, 0 € zusätzlich)")
        if reserve > float(b["max_pro_video_eur"]):
            raise BudgetStopp(f"Folge würde bis zu {reserve:.2f} € kosten (> max_pro_video_eur).")

        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        g_rw = SpendGuard(limit_eur=reserve, pricing=pricing, cfg=cfg, log_path=out / "ausgaben_runway.json",
                          provider="runway")
        el_cap = pricing.credits_to_eur(plan.credits("elevenlabs"), cfg, "elevenlabs") * 1.3 + 0.5
        g_el = SpendGuard(limit_eur=el_cap, pricing=pricing, cfg=cfg, log_path=out / "ausgaben_elevenlabs.json",
                          provider="elevenlabs")
        rw = RunwayClient(os.environ.get("RUNWAYML_API_SECRET", ""), g_rw)
        el = ElevenLabsClient(os.environ.get("ELEVENLABS_API_KEY", ""), g_el)
        saldo = rw.credit_balance()                                   # kostenlos
        need = plan.credits("runway") + float(b.get("runway_min_restguthaben_credits", 0))
        if saldo is None or saldo < need:
            raise BudgetStopp(f"Runway-Guthaben {saldo} Credits < benötigt {need:.0f}. Kein automatischer Nachkauf – "
                              "bitte Guthaben manuell aufladen (zählt zum Monatsbudget).")
        check_subscription(el.subscription(), plan.credits("elevenlabs"), cfg,
                           needs_music=any(j.kind == "music" for j in plan.jobs))   # kostenlos; Overage verweigert

        kasse.reservieren(run, reserve, f"Folge {slug} Teil {teil} (Runway, Höchstwert)")
        git_sync(f"Kasse: Reservierung {slug} Teil {teil}", ["state"])
    except (BudgetStopp, BudgetError, ApprovalError, RunwayError, ElevenLabsError) as exc:
        kasse.aufloesen(run)
        save_state(st)
        _summary(f"## ⛔ Produktion gestoppt ({d})\n\n{exc}\n\n{kasse.stand()}")
        raise SystemExit(1)

    # 5) Bezahlte Aufträge – jeder einzelne wird VOR dem Senden gegen die Reservierung geprüft
    clients = {"runway": rw, "elevenlabs": el}
    from csu.render import assemble, run_jobs
    ok = False
    try:
        files = run_jobs(plan, clients, out / "roh", ROOT / ".cache" / "auftraege")
        ok = True
    finally:  # tatsächliche Kosten IMMER buchen – auch bei Abbruch
        kasse.buchen(run, "runway", g_rw.spent_eur, plan.credits("runway"), f"{slug} Teil {teil}")
        kasse.buchen(run, "elevenlabs", 0.0, plan.credits("elevenlabs"), "im Abo enthalten")
        kasse.aufloesen(run)
        save_state(st)
        if not ok:
            _summary(f"## ⛔ Produktion abgebrochen ({d})\n\nBezahlte Teilergebnisse liegen im Cache und werden "
                     f"beim nächsten Lauf kostenlos wiederverwendet. Keine automatische Wiederholung.\n\n{kasse.stand()}")

    # neue Referenzbilder/Musik dauerhaft übernehmen (Figuren sehen in allen Folgen gleich aus)
    import shutil
    from csu.common import MUSIC, REFS
    for jid, f in files.items():
        if jid.startswith("REF_") and jid.count("_") == 1:
            dest = REFS / slug / f"{jid[4:]}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
        if jid == "MUSIC_story":
            MUSIC.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, MUSIC / f"{slug}.mp3")
    music = Path(plan.musik_datei) if plan.musik_datei else files.get("MUSIC_story")

    # 6) Schnitt (kostenlos)
    start_werte = json.loads(json.dumps(st["werte"]))
    filename = f"{d}_{slug}_teil-{teil:02d}.mp4"
    result = assemble(story, ep, start_werte, info["ereignisse"], files, music, out, filename)

    # 7) Stand fortschreiben
    wahl = ep["entscheidung"]
    kosten = kasse.run_kosten(run)
    cost = round(sum(kosten.values()), 2)
    st["werte"] = info["endwerte"]
    st["verlauf"].append({"teil": teil, "datum": str(d), "datei": filename, "titel": ep["titel"],
                          "wahl_davor": (st.get("offene_entscheidung") or {}).get("option"),
                          "werte_danach": info["endwerte"], "eur": cost})
    st["offene_entscheidung"] = {"teil": teil, "frage": wahl["frage"], "standard": wahl["standard"],
                                 "optionen": {str(k): v for k, v in wahl["optionen"].items()}, "option": None}
    st["naechster_teil"] = teil + 1
    save_state(st)

    # 8) Produktionsbericht
    tag = f"{d}-{slug}-teil-{teil:02d}"
    repo = os.environ.get("GITHUB_REPOSITORY", "youtubeemo/cartoon-story-universe")
    url = f"https://github.com/{repo}/releases/download/{tag}/{filename}"
    laufzeit = time.time() - t_start
    bericht = "\n".join([
        f"# {story['titel']} – Teil {teil}: {ep['titel']}", "",
        f"**Download (MP4):** {url}", "",
        "| | |", "|---|---|",
        f"| Datum | {d} |", f"| Länge | {result['laenge_s']:.1f} s · 1080×1920 · 30 fps · H.264/AAC |",
        f"| Produktionszeit | {laufzeit / 60:.1f} min |",
        f"| Kosten Runway | {kosten.get('runway', 0):.2f} € ({plan.credits('runway'):.0f} Credits) |",
        f"| Kosten Drehbuch (Claude) | {kosten.get('anthropic', 0):.2f} € |",
        f"| ElevenLabs | {plan.credits('elevenlabs'):.0f} Credits (im Abo, 0 €) |",
        f"| **Kosten gesamt** | **{cost:.2f} €** |",
        f"| Monatsbudget | {kasse.stand()} |", "",
        f"**Zuschauerwahl der Vorfolge:** {wahl_text}", "",
        f"**Neue Frage:** {wahl['frage']}", *[f"- {k}: {v['text']}" for k, v in wahl["optionen"].items()],
        "", *([f"Hinweis: {n}" for n in plan.notes])])
    rep = ROOT / "berichte" / f"{d}_{slug}_teil-{teil:02d}.md"
    rep.parent.mkdir(exist_ok=True)
    rep.write_text(bericht + "\n", encoding="utf-8")
    _summary(bericht)
    write_json(out / "release.json", {"tag": tag, "datei": result["datei"], "dateiname": filename, "url": url,
                                      "titel": f"{story['titel']} – Teil {teil}: {ep['titel']}",
                                      "bericht": str(rep)})
    print(f"✓ Fertig: {filename} ({result['laenge_s']:.1f} s, {cost:.2f} €)")


def cmd_kasse(a) -> None:
    from csu.kasse import Kasse
    k = Kasse(float(budget().get("monatsbudget_eur") or 0), monat=a.monat)
    if a.aufloesen:
        if a.tatsaechlich is None:
            raise SystemExit("--tatsaechlich EUR angeben (Betrag laut Anbieter-Abrechnung)")
        k.buchen(a.aufloesen, "nachbuchung", a.tatsaechlich, None, "manuell nach Abrechnungskontrolle")
        k.aufloesen(a.aufloesen)
    print(k.stand())
    for run, r in k.m["reservierungen"].items():
        print(f"  offen: {run} {r['eur']:.2f} € seit {r['seit']} – {'; '.join(r['zweck'])}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="csu")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("heute"); s.add_argument("--datum")
    sub.add_parser("validate")
    s = sub.add_parser("estimate"); s.add_argument("--geschichte", required=True); s.add_argument("--profil")
    sub.add_parser("kosten")
    s = sub.add_parser("abstimmen"); s.add_argument("--geschichte", required=True)
    s.add_argument("--youtube-video-id"); s.add_argument("--manuell", help="z. B. 1=34,2=12,3=8")
    s = sub.add_parser("produzieren"); s.add_argument("--datum"); s.add_argument("--bestaetigung", default="")
    s.add_argument("--geplant", action="store_true", help="vom täglichen Zeitplan gestartet")
    s.add_argument("--youtube-video-id"); s.add_argument("--tiktok-stimmen")
    s.add_argument("--out", default="ausgabe")
    s = sub.add_parser("kasse"); s.add_argument("--monat"); s.add_argument("--aufloesen", metavar="RUN")
    s.add_argument("--tatsaechlich", type=float)
    a = p.parse_args(argv)
    {"heute": cmd_heute, "validate": cmd_validate, "estimate": cmd_estimate, "kosten": cmd_kosten,
     "abstimmen": cmd_abstimmen, "produzieren": cmd_produzieren, "kasse": cmd_kasse}[a.cmd](a)
