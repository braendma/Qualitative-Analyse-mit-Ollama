"""Transport schemas and minimum structural validation for analytical JSON."""
STRING={'type':'string'}
STRINGS={'type':'array','items':STRING}

def obj(fields):
    return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}

def rows(fields):
    return {'type':'array','items':obj(fields)}

THEME={'thema':STRING,'verdichtung':STRING,'segment_ids':STRINGS}
SOURCE_THEME={'thema':STRING,'verdichtung':STRING,'quellen':STRINGS}
SCHEMAS={
    'clusterer':obj({'clusters':rows({'cluster_name':STRING,'definition':STRING,'segments':STRINGS})}),
    'swot':obj({key:rows({'thema':STRING,'analyse':STRING,'segment_ids':STRINGS}) for key in ('Stärken','Schwächen','Chancen','Risiken')}),
    'meta_swot':obj({'cluster':rows({'thema':STRING,'verdichtung':STRING,'finding_ids':STRINGS})}),
    'person_analysis':obj({'zentrale_themen':rows(THEME),'perspektiven':rows({'aussage':STRING,'segment_ids':STRINGS}),
        'spannungsfelder':rows({'beschreibung':STRING,'segment_ids':STRINGS}),
        'kontrastierende_aspekte':rows({'beschreibung':STRING,'segment_ids':STRINGS}),'gesamtverdichtung':STRING}),
    'person_comparison':obj({'gemeinsame_muster':rows({'thema':STRING,'verdichtung':STRING,'personen':STRINGS}),
        'zentrale_unterschiede':rows({'thema':STRING,'beschreibung':STRING,'personenpositionen':rows({'person':STRING,'position':STRING})}),
        'typen':rows({'typ_name':STRING,'beschreibung':STRING,'personen':STRINGS,'merkmale':STRINGS}),
        'nicht_zugeordnete_personen':rows({'person':STRING,'begruendung':STRING}),'gesamtvergleich':STRING}),
    'contrast_analysis':obj({'dominante_muster':rows({'muster':STRING,'beschreibung':STRING,'getragen_von':STRINGS}),
        'negativfaelle':rows({'person':STRING,'bezugs_muster':STRING,'abweichung':STRING,'begruendung':STRING}),
        'spannungen_zwischen_typen':rows({'typen':STRINGS,'beschreibung':STRING}),
        'relativierungen':rows({'aussage':STRING,'bedeutung':STRING}),'gesamteinordnung':STRING}),
    'relation_analysis':obj({'beziehungen':rows({'pair_id':STRING,'thema':STRING,'beziehungstyp':STRING,
        'beschreibung':STRING,'segment_ids_a':STRINGS,'segment_ids_b':STRINGS}),'gesamteinordnung':STRING}),
    'ambiguity_analysis':obj({'ambivalenzen':rows({'thema':STRING,'beschreibung':STRING,'position_a':STRING,'position_b':STRING,
        'segment_ids_a':STRINGS,'segment_ids_b':STRINGS}),'gesamteinordnung':STRING}),
    'evidence_audit':obj({'zuordnungen':rows({'audit_id':STRING,'gegenbeleg_ids':STRINGS,'einordnung':STRING})}),
    'overall_synthesis':obj({'kernergebnisse':rows(SOURCE_THEME),'uebergreifende_muster':rows(SOURCE_THEME),
        'spannungen_und_relativierungen':rows({'aussage':STRING,'einordnung':STRING,'quellen':STRINGS}),
        'methodische_einordnung':STRINGS,'gesamtsynthese':STRING}),
}

def schema_for(module):
    return SCHEMAS[module]

def require_structure(value, module):
    """Reject missing result sections instead of treating them as negative findings."""
    if not isinstance(value,dict):
        raise ValueError(f'{module}: Antwort muss ein JSON-Objekt sein.')
    for key,schema in SCHEMAS[module]['properties'].items():
        expected=list if schema['type']=='array' else str
        if key not in value or not isinstance(value[key],expected):
            raise ValueError(f'{module}: Pflichtfeld {key} fehlt oder hat falschen Typ.')
    return value
