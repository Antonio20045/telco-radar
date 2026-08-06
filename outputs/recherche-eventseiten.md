# Recherche: Automatische Ereignis-/Themen-Erkennung und temporäre Event-Seiten

Stand: 2026-08-06. Recherche für Telco Radar — Frage: Wie erkennt die Pipeline
automatisch, dass gerade ein großes Ereignis läuft (z. B. Samsung Unpacked,
ein Apple-Launch, eine große Übernahme), und wie baut sie dafür eine
temporäre Unterseite, die nach Abklingen wieder verschwindet, ohne einen
toten Link zu hinterlassen?

---

## 1. Kurzfassung der Empfehlung

**Kein Embedding-Clustering, kein klassisches Burst-Detection-Verfahren.**
Beides ist für Volumen ausgelegt, das Telco Radar pro Lauf nicht hat.
Stattdessen: ein **zweistufiges Verfahren aus mechanischem Vorfilter (billig,
kein LLM) und einer LLM-Bestätigung/Beschriftung (ein zusätzlicher Aufruf pro
Lauf)** — im Prinzip dieselbe Architektur, die die Redaktion (Bereichsredakteur
+ Chefredaktion) bereits nutzt, nur als dritte Stufe nach dem Editor. Ergänzt
um einen **handgepflegten Ereigniskalender** als Prior für die wenigen
Termine, die man ohnehin kennt (MWC, IFA, CES, Apple-Keynotes, Samsung
Unpacked), damit die Erkennung nicht erst nach zwei Läufen (~3–4 Tage)
anspringt, wenn das Ereignis längst läuft.

Begründung in Kürze — die drei klassischen Alternativen scheitern konkret an
der Datenmenge:

- **Kleinbergs Burst-Detection** modelliert Begriffshäufigkeit als
  Zwei-Zustands-Automat und braucht dafür genug Beobachtungen, um
  Übergangsraten zu schätzen — die Originalarbeit und ihre gängigen
  Erklärungen setzen kontinuierliche Zeitreihen mit vielen Ereignissen voraus
  (E-Mail-Threads über Jahre, Zitationsdaten). Bei 100–250 neuen Titeln
  zweimal pro Woche gibt es pro Begriff oft nur 1–5 Treffer — zu wenig, um
  eine Rate robust zu schätzen. ([Nikki Marinsek: Kleinberg burst detection](https://nikkimarinsek.com/blog/kleinberg-burst-detection-algorithm), [Logort: Understanding Kleinberg's Burst Detection](https://logort.com/analytics/understanding-kleinbergs-burst-detection-algorithm/))
- **Embedding-Clustering (HDBSCAN/BERTopic)** ist explizit für größere Korpora
  gebaut: Die BERTopic-FAQ nennt bereits **~1000 Dokumente** als "wenig", der
  Default-Parameter `min_cluster_size` von HDBSCAN liegt bei 10 — bei 200
  Titeln pro Lauf, verteilt über 87 Regionen/8 Themenfelder, bekäme man fast
  nie einen validen Cluster, außer man senkt den Parameter so weit, dass er
  Rauschen produziert. ([BERTopic FAQ](https://maartengr.github.io/BERTopic/faq.html), [BERTopic Parameter Tuning](https://maartengr.github.io/BERTopic/getting_started/parameter%20tuning/parametertuning.html))
- **Reine TF-IDF-Spikes** haben ein Kaltstart-Problem: Ein Produktname, der
  zum ersten Mal auftaucht (z. B. "Galaxy S27"), hat per Definition keine
  Historie, gegen die man einen Anstieg messen könnte. TF-IDF eignet sich gut
  als *Filter gegen Dauerbrenner* (siehe unten), aber nicht als *primärer*
  Auslöser für echte Neuheiten.

Was dagegen bei kleinen Datenmengen nachweislich funktioniert, sind zwei
Muster aus der Praxis: **(a)** einfache, deterministische Titel-Ähnlichkeit
(Wortüberlappung nach Normalisierung) als Vorfilter — genau das nutzt
NewsBlur produktiv, ganz ohne Embeddings, für sein Story-Clustering
([NewsBlur-Blog](https://blog.newsblur.com/2026/03/18/story-clustering/)) —
und **(b)** LLM als Cluster-Labeler/-Bestätiger *nach* einem billigen
Vorfilter, nicht als Clustering-Engine für den gesamten Rohstrom (das
"Map-Reduce"-Muster: erst gruppieren, dann pro Gruppe *einmal* das LLM
aufrufen, nicht pro Dokument) ([Piyush Kashyap: Text Clustering and Topic
Modeling with LLMs](https://medium.com/@piyushkashyap045/text-clustering-and-topic-modeling-with-llms-446dd7657366)).
Genau dieses Muster passt zur vorhandenen Architektur: 150–250 bewertete
Titel pro Lauf passen locker in ein einziges LLM-Kontextfenster, das ohnehin
schon für die Chefredaktion gefüllt wird.

Kommerzielle Systeme, die tatsächlich in Produktion News clustern, bestätigen
den Ansatz "billiger Vorfilter + Grenzwert, kein reines ML-Clustering für
kleine Batches": Die NewsCatcher-API etwa clustert über Kosinus-Ähnlichkeit
von Embeddings mit einem Schwellenwert von **0,7** (0,6 = größere/lockerere
Gruppen, 0,8 = enger) und Leiden-Community-Detection auf dem
Ähnlichkeitsgraphen — aber das läuft über *Millionen* Artikel und pro
Suchanfrage neu, nicht über einen 200-Item-Batch zweimal die Woche
([NewsCatcher-Doku](https://www.newscatcherapi.com/docs/news-api/guides-and-concepts/clustering-news-articles)).
Google News selbst kombiniert NLP-Themenerkennung mit Streaming-Pipelines
(Kafka-artig) auf Milliarden-Scale ([System Design Handbook: Google News](https://www.systemdesignhandbook.com/guides/google-news-system-design/),
[US8832105B2 — System for incrementally clustering news stories](https://patents.google.com/patent/US8832105)) — auch das ist eine Größenordnung, die für
Telco Radar irrelevant ist, aber das *Prinzip* "Cluster wachsen inkrementell,
werden gesplittet und gemergt, brauchen zwei getrennte Schwellenwerte" ist
direkt übertragbar (siehe Abschnitt 4).

---

## 2. Warum LLM-nativ statt Embedding-Infrastruktur

Ein Einwand liegt nahe: Anthropic bietet keine Embedding-API, man bräuchte
also einen zweiten Anbieter (z. B. Voyage AI oder OpenAI) nur für
Story-Clustering — zusätzliche Abhängigkeit, zusätzliches Secret,
zusätzlicher Fehlerfall. Bei 200 Titeln pro Lauf lohnt sich das nicht: Das
LLM, das ohnehin für die Analyse und Redaktion läuft, kann **denselben Job
günstiger und robuster** erledigen, weil es:

1. semantische statt nur lexikalische Ähnlichkeit versteht (wichtig, weil die
   Feeds seit Session 5 fünfsprachig sind — Deutsch, Französisch, Spanisch,
   Italienisch, Portugiesisch; ein rein wortbasierter Ähnlichkeitsfilter
   würde "Samsung lance son nouveau pliable" und "Samsung stellt neues
   Faltgerät vor" nicht zusammenführen, ein LLM schon),
2. in einem einzigen Aufruf **klassifizieren** kann, ob ein Kandidat
   tatsächlich ein Ereignis ist oder nur zufällige Stichwort-Überschneidung
   (das "Cluster bestätigen oder ablehnen"-Muster, siehe TnT-LLM-Framework:
   erst Taxonomie/Pseudo-Label per LLM, dann erst skalieren)
   ([Vickie Liu: From chaos to clarity](https://medium.com/data-science-at-microsoft/from-chaos-to-clarity-building-taxonomies-from-unstructured-text-using-large-language-models-c1303db3adb1)),
3. bereits im Kontext hat, was in den letzten Wochen berichtet wurde (Topic-
   Memory, `reported_topics.jsonl` existiert schon) — die Story-Erkennung
   kann dieselbe Gedächtnisschicht mitnutzen, statt eine zweite parallele
   Infrastruktur (Vektor-Store) aufzubauen.

Der mechanische Vorfilter (Schritt 1, siehe unten) bleibt trotzdem nötig —
nicht weil er das Clustering besser könnte, sondern damit **nicht jeder Lauf
einen weiteren vollen LLM-Durchlauf über alle 150–250 Titel braucht, nur um
am Ende "kein Ereignis" zu antworten**. Das ist Kostendisziplin, kein
Qualitätsargument gegen LLMs.

---

## 3. Datenmodell: die "Story"

Ein neuer, zustandsbehafteter Datentyp, analog zu den bestehenden State-
Dateien (`quellen_register.json`, `reported_topics.jsonl`). Vorschlag:
`data/state/stories.json`, ein Dict, Schlüssel = `story_id` (sprechender Slug,
z. B. `samsung-unpacked-2026-01`):

```json
{
  "story_id": "samsung-unpacked-2026-01",
  "titel": "Samsung Galaxy Unpacked Januar 2026",
  "kategorie": "produkt_launch",
  "kurzfassung": "Zwei bis drei Sätze, vom LLM geschrieben — nur bei Statuswechsel neu erzeugt, nicht bei jedem Lauf.",
  "status": "aktiv",
  "schluessel_akteure": ["Samsung", "Qualcomm", "Google"],
  "erster_treffer": "2026-01-15",
  "letzter_treffer": "2026-01-29",
  "kalender_anker": {"quelle": "config/ereignis_kalender.yaml", "termin_von": "2026-01-20", "termin_bis": "2026-01-22"},
  "meldungen": [
    {"titel": "...", "url": "...", "quelle_domain": "sammobile.com", "datum": "2026-01-16",
     "region_oder_thema": "thema:geraete", "dringlichkeit": 4, "lauf": 83}
  ],
  "anzahl_meldungen": 14,
  "anzahl_unabhaengiger_quellen": 6,
  "laeufe_ohne_neue_meldung": 0,
  "erzeugt_in_lauf": 82,
  "zuletzt_aktualisiert_in_lauf": 84,
  "llm_konfidenz": 0.9,
  "verworfen_grund": null
}
```

Wichtig: **`meldungen` referenziert dieselben Items, die ohnehin schon durch
COLLECT/DELTA/ANALYZE gelaufen sind** — die Story-Erkennung liest nur mit,
sie sammelt nichts neu und ruft keine zusätzlichen Quellen ab. Das hält den
Eingriff in die bestehende Pipeline minimal: ein neuer Schritt zwischen EDIT
und PUBLISH, der die bewerteten Meldungen des aktuellen Laufs plus die
`stories.json` aus dem letzten Lauf liest und aktualisiert zurückschreibt.

`anzahl_unabhaengiger_quellen` zählt **Domains**, nicht Meldungen — das ist
der wichtigere Wert (siehe Abschnitt 4). Die Unterscheidung "viele Meldungen,
eine Quelle" vs. "wenige Meldungen, viele Quellen" ist in der
Journalismus-Literatur der Standardindikator für Newsworthiness: Mehrere
voneinander unabhängige Quellen, die ein Thema unabhängig aufgreifen, gelten
als verlässlicheres Signal für Bedeutung als reines Volumen
([Wikipedia: Independent sources](https://en.wikipedia.org/wiki/Independent_sources)).

---

## 4. Erkennungsregeln mit konkreten Zahlen

### 4.1 Schritt 1 — mechanischer Vorfilter (kein LLM-Aufruf, läuft auf allen bewerteten Meldungen des Laufs)

1. **Kandidaten-Schlüssel bilden**: Für jede bewertete Meldung (bereits durch
   ANALYZE gelaufen, hat also Region/Thema-Tag) wird geprüft, ob ein bekannter
   Akteur/Produktname aus einer neuen, kleinen Konfigdatei
   `config/beobachtete_akteure.yaml` im Titel vorkommt (analog zu den
   bestehenden Alias-Listen der Watchlist — gleiche Technik, kein neuer
   Mechanismus). Ergänzend: einfache Titel-Ähnlichkeit über normalisierte
   Wortmengen (lowercase, Stopwörter raus, Jaccard-Überlappung) zwischen
   allen neuen Meldungen — das ist exakt NewsBlurs Ansatz ("significant-word
   overlap" statt Embeddings) ([NewsBlur-Blog](https://blog.newsblur.com/2026/03/18/story-clustering/)).
2. **Zeitfenster**: Meldungen aus dem aktuellen Lauf **plus den letzten drei
   Läufen** (≈ 10–12 Tage, da 2×/Woche) werden zusammen betrachtet — aus dem
   Archiv `data/reports/*.json`, das ja bereits vorliegt.
3. **Absolute Mindestschwelle** für einen Kandidaten, um überhaupt zur
   LLM-Bestätigung weitergereicht zu werden:
   - **≥ 5 bewertete Meldungen** (nicht nur gesammelte — Rauschfilter, weil
     ein Analyst sie für berichtenswert hielt) **im Zeitfenster**, UND
   - **≥ 3 unabhängige Quell-Domains**.
4. **Relative Schwelle gegen Dauerbrenner** (das eigentliche Anti-"5G ist
   kein Event"-Kriterium, siehe 4.2): Die Trefferdichte des Kandidaten im
   aktuellen Fenster muss **mindestens das 3-Fache** der historischen
   Durchschnittsdichte desselben Akteurs/Begriffs über die letzten 90 Tage
   betragen — das ist dasselbe Prinzip, mit dem Twitters Trend-Algorithmus
   echte Trends von Dauerthemen trennt: **Geschwindigkeit (Velocity), nicht
   absolutes Volumen** ist das Signal ([Sprout Social: How the Twitter
   Algorithm Works](https://sproutsocial.com/insights/twitter-algorithm/)).
   Für Akteure ohne Historie (Baseline = 0, echter Neuzugang) greift
   ausschließlich die absolute Schwelle aus Punkt 3.
5. Beide Bedingungen (absolut UND relativ, wo Baseline existiert) müssen
   erfüllt sein — nur dann geht der Kandidat in Schritt 2.

### 4.2 Explizite Dauerbrenner-Sperrliste

Ergänzend zur relativen Schwelle: eine kurze, handgepflegte Sperrliste
generischer Fachbegriffe in derselben Konfigdatei (`5G`, `6G`,
`Netzausbau`, `Glasfaser`, `Künstliche Intelligenz`, `Spektrum` etc.), die
der mechanische Vorfilter **nie eigenständig als Kandidat vorschlägt** —
diese Begriffe dürfen nur Teil eines Story-Titels werden, wenn sie an einen
konkreten, benannten Anlass gekoppelt sind (ein Produktname, ein
Firmenname, ein Deal-Name). Das ist dieselbe Vorsicht, die im Projekt schon
für Quellen-Abnahme gilt ("Form prüfen reicht nicht, der Wert bleibt
Handarbeit" — siehe CLAUDE.md Abschnitt 6): eine Sperrliste ist Handarbeit,
aber billig und pflegbar wie `config/kandidaten_firmen.yaml`.

### 4.3 Schritt 2 — LLM-Bestätigung, -Zusammenführung und -Beschriftung

Nur für Kandidaten, die Schritt 1 überstehen, **ein LLM-Aufruf pro Lauf**
(nicht pro Kandidat — alle Kandidaten in einem Prompt, Map-Reduce-Prinzip:
gruppieren zuerst, LLM danach nur noch auf die *Gruppen* ansetzen, nicht auf
jedes einzelne Item ([Piyush Kashyap, a. a. O.])). Der Prompt bekommt:

- die Kandidatenliste mit ihren Meldungen (Titel, Quelle, Datum, Kurztext),
- die Liste bereits **aktiver** Stories aus `stories.json` (damit das Modell
  entscheiden kann: neue Story oder Fortsetzung/Zusammenführung einer
  bestehenden — das "assign to existing cluster or create new"-Muster, siehe
  TnT-LLM/Taxonomie-Ansätze),
- die Sperrliste aus 4.2 als explizite Ablehnungs-Anweisung.

Das Modell liefert für jeden Kandidaten strukturiert: `confirmed` (bool),
`confidence` (0–1), `titel`, `kategorie`, `kurzfassung`, `merge_mit`
(story_id oder null), `beteiligte_akteure`. Bei `confidence < 0.6` wird der
Kandidat **nicht** veröffentlicht, sondern nur intern als „entstehend“
vorgemerkt und erst im nächsten Lauf erneut geprüft — dieselbe Regel, die im
Projekt schon für Quellen gilt: „nicht prüfbar ist kein PASS“ (CLAUDE.md
Abschnitt 6, zur Quellenabnahme) wird hier zu „nicht sicher genug ist keine
Story“.

### 4.4 Ereigniskalender als Prior (senkt die Schwelle, ersetzt sie nicht)

Für die eine Handvoll wirklich vorhersehbaren Termine im Jahr lohnt sich ein
kleiner, handgepflegter Kalender — es gibt **keine einzige öffentliche,
maschinenlesbare Sammelquelle**, die MWC/IFA/CES/Apple/Samsung-Termine
zusammen als Feed anbietet (das wurde in der Recherche gezielt geprüft: kein
gemeinsames ICS/API gefunden). Also: `config/ereignis_kalender.yaml`,
analog zu `kandidaten_firmen.yaml`, 1–2× im Jahr von Hand gepflegt (~10
Minuten Aufwand), z. B. Stand August 2026:

| Termin | Datum |
|---|---|
| MWC Barcelona 2026 | 23.–26. Februar 2026 |
| Samsung Galaxy Unpacked (Frühjahr) | typischerweise Ende Januar/Februar |
| Apple September-Keynote | erwartet Woche des 7. September 2026 |
| IFA Berlin 2026 | 4.–8. September 2026 |

(Quellen: [Shacknews CES 2026](https://www.shacknews.com/article/147308/ces-2026-guide-keynotes-livestreams-times), [The Gadgeteer: IFA 2026](https://the-gadgeteer.com/2026/05/23/ifa-2026-berlin-dates-what-to-expect/), [MacRumors: Apple September 2026](https://www.macrumors.com/2026/08/04/apple-september-2026-announcements/))

In einem Fenster von **±5 Tagen** um einen Kalendertermin sinkt die absolute
Schwelle aus 4.1 von 5/3 auf **3 Meldungen / 2 Quellen**, und die Story wird
mit vorbelegtem Titel und `kalender_anker` bereits im Zustand *entstehend*
angelegt, sodass sie beim ersten echten Treffer sofort aktiv werden kann,
statt erst nach einer Bestätigung im übernächsten Lauf. Reine
Kalender-Einträge ohne tatsächliche Meldungen erzeugen **nie** eine
sichtbare Seite — der Kalender senkt nur die Hürde, er ersetzt keine echten
Daten.

---

## 5. Lebenszyklus-Zustände

```
entstehend → aktiv → abklingend → archiviert
                 ↘  verworfen  ↙   (aus entstehend heraus, wenn LLM nicht bestätigt)
```

| Zustand | Bedingung, um hineinzukommen | Sichtbarkeit |
|---|---|---|
| **entstehend** | Schritt-1-Schwelle in genau einem Lauf erreicht, ODER Kalenderanker im ±5-Tage-Fenster ohne Bestätigung | Keine eigene Seite; taucht höchstens als "im Aufbau" im Explorer auf |
| **aktiv** | LLM bestätigt (`confidence ≥ 0.6`) UND (zweiter Lauf in Folge über der Schwelle ODER Kalenderanker vorhanden) | Eigene Seite live, in Navigation/Ticker verlinkt |
| **abklingend** | War aktiv, aktueller Lauf bringt **0–1 neue** zugeordnete Meldungen | Seite bleibt online, Badge „abklingend", rutscht aus Ticker/Startseite, bleibt im Archiv-Index sichtbar |
| **archiviert** | **Zwei aufeinanderfolgende Läufe** (≈ 1 Woche) ganz ohne neue Meldungen, ODER Kalender-Enddatum + 7 Tage Nachlauf ohne neue Meldungen | Seite bleibt unter derselben URL, wird eingefroren, Banner „Dieses Thema ist abgeschlossen — letzte Aktualisierung am [Datum]", aus Hauptnavigation entfernt, nur noch über Archiv-Index/Verweise aus alten Wochenberichten erreichbar |
| **verworfen** | LLM bestätigt in Schritt 2 nicht (`confirmed: false` oder `confidence < 0.6` über zwei Läufe hinweg) | Nie sichtbar, nur intern geloggt (für Debugging/Nachjustieren der Schwellen) |

**Wichtig — URL bleibt für immer stabil, egal in welchem Zustand.** Das ist
die zentrale Antwort auf die Link-Rot-Frage aus dem Auftrag: Es wird
**nichts gelöscht**, nur der Zustand degradiert und Navigation/Sichtbarkeit
ändern sich. Das folgt derselben Logik, die für Nachrichtenarchive als Best
Practice gilt: alte, relevante URLs archivieren statt entfernen, damit keine
404-Ketten entstehen ([Journalist's Resource: link rot best practices](https://journalistsresource.org/media/website-linking-best-practices-media-online-publishers/)).
Die Story-Seite verhält sich damit wie ein Eintrag in `archive.html`, den
das Projekt für Wochenberichte schon hat — nur eben pro Ereignis statt pro
Kalenderwoche.

Ein historisches Vorbild, das genau diese Idee schon 2009/2010 umgesetzt
hat — Google, NYT und Washington Post bauten "Living Stories": eine Seite
pro laufendem Thema mit Zusammenfassung, Zeitleiste und mehreren
Diskussionssträngen, die sich mit der Story weiterentwickelte, statt sie
als Serie isolierter Artikel abzubilden. 75 % der Testnutzer bevorzugten das
Format gegenüber klassischen Artikellisten — das Projekt scheiterte aber
nicht inhaltlich, sondern am Geschäftsmodell (kein Traffic zurück zu den
Originalartikeln, also kein Werbeerlös) ([Wikipedia: Living Stories](https://en.wikipedia.org/wiki/Living_Stories)).
Für Telco Radar ist das kein Problem — es gibt kein Werbemodell, jede
Meldung verlinkt ohnehin zur Originalquelle.

---

## 6. Seitenaufbau der Event-Seite

Orientiert an Living Stories, an CNN-Livestream-artigen "Was Sie wissen
müssen"-Blöcken ([Sourcefabric: Live Blog Examples](https://medium.com/sourcefabric/live-blog-examples-great-use-cases-for-blogging-inspiration-679f0a35b8cd)) und an
Axios' "Smart Brevity"-Prinzip (kurze, gescannte Blöcke statt Fließtext,
Struktur "Warum das wichtig ist" / "Der Stand" / "Was als Nächstes kommt")
([Wikipedia: Axios](https://en.wikipedia.org/wiki/Axios_(website))) — konsequent an das bestehende
Bloomberg-Terminal-Design angelehnt, keine neue Designsprache:

1. **Statusleiste** oben: Badge (aktiv/abklingend/archiviert), „läuft seit
   [Datum]" bzw. „abgeschlossen am [Datum]", Anzahl Meldungen, Anzahl
   unabhängiger Quellen.
2. **„Was bisher geschah"** — 2–3 Sätze, vom LLM in Schritt 2 geschrieben,
   nur bei Statuswechsel neu erzeugt (nicht bei jedem Lauf, um Kosten und
   Prosa-„Zappeln" zu vermeiden).
3. **Zeitleiste**: chronologische Liste aller zugeordneten Meldungen
   (Datum, Quelle, Titel, Link, Dringlichkeit) — technisch dieselbe
   Explorer-Komponente, die es im Wochenbericht schon gibt, nur gefiltert
   auf `story_id`. Kein neuer Code, nur ein neuer Filter auf vorhandene
   Daten.
4. **Beteiligte Akteure**: Badges/Tags der `schluessel_akteure`.
5. **Kleines Balkendiagramm** „Meldungen pro Lauf" — dieselbe SVG-Chart-
   Technik wie die bestehenden Region-/Themen-/Dringlichkeits-Charts im
   Bericht, nur mit `story.meldungen` gruppiert nach `lauf`.
6. **Quellenliste**: die distinct Domains, mit Zähler — macht sichtbar,
   dass es sich nicht um eine Einzelquellen-Wiederholung handelt (Kern des
   Unabhängigkeits-Arguments aus Abschnitt 4).
7. **Verweise zurück**: Links auf die Wochenberichte, in denen die Story
   erwähnt wurde (Cross-Link aus dem bestehenden Archiv).
8. Wenn abgeschlossen: Banner „Dieses Thema ist abgeschlossen" statt
   aktiver Statusleiste — Seite bleibt sonst identisch, keine separate
   Archiv-Vorlage nötig.

**SEO-Detail, das sich anbietet, wenn eine Story aktiv "live" läuft**: das
Schema.org-Objekt `LiveBlogPosting` mit dem Feld `coverageEndTime` signalisiert
Suchmaschinen, dass eine Seite laufend aktualisiert wird und wann sie das
nicht mehr tut — genau der Übergang aktiv → archiviert lässt sich darüber
korrekt maschinenlesbar abbilden ([Google: Event/LiveBlog Structured Data](https://developers.google.com/search/docs/appearance/structured-data/event), [schema.org/LiveBlogPosting](https://schema.org/LiveBlogPosting)). Für ein
laienorientiertes, deutschsprachiges Projekt ist das ein „nice to have", kein
Muss — aber technisch trivial (ein JSON-LD-Block im Template) und passt zum
Nachprüfbarkeits-Anspruch des Projekts.

---

## 7. Risiken und Fehlerfälle

**Falsch-positive Ereignisse.** Abgefangen durch das Doppel-Gate: der
mechanische Vorfilter (absolute + relative Schwelle, Sperrliste) lässt nur
wenige Kandidaten durch, und das LLM muss zusätzlich mit `confidence ≥ 0.6`
bestätigen — bei Unsicherheit lieber verzögern als voreilig veröffentlichen
(„nicht sicher ist keine Story", analog zur Quellen-Abnahmeregel des
Projekts). Kalender-Anker senken nur die Meldungsschwelle, erzeugen aber
nie von selbst eine Seite ohne echte Treffer.

**Themen spalten sich auf** (z. B. „Samsung Unpacked" zerfällt in
„Galaxy-S27-Leaks", „Unpacked-Event selbst", „Quartalszahlen Samsung").
Gegenmittel: Das LLM bekommt in Schritt 2 immer die **volle Liste aktiver
Stories** mitgeliefert und kann neue Kandidaten explizit einer bestehenden
zuordnen (`merge_mit`), statt automatisch eine neue anzulegen — das
klassische „einer bestehenden Gruppe zuordnen oder neue Gruppe eröffnen"-
Muster, wie es Taxonomie-Aufbau-Ansätze mit LLMs beschreiben ([Vickie Liu,
a. a. O.]). Eine Story ist bewusst kein starres Cluster, sondern ein
lebendes, vom LLM jeden Lauf neu bewertetes Objekt.

**Themen verschmelzen fälschlich** (zwei unabhängige Ereignisse teilen sich
zufällig einen Firmennamen, z. B. „Telefónica"-Übernahme und ein unabhängiges
„Telefónica"-CEO-Zitat). Der mechanische Vorfilter erzeugt hier nur einen
*Kandidaten* — die inhaltliche Trennung entscheidet ausschließlich das LLM
anhand der tatsächlichen Titel/Kurztexte, nicht anhand der reinen
Stichwort-Kookkurrenz. Genau dieses Fehlerbild (Cluster wachsen falsch
zusammen, weil frühe Einzelmeldungen fälschlich getrennten Clustern
zugeordnet wurden) ist in der Streaming-Clustering-Literatur als „Cluster
Merging" bekanntes Problem mit eigenen, separat kalibrierten Schwellenwerten
für Split und Merge beschrieben — die Empfehlung von dort, **zwei getrennte
Schwellenwerte statt einem gemeinsamen** zu verwenden, ist hier direkt
übernommen (Schritt 1 mechanisch grob, Schritt 2 LLM fein)
([Forschungsbeispiel zu Split/Merge in News-Streams](https://www.researchgate.net/figure/Splitting-and-merging-of-news-stories-a-during-its-evolution-over-time-theme-A-can_fig1_258143454)).

**Dauerbrenner-Themen** ("5G", "Netzausbau"). Doppelt abgesichert: explizite
Sperrliste (4.2) plus relative Geschwindigkeits-Schwelle (4.1, Punkt 4) nach
dem Twitter-Prinzip „Geschwindigkeit schlägt Volumen".

**Kosten/Betriebsrisiko.** Ein zusätzlicher LLM-Aufruf pro Lauf (Kandidaten
+ aktive Stories, gebündelt) bewegt sich in derselben Größenordnung wie die
bestehenden Editor-Aufrufe — bei den aktuell $1,45/Monat im teuersten Fall
ist das ein Aufschlag im Cent-Bereich, kein neues Kostenrisiko.

**Kleine Stichprobe, nur Titel + Kurztext, kein Volltext.** Das LLM soll bei
Unsicherheit explizit `confidence` niedrig ansetzen dürfen, statt zu raten —
lieber ein Lauf Verzögerung als eine falsche Story. Diese Regel spiegelt die
im Projekt bereits etablierte Haltung bei der Quellenabnahme: „nicht prüfbar
ist kein PASS."

**Pflegeaufwand der neuen Config-Dateien** (`beobachtete_akteure.yaml`,
`ereignis_kalender.yaml`). Beide sind bewusst klein und folgen exakt dem
Muster bestehender Config-Dateien (`kandidaten_firmen.yaml`,
`tech_sources.yaml`) — kein neues Pflegekonzept, sondern Wiederverwendung
eines etablierten.

---

## 8. Zusammenfassung: warum genau dieses Verfahren zum Kontext passt

Der Kontext — 200 kurze Titel zweimal wöchentlich, LLM billig verfügbar,
kein Volltext, statische Site — schließt die Verfahren aus, die für
kontinuierliche, hochvolumige Ströme gebaut wurden (Burst Detection,
Embedding-Clustering), und macht die Stärke des Projekts selbst zur Lösung:
Es gibt bereits ein LLM, das jeden Lauf ohnehin über alle bewerteten
Meldungen schaut, eine Editor-Architektur mit Bereichs- und Chefredaktion,
ein Topic-Memory und ein Berichtsarchiv als Historie. Die Story-Erkennung
ist am günstigsten als **dritte, kleine Erweiterung derselben Pipeline**
umsetzbar — ein mechanischer Vorfilter, der auf vorhandenen Daten läuft und
nichts Neues sammelt, plus ein zusätzlicher, gebündelter LLM-Aufruf, der
dieselbe Prompt-Logik nutzt wie die bestehenden Analysten/Editoren.

---

## Quellenliste

- Kleinberg-Burst-Detection: [Nikki Marinsek — Detecting bursts in time series data](https://nikkimarinsek.com/blog/kleinberg-burst-detection-algorithm) · [Logort — Understanding Kleinberg's Burst Detection](https://logort.com/analytics/understanding-kleinbergs-burst-detection-algorithm/) · [Logort — Making Sense of Kleinberg's Burst Detection](https://logort.com/analytics/making-sense-of-kleinbergs-burst-detection/)
- Google-News-Architektur: [System Design Handbook — Google News System Design](https://www.systemdesignhandbook.com/guides/google-news-system-design/) · [US8832105B2 — System for incrementally clustering news stories](https://patents.google.com/patent/US8832105) · [How 9/11 Inspired Google News (and MapReduce)](https://computerlab.io/2017/09/10/how-911-inspired-google-news-map-reduce/)
- LLM-Clustering/Labeling: [Piyush Kashyap — Text Clustering and Topic Modeling with LLMs](https://medium.com/@piyushkashyap045/text-clustering-and-topic-modeling-with-llms-446dd7657366) · [Vickie Liu — From chaos to clarity: Building taxonomies with LLMs](https://medium.com/data-science-at-microsoft/from-chaos-to-clarity-building-taxonomies-from-unstructured-text-using-large-language-models-c1303db3adb1)
- News-API-Clustering in Produktion: [NewsCatcher — Clustering news articles](https://www.newscatcherapi.com/docs/news-api/guides-and-concepts/clustering-news-articles)
- Topic Detection and Tracking (TDT), First Story Detection: [James Allan — TDT Lecture Slides (UMass)](https://www.khoury.northeastern.edu/home/jaa/CSG339.06F/Lectures/news_tdt.pdf) · [TDT Pilot Study Final Report](https://ciir.cs.umass.edu/pubfiles/ir-137.pdf)
- Inkrementelles Online-Clustering von News-Streams: [Real-time News Story Identification (arXiv 2508.08272)](https://arxiv.org/pdf/2508.08272) · [An Incremental Clustering Baseline for Event Detection on Twitter (arXiv 2412.15257)](https://arxiv.org/pdf/2412.15257) · [Event-Driven News Stream Clustering using Entity-Aware Contextual Embeddings (arXiv 2101.11059)](https://arxiv.org/pdf/2101.11059)
- Split/Merge-Problematik bei Story-Clustering: [Splitting and merging of news stories — Figure (ResearchGate)](https://www.researchgate.net/figure/Splitting-and-merging-of-news-stories-a-during-its-evolution-over-time-theme-A-can_fig1_258143454)
- Kleine Datenmengen bei BERTopic/HDBSCAN: [BERTopic — FAQ](https://maartengr.github.io/BERTopic/faq.html) · [BERTopic — Parameter Tuning](https://maartengr.github.io/BERTopic/getting_started/parameter%20tuning/parametertuning.html)
- Praxisbeispiel Titel-basiertes Clustering ohne Embeddings: [NewsBlur-Blog — Story clustering](https://blog.newsblur.com/2026/03/18/story-clustering/)
- Living Stories (Google/NYT/Washington Post): [Wikipedia — Living Stories](https://en.wikipedia.org/wiki/Living_Stories)
- Live-Blog-Format, "Was bisher geschah": [Sourcefabric — Live Blog Examples](https://medium.com/sourcefabric/live-blog-examples-great-use-cases-for-blogging-inspiration-679f0a35b8cd) · [Liveblog.pro — Live blogging breaking news best practices](https://liveblog.pro/en/live-blogging-breaking-news-best-practices-zeit-online/)
- LiveBlogPosting-Schema/SEO: [Google — Event Structured Data](https://developers.google.com/search/docs/appearance/structured-data/event) · [schema.org/LiveBlogPosting](https://schema.org/LiveBlogPosting) · [WTF is SEO — Structured data for live news](https://www.seoforjournalism.com/p/structured-data-for-live-blogs-and)
- Link-Rot/Archivierungs-Best-Practice: [Journalist's Resource — Link rot and best practices for online publishers](https://journalistsresource.org/media/website-linking-best-practices-media-online-publishers/)
- Axios „Smart Brevity" als Vorbild für Kurzformat: [Wikipedia — Axios (website)](https://en.wikipedia.org/wiki/Axios_(website))
- Trend vs. Dauerthema (Geschwindigkeit statt Volumen): [Sprout Social — How the Twitter Algorithm Works](https://sproutsocial.com/insights/twitter-algorithm/)
- Unabhängige Quellen als Signal: [Wikipedia — Independent sources](https://en.wikipedia.org/wiki/Independent_sources)
- Ereigniskalender-Termine 2026: [Shacknews — CES 2026 Guide](https://www.shacknews.com/article/147308/ces-2026-guide-keynotes-livestreams-times) · [The Gadgeteer — IFA 2026 Berlin](https://the-gadgeteer.com/2026/05/23/ifa-2026-berlin-dates-what-to-expect/) · [MacRumors — Apple September 2026 Announcements](https://www.macrumors.com/2026/08/04/apple-september-2026-announcements/) · [Wikipedia — Galaxy Unpacked](https://en.wikipedia.org/wiki/Galaxy_Unpacked)
