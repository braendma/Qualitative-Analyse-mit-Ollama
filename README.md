# 🧠 Qualitative Analyse-Pipeline mit Ollama

### Modulare, lokale und nachvollziehbare LLM-Pipeline für kodierte Interviewdaten

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Ollama](https://img.shields.io/badge/LLM-Ollama-black)
![License](https://img.shields.io/badge/License-MIT-green)
![Workflow](https://img.shields.io/badge/Workflow-YAML--modular-orange)

---

## 🌟 Kurzbeschreibung

Diese Pipeline unterstützt die **mehrstufige qualitative Auswertung bereits kodierter Interviewdaten** – beispielsweise aus einem MAXQDA-CSV-Export – mit einem lokal über **Ollama** ausgeführten Large Language Model.

Aus den kodierten Segmenten entstehen schrittweise **inhaltliche Cluster, Zusammenfassungen, facettenbezogene SWOT-Analysen, Meta-SWOTs, Personenanalysen, Fallvergleiche, Kontrast- und Negativfallanalysen, Zusammenhangsanalysen, Ambivalenzanalysen, ein Evidence-Audit und eine abschließende Gesamtsynthese**. Drei zusätzliche Module prüfen menschliche Codes gegen ein externes Kategoriesystem, führen ein blindes LLM-Coding durch und berechnen ein deterministisches **Human–LLM Coding Agreement**.

Der gesamte Workflow wird mit einem einzigen Kommando gestartet:

```bash
python 00_WORKFLOW_RUNNER.py
```

Die Besonderheit der aktuellen Architektur: **`00_WORKFLOW_RUNNER.py` kennt keine fest einprogrammierte Modulliste mehr.** Reihenfolge, Abhängigkeiten, Argumente, Outputs und Berichtseinbindung werden vollständig über `config_v2.yaml` gesteuert. Neue Analysebausteine können dadurch ergänzt werden, ohne den Orchestrator umzubauen.

---

## ✨ Highlights

- 🏠 **Lokale LLM-Verarbeitung mit Ollama**
- 🧩 **Modularer YAML-gesteuerter Workflow**
- 🔗 **Automatische Abhängigkeitsauflösung zwischen Modulen**
- 🧾 **JSON-Zwischenprodukte für Auditierbarkeit und Weiterverwendung**
- 🆔 **Global eindeutige Segment-IDs**
- 💬 **Originalzitate werden über validierte Segment-IDs zurückgeführt**
- 🛡️ **Retry-, Normalisierungs- und Self-Repair-Mechanismen**
- 📊 **Clusterplots und automatisch erzeugter Gesamtbericht**
- 🔎 **Kontrast-, Negativfall- und Ambivalenzanalyse**
- 🔗 **Analyse thematischer Beziehungen zwischen Codepfaden**
- 🧪 **Evidence-Audit für empirische Breite und Gegenbelege**
- 👥 **Fallbezogene Personenanalyse und vorsichtige Typenbildung**
- 🧠 **Abschließende Gesamtsynthese über mehrere Analyseebenen**
- ✅ **Code-Verifikation gegen Definitionen und Ankerbeispiele**
- 🙈 **Blind-Coding ohne Kenntnis des menschlichen Codes**
- 📐 **Deterministisches Human–LLM Coding Agreement mit Konfusionsmatrix**
- ⏱️ **Dynamische Fortschritts- und Restzeitanzeige für lange LLM-Läufe**
- 🧾 **Separate Modul-Logs und optionaler LLM-Raw-Audit als JSONL**

---

# 🧩 Aktueller Analyse-Workflow

```text
Kodierter CSV-Export
        │
        ▼
┌──────────────────────────────┐
│ 1. Clusteranalyse            │
└───────┬──────────────┬───────┘
        │              │
        │              ├──► Code-Verifikation ──┐
        │              └──► Blind-Coding ───────┤
        │                                        ▼
        │                         Human–LLM Coding Agreement
        ▼
┌──────────────────────────────┐
│ 2. Cluster-Zusammenfassungen │
└───────┬──────────┬───────────┘
        │          │
        │          ├──────────────────────────────┐
        │          │                              │
        ▼          ▼                              ▼
┌────────────┐ ┌──────────────────┐      ┌────────────────────┐
│ 3. SWOT    │ │ 5. Personen-     │      │ 8. Zusammenhangs-  │
│ pro Pfad   │ │ analyse          │      │ analyse            │
└─────┬──────┘ └───────┬──────────┘      └─────────┬──────────┘
      ▼                ▼                           │
┌──────────────┐ ┌──────────────────┐              │
│ 4. Meta-SWOT│ │ 6. Personen-     │              │
│             │ │ vergleich / Typen│              │
└──────┬───────┘ └───────┬──────────┘              │
       │                 ▼                         │
       │        ┌──────────────────┐               │
       │        │ 7. Kontrast- /   │               │
       │        │ Negativfallanalyse│              │
       │        └────────┬─────────┘               │
       │                 │                         │
       │        ┌────────▼─────────┐               │
       │        │ 9. Ambivalenz-   │               │
       │        │ analyse          │               │
       │        └────────┬─────────┘               │
       │                 │                         │
       └────────────┬────┴───────────────┬─────────┘
                    ▼                    │
          ┌──────────────────────┐       │
          │ 10. Evidence-Audit   │◄──────┘
          └──────────┬───────────┘
                     ▼
          ┌──────────────────────┐
          │ 11. Gesamtsynthese   │
          └──────────┬───────────┘
                     ▼
               gesamtbericht.md
```

---

# ✅ Coding-Validierung und Human–LLM Agreement

Die drei Qualitätssicherungsmodule werden wie alle anderen Schritte ausschließlich über `config_v2.yaml` eingebunden:

1. **`code_verification`** prüft den menschlich vergebenen vollständigen Codepfad gegen Definition und Ankerbeispiel des externen Kategoriesystems. Ergebnisse sind `bestätigt`, `teilweise_passend`, `nicht_passend` oder `unklar`.
2. **`blind_coding`** erhält Segment und Codebuch, aber nicht den menschlichen Code. Zulässig sind nur vorhandene vollständige Codepfade sowie `unklar` und `keine_zuordnung`.
3. **`coding_agreement`** arbeitet rein deterministisch und berechnet exakte sowie hierarchische Übereinstimmung, Verwechslungspaare, Fallstatus, eine Konfusionsmatrix und – nur wenn methodisch sinnvoll – exploratives Cohen's Kappa für single-label nominale exakte Codes.

Alle LLM-genannten Codepfade und Segment-IDs werden gegen die tatsächlichen Eingaben validiert. Erfundene Alternativcodes werden verworfen und protokolliert. Strukturell weiterhin ungültige Hauptantworten werden kontrolliert als `unklar` weitergeführt, statt den gesamten Workflow abzubrechen.

Die Kennzahlen werden ausdrücklich als **Human–LLM Coding Agreement** bezeichnet und nicht als klassische Interrater-Reliabilität zwischen unabhängigen menschlichen Ratern.

Während Verify und Blind-Coding zeigt die Konsole dynamisch:

```text
[Code-Verifikation] [########------------] 320/844 (37.91%) | Laufzeit 00:42:10 | Restzeit ca. 01:09:04
```

Optional können die unveränderten LLM-Antworten als append-only JSONL-Audit gespeichert werden:

```yaml
coding_validation:
  log_raw_llm_output: false  # auf true setzen für Raw-Audit
```

Bei `true` entstehen `code_verification_raw.jsonl` und `blind_coding_raw.jsonl`. Diese Dateien können sensible, aus Interviewmaterial abgeleitete Inhalte enthalten und sollten nicht ungeprüft geteilt werden.

---

# 🔬 Die Module

## 1. Clusteranalyse

Die Pipeline zerlegt den konfigurierten Codepfad in:

```text
Hauptkategorie > Subkategorie > Facette
```

Cluster werden **innerhalb des vollständigen Hierarchiepfades** gebildet. Gleichnamige Facetten unter unterschiedlichen Haupt- oder Subkategorien bleiben dadurch getrennt.

Jedes Segment erhält eine global eindeutige ID:

```text
Dokumentname#SEG00000
Dokumentname#SEG00001
Dokumentname#SEG00002
...
```

Die Nummerierung läuft über den gesamten Datensatz und startet nicht pro Person oder Facette neu.

**Outputs:**

```text
clusterer_output.md
clusters_output.json
id_to_text.json
plots/
```

---

## 2. Cluster-Zusammenfassungen

Für jedes Cluster wird eine datenbasierte Zusammenfassung erzeugt. Hierarchie, Clusterdefinition und Segmentreferenzen bleiben erhalten.

**Outputs:**

```text
summary_v1.md
summary_v1.json
```

---

## 3. SWOT pro vollständigem Codepfad

SWOT wird nicht nur auf Hauptkategorie-Ebene durchgeführt, sondern auf Ebene des vollständigen Pfades:

```text
Hauptkategorie > Subkategorie > Facette
```

Analysiert werden:

- **Stärken**
- **Schwächen**
- **Chancen**
- **Risiken**

Jeder Befund wird strukturiert mit Thema, Analyse und validierten Segment-IDs gespeichert.

Chancen und Risiken dürfen vorsichtige analytische Ableitungen sein, müssen aber unmittelbar im Material angelegt sein.

**Outputs:**

```text
swot_v1.md
swot_v1.json
```

---

## 4. Meta-SWOT

Die Meta-SWOT verdichtet die einzelnen SWOT-Befunde über mehrere Codepfade hinweg.

Dabei wird unterschieden zwischen:

- **übergreifenden Mustern**, die von mehreren Analysepfaden getragen werden,
- **quellenspezifischen Einzelbefunden**, die bewusst erhalten bleiben.

Jeder SWOT-Befund erhält dafür eine stabile `finding_id`, die später auch vom Evidence-Audit verwendet werden kann.

**Outputs:**

```text
meta_swot_v1.md
meta_swot_v1.json
```

---

## 5. Personenanalyse

Für jede im Datensatz vorkommende Person wird eine qualitative Fallanalyse erstellt.

Mögliche Bestandteile:

- zentrale Themen
- wiederkehrende Perspektiven
- empirisch belegte Spannungsfelder
- kontrastierende Aspekte innerhalb des Falls
- kurze Gesamtverdichtung

Die Analyse ist ausdrücklich **kein psychologisches Persönlichkeitsprofil**.

**Outputs:**

```text
person_analysis_v1.md
person_analysis_v1.json
```

---

## 6. Personenvergleich und Typenbildung

Die einzelnen Fallanalysen werden miteinander verglichen.

Analysiert werden unter anderem:

- gemeinsame Muster
- zentrale Unterschiede
- vorsichtige qualitative Typen
- nicht eindeutig zuordenbare Fälle

Die Typenbildung ist deskriptiv und datenbasiert – keine psychologische Klassifikation.

**Outputs:**

```text
person_comparison_v1.md
person_comparison_v1.json
```

---

## 7. Kontrast- und Negativfallanalyse

Dieses Modul sucht gezielt nach Fällen, die dominante Muster nicht bestätigen oder relativieren.

Dadurch werden Ausnahmen und abweichende Perspektiven nicht durch zu starke Verdichtung unsichtbar.

**Outputs:**

```text
contrast_analysis_v1.md
contrast_analysis_v1.json
```

---

## 8. Zusammenhangsanalyse

Die Zusammenhangsanalyse untersucht Beziehungen zwischen unterschiedlichen Themen bzw. Codepfaden.

Beziehungen können beispielsweise als:

- gemeinsames Auftreten
- inhaltliche Ergänzung
- Spannungsverhältnis
- von Befragten explizit hergestellte Verbindung

beschrieben werden.

Die Pipeline soll dabei **keine unbelegten Kausalbeziehungen erzeugen**.

Für größere Codesysteme kann die Zahl analysierter Paare in der YAML begrenzt werden:

```yaml
analysis_settings:
  relation_analysis:
    max_pairs: 80
    max_segments_per_path: 6
```

**Outputs:**

```text
relation_analysis_v1.md
relation_analysis_v1.json
```

---

## 9. Ambivalenz- und Widerspruchsanalyse

Dieses Modul untersucht **intrapersonelle Spannungen**.

Im Mittelpunkt steht nicht der Unterschied zwischen zwei Personen, sondern die Frage, ob dieselbe Person unterschiedliche, widersprüchliche oder ambivalente Perspektiven äußert.

Die Segmentbelege werden über vorhandene IDs validiert und anschließend auf den Originaltext zurückgeführt.

**Outputs:**

```text
ambiguity_analysis_v1.md
ambiguity_analysis_v1.json
```

---

## 10. Evidence-Audit

Der Evidence-Audit prüft, **wie breit zentrale Befunde im vorhandenen qualitativen Material abgestützt sind**.

Dabei können unter anderem berücksichtigt werden:

- Zahl stützender Personen
- Zahl stützender Segmente
- Zahl beteiligter Analysepfade
- vorhandene Gegenbelege
- Ambivalenzen und Relativierungen

Wichtig:

> **Empirische Breite ist keine statistische Signifikanz.**

Die Kennzahlen dienen der Nachvollziehbarkeit qualitativer Befunde und nicht der inferenzstatistischen Bewertung.

Zählbare Evidenzmerkmale werden in Python berechnet. Das LLM darf diese Zahlen nicht frei erfinden.

**Outputs:**

```text
evidence_audit_v1.md
evidence_audit_v1.json
```

---

## 11. Gesamtsynthese

Die letzte Analyseebene verbindet aktuell:

- Meta-SWOT
- Personenvergleich
- Kontrastanalyse
- Zusammenhangsanalyse
- Ambivalenzanalyse
- Evidence-Audit

Die Gesamtsynthese arbeitet damit auf bereits verdichteten Analysen und erzeugt eine übergreifende Ergebnisdarstellung.

**Outputs:**

```text
overall_synthesis_v1.md
overall_synthesis_v1.json
gesamtbericht.md
```

---

# 🚀 Quickstart

## 1. Repository klonen

```bash
git clone https://github.com/braendma/Qualitative-Analyse-mit-Ollama.git
cd Qualitative-Analyse-mit-Ollama
```

## 2. Virtuelle Umgebung erstellen

```bash
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows:

```powershell
.venv\Scripts\activate
```

## 3. Dependencies installieren

```bash
pip install -r requirements.txt
```

Aktuell werden verwendet:

```text
pandas
numpy
matplotlib
PyYAML
ollama
```

## 4. Ollama vorbereiten

Ollama installieren und ein geeignetes Modell laden, beispielsweise:

```bash
ollama pull granite4.1:8b
```

## 5. Beispieldaten

Das Repository enthält bereits zwei aufeinander abgestimmte fiktive UTF-8-Testdateien mit Semikolon-Trennung:

```text
maxqda_export.csv    # 60 synthetische Segmente aus 10 fiktiven Interviews
Kategoriesystem.csv # 12 passende Codepfade mit Definitionen und Ankerbeispielen
```

Damit kann der Workflow nach Installation von Ollama und Modell direkt gestartet werden. Für eigene Daten werden beide Dateien ersetzt oder die Pfade in `config_v2.yaml` angepasst.

## 6. Workflow starten

```bash
python 00_WORKFLOW_RUNNER.py
```

Mit einer anderen Interview-CSV:

```bash
python 00_WORKFLOW_RUNNER.py --csv eigener_export.csv
```

Mit eigenem Output-Verzeichnis:

```bash
python 00_WORKFLOW_RUNNER.py \
  --csv eigener_export.csv \
  --output-dir meine_analyse
```

---

# 📥 Erwartete Eingabedaten

Die Pipeline arbeitet auf **bereits kodierten Segmenten**.

Mindestens benötigt werden die in der YAML konfigurierten Spalten für:

```text
Code
Segment
Dokumentname
```

Beispiel:

```csv
Dokumentname;Code;Segment
Interview_01;Hauptthema > Unterthema > Facette A;"Beispielsegment aus einem Interview."
Interview_02;Hauptthema > Unterthema > Facette A;"Weiteres Beispielsegment."
```

Die tatsächlichen Spaltennamen können in `config_v2.yaml` angepasst werden.

Für Code-Verifikation und Blind-Coding wird zusätzlich `Kategoriesystem.csv` erwartet. Mindestens erforderlich sind:

```text
Kategorie
Unterkategorie
Ausprägung
Facette
Definition
Ankerbeispiel
```

Leere Hierarchieebenen sind zulässig. Der vollständige Codepfad wird aus allen nichtleeren Ebenen in der Reihenfolge `Kategorie > Unterkategorie > Ausprägung > Facette` gebildet. Jeder im Interviewexport verwendete Code sollte exakt einem solchen Pfad entsprechen.

---

# ⚙️ YAML-gesteuerte Pipeline

Der zentrale Unterschied zur früheren festen Workflow-Architektur ist die Deklaration unter:

```yaml
pipeline:
  modules:
```

Ein Modul sieht beispielsweise so aus:

```yaml
- id: ambiguity_analysis
  name: Ambivalenz- und Widerspruchsanalyse
  script: ambiguity_analysis.py
  enabled: true
  depends_on:
    - person_analysis

  args:
    - --config
    - "{config}"
    - --person-json
    - person_analysis_v1.json
    - --idmap-json
    - id_to_text.json
    - --out-md
    - ambiguity_analysis_v1.md
    - --out-json
    - ambiguity_analysis_v1.json

  outputs:
    - ambiguity_analysis_v1.md
    - ambiguity_analysis_v1.json

  report:
    title: Ambivalenz- und Widerspruchsanalyse
    markdown: ambiguity_analysis_v1.md
```

`00_WORKFLOW_RUNNER.py`:

1. liest die Moduldefinitionen,
2. prüft Abhängigkeiten,
3. bestimmt automatisch eine gültige Ausführungsreihenfolge,
4. startet die Module,
5. prüft deklarierte Outputs,
6. protokolliert den Status,
7. baut den Gesamtbericht aus den aktivierten Report-Modulen.

---

# ➕ Neues Analysemodul ergänzen

Ein neues Modul benötigt im einfachsten Fall:

```text
mein_modul.py
mein_modul_core.py
```

Danach wird nur die YAML erweitert:

```yaml
- id: mein_modul
  name: Mein neues Analysemodul
  script: mein_modul.py
  enabled: true
  depends_on:
    - summarizer

  args:
    - --config
    - "{config}"
    - --input-json
    - summary_v1.json
    - --out-md
    - mein_modul_v1.md
    - --out-json
    - mein_modul_v1.json

  outputs:
    - mein_modul_v1.md
    - mein_modul_v1.json

  report:
    title: Mein neues Analysemodul
    markdown: mein_modul_v1.md
```

**`00_WORKFLOW_RUNNER.py` muss dafür nicht verändert werden.**

Das macht die Pipeline zu einem kleinen erweiterbaren Framework für qualitative LLM-gestützte Analysebausteine.

---

# 📂 Typische Output-Struktur

```text
workflow_output/
│
├── clusterer_output.md
├── clusters_output.json
├── id_to_text.json
│
├── code_verification_v1.md
├── code_verification_v1.json
├── code_verification.log
├── blind_coding_v1.md
├── blind_coding_v1.json
├── blind_coding.log
├── coding_agreement_v1.md
├── coding_agreement_v1.json
├── coding_agreement_confusion.png
├── coding_agreement.log
│
├── summary_v1.md
├── summary_v1.json
│
├── swot_v1.md
├── swot_v1.json
│
├── meta_swot_v1.md
├── meta_swot_v1.json
│
├── person_analysis_v1.md
├── person_analysis_v1.json
│
├── person_comparison_v1.md
├── person_comparison_v1.json
│
├── contrast_analysis_v1.md
├── contrast_analysis_v1.json
│
├── relation_analysis_v1.md
├── relation_analysis_v1.json
│
├── ambiguity_analysis_v1.md
├── ambiguity_analysis_v1.json
│
├── evidence_audit_v1.md
├── evidence_audit_v1.json
│
├── overall_synthesis_v1.md
├── overall_synthesis_v1.json
│
├── gesamtbericht.md
├── workflow_manifest.json
├── workflow.log
│
└── plots/
    └── *.png
```

---

# 🛡️ Forschungsintegrität und technische Schutzmechanismen

Die Pipeline versucht LLM-Ausgaben möglichst eng an das vorhandene Material zu binden.

Dazu gehören:

- keine externen empirischen Informationen
- keine unbelegten theoretischen Ergänzungen
- keine erfundenen Ursachen oder Wirkungen
- keine psychologischen Diagnosen
- keine frei erfundenen Segment-IDs
- Validierung zurückgegebener Segment-IDs gegen den tatsächlichen Input
- Originaltext-Mapping über `id_to_text.json`
- strukturierte JSON-Outputs
- robuste JSON-Extraktion
- Normalisierung abweichender Modellantworten
- Retry- und Self-Repair-Mechanismen
- separate JSON-Zwischenprodukte
- Workflow-Manifest und Logs
- Validierung sämtlicher LLM-genannter Codes gegen `Kategoriesystem.csv`
- deterministische Rückführung von Originaltexten statt frei erzeugter Zitate
- kontrolliertes `unklar` statt Übernahme strukturell ungültiger LLM-Antworten

Ein LLM kann dennoch Fehler machen. Die Pipeline reduziert bestimmte Fehlertypen, ersetzt aber keine wissenschaftliche Prüfung.

---

# 📊 Visualisierung

Der Clusterer erzeugt Diagramme zu:

- Segmentanzahl pro Cluster
- Zahl unterschiedlicher Personen pro Cluster

Plot-Dateinamen berücksichtigen den vollständigen Analysepfad, damit gleichnamige Facetten aus unterschiedlichen Bereichen keine Dateien überschreiben.

---

# 🔐 Datenschutz

Bei lokaler Nutzung von Ollama kann das Interviewmaterial grundsätzlich auf dem eigenen Rechner verarbeitet werden.

Trotzdem gilt:

> **Lokale Verarbeitung ersetzt keine datenschutzrechtliche und forschungsethische Prüfung.**

Vor Veröffentlichung, Weitergabe, Cloud-Uploads oder dem Teilen von Debug-Dateien sollten personenbezogene Inhalte geprüft und gegebenenfalls anonymisiert oder pseudonymisiert werden.

Das gilt besonders für die optionalen Dateien `code_verification_raw.jsonl` und `blind_coding_raw.jsonl`, da sie unveränderte Modellausgaben enthalten.

Die mitgelieferte `config_v2.yaml`, `maxqda_export.csv` und `Kategoriesystem.csv` sind neutralisierte bzw. vollständig fiktive öffentliche Beispiele.

---

# ⚠️ Methodische Grenzen

Die Pipeline unterstützt qualitative Analyse, automatisiert aber keine wissenschaftliche Wahrheit.

Insbesondere gilt:

- LLM-Ausgaben können fehlerhaft oder instabil sein.
- Clusterbildung bleibt modell- und promptabhängig.
- Qualitative Häufigkeit ist nicht automatisch qualitative Bedeutung.
- Evidence-Breite ist keine statistische Signifikanz.
- Meta-SWOT-Cluster sind analytische Verdichtungen und keine statistischen Faktoren.
- Typenbildung ist explorativ und keine psychologische Klassifikation.
- Zusammenhangsanalyse darf nicht automatisch als Kausalmodell gelesen werden.
- Ambivalenzen benötigen überprüfbare Belege im Material.
- Chancen und Risiken einer SWOT bleiben interpretative Kategorien.
- Die finale Interpretation und wissenschaftliche Verantwortung liegen bei den Forschenden.

---

# 🧪 Testbarkeit

Durch die modulare JSON-basierte Architektur lassen sich einzelne Stufen unabhängig testen.

Unter anderem können kontrolliert geprüft werden:

- Datenfluss
- Segment-ID-Konsistenz
- JSON-Schnittstellen
- Prompt-Platzhalter
- Modulabhängigkeiten
- topologische Ausführungsreihenfolge
- Output-Dateien
- Zitat-Mapping
- Meta-Clustering
- Evidence-Berechnungen
- automatische Berichtserstellung

LLM-Antworten können für Integrationstests gemockt werden, sodass ein Großteil der Programmlogik unabhängig vom lokal installierten Modell testbar bleibt.

Die Coding-Validierungstests laufen ohne Ollama:

```bash
python -m unittest discover -s tests -v
```

---

# 🧰 Einzelne Module manuell starten

Für Entwicklung oder Debugging können die Module weiterhin einzeln ausgeführt werden:

```bash
python clusterer.py
python summarizer.py
python swot.py
python meta_swot.py
python person_analysis.py
python person_comparison.py
python contrast_analysis.py
python relation_analysis.py
python ambiguity_analysis.py
python evidence_audit.py
python code_verification.py
python blind_coding.py
python coding_agreement.py
python overall_synthesis.py
```

Im normalen Betrieb ist jedoch der modulare Runner vorgesehen:

```bash
python 00_WORKFLOW_RUNNER.py
```

---

# 📁 Projektstruktur

```text
00_WORKFLOW_RUNNER.py
config_v2.yaml
maxqda_export.csv
Kategoriesystem.csv
│
├── clusterer.py
├── clusterer_core.py
├── summarizer.py
├── summarizer_core.py
├── swot.py
├── swot_core.py
├── meta_swot.py
├── meta_swot_core.py
├── person_analysis.py
├── person_analysis_core.py
├── person_comparison.py
├── person_comparison_core.py
├── contrast_analysis.py
├── contrast_analysis_core.py
├── relation_analysis.py
├── relation_analysis_core.py
├── ambiguity_analysis.py
├── ambiguity_analysis_core.py
├── evidence_audit.py
├── evidence_audit_core.py
├── code_verification.py
├── code_verification_core.py
├── blind_coding.py
├── blind_coding_core.py
├── coding_agreement.py
├── coding_agreement_core.py
├── coding_validation_common.py
├── overall_synthesis.py
├── overall_synthesis_core.py
├── plot_core.py
├── utils_prompt.py
├── utils_csv.py
└── requirements.txt
```

---

# 🛠️ Mögliche nächste Erweiterungen

Durch die modulare Architektur können zusätzliche qualitative Analysebausteine relativ einfach ergänzt werden, zum Beispiel:

- Fall × Thema-Matrix
- zeitliche / sequenzielle Interviewanalyse
- analytische Memo-Generierung
- Code-Ko-Okkurrenz-Matrix
- Gruppen- oder Kohortenvergleich
- Stabilitätsanalyse über mehrere LLM-Läufe
- Modellvergleich zwischen verschiedenen Ollama-Modellen
- HTML-/DOCX-/PDF-Reporting
- interaktive Ergebnisexploration
- methodischer Audit-Trail

Contributions und neue Analyseideen sind willkommen.

---

# 🧾 Lizenz

MIT License

Frei nutzbar für Forschung, Lehre und Entwicklung entsprechend den Bedingungen der Lizenz.

---

# 🙌 Contributors

### Marcus Brändle

**Konzeption · Forschungsdesign · fachliche Anforderungen · Implementierung · Testing · methodische Validierung**

Initiierung und fachliche Weiterentwicklung des Projekts aus dem Anwendungskontext qualitativer Interviewforschung.

### ChatGPT · OpenAI

**Softwarearchitektur · Code-Co-Authoring · Refactoring · Debugging · Testdesign · Promptarchitektur · Dokumentation**

Mitarbeit an wesentlichen Teilen der modularen Architektur, der Analysebausteine, JSON-Schnittstellen, Fehlerbehandlung, Tests und Dokumentation.

> **Hinweis zur KI-gestützten Entwicklung:** Teile des Codes und der Dokumentation wurden in Zusammenarbeit mit ChatGPT von OpenAI entwickelt. KI-generierter oder KI-überarbeiteter Code sollte vor produktiver oder wissenschaftlicher Nutzung geprüft und validiert werden.

---

# 🎉 Los geht's

```bash
python 00_WORKFLOW_RUNNER.py
```

**Kodierte Interviewdaten rein → modulare qualitative Analysen → nachvollziehbare Zwischenprodukte → Gesamtsynthese → `gesamtbericht.md`.**

