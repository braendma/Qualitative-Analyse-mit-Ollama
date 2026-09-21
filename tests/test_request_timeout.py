"""Finite configured transport waits, with no real model or network calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from llm_client import request_chat, request_timeout_seconds
from local_app import App
from test_local_app import settings

REQUEST = {'model': 'synthetic', 'messages': [{'role': 'user', 'content': 'Synthetic input'}],
           'options': {'num_predict': 128, 'temperature': 0}}


class RequestTimeoutTests(unittest.TestCase):
    def test_finite_range_rejects_unlimited_or_malformed_values_before_client_creation(self):
        self.assertEqual(request_timeout_seconds({}), 180)
        for value in (None, True, False, '', '1200', float('nan'), float('inf'), -1, 0, 3601, 10**400):
            with self.subTest(value=repr(value)), patch('llm_providers.HTTPChatClient') as client:
                with self.assertRaisesRegex(ValueError, 'Antwortwartezeit'):
                    request_chat(None, copy.deepcopy(REQUEST), {'timeout_seconds': value})
                client.assert_not_called()
        for value in (1, 45, 90, 1200, 3600, 1.5):
            self.assertEqual(request_timeout_seconds({'timeout_seconds': value}), float(value))

    def test_all_provider_clients_receive_the_selected_wait(self):
        for provider in ('ollama_local', 'ollama_cloud', 'openai', 'anthropic', 'huggingface'):
            with self.subTest(provider=provider), patch('llm_providers.HTTPChatClient') as http:
                backend = MagicMock()
                result = {'message': {'content': 'Synthetic response'}}
                backend.Client.return_value.chat.return_value = result
                http.return_value.chat.return_value = result
                opts = {'provider': provider, 'gdpr_relevant': provider == 'ollama_local',
                        'timeout_seconds': 1200, 'max_attempts': 1, 'num_ctx': 4096}
                self.assertEqual(request_chat(backend, copy.deepcopy(REQUEST), opts, api_key='synthetic-key'), result)
                if provider.startswith('ollama_'):
                    self.assertEqual(backend.Client.call_args.kwargs['timeout'], 1200)
                    http.assert_not_called()
                else:
                    self.assertEqual(http.call_args.args, (provider, 'synthetic-key', 1200))
                    backend.Client.assert_not_called()

    def test_project_setting_persists_to_revision_yaml_and_preserves_template_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(tmp)
            pid = app.create('Synthetic timeout', True)['id']
            opts = settings(app)
            self.assertEqual(app.config(pid, opts)[0]['llm']['timeout_seconds'], app.template['llm']['timeout_seconds'])
            opts['timeout_seconds'] = 1200
            app.save(pid, opts)
            project = app.project(pid)
            self.assertEqual(project['settings']['timeout_seconds'], 1200)
            cfg = app.project_dir(pid) / 'revisions' / project['revision'] / 'config.yaml'
            self.assertEqual(yaml.safe_load(cfg.read_text(encoding='utf-8'))['llm']['timeout_seconds'], 1200)
            for value in (None, True, float('nan'), float('inf'), -1, 3601):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Antwortwartezeit'):
                    app.config(pid, {**opts, 'timeout_seconds': value})
