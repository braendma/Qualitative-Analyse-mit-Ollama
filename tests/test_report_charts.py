import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from plot_core import plot_clusters
from report_charts import chart_data


class ChartTests(unittest.TestCase):
    def test_unique_rows_and_missing_person_are_not_invented(self):
        captured=[]
        def capture(fig,*args,**kwargs):captured.append(fig)
        df=pd.DataFrame([{'_SegmentID':'one','Dokumentname':'P1'},{'_SegmentID':'two','Dokumentname':'P1'}])
        with tempfile.TemporaryDirectory() as tmp,patch.object(Figure,'savefig',capture):
            plot_clusters('Bereich','Faktor',[{'cluster_name':'Bekannt','segments':['one','one','two']},
                                            {'cluster_name':'Fehlende Zuordnung','segments':['SYN-UNKNOWN']}],df,out_dir=tmp)
            fig=captured[0];texts=[t.get_text() for ax in fig.axes for t in ax.texts]
            self.assertIn('2',texts);self.assertIn('nicht bestimmbar',texts)
            widths=[bar.get_width() for bar in fig.axes[0].patches]
            self.assertEqual(widths,[2,1,1])

    def test_person_category_cells_deduplicate_across_clusters_and_obey_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            payload={'segment_metadata':{'A':{'person':'P1'},'B':{'person':'P1'}},
                     'clusters':[{'code_path':'C','segments':['A','A','B']},{'code_path':'C','segments':['A']}]}
            (root/'clusters_output.json').write_text(json.dumps(payload))
            (root/'id_to_text.json').write_text(json.dumps({'A':'First','B':'Second'}))
            data=chart_data(root,[{'id':'clusterer'}])
            self.assertEqual(data['person_categories'],[{'person':'P1','code':'C','ids':['A','B']}])
            self.assertEqual(data['evidence']['B']['text'],'Second')
            self.assertEqual(chart_data(root,[{'id':'clusterer','enabled':False}]),{})
