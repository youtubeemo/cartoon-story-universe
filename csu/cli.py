"""Befehle:  python -m csu <befehl>

  heute        Welche Geschichte/welcher Teil ist heute dran?           (kostenlos)
  validate     Alle Geschichten + vorhandenen Folgen prüfen             (kostenlos)
  estimate     Kosten einer Folge aus dem echten Auftragsplan           (kostenlos)
  kosten       Hochrechnung pro Video und Monat                         (kostenlos)
  abstimmen    Zuschauerwahl auswerten und speichern                    (kostenlos)
  produzieren  Tageslauf: Wahl → Drehbuch → Prüfung → Render → MP4      (KOSTENPFLICHTIG, nur nach Freigabe)
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
LEDGER = STATE / "kosten.json"


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
def cmd_produzieren(a) -> None:
    from csu.voting import decide, fetch_youtube_comments, parse_manual, tally
    b = budget()
    d = dt.date.fromisoformat(a.datum) if a.datum else dt.date.today()
    slug = slot_for(d)
    story = load_story(slug)
    st = load_state(story)
    teil = st["naechster_teil"]
    print(f"== {d}: {story['titel']} – Teil {teil}")

    # Freigaben (fail-closed) – VOR jedem kostenpflichtigen Schritt
    if not b["paid_rendering_enabled"]:
        raise SystemExit("Gesperrt: paid_rendering_enabled ist false (config/budget.yaml). Keine Kosten entstanden.")
    if a.geplant and not b["taeglich_aktiv"]:
        raise SystemExit("Gesperrt: taeglich_aktiv ist false. Keine Kosten entstanden.")
    if not a.geplant and a.bestaetigung.strip() != b["approval_phrase"]:
        raise SystemExit("Bestätigungsphrase fehlt oder falsch. Keine Kosten entstanden.")

    print(resolve_vote(story, st, a.youtube_video_id, a.tiktok_stimmen, decide, fetch_youtube_comments,
                       parse_manual, tally))
    if not episode_path(slug, teil).exists():
        if not b["drehbuch_api_aktiv"]:
            raise SystemExit(f"Drehbuch Teil {teil} fehlt und drehbuch_api_aktiv ist false.")
        from csu.script import generate
        generate(story, st)
    ep = load_episode(slug, teil)
    errs, warns, info = validate_episode(story, ep, st, tuple(production()["video"]["ziel_sekunden"]))
    for w in warns:
        print("Hinweis:", w)
    if errs:
        save_state(st)  # Abstimmungsergebnis behalten
        raise SystemExit("Drehbuch ungültig – Abbruch vor Runway/ElevenLabs:\n  " + "\n  ".join(errs))

    _, _, _, plan, pricing, cfg, est = _plan_for(slug)
    monat = d.strftime("%Y-%m")
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    spent = float(ledger.get(monat, {}).get("eur", 0))
    limit_m = float(b.get("monatsbudget_eur") or 0)
    print(f"Schätzung: {est['eur']:.2f} € (mit Puffer {est['eur_mit_puffer']:.2f} €) · Monat bisher {spent:.2f} € von {limit_m:.2f} €")
    if est["eur_mit_puffer"] > float(b["max_pro_video_eur"]):
        raise SystemExit("Schätzung über max_pro_video_eur – Abbruch, keine Kosten entstanden.")
    if spent + est["eur_mit_puffer"] > limit_m:
        raise SystemExit("Monatsbudget würde überschritten – Abbruch, keine Kosten entstanden.")

    from storyhouse.budget import SpendGuard
    from storyhouse.elevenlabs import ElevenLabsClient, check_subscription
    from storyhouse.runway import RunwayClient
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    g_rw = SpendGuard(limit_eur=float(b["max_pro_video_eur"]), pricing=pricing, cfg=cfg,
                      log_path=out / "ausgaben_runway.json", provider="runway")
    g_el = SpendGuard(limit_eur=float(b["max_pro_video_eur"]), pricing=pricing, cfg=cfg,
                      log_path=out / "ausgaben_elevenlabs.json", provider="elevenlabs")
    g_rw.link(g_el)
    el = ElevenLabsClient(os.environ.get("ELEVENLABS_API_KEY", ""), g_el)
    check_subscription(el.subscription(), plan.credits("elevenlabs"), cfg,
                       needs_music=any(j.kind == "music" for j in plan.jobs))   # kostenlos, fail-closed
    clients = {"runway": RunwayClient(os.environ.get("RUNWAYML_API_SECRET", ""), g_rw), "elevenlabs": el}

    from csu.render import assemble, run_jobs
    try:
        files = run_jobs(plan, clients, out / "roh", ROOT / ".cache" / "auftraege")
    finally:  # Ausgaben IMMER verbuchen, auch bei Abbruch
        cost = round(g_rw.spent_eur + g_el.spent_eur, 2)
        ledger.setdefault(monat, {"eur": 0.0, "videos": []})
        ledger[monat]["eur"] = round(ledger[monat]["eur"] + cost, 2)
        ledger[monat]["videos"].append({"datum": str(d), "geschichte": slug, "teil": teil, "eur": cost})
        write_json(LEDGER, ledger)
        save_state(st)

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
    music = Path(plan.musik_datei) if plan.musik_datei else (files.get("MUSIC_story"))

    start_werte = json.loads(json.dumps(st["werte"]))
    events = info["ereignisse"]
    filename = f"{d}_{slug}_teil-{teil:02d}.mp4"
    result = assemble(story, ep, start_werte, events, files, music, out, filename)

    # Stand fortschreiben
    wahl = ep["entscheidung"]
    st["werte"] = info["endwerte"]
    st["verlauf"].append({"teil": teil, "datum": str(d), "datei": filename, "titel": ep["titel"],
                          "wahl_davor": (st.get("offene_entscheidung") or {}).get("option"),
                          "werte_danach": info["endwerte"], "eur": cost})
    st["offene_entscheidung"] = {"teil": teil, "frage": wahl["frage"], "standard": wahl["standard"],
                                 "optionen": {str(k): v for k, v in wahl["optionen"].items()}, "option": None}
    st["naechster_teil"] = teil + 1
    save_state(st)
    write_json(out / "release.json", {
        "tag": f"{d}-{slug}-teil-{teil:02d}", "datei": result["datei"], "dateiname": filename,
        "titel": f"{story['titel']} – Teil {teil}: {ep['titel']}",
        "notiz": f"{story['titel']} · Teil {teil}/{story['teile']} · {result['laenge_s']:.0f} s · Kosten {cost:.2f} €\n\n"
                 f"Frage: {wahl['frage']}\n" + "\n".join(f"{k}: {v['text']}" for k, v in wahl["optionen"].items())})
    print(f"✓ Fertig: {filename} ({result['laenge_s']:.1f} s, {cost:.2f} €)")


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
    a = p.parse_args(argv)
    {"heute": cmd_heute, "validate": cmd_validate, "estimate": cmd_estimate, "kosten": cmd_kosten,
     "abstimmen": cmd_abstimmen, "produzieren": cmd_produzieren}[a.cmd](a)
