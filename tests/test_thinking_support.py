import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Die Wrapper-Tests benötigen keinen laufenden Ollama-Server. Falls das
# Python-Paket in der Testumgebung fehlt, wird nur dessen chat-Schnittstelle
# simuliert, bevor clusterer_core importiert wird.
if "ollama" not in sys.modules:
    sys.modules["ollama"] = types.SimpleNamespace(chat=None)

import clusterer_core


class FakeOllama:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ThinkingSupportTests(unittest.TestCase):
    def setUp(self):
        self.original_ollama = clusterer_core.ollama

    def tearDown(self):
        clusterer_core.ollama = self.original_ollama

    def call_wrapper(self, fake, think="high"):
        clusterer_core.ollama = fake
        return clusterer_core.ollama_chat(
            [{"role": "user", "content": "Antworte als JSON."}],
            model="granite4.2:8b",
            temperature=0.05,
            max_tokens=16000,
            think=think,
        )

    def test_separate_thinking_is_not_part_of_content(self):
        fake = FakeOllama([{
            "message": {
                "thinking": "Interne Überlegung",
                "content": '{"status": "ok"}',
            }
        }])

        result = self.call_wrapper(fake)

        self.assertEqual(result, '{"status": "ok"}')
        self.assertEqual(fake.calls[0]["think"], "high")
        self.assertNotIn("think", fake.calls[0]["options"])
        self.assertFalse(fake.calls[0]["stream"])

    def test_complete_embedded_think_block_is_removed(self):
        fake = FakeOllama([{
            "message": {
                "content": '<think>Interne Überlegung</think>\n{"status": "ok"}'
            }
        }])

        self.assertEqual(self.call_wrapper(fake), '{"status": "ok"}')

    def test_closing_only_think_block_is_removed(self):
        fake = FakeOllama([{
            "message": {
                "content": 'Interne Überlegung</think>\n{"status": "ok"}'
            }
        }])

        self.assertEqual(self.call_wrapper(fake), '{"status": "ok"}')

    def test_incomplete_think_block_returns_no_parser_input(self):
        fake = FakeOllama([{
            "message": {"content": "<think>Noch nicht fertig"}
        }])

        self.assertEqual(self.call_wrapper(fake), "")

    def test_old_python_client_is_retried_without_think_argument(self):
        fake = FakeOllama([
            TypeError("chat() got an unexpected keyword argument 'think'"),
            {"message": {"content": '{"status": "ok"}'}},
        ])

        result = self.call_wrapper(fake)

        self.assertEqual(result, '{"status": "ok"}')
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("think", fake.calls[0])
        self.assertNotIn("think", fake.calls[1])

    def test_non_thinking_model_is_retried_without_think_argument(self):
        fake = FakeOllama([
            RuntimeError('"classic-model" does not support thinking'),
            {"message": {"content": '{"status": "ok"}'}},
        ])

        result = self.call_wrapper(fake, think=False)

        self.assertEqual(result, '{"status": "ok"}')
        self.assertEqual(len(fake.calls), 2)
        self.assertIs(fake.calls[0]["think"], False)
        self.assertNotIn("think", fake.calls[1])

    def test_boolean_strings_are_normalized(self):
        fake = FakeOllama([{"message": {"content": "ok"}}])

        result = self.call_wrapper(fake, think="false")

        self.assertEqual(result, "ok")
        self.assertIs(fake.calls[0]["think"], False)


if __name__ == "__main__":
    unittest.main()
