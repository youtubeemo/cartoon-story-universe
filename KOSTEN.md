# Kosten pro Video und Monat

Grundlage: der **echte Auftragsplan** von Teil 1 „Die letzten 10.000 €“ (76 s, 14 Szenen, 59 Aufträge),
berechnet mit `python -m csu estimate/kosten` und den am 14.11.2026 geprüften Preisen aus
`config/pricing.yaml` (Runway: 1 Credit = 0,01 $). Bewusst konservativ: 1 $ = 1 €, inkl. 19 % USt.

## Je Video

| Posten | Standard (gen4_image_turbo + gen4_turbo) | Premium (gen4_image + gen4.5) |
|---|---:|---:|
| Runway Bild + Bewegung (14 Szenen à 5 s) | 4,86 € | 12,19 € |
| … mit 50 % Nachdrehs (falls nötig, nie automatisch) | 7,28 € | 18,28 € |
| ElevenLabs (≈ 1.700 Credits: Erzähler, Stimmen, SFX) | im Abo | im Abo |
| Drehbuch per Claude-API (optional, ~12k/4k Tokens) | ≈ 0,10 € | ≈ 0,10 € |
| Schnitt, Overlays, Export (GitHub Actions, ~6 Min.) | 0 € | 0 € |
| **Summe je Video** | **≈ 5–7,50 €** | **≈ 12,50–18,50 €** |

## Je Monat (30 Videos)

| Posten | Standard | Premium |
|---|---:|---:|
| Runway | 146–218 € | 366–548 € |
| ElevenLabs Creator (100.000 Credits/Monat, kommerzielle Lizenz; Bedarf ≈ 51.000) | ≈ 26 € | ≈ 26 € |
| Claude-API Drehbücher (optional) | ≈ 3 € | ≈ 3 € |
| GitHub (privat, 2.000 Actions-Min. frei; Bedarf ≈ 200 Min.) | 0 € | 0 € |
| **Summe** | **≈ 175–250 €** | **≈ 395–580 €** |

**Einmalig je Geschichte:** Figuren-/Ort-Referenzbilder (≈ 5 × 8 Credits ≈ 0,50 €) und Musik (90 s, ≈ 1.350
ElevenLabs-Credits, im Abo). Danach aus dem Repo wiederverwendet – 0 €.

## Empfehlung

Mit **Standard** starten und **Monatsbudget 220 €** freigeben (`max_pro_video_eur: 12` ist bereits gesetzt).
Premium ist erst sinnvoll, wenn die ersten Folgen abgenommen sind; dafür `max_pro_video_eur` auf 20 € anheben.

## Schutzmechanismen

* Hauptschalter `paid_rendering_enabled: false`, Bestätigungsphrase für manuelle Läufe, `taeglich_aktiv` für den Cron.
* Vor dem Lauf: Schätzung + 25 % Puffer gegen Video- und Monatslimit; ElevenLabs-Tarif/Kontingent wird kostenlos geprüft
  (Free-Tarif und automatische Nachberechnung werden verweigert).
* Während des Laufs: storyhouse-SpendGuard prüft jeden Auftrag VOR dem Senden und vergleicht Runways eigene
  Kostenangabe – Abweichung = sofortiger Abbruch.
* Keine automatischen Wiederholungen. Bezahlte Ergebnisse liegen im Cache und kosten beim nächsten Lauf nichts.
* Tatsächliche Ausgaben landen in `state/kosten.json`.
* Runway-API-Guthaben wird vorab aufgeladen (Prepaid); ElevenLabs ist ein Monatsabo (Creator ca. 22 $).
