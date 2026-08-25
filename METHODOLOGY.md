# Methodology

## Methodische Einordnung, Qualitätssicherung und verwandte Arbeiten

> **Status dieser Dokumentation:** August 2026.  
> Dieses Dokument beschreibt die methodische Logik der Pipeline und ordnet sie in die aktuelle Literatur zu LLM-gestützter qualitativer Analyse ein. Es ist keine Behauptung, dass die verwendeten Einzelmethoden neu sind oder dass LLM-basierte Auswertung menschliche qualitative Forschung ersetzen kann.

## 1. Ziel und methodischer Anspruch

Dieses Repository stellt eine modulare, lokal ausführbare Pipeline zur Unterstützung der qualitativen Auswertung bereits kodierter Interviewdaten bereit. Die aktuelle Architektur verbindet Clusterung und Zusammenfassungen mit SWOT/Meta-SWOT, fallbezogenen Personenanalysen, Personenvergleichen, Kontrast- und Negativfallanalyse, Zusammenhangs- und Ambivalenzanalyse, einem Evidence-Audit und einer abschließenden Synthese. Ergänzend existieren drei Module zur Prüfung von Codierungen: Code-Verifikation, Blind-Coding und ein deterministisch berechnetes Human–LLM Coding Agreement [1].

Der methodische Anspruch ist bewusst begrenzt:

**Nicht das Vertrauen in eine einzelne LLM-Antwort soll erhöht werden, sondern die Nachvollziehbarkeit, Prüfbarkeit und empirische Rückbindung des gesamten Analyseprozesses.**

Das Projekt beansprucht daher nicht, LLM-basiertes Coding, qualitative Inhaltsanalyse, Intercoder-Vergleiche oder lokale Sprachmodelle erfunden zu haben. Diese Bausteine besitzen etablierte methodische und technische Vorläufer. Der Beitrag des Repositories liegt in ihrer konkreten, modularen Kombination sowie in Schutzmechanismen, die bekannte Schwächen generativer Sprachmodelle in qualitativen Workflows sichtbar und teilweise technisch kontrollierbar machen sollen.

Die Pipeline ist als **Assistenzsystem** zu verstehen. Wissenschaftliche Fragestellung, Kategorienbildung bzw. Auswahl des Kategoriensystems, Interpretation, Reflexion, Bewertung von Grenzfällen und Verantwortung für Schlussfolgerungen verbleiben bei den Forschenden.

---

## 2. Methodischer Hintergrund

### 2.1 Qualitative Inhaltsanalyse und KI als Assistenz

Kuckartz und Rädiker behandeln in der 6. Auflage ihrer *Qualitativen Inhaltsanalyse* generative KI ausdrücklich als mögliches Werkzeug und als analytische Assistenz. Ihr neues Kapitel zur KI diskutiert Anwendungen entlang verschiedener Phasen qualitativer Inhaltsanalyse und betont zugleich, dass die Delegation analytischer Aufgaben an KI methodisch reflektiert werden muss [2, 3].

Für dieses Repository ist diese Unterscheidung zwischen **Werkzeug** und **Assistenz** zentral. Ein LLM kann beispielsweise große Mengen bereits kodierter Segmente strukturieren, alternative Lesarten vorschlagen oder Muster verdichten. Daraus folgt jedoch nicht, dass seine Ausgabe den Status eines methodisch abgesicherten Forschungsbefunds erhält.

Der 2026 erschienene deutschsprachige Band *KI in der qualitativen Forschung* von Kempny, Annac, Yilmaz-Aslan und Brzoska erweitert diese Diskussion über den gesamten Forschungsprozess. Er behandelt unter anderem Herausforderungen des KI-Einsatzes, KI-Werkzeuge, Dokumentation im Forschungsjournal sowie Kodierung und Kategorienbildung mit KI [4]. Damit wird deutlich, dass die methodische Frage inzwischen weniger lautet, **ob** LLMs in qualitativen Workflows vorkommen, sondern unter welchen Bedingungen ihre Nutzung transparent, kontrolliert und verantwortbar gestaltet werden kann.

### 2.2 Kritische Befunde: Mayrings Erfahrungsbericht

Besonders relevant ist Mayrings systematischer Erfahrungsbericht zur qualitativen Inhaltsanalyse mit ChatGPT. In seinen Testläufen mit ChatGPT 3.5 und GPT-4 führten sowohl allgemeine als auch detailliertere Anweisungen lediglich zu groben Annäherungen an seine Musterlösung und zu zahlreichen Fehlern. Mayring berichtet unter anderem Probleme bei der korrekten Umsetzung inhaltsanalytischer Konzepte und beim Erkennen weniger offensichtlicher Textinhalte [5].

Diese Kritik ist für die Architektur des Repositories produktiv: Die Konsequenz besteht **nicht** darin, eine bessere Einmal-Promptformulierung zu suchen und danach von einer „automatischen qualitativen Inhaltsanalyse“ auszugehen. Stattdessen wird versucht, komplexe Analyseaufgaben zu zerlegen, Eingaben und Ausgaben strukturell zu begrenzen, maschinell überprüfbare Teile aus dem LLM herauszunehmen und Ergebnisse auf ihre empirischen Quellen zurückzuführen.

### 2.3 Internationale Forschung zu LLM-Coding

Auch internationale Studien zeigen ein gemischtes Bild. Xiao et al. demonstrierten bereits 2023, dass LLMs bei deduktivem Coding mit einem expertengestützten Codebook faire bis substanzielle Übereinstimmungen mit menschlichen Codierungen erreichen können [6]. QualiGPT erweitert diese Idee auf induktive und deduktive Szenarien und bewertet die Übereinstimmung zwischen menschlichen und LLM-basierten Codierungen mit Inter-Rater-Reliability-Maßen [7].

Neuere Arbeiten bestätigen zugleich, dass Leistungsfähigkeit stark von Aufgabe, Code, Prompting und gewünschter Interpretationstiefe abhängt. Ein serverseitig installiertes Llama-3-Modell erreichte bei der deduktiven Analyse psychosozialer Interviewdaten zwar substanzielle Übereinstimmungen, zeigte aber deutliche Unterschiede zwischen Codes; bei Zusammenfassungen wurden außerdem unerwünschte Elaborationen und Halluzinationen beobachtet. Die Autoren empfehlen deshalb ausdrücklich ein kollaboratives Modell mit menschlicher Prüfung, induktivem Coding und weiterer Interpretation [8].

Eine Studie zu deduktiver qualitativer Inhaltsanalyse in Implementierungsinterviews zeigt ebenfalls, dass LLMs mehr Textstellen codieren können als Menschen und dass Übereinstimmung je nach deskriptivem oder interpretativem Code variiert. Nuancierte Interpretation, Kontextualisierung und die Auflösung mehrdeutiger Klassifikationen blieben von menschlicher Expertise abhängig [9].

Auch die Forschung zu reflexiver thematischer Analyse ist zurückhaltend. Vikan et al. fanden bei einem offline betriebenen LLM nur begrenzte Unterstützung für reflexive thematische Analyse und verweisen auf Probleme wie irreführende Prompts, Übersetzungsfehler und andere Modellfehler [10]. Eine aktuelle Untersuchung kulturell und emotional komplexer Interviews berichtet, dass ChatGPT Oberflächeninhalte gut erfassen kann, kulturelle und emotionale Nuancen jedoch abflacht; Human-in-the-loop-Aufsicht war für Interpretationsbreite und Validität wesentlich [11].

Diese Befunde sprechen gegen die Vorstellung eines universellen „KI-Coders“. Sie sprechen eher für **aufgabenspezifische, überprüfbare Assistenz**.

---

## 3. Aus bekannten Kritikpunkten abgeleitete Designprinzipien

Die Pipeline versucht nicht, die methodischen Probleme von LLMs als „gelöst“ darzustellen. Stattdessen werden konkrete Risiken dort, wo es technisch möglich ist, durch Architekturentscheidungen adressiert.

### 3.1 Kein monolithischer „Analysiere meine Interviews“-Prompt

Ein wesentliches Risiko besteht darin, ein vollständiges Interviewkorpus an ein LLM zu übergeben und unmittelbar eine fertige Interpretation zu erwarten. Dadurch werden Segmentierung, Kategorienanwendung, Abstraktion, Evidenzauswahl und Synthese in einem kaum überprüfbaren Vorgang vermischt.

Die Pipeline zerlegt den Prozess deshalb in getrennte Module mit expliziten Inputs und Outputs [1]. Zwischenprodukte werden als strukturierte JSON-Dateien gespeichert und können unabhängig inspiziert werden. Die Modulreihenfolge und Abhängigkeiten werden über YAML deklariert.

Diese Zerlegung ist auch mit empirischen Befunden vereinbar: In einer Studie zu reflexiver Inhaltsanalyse erzielten auf einzelne Codes zugeschnittene Aufgaben teilweise deutlich bessere Übereinstimmung als die Verarbeitung des gesamten Codebooks in einem einzigen Prompt [12]. Eine weitere Studie zur deduktiven Codierung fand die stärksten Ergebnisse bei einer schrittweisen Aufgabenzerlegung [13].

**Adressiertes Risiko:** Überlastete Prompts, vermischte Analyseschritte, geringe Fehlerlokalisierbarkeit.

**Verbleibende Grenze:** Auch ein modularer LLM-Schritt kann semantisch falsch sein. Modularisierung erhöht Prüfbarkeit, nicht automatisch Validität.

### 3.2 Human Coding und LLM Coding werden getrennt behandelt

Die Pipeline kann von bereits menschlich kodierten Segmenten ausgehen [1]. Das LLM muss daher nicht zwangsläufig die ursprüngliche Codierung ersetzen. Stattdessen kann es nachgelagerte Analyseaufgaben übernehmen oder die vorhandene Codierung in einem separaten Prüfpfad untersuchen.

Diese Trennung folgt einem Human-in-the-loop-Verständnis, wie es auch in aktueller Forschung empfohlen wird [8, 9, 11]. Neuere kollaborative Ansätze gehen noch weiter und lassen Menschen ausdrücklich die konzeptuelle Autorität über Definitionen, Zusammenführungen und Interpretationsrahmen behalten [14].

**Adressiertes Risiko:** Gleichsetzung von LLM-Ausgabe und wissenschaftlicher Codierung.

**Verbleibende Grenze:** Menschliche Codierung ist selbst interpretativ und nicht automatisch ein fehlerfreier „Goldstandard“.

### 3.3 Code-Verifikation ist von Blind-Coding getrennt

`code_verification` prüft einen bereits menschlich vergebenen vollständigen Codepfad gegen Definition und Ankerbeispiel. `blind_coding` erhält dagegen Segment und Codebuch, jedoch nicht den menschlichen Code [1].

Das ist methodisch wichtig: Eine Prüfung, bei der das Modell den erwarteten menschlichen Code bereits kennt, misst etwas anderes als eine unabhängige erneute Klassifikation. Beide Perspektiven werden deshalb getrennt gespeichert.

**Adressiertes Risiko:** Bestätigungsbias bzw. scheinbare Validierung durch Offenlegung des Zielcodes.

**Verbleibende Grenze:** Blind-Coding macht das LLM nicht zu einem unabhängigen menschlichen Rater. Modelltraining, Prompt, Modellversion und Codebook beeinflussen weiterhin die Entscheidung.

### 3.4 Das Codebook begrenzt zulässige Antworten

Beim Blind-Coding sind nur vorhandene vollständige Codepfade sowie definierte Sonderfälle wie `unklar` oder `keine_zuordnung` zulässig. LLM-genannte Codes werden gegen das tatsächlich eingelesene Kategoriensystem validiert; erfundene Alternativcodes werden verworfen bzw. protokolliert [1].

Diese Strategie knüpft an Forschung zum codebook-basierten deduktiven Coding an, in der die explizite Bereitstellung von Definitionen und strukturierten Coding-Regeln zentral ist [6, 9].

**Adressiertes Risiko:** Halluzinierte Kategorien, semantisch plausible, aber im Kategoriensystem nicht existente Labels.

**Verbleibende Grenze:** Ein formal gültiger Code kann inhaltlich trotzdem falsch sein.

### 3.5 Agreement wird deterministisch berechnet

Das Modul `coding_agreement` lässt das LLM **nicht** selbst entscheiden, wie hoch seine Übereinstimmung mit menschlicher Codierung ist. Exakte und hierarchische Übereinstimmung, Verwechslungspaare, Fallstatus und Konfusionsmatrix werden programmatisch aus den gespeicherten Codierungen berechnet; Cohen's Kappa wird nur in methodisch geeigneten single-label-nominalen Situationen explorativ ausgewiesen [1].

Das folgt einem allgemeinen Prinzip klassischer Qualitätssicherung: Wenn ein Ergebnis deterministisch aus Daten berechnet werden kann, sollte es nicht durch ein generatives Modell geschätzt werden. Intercoder-Reliability kann in qualitativer Inhaltsanalyse zur Diagnose problematischer Codes und zur Verbesserung eines Kategoriensystems beitragen [15]. Aktuelle LLM-Studien verwenden entsprechend Kappa, Alpha, Accuracy oder F1 zur externen Bewertung der Modellcodierung [7, 8, 13].

Das Repository bezeichnet diese Kennzahlen bewusst als **Human–LLM Coding Agreement** und nicht pauschal als klassische Interrater-Reliabilität zwischen zwei menschlichen Ratern [1].

**Adressiertes Risiko:** vom LLM erfundene oder inkonsistent berechnete Reliabilitätskennzahlen.

**Verbleibende Grenze:** Hohe Übereinstimmung beweist weder interpretative Validität noch die Richtigkeit des menschlichen Referenzcodes. Agreement ist ein Diagnoseinstrument, kein Wahrheitsmaß.

### 3.6 Interpretation und Originalevidenz werden technisch getrennt

Ein besonders wichtiges Designprinzip ist die Trennung von generierter Interpretation und Originalmaterial. Jedes Segment erhält eine global eindeutige ID. In evidenzgebundenen Analyseschritten soll das Modell auf vorhandene Segment-IDs verweisen. Die IDs werden validiert und der tatsächliche Interviewtext anschließend deterministisch aus `id_to_text.json` zurückgeführt [1].

Vereinfacht:

`LLM-Interpretation -> validierte Segment-ID -> Python-Lookup -> Originaltext`

Damit muss das LLM ein Originalzitat nicht aus seinem eigenen Ausgabekontext reproduzieren.

**Adressiertes Risiko:** erfundene, veränderte oder ungenau rekonstruierte „Originalzitate“ sowie schwer überprüfbare Evidenzbehauptungen.

**Verbleibende Grenze:** Eine tatsächlich existierende Textstelle kann vom LLM falsch interpretiert oder selektiv als Beleg ausgewählt werden. Provenienz ersetzt keine hermeneutische Prüfung.

### 3.7 Zählbare Evidenzmerkmale werden nicht vom LLM erfunden

Der Evidence-Audit berücksichtigt unter anderem die Zahl stützender Personen, Segmente und Analysepfade sowie Gegenbelege, Ambivalenzen und Relativierungen. Zählbare Merkmale werden in Python berechnet und nicht vom LLM frei erzeugt [1].

Das ist eine bewusste Trennung zwischen **Interpretation** und **deterministischer Aggregation**. Der Audit soll zeigen, wie breit ein Befund im vorhandenen Material abgestützt ist, ohne diese Breite mit statistischer Signifikanz gleichzusetzen.

**Adressiertes Risiko:** plausible, aber numerisch falsche Aussagen des LLM über Häufigkeiten oder empirische Abdeckung.

**Verbleibende Grenze:** Häufigkeit bzw. Breite ist kein Ersatz für qualitative Bedeutung. Ein einzelner Negativfall kann theoretisch wichtiger sein als ein häufiges Muster.

### 3.8 Kontrast-, Negativfall- und Ambivalenzanalyse gegen vorschnelle Homogenisierung

LLM-Zusammenfassungen besitzen einen starken Verdichtungscharakter. Gerade dadurch können Minderheitenpositionen, Widersprüche oder fallinterne Spannungen verschwinden. Aktuelle Studien berichten ebenfalls von zu breiten „umbrella terms“, übermäßiger Granularität oder Verlust von Kontext und Nuance [9, 11].

Die Pipeline enthält deshalb eigene Module für Kontrast- und Negativfälle sowie für intrapersonelle Ambivalenzen [1]. Dominante Muster sollen dadurch nicht automatisch als widerspruchsfreie Gesamtaussage des Materials erscheinen.

**Adressiertes Risiko:** Glättung, Mehrheitsbias und Verlust widersprechender Evidenz bei Synthesen.

**Verbleibende Grenze:** Auch die Suche nach Gegenbelegen wird teilweise durch ein LLM durchgeführt und kann relevante Gegenbelege übersehen.

### 3.9 Keine automatische Kausalität oder psychologische Diagnostik

Die Zusammenhangsanalyse darf Beziehungen wie gemeinsames Auftreten, Ergänzung oder Spannungsverhältnis beschreiben, soll daraus aber keine unbelegten Kausalbeziehungen ableiten. Personenanalysen und Typenbildungen werden ausdrücklich nicht als psychologische Diagnosen verstanden [1].

**Adressiertes Risiko:** Überinterpretation sprachlicher Muster und Übergang von deskriptiven Daten zu unbelegten Ursachen-, Wirkungs- oder Persönlichkeitsaussagen.

**Verbleibende Grenze:** Promptregeln können Überinterpretation reduzieren, aber nicht vollständig verhindern; die finale Prüfung bleibt menschliche Aufgabe.

### 3.10 Strukturierte Outputs, Logs und optionale Raw-Audits

Die Pipeline verwendet JSON-Zwischenprodukte, Modul-Logs, ein Workflow-Manifest und optional append-only gespeicherte unveränderte LLM-Antworten für Code-Verifikation und Blind-Coding [1]. Dadurch können nicht nur Endberichte, sondern auch Zwischenschritte untersucht werden.

Diese Ausrichtung passt zu der wachsenden Forderung nach Transparenz und Auditierbarkeit bei LLM-gestützter qualitativer Forschung. Das COREQ+LLM-Projekt nennt Halluzinationen sowie Risiken für Reproduzierbarkeit, Validität und Trustworthiness als zentrale Herausforderungen und verweist auf fehlende Normen für transparente LLM-Nutzung [16]. Auch die neuere Diskussion um „technological reflexivity“ fordert, den Einfluss von Modell, Interface und Mensch–Algorithmus-Interaktion auf die Erkenntnisproduktion selbst zum Gegenstand methodischer Reflexion zu machen [17].

**Adressiertes Risiko:** Black-Box-Analyse und fehlende Rekonstruktion des technischen Analysepfads.

**Verbleibende Grenze:** Ein technischer Audit-Trail dokumentiert, *was* passiert ist; er beweist nicht, dass die interpretative Entscheidung wissenschaftlich angemessen war.

---

## 4. Lokale LLM-Verarbeitung als Datenschutz- und Reproduzierbarkeitsentscheidung

Die Pipeline nutzt lokale Modelle über Ollama [1]. Bei entsprechend lokaler Konfiguration muss Interviewmaterial für die Modellinferenz nicht an einen externen kommerziellen LLM-Dienst übertragen werden.

Dies ist insbesondere für qualitative Interviews relevant, weil selbst pseudonymisierte Texte sensible Kontextinformationen enthalten können. Kuckartz und Rädiker beziehen Datenschutz und ethische Fragen ausdrücklich in ihre Diskussion generativer KI ein [3].

Lokale Verarbeitung ist jedoch **kein Synonym für Datenschutzkonformität**. Forschende müssen weiterhin unter anderem prüfen:

- Rechtsgrundlage und Einwilligung,
- Anonymisierung bzw. Pseudonymisierung,
- Speicherorte und Backups,
- Zugriffsrechte,
- Log- und Debugdateien,
- Veröffentlichung von Beispieldaten,
- Modell- und Softwareherkunft,
- institutionelle Vorgaben und Forschungsethik.

Die Pipeline warnt deshalb insbesondere vor der ungeprüften Weitergabe von Raw-Audit-Dateien, die aus Interviewmaterial abgeleitete Inhalte enthalten können [1].

Lokale Modelle können zusätzlich die technische Reproduzierbarkeit verbessern, weil Modellname und Konfiguration kontrollierbarer dokumentiert werden können. Sie beseitigen Reproduzierbarkeitsprobleme aber nicht: Modellupdates, Samplingparameter, Hardware, Kontextlänge und nichtdeterministische Inferenz können weiterhin zu unterschiedlichen Resultaten führen.

---

## 5. Reproduzierbarkeit, Stabilität und Modellabhängigkeit

LLM-Ausgaben sind nicht deterministisch im gleichen Sinn wie klassische Statistikfunktionen. Deshalb sollte zwischen mindestens drei Ebenen unterschieden werden:

1. **technische Reproduzierbarkeit** – gleiche Daten, gleiche Softwareversion, gleiche Konfiguration;
2. **Output-Stabilität** – ähnliche Ergebnisse über wiederholte LLM-Läufe;
3. **interpretative Robustheit** – ähnliche oder zumindest nachvollziehbar unterschiedliche Befunde über Modelle, Prompts oder Forschende hinweg.

Das Repository adressiert derzeit vor allem die erste Ebene durch YAML-Konfiguration, strukturierte Zwischenprodukte, Logs, Tests und klar definierte Modulabhängigkeiten [1]. Eine systematische Stabilitätsanalyse über mehrere Runs und ein Vergleich verschiedener Ollama-Modelle sind als mögliche Erweiterungen ausgewiesen [1].

Andere aktuelle Werkzeuge gehen bereits explizit in diese Richtung. Das R-Paket `quallmer` bietet beispielsweise Funktionen zur Wiederholung von Codierungen mit unterschiedlichen Modellen und Einstellungen, zur Validierung gegen menschliche Goldstandards und zur Erstellung eines Audit-Trails [18]. Solche Ansätze sind wichtige Prior Art und zugleich ein sinnvoller Referenzpunkt für zukünftige Erweiterungen dieser Pipeline.

Eine methodisch starke Weiterentwicklung wäre daher:

- identische Stichproben mehrfach mit demselben Modell auszuführen,
- mehrere lokale Modelle zu vergleichen,
- Prompt- und Temperatureinstellungen zu dokumentieren,
- Stabilität pro Code statt nur global zu betrachten,
- besonders instabile Segmente gezielt menschlich zu prüfen.

---

## 6. Reflexivität statt bloßer Automatisierung

Eine rein technische Validierung reicht für qualitative Forschung nicht aus. Ibrahim und Voyer argumentieren für **technological reflexivity**: Forschende sollten nicht nur ihre eigene Position, sondern auch Modellbias, Interaktion mit dem System, Promptentscheidungen und den Einfluss digitaler Werkzeuge auf die Erkenntnisproduktion reflektieren [17].

Prahl operationalisiert diese Idee in einer AI-Reflexivity Checklist, die vor der Analyse klären soll, ob eine Aufgabe eher delegiert, assistiert oder menschlich geführt werden sollte. Kriterien sind unter anderem Kontextvariation, Erfahrungs- und Bedeutungstiefe, ethische Exposition und Reversibilität von Outputs [19].

Für die Nutzung dieses Repositories bedeutet das praktisch:

- Nicht jeder Analyseschritt ist gleichermaßen für LLM-Unterstützung geeignet.
- Deskriptive Strukturierung ist methodisch anders zu bewerten als latente Interpretation.
- Emotional, kulturell oder biografisch stark kontextgebundene Passagen benötigen besondere Vorsicht.
- Modelloutput sollte als analytischer Vorschlag behandelt werden, nicht als neutrale Beobachtung.
- Abweichungen zwischen Mensch und LLM sind nicht nur „Fehler“, sondern können Hinweise auf unklare Kategorien, unterschiedliche Lesarten oder blinde Flecken liefern.

Damit wird Human–LLM Agreement nicht ausschließlich als Leistungsranking verstanden. Uneinigkeit kann selbst diagnostisch relevant sein.

---

## 7. Verhältnis zu verwandten Softwareprojekten und Workflows

Das Repository steht in einem wachsenden Ökosystem von Werkzeugen für LLM-gestützte qualitative Analyse.

### QualiGPT

QualiGPT wurde entwickelt, um LLM-basiertes qualitatives Coding zugänglicher und transparenter zu machen. Es unterstützt induktive und deduktive Coding-Szenarien und vergleicht LLM- mit menschlicher Codierung über Reliability-Maße [7]. Gemeinsam ist beiden Ansätzen die Idee, LLM-Coding nicht ungeprüft als Endergebnis zu behandeln. Die vorliegende Pipeline legt ihren Schwerpunkt darüber hinaus auf die Verarbeitung bereits kodierter Interviewsegmente und auf nachgelagerte, miteinander verbundene Analyseebenen.

### quallmer

`quallmer` ist ein R-Werkzeugkasten für codebook-basiertes LLM-Coding. Besonders relevant sind Funktionen für Agreement, Goldstandard-Validierung, Modell-/Setting-Vergleiche und Audit-Trails [18]. Damit überschneidet sich `quallmer` deutlich mit dem Qualitätssicherungsbereich dieses Projekts. Der Schwerpunkt dieses Repositories liegt jedoch stärker auf einer mehrstufigen Interviewanalyse nach der Codierung – einschließlich Fall-, Kontrast-, Ambivalenz-, Beziehungs-, SWOT-/Meta-SWOT- und Evidence-Audit-Schritten.

### Multi-Stage LLM Pipeline mit Expert Validation

Eine 2026 publizierte Proof-of-Concept-Studie verwendete deutschsprachig erhobene Interviews aus Österreich, die für die LLM-Analyse ins Englische übersetzt wurden, und verglich eine mehrstufige LLM-Pipeline mit einer manuellen Baseline. Expert:innen sahen relevante thematische Überschneidungen, kritisierten aber unter anderem Granularität, vage Konzepte und Kontextabhängigkeit; die Outputs wurden als nach menschlicher Revision nutzbar bewertet [20].

Diese Arbeit ist besonders relevante Prior Art für die Idee einer **mehrstufigen** LLM-Pipeline. Das vorliegende Repository unterscheidet sich jedoch in Ziel und Architektur: Es verarbeitet bereits kodierte Segmente, kann lokal mit Ollama arbeiten und implementiert explizite technische Provenienz- und Validierungsschritte wie Segment-ID-Rückführung, Blind-Coding, deterministisches Agreement und Evidence-Audit.

### Weitere lokale bzw. auditierbare Ansätze

Neuere Open-Source-Projekte zeigen, dass lokale Verarbeitung, Goldstandard-Kalibrierung, Blind-Coding und Audit-Trails zunehmend zu eigenständigen Designzielen werden. `Concord` kombiniert beispielsweise AI-codierte Korpora mit Gold-Kalibrierung, Blind-Doppelcodierung, Agreement-Statistik und einem Ledger-basierten Replikationspfad [21]. `interview-analysis` positioniert das LLM ausdrücklich als vorläufigen First-Cycle-Coder und fordert menschliche Validierung der Ergebnisse [22].

Diese Überschneidungen sind **kein Plagiatsindiz**, sondern zeigen eine Konvergenz des Feldes auf ähnliche Qualitätsprobleme: Provenienz, Validierung, Blindheit, Stabilität und menschliche Verantwortlichkeit.

---

## 8. Was an diesem Repository nicht als Neuheitsanspruch verstanden werden sollte

Folgende Bestandteile besitzen klare methodische oder technische Vorläufer und werden hier nicht als originäre Erfindungen beansprucht:

- qualitative Inhaltsanalyse,
- deduktives oder induktives Coding,
- Kategorien- und Codebook-basierte Analyse,
- Intercoder- bzw. Agreement-Maße,
- Cohen's Kappa und Konfusionsmatrizen,
- LLM-basiertes Coding,
- Human–LLM-Vergleiche,
- lokale Open-Source-LLMs und Ollama,
- strukturierte JSON-Ausgaben,
- Fallvergleich und Negativfallanalyse,
- SWOT als analytisches Schema,
- Audit-Trails als Prinzip qualitativer Qualitätssicherung.

Die Eigenständigkeit des Projekts sollte deshalb nicht über einzelne Methoden behauptet werden. Sie liegt – soweit aus der hier berücksichtigten öffentlich zugänglichen Literatur und Software ersichtlich – vor allem in der **konkreten Zusammenstellung und Implementierung** eines YAML-gesteuerten lokalen Workflows für bereits kodierte Interviewdaten sowie in der Kombination von:

- Code-Verifikation,
- Blind-Coding,
- deterministischem Human–LLM Agreement,
- validierten Segment-IDs,
- deterministischer Rückführung von Originaltexten,
- mehrstufigen Fall-, Kontrast-, Ambivalenz- und Zusammenhangsanalysen,
- Evidence-Audit mit programmatisch berechneten Evidenzmerkmalen und
- abschließender Synthese über mehrere Analyseebenen.

Diese Aussage ist bewusst als **Abgrenzung**, nicht als Prioritäts- oder Alleinstellungsbehauptung formuliert. Das Forschungs- und Softwarefeld entwickelt sich schnell; ähnliche Funktionen können unabhängig entstehen oder nachträglich veröffentlicht werden.

---

## 9. Was die Pipeline trotz der Schutzmechanismen nicht leisten kann

### 9.1 Kein automatischer Nachweis interpretativer Richtigkeit

Eine Segment-ID kann korrekt sein, während die Interpretation der Passage falsch ist. Eine Konfusionsmatrix kann korrekt berechnet sein, während das Kategoriensystem theoretisch ungeeignet ist.

### 9.2 Kein Ersatz für Kontextwissen

LLMs können kulturelle, biografische, organisationale oder emotionale Bedeutungen nivellieren [11]. Das ist besonders problematisch, wenn latente Bedeutungen und nicht nur manifeste Inhalte untersucht werden.

### 9.3 Kein neutraler zweiter menschlicher Coder

Human–LLM Agreement ist nicht identisch mit klassischer Intercoder-Reliabilität. Ein Sprachmodell besitzt keine menschliche Sozialisation, Feldkenntnis oder Forschungserfahrung und ist zugleich durch Trainingsdaten und technische Modellarchitektur geprägt.

### 9.4 Keine statistische Repräsentativität

Der Evidence-Audit beschreibt empirische Breite innerhalb des vorhandenen qualitativen Materials. Viele stützende Personen oder Segmente erzeugen keine populationsstatistische Signifikanz.

### 9.5 Keine Garantie gegen Halluzinationen

Schema-Validierung, ID-Prüfung und kontrollierte Kategorien können bestimmte Halluzinationstypen verhindern oder sichtbar machen. Freie Interpretationen können trotzdem falsche Behauptungen enthalten.

### 9.6 Keine vollständige Reproduzierbarkeit allein durch lokale Modelle

Auch lokale Inferenz kann variieren. Für wissenschaftliche Verwendung sollten Modellname, Modellversion bzw. Hash soweit verfügbar, Parameter, Promptversion, Softwarestand und Datenversion dokumentiert werden.

---

## 10. Empfohlene Nutzung in wissenschaftlichen Projekten

Für wissenschaftliche Anwendungen empfiehlt sich ein kontrollierter Workflow:

1. **Forschungsfrage und qualitative Methode vor dem LLM-Einsatz festlegen.**
2. **Kategoriensystem und Codiereinheit explizit dokumentieren.**
3. **Menschliche Codierung bzw. eine unabhängige menschliche Stichprobe erhalten.**
4. **LLM-Aufgaben möglichst eng und nachvollziehbar definieren.**
5. **Blind-Coding verwenden, wenn unabhängige Übereinstimmung untersucht werden soll.**
6. **Agreement programmatisch und pro Kategorie prüfen.**
7. **Uneinigkeiten qualitativ inspizieren, statt nur einen globalen Kennwert zu berichten.**
8. **Originalevidenz über Segment-IDs zurückverfolgen.**
9. **Kontrast- und Negativfälle gezielt prüfen.**
10. **Modelle, Prompts, Parameter, Softwareversionen und Änderungen dokumentieren.**
11. **LLM-generierte Synthesen gegen Primärmaterial und Zwischenergebnisse prüfen.**
12. **Im Methodenabschnitt transparent berichten, welche Aufgaben Mensch, LLM und deterministischer Code jeweils übernommen haben.**

Für besonders sensible, latente oder kulturell kontextgebundene Analysen sollte die menschliche Interpretationsrolle größer sein als bei rein deskriptiven Klassifikationsaufgaben. Das entspricht der aktuellen Forschung, die LLMs eher als Assistenz- oder Augmentationswerkzeug denn als autonomen qualitativen Forscher einordnet [8–11, 14, 19].

---

## 11. Transparenz zur KI-gestützten Entwicklung dieses Repositories

Neben der LLM-Nutzung **innerhalb** der Analysepipeline wurde auch die Software selbst KI-gestützt entwickelt. Das Repository weist ChatGPT und OpenAI Codex transparent als Mitwirkende an Softwarearchitektur, Code-Co-Authoring, Refactoring, Debugging, Testdesign, Promptarchitektur und Dokumentation aus [1].

Diese Offenlegung ist wichtig, weil zwei Ebenen voneinander unterschieden werden müssen:

1. **KI als Gegenstand bzw. Werkzeug der Forschungsmethode**, und
2. **KI als Entwicklungswerkzeug für die Forschungssoftware**.

KI-gestützt erzeugter Code ist nicht allein deshalb wissenschaftlich validiert. Die relevante Frage ist, ob Implementierung, Berechnungen, Datenflüsse und methodische Annahmen geprüft und getestet wurden. Die modulare Architektur und die vorhandenen Tests unterstützen diese Prüfung, ersetzen aber weder Code Review noch fachliche Validierung.

---

## 12. Zusammenfassung der Qualitätssicherungslogik

| Bekannte Herausforderung | Reaktion der Pipeline | Was dadurch nicht bewiesen wird |
|---|---|---|
| LLM ignoriert oder erfindet Kategorien | Validierung gegen externes Kategoriensystem | inhaltliche Richtigkeit der gewählten Kategorie |
| Bestätigungsbias bei Prüfung vorhandener Codes | separates Blind-Coding ohne menschlichen Zielcode | Unabhängigkeit im Sinn eines menschlichen Raters |
| instabile oder erfundene Agreement-Werte | deterministische Python-Berechnung | interpretative Validität |
| halluzinierte/veränderte Zitate | Segment-ID-Validierung + Originaltext-Lookup | korrekte Interpretation des Zitats |
| erfundene Häufigkeiten | deterministische Evidence-Berechnungen | statistische Repräsentativität |
| Verlust von Minderheitenpositionen | Kontrast-/Negativfallanalyse | vollständiges Auffinden aller Gegenfälle |
| Glättung innerer Widersprüche | Ambivalenzanalyse | vollständige hermeneutische Erfassung |
| unbelegte Kausalität | explizite Beschränkung der Zusammenhangsanalyse | Ausschluss jeder Überinterpretation |
| Black-Box-Workflow | JSON-Zwischenprodukte, Logs, Manifest, optional Raw-Audit | methodische Angemessenheit jedes Schritts |
| Datenschutzrisiko externer APIs | lokale Ollama-Inferenz möglich | automatische DSGVO-/Ethikkonformität |
| Modellabhängigkeit | dokumentierbare lokale Modelle und Konfiguration | vollständige Output-Reproduzierbarkeit |

---

## 13. Fazit

Der aktuelle Forschungsstand rechtfertigt weder die pauschale Behauptung, LLMs könnten qualitative Interviewanalyse zuverlässig automatisieren, noch die Annahme, sie seien für qualitative Forschung grundsätzlich ungeeignet. Empirische Studien zeigen brauchbare Ergebnisse insbesondere bei klar begrenzten Coding-Aufgaben, gleichzeitig aber erhebliche Abhängigkeit von Codebook, Prompt, Modell, Kontext und Interpretationstiefe [6–13, 20].

Die Architektur dieses Repositories folgt deshalb einem vorsichtigen Grundsatz:

> **Generative Interpretation dort einsetzen, wo sie analytischen Mehrwert bieten kann; deterministische Berechnung und Validierung dort einsetzen, wo Ergebnisse technisch überprüfbar sind; und die wissenschaftliche Interpretations- und Entscheidungsverantwortung beim Menschen belassen.**

Die Schutzmechanismen sollen LLM-Fehler nicht unsichtbar machen, sondern möglichst früh lokalisieren, empirische Rückverfolgung ermöglichen und die Grenzen automatisierter Interpretation offenlegen.

---

## Literatur und verwandte Ressourcen

**[1]** Brändle, M. (2026). *Qualitative Analyse-Pipeline mit Ollama*. GitHub Repository.  
https://github.com/braendma/Qualitative-Analyse-mit-Ollama

**[2]** Kuckartz, U., & Rädiker, S. (2024). *Qualitative Inhaltsanalyse. Methoden, Praxis, Umsetzung mit Software und künstlicher Intelligenz* (6. Aufl.). Beltz Juventa. ISBN 978-3-7799-7912-8.

**[3]** Kuckartz, U., & Rädiker, S. (2024). Kapitel 10: Unterstützung durch künstliche Intelligenz. Leseprobe zur 6. Auflage.  
https://qualitativeinhaltsanalyse.de/documents/Kuckartz_Raediker_2024_Qualitative_Inhaltsanalyse_K10_Leseprobe.pdf

**[4]** Kempny, C., Annac, K., Yilmaz-Aslan, Y., & Brzoska, P. (2026). *KI in der qualitativen Forschung: Von der Studienplanung bis zur Datenauswertung*. Springer. https://doi.org/10.1007/978-3-662-73089-8

**[5]** Mayring, P. (2025). Qualitative Inhaltsanalyse mit ChatGPT: Fallstricke, grobe Annäherungen und grobe Fehler. Ein Erfahrungsbericht. *Forum Qualitative Sozialforschung / Forum: Qualitative Social Research, 26*(1), Art. 4. https://doi.org/10.17169/fqs-26.1.4252

**[6]** Xiao, Z., Yuan, X., Liao, Q. V., Abdelghani, R., & Oudeyer, P.-Y. (2023). *Supporting Qualitative Analysis with Large Language Models: Combining Codebook with GPT-3 for Deductive Coding*. arXiv:2304.10548. https://arxiv.org/abs/2304.10548

**[7]** Zhang, H., Wu, C., Xie, J., Rubino, F., Graver, S., Kim, C. M., Carroll, J. M., & Cai, J. (2024). *When Qualitative Research Meets Large Language Model: Exploring the Potential of QualiGPT as a Tool for Qualitative Coding*. arXiv:2407.14925. https://arxiv.org/abs/2407.14925

**[8]** *Deductively coding psychosocial autopsy interview data using a few-shot learning large language model*. (2025). *Frontiers in Public Health*. https://doi.org/10.3389/fpubh.2025.1512537

**[9]** *Large language models for deductive qualitative content analysis in dementia-focused embedded pragmatic clinical trials: A comparative methodological study*. (2026). *Implementation Science Communications*. https://doi.org/10.1186/s43058-026-00953-8

**[10]** Vikan, M., Aryan, R., Kannelønning, M. S., Riegler, M. A., & Danielsen, S. O. (2026). Reflecting on LLM Support in Reflexive Thematic Analysis: An Exploratory Study. *Qualitative Health Research, 36*(2–3), 191–205. https://doi.org/10.1177/10497323251365211

**[11]** *Using ChatGPT for thematic analysis of qualitative interviews in cultural research: a methodological investigation*. (2026). *Asian Journal of Psychiatry, 122*, 105071. https://doi.org/10.1016/j.ajp.2026.105071

**[12]** *Scaling hermeneutics: a guide to qualitative coding with LLMs for reflexive content analysis*. (2025). *EPJ Data Science*. https://doi.org/10.1140/epjds/s13688-025-00548-8

**[13]** Hila, A., & Hauser, E. (2025). *Assessing the Reliability of Large Language Models for Deductive Qualitative Coding: A Comparative Study of ChatGPT Interventions*. arXiv:2507.14384. https://arxiv.org/abs/2507.14384

**[14]** Liu, A., Sun, M., Esbenshade, L., Xiao, M., Tian, V., Zhang, Z., & He, K. (2026). *Human-LLM Collaborative Inductive Coding for Conceptualizing K-12 Educator AI Use*. arXiv:2607.28889. https://arxiv.org/abs/2607.28889

**[15]** Burla, L., Knierim, B., Barth, J., Liewald, K., Duetz, M., & Abel, T. (2008). From text to codings: intercoder reliability assessment in qualitative content analysis. *Nursing Research, 57*(2), 113–117. https://pubmed.ncbi.nlm.nih.gov/18347483/

**[16]** *Extension of the Consolidated Criteria for Reporting Qualitative Research Guideline to Large Language Models (COREQ+LLM): Protocol for a Multiphase Study*. (2025). https://pmc.ncbi.nlm.nih.gov/articles/PMC12508663/

**[17]** Ibrahim, E. I., & Voyer, A. (2026). Qualitative research with LLM chatbots: Technological reflexivity for interpretative technology. *Qualitative Research*. https://doi.org/10.1177/14687941251390794

**[18]** `quallmer`: Qualitative analysis with large language models. GitHub Repository.  
https://github.com/quallmer/quallmer

**[19]** Prahl, A. (2026). The AI-Reflexivity Checklist (ARC): A Pre-Analysis Pause for LLM-Assisted Coding. *Qualitative Health Research*. https://doi.org/10.1177/10497323251401503

**[20]** *Multi-Stage LLM Pipeline to Support Qualitative Content Analysis – A Proof of Concept Experiment with Expert Validation*. (2026). https://doi.org/10.3233/SHTI260065

**[21]** `concord`: Instrument-grade qualitative text analysis. GitHub Repository.  
https://github.com/emollick/concord

**[22]** `interview-analysis`: CLI tool to support non-interpretive interview coding. GitHub Repository.  
https://github.com/DennisSchulmeister/interview-analysis

### Ergänzende aktuelle Literatur

Dörfel, L., & Ammoneit, R. (2026). Evaluation of Inductive Coding with LLMs. *Education Sciences, 16*(8), 1314. https://doi.org/10.3390/educsci16081314

Misra, R., Dahal, R., Kirk, B., Khan, R., Dogan, G., Chataut, R., & Gyawali, P. (2026). Large Language Models in Qualitative Analysis: Comparing Traditional and Researcher-Interpreted Approaches. *International Journal of Qualitative Methods*. https://doi.org/10.1177/16094069261426100

---

## Zitier- und Aktualisierungshinweis

Diese Datei dokumentiert den methodischen Stand des Projekts und die zum angegebenen Zeitpunkt identifizierte verwandte Literatur. Da sich Forschung und Open-Source-Software zu LLM-gestützter qualitativer Analyse sehr schnell entwickeln, sollte die Related-Work-Sektion vor einer wissenschaftlichen Publikation erneut systematisch recherchiert und bibliografisch geprüft werden.