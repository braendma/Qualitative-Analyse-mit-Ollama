"""Read-only CSV/project contract check; optional real main-program importer, no inference."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys


def verify(project, categories, segments):
    for path in [categories, segments]:
        assert path.read_bytes().startswith(b'\xef\xbb\xbf'), 'UTF-8 BOM missing'
    with categories.open(encoding='utf-8-sig',newline='') as stream:book=list(csv.DictReader(stream,delimiter=';'))
    with segments.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream,delimiter=';'))
    docs={d['id']:d for d in project['documents']};cats={c['id']:c for c in project['categories']}
    expected=[]
    for ann in project['annotations']:
        doc=docs[ann['document_id']];seg=next(s for s in doc['segments'] if s['id']==ann['segment_id'])
        if seg['exclude']:continue
        expected.append((ann,doc,seg))
    assert len(rows)==len(expected)>0
    assert len(book)==len(cats)
    assert {b['Code'] for b in book}=={c['code'] for c in cats.values()}
    byid={r['segment_id']:r for r in rows};assert len(byid)==len(rows)
    for ann,doc,seg in expected:
        row=byid[ann['id']]
        assert row['Segment']==ann['quote']==seg['text'][ann['start']:ann['end']]
        assert row['Code']==cats[ann['category_id']]['code']
        assert row['Dokumentname']==row['PersonID']==seg['person']
        assert row['Quelldokument']==doc['title'] and row['Herkunft']==ann['origin']
        assert row['Memo']==ann['memo']
        assert int(row['Zeichenbeginn'])==ann['start'] and int(row['Zeichenende'])==ann['end']
        assert json.loads(row['PassageID'].removeprefix('PASS-'))==[doc['id'],seg['id'],ann['start'],ann['end']]
    return {'rows':len(rows),'categories':len(book),'people':sorted({r['PersonID'] for r in rows}),'passages':len({r['PassageID'] for r in rows}),'unique_row_ids':True,'quotes_people_provenance_offsets_verified':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--project',type=Path,required=True);parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--main-source',type=Path);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    project=json.loads(args.project.read_text(encoding='utf-8-sig'));project=project.get('project',project)
    categories=args.directory/'Kategoriesystem.csv';segments=args.directory/'maxqda_export.csv'
    report=verify(project,categories,segments)
    if args.main_source:
        sys.dont_write_bytecode=True
        sys.path.insert(0,str(args.main_source))
        import coding_validation_common as importer
        book,index=importer.load_codebook(categories)
        rows=importer.load_segments(segments,{'code':'Code','segment':'Segment','person':'Dokumentname','segment_id':'segment_id','unit_id':'PassageID'})
        assert len(book)==report['categories'] and len(rows)==report['rows']
        assert len({r.unit_id for r in rows})==report['passages']
        assert sorted({r.person for r in rows})==report['people']
        assert all(r.human_code in index for r in rows)
        report.update(main_importer_passed=True,main_importer_sha256=hashlib.sha256(Path(importer.__file__).read_bytes()).hexdigest())
    report['files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.project,categories,segments]}
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
