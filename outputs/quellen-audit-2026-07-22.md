# Telco Radar — vollständiger Quellen-Audit

Stand: 22.07.2026. Geprüft wurden `config/watchlist.yaml`, `config/news_sources.yaml`, die Collector unter `src/telco_radar/collect/`, `scripts/validate_sources.py`, die letzten fünf Workflow-Läufe sowie Rohdaten, Reports und die generierte Website. HTTP- und Collector-Werte stammen aus externen `curl`-/Playwright-Abrufen; `SKIP` bedeutet bewusst nicht gecrawlt, nicht „ungeprüft“.

## Ergebnis in Kürze

- 95 eindeutige Quellen: 69 crawlbare Betreiberquellen, 14 Fachpresse-Feeds, 12 offizielle Referenzquellen.
- Health-Check nach der Reparatur: 51 `OK`, 29 `EMPTY`, 3 echte Laufzeitfehler, 12 `SKIP`.
- Die drei klar falschen Quellen wurden repariert: Verizon-Parenting-RSS → Verizon-Newsroom, 1&1-United-Internet-IR → 1&1-Pressefeed, TIM-Brasil-RSS mit Smoke-Tests → offizieller Pressebereich. `inside digital` wurde entfernt.
- Die verbleibenden `EMPTY`-Quellen sind überwiegend JS-/SPA-/Bot-/Selector-Probleme; sie wurden nicht wegen eines einzelnen temporären Abruffehlers entfernt.

## Audit-Tabelle — Betreiberquellen

| Quelle / Betreiber | URL | HTTP / Abruf · Extraktion | Inhaltsqualität / Relevanz | Problem · Empfehlung |
|---|---|---|---|---|
| Vodafone Group · json_api | <https://www.vodafone.com/tools/urlproxy/advurlproxy.aspx?settingname=news-feed&categories=*&tags=*> | 200 · `OK 16/16` | Offizielle, datierte Vodafone-Meldungen; technisch sauber | Themen teils Policy/Netz statt Differenzierung · **behalten** |
| Vodafone Deutschland · newsroom_js | <https://newsroom.vodafone.de/> | 200 · `OK 2/0` | Offizielle Seite, aber aktuell kaum extrahierbare News | JS-/Presspage-DOM; Treffer waren Medien-/Kontakt-Navigation · **reparieren** |
| Deutsche Telekom · newsroom_js | <https://www.telekom.com/en/media/media-information> | 200 · `EMPTY` | Seite erreichbar, echte News liegen nicht im verwertbaren Linkset | Nach Navigation-Filter leer; spezifischen Selector/API ergänzen · **reparieren** |
| O2 Telefónica Deutschland · rss | <https://www.telefonica.de/o2/rss/news?category_id=11;pubdate=1> | 200 · `OK 20/20` | Offizieller Feed, datierte Presse-/Produktmeldungen | Ältere Meldungen im Feed; Freshness-Filter greift · **behalten** |
| Telefónica · rss | <https://www.telefonica.com/en/feed/> | 200 · `OK 10/10` | Offizieller Feed, aktuelle Press-/Blog-Inhalte | Blogs und Policy neben News · **behalten**, redaktionell filtern |
| Orange · newsroom | <https://www.orange.com/en/newsroom> | 403 Browser-UA, Fallback erfolgreich · `OK 5/5` | Offizielle Meldungen extrahierbar | Bot-Schutz und Finanzmeldungen im selben Newsroom · **behalten** |
| BT Group · rss | <https://newsroom.bt.com/feed/en> | 200 · `OK 25/25` | Sehr gute, datierte Betreiberquelle | B2B/Netz/Finanzen werden mitgeliefert · **behalten** |
| Swisscom · newsroom_js | <https://www.swisscom.ch/en/about/news.html> | 200 · `OK 3/0` | Offizielle Links, Datumsfelder fehlen teilweise | JS-/Datumserkennung schwach · **reparieren** |
| Telia · newsroom_js | <https://www.teliacompany.com/en/newsroom> | 200 · `OK 5/0` | Offizielle Inhalte, Titel/URLs brauchbar | Undatierte Treffer; Archiv-/JS-Struktur · **reparieren** |
| KPN · rss | <https://www.overons.kpn/nieuws/feed/en> | 200 · `OK 25/25` | Datiert und ergiebig; auch Kundenangebote | Finanzen/Personal neben relevanten Services · **behalten** |
| Proximus · newsroom | <https://www.proximus.com/news.html> | 200 · `OK 3/3` | Direkte, datierte Press Releases | Niedrige Ergiebigkeit, aber brauchbar · **behalten** |
| TIM · newsroom_js | <https://www.gruppotim.it/en/press-archive.html> | 200 · `EMPTY` | Erreichbar, Collector findet keine Artikel | JS-/Archivseite ohne passende DOM-Links · **reparieren** |
| Liberty Global · newsroom_js | <https://www.libertyglobal.com/news-insights/featured-news-insights/> | 200 · `EMPTY` | Offizielle Seite, keine extrahierbaren Artikel | JS-/Featured-Content-API nötig · **reparieren** |
| VEON · newsroom | <https://www.veon.com/newsroom> | 200 · `OK 30/18` | Viele echte, datierte Meldungen | Finanz-/IR-Meldungen im Stream · **behalten** |
| Telenor · newsroom | <https://www.telenor.com/media/newsroom/> | 200 · `OK 10/6` | Echte Pressemitteilungen und Announcements | Teilweise interne/gesellschaftliche Meldungen · **behalten** |
| Turkcell · newsroom_js | <https://medya.turkcell.com.tr/basin-bultenleri/> | 200 · `EMPTY` | Offizielle türkische Presseseite | JS/API nicht extrahiert; kein stabiler RSS-Ersatz · **reparieren** |
| Iliad · newsroom_js | <https://www.iliad.fr/en/press> | 200 · `EMPTY` | Offizielle Seite, aber sehr kleine/JS-lastige Antwort | Falscher/älterer Press-Pfad oder API nötig · **reparieren** |
| 1&1 · rss | <https://unternehmen.1und1.de/presse/feed> | 200 · `OK 10/10` | Offizieller 1&1-Feed; konkrete TV-, Router- und Produktmeldungen | Ersetzt die falsche United-Internet-IR-Zuordnung · **behalten** |
| Bouygues Telecom · newsroom_js | <https://www.corporate.bouyguestelecom.fr/presse-et-actualites/> | 200 · `OK 22/13` | Echte offizielle Artikel, einige Datumsfelder fehlen | News-/Perspectives-/CSR-Mix · **behalten**, Selector verbessern |
| A1 Telekom Austria · newsroom_js | <https://newsroom.a1.net/> | 200 · `OK 12/10` | Gute aktuelle Meldungen und Partnerschaften | Glasfaserlastig, aber real telcorelevant · **behalten** |
| Tele2 · newsroom | <https://www.tele2.com/media/press-releases> | 200→`/media/` · `OK 1/1` | Echtes, datiertes Dokument | Sehr niedrige Ausbeute · **reparieren** |
| Elisa · newsroom_js | <https://elisa.com/corporate/news-room/> | 200 · `OK 4/4` | Datiert, offizielle Pressemitteilungen | B2B/Managed-Security neben Consumer-News · **behalten** |
| Three UK · newsroom_js | <https://www.threemediacentre.co.uk/press-release-browser/> | 200 · `EMPTY` | Offizielle Media-Centre-Seite | Browser-/Filterstruktur liefert keine Artikel · **reparieren** |
| Cosmote · newsroom_js | <https://www.cosmote.gr/otegroupcompanysite/en/media/press-releases> | 200, 212-Byte-HTML · `EMPTY` | Praktisch leere Antwort | Kaputter/alter Pfad oder Bot-/JS-Shell · **reparieren oder ersetzen** |
| Verizon · newsroom_js | <https://www.verizon.com/about/news> | 200 · `OK 2/0` | Offizieller Newsroom; besser als der alte Parenting-Feed | Nur Featured-/Alert-Links, undatiert · **reparieren** |
| AT&T · official | <https://about.att.com/newsroom.html> | 403 · `SKIP` | Offizielle Referenz, Bot-Schutz bestätigt | Nicht crawlbar ohne geeigneten Proxy/API · **behalten** als Referenz |
| T-Mobile US · official | <https://www.t-mobile.com/news> | 200 · `SKIP` | Offizielle Referenz; Crawl bewusst deaktiviert | Collector würde Bot-/JS-Risiko eingehen · **behalten** als Referenz |
| Comcast · rss | <https://corporate.comcast.com/rss> | 200 · `OK 40/40` | Technisch gut, aber viele lokale Broadband-/Personalthemen | Nur teilweise Mobile-/Consumer-Wettbewerb · **behalten**, filtern |
| Charter Communications · newsroom_js | <https://corporate.charter.com/newsroom> | 200 · `EMPTY` | Große Seite, keine Artikel aus dem aktuellen DOM | JS-API/Selector fehlt · **reparieren** |
| DISH Wireless · rss | 200 · `OK 40/40` | <https://api.client.notified.com/api/rss/publish/view/53068?type=press> | Offizieller Notified-Feed, datiert | Auch DISH-TV und ältere Inhalte · **behalten**, Freshness/Scope prüfen |
| UScellular · official | <https://investors.uscellular.com/news/default.aspx> | 403 · `SKIP` | Offizielle Q4-IR-Referenz | Bot-Schutz, Q4-API noch nicht angebunden · **behalten** als Referenz |
| Bell Canada · newsroom_js | <https://www.bce.ca/news-and-media/newsroom> | 200 · `EMPTY` | Aktuell extrahierte Links waren nur Media Contacts/Library und wurden herausgefiltert | Echter News-Selector/API nötig · **reparieren** |
| Rogers · official | <https://about.rogers.com/news-ideas/> | 200 · `SKIP` | Offizielle Seite erreichbar | Crawl bewusst nicht aktiviert; Bot-/JS-Risiko · **behalten** als Referenz |
| Telus · official | <https://www.telus.com/en/about/news-and-events> | 403 · `SKIP` | Offizielle Referenz | Bot-Schutz · **behalten** als Referenz |
| América Móvil · official | <https://www.americamovil.com/English/press-releases/default.aspx> | 403 · `SKIP` | Offizielle Referenz | Q4-/Bot-Schutz · **behalten** als Referenz |
| Millicom · newsroom_js | <https://www.millicom.com/media/press-releases> | 200 · `OK 1/0` | Nur ein undatierter, echter Link | Press-Releases-Seite liefert Featured-/JS-Inhalt nicht vollständig · **reparieren** |
| TIM Brasil · newsroom | <https://www.tim.com.br/sobre-a-tim/sala-de-imprensa> | 200 · `OK 5/0` | Offizielle Presseartikel; keine Smoke-/Stage-Einträge mehr | Datum nicht im extrahierten Linktext · **behalten**, Datum verbessern |
| Entel · newsroom_js | <https://informacioncorporativa.entel.cl/sala-de-prensa> | 200 · `EMPTY` | Offizielle Seite, keine Artikel im gerenderten Linkset | JS-/API-Collector nötig · **reparieren** |
| Oi · newsroom_js | <https://www.oi.com.br/sala-de-imprensa/> | 200 · `EMPTY` | Erreichbar, keine verwertbaren Links | JS-/SPA-Pfad oder API nötig · **reparieren** |
| Telecom Argentina · official | <https://institucional.telecom.com.ar/prensa> | 403→`institucional.personal.com.ar` · `SKIP` | Referenz erreichbar, aber Edge-/Bot-Redirect | Crawl nicht stabil · **behalten** als Referenz |
| WOM · newsroom_js | <https://sobrenosotros.wom.cl/wom-en-prensa/> | 200 · `EMPTY` / zeitweise Timeout | Inhalt vermutlich vorhanden, Render-Budget zu knapp | Timeout/JS; nicht wegen eines Einzel-Timeouts entfernt · **reparieren** |
| MTN Group · rss | <https://www.mtn.com/feed/> | 200 · `OK 10/10` | Datiert, offizielle Unternehmens-/Digitalmeldungen | Teilweise Führung/CSR · **behalten** |
| Vodacom · newsroom_js | <https://www.vodacom.com/press-releases.php> | 200 · `OK 30/0` | Viele echte offizielle Artikel | Artikel-URLs tragen kaum Datum · **behalten**, Datum verbessern |
| Safaricom · newsroom | <https://www.safaricom.co.ke/media-center-landing> | 403 Browser-UA/Fallback · `OK 4/3` | Offizielle Meldungen, FAQ-Navigation inzwischen filterbar | Bot-Fallback und einzelne undatierte Treffer · **behalten** |
| Airtel Africa · newsroom_js | <https://airtel.africa/media> | 200 · `EMPTY` | Offizielle Media-Seite, keine Artikel extrahiert | JS-/API-Struktur · **reparieren** |
| stc · newsroom_js | <https://www.stc.com/en/media-center.html> | 200 · `EMPTY` | Erreichbar, keine verwertbaren Artikel | JS-/Lokalisierungsstruktur · **reparieren** |
| e& · newsroom_js | <https://www.eand.com/en/news.html> | 200 · `EMPTY` | Erreichbar, keine extrahierbaren News | JS-/API-Collector nötig · **reparieren** |
| Ooredoo · official | <https://www.ooredoo.com/en/media/news_view/> | 403 · `SKIP` | Offizielle Referenz | Bot-Schutz · **behalten** als Referenz |
| Zain · official | <https://www.zain.com/en/media-center> | 307 Edge-Challenge · `SKIP` | Offizielle Referenz, Bot-Challenge bestätigt | Nicht crawlbar ohne Proxy · **behalten** als Referenz |
| Orange MEA · newsroom_js | <https://www.orange.eg/en/media-center/press-releases> | 200, 246-Byte-HTML · `EMPTY` | Praktisch nur JS-Shell | Falscher/JS-only Press-Pfad · **reparieren oder ersetzen** |
| du · newsroom_js | <https://www.du.ae/about-us/media-centre> | 200 · `EMPTY` | Frühere Treffer waren Support-Artikel; diese werden nun korrekt verworfen | News-API/Selector ergänzen · **reparieren** |
| Maroc Telecom · official | <https://www.iam.ma/groupe/salle-de-presse/communiques-de-presse.aspx> | 403 · `SKIP` | Offizielle Referenz | Bot-Schutz · **behalten** als Referenz |
| Turk Telekom · newsroom_js | <https://medya.turktelekom.com.tr/basin-bultenleri/basin-bultenleri-ve-gorseller> | 200 · `EMPTY` | Erreichbar, keine extrahierbaren Artikel | JS-/Türkisch-Template · **reparieren** |
| KDDI · rss | <https://newsroom.kddi.com/english/news/newsrelease.xml> | 200 · `OK 10/10` | Datiert und offiziell | Enthält IR-Hinweise und PDFs statt News · **behalten**, IR/PDF filtern |
| Bharti Airtel · newsroom | <https://www.airtel.in/press-release> | 200→`/press-release/` · `OK 30/30` | Viele echte, datierte Press Releases | Stark netz-/ausbauorientiert · **behalten** |
| Reliance Jio · newsroom_js | <https://www.jio.com/press-release> | 200→`page-not-found` · `EMPTY` | Falscher/alter Pfad | Offizielle aktuelle Press-URL ermitteln · **reparieren oder ersetzen** |
| Vodafone Idea · newsroom_js | <https://www.myvi.in/media/press-releases> | 200 · `EMPTY` | Erreichbar, keine Artikel extrahiert | JS-/API-Quelle fehlt · **reparieren** |
| Singtel · newsroom_js | <https://www.singtel.com/about-us/media-centre> | 200 · `OK 11/11` | Echte, datierte News Releases | Stock-Exchange-Navigation wird mitgeliefert · **behalten**, IR filtern |
| SK Telecom · newsroom_js | <https://www.sktelecom.com/en/press/press_list.do> | 200→`error.html` · `EMPTY` | Falsches/abgelaufenes Ziel | Aktuelle englische Press-URL/API ermitteln · **reparieren oder ersetzen** |
| KT · newsroom_js | <https://corp.kt.com/eng/html/prcenter/report_list.html> | 200, 1.8-KB-HTML · `EMPTY` | Minimal-/Fehlerseite | JS-/Pfadproblem · **reparieren oder ersetzen** |
| NTT Docomo · newsroom | <https://www.docomo.ne.jp/english/info/media_center/pr/> | 200 · `OK 20/20` | Gute, datierte offizielle Quelle | Netz-/Technologiemix, aber verwertbar · **behalten** |
| SoftBank · newsroom_js | <https://www.softbank.jp/en/corp/news/press/> | 200→`/all/` · `OK 30/30` | Viele datierte, offizielle Meldungen | Hoher IR-/Aktienanteil · **behalten**, IR filtern |
| Rakuten Mobile · newsroom | <https://corp.mobile.rakuten.co.jp/english/news/press/> | 200 · `OK 30/30` | Offizielle, datierte Press Releases | Teilweise Infrastruktur/IR · **behalten** |
| China Mobile · newsroom_js | <https://www.chinamobileltd.com/en/media/press.php> | 403 · `EMPTY` | Bot-Schutz, kein Inhalt | Proxy/API erforderlich · **reparieren** |
| China Telecom · newsroom_js | <https://www.chinatelecom-h.com/en/media/press.php> | 200 · `EMPTY` / Timeout | Timeout und keine Links | Render-/Pfadproblem · **reparieren** |
| Chunghwa Telecom · newsroom_js | <https://www.cht.com.tw/en/home/cht/messages> | 200 · `EMPTY` | Erreichbar, Linkstruktur nicht passend | Selector/API nötig · **reparieren** |
| Telkomsel · newsroom | <https://www.telkomsel.com/en/about-us/news> | 200→Indonesisch · `OK 8/8` | Datiert, konkrete Angebote/Partnerschaften | Sprache/Datumsdarstellung gemischt · **behalten** |
| AIS · newsroom_js | <https://investor.ais.co.th/en/newsroom/set-announcements> | 200 · `EMPTY` | SET-Investor-Seite, keine passenden Artikel | Investor-/JS-API nötig · **reparieren** |
| Viettel · newsroom_js | <https://viettel.com.vn/en/news> | 200 · `OK 1/0` | Ein Treffer war nur „Official Channels“ und wird künftig verworfen | Aktuelle News-API/Selector fehlt · **reparieren** |
| Globe Telecom · official | <https://www.globe.com.ph/about-us/newsroom> | Timeout · `SKIP` | Offizielle Referenz, Abruf instabil | Bot-/Timeout-Problem · **behalten** als Referenz |
| PLDT · newsroom_js | <https://main.pldt.com/newsroom> | 200 · `OK 10/0` | Aktuell vor allem IR-/Disclosure-Navigation | Newsroom-Selector zu breit · **reparieren** |
| Indosat Ooredoo Hutchison · newsroom_js | <https://ioh.co.id/portal/en/iohpressrelease> | 200→Home · Timeout | SPA lädt nicht innerhalb 16 Sekunden | Render-/API-Integration nötig · **reparieren** |
| CelcomDigi · newsroom | <https://corporate.celcomdigi.com/newsroom> | 200 · `OK 30/30` | Konkrete, datierte Consumer-/Business-Meldungen | Text der Karten teils sehr lang; B2B-Mix · **behalten**, redaktionell filtern |
| Maxis · newsroom_js | <https://www.maxis.com.my/en/about-maxis/newsroom/> | 200 · `OK 7/7` | Datiert, echte Service-/Community-News | Teilweise CSR statt Wettbewerb · **behalten** |
| True Corporation · newsroom_js | <https://investor.true.th/en/newsroom/set-announcements> | 404 · `EMPTY` | Veralteter/falscher SET-Pfad | Neue Investor-/Press-URL ermitteln · **ersetzen** |
| Telstra · newsroom_js | <https://www.telstra.com.au/exchange> | 200 · `EMPTY` | Erreichbar, keine Artikel extrahiert | JS-/Selector/API nötig · **reparieren** |
| Optus · newsroom_js | <https://www.optus.com.au/about/media-centre> | HTTP/2-Fehler · `FAIL` | Technischer Abruffehler reproduzierbar; URL selbst antwortet per curl, Chromium scheitert | HTTP/2-/Browser-Fallback oder Alternative · **reparieren** |
| TPG Telecom · newsroom_js | <https://www.tpgtelecom.com.au/media_release> | 200 · `EMPTY` | Erreichbar, keine Artikel extrahiert | Pfad/JS-Selector prüfen · **reparieren** |
| One NZ · rss | <https://media.one.nz/index.rss> | 200 · `OK 10/10` | Offizieller, datierter Feed | CSR/Partnerschaften neben Netz-News · **behalten** |
| Spark · official | <https://www.sparknz.co.nz/news/> | 200→`spark.co.nz/online/about/our-company/news` · `SKIP` | Redirect/Bot-Wall dokumentiert | Residential-Proxy oder Alternative nötig · **behalten** als Referenz |
| 2degrees · newsroom_js | <https://www.2degrees.nz/media-releases> | 200 · `OK 9/9` | Datiert und konkrete Unternehmensmeldungen | Teilweise Studien/CSR · **behalten** |

## Audit-Tabelle — Fachpresse

| Medium | URL | HTTP / Abruf · Extraktion | Inhaltsqualität / Relevanz | Problem · Empfehlung |
|---|---|---|---|---|
| Mobile World Live | <https://www.mobileworldlive.com/feed/> | 403 Browser-UA, Fallback · `OK 30/30` | Gute Telco-Fachpresse, aktuelle Artikel | Bot-Schutz; direkte Links teils 403 · **behalten** |
| Light Reading | <https://www.lightreading.com/rss.xml> | 200/zeitweise TLS-Timeout · `FAIL` im letzten Check | Relevante Telco-Fachpresse | Temporärer Handshake-/Rate-Fehler, nicht dauerhaft kaputt · **behalten**, retry/Monitoring |
| Fierce Network | <https://www.fierce-network.com/rss/xml> | 200 · `OK 25/0` | Relevante Carrier-/Netz-News | Datumsfelder fehlen, Bot-Schutz auf Artikeln · **behalten**, Datum verbessern |
| Total Telecom | <https://totaltele.com/feed/> | 200 · `OK 10/10` | Gute Telco-/Regulierungs-/Netzabdeckung | Viel Infrastruktur/B2B · **behalten**, filtern |
| RCR Wireless | <https://www.rcrwireless.com/feed> | 200 · `OK 10/10` | Gute Carrier-/Technologieabdeckung | Meinungs-/Vendor-Anteil · **behalten** |
| Developing Telecoms | <https://developingtelecoms.com/?format=feed&type=rss> | 200 · `OK 34/34` | Gute internationale Telco-Abdeckung | Infrastruktur/Regulierung dominiert teilweise · **behalten** |
| Mobile Europe | <https://www.mobileeurope.co.uk/feed/> | 200 · `OK 10/10` | Gute Europa-/Vodafone-/Vendor-News | Teilweise Meinungsstücke · **behalten** |
| Broadband TV News | <https://www.broadbandtvnews.com/feed/> | 200 · `OK 10/10` | Sinnvoll für TV-/Content-Bundles und Telcos | Auch Medienbranchen-News ohne Telco-Bezug · **behalten**, filtern |
| Telecoms Tech News | <https://www.telecomstechnews.com/feed/> | 200 · `OK 10/10` | Telco-/Satellite-/Security-News | Teilweise allgemeine Security/Auto · **behalten**, filtern |
| The Fast Mode | <https://www.thefastmode.com/?format=feed&type=rss> | 200 · `OK 40/40` | Viele konkrete Operator-Partnerschaften/Services | Sehr breiter Vendor-/B2B-/Infrastrukturmix · **behalten**, stärker filtern |
| Telecompetitor | <https://www.telecompetitor.com/feed/> | 200 · `OK 10/10` | Gute US-Carrier- und Regulierungsnews | Broadband-/Policy-lastig · **behalten** |
| TelecomTalk | <https://telecomtalk.info/feed/> | 200 · `OK 20/20` | Operator-News und Indien-Abdeckung | Viele Smartphone-/Gadget-/Tarifartikel; nicht jede Meldung ist Radar-relevant | **behalten**, Titel-/Operatorfilter verschärfen |
| ISPreview UK | <https://www.ispreview.co.uk/index.php/feed> | 200 · `OK 8/8` | Gute UK-Broadband-/Regulierungsquelle | Infrastruktur- und Provider-Mix; einige Artikel bot-geschützt · **behalten**, filtern |
| CommsRisk | <https://commsrisk.com/feed/> | 200 · `OK 10/10` | Nischenquelle für Fraud, SMS, Trust/Security | Wenige Meldungen, aber passend · **behalten** |

`inside digital` wurde aus `config/news_sources.yaml` entfernt. Der Feed war technisch erreichbar, lieferte aber Powerbanks, Mähroboter, Autos und Deals; das ist für einen Telco-Radar keine vertretbare Quelle.

## Workflow-, Rohdaten- und Ergebnis-Audit

| Lauf | Status / Dauer | Quellen · gesammelt · neu | Befund |
|---|---|---:|---|
| #24, 17.07. | fehlgeschlagen nach 27:35; Pipeline selbst erfolgreich, Commit-Step fehlgeschlagen | — | Kein fachlicher Pipelinefehler aus den Jobdaten ersichtlich; Push-/Commitproblem |
| #25, 17.07. | Erfolg, 22:27 | 16 · 279 · nicht im JSON als Run-Stats erhalten | Übergangslauf direkt nach der Quellenumstellung |
| #26, 19.07. | Erfolg, 22:05 | 84 · 727 · 233 | 49 OK, 30 leer, 5 fehlgeschlagen; viele alte Quellen-/Suchreste bereits aus der Datenbasis entfernt |
| #27, 20.07. | Erfolg, 14:50 | 84 · 762 · 27 | 50 OK, 29 leer, 5 fehlgeschlagen; kleiner Delta-Lauf |
| #28, 21.07. | Erfolg, 18:49 | 84 · 855 · 185 | 54 OK, 29 leer, 1 fehlgeschlagen; Sammeln 76 s, Bewertung/Schreiben 686 s, Wettbewerber 64 s |

Die GitHub-API stellt für dieses öffentliche Repository die ausführlichen Job-Logs ohne Admin-Rechte nicht bereit (`403 Must have admin rights`). Deshalb sind Collector-/LLM-Details aus den versionierten `run`-Objekten, nicht aus erfundenen Logzeilen rekonstruiert. Im gespeicherten Lauf #28 ist `Optus` der eine Fehler; die Sweep-Zeile selbst wird nicht in `report.json` persistiert. Der Code ruft den Kategorie-Sweep trotzdem in jedem LLM-Lauf auf; sein Ergebnis ist nur im Actions-Log sichtbar.

## Rohdaten gegen Berichte

- `data/state/seen.jsonl`: 702 Zeilen; der Seen-Store dedupliziert nach normalisierter URL. Die 95 aktuellen Konfigurations-URLs sind eindeutig.
- `data/reports/2026-07-21.json`: 185 neue Meldungen, davon 29 redaktionell ausgewählt; alle 29 haben URL und Source, keine doppelten URLs, eine Meldung ohne Datum.
- Die 29 Report-Links waren erreichbar in 18 Fällen mit HTTP 200. Fünf Publisher antworteten mit 403, drei mit 503 (TIM-Brasil-CMS), drei liefen in Timeout/Handshake. Das sind überwiegend Bot-/Publisher-Probleme, aber sie mindern die Nachprüfbarkeit.
- Der Bericht passt als allgemeiner Radar nur teilweise: 8 Partnerschaften und mehrere konkrete Services sind brauchbar. Gleichzeitig enthält er Open RAN, 5G-Ausbau, Glasfaser, Data-Center-Faser, B2B-Churn, M&A, Finanzen und reine Tarifaktionen. Diese Klassifikationen sind für die Differenzierungsseite ungeeignet und zeigen eine weiterhin zu schwache redaktionelle Ausschlusslogik.
- `data/state/differentiation_db.json` enthält 34 Einträge. 29 Links antworteten mit 200, 5 mit 403. Mehrere Einträge sind als 2024/2025 datiert; außerdem stehen Vergleichs-/Affiliate-/Sekundärquellen wie WhistleOut, YourNavi, GamsGo, AndroidExperto, Kavout und CableTV neben Primär- und Fachpressequellen. Die DB ist deshalb als Inspirationsbestand nützlich, aber nicht als vollständig verifizierte aktuelle Quellenbasis.
- `data/state/differentiation.jsonl` enthält fünf Newsroom-Kandidaten, darunter konkrete Telkomsel-, Vodacom- und Telekom-Angebote. Die dedizierte Seite verlinkt die Beispiele; sie sollte historische/sekundäre Sweep-Einträge künftig sichtbarer als „zuletzt geprüft“ und nicht als aktuelle Meldung kennzeichnen.

## Änderungen

Commit `2539481` (`audit: repair misleading sources and extraction filters`) wurde nach `main` gepusht.

- Offizielle Quellen repariert: 1&1-Pressefeed, Verizon-Newsroom, TIM-Brasil-Pressebereich.
- `inside digital` entfernt.
- Newsroom-Collector: Media-/IR-/Support-/Kontakt-/Social-Navigation, falsche Suffix-Domains und weitere Navigationsseiten werden verworfen; zusätzliche Datumsformate werden erkannt.
- Freshness-Filter: Termine mehr als einen Tag in der Zukunft werden nicht mehr als aktuelle Meldungen analysiert.
- Regressionstests für Navigation/Datumsformate und Zukunftsdaten ergänzt.
- Lokale Website neu gerendert; GitHub-CI und Deploy-Site-Workflow liefen für den Commit erfolgreich.

## Live-Stand

Render antwortet nach dem Push mit HTTP 200 für `/`, `/bericht.html`, `/differenzierung.html` und `/sources.html`. Die Live-Quellenübersicht zeigt die drei neuen URLs und keinen `inside digital`-Eintrag. Der alte 21.07.-Bericht blieb unverändert: Lauf #29 wurde manuell auf `main` gestartet, scheiterte aber auch im zweiten Versuch nach 24:56 Minuten bereits in `Run pipeline`; Commit- und Render-Schritte wurden übersprungen. Die öffentlichen Check-Run-Hinweise enthalten nur Exit-Code 1; die detaillierten Actions-Logs sind ohne Admin-Rechte nicht abrufbar (HTTP 403). Deshalb ist der neue Report mit den reparierten Quellen noch nicht live.
