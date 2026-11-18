# Technischer Umsetzungsplan: echte 2D-Animationspipeline (Stand 18.11.2026)

Runway bleibt deaktiviert. Die alte Pipeline (`csu/`) bleibt unverändert im Repo, bis die neue Pipeline (`toon/`) produktiv läuft.

## 1. Werkzeugauswahl

| Werkzeug | Für automatisierte GitHub-Actions-Produktion | Ergebnis |
|---|---|---|
| Blender Grease Pencil | Sehr mächtig und per Python steuerbar. Ohne Grafikkarte bleibt aber nur langsames CPU-Rendern: in `dschungel-freunde` gemessen 0,21 Runner-Min. pro Bild (960×540), also Hunderte Minuten je Folge. Rigs per Code aufzubauen ist aufwendig, und jeder Lauf lädt rund 300 MB. | nicht gewählt |
| Synfig | Hat Knochen-Rigs und rendert per Kommandozeile. Das XML-Format ist mühsam zu erzeugen, das Rendern bei 1080p langsam, und Lippensync geht nur über einen Import. | nicht gewählt |
| OpenToonz | Professionell, aber ohne verlässliche Steuerung ohne Bildschirm für Skripte und Render. | nicht gewählt |
| Godot | Schnelles Rendern und gutes Animationssystem. Braucht aber eine Grafikkarte (Vulkan/OpenGL), die Videoaufnahme ist nicht für Server gedacht, der Aufwand ist hoch. | nicht gewählt |
| **Eigenes Cut-out-Rig in Python** (Pillow-Vektorzeichnung, 2× Supersampling) + **Rhubarb** + **Piper/ElevenLabs** + **FFmpeg** | Läuft ohne Bildschirm, reproduzierbar, ohne Grafikkarte und ohne Lizenzkosten. Figuren, Orte und Bewegungen sind Code/YAML, also versioniert und wiederverwendbar. **Gemessen: 1,9 s Rechenzeit pro Videosekunde** auf 2 Kernen. | **gewählt** |

Nachteil der Wahl: Der Look beschränkt sich auf flache Cut-out-Cartoons (passt zur Stilbibel). Neue Figuren und Orte müssen einmal als Vektorbeschreibung angelegt werden, und komplexe Bewegungen wie Laufen, Hinsetzen oder Drehen müssen als Bewegungsbausteine programmiert werden.

## 2. Architektur (`toon/`)

| Modul | Aufgabe | Status |
|---|---|---|
| `geo.py` | Vektorformen, Matrizen, Stift mit einheitlicher Kontur, Tageszeit-Tönung | fertig |
| `figur.py` + `figuren/*.yaml` | Rig: Hüfte, Oberkörper, Kopf, Schultern/Ellbogen, Hüften/Knie; Gesicht mit Lidern, Pupillen, Brauen, 9 Mundformen (A–H, X); 9 Ausdrücke; Frisuren, Kleidung, Accessoires, Requisiten | fertig für Jonas, Aylin, Grell |
| `anim.py` | 13 Haltungen mit weichen Übergängen, 6 Einzelaktionen (Jubeln mit Stauchen/Strecken, Nicken, Kopfschütteln, Erschrecken, Winken, Seufzen); automatisch Atmen, Blinzeln, Blickkontakt, Kopfbewegung beim Sprechen | fertig |
| `orte.py` | Vektor-Hintergründe, 4 Tageszeiten | Backstube fertig |
| `szene.py` | Storyboard v3 → eine durchgehende Zeitleiste; Haltung und Ausdruck bleiben über Schnitte erhalten; feste Kameraausschnitte; Logikprüfung | fertig |
| `ton.py` | Stimmen (Piper kostenlos, ElevenLabs nach Freigabe), Rhubarb-Lippensync (Prüfsumme festgelegt), Effekte, Musik, Mischung mit automatischer Musikabsenkung, −14 LUFS | fertig (Musik vorerst einfach) |
| `render.py` | Hintergrund einmal je Einstellung, Figuren je Bild, Blenden, Ausgabe nativ 1080×1920, 30 fps, H.264 (crf 17)/AAC | fertig |
| Statusanzeigen/Untertitel | aus der bestehenden Pipeline (`csu/hud.py`, `csu/state.py`) wiederverwendet | fertig |

## 3. Stand 18.11.2026 (Ausbaustufe 2)

| Bereich | Stand |
|---|---|
| Rig „2,5D“ | Körperdrehung stufenlos (vorne ↔ Dreiviertel ↔ Profil), Gliedmaßen mit echter Verkürzung, nahe/ferne Arme und Beine richtig überdeckt, Kopf dreht zusätzlich |
| Bewegungen | Gehen (Schrittzyklus, Armschwung, Anfahren/Abbremsen, Schrittgeräusche), Drehen (mit Blinzeln), Hinsetzen/Aufstehen, Übergeben von Hand zu Hand, Auf- und Abgänge, Jubeln, Nicken, Kopfschütteln, Erschrecken, Winken, Seufzen, Lachen, Stampfen; 18 Haltungen |
| Mimik/Gestik | 11 Ausdrücke inkl. Lachfalten, Brauen-Betonung auf offenen Vokalen, Sprechgesten, Nicken am Satzende, größere Mundformen, Mund verengt sich bei Drehung |
| Figuren | alle 18 Figuren der 7 Geschichten (15 Menschen, Hund Pixel, Roboter BOLT, Drache Glut; Papagei Kiko auf Tobis Schulter) |
| Orte | alle 18 Schauplätze aus 45 wiederverwendbaren Bauteilen (`toon/bausteine.py`, `toon/orte/*.yaml`), 4 Tageszeiten, Sitzplätze |
| Storyboard v3 | Positionen, Requisiten und Sitzen laufen über Schnitte durch; Prüfung verhindert Springen, Gehen im Sitzen, Übergaben ohne Gegenstand, Sprung-Schnitte, unbekannte Orte/Sitze |
| Stimmen | ElevenLabs (Abo) mit harter Credit-Grenze, kostenloser Abo-Prüfung, Emotions-Tags aus dem Ausdruck, Archiv gegen Doppelzahlung; Piper als kostenloser Ersatz |
| Musik/Geräusche | eigener Komponist (Akkordfolge, Bass, Begleitung, Motiv, Schlagwerk; 6 Stimmungen), Schritte, Stuhl, Ladenglocke, Tür, Papier, Posaune, Kasse, Whoosh; Musik duckt unter Sprache |
| Produktion | `python -m toon folge` + Workflow „Tagesfolge 2D“ (Abstimmung, Drehbuch-KI v3, Prüfung, Render, QC, Stand, Release); täglicher Zeitplan **aus** |

Noch offen: Bewegungen mit Gegenständen im Raum (Tür öffnen, Treppen), Tierfiguren mit weniger Aktionen, Stilbibel an die Videoreferenz anpassen (Referenz liegt nicht vor).

## 4. Kosten

| Posten | je Folge | je Monat (30 Folgen) |
|---|---:|---:|
| Animation und Render (eigene Pipeline) | 0 € | 0 € |
| GitHub Actions (≈ 6 Min. je Folge; 2.000 Freiminuten werden mit anderen privaten Repos geteilt; darüber 0,006 $/Min.) | 0–0,04 € | 0–1,10 € |
| Stimmen: Piper | 0 € | 0 € |
| Stimmen: ElevenLabs (≈ 1.700 Credits, im Creator-Abo) | 0 € zusätzlich | 0 € zusätzlich |
| Lippensync (Rhubarb), Effekte, Schnitt | 0 € | 0 € |
| Drehbuch per Claude-API (optional, nach Freigabe) | ≈ 0,10 € | ≈ 3 € |
| **Summe zusätzlich** | **≈ 0,10 €** | **≈ 3–4 €** |

Zum Vergleich: Die KI-Videovariante hätte ≈ 10,55 € je Folge gekostet. Mit der neuen Pipeline sind **tägliche Folgen weit innerhalb von 150 €** möglich. Der eigentliche Aufwand verschiebt sich auf das einmalige Anlegen von Figuren, Orten und Bewegungen.
