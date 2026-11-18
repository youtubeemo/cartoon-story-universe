"""Kostenlose Tests der 2D-Rig-Pipeline (kein Ton, kein Video – nur Logik und ein Standbild)."""
from pathlib import Path

import yaml

from toon import render, szene
from toon.anim import Spur

SB = yaml.safe_load((Path(__file__).resolve().parent.parent / "probe" / "animationsprobe.yaml").read_text())


def _fake_ton(sprecher, text, key):
    d = len(text) / 14
    return Path("/dev/null"), d, [(0.0, d / 2, "C"), (d / 2, d, "B")]


def test_probe_storyboard_gueltig():
    assert szene.pruefen(SB) == []


def test_logikfehler_werden_erkannt():
    sb = yaml.safe_load(yaml.safe_dump(SB))
    sb["einstellungen"][2]["kamera"] = "nah"                  # nah mit zwei Figuren im Fokus
    sb["einstellungen"][1]["figuren"]["jonas"]["x"] = 900      # Figur springt ohne Gang
    sb["einstellungen"][0]["ablauf"][0]["haltung"] = "fliegen"
    errs = szene.pruefen(sb)
    assert any("nah" in e for e in errs) and any("springt" in e for e in errs) and any("fliegen" in e for e in errs)


def test_zeitleiste_haltung_bleibt_ueber_schnitte():
    tl = szene.zeitleiste(SB, _fake_ton)
    e1, e2, e3 = tl["einstellungen"]
    assert e1.ende == e2.start and e2.ende == e3.start
    jonas = tl["spuren"]["jonas"]
    z = jonas.zustand(e2.start + 0.05, 560, 2000, 960)        # Haltung aus Einstellung 1 wirkt fort
    assert z.requisit is None or z.requisit == "brief"
    assert any(f == "C" for _, _, f in jonas.mund)


def test_blinzeln_reproduzierbar():
    assert Spur("jonas", 5).blinks[:5] == Spur("jonas", 5).blinks[:5]


def test_standbild(tmp_path):
    tl = szene.zeitleiste(SB, _fake_ton)
    p = render.standbild(tl, 40, tmp_path / "f.png")
    from PIL import Image
    assert Image.open(p).size == (1080, 1920)
