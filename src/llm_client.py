"""Bounded Ollama requests. Credentials come only from the named environment variable."""
import logging
import copy
import json
import math
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


def request_timeout_seconds(settings):
    """Validate a finite transport wait; never accept an unlimited timeout."""
    value = settings.get('timeout_seconds', 180)
    if type(value) not in (int, float) or not 1 <= value <= 3600 or not math.isfinite(value):
        raise ValueError('Die Antwortwartezeit (timeout_seconds) muss eine endliche Zahl zwischen 1 und 3600 Sekunden sein.')
    return float(value)


def request_chat(backend, request, settings, *, api_key=None):
    from llm_providers import transport_selection, HTTPChatClient
    timeout = request_timeout_seconds(settings)
    try:
        selected = transport_selection(settings, request['model'])
    except ValueError as exc:
        raise LLMTransportError(str(exc)) from None
    host = selected['host']
    provider = selected['provider']
    cloud = provider != 'ollama_local'
    managed_host = os.environ.get('QUALITATIVE_MANAGED_OLLAMA_HOST')
    if managed_host and not cloud:
        parsed = urlparse(managed_host)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise LLMTransportError('Ungültige lokale Laufzeitadresse.')
        host = managed_host
    schema = settings.get('response_schema')
    if provider == 'ollama_cloud' and schema and settings.get('structured_outputs', True):
        # Cloud has no schema-constrained decoding. Preserve the same response
        # contract as prompt guidance; callers still validate the real response.
        request = copy.deepcopy(request)
        request.pop('format', None)
        guidance = ('Verbindliches Ausgabeformat für diese einzelne Antwort: Gib genau einen '
                    'JSON-Wert entsprechend dem folgenden Schema aus, ohne Markdown. '
                    'Vergleichsmaterial erweitert nicht den Antwortumfang. '
                    'Beachte insbesondere vorgegebene enum-Werte und den Wurzeltyp. JSON-Schema:\n'
                    + json.dumps(schema, ensure_ascii=False, separators=(',', ':')))
        instruction = {'role': 'system', 'content': guidance}
        if instruction not in request['messages']:
            request['messages'].insert(0, instruction)
    if schema and not cloud and settings.get('structured_outputs', True):
        request['format'] = schema
    num_ctx = int(settings.get('num_ctx', 32768))
    reserve = int(request['options']['num_predict'])
    from runtime_context import require_messages
    require_messages(request['messages'], settings, answer=reserve)
    if not cloud:
        request['options']['num_ctx'] = num_ctx
    else:
        request['options'].pop('num_ctx', None)
    headers = {}
    key = api_key or os.environ.get(selected['api_key_env'])
    if cloud and not key:
        raise LLMTransportError('Cloud-Schlüssel fehlt für den gewählten Anbieter.')
    if provider == 'ollama_cloud': headers['Authorization'] = 'Bearer ' + key
    if provider in ('ollama_local', 'ollama_cloud'):
        client = backend.Client(host=host, headers=headers, verify=ssl.create_default_context(),
                                timeout=timeout) if hasattr(backend, 'Client') else backend
    else:
        client = HTTPChatClient(provider, key, timeout)
    attempts = int(settings.get('max_attempts', 3))
    if not 1 <= attempts <= 5:
        raise ValueError('max_attempts muss zwischen 1 und 5 liegen.')
    started = time.monotonic()
    for attempt in range(attempts):
        from runtime_evidence import RequestReceipt
        receipt = RequestReceipt(provider, host, request)
        try:
            from progress_events import request_event
            request_event(start=True)
            response = client.chat(**request)
            request_event()
            logger.info('LLM request completed: model=%s attempt=%s elapsed=%.2fs',
                        request['model'], attempt + 1, time.monotonic() - started)
        except Exception as exc:
            request_event(success=False)
            status = getattr(exc, 'status_code', None)
            error = str(getattr(exc, 'error', exc)).lower()
            if 'think' in request and any(s in error for s in (
                    "unexpected keyword argument 'think'", 'does not support thinking', 'invalid think value')):
                receipt.fail('thinking_unsupported')
                if receipt.path:
                    raise LLMTransportError('Thinking wird nicht unterstützt. Kontrollierte Wiederholung stoppt ohne Wechsel zum Modellstandard; Einstellung prüfen und neue Serie planen.') from None
                logger.warning('Thinking-Einstellung wird vom Modell/Client nicht unterstützt; verwende Modellstandard.')
                request.pop('think')
                return request_chat(backend, request, {**settings, 'max_attempts': max(1, attempts - attempt)}, api_key=api_key)
            receipt.fail('transport_error')
            retryable = status in (408, 429, 500, 502, 503, 504) or (
                status is None and not isinstance(exc, (ValueError, TypeError)))
            if not retryable or attempt + 1 == attempts:
                # Do not include arbitrary server/transport strings (may contain secrets).
                raise LLMTransportError(f'KI-Anfrage fehlgeschlagen ({type(exc).__name__}, Status {status}).') from None
            time.sleep(min(float(settings.get('retry_delay_seconds', 1)) * 2 ** attempt, 8))
            continue
        # An invalid receipt is not a retryable model transport failure.
        receipt.accept(response)
        return response
