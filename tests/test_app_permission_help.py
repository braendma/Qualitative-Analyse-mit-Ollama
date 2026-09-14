import io
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from local_app import Handler


class PermissionHelpTests(unittest.TestCase):
    def test_file_denial_has_actionable_guidance_without_private_exception_text(self):
        for route, body, method in (
                ('/api/save', {'project': 'synthetic', 'settings': {}}, 'save'),
                ('/api/provider-key', {'project': 'synthetic'}, 'save_provider_key')):
            with self.subTest(route=route):
                app = SimpleNamespace(lock=threading.RLock())
                setattr(app, method, Mock(side_effect=PermissionError('synthetic-private-key-and-interview-text')))
                handler = object.__new__(Handler)
                raw = json.dumps(body).encode('utf-8')
                handler.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(raw))}
                handler.rfile = io.BytesIO(raw)
                handler.path = route
                handler.server = SimpleNamespace(app=app)
                handler.allowed = lambda: True
                handler.json = Mock()
                handler.do_POST()
                payload, status = handler.json.call_args.args
                self.assertEqual(status, 400)
                self.assertIn('Schreibrechte', payload['error'])
                self.assertIn('Virenschutz', payload['error'])
                self.assertNotIn('synthetic-private', payload['error'])


if __name__ == '__main__':
    unittest.main()
