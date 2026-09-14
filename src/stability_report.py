"""Readable Markdown for the verified stability result; no opaque finding IDs as prose."""
import json

from coverage_core import markdown_escape as esc

LABELS = {'clusterer': 'Cluster', 'summarizer': 'Zusammenfassungen', 'swot': 'SWOT',
          'meta_swot': 'Meta-SWOT', 'person_analysis': 'Personenanalyse',
          'person_comparison': 'Personenvergleich', 'contrast_analysis': 'Kontraste und Negativfälle',
          'relation_analysis': 'Relationen', 'ambiguity_analysis': 'Ambivalenzen',
          'evidence_audit': 'Evidenzprüfung', 'overall_synthesis': 'Gesamtsynthese',
          'blind_coding': 'Unabhängige Codierung', 'code_verification': 'Codierüberprüfung'}
SCOPES = {'direct': 'Direkte Belegauswahl', 'input_association': 'Zuordnung von Eingabestellen',
          'source_group': 'Kontext aus Quellengruppen', 'person_reference': 'Personenreferenzen'}
STATES = {'success': 'abgeschlossen', 'failed': 'fehlgeschlagen', 'pending': 'noch nicht gestartet',
          'paused': 'pausiert', 'interrupted': 'unterbrochen', 'invalid': 'ungültig',
          'invalid_artifact': 'Ergebnisstruktur oder Referenzen ungültig', 'completed': 'abgeschlossen',
          'assigned': 'zugeordnet', 'none': 'begründet keine Zuordnung', 'abstained': 'inhaltlich unsicher'}


def ratio(value):
    if value is None or value.get('value') is None:
        return 'nicht berechenbar'
    return f"{value['numerator']}/{value['denominator']} ({value['value']:.1%})"


def render_stability(result):
    lines = ['# Stabilität bei wiederholter Analyse', '',
        'Dieser Bericht beschreibt Wiederholbarkeit unter derselben gespeicherten Laufgrundlage. '
        'Er bewertet weder die Richtigkeit einer Codierung noch die Wahrheit einer Interpretation. '
        'Abweichende Formulierungen können denselben Inhalt ausdrücken; das wird hier nicht automatisch entschieden.', '',
        '## Wiederholungen und Laufbedingungen', '',
        '| Wiederholung | Zustand | Akzeptierte Anfragen | Fehlgeschlagene Anfragen |',
        '|---|---|---:|---:|']
    for condition in result['conditions']:
        runtime = condition.get('runtime', {})
        counts = runtime.get('modules', {}).values()
        lines.append('| ' + esc(condition['sample_id']) + ' | ' + esc(STATES.get(condition['status'], condition['status'])) +
            f" | {sum(c['accepted'] for c in counts)} | {sum(c['failed'] for c in counts)} |")
    lines += ['', 'Die Anfragezahl bezieht sich auf das im Manifest gesicherte Inventar und enthält auch Reparaturversuche. '
              'Bei unterbrochenen Läufen können weitere, noch nicht im Manifest gesicherte Versuche fehlen. '
              'Akzeptierte Anfragen sind kein Nachweis '
              'inhaltlich gültiger Antworten oder der serverinternen Durchsetzung aller Parameter.', '']
    for note in result['notes']:
        lines += ['- ' + esc(note)]
    lines += ['', 'Modellgewichte: ' + ('derselbe lokale Digest wurde vor und nach den akzeptierten Anfragen beobachtet; '
              'dies ist keine Prüfung jedes einzelnen Berechnungsschritts.'
              if result.get('model_identity_status') == 'local_digest_observed' else
              'nicht beobachtet oder beim Cloud-Anbieter nicht unabhängig prüfbar.'), '']
    lines += ['', '### Tatsächlich übertragene Parameter', '']
    for condition in result['conditions']:
        lines += ['**' + esc(condition['sample_id']) + '**', '']
        profiles = condition.get('runtime', {}).get('profiles', [])
        if not profiles:
            lines += ['Keine akzeptierten Anfragen nachgewiesen. Laufzeitbedingungen bleiben unbestätigt.', '']
        for p in profiles:
            settings = json.dumps(p['parameters_sent'], ensure_ascii=False, sort_keys=True)
            contexts = ', '.join(map(str, p['observed_context_lengths'])) or 'nicht beobachtet'
            lines += ['- ' + esc(LABELS.get(p['module'], p['module'])) + ': ' + esc(p['provider']) +
                      ' / ' + esc(p['model']) + f"; {p['accepted_requests']} Anfragen; " + esc(settings) +
                      '; geladener Kontext: ' + esc(contexts)]
        lines += ['']
    lines += ['## Modulvergleiche', '']
    for mid, data in result['comparisons'].items():
        lines += ['### ' + esc(LABELS.get(mid, mid)), '',
                  f"Verwertbare Wiederholungen: {len(data['included_samples'])} von {data['requested_samples']}.", '']
        for excluded in data['excluded_samples']:
            lines += ['- Ausgeschlossen: ' + esc(excluded['sample_id']) + ' – ' + esc(STATES.get(excluded['reason'], excluded['reason']))]
        same = data['runtime_comparison']['parameter_profiles_same']
        lines += ['', 'Übertragene Parameterprofile: ' + ('gleich' if same is True else
                  'unterschiedlich; Bedingungen vor Interpretation prüfen' if same is False else 'nicht ausreichend nachgewiesen') + '.', '']
        if data['comparison_status'] != 'available':
            lines += ['Weniger als zwei verwertbare Wiederholungen: kein Stabilitätsvergleich möglich.', '']
            continue
        for pair in data['pairs']:
            lines += ['**' + esc(pair['left']) + ' ↔ ' + esc(pair['right']) + '**', '']
            measures = [('state_agreement', 'Übereinstimmung der Entscheidungszustände'),
                        ('code_set_agreement', 'Exakte Code-Mengenübereinstimmung'),
                        ('alternative_set_agreement', 'Gleiche Alternativcodemengen der Überprüfung'),
                        ('cluster_membership_overlap', 'Überlappung vollständiger Cluster-Mitgliedsmengen'),
                        ('coassignment_overlap', 'Überlappung gemeinsam gruppierter Segmentpaare'),
                        ('projected_record_overlap', 'Überlappung projizierter Texte und Referenzen'),
                        ('projected_reference_binding_overlap', 'Überlappung der Referenzbindungen ohne Text')]
            for key, label in measures:
                if key in pair:
                    lines += ['- ' + label + ': ' + ratio(pair[key])]
            if 'technical_excluded_units' in pair:
                lines += [f"- Wegen technischer Fehler ausgeschlossene Einheiten: {pair['technical_excluded_units']}"]
                if 'abstention_excluded_units' in pair:
                    lines += [f"- Wegen Unsicherheit aus dem Codevergleich ausgeschlossen: {pair['abstention_excluded_units']}"]
            for ref in pair.get('reference_comparisons', []):
                context = ' / '.join(ref['comparison_context'])
                label = SCOPES.get(ref['scope'], ref['scope']) + ' / ' + ref['kind'] + (' / ' + context if context else '')
                lines += ['- ' + esc(label) + ': Segmentüberlappung ' + ratio(ref['segment_overlap']) +
                          '; Personenüberlappung ' + ratio(ref['person_overlap'])]
            lines += ['']
            for selection in pair.get('selection_distribution_changes', []):
                lines += ['**Verteilung: ' + esc(SCOPES.get(selection['scope'], selection['scope'])) + '**', '']
                if not selection['comparable']:
                    lines += ['Keine vergleichbare Verteilung von Textstellen: nur Personenreferenzen oder fehlende Segmentverknüpfungen. '
                              'Aus Personennamen werden keine Textstellen oder Kategorien ergänzt.', '']
                    continue
                lines += [f"Ausgewählte Materialeinheiten: {selection['selected_units_left']} → {selection['selected_units_right']} "
                          f"bei {selection['material_units']} Einheiten im gemeinsamen Export.", '',
                          'Personenanteile zählen eindeutige explizite Passagen, sonst Codierzeilen. '
                          'Kategorieanteile zählen referenzierte Codierzeilen je Hierarchieebene. '
                          'Diese Werte beschreiben die gespeicherte Quellenauswahl, keine umfassende thematische Nennungshäufigkeit.', '']
                people = [p for p in selection['by_person'] if p['selected_units_left'] != p['selected_units_right'] or p['share_delta'] not in (None, 0)]
                categories = [p for p in selection['by_category'] if p['selected_coding_rows_left'] != p['selected_coding_rows_right'] or p['share_delta'] not in (None, 0)]
                def fraction(n, d):
                    return f'{n}/{d} ({n/d:.1%})' if d else 'nicht berechenbar (keine ausgewählten Einheiten)'
                if people:
                    lines += ['| Person | Anteil links | Anteil rechts | Eigene Materialeinheiten im Export |', '|---|---:|---:|---:|']
                    for p in people[:50]:
                        lines += ['| ' + esc(p['person']) + ' | ' + fraction(p['selected_units_left'],selection['selected_units_left']) +
                                  ' | ' + fraction(p['selected_units_right'],selection['selected_units_right']) + f" | {p['material_units']} |"]
                    lines += ['']
                if categories:
                    lines += ['| Ebene / Kategorie | Anteil links | Anteil rechts | Codierzeilen im Export |', '|---|---:|---:|---:|']
                    for p in categories[:50]:
                        lines += [f"| {p['level']} / " + esc(p['code']) + ' | ' + fraction(p['selected_coding_rows_left'],p['level_selected_rows_left']) +
                                  ' | ' + fraction(p['selected_coding_rows_right'],p['level_selected_rows_right']) + f" | {p['material_coding_rows']} |"]
                    lines += ['']
                if not people and not categories:
                    lines += ['Keine Änderung der gespeicherten Auswahlzahlen oder berechenbaren Anteile.', '']
                if len(people)>50 or len(categories)>50:
                    lines += [f'{max(0,len(people)-50)} weitere Personen und {max(0,len(categories)-50)} weitere Kategorieänderungen stehen im JSON-Ergebnis.', '']
        changed = [r for r in data.get('record_occurrences', []) if r['repeat_status'] == 'variable']
        if changed:
            lines += ['#### Unterschiedlich vorkommende projizierte Befunde', '',
                      f'{len(changed)} unterschiedliche Text-/Referenzkombinationen; keine automatisch bestätigten Bedeutungsänderungen.', '']
            for row in changed[:50]:
                lines += ['> ' + esc(row['text_preview'] or 'Kein Textfeld in dieser Quellenprojektion.'), '',
                    'Vorkommen: ' + ratio(row['sample_frequency']) + '; Quellenart: ' + esc(SCOPES.get(row['scope'], row['scope'])) +
                    '; Textstellen: ' + esc(', '.join(row['segment_ids']) or 'keine direkten Segmentreferenzen') +
                    '; Personen: ' + esc(', '.join(row['persons']) or 'nicht ausdrücklich referenziert') + '.', '']
                if row['text_preview_truncated']:
                    lines += [f"Auszug gekürzt; Original enthält {row['text_characters']} Zeichen. Vergleich verwendete den vollständigen Text.", '']
            if len(changed) > 50:
                lines += [f'{len(changed)-50} weitere Kombinationen stehen vollständig im JSON-Diagnoseergebnis.', '']
        units = [u for u in data.get('units', []) if u['technical_failure_samples'] or
                 len({(r['state'],tuple(r['codes'])) for r in u['observations'].values()}) > 1]
        if units:
            lines += ['#### Codierungen zur Nachprüfung', '']
            for unit in units[:50]:
                lines += ['**Person ' + esc(unit['person']) + '; Textstelle ' + esc(unit['unit_id']) + '**', '',
                          '> ' + esc(unit['text_preview']), '']
                if unit['text_preview_truncated']:
                    lines += [f"Auszug gekürzt ({unit['text_characters']} Zeichen im Original).", '']
                for sid, row in unit['observations'].items():
                    lines += ['- ' + esc(sid) + ': ' + esc(STATES.get(row['state'], row['state'])) + '; Codes: ' + esc(', '.join(row['codes']) or 'keine') +
                              '; Verarbeitung: ' + esc(STATES.get(row['processing_status'], row['processing_status']))]
                lines += ['']
            if len(units) > 50:
                lines += [f'{len(units)-50} weitere Einheiten stehen vollständig im JSON-Diagnoseergebnis.', '']
        for sample in data.get('sample_details', []):
            for warning in sample['warnings']:
                lines += ['- ' + esc(sample['sample_id']) + ': ' + esc(warning)]
            if sample.get('coassignment', {}).get('status') == 'not_calculated':
                lines += ['- ' + esc(sample['sample_id']) + ': Paarberechnung wegen Umfangsgrenze vollständig ausgelassen.']
        lines += ['']
    lines += ['## Interpretation', '',
              'Ein leerer Nenner ergibt keinen Prozentwert. Gleiche Unsicherheiten sind keine bestätigten Codes. '
              'Wiederholtes Auftreten eines Befunds zählt Läufe, nicht Interviewpersonen oder thematische Nennungen. '
              'Quellengruppen bleiben Kontext und werden nicht als direkte Belege ausgegeben. '
              'Textprojektionen erfassen nicht alle Beziehungen zwischen Teilbefunden und nicht jeden freien Berichtstext.', '']
    return '\n'.join(lines)
