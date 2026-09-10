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

Schlüssel im separaten Feld speichern, ersetzen oder entfernen. Ohne Windows-Speicheroption bleiben sie nur im laufenden Serverprozess. Optional speichert Windows sie über DPAPI an das Benutzerkonto gebunden verschlüsselt. Die Datei `llm_keys.private.json` liegt außerhalb der Projektordner und gehört nicht in GitHub. Der Kindprozess erhält nur den Schlüssel seines ausgewählten Anbieters; Schlüssel werden nicht in Argumentlisten, Projektkonfigurationen, Berichtsmetadaten oder Prüfexporte geschrieben.

Die lokale Projektsperre wird auch vor Wiederaufnahme und Kategorienvorschlägen kontrolliert. Alte Cloud-Konfigurationen können sie nicht übergehen. Vor erneuter Aktivierung der Sperre einen aktiven Lauf abschließen oder nach dem aktuellen Modul pausieren. Bereits übermittelte Inhalte werden nicht zurückgerufen. Ein Anbieterwechsel erfordert einen neuen Lauf; die Wiederaufnahme bleibt an die bisherige Konfiguration gebunden.

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

Die übrigen Einstellungen aus der vollständigen Konfiguration beibehalten. Den Schlüssel ausschließlich als Umgebungsvariable setzen. Bei den anderen Cloud-Anbietern `provider` und `api_key_env` gemäß Tabelle ändern und den dort verfügbaren Modellnamen eintragen. Die Transportadressen dieser Anbieter sind fest hinterlegt. Frühere CLI-Konfigurationen mit explizitem Ollama-Cloud-Host bleiben kompatibel; `gdpr_relevant: true` sperrt Cloud unabhängig davon. Neue Konfigurationen sollten beide Auswahlfelder ausdrücklich setzen.

## API-Verhalten und Teststand

- OpenAI verwendet die Responses API mit `store: false`. Das ist keine Zusage über vollständige Löschung oder Aufbewahrungsfristen beim Anbieter. [Responses API](https://platform.openai.com/docs/api-reference/responses/create).
- Anthropic erhält Systemanweisungen über das separate `system`-Feld und Nachrichten über `messages`. [Messages API](https://platform.claude.com/docs/en/api/messages/create).
- Hugging Face verwendet den Chat-Completions-Endpunkt seiner Inference Providers. [Dokumentation](https://huggingface.co/docs/inference-providers/tasks/chat-completion).
- Ollama Cloud authentifiziert sich mit einem Bearer-Schlüssel. [Ollama-Authentifizierung](https://docs.ollama.com/api/authentication).

Temperatur und Thinking werden nur für Ollama übergeben. Die übrigen Adapter verwenden die Modellstandards. Antworten müssen vollständig und als sichtbarer Text vorhanden sein; gekürzte oder abgelehnte Antworten werden nicht als gültiges Ergebnis weiterverarbeitet. Authentifizierungsfehler werden nicht erneut versucht; vorübergehende Fehler nur begrenzt. Anbieter-Fehlertexte werden nicht ungefiltert ausgegeben, da sie sensible Inhalte enthalten können.

Stand 2026-09-10: Neuer Ollama-Cloud-Transport mit zwei künstlichen Textstellen, Clusteranalyse und Zusammenfassung erfolgreich geprüft (drei echte Anfragen). OpenAI, Anthropic und Hugging Face wurden mit kontrollierten API-Antworten, Fehlern, Kürzungen und Ablehnungen getestet; ein Live-Test mit Zugang zum jeweiligen Anbieter steht aus. Keine neuen SDK-Abhängigkeiten erforderlich. Diese Tests prüfen Funktion, nicht die wissenschaftliche Qualität eines Modells.
