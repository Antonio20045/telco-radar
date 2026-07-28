# Telco Radar — Verifizierte Quellenliste (offizielle Betreiber-Quellen)

Stand: 17.07.2026, aktualisiert im Audit vom 28.07.2026 (siehe Abschnitt "Audit 28.07.2026"
unten). Jede URL wurde live geprüft (Browser-User-Agent, HTTP-Status, echte Inhalte, gehört dem
Unternehmen). Feeds wurden mit `feedparser` geparst (Eintragszahl + Datum als Beleg).
**Primärquelle jedes Betreibers ist seine eigene Domain** — keine Dritt-Medien, keine
Stichwort-Nachrichtensuche. Telco-Fachpresse ist eine separate, klar gekennzeichnete zweite Ebene.

## Überblick

- **81 Betreiber** in 6 Regionen, jeder mit ≥1 offizieller Quelle auf eigener Domain.
- Direkt maschinenlesbar (Feed/JSON): **12** (11× RSS/Atom, 1× JSON-API).
- Newsroom statisch (httpx-Scrape): **12**.
- Newsroom JS-gerendert (Headless/Playwright): **32**.
- Bot-/JS-blockiert → verifizierte Referenz + dokumentierter Plan: **25**.

## Europa (24)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Maschinen-Feed | Anbindung | Verifikation |
|---|---|---|---|---|---|---|
| Vodafone Group | GB | vodafone.com | https://www.vodafone.com/news | https://www.vodafone.com/tools/urlproxy/advurlproxy.aspx?settingname=news-feed&categories=*&tags=* | Feed (JSON-API) | JSON-API, 108 Seiten, aktuellster Eintrag 17.07.2026 |
| Vodafone Deutschland | DE | vodafone.de | https://newsroom.vodafone.de/ | — | Newsroom (Headless/Playwright) | JS-gerendert (Presspage) |
| Deutsche Telekom | DE | telekom.com | https://www.telekom.com/en/media/media-information | — | Newsroom (Headless/Playwright) | JS-gerendert; statisch nur 2 Links |
| O2 Telefónica Deutschland | DE | telefonica.de | https://www.telefonica.de/presse.html | https://www.telefonica.de/o2/rss/news?category_id=11;pubdate=1 | Feed (RSS/Atom) | RSS, 20 Einträge |
| Telefónica | ES | telefonica.com | https://www.telefonica.com/en/communication-room/ | https://www.telefonica.com/en/feed/ | Feed (RSS/Atom) | RSS, 10 Einträge |
| Orange | FR | orange.com | https://www.orange.com/en/newsroom | — | Newsroom (statisch) | statisch, 24 Artikel-Links |
| BT Group | GB | bt.com | https://newsroom.bt.com/ | https://newsroom.bt.com/feed/en | Feed (RSS/Atom) | RSS, 25 Einträge, 16.07.2026 |
| Swisscom | CH | swisscom.ch | https://www.swisscom.ch/en/about/news.html | — | Newsroom (Headless/Playwright) | statisch, 3 Artikel-Links |
| Telia | SE | teliacompany.com | https://www.teliacompany.com/en/newsroom | — | Newsroom (Headless/Playwright) | JS-gerendert |
| KPN | NL | kpn.com | https://www.overons.kpn/nieuws/en/ | https://www.overons.kpn/nieuws/feed/en | Feed (RSS/Atom) | RSS, 25 Einträge, 09.07.2026 |
| Proximus | BE | proximus.com | https://www.proximus.com/news.html | — | Newsroom (statisch) | statisch, 4 Artikel-Links |
| TIM | IT | gruppotim.it | https://www.gruppotim.it/en/press-archive.html | — | Referenz (JS-Blockade) + Plan | Presseliste laedt per Klick/API nach, DOM nach Render nur 30 Nav-Links |
| Liberty Global | GB | libertyglobal.com | https://www.libertyglobal.com/news-insights/featured-news-insights/ | — | Newsroom (Headless/Playwright) | JS-gerendert |
| VEON | NL | veon.com | https://www.veon.com/newsroom | — | Newsroom (statisch) | statisch, 32 Artikel-Links |
| Telenor | NO | telenor.com | https://www.telenor.com/media/newsroom/ | — | Newsroom (statisch) | statisch, 10 Artikel-Links |
| Turkcell | TR | turkcell.com.tr | https://medya.turkcell.com.tr/basin-bultenleri/ | — | Newsroom (Headless/Playwright) | JS-gerendert; RSS nur veraltet (2016) |
| Iliad | FR | iliad.fr | https://www.iliad.fr/en/press | — | Referenz (JS-Blockade) + Plan | Presseliste laedt clientseitig nach, DOM nur Navigation |
| 1&1 | DE | united-internet.de | https://unternehmen.1und1.de/presse | https://unternehmen.1und1.de/presse/feed | Feed (RSS/Atom) | offizieller 1&1-Pressefeed, 10 Einträge |
| Bouygues Telecom | FR | bouyguestelecom.fr | https://www.corporate.bouyguestelecom.fr/presse-et-actualites/ | — | Newsroom (Headless/Playwright) | JS-gerendert |
| A1 Telekom Austria | AT | a1.group | https://newsroom.a1.net/ | — | Newsroom (Headless/Playwright) | JS-gerendert |
| Tele2 | SE | tele2.com | https://www.tele2.com/media/press-releases | — | Newsroom (statisch) | statisch, 10 Artikel-Links |
| Elisa | FI | elisa.com | https://elisa.com/corporate/news-room/ | — | Newsroom (Headless/Playwright) | JS-gerendert |
| Three UK | GB | three.co.uk | https://www.threemediacentre.co.uk/press-release-browser/ | — | Newsroom (Headless/Playwright) | JS-gerendert; Presspage-Cards nutzen opake `/content/<slug>/`-URLs ohne Presse-Keyword - `item_selector: a.card` noetig, 18 Artikel verifiziert |
| Cosmote | GR | cosmote.gr | https://www.cosmote.gr/otegroupcompanysite/en/media/press-releases | — | Referenz (JS-Blockade) + Plan | DOM nach Render fast leer (338 Zeichen, 0 Links) |

## Nordamerika (10)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Maschinen-Feed | Anbindung | Verifikation |
|---|---|---|---|---|---|---|
| Verizon | US | verizon.com | https://www.verizon.com/about/news | — | Newsroom (Headless/Playwright) | offizieller Newsroom; der alte RSS-Feed war ein Parenting-Feed |
| AT&T | US | att.com | https://about.att.com/newsroom.html | — | Referenz (Bot-geblockt) + Plan | 403 Bot-Sperre |
| T-Mobile US | US | t-mobile.com | https://www.t-mobile.com/news | — | Referenz (Bot-geblockt) + Plan | 403 Bot-Sperre |
| Comcast | US | comcast.com | https://corporate.comcast.com/news-information | https://corporate.comcast.com/rss | Feed (RSS/Atom) | RSS, 50 Einträge, 17.07.2026 |
| Charter Communications | US | charter.com | https://corporate.charter.com/newsroom | — | Newsroom (Headless/Playwright) | JS-gerendert |
| DISH Wireless | US | dish.com | https://about.dish.com/newsroom | https://api.client.notified.com/api/rss/publish/view/53068?type=press | Feed (RSS/Atom) | RSS (Notified), 50 Einträge |
| UScellular | US | uscellular.com | https://investors.uscellular.com/news/default.aspx | — | Referenz (Bot-geblockt) + Plan | 403 Bot-Sperre |
| Bell Canada | CA | bce.ca | https://www.bce.ca/news-and-media/newsroom | — | Referenz (JS-Blockade) + Plan | Tailwind-SPA, 67 Links im DOM sind reine Navigation, keine Presse-Cards |
| Rogers | CA | rogers.com | https://about.rogers.com/news-ideas/ | https://about.rogers.com/feed | Feed (RSS/Atom) | RSS (WordPress), 10 Einträge, 27.07.2026 - am 28.07.2026 verifiziert nachdem der Bot-Block auf der Newsroom-Seite selbst bestehen blieb |
| Telus | CA | telus.com | https://www.telus.com/en/about/news-and-events | — | Referenz (Bot-geblockt) + Plan | 403 Bot-Sperre |

## Lateinamerika (7)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Maschinen-Feed | Anbindung | Verifikation |
|---|---|---|---|---|---|---|
| América Móvil | MX | americamovil.com | https://www.americamovil.com/English/press-releases/default.aspx | — | Referenz (Bot-geblockt) + Plan | 403 (Q4-Plattform) |
| Millicom | LU | millicom.com | https://www.millicom.com/media/press-releases | — | Referenz (JS-Blockade) + Plan | DOM nach Render praktisch leer (4 Links, alles Cookie-Footer) |
| TIM Brasil | BR | tim.com.br | https://www.tim.com.br/sobre-a-tim/sala-de-imprensa | — | Newsroom (statisch) | offizieller Pressebereich; der alte RSS-Feed enthielt Smoke-Tests und CMS-Promos |
| Entel | CL | entel.cl | https://informacioncorporativa.entel.cl/sala-de-prensa | — | Newsroom (Headless/Playwright) | JS-gerendert |
| Oi | BR | oi.com.br | https://www.oi.com.br/sala-de-imprensa/ | — | Newsroom (Headless/Playwright) | statisch, 11 Artikel-Links |
| Telecom Argentina | AR | telecom.com.ar | https://institucional.telecom.com.ar/prensa | — | Referenz (Bot-geblockt) + Plan | 403 + Edge-Redirect |
| WOM | CL | wom.cl | https://sobrenosotros.wom.cl/wom-en-prensa/ | — | Newsroom (Headless/Playwright) | statisch, 44 Artikel-Links |

## Afrika & Naher Osten (12)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Maschinen-Feed | Anbindung | Verifikation |
|---|---|---|---|---|---|---|
| MTN Group | ZA | mtn.com | https://www.mtn.com/newsroom/ | https://www.mtn.com/feed/ | Feed (RSS/Atom) | RSS (WordPress) |
| Vodacom | ZA | vodacom.com | https://www.vodacom.com/press-releases.php | — | Newsroom (Headless/Playwright) | JS-gerendert |
| Safaricom | KE | safaricom.co.ke | https://www.safaricom.co.ke/media-center-landing | — | Newsroom (statisch) | statisch, 9 Artikel-Links |
| Airtel Africa | NG | airtel.africa | https://airtel.africa/media | — | Newsroom (Headless/Playwright) | JS-gerendert |
| stc | SA | stc.com.sa | https://www.stc.com/en/media-center.html | — | Referenz (JS-Blockade) + Plan | 188 Links im DOM sind ausschliesslich das mobile Mega-Menu, keine Pressemeldung |
| e& | AE | eand.com | https://www.eand.com/en/news.html | — | Referenz (JS-Blockade) + Plan | 62 Links im DOM sind ausschliesslich Hauptnavigation |
| Ooredoo | QA | ooredoo.com | https://www.ooredoo.com/en/media/news_view/ | — | Referenz (Bot-geblockt) + Plan | 403 Bot-Sperre |
| Zain | KW | zain.com | https://www.zain.com/en/media-center | — | Referenz (Bot-geblockt) + Plan | 307 Bot-Challenge |
| Orange MEA | EG | orange.eg | https://www.orange.eg/en/media-center/press-releases | — | Referenz (JS-Blockade) + Plan | DOM nach Render fast leer (246 Zeichen, 1 Link) |
| du | AE | du.ae | https://www.du.ae/about-us/media-centre | — | Newsroom (Headless/Playwright) | JS-gerendert |
| Maroc Telecom | MA | iam.ma | https://www.iam.ma/groupe/salle-de-presse/communiques-de-presse.aspx | — | Referenz (Bot-geblockt) + Plan | 403 Bot-Sperre |
| Turk Telekom | TR | turktelekom.com.tr | https://medya.turktelekom.com.tr/basin-bultenleri/basin-bultenleri-ve-gorseller | — | Newsroom (Headless/Playwright) | JS-gerendert |

## Asien (22)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Maschinen-Feed | Anbindung | Verifikation |
|---|---|---|---|---|---|---|
| KDDI | JP | kddi.com | https://newsroom.kddi.com/english/ | https://newsroom.kddi.com/english/news/newsrelease.xml | Feed (RSS/Atom) | RSS, 10 Einträge, 06.07.2026 |
| Bharti Airtel | IN | airtel.in | https://www.airtel.in/press-release | — | Newsroom (statisch) | statisch |
| Reliance Jio | IN | jio.com | https://www.jio.com/press-release | — | Referenz (JS-Blockade) + Plan | 127 Links im DOM sind ausschliesslich Self-Care-/Account-Navigation |
| Vodafone Idea | IN | myvi.in | https://www.myvi.in/media/press-releases | — | Newsroom (Headless/Playwright) | JS-gerendert |
| Singtel | SG | singtel.com | https://www.singtel.com/about-us/media-centre | — | Newsroom (Headless/Playwright) | JS-gerendert |
| SK Telecom | KR | sktelecom.com | https://www.sktelecom.com/en/press/press_list.do | — | Referenz (JS-Blockade) + Plan | DOM nach Render fast leer (5390 Zeichen, 4 Links ohne Text) |
| KT | KR | corp.kt.com | https://corp.kt.com/eng/html/prcenter/report_list.html | — | Referenz (JS-Blockade) + Plan | DOM nach Render komplett leer (0 Links) |
| NTT Docomo | JP | docomo.ne.jp | https://www.docomo.ne.jp/english/info/media_center/pr/ | — | Newsroom (statisch) | statisch, 20 Artikel-Links |
| SoftBank | JP | softbank.jp | https://www.softbank.jp/en/corp/news/press/ | — | Newsroom (Headless/Playwright) | statisch, 4 Artikel-Links |
| Rakuten Mobile | JP | rakuten.co.jp | https://corp.mobile.rakuten.co.jp/english/news/press/ | — | Newsroom (statisch) | statisch, 144 Artikel-Links |
| China Mobile | CN | chinamobileltd.com | https://www.chinamobileltd.com/en/media/press.php | — | Newsroom (Headless/Playwright) | JS-gerendert; statisch nur 1 Link |
| China Telecom | CN | chinatelecom-h.com | https://www.chinatelecom-h.com/en/media/press.php | — | Newsroom (Headless/Playwright) | statisch, 4 Artikel-Links |
| Chunghwa Telecom | TW | cht.com.tw | https://www.cht.com.tw/en/home/cht/messages | — | Newsroom (Headless/Playwright) | JS-gerendert |
| Telkomsel | ID | telkomsel.com | https://www.telkomsel.com/en/about-us/news | — | Newsroom (statisch) | statisch, 9 Artikel-Links |
| AIS | TH | ais.co.th | https://investor.ais.co.th/en/newsroom/set-announcements | — | Newsroom (Headless/Playwright) | JS-gerendert (Investor SET) |
| Viettel | VN | viettel.com.vn | https://viettel.com.vn/en/news | — | Newsroom (Headless/Playwright) | JS-gerendert |
| Globe Telecom | PH | globe.com.ph | https://www.globe.com.ph/about-us/newsroom | — | Referenz (Bot-geblockt) + Plan | 403 Bot-Sperre |
| PLDT | PH | pldt.com | https://main.pldt.com/newsroom | — | Newsroom (Headless/Playwright) | JS-gerendert |
| Indosat Ooredoo Hutchison | ID | ioh.co.id | https://ioh.co.id/portal/en/iohpressrelease | — | Referenz (JS-Blockade) + Plan | 18 Links im DOM sind interne SPA-Hash-Routen, keine echten Artikel-URLs |
| CelcomDigi | MY | celcomdigi.com | https://corporate.celcomdigi.com/newsroom | — | Newsroom (statisch) | statisch, 100 Artikel-Links |
| Maxis | MY | maxis.com.my | https://www.maxis.com.my/en/about-maxis/newsroom/ | — | Newsroom (Headless/Playwright) | JS-gerendert |
| True Corporation | TH | truecorp.co.th | https://investor.true.th/en/newsroom/set-announcements | — | Referenz (JS-Blockade) + Plan | DOM nach Render komplett leer (0 Links), Investor-SET-Portal vermutlich hinter Login-/JS-Wall |

## Ozeanien (6)

| Betreiber | Land | Website | Presse-/Newsroom-URL | Maschinen-Feed | Anbindung | Verifikation |
|---|---|---|---|---|---|---|
| Telstra | AU | telstra.com.au | https://www.telstra.com.au/exchange | — | Newsroom (Headless/Playwright) | JS-gerendert |
| Optus | AU | optus.com.au | https://www.optus.com.au/about/media-centre | — | Referenz (JS-Blockade) + Plan | Chromium scheitert reproduzierbar an der Navigation (ERR_HTTP2_PROTOCOL_ERROR, nach Fix TimeoutError) |
| TPG Telecom | AU | tpgtelecom.com.au | https://www.tpgtelecom.com.au/media_release | — | Newsroom (Headless/Playwright) | JS-gerendert |
| One NZ | NZ | one.nz | https://media.one.nz | https://media.one.nz/index.rss | Feed (RSS/Atom) | RSS, 10 Einträge, 05.07.2026 |
| Spark | NZ | sparknz.co.nz | https://www.sparknz.co.nz/news/ | — | Referenz (Bot-geblockt) + Plan | Radware-Bot-Wall |
| 2degrees | NZ | 2degrees.nz | https://www.2degrees.nz/media-releases | — | Newsroom (Headless/Playwright) | JS-gerendert; RSS veraltet (2021) |

## Bot-/JS-blockierte Betreiber — dokumentierter Plan (Phase 2)

Diese Betreiber liefern automatisierten Clients 403/307, eine Bot-Wall, oder ihre JS-gerenderte
Presseliste erscheint auch nach Render-Warten nie im DOM (die Liste laedt vermutlich per separatem,
nicht sichtbarem API-Call nach). Die offizielle Presse-URL ist verifiziert und wird als Referenz
angezeigt; das Auto-Signal kommt vorerst über die Fachpresse-Ebene (Namensnennung). Plan zur
Freischaltung:

- **AT&T** (US) — https://about.att.com/newsroom.html — Newsroom liefert Bots 403. Plan: Playwright über Residential-Proxy oder offizielle Media-API; bis dahin Referenz + Fachpresse-Zuordnung.
- **T-Mobile US** (US) — https://www.t-mobile.com/news — 403. Plan: Playwright über Residential-Proxy; bis dahin Referenz + Fachpresse.
- **UScellular** (US) — https://investors.uscellular.com/news/default.aspx — IR-Newsroom (Q4) blockt Bots. Plan: Q4-JSON-API prüfen; bis dahin Referenz.
- **Telus** (CA) — https://www.telus.com/en/about/news-and-events — 403. Plan: Playwright über Residential-Proxy; bis dahin Referenz.
- **América Móvil** (MX) — https://www.americamovil.com/English/press-releases/default.aspx — Plan: Q4-JSON-API prüfen; bis dahin Referenz + Fachpresse.
- **Telecom Argentina** (AR) — https://institucional.telecom.com.ar/prensa — 403. Plan: Playwright über Residential-Proxy; bis dahin Referenz.
- **Ooredoo** (QA) — https://www.ooredoo.com/en/media/news_view/ — 403. Plan: Playwright über Residential-Proxy; bis dahin Referenz.
- **Zain** (KW) — https://www.zain.com/en/media-center — 307-Edge-Challenge. Plan: Playwright über Residential-Proxy; bis dahin Referenz.
- **Maroc Telecom** (MA) — https://www.iam.ma/groupe/salle-de-presse/communiques-de-presse.aspx — 403. Plan: Playwright über Residential-Proxy; bis dahin Referenz.
- **Globe Telecom** (PH) — https://www.globe.com.ph/about-us/newsroom — 403. Plan: Playwright über Residential-Proxy; bis dahin Referenz + Fachpresse.
- **Spark** (NZ) — https://www.sparknz.co.nz/news/ — Radware-Wall (Redirect zu perfdrive). Plan: Playwright über Residential-Proxy; Alternative businessgroup.spark.co.nz prüfen; bis dahin Referenz.
- **TIM** (IT) — https://www.gruppotim.it/en/press-archive.html — JS-Routing, Presseliste laedt nur per Klick/API nach, DOM zeigt nur 30 Nav-Links. Plan: State-basierter Crawler oder API-Reverse-Engineering; bis dahin Referenz + Fachpresse.
- **Iliad** (FR) — https://www.iliad.fr/en/press — Presseliste laedt clientseitig nach, DOM nur Navigation. Plan: wie TIM.
- **Cosmote** (GR) — https://www.cosmote.gr/otegroupcompanysite/en/media/press-releases — DOM nach Render fast leer (338 Zeichen, 0 Links), vermutlich Cookie-/Bot-Challenge. Plan: Cookie-Consent-Handling oder Playwright-Stealth-Profil testen; bis dahin Referenz.
- **Bell Canada** (CA) — https://www.bce.ca/news-and-media/newsroom — Tailwind-SPA, 67 Links im DOM sind ausschliesslich Navigation/Investor-Relations. Plan: API-Reverse-Engineering; bis dahin Referenz.
- **Millicom** (LU) — https://www.millicom.com/media/press-releases — DOM nach Render praktisch leer (4 Links, alles Cookie-Footer). Plan: wie Bell Canada.
- **stc** (SA) — https://www.stc.com/en/media-center.html — 188 Links im DOM sind ausschliesslich das mobile Mega-Menu, keine Pressemeldung. Plan: API-Reverse-Engineering; bis dahin Referenz.
- **e&** (AE) — https://www.eand.com/en/news.html — 62 Links im DOM sind ausschliesslich Hauptnavigation. Plan: wie stc.
- **Orange MEA** (EG) — https://www.orange.eg/en/media-center/press-releases — DOM nach Render fast leer (246 Zeichen, 1 Link), vermutlich Bot-/Cookie-Challenge. Plan: wie Cosmote.
- **Reliance Jio** (IN) — https://www.jio.com/press-release — 127 Links im DOM sind ausschliesslich Self-Care-/Account-Navigation. Plan: wie stc.
- **SK Telecom** (KR) — https://www.sktelecom.com/en/press/press_list.do — DOM nach Render fast leer (5390 Zeichen, 4 Links ohne Text). Plan: wie Cosmote.
- **KT** (KR) — https://corp.kt.com/eng/html/prcenter/report_list.html — DOM nach Render komplett leer (0 Links), vermutlich Bot-Wall/Consent-Screen. Plan: wie Cosmote.
- **Indosat Ooredoo Hutchison** (ID) — https://ioh.co.id/portal/en/iohpressrelease — 18 Links im DOM sind interne SPA-Hash-Routen, keine echten Artikel-URLs. Plan: wie stc.
- **True Corporation** (TH) — https://investor.true.th/en/newsroom/set-announcements — DOM nach Render komplett leer (0 Links), Investor-SET-Portal vermutlich hinter Login-/JS-Wall. Plan: wie Cosmote.
- **Optus** (AU) — https://www.optus.com.au/about/media-centre — Chromium scheitert reproduzierbar an der Navigation (zuerst ERR_HTTP2_PROTOCOL_ERROR; nach `--disable-http2`-Fix stattdessen TimeoutError nach 30s), vermutlich IP-Sperre gegen GitHub-Actions-Runner. Plan: Playwright über Residential-Proxy; ohne zusaetzliche kostenpflichtige Infrastruktur nicht loesbar.

## Audit 28.07.2026

Zweiter Durchgang über die 12 bereits als `official` markierten Bot-Sperren plus 15 zusaetzlich
verdaechtige Betreiber (durchgehend `EMPTY` in echten Laeufen). Verifikation lief ueber echten
Netzzugriff via GitHub-Actions-Dispatch (`scripts/validate_sources.py`, `scripts/rescue_sources.py`
fuer RSS-Autodiscovery + gaengige Feed-Pfade, `scripts/inspect_dom.py` fuer rohe DOM-Dumps inkl.
`item_selector`-Treffer) — nicht in dieser Sandbox, die keinen ausgehenden Internetzugriff hat.

Ergebnis:
- **2 echte Reparaturen** mit verifizierten Live-Daten: **Rogers** (about.rogers.com/feed, 10
  aktuelle Eintraege) und **Three UK** (item_selector: a.card auf threemediacentre.co.uk foerdert
  18 echte Pressemeldungen zutage, die die bisherige URL-Keyword-Heuristik stillschweigend verwarf,
  weil die Presspage-CMS opake `/content/<slug>/`-Pfade ohne "news"/"press"-Keyword nutzt —
  `parse_newsroom_html` vertraut jetzt einem konfigurierten `item_selector` mehr als der
  URL-Heuristik, siehe `src/telco_radar/collect/newsroom.py`).
- **1 Versuch mit Teilerfolg, aber weiterhin blockiert**: **Optus** — `--disable-http2` fuer den
  gemeinsamen Playwright-Start behebt den urspruenglichen `ERR_HTTP2_PROTOCOL_ERROR`, die Seite
  liefert aber weiterhin keinen Inhalt (Timeout nach 30s) — vermutlich eine IP-Sperre gegen
  GitHub-Actions-Runner.
- **14 neu bestaetigte Sackgassen** (siehe Tabelle oben + Bullet-Liste): entweder ein nach
  Playwright-Render fast/komplett leeres DOM (Cookie-/Bot-Challenge blockiert das Rendering) oder
  ein DOM voller Navigation ohne jede Presse-Card (die eigentliche Liste laedt vermutlich per
  separatem, im Render-Fenster nicht sichtbarem API-Call). Fuer keinen dieser 14 fand
  `rescue_sources.py` einen funktionierenden RSS/Atom-Feed.
- Zusaetzlich: `parse_newsroom_html` parst jetzt auch Datumsangaben mit Ordinalzahlen ("28th May
  2026"), nicht nur "28 May 2026" — betrifft u.a. die neuen Three-UK-Eintraege.
