"""Bounded complete-input context summaries with explicit source receipts."""
import json
from runtime_support import fingerprint,PartCheckpoint
from summary_reduction import reduce_prompt


def compact_context(value,params,summarize,target_bytes=1200):
    source=json.dumps(value,ensure_ascii=False,indent=2)
    if len(source.encode('utf-8'))<=target_bytes:
        return value,{'used':False,'source_sha256':fingerprint(value)}
    system=('Verdichte die vollständige Analyse als Hintergrund für die Prüfung von Originalbelegen. '
            'Bewahre Unterschiede, Gegenbeispiele und Unsicherheiten; erfinde keine Belege.')
    key={'source':fingerprint(value),'target_bytes':target_bytes}
    text=PartCheckpoint('bounded_analysis_context',params).run(key,{'source':source,'system':system},
        lambda:reduce_prompt(system,source,params,summarize,target_bytes=target_bytes,allow_target_overflow=True))
    if not isinstance(text,str) or not text.strip():raise ValueError('Leere Kontextverdichtung.')
    return {'verdichteter_kontext':text},{'used':True,'source_sha256':fingerprint(value),
        'summary':text,'note':'Vollständiger Hintergrund wurde verdichtet; Details können verloren gehen. Originalanalysen bleiben erhalten.'}
