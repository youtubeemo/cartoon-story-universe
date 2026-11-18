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

## 3. Nächste Schritte bis zur täglichen Produktion

1. **Bewegungsbausteine erweitern**: Gehen von A nach B (Laufzyklus), Umdrehen, Hinsetzen, Tür öffnen, Gegenstände übergeben.
2. **Seitenansicht der Figuren** (bisher wirkt nur der Kopf gedreht).
3. **Alle Orte und Figuren der 7 Geschichten** anlegen: etwa 18 Orte und 17 Figuren, alles einmalig und danach wiederverwendet.
4. **Drehbuch-KI auf Storyboard v3** umstellen. Claude schreibt nur noch Beats (Haltung, Ausdruck, Aktion, Text), keine Bild-Prompts.
5. **Produktionsworkflow** auf `toon` umstellen: Abstimmung, Storyboard, Prüfung, Ton, Render, Qualitätskontrolle, Release. Die Qualitätskontrolle für Ton, Untertitel, Länge und Auflösung wird übernommen.
6. **Stimmen in Produktionsqualität**: ElevenLabs im Abo (nach Freigabe). Piper ist kostenlos, klingt aber deutlich synthetischer.
7. **Musik**: je Geschichte einmal mit ElevenLabs (im Abo) oder aus einer lizenzfreien Bibliothek. Die synthetische Musik ist nur ein Platzhalter.
8. **Stilbibel an deine Videoreferenz anpassen**, sobald sie vorliegt.

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
