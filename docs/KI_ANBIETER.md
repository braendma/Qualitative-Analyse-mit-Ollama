# KI-Anbieter und Datenfreigabe

Die Oberfläche startet mit `gdpr_relevant: true` und `provider: ollama_local`. Cloud-Schlüsselfelder werden erst nach Abwählen der DSGVO-Option freigeschaltet. Diese Entscheidung erfolgt durch die forschende Person: Das Programm prüft weder Rechtsgrundlagen noch anonymisiert es die Eingaben.

| Auswahl | API | Schlüsselvariable für die Kommandozeile |
|---|---|---|
| Ollama · lokal | HTTP-Loopback, Standardport 11434 | keine |
| Ollama Cloud | `https://ollama.com` | `OLLAMA_API_KEY` |
| OpenAI | Responses API | `OPENAI_API_KEY` |
| Anthropic | Messages API | `ANTHROPIC_API_KEY` |
| Hugging Face | Inference Providers, Chat Completions | `HF_TOKEN` |

In der Oberfläche werden feste Anbieteradressen verwendet. Eigene Gateways und weitere Anbieter sind noch nicht vorgesehen. Hugging Face kann an weitere Anbieter routen. Das Modell muss im jeweiligen API-Konto verfügbar sein; Namen direkt dort nachsehen. Chat-Abonnements und API-Zugang können unterschiedliche Abrechnung und Berechtigungen haben.

Schlüssel im separaten Feld speichern, ersetzen oder entfernen. Ohne Windows-Speicheroption bleiben sie nur im laufenden Serverprozess. Optional speichert Windows sie über DPAPI an das Benutzerkonto gebunden verschlüsselt. Die Datei `llm_keys.private.json` liegt außerhalb der Projektordner und gehört nicht in GitHub. Die Anwendung schreibt diese Schlüssel nicht in Argumentlisten, Projektkonfigurationen, Berichtsmetadaten oder Prüfexporte.

Die lokale Projektsperre wird auch vor Wiederaufnahme und Kategorienvorschlägen kontrolliert. Alte Cloud-Konfigurationen können sie nicht übergehen. Vor erneuter Aktivierung der Sperre einen aktiven Lauf abschließen oder nach dem aktuellen Modul pausieren. Bereits übermittelte Inhalte werden nicht zurückgerufen. Ein Anbieterwechsel erfordert einen neuen Lauf; die Wiederaufnahme bleibt an die bisherige Konfiguration gebunden.

## Lokaler Ollama-Status (Entwicklungsstand P03)

Die Anwendung startet auch ohne installierten oder laufenden Ollama-Server. Beim lokalen Anbieter prüft sie im Hintergrund die Erreichbarkeit; **Ollama erneut prüfen** aktualisiert den Status und die lokale Modellliste. Ein erreichbarer Server ohne Modell wird von einem nicht erreichbaren Server unterschieden. Alte Listenvorschläge werden bei fehlender Erreichbarkeit entfernt; der eingegebene Modellname bleibt erhalten. Netzwerkdetails und interne Fehlermeldungen werden nicht in die Statusanzeige übernommen.

Die Abfrage liest nur Metadaten des lokalen Servers und startet oder installiert nichts. Sie ersetzt weder die Speicherschätzung noch den ausdrücklich bestätigten kurzen Modelltest. Ist lokales Ollama nicht erreichbar oder ohne Modell, bleiben die Oberfläche, reine Diagnosen ohne modellabhängige Vorstufen und freigegebene Cloud-Anbieter verfügbar. Nur ausgewählte lokale Modellanalysen benötigen wieder einen erreichbaren Server mit installiertem Modell. Cloud-Freigabe und Schlüsselpflicht gelten unverändert; es gibt keinen automatischen Wechsel in die Cloud.

## Kontextbudget und Modellfenster

Das **Kontextbudget im Programm** ist eine konservative Rechengrenze. Es umfasst die Eingaben einschließlich Anweisungen und Schema, UTF-8-Bytes und Nachrichtenaufschläge sowie die reservierte Antwortlänge. Diese Abschätzung ist keine Messung durch den Tokenizer des Modells und kann früher begrenzen als dessen tatsächliches Fenster. Die Fehlerhilfe zeigt bei einem abgewiesenen vorbereiteten Request den konservativen Bedarf, die Antwortreserve und die eingestellte Grenze.

Bei lokalem Ollama wird `llm.num_ctx` zusätzlich als gewünschtes Modellfenster übergeben; Modellunterstützung und verfügbarer Speicher bleiben erforderlich. Bei Ollama Cloud wird `num_ctx` nicht an den Anbieter gesendet: Ein höheres Programmbudget vergrößert dessen Modellfenster nicht. Die tatsächliche Anbietergrenze gilt zusätzlich. Dasselbe Grundprinzip gilt für die übrigen Cloudadapter: Das Programmbudget ersetzt keine Prüfung der Modellgrenze beim Anbieter.

Es gibt keinen verlässlichen allgemeinen Mindestwert je Modul. Der Bedarf hängt unter anderem von Textmenge, Kodierungen, Themen, Anweisungen, Schema und Antwortreserve ab. Ein kurzer erfolgreicher Test liefert deshalb keine allgemeine Budgetempfehlung. Bei einer Abweisung Einstellungen und Materialumfang prüfen; weder Text noch Antwortreserve werden automatisch gekürzt. Geänderte Einstellungen benötigen einen neuen Lauf; bestehende Ergebnisse bleiben erhalten.

## Kommandozeile

Eine eigene YAML-Kopie erstellen. Beispiel für ausdrücklich freigegebene künstliche Daten:

```yaml
llm:
  provider: ollama_cloud
  gdpr_relevant: false
  host: https://ollama.com
  api_key_env: OLLAMA_API_KEY
  model: gemma4:31b
```

Die übrigen Einstellungen aus der vollständigen Konfiguration beibehalten. Den Schlüssel ausschließlich als Umgebungsvariable setzen. Bei den anderen Cloud-Anbietern `provider` und `api_key_env` gemäß Tabelle ändern und den dort verfügbaren Modellnamen eintragen. Die Transportadressen dieser Anbieter sind fest hinterlegt. Neue Konfigurationen sollten `provider` und `gdpr_relevant` ausdrücklich setzen.

Fehlt `gdpr_relevant`, bleibt die Kommandozeile grundsätzlich im privaten Modus.
Ein gesetzter Cloud-Anbieter oder ein geerbtes `OLLAMA_HOST=https://ollama.com`
erteilt für sich allein keine Datenfreigabe. Der Modelltransport wird dann vor
der Anfrage abgewiesen. Eine lokale Loopback-Adresse mit abweichendem Port über
`OLLAMA_HOST` bleibt möglich.

Eine enge Ausnahme erhält frühere Ollama-Cloud-YAMLs: Steht `host: https://ollama.com`
ausdrücklich in der Datei und ist der gewählte Anbieter Ollama Cloud, wird dies
weiterhin als bisherige Freigabe behandelt. Ein abschließender `/` und Port `443`
sind zulässig; Zugangsdaten in der Adresse, andere Pfade, Queries, Fragmente oder
Ports begründen diese Ausnahme nicht. `gdpr_relevant: true` sperrt Cloud auch bei
solchen alten Konfigurationen. Die Datei wird dabei nicht automatisch umgeschrieben.

### Schlüsselquellen und Unterprozesse

In der YAML darf `llm.api_key_env` ausschließlich einen Variablennamen wie
`OLLAMA_API_KEY` oder `MEIN_MODELL_KEY` enthalten, niemals den Schlüsselwert.
Eingebettete Felder wie `api_key`, `token`, `password` oder `credential` werden
auch verschachtelt abgelehnt. Das gilt vor dem normalen Runnerstart, bei
`--validate-only` und beim Vorbereiten einer Wiederholungsserie. Die Prüfung
bereinigt die Datei nicht still, sondern verlangt eine Korrektur vor der neuen
Laufausgabe. Schlüsselwerte nicht in andere YAML-Felder oder Prompttexte kopieren;
die Feldprüfung ist keine allgemeine Erkennung beliebiger Geheimnisse in Texten.

Vor regulären Modulprozessen und kontrollierten Unterläufen entfernt die
Anwendung die bekannten Anbieter-Schlüsselvariablen und den ausdrücklich
konfigurierten eigenen Schlüsselnamen aus der übernommenen Umgebung. Ein
Modellprozess erhält davon nur den benötigten Schlüssel seines ausgewählten
Cloud-Anbieters. Lokale und modellfreie Module erhalten keinen dieser Schlüssel.
Andere Laufzeitvariablen bleiben erhalten; beliebig anders benannte geheime
Variablen werden nicht allgemein erkannt. Unter Windows werden bekannte
Schlüsselnamen unabhängig von Groß-/Kleinschreibung behandelt; widersprüchliche
Aliaswerte für den benötigten Cloudschlüssel werden abgewiesen.

## API-Verhalten und Teststand

- OpenAI verwendet die Responses API mit `store: false`. Das ist keine Zusage über vollständige Löschung oder Aufbewahrungsfristen beim Anbieter. [Responses API](https://platform.openai.com/docs/api-reference/responses/create).
- Anthropic erhält Systemanweisungen über das separate `system`-Feld und Nachrichten über `messages`. [Messages API](https://platform.claude.com/docs/en/api/messages/create).
- Hugging Face verwendet den Chat-Completions-Endpunkt seiner Inference Providers. [Dokumentation](https://huggingface.co/docs/inference-providers/tasks/chat-completion).
- Ollama Cloud authentifiziert sich mit einem Bearer-Schlüssel. [Ollama-Authentifizierung](https://docs.ollama.com/api/authentication).

Temperatur und Thinking werden nur für Ollama übergeben. Die übrigen Adapter verwenden die Modellstandards. Antworten müssen vollständig und als sichtbarer Text vorhanden sein; gekürzte oder abgelehnte Antworten werden nicht als gültiges Ergebnis weiterverarbeitet. Authentifizierungsfehler werden nicht erneut versucht; vorübergehende Fehler nur begrenzt. Anbieter-Fehlertexte werden nicht ungefiltert ausgegeben, da sie sensible Inhalte enthalten können.

Stand 2026-09-10: Neuer Ollama-Cloud-Transport mit zwei künstlichen Textstellen, Clusteranalyse und Zusammenfassung erfolgreich geprüft (drei echte Anfragen). OpenAI, Anthropic und Hugging Face wurden mit kontrollierten API-Antworten, Fehlern, Kürzungen und Ablehnungen getestet; ein Live-Test mit Zugang zum jeweiligen Anbieter steht aus. Keine neuen SDK-Abhängigkeiten erforderlich. Diese Tests prüfen Funktion, nicht die wissenschaftliche Qualität eines Modells.
