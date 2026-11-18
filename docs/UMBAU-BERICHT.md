# Umbau-Bericht – 18.11.2026

## Sofortmaßnahmen
* `paid_rendering_enabled`, `drehbuch_api_aktiv` und `taeglich_aktiv` stehen auf **false**, der Zeitplan im Workflow ist auskommentiert.
* Seit der ersten Folge sind keine neuen Renderings oder API-Kosten entstanden. Gebucht sind weiter 5,01 € von 150 €.
* Die verworfene Folge „Das Haus am Nebelsee – Teil 1“ ist zurückgesetzt: Drehbuch, Stand und Figurenbilder sind
  entfernt, die Musik bleibt erhalten. Der Release bleibt als Beleg bestehen.

## Ursachen der schlechten ersten Folge (aus dem Code)

| Problem | Konkrete Ursache |
|---|---|
| Lose Aneinanderreihung von KI-Bildern | Jede Szene bekam ein eigenes, unabhängig erzeugtes Startbild und wurde 5 s animiert. Es gab keinen Bildanschluss zwischen Szenen, kein Storyboard und keine Prüfung der Szenenlogik. |
| Unlogische Übergänge | Das Drehbuch hatte nur Freitext-Felder (`kamera`, `motion_prompt`), ohne Regeln für Orte, Tageszeit, Anschlüsse oder Sprung-Schnitte. |
| Zufällige Kamerafahrten | `config/production.yaml` hängte an **jeden** Bewegungsprompt „dynamic camera move“ an. Das Modell hat also in jeder Szene eine Kamerafahrt erfunden. |
| Inkonsistente Figuren (z. B. Albert) | Pro Figur gab es nur **ein** Bild aus einem Text-Prompt („model sheet“), ohne Abnahme. Orte belegten Referenzplätze (max. 3), in Szene 12 fiel deshalb eine Figur heraus. |
| „Gemalte“ statt klarer Cartoon-Optik | Der Stil-Prompt verlangte „painterly richly detailed backgrounds, feature-film look“. Das ergibt Illustrationen, keine einfachen Cartoons. |
| Zu viel Text im Bild | Statusanzeige mit 3 Zeilen dauerhaft sichtbar, dazu Titel, Pop-ups, Untertitel und eine doppelte Aufforderung am Ende. |
| **Auflösung (512 × 910?)** | Die Datei selbst ist 1080 × 1920 (ffprobe), der **Bildinhalt aber nicht**: Runway gen4_turbo kann höchstens **720 × 1280** erzeugen, FFmpeg hat nur hochskaliert. Eine Messung zeigt, dass das Bild nach Verkleinern auf 512 px Breite und Zurückskalieren fast unverändert bleibt (PSNR 38,7 dB), die echte Detailschärfe liegt also nur bei etwa 512–720 px. Dazu kam eine niedrige Bitrate von 3,5 Mbit/s (`crf 20`, `preset veryfast`). Woher genau die Angabe 512 × 910 stammt, kann ich nicht sicher sagen. Die Datei im Release hat 1080 × 1920, eine niedrigere Anzeige kann aber von einer Vorschau oder Neukodierung auf dem Gerät kommen. |
| Keine echte Qualitätskontrolle | Geprüft wurden nur Containerwerte (Auflösung, Codec, Länge), nicht der Inhalt. |

## Was umgebaut wurde

1. **Verbindliche Stilbibel** (`config/stil.yaml`, `docs/STILBIBEL.md`): einfacher 2D-Cartoon, gleichmäßige
   Konturen, flächige Farben, feste Farbpalette, Verbotsliste. Alle Prompts werden nur noch daraus gebaut.
2. **Charaktervorlagen** (Phase `vorlagen`): je Hauptfigur vorne, seite und dreiviertel, wobei die Seiten- und
   Dreiviertelansicht mit der Vorderansicht als Referenz entstehen. Dazu ein Hintergrund je Ort. Genutzt wird nur,
   was in `freigabe.yaml` mit Prüfsumme steht. Ein ausgetauschtes Bild gilt automatisch als nicht freigegeben.
3. **Storyboard Pflicht** (Format v2): nummerierte Szenen mit Ort, Figuren, Ansicht, Tageszeit, Handlung, Startbild,
   Kamera, Kamerabewegung, Bewegung, Übergang und Dauer. Die Drehbuch-KI ist auf dieses Format verpflichtet,
   „Die letzten 10.000 €“ Teil 1 ist als Referenz umgeschrieben.
4. **Logische Übergänge erzwungen** (`csu/validate.py`): gültige Anschlüsse, keine Sprung-Schnitte, neuer Ort zuerst in
   totale oder halbtotale, Tageszeit nie rückwärts, Sprecher muss im Bild sein, Sprechtext muss in die Szene passen,
   höchstens eine Statusänderung je Szene. Ein Verstoß stoppt den Lauf, bevor Bildkosten entstehen.
5. **Konsistente Referenzen**: Jede Figur geht in der passenden Ansicht als eigene Referenz in jedes Startbild ein.
   Anschluss-Szenen starten exakt mit dem letzten Bild der vorigen Szene.
6. **Keine zufälligen Kamerafahrten**: feste Phrasen je Einstellung, standardmäßig statisch, der Zusatz „dynamic
   camera“ ist entfernt. Die Bewegungsprompts verbieten Schnitte, Morphing und neue Figuren.
7. **Echte Bewegung statt Montage**: Jede Szene beschreibt eine konkrete Aktion. Sprechende Figuren bekommen eine
   Mundbewegung. Blenden laufen über Schwarz statt harter Wechsel.
8. **Echtes 1080 × 1920**: Das neue Profil `qualitaet` nutzt Runway **veo3.1_fast**, das nativ 1080 × 1920 liefert
   (Gen-4-Modelle können nur 720p). Startbilder mit gen4_image in 1080p, Export mit `crf 17`, `preset medium`.
9. **Weniger Text im Bild**: Titel nur 2,5 s, Statusanzeige nur bei Änderungen, kürzere Untertitel, keine doppelte
   Aufforderung am Ende.
10. **Automatische Qualitätskontrolle** (`csu/qc.py`), ohne bestandene Prüfung kein öffentlicher Release (nur ein
    Entwurf) und kein Fortschreiben des Stands. Geprüft werden:
    * Auflösung, Codecs, Bildrate und Länge, außerdem die **echte Quellauflösung jedes Clips** (Hochskalieren fällt auf).
    * Ton: Lautheit, Spitzenpegel, Lücken und ob Ton- und Bildlänge übereinstimmen.
    * Untertitel: Überlappung, Lesetempo und Zeilenlänge.
    * Szenenfolge: **zufällige Bildwechsel innerhalb einer Szene** und harte Brüche an Anschlüssen.
      An der ersten Folge getestet: Die Prüfung findet alle 13 Szenengrenzen und zusätzlich einen
      unerwarteten Wechsel bei 57,9 s.
    * Bildstabilität innerhalb jeder Szene.
    * Ein Kontaktbogen mit einem Bild je Szene für die Sichtprüfung.
11. **Bildprüfung vor dem teuren Teil**: Phase `storyboard` erzeugt nur die Startbilder (≈ 1,10 €). Danach vergleicht
    Claude jedes Bild mit den Vorlagen und der geplanten Handlung (≈ 0,03 €), und anschließend sichtet ein Mensch das
    Storyboard. Erst danach darf die Animation (≈ 9,30 €) laufen.

## Grenzen – ehrlich
* Kostenlos getestet ist nur die Technik: Schnitt, Prüfungen und Logik mit künstlichen Testbildern. **Ob die neuen
  Einstellungen gute Animationen ergeben, ist nicht bewiesen.** Das zeigt erst ein freigegebener Lauf mit
  Vorlagen und Storyboard.
* Eine exakte Lippensynchronität erzeugt die Pipeline nicht, die Figuren bewegen nur allgemein den Mund.
* Die automatische Bildkonsistenzprüfung ist ein KI-Gutachten und ersetzt nicht den Blick eines Menschen.
* Die erwähnte Videoreferenz liegt mir nicht vor. Die Stilbibel ist aus der Beschreibung abgeleitet.

## Kosten (Profil `qualitaet`, aus dem echten Auftragsplan)

| | Credits | € (1 $ = 1 €, inkl. USt.) |
|---|---:|---:|
| Storyboard (12 Startbilder, gen4_image 1080p) | 96 | 1,14 |
| Animation (78 s veo3.1_fast, 1080 × 1920) | 780 | 9,28 |
| Claude (Drehbuch und Bildprüfung, typisch) | – | ≈ 0,13 |
| ElevenLabs (Stimmen, SFX, Musik) | ≈ 2.900 | im Abo |
| **Je Folge** | | **≈ 10,55 €** |
| Vorlagen, einmalig je Geschichte (z. B. 3 Figuren × 3 + 3 Orte) | ≈ 96 | ≈ 1,15 |

**Mit 150 € im Monat sind das ≈ 14 Folgen**, also keine tägliche Folge. Die Alternativen: das Profil `test` (≈ 5 €,
29 Folgen, aber nur 720p und hochskaliert, also ein Teil der alten Ursache) oder ein Budget von etwa 330 € für eine
tägliche Folge in voller Qualität.
