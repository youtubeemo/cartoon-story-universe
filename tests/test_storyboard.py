"""Kostenlose Tests der neuen Storyboard-Regeln, Freigaben und Auftragspläne (keine API-Aufrufe)."""
import copy

from csu.common import load_episode, load_story
from csu.state import initial_state
from csu.validate import validate_episode

STORY = load_story("die-letzten-10000")
EP = load_episode("die-letzten-10000", 1)


def _errs(ep):
    return validate_episode(STORY, ep, initial_state(STORY))[0]


def test_referenz_storyboard_gueltig():
    assert _errs(EP) == []


def test_anschluss_nur_bei_gleichem_ort_und_figuren():
    ep = copy.deepcopy(EP)
    ep["szenen"][4]["uebergang"] = "anschluss"            # Bank nach Backstube
    assert any("anschluss" in e for e in _errs(ep))


def test_sprungschnitt_wird_erkannt():
    ep = copy.deepcopy(EP)
    ep["szenen"][3]["uebergang"] = "schnitt"              # gleiche Einstellung wie Szene 3
    assert any("Sprung-Schnitt" in e for e in _errs(ep))


def test_tageszeit_darf_nicht_rueckwaerts():
    ep = copy.deepcopy(EP)
    ep["szenen"][11]["tageszeit"] = "morgen"
    ep["szenen"][11]["uebergang"] = "schnitt"
    ep["szenen"][11]["kamera"] = "nah"
    assert any("Tageszeit" in e for e in _errs(ep))


def test_sprecher_muss_im_bild_sein_und_text_muss_passen():
    ep = copy.deepcopy(EP)
    ep["szenen"][7]["dialog"][0]["figur"] = "jonas"
    ep["szenen"][0]["erzaehler"] = "Ein sehr langer Erzählertext, der niemals in sechs Sekunden passt, weil er viel zu lang ist."
    errs = _errs(ep)
    assert any("nicht im Bild" in e for e in errs) and any("passt nicht" in e for e in errs)


def test_unbekannte_kamera_und_dauer():
    ep = copy.deepcopy(EP)
    ep["szenen"][2]["kamera"] = "drohne"
    ep["szenen"][2]["dauer"] = 5
    errs = _errs(ep)
    assert any("kamera" in e for e in errs) and any("dauer" in e for e in errs)


def test_freigabe_prueft_hash(tmp_path):
    from PIL import Image
    from csu.freigabe import _approved, freigeben
    Image.new("RGB", (8, 8), "red").save(tmp_path / "ella_v.png")
    freigeben(tmp_path)
    assert "ella_v" in _approved(tmp_path)
    Image.new("RGB", (8, 8), "blue").save(tmp_path / "ella_v.png")   # nachträglich ausgetauscht
    assert "ella_v" not in _approved(tmp_path)
