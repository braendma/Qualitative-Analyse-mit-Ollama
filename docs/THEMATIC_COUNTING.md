# Thematische Zählung – Entwicklervertrag des gemeinsamen Kerns

**Entwicklungsstand S13a:** Materialbasis, Modusvalidierung, vorhandene
Clusterzuordnungen und deterministische Zählung sind als gemeinsame
Bibliotheksfunktionen implementiert. Das ist noch keine Freischaltung neuer
Analyseperspektiven in Oberfläche oder Workflow-CLI. Die generative
Themenzuordnung, häufigkeitsinformierte Interpretation und deren Einbindung
in die einzelnen Module folgen gesondert. Die bisherige qualitative
Arbeitsweise bleibt unverändert.

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

## 7. Perspektiven, Identität und noch offene Integration

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
spätere Einbindung in bestehende Lauf-/Checkpointidentitäten bereit. Kein
Fingerprint beweist die fachliche Richtigkeit einer Zuordnung.

Noch erforderlich sind Moduladapter, vollständige LLM-Zuordnung bei neu
gebildeten Themen, Interpretationsprompts, Berichte, Diagnoseprojektionen,
Aufwand-/Fortschrittsanzeige und UI-Auswahl. Erst ihre getestete Integration
darf die betreffende Perspektive zur normalen Nutzung freischalten.
