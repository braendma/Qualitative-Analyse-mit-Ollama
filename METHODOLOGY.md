# Methodology

## Methodische Einordnung, Qualitätssicherung und verwandte Arbeiten

> **Stand der Dokumentation:** August 2026.  
> Die vorliegende Dokumentation beschreibt die methodische Logik der Pipeline und ordnet diese in die Forschung zur LLM-gestützten qualitativen Analyse ein. Die Darstellung begründet keinen Neuheitsanspruch für einzelne Methoden und setzt LLM-basierte Auswertung nicht mit menschlicher qualitativer Forschung gleich.

## 1. Ziel und methodischer Anspruch

Das Repository stellt eine modulare, lokal ausführbare Pipeline zur Unterstützung der qualitativen Auswertung bereits kodierter Interviewdaten bereit. Die Architektur verbindet Clusterung und Zusammenfassungen mit SWOT- und Meta-SWOT-Analysen, fallbezogenen Personenanalysen, Personenvergleichen, Kontrast- und Negativfallanalysen, Zusammenhangs- und Ambivalenzanalysen, einem Evidence-Audit sowie einer abschließenden Synthese. Ergänzend werden mit Code-Verifikation, Blind-Coding und einem deterministisch berechneten Human–LLM Coding Agreement drei Verfahren zur Prüfung vorhandener Codierungen bereitgestellt [1].

Der methodische Anspruch besteht dabei nicht darin, das Vertrauen in einzelne LLM-Ausgaben zu erhöhen. Im Vordergrund stehen vielmehr die Nachvollziehbarkeit, Prüfbarkeit und empirische Rückbindung des Analyseprozesses. Das Projekt beansprucht dementsprechend weder LLM-basiertes Coding noch qualitative Inhaltsanalyse, Intercoder-Vergleiche oder lokale Sprachmodelle als eigenständige methodische Neuerungen. Für diese Bestandteile liegen etablierte methodische und technische Vorläufer vor [2–7].

Die Eigenständigkeit des Ansatzes ergibt sich aus der konkreten Zusammenführung dieser Bestandteile in einer modularen Pipeline sowie aus der Implementierung von Schutzmechanismen, mit denen bekannte Schwächen generativer Sprachmodelle sichtbar und teilweise technisch kontrollierbar werden. Die Pipeline wird daher als Assistenzsystem verstanden. Forschungsfrage, Auswahl oder Entwicklung des Kategoriensystems, Interpretation, Reflexion, Bewertung von Grenzfällen sowie die Verantwortung für die Schlussfolgerungen verbleiben bei den Forschenden.

---

## 2. Methodischer Hintergrund

### 2.1 Qualitative Inhaltsanalyse und KI als Assistenz

Kuckartz und Rädiker behandeln generative KI in der sechsten Auflage ihrer *Qualitativen Inhaltsanalyse* ausdrücklich als mögliches Werkzeug und als analytische Assistenz. Die Anwendungen werden entlang verschiedener Phasen qualitativer Inhaltsanalyse diskutiert, wobei zugleich die methodische Reflexion der Delegation analytischer Aufgaben an KI hervorgehoben wird [2]. Diese Unterscheidung zwischen Werkzeug und Assistenz bildet einen zentralen Bezugspunkt der vorliegenden Pipeline.

Ein Large Language Model (LLM) kann große Mengen bereits kodierter Segmente strukturieren, alternative Lesarten vorschlagen oder vorhandene Muster verdichten. Aus dieser technischen Leistungsfähigkeit ergibt sich jedoch nicht, dass die erzeugte Ausgabe den Status eines methodisch abgesicherten Forschungsbefunds erhält. Der deutschsprachige Band *KI in der qualitativen Forschung* erweitert diese Perspektive auf den gesamten Forschungsprozess und behandelt neben den verfügbaren Werkzeugen insbesondere Fragen der Dokumentation, Kategorienbildung und methodischen Kontrolle [4]. Damit verschiebt sich die Fragestellung von der grundsätzlichen Nutzung generativer KI hin zu den Bedingungen, unter denen deren Einsatz transparent, kontrolliert und wissenschaftlich verantwortbar erfolgen kann.

### 2.2 Kritik an automatisierter qualitativer Inhaltsanalyse

Für diese Einordnung ist Mayrings Erfahrungsbericht zur qualitativen Inhaltsanalyse mit ChatGPT von besonderer Bedeutung. Die untersuchten Modellversionen erreichten trotz unterschiedlich detaillierter Instruktionen lediglich grobe Annäherungen an die zugrunde gelegte Musterlösung. Festgestellt wurden unter anderem Fehler bei der Umsetzung inhaltsanalytischer Konzepte sowie beim Erkennen weniger offensichtlicher Textinhalte [5].

Aus diesen Befunden wird für die vorliegende Pipeline nicht die Annahme abgeleitet, dass eine weiter optimierte Einzelanweisung die methodischen Probleme automatisierter Inhaltsanalyse behebt. Stattdessen werden komplexe Analyseaufgaben in getrennte Schritte zerlegt, Ein- und Ausgaben strukturell begrenzt, deterministisch überprüfbare Operationen aus dem LLM herausgelöst sowie generierte Befunde auf das empirische Ausgangsmaterial zurückgeführt. Die Kritik wird damit unmittelbar in Architekturentscheidungen übersetzt.

### 2.3 Empirische Befunde zum LLM-basierten Coding

Internationale Studien weisen für LLM-basiertes Coding ein differenziertes Bild auf. Xiao et al. zeigen, dass LLMs bei deduktivem Coding auf Basis eines expertengestützten Codebooks relevante Übereinstimmungen mit menschlichen Codierungen erreichen können [6]. QualiGPT überträgt diese Grundidee auf induktive und deduktive Szenarien und untersucht die Übereinstimmung zwischen menschlichen und LLM-basierten Codierungen mit Reliabilitätsmaßen [7].

Die Leistungsfähigkeit hängt jedoch deutlich von Aufgabe, Code, Promptgestaltung und Interpretationstiefe ab. Für ein lokal bzw. serverseitig installiertes Llama-3-Modell wurden bei der deduktiven Analyse psychosozialer Interviewdaten substanzielle Übereinstimmungen festgestellt, gleichzeitig jedoch erhebliche Unterschiede zwischen einzelnen Codes sowie unerwünschte Elaborationen und Halluzinationen in Zusammenfassungen berichtet [8]. Vergleichbare Einschränkungen zeigen sich bei Implementierungsinterviews: In der Studie identifizierten LLMs mehr Textstellen als die menschliche Codierung, wobei dies nicht automatisch eine höhere Qualität bedeutete und zusätzliche menschliche Prüfung erforderlich blieb [9].

Auch für reflexive thematische Analyse wird die Unterstützungsleistung zurückhaltend beurteilt. Vikan et al. berichten bei einem offline betriebenen LLM unter anderem Probleme durch irreführende Prompts, Übersetzungsfehler und weitere Modellfehler [10]. Bei kulturell und emotional komplexen Interviews zeigt sich außerdem, dass Oberflächeninhalte vergleichsweise gut erfasst werden können, während kulturelle und emotionale Nuancen teilweise nivelliert werden. Human-in-the-loop-Verfahren bleiben deshalb für Interpretationsbreite und Validität relevant [11].

Aus diesen Befunden ergibt sich keine hinreichende Grundlage für die Annahme eines universell einsetzbaren KI-Coders. Sie stützen vielmehr eine aufgabenspezifische Verwendung, bei der LLM-Ausgaben überprüfbar bleiben und mit menschlicher Interpretation verbunden werden.

---

## 3. Aus der bisherigen Kritik abgeleitete Designprinzipien

Die methodischen Probleme von LLMs werden durch die Pipeline nicht als gelöst vorausgesetzt. Soweit Risiken technisch adressierbar sind, werden vielmehr zusätzliche Kontrollschritte eingeführt. Die folgenden Abschnitte stellen jeweils die zugrunde liegende Problemlage, die implementierte Gegenmaßnahme sowie die verbleibende Grenze dar.

### 3.1 Zerlegung komplexer Analyseaufgaben

Die Übergabe eines vollständigen Interviewkorpus mit der Aufforderung, unmittelbar eine umfassende qualitative Interpretation zu erzeugen, verbindet Segmentierung, Kategorienanwendung, Abstraktion, Evidenzauswahl und Synthese in einem nur eingeschränkt überprüfbaren Verarbeitungsschritt. Die Pipeline zerlegt diese Aufgaben deshalb in getrennte Module mit expliziten Ein- und Ausgaben [1]. Strukturierte JSON-Zwischenprodukte ermöglichen die unabhängige Prüfung einzelner Verarbeitungsschritte, während Reihenfolge und Abhängigkeiten der Module über YAML deklariert werden.

Diese Zerlegung entspricht Befunden, nach denen auf einzelne Codes zugeschnittene Aufgaben teilweise höhere Übereinstimmungen erreichen als die gleichzeitige Verarbeitung eines vollständigen Codebooks [12]. Auch für deduktive Codierung wurden Vorteile schrittweise zerlegter Aufgaben berichtet [13]. Diese Studien stützen die Vorteile einer Aufgabenzerlegung, arbeiten jedoch mit codeweise zugeschnittenen oder eigens optimierten Interventionen. Sie beschreiben daher nicht unmittelbar die standardisierte Promptlogik des vorliegenden Workflows. Aus der Modularisierung ergibt sich eine höhere Prüfbarkeit und Fehlerlokalisierbarkeit. Eine semantisch korrekte Interpretation wird dadurch jedoch nicht gewährleistet.

### 3.2 Trennung menschlicher und LLM-basierter Codierung

Die Pipeline kann von bereits menschlich kodierten Segmenten ausgehen [1]. Das LLM ersetzt die ursprüngliche Codierung daher nicht zwangsläufig, sondern kann nachgelagerte Analyseaufgaben übernehmen oder die vorhandene Codierung in einem separaten Prüfpfad untersuchen. Diese Trennung entspricht Human-in-the-loop-Ansätzen, in denen die konzeptuelle Verantwortung für Definitionen, Zusammenführungen und Interpretationsrahmen bei den Forschenden verbleibt [8, 9, 11, 14].

Damit wird die Gleichsetzung einer generierten Klassifikation mit einer wissenschaftlich verantworteten Codierung vermieden. Gleichzeitig ist zu berücksichtigen, dass auch menschliche Codierungen interpretativ sind und nicht ohne Weiteres als fehlerfreier Goldstandard verstanden werden können.

### 3.3 Trennung von Code-Verifikation und Blind-Coding

`code_verification` prüft einen bereits menschlich vergebenen vollständigen Codepfad anhand von Definition und Ankerbeispiel. `blind_coding` erhält demgegenüber Segment und Codebuch, jedoch nicht den menschlich vergebenen Zielcode [1]. Beide Verfahren beantworten damit unterschiedliche Fragen und werden getrennt gespeichert.

Eine Verifikation mit bekanntem Zielcode kann Hinweise auf die Plausibilität einer bestehenden Zuordnung liefern, ist jedoch gegenüber Bestätigungstendenzen anfällig. Blind-Coding ermöglicht eine unabhängigere erneute Klassifikation, ohne das LLM dadurch mit einem unabhängigen menschlichen Rater gleichzusetzen. Modelltraining, Promptgestaltung, Modellversion und Codebook beeinflussen die Entscheidung weiterhin.

### 3.4 Begrenzung der zulässigen Codes

Beim Blind-Coding sind ausschließlich vorhandene vollständige Codepfade sowie definierte Sonderfälle wie `unklar` oder `keine_zuordnung` zulässig. Vom LLM erzeugte Codes werden gegen das eingelesene Kategoriensystem validiert; nicht vorhandene Alternativcodes werden verworfen bzw. protokolliert [1]. Die Pipeline verwendet je Modul standardisierte, in der YAML-Konfiguration hinterlegte Promptvorlagen. Bei Modellvergleichen bleiben diese Vorlagen unverändert; befüllt werden lediglich die vorgesehenen Platzhalter für Projektkontext, Segmentmaterial, Kategorien und Definitionen sowie analytische Zwischenprodukte [1]. Das Kategoriensystem bildet damit einen externen Analyseinput und nicht die Grundlage jeweils neu formulierter Prompts.

Durch diese Begrenzung lassen sich halluzinierte Kategorien technisch erkennen. Daraus folgt jedoch nicht, dass ein formal gültiger Code inhaltlich zutreffend ist. Die Schema-Validierung kontrolliert die Zulässigkeit der Ausgabe, nicht deren interpretative Richtigkeit.

### 3.5 Deterministische Berechnung des Human–LLM Agreements

Das Modul `coding_agreement` überlässt die Ermittlung der Übereinstimmung nicht dem LLM. Exakte und hierarchische Übereinstimmungen, Verwechslungspaare, Fallstatus und Konfusionsmatrix werden programmatisch aus den gespeicherten Codierungen berechnet. Cohen's Kappa wird nur in methodisch geeigneten single-label-nominalen Konstellationen explorativ ausgewiesen [1].

Die Vorgehensweise folgt dem Grundsatz, deterministisch berechenbare Ergebnisse nicht durch ein generatives Modell schätzen zu lassen. Intercoder-Reliability kann in qualitativer Inhaltsanalyse zur Diagnose problematischer Codes und zur Weiterentwicklung eines Kategoriensystems beitragen [15]. Entsprechend werden auch in aktuellen LLM-Studien Kappa, Alpha, Accuracy oder F1 zur externen Bewertung der Modellcodierung eingesetzt [7, 8, 13].

Die Kennzahlen werden im Repository bewusst als Human–LLM Coding Agreement bezeichnet [1]. Eine hohe Übereinstimmung belegt weder interpretative Validität noch die Richtigkeit des menschlichen Referenzcodes. Agreement wird daher als diagnostische Kennzahl und nicht als Wahrheitsmaß verwendet.

### 3.6 Trennung von Interpretation und Originalevidenz

Jedes Segment erhält eine global eindeutige ID. In evidenzgebundenen Analyseschritten verweist das Modell auf vorhandene Segment-IDs, die anschließend validiert werden. Der tatsächliche Interviewtext wird deterministisch aus `id_to_text.json` zurückgeführt [1]. Der Verarbeitungsweg lässt sich vereinfacht wie folgt darstellen:

`LLM-Interpretation → validierte Segment-ID → deterministische Rückführung → Originaltext`

Das Originalzitat muss damit nicht aus einer generierten Modellantwort rekonstruiert werden. Erfundenen oder veränderten Zitaten sowie nicht überprüfbaren Evidenzbehauptungen wird dadurch technisch entgegengewirkt. Eine vorhandene Textstelle kann jedoch weiterhin falsch interpretiert oder selektiv als Beleg ausgewählt werden. Die technische Provenienz ersetzt dementsprechend keine inhaltliche Prüfung.

### 3.7 Deterministische Ermittlung zählbarer Evidenzmerkmale

Der Evidence-Audit berücksichtigt unter anderem die Anzahl stützender Personen, Segmente und Analysepfade sowie Gegenbelege, Ambivalenzen und Relativierungen. Zählbare Merkmale werden programmatisch ermittelt und nicht durch das LLM frei erzeugt [1]. Damit werden Interpretation und deterministische Aggregation voneinander getrennt.

Der Audit beschreibt, wie breit ein Befund innerhalb des vorliegenden Materials abgestützt ist. Diese empirische Breite ist nicht mit statistischer Signifikanz oder Repräsentativität gleichzusetzen. Ebenso kann ein einzelner Negativfall für die qualitative Interpretation theoretisch bedeutsamer sein als ein häufig auftretendes Muster.

### 3.8 Kontrast-, Negativfall- und Ambivalenzanalyse

Generative Zusammenfassungen verdichten umfangreiches Material, wodurch Minderheitenpositionen, Widersprüche oder fallinterne Spannungen verloren gehen können. Aktuelle Studien berichten in diesem Zusammenhang von zu breiten Oberbegriffen, übermäßiger Granularität sowie einem Verlust von Kontext und Nuance [9, 11].

Die Pipeline enthält deshalb eigene Module für Kontrast- und Negativfälle sowie für intrapersonelle Ambivalenzen [1]. Dominante Muster werden dadurch systematisch mit widersprechender oder relativierender Evidenz konfrontiert. Diese Gegenmaßnahme reduziert das Risiko einer vorschnellen Homogenisierung, gewährleistet jedoch nicht, dass sämtliche relevanten Gegenbeispiele durch das LLM erkannt werden.

### 3.9 Begrenzung kausaler und personenbezogener Interpretationen

Die Zusammenhangsanalyse kann gemeinsames Auftreten, Ergänzungen oder Spannungsverhältnisse beschreiben, soll daraus jedoch keine unbelegten Kausalbeziehungen ableiten. Personenanalysen und Typenbildungen werden ebenso nicht als psychologische Diagnosen verstanden [1]. Dadurch wird der Übergang von deskriptiven Interviewdaten zu unbelegten Ursachen-, Wirkungs- oder Persönlichkeitsaussagen begrenzt.

Promptbasierte Regeln können entsprechende Überinterpretationen reduzieren, jedoch nicht vollständig ausschließen. Die abschließende Bewertung bleibt deshalb eine Aufgabe der Forschenden.

### 3.10 Strukturierte Zwischenprodukte und Auditierbarkeit

Die Pipeline verwendet JSON-Zwischenprodukte, Modul-Logs, ein Workflow-Manifest sowie optional append-only gespeicherte unveränderte LLM-Antworten für Code-Verifikation und Blind-Coding [1]. Neben den Endberichten können damit auch die vorgelagerten Verarbeitungsschritte untersucht werden.

Diese Ausrichtung entspricht der zunehmenden Forderung nach Transparenz und Auditierbarkeit LLM-gestützter qualitativer Forschung. Das als Studienprotokoll veröffentlichte und noch in Entwicklung befindliche COREQ+LLM-Projekt nennt Halluzinationen sowie Risiken für Reproduzierbarkeit, Validität und Trustworthiness als zentrale Herausforderungen [16]. Eine inzwischen veröffentlichte Scoping-Review von 75 Studien zeigt zudem erhebliche Lücken bei der Dokumentation von Modellversionen, Bereitstellungsformen, Parametern, Prompts und Validierungsverfahren [3]. Die Diskussion um *technological reflexivity* erweitert diese Perspektive, indem der Einfluss von Modell, Interface und Mensch–Algorithmus-Interaktion auf die Erkenntnisproduktion selbst zum Gegenstand der methodischen Reflexion wird [17].

Ein technischer Audit-Trail ermöglicht die Rekonstruktion des Analysewegs. Die methodische Angemessenheit einer Interpretation wird dadurch nicht automatisch nachgewiesen.

---

## 4. Lokale LLM-Verarbeitung, Datenschutz und Reproduzierbarkeit

Die Pipeline nutzt lokale Modelle über Ollama [1]. Bei vollständig lokaler Konfiguration muss das Interviewmaterial für die Modellinferenz nicht an einen externen kommerziellen LLM-Dienst übertragen werden. Für qualitative Interviews ist diese Eigenschaft insbesondere deshalb relevant, weil auch pseudonymisierte Texte sensible Kontextinformationen enthalten können. Datenschutz und ethische Fragen werden dementsprechend auch in der aktuellen methodischen Literatur als Bestandteil des Einsatzes generativer KI behandelt [2, 4].

Lokale Verarbeitung ist jedoch nicht mit Datenschutzkonformität gleichzusetzen. Rechtsgrundlage und Einwilligung, Anonymisierung bzw. Pseudonymisierung, Speicherorte und Backups, Zugriffsrechte, Log- und Debugdateien, die Veröffentlichung von Beispieldaten sowie institutionelle Vorgaben und Forschungsethik sind unabhängig vom Inferenzort zu prüfen. Dies gilt insbesondere für Raw-Audit-Dateien, die aus Interviewmaterial abgeleitete Inhalte enthalten können [1].

Die lokale Ausführung kann zugleich die technische Reproduzierbarkeit unterstützen, da Modell und Konfiguration kontrollierbarer dokumentiert werden können. Modellupdates, Samplingparameter, Hardware, Kontextlänge und nichtdeterministische Inferenz können dennoch zu unterschiedlichen Ergebnissen führen. Aus lokaler Verarbeitung folgt daher weder vollständige Reproduzierbarkeit noch methodische Validität.

---

## 5. Reproduzierbarkeit, Stabilität und Modellabhängigkeit

Für LLM-basierte Analysen sind technische Reproduzierbarkeit, Output-Stabilität und interpretative Robustheit voneinander zu unterscheiden. Technische Reproduzierbarkeit bezieht sich auf identische Daten, Softwarestände und Konfigurationen. Output-Stabilität beschreibt die Ähnlichkeit wiederholter LLM-Läufe, während interpretative Robustheit die Vergleichbarkeit von Befunden über Modelle, Prompts oder Forschende hinweg betrifft.

Das Repository adressiert derzeit vor allem die technische Ebene durch YAML-Konfiguration, strukturierte Zwischenprodukte, Logs, Tests und definierte Modulabhängigkeiten [1]. Eine systematische Stabilitätsanalyse über mehrere Läufe sowie ein Vergleich verschiedener Ollama-Modelle stellen weiterführende Entwicklungsschritte dar. `quallmer` bietet für vergleichbare Fragestellungen bereits Funktionen zur Wiederholung von Codierungen mit unterschiedlichen Modellen und Einstellungen, zur Validierung gegen menschliche Goldstandards sowie zur Erstellung eines Audit-Trails [18].

Auf dieser Basis erscheint für zukünftige Untersuchungen insbesondere die wiederholte Analyse identischer Stichproben mit demselben Modell, der Vergleich mehrerer lokaler Modelle sowie die Dokumentation von Prompt- und Temperatureinstellungen angezeigt. Stabilität sollte dabei nicht ausschließlich global, sondern auch auf Ebene einzelner Codes und Segmente betrachtet werden. Instabile Fälle können anschließend gezielt einer menschlichen Prüfung zugeführt werden.

---

## 6. Reflexivität als Bestandteil der Analyse

Eine technische Validierung bildet nur einen Teil der Qualitätssicherung qualitativer Forschung. Ibrahim und Voyer fassen unter *technological reflexivity* die Anforderung, neben der eigenen Position der Forschenden auch Modellbias, Interaktion mit dem System, Promptentscheidungen und den Einfluss digitaler Werkzeuge auf die Erkenntnisproduktion zu reflektieren [17]. Prahl konkretisiert diese Perspektive mit einer AI-Reflexivity Checklist, anhand derer vor der Analyse geprüft werden kann, ob eine Aufgabe delegiert, assistiert oder primär menschlich bearbeitet werden sollte [19].

Für die Pipeline folgt daraus, dass Analyseschritte nicht als methodisch gleichwertig behandelt werden. Deskriptive Strukturierung unterscheidet sich von latenter Interpretation; emotional, kulturell oder biografisch stark kontextgebundene Passagen erfordern eine intensivere menschliche Prüfung. Modelloutput wird dementsprechend als analytischer Vorschlag und nicht als neutrale Beobachtung behandelt.

Abweichungen zwischen menschlicher und LLM-basierter Codierung sind dabei nicht ausschließlich als Modellfehler zu interpretieren. Sie können ebenso auf unklare Kategorien, unterschiedliche Lesarten oder problematische Grenzfälle hinweisen. Human–LLM Agreement besitzt damit neben der quantitativen Beschreibung der Übereinstimmung eine diagnostische Funktion für die weitere qualitative Prüfung.

---

## 7. Verhältnis zu verwandten Arbeiten

Die Pipeline steht in einem wachsenden Forschungs- und Softwarefeld zur LLM-gestützten qualitativen Analyse. Die folgenden Arbeiten weisen in Teilbereichen deutliche Überschneidungen auf und sind deshalb für die Einordnung des Projekts besonders relevant.

### 7.1 QualiGPT

QualiGPT unterstützt induktive und deduktive Coding-Szenarien und vergleicht LLM-basierte mit menschlichen Codierungen anhand von Reliabilitätsmaßen [7]. Mit dem vorliegenden Repository besteht damit eine Überschneidung hinsichtlich der kontrollierten Prüfung LLM-basierter Codierung. Die Pipeline legt darüber hinaus einen Schwerpunkt auf die Verarbeitung bereits kodierter Interviewsegmente sowie auf miteinander verbundene nachgelagerte Analyseebenen.

### 7.2 quallmer

`quallmer` stellt einen R-Werkzeugkasten für codebook-basiertes LLM-Coding bereit. Funktionen für Agreement, Goldstandard-Validierung, Modell- und Einstellungsvergleiche sowie Audit-Trails überschneiden sich unmittelbar mit dem Qualitätssicherungsbereich dieses Projekts [18]. Die vorliegende Pipeline erweitert diesen Schwerpunkt um eine mehrstufige Analyse nach der Codierung, die Fall-, Kontrast-, Ambivalenz-, Zusammenhangs-, SWOT-, Meta-SWOT- und Evidence-Audit-Schritte miteinander verbindet.

### 7.3 Mehrstufige LLM-Pipeline mit Expert:innenvalidierung

Eine 2026 publizierte Proof-of-Concept-Studie untersuchte deutschsprachig erhobene Interviews aus Österreich, die für die LLM-Analyse ins Englische übersetzt wurden, und verglich eine mehrstufige LLM-Pipeline mit einer manuellen Baseline [20]. Expert:innen stellten relevante thematische Überschneidungen fest, kritisierten jedoch unter anderem die Granularität, vage Konzepte und die Kontextabhängigkeit der erzeugten Ergebnisse. Die Ausgaben wurden insbesondere nach menschlicher Revision als nutzbar beurteilt.

Diese Arbeit bildet relevante Prior Art für die grundsätzliche Verwendung mehrstufiger LLM-Pipelines. Während dort ein progressives Codebook innerhalb der LLM-Pipeline aufgebaut wird, verarbeitet der vorliegende Workflow ein extern entwickeltes Kategoriensystem und bereits kodierte Segmente. Die vorliegende Implementierung unterscheidet sich zudem hinsichtlich der technischen Qualitätssicherung: Sie kann lokal über Ollama ausgeführt werden und verbindet Segment-ID-Rückführung, Blind-Coding, deterministisches Agreement sowie Evidence-Audit in einem gemeinsamen Workflow [1].

### 7.4 Weitere lokale und auditierbare Ansätze

Neuere Open-Source-Projekte zeigen, dass lokale Verarbeitung, Goldstandard-Kalibrierung, Blind-Coding und Audit-Trails zunehmend eigenständige Entwicklungsziele darstellen. `Concord` verbindet beispielsweise KI-codierte Korpora mit Gold-Kalibrierung, Blind-Doppelcodierung, Agreement-Statistik und einem Ledger-basierten Replikationspfad [21]. `interview-analysis` positioniert das LLM ausdrücklich als vorläufigen First-Cycle-Coder und fordert eine menschliche Validierung der Ergebnisse [22].

Die Überschneidungen mit diesen Ansätzen sind kein Hinweis auf eine Übernahme fremder Arbeit. Vielmehr zeigen sie, dass unterschiedliche Projekte auf vergleichbare methodische Probleme reagieren, insbesondere auf Anforderungen hinsichtlich Provenienz, Validierung, Blindheit, Stabilität und menschlicher Verantwortlichkeit. Für die Abgrenzung des vorliegenden Repositories ist deshalb nicht die Neuheit einzelner Komponenten, sondern deren konkrete Zusammenführung maßgeblich.

---

## 8. Abgrenzung des Neuheitsanspruchs

Qualitative Inhaltsanalyse, deduktives und induktives Coding, Kategorien- und Codebook-basierte Analyse, Intercoder- bzw. Agreement-Maße, Cohen's Kappa, Konfusionsmatrizen, LLM-basiertes Coding, Human–LLM-Vergleiche, lokale Open-Source-LLMs, strukturierte JSON-Ausgaben, Fall- und Negativfallanalysen, SWOT sowie Audit-Trails besitzen methodische oder technische Vorläufer [2–22]. Diese Bestandteile werden im Repository nicht als originäre Erfindungen beansprucht.

Die Eigenständigkeit liegt, soweit anhand der berücksichtigten Literatur und Software nachvollziehbar, in der konkreten Zusammenstellung und Implementierung eines YAML-gesteuerten lokalen Workflows für bereits kodierte Interviewdaten. Dabei werden Code-Verifikation, Blind-Coding und deterministisches Human–LLM Agreement mit validierten Segment-IDs, deterministischer Rückführung von Originaltexten, mehrstufigen Fall-, Kontrast-, Ambivalenz- und Zusammenhangsanalysen, einem Evidence-Audit mit programmatisch ermittelten Evidenzmerkmalen sowie einer abschließenden Synthese verbunden [1].

Diese Abgrenzung ist nicht als Prioritäts- oder Alleinstellungsbehauptung zu verstehen. Das Forschungs- und Softwarefeld entwickelt sich dynamisch, sodass vergleichbare Funktionen unabhängig entwickelt oder nachträglich veröffentlicht werden können. Vor einer wissenschaftlichen Publikation ist daher eine erneute systematische Prüfung der verwandten Arbeiten angezeigt.

---

## 9. Grenzen der Schutzmechanismen

Die implementierten Kontrollschritte begrenzen spezifische Fehlerquellen, ohne die grundsätzlichen methodischen Grenzen generativer Modelle aufzuheben. Eine validierte Segment-ID gewährleistet beispielsweise die Existenz einer Textstelle, nicht jedoch deren korrekte Interpretation. Ebenso kann eine Konfusionsmatrix formal korrekt berechnet sein, während das zugrunde liegende Kategoriensystem theoretisch ungeeignet ist.

LLMs ersetzen außerdem kein feld- oder kontextspezifisches Wissen. Kulturelle, biografische, organisationale oder emotionale Bedeutungen können nivelliert werden, insbesondere wenn latente statt ausschließlich manifeste Inhalte untersucht werden [11]. Human–LLM Agreement ist daher nicht mit klassischer Intercoder-Reliabilität zwischen zwei menschlichen Rater:innen gleichzusetzen.

Der Evidence-Audit beschreibt die empirische Breite innerhalb des vorhandenen qualitativen Materials, begründet jedoch keine populationsstatistische Repräsentativität. Ebenso verhindern Schema-Validierung, ID-Prüfung und kontrollierte Kategorien nicht sämtliche Halluzinationen, da freie Interpretationen weiterhin sachlich falsche Aussagen enthalten können. Schließlich führt auch lokale Inferenz nicht zu vollständiger Reproduzierbarkeit. Für wissenschaftliche Anwendungen sind Modellname, Modellversion bzw. Hash, Parameter, Promptversion, Softwarestand und Datenversion soweit möglich zu dokumentieren.

---

## 10. Empfohlene Verwendung in wissenschaftlichen Projekten

Für wissenschaftliche Anwendungen ergibt sich aus den vorstehenden Überlegungen ein kontrollierter Ablauf. Forschungsfrage und qualitative Methode sollten vor dem LLM-Einsatz festgelegt sowie Kategoriensystem und Codiereinheit dokumentiert werden. Eine menschliche Codierung oder zumindest eine unabhängig menschlich codierte Stichprobe ermöglicht anschließend die Prüfung LLM-basierter Zuordnungen.

LLM-Aufgaben sollten eng begrenzt und nachvollziehbar formuliert werden. Sofern eine unabhängige Übereinstimmung untersucht wird, ist Blind-Coding einer Verifikation mit bekanntem Zielcode vorzuziehen. Agreement-Kennzahlen sollten programmatisch und zusätzlich auf Ebene einzelner Kategorien ausgewertet werden, wobei Abweichungen qualitativ zu prüfen sind. Originalevidenz ist über Segment-IDs auf das Primärmaterial zurückzuführen; Kontrast- und Negativfälle sind gezielt in die Interpretation einzubeziehen.

Für die Dokumentation sind Modelle, Prompts, Parameter, Softwareversionen und relevante Änderungen festzuhalten. LLM-generierte Synthesen sollten gegen Primärmaterial und Zwischenprodukte geprüft werden. Im Methodenabschnitt einer Publikation ist zudem transparent auszuweisen, welche Aufgaben durch Forschende, LLM und deterministischen Programmcode übernommen wurden. Bei sensiblen, latenten oder kulturell stark kontextgebundenen Analysen ist eine stärkere menschliche Interpretationsrolle angezeigt als bei deskriptiven Klassifikationsaufgaben [8–11, 14, 19].

---

## 11. Transparenz zur KI-gestützten Softwareentwicklung

Neben der LLM-Nutzung innerhalb der Analysepipeline wurde auch die Software KI-gestützt entwickelt. Das Repository weist ChatGPT und OpenAI Codex als Mitwirkende an Softwarearchitektur, Code-Co-Authoring, Refactoring, Debugging, Testdesign, Promptarchitektur und Dokumentation aus [1].

Damit werden zwei Ebenen voneinander getrennt: die Nutzung von KI als Werkzeug innerhalb des Forschungsprozesses sowie die Nutzung von KI als Entwicklungswerkzeug für die Forschungssoftware. KI-gestützt erzeugter Programmcode ist nicht allein aufgrund seiner Erzeugungsweise wissenschaftlich validiert. Maßgeblich ist vielmehr, ob Implementierung, Berechnungen, Datenflüsse und methodische Annahmen überprüft und getestet werden. Die modulare Architektur und die vorhandenen Tests unterstützen diese Prüfung, ersetzen jedoch weder Code Review noch fachliche Validierung.

---

## 12. Übersicht der Qualitätssicherungslogik

| Bekannte Herausforderung | Gegenmaßnahme der Pipeline | Verbleibende Grenze |
|---|---|---|
| LLM erzeugt nicht vorhandene Kategorien | Validierung gegen externes Kategoriensystem | inhaltliche Richtigkeit des formal gültigen Codes |
| Bestätigung vorhandener menschlicher Codes | separates Blind-Coding ohne Zielcode | keine Unabhängigkeit im Sinne eines menschlichen Raters |
| instabile oder erfundene Agreement-Werte | deterministische Berechnung | keine Aussage über interpretative Validität |
| halluzinierte oder veränderte Zitate | Segment-ID-Validierung und Originaltext-Rückführung | keine Garantie korrekter Interpretation |
| erfundene Häufigkeiten | programmatische Evidenzberechnung | keine statistische Repräsentativität |
| Verlust von Minderheitenpositionen | Kontrast- und Negativfallanalyse | Gegenfälle können übersehen werden |
| Glättung fallinterner Widersprüche | Ambivalenzanalyse | keine vollständige hermeneutische Erfassung |
| unbelegte Kausalität | Beschränkung der Zusammenhangsanalyse | Überinterpretation bleibt grundsätzlich möglich |
| nicht nachvollziehbarer Analyseweg | JSON-Zwischenprodukte, Logs, Manifest und optionaler Raw-Audit | technische Dokumentation belegt keine methodische Angemessenheit |
| Datenschutzrisiko externer Dienste | lokale Ollama-Inferenz möglich | keine automatische Datenschutz- oder Ethikkonformität |
| Modellabhängigkeit | dokumentierbare lokale Modelle und Konfiguration | keine vollständige Output-Reproduzierbarkeit |

---

## 13. Fazit

Der Forschungsstand rechtfertigt weder die pauschale Annahme einer zuverlässigen Automatisierbarkeit qualitativer Interviewanalyse noch die grundsätzliche Zurückweisung von LLMs für qualitative Forschungsprozesse. Für klar begrenzte Coding-Aufgaben werden relevante Übereinstimmungen berichtet, während die Ergebnisse zugleich erheblich von Codebook, Promptgestaltung, Modell, Kontext und Interpretationstiefe abhängen [3, 6–13, 20].

Aus diesen Befunden ergibt sich für die Pipeline eine arbeitsteilige Qualitätssicherungslogik. Generative Modelle werden für Aufgaben eingesetzt, bei denen sprachliche Strukturierung und Interpretation einen analytischen Beitrag leisten können. Deterministisch berechenbare oder validierbare Operationen werden demgegenüber programmatisch ausgeführt. Die wissenschaftliche Interpretations- und Entscheidungsverantwortung verbleibt bei den Forschenden.

Die implementierten Schutzmechanismen zielen dementsprechend nicht darauf, Modellfehler grundsätzlich auszuschließen. Sie sollen Fehler lokalisierbarer machen, die Rückführung auf empirische Evidenz unterstützen und die Grenzen automatisierter Interpretation nachvollziehbar dokumentieren.

---

## Literatur und verwandte Ressourcen

**[1]** Brändle, M. (2026). *Qualitative Analyse-Pipeline mit Ollama*. GitHub Repository, Version 0.1.0.  
https://github.com/braendma/Qualitative-Analyse-mit-Ollama (Abruf: 31. August 2026)

**[2]** Kuckartz, U., & Rädiker, S. (2024). *Qualitative Inhaltsanalyse. Methoden, Praxis, Umsetzung mit Software und künstlicher Intelligenz* (6. Aufl.). Beltz Juventa. ISBN 978-3-7799-7912-8. Kapitel-10-Leseprobe:  
https://qualitativeinhaltsanalyse.de/documents/Kuckartz_Raediker_2024_Qualitative_Inhaltsanalyse_K10_Leseprobe.pdf

**[3]** Kempny, C., Frings, J., Rust, P., Meister, S., & Fehring, L. (2026). The use and methodological reporting of large language models in qualitative research: A scoping review. *BMC Medical Research Methodology, 26*, 137. https://doi.org/10.1186/s12874-026-02913-1

**[4]** Kempny, C., Annac, K., Yilmaz-Aslan, Y., & Brzoska, P. (2026). *KI in der qualitativen Forschung: Von der Studienplanung bis zur Datenauswertung*. Springer. https://doi.org/10.1007/978-3-662-73089-8

**[5]** Mayring, P. (2025). Qualitative Inhaltsanalyse mit ChatGPT: Fallstricke, grobe Annäherungen und grobe Fehler. Ein Erfahrungsbericht. *Forum Qualitative Sozialforschung / Forum: Qualitative Social Research, 26*(1), Art. 4. https://doi.org/10.17169/fqs-26.1.4252

**[6]** Xiao, Z., Yuan, X., Liao, Q. V., Abdelghani, R., & Oudeyer, P.-Y. (2023). Supporting Qualitative Analysis with Large Language Models: Combining Codebook with GPT-3 for Deductive Coding. In *Proceedings of the 28th International Conference on Intelligent User Interfaces Companion* (pp. 75–78). ACM. https://doi.org/10.1145/3581754.3584136

**[7]** Zhang, H., Wu, C., Xie, J., Rubino, F., Graver, S., Kim, C. M., Carroll, J. M., & Cai, J. (2024). *When Qualitative Research Meets Large Language Model: Exploring the Potential of QualiGPT as a Tool for Qualitative Coding*. arXiv:2407.14925. https://arxiv.org/abs/2407.14925

**[8]** Balt, E., Salmi, S., Bhulai, S., Vrinzen, S., Eikelenboom, M., Gilissen, R., Creemers, D., Popma, A., & Mérelle, S. (2025). Deductively coding psychosocial autopsy interview data using a few-shot learning large language model. *Frontiers in Public Health, 13*, 1512537. https://doi.org/10.3389/fpubh.2025.1512537

**[9]** Turner, J., Hey, S. P., Baker, Z. G., Mor, V., & Sullivan, J. L. (2026). Large language models for deductive qualitative content analysis in dementia-focused embedded pragmatic clinical trials: A comparative methodological study. *Implementation Science Communications, 7*, 130. https://doi.org/10.1186/s43058-026-00953-8

**[10]** Vikan, M., Aryan, R., Kannelønning, M. S., Riegler, M. A., & Danielsen, S. O. (2026). Reflecting on LLM Support in Reflexive Thematic Analysis: An Exploratory Study. *Qualitative Health Research, 36*(2–3), 191–205. https://doi.org/10.1177/10497323251365211

**[11]** Umer, M., Asif, M., Xue, S., Jones, B. D. M., Dennis, C.-L., Naeem, F., Mulsant, B. H., & Husain, M. I. (2026). Using ChatGPT for thematic analysis of qualitative interviews in cultural research: A methodological investigation. *Asian Journal of Psychiatry, 122*, 105071. https://doi.org/10.1016/j.ajp.2026.105071

**[12]** Dunivin, Z. O. (2025). Scaling hermeneutics: A guide to qualitative coding with LLMs for reflexive content analysis. *EPJ Data Science, 14*, 28. https://doi.org/10.1140/epjds/s13688-025-00548-8

**[13]** Hila, A., & Hauser, E. (2025). Assessing the reliability of large language models for deductive qualitative coding: A comparative intervention study with ChatGPT. *Proceedings of the Association for Information Science and Technology, 62*(1), 275–285. https://doi.org/10.1002/pra2.1255

**[14]** Liu, A., Sun, M., Esbenshade, L., Xiao, M., Tian, V., Zhang, Z., & He, K. (2026). *Human-LLM Collaborative Inductive Coding for Conceptualizing K-12 Educator AI Use*. arXiv:2607.28889. https://arxiv.org/abs/2607.28889

**[15]** Burla, L., Knierim, B., Barth, J., Liewald, K., Duetz, M., & Abel, T. (2008). From text to codings: intercoder reliability assessment in qualitative content analysis. *Nursing Research, 57*(2), 113–117. https://pubmed.ncbi.nlm.nih.gov/18347483/

**[16]** Fehring, L., Frings, J., Rust, P., Kempny, C., Thürmann, P. A., & Meister, S. (2025). Extension of the Consolidated Criteria for Reporting Qualitative Research Guideline to Large Language Models (COREQ+LLM): Protocol for a Multiphase Study. *JMIR Research Protocols, 14*, e78682. https://doi.org/10.2196/78682

**[17]** Ibrahim, E. I., & Voyer, A. (2026). Qualitative research with LLM chatbots: Technological reflexivity for interpretative technology. *Qualitative Research*. https://doi.org/10.1177/14687941251390794

**[18]** `quallmer`: Qualitative analysis with large language models. GitHub Repository.  
https://github.com/quallmer/quallmer (Abruf: 31. August 2026)

**[19]** Prahl, A. (2026). The AI-Reflexivity Checklist (ARC): A Pre-Analysis Pause for LLM-Assisted Coding. *Qualitative Health Research, 36*(2–3), 181–190. https://doi.org/10.1177/10497323251401503

**[20]** Forster, E., Kartschmit, N., Klager, E., Mosor, E., Schuster, B., Mosor, E., Stamm, T., & Donsa, K. (2026). Multi-Stage LLM Pipeline to Support Qualitative Content Analysis – A Proof of Concept Experiment with Expert Validation. In G. Schreier et al. (Eds.), *dHealth 2026: Proceedings of the 20th Health Informatics Meets Digital Health Conference* (pp. 110–116). IOS Press. https://doi.org/10.3233/SHTI260065

**[21]** `concord`: Instrument-grade qualitative text analysis. GitHub Repository.  
https://github.com/emollick/concord (Abruf: 31. August 2026)

**[22]** `interview-analysis`: CLI tool to support non-interpretive interview coding. GitHub Repository.  
https://github.com/DennisSchulmeister/interview-analysis (Abruf: 31. August 2026)

### Ergänzende aktuelle Literatur

Dörfel, L., & Ammoneit, R. (2026). Evaluation of Inductive Coding with LLMs. *Education Sciences, 16*(8), 1314. https://doi.org/10.3390/educsci16081314

Misra, R., Dahal, R., Kirk, B., Khan, R., Dogan, G., Chataut, R., & Gyawali, P. (2026). Large Language Models in Qualitative Analysis: Comparing Traditional and Researcher-Interpreted Approaches. *International Journal of Qualitative Methods*. https://doi.org/10.1177/16094069261426100

---

## Zitier- und Aktualisierungshinweis

Die Datei dokumentiert den methodischen Stand des Projekts und die zum angegebenen Zeitpunkt identifizierten verwandten Arbeiten. Da sich Forschung und Open-Source-Software zur LLM-gestützten qualitativen Analyse dynamisch entwickeln, ist die Literatur- und Softwareabgrenzung vor einer wissenschaftlichen Publikation erneut systematisch zu prüfen.