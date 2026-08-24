# Erweiterung: Coding-Validierung

Der YAML-gesteuerte Workflow enthält drei zusätzliche Module. Der generische
Runner `00_WORKFLOW_RUNNER.py` wurde dafür nicht verändert; Aktivierung,
Abhängigkeiten, Argumente, Outputs und Berichtseinbindung stehen ausschließlich
unter `pipeline.modules` in `config_v2.yaml`.

## Eingaben

- `maxqda_export.csv` bzw. eigener MAXQDA-Export als UTF-8-CSV mit Semikolon
- `Kategoriesystem.csv` als UTF-8-CSV mit Semikolon
- erwartete Codebuchspalten: `Kategorie`, `Unterkategorie`, `Ausprägung`,
  `Facette`, `Definition`, `Ankerbeispiel`

Übliche alternative Spaltenbezeichnungen werden erkannt. Fehlen notwendige
Spalten oder Dateien, bricht das jeweilige Modul mit einer konkreten Meldung ab.
Leere Hierarchieebenen bleiben bewusst leer, weil das reale Kategoriesystem auch
Codes auf höheren Ebenen enthält. Der vollständige Codepfad wird aus allen
nichtleeren Hierarchiekomponenten mit ` > ` gebildet.

## Module

1. `code_verification.py` prüft den menschlich vergebenen vollständigen
   Codepfad gegen Definition und Ankerbeispiel. Nicht existierende LLM-Codes und
   fremde Segment-IDs werden abgewiesen. Originaltexte werden deterministisch
   aus den tatsächlichen Segmentdaten übernommen.
2. `blind_coding.py` übergibt dem LLM Segment und Codebuch, jedoch nicht den
   menschlich vergebenen Code. Zulässig sind ausschließlich vorhandene
   vollständige Codepfade sowie `unklar` und `keine_zuordnung`.
3. `coding_agreement.py` arbeitet rein deterministisch. Es erzeugt exakte und
   hierarchische Agreement-Werte, Verwechslungspaare, Konfusionsmatrix,
   Falllisten und – sofern methodisch sinnvoll – exploratives Cohen's Kappa für
   single-label nominale exakte Codes. Die Kennzahl ist ausdrücklich als
   **Human–LLM Coding Agreement**, nicht als klassische Interrater-Reliabilität,
   bezeichnet.

## Outputs

```text
code_verification_v1.md
code_verification_v1.json
blind_coding_v1.md
blind_coding_v1.json
coding_agreement_v1.md
coding_agreement_v1.json
coding_agreement_confusion.png   # wenn eine Matrix sinnvoll darstellbar ist
code_verification.log
blind_coding.log
coding_agreement.log
```

Die drei Logdateien enthalten Start und Abschluss des jeweiligen Moduls,
Fallzahlen und Fehlermeldungen. Die LLM-Module protokollieren außerdem
verworfene, nicht im Kategoriesystem vorhandene Alternativcodes. Die Logs
enthalten standardmäßig keine vollständigen Rohantworten des LLM.

`code_verification` und `blind_coding` zeigen während der Verarbeitung außerdem
einen Konsolenfortschritt mit `verarbeitet/gesamt`, Prozentwert, bisheriger
Laufzeit und geschätzter Restzeit. Die Schätzung stabilisiert sich erst nach
mehreren Segmenten und kann bei unterschiedlich langen Reparaturaufrufen
schwanken.

## Optionaler LLM-Raw-Audit

Die unveränderten LLM-Antworten sind standardmäßig deaktiviert:

```yaml
coding_validation:
  log_raw_llm_output: false
```

Mit `true` entstehen zusätzlich:

```text
code_verification_raw.jsonl
blind_coding_raw.jsonl
```

Jede JSONL-Zeile enthält Zeitstempel, Modul, Segment-ID, Aufruftyp
(`initial`/`repair`), den unveränderten Raw-Output sowie den anschließenden
Validierungsstatus. Die Dateien werden fortgeschrieben und können sensible,
aus Interviewmaterial abgeleitete Inhalte enthalten. `coding_agreement` hat
keinen Raw-Audit, weil dieses Modul kein LLM aufruft.

Start des vollständigen Workflows:

```bash
python 00_WORKFLOW_RUNNER.py
```

Für Tests liegt unter `tests/` ein synthetischer semikolon-getrennter Datensatz
mit Mock-LLM-Antworten. Der Test benötigt kein laufendes Ollama-Modell.

