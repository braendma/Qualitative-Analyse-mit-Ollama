"""New synthesis themes from explicit model selection and verified real sources.

Internal preparation only. Application provenance, execution and UI activation
must be wired before this becomes a selectable module perspective.
"""
from copy import deepcopy
from runtime_support import fingerprint
from synthesis_countability import validate_selection
from synthesis_provenance import validate_synthesis_provenance
from synthesis_material import validate_source_material
from thematic_counts import _topics
from thematic_person_adapters import _unweighted


NOTE = ('Die Auswahl zählbarer Synthesebefunde ist eine Modellklassifikation und nicht menschlich bestätigt. '
        'Gezählt wird die direkte Materialstützung vollständiger analytischer Aussagen, nicht deren wörtliche Nennung. '
        'Herkunftsquellen und Verdichtungsknoten sind keine Personen oder Belegzitate und begrenzen nicht den Nenner. '
        'Methoden-, Mengen- und Gruppenbehauptungen sowie gemischte oder unklare Aussagen bleiben ausdrücklich Kontext. '
        'Die Prüfung einzelner Materialeinheiten bestätigt keine allgemeine Kausalität oder übergreifende Verteilung.')


def build_overall_synthesis_topics(material, payload, source_payloads_by_label, selection, *, bindings, upstream_payloads):
    """Prepare one full-corpus topic matrix; selected source refs are provenance."""
    original = _unweighted(payload)
    if 'source_projection_fingerprints' not in original:
        raise ValueError('Diese ältere Synthese enthält keinen Quellinhaltsnachweis. Für die Häufigkeitsperspektive einen neuen Lauf erstellen.')
    checked = validate_source_material(material, source_payloads_by_label, bindings, upstream_payloads)
    provenance = validate_synthesis_provenance(original, source_payloads_by_label)
    classified = validate_selection(original, selection)
    scope = sorted(material['units'])
    topics = []; links = {}
    for row in classified['selected']:
        # Canonical source paths/content, not ephemeral N/L ids or sampled quotes,
        # define the provenance part of the topic identity.
        origins = {}
        for ref in row['source_references']:
            for path in provenance['references'][ref]['source_paths']:
                origins[fingerprint(path)] = path
        origin_paths = [origins[key] for key in sorted(origins)]
        identity = {'section': row['section'], 'definition': row['definition'],
                    'source_paths': origin_paths, 'scope_unit_ids': scope}
        tid = 'synthesis_' + fingerprint(identity)[:24]
        if tid in links:
            raise ValueError('Identischer Synthesebefund ist mehrfach enthalten; Herkunft vor der Zuordnung klären.')
        record = row['original_record']
        topics.append({'topic_id': tid, 'label': record.get('thema', record.get('aussage')),
            'definition': row['definition'], 'kind': 'derived', 'scope_unit_ids': scope,
            'inclusion': 'Prüfe die vollständige konkrete Syntheseaussage unabhängig an jeder vollständigen Originaleinheit aller bestätigten Personen auf unmittelbare Stützung oder ausdrücklichen Widerspruch. Kontext und Einschränkungen der Originalaussage erhalten.',
            'exclusion': 'Keine Materialstützung allein aus Herkunfts-IDs, Quellenanzahl, einer ähnlichen Themenüberschrift oder vorherigen Zählungen ableiten. Getrennte Aussagen oder Personen nicht zu erfundenen Einzelbelegen verbinden. Keine allgemeine Mengen-, Gruppen- oder Kausalbehauptung durch passende Einzelstellen bestätigen. Bei nicht prüfbarer gemischter Aussage unclear statt erzwungener Zuordnung verwenden.'})
        links[tid] = {'module_id': 'overall_synthesis', 'section': row['section'],
            'source_record_index': row['source_record_index'], 'source_candidate_id': row['candidate_id'],
            'qualitative_text': row['definition'], 'source_references': list(row['source_references']),
            'verified_source_paths': origin_paths, 'selection_origin': 'model_classification',
            'human_review_status': 'not_reviewed', 'classification': row['classification'],
            'classification_reason': row['reason'], 'counting_note': NOTE}
    context = {'records': deepcopy(classified['context']), 'counting_note': NOTE,
               'selection_origin': 'model_classification', 'human_review_status': 'not_reviewed',
               'candidate_count': len(classified['candidate_registry']), 'selected_count': len(topics)}
    return {'schema_version': 1, 'basis_fingerprint': material['basis_fingerprint'],
        'source_fingerprint': fingerprint({'synthesis': original, 'provenance': provenance,
                                           'checked_modules': checked, 'bindings': bindings, 'selection': selection}),
        'assignment_origin': 'requires_full_thematic_assignment', 'assignments': None,
        'topics': _topics(material, topics), 'source_links': dict(sorted(links.items())),
        'qualitative_source': deepcopy(original), 'unassigned_context': context,
        'selection': deepcopy(selection), 'source_provenance': provenance,
        'checked_source_modules': checked, 'model_calls': 0, 'methodological_note': NOTE}
