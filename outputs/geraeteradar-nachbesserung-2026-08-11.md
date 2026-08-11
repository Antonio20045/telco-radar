# Geräteradar — Nachbesserung nach der Evaluation

Stand: 11. August 2026. Grundlage war das Evaluationsdokument zur ersten
Lieferung (10.08.). Gearbeitet wurde in der Reihenfolge P1 → P3 → P2.

**Stand danach:** 1411 Tests (vorher 1398), `pruefe_portal.py` **15 bestanden
/ 0 durchgefallen / 0 nicht prüfbar**.

---

## Was erledigt ist

### P1 — die Positionskarte (Commit `e56808d`)

Der Kernbefund ist bestätigt und war in der Anbieteransicht schlimmer als im
Dokument beschrieben. Am ausgelieferten `site/geraete.html` gemessen:

| | Punkte | mit Etikett | größter Versatz |
|---|---|---|---|
| Hersteller | 85 | 66 | **181 px** |
| Anbieter | 85 | 28 | **235 px** |

**87 von 94 Etiketten** standen weiter als drei Prozent neben ihrem Preis.
**60 von 85 Kreisen** lagen exakt deckungsgleich; es gab 25 unterschiedliche
Koordinaten.

Neu: `src/telco_radar/report/geraete_karte.py` mit drei Regeln.

1. **Die Y-Achse gehört dem Preis.** Ausgewichen wird ausschließlich nach
   rechts, per Intervallpackung. Es gibt keinen Codepfad mehr, der `label_y`
   unabhängig von `cy` setzt — das ist der ganze Unterschied zu
   `ly = max(cy, letzte + 14)`.
2. **Gezeichnet werden Preispunkte, keine SKUs.** Aggregation auf
   (Modell, Speicher, Laden, **Zustand**). Der Zustand gehört in den
   Schlüssel: sonst schluckt ein refurbished-Preis den Neupreis desselben
   Geräts — ALDI TALK listet genau so ein Gerät.
3. **Was im Zeichenbereich steht, trägt eine Preisaussage** (`gr-etikett`);
   was unter der Achse steht, nicht (`gr-bandname`). Beidseitig geprüft,
   sonst wäre die Ausnahme ein Schlupfloch.

**Zwei Formen, beide gebaut, Preisbänder als Standard.** Aus 38 Apple-Punkten
werden fünf Bänder. Screenshots beider Formen liegen unter
`/tmp/telco-screenshots/` (`geraete-band-*`, `geraete-nachher-*`); die Wahl
ist eine Zeile in `geraete_karte.FORMEN` und jederzeit umkehrbar.

**Breite vor Höhe.** 1180 statt 980 px — die Seite gibt 1184 her, die alte
SVG verschenkte 200. Das hebt die Chipbahnen je Spalte von drei auf vier und
spart 360 px Höhe. Mobil wird **gerollt statt gestaucht**; die Regel
`.gr-etikett{font-size:8px}` im Media Query ergab auf einem 390-px-Telefon
real 2,7 CSS-Pixel und ist ersatzlos weg.

**mobilcom-debitel und freenet sind derselbe Laden** (neue Felder
`shop`/`anzeige`). Als zwei Spalten verglich die Karte einen Laden mit sich
selbst. Die Veröffentlichungsschwelle zählt deshalb **Läden, nicht Marken** —
sonst schaltete sich der Navigationseintrag mit „2 Anbietern" frei, während
die Karte eine Spalte zeigt.

**Ergebnis, gemessen:** 25 Punkte statt 85, 25 verschiedene Koordinaten,
größter Etikettenversatz **3,5 px**, **0** Etiketten außerhalb der
3-%-Grenze.

### P3 — Lifecycle und Wochenkarte (Commit `165f546`)

**Die Ursache der 24 Nullzeilen gefunden:** `duenn = len(punkte) < MIND_PUNKTE`
zählte **Preispunkte statt Messtermine**. 85 Listungen an einem Tag ergeben 85
Punkte, die Basis galt als tragfähig, und `gr-basis--duenn` — im CSS seit dem
ersten Tag angelegt — kam im HTML kein einziges Mal vor.

Gezählt werden jetzt verschiedene Messtage und die Spanne dazwischen, **je
Gerät**: vier Termine über mindestens 21 Tage, sonst keine Zeile.

**Korrektur zum Dokument, Punkt 5:** „Was diese Woche auffällt" war gebaut
(`_auffaellig()` + Vorlage) und rendert nur nicht. Zwei Gründe, beide behoben:

1. Der Bezugstag war der **Berichtstag**. Der Gerätezweig läuft nächtlich, der
   Bericht zweimal die Woche — die Gerätedaten sind damit regelmäßig neuer als
   „heute" (gemessen: Bestand vom 11., letzter Bericht vom 8.). Weil das
   Fenster nur zurückschaut, fiel jede Änderung heraus.
2. Ohne zweiten Messtag kann keine Bewegung entstanden sein. Die Karte zeigt
   dann, was neu **erfasst** wurde, und sagt das auch so.

### P0 — die Regel über allem

`scripts/schiess_screenshot.py` ist neu. Es rendert, fotografiert 1440 und
390 px **und rechnet aus jeder Etikettenhöhe den Preis zurück**. Gegen den
alten Stand gemessen meldet es 87 Beanstandungen, gegen den neuen null.

`pruefe_portal.py` Kriterium 11 tut dasselbe. Vorher prüfte es nur „kein
Etikett unter der Nulllinie" — genau daran lief der echte Fehler vorbei, der
181 px **über** der Achse stattfand.

---

## Was NICHT erledigt ist: P2, die Abdeckung

**Ehrlich und ohne Beschönigung: es liefern weiterhin zwei Anbieter.** Die
Grundlage steht, die Adapter fehlen.

### Was steht

Der Ausbau scheiterte an der Architektur, nicht an den Seiten:
`UMGESETZTE_METHODEN` war ein Tupel, die Verzweigung ein hartcodiertes `if`,
und `json_endpunkt` ein **Sammelbegriff für fünf verschiedene Nutzlasten**.
Jetzt:

- **Adapter-Registry** `{methode: Adapter}` mit `lies` **und** `ernte`. Der
  zweite Teil wird gern vergessen: Telekom und o2 führen ihre Produktadressen
  in derselben JSON-Nutzlast wie die Preise, nicht als `<a href>`.
- **Bündelpreise** (P2.3): `_preisfelder()` kann eine Zuzahlung **mit
  Tarifreferenz** schreiben; ohne sie wird sie weiterhin verworfen. Das
  Datenmodell trug die Felder längst, die Sammelschicht konnte sie nicht
  füllen.
- Die Belegstufe wird aus der Registry **nachgeschlagen** statt an einer
  Stelle aufgezählt — ein neuer Adapter hätte sonst still „mittel" belegt.

### Warum keine Adapter — und was das Messen ergeben hat

Der `ultracode`-Workflow lief mit einem Bau- und einem Prüf-Subagenten je
Anbieter. **Der Bau-Subagent für Telekom hat seine Fixture erfunden** — er
behauptete ein `application/ld+json` auf der Produktseite, wo live null
Treffer stehen. Der adversarische Prüfer hat das aufgedeckt; die Artefakte
sind gelöscht. (Ein Konfigurationsfehler meinerseits: die Anbieterliste kam
als Zeichenkette statt als Liste im Workflow an, deshalb lief nur Telekom.)

**Anschließend selbst nachgemessen** — und dabei sind zwei Angaben gefallen,
die bisher als gemessen galten:

| Anbieter | Befund vom 11.08.2026 |
|---|---|
| **Telekom** | `productDetailed.productDetailsData` trägt je Speicherstufe nur `deltaPrice`, also einen **Aufschlag ohne Grundbetrag**. Die einzigen absoluten Beträge sind `installmentConfiguratorItems[…].upfrontPrice` je Ratenlaufzeit — **Zuzahlungen im Bündel**. Die bisherige Angabe „der Preis steht in productDetailsData" ist damit falsch. Über HTTP/2 antwortet eine WAF-Challenge, über HTTP/1.1 kommen 2,8 MB. Die Linkernte steht: zehn Adressen als echte `a-href` unter `/shop/geraet/`. |
| **o2** | Die Einstiegsseite trägt ein ld+json vom Typ **BreadcrumbList** — kein Produktschema. Die Kaskade des Projekts liefert null Sätze. |
| **1&1** | ld+json-Typen: FAQPage, WebSite, Organization. Kein Produktschema. |
| **expert** | Genau ein ld+json-Block, und der hat **gar kein `@type`**. Sitemap liefert sauber: 1837 Adressen. |
| **Blau** | Produktdaten als **escaptes ld+json in einem HTML-Attribut**, Preis darin `"price": "1.00"` — eine Zuzahlung. |

**Die tragende Erkenntnis für die nächste Sitzung:** alle zwölf konfigurierten
Einstiegsseiten antworten mit **HTTP 200** — auch MediaMarkt, das die
Evaluation als 403 führt (403 gilt nur für die Produktseiten). Gescheitert
ist nichts am Zugang, sondern daran, dass **kein einziger dieser Anbieter ein
`Product`-Schema ausliefert**. Der billige Weg („nur Konfiguration, kein
Code") existiert nicht; jeder braucht seinen Extraktor.

Und: **die Netzbetreiber-Ebene hängt an P2.3, nicht an den Extraktoren.**
Telekom und Blau liefern Zuzahlungen. Ohne Tarifreferenz bleiben sie zu Recht
draußen — die Schicht dafür steht jetzt, der Extraktor ist der Rest.

Alle diese Messungen stehen **wörtlich in `config/geraete_quellen.yaml`** und
damit auf `/geraete-quellen.html`. Kein Anbieter fehlt dort stillschweigend.

---

## Akzeptanzkriterien, abgehakt

| Kriterium | Stand |
|---|---|
| Rückgerechneter Preis < 3 % daneben, als Test hinterlegt | **erfüllt** (Test + Kriterium 11 + Screenshot-Helfer, drei Orte, eine Formel) |
| Kein Punkt deckungsgleich auf einem anderen | **erfüllt** |
| Höchstens so viele Punkte wie (Modell, Speicher, Anbieter) | **erfüllt** — 25 statt 85 |
| Etikettenschrift nie unter 10 px, auf 390 px scrollen | **erfüllt** |
| Tap füllt die Detailzeile inkl. Quelllink | **erfüllt** |
| Mindestens 8 Anbieter, darunter Telekom, o2, Vodafone | **nicht erfüllt** — siehe oben |
| Kein Anbieter auf „gemessen, aber ohne Adapter" | **nicht erfüllt** |
| Bündelpreise nur mit Tarif | **erfüllt** (Schicht steht, noch kein Lieferant) |
| Kein Lifecycle-Eintrag ohne 4 Messtermine über 21 Tage | **erfüllt** |
| Screenshots 1440/390 liegen vor und wurden angesehen | **erfüllt** |
| Alle bestehenden Tests grün, keiner abgeschwächt | **erfüllt** — 1411, jeder ersetzte Test durch einen strengeren |

---

## Offen für die nächste Sitzung

1. **Die acht Adapter.** Reihenfolge nach Wert unverändert. Die Nutzlastpfade
   stehen jetzt gemessen in der Konfiguration; das Fundament (Registry,
   Linkernte je Adapter, Bündelpreise) trägt.
   **Fixtures müssen aus einem gespeicherten echten Abruf stammen** — der
   erste Anlauf hat gezeigt, wie leicht dort etwas erfunden wird.
2. **Vodafone** ist der einzige ohne jedes statische Preissignal (219 KB ohne
   `price`). Für ihn ist die JS-Stufe freigegeben; sie ist in der Sandbox
   nicht testbar und erst im nächtlichen Actions-Lauf beweisbar.
3. **MediaMarkt und Saturn zählen als EIN Wettbewerber** (Ceconomy). Die
   Felder `shop`/`anzeige` tragen das bereits — beide Einträge haben sie noch
   nicht, weil sie inaktiv sind.
4. **`max_produkte` bei expert.** 1837 Adressen gegen einen Standarddeckel von
   60: ein erreichter Deckel macht die Einstiegsseite ungelesen, dann altert
   nichts und der Anbieter steht trotz Funden als „fehler" im Protokoll.
5. **Die SKU-Matrix mit acht Anbietern** auf Lesbarkeit prüfen, Gerätespalte
   gegebenenfalls sticky (P3.3, bis dahin gegenstandslos).
