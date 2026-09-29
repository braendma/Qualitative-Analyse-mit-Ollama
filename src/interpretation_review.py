"""Local, conservative review hints. Never correct or approve model output.

Rules inspect the original paragraph and its bound counting/evidence context.
Absence of a hint is not a semantic validation result. No network/model calls.
"""
import re

RULESET = '0.5.2-1'


def count_explanation(row):
    """Only computed values; no model-written conclusions or inferred zeros."""
    if not row:
        return ''
    scope, coverage = row['scope'], row['coverage']
    def value(n):
        return 'nicht bestimmbar' if n is None else str(n)
    parts = [
        f"Bezugsmenge dieses Themas: {value(scope['person_count'])} Personen, "
        f"{value(scope['unit_count'])} Materialeinheiten.",
        f"Entschiedene Zuordnungen: {coverage['decided_cells']} von {coverage['expected_cells']}. "
        'Vollständigkeit beschreibt nur den Bearbeitungsstand, keine fachliche Bestätigung oder Wirksamkeit.',
    ]
    if row['kind'] == 'derived':
        parts.append('Gezählt wird die modellseitig zugeordnete Materialbasis einer analytischen Ableitung; '
                     'das ist keine direkte Zustimmung, Ablehnung oder ausdrückliche Nennung durch Personen.')
    elif row['kind'] == 'membership':
        parts.append('Gezählt wird die Clusterzuordnung, nicht die Belegung jeder Aussage der Zusammenfassung.')
    else:
        parts.append('Gezählt werden modellseitige Themenzuordnungen zu Äußerungen; diese sind noch fachlich zu prüfen.')
    for stance, label in [('supporting', 'Stützend'), ('opposing', 'Entgegenstehend'), ('both', 'Beide Positionen')]:
        count = row['counts'][stance]
        parts.append(f"{label}: beobachtet {value(count['observed_person_count'])} Personen und "
                     f"{value(count['observed_unit_count'])} Einheiten; vollständig bestimmbar: "
                     f"{value(count['exact_person_count'])} Personen und {value(count['exact_unit_count'])} Einheiten.")
    parts.append('Nicht bestimmbar bedeutet nicht null. Beobachtete Werte können Untergrenzen sein. '
                 'Fehlende Evidenz ist keine Gegenposition. „Beide Positionen“ bedeutet Stützung und Widerspruch '
                 'zur selben geprüften Aussage; bei Personen auch in verschiedenen Passagen. '
                 'Anteile belegen weder Repräsentativität noch Kausalität oder Wirksamkeit.')
    return ' '.join(parts)


def review_hints(text, evidence=(), row=None):
    """Return candidates for human checking, bound to this unchanged paragraph."""
    hints = []
    def add(code, message, ids=()):
        if not any(h['code'] == code for h in hints):
            hints.append({'code': code, 'ruleset': RULESET, 'message': message,
                          'evidence_ids': list(dict.fromkeys(ids))})
    # Sentence-local guards avoid treating explicit methodological exclusions as claims.
    sentences = re.split(r'(?<=[.!?;])\s+', text.casefold())
    for sentence in sentences:
        exclusion = re.search(r'\b(?:nicht|keine?[nmrst]?|weder|ohne)\b', sentence)
        conclusion = re.search(r'\b(?:bestätigt|beweist|belegt|zeigt|stützt|nachgewiesen|nachweis)\b', sentence)
        numerical_basis = re.search(r'anteil|häufigkeit|zähl|zuordnung|complete|share|%', sentence)
        representativeness = re.search(r'repräsentativ', sentence) and not re.search(r'begrenzt|eingeschränkt', sentence)
        if (conclusion and not exclusion and (representativeness or
                (numerical_basis and re.search(r'kausal|wirksam|effektiv', sentence)))):
            add('unsupported_inference', 'Eine Formulierung legt Repräsentativität, Kausalität oder Wirksamkeit nahe. '
                'Prüfen, ob dafür eigenständige Belege vorliegen; Häufigkeiten allein reichen nicht.')
        if (re.search(r'complete\s*:\s*true|vollständige\w* (?:modell)?zuordnung', sentence)
                and conclusion and not exclusion and re.search(r'wirksam|valid|richtig|qualitative einschätzung', sentence)):
            add('completion_not_validity', 'Vollständige Zuordnung ist ein Bearbeitungsstatus. '
                'Daraus folgt keine fachliche Richtigkeit oder wirksame Praxis.')
        if (re.search(r'\bboth\b|beide positionen', sentence)
                and re.search(r'\b(?:da|weil|bedeutet)\b', sentence)
                and re.search(r'allen? (?:untersuchten )?(?:personen|passagen|fällen)', sentence)
                and not re.search(r'bedeutet (?:gerade )?nicht|nicht .+sondern', sentence)):
            add('both_not_universal', 'Die Begründung scheint „beide Positionen“ mit einer Nennung durch alle zu verbinden. '
                'Gemeint sind stützende und entgegenstehende Positionen zur selben Aussage, nicht universelle Nennung.')
        if (row and row['kind'] == 'derived'
                and re.search(r'explizit thematisiert|direkt ablehnend|ausdrücklich (?:genannt|abgelehnt)|direkte zustimmung', sentence)
                and not exclusion):
            add('derived_not_explicit', 'Diese Zahlen betreffen Materialstützung einer analytischen Ableitung. '
                'Direkte Äußerung, Zustimmung oder Ablehnung durch Personen anhand der Zitate gesondert prüfen.')
        if (row and re.search(r'(?:nicht für alle|für .* nicht) .*gilt|nicht zutrifft', sentence)
                and re.search(r'%|häufigkeit|anteil|no_evidence', sentence)
                and not re.search(r'(?:beweist?|zeigt|belegt|folgt) (?:jedoch )?nicht|kein nachweis', sentence)):
            add('missing_not_false', 'Ein fehlender oder kleinerer Zuordnungsanteil beweist nicht, dass die Aussage '
                'für die übrigen Fälle falsch ist. Fehlende Evidenz und Gegenposition unterscheiden.')
        if (row and re.search(r'(?:pro|je(?:der)?) person', sentence)
                and not re.search(r'nicht (?:pro|je(?:der)?) person', sentence)):
            c = row['counts']['supporting']
            if c['observed_person_count'] == 1 and (row['scope']['person_count'] or 0) > 1:
                add('single_not_each', 'Die Tabelle weist eine stützend zugeordnete Person innerhalb einer größeren '
                    'Bezugsmenge aus. Prüfen, ob „pro Person“ irrtümlich auf sämtliche Personen bezogen wird.')

    # Narrow lexical candidate detection, not a general contradiction classifier.
    predicates = r'\b(?:startet|starten|funktioniert|funktionieren|läuft|laufen|gelingt|gelingen)\b'
    def anchors(s):
        return {w[:7] for w in re.findall(r'\b[a-zäöüß]{6,}\b', s)
                if w not in {'simulation', 'startet', 'starten', 'funktioniert', 'funktionieren',
                             'diesem', 'dieser', 'werden', 'können', 'während', 'jedoch'}}
    for quote in evidence:
        source = quote.get('text', '').casefold()
        for match in re.finditer(predicates, source):
            tail = source[match.end():].split(';')[0].split('.')[0][:60]
            if not re.search(r'\bnicht\b|\bkein\w*\b', tail):
                continue
            for clause in re.split(r'[,;.!?]', text.casefold()):
                claim = re.search(r'\b' + re.escape(match.group()) + r'\b', clause)
                if not claim or re.search(r'\bnicht\b|\bkein\w*\b', clause):
                    continue
                if anchors(source) & anchors(clause):
                    add('possible_negation_loss', 'Ein zugeordnetes Originalzitat verneint einen ähnlichen Vorgang, '
                        'der hier bejaht erscheint. Gleichen Gegenstand, Bedingungen und Verneinung prüfen; '
                        'dies ist ein Verdacht, kein automatisch festgestellter Widerspruch.', [quote.get('id', '')])
    return hints
