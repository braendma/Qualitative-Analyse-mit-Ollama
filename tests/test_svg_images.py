import base64
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from svg_images import passive_svg
from html_report import build_html_report
from plot_core import plot_clusters
from coding_agreement_core import save_confusion_png


class SvgTests(unittest.TestCase):
    def test_active_external_and_raster_svg_rejected(self):
        for content in ('<script>alert(1)</script>', '<image href="data:image/png;base64,AAAA"/>',
                        '<use href="https://example.com/a.svg#x"/>', '<g onclick="bad()"/>',
                        '<style>@import "https://example.com";</style>', '<path style="fill:url(https://example.com)"/>',
                        '<foreignObject/>'):
            with self.subTest(content=content),self.assertRaises(ValueError):
                passive_svg(('<svg xmlns="http://www.w3.org/2000/svg">'+content+'</svg>').encode())
        with self.assertRaises(ValueError):passive_svg(b'<!DOCTYPE svg [<!ENTITY x "bad">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>')

    def test_both_plot_types_are_vectors_and_html_prefers_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            png=Path(plot_clusters('Category','Factor',[{'cluster_name':'Example','segments':['one']}],
                pd.DataFrame([{'_SegmentID':'one','Dokumentname':'P1'}]),out_dir=root))
            self.assertTrue(png.is_file());svg=png.with_suffix('.svg');self.assertTrue(svg.is_file())
            self.assertNotIn(b'<image',passive_svg(svg.read_bytes()))
            matrix=root/'confusion.png';self.assertTrue(save_confusion_png(['A','B'],[[2,1],[0,3]],matrix))
            self.assertNotIn(b'<image',passive_svg(matrix.with_suffix('.svg').read_bytes()))
            (root/'report.md').write_text(f'![Example]({png.name})\n',encoding='utf-8')
            modules=[{'id':'plot','name':'Plot','report':{'markdown':'report.md'}}]
            html=build_html_report(root,modules,'now').read_text(encoding='utf-8')
            data=json.loads(re.search('id="report-data">(.*?)</script>',html,re.S)[1])
            self.assertTrue(next(iter(data['images'].values())).startswith('data:image/svg+xml;base64,'))
            # Invalid optional SVG must not remove the usable PNG fallback.
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>')
            html=build_html_report(root,modules,'now').read_text(encoding='utf-8')
            data=json.loads(re.search('id="report-data">(.*?)</script>',html,re.S)[1])
            self.assertTrue(next(iter(data['images'].values())).startswith('data:image/png;base64,'))
            self.assertTrue(data['warnings'])

    def test_svg_artifacts_have_no_duplicate_windows_paths(self):
        from local_app import App
        from test_local_app import settings
        from runtime_support import atomic_json
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Demo',True)['id'];app.save(pid,settings(app))
            folder=app.project_dir(pid)/'jobs'/('a'*20);run=folder/'runs'/'example';(run/'plots').mkdir(parents=True)
            (run/'plots/chart.png').write_bytes(b'png fixture')
            (run/'plots/chart.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
            (run/'clusterer_output.md').write_text('![Plot](plots/chart.png)')
            atomic_json(run/'workflow_manifest.json',{'status':'success','completed_steps':['clusterer']})
            cfg=app.project_dir(pid)/'revisions'/app.project(pid)['revision']/'config.yaml'
            atomic_json(folder/'job.json',{'id':'a'*20,'created':1,'status':'success','config':str(cfg),'modules':[]})
            files=app.jobs(pid)[0]['files']
            self.assertEqual([p for p in files if p.endswith('.svg')],['plots/chart.svg'])
