"""Synthetic OOXML fixtures; no study data is needed or retained by these tests."""
import base64
import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from tabular_import import xlsx_csv
from local_app import App, csv_info
from test_local_app import settings


def fixture(sheets):
    """Minimal ZIP/XML input bytes, rather than a generated spreadsheet deliverable."""
    output = io.BytesIO()
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>')
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'+''.join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(sheets,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="{rel}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+'</Relationships>')
        for i, (_, rows) in enumerate(sheets,1):
            body = []
            for n, row in enumerate(rows,1):
                cells = []
                for col, value in enumerate(row):
                    address = chr(65+col)+str(n)
                    if isinstance(value, tuple):
                        cells.append(f'<c r="{address}"><f>{escape(value[0])}</f><v>2</v></c>')
                    else:
                        cells.append(f'<c r="{address}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>')
                body.append(f'<row r="{n}">'+''.join(cells)+'</row>')
            z.writestr(f'xl/worksheets/sheet{i}.xml', f'<worksheet xmlns="{ns}"><sheetData>'+''.join(body)+'</sheetData></worksheet>')
    return output.getvalue()


class SpreadsheetImportTests(unittest.TestCase):
    def test_incorrect_excel_dimension_does_not_truncate_rows(self):
        data=fixture([('Export',[['a','b'],['1','2'],['3','4']])])
        output=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as source,zipfile.ZipFile(output,'w') as target:
            for name in source.namelist():
                raw=source.read(name)
                if name.endswith('sheet1.xml'):
                    raw=raw.replace(b'<sheetData>',b'<dimension ref="A1:B1"/><sheetData>')
                target.writestr(name,raw)
        raw,_=xlsx_csv(output.getvalue())
        self.assertEqual(csv_info(raw)['count'],2)

    def test_long_csv_field_and_unclosed_quote(self):
        text='x'*150000
        self.assertEqual(csv_info(('a;b\n1;'+text+'\n').encode())['count'],1)
        with self.assertRaises(ValueError):csv_info(b'a;b\n1;"unclosed\n')

    def test_broken_sheet_xml_reports_readable_error(self):
        data=fixture([('Export',[['a','b'],['1','2']])]);output=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as source,zipfile.ZipFile(output,'w') as target:
            for name in source.namelist():
                raw=source.read(name)
                if name.endswith('sheet1.xml'):raw=raw.replace(b'</sheetData>',b'</broken>')
                target.writestr(name,raw)
        with self.assertRaisesRegex(ValueError,'XLSX'):xlsx_csv(output.getvalue())

    def test_text_quotes_newlines_ids_and_maxqda_columns(self):
        headers = ['Farbe','Kommentar','Dokumentgruppe','Dokumentname','Code','Anfang','Ende','Gewicht','Segment','Bearbeitet von','Bearbeitet am','Erstellt von','Erstellt am','Fläche','Abdeckungsgrad %']
        row = ['', '', 'Gruppe', 'Person_01', 'Organisation > Unterstützung', '1', '2', '0', '  Ein "Zitat"; mit Umlaut ä\nund zweiter Zeile.  ', '', '', '', '', '0', '0.2']
        raw, meta = xlsx_csv(fixture([('Export',[headers,row])]))
        self.assertEqual(list(csv.reader(io.StringIO(raw.decode()),delimiter=';')), [headers,row])
        self.assertEqual(csv_info(raw)['count'],1)
        self.assertEqual(meta['sheet'],'Export')

    def test_sheet_choice_no_silent_merging_and_bad_selection(self):
        data = fixture([('Erstes',[['a','b'],['1','2']]),('Zweites',[['a','b'],['3','4']])])
        raw, meta = xlsx_csv(data)
        self.assertIsNone(raw)
        self.assertTrue(meta['requires_sheet'])
        self.assertEqual(xlsx_csv(data,'Zweites')[0],b'a;b\n3;4\n')
        with self.assertRaisesRegex(ValueError,'existiert nicht'):xlsx_csv(data,'missing')

    def test_bad_headers_formula_empty_and_unheaded_data(self):
        for rows, message in [([['a','a'],['1','2']],'Spaltennamen'),([['Titel'],['a','b']],'Spaltennamen'),([['a','b'],[('1+1',),'text']],'A2'),([['a','b',''],['1','2','extra']],'ohne Überschrift')]:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError,message):
                xlsx_csv(fixture([('Export',rows)]))
        raw,_=xlsx_csv(fixture([('Export',[['a','b']])]))
        with self.assertRaisesRegex(ValueError,'keine Daten'):csv_info(raw)
        with self.assertRaisesRegex(ValueError,'lesbare XLSX'):xlsx_csv(b'broken')

    def test_blank_rows_and_individual_empty_fields(self):
        raw,_=xlsx_csv(fixture([('Export',[['ID','Text'],['',''],['0001',''],['0002','Hallo']])]))
        self.assertEqual(raw.decode(),'ID;Text\n0001;\n0002;Hallo\n')

    def test_size_limits(self):
        data=fixture([('Export',[['a','b'],['1','2']])])
        with patch('tabular_import.MAX_EXPANDED',10), self.assertRaisesRegex(ValueError,'entpackte'):xlsx_csv(data)
        with patch('tabular_import.MAX_ROWS',1), self.assertRaisesRegex(ValueError,'Importgrenzen'):xlsx_csv(data)

    def test_both_upload_formats_immutable_original_and_validation(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Synthetic import',True)['id']
            for kind, name in [('segments','maxqda_export.csv'),('codebook','Kategoriesystem.csv')]:
                rows=list(csv.reader(io.StringIO((root/'demo'/name).read_text(encoding='utf-8-sig')),delimiter=';'))
                data=fixture([('Export',rows)])
                uploaded=app.upload(pid,kind,'example.xlsx',base64.b64encode(data).decode())[kind]
                original=app.project_dir(pid)/'inputs'/(uploaded['id']+'.xlsx')
                self.assertEqual(original.read_bytes(),data)
            result=app.save(pid,settings(app))
            self.assertEqual((result['segments'],result['passages']),(50,43))
            before=app.project(pid)['uploads']
            data=fixture([('One',[['a','b'],['1','2']]),('Two',[['a','b'],['3','4']])])
            response=app.upload(pid,'segments','choose.xlsx',base64.b64encode(data).decode())
            self.assertTrue(response['requires_sheet'])
            self.assertEqual(app.project(pid)['uploads'],before)
            with self.assertRaisesRegex(ValueError,'.xlsx- oder .csv'):
                app.upload(pid,'segments','legacy.xls',base64.b64encode(b'a;b\n1;2').decode())
            app.upload(pid,'segments','again.csv',base64.b64encode((root/'demo/maxqda_export.csv').read_bytes()).decode())
            self.assertEqual(app.save(pid,settings(app))['segments'],50)


if __name__ == '__main__':
    unittest.main()
