"""Kostenlose Kerntests: Statusrechnung, Abstimmung, HUD-Overlay, Folgenprüfung. Keine API, kein Render."""
import copy

import pytest

from csu.common import load_episode, load_story, story_slugs
from csu.hud import build_ass, fmt_delta, fmt_value
from csu.state import StateError, apply, initial_state, simulate
from csu.validate import validate_episode, validate_story
from csu.voting import decide, parse_manual, parse_vote, tally

STORY = load_story("die-letzten-10000")


def test_alle_geschichten_gueltig():
    for slug in story_slugs():
        assert validate_story(load_story(slug)) == [], slug


def test_teil1_rechnet_korrekt():
    st = initial_state(STORY)
    events, werte = simulate(STORY, st, load_episode("die-letzten-10000", 1))
    assert [(e["key"], e["vorher"], e["nachher"]) for e in events] == [
        ("geld", 0, 10000), ("geld", 10000, 8500), ("tage", 30, 29)]
    assert werte == {"geld": 8500, "schulden": 18000, "tage": 29}
    errs, _, info = validate_episode(STORY, load_episode("die-letzten-10000", 1), st)
    assert errs == [] and 60 <= info["laenge_s"] <= 90


def test_wahl_wird_in_naechster_folge_verrechnet():
    st = initial_state(STORY)
    st["werte"] = {"geld": 8500, "schulden": 18000, "tage": 29}
    st["offene_entscheidung"] = {"option": 2, "effekte": {"geld": -600, "tage": -2}}
    ep = copy.deepcopy(load_episode("die-letzten-10000", 1))
    for s in ep["szenen"]:
        s.pop("hud", None)
    events, werte = simulate(STORY, st, ep)
    assert werte == {"geld": 7900, "schulden": 18000, "tage": 27}
    assert events[0]["quelle"] == "Eure Wahl: 2"


def test_grenzen_und_inventar():
    hud = {"w": {"typ": "prozent"}, "inv": {"typ": "inventar"}}
    werte = {"w": 10, "inv": ["Seil"]}
    with pytest.raises(StateError):
        apply(werte, hud, "w", delta=-20)
    with pytest.raises(StateError):
        apply(werte, hud, "inv", items=["-Messer"])
    assert apply(werte, hud, "inv", items=["+Messer", "-Seil"]) == (["Seil"], ["Messer"])


def test_abstimmung():
    assert [parse_vote(t) for t in ["2", "Option 3!", "1️⃣ klar", "10 von 10", "ich nehme 2", "2.5"]] == \
        [2, 3, 1, None, None, None]
    c = tally([{"author": "a", "text": "1", "time": "1"}, {"author": "a", "text": "3", "time": "2"},
               {"author": "b", "text": "3", "time": "1"}, {"author": "kanal", "text": "1", "time": "1"}], {"kanal"})
    assert c == {3: 2}
    assert decide(c, standard=2, min_stimmen=1)[0] == 3
    assert decide(c, standard=2, min_stimmen=5)[0] == 2           # zu wenige Stimmen
    assert decide(parse_manual("1=4,2=4,3=1"), 3, 1)[0] == 3       # Gleichstand → Standard


def test_hud_format_und_overlay():
    d = STORY["hud"]["geld"]
    assert fmt_value(d, 8500) == "8.500 €" and fmt_delta(d, 10000, 8500) == "−1.500 €"
    assert fmt_value({"typ": "tage"}, 7) == "Noch 7 Tage"
    ass = build_ass(STORY, {"geld": 10000, "schulden": 18000, "tage": 30},
                    [{"t": 5.0, "key": "geld", "vorher": 10000, "nachher": 8500}], 70.0,
                    [{"start": 1, "end": 2, "text": "Hallo", "erzaehler": True}],
                    {**load_episode("die-letzten-10000", 1)["entscheidung"], "start": 62.0}, "Teil 1")
    assert "Geld: 10.000 €" in ass and "Geld: 8.500 €" in ass and "−1.500 €" in ass
    assert "Schreib 1, 2 oder 3" in ass and "PlayResY: 1920" in ass
