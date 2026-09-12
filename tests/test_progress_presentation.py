import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from progress_presentation import module_overview, phase_lines, request_age_lines


class PresentationTests(unittest.TestCase):
    def test_module_bar_survives_unknown_work_total_without_time_percentage(self):
        text='\n'.join(module_overview(14,15))
        self.assertIn('▰'*14+'▱',text)
        self.assertIn('14/15',text)
        self.assertNotIn('%',text)
        for value in (True,-1,101,float('nan'),'PRIVATE'):
            self.assertEqual(module_overview(value,15),[])

    def test_reduction_levels_do_not_look_like_module_restarts(self):
        labels={'reduction_level':'Verdichtungsebene'}
        first=phase_lines({'phase':'reduction_level','phase_level':1},labels)
        second=phase_lines({'phase':'reduction_level','phase_level':2},labels)
        self.assertIn('Verdichtungsebene 1',first)
        self.assertIn('Verdichtungsebene 2',second)
        self.assertIn('weitere Ebenen',' '.join(second))
        self.assertEqual(phase_lines({'phase':'PRIVATE'},labels),[])
        self.assertNotIn('PRIVATE',' '.join(phase_lines({'phase':'reduction_level','phase_level':'PRIVATE'},labels)))

    def test_request_age_only_for_valid_active_request(self):
        detail={'request_active':True,'request_started_at':820}
        self.assertEqual(request_age_lines(detail,1000),['Letzter Anfragestart vor 3 Minuten.'])
        self.assertEqual(request_age_lines({**detail,'active_requests':0},1000),[])
        for stamp in (True,float('nan'),float('inf'),1001,-1,'PRIVATE'):
            self.assertEqual(request_age_lines({**detail,'request_started_at':stamp},1000),[])


if __name__=='__main__':unittest.main()
