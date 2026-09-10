"""Self-contained, offline report export from existing module outputs; no model calls."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import yaml
from runtime_support import atomic_text

ROOT = Path(__file__).resolve().parent
MAX_IMAGE = 20 * 1024 * 1024
MAX_EXPORT = 95 * 1024 * 1024
IMAGE = re.compile(r'^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$', re.M)


def inline_assets():
    """Exact bundled code/style shared by export and the app's CSP allowlist."""
    return {'script': [(ROOT/'report_viewer.js').read_text(encoding='utf-8'),
                       (ROOT/'html_report.js').read_text(encoding='utf-8')],
            'style': [(ROOT/'html_report.css').read_text(encoding='utf-8')]}


def csp_hashes():
    return {tag: ["'sha256-"+base64.b64encode(hashlib.sha256(value.encode()).digest()).decode()+"'"
                  for value in values] for tag,values in inline_assets().items()}


def local_file(directory, name):
    # Paths in model-produced Markdown must never read outside this run.
    name = str(name).replace('\\','/').strip('<>')
    if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:',name) or name.startswith('/'):
        raise ValueError('Nur relative Dateien innerhalb dieses Laufs sind zulässig.')
    path = (directory/name).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError('Datei liegt außerhalb des Laufordners.')
    return path


def image_data(path):
    if path.stat().st_size > MAX_IMAGE:raise ValueError('Abbildung überschreitet 20 MB.')
    raw = path.read_bytes()
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):mime='image/png'
    elif raw.startswith(b'\xff\xd8\xff'):mime='image/jpeg'
    elif raw[:6] in (b'GIF87a',b'GIF89a'):mime='image/gif'
    elif raw[:4]==b'RIFF' and raw[8:12]==b'WEBP':mime='image/webp'
    else:raise ValueError('Kein unterstütztes Rasterbild.')
    return 'data:'+mime+';base64,'+base64.b64encode(raw).decode()


def build_html_report(directory, modules, created_at, *, filename='gesamtbericht.html', config=None):
    directory=Path(directory).resolve()
    if config is None:
        path=directory/'config_snapshot.yaml'
        config=yaml.safe_load(path.read_text(encoding='utf-8')) if path.is_file() else {}
    config=config or {};sections=[];warnings=[];assets={};image_bytes=0
    for module in modules:
        if not module.get('enabled',True):continue
        report=module.get('report',{})
        if not isinstance(report,dict) or not report.get('markdown'):continue
        name=report['markdown'];path=local_file(directory,name)
        if not path.is_file():
            warnings.append('Berichtsteil fehlt: '+str(module.get('name',module['id'])))
            continue
        text=path.read_text(encoding='utf-8-sig')
        section_assets={}
        for match in IMAGE.finditer(text):
            reference=match[2]
            try:
                target=local_file(directory,str(path.parent.relative_to(directory)/reference.replace('\\','/')))
                key=str(target.relative_to(directory))
                if key not in assets:
                    encoded=image_data(target)
                    if image_bytes+len(encoded)>MAX_EXPORT//2:raise ValueError('Bildbudget überschritten.')
                    assets[key]=encoded;image_bytes+=len(encoded)
                section_assets[reference]=key
            except (OSError,ValueError):
                warnings.append('Eine Abbildung in „'+str(report.get('title',module['name']))+'“ wurde nicht eingebettet (fehlend, zu groß oder nicht unterstützter Pfad/Bildtyp).')
        sections.append({'id':'section-'+str(len(sections)+1),'title':str(report.get('title',module['name'])),
                         'markdown':text,'images':section_assets})
    source=config.get('review_provenance') or {}
    data={'schema_version':1,'created_at':str(created_at),'run_id':directory.name,
          'model':str(config.get('llm',{}).get('model','Nicht dokumentiert')),
          'review_note':str(source.get('note','')),'sections':sections,'images':assets,'warnings':list(dict.fromkeys(warnings))}
    # No credentials, complete YAML or file-system paths enter the metadata.
    payload=json.dumps(data,ensure_ascii=False).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    bundled=inline_assets();hashes=csp_hashes()
    policy="default-src 'none'; script-src "+' '.join(hashes['script'])+"; style-src "+' '.join(hashes['style'])+"; img-src data:; base-uri 'none'; form-action 'none'"
    template=(ROOT/'html_report_template.html').read_text(encoding='utf-8')
    page=template.replace('__POLICY__',policy).replace('__STYLE__',bundled['style'][0])
    # Insert data last so arbitrary report content cannot act as a template marker.
    page=page.replace('__RENDERER__',bundled['script'][0]).replace('__REPORT_SCRIPT__',bundled['script'][1]).replace('__PAYLOAD__',payload)
    if len(page.encode('utf-8'))>MAX_EXPORT:
        raise ValueError('HTML-Bericht überschreitet 95 MB. Markdown und einzelne Abbildungen verwenden.')
    output=local_file(directory,filename);atomic_text(output,page);return output


def main():
    parser=argparse.ArgumentParser(description='HTML aus vorhandenen Berichten erzeugen, ohne Modellaufruf')
    parser.add_argument('--run-dir',required=True);args=parser.parse_args()
    folder=Path(args.run_dir).resolve();manifest=json.loads((folder/'workflow_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status')!='success':raise ValueError('HTML-Nacherstellung benötigt einen erfolgreich abgeschlossenen Lauf.')
    cfg=yaml.safe_load((folder/'config_snapshot.yaml').read_text(encoding='utf-8'))
    # Preserve a previous export; rerender into an explicitly separate file.
    import uuid
    name='gesamtbericht.html' if not (folder/'gesamtbericht.html').exists() else 'gesamtbericht_'+uuid.uuid4().hex[:8]+'.html'
    path=build_html_report(folder,cfg['pipeline']['modules'],manifest.get('finished_at',''),filename=name,config=cfg)
    print(str(path))


if __name__=='__main__':main()
