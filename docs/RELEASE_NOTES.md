# 0.3.3 · Beta · Lokale Ollama-Speicherschätzung

Automatische, rein lesende Kapazitätsschätzung nach Modellwahl oder Kontextänderung; aktueller NVIDIA-VRAM und verfügbarer RAM, konservativer Prüfbereich von 1–8 Anfragen. Unbekannte Architekturen und bereits geladene Modelle werden ausdrücklich als nicht bestimmbar angezeigt. Server-Parallelität wird nicht automatisch verändert. Handbuch mit bebildertem Beispiel ergänzt.

# 0.3.2 · Beta · 11. September 2026

Codierregeln und CSV-Vorschau. Die Vorschau der Originalspalten steht direkt über der manuellen Zuordnung. Alle zwölf Codes des vollständigen Demos enthalten künstliche Ein-/Ausschlussregeln und Abgrenzungen.

Semikolon-CSV zunächst als Vorschau einlesen, dann Kategorienspalten manuell zuordnen. Pflicht: Codepfad oder Kategorie sowie Definition. Ein-/Ausschlussregeln, weitere Codierhinweise und Ankerbeispiele bleiben optional. Fehlende oder doppelte Zuordnungen sperren den Start. Regeln fließen in Codierung, Codeprüfung und Kategorienvorschläge ein; Kategorienvergleich und Folgeläufe erhalten sie. Bisherige Dateien ohne Regelfelder bleiben lesbar. Mit künstlichem CSV-Beispiel und Handbuch-Screenshot.

Prüfung: 102 Python-Tests und neun JavaScript-Tests bestanden. Browserprüfung für Importvorschau, manuelle Zuordnung, Startsperre, erneutes Öffnen und schmale Ansicht. Keine echten Modellaufrufe; ein Qualitätsgewinn ist damit noch nicht empirisch belegt.

---

# 0.3.1 · SVG-Patch · 10. September 2026

Weiterhin als Vorabversion veröffentlicht. Clusterdiagramme und Konfusionsmatrix werden zusätzlich als echte SVG-Vektorgrafiken gespeichert. HTML-Gesamtberichte bevorzugen SVG, bieten einen Einzeldatei-Download und bleiben offline nutzbar. PNG bleibt als Alternative erhalten. Die Konfusionsmatrix verwendet auch für Zellen und Farbskala Vektorformen.

SVG-Dateien werden auf passive Bildinhalte geprüft; Skripte, eingebettete Rasterbilder und externe Ressourcen werden abgewiesen. Vorhandene Berichte bleiben unverändert. Eine doppelte Dateianzeige durch unterschiedliche Windows-Pfadschreibweisen wurde korrigiert.

Prüfung: 98 Python-Tests sowie acht bestehende JavaScript-Tests; Browsertest mit 13 SVG-Diagrammen, Vektordownload, Offline-Anzeige und PDF-Export. Keine Modellaufrufe für diesen Patch. Die Cloud-Testgrenzen der Beta 3 bleiben bestehen.

Beim Update die Oberfläche schließen und die Programmdateien ersetzen; private Konfigurationen und Projekte erhalten. Nach Codeänderungen neue Analyseläufe beginnen, statt alte Checkpoints unverändert fortzusetzen.

---

# 0.3.0-beta.1 · Beta 3 · 10. September 2026

**Bedienung und Berichte:** Automatische HTML-Gesamtberichte mit dauerhafter Ergebnisverknüpfung, Offline-Grafiken und Suche; einklappbare Einzeldateien; Assistent für fehlende Passage-IDs mit bestätigten Gruppen und unveränderlichen Originalen; vollständiges lokales [Handbuch](HANDBUCH.md); braendma-Signet in der Seitenleiste. Clusterüberschriften zeigen jetzt alle vorhandenen Kategorieebenen ohne leere Facetten. Gleichzeitige Bildabrufe werden zuverlässiger angenommen.

Diese Vorabversion ergänzt automatische, versionierte Prüfentscheidungen in der lokalen Oberfläche, Excel-Export, neue Analyseversionen nach manueller Prüfung und optionale LLM-Vorschläge zum Kategoriensystem. Hinzu kommen Kategorienvergleich, Einrichtungskontrolle, formatierte und durchsuchbare Ergebnisse sowie Fortschritt innerhalb einzelner Module im Browser und optional über Telegram.

Zusätzlich: überarbeitete Clusterdiagramme und Konfusionsmatrix, anklickbare Personen–Kategorien-Übersicht sowie Fallklassen im HTML. Optionale Cloud-Anbieter (Ollama Cloud, OpenAI, Anthropic, Hugging Face) sind durch eine standardmäßig aktive DSGVO-Sperre geschützt. Schlüssel werden getrennt verwaltet. Drei zusätzliche echte Ollama-Cloud-Anfragen prüfen den neuen Transport; für die drei anderen Anbieter wurden Antwortformate und Fehlerbehandlung mit Mocks geprüft, kein Live-Zugriff.

Ursprüngliche Eingaben und Ergebnisse bleiben erhalten. Folgeläufe und Vorschläge starten nur ausdrücklich; sie trainieren das Modell nicht. Die öffentliche Konfiguration bleibt auf lokales Ollama und vollständig künstliche Beispieldaten eingestellt. [Anleitung mit Screenshots](PRUEFUNG_UND_FOLGELAUF.md).

Geprüft mit 95 Python- und acht Browserlogik-Tests sowie zwei zusätzlichen Ollama-Cloud-Abläufen mit künstlichen Daten. Die Windows-Schlüsselspeicherung wurde außerhalb des eingeschränkten Sandbox-Kontos geprüft. Eine neue vollständige Installation wurde für diesen Stand nicht angelegt; die vorherige Installationsprüfung unten bezieht sich auf 0.2.0-beta.1. [Testbericht](TEST_REPORT.md).

Beim Wechsel die Oberfläche nach Abschluss oder Pause eines Laufs schließen, Programmdateien aktualisieren und neu öffnen. Projekte bleiben erhalten; Prüfentscheidungen können auch für vorhandene Prüflisten erfasst werden. Nach Programmänderungen neue Analyseläufe starten, alte Checkpoints werden nicht migriert. Die öffentliche Vorabversion trägt den Tag `v0.3.0-beta.1`. Fehler bitte über GitHub Issues melden; dabei keine echten Interviewtexte, Schlüssel oder privaten Konfigurationen anhängen.

---

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
