# Start auf dem Mac

Dieses Unterverzeichnis enthält die Mac-Startdateien. Der Programmcode, die Beispiele und das Handbuch liegen gemeinsam im übergeordneten Programmordner. Bitte **das gesamte ZIP entpacken** und die Ordner zusammenlassen.

1. [Python 3.10 oder neuer](https://www.python.org/downloads/macos/) installieren. Empfohlen ist Python 3.12 oder 3.13. Für lokale Analysen zusätzlich [Ollama für macOS](https://docs.ollama.com/macos) installieren und öffnen. Ollama benötigt macOS 14 oder neuer; Apple Silicon unterstützt GPU-Beschleunigung, Intel-Macs verwenden die CPU.
2. **Einrichtung.command** doppelklicken. Sie legt im Programmordner `.venv-macos` an und installiert die Python-Pakete aus dem Internet. Es wird kein Modell heruntergeladen oder gestartet. Die Umgebung ist von der Windows-Umgebung getrennt.
3. **Start_Oberflaeche.command** doppelklicken. Die Oberfläche öffnet sich im Standardbrowser. Das Terminal während der Nutzung geöffnet lassen; zum Beenden dort **Ctrl+C** drücken.
4. In der Oberfläche ein Projekt anlegen und **Künstliche Beispieldaten laden** wählen. Dateivorschau und Eingabeprüfung funktionieren ohne Modell. Vor einem Analyselauf ein in Ollama installiertes Modell auswählen, das zum verfügbaren Speicher passt.

Falls macOS die Startdatei nicht öffnet, kannst du sie ausdrücklich im Terminal starten: `bash ` eingeben, die jeweilige `.command`-Datei aus dem Finder ins Terminal ziehen und Enter drücken. Das funktioniert auch, wenn ein ZIP-Entpacker die Ausführungsrechte nicht erhält. Nur Dateien aus dem hier verlinkten Repository verwenden. Es ist keine Änderung globaler Sicherheitseinstellungen erforderlich.

## Daten und Updates

Projekte und Ergebnisse liegen standardmäßig unter `~/.local/share/QualitativeOllama`. Im Finder **Gehe zu → Gehe zum Ordner** verwenden und diesen Pfad einfügen. Sie bleiben beim Austausch des Programmordners erhalten. Nach dem Entpacken einer neuen Version erneut deren Einrichtung starten. `.venv-macos` lässt sich nicht zwischen Rechnern verschieben; sie wird auf jedem Mac eingerichtet. Modelle verwaltet Ollama separat.

## Grenzen dieser Ausgabe

- Gemeinsamer Programmstand **0.3.4**, mit ergänzter Mac-Verpackung. Die Analysefunktionen entsprechen der Windows-Ausgabe.
- Auf dem Mac **eine gleichzeitige Modellanfrage** verwenden. Die automatische Speicherprüfung für mehrere Anfragen benötigt derzeit NVIDIA und kann Apple Unified Memory nicht zuverlässig beurteilen.
- API- und Telegram-Schlüssel sind unter macOS nur für die aktuelle Anwendungssitzung verfügbar. Die dauerhafte verschlüsselte Ablage verwendet unter Windows DPAPI; eine macOS-Schlüsselbundanbindung ist noch nicht implementiert.
- Der GitHub-Workflow prüft Einrichtung, Programmtests und den Start des lokalen Webservers auf macOS. Ein vollständiger Ollama-Analyselauf auf einem physischen Mac und der Finder-Doppelklick sind noch nicht geprüft. Den aktuellen Prüflauf findest du unter [GitHub Actions](https://github.com/braendma/Qualitative-Analyse-mit-Ollama/actions/workflows/macos.yml).

Die Bedienung erklärt das [Handbuch mit Bildern und Beispielen](../../docs/HANDBUCH.md). Die Datei `docs/HANDBUCH.html` lässt sich auch direkt im Browser öffnen. Einrichtung und Start benötigen keine Änderungen an YAML-Dateien.
