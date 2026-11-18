# Weg 1 – illustrierter Look: Stilbibel und Technikvergleich

Ziel: Folgen mit derselben Bildwirkung wie das Vorbild-Video (detaillierte Illustrationen, schnelle Schnitte,
Infografik-Overlays), aber mit **eigenen** Figuren, Orten und Geschichten. Vom Vorbild übernehmen wir nur den allgemeinen
Stil, keine Figuren, keine Marke, kein Wasserzeichen und keine Einzelbilder.

## Bildsprache

| Element | Regel |
|---|---|
| Bilder | Ein KI-Standbild je Shot (Runway `gen4_image`, 1080×1920), gemalter 2D-Cartoon-Look, Tiefe durch Vorder-, Mittel- und Hintergrund, weiches Licht, kräftige Farben, klare Konturen, große lesbare Gesichtsausdrücke |
| Figuren | Einmal je Geschichte ein Referenzblatt (Front- und Dreiviertelansicht) → in jedem Shot als Referenz `@jonas` usw. So bleiben Figuren in allen Folgen gleich |
| Orte | Einmal je Geschichte ein leeres Ortsbild als Referenz `@backstube` usw. Jede Geschichte hat ihre eigenen Orte |
| Text im Bild | Verboten (kein Text, keine Logos, keine Sprechblasen) – alle Schrift kommt aus der Pipeline und ist deshalb fehlerfrei |
| Schnitt | Shots von 1–3,6 s (Vorbild: ≈ 1,7 s), Länge folgt der gesprochenen Zeile; kein Bild doppelt ohne neue Kamera |
| Kamera | Nur festgelegte Fahrten auf einen Fokuspunkt: `ran`, `raus`, `links`, `rechts`, `hoch`, `runter`, `ruhig` – keine Zufallsbewegung |
| Atmosphäre | Schwebende Lichtpartikel, Vignette, kurzer Lichtblitz beim Ortswechsel |
| Werte-Schilder | Weißes, abgerundetes Schild mit Zeiger, graue Beschriftung und große Zahl; bei Änderung zählt die Zahl, das Schild springt und wackelt, grün = gut, rot = schlecht |
| Ausrufe | Gelbe, schräge Großschrift mit schwarzer Kontur (`+10.000 €`), springt ins Bild |
| Untertitel | 1–2 Wörter, Großbuchstaben, weiß mit schwarzer Kontur, Schlüsselwort rot (`*wort*` im Text) |
| Ende | Frage + drei Auswahlkarten 1/2/3, Erzähler fordert zum Kommentieren auf |
| Schriften | Anton (Untertitel, OFL), Luckiest Guy (Ausrufe, Apache 2.0), Baloo 2 (Schilder/Karten, OFL) – Lizenzen in `assets/fonts/` |

Einstellungen: `config/illustration.yaml`. Storyboard-Format: `illu/storyboard.py` (v4), Beispiel:
`stories/die-letzten-10000/teil-01.illu.yaml` (28 Shots, gleiche Handlung und Werte wie Teil 1 v2).

## Technikvergleich

| | Alt A: Runway-Video (`csu/`) | Alt B: Code-Zeichnung (`toon/`) | **Neu: Weg 1 (`illu/`)** |
|---|---|---|---|
| Bildquelle | KI-Bewegtbild je Szene | Formen aus Code (Pillow) | KI-Standbild je Shot |
| Bildqualität | gut, aber Figuren und Logik schwankten | gleichmäßig, wirkt einfach | detailliert wie das Vorbild |
| Bewegung | KI-Bewegung (unkontrolliert) | Rig: Gehen, Drehen, Lippen | gesteuerte Kamerafahrt + Overlays |
| Schnitttempo | 14 Szenen à 5 s | wenige lange Einstellungen | ≈ 28 Shots à 1–3,6 s |
| Figurentreue | Referenzbilder, trotzdem Abweichungen | exakt (Code) | Referenzblätter, je Bild bis 3 Referenzen |
| Schrift/Zahlen | ASS-Overlay | ASS-Overlay | eigene Schilder, Pop-ups, Wort-Untertitel |
| Stimmen | ElevenLabs | ElevenLabs/Piper | ElevenLabs (eine Zeile je Shot, mit Emotion) |
| Musik/Geräusche | ElevenLabs | lokal erzeugt | lokal erzeugt + Whoosh/Kasse automatisch |
| Kosten je Folge | ≈ 5,00 € | 0 € | **≈ 2,60 €** (+ einmalig ≈ 0,57 € Referenzen je Geschichte) |
| Renderzeit | Minuten bei Runway | ≈ 3–5 Min. | ≈ 3 Min. (2 Kerne) |

Was aus den alten Wegen bleibt: Kasse, Freigabephrase und SpendGuard (`csu/`), Werte-Rechnung und Prüfung der
drei Optionen (`csu/state.py`), Stimmen-Archiv und Credit-Grenze, Musik, Geräusche und Mischung (`toon/ton.py`).

## Ablauf

```
python -m illu pruefen die-letzten-10000 1          # Storyboard + Kosten, kostenlos
python -m illu muster  die-letzten-10000 1 --out out/muster   # Platzhalterbilder, kostenlos
python -m illu bilder  die-letzten-10000 1 --out out/b --bestaetigung "…" [--nur s01,s05]   # KOSTENPFLICHTIG
python -m illu folge   die-letzten-10000 1 --out out/f --stimmen elevenlabs --credit-grenze 1500
```

`bilder` läuft nur, wenn `config/illustration.yaml › aktiv: true` **und** `config/budget.yaml ›
paid_rendering_enabled: true` gesetzt sind und die Freigabephrase stimmt. Fertige Bilder liegen in `assets/illu/` und
werden nie zweimal bezahlt.

## Offen bis zur Freigabe

* Erster bezahlter Bildtest (6 Referenzblätter + 3 Shots ≈ 72 Credits ≈ 0,86 €) – nur nach ausdrücklicher Freigabe.
* Danach visuelle Prüfung, ob Figuren über mehrere Shots gleich bleiben; erst dann eine komplette Folge.
