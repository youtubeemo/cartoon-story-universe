# Kosten und Budgetkontrolle

**Monatslimit: 150 € zusätzliche Ausgaben** (Kalendermonat, Europe/Berlin). Abo-Gebühren (ElevenLabs Creator) zählen nicht.
Preise geprüft am 18.11.2026: Runway-API 1 Credit = 0,01 $, gen4_turbo 5 Credits/s, gen4_image_turbo 2 Credits/Bild;
Claude Sonnet 5.5 2 $ / 10 $ je 1 Mio. Tokens (Input/Output). Rechnung bewusst ungünstig: 1 $ = 1 €, plus 19 % USt.

## Je Folge (76 s, 14 Szenen, aus dem echten Auftragsplan)

| Posten | Credits | Zusätzliche Kosten |
|---|---:|---:|
| Runway: 14 Keyframes + 14 × 5 s Bewegtbild | 408 | 4,86 € |
| Runway: Figuren-/Ort-Referenzbilder (nur in der ersten Folge einer Geschichte) | ≈ 48 | ≈ 0,57 € einmalig |
| Claude-API Drehbuch (typisch ≈ 15k/5k Tokens; reserviert werden max. 40k/8k) | – | ≈ 0,10 € (max. 0,19 €) |
| ElevenLabs: Erzähler, Figurenstimmen, Soundeffekte (≈ 1.700 Credits) | – | 0 € (im Abo) |
| ElevenLabs: Musik (einmal je Geschichte, ≈ 1.350 Credits, dann wiederverwendet) | – | 0 € (im Abo) |
| GitHub Actions (≈ 6 Min.), Schnitt, Untertitel, Anzeigen, Export | – | 0 € |
| **Summe je Folge** | | **≈ 5,00 €** (Reservierung vor Start ≈ 6,30 €) |

## Wie viele Folgen schafft das Budget?

Mit 150 €: **29 Folgen pro Monat** (nachgerechnet in `tests/test_kasse.py`). In Monaten mit 30/31 Tagen stoppt die Kasse
an den letzten 1–2 Tagen automatisch. Weil der echte Dollarkurs unter 1 € liegt, sind die tatsächlichen Ausgaben
niedriger als gebucht – das ist der Puffer für Kursschwankungen und noch ausstehende Abrechnungen.
Für lückenlose 31 Folgen: Drehbücher auf 13 Szenen begrenzen (≈ 4,65 €/Folge) oder Budget auf 160 € anheben.

ElevenLabs-Verbrauch: ≈ 30 × 1.700 + 7 × 1.350 ≈ 61.000 Credits/Monat – passt in den Creator-Tarif (100.000).
Premium-Qualität (gen4.5, ≈ 12 €/Folge) wäre mit 150 € nur für ≈ 12 Folgen/Monat möglich und ist daher nicht aktiv.

## So wird das Limit durchgesetzt (`csu/kasse.py`)

1. **Freigabe-Schalter** (`config/budget.yaml`): ohne `paid_rendering_enabled` / `taeglich_aktiv` endet jeder Lauf mit 0 €.
2. **Reservierung des Höchstbetrags** vor Produktionsbeginn (Schätzung × 1,25, ungünstiger Kurs, USt.). Reicht das
   Restbudget (Limit − gebucht − offene Reservierungen) nicht → Stopp, keine Kosten.
3. **Kein Parallel-Überziehen:** Workflow-`concurrency` erlaubt nur einen Lauf; die Reservierung wird vor dem ersten
   API-Aufruf ins Repo gepusht – scheitert der Push, bricht der Lauf ab. Offene Reservierungen blockieren neue Läufe.
4. **Prüfung vor jedem einzelnen API-Aufruf** durch den SpendGuard (aus storyhouse), Abgleich mit Runways eigener
   Kostenangabe; Abweichung = Abbruch.
5. **Guthaben-/Tarifprüfung (kostenlos):** Runway-Guthaben muss den Bedarf decken; ElevenLabs muss bezahlter Tarif mit
   genug Restkontingent sein, Overage/Nachberechnung aktiv = Abbruch.
6. **Protokoll:** jeder Posten in `state/kosten.json`, je Folge ein Bericht in `berichte/`.
7. **Keine automatischen Wiederholungen.** Bricht ein Lauf ab, bleibt seine Reservierung voll stehen (gilt als bezahlt),
   bis sie nach Blick in die Anbieter-Abrechnung bereinigt wird: `python -m csu kasse --aufloesen RUN --tatsaechlich EUR`.

## Aufladungen und Abos – bewusst NICHT automatisiert

| Anbieter | Automatisches Nachladen | Grund |
|---|---|---|
| Runway API | **aus** | Prepaid-Guthaben; eine vom Code durchsetzbare Monatsobergrenze für Aufladungen ist nicht nachweisbar. Die Pipeline lädt nie nach, sie stoppt bei zu wenig Guthaben. |
| ElevenLabs | **aus** | Neue Abos haben keine Nachberechnung mehr; ältere Abos können Overage haben – die Pipeline bricht dann ab. Kein Tarif-Upgrade durch die Pipeline. |
| Anthropic (Claude-API) | **aus** | Auto-Reload in der Console nicht aktivieren; zusätzlich dort ein Monats-Ausgabenlimit (z. B. 5 $) setzen. |

**Aktueller Stand Runway: 306 Credits – das reicht nicht für eine Folge (erste Folge braucht 456).**
Manuell nachkaufen (z. B. 1.500 Credits = 15 $), der Kauf liegt innerhalb des Monatsbudgets; die Kasse bucht den Verbrauch.
