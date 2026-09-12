"""Local, fixed troubleshooting guidance; never copy raw model/log text into hints."""


def failure_help(text):
    value=str(text).lower()
    if any(x in value for x in ('out of memory','cuda error','cuda allocation','nicht genügend speicher')):
        kind='memory'
        cause='Der Arbeitsspeicher oder Grafikspeicher reicht für diese Anfrage nicht aus.'
        action='Andere GPU-Anwendungen schließen und erneut prüfen. Falls nötig Parallelität reduzieren oder ein kleineres Modell wählen; geänderte Einstellungen erfordern einen neuen Lauf.'
    elif any(x in value for x in ('synthesiscallbudgeterror','synthese-aufrufbudget','hierarchische synthese erreicht max_calls')):
        kind='call_budget'
        cause='Das Aufrufbudget der Gesamtsynthese reicht nicht für die nächste Verdichtungsrunde oder notwendige Antwortreparaturen.'
        import re
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
