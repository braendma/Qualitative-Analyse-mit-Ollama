# Transkriptionsmodelle und Projekte

In Transkription und Codierung auf „Modell einrichten / ändern“ klicken. Whisper large-v3 oder small auswählen und den zentralen Download ausdrücklich starten. Öffentliche Modelldateien werden von Hugging Face geladen; Projekt- und Audiodaten werden dabei nicht übertragen. Prüfsummen werden kontrolliert. Abbrechen lässt vorhandene Modelle unverändert. Ein gescheiterter Download wird nicht automatisch fortgesetzt.

Die zentrale Bibliothek liegt unter Dokumente/Qualitative Analyse/Modelle. Bereits installierte Modelle mit model_manifest.json können stattdessen ausgewählt oder einmal zentral übernommen werden. „Für neue Projekte verwenden“ speichert die Auswahl; bestehende Projekte behalten ihre ausdrücklich gewählte Einstellung. Ollama-Modelle sind keine Whisper-Modelle.

Neue Projekte liegen bei normalem Start in Dokumente/Qualitative Analyse/Projekte. Der tatsächliche Projektordner wird in der Oberfläche angezeigt. Ein ausdrücklich gesetztes --data-dir behält seine eigene Projektablage. Ältere Projekte bleiben erreichbar; vorhandene Daten werden beim Programmstart nicht automatisch verschoben oder gelöscht. Modellgewichte und technische Einstellungen liegen getrennt von den Projekten.

Audio bis 120 Minuten und 2 GiB. Vollständige lange Spracherkennung benötigt entsprechende Rechenzeit; Sortformer v2 unterstützt ebenfalls bis 120 Minuten. Die automatische Zuordnung bleibt menschlich zu prüfen.
