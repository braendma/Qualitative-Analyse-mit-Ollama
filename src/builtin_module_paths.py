"""Explicit file argument contracts for shipped analysis entry points.

The process may run in the installation directory while its artifacts remain in
the original run directory. Custom source scripts retain their old cwd contract.
This module never imports an analysis CLI, reads study configuration, or starts
a process. Import-time logs and non-CLI outputs need the same run-root contract
at their own write boundaries; argument normalization alone does not move them.
"""
from dataclasses import dataclass
from pathlib import Path

from filesystem_paths import canonical_path, io_path
from project_paths import DEFAULT_CONFIG, SOURCE_DIR
from synthesis_inputs import LEGACY_SOURCES, parse_source


@dataclass(frozen=True)
class PathOption:
    names: tuple
    base: str = 'run'
    default: str | None = None


def _option(names, default=None, base='run'):
    return PathOption(tuple(names.split()), base, default)


def _config(alias=True, required=False):
    return _option('--config -c' if alias else '--config',
                   None if required else str(DEFAULT_CONFIG))


def _outputs(stem, aliases=True):
    return (_option('--out-md -o' if aliases else '--out-md', stem + '.md'),
            _option('--out-json -x' if aliases else '--out-json', stem + '.json'))


_CSV = _option('--csv', base='config')
_CLUSTERS = _option('--clusters-json -j', 'clusters_output.json')
_IDMAP = _option('--idmap-json -m', 'id_to_text.json')
_SUMMARY = _option('--summary-json -s', 'summary_v1.json')

# Deliberately explicit: filenames and suffixes are never used to guess a type.
BUILTIN_PATH_OPTIONS = {
    'clusterer.py': (_config(), _option('--csv -i'),
        _option('--out-md -o', 'clusterer_output.md'),
        _option('--out-json -x', 'clusters_output.json'), _IDMAP,
        _option('--plots-dir -p', 'plots')),
    'summarizer.py': (_config(), _CLUSTERS, _IDMAP, _CSV,
                      *_outputs('summary_v1')),
    'swot.py': (_config(), _CLUSTERS, _IDMAP, _SUMMARY, _CSV,
                *_outputs('swot_v1')),
    'meta_swot.py': (_config(), _option('--swot-json -s', 'swot_v1.json'),
                     _CSV, *_outputs('meta_swot_v1')),
    'person_analysis.py': (_config(), _CLUSTERS, _IDMAP, _SUMMARY, _CSV,
                           *_outputs('person_analysis_v1')),
    'person_comparison.py': (_config(),
        _option('--person-json -j', 'person_analysis_v1.json'), _CSV,
        *_outputs('person_comparison_v1')),
    'contrast_analysis.py': (_config(),
        _option('--person-json -p', 'person_analysis_v1.json'),
        _option('--comparison-json -j', 'person_comparison_v1.json'), _CSV,
        *_outputs('contrast_analysis_v1')),
    'relation_analysis.py': (_config(), _CLUSTERS, _IDMAP, _SUMMARY, _CSV,
                             *_outputs('relation_analysis_v1')),
    'ambiguity_analysis.py': (_config(),
        _option('--person-json -p', 'person_analysis_v1.json'), _IDMAP, _CSV,
        *_outputs('ambiguity_analysis_v1')),
    'evidence_audit.py': (_config(), _option('--swot-json', 'swot_v1.json'),
        _option('--meta-swot-json', 'meta_swot_v1.json'),
        _option('--contrast-json', 'contrast_analysis_v1.json'),
        _option('--ambiguity-json', 'ambiguity_analysis_v1.json'), _IDMAP,
        *_outputs('evidence_audit_v1')),
    'overall_synthesis.py': (_config(), _option('--source-json', base='source'),
        _option('--meta-swot-json'), _option('--comparison-json'),
        _option('--contrast-json'), _CSV, *_outputs('overall_synthesis_v1')),
    'coding_agreement.py': (_config(),
        _option('--input-csv -i', base='config'),
        _option('--codebook-csv', base='config'),
        _option('--verify-json', 'code_verification_v1.json'),
        _option('--blind-json', 'blind_coding_v1.json'),
        *_outputs('coding_agreement_v1', False),
        _option('--out-confusion-png', 'coding_agreement_confusion.png'),
        _option('--log-file', 'coding_agreement.log')),
    'review_queue.py': (_config(False), _option('--input-csv', base='config'),
        _option('--agreement-json', 'coding_agreement_v1.json'),
        _option('--verify-json', 'code_verification_v1.json'),
        _option('--blind-json', 'blind_coding_v1.json'),
        _option('--audit-json', 'evidence_audit_v1.json'),
        _option('--queue-json', 'review_queue.json'),
        _option('--out-html', 'review_queue.html'),
        _option('--out-md', 'review_queue.md'), _option('--import-decisions'),
        _option('--decisions-out', 'review_decisions.json')),
}
for _name in ('code_verification', 'blind_coding'):
    BUILTIN_PATH_OPTIONS[_name + '.py'] = (_config(),
        _option('--input-csv -i', base='config'),
        _option('--codebook-csv', base='config'), _option('--idmap-json'),
        *_outputs(_name + '_v1', False), _option('--log-file', _name + '.log'),
        _option('--checkpoint'), _option('--mock-responses-json', base='config'))
for _script, _stem in (
        ('coverage_analysis', 'coverage'),
        ('information_loss_analysis', 'information_loss'),
        ('codebook_diagnostics', 'codebook_diagnostics'),
        ('stability_analysis', 'stability'),
        ('sensitivity_analysis', 'sensitivity')):
    BUILTIN_PATH_OPTIONS[_script + '.py'] = (
        _config(False, required=True), _option('--input-csv'),
        _option('--run-dir', '.'), *_outputs(_stem, False))


def _verified_options(script):
    candidate = Path(script)
    options = BUILTIN_PATH_OPTIONS.get(candidate.name)
    if options is None or not candidate.is_absolute():
        return None
    expected = canonical_path(SOURCE_DIR) / candidate.name
    if (io_path(candidate) != io_path(expected)
            or canonical_path(candidate) != expected
            or not io_path(candidate).is_file()):
        return None
    return options


def _occurrences(args, options):
    """Read exact registered flags, leaving all unknown tokens untouched."""
    by_name = {name: option for option in options for name in option.names}
    found = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == '--':
            break
        name, separator, value = token.partition('=')
        option = by_name.get(name)
        prefix = name + '=' if separator else ''
        if option is None and name.startswith('--'):
            matches = sorted(flag for flag in by_name
                             if flag.startswith('--') and flag.startswith(name))
            if matches:
                # Some CLIs accept argparse abbreviations. Leaving one opaque
                # while appending an explicit default could silently override
                # the user's path; require a complete declared flag instead.
                raise ValueError('Abgekürzte Pfadoption ' + name
                                 + ' ist nicht eindeutig abgesichert. Vollständige Option verwenden: '
                                 + ', '.join(matches) + '.')
        # argparse also accepts attached values for a declared short alias.
        if option is None and token.startswith('-') and not token.startswith('--'):
            option = by_name.get(token[:2])
            if option is not None and len(token) > 2:
                name, prefix, value = token[:2], token[:2], token[2:]
        if option is not None:
            value_index = index
            if not prefix:
                index += 1
                if index >= len(args) or args[index].startswith('-'):
                    raise ValueError('Dateipfad fehlt nach ' + name + '.')
                value_index, value = index, args[index]
            found.append((option, value_index, prefix, value))
        index += 1
    return found


def _absolute(value, base):
    # Config input '' historically falls back to its configured value. Leaving
    # empty values untouched also preserves the CLI's own invalid-output error.
    if not value:
        return value
    path = Path(value)
    return str(io_path(path if path.is_absolute() else base / path))


def prepare_builtin_arguments(script, args, run_root):
    """Normalize only shipped analysis file arguments, or return None for custom.

    All supplied aliases, argument order and repeated options survive. Explicit
    config-relative inputs use the last config flag, just as argparse does.
    Missing optional inputs/checkpoints remain missing; diagnostics keep their
    required config/input arguments. Defaults are inserted before a '--' marker.
    """
    options = _verified_options(script)
    if options is None:
        return None
    result = list(args)
    if any(not isinstance(arg, str) for arg in result):
        raise TypeError('Modulargumente müssen Zeichenketten sein.')
    # Join '..' against ordinary canonical syntax, then add the IO prefix.
    # Extended Windows paths deliberately reject unresolved dot components.
    root = canonical_path(run_root)
    occurrences = _occurrences(result, options)
    config = next(option for option in options if '--config' in option.names)
    selected_config = config.default
    for option, _, _, value in occurrences:
        if option is config:
            selected_config = value
    config_parent = (canonical_path(_absolute(selected_config, root)).parent
                     if selected_config else root)
    present = {option.names[0] for option, _, _, _ in occurrences}
    for option, index, prefix, value in occurrences:
        if option.base == 'source':
            label, source = parse_source(value)
            value = label + '=' + _absolute(source, root)
        else:
            value = _absolute(value, config_parent if option.base == 'config' else root)
        result[index] = prefix + value
    additions = []
    for option in options:
        if option.names[0] not in present and option.default is not None:
            additions.extend((option.names[0], _absolute(option.default, root)))
    if Path(script).name == 'overall_synthesis.py':
        source_flags = {'--source-json'} | {flag for flag, _, _ in LEGACY_SOURCES}
        if not present.intersection(source_flags):
            for flag, _, default in LEGACY_SOURCES:
                additions.extend((flag, _absolute(default, root)))
    stop = result.index('--') if '--' in result else len(result)
    result[stop:stop] = additions
    return result
