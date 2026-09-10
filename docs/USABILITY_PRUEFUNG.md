# Usability-Prüfung · 0.3.0-dev

Geprüft wurden Einstieg, Datenimport, Spaltenzuordnung, ID-Vorbereitung, Modulauswahl, Ergebnisse, Wiederöffnung, Rückmeldungen und Hilfen mit künstlichen Daten.

## Im aktuellen Patch erledigt

- **Priorität 1:** HTML-Gesamtbericht automatisch erzeugen und dauerhaft beim Lauf öffnen/herunterladen; die Interaktion funktioniert auch in der geschützten Vorschau.
- **Priorität 1:** Zeilen-ID-Automatik erklären; fehlende Passage-IDs aus exakten Exportmerkmalen vorbereiten und gemeinsame Stellen gezielt bestätigen lassen. Keine Originale überschreiben.
- **Priorität 1:** Direkt erreichbares, offline verfügbares Handbuch mit Importbeispielen, Screenshots, Fehlerhilfe und vollständigem Prüf-/Folgelaufablauf.
- **Priorität 2:** Technische Einzeldateien einklappen und den Gesamtbericht hervorheben; Datei-/Zeilenzahlen klar beschriften.
- **Priorität 2:** Vollständige Kategoriehierarchie im Clusterbericht statt fehlender Ausprägungen und leerer Facetten.
- **Priorität 2:** HTTP/1.1 und mehr gleichzeitige HTTP-Verbindungen für bebilderte Hilfe erlauben; lokales Signet statt extern geladener Profilgrafik.

## Sinnvolle nächste Ausbaustufen

1. **Hohe Priorität: Projekt vollständig sichern und wiederherstellen.** Ein Assistent sollte Eingaben, Konfigurationen, Läufe und Prüfversionen gemeinsam sichern und Wiederherstellungen vorab prüfen. Derzeit muss der vollständige Datenordner gesichert werden.
2. **Hohe Priorität: Entwürfe für Projekteinstellungen.** Noch nicht validierte Feldänderungen deutlicher als ungespeichert markieren und beim Wechsel sichern/anbieten. Prüfentscheidungen besitzen bereits eine eigene automatische Speicherung.
3. **Mittlere Priorität: Laufnamen, Notizen und Vergleichsansicht.** Bei vielen Versionen ergänzend zum Datum die Fragestellung und veränderten Module erkennbar machen.
4. **Mittlere Priorität: Fehlermeldung mit direktem Sprung zur betroffenen Eingabe.** Beispielsweise unbekannten Code samt Datenzeile anzeigen und das passende Zuordnungsfeld fokussieren.
5. **Mittlere Priorität: Ältere Berichte per Knopf nacherstellen.** Der aktuelle Patch bietet dafür einen modellfreien CLI-Befehl. Eine integrierte Aktion sollte Originaldateien und Manifestversionen ebenso erhalten.

Diese weitergehenden Erweiterungen sind Vorschläge; sie wurden nicht als bereits vorhandene Funktionen dargestellt. Keine neue Beta-Veröffentlichung Bestandteil dieses Patches.
