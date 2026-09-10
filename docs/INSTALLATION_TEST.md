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
