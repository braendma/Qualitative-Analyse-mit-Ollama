"""Synthetic release checks for the desktop proxy and MAXQDA import."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from coding_validation_common import load_codebook, load_segments
from llm_client import LLMOutputLimitError, LLMTransportError, request_chat
from llm_providers import UP_PROXY, proxy_base_url, selection
from local_app import App, RUNNER
from test_local_app import settings
from test_providers import REQUEST


class ProxyTests(unittest.TestCase):
    def test_base_and_cloud_consent(self):
        self.assertEqual(proxy_base_url("https://EXAMPLE.org:443/team/v1/"), "https://example.org/team/v1")
        for base in ("http://example.org", "https://user:password@example.org", "https://example.org?k=val",
                     "https://example.org/#token", "https://example.org/../v1", "https://example.org/chat/completions"):
            with self.subTest(base=base), self.assertRaises(ValueError):
                proxy_base_url(base)
        with self.assertRaisesRegex(ValueError, "Cloud gesperrt"):
            selection({"provider": "litellm", "model": "abc"})
        self.assertEqual(selection({"provider":"litellm","model":"abc","gdpr_relevant":False})["host"],
                         UP_PROXY + "/chat/completions")

    def test_project_saves_address_fetches_models_and_binds_credentials(self):
        base = "https://example.org/team/v1"
        opts = {"provider":"litellm", "proxy_base_url":base, "model":"via/proxy", "gdpr_relevant":False}
        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.build_opener") as opener:
            app=App(tmp)
            pid=app.create("synthetisch", True)["id"]
            with self.assertRaises(ValueError):
                app.list_proxy_models(pid,opts)
            opener.assert_not_called()
            app.privacy(pid,False)
            app.save_provider_key(pid, {**opts, "key":"synthetic-credential"})
            response=opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value=json.dumps({"data":[{"id":"via/proxy"},{"id":"via/proxy"}]}).encode()
            self.assertEqual(app.list_proxy_models(pid,opts),{"models":["via/proxy"]})
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,base+"/models")
            self.assertEqual(request.get_header("Authorization"),"Bearer synthetic-credential")
            self.assertTrue(app.save(pid,{**settings(app),**opts})["valid"])
            revision=app.project_dir(pid)/"revisions"/app.project(pid)["revision"]
            config=(revision/"config.yaml").read_text(encoding="utf-8")
            self.assertIn(base,config)
            self.assertNotIn("synthetic-credential",config)
            response.read.return_value=b'{"choices":[{"finish_reason":"stop","message":{"content":"OK"}}]}'
            self.assertTrue(app.model_test(pid,opts)["ok"])
            self.assertEqual(opener.return_value.open.call_args.args[0].full_url,base+"/chat/completions")
            with self.assertRaisesRegex(ValueError,"Schlüssel"):
                app.list_proxy_models(pid,{**opts,"proxy_base_url":"https://other.example"})
            app.privacy(pid,True)
            with self.assertRaisesRegex(ValueError,"gesperrt"):
                app.model_test(pid,opts)

    def test_provider_limit_is_typed_and_no_retry_for_refusal(self):
        opts={"provider":"litellm", "gdpr_relevant":False, "num_ctx":8192, "max_attempts":3,
              "response_schema":{"type":"object"}}
        for reason,error in (("length",LLMOutputLimitError),("content_filter",LLMTransportError)):
            with self.subTest(reason=reason), patch("urllib.request.build_opener") as opener:
                reply=opener.return_value.open.return_value.__enter__.return_value
                reply.read.return_value=json.dumps({"choices":[{"finish_reason":reason,"message":{"content":"partial"}}]}).encode()
                with self.assertRaises(error):
                    request_chat(None,copy.deepcopy(REQUEST),opts,api_key="synthetic")
                self.assertEqual(opener.return_value.open.call_count,1)
                payload=json.loads(opener.return_value.open.call_args.args[0].data)
                self.assertTrue(any("JSON-Schema" in m["content"] for m in payload["messages"]))

    def test_report_export_error_preserves_successful_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(tmp)
            pid = app.create("Exporttest", True)["id"]
            opts = {**settings(app), "modules":["clusterer"]}
            app.save(pid, opts)
            config = app.project_dir(pid)/"revisions"/app.project(pid)["revision"]/"config.yaml"
            with patch.dict(os.environ), patch("logging.basicConfig"), patch("logging.FileHandler"), \
                    patch.object(RUNNER, "run_step"), patch("managed_ollama.ManagedOllama.start", return_value={}), \
                    patch.object(RUNNER, "build_full_report", side_effect=ValueError("HTML-Grenze")), \
                    self.assertRaisesRegex(ValueError, "HTML-Grenze"):
                RUNNER.main(["--config", str(config), "--output-dir", opts["output_dir"]])
            manifest_path, = Path(opts["output_dir"]).rglob("workflow_manifest.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["module_status"]["clusterer"],"success")
            self.assertIsNone(manifest["current_module"])
            self.assertEqual(manifest["phase"],"report_export")
            self.assertIn("Berichtsexport fehlgeschlagen",manifest["error"])

    def test_code_path_columns_report_matching_row_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            seg=Path(tmp)/"segments.csv"
            book=Path(tmp)/"book.csv"
            seg.write_text("Dokumentname;Segment;Code\nTest;Text;A  > B\n",encoding="utf-8")
            book.write_text("Code;Definition\nA>B;Definition\n",encoding="utf-8")
            self.assertIn(load_segments(seg)[0].human_code,load_codebook(book)[1])
            for path,loader,row in ((seg,load_segments,"Test;Text;A > > B"),(book,load_codebook,"A > > B;Definition")):
                with path.open("a",encoding="utf-8") as f:
                    f.write(row+"\n")
                with self.assertRaisesRegex(ValueError,"Zeile 3: Codepfad"):
                    loader(path)
