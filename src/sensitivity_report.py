"""Readable sensitivity report, with explicit configuration and repeat denominators."""
from coverage_core import markdown_escape as esc
from stability_report import LABELS, SCOPES, STATES, render_stability, ratio


def render_sensitivity(result):
    lines = ['# Sensitivität gegenüber geänderten Einstellungen', '',
        'Dieser Vergleich prüft, welche Ergebnisse unter anderen Einstellungen auftreten. '
        'Er entscheidet nicht, welche Einstellung richtig oder besser ist. '
        'Die Wiederholungen jeder Einstellung werden zunächst getrennt ausgewertet.', '',
        '## Geplante Änderungen', '']
    for config in result['configurations']:
        lines += ['### ' + esc(config['configuration_id']), '']
        if not config['changes']:
            lines += ['Basiseinstellung.']
        for change in config['changes']:
            if 'before_sha256' in change:
                text = 'gespeicherte Vorlage geändert; ihre tatsächliche Verwendung ist nicht gesondert nachgewiesen'
            else:
                text = str(change['before']) + ' → ' + str(change['after'])
            lines += ['- ' + esc(change['path']) + ': ' + esc(text)]
        if config['joint_changes']:
            lines += ['', '**Mehrere Änderungen gleichzeitig:** Unterschiede lassen sich keiner einzelnen Einstellung zuordnen.']
        lines += ['']
    lines += ['## Unterschiede zwischen Einstellungen', '',
        '„Mindestens einmal“ zählt Einstellungen mit einem Vorkommen in mindestens einer auswertbaren Wiederholung. '
        '„Jedes Mal“ setzt mindestens zwei auswertbare Wiederholungen voraus. '
        'Die jeweiligen Nenner enthalten nur auswertbare Einstellungen. '
        'Die zusätzliche vollständige Auswertung verlangt alle geplanten Wiederholungen. '
        'Ein fehlgeschlagener Lauf zählt nicht als fehlendes Vorkommen. '
        'Code-Mengen schließen inhaltliche Enthaltungen aus; Entscheidungszustände zeigen diese getrennt.', '']
    for mid, comparison in result['comparisons'].items():
        lines += ['### ' + esc(LABELS.get(mid, mid)), '']
        distributions = comparison.get('selection_distributions', [])
        if distributions:
            lines += ['#### Verteilung der ausgewählten Quellen', '',
                'Spannweiten zeigen Minimum bis Maximum über auswertbare Wiederholungen. '
                'Personen zählen Materialeinheiten, Kategorien Codierzeilen innerhalb derselben Hierarchieebene. '
                'Die Anteile beziehen sich auf die jeweils ausgewählten Quellen; sie sind keine vollständigen Themenhäufigkeiten. '
                'Kontextquellen bleiben getrennt von direkten Belegen.', '',
                '| Quellenart / Person oder Kategorie | Einstellung | Auswertbar / geplant | Anzahl min–max | Anteil min–max |',
                '|---|---|---:|---:|---:|']
            for row in distributions[:50]:
                label = SCOPES.get(row['scope'], row['scope']) + ' / ' + (row['person'] if 'person' in row else
                    f"Ebene {row['level']}: {row['code']}")
                for cid, data in row['per_configuration'].items():
                    counts, shares = data['selected_range'], data['share_range']
                    lines += ['| ' + esc(label) + ' | ' + esc(cid) +
                        f" | {data['evaluated_repetitions']}/{data['planned_repetitions']} | " +
                        (f'{counts[0]}–{counts[1]}' if counts else 'nicht auswertbar') + ' | ' +
                        (f'{shares[0]:.1%}–{shares[1]:.1%}' if shares else 'nicht berechenbar') + ' |']
            lines += ['', 'Anteile mit leerem Nenner sind nicht berechenbar und gehen nicht in die Anteilsspannweite ein. '
                      'Alle einzelnen Zähler und Nenner stehen im JSON.', '']
            if len(distributions) > 50:
                lines += [f'{len(distributions) - 50} weitere Verteilungen stehen vollständig im JSON.', '']
        lines += ['#### Befunde und Codierentscheidungen', '']
        if comparison['comparison_status'] == 'not_computable':
            lines += ['Weniger als zwei Einstellungen mit verwertbaren Ergebnissen: kein Vergleich zwischen Einstellungen möglich.', '']
        rows = sorted(comparison['findings'], key=lambda f: f['observed_patterns_differ'] is not True)
        if not rows:
            lines += ['Keine auswertbaren projizierten Befunde oder Codierentscheidungen vorhanden.', '']
        for row in rows[:80]:
            kind = {'exact_projection': 'Exakter Befund', 'reference_binding': 'Belegbindung',
                    'cluster_membership': 'Cluster-Mitgliedschaft', 'decision_state': 'Entscheidungszustand',
                    'code_presence': 'Code-Vorkommen', 'code_set': 'Code-Menge'}[row['feature_type']]
            label = str(row.get('value', row.get('text_preview', 'Quellen: ' + ', '.join(row['segment_ids']))))
            if row['feature_type'] == 'decision_state':
                label = STATES.get(row['value'], row['value'])
            elif row['feature_type'] == 'code_set':
                label = ', '.join(row['value']) or 'keine Codes zugeordnet'
            lines += ['**' + esc(kind) + ': ' + esc(label) + '**', '']
            if row.get('person'):
                lines += ['Person: ' + esc(row['person']) + '. Textstelle: ' + esc(row['text_preview']), '']
            elif row.get('persons'):
                lines += ['Personen: ' + esc(', '.join(row['persons'])), '']
            if row.get('text_preview_truncated'):
                lines += ['Textauszug gekürzt; die Berechnung verwendet die vollständige Projektion bzw. Codierentscheidung.', '']
            lines += ['| Einstellung | Vorkommen / auswertbare Wiederholungen | Geplant |', '|---|---:|---:|']
            for cid, counts in row['per_configuration'].items():
                n, d = counts['present_repetitions'], counts['evaluated_repetitions']
                lines += ['| ' + esc(cid) + ' | ' + (f'{n}/{d}' if d else 'nicht auswertbar') +
                          f" | {counts['planned_repetitions']} |"]
            lines += ['', 'Einstellungen – mindestens einmal: ' + ratio(row['any_observed_repeat']) +
                '; jedes Mal: ' + ratio(row['all_observed_repeats']) + '.',
                'Nur vollständig auswertbare Einstellungen – mindestens einmal: ' + ratio(row['any_repeat_complete_only']) +
                '; jedes Mal: ' + ratio(row['all_repeats_complete_only']) + '.',
                'Geplante Einstellungen: ' + str(row['planned_configurations']) + '.']
            if row['excluded_configurations']:
                lines += ['Nicht auswertbar: ' + esc(', '.join(row['excluded_configurations'])) + '.']
            if row['provisional_configurations']:
                lines += ['Nur vorläufig auswertbar: ' + esc(', '.join(row['provisional_configurations'])) + '.']
            lines += ['']
        if len(rows) > 80:
            lines += [f'{len(rows) - 80} weitere Befunde stehen vollständig in der JSON-Datei.', '']
    lines += ['## Schwankungen innerhalb jeder Einstellung', '']
    for config in result['configurations']:
        cid = config['configuration_id']
        conditions = [c for c in result['conditions'] if c['configuration_id'] == cid]
        digest = set(d for c in conditions for d in c.get('runtime', {}).get('local_digests', []))
        within = {'conditions': conditions, 'notes': result['notes'],
            'comparisons': {mid: c['within_configurations'][cid] for mid, c in result['comparisons'].items()},
            'model_identity_status': 'local_digest_observed' if digest else 'not_observed_or_cloud_weights_unverifiable'}
        lines += ['### Einstellung: ' + esc(cid), '']
        # Reuse the established repeat report; shift headings underneath this setting.
        for line in render_stability(within).splitlines():
            lines.append('###' + line if line.startswith('#') else line)
        lines += ['']
    return '\n'.join(lines)
