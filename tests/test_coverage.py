from pathlib import Path
import sys
import tempfile
import unittest
import json
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from coding_validation_common import Segment
from diagnostic_sources import make_snapshot
from coverage_core import analyze_coverage, render_coverage
from coverage_analysis import main as coverage_main
from runtime_support import atomic_json, file_hash


def fixture(selected=('s1',), scope='direct', stage_id='swot'):
    segments = [Segment('s1', 'eins zwei', 'A > X', 'P1', 'U1'),
                Segment('s2', 'eins zwei', 'B', 'P1', 'U1'),
                Segment('s3', 'drei vier fünf sechs', 'A > Y', 'P2', 'U2')]
    stage = {'status': 'available', 'warnings': [], 'records': [
        {'key': 'finding/0', 'scope': scope, 'kind': 'finding',
         'segment_ids': list(selected), 'persons': [], 'unresolved': [], 'text': 'synthetic'}]}
    return make_snapshot(segments, {stage_id: stage})


class CoverageTests(unittest.TestCase):
    def test_cli_requires_original_inputs_and_preserves_all_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'input.csv'
            source.write_text('ID;Person;Code;Text\ns1;P1;A;Originaltext\n', encoding='utf-8')
            config = root/'config.yaml'
            cfg = {'columns': {'segment_id': 'ID', 'person': 'Person', 'code': 'Code', 'segment': 'Text'},
                   'pipeline': {'modules': []}}
            config.write_text(yaml.safe_dump(cfg), encoding='utf-8')
            atomic_json(root/'workflow_manifest.json', {'provenance': {
                'config_sha256': file_hash(config), 'input_sha256': file_hash(source)}})
            base = ['--config', str(config), '--input-csv', str(source), '--run-dir', str(root)]
            out_json, out_md = root/'coverage.json', root/'coverage.md'
            outputs = ['--out-json', str(out_json), '--out-md', str(out_md)]
            original = source.read_bytes()
            coverage_main(base + outputs)
            self.assertEqual(json.loads(out_json.read_text())['model_calls'], 0)
            with self.assertRaisesRegex(ValueError, 'existiert bereits'):
                coverage_main(base + outputs)
            with self.assertRaisesRegex(ValueError, 'überschreiben'):
                coverage_main(base + ['--out-json', str(source), '--out-md', str(root/'new.md')])
            self.assertEqual(source.read_bytes(), original)
            source.write_text('ID;Person;Code;Text\ns1;P1;A;Verändert\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Diagnose abgelehnt'):
                coverage_main(base + ['--out-json', str(root/'fresh.json'), '--out-md', str(root/'fresh.md')])
            self.assertFalse((root/'fresh.json').exists())

    def test_person_passage_row_and_word_denominators(self):
        result = analyze_coverage(fixture())
        data = result['stages']['swot']['scopes']['direct']['distribution']
        self.assertEqual(data['material_units'], 2)
        self.assertEqual(data['input_coding_rows'], 3)
        self.assertEqual(data['selected_units'], 1)
        person = data['by_person'][0]
        self.assertEqual(person['material_share'], .5)
        self.assertAlmostEqual(person['material_word_share'], 1/3)
        self.assertEqual(person['evidence_share'], 1)
        self.assertEqual(data['by_person'][1]['evidence_share'], 0)
        categories = {(r['level'], r['code']): r for r in data['by_category']}
        self.assertAlmostEqual(categories[1, 'A']['material_share_at_level'], 2/3)
        self.assertEqual(categories[2, 'A > X']['material_share_at_level'], .5)
        self.assertEqual(categories[1, 'B']['selected_coding_rows'], 0)
        self.assertEqual(result['model_calls'], 0)

    def test_duplicate_reference_does_not_inflate_coverage(self):
        one = analyze_coverage(fixture(('s1',)))
        repeated = analyze_coverage(fixture(('s1', 's1')))
        self.assertEqual(one, repeated)
        both_codes = analyze_coverage(fixture(('s1', 's2')))
        data = both_codes['stages']['swot']['scopes']['direct']['distribution']
        self.assertEqual(data['selected_coding_rows'], 2)
        self.assertEqual(data['selected_units'], 1)

    def test_unavailable_invalid_and_unlinked_are_not_zero(self):
        for status in ('unavailable', 'invalid'):
            snap = fixture()
            snap['stages']['swot'].update(status=status, reason='not verified')
            self.assertEqual(analyze_coverage(snap)['stages']['swot']['scopes'], {})
        unknown = analyze_coverage(fixture(('unknown',)))
        self.assertIsNone(unknown['stages']['swot']['scopes']['direct']['distribution'])
        group = analyze_coverage(fixture((), 'source_group', 'overall_synthesis'))
        self.assertIsNone(group['stages']['overall_synthesis']['scopes']['source_group']['distribution'])

    def test_successful_empty_result_is_zero_with_undefined_share(self):
        snap = fixture()
        snap['stages']['swot']['records'] = []
        data = analyze_coverage(snap)['stages']['swot']['scopes']['direct']['distribution']
        self.assertEqual(data['unit_coverage'], 0)
        self.assertIsNone(data['by_person'][0]['evidence_share'])
        self.assertEqual(data['by_person'][0]['within_person_coverage'], 0)

    def test_rows_without_unit_ids_never_deduplicated_by_text(self):
        snap = fixture(('s1', 's2'))
        for row in snap['inputs'].values():
            row['unit_id'] = None
        result = analyze_coverage(snap)
        self.assertEqual(result['material']['material_units'], 3)
        self.assertEqual(result['unit_basis'], 'rows_with_explicit_passages_grouped')

    def test_inconsistent_passage_rejected(self):
        snap = fixture()
        snap['inputs']['s2']['person'] = 'P2'
        with self.assertRaisesRegex(ValueError, 'Passage-ID'):
            analyze_coverage(snap)

    def test_scope_separation_and_no_normative_quality_score(self):
        result = analyze_coverage(fixture(('s1',), 'source_group', 'overall_synthesis'))
        stage = result['stages']['overall_synthesis']['scopes']
        self.assertIsNone(stage['direct']['distribution'])
        self.assertEqual(stage['source_group']['distribution']['unit_coverage'], .5)
        text = render_coverage(result)
        self.assertIn('keine qualitative Güte', text)
        self.assertIn('Material zitierter Quellengruppen', text)
        self.assertIn('s3', text)
        self.assertNotIn('quality_score', result)


if __name__ == '__main__':
    unittest.main()
