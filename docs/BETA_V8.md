# v8 Beta: Transkription und Codierung

Diese Beta-Version verbindet die vorhandene Analyse mit Transkription und Codierung. Ein Projekt bietet zwei Einstiege: bereits codierte MAXQDA-Dateien importieren oder unter „Transkribieren / Codieren“ Material vorbereiten. Die Analysefunktionen und der Berichtseditor stehen anschließend in beiden Wegen zur Verfügung.

## Material vorbereiten

1. Audio im Bereich „Audio und Lesetext“ öffnen oder einen vorhandenen Text im Codierbereich importieren. Textimporte unterstützen die dort angebotenen Formate. Originale und Arbeitsversionen bleiben getrennt erhalten.
2. Unter „Modell einrichten / ändern“ Whisper und optional Sortformer v2 ausdrücklich zentral installieren oder einen vorhandenen Modellordner wählen. Installationen werden geprüft und von allen Projekten wiederverwendet. Audio wird lokal auf CPU verarbeitet. Beide Schritte erlauben bis 120 Minuten/2 GiB. Sortformer unterstützt maximal vier Stimmen. Die Labels sind Vorschläge, keine bestätigten Personenidentitäten. Unklare Wörter bleiben ohne Zuordnung. Ohne Sprecher-Modell erfolgt die Zuordnung manuell.
3. Lesetext anhand des Audios korrigieren, Ausschlüsse und Personenkennungen prüfen und ausdrücklich bestätigen. Mehrere Aufnahmen ergänzen das Codierprojekt. Bereits codierter Text wird dabei nicht ersetzt. Der Prüfstand wird versioniert gespeichert.
4. Im Codierbereich Kategorien anlegen oder geprüfte Vorschläge übernehmen und Originalpassagen markieren. Manuelle Zuordnungen und Memos sind möglich. Gespeicherte Codierungen enthalten das unveränderte Zitat samt Fundstelle.
5. Für LLM-Vorschläge Dokument, Vorschlagsart und prüfende Person wählen. Bei Codierung das Kategoriensystem ausdrücklich bestätigen. Jede Antwort wird strukturell und gegen das Originalmaterial geprüft. Anschließend jeden Vorschlag annehmen, bearbeiten oder ablehnen und den geprüften Satz in das Codierprojekt übernehmen. Ungeprüfte Antworten gelangen nicht in die Analyse.

## Lokal und ausdrücklich gewählte Cloud

Ollama lokal und DSGVO-relevantes Material sind Standard. Lokale Modelle müssen installiert sein; als lokal registrierte Remote-Modelle werden abgewiesen. Es gibt keinen automatischen Wechsel in die Cloud.

Für Ollama Cloud müssen Anbieter und Modell ausdrücklich gewählt, das Material als für diesen Weg geeignet eingeordnet und die Übertragung des bestätigten Transkripttexts mit Kategorien für jede Vorschlagsanfrage bestätigt werden. Audio wird dabei nicht übertragen. Der Schlüssel wird vom bestehenden Schlüsselservice verwendet; unter Windows kann er geschützt gespeichert werden. Er gehört nicht zum Projekt oder Export. Ohne gespeicherten Schlüssel ist nach einem Neustart eine erneute Eingabe erforderlich. Cloudantworten durchlaufen dieselben lokalen Inhalts- und Herkunftsprüfungen und bleiben menschlich zu prüfende Vorschläge.

## Übergabe und Berichte

„Version bestätigen und übergeben“ verlangt die Prüfung von Transkript, Personen, Ausschlüssen, Kategorien und Codierungen. Die Freigabe gilt für einen unveränderlichen Snapshot mit CSVs und Verlauf. Danach prüft der reguläre Analyseimport Personen, Kategorien und Eingaben. Optional startet der gespeicherte Workflow unmittelbar nach gültiger Übergabe; ansonsten können Module und Modell vorher in der Analyseoberfläche gewählt werden. Änderungen in der Vorbereitung verändern keine bereits erzeugten Analyseergebnisse.

CSV-Export bleibt unabhängig möglich. Im HTML-Bericht können eindeutig getrennte Deutungen mit dokumentiertem Verlauf korrigiert werden. Originalzitate, Quellen- und Personenkennungen und berechnete Tabellen sind schreibgeschützt. Gespeicherte Herkunftsverweise führen bei Änderungen zu möglichen Folgeprüfstellen; genaue Elementbezüge und lediglich verwandte Bereiche werden unterschieden. Es erfolgt keine automatische Umklassifikation oder Neuberechnung. Das ersetzt keine fachliche Prüfung.

## Speichern und Beenden

Autosave verwendet Versionskontrolle und bewahrt frühere Stände. Nach Neustart ist das Projekt wieder aufrufbar. Laufende Vorschlagsaufträge verhindern ein unbemerktes normales Beenden. Eigene Audioaufträge können im Vorbereitungsbereich beendet werden; erst die Prozessaufsicht bestätigt das Ende. Teilresultate bleiben erhalten. Ein externer Prozessabbruch kann unvollständige Arbeit hinterlassen; diese wird nicht als abgeschlossen übernommen.

## Pakete und Grenzen

Whisper-/Sprechergewichte, virtuelle Umgebungen, Zugangsschlüssel und Nutzerprojekte sind nicht Bestandteil der Pakete. Die kleinen zur faster-whisper-Bibliothek gehörenden VAD-Ressourcen sind im Standalone enthalten. Lizenzen und Anleitungen des jeweiligen separat installierten Modells gelten weiter. Python-Pakete benötigen die gepinnten Abhängigkeiten aus `requirements.txt` und `requirements-transcription.txt`. Alle drei Pakete werden an denselben endgültigen Git-Commit gebunden. Native macOS-Ausführung und externe HPC-Ausführung sind getrennte Abnahmen; die HPC-Variante enthält diesen Transkriptionsweg nicht.

Bei Rückkehr in die Analyseoberfläche kann „Dokumentzuordnung anzeigen / prüfen“ nötig sein, um die gespeicherte Zuordnung wieder sichtbar zu laden. Die Bestätigung wird nur wiederverwendet, wenn ihr Fingerabdruck mit dem aktuellen Import übereinstimmt. Bei veränderten Eingaben ist erneut zu prüfen. Die unmittelbare Startoption bei der Übergabe nutzt die gerade ausdrücklich bestätigten Personenkennungen.

Das Kontextfeld bezeichnet bei Cloudanbietern das konservative Programmbudget für Schätzung und Antwortreserve. Es konfiguriert kein Cloud-Kontextfenster; Schätzwerte sind keine gemessenen Tokenzahlen. Bei lokaler Ollama-Verarbeitung wird das konfigurierte Fenster zusätzlich an die lokale Laufzeit übergeben.

## Beta-Prüfstand

Mit Windows-Standalone wurde ein vollständiges synthetisches 14:25-Minuten-Interview mit Hintergrundgeräuschen verarbeitet: zwei Sprecherlabels, 2110 Wörter, 114 Wörter ohne eindeutige Sprecherzuordnung. Bearbeiten, Speichern, Personenprüfung, Zusammenführen benachbarter bestätigter gleicher Personen, manuelle Codierung, CSV-Export und Prozessneustart bestanden. Fachliche Kontrolle bleibt erforderlich; kein allgemeiner Qualitätsnachweis für reale Interviews.

Separat wurde Sortformer auf 120 Minuten wiederholtem synthetischem Audio vollständig auf CPU geprüft. Kein vollständiger zweistündiger Whisper-Test, kein praktischer macOS-Audiotest. Die bestehenden Analysefunktionen wurden mit synthetischen Cloudtests geprüft; der gesamte lokale Granite-Nachtest einschließlich Stabilitäts- und Sensitivitätsserien ist noch offen. Eine Beta-Kennzeichnung ersetzt diese Prüfung nicht.

Projekte werden standardmäßig in Dokumente/Qualitative Analyse/Projekte gespeichert, zentrale Modelle in Dokumente/Qualitative Analyse/Modelle. Ein explizites `--data-dir` bleibt vorrangig. Es wird keine Cloud-Synchronisation zugesichert.
