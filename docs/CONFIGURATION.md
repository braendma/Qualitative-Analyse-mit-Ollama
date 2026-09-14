# Konfigurationsreferenz der wissenschaftlichen Diagnosen

Diese Referenz wird mit jedem neuen Diagnosemodul erweitert. Bisherige Optionen:
[EXTENSIONS](EXTENSIONS.md), [ROBUSTNESS](ROBUSTNESS.md) und die kommentierte
`config/config_v2.yaml`. Die neuen Felder sind optional; alte YAML-Dateien benötigen
keine automatische Migration und werden nicht umgeschrieben.

## Moduldefinition (`pipeline.modules[]`)

| Schlüssel | Typ / Default | Erlaubte Werte | Bedeutung / Laufzeitwirkung / methodische Wirkung |
|---|---|---|---|
| `enabled` | bool / `true` (bereits vorhanden) | `true`, `false` | UI und Runner respektieren den Default. Coverage ist in der gelieferten Konfiguration ausdrücklich `false`. Eine gespeicherte manuelle Auswahl hat Vorrang. |
| `after_if_enabled` | Liste von Strings / `[]` | Modul-IDs | Reihenfolge nach den genannten, ebenfalls aktivierten Modulen. Fehlende/deaktivierte Module werden nicht hinzugeschaltet; erfolglose Quellen bleiben diagnostizierbar. Keine Voraussetzung einer erfolgreichen Quelle; Zyklen werden abgelehnt. |
| `requires_model` | bool / `true` | `true`, `false` | `false` nur für tatsächlich modellfreie Programme. Sind alle ausgewählten Module modellfrei, entfallen Provider-/Modellprüfung und eigener Ollama-Start. Kein methodischer Qualitätsanspruch. |
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
