"""Read transcript exchange files, never proprietary analysis-project containers."""
import argparse
import hashlib
import html
import io
import json
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET
import llm_review as review


STAMP = re.compile(r'#(\d{1,3}:\d{2}:\d{2}(?:[-.,]\d+)?)#|\[(\d{1,3}:\d{2}:\d{2}(?:[.,]\d+)?)\]')
TIMING = re.compile(r'((?:\d+:)?\d{2}:\d{2}[,.]\d+)\s*-->\s*((?:\d+:)?\d{2}:\d{2}[,.]\d+)(?:\s+.*)?$')


def seconds(value):
    value=value.replace(',','.').replace('-','.')
    parts=value.split(':')
    review.require(len(parts) in (2,3),'Ungültige Zeitmarke.')
    h,m,s=(0,*parts) if len(parts)==2 else parts
    h,m,s=int(h),int(m),float(s)
    review.require(h>=0 and 0<=m<60 and 0<=s<60,'Zeitmarke außerhalb gültiger Grenzen.')
    return h*3600+m*60+s


def text_decode(data,encoding):
    if data.startswith((b'\xff\xfe',b'\xfe\xff')):return data.decode('utf-16')
    try:return data.decode(encoding or 'utf-8-sig')
    except UnicodeDecodeError as exc:raise ValueError('Textkodierung nicht erkannt. UTF-8 exportieren oder explizit --encoding cp1252 wählen; keine stillen Ersatzzeichen.') from exc


def parse_bytes(filename,data,encoding=None):
    review.require(len(data)<=20*1024*1024,'Importlimit: 20 MiB.')
    suffix=Path(filename).suffix.lower();warnings=[]
    if suffix=='.docx':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info=archive.getinfo('word/document.xml')
            review.require(info.file_size<=20*1024*1024,'DOCX-Inhalt zu groß.')
            xml=archive.read(info)
        review.require(b'<!DOCTYPE' not in xml.upper() and b'<!ENTITY' not in xml.upper(),'DOCX mit DTD/Entitäten nicht unterstützt.')
        tree=ET.fromstring(xml);ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        text='\n'.join(''.join(n.text or '' if n.tag==ns+'t' else '\n' if n.tag in (ns+'br',ns+'cr') else '\t' if n.tag==ns+'tab' else '' for n in p.iter()) for p in tree.iter(ns+'p'))
        if any(True for _ in tree.iter(ns+'tbl')):warnings.append('DOCX enthält Tabellen. Zellen wurden in Lesereihenfolge übernommen; Zeilennummern/Memos in der Vorschau prüfen.')
        if any(True for _ in tree.iter(ns+'del')):warnings.append('DOCX enthält Änderungsmarkierungen. Endfassung vor Analyse besonders prüfen.')
    elif suffix=='.rtf':
        from striprtf.striprtf import rtf_to_text
        text=rtf_to_text(data.decode('latin1'),errors='strict')
        warnings.append('RTF-Formatierung entfällt; Transkripttext und sichtbare Zeitmarken bleiben erhalten.')
    elif suffix in ('.txt','.srt','.vtt'):
        text=text_decode(data,encoding)
    else:raise ValueError('Unterstützt: TXT, DOCX, RTF, SRT, VTT. Native f4-/MAXQDA-/ATLAS.ti-Projekte zuerst als Transkript exportieren.')
    text=text.replace('\r\n','\n').replace('\r','\n');segments=[]
    if suffix in ('.srt','.vtt'):
        for block in re.split(r'\n\s*\n',text.strip()):
            lines=block.splitlines()
            if not lines:continue
            if lines[0].startswith(('WEBVTT','NOTE','STYLE','REGION')):continue
            at=next((i for i,line in enumerate(lines) if '-->' in line),None)
            review.require(at is not None and at<=1,'Untertitelblock ohne gültige Zeitmarke; Import abgebrochen statt Text zu verwerfen.')
            match=TIMING.fullmatch(lines[at].strip());review.require(match,'Ungültiger SRT/VTT-Zeitbereich.')
            start,end=seconds(match[1]),seconds(match[2]);review.require(end>=start,'Rückwärts laufender Zeitbereich.')
            raw='\n'.join(lines[at+1:]);voice=re.match(r'<v(?:\.[^ >]+)?\s+([^>]+)>',raw)
            # Strip only documented caption formatting, retaining ordinary angle-bracket content.
            cleaned=re.sub(r'</?(?:v(?:\.[^ >]+)?(?:\s+[^>]+)?|b|i|u|c(?:\.[^ >]+)?|lang(?:\s+[^>]+)?)>', '',raw)
            cleaned=re.sub(r'<(?:\d+:)?\d{2}:\d{2}\.\d+>','',cleaned)
            cleaned=html.unescape(cleaned)
            review.require(cleaned.strip(),'Leerer Untertitelblock.')
            segments.append({'id':str(len(segments)+1),'start':start,'end':end,'text':cleaned,'speaker':voice[1] if voice else None})
        warnings.append('Untertitelzeiten sind Cue-Grenzen. Überlappende Cues bleiben erhalten; keine automatische Zusammenführung.')
    else:
        for line in text.splitlines():
            if not line.strip():continue
            stamps=list(STAMP.finditer(line));hint=None
            if len(stamps)==1:
                match=stamps[0];hint=seconds(match[1] or match[2])
            elif len(stamps)>1:warnings.append(f'Abschnitt {len(segments)+1}: mehrere Zeitmarken, keine eindeutige Segmentgrenze abgeleitet.')
            speaker=re.match(r'^\s*([^:\d][^:]{0,35}):\s+',line)
            segments.append({'id':str(len(segments)+1),'start':hint,'end':hint,'text':line.strip(),'speaker':speaker[1].strip() if speaker else None})
        warnings.append('Absätze/Zeilen bleiben Textsegmente. Einzelne f4/easytranscript/MAXQDA-Zeitmarken sind nur Sprungpunkte, keine gemessenen Zeitbereiche. Fehlende Zeitmarken bleiben unbekannt.')
    review.segments({'segments':segments})
    return {'kind':'imported_transcript','source_name':Path(filename).name,'source_sha256':hashlib.sha256(data).hexdigest(),
            'source_format':suffix,'segments':segments,'warnings':list(dict.fromkeys(warnings)),
            'review':{'confirmed':False},'person_mapping_confirmed':False,
            'note':'Sprecherlabels sind Importhinweise, keine bestätigten Personen. Native Codierungen werden nicht importiert.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--encoding')
    a=p.parse_args()
    try:review.write(a.output,parse_bytes(a.source.name,a.source.read_bytes(),a.encoding))
    except (ValueError,OSError,KeyError,ImportError) as exc:p.exit(2,f'Import nicht abgeschlossen: {exc}\n')
    print('Unbestätigte Vorschau gespeichert: '+str(a.output))


if __name__=='__main__':main()
