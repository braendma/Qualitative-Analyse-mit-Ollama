"""Local source selection uses synthetic files, never model transport."""
import base64
from contextlib import contextmanager
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from local_app import App, make_server
from runtime_support import atomic_json
from test_local_app import settings as valid_settings


ROOT=Path(__file__).resolve().parents[1]
CSV='Dokumentname;Code;Segment\nInterview_A;A;Eine künstliche Aussage.\n'


def workspace(tmp):
    app=App(Path(tmp)/'state');pid=app.create('Synthetic local import')['id']
    parent=Path(tmp)/'Forschung Ä mit Leerzeichen';parent.mkdir()
    source=parent/'Codierte Segmente.csv';source.write_text(CSV,encoding='utf-8')
    return app,pid,source


def workbook(path,extra=''):
    book=Workbook();sheet=book.active;sheet.title='Daten'
    sheet.append(['Dokumentname','Code','Segment']);sheet.append(['Interview_A','A','Künstlich '+extra])
    book.create_sheet('Weitere Daten').append(['Dokumentname','Code','Segment'])
    book.save(path);book.close()


def snapshot(app,pid):
    folder=app.project_dir(pid)
    return {str(path.relative_to(folder)):path.read_bytes() for path in folder.rglob('*') if path.is_file()}


@contextmanager
def server_for(app):
    server=make_server(app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield server
    finally:server.shutdown();server.server_close();thread.join()


def post(server,path,data,**headers):
    connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
    try:
        connection.request('POST',path,json.dumps(data),{'Content-Type':'application/json',**headers})
        response=connection.getresponse()
        return response.status,response.read()
    finally:connection.close()


def rejected_headers(server,path,headers):
    # Authorization must reject before reading any request body. Sending just
    # headers also avoids Windows resetting a closed socket with unread bytes.
    connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
    try:
        connection.putrequest('POST',path,skip_host='Host' in headers)
        connection.putheader('Content-Type','application/json')
        connection.putheader('Content-Length','100')
        for key,value in headers.items():connection.putheader(key,value)
        connection.endheaders()
        response=connection.getresponse()
        return response.status,response.read()
    finally:connection.close()


class LocalImportTests(unittest.TestCase):
    def test_csv_import_preserves_original_and_records_verified_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,source=workspace(tmp);original=source.read_bytes()
            result=app.local_import(pid,'segments',str(source))
            upload=result['uploads']['segments']
            self.assertEqual(upload['source_path'],str(source.resolve()))
            self.assertEqual(upload['source_sha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual(result['source_path'],str(source.resolve()))
            self.assertEqual(result['suggested_output_dir'],str(source.parent.resolve()))
            self.assertEqual(source.read_bytes(),original)
            copied=app.project_dir(pid)/'inputs'/(upload['id']+'.csv')
            self.assertEqual(copied.read_bytes(),original)
            self.assertNotEqual(copied.resolve(),source.resolve())
            current=app.project(pid)['settings']
            self.assertEqual(current['output_dir'],str(source.parent.resolve()))
            self.assertEqual(current['output_dir_mode'],'input')

    def test_explicit_target_survives_local_and_browser_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,source=workspace(tmp);target=Path(tmp)/'Separate results';target.mkdir()
            atomic_json(app.project_dir(pid)/'settings.json',{'output_dir':str(target),'output_dir_mode':'explicit'})
            app.local_import(pid,'segments',str(source))
            app.upload(pid,'segments','replacement.csv',base64.b64encode(CSV.encode()).decode())
            current=app.project(pid)
            self.assertEqual(current['settings']['output_dir'],str(target))
            self.assertEqual(current['settings']['output_dir_mode'],'explicit')
            self.assertNotIn('source_path',current['uploads']['segments'])

    def test_new_local_segment_source_updates_only_automatic_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,source=workspace(tmp);app.local_import(pid,'segments',str(source))
            second=Path(tmp)/'Other input';second.mkdir();source2=second/'Second.csv';source2.write_text(CSV,encoding='utf-8')
            app.local_import(pid,'segments',str(source2))
            self.assertEqual(app.project(pid)['settings']['output_dir'],str(second.resolve()))
            book=source.parent/'Categories.csv';book.write_text('Code;Definition\nA;Künstlich\n',encoding='utf-8')
            result=app.local_import(pid,'codebook',str(book))
            self.assertNotIn('suggested_output_dir',result)
            self.assertEqual(app.project(pid)['settings']['output_dir'],str(second.resolve()))

    def test_browser_replacement_clears_unknown_automatic_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,source=workspace(tmp);app.local_import(pid,'segments',str(source))
            result=app.upload(pid,'segments',r'C:\fakepath\Browser.csv',base64.b64encode(CSV.encode()).decode())
            self.assertIn('segments',result)
            self.assertNotIn('uploads',result)
            self.assertNotIn('source_path',result['segments'])
            self.assertNotIn('source_sha256',result['segments'])
            self.assertEqual(app.project(pid)['settings']['output_dir'],'')
            self.assertEqual(app.project(pid)['settings']['output_dir_mode'],'explicit')

    def test_multiple_sheets_do_not_commit_until_receipted_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,source=workspace(tmp);app.local_import(pid,'segments',str(source))
            xlsx=source.with_suffix('.xlsx');workbook(xlsx);original=xlsx.read_bytes()
            previous_id=app.project(pid)['uploads']['segments']['id']
            before=snapshot(app,pid)
            preview=app.local_import(pid,'segments',str(xlsx))
            self.assertTrue(preview['requires_sheet'])
            self.assertEqual(preview['sheets'],['Daten','Weitere Daten'])
            self.assertEqual(preview['name'],xlsx.name)
            self.assertEqual(snapshot(app,pid),before)
            result=app.local_import(pid,'segments',preview['source_path'],sheet='Daten',receipt=preview['receipt'])
            self.assertEqual(result['uploads']['segments']['sheet'],'Daten')
            self.assertEqual(result['uploads']['segments']['source_sha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual(xlsx.read_bytes(),original)
            self.assertNotEqual(result['uploads']['segments']['id'],previous_id)
            self.assertNotIn(preview['receipt'],app.local_imports)
            committed=snapshot(app,pid)
            with self.assertRaises(ValueError):
                app.local_import(pid,'segments',preview['source_path'],sheet='Daten',receipt=preview['receipt'])
            self.assertEqual(snapshot(app,pid),committed)

    def test_sheet_receipt_rejects_changed_source_context_and_expiration(self):
        for variant in ('source','project','path','kind','expired','current_upload','fabricated'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                app,pid,source=workspace(tmp);xlsx=source.with_suffix('.xlsx');workbook(xlsx)
                preview=app.local_import(pid,'segments',str(xlsx))
                call={'pid':pid,'kind':'segments','path':preview['source_path'],'sheet':'Daten','receipt':preview['receipt']}
                if variant=='source':workbook(xlsx,'nachträglich verändert')
                elif variant=='project':call['pid']=app.create('Other synthetic project')['id']
                elif variant=='path':
                    other=xlsx.with_name('other.xlsx');other.write_bytes(xlsx.read_bytes());call['path']=str(other)
                elif variant=='kind':call['kind']='codebook'
                elif variant=='expired':app.local_imports[preview['receipt']]['created']-=601
                elif variant=='current_upload':app.upload(pid,'segments','replacement.csv',base64.b64encode(CSV.encode()).decode())
                elif variant=='fabricated':call['receipt']={'path':str(xlsx),'project':pid}
                before=snapshot(app,pid);other_before=snapshot(app,call['pid'])
                with self.assertRaises(ValueError):app.local_import(**call)
                self.assertEqual(snapshot(app,pid),before)
                self.assertEqual(snapshot(app,call['pid']),other_before)

    def test_sheet_argument_requires_original_preview_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,source=workspace(tmp);xlsx=source.with_suffix('.xlsx');workbook(xlsx)
            before=snapshot(app,pid)
            with self.assertRaises(ValueError):app.local_import(pid,'segments',str(xlsx),sheet='Daten')
            self.assertEqual(snapshot(app,pid),before)

    def test_save_input_mode_requires_known_current_segment_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(Path(tmp)/'state');pid=app.create('Synthetic demo',True)['id']
            parent=Path(tmp)/'Original input';parent.mkdir();source=parent/'demo.csv'
            source.write_bytes((ROOT/'demo/maxqda_export.csv').read_bytes())
            app.local_import(pid,'segments',str(source))
            opts=valid_settings(app);opts.update(output_dir=str(parent),output_dir_mode='input')
            app.save(pid,opts)
            before=app.project(pid)
            other=Path(tmp)/'Unrelated target';other.mkdir();opts['output_dir']=str(other)
            with self.assertRaises(ValueError):app.save(pid,opts)
            self.assertEqual(app.project(pid)['revision'],before['revision'])
            self.assertEqual(app.project(pid)['settings'],before['settings'])
            app.upload(pid,'segments','browser.csv',base64.b64encode(source.read_bytes()).decode())
            opts=valid_settings(app);opts.update(output_dir=str(parent),output_dir_mode='input')
            with self.assertRaises(ValueError):app.save(pid,opts)

    def test_unauthorized_http_requests_do_not_browse_or_read_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,source=workspace(tmp)
            with patch.object(app,'local_browse') as browse,patch.object(app,'local_import') as importing,server_for(app) as server:
                for route in ('/api/local-browse','/api/local-import'):
                    for headers in ({},{'X-App-Token':server.token,'Origin':'https://example.invalid'},
                                    {'X-App-Token':server.token,'Host':'example.invalid'},
                                    {'X-App-Token':server.token,'Sec-Fetch-Site':'cross-site'}):
                        with self.subTest(route=route,headers=tuple(headers)):
                            status,_=rejected_headers(server,route,headers)
                            self.assertEqual(status,403)
                browse.assert_not_called();importing.assert_not_called()

    def test_review_followup_preserves_target_as_explicit_without_fabricating_source(self):
        from test_external_review import external_fixture
        from test_review_workspace import decision
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,_,cfg,_=external_fixture(tmp)
            target=Path(tmp)/'Chosen source folder';target.mkdir()
            source=target/'original.csv';source.write_bytes((cfg.parent/'segments.csv').read_bytes())
            app.local_import(pid,'segments',str(source))
            self.assertEqual(app.project(pid)['settings']['output_dir_mode'],'input')
            app.save_review(pid,jid,decision(),0)
            prepared=app.prepare_followup(pid,jid,1)['project']
            self.assertEqual(prepared['settings']['output_dir'],str(target.resolve()))
            self.assertEqual(prepared['settings']['output_dir_mode'],'explicit')
            self.assertNotIn('source_path',prepared['uploads']['segments'])
            self.assertTrue(app.save(pid,prepared['settings'])['valid'])

    def test_passage_preparation_retains_real_original_source_and_input_target(self):
        from test_passage_ids import RAW,COLS
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,source=workspace(tmp);source.write_bytes(RAW)
            imported=app.local_import(pid,'segments',str(source))['uploads']['segments']
            preview=app.passage_preview(pid,COLS)
            opts={**app.project(pid)['settings'],'columns':COLS,'model':'mock'}
            updated=app.passage_apply(pid,opts,preview['fingerprint'],['0'])
            derived=updated['uploads']['segments']
            self.assertNotEqual(imported['id'],derived['id'])
            self.assertEqual(derived['source_path'],imported['source_path'])
            self.assertEqual(derived['source_sha256'],hashlib.sha256(RAW).hexdigest())
            self.assertEqual(updated['settings']['output_dir_mode'],'input')
            self.assertEqual(updated['settings']['output_dir'],str(source.parent.resolve()))
            self.assertEqual(source.read_bytes(),RAW)

    def test_handbook_selection_svg_is_explicitly_served_without_directory_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,_,_=workspace(tmp)
            with server_for(app) as server:
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                try:
                    connection.request('GET','/images/local-file-selection.svg')
                    response=connection.getresponse();raw=response.read()
                    self.assertEqual(response.status,200)
                    self.assertEqual(response.getheader('Content-Type'),'image/svg+xml')
                    self.assertIn(b'<svg',raw)
                    self.assertIn('schematisches Beispiel',raw.decode('utf-8'))
                    connection.request('GET','/images/not-published.svg')
                    response=connection.getresponse();response.read()
                    self.assertEqual(response.status,403)
                finally:connection.close()

    def test_browse_dispatch_does_not_wait_for_mutation_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,source=workspace(tmp)
            with patch.object(app,'local_browse',return_value={'synthetic':True}) as browse,server_for(app) as server:
                with app.lock:
                    status,body=post(server,'/api/local-browse',{'project':pid,'path':str(source.parent),'kind':'directory'},**{'X-App-Token':server.token})
                self.assertEqual(status,200);self.assertEqual(json.loads(body),{'synthetic':True})
                browse.assert_called_once_with(pid,str(source.parent),'directory')


if __name__=='__main__':unittest.main()
