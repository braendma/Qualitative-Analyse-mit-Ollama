"""Session credentials with optional Windows protection, outside project snapshots."""
import base64
import json
import os
from pathlib import Path
from llm_providers import PROVIDERS
from runtime_support import atomic_json
from telegram_notifications import protect


class ProviderKeys:
    def __init__(self, directory):
        self.path = Path(directory) / 'llm_keys.private.json'
        self.keys, self.encrypted = {}, {}
        self.warning = ''
        if self.path.is_file():
            try:
                saved = json.loads(self.path.read_text(encoding='utf-8'))
                for provider, value in saved.items():
                    if provider not in PROVIDERS or not PROVIDERS[provider]['env']: continue
                    self.encrypted[provider] = value
                    self.keys[provider] = protect(base64.b64decode(value, validate=True), decrypt=True).decode()
            except (ValueError, TypeError, UnicodeError, AttributeError, OSError):
                self.warning = 'Ein gespeicherter Schlüssel ist nicht lesbar. Beim betroffenen Anbieter neu eingeben.'

    def public(self):
        return {'providers': {p: {'has_key': bool(self.keys.get(p)), 'persist': p in self.encrypted}
                              for p in PROVIDERS if PROVIDERS[p]['env']},
                'can_persist': os.name == 'nt', 'warning': self.warning}

    def save(self, provider, key='', persist=False, remove=False):
        if provider not in PROVIDERS or not PROVIDERS[provider]['env']:
            raise ValueError('Einen Cloud-Anbieter auswählen.')
        if not isinstance(key, str): raise ValueError('Ungültiger API-Schlüssel.')
        key = key.strip() or self.keys.get(provider, '')
        if remove: key = ''
        if key and (len(key) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key)):
            raise ValueError('API-Schlüssel muss aus einer einzelnen Zeile ohne Leerzeichen bestehen.')
        encrypted = dict(self.encrypted)
        if persist and key:
            try: encrypted[provider] = base64.b64encode(protect(key.encode())).decode()
            except ValueError: raise ValueError('Windows konnte den API-Schlüssel nicht schützen. Sitzungsspeicherung verwenden.') from None
        else: encrypted.pop(provider, None)
        atomic_json(self.path, encrypted)
        self.encrypted = encrypted
        if key: self.keys[provider] = key
        else: self.keys.pop(provider, None)
        return self.public()
