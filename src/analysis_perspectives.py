"""Pure opt-in perspective contract; no assignment, interpretation or model calls.

Capability describes methodological eligibility, not an implemented adapter.
Callers must explicitly provide implemented_modules before nondefault selections
can become executable. Nothing is migrated into the caller's configuration.
"""
import hashlib
import json


MODES = ('qualitative', 'frequency', 'both')

# id, eligible, reason. Keep this independent of UI labels and execution imports.
_CAPABILITIES = (
    ('clusterer', True, 'Personen und Passagen je expliziter Clusterzuordnung; Clusterzahl ist keine Personenzahl.'),
    ('summarizer', True, 'Geprüfte Clusterbasis kann die Interpretation informieren; freie Aussagen benötigen eigene Themenzuordnung.'),
    ('swot', True, 'Themenbreite kann Schwerpunkte informieren; explizite Äußerungen und analytische Ableitungen getrennt halten.'),
    ('meta_swot', True, 'Personen und Passagen über Mengenvereinigung zählen; neue Metathemen brauchen eine eigene geprüfte Zuordnung.'),
    ('person_analysis', True, 'Passagen innerhalb einer Person vergleichen; keine irreführende Personenquote im Einzelfall.'),
    ('person_comparison', True, 'Nur gemeinsame Muster über vollständiges Originalmaterial aller bestätigten Personen prüfen. Typen, Unterschiede, nicht zugeordnete Personen und Gesamtvergleich bleiben qualitativ.'),
    ('contrast_analysis', True, 'Globale Muster im gesamten Material und eindeutig gebundene Gegenfälle innerhalb ihrer Person prüfen. Nenner getrennt halten; unaufgelöste Bezüge und Typenspannungen bleiben qualitativ.'),
    ('relation_analysis', True, 'Vollständige konkrete Relationszuordnung und getrennte Codeüberschneidungen; keine automatische Kausalität oder gemeinsame Passage.'),
    ('ambiguity_analysis', True, 'Beide Positionen und ihre Personenüberschneidung erhalten; Gegenpositionen nicht verrechnen.'),
    ('overall_synthesis', True, 'Aussagen benötigen eigene Themenzuordnung; transitive Quellen allein sind keine vollständige Nennungshäufigkeit.'),
    ('code_verification', False, 'Codierüberprüfung prüft Passung und Alternativen; keine zusätzliche Häufigkeitsgewichtung der Entscheidung.'),
    ('blind_coding', False, 'Unabhängige Codierung ordnet Material zu; Häufigkeiten sollen diese Codierentscheidung nicht vorwegnehmen.'),
    ('coding_agreement', False, 'Codierübereinstimmung besitzt eigene definierte Kennzahlen und keinen zweiten Interpretationsmodus.'),
    ('review_queue', False, 'Die Prüfliste führt vorhandene Fälle zusammen; kein zusätzlicher generativer Interpretationsmodus.'),
    ('evidence_audit', False, 'Beleg- und Gegenbelegbreite ergänzen die Prüfung; Belegzahlen ergeben keine Wahrheitsquote oder zweite Auditperspektive.'),
    ('coverage', False, 'Coverage beschreibt bereits explizite Verteilungen und benötigt keine zweite Interpretationsperspektive.'),
    ('information_loss', False, 'Referenzänderungen und Prüfpunkte benötigen keine zusätzliche Häufigkeitsgewichtung.'),
    ('codebook_diagnostics', False, 'Die Codebook-Diagnostik besitzt definierte Prüfkennzahlen und ändert keine Interpretation durch einen zweiten Modus.'),
    ('stability', False, 'Stabilität vergleicht die gewählten Analysebedingungen; sie ist selbst keine weitere Interpretationsperspektive.'),
    ('sensitivity', False, 'Sensitivität vergleicht ausdrücklich unterschiedliche Einstellungen; kein eigener Häufigkeitsmodus.'),
)
_KNOWN = frozenset(row[0] for row in _CAPABILITIES)
_ELIGIBLE = frozenset(row[0] for row in _CAPABILITIES if row[1])


def _implemented(value):
    if not isinstance(value, (list, tuple, set, frozenset)) or any(not isinstance(x, str) for x in value):
        raise ValueError('Implementierte Perspektivmodule müssen ausdrücklich als Modul-ID-Sammlung angegeben werden.')
    if len(value) != len(set(value)) or not set(value) <= _ELIGIBLE:
        raise ValueError('Implementierungsfreigabe enthält doppelte oder ungeeignete Perspektivmodule.')
    return frozenset(value)


def perspective_capabilities(*, implemented_modules=()):
    """Return fresh public eligibility/availability metadata for all standard modules."""
    implemented = _implemented(implemented_modules)
    return [{'module_id': mid, 'eligible': eligible, 'reason': reason,
             'implemented': mid in implemented,
             'available_modes': list(MODES) if mid in implemented else ['qualitative'] if eligible else []}
            for mid, eligible, reason in _CAPABILITIES]


def normalize_analysis_perspectives(config, *, implemented_modules=()):
    """Validate the whole stored selection and return canonical effective modes.

    Null is allowed for the optional section only. Explicit entries are never
    silently ignored, even when the corresponding pipeline module is disabled.
    """
    implemented = _implemented(implemented_modules)
    if not isinstance(config, dict):
        raise ValueError('Die Konfiguration der Analyseperspektiven muss eine Zuordnung sein.')
    raw = config.get('analysis_perspectives')
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError('analysis_perspectives muss Modul-IDs auf qualitative, frequency oder both abbilden.')
    reasons = {mid: reason for mid, _, reason in _CAPABILITIES}
    for mid, mode in raw.items():
        if not isinstance(mid, str) or mid not in _KNOWN:
            raise ValueError('analysis_perspectives enthält eine unbekannte Modul-ID.')
        if mid not in _ELIGIBLE:
            raise ValueError('Für ' + mid + ' ist kein zusätzlicher Perspektivmodus vorgesehen. ' + reasons[mid])
        if not isinstance(mode, str) or mode not in MODES:
            raise ValueError('Analyseperspektive für ' + mid + ': qualitative, frequency oder both wählen.')
        if mode != 'qualitative' and mid not in implemented:
            raise ValueError('Die zusätzliche Analyseperspektive für ' + mid + ' ist noch nicht integriert.')
    return {mid: raw.get(mid, 'qualitative') for mid in sorted(_ELIGIBLE)}


def perspective_metadata(config, *, module_ids=None, implemented_modules=()):
    """Canonical effective modes for a project or selected module closure.

    Same modes produce the same identity independent of mapping order or explicit
    defaults. A changed active perspective changes this identity. Material/theme
    identities still need the surrounding existing run/checkpoint provenance.
    """
    modes = normalize_analysis_perspectives(config, implemented_modules=implemented_modules)
    if module_ids is not None:
        if (not isinstance(module_ids, (list, tuple, set, frozenset))
                or any(not isinstance(x, str) or x not in _KNOWN for x in module_ids)
                or len(module_ids) != len(set(module_ids))):
            raise ValueError('Die Perspektivprojektion benötigt eindeutige bekannte Modul-IDs.')
        modes = {mid: mode for mid, mode in modes.items() if mid in module_ids}
    payload = {'schema_version': 1, 'modes': modes}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return {**payload, 'fingerprint': hashlib.sha256(encoded).hexdigest()}


def perspective_effort(config, module_ids, *, implemented_modules=()):
    """Logical extra work, not a scheduler, request estimate or duration forecast.

    An assignment basis may reuse validated memberships or require new model
    classification. Until the adapter plans actual blocks, cells and request
    counts stay unknown. Both interpretations share one basis per module.
    """
    metadata = perspective_metadata(config, module_ids=module_ids, implemented_modules=implemented_modules)
    rows = []
    for mid, mode in metadata['modes'].items():
        counted = mode != 'qualitative'
        rows.append({'module_id': mid, 'mode': mode,
            'interpretation_outputs': ['qualitative', 'frequency'] if mode == 'both' else [mode],
            'shared_assignment_bases': 1 if counted else 0,
            'additional_frequency_interpretation_phases': 1 if counted else 0,
            'additional_assignment_cells': None if counted else 0,
            'additional_model_calls': None if counted else 0})
    counted_rows = [row for row in rows if row['mode'] != 'qualitative']
    return {'basis': 'fresh_run', 'perspective_fingerprint': metadata['fingerprint'], 'modules': rows,
            'additional_work_required': bool(counted_rows),
            'shared_assignment_bases': len(counted_rows),
            'additional_frequency_interpretation_phases': len(counted_rows),
            'additional_model_calls': None if counted_rows else 0,
            'limits': ['Zusätzliche Zuordnungen und Interpretationsanfragen sind erst nach der Modul- und Blockplanung bezifferbar.',
                       'Beide Perspektiven teilen je Modul dieselbe geprüfte Zuordnungsbasis; Modellanfragen werden dadurch nicht als doppelt oder kostenfrei unterstellt.',
                       'Diese Angaben betreffen nur Zusatzarbeit der Perspektive im frischen Lauf, nicht den Gesamtaufwand, Restzeit oder Kosten.']}
