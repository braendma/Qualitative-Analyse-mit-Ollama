import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from failure_help import failure_help


class FailureHelpTests(unittest.TestCase):
    def test_transport_debug_does_not_hide_final_response_failure(self):
        prefix = ('2026-09-19 [DEBUG] connect_tcp.started timeout=180.0\n'
                  '2026-09-19 [INFO] HTTP Request: POST /api/chat "HTTP/1.1 200 OK"\n'
                  'Traceback (most recent call last):\n')
        for error in ('llm_client.LLMResponseError: Clusterantwort unvollständig: 1 Segmente fehlen.',
                      'ValueError: Thematische Zuordnung bleibt nach Korrektur ungültig oder unvollständig; Teilanalyse erneut starten.'):
            result = failure_help(prefix + error + ' PRIVATE_TEST')
            self.assertEqual(result['kind'], 'response')
            self.assertNotIn('PRIVATE_TEST', str(result))
            self.assertIn('Vollständigkeitsprüfung', result['action'])

    def test_final_exception_overrides_earlier_failure_or_prompt_keywords(self):
        self.assertEqual(failure_help('LLMResponseError: failed\nhttpx.ReadTimeout: timed out')['kind'], 'connection')
        self.assertEqual(failure_help('Interview: CUDA out of memory\nValueError: unbekannter Fehler')['kind'], 'unknown')
        self.assertEqual(failure_help('[DEBUG] connect_tcp.started timeout=180.0\nUnbekannter Fehler')['kind'], 'unknown')

    def test_diagnostic_failures_explain_sources_and_integrity_without_model_tuning(self):
        for marker, kind in [('Diagnose abgelehnt', 'diagnostic_integrity'),
                             ('Diagnoseausgabe existiert bereits', 'diagnostic_output'),
                             ('Modul information_loss lieferte unvollständige Ergebnisse', 'diagnostic_sources'),
                             ('Modul codebook_diagnostics lieferte unvollständige Ergebnisse', 'diagnostic_sources'),
                             ('Modul coverage lieferte unvollständige Ergebnisse', 'diagnostic_sources')]:
            result=failure_help(marker+' PRIVATE_CONTENT')
            self.assertEqual(result['kind'],kind)
            self.assertNotIn('PRIVATE_CONTENT',str(result))
        self.assertIn('erneut berechnet',result['action'])

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
