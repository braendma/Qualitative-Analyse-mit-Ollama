# Qualitative Analyse mit Ollama
## Ein modularer Workflow für kodierte Textdaten

**Marcus Brändle und OpenAI Codex (KI-Mitautor)**

Technischer Kurzbericht · 14. September 2026 · Bezugsstand: öffentliche Software 0.5.0-beta.1


### Zweck und Datenbasis

Die Software unterstützt die Analyse bereits kodierter Textstellen. Sie verbindet thematische Verdichtung, Fallanalysen, Kodierungsprüfung und nachvollziehbare Ergebnisberichte. Die Forschenden bestimmen Fragestellung, Materialauswahl, Kategoriensystem und Interpretation. Verarbeitet wird der exportierte Ausschnitt; nicht exportierte Interviewpassagen stehen dem Modell nicht automatisch zur Verfügung.

Codierte Segmente und Kategoriensystem werden als CSV oder XLSX eingelesen. Die Oberfläche bietet Tabellen- und Spaltenvorschauen. Benötigt werden Dokumentkennung, Codepfad und Segmenttext sowie Code beziehungsweise Kategorie und Definition. Einschlussregeln, Ausschlussregeln, Abgrenzungen und Ankerbeispiele sind optional. Mehrere Dokumentteile können ausdrücklich derselben Person zugeordnet werden. Diese Zuordnung wird vor dem Start bestätigt. Codierzeilen und mehrfach kodierte tatsächliche Passagen bleiben unterscheidbar.

### Ablauf

1. Projekt anlegen, Dateien auswählen, Spalten und Personenzuordnung prüfen.
2. Forschungsfrage und Kontext ergänzen; Modell, Module und gegebenenfalls Analyseperspektiven auswählen.
3. Eingaben und Kontextbedarf prüfen; einen eigenen Ergebnisordner festlegen und den Lauf starten.
4. Ergebnisse, Originalbelege und diagnostische Hinweise im HTML-Bericht prüfen. Modellurteile und menschliche Entscheidungen bleiben getrennt.
5. Prüfentscheidungen sichern und bei Bedarf einen neuen, versionierten Folgelauf anlegen. Bestehende Ergebnisse bleiben erhalten. Rückmeldungen trainieren das Modell nicht.

### Analyse und Diagnose

Die 15 bisherigen Module umfassen Clusterung und Zusammenfassungen, SWOT und Meta-SWOT, Personenanalyse und Personenvergleich, Kontrast-, Zusammenhangs- und Ambivalenzanalyse sowie die Gesamtsynthese. Code-Verifikation, Blind-Coding, Coding Agreement, Evidence-Audit und Prüfliste unterstützen die Kontrolle. Bei der Verifikation ist die vorhandene Codierung bekannt; beim Blind-Coding wird sie dem Modell nicht als Zielzuordnung mitgeteilt.

Fünf optionale Diagnosemodule ergänzen diesen Ablauf:

| Modul | Funktion und Grenze |
|---|---|
| Coverage und Blind Spots | Vergleicht Materialverteilung mit gespeicherten Belegreferenzen. Seltene Referenzierung ist nicht automatisch ein Qualitätsmangel. |
| Information-Loss-Audit | Markiert Referenzänderungen und mögliche Prüfpunkte zwischen Verdichtungsstufen. Er beweist keinen semantischen Informationsverlust. |
| Codebook-Diagnostik | Zeigt Codeverwendung, Zuordnungsabweichungen und mögliche Überschneidungen. Kategorien werden nicht automatisch geändert. |
| Stabilitätsanalyse | Wiederholt ausgewählte Analysen unter gleich konfigurierten Bedingungen. Übereinstimmung beweist keine Richtigkeit. |
| Sensitivitätsanalyse | Vergleicht ausdrücklich gewählte Modellparameter oder Promptvarianten. Unterschiede gelten für die geprüften Bedingungen. |

Die ersten drei Diagnosen berechnen ihre Hinweise ohne zusätzliche Modellanfragen aus vorhandenen Daten und Ergebnissen. Stabilitäts- und Sensitivitätsanalysen erzeugen zusätzliche Läufe und entsprechenden Aufwand.

### Qualitative und häufigkeitsbezogene Perspektiven

Für zehn inhaltliche Module lassen sich **Qualitativ**, **Häufigkeiten** oder **Beide** unabhängig auswählen: Clusterung, Zusammenfassungen, SWOT, Meta-SWOT, Personenanalyse, Personenvergleich, Kontrast-, Zusammenhangs- und Ambivalenzanalyse sowie Gesamtsynthese. Qualitativ bleibt die Voreinstellung. Die Häufigkeitsperspektive ergänzt Einheiten- und Personenzahlen und eine darauf bezogene Modellinterpretation. Beide Ansichten verwenden je Modul dieselbe geprüfte Zuordnungsbasis.

Gezählt werden je nach Modul vorhandene Clusterzuordnungen oder zusätzlich geprüfte Thema-Einheit-Zuordnungen. Python berechnet die Zahlen; inhaltliche Modellzuordnungen bleiben überprüfungsbedürftig. Eine Person wird innerhalb des jeweiligen Themas einmal gezählt. Sieben verschiedene zugeordnete Textstellen von drei Personen ergeben deshalb keine sieben Personen. Der jeweilige Nenner und unklare beziehungsweise fehlende Zuordnungen werden ausgewiesen. Einzelfallanalysen beziehen sich auf die betreffende Person, nicht auf einen stillschweigend erweiterten Gesamtvergleich.

Nicht jeder Befund ist zählbar. Beim Personenvergleich bleiben Typen und Unterschiede qualitativ; Ambivalenzseiten werden unabhängig geprüft. Codeüberschneidungen sind von semantischen Zusammenhängen getrennt. Für die Gesamtsynthese werden materialbezogene Aussagen eigens ausgewählt; Mengen-, Gruppen- oder Methodenbehauptungen werden nicht automatisch in Themen umformuliert. Häufigkeiten dienen einer ergänzenden Beschreibung, nicht einer Bedeutungsskala oder einer Aussage über eine Population (Maxwell, 2010; Sandelowski, 2001).

### Nachvollziehbarkeit und Grenzen

Gespeicherte Konfigurationen, Zwischenprodukte, Quellenzuordnungen und Prüfsummen dokumentieren die Verarbeitung. Promptvorlagen sind einsehbar; technische Fehler führen zu Hinweisen und können mit geprüften Zwischenständen fortgesetzt werden. Zu große Eingaben werden nicht still abgeschnitten. HTML- und Markdown-Berichte lassen sich außerhalb der Oberfläche aufbewahren; eingebettete SVG-Grafiken bleiben vergrößerbar.

Modellvorschläge können falsch, selektiv oder instabil sein. Weder Coding Agreement noch Coverage, stabile Wiederholungen oder technisch gültige Quellen ersetzen eine unabhängige Prüfung am Material. Synthetische Softwaretests belegen technische Abläufe, keine empirische Analysequalität. Der zusätzliche Aufwand hängt von Materialumfang, Kontextfenster, gewählten Perspektiven und Wiederholungen ab.

### Software und Dokumentation

Die Anwendung bietet eine lokale Browseroberfläche und einen Python-Kommandozeilenweg. Verfügbar sind ein Windows-Standalone-Paket mit enthaltener Python-Laufzeit sowie gesonderte Python-Quellpakete für Windows und macOS mit den jeweiligen Einrichtungs- und Startdateien. Die Quellpakete benötigen eine eigene Python-Installation. Ollama und Modelle werden separat bereitgestellt. Lokales Ollama ist voreingestellt; Cloud-Anbieter erfordern eine ausdrückliche Datenfreigabe und eigene Zugangsdaten. Die Source-Installationsprüfungen für Windows und macOS wurden bestanden. Ein natives Mac-Paket bleibt zurückgestellt.

- [Repository und Quellcode](https://github.com/braendma/Qualitative-Analyse-mit-Ollama)
- [Version 0.5.0-beta.1 mit Windows- und macOS-Python-Downloads](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/releases/tag/v0.5.0-beta.1)
- [Handbuch mit Bildern, Beispielen und ausführlicher methodischer Einordnung](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/blob/main/docs/HANDBUCH.md)

OpenAI Codex ist auf Wunsch des Autors als KI-Mitautor genannt. Der Beitrag umfasst Unterstützung bei Softwareentwicklung, Dokumentation und diesem Bericht. Die wissenschaftlichen Entscheidungen und die Verantwortung für eine veröffentlichte Fassung liegen bei Marcus Brändle; eine eigenständige empirische Forschungsleistung der KI wird damit nicht behauptet.

### Literatur

Maxwell, J. A. (2010). Using numbers in qualitative research. *Qualitative Inquiry, 16*(6), 475–482. doi:10.1177/1077800410364740

Sandelowski, M. (2001). Real qualitative researchers do not count: The use of numbers in qualitative research. *Research in Nursing & Health, 24*(3), 230–240. doi:10.1002/nur.1025
