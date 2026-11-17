"""Zentrale Kostenkontrolle für ALLE kostenpflichtigen Anbieter (Monatslimit, z. B. 150 €).

Regeln
* Verfügbar = Monatslimit − gebuchte Kosten − offene Reservierungen.
* Vor Produktionsbeginn wird der MAXIMAL mögliche Betrag reserviert (Schätzung + Sicherheitsaufschlag,
  Wechselkurs bewusst ungünstig 1 $ = 1 €, inkl. USt.). Reicht das Restbudget nicht → Stopp, 0 € ausgegeben.
* Jeder einzelne API-Aufruf wird zusätzlich vom SpendGuard gegen die Reservierung geprüft (vor dem Senden).
* Nach dem Lauf werden die tatsächlichen Kosten gebucht und die Reservierung aufgelöst.
* Bricht ein Lauf hart ab, bleibt die Reservierung VOLL stehen (ausstehende Abrechnungen gelten als bezahlt),
  bis sie nach Kontrolle der Anbieter-Abrechnung mit ``python -m csu kasse --aufloesen RUN --tatsaechlich EUR``
  bereinigt wird.
* Die Reservierung wird vor dem ersten Aufruf ins Repo gepusht. Scheitert der Push (paralleler Lauf), wird
  abgebrochen – so kann auch kein zweiter Workflow das Limit überschreiten.
* Abo-Gebühren zählen nicht (ElevenLabs-Credits im Abo = 0 € zusätzlich; Nachkauf/Overage wird verweigert).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

from csu.common import ROOT, STATE, write_json

LEDGER = STATE / "kosten.json"
TZ = ZoneInfo("Europe/Berlin")


class BudgetStopp(RuntimeError):
    """Restbudget reicht nicht – Produktion wird ohne Kosten beendet."""


def jetzt() -> dt.datetime:
    return dt.datetime.now(TZ)


class Kasse:
    def __init__(self, limit_eur: float, path: Path = LEDGER, monat: str | None = None):
        self.path = Path(path)
        self.limit = float(limit_eur)
        self.monat = monat or jetzt().strftime("%Y-%m")
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        if "monate" not in self.data:          # altes Format übernehmen
            alt = {k: v for k, v in self.data.items() if k[:2] == "20"}
            self.data = {"version": 2, "monate": {}}
            for m, v in alt.items():
                self.data["monate"][m] = {"gebucht_eur": float(v.get("eur", 0)), "reservierungen": {}, "posten": []}
        self.m = self.data["monate"].setdefault(self.monat, {"gebucht_eur": 0.0, "reservierungen": {}, "posten": []})
        self.m["limit_eur"] = self.limit

    # -------------------------------------------------------------- Abfragen
    @property
    def gebucht(self) -> float:
        return round(float(self.m["gebucht_eur"]), 2)

    @property
    def reserviert(self) -> float:
        return round(sum(float(r["eur"]) for r in self.m["reservierungen"].values()), 2)

    @property
    def verfuegbar(self) -> float:
        return round(self.limit - self.gebucht - self.reserviert, 2)

    def stand(self) -> str:
        return (f"Monat {self.monat}: Limit {self.limit:.2f} € · gebucht {self.gebucht:.2f} € · "
                f"reserviert {self.reserviert:.2f} € · frei {self.verfuegbar:.2f} €")

    # -------------------------------------------------------------- Änderungen
    def reservieren(self, run: str, eur: float, zweck: str) -> None:
        eur = round(float(eur), 2)
        if eur <= 0:
            return
        if self.limit <= 0:
            raise BudgetStopp("Kein Monatsbudget freigegeben (monatsbudget_eur = 0).")
        if eur > self.verfuegbar:
            raise BudgetStopp(f"Restbudget reicht nicht: benötigt bis zu {eur:.2f} €, frei {self.verfuegbar:.2f} € "
                              f"({self.stand()}). Produktion gestoppt, keine Kosten entstanden.")
        r = self.m["reservierungen"].setdefault(run, {"eur": 0.0, "seit": jetzt().isoformat(timespec="seconds"),
                                                       "zweck": []})
        r["eur"] = round(float(r["eur"]) + eur, 2)
        r["zweck"].append(f"{zweck}: {eur:.2f} €")
        self.save()

    def buchen(self, run: str, anbieter: str, eur: float, credits: float | None = None, notiz: str = "") -> None:
        eur = round(float(eur), 4)
        self.m["posten"].append({"zeit": jetzt().isoformat(timespec="seconds"), "run": run, "anbieter": anbieter,
                                 "eur": round(eur, 2), "credits": None if credits is None else round(credits, 1),
                                 "notiz": notiz})
        self.m["gebucht_eur"] = round(float(self.m["gebucht_eur"]) + eur, 4)
        self.save()

    def aufloesen(self, run: str) -> None:
        self.m["reservierungen"].pop(run, None)
        self.save()

    def run_kosten(self, run: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for p in self.m["posten"]:
            if p["run"] == run:
                out[p["anbieter"]] = round(out.get(p["anbieter"], 0) + p["eur"], 2)
        return out

    def save(self) -> None:
        write_json(self.path, self.data)


def git_sync(nachricht: str, pfade: list[str]) -> None:
    """Pusht den Kassenstand sofort (nur in GitHub Actions, CSU_GIT_SYNC=1). Push-Fehler = Abbruch."""
    if os.environ.get("CSU_GIT_SYNC") != "1":
        return

    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)

    git("add", *pfade)
    if git("diff", "--cached", "--quiet").returncode == 0:
        return
    git("commit", "-q", "-m", nachricht)
    r = git("push", "-q")
    if r.returncode != 0:
        raise BudgetStopp("Kassenstand konnte nicht gesichert werden (paralleler Lauf?) – Abbruch vor jeder "
                          f"Ausgabe.\n{r.stderr[-400:]}")
