"""Kostenlose Tests der 2D-Rig-Pipeline (kein Ton, kein Video – nur Logik und ein Standbild)."""
from pathlib import Path

import yaml

from toon import render, szene
from toon.anim import Spur

SB = yaml.safe_load((Path(__file__).resolve().parent.parent / "probe" / "animationsprobe2.yaml").read_text())


def _fake_ton(sprecher, text, key, emotion=None):
    d = len(text) / 14
    return Path("/dev/null"), d, [(0.0, d / 2, "C"), (d / 2, d, "B")]


def test_probe_storyboard_gueltig():
    assert szene.pruefen(SB) == []


def test_logikfehler_werden_erkannt():
    sb = yaml.safe_load(yaml.safe_dump(SB))
    sb["einstellungen"][1]["kamera"] = "nah"                       # nah mit zwei Figuren im Fokus
    sb["einstellungen"][2]["figuren"]["jonas"] = {"x": 1200}         # Figur springt ohne Gang
    sb["einstellungen"][0]["ablauf"][4]["steht_auf"] = False         # geht los/gibt, obwohl sitzend …
    sb["einstellungen"][2]["ablauf"][3]["setzt_sich"] = "sofa"       # Sitz gibt es nicht
    errs = szene.pruefen(sb)
    assert any("nah" in e for e in errs) and any("springt" in e for e in errs)
    assert any("Sitz" in e for e in errs)


def test_uebergabe_nur_was_man_haelt():
    sb = yaml.safe_load(yaml.safe_dump(SB))
    sb["einstellungen"][1]["ablauf"][1]["gibt"]["requisit"] = "brief"
    assert any("gibt brief" in e for e in szene.pruefen(sb))


def test_zeitleiste_positionen_und_uebergabe():
    tl = szene.zeitleiste(SB, _fake_ton)
    e1, e2, e3 = tl["einstellungen"]
    assert e1.ende == e2.start and e2.ende == e3.start
    grell, jonas = tl["spuren"]["grell"], tl["spuren"]["jonas"]
    assert grell.x(e1.ende) == 960 and abs(grell.x(e2.ende) - (jonas.x(e2.ende) + 230)) < 1
    assert grell._aktiv(grell.requisiten, e3.start)[1] is None
    assert jonas._aktiv(jonas.requisiten, e3.start)[1] == "karte"
    assert jonas.sitzt(tl["gesamt"]) == 1.0 and grell.x(tl["gesamt"]) > 1440
    assert any(n == "schritt" for n, _ in tl["effekte"])


def test_blinzeln_reproduzierbar():
    assert Spur("jonas", 5).blinks[:5] == Spur("jonas", 5).blinks[:5]


def test_standbild(tmp_path):
    tl = szene.zeitleiste(SB, _fake_ton)
    p = render.standbild(tl, 40, tmp_path / "f.png")
    from PIL import Image
    assert Image.open(p).size == (1080, 1920)
