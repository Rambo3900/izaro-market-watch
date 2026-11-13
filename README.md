# Izaro Market Watch ⚔️💎

Automatischer Marktmonitor für **Path of Exile 1 / aktuelle Softcore-Challenge-Liga**.
Ziel: Transfigured Gems im Labyrinth farmen und die Nachfrage erkennen, ohne ständige Nullmeldungen.

## Was wird geprüft?

- Jede Stunde um **Minute 17 UTC** über GitHub Actions (Zeitplan ist "best effort").
- Öffentliche Economy-API von [poe.ninja](https://poe.ninja/docs/api) für Gem-Preise.
- [RePoE](https://repoe-fork.github.io/) für die Liste echter Transfigured Gems und ihre Farben (täglich aktualisierter Katalog).
- Ausschließlich **unkorrumpierte Gem-Level 1 / Qualität 0** (0-Qualität kann bei poe.ninja auch als \`null\` erscheinen).
- Preisalarme nur bei **mindestens vier aktuellen Listings**. Preise sind Schätzwerte, keine garantierten Verkäufe.
- Eigene Watchlist mit zehn Starterkandidaten, zusätzlich alle anderen Transfigured Gems als Überraschungskandidaten.
- Relevante Preisänderungen, neue teure Gems, neue Top-10-Kandidaten und Wechsel der führenden Farbe.
- Vorsicht bei Ausreißern: Mindeständerung in Chaos und Prozent; vier Stunden Cooldown je Gem.
- **Erster Datenstand = Vergleichsbasis, kein Alarm.** Standard und Hardcore werden nicht verwendet.

## Öffentliche Ergebnisse

Diese Dateien werden bei jedem erfolgreichen Preisabruf von GitHub Actions aktualisiert:

| Datei | Beschreibung |
| --- | --- |
| [data/latest.json](data/latest.json) | Momentaufnahme, Preise, Anzahl Listings, Watchlist und Top 10 jeder Farbe |
| [data/history.json](data/history.json) | Stündliche Preis-Historie der letzten 14 Tage |
| [data/latest_alert.json](data/latest_alert.json) | Ereignisse aus dem letzten Abruf, **leere Liste bei Nullmeldung** |
| [data/catalog.json](data/catalog.json) | Aktuelle Transfigured-Gem-Namen und Farben aus RePoE |
| [data/cooldowns.json](data/cooldowns.json) | Unterdrückung wiederholter Preisalarme |

Solange die Challenge-Liga noch nicht in poe.ninja verfügbar ist, existieren die Dateien möglicherweise noch nicht. Das ist normal.

## GitHub Actions

[Izaro Market Watch – Actions](../../actions)

Der Workflow läuft stündlich, bei Codeänderungen oder manuell über **Run workflow**.
Er führt vor jedem Abruf die Offline-Tests aus und committet nur geänderte öffentliche JSON-Daten.

**Wichtig:** Die Benachrichtigung direkt in ChatGPT ist eine *separate* Bedingungsüberwachung.
Sie liest \`data/latest_alert.json\` und soll nur bei frischen, echten Ereignissen eine Meldung erzeugen.
GitHub Actions allein sendet keine ChatGPT-Push-Mitteilung.

## Interpretation und Grenzen

- \`price_chaos\` sind poe.ninja-Preisschätzungen, nicht nachgewiesene Verkäufe.
- Mindest-Liquidität: \`listings >= 4\`. Sehr junge, seltene Gems können daher zunächst ignoriert werden.
- Für die **Gem-Farben** verwenden wir RePoE, nicht eine heuristische Zuordnung über den Skill-Namen.
- \`top10_mean_chaos\` ist der Durchschnitt der zehn teuersten **ausreichend gelisteten** Gems je Farbe. Das ist **nicht** der erwartete Gewinn pro Divine-Font-Nutzung.
- GitHub Actions kann Läufe verzögern oder gelegentlich auslassen. poe.ninja und RePoE können ihre API ändern.
- Bei einem Wechsel der Challenge-Liga wird die Historie neu aufgebaut.
- Keine Zugangsdaten notwendig: Das Repository enthält ausschließlich öffentliche Preise und Code.
