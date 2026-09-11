"""Read-only local capacity estimate. Never loads/unloads models or sends prompts."""
import ctypes
import json
import math
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from llm_providers import NoRedirect, selection

GIB = 1024 ** 3
MAX_PARALLEL = 8


def metadata(endpoint, body=None):
    if endpoint not in ('tags', 'ps', 'show'):
        raise ValueError('Nur Modellmetadaten dürfen abgefragt werden.')
    request = urllib.request.Request('http://127.0.0.1:11434/api/' + endpoint,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=6) as response:
        raw = response.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('Ollama-Metadaten sind zu groß.')
    return json.loads(raw)


def hardware():
    result = {'gpus': [], 'ram_available_bytes': None}
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        output = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.free',
            '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5,
            creationflags=flags, check=True).stdout
        for line in output.splitlines():
            name, total, free = line.rsplit(',', 2)
            total, free = float(total), float(free)
            if not (math.isfinite(total) and 0 <= free <= total):
                continue
            result['gpus'].append({'name': name.strip(), 'total_bytes': int(total * 1024**2),
                                   'free_bytes': int(free * 1024**2)})
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        if os.name == 'nt':
            class Memory(ctypes.Structure):
                _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
                    (name, ctypes.c_uint64) for name in ('total', 'available', 'page_total',
                        'page_available', 'virtual_total', 'virtual_available', 'extended')]
            value = Memory(); value.length = ctypes.sizeof(value)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
                result['ram_available_bytes'] = value.available
        else:
            entries = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
            result['ram_available_bytes'] = int(entries['MemAvailable'].split()[0]) * 1024
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    return result


def kv_bytes_per_token(info):
    """Only standard attention layouts; hybrid/MLA/recurrent caches need other formulas."""
    arch = info.get('general.architecture')
    if arch not in {'llama', 'qwen2', 'qwen3', 'qwen2moe', 'qwen3moe', 'gemma', 'gemma2', 'gemma3', 'granite'}:
        return None
    try:
        def number(key):
            value = info[arch + '.' + key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1000000:
                raise ValueError()
            return float(value)
        layers = number('block_count')
        heads = number('attention.head_count')
        kv_heads = number('attention.head_count_kv')
        dimension = number('embedding_length') / heads
        key = number('attention.key_length') if arch + '.attention.key_length' in info else dimension
        value = number('attention.value_length') if arch + '.attention.value_length' in info else dimension
        return math.ceil(layers * kv_heads * (key + value) * 2)  # conservative f16 cache
    except (ValueError, KeyError, TypeError):
        return None


def estimate(model, context, tag, show, running, machine):
    result = {'model': model, 'num_ctx': context, 'checked_at': time.time(), 'status': 'unknown',
              'estimated_parallel': None, 'checked_up_to': MAX_PARALLEL, 'hardware': machine,
              'model_calls': 0, 'notes': [
                  'Speicherschätzung, kein Belastungstest. Die tatsächliche Ollama-Parallelität ist nicht auslesbar.',
                  'Gilt für vollständig auf GPUs geladenes Modell und die angezeigte momentane Belegung.']}
    gpus = machine.get('gpus', [])
    if not gpus:
        result['reason'] = 'Keine auswertbaren NVIDIA-Speicherdaten. Für CPU, AMD und Apple wird keine Zahl geraten.'
        return result
    cache = kv_bytes_per_token(show.get('model_info', {}))
    if cache is None:
        result['reason'] = 'Für diese Modellarchitektur fehlen verlässliche Angaben zum Kontextspeicher.'
        return result
    weights = tag.get('size', 0)
    if not isinstance(weights, (int, float)) or not math.isfinite(weights) or weights <= 0:
        result['reason'] = 'Modellgröße nicht verfügbar.'
        return result
    matches = [m for m in running.get('models', []) if m.get('digest') and m.get('digest') == tag.get('digest')]
    # Do not treat occupied model memory as free: allocation across devices and
    # active sessions cannot be reconstructed reliably from /api/ps.
    if matches:
        result['reason'] = 'Das gewählte Modell ist bereits geladen. Seine belegten Slots und die Speicherverteilung sind nicht auslesbar. Nach regulärem Entladen erneut prüfen.'
        result['loaded'] = True
        return result
    maximum_context = show.get('model_info', {}).get(show.get('model_info', {}).get('general.architecture', '') + '.context_length')
    if isinstance(maximum_context, (int, float)) and context > maximum_context:
        result['reason'] = 'Das gewählte Kontextfenster überschreitet den vom Modell gemeldeten Kontext.'
        return result
    # File size upper approximation, 10% weight overhead, reserve per device and
    # 20% cache margin. Aggregation remains conditional on Ollama GPU placement.
    reserve = sum(max(GIB, gpu['total_bytes'] * .1) for gpu in gpus)
    free = sum(gpu['free_bytes'] for gpu in gpus)
    per_request = cache * context * 1.2
    base = weights * 1.1 + reserve
    count = max(0, min(MAX_PARALLEL, math.floor((free - base) / per_request)))
    result.update(status='estimate', estimated_parallel=count, weights_bytes=weights,
                  cache_per_request_bytes=math.ceil(per_request), reserve_bytes=math.ceil(reserve),
                  free_vram_bytes=free)
    result['notes'] += ['Berechnung mit f16-Kontextcache, 20 % Cache-Zuschlag, 10 % Modell-Zuschlag und GPU-Reserve.',
                        'Mehrere GPUs werden zusammengezählt. Ollamas GPU-Auswahl und Verteilung können die Zahl verringern.',
                        'Ab 2 gewählten Anfragen startet der Workflow eine eigene lokale Ollama-Instanz mit passenden Verarbeitungsplätzen.',
                        'Clustering und Codierprüfungen senden unabhängige Einheiten parallel; abhängige Stufen laufen nacheinander.']
    if count == 0:
        result['reason'] = 'Aktuell keine reine GPU-Anfrage mit diesen Reserven abschätzbar. Andere Belegung, kleineres Modell oder Kontext prüfen; CPU-Auslagerung ist hier nicht bewertet.'
    else:
        result['reason'] = f'Speicherschätzung: bis zu {count} gleichzeitige Anfragen (Prüfbereich 1–{MAX_PARALLEL}).'
    return result


def check(values):
    chosen = selection(values)
    if chosen['provider'] != 'ollama_local':
        raise ValueError('Die Speicherprüfung ist nur für lokales Ollama verfügbar.')
    context = values.get('num_ctx')
    if type(context) is not int or not 2048 <= context <= 1048576:
        raise ValueError('Ein gültiges Kontextfenster zwischen 2048 und 1048576 wählen.')
    try:
        tags = metadata('tags')['models']
        model = chosen['model']
        canonical = model if ':' in model.rsplit('/', 1)[-1] else model + ':latest'
        tag = next((m for m in tags if m.get('name') in (model, canonical)), None)
        if not tag:
            raise ValueError('Das gewählte Modell ist nicht lokal installiert.')
        if tag.get('remote_host') or 'cloud' in tag.get('name', '').lower():
            raise ValueError('Cloud-Modelle haben keine lokale Speicherschätzung.')
        show = metadata('show', {'model': tag['name']})
        if show.get('remote_host'):
            raise ValueError('Cloud-Modelle haben keine lokale Speicherschätzung.')
        return estimate(tag['name'], context, tag, show, metadata('ps'), hardware())
    except (OSError, KeyError, json.JSONDecodeError):
        raise ValueError('Lokale Ollama-Metadaten nicht verfügbar. Ollama starten und erneut prüfen.') from None
