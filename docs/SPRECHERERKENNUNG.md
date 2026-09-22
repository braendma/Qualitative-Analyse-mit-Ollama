# Automatische Sprecherwechsel in v0.6.0 Beta

Whisper erzeugt den Text. Sortformer v2 erkennt anschließend Sprecherwechsel auf der CPU. Beide Schritte unterstützen Aufnahmen bis 120 Minuten und 2 GiB. Die tatsächliche Rechenzeit hängt vom Rechner ab.

Unter **Modell einrichten / ändern** im zentralen Installationsbereich **Sortformer v2 – Sprechererkennung bis 120 Minuten** auswählen und **Gewähltes Modell zentral herunterladen** anklicken. Ein vorhandenes Modell wird geprüft und wiederverwendet. Whisper bleibt dabei als Transkriptionsmodell ausgewählt.

Die gemeinsame Bibliothek liegt unter Dokumente/Qualitative Analyse/Modelle. Sortformer liegt darin im Ordner sortformer-v2-onnx. Für neue Aufnahmen wird das installierte Modell automatisch verwendet; vorhandene Transkripte werden dadurch nicht neu berechnet. Es werden nur öffentliche Modelldateien geladen, keine Audiodaten versendet.

Die Sprechererkennung unterstützt höchstens vier Stimmen. Labels sind Vorschläge innerhalb einer Aufnahme, keine identifizierten Personen. Hintergrundgeräusche, Überlappungen oder ähnlich klingende Stimmen können falsche Grenzen/Zuordnungen verursachen. Personen und schwierige Stellen am Audio prüfen. Die erwartete Sprecheranzahl ist eine Plausibilitätskontrolle und steuert das Modell nicht.

Beim manuellen Bearbeiten werden direkt benachbarte bestätigte Abschnitte derselben Person zusammengeführt, auch beim Öffnen eines älteren Arbeitsstands. Unterschiedliche Personen, Ausschlussregeln und ungeprüfte Zuordnungen bleiben getrennt. Wortfolge, ursprüngliche Audioanker und Quellzuordnungen bleiben erhalten; der alte Textstand bleibt im Versionsverlauf. Innerhalb eines Zuordnungsbereichs bewusst gesetzte Absätze bleiben erhalten.

Technik: begrenzte FFT-Blöcke und temporäre Audiodatei statt einer vollständigen Spektralanalyse im Arbeitsspeicher. Der Sprecher-Cache bleibt über die gesamte Aufnahme erhalten. Abbruch nutzt die vorhandene Prozessaufsicht; bei Fehlern der Sprechererkennung bleibt das ASR-Ergebnis erhalten.

Modell: NVIDIA Sortformer v2, ONNX-Konvertierung altunenes/parakeet-rs. Herkunft, feste Revision, SHA256 und Lizenzlinks im diarization_model_manifest.json; Modellgewichte sind nicht Teil der Programmpakete.
