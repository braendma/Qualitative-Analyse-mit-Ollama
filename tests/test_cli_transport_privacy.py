"""CLI privacy boundaries and minimal child key inheritance, without model I/O."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from llm_providers import KEY_ENVS, provider_environment, transport_selection
from llm_client import LLMTransportError, request_chat
from diagnostic_series import _child_environment
from diagnostic_repetitions import prepare_repetitions
from test_diagnostic_repetitions import Workspace


class CLITransportPrivacyTests(unittest.TestCase):
    def test_environment_cloud_host_does_not_authorize_unmarked_yaml_or_transport(self):
        settings = {'model': 'synthetic-model', 'num_ctx': 4096}
        before = copy.deepcopy(settings)
        backend = MagicMock()
        with patch.dict(os.environ, {'OLLAMA_HOST': 'https://ollama.com', 'OLLAMA_API_KEY': 'synthetic-key'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Cloud gesperrt'):
                transport_selection(settings, settings['model'])
            with self.assertRaisesRegex(LLMTransportError, 'Cloud gesperrt'):
                request_chat(backend, {'model': settings['model'], 'messages': [], 'options': {'num_predict': 128}}, settings)
            backend.Client.assert_not_called()
            backend.chat.assert_not_called()
        self.assertEqual(settings, before)

    def test_each_explicit_cloud_provider_needs_privacy_choice_without_legacy_host(self):
        with patch.dict(os.environ, {}, clear=True):
            for provider in ('openai', 'anthropic', 'huggingface', 'ollama_cloud'):
                with self.subTest(provider=provider):
                    with self.assertRaisesRegex(ValueError, 'Cloud gesperrt'):
                        transport_selection({'provider': provider}, 'synthetic')
                    selected = transport_selection({'provider': provider, 'gdpr_relevant': False}, 'synthetic')
                    self.assertEqual(selected['provider'], provider)
                    self.assertFalse(selected['gdpr_relevant'])

    def test_explicit_historical_cloud_host_remains_compatible_and_unmodified(self):
        with patch.dict(os.environ, {'OLLAMA_HOST': 'http://127.0.0.1:11500'}, clear=True):
            for host in ('https://ollama.com', 'https://ollama.com/', 'https://ollama.com:443'):
                for provider in (None, 'ollama_cloud'):
                    settings = {'host': host}
                    if provider:
                        settings['provider'] = provider
                    before = dict(settings)
                    selected = transport_selection(settings, 'synthetic')
                    self.assertEqual(selected['provider'], 'ollama_cloud')
                    self.assertFalse(selected['gdpr_relevant'])
                    self.assertEqual(settings, before)
                    with self.assertRaisesRegex(ValueError, 'Cloud gesperrt'):
                        transport_selection({**settings, 'gdpr_relevant': True}, 'synthetic')

    def test_legacy_host_cannot_consent_for_other_providers_or_noncanonical_addresses(self):
        with patch.dict(os.environ, {}, clear=True):
            for provider in ('openai', 'anthropic', 'huggingface'):
                with self.subTest(provider=provider), self.assertRaisesRegex(ValueError, 'Cloud gesperrt'):
                    transport_selection({'provider': provider, 'host': 'https://ollama.com'}, 'synthetic')
            for host in ('http://ollama.com', 'https://name:synthetic@ollama.com',
                         'https://ollama.com/private', 'https://ollama.com?key=synthetic',
                         'https://ollama.com/#private', 'https://ollama.com:444'):
                with self.subTest(host=host), self.assertRaisesRegex(ValueError, 'Cloud gesperrt'):
                    transport_selection({'host': host}, 'synthetic')

    def test_private_true_always_blocks_cloud_including_environment_selection(self):
        with patch.dict(os.environ, {'OLLAMA_HOST': 'https://ollama.com'}, clear=True):
            for settings in ({'gdpr_relevant': True}, {'host': 'https://ollama.com', 'gdpr_relevant': True},
                             {'provider': 'openai', 'gdpr_relevant': True}):
                with self.subTest(settings=settings), self.assertRaisesRegex(ValueError, 'Cloud gesperrt'):
                    transport_selection(settings, 'synthetic')

    def test_local_environment_port_survives_and_explicit_yaml_host_wins(self):
        with patch.dict(os.environ, {'OLLAMA_HOST': 'http://127.0.0.1:11500'}, clear=True):
            selected = transport_selection({}, 'synthetic')
            self.assertTrue(selected['gdpr_relevant'])
            self.assertEqual(selected['host'], 'http://127.0.0.1:11500')
            explicit = transport_selection({'host': 'http://localhost:11499'}, 'synthetic')
            self.assertEqual(explicit['host'], 'http://localhost:11499')

    def test_unmarked_legacy_repetition_plan_is_blocked_before_any_new_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(Path(tmp))
            for key in ('host', 'provider', 'gdpr_relevant'):
                workspace.config['llm'].pop(key, None)
            workspace.save()
            before = {p.name: p.read_bytes() for p in workspace.root.iterdir()}
            with patch.dict(os.environ, {'OLLAMA_HOST': 'https://ollama.com', 'OLLAMA_API_KEY': 'synthetic'}, clear=True):
                with self.assertRaisesRegex(ValueError, 'Cloud gesperrt'):
                    prepare_repetitions(workspace.path, ['blind_coding'], repetitions=2)
            self.assertEqual({p.name: p.read_bytes() for p in workspace.root.iterdir()}, before)

    def test_environment_projection_preserves_runtime_and_only_selected_standard_key(self):
        environment = {key: 'synthetic-' + key for key in KEY_ENVS}
        environment.update(PATH='synthetic-path', SYSTEMROOT='synthetic-system', TEMP='synthetic-temp',
                           CUDA_VISIBLE_DEVICES='0,1', OLLAMA_HOST='http://127.0.0.1:11500')
        before = dict(environment)
        selected = transport_selection({'provider': 'openai', 'gdpr_relevant': False}, 'synthetic')
        result = provider_environment(selected, environment)
        self.assertEqual(result['OPENAI_API_KEY'], environment['OPENAI_API_KEY'])
        self.assertEqual(set(result) & KEY_ENVS, {'OPENAI_API_KEY'})
        for key in ('PATH', 'SYSTEMROOT', 'TEMP', 'CUDA_VISIBLE_DEVICES', 'OLLAMA_HOST'):
            self.assertEqual(result[key], environment[key])
        self.assertEqual(environment, before)

    def test_custom_selected_key_replaces_default_and_local_receives_no_known_keys(self):
        environment = {key: 'synthetic-' + key for key in KEY_ENVS}
        environment.update(SYNTHETIC_CUSTOM_KEY='synthetic-custom', PATH='runtime')
        selected = transport_selection({'provider': 'anthropic', 'gdpr_relevant': False,
                                        'api_key_env': 'SYNTHETIC_CUSTOM_KEY'}, 'synthetic')
        result = provider_environment(selected, environment)
        self.assertEqual(result, {'SYNTHETIC_CUSTOM_KEY': 'synthetic-custom', 'PATH': 'runtime'})
        local = transport_selection({'provider': 'ollama_local', 'host': 'http://localhost:11434',
                                     'api_key_env': 'SYNTHETIC_CUSTOM_KEY'}, 'synthetic')
        self.assertEqual(provider_environment(local, environment), {'PATH': 'runtime'})

    def test_absent_selected_key_is_not_replaced_with_another_provider_key(self):
        selected = transport_selection({'provider': 'openai', 'gdpr_relevant': False}, 'synthetic')
        self.assertEqual(provider_environment(selected, {'ANTHROPIC_API_KEY': 'synthetic', 'PATH': 'runtime'}),
                         {'PATH': 'runtime'})

    def test_series_environment_uses_filter_and_keeps_existing_workflow_isolation(self):
        environment = {key: 'synthetic-' + key for key in KEY_ENVS}
        environment.update(SYNTHETIC_CUSTOM_KEY='synthetic-custom', PATH='runtime', SYSTEMROOT='system',
                           WORKFLOW_RUN_ID='old', WORKFLOW_EXPECTED_MODEL_DIGEST='old-digest',
                           PYTHONUTF8='0', CUDA_VISIBLE_DEVICES='0,1')
        config = {'llm': {'provider': 'anthropic', 'gdpr_relevant': False, 'model': 'synthetic',
                          'api_key_env': 'SYNTHETIC_CUSTOM_KEY'}}
        with patch.dict(os.environ, environment, clear=True):
            result = _child_environment(config)
        self.assertEqual(result['SYNTHETIC_CUSTOM_KEY'], 'synthetic-custom')
        self.assertFalse(set(result) & KEY_ENVS)
        self.assertFalse(any(key.startswith('WORKFLOW_') for key in result))
        self.assertEqual(result['PYTHONUTF8'], '1')
        self.assertEqual(result['CUDA_VISIBLE_DEVICES'], '0,1')
        self.assertEqual(result['PATH'], 'runtime')

    def test_windows_key_names_are_case_insensitive_without_duplicate_credentials(self):
        environment = {'openai_api_key': 'synthetic-openai', 'Custom_Key': 'synthetic-custom', 'PATH': 'runtime'}
        cloud = {'provider': 'openai', 'api_key_env': 'custom_key'}
        local = {'provider': 'ollama_local', 'api_key_env': 'CUSTOM_KEY'}
        with patch('llm_providers.os.name', 'nt'):
            self.assertEqual(provider_environment(cloud, environment), {'custom_key': 'synthetic-custom', 'PATH': 'runtime'})
            self.assertEqual(provider_environment(local, environment), {'PATH': 'runtime'})
            with self.assertRaisesRegex(ValueError, 'Mehrdeutige'):
                provider_environment(cloud, {'CUSTOM_KEY': 'one', 'custom_key': 'another'})

    def test_invalid_selection_cannot_broaden_environment_projection(self):
        for selected in ({'provider': 'unknown', 'api_key_env': 'OPENAI_API_KEY'},
                         {'provider': 'openai', 'api_key_env': '../secret'},
                         {'provider': 'openai', 'api_key_env': None}):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                provider_environment(selected, {'OPENAI_API_KEY': 'synthetic'})


if __name__ == '__main__':
    unittest.main()
