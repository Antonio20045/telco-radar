# Telco Radar — Quellenliste (offizielle Betreiber-Quellen)

Erzeugt am 01.08.2026 mit `scripts/build_quellen_doc.py` --validate aus `config/watchlist.yaml`.

**Primaerquelle jedes Betreibers ist seine eigene Domain.** Ausnahmen sind im YAML kommentiert und unten in der Spalte Verifikation erkennbar. Telco-Fachpresse ist eine separate zweite Ebene (`config/news_sources.yaml`).

## Ueberblick

- **81 Betreiber** in 6 Regionen.
- Direkt maschinenlesbar (Feed/JSON): **33** (20x RSS/Atom, 13x JSON-API).
- Newsroom statisch: **33**.
- Newsroom JS-gerendert: **11**.
- Nicht automatisiert (Referenz + Begruendung): **5**.
- Fachpresse: **14** Feeds.

## Europa (24)

| Betreiber | Land | Website | Quelle | Anbindung | Verifikation |
|---|---|---|---|---|---|
| 1&1 | DE | united-internet.de | https://unternehmen.1und1.de/presse/feed | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-22, 0 im 8-Tage-Fenster |
| A1 Telekom Austria | AT | a1.group | https://newsroom.a1.net/ | Newsroom (Headless/Playwright) | hier nicht pruefbar (kein Headless-Browser), laeuft in GitHub Actions |
| BT Group | GB | bt.com | https://newsroom.bt.com/feed/en | Feed (RSS/Atom) | 25 Meldungen, 25 datiert, neuestes 2026-07-23, 0 im 8-Tage-Fenster |
| Bouygues Telecom | FR | bouyguestelecom.fr | https://www.corporate.bouyguestelecom.fr/presse-et-actualites/ | Newsroom (statisch) | 18 Meldungen, 13 datiert, neuestes 2026-07-30, 2 im 8-Tage-Fenster |
| Cosmote | GR | cosmote.gr | https://www.cosmote.gr/otegroupcompanysite/en/media/press-releases | Referenz (nicht automatisiert) | nicht gecrawlt (Referenz) — Echter Imperva-Incapsula-Bot-Wall, kein Timing-/Consent-Problem: selbst reiner curl mit Browser-UA bekommt HTTP 200, aber der Body ist nur das _Incapsula_Resource-Challenge-Script (585 Byte, 0 <a>-Tags); mit Googlebot-UA sogar HTTP 404. Playwright mit Cookie-Consent-Klick + 8s Wartezeit liefert dass |
| Deutsche Telekom | DE | telekom.com | https://www.telekom.com/de/medien/medieninformationen | Newsroom (statisch) (item_selector: `div.content-wrapper`) | 13 Meldungen, 13 datiert, neuestes 2026-07-30, 4 im 8-Tage-Fenster |
| Elisa | FI | elisa.com | https://cms-rest-api-public.csf.elisa.fi/public/bulletins?tags=corporate.elisa.com:press&maxResults=30 | Feed (JSON-API) | 30 Meldungen, 30 datiert, neuestes 2026-07-03, 0 im 8-Tage-Fenster |
| Iliad | FR | iliad.fr | https://api.scw.iliad.fr/iliad-cms/news-items/deep-find?language=en&year=all&tag=all | Feed (JSON-API) | 40 Meldungen, 40 datiert, neuestes 2026-07-21, 0 im 8-Tage-Fenster |
| KPN | NL | kpn.com | https://www.overons.kpn/nieuws/feed/en | Feed (RSS/Atom) | 25 Meldungen, 25 datiert, neuestes 2026-07-23, 0 im 8-Tage-Fenster |
| Liberty Global | GB | libertyglobal.com | https://www.libertyglobal.com/feed/ | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-23, 0 im 8-Tage-Fenster |
| O2 Telefónica Deutschland | DE | telefonica.de | https://www.telefonica.de/o2/rss/news?category_id=10;pubdate=1 | Feed (RSS/Atom) | 20 Meldungen, 20 datiert, neuestes 2026-07-29, 1 im 8-Tage-Fenster |
| O2 Telefónica Deutschland | DE | telefonica.de | https://www.telefonica.de/o2/rss/news?category_id=11;pubdate=1 | Feed (RSS/Atom) | 20 Meldungen, 20 datiert, neuestes 2026-05-18, 0 im 8-Tage-Fenster |
| Orange | FR | orange.com | https://www.orange.com/en/newsroom | Newsroom (statisch) | 6 Meldungen, 6 datiert, neuestes 2026-07-28, 3 im 8-Tage-Fenster |
| Proximus | BE | proximus.com | https://www.proximus.com/news.html | Newsroom (statisch) | 4 Meldungen, 4 datiert, neuestes 2026-07-31, 1 im 8-Tage-Fenster |
| Swisscom | CH | swisscom.ch | https://www.swisscom.ch/en/about/news.html | Newsroom (Headless/Playwright) | hier nicht pruefbar (kein Headless-Browser), laeuft in GitHub Actions |
| TIM | IT | gruppotim.it | https://www.gruppotim.it/en/press-archive.html | Referenz (nicht automatisiert) | nicht gecrawlt (Referenz) — Erneut mit echtem Internetzugang und vollem Playwright-Render (45s, networkidle, Cookie-Consent-Klick, Scroll-Trigger) geprueft: identisches DOM zur statischen curl-Antwort (316541 Zeichen, nur 30 Nav-Links, 0 Presse-Links). 0 XHR/fetch/JSON-Responses waehrend des gesamten Renders - die Seite laedt  |
| Tele2 | SE | tele2.com | https://www.tele2.com/media/press-releases | Newsroom (statisch) (item_selector: `a.item`) | 5 Meldungen, 5 datiert, neuestes 2026-07-31, 1 im 8-Tage-Fenster |
| Telefónica | ES | telefonica.com | https://www.telefonica.com/en/feed/ | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-31, 8 im 8-Tage-Fenster |
| Telenor | NO | telenor.com | https://www.telenor.com/media/newsroom/ | Newsroom (statisch) (item_selector: `a.link-wrap`) | 10 Meldungen, 10 datiert, neuestes 2026-07-16, 0 im 8-Tage-Fenster |
| Telia | SE | teliacompany.com | https://news.cision.com/telia-company | Newsroom (statisch) (item_selector: `.card-item`) | 23 Meldungen, 23 datiert, neuestes 2026-07-17, 0 im 8-Tage-Fenster |
| Three UK | GB | three.co.uk | https://www.threemediacentre.co.uk/ | Newsroom (statisch) (item_selector: `a.card`) | 18 Meldungen, 18 datiert, neuestes 2026-07-22, 0 im 8-Tage-Fenster |
| Turkcell | TR | turkcell.com.tr | https://medya.turkcell.com.tr/bulletins/feed/ | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-31, 1 im 8-Tage-Fenster |
| VEON | NL | veon.com | https://www.veon.com/newsroom | Newsroom (statisch) | 30 Meldungen, 18 datiert, neuestes 2026-07-31, 12 im 8-Tage-Fenster |
| Vodafone Deutschland | DE | vodafone.de | https://newsroom.vodafone.de/rss | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-30, 4 im 8-Tage-Fenster |
| Vodafone Group | GB | vodafone.com | https://www.vodafone.com/tools/urlproxy/advurlproxy.aspx?settingname=news-feed&categories=*&tags=* | Feed (JSON-API) | 16 Meldungen, 16 datiert, neuestes 2026-07-31, 6 im 8-Tage-Fenster |

## Nordamerika (10)

| Betreiber | Land | Website | Quelle | Anbindung | Verifikation |
|---|---|---|---|---|---|
| AT&T | US | att.com | https://investors.att.com/news-and-events/news-releases | Newsroom (statisch) (item_selector: `tr[class*=yr-]`) | 25 Meldungen, 25 datiert, neuestes 2026-07-28, 1 im 8-Tage-Fenster |
| Bell Canada | CA | bce.ca | https://www.newswire.ca/news/bce-inc./ | Newsroom (statisch) (item_selector: `.newsCards`) | 25 Meldungen, 25 datiert, neuestes 2026-07-31, 2 im 8-Tage-Fenster |
| Charter Communications | US | charter.com | https://corporate.charter.com/page-data/sq/d/2336972469.json | Feed (JSON-API) | 40 Meldungen, 40 datiert, neuestes 2026-07-31, 3 im 8-Tage-Fenster |
| Comcast | US | comcast.com | https://www.cmcsa.com/rss/news-releases.xml | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-30, 1 im 8-Tage-Fenster |
| DISH Wireless | US | dish.com | https://ir.echostar.com/rss/news-releases.xml | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-29, 1 im 8-Tage-Fenster |
| Rogers | CA | rogers.com | https://about.rogers.com/feed | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-29, 2 im 8-Tage-Fenster |
| T-Mobile US | US | t-mobile.com | https://www.t-mobile.com/news | Newsroom (statisch) | 20 Meldungen, 19 datiert, neuestes 2026-07-28, 1 im 8-Tage-Fenster |
| Telus | CA | telus.com | https://www.telus.com/en/about/newsroom | Newsroom (Headless/Playwright) | hier nicht pruefbar (kein Headless-Browser), laeuft in GitHub Actions |
| UScellular | US | uscellular.com | https://investors.uscellular.com/news/default.aspx | Referenz (nicht automatisiert) | nicht gecrawlt (Referenz) — Kein Crawling-Problem, sondern ein Fakt: T-Mobile hat die UScellular-Mobilfunksparte uebernommen (Deal abgeschlossen 2025). investors.uscellular.com liefert per curl Cloudflare-403; mit Playwright wird die Challenge zwar bestanden, aber die Seite leitet clientseitig komplett auf investor.t-mobile.co |
| Verizon | US | verizon.com | https://www.verizon.com/about/nextgen/api/articles?limit=25&type=press_release | Feed (JSON-API) | 18 Meldungen, 18 datiert, neuestes 2026-07-30, 1 im 8-Tage-Fenster |

## Lateinamerika (7)

| Betreiber | Land | Website | Quelle | Anbindung | Verifikation |
|---|---|---|---|---|---|
| América Móvil | MX | americamovil.com | https://www.americamovil.com/rss/pressrelease.aspx?LanguageId=1 | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-20, 0 im 8-Tage-Fenster |
| Entel | CL | entel.cl | https://informacioncorporativa.entel.cl/comunicados-de-prensa | Newsroom (statisch) | 20 Meldungen, 20 datiert, neuestes 2026-07-25, 1 im 8-Tage-Fenster |
| Millicom | LU | millicom.com | https://mfn.se/all/a/millicom.rss | Feed (RSS/Atom) | 40 Meldungen, 40 datiert, neuestes 2026-07-27, 1 im 8-Tage-Fenster |
| Oi | BR | oi.com.br | https://www.oi.com.br/sala-de-imprensa/ | Newsroom (statisch) (item_selector: `.news__item`) | 6 Meldungen, 6 datiert, neuestes 2025-01-15, 0 im 8-Tage-Fenster |
| TIM Brasil | BR | tim.com.br | https://www.tim.com.br/sobre-a-tim/sala-de-imprensa | Newsroom (statisch) (item_selector: `div.artigo-sem-imagem`) | 6 Meldungen, 6 datiert, neuestes 2026-07-21, 0 im 8-Tage-Fenster |
| Telecom Argentina | AR | telecom.com.ar | https://institucional.telecom.com.ar/prensa/noticias | Newsroom (Headless/Playwright) (item_selector: `article.lastest-news-card`) | hier nicht pruefbar (kein Headless-Browser), laeuft in GitHub Actions |
| WOM | CL | wom.cl | https://sobrenosotros.wom.cl/wp-json/wp/v2/posts?categories=1&per_page=20 | Feed (JSON-API) | 20 Meldungen, 20 datiert, neuestes 2026-07-31, 1 im 8-Tage-Fenster |

## Afrika & Naher Osten (12)

| Betreiber | Land | Website | Quelle | Anbindung | Verifikation |
|---|---|---|---|---|---|
| Airtel Africa | NG | airtel.africa | https://www.investegate.co.uk/company/AAF | Newsroom (statisch) (item_selector: `tbody tr`) | 30 Meldungen, 30 datiert, neuestes 2026-07-28, 1 im 8-Tage-Fenster |
| MTN Group | ZA | mtn.com | https://www.mtn.com/feed/ | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-29, 1 im 8-Tage-Fenster |
| Maroc Telecom | MA | iam.ma | https://www.iam.ma/groupe/salle-de-presse/communiques-de-presse.aspx | Referenz (nicht automatisiert) | nicht gecrawlt (Referenz) — 403. Plan: Playwright über Residential-Proxy; bis dahin Referenz. |
| Ooredoo | QA | ooredoo.com | https://www.ooredoo.com/en/media/news_view/ | Referenz (nicht automatisiert) | nicht gecrawlt (Referenz) — 403. Plan: Playwright über Residential-Proxy; bis dahin Referenz. |
| Orange MEA | EG | orange.eg | https://orange.jo/en/corporate/media-center | Newsroom (statisch) (item_selector: `div.card`) | 6 Meldungen, 6 datiert, neuestes 2026-07-27, 1 im 8-Tage-Fenster |
| Safaricom | KE | safaricom.co.ke | https://www.safaricom.co.ke/media-center-landing/press-releases | Newsroom (statisch) | 30 Meldungen, 30 datiert, neuestes 2026-07-16, 0 im 8-Tage-Fenster |
| Turk Telekom | TR | turktelekom.com.tr | https://medya.turktelekom.com.tr/basin-bultenleri/basin-bultenleri-ve-gorseller | Newsroom (statisch) (item_selector: `a.relases-card`) | 10 Meldungen, 10 datiert, neuestes 2026-07-31, 2 im 8-Tage-Fenster |
| Vodacom | ZA | vodacom.com | https://www.vodacom.com/press-releases.php | Newsroom (Headless/Playwright) | hier nicht pruefbar (kein Headless-Browser), laeuft in GitHub Actions |
| Zain | KW | zain.com | https://www.zain.com/en/media-center | Newsroom (Headless/Playwright) (item_selector: `.PressCard`) | hier nicht pruefbar (kein Headless-Browser), laeuft in GitHub Actions |
| du | AE | du.ae | https://www.du.ae/sites/Satellite?pagename=DisplayPressRelease&Category=0&lang=en&Year=0&Month=0 | Newsroom (statisch) (item_selector: `#pMediaCentreNews .news`) | 30 Meldungen, 30 datiert, neuestes 2026-07-27, 1 im 8-Tage-Fenster |
| e& | AE | eand.com | https://www.eand.com/en/news/news-overview.html | Newsroom (statisch) (item_selector: `.tile-box-tile`) | 30 Meldungen, 30 datiert, neuestes 2026-07-30, 3 im 8-Tage-Fenster |
| stc | SA | stc.com.sa | https://www.stc.com/bin/public/assets?root=/content/dam/stc/content-fragments/press-release&isContentFragment=true&getJCRProps=false | Feed (JSON-API) | 40 Meldungen, 40 datiert, neuestes 2026-06-25, 0 im 8-Tage-Fenster |

## Asien (22)

| Betreiber | Land | Website | Quelle | Anbindung | Verifikation |
|---|---|---|---|---|---|
| AIS | TH | ais.co.th | https://www.ais.th/en/about-us/pr-news | Newsroom (statisch) (item_selector: `.content-list-div`) | 30 Meldungen, 0 datiert, neuestes -, 0 im 8-Tage-Fenster |
| Bharti Airtel | IN | airtel.in | https://www.airtel.in/press-release | Newsroom (statisch) | 30 Meldungen, 30 datiert, neuestes 2026-07-01, 0 im 8-Tage-Fenster |
| CelcomDigi | MY | celcomdigi.com | https://corporate.celcomdigi.com/newsroom | Newsroom (statisch) | 30 Meldungen, 30 datiert, neuestes 2026-07-29, 1 im 8-Tage-Fenster |
| China Mobile | CN | chinamobileltd.com | https://www.irasia.com/cgi-local/news/rss.cgi?id=chinamobile&loc=hk&t=p&title_for_section=yes | Feed (RSS/Atom) | 20 Meldungen, 20 datiert, neuestes 2026-03-26, 0 im 8-Tage-Fenster |
| China Telecom | CN | chinatelecom-h.com | https://www.irasia.com/cgi-local/news/rss.cgi?id=chinatelecom&loc=hk&t=p&title_for_section=yes | Feed (RSS/Atom) | 20 Meldungen, 20 datiert, neuestes 2026-03-24, 0 im 8-Tage-Fenster |
| Chunghwa Telecom | TW | cht.com.tw | https://www.cht.com.tw/en/home/cht/messages | Newsroom (statisch) (item_selector: `a.list-item-head-link`) | 10 Meldungen, 10 datiert, neuestes 2026-07-22, 0 im 8-Tage-Fenster |
| Globe Telecom | PH | globe.com.ph | https://www.globe.com.ph/about-us/newsroom | Newsroom (Headless/Playwright) (item_selector: `.media-card`) | hier nicht pruefbar (kein Headless-Browser), laeuft in GitHub Actions |
| Indosat Ooredoo Hutchison | ID | ioh.co.id | https://web-api.ioh.co.id/api/content-hub/public?page=1&limit=20&paginateDisable=false&site=&type=Press%20Release&lang=EN&language=EN | Feed (JSON-API) | 20 Meldungen, 20 datiert, neuestes 2026-08-01, 3 im 8-Tage-Fenster |
| KDDI | JP | kddi.com | https://newsroom.kddi.com/english/news/newsrelease.xml | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-28, 1 im 8-Tage-Fenster |
| KT | KR | corp.kt.com | https://rdi.kt.com/corp/presses/v1.0/channels/KOR/sections/ALL?limit=20&offset=1 | Feed (JSON-API) | 20 Meldungen, 20 datiert, neuestes 2026-07-29, 3 im 8-Tage-Fenster |
| Maxis | MY | maxis.com.my | https://www.maxis.com.my/en/about-maxis/newsroom/jcr:content/content/section_container/section_container/container/repository_search_co.newsroom.json?keyword=*:* | Feed (JSON-API) | 18 Meldungen, 18 datiert, neuestes 2026-07-22, 0 im 8-Tage-Fenster |
| NTT Docomo | JP | docomo.ne.jp | https://www.docomo.ne.jp/english/info/media_center/pr/ | Newsroom (statisch) | 20 Meldungen, 20 datiert, neuestes 2026-07-31, 1 im 8-Tage-Fenster |
| PLDT | PH | pldt.com | https://cms.pldt.com/drupal/api/v1/newsroom-article-list | Feed (JSON-API) | 10 Meldungen, 10 datiert, neuestes 2026-07-28, 3 im 8-Tage-Fenster |
| Rakuten Mobile | JP | rakuten.co.jp | https://corp.mobile.rakuten.co.jp/english/news/press/ | Newsroom (statisch) | 30 Meldungen, 30 datiert, neuestes 2026-07-24, 0 im 8-Tage-Fenster |
| Reliance Jio | IN | jio.com | https://www.jio.com/jcms-api/v1-press-release-page | Feed (JSON-API) | 40 Meldungen, 40 datiert, neuestes 2026-06-14, 0 im 8-Tage-Fenster |
| SK Telecom | KR | sktelecom.com | https://www.sktelecom.com/en/press/press.do | Newsroom (statisch) (item_selector: `a.link`) | 10 Meldungen, 10 datiert, neuestes 2026-07-29, 1 im 8-Tage-Fenster |
| Singtel | SG | singtel.com | https://www.singtel.com/about-us/media-centre | Newsroom (statisch) | 30 Meldungen, 30 datiert, neuestes 2026-07-24, 0 im 8-Tage-Fenster |
| SoftBank | JP | softbank.jp | https://www.softbank.jp/en/corp/news/press/ | Newsroom (Headless/Playwright) | hier nicht pruefbar (kein Headless-Browser), laeuft in GitHub Actions |
| Telkomsel | ID | telkomsel.com | https://www.telkomsel.com/en/about-us/news | Newsroom (statisch) | 8 Meldungen, 8 datiert, neuestes 2026-07-28, 2 im 8-Tage-Fenster |
| True Corporation | TH | truecorp.co.th | https://www.true.th/blog/en/feed/ | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-27, 1 im 8-Tage-Fenster |
| Viettel | VN | viettel.com.vn | https://viettel.com.vn/en/news | Newsroom (Headless/Playwright) | hier nicht pruefbar (kein Headless-Browser), laeuft in GitHub Actions |
| Vodafone Idea | IN | myvi.in | https://www.myvi.in/bin/vodafoneideadigital/newssearchservlet?search=%7B%22q%22%3A%22%2A%22%2C%22newsType%22%3A%22press%22%2C%22newsCategory%22%3A%22%2A%22%2C%22newsCircle%22%3A%22%2A%22%2C%22newsYear%22%3A0%2C%22pageNumber%22%3A1%7D | Feed (JSON-API) | 8 Meldungen, 8 datiert, neuestes 2026-06-10, 0 im 8-Tage-Fenster |

## Ozeanien (6)

| Betreiber | Land | Website | Quelle | Anbindung | Verifikation |
|---|---|---|---|---|---|
| 2degrees | NZ | 2degrees.nz | https://www.2degrees.nz/media-releases | Newsroom (Headless/Playwright) | hier nicht pruefbar (kein Headless-Browser), laeuft in GitHub Actions |
| One NZ | NZ | one.nz | https://media.one.nz/index.rss | Feed (RSS/Atom) | 10 Meldungen, 10 datiert, neuestes 2026-07-28, 1 im 8-Tage-Fenster |
| Optus | AU | optus.com.au | https://www.optus.com.au/about/media-centre/media-releases | Newsroom (statisch) | 10 Meldungen, 10 datiert, neuestes 2026-07-15, 0 im 8-Tage-Fenster |
| Spark | NZ | sparknz.co.nz | https://www.nzx.com/companies/SPK/announcements | Newsroom (statisch) (item_selector: `tbody tr`) | 17 Meldungen, 17 datiert, neuestes 2026-07-27, 1 im 8-Tage-Fenster |
| TPG Telecom | AU | tpgtelecom.com.au | https://www.tpgtelecom.com.au/media_release | Newsroom (statisch) (item_selector: `.mediaItem`) | 9 Meldungen, 9 datiert, neuestes 2026-05-15, 0 im 8-Tage-Fenster |
| Telstra | AU | telstra.com.au | https://www.telstra.com.au/exchange | Newsroom (Headless/Playwright) (item_selector: `a.tcom-article-box__link`) | hier nicht pruefbar (kein Headless-Browser), laeuft in GitHub Actions |

## Fachpresse (zweite Ebene)

| Quelle | Feed | Verifikation |
|---|---|---|
| Mobile World Live | https://www.mobileworldlive.com/feed/ | 30 Meldungen, 30 datiert, neuestes 2026-07-31, 30 im 8-Tage-Fenster |
| Light Reading | https://www.lightreading.com/rss.xml | 40 Meldungen, 40 datiert, neuestes 2026-07-31, 40 im 8-Tage-Fenster |
| Fierce Network | https://www.fierce-network.com/rss/xml | 25 Meldungen, 25 datiert, neuestes 2026-07-31, 25 im 8-Tage-Fenster |
| Total Telecom | https://totaltele.com/feed/ | 10 Meldungen, 10 datiert, neuestes 2026-07-27, 1 im 8-Tage-Fenster |
| RCR Wireless | https://www.rcrwireless.com/feed | 10 Meldungen, 10 datiert, neuestes 2026-07-31, 10 im 8-Tage-Fenster |
| Developing Telecoms | https://developingtelecoms.com/?format=feed&type=rss | 34 Meldungen, 34 datiert, neuestes 2026-07-31, 32 im 8-Tage-Fenster |
| Mobile Europe | https://www.mobileeurope.co.uk/feed/ | 10 Meldungen, 10 datiert, neuestes 2026-07-31, 10 im 8-Tage-Fenster |
| Broadband TV News | https://www.broadbandtvnews.com/feed/ | 10 Meldungen, 10 datiert, neuestes 2026-07-31, 10 im 8-Tage-Fenster |
| Telecoms Tech News | https://www.telecomstechnews.com/feed/ | 10 Meldungen, 10 datiert, neuestes 2026-07-30, 3 im 8-Tage-Fenster |
| The Fast Mode | https://www.thefastmode.com/?format=feed&type=rss | 40 Meldungen, 40 datiert, neuestes 2026-07-31, 40 im 8-Tage-Fenster |
| Telecompetitor | https://www.telecompetitor.com/feed/ | FEHLER: HTTPStatusError: 403 with UA 'TelcoRadar/1.0 (+https:/...' |
| TelecomTalk | https://telecomtalk.info/feed/ | 20 Meldungen, 20 datiert, neuestes 2026-08-01, 20 im 8-Tage-Fenster |
| ISPreview UK | https://www.ispreview.co.uk/index.php/feed | 8 Meldungen, 8 datiert, neuestes 2026-08-01, 8 im 8-Tage-Fenster |
| CommsRisk | https://commsrisk.com/feed/ | 10 Meldungen, 10 datiert, neuestes 2026-07-31, 3 im 8-Tage-Fenster |
