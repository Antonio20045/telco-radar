## Kurzfassung

Der ergiebigste Fund ist Media Cloud (mediacloud.org): ein offenes, akademisch betriebenes Verzeichnis mit 25.000+ Nachrichtenquellen, das über eine kostenlose API abrufbar ist und pro Quelle tatsächlich RSS-/Sitemap-Feed-URLs mitliefert — genau das Datenformat, das die Pipeline braucht. GDELT liefert dagegen nur Domain-Listen ohne Feed-URLs und ist damit ein Filter/Cross-Check, kein direkter Kandidatenlieferant. Feedspot und OPML-Sammlungen (awesome-rss-feeds) sind von Hand kuratiert, klein, aber sofort mit Feed-URL nutzbar und gut für die Telko-Nische. Für dieses Projekt lohnt sich am ehesten Media Cloud als Vorfilter, der den Sucher direkt mit Domain+Feed-Paaren füttert, statt bei Null zu suchen — das beschleunigt nicht die Netz-Wanduhr (die Feeds müssen trotzdem einzeln geprüft werden), sondern spart die 40-Adressen-Rateversuche pro Firma.

## Befunde

**Media Cloud (mediacloud.org)** — offenes, gemeinnütziges Nachrichtenarchiv- und Quellenverzeichnis-Projekt, jetzt von einem Konsortium aus Media Ecosystems Analysis Group, UMass Amherst und Northeastern University betrieben (ursprünglich Harvard/MIT). Verzeichnis: **25.000+ Medienquellen, kuratierte Collections aus über 100 Ländern**, dazu ein Online-News-Archiv mit Milliarden Artikeln. Zugang über die Directory-API (Python-Client `mediacloud/api-client`, `DirectoryApi.source_list()`), kostenlos nach Registrierung/API-Key über search.mediacloud.org; die ältere v2-API dokumentierte ein Limit von 1.000 Calls / 20.000 Storys pro 7 Tagen, für die neue v4-API war das exakte Limit nicht auffindbar. Lizenz: Software ist GPLv3, Datenlizenz für die Directory-Inhalte nicht explizit dokumentiert. **Wichtig: Quellen haben laut Source-Guide zugeordnete Feeds** ("Sources have associated Feeds (RSS and Google News Sitemap)"). Aktiv, Doku zuletzt 2024 aktualisiert. [GEPRUEFT]

**GDELT Project** — Ereignis-/Medienmonitoring-Projekt, überwacht Nachrichten in 65 Sprachen live. Für Quellenerkennung relevant sind Cross-Reference-Dumps wie `DOMAINSBYCOUNTRY-ENGLISH.TXT` (13.155 englischsprachige Domains mit geschätztem Herkunftsland) und `DOMAINSBYCOUNTRY-ALLLANGUAGES.TXT`. Zugang: direkter Download unter data.gdeltproject.org/supportingdatasets/, keine API nötig, kostenlos. **Nur Domains, keine Feed-URLs.** Lizenz nirgends explizit genannt, die GKG-Rohdaten laufen unter Public-Domain-artiger Freigabe (GNU-GPL nur für den inoffiziellen Python-Client, nicht für die Daten selbst). Aktiv, GKG-Dateien werden täglich neu erzeugt; die Country-Lookup-Datei stammt aus 2021, neuere Version nicht gefunden. [GEPRUEFT]

**Feedspot Telecom-Verzeichnis** (rss.feedspot.com/telecom_rss_feeds) — von Hand kuratierte Liste, aktuell **70 Telecom-RSS-Feeds** in 12 Unterkategorien, plus separate Länderlisten (UK, Kanada, Indien/ET Telecom, 5G-Technologie). Enthält teils direkte Feed-URLs (z. B. RCR Wireless via Feedburner), teils nur Website-Links ohne Feed. Kostenlos browsbar; ein Volltextexport bzw. die "250k Bloggers/Publications"-Datenbank ist Teil eines kostenpflichtigen Media-Contact-Produkts. Keine erkennbare API, nur HTML-Scraping möglich. [GEPRUEFT]

**awesome-rss-feeds / OPML-Sammlungen** (github.com/plenaryapp/awesome-rss-feeds und Ableger wie tuan3w/awesome-tech-rss) — von Entwicklern gepflegte, CC0-lizenzierte OPML-Dateien mit ca. 500+ kuratierten Feeds, überwiegend allgemeine Tech-/Business-Kategorien, **keine dedizierte Telko-Kategorie**. Direkt als Datei im Repo abrufbar, sofort mit Feed-URL nutzbar, aber klein und generisch — Mehrwert für dieses Projekt gering. [GEPRUEFT]

**NewsCatcher** — kommerzielle News-API, wirbt mit **150.000+ Quellen in 50+ Sprachen/200+ Ländern**. Kein öffentliches Quellenverzeichnis zum Download, nur Abfrage über die kostenpflichtige API (ab ca. 29 $/Monat, Enterprise deutlich teurer); Trial-Key vorhanden. Für Massenextraktion einer Domain/Feed-Liste ungeeignet, da nicht als Bulk-Export gedacht. [GEPRUEFT]

**Common Crawl News (CC-NEWS)** — tägliche WARC-Rohdaten von Nachrichtenseiten seit 2016, gehostet auf AWS Open Data (S3, kostenlos, ohne AWS-Kosten für Abruf aus der Region). **Keine fertige Domain- oder Feed-Liste** — man müsste WARC-Dateien selbst parsen, um Domains zu extrahieren; ein einzelner Monatscrawl enthält laut Community-Angaben ca. 2.700–2.800 Domains. Lizenz nicht explizit auf der Seite, generell Common-Crawl-Nutzungsbedingungen (Weiterverwendung frei, Zuschreibung erwünscht). Für dieses Projekt nur als aufwendiger Umweg brauchbar. [GEPRUEFT]

**OpenSources/FakeNewsCorpus, CLEF/NewsIR, Muck Rack/Cision** — alle drei geprüft und verworfen: OpenSources klassifiziert Domains nach Glaubwürdigkeit (kein Feed-Bezug, Fokus Falschinformation), CLEF/NewsIR ist ein statischer Forschungskorpus von 2016 ohne aktuelle Feed-Liste, Muck Rack/Cision sind PR-Journalistendatenbanken ab 3.000–34.000 $/Jahr mit Kontaktdaten statt Feed-URLs. [UNGEPRUEFT bei CLEF/OpenSources direkt, GEPRUEFT bei Muck Rack/Cision-Preisseiten via Suchergebnis]

## Was das für dieses Projekt bedeutet

Media Cloud ist der einzige Fund mit echten Feed-URLs im großen Maßstab und passt direkt in die bestehende Pipeline: Statt `finde_quellen.py` bei Null starten zu lassen, könnte ein einmaliger Directory-Abruf (per Land-/Themen-Collection) eine Liste aus Domain+Feed-URL liefern, die man direkt in `pruefe_quellenvorschlag.py` einspeist — das spart die 40-Adressen-Rateversuche, nicht aber den Abnahme-Check oder die 154-von-234-Handarbeit, die an der inhaltlichen Wertung hängt, nicht an der URL-Suche. GDELT und Feedspot taugen als Ergänzung für die Länder-/Themenabdeckung, aber nur als Domain-Hinweis, nicht als Feed-Quelle. Nächster Schritt: einen Test-Directory-Abruf für 2–3 Länder-Collections machen und die zurückgegebenen Feed-URLs stichprobenartig durch `pruefe_quellenvorschlag.py` schicken, um die reale Trefferquote gegen die bisherigen 234/1362 zu vergleichen.

## Fallstricke

Media Clouds Rate Limit (alte API: 1.000 Calls/7 Tage) würde bei einer Massenabfrage aller Collections schnell greifen — Kontingent vorher klären. GDELT liefert nur Domains, keine Feeds: die "Ausbeute" wäre wieder ein Sucherlauf, kein direkter Zugewinn. Common Crawl erfordert WARC-Parsing (schwergewichtig, für 285→1000 Quellen unverhältnismäßig). Feedspot-Listen sind handkuratiert und teils veraltet (Feeds können längst tot sein, ungeprüft übernommen würde die Fehlerquote der Abnahme-Kriterien treiben). Bei allen Verzeichnissen gilt dasselbe Muster wie bei den bisherigen 1362 Kandidaten: **Form-Check ersetzt keine Wertprüfung** — auch ein Media-Cloud-Eintrag mit Feed-URL kann Boilerplate oder ein toter Feed sein und muss durch denselben neunkriterigen Check laufen wie jeder andere Vorschlag.

---

## Kurzfassung

Wikidata-SPARQL liefert für Telko-**Unternehmen** brauchbare, sofort maschinell abrufbare Listen mit Ländern und offiziellen Websites — ich habe das mit echten Live-Abfragen gegen query.wikidata.org nachgemessen, nicht nur behauptet. Für **Regulierungsbehörden** und **Fachpresse**, also genau die zwei Kategorien, die laut Projekt-Handover den höchsten Wert je Suchauftrag bringen, existiert dagegen keine saubere, durchsuchbare Wikidata-Klasse — meine Testabfragen dafür liefen ins Leere. Das Verfahren würde also einen Teil der Recherche ersetzen (Firmen+Domain-Listen), aber nicht den teuren Rest (Regulierer, Fachtitel, Wertprüfung).

## Befunde

**Wikidata Query Service / query.wikidata.org** [GEPRUEFT] — Der offizielle SPARQL-Endpunkt. Ich habe live abgefragt: `?item wdt:P31/wdt:P279* wd:Q2401749` (Klasse „telecommunication company") liefert **1111** Treffer; mit zusätzlichem `wdt:P856` (offizielle Website) UND `wdt:P17` (Land) sinkt das auf **799** (72 %). Für die enger gefasste Klasse `wd:Q1941618` („mobile network operator", P31 direkt statt rekursiv) sind es nur **80** Treffer, davon **71** mit P856 (89 %) — die meisten realen Mobilfunkbetreiber sind in Wikidata aber schlicht als „company"/„business" getypt, nicht als MNO, sodass die enge Klasse die meisten verpasst und man auf die breite Firmenklasse plus Branchenfilter (P452) ausweichen muss. Kostenlos, kein Login. Rate Limits laut Wikimedia-Mailingliste-Thread [GEPRUEFT]: 60 s Query-Zeit pro Minute (Burst 120 s), max. 30 Fehler/Minute (Burst 60), Durchsetzung über IP+User-Agent-Kombination, bei Ignorieren von HTTP 429 folgt ein längerer 403-Bann. Exakter Timeout-Wert einer Einzelabfrage in Sekunden ließ sich auf der offiziellen Limits-Seite nicht verifizieren [UNGEPRUEFT] — praktisch beobachtet: einfache COUNT-Abfragen liefen in 1–3 s durch.

**Regulierungsbehörden als Wikidata-Klasse** [GEPRUEFT, Negativbefund] — Es gibt **keine** funktionierende Klasse. `Q7695862` („Telecommunications Regulatory Authority") ist laut eigenem P31 eine „Wikimedia disambiguation page", keine Klasse — Query darauf liefert 0. Ein Versuch über `Q1639780` (regulatory agency, subclass-rekursiv) kombiniert mit P452=Telekommunikation lieferte ebenfalls **0**. Jedes Land hat stattdessen ein eigenes, unverbundenes Item (Q9367280, Q25494062, Q5954934, Q6738599 …) ohne gemeinsame Oberklasse, die man in einer Abfrage fassen könnte. Maschinelles Ziehen scheitert hier strukturell.

**Fachpresse/Trade-Press als Wikidata-Klasse** [GEPRUEFT, Negativbefund] — `Q685935` (trade magazine) existiert, aber die Verknüpfung über P921 (main subject) mit einem Telekommunikations-Thema lief mit der naheliegenden QID ins Leere (falsche QID traf eine gallische Stammes-Konföderation, nicht „Telekommunikation" als Thema — Wikidata-QIDs sind nicht intuitiv erratbar, jede muss einzeln verifiziert werden). Ohne saubere Themenverknüpfung bräuchte man Volltextfilter über Magazin-Titel, was wieder Handarbeit ist.

**QLever (qlever.dev/wikidata)** [GEPRUEFT] — Alternativer öffentlicher SPARQL-Endpunkt derselben Wikidata-Daten, Uni Freiburg, andere Engine (kein Blazegraph), Standard-Zeilenlimit 100 in der Web-UI, per API mehr. Kostenlos. Als Fallback bei WDQS-Throttling geeignet.

**DBpedia SPARQL (dbpedia.org/sparql)** [GEPRUEFT] — Lebt, Virtuoso-Backend, `dbo:Company` allein liefert **276464** Treffer (ungefiltert, nicht telko-spezifisch) — zeigt nur, dass der Dienst online ist, keine spezifische Telco-Klasse getestet. Datenbasis ist der ältere, gröber typisierte DBpedia-Infobox-Extrakt, für Telko-Feineingrenzung schwächer als Wikidata direkt.

**Wikipedia-Listenartikel** (z. B. „List of mobile network operators of Europe") [GEPRUEFT] — Enthält Wikitables je Land mit Spalten Rang/Operator/Technologie/Abonnenten/Eigentümer/MCC-MNC. Operatorname verlinkt aber nur zum **Wikipedia-Artikel**, nicht zur offiziellen Website — man braucht einen zweiten Schritt (Wikidata-Sitelink des Artikels → P856) oder das Infobox-Feld „website" im Artikel selbst. Kein direktes Firmenverzeichnis mit URL.

**WDumper / wdumps.toolforge.org** [GEPRUEFT] — Lebt, erzeugt gefilterte Custom-RDF-Dumps aus dem kompletten Wikidata-JSON-Dump nach eigener Filterdatei. Kostenlos (Toolforge). Für einmalige Massenextraktion sinnvoller als tausend Einzelqueries, aber Overkill für 1000-Zeilen-Bedarf.

**qwikidata (PyPI/GitHub, kensho-technologies)** [TEILWEISE GEPRUEFT] — Python-Wrapper für Entities, SPARQL und Dumps existiert, Apache-2.0-Lizenz bestätigt über PyPI-Suche. Aktualität/letzter Commit ließ sich per WebFetch nicht sicher lesen [UNGEPRUEFT] — vor Einsatz Commit-Historie selbst prüfen.

## Was das fuer dieses Projekt bedeutet

Für die **Firmen+Domain-Liste** würde es die 4,2 Firmen/Minute massiv beschleunigen: eine einzige SPARQL-Abfrage liefert in Sekunden ~800 Telko-Firmen mit Land und offizieller Website, ohne die 40-Adressen-Try-Schleife pro Firma. Es würde aber die **Handarbeit nicht reduzieren** — P856 zeigt oft auf die Konzern-Startseite, nicht auf den Newsroom/Feed, der Abnahme-Check mit den 9 Kriterien bleibt also Pflicht. Für Regulierer und Fachpresse, die laut eigener Lehre die ergiebigste Quellenkategorie sind, hilft Wikidata praktisch nicht. Nächster Schritt: eine SPARQL-Abfrage nach Q2401749-Subklasse + P856 + P17 gegen die bestehende Watchlist abgleichen (Domain-Duplikate raus), Ergebnis als neue P856-Domainliste in `finde_quellen.py` einspeisen statt als LLM-Recherche.

## Fallstricke

QID-Raten ist gefährlich — eine falsch geratene ID (wie oben bei P921) liefert 0 statt Fehler, wirkt aber wie ein valider Negativbefund. `COUNT(?item)` ohne `DISTINCT` zählt bei mehrwertigen Properties (mehrere P856-Werte) Zeilen statt Entitäten und täuscht höhere Trefferzahlen vor — mir selbst passiert, 80 vs. „88" bei P856-Join. P856 ist oft veraltet oder zeigt auf tote Domains (nicht geprüft, nur als bekanntes Wikidata-Problem zu nennen). Ohne User-Agent-Header droht Bann des Endpunkts. Massenabfragen brauchen Backoff wegen des 60-s/Minute-Zeitbudgets.

---

## Kurzfassung

Kein kommerzieller Anbieter liefert das, was Telco Radar eigentlich braucht: eine downloadbare Liste von RSS-/Newsroom-URLs je Fachpresse-Branche. Die News-APIs (NewsAPI.org, Event Registry, Webz.io, NewsCatcher, Perigon, Newsdata.io, GNews) verkaufen Artikelzugriff über ihre eigene Such-API, nicht Quellcode-Feeds — man würde die Website selbst crawlen weiter aufgeben und stattdessen deren aggregierten Content abonnieren, meist mit Lizenzauflagen gegen Weiterverwendung/Caching. Die einzigen Anbieter mit echtem "Verzeichnis exportieren"-Feature sind PR-Mediendatenbanken (Muck Rack, Cision) — die kosten 5.000–50.000 $/Jahr und liefern Journalisten-/Outlet-Kontakte, keine RSS-Endpunkte. Für ein Projekt, das kostenlos bleiben muss, taugt praktisch keiner der geprüften Dienste als Ersatz für den bestehenden Crawl-Ansatz; allenfalls die `/sources`-Endpunkte von NewsAPI.org/NewsCatcher könnten als einmalige Kandidatenliste (Name+Homepage, keine RSS-URL) den LLM-Websearch-Schritt ergänzen.

## Befunde

**NewsAPI.org** [GEPRUEFT] – Artikel-Suche über 150.000+ Quellen, `/sources`-Endpunkt liefert id/name/description/**Homepage-URL** (keine RSS-URL), filterbar nach Land/Sprache/Kategorie. Preise: Developer kostenlos (nur localhost, 100 Req/Tag, 24h-Verzögerung), Business 449 $/Monat, Advanced 1.749 $/Monat, Enterprise custom mit "extended source library". ToS untersagt Weiterveröffentlichung von Volltext, nur Titel/Beschreibung/URL erlaubt; Redistribution nur im Enterprise-Plan case-by-case. https://newsapi.org/pricing, https://newsapi.org/docs/endpoints/sources.

**Event Registry / NewsAPI.ai** [GEPRUEFT] – über 150.000 Quellen, 30.000+ Verlage, 60+ Sprachen. Token-basiert: Free 2.000 Tokens/Monat, 5K-Plan ab 90 $/Monat, 500 $/Monat für 50k Ergebnisse. Historische Daten seit 2014. https://newsapi.ai/plans.

**Webz.io** [GEPRUEFT] – "Millionen" Quellen (News, Blogs, Foren, Deep/Dark Web), 3,5 Mio. Artikel/Tag, 170+ Sprachen, 200+ Länder. Keine öffentliche Preisliste, nur Sales-Kontakt; Self-Service-Tool zum Beantragen zusätzlicher Quellen erwähnt, aber kein Bulk-Export eines Quellverzeichnisses dokumentiert. https://webz.io/products/news-api/.

**Diffbot Knowledge Graph** [GEPRUEFT] – kein News-API im engeren Sinn, sondern Web-Extraktion + Entitäts-Graph (>10 Mrd. Entitäten, angeblich 50x mehr Artikel als der Google-News-Index). Free 10.000 Credits, Startup 299 $/Monat (250.000 Credits), Plus 899 $/Monat. Export eines Entity-Records kostet 25 Credits — theoretisch könnte man Organisationsdaten (inkl. Homepage) bulk exportieren, aber keine RSS-Feed-Zuordnung erkennbar. https://www.diffbot.com/pricing/.

**NewsCatcher** [GEPRUEFT] – 90.000–140.000+ indexierte Quellen laut eigenen Angaben (Zahl schwankt je Seite). `/sources`-Endpunkt liefert Sprache/Land/Name/**URL** je Outlet, filterbar. Preise: Individual PAYG, Starter 50 $/Monat + 6.000 Credits, Scale 500 $/Monat + 60.000 Credits, Produktion nur ab Enterprise (custom). https://www.newscatcherapi.com/pricing.

**Bing News Search API** [GEPRUEFT] – **eingestellt am 11.8.2025**, komplett zusammen mit allen Bing-Search-APIs. Microsofts Ersatzempfehlung ist "Grounding with Bing Search" über Azure AI Agents (kein reiner Such-Endpunkt mehr, Kosten laut Presseberichten 40–483 % höher). Existiert für dieses Projekt nicht mehr. https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement.

**Google News/Programmable Search** [UNGEPRUEFT, per Suchergebnisse] – die dedizierte Google News API wurde bereits 2016 abgeschaltet; die Custom-Search-JSON-API (der einzige verbliebene Weg) wird zum 1.1.2027 komplett eingestellt, 5 $/1.000 Anfragen, 10.000/Tag Deckel. Für ein Langfrist-Projekt kein tragfähiger Baustein.

**Meltwater** [UNGEPRUEFT] – Enterprise-Medienmonitoring, keine öffentliche Preisliste, Marktschätzungen ~15.000–40.000 $/Jahr. Mediendatenbank als separates Zusatzmodul.

**Cision** [UNGEPRUEFT] – Media-Contacts-Datenbank, 500.000+ Profile in 225 Ländern, **Export von Outlet-Listen nach Beat/Branche explizit als Feature** genannt. Preise ~7.200–25.000+ $/Jahr für 1–5 Sitze. Zielgruppe PR-Teams (Journalistenkontakte), nicht Feed-URLs.

**Muck Rack** [UNGEPRUEFT, Fetch der Hilfeseite mit 403 blockiert] – hat laut Hilfe-Center-Titel eine Funktion "Export Outlet Lists" (Excel/PDF), Suche nach Branche/Beat über "Outlet Rankings". Preise laut Marktschätzungen 5.000 $ (Einstieg) bis 50.000+ $/Jahr (Enterprise), nur Jahresverträge. Das ist der einzige Fund, der wörtlich "Verzeichnis exportieren" anbietet — aber als Journalisten-/PR-Werkzeug, nicht als RSS-Quellenliste.

**Aylien / Quantexa** [UNGEPRUEFT] – seit Februar 2023 Teil von Quantexa (Decision-Intelligence-Plattform), News-API mit 80.000+ Quellen, mehrsprachig. Keine öffentliche Preisliste mehr gefunden, wirkt heute auf Enterprise-Risk-Intelligence-Kunden ausgerichtet, nicht auf einzelne Entwickler.

**Perigon** [GEPRUEFT] – ~200.000 Quellen laut eigener Angabe. Free 150 Req/Monat (nur privat), Basic 250 $/Monat (eingeschränkt kommerziell), Plus 550 $/Monat, Commercial ab 24.000 $/Jahr für volle kommerzielle Lizenz. https://perigon.io/products/pricing/apis.

**Newsdata.io** [UNGEPRUEFT] – 84.675+ Quellen laut Eigenangabe, 89 Sprachen, Basic 199,99 $/Monat (20.000 Credits).

**GNews.io** [GEPRUEFT] – kleiner Anbieter, keine Quellenzahl genannt. Free 0 €/Monat (nicht-kommerziell, 12h-Verzögerung), Essential 49,99 €/Monat, Business 99,99 €/Monat, Enterprise 249,99 €/Monat. https://gnews.io/pricing.

## Was das für dieses Projekt bedeutet

Keine dieser APIs beschleunigt die 4,2 Firmen/Minute-Grenze, weil die Grenze bei der eigenen RSS-Feed-*Entdeckung* liegt und keiner der Dienste RSS-URLs herausgibt — man würde stattdessen den gesamten Collector durch Vendor-API-Calls ersetzen, was Kosten (mindestens 90–500 $/Monat für brauchbare Kontingente) und Lizenzrisiken (Redistributions- und Cache-Verbote) gegen "kostenlos bleiben" stellt. Die Handarbeit bei der Wertprüfung würde eher wachsen, nicht schrumpfen: die gelieferten "Quellen" sind bereits aggregierte Artikel, kein Rohmaterial für den Abnahme-Check. Der einzig sinnvolle nächste Schritt: den kostenlosen `/sources`-Endpunkt von NewsAPI.org (Developer-Tier reicht für einmaligen Abruf) einmalig als **Namens-/Domain-Kandidatenliste** in `config/kandidaten_firmen.yaml` einspeisen statt weiter LLM-Websuche zu betreiben — der bestehende Crawl-Pfad bleibt unverändert.

## Fallstricke

Fast alle "kostenlosen" Tiers verbieten kommerzielle Nutzung explizit (GNews, Perigon Free) — ein Vodafone-Wettbewerbsbericht zählt vermutlich als kommerziell, selbst ohne Weiterverkauf. Quellenzahlen sind Marketingzahlen ohne geprüfte Methodik (NewsCatcher nennt 90.000 und 140.000 auf verschiedenen eigenen Seiten). `/sources`-Endpunkte liefern Homepage-, nie RSS-URLs — man bräuchte trotzdem den eigenen Feed-Finder. Bing News Search und die alte Google News API sind tot; wer sie in einem Tutorial von 2023 findet, testet gegen ein abgeschaltetes Produkt. Cision/Muck Rack sind PR-Journalistendatenbanken — ihre Lizenz erlaubt typischerweise kein Bulk-Scraping der Outlet-Liste für einen automatisierten Crawler, nur manuelle PR-Listenerstellung.

---

## Kurzfassung

Fertige Feed-Verzeichnisse ersetzen die Websuche nach Firmennamen nicht, sondern zwei andere Schritte: das Erraten der Feed-URL pro Domain und die manuelle Recherche nach Fachpresse-Titeln. Der einzige geprüfte Fund, der direkt in die Pipeline passt, ist **Feedsearch (feedsearch.dev / feedsearch-crawler)** — eine kostenlose, offen lizenzierte, noch aktive API, die pro Domain alle auffindbaren Feeds samt Metadaten liefert und im Test gegen `telekom.com` sechs echte Feeds fand (u. a. eine „Netz"-Rubrik), ohne die ~40 URL-Muster selbst durchzuprobieren. Alle „Firmen-API"-Kandidaten (Feedly, Inoreader, NewsBlur, Feedbin) sind entweder kostenpflichtig/Enterprise-only, dienen nur der Verwaltung eigener Abos statt einer offenen Themensuche, oder haben keinen öffentlichen Discovery-Endpunkt. Feedspot-Listen sind als Startpunkt für Fachpresse brauchbar, aber Handarbeit und rechtlich nur zum Ablesen einzelner URLs, nicht zum Massen-Scraping. Der Zeitgewinn liegt bei Faktor 2–5 auf den Erratungs-Schritt, nicht bei der Wertprüfung — die bleibt Handarbeit.

## Befunde

**Feedsearch / feedsearch.dev** [GEPRUEFT] — API + zugrunde liegende Python-Bibliothek `feedsearch-crawler`, die eine Domain nach RSS/Atom/JSON-Feeds durchsucht (rel=alternate, WordPress-REST, Podcast-Feeds, gecachte Historie). Live getestet: `GET https://feedsearch.dev/api/v1/search?url=<domain>` lieferte ohne API-Key sowohl für `stackoverflow.blog` (1 Feed, korrekt) als auch für `telekom.com` (6 Feeds inkl. „Netz"-Rubrik und EN/DE-Pressemitteilungen, mit `item_count`, `last_updated`, `velocity`-Score) saubere JSON-Antworten. Kein sichtbares Auth/Rate-Limit im Test (Cloudflare-CDN, `cache-control: max-age=604800`). Lizenz des Codes: MIT (`DBeath/feedsearch-crawler`, 160 Commits, 2 offene Issues — moderat aktiv, kein totes Projekt). Kosten: kostenlos, kein Key nötig; Selbst-Hosting der Bibliothek ebenfalls möglich und MIT-lizenziert weiterverwendbar.

**Feedly Cloud API** [GEPRUEFT] — `POST v3/search/feeds` sucht Feeds nach Titel/URL/`#topic`; existiert laut Doku, aber die produktive API-Nutzung (inkl. Search) hängt an einem OAuth-Token, dessen Self-Service-Seite für „Threat Intelligence"-Kunden gedacht ist. Rate-Limit laut `reference/request-limits`: 100 000 Requests/Monat pro Token — aber ohne erkennbaren kostenlosen Zugang; API-Zugriff wird laut Preisrecherche erst ab den Enterprise-Tiers „Market/Threat Intelligence" ($1 600–3 200/Monat) genannt. Für ein Gratis-Projekt praktisch nicht nutzbar.

**Inoreader API** [GEPRUEFT] — Entwicklerportal existiert, REST-Basis `reader/api/0`, AppId/AppKey + OAuth. Es gibt eine nutzerseitige Volltextsuche über indizierte öffentliche Feeds, aber keinen dokumentierten offenen „Suche Feeds zu Thema X"-Endpunkt für Dritte ohne bestehendes Konto/Abo.

**NewsBlur API** [GEPRUEFT] — `GET /rss_feeds/feed_autocomplete` liefert Feeds zu einer Phrase, offen erreichbar. Einschränkung: Volltextsuche in Feeds ist Premium-only; Autocomplete selbst wirkt eher für Interface-Zwecke gedacht (Titelabgleich), nicht als Massenexport-Werkzeug.

**Feedbin API** [GEPRUEFT] — Dokumentiert nur Endpunkte für die eigenen Abos (Subscriptions, Entries, Saved Searches), kein öffentlicher Discovery-/Suchendpunkt für fremde Feeds.

**The Old Reader API** [GEPRUEFT] — Google-Reader-Nachbau, verwaltet ausschließlich das eigene Konto (Abos anlegen/lesen), keine Themen- oder Domainsuche über einen fremden Index.

**Feedspot-Listen** (z. B. „Top 70 Telecom RSS Feeds") [GEPRUEFT] — Kuratierte HTML-Liste, 70 Einträge mit Klartext-Feed-URLs geprüft (u. a. RCR Wireless, Total Telecom, CircleID, Deutsche Telekom Blog). Viele Einträge sind alt/generisch (mehrere FeedBurner-Links, teils Kanzlei-/Anwaltsblogs statt Betreiber-News) — Qualität durchwachsen, Aktualität nicht verifizierbar. ToS (`feeds.feedspot.com/fs/terms`) erlaubt Crawlen gemäß robots.txt, verbietet aber „Scraping ohne Zustimmung" und die Weitergabe von Feedspot-„Daten" an Dritte über aggregierte Analysen hinaus — einzelne öffentliche URLs von Hand abzulesen ist rechtlich unkritisch, ein automatisierter Bulk-Export der Liste nicht.

**awesome-rss-feeds (plenaryapp)** [GEPRUEFT] — GitHub-OPML-Sammlung, ~750 Feeds (250 Länderquellen + 500 „recommended"), Lizenz **CC0-1.0** (gemeinfrei, uneingeschränkt übernehmbar). Keine eigene Telecom-Kategorie, Quellen wirken allgemein-newslastig, keine dokumentierte Prüfmethodik.

**RSSHub** [GEPRUEFT] — 900+ eingebaute + 5000+ Community-Routen, AGPL-3.0, 45,6k Stars, sehr aktiv (17 357 Commits). Fokus liegt auf Social-Media-/Plattform-Feeds (Twitter, TikTok, Weibo, YouTube …), keine erkennbaren Telco-Newsroom-Routen. AGPL-3.0 bedeutet: eigenes Hosting mit Copyleft-Pflichten, falls man den Code verändert und weiterverbreitet.

**RSS-Bridge** [GEPRUEFT] — 400+ „Bridges", die Feeds für Seiten ohne eigenen Feed generieren. Code Public Domain (Third-Party-Libs mit eigener Lizenz). Selbst hostbar, PHP.

**openrss.org** [GEPRUEFT] — Gemeinnütziger Dienst (501(c)(3)), generiert on-the-fly Feeds für beliebige URLs, kostenlos, aber hart begrenzt auf 4–10 Items je Feed — für ein Frischefenster-System mit Interleaving zu wenig Tiefe.

**RSS.app** [GEPRUEFT] — Kommerzieller Feed-Generator, Free-Tier nur 2 Feeds/24h-Refresh, „Developer"-Tier mit API-Zugriff erst ab $16,64/Monat (100 Feeds) — für 700+ zusätzliche Quellen unbezahlbar in dieser Größenordnung.

## Was das fuer dieses Projekt bedeutet

Feedsearch würde den Erratungs-Schritt (die ~40 URL-Muster) durch einen einzigen API-Call ersetzen — das beschleunigt die 4,2-Firmen/Minute-Grenze spürbar, weil ein Server pro Domain nur noch von Feedsearchs Infrastruktur statt vom eigenen Netz-Client abgeklopft wird (Höflichkeits-Timeout entfällt für den eigenen Runner). Die Handarbeit bei der Wertprüfung wird dadurch NICHT reduziert — Feedsearch liefert Kandidaten, keine Bewertung; jeder Treffer muss weiterhin durch `pruefe_quellenvorschlag.py` (9 Kriterien) und die manuelle Wertprüfung laufen. Nächster Schritt: `scripts/finde_quellen.py` um eine Feedsearch-Stufe vor der eigenen 40-URL-Heuristik ergänzen und gegen die frische Firmenliste aus Welle 3 laufen lassen.

## Fallstricke

Feedly/Inoreader/NewsBlur/Feedbin sind für dieses Gratis-Projekt keine Option — entweder kein offener Such-Endpunkt oder Enterprise-Preise. Feedspot-Listen dürfen nicht automatisiert als Ganzes abgegriffen werden (ToS-Verstoß „Scraping"), nur einzelne URLs manuell übernehmen. RSSHub/RSS-Bridge lösen ein anderes Problem (Feed für Seite OHNE Feed erzeugen) und sind für Telco-Newsrooms kaum vorkonfiguriert — würde eigene Bridge-Entwicklung bedeuten, kein Zeitgewinn. Feedsearch selbst ist ein Ein-Personen-Projekt mit nur 160 Commits und 2 offenen Issues — kein SLA, keine garantierte Verfügbarkeit, sollte wie jede externe Quelle mit Timeout/Fallback behandelt werden, nicht als Kernabhängigkeit. Bing/Google News APIs sind tot (Bing seit 11.08.2025 abgeschaltet) — ein Hinweis, dass in diesem Feld Dienste schnell verschwinden; jede neu eingebaute Abhängigkeit sollte denselben Abnahme-Check durchlaufen wie ein Firmenvorschlag.

---

## Kurzfassung

Der einzige Fund mit echtem Hebel ist die **Common-Crawl-Columnar-Index-Abfrage über Athena**: eine SQL-Regex-Suche über `url_path` nach `newsroom`/`press-release`/`pressemitteilungen` liefert in Sekunden bis Minuten tausende Domains, die genau dieses Pfadmuster bereits ausgeliefert haben — für ein bis fünf Dollar pro Abfrage. Alles andere in diesem Themenfeld löst das eigentliche Problem des Projekts nicht: Certificate-Transparency-Logs und Passive-DNS brauchen bereits einen bekannten Domainnamen (helfen also erst NACH der Firmenliste, nicht bei ihrer Erstellung), Rapid7 Sonar ist seit 2022 kommerziell gesperrt, und Domain-Ranglisten wie Tranco/Cloudflare Radar/Majestic liefern zwar massenhaft Domains, aber ohne Branchenfilter — sie ersetzen die Sonnet-Recherche nicht, sie liefern höchstens Rohmaterial für sie. Für die 4,2-Firmen/Minute-Bremse (Höflichkeit gegenüber dem Zielserver) ändert nichts hier etwas, weil diese Bremse beim SPÄTEREN Abruf der gefundenen Feeds greift, nicht bei der Domain-Findung.

## Befunde

**Common Crawl Columnar Index (cc-index) [GEPRÜFT]** — Parquet-Index über alle URLs eines monatlichen Crawls unter `s3://commoncrawl/cc-index/table/cc-main/warc/`, abfragbar per AWS Athena/Trino. Ein Monatscrawl umfasst rund 300 GB Indexdaten; Athena berechnet $5/TB gescannter Daten, eine gezielte Pfad-Regex-Abfrage (`regexp_extract_all(url_path, ...)`) mit Partitionsfilter auf `crawl`/`subset` scannt oft nur MB bis wenige GB und kostet Cent-Beträge, eine ungefilterte Volltextsuche über einen ganzen Monat kann in den einstelligen Dollarbereich gehen. Läuft in Sekunden bis wenigen Minuten. Lizenz: Common Crawl Nutzungsbedingungen (frei, Attribution empfohlen). Sehr aktiv gepflegt (`commoncrawl/cc-index-table` auf GitHub, aktuelle Crawls monatlich). Braucht einen AWS-Account mit Zahlungsmethode — nicht literarisch kostenlos, aber im Cent- bis niedrigen Dollarbereich pro Abfrage.

**cdx-toolkit [GEPRÜFT]** — Python-Bibliothek/CLI (`pip install cdx_toolkit`, `commoncrawl/cdx_toolkit`), die die CDX-API von Common Crawl UND dem Internet Archive vereinheitlicht, monatliche Indizes zu einem virtuellen Gesamtindex verknüpft. Kostenlos, Open Source, aktiv gepflegt. Für URL-Pfad-Muster reicht es aber nur, wenn man den Host schon kennt — es ist kein Analog zu einer Athena-Volltextsuche über alle Hosts, sondern eine Abfrage je bekannter Domain (deutlich langsamer als Athena für „alle Hosts mit /newsroom finden").

**Common Crawl Host-Level Webgraph [UNGEPRÜFT, nur Suchtreffer]** — separate, kleine Datei (wenige GB gepackt) unter `s3://commoncrawl/projects/hyperlinkgraph/.../host/`: alle rund 490 Millionen Host-/Domainnamen, die ein Crawl gesehen hat, in umgekehrter Notation (`com.example.subdomain`). Kein SQL nötig, einfach herunterladen und lokal mit `grep`/`zgrep` nach Mustern wie `.telecom.` oder `newsroom.` durchsuchen — kostenlos, kein Athena-Query-Preis. Deckt aber nur Hostnamen ab, keine Pfade.

**crt.sh (Certificate-Transparency-Suche) [GEPRÜFT]** — Web-/JSON-API (`crt.sh/?q=%.domain.com&output=json`) über eine PostgreSQL-Datenbank aller ausgestellten TLS-Zertifikate; deckt effektiv jede öffentlich erreichbare Domain ab, da praktisch alle Browser TLS+CT erzwingen. Kostenlos, kein API-Key. Aber: Rate-Limit von 5 Requests/Minute pro IP, Direktzugriff auf die eigene PostgreSQL-Instanz (Port 5432) ist ebenfalls auf 5 gleichzeitige Verbindungen begrenzt und leidet unter Statement-Timeouts; der Dienst meldete bei meinem eigenen Test (06.08.2026) einen 502 Bad Gateway — Nutzer berichten in den offiziellen Google-Groups von hunderten täglichen 502/503/504-Fehlern durch stündliche Cron-Jobs auf der Masterdatenbank. Nützlich NUR, wenn man einen Domainnamen schon kennt (Subdomain-Enumeration `newsroom.vodafone.com`), nicht zur Neuentdeckung von Firmen.

**Certstream / CT-Log-Firehose [GEPRÜFT, aber unvollständig]** — Echtzeit-WebSocket-Stream aller neu ausgestellten Zertifikate (aktueller Server: `certstream-server-rust`, Nachfolger von CaliDogs Elixir-Server; `certstream.dev`-Doku beschreibt Selbst-Hosting, keine Aussage zu einer öffentlich gehosteten Instanz mit Kapazitätsangabe gefunden). Fängt nur NEU ausgestellte Zertifikate ab dem Zeitpunkt des Mitschnitts — die meisten Newsroom-Subdomains bestehender Firmen wurden längst zertifiziert und tauchen im Live-Stream nie wieder auf, außer bei Zertifikatserneuerung.

**Rapid7 Sonar/Open Data [GEPRÜFT]** — Internetweite Scan-Daten (FDNS, RDNS, HTTP, TLS-Zertifikate). Seit 10.02.2022 **kein freier Zugang mehr**, jetzt kommerziell mit Vetting-Prozess (Organisationsbeschreibung, Use Case, Mengenangabe an opendata@rapid7.com). Für dieses Projekt praktisch tot.

**Tranco / Cloudflare Radar / Majestic Million [GEPRÜFT: Tranco, Cloudflare; UNGEPRÜFT: Majestic]** — alle drei kostenlos als CSV/API abrufbar (Tranco `top-1m.csv.zip`, Cloudflare Radar Top-100 + Buckets bis 1 Mio, Majestic `downloads.majestic.com/majestic_million.csv`, alle täglich aktualisiert). Cloudflare Radar bietet Land- und grobe Kategoriefilter über die API (Bearer-Token nötig, kostenlose Stufe). Keine der drei kennt „Telekommunikationsanbieter" als Branche — sie ranken nach Popularität/Backlinks, nicht nach Sektor.

## Was das für dieses Projekt bedeutet

Es beschleunigt die **4,2 Firmen/Minute nicht** — die Bremse liegt beim Abruf der Feed-Kandidaten selbst, nicht bei der Domain-Findung. Es könnte aber die **Handarbeit bei der Kandidatenerzeugung** reduzieren: eine einmalige Athena-Abfrage über den Common-Crawl-Index mit Regex auf `url_path` nach `newsroom|press-release|pressemitteilung|news` liefert eine Liste von Domains, die dieses Muster nachweislich schon ausliefern — eine Vorfilterung, die vor dem 40-Pfade-Probe ansetzt und nur Domains durchlässt, die wahrscheinlich einen Treffer haben. Nächster Schritt: eine einzelne testweise Athena-Abfrage gegen den aktuellsten Crawl fahren (AWS-Account mit Kreditkarte nötig), Kosten und Trefferqualität an 20 bekannten Telcos aus der Watchlist prüfen, bevor man es in die Recherchephase einbaut.

## Fallstricke

Common Crawl crawlt bevorzugt populäre, gut verlinkte Domains — kleine regionale Betreiber (laut Welle 3 ohnehin die unergiebigste Kategorie) tauchen im Index oft gar nicht oder nur alle paar Monate auf; das Ergebnis ist also verzerrt zugunsten dessen, was man ohnehin schon kennt. crt.sh ist notorisch überlastet (502/503, Rate-Limit 5/min) und damit kein Ersatz für einen Massenlauf. Rapid7 Sonar ist seit 2022 zu; wer das aus altem Wissen zitiert, zitiert Falsches. Domain-Ranglisten ohne Branchenfilter erzeugen viel Rauschen, das erst wieder von Hand aussortiert werden muss — genau die 154-von-234-Verwurfsquote, die das Projekt schon hat.

---

## Kurzfassung

Der ergiebigste Weg fuer dieses Thema sind nicht die grossen kommerziellen Datenbanken (GSMA Intelligence, TeleGeography, Omdia), sondern zwei kostenlose, maschinell abfragbare Register: **PeeringDB** (Netzbetreiber mit Website-Feld, offene REST-API) und **nationale Regulierer-Verzeichnisse** wie das deutsche BNetzA-"Verzeichnis der gemeldeten Anbieter" (XLSX, alle Anbieter eines Landes). ITU-Register sind fuer Firmenwebsites praktisch nutzlos, weil sie Regulierer, nicht Betreiber, und meist als PDF/Umfragedaten statt strukturiert vorliegen. PeeringDB ist der groesste maschinenlesbare Pool (>35.000 Netz-Datensaetze), aber seine Nutzungsbedingungen verbieten ausdruecklich die Weiterverwendung in Produkten — das ist der zentrale Haken fuer dieses Projekt. RIR-Datenbanken (RIPE, ARIN) sind technisch offen, aber auf Netzbetreiber im engeren Sinn (AS-Inhaber) beschraenkt und enthalten viele Nicht-Telcos (Hosting, Enterprise, CDN).

## Befunde

**PeeringDB** [GEPRUEFT] — Freiwilliges Register von Netzbetreibern fuers Peering. `/api/net` liefert JSON mit Feldern `name`, `website`, `aka`, `asn`, `info_type` (NSP/Enterprise/Content/Route Server). Ich habe `https://www.peeringdb.com/api/net?limit=5` real abgerufen: die Website-URL ist ein eigenes Feld, sauber befuellt. Groessenordnung laut Suchtreffer (ISOC Pulse, Juli 2026, nicht direkt abrufbar wegen 403): **35.054 Netze** insgesamt, davon aber viele Enterprise/Content-Netze, keine reinen Telcos. Zugang kostenlos, kein Key noetig fuer Lesezugriff. **Lizenz ist die Bremse**: die AUP (laut Suchtreffer, nicht direkt gegengelesen) verbietet Weitergabe/Einbindung in Produkte ohne Erlaubnis von PeeringDB, "Internet operational purposes" ausgenommen. Reifegrad hoch, aktiv gepflegt.

**RIPE Database / RIPEstat** [GEPRUEFT] — REST-API unter `docs.db.ripe.net`, Objekttyp `organisation` per `type-filter=organisation` durchsuchbar, JSON/XML, Paging via `limit`/`offset`. RIPE NCC hat laut Suchtreffer knapp 20.000 Mitglieder (Stand Ende 2024) in der EMEA-Region — das sind LIRs (meist ISPs/Hoster), nicht spezifisch Telcos. Kein dediziertes Bulk-Export-Feature dokumentiert gefunden, nur Query-API mit Rate-Limits (403/429 bei Ueberschreitung). Kostenlos, offen.

**ARIN Bulk Whois / Whois-RWS** [UNGEPRUEFT, nur Suchtreffer] — Bulk-Download als ZIP/TXT/XML fuer die Nordamerika-Region, aber nur nach Antrag und ausdruecklich beschraenkt auf "Internet operational or technical research" — kommerzielle Nutzung/Einbindung in Produkte ist laut den Nutzungsbedingungen verboten.

**BNetzA-Anbieterverzeichnis (§5 TKG)** [GEPRUEFT] — Deutschlands Regulierer veroeffentlicht eine XLSX-Datei "Verzeichnis der gemeldeten Anbieter von Telekommunikationsdiensten und Betreiber oeffentlicher Telekommunikationsnetze", Stand laufend aktualisiert (05.08.2026 im Fetch), 301 KB, direkter Download ohne Login. Enthaelt vermutlich alle bei der BNetzA gemeldeten TK-Unternehmen Deutschlands — genau das Muster "Lizenzliste als Datei". Kostenlos, offene Behoerdendaten.

**FCC ULS / Open Data Portal** [GEPRUEFT, Existenz bestaetigt; Inhalt nicht im Detail] — `opendata.fcc.gov` fuehrt das Universal Licensing System als offenes Dataset, zusaetzlich Pipe-delimited Bulk-Downloads (woechentlich/taeglich) unter fcc.gov/wireless/data. US-spezifisch, Lizenznehmer inkl. Adressdaten, kein Website-Feld dokumentiert gefunden.

**ITU World Telecommunication/ICT Regulatory Survey** [GEPRUEFT] — Eine Umfrage an Mitgliedstaaten, kein durchsuchbares Firmenregister. Ergebnisse fliessen in ITU DataHub (403 beim Abruf) und den ICT Regulatory Tracker. Datahub enthaelt laut Suchtreffer ein Feld "Name of authority" je Land — also Regulierer, nicht Betreiber.

**GSMA (Vereinsmitgliederliste)** [UNGEPRUEFT, 403 beim Fetch] — Laut Suchtreffer >750 Vollmitglieder (Mobilfunknetzbetreiber) plus ~400 Associate Members, filterbares Web-Verzeichnis unter gsma.com/get-involved/gsma-membership/our-members/, aber kein erkennbarer Bulk-Export/API.

**GSMA Intelligence** [UNGEPRUEFT] — Kommerzielle Datenbank, laut Marketingtexten >1.000 Mobilfunkbetreiber/~4.500 Netze weltweit, PDF/Tabellen-Export, kein oeffentlicher API-Zugang erkennbar, Preis nicht genannt (nur "Contact us").

**TeleGeography GlobalComms** [GEPRUEFT, Marketingseite] — Umfassende Firmenprofile, herunterladbare Datensaetze, aber kein Preis genannt, Abo-Login noetig; keine Angabe der Betreiberzahl auf der Seite selbst.

**Regulatel** [teilweise GEPRUEFT] — Forum von 23 Laendern (Lateinamerika + Spanien/Portugal/Italien), Mitgliederseite existiert (`regulatel.org/miembros`), Inhalt beim Fetch nicht auslesbar (vermutlich JS-gerendert).

## Was das fuer dieses Projekt bedeutet

PeeringDB wuerde die 4,2-Firmen/Minute-Grenze massiv sprengen — eine einzige API-Abfrage liefert tausende Website-Felder auf einmal, ohne Host-Hoeflichkeitslimit pro Firma. Aber die AUP verbietet genau die geplante Nutzung (automatisierte Weiterverarbeitung in ein Produkt), also waere vor Einsatz eine Anfrage an PeeringDB noetig oder eine sehr enge Auslegung "nur zum manuellen Nachschlagen". Die Handarbeit (154/234 verworfen) wuerde PeeringDB NICHT reduzieren, eher vergroessern: die meisten Eintraege sind IX/Hosting/Enterprise-Netze ohne Newsroom. **Naechster Schritt**: BNetzA-Muster auf 5-10 weitere grosse Maerkte uebertragen (Ofcom, ARCEP, AGCOM, FCC) — Regulierer-Lizenzlisten sind der einzige Fund hier, der echte, bereits gefilterte Telco-Firmennamen mit oft vorhandenem Domainfeld liefert, ohne AUP-Problem.

## Fallstricke

PeeringDB-Daten in grossem Stil abzugreifen verletzt vermutlich die AUP — rechtliches Risiko, nicht nur technisches. RIR-Datenbanken (ARIN explizit) verbieten kommerzielle/produktive Weiterverwendung von Bulk-Daten. Regulierer-Listen sind uneinheitlich (PDF-Scan bis XLSX), oft nur Firmennamen ohne Website — zusaetzlicher Domain-Suchschritt noetig. ITU-Ressourcen liefern Regulierer, keine Betreiber — Verwechslungsgefahr. GSMA/TeleGeography/Omdia sind kostenpflichtig und ohne erkennbare Export-API, also fuer eine kostenlose GitHub-Actions-Pipeline ungeeignet.

---

## Kurzfassung

Kein einziges der recherchierten Grossprojekte löst das Wertproblem automatisch – alle setzen auf manuelle oder halbmanuelle Kuratierung, oft über Jahrzehnte gewachsen, und lassen Volumen (GDELT, NewsCatcher) oder Qualität (Media Cloud, EMM, Fundus) explizit gegeneinander antreten. Die einzige Klasse von Ansatz, die tatsächlich Handarbeit spart, ist "LLM bewertet Inhalt/Quelle nach Kriterien statt Mensch" – aber sie ersetzt die menschliche Prüfung nirgends vollständig, sie verkürzt sie nur. Für Telco Radar ist der ehrlichste Befund: die 4,2 Firmen/Minute-Grenze ist branchenüblich (EMM/NewsBrief der EU-Kommission arbeitet nach demselben "besuche jede Seite, nimm RSS oder parse HTML"-Prinzip wie das eigene Skript), und die 154-von-234-Verwurfsquote ist eher niedrig als hoch verglichen mit dem, was Media Cloud und Fundus über sich selbst schreiben.

## Befunde

**Media Cloud** – offene Plattform (MIT/Northeastern), sammelt seit über 10 Jahren per RSS- und Sitemap-Feeds. Quellenaufnahme ist ausdrücklich "subjektiv", jede Quelle bekommt Metadatenfelder inkl. Freitext-Notiz für "inclusion reasoning, quality, editing history" – also dieselbe Handarbeit wie bei Telco Radar, nur ohne automatisierten 9-Kriterien-Check davor. Kein publizierter Automatisierungsschritt für die Wertprüfung. Zugang: mediacloud.org, teils kostenlose API. [GEPRÜFT] (arxiv.org/abs/2104.03702, mediacloud.org/documentation/source-guide)

**GDELT** – ca. 47.000 Quellen, seit 2015 über 1 Mrd. Artikel. Zentrale Erkenntnis: GDELT filtert selbst NICHT vor – es "ingests spammy SEO blogs, PR newswires, and news media" undifferenziert und überlässt die Qualitätsauswahl externen Forschern, die daraus Medienlisten wie "elite media", "wire media", "emerging media" bauen. Kostenlos, BigQuery + CSV-Export, Master-Filelisten alle 15 Minuten aktualisiert. [UNGEPRÜFT] (nur Suchtreffer, GDELT-Blog nicht direkt abgerufen)

**Europe Media Monitor / NewsBrief (JRC, EU-Kommission)** – strukturell am nächsten an Telco Radar: besucht Quellen alle 5 Minuten, nutzt RSS wo vorhanden, sonst HTML-Extraktion aus "often complex pages" – exakt der eigene Fallback-Pfad. Frühere Dokumentation (2018) nennt ~2.500 handverlesene Quellen; aktuelle Suchtreffer zur Nachfolgeseite media-monitor.europa.eu nennen 20.000 überwachte Websites, 80 Sprachen, 150 Länder – also zehnfaches Wachstum, weiterhin hand-selektiert. Kostenlos für EU-Zwecke, Zugang eingeschränkt (kein offenes Self-Service-API für Dritte bekannt). Aktiv (Redirect von der alten emm.newsbrief.eu-URL funktioniert). [GEPRÜFT für Aktivität/Redirect, UNGEPRÜFT für die 20.000-Zahl – kam nur aus Suchsnippet, nicht aus direkt abgerufenem Seiteninhalt]

**NewsCatcher** – über 120.000 Quellen, kommerziell (YC-Company). Discovery-Methode nicht offengelegt; bekannt ist nur die Scheduling-Seite (Crawl-Frequenz pro Quelle nach beobachtetem Publikationsrhythmus) und 5 Extraktionsmethoden inkl. "3 proprietäre Techniken". Keine publizierten Ausbeute- oder Verwurfszahlen zur Quellenaufnahme selbst. API kostenpflichtig. [GEPRÜFT] (newscatcherapi.com/how-it-works)

**Aylien** – Blogpost nennt Wachstum von ~15.000 auf ~80.000 Quellen, aber die Domain aylien.com ist beim Abruf nicht mehr auflösbar (DNS-Fehler) – starkes Indiz, dass das Produkt/Unternehmen inzwischen abgeschaltet oder umbenannt ist. Vor Nutzung zwingend prüfen. [UNGEPRÜFT, mit Warnhinweis – WebFetch schlug mit ENOTFOUND fehl]

**Feedly** – Millionen Quellen, aber die Kuratierungsarbeit läuft anders herum: Feedly baut seine Themen-Taxonomie aus anonymisierten Ordnernamen der Nutzer ("wer folgt X und nennt seinen Ordner 'tech'") und rankt Empfehlungen nach Nutzerzahl/Relevanz – das ist Crowd-Sourcing der Bewertung, nicht ein Ersatz für Erstprüfung neuer Quellen. [UNGEPRÜFT, nur Suchsnippets]

**Fundus (KIT, arXiv 2403.15279)** – Gegenmodell zu "viele Quellen": 39 Publisher, komplett handgeschriebene CSS/XPath-Parser pro Site, 97,7 ROUGE-F1 gegen 89,8 bei Trafilatura. Die Autoren schreiben explizit: der Ansatz "inherently lacks scalability", und nennen als offene Zukunftsarbeit "semi-automatic methods to suggest extraction rules" – also genau die Automatisierung, die noch niemand gebaut hat. [GEPRÜFT]

**LLM-Assisted News Discovery (arXiv 2509.25491, 2025)** – der einzige Fund, der Handarbeit MISST statt behauptet zu reduzieren: n8n-Pipeline, RSS+Google-Alerts → LLM bewertet Newsworthiness 1–5 nach vier Kriterien, $0,15/Tag, o3 erreicht 92 % "±1-Genauigkeit" gegen menschliche Bewertung, aber nur 26,7 % exakte Übereinstimmung. Fazit der Autoren selbst: brauchbar zur Vorsortierung, nicht als Ersatz der Redaktion. Bezieht sich auf Artikelbewertung, nicht Quellenaufnahme, aber das Prinzip überträgt sich direkt. [GEPRÜFT]

**Webgraph-basierte Quellenentdeckung (arXiv 2401.02379)** – nutzt Backlink/Outlink-Homophilie + SEO-Signale, um von bekannten Fake-News-Domains zu neuen zu springen (F1 0,96 als Klassifikator, nicht als Discovery-Ausbeute). Prinzip liesse sich umdrehen: von 285 bekannten guten Newsroom-Domains über deren Verlinkungsnachbarschaft neue Kandidaten finden statt über Firmenlisten zu suchen. [GEPRÜFT nur Abstract, Volltext nicht geprüft]

## Was das für dieses Projekt bedeutet

Kein Fund würde die 4,2 Firmen/Minute-Netzhöflichkeitsgrenze beschleunigen – die ist physikalisch (ein Server, keine Parallelität hilft), und EMM/NewsBrief hat exakt dasselbe Limit, nur mit EU-Infrastrukturbudget statt Sandbox. Die Handarbeit liesse sich am ehesten nach dem Muster von arXiv 2509.25491 verkürzen: einen LLM-Prompt mit den bereits im CLAUDE.md dokumentierten Ablehnungsgründen (Boilerplate, Kampagnenseite, Wettbewerbsbehörde statt Telko-Behörde, Dubletten) als Vorfilter VOR den 9-Kriterien-Check zu schalten – nicht als Ersatz, sondern um die 234 bestandenen Kandidaten vor der Handprüfung auf vielleicht 100 vorzusortieren. Nächster Schritt in einem Satz: einen LLM-Prompt bauen, der jede bestandene Quelle gegen die Session-4/5/6-Ablehnungsliste aus CLAUDE.md bewertet und nur "wahrscheinlich wertlos" markiert, damit Antonios Kollegin nur noch die Grenzfälle von Hand sieht.

## Fallstricke

Bing News Search API ist seit 11.08.2025 tot (HTTP 410) – ein naheliegender Fallback, den man nicht mehr nutzen kann. [GEPRÜFT: learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement] Aylien ist vermutlich ebenfalls nicht mehr erreichbar – vor jeder Erwähnung in einer Empfehlung selbst nachprüfen. GDELT und Feedly filtern nicht vor, sondern verlagern das Wertproblem auf nachgelagerte, meist akademische oder crowd-basierte Kuratierung – "GDELT hat 47.000 Quellen" heisst nicht "47.000 gute Quellen". Fundus zeigt die Kehrseite von zu viel Handarbeit: bei striktem Qualitätsanspruch bleibt man bei 39 Publishern hängen. Boilerplate-Klassifikatoren (Boilerpipe u.ä.) lösen die Extraktion sauberen Fliesstexts, nicht die Frage, ob eine Quelle inhaltlich wertvoll ist – das ist ein anderes Problem als das, wofür Telco Radar sie bräuchte.

---

## Kurzfassung

Der ergiebigste fertige Baustein ist **trafilatura**: `find_feed_urls()` und `sitemap_search()` sind gut gepflegt (Apache 2.0, aktiv), aber inhaltlich dieselbe Heuristik wie die eigene — bekannte Pfade plus `<link rel=alternate>`, keine geheime Zusatzintelligenz. Der Gewinn ist Wartungsaufwand sparen, nicht Trefferquote springen. **JSON-LD/`NewsArticle`** wäre die sauberere Datumsquelle als Textparsing, ist aber auf B2B-Konzernseiten (genau das Zielsegment) empirisch selten vorhanden. **News-Sitemaps** (`news:publication_date`) sind ein starkes Signal bei Fachpresse mit WordPress/Yoast, aber bei Telco-Newsrooms selbst kaum verbreitet — geprüft an Vodafone: normale Sitemap mit `lastmod`, kein `news:`-Namespace. Keines der Werkzeuge löst die beiden echten Engpässe (Netz-Wanduhr, Wertprüfung von Hand); sie könnten höchstens die Formprüfung leicht verbilligen.

## Befunde

**trafilatura** [GEPRUEFT] — Textextraktion mit eingebauter Link-Discovery. `find_feed_urls(url, target_lang, external, sleep_time)` gibt sortierte Feed-URL-Liste zurück, `sitemap_search(url, target_lang, external, max_sitemaps=10000)` durchsucht Sitemaps und liefert Artikel-Links. GitHub `adbar/trafilatura`, 6,4k Stars, 1635 Commits, Apache-2.0 (vor v1.8 GPLv3+), aktiv gepflegt (Nutzer u. a. HuggingFace, IBM). Läuft mit httpx-kompatiblem Stack, pip-installierbar. https://trafilatura.readthedocs.io/en/latest/usage-cli.html

**feedsearch-crawler** (DBeath) [GEPRUEFT] — Async-Crawler (asyncio/aiohttp) speziell für Feed-Discovery, folgt Links bis Tiefe 10, scored nach Relevanz, optional `try_urls=True` für bekannte Pfade. MIT-Lizenz, PyPI 2.0.1, 96 Stars, moderat aktiv. Der zugehörige Hosted-Dienst **feedsearch.dev** antwortete bei meinem Abruf mit HTTP 403 — entweder tot oder durch Bot-Schutz blockiert; als API nicht verlässlich, die Library selbst schon. https://github.com/DBeath/feedsearch-crawler

**feedfinder2** (dfm) [UNGEPRUEFT, aus Suchergebnissen] — einzelne Funktion `find_feeds()`, letzte PyPI-Version 0.0.4, laut Snyk seit über 12 Monaten kein Release, kaum Issue-Aktivität. Faktisch eingefroren, nicht tot, aber kein Fortschritt zu erwarten.

**listparser** (kurtmckee) [GEPRUEFT via Suche] — parst OPML/RDF+FOAF-Abolisten, KEINE Feed-Discovery auf beliebigen Seiten. v0.20, Python ≥3.10, gepflegt. Für dieses Projekt irrelevant, außer man bekäme fremde OPML-Exporte zum Einlesen.

**newspaper4k** (AndyTheFactory) [GEPRUEFT via Suche] — aktiver Fork von newspaper3k (das seit 09/2020 tot war), v0.9.5 vom 28.02.2026, MIT-artig. Extrahiert Artikel-Metadaten inkl. Datum aus Meta-Tags/JSON-LD, kann Kategorie-/Feed-URLs einer Domain sammeln. Guter Ersatz für BeautifulSoup-Handarbeit bei der Datumsextraktion, aber kein eigenständiger Feed-Finder.

**news-please** (fhamborg) [GEPRUEFT via Suche] — kombiniert Scrapy + Newspaper + Readability, vier Crawl-Modi: rss, recursive, sitemap, automatic. Der Sitemap-Modus testet jeden Sitemap-Link gegen einen Artikel-Klassifikator. Mächtig, aber schwergewichtig (Scrapy-Unterbau) — für ein schlankes httpx/GitHub-Actions-Setup vermutlich zu viel Gewicht für zu wenig Zusatznutzen gegenüber der eigenen Pipeline.

**GNE / GeneralNewsExtractor** [UNGEPRUEFT] — chinesisches Projekt, GPL-3.0, letzte nennenswerte Aktivität um 2019–2021. Auf chinesische Boilerplate-Muster trainiert, für europäische/nordamerikanische Telco-Seiten wenig Mehrwert, GPL zudem lizenzkritisch für ein sonst freizügiges Projekt.

**boilerpy3** [GEPRUEFT via Suche] — Apache-2.0-Port von Boilerpipe, reine Fließtext-/Boilerplate-Extraktion aus HTML, kein Feed- oder Artikellisten-Erkenner. Kein Release seit über 12 Monaten. Löst ein anderes Problem als das gesuchte.

**RSSHub** [GEPRUEFT via Suche] — 41k Stars, MIT, sehr aktiv, self-hostbar. Wandelt "fast jede Website" in Feeds um — aber über handgeschriebene, seitenspezifische "Routen" (>1000 Stück), kein generischer Detektor. Für einen Nischen-B2B-Newsroom eines Telco-Betreibers existiert praktisch nie eine passende Route; man müsste sie selbst schreiben, was der Aufgabe nicht abnimmt, sondern nur verlagert.

**RSS-Bridge** [GEPRUEFT via Suche] — PHP, Public Domain, ~8,8k Stars, aktiv (Releases bis 08/2025), ~528 community-gepflegte "Bridges" nach demselben Prinzip wie RSSHub: seitenspezifische Scraper, kein generischer Erkenner.

**Schema.org JSON-LD / NewsArticle** [GEPRUEFT] — Google-Schema.org-Kooperationsdatensatz (blog.schema.org, 06/2026) bestätigt: `NewsArticle` liegt in der 100k–1-Mio.-Domain-Bucket-Kategorie, deutlich seltener als generisches `Article` (Gesamtadoption dort ~1,77 %, Web Almanac 2024). Stichprobe Deutsche Telekom-Pressebereich: **kein** JSON-LD im HTML gefunden. Wo vorhanden, ist `datePublished` deutlich zuverlässiger als Textparsing — aber "wo vorhanden" ist bei Konzern-Pressebereichen die Ausnahme, nicht die Regel.

**News-Sitemaps / `news:publication_date`** [GEPRUEFT] — offizielle Google-Doku (developers.google.com, Stand 10.12.2025) bestätigt Format: max. 1000 URLs, nur letzte 2 Tage, Pflichtfeld ist `news:publication_date`, NICHT `lastmod` (das gehört zur normalen Sitemap und misst "zuletzt geändert", nicht "veröffentlicht" — oft CMS-Build-Zeitstempel). Google hat die manuelle News-Sitemap-Registrierung in Publisher Center seit 04/2024 abgeschafft, automatische Aufnahme seit 03/2025 — das schwächt den Anreiz für Verlage, das Format sauber zu pflegen. Stichprobe Vodafone: normale Sitemap mit `lastmod`, kein `news:`-Namespace.

## Was das für dieses Projekt bedeutet

Nein, keines beschleunigt die 4,2 Firmen/Minute — der Engpass ist Höflichkeits-Wanduhr gegen einzelne Server, nicht Erkennungsqualität. trafilatura's `sitemap_search()`/`find_feed_urls()` könnten als **zusätzlicher, kostenloser Kandidatengenerator neben** der eigenen Stufe-4-Suche laufen (parallel testen, nicht ersetzen) — echter Zeitgewinn ist eher an Wartungscode gespart als an Wanduhr. JSON-LD/News-Sitemaps würden die Wertprüfung nicht automatisieren, könnten aber als **zusätzliches PASS/FAIL-Kriterium** im Abnahme-Check dienen ("hat die Quelle `datePublished` oder `news:publication_date` — dann ist das Datumsproblem gelöst, ohne Monatsnamen-Tabellen"). Nächster Schritt in einem Satz: trafilatura's zwei Funktionen probeweise in `finde_quellen.py` als fünfte Suchstufe einbauen und an der Welle-3-Firmenliste gegen die bestehende Stufe-4-Heuristik messen, bevor man sie ersetzt.

## Fallstricke

RSSHub/RSS-Bridge lösen scheinbar "Feed für jede Seite", liefern aber nur, wenn zufällig schon eine Community-Route existiert — bei Nischen-B2B-Newsrooms praktisch nie, und GPL/Copyleft-Fragen bei mitgelieferten Bridges sind ungeprüft. GNE ist GPL-3.0 — Lizenzkonflikt, falls das Projekt bislang permissiv bleiben will. `feedsearch.dev` als gehosteter Dienst antwortete bei mir mit 403 — nicht als verlässliche externe Abhängigkeit einplanen. News-Sitemaps sind zeitlich sehr eng (2-Tage-Fenster, max. 1000 URLs) — bei zweiwöchentlichem Cron-Lauf ungeeignet als alleinige Quelle, nur als Ergänzung zur regulären Sitemap brauchbar. JSON-LD-Datumsangaben können ebenso wie `lastmod` falsch/stale sein (CMS setzt beim Republish `dateModified` neu, `datePublished` bleibt oder wird überschrieben) — genauso prüfbar-schädlich wie das jetzige Textparsing-Problem, nur mit anderem Fehlerbild. news-please/GNE ziehen schwere Abhängigkeiten (Scrapy bzw. chinesische NLP-Stacks) — Risiko für die GitHub-Actions-Kostenfreiheit und Laufzeit, wenn unreflektiert integriert.

---

## Kurzfassung

Es gibt kein fertiges "Ist-das-Presse-oder-Werbung"-Modell, das man einfach einbindet — weder Media Cloud noch NewsGuard noch Feedly Leo lösen diese Frage automatisiert, alle drei bauen auf menschlicher Kuratierung bzw. proprietärem Nutzerfeedback. Was funktioniert und für dieses Projekt passt: die 9-Kriterien-Formprüfung um einen billigen LLM-Richter (Haiku) erweitern, der über die ohnehin gesammelten ~10 Titelproben je Kandidat urteilt — das kostet bei aktueller Preisliste unter 1 US-Dollar pro 1000 Kandidaten und ist damit gegenüber der Netz-Wanduhr (4,2 Firmen/Minute) komplett vernachlässigbar. Der eigentliche Hebel liegt aber nicht im Modell, sondern in den Trainingsdaten, die bereits existieren: 234 von Hand klassifizierte Kandidaten (80 akzeptiert, 154 abgelehnt mit dokumentierten Ablehnungsgründen) sind eine reale Few-Shot-Grundlage für SetFit oder als Few-Shot-Beispiele im LLM-Prompt — deutlich wertvoller als jedes generische Advertorial-Modell aus der Forschung.

## Befunde

**Claude Haiku 4.5 Pricing** [GEPRÜFT, platform.claude.com/docs/en/about-claude/pricing] — $1/MTok Input, $5/MTok Output, Batch $0,50/$2,50, Cache-Hit $0,10. Bei 10 Titeln + Prompt (~400 Input-, ~100 Output-Tokens) je Kandidat kostet ein Urteil über 1000 Kandidaten rund $0,90 im Standardtarif, ~$0,45 per Batch-API. Sonnet 5 (aktuell $2/$10) läge bei ~$2 je 1000 — auch das noch trivial gegen die Recherche-Zeit.

**facebook/bart-large-mnli** [GEPRÜFT, huggingface.co] — 400-Mio.-Parameter Zero-Shot-NLI-Modell (Hypothese "Dies ist eine Werbemeldung" vs. Premise), kostenlos, Apache/MIT-artig lizenziert. Auf CPU (GitHub-Actions-Runner hat 2 Kerne) mehrere hundert ms bis Sekunden je Item — für 1000+ Kandidaten in der Pipeline machbar, aber langsamer und ungenauer als ein gezielter LLM-Prompt mit Domänenwissen.

**SetFit** [UNGEPRÜFT, nur Suchergebnisse] — Sentence-Transformer-Few-Shot-Klassifikation, funktioniert schon ab 8 Beispielen/Klasse, Training in Minuten auf CPU, MIT-lizenziert (HuggingFace). Direkt nutzbar mit den 234 vorhandenen Session-6-Labels als Trainingsmenge, die mit jeder Welle wächst.

**fastText** [UNGEPRÜFT, nur Suchergebnisse] — Meta, MIT-Lizenz, CPU-Inferenz im Millisekundenbereich, klassisches Werkzeug für Spam-/Grobfilter. Genau wie SetFit auf eigene Labels angewiesen, liefert aber weniger feine Unterscheidungen (SKU-Titel vs. Pressemitteilung) als Embeddings/Transformer.

**Electronic News Dataset for Native Advertisement Detection** [GEPRÜFT, pmc.ncbi.nlm.nih.gov/articles/PMC12181363] — 12.088 indonesische Newsartikel, 50/50 Native-Ads/News, CC-BY 4.0, frei via figshare, BERT-BiLSTM erreichte 95 % Genauigkeit. Zeigt: Advertorial-Erkennung ist ein aktives Forschungsfeld mit offenen Datensätzen — aber Sprache (Indonesisch) und Domäne (Publikumspresse, nicht B2B-Fachpresse/Telko) passen nicht, ein fertiges Modell daraus gibt es nicht zum Download.

**Media Cloud Source Guide** [GEPRÜFT, mediacloud.org/documentation/source-guide] — Quellenauswahl ist explizit manuell: "We apply that criteria subjectively based on each research project." Einzige automatisierte Kennzahl ist "Stories per Week", rein deskriptiv, kein Werturteil. Selbst ein MIT/Harvard-Projekt mit jahrelanger Förderung hat die Wertfrage nicht automatisiert — realistische Erwartungshaltung für dieses Projekt.

**NewsGuard** [teilweise GEPRÜFT über newsguardtech.com Solutions-Seite] — redaktionelle Trust-Ratings für >35.000 Quellen, API/Datastream vorhanden, aber kommerzielle Nutzung lizenzpflichtig, Preise nicht öffentlich (Enterprise-Sales). Bewertet Vertrauenswürdigkeit/Desinformation, nicht Fachrelevanz — würde die B2B-Telko-Frage ("ist das Fachpresse oder IT-Allgemeinpresse") gar nicht beantworten.

**Feedly Leo** [UNGEPRÜFT, nur Suchergebnisse] — Nutzer-Feedback-Loop (Like/Mute pro Artikel), proprietär, kein offenes Modell/API, das man für eine automatisierte Vorabprüfung nutzen könnte.

**jusText / trafilatura** [GEPRÜFT über Suchergebnisse; jusText aktiv gepflegt, Release Feb. 2025, PyPI, Production/Stable] — heuristische Boilerplate-Entfernung (Nav/Footer/Kommentare), Python, kostenlos. Nützlich als Vorverarbeitung vor jeder Klassifikation, beantwortet aber nicht "Presse vs. Werbung", nur "Haupttext vs. Layout-Müll".

**FineWeb/C4-Heuristiken** [GEPRÜFT über Paper/Suchergebnisse] — Wiederholungsraten, Stoppwortanteil, Zeilenlänge als billige Pretraining-Filter. Prinzip übertragbar (z. B. hohe Titel-Wiederholungsrate = Terminkalender/Event-Feed), aber nicht für Presse/Werbung gebaut.

**Voyage AI / OpenAI Embeddings** [GEPRÜFT] — Voyage-4-lite $0,02/MTok, text-embedding-3-small $0,02/MTok (Batch $0,01). Für Zentroid-Ähnlichkeit extrem billig, erfordert aber ein zusätzliches API-Konto/Secret neben dem vorhandenen Anthropic-Key.

## Was das für dieses Projekt bedeutet

Die Netz-Wanduhr (4,2 Firmen/Minute) wird dadurch nicht schneller — das ist ein Höflichkeits-/Rate-Limit-Problem, kein Klassifikationsproblem. Was sich reduzieren lässt, ist die Handarbeit bei den 234 formal bestandenen Kandidaten: ein Haiku-Aufruf über die 10 Titelproben (Prompt mit den dokumentierten Ablehnungsmustern aus Abschnitt 6 des CLAUDE.md als Few-Shot-Beispiele) kostet pro Welle unter einem Dollar und würde die offensichtlichen Fälle (SKU-Titel, Terminkalender, Personalmeldungen) vorsortieren, sodass nur Grenzfälle (Überschneidung mit Bestand, "ist das noch Fachpresse") von Hand bleiben. Nächster Schritt: einen `pruefe_wert.py`-Schritt bauen, der nach dem bestehenden 9-Kriterien-Check die Titelproben jedes PASS-Kandidaten durch einen Haiku-Prompt mit den echten 154 Ablehnungsbeispielen als Few-Shot-Kontext schickt und ein Ja/Nein/Unsicher plus Begründung zurückgibt.

## Fallstricke

Ein LLM-Richter ohne die projektspezifischen Beispiele urteilt genau wie die "geprüft"-Behauptung aus Session 4 — überzeugend klingend, aber falsch, weil generisches Weltwissen nicht weiß, dass corporate.comcast.com/rss schon einmal verworfen wurde. Zero-Shot-Modelle (bart-large-mnli) sind auf CPU in GitHub Actions langsam genug, dass sie bei 1000+ Kandidaten eher Minuten als Sekunden kosten. NewsGuard/Media-Cloud sind für "vertrauenswürdig" gebaut, nicht für "B2B-Fachrelevanz" — ihr Einsatz würde falsche Sicherheit erzeugen. Und jedes automatisierte Urteil ersetzt nicht die Vier-Augen-Regel aus Session 6 (identische erste Titelprobe bei Dubletten von Hand vergleichen) — das bleibt Handarbeit, weil es ein Vergleich zwischen zwei Kandidaten ist, kein Urteil über einen einzelnen.

---

