"""Readable progress, restricted to built-in labels and bounded counters."""
import time
import math
from progress_presentation import module_overview, phase_lines, request_age_lines, unknown_work_lines

MODULES={
 'clusterer':'Clusteranalyse','code_verification':'Code-Prüfung','blind_coding':'Blind-Coding',
 'coding_agreement':'Codierübereinstimmung','summarizer':'Cluster-Zusammenfassungen',
 'swot':'SWOT','meta_swot':'Meta-SWOT','person_analysis':'Personenanalyse',
 'person_comparison':'Personenvergleich','contrast_analysis':'Kontrastanalyse',
 'relation_analysis':'Zusammenhangsanalyse','ambiguity_analysis':'Ambivalenzanalyse',
 'evidence_audit':'Evidence-Audit','review_queue':'Prüfliste','overall_synthesis':'Gesamtsynthese'}
UNITS={'passages':'Passagen','rows':'Codierzeilen','batches':'Prüfblöcke',
       'categories':'Kategorien','persons':'Personen','summaries':'Zusammenfassungen','dimensions':'SWOT-Dimensionen',
       'pairs':'Paare','steps':'Schritte'}
PHASES={'preparation':'Vorbereitung','analysis':'Analyse','person_reduction':'Vorbereitung je Person',
        'comparison':'Vergleich','synthesis':'Abschließende Synthese','reduction_level':'Verdichtungsebene',
        'finished':'Abgeschlossen','cluster_summaries':'Clusterzusammenfassungen','overall_summary':'Gesamtzusammenfassung'}


def counter(value):
    return value if type(value) is int and 0<=value<=10000000 else None


def format_progress(completed,total,detail=None,now=None):
    now=time.time() if now is None else now
    lines=['📊 Qualitative Analyse · '+time.strftime('%H:%M',time.localtime(now))]
    count,modules=counter(completed),counter(total)
    if count is not None and modules is not None and 0<=count<=modules<=100:
        lines.extend(module_overview(count,modules))
    if isinstance(detail,dict) and detail:
        mid=detail.get('module');unit=detail.get('unit')
        label=MODULES.get(mid,'Aktuelles Modul') if isinstance(mid,str) else 'Aktuelles Modul'
        unit=UNITS.get(unit,'Einheiten') if isinstance(unit,str) else 'Einheiten'
        lines.extend(['',label])
        phase=detail.get('phase')
        lines.extend(phase_lines(detail,PHASES))
        done,amount=counter(detail.get('completed')),counter(detail.get('total'))
        if done is not None and amount and done<=amount:
            filled=done*10//amount
            lines.append('▰'*filled+'▱'*(10-filled)+f' {done*100//amount} %')
            lines.append(f'{done} von {amount} {unit}')
        elif done==0 and amount==0:lines.append('Keine Arbeitseinheiten in dieser Phase.')
        else:lines.extend(unknown_work_lines(mid))
        subdone,subtotal=counter(detail.get('detail_completed')),counter(detail.get('detail_total'))
        if subdone is not None and subtotal and subdone<=subtotal:
            lines.append(f'Aktueller Teilabschnitt: {subdone}/{subtotal} Prüfblöcke')
        reused=counter(detail.get('reused'))
        if reused and done is not None and reused<=done:
            lines.append(f'Davon {reused} aus geprüften Zwischenergebnissen wiederverwendet.')
        requests=counter(detail.get('requests'));active=counter(detail.get('active_requests'))
        if requests is not None:lines.append(f'Modellantworten: {requests}')
        if active is not None:lines.append(f'Modellanfragen gleichzeitig aktiv: {active}')
        elif detail.get('request_active') is True:lines.append('Eine Modellanfrage läuft.')
        lines.extend(request_age_lines(detail,now))
        stamp=detail.get('last_response_at')
        if type(stamp) in (int,float) and math.isfinite(stamp) and 0<stamp<=now:
            seconds=int(now-stamp)
            age=f'{seconds} Sekunden' if seconds<60 else f'{seconds//60} Minuten'
            lines.append(f'Letzte Modellantwort vor {age}.')
        if (counter(detail.get('failed')) or 0)>0 or detail.get('context_blocked') is True:
            lines.append('⚠️ Teilproblem erkannt · Details in der Oberfläche prüfen.')
    lines.extend(['','Modulübersicht zählt fertige Module, keine verstrichene Laufzeit. Teilbalken gelten nur für den jeweiligen Abschnitt.'])
    return '\n'.join(lines)
