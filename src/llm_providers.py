"""Provider endpoints, explicit project consent and normalized text responses."""
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse

UP_PROXY = 'https://llm.ki.k8s.rz.uni-potsdam.de'
MODEL_ID = re.compile(r'[A-Za-z0-9_.:/@+-]{1,200}')


def proxy_base_url(value):
    """Return the canonical HTTPS API prefix shared by discovery and inference."""
    if not isinstance(value, str) or not re.fullmatch(r'https://[A-Za-z0-9.\[\]:/_~-]+', value.strip()):
        raise ValueError('LiteLLM benötigt eine HTTPS-Basisadresse ohne Zugangsdaten, Parameter oder Fragment.')
    parsed = urlparse(value.strip())
    if not parsed.hostname or parsed.netloc.endswith(':') or parsed.port == 0:
        raise ValueError('Ungültige LiteLLM-Basisadresse.')
    path = parsed.path.rstrip('/')
    if any(part in ('.', '..') for part in path.split('/')) or path.endswith(('/models', '/chat/completions')):
        raise ValueError('LiteLLM-Basisadresse eingeben, gegebenenfalls einschließlich /v1.')
    host = parsed.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    if parsed.port and parsed.port != 443:
        host += ':' + str(parsed.port)
    return 'https://' + host + path


def credential_slot(provider, base=None):
    if provider == 'litellm':
        return 'litellm@' + proxy_base_url(UP_PROXY if base is None else base)
    return provider


PROVIDERS = {
    'ollama_local': {'name': 'Ollama · lokal', 'host': 'http://localhost:11434', 'env': None},
    'ollama_cloud': {'name': 'Ollama Cloud', 'host': 'https://ollama.com', 'env': 'OLLAMA_API_KEY'},
    'openai': {'name': 'OpenAI', 'host': 'https://api.openai.com/v1/responses', 'env': 'OPENAI_API_KEY'},
    'anthropic': {'name': 'Anthropic', 'host': 'https://api.anthropic.com/v1/messages', 'env': 'ANTHROPIC_API_KEY'},
    'litellm': {'name': 'LiteLLM / OpenAI-kompatibler Proxy', 'host': UP_PROXY, 'env': 'LITELLM_API_KEY'},
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
    if not MODEL_ID.fullmatch(model):
        raise ValueError('Einen gültigen Modellnamen des gewählten Anbieters eingeben.')
    if provider == 'ollama_local' and 'cloud' in model.lower():
        raise ValueError('Für lokale Verarbeitung ein lokales Modell ohne Cloud-Verweis wählen.')
    result = {'provider': provider, 'gdpr_relevant': private, 'model': model,
              'host': PROVIDERS[provider]['host'], 'api_key_env': PROVIDERS[provider]['env'] or 'OLLAMA_API_KEY'}
    if provider == 'litellm':
        base = proxy_base_url(settings.get('proxy_base_url', UP_PROXY))
        result.update(proxy_base_url=base, host=base + '/chat/completions')
    return result


def _explicit_legacy_cloud_host(settings):
    """Compatibility consent applies only to the host written in an old YAML.

    An inherited OLLAMA_HOST is a transport preference, never data-release consent.
    Credentials, redirects and alternate endpoint paths are not legacy host syntax.
    """
    host = settings.get('host')
    if not isinstance(host, str):
        return False
    try:
        parsed = urlparse(host)
        return (parsed.scheme == 'https' and parsed.hostname == 'ollama.com' and
                parsed.port in (None, 443) and not parsed.username and not parsed.password and
                parsed.path in ('', '/') and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def transport_selection(settings, model):
    # Legacy CLI configurations can explicitly use Ollama Cloud. New configs and
    # every dashboard project default to private; an explicit True always wins.
    legacy_host = settings.get('host') or os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    provider = settings.get('provider') or ('ollama_cloud' if urlparse(legacy_host).hostname == 'ollama.com' else 'ollama_local')
    legacy_consent = provider == 'ollama_cloud' and _explicit_legacy_cloud_host(settings)
    result = selection({**settings, 'provider': provider, 'model': model}, default_private=not legacy_consent)
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


def provider_environment(selected, environment):
    """Pass only the chosen provider credential while keeping runtime context.

    The caller supplies a validated transport selection. Unknown environment
    variables remain functional context; this is not a general secret scanner.
    """
    provider = selected.get('provider')
    if provider not in PROVIDERS:
        raise ValueError('Unbekannter KI-Anbieter für den Kindprozess.')
    variable = selected.get('api_key_env')
    if not isinstance(variable, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', variable):
        raise ValueError('Ungültiger Name der Schlüssel-Umgebungsvariable.')
    canonical = str.upper if os.name == 'nt' else str
    names = {canonical(key) for key in KEY_ENVS | {variable}}
    result = {key: value for key, value in environment.items() if canonical(key) not in names}
    if provider != 'ollama_local':
        matches = [value for key, value in environment.items() if canonical(key) == canonical(variable)]
        if len(set(matches)) > 1:
            raise ValueError('Mehrdeutige Schlüssel-Umgebungsvariable; Schreibweise vereinheitlichen.')
        if matches:
            result[variable] = matches[0]
    return result


class ProviderHTTPError(Exception):
    def __init__(self, status):
        self.status_code = status
        super().__init__('KI-Anbieter hat die Anfrage abgelehnt.')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class ProviderOutputLimit(ValueError):
    """The provider explicitly reported exhaustion of the completion budget."""


def proxy_models(base, key):
    url = proxy_base_url(base) + '/models'
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('Modellliste ist zu groß.')
        rows = json.loads(raw)['data']
        if not isinstance(rows, list):
            raise TypeError
        return sorted({row['id'] for row in rows if isinstance(row, dict)
                       and isinstance(row.get('id'), str) and MODEL_ID.fullmatch(row['id'])})
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        raise ValueError(f'LiteLLM-Modellliste abgelehnt (HTTP {status}).') from None
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('LiteLLM-Modellliste nicht lesbar. Adresse und Schlüssel prüfen oder Modell-ID eingeben.') from None


class HTTPChatClient:
    def __init__(self, provider, key, timeout, *, base=None):
        self.provider, self.key, self.timeout = provider, key, timeout
        self.endpoint = (proxy_base_url(UP_PROXY if base is None else base) + '/chat/completions'
                         if provider == 'litellm' else PROVIDERS[provider]['host'])

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
        req = urllib.request.Request(self.endpoint, data=json.dumps(body).encode(), headers=headers)
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
                if data.get('status') == 'incomplete' and (data.get('incomplete_details') or {}).get('reason') == 'max_output_tokens':
                    raise ProviderOutputLimit('Antwortlimit erreicht.')
                if data.get('status') != 'completed': raise ValueError('Antwort nicht abgeschlossen.')
                parts = [c for item in data['output'] if item.get('type') == 'message' for c in item.get('content', [])]
                if any(c.get('type') == 'refusal' for c in parts): raise ValueError('Antwort abgelehnt.')
                text = '\n'.join(c['text'] for c in parts if c.get('type') == 'output_text')
            elif provider == 'anthropic':
                if data.get('stop_reason') == 'max_tokens':
                    raise ProviderOutputLimit('Antwortlimit erreicht.')
                if data.get('stop_reason') not in ('end_turn', 'stop_sequence'): raise ValueError('Antwort nicht abgeschlossen.')
                text = '\n'.join(c['text'] for c in data['content'] if c.get('type') == 'text')
            else:
                choice = data['choices'][0]
                if choice.get('finish_reason') == 'length':
                    raise ProviderOutputLimit('Antwortlimit erreicht.')
                if choice.get('finish_reason') != 'stop' or choice['message'].get('refusal'):
                    raise ValueError('Antwort nicht abgeschlossen.')
                text = choice['message']['content']
            if not isinstance(text, str) or not text.strip(): raise ValueError('Leere Textantwort.')
        except ProviderOutputLimit:
            raise
        except (KeyError, IndexError, TypeError, ValueError):
            raise ValueError('Keine vollständige Textantwort vom KI-Anbieter. Modell und Antwortlimit prüfen.') from None
        return {'message': {'content': text}}
