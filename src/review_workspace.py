"""Local review drafts, immutable follow-up inputs and category comparisons."""
import base64
import copy
import csv
import io
import json
import time
import uuid
from pathlib import Path

import yaml
from coding_validation_common import load_codebook, load_segments
from review_queue import validate_decisions
from runtime_support import atomic_json, atomic_text, fingerprint, file_hash


def read(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else default


def complete(row):
    return row['decision'] != 'unresolved' and bool(row['note'].strip()) and bool(row['reviewer'].strip())


def review_summary(queue, payload):
    by_id = {r['case_id']:r for r in payload['decisions']}
    critical = [c for c in queue['cases'] if c['needs_review']]
    done = lambda c: c['case_id'] in by_id and complete(by_id[c['case_id']])
    return {'total':len(queue['cases']), 'completed':sum(done(c) for c in queue['cases']),
            'critical':len(critical), 'critical_open':sum(not done(c) for c in critical)}


def compare_books(old, new, segments):
    old = {c.code:c.as_prompt_dict() for c in old}
    new = {c.code:c.as_prompt_dict() for c in new}
    added, removed = sorted(new.keys()-old.keys()), sorted(old.keys()-new.keys())
    changed = [k for k in sorted(old.keys() & new.keys()) if old[k] != new[k]]
    touched = set(removed+changed)
    affected = [{'segment_id':s.segment_id,'code':s.human_code} for s in segments if s.human_code in touched]
    return {'added':[new[k] for k in added], 'removed':[old[k] for k in removed],
            'changed':[{'code':k,'before':old[k],'after':new[k]} for k in changed],
            'affected_count':len(affected), 'affected':affected[:200],
            'unchanged':len(old.keys() & new.keys())-len(changed),
            'note':'Umbenennungen erscheinen als entfernt und neu. Betroffenheit bezieht sich auf die aktuell ausgewählten Codierzeilen; Definitionen werden nicht semantisch bewertet.'}


def decisions_xlsx(queue, payload):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    wb=Workbook(); ws=wb.active; ws.title='Prüfentscheidungen'
    columns=['Prüffall','Person','Originaltext','Ursprüngliche Codes','Modellcodes','Entscheidung',
             'Finale Codes','Begründung','Geprüft von','Abgeschlossen','Quellfingerprint']
    ws.append(columns)
    by_id={r['case_id']:r for r in payload['decisions']}
    for case in queue['cases']:
        row=by_id.get(case['case_id'], {'decision':'unresolved','final_codes':[],'note':'','reviewer':''})
        values=[case['case_id'],case['person'],case['text'],'\n'.join(case['human_codes']),
                '\n'.join(case['predicted_codes']),row['decision'],'\n'.join(row['final_codes']),
                row['note'],row['reviewer'],'ja' if complete(row) else 'nein',queue['source_fingerprint']]
        # Write all values as text, including strings beginning with =, +, - or @.
        # Excel's per-cell limit is explicit; never silently truncate research text.
        for col,value in enumerate(values,1):
            value=str(value)
            if len(value)>32767 or ILLEGAL_CHARACTERS_RE.search(value):
                raise ValueError('Mindestens ein Text ist für Excel zu lang oder enthält unzulässige Steuerzeichen. JSON-Export verwenden; dort bleiben die Texte vollständig erhalten.')
            cell=ws.cell(ws.max_row+1 if col==1 else ws.max_row,col)
            cell.value=value; cell.data_type='s';cell.alignment=Alignment(wrap_text=True,vertical='top')
    for cell in ws[1]:
        cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='183C48')
    widths=[24,20,70,35,35,22,35,55,22,18,30]
    for i,width in enumerate(widths,1):ws.column_dimensions[ws.cell(1,i).column_letter].width=width
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    buf=io.BytesIO();wb.save(buf);return buf.getvalue()


class ReviewWorkspace:
    def review_source(self, pid, jid):
        # artifact applies project/job identifiers, output allowlist and containment.
        path=self.artifact(pid,jid,'review_queue.json')
        queue=read(path)
        if not isinstance(queue,dict) or queue.get('schema_version')!=1:
            raise ValueError('Diese Prüfliste wird nicht unterstützt.')
        folder=self.project_dir(pid)/'jobs'/jid
        return folder,queue

    def review(self, pid, jid):
        folder,queue=self.review_source(pid,jid)
        current=read(folder/'review/current.json')
        if current is None:
            current={'schema_version':1,'source_fingerprint':queue['source_fingerprint'],'revision':0,'decisions':[]}
        validate_decisions(queue,current,draft=True)
        return {'queue':queue,'draft':current,'summary':review_summary(queue,current)}

    def save_review(self, pid, jid, row, expected_revision):
        with self.lock:
            loaded=self.review(pid,jid);queue=loaded['queue'];current=loaded['draft']
            if type(expected_revision) is not int or current['revision']!=expected_revision:
                raise ValueError('Die Prüfliste wurde in einem anderen Fenster geändert. Entwurf exportieren und Prüfliste neu öffnen.')
            checked=validate_decisions(queue,{'schema_version':1,'source_fingerprint':queue['source_fingerprint'],'decisions':[row]},draft=True)
            new=checked['decisions'][0]
            rows={r['case_id']:r for r in current['decisions']};rows[new['case_id']]=new
            payload={**checked,'decisions':list(rows.values()),'revision':current['revision']+1,'saved_at':time.time()}
            directory=self.project_dir(pid)/'jobs'/jid/'review'
            # A single atomic pointer names an immutable whole draft version.
            atomic_json(directory/'versions'/(uuid.uuid4().hex+'.json'),payload)
            atomic_json(directory/'current.json',payload)
            return {'revision':payload['revision'],'summary':review_summary(queue,payload),'saved_at':payload['saved_at']}

    def followup_preview(self, pid, jid):
        loaded=self.review(pid,jid);queue,payload=loaded['queue'],loaded['draft']
        if loaded['summary']['critical_open']:
            raise ValueError('Zuerst alle kritischen Fälle mit Entscheidung, Begründung und prüfender Person abschließen.')
        rows={r['case_id']:r for r in payload['decisions'] if complete(r)}
        changed=[c for c in queue['cases'] if c['case_id'] in rows and set(rows[c['case_id']]['final_codes'])!=set(c['human_codes'])]
        uncoded=[c['case_id'] for c in queue['cases'] if c['case_id'] in rows and not rows[c['case_id']]['final_codes']]
        return {'review_revision':payload['revision'],'changed':len(changed),'uncoded':len(uncoded),
                'changes':[{'case_id':c['case_id'],'before':c['human_codes'],'after':rows[c['case_id']]['final_codes']} for c in changed],
                'note':'Neue Eingabeversion; ursprünglicher Lauf bleibt erhalten. Nicht geprüfte unkritische Fälle behalten ihre ursprünglichen Codes. Fälle ohne finale Zuordnung bleiben in der Prüfliste erhalten und werden aus der codierten Folgeanalyse ausgeschlossen.'}

    def prepare_followup(self, pid, jid, expected_revision, accept_exclusions=False):
        with self.lock:
            preview=self.followup_preview(pid,jid)
            if type(expected_revision) is not int or expected_revision!=preview['review_revision']:raise ValueError('Prüfentscheidungen haben sich geändert. Vorschau erneut öffnen.')
            if preview['uncoded'] and accept_exclusions is not True:
                raise ValueError('Den Ausschluss der Fälle ohne finale Codes ausdrücklich bestätigen.')
            loaded=self.review(pid,jid);queue=loaded['queue'];draft=loaded['draft']
            directory=self.project_dir(pid);job=read(directory/'jobs'/jid/'job.json')
            oldcfg=yaml.safe_load(Path(job['config']).read_text(encoding='utf-8'))
            segments=load_segments(oldcfg['paths']['input_csv'],oldcfg['columns'])
            known={s.segment_id:s for s in segments}
            ids=[sid for c in queue['cases'] for sid in c['segment_ids']]
            if len(ids)!=len(set(ids)) or set(ids)!=set(known):raise ValueError('Prüfliste deckt die Originaleingabe nicht eindeutig ab.')
            rows={r['case_id']:r for r in draft['decisions'] if complete(r)}
            out=io.StringIO(newline='');writer=csv.writer(out,delimiter=';',lineterminator='\n')
            writer.writerow(['segment_id','PassageID','Dokumentname','Code','Segment','SourceSegmentIDs'])
            excluded=[];count=0
            for c in queue['cases']:
                members=[known[sid] for sid in c['segment_ids']]
                if any(s.person!=c['person'] or s.text!=c['text'] for s in members):
                    raise ValueError('Originaltext oder Person weicht von der Prüfliste ab.')
                codes=rows[c['case_id']]['final_codes'] if c['case_id'] in rows else c['human_codes']
                if not codes:excluded.append(c['case_id'])
                for code in codes:
                    count+=1
                    writer.writerow([f'R{count:07d}',c.get('unit_id') or c['case_id'],c['person'],code,c['text'],' | '.join(c['segment_ids'])])
            if not count:raise ValueError('Keine codierten Fälle für einen Folgelauf vorhanden.')
            # Reuse the source run's study context, codebook and model, not later unrelated uploads.
            source_settings=read(Path(job['config']).parent/'settings.json')
            if source_settings is None:
                source_settings={'model':oldcfg['llm']['model'],'context':oldcfg['context'],
                                 'modules':[m['id'] for m in oldcfg['pipeline']['modules'] if m.get('enabled',True)]}
                source_settings.update({k:oldcfg['llm'][k] for k in ('num_ctx','max_tokens','temperature','think','provider','gdpr_relevant') if k in oldcfg['llm']})
            settings=copy.deepcopy(source_settings)
            if not settings.get('provider'):
                settings['provider']='ollama_cloud' if oldcfg['llm'].get('host')=='https://ollama.com' else 'ollama_local'
            # Preparing a historical review must never revoke the current project's privacy choice.
            current_private=self.project(pid)['settings'].get('gdpr_relevant',True)
            settings['gdpr_relevant']=current_private
            if current_private:
                settings['provider']='ollama_local'
                if oldcfg['llm'].get('provider','ollama_local')!='ollama_local' or oldcfg['llm'].get('host')=='https://ollama.com':
                    settings['model']=self.template['llm']['model']
            settings['columns']={'segment_id':'segment_id','unit_id':'PassageID','person':'Dokumentname','code':'Code','segment':'Segment'}
            settings['label_mode']='multi_label'
            from coding_validation_common import CODEBOOK_ALIASES, resolve_column
            headers = next(csv.reader(io.StringIO(Path(oldcfg['paths']['category_system_csv']).read_text(encoding='utf-8-sig')), delimiter=';'))
            settings['book_columns'] = {}
            for key, aliases in CODEBOOK_ALIASES.items():
                try:
                    settings['book_columns'][key] = resolve_column(headers, None, aliases, key)
                except ValueError:
                    settings['book_columns'][key] = ''
            source={'kind':'reviewed_followup','parent_job':jid,'review_revision':draft['revision'],
                    'review_fingerprint':fingerprint(draft),'excluded_cases':excluded,'changed_cases':preview['changed'],
                    'note':'Auswertung nach manueller Prüfung; keine unabhängige Validierung und kein Modelltraining.'}
            # Stage in a new directory first. Publish project pointers only after full validation.
            rev=directory/'revisions'/uuid.uuid4().hex[:20];rev.mkdir(parents=True)
            atomic_text(rev/'segments.csv',out.getvalue())
            atomic_text(rev/'codebook.csv',Path(oldcfg['paths']['category_system_csv']).read_text(encoding='utf-8-sig'))
            cfg=copy.deepcopy(oldcfg);cfg['paths'].update(input_csv=str(rev/'segments.csv'),category_system_csv=str(rev/'codebook.csv'))
            from llm_providers import selection
            cfg['llm'].update(selection(settings))
            cfg['columns']=settings['columns'];cfg['coding_agreement'].update(label_mode='multi_label',independent_units_confirmed=False)
            cfg['review_provenance']=source
            atomic_text(rev/'config.yaml',yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False))
            self.validate_config(rev/'config.yaml')
            atomic_json(rev/'review_snapshot.json',draft);atomic_json(rev/'settings.json',settings)
            from local_app import csv_info
            uploads={}
            for kind,name in [('segments','segments.csv'),('codebook','codebook.csv')]:
                raw=(rev/name).read_bytes();fid=uuid.uuid4().hex[:20]
                path=directory/'inputs'/(fid+'.csv');path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
                uploads[kind]={'id':fid,'name':'Geprüfte Codierungen.csv' if kind=='segments' else 'Kategoriensystem des Ursprungslaufs.csv','format':'csv',**csv_info(raw)}
            data=read(directory/'project.json');data.update(revision=rev.name,last_valid_revision=rev.name,review_provenance=source)
            atomic_json(directory/'uploads.json',uploads);atomic_json(directory/'settings.json',settings);atomic_json(directory/'project.json',data)
            return {'project':self.project(pid),'preview':preview,'model_calls':0}

    def category_versions(self,pid):
        result=[]
        directory=self.project_dir(pid);data=read(directory/'project.json')
        # Older app versions did not write per-revision settings. Include their
        # current revision and job sources, while excluding failed validation drafts.
        valid={data.get('revision'),data.get('last_valid_revision')}
        for job in (directory/'jobs').glob('*/job.json'):
            config=read(job).get('config')
            if config:valid.add(Path(config).parent.name)
        for path in (directory/'revisions').glob('*/config.yaml'):
            if not (path.parent/'codebook.csv').is_file():continue
            if not (path.parent/'settings.json').exists() and path.parent.name not in valid:continue
            result.append({'id':path.parent.name,'created':path.stat().st_mtime,'sha256':file_hash(path.parent/'codebook.csv')})
        return sorted(result,key=lambda r:r['created'],reverse=True)

    def compare_categories(self,pid,settings,baseline=None):
        from local_app import identifier
        directory=self.project_dir(pid);data=read(directory/'project.json')
        baseline=baseline or data.get('last_valid_revision') or data.get('revision')
        if not baseline:return {'baseline':None,'note':'Noch keine gespeicherte Vergleichsversion. Zuerst Eingaben erfolgreich speichern und prüfen.'}
        path=directory/'revisions'/identifier(baseline)/'codebook.csv'
        if not path.is_file():raise ValueError('Vergleichsversion fehlt.')
        cfg,text=self.config(pid,settings)
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            current=Path(tmp)/'codebook.csv';current.write_text(text,encoding='utf-8')
            old,_=load_codebook(path);new,_=load_codebook(current)
        result=compare_books(old,new,load_segments(cfg['paths']['input_csv'],cfg['columns']))
        return {'baseline':baseline,**result}

    def start_refinement(self,pid,jid,expected_revision):
        with self.lock:
            loaded=self.review(pid,jid);draft=loaded['draft'];queue=loaded['queue']
            if loaded['summary']['critical_open']:raise ValueError('Zuerst die kritischen Fälle vollständig prüfen.')
            if type(expected_revision) is not int or draft['revision']!=expected_revision:raise ValueError('Prüfung geändert. Prüfliste erneut öffnen.')
            if not any(complete(r) for r in draft['decisions']):raise ValueError('Noch keine abgeschlossenen Prüfentscheidungen vorhanden.')
            source=read(self.project_dir(pid)/'jobs'/jid/'job.json')
            cfg=yaml.safe_load(Path(source['config']).read_text(encoding='utf-8'))
            rev=self.project_dir(pid)/'revisions'/uuid.uuid4().hex[:20];rev.mkdir(parents=True)
            atomic_json(rev/'review.json',draft);atomic_json(rev/'queue.json',queue)
            cfg['refinement']={'queue':str(rev/'queue.json'),'decisions':str(rev/'review.json'),'batch_size':6}
            cfg['pipeline']['modules']=[{'id':'codebook_refinement','name':'Vorschläge zum Kategoriensystem',
                'script':'codebook_refinement.py','enabled':True,'depends_on':[], 'args':['--config','{config}'],
                'outputs':['codebook_proposals.json','codebook_proposals.md'],
                'report':{'title':'Vorschläge zum Kategoriensystem','markdown':'codebook_proposals.md'}}]
            cfg['review_provenance']={'kind':'codebook_proposals','parent_job':jid,'review_revision':draft['revision'],
                                     'note':'Vorschläge aus manueller Prüfung. Nicht automatisch übernommen.'}
            atomic_text(rev/'config.yaml',yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False))
            return self.start(pid,prepared_config=rev/'config.yaml')
