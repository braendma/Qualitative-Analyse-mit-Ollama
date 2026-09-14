# 0.4.0-beta.1 · 13. September 2026

Diese Beta ergänzt nachvollziehbare Personenzuordnung und Hilfe bei größeren Analysen. Ein Quelldokument zählt erst nach ausdrücklicher Zuordnung als Person; mehrere Interviewteile können gemeinsam ausgewertet werden. Oberfläche und Kommandozeile prüfen die Zuordnung vor der Analyse. Veränderte Daten erfordern eine neue Bestätigung.

- Herkunftsdetails der Gesamtsynthese lösen technische Kennungen in verständliche Analyse-Namen auf. Gespeicherte Originaltextstellen sind im HTML aufklappbar; fehlende oder nur mittelbare Belegzuordnungen werden offengelegt. Bestehende Analysedaten werden beim erneuten HTML-Export nicht verändert.
- Zehn Themenhilfen und Ergebnisbeispiele für alle 15 Module, mit künstlichen Tabellen und Bildern direkt an der Oberfläche.
- Lesbare Modul-Prompts mit Systemanweisung, Aufgabentext und gemeinsamen Regeln. Bestehende Läufe zeigen ihre gespeicherte Konfiguration. Die Ansicht setzt keine Studiendaten ein und ist kein vollständiges Anfrageprotokoll.
- Fehlerhilfe für Speicher, Kontext, Antwortvalidierung, Aufrufbudget, Verbindung, Zugang und Kontingent; Knopf zur passenden Einstellung. Erneute Eingabeprüfung speichert gültige Einstellungen, startet aber keinen Lauf.
- Das Synthese-Aufrufbudget ist im Formular einstellbar. Vor jeder bekannten Verdichtungsrunde wird der Mindestbedarf geprüft. Spätere Runden und Reparaturbedarf lassen sich nicht vollständig vorhersagen.
- Begrenzte Parallelität für unabhängige SWOT-Kategorien und Personenanalysen. Erfolgreiche Teilergebnisse bleiben auch bei Fehlern anderer Einheiten erhalten; fehlgeschlagene Teile werden nicht als erfolgreich gezählt.
- Große Personenvergleiche, Meta-SWOT, Kontrast-, Ambivalenz-, Zusammenhangs- und Beleganalysen nutzen bei Bedarf dokumentierte Teilprüfungen bzw. Verdichtungen. Grenzen blockübergreifender Aussagen und mögliche Detailverluste werden ausdrücklich benannt.
- Gemeinsame Clusterkontexte werden in Personenprompts einmal mit eindeutigen Referenzen übertragen; Originaltexte und Zuordnungen bleiben erhalten.
- Fortschritt in Oberfläche und Telegram trennt Modulabschluss und aktuelle Arbeitseinheiten. Verdichtungsebenen, letzte Anfrage/Antwort und wiederverwendete Teile werden eingeordnet. Unbekannte Gesamtzahlen werden nicht geschätzt. Lange unveränderte Anfragen können nach zehn Minuten erneut gemeldet werden.

**Umstieg:** Laufende lokale Analysen zunächst abschließen. Nach dem Update einen neuen Lauf erstellen und Personenzuordnung prüfen. Die strenge Wiederaufnahmeprüfung verhindert, dass alte Ergebnisse mit einer neuen Programmversion vermischt werden. Private Eingaben und Konfigurationen beim Aktualisieren erhalten.

**Prüfung und Grenzen:** 203 Python- und 21 JavaScript-Tests mit künstlichen Daten bestanden unter Windows. Zusätzlich Browserprüfungen für 27 Beispielknöpfe, alle Modul-Prompts, acht Fehlerziele, Tastaturbedienung und mobile Darstellung. Frische Installation und HTTP-Start werden für Windows und macOS durch GitHub Actions geprüft; maßgeblich ist der erfolgreiche Prüflauf am Release-Commit. Das ist kein Nachweis gleicher Modellleistung auf jeder Hardware. Die automatische Parallelitätsschätzung benötigt NVIDIA; auf macOS zunächst eine Anfrage verwenden. API-Schlüssel werden unter macOS nur für die Sitzung gespeichert. Keine neue Live-Prüfung von OpenAI, Anthropic oder Hugging Face und kein empirischer Nachweis einer allgemeinen Qualitätssteigerung.


Zwei ergänzende lokale Funktionstests mit granite4.2:30b (Thinking low, 12.288 Kontexttokens) verglichen wiederholte Clusterkontexte mit der Referenztabelle an vier erfundenen Textstellen. Beide Antworten enthielten dieselben vier gültigen Beleg-IDs sowie Unterrichtsfreude, Einkommen, Arbeitsbelastung und soziale Motivation. Die neue Anfrage war in diesem Beispiel kleiner (4.626 statt 5.222 UTF-8-Bytes). Das ist kein Qualitätsbenchmark: Beide Antworten verschärften eine Motivabwägung stellenweise zu einem Gegensatz mit „ausschließlich sozialer Motivation“, den der Ausgangstext nicht trägt. Eine fachliche Prüfung bleibt erforderlich; die Referenztabelle allein verhindert solche Deutungen nicht.

# 0.3.5 · Beta · Robustere Zusammenfassungen und Antwortreparatur

**Kontextprüfung vor dem Start:** Zu große bereits bekannte Anfragen sperren den Lauf mit konkreten Abhilfen. Hinweise machen knappen Reparaturplatz und die unbekannte Größe späterer Modellbefunde sichtbar. Die Prüfung benötigt keine Modellanfrage.

Zu große Eingaben für die Cluster- und Gesamtzusammenfassung werden in passende Teile zerlegt und stufenweise verdichtet. Jeder Eingabeteil wird verarbeitet; es werden keine überzähligen Textstellen einfach abgeschnitten. Die Verdichtung kann Details verlieren und ersetzt keine Prüfung am Original. Zahl der Teile und Stufen stehen im Laufprotokoll. Diese Änderung betrifft die Zusammenfassung, nicht sämtliche Analysearten.

Abgebrochene kurze Zwischenzusammenfassungen erhalten bis zu drei Versuche mit geprüftem Antwortbudget. Reicht das nicht, wird der betroffene Teil begrenzt weiter aufgeteilt. Vollständige Zwischenstände werden gespeichert und bei unveränderten Eingaben und unverändertem Programmstand wiederverwendet. Leere Antworten, fehlende Verkleinerung oder ein unmögliches Kontextbudget brechen mit einem Fehler ab.

Die Reparatur ungültiger Codierantworten erhält wieder die ursprüngliche Textstelle und das Codebuch einschließlich der zugeordneten Regeln. Die anschließende Prüfung erlaubter Codes und IDs bleibt bestehen. Auch die Reparaturanfrage muss ins Kontextfenster passen; das Programm kürzt dafür keine Belege oder Regeln stillschweigend.

**Umstieg:** Vor dem Update laufende lokale Auswertungen abschließen. Nach dem Update einen neuen Lauf starten; alte Ergebnisse bleiben lesbar. Die strenge Prüfung beim Wiederaufnehmen lässt keine Vermischung unterschiedlicher Programmstände zu. Private Konfigurationen und Dateien beim Aktualisieren behalten.

Windows- und Mac-Starter bleiben im Paket enthalten. Sie verwenden denselben Analysecode. Die Änderungen sind keine neue Qualitätsmessung des Modells; technische Tests und Grenzen stehen in [INSTALLATION_TEST.md](INSTALLATION_TEST.md).

# 0.3.4 · Beta · Parallele lokale Ollama-Anfragen

Die Auswahl „Gleichzeitige Anfragen“ aktiviert nun die Verarbeitung: 1 bleibt Standard; ab 2 startet eine eigene lokale Ollama-Instanz mit der gewählten Zahl an Slots. Frische Speicherprüfung vor dem Start, höchstens 8, keine Cloud-Parallelisierung. Clustering, Code-Verifikation und Blindcodierung verarbeiten unabhängige Einheiten parallel. Ergebnisreihenfolge, Passage-Gruppen und geprüfte Zwischenstände bleiben erhalten. Fortschrittszählung und Rohantwortprotokolle sind gegen gleichzeitige Schreibzugriffe geschützt. Die eigene Instanz endet mit dem Workflow; bestehende Server bleiben erhalten.

Prüfung: 119 Python-Tests, zehn JavaScript-Tests und Browserprüfung. Lokaler Test mit Granite 4.2:8b, zwei gleichzeitig aktiven Ollama-Slots und 4.096 Tokens Kontext je Anfrage. Kein allgemeiner Benchmark und keine Qualitätsmessung. Handbuch und Bildschirmabbildung aktualisiert.

Beim Update Programmdateien ersetzen, private Projekte und Konfigurationen behalten und einen neuen Lauf beginnen. Voreinstellung bleibt eine Anfrage. 0.3.4 folgt dem dreiteiligen Versionsschema.

---

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


Die Belegprüfung beschränkt das angeforderte JSON-Antwortformat auf die IDs des jeweiligen Prüfblocks. Auch danach werden alle Zuordnungen validiert. Scheitert die Reparatur einer ungültigen Antwort, folgt höchstens eine neue Anfrage mit der vollständigen ursprünglichen Eingabe. Bleiben IDs ungültig, stoppt das Modul mit Fehler; Gegenbelege werden nicht still entfernt. Anbieter müssen das Antwortschema tatsächlich unterstützen; die nachträgliche Prüfung gilt unabhängig davon.


## Fortschrittsanzeige

Der obere Balken zählt vollständig abgeschlossene Module. Da die Module unterschiedlich lange dauern, ist er keine Schätzung der verbleibenden Laufzeit. Darunter zeigt das aktive Modul seine abgeschlossenen Arbeitsschritte und einen Prozentwert, wenn eine Gesamtzahl bekannt ist. Ohne Gesamtzahl erscheint eine Aktivitätsanzeige mit dem ausdrücklichen Hinweis, dass kein Prozentwert verfügbar ist. Antwortzähler und Zeitstempel helfen dabei, laufende Verarbeitung von einer unveränderten Anzeige zu unterscheiden. Eine länger dauernde Anfrage ist allein kein Fehlernachweis.

Die Zusammenfassung meldet in neuen Läufen jede abgeschlossene Clusterzusammenfassung und anschließend die Gesamtzusammenfassung als eigenen Schritt. Wiederverwendete geprüfte Ergebnisse zählen als erledigt; eine fehlgeschlagene Gesamtzusammenfassung zählt nicht als abgeschlossen.

Fortschritt aller Module geprüft: separate Vorbereitung, Analyse und Abschlussphasen; untergeordnete Prüfblöcke überschreiben keine Personen-/Dimensionszähler. Übersicht: FORTSCHRITT.md. Vorhandene eingefrorene Läufe behalten ihre bisherigen Daten; fehlende Prozentwerte werden ausdrücklich als unbekannt angezeigt.
