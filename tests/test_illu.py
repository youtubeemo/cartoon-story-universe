"""Weg 1 (illustrierter Look): Storyboard v4, Kosten, Zeitleiste, Bildaufbau – alles kostenlos."""
import copy

from PIL import Image

from csu.common import load_story
from csu.state import initial_state
from illu import plan, render
from illu.storyboard import laden, normalisieren, pruefen, verlauf

SLUG = "die-letzten-10000"


def _daten():
    story = load_story(SLUG)
    return story, laden(SLUG, 1), initial_state(story)["werte"]


def test_teil1_ist_gueltig_und_rechnet_wie_v2():
    story, sb, start = _daten()
    assert pruefen(story, sb, start) == []
    ende = verlauf(story, sb, start)[-1]["werte"]
    assert ende == {"geld": 8500, "schulden": 18000, "tage": 29}


def test_pruefung_findet_fehler():
    story, sb, start = _daten()
    kaputt = copy.deepcopy(sb)
    kaputt["shots"][2]["bild"] = kaputt["shots"][1]["bild"]                       # gleiches Bild
    kaputt["shots"][3]["text"] = " ".join(["Wort"] * 20)                           # zu langer Shot
    kaputt["shots"][4]["werte"] = {"geld": {"delta": -50000}}                      # Geld < 0
    q = next(s for s in kaputt["shots"] if s.get("bild_von"))
    q["kamera"], q["fokus"] = "ran", [0.4, 0.45]                                   # gleiche Kamera wie Quelle
    f = " | ".join(pruefen(story, normalisieren(kaputt), start))
    assert "gleiches Bild" in f and "zu lang" in f and "Minimum" in f and "andere Kamera" in f


def test_kosten_je_folge():
    story, sb, _ = _daten()
    auftr = plan.auftraege(story, sb)
    k = plan.kosten(auftr, nur_offene=False)
    shots = sum(1 for s in sb["shots"] if not s.get("bild_von"))
    assert k["shots"] == shots and k["referenzen"] == 6
    assert k["credits"] == 8 * (shots + 6)
    assert abs(k["eur"] - k["credits"] * 0.01 * 1.19) < 0.01
    img = next(a for a in auftr if a.id.startswith("IMG_"))
    assert len(img.refs) <= 3 and img.refs[0].startswith("REF_") and "No text" in img.prompt


def test_wort_untertitel():
    assert render._chunks("Fünftausend Euro. *Heute*.", 14) == ["FÜNFTAUSEND", "EURO", "HEUTE"]
    assert render._chunks("Kontostand: genau *null* Euro.", 14) == ["KONTOSTAND", "GENAU NULL", "EURO"]


def test_bildaufbau(tmp_path):
    story, sb, start = _daten()
    leer = tmp_path / "leer.png"
    Image.new("RGB", (1080, 1920), (60, 70, 96)).save(leer)
    bilder = {s["id"]: leer for s in sb["shots"]}
    ton = {s["id"]: {"dauer": 1.5} for s in sb["shots"]}
    tl = render.zeitleiste(story, sb, start, bilder, ton)
    assert len(tl["shots"]) == len(sb["shots"]) and tl["cues"]
    s06 = next(s for s in tl["shots"] if s["id"] == "s06")
    im = render.bild(tl, int((s06["t0"] + 0.9) * 30))
    assert im.size == (1080, 1920)
    assert min(im.getpixel((540, int(1920 * 0.16) + 45))) > 200    # weißes Werte-Schild sichtbar
