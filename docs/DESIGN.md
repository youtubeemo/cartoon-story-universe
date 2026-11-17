# Einheitliches Cartoon-Design

## Stil (in `config/production.yaml → stil`, an JEDEN Prompt angehängt)
Hochwertiger handgezeichneter 2D-Look: kräftige dunkelbraune Konturen, Cel-Shading mit weichen Verläufen, malerische,
detailreiche Hintergründe, warme gesättigte Palette mit Petrol-Akzenten, große ausdrucksstarke Augen, klare Silhouetten.
Bewegung: Squash & Stretch, Sekundärbewegung (Haare, Stoff), aktive Kamera (Fahrten, Kreisfahrten, Reißschwenks).
Kein Text im Bild – alle Schrift kommt sauber aus dem Overlay.

## Figuren sehen in allen Folgen gleich aus
1. Jede Figur und jeder Ort hat einen festen `reference_prompt` (Model Sheet, Vorder- und Dreiviertelansicht).
2. Beim ersten bezahlten Lauf entsteht daraus EIN Referenzbild, das automatisch nach `assets/refs/<slug>/<tag>.png`
   übernommen wird. Ab dann wird nur noch dieses Bild verwendet (0 €, identisches Aussehen).
3. Jeder Keyframe bekommt bis zu drei Referenzen per `@tag` (Runway `referenceImages`), das Video entsteht aus dem
   Keyframe (Bild → Bewegung). Ein schlechtes Referenzbild kann vor der Serie einfach im Repo ersetzt werden.

## Statusanzeigen (HUD)
* Oben links, halbtransparente Kästen, Zeilen laut `anzeige` der Geschichte (Geld, Wasser, Frist, Inventar …).
* Änderung: Zahl zählt in 0,8 s hoch/runter, Zeile leuchtet grün (gut) oder rot (schlecht), Pop-up „−1.500 €“ steigt auf.
  Ob „runter“ gut ist, legt `gut: runter` fest (Schulden, Drachenhunger).
* Formate: `geld` 8.500 €, `prozent` 50 %, `tage` „Noch 7 Tage“, `stunden`, `jahr`, `sterne` ★★☆☆☆, `bruch` 3/7, `inventar`.
* **Rechnerisch korrekt über alle Folgen:** Drehbücher geben nur „zu“/„delta“ an; der Vorher-Wert kommt immer aus
  `state/<slug>.json`. Unmögliche Werte (negativ, > 100 %, fehlender Gegenstand) stoppen die Produktion vor jeder Ausgabe.
  Die Effekte der Zuschauerwahl werden zu Beginn der nächsten Folge sichtbar verrechnet („Eure Wahl: 2“).

## Bildaufbau für TikTok/Shorts
Sichere Zone: oben 130 px (HUD beginnt bei 150), unten 420 px (Untertitel darüber), rechts 160 px (Buttons).
Untertitel: weiß = Erzähler, gelb = Figuren, max. 2 Zeilen. Auswahlkarte in den letzten ~8 s: Frage + drei Optionen
fliegen nacheinander ein, darunter „Schreib 1, 2 oder 3 in die Kommentare!“.
