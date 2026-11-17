# Bestandsaufnahme (17.11.2026)

| Repository | Inhalt | Wiederverwendung |
|---|---|---|
| storyhouse-originals (öffentlich) | Runway- und ElevenLabs-Clients mit Spezifikationsprüfung, SpendGuard, geprüfte Preise (14.11.2026), Lizenz-/Tarifprüfung | **Ja** – fest eingebunden (Commit `0c12b1d`), `config/pricing.yaml` übernommen |
| dschungel-freunde (privat) | Kostenlose Strecke: Blender, Piper-Stimmen, Rhubarb-Lippensynchronität, Animatic | Ausweichweg, falls ohne KI-Kosten produziert werden soll (Qualität deutlich einfacher) |
| gta-shorts-germany, gta-shorts-website, -49-174-4336567 | andere Projekte | nicht verwendet |

Hinweis: Private Repos teilen sich 2.000 kostenlose Actions-Minuten pro Monat. Cartoon Story Universe braucht ≈ 200.
Erkenntnis aus storyhouse: Runway lehnt leere `referenceImages` ab; eleven_v3 erlaubt nur `stability` 0 / 0,5 / 1 –
beides ist hier berücksichtigt und wird vor jedem Aufruf kostenlos geprüft.
