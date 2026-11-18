"""Befehle:  python -m csu <befehl>

  heute        Welche Geschichte/welcher Teil ist heute dran?                          (kostenlos)
  validate     Story-Bibeln + Storyboards prüfen (Format, Logik, Übergänge, Rechnung)   (kostenlos)
  estimate     Kosten einer Folge aus dem echten Auftragsplan                          (kostenlos)
  kosten       Hochrechnung pro Folge und Monat je Qualitätsprofil                     (kostenlos)
  abstimmen    Zuschauerwahl auswerten und speichern                                   (kostenlos)
  kasse        Monatsbudget, Reservierungen, Nachbuchung                               (kostenlos)
  pruefen      Betriebsprüfung (Inhalte, Kasse, Schnitt mit Platzhaltern, API-Lesezugriffe) (kostenlos)
  freigeben    Vorlagen oder Storyboard nach Sichtung freigeben                        (kostenlos)
  produzieren  --phase vorlagen | storyboard | animation | auto                        (KOSTENPFLICHTIG)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

from csu.common import (ROOT, STATE, budget, episode_path, load_episode, load_story, production, story_slugs,
                        write_json)
from csu.state import load_state, save_state
from csu.validate import validate_episode, validate_story

SLOT_FILE = STATE / "wochenplan.json"


def _summary(text: str) -> None:
    print(text)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


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
        nxt = next((q for q in queue if q not in set(slots.values())), None)
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
          f" von {story['teile']}; Storyboard {'vorhanden' if episode_path(slug, st['naechster_teil']).exists() else 'fehlt'}")


def cmd_validate(a) -> None:
    errors = 0
    for slug in story_slugs():
        story = load_story(slug)
        errs = validate_story(story)
        st = load_state(story)
        ep = load_episode(slug, st["naechster_teil"])
        info = {}
        if ep:
            e2, _, info = validate_episode(story, ep, st, tuple(production()["video"]["ziel_sekunden"]))
            errs += e2
        extra = f" · Teil {st['naechster_teil']}: {info.get('laenge_s')} s, {info.get('szenen')} Szenen" if ep else ""
        print(f"{'✗' if errs else '✓'} {slug}{extra}")
        for e in errs:
            print(f"   FEHLER: {e}")
        errors += len(errs)
    if errors:
        sys.exit(1)


# ---------------------------------------------------------------- Kosten
def _kosten_folge(slug: str, profil: str | None = None) -> dict:
    from csu.plan import Pricing, budget_config, build_plan, estimate
    story = load_story(slug)
    ep = load_episode(slug, 1)
    pricing = Pricing.load(ROOT / "config" / "pricing.yaml")
    cfg = budget_config()
    sb = build_plan(story, ep, pricing, profil, phase="storyboard", schaetzung=True)
    an = build_plan(story, ep, pricing, profil, phase="animation", schaetzung=True)
    e_sb, e_an = estimate(sb, pricing, cfg), estimate(an, pricing, cfg)
    return {"profil": an.profil, "storyboard_credits": e_sb["runway_credits"], "storyboard_eur": e_sb["runway_eur"],
            "animation_credits": e_an["runway_credits"], "animation_eur": e_an["runway_eur"],
            "runway_eur_folge": round(e_sb["runway_eur"] + e_an["runway_eur"], 2),
            "elevenlabs_credits": e_an["elevenlabs_credits"]}


def cmd_estimate(a) -> None:
    print(json.dumps(_kosten_folge(a.geschichte, a.profil), indent=2, ensure_ascii=False))


def cmd_kosten(a) -> None:
    from csu.script import max_cost_eur
    from csu.vision import max_cost_eur as vision_eur
    limit = float(budget().get("monatsbudget_eur") or 0)
    ki = max_cost_eur() * 0.5 + vision_eur() * 0.5   # typischer Verbrauch ≈ Hälfte des reservierten Höchstwerts
    print("| Profil | Runway-Credits/Folge | Runway €/Folge | + Claude ≈ | Summe €/Folge | Folgen mit "
          f"{limit:.0f} €/Monat |")
    print("|---|---:|---:|---:|---:|---:|")
    for profil in ("qualitaet", "final", "test"):
        k = _kosten_folge("die-letzten-10000", profil)
        summe = k["runway_eur_folge"] + ki
        cr = k["storyboard_credits"] + k["animation_credits"]
        print(f"| {profil} | {cr} | {k['runway_eur_folge']:.2f} € | {ki:.2f} € | {summe:.2f} € | "
              f"{int(limit // summe) if summe else 0} |")


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
    counts, quelle = Counter(), []
    yt_id = yt_id or wahl.get("youtube_video_id")
    key = os.environ.get("YOUTUBE_API_KEY")
    if yt_id and key:
        try:
            counts += tally(fetch(yt_id, key), {os.environ.get("YOUTUBE_CHANNEL_ID", "")})
            quelle.append("YouTube")
        except Exception as exc:  # noqa: BLE001 – nicht zuverlässig abrufbar → Standardoption
            quelle.append(f"YouTube nicht abrufbar ({type(exc).__name__})")
    if manual:
        counts += parse_manual(manual)
        quelle.append("TikTok (manuell)")
    option, grund = decide(counts, int(wahl["standard"]), int(budget().get("min_stimmen", 5)))
    wahl.update({"option": option, "effekte": wahl["optionen"][str(option)]["effekte"],
                 "stimmen": {str(k): counts[k] for k in (1, 2, 3)}, "grund": grund, "quellen": quelle})
    return f"Entscheidung Teil {st['naechster_teil'] - 1}: Option {option} – {grund}"


# ---------------------------------------------------------------- Produktion, Freigabe, Kasse, Prüfung
def cmd_produzieren(a) -> None:
    from csu import produktion
    if a.phase == "vorlagen" and not a.geschichte:
        raise SystemExit("--geschichte angeben")
    {"vorlagen": produktion.vorlagen, "storyboard": produktion.storyboard, "animation": produktion.animation,
     "auto": produktion.auto}[a.phase](a)


def cmd_freigeben(a) -> None:
    from csu.common import REFS
    from csu.freigabe import freigeben, storyboard_ordner
    story = load_story(a.geschichte)
    if a.was == "vorlagen":
        names = freigeben(REFS / story["slug"], a.nur, a.notiz or "")
    else:
        teil = a.teil or load_state(story)["naechster_teil"]
        names = freigeben(storyboard_ordner(story["slug"], teil), a.nur, a.notiz or "")
    print(f"Freigegeben ({a.was}, {story['titel']}): {', '.join(names)}")


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


def cmd_pruefen(a) -> None:
    from csu.check import api_pruefung, schnitt_pruefung
    from csu.kasse import Kasse
    b = budget()
    z: list[tuple[bool, str]] = []
    k = Kasse(float(b.get("monatsbudget_eur") or 0))
    z.append((k.reserviert == 0 and k.limit == 150, f"Kasse: {k.stand()}"))
    kf = _kosten_folge("die-letzten-10000")
    z.append((kf["runway_eur_folge"] * (1 + float(b["safety_margin"])) <= float(b["max_pro_video_eur"]),
              f"Referenzfolge ({kf['profil']}): Runway ≈ {kf['runway_eur_folge']:.2f} €/Folge"))
    if a.schnitt:
        q = schnitt_pruefung()
        z.append((q["ok"], f"Schnitt + QC mit Platzhaltern: {q['detail']}"))
    if a.apis:
        z += api_pruefung(kf["storyboard_credits"] + kf["animation_credits"], 61000)
    _summary("## Betriebsprüfung (kostenlos)\n\n" + "\n".join(f"- {'✅' if o else '❌'} {t}" for o, t in z))
    if not all(o for o, _ in z):
        raise SystemExit(1)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="csu")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("heute"); s.add_argument("--datum")
    sub.add_parser("validate")
    s = sub.add_parser("estimate"); s.add_argument("--geschichte", required=True); s.add_argument("--profil")
    sub.add_parser("kosten")
    s = sub.add_parser("abstimmen"); s.add_argument("--geschichte", required=True)
    s.add_argument("--youtube-video-id"); s.add_argument("--manuell", help="z. B. 1=34,2=12,3=8")
    s = sub.add_parser("produzieren")
    s.add_argument("--phase", choices=["vorlagen", "storyboard", "animation", "auto"], required=True)
    s.add_argument("--geschichte"); s.add_argument("--datum"); s.add_argument("--bestaetigung", default="")
    s.add_argument("--geplant", action="store_true", help="vom täglichen Zeitplan gestartet")
    s.add_argument("--youtube-video-id"); s.add_argument("--tiktok-stimmen"); s.add_argument("--out", default="ausgabe")
    s = sub.add_parser("freigeben"); s.add_argument("was", choices=["vorlagen", "storyboard"])
    s.add_argument("--geschichte", required=True); s.add_argument("--teil", type=int)
    s.add_argument("--nur", nargs="*"); s.add_argument("--notiz")
    s = sub.add_parser("kasse"); s.add_argument("--monat"); s.add_argument("--aufloesen", metavar="RUN")
    s.add_argument("--tatsaechlich", type=float)
    s = sub.add_parser("pruefen"); s.add_argument("--schnitt", action="store_true")
    s.add_argument("--apis", action="store_true")
    a = p.parse_args(argv)
    {"heute": cmd_heute, "validate": cmd_validate, "estimate": cmd_estimate, "kosten": cmd_kosten,
     "abstimmen": cmd_abstimmen, "produzieren": cmd_produzieren, "freigeben": cmd_freigeben, "kasse": cmd_kasse,
     "pruefen": cmd_pruefen}[a.cmd](a)
