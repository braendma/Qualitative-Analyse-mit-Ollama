"""Run the analysis workflow on two invented MAXQDA rows with an explicitly chosen model."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from local_app import App


def smoke(provider, model):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        app = App(tmp / "app")
        pid = app.create("Synthetischer Modelltest")["id"]
        inputs = {
            "segments": "Dokumentname;Code;Segment\nDemo;Werkzeug>Wahl;Ich verwende einen Hammer.\n"
                        "Demo;Werkzeug > Wahl;Ich nehme den Hammer für den Nagel.\n",
            "codebook": "Code;Definition\nWerkzeug > Wahl;Aussagen über die Wahl eines Werkzeugs.\n",
        }
        for kind, text in inputs.items():
            encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
            app.upload(pid, kind, kind + ".csv", encoded)
        columns = {"code": "Code", "segment": "Segment", "person": "Dokumentname"}
        preview = app.person_preview(pid, columns)
        opts = {"columns": columns, "book_columns": {"code": "Code", "definition": "Definition"},
                "person_identity": {"confirmed": True, "fingerprint": preview["fingerprint"],
                                    "mapping": {"Demo": "Demo"}},
                "modules": ["clusterer"], "label_mode": "unspecified", "provider": provider,
                "gdpr_relevant": provider == "ollama_local", "model": model, "num_ctx": 16384,
                "max_tokens": 2048, "think": False, "timeout_seconds": 180}
        if provider == "litellm":
            key = os.environ["LITELLM_API_KEY"]
            app.privacy(pid, False)
            app.save_provider_key(pid, {**opts, "key": key})
            ids = app.list_proxy_models(pid, opts)["models"]
            if model not in ids:
                matches = [mid for mid in ids if mid.rsplit("/", 1)[-1] == model]
                if len(matches) != 1:
                    raise ValueError("Modell-ID nicht eindeutig in der UP-Modellliste: " + model)
                opts["model"] = matches[0]
        checked = app.save(pid, opts)
        assert checked["valid"] and checked["segments"] == 2 and checked["codes"] == 1
        project = app.project(pid)
        config = app.project_dir(pid) / "revisions" / project["revision"] / "config.yaml"
        results = tmp / "runs"
        results.mkdir()
        cmd = [sys.executable, str(ROOT/"src"/"00_WORKFLOW_RUNNER.py"), "--config", str(config),
               "--output-dir", str(results)]
        subprocess.run(cmd, cwd=tmp, check=True, timeout=900)
        manifests = list(results.rglob("workflow_manifest.json"))
        assert len(manifests) == 1
        run = manifests[0].parent
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        assert manifest["status"] == "success" and manifest["module_status"]["clusterer"] == "success"
        assert (run/"gesamtbericht.html").is_file()
        clusters = json.loads((run/"clusters_output.json").read_text(encoding="utf-8"))
        assert clusters["clusters"]
        print(json.dumps({"version": (ROOT/"VERSION").read_text().strip(), "provider":provider,
                          "model":opts["model"], "segments":2,"code_paths":1,
                          "clusters":len(clusters["clusters"]), "html":True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=["litellm", "ollama_local"])
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    smoke(args.provider, args.model)
