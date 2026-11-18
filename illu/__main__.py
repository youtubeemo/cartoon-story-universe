"""Weg 1 – illustrierte Folgen.

    python -m illu pruefen SLUG TEIL                 # Storyboard v4 prüfen + Kosten (kostenlos)
    python -m illu muster  SLUG TEIL --out DIR       # Ablauf mit Platzhalterbildern/-stimmen (kostenlos, lokal)
    python -m illu bilder  SLUG TEIL --out DIR --bestaetigung "…" [--nur s01,s02]
                                                     # KOSTENPFLICHTIG (Runway) – nur nach Freigabe im Chat
    python -m illu folge   SLUG TEIL --out DIR [--stimmen elevenlabs --credit-grenze N]
                                                     # Schnitt nur aus QC-freigegebenen Bildern (ElevenLabs im Abo)
    python -m illu qc      SLUG TEIL --out DIR       # lokale Prüfung + Prüfbögen (kostenlos)
    python -m illu urteil  SLUG DATEI ok|fehler|vorbehalt --grund "…"   # manuelles Urteil (protokolliert)
    python -m illu retusche SLUG                     # kostenlose Retusche nach stories/SLUG/retusche.yaml

Bilder entstehen in zwei Phasen: erst Referenzen (--nur-referenzen), dann – nach QC und Eintrag in
stories/SLUG/referenzen.yaml – die Shots. Shots mit nicht freigegebenen Referenzen werden verweigert.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import textwrap
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from csu.common import load_story
from csu.state import load_state
from illu import plan as bplan
from illu import qc
from illu import render
from illu.storyboard import laden, pruefen, stil

ROOT = Path(__file__).resolve().parent.parent


def _start(story: dict, teil: int) -> dict:
    zustand = load_state(story)
    if teil != zustand["naechster_teil"]:
        print(f"Hinweis: gespeicherter Stand ist vor Teil {zustand['naechster_teil']} – Prüfung mit diesem Stand.")
    return zustand["werte"]


def _sprechtext(s: dict) -> str:
    return " ".join(s.get("text", "").replace("*", "").split())


def vertonen(story: dict, sb: dict, ordner: Path, modus: str, credit_grenze: int) -> dict[str, dict]:
    from toon import ton
    ordner.mkdir(parents=True, exist_ok=True)
    budget = ton.CreditBudget(credit_grenze)
    out: dict[str, dict] = {}
    if modus == "elevenlabs":
        bedarf = sum(ton.el_credits(_sprechtext(s)) for s in sb["shots"])
        if bedarf > credit_grenze:
            raise SystemExit(f"Folge braucht ~{bedarf} Credits > Grenze {credit_grenze} – nichts ausgegeben.")
        print("ElevenLabs:", ton.el_vorpruefung(bedarf))
    for s in sb["shots"]:
        text = _sprechtext(s)
        if not text:
            continue
        sp = s.get("sprecher", "erzaehler")
        wav = ordner / f"{s['id']}.wav"
        if modus == "elevenlabs":
            voice = ton.el_stimme_fuer(None, None) if sp == "erzaehler" else story["figuren"][sp]["voice"]
            tag = ton.EMOTION.get(s.get("emotion", ""), "")
            out[s["id"]] = ton.elevenlabs(f"{tag} {text}".strip(), voice, wav, budget)
        else:
            fpfad = ROOT / "toon" / "figuren" / f"{sp}.yaml"
            cfg = yaml.safe_load(fpfad.read_text(encoding="utf-8"))["stimme"] if fpfad.exists() else ton.ERZAEHLER_PIPER
            out[s["id"]] = ton.stimme(text, cfg, wav, platzhalter=(modus == "platzhalter"))
    print(f"Stimmen: {len(out)} Zeilen, ElevenLabs {budget.verbraucht} Credits neu, {budget.wiederverwendet} aus Archiv")
    return out


def platzhalterbilder(story: dict, sb: dict, ordner: Path) -> dict[str, Path]:
    """Graue Layout-Bilder (keine Illustration!) – nur um Kamera, Anzeigen und Untertitel zu prüfen."""
    ordner.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    farben = {}
    for s in sb["shots"]:
        if s.get("bild_von"):
            out[s["id"]] = out[s["bild_von"]]
            continue
        c = farben.setdefault(s["ort"], [(60, 70, 96), (88, 64, 72), (54, 86, 74), (90, 80, 52)][len(farben) % 4])
        im = Image.new("RGB", (1080, 1920), c)
        d = ImageDraw.Draw(im)
        for y in range(0, 1920, 120):
            d.line((0, y, 1080, y), fill=tuple(min(255, v + 14) for v in c), width=2)
        fx, fy = s.get("fokus", [0.5, 0.45])
        d.ellipse((fx * 1080 - 40, fy * 1920 - 40, fx * 1080 + 40, fy * 1920 + 40), outline=(255, 255, 255), width=6)
        txt = f"PLATZHALTER {s['id']} · {s['ort']} · {', '.join(s.get('figuren') or []) or '–'}\n\n" + \
              "\n".join(textwrap.wrap(s["bild"], 38))
        d.multiline_text((60, 360), txt, fill=(235, 235, 235), font=render._font("assets/fonts/Baloo2.ttf", 40))
        out[s["id"]] = ordner / f"{s['id']}.png"
        im.save(out[s["id"]])
    return out


def _bilder_vorhanden(story: dict, sb: dict) -> dict[str, Path]:
    auftr = bplan.auftraege(story, sb)
    fehlt = [a.id for a in auftr if a.id.startswith("IMG_") and not a.datei.exists()]
    if fehlt:
        raise SystemExit(f"Es fehlen {len(fehlt)} Bilder ({', '.join(fehlt[:5])} …) – erst „bilder“ (kostenpflichtig).")
    bilder = bplan.bild_fuer(sb, auftr)
    gesperrt = qc.sperren_fehlende(story, sb, {k: v for k, v in bilder.items()})
    if gesperrt:
        raise SystemExit("⛔ Nicht freigegebene Bilder – keine Folge:\n  " + "\n  ".join(gesperrt))
    return bilder


def _refs_fuer(auftr) -> dict[str, Path]:
    return {x.id[4:]: x.datei for x in auftr if x.id.startswith("REF_")}


def cmd_qc(a) -> int:
    story, sb = load_story(a.slug), laden(a.slug, a.teil)
    auftr = bplan.auftraege(story, sb)
    refs = _refs_fuer(auftr)
    bilder = {sid: p for sid, p in bplan.bild_fuer(sb, auftr).items() if p.exists()}
    lok = qc.lokal(bilder)
    shots = {s["id"]: s for s in sb["shots"]}
    for sid, p in bilder.items():
        if lok[sid]:
            qc.setzen(a.slug, p, "fehler", lok[sid], "lokal")
        qc.pruefbogen(story, shots[sid], p, refs, Path(a.out) / f"pruefbogen_{sid}.jpg")
    for tag, p in refs.items():
        print(f"Referenz {tag:10s} {p.name:32s} {'fest' if tag in bplan.freigegebene_referenzen(a.slug) else '–':5s} "
              f"{qc.status(a.slug, p)['status'] if p.exists() else 'fehlt'}")
    for s in sb["shots"]:
        p = bplan.bild_fuer(sb, auftr)[s["id"]]
        print(f"Shot {s['id']:5s} {p.name:32s} {qc.status(a.slug, p)['status'] if p.exists() else 'fehlt'}")
    print(f"Prüfbögen: {a.out}")
    return 0


def cmd_urteil(a) -> int:
    p = bplan.ARCHIV / a.slug / a.datei
    if not p.exists():
        raise SystemExit(f"{p} fehlt")
    qc.setzen(a.slug, p, {"ok": "manuell_ok"}.get(a.urteil, a.urteil), [a.grund] if a.grund else [],
              f"manuell ({a.wer})")
    print(p.name, "→", qc.status(a.slug, p))
    return 0


def cmd_retusche(a) -> int:
    from illu.retusche import anwenden
    for p in anwenden(a.slug):
        print("✓", p.relative_to(ROOT), "(Status: ungeprüft – erst QC/Urteil)")
    return 0


def cmd_pruefen(a) -> int:
    story, sb = load_story(a.slug), laden(a.slug, a.teil)
    fehler = pruefen(story, sb, _start(story, a.teil)) + bplan.pruefe_auftraege(bplan.auftraege(story, sb))
    for f in fehler:
        print("✗", f)
    k = bplan.kosten(bplan.auftraege(story, sb))
    print(f"{len(sb['shots'])} Shots · offene Bilder {k['bilder']} (Referenzen {k['referenzen']}, Shots {k['shots']}) "
          f"· {k['credits']} Credits ≈ {k['eur']:.2f} € inkl. USt (Reservierung {k['eur_reserve']:.2f} €)")
    print("OK" if not fehler else f"{len(fehler)} Fehler")
    return 1 if fehler else 0


def _schneiden(story, sb, bilder, ton_info, out: Path, name: str) -> Path:
    tl = render.zeitleiste(story, sb, _start(story, sb["teil"]), bilder, ton_info)
    wav = render.tonspur(tl, out / "ton.wav", story.get("stimmung", "spannend"))
    mp4 = render.video(tl, wav, out / name)
    for t in (0.5, tl["dauer"] * 0.3, tl["dauer"] - 1.0):
        render.standbild(tl, t, out / f"bild_{t:05.1f}s.png")
    print(f"✓ {mp4} ({tl['dauer']:.1f} s, {len(tl['shots'])} Shots)")
    return mp4


def cmd_muster(a) -> int:
    if cmd_pruefen(a):
        return 1
    story, sb = load_story(a.slug), laden(a.slug, a.teil)
    out = Path(a.out)
    bilder = platzhalterbilder(story, sb, out / "platzhalter")
    ton_info = vertonen(story, sb, out / "stimmen", "platzhalter", 0)
    _schneiden(story, sb, bilder, ton_info, out, f"MUSTER_{a.slug}_teil{a.teil:02d}.mp4")
    return 0


def cmd_folge(a) -> int:
    if cmd_pruefen(a):
        return 1
    story, sb = load_story(a.slug), laden(a.slug, a.teil)
    out = Path(a.out)
    bilder = _bilder_vorhanden(story, sb)
    ton_info = vertonen(story, sb, out / "stimmen", a.stimmen, a.credit_grenze)
    titel = re.sub(r"[^A-Za-z0-9äöüÄÖÜß-]+", "-", sb.get("titel", "")).strip("-")
    _schneiden(story, sb, bilder, ton_info, out, f"{a.slug}_teil{a.teil:02d}_{titel}.mp4")
    return 0


def cmd_bilder(a) -> int:
    """KOSTENPFLICHTIG. Gleicher Rahmen wie die alte Pipeline: Freigabephrase, Kasse (Reservierung vorab),
    SpendGuard je Aufruf, Guthabenprüfung, keine automatischen Wiederholungen, Archiv statt Doppelzahlung."""
    st = stil()
    if not st.get("aktiv"):
        print("⏸ Bilderzeugung Weg 1 ist nicht freigegeben (config/illustration.yaml › aktiv: false). Keine Kosten.")
        return 0
    if cmd_pruefen(a):
        return 1
    from csu.produktion import STOPP, Lauf
    from csu.plan import EpisodePlan
    from csu.render import run_jobs
    from storyhouse.plan import Job

    story, sb = load_story(a.slug), laden(a.slug, a.teil)
    auftr = bplan.auftraege(story, sb, st)
    if a.nur:
        wahl = {f"IMG_{x.strip()}" for x in a.nur.split(",")}
        if not wahl <= {x.id for x in auftr}:
            raise SystemExit(f"Unbekannte Shots in --nur: {a.nur}")
        noetig = {r for x in auftr if x.id in wahl for r in x.refs}
        auftr = [x for x in auftr if x.id in wahl or x.id in noetig]
    if a.nur_referenzen:
        auftr = [x for x in auftr if x.id.startswith("REF_")]
    nicht_frei = sorted({r for x in auftr if x.id.startswith("IMG_") and not x.datei.exists()
                         for r in x.refs if not next(y for y in auftr if y.id == r).fest})
    nicht_frei += sorted({f"{x.id} (QC: {qc.status(a.slug, x.datei)['status']})" for x in auftr
                          if x.fest and qc.status(a.slug, x.datei)["status"] not in qc.OK})
    if nicht_frei:
        print(f"⛔ Shots brauchen freigegebene Referenzen ({', '.join(nicht_frei)}) – erst --nur-referenzen, "
              "dann QC und Eintrag in referenzen.yaml. Nichts gesendet, keine Kosten.")
        return 1
    lauf = Lauf(a, "illu-bilder")
    lauf.gate("Weg-1-Bilder")
    p = EpisodePlan(slug=a.slug, teil=a.teil, profil="illu", phase="bilder")
    modell = st["bildmodell"]
    credits = lauf.pricing.image_credits(modell)
    for x in auftr:
        if x.datei.exists():
            p.frozen_refs[x.id] = str(x.datei)
            continue
        payload = {"model": modell, "ratio": st["format"], "seed": x.seed, "promptText": x.prompt[:1000]}
        if x.refs:
            payload["referenceImages"] = [{"uri": f"{{{{out:{r}}}}}", "tag": r[4:]} for r in x.refs]
        p.jobs.append(Job(id=x.id, kind="image", model=modell, ext="png", credits=credits,
                          depends=[r for r in x.refs if r not in p.frozen_refs], payload=payload))
    if not p.jobs:
        print("Alle Bilder liegen schon im Archiv – 0 €.")
        return 0
    ki = bool(st["qc"]["ki_pruefung"]) and bool(os.environ.get("ANTHROPIC_API_KEY"))
    ki_eur = qc.ki_kosten_eur(len(p.jobs)) if ki else 0.0
    eur = p.eur(lauf.pricing, lauf.cfg) + ki_eur
    print(f"{len(p.jobs)} Bilder, {p.credits('runway'):.0f} Credits + KI-Prüfung {ki_eur:.2f} € = bis zu {eur:.2f} € "
          f"(Obergrenze {a.max_eur:.2f} €)")
    if eur > a.max_eur + 1e-9:
        print(f"⛔ {eur:.2f} € > freigegebene {a.max_eur:.2f} € – nichts gesendet, keine Kosten.")
        return 1
    try:
        lauf.reservieren(a.max_eur, f"Weg-1-Bilder {a.slug} {a.teil}")
        clients = lauf.clients(p.credits("runway"), 0, False, a.max_eur - ki_eur)   # SpendGuard: harte Grenze
        # Zwischenspeicher im Archivordner: wird vom Workflow immer committet → bezahlte Bilder gehen nie verloren
        files = run_jobs(p, clients, Path(a.out) / "roh", bplan.ARCHIV / a.slug / "cache")
    except STOPP as exc:
        lauf.stopp(exc)
    except Exception:                       # unerwarteter Fehler: bisher Ausgegebenes trotzdem buchen
        if getattr(lauf, "guards", None):
            lauf.kasse.buchen(lauf.run, "runway", lauf.guards[0].spent_eur, None, "Abbruch (unerwarteter Fehler)")
            lauf.kasse.aufloesen(lauf.run)
        raise
    for x in auftr:
        if x.id in files and not x.datei.exists():
            x.datei.parent.mkdir(parents=True, exist_ok=True)
            x.datei.write_bytes(Path(files[x.id]).read_bytes())
    # Qualitätskontrolle: lokal immer, KI nur wenn eingeplant. Ohne Bestehen bleibt jedes Bild gesperrt.
    erzeugt = {j.id for j in p.jobs}
    neu = {x.id: x for x in auftr if x.id in erzeugt and x.id in files}
    lok = qc.lokal({k: v.datei for k, v in neu.items()})
    refs = _refs_fuer(bplan.auftraege(story, sb, st))
    shots = {s["id"]: s for s in sb["shots"]}
    usage_in = usage_out = 0
    for jid, x in neu.items():
        if lok[jid]:
            qc.setzen(a.slug, x.datei, "fehler", lok[jid], "lokal")
            continue
        if not ki:
            qc.setzen(a.slug, x.datei, "ungeprueft", ["KI-Prüfung nicht gelaufen – manuelles Urteil nötig"], "lokal")
            continue
        if jid.startswith("REF_"):
            tag = jid[4:]
            shot = {"id": jid, "figuren": [tag] if tag in story["figuren"] else [],
                    "bild": "single character reference sheet" if tag in story["figuren"] else "empty location"}
            ok, gruende, u = qc.ki_pruefen(story, shot, x.datei, {})
        else:
            ok, gruende, u = qc.ki_pruefen(story, shots[jid[4:]], x.datei, refs)
        usage_in, usage_out = usage_in + u.get("input_tokens", 0), usage_out + u.get("output_tokens", 0)
        qc.setzen(a.slug, x.datei, "ok" if ok else "fehler", gruende, "ki")
        print(f"QC {jid}: {'ok' if ok else 'FEHLER – ' + '; '.join(gruende[:3])}")
    lauf.buchen(f"Weg-1-Bilder {a.slug} {a.teil}", p.credits("runway"), 0)
    if ki:
        from csu.produktion import _anthropic_eur
        lauf.kasse.buchen(lauf.run, "anthropic", _anthropic_eur({"input_tokens": usage_in,
                                                                 "output_tokens": usage_out}), None, "KI-Bildprüfung")
    print(f"✓ Bilder unter {bplan.ARCHIV / a.slug} · {lauf.kasse.stand()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m illu")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pruefen", "muster", "bilder", "folge", "qc"):
        s = sub.add_parser(name)
        s.add_argument("slug")
        s.add_argument("teil", type=int)
        s.add_argument("--out", default="out/illu")
        if name == "bilder":
            s.add_argument("--bestaetigung", default="")
            s.add_argument("--nur", default="")
            s.add_argument("--max-eur", type=float, required=True)
            s.add_argument("--nur-referenzen", action="store_true")
            s.add_argument("--datum", default="")
            s.add_argument("--geplant", action="store_true")
        if name == "folge":
            s.add_argument("--stimmen", choices=["platzhalter", "piper", "elevenlabs"], default="piper")
            s.add_argument("--credit-grenze", type=int, default=0)
    u = sub.add_parser("urteil")
    u.add_argument("slug")
    u.add_argument("datei")
    u.add_argument("urteil", choices=["ok", "fehler", "vorbehalt"])
    u.add_argument("--grund", default="")
    u.add_argument("--wer", default="Mensch")
    r = sub.add_parser("retusche")
    r.add_argument("slug")
    a = ap.parse_args(argv)
    return {"pruefen": cmd_pruefen, "muster": cmd_muster, "bilder": cmd_bilder, "folge": cmd_folge, "qc": cmd_qc,
            "urteil": cmd_urteil, "retusche": cmd_retusche}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
