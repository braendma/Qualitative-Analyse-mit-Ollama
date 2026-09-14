"""Semantic relation topics, strictly separate from existing-code co-occurrence."""
from copy import deepcopy

from runtime_support import fingerprint
from relation_selection import validate_relation_selection
from relation_cooccurrence import count_code_path_cooccurrences
from thematic_adapters import _require, _nonempty
from thematic_counts import _topics as validate_topics
from thematic_person_adapters import _unweighted


def build_relation_topics(material, payload, cluster_payload, summary_payload):
    """Prepare complete original-unit matrices for recorded relation assertions.

    Selected pair quotes nominate assertions, never their complete counting scope.
    Cross-person contrasts and incomplete assertions remain uncounted context.
    """
    original = _unweighted(payload)
    clusters = _unweighted(cluster_payload); summaries = _unweighted(summary_payload)
    validate_relation_selection(material, original, clusters, summaries)
    code_counts = count_code_path_cooccurrences(material)
    topics = []; links = {}; context = {'records': [], 'gesamteinordnung': original['gesamteinordnung'],
        'selection_summary': {key: original[key] for key in ('candidate_pair_count_total', 'candidate_pair_count_submitted',
            'candidate_pair_count_without_validated_relation', 'omitted_pair_count')}}
    scope = sorted(material['units'])
    for index, row in enumerate(original['beziehungen']):
        reason = ('cross_person_evidence' if row['bezugsebene'] != 'innerhalb_person' else
                  'incomplete_candidate' if not (_nonempty(row['thema']) and _nonempty(row['beschreibung'])) else None)
        if reason:
            context['records'].append({'section': 'beziehungen', 'source_record_index': index,
                                      'record': deepcopy(row), 'reason': reason})
            continue
        identity = {key: row[key] for key in ('thema', 'beschreibung', 'beziehungstyp', 'pfad_a', 'pfad_b')}
        tid = 'relation_' + fingerprint(identity)[:24]
        _require(tid not in links, 'Identische Relationsbehauptung ist mehrfach enthalten; Herkunft vor der Zuordnung klären.')
        definition = ('Thema: ' + row['thema'] + '\nCodepfad A: ' + row['pfad_a'] + '\nCodepfad B: ' + row['pfad_b'] +
            '\nQualitativer Beziehungstyp: ' + row['beziehungstyp'] + '\nVollständige Relationsbehauptung: ' + row['beschreibung'])
        topics.append({'topic_id': tid, 'label': row['thema'], 'definition': definition, 'kind': 'derived',
            'scope_unit_ids': scope,
            'inclusion': 'Prüfe jede vollständige Originaleinheit des gesamten bestätigten Korpus auf direkte Stützung oder ausdrücklichen Widerspruch zu dieser konkreten Relationsbehauptung. Eine sprachlich beschriebene Folge bleibt eine berichtete Beziehung, kein Kausalnachweis.',
            'exclusion': 'Bloße Nennung oder gemeinsame Codezuordnung von A und B genügt nicht als semantischer Relationsbeleg. A/B-Reihenfolge definiert keine Wirkungsrichtung; keine Richtung ergänzen, die nicht in der Behauptung steht. Getrennte Stellen oder unterschiedliche Personen nicht zu einem erfundenen Einzelbeleg verbinden. both bedeutet Stützung und Ablehnung derselben Behauptung, nicht A und B gemeinsam.'})
        links[tid] = {'module_id': 'relation_analysis', 'section': 'beziehungen',
            'pfad_a': row['pfad_a'], 'pfad_b': row['pfad_b'], 'relation_type': row['beziehungstyp'],
            'source_relation_id': row['relation_id'], 'source_pair_id': row['pair_id'],
            'source_record_index': index, 'qualitative_text': definition,
            'selected_evidence_segment_ids': sorted(set(row['segment_ids_a']) | set(row['segment_ids_b'])),
            'selected_evidence_segment_ids_a': list(row['segment_ids_a']),
            'selected_evidence_segment_ids_b': list(row['segment_ids_b']),
            'source_evidence_person_ids': list(row['beidseitig_belegte_personen']),
            'counting_basis': 'full_assignment_required',
            'counting_note': 'Ausgewählte A/B-Belege begründen nur die Kandidatenherkunft. Die neue direkte Relationszuordnung prüft alle Originaleinheiten aller bestätigten Personen; Code-Kovorkommen ist eine getrennte deskriptive Berechnung.'}
    context['counting_note'] = ('Gezählt werden nur vollständig beschriebene Relationskandidaten mit innerhalb einer Person belegter Herkunft, '
        'jeweils über das vollständige Originalmaterial. Personenübergreifende Gegenüberstellungen, unvollständige Kandidaten und Gesamteinordnung bleiben ungezählter Kontext. '
        'Ausgelassene Kandidatenpaare oder fehlende gültige Befunde sind keine nachgewiesenen Nullrelationen.')
    return {'schema_version': 1, 'basis_fingerprint': material['basis_fingerprint'],
        'source_fingerprint': fingerprint({'clusters': clusters, 'summaries': summaries, 'relation_analysis': original}),
        'source_cluster_fingerprint': fingerprint(clusters), 'source_summary_fingerprint': fingerprint(summaries),
        'assignment_origin': 'requires_full_thematic_assignment', 'topics': validate_topics(material, topics), 'assignments': None,
        'source_links': dict(sorted(links.items())), 'qualitative_source': deepcopy(original),
        'unassigned_context': context, 'code_cooccurrence': code_counts, 'model_calls': 0,
        'methodological_note': 'Semantische Beziehungen werden als konkrete analytische Behauptungen unabhängig im gesamten Originalkorpus geprüft. '
            'Gemeinsame Codezuordnungen sind weder semantische Belege noch Ursachen. Die Einzelstellenmatrix erfasst direkt stützendes oder widersprechendes Material; '
            'erst aus mehreren getrennten Stellen rekonstruierbare Zusammenhänge werden dadurch nicht vollständig erfasst. '
            'Ausgewählte Round-Robin-Belege und begrenzte Kandidatenpaare beschränken die Themenentdeckung; eine neue Matrix entdeckt keine zuvor ausgelassenen Relationskandidaten nachträglich.'}
