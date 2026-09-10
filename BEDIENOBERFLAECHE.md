# Lokale Bedienoberfläche

Die Oberfläche führt durch **Projekt → Eingaben prüfen → Analyse → Ergebnisse**. Sie startet den bestehenden Workflow-Runner und speichert unveränderliche Dateiversionen pro Lauf. Python- und YAML-Dateien müssen für die normale Bedienung nicht bearbeitet werden.

## Einmalig einrichten und starten

1. Das gesamte GitHub-Projekt herunterladen und entpacken. Python 3.10 oder neuer und Ollama müssen installiert sein.
2. Unter Windows `Einrichtung.cmd` doppelklicken. Dies legt eine `.venv` im Programmordner an und installiert die Pakete aus `requirements.txt` aus dem Internet. Es werden keine Modelle installiert oder gestartet.
3. Ollama starten und ein geeignetes **lokales** Modell installieren. Der Speicherbedarf hängt vom Modell und dem Kontextfenster ab.
4. `Start_Oberflaeche.cmd` doppelklicken. Im Browser öffnet sich die Oberfläche. Das Startfenster während der Analyse geöffnet lassen.

Falls eine passende Python-Umgebung bereits eingerichtet ist, reicht `python -X utf8 local_app.py`. Auf anderen Betriebssystemen lässt sich die Oberfläche ebenfalls so starten; die Windows-Startdateien und die dauerhafte Windows-Tokenverschlüsselung sind dort nicht verfügbar.

Die Oberfläche ist nur an `127.0.0.1` gebunden und wird nicht veröffentlicht. Ein zufälliger Sitzungsschlüssel schützt ihre API. Die angezeigte Startadresse gehört ausschließlich auf diesen PC. Die lokale Ollama-Verbindung ist fest eingestellt; Cloud-Modelle sind in dieser Oberfläche nicht vorgesehen.

## Ein Projekt bearbeiten

- Ein eigenes Projekt anlegen oder die mitgelieferte künstliche Demo laden. Die Demo liegt separat in `demo/` und enthält 50 Codierzeilen, 43 Passagen und 12 Codepfade.
- Interviewdaten und Kategoriensystem als UTF-8-CSV mit Semikolon auswählen (jeweils maximal 20 MB). Die ersten fünf Datensätze werden als Vorschau angezeigt. Originaldateien werden nicht verändert.
- Text, Person, Code und gegebenenfalls Zeilen-/Passage-ID zuordnen. Das Kategoriensystem unterstützt vier Ebenen, Definition und Ankerbeispiel. Optionale Spalten können leer bleiben. Vollständige Codepfade müssen zu den menschlichen Codierungen passen.
- Bei Mehrfachcodierung eine verlässliche Passage-ID verwenden. Dieselbe Passage-ID muss dieselbe Textstelle derselben Person bezeichnen. Ohne solche IDs kann der Zeilenvergleich ohne Kappa verwendet werden. Die Anwendung erfindet keine Passage-IDs aus Textähnlichkeit.
- Projektbeschreibung, Teilnehmende und Methodik prüfen. Modell, Kontextfenster, Antwortlimit, Temperatur und Thinking sind über Felder einstellbar. **Ollama prüfen & Modelle laden** fragt lediglich installierte Modelle ab und startet keine Inferenz.
- Gewünschte Analyseschritte auswählen. Die Anwendung ergänzt deren benötigte Vorstufen automatisch. **Einstellungen speichern & Eingaben prüfen** prüft die Daten ohne Modellaufruf und zeigt die aktiven Schritte an.

Mit **Prüfen & neuen Lauf starten** werden die aktuellen Einstellungen gespeichert, die Eingaben nochmals geprüft und die lokale Analyse gestartet. Pro Oberfläche ist jeweils ein Lauf aktiv. Der Fortschritt zeigt abgeschlossene Module und das aktuell laufende Modul; es gibt keine geschätzte Restlaufzeit.

## Pausieren, fortsetzen und Ergebnisse öffnen

**Nach diesem Modul pausieren** lässt das aktuelle Modul abschließen und pausiert vor dem nächsten. Ein bereits laufender Modellaufruf wird nicht hart abgebrochen. Bei einer Pause im letzten Modul kann der Lauf regulär fertig werden.

**Diesen Lauf fortsetzen** verwendet die ursprüngliche Dateiversion und die ursprünglichen Einstellungen dieses Laufs. Spätere Projektänderungen beeinflussen diese Wiederaufnahme nicht. Geänderte Programmdateien, Abhängigkeiten oder Ergebnisdateien führen weiterhin zur Ablehnung; dann ist ein neuer Lauf erforderlich. Erhaltene Teil-Checkpoints vermeiden erneute erfolgreiche Modellaufrufe. Details: [ROBUSTNESS.md](ROBUSTNESS.md).

Unter **Ergebnisse** erscheinen die vorhandenen Berichte, JSON-Dateien, Grafiken und die interaktive Prüfliste. Textberichte werden in einer einfachen Textansicht angezeigt; Dateien lassen sich separat speichern. Die Prüfliste läuft in einer abgeschirmten Vorschau. Prüfentscheidungen dort ausdrücklich als JSON exportieren und bei der nächsten Bearbeitung wieder importieren. Es gibt noch keine zentrale Speicherung der Prüfentscheidungen in der Oberfläche und keinen automatischen Rückimport in MAXQDA.

Bestehende CLI-Läufe außerhalb der Projektverwaltung werden in dieser ersten Version nicht automatisch importiert. Wird das Startfenster beendet, können laufende Prozesse weiterarbeiten; Telegram-Updates sind dann nicht mehr garantiert. Nach einem Neustart erkennt die Oberfläche aktive Runner-Prozesse und lässt keine parallele Wiederaufnahme zu. Das Startfenster deshalb bis zum Abschluss bzw. zur Pause geöffnet lassen.

## Telegram optional einrichten

Telegram wird ausschließlich bei Aktivierung und für die ausgewählten Ereignisse angesprochen. Für die Einrichtung werden ein Bot-Token von **@BotFather** und eine Ziel-Chat-ID benötigt. Den eigenen Bot zunächst in Telegram öffnen und `/start` senden. Die Chat-ID ist nicht die Telefonnummer. Wer bereits einen Bot verwendet, kann dessen vorhandene Chat-ID übernehmen. Die Oberfläche liest keine Telegram-Konversationen und verändert keine Webhooks oder Bot-Einstellungen.

1. Unter **Telegram-Updates** den Token eingeben oder eine kleine Textdatei mit ausschließlich dem Token laden.
2. Chat-ID eintragen. Auswählen, ob Meldungen zu Start, Fortschritt, Abschluss, Fehler oder Pause gesendet werden sollen.
3. Einstellungen speichern. Ein leeres Tokenfeld behält den vorhandenen Token bei; ein neuer Token ersetzt ihn. **Token entfernen** löscht den gespeicherten Token und deaktiviert die Meldungen.
4. Bei Bedarf **Testnachricht senden** klicken. Diese Schaltfläche sendet ausdrücklich eine allgemeine Testmeldung an den gespeicherten Chat, auch wenn automatische Meldungen ausgeschaltet sind.

Ohne dauerhafte Speicherung bleibt der Token nur für die aktuelle Serversitzung im Speicher. Unter Windows kann er mit DPAPI für das aktuelle Benutzerkonto verschlüsselt gespeichert werden. Es gibt keinen Rückfall auf unverschlüsselte Tokenspeicherung. Der Token wird nicht in Projekt-YAMLs, Berichte, Browser-Speicher oder API-Antworten geschrieben. Ein Import übernimmt ihn zunächst nur in das verdeckte Eingabefeld; erst Speichern aktualisiert die Einstellung.

Gesendet werden nur feste Meldungstexte wie „Qualitative Analyse: Lauf abgeschlossen“ und beim Fortschritt die Zahl abgeschlossener Module. Projektnamen, Texte, Kategorien, Pfade und technische Fehlerdetails werden nicht gesendet. Fehler beim Benachrichtigen werden getrennt angezeigt und stoppen die Analyse nicht. Meldungen werden nicht dauerhaft gepuffert oder wiederholt; dadurch werden bei unsicheren Netzwerkantworten keine automatischen Mehrfachsendungen ausgelöst. Die Umsetzung verwendet Telegram [`sendMessage`](https://core.telegram.org/bots/api#sendmessage).

## Wo liegen meine Daten?

Unter Windows standardmäßig in `%LOCALAPPDATA%\QualitativeOllama`. Darin liegen `projects/` mit Eingabekopien, Einstellungen, Revisionen und Läufen sowie separat `telegram.private.json` mit Einstellungen und gegebenenfalls verschlüsseltem Token. Die Daten gehören außerhalb öffentlicher Repositories. Für eine Sicherung die Oberfläche nach Abschluss eines Laufs schließen und den Projektordner kopieren. Die Telegram-Verschlüsselung ist an das Windows-Benutzerkonto gebunden.

Ein anderer lokaler Speicherort kann mit `python local_app.py --data-dir PFAD` gewählt werden. Eine vertrauenswürdige lokale YAML-Vorlage lässt sich mit `--config PFAD` verwenden. Die Oberfläche erlaubt keine hochgeladenen ausführbaren Pipeline-Konfigurationen. Die Ollama-Modellliste stammt aus dem lokalen [`/api/tags`-Endpunkt](https://docs.ollama.com/api/tags).

## Tests und Grenzen

Die Tests prüfen Projektrevisionen, Spaltenzuordnung, Zugriffsgrenzen, Tokenwechsel und Entfernung, DPAPI unter Windows, generische Benachrichtigungen sowie Start/Pause/Wiederaufnahme des echten Runners mit ersetztem Modelltransport. DPAPI benötigt Zugriff auf das Windows-Benutzerprofil und kann in eingeschränkten Sandbox-Konten scheitern. Dann Sitzungsspeicherung verwenden oder die Anwendung unter dem normalen Benutzerkonto ausführen. Testergebnisse stehen in [TEST_REPORT.md](TEST_REPORT.md).

Dies ist eine erste lokale Oberfläche mit Windows-Startdateien. Python, Ollama und Modelle sind noch nicht in einem eigenständigen Installer gebündelt. Die Prüfung ersetzt weder die methodische Entscheidung über Kategorien und Codierungen noch die fachliche Prüfung der erzeugten Befunde.
