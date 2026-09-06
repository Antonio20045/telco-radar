# Saturn-Spike — ein Gerätepreis, ehrlich gemessen (05.09.2026)

Auftragsgrundlage: `BRIEF_SATURN_SPIKE.md` (Workspace-Engineer), Pflichtlektüre
`QUELLEN_MAP.md` Abschnitt „Händler (A-R3)". Spike, **kein Produktionscode**:
Ergebnis ist ein Wegwerf-Skript unter `scripts/spike_saturn_geraetepreis.py`
plus dieser Bericht. Kein Test, keine Konfiguration, kein State angefasst.

Diese Fassung ist die **dritte**: zwei `diff-reviewer`-Durchläufe vor dem
Commit haben insgesamt zwei schwere Fehler (falsch zugeordnete
Marktplatz-Erkennungsregel, überclaimte Netzruhe) und mehrere kleinere
Präzisionsfehler (u. a. eine unvollständige Disallow-Liste, unbelegte
Statuscode-Aussagen, ein widersprüchlicher Modul-Kommentar) gefunden — alle
sind unten korrigiert, mit neu erhobenen, präziseren Belegen. Details siehe
Abschnitt „Was der Review korrigiert hat".

## Ergebnis in einem Satz

Saturn liefert den reinen Gerätepreis **serverseitig gerendert** in zwei
unabhängigen, standardkonformen JSON-Strukturen derselben HTML-Antwort —
ganz ohne Bündelrabatt, nachweislich **ohne dass ein Browser die Antwort
erst rendern müsste** (ein reiner `curl`/`urllib`-Abruf liefert dieselben
Zahlen); die im Auftrag genannte Kategorie-URL ist dagegen eine **tote/
veraltete Kategorie-ID** (0 Artikel, kein Bot-Block) und keine geeignete
Zielseite.

## 1. Der Preis, belastbar mit Gegenprobe

**APPLE iPhone 17 Pro 5G 256 GB Tiefblau Dual SIM — 1.179,00 €**
(reiner Gerätepreis ohne Vertrag, Kategorie „Handys ohne Vertrag";
UVP/Streichpreis 1.299,00 €, versandkostenfrei laut Seite; **Saturn selbst
als Verkäufer**, kein Marktplatzangebot — geprüftes Feld, siehe §2).

- Quelle: `https://www.saturn.de/de/brand/apple/iphone/iphone-17-pro`
  (aktuelle, im Sitemap-Index geführte Markenseite; Saturn-Produkt-ID
  3013587)
- Abgerufen: 2026-09-05, sowohl per reinem HTTP-GET (`urllib`, 13:26 UTC)
  als auch per Playwright/Chromium (13:29 UTC), beide mit dem ehrlichen UA
  `TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)`
- **Screenshot-Gegenprobe:** `/tmp/saturn-spike-2026-09-05-brand-iphone17pro.png`
  — zeigt „APPLE iPhone 17 Pro 5G 256 GB Tiefblau Dual SIM", „UVP 1299,– €"
  (durchgestrichen), „**1179,– €**", „Bezahle in 36 Raten à 38,25 €", **und**
  den Preisfilter der Seite mit „Von (€) 1179 / Bis (€) 1589" — deckt sich
  exakt mit dem Minimum/Maximum der vier unten extrahierten Preise. Kein
  Zweifel zwischen Zahl und Anzeige (das Bild wurde mit den Augen geprüft,
  nicht nur maschinell verglichen).
- **Zweifache Gegenprobe, zwei unabhängige STRUKTURIERTE Quellen derselben
  Antwort, beide auf den Cent gleich** (die dritte, ursprünglich als
  „DOM-Regex" geplante automatische Quelle war in der ersten Fassung dieses
  Skripts fehlerhaft — siehe „Was der Review korrigiert hat" — und wurde
  ersatzlos entfernt statt geflickt; die Screenshot-Sichtprüfung bleibt als
  manuelle, nicht automatisierte Gegenprobe bestehen):

  | Quelle | Fundstelle | Preis | Nur mit Browser? |
  |---|---|---|---|
  | `<script type="application/ld+json">`, `@type: ItemList` | `itemListElement[0].item.offers.price` | 1179 | **Nein** — bereits im reinen `urllib`-GET vorhanden |
  | `window.__PRELOADED_STATE__` (Apollo-Cache) | `apolloState["CofrPriceFeature:…3013587…"].price.amount` | 1179 | **Nein** — ebenfalls |

  Reproduzierbar über die gespeicherten Artefakte:
  `/tmp/saturn-spike-2026-09-05-brand-iphone17pro-http-static-report.json`
  (reiner HTTP-Abruf, kein Playwright) und
  `/tmp/saturn-spike-2026-09-05-brand-iphone17pro-network.json`
  (Playwright-Lauf, inkl. vollem Netzwerkmitschnitt).

**Generalitäts-Check (kein Einzelfall):** dieselbe Struktur liefert auch
`https://www.saturn.de/de/brand/apple/iphone/iphone-17` — 12 Varianten,
reiner `urllib`-Abruf, kein Playwright nötig
(`/tmp/saturn-spike-2026-09-05-brand-iphone17-http-static-report.json`).
**Wichtiger Befund an genau dieser zweiten Seite** (siehe §2): von den 12
gelisteten Angeboten sind nur **5 tatsächlich Saturn-eigen** (939,99 € für
die vier Standardvarianten, 939,99 € Lavendel), die übrigen **7 sind
Marktplatz-Drittanbieter** (technik-guenstiger, Clevertronic, buyZOXS,
Media-Reich GmbH, Revalis) mit Preisen von 1.080 € bis 2.036 € — ohne
Filterung nach dem Marktplatz-Feld hätte die „günstigste Zahl" der Seite
in mindestens einem Fall (Revalis, 1.080–1.102 €) fälschlich als
Saturn-Preis gegolten.

## 2. Struktur-Fund — wo die Zahl steht (und wie man Fremdanbieter aussortiert)

Zwei unabhängige, **beide bereits serverseitig gerenderte** Fundstellen in
derselben HTML-Antwort (kein GraphQL-Nachladen für den Preis nötig):

### 2a. `application/ld+json`, `@type: ItemList` (Preis, aber ohne Verkäufer-Feld)

Auf jeder Marken-/Modell-Übersichtsseite (`/de/brand/<hersteller>/<serie>/<modell>`)
steht ein Standard-schema.org-Block mit allen aktuell verkauften Varianten:

```json
{
  "@context": "https://schema.org",
  "@type": "ItemList",
  "itemListElement": [
    {"@type": "ListItem", "position": 1, "item": {
      "@type": "Product",
      "name": "APPLE iPhone 17 Pro 5G 256 GB Tiefblau Dual SIM",
      "offers": {"@type": "Offer", "price": 1179, "priceCurrency": "EUR"}
    }}
  ]
}
```

**Dieser Block allein reicht NICHT, um Saturn-eigene von
Marktplatz-Angeboten zu unterscheiden** — er trägt kein Verkäuferfeld. Für
den reinen Gerätepreis dieses Projekts (§1 der Handover-Regel „Leitzahl ist
der reine Gerätepreis") ist §2b zwingend als zweite Stufe nötig.

Auf der Einzel-Produktseite (`/de/product/_<slug>-<id>.html`) steht
zusätzlich ein `BuyAction`/`ProductGroup`-Block (anderer `@type`, KEIN
`ItemList` — das Skript unterscheidet die Typen und liest hier `[]` für
`ld_json_itemlist`, das ist korrekt, nicht leer wegen eines Fehlers) mit
`gtin13`, `sku` und `hasVariant[]`.

### 2b. `window.__PRELOADED_STATE__` (Apollo-Normalized-Cache) — trägt das Verkäufer-Feld

```
window.__PRELOADED_STATE__ = { "apolloState": {
  "CofrPriceFeature:{\"id\":\"Saturn:de:3013587\",...}": {
    "price": {"amount": 1179, "shippingCost": 4.99, "installment": {...}},
    "strikePrice": {"amount": 1299, "type": "RRP"},
    "currency": "EUR",
    "isProductOfTypeMarketplace": false,
    "marketplaceSeller": null
  },
  "GraphqlProduct:Saturn:de-DE:3013587": {
    "title": "APPLE iPhone 17 Pro 5G 256 GB Tiefblau Dual SIM",
    "url": "/de/product/_apple-iphone-17-pro-5g-256-gb-tiefblau-dual-sim-3013587.html",
    "breadcrumbs": [{"name": "Handys ohne Vertrag"}, ...]
  }
}}
```

**Korrektur gegenüber der ersten Fassung dieses Berichts:** das
Erkennungsmerkmal für Marktplatz-Angebote ist `isProductOfTypeMarketplace`
/ `marketplaceSeller` — beides Felder **auf dem `CofrPriceFeature`-Objekt
selbst**, nicht auf `GraphqlProduct`, und **nicht** verlässlich an einem
Klammer-Suffix in der ID erkennbar. Live nachgemessen an
`/de/brand/apple/iphone/iphone-17`:

| Produkt-ID | Titel | Preis | `isProductOfTypeMarketplace` | Verkäufer |
|---|---|---|---|---|
| 3013575–3013579 (5×) | APPLE iPhone 17 5G 256 GB … | 939,99 € | `false` | — (Saturn) |
| 168733642 | APPLE iPhone 17 256 GB Lavendel Dual SIM | 1.084,06 € | `true` | technik-guenstiger |
| 161651044 | APPLE IPHONE 17 512 GB Lavendel Dual SIM | 1.142,41 € | `true` | Clevertronic |
| 161651569 | APPLE IPHONE 17 512 GB Salbei Dual SIM | 1.319,37 € | `true` | buyZOXS |
| 161651734 | APPLE IPHONE 17 512 GB Weiß Dual SIM | 2.036,00 € | `true` | Media-Reich GmbH |
| 168733538 / 168733788 / 168733862 | APPLE iPhone 17 …, 3× | 1.080–1.102 € | `true` | Revalis |

**Keine** der `false`-IDs trägt ein Klammer-Suffix, aber auch **keine**
der o. g. Marktplatz-IDs trägt eins — die Klammer-Suffix-Form
(`"Saturn:de:165777527[1792976363]"`) kommt separat auf der
**Produktdetailseite** vor (Cross-Sell-Widget „Zusätzlich neue und
refurbished Angebote ab …", `/de/product/_apple-iphone-17-pro-5g-256-gb-tiefblau-dual-sim-3013587.html`,
Belegt in `/tmp/saturn-spike-2026-09-05-product-3013587-http-static-report.json`)
und ist DORT ebenfalls über dasselbe Feld, nicht über die Klammer,
erkennbar. Das Zielmodell dieses Spikes (iPhone 17 **Pro**) hat auf seiner
eigenen Markenseite `isProductOfTypeMarketplace: false` für alle vier
Varianten (§1) — die 1.179-€-Zahl ist also echt Saturn-eigen, nicht
zufällig die günstigste eines Drittanbieters.

**Zweiter Fund derselben Produktdetailseite: derselbe `product_id` kann
unter zwei verschiedenen Apollo-Schlüsseln liegen** (mit/ohne
`installment`-Unterauswahl in der ursprünglichen GraphQL-Query-Form,
gleicher Betrag in beiden Fällen). Belegt für die ID `3013587` auf genau
dieser Seite:
`duplicate_apollo_keys_for_same_product_id: ["3013587"]` im selben Report.
Ein Adapter matcht über das Feld `id` im Wert und dedupliziert danach —
nie über den vollen Schlüsseltext (das Skript tut das bereits,
`_dedupe_by_product_id`).

## 3. Messgrenze: die im Auftrag genannte Kategorie-URL

`https://www.saturn.de/de/category/_apple-iphone-17-pro-701440.html`
(Aufgabe 2 des Briefs) ist **HTTP 200, aber leer** — kein Bot-Block, keine
Umleitung, sondern eine inhaltlich tote Kategorie-ID:

- Reiner `urllib`-Abruf (ohne JS): „0 Artikel", „Ups! Wir konnten leider
  keine Ergebnisse finden." — `preloaded_state_found: true`,
  `price_features_from_ssr_state: []`, `ld_json_itemlist: []`
  (`/tmp/saturn-spike-2026-09-05-category-701440-http-static-report.json`).
- Playwright/Chromium-Rendering derselben URL: identisches strukturelles
  Ergebnis (`/tmp/saturn-spike-2026-09-05-category-701440-network.json`).
  **Ehrlich vermerkt:** in diesem EINEN Browser-Lauf wurde die Netzruhe
  (`networkidle`, 20 s Fenster) NICHT erreicht (`networkidle_reached:
  false`, Ursache laufende Analytics-/Ad-Tracking-Beacons ohne Ende —
  Google, Pinterest, DoubleClick, Forter, Talkative; keiner davon ein
  Saturn-eigener Preis-Request). Das Skript ist danach 5 s fest gewartet
  und hat den Seiteninhalt trotzdem vollständig erfasst — die fehlende
  Netzruhe ist eine Eigenschaft der Seite (Dauer-Tracking), keine
  unvollständige Messung dieses Spikes; belastbar ist das Ergebnis, weil
  der **davon unabhängige** reine `urllib`-Abruf (ohne jedes Warten auf
  Netzruhe, siehe oben) exakt dasselbe strukturelle Ergebnis liefert.
- **Screenshot-Beleg:** `/tmp/saturn-spike-2026-09-05-category-701440.png`
  (identischer „0 Artikel"-Zustand wie im reinen HTTP-Abruf — Bild und
  Rohdaten stimmen überein, kein Rendering-Artefakt).
- Diagnose: die Sitemap-Datei `sitemap-productlistpages.xml` führt heute
  **keine** Kategorie `apple-iphone-17-pro-701440` mehr; die Kategorie-ID
  ist entweder umbenannt oder ausgelaufen. Der ursprüngliche Recon-Treffer
  „HTTP 200 gemessen" war korrekt, hat aber nur den Statuscode geprüft,
  nicht den Inhalt.
- Die **korrekte, aktuelle** Zielseite für dasselbe Modell steht im
  Sitemap-Index unter `sitemap-brandpages.xml`:
  `/de/brand/apple/iphone/iphone-17-pro` (siehe §1) — kein Umgehungsweg,
  sondern die vom Betreiber selbst als aktuell ausgezeichnete URL für
  exakt dieselbe Fragestellung.

## 4. Die drei ehrlichen Ausfallarten (Aufgabe 4) — einzeln geprüft

Gemessen an: zwei reinen `urllib`-Abrufen ohne JS (Marke iPhone 17 Pro,
Marke iPhone 17, dazu Produktdetail und die Kategorie-URL — vier statische
Abrufe insgesamt) und zwei Playwright/Chromium-Läufen (Marke iPhone 17 Pro,
Kategorie-URL) über gut vier Minuten Laufzeit (13:26–13:30 UTC).

| Ausfallart | Beobachtet? | Beleg |
|---|---|---|
| **Bot-Erkennung** | Nein. Saturn läuft hinter Cloudflare (`server: cloudflare`, `cf-cache-status`-Header auf jeder Antwort), aber kein einziger der vier statischen `http_status`-Werte (alle 200) und keine der von den zwei Chromium-Läufen erfassten **GraphQL-Antworten** (`graphql_responses[].status`, jeweils vollständig protokolliert) war 403/429 oder eine Challenge-Seite — beide Läufe: ausschließlich Status 200 auf allen 8 gesehenen GraphQL-Aufrufen. Unter den insgesamt 90 sonstigen XHR/Fetch-Antworten beider Läufe traten 3× Status 204 auf (No Content) — ausschließlich auf **Drittanbieter-Trackingdomains** (`ad.doubleclick.net`, `region1.analytics.google.com`), nie auf `saturn.de` selbst; 204 ist die normale Antwort einer akzeptierten Tracking-Pixel-Anfrage, kein Abwehrsignal. Vollständige Liste in `non_200_responses` beider Netzwerkmitschnitte. |
| **Captcha** | Nein. Keine Cloudflare-Turnstile-Seite, kein „Bitte bestätigen Sie, dass Sie ein Mensch sind" in irgendeiner der vier geladenen Seiten (weder in den zwei Screenshots noch im gespeicherten HTML der zwei statischen Abrufe). |
| **Leere Werte** | **Ja, einmal, dokumentiert in §3.** Die im Auftrag genannte Kategorie-URL liefert strukturell korrektes, aber leeres Ergebnis (0 Artikel) — eine echte Messgrenze dieser einen URL, kein allgemeiner Ausfall von Saturn als Quelle. Auf allen anderen geprüften Seiten (Marke iPhone 17 Pro, Marke iPhone 17, Produktdetail) waren die Preisfelder vollständig gefüllt. |

## 5. Robots.txt — was tatsächlich geprüft wurde (nicht nur behauptet)

Ein Befund dieses Spikes, der über die im Auftrag genannten zwei
GraphQL-Operationen hinausgeht: **eine rein passive Chromium-Seitenlast
löst von sich aus Requests auf mehrere weitere, in der `*`-Gruppe der
robots.txt gesperrte Pfade aus** — nicht durch eine Handlung dieses
Skripts, sondern durch Skripte, die Saturn selbst in die Seite einbettet:

| Gesperrter Pfad | Was ihn auslöst | Beobachtet |
|---|---|---|
| `/cdn-cgi/challenge-platform/…` | Cloudflares eigenes Bot-Management-Skript, lädt sich selbst nach | jedem Chromium-Lauf |
| `/api/v1/msg` | ein Konfigurations-Ping (vermutlich Chat-Widget) | mehrfach je Lauf |
| `/public/setCookie/ts_id/…` | ein Tracking-Cookie-Endpunkt | 2× je Lauf |

Das ist der entscheidende, praktische Grund, warum ein reiner
HTTP-GET (§1, §2, kein Browser) hier nicht nur billiger, sondern auch
**robots-sauberer** ist: er löst KEINEN dieser drei Requests überhaupt
aus, weil er kein JavaScript ausführt. Für den Browser-Modus dieses
Skripts ist die **vollständige** Disallow-Liste der `*`-Gruppe (18 Muster,
inkl. Wildcards wie `/*shopfallback*`) seit dieser Fassung aktiv per
`page.route()` blockiert — dieselbe Liste, aus der auch der nachträgliche
Audit unten liest (keine zwei unabhängig gepflegten Listen mehr), geprüft
gegen URL UND POST-Body, damit ein per POST gesendetes persisted-Query-Objekt
nicht durchrutscht (Einschränkung: der Body-Check verlangt exakt
`"operationName": "…"` mit optionalem Leerraum um den Doppelpunkt — ein
strukturell anderes JSON-Feldformat würde nicht erkannt; in keinem der
beobachteten Requests war das der Fall). Nachweis, dass der Handler
wirklich feuert (nicht nur „nichts gefunden, weil nie geprüft"): in beiden
Playwright-Läufen ist `graphql_requests_seen_by_handler` (8 bzw. 8) exakt
gleich `graphql_response_count` (8 bzw. 8) — jeder vom Handler gesehene
GraphQL-Request hat auch tatsächlich eine Antwort erzeugt, und
`blocked_tabu_calls` listet in beiden Läufen 6–7 tatsächlich abgefangene
Treffer (Cloudflare-Challenge-Skript, Tracking-Cookie, Chat-Ping — keiner
davon eine GraphQL-Operation).

Zusätzlich: jede von der Seite ausgelöste, NICHT blockierte XHR/Fetch-Antwort
steht vollständig im Report (`xhr_fetch_responses`, mit Statuscode, 36–54
pro Lauf) und wurde ein zweites Mal gegen dieselbe Disallow-Liste geprüft
(`robots_disallow_audit_hits`) — Ergebnis in beiden Läufen: **leer**. Das
deckt nur Antworten vom Typ `xhr`/`fetch`; andere Ressourcentypen (z. B.
Skript- oder Bild-Requests) werden VOR einer möglichen Antwort bereits vom
selben Blocker abgefangen, tauchen im Audit also gar nicht erst auf, weil
sie nie durchgelassen wurden.

Die zwei im Auftrag genannten Tabu-Operationen selbst wurden bei keinem der
beiden Browser-Läufe (Marke iPhone 17 Pro, Kategorie-URL — die zwei
weiteren Abrufe dieses Spikes liefen im reinen HTTP-Modus ohne
JavaScript-Ausführung und konnten schon konstruktionsbedingt keine
GraphQL-Operation auslösen) auch nur ausgelöst — die dort beobachteten
GraphQL-Operationen waren `GetConsentCategories`, `GetChatsConfiguration`,
`ProductComparisonConfig`, `GetUser`, `PWAConsentLayer`, `GetBrandHub`. Sie
gehören zu einem anderen Feature (Finanzierungs-/Vertragsbündel beim
Checkout) und sind für einen
reinen Gerätepreis-Adapter ohnehin irrelevant.

## 6. Empfehlung: **Adapter lohnt sich — und günstiger als erwartet**

Nicht nur „lohnt sich", sondern **einfacher als der Playwright-Weg, den der
Auftrag als notwendig unterstellt hat**: die Preisdaten stehen bereits in
der ersten HTTP-Antwort, kein `newsroom_js`-artiger Browser-Collector
nötig — und §5 zeigt, dass der Browser-Weg sogar zusätzliche,
robots-sensible Requests mit sich bringt, die der reine HTTP-Weg
grundsätzlich vermeidet.

1. **Kein Playwright in Produktion.** Ein `httpx`-GET mit dem bestehenden
   `TelcoRadar/1.0`-UA auf `/de/brand/<hersteller>/<serie>/<modell>`
   reicht; Extraktion über `json.loads` auf den ld+json-`ItemList`-Block
   (§2a), **zwingende** zweite Stufe: Filter auf `isProductOfTypeMarketplace
   is False` aus dem Apollo-Cache (§2b) gegen Marktplatz-Vermischung —
   ohne diese Stufe wäre in mindestens einem beobachteten Fall (§1, iPhone
   17 Standard) ein Drittanbieterpreis als Saturn-Preis in die Leitzahl
   gelaufen.
2. **Eine Konfigurationszeile pro beobachtetem Modell**, keine
   Kategorie-ID-Recherche nötig — die URL-Form
   `/de/brand/apple/iphone/iphone-17-pro` ist stabil, menschenlesbar und
   steht selbst im Sitemap-Index (`sitemap-brandpages.xml`), lässt sich
   also auch automatisiert gegen den Produktkatalog abgleichen.
3. **robots.txt erlaubt den ganzen Pfad** (`/de/brand/…`, `/de/product/…`,
   `/de/category/…` sind nicht gesperrt); die zwei tabuisierten
   GraphQL-Operationen werden von diesen Seiten nie aufgerufen, und der
   reine HTTP-Weg löst keinen der in §5 gefundenen Zusatz-Requests aus.
4. **Zwei Pflichtpunkte für einen echten Adapter (kein Blocker, aber
   Pflicht vor Produktivsetzung):**
   - Marktplatz-Filterung aus §2b zwingend einbauen (s. o.).
   - Denselben `product_id`-Dedup wie in diesem Skript (`_dedupe_by_product_id`)
     übernehmen — auf der Produktdetailseite trägt dieselbe SKU zwei
     Apollo-Schlüssel mit demselben Preis (§2b).
5. **Nicht Teil dieses Spikes, aber naheliegend:** ein künftiger Adapter
   sollte grundsätzlich `/de/brand/…`-URLs verwenden, nicht
   `/de/category/…`-IDs, weil letztere laut diesem Befund nicht stabil
   sind (§3).

## Was der Review korrigiert hat

Vor dem Commit hat ein `diff-reviewer`-Durchlauf die erste Fassung dieses
Skripts und Berichts geprüft und zwei schwere und mehrere kleinere Befunde
gemeldet. Zur Nachvollziehbarkeit, was geändert wurde und warum:

1. **Falsch zugeordnete Marktplatz-Erkennung.** Die erste Fassung nannte
   ein „Klammer-Suffix in der ID" als Erkennungsmerkmal und behauptete das
   Feld stehe auf `GraphqlProduct`. Beides war falsch bzw. ungenau — das
   richtige, verlässliche Feld ist `isProductOfTypeMarketplace` /
   `marketplaceSeller` auf `CofrPriceFeature` selbst (§2b, neu mit echten
   Messwerten belegt).
2. **Überclaimte Netzruhe.** Die erste Fassung schrieb „identisches
   Ergebnis nach Netzruhe", obwohl beide Playwright-Läufe das
   20-Sekunden-`networkidle`-Fenster wegen dauerhafter Tracking-Beacons nie
   erreicht haben (`idle_error` in beiden Netzwerkmitschnitten). Jetzt in
   §3 präzise benannt, inklusive der Ursache.
3. **Fragile, unbenutzte DOM-Regex entfernt statt geflickt.** Ein
   Preis-Regex auf den sichtbaren Seitentext verlor bei Beträgen ohne
   Tausenderpunkt die führende Ziffer (aus „1179,00" wurde „179,00") und
   wurde im Bericht nicht als dritte Quelle zitiert, hätte aber in einer
   künftigen Iteration leicht als solche missverstanden werden können. Die
   Funktion ist ersatzlos aus dem Skript entfernt.
4. **Robots-Audit erweitert statt nur behauptet.** Die erste Fassung
   blockierte ausschließlich die zwei benannten GraphQL-Operationen und
   verwarf die Liste aller sonst gesehenen Requests. Jetzt: alle
   XHR/Fetch-URLs stehen im Report, zusätzlich aktiv blockiert werden drei
   real beobachtete, robots-gesperrte Pfade, die die Seite von sich aus
   nachlädt (§5) — ein Befund, der erst durch das genaue Hinsehen bei der
   Review-Nachmessung sichtbar wurde.
5. **Tabu-Prüfung auf POST-Body erweitert**, `--tag` gegen Pfad-Traversal
   bereinigt, Parse-Fehler von `window.__PRELOADED_STATE__` werden jetzt
   mit Grund unterschieden statt still auf `None` abgebildet.

Eine ZWEITE Review-Runde auf diese bereits korrigierte Fassung hat sechs
weitere, kleinere Präzisionsfehler gefunden — alle behoben, ebenfalls zur
Nachvollziehbarkeit:

6. **Statuscodes wurden im Browser-Modus gar nicht erfasst.** §4 behauptete
   „alle Statuscodes 200", ohne dass das Skript je einen Statuscode
   speicherte — unbelegbar. Jetzt trägt jede erfasste Antwort ihren
   Statuscode (`xhr_fetch_responses`, `graphql_responses`), und ein neues
   Feld `non_200_responses` macht die drei tatsächlich aufgetretenen
   204er (Drittanbieter-Tracking, siehe §4) sichtbar statt sie zu
   verschweigen.
7. **Die unerklärte Lücke zwischen „gesehenen" und „beantworteten"
   GraphQL-Requests** (9 gegen 7 bzw. 8 gegen 6 in der ersten Fassung) lag
   daran, dass GraphQL-Antworten nur gezählt wurden, wenn Playwright sie als
   `xhr`/`fetch` klassifizierte. Jetzt werden GraphQL-Antworten unabhängig
   vom Ressourcentyp gezählt; beide Zahlen sind seither in beiden Läufen
   identisch (8 = 8).
8. **Die Disallow-Liste war ein von Hand gepflegter „Auszug"** (Kommentar
   sagte es selbst), dem vier Muster der `*`-Gruppe fehlten
   (`/*MultiChannelMARepairStatusResult*`, die Verfügbarkeits-Endpunkt-Zeile,
   `*de/list/*_*`, `*de/promo-list/*`), während der Bericht „volle
   Disallow-Liste" behauptete. Block-Regex und Audit-Funktion lesen jetzt
   aus derselben, vollständigen `_ROBOTS_DISALLOW_PATTERNS`-Liste (18
   Muster, mit korrekter `*`-Wildcard-zu-Regex-Übersetzung statt reiner
   Teilstring-Suche) — eine Änderung an der einen Stelle kann beide nicht
   mehr auseinanderlaufen lassen.
9. **Der Modul-Kopf widersprach dem eigenen Code**: er beschrieb die
   Disallow-Pfade als „durchgelassen und nur beobachtet", während der Code
   sie längst aktiv blockierte. Text korrigiert.
10. **Ungenaue Formulierungen präzisiert**: „vier Seitenaufrufe" in §4/§5
    zählte zwei reine HTTP-Abrufe (die schon konstruktionsbedingt kein
    JavaScript und damit keine GraphQL-Operation auslösen konnten) und zwei
    Browser-Läufe zusammen, ohne den Unterschied zu nennen — nachgezogen.
    Eine Zeitangabe „gut 25 Minuten" war um mehr als das Sechsfache zu hoch
    gegriffen (tatsächlich rund vier Minuten für den finalen Testlauf,
    gemessen an den Zeitstempeln der Artefakte); ebenfalls korrigiert. Die
    POST-Body-Prüfung toleriert jetzt Leerraum um den Doppelpunkt
    (`"operationName": "X"` statt nur `"operationName":"X"`), mit der Grenze
    des Verfahrens (ein strukturell anderes JSON-Format würde weiterhin
    nicht erkannt) offen benannt statt verschwiegen.

## Anhang — Belege

| Datei | Inhalt |
|---|---|
| `/tmp/saturn-spike-2026-09-05-brand-iphone17pro.png` | Screenshot-Gegenprobe zum Preis (§1) |
| `/tmp/saturn-spike-2026-09-05-brand-iphone17pro-network.json` | Playwright-Lauf: voller Netzwerkmitschnitt, robots-Audit, extrahierter State |
| `/tmp/saturn-spike-2026-09-05-brand-iphone17pro-http-static-report.json` | Reiner HTTP-Abruf (kein Playwright) derselben Seite — Beleg für „kein Browser nötig" |
| `/tmp/saturn-spike-2026-09-05-brand-iphone17pro-http.html` | Rohes HTML dazu |
| `/tmp/saturn-spike-2026-09-05-brand-iphone17-http-static-report.json` | Generalitäts-Check + Marktplatz-Befund (§1, §2b) |
| `/tmp/saturn-spike-2026-09-05-brand-iphone17-http.html` | Rohes HTML dazu |
| `/tmp/saturn-spike-2026-09-05-product-3013587-http-static-report.json` | Produktdetailseite: Klammer-Suffix-Marktplatzangebote, Dubletten-Beleg (§2b) |
| `/tmp/saturn-spike-2026-09-05-product-3013587-http.html` | Rohes HTML dazu |
| `/tmp/saturn-spike-2026-09-05-category-701440.png` | Screenshot-Beleg zur leeren, im Auftrag genannten Kategorie-URL (§3) |
| `/tmp/saturn-spike-2026-09-05-category-701440-network.json` | Playwright-Lauf zur leeren Kategorie-URL |
| `/tmp/saturn-spike-2026-09-05-category-701440-http-static-report.json` | Reiner HTTP-Abruf zur leeren Kategorie-URL |
| `scripts/spike_saturn_geraetepreis.py` | Das Spike-Skript selbst (Wegwerf-Diagnose, kein Adapter) |

Aufruf zur Reproduktion:

```bash
# Reiner HTTP-Abruf (kein Playwright) - der eigentliche Beweis
/opt/homebrew/bin/python3 scripts/spike_saturn_geraetepreis.py \
    --mode static --url "https://www.saturn.de/de/brand/apple/iphone/iphone-17-pro" \
    --tag brand-iphone17pro-http

# Browser-Lauf mit Screenshot-Gegenprobe
/opt/homebrew/bin/python3 scripts/spike_saturn_geraetepreis.py \
    --mode browser --url "https://www.saturn.de/de/brand/apple/iphone/iphone-17-pro" \
    --tag brand-iphone17pro

# Messgrenze: die im Auftrag genannte, leere Kategorie-URL
/opt/homebrew/bin/python3 scripts/spike_saturn_geraetepreis.py \
    --mode browser --url "https://www.saturn.de/de/category/_apple-iphone-17-pro-701440.html" \
    --tag category-701440
```
