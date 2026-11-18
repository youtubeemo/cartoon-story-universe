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

## Ausbaustufe 2: Figurentreue und Qualitätskontrolle (nach dem Bildtest vom 18.11.2026)

**Ergebnis des Bildtests (8 Bilder, 0,86 €):** Hintergründe und Farben gut; Referenzblätter plastisch-3D statt 2D;
Jonas in s15 als Kind mit schwarzen Haaren; Fantasieschrift auf Schildern; Gesichter auf Broten; Grells Hautfarbe
nicht wie in der Figurenvorlage. Urteile je Bild: `assets/illu/die-letzten-10000/qc.json`.

| Problem | Umsetzung (kostenlos, im Code) |
|---|---|
| Figuren uneinheitlich | Verbindliche Charakterbibel `merkmale` für **alle 18 Figuren** in `stories/*/story.yaml`: Alter, Gesicht, Frisur, Haarfarbe, Haut, Kleidung, Körper + Kurzform für Shots; Prüfung verlangt sie vollständig |
| 3D-Referenzblätter | Gleicher Stiltext für Referenzen und Shots („flat 2D … not 3D, not CGI“); Referenzblatt nur noch **eine** Vorderansicht (die zwei Ansichten wichen voneinander ab); eigener 2D-Stilanker wird beim Erzeugen jeder Referenz als Stilvorlage mitgegeben |
| Referenzen wirklich genutzt? | Nachweis s. u.; zusätzlich prüft `pruefe_auftraege` vor jedem Lauf: jede Referenz wird als Bild übergeben, ihr Tag erfüllt Runways Regel und steht als `@tag` im Prompt; Prompt ≤ 1000 Zeichen (wird nie still gekürzt) |
| Jonas falsch | Jede Figur steht mit Kurzbeschreibung im Shot-Prompt („@jonas is Jonas (21-year-old adult man (not a kid), copper-red curly hair …)“) |
| Schrift, Gesichter auf Essen | Verbotsliste im Prompt; Storyboard-Prüfung lehnt Bildbeschreibungen ab, die Schrift verlangen |
| Fehlerhafte Bilder | Zwei Phasen: erst Referenzen, dann QC + Eintrag in `stories/<slug>/referenzen.yaml`; Shots nur mit freigegebenen Referenzen. Jedes Bild bekommt einen QC-Status; `folge` verweigert jedes Bild ohne `ok`/`manuell_ok` |
| Automatische Prüfung | `illu/qc.py`: lokal (Format, Duplikate) + KI-Prüfung je Bild gegen Referenz und Charakterbibel (11 Prüfpunkte, fehlende Antwort = nein) + Prüfbögen für Menschen + protokolliertes manuelles Urteil |
| Vorhandene Bilder | `illu/retusche.py`: Schrift und Brot-Gesichter lokal entfernt (s21, Straße). Neue Referenz → neuer Dateiname → betroffene Shots werden automatisch neu geplant |

**Nachweis, dass Runway die Referenzbilder verarbeitet hat:** Jonas trägt in s15 und s21 dasselbe kleine
Buchstaben-Logo auf der Jacke wie auf seinem Referenzblatt – es stand in keinem Prompt. Grell hat in s13/s15
dieselbe Hautfarbe und Gesichtsform wie sein Referenzblatt, obwohl der Prompt nichts dazu sagte. Die Bilder wurden also
als Eingabe genutzt; das Problem war die Qualität der Referenzen (zwei widersprüchliche Ansichten, 3D) und die zu
knappe Figurenbeschreibung im Shot. Laut API-Beschreibung nimmt `gen4_image` höchstens 3 Referenzen; Tags müssen
3–16 Zeichen lang sein und `^[a-z][a-z0-9_]+$` erfüllen.

**Was lokale Prüfung nicht kann:** Texterkennung (Tesseract) lieferte in den gemalten Bildern fast nur Fehlalarme und
erkannte „ATAN“ nur als „AX“; Farbanteile unterschieden falschen und richtigen Jonas nicht (Brot und Holz haben
denselben Farbton wie seine Haare). Beides wird deshalb nicht als Prüfung verwendet; Alter, Gesicht und Proportionen
prüft nur die KI-Bildprüfung (≈ 0,02 € je Bild) oder ein Mensch.

**Retusche statt Neuerzeugung:** möglich für kleine Störungen (Schrift, Augen auf Brot, Logos) – umgesetzt für s21
und die Straßenreferenz. Nicht möglich für falsche Figuren (s15), falsche Hautfarbe (s13) oder den 3D-Look der
Referenzblätter – diese brauchen neue Bilder. Bearbeitungsfähige Bildmodelle (z. B. `gpt_image_2`,
`nano_banana_2.1`, `ideogram_4_5` mit Maske) sind über dieselbe Runway-Schnittstelle erreichbar, aber
kostenpflichtig und noch nicht in `config/pricing.yaml` geprüft – deshalb nicht aktiviert.

**Stilvorlage „Schlaf ist Währung“:** Das hochgeladene Video ist das Original des Kanals @ABSURDIAWORLD. Dessen Bilder
als Referenz in die Bild-KI zu geben hieße, fremde, urheberrechtlich geschützte Grafik als Vorlage zu kopieren –
das ist rechtlich nicht sauber und wird nicht gemacht. Stattdessen dient ein **eigenes** Bild als Stilanker
(`assets/illu/die-letzten-10000/stil_anker.png`, retuschierte Straßenreferenz). Wenn du eigene Bilder aus einem
selbst erstellten Video hast, können sie als Stilanker eingetragen werden.

## Offen bis zur Freigabe

* Zweiter Bildtest in zwei Phasen: 4 neue Referenzen (Jonas, Aylin, Grell, Backstube) ≈ 0,38 € + KI-Prüfung
  ≈ 0,08 €; danach 3 Shots ≈ 0,29 € + KI-Prüfung ≈ 0,06 €; zusammen ≈ 0,81 €.
* Erst danach lässt sich beurteilen, ob 2D-Stil, gleiches Alter und gleiche Gesichtszüge wirklich erreicht werden.
