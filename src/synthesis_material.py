"""Validate declared synthesis sources against confirmed complete original units.

The caller owns source-file and same-run artifact checks. This pure boundary uses
the existing module adapters; source labels or embedded ledgers cannot replace
the actual upstream results needed by those adapters.
"""
from runtime_support import fingerprint
from thematic_counts import _material, _material_index
from synthesis_inputs import SOURCE_MODULES


UPSTREAMS = {
    'summarizer': ('clusterer',),
    'meta_swot': ('swot',),
    'person_comparison': ('person_analysis',),
    'contrast_analysis': ('person_analysis', 'person_comparison'),
    'relation_analysis': ('clusterer', 'summarizer'),
    'ambiguity_analysis': ('person_analysis',),
}


def validate_source_material(material, source_payloads_by_label, bindings, upstream_payloads):
    """Return fingerprints of all source modules actually checked, without I/O."""
    from thematic_adapters import build_cluster_topics, build_summary_topics, build_swot_topics
    from thematic_person_adapters import build_person_topics, build_ambiguity_topics, _unweighted
    from thematic_meta_adapter import build_meta_swot_topics
    from thematic_comparison_adapter import build_person_comparison_topics
    from thematic_contrast_adapter import build_contrast_topics
    from thematic_relation_adapter import build_relation_topics
    _material(material)
    _material_index(material)
    if material['person_basis'] != 'confirmed':
        raise ValueError('Synthesezählung benötigt zuerst eine bestätigte Personenzuordnung.')
    if (not isinstance(source_payloads_by_label, dict) or not source_payloads_by_label
            or not isinstance(bindings, dict) or set(bindings) != set(source_payloads_by_label)
            or not isinstance(upstream_payloads, dict)):
        raise ValueError('Synthesezählung benötigt vollständige tatsächliche Quellen und ihre Modulzuordnung.')
    checked = {}
    def validate(mid):
        if mid in checked:
            return
        if mid not in SOURCE_MODULES or not isinstance(upstream_payloads.get(mid), dict):
            raise ValueError('Tatsächliche Analysevorstufe fehlt für die Synthesezählung: ' + str(mid))
        for required in UPSTREAMS.get(mid, ()):
            validate(required)
        original = _unweighted(upstream_payloads[mid])
        if mid == 'clusterer':
            build_cluster_topics(material, original)
        elif mid == 'summarizer':
            build_summary_topics(material, upstream_payloads['clusterer'], original)
        elif mid == 'swot':
            build_swot_topics(material, original)
        elif mid == 'meta_swot':
            build_meta_swot_topics(material, original, upstream_payloads['swot'])
        elif mid == 'person_analysis':
            build_person_topics(material, original)
        elif mid == 'person_comparison':
            build_person_comparison_topics(material, original, upstream_payloads['person_analysis'])
        elif mid == 'contrast_analysis':
            build_contrast_topics(material, original, upstream_payloads['person_analysis'], upstream_payloads['person_comparison'])
        elif mid == 'relation_analysis':
            if not isinstance(original.get('selection_provenance'), dict):
                raise ValueError('Der älteren Zusammenhangsanalyse fehlt der Auswahl- und Herkunftsnachweis. '
                                 'Einen neuen Lauf einschließlich Zusammenhangsanalyse mit aktivierter Syntheseperspektive erstellen; '
                                 'die Zusammenhangsanalyse selbst darf qualitativ bleiben.')
            build_relation_topics(material, original, upstream_payloads['clusterer'], upstream_payloads['summarizer'])
        elif mid == 'ambiguity_analysis':
            build_ambiguity_topics(material, original, upstream_payloads['person_analysis'])
        else:
            from coding_validation_common import Segment
            from diagnostic_sources import project_stage, make_snapshot
            segments = []
            for sid, row in material['segment_index'].items():
                unit = material['units'][row['unit_id']]
                passage = row['unit_id'][len('passage:'):] if unit['kind'] == 'passage' else None
                segments.append(Segment(sid, unit['text'], row['code_path'], unit['person'], passage))
            projected = project_stage(mid, original, segments=segments)
            snapshot = make_snapshot(segments, {mid: projected})
            if any(not row['valid'] for row in snapshot['stages'][mid]['records']):
                raise ValueError('Evidence-Audit verweist auf fehlendes oder fremdes Originalmaterial.')
            by_id = {segment.segment_id: segment for segment in segments}
            for row in original['befunde']:
                ids = row.get('segment_ids')
                if (not isinstance(ids, list) or any(not isinstance(sid, str) or sid not in by_id for sid in ids)
                        or len(set(ids)) != len(ids)):
                    raise ValueError('Evidence-Audit benötigt eindeutige Originalsegment-Verweise.')
                expected_people = sorted({by_id[sid].person for sid in ids})
                people = row.get('personen')
                if (not isinstance(people, list) or any(not isinstance(person, str) for person in people)
                        or sorted(people) != expected_people):
                    raise ValueError('Personen des Evidence-Audits passen nicht zu den ursprünglichen Belegen.')
                for key, expected in (('personen_count', len(expected_people)), ('segment_count', len(ids))):
                    if key in row and (type(row[key]) is not int or row[key] != expected):
                        raise ValueError('Evidence-Audit enthält abweichende Personen- oder Segmentzahlen.')
                quotes = row.get('belegbeispiele', [])
                if not isinstance(quotes, list):
                    raise ValueError('Evidence-Audit benötigt eine Liste unveränderter Originalzitate.')
                for quote in quotes:
                    if (not isinstance(quote, dict) or quote.get('segment_id') not in ids
                            or quote.get('text') != by_id[quote['segment_id']].text):
                        raise ValueError('Belegzitat im Evidence-Audit stimmt nicht mit dem Originalmaterial überein.')
                for counter in row['gegenbelege']:
                    for key in ('segment_ids', 'segment_ids_a', 'segment_ids_b'):
                        for sid in counter.get(key, []):
                            if counter.get('person') and by_id[sid].person != counter['person']:
                                raise ValueError('Gegenbeleg im Evidence-Audit ist einer fremden Person zugeordnet.')
        checked[mid] = fingerprint(original)
    for label, payload in source_payloads_by_label.items():
        binding = bindings[label]
        if not isinstance(binding, dict) or not isinstance(binding.get('module_id'), str):
            raise ValueError('Analytische Quelle benötigt eine eindeutige tatsächliche Modulzuordnung.')
        mid = binding['module_id']
        validate(mid)
        if fingerprint(payload) != fingerprint(upstream_payloads[mid]):
            raise ValueError('Ausgewählte Synthesequelle unterscheidet sich von ihrer geprüften Modulvorstufe.')
    return dict(sorted(checked.items()))
