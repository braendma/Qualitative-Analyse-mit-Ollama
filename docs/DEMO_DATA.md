# Synthetische Beispieldaten

`maxqda_export.csv` und `Kategoriesystem.csv` enthalten vollständig erfundene Aussagen zu einem technischen Weiterbildungsangebot. Sie sind keine anonymisierten Originalinterviews und enthalten keine Auszüge aus einer realen Studie. Der Generator `tests/generate_demo.py` erstellt beide Dateien reproduzierbar.

Die 50 Codierzeilen umfassen 43 Passagen, sechs fiktive Personen und zwölf Codepfade mit einer bis vier Ebenen. Enthalten sind positive und negative Transfererfahrungen, gemischte Bewertungen, kontextabhängige Aussagen, gleiche Begriffe unter verschiedenen Pfaden sowie sechs absichtlich mehrfach codierte Passagen (darunter eine mit drei Codes). Zeilen-ID und Passage-ID sind getrennt; Personenkennungen dürfen nicht aus den externen Segment-IDs abgeleitet werden.

Die Beispielcodes sind illustrative menschliche Zuordnungen. Sie sind kein validierter Goldstandard für Modellqualität. Eine alternative Zuordnung bei den kontextsensitiven Fällen kann plausibel sein. Der Workflow muss auch bei Enthaltungen, abweichenden Zuordnungen und technischen Fehlern korrekt berichten.

Die öffentliche YAML verwendet `label_mode: multi_label`. Jede Passage wird unabhängig mit einer Codemenge vorhergesagt. Die Kennzahlen vergleichen Mengen je Passage und weisen fehlende sowie zusätzliche Codes aus; siehe [EXTENSIONS.md](EXTENSIONS.md). Cohen's Kappa bleibt deaktiviert. Für Single-Label-Analysen sind eine ausdrücklich bestätigte unabhängige Analyseeinheit und eindeutige Passage-IDs erforderlich.

Produktive Daten gehören in ein separates privates Verzeichnis. Cloud-Tests verwenden ausschließlich diese synthetischen Dateien; die ausgelieferte Standardkonfiguration verwendet lokales Ollama.
