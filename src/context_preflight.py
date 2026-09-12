"""Read-only prompt-size screening using the same conservative bound as requests."""
import hashlib
import json
from collections import defaultdict
from coding_validation_common import CODEBOOK_RULE_GUIDANCE, code_hierarchy
from utils_prompt import build_prompt_for_module


def check_context(config, segments, codebook, modules):
    settings=config.get('llm',{})
    context=int(settings.get('num_ctx',32768)); answer=int(settings.get('max_tokens',2048))
    enabled={m['id'] if isinstance(m,dict) else m for m in modules}
    prompts=config.get('prompts',{}); study=config.get('context',{})
    book=list(codebook.values()) if isinstance(codebook,dict) else list(codebook)
    by_code={c.code:c for c in book}
    serialized=json.dumps([c.as_prompt_dict() for c in book],ensure_ascii=False)
    maxima={}; counts=defaultdict(int)
    def record(module, messages):
        # Matches llm_client.request_chat: UTF-8 bytes + 32 per message + 256.
        needed=sum(len(m['content'].encode('utf-8'))+32 for m in messages)+answer+256
        maxima[module]=max(maxima.get(module,0),needed); counts[module]+=1
    def pair(module, key, guidance='', **values):
        system,user=build_prompt_for_module(key,prompts,study,**values)
        record(module,[{'role':'system','content':system+guidance},{'role':'user','content':user}])
    for segment in segments:
        if 'code_verification' in enabled:
            pair('code_verification','code_verification',CODEBOOK_RULE_GUIDANCE,
                segment_id=segment.segment_id,segment=segment.text,human_code=segment.human_code,
                target_code=json.dumps(by_code[segment.human_code].as_prompt_dict(),ensure_ascii=False),codebook=serialized)
        if 'blind_coding' in enabled and config.get('coding_agreement',{}).get('label_mode')!='multi_label':
            pair('blind_coding','blind_coding',CODEBOOK_RULE_GUIDANCE,
                segment_id=segment.segment_id,segment=segment.text,codebook=serialized)
    if 'blind_coding' in enabled and config.get('coding_agreement',{}).get('label_mode')=='multi_label':
        from multi_label_core import group_units, blind_unit_messages
        for uid,members in group_units(segments).items():
            opaque='U'+hashlib.sha256(uid.encode('utf-8')).hexdigest()[:20]
            record('blind_coding',blind_unit_messages(opaque,members[0].text,book,study))
    if 'clusterer' in enabled:
        groups=defaultdict(list)
        for segment in segments:groups[segment.human_code].append(segment)
        for code,members in groups.items():
            _,levels=code_hierarchy(code,by_code)
            pair('clusterer','cluster_analysis',subcat=levels[-1],facets=code,
                segments=json.dumps([{'id':s.segment_id,'text':s.text,'person':s.person} for s in members],ensure_ascii=False),
                json_schema=prompts.get('json_schema',''))
    # Later stages depend on model outputs that do not exist at start. Check
    # their fixed instructions now and explicitly retain that uncertainty.
    keys={'summarizer':'cluster_summary','swot':'swot_analysis','meta_swot':'meta_swot',
        'person_analysis':'person_analysis','person_comparison':'person_comparison',
        'contrast_analysis':'contrast_analysis','relation_analysis':'relation_analysis',
        'ambiguity_analysis':'ambiguity_analysis','evidence_audit':'evidence_audit','overall_synthesis':'overall_synthesis'}
    for module,key in keys.items():
        if module in enabled:pair(module,key)
    if 'summarizer' in enabled:pair('summarizer','category_summary')
    blocked=[{'module':module,'required_bound':needed} for module,needed in maxima.items() if needed>context]
    warnings=[]
    for module in ('code_verification','blind_coding'):
        if module in maxima and maxima[module]+4*answer+1024>context:
            warnings.append(f'{module}: Für eine längere Antwortreparatur könnte der Kontext zu knapp sein. Mehr Kontext wählen oder das Antwortlimit passend verringern.')
    if enabled.intersection(keys):
        warnings.append('Spätere Analysestufen verwenden erst noch zu erzeugende Modellbefunde. Deren Größe ist vorab unbekannt; die Laufzeitprüfung bleibt erforderlich. Große Zusammenfassungen werden automatisch verdichtet.')
    if settings.get('think'):
        warnings.append('Thinking und sichtbare Antwort teilen sich das Antwortlimit. Ein kleines Limit kann trotz passender Eingabe zu abgeschnittenen Antworten führen.')
    return {'context':context,'answer_limit':answer,'blocked':blocked,'warnings':warnings,
        'checks':[{'module':module,'required_bound':needed,'requests_checked':counts[module]} for module,needed in maxima.items()],
        'note':'Konservative Vorprüfung mit UTF-8-Bytes wie beim Anfrage-Client, keine gemessene Tokenzahl und kein Modellaufruf.'}


def require_context(report):
    if report['blocked']:
        details='; '.join(f"{x['module']}: Rechengrenze {x['required_bound']:,}".replace(',','.') for x in report['blocked'][:5])
        raise ValueError(f"Start gesperrt: Kontextfenster {report['context']:,} reicht nach der konservativen Anfrageprüfung nicht ({details}). "
            'Größeres Kontextfenster wählen und die Speicherschätzung erneut prüfen; dafür können weniger parallele Anfragen nötig sein. '
            'Alternativ das Antwortlimit angemessen verringern. Texte und Codierregeln werden nicht automatisch gekürzt.')
