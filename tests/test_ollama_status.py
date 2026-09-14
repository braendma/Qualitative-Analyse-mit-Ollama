"""The status check lists local models without starting a server or inference."""
import json
import tempfile
import unittest
from unittest.mock import patch

from local_app import App


class OllamaStatusTests(unittest.TestCase):
    def test_app_startup_does_not_contact_or_launch_ollama(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('local_app.urllib.request.build_opener') as network, \
             patch('local_app.subprocess.Popen') as launch:
            app=App(tmp)
            app.create('Synthetic status example',True)
            network.assert_not_called()
            launch.assert_not_called()

    def test_status_is_bounded_read_only_and_excludes_remote_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp)
            with patch('local_app.urllib.request.build_opener') as build, \
                 patch('local_app.subprocess.Popen') as launch:
                response=build.return_value.open.return_value.__enter__.return_value
                response.read.return_value=json.dumps({'models':[
                    {'name':'synthetic-local:small'},
                    {'name':'synthetic-cloud'},
                    {'name':'synthetic-remote','remote_host':'https://example.invalid'}]}).encode()
                self.assertEqual(app.models(),{'models':['synthetic-local:small']})
                build.return_value.open.assert_called_once_with('http://127.0.0.1:11434/api/tags',timeout=5)
                response.read.assert_called_once_with(2*1024*1024)
                launch.assert_not_called()

    def test_unavailable_status_redacts_transport_details_and_allows_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp)
            with patch('local_app.urllib.request.build_opener') as build:
                build.return_value.open.side_effect=OSError('synthetic-private-transport-detail')
                with self.assertRaisesRegex(ValueError,'erneut prüfen') as error:app.models()
                self.assertNotIn('synthetic-private',str(error.exception))
                build.return_value.open.side_effect=None
                build.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"models":[]}'
                self.assertEqual(app.models(),{'models':[]})


if __name__=='__main__':unittest.main()
