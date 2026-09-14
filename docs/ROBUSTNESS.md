# Fehlerbehandlung und reproduzierbare Läufe

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
python run_workflow.py --config config/config_v2.yaml --resume workflow_output/LAUF-ID
```

Jeder neue Lauf erhält ein eigenes Verzeichnis unter `workflow_output`. Darin stehen der Gesamtbericht, die Konfigurationskopie und das Manifest mit Lauf-ID, SHA-256-Prüfsummen, Modellparametern, Codeversion und Abhängigkeitsversionen. JSON- und Markdown-Ergebnisse werden atomar geschrieben. Ein Modul darf weder unveränderte alte Dateien noch unvollständige Ergebnisse als Erfolg melden.

Eine Wiederaufnahme prüft zuerst Eingaben, Codebuch, Konfiguration, Programmdateien, Abhängigkeiten und bereits abgeschlossene Ergebnisdateien. Änderungen führen zu einer Ablehnung; dafür ist ein neuer Lauf vorgesehen. Logs werden fortlaufend geschrieben und sind von der unveränderlichen Ergebnisprüfung ausgenommen. Die Checkpoints der Coding-Module speichern ausschließlich vollständig validierte Segmentergebnisse. Nach einer Unterbrechung werden diese wiederverwendet; fehlgeschlagene Segmente werden erneut bearbeitet. Ein Upgrade von älteren Programmversionen setzt einen neuen Lauf voraus.

## Fehler und empirische Rückverweise

### Zwischenstände innerhalb eines Moduls

Mit `llm.partial_checkpoints: true` (Standard) speichert der Runner zusätzlich geprüfte Teilanalysen unter `workflow_output/LAUF-ID/_checkpoints`: je Codepfad bei Clustern und SWOT, je Cluster bei Zusammenfassungen, je Person bei Personen- und Ambiguitätsanalysen, je SWOT-Dimension bei Meta-SWOT sowie je Paket bei Relationsanalyse, Evidence-Audit und hierarchischer Synthese. Die Coding-Module behalten ihre eigenen Segment-/Passagen-Checkpoints.

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

Die bestehende Desktop-Überwachung toleriert außerdem kurzzeitige Windows-
Lesesperren auf Statusdateien. Ein JSON-Lesezugriff wird bei einer solchen Sperre
begrenzt wiederholt; während eines aktiven Prozesses wird ein nicht lesbarer
Status beim nächsten Überwachungstakt erneut geprüft. Die Sperre gegen einen
zweiten Analysestart bleibt dabei bestehen. Beschädigte JSON-Dateien werden
nicht allgemein als erfolgreiche oder leere Ergebnisse umgedeutet.

Der Entwicklungsstand kann Wiederholungen mit identischen konfigurierten
Bedingungen planen und über die interne API `execute_repetitions` seriell an den
vorhandenen Runner übergeben. Eine auswählbare UI-Diagnose ist noch nicht enthalten. Die
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
Ein Kind mit ungeklärtem `running`-Status wird nicht erneut gestartet. Normale
Tastaturunterbrechungen räumen den Kindprozess auf; harter Elternprozessabbruch
benötigt noch die geplante Prozessaufsicht. Ebenso ist die Übergabe einer äußeren
verwalteten Ollama-Instanz noch offen; gegenwärtig wird diese Konstellation vor
einem Start verständlich abgewiesen. Siehe den API-Vertrag in `DIAGNOSTICS.md`.
