import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from failure_help import failure_help


class FailureHelpTests(unittest.TestCase):
    def test_invalid_audit_references_explain_preserved_results_and_validation(self):
        for marker in ('Audit enthält ungültige Gegenbeleg-IDs.', 'Unbekannte oder doppelte Audit-ID.', 'Audit unvollständig: erwartete Audit-IDs fehlen.'):
            result=failure_help(marker+' SECRET_TEST')
            self.assertEqual(result['kind'],'response')
            self.assertIn('Teilprüfungen bleiben gespeichert',result['action'])
            self.assertIn('nicht von Hand löschen',result['action'])
            self.assertNotIn('SECRET_TEST',str(result))

    def test_known_failures_provide_distinct_actions_without_echoing_private_text(self):
        for marker,kind in [('CUDA out of memory','memory'),('ContextBudgetError','context'),
                            ('Status 401','credentials'),('Status 429','quota'),
                            ('ConnectError','connection'),('LLMResponseError','response'),
                            ('Zwischenzusammenfassung','reduction'),('unbekannt','unknown')]:
            with self.subTest(kind=kind):
                result=failure_help(marker+' SECRET_TEST interview-content /private/path')
                self.assertEqual(result['kind'],kind)
                self.assertTrue(result['action'])
                self.assertNotIn('SECRET_TEST',str(result))
                self.assertNotIn('interview-content',str(result))
                self.assertIn('ursprünglichen',result['resume_note'])


if __name__=='__main__':unittest.main()
