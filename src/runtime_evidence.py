"""Local, content-free request receipts for controlled diagnostic child runs.

Acceptance proves transmission, not that every server setting was enforced.
Model metadata is a before/after observation, not per-token attestation.
"""
import json
import math
import os
from pathlib import Path
import re
import time
import uuid

from runtime_support import atomic_json, fingerprint

ENV = 'WORKFLOW_RUNTIME_EVIDENCE_DIR'


class RuntimeEvidenceError(ValueError):
    """Do not silently downgrade a diagnostic request with unverifiable conditions."""


def _name(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_./:@+-]{1,240}', value) else None


def _canonical(name):
    return name if ':' in name.rsplit('/', 1)[-1] else name + ':latest'


def transmitted_parameters(provider, request):
    """Only the fields forwarded by our transport adapters, never message content."""
    options = request.get('options', {})
    if provider in ('ollama_local', 'ollama_cloud'):
        numeric = {k: v for k, v in options.items() if k in
                   {'temperature', 'num_predict', 'num_ctx', 'seed', 'top_k', 'top_p', 'min_p', 'repeat_penalty'}}
        if provider == 'ollama_cloud':
            numeric.pop('num_ctx', None)
        result = {'options': numeric}
        if 'think' in request:
            value = request['think']
            if type(value) is not bool and value not in ('low', 'medium', 'high', 'max'):
                raise RuntimeEvidenceError('Thinking-Einstellung für den Laufzeitnachweis ungültig.')
            result['think'] = value
        if 'format' in request:
            result['format_sha256'] = fingerprint(request['format'])
    else:
        numeric = {('max_output_tokens' if provider == 'openai' else 'max_tokens'): options.get('num_predict')}
        result = dict(numeric)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in numeric.values()):
        raise RuntimeEvidenceError('Modellparameter für den Laufzeitnachweis müssen endliche Zahlen sein.')
    return result


def observe_model(host, model):
    from ollama_capacity import metadata
    try:
        data = metadata('tags', host=host)
        matches = [m for m in data['models'] if isinstance(m, dict)
                   and _name(m.get('name')) and _canonical(m['name']) == _canonical(model)]
        if len(matches) != 1:
            raise ValueError('model identity ambiguous')
        tag = matches[0]
        digest = tag.get('digest')
        if tag.get('remote_host') or tag.get('remote_model') or not isinstance(digest, str) or not re.fullmatch(r'(sha256:)?[a-fA-F0-9]{64}', digest):
            raise ValueError('no local digest')
        return {'name': tag['name'], 'digest': digest.removeprefix('sha256:').lower(),
                'status': 'local_metadata_observed'}
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeEvidenceError('Lokale Modellidentität nicht eindeutig prüfbar. Ollama und Modell prüfen; keine kontrollierte Anfrage gestartet bzw. übernommen.') from None


def observed_context(host, digest):
    from ollama_capacity import metadata
    try:
        data = metadata('ps', host=host)
        matches = [m for m in data['models'] if isinstance(m, dict)
                   and isinstance(m.get('digest'), str) and m['digest'].removeprefix('sha256:').lower() == digest]
        value = matches[0].get('context_length') if len(matches) == 1 else None
        return value if type(value) is int and value > 0 else None
    except (OSError, ValueError, KeyError, TypeError):
        return None  # Optional observation; never infer context from the configured number.


class RequestReceipt:
    def __init__(self, provider, host, request):
        self.path = None
        directory = os.environ.get(ENV)
        if not directory:
            return
        run_id = _name(os.environ.get('WORKFLOW_RUN_ID'))
        module = _name(os.environ.get('WORKFLOW_MODULE'))
        identity = os.environ.get('WORKFLOW_FINGERPRINT', '')
        model = _name(request.get('model'))
        if not run_id or not module or not model or not re.fullmatch('[a-f0-9]{64}', identity):
            raise RuntimeEvidenceError('Laufzeitnachweis benötigt gültige Lauf-, Modul- und Modellidentität.')
        self.host = host
        self.path = Path(directory) / (uuid.uuid4().hex + '.json')
        self.data = {'schema_version': 1, 'run_id': run_id, 'module': module,
                     'workflow_fingerprint': identity, 'provider': provider,
                     'model': model, 'parameters_sent': transmitted_parameters(provider, request),
                     'parameter_status': 'not_sent', 'status': 'preparing',
                     'created_at': time.time(), 'server_parameter_enforcement': 'not_verifiable',
                     'model_before': None, 'model_after': None}
        self.save()
        if provider == 'ollama_local':
            try:
                self.data['model_before'] = observe_model(host, model)
            except RuntimeEvidenceError:
                self.fail('identity_unavailable_before_request')
                raise
            expected = os.environ.get('WORKFLOW_EXPECTED_MODEL_DIGEST')
            if expected and expected != self.data['model_before']['digest']:
                self.fail('model_changed_between_samples')
                raise RuntimeEvidenceError('Modellidentität gegenüber der vorherigen Wiederholung verändert. Neue Serie mit festem Modell planen.')
        else:
            self.data['model_identity_status'] = 'cloud_weights_not_verifiable'
        self.data.update(status='pending', parameter_status='prepared_for_transmission')
        self.save()

    def save(self):
        if self.path:
            atomic_json(self.path, self.data)

    def fail(self, reason):
        if self.path:
            self.data.update(status='failed', failure_kind=reason, finished_at=time.time())
            self.save()

    def accept(self, response):
        if not self.path:
            return
        self.data.update(parameter_status='request_accepted', status='accepted', finished_at=time.time())
        reported = response.get('model') if hasattr(response, 'get') else getattr(response, 'model', None)
        self.data['response_model'] = _name(reported)
        if self.data['provider'] == 'ollama_local':
            try:
                after = observe_model(self.host, self.data['model'])
            except RuntimeEvidenceError:
                self.fail('identity_unavailable_after_request')
                raise
            self.data['model_after'] = after
            if after['digest'] != self.data['model_before']['digest']:
                self.fail('model_changed_during_request')
                raise RuntimeEvidenceError('Modellidentität hat sich während der Anfrage geändert. Neue kontrollierte Serie mit festem Modell starten.')
            if self.data['response_model'] and _canonical(self.data['response_model']) != _canonical(self.data['model']):
                self.fail('response_model_mismatch')
                raise RuntimeEvidenceError('Antwort nennt ein anderes Modell als angefordert; kontrollierte Anfrage nicht übernommen.')
            self.data['observed_context_length'] = observed_context(self.host, after['digest'])
            self.data['model_identity_status'] = 'same_local_digest_observed_before_after'
        self.save()


def summarize(directory, run_id, identity):
    """Verified receipt inventory; missing receipts never mean parameter verification."""
    from runtime_support import file_hash
    records = []
    files = {}
    for path in sorted(Path(directory).glob('*.json')):
        if path.is_symlink() or not path.resolve().is_relative_to(Path(directory).resolve()):
            raise RuntimeEvidenceError('Laufzeitnachweis verweist außerhalb des eigenen Ordners.')
        data = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or data.get('schema_version') != 1 or data.get('run_id') != run_id
                or data.get('workflow_fingerprint') != identity
                or data.get('status') not in ('accepted', 'failed', 'pending', 'preparing')):
            raise RuntimeEvidenceError('Laufzeitnachweis gehört nicht zu diesem Lauf.')
        records.append(data)
        files[path.name] = file_hash(path)
    accepted = [r for r in records if r.get('status') == 'accepted']
    digests = sorted({r['model_before']['digest'] for r in accepted if r.get('model_before')})
    return {'schema_version': 1, 'records': len(records), 'accepted': len(accepted),
            'failed': sum(r.get('status') == 'failed' for r in records),
            'pending': sum(r.get('status') in ('pending', 'preparing') for r in records),
            'local_digests': digests, 'files': files,
            'parameter_status': 'request_receipts_available' if accepted else 'not_observed',
            'server_parameter_enforcement': 'not_verifiable'}


def verify_inventory(run, manifest):
    """Bind persisted receipts to their manifest; interrupted modules may add receipts."""
    from runtime_support import file_hash
    root = Path(run) / '_runtime_evidence'
    if root.is_symlink() or not root.resolve().is_relative_to(Path(run).resolve()):
        raise RuntimeEvidenceError('Laufzeitnachweise verweisen außerhalb des Laufs.')
    recorded = manifest.get('runtime_evidence')
    if recorded is None:
        return None
    if not isinstance(recorded, dict) or not isinstance(recorded.get('files'), dict):
        raise RuntimeEvidenceError('Inventar der Laufzeitnachweise ist beschädigt.')
    for name, digest in recorded['files'].items():
        if not re.fullmatch(r'[a-f0-9]{32}\.json', name):
            raise RuntimeEvidenceError('Ungültiger Pfad im Laufzeitnachweis.')
        path = root / name
        if path.is_symlink() or not path.is_file() or file_hash(path) != digest:
            raise RuntimeEvidenceError('Gespeicherter Laufzeitnachweis verändert oder fehlt.')
    actual = summarize(root, manifest['run_id'], manifest['fingerprint'])
    if manifest.get('status') == 'success' and actual != recorded:
        raise RuntimeEvidenceError('Abgeschlossener Lauf enthält abweichende Laufzeitnachweise.')
    return actual
