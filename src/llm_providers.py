"""Fixed provider endpoints, explicit privacy boundary and normalized text responses."""
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse

PROVIDERS = {
    'ollama_local': {'name': 'Ollama · lokal', 'host': 'http://localhost:11434', 'env': None},
    'ollama_cloud': {'name': 'Ollama Cloud', 'host': 'https://ollama.com', 'env': 'OLLAMA_API_KEY'},
    'openai': {'name': 'OpenAI', 'host': 'https://api.openai.com/v1/responses', 'env': 'OPENAI_API_KEY'},
    'anthropic': {'name': 'Anthropic', 'host': 'https://api.anthropic.com/v1/messages', 'env': 'ANTHROPIC_API_KEY'},
    'huggingface': {'name': 'Hugging Face', 'host': 'https://router.huggingface.co/v1/chat/completions', 'env': 'HF_TOKEN'},
}
KEY_ENVS = {v['env'] for v in PROVIDERS.values() if v['env']}


def selection(settings, *, default_private=True):
    private = settings.get('gdpr_relevant', default_private)
    if type(private) is not bool:
        raise ValueError('DSGVO-Einstellung muss ein Wahrheitswert sein.')
    provider = settings.get('provider', 'ollama_local')
    if provider not in PROVIDERS:
        raise ValueError('Unbekannter KI-Anbieter.')
    if private and provider != 'ollama_local':
        raise ValueError('DSGVO-relevantes Material: Cloud gesperrt. Nur lokales Ollama ist freigegeben.')
    model = str(settings.get('model', '')).strip()
    if not re.fullmatch(r'[A-Za-z0-9_.:/@+-]{1,200}', model):
        raise ValueError('Einen gültigen Modellnamen des gewählten Anbieters eingeben.')
    if provider == 'ollama_local' and 'cloud' in model.lower():
        raise ValueError('Für lokale Verarbeitung ein lokales Modell ohne Cloud-Verweis wählen.')
    return {'provider': provider, 'gdpr_relevant': private, 'model': model,
            'host': PROVIDERS[provider]['host'], 'api_key_env': PROVIDERS[provider]['env'] or 'OLLAMA_API_KEY'}


def transport_selection(settings, model):
    # Legacy CLI configurations can explicitly use Ollama Cloud. New configs and
    # every dashboard project default to private; an explicit True always wins.
    legacy_host = settings.get('host') or os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    provider = settings.get('provider') or ('ollama_cloud' if urlparse(legacy_host).hostname == 'ollama.com' else 'ollama_local')
    result = selection({**settings, 'provider': provider, 'model': model}, default_private=provider == 'ollama_local')
    if settings.get('api_key_env'):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',settings['api_key_env']):
            raise ValueError('Ungültiger Name der Schlüssel-Umgebungsvariable.')
        result['api_key_env']=settings['api_key_env']
    if provider == 'ollama_local':
        parsed = urlparse(legacy_host)
        if parsed.hostname not in ('localhost', '127.0.0.1', '::1') or parsed.scheme != 'http' or parsed.username or parsed.password:
            raise ValueError('Lokales Ollama muss eine HTTP-Loopback-Adresse verwenden.')
        result['host'] = legacy_host
        if os.environ.get('QUALITATIVE_CLOUD_TEST_ONLY') == '1':
            raise ValueError('In dieser Cloud-Testoberfläche sind lokale Modellaufrufe deaktiviert.')
    return result


class ProviderHTTPError(Exception):
    def __init__(self, status):
        self.status_code = status
        super().__init__('KI-Anbieter hat die Anfrage abgelehnt.')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class HTTPChatClient:
    def __init__(self, provider, key, timeout):
        self.provider, self.key, self.timeout = provider, key, timeout

    def chat(self, **request):
        provider = self.provider
        messages = request['messages']
        limit = request['options']['num_predict']
        headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.key}
        if provider == 'openai':
            body = {'model': request['model'], 'input': messages, 'max_output_tokens': limit, 'store': False}
        elif provider == 'anthropic':
            headers = {'Content-Type': 'application/json', 'x-api-key': self.key, 'anthropic-version': '2023-06-01'}
            body = {'model': request['model'], 'max_tokens': limit,
                    'messages': [m for m in messages if m['role'] not in ('system', 'developer')]}
            system = '\n\n'.join(m['content'] for m in messages if m['role'] in ('system', 'developer'))
            if system: body['system'] = system
        else:
            body = {'model': request['model'], 'messages': messages, 'max_tokens': limit}
        req = urllib.request.Request(PROVIDERS[provider]['host'], data=json.dumps(body).encode(), headers=headers)
        opener = urllib.request.build_opener(NoRedirect())
        try:
            with opener.open(req, timeout=self.timeout) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024: raise ValueError('Modellantwort ist zu groß.')
            data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise ProviderHTTPError(status) from None
        try:
            if provider == 'openai':
                if data.get('status') != 'completed': raise ValueError('Antwort nicht abgeschlossen.')
                parts = [c for item in data['output'] if item.get('type') == 'message' for c in item.get('content', [])]
                if any(c.get('type') == 'refusal' for c in parts): raise ValueError('Antwort abgelehnt.')
                text = '\n'.join(c['text'] for c in parts if c.get('type') == 'output_text')
            elif provider == 'anthropic':
                if data.get('stop_reason') not in ('end_turn', 'stop_sequence'): raise ValueError('Antwort nicht abgeschlossen.')
                text = '\n'.join(c['text'] for c in data['content'] if c.get('type') == 'text')
            else:
                choice = data['choices'][0]
                if choice.get('finish_reason') != 'stop' or choice['message'].get('refusal'):
                    raise ValueError('Antwort nicht abgeschlossen.')
                text = choice['message']['content']
            if not isinstance(text, str) or not text.strip(): raise ValueError('Leere Textantwort.')
        except (KeyError, IndexError, TypeError, ValueError):
            raise ValueError('Keine vollständige Textantwort vom KI-Anbieter. Modell und Antwortlimit prüfen.') from None
        return {'message': {'content': text}}
