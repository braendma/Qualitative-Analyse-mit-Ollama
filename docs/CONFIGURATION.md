# Konfigurationsreferenz der wissenschaftlichen Diagnosen

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
