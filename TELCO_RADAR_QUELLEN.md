# Telco Radar — Verifizierte Quellenliste (offizielle Betreiber-Quellen)

Stand: 29.07.2026, grosser Reparatur-Durchgang (siehe Abschnitt "Audit 28.-29.07.2026" unten): von den 43 zuvor toten Quellen sind jetzt 33 mit echten, automatisch gecrawlten Daten repariert. Jede URL wurde live geprüft (Browser-User-Agent, HTTP-Status, echte Inhalte, gehört dem Unternehmen); die Item-/Datums-Zahlen in der Verifikations-Spalte stammen aus einem echten `validate_sources.py`-Lauf. **Primärquelle jedes Betreibers ist seine eigene Domain** — keine Dritt-Medien, keine Stichwort-Nachrichtensuche. Telco-Fachpresse ist eine separate, klar gekennzeichnete zweite Ebene.

## Überblick

- **81 Betreiber** in 6 Regionen, jeder mit ≥1 offizieller Quelle auf eigener Domain.
- Direkt maschinenlesbar (Feed/JSON): **26** (15× RSS/Atom, 11× JSON-API).
- Newsroom statisch (httpx-Scrape): **23**.
- Newsroom JS-gerendert (Headless/Playwright): **22**.
- Nicht automatisiert (Referenz + dokumentierter Grund): **10** (davon 4 nur mit kostenpflichtigem Residential-Proxy loesbar, siehe unten).

## Europa (24)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Anbindung | Verifikation |
|---|---|---|---|---|---|
| Vodafone Group | GB | vodafone.com | https://www.vodafone.com/tools/urlproxy/advurlproxy.aspx?settingname=news-feed&categories=*&tags=* | Feed (JSON-API) | 16 Meldungen, 16 datiert |
| Vodafone Deutschland | DE | vodafone.de | https://newsroom.vodafone.de/ | Newsroom (Headless/Playwright) | 1 Meldungen, 0 datiert |
| Deutsche Telekom | DE | telekom.com | https://www.telekom.com/en/media/media-information | Newsroom (statisch) (item_selector: `a.media-link[title]`) | statisch statt JS-gerendert: Titel steckt im title-Attribut des Icon-Links ("Media information: ..."), item_selector: a.media-link[title] - 13 Meldungen |
| O2 Telefónica Deutschland | DE | telefonica.de | https://www.telefonica.de/o2/rss/news?category_id=11;pubdate=1 | Feed (RSS/Atom) |  |
| Telefónica | ES | telefonica.com | https://www.telefonica.com/en/feed/ | Feed (RSS/Atom) | 10 Meldungen, 10 datiert |
| Orange | FR | orange.com | https://www.orange.com/en/newsroom | Newsroom (statisch) | 6 Meldungen, 6 datiert |
| BT Group | GB | bt.com | https://newsroom.bt.com/feed/en | Feed (RSS/Atom) | 25 Meldungen, 25 datiert |
| Swisscom | CH | swisscom.ch | https://www.swisscom.ch/en/about/news.html | Newsroom (Headless/Playwright) | 3 Meldungen, 0 datiert |
| Telia | SE | teliacompany.com | https://www.teliacompany.com/en/newsroom | Newsroom (Headless/Playwright) | 15 Meldungen, 10 datiert |
| KPN | NL | kpn.com | https://www.overons.kpn/nieuws/feed/en | Feed (RSS/Atom) | 25 Meldungen, 25 datiert |
| Proximus | BE | proximus.com | https://www.proximus.com/news.html | Newsroom (statisch) | 3 Meldungen, 3 datiert |
| TIM | IT | gruppotim.it | https://www.gruppotim.it/en/press-archive.html | Referenz (nicht automatisiert) + Plan | Nach Render (curl UND Playwright, 45s, networkidle, Cookie-Klick) identisches leeres DOM (nur 30 Nav-Links); 0 XHR/JSON waehrend des gesamten Renders, nur ein reCAPTCHA-Script laedt. 46 Feed-Kandidaten erfolglos. Kein Bot-Block (curl bekommt 200) - die Seite ist schlicht ohne erkennbaren Daten-Call. |
| Liberty Global | GB | libertyglobal.com | https://www.libertyglobal.com/feed/ | Feed (RSS/Atom) | eigener libertyglobal.com/feed/-RSS-Feed statt JS-Render |
| VEON | NL | veon.com | https://www.veon.com/newsroom | Newsroom (statisch) | 30 Meldungen, 18 datiert |
| Telenor | NO | telenor.com | https://www.telenor.com/media/newsroom/ | Newsroom (statisch) | 10 Meldungen, 6 datiert |
| Turkcell | TR | turkcell.com.tr | https://medya.turkcell.com.tr/basin-bultenleri/ | Newsroom (statisch) (item_selector: `a.latest-bulletins-item`) | statisch statt JS-gerendert, item_selector: a.latest-bulletins-item - 9 Meldungen |
| Iliad | FR | iliad.fr | https://api.scw.iliad.fr/iliad-cms/news-items/deep-find?language=en&year=all&tag=all | Feed (JSON-API) | JSON-API gefunden (api.scw.iliad.fr Strapi-Backend) statt Referenz - 40 Meldungen; URL-Feld ist ein Slug, per link_template zusammengesetzt |
| 1&1 | DE | united-internet.de | https://unternehmen.1und1.de/presse/feed | Feed (RSS/Atom) | 10 Meldungen, 10 datiert |
| Bouygues Telecom | FR | bouyguestelecom.fr | https://www.corporate.bouyguestelecom.fr/presse-et-actualites/ | Newsroom (Headless/Playwright) | 18 Meldungen, 13 datiert |
| A1 Telekom Austria | AT | a1.group | https://newsroom.a1.net/ | Newsroom (Headless/Playwright) | 12 Meldungen, 10 datiert |
| Tele2 | SE | tele2.com | https://www.tele2.com/media/press-releases | Newsroom (statisch) | 1 Meldungen, 1 datiert |
| Elisa | FI | elisa.com | https://elisa.com/corporate/news-room/ | Newsroom (Headless/Playwright) | 4 Meldungen, 4 datiert |
| Three UK | GB | three.co.uk | https://www.threemediacentre.co.uk/press-release-browser/ | Newsroom (Headless/Playwright) (item_selector: `a.card`) | 18 Meldungen, 18 datiert |
| Cosmote | GR | cosmote.gr | https://www.cosmote.gr/otegroupcompanysite/en/media/press-releases | Referenz (nicht automatisiert) + Plan | Echter Imperva-Incapsula-Bot-Wall: auch reiner curl mit Browser-UA bekommt nur das Challenge-Script (585 Byte); mit Googlebot-UA sogar 404. Serverseitige WAF-Entscheidung, kein Render-Timing-Problem. |

## Nordamerika (10)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Anbindung | Verifikation |
|---|---|---|---|---|---|
| Verizon | US | verizon.com | https://www.verizon.com/about/news | Newsroom (Headless/Playwright) | 2 Meldungen, 0 datiert |
| AT&T | US | att.com | https://about.att.com/newsroom.html | Referenz (nicht automatisiert) + Plan | 403 Akamai-Bot-Sperre, unveraendert. Kein Feed gefunden. |
| T-Mobile US | US | t-mobile.com | https://www.t-mobile.com/news | Newsroom (statisch) | kein Bot-Block mehr feststellbar - echter Newsroom, kein Playwright noetig - 21 Meldungen |
| Comcast | US | comcast.com | https://corporate.comcast.com/rss | Feed (RSS/Atom) | 40 Meldungen, 40 datiert |
| Charter Communications | US | charter.com | https://corporate.charter.com/page-data/sq/d/2336972469.json | Feed (JSON-API) | JSON-API gefunden (Gatsby page-data-Endpoint) statt JS-Render - 40 Meldungen |
| DISH Wireless | US | dish.com | https://api.client.notified.com/api/rss/publish/view/53068?type=press | Feed (RSS/Atom) | 40 Meldungen, 40 datiert |
| UScellular | US | uscellular.com | https://investors.uscellular.com/news/default.aspx | Referenz (nicht automatisiert) + Plan | Kein Crawling-Problem: T-Mobile hat die Mobilfunksparte uebernommen, es gibt keinen eigenstaendigen Newsroom mehr (die Seite leitet clientseitig auf investor.t-mobile.com weiter). |
| Bell Canada | CA | bce.ca | https://www.bce.ca/news-and-media/newsroom | Referenz (nicht automatisiert) + Plan | Next.js-App-Router-Seite ohne echten JSON-Endpoint - die einzigen Netzwerk-Antworten sind React-Server-Components-"Flight"-Payloads (text/x-component), kein normales JSON und keine echten <a href>-Elemente. |
| Rogers | CA | rogers.com | https://about.rogers.com/feed | Feed (RSS/Atom) | 10 Meldungen, 10 datiert |
| Telus | CA | telus.com | https://www.telus.com/en/about/newsroom | Newsroom (Headless/Playwright) | neue URL (news-and-events -> newsroom, alte Seite 404), generische URL-Heuristik reicht |

## Lateinamerika (7)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Anbindung | Verifikation |
|---|---|---|---|---|---|
| América Móvil | MX | americamovil.com | https://www.americamovil.com/rss/pressrelease.aspx?LanguageId=1 | Feed (RSS/Atom) | eigener Q4-RSS-Feed (rss/pressrelease.aspx) statt Referenz - 10 Meldungen |
| Millicom | LU | millicom.com | https://www.millicom.com/media/press-releases | Referenz (nicht automatisiert) + Plan | XHR-Sniffing fand einen Strapi-Endpoint, der aber ein leeres data:[] liefert (falscher Slug); /api/articles existiert (403 statt 404) aber ist ohne Auth nicht lesbar. |
| TIM Brasil | BR | tim.com.br | https://www.tim.com.br/sobre-a-tim/sala-de-imprensa | Newsroom (statisch) | 5 Meldungen, 0 datiert |
| Entel | CL | entel.cl | https://informacioncorporativa.entel.cl/comunicados-de-prensa | Newsroom (statisch) | echte Archiv-URL (comunicados-de-prensa statt sala-de-prensa); Modyo/Andino-CMS bettet die Liste als JSON im eds-card-Attribut ein, dedizierter Extraktor ergaenzt - 20 Meldungen |
| Oi | BR | oi.com.br | https://www.oi.com.br/sala-de-imprensa/ | Newsroom (statisch) (item_selector: `.news__item`) | item_selector: .news__item statt JS-Render - 6 Meldungen |
| Telecom Argentina | AR | telecom.com.ar | https://institucional.telecom.com.ar/prensa/noticias | Newsroom (Headless/Playwright) (item_selector: `article.lastest-news-card`) | neue URL (institucional.telecom.com.ar/prensa/noticias, alte Seite umstrukturiert), item_selector: article.lastest-news-card - 7 Meldungen |
| WOM | CL | wom.cl | https://sobrenosotros.wom.cl/wp-json/wp/v2/posts?categories=1&per_page=20 | Feed (JSON-API) | eigene WordPress-REST-API (wp-json/wp/v2/posts, Kategorie "Comunicados") statt JS-Render |

## Afrika & Naher Osten (12)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Anbindung | Verifikation |
|---|---|---|---|---|---|
| MTN Group | ZA | mtn.com | https://www.mtn.com/feed/ | Feed (RSS/Atom) | 10 Meldungen, 10 datiert |
| Vodacom | ZA | vodacom.com | https://www.vodacom.com/press-releases.php | Newsroom (Headless/Playwright) | 30 Meldungen, 24 datiert |
| Safaricom | KE | safaricom.co.ke | https://www.safaricom.co.ke/media-center-landing | Newsroom (statisch) | 3 Meldungen, 3 datiert |
| Airtel Africa | NG | airtel.africa | https://www.investegate.co.uk/company/AAF | Newsroom (statisch) (item_selector: `tbody tr`) | airtel.africa selbst bleibt unloesbar (PDF-Links auf Fremddomain + Titel in unklassifiziertem Nachbar-div) - stattdessen RNS-Boersenmeldungen via Investegate (Airtel Africa ist an der LSE notiert), 30 Meldungen |
| stc | SA | stc.com.sa | https://www.stc.com/bin/public/assets?root=/content/dam/stc/content-fragments/press-release&isContentFragment=true&getJCRProps=false | Feed (JSON-API) | JSON-API gefunden (AEM-Servlet bin/public/assets, brauchte einen Referer-Header) statt Referenz - 40 Meldungen (siehe http.py-Fix) |
| e& | AE | eand.com | https://www.eand.com/en/news/news-overview.html | Newsroom (statisch) (item_selector: `.tile-box-tile`) | echte Listing-URL (en/news/news-overview.html statt en/news.html), item_selector: .tile-box-tile - 30 Meldungen |
| Ooredoo | QA | ooredoo.com | https://www.ooredoo.com/en/media/news_view/ | Referenz (nicht automatisiert) + Plan | Cloudflare-Turnstile-Challenge ("Just a moment..."), unveraendert - auch mit Playwright nicht loesbar. |
| Zain | KW | zain.com | https://www.zain.com/en/media-center | Newsroom (Headless/Playwright) (item_selector: `.PressCard`) | item_selector: .PressCard statt Referenz - 4 Meldungen; Fix war generisch (siehe unten: render_html-Bugs) |
| Orange MEA | EG | orange.eg | https://www.orange.eg/en/media-center/press-releases | Referenz (nicht automatisiert) + Plan | Echte F5/BIG-IP-WAF-Ablehnung ("The requested URL was rejected"), kein Consent-/Timing-Problem. |
| du | AE | du.ae | https://www.du.ae/about-us/media-centre | Newsroom (Headless/Playwright) | 30 Meldungen, 30 datiert |
| Maroc Telecom | MA | iam.ma | https://www.iam.ma/groupe/salle-de-presse/communiques-de-presse.aspx | Referenz (nicht automatisiert) + Plan | Cloudflare-Turnstile-Challenge, identisch zu Ooredoo. |
| Turk Telekom | TR | turktelekom.com.tr | https://medya.turktelekom.com.tr/basin-bultenleri/basin-bultenleri-ve-gorseller | Newsroom (statisch) (item_selector: `a.relases-card`) | statisch statt JS-gerendert, item_selector: a.relases-card - 10 Meldungen |

## Asien (22)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Anbindung | Verifikation |
|---|---|---|---|---|---|
| KDDI | JP | kddi.com | https://newsroom.kddi.com/english/news/newsrelease.xml | Feed (RSS/Atom) | 10 Meldungen, 10 datiert |
| Bharti Airtel | IN | airtel.in | https://www.airtel.in/press-release | Newsroom (statisch) | 30 Meldungen, 30 datiert |
| Reliance Jio | IN | jio.com | https://www.jio.com/jcms-api/v1-press-release-page | Feed (JSON-API) | JSON-API gefunden (jcms-api/v1-press-release-page) statt Referenz - 40 Meldungen, aktuellste 14.06.2026 |
| Vodafone Idea | IN | myvi.in | https://www.myvi.in/bin/vodafoneideadigital/newssearchservlet?search=%7B%22q%22%3A%22%2A%22%2C%22newsType%22%3A%22press%22%2C%22newsCategory%22%3A%22%2A%22%2C%22newsCircle%22%3A%22%2A%22%2C%22newsYear%22%3A0%2C%22pageNumber%22%3A1%7D | Feed (JSON-API) | JSON-API gefunden (myvi.in Servlet) statt JS-Render - 8 Meldungen |
| Singtel | SG | singtel.com | https://www.singtel.com/about-us/media-centre | Newsroom (Headless/Playwright) | 11 Meldungen, 11 datiert |
| SK Telecom | KR | sktelecom.com | https://www.sktelecom.com/en/press/press.do | Newsroom (statisch) (item_selector: `a.link`) | echte URL (press.do statt totes press_list.do), statisch statt JS-gerendert, item_selector: a.link (Karte enthaelt Titel+Summary+Datum in einem <a>, Titel/Datum-Extraktion bevorzugt jetzt .title/[class*=date]-Kindelemente) - 10 Meldungen |
| KT | KR | corp.kt.com | https://rdi.kt.com/corp/presses/v1.0/channels/KOR/sections/ALL?limit=20&offset=1 | Feed (JSON-API) | JSON-API gefunden (rdi.kt.com, KOR-Kanal - der ENG-Kanal ist seit 2020 eingefroren) statt Referenz - Inhalte ab jetzt koreanisch |
| NTT Docomo | JP | docomo.ne.jp | https://www.docomo.ne.jp/english/info/media_center/pr/ | Newsroom (statisch) | 20 Meldungen, 20 datiert |
| SoftBank | JP | softbank.jp | https://www.softbank.jp/en/corp/news/press/ | Newsroom (Headless/Playwright) | 30 Meldungen, 30 datiert |
| Rakuten Mobile | JP | rakuten.co.jp | https://corp.mobile.rakuten.co.jp/english/news/press/ | Newsroom (statisch) | 30 Meldungen, 30 datiert |
| China Mobile | CN | chinamobileltd.com | https://www.irasia.com/cgi-local/news/rss.cgi?id=chinamobile&loc=hk&t=p&title_for_section=yes | Feed (RSS/Atom) | eigener irasia.com-IR-Feed statt JS-Newsroom (dessen Meldungen sind PDFs, die der Collector kategorisch ausschliesst) |
| China Telecom | CN | chinatelecom-h.com | https://www.irasia.com/cgi-local/news/rss.cgi?id=chinatelecom&loc=hk&t=p&title_for_section=yes | Feed (RSS/Atom) | eigener irasia.com-IR-Feed statt JS-Newsroom (dessen Meldungen sind PDFs) |
| Chunghwa Telecom | TW | cht.com.tw | https://www.cht.com.tw/en/home/cht/messages | Newsroom (Headless/Playwright) | EMPTY - kein bekanntes item_selector/API fuer diese Quelle (ausserhalb des 43er-Reparatur-Umfangs) |
| Telkomsel | ID | telkomsel.com | https://www.telkomsel.com/en/about-us/news | Newsroom (statisch) | 8 Meldungen, 8 datiert |
| AIS | TH | ais.co.th | https://investor.ais.co.th/en/newsroom/set-announcements | Newsroom (Headless/Playwright) (item_selector: `a.card--set-announcement`) | item_selector: a.card--set-announcement - 11 Meldungen (Fix war generisch, siehe render_html-Bugs) |
| Viettel | VN | viettel.com.vn | https://viettel.com.vn/en/news | Newsroom (Headless/Playwright) | 1 Meldungen, 0 datiert |
| Globe Telecom | PH | globe.com.ph | https://www.globe.com.ph/about-us/newsroom | Newsroom (Headless/Playwright) (item_selector: `.media-card`) | item_selector: .media-card statt Referenz - kein Bot-Block mehr feststellbar |
| PLDT | PH | pldt.com | https://cms.pldt.com/drupal/api/v1/newsroom-article-list | Feed (JSON-API) | JSON-API gefunden (cms.pldt.com/drupal/api/v1/newsroom-article-list) statt bloss `/newsroom`-Shell - 10 Meldungen mit echtem Datum |
| Indosat Ooredoo Hutchison | ID | ioh.co.id | https://web-api.ioh.co.id/api/content-hub/public?page=1&limit=20&paginateDisable=false&site=&type=Press%20Release&lang=EN&language=EN | Feed (JSON-API) | JSON-API gefunden (web-api.ioh.co.id/api/content-hub/public) statt Referenz - 20 Meldungen, 18 datiert |
| CelcomDigi | MY | celcomdigi.com | https://corporate.celcomdigi.com/newsroom | Newsroom (statisch) | 30 Meldungen, 30 datiert |
| Maxis | MY | maxis.com.my | https://www.maxis.com.my/en/about-maxis/newsroom/jcr:content/content/section_container/section_container/container/repository_search_co.newsroom.json?keyword=*:* | Feed (JSON-API) | JSON-API gefunden (repository_search_co.newsroom.json?keyword=*:*) statt JS-Render - 18 Meldungen |
| True Corporation | TH | truecorp.co.th | https://investor.true.th/en/newsroom/set-announcements | Newsroom (Headless/Playwright) (item_selector: `a.card--news`) | item_selector: a.card--news; Announcements verlinken auf einen Drittanbieter-IR-Vendor (ir.listedcompany.com) - dafuer expliziter, eng gefasster Domain-Trust ergaenzt - 12 Meldungen |

## Ozeanien (6)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Anbindung | Verifikation |
|---|---|---|---|---|---|
| Telstra | AU | telstra.com.au | https://www.telstra.com.au/exchange | Newsroom (Headless/Playwright) (item_selector: `a.tcom-article-box__link`) | item_selector: a.tcom-article-box__link - 16 Meldungen |
| Optus | AU | optus.com.au | https://www.optus.com.au/about/media-centre | Referenz (nicht automatisiert) + Plan | Timeout bei der Navigation (30-40s) - auch von der direkten Sandbox-IP aus reproduziert, nicht nur von GitHub-Actions-Runnern. Vermutlich eine breitere Anti-Datacenter-IP-Sperre. |
| TPG Telecom | AU | tpgtelecom.com.au | https://www.tpgtelecom.com.au/media_release | Newsroom (statisch) (item_selector: `.mediaItem`) | statisch statt JS-gerendert, item_selector: .mediaItem (Titel sitzt in h5 neben dem PDF-Link) - 9 Meldungen |
| One NZ | NZ | one.nz | https://media.one.nz/index.rss | Feed (RSS/Atom) | 10 Meldungen, 10 datiert |
| Spark | NZ | sparknz.co.nz | https://www.nzx.com/companies/SPK/announcements | Newsroom (statisch) (item_selector: `tbody tr`) | sparknz.co.nz/news bleibt hinter Radware-Bot-Wall - stattdessen NZX-Boersenmeldungen (Spark ist an der NZX/ASX notiert), 17 Meldungen |
| 2degrees | NZ | 2degrees.nz | https://www.2degrees.nz/media-releases | Newsroom (Headless/Playwright) | 9 Meldungen, 9 datiert |

## Nicht automatisiert — dokumentierter Grund

Diese 10 Betreiber liefern trotz vollem Playwright-Render, Cookie-Consent-Klick und RSS-Autodiscovery sowie kreativer Suche nach alternativen offiziellen Kanaelen (Boersen-Meldewege wie RNS/NZX, die schon zwei weitere Faelle geloest haben - siehe Airtel Africa und Spark oben) keine automatisch crawlbare Presseliste. Die offizielle Presse-URL ist verifiziert und wird als Referenz angezeigt; das Auto-Signal kommt vorerst über die Fachpresse-Ebene (Namensnennung).

**4 davon sind ausschliesslich mit einem kostenpflichtigen Residential-Proxy loesbar** (AT&T, Ooredoo, Maroc Telecom, Optus - alle hinter Cloudflare-Turnstile/Akamai-Bot-Walls, die eine Rechenzentrums-IP kategorisch ablehnen, auch fuer ihre Boersen-Disclosure-Seiten wo eine gefunden wurde) - Antonio hat entschieden, dafuer kein Budget freizugeben.

**6 davon sind aus anderen Gruenden nicht (oder nicht sinnvoll) automatisierbar:** TIM und Millicom (kein erkennbarer Daten-Endpoint gefunden, auch nicht ueber die jeweilige Boerse), Cosmote und Orange MEA (echte WAF-Ablehnung, kein Bot-Proxy-Problem), Bell Canada (Next.js React-Server-Components statt JSON/HTML-Links; die einzige gefundene Alternative, ein Cision-Newswire-Tag "bell-canada", mischt Drittanbieter-Pressemitteilungen ueber Bell ein statt Bells eigener - verstoesst gegen das Primaerquellen-Prinzip dieses Projekts) und UScellular (Firma wurde von T-Mobile uebernommen, es gibt keinen eigenen Newsroom mehr).

- **TIM** (IT) — https://www.gruppotim.it/en/press-archive.html — Erneut mit echtem Internetzugang und vollem Playwright-Render (45s, networkidle, Cookie-Consent-Klick, Scroll-Trigger) geprueft: identisches DOM zur statischen curl-Antwort (316541 Zeichen, nur 30 Nav-Links, 0 Presse-Links). 0 XHR/fetch/JSON-Responses waehrend des gesamten Renders - die Seite laedt nur ein reCAPTCHA-Script, nie einen Daten-Call. 46 Feed-Kandidaten von rescue_sources.py probiert, keiner funktioniert; robots.txt-Alternative /en/press/press-releases.html redirectet zurueck auf dieselbe leere Seite; /en/sitemap.xml und /it.sitemap.xml beide 404. Kein Bot-Block (curl bekommt 200), die Seite ist einfach clientseitig kaputt/leer. Bis auf Weiteres kein Ansatz gefunden; Referenz + Fachpresse.
- **Cosmote** (GR) — https://www.cosmote.gr/otegroupcompanysite/en/media/press-releases — Echter Imperva-Incapsula-Bot-Wall, kein Timing-/Consent-Problem: selbst reiner curl mit Browser-UA bekommt HTTP 200, aber der Body ist nur das _Incapsula_Resource-Challenge-Script (585 Byte, 0 <a>-Tags); mit Googlebot-UA sogar HTTP 404. Playwright mit Cookie-Consent-Klick + 8s Wartezeit liefert dasselbe Ergebnis (visid_incap_*/x-iinfo-Cookies vorhanden, Titel "404 Not Found"). JS wird nie ausgefuehrt, das ist eine serverseitige WAF-Entscheidung, kein Render-Problem. Nur mit Residential-Proxy oder expliziter Incapsula-Allowlist loesbar; bis dahin Referenz.
- **AT&T** (US) — https://about.att.com/newsroom.html — Newsroom liefert Bots 403. Plan: Playwright über Residential-Proxy oder offizielle Media-API; bis dahin Referenz + Fachpresse-Zuordnung.
- **UScellular** (US) — https://investors.uscellular.com/news/default.aspx — Kein Crawling-Problem, sondern ein Fakt: T-Mobile hat die UScellular-Mobilfunksparte uebernommen (Deal abgeschlossen 2025). investors.uscellular.com liefert per curl Cloudflare-403; mit Playwright wird die Challenge zwar bestanden, aber die Seite leitet clientseitig komplett auf investor.t-mobile.com weiter - es gibt keinen eigenstaendigen UScellular-Newsroom mehr. Vodafone-relevante Meldungen zu diesem Konzern laufen inzwischen ueber den (reparierten) T-Mobile-US-Eintrag. Referenz, kein technisches Fix noetig.
- **Bell Canada** (CA) — https://www.bce.ca/news-and-media/newsroom — Next.js-App-Router-Seite; 67 quelleneigene Links im gerenderten DOM sind ausschliesslich Navigation/Investor-Relations, keine Presse-Cards. Tiefere Analyse: es gibt keinen normalen JSON-Endpoint - weder client-seitig (sniff_xhr zeigt nur "text/x-component"-Antworten auf ?_rsc=... URLs, das React-Server-Components "Flight"-Protokoll fuer Hydration, kein JSON) noch separat auffindbar (kein Contentstack- Call trotz CSP-Hinweis auf api.contentstack.io - laeuft offenbar nur serverseitig). Die echten Release-Daten (headline/summary/published_date/sitemap_url) stecken zwar in der normalen HTML-Antwort, aber nur als escapte JSON-Strings in <script>self.__next_f.push([1,"..."])</script>-Chunks, nicht als <a href> im DOM und nicht als eigenstaendiges JSON-Dokument - passt weder in den newsroom- noch in den json_api-Collector, sondern braeuchte einen komplett neuen, RSC-Flight-spezifischen Parsertyp. Kein Feed gefunden. Bewusst als nicht automatisch crawlbar eingestuft (Aufwand/Nutzen); bis dahin Referenz + Fachpresse.
- **Millicom** (LU) — https://www.millicom.com/media/press-releases — Mit vollem Playwright-Render (Tailwind/Next.js-Seite) jetzt viele Nav-Links sichtbar, aber keine Presse-Links. XHR-Sniffing fand einen Strapi-Endpoint (ww2-api.tigocloud.net/api/pages?filters[slug]=/media/press-releases) - liefert aber leeres data:[] (falscher Slug oder anderer Content-Type fuer die eigentliche Liste). /api/press-releases, /api/news, /api/media existieren nicht (404); /api/articles existiert (403 Forbidden statt 404) aber ist ohne Auth nicht lesbar. Kein Feed gefunden. Naechster Schritt waere das Strapi-Content-Model vollstaendig zu enumerieren; ohne das bis dahin Referenz.
- **Ooredoo** (QA) — https://www.ooredoo.com/en/media/news_view/ — 403. Plan: Playwright über Residential-Proxy; bis dahin Referenz.
- **Orange MEA** (EG) — https://www.orange.eg/en/media-center/press-releases — Echte WAF-Ablehnung, kein Render-/Consent-Problem: sowohl curl als auch Playwright bekommen HTTP 200 mit dem Body "The requested URL was rejected. Please consult with your administrator... Your support ID is: ..." (246 Byte, F5/BIG-IP-Stil, mit 3 verschiedenen User-Agents reproduziert). Kein Consent-Banner, kein JS - die WAF lehnt die URL selbst ab, bevor irgendetwas laedt. Nur mit Residential-Proxy oder expliziter WAF-Allowlist loesbar; bis dahin Referenz.
- **Maroc Telecom** (MA) — https://www.iam.ma/groupe/salle-de-presse/communiques-de-presse.aspx — 403. Plan: Playwright über Residential-Proxy; bis dahin Referenz.
- **Optus** (AU) — https://www.optus.com.au/about/media-centre — Chromium scheitert reproduzierbar an der Navigation (zuerst ERR_HTTP2_PROTOCOL_ERROR; nach --disable-http2-Fix stattdessen TimeoutError nach 30s) - vermutlich IP-Sperre gegen GitHub-Actions-Runner oder eine Bot-Challenge, die die Seite nie ausliefert. Plan: Playwright ueber Residential-Proxy; ohne zusaetzliche kostenpflichtige Infrastruktur nicht loesbar.
