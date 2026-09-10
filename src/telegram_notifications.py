"""Optional, content-free notifications; bot tokens never enter analysis configs."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import threading
import urllib.request
from runtime_support import atomic_json


def protect(value, decrypt=False):
    """Windows DPAPI, current user; no plaintext fallback on other platforms."""
    if os.name != 'nt':
        raise ValueError('Dauerhaftes Speichern ist hier nur unter Windows verfügbar. Sitzungsspeicherung verwenden.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError('Windows konnte den Bot-Token nicht schützen oder entschlüsseln.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Telegram:
    EVENTS = {'start', 'progress', 'success', 'failed', 'paused'}
    def __init__(self, directory):
        self.path = Path(directory) / 'telegram.private.json'
        self.lock = threading.RLock()
        self.token = ''
        self.settings = {'enabled': False, 'chat_id': '', 'events': ['success', 'failed'], 'persist': False}
        self.last_status = 'Noch keine Nachricht gesendet.'
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self.settings.update({k: data[k] for k in self.settings if k in data})
            if data.get('protected_token'):
                try:
                    self.token = protect(base64.b64decode(data['protected_token']), decrypt=True).decode()
                except ValueError:
                    self.settings['enabled'] = False
                    self.last_status = 'Gespeicherter Token nicht lesbar. Bitte neu eingeben.'
        if not self.token:
            self.settings['enabled'] = False

    def public(self):
        with self.lock:
            return {**self.settings, 'has_token': bool(self.token), 'last_status': self.last_status,
                    'can_persist': os.name == 'nt'}

    def save(self, values):
        with self.lock:
            token = str(values.get('token', '')).strip() or self.token
            if values.get('remove_token'):
                token = ''
            if token and not re.fullmatch(r'\d{5,}:[A-Za-z0-9_-]{20,}', token):
                raise ValueError('Bot-Token hat kein gültiges Format. Den vollständigen Token von BotFather verwenden.')
            chat = str(values.get('chat_id', '')).strip()
            if chat and not re.fullmatch(r'-?\d+|@[A-Za-z0-9_]{5,}', chat):
                raise ValueError('Chat-ID muss eine Zahl oder ein öffentlicher Kanalname mit @ sein.')
            events = values.get('events', [])
            if not isinstance(events, list) or not set(events) <= self.EVENTS:
                raise ValueError('Unbekannte Benachrichtigungsart.')
            enabled = bool(values.get('enabled', False)) and not values.get('remove_token', False)
            if enabled and (not token or not chat):
                raise ValueError('Zum Aktivieren werden Bot-Token und Chat-ID benötigt.')
            settings = {'enabled': enabled, 'chat_id': chat, 'events': events,
                        'persist': bool(values.get('persist', False)) and bool(token)}
            encrypted = base64.b64encode(protect(token.encode())).decode() if settings['persist'] else None
            # Only encrypted token bytes are persisted, separate from project files.
            atomic_json(self.path, {**settings, 'protected_token': encrypted})
            self.settings, self.token = settings, token
            return self.public()

    def send(self, event, completed=0, total=0, test=False, detail=None):
        with self.lock:
            token, settings = self.token, dict(self.settings)
        if not test and (not settings['enabled'] or event not in settings['events']):
            return False
        if not token or not settings['chat_id']:
            if test:
                raise ValueError('Bot-Token und Chat-ID zuerst speichern.')
            return False
        messages = {'start': 'Qualitative Analyse: Lauf gestartet.',
                    'progress': f'Qualitative Analyse: {int(completed)} von {int(total)} Modulen abgeschlossen.',
                    'success': 'Qualitative Analyse: Lauf abgeschlossen. Ergebnisse lokal öffnen.',
                    'failed': 'Qualitative Analyse: Lauf unterbrochen. Bitte die lokale Oberfläche prüfen.',
                    'paused': 'Qualitative Analyse: Lauf pausiert. Fortsetzen ist lokal möglich.'}
        message = 'Qualitative Analyse: Telegram-Test erfolgreich.' if test else messages[event]
        if event=='progress' and not test and isinstance(detail,dict):
            # Only bounded numeric counters and fixed labels can reach Telegram.
            unit={'passages':'Passagen','rows':'Codierzeilen','batches':'Prüfblöcken'}.get(detail.get('unit'))
            done,amount=detail.get('completed'),detail.get('total')
            if unit and type(done) is int and type(amount) is int and 0<=done<=amount<=10000000:
                message+=f' Im aktuellen Modul: {done} von {amount} {unit} bearbeitet.'
            elif type(detail.get('requests')) is int and 0<=detail['requests']<=10000000:
                message+=f" Im aktuellen Modul: {detail['requests']} Modellantworten empfangen."
        body = json.dumps({'chat_id': settings['chat_id'], 'text': message}).encode()
        request = urllib.request.Request('https://api.telegram.org/bot' + token + '/sendMessage',
                                         data=body, headers={'Content-Type': 'application/json'})
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=10) as response:
                if not json.loads(response.read(65536)).get('ok'):
                    raise ValueError('Telegram hat die Nachricht abgelehnt.')
        except Exception:
            # HTTP exceptions include the secret-bearing URL. Never expose their text.
            self.last_status = 'Versand fehlgeschlagen. Token, Chat-ID, Bot-Freigabe und Internetverbindung prüfen.'
            if test:
                raise ValueError(self.last_status) from None
            return False
        self.last_status = 'Letzte Statusmeldung erfolgreich gesendet.'
        return True
