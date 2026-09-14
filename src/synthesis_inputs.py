"""Resolve actual synthesis CLI sources and bind aliases to declared artifacts.

Labels are presentation names, never module identities. File integrity and source
schema checks belong to the caller; this helper performs no reads or model calls.
"""
from pathlib import Path
from filesystem_paths import canonical_path


LEGACY_SOURCES = (
    ('--meta-swot-json', 'Meta-SWOT', 'meta_swot_v1.json'),
    ('--comparison-json', 'Personenvergleich', 'person_comparison_v1.json'),
    ('--contrast-json', 'Kontrastanalyse', 'contrast_analysis_v1.json'),
)
SOURCE_MODULES = frozenset(('clusterer', 'summarizer', 'swot', 'meta_swot',
    'person_analysis', 'person_comparison', 'contrast_analysis', 'relation_analysis',
    'ambiguity_analysis', 'evidence_audit'))


def parse_source(value):
    if not isinstance(value, str) or '=' not in value:
        raise ValueError('--source-json erwartet LABEL=DATEI, z. B. Meta-SWOT=meta_swot_v1.json')
    label, path = (part.strip() for part in value.split('=', 1))
    if not label or not path:
        raise ValueError('LABEL und DATEI dürfen nicht leer sein.')
    return label, path


def resolve_sources(source_json=(), *, meta_swot_json=None, comparison_json=None, contrast_json=None):
    """Keep one explicit source set; conflicting aliases never silently win."""
    result = {}
    def add(label, path):
        if label in result:
            raise ValueError('Analytische Quellenbezeichnung mehrfach vergeben: ' + label
                             + '. Jede Quelle benötigt eine eindeutige Bezeichnung.')
        result[label] = path
    for value in source_json:
        add(*parse_source(value))
    for (_, label, _), path in zip(LEGACY_SOURCES, (meta_swot_json, comparison_json, contrast_json)):
        if path is not None:
            if not isinstance(path, str) or not path.strip():
                raise ValueError('Analytischer Quellpfad darf nicht leer sein.')
            add(label, path.strip())
    return result or {label: path for _, label, path in LEGACY_SOURCES}


def sources_from_module(module):
    """Read the same source flags from a saved module argument contract."""
    args = module.get('args', [])
    if not isinstance(args, list) or any(not isinstance(v, str) for v in args):
        raise ValueError('Syntheseargumente müssen als Liste von Zeichenketten vorliegen.')
    explicit, legacy = [], {}
    flags = {flag for flag, _, _ in LEGACY_SOURCES} | {'--source-json'}
    index = 0
    while index < len(args):
        flag, separator, value = args[index].partition('=')
        if flag in flags:
            if not separator:
                index += 1
                if index == len(args) or args[index].startswith('--'):
                    raise ValueError('Analytischer Quellpfad fehlt nach ' + flag + '.')
                value = args[index]
            if flag == '--source-json':
                explicit.append(value)
            else:
                if flag in legacy:
                    raise ValueError('Analytisches Quellenargument mehrfach angegeben: ' + flag)
                legacy[flag] = value
        index += 1
    return resolve_sources(explicit, **{flag[2:].replace('-', '_'): value for flag, value in legacy.items()})


def bind_source_modules(sources, modules, directory):
    """Bind each actual path to exactly one known built-in output declaration.

    This is an identity check, not a claim that the artifact exists or is valid.
    Aliases may differ freely from module names; filename guesses are prohibited.
    """
    from diagnostic_sources import declared_json
    if not isinstance(sources, dict) or not sources:
        raise ValueError('Geprüfte Synthese benötigt eine eindeutige analytische Quellenauswahl.')
    directory = canonical_path(directory)
    declarations = {}
    seen = set()
    for module in modules:
        mid = module.get('id')
        if mid in seen:
            raise ValueError('Doppelte Modul-ID im Synthesequellenvertrag.')
        seen.add(mid)
        if mid not in SOURCE_MODULES:
            continue
        artifact = declared_json(module)
        path = canonical_path(directory / artifact)
        declarations.setdefault(path, []).append(module)
    result = {}
    for label, name in sources.items():
        if not isinstance(label, str) or not label.strip() or not isinstance(name, str) or not name.strip():
            raise ValueError('Synthesequellen benötigen nichtleere Bezeichnungen und Dateipfade.')
        path = canonical_path(directory / name)
        matches = declarations.get(path, [])
        if len(matches) != 1:
            raise ValueError('Synthesequelle ist keinem eindeutigen Analysemodul zugeordnet: ' + label)
        module = matches[0]
        if not module.get('enabled', True) or module.get('script') != module['id'] + '.py':
            raise ValueError('Geprüfte Synthesequelle benötigt ein aktiviertes Standardmodul: ' + label)
        result[label] = {'module_id': module['id'], 'artifact': declared_json(module)}
    return result
