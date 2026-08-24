import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blind_coding_core import blind_code_segments
from code_verification_core import verify_segments
from coding_validation_common import MockLLM, load_codebook, load_segments


class CodingValidationTests(unittest.TestCase):
    def test_real_config_is_yaml_and_contains_modules(self):
        config = yaml.safe_load((ROOT / "config_v2.yaml").read_text(encoding="utf-8"))
        modules = {item["id"]: item for item in config["pipeline"]["modules"]}
        self.assertEqual(config["llm"]["model"], "granite4.1:8b")
        self.assertEqual(config["paths"]["input_csv"], "maxqda_export.csv")
        self.assertFalse(config["coding_validation"]["log_raw_llm_output"])
        self.assertIn("code_verification", modules)
        self.assertIn("blind_coding", modules)
        self.assertEqual(modules["coding_agreement"]["depends_on"], ["code_verification", "blind_coding"])

    def test_blind_prompt_does_not_receive_human_code_field(self):
        codebook, _ = load_codebook(ROOT / "tests" / "synthetic_categories.csv")
        segments = load_segments(ROOT / "tests" / "synthetic_segments.csv", {"code": "Code", "segment": "Segment", "person": "Dokumentname"})[:1]
        mock = MockLLM([{
            "segment_id": segments[0].segment_id,
            "predicted_code": codebook[0].code,
            "confidence": "mittel",
            "begruendung": "Test",
            "alternative_codes": [],
        }])
        blind_code_segments(
            segments, codebook,
            {"blind_coding": {"system": "blind", "user": "id={segment_id}\ntext={segment}\nbook={codebook}"}},
            {}, {"model": "mock", "temperature": 0, "max_tokens": 1000}, llm=mock,
        )
        prompt = json.dumps(mock.calls[0], ensure_ascii=False)
        self.assertNotIn("human_code", prompt)
        self.assertNotIn("Menschlich vergebener", prompt)

    def test_unknown_llm_code_becomes_unclear_even_after_repair(self):
        codebook, _ = load_codebook(ROOT / "tests" / "synthetic_categories.csv")
        segments = load_segments(ROOT / "tests" / "synthetic_segments.csv", {"code": "Code", "segment": "Segment", "person": "Dokumentname"})[:1]
        invalid = {
            "segment_id": segments[0].segment_id,
            "predicted_code": "Erfundener > Code",
            "confidence": "hoch",
            "begruendung": "Ungültig",
            "alternative_codes": [],
        }
        _, output = blind_code_segments(
            segments, codebook,
            {"blind_coding": {"system": "blind", "user": "{segment_id} {segment} {codebook}"}},
            {}, {"model": "mock", "temperature": 0, "max_tokens": 1000},
            llm=MockLLM([invalid, invalid]),
        )
        self.assertEqual(output["results"][0]["predicted_code"], "unklar")
        self.assertEqual(output["results"][0]["alternative_codes"], [])

    def test_invented_verification_alternative_is_discarded(self):
        codebook, _ = load_codebook(ROOT / "tests" / "synthetic_categories.csv")
        segments = load_segments(ROOT / "tests" / "synthetic_segments.csv", {"code": "Code", "segment": "Segment", "person": "Dokumentname"})[:1]
        response = {
            "segment_id": segments[0].segment_id,
            "human_code": segments[0].human_code,
            "verification": "bestätigt",
            "confidence": "hoch",
            "begruendung": "Passend.",
            "alternative_codes": ["Motivational Faktoren > Erfunden"],
        }
        _, output = verify_segments(
            segments, codebook,
            {"code_verification": {"system": "verify", "user": "{segment_id} {segment} {human_code} {target_code} {codebook}"}},
            {}, {"model": "mock", "temperature": 0, "max_tokens": 1000},
            llm=MockLLM([response]),
        )
        self.assertEqual(output["results"][0]["verification"], "bestätigt")
        self.assertEqual(output["results"][0]["alternative_codes"], [])

    def test_generic_runner_end_to_end_with_mock_llm(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            command = [
                sys.executable, str(ROOT / "00_WORKFLOW_RUNNER.py"),
                "--config", str(ROOT / "tests" / "config_test.yaml"),
                "--output-dir", temp_dir,
            ]
            result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, msg=result.stdout + "\n" + result.stderr)
            agreement = json.loads((Path(temp_dir) / "coding_agreement_v1.json").read_text(encoding="utf-8"))
            self.assertEqual(agreement["analysis_type"], "Human–LLM Coding Agreement")
            self.assertEqual(agreement["exact_agreement"]["agreements"], 2)
            self.assertEqual(agreement["case_counts"], {"bestätigt": 2, "strittig": 1, "unklar": 0})
            self.assertTrue((Path(temp_dir) / "coding_agreement_confusion.png").is_file())
            full_report = (Path(temp_dir) / "gesamtbericht.md").read_text(encoding="utf-8")
            self.assertIn("## 1. Code-Verifikation", full_report)
            self.assertIn("## 2. Blind-Coding", full_report)
            self.assertIn("## 3. Human–LLM Coding Agreement", full_report)
            for filename in ("code_verification.log", "blind_coding.log", "coding_agreement.log"):
                log_path = Path(temp_dir) / filename
                self.assertTrue(log_path.is_file(), msg=f"Fehlender Log: {filename}")
                self.assertGreater(log_path.stat().st_size, 0)
            verification_log = (Path(temp_dir) / "code_verification.log").read_text(encoding="utf-8")
            blind_log = (Path(temp_dir) / "blind_coding.log").read_text(encoding="utf-8")
            self.assertIn("[Code-Verifikation] [", verification_log)
            self.assertIn("3/3 (100.00%)", verification_log)
            self.assertIn("[Blind-Coding] [", blind_log)
            self.assertIn("3/3 (100.00%)", blind_log)
            agreement_log = (Path(temp_dir) / "coding_agreement.log").read_text(encoding="utf-8")
            self.assertIn("Agreement abgeschlossen", agreement_log)
            for filename in ("code_verification_raw.jsonl", "blind_coding_raw.jsonl"):
                raw_path = Path(temp_dir) / filename
                self.assertTrue(raw_path.is_file(), msg=f"Fehlender Raw-Audit: {filename}")
                events = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
                self.assertTrue(all("raw_output" in event for event in events))
                self.assertIn("initial", {event["phase"] for event in events})
                self.assertIn("repair", {event["phase"] for event in events})
                self.assertIn("accepted", {event["validation_status"] for event in events})


if __name__ == "__main__":
    unittest.main()

