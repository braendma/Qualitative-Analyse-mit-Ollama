"""Portable bounded plot components and their existing report references."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest

import matplotlib
matplotlib.use('Agg')
import pandas as pd

from plot_core import _plot_filename, _safe_filename, plot_clusters
from html_report import build_html_report


class PlotFilenameTests(unittest.TestCase):
    def test_existing_short_names_remain_identical(self):
        for cat, sub, facet in [('Category', 'Factor', None), ('Äußere Lage', 'A/B', ''),
                                ('', '', None), ('A', 'B', 'C > D')]:
            with self.subTest(values=(cat, sub, facet)):
                expected='_'.join(_safe_filename(str(v)) for v in (cat,sub,facet) if v is not None)+'_clusterdiagramm.png'
                self.assertEqual(_plot_filename(cat, sub, facet), expected)

    def test_long_original_hierarchies_and_empty_facets_have_distinct_hashes(self):
        prefix='Gemeinsamer langer Kategorienanfang ' * 12
        inputs=[(prefix+'A', 'Faktor', None), (prefix+'B', 'Faktor', None),
                (prefix+'A', 'Faktor', ''), (prefix+'A', 'Faktor', 'letzte Facette'),
                (prefix+'A/B', 'Faktor', None), (prefix+'A?B', 'Faktor', None)]
        names=[]
        for values in inputs:
            name=_plot_filename(*values);names.append(name)
            digest=hashlib.sha256(json.dumps(list(values),ensure_ascii=True,separators=(',',':')).encode()).hexdigest()[:16]
            self.assertTrue(name.endswith('__'+digest+'_clusterdiagramm.png'))
            self.assertEqual(name,_plot_filename(*values))
        self.assertEqual(len(names),len(set(names)))

    def test_utf16_and_utf8_limits_preserve_complete_characters(self):
        # Astral letters survive filename sanitization and occupy two UTF-16
        # units; three-byte BMP letters exercise the separate UTF-8 limit.
        for text in ('A'*10000, '\U00020000'*100, '漢'*100, 'ä'*300):
            name=_plot_filename(text,'Unterkategorie','Facette')
            self.assertLessEqual(len(name.encode('utf-16-le'))//2,120)
            self.assertLessEqual(len(name.encode('utf-8')),240)
            self.assertEqual(name.encode('utf-16-le').decode('utf-16-le'),name)
            self.assertNotIn('/',name);self.assertNotIn('\\',name)
            svg=Path(name).with_suffix('.svg').name
            self.assertLessEqual(len(svg.encode('utf-16-le'))//2,120)
            self.assertLessEqual(len(svg.encode('utf-8')),240)

    def test_exact_short_boundary_and_longer_name(self):
        tail='_B_clusterdiagramm.png'
        exact='A'*(120-len(tail))
        self.assertEqual(_plot_filename(exact,'B'),exact+tail)
        self.assertNotEqual(_plot_filename(exact+'A','B'),exact+'A'+tail)
        self.assertLessEqual(len(_plot_filename(exact+'A','B')),120)

    def test_long_png_and_svg_share_stem_and_html_uses_returned_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            category='Wiederholtes Thema mit vollständig erhaltenem Diagrammtitel '*4
            subcategory='Lange Unterkategorie zur Untersuchung der Zuordnung '*3
            frame=pd.DataFrame([{'_SegmentID':'SYN-1','Dokumentname':'SYN-P01'}])
            path=plot_clusters(category,subcategory,[{'cluster_name':'Künstlicher Befund','segments':['SYN-1']}],
                               frame,out_dir=root,facet='Mehrere Facetten')
            self.assertIsNotNone(path)
            png=Path(path);svg=png.with_suffix('.svg')
            self.assertEqual(png.name,_plot_filename(category,subcategory,'Mehrere Facetten'))
            self.assertTrue(png.is_file());self.assertTrue(svg.is_file())
            self.assertEqual(png.stem,svg.stem)
            self.assertIn('Wiederholtes Thema',svg.read_text(encoding='utf-8'))
            (root/'report.md').write_text(f'![Clusterdiagramm]({png.name})\n',encoding='utf-8')
            report=build_html_report(root,[{'id':'clusterer','name':'Cluster','report':{'markdown':'report.md'}}],'synthetic')
            data=json.loads(re.search('id="report-data">(.*?)</script>',report.read_text(encoding='utf-8'),re.S)[1])
            self.assertTrue(data['images'])
            self.assertTrue(all(value.startswith('data:image/svg+xml;base64,') for value in data['images'].values()))
            self.assertFalse(data['warnings'])


if __name__=='__main__':unittest.main()
