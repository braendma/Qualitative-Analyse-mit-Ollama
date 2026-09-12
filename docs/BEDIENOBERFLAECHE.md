**Vollständiger Rundgang:** [Handbuch mit Bildern und Beispielen](HANDBUCH.md). In der Oberfläche neben Telegram-Updates direkt als lokale HTML-Anleitung erreichbar.

# Lokale Bedienoberfläche

Die Oberfläche führt durch **Projekt → Eingaben prüfen → Analyse → Ergebnisse**. Sie startet den bestehenden Workflow-Runner und speichert unveränderliche Dateiversionen pro Lauf. Python- und YAML-Dateien müssen für die normale Bedienung nicht bearbeitet werden.

Eine bebilderte Schritt-für-Schritt-Anleitung findest du am Anfang der [README](../README.md#einstieg). Die folgenden Abschnitte erläutern Details und Sonderfälle.

## Programmordner und Umstieg

Die Startdateien bleiben im obersten Ordner. Programmcode und Oberfläche liegen unter `src/`, die YAML-Vorlage unter `config/`, künstliche Beispieldaten unter `demo/` und Anleitungen unter `docs/`. Die komplette Ordnerstruktur zusammenlassen.

Ein neues Programmverzeichnis ändert nicht automatisch die private Projektablage unter `%LOCALAPPDATA%\QualitativeOllama`. Bestehende Projekte bleiben dort verfügbar. Nach Änderungen am Programm einen neuen Lauf mit den geprüften Projekteinstellungen starten; frühere Ergebnisse aufbewahren.

## Einmalig einrichten und starten

1. Das gesamte GitHub-Projekt herunterladen und entpacken. Python 3.10 oder neuer und Ollama müssen installiert sein.
2. Unter Windows `Einrichtung.cmd` doppelklicken. Dies legt eine `.venv` im Programmordner an und installiert die Pakete aus `requirements.txt` aus dem Internet. Es werden keine Modelle installiert oder gestartet.
3. Ollama starten und ein geeignetes **lokales** Modell installieren. Der Speicherbedarf hängt vom Modell und dem Kontextfenster ab.
4. `Start_Oberflaeche.cmd` doppelklicken. Im Browser öffnet sich die Oberfläche. Das Startfenster während der Analyse geöffnet lassen.

Falls eine passende Python-Umgebung bereits eingerichtet ist, reicht `python -X utf8 src/local_app.py`. Auf anderen Betriebssystemen lässt sich die Oberfläche ebenfalls so starten; die Windows-Startdateien und die dauerhafte Windows-Tokenverschlüsselung sind dort nicht verfügbar.

Die Oberfläche ist nur an `127.0.0.1` gebunden und wird nicht veröffentlicht. Ein zufälliger Sitzungsschlüssel schützt ihre API. Die angezeigte Startadresse gehört ausschließlich auf diesen PC. Standardmäßig gilt die DSGVO-Sperre mit lokalem Ollama. Cloud-Anbieter sind nach ausdrücklicher Freigabe im Projekt verfügbar; siehe [Handbuch](HANDBUCH.md#datenfreigabe-anbieter-und-schlussel) und [Anbieterhinweise](KI_ANBIETER.md).

## Ein Projekt bearbeiten

- Ein eigenes Projekt anlegen oder die mitgelieferte künstliche Demo laden. Die Demo liegt separat in `demo/` und enthält 50 Codierzeilen, 43 Passagen und 12 Codepfade.
- Interviewdaten und Kategoriensystem als XLSX oder UTF-8-CSV mit Semikolon auswählen (jeweils maximal 20 MB). Die ersten fünf Datensätze werden als Vorschau angezeigt. Originaldateien werden nicht verändert.
- Text, Person, Code und gegebenenfalls Zeilen-/Passage-ID zuordnen. Das Kategoriensystem unterstützt Codepfad oder vier Hierarchieebenen, Definition, Ein-/Ausschlussregeln, weitere Codierhinweise und Ankerbeispiele. Nach der Vorschau werden die Spalten manuell zugeordnet; Code/Kategorie und Definition sind Pflicht. Fehlende Pflichtzuordnungen sperren den Start. Optionale Spalten können leer bleiben. Vollständige Codepfade müssen zu den menschlichen Codierungen passen.
- Bei Mehrfachcodierung eine verlässliche Passage-ID verwenden. Dieselbe Passage-ID muss dieselbe Textstelle derselben Person bezeichnen. Ohne solche IDs kann der Zeilenvergleich ohne Kappa verwendet werden. Über „Passage-IDs vorbereiten“ lassen sich IDs aus MAXQDA-Positionsspalten und exaktem Text vorbereiten. Mögliche Gruppen werden erst nach Bestätigung zusammengeführt; es gibt keine Ähnlichkeitsheuristik.
- Projektbeschreibung, Teilnehmende und Methodik prüfen. Modell, Kontextfenster, Antwortlimit, Temperatur und Thinking sind über Felder einstellbar. **Installierte Modelle anzeigen** fragt lediglich installierte Modelle ab und startet keine Inferenz.
- Unter **Analyse → 1. Analysemodule auswählen** einzelne Module per Häkchen auswählen. **Auswahl leeren** entfernt alle Häkchen für eine eigene Zusammenstellung. Unter jedem Modul stehen Funktion und Abhängigkeiten. Die Anzeige unter der Liste nennt die Gesamtzahl auszuführender Module sowie automatisch benötigte Vorstufen. Diese Vorstufen werden auch dann ausgeführt, wenn sie selbst kein Häkchen haben. **Einstellungen speichern & Eingaben prüfen** prüft die Daten ohne Modellaufruf und zeigt die aktiven Schritte an.

Mit **Prüfen & neuen Lauf starten** werden die aktuellen Einstellungen gespeichert, die Eingaben nochmals geprüft und die lokale Analyse gestartet. Pro Oberfläche ist jeweils ein Lauf aktiv. Der Fortschritt zeigt abgeschlossene Module und das aktuell laufende Modul; es gibt keine geschätzte Restlaufzeit.

## Textstellen aus MAXQDA vorbereiten

**Das Kopieren einer geeigneten Tabelle aus MAXQDA nach Excel ist möglich.** Ein bestimmter MAXQDA-Exportknopf ist für dieses Programm nicht vorgeschrieben. Die Tabelle muss jedoch codierte Textstellen einschließlich Herkunft und Code enthalten. Eine reine Codeliste mit Codenamen und Häufigkeiten genügt nicht.

Als regulären Weg bietet MAXQDA den Excel-Export der **Liste der codierten Segmente** an, auch über **Reports → Exportieren → Liste der codierten Segmente**. Zuerst die gewünschten Dokumente und Codes für die Segmentsuche auswählen und den Umfang kontrollieren. Die verfügbaren Exportoptionen sind in der [MAXQDA-Anleitung zum Segmentexport](https://www.maxqda.com/de/hilfe/segment-suche/codierte-segmente-ausdrucken-und-exportieren) beschrieben. Menübezeichnungen können je nach Version abweichen. Die resultierende Tabelle anschließend auf die unten beschriebene Struktur prüfen und gegebenenfalls anpassen; nicht jede Exportvariante entspricht ihr automatisch.

### Benötigte Tabellenspalten

| Beispielname | Inhalt | Pflicht |
|---|---|---|
| `Dokumentname` | Dokument-/Personenkennung für diese Textstelle, in jeder Zeile ausgefüllt | Ja |
| `Code` | Genau ein vollständiger Codepfad, mit ` > ` zwischen den Ebenen | Ja |
| `Segment` | Vollständiger Originaltext der codierten Stelle | Ja |
| `segment_id` | Eindeutige ID pro Codierzeile; entsteht ohne zugeordnete ID-Spalte automatisch | Optional |
| `PassageID` | Stabile ID pro tatsächlicher Textstelle, bei Mehrfachcodierung in mehreren Zeilen wiederholt | Im Modus Mehrfachcodierung |

Die Spalten dürfen anders heißen; sie werden in der Oberfläche zugeordnet. Ein Codepfad muss exakt zu einem Pfad im separaten Kategoriensystem passen. Für die Herkunft eine eindeutige Dokument-/Personenkennung verwenden, keine bloße Dokumentgruppe. Falls mehrere Personen in einem Dokument vorkommen, muss die Personenkennung entsprechend aufbereitet werden.

### Eine Zeile je Codierung

Künstliches Strukturbeispiel: Dieselbe Passage hat zwei Codes. Beide Zeilen besitzen dieselbe Passage-ID und denselben Text, aber verschiedene Zeilen-IDs.

```csv
segment_id;PassageID;Dokumentname;Code;Segment
Z001;P001;Interview_01;Organisation > Unterstützung;Die Betreuung half uns beim Vergleich unserer Messwerte.
Z002;P001;Interview_01;Zusammenarbeit > Gruppe > Austausch;Die Betreuung half uns beim Vergleich unserer Messwerte.
```

Mehrere Codes in einer Sammelzelle oder zusätzlichen Codespalten werden nicht automatisch auf mehrere Codierzeilen verteilt. Auch eingerückte oder über mehrere Zeilen verteilte Codehierarchien werden nicht automatisch ergänzt. Trage den vollständigen Pfad sowie Dokumentname und Text für jede Codierung ein.

**Passage-ID und Zeilen-ID erfüllen unterschiedliche Aufgaben.** Gemeinsame Passage-IDs nur vergeben, wenn es nachweislich dieselbe Textstelle derselben Person ist. Die Herkunft mit ausreichend genauen Start-/Endpositionen kann bei der Zuordnung helfen; gleiche Absatznummern oder gleiche Wörter allein beweisen keine identische Textstelle. Überlappende, unterschiedlich lange Segmente nicht allein deshalb zusammenfassen. Ohne verlässliche Passage-IDs den Zeilenvergleich ohne Kappa wählen und das Feld Passage-ID unzugeordnet lassen.

### XLSX direkt verwenden oder CSV speichern

1. Die Tabelle in Excel so aufbereiten, dass die erste Zeile eindeutige Spaltenüberschriften enthält. Vorgeschaltete Titelzeilen entfernen. Keine verbundenen Zellen oder leeren Fortsetzungsfelder für Dokumentnamen und Codes verwenden.
2. Die **XLSX-Datei direkt auswählen**. Bei mehreren Tabellenblättern fragt die Oberfläche nach dem gewünschten Blatt. CSV bleibt als Alternative möglich. Die Originaldatei wird unverändert lokal kopiert; die Anwendung erstellt intern eine CSV für den bestehenden Runner. Es wird nichts an einen Cloud-Dienst gesendet.
3. Bei CSV muss **Semikolon** als Feldtrennzeichen verwenden. Die Bezeichnung des Excel-Dateityps allein garantiert das tatsächliche Trennzeichen nicht. Bei Bedarf die Kopfzeile in einem Texteditor prüfen: `Dokumentname;Code;Segment`. Nicht pauschal Kommas oder Semikolons im gesamten Text ersetzen.
4. Zeilenumbrüche innerhalb einer Passage müssen in einer Excel-Zelle bleiben. Der CSV-Export muss Felder mit Zeilenumbrüchen, Semikolons oder Anführungszeichen korrekt in Anführungszeichen setzen. Keine Quellenangabe nachträglich an den Segmenttext anhängen; Herkunft gehört in eigene Spalten.
5. Die XLSX oder CSV in der Oberfläche auswählen, die Vorschau kontrollieren, Spalten zuordnen und **Einstellungen speichern & Eingaben prüfen** ausführen. Diese Prüfung startet keine Modellanfrage.

**XLSX-Hinweise:** Die erste Zeile enthält die Überschriften. Vollständig leere Datenzeilen und leere Randspalten werden ausgelassen; einzelne leere Zellen bleiben leer. Formeln und Excel-Fehler werden mit Zelladresse zurückgewiesen: in einer Kopie zuerst durch Werte ersetzen. Text und Zeilenumbrüche bleiben erhalten. IDs möglichst als Text speichern; einfache Zahlenformate wie `0000` erhalten ihre führenden Nullen. Sonstige Zahlen- und Datumsformate werden als Werte, nicht als Excel-Anzeige übernommen. Alte `.xls`-Dateien vorher als `.xlsx` speichern. Maximal 100.000 Zeilen, 200 Spalten, 100 MB entpackte XLSX-Daten und 20 MB interne CSV. Der direkte Kommandozeilen-Runner erwartet weiterhin CSV; der XLSX-Import erfolgt in der Oberfläche.

Das **Kategoriensystem** ist eine zweite Datei mit Kategorien und Definitionen. Die Interviewdatei enthält die bereits vergebenen Codes und die zugehörigen Textstellen; sie ersetzt das Kategoriensystem nicht.

## Pausieren, fortsetzen und Ergebnisse öffnen

**Nach diesem Modul pausieren** lässt das aktuelle Modul abschließen und pausiert vor dem nächsten. Ein bereits laufender Modellaufruf wird nicht hart abgebrochen. Bei einer Pause im letzten Modul kann der Lauf regulär fertig werden.

**Diesen Lauf fortsetzen** verwendet die ursprüngliche Dateiversion und die ursprünglichen Einstellungen dieses Laufs. Spätere Projektänderungen beeinflussen diese Wiederaufnahme nicht. Geänderte Programmdateien, Abhängigkeiten oder Ergebnisdateien führen weiterhin zur Ablehnung; dann ist ein neuer Lauf erforderlich. Erhaltene Teil-Checkpoints vermeiden erneute erfolgreiche Modellaufrufe. Details: [ROBUSTNESS.md](ROBUSTNESS.md).

Nach erfolgreichem Lauf wird `gesamtbericht.html` automatisch erzeugt. **Interaktiven Bericht öffnen** bietet Suche, Abschnittsnavigation und eingebettete Diagramme. Die Datei bleibt beim Lauf gespeichert und funktioniert nach dem Herunterladen offline. Einzeldateien lassen sich aufklappen. Unter **Ergebnisse** erscheinen Berichte, JSON-Dateien, Grafiken und die Prüfliste. Markdown wird formatiert dargestellt, geeignete JSON-Ergebnisse sind durchsuchbar. **Codierungen im Projekt prüfen** öffnet die automatisch gespeicherten Entscheidungen mit zusätzlichem Excel- und JSON-Export. Nach Abschluss der kritischen Fälle können ein versionierter Folgelauf oder optionale Kategorienvorschläge vorbereitet werden. Die separate Offline-HTML-Prüfliste benötigt weiterhin manuelles Speichern und Laden; ein automatischer MAXQDA-Rückimport ist nicht enthalten.

Die [bebilderte Anleitung zu Prüfung und Folgelauf](PRUEFUNG_UND_FOLGELAUF.md) erklärt Speicherung, Konflikte, Kategorienvergleich, Einrichtungstest und detaillierten Fortschritt.

Bestehende CLI-Läufe außerhalb der Projektverwaltung werden in dieser ersten Version nicht automatisch importiert. Wird das Startfenster beendet, können laufende Prozesse weiterarbeiten; Telegram-Updates sind dann nicht mehr garantiert. Nach einem Neustart erkennt die Oberfläche aktive Runner-Prozesse und lässt keine parallele Wiederaufnahme zu. Das Startfenster deshalb bis zum Abschluss bzw. zur Pause geöffnet lassen.

## Telegram optional einrichten

Telegram wird ausschließlich bei Aktivierung und für die ausgewählten Ereignisse angesprochen. Für die Einrichtung werden ein Bot-Token von **@BotFather** und eine Ziel-Chat-ID benötigt. Den eigenen Bot zunächst in Telegram öffnen und `/start` senden. Die Chat-ID ist nicht die Telefonnummer. Wer bereits einen Bot verwendet, kann dessen vorhandene Chat-ID übernehmen. Die Oberfläche liest keine Telegram-Konversationen und verändert keine Webhooks oder Bot-Einstellungen.

1. Unter **Telegram-Updates** den Token eingeben oder eine kleine Textdatei mit ausschließlich dem Token laden.
2. Chat-ID eintragen. Auswählen, ob Meldungen zu Start, Fortschritt, Abschluss, Fehler oder Pause gesendet werden sollen.
3. Einstellungen speichern. Ein leeres Tokenfeld behält den vorhandenen Token bei; ein neuer Token ersetzt ihn. **Token entfernen** löscht den gespeicherten Token und deaktiviert die Meldungen.
4. Bei Bedarf **Testnachricht senden** klicken. Diese Schaltfläche sendet ausdrücklich eine allgemeine Testmeldung an den gespeicherten Chat, auch wenn automatische Meldungen ausgeschaltet sind.

Ohne dauerhafte Speicherung bleibt der Token nur für die aktuelle Serversitzung im Speicher. Unter Windows kann er mit DPAPI für das aktuelle Benutzerkonto verschlüsselt gespeichert werden. Es gibt keinen Rückfall auf unverschlüsselte Tokenspeicherung. Der Token wird nicht in Projekt-YAMLs, Berichte, Browser-Speicher oder API-Antworten geschrieben. Ein Import übernimmt ihn zunächst nur in das verdeckte Eingabefeld; erst Speichern aktualisiert die Einstellung.

Fortschrittsmeldungen enthalten einen Balken mit Prozent und Einheiten für das aktuelle Modul sowie getrennt die Zahl abgeschlossener Module. Modellantworten, gleichzeitig aktive Anfragen und geprüfte wiederverwendete Zwischenergebnisse erscheinen, soweit diese Zähler vorliegen. Fehlt eine belastbare Gesamtzahl, steht dort „Fortschritt noch nicht beziffert“. Der Balken beschreibt das einzelne Modul, nicht die Gesamtlaufzeit.

Veränderte Zwischenstände innerhalb eines Moduls werden höchstens alle zwei Minuten gesendet; neue Modulabschlüsse zusätzlich zeitnah. Beim Modulwechsel entstehen keine doppelten Fortschrittsmeldungen und keine falsch zugeordneten Zähler des vorherigen Moduls. Verwendet werden ausschließlich fest vorgegebene Modulbezeichnungen und allgemeine Zähler. Projektnamen, Texte, Kategorien des Kategoriensystems, Pfade und technische Fehlerdetails werden nicht gesendet. Fehler beim Benachrichtigen werden getrennt angezeigt und stoppen die Analyse nicht. Meldungen werden nicht dauerhaft gepuffert oder wiederholt; dadurch werden bei unsicheren Netzwerkantworten keine automatischen Mehrfachsendungen ausgelöst. Die Umsetzung verwendet Telegram [`sendMessage`](https://core.telegram.org/bots/api#sendmessage).

## Wo liegen meine Daten?

Unter Windows standardmäßig in `%LOCALAPPDATA%\QualitativeOllama`. Darin liegen `projects/` mit Eingabekopien, Einstellungen, Revisionen und Läufen sowie separat `telegram.private.json` mit Einstellungen und gegebenenfalls verschlüsseltem Token. Die Daten gehören außerhalb öffentlicher Repositories. Für eine Sicherung die Oberfläche nach Abschluss eines Laufs schließen und den Projektordner kopieren. Die Telegram-Verschlüsselung ist an das Windows-Benutzerkonto gebunden.

Ein anderer lokaler Speicherort kann mit `python src/local_app.py --data-dir PFAD` gewählt werden. Eine vertrauenswürdige lokale YAML-Vorlage lässt sich mit `--config PFAD` verwenden. Die Oberfläche erlaubt keine hochgeladenen ausführbaren Pipeline-Konfigurationen. Die Ollama-Modellliste stammt aus dem lokalen [`/api/tags`-Endpunkt](https://docs.ollama.com/api/tags).

## Tests und Grenzen

Die Tests prüfen Projektrevisionen, Spaltenzuordnung, Zugriffsgrenzen, Tokenwechsel und Entfernung, DPAPI unter Windows, generische Benachrichtigungen sowie Start/Pause/Wiederaufnahme des echten Runners mit ersetztem Modelltransport. DPAPI benötigt Zugriff auf das Windows-Benutzerprofil und kann in eingeschränkten Sandbox-Konten scheitern. Dann Sitzungsspeicherung verwenden oder die Anwendung unter dem normalen Benutzerkonto ausführen. Testergebnisse stehen in [TEST_REPORT.md](TEST_REPORT.md).

Dies ist eine erste lokale Oberfläche mit Windows-Startdateien. Python, Ollama und Modelle sind noch nicht in einem eigenständigen Installer gebündelt. Die Prüfung ersetzt weder die methodische Entscheidung über Kategorien und Codierungen noch die fachliche Prüfung der erzeugten Befunde.


## Personen und Interviewteile vor dem Start zuordnen

Ein Dokument ist nicht automatisch eine Person. Unter „Eingaben prüfen“ zuerst die Text-, Code- und Dokumentspalte wählen. Danach „Dokumentzuordnung anzeigen / prüfen“ öffnen. Zusammengehörige Interviewteile bekommen dieselbe Personenkennung; verschiedene Personen brauchen verschiedene Kennungen. Beispiel: Interview_A_Teil1 und Interview_A_Teil2 erhalten P01, Interview_B erhält P02. Drei Dokumente ergeben so zwei Personen.

Die angezeigte Personenzahl und alle Zuordnungen ausdrücklich bestätigen. Ohne diese Bestätigung startet die Oberfläche keine Analyse. Originalspalten und Segment-IDs bleiben erhalten. Nach Datei- oder Spaltenwechsel ist die Bestätigung erneut erforderlich. Alte Berichte mit falscher Personenabgrenzung benötigen einen neuen vollständigen Lauf. Folgeläufe nach manueller Codeprüfung übernehmen die nachweislich bestätigten Personen des Ursprungslaufs.



## Fortschrittsanzeige

Der obere Balken zählt vollständig abgeschlossene Module. Da die Module unterschiedlich lange dauern, ist er keine Schätzung der verbleibenden Laufzeit. Darunter zeigt das aktive Modul seine abgeschlossenen Arbeitsschritte und einen Prozentwert, wenn eine Gesamtzahl bekannt ist. Ohne Gesamtzahl erscheint eine Aktivitätsanzeige mit dem ausdrücklichen Hinweis, dass kein Prozentwert verfügbar ist. Antwortzähler und Zeitstempel helfen dabei, laufende Verarbeitung von einer unveränderten Anzeige zu unterscheiden. Eine länger dauernde Anfrage ist allein kein Fehlernachweis.

Die Zusammenfassung meldet in neuen Läufen jede abgeschlossene Clusterzusammenfassung und anschließend die Gesamtzusammenfassung als eigenen Schritt. Wiederverwendete geprüfte Ergebnisse zählen als erledigt; eine fehlgeschlagene Gesamtzusammenfassung zählt nicht als abgeschlossen.


Fortschritt bei SWOT: Die reguläre SWOT zählt abgeschlossene Kategorien, Meta-SWOT die vier Dimensionen Stärken, Schwächen, Chancen und Risiken. Eine Kategorie oder Dimension kann mehrere Modellanfragen benötigen. Die Prozentzahl beschreibt erledigte Einheiten, nicht den Zeitanteil. Für eingefrorene ältere Läufe ohne Gesamtzahl bleibt es bei einer ausdrücklich gekennzeichneten Aktivitätsanzeige.
