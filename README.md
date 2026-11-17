# CARTOON STORY UNIVERSE

Automatische Produktion interaktiver 2D-Cartoon-Kurzvideos (9:16, 1080 × 1920, 30 fps, 60–90 s, H.264/AAC).
Jeden Tag eine Folge, Mo–So je eine andere Geschichte; die Zuschauer entscheiden per Kommentar (1, 2 oder 3),
wie es weitergeht. Fertige Videos kommen als **direkter MP4-Download** (GitHub-Release, kein ZIP).

**Status:** vorbereitet, **alle kostenpflichtigen Schritte gesperrt** (`config/budget.yaml`). Es wurde noch kein Video
gerendert und kein Cent ausgegeben.

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
python -m pytest -q tests
```

## Freigabe (Schritt für Schritt)

1. **Secrets** (Repo → Settings → Secrets → Actions): `RUNWAYML_API_SECRET`, `ELEVENLABS_API_KEY`
   (bezahlter Tarif, mind. Creator); optional `ANTHROPIC_API_KEY` (Drehbuch), `YOUTUBE_API_KEY`,
   `YOUTUBE_CHANNEL_ID` (Abstimmung), `R2_*` (Download ohne GitHub-Login).
2. **Budget** in `config/budget.yaml`: `monatsbudget_eur` setzen, `paid_rendering_enabled: true`.
3. **Erstes Video** manuell: Actions → „Tagesvideo produzieren“ → Bestätigungsphrase eingeben. Dabei entstehen
   einmalig die Figuren-Referenzbilder; sie werden ins Repo übernommen und in allen Folgen wiederverwendet.
4. **Täglich automatisch:** `taeglich_aktiv: true` und den `schedule`-Block in `produktion.yml` einkommentieren.
5. **Veröffentlichung** auf TikTok/YouTube bleibt aus, bis gesondert freigegeben.

## Download auf dem iPhone

Jede Folge erscheint unter **Releases** als `JJJJ-MM-TT_<geschichte>_teil-NN.mp4`, dazu ein Issue mit dem direkten
Link (Push über die GitHub-App). Link in Safari öffnen → Teilen → „In Dateien sichern“ oder „Video sichern“.
Da das Repo privat ist, muss Safari bei github.com angemeldet sein. Alternative ohne Login: Cloudflare R2
(10 GB kostenlos) mit 7 Tage gültigem Link – Secrets `R2_BUCKET`, `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY` eintragen, der Workflow nutzt es dann automatisch.
