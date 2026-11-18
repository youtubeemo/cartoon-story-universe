# cartoon-story-universe – Regeln für KI-Agenten

Automatische 2D-Cartoon-Kurzvideos (Paket `csu/`), Kosten in `KOSTEN.md`, Budgetdurchsetzung in `csu/kasse.py`.

- Tests: `python -m pytest -q`; Prüfen: `python -m csu validate`, Kosten: `python -m csu kosten`
- **Budget: 150 € pro Monat, unveränderlich ohne Freigabe. Weitere kostenpflichtige Cartoon-Produktionen sind gesperrt** – Zeitplan und bezahlte Schritte (Runway, Claude-API, ElevenLabs) nicht wieder aktivieren.

<!-- agent-rules:start v1.0.0 — zentral gepflegt in claude-config, nicht hier von Hand ändern -->
## Kosten und Sicherheit (gilt für jeden KI-Agenten)

- Keine kostenpflichtigen API-Aufrufe oder -Tests ohne ausdrückliche Freigabe im Chat. Nur kostenlose Prüfungen (lokale Tests, Lint, Trockenläufe).
- Keine Zahlungen, Guthabenaufladungen, Abonnements, Testphasen mit Zahlungsmittel.
- API-Schlüssel, Secrets, Budgets und Produktionsgrenzen nicht ändern. `.env` niemals committen.
- Keine Secrets, Kundendaten oder personenbezogenen Daten an fremde Dienste senden.
- Keine ungeprüften Installationsskripte ausführen (`curl … | sh`, `npx <paket>@latest` u. ä.).
- Laufende Produktions-Workflows (GitHub Actions, Zeitpläne, Uploads) nicht unterbrechen, deaktivieren oder auslösen, außer auf ausdrücklichen Wunsch.
- Änderungen über einen eigenen Branch und Pull Request, nicht direkt auf `main`.
<!-- agent-rules:end -->
