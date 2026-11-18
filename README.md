# CARTOON STORY UNIVERSE

Automatische Produktion interaktiver 2D-Cartoon-Kurzvideos (9:16, 1080 × 1920, 30 fps, 60–90 s, H.264/AAC).
Jeden Tag eine Folge, Mo–So je eine andere Geschichte; die Zuschauer entscheiden per Kommentar (1, 2 oder 3),
wie es weitergeht. Fertige Videos kommen als **direkter MP4-Download** (GitHub-Release, kein ZIP).

**Status (18.11.2026, Mittag):** Strategiewechsel auf eine **eigene 2D-Animationspipeline** (`toon/`): Cut-out-Rig,
Lippensync (Rhubarb), Piper-/ElevenLabs-Stimmen, FFmpeg – keine KI-Videos mehr. Plan und Kosten:
[`docs/TECHNIKPLAN-2D.md`](docs/TECHNIKPLAN-2D.md). Animationsprobe: Workflow „Animationsprobe (kostenlos)“.
Runway, alle bezahlten Schritte und der Zeitplan sind **deaktiviert**; die alte Pipeline (`csu/`) bleibt bis zur Ablösung erhalten.

## Ablauf einer Folge

```
Abstimmung der Vorfolge (YouTube-API kostenlos, TikTok manuell) ─► Effekte der Wahl
  ─► Drehbuch (liegt im Repo oder Claude-API, ~0,10 €) ─► kostenlose Prüfung (Länge, Rechnung, Referenzen)
  ─► Budgetprüfung ─► ElevenLabs: Erzähler, Figurenstimmen, Soundeffekte
  ─► Runway: Keyframes mit festen Figur-Referenzen ─► Runway: bewegte 2D-Szenen
  ─► FFmpeg: Schnitt, Ton-Mix, Musik, animierte Statusanzeigen, Untertitel, Auswahlkarte, Export
  ─► Qualitätsprüfung ─► GitHub-Release (MP4) + Issue mit Link ─► Stand & Kosten gespeichert
```

| Pfad | Inhalt |
|---|---|
| `stories/<slug>/story.yaml` | Story-Bibel: Figuren (Referenz-Prompts, Stimmen), Orte, Statusanzeigen, Bogen über 6 Teile |
| `stories/<slug>/teil-NN.yaml` | Drehbuch einer Folge (Szenen, Kamera, Erzähler, Dialog, SFX, HUD-Ereignisse, 3 Optionen) |
| `state/<slug>.json` | dauerhafter Stand: Werte, Inventar, Entscheidungen, Verlauf |
| `state/kosten.json` | tatsächliche Ausgaben je Monat |
| `config/` | Produktion, Stil, Budget (Hauptschalter), geprüfte Preise |
| `csu/` | Pipeline (nutzt die geprüften API-Clients aus `storyhouse-originals`, fester Commit) |
| [`KOSTEN.md`](KOSTEN.md) | Kosten pro Video und Monat |
| [`docs/DESIGN.md`](docs/DESIGN.md) | Cartoon-Stil, Figurenkonsistenz, Statusanzeigen |
| [`docs/ENTSCHEIDUNGEN.md`](docs/ENTSCHEIDUNGEN.md) | Zuschauer-Abstimmung |
| [`docs/BESTAND.md`](docs/BESTAND.md) | geprüfte vorhandene Repositories |

## Kostenlose Befehle

```bash
pip install -r requirements.txt && bash scripts/storyhouse_holen.sh
python -m csu validate                                   # alle Geschichten + nächste Folgen prüfen
python -m csu heute --datum 2026-11-23                   # was ist an dem Tag dran?
python -m csu estimate --geschichte die-letzten-10000    # Kosten aus dem echten Auftragsplan
python -m csu kosten                                     # Hochrechnung pro Video/Monat
python -m csu kasse                                      # Monatsbudget, Reservierungen
python -m pytest -q tests
```

## Automatisierung

Der Workflow „Tagesvideo produzieren“ läuft **täglich um 05:17 Uhr** (Berlin). Solange die Kosten nicht freigegeben
sind, prüft er nur kostenlos und meldet „keine Produktion, 0 €“. Nach Freigabe läuft jeden Tag ohne Eingriff:
Abstimmung auswerten → Drehbuch schreiben (Claude-API) → Figuren/Szenen vorbereiten → Animation (Runway) →
deutsche Stimmen, Soundeffekte, lizenzierte Musik (ElevenLabs) → Schnitt mit Anzeigen und Untertiteln → MP4 →
Produktionsbericht mit Kosten, Laufzeit und Download-Link (`berichte/`, Release, Issue). Budgetregeln: [`KOSTEN.md`](KOSTEN.md).

## Freigabe (Schritt für Schritt)

1. Secrets `RUNWAYML_API_SECRET`, `ELEVENLABS_API_KEY` sind vorhanden; zusätzlich `ANTHROPIC_API_KEY` für die täglichen
   Drehbücher (optional `YOUTUBE_API_KEY`, `YOUTUBE_CHANNEL_ID`, `R2_*`).
2. Runway-Guthaben manuell aufladen (306 Credits reichen nicht für eine Folge), Auto-Reload überall aus lassen.
3. In `config/budget.yaml`: `paid_rendering_enabled: true`, `drehbuch_api_aktiv: true`, `taeglich_aktiv: true`.
   Das Monatslimit von 150 € ist bereits eingetragen.
4. Veröffentlichung auf TikTok/YouTube bleibt aus, bis gesondert freigegeben.

## Download auf dem iPhone

Jede Folge erscheint unter **Releases** als `JJJJ-MM-TT_<geschichte>_teil-NN.mp4`, dazu ein Issue mit dem direkten
Link (Push über die GitHub-App). Link in Safari öffnen → Teilen → „In Dateien sichern“ oder „Video sichern“.
Da das Repo privat ist, muss Safari bei github.com angemeldet sein. Alternative ohne Login: Cloudflare R2
(10 GB kostenlos) mit 7 Tage gültigem Link – Secrets `R2_BUCKET`, `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY` eintragen, der Workflow nutzt es dann automatisch.
