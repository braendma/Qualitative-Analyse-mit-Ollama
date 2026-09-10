# 0.2.0-beta.1

Diese Vorabversion ergänzt eine lokale Bedienoberfläche für den Import codierter Textstellen, die Auswahl der Analysemodule und die Prüfung der Ergebnisse. Sie bleibt eine Beta; Modellvorschläge benötigen eine fachliche Prüfung.

## Änderungen

- CSV und MAXQDA-XLSX direkt importieren, Tabellenblatt auswählen und Spalten zuordnen.
- Module per Häkchen auswählen; benötigte Vorgängermodule werden berücksichtigt.
- Eingaben vor dem Start prüfen, Laufstatus anzeigen und Ergebnisse öffnen. Die lokale Prüfliste unterstützt die dokumentierte Bewertung von Modellvorschlägen.
- Optionale Telegram-Statusmeldungen mit austauschbarem Schlüssel und geschützter Speicherung unter Windows. Interviewtexte werden nicht als Statusmeldungen versendet.
- Fehlerkorrekturen bei großen CSV-Textfeldern, Excel-Blattmetadaten, fehlgeschlagenen Fortsetzungen und schnellen Projektwechseln während Dateiupload oder Prüfung.
- Übersichtliche Ordner `src/`, `config/`, `demo/`, `tests/` und `docs/`; bebilderte Anleitung im README.
- MIT-Lizenz sowie dokumentierte Installationsprüfung und Paketversionen.

## Öffentliche Konfiguration und Daten

`config/config_v2.yaml` verwendet lokales Ollama unter `http://localhost:11434` mit `granite4.1:8b`. Die beiden Eingabepfade zeigen ausschließlich auf `demo/`. Die Demo und ihr Kategoriensystem sind vollständig künstlich: 50 Codierzeilen aus 43 Passagen von sechs erfundenen Personen. Auch der vorgegebene Untersuchungskontext beschreibt ausdrücklich eine Demonstration.

Es sind keine API-Schlüssel, privaten Interviewexporte oder studienspezifischen Konfigurationen Bestandteil des Veröffentlichungspakets. `OLLAMA_API_KEY` ist lediglich der Name einer optionalen Umgebungsvariablen. Thinking-Protokollierung und rohe Antworten der Coding-Validierung sind standardmäßig deaktiviert. Normale Analyseergebnisse können Textzitate enthalten und gehören bei eigenen Forschungsdaten in eine private Ablage.

## Aktualisierung

Das vollständige Projekt in einen neuen Ordner entpacken und einrichten. Eigene Konfigurationen separat übernehmen und prüfen: relative Eingabepfade beziehen sich auf den Ordner der jeweiligen YAML-Datei. Der CLI-Einstieg heißt jetzt `python run_workflow.py`; Einzelmodule liegen unter `src/`.

Nach diesem Programmwechsel einen neuen Analyselauf starten. Vorhandene Projektdateien und Ergebnisse bleiben erhalten; alte Checkpoints werden nicht automatisch migriert.

## Prüfstand und Grenzen

Die [frische Installation unter Windows/Python 3.13](INSTALLATION_TEST.md) bestand 67 Python-Tests und vier Oberflächentests. Start, Demo und Eingabeprüfung wurden zusätzlich im Browser geprüft. Lokale Modellinferenz wurde dabei nicht getestet. Die künstlichen Beispiele prüfen technische Abläufe und sind kein unabhängiger wissenschaftlicher Gütebenchmark.
