"""Pure complete-scope Meta-SWOT topics; no inherited or summed frequencies."""
from copy import deepcopy

from meta_swot_core import flatten_findings
from runtime_support import fingerprint
from thematic_adapters import build_swot_topics, DIMENSIONS
from thematic_counts import _topics as validate_topics


def _require(condition):
    if not condition:
        raise ValueError('Meta-SWOT-Themen benötigen vollständige, unveränderte Original-SWOT-Quellen und eindeutige Verweise.')


def _ids(value, *, empty=False):
    _require(isinstance(value, list) and (empty or bool(value)))
    _require(all(isinstance(v, str) and bool(v.strip()) for v in value))
    _require(len(value) == len(set(value)))
    return sorted(value)


def _text(value):
    _require(isinstance(value, str) and bool(value.strip()))
    return value


def _number(value, expected):
    _require(type(value) is int and value == expected)


def build_meta_swot_topics(material, payload, source_swot_payload):
    """Prepare new derived topics for a full original-material assignment matrix.

    Both payloads' top-level analysis_perspective extensions are intentionally
    excluded from the common unweighted candidate basis. File/run provenance
    remains the caller's responsibility. Registry content and source membership
    are independently checked here. Finding counters are not stable topic IDs.
    """
    _require(isinstance(payload, dict) and isinstance(source_swot_payload, dict))
    _require(payload.get('processing_status', 'completed') == 'completed')
    original = {k: deepcopy(v) for k, v in payload.items() if k != 'analysis_perspective'}
    source = {k: deepcopy(v) for k, v in source_swot_payload.items() if k != 'analysis_perspective'}
    # Existing strict SWOT adapter validates all code paths, people, original
    # quote text and selected references before flatten_findings can skip rows.
    build_swot_topics(material, source)
    by_dimension = flatten_findings(source)
    registry = {row['finding_id']: row for dimension in DIMENSIONS for row in by_dimension[dimension]}
    _require(original.get('finding_registry') == registry)
    source_units = sorted(source['swot'])
    _require(_ids(original.get('source_units'), empty=True) == source_units)
    _number(original.get('source_unit_count'), len(source_units))
    _number(original.get('finding_count'), len(registry))
    _require(original.get('source_swot_created_at') == source.get('created_at'))
    dimensions = original.get('meta_swot')
    _require(isinstance(dimensions, dict) and set(dimensions) == set(DIMENSIONS))
    # A source reference nominates a candidate, not its final counting scope.
    # All original units are eligible to support or oppose each new meta-theme.
    scope = sorted(material['units'])
    topics, links = [], {}
    cross_total = 0
    for dimension in DIMENSIONS:
        section = dimensions[dimension]
        _require(isinstance(section, dict))
        expected = {row['finding_id'] for row in by_dimension[dimension]}
        seen, cross = set(), set()
        for section_name in ('uebergreifende_muster', 'einzelbefunde'):
            entries = section.get(section_name)
            _require(isinstance(entries, list))
            for entry in entries:
                fields = ({'thema', 'verdichtung', 'finding_ids', 'quellen', 'anzahl_quellen'}
                          if section_name == 'uebergreifende_muster' else
                          {'finding_id', 'thema', 'verdichtung', 'quelle', 'segment_ids'})
                _require(isinstance(entry, dict) and set(entry) == fields)
                label, analysis = _text(entry.get('thema')), _text(entry.get('verdichtung'))
                if section_name == 'uebergreifende_muster':
                    fids = _ids(entry.get('finding_ids'))
                else:
                    fid = _text(entry.get('finding_id'))
                    fids = [fid]
                _require(set(fids) <= expected and not (set(fids) & seen))
                seen.update(fids)
                sources = sorted({registry[fid]['source_id'] for fid in fids})
                if section_name == 'uebergreifende_muster':
                    _require(len(fids) >= 2 and len(sources) >= 2)
                    _require(_ids(entry.get('quellen')) == sources)
                    _number(entry.get('anzahl_quellen'), len(sources))
                    cross.update(fids)
                else:
                    finding = registry[fids[0]]
                    _require(entry.get('quelle') == finding['source_id'])
                    _require(label == finding['thema'] and analysis == finding['analyse'])
                    _require(_ids(entry.get('segment_ids')) == sorted(finding['segment_ids']))
                # Source signatures exclude order-dependent finding_ids. Same
                # text in a different source or SWOT dimension stays distinct.
                signatures = sorted(fingerprint({key: registry[fid][key]
                                    for key in ('source_id', 'thema', 'analyse')}) for fid in fids)
                identity = {'dimension': dimension, 'section': section_name,
                            'label': label, 'analysis': analysis, 'source_signatures': signatures}
                tid = 'meta_swot_' + fingerprint(identity)[:24]
                _require(tid not in links)
                topics.append({'topic_id': tid, 'label': label,
                    'definition': label + '\nAnalytischer Meta-Befund: ' + analysis,
                    'inclusion': 'Originalmaterial, das den konkreten analytischen Meta-Befund in dieser SWOT-Dimension stützt. '
                        'Ausdrücklich entgegenstehende Positionen als Gegenposition zuordnen.',
                    'exclusion': 'Bloße Erwähnung eines Quellthemas oder Zugehörigkeit zu einem Codepfad genügt nicht. '
                        'Fehlende Evidenz ist keine Ablehnung; keine nicht geäußerten Überzeugungen ableiten.',
                    'kind': 'derived', 'scope_unit_ids': list(scope)})
                links[tid] = {'module_id': 'meta_swot', 'dimension': dimension, 'section': section_name,
                    'thema': label, 'qualitative_text': analysis, 'finding_ids': sorted(fids),
                    'source_code_paths': sources, 'source_signatures': signatures,
                    'selected_evidence_segment_ids': sorted({sid for fid in fids for sid in registry[fid]['segment_ids']}),
                    'counting_basis': 'full_assignment_required',
                    'scope_basis': 'all_original_units_in_complete_swot_material',
                    'counting_note': 'Quellbereiche und Befunde sind keine Personen. Neue Meta-Themen benötigen eigene vollständige Zuordnungen; keine Addition oder unterstellte ODER-Union vorhandener Zähler.'}
        _require(seen == expected)
        stats = section.get('statistik')
        _require(isinstance(stats, dict))
        _number(stats.get('befunde'), len(expected))
        _number(stats.get('quellbereiche'), len({registry[fid]['source_id'] for fid in expected}))
        _number(stats.get('in_mehrquellenmustern'), len(cross))
        cross_total += len(cross)
    _number(original.get('findings_in_cross_source_patterns'), cross_total)
    return {'schema_version': 1, 'basis_fingerprint': material['basis_fingerprint'],
        'source_fingerprint': fingerprint({'meta_swot': original, 'swot': source}),
        'source_swot_fingerprint': fingerprint(source),
        'assignment_origin': 'requires_full_thematic_assignment',
        'topics': validate_topics(material, topics), 'assignments': None,
        'source_links': dict(sorted(links.items())), 'qualitative_source': deepcopy(original),
        'model_calls': 0,
        'methodological_note': 'Neue Meta-Befunde werden gegen sämtliche Originaleinheiten des ausgewerteten SWOT-Materials geprüft. '
            'Quellbereiche, Befundzahlen und ausgewählte Belege ersetzen keine Personen- oder Passagenzählung. '
            'Die vollständige Zuordnung prüft vorhandene Kandidaten, entdeckt aber nicht automatisch in der blockweisen Meta-Analyse übersehene Themen.'}
