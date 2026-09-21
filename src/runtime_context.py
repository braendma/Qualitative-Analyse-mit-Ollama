"""Recheck actual later-stage inputs without silently changing runtime memory."""
import threading
import logging
import os
from progress_events import update_progress
from llm_client import ContextBudgetError


LOCK = threading.RLock()
MAXIMUM = 0
SCOPE = None


def message_bound(messages, settings, answer=None):
    """Pure sizing for lossless prompt planning, with the execution boundary."""
    reserve = int(settings.get('max_tokens', 2048) if answer is None else answer)
    return sum(len(m['content'].encode('utf-8')) + 32 for m in messages) + reserve + 256


def require_messages(messages, settings, answer=None):
    global MAXIMUM, SCOPE
    limit = int(settings.get('num_ctx', 32768))
    reserve = int(settings.get('max_tokens', 2048) if answer is None else answer)
    needed = message_bound(messages, settings, answer)
    with LOCK:
        scope = (os.environ.get('WORKFLOW_PROGRESS_FILE'), os.environ.get('WORKFLOW_MODULE'))
        if scope != SCOPE:
            SCOPE, MAXIMUM = scope, 0
        if needed > MAXIMUM:
            logging.getLogger('context').info(
                'Laufzeit-Kontextprüfung: konservativer Bedarf=%s, Programmbudget=%s, Antwortreserve=%s; keine gemessene Tokenzahl und keine automatische Erhöhung.',
                needed, limit, reserve)
        MAXIMUM = max(MAXIMUM, needed)
        update_progress(context_required=MAXIMUM, context_limit=limit)
        if needed > limit:
            update_progress(context_blocked=True)
    if needed > limit:
        raise ContextBudgetError(
            f'Kontextbudget im Programm überschritten: konservativer Bedarf {needed}, '
            f'davon Antwortreserve {reserve}; eingestellt sind {limit}. '
            'Die Eingabeschätzung verwendet UTF-8-Bytes und Aufschläge, keine gemessene Tokenzahl. '
            'Keine Texte wurden gekürzt. Lokal zusätzlich Modellfenster und Speicher prüfen. '
            'Bei Cloud begrenzt dieser Wert nur die Vorprüfung im Programm; er verändert das '
            'Kontextfenster des Anbieters nicht. Dessen Modellgrenze bleibt zusätzlich gültig. '
            'Geänderte Einstellungen benötigen einen neuen Lauf; das Budget wird nicht automatisch erhöht.')
    return needed
