"""Reproducible fictional interview material; no study quotations are used."""
import csv
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'demo'
CASES=[
    (('Lernangebot','Praxis','Übertragung','gelingt'),'Gelerntes wurde in einer konkreten Arbeitssituation erfolgreich angewendet.',[
        'Die Fehlersuche aus dem Kurs konnte ich am nächsten Tag an unserem Übungsgerät wiederholen. Erst danach habe ich den Ablauf verstanden.',
        'Beim zweiten Versuch habe ich die Messwerte selbst geprüft. Die Checkliste aus dem Seminar war dafür wirklich brauchbar.',
        'Das Beispiel war anders als meine Aufgabe, aber das Vorgehen ließ sich übertragen. Ganz ohne Rückfrage ging es noch nicht.']),
    (('Lernangebot','Praxis','Übertragung','stockt'),'Ein konkreter Transfer scheitert oder bleibt trotz Lernangebot unsicher.',[
        'Im Kurs konnte ich jeden Schritt nachmachen. Allein vor einer anderen Maschine wusste ich dann nicht, womit ich anfangen soll.',
        'Das Verfahren kenne ich jetzt dem Namen nach; für meinen Arbeitsauftrag hilft mir das bisher noch nicht.',
        'Die Erklärung klang klar. Beim eigenen Versuch passten die Anschlüsse nicht, und ich habe die Aufgabe abgebrochen.']),
    (('Lernangebot','Praxis','Übung',''),'Bewertung von Übungsmöglichkeiten ohne Aussage über späteren Transfer.',[
        'Es wäre gut, wenn wir denselben Versuch zweimal durchführen dürften. Nach einem Durchgang ist die Zeit schon vorbei.',
        'Die kleinen Übungsgruppen fand ich angenehm. Ob ich das später allein kann, weiß ich noch nicht.',
        'Für die Station hatten wir nur ein Messgerät. Ich habe zugesehen, aber selbst kaum etwas ausprobiert.']),
    (('Lernangebot','Materialien','',''),'Bewertung der bereitgestellten Lernmaterialien.',[
        'Die Skizzen helfen mir. Bei Tabelle 3 fehlen allerdings die Einheiten; das macht das Nachlesen schwierig.',
        'Ich nutze vor allem die kurze Anleitung. Das lange Video habe ich bisher nicht bis zum Ende angesehen.',
        'Im Skript steht „vor dem Einschalten prüfen“. Was genau geprüft werden soll, wird auf der Seite nicht erläutert.']),
    (('Organisation','Zeit','Vereinbarkeit','entlastend'),'Die zeitliche Gestaltung erleichtert die Teilnahme.',[
        'Seit die Termine früher angekündigt werden, kann ich meinen Dienst tauschen. Dadurch musste ich keinen Kurstag mehr auslassen.',
        'Das Material am Abend abrufen zu können, hilft mir. Tagsüber habe ich dafür keinen freien Block.',
        'Zwei kurze Treffen passen für mich besser als ein ganzer Samstag. So bleibt der Nachmittag für andere Aufgaben frei.']),
    (('Organisation','Zeit','Vereinbarkeit','belastend'),'Die zeitliche Gestaltung erschwert die Teilnahme.',[
        'Wenn der Termin erst am Vortag verschoben wird, bekomme ich meinen Dienst nicht mehr getauscht.',
        'Das flexible Lernen klingt gut. Tatsächlich sitze ich regelmäßig noch spät am Abend daran und bin dann zu müde.',
        'Der Samstagstermin ist für mich schwierig. Ich konnte deshalb nur die erste Hälfte des letzten Treffens besuchen.']),
    (('Organisation','Zugang','Technik',''),'Technische Bedingungen ermöglichen oder behindern den Zugang.',[
        'Am eigenen Rechner läuft die Simulation. Auf dem Leihgerät startet sie nicht; die Fehlermeldung bleibt leer.',
        'Die Anmeldung klappt inzwischen. Für jede Sitzung muss ich aber erneut ein Passwort anfordern.',
        'Ich habe die Datei heruntergeladen, bevor die Verbindung abbrach. Ohne diese Kopie hätte ich nicht mitarbeiten können.']),
    (('Organisation','Unterstützung','',''),'Erfahrungen mit organisatorischer oder fachlicher Hilfe.',[
        'Auf meine Frage kam noch am selben Tag eine Antwort. Sie hat das Problem eingegrenzt, aber nicht vollständig gelöst.',
        'Ich wusste nicht, wen ich bei dem Fehler ansprechen soll. Zwei Stellen haben mich jeweils weiterverwiesen.',
        'In der Sprechstunde konnte ich meinen Versuch zeigen. Die Rückfrage zur Messung war hilfreicher als eine fertige Lösung.']),
    (('Zusammenarbeit','Gruppe','Austausch',''),'Sachlicher Austausch zwischen Teilnehmenden.',[
        'Wir haben unsere Messwerte verglichen. Dabei fiel auf, dass wir verschiedene Bezugspunkte verwendet hatten.',
        'Die andere Gruppe kam zu einem anderen Ergebnis. Erst im Gespräch haben wir den Unterschied im Aufbau gefunden.',
        'Ich habe nur eine Verständnisfrage gestellt. Daraus wurde ein längeres Gespräch über mehrere Lösungswege.']),
    (('Zusammenarbeit','Gruppe','Konflikt',''),'Spannungen oder ungleiche Beteiligung innerhalb einer Gruppe.',[
        'Zwei Personen haben den Aufbau übernommen. Als ich etwas ändern wollte, hieß es, dafür sei keine Zeit mehr.',
        'Wir waren uns beim Vorgehen nicht einig. Am Ende haben wir abgestimmt, aber meine Frage blieb offen.',
        'Die Aufgaben waren verteilt, trotzdem habe ich fast das ganze Protokoll geschrieben. Das möchte ich beim nächsten Mal anders regeln.']),
    (('Verbesserungsvorschlag','','',''),'Konkreter Vorschlag zur Änderung des Angebots.',[
        'Eine kurze Übersicht mit den drei häufigsten Fehlern würde mir helfen. Sie könnte direkt neben dem Versuchsaufbau liegen.',
        'Ich wünsche mir einen zusätzlichen Termin, an dem man einen eigenen Fall mitbringen kann.',
        'Vielleicht könnte die Abgabe in zwei kleine Schritte geteilt werden. Dann gäbe es Rückmeldung, bevor alles fertig ist.']),
    (('Gesamturteil','ambivalent','',''),'Ausdrücklich gemischte Gesamtbewertung ohne eindeutige positive oder negative Bilanz.',[
        'Insgesamt hat es mir etwas gebracht, aber der Aufwand war höher als erwartet. Ich würde es empfehlen, allerdings nicht uneingeschränkt.',
        'Ich bin weder enttäuscht noch richtig zufrieden. Einige Teile waren hilfreich, andere passten für mich nicht.',
        'Ob es sich gelohnt hat? Teilweise schon. Für eine klare Antwort müsste ich erst sehen, was ich später tatsächlich nutze.']),
]

def generate():
    with (ROOT/'Kategoriesystem.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f,delimiter=';')
        writer.writerow(['Kategorie','Unterkategorie','Ausprägung','Facette','Definition','Ankerbeispiel'])
        for levels,definition,texts in CASES:
            writer.writerow([*levels,definition,texts[0]])
    rows=[]
    for ci,(levels,_,texts) in enumerate(CASES):
        for ti,text in enumerate(texts):
            index=len(rows)+1
            rows.append([f'SYN-{index:03d}',f'SYN-PASS-{index:03d}',f'SYN-P{(ci+ti)%6+1:02d}',
                         ' > '.join(x for x in levels if x),text,'eindeutig' if ti==0 else 'kontextsensitiv'])
    # One passage intentionally has two coding rows. It must not be silently deduplicated.
    for code in ('Organisation > Unterstützung','Zusammenarbeit > Gruppe > Austausch'):
        rows.append([f'SYN-{len(rows)+1:03d}','SYN-PASS-037','SYN-P01',code,
                     'In der offenen Sprechstunde haben wir gemeinsam unsere Messwerte verglichen. Die Kursleitung half uns, den unterschiedlichen Aufbau zu erkennen.',
                     'mehrfachcodierte_passage'])
    complex_cases = [
        ('Die Kursunterlagen waren verständlich. Erst als ich die Anleitung an unserer Anlage ausprobierte, merkte ich, dass dort andere Sensoren verbaut sind. Mit dem Verfahren kam ich allein nicht weiter.',
         ['Lernangebot > Materialien','Lernangebot > Praxis > Übertragung > stockt']),
        ('Der neue Abendtermin lässt sich mit meinem Dienst vereinbaren. Gleichzeitig bin ich nach der Schicht so erschöpft, dass mir die Konzentration für den Kurs fehlt. Beides trifft für mich zu.',
         ['Organisation > Zeit > Vereinbarkeit > entlastend','Organisation > Zeit > Vereinbarkeit > belastend']),
        ('Beim Vergleich unserer Protokolle fanden wir unterschiedliche Messpunkte. Danach bestimmte ein Kollege allein, welches Ergebnis abgegeben wird; mein Einwand wurde übergangen.',
         ['Zusammenarbeit > Gruppe > Austausch','Zusammenarbeit > Gruppe > Konflikt']),
        ('Die Simulation startete auch nach dem dritten Versuch nicht. Die Betreuung antwortete schnell und grenzte den Fehler ein. Ich würde mir für solche Fälle zusätzlich eine Anleitung zur Fehlersuche wünschen.',
         ['Organisation > Zugang > Technik','Organisation > Unterstützung','Verbesserungsvorschlag']),
        ('Eine Kollegin sagt, das Material sei nutzlos. Das ist nicht meine Erfahrung: Die beschrifteten Skizzen und die gut lesbare Tabelle haben mir beim Nachschlagen geholfen. Über ihren Arbeitsplatz kann ich nichts sagen.',
         ['Lernangebot > Materialien']),
        ('Zuerst dachte ich, der Kurs hätte wenig gebracht. Später konnte ich bei einer Störung den Messablauf selbst anwenden und den Fehler finden. Dennoch bleibt mein Gesamturteil gemischt, weil viele andere Teile für mich wenig hilfreich waren.',
         ['Lernangebot > Praxis > Übertragung > gelingt','Gesamturteil > ambivalent']),
    ]
    for index,(text,codes) in enumerate(complex_cases,start=38):
        for code in codes:
            rows.append([f'SYN-{len(rows)+1:03d}',f'SYN-PASS-{index:03d}',f'SYN-P{(index-38)%6+1:02d}',code,text,'mehrfachcodierung_grenzfall'])
    with (ROOT/'maxqda_export.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f,delimiter=';')
        writer.writerow(['segment_id','PassageID','Dokumentname','Code','Segment','Testszenario'])
        writer.writerows(rows)
    print(f'{len(rows)} synthetic coding rows, {len({r[1] for r in rows})} passages, 6 fictional persons, {len(CASES)} paths.')

if __name__=='__main__': generate()
