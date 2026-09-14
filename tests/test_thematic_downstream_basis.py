"""Original downstream candidate prompts cannot absorb weighted extensions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contrast_analysis_core import build_contrast_analysis
from overall_synthesis_core import build_overall_synthesis, project_synthesis_source
from runtime_support import atomic_json
from test_thematic_person_adapters import fixture


class DownstreamBasisTests(unittest.TestCase):
    params={'model':'synthetic','num_ctx':32768,'max_tokens':1024,'partial_checkpoints':False,'parallel_workers':1}
    extension={'interpretations':{'frequency':'SYNTHETIC_WEIGHTED_ONLY ' * 6000}}

    def test_synthesis_projection_keeps_original_fields_and_input_unchanged(self):
        _,source,_=fixture(1)
        original=project_synthesis_source(source)
        source['analysis_perspective']=copy.deepcopy(self.extension)
        before=copy.deepcopy(source)
        self.assertEqual(project_synthesis_source(source),original)
        self.assertEqual(source,before)

    def test_relation_selection_and_code_counts_do_not_enter_synthesis_candidate_text(self):
        original={'beziehungen':[{'thema':'Beibehaltene Relation','beschreibung':'Originaler qualitativer Befund.'}]}
        enriched={**copy.deepcopy(original), 'selection_provenance':{'candidate_pairs':['SYNTHETIC_INTERNAL_ONLY']},
                  'analysis_perspective':{'code_cooccurrence':{'count':100}}, 'code_cooccurrence':{'count':100}}
        before=copy.deepcopy(enriched)
        self.assertEqual(project_synthesis_source(enriched),project_synthesis_source(original))
        self.assertEqual(enriched,before)

    def test_actual_contrast_requests_use_same_original_basis_for_both_upstream_modes(self):
        _,source,_=fixture(1)
        comparison={'typen':[],'gemeinsame_muster':[],'gesamtvergleich':'Künstlicher Vergleich.'}
        seen=[]
        def response(system,user,params):
            seen.append(user)
            return json.dumps({'dominante_muster':[],'negativfaelle':[],'spannungen_zwischen_typen':[],
                               'relativierungen':[],'gesamteinordnung':'Künstliche Einordnung.'})
        with tempfile.TemporaryDirectory() as tmp, patch('contrast_analysis_core.llm_contrast_analysis',side_effect=response), \
             patch('analysis_context.compact_context',side_effect=AssertionError('Unexpected extra context from weighted results')):
            root=Path(tmp)
            for weighted in (False,True):
                a,b=copy.deepcopy(source),copy.deepcopy(comparison)
                if weighted:a['analysis_perspective']=self.extension;b['analysis_perspective']=self.extension
                atomic_json(root/'persons.json',a);atomic_json(root/'comparison.json',b)
                before=[(root/name).read_bytes() for name in ('persons.json','comparison.json')]
                _,payload=build_contrast_analysis(root/'persons.json',root/'comparison.json',self.params,
                    {'contrast_analysis':{'system':'synthetic','user':'{data}'}},{})
                self.assertFalse(payload['input_reduction']['used'])
                self.assertEqual(before,[(root/name).read_bytes() for name in ('persons.json','comparison.json')])
        self.assertEqual(len(seen),2)
        self.assertEqual(seen[0],seen[1])
        self.assertNotIn('SYNTHETIC_WEIGHTED_ONLY',seen[1])

    def test_actual_synthesis_requests_and_source_nodes_preserve_original_basis(self):
        _,source,_=fixture(1)
        seen=[];nodes=[]
        def response(system,user,params):
            seen.append(user)
            return json.dumps({'kernergebnisse':[{'thema':'Thema','verdichtung':'Künstlicher Befund.','quellen':['Test']}],
                               'uebergreifende_muster':[],'spannungen_und_relativierungen':[],
                               'methodische_einordnung':[],'gesamtsynthese':'Künstlicher Befund.'})
        with tempfile.TemporaryDirectory() as tmp, patch('overall_synthesis_core.llm_overall_synthesis',side_effect=response), \
             patch('coding_validation_common.default_llm',side_effect=AssertionError('Unexpected reduction from weighted results')):
            path=Path(tmp)/'persons.json'
            for weighted in (False,True):
                value=copy.deepcopy(source)
                if weighted:value['analysis_perspective']=self.extension
                atomic_json(path,value);before=path.read_bytes()
                _,payload=build_overall_synthesis({'Test':path},self.params,
                    {'overall_synthesis':{'system':'synthetic','user':'{data}'}},{})
                self.assertEqual(path.read_bytes(),before)
                self.assertFalse(payload['hierarchical_reduction']['used'])
                nodes.append(payload['hierarchical_reduction'])
        self.assertEqual(len(seen),2)
        self.assertEqual(seen[0],seen[1])
        self.assertEqual(nodes[0],nodes[1])
        self.assertNotIn('SYNTHETIC_WEIGHTED_ONLY',seen[1])


if __name__=='__main__': unittest.main()
