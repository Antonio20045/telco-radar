# KI-Agent oder Algorithmus? — Audit der Pipeline-Stufen (27.08.2026)

Auftrag (Antonio, 27.08.2026): Token-effizienter arbeiten. Prüfen, welche
Aufgaben wirklich nur ein KI-Agent kann und welche auch ein normaler
Algorithmus löst — Anlass ist die Beobachtung, dass bei leerem API-Guthaben
**gar keine Bilder** mehr auf der Website erscheinen. Nur Analyse und
Premortem, kein Umbau.

Alle Zahlen in diesem Dokument sind nachgemessen: am Code, an den
Berichts-JSONs unter `data/reports/` (Läufe vom 14.08. als letzter mit
teilweise antwortendem Modell und 19./21./25./26.08. mit leerem Guthaben)
und an `config/settings.yaml`.

---

## 1. Der Befund zu den Bildern: sie brauchen KEINEN Agenten — sie hängen nur hinter einem

**Die Bildbeschaffung ist heute schon zu 100 % algorithmisch.** Kein einziger
Modellaufruf:

| Modul | Was es tut |
|---|---|
| `report/bilder.py` | Feed-Bild UND `og:image` der Artikelseite holen, mit Pillow messen, das breitere gewinnt, als JPEG ablegen (httpx + Pillow) |
| `promo_bilder.py` | Vier-Stufen-Zuordnung Bild→Angebot (Anker → Pfad → seltene Wörter → Seitenmotiv) — reine Wort-/URL-Rechnung |
| `report/diff_bilder.py` | Wochenberichts-Bild wiederverwenden, sonst `og:image` |

**Warum trotzdem keine Bilder da sind:** `hole_bilder()` läuft über
`alle_highlights` — also nur über Meldungen, **die ein Analyst behalten
hat** (`pipeline.py:744-746`). Mit leerem Guthaben scheitern alle
Analysten-Stapel, `analyze_region` liefert null Highlights, und die
Bildstufe bekommt nichts zu tun. Gemessen am Lauf vom 26.08.:

```
Sammeln: 194 Quellen, 3655 Meldungen        → funktioniert (algorithmisch)
Nur Neues: 967 neue Meldungen               → funktioniert (algorithmisch)
Ereignisse bündeln: 863 Ereignisse          → funktioniert (algorithmisch)
Bewerten & Schreiben: 0 bewertete Meldungen → alle Stapel scheitern (402)
Bilder: 0 von 0 Meldungen mit Bild          → die Stufe bekommt LEEREN Input
```

Der Bericht fällt auf den „Redaktions-Fallback / Roh-Digest" zurück — eine
Linkliste im Fließtext, ohne Karten. Ohne Karten kein Ort für ein Bild.
**Es ist ein Anzeige-/Auswahlproblem, kein Bildproblem.**

### Das Paradox: `--no-llm` wäre besser als „Key da, Guthaben leer"

Der Code kennt zwei verschiedene Ausfallpfade, und der schlechtere ist der,
der gerade läuft:

| Pfad | Highlights | Bilder | Seen-Store |
|---|---|---|---|
| **explizit ohne LLM** (`--no-llm` bzw. kein Key) | alle neuen Meldungen als „Unbewertet"-Karten (`pipeline.py:616-627`) | werden geholt | **ALLES wird als gesehen markiert** — die Meldungen werden nie mehr bewertet |
| **Key vorhanden, Guthaben leer** (heute) | 0 — Stapel scheitern, Fallback greift nicht (er greift nur bei Exception aus `analyze_region`, nicht bei „alle Stapel gescheitert") | 0 von 0 | geschützt: ungelesene Meldungen bleiben draußen und kommen wieder |

`llm_available()` prüft nur, ob ein Key **existiert** — nicht, ob er zahlt
(`analyze/llm.py:80`). Deshalb nimmt die Pipeline mit leerem Guthaben den
LLM-Pfad und endet mit der leersten aller Seiten. Der eine Umbau, der
Antonios Beobachtung direkt beantwortet, wäre: **wenn alle Anbieter tot sind
(`dead_models()` / alle Stapel gescheitert), für die SEITE auf den
Unbewertet-Karten-Pfad wechseln — aber mit dem Seen-Store-Schutz des
heutigen Kaputt-Pfads.** Achtung: den bestehenden No-LLM-Zweig darf man
dafür NICHT einfach nehmen, der verbrennt den Bestand (siehe Premortem #2).

---

## 2. Inventar: alle Modellaufrufstellen, klassifiziert

Es gibt genau **14 Module mit LLM-Aufrufen** (Importer von
`analyze/llm.py`), plus die Übersetzung. Alles andere — Sammeln, Delta,
Geräteradar, Tarif-, Lieferzeit-, Änderungs- und CT-Radar-Kern,
Wettbewerbs-Chronik, Suche, Effektivpreis, alle drei Bild-Module, der
gesamte Rendervorgang — ist bereits modellfrei.

### Klasse A — schon algorithmisch (hier ist nichts zu holen)

Bilder (alle drei Module), Ereignis-Clustering-**Kern** (Wortpaar-Rechnung),
CTM **Stufe 3 + Rückfallstufe** (`ctm.deterministische_stufe`, reine
Config-Rechnung), Promo-Score-**Achsen** (Composite nach OECD-Handbook,
reiner Code), Highlight-Themen-**Kandidatensuche und Zuordnung** (läuft
ausdrücklich auch ohne Modell weiter), Zahlen-/Sicherheitswort-Prüfung in
`faithfulness.py`.

### Klasse B — Modell nur als Zusatzstufe; abschaltbar oder ersetzbar mit kleinem, messbarem Verlust

| Stufe | Modellanteil | Algorithmische Alternative | Risiko |
|---|---|---|---|
| Clustering-Graubereichsprüfung | prüft unsichere Paare nach | `cluster_llm_pruefung: false` (Schalter existiert) — der deterministische Kern trägt | Dubletten ODER falsche Zusammenlegungen im Graubereich; vorher die Graubereichsquote im Protokoll messen. Kostenpunkt ist real: „Ereignisse bündeln" brauchte am 14.08. **580 s** (mit Modell) gegen 83 s (ohne) |
| CT-Radar-Modellstufe | sortiert Infrastruktur-Subdomains aus | gepflegte Wortliste (wie die Rauschmuster in `ct_domains.yaml`) | degradiert heute schon sauber: bei Fehler bleibt alles als „unbewertet" drin. Kleinster Posten (1 Call/Lauf) |
| Promo-Score `judge_offers` | Belegachse für strittige Angebote | Achse weglassen/deckeln — Composite steht ohne sie | Score etwas gröber; Reihenfolge der Blöcke hängt ohnehin am gepflegten `rang` |
| Kategorie-Sweep | filtert Brave-Suchtreffer gegroundet | abschalten (zweite Datenquelle NEBEN dem Crawl) | Differenzierungs-Seite verliert die Web-Funde, behält den Presse-Kurator |
| Beleg-Prüfung (`faithfulness`) | prüft die AUSSAGE des Folgerungssatzes | nicht ersetzen — fail closed ist die richtige Degradation: ohne Modell erscheinen schlicht keine Folgerungssätze | ein „nur Zahlencheck"-Ersatz ließe plausible falsche Folgerungen live gehen — laut Projektdoku das teuerste Risiko des Portals |

### Klasse C — echte Modellarbeit (Ersatz = Qualitätsbruch, nicht Ersparnis)

| Stufe | Warum ein Algorithmus das nicht kann |
|---|---|
| **Analyst** (Relevanz 1–5, Kategorie, deutsche Zusammenfassung, „warum interessant") | Der Analyst verwirft ~90 % (14.08.: 58 behalten aus 944). Ein Keyword-Filter kennt den Unterschied zwischen „AT&T launcht Tarif" und ESG-Boilerplate nicht — genau daran sind in Session 4 die maschinell „bestandenen" Quellen gescheitert. Und die deutsche Zusammenfassung IST Übersetzung + Urteil |
| **Editor / Prosabericht** | Das Herzstück laut §8. Der deterministische Digest existiert als ehrliche Notlösung und ist sichtbar das, was gerade live steht |
| **Promo-Extraktion** | Gemessen (11.08.): ld+json trägt im deutschen Telko-Handel keine Angebote; Preis-Regex-Wege sind im Projekt mehrfach als Rauschquelle belegt (drei Sicherungen allein für den Tarifseiten-Diff) |
| **Übersetzung** | Modellarbeit per Definition (allenfalls billigere MT-API, kein „Algorithmus") |
| Wettbewerber-Lage, Diff-/Promo-Redaktion, Themen-Agent | Prosa und Benennen/Verwerfen; die jeweiligen Rohdaten-Teile (Chronik, Karten, Kandidaten) sind schon Code |

---

## 3. Wo die Tokens wirklich liegen

Grobe Rangfolge je gesundem Lauf (Call-Zahlen aus dem 14.08.-Protokoll,
Budgets aus `settings.yaml`):

1. **Analysten-Stapel: 61 Calls** à Budget 16k — der mit Abstand größte Posten
2. **Clustering-Graubereichsprüfungen** (`cluster_max_llm_pruefungen: null` = ungedeckelt)
3. **Redaktion** (zweistufig ab 120 Meldungen: 14 Bereichsredakteure + Chefredaktion)
4. **Übersetzung** (3–5 Calls je Artikel, 10–25 Artikel)
5. CTM-Belegprüfung, Promo-Extraktion/-Score/-Redaktion, Sweep, Wettbewerber (3), Themen-Agent (1), CT-Radar (1)

Einordnung: Die großen Kostentreiber waren schon am 18.08. behoben
(Denkspur-Budgets, Mechanik-Stufen auf v4-flash, Cron aus der Pekinger
Stoßzeit). **Erwartete Kosten je gesunder Lauf: ~0,30–0,60 $.** Die
Klasse-B-Hebel sparen davon Bruchteile — der Nutzen eines Umbaus „Agent →
Algorithmus" ist in Cent messbar, das Risiko in Portalqualität. Vor jedem
Hebel gehört der **Kostenzähler je Stufe** gebaut (offener Punkt 3 aus dem
18.08.) — sonst ist jede Ersparnis geraten.

---

## 4. Premortem

*Es ist Mitte Oktober 2026. Der Umbau „weniger KI, mehr Algorithmen" ist
gescheitert, Antonio ist unzufrieden. Was ist passiert?*

1. **Die Startseite ist voller Boilerplate.** Der Keyword-Filter, der den
   Analysten ersetzen sollte, behält Pressemitteilungs-Rauschen, das der
   Analyst verworfen hätte. Das Alleinstellungsmerkmal des Portals — nur
   Relevantes, alles belegt — ist weg, und die Kollegin liest es nicht mehr.
2. **Der Meldungsbestand ist verbrannt.** Für die Bilder wurde der
   bestehende No-LLM-Zweig aktiviert. Der markiert ALLE neuen Meldungen als
   gesehen (`zu_merkende_meldungen` schützt nur ausgefallene Stapel, und
   ohne LLM fällt kein Stapel aus). Als das Guthaben wieder da war, gab es
   nichts mehr zu bewerten — das Frischefenster (8 Tage) war durch, die
   Berichte blieben wochenlang dünn, und im Protokoll sah alles normal aus.
3. **Dubletten oder Falschbündelungen auf der Titelseite.** Die
   Clustering-Modellprüfung wurde abgeschaltet, ohne vorher zu messen, wie
   viele Paare im Graubereich landen. Entweder stehen wieder zwei Varianten
   derselben Meldung auf Platz 2 und 5 — oder, schlimmer, zwei verschiedene
   Ereignisse wurden verschmolzen („eine falsche Verbindung ist schlimmer
   als keine").
4. **Englische und polnische Textfetzen auf einer deutschen Manager-Seite.**
   Die deutsche Zusammenfassung wurde durch den Roh-Teaser ersetzt.
   Zielgruppe laut §1: Manager OHNE Technik-Hintergrund, deutsch.
5. **Der SpaceX-Effekt ist zurück.** Relevanz wurde aus der Quellenzahl
   gerechnet („viel Echo = wichtig"). PR-verstärkte Themen schlagen
   exklusive Einzelquellen-Funde — genau die Verzerrung, gegen die der
   Absenderdeckel gebaut wurde, nur eine Ebene tiefer.
6. **Ein plausibler falscher Folgerungssatz stand zwei Wochen live.** Die
   Beleg-Prüfung wurde auf den Zahlencheck reduziert, „weil der Code das
   kann". Der Satz klang richtig, stand unter einem Quellenlink, und die
   Quelle gab ihn nicht her — das im Projekt ausdrücklich als teuerster
   Vertrauensverlust beschriebene Szenario.
7. **Die Promo-Seite zeigt veraltete Preise.** Die Extraktion lief per
   Regex; ein umgebautes Seitenlayout schob fremde Preise unter alte
   Etiketten. Der Stale-Preis ist genau das Risiko, weswegen die Seite
   Mechaniken statt Fixpreisen zeigt.
8. **Wochen Arbeit, Cents Ersparnis, keine Messung.** Es wurde umgebaut,
   bevor der Kostenzähler je Stufe existierte. Am Ende weiß niemand, was
   die Umbauten gespart haben — die Läufe kosteten vorher schon nur
   ~0,30–0,60 $.

Gegenmittel, aus dem Premortem rückwärts gelesen: (1) Analyst/Editor nicht
ersetzen; (2) jeder Seiten-Fallback braucht den Seen-Store-Schutz des
heutigen Kaputt-Pfads; (3) vor jedem Klasse-B-Hebel die betroffene Quote im
Protokoll messen; (4) fail closed bleibt fail closed; (5) zuerst den
Kostenzähler bauen.

---

## 5. Empfehlung, in Reihenfolge

1. **Der eine lohnende Umbau** (beantwortet exakt die Ausgangsbeobachtung):
   ein „Anbieter tot"-Fallback, der die Seite aus Unbewertet-Karten baut —
   Karten, Bilder, Ressorts da; Prosabericht ehrlich als Fallback markiert;
   Seen-Store bleibt geschützt, damit nach dem Aufladen alles nachbewertet
   wird. Kostet null Tokens und macht die Guthaben-leer-Wochen sichtbar
   statt leer.
2. **Kostenzähler je Stufe** (offen aus 18.08.) — die Voraussetzung für
   jede weitere Entscheidung.
3. **Danach, einzeln und gemessen, die Klasse-B-Hebel**: Deckel für die
   Clustering-Prüfung (`cluster_max_llm_pruefungen` ist heute ungedeckelt),
   CT-Wortliste, `judge_offers`-Deckel, Sweep-Schalter.
4. **Nicht anfassen:** Analyst, Editor, Promo-Extraktion, Beleg-Prüfung,
   Übersetzung.

Kein Code geändert; dieses Dokument ist der einzige Inhalt des Branches.
