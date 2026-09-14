# Windows-Paket selbst bauen und prüfen

Diese Anleitung beschreibt den nativen Windows-Build aus einem sauberen,
versionierten Checkout. Das Ergebnis ist ein vollständiger Programmordner mit
`QualitativeAnalyse.exe` und `_internal`, verpackt als ZIP. Die EXE allein reicht
nicht aus. Für die Verwendung des fertigen Pakets ist keine eigene
Python-Installation vorgesehen; zum **Bauen und Testen** wird Python benötigt.

Der Windows-Paketworkflow befindet sich in
[windows-package.yml](../.github/workflows/windows-package.yml). Er lädt nach
bestandenen Prüfungen ein Actions-Artefakt hoch. Er erstellt weder einen
GitHub-Release noch einen Tag. Eine native macOS-Distribution ist derzeit
pausiert; die vorhandene [Source-CI](../.github/workflows/macos.yml) bleibt erhalten.

## Voraussetzungen

- Windows x64, Python **3.12.14 x64**, Git und PowerShell 7.
- Node.js mit integriertem Test-Runner für die JavaScript-Tests. Die CI verwendet
  das Node.js des Windows-Runnerimages und protokolliert dessen Version.
- Ein sauberer Checkout des gewünschten Commits ohne private Daten, eigene
  Konfigurationen oder unversionierte zusätzliche Analyseskripte.
- Die vollständig gepinnten Abhängigkeiten aus
  [requirements-build.txt](requirements-build.txt). Installation und GitHub
  Actions benötigen Internetzugriff. Die beschriebenen Modelltests verwenden
  synthetische Daten und simulierte Antworten; die Frozen-Smokes starten kein
  Ollama und rufen kein Cloudmodell auf.

Alle folgenden Befehle werden im Repository-Hauptordner ausgeführt. Bei einem
Fehler nicht mit dem nächsten Abschnitt fortfahren. Ein anderer Python-Patchstand
oder geänderte Pins erfordern eine bewusst geprüfte neue Buildgrundlage.

## 1. Umgebung und vollständige Regression

```powershell
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python-Umgebung konnte nicht angelegt werden.' }
& ./.venv/Scripts/python.exe -c "import sys; assert sys.version_info[:3] == (3, 12, 14), sys.version"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12.14 erforderlich.' }
& ./.venv/Scripts/python.exe -m pip install -r packaging/requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Installation fehlgeschlagen.' }
& ./.venv/Scripts/python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Abhängigkeiten widersprechen sich.' }

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = 'src;tests'
$env:MPLBACKEND = 'Agg'
& ./.venv/Scripts/python.exe -u -m unittest discover -s tests -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Python-Tests fehlgeschlagen.' }
$testFiles = @(Get-ChildItem -LiteralPath tests -Filter 'test_*.cjs' | Sort-Object Name | ForEach-Object FullName)
if ($testFiles.Count -eq 0) { throw 'JavaScript-Tests fehlen.' }
node --test @testFiles
if ($LASTEXITCODE -ne 0) { throw 'JavaScript-Tests fehlgeschlagen.' }
```

## 2. Manifest und Anwendung bauen

[build_manifest.py](build_manifest.py) verlangt den tatsächlichen `HEAD`, einen
sauberen Stand der versionierten Dateien und versionierte Buildinputs. Es erfasst
die öffentliche Ressourcenliste, deren Inhalte, die Bootstrap-/Spec-Dateien und
die Build-Abhängigkeitsversionen. Die erzeugte `build-manifest.json` ist absichtlich
ignoriert und wird nicht selbst zum Quellcommit hinzugefügt.

```powershell
$sourceCommit = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Git-Commit konnte nicht gelesen werden.' }
& ./.venv/Scripts/python.exe packaging/build_manifest.py --repository . --source-commit $sourceCommit.Trim() --output packaging/build-manifest.json
if ($LASTEXITCODE -ne 0) { throw 'Buildmanifest konnte nicht erstellt werden.' }
& ./.venv/Scripts/python.exe -m PyInstaller --clean --noconfirm --distpath dist --workpath build packaging/windows.spec
if ($LASTEXITCODE -ne 0) { throw 'Build fehlgeschlagen.' }
```

Die [Spec](windows.spec) prüft das Ressourceninventar erneut und verhindert eine
zweite Kopie der Projektmodule im Python-Archiv. Die Anwendung lädt die erfassten
Projektquellen aus `_internal/src`. `dist/` enthält das Ergebnis; `build/` enthält
Arbeitsdateien. Beides ist Git-ignoriert. Für einen neuen Kandidaten einen frischen
Checkout beziehungsweise einen eigenen Buildordner verwenden, damit alte
Artefakte nicht mit einem neuen Stand vermischt werden.

## 3. Genau das ZIP prüfen, das weitergegeben werden soll

Der folgende Ablauf verlangt einen noch nicht vorhandenen ZIP-Namen und einen
neuen Prüfungsordner. Die EXE wird aus dem wieder entpackten ZIP geprüft. Eine
Dateiauswahl aus dem Entwicklungsordner oder aus Forschungsdaten gehört nicht
in dieses Archiv.

```powershell
$zipPath = 'dist/QualitativeAnalyse-windows-x64.zip'
$checkDir = Join-Path $env:TEMP ('qualitative-package-' + [guid]::NewGuid().ToString('N'))
Compress-Archive -LiteralPath dist/QualitativeAnalyse -DestinationPath $zipPath -ErrorAction Stop
Expand-Archive -LiteralPath $zipPath -DestinationPath $checkDir -ErrorAction Stop
$packageDir = Join-Path $checkDir 'QualitativeAnalyse'
& (Join-Path $packageDir 'QualitativeAnalyse.exe') --package-check
if ($LASTEXITCODE -ne 0) { throw 'Paketidentität oder Quellloader passen nicht.' }
& ./.venv/Scripts/python.exe tests/smoke_frozen_ui.py --package $packageDir
if ($LASTEXITCODE -ne 0) { throw 'Frozen-Oberflächentest fehlgeschlagen.' }
& ./.venv/Scripts/python.exe tests/smoke_frozen_ui.py --package $packageDir --long-output
if ($LASTEXITCODE -ne 0) { throw 'Frozen-Langpfadtest fehlgeschlagen.' }
& ./.venv/Scripts/python.exe tests/smoke_frozen_workflow.py --package $packageDir
if ($LASTEXITCODE -ne 0) { throw 'Frozen-Workflowtest fehlgeschlagen.' }
Get-FileHash -LiteralPath $zipPath -Algorithm SHA256
```

Die beiden UI-Durchläufe prüfen den normalen Ergebnisordner und einen vom
Benutzer angegebenen Windows-Pfad über 300 Zeichen. Dazu ist keine Änderung der
Windows-Registrierung vorgesehen. Der Workflowtest prüft zusätzlich CSV-/XLSX-
Verarbeitung und Wiederaufnahme. Alle Smokes müssen erfolgreich enden; ihre
Prüfungen und Grenzen stehen direkt in
[smoke_frozen_ui.py](../tests/smoke_frozen_ui.py) und
[smoke_frozen_workflow.py](../tests/smoke_frozen_workflow.py). Ein grüner Source-Test
ersetzt diese Prüfung der tatsächlich gebauten EXE nicht. Den temporären
Prüfungsordner anschließend nach bestätigtem Prozessende entfernen. Eigene
Forschungsordner und technische Projektdaten gehören nicht zur Buildbereinigung.

## Identität, Grenzen und CI-Artefakt

Die Paketidentität verbindet die tatsächliche EXE-Prüfsumme mit den validierten
Buildinputs und den erfassten Ressourcen. Ein verändertes Paket darf alte
Checkpoints nicht stillschweigend weiterverwenden. `--package-check` prüft zudem
für zentrale Module den tatsächlichen `SourceFileLoader` und den Ursprung im
Paket. Diese Nachweise sind **keine digitale Herstellersignatur**, kein Nachweis
eines VM-Tests und keine Zusage bitidentischer Builds auf beliebigen Systemen.
Die Versionspins und das Manifest machen die Buildgrundlage nachvollziehbar;
Runnerimage, Toolchain und weitere Plattformdetails können Buildbytes beeinflussen.

Die Windows-CI verwendet die bereits im Projekt gepinnten Checkout-/Python-Setup-
Actions. Der zusätzliche Upload ist auf den offiziellen
[Commit von upload-artifact v7.0.1](https://github.com/actions/upload-artifact/commit/043fb46d1a93c77aae656e7c1c64a875d1fc6a0a)
festgelegt. Nur das nach Regression, Build, Entpacken und allen drei Frozen-Smokes
erfolgreich geprüfte ZIP wird für 14 Tage als Actions-Artefakt bereitgestellt.
Logs, Checkouts, Schlüssel und Forschungsdaten werden nicht als Artefakt hochgeladen.
