# v8-Beta als Python-Version auf dem Mac

Das gesamte macOS-Python-ZIP in einen neuen Programmordner entpacken. Die Starter in diesem Unterordner gehören zu den gemeinsamen Quellen der **8.0.0-beta.1**; die übrigen Dateien und Unterordner müssen zusammenbleiben. Es gibt kein Mac-Standalone.

1. Python 3.12 installieren.
2. `Einrichtung.command` öffnen. Sie erstellt `.venv-macos` im Programmordner und installiert die Python-Abhängigkeiten aus dem Internet. Modelle werden dabei nicht heruntergeladen.
3. `Start_Oberflaeche.command` öffnen. Das Terminal während der Nutzung geöffnet lassen und das Programm über die Oberfläche beenden. Läuft eine Analyse, zunächst kontrolliert pausieren oder abbrechen und den Abschluss abwarten.
4. Im Seitenmenü zwischen vorhandenen Exporten und Transkription/Codierung wechseln. Whisper und optional Sortformer v2 können ausdrücklich über die Modelleinstellungen zentral installiert werden. Audio wird lokal auf CPU verarbeitet; Text und Sprecherzuordnungen müssen geprüft werden.

Falls der Finder eine Startdatei nicht öffnet, im Terminal `bash ` eingeben, die `.command`-Datei hineinziehen und Enter drücken. Das funktioniert auch, wenn der ZIP-Entpacker die Ausführungsrechte nicht erhalten hat. Keine globalen Sicherheitseinstellungen ändern.

## Daten und Updates

Projekte liegen standardmäßig unter `~/Documents/Qualitative Analyse/Projekte`, zentrale Modelle daneben unter `Modelle`. Der Projektname und tatsächliche Speicherpfad werden in der Oberfläche angezeigt. Technische Appdaten liegen getrennt unter `~/Library/Application Support/QualitativeAnalyse`; ein ausdrücklich gewähltes `--data-dir` bleibt vorrangig. Cloud-Synchronisation wird nicht zugesichert.

Bei einem Programmupdate Projekte und Modelle bewahren und die Einrichtung im neuen Programmordner ausführen. Virtuelle Umgebungen nicht zwischen Rechnern kopieren. Ein laufender Analyselauf darf nicht durch einen Versionswechsel verändert werden; Wiederaufnahme erfordert unveränderte Quellen, Eingaben und Konfiguration.

## Prüfung und Grenzen

- Die GitHub-CI prüft Installation, Python-/JavaScript-Regressionen und HTTP-Start des veröffentlichten Commits. [Aktuelle Prüfungen](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/actions/workflows/macos.yml).
- Ein praktischer macOS-Audiotest, der Finder-Doppelklick und ein vollständiger lokaler Ollama-Analyselauf auf einem physischen Mac sind nicht abgenommen. Die Windows-Audioprüfung ist kein Ersatz dafür.
- Auf dem Mac eine gleichzeitige Analyse-Modellanfrage verwenden. Die NVIDIA-bezogene Parallelitätsprüfung kann Apple Unified Memory nicht zuverlässig beurteilen.
- API-/Telegram-Schlüssel gelten unter macOS nur für die Sitzung. Die dauerhafte verschlüsselte Speicherung verwendet Windows-DPAPI; eine macOS-Schlüsselbundanbindung ist nicht implementiert.
- Die vollständige Bereinigung verschachtelter Prozessaufsichten bei Diagnose-Wiederholungen bleibt eine separat praktisch zu prüfende Grenze. Keine fremden Prozesse beenden.
- Beide Audioschritte erlauben bis 120 Minuten/2 GiB. Sortformer unterstützt höchstens vier Stimmen; Labels sind keine bestätigten Personenidentitäten. Vollständige zweistündige Whisper-Verarbeitung und der gesamte lokale Granite-Nachtest einschließlich Serien sind noch offen.

Weitere Bedienung und Grenzen: [Beta-Anleitung](../../docs/BETA_V8.md).
