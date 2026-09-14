import copy
import unittest
from synthesis_material import validate_source_material
from test_thematic_memberships import fixture
from test_thematic_adapters import summary
from test_thematic_meta_adapter import meta_fixture
from test_thematic_person_adapters import fixture as person_fixture
from test_thematic_comparison_adapter import comparison_fixture
from test_thematic_contrast_adapter import contrast_fixture
from test_thematic_relation_adapter import relation_fixture


def module_sources():
    """Independent real-normalized adapter fixtures with actual required inputs."""
    material,swot,meta=meta_fixture()
    yield 'meta_swot',material,{'swot':swot,'meta_swot':meta}
    material,persons,ambiguity=person_fixture()
    yield 'person_analysis',material,{'person_analysis':persons}
    yield 'ambiguity_analysis',material,{'person_analysis':persons,'ambiguity_analysis':ambiguity}
    material,persons,comparison=comparison_fixture(reduced=True)
    yield 'person_comparison',material,{'person_analysis':persons,'person_comparison':comparison}
    material,persons,comparison,contrast=contrast_fixture(reduced=True)
    yield 'contrast_analysis',material,{'person_analysis':persons,'person_comparison':comparison,'contrast_analysis':contrast}
    material,clusters,summaries,relation=relation_fixture()
    yield 'relation_analysis',material,{'clusterer':clusters,'summarizer':summaries,'relation_analysis':relation}


def audit_fixture():
    """Use the actual audit-item builder, including real persons/source refs."""
    from evidence_audit_core import build_audit_items
    from meta_swot_core import flatten_findings
    material,swot,meta=meta_fixture()
    finding_lookup={row['finding_id']:row for rows in flatten_findings(swot).values() for row in rows}
    items=build_audit_items(meta,finding_lookup,swot['segment_metadata'])
    for row in items:
        row['gegenbelege']=[]
        row['belegbeispiele']=[{'segment_id':sid,'text':material['units'][material['segment_index'][sid]['unit_id']]['text']} for sid in row['segment_ids'][:3]]
    return material,{'processing_status':'completed','befunde':items}


class SynthesisMaterialTests(unittest.TestCase):
    def fixture(self):
        material, clusters = fixture()
        summaries = summary(clusters)
        return material, {'Alias': summaries}, {'Alias': {'module_id': 'summarizer'}}, {
            'clusterer': clusters, 'summarizer': summaries}

    def test_actual_named_source_uses_complete_original_upstream(self):
        args = self.fixture()
        before = copy.deepcopy(args)
        result = validate_source_material(*args)
        self.assertEqual(set(result), {'clusterer', 'summarizer'})
        self.assertEqual(args, before)

    def test_missing_or_changed_upstream_is_not_reconstructed_from_the_source(self):
        for change in ('missing', 'changed', 'unconfirmed', 'alias_payload', 'shortened'):
            with self.subTest(change=change):
                material, sources, bindings, upstream = self.fixture()
                if change == 'missing':
                    del upstream['clusterer']
                elif change == 'changed':
                    upstream['clusterer']['clusters'][0]['definition'] = 'Different original finding'
                elif change == 'unconfirmed':
                    material['person_basis'] = 'unconfirmed'
                elif change == 'alias_payload':
                    sources = copy.deepcopy(sources)
                    sources['Alias']['final_summary'] = 'Changed source'
                else:
                    del material['segment_index']['s3']
                with self.assertRaises(ValueError):
                    validate_source_material(material, sources, bindings, upstream)

    def test_unknown_module_does_not_get_counting_capability_from_its_label(self):
        args = self.fixture()
        args[2]['Alias']['module_id'] = 'custom_synthesis'
        with self.assertRaises(ValueError):
            validate_source_material(*args)

    def test_all_implemented_source_adapters_validate_actual_required_sources(self):
        for mid,material,upstream in module_sources():
            with self.subTest(module=mid):
                args=(material,{'Custom label':upstream[mid]},{'Custom label':{'module_id':mid}},upstream)
                before=copy.deepcopy(args)
                checked=validate_source_material(*args)
                self.assertEqual(set(checked),set(upstream))
                self.assertEqual(args,before)

    def test_missing_required_upstreams_cannot_be_rebuilt_from_selected_sources(self):
        from synthesis_material import UPSTREAMS
        for mid,material,upstream in module_sources():
            for required in UPSTREAMS.get(mid,()):
                with self.subTest(module=mid,missing=required):
                    source=upstream[mid];broken=copy.deepcopy(upstream);del broken[required]
                    with self.assertRaises(ValueError):
                        validate_source_material(material,{'Source':source},{'Source':{'module_id':mid}},broken)

    def test_all_source_adapters_reject_shortened_or_foreign_material(self):
        for mid,material,upstream in module_sources():
            for change in ('shortened_index','foreign_person'):
                with self.subTest(module=mid,change=change):
                    changed=copy.deepcopy(material)
                    if change=='shortened_index':del changed['segment_index'][next(iter(changed['segment_index']))]
                    else:
                        old=changed['persons'][0]
                        changed['persons']=['foreign' if person==old else person for person in changed['persons']]
                        for row in changed['units'].values():
                            if row['person']==old:row['person']='foreign'
                    with self.assertRaises(ValueError):
                        validate_source_material(changed,{'Source':upstream[mid]},{'Source':{'module_id':mid}},upstream)

    def test_weighted_sources_preserve_checked_original_basis_but_alias_must_match_actual_artifact(self):
        for mid,material,upstream in module_sources():
            with self.subTest(module=mid):
                binding={'Alias':{'module_id':mid}}
                expected=validate_source_material(material,{'Alias':upstream[mid]},binding,upstream)
                for value in upstream.values():value['analysis_perspective']={'text':'Additional weighted interpretation.'}
                self.assertEqual(validate_source_material(material,{'Alias':upstream[mid]},binding,upstream),expected)
                selected=copy.deepcopy(upstream[mid]);selected['analysis_perspective']['text']='Different actual artifact.'
                with self.assertRaises(ValueError):validate_source_material(material,{'Alias':selected},binding,upstream)

    def test_actual_audit_item_original_references_are_accepted(self):
        material,audit=audit_fixture()
        checked=validate_source_material(material,{'Audit alias':audit},{'Audit alias':{'module_id':'evidence_audit'}},{'evidence_audit':audit})
        self.assertEqual(set(checked),{'evidence_audit'})

    def test_audit_foreign_ids_persons_quotes_and_counterpersons_are_rejected(self):
        for change in ('segment','person','quote','counterperson'):
            with self.subTest(change=change):
                material,audit=audit_fixture();row=audit['befunde'][0]
                if change=='segment':row['segment_ids']=['foreign']
                if change=='person':row['personen']=['foreign']
                if change=='quote':row['belegbeispiele'][0]['text']='Not the original text.'
                if change=='counterperson':row['gegenbelege']=[{'person':'foreign','abweichung':'Countercase.'}]
                with self.assertRaises(ValueError):
                    validate_source_material(material,{'Audit':audit},{'Audit':{'module_id':'evidence_audit'}},{'evidence_audit':audit})


if __name__ == '__main__':
    unittest.main()
