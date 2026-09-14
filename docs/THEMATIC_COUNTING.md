# Thematische Zählung – Entwicklervertrag des gemeinsamen Kerns

**Entwicklungsstand S13h2:** Clusteranalyse (`clusterer`), Clusterzusammenfassungen
(`summarizer`), SWOT (`swot`), Meta-SWOT (`meta_swot`), Personenanalyse
(`person_analysis`), Personenvergleich (`person_comparison`), Kontrastanalyse
(`contrast_analysis`), Zusammenhangsanalyse (`relation_analysis`) und Ambivalenzanalyse (`ambiguity_analysis`) sind über ihre regulären Module in
Workflow-CLI und Oberfläche mit den Perspektiven `qualitative`, `frequency` und
`both` verbunden. Die Auswahl gilt unabhängig je Modul; fehlende Einstellungen
bleiben qualitativ. Das weitere geeignete Modul
Gesamtsynthese hat noch keine
zusätzlichen Perspektiven. Dies beschreibt den aktuellen Entwicklungsstand, keine neue
veröffentlichte Version. Der gemeinsame Kern verbindet vollständige
Themenzuordnung, deterministische Zählung und häufigkeitsinformierte Interpretation.

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
Die zentrale Grenze `thematic_pipeline` gibt nur die neun integrierten
Standardmodule frei. Ein eigenes Skript mit derselben Modul-ID erbt keine
zusätzliche Verfügbarkeit. Die Oberfläche liest diese Freigabe vom Server.
Ungültige gespeicherte Modi werden angezeigt und abgewiesen, auch bei gerade
nicht ausgewählten Modulen; sie werden nicht still entfernt.

Beide Perspektiven verwenden je Modul dieselbe geprüfte Zuordnungsbasis
und liefern getrennte Interpretationen. Vor Themen- und Blockplanung bleiben
zusätzliche Matrixzellen und Modellanfragen unbekannt; eine logische gemeinsame
Basis ist keine Zusage über eine einzelne oder kostenlose Modellanfrage.
Die gespeicherte Konfiguration enthält die Moduswahl und bindet sie damit
an den bestehenden Lauf-Fingerprint. Material-, Themen- und Resultatidentität
werden zusätzlich geprüft; Zuordnungs- und Interpretationsphasen verwenden
die vorhandenen Teil-Checkpoints. Verifizierte Diagnoseprojektionen trennen
thematische Kennzahlen von benannten Interpretationstexten. Kein Fingerprint
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
Themenkennzahlen im ausdrücklich benannten Vergleichsraum und die vorhandenen
entgegenstehenden Originaleinheiten. Bei Cluster, Zusammenfassungen, SWOT,
Meta-SWOT und Personenvergleich enthält `comparison_basis: all_fixed_topics` sämtliche festgelegten
gezählten Modulthemen. Beim Personenvergleich sind dies ausschließlich gemeinsame Muster. Bei Personen- und Ambivalenzanalyse enthält
`comparison_basis: same_person_scope` dagegen sämtliche Themen desselben
vollständigen Einzelfall-Scopes, einschließlich aller A-/B-Seiten dieses Falles.
Themen anderer Personen gehören nicht zu diesem Vergleichsraum. Das ist eine
fachliche Scope-Grenze, keine Kürzung auf eine beliebige Auswahl und kein
vorweggenommener Personenvergleich. Alle Einzelfälle werden weiterhin ausgewertet.

`module_topic_count` benennt die Gesamtzahl der Modulthemen,
`comparison_topic_count` die Zahl im jeweiligen Anfrageregister. Die vollständigen
Modulergebnisse behalten sämtliche Themen und Zähler. Das Register unterscheidet
Scope, Abdeckung, Personen, Passagen und Codierzeilen; ein Scope-Fingerprint
kennzeichnet dieselbe Bezugsmenge.
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

## 10. Orchestrierung, Anwendungseinstiege und getrennte Ausgaben

`thematic_execution.execute_perspective` erhält Modul, Modus, Material,
Originalergebnis, Modellparameter und die tatsächlich benötigten geprüften Vorstufen. Die Funktion
unterstützt `clusterer`, `summarizer`, `swot`, `meta_swot`, `person_analysis`,
`person_comparison`, `contrast_analysis`, `relation_analysis` und `ambiguity_analysis`:

1. Bei `qualitative` liefert die Funktion `None` und startet keine neue
   Materialprüfung oder Modellanfrage; der bestehende Standardpfad bleibt.
2. Der passende Adapter bereitet gemeinsame ungewichtete Themen vor.
   Cluster und Summarizer verwenden ihre vollständige Mitgliedschaft,
   SWOT, Meta-SWOT, Personenanalyse, Personenvergleich, Kontrastanalyse, Zusammenhangsanalyse und Ambivalenzanalyse führen eine zusätzliche
   vollständige Matrixphase in ihrem ausdrücklich definierten Scope aus.
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

Kontrastanalyse und Gesamtsynthese schließen deshalb gespeicherte
`analysis_perspective`-Erweiterungen ihrer Eingaben ausdrücklich aus ihrer
Kandidaten- und Verdichtungsbasis aus. Die vollständigen Quelldateien und ihre
zusätzlichen Ergebnisse bleiben unverändert gespeichert. Die ausführbaren
Vergleichstests prüfen identische ursprüngliche Anfrageinhalte mit und ohne
solche Erweiterungen; diese erzeugen keine zusätzliche Kontextverdichtung.

`thematic_pipeline.prepare` prüft vor dem bisherigen Modulablauf die bestätigte
Materialbasis. Für abhängige Module werden Cluster, Originaltext-Zuordnung und
gegebenenfalls Clusterzusammenfassungen gegen Material und im Runner gegen die
deklarierten, abgeschlossenen Artefakte geprüft. `finish` ergänzt das Ergebnis
unter `analysis_perspective` und den Markdown-Bericht, ohne die ursprünglichen
Quellfelder zu ersetzen. Veränderte Eingaben oder Vorstufen werden vor und nach
der zusätzlichen Ausführung abgewiesen. Der HTML-Gesamtbericht übernimmt den
Modulbericht; vollständige strukturierte Ergebnisse bleiben in der separaten
JSON-Datei des Moduls.

Die Promptansicht ergänzt bei gespeichertem `frequency`/`both` die festen
Systemanweisungen für Häufigkeitsinterpretation und bei SWOT, Meta-SWOT,
Personenanalyse, Personenvergleich, Kontrastanalyse, Zusammenhangsanalyse und Ambivalenzanalyse für vollständige Themenzuordnung.
Sie beschreibt die dynamischen Eingaben, zeigt aber weder das vollständige
Anfrageprotokoll noch automatisch Interviewmaterial. Stabilitäts-/Sensitivitätsansichten
berücksichtigen die entsprechenden Zielmodule. Weitere Moduladapter bleiben
nicht verfügbar; eine Eignungskennzeichnung ist keine Ausführungsfreigabe.

Stabilität und Sensitivität vergleichen die benannten Interpretationen und
berechneten Zahlen zusätzlich zur gemeinsamen Kandidatenbasis. Die Zähler werden
dafür aus den Originaleinheiten erneut geprüft. Ihre vollständigen Scopes oder
Zuordnungsmatrizen werden nicht als neu ausgewählte Zitate behandelt. Coverage
misst weiterhin die vorhandenen vier Referenzarten. Der Information-Loss-Audit
weist thematische Ergebnisrecords separat aus und nimmt sie nicht in seine
Referenz- und Wortlistenübergänge auf; fehlende direkte Segmentlinks solcher
Zähler sind kein festgestellter Belegverlust. Damit ist die neue Modellprosa
nicht automatisch einer eigenständigen semantischen Verlustprüfung unterzogen.

Bedienung, sichere Fehlerbehebung und Beispiele:
[Analyseperspektiven im Handbuch](HANDBUCH.md#analyseperspektiven-je-modul).
YAML-Vertrag und CLI-Voraussetzungen:
[Konfigurationsreferenz](CONFIGURATION.md#analyseperspektiven-je-modul).

## 11. Meta-SWOT und Einzelfälle: Adapter und Quellenverträge

Die integrierten Module `meta_swot`, `person_analysis` und `ambiguity_analysis`
verwenden die bestehenden Adapter und dieselbe zentrale Ausführung wie die
ersten drei Module. CLI-Quellenprüfung, Diagnoseprojektion und serverseitige
Verfügbarkeitsanzeige gehören zu ihrer Anwendungsgrenze. Die qualitative
Vorgabe bleibt unverändert; erst eine ausdrückliche Moduswahl startet Zusatzarbeit.

Meta-SWOT erhält mit `swot_payload` die ursprüngliche SWOT-Vorstufe. Der Adapter
baut deren Befundregister erneut auf und prüft alle Meta-Verweise einschließlich
Quellbereichen und Originalbelegen. Jedes neu verdichtete Meta-Thema wird gegen
das gesamte ursprüngliche SWOT-Material geprüft. Bereits ermittelte Häufigkeiten
werden weder addiert noch durch eine unterstellte Themenunion übernommen.
Eine vollständige Zuordnung zu gefundenen Themen beweist nicht, dass die
Kandidatenphase alle möglichen, insbesondere blockübergreifenden Themen entdeckt hat.

Die Personenanalyse prüft ihre vollständige Personen- und Segmentmenge gegen
das bestätigte Material. Die vier strukturierten Befundabschnitte liefern
analytisch abgeleitete Themen; freie Gesamtverdichtungen bleiben Kontext.
Ein Thema wird gegen alle Originaleinheiten dieser einen Person geprüft.
Mehrere Dokumentteile bleiben ein Fall, mehrfach codierte identische Passagen
eine Materialeinheit. Ein Personennenner von eins bezeichnet einen Einzelfall,
keine Mehrheit der Untersuchungsgruppe. Gleichnamige Themen verschiedener Fälle
dürfen deshalb nicht ohne eine gemeinsame Definition zusammengezählt werden.

Die Ambivalenzanalyse benötigt zusätzlich die originale Personenanalyse als
`person_payload`. Jedes gültige Paar erzeugt zwei unabhängige Seitenthemen A und B
mit gemeinsamer Paaridentität und jeweils dem vollständigen Einzelfall als
Bezugsmenge. B ist nicht automatisch die logische Negation von A. Eine Passage
kann beide Seiten stützen; Seitenzahlen werden nicht voneinander abgezogen.
`both` innerhalb einer Seitenthemenzuordnung bedeutet Stützung und Widerspruch
zu dieser Seite, nicht die gemeinsame Nennung der beiden Seiten. Der Bericht
macht diese Unterscheidung ausdrücklich sichtbar. Freie Gesamteinordnungen
erhalten keine erfundenen Häufigkeiten. Die bestehende Kandidatennormalisierung
verwirft Paare mit identischen A-/B-Belegmengen. Eine neue vollständige Matrix
zu den verbleibenden Seitenthemen hebt diese Entdeckungsgrenze nicht auf.

Alle drei Adapter verwenden dieselbe flache Zuordnungs-, Zähl- und
Interpretationsphase sowie vorhandene Teil-Checkpoints. Ein technischer Abbruch
wird nicht als inhaltlich unklare Antwort umgedeutet. Die ursprünglichen
qualitativen Kandidaten bleiben getrennt von den zusätzlichen Interpretationen;
bereits vorhandene `analysis_perspective`-Erweiterungen einer Vorstufe verändern
ihre ungewichtete Kandidatenbasis nicht.


### Zusätzliche Prüfungen an der Anwendungsgrenze

Meta-SWOT benötigt das vollständig deklarierte originale SWOT-Artefakt.
Personenanalyse benötigt Cluster, exakte Originaltext-Zuordnung und passende
Clusterzusammenfassungen; Ambivalenz benötigt die vollständige Personenanalyse
und Originaltext-Zuordnung. Ein CSV-Override muss zum bestätigten Material
passen. Fehlende Runnernachweise führen nicht in einen ungeprüften
Standalone-Fallback. Dateihashes der Eingaben und Vorstufen bleiben vor und nach
der zusätzlichen Ausführung verbindlich. Die von gewichteten Zusatzfeldern
bereinigte semantische Kandidatenidentität ersetzt keinen Dateinachweis.

Diagnoseprojektionen dürfen Meta-/Ambivalenz-Vorstufen nicht aus ausgewählten
Belegen oder Teilregistern erfinden. Sie verwenden die vollständig geprüften
Quellpayloads des jeweiligen Laufs, auch wenn die Module in anderer Reihenfolge
aufgelistet sind. Fehlt eine notwendige Quelle oder ist sie ungültig, ist die
abhängige Projektion nicht auswertbar. Die Zuordnungsmatrix wird weiterhin nicht
zur angeblich ausgewählten Evidenz. Wiederholungsvergleiche müssen dieselben
Quellenregeln innerhalb des jeweiligen Kindlaufs anwenden.


## 12. Personenvergleich: gemeinsame Muster und qualitativer Rest

`thematic_comparison_adapter.build_person_comparison_topics(material, payload,
source_person_payload)` validiert die vollständige Personenanalyse und die
exakte Liste `source_persons`. `input_reduction.source_sha256` muss auf die
ursprünglichen Personenanalysen zeigen. Bei tatsächlicher Verdichtung werden
auch jede Personenquelle, Summary, Personenkennung und gespeicherte Bytegröße
geprüft. Zeitreferenzen allein ersetzen diese Nachweise und die Dateihashes der
Anwendungsgrenze nicht. Auch gewichtete Vorstufen werden anhand ihrer gemeinsamen
ungewichteten Originalfelder geprüft.

Nur `gemeinsame_muster[]` erzeugt Themen aus vollständigem Thema und Verdichtung.
`kind=derived` beschreibt Unterstützung einer analytischen Aussage, keine
automatisch bestätigte wörtliche Nennung. Der Scope enthält alle Originaleinheiten
aller bestätigten Vergleichspersonen. `personen` wird als Herkunftsreferenz
validiert, aber weder als vollständige Mitgliedschaft noch als positive
Zuordnung übernommen. Jedes Muster erhält eine vollständige neue Matrix; bereits
bekannte Personenhäufigkeiten anderer Module werden nicht addiert.

`zentrale_unterschiede`, `typen`, `nicht_zugeordnete_personen`, `gesamtvergleich`
und der Reduktionshinweis bleiben in `unassigned_context`. Auch ihre Personen-
referenzen werden geprüft. Die Typenliste darf überlappen und unvollständig sein;
das Ergebnis behauptet keine Typenpartition oder neue Typen-/Aussagenhäufigkeit.
Der unveränderte qualitative Originalbericht bleibt erhalten; der zusätzliche
Perspektivabschnitt benennt ausdrücklich, welche Abschnitte keine eigene Zählung
besitzen. Keine gemeinsamen Muster bedeutet keine berechenbaren gemeinsamen
Musterthemen, nicht automatisch fehlende Unterschiede oder Typen.

`comparison_basis=all_fixed_topics` enthält hier alle gezählten gemeinsamen
Muster über derselben globalen Originalbasis. Das ist vom `same_person_scope`
der Personen- und Ambivalenzanalyse zu unterscheiden. `frequency`/`both` teilen
wie bisher eine Zuordnungsmatrix. Neue Modellzuordnungen können ursprüngliche
Mehrheitsformulierungen einschränken; die Bezeichnung als gemeinsames Muster
beweist keine Mehrheit. Die Matrix ergänzt die Prüfung vorhandener Kandidaten
und entdeckt keine zuvor in der Verdichtung übersehenen Muster nachträglich.


## 13. Kontrast: globale Muster und gebundene Einzelgegenfälle

Der Kontrastadapter erhält Material, Originalkontrast, vollständige originale
Personenanalyse und originalen Personenvergleich. Deren Personenbestand,
Referenzen und vorhandene Reduktionsnachweise werden geprüft. Zusätzliche
`analysis_perspective`-Ansichten ändern die gemeinsame Kandidatenbasis nicht;
die Anwendung prüft trotzdem die vollständigen Dateihashes.

Vollständige `dominante_muster` werden als `derived` Themen über alle
Originaleinheiten geprüft. `getragen_von` setzt keine Matrixzellen vorab.
Ein Gegenfall wird nur bei eindeutigem exaktem Bezug auf einen vollständig
definierten lokalen Mustertitel zum eigenen Thema über das gesamte Material
seiner Person. Seine Definition bewahrt die Abweichung und den Musterkontext.
Identische vollständige Muster aus mehreren Blöcken ergeben ein Thema mit
erhaltener Herkunft; gleiche Titel mit verschiedenen Definitionen sind
mehrdeutig. Es werden keine Batch-IDs oder unscharfen Verknüpfungen erfunden.

Unaufgelöste oder mehrdeutige Freitextbezüge und unvollständige Kandidaten bleiben
mit konkretem Grund in `unassigned_context`. Typenspannungen, Relativierungen und
Gesamteinordnung bleiben ebenfalls qualitativ. Diese Gründe erscheinen im
Bericht; vollständige Strukturen bleiben zusätzlich im Modul-JSON. Ungezählt
bedeutet weder `no_evidence` noch null Nennungen. Fremde Personen, beschädigte
Vorstufen oder falsche Reduktionsnachweise sind harte Validierungsfehler.

**Fester gemischter Vergleichsvertrag:** `source_links` unterscheidet
`scope_kind: global_pattern` und `individual_countercase`; Fallthemen nennen
`person` und `pattern_topic_id`. Rollen werden ausdrücklich geprüft und nicht
aus einem Personennenner von eins erraten. Der globale Scope muss sämtliche
Originaleinheiten umfassen, der Fall-Scope sämtliche Einheiten dieser Person,
das referenzierte Musterthema muss ein gültiges globales Thema sein.

- Modulbasis: `comparison_basis: contrast_scoped`.
- Globales Muster: `comparison_scope: global_patterns`, Kennzahlenregister aller
  globalen Muster. `reference_context` enthält vollständig alle diesem Muster
  eindeutig zugeordneten Gegenfälle als qualitative Bezüge mit Person und
  Topic-ID; deren Einzelfallzähler werden nicht ins globale Register gemischt.
- Gegenfall: `comparison_scope: same_person_countercases`, Kennzahlenregister
  aller gezählten Gegenfallthemen derselben Person, auch zu anderen Mustern.
  `reference_context` enthält das konkret gebundene globale Muster mit seiner
  vollständigen Definition. Keine Gegenfallregister anderer Personen und kein
  scheinbar gleichberechtigter globaler Nenner im Fallregister.

Das Kontrastvergleichsregister enthält die vollständige Definition jedes Themas, damit auch identische Titel unterscheidbar bleiben; auch dieses Register wird niemals still gekürzt.

`comparison_topic_count` zählt nur das Kennzahlenregister, `module_topic_count`
alle gezählten Modulthemen. Der zusätzliche Bezugskontext ist keine weitere
Zählbasis. Alle Muster/Fälle bleiben im Gesamtergebnis erhalten; Gegenfälle
werden weder von globalen Zählern abgezogen noch automatisch als logische
Negation behandelt. Auch eine Einpersonenstudie behält die zwei verschiedenen
Rollen. Register und qualitative Bezugstexte bleiben vollständig; bei zu großem
Kontext erfolgt keine stille Kürzung. Matrix und häufigkeitsinformierte
Interpretation verwenden den bestehenden gemeinsamen Executor. `both` teilt
diese Matrix, löst keine zweite Zählung aus.


## 14. Zusammenhangsanalyse: verifizierte Auswahl und getrennte Zählungen

`relation_analysis` ist in CLI, Runner und Oberfläche für `frequency`/`both`
freigegeben. Der qualitative Default bleibt unverändert. `prepare` benötigt
bestätigtes Originalmaterial, vollständige Cluster, Summary und Textzuordnung;
der Core erhält das geprüfte `material`. Auswahlprovenienz entsteht vor den
Modellaufrufen und wird nach dem Core erneut geprüft. Alte Ergebnisse ohne
`selection_provenance` bleiben lesbar, reichen aber nicht als Grundlage einer
neuen vollständigen Häufigkeitsperspektive: dafür einen neuen Lauf erstellen.

`relation_selection` speichert die tatsächlichen Parameter, vollständige
Rangfolge der zulässigen Codepaare, Seiten-IDs und Personen sowie Fingerprints
der Originalquellen und Paarinputs vor Kontextverdichtung. `0` bei `max_pairs`
bedeutet alle zulässigen Paare mit mindestens einer gemeinsamen Person. Das
ist keine vollständige Prüfung aller denkbaren semantischen Beziehungen.
Replay prüft Statistiken, Pfade, ausgewählte Originalzitate, Personenbezug und
Kontextverdichtungen. Namen allein bestimmen keine Clusteridentität;
Definition und vollständige Segmentmenge gehören ebenfalls dazu.

`thematic_relation_adapter.build_relation_topics(material, payload, clusters,
summary)` übernimmt nur vollständig beschriebene Relationskandidaten mit
innerhalb einer Person belegter Herkunft. Jedes Thema erhält alle Original-
einheiten aller bestätigten Personen als Scope. Bloßes A/B-Kovorkommen ist
kein semantischer Beleg. Die Einzelstellenmatrix erkennt nicht notwendig eine
Relation, die erst aus mehreren getrennten Aussagen rekonstruiert werden
müsste. Personenübergreifende Gegenüberstellungen, unvollständige Aussagen und
Gesamteinordnung bleiben ausdrücklich ungezählter Kontext. `both` bedeutet
Stützung und Widerspruch zur selben Relationsthese, nicht beide Codes gemeinsam.
Die A/B-Pfadordnung begründet keine Wirkungsrichtung oder Kausalität.

Das vollständige Interpretationsregister enthält jede Relationsdefinition,
auch wenn Titel identisch sind. Das Modell erhält die semantischen Themen-
kennzahlen; Codeüberschneidungen sind keine stillen Gewichte dieser Aussagen.
`relation_cooccurrence.count_code_path_cooccurrences(material)` berechnet
zusätzlich alle bestehenden Codepaare, einschließlich Nullüberschneidungen.
Die getrennte Ausgabe steht unter `analysis_perspective.code_cooccurrence`.
Personen, gleiche ausdrücklich identifizierte Passagen und Codierzeilen bleiben
verschieden. Bei gemischter Passagebasis sind exakte Passagezahlen und Anteile
`null`; bekannte Passagen werden separat als beobachtete Untergrenze gezeigt.
Der Nenner ist der vollständige bestätigte Exportumfang, nicht die Beispielauswahl.

Diagnosen reproduzieren Themen und Codeüberschneidungen mit denselben tatsächlichen
Cluster-/Summaryvorstufen. Separate `code_cooccurrence_counts`-Records enthalten
nur Kennzahlen, Scope und Codepfade, keine ausgewählten Beleg-IDs. Wiederholungen
benötigen die beiden eigenen geprüften Kindlaufquellen. In der ursprünglichen
Gesamtsynthese-Kandidatenprojektion werden `selection_provenance`, zusätzliche
`code_cooccurrence`-Felder und `analysis_perspective` ausgeschlossen: technische
Register ersetzen keine qualitativen Ausgangsbefunde.
