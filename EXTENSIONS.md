# Mehrfachcodierung, Prüfliste und große Gesamtsynthesen

## Mehrfachcodierung je Passage

`coding_agreement.label_mode: multi_label` benötigt eine explizite Spalte `columns.unit_id`, im Beispiel `PassageID`. Mehrere Codierzeilen derselben Passage müssen exakt denselben Text und dieselbe Person haben. Gleiche Texte allein werden nicht automatisch zusammengelegt. Fehlende oder widersprüchliche Passage-IDs werden vor dem ersten Modellaufruf abgewiesen.

Blind-Coding fragt jede Passage genau einmal mit einer Liste sämtlicher passender Codes ab. Menschliche Codes, die Zahl ihrer Codierzeilen und die ursprünglichen Kennungen sind nicht Teil dieser Anfrage. Die Vorhersage darf mehrere Codes, begründet keine Zuordnung (`none`) oder eine Enthaltung (`abstained`) enthalten. Bekannte Alternativcodes einer alten Single-Label-Antwort werden nicht nachträglich als Mehrfachzuordnung umgedeutet. Bestehende zeilenweise Blind-Outputs erfordern einen neuen Lauf.

Der Bericht vergleicht Codemengen je Passage: exakte Mengenübereinstimmung, Micro-Präzision, Micro-Recall, Micro-F1 und mittlerer Jaccard. Fehlende und zusätzliche Codes werden pro Passage aufgeführt. Die menschliche Zuordnung ist dabei die Vergleichsreferenz, kein automatisch geprüfter Wahrheitsmaßstab. Technische Fehler, ungültige menschliche Codes und Enthaltungen werden mit ihrer Abdeckung separat ausgewiesen; `none` zählt dagegen als auswertbare leere Vorhersage. Cohen's Kappa bleibt in diesem Modus deaktiviert.

## Entscheidungen lokal prüfen und getrennt speichern

Nach Coding-Agreement und Evidence-Audit erzeugt der Workflow `review_queue.html`, `review_queue.json` und `review_queue.md`. Die HTML-Datei lässt sich ohne Server und ohne Internet im Browser öffnen. Sie zeigt Originaltext, Codes, fehlende/zusätzliche Vorschläge, Modellbegründung, Verifikation und zugehörige Audit-Gegenbelege. Ein Gegenbeleg zu einem analytischen Befund ist nicht automatisch eine Widerlegung eines einzelnen Codes.

Zunächst sind nur prüfbedürftige Fälle sichtbar. Bestätigte Fälle lassen sich einblenden. Pro Fall kann man menschliche Codes beibehalten, Modellcodes übernehmen, eigene Codes auswählen oder die Entscheidung offenlassen. Abgeschlossene Entscheidungen benötigen eine Begründung und eine prüfende Person.

**Es gibt keine automatische Speicherung:** „Entscheidungen speichern“ lädt eine separate JSON-Datei herunter. Vor dem Schließen sichern; beim nächsten Öffnen über „Entscheidungen laden“ fortsetzen. Der Download verändert weder Originaldaten noch Modelloutput. Für eine validierte Prüfversion im Laufverzeichnis:

```bash
python /pfad/zum/programm/review_queue.py --queue-json review_queue.json --import-decisions /pfad/zum/download/review_decisions_draft.json --decisions-out review_decisions_v1.json
```

Die Prüfung weist fremde Versionen, doppelte Fälle, unbekannte Codes, widersprüchliche Entscheidungen und fehlende Pflichtangaben ab. Ein vorhandenes Ziel wird nicht überschrieben; für weitere Prüfstände einen neuen Namen wählen. Die Entscheidungen werden nicht automatisch in MAXQDA oder die Eingabe-CSV zurückgeschrieben. Prüflisten und Entscheidungen können echte Interviewtexte enthalten und gehören ausschließlich in die private Ablage.

## Mehrstufige Gesamtsynthese

Passt die Gesamtsynthese nicht in das konfigurierte Kontextbudget, zerlegt das Programm die analytischen Quellen an strukturellen Grenzen in Teilbefunde. Die Teilanalysen werden bei Bedarf über weitere Ebenen zusammengeführt. Einzelne Befunde bleiben ungeteilt; ein zu großer Einzelbefund wird weiterhin kontrolliert abgewiesen.

`llm.hierarchical_synthesis` steuert `enabled`, `max_calls`, `max_levels`, `batch_items` und `summary_chars`. `force: true` ist für gezielte Tests vorgesehen und im ausgelieferten Standard nicht gesetzt. Bereits ein zu großer fester Prompt wird vor Modellaufrufen abgewiesen. Ein ausbleibender Größenfortschritt oder ein erreichtes Limit beendet den Vorgang. Damit entstehen weder eine Endlosschleife noch eine unbemerkte Kürzung der Eingabe.

Im JSON der Gesamtsynthese steht `hierarchical_reduction`: Originalteilbefunde mit Quellenpfaden, sämtliche Verdichtungsstufen und ein vom Programm geführter Graph der tatsächlich verwendeten Eingaben. Finale empirische Einträge müssen gültige Verweise auf Teilanalysen tragen. Die vollständigen analytischen Originalausgaben bleiben erhalten. Diese Herkunftsnachweise belegen, welche Eingaben verwendet wurden; sie garantieren nicht, dass das Modell bei der Verdichtung jede Nuance erhalten hat. Widersprüche und Unsicherheit sollen ausdrücklich erhalten bleiben und müssen fachlich geprüft werden.

Die hierarchische Verarbeitung betrifft die Gesamtsynthese. Andere Module behalten ihre eigenen Grenzen: Relations- und Auditbefunde werden bereits paketweise bearbeitet; ein übergroßes Codebuch, ein einzelnes Interview oder ein übergroßer Eingabebestand eines vorgelagerten globalen Moduls können weiterhin eine angepasste Konfiguration erfordern. Ein neuer Lauf nach Softwareänderungen bleibt erforderlich.
