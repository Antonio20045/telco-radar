# Geräte- und Preisradar — Schlussliste

Stand: 10. August 2026. Auftrag: `/geraete.html`, vier Bauabschnitte D1–D4.
Alles umgesetzt. **1384 Tests** (vorher 1104), `pruefe_portal.py`: 14
bestanden, 0 durchgefallen, Kriterium 11 übersprungen — es braucht Daten, die
erst der erste Lauf bringt.

---

## Was gebaut wurde

| Abschnitt | Dateien | Die eine Regel, die ihn trägt |
|---|---|---|
| **D1** Modell | `geraete_model.py`, `geraete_config.py`, `config/geraete_katalog.yaml` (46 Modelle), `config/farben.yaml`, `config/geraete_quellen.yaml` (23 Anbieter) | Die ID kommt aus dem **Katalogeintrag**, den ein Titel trifft — nie aus dem Titel. Lesbare Slugs statt Hash |
| **D2** Collector | `collect/geraete/{__init__,robots,strukturdaten}.py`, `analyze/geraete_store.py`, `geraete_pipeline.py`, `.github/workflows/geraete.yml` | Zwei-Stufen-Auslistung; und was **nicht gelesen** wurde, altert nicht |
| **D3** Lifecycle | `analyze/geraete_lifecycle.py` | Deterministisch, kein LLM. Unter 12 Messpunkten „Datenbasis dünn", kein Trend |
| **D4** Seite | `report/geraete_view.py`, `templates/geraete{,_quellen}.html.j2`, `style.css`, `app.js`, `render_site()`, `pruefe_portal.py` Kriterium 11 | Positionskarte als gerechnetes SVG, beide Ansichten vorgerechnet, Umschalter ohne Reload |

---

## Die Quellen sind gemessen, nicht geraten

Am 10.08.2026 wurden **22 Anbieter einzeln abgerufen** (Amazon nicht — es
wird aus Rechtsgründen gar nicht erst angefasst; 23 stehen in der Konfiguration) — robots.txt zuerst,
dann eine Kategorie- oder Sitemap-Seite, dann eine Produktseite, und der Preis
mit `json.loads` aus dem strukturierten Datensatz gezogen. Ergebnis:

| Klasse | Anbieter |
|---|---|
| **ldjson** (Adapter gebaut) | Medimax, ElectronicPartner, mobilcom-debitel/freenet, ALDI TALK (Microdata) |
| **ldjson, aber Bündelpreis** | congstar (577 € Einmalpreis ohne Tarif), WinSIM (price = 1), 1&1 (Monatspreis!) |
| **json_endpunkt** (gemessen, kein Adapter) | MediaMarkt, Saturn, expert, Telekom, o2, Vodafone, klarmobil, otelo, Norma, Edeka |
| **html** | Blau, smartmobil |
| **bot** | Euronics — 403 auf **jede** Variante, auch auf die robots.txt selbst |
| **kein_hardware** | fraenk, SIMon mobile — belegt, nicht vermutet |
| **deaktiviert** | Amazon (Product Advertising API 5.0 nötig, Teil C3 wörtlich umgesetzt) |

**Vier Adapter, nicht zwanzig** (Teil F). Alle anderen stehen mit ihrem
Messergebnis und ihrem Grund in der Konfiguration und auf
`/geraete-quellen.html`.

### Der Befund, der den Zeitplan bestimmt

medimax.de und ep.de schreiben in ihrer robots.txt wörtlich:

```
Request-rate: 1/10
Crawl-delay: 10
Visit-time: 0200-0800          # only visit between 02:00 and 08:00 UTC
```

Der Wochenlauf startet **08:30 UTC** — also außerhalb. `collect/geraete/robots.py`
erzwingt das: außerhalb der Besuchszeit wird nicht abgerufen, der Grund steht
auf der Quellenseite, und — der wichtigere Teil — **die Geräte werden nicht
gealtert**. Sonst hätte jeder Tageslauf die halbe Palette dieser zwei Händler
Richtung „ausgelistet" geschoben.

Deshalb `.github/workflows/geraete.yml`, täglich 03:10 UTC. Er fasst weder
Seen-Store noch Berichte an und rendert nichts — er schreibt genau zwei
Zustandsdateien.

**Das ist die erste wirklich umgesetzte robots.txt-Prüfung dieses Repos.**
Bis heute stand die Zusage „robots.txt wird respektiert" ausgerechnet im
Rechtsbegründungsabsatz von `collect/aenderungen.py`, und im Code stand nichts
davon.

---

## Der Review, und was er gekostet hat

`diff-reviewer` hat nach D1/D2 **17 Befunde** gemeldet, drei davon kritisch.
Alle sind behoben, jeder mit einem Test, der gegen den alten Stand durchfällt:

| # | Befund | Fix |
|---|---|---|
| 1 | „Google Pixel 10 Pro **Fold**" traf den Katalogeintrag „Pixel 10 Pro". Beide beim selben Händler, 800 € auseinander → dieselbe `listung_id` → die Historie schrieb **in jedem Lauf zwei Änderungspunkte hin und zurück**, eine dauerhafte Sägezahnkurve | `_MODELLZUSATZ`: ein Modellzusatz direkt hinter dem Treffer verwirft die Zuordnung. Dazu Binnenmajuskel-Trennung („ProMax" → „Pro Max") und „+" → „plus" |
| 2 | Lauf 1 liest `color`, Lauf 2 nicht → **neue** `sku_id` → „1 neues Gerät, 1 vermutlich ausgelistet" statt einer Preissenkung | `GeraeteDB._finde_verwandten`: eine unbekannte ID wird gegen Anbieter+Gerät+Speicher abgeglichen; passt genau einer und widerspricht die Farbe nicht, ist es derselbe Artikel. Die ID wird nie umgeschrieben |
| 3 | `max_produkte` schnitt die Linkliste ab, die Seite galt trotzdem als **gelesen** → `mark_stale` alterte alles dahinter. Live: freenet liefert 83 Adressen, Deckel stand bei 60 | Abgeschnitten = nicht vollständig gelesen, plus `bilanz.gedeckelt` (keine stille Kappung) |
| 4 | Unbekannte Farbe aus dem Titel ging ganz verloren | Der Farbbericht speist sich aus den **Farbfeldern der Quellen**; im Titel wird nicht geraten. Der irreführende Test ist repariert |
| 5 | `verfuegbarkeit` ist nie `None` → die Ausfallregel griff dort nie → „lieferbar → unbekannt → lieferbar" wurde ein Lieferereignis | `_ist_ausfall()` kennt „unbekannt" als Ausfall |
| 6 | Zubehörliste verwarf echte Geräte („ohne Netzteil", „5000 mAh Akku", „AMOLED Display") | Zwei Listen: `_ZUBEHOER_IMMER` überall, `_ZUBEHOER_DAVOR` nur **vor** dem Modellnamen |
| 7 | „12 GB RAM 512 GB" ohne Trennzeichen → Speicher verloren | Die zwei Richtungen sind nicht symmetrisch: nach der Zahl zählt „RAM", davor nur „Arbeitsspeicher" |
| 8 | Katalog-`speicher` war ein harter Filter → „iPhone 17 1 TB" fiel auf `ohne-speicher` | Vorliebe statt Filter |
| 9/10 | Eintrag ohne `einstieg_url` alterte **nie**; bei mehreren Einstiegen zählte nur der zuletzt gesehene | `einstiege` als Liste + `leitseite`-Rückfall (Konvention von `promo_store`) |
| 11 | `erstpreis` mischte die zwei Preisarten → 96,6 % „Preisverfall" | `erstpreis_art` daneben, Verfall nur innerhalb einer Art |
| 12 | `preis_mit_vertrag_ab` umging die C4-Sicherung; sein erster Messpunkt ging verloren | Tarifbezug auch dort Pflicht; `_PREISFELDER` statt zwei Feldern |
| 13 | „Titanium Black" → `schwarz`, „Black Titanium" → `titan-schwarz`: zwei SKUs für eine Farbe | Bruchstück-Wächter: ein Farbwort neben dem Treffer verwirft ihn |
| 14 | `rate_limit_sekunden: "zehn"` kippte den Loader; `0` wurde still zu 2.0; unbekanntes `kind` verschwand lautlos | `_als_zahl()` + Warnung; ein Anbieter ohne Einstieg bekommt automatisch einen Grund |
| 15 | Drei Tests grün und ohne Prüfwert (der „5G"-Fall enthielt kein GB; der Wortgrenzen-Fall scheiterte schon am Zubehörfilter; der Farbfall umging den versagenden Pfad) | Alle drei repariert |
| 16 | Fünf Widersprüche zwischen YAML-Kommentar und Code (u. a. „227 Geräteadressen" — gemessen sind es 83 zum konfigurierten Muster) | Korrigiert |
| 17 | `mark_stale` nicht tagesidempotent; Refurbished kollidierte mit Neuware; freenets Container-Knoten erzeugte eine Phantom-Listung | `letzter_check`, `zustand` in der SKU-ID, `_ohne_sammelknoten()` |

### Der zweite Review — die Seite

Nach D4 hat `diff-reviewer` noch einmal **19 Befunde** gemeldet, sechs davon
schwer. Auch die sind alle behoben, jeder mit Test:

| # | Befund | Fix |
|---|---|---|
| 1 | Die Etiketten-Entzerrung hatte **keinen Deckel**: bei 60 Punkten in einer Spalte standen 31 Etiketten unter der Nulllinie, 26 außerhalb des viewBox. Der Punkt blieb richtig, das Etikett log | Deckel auf die Nulllinie; was nicht mehr passt, bekommt **kein** Etikett (Punkt und Titel bleiben) und wird in der Legende gezählt — keine stille Kappung |
| 2 | `label_kurz` kürzte auf die **ganze** Spaltenbreite, geschrieben wird aber ab der Spaltenmitte nach rechts. Bei neun Spalten lief das Etikett um Faktor zwei in die Nachbarspalte | Halbe Spalte minus Abstand. Die Formel war vom Spaltenkopf kopiert — der trägt `text-anchor="middle"`, das Etikett nicht |
| 3 | Die Legende schrieb „N **Geräte**" über eine Zahl von **Listungen** — dieselbe Seite nannte in der Kachel 3 und in der Legende 4 | „N Listungen von M Geräten bei K Anbietern" |
| 4 | „Preise abgerufen am X" war das **Berichtsdatum**. Fällt der nächtliche Lauf zwei Wochen aus, behauptet die Legende trotzdem den Berichtstag | `max(abgerufen_am)` aus den Daten |
| 5 | „Was diese Woche auffällt" hatte **kein Zeitfenster**: eine Preisänderung vom 9. März stand in der Augustausgabe — und wäre dort geblieben, bis sich der Preis wieder ändert | 14-Tage-Fenster für Bewegungen, Neuzugänge und Abgänge; das Datum steht in der Tabelle |
| 6 | Das `try/except` in `render_site` umfasste auch das **Rendern**: ein kaputter Eintrag ließ beide Seiten verschwinden, `site/` behielt die Vorwoche, und `pruefe_portal` meldete „nicht prüfbar" mit Exit 0 | Nur die Aufbereitung wird abgefangen; die Seite entsteht immer und **sagt**, wenn sie nichts zeigen kann (`geraete_view.leer()`). Kriterium 11 fällt jetzt durch, wenn die Datei ganz fehlt |
| 7 | `pruefe_zahlen` war fail-**open**: „Das iPhone kostet 999 Euro" kam erfunden durch, weil „Euro" ausgeschrieben war | Es wird wieder **jede** Zahl geprüft; die Zahlen der Eigennamen werden über `zahlen_der_namen()` ausdrücklich angemeldet |
| 8 | „neu im Regal" verglich `first_seen == heute` — der nächtliche Lauf schreibt an sechs von sieben Tagen ein Datum, das nie ein Renderdatum ist | dasselbe 14-Tage-Fenster |
| 9 | Ein Anbieter **mit Daten**, aber ohne Konfigurationszeile, fehlte still auf der Quellenseite — unter dem Satz, der verspricht, dass keiner fehlt | Eigene Zeile „nicht konfiguriert" mit Erklärung |
| 10 | „Alle beobachteten Anbieter **23**" über 21 Zeilen | Die Zahl zählt die Zeilen |
| 11 | Der Preisverfall mischte die zwei Preisarten in einer Spalte — genau das, was Teil C4 für die Karte verbietet, eine Sektion tiefer | `art` wird gerendert |
| 12 | Ein Gerät ohne Katalogeintrag erzeugte eine **namenlose Spalte** und sortierte den Slug in der Matrix nach oben | „ohne Katalogeintrag" als Hersteller, plus eine eigene Zeile unter „Lücken" |
| 13 | Eine unlesbare `geraete_db.json` sah aus wie „noch nichts gefunden" | `GeraeteDB.lesbar`, eigener Text auf der Seite |
| 14–19 | Hover trägt keinen Quelllink (ein `<title>` kann keinen tragen — er steht in der Detailzeile), `#gr-detail` wurde nie geleert, `_karte` hatte keinen Unit-Test, Kriterium 11 prüfte nur eine Ansicht, drei Dokumentationszahlen stimmten nicht (24 statt 34 Modelle ohne Marktstart), `reports_dir.parent.parent` statt `cfg.root`, `Y_MINDEST` undokumentiert | alle behoben |

---

## Zwei bewusste Abweichungen vom Auftragstext

1. **`ausgelistet` ist keine Verfügbarkeitsstufe.** Der Auftrag nennt sie in
   derselben Aufzählung wie „lieferbar" und „ausverkauft". Auslistung ist aber
   kein Zustand, den eine Produktseite meldet, sondern eine Schlussfolgerung
   aus mehreren Läufen. Wären beide dasselbe Feld, machte ein „vorübergehend
   nicht lieferbar" das Gerät zum Portfolio-Ende — und genau davor warnt
   Teil F.
2. **Die Seite steht nicht in der Navigation.** Die Veröffentlichungsschwelle
   aus CLAUDE.md §5 gilt: eine Seite wird verlinkt, wenn sie ihre Frage
   beantworten kann. Schwelle beziffert in
   `tests/test_geraete_seite.py`: **3 Anbieter, 2 Hersteller, 20 SKUs**. Der
   Test misst Navigation und Schwelle gegeneinander — laufen sie auseinander,
   wird er rot.

Dazu: **„Was diese Woche auffällt" entsteht deterministisch**, nicht per
Editor. Der Zahlenwächter (`pruefe_zahlen`, fail closed wie
`faithfulness.py`) ist trotzdem gebaut und getestet — dort würde ein Editor
später ansetzen, und dann muss die Sperre schon dastehen. Er prüft Zahlen
**mit Einheit** (€, EUR, %): eine Modellbezeichnung ist ein Name, keine
Behauptung. Der erste Anlauf verwarf deshalb einen wahren Satz, weil die 16
aus „iPhone 16 Pro Max" nicht im Datensatz stand.

---

## Im Browser gemessen

Chromium, 1440×900 und 390×844. Die Testsuite misst gegen eine kleine
Fixture, die Sichtprüfung zusätzlich gegen einen dichteren Datensatz
(14 Listungen, 3 Anbieter, 7 Hersteller):

* Umschalter Hersteller ↔ Anbieter: blendet um, lädt nicht neu ✔
* Filter Segment/Speicher/Generation: blenden aus, **verschieben die Achse
  nicht** (ein Test hält `cy` vorher/nachher gegeneinander) ✔
* Tap auf einen Punkt füllt die Detailzeile mit Modell, Speicher, Farbe,
  Preis, Anbieter, Abrufdatum und Quelllink ✔
* Kein waagerechter Überlauf auf beiden Formaten — **nach zwei Korrekturen**:
  die Bewegungs- und die Quellentabelle brauchten Rollbehälter, und
  `<code>application/ld+json</code>` verbreiterte die Seite, bis es umbrechen
  durfte ✔

---

## Offen, erst nach dem ersten echten Lauf prüfbar

1. **Der nächtliche Lauf ist noch nie gelaufen.** Im Protokoll
   (`geraeteradar-log-<run_id>`) die Zeile `Geraeteradar:` ansehen. Erwartung
   für den ersten Lauf: Medimax und ep.de liefern je bis zu 20 Produktseiten,
   freenet bis zu 120, ALDI TALK bis zu 30.
2. **Der Tageslauf muss Medimax und ep.de überspringen.** Steht dort etwas
   anderes als „ausserhalb der Besuchszeit", greift der Wächter nicht.
3. **Der Zubehörfilter ist an konstruierten Titeln gemessen, nicht an echten.**
   Nach dem ersten Lauf `bilanz.unbekannte_titel` durchsehen: stehen dort
   echte Geräte, ist der Katalog zu schmal; stehen dort Hüllen, ist der Filter
   zu eng.
4. **Der Farbbericht am Seitenfuß ist die Arbeitsliste für
   `config/farben.yaml`.** Er füllt sich erst mit echten Daten.
5. **24 von 46 Katalogmodellen haben kein belegtes Marktstartdatum.** Für sie
   gibt es keine Nachfolger-Analyse. Das ist der eine Punkt, den nur ein
   Mensch schließen kann — eine Zeile je Recherche, aus der Pressemitteilung
   des Herstellers (Verkaufsstart, nicht Ankündigung).
6. **Kriterium 11 von `pruefe_portal.py` ist derzeit „nicht prüfbar"** — mit
   leerem Bestand gibt es keine Punkte zu messen. Nach dem ersten Lauf muss es
   auf BESTANDEN springen; tut es das nicht, stimmt die Verdrahtung nicht.
