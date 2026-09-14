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
    'coverage': (),
    'information_loss': (),
    'codebook_diagnostics': (),
    'stability': (),
    'sensitivity': (),
}


def catalog(config, modules):
    from thematic_pipeline import modes as thematic_modes
    perspectives = thematic_modes(config)
    prompts=config.get('prompts',{})
    if not isinstance(prompts,dict):raise ValueError('Die Prompt-Konfiguration muss eine Zuordnung sein.')
    result=[]
    for module in modules:
        mid=module['id'];keys=PROMPT_KEYS.get(mid,(mid,));templates=[]
        if mid in ('stability', 'sensitivity'):
            diagnostics=config.get('diagnostics',{})
            settings=diagnostics.get(mid,{}) if isinstance(diagnostics,dict) else {}
            targets=settings.get('modules',[]) if isinstance(settings,dict) else []
            required=set(targets) if isinstance(targets,list) and all(isinstance(x,str) for x in targets) else set()
            while True:
                expanded=required|{d for m in modules if m['id'] in required for d in m.get('depends_on',[])}
                if expanded==required:break
                required=expanded
            keys=tuple(dict.fromkeys(k for m in modules if m['id'] in required for k in PROMPT_KEYS.get(m['id'],())))
        for key in keys:
            value=prompts.get(key)
            if not isinstance(value,dict):continue
            system=value.get('system','') or '';user=value.get('user','') or ''
            if not isinstance(system,str) or not isinstance(user,str):continue
            templates.append({'key':key,'system':system,'user':user,
                'placeholders':sorted(set(re.findall(r'\{([A-Za-z_][A-Za-z0-9_]*)\}',system+'\n'+user)))})
        if mid == 'sensitivity':
            variants=settings.get('variants',[]) if isinstance(settings,dict) else []
            for variant in variants if isinstance(variants,list) else []:
                if not isinstance(variant,dict) or not isinstance(variant.get('prompts',{}),dict):continue
                for key, fields in variant.get('prompts',{}).items():
                    if key not in keys or not isinstance(fields,dict):continue
                    base=prompts.get(key,{})
                    if not isinstance(base,dict):continue
                    system=fields.get('system',base.get('system',''));user=fields.get('user',base.get('user',''))
                    if not isinstance(system,str) or not isinstance(user,str):continue
                    templates.append({'key':str(variant.get('id','Variante'))+' / '+key,'system':system,'user':user,
                        'placeholders':sorted(set(re.findall(r'\{([A-Za-z_][A-Za-z0-9_]*)\}',system+'\n'+user)))})
            note='Basisvorlagen und ausdrücklich gespeicherte Promptvarianten. Jede Einstellung erzeugt zusätzliche Modellaufrufe; der anschließende Vergleich benötigt keine eigene Modellanfrage. Diese Ansicht belegt nicht, dass jeder Anfragepfad tatsächlich verwendet wurde.'
        elif mid == 'stability':
            note='Die Wiederholungen verwenden die konfigurierten Vorlagen ihrer Zielmodule und Vorstufen. Dafür entstehen zusätzliche Modellaufrufe; der anschließende Stabilitätsvergleich selbst benötigt keine Modellanfrage.'
        elif not keys:
            note='Dieses Modul arbeitet ohne eigenen LLM-Aufruf. Es verarbeitet vorhandene Codierungen oder Analyseergebnisse.'
        elif not templates:
            note='Keine passende Vorlage in dieser Konfiguration vorhanden. Das Modul kann Vorgaben aus dem Programmcode verwenden; hier wird kein Prompt erfunden.'
        else:
            note='Vorlagen aus der gewählten Konfiguration. Daten, Projektkontext und weitere Regeln werden erst beim Modellaufruf eingesetzt. Zusätzliche Hilfs-, Verdichtungs- und Reparaturanweisungen sowie Antwortschemata können aus dem Programmcode hinzukommen.'
        perspective_targets = required if mid in ('stability', 'sensitivity') else {mid}
        extra_targets = sorted(target for target in perspective_targets if perspectives.get(target, 'qualitative') != 'qualitative')
        if extra_targets:
            from thematic_interpretation import SYSTEM as frequency_system
            from thematic_assignment import SYSTEM as assignment_system
            from thematic_pipeline import FULL_ASSIGNMENT_MODULES
            for target in extra_targets:
                if target in FULL_ASSIGNMENT_MODULES:
                    templates.append({'key':target+' / thematic_assignment', 'system':assignment_system,
                                      'user':'Zur Laufzeit: feste Themen, vollständige Originaleinheiten und angeforderte Matrixzellen.', 'placeholders':[]})
                templates.append({'key':target+' / frequency_interpretation', 'system':frequency_system,
                                  'user':'Zur Laufzeit: Thema, qualitativer Ausgangsbefund, berechnete Kennzahlen und Gegenpositionsmaterial.', 'placeholders':[]})
            note += ' Zusätzliche Perspektiven verwenden diese festen Programmanweisungen; beide Perspektiven teilen eine Zuordnungsmatrix.'
        result.append({'id':mid,'name':module['name'],'templates':templates,'note':note})
    # Referenced shared strings are shown separately and never expanded into research material.
    referenced=set(p for m in result for t in m['templates'] for p in t['placeholders'])
    rules=[{'key':key,'text':value} for key,value in prompts.items() if key in referenced and isinstance(value,str)]
    return {'modules':result,'rules':rules}
