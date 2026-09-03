# Strategie: Gerätepreise und Total Cost of Ownership

**Phase 0 — Audit und Plan.** Erstellt am 03.09.2026. Alle Live-Messungen
dieses Dokuments stammen vom **03.09.2026**; alle Datei-Belege beziehen sich auf
den Repo-Stand desselben Tages (Arbeitskopie sauber,
`git status --porcelain` = 0 Einträge).

**Korrekturstand 03.09.2026:** Dieses Dokument wurde unabhängig verifiziert; die
zwölf Widerlegungen des Prüfberichts (W1–W12) sind eingearbeitet. Die
schwerwiegendsten: o2 bietet **keine** 48-Monats-Geräteraten (nur 24 oder 36),
Vodafones Ratenvarianten tragen `financingType: rate` statt `sub`, und die
AWS WAF der Telekom ist **vorhanden**, blockiert die Kategorieseite aber nicht.
Die vier Befunde und die Modellentscheidung „jede Zahl bekommt eine Preisform"
sind durch die Prüfung bestätigt.

---

## 0. Kurzfassung

Die Geräteseite zeigt in **einer** Spalte mit **einer** Überschrift („Preis",
Preisart „ohne Vertrag") vier verschiedene Größen, die keine gemeinsame Einheit
haben:

| Anbieter | Was die Zahl WIRKLICH ist | Beleg |
|---|---|---|
| freenet / Medimax / EP / ALDI TALK | Barpreis (`schema.org/Offer.price`) | `strukturdaten.py:192` |
| **o2** | **Gesamtbetrag einer 24-Monats-Ratenzahlung** (`totalPrice`, 0 % Zins) | `o2.py:98`, Live 03.09.2026 |
| **Vodafone** | **Listenpreis ohne Rabatte** aus einer `newContract`-Nutzlast; im selben Datensatz steht dieselbe Zahl als `uvp`, der wirklich berechnete Gerätebetrag als `total` = 703,00 € | `vodafone.py:153`, Live 03.09.2026 |
| Telekom | fehlt ganz | `geraete_quellen.yaml:278` |

Daraus folgen die drei Kernbefunde:

1. **Antonios ~700 € sind kein Rechenfehler, sondern ein Belegfehler.** Die
   709,90 € stehen real in Vodafones Schnittstelle — aber der Quelllink daneben
   führt auf `vodafone.de/privat/handys/iphone-15.html`, eine Seite mit dem Titel
   „**iPhone 15 mit Vertrag**", in deren ausgeliefertem HTML die Zeichenfolge
   „709" **null mal** vorkommt. Die Seite verspricht Nachprüfbarkeit und liefert
   an dieser Stelle keine. (§ 2)
2. **Der Vergleich „wer ist günstiger als Vodafone" ist derzeit nicht
   belastbar**, weil er Barpreise gegen Ratenzahlungs-Gesamtbeträge rechnet.
   Konkret am 03.09.2026: iPhone 17 256 GB steht mit 949,00 € (freenet, bar)
   gegen 1027,00 € (o2, 7 € Anzahlung + 24 × 42,50 €) in derselben Spalte —
   78 € Unterschied, der zum Teil eine Frage der Zahlweise ist, nicht des Preises.
3. **Die Telekom ist erreichbar, und ihr Gerätepreis ohne Vertrag ist lesbar.**
   Der Config-Grund „es gibt dort keinen Gerätepreis ohne Vertrag zu lesen"
   (`geraete_quellen.yaml:280`) wurde am 11.08.2026 an der **Produktseite**
   gemessen und stimmt dort. Auf der **Kategorieseite**
   `/shop/geraete/smartphones/ohne-vertrag` liefert Telekom heute 10 Geräte mit
   absoluten Beträgen im serverseitig ausgelieferten `__INITIAL_STATE__`. (§ 3)

Das Ziel dieses Dokuments ist nicht „mehr Anbieter", sondern **eine ehrliche
Preisachse**: jede Zahl bekommt eine *Preisform*, und aus Preisform plus Tarif
entsteht eine Total-Cost-of-Ownership-Rechnung, die man gegen ein
Produktinformationsblatt halten kann. Der Weg dorthin steht in acht Phasen
(§ 8), jede für sich abgeschlossen testbar.

---

## 1. Befund A — wie die Preise auf der Geräteseite entstehen

### 1.1 Der Weg einer Zahl, von der Quelle bis in die Tabelle

```
config/geraete_quellen.yaml   (Anbieter, Einstieg, methode)
        │
        ▼  collect/geraete/__init__.py:365-446   robots → Einstieg → Links → Produktseiten
   Adapter je methode  (ldjson | shopify | vodafone_api | o2_katalog | congstar_next)
        │                        __init__.py:236-266
        ▼  __init__.py:274-307   _preisfelder()  ← HIER entsteht die Preisart
   Listung  (geraete_model.py:795-861)
        │
        ▼  analyze/geraete_store.py             GeraeteDB.upsert + Preishistorie
   data/state/geraete_db.json · data/state/geraete_preise.jsonl
        │
        ▼  report/geraete_view.py · geraete_vergleich.py · geraete_alarme.py
   site/geraete.html
```

### 1.2 Es gibt genau zwei Preisarten — und nur eine wird benutzt

`collect/geraete/__init__.py:274-307` kennt zwei Fälle:

* **Bündelzahl:** `zuzahlung` + `tarif_referenz` (+ optional `preis_mit_vertrag_ab`).
  Ohne Tarifreferenz wird sie verworfen; `geraete_model.py:857-861` wirft
  zusätzlich beim Bau der `Listung`.
* **Ladenpreis:** `preis_ohne_vertrag`, geschützt durch den Lockpreis-Wächter
  (`strukturdaten.py:44`, `_LOCKPREIS_GRENZE = 30.0`) gegen die 1-Euro-Zahl aus
  Tarifbündeln.

**Gemessen am Datenbestand** (`data/state/geraete_db.json`, `updated: 2026-09-03`,
391 Listungen): **391 × `erstpreis_art: "ohne_vertrag"`, 0 × Zuzahlung.** In
`data/state/geraete_preise.jsonl` (405 Zeilen) sind `uvp`,
`preis_mit_vertrag_ab`, `zuzahlung` und `tarif_referenz` in **allen** Zeilen
`null`. Die Bündelhälfte des Modells ist gebaut und leer.

Die Felder existieren seit `geraete_model.py:810-814`:

```python
preis_ohne_vertrag: Optional[float] = None
uvp: Optional[float] = None
preis_mit_vertrag_ab: Optional[float] = None
zuzahlung: Optional[float] = None
tarif_referenz: str = ""
```

### 1.3 Die Antwort auf „nur Gerätepreis ohne Tarif?" lautet: nein, nicht durchgängig

Die Seite behauptet es zweimal ausdrücklich:

* `report/templates/geraete.html.j2:234` — `Preisart: ohne Vertrag`
* `report/templates/geraete.html.j2:314-315` — „Verglichen werden ausschließlich
  Neugeräte ohne Vertrag, jeweils der günstigste Preis je Laden."
  (wörtlich so in `site/geraete.html` ausgeliefert)

Was tatsächlich in der Spalte steht, ist je Anbieter etwas anderes:

**freenet / mobilcom-debitel (149 Listungen), Medimax, ElectronicPartner, ALDI TALK — Barpreis, sauber.**
Live 03.09.2026: `https://www.freenet.de/handys-smartphones/p/P-M-3925066?ds=P-4038730`
→ HTTP 200, `<title>iPhone 16e ohne Vertrag günstig kaufen | freenet</title>`,
`ld+json` `offers.price = "599"`, `availability: InStock`. Die 599,00 € in
`geraete_db.json` sind auf der verlinkten Seite auffindbar. **Preisform: Barkauf.**

**o2 (83 Listungen) — Gesamtbetrag einer Ratenzahlung.**
`o2.py:98` liest `price.totalPrice`. Der Endpunkt trägt die Zahlweise im Pfad:
`…/catalog/o2shop/privatkunden/**ratenzahlung**/default/…?hwOnly=true`
(`geraete_quellen.yaml:364`). Live 03.09.2026, iPhone 14 128 GB mitternacht:

```json
{"oneTimePrice": 1, "monthlyPrice": 30.0, "totalPrice": 721.0, "activationFee": 0}
```

1 + 24 × 30 = 721. Auf der verlinkten Produktseite steht das wörtlich als
„Gerät Anzahlung: 1,00 €" und „(Gesamtpreis Gerät: 721,00 €)". Der Beleg ist
also da — **aber es ist der Gesamtbetrag eines Teilzahlungsgeschäfts.** Dieselbe
Seite trägt den gesetzlichen Finanzierungshinweis („Der Sollzins liegt bei 0 %,
der effektive Jahreszins bei 0 %"). Ein Barkaufpreis wird auf o2online.de nicht
**verlinkt**: die Nutzlast von `/e-shop/` referenziert 25 Katalogadressen
(13 distinkte Pfade, Live 03.09.2026); 24 davon tragen den Pfadbestandteil
`ratenzahlung`, eine nicht (`/e-shop/rest/catalog/device-trade-in`). Wo
`vertragsart=` gesetzt ist, hat es genau einen Wert: `ratenzahlung` (89 von 89
Treffern; im Katalog 95 von 95). Das ist ein **Negativbeweis über die verlinkten
Adressen** — kein Beweis, dass o2 nirgends einen Barkauf führt.

**Vodafone (151 Listungen) — Listenpreis aus einer Bündelnutzlast.**
`vodafone.py:153-154` liest
`atomics[].prices.hardware.priceByType.rate.onetime.withoutDiscounts.gross`.
Live 03.09.2026, `virtualItem/51` (iPhone 15), `atomics[0]` = 128 GB Schwarz:

| Pfad | Wert |
|---|---|
| `prices.hardware.…rate.onetime.withoutDiscounts.gross` ← **wird gelesen** | **709,90** |
| `composition[0].priceByComponent.hardware.priceByType.**uvp**.onetime…gross` | 709,90 |
| `composition[0].…hardware.priceByType.**total**.onetime…gross` | **703,00** |
| `composition[0].…hardware.priceByType.financingAmount.onetime…gross` | 702,00 |
| `composition[0].…hardware.priceByType.rate.onetime…gross` (Anzahlung) | 1,00 |
| `composition[0].…hardware.priceByType.rate.month…gross` (Monate 1–12) | 58,50 |

1,00 + 12 × 58,50 = 703,00 = `total`. Die gelesene Zahl ist damit **deckungsgleich
mit dem `uvp`-Knoten**, nicht mit dem Betrag, den Vodafone im Bündel für das Gerät
ansetzt. Der Aufruf trägt `businessTransaction=newContract`
(`geraete_quellen.yaml:330`) — also ausdrücklich den Neuvertragskontext.

Gegenprobe: mit `businessTransaction=hardwareOnly` antwortet dieselbe
Schnittstelle mit **709,90** und ohne jeden `composition`-Block. Das stützt die
Lesart „709,90 € ist Vodafones Preis für den Gerätekauf ohne Vertrag" — es
widerlegt aber nicht, dass die Zahl ein `withoutDiscounts`-Wert ist. **Preisform:
Listenpreis, Rabattstand unbekannt.**

### 1.4 Der Vergleich filtert die Preisart, aber nicht den Anbietertyp

`report/geraete_vergleich.py:180,193` filtert Zeilen auf
`preisart == "ohne_vertrag"`. Ein Filter auf `anbieter_typ` existiert nicht;
`anbieter_typ` wird nur als Anzeigefeld durchgereicht (`geraete_vergleich.py:142`).
Deshalb stehen Barpreis (Handel) und Ratenzahlungs-Gesamtbetrag (Netzbetreiber) in
derselben Rechnung. Konkret aus `data/state/geraete_db.json` (03.09.2026):

| Gerät | freenet (bar) | o2 (24 Raten gesamt) | Vodafone (Listenpreis) |
|---|---|---|---|
| iPhone 17 256 GB | 949,00 | **1027,00** | 949,90 |
| iPhone 17 Pro Max 256 GB | 1449,00 | **1459,00** | 1349,90 |
| iPhone 15 128 GB | – | **721,00** | 709,90 |

Die vier Kacheln „Kritisch / Mittel / Gering / Bestpreis" und die Alarmtabelle
rechnen auf dieser Basis.

### 1.5 Sind die Links korrekt extrahiert?

| Anbieter | Linkziel | Bewertung |
|---|---|---|
| freenet | `offers.url` aus dem ld+json, SKU-genau (`?ds=P-…`) | **korrekt und belegend** (Live geprüft) |
| o2 | `detailWwwAbsoluteCall.constantPayload.link.uri`, mit `ohne-tarif=ja&…&vertragsart=ratenzahlung` | **korrekt und belegend** — die Zahl steht auf der Zielseite |
| ALDI TALK | Produktseite mit angehängten Suchparametern (`FF_QUERY=…&FF_POS=14&…`) | funktioniert, aber die Adresse trägt fremden Sitzungsballast |
| **Vodafone** | `hubpage.href` → `www.vodafone.de/privat/handys/<modell>.html` (`vodafone.py:145-147`) | **nicht belegend** — Modellseite statt SKU-Seite, Bündelseite statt Preisseite, Zahl nicht auffindbar |

Vodafones Nutzlast bietet keinen besseren Link an: das `url`-Feld einer
`atomics`-Variante enthält (Live 03.09.2026) ausschließlich `galleryImage`. Der
`hubpage`-Link ist die einzige menschenlesbare Adresse, die Vodafone selbst nennt.
Das ist kein Extraktionsfehler, sondern eine **Belegbarkeitslücke der Quelle** —
und sie muss auf der Seite als solche stehen, statt als Beleg auszusehen.

Nebenbefund aus derselben Messung: die o2-Produktseite des iPhone 14 128 GB trägt
`availability: OutOfStock` und im Tracking-Objekt `"dimension62":
"CURRENTLY_NOT_AVAILABLE"`. In `geraete_db.json` steht dieselbe Listung als
`status: aktiv`, `verfuegbarkeit: unbekannt` — `o2.py:117` setzt
`"verfuegbarkeit": "unbekannt"` fest, weil der Katalog kein Verfügbarkeitsfeld
führt. Das ist konsistent mit der Projektdisziplin („nicht raten"), heißt aber:
**83 von 83 o2-Listungen tragen keine Verfügbarkeitsaussage**, obwohl die
Produktseite eine hätte.

---

## 2. Befund B — die ~700 €, die in der Quelle nicht auftauchen

**Die Fehlerquelle ist identifiziert und reproduzierbar.**

Die Zeile, die Antonio gesehen hat, steht so in `site/geraete.html`:

```html
<a class="gr-a-quelle" href="https://www.vodafone.de/privat/handys/iphone-15.html" …>Vodafone ↗</a>
<td class="num">709,90 €</td>
```

Kette, jede Stufe am 03.09.2026 nachgemessen:

1. **Woher die Zahl kommt.**
   `GET https://api.vodafone.de/glados/v2/hardware/v2/virtualItem/51?businessTransaction=newContract&salesChannel=Online.Consumer`
   mit dem öffentlichen Browser-Schlüssel aus `geraete_quellen.yaml:320`
   → HTTP 200, 38 089 Bytes.
   `data.atomics[0].prices.hardware.priceByType.rate.onetime.withoutDiscounts.gross = 709.9`.
   Die Zahl ist **echt** und stammt aus einer offiziellen Vodafone-Nutzlast.

2. **Wohin der Link zeigt.**
   `data.hubpage.href = "/privat/handys/iphone-15.html"`, absolut gemacht in
   `vodafone.py:145-147`.
   `GET https://www.vodafone.de/privat/handys/iphone-15.html` → HTTP 200,
   314 023 Bytes, `<title>iPhone 15 **mit Vertrag** | Vodafone</title>`.
   Vorkommen von `709` im ausgelieferten HTML: **0**.
   Vorkommen von `application/ld+json`: **0**. Preise entstehen dort erst im
   Browser (171 Treffer auf `simplicity`, Vodafones Frontend-Bündel).

3. **Warum die Zahl auch inhaltlich nicht die ist, die ein Kunde zahlt.**
   Im selben Datensatz steht der Geräteanteil des 12-Monats-Bündels als
   `total = 703,00 €` (= 1,00 € Anzahlung + 12 × 58,50 €), und die 709,90 €
   tragen dort das Etikett `uvp`. Wer auf vodafone.de ein iPhone 15 kauft, sieht
   je nach Weg 1,00 €, 58,50 €/Monat, 703,00 € oder 709,90 € — die Geräteseite
   zeigt eine dieser vier Zahlen ohne zu sagen, welche.

**Diagnose.** Drei Fehler, in dieser Reihenfolge nach Schwere:

* **B-1 (schwer, Vertrauensschaden):** Der Quelllink belegt die Zahl nicht.
  Das verletzt den ausdrücklichen Anspruch des Portals — `geraete_model.py:831-833`
  wirft sogar eine Ausnahme für Listungen ohne `quelle_url`, mit der Begründung
  „ein Preis ohne Beleg ist auf diesem Portal keine Zahl". Eine *nicht belegende*
  Adresse rutscht durch dieselbe Prüfung, weil nur auf Vorhandensein geprüft wird.
* **B-2 (schwer, Sachfehler):** Das Etikett „ohne Vertrag" ist für Vodafone und
  o2 nicht präzise. Bei o2 ist es ein Ratenzahlungs-Gesamtbetrag, bei Vodafone ein
  `withoutDiscounts`-Listenwert aus einem Neuvertragskontext.
* **B-3 (mittel, Auflösung):** Vodafone-Links stehen auf Modellebene. Die drei
  Varianten „Galaxy Z Fold8 Ultra 512 GB Cream / Graphite / Violet Shadow"
  (2399,90 €) teilen sich eine einzige Adresse.

**Was NICHT die Ursache ist** (geprüft und ausgeschlossen): kein Parserfehler in
`lies_preis` (`strukturdaten.py:112-148`), kein Währungsfehler, kein
Sammelknotenproblem (`__init__.py:492-507`), kein Lockpreis-Durchschlupf
(`strukturdaten.py:151-152`). Der Extraktor arbeitet exakt so, wie er
dokumentiert ist. Der Fehler sitzt eine Ebene höher: in der **Bedeutung**, die
Seite und Modell der gelesenen Zahl zuschreiben.

---

## 3. Befund C — warum die Telekom fehlt

### 3.1 Faktenlage im Repo

`config/geraete_quellen.yaml:273-300`:

* `methode: json_endpunkt` (Z. 277) — **das ist kein Adaptername.**
  Registriert sind fünf Methoden (`collect/geraete/__init__.py:236-266`):
  `ldjson`, `shopify`, `vodafone_api`, `o2_katalog`, `congstar_next`.
  `geraete_config.py:30-35` nennt `json_endpunkt` ausdrücklich „eine Diagnose,
  kein Adaptername".
* `aktiv: false` (Z. 278) → `crawlbar == False` (`geraete_config.py:120`) →
  `sammle_anbieter` bricht mit Status `uebersprungen` ab
  (`collect/geraete/__init__.py:324-327`).

Beide Sperren greifen unabhängig voneinander. Eine `telekom.py` hat es nie
gegeben; `tests/test_geraete_collect.py:407-415` schreibt Telekom sogar als
Musterfall für `status == "nicht_umgesetzt"` fest.

Der dokumentierte Grund (`geraete_quellen.yaml:279-294`, wörtlich auch auf
`site/geraete-quellen.html`): am 11.08.2026 an
`/shop/geraet/apple/apple-iphone-17-pro-max/silber-256-gb` gemessen — kein
ld+json, kein Microdata, im `__INITIAL_STATE__` nur `deltaPrice` (Aufschlag ohne
Grundbetrag) und `installmentConfiguratorItems.upfrontPrice` (Zuzahlung im
Bündel). Dazu, aus dem Promo-Zweig, `CLAUDE.md:683-687`: „telekom.de beantwortet
jeden httpx-Abruf mit HTTP 202 und einer 2-KB-Challenge […] curl bekommt dieselbe
URL als 200 mit vollem Inhalt; es ist TLS-/Client-Erkennung." An vier weiteren
Stellen (`CLAUDE.md:1914`, `outputs/geraete-html-neubau-2026-08-30.md:66`,
`collect/geraete/congstar.py:7`, `geraete_quellen.yaml:399`) ist daraus
„AWS-WAF, wird nicht versucht" geworden — eine Verkürzung, die den Befund
falsch zuspitzt (§ 3.3).

### 3.2 Live nachgemessen am 03.09.2026 — der Befund gilt nur für die Produktseite

**robots.txt:** `https://www.telekom.de/robots.txt` → HTTP 301 →
`https://www.telekom.de/content/robots` → HTTP 200, 151 Bytes, vollständig:

```
User-agent: *
Disallow: /is-bin/intershop.enfinity/BOS/
Disallow: /is-bin/intershop.static/

Sitemap: https://www.telekom.de/content/robots/sitemap
```

**Keine Sperre für Geräteseiten, kein Crawl-delay, keine Visit-time.** Die
Geräteseiten stehen in Telekoms eigener Sitemap (301 Adressen unter
`/shop/geraet/`, 48 unter `/shop/geraete…`, darunter ausdrücklich
`…/smartphones/ohne-vertrag`).

**Kategorieseite (eigene Messung, Absender `TelcoRadar/1.0`):**
`GET https://www.telekom.de/shop/geraete/smartphones/ohne-vertrag`
→ **HTTP 200 über HTTP/2**, kein 403, keine Challenge. `__INITIAL_STATE__`
1 ×, `hardwareOnlySale` 10 ×, `application/ld+json` 1 × (BreadcrumbList /
Organization / FAQPage — **kein `Product`, kein `Offer`**).

Im Zustandsobjekt stehen für alle 10 Geräte absolute Beträge:

| Gerät | Anzahlung | Rate | n | Gesamt | Probe |
|---|---|---|---|---|---|
| Samsung Galaxy Z Fold8 Ultra | 399 | 50,00 | 36 | 2199,00 | ✔ |
| Samsung Galaxy Z Fold8 | 399 | 44,40 | 36 | 1997,40 | ✔ |
| Google Pixel 11 Pro XL | 199 | 33,30 | 36 | 1397,80 | ✔ |
| Apple iPhone 17 Pro Max | 199 | 31,90 | 36 | 1347,40 | ✔ |
| Samsung Galaxy Z Flip8 | 199 | 30,50 | 36 | 1297,00 | ✔ |
| Apple iPhone 17 Pro / Google Pixel 11 Pro | 99 | 30,50 | 36 | 1197,00 | ✔ |
| Google Pixel 11 | 99 | 25,00 | 36 | 999,00 | ✔ |
| Apple iPhone 17 | 99 | 23,60 | 36 | 948,60 | ✔ |
| Xiaomi 17T Pro | 1 | 24,30 | 36 | 875,80 | ✔ |

`upfrontPrice + 36 × recurringPrice == totalPrice` bei 10 von 10.

Das ist **dieselbe Konstruktion wie bei o2** — und damit auch dieselbe
Einschränkung: es ist ein **36-Monats-Ratenzahlungs-Gesamtbetrag**, kein
Barpreis. Ob Telekom denselben Artikel als Sofortkauf anbietet, ist **ungeprüft**
(die Kauflabels rendert React nach; im ausgelieferten Fließtext stand als
einziger Eurobetrag „9,99 €").

**Produktseite:** Der Befund vom 11.08.2026 bestätigt sich —
`/shop/geraet/apple/apple-iphone-17-pro-max/silber-256-gb?hardwareOnlySale=true`
→ HTTP 200, kein ld+json, `deltaPrice` vorhanden,
`installmentConfiguratorItems` leer.

### 3.3 Bewertung

| Hypothese | Urteil |
|---|---|
| (a) robots.txt verbietet es | **Nein**, ausgeschlossen (Volltext oben) |
| (b) Bot-Schutz / 403 | **Teilweise — die Sperre greift hier nicht.** **AWS WAF ist vorhanden:** das ausgelieferte HTML führt `AWS_WAF_API_KEY` und `AWS_WAF_INTEGRATION_URL` auf ein `…captcha-sdk.awswaf.com`-Captcha (Live 03.09.2026). Es **blockiert die Kategorieseite derzeit nicht**: zwei Abrufe (Chrome-UA und `TelcoRadar/1.0`) über HTTP/2 mit HTTP 200, kein 403, keine Challenge. Header zeigen CloudFront + Envoy + Dynatrace; `Varnish` ist in den Antwortheadern **nicht** auffindbar. Real bleibt zusätzlich die httpx-spezifische 202-Challenge (`CLAUDE.md:683-687`) — sie trifft genau den Client, den der Sammler benutzt. **Ob sie heute noch auftritt, ist ungeprüft** (gemessen wurde mit curl). |
| (c) JS-Rendering ohne strukturierte Daten | **Halb richtig.** Kein `Product`-Schema — bestätigt. Aber „kein Gerätepreis ohne Vertrag zu lesen" gilt nur für die **Produktseite**; die Kategorieseite liefert ihn serverseitig. |
| (d) nie implementiert, bewusst zurückgestellt | **Ja, das ist der tragende Grund.** Kein Adapter, `aktiv: false`, Test zementiert den Zustand. `CLAUDE.md:1993`: „W4 (Telekom, Ceconomy, expert, 1&1) ist nicht angefasst". |

**Was blockiert, in einem Satz:** Nicht der Zugang — die AWS WAF ist zwar
deployed, blockiert die Kategorieseite aber nicht —, sondern der auf der
**Produktseite** fehlende serverseitige Gerätepreis und ein Angebot, das den
Gerätepreis ausschließlich als Ratenzahlung ausweist; verstärkt durch ein
Client-Symptom, das im Repo zu einer Zugangssperre verhärtet ist, und eine
Priorisierung, die Telekom hinter drei andere Wellen gestellt hat.

**Nebenbefund:** Der Telekom-Wert für das iPhone 17 Pro Max 256 GB (1347,40 €)
wäre in der heutigen Vergleichslogik sofort „günstigster Wettbewerber" —
günstiger als Vodafones 1349,90 €. Er ist aber ein 36-Monats-Betrag gegen einen
Listenpreis. **Telekom anzubinden, ohne vorher die Preisform einzuführen, würde
den Vergleich nicht verbessern, sondern kaputtmachen.** Das ist der Grund für die
Phasenreihenfolge in § 8.

---

## 4. Befund D — Inventur: was abgedeckt ist und was fehlt

### 4.1 Anbieter

`config/geraete_quellen.yaml`: **23 Anbieter konfiguriert, 7 aktiv, 16
deaktiviert** (jeder Deaktivierte mit `grund` — kein stiller Ausfall).

| typ | gesamt | aktiv | liefert Daten |
|---|---|---|---|
| handel | 8 | 3 | 3 |
| netzbetreiber | 4 | 2 | 2 |
| discount | 11 | 2 | 1 |

**Daten liefern 6 Anbieter** (`data/state/geraete_db.json`, 391 Listungen,
274 SKUs, 59 Geräte):

| Anbieter | Listungen | Geräte | min € | median € | max € | aktiv/ausgelistet |
|---|---|---|---|---|---|---|
| Vodafone *(eigen)* | 151 | 41 | 219,90 | 1199,90 | 2399,90 | 149 / 2 |
| mobilcom-debitel (freenet) | 149 | 21 | 179,00 | 999,90 | 2449,00 | 149 / 0 |
| o2 | 83 | 55 | 253,00 | 721,00 | 2197,00 | 67 / 16 |
| ALDI TALK | 4 | 3 | 129,00 | 519,00 | 539,00 | 4 / 0 |
| ElectronicPartner | 2 | 2 | 299,00 | 344,00 | 389,00 | 2 / 0 |
| Medimax | 2 | 2 | 349,00 | 549,00 | 749,00 | 2 / 0 |

**77 % des Bestands (300 von 391) stammen aus zwei Quellen**, eine davon die
eigene Referenz. Medimax und ElectronicPartner gehören demselben Betreiber
(`geraete_quellen.yaml:208`, Kommentar auch Z. 53) — sie sind **kein**
unabhängiger zweiter Marktpunkt.
Ohne Vodafone bleiben 240 Wettbewerbslistungen aus drei unabhängigen Quellen.

**Der gravierendste Deckungsfehler:** `congstar` ist der einzige *aktive*
Anbieter **ohne eine einzige Listung** und ohne Lauf-Protokolleintrag —
angebunden am 31.08.2026, seither kein Fund. Damit ist das **Telekom-Netz im
Gerätepreisradar vollständig unbelegt** (Telekom selbst inaktiv;
klarmobil / Edeka smart / Norma Connect / fraenk deaktiviert).

**Gar nicht konfiguriert:** Cyberport, notebooksbilliger.de, Otto, Gravis,
Conrad, Kaufland, Tchibo mobil, yourfone, ja! mobil — sowie Lidl Connect,
Penny Mobil, PremiumSIM und simplytel, die `config/promo_sources.yaml` bereits
als Marken führt. **Die beiden Markenlisten des Projekts sind nicht abgeglichen.**

### 4.2 Betrieb — drei von sechs Anbietern werden nie fertig

Lauf-Protokoll aus dem `anbieter`-Block von `geraete_db.json`
(geschrieben von `analyze/geraete_store.py:342`, aufgerufen in
`geraete_pipeline.py:134`):

| Anbieter | vollständige Läufe | letzter Fund | Funde gesamt |
|---|---|---|---|
| ALDI TALK | 8 | 2026-09-03 | 25 |
| Vodafone | 6 | 2026-09-03 | 896 |
| o2 | 6 | 2026-09-03 | 406 |
| **mobilcom-debitel** | **0** | 2026-09-03 | 738 |
| **ElectronicPartner** | **0** | 2026-09-03 | 40 |
| **Medimax** | **0** | 2026-09-03 | 40 |
| congstar | *kein Eintrag* | – | – |

`geraete_pipeline.py:119-125` lässt `mark_stale` nur für Anbieter mit
`bilanz.vollstaendig` laufen. Für drei der sechs liefernden Anbieter läuft die
Auslistungslogik also **nie**. Das ist die richtige Sicherung (nicht Gelesenes
altert nicht) mit einer unerwünschten Folge: **ihr Bestand kann beliebig
veralten, ohne dass es auf der Seite sichtbar wird.** Bei mobilcom-debitel sind
das 149 von 391 Listungen.

Ungeklärte Diskrepanz: Medimax und ElectronicPartner melden je 20 Funde pro Lauf,
im Bestand stehen je 2 Listungen. Die einzige im Code vorgesehene Erklärung ist
`GeraeteDB.kollisionen` (`analyze/geraete_store.py:194-203`); `kollisionen` wird
nicht persistiert, der Befund ist aus den Dateien **nicht abschließend beweisbar**.

### 4.3 Katalog und Datenqualität

`config/geraete_katalog.yaml`: **83 Modelle** (Samsung 23, Apple 17, Xiaomi 14,
Google 12, Nothing 5, Motorola 3, HONOR 3, OnePlus 3, realme 2, Fairphone 1),
212 Speicherstufen.

| Lücke | Zahl |
|---|---|
| Modelle ohne `marktstart` | **54 von 83 (65 %)** → keine Nachfolger-Analyse |
| Modelle ohne `vorgaenger` | 49 von 83 (59 %) |
| Modelle ohne jede Listung | 24 von 83 (29 %) |
| Hersteller mit **null** Listungen | Motorola, HONOR, OnePlus, realme |
| Listungen ohne normalisierte Farbe | **200 von 391 (51 %)** bei 115 Rohschreibweisen gegen 19 Farbschlüssel in `config/farben.yaml` |
| EAN vorhanden | 8 von 391 |

**Dringendste Kataloglücke: die iPhone-18-Reihe.** Sie kommt im eigenen
Berichtsarchiv (`data/reports/*.json`, 25 Berichte) 17-mal vor, mit Marktstart
September 2026 — steht aber nicht im Katalog. Ohne Katalogeintrag erkennt
`erkenne_geraet()` sie nicht, und sie erscheint nicht in der Datenbank. Ebenfalls
fehlend: Xiaomi-16er-Reihe komplett, `Xiaomi 17 Pro`, POCO als ganze Marke,
`Pixel 9a`, `Pixel 9 Pro Fold`, OnePlus 16, Honor Magic9.

**Nicht ermittelbar:** die Liste der „unbekannten Titel" (Produkttitel ohne
Katalogtreffer). Sie wird in `collect/geraete/__init__.py:120,546` gesammelt und
in `geraete_pipeline.py:189-196` **nur ins Log geschrieben** — es gibt keine
Logdatei im Repo und keine Persistenz in `data/`. Die Arbeitsliste, aus der die
Katalogpflege leben soll, existiert praktisch nicht.

### 4.4 Zeitreihe

`data/state/geraete_preise.jsonl`: 405 Zeilen, 2026-08-10 bis 2026-09-03,
**7 Messtermine** (08-10, 08-29, 08-30, 08-31, 09-01, 09-02, 09-03), davon nur
zwei zwischen dem 10.08. und dem 29.08.
**Vier Listungen** haben mehr als einen Preispunkt; **vier echte Preisänderungen**
sind belegt — drei bei o2 (343→379, 223→271, 541→505) und eine bei ALDI TALK
(155,00→159,00 zum 01.09.). Die Seite sagt das selbst („Aussagen zu Preisverfall und
Verweildauer ab etwa 12 Wochen") — die Preisverlauf-Sektion ist heute eine
Absichtserklärung, keine Auswertung.

Ein Datenfehler in der Reihe: `aldi-talk--samsung-galaxy-a17-128gb-schwarz`
bekommt an sechs Tagen in Folge je zwei Preise am selben Tag (129,00 und
155,00/159,00). Der Titel verrät den Grund: „SAMSUNG Galaxy A17 LTE, 128 GB,
Black … **+ Beclad Starter Kit**" — zwei Quellprodukte kollidieren auf einer
`listung_id`. Der o2-Adapter verwirft Zubehörbündel bereits (`o2.py:95`), der
generische `ldjson`-Adapter nicht.

---

## 5. Wie der Markt wirklich rechnet (Recherche)

Recherchestand **03.09.2026**. Primärquellen sind Anbieterdomains. Was nicht
primär belegt ist, steht in § 5.5 **oder** ist an Ort und Stelle als *ungeprüft*
bzw. *teilweise belegt* gekennzeichnet. Beides ist gleichermaßen gesperrt: keine
Grundlage für eine Empfehlung, eine Konfiguration oder einen Testsollwert
(§ 11).

### 5.1 Die vier Netzbetreiber plus congstar

| Anbieter | Gerätepreis-Darstellung | Ratenlaufzeiten | Anschlusspreis | Primärquelle (Abruf 03.09.2026) |
|---|---|---|---|---|
| **Telekom** | getrennter Ratenkauf: „Anzahlung plus monatliche Raten ergeben den Gerätepreis", 0 % Zinsen, „getrennt vom Tarif" | 6 / 12 / 24 / **36** | *ungeprüft* — live nur „Bereitstellungspreis **39,95 € bzw. 69,95 €**" im Kleingedruckten eines MagentaEINS-Kombiangebots, nicht als generischer Mobilfunk-Anschlusspreis (§ 5.5 Nr. 13) | `telekom.de/shop/geraete/ratenkauf`; `telekom.de/optionsuebersicht/mobilfunk/magentaeins-vorteil` |
| **Vodafone** | voller Kaufpreis ausgewiesen („Einmal 999,99 €"), Ratenzahlungsvereinbarung mit 0 % Zinsen, Rabatt als Rechnungsgutschrift | 12 / 24 / **36** | 39,99 €, aktuell **0 €** für Neukunden | `vodafone.de/privat/handys-tablets-tarife/smartphone-ratenzahlung.html`; `…/alle-tarife-mit-vertrag.html` |
| **o2** | „o2 my Handy" als **eigener Ratenkaufvertrag**: „Die Ratenzahlung für das Gerät läuft unabhängig vom gewählten Tarif", 0 % Finanzierung, Anzahlung ab 1,00 € *(Minimum der 95 Katalogeinträge; die Formulierung „ab 1 Euro" steht so nicht auf der Seite)* | **24 / 36** — „mit Ratenzahlung über wahlweise 24 oder 36 Monate Laufzeit" | 39,99 €; „bei einzelnen Tarifen 0 €" *ungeprüft* (§ 5.5 Nr. 14) | `o2online.de/e-shop/apple/apple-iphone-14-128gb-mitternacht-details`; `o2online.de/service/myhandy/`; `o2online.de/tarife/mobilfunktarife/` |
| **1&1** | **kein separater Gerätepreis**: „Gerätepreis wird in der monatlichen Grundgebühr verrechnet – keine hohe Einmalzahlung für das Gerät" | im Tarif enthalten; Laufzeit 24 oder **24 + 12** | *ungeprüft* | `mobile.1und1.de/handyvertrag`; `mobile.1und1.de/mobilfunkvertrag` |
| **congstar** | beworbener Monatspreis „ab 45,00 € mtl." („1. bis 36. Monat: 45,00 €"; den Begriff „Mischpreis" verwendet congstar nicht), inkl. antizipiertem Restwert | **36**; im **Rückgabedeal** zusätzlich eine 37. Schlussrate, ohne ihn ist Monat 37 eine fortlaufende Monatsrate (24,00 €) | **15 €** (24-Monats-Tarif) bzw. **35 €** (Flex) — „Einmaliger Bereitstellungspreis" | `congstar.de/handys/`; `congstar.de/geraete/rueckgabedeal/` |

Zwei Strukturen verdienen besondere Aufmerksamkeit:

* **Die Geräteratenlaufzeit übersteigt bei allen drei Netzbetreibern die
  Tarifbindung** — Telekom, Vodafone und o2 bieten je 36 Monate gegen 24 Monate
  Bindung, also bis zu **12 Monate Überhang**. Eine reine 24-Monats-Rechnung
  zeigt dort nur zwei Drittel der Gerätekosten. Keiner der drei sticht dabei
  heraus; die frühere Lesart „o2 entkoppelt am extremsten" beruhte auf einer
  48-Monats-Angabe, die es für Smartphones nicht gibt (die einzige
  `ratenzahlung=48` im o2-HTML ist ein Navigationslink auf MacBooks).
* **congstars Rückgabedeal** ist eine Ballonfinanzierung und damit der
  Extremfall im Markt: **Referenzbeispiel der Erklärseite** 39 € Anzahlung,
  36 Raten, **37. Schlussrate 288 €** (iPhone 17 Pro), die bei Rückgabe im
  Zustand „Gebraucht" verrechnet wird, bei „Gebrochen" zu 50 % und bei „Defekt"
  voll fällig bleibt. Die **aktuelle Produktseite desselben Geräts** zeigt eine
  abweichende Promo-Konfiguration (1,00 € Anzahlung, 21,00 €/Monat, 234,00 €
  Rückgabewert) — Erklärbeispiel und Live-Angebot dürfen im Code nicht
  vermischt werden. Der beworbene Monatspreis enthält ein Restwertrisiko, das
  vom Gerätezustand abhängt.

Zur Einordnung der eigenen Zahlen des Projekts: **alle vier Netzbetreiber
bewerben 0 % Sollzins.** Ein Ratenzahlungs-Gesamtbetrag ist damit **nicht** um
Zinsen verfälscht — er ist trotzdem eine andere Größe als ein Barpreis, weil er
den Kunden über 24–36 Monate bindet — bei congstars Rückgabedeal bis in den
37. Monat — und weil er, wie o2 zeigt (949,00 € bar bei
freenet gegen 1027,00 € bei o2 für dasselbe iPhone 17 256 GB), nicht mit dem
Marktbarpreis übereinstimmen muss.

### 5.2 Rabattmechaniken, die in keiner Preisspalte stehen

* **Vodafone:** 200 € Hardware-Bonus für Tarife M–XL, ausgezahlt als monatliche
  Gutschrift von **8,34 € über 24 Monate** (Primär, `alle-tarife-mit-vertrag.html`).
  *Teilweise belegt:* 8,34 × 24 = **200,16 €**, nicht 200,00 € — für eine
  TCO-Rechnung muss feststehen, welcher der beiden Werte gilt.
  Vodafone Kombi (ehem. GigaKombi) staffelt 5 / 10 € je Kombination
  (`vodafone.de/privat/vodafonekombi.html`); eine **15-€-Stufe war am 03.09.2026
  nicht auffindbar** und gilt als *teilweise belegt*. Achtung: der neue Tarif
  „Vodafone Mobil" bekommt in der Festnetzkombi **5 €**, das alte GigaMobil
  **10 €** — der Portfoliowechsel zum 16.07.2026 hat den Kombivorteil für
  Neukunden halbiert.
* **o2:** Kombirabatte bis **25 €**/Monat je Zweittarif (25 € und 10 € belegt;
  eine **5-€-Untergrenze war nicht auffindbar** — *teilweise belegt*). Internet
  zuhause bringt **10 € monatlich Rabatt auf die Grundgebühr**
  (`o2online.de/kombiangebote/`, „Dauerhaft bis zu 25 € monatlichen Rabatt").
  **Eine Monatsgrenze („ab dem 2. Vertragsjahr") nennt die Seite nicht** — die
  frühere Angabe einer Rabattstufe ab Monat 13 ist unbelegt und darf nicht als
  Testsollwert dienen.
* **Telekom:** MagentaEINS ist **kein Euro-Rabatt**, sondern Sachleistung
  (Festnetz-Flat in alle Mobilfunknetze, unbegrenztes Datenvolumen).
  **Für ein TCO-Modell nicht als Geldbetrag abbildbar** — das ist eine
  Modellierungsentscheidung, keine Datenlücke.
* **1&1:** Rabattstufen im SIM-only-Tarif sind inhaltlich plausibel, aber die
  im Doc bisher zitierte Staffelung („3 Monate je 9,99 €", danach 14,99 €) ist
  an der angegebenen Fundstelle (`mobile.1und1.de/handyvertrag`) **nicht
  auffindbar** (Abruf 03.09.2026). Fundstellen-Verwechslung, keine erfundene
  Zahl — bis eine korrekte Primärquelle vorliegt: *ungeprüft* (§ 5.5 Nr. 15).

### 5.3 Der Rechtsrahmen ist die stabilste Datenquelle

* **§ 54 Abs. 3 TKG** verpflichtet jeden Anbieter, vor Vertragsschluss kostenlos
  eine **Vertragszusammenfassung** nach dem Muster der
  **Durchführungsverordnung (EU) 2019/2243** bereitzustellen. Nach **Abs. 4**
  werden diese Angaben **Vertragsinhalt**.
* Das Muster (Anhang, Abschnitt „Preis") verlangt ausdrücklich: den
  wiederkehrenden Preis inkl. Steuern je Abrechnungszeitraum, **„etwaige
  zusätzliche Festpreise, z. B. für die Aktivierung des Dienstes"**,
  **„gegebenenfalls der Gerätepreis"** und **„etwaige befristete Preisabschläge",
  die „eindeutig als solche zu kennzeichnen" sind.** Bei Bündelung mit Endgeräten
  darf das Dokument drei DIN-A4-Seiten umfassen.
  (`eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:32019R2243`, Abruf 03.09.2026)
* **PAngV 2022 § 3**: Gesamtpreise sind anzugeben, „Preisklarheit und
  Preiswahrheit"; wird ein Preis aufgegliedert, ist der Gesamtpreis hervorzuheben.
  **§§ 16–19** regeln den effektiven Jahreszins bei Finanzierungshilfen — das ist
  die Rechtsgrundlage der „0 %"-Angaben aller vier Netzbetreiber.
  (`gesetze-im-internet.de/pangv_2022/`, Abruf 03.09.2026)
* Das **Produktinformationsblatt** (TK-Transparenzverordnung) verlangt u. a.
  Vertragslaufzeit und monatliche Kosten; die BNetzA stellt Muster bereit.
  (`bundesnetzagentur.de/DE/Fachthemen/Telekommunikation/Unternehmenspflichten/Transparenzmassnahmen/`, Abruf 03.09.2026)

**Das ist die gute Nachricht für dieses Repo: der Tarifzweig liest genau diese
Dokumente bereits.** `collect/tarif_crawler.py` + `collect/tarif_pdf.py` ziehen
PIB-PDFs, `tarif_model.py:79-117` hat schon `preisphasen`, `anschlusspreis`,
`anschlusspreis_nach_erstattung`, `geraetepreisstaffel` und `laufzeit_monate`,
und `report/effektivpreis.py:139-184` rechnet daraus einen 24-Monats-Effektivpreis
**inklusive eines `geraetezuzahlung`-Parameters, den heute niemand füllt.**
`config/tarif_quellen.yaml:27-44` führt bereits
`https://www.telekom.de/produktinformationsblatt` mit 1177 verlinkten Dokumenten.

Der Bestand ist allerdings dünn: `data/state/tarife.jsonl` enthält **3 Tarife von
1 Anbieter** (o2), und `site/tarife.html` sagt das selbst: „Erfasst: o2.
Konfiguriert, aber ohne Daten: Telekom."

**Die zentrale offene Machbarkeitsfrage** der Recherche: Die
Vertragszusammenfassung nach DVO 2019/2243 wird typischerweise erst in der
Bestellstrecke ausgeliefert. Ein Beispielabruf
(`telekom.de/hilfe/downloads/vertragszusammenfassung-fut-hybrid-g.pdf`) ergab
HTTP 404. Ob es einen statisch verlinkten Katalog dieser Dokumente gibt, ist
**ungeprüft** (§ 5.5 Nr. 16). Das PIB ist dagegen belegt erreichbar.

### 5.4 Wie andere den Effektivpreis rechnen

* **CHECK24** (`handytarife.check24.de/vergleich`, Abruf 03.09.2026, wörtlich):
  „Um Tarife besser vergleichen zu können, berücksichtigen wir **unabhängig von
  der Vertragslaufzeit alle in den ersten 24 Monaten fest anfallenden Kosten**
  sowie die **bestenfalls realisierbaren Vergünstigungen** und berechnen daraus
  den durchschnittlichen Monatspreis." Mit dem eigenen Hinweis, es handele sich
  „nicht um die tatsächlich zu zahlende monatliche Grundgebühr".
  Zwei Schwächen, die dieses Projekt **nicht** übernehmen sollte:
  Best-Case-Bias bei Cashback, und die 24-Monats-Kappung ignoriert Geräteraten in
  Monat 25–36 (Telekom, Vodafone, o2) und die 37. Schlussrate im
  congstar-Rückgabedeal.
* **Differenzmethode** (teltarif, Fachpresse): effektiver Gerätepreis =
  Gesamtkosten Bündel über 24 Monate minus Gesamtkosten eines vergleichbaren
  SIM-only-Tarifs. Methodisch überlegen, weil sie die richtige Frage beantwortet.
  **Für 1&1 ist sie nicht optional, sondern der einzige Weg**, weil dort kein
  Gerätepreis ausgewiesen wird.

### 5.5 Ausdrücklich ungeprüft

Nicht mit einer Primärquelle belegt und deshalb **keine Grundlage für Code oder
Seiteninhalte**:

1. Anschlusspreis **1&1** (19,90 € / 39,90 €) — nicht primär belegt. *Die
   frühere Begründung „`1und1.de/handy/` antwortet HTTP 403" ist widerlegt: die
   Seite liefert HTTP 200, mit und ohne Chrome-UA (03.09.2026). Der Wert bleibt
   ungeprüft, die Sperre existiert nicht.*
2. Telekom-Bundle-Beispielpreise (iPhone 17 Pro + MagentaMobil S: 439,95 € +
   39,95 €/Monat) — nur Sekundärquelle.
3. Telekom „Alt gegen Neu" 100 €; Cashback-Staffelung und -Frist (die Existenz
   „bis zu 240 € Cashback" ist primär belegt, die Staffelung nicht).
4. o2 „Pay-Stop-Garantie"; die konkrete Plus-Bundle-Rabattzuordnung.
5. **Alle Servicepauschalen aller fünf Anbieter** — Telekoms Preislisten-PDF
   antwortet 404, Vodafones ist ein Bild-PDF ohne Textlayer.
6. **Versandkosten** — bei keinem Anbieter primär belegt.
7. **Wechslerbonus / Portierungsprämien** — bei keinem Anbieter belegt.
8. **Restschuldregelung bei vorzeitiger Kündigung** bei laufender Geräterate —
   für keinen Anbieter belegt; bei 36-Monats-Raten (Telekom, Vodafone, o2) und
   bei congstars Schlussrate eine erhebliche Lücke.
9. Vodafone-Preiswiderspruch: dieselbe Seite lieferte „Mobil XS 39,99 €" /
   „Mobil S 49,99 € ab dem 13. Monat" **und** „XS ab 22,45 € / S ab 29,95 €".
   Vermutlich parallele Aktionsvarianten; **die Rabattstufen-Grenzen bei
   Vodafone sind ungeklärt.**
10. Ob **Telekom** einen Sofortkauf-Barpreis führt (siehe § 3.2).
11. Ob die httpx-202-Challenge gegen telekom.de heute noch auftritt (gemessen
    wurde mit curl).
12. Die Paginierung der Telekom-Kategorieseite (`"currentPage": 1`).
13. Ein **generischer Mobilfunk-Anschlusspreis der Telekom** (bisher als
    39,95 € geführt). Live auffindbar ist nur „Bereitstellungspreis 39,95 €
    bzw. 69,95 €" im Kleingedruckten eines MagentaEINS-Kombiangebots — anderer
    Begriff, zwei Werte, anderer Vertragstyp.
14. o2 „Anschlusspreis **bei einzelnen Tarifen 0 €**" — die 39,99 € sind belegt,
    die Ausnahme nicht.
15. Die 1&1-Rabattstufe „**3 Monate je 9,99 €**, danach 14,99 €" — an der
    zitierten Fundstelle nicht auffindbar (§ 5.2).
16. Ob es einen **statisch verlinkten Katalog der Vertragszusammenfassungen**
    nach DVO 2019/2243 gibt (§ 5.3); ebenso die Wortlautzitate aus dem
    DVO-Anhang selbst — eur-lex war dreimal nicht erreichbar.
17. Die **Tarif-Mindestlaufzeit bei congstar** (im Modell mit 24 Monaten
    angenommen, § 6.3).

**Teilweise belegt** — die Existenz steht, der genaue Wert nicht. Für Code und
Seiteninhalte gilt dieselbe Sperre wie für § 5.5:

* **T1** — Vodafone-Kombi: 5 € und 10 € sind belegt, eine **15-€-Stufe** war am
  03.09.2026 nicht auffindbar.
* **T2** — o2-Kombirabatte: 25 € und 10 € sind belegt, die **5-€-Untergrenze**
  nicht.
* **T3** — Vodafones 200-€-Hardware-Bonus: belegt ist die Auszahlung als
  **8,34 € × 24 = 200,16 €**. Ob 200,00 € oder 200,16 € der maßgebliche Betrag
  ist, ist offen.

**Volatilitätswarnung:** In drei Monaten hat Vodafone sein Portfolio umbenannt
(GigaMobil → Vodafone Mobil, 16.07.2026) und o2 auf „Plus Bundles" umgestellt
(10.06.2026). Fünf recherchierte Anbieter-URLs antworteten mit HTTP 404. Jede
Konfiguration, die auf Tarifnamen oder Marketing-URLs baut, hat eine Halbwertszeit
von Monaten.

---

## 6. Datenmodell-Empfehlung für TCO

### 6.1 Das eine fehlende Feld: die Preisform

Heute entscheidet `_preisfelder()` zwischen zwei Fällen und legt das Ergebnis in
zwei getrennten Feldern ab. Das reicht nicht mehr, weil `preis_ohne_vertrag`
inzwischen drei verschiedene Dinge trägt. Vorschlag:

```python
# geraete_model.py
PREISFORMEN = (
    "barkauf",        # Sofortkauf, Betrag sofort fällig   (freenet, Medimax, EP, ALDI)
    "raten_gesamt",   # Anzahlung + n Raten, Summe          (o2, Telekom)
    "listenpreis",    # UVP/Listenwert ohne Rabattstand     (Vodafone withoutDiscounts)
    "buendel",        # Zuzahlung + Tarif                   (heute unbenutzt)
)

@dataclass
class Preis:
    """EINE Preisangabe eines Anbieters, mit ihrer Form."""
    form: str                       # aus PREISFORMEN, Pflicht
    betrag: float                   # der Gesamtbetrag dieser Form
    anzahlung: Optional[float] = None
    monatsrate: Optional[float] = None
    raten_anzahl: Optional[int] = None
    zins_effektiv: Optional[float] = None    # 0.0 heisst belegt 0 %, None heisst unbekannt
    tarif_id: str = ""                       # Pflicht bei form == "buendel"
    beleg_url: str = ""                      # die Seite, auf der DIESE Zahl steht
    beleg_gefunden: Optional[bool] = None    # wurde der Betrag dort verifiziert?
```

Drei Zusicherungen, im Konstruktor durchgesetzt (dieselbe Bauform wie
`Listung.__post_init__`, `geraete_model.py:830-861`):

1. `form == "raten_gesamt"` verlangt `anzahlung`, `monatsrate` und
   `raten_anzahl`; und `anzahlung + raten_anzahl * monatsrate == betrag`
   (Toleranz 0,01 €). Diese Probe ging bei o2 in 92 von 93 Fällen auf — so der
   Konfigurationskommentar vom **28.08.2026** (`geraete_quellen.yaml:353-355`);
   live am 03.09.2026 geht sie bei **95 von 95** Katalogeinträgen auf. Bei
   Telekom stimmt sie in 10 von 10 Fällen (§ 3.2). Sie ist die billigste
   verfügbare Korrektheitskontrolle.
2. `form == "buendel"` verlangt `tarif_id` (die heutige Regel, nur mit
   Fremdschlüssel statt Freitext).
3. `form == "listenpreis"` erzeugt **keine** Vergleichszeile, sondern nur eine
   Anzeigezeile. Ein Listenpreis ist eine Auskunft über die Preisliste, keine
   über die Kasse.

**`beleg_gefunden`** ist die direkte Antwort auf Befund B: wenn der Adapter die
Zahl auf der verlinkten Menschenseite nicht wiederfinden kann, steht das im
Datensatz und auf der Seite — statt dass ein Link Nachprüfbarkeit vortäuscht.

### 6.2 Was für eine TCO-Rechnung gescrapet werden muss

Formel, die aus § 5 folgt:

```
TCO(horizont) =   Anzahlung Gerät
                + Σ(m=1..horizont) Geräterate(m)
                + Σ(m=1..horizont) Tarifgrundpreis(m)      ← Preisphasen, monatsgenau
                + Anschluss-/Bereitstellungspreis
                + Σ(m=1..horizont) gebuchte Optionen(m)
                − Σ Boni und Gutschriften (mit ihrer Fälligkeit)
                − Σ(m=1..horizont) Kombivorteil(m)
                + Restbetrag(m > horizont)                 ← offene Raten, Schlussrate
```

Je Komponente: Quelle, Feld, heutiger Stand.

| # | Komponente | Beste belegte Quelle | Feld / Pfad | Stand |
|---|---|---|---|---|
| 1 | Anzahlung Gerät | Vodafone-API / o2-Katalog / Telekom `__INITIAL_STATE__` | `hardware…rate.onetime.gross` · `price.oneTimePrice` · `price.upfrontPrice` | **alle drei live belegt** |
| 2 | Geräterate + Anzahl | dieselben | `hardware…rate.month.gross` · `price.monthlyPrice` · `price.installments[].recurringPrice` / `numberOfInstallments` | **live belegt** |
| 3 | Gerätegesamtbetrag | dieselben | `total` · `totalPrice` · `totalPrice` | **live belegt** |
| 4 | Listenpreis / UVP | Vodafone-API | `…priceByType.uvp.onetime…gross` | **live belegt**, heute fälschlich als `preis_ohne_vertrag` gespeichert |
| 5 | Tarifgrundpreis + Preisphasen | **PIB / Vertragszusammenfassung** | `tarif_model.Preisphase` | Modell da, 3 Tarife im Bestand |
| 6 | Anschlusspreis | PIB, ersatzweise Tarifseite | `tarif_model.anschlusspreis` | Modell da, Feld leer |
| 7 | Tarifbezug des Bündels | Vodafone `composition[].priceByComponent.tariff` | – | **Problem: die Nutzlast nennt keinen Tarifnamen**, nur Beträge (41,95 € ohne / 31,45 € mit Rabatt). Ein Fremdschlüssel muss erst hergestellt werden. |
| 8 | Ratenlaufzeit-Varianten | Vodafone `composition[].financingDuration` | 12 / 24 / 36, **alle drei mit `financingType: rate`**. Der zusätzliche `sub`-Eintrag trägt weder `financingDuration` noch `total` und ist **nicht** der gesuchte Knoten | **live belegt** |
| 9 | Boni / Gutschriften | Tarifseiten (Fließtext) | – | nicht strukturiert verfügbar |
| 10 | Kombivorteil | Tarifseiten (Tabelle) | – | Vodafone/o2 als Euro, Telekom als Sachleistung |
| 11 | Restbetrag jenseits des Horizonts | aus 1–3 gerechnet | – | rechenbar, sobald 1–3 stehen |
| 12 | Servicepauschalen, Versand, Wechslerbonus | – | – | **ungeprüft / nicht erreichbar** |

### 6.3 Zwei Kennzahlen statt einer — die wichtigste Modellentscheidung

`report/effektivpreis.py:17-22` setzt den Horizont fest auf 24 Monate, mit einer
guten Begründung („ein Vergleich braucht einen gemeinsamen Nenner"). Für Tarife
stimmt das. Für **Gerät plus Tarif** stimmt es nicht mehr, weil die
Geräteratenlaufzeit von der Tariflaufzeit entkoppelt ist:

| Anbieter | Tarifbindung | wählbare Geräteratenlaufzeit | Überhang |
|---|---|---|---|
| Telekom | 24 | 6 / 12 / 24 / 36 | bis 12 Monate |
| Vodafone | 24 | 12 / 24 / 36 | bis 12 Monate |
| **o2** | 24 | 24 / **36** | bis 12 Monate |
| congstar | 24 *(ungeprüft, § 5.5 Nr. 17)* | 36; im Rückgabedeal + 37. Schlussrate | **bis 13 Monate** |
| 1&1 | 24 bzw. 24+12 | im Tarif enthalten | – |

Eine auf 24 Monate gekappte Zahl belohnt systematisch, wer die Geräterate am
weitesten streckt. Der Überhang ist mit 12 Monaten (bzw. 13 bei congstar)
kleiner als früher angenommen — aber er kippt eine 24-Monats-Kappung genauso,
nur weniger dramatisch: bei 36 Raten liegt ein Drittel des Gerätepreises
außerhalb des Horizonts. **Empfehlung: immer zwei Zahlen führen —**

* `tco_bindung` — über die Tarif-Mindestlaufzeit (Vergleichbarkeit)
* `tco_voll` — bis das Gerät abbezahlt ist, inklusive offener Raten
  (Wahrhaftigkeit)

und die Differenz benennen. Das ist dieselbe Haltung wie in
`effektivpreis.py:24-31` („Warum immer DREI Werte"): eine Zahl, die eine
Nebenbedingung versteckt, ist eine Rangliste dieser Nebenbedingung.

### 6.4 Eine fehlende Komponente bleibt eine Lücke

`effektivpreis.py:33-39` hat die Regel bereits: „Wenn kein Anschlusspreis bekannt
ist, heißt das nicht ‚kostenlos'." Diese Regel wird **unverändert** auf die
TCO übertragen: `Tco.luecken: list[str]`, und eine TCO mit Lücken wird nie
stillschweigend gegen eine vollständige gestellt. Angesichts von § 5.5 (Versand,
Servicepauschalen, Wechslerbonus bei **keinem** Anbieter belegt) wird jede TCO
dieses Projekts auf absehbare Zeit Lücken tragen. Das ist kein Mangel des
Modells, sondern eine Eigenschaft des Marktes — sie muss sichtbar sein.

---

## 7. Vorbemerkung zum Phasenplan: das Review-Gate

Jede Phase endet mit demselben Gate. Ein Orchestrator kann es wörtlich
mitgeben.

**Gate-Schritt 1 — Tests.**

```bash
cd <repo> && PYTHONPATH=src python3 -m pytest -q
```

Referenzlauf vom 03.09.2026 auf dieser Maschine: **2188 passed, 33 skipped,
2 failed, 49 errors in 149 s.** Die 2 Fehlschläge (`tests/test_promo_seite.py`)
und die 49 Fehler (`tests/test_geraete_reiter_browser.py`) sind **ausschließlich
Umgebungsfolgen**: `PIL` (Pillow) ist nicht installiert, weshalb
`report/bilder.ist_leer` (`bilder.py:207-213`) in den Ausnahmezweig fällt und
jedes Bild „leer" nennt. Bei Playwright ist es **nur das Browser-Binary**: das
Modul importiert sauber
(`/opt/homebrew/lib/python3.14/site-packages/playwright/`), aber
`chromium.launch()` findet kein Executable unter
`…/ms-playwright/chromium_headless_shell-*`. Die Abhilfe heißt deshalb
`playwright install chromium`, nicht `pip install playwright`. Dass es
Laufzeit- und keine Importfehler sind, zeigt `pytest --collect-only -q`:
**2270 Tests, 0 Collection-Errors.** Wer eine Phase abnimmt, muss **dieselbe
Zahl bestandener Tests plus die neuen** sehen, und darf 2 failed / 49 errors nur
akzeptieren, solange Pillow und das Chromium-Binary fehlen. Auf einer
vollständigen Umgebung ist das Gate: **alles grün.**

**Gate-Schritt 2 — Clean-Code-Review nach `docs/clean-code-referenz.md`.**
Scope = die in der Phase geänderten Dateien. Kategorie für Kategorie, Eintrag für
Eintrag, je Eintrag PASS / FLAG / n. z. Ausgabeformat je FLAG:
`ID · Schweregrad · Datei:Zeile · was den Verstoß ausmacht · konkreter Fix`.
S1/S2 einzeln und vollständig, S3/S4 am Ende gebündelt (Audit-Regel 8).
Schweregrade nach P1: S1 Tests, S2 Duplizierung, S3 Ausdrucksstärke,
S4 Anzahl Klassen/Methoden; Korrektheits- und Sicherheitsverstöße zählen wie S1.
`[Prozess/Repo]`-Einträge nur bei direkter Evidenz im Scope (Regel 7).

**Gate-Schritt 3 — die repo-eigenen S1-Regeln** (Kopf der Clean-Code-Referenz,
CLAUDE.md §5/§6). In jeder Phase dieses Plans einzeln zu bestätigen:

* robots.txt wird eingehalten, **inklusive Crawl-delay und Visit-time** — nicht
  umgangen, nicht mit einem anderen User-Agent unterlaufen.
* **Keine hochgezählten IDs.** Abgerufen wird nur, was auf einer konfigurierten
  Einstiegsseite oder in einer vom Anbieter selbst ausgewiesenen Sitemap stand
  (§ 87b UrhG). `bilanz["nicht_verlinkt"]` muss leer bleiben.
* **`data/state/` und `data/reports/` werden nach lokalen Läufen nie committet.**
* Veröffentlichungsschwellen rechnet der Code, nie ein Test allein.
* Neues Verhalten braucht einen automatisierten Test; fehlt er, ist das S1.

**Gate-Schritt 4 — Seiten-Smoke-Test**, nur in Phasen, die die Website ändern:

```bash
python3 scripts/pruefe_portal.py
python3 scripts/schiess_screenshot.py
```

**Gate-Schritt 5 — Nachmessen.** Jede Phase nennt unten eigene Befehle. Ein
Befund gilt erst, wenn er auf dieser Maschine reproduziert wurde.

---

## 8. Phasenplan

Acht Phasen, sequenziell. Jede ist für sich abgeschlossen testbar und liefert
einen sichtbaren Zustand. **Die Reihenfolge ist nicht verhandelbar**: Phase 5
(Telekom) vor Phase 3 (Preisform) würde den Vergleich verschlechtern, nicht
verbessern (§ 3.3).

---

### Phase 1 — Wahrheit auf der bestehenden Seite

*Kein neuer Anbieter, kein neues Feld, keine neue Zahl. Nur: nichts behaupten,
was nicht stimmt.*

**Ziel.** Die Geräteseite hört auf, drei verschiedene Größen als „Preis ohne
Vertrag" auszugeben, und hört auf, mit einem Link Nachprüfbarkeit zu versprechen,
den er nicht einlöst.

**Aufgaben.**

1. `report/templates/geraete.html.j2:234` und `:314-315`: das pauschale Etikett
   „ohne Vertrag" ersetzen durch eine Formulierung, die den heutigen Zustand
   trifft — je Zeile eine Herkunftsangabe („Barpreis" / „Gesamtbetrag bei
   24 Monatsraten" / „Listenpreis"). Die Angabe kommt aus einer Zuordnung
   Anbieter → Preisform, die **in der Konfiguration** steht
   (`geraete_quellen.yaml`, neues Feld `preisform` je Anbieter), nicht aus einer
   Namensliste im Renderer (sonst verfehlt sie jeder neue Anbieter still —
   dieselbe Lehre wie `_belegstufe`, `collect/geraete/__init__.py:528-531`).
2. Vodafone-Quelllink: solange kein SKU-genauer Link existiert, den Anker als
   das kennzeichnen, was er ist — „Modellseite bei Vodafone (zeigt Bündelpreise)"
   — und die Zahl mit ihrer Herkunft versehen („Schnittstelle der
   Geräteübersicht"). Kein erfundener Deep-Link.
3. `geraete_quellen.yaml:279-294` (Telekom): den Grund auf den am 03.09.2026
   gemessenen Stand bringen — **präzisieren statt streichen**. Richtig ist:
   *AWS WAF ist vorhanden (`AWS_WAF_API_KEY`, `awswaf.com`-Captcha), blockiert
   die Kategorieseite derzeit aber nicht (HTTP 200, kein 403); Hauptblocker
   bleibt der fehlende serverseitige Gerätepreis auf der Produktseite und das
   Bundle-only-Modell.* „AWS-WAF" ersatzlos zu streichen würde eine wahre
   Aussage durch eine falsche ersetzen. Ebenso präzisieren:
   `collect/geraete/congstar.py:7`, `geraete_quellen.yaml:399` und
   `outputs/geraete-html-neubau-2026-08-30.md:66`.
   *Begründung:* `geraete_quellen.yaml:10-16` verspricht „jede Zeile hier ist
   gemessen, nicht geraten". Drei Zeilen halten das nicht.
4. `geraete_quellen.yaml:162,189` (Medimax, ElectronicPartner): der `grund`
   („findet seit dem 15.08.2026 nichts") ist überholt — beide liefern seit dem
   02.09.2026. Auf den Ist-Stand bringen.

**Abnahmekriterien.**

* Auf `site/geraete.html` steht neben **jeder** Preiszahl, welcher Preisform sie
  entstammt; kein Vorkommen von „ausschließlich Neugeräte ohne Vertrag" mehr,
  solange o2 und Vodafone in derselben Spalte stehen.
* Ein Test stellt sicher, dass ein Anbieter **ohne** `preisform` in der
  Konfiguration den Lauf nicht still passiert, sondern auffällt.
* `git diff` berührt `data/state/` nicht.

**Review-Gate.** § 7, Schritte 1–4. Besonderes Augenmerk: **N-Serie**
(sagt der Name, was das Feld ist?) und **G-Serie** (keine zweite Wahrheit im
Renderer neben der Konfiguration).

**Nachmessen.**
```bash
grep -c 'ausschließlich Neugeräte ohne Vertrag' site/geraete.html   # erwartet: 0
```

---

### Phase 2 — Betriebsfundament: gelesen heißt gelesen

*Ohne diese Phase ist jede spätere Zahl unbelastbar, weil der Bestand veralten
kann, ohne dass es auffällt.*

**Ziel.** Alle liefernden Anbieter erreichen wieder vollständige Läufe, und die
Arbeitslisten der Katalogpflege existieren als Datei statt als Logzeile.

**Aufgaben.**

1. `laeufe: 0` bei mobilcom-debitel, ElectronicPartner, Medimax (§ 4.2)
   diagnostizieren und beheben. Zwei Kandidaten, beide zu messen, nicht zu raten:
   das Zeitbudget (`geraete_pipeline.FRIST_STANDARD`, `_MINDEST_JE_ANBIETER`,
   `collect/geraete/__init__.py:559`) und der Produktdeckel
   (`max_produkte`, `__init__.py:405-416`).
2. Die Kollisionsdiskrepanz bei Medimax/EP (20 Funde → 2 Listungen) aufklären.
   `GeraeteDB.kollisionen` (`analyze/geraete_store.py:194-203`) **persistieren**
   statt nur zu zählen — sonst bleibt der Befund unbeweisbar.
3. `unbekannte_titel` und `unbekannte_farben` aus
   `geraete_pipeline.py:189-200` in eine Datei unter `data/state/` schreiben
   (JSONL, mit Datum und Anbieter). Sie sind die Arbeitsliste für
   `config/geraete_katalog.yaml` und `config/farben.yaml` und existieren heute
   praktisch nicht.
4. Zubehörbündel im generischen `ldjson`-Adapter erkennen — der ALDI-TALK-Fall
   „Galaxy A17 … + Beclad Starter Kit" (§ 4.4) verunreinigt die Preisreihe.
   Die Regel steht bei o2 schon (`o2.py:64-68,95`).

**Abnahmekriterien.**

* Ein nächtlicher Lauf meldet für **alle** aktiven Anbieter mit Funden
  `vollstaendig: true` — oder der Grund steht mit Zahlen im Protokoll
  (abgeschnitten bei N von M Adressen / Frist nach X Sekunden).
* `data/state/geraete_unbekannt.jsonl` (o. ä.) existiert und ist nach einem Lauf
  nicht leer.
* Keine `listung_id` bekommt zwei verschiedene Preise am selben Tag.
* Tests für jede der vier Aufgaben; für 4 ein Fixture mit einem echten
  Bündel-Titel.

**Review-Gate.** § 7, Schritte 1–3, 5. Augenmerk: **T-Serie** (jede der vier
Änderungen braucht einen eigenen Test) und **P12/F.I.R.S.T.** — die neuen Tests
dürfen kein Netz anfassen.

**Nachmessen.**
```bash
python3 -c "import json;d=json.load(open('data/state/geraete_db.json'));\
print({k:v.get('laeufe') for k,v in d['anbieter'].items()})"
```

---

### Phase 3 — Die Preisform als First-Class-Datum

*Die Modelländerung. Noch kein neuer Anbieter, noch keine TCO.*

**Ziel.** Jede gespeicherte Zahl trägt ihre Form. Das Modell kann nicht mehr
ausdrücken „Preis ohne Vertrag", ohne zu sagen, welcher.

**Aufgaben.**

1. `PREISFORMEN` und die Zusicherungen aus § 6.1 in `geraete_model.py`
   einführen, einschließlich der Rechenprobe
   `anzahlung + n * rate == betrag`.
2. `collect/geraete/__init__.py:274-307` `_preisfelder()` auf die Preisform
   umstellen. Die Funktion behält ihre Aufgabe (welche Größe trägt diese Zahl?)
   und bekommt eine dritte und vierte Antwort.
3. `analyze/geraete_store.py` und `data/state/geraete_db.json` migrieren.
   **Bestandsschutz:** vorhandene Listungen bekommen ihre Form aus der
   Anbieter-Konfiguration (Phase 1, Aufgabe 1) zugewiesen — es wird nichts
   gelöscht und nichts neu geraten. `data/state/geraete_preise.jsonl` bleibt
   unangetastet; neue Zeilen tragen die Form, alte tragen sie nicht, und das ist
   sichtbar.
4. `report/geraete_vergleich.py:180,193`: der Vergleich rechnet nur noch
   **innerhalb einer Preisform**. Zeilen anderer Form erscheinen, aber nicht in
   derselben Rechnung — dieselbe Regel, die dort schon für Zustand und Preisart
   gilt (`geraete_vergleich.py:12-31`).
5. `beleg_gefunden` einführen und für Vodafone auf `False` setzen (Befund B-1),
   für o2 und freenet auf `True` (beide live verifiziert).

**Abnahmekriterien.**

* Ein `Preis` mit `form="raten_gesamt"` und nicht aufgehender Rechenprobe lässt
  sich nicht konstruieren — Test vorhanden.
* Die Alarmtabelle vergleicht keine zwei verschiedenen Formen mehr. Ein Test
  stellt einen Barpreis gegen einen Ratengesamtbetrag und erwartet **keine**
  Vergleichszeile.
* Der Migrationslauf verändert keine einzige Betragszahl. Test: Summe aller
  Beträge vor und nach der Migration identisch.
* Zeilen mit `beleg_gefunden == False` sind auf der Seite als solche erkennbar.

**Review-Gate.** § 7, Schritte 1–4. Augenmerk: **P1/S2** — die Rechenprobe darf
nur an einer Stelle stehen; **G-Serie** (keine Preisform-Fallunterscheidung im
Renderer, die es schon im Modell gibt).

**Nachmessen.**
```bash
python3 -c "import json,collections;d=json.load(open('data/state/geraete_db.json'));\
print(collections.Counter(l.get('preisform') for l in d['listungen']))"
```

---

### Phase 4 — Die Adapter liefern die volle Preisstruktur

**Ziel.** Anzahlung, Rate, Ratenzahl und Gesamtbetrag stehen dort, wo der
Anbieter sie nennt — statt nur einer verdichteten Zahl.

**Aufgaben.**

1. **o2** (`o2.py:98`): zusätzlich zu `totalPrice` auch `oneTimePrice`,
   `monthlyPrice` und die Ratenzahl aus dem `offerName`-Suffix (`…-24xhigh`)
   lesen. `activationFee` und die `promotion*`-Felder mitnehmen — sie sind im
   Katalog vorhanden (Live 03.09.2026) und heute unbeachtet.
2. **Vodafone** (`vodafone.py:150-183`): zusätzlich `uvp`, `total`,
   `financingAmount` und die `composition[]`-Einträge lesen. Die drei
   Ratenvarianten tragen `financingDuration` 12 / 24 / 36 und **jeweils
   `financingType: rate`** — auf `sub` zu filtern greift den einzigen Eintrag
   **ohne** Laufzeit und **ohne** `total`. Die heute gelesene Zahl als
   `form="listenpreis"` kennzeichnen. `total` = **703,00 € für alle drei
   Laufzeiten**; unterschiedlich ist nur die Rate (58,50 / 29,25 / 19,50 bei je
   1,00 € Anzahlung). Ein `raten_gesamt` ohne mitgeführte `raten_anzahl` ist bei
   Vodafone deshalb mehrdeutig und unzulässig.
3. **Handel** (`strukturdaten.py`): `form="barkauf"` setzen; `itemCondition` und
   `availability` werden bereits gelesen (`strukturdaten.py:201-208`).
4. Belegprüfung: nach dem Lesen der Produktseite prüfen, ob der gespeicherte
   Betrag im ausgelieferten Text der **verlinkten** Seite vorkommt, und das
   Ergebnis in `beleg_gefunden` schreiben. Für o2 ist das positiv verifiziert
   („(Gesamtpreis Gerät: 721,00 €)"), für freenet ebenfalls.

**Abnahmekriterien.**

* Für jede o2- und Vodafone-Listung sind Anzahlung, Rate und Ratenzahl gesetzt
  und die Rechenprobe geht auf.
* Fixture-Tests je Adapter mit einer echten, gekürzten Nutzlast vom 03.09.2026
  (die Werte aus § 1.3 und § 3.2 sind die Sollwerte).
* Ein Gegenprobe-Test, der fehlschlägt, sobald Vodafones `uvp` wieder als
  Barpreis gespeichert würde — analog zu
  `tests/test_geraete_adapter_congstar.py::test_discounted_gegenprobe…`.

**Review-Gate.** § 7, Schritte 1–3, 5. Augenmerk: **S2** — drei Adapter, die
dieselbe Ratenrechnung machen, brauchen eine gemeinsame Funktion.

**Nachmessen.**
```bash
curl -sS -H 'Accept: application/vnd.commerce.message+json' -A 'TelcoRadar/1.0' \
 'https://www.o2online.de/e-shop/rest/catalog/o2shop/privatkunden/ratenzahlung/default/__not-specified__/__not-specified__/__not-specified__?hwOnly=true' \
 | python3 -c "import json,sys;d=json.load(sys.stdin);h=[x for x in d['hardware'] if 'iphone-14-128gb-mitternacht-24' in x.get('offerName','')][0];print(h['price'])"
```

---

### Phase 5 — Telekom anbinden, congstar reparieren

*Erst jetzt, weil ein 36-Monats-Gesamtbetrag ohne Preisform den Vergleich
zerstören würde (§ 3.3).*

**Ziel.** Alle vier Netzbetreiber stehen mit einer korrekt etikettierten Zahl auf
der Seite; das Telekom-Netz ist nicht länger unbelegt.

**Aufgaben.**

1. Adapter `telekom_state`: Einstieg
   `https://www.telekom.de/shop/geraete/smartphones/ohne-vertrag`,
   `__INITIAL_STATE__` parsen, je Gerät `upfrontPrice`,
   `price.installments[].recurringPrice`, `numberOfInstallments` und
   `totalPrice` als `form="raten_gesamt"`. `methode: json_endpunkt` durch den
   echten Adapternamen ersetzen, `aktiv: true`.
2. **Zwei offene Punkte klären, bevor der Adapter als fertig gilt:**
   die Paginierung (`"currentPage": 1`, § 5.5 Nr. 12) und die Frage, ob httpx
   gegen telekom.de heute die 202-Challenge auslöst (§ 5.5 Nr. 11). Fällt httpx
   durch, ist das eine Client-Frage (`collect/http.py`), keine Zugangsfrage —
   und sie gehört gemessen, nicht umgangen.
3. Linkziel: die Produktseiten aus der Sitemap
   (`https://www.telekom.de/content/robots/sitemap`, 301 Adressen unter
   `/shop/geraet/`) als Quelllink verwenden. **Achtung:** die Produktseite trägt
   den Betrag nicht (§ 3.2) — also `beleg_gefunden = False`, wie bei Vodafone.
   Keine Ausnahme für den eigenen neuen Adapter.
4. **congstar** (§ 4.1): 0 Funde seit dem 31.08.2026 bei `aktiv: true`
   diagnostizieren. Der Adapter existiert und ist getestet
   (`tests/test_geraete_adapter_congstar.py`) — der Ausfall liegt also am
   Einstieg, am Zeitbudget oder an einer Änderung der Seite.
5. **Robots erneut prüfen und die Prüfung festhalten.** Der heutige Befund
   (nur `/is-bin/intershop.*` gesperrt) muss im `hinweis` mit Datum stehen, und
   `RobotsWaechter` muss ihn zur Laufzeit erneut lesen — nicht die
   Konfigurationszeile glauben.

**Abnahmekriterien.**

* Telekom liefert Listungen; die Rechenprobe geht bei allen auf.
* `bilanz["nicht_verlinkt"]` ist leer (keine geratene Adresse).
* congstar liefert Listungen **oder** trägt einen mit Datum gemessenen `grund`
  und `aktiv: false`. Ein aktiver Anbieter ohne Fund ist kein zulässiger
  Endzustand.
* Die Vergleichstabelle stellt Telekoms Ratengesamtbetrag **nicht** gegen
  freenets Barpreis (Phase-3-Regel greift).

**Review-Gate.** § 7, alle fünf Schritte. Augenmerk: die repo-eigenen S1-Regeln
(Schritt 3) — robots, Crawl-delay, keine hochgezählten IDs. Neuer Anbieter heißt
neue Angriffsfläche für genau diese Regeln.

**Nachmessen.**
```bash
curl -sS -A 'TelcoRadar/1.0' https://www.telekom.de/content/robots
curl -sS -L --compressed -A 'TelcoRadar/1.0' \
  https://www.telekom.de/shop/geraete/smartphones/ohne-vertrag \
  | grep -c '__INITIAL_STATE__'
```

---

### Phase 6 — Tarife: Bestand und Bezug

*Ohne Tarif keine TCO. Der Tarifzweig existiert und ist fast leer.*

**Ziel.** Genug Tarife im Bestand, dass eine TCO überhaupt rechenbar ist — und
ein belastbarer Bezug zwischen einer Bündel-Gerätezahl und dem Tarif, zu dem sie
gehört.

**Aufgaben.**

1. `config/tarif_quellen.yaml` ausbauen. Telekom ist konfiguriert (1177
   verlinkte PIB) und liefert nichts — die Ursache messen. Vodafone fehlt ganz;
   1&1 ist mit Begründung ausgesetzt (`tarif_quellen.yaml:54-59`).
2. Den **Fremdschlüssel** herstellen: `Listung.tarif_referenz` wird zu
   `tarif_id` (`data/state/tarife.jsonl` führt bereits `tarif_id`, z. B.
   `o2:o2-mobile-unlimited-m-flex`). Ein Bündelpreis ohne auflösbaren
   `tarif_id` wird weiterhin verworfen — die heutige Regel
   (`geraete_model.py:857-861`) bleibt, sie bekommt nur ein Ziel.
3. **Das ungelöste Problem benennen und lösen:** Vodafones
   `composition[].priceByComponent.tariff` nennt Beträge (41,95 € / 31,45 €),
   **aber keinen Tarifnamen** (Live 03.09.2026). Ohne Zuordnung ist die
   Bündelzahl nach der Projektdisziplin nicht speicherbar. Zu prüfen: ob ein
   zweiter Schnittstellenaufruf den Tarif nennt, oder ob die Zuordnung über den
   Betrag gegen `tarife.jsonl` erfolgen kann (**dann mit
   `confidence: mittel`, nie `hoch`**).
4. `Preisphase` (`tarif_model.py:53-67`) mit echten Daten füllen. **Achtung:**
   die beiden früher hier genannten Fixtures sind keine belegten Sollwerte mehr
   — die 1&1-Staffelung „3 Monate je 9,99 €" steht nicht an der zitierten
   Fundstelle (§ 5.5 Nr. 15), und o2s 10-€-Vorteil gilt ohne die Bedingung „ab
   dem 2. Vertragsjahr" (§ 5.2). Testfälle sind erst aus einer **neu belegten**
   Preisstaffel zu bilden; Vodafones „Mobil S 49,99 € ab dem 13. Monat" ist
   ebenfalls ungeklärt (§ 5.5 Nr. 9).

**Abnahmekriterien.**

* `data/state/tarife.jsonl` enthält Tarife von mindestens drei Anbietern.
* `site/tarife.html` sagt weiterhin wahrheitsgemäß, wer erfasst ist und wer
  konfiguriert, aber ohne Daten.
* Kein Bündelpreis im Bestand ohne auflösbaren `tarif_id`.
* Eine Bündelzahl, deren Tarif nur über den Betrag zugeordnet wurde, trägt
  `confidence: mittel` — Test vorhanden.

**Review-Gate.** § 7, Schritte 1–3, 5. Augenmerk: **P8/P9** (Ausnahmen mit
Kontext beim PDF-Extraktor) und die Belegregel aus `tarif_model.py:121-131`
(kein Feldwert ohne Fundstelle).

**Nachmessen.**
```bash
python3 -c "import json,collections;\
print(collections.Counter(json.loads(l)['anbieter'] for l in open('data/state/tarife.jsonl')))"
```

---

### Phase 7 — Der TCO-Rechner

**Ziel.** Aus Gerät, Preisform und Tarif entstehen zwei belegte Zahlen mit
sichtbaren Lücken.

**Aufgaben.**

1. Modul `report/tco.py`, gebaut wie `report/effektivpreis.py`: ein
   `Tco`-Dataclass mit `bestandteile: dict`, `luecken: list[str]`,
   `belastbar: bool`.
2. **Zwei Horizonte** (§ 6.3): `tco_bindung` und `tco_voll`. Die Differenz wird
   ausgewiesen, nicht versteckt.
3. `effektivpreis.rechne()` bekommt seinen `geraetezuzahlung`-Parameter
   (`effektivpreis.py:141`) endlich gefüllt — statt eines zweiten, parallelen
   Rechenwegs. **Nicht duplizieren** (S2): der TCO-Rechner benutzt
   `phasensumme()` (`effektivpreis.py:77-101`).
4. Die Lückenliste ist Pflicht. Aus § 5.5 folgt, dass Versandkosten,
   Servicepauschalen und Wechslerbonus bei **keinem** Anbieter belegt sind —
   jede TCO wird diese drei Lücken tragen, und sie muss sie nennen.
5. Restbetrag jenseits des Horizonts: bei 36-Monats-Raten (Telekom, Vodafone,
   o2) und bei congstars Schlussrate im Rückgabedeal ist das der Unterschied zwischen einer richtigen und einer
   werbewirksamen Zahl.

**Abnahmekriterien.**

* Ein Rechenbeispiel aus § 1.3 (Vodafone iPhone 15, 1,00 € + 12 × 58,50 €,
  Tarif 41,95 €/Monat ohne Rabatt) ergibt eine nachrechenbare TCO — als Test
  mit von Hand geprüften Sollwerten.
* Fehlt eine Komponente, erscheint sie in `luecken` und **nicht** als 0.
* `tco_voll >= tco_bindung` immer; ein Test stellt den o2-36-Monats-Fall
  (24 Monate Bindung, 36 Geräteraten).
* Kein zweiter Rechenweg für Preisphasen im Repo (Grep als Teil der Abnahme).

**Review-Gate.** § 7, Schritte 1–3. Augenmerk: **S2/Duplizierung** — das ist die
Phase, in der eine zweite Preisrechnung entstehen könnte; und **P14** (ein
Konzept pro Test).

---

### Phase 8 — TCO auf der Seite

**Ziel.** Ein Vodafone-Manager sieht, was ein Gerät bei wem über die Laufzeit
wirklich kostet — und woran die Zahl hängt.

**Aufgaben.**

1. Die TCO als eigene Ansicht, nicht als weitere Spalte in der Alarmtabelle.
   Die Alarmtabelle beantwortet „wo liegen wir zurück"; die TCO beantwortet
   „was kostet es". Zwei Fragen, zwei Tafeln (dieselbe Logik wie die drei
   heutigen Reiter).
2. Je Zeile: beide Horizonte, die Bestandteile aufklappbar, die Lücken sichtbar,
   der Quelllink mit `beleg_gefunden`-Kennzeichnung.
3. Export (`report/geraete_export.py`) um die TCO-Felder erweitern.
4. Der Erklärtext nennt die Methode in zwei Sätzen und die Grenze in einem —
   im Stil von `site/tarife.html` („Grundlage ist das gesetzlich vorgeschriebene
   Produktinformationsblatt, nicht die Werbeseite").

**Abnahmekriterien.**

* `scripts/pruefe_portal.py` und `scripts/schiess_screenshot.py` laufen sauber.
* Keine TCO-Zahl ohne Herkunft und ohne Lückenangabe auf der Seite.
* Ein Browser-Test (`tests/test_geraete_reiter_browser.py`-Bauart) für die neue
  Tafel — er läuft nur mit Playwright und ist als solcher gekennzeichnet.
* Die Seite bleibt im Höhenbudget (vgl. `geraete_alarme.SICHTBAR_MAX`).

**Review-Gate.** § 7, alle fünf Schritte, plus die Testexistenz-Regel (P11):
neues Verhalten ohne Test ist S1. Optik-Kriterien, die ein Test nicht greifen
kann, gehen über die beiden Smoke-Skripte.

---

## 9. Risiken

**R1 — Der Vergleich wird kurzfristig schlechter aussehen, bevor er besser wird.**
Sobald Phase 3 nur noch innerhalb einer Preisform vergleicht, brechen Zeilen weg:
o2 (83 Listungen, Ratengesamtbetrag) und Vodafone (151, Listenpreis) haben dann
formal keine gemeinsame Vergleichsbasis mit dem Handel mehr. Die Seite wird
ehrlicher und dünner. *Gegenmaßnahme:* Phase 4 stellt die Basis wieder her,
indem sie aus Vodafones `composition` einen echten Ratengesamtbetrag gewinnt —
dann vergleichen o2, Vodafone und Telekom untereinander in derselben Form.
*Diese Zwischenlage muss Antonio wollen* (siehe E1).

**R2 — Quellenvolatilität.** In drei Monaten hat Vodafone sein Portfolio
umbenannt und o2 umgestellt; fünf recherchierte URLs antworteten 404 (§ 5.5).
Vodafones Adapter hängt zusätzlich an einem öffentlichen Browser-Schlüssel
(`geraete_quellen.yaml:320`), der jederzeit rotiert werden kann. *Gegenmaßnahme:*
`beleg_gefunden` macht ein stilles Wegbrechen sichtbar, statt dass eine alte Zahl
weiterläuft.

**R3 — Der Telekom-Client.** Die 202-Challenge gegen httpx (`CLAUDE.md:683-687`)
ist real dokumentiert und heute **ungeprüft**. Fällt sie an, ist Phase 5 kein
Parser-, sondern ein Client-Problem. Ein User-Agent-Wechsel wäre keine Lösung,
sondern eine Umgehung — und damit nach den repo-eigenen S1-Regeln unzulässig,
solange robots.txt nicht ohnehin erlaubt, was getan wird (sie tut es hier).
*Zu entscheiden ist die Grenze zwischen „anderer HTTP-Client" und „Umgehung".*

**R4 — Der Tarifbezug bei Vodafone ist ungelöst.** Ohne Tarifnamen in der
Nutzlast (§ 6.2, Zeile 7) bleibt die Bündelseite von Vodafone modellierbar, aber
nicht speicherbar. Eine Betragszuordnung gegen `tarife.jsonl` ist möglich, aber
schwächer. *Wenn Phase 6, Aufgabe 3 scheitert, liefert Phase 7 für Vodafone nur
`tco_voll` auf Gerätebasis, keine Bündel-TCO.*

**R5 — Datendünne.** 7 Messtermine, 4 belegte Preisänderungen (drei o2, eine
ALDI TALK), 4 Listungen mit mehr als einem Preispunkt (§ 4.4). Jede Aussage über Preisverfall ist derzeit
statistisch nicht tragfähig, und keine Phase dieses Plans ändert das — nur Zeit
tut das. *Die Seite sagt es bereits; sie muss es weiter sagen.*

**R6 — Der Katalog ist der stille Flaschenhals.** 65 % ohne Marktstart, 51 % der
Listungen ohne normalisierte Farbe, die iPhone-18-Reihe fehlt bei Marktstart
September 2026 (§ 4.3). Ein Gerät ohne Katalogeintrag existiert für dieses System
nicht. Phase 2 stellt die Arbeitsliste her — **füllen muss sie ein Mensch.**

**R7 — Rechtliche Grenze.** Jede neue Quelle vergrößert die Fläche für § 87b
UrhG und robots.txt. Die bestehende Disziplin (nur verlinkte Adressen,
`nicht_verlinkt` als Buchführung) ist gut; sie muss bei Telekom, congstar und
jedem Tarif-PDF unverändert gelten. Bei den PIB-Dokumenten ist die Lage
besonders klar: sie sind Pflichtdokumente, deren Zweck die Abrufbarkeit ist —
aber `tarif_quellen.yaml:5-16` verbietet zu Recht das Durchzählen der
o2-Blob-IDs. **Das bleibt so.**

**R8 — Die Testumgebung ist unvollständig.** Pillow fehlt auf dieser Maschine,
und von Playwright fehlt das Chromium-Binary (das Modul ist installiert, § 7);
2 Tests schlagen fehl, 49 brechen zur Laufzeit ab — `--collect-only` sammelt
2270 Tests ohne Collection-Error. Wer ein Gate ohne
diese Kenntnis anwendet, hält einen grünen Lauf für unerreichbar oder einen roten
für normal. *Vor Phase 1 klären, auf welcher Umgebung abgenommen wird.*

---

## 10. Offene Entscheidungen für Antonio

**E1 — Ehrlichkeit vor Fülle?**
Phase 3 nimmt Vergleichszeilen von der Seite, bis Phase 4 sie in korrekter Form
zurückbringt. Zwischen beiden Phasen zeigt die Seite weniger als heute.
*Alternative:* Phase 3 und 4 als eine Auslieferung zusammenfassen — größerer
Schritt, kein sichtbarer Rückschritt.
→ **Zu entscheiden: zwei kleine Phasen mit Delle oder eine große ohne.**

**E2 — Welcher Horizont ist die Leitzahl?**
§ 6.3 empfiehlt zwei Kennzahlen. Auf einer Seite für Manager ohne technischen
Hintergrund braucht es trotzdem **eine** Zahl, die groß steht.
→ **Zu entscheiden: `tco_bindung` (24 Monate, vergleichbar, unterschätzt o2) oder
`tco_voll` (bis abbezahlt, wahrhaftig, vergleicht 24 gegen 36 Monate).**
Empfehlung: `tco_voll` groß, `tco_bindung` klein darunter — die Seite sagt sonst
dasselbe, was CHECK24 sagt, und übernimmt dessen Schwäche.

**E3 — Wird Vodafone als Listenpreis oder als Bündelbetrag geführt?**
Vodafones 709,90 € sind der `uvp`-Wert; 703,00 € ist der Betrag im 12-Monats-
Bündel. Beide sind belegt, beide sind wahr, sie beantworten verschiedene Fragen.
→ **Zu entscheiden: Welche Zahl steht in der Positionskarte für „unser Preis"?**
Das ist keine technische Frage — sie entscheidet, wogegen sich Vodafone auf
seiner eigenen Wettbewerbsseite misst.

**E4 — Wie weit darf der HTTP-Client angepasst werden?**
Telekom antwortet curl mit 200 und (dokumentiert) httpx mit 202. robots.txt
erlaubt den Abruf ausdrücklich. Ist ein anderer TLS-Client eine legitime
technische Anpassung oder eine Umgehung?
→ **Antonios Grenzziehung wird als Regel in `CLAUDE.md` gebraucht**, nicht als
Einzelfallentscheidung im Adapter.

**E5 — Wird der Elektronikfachhandel aufgegeben oder ausgebaut?**
Amazon, MediaMarkt, Saturn, expert, Euronics sind gesperrt oder nicht
angebunden; Cyberport, notebooksbilliger.de, Otto und Gravis sind nicht einmal
konfiguriert (§ 4.1). Der Handel liefert heute 4 von 391 Listungen aus **einem**
Betreiber. Als Barpreis-Referenz ist er aber die einzige saubere Vergleichsbasis
gegen die Ratenangebote der Netzbetreiber.
→ **Zu entscheiden: eine Phase 9 für zwei bis drei Barpreis-Händler, oder die
bewusste Beschränkung auf Netzbetreiber und Zweitmarken.**

**E6 — Wer pflegt den Katalog?**
Phase 2 stellt die Arbeitsliste her; 54 fehlende Marktstartdaten und die
iPhone-18-Reihe muss ein Mensch eintragen (§ 4.3, R6). Ohne feste Zuständigkeit
verfällt die Liste wie heute im Log.
→ **Zu entscheiden: Wer, in welchem Rhythmus?**

**E7 — Markenliste zusammenführen?**
`config/promo_sources.yaml` und `config/geraete_quellen.yaml` beobachten
verschiedene Markenmengen (§ 4.1). Vier Marken kennt das Promo-Radar und das
Geräteradar nicht; fünf umgekehrt.
→ **Zu entscheiden: eine gemeinsame Markenliste als dritte Konfigurationsdatei,
oder bewusst getrennt halten (die Quellenarten sind verschieden — dieselbe
Begründung wie in `TELCO_RADAR_HANDOVER.md` §12).**

---

## 11. Ausdrücklich nicht

* **Keine Barpreis-Schätzung für o2 und Telekom.** Wenn ein Anbieter nur
  Ratenzahlung anbietet, ist der Barpreis unbekannt und wird nicht abgeleitet.
* **Kein Rückfall auf Textextraktion** für Preise. `strukturdaten.py:293-304`
  begründet das gut; die Regel gilt auch für `__INITIAL_STATE__`-Adapter — es
  wird ein Feld gelesen, kein Regex über sichtbaren Text.
* **Kein Umgehen von robots.txt, Crawl-delay oder Visit-time**, auch nicht für
  die Telekom, auch nicht mit einem anderen User-Agent.
* **Keine hochgezählten IDs**, weder bei Telekoms `/shop/geraet/`-Adressen noch
  bei o2s Blob-IDs.
* **Kein Commit von `data/state/` oder `data/reports/` aus lokalen Läufen.**
* **Keine MagentaEINS-Bewertung in Euro.** Eine Sachleistung bekommt kein
  erfundenes Preisschild (§ 5.2).
* **Keine Übernahme der CHECK24-Methodik** („bestenfalls realisierbare
  Vergünstigungen", 24-Monats-Kappung unabhängig von der Laufzeit) — beide
  Schwächen sind in § 5.4 benannt.
* **Keine Zahl aus § 5.5** in Code, Konfiguration oder Seiteninhalt, solange sie
  ungeprüft ist — das gilt gleichermaßen für die dort als *teilweise belegt*
  geführten Werte T1–T3 und für jede Zahl, die anderswo im Dokument als
  ungeprüft gekennzeichnet ist.

---

## 12. Nachmessen — die Befehle dieses Audits

Alle am 03.09.2026 ausgeführt. Sie belegen die vier Befunde; sie belegen
**nicht** jede Aussage des Dokuments — die Marktrecherche in § 5 stützt sich auf
Live-Abrufe, die nicht als Befehl mitgeliefert sind, und die als *ungeprüft*
oder *teilweise belegt* gekennzeichneten Punkte sind ausdrücklich nicht
reproduziert. Der Stand nach der unabhängigen Verifikation vom 03.09.2026
(Korrekturen W1–W12) ist eingearbeitet.

```bash
# --- Bestand ---
python3 -c "import json,collections;d=json.load(open('data/state/geraete_db.json'));\
L=d['listungen'];print(len(L));print(collections.Counter(l['anbieter'] for l in L));\
print(collections.Counter(l['erstpreis_art'] for l in L))"

# --- Laufvollständigkeit je Anbieter ---
python3 -c "import json;d=json.load(open('data/state/geraete_db.json'));\
print({k:(v.get('laeufe'),v.get('letzter_fund')) for k,v in d['anbieter'].items()})"

# --- Befund B: die 709,90 EUR und ihr Beleg ---
curl -sS -A 'Mozilla/5.0' -H 'x-api-key: DSWoP7V0jh0a3LFDdq3XhiBD5Uh5GuzR' \
  -H 'Accept: application/json' \
  'https://api.vodafone.de/glados/v2/hardware/v2/virtualItem/51?businessTransaction=newContract&salesChannel=Online.Consumer' \
  | python3 -c "import json,sys;a=json.load(sys.stdin)['data']['atomics'][0];\
p=a['prices'];print('gelesen:',p['hardware']['priceByType']['rate']['onetime']['withoutDiscounts']['gross']);\
c=p['composition'][0]['priceByComponent']['hardware']['priceByType'];\
print('uvp:',c['uvp']['onetime']['withoutDiscounts']['gross'],\
'total:',c['total']['onetime']['withoutDiscounts']['gross'])"

curl -sS -L -A 'Mozilla/5.0' https://www.vodafone.de/privat/handys/iphone-15.html \
  | grep -c 709            # erwartet: 0

# --- Befund A: o2 rechnet Anzahlung + 24 Raten ---
curl -sS -A 'TelcoRadar/1.0' -H 'Accept: application/vnd.commerce.message+json' \
  'https://www.o2online.de/e-shop/rest/catalog/o2shop/privatkunden/ratenzahlung/default/__not-specified__/__not-specified__/__not-specified__?hwOnly=true' \
  | python3 -c "import json,sys;d=json.load(sys.stdin);\
h=[x for x in d['hardware'] if x.get('offerName')=='privatkunden-apple-iphone-14-128gb-mitternacht-24xhigh'][0];\
p=h['price'];print(p['oneTimePrice'],'+ 24 x',p['monthlyPrice'],'=',p['oneTimePrice']+24*p['monthlyPrice'],'| totalPrice',p['totalPrice'])"

# --- Befund C: Telekom ist offen und liefert Preise ---
curl -sS -L -A 'TelcoRadar/1.0' https://www.telekom.de/robots.txt
curl -sS -L --compressed -A 'TelcoRadar/1.0' \
  https://www.telekom.de/shop/geraete/smartphones/ohne-vertrag \
  | grep -o '"upfrontPrice":[0-9.]*' | sort | uniq -c

# --- Tests ---
PYTHONPATH=src python3 -m pytest -q
```

---

## 13. Der Satz, an dem dieser Plan sich messen lassen soll

> Auf der Geräteseite steht keine Zahl mehr, deren Bedeutung man erst der
> Quelle entnehmen muss — und keine Quelle mehr, die die Zahl nicht enthält.
