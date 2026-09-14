"""Qualitative effort guidance, never a runtime or model-call estimate.

Defaults apply only to the shipped ID/script pair. YAML may explicitly override
profiles for custom modules. Normalization must not modify users' source config.
"""

COST_CLASSES = ('NIEDRIG', 'MITTEL', 'HOCH', 'SEHR HOCH')

# Default profiles also support project configurations predating this metadata.
_DEFAULTS = {
    'clusterer': ('clusterer.py', 'HOCH',
        'für iterative Arbeit geeignet',
        'Gruppiert Textstellen je Codepfad; große Gruppen und lange Texte können mehrere Modellaufrufe erfordern.'),
    'code_verification': ('code_verification.py', 'HOCH',
        'für Zwischenvalidierung geeignet',
        'Prüft Codierungen am Text. Zahl und Länge der Codierzeilen sowie Reparaturversuche bestimmen den Aufwand.'),
    'blind_coding': ('blind_coding.py', 'HOCH',
        'für Zwischenvalidierung geeignet',
        'Ordnet Textstellen anhand des Kategoriensystems zu. Viele Textstellen und umfangreiche Codedefinitionen erhöhen den Aufwand.'),
    'coding_agreement': ('coding_agreement.py', 'NIEDRIG',
        'für Zwischenvalidierung geeignet',
        'Keine eigenen Modellaufrufe. Berechnet Übereinstimmungen aus Codierergebnissen; die benötigten Vorstufen verursachen zusätzlichen Aufwand.'),
    'summarizer': ('summarizer.py', 'MITTEL',
        'für iterative Arbeit geeignet',
        'Verdichtet die Cluster. Viele Cluster oder lange Textsammlungen erfordern zusätzliche Verarbeitungsschritte.'),
    'swot': ('swot.py', 'HOCH',
        'für Zwischenvalidierung geeignet',
        'Analysiert Cluster und ihre Belege. Viele Cluster, lange Eingaben und Reparaturversuche erhöhen den Aufwand.'),
    'meta_swot': ('meta_swot.py', 'MITTEL',
        'eher für finale Analyse',
        'Verdichtet vorhandene SWOT-Befunde. Umfangreiche Vorberichte können zusätzliche Aufteilungen erfordern.'),
    'person_analysis': ('person_analysis.py', 'HOCH',
        'für Zwischenvalidierung geeignet',
        'Analysiert die zugeordneten Personen. Viele Personen und umfangreiches Material je Person erhöhen den Aufwand.'),
    'person_comparison': ('person_comparison.py', 'HOCH',
        'eher für finale Analyse',
        'Vergleicht Personenanalysen; Anzahl und Umfang der Personenprofile bestimmen den Aufwand.'),
    'contrast_analysis': ('contrast_analysis.py', 'HOCH',
        'eher für finale Analyse',
        'Prüft Muster auf abweichende Fälle. Umfangreiche Personenanalysen und Vergleichsergebnisse erhöhen den Aufwand.'),
    'relation_analysis': ('relation_analysis.py', 'HOCH',
        'eher für finale Analyse',
        'Untersucht Zusammenhänge zwischen Kategorien. Viele Kategorien und Belege können zahlreiche Prüfungen erfordern.'),
    'ambiguity_analysis': ('ambiguity_analysis.py', 'HOCH',
        'für Zwischenvalidierung geeignet',
        'Prüft Personenanalysen auf gegenläufige Aussagen. Viele Personen und Befunde erhöhen den Aufwand.'),
    'evidence_audit': ('evidence_audit.py', 'SEHR HOCH',
        'eher für finale Analyse',
        'Prüft Befunde aus mehreren Analysen auf Gegenbelege. Viele Aussagen, lange Quellen und Reparaturversuche können den Aufwand stark erhöhen.'),
    'review_queue': ('review_queue.py', 'NIEDRIG',
        'für iterative Arbeit geeignet',
        'Keine eigenen Modellaufrufe. Erstellt die Prüfliste aus vorhandenen Ergebnissen. Die manuelle Prüfung und benötigte Vorstufen sind hier nicht eingerechnet.'),
    'overall_synthesis': ('overall_synthesis.py', 'MITTEL',
        'eher für finale Analyse',
        'Führt vorhandene Analyseberichte zusammen. Lange Vorberichte können zusätzliche Aufteilungen erfordern; ihre Erstellung ist nicht eingerechnet.'),
    'coverage': ('coverage_analysis.py', 'NIEDRIG',
        'für iterative Arbeit geeignet',
        'Keine zusätzlichen Modellaufrufe. Wertet nur abgeschlossene ausgewählte Analysen aus; aktiviert keine Vorstufen.'),
    'information_loss': ('information_loss_analysis.py', 'MITTEL',
        'für iterative Arbeit geeignet',
        'Keine zusätzlichen Modellaufrufe. Vergleicht Referenzen ausgewählter Analysen; Prüfpunkte müssen am Original beurteilt werden.'),
    'codebook_diagnostics': ('codebook_diagnostics.py', 'NIEDRIG',
        'für iterative Arbeit geeignet',
        'Keine zusätzlichen Modellaufrufe. Prüft das Kategoriensystem und ausgewählte Codierergebnisse; ändert keine Codes.'),
    'stability': ('stability_analysis.py', 'HOCH',
        'erst nach Stabilisierung von Material und Kategoriensystem empfohlen',
        'Zusätzliche vollständige Modellläufe mit getrennten Ausgaben. Wiederholungen und Ziele samt Vorstufen bestimmen den Zusatzaufwand.'),
    'sensitivity': ('sensitivity_analysis.py', 'SEHR HOCH',
        'erst nach Stabilisierung von Material und Kategoriensystem empfohlen',
        'Basis und jede Variante werden mehrfach neu ausgeführt, einschließlich benötigter Vorstufen. Unterschiede sind keine automatisch erkannten Fehler.'),
}


def normalize_cost_profile(module: dict) -> dict | None:
    """Validate explicit metadata or return an independent built-in default."""
    module_id = module['id']
    raw = module.get('cost_profile')
    if raw is None:
        default = _DEFAULTS.get(module_id)
        if default is None or module['script'] != default[0]:
            return None
        return dict(zip(('class', 'recommendation', 'note'), default[1:]))
    hint = f"Modul {module_id}: cost_profile benötigt class (NIEDRIG, MITTEL, HOCH oder SEHR HOCH), recommendation und optional note."
    if not isinstance(raw, dict):
        raise ValueError(hint)
    level = raw.get('class')
    recommendation = raw.get('recommendation')
    note = raw.get('note', '')
    if (level not in COST_CLASSES or not isinstance(recommendation, str)
            or not recommendation.strip() or not isinstance(note, str)):
        raise ValueError(hint)
    return {'class': level, 'recommendation': recommendation.strip(), 'note': note.strip()}
