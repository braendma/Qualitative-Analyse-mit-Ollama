# Codierungen prüfen und weiterarbeiten

Dieser Ablauf gehört zur lokalen Oberfläche. Voraussetzung ist ein abgeschlossener Lauf mit dem Modul **Prüfliste der Codierungen** und seinen Vorstufen. Die Beispiele und Screenshots zeigen ausschließlich künstliche Daten und erfundene Beurteilungen.

## Entscheidungen im Projekt speichern

1. Unter **Ergebnisse** beim gewünschten Lauf **Codierungen im Projekt prüfen** anklicken.
2. Zunächst die angezeigten kritischen Fälle bearbeiten. Originaltext, bisherige Codes und Modellvorschlag vergleichen; bei Bedarf **Modellbegründung und Belege** aufklappen.
3. **Ursprüngliche Codes beibehalten**, **Modellcodes übernehmen** oder **Codes selbst festlegen** wählen. Bei eigener Zuordnung lassen sich mehrere vorhandene Codes mit Strg bzw. ⌘ auswählen.
4. Eine Begründung und unter **Geprüft von** einen Namen oder ein vereinbartes Prüfkürzel eintragen. Erst damit gilt ein Fall als abgeschlossen. Ein Zwischenstand mit leeren Feldern kann bereits gespeichert werden.
5. Auf **Im Projekt gespeichert · Prüfversion …** achten. Änderungen werden nach kurzer Eingabepause automatisch gespeichert. **Jetzt speichern** speichert sofort.

![Prüfansicht mit Speicherstatus, Suche und Export](screenshots/05-pruefentscheidungen.jpg)

Die Suche und **Nur kritische Fälle anzeigen** helfen bei der Auswahl. Pro Seite erscheinen höchstens 20 Fälle. Du kannst die Oberfläche später erneut öffnen und beim selben Lauf weiterarbeiten. Jede Speicherung erhält eine eigene Prüfversion; Originalcodierungen und Analyseergebnisse bleiben erhalten.

**Bei einem Speicherkonflikt:** Die Oberfläche überschreibt Änderungen aus einem anderen Fenster nicht. **Entwurf als JSON sichern** verwenden, dann die Seite neu laden und die Prüfliste wieder öffnen. Den gesicherten Entwurf zum Abgleich behalten. Es gibt derzeit keinen automatischen Zusammenführungs- oder Importdialog für solche Entwürfe in der Projektansicht.

## Excel und JSON exportieren

**Prüftabelle als Excel exportieren** enthält Originaltexte, ursprüngliche und modellbasierte Codes, finale Entscheidungen, Begründungen, Prüfkürzel und Abschlussstatus. Die Tabelle hat Filter, fixierte Überschriften und Textzellen; Inhalte werden nicht als Excel-Formeln ausgeführt. Texte über 32.767 Zeichen pro Zelle oder unzulässige Steuerzeichen führen zu einer erklärten Ablehnung statt stiller Kürzung. Die vollständigen Originaltexte bleiben in `review_queue.json`; **Entwurf als JSON sichern** bewahrt die Entscheidungen.

Excel ist für fachliche Sichtung und Dokumentation gedacht. Änderungen in einer exportierten Excel-Datei werden nicht automatisch zurückübernommen. Für die weitere Arbeit in der Anwendung Entscheidungen direkt in der Projektansicht bearbeiten.

Die separate Datei `review_queue.html` bleibt als Offline-Prüfliste verfügbar. Dort müssen Entscheidungen weiterhin ausdrücklich als JSON gespeichert und wieder geladen werden. Sie synchronisiert sich nicht mit den Entscheidungen in der Projektansicht. Ein automatischer Rückimport nach MAXQDA ist nicht enthalten.

## Mit geprüften Codierungen einen neuen Lauf vorbereiten

Sobald alle kritischen Fälle abgeschlossen und gespeichert sind, erscheint das Angebot zum Weiterarbeiten.

1. **Mit geprüften Codierungen einen neuen Lauf vorbereiten** anklicken.
2. Die Anzahl geänderter Fälle und unter **Änderungen einzeln ansehen** die bisherigen und finalen Codes prüfen.
3. Fälle ohne finale Codes werden aus der codierten Folgeanalyse ausgeschlossen. Falls solche Fälle vorliegen, den Ausschluss ausdrücklich bestätigen. Sie bleiben in der ursprünglichen Prüfliste und der Herkunftsdokumentation erhalten.
4. **Neue Version vorbereiten** erstellt neue Eingabekopien und wechselt zur Analyse. Dieser Schritt ruft kein Modell auf.
5. Module und Modell prüfen und dann **Prüfen & neuen Lauf starten** anklicken.

![Vorschau vor dem Erstellen einer neuen Eingabeversion](screenshots/06-folgelauf-vorbereiten.jpg)

Abgeschlossene Entscheidungen bestimmen die finalen Codemengen. Nicht vollständig geprüfte unkritische Fälle behalten ihre ursprünglichen Codes. Der Folgelauf verwendet das Kategoriensystem, den Untersuchungskontext und zunächst die Modelleinstellungen des Ursprungslaufs. Später hochgeladene, andere Dateien werden nicht versehentlich mit dessen Prüfung kombiniert.

Neue Codierzeilen erhalten neue IDs und einen Bezug auf ihre Ursprungszeilen. Der Lauf dokumentiert Ursprungslauf, Prüfversion und ausgeschlossene Fälle und trägt den Hinweis **Auswertung nach manueller Prüfung**. Alte Ergebnisse werden nicht überschrieben. Es wird kein Modell trainiert. Eine spätere Übereinstimmung mit den korrigierten Codes ist kein unabhängiger Validierungsnachweis, weil die Modellvorschläge die Beurteilung bereits beeinflusst haben können.

## Vorschläge zum Kategoriensystem erstellen lassen

Nach Abschluss der kritischen Fälle kann **Kategorienvorschläge vorbereiten** gewählt werden. Es muss mindestens eine vollständige Beurteilung vorhanden sein. Erst **Kategorienvorschläge lokal starten** im Bestätigungsfenster startet einen separaten Modelllauf mit den Modelleinstellungen des Ursprungslaufs.

Das Modell erhält das Kategoriensystem sowie Originaltexte, ursprüngliche Codes, Modellcodes, finale Entscheidungen und Begründungen der abgeschlossenen Fälle. Prüfkürzel und Personenfelder werden nicht eigens in den Vorschlagsprompt aufgenommen; Originaltexte und Notizen können dennoch sensible Inhalte enthalten. In der ausgelieferten Oberfläche erfolgt die Verarbeitung mit lokalem Ollama.

Das Ergebnis liegt als `codebook_proposals.md` und `codebook_proposals.json` bei einem eigenen Lauf. Vorschläge können Definitionen präzisieren, Kategorien abgrenzen, zusammenführen, aufteilen, ergänzen oder entfernen. Jeder Vorschlag benötigt Belegfälle, eine Begründung und Einschränkungen. Unbekannte Code- und Fallverweise werden zurückgewiesen. Auch ein Ergebnis ohne Änderungsvorschläge ist zulässig.

Die Verarbeitung erfolgt in begrenzten Prüfblöcken. Überschneidungen zwischen Vorschlägen müssen fachlich zusammengeführt werden. Zu große Eingaben führen vor den Modellaufrufen zu einem Hinweis zum Kontextbudget; Texte werden nicht abgeschnitten. Die Beurteilungen trainieren das Modell nicht, sondern stehen ihm für diesen Vorschlagslauf als Eingabe zur Verfügung.

**Übernahme bleibt eine fachliche Entscheidung:** Gewünschte Änderungen selbst in einer neuen Kategoriensystem-Datei bearbeiten und hochladen. Das Programm ersetzt weder das bestehende Kategoriensystem noch Codes automatisch durch Vorschläge.

## Kategorienversionen vergleichen

Unter **Eingaben prüfen → Kategorienversionen vergleichen** zuerst bei Bedarf **Versionen anzeigen** wählen. Eine frühere Version auswählen und mit **Änderungen anzeigen** gegen das aktuell hochgeladene und zugeordnete Kategoriensystem vergleichen. Am besten vor dem Speichern der neuen Eingaben vergleichen oder eine frühere Version ausdrücklich auswählen.

Die Vorschau nennt neue und entfernte Codepfade, geänderte Definitionen bzw. Ankerbeispiele und betroffene aktuelle Codierzeilen. Umbenennungen erscheinen als Entfernen und Hinzufügen. Der Vergleich bewertet Bedeutungsänderungen nicht automatisch und codiert keine Texte um. Entfernte Codes, die noch in den Interviewdaten stehen, müssen vor einem neuen Lauf fachlich geklärt werden.

## Einrichtung, Fortschritt und Berichte

**Analyse → Systemprüfung ohne Modellaufruf** kontrolliert Python-Pakete, Schreibrechte, freien Speicher und die lokale Ollama-Modellliste. Der gesonderte kurze Modelltest erfordert einen ausdrücklichen Start und sendet nur eine feste Testaufforderung. Er prüft keine Eignung für das vollständige Kontextfenster und ist kein Leistungsbenchmark.

Während eines Laufs zeigt der Browser abgeschlossene Module, empfangene Modellantworten und – bei Codierprüfungen und Kategorienvorschlägen – bearbeitete Zeilen, Passagen oder Prüfblöcke. „Bearbeitet“ schließt technische Fehlversuche ein; der Zähler ist kein Qualitätsmaß. Eine aktive Anfrage ohne neue Antwort kann weiterhin rechnen; es gibt keine verlässliche Restzeit-Schätzung.

Bei aktivierten Telegram-Fortschrittsmeldungen kommen zusätzlich zu Modulmeldungen höchstens alle zwei Minuten veränderte Zwischenstände. Nur allgemeine Zahlen werden versendet. Markdown-Berichte erscheinen formatiert; geeignete JSON-Ergebnisse als durchsuchbare Tabelle mit 50 Zeilen pro Seite. Große Textvorschauen sind begrenzt, die vollständige Datei ist über **Speichern** verfügbar.

Die Prüfversionen liegen innerhalb des privaten Projektordners unter `jobs/<Lauf-ID>/review/`; Folgelauf-Eingaben unter `revisions/`. Diese Ablage zusammen mit den übrigen Projektdaten sichern. Sie gehört bei echten Forschungsdaten nicht in ein öffentliches Repository.
