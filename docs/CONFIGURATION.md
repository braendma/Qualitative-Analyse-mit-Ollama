# Konfigurationsreferenz der wissenschaftlichen Diagnosen

## Ergebnisordner und technische Appdaten (P01b)

Ohne `--output-dir` erstellt die CLI neben der tatsächlich verwendeten Eingabedatei einen neuen Ordner `QualitativeAnalyse_<Lauf-ID>`. Maßgeblich ist `--csv`, falls angegeben, sonst `paths.input_csv` aus der Konfiguration; relative Konfigurations-Eingaben werden gegen deren Ordner aufgelöst. Ein explizites `--output-dir` bleibt relativ zum aktuellen Arbeitsordner, wird bei Bedarf angelegt und enthält wie bisher Unterordner `<Lauf-ID>`. Vor dem neuen Lauf wird die Beschreibbarkeit geprüft. Bei einem ungültigen oder nicht beschreibbaren Ziel erfolgt eine Fehlermeldung, kein Ausweichen in AppData oder einen temporären Ordner. `--validate-only` prüft die Analysedaten, noch nicht die spätere Schreibbarkeit des Ergebnisziels. Resume verwendet unverändert den ausdrücklich angegebenen bestehenden Laufordner und prüft dessen Herkunft.

```console
python run_workflow.py --config config/config_v2.yaml --csv daten/export.csv
python run_workflow.py --config config/config_v2.yaml --csv daten/export.csv --output-dir ergebnisse
python run_workflow.py --config config/config_v2.yaml --csv daten/export.csv --resume daten/QualitativeAnalyse_LAUF-ID
```

Im ersten Beispiel liegt der neue Ordner unter `daten/QualitativeAnalyse_<Lauf-ID>`;
im zweiten unter `ergebnisse/<Lauf-ID>`. Das dritte Beispiel setzt den ersten Lauf
mit exakt derselben Eingabe und Konfiguration fort; `LAUF-ID` ersetzen. Ein alter
Lauf unter `workflow_output/` kann weiterhin mit seinem tatsächlichen Pfad
fortgesetzt werden, wenn die bestehenden Herkunftsprüfungen erfüllt sind.
Die öffentliche Demo-Konfiguration schreibt ohne Zielargument entsprechend
neben ihre tatsächliche Eingabe in `demo/`, nicht automatisch in den Projektroot.

Neue technische Appdaten liegen unter Windows in `%LOCALAPPDATA%\QualitativeAnalyse`, unter macOS in `~/Library/Application Support/QualitativeAnalyse`, unter Linux bei absolut gesetztem `XDG_DATA_HOME` in `$XDG_DATA_HOME/QualitativeAnalyse`, sonst in `~/.local/share/QualitativeAnalyse`. Ein eindeutig vorhandener alter `QualitativeOllama`-Ordner wird weiterverwendet; es wird nichts verschoben. Werden mehrere bestehende Ablagen gefunden, mit `--data-dir` ausdrücklich die gewünschte auswählen.

**Entwicklungsstand P01b – Ergebnisziel in der Oberfläche:** Vor einem neuen Analyselauf unter **Projekt & Dateien → Speicherort für Analyseergebnisse** den vollständigen Pfad zu einem vorhandenen Ordner eintragen. Dafür den Ordnerpfad aus der Explorer-Adressleiste oder über „Pfadname kopieren“ im Finder kopieren und **Ordner prüfen** wählen. Der Browser kennt den ursprünglichen Ordner einer hochgeladenen Datei nicht. Ein nativer Ordnerauswahldialog ist noch nicht vorhanden; die neue Ablage ist noch keine Freigabe fertiger Windows-/macOS-Installationspakete.

Jeder neue App-Lauf bekommt im gewählten Ziel einen eigenen Ordner `QualitativeAnalyse_<Datum>_<Job-ID>/`. Analyseberichte und Moduldateien liegen darunter in `runs/<Lauf-ID>/`; Prüfentscheidungen und deren Versionen in `review/`. Geprüfte Folgeeingaben werden zusätzlich unter `review/followups/<Revision-ID>/` mit `segments.csv`, `codebook.csv`, `review_snapshot.json` und einem Inhaltsnachweis abgelegt. Eine Zieländerung gilt nur für neue Läufe. Wiederaufnahme, Berichtsaufruf und Prüfung bestehender Läufe bleiben an deren ursprünglichen Ordner gebunden. Ist er nicht verfügbar oder passt seine gespeicherte Zuordnung nicht mehr, erscheint ein Hinweis; es gibt keinen Ersatzordner in AppData. Alte Läufe behalten ihre bisherige Ablage und bleiben dort lesbar.

Die technische Projektverwaltung, Einstellungen und unveränderlichen Eingabe-/Konfigurationskopien bleiben im App-Datenordner. Für eine vollständige Sicherung nach Abschluss aller Läufe sowohl diesen Datenordner als auch die gewählten Forschungsordner sichern.

## Datenfreigabe und Schlüssel in vorhandenen Konfigurationen

| Feld | Vorgabe / gültiger Inhalt | Verhalten |
|---|---|---|
| `llm.gdpr_relevant` | Ohne Angabe grundsätzlich `true` | Cloud benötigt eine ausdrückliche Freigabe; ein Cloud-Anbieter oder geerbter Umgebungshost ersetzt sie nicht. |
| `llm.provider` | Beispielsweise `ollama_local` | Neue Dateien nennen Anbieter und Datenfreigabe ausdrücklich. |
| `llm.api_key_env` | Name einer Umgebungsvariable, etwa `OLLAMA_API_KEY` | Nur der Name, niemals der Schlüsselwert. Er beginnt mit `A–Z`, `a–z` oder `_`, enthält danach zusätzlich Ziffern und hat höchstens 200 Zeichen. |

Die dokumentierte Ausnahme für alte Ollama-Cloud-Dateien gilt nur bei ausdrücklich
in der YAML gesetztem `https://ollama.com` und effektivem Anbieter Ollama Cloud;
ein abschließender `/` beziehungsweise Port `443` ist zulässig. Andere URL-Bestandteile
begründen keine Freigabe. Ein explizites `gdpr_relevant: true` hat immer Vorrang.
`OLLAMA_HOST` allein aktiviert diese Ausnahme nicht. Einzelheiten:
[KI-Anbieter und Datenfreigabe](KI_ANBIETER.md#kommandozeile).

Schlüssel gehören ins separate Feld der Oberfläche oder für CLI-Aufrufe in die
gewählte Umgebungsvariable. Die gemeinsame Konfigurationsprüfung lehnt
Credential-Felder auch verschachtelt ab, bevor der Runner neue Ausgaben anlegt
oder Provenienz und Konfigurationssnapshot erstellt. Sie gilt ebenso für
`--validate-only` und Wiederholungspläne. Nur `llm.api_key_env` ist als
Schlüsselquellenname ausgenommen; gleichnamige Felder an anderer Stelle sind
keine Ausnahme. `max_tokens` und normale Analyseparameter bleiben zulässig.
Dateien werden nicht still bereinigt oder umgeschrieben. Beliebige Textwerte
werden dabei nicht auf sämtliche denkbaren Geheimnisse untersucht.

Alte YAMLs mit den 15 Basismodulen brauchen keine neuen Diagnoseabschnitte oder
Aufwandfelder. Die Normalisierung ergänzt Anzeigevorgaben im Arbeitsspeicher,
aber keine zusätzlichen aktivierten Module und keine Wiederholungen.
Vorhandene Projekte behalten beim Öffnen ihre Modulauswahl, bestätigte
Personenzuordnung und gespeicherten Berichte. Erst ausdrückliches Speichern
erstellt eine neue Revision mit der aktuellen Vorlage; neue Diagnosen bleiben
ohne Auswahl ausgeschaltet. Frühere Revisionen und Berichte bleiben erhalten.
Lesbarkeit alter Ergebnisse ist keine Freigabe zum Fortsetzen mit verändertem
Code oder anderen Eingaben: Die bisherige Fingerprintprüfung bleibt bestehen.

## Sensitivität: interner Entwicklungsvertrag

**Sensitivität ist jetzt optional in Oberfläche, Runner und Gesamtbericht integriert.**
Das Modul `sensitivity` ist standardmäßig aus. `diagnostics.sensitivity` enthält
`modules` (gelieferte Vorgabe `[blind_coding]`), `repetitions` (Default 2) und
`variants` (Default `[]`, vor Aktivierung ausdrücklich 1–9 Varianten festlegen).
Die Oberfläche speichert diese Werte pro Projekt. Leere Variantenfelder übernehmen
die Basis; mehrere Änderungen bleiben in derselben Variante erhalten. Startprüfung
und Ausführung verwenden denselben Planer. Für die interne Entwicklung ist der Einstieg
`diagnostic_sensitivity.prepare_sensitivity(config_path, module_ids, variants, repetitions=2)`.
Er liest Eingaben, schreibt keine Dateien und fragt kein Modell ab. Der vorhandene
`diagnostic_series.execute_repetitions` führt einen solchen Plan aus; dabei entstehen
zusätzliche Modellanfragen und eigene Laufordner. Das öffentliche Modul
`sensitivity_analysis.py` wird wie Stabilität über den regulären Workflow-Runner
mit aktivierter Pipeline-Konfiguration gestartet. Ausgaben sind `sensitivity.json`
und `sensitivity.md`; letztere wird in den Gesamtbericht eingebunden. Der eigene
Serienordner `_sensitivity_repetitions` ist als alternatives Berichtsziel gesperrt.

| Feld | Typ / Vorgabe | Bedeutung und Grenze |
|---|---|---|
| `config_path` | Pfad | Unveränderte Ursprungskonfiguration; keine Diagnose-Kindkonfiguration |
| `module_ids` | Nicht leere Liste | Bereits aktivierte Basisanalysen; benötigte Vorstufen werden mit wiederholt |
| `variants` | Liste mit 1–9 Einträgen | Zusätzliche Varianten; unveränderte `baseline` kommt automatisch hinzu |
| `variants[].id` | Text, 1–40 Zeichen | Eindeutig, beginnt mit Kleinbuchstaben; danach Kleinbuchstaben/Ziffern/`_`/`-`; `baseline` reserviert |
| `variants[].llm` | Optionale Zuordnung | Nur `model`, `temperature`, `num_ctx`, `max_tokens`, `think` |
| `variants[].prompts` | Optionale Zuordnung | Vorhandener Vorlagenname → `system` und/oder `user`; unveränderte Platzhalter samt Häufigkeit |
| `repetitions` | Ganzzahl, Vorgabe 2; 2–20 | Frische Wiederholungen je Konfiguration einschließlich Basis |

Die Basis muss `llm.model`, `llm.temperature`, `llm.num_ctx` und `llm.max_tokens`
ausdrücklich setzen. Temperatur: endliche Zahl von 0 bis 2; Kontext und Antwortlimit:
positive Ganzzahlen, Antwortlimit kleiner als Kontext. Thinking: `true`, `false`,
`low`, `medium`, `high`, `max`; tatsächliche Unterstützung ist modellabhängig.
Nicht angegebene Felder bleiben unverändert. Jeder Eintrag wird von derselben Basis
abgeleitet, nicht vom vorherigen Eintrag. Ein Eintrag muss etwas ändern; wirkungslose
Schlüssel, reine Leerraumänderungen und doppelte Konfigurationen werden abgelehnt.

Beispiel für `variants` (alle Texte und Modellnamen in Tests müssen künstlich sein):

```yaml
- id: temperatur-020
  llm:
    temperature: 0.20
- id: andere-anweisung
  prompts:
    blind_coding:
      system: "Blindcodierung: Prüfe ausdrücklich auch mögliche Gegenargumente."
```

Das Promptbeispiel setzt eine Basisvorlage ohne Platzhalter im Systemtext voraus.
Bei Platzhaltern in der eigenen Vorlage diese vollständig übernehmen. Nur Vorlagen
der tatsächlich gewählten Module/Vorstufen sind zulässig. `self_repair` wird nicht
als eigene Behandlung angeboten. Im Mehrfachmodus verwendet Blind-Coding eine
programmseitige Passage-Anweisung; die dort nicht verwendete YAML-Blindvorlage
kann deshalb kein Sensitivitätsziel sein. Platzhalterprüfung ersetzt keine fachliche
Prüfung, ob eine neue Formulierung dieselben Daten angemessen berücksichtigen lässt.

Die Adapter übertragen unterschiedliche Parameter: Temperatur/Thinking werden nur
für Ollama zugelassen, Kontextvariation nur für lokales Ollama. Die Cloud-Kontextzahl
ist eine lokale Eingabegrenze und wird deshalb nicht als Modellparameter variiert.
`top_p`, `top_k` und `seed` sind derzeit nicht durch die Analyse-Aufrufe verdrahtet;
der Planer lehnt diese Schlüssel ab. Das beschreibt die aktuelle Programmanbindung,
keine grundsätzliche Begrenzung der Anbieter-APIs. Anbieter, Freigabe, Schlüssel,
Hosts, Quelldateien, Personen-/Spaltenzuordnung und Modulauswahl bleiben fest.

Vor jeder Ausführung werden Plan und Originaldateien erneut geprüft. Pro Variante
liegt eine separate `configuration-<id>.yaml` im Serienordner; der gemeinsame
`repetition_plan.json` verwendet dafür Schema 2. Jeder Sampleordner erhält einen
frischen regulären Runner-Lauf samt Checkpoints, Prozessaufsicht und Anfragequittungen.
Fehler/Pause stoppen die weitere Serie; eine zulässige Wiederaufnahme überspringt
fertige Samples und setzt denselben unvollständigen Kindlauf fort. Geänderte Dateien,
Laufgrundlagen oder nicht bestätigte Prozessenden sperren die Wiederaufnahme.
Modellwechsel dürfen andere Modelldigests haben; unter demselben Modellnamen
bleiben geänderte Gewichte auch zwischen Varianten unzulässig. Bestehende
Stabilitätsserien behalten ihren bisherigen Schema-1-Vertrag.

**Aufwand:** `(1 + Anzahl Varianten) × Wiederholungen × Anzahl Module einschließlich
Vorstufen`. Zwei Varianten plus Basis, je zwei Wiederholungen von Blind-Coding mit
Clustering, ergeben zwölf zusätzliche Modulausführungen. Das ist keine exakte Zahl
von Modellanfragen. Antwortreparaturen und Verdichtungen erhöhen sie gegebenenfalls.
Die Kontextvorprüfung prüft das bekannte Material jeder Konfiguration; unbekannte
spätere Modellbefunde und GPU-Kapazität sind dadurch nicht freigegeben.

Mehrere geänderte Parameter werden als gemeinsame Veränderung (`joint_changes`)
markiert: Unterschiede können keinem einzelnen Parameter zugeschrieben werden.
Die Planung beweist weder tatsächliche Parameterübertragung noch deren Durchsetzung
im Modell. Der Vergleich berücksichtigt Anfragequittungen und Wiederholungsstreuung
getrennt. Sensitivität wird nicht automatisch als methodischer Fehler bewertet.

Diese Referenz wird mit jedem neuen Diagnosemodul erweitert. Bisherige Optionen:
[EXTENSIONS](EXTENSIONS.md), [ROBUSTNESS](ROBUSTNESS.md) und die kommentierte
`config/config_v2.yaml`. Die neuen Felder sind optional; alte YAML-Dateien benötigen
keine automatische Migration und werden nicht umgeschrieben.

## Moduldefinition (`pipeline.modules[]`)

| Schlüssel | Typ / Default | Erlaubte Werte | Bedeutung / Laufzeitwirkung / methodische Wirkung |
|---|---|---|---|
| `enabled` | bool / `true` (bereits vorhanden) | `true`, `false` | UI und Runner respektieren den Default. Coverage und Information-Loss sind in der gelieferten Konfiguration ausdrücklich `false`. Eine gespeicherte manuelle Auswahl hat Vorrang. |
| `after_if_enabled` | Liste von Strings / `[]` | Modul-IDs | Reihenfolge nach den genannten, ebenfalls aktivierten Modulen. Fehlende/deaktivierte Module werden nicht hinzugeschaltet; erfolglose Quellen bleiben diagnostizierbar. Keine Voraussetzung einer erfolgreichen Quelle; Zyklen werden abgelehnt. |
| `requires_model` | bool / `true` | `true`, `false` | `false` nur für tatsächlich modellfreie Programme. Sind alle ausgewählten Module modellfrei, entfallen Provider-/Modellprüfung und eigener Ollama-Start. Kein methodischer Qualitätsanspruch. |
| `starts_child_runs` | bool / `false` | `true`, `false` | Interner Vertrag für Module, die kontrollierte Modell-Unterläufe starten. Erfordert `requires_model: true`, damit Providerfreigabe und Aufwand sichtbar bleiben. Der Runner gibt seine Modellinstanz davor frei und startet sie erst bei späterem Bedarf neu. Unterläufe dürfen nicht erneut solche Module ausführen. Reguläre Analysen lassen den Wert auf `false`. |
| `cost_profile.class` | String / nicht gesetzt | `NIEDRIG`, `MITTEL`, `HOCH`, `SEHR HOCH` | Qualitativer Aufwandshinweis in der Modulauswahl, keine Laufzeitzusage. |
| `cost_profile.recommendation` | String / nicht gesetzt | verständliche Einsatzempfehlung | Beschreibt die geeignete Analysephase, verändert keine Einstellungen. |
| `cost_profile.note` | String / nicht gesetzt | erläuternder Text | Grenzen und zusätzlicher Aufwand anderer gewählter Module; keine automatische Aktivierung. |

`depends_on` bleibt die vorhandene harte Abhängigkeit. Eine ausgewählte Stufe mit
solchen Abhängigkeiten schaltet sie in der Oberfläche weiterhin hinzu; im Runner
müssen sie aktiviert sein und erfolgreich abgeschlossen werden. `after_if_enabled`
ist nur eine zusätzliche Reihenfolgevorgabe. Die Diagnose liest ausschließlich
abgeschlossene Quellen mit passenden Datei- und Eingabe-Prüfsummen.

Beispiel (gekürzt; vollständige Definition in der Standard-YAML):

```yaml
- id: coverage
  name: Coverage und Blind Spots
  script: coverage_analysis.py
  enabled: false
  requires_model: false
  depends_on: []
  after_if_enabled: [clusterer, summarizer, swot, overall_synthesis]
  cost_profile:
    class: NIEDRIG
    recommendation: für iterative Arbeit geeignet
    note: Keine zusätzlichen Modellaufrufe; ausgewählte Vorstufen haben eigenen Aufwand.
  args: [--config, "{config}", --input-csv, "{input_csv}"]
  outputs: [coverage.json, coverage.md]
  report:
    title: Coverage und Blind Spots
    markdown: coverage.md
```

Coverage hat keine Modell-/Samplingoptionen. Methodenparameter sind die vorhandene
Personenzuordnung und die expliziten Passage-IDs; sie bestimmen die Nenner. Die
Diagnose verändert weder Zuordnungen noch Kategorien. Fehlende Passage-IDs werden
nicht anhand ähnlicher Texte ergänzt. CLI-Pfade und Ergebnisfelder:
[DIAGNOSTICS](DIAGNOSTICS.md).

## Information-Loss-Audit

`information_loss` nutzt dieselben Modulfelder, ohne zusätzliche Modellparameter.
Die vollständige ausgelieferte Definition wartet über `after_if_enabled` auf alle
elf ebenfalls ausgewählten analytischen Quellen. Beispiel mit zwei Quellen:

```yaml
- id: information_loss
  name: Information-Loss-Audit
  script: information_loss_analysis.py
  enabled: false
  requires_model: false
  depends_on: []
  after_if_enabled: [swot, meta_swot]
  cost_profile:
    class: MITTEL
    recommendation: für iterative Arbeit geeignet
    note: Keine zusätzlichen Modellaufrufe; Prüfpunkte am Original beurteilen.
  args: [--config, "{config}", --input-csv, "{input_csv}"]
  outputs: [information_loss.json, information_loss.md]
  report:
    title: Information-Loss-Audit
    markdown: information_loss.md
```

Wortlisten und Vorschaugrenzen sind derzeit feste, versionierte Programmregeln,
keine YAML-Optionen. Sie sind vollständig in [DIAGNOSTICS.md](DIAGNOSTICS.md)
dokumentiert. Die methodisch relevanten Referenzkanten stammen aus den
`depends_on`- und Dateiargumenten der ausgewählten Quellmodule; bloßes Warten über
`after_if_enabled` erfindet keinen inhaltlichen Analyseübergang. Fehlgeschlagene
Quellen führen zu vorläufigen Ergebnissen und gezielter Fehlerhilfe. Wird das
Quellenproblem behoben, berechnet der bestehende Resume die Diagnose erneut.

## Codebook-Diagnostik

`codebook_diagnostics` hat keine eigenen Modellparameter und ist standardmäßig
ausgeschaltet. Die vorhandenen Einstellungen zur Personenzuordnung sowie
`coding_agreement.label_mode` bestimmen die Analyseeinheiten. Im Mehrfachmodus ist
`columns.unit_id` erforderlich. Konfiguration und Originalcodebuch sind Teil des
Herkunftsnachweises; nur unveränderte Grundlagen dürfen erneut ausgewertet werden.

```yaml
- id: codebook_diagnostics
  name: Codebook-Diagnostik
  script: codebook_diagnostics.py
  enabled: false
  requires_model: false
  depends_on: []
  after_if_enabled: [code_verification, blind_coding, coding_agreement, review_queue]
  cost_profile:
    class: NIEDRIG
    recommendation: für iterative Arbeit geeignet
    note: Keine zusätzlichen Modellaufrufe; ausgewählte Vorstufen haben eigenen Aufwand.
  args: [--config, "{config}", --input-csv, "{input_csv}"]
  outputs: [codebook_diagnostics.json, codebook_diagnostics.md]
  report:
    title: Codebook-Diagnostik
    markdown: codebook_diagnostics.md
```

`after_if_enabled` schaltet keine Codieranalyse ein. Ohne solche Quellen stehen
nur Material-/Codebuchhinweise zur Verfügung. Eine fehlende gewählte Quelle führt
zur vorläufigen Diagnose und wird bei Resume erneut geprüft. Die Schwellen für
geringe Häufigkeit, Co-Codierung sowie die Darstellungs-/Rechengrenzen sind feste,
versionierte Regeln in [DIAGNOSTICS.md](DIAGNOSTICS.md), keine versteckten
Modellparameter. Die Diagnose ändert keine Codes oder menschlichen Entscheidungen.

## Stabilitätsanalyse konfigurieren


```yaml
diagnostics:
  stability:
    repetitions: 3  # ganze Zahl 2–20; zusätzliche Läufe
    modules: [blind_coding]  # explizite, bereits aktivierte Ziele
```

Das mitgelieferte Pipeline-Modul heißt `stability`, verwendet `stability_analysis.py` und ist `enabled: false`. Für die Aktivierung bleiben `requires_model: true` und `starts_child_runs: true` zwingend. Die Argumente sind `--config "{config}" --input-csv "{input_csv}"`; Ausgaben: `stability.json`, `stability.md`. `after_if_enabled` ordnet es nach den aktivierten Basisanalysen ein, ohne die Zielauswahl still zu erweitern. Nötige analytische Vorstufen werden innerhalb jeder Wiederholung neu gerechnet; Diagnosen selbst sind keine Ziele.

Eine aktivierte Stabilitätskonfiguration wird bereits bei `00_WORKFLOW_RUNNER.py --config PFAD --validate-only` geprüft. `stability_plan` enthält Wiederholungszahl, Ziele, effektive Module, zusätzliche Vorstufen und zusätzliche Modulausführungen. `model_calls: null` bedeutet unbekannte tatsächliche Anzahl, nicht null Aufrufe. Abweichendes `--csv` ist gesperrt; zuerst `paths.input_csv` ändern.

Direktes Starten des Moduls ohne passenden aktiven Runner-Lauf ist gesperrt. `_stability_repetitions` ist reserviert; Diagnoseausgaben dürfen keine internen Seriendateien überschreiben. App-Einstellungen speichern dieselbe Struktur als `settings.stability`. Ist das Modul aus, startet es keine Wiederholungen; ältere Projekte ohne diese Einstellungen behalten den ausgeschalteten Default.

## Einheitliche Aufwandprofile

Jedes der 20 Standardmodule enthält unter `pipeline.modules` ein `cost_profile`.
Die Klassen `NIEDRIG`, `MITTEL`, `HOCH`, `SEHR HOCH` bezeichnen den relativen
Eigenaufwand; benötigte Vorstufen kommen hinzu. Keine Zeit- oder Preisschätzung.
Die Oberfläche zeigt Klasse, Einsatzempfehlung und konkrete Einflussfaktoren direkt
bei der Auswahl. Eine Übersicht enthält das [Handbuch](HANDBUCH.md#aufwandprofile).

```yaml
cost_profile:
  class: HOCH
  recommendation: für Zwischenvalidierung geeignet
  note: Viele Textstellen und lange Eingaben erhöhen den Aufwand.
```

`class` muss eine der vier Klassen sein, `recommendation` ein nichtleerer Text,
`note` ist optional und muss bei Angabe Text sein. Fehler nennen Modul und Felder.
Fehlende oder mit `null` belegte Profile erben den Standard aus `cost_profiles.py`,
sofern Modul-ID und Script genau dem Originalmodul entsprechen. Eigene Scripts
bekommen keine unterstellte Einstufung; dafür ein explizites Profil angeben.
Die Standardkonfiguration und die kompatiblen Defaults werden auf Gleichheit geprüft.
Normalisierung ändert keine Originaldateien und schaltet keine zusätzlichen Module ein.


## Vorstartübersicht und finales Validierungspreset

Die optionale Schaltfläche **Finale Validierungsanalyse** wählt die fünf Diagnosen
und benötigte Basisanalysen aus, ohne etwas zu starten oder bestehende Varianten
zu ersetzen. Material, Segmentierung und Kategoriensystem sollten weitgehend
stabil sein. Sensitivitätsvarianten müssen ausdrücklich festgelegt werden.
Die Oberfläche zeigt Hauptlauf, zusätzliche Serien und Ausführungen je Modul;
`--validate-only` liefert dieselbe serverseitige Zusammenfassung als `effort`.
[Bedienung und Beispiel mit 21 Modulausführungen im Handbuch](HANDBUCH.md#finale-validierungsanalyse-und-aufwandübersicht).

Es wird kein neuer YAML-Schalter benötigt: `pipeline.modules[].enabled` und
`diagnostics.stability` / `diagnostics.sensitivity` bleiben maßgeblich. Die
Konfiguration aktiviert das Preset nicht automatisch; es gilt nur die ausdrücklich
gewählte Modulliste. `effort` ist Ausgabe der Prüfung, keine Konfigurationsoption.
Es enthält `main_module_executions`, `additional_module_executions`,
`total_module_executions`, `known_module_executions`, `series` und `modules` mit
Einzelausführungen pro Hauptlauf/Stabilität/Sensitivität. `basis: fresh_run`
kennzeichnet den vollständigen neuen Lauf; keine Restzeit beim Resume.
`model_calls_estimate` ist bei einem rein modellfreien Lauf 0, sonst `null`.
`unplanned_child_modules` nennt eigene Module mit nicht berechneten Unterläufen;
in diesem Fall ist `total_module_executions: null`. Keine Zeit-/Preisprognose.


## Analyseperspektiven je Modul

Der aktuelle Entwicklungsstand erlaubt zusätzliche Perspektiven für die
zehn unveränderten Standardmodule `clusterer`, `summarizer`, `swot`,
`meta_swot`, `person_analysis`, `person_comparison`, `contrast_analysis`, `relation_analysis`, `ambiguity_analysis` und `overall_synthesis`. Die Modi werden unabhängig
je Modul gewählt; die folgende Auswahl ist ein Beispiel, keine automatische
Aktivierung aller zehn Module:

```yaml
analysis_perspectives:
  clusterer: qualitative
  summarizer: both
  swot: frequency
  meta_swot: both
  person_analysis: frequency
  person_comparison: both
  contrast_analysis: both
  relation_analysis: both
  ambiguity_analysis: both
  overall_synthesis: both
```

Dieser optionale Abschnitt ergänzt eine vorhandene Konfiguration; er aktiviert
selbst keine Module. `pipeline.modules[].enabled` und die benötigten Vorstufen
bestimmen weiter den Ausführungsumfang. Die Auswahl gilt auch für automatisch
benötigte Vorstufen. Oberfläche: `settings.analysis_perspectives` verwendet
dieselbe Zuordnung. Abgewählte Module behalten gespeicherte Modi.

| Wert | Wirkung |
|---|---|
| `qualitative` | Bestehende Analyse ohne zusätzliche thematische Phase; Vorgabe bei fehlendem Eintrag. |
| `frequency` | Gemeinsame Ausgangsanalyse, deterministische Zählung und benannte Häufigkeitsinterpretation. |
| `both` | Dieselbe einmalige Zählbasis und Häufigkeitsinterpretation, zusätzlich die ursprüngliche qualitative Interpretation als benannte Vergleichsperspektive. |

Ein fehlender oder `null` gesetzter gesamter Abschnitt bedeutet qualitativ.
Null-Einzelwerte, Listen, unbekannte Modi und unbekannte Modul-IDs werden
abgewiesen. Die zehn genannten unveränderten Standardmodule sind integriert. Codiervergleich, Review und Diagnosen erhalten
keine künstlichen Interpretationsmodi. Eigene Skripte können keine Freigabe durch
Wiederverwendung einer Standard-ID erlangen. Alle gespeicherten Einträge werden
geprüft, auch bei gerade abgewählten Modulen; ungültige Werte bewusst korrigieren.

Bei `overall_synthesis: frequency` oder `both` kommt vor der neuen vollständigen
Originalmatrix eine modellseitige Auswahl vollständiger materialbezogener
Synthesebefunde hinzu. `both` teilt Auswahl und Matrix; andere Quellenmodule
werden dadurch nicht automatisch auf Häufigkeiten umgestellt. Die Auswahl ist
menschlich unbestätigt und mit Begründung sichtbar. Mengen-, Gruppen-, Methoden-
und allgemeine Beziehungsbehauptungen sowie unklare Aussagen bleiben Kontext;
es werden keine Teilbehauptungen herausgelöst. Quellen und deren vollständiger
Verdichtungsweg müssen zum Originalmaterial und zu deklarierten Dateien des
gleichen Laufs passen. Alte Synthesen ohne `source_projection_fingerprints`
benötigen dafür einen neuen Lauf mit den Vorstufen. Die zusätzliche Auswahlphase
steht als `additional_countability_selection_phases` in der Aufwandvorschau;
Kandidatenzahl, Anfragen und mögliche API-Kosten sind vorab unbekannt. Das
Aufrufbudget der hierarchischen Verdichtung begrenzt diese Zusatzphasen nicht.
Vollständige Kandidaten und Vergleichsregister werden zur Laufzeit auf Kontext
geprüft und nicht still gekürzt. Details: [Handbuch](HANDBUCH.md#analyseperspektiven-je-modul).

Für `frequency`/`both` muss `person_identity` einen zur unveränderten CSV passenden
Bestätigungsnachweis enthalten. Die Oberfläche erstellt ihn nach Prüfung und
Bestätigung der Dokument-/Personenzuordnung. Für einen CLI-Lauf die entsprechend
vorbereitete Konfiguration zusammen mit ihrer normalisierten Arbeits-CSV und
den zugehörigen Eingabepfaden verwenden; ein frei gesetztes `confirmed: true`
reicht nicht. Die [Personenzuordnung](Personenzuordnung.md) zuerst prüfen.
Die reguläre Eingabeprüfung ist beispielsweise:

```console
python run_workflow.py --config pfad/zur/vorbereiteten_config.yaml --validate-only
```

Diese Prüfung führt keine Modellanfrage aus. Themen und Vergleichsregister
entstehen erst aus den Analysen, deshalb ist eine bestandene Vorprüfung keine
Garantie, dass alle späteren Häufigkeitsanfragen in das Kontextfenster passen.
Einzeltexte, Register und Gegenpositionsmaterial werden nicht still gekürzt.
Bei einem Kontextfehler Einstellungen oder Material begründet überarbeiten
und einen neuen Lauf starten. Fortsetzen erfordert unveränderte Konfiguration,
Eingaben und Programmversion; passende Teilblöcke können wiederverwendet werden.

Die Aufwandübersicht nennt gemeinsame Zählbasen und zusätzliche
Interpretationsphasen. Eine Basis ist keine einzelne Modellanfrage. SWOT führt
die vollständige Thema-Einheit-Zuordnung im jeweiligen Codepfad aus, Meta-SWOT
im gesamten ausgewerteten SWOT-Material. Der Personenvergleich prüft gemeinsame
Muster im vollständigen bestätigten Vergleichsmaterial. Personenbefunde und jede einzelne
Ambivalenzseite werden gegen den vollständigen Einzelfall geprüft. Cluster und
Zusammenfassungen verwenden vollständige Clusterzuordnungen.
Matrixumfang, Themen und Reparaturen bestimmen die tatsächliche Zusatzarbeit;
Wiederholungsserien führen sie erneut aus. `both` teilt die Matrix pro Modul.
Der Kern zählt selbst; Modelltexte können die berechneten Werte dennoch falsch
interpretieren. Materialeinheiten, bestätigte Personen, Prüfstatus und Nenner
bleiben deshalb explizit. Siehe [Bedienung und Fehlerhilfe](HANDBUCH.md#analyseperspektiven-je-modul)
und [Entwicklervertrag](THEMATIC_COUNTING.md).


Bei Meta-SWOT werden bestehende SWOT-Häufigkeiten nicht addiert oder als exakte
Themenunion übernommen: Die neuen analytischen Meta-Befunde benötigen eine
neue Matrix. Die Personenanalyse hat je Befund einen Personennenner von eins;
mehrere Dokumente derselben bestätigten Person erhöhen diesen nicht. Bei
Ambivalenz bezeichnet `both` als **Zuordnungsstatus** Stützung und Widerspruch
gegenüber einer Seite, während `both` als **Konfigurationsmodus** die beiden
Analyseperspektiven auswählt. Seiten A/B werden unabhängig geprüft; B wird
nicht automatisch zur Gegenposition von A.

Die Quellenprüfung benötigt bei Meta-SWOT die originale SWOT-Vorstufe, bei
Personenanalyse Cluster, Originaltext-Zuordnung und Clusterzusammenfassungen,
bei Ambivalenz die Personenanalyse und Originaltext-Zuordnung. Im Runner gelten
deklarierte Artefakte, Abschlussstatus und Dateihashes; Eingaben und Vorstufen
müssen auch nach der Ausführung unverändert sein. Semantische Fingerprints der
ungewichteten Befunde ersetzen diese Dateiprüfungen nicht. Vorhandene
`analysis_perspective`-Zusätze beeinflussen die Originalkandidaten nicht.
Für Diagnoseprojektionen werden abhängige Quellen ebenfalls geprüft; fehlende
oder beschädigte Vorstufen liefern keine vermeintlich gültigen Nullwerte.


Der Vergleichsraum der Häufigkeitsinterpretation ist fachlich festgelegt, kein
zusätzliches Feld in der YAML: Personen- und Ambivalenzanalyse übergeben sämtliche
Themen desselben vollständigen Einzelfalls (`comparison_basis: same_person_scope`),
einschließlich aller A-/B-Seiten. Cluster, Zusammenfassungen, SWOT, Meta-SWOT, Personenvergleich, Zusammenhangsanalyse
und Gesamtsynthese verwenden sämtliche gezählten Modulthemen (`all_fixed_topics`). Das Anfrageobjekt benennt
`module_topic_count` und `comparison_topic_count` getrennt. Themen anderer Personen
werden nicht in die Einzelfallinterpretation eingeschleust; alle Fälle und ihre
Zähler bleiben im Gesamtergebnis. Auch das vollständige Einzelfallregister kann
zu groß für den gewählten Kontext sein und wird dann nicht still gekürzt.


Beim Personenvergleich zählt die neue Perspektive ausschließlich
`gemeinsame_muster`. Jedes vollständig definierte Muster wird über sämtliche
Originaleinheiten aller bestätigten Vergleichspersonen geprüft. Es handelt sich
um Unterstützung oder Gegenposition zu einer analytisch abgeleiteten Aussage,
nicht automatisch um ihre wörtliche Nennung. Die ursprüngliche Liste `personen`
ist nur eine Kandidatenreferenz und setzt keine Matrixzellen vorab auf positiv.
`zentrale_unterschiede`, `typen`, `nicht_zugeordnete_personen` und `gesamtvergleich`
bleiben ausdrücklich qualitativer Kontext. Typenlisten dürfen sich überschneiden
oder unvollständig sein; daraus entstehen keine behauptete Partition, Typenquote
oder zusätzliche Nennungshäufigkeit. Diese Auswahl ist fest im Adapter definiert,
kein weiterer YAML-Schalter.

Der Personenvergleich benötigt die vollständige originale Personenanalyse und
einen dazu passenden Verdichtungsnachweis (`input_reduction`). Fremde Personen,
fehlende Originalpersonen oder falsche Quell-/Verdichtungshashes verhindern die
zusätzliche Auswertung. Die Moduswahl ändert nicht die bestätigte Personenbasis.


Die Kontrastanalyse zählt vollständig definierte dominante Muster über das gesamte
bestätigte Originalmaterial und eindeutig an ein lokales Muster gebundene
Gegenfälle über sämtliche Originaleinheiten ihrer jeweiligen Person.
`getragen_von` ist keine vollständige Mitgliedschaftsliste. Mehrdeutige oder
nicht passende Freitextbezüge auf Muster bleiben mit Grund ungezählter Kontext,
ebenso Typenspannungen, Relativierungen und Gesamteinordnung. Ein fehlender
Bezug ist kein Nachweis für null Nennungen. Fremde Personen oder fehlerhafte
Quell-/Verdichtungsnachweise dagegen verhindern die zusätzliche Auswertung.
Benötigt werden die vollständige Personenanalyse und der dazu passende originale
Personenvergleich; beide bleiben ungewichtete Quellen.

Der feste Kontrastvergleich heißt `comparison_basis: contrast_scoped`.
`comparison_scope: global_patterns` enthält alle globalen Muster; eindeutig
zugeordnete Gegenfälle des jeweiligen Musters stehen vollständig als getrennte
qualitative Bezüge daneben. `same_person_countercases` enthält alle gezählten
Gegenfallthemen derselben Person; das gebundene globale Muster steht separat
als vollständiger qualitativer Bezug. `reference_context` mischt keine fremden
Nenner in das Kennzahlenregister. Globale und Einzelfallzahlen werden weder
addiert noch voneinander abgezogen. Auch bei nur einer Studienperson bleiben
diese Rollen verschieden. Register und Bezugstexte werden nicht gekürzt, um
ein Kontextlimit zu umgehen. Dies ist kein zusätzlicher YAML-Schalter.


## Auswahlgrenzen der Zusammenhangsanalyse

Unter `analysis_settings.relation_analysis` sind `max_pairs` (Standard: 80)
und `max_segments_per_path` (Standard: 6) Ganzzahlen. `max_pairs: 0` wählt alle
zulässigen Codepaare; negative Werte sind ungültig. Das Segmentlimit muss
mindestens 1 sein. Boolesche Werte, Dezimalzahlen und als Text gespeicherte
Zahlen werden abgewiesen, auch wenn keine Kandidaten existieren. So bleibt
eine ungültige Einstellung nicht unbemerkt. Diese Grenzen steuern die
Beispielauswahl der bestehenden qualitativen Relationsanalyse; sie stellen
keine vollständige thematische Häufigkeitsprüfung her.


Die zusätzliche Perspektive der Zusammenhangsanalyse benötigt die bestätigte
CSV, Cluster, Zusammenfassungen und vollständige Originaltext-Zuordnung aus
demselben Lauf. `relation_analysis.py --csv` kann die Eingabe ausdrücklich
setzen. Ein neuer Auswahlnachweis bindet Parameter, Reihenfolge und tatsächlich
verwendete Seitenbelege. Alte JSON-Dateien ohne diesen Nachweis werden nicht
mit heutigen Standardparametern als historisch vollständig ausgegeben.
Inhaltliche Relationszuordnungen und deterministische Codeüberschneidungen
erscheinen getrennt. Die inhaltliche Matrix und ihre Interpretation führen zusätzliche Modell-
anfragen aus; Codeüberschneidungen werden ohne Modell berechnet. Die Zahl der
Kandidaten ist keine vollständige Nennungshäufigkeit einer Relation.
