"""Per-person reduction with fixed identities, complete input and source receipts."""
import json
from runtime_support import fingerprint, PartCheckpoint
from summary_reduction import reduce_prompt
from progress_events import update_progress
from parallel_items import completed_items


def prepare_people(persons, build_prompt, params, summarize):
    names = sorted(persons)
    original = {'personen': [persons[name] for name in names]}
    system, user = build_prompt(original)
    context = int(params.get('num_ctx', 16384))
    reserve = int(params.get('max_tokens', 6000))
    fits = lambda s,u: len(s.encode('utf-8')) + len(u.encode('utf-8')) + reserve + 1024 <= context
    if fits(system,user):
        return original, {'used':False,'source_sha256':fingerprint(persons)}
    # Each identity is assigned by code, never inferred or merged by a model.
    skeleton = {'personen':[{'person':name,'verdichtete_personenanalyse':''} for name in names]}
    fixed_system, fixed_user = build_prompt(skeleton)
    available = context - reserve - 1024 - len((fixed_system+fixed_user).encode('utf-8'))
    target = min(1200, available // max(1,len(names)) - 64)
    if target < 256:
        raise ValueError('Personenvergleich: Zu wenig Kontext, um alle Personen getrennt zu berücksichtigen.')
    update_progress(phase='person_reduction',completed=0,total=len(names),unit='persons')
    def compute(name):
        source = json.dumps(persons[name],ensure_ascii=False,indent=2)
        cp = PartCheckpoint('comparison_person_reduction',params)
        value = cp.run(name, {'source':source,'target_bytes':target},
            lambda: reduce_prompt(fixed_system,source,params,summarize,target_bytes=target,
                                  allow_target_overflow=True))
        if not isinstance(value,str) or not value.strip():
            raise ValueError('Unvollständige Personenverdichtung.')
        return {'person':name,'verdichtete_personenanalyse':value}
    entries=[None]*len(names)
    for done,(index,result) in enumerate(completed_items(names,compute,min(2,params.get('parallel_workers',1))),1):
        entries[index]=result
        update_progress(completed=done)
    payload={'personen':entries}
    if not fits(*build_prompt(payload)):
        raise ValueError('Personenvergleich passt auch nach vollständiger Verdichtung nicht ins Kontextfenster.')
    ledger={'used':True,'method':'per_person_hierarchical_reduction','source_sha256':fingerprint(persons),
            'target_bytes_per_person':target,'context':context,
            'budget_method':'shared_final_prompt_with_soft_person_targets',
            'actual_bytes_per_person':{entry['person']:len(entry['verdichtete_personenanalyse'].encode('utf-8')) for entry in entries},
            'sources':{name:{'source_sha256':fingerprint(persons[name]),
                            'source_person':name,'summary':entries[i]['verdichtete_personenanalyse']}
                       for i,name in enumerate(names)},
            'note':'Alle vollständigen Personenanalysen gingen getrennt in die Verdichtung ein. '
                   'Der Vergleich verwendet diese Verdichtungen; Details können verloren gehen. '
                   'Originalanalysen und Belege bleiben in person_analysis_v1.json erhalten.'}
    return payload,ledger
