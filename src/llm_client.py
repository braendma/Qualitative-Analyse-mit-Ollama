"""Bounded Ollama requests. Credentials come only from the named environment variable."""
import logging
import os
import ssl
import time
from urllib.parse import urlparse

logger = logging.getLogger('llm_client')


class LLMError(RuntimeError):
    pass


class LLMTransportError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


class ContextBudgetError(LLMError):
    pass


def request_chat(backend, request, settings, *, api_key=None):
    from llm_providers import transport_selection, HTTPChatClient
    try:
        selected = transport_selection(settings, request['model'])
    except ValueError as exc:
        raise LLMTransportError(str(exc)) from None
    host = selected['host']
    provider = selected['provider']
    cloud = provider != 'ollama_local'
    schema = settings.get('response_schema')
    if schema and not cloud and settings.get('structured_outputs', True):
        request['format'] = schema
    num_ctx = int(settings.get('num_ctx', 32768))
    reserve = int(request['options']['num_predict'])
    # UTF-8 byte count is a conservative upper bound for supported byte-level tokenizers.
    size = sum(len(m['content'].encode('utf-8')) + 32 for m in request['messages'])
    if size + reserve + 256 > num_ctx:
        raise ContextBudgetError(
            f'Eingabe überschreitet das konservative Kontextbudget ({size} Bytes + '
            f'{reserve} Ausgabetokens; num_ctx={num_ctx}). Eingabe aufteilen oder Kontext erhöhen.')
    if not cloud:
        request['options']['num_ctx'] = num_ctx
    headers = {}
    key = api_key or os.environ.get(selected['api_key_env'])
    if cloud and not key:
        raise LLMTransportError('Cloud-Schlüssel fehlt für den gewählten Anbieter.')
    if provider == 'ollama_cloud': headers['Authorization'] = 'Bearer ' + key
    if provider in ('ollama_local', 'ollama_cloud'):
        client = backend.Client(host=host, headers=headers, verify=ssl.create_default_context(),
                                timeout=float(settings.get('timeout_seconds', 180))) if hasattr(backend, 'Client') else backend
    else:
        client = HTTPChatClient(provider, key, float(settings.get('timeout_seconds', 180)))
    attempts = int(settings.get('max_attempts', 3))
    if not 1 <= attempts <= 5:
        raise ValueError('max_attempts muss zwischen 1 und 5 liegen.')
    started = time.monotonic()
    for attempt in range(attempts):
        try:
            from progress_events import request_event
            request_event(start=True)
            response = client.chat(**request)
            request_event()
            logger.info('LLM request completed: model=%s attempt=%s elapsed=%.2fs',
                        request['model'], attempt + 1, time.monotonic() - started)
            return response
        except Exception as exc:
            from progress_events import update_progress
            update_progress(request_active=False)
            status = getattr(exc, 'status_code', None)
            error = str(getattr(exc, 'error', exc)).lower()
            if 'think' in request and any(s in error for s in (
                    "unexpected keyword argument 'think'", 'does not support thinking', 'invalid think value')):
                logger.warning('Thinking-Einstellung wird vom Modell/Client nicht unterstützt; verwende Modellstandard.')
                request.pop('think')
                return request_chat(backend, request, {**settings, 'max_attempts': max(1, attempts - attempt)}, api_key=api_key)
            retryable = status in (408, 429, 500, 502, 503, 504) or (
                status is None and not isinstance(exc, (ValueError, TypeError)))
            if not retryable or attempt + 1 == attempts:
                # Do not include arbitrary server/transport strings (may contain secrets).
                raise LLMTransportError(f'KI-Anfrage fehlgeschlagen ({type(exc).__name__}, Status {status}).') from None
            time.sleep(min(float(settings.get('retry_delay_seconds', 1)) * 2 ** attempt, 8))
