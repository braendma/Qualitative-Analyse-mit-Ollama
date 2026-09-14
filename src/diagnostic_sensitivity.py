"""Pure sensitivity planning on the existing controlled-repetition contract.

No dispatch, model lookup or file writes. Runtime evidence is still required to
establish which planned conditions were actually used by accepted requests.
"""
import copy
import math
import re
from collections import Counter

from coding_validation_common import load_codebook, load_segments
from context_preflight import check_context, require_context
from diagnostic_repetitions import prepare_repetitions
from llm_providers import transport_selection
from prompt_catalog import PROMPT_KEYS
from provider_keys import reject_secret_settings
from runtime_evidence import _canonical
from runtime_support import fingerprint

MAX_CONFIGURATIONS = 10  # Includes the unchanged reference configuration.
LLM_PARAMETERS = {'model', 'temperature', 'num_ctx', 'max_tokens', 'think'}
PLACEHOLDERS = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)\}')


def _effective_value(key, value, provider):
    if key == 'model':
        return _canonical(value) if provider.startswith('ollama_') else value
    if key == 'temperature':
        return float(value)
    return value


def _llm_values(settings):
    """Explicit values avoid different module defaults masquerading as one baseline."""
    for key in ('temperature', 'num_ctx', 'max_tokens', 'model'):
        if key not in settings:
            raise ValueError('Sensitivität benötigt eine explizite Basiseinstellung llm.' + key + '.')
    if not isinstance(settings['model'],str) or not settings['model'] or settings['model'] != settings['model'].strip():
        raise ValueError('Sensitivität: Modellname muss nicht leerer Text ohne äußeren Leerraum sein.')
    temperature=settings['temperature']
    if type(temperature) not in (int, float) or not math.isfinite(temperature) or not 0 <= temperature <= 2:
        raise ValueError('Sensitivität: Temperatur muss eine endliche Zahl zwischen 0 und 2 sein.')
    for key in ('num_ctx', 'max_tokens'):
        if type(settings[key]) is not int or settings[key] < 1:
            raise ValueError('Sensitivität: ' + key + ' muss eine positive ganze Zahl sein.')
    if settings['max_tokens'] >= settings['num_ctx']:
        raise ValueError('Sensitivität: Antwortlimit muss kleiner als das Kontextfenster sein.')
    think=settings.get('think')
    if think is not None and type(think) is not bool and not (isinstance(think,str) and think in ('low','medium','high','max')):
        raise ValueError('Sensitivität: Thinking benötigt true, false, low, medium, high oder max.')


def _variant(base, variant, provider, prompt_keys):
    if not isinstance(variant,dict) or set(variant)-{'id','llm','prompts'}:
        raise ValueError('Sensitivitätsvariante benötigt id und nur llm und/oder prompts.')
    vid=variant.get('id')
    if not isinstance(vid,str) or not re.fullmatch('[a-z][a-z0-9_-]{0,39}',vid) or vid == 'baseline':
        raise ValueError('Varianten-ID: 1–40 Kleinbuchstaben, Ziffern, _ oder -; baseline ist reserviert.')
    reject_secret_settings(variant)
    overrides=variant.get('llm',{})
    prompts=variant.get('prompts',{})
    if not isinstance(overrides,dict) or set(overrides)-LLM_PARAMETERS or not isinstance(prompts,dict):
        raise ValueError('Nur tatsächlich unterstützte Modellparameter und Promptvorlagen variieren; Anbieter, Schlüssel und Pfade bleiben fest.')
    if not overrides and not prompts:
        raise ValueError('Sensitivitätsvariante enthält keine Veränderung.')
    if provider not in ('ollama_local','ollama_cloud') and set(overrides)&{'temperature','think'}:
        raise ValueError('Temperatur und Thinking werden von diesem Anbieteradapter nicht übertragen.')
    if provider != 'ollama_local' and 'num_ctx' in overrides:
        raise ValueError('Cloud-Kontext ist nur eine lokale Eingabegrenze, keine übertragene Modellvariante.')
    result=copy.deepcopy(base)
    result['llm'].update(overrides)
    _llm_values(result['llm'])
    selected=transport_selection(result['llm'],result['llm']['model'])
    if selected['provider'] != provider:
        raise ValueError('Anbieterwechsel ist innerhalb der Sensitivitätsanalyse nicht erlaubt.')
    changes=[]
    for key,value in overrides.items():
        before=base['llm'].get(key)
        if _effective_value(key,before,provider) == _effective_value(key,value,provider):
            raise ValueError('Variante enthält eine unveränderte Einstellung: llm.' + key)
        changes.append({'path':'llm.'+key,'before':before,'after':value})
    original_prompts=base.get('prompts',{})
    if not isinstance(original_prompts,dict):
        raise ValueError('Basis benötigt eine gültige Promptkonfiguration.')
    for key,fields in prompts.items():
        if key not in prompt_keys:
            raise ValueError('Promptvorlage wird von den gewählten Modulen nicht konfigurierbar verwendet: '+str(key))
        original=original_prompts.get(key)
        if (not isinstance(original,dict) or not isinstance(fields,dict) or not fields
                or set(fields)-{'system','user'}):
            raise ValueError('Promptvariante benötigt vorhandene system-/user-Vorlagen.')
        for field,value in fields.items():
            before=original.get(field)
            if not isinstance(before,str) or not isinstance(value,str) or not value.strip():
                raise ValueError('Promptvorlage muss vorhandenen, nicht leeren Text ersetzen.')
            if Counter(PLACEHOLDERS.findall(before)) != Counter(PLACEHOLDERS.findall(value)):
                raise ValueError('Promptvariante muss alle Platzhalter unverändert oft beibehalten.')
            if ' '.join(before.split()) == ' '.join(value.split()):
                raise ValueError('Promptvariante ändert nur Leerraum oder ist unverändert.')
            result['prompts'][key][field]=value
            # Metadata can be displayed without exposing the prompt text itself.
            changes.append({'path':'prompts.'+key+'.'+field,
                            'before_sha256':fingerprint(before),'after_sha256':fingerprint(value)})
    return vid,result,changes


def prepare_sensitivity(config_path, module_ids, variants, *, repetitions=2):
    """Plan baseline + 1–9 explicit variants, each with 2–20 fresh repetitions.

    Variants are relative to the baseline, never cumulatively applied. Same
    materials, module closure, person mapping and privacy boundary throughout.
    """
    if not isinstance(variants,list) or not 1 <= len(variants) < MAX_CONFIGURATIONS:
        raise ValueError('Sensitivität benötigt 1–9 Varianten zusätzlich zur unveränderten Basis.')
    base_plan=prepare_repetitions(config_path,module_ids,repetitions=repetitions)
    base=base_plan['config'];provider=base_plan['provider']
    _llm_values(base['llm'])
    prompt_keys={key for mid in base_plan['effective_modules'] for key in PROMPT_KEYS.get(mid,())}
    prompt_keys.discard('self_repair')  # Conditional repair templates are not independent treatment targets.
    if base.get('coding_agreement',{}).get('label_mode') == 'multi_label':
        prompt_keys.discard('blind_coding')  # This path uses blind_unit_messages, not the configured template.
    configurations=[{'configuration_id':'baseline','config':copy.deepcopy(base),'changes':[]}]
    ids={'baseline'}
    for variant in variants:
        vid,config,changes=_variant(base,variant,provider,prompt_keys)
        if vid in ids:
            raise ValueError('Varianten-IDs müssen eindeutig sein.')
        ids.add(vid)
        configurations.append({'configuration_id':vid,'config':config,'changes':changes})
    seen=set()
    segments=load_segments(base['paths']['input_csv'],base['columns'])
    book,_=load_codebook(base['paths']['category_system_csv'])
    samples=[]
    for item in configurations:
        canonical=copy.deepcopy(item['config'])
        for key in LLM_PARAMETERS:
            if key in canonical['llm']:
                canonical['llm'][key]=_effective_value(key,canonical['llm'][key],provider)
        for fields in canonical.get('prompts',{}).values():
            if isinstance(fields,dict):
                for field in ('system','user'):
                    if isinstance(fields.get(field),str):
                        fields[field]=' '.join(fields[field].split())
        effective=fingerprint(canonical)
        if effective in seen:
            raise ValueError('Doppelte wirksame Konfigurationen sind keine unterschiedlichen Sensitivitätsvarianten.')
        seen.add(effective)
        item['configuration_fingerprint']=fingerprint(item['config'])
        item['effective_configuration_fingerprint']=effective
        item['context_preflight']=check_context(item['config'],segments,book,base_plan['effective_modules'])
        try:
            require_context(item['context_preflight'])
        except ValueError as exc:
            raise ValueError(item['configuration_id']+': '+str(exc)) from None
        item['joint_changes']=len(item['changes']) > 1
        for number in range(1,repetitions+1):
            samples.append({'sample_id':item['configuration_id']+f'-repeat-{number:03d}',
                'configuration_id':item['configuration_id'],
                'configuration_fingerprint':item['configuration_fingerprint']})
    plan={'schema_version':1,'kind':'sensitivity','source_config':base_plan['source_config'],
        'source_provenance':base_plan['source_provenance'],'requested_modules':base_plan['requested_modules'],
        'effective_modules':base_plan['effective_modules'],'added_prerequisites':base_plan['added_prerequisites'],
        'variants':copy.deepcopy(variants),'repetitions':repetitions,'provider':provider,
        'configurations':configurations,'samples':samples,'configuration_count':len(configurations),
        'module_executions':len(samples)*len(base_plan['effective_modules']),'model_calls':None,
        'parameter_status':'configured_not_runtime_verified',
        'notes':['Sehr hoher Zusatzaufwand; jede Konfiguration wird mit frischen Vorstufen wiederholt.',
                 'Mehrere gleichzeitig geänderte Parameter erlauben keine isolierte Ursachenattribution.',
                 'Reparatur- und Verdichtungsanfragen können eigene Temperaturen und Antwortlimits verwenden.',
                 'Modellverfügbarkeit, Speicher, Parameterunterstützung und Laufzeitnachweise sind vor bzw. während Ausführung zu prüfen.',
                 'Vorprüfungen kennen spätere Modellbefunde nicht; serverinterne Parameterdurchsetzung bleibt ungeprüft.',
                 'Sensitivität ist kein methodischer Fehler. Einzelne Promptformulierungen benötigen fachliche Prüfung.',
                 'Dies ist ausschließlich ein Plan; keine Variante wurde ausgeführt.']}
    plan['plan_fingerprint']=fingerprint(plan)
    return plan
