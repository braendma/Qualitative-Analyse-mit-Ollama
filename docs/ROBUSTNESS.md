# Fehlerbehandlung und reproduzierbare Läufe

## Kontrolliertes Beenden und lokale Prozessaufsicht

Die Oberfläche bietet **Programm beenden** an. Eine laufende Analyse kann erst
nach dem aktuellen Modul pausieren oder nach ausdrücklicher Bestätigung sofort
abgebrochen werden. Das Schließen des Browsertabs löst keinen Abbruch aus.
Neue Starts und veraltete Abbruchanfragen sind während des Beendens gesperrt.
Pro technischer Projektablage darf nur eine Appinstanz laufen; getrennte Ablagen
können unabhängig geöffnet werden.

Die App steuert ausschließlich den eigenen gestarteten Prozess und dessen
Verbindung zur bestehenden Prozessaufsicht. Sie beendet keine Prozesse allein
anhand einer gespeicherten Prozessnummer. Ein Abschlussnachweis muss zum
aktuellen Startversuch, Auftrag und Kommando passen. Fehlt er oder sind lokale
Statusdateien vorübergehend nicht lesbar, bleibt der Startschutz erhalten.
Windows-Python kann einen separaten Startprozess verwenden; dessen Nummer und
die Nummer der eigentlichen Prozessaufsicht werden deshalb getrennt behandelt.

Nach bestätigter Bereinigung erhält der Browser die Abschlussmeldung, bevor
der lokale Webserver endet. Ist der Browser nicht mehr verbunden, wartet der
Server begrenzt auf die Zustellung. Ein bloßer Verbindungsverlust wird in der
Oberfläche weiterhin nicht als bestätigter Abschluss dargestellt. Gespeicherte
Ergebnisse bleiben erhalten; die normalen Herkunftsprüfungen gelten auch bei
der Wiederaufnahme.

Diese Prozessfälle sind im Windows-Sourcebetrieb mit künstlichen Aufgaben
geprüft. Die neue Mac-Distribution ist vorerst zurückgestellt. Vorarbeiten
für verschachtelte POSIX-Prozessgruppen sind getrennt gesichert; ihre
Einbindung und native Abnahme stehen aus. Auch das ausführbare Windows-Paket
benötigt noch seine eigene Installations- und Laufzeitprüfung.

## Paketvorbereitung: Aufrufe und Grenzen (P02a)

Die gemeinsame Startlogik erhält im Sourcebetrieb das bisherige Python-Kommando einschließlich eigener Skripte. Im vorbereiteten Paketbetrieb sind ausschließlich 24 festgelegte Programmeinstiege zulässig. Geprüft wird die genaue gebündelte Datei, nicht nur ihr Name; fremde Skriptpfade werden vor dem Modellstart abgewiesen. Interne Modulaufrufe öffnen keine zusätzliche Oberfläche. Argumente, Arbeitsordner und Modul-Rückgabecodes bleiben erhalten, insbesondere `75` für die kontrollierte Pause.

Diese Änderung ist noch keine Abnahme einer ausführbaren Distribution. Am tatsächlichen Paket sind zusätzlich die Herkunft der wirklich geladenen Projektquellen, deren Übereinstimmung mit den gespeicherten Prüfsummen, die vollständige Prozessbeendigung und der Schutz vor konkurrierenden Appinstanzen zu prüfen. Die bisherigen Herkunfts- und Resumeprüfungen bleiben aktiv; ein gemockter Paketmodus ersetzt diese Paketprüfung nicht.

## Bestehende Konfigurationen, Datenfreigabe und Schlüssel

Der normale CLI-Einstieg und die kontrollierten Wiederholungspläne verwenden
dieselbe rekursive Prüfung auf Credential-Felder. Sie läuft vor neuer
Laufausgabe, Provenienz und Konfigurationssnapshot und gilt auch für
`--validate-only`. Nur `llm.api_key_env` darf als Name einer Umgebungsvariable
angegeben werden. Eingebettete Schlüssel werden abgelehnt; die Konfiguration
wird nicht still bereinigt. Vorhandene Dateien bleiben dabei erhalten.
Diese Feldprüfung erkennt nicht beliebige Geheimnisse in frei formulierten
Textwerten. Schlüssel deshalb ausschließlich über die vorgesehenen Schlüsselquellen eingeben.

Fehlende CLI-Datenfreigabe bedeutet grundsätzlich privaten Modus. Ein geerbter
Ollama-Cloud-Host oder eine Anbieterwahl allein hebt die Sperre nicht auf.
Die enge Ausnahme für frühere, ausdrücklich in der YAML gesetzte reine
`https://ollama.com`-Adressen ist in [KI_ANBIETER.md](KI_ANBIETER.md#kommandozeile)
beschrieben; ein explizites `gdpr_relevant: true` hat auch dort Vorrang.
Modellfreie Module benötigen weiterhin keinen Modellstart oder API-Schlüssel.

Reguläre Modulprozesse und Serienkinder filtern die bekannten Provider-Schlüssel
sowie den ausdrücklich konfigurierten eigenen Schlüsselnamen aus der geerbten
Umgebung. Nur der benötigte Cloudschlüssel wird weitergegeben; lokale und
modellfreie Module erhalten keinen dieser Schlüssel. Gewöhnliche
Laufzeitvariablen bleiben erhalten. Dies ist kein allgemeiner Scanner für
beliebig anders benannte geheime Umgebungsvariablen.

Die synthetische Legacyfixture enthält ausschließlich die 15 Basismodule ohne
Diagnose-, Aufwand- oder Unterlauf-Felder. Die Tests prüfen, dass Normalisierung
und Vorprüfung keine neuen Module aktivieren und die Originaldatei unverändert
lassen. Ein vorhandenes Projekt behält beim Öffnen Auswahl, bestätigte
Personenzuordnung, gespeicherte Promptvorlagen und Berichte. Eine ausdrückliche
Speicherung erzeugt eine neue Revision; alte Revisionen und Ergebnisse bleiben
erhalten, neue Diagnosen ohne Auswahl ausgeschaltet. Unveränderte Lesbarkeit
alter Berichte bedeutet keine Lockerung der Wiederaufnahme: Ein anderer
Fingerprint durch geänderte Eingaben, Einstellungen, Code oder Abhängigkeiten
führt weiterhin zur begründeten Ablehnung von Resume.

## Modellfreie Coverage und unvollständige Quellen

Die optionale Coverage prüft Datei-, Eingabe- und Konfigurationshashes. Ausfälle
ausgewählter Vorstufen erzeugen einen vorläufigen Bericht mit
`processing_status: incomplete`; er zählt nicht als abgeschlossenes Modul.
Resume berechnet die Diagnose nach Behebung der Quellen erneut. Deaktivierte
Vorstufen gelten nicht als Fehler. Ohne generatives Modul wird kein Modellserver
gestartet oder API-Schlüssel benötigt. [Diagnosegrenzen](DIAGNOSTICS.md).

Zusätzliche synthetische Grenztests prüfen Textstellen über 1 MB mit Unicode,
Semikolon, Zeilenumbrüchen und HTML-artigem Text, große Codebuchdefinitionen,
widersprüchliche Passage-IDs und beschädigte Quellenregister. Zu große generative
Eingaben werden durch die Kontextvorprüfung erklärt abgewiesen; die
deterministische Coverage kürzt sie nicht. Kennungen werden im Coverage-Markdown
als Daten maskiert. Diese Tests belegen technische Schutzmechanismen, keinen
Qualitätsbenchmark eines Modells.

## Ausführen und fortsetzen

Die öffentliche `config/config_v2.yaml` verwendet lokale Inferenz über `http://localhost:11434` mit Granite. Das Beispielmaterial ist vollständig synthetisch; siehe [DEMO_DATA.md](DEMO_DATA.md). Private Daten und projektspezifische Konfigurationen gehören in eine separate lokale Arbeitskopie.

```bash
python run_workflow.py --validate-only
python run_workflow.py --config config/config_v2.yaml
python run_workflow.py --config config/config_v2.yaml --resume demo/QualitativeAnalyse_LAUF-ID
```

Ohne `--output-dir` erstellt die CLI neben der tatsächlich verwendeten Eingabedatei einen neuen Ordner `QualitativeAnalyse_<Lauf-ID>`. Maßgeblich ist `--csv`, falls angegeben, sonst `paths.input_csv` aus der Konfiguration; relative Konfigurations-Eingaben werden gegen deren Ordner aufgelöst. Ein explizites `--output-dir` bleibt relativ zum aktuellen Arbeitsordner, wird bei Bedarf angelegt und enthält wie bisher Unterordner `<Lauf-ID>`. Vor dem neuen Lauf wird die Beschreibbarkeit geprüft. Bei einem ungültigen oder nicht beschreibbaren Ziel erfolgt eine Fehlermeldung, kein Ausweichen in AppData oder einen temporären Ordner. `--validate-only` prüft die Analysedaten, noch nicht die spätere Schreibbarkeit des Ergebnisziels. Resume verwendet unverändert den ausdrücklich angegebenen bestehenden Laufordner und prüft dessen Herkunft. Die folgenden Dateien liegen im jeweils erzeugten Laufordner. Darin stehen der Gesamtbericht, die Konfigurationskopie und das Manifest mit Lauf-ID, SHA-256-Prüfsummen, Modellparametern, Codeversion und Abhängigkeitsversionen. JSON- und Markdown-Ergebnisse werden atomar geschrieben. Ein Modul darf weder unveränderte alte Dateien noch unvollständige Ergebnisse als Erfolg melden.

Das Resume-Beispiel verwendet die öffentliche Demo-Eingabe; `LAUF-ID` durch den tatsächlich entstandenen Ordnernamen ersetzen. Bei `--csv` oder einem expliziten Ziel entsprechend dessen bestehenden Laufordner angeben. **Entwicklungsstand P01c – Datei- und Ordnerauswahl:** Über **Auf diesem Rechner auswählen** lädst du Interviewdatei oder Kategoriensystem aus der Dateiauswahl innerhalb der Oberfläche. Bei einer so gewählten Interviewdatei wird deren Ordner als Ergebnisziel übernommen, sofern du kein eigenes Ziel festgelegt hast. Mit **Ordner auswählen** wählst du ein anderes vorhandenes Ziel; **Ordner der Eingabedatei verwenden** wechselt zurück zum bekannten Eingabeordner. **Ordner prüfen** kontrolliert Verfügbarkeit und Schreibrechte. Die Auswahl zeigt Dateien auf dem Rechner der laufenden Anwendung, nicht auf einem anderen Gerät, mit dem du den Browser bedienst. Der bisherige Browserupload und das manuelle Pfadfeld bleiben verfügbar; beim Browserupload ist der ursprüngliche Dateiordner unbekannt und muss als Ziel ausdrücklich ausgewählt werden. Noch keine Freigabe neuer Windows-/macOS-Installationspakete.

Jeder neue App-Lauf bekommt im gewählten Ziel einen eigenen Ordner `QualitativeAnalyse_<Datum>_<Job-ID>/`. Analyseberichte und Moduldateien liegen darunter in `runs/<Lauf-ID>/`; Prüfentscheidungen und deren Versionen in `review/`. Geprüfte Folgeeingaben werden zusätzlich unter `review/followups/<Revision-ID>/` mit `segments.csv`, `codebook.csv`, `review_snapshot.json` und einem Inhaltsnachweis abgelegt. Eine Zieländerung gilt nur für neue Läufe. Wiederaufnahme, Berichtsaufruf und Prüfung bestehender Läufe bleiben an deren ursprünglichen Ordner gebunden. Ist er nicht verfügbar oder passt seine gespeicherte Zuordnung nicht mehr, erscheint ein Hinweis; es gibt keinen Ersatzordner in AppData. Alte Läufe behalten ihre bisherige Ablage und bleiben dort lesbar.

Die technische Projektverwaltung, Einstellungen und unveränderlichen Eingabe-/Konfigurationskopien bleiben im App-Datenordner. Für eine vollständige Sicherung nach Abschluss aller Läufe sowohl diesen Datenordner als auch die gewählten Forschungsordner sichern.

Eine Wiederaufnahme prüft zuerst Eingaben, Codebuch, Konfiguration, Programmdateien, Abhängigkeiten und bereits abgeschlossene Ergebnisdateien. Änderungen führen zu einer Ablehnung; dafür ist ein neuer Lauf vorgesehen. Logs werden fortlaufend geschrieben und sind von der unveränderlichen Ergebnisprüfung ausgenommen. Die Checkpoints der Coding-Module speichern ausschließlich vollständig validierte Segmentergebnisse. Nach einer Unterbrechung werden diese wiederverwendet; fehlgeschlagene Segmente werden erneut bearbeitet. Ein Upgrade von älteren Programmversionen setzt einen neuen Lauf voraus.

## Fehler und empirische Rückverweise

### Zwischenstände innerhalb eines Moduls

Mit `llm.partial_checkpoints: true` (Standard) speichert der Runner zusätzlich geprüfte Teilanalysen unter `<Laufordner>/_checkpoints`: je Codepfad bei Clustern und SWOT, je Cluster bei Zusammenfassungen, je Person bei Personen- und Ambiguitätsanalysen, je SWOT-Dimension bei Meta-SWOT sowie je Paket bei Relationsanalyse, Evidence-Audit und hierarchischer Synthese. Die Coding-Module behalten ihre eigenen Segment-/Passagen-Checkpoints.

Nach einem Abbruch genügt derselbe oben gezeigte `--resume`-Befehl. Fertige Teile werden ohne erneuten Modellaufruf geladen; die unterbrochene Teilanalyse wird erneut ausgeführt. Fehlerhafte, unvollständige oder veränderte Zwischenstände werden nicht übernommen. Eingaben, Prompts, Modellparameter und Programmversion müssen weiterhin übereinstimmen. Einzelne globale Modellaufrufe werden erst nach Abschluss ihres Moduls wiederverwendet.

Der gesamte Laufordner einschließlich der Zwischenstände kann Originaltexte und private Analyseergebnisse enthalten und bleibt außerhalb öffentlicher Repositories. Er sollte für die Wiederaufnahme vollständig erhalten bleiben. Direkte Aufrufe der Python-Kernfunktionen benötigen dafür einen ausdrücklich gesetzten Parameter `partial_checkpoint_dir`; beim Runner wird das Verzeichnis automatisch festgelegt. `partial_checkpoints: false` deaktiviert nur diese zusätzlichen Teil-Checkpoints.

Im Herkunftsnachweis der hierarchischen Synthese zählt `reused_batches` die wiederverwendeten Pakete. `model_calls` enthält die zur Erzeugung der erfolgreichen Pakete gespeicherten Aufrufzahlen einschließlich ihrer Reparaturversuche und wiederverwendeter Pakete; es ist kein Zähler ausschließlich neuer Netzwerkanfragen oder aller Anfragen früherer fehlgeschlagener Versuche.

- Transportfehler werden begrenzt wiederholt und danach als Fehler weitergereicht. Leere oder am Ausgabelimit abgeschnittene Antworten sind keine abgeschlossenen Analysen.
- Coding-Ergebnisse unterscheiden `processing_status: completed`, `failed` und `invalid_input`. Inhaltliches `unklar` bleibt eine getrennte Kategorie. Der Runner stoppt bei einem unvollständigen Coding-Modul; bereits validierte Checkpoints bleiben erhalten.
- Der Evidence-Audit verlangt jede erwartete Audit-ID genau einmal und ausschließlich bekannte Gegenbeleg-IDs. Nach erfolgloser Reparatur bricht er ab. Es entsteht kein positiver Befund aus einer fehlgeschlagenen Gegenbelegprüfung.
- Personenanalyse und Gesamtsynthese verwerfen empirische Einträge ohne gültige Belegverweise. Ihre freien Abschlussabsätze werden aus den erhaltenen belegten Themeneinträgen zusammengesetzt, damit ausgesonderte Aussagen nicht im Freitext weiterleben. Das garantiert referenzielle Rückverfolgbarkeit, keine semantisch richtige Interpretation durch das Modell.
- Ein gemeinsamer Segmentloader erhält externe IDs und Originaltexte. Ein ausdrücklich übergebenes Textmapping muss existieren und vollständig sowie textgleich sein. Fehlende Personenkennungen, doppelte Zeilen-IDs und unbekannte Codepfade werden vor dem Workflow abgelehnt.
- Die Hierarchie wird aus den vier Codebuchspalten gelesen. Ein- bis vierstufige Pfade bleiben vollständig erhalten, auch wenn eine Zwischenebene im Codebuch leer ist. Cluster, Zusammenfassungen und SWOT-Gruppen unterscheiden die Ausprägung von der Facette.

## Kontext und Modellausgaben

`llm.num_ctx`, `max_tokens`, `timeout_seconds`, `max_attempts` und `retry_delay_seconds` sind explizite Einstellungen. Der Client verwendet einen konservativen UTF-8-Bytewert als Eingabeschätzung, zuzüglich Ausgabereseve und Nachrichten-Overhead. Er kürzt Eingaben niemals still. Relationenkandidaten und Auditbefunde werden bei Bedarf in unabhängige Pakete geteilt (`llm.batch_items`, Standard 8). Eine einzelne zu große Einheit, ein zu großer gemeinsamer Gegenbelegbestand oder ein zu großer gemeinsamer Eingabebestand eines vorgelagerten globalen Moduls führt zu einem erklärten Abbruch. Die Gesamtsynthese kann Teilanalysen mehrstufig verdichten; Grenzen und Herkunftsnachweise sind in [EXTENSIONS.md](EXTENSIONS.md) beschrieben. Vorgelagerte globale Module behalten ihre eigenen Kontextgrenzen.

Lokale JSON-Module übergeben ein Antwortschema über Ollamas `format`-Parameter. Inhaltsprüfungen bleiben erforderlich. Cloud-Aufrufe verwenden aktuell keine erzwungenen Schemas, da Ollama Cloud diese laut [Dokumentation](https://docs.ollama.com/capabilities/structured-outputs) nicht unterstützt. Ein Cloud-Test muss separat `host: https://ollama.com` konfigurieren und den Schlüssel über `OLLAMA_API_KEY` erhalten. Die Standard-YAML bleibt lokal. TLS-Zertifikate werden gegen den System-Zertifikatsspeicher geprüft.

Die Gesamtsynthese erhält kompakte Analyseergebnisse mit Quellen- und Befund-IDs. Bereits mehrfach eingebettete Zitattexte, Metadatenregister und Zeitstempel werden aus diesem Modellinput entfernt; die vollständigen Originalausgaben bleiben im Laufverzeichnis erhalten. Das senkt den Kontextbedarf, wird bei großen Gesamtsynthesen durch eine begrenzte hierarchische Verdichtung ergänzt.

## Agreement und Relationsanalyse

Die exakte Übereinstimmung bezieht sich auf vergleichbare Codepfade. Der Bericht enthält zusätzlich Zuordnungsquote, technische Ausfälle, ungültige menschliche Codes und inhaltliche Enthaltungen. Hohe Übereinstimmung bei geringer Abdeckung darf nicht als hohe Gesamtqualität interpretiert werden.

Für Kappa müssen `coding_agreement.label_mode: single_label` und `independent_units_confirmed: true` gesetzt sein. Zusätzlich benötigt `columns.unit_id` eine vorhandene, vollständige und eindeutige Passage-ID-Spalte. Diese Bestätigung ersetzt keine methodische Prüfung der Unabhängigkeit. Ohne sie wird kein Kappa berechnet. Im Multi-Label-Modus werden unabhängige Codemengen pro expliziter Passage-ID verglichen. Technische Fehler und Enthaltungen werden getrennt ausgewiesen; Details stehen in [EXTENSIONS.md](EXTENSIONS.md).

Relationsstichproben werden personenweise gepaart gezogen. Der Output unterscheidet Relationen mit beidseitigen Belegen innerhalb derselben Person von personenübergreifenden Belegen. Er dokumentiert insgesamt mögliche, übermittelte, ausgelassene und mit einer validierten Relation beantwortete Kandidaten. Eine fehlende Relation in der Antwort ist kein Nachweis, dass keine Beziehung existiert.

Konfidenzangaben sind unkalibrierte Selbsteinschätzungen des Modells.

## Tests

```bash
python -X utf8 -m unittest discover -s tests -v
```

Die Tests benötigen keine lokale Modellinferenz. Sie prüfen die reproduzierten Fehlerszenarien, Checkpoints, Abdeckung und den vollständigen YAML-Workflow über alle 15 Module mit einem ersetzten Modelltransport. Der vollständige Test umfasst externe Segment-IDs, vierstufige Codes, Personenmetadaten, Gegenbelege, einen absichtlichen Abbruch und die Wiederaufnahme. Die Cloud-Verbindungsprüfung verwendet ausschließlich synthetische Daten; sie ist kein Qualitätsbenchmark und kein Nachweis der Güte einer produktiven Studie.

## Information-Loss-Audit: Grenzfälle im Entwicklungsstand

Die Diagnose verwendet geprüfte Eingabe-, Konfigurations- und Output-Hashes. Ein
fehlgeschlagenes Quellenmodul erzeugt einen vorläufigen Audit, keine erfolgreiche
Nullauswertung. Ein separater Export überschreibt weder bestehende Ergebnisse
noch Eingaben. Nur der bestehende Runner darf sein eigenes unfertiges
Diagnosemodul mit passender Run-ID und Modulstatus erneut schreiben.

Die Regression prüft einen analytischen Text mit über einer Million Zeichen,
Unicode und Zeilenumbrüchen, 60 mögliche Nachfolgeeinträge, mehrfach codierte
Passagen, reine Personenreferenzen, fehlende Gruppenbelege, veränderte Outputdateien
und die Wiederholung nach einem Teilfehler. Wortlisten durchsuchen die gesamten
projizierten Texte; nur die klar gekennzeichnete Vorschau wird begrenzt. Gemeinsame
Referenzen erlauben keine automatische Aussagezuordnung. Negationen und Synonyme
sind ausdrücklich dokumentierte Grenzen der sprachlichen Hinweise. Technische
Tests weisen keine inhaltliche Validität des Audits nach.

## Codebook-Diagnostik: geschützte Dateien und ungewöhnliche Eingaben

Der gemeinsame Diagnoselader prüft deklarierte Ergebnisdateien und bindet bei der
Codebook-Diagnose auch das Kategoriensystem über seinen gespeicherten SHA-256-Wert
an den Lauf. Veränderte Grundlagen werden abgelehnt. Fehlende, beschädigte,
übermäßig verschachtelte oder unvollständige JSON-Quellen werden als ungültig
ausgewiesen. Ein passender Dateihash ersetzt keine Prüfung der Datenstruktur.

Tests lesen synthetische CSV-Dateien mit über einer Million Zeichen pro Segment
und Definition, UTF-8-BOM, Semikolons, Zeilenumbrüchen, Tabs, Emoji und HTML-Text.
Der Inhalt bleibt vollständig; die bestehende Leerraumnormalisierung des
Codebuchimports und ausdrücklich gekürzte Berichtsvorschauen bleiben unterscheidbar.
Die Originaldateien sind anschließend bytegleich. Weitere Tests prüfen alternative
Ausgabedateinamen, Pfade außerhalb des Laufordners, fremde Segment-IDs, veränderte
Prüfsummen, fehlende Herkunftsnachweise und Wiederaufnahme ohne Überschreiben des
Codebuchs. Ein vollständiger Testworkflow prüft die CLI zusätzlich an tatsächlich
erzeugten Single- und Multi-Label-Ergebnissen nach Fehler und Wiederaufnahme.

Die Codebook-Diagnostik ist optional in der bestehenden Pipeline integriert.
Ein Test unterbricht die Code-Verifikation, prüft den vorläufigen Diagnosezustand
und setzt den Lauf fort, ohne erfolgreiche Modellanfragen zu wiederholen. Ein
weiterer Test startet die drei modellfreien Diagnosen gemeinsam über die App,
ohne einen Provider oder die GPU-Prüfung aufzurufen. Alle Diagnoseabschnitte
erscheinen im HTML-Bericht.

Der gemeinsame HTML-Textbetrachter zeigt maskierte Codepfade (`&gt;`, `&amp;`)
und Markdown-Sonderzeichen wieder lesbar an. Die Entschlüsselung der Schreibweise
erfolgt ausschließlich in Textknoten; daraus entstehen weder HTML-Elemente noch
ausführbare Links. Inline-Code und Codeblöcke behalten ihre wörtliche Schreibweise.
Tests prüfen auch HTML-ähnliche Texte, numerische Zeichenreferenzen und maskierte
Tabellentrennzeichen.

## Wiederholungen: vorbereiteter Plan und Cache-Trennung

Kontrollierte Diagnosekinder führen zusätzlich ein geprüftes Inventar technischer
Anfragenachweise. Thinking wird dort bei Inkompatibilität nicht still entfernt.
Lokale Modell-Digests werden vor und nach Anfragen verglichen und über Versuche
hinweg gebunden. Die Annahme einer Anfrage ist ausdrücklich kein Beweis für die
serverinterne Umsetzung aller Parameter. Cloud-Gewichte und fehlende Metadaten
werden nicht als geprüft dargestellt. Nachweise enthalten keine Prompt-/Antwort-
oder Schlüsselwerte; Konsolenlogs bleiben davon getrennt. Der ausführliche Vertrag
und die Grenzen stehen unter „Nachweise der Modellanfragen“ in `DIAGNOSTICS.md`.

Die bestehende Desktop-Überwachung toleriert außerdem kurzzeitige Windows-
Lesesperren auf Statusdateien. Ein JSON-Lesezugriff wird bei einer solchen Sperre
begrenzt wiederholt; während eines aktiven Prozesses wird ein nicht lesbarer
Status beim nächsten Überwachungstakt erneut geprüft. Die Sperre gegen einen
zweiten Analysestart bleibt dabei bestehen. Beschädigte JSON-Dateien werden
nicht allgemein als erfolgreiche oder leere Ergebnisse umgedeutet.

Der Entwicklungsstand kann Wiederholungen mit identischen konfigurierten
Bedingungen planen und über die interne API `execute_repetitions` seriell an den
vorhandenen Runner übergeben. Stabilität und Sensitivität verwenden diese Ausführung auch als optionale UI-/CLI-Diagnosen. Die
Planung verwendet dieselbe Modulsortierung und denselben Schutz vor gespeicherten
Schlüsselwerten wie die bestehende Anwendung. Sie lehnt rekursive Diagnosen,
gemeinsame Checkpointordner und Ausgabeziele außerhalb eines Unterlaufs ab.

Die Tests starten zwei getrennte tatsächliche Runner-Läufe mit künstlichem
Modelltransport. Beide rechnen neu; ein Resume des zweiten Laufs wiederholt
keine erfolgreichen Anfragen. Weitere Prüfungen betreffen deaktivierte Ziele,
explizite Vorstufen, falsche YAML-Typen, fehlende Eingabedateien, DOS-/UNC-Pfade,
reservierte Windows-Dateinamen, alternative relative Ausgaben und unveränderte
Datenschutzvorgaben. Die Ergebnisse belegen die technische Vorbereitung und
Cache-Isolation, noch keine wissenschaftliche Stabilität eines Modells.

Die Seriensteuerung verwendet getrennte Laufordner, die vorhandene strenge
Runner-Identität und dessen Outputprüfung. Tests prüfen Fehler/Fortsetzen,
Pause vor dem Start und innerhalb des Kind-Runners, veränderte Outputs/Berichte,
beschädigte Manifeste, Code-/Konfigurationsänderungen, mehrdeutige Ordner,
eine echte Prozesssperre und das Entfernen äußerer Checkpoint-/Fortschrittsvariablen.
Ein kompletter Versuch wird beim Resume ohne Prozess-/Modellstart übernommen.
Ein Kind mit ungeklärtem `running`-Status wird nicht erneut gestartet. Die gemeinsam
genutzte Pipe-Lease-Aufsicht beendet Serienkinder bei Elternabbruch. Unter Windows
schließt ein Kernel-Jobobjekt Nachkommen ein, auch wenn der direkte Elternprozess
schon beendet ist; auf POSIX wird die eigene Prozessgruppe geprüft. Erst eine zum
Startauftrag passende Aufräumquittung erlaubt die Wiederaufnahme. Tests töten einen
eigenen Controller, prüfen verwaiste Nachkommen, lassen einen unabhängigen Prozess
unberührt und setzen eine unterbrochene echte Testserie unter gleicher Lauf-ID fort.
Eine getötete Aufsicht ohne Quittung erlaubt keine automatische Übernahme.

Der Runner startet seine Modellinstanz erst vor einem tatsächlich anstehenden
Modellmodul. Vor `starts_child_runs: true` wird sie freigegeben, bei späterem Bedarf
neu gestartet. Ein vollständig abgeschlossener Resume startet sie nicht. Ein
Integrationstest führt tatsächliche verschachtelte Serien mit künstlichen
Modellservern aus und prüft die Übergabe. Native Windows-Abbruchtests bestehen;
native macOS-Prüfung bleibt Bestandteil der dortigen CI-/Distributionsprüfung.
Siehe den vollständigen API-Vertrag und die Grenzen in `DIAGNOSTICS.md`.

## Integrierte Stabilität: Pause und Fortsetzen

Vor dem Modulstart wird eine vorhandene verwaltete Ollama-Instanz des Elternlaufs freigegeben. Unterläufe verwenden die bestehende S05-Prozessaufsicht und eigene Verzeichnisse. `WORKFLOW_PAUSE_FILE` wird an die kontrollierte Serie weitergereicht; die Kindrunner erhalten ihren Pausepfad explizit, sonstige `WORKFLOW_*`-Werte werden nicht geerbt. Exit 75 bedeutet ausschließlich bei `starts_child_runs` eine sichere Modul-Pause. Das Elternmanifest erhält `paused`; das Modul und seine Teilberichte werden nicht als abgeschlossene, gehashte Ausgaben verbucht. Andere Module mit Exit 75 bleiben Fehler. Nach Resume werden fertige Samples geprüft und nicht erneut gestartet. Abbruchfehler bleiben mit Teilbericht und Fehlerhilfe sichtbar. Vollständiger App-Abbruch beim Schließen wird separat für die Standalone-Distribution geprüft.

## Sensitivität: getrennte Konfigurationen und sichere Wiederaufnahme

Basis und jede Variante sind an dieselben Originaldaten und eigene Konfigurationshashes gebunden. Vor dem Modellstart prüft der gemeinsame Planer Parameterunterstützung, Vorlagenplatzhalter, No-ops und bekannte Kontextgrenzen. Fehlgeschlagene oder pausierte Serien erzeugen einen ausdrücklich unvollständigen Teilbericht. Resume verwendet fertige Unterläufe nur nach Prüfung von Prozessabschluss, Manifesten, Daten-, Code- und Konfigurationsidentität. Eigene Seriendateien können nicht als alternative Berichtsausgabe überschrieben werden. Geänderte Gewichte unter demselben Modellnamen sperren die Serie; ein ausdrücklich anderes Modell darf andere Gewichte haben. Keine stillen Parameter-Fallbacks in kontrollierten Unterläufen.

## Änderungen während der Eingabeprüfung

Die Oberfläche verwirft verspätete Prüfergebnisse nach einer Änderung an Auswahl oder Einstellungen. Das gilt auch für Preset-Schaltflächen. Ein bereits angeklickter Start wird nach einer solchen Änderung nicht automatisch fortgesetzt; die aktuelle Auswahl muss erneut geprüft werden. Eine zuvor serverseitig gespeicherte Revision kann erhalten bleiben, wird aber durch diese Aktion nicht gestartet.


## Kontrollierte Serien: Status ist kein Abschlussnachweis

Der bestehende Supervisor bleibt für Prozessende und Bereinigung verantwortlich.
Während seiner Wartezeit liest ein optionaler Fortschrittscallback nur den zur
geplanten Wiederholung gehörenden Unterlauf. Die Statusdateien sind größenbegrenzt;
Laufbindung, Modulübergang und die Herkunft der Fortschrittsmeldung werden geprüft.
Im Sekunden-Polling werden keine vollständigen Ergebnisdateien erneut gehasht.
Fehlende, beschädigte oder fremde Statusdaten bleiben unbeziffert und belegen
allein keinen Analyseabbruch. Der Zeitstempel stammt aus dem Kindlauf und wird
nicht durch bloßes Polling erneuert. Die vollständigen bisherigen Manifest-,
Artefakt-, Quellen- und Prozessabschlussprüfungen bleiben für Abschluss/Resume bestehen.

Scheitert eine kontrollierte Wiederholung, zeigen Laufkarte und Teilbericht die gesicherte Fehlerkategorie und passende Schritte, beispielsweise bei zu kleinem Kontextfenster, Speichermangel oder einem Anbieterkontingent. Der Teilbericht nennt die betroffene Wiederholung und das Modul. Alte oder unvollständige Fehlerdaten werden ausdrücklich als unbekannt gekennzeichnet. Rohprotokolle, Eingabetexte und Zugangsdaten werden nicht in diese Hinweise übernommen. Fortsetzen erhält die ursprünglichen Einstellungen; geänderte Einstellungen benötigen einen neuen Lauf.

Bei Codebook-Verweisen werden nur deklarierte, abgeschlossene und verifizierte
Wiederholungsberichte des aktuellen Laufs ausgewertet. Stimmen Material,
Kategoriensystem, Einheiten oder Vergleichsschema nicht überein, wird die Quelle
als ungültig ausgewiesen. Aus ihr wird kein Code-Vorkommen von null abgeleitet.
Deaktivierte Quellen bleiben optional; es werden keine teuren Wiederholungen
durch Auswahl der Codebook-Diagnostik automatisch gestartet.
