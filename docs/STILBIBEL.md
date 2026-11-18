# Stilbibel – Cartoon Story Universe (verbindlich)

Maschinenlesbare Fassung: `config/stil.yaml`. Jeder Bild- und Bewegungsprompt wird ausschließlich daraus gebaut.
Hinweis: Die vom Auftraggeber erwähnte Videoreferenz liegt noch nicht vor. Sobald sie da ist, werden Look,
Farbwelt und Kameraregeln hier daran angeglichen.

## 1. Look
* Einfacher, ausdrucksstarker 2D-Cartoon im TV-Animationsstil.
* Klare, gleichmäßig dicke schwarze Konturen (#1B1B1F), überall gleiche Linienstärke.
* Flächige Farben, höchstens ein harter Schattenton. Keine Verläufe, keine Maltextur, kein 3D, kein Fotorealismus.
* Große Köpfe und Augen, klare Silhouetten. Hintergründe vereinfacht und leicht entsättigt, damit Figuren hervortreten.
* Kein Text im Bild (Schilder, Briefe, Logos ohne Schrift).

## 2. Farben
Globale Farbwelt aus `stil.yaml → palette` (Tag-, Nacht- und Akzentfarben). Jede Figur behält ihre Kostümfarben aus
der Story-Bibel, und die Vorlagen sind dafür die Referenz.

## 3. Charaktervorlagen
Jede Hauptfigur bekommt drei feste Ansichten: **vorne**, **seite** und **dreiviertel** (Ganzkörper, neutrale Pose,
hellgrauer Hintergrund). Seite und Dreiviertel werden mit der Vorderansicht als Referenz erzeugt. Dazu kommt je Ort ein
Hintergrundbild ohne Figuren. Verwendet wird nur, was ein Mensch freigegeben hat (`freigabe.yaml` mit Prüfsumme).

## 4. Storyboard (Pflicht vor jeder Animation)
Jede Szene ist nummeriert und legt fest: Ort · Figuren (max. 3) · Ansicht · Tageszeit · Handlung (was und warum) ·
Startbild · Kamera (Einstellungsgröße) · Kamerabewegung (höchstens eine) · Bewegung der Figuren · Übergang ·
Dauer (4/6/8 s) · Erzähler/Dialog/SFX/Statusänderung.

## 5. Kamera
| Einstellung | Bedeutung |
|---|---|
| totale | ganzer Ort, Orientierung (Pflicht beim ersten Auftritt eines Ortes) |
| halbtotale | Figuren ganz |
| halbnah / nah / gross / detail | zunehmend näher |
| ueber_schulter, aufsicht, untersicht | Perspektive |

Kamerabewegung: standardmäßig **statisch**. Erlaubt ist genau eine ruhige Bewegung (Schwenk, Ran- oder Rückfahrt,
Begleitfahrt, Neigung), und nur wenn sie der Handlung dient. Keine zufälligen Fahrten.

## 6. Übergänge (Logik wird automatisch geprüft)
* **abblende**: Folgenbeginn aus Schwarz.
* **schnitt**: neue Einstellung. Gleicher Ort, gleiche Figuren und gleiche Einstellung sind als Sprung-Schnitt verboten.
* **anschluss**: Handlung läuft nahtlos weiter. Das Startbild ist das letzte Bild der vorigen Szene. Nur bei
  gleichem Ort, gleichen Figuren, gleicher Kamera und Tageszeit.
* **ueberblendung**: Orts- oder Zeitsprung über kurze Schwarzblende.
* Die Tageszeit läuft nie rückwärts ohne Überblendung.

## 7. Bewegung
Jede Szene beschreibt eine konkrete, sichtbare Aktion (mindestens 5 Wörter). An jeden Bewegungsprompt wird angehängt:
flüssige 2D-Animation, gleiche Figuren wie im Startbild, keine Schnitte, kein Morphing, keine neuen Figuren.
Sprechende Figuren bewegen den Mund (keine exakte Lippensynchronität, siehe Bericht).

## 8. Text im Bild (Overlay)
* Titel nur 2,5 s am Anfang.
* Statusanzeige nur am Anfang (3 s) und für 3,5 s nach jeder Änderung, höchstens eine Änderung je Szene.
* Untertitel höchstens 32 Zeichen pro Einblendung.
* Auswahlkarte am Ende ohne zusätzlichen Untertitel.
