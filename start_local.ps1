param([switch]$Setup)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
try {
    if (-not (Test-Path -LiteralPath $taskPython)) {
        $taskLauncher = Get-Command py -ErrorAction SilentlyContinue
        $taskPrefix = @('-3')
        if (-not $taskLauncher) {
            $taskLauncher = Get-Command python -ErrorAction SilentlyContinue
            $taskPrefix = @()
        }
        if (-not $taskLauncher) { throw 'Python fehlt. Python 3.10 oder neuer installieren und danach Einrichtung.cmd starten.' }
        & $taskLauncher.Source @taskPrefix -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.10 oder neuer wird benoetigt.' }
        if ($Setup) {
            & $taskLauncher.Source @taskPrefix -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Die Python-Umgebung konnte nicht angelegt werden.' }
        } else {
            & $taskLauncher.Source @taskPrefix -c 'import pandas,numpy,matplotlib,yaml,ollama'
            if ($LASTEXITCODE -ne 0) { throw 'Python-Pakete fehlen. Einmal Einrichtung.cmd ausfuehren; dabei werden Pakete aus dem Internet installiert.' }
            & $taskLauncher.Source @taskPrefix -X utf8 local_app.py
            exit $LASTEXITCODE
        }
    }
    if ($Setup) {
        Write-Host 'Installiere Analyse-Pakete in die lokale .venv-Umgebung ...'
        & $taskPython -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Paketinstallation fehlgeschlagen. Internetverbindung und die Meldungen oben pruefen.' }
        Write-Host 'Einrichtung abgeschlossen. Jetzt Start_Oberflaeche.cmd oeffnen.'
    } else {
        & $taskPython -c 'import pandas,numpy,matplotlib,yaml,ollama'
        if ($LASTEXITCODE -ne 0) { throw 'Python-Pakete fehlen. Einrichtung.cmd erneut ausfuehren.' }
        & $taskPython -X utf8 local_app.py
        if ($LASTEXITCODE -ne 0) { throw 'Die Oberflaeche wurde mit einem Fehler beendet. Siehe Meldung oben.' }
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
