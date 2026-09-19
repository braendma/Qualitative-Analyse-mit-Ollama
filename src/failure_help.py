"""Local, fixed troubleshooting guidance; never copy raw model/log text into hints."""
import re


# Replay a known category through the same fixed guidance catalog. Persisted causes,
# actions, module names and log text are deliberately not trusted as display text.
_KIND_MARKERS = {
    'memory': 'CUDA out of memory', 'context': 'ContextBudgetError',
    'credentials': 'Status 401', 'quota': 'Status 429', 'connection': 'ConnectError',
    'response': 'LLMResponseError', 'reduction': 'Zwischenzusammenfassung',
    'call_budget': 'Synthese-Aufrufbudget', 'diagnostic_integrity': 'Diagnose abgelehnt',
    'diagnostic_output': 'Diagnoseausgabe existiert bereits',
    'diagnostic_sources': 'Modul coverage lieferte unvollständige Ergebnisse',
    'stability_integrity': 'Laufgrundlage', 'stability': 'Stabilitätsanalyse unvollständig',
    'sensitivity': 'Sensitivitätsanalyse unvollständig', 'unknown': 'Unbekannter Fehler',
}


def fixed_failure_help(kind):
    """Return only application-authored guidance for an untrusted stored kind."""
    marker = _KIND_MARKERS.get(kind) if isinstance(kind, str) else None
    return failure_help(marker or _KIND_MARKERS['unknown'])


def child_failure_guidance(manifest, planned_modules):
    """Project failed planned modules without copying child logs or input content."""
    from prompt_catalog import PROMPT_KEYS
    statuses = manifest.get('module_status', {})
    errors = manifest.get('module_errors', {})
    if not isinstance(statuses, dict):
        return []
    errors = errors if isinstance(errors, dict) else {}
    result = []
    for mid in planned_modules:
        if statuses.get(mid) != 'failed':
            continue
        error = errors.get(mid)
        kind = error.get('kind') if isinstance(error, dict) else None
        result.append({'module': mid if mid in PROMPT_KEYS else 'custom_module',
                       **fixed_failure_help(kind)})
    return result


def repetition_failure_marker(result):
    """Choose a fixed error category for the existing parent log classifier."""
    for condition in result.get('conditions', []):
        if condition.get('status') not in ('failed', 'interrupted'):
            continue
        for item in condition.get('failure_guidance', []):
            kind = fixed_failure_help(item.get('kind'))['kind']
            return 'Wiederholungsfehler [' + kind + ']. '
    return ''


def failure_help(text):
    value=str(text).lower()
    # Transport debug lines contain e.g. timeout=180 even after successful HTTP
    # calls. Classify the final traceback exception, not earlier prompt/log text.
    exceptions = re.findall(r'^\s*(?:[a-z_]\w*\.)*[a-z_]\w*(?:error|exception|timeout):[^\r\n]*',
                            value, flags=re.MULTILINE)
    if exceptions:
        value = exceptions[-1].strip()
    else:
        value = '\n'.join(line for line in value.splitlines() if '[debug]' not in line)
    repeated = re.search(r'wiederholungsfehler \[([a-z_]+)\]', value)
    if repeated and repeated[1] in _KIND_MARKERS:
        guidance = fixed_failure_help(repeated[1])
        guidance['cause'] = 'Eine kontrollierte Wiederholung ist fehlgeschlagen. ' + guidance['cause']
        guidance['action'] += ' Den Stabilitäts- oder Sensitivitäts-Teilbericht für Wiederholung und betroffenes Modul öffnen.'
        return guidance
    if any(x in value for x in ('sensitivitätsanalyse unvollständig', 'sensitivität benötigt', 'diagnostics.sensitivity', 'variante')):
        kind='sensitivity'
        cause='Die Vergleichsvarianten sind ungültig oder ihre Wiederholungen sind nicht vollständig.'
        action='1–9 ausdrücklich geänderte Varianten und 2–20 Wiederholungen pro Einstellung festlegen. Zielmodule samt Vorstufen aktivieren. Anbieterunterstützung, Kontextgrenzen und unveränderte Promptplatzhalter prüfen. Bei Abbruch den Sensitivitäts-Teilbericht und _sensitivity_repetitions lesen; unveränderten Lauf nach Behebung fortsetzen. Neue Einstellungen benötigen einen neuen Lauf.'
    elif any(x in value for x in ('stabilitätsanalyse unvollständig', 'stabilität benötigt', 'diagnostics.stability', 'wiederholungsziele', 'wiederholungszahl')):
        kind='stability'
        cause='Die kontrollierten Wiederholungen sind unvollständig oder ihre Auswahl ist ungültig.'
        action='Wiederholungszahl (2–20), ausgewählte Zielmodule und aktivierte Vorstufen prüfen. Bei einem Laufabbruch den Stabilitäts-Teilbericht und das Serienlog im Unterordner _stability_repetitions lesen. Nach Behebung ohne geänderte Einstellungen denselben Lauf fortsetzen; bei neuen Einstellungen einen neuen Lauf starten.'
    elif any(x in value for x in ('serienkonfiguration verändert', 'laufgrundlage', 'prozessende ist noch nicht sicher bestätigt', 'modellgewichte', 'laufzeitnachweis verändert')):
        kind='stability_integrity'
        cause='Die gemeinsame Laufgrundlage oder das sichere Ende einer Wiederholung kann nicht bestätigt werden.'
        action='Auf das bestätigte Prozessende warten und Originaldateien sowie Laufzeitnachweise prüfen. Keine Prüfsummen bearbeiten und keine parallele Wiederaufnahme erzwingen. Bei geändertem Code, Modell oder Einstellungen eine neue Serie in einem neuen Lauf anlegen.'
    elif any(x in value for x in ('diagnose abgelehnt', 'output-prüfsumme fehlt')):
        kind='diagnostic_integrity'
        cause='Die Diagnose kann Eingaben, Konfiguration oder Analyseergebnisse nicht dem gespeicherten Lauf zuordnen.'
        action='Unveränderte Originaldateien dieses Laufs und den Herkunftsnachweis prüfen. Geänderte Daten in einem neuen Lauf auswerten. Prüfsummen oder Prüfregeln nicht von Hand ändern. Ein höheres Modelllimit behebt dieses Problem nicht.'
    elif any(x in value for x in ('diagnoseausgabe existiert bereits', 'diagnoseausgaben dürfen')):
        kind='diagnostic_output'
        cause='Die gewählten Diagnoseausgaben würden vorhandene Dateien überschreiben.'
        action='Für den separaten Diagnoseexport neue Ausgabedateinamen oder einen neuen Zielordner wählen. Eingaben und vorhandene Ergebnisse erhalten.'
    elif any(x in value for x in ('modul coverage lieferte unvollständige', 'modul information_loss lieferte unvollständige', 'modul codebook_diagnostics lieferte unvollständige')):
        kind='diagnostic_sources'
        cause='Mindestens eine ausgewählte Analysequelle ist unvollständig oder nicht verifizierbar. Die Diagnose ist vorläufig.'
        action='Zuerst das vorher fehlgeschlagene Analysenmodul und dessen Fehlerhilfe prüfen. Nach Behebung den Lauf fortsetzen; die Diagnose wird erneut berechnet. Bei veränderten Quelldateien einen neuen Lauf anlegen. Das Antwortlimit der Diagnose muss nicht erhöht werden.'
    elif any(x in value for x in ('out of memory','cuda error','cuda allocation','nicht genügend speicher')):
        kind='memory'
        cause='Der Arbeitsspeicher oder Grafikspeicher reicht für diese Anfrage nicht aus.'
        action='Andere GPU-Anwendungen schließen und erneut prüfen. Falls nötig Parallelität reduzieren oder ein kleineres Modell wählen; geänderte Einstellungen erfordern einen neuen Lauf.'
    elif any(x in value for x in ('synthesiscallbudgeterror','synthese-aufrufbudget','hierarchische synthese erreicht max_calls')):
        kind='call_budget'
        cause='Das Aufrufbudget der Gesamtsynthese reicht nicht für die nächste Verdichtungsrunde oder notwendige Antwortreparaturen.'
        counts=re.search(r'mindestens (\d{1,7}) teilaufgaben, (\d{1,7}) aufrufe übrig',value)
        if counts:
            needed,left=map(int,counts.groups())
            cause+=f' Für diese Runde sind mindestens {needed} Teilaufgaben nötig; {left} Aufrufe sind im Budget übrig.'
        action='Unter „Erweiterte Modelleinstellungen“ das Aufrufbudget der Gesamtsynthese prüfen (YAML: llm.hierarchical_synthesis.max_calls). Ein höheres Limit erlaubt mehr Modellaufrufe und kann bei Cloud-Anbietern Kosten erhöhen. Danach einen neuen Lauf anlegen; unverändertes Fortsetzen hebt die Grenze nicht an. Vorhandene Ergebnisse bleiben erhalten. Ein größeres Kontextfenster allein behebt dieses Aufruflimit nicht.'
    elif any(x in value for x in ('contextbudgeterror','kontextfenster','kontextbudget','zu wenig kontext','kontext reicht','eingabe zu groß')):
        kind='context'
        cause='Die entstandene Eingabe und das Antwortbudget passen nicht in das Kontextfenster.'
        action='Kontext- und Speicherprüfung erneut ausführen. Ein größeres Kontextfenster nur bei ausreichender Modell- und Speicherkapazität verwenden; mit geänderten Einstellungen einen neuen Lauf starten. Bleibt der Fehler, Modulprotokoll prüfen und eine bereinigte Fehlermeldung melden.'
    elif any(x in value for x in ('kürzungsversuchen','zwischenzusammenfassung','zusammenfassungsstufen','personenverdichtung')):
        kind='reduction'
        cause='Die Modellantwort ließ sich nicht ausreichend verdichten.'
        action='Gesicherte Ergebnisse bleiben erhalten. Kontextprüfung und Modellwahl prüfen. Wiederholt sich der Fehler beim Fortsetzen, nicht unverändert immer neu starten; Modulprotokoll prüfen und eine bereinigte Fehlermeldung melden.'
    elif any(x in value for x in ('status 401','status 403','unauthorized','authenticationerror')):
        kind='credentials'
        cause='Der Anbieter hat die Anmeldung oder den Zugriff abgelehnt.'
        action='Beim gewählten Anbieter API-Schlüssel und Berechtigungen prüfen, gegebenenfalls den Schlüssel in der Oberfläche ersetzen. Schlüssel niemals in Fehlermeldungen oder Screenshots veröffentlichen.'
    elif any(x in value for x in ('status 429','rate limit','quota')):
        kind='quota'
        cause='Der Anbieter begrenzt derzeit die Anfragen oder das Kontingent ist erschöpft.'
        action='Kontingent und Anbieterstatus prüfen, erforderlichenfalls warten und diesen Lauf anschließend fortsetzen.'
    elif any(x in value for x in ('audit enthält ungültige gegenbeleg-ids', 'unbekannte oder doppelte audit-id', 'audit unvollständig')):
        kind='response'
        cause='Die Belegprüfung erhielt ungültige oder unvollständige Belegverweise vom Modell.'
        action='Gültige Teilprüfungen bleiben gespeichert. Bei einem einmaligen Fehler diesen Lauf fortsetzen. Wiederholt sich der Fehler, Modell und Unterstützung strukturierter Antworten prüfen und das bereinigte Modulprotokoll melden. Ungültige IDs nicht von Hand löschen oder die Prüfung deaktivieren.'
    elif any(x in value for x in ('llmresponseerror', 'jsondecodeerror',
                                 'thematische zuordnung bleibt nach korrektur', 'clusterantwort unvollständig')):
        kind='response'
        cause='Das Modell hat trotz Antwortkorrektur eine ungültige oder unvollständige Antwort geliefert.'
        action='Erfolgreiche Teilanalysen bleiben gespeichert. Bei einem einzelnen Modellfehler denselben Lauf fortsetzen. Bei wiederholten Fehlern Modell, Unterstützung strukturierter Antworten und Antwortlimit prüfen; geänderte Einstellungen benötigen einen neuen Lauf. Fehlende Zuordnungen nicht als negative Befunde zählen und die Vollständigkeitsprüfung nicht abschalten.'
    elif any(x in value for x in ('timeout','timed out','connection','connecterror','llmtransporterror','nicht erreichbar')):
        kind='connection'
        cause='Eine Modellanfrage konnte nicht rechtzeitig abgeschlossen oder die Verbindung nicht hergestellt werden.'
        action='Ollama beziehungsweise den gewählten Anbieter und die Verbindung prüfen. Nach Behebung diesen Lauf fortsetzen. Bei wiederholten Zeitüberschreitungen Speicherbedarf und Parallelität prüfen.'
    elif any(x in value for x in ('llmresponseerror','jsondecodeerror','unvollständige ergebnisse','outputs fehlen','alten output')):
        kind='response'
        cause='Das Modul hat keine vollständige, gültige Antwort oder Ergebnisdatei erzeugt.'
        action='Das Modulprotokoll prüfen. Antwortlimit und Kontext gemeinsam kontrollieren; Änderungen erfordern einen neuen Lauf. Bei einmaligem Modellfehler kann Fortsetzen helfen.'
    else:
        kind='unknown'
        cause='Das Modul konnte nicht erfolgreich abgeschlossen werden; die genaue Ursache steht im Protokoll.'
        action='Laufprotokoll herunterladen und die letzte Fehlermeldung des Moduls prüfen. Vor dem Teilen Forschungsinhalte, lokale Pfade und Zugangsdaten entfernen. Erfolgreiche Module bleiben gespeichert.'
    return {'kind':kind,'cause':cause,'action':action,
            'resume_note':'Fortsetzen verwendet die ursprünglichen Eingaben und Einstellungen. Nach deren Änderung einen neuen Lauf anlegen.'}


class ModuleFailure(RuntimeError):
    def __init__(self,message,diagnostic):
        super().__init__(message)
        self.diagnostic=diagnostic
