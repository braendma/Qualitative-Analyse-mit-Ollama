# Thematische Zählung – Entwicklervertrag des gemeinsamen Kerns

**Interner Entwicklungsstand S13b:** Der gemeinsame Kern besitzt jetzt eine
ausführbare Themenzuordnung, deterministische Zählung, häufigkeitsinformierte
Interpretation und drei Adapter für Cluster, Clusterzusammenfassungen und SWOT.
`execute_perspective` verbindet diese Funktionen intern; die Abläufe lassen
sich mit künstlichen Modellantworten testen. **Oberfläche und Workflow-CLI
schalten die neuen Perspektiven noch nicht frei.** Die vorhandene
Verfügbarkeitsprüfung bleibt gesperrt, bis der jeweilige Einstieg vollständig
integriert ist. Die bisherige qualitative Arbeitsweise bleibt unverändert.

Methodische Einordnung und Literatur stehen im
[Handbuch: Aussagen und Personen zählen](HANDBUCH.md#aussagen-und-personen-zählen-methodische-einordnung)
und in der [bebilderten Handbuchfassung](HANDBUCH.html#aussagen-und-personen-zaehlen).
Der folgende Vertrag beschreibt technische und methodische Grenzen dieser
Implementierung; er stellt keine zusätzlich literaturvalidierte LLM-Methode dar.

## 1. Gemeinsame Materialbasis

`thematic_material.build_material(segments, person_basis="unconfirmed", provenance=None)`
arbeitet auf bereits geladenen Segmenten. Die reine Funktion kann eine behauptete
Personenbestätigung nicht unabhängig prüfen. Sie darf `person_basis="confirmed"`
nur aus einer vorher geprüften Grundlage erhalten.

Für Dateien übernimmt dies
`load_counting_material(config_path, input_path=None, run_dir=None, require_confirmed=True)`:

- Bestätigte Dokument-/Personenzuordnung gegen die unveränderte Eingabe prüfen.
  Mehrere Dokumentteile bleiben derselben ausdrücklich zugeordneten Person
  zugehörig; normalisierte Namen dürfen keine verschiedenen Personen zusammenführen.
- Codepfade mit dem aktuellen Kategoriensystem abgleichen.
- Eingabe, Konfiguration und Kategoriensystem vor und nach dem Einlesen prüfen;
  bei angegebenem `run_dir` zusätzlich die vorhandene Laufbindung verwenden.
- Die Materialidentität bindet Inhalte, Personenstatus und Herkunft. Originaltexte
  bleiben vollständig; sehr lange Texte werden hier nicht gekürzt.

Explizite Passage-IDs bilden Materialeinheiten über mehrere Codierzeilen hinweg.
Ohne solche IDs bleiben die Einheiten Codierzeilen. Derselbe Wortlaut allein
begründet keine gemeinsame Passage. Widersprüchliche Personen oder Texte einer
Passage und doppelte Segment-IDs werden abgelehnt.

Das Ergebnis enthält `units`, `segment_index`, `persons`, `person_basis`,
`basis_fingerprint` und nachvollziehbare Ausgangszahlen. `unit_ids_for_segments`
übersetzt bekannte Segmentverweise in eindeutige Materialeinheiten. Unbekannte
Verweise werden abgewiesen. Die Bezugsmenge umfasst nur den übergebenen codierten
Export, nicht automatisch vollständige Interviews oder die gesamte Population.

Bei `require_confirmed=False` sind unbestätigte Materialien für technische
Prüfungen zulässig. Daraus werden keine Personenanzahlen abgeleitet. Eine
vorhandene, aber ungültige Personenbestätigung wird auch dann nicht übergangen.

## 2. Thema, Bedeutung der Zählung und Scope

`thematic_counts.count_topics(material, topics, assignments)` benötigt für jedes
Thema eine stabile `topic_id`, `definition`, `inclusion`, `exclusion`, `kind`
und `scope_unit_ids`; `label` ist optional. Definition und ID dürfen nicht leer
sein. Ein-/Ausschlussregeln müssen als Text vorliegen, dürfen jedoch leer sein.
Gleiche Titel begründen keine Zusammenlegung unterschiedlicher Themen.

| `kind` | `count_meaning` im Ergebnis | Zulässige Interpretation |
|---|---|---|
| `explicit` | `expressed_topic_positions` | Dem Thema zugeordnete ausdrücklich geäußerte Positionen. |
| `derived` | `material_support_for_inference` | Stützende beziehungsweise entgegenstehende Materialbasis einer analytischen Ableitung, keine Zahl wörtlich geäußerter Chancen oder Risiken. |
| `membership` | `model_assigned_group_membership` | Gespeicherte Gruppen-/Clusterzugehörigkeit, keine vollständige Nennungshäufigkeit jeder freien Zusammenfassungsaussage. |

`scope_unit_ids` benennt die für dieses Thema zu prüfenden Materialeinheiten.
Der Scope wird ausdrücklich vorgegeben und enthält nur bekannte IDs. Der Kern
entscheidet nicht, ob diese Auswahl inhaltlich angemessen oder vollständig ist.
Deshalb muss der jeweilige Moduladapter den Scope begründen und mit dem
zugehörigen Analysekontext binden.

## 3. Zuordnungsmatrix und unvollständige Beobachtungen

Eine Zuordnungszeile enthält genau `topic_id`, `unit_id` und `status`.
Unbekannte IDs, Einheiten außerhalb des Scopes, unbekannte Statuswerte und doppelte
Zellen werden abgelehnt. Vom LLM geschätzte Zähler sind kein Eingabefeld.

| Status | Bedeutung für den Kern |
|---|---|
| `supported` | Stützende/zugehörige Position oder Mitgliedschaft zugeordnet. |
| `opposed` | Gegenposition zugeordnet. |
| `both` | Beide Positionen dieser Einheit zugeordnet. |
| `no_evidence` | Innerhalb der geprüften Einheit kein entsprechender Beleg zugeordnet. |
| `unclear` | Inhaltlich nicht entschieden. |
| `failed` | Technische Prüfung fehlgeschlagen. |
| `not_checked` | Noch nicht geprüft; auch Standard für eine fehlende Matrixzelle. |

Die ersten vier Zustände gelten technisch als entschieden. Fehlende Zellen
werden ausdrücklich zu `not_checked`, niemals zu `no_evidence`. Die Abdeckung
nennt erwartete und entschiedene Zellen sowie sämtliche Statuszahlen.

Ist mindestens eine Zelle unklar, fehlgeschlagen oder ungeprüft, bleiben
`exact_*` und die daraus abgeleiteten Anteile `null`. Die `observed_*`-Zahlen
zeigen dann die bereits beobachtete Untergrenze innerhalb der gelieferten
Zuordnungen. Sie sind keine gesicherte Untergrenze einer unbekannten
menschlichen Wahrheit: Auch bereits entschiedene Modellzuordnungen können
inhaltlich falsch sein. `assignment_review_status: not_verified_by_counting`
kennzeichnet, dass der Zählkern selbst keine menschliche Bestätigung erteilt.

## 4. Zähleinheiten und Nenner

Je Thema werden Mengen für `supporting`, `opposing`, `both` und `mentioned`
gebildet. `mentioned` ist die Vereinigung der beiden Positionen. Personen
zählen je Menge einmal. Eine Person kann zwei Positionen in unterschiedlichen
Passagen äußern: Dann gehört sie zu beiden Personenmengen, auch wenn keine
einzelne Passage beide Positionen enthält.

Der Ergebnis-Scope nennt Materialeinheiten, zugehörige Codierzeilen und bei
bestätigter Zuordnung Personen. Ergänzend werden Exportgesamtzahlen ausgewiesen.
`unit_share_in_scope` und `person_share_in_scope` beziehen sich auf den
ausdrücklich benannten Themen-Scope, nicht still auf den gesamten Export.
Bei leerem Nenner sind Anteile `null`. Bei unbestätigten Personen bleiben
Personenzahlen und Personenmengen `null`.

Passagenzahlen gibt es nur bei einem ausschließlich aus expliziten Passagen
bestehenden Scope. Codierzeilen oder gemischte Einheiten werden nicht als
Passagen ausgegeben. Mehrfachcodierungen erhöhen die Codierzeilenzahl, aber
nicht die Menge derselben Passage oder Person. Anteile unterschiedlicher
Themen können sich überschneiden und müssen sich nicht zu 100 % summieren.

Technisch vollständige Zählung bedeutet vollständig entschiedene Zellen
innerhalb dieses Scopes. Sie bedeutet weder vollständige Interviews noch
inhaltliche Richtigkeit, Repräsentativität oder eine Qualitätsquote.

## 5. Vorhandene Clusterzuordnung verwenden

`thematic_memberships.cluster_memberships(material, payload)` projiziert
vollständige bestehende Clusterzuordnungen ohne neue Modellanfrage. Es verlangt
einen abgeschlossenen Payload, passende Segment-/Personen-/Passagenmetadaten
und vollständige Abdeckung aller erwarteten Codierzeilen je Codepfad.
Ausgewählte Beispielzitate oder teilweise Ergebnisse erfüllen diesen Vertrag nicht.

Jeder Cluster wird ein eigenes `membership`-Thema. Sein Scope umfasst die
Materialeinheiten des jeweiligen Codepfads. Zugeordnete Einheiten erhalten
`supported`, die übrigen Einheiten dieses Codepfads `no_evidence`; andere
Codepfade gehören nicht in diesen Nenner. Einheiten dürfen mehreren Clustern
angehören, werden aber nicht mehrfach innerhalb derselben Themenmenge gezählt.
Name, Definition, Codepfad und Mitglieds-IDs bestimmen die technische Themen-ID.

Die Funktion validiert die Struktur und liefert einen Inhaltsfingerprint.
Sie ersetzt keine Prüfung, ob die Clusterdatei tatsächlich zum aktuellen Lauf
und seinen unveränderten Eingaben gehört. Vor dem späteren Adapteraufruf muss
der vorhandene deklarierte Artefakt-/Herkunftsweg diese Bindung sichern.

```python
from thematic_material import load_counting_material
from thematic_memberships import cluster_memberships
from thematic_counts import count_topics

material = load_counting_material(config_path, run_dir=run_dir)
# verified_cluster_payload: zuvor über den bestehenden Artefaktvertrag geprüft.
membership = cluster_memberships(material, verified_cluster_payload)
counts = count_topics(material, membership["topics"], membership["assignments"])
```

Das ist ein Aufrufbeispiel für Entwickler, keine neue Workflow-CLI-Anweisung.

`thematic_adapters.build_cluster_topics` ergänzt diese Mitgliedschaften um
stabile `source_links` und eine unveränderte Kopie der qualitativen Quelle.
`build_summary_topics(material, cluster_payload, summary_payload)` verwendet
dieselbe Zuordnung nur dann, wenn jede Zusammenfassung eindeutig anhand von
Codepfad, Clustername, Definition und Segmentmenge zu einem Originalcluster
passt. Eine Zuordnung nur nach ähnlichem Titel ist ausgeschlossen. Die freie
`final_summary` bleibt `unassigned_context`; ihre einzelnen Aussagen werden
nicht automatisch als vollständig zugeordnete Themen gezählt.

### SWOT-Themen für eine vollständige Zuordnung vorbereiten

`thematic_adapters.build_swot_topics(material, payload)` erzeugt feste Themen
aus den bestehenden qualitativen SWOT-Befunden. Der Scope umfasst jeweils
alle Materialeinheiten des tatsächlichen Codepfads. Ausgewählte
`segment_ids` bleiben ausgewählte Belege in `source_links` und werden nicht
als positive Zuordnungen oder als vollständige Materialmenge übernommen.
Der Adapter liefert daher zunächst `assignments: null`.

Codepfade, erwartete Dimensionen, Segmentmetadaten, Verweise und gegebenenfalls
gespeicherte Originalzitate werden geprüft. Identische doppelte Befunde werden
abgewiesen. Codepfad, Dimension, Thema und Analyse bestimmen die stabile
Themen-ID; eine bloß andere Auswahl von Beispielzitaten verändert das Thema
nicht. Sehr lange Definitionen werden nicht gekürzt.

Das bestehende SWOT-Schema bescheinigt keine wörtliche Äußerung einer
SWOT-Ableitung. Deshalb kennzeichnet der Adapter alle diese Themen konservativ
als `derived`, auch bei Stärken und Schwächen. Die spätere Matrix zählt
stützende und entgegenstehende Materialbasis. Sie behauptet nicht, Personen
hätten den analytischen SWOT-Befund selbst ausdrücklich formuliert.

## 6. Exakte Themenunion

`union_topics(material, results, *, topic_id, member_topic_ids, definition,
exact_union=False, inclusion="", exclusion="", label=None)` bildet eine
ausdrücklich erklärte ODER-Verknüpfung benannter Quellthemen. Dafür muss der
Aufrufer ausdrücklich `exact_union=True` setzen; die Vorgabe ist gesperrt. Die Quellen müssen
dieselbe Materialbasis besitzen, reproduzierbare Zählresultate liefern und
dieselbe Zuordnungsart (`kind`) verwenden. Unbekannte oder mehrdeutige Themen-IDs
und geänderte Zähler werden abgelehnt. Quellthemen werden nicht anhand ähnlicher
Bezeichnungen zusammengeführt.

Personen- und Einheitenmengen werden vereinigt, Quellzahlen nicht addiert.
Die Zahl der geprüften Matrixzellen bleibt dagegen die Summe der jeweils
erwarteten Thema-Einheit-Prüfungen; sie kann größer sein als der vereinigte
Einheitennenner. Die Union bleibt vorläufig, solange eine der erforderlichen
Quellzellen nicht entschieden ist, auch wenn jede Einheit bereits irgendwo
einen positiven Beleg hat.

Positionen beziehen sich auf mindestens eines der Quellthemen. Eine Gegenposition
zu einem Teilthema bedeutet nicht automatisch die logische Ablehnung eines
abstrakten Metathemas. Ein neues, engeres oder umformuliertes Metathema benötigt
eine eigene Zuordnungsmatrix. Der derzeitige Unionhelper akzeptiert Resultate
von `count_topics`; eine bereits aggregierte Union ist nicht automatisch ein
neues Quellresultat. Weitere Aggregation muss auf den benannten ursprünglichen
Themen beruhen oder einen gesonderten geprüften Vertrag erhalten.

## 7. Perspektiven und Identität

`analysis_perspectives` validiert die Modi `qualitative`, `frequency` und `both`.
Fehlende oder `null` gesetzte Abschnitte bleiben qualitativ. Methodische Eignung
ist von implementierter Verfügbarkeit getrennt: Nichtqualitative Modi werden
ohne ausdrücklich freigegebenen Adapter als „noch nicht integriert“ abgewiesen.
Die bestehenden Runner-/UI-Einstiege werden durch diesen Bibliothekskern nicht
automatisch erweitert.

Beide Perspektiven sollen je Modul dieselbe geprüfte Zuordnungsbasis verwenden
und getrennte Interpretationen liefern. Vor Themen- und Blockplanung bleiben
zusätzliche Matrixzellen und Modellanfragen unbekannt; eine logische gemeinsame
Basis ist keine Zusage über eine einzelne oder kostenlose Modellanfrage.
Mode-Metadaten, Material-, Themen- und Resultatfingerprints stehen für die
Einbindung in bestehende Lauf-/Checkpointidentitäten bereit. Die internen
Zuordnungs- und Interpretationsphasen verwenden die vorhandenen
Teil-Checkpoints; die vollständige Aufnahme der Moduswahl in die öffentlichen
Runner-/UI-Einstiege und Diagnoseprojektionen folgt noch. Kein Fingerprint
beweist die fachliche Richtigkeit einer Zuordnung.

## 8. Vollständige Matrix intern ausführen

`thematic_assignment.execute_assignments(material, topics, params, *, module, llm=None)`
plant jede erforderliche Thema-Einheit-Zelle des vorgegebenen Scopes.
Themenregister, Materialinhalt und ursprüngliche Materialidentität werden
gebunden. Die Originaltexte bleiben vollständig. Das Antwortbudget und die
Eingabegröße bestimmen die Modellblöcke; auch der mögliche Korrekturaufruf
wird vor der ersten Anfrage auf Kontextverträglichkeit geprüft.

Die Ausführung verwendet `bounded_batches`, `require_messages` und den
vorhandenen `analysis_work.analyze_items`-Koordinator mit dessen
Teil-Checkpoints. Es entsteht kein zusätzlicher Worker-Pool. Der aufrufende
Moduladapter darf diese Phase deshalb nicht wiederum innerhalb eines bereits
laufenden parallelen Einzelitems starten. Große Matrizen werden in
Modellanfrageblöcke geteilt; die gesamte Zuordnungsplanung ist dadurch nicht
automatisch speicherunbegrenzt skalierbar.

Die interne Fortschrittsmeldung verwendet die vorhandenen Phasen und
Arbeitseinheiten: Zuordnungsblöcke in `analysis`/`batches`,
Interpretationen in `synthesis`/`summaries`. Diese Zähler beschreiben
abgeschlossene Arbeitseinheiten, keinen Zeitanteil.

Jede Modellantwort muss genau die angeforderten Zellen einmal enthalten.
Nur `supported`, `opposed`, `both`, `no_evidence` und `unclear` sind
Modellentscheidungen. Doppelte JSON-Felder, fehlende oder zusätzliche Zellen,
fremde IDs und zusätzliche Zählerfelder werden abgewiesen. Bei einer ungültigen
Antwort gibt es höchstens einen erneuten Formatversuch auf Grundlage der
ursprünglichen vollständigen Eingabe. Auch aus Checkpoints geladene Blöcke
werden gegen ihre genauen erwarteten Zellen geprüft.

Ein technischer Fehler beendet die Phase; erfolgreiche Blöcke bleiben über
die bestehende Wiederaufnahmelogik verfügbar. Das ist etwas anderes als
`unclear`: Diese gültige inhaltliche Enthaltung lässt die technische
Ausführung zu Ende laufen, aber exakte Themenzahlen bleiben entsprechend
unbestimmt. Fehlende Antworten werden nicht als negative Evidenz fortgeschrieben.
Passt schon eine einzelne Originaleinheit mit ihrem Thema nicht in den
Kontext, folgt ein Kontextfehler statt einer stillen Textkürzung.

## 9. Zahlen interpretieren, ohne Zähler zu ersetzen

`thematic_interpretation.interpret_counts(material, counted, qualitative_by_topic,
params, *, module, llm=None)` prüft zunächst, ob die übergebene Zählung aus
derselben Materialbasis und Zuordnung reproduzierbar ist. Zu jedem Thema
muss genau ein qualitativer Ausgangstext vorhanden sein.

Eine Interpretationsanfrage enthält das betreffende Thema, diesen
unveränderten Ausgangstext, ein vollständiges Register der berechneten
Themenkennzahlen und die vorhandenen entgegenstehenden Originaleinheiten.
Das Register unterscheidet Scope, Abdeckung, Personen, Passagen und
Codierzeilen; ein Scope-Fingerprint kennzeichnet dieselbe Bezugsmenge.
Es enthält keine ungeprüften, vom Modell geschätzten Zähler. Sehr große
Register oder Gegenbelegsammlungen können die Kontextprüfung scheitern
lassen; sie werden derzeit nicht still gekürzt oder durch eine beliebige
Teilmenge ersetzt.

Das Modell liefert genau `topic_id`, `interpretation`, `counterpositions`
und `limitations`. Die Themen-ID muss passen und alle Textfelder müssen
nicht leer sein. Zusätzliche Kennzahlfelder werden nicht übernommen.
Die Antwort wird bei Bedarf einmal mit einer festen Korrekturanweisung
wiederholt und auch nach Wiederverwendung eines Checkpoints validiert.

Die berechneten Zahlen bleiben in einem getrennten Ergebnisobjekt. Diese
Trennung verhindert, dass ein vom Modell geliefertes Zahlenfeld die
deterministische Zählung ersetzt. Sie ist keine semantische Garantie:
Auch ein formal gültiger Interpretationstext kann Zahlen falsch beschreiben
oder unzutreffende Schlussfolgerungen ziehen. Gegenpositionen, Grenzen und
die danebenstehenden berechneten Werte müssen fachlich geprüft werden.

## 10. Interne Orchestrierung und getrennte Ausgaben

`thematic_execution.execute_perspective(module, mode, material, payload, params,
*, cluster_payload=None, llm=None)` unterstützt intern `clusterer`,
`summarizer` und `swot`:

1. Bei `qualitative` liefert die Funktion `None` und startet keine neue
   Materialprüfung oder Modellanfrage; der bestehende Standardpfad bleibt.
2. Der passende Adapter bereitet gemeinsame ungewichtete Themen vor.
   Cluster und Summarizer verwenden ihre vollständige Mitgliedschaft,
   SWOT führt die zusätzliche vollständige Matrixphase aus.
3. Der Kern zählt die gemeinsame Zuordnung einmal und führt anschließend
   häufigkeitsinformierte Interpretationen pro Thema aus.
4. `frequency` enthält die benannte häufigkeitsinformierte Ausgabe;
   `both` ergänzt die getrennte ursprüngliche qualitative Ausgabe. Beide
   Perspektiven teilen dieselbe Matrix. Es wird keine zweite
   Zuordnungsrunde nur für den qualitativen Vergleich gestartet.

Das Ergebnis enthält unter anderem `selected_mode`, `counting`,
`source_links`, `candidate_source_fingerprint`, `assignment_origin`,
`interpretations` und gegebenenfalls `unassigned_context`.
`perspective_markdown` stellt die berechneten Zähler/Nenner und
Verfügbarkeit getrennt von den Modellinterpretationen dar. Der vorhandene
qualitative Payload wird nicht überschrieben.

**Nachgelagerter Vertrag:** Die ursprünglichen strukturierten Befunde und
Quellen bleiben die gemeinsame ungewichtete Kandidatenbasis. Benannte
Interpretationen sind zusätzliche Ergebnisse dieses Moduls. Ein
nachgelagertes Modul darf gewichteten Text nicht still an die Stelle von
`summary`, `analyse` oder anderen bisherigen Quellfeldern setzen.
Dadurch wird eine bereits gewichtete Interpretation nicht als angeblich
ungewichtete Vergleichsbasis weitergereicht.

Diese interne Ausführung umgeht nicht die öffentliche Verfügbarkeitsprüfung.
Die Auswahl muss erst in den regulären Modulaufrufen, Konfigurations- und
Projektgrenzen, Promptansichten, Berichten sowie Aufwand-/Fortschrittsanzeigen
verdrahtet werden. Weitere geeignete Module und die neuen
Diagnose-/Wiederholungsprojektionen stehen ebenfalls noch aus. Erst ihre
getestete Integration darf neue Modi in der normalen Anwendung freischalten.
