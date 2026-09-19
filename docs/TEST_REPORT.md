# Bugfix-Prüfstand für 0.5.0-beta.2 · 19. September 2026

**Quellenbindung:** Der folgende Nachweis betrifft den Bugfix-Code vor der abschließenden Versions-/Dokumentationsänderung. Das mitgelieferte Buildmanifest nennt den exakten Quellcommit des jeweiligen Windows-Pakets. Dessen abschließende Regression und Paketprüfungen sind im [Windows-Buildverlauf](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/actions/workflows/windows-package.yml) an diesem Commit nachvollziehbar; die [Release-Seite](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/releases/tag/v0.5.0-beta.2) nennt den freigegebenen Download und seine Prüfsumme. Ein grüner Test eines früheren Commits ersetzt diese Paketprüfung nicht.

Auf `bec08197ba4e885fe6604eb10dd233839af7eddc` bestand der [Windows-Paketlauf](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/actions/runs/35456518555) 951 Python-Tests, 84 JavaScript-Tests sowie Paketidentität, normale und lange Ergebnisordner und den modellfreien Paketworkflow. Das dabei gebaute Paket trägt noch die Versionsnummer beta.1 und wird nicht als beta.2 veröffentlicht.

Der [native Mac-Test](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/actions/runs/35456518561/job/105932656199) bestand den gezielten Pause-/Resume-/Cleanup-Zyklus sowie 951 Python-Tests (18 vorgesehene plattformabhängige Skips), 69 JavaScript-Tests und den HTTP-Start. Damit ist der konkret diagnostizierte EPERM-Fehler geprüft; eine native Mac-Distribution oder ein vollständiger Modelllauf auf physischer Mac-Hardware ist daraus nicht abzuleiten.

Die Windows-Sourceprüfung desselben Desktop-Laufs bestand ebenfalls 951 Python-Tests, 69 JavaScript-Tests und den HTTP-Start. Damit sind beide Installationswege zusätzlich zum gebündelten Windows-Paket geprüft.

Lokal bestanden 43 gezielte App-/Parallelitäts-/Prozesstests und 69 JavaScript-Tests. Zusätzlich wurden die veröffentlichte Windows-EXE und die gepatchte Python-Oberfläche per Browser-Klick geprüft. Mit synthetischen Daten startete Granite 4.2:8b bei 32.768 Tokens und zwei Slots. Im zweiten UI-Lauf bearbeiteten beide Slots tatsächlich gleichzeitig zwei Kategorien; beide Antworten waren vollständig. Eine absichtlich zu hohe Einstellung wurde verständlich abgewiesen und ließ sich in der Oberfläche korrigieren. Alle Testprozesse wurden kontrolliert beendet.

Alle Analysedaten sind künstlich. Dies ist kein Nachweis empirischer Modellqualität und keine allgemeine Zusage für Hardware, Modellarchitekturen oder Virenschutz. Historische Testzahlen unten gehören ausschließlich zu den jeweils genannten älteren Ständen.

# Abschlussprüfung für 0.5.0-beta.1 · 14. September 2026

## Veröffentlichtes Release

Der endgültige Release-Commit ist `7f14156db83e56e2f96395cbb27bdcda5e543475`.
Der [Windows-Paketlauf](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/actions/runs/34896832148)
bestand 947 Python-Tests in 799,967 Sekunden, 82 JavaScript-Tests, Paketidentität,
normale und lange Ausgabepfade sowie einen vollständigen modellfreien Workflow
mit CSV/XLSX, HTML/Markdown und Wiederaufnahme. Das veröffentlichte ZIP stammt
unverändert aus diesem geprüften Lauf.

Die [Source-Installationsprüfungen](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/actions/runs/34896832413)
bestanden auf Windows (947 Tests, 862,344 Sekunden) und macOS (947 Tests,
374,240 Sekunden, 18 plattformabhängige Skips), jeweils zusätzlich 67 JS-Tests
und den tatsächlichen HTTP-Start. Frühere Mac-Prozessfehler traten in diesem
Lauf nicht auf; die native Mac-Ausgabe bleibt zurückgestellt.

Lokal wurden 202 Ressourcen exakt mit den Git-Blobs verglichen. Die Prüfung
von 1408 Paketdateien und eingebettetem Python-Code fand keine der geprüften
Privatmarker; elf erneute UI-Prüfungen bestanden. Das ist kein vollständiger
Geheimnisscan, VM-Test oder empirischer Qualitätsnachweis. Alle Analysedaten
der Tests sind synthetisch.

Windows-ZIP SHA256: `d15166b48ea85a61dc3735eaf96f3e60af2df950c7703b27dff1683a73c21836`.

## Historische Zwischenschritte vor der Veröffentlichung

Die folgenden Angaben beziehen sich jeweils auf frühere Commits und ersetzen
nicht den oben ausgewiesenen abschließenden Nachweis.


Auf `92b8971` bestand die GitHub-Windows-Sourceprüfung 947 Python-Tests in
631,116 Sekunden, 67 JavaScript-Tests sowie den HTTP-Start der Oberfläche.
Der separate Paketjob führte ebenfalls 947 Python-Tests aus; dort scheiterte
die anschließende Entfernung einer Test-Logdatei an einem noch auslaufenden
Hilfsprozess. Der Test wartet nun auch auf dessen vollständiges Ende, zusätzlich
zur bestätigten Bereinigung seiner Nachkommen. Die fünf betroffenen lokalen
Prozesstests bestanden danach in 2,202 Sekunden. Die erneute Paketabnahme bleibt
unter [GitHub Actions](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/actions/workflows/windows-package.yml)
am jeweiligen Commit prüfbar; ein erfolgreicher Source-Test allein ist keine
Paketfreigabe. Die zwei aktuellen [Mac-Prozessfehler](../start/macos/README.md)
sind ausdrücklich davon getrennt und noch offen.

Nachtrag zum Oberflächenstart: 16 lokale App-/Instanztests bestanden nach dem
Entfernen einer unnötigen DNS-Namensauflösung beim Binden an `127.0.0.1`.
Ein gezielter Test verbietet `socket.getfqdn` und prüft den tatsächlich
gebundenen Loopback-Port; vor der Änderung schlug er an genau diesem Aufruf fehl.
Die GitHub-Mac-Quellprüfung auf `bc69aa7` meldete zuvor zwei Startzeitüberschreitungen
bei 946 Tests (18 plattformabhängige Skips). Deren genaue Ursache war aus dem
leeren Startprotokoll nicht ablesbar; die erneute GitHub-Prüfung muss zeigen,
ob diese Verzögerung damit behoben ist. Die folgenden Gesamt- und Paketnachweise
beziehen sich weiterhin auf ihre ausdrücklich genannten früheren Quellstände.

Am Quellstand `36dfe0d` liefen **946 Python-Tests in 433,075 Sekunden**:
944 bestanden; zwei Tests mit echten Windows-Symlinks wurden wegen fehlender
Erstellungsrechte übersprungen. Die übrigen Prüfungen für umgeleitete Pfade
bestanden. Die zuvor beobachteten Testfixture-Fehler sind behoben; diese
Gesamtausführung war erfolgreich. Für den unveränderten JavaScript-Code liegen
**82 bestandene Tests** vor. Alle Analysedaten und simulierten Modellantworten
dieser Regression sind künstlich; das ist kein Nachweis allgemeiner Modellqualität.

Die daraus gebaute Windows-EXE bestand **11 normale Oberflächenprüfungen**,
**12 Prüfungen mit Ergebnisordnern über 300 Zeichen** sowie CSV-/XLSX-Verarbeitung
mit HTML-/Markdown-Berichten, unveränderten Eingaben und Wiederaufnahme. Die
Oberflächenprüfung umfasst drei modellfreie Module, Handbuch, Instanzschutz,
bestätigtes Beenden eigener Kindprozesse und Neustart. Temporäre
UI-Installationen wurden entfernt. Die EXE startete ohne Python im Suchpfad;
eine frische virtuelle Maschine wurde nicht geprüft.

Zusätzliche native Tests bestätigten das atomare Speichern bei kurzzeitig offenen
Windows-Lesehandles, auch auf langen Pfaden. Dauerhafte Verweigerung bleibt nach
höchstens 0,75 Sekunden Wartezeit ein Fehler; Originaldatei und atomarer Austausch
bleiben geschützt. Das ist keine allgemeine Zusage für jede Virenschutzkonfiguration.

Der Paketbestand umfasst 1.407 Dateien. Der geprüfte Bootstrap entspricht den
erfassten Quellen; Projektmodule werden aus den erfassten Quelldateien geladen.
Der gezielte Abgleich fand keine der geprüften privaten Pfade oder Kennungen.
Jedes Mitglied der geprüften ZIP stimmt per SHA-256 mit dem Paket überein.
Dies ersetzt weder eine digitale Signatur noch einen vollständigen Malware-Scan.

Der abschließende Dokumentationsstand ändert diesen Analysecode nicht. Die
konkrete Quellenbindung jedes Pakets steht in dessen
`_internal/packaging/build-manifest.json`. GitHub Actions führt Regression und
Paketprüfungen zusätzlich aus; der tatsächliche Status ist am jeweiligen
Release-Commit zu prüfen. Eine native Mac-Distribution bleibt zurückgestellt.

## Ältere Zwischenstände

Die folgenden datierten Nachweise bleiben zur Nachvollziehbarkeit erhalten;
frühere offene Punkte beschreiben ihren jeweiligen damaligen Stand.

# Windows-Quellstand und Paketprüfung · 14. September 2026

Die zusammengeführte Regression am Quellstand `ad553db` führte **895 Python-Tests
in 434,437 Sekunden** aus: 894 bestanden, ein Windows-Symlinktest wurde
übersprungen. **82 JavaScript-Tests** bestanden. Die Tests verwenden synthetische
Daten und simulierte Modellantworten; sie belegen keine allgemeine Modellqualität.

Der native Windows-Paketkandidat aus Commit `56750ed` verwendet Python 3.12.14
und PyInstaller 6.22.3. An der tatsächlichen EXE bestanden **11 Prüfungen der
Oberfläche** und **12 Prüfungen mit einem Ergebnisordner über 300 Zeichen**.
Der Langpfadtest bestand bei erneuter Ausführung mit unveränderter EXE. Die
Oberflächenprüfungen umfassen drei modellfreie Module, Berichtserzeugung,
Instanzschutz, Neustart sowie bestätigtes Ende der eigenen Kindprozesse.
Zusätzlich bestanden CSV-/XLSX-Verarbeitung, modellfreie Coverage,
HTML-/Markdown-Export, unveränderte Originale und geprüfte Wiederaufnahme.
Dabei befand sich kein Python im Suchpfad der gestarteten EXE. Die Paketprüfung
bestätigt tatsächliche Quellenloader und den erfassten Bootstrap; eine
Paketänderung verhindert die Wiederverwendung unpassender Checkpoints.
Das ist eine isolierte Paketprüfung auf Windows, kein Test in einer frischen VM
und keine allgemeine Freigabe aller Pfadlängen oder Virenschutzkonfigurationen.

**Abschließende Freigabe noch offen:** Die oben genannte vollständige Regression
belegt den früheren Quellstand `ad553db`. Ein späterer Durchlauf blieb wegen
eines Einrückungsfehlers in einer Testdatei und einer veralteten Pfadannahme in
einer Testfixture unvollständig erfolgreich. Die erneute vollständige Regression
nach den Korrekturen läuft noch. Der aktuelle Quellstand ergänzt außerdem ein
kurzes, begrenztes Wiederholen atomarer Schreibvorgänge bei vorübergehenden
Windows-Dateisperren. Für diesen Stand sind ein neuer Build und die erneute
Prüfung genau des auszuliefernden ZIP erforderlich; die bestandenen Smokes von
`56750ed` ersetzen diese Abschlussprüfung nicht.
Der vorbereitete GitHub-Buildworkflow einschließlich Langpfadprüfung ist kein
bereits bestandener GitHub-Lauf. Die native Mac-Distribution ist zurückgestellt;
bestehende Mac-Source-Dateien bleiben erhalten.

Die folgenden Einträge dokumentieren ältere Zwischenstände.
# Windows-Prozessverwaltung und Ollama-Status · 14. September 2026

Die vollständige Regression führte **888 Python-Tests in 414,254 Sekunden**
aus: 879 bestanden, ein Windows-Symlinktest wurde übersprungen, acht alte
Telegram-Testfixtures scheiterten an ihrer unvollständigen Appinitialisierung.
Nach Anpassung dieser Fixtures bestanden **59 betroffene App-, Telegram-,
Start-/Beenden-, Pfad- und Wiederaufnahmetests in 39,743 Sekunden**. Die
bestehenden Fortschritts- und Datenschutzassertionen blieben erhalten.
**82 JavaScript-Tests bestanden.** Eine zweite vollständig grüne
888-Test-Ausführung wird damit nicht behauptet.

Geprüft wurden sichere Pause, bestätigter Abbruch, Bereinigung eigener
Unterprozesse, Weiterlaufen fremder Prozesse, Instanzschutz, beschädigte oder
fehlende Abschlussnachweise, veraltete Startversuche sowie der Start ohne
Ollama. Ein im echten Windows-Test entdeckter Unterschied zwischen Python-
Startprozess und Supervisor wurde korrigiert. Der Browser erhält den
bestätigten Abschluss vor dem Serverende; ein Verbindungsabbruch gilt nicht
als erfolgreicher Abschluss. Diese Anzeige und die Ollama-Modellliste wurden
zusätzlich in einer isolierten Browserinstanz geprüft.

Die neue Mac-Distribution wurde zurückgestellt. 14 in der Vollprüfung
enthaltene reine Tests gehörten zu noch unbenutzten POSIX-Vorarbeiten; diese
Dateien wurden danach getrennt vom Windows-Repository gesichert. Die 59
abschließenden Tests liefen bereits auf diesem bereinigten Stand. Alle
Analysedaten und Modellantworten waren künstlich; keine Telegramnachrichten
oder echten Modellanfragen wurden versendet. 213 lokale Dokumentationslinks
wurden geprüft, ohne fehlendes Dateiziel.

Dies bestätigt den Windows-Sourcebetrieb. Ausführbare Pakete, ihre tatsächlich
geladenen Quellen und die frische Installation folgen als separate Abnahme.

---

# Gemeinsamer Programmeinstieg / P02a · 14. September 2026

**61 gezielte Python-Tests bestanden** (76,752 Sekunden). Geprüft wurden der
gemeinsame Programmeinstieg, erhaltene Sourceaufrufe, die feste Liste der
Paketeinstiege, frühe Ablehnung fremder Skripte im simulierten Frozenbetrieb,
Argumente und Exitcodes einschließlich Pause sowie bestehende App-/Diagnoserien-
und Runtimeübergaben. Ein echter Sourceprozess führte eine modellfreie Diagnose
aus und setzte sie anhand unveränderter Ergebnisse fort. Eigene Source-Skripte
bleiben nutzbar; es gab keine echten Modellanfragen.

Die Frozenprüfung ist hier noch simuliert. Tatsächliche Windows-/macOS-Pakete,
deren ausgeführte Quellen, Prozessaufsicht und kontrolliertes Schließen sind
eigene folgende Abnahmeschritte. Die folgende Vollregression gehört zu P01c;
für P02a wird keine zusätzliche vollständige Regression behauptet.

---

# Lokale Datei-/Ordnerauswahl / P01c · 14. September 2026

**834 Python-Tests ausgeführt: 833 bestanden, ein Windows-Symlinktest übersprungen;
keine Fehler** (403,670 Sekunden). **68 JavaScript-Tests bestanden.** Die vollständige
Regression umfasst die externe Ergebnisablage und die neue Auswahl innerhalb der
Oberfläche. Alle Analysedaten und Modelltransporte waren künstlich.

Geprüft wurden CSV-/XLSX-Import, Mehrblatt-Auswahl mit erneuter Quellenprüfung,
Originaldateischutz, Ausgabe neben der Eingabedatei, ausdrücklich gewählte andere
Ziele, Browserupload-Wechsel, Prüf-Folgeläufe und Zugriffsschutz. Ein Windowsfehler
beim Vergleich unterschiedlicher Dateizeitangaben wurde vor dieser Vollprüfung
behoben; frische XLSX-Dateien werden korrekt eingelesen.

Im Browser zusätzlich bestätigt: CSV-Import, Excel-Blattauswahl, Ordnernavigation,
alternatives Ziel und Rückkehr zum Eingabedateiordner. Anschließend wurden nur die
Dialogbreite und die Auslieferung der schematischen Handbuchgrafik ergänzt; dafür
bestanden 24 gezielte Python-Tests, und beide Darstellungen wurden visuell geprüft.
Die Grafik erklärt die beiden Importwege mit erfundenen Pfaden. Die vorangehende
Vollprüfung wird durch diese gezielte Ergänzung nicht nachträglich hochgezählt.

Dies ist weiterhin ein Source-Entwicklungsnachweis. Gebaute Windows-/macOS-Pakete,
deren frische Installation und Start-/Beenden-Verhalten werden separat geprüft.

---
# Externe App-Ergebnisordner / P01b · 14. September 2026

Die vollständige Python-Regression führte **811 Tests in 397,005 Sekunden** aus:
809 bestanden, ein Windows-Symlinktest wurde wegen fehlender Berechtigung
übersprungen und ein Test scheiterte an einer veralteten Fehlermeldungserwartung
der Promptansicht. Dieser Test verwendet nach der Korrektur eine tatsächlich
vorhandene Konfiguration aus einem fremden Projekt und prüft ihre Ablehnung vor
dem Aufbau des Promptkatalogs. Die zugehörige gezielte Wiederholung bestand
anschließend mit **vier Tests in 1,280 Sekunden**. Eine erneut vollständig grüne
811-Test-Regression wird damit nicht behauptet. Für die übersprungene reale
Symlinkprüfung bestand zusätzlich ein deterministischer Test der aufgelösten
Pfadumleitung ohne erforderliche Windows-Symlinkberechtigung.

**57 JavaScript-Tests bestanden in 158,1 Millisekunden.** Im Browser wurde die
Ergebnisordnerprüfung mit einem ungültigen und anschließend einem gültigen Ziel
kontrolliert; eine vorherige Fehlermeldung bleibt nach erfolgreicher Prüfung
nicht stehen. **217 lokale Dokumentationslinks wurden ohne fehlende Ziele
geprüft.** Die künstlichen Python-Fälle decken unter anderem gebundene externe
Ergebnis- und Reviewordner, Folgeeingaben mit Inhaltsnachweis, unveränderte
Projektverweise bei Speicherfehlern sowie die bisherige Ablage alter Jobs ab.

Dies ist ein Entwicklungsnachweis der Quellversion mit manueller Pfadeingabe.
Ein nativer Ordnerauswahldialog und gebaute Windows-/macOS-Installationspakete
sind damit weder geprüft noch freigegeben. Frühere Testzahlen bleiben unten als
getrennte historische Nachweise erhalten.

---

# Pfadgrundlage für die Distribution / P01a · 14. September 2026

34 gezielte Python-Tests bestanden. Geprüft wurden die CLI-Ausgabe neben der
tatsächlichen Eingabe, getrennte neue Laufordner, unveränderte Originaldateien,
Wiederaufnahme, explizite Ausgabeziele, vorhandene App-Projekte und der gemeinsame
Lauf aller fünf Diagnosen. Die Tests verwenden ausschließlich künstliche Daten.
Source-/Frozen-Pfade wurden simuliert, einschließlich gesperrter Ausgabe in
gebündelte Ressourcen; dies ist noch kein Test einer gebauten EXE oder macOS-App.
Die Ergebnisordnerwahl in der Oberfläche folgt in einem eigenen Integrationsschritt.
Der zuvor dokumentierte vollständige Testlauf bleibt ein eigener Nachweis.

---

# Entwicklungsprüfung v7 / S13i2 · 14. September 2026

**767 Python-Tests und 52 JavaScript-Tests bestanden.** Die vollständige
Python-Regression lief mit eingefrorenen Programmquellen; die Frontendprüfung
enthält unter anderem Modusauswahl, gespeicherte Einstellungen, Fehlermeldungen,
Aufwand und getrennte Fortschrittsanzeigen. Die synthetischen Integrationstests
prüfen reale CLI-/Runner-Einstiege, zehn zusätzliche Analyseperspektiven,
Quellenbindung, Personen-/Passagenzuordnung, Berichtsausgabe und Wiederaufnahme
mit simuliertem Modelltransport. Dies ist ein technischer Entwicklungsnachweis,
kein unabhängiger Benchmark der inhaltlichen Analysequalität.

**210 lokale Dokumentationslinks geprüft; keine fehlenden Ziele.** Das ist eine
Prüfung lokaler Verweisziele, keine Zusage über die Verfügbarkeit externer Seiten,
die Aktualität jedes historischen Screenshots oder die visuelle Darstellung auf
jeder Bildschirmgröße. Die bisherigen datierten Prüfberichte stehen unverändert
darunter und werden nicht dem neuen Entwicklungsstand zugerechnet.

Ergänzend wurde der vorhandene Integrationstest auf einen gemeinsamen Hauptlauf
mit allen fünf Diagnosen erweitert und erneut bestanden (ein gezielter Test,
19,927 Sekunden). Geprüft wurden alle Ergebnisprüfsummen, die Markdown-/HTML-
Abschnitte, sechs getrennte Kindläufe, unveränderte Eingaben und die Wiederaufnahme
ohne zusätzliche Modellanfragen. Dieser ergänzende Nachweis folgt auf die obige
Vollregression; deren Testzahl wird deshalb nicht nachträglich erhöht. Die
wissenschaftliche Phase ist damit einschließlich Dokumentationsabgleich geprüft. Neue
Windows-/macOS-Pakete, frische Installation dieser Pakete, deren Ressourcenpfade
und native Start-/Schließabläufe sind anschließend gesonderte Phase-2-Prüfungen.
Diese Testzahlen sind keine Veröffentlichung oder Freigabe fertiger Installationspakete.

---

# Prüfung 0.3.4 · 11. September 2026

119 Python-Tests und zehn JavaScript-Tests bestanden. Zusätzliche Prüfungen: tatsächlich überlappende Arbeitseinheiten, unveränderte Passage-Gruppen und Ergebnisreihenfolge, geordnete Diagrammerzeugung im Hauptthread, Wiederaufnahme fertiger Einheiten, Abbruch ohne neue Aufträge, frische Speicherprüfung, Cloud-Sperre, eigene Serverkonfiguration und Bereinigung bei Startfehlern, korrekte Zählung laufender und fehlgeschlagener Anfragen. Browserprüfung für gespeicherte Auswahl, simulierte Speicherschätzung, verspätete Antworten und Anbieterwechsel. Handbuchbild mit ausdrücklich simulierten Hardwarewerten.

**Realer lokaler Test:** Granite 4.2:8b, zwei Verarbeitungsplätze, 4.096 Tokens Kontext je Anfrage. Nach einer kurzen Aufwärmanfrage wurden zwei künstliche Anfragen gleichzeitig verarbeitet. Ollamas Laufzeitprotokoll zeigt zwei aktive Slots (0 und 1) mit überlappender Token-Erzeugung. Antworten kamen nach rund 5,5 und 5,2 Sekunden; danach wurde die eigene Instanz beendet. Dieser kurze Funktionstest belegt keine allgemeine Speicherobergrenze, keinen garantierten Geschwindigkeitsgewinn und keine Codierqualität. Keine privaten Forschungsdaten oder Cloud-Anfragen für diesen Test.

---

# Prüfung 0.3.3 · 11. September 2026

110 Python-Tests und neun JavaScript-Tests bestanden. Acht neue Tests prüfen die Kapazitätsschätzung, Kontextbedarf, fremde GPU-Belegung, bereits geladene Modelle, fehlende Metadaten und die Beschränkung auf lesende lokale Metadaten-Endpunkte. Browserprüfung mit echtem lokalem Ollama-Metadatenabruf: automatische Aktualisierung, Ablehnung verspäteter Antworten und Ausblenden bei Cloud-Auswahl. Die Handbuchabbildung verwendet klar gekennzeichnete simulierte Hardwarewerte. Keine lokalen oder Cloud-Inferenzanfragen für dieses Feature; die Parallelitätszahlen sind keine empirisch gemessenen Lastgrenzen.

# Codebook mapping and rules · 2026-09-11

- All 102 Python tests pass, including Windows persistence and full workflow pause/resume. The mock transport identifies its module from the first system-prompt line so appended rule guidance remains testable.
- Nine JavaScript tests pass. Added checks cover manual selection and missing/duplicate mappings.
- Four Python regression cases cover arbitrary headers, immutable normalized copies, optional fields, explicit code paths, rule propagation into single-label/multi-label coding and verification prompts, rule diffs and follow-up saves.
- Edge browser checks confirm CSV preview, manual mapping, missing-field and duplicate-field start gates, validation, reload persistence and a 390-pixel viewport.
- The full 12-code demo now contains inclusion, exclusion and distinction rules. The focused regression tests passed again after expanding this fixture.
- All published fixtures and screenshots are artificial. No local or cloud model calls; no claim of improved empirical coding quality.

# SVG patch · 0.3.1 · 2026-09-10

- Three added Python tests cover passive SVG validation, rejection of active/external content, real vector output for both plot types, SVG preference/PNG fallback and unique Windows artifact paths. Total: 98 tests.
- Final full-suite run: all 98 Python tests passed with unchanged source, including both Windows DPAPI tests and workflow pause/resume.
- Eight existing JavaScript tests pass. Edge verifies 13 SVG images in the app report, individual SVG download containing vector paths, 13 unique SVG artifacts, offline display and PDF export, without JavaScript errors.
- Synthetic results from an earlier Cloud run were redrawn. No local or cloud model calls and no real interview data were needed.

# Provider and chart patch · 2026-09-10

- 95 Python tests pass, including the complete mocked workflow, provider request/response formats, refusal and truncation handling, bounded retries, secret separation, selected-provider environment, privacy guards on resume, chart deduplication, and Windows DPAPI key rotation/removal. DPAPI tests run under the regular Windows account; they cannot use the restricted sandbox identity.
- Eight existing JavaScript regression tests pass. A real headless Edge session verifies the default privacy checkbox, cloud field gating, separate keys, removal, persisted privacy after reload, and HTML category-to-text drilldown. All embedded images load; no JavaScript errors observed.
- The new Ollama Cloud transport completes cluster analysis and summarization on two public synthetic rows: three successful real requests, no local inference. The exported HTML is generated successfully.
- OpenAI, Anthropic and Hugging Face adapters are tested with controlled HTTP responses only. Live authentication, account permissions and individual model compatibility still need a provider account. They are not claimed as live-validated.
- Existing 38-row synthetic results are redrawn without new model requests. Original study data and prior reports remain unchanged. Review-status charts describe the model-run snapshot; they are not live human-review completion counters.
- No new SDK dependencies or beta release. The public defaults remain local Ollama and artificial inputs.

# Usability-Patch · 10. September 2026

- 84 Python-Tests: 83 bestanden im eingeschränkten Testkonto; der Windows-DPAPI-Test bestand separat im regulären Benutzerkontext. Nach der Serverkorrektur alle 10 Tests der Desktop-/Telegram-Datei erneut erfolgreich.
- Acht bestehende JavaScript-Tests bestanden; insbesondere verzögerte Antworten, Projektwechsel, gespeicherte Prüfentscheidungen und Schutz neuerer Entwürfe.
- Neuer ID-Assistent: exakte Gruppierung, getrennte Dokumentgruppen/Personen/Positionen/Texte, explizite Bestätigung, veraltete Vorschauen, vorhandene IDs und unveränderte Originale geprüft.
- HTML: eingebettete Bilder, externe und ausbrechende Pfade, sichere Textdarstellung sowie exakte CSP-Freigaben geprüft. Beide kompletten Mock-Pipelines einschließlich Wiederaufnahme erzeugen HTML und dokumentieren dessen Prüfsumme.
- Tatsächlicher Edge-Browsertest: 14 Berichtsteile und 13 Diagramme aus einem früheren synthetischen Cloud-Lauf; Suche, Navigation, Auf-/Zuklappen und Wiederöffnung erfolgreich. Handbuch mit 12 Kapiteln und acht Bildern lädt ohne Browserfehler. ID-Gruppierung und anschließende Eingabevalidierung zusätzlich in der Browseroberfläche durchgeführt.
- Für diesen Darstellungs-/Importpatch keine zusätzlichen LLM-Anfragen nötig. Vorhandene Cloud-Ergebnisse wurden ohne inhaltlichen Neulauf in HTML überführt. Keine lokale Ollama-Inferenz und keine echten Interviewdaten im Test.
- Die zusätzliche HTTP-Verbindungswarteschlange und HTTP/1.1 beseitigten im Browsercheck zuvor beobachtete Verbindungsabbrüche bei parallelen Bildabrufen.

Die fachliche Qualität der LLM-Auswertung ist damit nicht neu bewertet. Die frühere echte Cloud-Prüfung und Installationsprüfung sind unten dokumentiert. Ein Beta-Release wurde nicht erstellt.

---

# Review workflow validation · 0.3.0-dev

Date: 2026-09-10. Published predecessor: `b95a74ad0fbb8a47f6c50bb20dad760d00cb2fb4`.

- 78 Python tests exercised the current source. 77 passed in the restricted sandbox; the Windows DPAPI persistence test could not access the normal user-profile encryption context. The complete 10-test desktop/Telegram file then passed outside that restriction, including DPAPI. No local model inference was performed.
- Eight Node.js tests pass, including serial autosave, edits during an in-flight save, preservation on revision conflict, and stale report responses after closing a preview.
- New Python coverage includes draft/history persistence after restart, optimistic concurrency, protected HTTP review/export routes, literal-text XLSX export, explicit exclusion of uncoded cases, source-preserving follow-up inputs, legacy category versions, proposal reference validation and context limits, numeric progress and mocked Telegram messages.
- Real browser checks with synthetic data confirmed persisted decisions after reload, the follow-up preview and creation of a separate input revision without launching a model, and formatted viewing of the proposal report. Screenshots contain artificial text and fabricated reviewer decisions.
- Two additional real workflows used **Ollama Cloud / gemma4:31b**, exclusively with three passages from the public synthetic demo and invented human judgments. The proposal workflow completed with one model response and produced one grounded suggestion distinguishing practice from transfer. The follow-up clustering/summary workflow completed with five logged successful responses. No original input or category file was replaced. These six responses are a functional integration check, not a quality benchmark or estimate of local Granite performance.
- The proposal explicitly warned that its interpretation depends on context not always stated in the short passage. No proposal was automatically applied. Larger reviewed collections are split into bounded blocks; cross-block consolidation remains a human task.
- The existing Python environment was used for this update. The fresh Python 3.13 installation documented in [INSTALLATION_TEST.md](INSTALLATION_TEST.md) tested the preceding beta and was removed afterward; it was not recreated for this change.

Earlier validation records follow and refer to their stated source versions.

---

# Validation of project isolation, imports and directory layout

Date: 2026-09-10. Baseline: `4c53d6b45d6e7305c49f9d76dd0df4fe475f2fc5`.

- 67 Python tests pass: the complete 65-test suite passed after reorganization in 56.0 seconds; two additional entry-point tests passed from both an unrelated working directory with spaces and the repository directory. Four Node.js browser-logic tests also pass.
- Regressions cover rejected saves retaining the previous valid settings, new uploads invalidating stale revisions, failed resume status, large CSV fields, malformed quoting, incorrect XLSX used-range metadata and broken sheet XML.
- Browser-logic tests exercise delayed validation, a project switch during Start, out-of-order project responses and independent column mappings. Previous previews are cleared on project switches; editing inputs hides an outdated successful validation result.
- The real browser was checked with synthetic inputs: valid validation, rejection of inconsistent passage/person mapping, and restoration of the last valid mapping after reload.
- Code and UI assets now live in `src/`, configuration in `config/`, artificial inputs in `demo/`, tests in `tests/`, and documentation in `docs/`. Root launchers remain available. Markdown file links and PowerShell launcher syntax were checked.
- A real `gemma4:31b` Cloud smoke test through the reorganized CLI entry point used a GUI-generated isolated configuration with two artificial rows. Cluster analysis and summarization completed successfully with three model requests. No local GPU inference, real interview data or live Telegram message was used.
- These are development-machine and synthetic workflow checks, not a guarantee of semantic coding accuracy or compatibility with every PC. Existing projects remain available; changed program provenance requires a new run rather than migration of old checkpoints.

## Earlier validation of XLSX and CSV imports

Date: 2026-09-10. Baseline: `4002a0a31c2fe50887f6d2b8e0a4b1999b327eef`.

- All 59 automated tests pass (64.7 seconds). Six new synthetic import tests cover MAXQDA-style columns, quotes and newlines, explicit sheet selection, invalid headers/formulas, blank cells, bounded input size, unchanged XLSX originals, both input formats and validation with 50 coding rows / 43 passages.
- The browser import was checked with a synthetic two-sheet XLSX export and a CSV category system, including sheet selection and automatic column mapping.
- XLSX ingestion runs locally and requires no model call. No additional Cloud or local GPU inference was used for this change. This release adds `openpyxl` to setup requirements; the command-line runner continues to consume CSV.

## Earlier validation of the local desktop interface

Date: 2026-09-10. Baseline: `90e0ff38fe0da214b6259b4c63a7bd93a6ec689a`.

- 53 automated tests cover the previous workflow and the new local interface. New tests exercise immutable project revisions, synthetic demo validation (50 rows / 43 passages / 12 paths), dependency selection, column errors, path confinement, HTTP session/Origin/Host checks, token redaction and the actual runner with mocked inference through pause and resume.
- Telegram tests use fabricated tokens and a mocked network. They verify session-only persistence, replacement, removal, current-user Windows DPAPI encryption/decryption, event selection, content-free messages and sanitized transport errors. DPAPI was verified outside the restricted sandbox under the normal Windows account. No live Telegram message was sent: no real Telegram bot token or destination was provided.
- A real `gemma4:31b` Cloud smoke test used a configuration produced by the new project interface, with an isolated Cloud override and two artificial input rows. Cluster analysis and summarization completed with three successful model requests. The shipped interface and YAML defaults remain local; no local GPU inference or real study data was used.
- Browser checks exercised demo creation, default column mappings, validation, disabled Telegram settings with a fabricated token, token removal and result/review preview. This is a Windows development-machine validation, not an installer test across multiple PCs.

## Earlier validation of partial checkpoints

Date: 2026-09-10. Baseline: `6110780a325ad793eaf7b9939b106cf568f1bfdd`.

- All 46 automated tests pass. Seven complete 15-module workflow scenarios interrupt the second request in cluster analysis, summarization, SWOT, meta-SWOT, person analysis, ambiguity analysis or hierarchical reduction. Each resumed workflow finishes and the first successful request is not repeated.
- Targeted relation and evidence-audit tests interrupt the second batch and verify reuse of the first batch, complete audit IDs and stable global relation IDs. Integrity tests reject changed inputs/model settings, corrupted results and failed partial work; disabled checkpoints do not write or reuse results.
- A real `gemma4:31b` Cloud probe reduced four artificial findings in two batches. An intentional interruption before the second network request left one validated checkpoint. Resume reused that batch, completed the other and preserved all four source records in the reference graph. This required two successful Cloud requests in total. It tests recovery, not interpretive accuracy.
- Public and private defaults remain local Ollama. No local GPU inference or real study data was used. Program upgrades still require a new run; this release does not migrate older checkpoints.

## Earlier validation of multi-label coding, offline review and hierarchical synthesis

Date: 2026-09-10. Extension baseline: `f2e939ec0f1a32a12cb23d24998fffb2eccd1a87`.

- 41 automated tests cover both coding modes, explicit passage identity, independent multi-label calls, set metrics, abstention/failure coverage, checkpoints, the complete 15-module workflow, review decisions, HTML escaping, multi-level reduction, reference graphs and bounded failure cases.
- A real `gemma4:31b` Cloud workflow completed all 15 modules on 50 synthetic coding rows representing 43 passages. All 43 passages were evaluated without coding failures or abstentions. All 50 reference code assignments were found, with 10 additional model assignments: micro-precision 83.3%, recall 100%, F1 90.9%, mean Jaccard 88.8%, and exact set agreement 33/43 (76.7%). The review queue contains 14 disputed cases; verification can flag a case even when its predicted code set matches.
- The full workflow exercised hierarchical synthesis with 13 reduction calls. A separate real Cloud stress test used an 8500 context budget and completed two reduction levels (eight reduction calls plus final synthesis). The final references resolve through the recorded nodes to all nine input records, including the synthetic source note.
- Browser testing verified required review fields, exported a separate decision JSON file, reloaded the page and imported that downloaded file with the decision, note and reviewer intact. The offline page was visually inspected. Original codings and model results remain unchanged.
- These were development runs with documented continuations: a relation request timed out, the first hierarchy implementation lost model-generated reference lists, and a later response exceeded the summary length limit. Reference provenance is now assigned deterministically from actual batch inputs. A diagnostic run and retry completed successfully. An intentionally undersized 6000-context stress run reached the level bound; a new preflight rejects an impossible static prompt before any reduction requests. The added guard was verified not to affect the completed full-run configuration, and its output hashes were retained through an archived compatibility migration.
- The full extension workflow and its continuations used 207 successful requests; additional targeted diagnostics and stress tests are separate. The standard configurations still use local Granite. No real interview data, private study context or local GPU inference was used for these tests.

Interpretation: the examples are artificial and partly overlap with codebook anchors. These values are illustrative, not an independent accuracy benchmark. The stricter set-level results are not directly comparable to the earlier row-level rate. Local Granite inference and real interviews remain untested. Hierarchical reduction applies to the final synthesis; upstream modules retain their documented context limits. Provenance links document inputs, not semantic completeness of every generated summary.

## Earlier robustness stage

Date: 2026-09-10. Baseline: `6f5c9f5b959156fbd224baef68a3f5de171ad797`.

- 30 automated tests pass with Python 3.12 and UTF-8 enabled on Windows.
- The full YAML integration test executes all 14 module entry points with a replaced model transport. It verifies external IDs, fourth-level code paths, source/person metadata, evidence auditing, generated reports, an intentional interruption and subsequent resume. Changed input is rejected on resume.
- Regression tests cover transport errors, invalid cluster output, incomplete audits, claims without evidence, original text preservation, mapping mismatch, stale outputs, checkpoint integrity, paired relation sampling, conservative context budgets, structured-output routing and agreement coverage.
- The public input passes `--validate-only`: 38 synthetic coding rows, 12 paths, 14 modules, zero model calls.
- Six real cloud requests using `gemma4:31b` completed successfully: verification and blind coding for one trivial synthetic example and two examples from the public dataset with opposed fourth-level codes. All responses passed structural and code/ID validation. These are connection and integration smoke tests, not a model-quality benchmark; the selected public examples also occur as codebook anchors.
- A subsequent real Cloud workflow with `gemma4:31b`, temperature 0, context 131072 and output limit 4000 completed all 14 modules on the public 38-row dataset. Exact row-level code agreement was 35/38 (92.1%), assignment coverage 38/38, with no failed verification/blind-coding cases or abstentions. Kappa remained disabled. There were 36 audited findings, 13 with counterexamples, and 30 validated relations from 58 submitted candidate pairs.
- The three code disagreements concern overlapping practice/transfer, practice/group-conflict, and support/group-exchange interpretations (SYN008, SYN009, SYN037). One passage deliberately has two coding rows. These are illustrative outcomes, not independent accuracy estimates: the dataset is small, artificial and shares material with its codebook anchors.
- This was a development run with controlled continuations, not a clean uninterrupted benchmark. It exposed a wrong person-comparison schema key, a contradictory audit omission instruction, and an oversized synthesis prompt. Corrections were applied before continuing. Completed upstream outputs were reused only after verifying their hashes and the exact relevant source/configuration changes; each migration and prior manifest was archived. A final synthesis-only rerun verified retained source identifiers. The production runner still rejects ordinary resume after code/configuration changes.
- The earlier workflow and its targeted continuations used 166 successful model requests, in addition to the six preliminary smoke requests. A workflow contains multiple requests; this is not 166 complete test runs.
- No local Ollama inference was used. No real interviews or private study configuration were sent to Ollama Cloud.

The earlier stage's metrics were row-based. The extension above replaces that behavior in multi-label mode with independent passage-level predictions and set metrics. Refer to `ROBUSTNESS.md` and `EXTENSIONS.md` for current behavior.

