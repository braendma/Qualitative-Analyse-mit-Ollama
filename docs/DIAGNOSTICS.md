# Wissenschaftliche Diagnosen – technische Grundlage

Entwicklungsstand: Die gemeinsame Quellenauswertung ist implementiert. Die fünf
Benutzermodule werden darauf aufbauend integriert und sind noch nicht als fertige
Funktionen verfügbar. Dieser Abschnitt beschreibt den überprüfbaren Datenvertrag.

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
