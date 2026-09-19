# Windows-Paket 0.5.0-beta.2 · Freigabe in Vorbereitung

Der Bugfix-Code bestand die Windows-Paketregression und die native Mac-Sourceprüfung. Das endgültige Paket mit eingebauter Versionsnummer beta.2 muss noch gebaut und abgenommen werden. Aktueller [Testbericht](TEST_REPORT.md). Die folgenden Angaben dokumentieren ältere Pakete und ersetzen diese Abnahme nicht.

# Eigenständiges Windows-Paket 0.5.0-beta.1 · 14. September 2026

Das Windows-Paket enthält Python 3.12.14 und wurde mit PyInstaller 6.22.3 gebaut.
Die EXE wurde in temporären Installationen ohne Python im Suchpfad geprüft:
normale und sehr lange Ergebnisordner, drei modellfreie Module, CSV/XLSX,
HTML-/Markdown-Export, Wiederaufnahme, Instanzschutz und geordnetes Beenden.
Alle Paketprüfungen bestanden; die temporären UI-Installationen wurden entfernt.
Die vollständige Python-Regression umfasst 946 Tests (944 bestanden, zwei
Windows-Symlinktests mangels Erstellungsrechten übersprungen).

Die Eingaben sind künstlich. Eine frische VM, eine universelle Virenschutzfreigabe
oder native Mac-Installation wurden damit nicht geprüft. Die genaue Quellenbindung
steht im mitgelieferten Buildmanifest; der [Testbericht](TEST_REPORT.md) nennt
Prüfstand und Grenzen. [Windows-Kurzanleitung](WINDOWS_STANDALONE.txt) ·
[Build und automatische Paketprüfungen](../packaging/README.md).

## Ältere Zwischenstände

Die folgenden Einträge beziehen sich auf ihre damaligen Paketstände.

# Vorbereitung des eigenständigen Windows-Pakets · 14. September 2026

Der aktuelle Paketkandidat enthält eine eigene Python-Laufzeit. Bau und
Prüfverfahren stehen in [packaging/README.md](../packaging/README.md), die
Bedienhinweise in [WINDOWS_STANDALONE.txt](WINDOWS_STANDALONE.txt). Ergebnisse
und der noch offene Freigabepunkt stehen im [aktuellen Testbericht](TEST_REPORT.md).
Am tatsächlich gebauten Kandidaten `56750ed` bestanden die modellfreie
Oberflächenprüfung, ihre Variante mit einem Ergebnisordner über 300 Zeichen
sowie CSV-/XLSX-Verarbeitung und Wiederaufnahme. Diese Prüfungen starteten die
EXE ohne Python im Suchpfad; eine frische virtuelle Maschine wurde nicht geprüft.
Die abschließende Regression und der neu zu bauende Auslieferungsstand bleiben
separat abzunehmen. Eine neue native Mac-Distribution ist zurückgestellt.
Die unten genannten Versionen und Testzahlen bleiben als historische Nachweise erhalten.
# Prüfung für 0.4.0-beta.1 (13. September 2026)

203 Python- und 21 JavaScript-Tests bestanden unter Windows mit Python 3.12. Die Tests verwenden künstliche Daten und simulierte Modellantworten, einschließlich kompletter Pipeline und Wiederaufnahme. Der Windows-DPAPI-Test lief im Benutzerkontext. Ein isolierter HTTP-Start mit Leerzeichen im Datenpfad und dem neuen Prompt-Dialog wurde ebenfalls geprüft.

Die GitHub-Prüfung installiert für Windows und macOS jeweils eine frische Python-Umgebung über die mitgelieferten Einrichtungsskripte. Anschließend laufen Regressionen und ein HTTP-Starttest. Den tatsächlichen Status des Release-Commits unter GitHub Actions prüfen; ein vorbereiteter Workflow ist noch kein bestandener Lauf. Physische Mac-GPU-Leistung und macOS-Schlüsselbundintegration sind damit nicht nachgewiesen.


Zwei ergänzende lokale Funktionstests mit granite4.2:30b (Thinking low, 12.288 Kontexttokens) verglichen wiederholte Clusterkontexte mit der Referenztabelle an vier erfundenen Textstellen. Beide Antworten enthielten dieselben vier gültigen Beleg-IDs sowie Unterrichtsfreude, Einkommen, Arbeitsbelastung und soziale Motivation. Die neue Anfrage war in diesem Beispiel kleiner (4.626 statt 5.222 UTF-8-Bytes). Das ist kein Qualitätsbenchmark: Beide Antworten verschärften eine Motivabwägung stellenweise zu einem Gegensatz mit „ausschließlich sozialer Motivation“, den der Ausgangstext nicht trägt. Eine fachliche Prüfung bleibt erforderlich; die Referenztabelle allein verhindert solche Deutungen nicht.

# Ergänzende Prüfung für 0.3.5 (12. September 2026)

- Windows: Python-Regressionen einschließlich vollständiger synthetischer Pipeline, Wiederaufnahme, Codebuchregeln, Kontext-Startsperre und Windows-Schlüsselverschlüsselung; JavaScript-Tests einschließlich sichtbarer Kontexthinweise. Die endgültige Testanzahl steht in den GitHub-Versionshinweisen.
- Echter Start von `src/local_app.py` mit einem temporären Projektpfad mit Leerzeichen: HTTP 200, Handbuch- und Telegram-Bedienelemente vorhanden. Testprozess und temporäre Daten anschließend entfernt.
- Live mit lokalem `granite4.2:30b`, Q4_K_M: zwei gleichzeitige vollständige Antworten bei je 12.288 Tokens Kontext, alle 65 Schichten auf den GPUs (12 GB + 16 GB). Bei je 16.384 Tokens: vollständige Antworten, aber nur 61 von 65 Schichten auf den GPUs. Keine Festlegung einer universellen Leistungsgrenze; die Testprompts füllen das Kontextfenster nicht vollständig.
- Eine künstliche Eingabe über der lokalen Kontext-Rechengrenze wurde über die neue Zusammenfassungsfunktion vollständig in Teile zerlegt, verdichtet und abschließend zusammengefasst. Geprüfte Zwischenteile wurden gespeichert. Methodische Genauigkeit ist damit nicht gemessen.
- Ein erster Wiederholungstest wurde durch ein gleichzeitig gestartetes zweites Modell gestört und lief ins Zeitlimit. Nach dessen Beendigung wurden die Tests mit freiem Speicher wiederholt. Das bestätigt, dass die Belegung anderer Programme für das Ergebnis relevant ist.
- macOS verwendet denselben Analysecode und weiterhin die Starter unter `start/macos`. Der GitHub-Prüflauf kontrolliert Installation, Regressionen und HTTP-Start; lokale Granite-GPU-Tests unter Windows belegen keinen Vollbetrieb auf einem physischen Mac.
- Öffentliche Dateien und Archive werden gegen eine erlaubte Dateiliste und auf private Studienpfade, Zugangsdaten und HPC-Konfiguration geprüft. Private Konfigurationen und Forschungsdateien werden beim OneDrive-Update beibehalten.

# Installationsprüfung für 0.2.0-beta.1

Am 10. September 2026 wurde eine neue Kopie der öffentlichen Programmdateien unter Windows mit Python 3.13.1 eingerichtet. Der Test verwendete den mitgelieferten Aufruf `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_local.ps1 -Setup`, auf den auch `Einrichtung.cmd` verweist.

Dabei wurde eine neue `.venv` erstellt und `requirements.txt` installiert. Die Umgebung hatte keinen Zugriff auf die Pakete der bestehenden Python-Umgebungen (`include-system-site-packages = false`). Es war eine isolierte Python-Installation auf einem vorhandenen Windows-System, keine vollständige virtuelle Maschine und kein Test auf einem zweiten PC.

Ergebnisse:

- `python -m pip check`: keine widersprüchlichen oder fehlenden Abhängigkeiten.
- `python -X utf8 -m unittest discover -s tests -v`: alle 67 Tests bestanden, einschließlich CSV-/XLSX-Import, lokaler Oberfläche, Workflow, Checkpoints und Windows-Schlüsselspeicherung.
- `node --test tests/test_local_app_frontend.cjs`: alle vier Tests bestanden. Node ist nur für diese Entwicklungstests erforderlich.
- Tatsächlicher Start mit der neuen Python-Umgebung: Oberfläche im Browser geöffnet, künstliche Demo geladen und Eingabeprüfung erfolgreich abgeschlossen (50 Codierzeilen, 43 Passagen, 12 Codepfade).
- Die Tests führten kein lokales Ollama-Modell aus. Modellantworten in den automatisierten Tests wurden simuliert. Ein vorausgegangener separater Cloud-Funktionstest verwendete ausschließlich künstliche Daten; er ersetzt keinen Leistungstest eines lokalen Modells.

Die frisch installierten Paketversionen sind in [requirements-tested-windows-py313.txt](requirements-tested-windows-py313.txt) festgehalten. Sie dokumentieren diese getestete Kombination, nicht die Kompatibilität jeder Paketversion mit allen unterstützten Python-Versionen. Für eine Wiederholung mit Python 3.13 kann eine neue Umgebung die dokumentierten Versionen direkt installieren:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r docs/requirements-tested-windows-py313.txt
```

Die normale Einrichtung verwendet weiterhin `requirements.txt`. Neuere Paketstände können abweichende Ergebnisse liefern. Modellinstallation, Speicherbedarf, Geschwindigkeit und inhaltliche Güte müssen auf dem jeweiligen Zielrechner geprüft werden.
