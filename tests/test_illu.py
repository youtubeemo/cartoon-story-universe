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
    neu_refs = sum(1 for a in auftr if a.id.startswith("REF_") and not a.fest)   # freigegebene kosten nichts
    assert k["shots"] == shots and k["referenzen"] == neu_refs == 5
    assert k["credits"] == 8 * (shots + neu_refs)
    assert abs(k["eur"] - k["credits"] * 0.01 * 1.19) < 0.01
    img = next(a for a in auftr if a.id.startswith("IMG_"))
    assert len(img.refs) <= 3 and img.refs[0].startswith("REF_") and "no letters" in img.prompt


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


# ---------------------------------------------------------------- Figurentreue, Referenzen, QC, Retusche
def test_charakterbibel_vollstaendig_fuer_alle_geschichten():
    import glob
    import yaml
    from illu.storyboard import MERKMALE
    for f in glob.glob("stories/*/story.yaml"):
        for k, fig in yaml.safe_load(open(f, encoding="utf-8"))["figuren"].items():
            assert all(fig["merkmale"].get(m) for m in MERKMALE), (f, k)


def test_referenzen_werden_als_bilder_uebergeben_und_angesprochen():
    story, sb, _ = _daten()
    auftr = plan.auftraege(story, sb)
    assert plan.pruefe_auftraege(auftr) == []
    s15 = next(a for a in auftr if a.id == "IMG_s15")
    assert s15.refs == ["REF_backstube", "REF_grell", "REF_jonas"]
    assert "@jonas is Jonas (21-year-old adult man" in s15.prompt
    ref = next(a for a in auftr if a.id == "REF_jonas")
    assert "front view" in ref.prompt and "Not 3D" in ref.prompt and "copper red" in ref.prompt
    kaputt = copy.deepcopy(s15)
    kaputt.prompt = kaputt.prompt.replace("@jonas", "Jonas")
    assert any("nicht angesprochen" in f for f in plan.pruefe_auftraege(auftr + [kaputt]))


def test_neue_referenz_erzwingt_neues_shotbild(tmp_path, monkeypatch):
    story, sb, _ = _daten()
    vorher = {a.id: a.datei.name for a in plan.auftraege(story, sb)}
    alt = plan.freigegebene_referenzen
    monkeypatch.setattr(plan, "freigegebene_referenzen",
                        lambda slug: {**alt(slug), "jonas": plan.ARCHIV / slug / "ref_jonas_neu.png"})
    nachher = {a.id: a.datei.name for a in plan.auftraege(story, sb)}
    assert nachher["REF_jonas"] == "ref_jonas_neu.png"
    assert nachher["IMG_s15"] != vorher["IMG_s15"] and nachher["IMG_s13"] == vorher["IMG_s13"]


def test_schrift_im_bildprompt_wird_abgelehnt():
    story, sb, start = _daten()
    k = copy.deepcopy(sb)
    k["shots"][0]["bild"] += ", a shop sign with the text OPEN"
    assert any("verlangt Schrift" in f for f in pruefen(story, k, start))


def test_ki_urteil_sperrt_bei_jeder_abweichung():
    from illu import qc
    alles = {"figuren": {"jonas": {k: True for k in qc.PRUEFPUNKTE_FIGUR}}, **{k: True for k in qc.PRUEFPUNKTE_BILD}}
    assert qc.auswerten(alles, ["jonas"]) == (True, [])
    kind = copy.deepcopy(alles)
    kind["figuren"]["jonas"]["alter"] = False
    ok, gruende = qc.auswerten(kind, ["jonas"])
    assert not ok and "jonas: alter weicht ab" in gruende
    ohne = copy.deepcopy(alles)
    del ohne["kein_text"]                                   # fehlende Antwort = nein
    assert qc.auswerten(ohne, ["jonas"])[0] is False


def test_nicht_freigegebene_bilder_sperren_die_folge(tmp_path, monkeypatch):
    from illu import qc
    monkeypatch.setattr(plan, "ARCHIV", tmp_path)
    story, sb, _ = _daten()
    b = tmp_path / "x.png"
    Image.new("RGB", (1080, 1920)).save(b)
    assert qc.sperren_fehlende(story, sb, {"s01": b})            # ungeprüft → gesperrt
    qc.setzen(story["slug"], b, "manuell_ok", [], "test")
    assert qc.sperren_fehlende(story, sb, {"s01": b}) == []
    qc.setzen(story["slug"], b, "vorbehalt", ["Haut"], "test")
    assert qc.sperren_fehlende(story, sb, {"s01": b})


def test_retusche_entfernt_details_und_laesst_flaeche():
    import numpy as np
    from illu.retusche import flicken
    img = np.full((200, 300, 3), (60, 140, 200), np.uint8)
    img[90:110, 120:180] = 20                                    # „Schrift“
    out = flicken(img, [100, 70, 200, 130])
    assert np.abs(out[100, 150].astype(int) - (60, 140, 200)).max() < 25
    assert (out[0, 0] == img[0, 0]).all()
