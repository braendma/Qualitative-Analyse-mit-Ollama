# Technischer Überblick zur Methode

**Öffentliche Software 0.5.0-beta.1 · 14. September 2026.**

Die Software unterstützt die Analyse bereits kodierter Textdaten. Forschungsfrage,
Materialauswahl, Kategoriensystem und Interpretation bleiben Aufgaben der
Forschenden. Nicht exportierte Textpassagen stehen dem Modell nicht automatisch
zur Verfügung. Ausführliche Einordnung und Literatur:
[Handbuch](HANDBUCH.md#aussagen-und-personen-zählen-methodische-einordnung).

## Ablauf

1. Codierte Segmente und Kategoriensystem als CSV/XLSX einlesen; Spalten und
   optionale Kodierregeln zuordnen.
2. Dokumentteile ausdrücklich Personen zuordnen und diese Zuordnung bestätigen.
   Codierzeilen und tatsächliche Passagen bleiben unterscheidbar.
3. Kontext, Modell, Module und Analyseperspektiven auswählen; Eingaben und
   Kontextbedarf prüfen; einen eigenen Ergebnislauf starten.
4. Originalbelege, Modellvorschläge und Diagnosehinweise im HTML-Bericht prüfen.
5. Menschliche Entscheidungen sichern und bei Bedarf einen neuen versionierten
   Folgelauf erstellen. Rückmeldung trainiert das Modell nicht.

## Funktionen

Die 15 Basismodule verbinden Clusterung, Zusammenfassungen, SWOT, fallbezogene und
vergleichende Analysen, Gesamtsynthese und Kodierungsprüfung. Fünf optionale
Diagnosen ergänzen sie:

- **Coverage und Blind Spots:** Materialverteilung und gespeicherte Belegreferenzen.
- **Information-Loss-Audit:** Referenzübergänge und manuelle Prüfpunkte zwischen
  Verdichtungsstufen.
- **Codebook-Diagnostik:** Hinweise zu Codeverwendung, Definitionen und gespeicherten
  Zuordnungsabweichungen.
- **Stabilität:** kontrollierte Wiederholungen ausgewählter Analysen.
- **Sensitivität:** ausdrücklich konfigurierte Parameter- oder Promptvarianten.

Die ersten drei Diagnosen benötigen keine zusätzlichen Modellanfragen;
Wiederholungen und Sensitivitätsvarianten verursachen zusätzlichen Aufwand.
[Verträge, Beispiele und Grenzen](DIAGNOSTICS.md).

Zehn geeignete Inhaltsmodule bieten unabhängig die Perspektiven **Qualitativ**,
**Häufigkeiten** und **Beide**. Qualitativ bleibt voreingestellt. Häufigkeiten
beruhen auf geprüften Clusterzuordnungen oder einer zusätzlichen Thema-Einheit-
Zuordnung. Python berechnet die Zahlen; die Modellzuordnung bleibt menschlich
zu prüfen. Einheiten, Personen, Nenner und unklare Zuordnungen werden getrennt
ausgewiesen. Beide Ansichten teilen je Modul dieselbe Zuordnungsbasis.
[Bedienung](HANDBUCH.md#analyseperspektiven-je-modul) ·
[Modulspezifische Zählgrenzen](THEMATIC_COUNTING.md).

## Aussagegrenzen und Transparenz

Häufigkeit ist keine Bedeutungsskala oder Populationsschätzung. Coding Agreement,
Coverage und stabile Wiederholungen beweisen keine inhaltliche Richtigkeit.
Prüfsummen dokumentieren Verarbeitung und Herkunft, keine qualitative Güte.
Synthetische Tests belegen technische Abläufe, keine empirische Analysequalität.
Die Forschenden prüfen Vorschläge gegen das Material und dokumentieren ihre
Entscheidungen. Gespeicherte Konfigurationen, Promptvorlagen, Zwischenprodukte
und Originalbelege unterstützen diese Arbeit.

Marcus Brändle und OpenAI Codex (KI-Mitautor): Codex unterstützte Softwareentwicklung
und Dokumentation. Die wissenschaftlichen Entscheidungen und Verantwortung für
die veröffentlichte Fassung liegen bei Marcus Brändle.

[Programm und Anleitung](../README.md) ·
[Version 0.5.0-beta.1 und Windows-Download](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/releases/tag/v0.5.0-beta.1)

[Technischer Kurzbericht als PDF](technical_report/technical_report.pdf) · [LaTeX-Quelle](technical_report/technical_report.tex) · [Lesefassung](technical_report/technical_report.md)
