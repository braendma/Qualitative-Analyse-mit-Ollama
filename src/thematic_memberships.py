"""Project complete existing cluster membership; selected quotes cannot use this adapter."""
from runtime_support import fingerprint
from thematic_material import unit_ids_for_segments


def cluster_memberships(material, payload):
    """Return the same topic/cell contract as a future full thematic assignment.

    This counts model-assigned cluster membership inside each code path, not
    mention frequencies of every statement in a cluster's free-form summary.
    """
    def require(condition):
        if not condition:
            raise ValueError('Clusterzuordnung ist unvollständig oder passt nicht zur geprüften Zählgrundlage.')
    require(isinstance(payload,dict) and payload.get('processing_status')=='completed')
    index=material['segment_index'];units=material['units']
    metadata=payload.get('segment_metadata')
    require(isinstance(metadata,dict) and set(metadata)==set(index))
    for sid,entry in metadata.items():
        unit=units[index[sid]['unit_id']]
        passage=index[sid]['unit_id'][len('passage:'):] if unit['kind']=='passage' else None
        require(isinstance(entry,dict) and entry.get('person')==unit['person'] and entry.get('unit_id')==passage)
    clusters=payload.get('clusters');require(isinstance(clusters,list))
    expected={}
    for sid,entry in index.items():expected.setdefault(entry['code_path'],set()).add(sid)
    assigned={code:set() for code in expected}
    topics=[];cells=[];seen=set()
    for cluster in clusters:
        require(isinstance(cluster,dict))
        code=cluster.get('code_path');members=cluster.get('segments')
        require(isinstance(code,str) and code in expected)
        require(isinstance(members,list) and bool(members) and all(isinstance(s,str) for s in members))
        require(len(set(members))==len(members) and set(members)<=expected[code])
        name=cluster.get('cluster_name');definition=cluster.get('definition')
        require(isinstance(name,str) and bool(name.strip()) and isinstance(definition,str) and bool(definition.strip()))
        identity={'code_path':code,'label':name,'definition':definition,'member_segment_ids':sorted(members)}
        tid='cluster_'+fingerprint(identity)[:24]
        require(tid not in seen);seen.add(tid)
        scope=unit_ids_for_segments(material,expected[code]);chosen=set(unit_ids_for_segments(material,members))
        topics.append({'topic_id':tid,'label':name,'definition':definition,'inclusion':'',
            'exclusion':'','kind':'membership','scope_unit_ids':scope})
        cells.extend({'topic_id':tid,'unit_id':uid,'status':'supported' if uid in chosen else 'no_evidence'} for uid in scope)
        assigned[code].update(members)
    require(assigned==expected)
    return {'schema_version':1,'basis_fingerprint':material['basis_fingerprint'],
        'source_fingerprint':fingerprint(payload),'assignment_origin':'complete_cluster_membership',
        'topics':sorted(topics,key=lambda t:t['topic_id']),
        'assignments':sorted(cells,key=lambda c:(c['topic_id'],c['unit_id'])),
        'model_calls':0,'methodological_note':'Gezählt wird die vollständige gespeicherte Clusterzuordnung '
            'innerhalb des jeweiligen Codepfads. Sie ist modellgestützt, nicht menschlich bestätigt. '
            'Freie Zusammenfassungsaussagen haben damit noch keine eigene vollständige Nennungszählung.'}
