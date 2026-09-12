# Dokumente und Personen zuordnen

Eine Person kann in mehreren exportierten Dokumenten vorkommen, etwa wenn ein Interview in Teilen aufgenommen oder transkribiert wurde. Dokumentnamen sind deshalb nicht automatisch Personenkennungen.

1. Die CSV- oder XLSX-Datei hochladen und die Spalten für Text, Code und Dokumentkennung auswählen.
2. Im Bereich **Dokumente zu Personen zusammenfassen · Pflichtprüfung** die Vorschau öffnen. Sie listet die Dokumentkennungen und ihre Codierzeilen auf.
3. Zusammengehörigen Dokumenten dieselbe Personenkennung geben. Verschiedene Personen benötigen verschiedene Kennungen.
4. Die angezeigte Zahl der Personen prüfen und die Zuordnung ausdrücklich bestätigen. Erst danach können Eingaben gespeichert und der Lauf gestartet werden.

| Dokumentkennung aus dem Export | Personenkennung |
| --- | --- |
| Interview_A_Teil1 | P01 |
| Interview_A_Teil2 | P01 |
| Interview_B | P02 |

In diesem künstlichen Beispiel ergeben drei Dokumente zwei Personen. Sind bereits verlässliche Personen-IDs im Export enthalten, können diese unverändert bestätigt werden. Bei anderen Materialien steht die Kennung für den zu vergleichenden Fall, etwa einen Bildungsplan.

Die Anwendung speichert die bestätigte Zuordnung und zählt Personen danach. Originalspalten und Segment-IDs bleiben erhalten; für die Analyse werden eigene Personenspalten ergänzt. Eine neue Datei oder geänderte Spaltenzuordnung erfordert eine erneute Prüfung. Die Software errät keine Personenidentitäten aus Namen oder Ähnlichkeiten.

Ein bereits berechneter Bericht wird dadurch nicht nachträglich korrigiert. Bei falscher Personenzuordnung einen neuen vollständigen Lauf erstellen. Nach einer manuellen Codierprüfung können Folgeläufe die verifizierten Personenkennungen des Ursprungslaufs übernehmen, da dort nur Codes geändert werden.
