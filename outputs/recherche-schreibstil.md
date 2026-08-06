# Recherche: Nachrichten-Schreibhandwerk für Telco Radar

Stand: 2026-08-06. Auftrag: Belegte Regeln aus Stilbüchern, Journalistenschulen,
Verständlichkeitsforschung und Business-Intelligence-Publikationen sammeln und
in ein einsetzbares deutsches Prompt-Regelwerk für den LLM-Editor übersetzen.
Ziel-Gefühl: Nachrichtenportal (WSJ, Spiegel, FAZ), nicht Berichtsprosa.

---

## 1. Erkenntnisse mit Quellen

### 1.1 Headline-Handwerk (Englisch: AP, Economist, Guardian, BBC)

- **AP-Stil**: Jede Überschrift braucht ein Verb, meist im **Präsens** (auch
  für vergangene Ereignisse — journalistisches "historisches Präsens"), in
  **Aktiv**. Keine Überschrift beginnt mit einem Verb — es braucht ein
  Subjekt, die Zeile muss als vollständiger Satz lesbar sein. Kein Punkt am
  Ende. Richtwert **unter 100 Zeichen**. Unnötige Wörter (Artikel,
  Konjunktionen, "ist"/"sind") fallen weg ("Downstyle"-Großschreibung: nur
  erstes Wort und Eigennamen groß).
  Quelle: [Print headline rules – COM311](https://janenattcom311.wordpress.com/headline-rules/), [PR Daily/Grammar Girl AP-Style](https://www.prdaily.com/grammar-girl-gives-sage-ap-style-advice-in-an-ever-changing-writing-world/)
- **BBC News Style Guide**: einfache Sprache, kein Fachjargon, **kurze
  Sätze, Aktiv, direkte Formulierung**, unnötige Wörter und komplexe
  Nebensatzkonstruktionen streichen. Leitsatz: *"keep it plain and keep it
  simple"*; Texte laut vorlesen, um holprige Stellen zu erkennen.
  Quelle: [dl.iir.edu.ua – BBC News Style Guide](https://dl.iir.edu.ua/iir-news/bbc-news-style-guide-a-comprehensive-look-1764800835)
- **Guardian/Observer Style Guide**: Überschriften sollen **ausgewogen und
  informativ** sein, Sprache "clean, contemporary and consistent" — Worte
  sollen "so hart wie möglich arbeiten" (jedes Wort trägt Bedeutung, keine
  Füllwörter).
  Quelle: [sean.co.uk – Guardian Style Guide](https://www.sean.co.uk/a/journalism/writing_with_style.shtm)
- **"Headlinese"**: Im **Englischen** werden in Schlagzeilen systematisch
  Artikel, Hilfsverben und Kopulaverben weggelassen ("Article Drop"), ein
  eigenes Register mit fester Grammatik. Im **Deutschen** ist diese Form der
  Elli­pse seltener und riskanter: Journalistikon (siehe 1.2) beschreibt für
  deutsche Schlagzeilen zwar auch eine "elliptisch-komprimierende" Passiv-
  Variante mit weggelassenem Hilfsverb und Artikel ("ARD-Fernsehteam bei
  Recherche festgenommen"), aber als **Sonderfall neben** der Vollverb-
  Aktiv-Form, nicht als Standard wie im Englischen. Das Deutsche bevorzugt
  den vollständigen Aktivsatz mit Verb.
  Quelle: [Andrew Weir (2009) – Article drop in English headlinese](https://awweir.files.wordpress.com/2017/04/weir-2009-headlinese.pdf), [Journalistikon – Überschrift](https://journalistikon.de/ueberschrift/)

### 1.2 Dachzeile, Schlagzeile, Unterzeile (deutsche Zeitungs-Titelei)

Klassischer Aufbau, hierarchisch von oben nach unten (Quelle:
[Journalistikon – Überschrift](https://journalistikon.de/ueberschrift/),
[helpster.de – Dachzeile](https://www.helpster.de/dachzeile-eines-artikels-was-sie-fuer-eine-zeitung-beachten-sollten_75850),
[Zeitung in der Schule, Pressehaus Heidenheim](http://www.hz-online.de/fileadmin/downloads/zisch/lehrer.pdf)):

1. **Dachzeile** (auch Kicker/Spitzmarke): kleine, unauffällige Zeile ÜBER
   der Hauptüberschrift. Nennt **sachlich das Thema/den Rahmen** (Region,
   Ressort, Unternehmen), ohne Zuspitzung oder Wertung — keine
   Fettschrift, keine Übertreibung. Funktion: einordnen, nicht anlocken.
2. **Schlagzeile** (Hauptzeile): **fasst den Kern zusammen oder deutet ihn**,
   zielt auf den flüchtig lesenden Leser, muss beim Überfliegen wirken.
   Journalistikon unterscheidet **Themen-Titel** ("Neue Debatte um
   Stadionbau") von **Aussage-Titel** ("Gericht stoppt Ausbau der A44") —
   Letzterer ist konkreter und stärker.
3. **Unterzeile** (Subhead/Dek): liefert **Basisinformationen** und führt in
   den Artikel — ergänzt die Schlagzeile inhaltlich oder verstärkt sie
   stilistisch, oft der Ort, an dem die "Warum jetzt"-Info steht, die in die
   Schlagzeile nicht mehr passt.
4. Danach folgt der **Vorspann** (Lead) als erster Absatz des Fließtexts.

**Doppelpunkt-Muster** in deutschen Schlagzeilen (Journalistikon): drei
wiederkehrende Formen — Quelle:Aussage ("US-Behörde: 2015 war das heißeste
Jahr"), Ursache:Ereignis ("Krebserkrankung: Barça-Trainer Vilanova tritt
zurück"), Thema:Aktuelles ("Flüchtlingskrise: Österreich fordert
Obergrenze"). Ausrufe- und Fragezeichen gelten in der seriösen Presse als
Boulevard-Signal und werden vermieden, weil sie Meinung/Spekulation
suggerieren. Referenzwerke: Wolf Schneider, *Die Überschrift* (5. Aufl.
2015); Markus Reiter, *Überschrift, Vorspann, Bildunterschrift* (2009).
Quelle: [Journalistikon – Überschrift](https://journalistikon.de/ueberschrift/)

**Wolf Schneiders Stilregeln** (*Deutsch für Profis*): "weg mit den
Adjektiven, her mit den Verben" — aktive Verben statt Substantivkonstruktionen
(Nominalstil), kurze Sätze statt Schachtelsätze, konkrete statt abstrakte
Begriffe.
Quelle: [hm-kom.de – Buchtipp Wolf Schneider](https://www.hm-kom.de/blog/2016-05-16-buchtipp-wolf-schneiders-deutsch-fur-profis-wege-zu-gutem-stil)

### 1.3 Textstrukturen

- **Umgekehrte Pyramide**: wichtigste Fakten zuerst, absteigende
  Relevanz danach — damit der Text auch beim Kürzen von hinten funktioniert.
  Quelle: [Wikipedia – Inverted pyramid](https://en.wikipedia.org/wiki/Inverted_pyramid)
- **Nut Graf**: der Absatz nach dem Lead, der die **"So what?"-Frage**
  beantwortet — warum die Geschichte jetzt zählt, welchen Kontext sie
  braucht. Ursprung u. a. beim Wall Street Journal als redaktioneller
  Standardbaustein.
  Quelle: [Poynter – The nut graf, Part I](https://www.poynter.org/archive/2003/the-nut-graf-part-i/), [CCNY Intro to Journalism – The Nut Graf](https://ccnyintroductiontojournalism.com/2024/02/12/the-nut-graf/)
- **Axios Smart Brevity**: sechs Kernregeln — für die Zielgruppe schreiben,
  mit kurzer, konkreter Überschrift Aufmerksamkeit gewinnen, **"Was ist neu"
  und "Warum es wichtig ist" je in einem Satz**, einfache Subjekt-Verb-Objekt-
  Sätze, menschlich schreiben, mit kurzen Absätzen und Aufzählungen
  scannbar machen. Fettgedruckte Schlüsselbegriffe ("Axioms") strukturieren
  den Text, gefolgt von genau einem Satz oder wenigen Bulletpoints.
  Quelle: [Axios HQ – Understanding Smart Brevity](https://help.axioshq.com/hc/en-us/articles/40406826943891-Understanding-Smart-Brevity), [journalism.co.uk – How Axios is reinventing text journalism](https://www.journalism.co.uk/how-axios-is-reinventing-text-journalism-with-smart-brevity/)
- **Semafor "Semaform"**: trennt Fakt und Meinung explizit in fünf
  Bausteine — **The News** (unstrittige Fakten), **Reporter's View**
  (Einordnung/Analyse des Autors), **Room for Disagreement** (worin die
  eigene Analyse falsch liegen könnte — explizite Gegenposition),
  **The View From** (Perspektive einer beteiligten Partei/Region), **Notable**
  (Links zu guter Berichterstattung anderswo). Begründung von Executive
  Editor Gina Chua: klassische Artikel verweben Fakt und Analyse so eng,
  dass Leser sie nicht auseinanderhalten können; das Format macht
  redaktionelle Entscheidungen sichtbar und benennt legitimen Dissens.
  Quelle: [Semafor – What is a Semaform, anyway?](https://www.semafor.com/article/10/18/2022/what-is-a-semaform-anyway-and-why-should-you-care)
- **Bloomberg "Five Things" / Economist "Espresso"**: tägliches Kompakt-
  Format, fünf kurze, in sich abgeschlossene Meldungen à ca. 1 Minute
  Lesezeit ("finishable 1 minute reads") statt eines langen Fließtexts.
  Quelle: [Bloomberg – Five Things](https://www.bloomberg.com/news/newsletters/2024-10-07/five-things-you-need-to-know-to-start-your-day-americas), [Apple App Store – Espresso](https://apps.apple.com/JP/app/id896628003)

**Einordnung für ein Wettbewerbs-Briefing**: Die Semaform-Trennung
(Fakt/Einordnung/Gegenposition) passt inhaltlich am besten zu einer
Competitive-Intelligence-Meldung — sie erzwingt genau die Struktur, die eine
Managerin braucht: **was ist passiert (Fakt) → was heißt das für Vodafone
(Einordnung) → wie sicher ist das (Gegenposition/Unsicherheit)**. Axios Smart
Brevity liefert das Tempo-Prinzip (kurze Sätze, ein Satz je Aussage,
scannbare Struktur) für die Kürze der einzelnen Meldung; die umgekehrte
Pyramide plus Nut Graf strukturieren den langen Wochenbericht.

### 1.4 Verständlichkeit auf Deutsch für Fachfremde

- **Hamburger Verständlichkeitskonzept** (Langer/Schulz von Thun/Tausch,
  1970er): vier Dimensionen, mit Skala von −2 bis +2 bewertbar:
  1. **Einfachheit** (wichtigste Dimension, Optimum bei +2): geläufige
     Wörter, kurze Sätze, Fachwörter erklärt statt vermieden, konkret und
     anschaulich; Nebensätze vor oder nach dem Hauptsatz, nicht eingebettet.
  2. **Gliederung/Ordnung** (zweitwichtigste, Optimum bei +2): von Anfang an
     klar, worum es geht; Reihenfolge logisch, Zusammenhänge erkennbar;
     äußerlich sichtbar durch Absätze, Zwischenüberschriften, Hervorhebungen,
     Zusammenfassungen.
  3. **Kürze/Prägnanz** (Optimum nahe 0 — auch zu radikale Kürze schadet;
     etwas Redundanz durch Wiederholung in anderen Worten hilft dem
     Verständnis).
  4. **Anregende Zusätze** (am wenigsten wichtig; Gefühle ansprechen, aber
     sparsam, sonst verdeckt es den Kern).
  Empirisch: 70 % der trainierten Schreiber produzierten gut verständliche
  Texte, gegenüber 20 % ungeschulter Schreiber.
  Quelle: [Wikipedia – Hamburger Verständlichkeitskonzept](https://de.wikipedia.org/wiki/Hamburger_Verst%C3%A4ndlichkeitskonzept)
- **Wiener Sachtextformel** (Bamberger/Vanecek 1984): berechnet eine
  Schulstufen-Note (4 = sehr leicht, 15 = sehr schwer) aus vier Variablen —
  MS = Anteil Wörter mit ≥3 Silben, SL = mittlere Satzlänge (Wörter), IW =
  Anteil Wörter mit >6 Buchstaben, ES = Anteil einsilbiger Wörter.
  WSTF1 = 0,1935·MS + 0,1672·SL + 0,1297·IW − 0,0327·ES − 0,875 (genaueste
  Variante, alle vier Merkmale); vereinfachte Varianten WSTF2–4 nutzen
  weniger Merkmale.
  Quelle: [Websuche – Wiener Sachtextformel Formel/Variablen](https://oscarstories.com/de/calculator/wiener-sachtextformel/), [dewiki – Lesbarkeitsindex](https://dewiki.de/Lexikon/Lesbarkeitsindex)
- **LIX-Index**: sprachunabhängig, gut für Sprachvergleiche, aus mittlerer
  Satzlänge und Anteil langer Wörter (>6 Buchstaben).
  Quelle: [fleschindex.de – Lesbarkeitsindex im Überblick](https://fleschindex.de/lesbarkeitsindex)
- **Flesch-Amstad**: Toni Amstads deutsche Adaption der Flesch-Reading-
  Ease-Formel, mit angepasstem Wortlängen-Faktor (deutsche Wörter sind im
  Schnitt länger als englische).
  Quelle: [fleschindex.de – Wiener Sachtextformel](https://fleschindex.de/wiener-sachtextformel)
- **Python-Messbarkeit**: Die Bibliothek **`textstat`** unterstützt Deutsch
  inklusive `textstat.wiener_sachtextformel(text, variant)` (variant 1–4,
  Rückgabe = Schulstufen-Note) sowie weitere Indizes; Silbenzählung läuft
  intern über `Pyphen`. Für die Wiener Sachtextformel gibt es zusätzlich das
  eigenständige, MIT-lizenzierte Skript **`pablotheissen/wstf`**.
  Quelle: [DeepWiki – textstat Readability Metrics](https://deepwiki.com/textstat/textstat/3.2-readability-metrics), [GitHub – textstat #113 German Readability](https://github.com/textstat/textstat/issues/113), [GitHub – pablotheissen/wstf](https://github.com/pablotheissen/wstf)
- **Nominalstil**: Wenn Sätze überwiegend durch Substantivierungen
  ("die Durchführung der Prüfung erfolgte") statt Verben ("man prüfte")
  getragen werden, sinkt die Verständlichkeit — Verbalstil aktiviert und
  beschleunigt das Lesen, macht klarer, wer/was handelt.
  Quelle: [Uni Leipzig Schreibportal – Nominalstil](https://home.uni-leipzig.de/schreibportal/nominalstil/)

### 1.5 Business-Intelligence-Briefings

- **Axios "Why it matters"** ist inzwischen de facto Branchenstandard für
  kurze Analyse-Absätze in Tech-/Wirtschaftsjournalismus — ein fett
  hervorgehobenes Schlüsselwort, gefolgt von genau einem erklärenden Satz.
  Quelle: [Axios HQ – Smart Brevity](https://help.axioshq.com/hc/en-us/articles/40406826943891-Understanding-Smart-Brevity)
- **CB Insights**: Analyst-Briefings strukturieren konsequent nach **"was
  tut das Unternehmen — warum zählt es — was bedeutet das für [Zielgruppe,
  hier: kleinere/andere Unternehmen]"**. Auffällig ist die bewusst
  zugängliche, nicht-trockene Tonalität trotz Datenlastigkeit — dient als
  Beleg, dass "Zielgruppe versteht sofort" und "seriöse Analyse" sich nicht
  ausschließen.
  Quelle: [CB Insights – Analyst Insights](https://www.cbinsights.com/what-we-offer/platform/analyst-insights/), [Radix Communications – CB Insights Newsletter](https://radix-communications.com/b2b-content-hall-of-fame-how-cb-insights-created-a-god-tier-newsletter/)
- **Stratechery/The Information**: Stratechery ist bekannt dafür, "Punkte zu
  verbinden" — Einzelmeldungen in einen größeren strategischen Rahmen zu
  setzen, statt sie isoliert zu berichten (genau das fehlt im aktuellen
  Telco-Radar-Bericht: Meldungen stehen nebeneinander ohne verbindende
  These). The Information setzt auf exklusive, klar auf das Wesentliche
  fokussierte Berichterstattung ohne Ablenkung durch Nebensächliches.
  Quelle: [amazingnewsletters.com – Stratechery vs The Information](https://amazingnewsletters.com/compare/stratechery-vs-the-information)
- **Gartner**: Research Notes destillieren große Datenmengen zu klaren,
  präzisen **Empfehlungen** ("Key Findings" + "Recommendations" als feste
  Bausteine), damit Kunden auf Basis der Kürzung Entscheidungen treffen
  können — Konvention: erst Befund, dann explizite Handlungsanweisung,
  getrennt ausgewiesen.
  Quelle: [Gartner – Methodologies Overview](https://www.gartner.com/imagesrv/research/methodologies/methodologies_brochure_14.pdf)

**Fehlende, aber wichtige Konvention (aus eigener Kenntnis, nicht in den
gefundenen Quellen explizit belegt, deshalb hier nur als Hinweis)**:
professionelle Analystenhäuser markieren oft explizit den **Vertrauensgrad**
einer Einschätzung (z. B. "hohe/mittlere/geringe Zuverlässigkeit",
"unbestätigt", "laut Unternehmensangabe" vs. "laut Analyse"). Für Telco
Radar übersetzt sich das simpler: **jede Einordnung muss durch die
Originalquelle abgesichert oder ausdrücklich als Einschätzung der
Redaktion markiert sein** — das deckt sich mit Antonios Anforderung
"jede Aussage mit Quellen-Link".

### 1.6 Anti-Patterns bei LLM-generiertem Text ("AI Slop")

- **Englische Signalphrasen** (breit belegt, mehrere unabhängige Quellen):
  "In today's fast-paced world", "in today's ever-evolving landscape",
  "it's no secret that", "it's worth noting", "delve into", "game-changer",
  "at the end of the day", "leverage cutting-edge solutions to streamline
  your workflow". Strukturmerkmale: **uniforme Satzlängen** (jeder Satz
  10–15 Wörter), **Stakkato-Fragmente** ("Kurz. Knapp. Überall."),
  Aufzählungswut.
  Quelle: [ignorance.ai – Field Guide to AI Slop](https://www.ignorance.ai/p/the-field-guide-to-ai-slop), [SlopDetector.org](https://slopdetector.org/)
- **Deutsche Signalphrasen**: "essenziell", "vielfältig", "nahtlos",
  "maßgeschneidert", "ganzheitlich"; Brückenfloskeln wie "Es ist wichtig zu
  beachten, dass …" oder "Insgesamt lässt sich festhalten …"; Einstiegsfloskeln
  "In der heutigen Zeit ist es wichtiger denn je, …", "In einer Welt, in
  der…", "Integraler Bestandteil"; Muster "Nicht nur X, sondern auch Y" bzw.
  "Wenn X, dann Y" überproportional häufig.
  Quelle: [giga.de – Floskeln, die ChatGPT/KI-Texte erkennen lassen](https://www.giga.de/artikel/mit-diesen-floskeln-lassen-sich-chatgpt-ki-texte-erkennen/), [t3n – 5 Anzeichen für KI-Texte](https://t3n.de/news/ki-texte-erkennen-5-merkmale-chatgpt-1745388/)

Für Telco Radar sind "es bleibt abzuwarten" und "unterstreicht die
Bedeutung" nicht in den zitierbaren Quellen als AI-Slop-Belege genannt,
gehören aber demselben dokumentierten Muster an (vage,
folgenlose Abschluss- bzw. Betonungsfloskel) und sind aus eigener
Beobachtung des bisherigen Wochenberichts bekannt — sie werden deshalb in
die Verbotsliste unten aufgenommen, mit dieser Einschränkung transparent
gemacht.

---

## 2. Prompt-Baustein: Deutsches Regelwerk für den LLM-Editor

Der folgende Block ist so geschrieben, dass er **wörtlich** als Abschnitt in
den System-Prompt von `analyze/editor.py` (bzw. der Chefredaktion/
Bereichsredakteur-Prompts) eingesetzt werden kann.

```
### SCHREIBHANDWERK (verbindlich für jede Ausgabe)

Du schreibst wie eine Nachrichtenredaktion (Vorbild: Spiegel, FAZ,
Handelsblatt), nicht wie ein Analyse-Tool. Halte dich an diese Regeln.

--- (a) ÜBERSCHRIFTEN ---
- Jede Überschrift ist ein vollständiger Satz mit Subjekt und Verb im
  Aktiv, Präsens (auch für bereits abgeschlossene Ereignisse: "Vodafone
  kauft", nicht "Vodafone kaufte").
- Beginne NIE mit dem Verb. Das Subjekt (meist der Unternehmens- oder
  Ländername) steht vorn.
- Maximal 70 Zeichen. Kürzer ist besser.
- Konkrete Fakten statt Themenankündigung: "Telefónica halbiert
  Netzausbau-Budget für 2027" statt "Neue Pläne bei Telefónica".
- Eigennamen (Unternehmen, Länder, Produkte) so weit vorn wie möglich.
- Zahlen als Ziffern, nicht ausgeschrieben (5, nicht "fünf").
- Kein Punkt am Satzende. Keine Ausrufe- oder Fragezeichen (das ist
  Boulevard-Stil, keine seriöse Nachricht).
- Keine Häufung von Adjektiven oder Superlativen.

--- (b) DACHZEILE + DEK (Vorspann-Zeile) ---
- Die Dachzeile (max. 30 Zeichen) ordnet sachlich ein: Region oder
  Themenfeld, z. B. "EUROPA · NETZAUSBAU" oder "REGULIERUNG". Keine
  Wertung, kein Superlativ, kein Ausrufezeichen.
- Der Dek (1 Satz, max. 160 Zeichen) liefert die Information, die in der
  Überschrift keinen Platz mehr hatte: Kontext, Zeitpunkt, Größenordnung.
  Er wiederholt die Überschrift NICHT in anderen Worten, sondern ergänzt
  sie.
- Dachzeile und Dek sind vollständige, für sich verständliche Sätze bzw.
  Fragmente — keine Fortsetzung der Überschrift über den Zeilenumbruch
  hinweg.

--- (c) MELDUNGSTEXT (einzelne Meldung) ---
Struktur, in dieser Reihenfolge, jeder Baustein als eigener kurzer Absatz:
1. WAS IST PASSIERT (1–2 Sätze, umgekehrte Pyramide): die wichtigste
   Tatsache zuerst, ohne Vorgeschichte.
2. WARUM ES FÜR VODAFONE ZÄHLT (1 Absatz, 2–4 Sätze): die Einordnung.
   Beginne den Absatz mit dem fett hervorgehobenen Signalwort "Warum es
   zählt:" nach dem Vorbild von Axios' "Why it matters". Sag konkret, was
   sich für Vodafone dadurch ändert oder ändern könnte — keine
   allgemeine Bedeutungsbehauptung ohne Konsequenz.
3. EINORDNUNG/UNSICHERHEIT (optional, 1 Satz): wenn die Meldung auf einer
   Selbstauskunft des Unternehmens beruht, unbestätigt ist oder es
   plausible Gegenlesarten gibt, benenne das explizit ("laut
   Unternehmensangabe", "noch nicht von Dritten bestätigt", "Analysten
   sind sich uneinig, ob …").
- Jede Tatsachenbehauptung braucht einen Quellenlink an der Stelle, wo sie
  steht — nicht gesammelt am Absatzende.
- Sätze im Schnitt unter 20 Wörter. Ein Gedanke pro Satz.
- Aktiv statt Passiv, wo immer möglich. Verben statt Substantivierungen
  ("X kündigt an" statt "die Ankündigung von X erfolgte").
- Fachbegriffe (5G-SA, Spectrum-Auktion, MVNO, Glasfaser-Wholesale, …)
  beim ersten Vorkommen im Text in einem Halbsatz erklären, nicht durch
  einen Linkverweis ersetzen und nicht vermeiden.

--- (d) LANGER WOCHENBERICHT (Gesamtstruktur) ---
Der Bericht folgt der umgekehrten Pyramide über die GESAMTE Ausgabe, nicht
nur je Meldung:
1. Ein Nut Graf ganz oben (3–5 Sätze): beantwortet sofort "worum geht es
   diese Woche insgesamt und warum betrifft es Vodafone" — bevor irgendein
   Abschnitt beginnt. Ein Leser, der nur diesen Absatz liest, kennt die
   Kernaussage der Woche.
2. Danach absteigende Wichtigkeit: die wichtigste Einzelmeldung der Woche
   zuerst ausführlich, dann der Rest nach Region/Thema. Kein Abschnitt
   darf wichtiger wirken, wenn er es inhaltlich nicht ist, nur weil er
   weiter oben in der bisherigen festen Gliederung stand.
3. Jeder Regions-/Themenabschnitt beginnt mit einem eigenen Ein-Satz-
   Fazit ("Diese Woche in Europa: …"), bevor Einzelmeldungen folgen —
   kein Abschnitt startet direkt mit Aufzählungen ohne Einordnungssatz.
4. Meinung/Einordnung wird von Fakt sprachlich getrennt (nach Vorbild
   Semafor): Fakten stehen im Meldungstext, Einordnung ausschließlich im
   "Warum es zählt"-Absatz oder in einem eigenen mit "Einordnung:"
   markierten Absatz — niemals unmarkiert vermischt.
5. Absätze maximal 4 Sätze. Zwischenüberschriften mindestens alle 150–200
   Wörter im Fließtext.

--- VERBOTSLISTE (harte Ausschlüsse, in KEINER Ausgabe verwenden) ---
Floskeln/Phrasen (Deutsch): "in der heutigen schnelllebigen Welt", "in
einer Welt, in der …", "es bleibt abzuwarten", "unterstreicht die
Bedeutung", "es ist wichtig zu betonen/beachten, dass", "insgesamt lässt
sich festhalten", "vor diesem Hintergrund", "nicht zuletzt", "ganzheitlich",
"nahtlos", "maßgeschneidert", "essenziell", "vielfältig", "integraler
Bestandteil", "auf das nächste Level heben", "Game-Changer",
"zukunftsweisend", "wegweisend", "Meilenstein" (außer bei tatsächlichem
Etappenziel mit Zahl), "Startschuss", "die Weichen stellen".
Satzmuster: "Nicht nur X, sondern auch Y" und "Wenn X, dann Y" jeweils
höchstens einmal je Ausgabe — nicht als wiederkehrendes Baumuster.
Leere Superlative ohne Beleg ("massiv", "enorm", "bahnbrechend",
"revolutionär") — wenn eine Zahl belegt, wie groß etwas ist, steht die
Zahl da, nicht das Adjektiv.
Aufzählungswut: keine Bulletliste, wenn ein Fließsatz die gleiche
Information trägt. Aufzählungen nur für wirklich parallele, gleichrangige
Elemente (z. B. Liste von Ländern).
Wiederholung derselben Kerninformation in zwei verschiedenen Formulierungen
im selben Text (Überschrift sagt X, erster Satz sagt X noch einmal mit
anderen Worten) — das kostet Platz ohne neue Information.
```

---

## 3. Textbausteine pro Meldung — Vorschlag für die Pipeline

| Baustein | Zweck | Max. Zeichen | Vorbild |
|---|---|---|---|
| Dachzeile | Sachliche Einordnung (Region/Thema) | 30 | Zeitungs-Kicker |
| Schlagzeile | Kern der Meldung, Aktiv+Präsens+Subjekt | 70 | AP/dpa |
| Dek (Vorspann-Satz) | Ergänzender Kontext, 1 Satz | 160 | FAZ-Unterzeile |
| "Was ist passiert" | Faktenkern, umgekehrte Pyramide | 280 (2 Sätze) | Inverted Pyramid |
| "Warum es zählt" | Einordnung für Vodafone, mit Quellenbezug | 320 (2–4 Sätze) | Axios "Why it matters" |
| Einordnung/Unsicherheit | Optional: Quellenlage, Gegenposition | 160 (1 Satz) | Semafor "Room for Disagreement" |
| Dringlichkeit | Bestehendes Feld (1–5), unverändert | – | – |

Damit entsteht pro Meldung ein festes, kurzes Muster (Dachzeile → Schlagzeile
→ Dek → Was ist passiert → Warum es zählt → ggf. Einordnung), das sich sowohl
für die Explorer-Detailansicht als auch für die Top-Prioritäten-Karten eignet
und das aktuelle Problem löst: sofort erkennbar, worum es geht, ohne den
ganzen Absatz lesen zu müssen.

Für den langen Wochenbericht zusätzlich: ein **Nut Graf** (3–5 Sätze, max.
500 Zeichen) direkt nach der Hero-Zeile, vor "Für Eilige"/Executive Summary
— beantwortet "worum geht es diese Woche" sofort, bevor irgendein
Unterabschnitt beginnt.

---

## 4. Maschinell prüfbare Qualitätskriterien (Python-Check nach Generierung)

1. **Überschriften-Länge**: `len(headline) <= 70` Zeichen; Regel-Verstoß
   loggen, nicht hart blocken (Sonderfälle mit langen Eigennamen).
2. **Verb-vorn-Verbot**: erstes Token der Überschrift ist kein finites Verb
   (POS-Tag-Check z. B. via spaCy `de_core_news_sm`).
3. **Kein Satzzeichen-Boulevard**: Überschrift/Dachzeile enthalten kein `!`
   oder `?`.
4. **Floskel-Scan**: Regex-Liste aus Abschnitt 2 (Verbotsliste) gegen jeden
   generierten Text; Treffer zählen und im CI/Report als Warnung ausgeben —
   analog zu den Ansätzen von SlopDetector/AI-Slop-Word-Blacklist, aber mit
   eigener, auf Telco-Radar-Floskeln zugeschnittener Liste statt der
   generischen Fantasy-Wortliste.
   Quelle: [blog.atharvashah.com – AI Slop Word Blacklist](https://blog.atharvashah.com/p/the-ultimate-ai-slop-word-blacklist)
5. **Satzlängen-Verteilung**: mittlere Wörter/Satz im Meldungstext < 20;
   Warnung, wenn > 3 Sätze in Folge dieselbe Wortzahl ±1 haben
   (Uniformitäts-Anzeichen von KI-Text).
6. **Lesbarkeitsindex**: `textstat.wiener_sachtextformel(text, variant=1)`
   je Meldung und für den Gesamtbericht berechnen, Zielkorridor Schulstufe
   8–10 (Tageszeitungsniveau) protokollieren; deutliche Ausreißer nach oben
   (>12) markieren.
   Quelle: [GitHub – textstat, German Readability](https://github.com/textstat/textstat/issues/113)
7. **Nominalstil-Anteil**: Anteil der Wörter mit Endungen `-ung`, `-heit`,
   `-keit`, `-tion`, `-ismus` pro Satz messen; hoher Anteil als
   Nominalstil-Warnung (Heuristik, kein Ersatz für manuelle Prüfung).
8. **Passivanteil**: Anteil finiter Verben in Passivkonstruktion
   ("wird/wurde … + Partizip II") über POS-Tagging schätzen; Zielwert
   niedrig halten (BBC/AP-Vorbild: Aktiv bevorzugt).
9. **Quellenlink-Abdeckung**: jeder Absatz mit einer Tatsachenbehauptung
   (heuristisch: enthält Zahl, Eigenname + Verb der Vergangenheit/Gegenwart)
   muss einen Link im selben oder direkt angrenzenden Satz enthalten —
   Regex/Struktur-Check auf Markdown-Linksyntax je Absatz.
10. **Wiederholungs-Check**: Kosinus-Ähnlichkeit (TF-IDF oder Embeddings)
    zwischen Überschrift und erstem Satz des Deks; bei zu hoher Ähnlichkeit
    (> Schwellenwert) Warnung "Dek wiederholt Überschrift".
11. **Dachzeile-Neutralität**: Dachzeile darf keine Wörter aus der
    Verbotsliste (Abschnitt 2) und keine Adjektive mit Steigerungsform
    enthalten (heuristisch über POS/Morphologie).
12. **Bausteinlängen**: alle in Abschnitt 3 genannten Zeichenobergrenzen
    hart als CI-Check, mit Toleranz von max. 10 % vor Fehlerabbruch des
    Redaktionslaufs.

Alle zwölf Checks lassen sich in einem einzigen Nachlauf-Skript
(`scripts/pruefe_schreibstil.py`, analog zu den bestehenden
`scripts/pruefe_quellenvorschlag.py`) realisieren, das nach dem
EDIT-Schritt läuft und Verstöße als strukturierte Warnungen ins
Laufprotokoll schreibt — passend zum bestehenden Muster harter,
maschineller Abnahme-Checks im Projekt (siehe CLAUDE.md Abschnitt 6:
"Ein Modell, das 'ich habe es geprüft' sagt, zählt nicht").

---

## 5. Quellenliste (URLs)

- [Print headline rules – COM311 (AP-Stil-Regeln)](https://janenattcom311.wordpress.com/headline-rules/)
- [PR Daily – Grammar Girl AP-Style-Tipps zu Überschriften](https://www.prdaily.com/grammar-girl-gives-sage-ap-style-advice-in-an-ever-changing-writing-world/)
- [The Economist Style Guide (PDF, 2015)](http://cdn.static-economist.com/sites/default/files/store/Style_Guide_2015.pdf)
- [BBC News Style Guide – Zusammenfassung](https://dl.iir.edu.ua/iir-news/bbc-news-style-guide-a-comprehensive-look-1764800835)
- [sean.co.uk – Guardian/Observer Style Guide](https://www.sean.co.uk/a/journalism/writing_with_style.shtm)
- [Andrew Weir (2009) – Article drop in English headlinese](https://awweir.files.wordpress.com/2017/04/weir-2009-headlinese.pdf)
- [Journalistikon – Überschrift](https://journalistikon.de/ueberschrift/)
- [helpster.de – Dachzeile eines Artikels](https://www.helpster.de/dachzeile-eines-artikels-was-sie-fuer-eine-zeitung-beachten-sollten_75850)
- [Zeitung in der Schule – Pressehaus Heidenheim (PDF)](http://www.hz-online.de/fileadmin/downloads/zisch/lehrer.pdf)
- [hm-kom.de – Buchtipp Wolf Schneider, Deutsch für Profis](https://www.hm-kom.de/blog/2016-05-16-buchtipp-wolf-schneiders-deutsch-fur-profis-wege-zu-gutem-stil)
- [Wikipedia – Inverted pyramid](https://en.wikipedia.org/wiki/Inverted_pyramid)
- [Poynter – The nut graf, Part I](https://www.poynter.org/archive/2003/the-nut-graf-part-i/)
- [CCNY Intro to Journalism – The Nut Graf](https://ccnyintroductiontojournalism.com/2024/02/12/the-nut-graf/)
- [Axios HQ – Understanding Smart Brevity](https://help.axioshq.com/hc/en-us/articles/40406826943891-Understanding-Smart-Brevity)
- [journalism.co.uk – How Axios is reinventing text journalism](https://www.journalism.co.uk/how-axios-is-reinventing-text-journalism-with-smart-brevity/)
- [Semafor – What is a Semaform, anyway?](https://www.semafor.com/article/10/18/2022/what-is-a-semaform-anyway-and-why-should-you-care)
- [Bloomberg – Five Things Newsletter](https://www.bloomberg.com/news/newsletters/2024-10-07/five-things-you-need-to-know-to-start-your-day-americas)
- [Apple App Store – Espresso von The Economist](https://apps.apple.com/JP/app/id896628003)
- [Wikipedia – Hamburger Verständlichkeitskonzept](https://de.wikipedia.org/wiki/Hamburger_Verst%C3%A4ndlichkeitskonzept)
- [fleschindex.de – Lesbarkeitsindex im Überblick (Flesch, WSTF, LIX, SMOG)](https://fleschindex.de/lesbarkeitsindex)
- [fleschindex.de – Wiener Sachtextformel](https://fleschindex.de/wiener-sachtextformel)
- [dewiki – Lesbarkeitsindex (WSTF-Formel-Details)](https://dewiki.de/Lexikon/Lesbarkeitsindex)
- [GitHub – textstat, Issue #113 German Readability Support](https://github.com/textstat/textstat/issues/113)
- [DeepWiki – textstat Readability Metrics](https://deepwiki.com/textstat/textstat/3.2-readability-metrics)
- [GitHub – pablotheissen/wstf (Wiener Sachtextformel in Python)](https://github.com/pablotheissen/wstf)
- [Uni Leipzig Schreibportal – Nominalstil](https://home.uni-leipzig.de/schreibportal/nominalstil/)
- [CB Insights – Analyst Insights](https://www.cbinsights.com/what-we-offer/platform/analyst-insights/)
- [Radix Communications – CB Insights Newsletter Analyse](https://radix-communications.com/b2b-content-hall-of-fame-how-cb-insights-created-a-god-tier-newsletter/)
- [amazingnewsletters.com – Stratechery vs The Information](https://amazingnewsletters.com/compare/stratechery-vs-the-information)
- [Gartner – Research Methodologies Overview (PDF)](https://www.gartner.com/imagesrv/research/methodologies/methodologies_brochure_14.pdf)
- [ignorance.ai – The Field Guide to AI Slop](https://www.ignorance.ai/p/the-field-guide-to-ai-slop)
- [SlopDetector.org](https://slopdetector.org/)
- [blog.atharvashah.com – The Ultimate AI Slop Word Blacklist](https://blog.atharvashah.com/p/the-ultimate-ai-slop-word-blacklist)
- [giga.de – Floskeln, die ChatGPT & KI-Texte erkennen lassen](https://www.giga.de/artikel/mit-diesen-floskeln-lassen-sich-chatgpt-ki-texte-erkennen/)
- [t3n – 5 Anzeichen, die KI-Texte verraten](https://t3n.de/news/ki-texte-erkennen-5-merkmale-chatgpt-1745388/)
