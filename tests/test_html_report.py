import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from html_report import build_html_report, local_file, csp_hashes

class HtmlReportTests(unittest.TestCase):
    def test_offline_images_safe_payload_exact_csp_and_no_secret_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'plots').mkdir()
            (root/'plots/chart.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j9i8AAAAASUVORK5CYII='))
            text='# Beispiel\n</script><script>alert(1)</script>\n![Diagramm](plots/chart.png)\n![Zweites](plots/chart.png)\n![Extern](https://example.com/image.png)\n![Ausbruch](../secret.png)\n'
            (root/'module.md').write_text(text,encoding='utf-8')
            modules=[{'id':'a','name':'Modul','report':{'markdown':'module.md'}}]
            output=build_html_report(root,modules,'2026',config={'llm':{'model':'mock','api_key':'SECRET'},'paths':{'input_csv':'PRIVATE-PATH'}})
            html=output.read_text(encoding='utf-8')
            payload=json.loads(re.search(r'id="report-data">(.*?)</script>',html,re.S)[1])
            self.assertEqual(payload['sections'][0]['markdown'],text)
            self.assertEqual(len(payload['images']),1)
            self.assertTrue(all('\\' not in key for key in payload['images']))
            self.assertTrue(payload['warnings'])
            self.assertNotIn('SECRET',html);self.assertNotIn('PRIVATE-PATH',html)
            self.assertNotIn('</script><script>alert(1)',html)
            for tag in ('script','style'):
                for code in re.findall('<'+tag+'>(.*?)</'+tag+'>',html,re.S):
                    digest="'sha256-"+base64.b64encode(hashlib.sha256(code.encode()).digest()).decode()+"'"
                    self.assertIn(digest,csp_hashes()[tag]);self.assertIn(digest,html)

    def test_outside_paths_rejected_and_missing_sections_explained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('../outside','https://host/a','C:/outside','/outside','..\\outside'):
                with self.assertRaises(ValueError):local_file(root,name)
            output=build_html_report(root,[{'id':'a','name':'Fehlt','report':{'markdown':'missing.md'}}],'2026')
            self.assertIn('Berichtsteil fehlt',output.read_text(encoding='utf-8'))
