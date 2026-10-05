# Kommentarwissen 06-collect-rest

Stand: Commit aaa8b0d, 16 Dateien, 924 Kommentarzeilen.

## Übernahmen in Code
- `src/telco_radar/collect/newsroom_js.py`: Konstante `NACHLADEZEIT_MS` ersetzt `9000` in `render_html` – feste Wartezeit für clientseitig nachgeladene Artikellisten.
- `src/telco_radar/collect/newsroom.py`: nicht übernommen (die Konstante hätte die Riesendatei über ihre Grenze gebracht); Wissen: `[:400]` in `parse_newsroom_html` (zwei Stellen) ist die Länge, bis zu der im Kartentext nach dem Datum gesucht wird; eine `date`-Klasse im Nachfahren ist genauer und wird vorher versucht, weil ein Datum hinter einem langen Absatz außerhalb der 400 Zeichen liegen kann.
- Alle anderen erklärten Werte sind schon benannt (`_QUELLEN_FRIST`, `_JS_GLEICHZEITIG`, `MAX_WERTE`, `MAX_AENDERUNGEN_JE_SEITE`, `_BACKOFF_WAITS`, `VOLLTEXT_MINDESTLAENGE`, `_TABELLENTIEFE` …); keine neuen Tests.

## Für docs/betrieb.md
- Sammelphase: harte Frist je Quelle 75 s (`_QUELLEN_FRIST`); Lauf #75 brauchte für EINE tote Quelle (KT, `timeout_seconds: 30`, volle Retry-Leiter) 302,6 s, die gesamte Sammelphase 303,7 s (Quelle `collect/__init__.py:22`, `http.py:208`).
- Headless-Browser höchstens 4 gleichzeitig (GitHub-Runner hat zwei Kerne); Diagnoselauf #74 (05.08.2026): bei 64 Workern fiel Viettel mit "Page.goto: Timeout 16000ms exceeded" aus, bei 8 Workern lief er durch (`collect/__init__.py:30`).
- Host-Drosselung: 130 Quellen bei 8 Workern brauchten 325 s, 1000 Quellen wären 42 min und damit über dem Job-Timeout; je Host höchstens `max_parallel` gleichzeitig plus Mindestabstand zwischen zwei Starts, Gate in `fetch()` (`http.py:115`).
- Job-Timeout des Radars liegt bei 50 Minuten, zuletzt gemessen 27,4 min (`rss.py:32`).
- Aus GitHub Actions antwortet die Telekom-Tarifseite mit einer Challenge (HTTP 202, rund 2 KB, kein Link); aus der Sandbox 200 und 1114 Links. Telekom lief deshalb zwei Monate als "liefert nichts" (Befund 04.09.2026) (`tarif_crawler.py:953`).
- Zertifikatsspeicher des Runner-Images ändert sich ohne Projektänderung (NTIA CERTIFICATE_VERIFY_FAILED, Lauf 07.08.2026); deshalb das `certifi`-Bündel explizit (`http.py:63`).
- Telekom-Absender: Override pro Anbieter über `user_agent:` in `tarif_quellen.yaml`; die globale Kennung `http.user_agent` gilt für alle 196 Quellen (`tarif_crawler.py:179`).
- Chromium-Umgebungsvariable für TLS-Proxy ist nur Dev-Sandbox, in CI/Produktion ungesetzt (`newsroom_js.py:67`).

## Widersprüche
- keine

## Wissen je Datei

### `src/telco_radar/collect/__init__.py`
- `_QUELLEN_FRIST` (22): 75 s lassen einer langsamen Quelle zwei volle Versuche à 30 s; Messung Lauf #75 siehe betrieb.md.
- `_JS_GLEICHZEITIG` (30): newsroom_js ist keine reine Wartezeit; Worker dürfen steigen, gleichzeitige Renderings nicht (Messung #74 siehe betrieb.md).
- Duplikat-Hinweis (61): Verizon spiegelt 7 von 25 Meldungen spanisch unter `/about/news/es/`; andere URL, der Seen-Store hält sie für eine zweite Meldung.
- Quellen-URL zentral (66): Trefferquote je KANAL braucht die Quellen-URL; ein Betreiber mit Newsroom plus Investor Relations trägt in beiden denselben `source_name`.
- Region regionaler Fachpresse (125): ohne Vorgabe landete alles unter "Global"; Lauf #75 schloss Europa mit NULL bewerteten Meldungen ab, Global bekam 62 von 92.
- Themenquellen (130): laufen mit Themenschlüssel als "Region", damit jedes Themenfeld einen eigenen Analysten bekommt, ohne dass die Regionslogik es für einen Betreiber hält.
- Stillgelegte Quellen (137): überspringen ist Laufzeit, kein Komfort; der Bewährungsabruf (`quellen_register.py`) holt sie zurück.
- Mehrdeutige Einzelwörter (255): zu mehrdeutig, um allein einen Betreiber zu bestimmen; Mehrwortbegriffe, die sie enthalten, bleiben erlaubt.
- Zeile 185: nur noqa, nichts zu übernehmen.

### `src/telco_radar/collect/aenderungen.py`
- `MAX_WERTE` (69): eine Tarifübersicht hat ein paar Dutzend Preise; tausend Werte sind die Preisliste des ganzen Shops, der Diff wäre Rauschen.
- Mindestwerte (74): GEMESSEN 08.08.2026 an allen 16 konfigurierten Seiten: Preistabelle im HTML bringt 16 bis 54 Werte (o2 54, 1&1 29, blau 28, klarmobil 16); nur eine Handvoll heißt Fließtext ("sparst du 10 %", "bis zu 1 GB"), die Tabelle baut JavaScript auf. Ein Diff darauf meldet Textänderungen als Preisänderungen.
- `MAX_AENDERUNGEN_JE_SEITE` (85): 12; darüber gilt die Seite als umgebaut und wird nicht gemeldet – ein Relaunch ist keine Preisänderung, vierzig Meldungen machten den Kanal unbrauchbar.
- Zahlenwerte (102): nur mit Einheit; eine nackte Zahl auf einer Webseite ist Artikelnummer, Zähler oder Jahreszahl.
- Ausschlussliste (110): ohne sie meldete jeder Abruf eine Änderung, weil die Seite die Uhrzeit ausgibt.
- Zeile 331: zu wenige Werte heißt JS-Preistabelle; "alles entfallen" zu melden wäre die teuerste Falschmeldung, der Prosa-Diff die zweitteuerste.
- Zeilen 326, 357: noqa bzw. Wiederholung ("Relaunch ist keine Preisänderung"), nichts weiter.

### `src/telco_radar/collect/ct_log.py`
- Frist je Domain (70): große Domains bekommen mehr, aber begrenzt; certspotter beantwortet telekom.de mit include_subdomains gar nicht.
- Obergrenze neuer Namen (75, 438): mehr aus einem Lauf ist ein Umbau des Namensraums (Grundlinie stimmt vermutlich nicht), keine Kampagne; wie `MAX_AENDERUNGEN_JE_SEITE`.
- Zeile 413: Ausfall bei großen Domains ist erwartbar und ausdrücklich KEIN leeres Ergebnis; die Grundlinie bleibt unangetastet.
- Zeile 185: nur Präfixe prüfen, nicht die Registrierungsdomain.
- Zeilen 118, 313, 322: Feldhinweis, pragma, noqa – nichts übernommen.

### `src/telco_radar/collect/http.py`
- Client-Hints (34): GEMESSEN 08.08.2026 an den drei Quellen mit 403 im Lauf 07.08.: ISPreview UK und MediaNama antworten mit und ohne Satz 200 (Ausfall war nicht der User-Agent). Telecompetitor antwortet auf JEDE Variante (Client-Hints, nackter Browser-UA, Googlebot-UA, HTTP/2, ohne Referer) mit 403 = IP-Sperre; Antwort ist die Quarantäne mit Bewährungsabruf. Der Satz bleibt: kostet nichts, ist ehrlich, hilft gegen reine Client-Hint-Prüfung.
- Wurzelzertifikate (63): NTIA-Fehler siehe betrieb.md; fehlt certifi, bleibt der Systemspeicher (Abhängigkeit darf keine Sammelphase kippen).
- Host-Drosselung (115): siehe betrieb.md. Gedrosselte Quelle kostet drei Versuche mit 4 s und 9 s Backoff, mehr Parallelität macht langsamer. Gate bewusst in `fetch()`, damit Wiederholungen (rss.py bis zu drei Mal) und Folgeabrufe der Newsroom-Parser mitzählen.
- Abstand (168): gilt zwischen zwei STARTS zum selben Host; Wartezeit unter dem Host-Lock, sonst starten zwei Threads gleichzeitig.
- Gate (186): Standard unbegrenzt (wirkungslos), damit Tests und Einzelabrufe unverändert laufen; die Pipeline setzt es aus `settings.yaml`.
- Frist je Quelle (208): Messwerte siehe betrieb.md; Timeout des einzelnen Versuchs bleibt unberührt, eine langsame lebende Quelle bekommt ihre 30 s, nur nicht sechsmal.
- Referer (277): gleicher Ursprung; manche AEM/CMS-"public"-Servlets (stc `bin/public/assets`) lehnen Anfragen ohne Referer als leichten CSRF/Hotlink-Schutz ab.
- Accept-Language (289): Deutsch zuerst; seit Session 5 ist die Quellenliste mehrsprachig, eine nach Accept-Language ausliefernde Seite gab sonst Englisch heraus, auch bei deutscher Quelle.
- Client-Hints nur mit Browser-UA (295): unter ehrlicher Kennung wären sie ein Widerspruch ("Programm" gegen "Chrome") – gilt für jede ehrliche Kennung, nicht nur `BOT_UA`.
- Zeile 335: nach transientem 5xx/429 hilft kein UA-Wechsel.
- Zeilen 80, 85–88, 303, 322, 329: Ablaufbeschriftungen/pragma, nichts übernommen.

### `src/telco_radar/collect/json_api.py`
- Datumsfelder (35): nach Vertrauen geordnet; explizites Veröffentlichungsdatum schlägt "created"/"updated" (bei manchen CMS der Tag der Redakteursberührung).
- Lesereihenfolge (75, 275): bis `MAX_RECORDS` lesen, neueste zuerst sortieren, dann auf `MAX_ITEMS` kürzen; NICHT vor dem Sortieren kappen: stc liefert 281 Meldungen, die ersten 40 sind von 2021/2022, die 2026er stehen weiter hinten (Newsroom wirkte vier Jahre alt).
- CTA-Titel (82, 282): stc-Content-Fragmente nutzen bei älteren Records ein Aufrufetikett ("Details") als Titel; echte Überschrift nur aus Beschreibung/Body, Tags entfernen als letzter Ausweg.
- WordPress (104): Textfelder als `{"rendered": ...}` entpacken. Gatsby (111): abgeleitete Werte wie URL liegen in `"fields"` (Charter).
- Zusammengesetztes Datum (141): z. B. Vodafone Idea `"Tamil Nadu | 10 Jun, 2026"`; Datum herausziehen, sonst sinkt der Eintrag in der Analystenschlange.
- Rekursive Suche (254): Fallback sucht Record-Listen überall im Payload und mischt sie, Dublettenschutz über den Titel.
- `link_template` (293): gewinnt immer vor rohem url/link-Feld; Iliad liefert unter `"url"` nur einen Slug, der sonst gegen den API-Host aufgelöst würde.
- Zeilen 193, 197, 235: Ablaufbeschriftungen, nichts übernommen.

### `src/telco_radar/collect/lieferzeit.py`
- Obergrenze Lieferzeit (63): mehr ist Vorbestellung mit offenem Termin oder Lesefehler; solche Werte gehen in Quarantäne.
- Lagerengpass (67): Signal ist der Sprung ("2-3 Werktage" auf "mehrere Wochen"), nicht die absolute Zahl.
- Beobachtungstiefe (73): Zeitreihe braucht Tiefe, eine JSON-Datei im Repo braucht ein Ende.
- Kontext-Muster (95): ohne Kontext läse der Regex "24 Monate Laufzeit" als Lieferzeit.
- Trennung (264): an Zeilen und Trennzeichen, NICHT am Punkt; "Nicht auf Lager (Lieferzeit ca. 14 Tage)" zerfiel am "ca." und las sich als "auf Lager".
- Platzhalter (338): ein durchgerutschter Platzhalter ist keine Messung.
- Zeilen 79, 111–118, 188, 344, 432: Beispiele/Feldwerte/Abschnittsüberschriften/noqa, nichts übernommen.

### `src/telco_radar/collect/newsroom.py`
- Dateiendungen/Drittanbieter (44, 50, 54): PDFs normal ausgeschlossen, aber TPG Telecom veröffentlicht Meldungen als Überschrift plus PDF – dort ist das PDF der Artikel, ein konfigurierter `item_selector` darf sie behalten. Börsenmeldungs-Anbieter (z. B. True Corporation/SET) dürfen als Fremddomain gelten, nur bei verifiziertem `item_selector`. Mehrteilige öffentliche Suffixe (`tim.com.br`): sonst bliebe nach Abschneiden eines Labels `com.br`.
- `_URL_DATE` (104): `(?![0-9])` nötig; sonst wird die ID in `.../fifa-wm-2030-1116606` als 16.11.2030 gelesen und vom Frischefilter als "Zukunft" verworfen. Monatsgruppe nimmt jedes Wort, `_MONTHS` entscheidet; "de" dazwischen für pt/es ("30 de julho de 2026").
- Navigationsetiketten (131, 162): nur wenn sie der ganze kurze Titel sind (optional "of [the] <owner> newsroom"); "Social media ban for kids", "FAQ: neue Regeln" sind echte Überschriften. Datumsetikett (176): nur Füllwörter davor, sonst steht das Datum im Satz ("Vodafone announces on 15 July 2026 …") und bleibt.
- `_MONTHS` (276): nicht englische Monatsnamen nach ersten drei Buchstaben, nur eindeutige; französisch "jui" fehlt (juin/juillet). Ohne sie bleibt z. B. "24 Temmuz 2026" (Turk Telekom) undatiert, undatierte Meldungen sortieren unter die Analysten-Regionsobergrenze und werden nie gelesen.
- Web-Component-Karten (318): Modyo/Andino (Entel) betten die Liste als JSON im Attribut `eds-card` ein, im statischen HTML; eigener Extraktor vor der `<a>`-Heuristik.
- AEM `datamodel` (398): Optus, Singtel liefern Artikel als HTML-escaped JSON im Attribut `datamodel` unter "articles"; Headless-Render scheitert an der Bot-Sperre, statisches HTML reicht; gleiche Form, andere Feldnamen (Key-Tupel).
- Datum aus Etikett (468): "15 July 2026, 08:30 AM" ist lokales Betreiberdatum; `curatorAsDate` (Epoch ms) landet nach UTC einen Tag früher – Etikett bevorzugen, Zeitstempel als Rückfall.
- Karten-Überschrift (503–531): `item_root` ist der synthetische Wrapper; Aufstieg bei direktem Kind abbrechen, sonst löst jedes Item auf die erste Überschrift auf. Telecom Argentina: Titel als `<p class="...title...">`. e&-Kacheln: kurze `<h5>`-Kategorie vor `<h2>` – den längsten Überschriftentext nehmen.
- Datum (544, 559): Pfade mit `/07-2026/`; Jahr in der Überschrift ("Strategie 2030") kann als Datum durchrutschen – Zukunft gilt als kein Datum, dann zählt der Kartentext.
- Screenreader-Labels (620): AT&T wiederholt Spaltenköpfe je Zeile als `<span class="pr-mobi-headers">`; sie klebten vor jedem Titel.
- Selektor-Vertrauen (652–681): PDF-Links und Fremddomain nur bei explizitem `item_selector`; opake Slugs ohne news/press-Stichwort; echter Pfad statt Sektionswurzel.
- Titel (686–760): SK Telecom wickelt Karte samt Zusammenfassung in ein `<a>` (Text tausende Zeichen) – Nachfahre mit Klasse "title" zuerst; Three UK ("Press release 22nd Jul 2026 Deals <headline>") – Nachfahre heading/title nur akzeptieren, wenn er den Titel VERKÜRZT; e&: Überschrift als Geschwister-`<h1>`–`<h6>`, Anker "Read more"; AT&T-IR-Tabelle: Titel in Nachbarzelle, Anker nur Icon; Deutsche Telekom: Titel nur in title/aria-label mit Präfix ("Media information: ").
- `allow_short_titles` (757): Quelle muss kurze Titel ("Q1 Results", RNS) ausdrücklich zulassen; "About Us"-Fehltreffer sind gleich kurz.
- Datumssuche (775–808): Nachfahre mit Klasse "date" (SK Telecom "reg-date") zuerst, `[:100]`; bei verengter Karte der EIGENE Kartentext vor Aufstieg (Three UK: Geschwister-Karten unter einem div gäben jeder Meldung das Datum der ersten); `<tr>` vor div/li/article (Investegate; sonst Datum der ganzen Tabelle); danach ganzer Item-Container; Monatsgenauigkeit ist besser als nichts.
- Rest (27, 31, 232, 252, 289–316): Muster-Beschriftungen, Sprachgruppen, Beispiele, nichts übernommen.

### `src/telco_radar/collect/newsroom_js.py`
- Stylesheets (26): bewusst NICHT geblockt; Zain koppelt das Befüllen der Artikelliste an CSS-Sichtbarkeit (IntersectionObserver-Lazy-Load), Blocken brach Inhalte still.
- Cookie-Banner (32): Schaltflächen gängiger CMPs (OneTrust, Cookiebot, generisch); ein Banner kann den Lazy-Load blockieren; Klick vor der Wartezeit, jeder Selektor mit kurzem Timeout (1200 ms), Fehler still (meist gibt es kein Banner).
- HTTP/1.1 erzwungen (59): Optus scheitert von Rechenzentrums-IPs mit ERR_HTTP2_PROTOCOL_ERROR; jeder Server spricht HTTP/1.1.
- Dev-Proxy (67): nur Dev-Sandbox, TLS-Proxy verschluckt sich an Chromiums ClientHello (GREASE/Post-Quanten); in CI/Produktion ungesetzt (siehe `scripts/inspect_dom.py`).
- `NACHLADEZEIT_MS` (101): feste Wartezeit statt networkidle, weil viele Telco-Seiten Long-Poll/Analytics offen halten und das ganze Timeout-Budget verbrennen; 1,8 s war zu kurz und lieferte fast leere Karten.
- Zeile 99: noqa, nichts übernommen.

### `src/telco_radar/collect/promo_snapshot.py`
- Meta-Tags (82): Bildquellen nach Priorität, bewusst nur seitenweit (ein Hero-Bild je Marke); Zuordnung einzelner Angebote zu Bildern bräuchte Selektor-Pflege oder Vision-Extraktion und wäre fragiler. Fehlendes Bild ist nie ein Fehler, die Vorlage fällt auf eine Farbkachel zurück.
- Link-Kandidaten (95): höchstens 30 je Marke an das LLM (jeder Kandidat kostet Prompt-Token); genug für die wenigen echten Angebote (`promo_analyst._MAX_ENTRIES_PER_PAGE=6`).
- Bildkandidaten (105): 60; größte gemessene Seite winSIM hat 66 `<img>`, davon 25 über 400 px; Seiten tragen viel mehr Bilder als brauchbare Links (Gerätefotos, Testimonials, Netzkarten).
- Bildsuche behält `<header>` (111): Kampagnenmotiv steht dort oft (o2online.de, otelo.de, congstar.de); sonst fällt das beste Bild weg.
- Endungen (128): Pfad ohne Endung (CDN mit Query) fällt NICHT durch, der Download misst ohnehin nach.
- Tracking-Parameter (132): ALDI TALK `FF_*`, `utm_*`; nur für die interne `content_hash()`-Signatur entfernt, gespeicherte URL bleibt unberührt (o2-Parameter `ratenzahlung`/`zielgruppe` wählen die Tarifvariante, sind kein Tracking; Quelle `promo-tiefenlinks-konzept.md`, Premortem c).
- Breite (301): angekündigte Breite schlägt unbekannte, größte gewinnt; gemessen wird später mit Pillow.
- Entfernter Screenshot-Weg (426): bis 07.08.2026 gab es `_dismiss_cookie_banner()` und `capture_hero_image()` (Chromium je Marke, 1280x720 aus dem Viewport). Messung: von 15 Screenshots zeigten zwei das Cookie-Banner (1&1, congstar), einer war weiß, alle zeigten ein Muster statt der Aktion. Antonio: "Bei vielen sieht man nur die Cookies. Und so ein Screenshot hilft überhaupt nicht." Ersetzt durch `extract_image_candidates()` plus `promo_bilder.py` (wie die Marktrecherche seit 06.08.2026); ein Chromium-Start je Marke entfällt.
- Zeilen 101, 243, 381: Containerhinweis, noqa, nichts übernommen.

### `src/telco_radar/collect/rss.py`
- `MAX_ENTRIES_PER_FEED` (24): DECKEL, kein Ziel; am 08.08.2026 von 40 auf 60, weil die zehn ergiebigsten Quellen exakt 40 lieferten (Light Reading, Telecoms.com, The Fast Mode). Zwischen Freitags- und Dienstagslauf liegen vier Tage, 12 Meldungen/Tag überschreiten 40. Preis ist Laufzeit (mehr Analysten-Stapel); gemildert durch Ereignis-Clustering (`analyze/clustering.py`), Job-Timeout 50 min gegen zuletzt 27,4 min.
- Textdatum (53): feedparser parst nur RFC822/ISO; Fierce Network ("Jul 31, 2026 12:57pm") bliebe undatiert und fiele unter die Regionsobergrenze; Rückfall auf den Newsroom-Textparser.
- Datum im Link (64): Bundesnetzagentur-Feed hat weder pubDate noch dc:date, Pfad trägt es (`/Pressemitteilungen/DE/2026/20260806_Agnes.html`); ohne Ausweg fiele eine Quelle durch Kriterium 3 des Abnahme-Checks (>= 80 % datiert), undatierte Meldungen sind faktisch unsichtbar.
- Pfadformen (78): `/2026/08/06/`, `/2026-08-06-`, `/20260806_`; bewusst NICHT sechsstellig (260806), das fände jede Artikelnummer.
- `VOLLTEXT_MINDESTLAENGE` (128): 1200 Zeichen absolut, nicht als Faktor des Teasers; digi.no, Messung 13.08.2026: 45 Zeichen Teaser, 141 Zeichen Extrakt hinter Paywall wären "3,1x länger", also ein Treffer.
- Wiederholung (209): ein Feed kann HTTP 200/202 liefern und kein Feed sein; Telecoms Tech News liefert in etwa 4 von 10 Läufen eine WAF-Captcha-Seite, zwei Joomla-Feeds (The Fast Mode, Developing Telecoms) gelegentlich abgeschnittenes XML; sofortiger zweiter Abruf hilft.

### `src/telco_radar/collect/tarif_crawler.py`
- Felder (61): Reihenfolge = Reihenfolge im Meldungstext. Kleingedrucktes (77, A9): Felder, die sich ohne Preisbewegung ändern; Drosselgrenze 80 GB auf 50 GB bei gleichem Preis ist eine unsichtbare Preiserhöhung – Grund für den Radar.
- Lesarten (121–161): `dokumente` (Regelfall, verlinkte Pflichtdokumente via `tarif_pdf`), `ldjson` (Einstiegsseite IST die Nutzlast, schema.org), `kacheln` (o2: ein ld+json mit nur BreadcrumbList, übrige Pflichtblätter unter `/assets/`, das die robots-Gruppe sperrt), `telekom_kacheln` (React-CSS-Modul-Klassen `TariffTileModified_...`; es zählt der DURCHGESTRICHENE Preis, nicht der große "Ø"-Kombipreis; Messung in `tarif_telekom_kacheln.py`). Liste der gebauten Methoden steht einmal hier, gegen die sich Konfiguration und Test messen.
- `ausschliessen` (171, P3-E1 28.09.2026): noch verlinkte, nicht mehr verkaufte Dokumente; Suche in Adresse UND Linkbeschriftung; nicht geholt, Stand im Bestand als zurückgezogen markiert (sonst bliebe er "aktueller" Tarif).
- Absender-Override (179): `tarif_quellen.yaml` pro Anbieter; Hintergrund siehe betrieb.md; ohne Zeile bleibt es `None` und `http_cfg` unverändert (BRIEF_TELEKOM_TAEGLICH_R3_E4).
- Unbekannte Methode (234, 920): wird nicht still zur Vorgabe, sondern fällt in `sammle()` als Fehler auf; sonst läse man eine Shop-Seite als Dokumentverzeichnis mit null Links.
- Tarifname (256): Gattung in Klammern ("(Postpaid Mobilfunk)", "(Mobilfunk)") ist Einordnung des Blattes; sonst hieß congstars Schlüssel `congstar:allnet-flat-l-postpaid-mobilfunk` und eine Angabe "Allnet Flat L" traf ihn nie.
- Slug-Datum (338): Telekom-Slug endet auf Vermarktungsdatum (`magentamobil-l-20240801`); nur vierstellige Jahre ab 2000, wie bei rss.py.
- Auswahl (394, 410): je Wunsch ein Fach plus Rest, innerhalb Seitenreihenfolge statt Alphabet (`Produktinformationsblatt_549.pdf` vor `_9001.pdf` ist eine Münze); REIHUM statt Fach für Fach, gemessen 04.09.2026: `magentamobil-s-` trifft neun Dokumente, Deckel zwölf brachte NEUNMAL S und nie M, L, XL, Basic; wie `_interleave_by_source` in der Pipeline.
- Wiederlesen (463): wieder gelesen = wieder im Sortiment, früherer Rückzug (`ziehe_zurueck`) erlischt.
- Vergleich (531–550): leerer String ist ein fehlender Wert (`volumen_automatik` startet als ""); ein diesmal nicht gefundenes Feld ist Ausfall, nicht Änderung ("80 GB -> nicht angegeben" wäre die häufigste Falschmeldung); "nicht angegeben -> unbegrenzt" beim Volumen ist keine Änderung (P3, 28.09.2026: o2-Kachel schrieb "Unbegrenzt" als None, Vodafone-XL-Blatt "Unlimitierte Highspeed-Daten" wurde nicht gelesen); neu hinzugekommenes Feld zählt weiter (`test_neu_hinzugekommenes_feld_zaehlt`), "100 GB -> unbegrenzt" bleibt Änderung.
- Meldungstext (584): mit Präposition, damit beide Sätze deutsch bleiben ("im Produktinformationsblatt", "auf der Shop-Seite").
- `origin` (623): bleibt Name des ZWEIGS, nicht der Quellenart; sagt der Pipeline, welcher Sammler es erzeugte, ein zweiter Wert wäre ein unbekannter Zweig.
- Meldungs-ID (628): aus Tarif UND Dokument-Hash; zwei Änderungen desselben Tarifs müssen zwei Meldungen sein, sonst hält der Seen-Store die zweite für gemeldet.
- Zwei Lesarten = zwei Zeitreihen (662): live 04.09.2026: o2-PIB und o2-SIM-only-Kachel nennen beide "O2 Mobile Unlimited M Flex" (gleiche Tarif-ID); sonst wurde der Kachelsatz zur nächsten FASSUNG des Blattes (Blatt nennt Mindestlaufzeit, Flex-Kachel keine). `preistyp` ist dafür gebaut ("Beide dürfen auseinanderlaufen; die Abweichung ist die Auskunft"). Zusatz = PREISTYP, je Quelle konstant, also stabil; ein Inhaltshash zerfiele die Zeitreihe bei jeder Preisänderung. Wer zuerst da war, behält den kurzen Schlüssel (Bestandsschutz, keine Rangfolge).
- Gleiche Titelzeile im SELBEN Lauf (701): live 08.08.2026: o2 `o2-home-l-flex` und `o2-home-l-175-flex`, beide "O2 Home L 175/250/300 Flex"; sonst wechselt der Diff bei jedem Lauf hin und her. Nacheinander = Versionsfolge, im selben Lauf = zwei Produkte.
- Neuer Hash, gleiche Werte (734): Layoutänderung, keine Meldung.
- Leere Befunde (821, 953, 975): Seite mit 200 und 450 KB ohne Tarif = Formatänderung oder Challenge, Status und Größe gehören in die Zeile (Telekom-Lehre 04.09.2026, Hintergrund in betrieb.md); `verlinkt` zählt Kandidaten nach "jüngste Fassung", die rohe Zahl steht in der Protokollzeile der Einstiegsseite.
- Herkunft (847, 892, 1042): Fingerabdruck des Knotens, alle Tarife der Seite teilen die Adresse; je Lauf merken, welche Tarif-ID von welcher Adresse kam.
- `setdefault` (940): innerhalb einer Seite gewinnt der ERSTE Linktext, über Einstiegsseiten gilt dasselbe; `update` wären zwei Regeln für dieselbe Frage.
- Anbieter aus Config (1029): ohne Fundstelle und bewusst nicht über `setze()`; Belegpflicht gilt für Dokumentinhalt, eine erfundene Fundstelle wäre die Unehrlichkeit, gegen die `pruefe_belege()` gebaut ist.
- Absender-Kopie (896): Quelle mit `user_agent:` bekommt eigene Kopie von `http_cfg`, andere sehen es unverändert.
- Rest (309, 761, 764, 809, 948, 1014): Einstiegsseite kein Dokument, HTML-/Textform der Vertragszusammenfassung, noqa – nichts übernommen.

### `src/telco_radar/collect/tarif_einsundeins_simonly.py`
- Absender (81): BRIEF S-5; weicht vom Per-Anbieter-Override im Gerätezweig nur im Kontakt-Zusatz ab, beide ehrliche Kennungen (`collect.http._ist_ehrliche_kennung`).
- Abstand (88): keine Crawl-delay in den robots beider Domains, Abstand ist eigene Zurückhaltung wie `einsundeins._GEBUEHR_ABSTAND`; zur LAUFZEIT auflösen (359), weil ein Test, der den Abstand am Modul-Attribut auf 0 setzt, sonst ignoriert würde.
- Muster (93): "Unlimited pro Monat" trifft das GB-Muster nicht, unbegrenzt wird keine Zahl (kein `volumen_gb`); "3 Monate je 9,99 €" -> (3, 9.99).
- Dokumentzeile (101): im Tarifdetails-Dokument ist die OHNE-Smartphone-Zeile richtig (S2-C hat "Tarif mit Smartphone" im Gerätezweig).
- Name (192): ohne kanonischen Namen keine stabile `sim_only_id`, der Slug ist nur Abkürzung.
- "DAUERHAFT" (203): Etikett sagt, der Kachelpreis ist unbefristet; Kachel mit Aktionsphase trägt es nicht, Dauerpreis daneben, Phase im `text-with-bg-secondary`-Kasten.
- Messwert (229): der ganze Messwert zählt, nicht nur der Preis; andere Aktionsphase oder anderes Volumen ist genauso uneindeutig.
- Gegenprobe (287): fehlt das Kreuzzeug (ld+json-Namen driften von Kacheltiteln), bleibt der Preis, aber der Verfall der Gegenprobe wird gemeldet.
- Zeilen 374, 406: noqa.

### `src/telco_radar/collect/tarif_kacheln.py`
- Kachelmarkierung (107): TEILKLASSE statt Klassenliste; Kacheln tragen daneben `teaser-neuro`, `teaser-highlight`, `teaser-switchable`; eine davon zu verlangen hinge an Design statt Sache.
- Volumen (114): nur GB; MB in einer Kachel ist eine Geschwindigkeit ("5G mit max. 300 MBit/s"), deshalb nur im Volumenteil der Überschrift gesucht; Unlimited-Kacheln heißen genau "Unbegrenzt".
- Beispiele (122, 125, 205): "+ einm. Anschlusspreis 0,00 € statt 39,99 €" -> 0,00; "24 Monate" im Auswahlknopf; "Monatlich kündbar" ist Aussage ohne Monatszahl.
- Kopie (181): `extract()` verändert den Baum, Kachel wird danach noch für den Rohtext gebraucht.
- Rohtext (263): IST die Kachel plus die Adresse für den Slug, sonst stünde `buendel_slug` mit einer Fundstelle da, die im Rohtext fehlt und `pruefe_belege()` zu Recht wirft.
- Fingerabdruck (297): an der KACHEL, nicht der Seite (zwölf Tarife sonst gleicher Hash).
- Dublette (327): o2 liefert die Übersicht in mehreren Reitern, identische Kacheln sind kein zweiter Datensatz.

### `src/telco_radar/collect/tarif_ldjson.py`
- Volumen (85): steht in `description`, nicht im `name`; ohne "MB", da dort eher Drosselgeschwindigkeit.
- Rohtext (200): IST der Knoten, jede Fundstelle steht wörtlich darin, `pruefe_belege()` prüft echte Zusage.
- Fundstelle (208): Seite, auf der die Zahl stand; `offers.url` ist Bestellweg (1&1: gleiche Adresse für alle sieben Tarife).
- Fingerabdruck (227): am KNOTEN, nicht an der Seite (sieben Tarife, sonst alle bei einer Änderung geändert).
- Dublette (254): gleicher Knoten zweimal (Shop liefert denselben Graphen für Kopf und Fuß).

### `src/telco_radar/collect/tarif_pdf.py`
- Dokumenterkennung (58): ohne einen der Sätze ist es kein PIB und keine Vertragszusammenfassung.
- Name (145, 155): ohne Klammerzusatz erste Nicht-Fließtext-Zeile; offene Klammer am Ende ist PDF-Zeilenumbruch (congstar XL: "(Postpaid" – Wert abschneiden, BELEG bleibt die ganze Zeile).
- Kündigungsfrist (189): zwei Satzstellungen – Telekom "Kündigungsfrist ein Monat" (Zahl danach), o2 "mit einer Frist von 1 Monat" (Zahl davor); die erste Fassung ließ bei beiden o2-Dokumenten das Feld leer.
- Unbegrenzt (297, 313): o2 "Unlimited", Vodafone Mobil XL "Unlimitierte Highspeed-Daten … Fair Use von 135 GB" (PIB Juli 2026); Fair Use ist keine Drossel, danach wird je MB berechnet. Unlimited ist Aussage, kein fehlender Wert; als None fiele der Tarif auch aus der Positionskarte.
- Grundpreis-Fälle (378–446): 1) Staffelzeile >= 3 Beträge unter Entgelt-Bezeichner, auf ROHZEILEN (Zuordnung hängt an Zeichenposition); 2) senkrechte Tabelle (Vodafone) VOR den Einzelbetragsmustern, sonst wird der erste Betrag der Tabelle als Grundpreis gelesen; 3) Einzelbetrag unter Bezeichner; 4) Bezeichner mit Produktnamen (congstar "Entgelt Allnet Flat L (ohne Endgerät) 29,00 € / Monat", 04.09.2026) – Monatsangabe HINTER dem Betrag verlangt; 5) einzelner Listenpreis ohne Phasenspalten (CallYa "Listenpreis inkl. MwSt. 14,99 €") bewusst NACH der Tabellenform, deren Kopfzeile denselben Bezeichner ohne Betrag trägt.
- Spaltenzuordnung (510–552): WORTWEISE zur nächsten Betragsspalte; Fallen: "mit Premium- mit Premium-" sind zwei Spalten mit einem Leerzeichen (Trennung an zwei Leerzeichen reicht nicht), harter Zeichenschnitt zerschnitt "Smartphone" zu "Smartphon"+"e". Spaltenbreite wird GEMESSEN: "Hardware" stand bei zwei Telekom-Dokumenten 15 bzw. 14 Zeichen von der ersten Betragsspalte, feste Toleranz kippte auf "ohne Smartphone Hardware". Links der ersten Spalte um mehr als eine halbe Spaltenbreite = Zeilenbeschriftung, keine Schwelle. Umbruch in der Spalte ("mit Premium-"/"Plus-Smart-"/"phone") ist Überschrift; Trennstrich aus Umbruch entfernen ("Smart-phone" -> "Smartphone"), echten behalten ("Top-Smartphone").
- Vodafone-Tabellenform (558): Zeilen = Kategorien, Spalten = PREISPHASEN ("Monat 1-24", "ab Monat 25" sind vom Anbieter selbst ausgezeichnete Phasen, einzige solche Stelle; bis 04.09.2026 stand überall die Ersatzphase "1 bis Vertragsende" aus `lies_text`). Gelesen auf NORMALISIERTEM Text (Etikett vorn, Beträge dahinter, Zeichenposition nicht nötig). GEMESSEN 04.09.2026 an elf vermarkteten Vodafone-Tarifen (VF-Mobil-XS/S/M/L/XL mit und ohne Smartphone, Smart XS): in ALLEN elf gleicher Betrag in beiden Phasen; Struktur trotzdem echt, dort wird eine Rabattphase auftauchen.
- Gerätestufe (591): Vodafone stellt Tarifoptionen ("ohne/mit 5 Jahresversprechen", "mit zusätzlichem Datenvolumen") in dieselbe Tabellenform; als Gerätepreisstaffel abgelegt wäre das eine Falschaussage. Tabellenkopf (597): "Listenpreis" allein reicht nicht, erst mit Monatsspalte.
- Vier-Wochen-Takt (601): Preis je VIER WOCHEN ist kein Monatspreis (`Tarif.grundgebuehr` = Monatspreis, `tco_24` über 24 Monate; 13 Zyklen sind nicht 12 Monate; Umrechnen wäre Rechnung des Projekts, keine Angabe des Anbieters). congstar "Entgelt Prepaid Allnet M … 10,00 € / 4 Wochen", Vodafone CallYa "Listenpreis inkl. MwSt. 14,99 €" über "Vertragslaufszeiten 4 Wochen" (04.09.2026). Fall 4 fällt durch "/ Monat" von selbst richtig, Fall 5 braucht die Sperre (sonst stand CallYa mit 14,99 EUR als Monatspreis). Zwei Muster (`_ABRECHNUNG_IN_WOCHEN`, `_VERTRAG_IN_WOCHEN`), weil der Takt bei congstar am Betrag, bei Vodafone am VERTRAG steht, Preis eine Zeile weiter ohne Zeitangabe; erste Fassung prüfte nur die Trefferzeile und lief am Begründungsdokument `vodafone_callya_allnet_flat_m` vorbei (Fixture liegt bei). Gebunden an Vertragslaufzeit, nicht an "Wochen": "Kündigungsfrist 4 Wochen" kommt bei monatlich abgerechneten Verträgen vor.
- `_TABELLENTIEFE` (633): 15; längste Staffel im Bestand hat sechs Zeilen (Vodafone "mit Smartphone") plus Zwischenzeilen ohne Betrag; Notbremse, echte Grenze ist die erste betragslose Zeile nach der ersten Preiszeile.
- Phasenzuordnung (719): nur wenn Spalten- und Betragszahl passen; geratene Phase sieht aus wie eine Messung, schlimmer als keine – dann Ersatzphase aus `lies_text`.
- Anbieterreihenfolge (769): congstar VOR Telekom ist Korrektheit, nicht Reihenfolge; congstar-PIB-Fuß "eine Marke der Telekom Deutschland GmbH", bis 04.09.2026 rettete nur ein Zeilenumbruch mitten im Satz; eigene Tarife zu eigenen Preisen (29,00 gegen 59,95 EUR).
- Rohzeilen (800): behalten Spaltenausrichtung, nur unsichtbare Zeichen entfernen; sonst Gerätestaffel nicht zuzuordnen.
- Ersatzphase (822): PIB nennt Listenpreis ohne Rabattphasen; eine Phase über die ganze Laufzeit ist ehrlich, Effektivpreis rechnet ohne Sonderfall.
- Rest (114, 277, 788): Abschnittsüberschriften, "Raten in derselben oder nächsten Zeile" – nichts übernommen.

### `src/telco_radar/collect/tarif_telekom_kacheln.py`
- Wrapper-Muster (91): äußerer Kachel-Wrapper trägt genau EIN CSS-Modul-Hash-Suffix; Unterknoten ("...__hero__27i7x", "...__strike-price__3Py6_") haben zusätzlich einen Teilnamen und werden bewusst NICHT getroffen.
