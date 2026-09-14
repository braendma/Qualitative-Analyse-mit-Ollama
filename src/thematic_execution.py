"""Shared opt-in execution for the first thematic module adapters.

Adapters consume the original unweighted candidate fields. Selected perspectives
are separate outputs; no downstream module silently replaces its candidate basis
with an upstream weighted text. Each module interprets its own fixed topics.
"""
from copy import deepcopy
from coverage_core import markdown_escape as escape

from analysis_perspectives import MODES
from thematic_adapters import build_cluster_topics, build_summary_topics, build_swot_topics
from thematic_counts import count_topics
from thematic_interpretation import interpret_counts


ADAPTER_MODULES = ('clusterer', 'summarizer', 'swot', 'meta_swot',
                   'person_analysis', 'ambiguity_analysis')


def execute_perspective(module, mode, material, payload, params, *, cluster_payload=None,
                        swot_payload=None, person_payload=None, llm=None):
    """Build one shared matrix and named interpretations; leave inputs untouched.

This is an internal adapter boundary, not a user-configurable capability bypass.
Public configuration and UI enablement must be added at the application boundary.
The qualitative default has no new material, model or output requirements.
"""
    if module not in ADAPTER_MODULES or mode not in MODES:
        raise ValueError('Unbekannter Moduladapter oder unbekannte Analyseperspektive.')
    if mode == 'qualitative':
        return None
    if module == 'clusterer':
        prepared = build_cluster_topics(material, payload)
    elif module == 'summarizer':
        prepared = build_summary_topics(material, cluster_payload, payload)
    elif module == 'swot':
        prepared = build_swot_topics(material, payload)
    elif module == 'meta_swot':
        from thematic_meta_adapter import build_meta_swot_topics
        prepared = build_meta_swot_topics(material, payload, swot_payload)
    elif module == 'person_analysis':
        from thematic_person_adapters import build_person_topics
        prepared = build_person_topics(material, payload)
    else:
        from thematic_person_adapters import build_ambiguity_topics
        prepared = build_ambiguity_topics(material, payload, person_payload)
    assignments = prepared['assignments']
    origin = prepared['assignment_origin']
    if assignments is None:
        from thematic_assignment import execute_assignments
        assignments = execute_assignments(material, prepared['topics'], params, module=module, llm=llm)
        origin = 'full_scoped_model_assignment'
    counted = count_topics(material, prepared['topics'], assignments)
    qualitative = {tid: link['qualitative_text'] for tid, link in prepared['source_links'].items()}
    frequency = interpret_counts(material, counted, qualitative, params, module=module, llm=llm)
    outputs = {'frequency': frequency}
    if mode == 'both':
        outputs['qualitative'] = [{'topic_id': tid, 'interpretation': text} for tid, text in qualitative.items()]
    return {
        'schema_version': 1, 'module_id': module, 'selected_mode': mode,
        'candidate_source_fingerprint': prepared['source_fingerprint'],
        'candidate_basis': 'original_unweighted_findings',
        'downstream_contract': 'Original source fields remain the unweighted candidate basis; '
            'named interpretations are separate results of this module, never implicit replacements.',
        'assignment_origin': origin, 'counting': counted,
        'source_links': deepcopy(prepared['source_links']), 'interpretations': outputs,
        'unassigned_context': deepcopy(prepared.get('unassigned_context', {})),
        'methodological_note': 'Gezählt werden Zuordnungen im exportierten codierten Material. '
            'Eine vollständige technische Matrix ist keine menschliche Bestätigung. '
            'Personen, Passagen und Codierzeilen bleiben getrennt; seltene Gegenpositionen bleiben relevant. '
            + prepared.get('methodological_note', ''),
    }


def perspective_markdown(result):
    """Expose actual computed counts separately from model interpretation prose."""
    if result is None:
        return ''
    counted = result['counting']
    definitions = {t['topic_id']: t for t in counted['definitions']}
    outputs = result['interpretations']
    frequency = {r['topic_id']: r for r in outputs['frequency']}
    qualitative = {r['topic_id']: r for r in outputs.get('qualitative', [])}
    lines = ['\n\n## Häufigkeitsinformierte Analyseperspektive\n', escape(result['methodological_note']),
             '\nDie folgenden Zahlen werden aus den Zuordnungen berechnet. Die Interpretation darunter ist ein Modellvorschlag.']
    meanings = {'explicit': 'Äußerungsbezogene Themenzuordnung', 'derived': 'Materialbasis einer analytischen Ableitung',
                'membership': 'Clusterzuordnung; keine Zählung jeder Zusammenfassungsaussage'}

    def value(n):
        return 'nicht bestimmbar' if n is None else str(n)

    for row in counted['topics']:
        tid = row['topic_id']; topic = definitions[tid]; scope = row['scope']; cov = row['coverage']
        lines += ['\n### ' + escape(topic.get('label', topic['definition'])),
                  meanings[row['kind']],
                  f"\nBezugsmenge: {value(scope['person_count'])} Personen; {scope['unit_count']} Materialeinheiten "
                  f"({value(scope['passage_count'])} Passagen; {scope['coding_row_count']} Codierzeilen).",
                  f"Entschiedene Zuordnungen: {cov['decided_cells']} von {cov['expected_cells']}. "
                  f"Unklar: {cov['status_counts']['unclear']}; fehlgeschlagen: {cov['status_counts']['failed']}; "
                  f"ungeprüft: {cov['status_counts']['not_checked']}.",
                  '\n| Position | Beobachtete Personen | Vollständig bestimmte Personen | Beobachtete Einheiten | Vollständig bestimmte Einheiten |',
                  '|---|---:|---:|---:|---:|']
        for stance, label in [('supporting', 'Stützend'), ('opposing', 'Entgegenstehend'), ('both', 'Beide Positionen'), ('mentioned', 'Mindestens eine Position')]:
            c = row['counts'][stance]
            lines.append(f"| {label} | {value(c['observed_person_count'])} | {value(c['exact_person_count'])} | "
                         f"{c['observed_unit_count']} | {value(c['exact_unit_count'])} |")
        lines.append('\n„Beide Positionen“ bei Personen umfasst auch gegensätzliche Aussagen in verschiedenen Passagen. '
                     'Bei unvollständiger Zuordnung sind beobachtete Werte lediglich Untergrenzen der Modellzuordnung.')
        if scope['person_count'] == 1:
            lines.append('\nDiese Bezugsmenge enthält eine einzelne Person. Die Zahlen beschreiben die '
                         'Materialbreite innerhalb dieses Falles; eine Personenquote von 1/1 wäre keine '
                         'Mehrheit in der Untersuchungsgruppe.')
        link = result['source_links'][tid]
        if link.get('counting_note'):
            lines.append('\n' + escape(link['counting_note']))
        if result['module_id'] == 'ambiguity_analysis':
            lines.append('\nDie Seiten A und B werden unabhängig geprüft. „Beide Positionen“ in dieser '
                         'Tabelle bedeutet Stützung und Widerspruch zu dieser einen Seite, nicht die '
                         'gemeinsame Nennung von A und B. Die andere Seite ist nicht automatisch ihre Negation.')
        if tid in qualitative:
            lines += ['\n**Qualitative Perspektive**\n', escape(qualitative[tid]['interpretation'])]
        lines += ['\n**Häufigkeitsinformierte Perspektive**\n', escape(frequency[tid]['interpretation']),
                  '\n**Gegenpositionen**\n', escape(frequency[tid]['counterpositions']),
                  '\n**Grenzen**\n', escape(frequency[tid]['limitations'])]
    if result['unassigned_context']:
        lines.append('\nEine freie Gesamtzusammenfassung bleibt qualitativer Kontext. Ihre einzelnen Aussagen erhalten dadurch keine eigenen Nennungshäufigkeiten.')
    return '\n\n'.join(lines) + '\n'
