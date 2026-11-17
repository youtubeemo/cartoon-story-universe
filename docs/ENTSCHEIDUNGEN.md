# Zuschauerentscheidungen

Jede Folge endet mit einem Cliffhanger und drei Optionen (1, 2, 3). Jede Option hat rechnerisch geprüfte Effekte
(z. B. `geld: -600, tage: -2`) und jede Folge eine **Standardoption**.

## Auswertung (vor der nächsten Folge derselben Geschichte, also 7 Tage später)
* **Gültig:** Kommentar beginnt mit 1, 2 oder 3 („2“, „2!“, „Option 3“, „Nr. 1“, „2️⃣ weil …“). „10 von 10“ oder „ich nehme 2“ zählen nicht.
* **Eine Stimme pro Konto** – die letzte gültige zählt. Der eigene Kanal zählt nicht.
* **YouTube:** automatisch über die YouTube Data API (kostenlos, nur API-Schlüssel; Video-ID im Workflow angeben).
* **TikTok:** Für normale Konten gibt es keine zuverlässige Kommentar-API. Stimmen optional im Workflow eintragen
  (`1=34,2=12,3=8`); sie werden addiert.
* **Fallback:** weniger als 5 gültige Stimmen, Gleichstand oder Kommentare nicht abrufbar → Standardoption.

Ergebnis, Stimmen, Quelle und Begründung werden in `state/<slug>.json` gespeichert; das Drehbuch der nächsten Folge
setzt genau diese Wahl fort, und ihre Effekte erscheinen am Anfang der Folge in den Anzeigen.
Vor der ersten Veröffentlichung gibt es keine Kommentare – dann gilt immer die Standardoption.
