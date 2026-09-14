"""Build Python child commands without changing Source caller arguments.

The frozen entry list is part of the application, never extended by a YAML.
Actual bundled import/provenance verification remains a packaging requirement.
"""
from pathlib import Path
import sys

from project_paths import SOURCE_DIR


INTERNAL_SCRIPT_FLAG = '--internal-script'
APPROVED_SCRIPTS = frozenset({
    '00_WORKFLOW_RUNNER.py', 'local_app.py', 'managed_ollama.py',
    'codebook_refinement.py',
    'clusterer.py', 'code_verification.py', 'blind_coding.py',
    'coding_agreement.py', 'summarizer.py', 'swot.py', 'meta_swot.py',
    'person_analysis.py', 'person_comparison.py', 'contrast_analysis.py',
    'relation_analysis.py', 'ambiguity_analysis.py', 'evidence_audit.py',
    'review_queue.py', 'overall_synthesis.py', 'coverage_analysis.py',
    'information_loss_analysis.py', 'codebook_diagnostics.py',
    'stability_analysis.py', 'sensitivity_analysis.py',
})


def validate_script(script):
    """Validate frozen dispatch before runtime startup; Source keeps old rules."""
    path = Path(script)
    if not getattr(sys, 'frozen', False):
        return path
    try:
        source = SOURCE_DIR.resolve(strict=True)
        canonical = path.resolve(strict=True)
        valid = (path.is_absolute() and path == canonical
                 and path.parent == source and path.name in APPROVED_SCRIPTS
                 and path.is_file())
    except (OSError, RuntimeError, ValueError):
        valid = False
    if not valid:
        raise ValueError('Dieses Skript ist im installierten Programm nicht als Einstieg freigegeben. '
                         'Ein unverändertes Standardmodul verwenden; eigene Skripte benötigen den Sourcebetrieb.')
    return canonical


def python_command(script, args=()):
    """Return argv, never a shell string or a basename-based replacement."""
    checked = validate_script(script)
    if getattr(sys, 'frozen', False):
        return [sys.executable, INTERNAL_SCRIPT_FLAG, checked.name, *args]
    return [sys.executable, str(script), *args]
