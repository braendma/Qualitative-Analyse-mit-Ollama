"""Recheck actual later-stage inputs without silently changing runtime memory."""
import threading
import logging
import os
from progress_events import update_progress
from llm_client import ContextBudgetError


LOCK = threading.RLock()
MAXIMUM = 0
SCOPE = None


def require_messages(messages, settings, answer=None):
    global MAXIMUM, SCOPE
    limit = int(settings.get('num_ctx', 32768))
    reserve = int(settings.get('max_tokens', 2048) if answer is None else answer)
    needed = sum(len(m['content'].encode('utf-8')) + 32 for m in messages) + reserve + 256
    with LOCK:
        scope = (os.environ.get('WORKFLOW_PROGRESS_FILE'), os.environ.get('WORKFLOW_MODULE'))
        if scope != SCOPE:
            SCOPE, MAXIMUM = scope, 0
        if needed > MAXIMUM:
            logging.getLogger('context').info(
                'Laufzeit-Kontextprüfung: konservative Rechengrenze=%s, Kontext=%s, Antwortreserve=%s; keine automatische Erhöhung.',
                needed, limit, reserve)
        MAXIMUM = max(MAXIMUM, needed)
        update_progress(context_required=MAXIMUM, context_limit=limit)
        if needed > limit:
            update_progress(context_blocked=True)
    if needed > limit:
        raise ContextBudgetError(
            f'Die tatsächlich entstandene Eingabe benötigt nach der konservativen Kontextprüfung '
            f'bis zu {needed} Tokens einschließlich Antwortreserve; eingestellt sind {limit}. '
            'Keine Texte wurden gekürzt. Kontext und Speicherschätzung erneut prüfen; '
            'gegebenenfalls weniger parallele Anfragen wählen. Eine neue Konfiguration benötigt '
            'einen neuen Lauf. Das reservierte Kontextfenster wird nicht automatisch erhöht.')
    return needed
