# Wissenschaftliche Diagnosen – technische Grundlage

Entwicklungsstand: Die gemeinsame Quellenauswertung und der Coverage-Kern mit CLI
sind implementiert. Die Auswahl in der Oberfläche und die weiteren Diagnosemodule
werden darauf aufbauend integriert. Dieser Abschnitt beschreibt den überprüfbaren
Datenvertrag und die bereits nutzbare technische Schnittstelle.

## Referenzen eindeutig unterscheiden

`diagnostic_sources.py` liest die JSON-Ausgabe aus dem vorhandenen Outputvertrag
jedes Moduls. Ein `--out-json`-Argument hat Vorrang vor Hilfsdateien wie dem
Textmapping. Alternative Dateinamen werden unterstützt. Die Datei muss innerhalb
des Laufordners liegen, das Modul im Manifest abgeschlossen sein und die SHA-256-
Prüfsumme stimmen. Fehlende, deaktivierte, veränderte und nicht verifizierte Quellen
erscheinen mit eigenem Status; sie gelten nicht als erfolgreiche leere Analysen.

Die Projektion trennt vier Arten von Verweisen:

| `scope` | Bedeutung | Grenze |
|---|---|---|
| `direct` | Vom jeweiligen Befund ausgewählte Segment-IDs, ggf. über referenzierte Meta-SWOT-Befunde aufgelöst | Beweist keine semantische Richtigkeit |
| `input_association` | Segmente eines Clusters oder Eingaben seiner Zusammenfassung | Kein Nachweis, dass jede Textnuance in der Zusammenfassung vorkommt |
| `source_group` | Im gespeicherten Synthesegraphen zu einer zitierten Quellengruppe gehörende Textstellen | Kein bestätigter Beleg für jede einzelne Syntheseaussage |
| `person_reference` | Genannte Personen ohne exakte Segmentzuordnung | Daraus wird keine Segmentabdeckung abgeleitet |

Personenregister, vollständige `segment_metadata`, unbenutzte `finding_registry`-
Einträge und zur Anzeige ergänzte Zitatkopien werden nicht als zusätzliche
Evidenzauswahl gezählt. Ambivalenzen und Relationen behalten beide Belegseiten;
Gegenbelege bleiben als solche erkennbar. Nicht auflösbare Syntheseknoten und
unbekannte Personen-/Segment-IDs werden ausgewiesen. Betroffene Einträge sind von
quantitativen Vergleichen auszuschließen, nicht als Nullbefund zu behandeln.

Ein Snapshot (`schema_version: 1`) enthält `inputs`, einen `input_fingerprint` und
`stages`. Eingaben führen ID, bestätigte Person, Code, optionale Passage-ID,
Wortanzahl (Trennung an Leerraum) und Texthash. Originaltexte werden nicht noch
einmal kopiert; analytische Texte und Kennungen können dennoch sensibel sein.
Die bestehenden Ergebnisdateien und Eingaben bleiben unverändert.

Der Datei-basierte Aufruf prüft zusätzlich die Prüfsummen der Eingabe und der
Konfiguration gegen das ursprüngliche Manifest. Identische Segment-IDs allein
genügen nicht: Auch veränderte Texte mit beibehaltenen IDs werden abgewiesen.

## Aussagegrenzen

Die freie Gesamtzusammenfassung hat keine exakten Segmentverweise. Bei nicht
hierarchischen Synthesen können nur Modulnamen als Quellen vorliegen; ohne
gespeicherte Segmentzuordnung wird keine solche erfunden. Ein späterer Bericht
kann Quellen anzeigen, obwohl eine einzelne Aussage keine direkte Zuordnung hat.
Ein Referenzverlust ist daher ein Anlass zur Originalprüfung, kein automatisch
bewiesener Bedeutungsverlust. Es werden keine zusätzlichen Modelle aufgerufen.

## Tests

`python -m unittest discover -s tests -p 'test_diagnostic_sources.py'` prüft
Registerabgrenzung, Quellengruppen, beide Ambivalenzseiten, unbekannte IDs,
unveränderte Eingaben, alternative Dateinamen, Hash-/Abschlussnachweise und
fehlende/unerlaubte Dateien anhand ausschließlich künstlicher Daten. Zusätzlich
prüft `test_full_pipeline.py` die Adapter gegen die tatsächlich geschriebenen
Ergebnisse aller elf analytischen Stufen, in Single- und Multi-Label-Läufen mit
Fehler/Wiederaufnahme sowie hierarchischer Synthese.

## Coverage und Blind Spots

Motivation: Sichtbar machen, welche Personen, Kategorien und exportierten
Textstellen in späteren analytischen Ergebnissen referenziert werden. Der Kern
`coverage_core.py` benötigt keine zusätzlichen Modellaufrufe. Aufwand der Diagnose:
**NIEDRIG**, für iterative Arbeit geeignet. Noch fehlende vorgelagerte Analysen
können ihrerseits erheblichen Modellaufwand verursachen; dieser gehört nicht zur
deterministischen Diagnose.

Der Bericht trennt die vier Referenzarten und führt je verfügbarer Stufe
Personenanteile, Kategorien bis zur vierten Ebene und nicht referenzierte
Codierzeilen auf. Das JSON enthält zusätzlich Wortanteile, technische Quellen mit
Prüfsummen und den jeweiligen Auswertbarkeitsstatus.

### Nenner und Interpretation

- **Personenanteile:** Eindeutige explizite Passage-IDs werden genau einmal gezählt.
  Eine wiederholte Passage muss dieselbe Person und denselben Originaltext besitzen.
  Ohne Passage-ID bleibt jede Codierzeile eine Materialeinheit; gleiche Texte allein
  werden nicht zusammengelegt. Gemischte Daten sind ausdrücklich so gekennzeichnet.
- **Kategorieanteile:** Codierzeilen auf derselben Hierarchieebene bilden den Nenner.
  Ein Code ohne zweite Ebene wird auf Ebene 2 nicht künstlich verlängert.
- **Wortanteile:** Wörter der Materialeinheiten, an Leerraum getrennt; mehrfach
  codierte explizite Passagen zählen einmal. Das sind keine Interviewdauer- oder
  Volltranskriptanteile, da nur die exportierten codierten Stellen vorliegen.
- **Evidenzauswahl:** Jede ID zählt innerhalb derselben Stufe und Referenzart einmal,
  auch wenn mehrere Befunde darauf verweisen. Die Anzahl der Referenzeinträge ist
  keine Zahl unabhängiger Aussagen (z. B. zwei Seiten einer Ambivalenz).

Beispiel: P1 hat eine Passage mit zwei Codes, P2 eine Passage mit einem Code.
Beide Personen stellen 50 % der zwei Materialeinheiten. Wird nur die Passage von
P1 referenziert, stellt P1 100 % der referenzierten Einheiten. Die Zahl der
Codierzeilen bleibt dagegen drei. Das Programm entscheidet nicht, welche Verteilung
methodisch angemessen ist. Minderheiten- und Randpositionen fachlich am Original
prüfen; eine seltene Person oder Kategorie ist nicht automatisch eine solche Position.

Eine erfolgreich ausgewertete leere Befundliste ergibt eine Abdeckung von 0 %,
aber keinen berechenbaren Anteil an einer leeren Evidenzauswahl. Fehlende Quellen,
ungültige Verweise oder Quellennamen ohne gespeicherte Segmentzuordnung ergeben
„nicht bestimmbar“. Gruppenmaterial einer Synthese ist kein bestätigter
Direktbeleg. Coverage ist **kein Maß qualitativer Güte**.

### Technischer Aufruf vor der UI-Integration

Den vorhandenen Lauf zuerst unverändert lassen. Ein separates Ausgabeverzeichnis
für diese Nachprüfung verwenden. Vorhandene Ziele, Eingaben und gespeicherte
Ergebnisse werden beim separaten Export als Ausgabepfad abgewiesen:

```bash
python src/coverage_analysis.py --config /pfad/zum/lauf/config_snapshot.yaml --input-csv /pfad/zur/unveraenderten/eingabe.csv --run-dir /pfad/zum/lauf --out-json /pfad/zur/diagnose/coverage.json --out-md /pfad/zur/diagnose/coverage.md
```

Alle Argumente verwenden vorhandene Pfadkonventionen. `--config` und `--input-csv`
sind erforderlich. `--run-dir` ist standardmäßig das Arbeitsverzeichnis;
`--out-json` und `--out-md` heißen standardmäßig `coverage.json` und `coverage.md`.
Zur Integration im bestehenden Runner ist eine optionale Moduldefinition möglich;
die gemeinsame Modulauswahl wird separat ergänzt. Die Stufe nach den gewünschten
analytischen Quellen einordnen. Nicht abgeschlossene Module werden nicht nachträglich
berechnet, sondern als nicht verfügbar ausgewiesen.

Die Diagnose misst die analytischen Referenzen, nicht das fertige HTML-Dokument.
Der HTML-Export entsteht erst danach und muss im vollständigen Integrationstest
gesondert geprüft werden. Berichte, Kennungen, analytische Texte und Quellenpfade
können sensibel sein und bleiben in der privaten Projektablage.
