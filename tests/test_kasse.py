"""Kostenlose Prüfung der zentralen Budgetkontrolle (keine API-Aufrufe)."""
import pytest

from csu.kasse import BudgetStopp, Kasse
from csu.script import max_cost_eur


def test_reservierung_buchung_und_stopp(tmp_path):
    k = Kasse(150, tmp_path / "k.json", monat="2026-12")
    k.reservieren("r1", 6.30, "Folge")
    assert k.verfuegbar == 143.70
    k.buchen("r1", "runway", 5.04, 408)
    k.aufloesen("r1")
    assert (k.gebucht, k.reserviert, k.verfuegbar) == (5.04, 0, 144.96)
    # Persistenz: neuer Prozess sieht denselben Stand
    k2 = Kasse(150, tmp_path / "k.json", monat="2026-12")
    assert k2.gebucht == 5.04 and k2.run_kosten("r1") == {"runway": 5.04}


def test_limit_wird_nie_ueberschritten(tmp_path):
    k = Kasse(150, tmp_path / "k.json", monat="2026-12")
    n = 0
    while True:
        try:
            k.reservieren(f"r{n}", 6.30, "Folge")
        except BudgetStopp:
            break
        k.buchen(f"r{n}", "runway", 5.04)
        k.aufloesen(f"r{n}")
        n += 1
    assert k.gebucht <= 150 and n == 29


def test_offene_reservierung_blockiert_parallel(tmp_path):
    a = Kasse(10, tmp_path / "k.json", monat="2026-12")
    a.reservieren("lauf-a", 8, "Folge")
    b = Kasse(10, tmp_path / "k.json", monat="2026-12")   # zweiter Workflow liest denselben Stand
    with pytest.raises(BudgetStopp):
        b.reservieren("lauf-b", 8, "Folge")


def test_ohne_freigabe_kein_budget(tmp_path):
    with pytest.raises(BudgetStopp):
        Kasse(0, tmp_path / "k.json").reservieren("r", 1, "x")


def test_drehbuch_hoechstkosten():
    # 40k Input × 2 $ + 8k Output × 10 $ je Mio. = 0,16 $ → × 1,19 USt. bei 1 $ = 1 €
    assert max_cost_eur() == pytest.approx(0.1904, abs=1e-4)
