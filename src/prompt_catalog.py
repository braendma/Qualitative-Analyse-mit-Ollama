"""Read-only catalog of configured templates, without interpolating study inputs."""
import re

PROMPT_KEYS = {
    'clusterer': ('cluster_analysis', 'self_repair'),
    'code_verification': ('code_verification',),
    'blind_coding': ('blind_coding',),
    'coding_agreement': (),
    'summarizer': ('cluster_summary', 'category_summary'),
    'swot': ('swot_analysis',),
    'meta_swot': ('meta_swot',),
    'person_analysis': ('person_analysis',),
    'person_comparison': ('person_comparison',),
    'contrast_analysis': ('contrast_analysis',),
    'relation_analysis': ('relation_analysis',),
    'ambiguity_analysis': ('ambiguity_analysis',),
    'evidence_audit': ('evidence_audit',),
    'review_queue': (),
    'overall_synthesis': ('overall_synthesis',),
}


def catalog(config, modules):
    prompts=config.get('prompts',{})
    if not isinstance(prompts,dict):raise ValueError('Die Prompt-Konfiguration muss eine Zuordnung sein.')
    result=[]
    for module in modules:
        mid=module['id'];keys=PROMPT_KEYS.get(mid,(mid,));templates=[]
        for key in keys:
            value=prompts.get(key)
            if not isinstance(value,dict):continue
            system=value.get('system','') or '';user=value.get('user','') or ''
            if not isinstance(system,str) or not isinstance(user,str):continue
            templates.append({'key':key,'system':system,'user':user,
                'placeholders':sorted(set(re.findall(r'\{([A-Za-z_][A-Za-z0-9_]*)\}',system+'\n'+user)))})
        if not keys:
            note='Dieses Modul arbeitet ohne eigenen LLM-Aufruf. Es verarbeitet vorhandene Codierungen oder Analyseergebnisse.'
        elif not templates:
            note='Keine passende Vorlage in dieser Konfiguration vorhanden. Das Modul kann Vorgaben aus dem Programmcode verwenden; hier wird kein Prompt erfunden.'
        else:
            note='Vorlagen aus der gewählten Konfiguration. Daten, Projektkontext und weitere Regeln werden erst beim Modellaufruf eingesetzt. Zusätzliche Hilfs-, Verdichtungs- und Reparaturanweisungen sowie Antwortschemata können aus dem Programmcode hinzukommen.'
        result.append({'id':mid,'name':module['name'],'templates':templates,'note':note})
    # Referenced shared strings are shown separately and never expanded into research material.
    referenced=set(p for m in result for t in m['templates'] for p in t['placeholders'])
    rules=[{'key':key,'text':value} for key,value in prompts.items() if key in referenced and isinstance(value,str)]
    return {'modules':result,'rules':rules}
