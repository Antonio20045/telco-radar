# Gerätepreise: Ist-Zustand und Stand (21.11.2026)

## Ist-Zustand (main 8d05c0aa, vor dem Aufräumen)

**Wege zu einem Preis: rund 20.** Neun Adapter, vier Nachlese-Hooks, die Tarifwelt-Stufe (Saturn/MediaMarkt), der 1&1-SIM-only-Leser, der Klick-Crawler (24 Playwright-Jobs, 960 handgepflegte URLs) und fünf `lokallauf_*`-Skripte. Alle fünf Netzbetreiber laufen absichtlich doppelt (`erfassung: adapter+klick`). Der Klick-Crawler fängt dabei dieselbe JSON-Antwort ab, die der Adapter liest. Fünfzehn `analyze/klick_*`-Module regeln danach, welcher Wert gewinnt. Preiserfassung und Zusammenführung umfassen rund 31 000 Zeilen.

| Anbieter | Lieferweg in Actions | Bündel 19.11. → 20.11. | Befund 20.11. |
|---|---|---|---|
| Vodafone | Adapter (glados-API), Klick nur Gegenprobe | 2385 → 2385 | stabil |
| o2 | Adapter + Klick, ~1760 Zeilen **hergeleitet** | 1874 → 2375 | Vertiefung endet an der Frist |
| congstar | Klick (726) vor Adapter (197) | 791 → 805 | 789 von 1776 Zeilen veraltet |
| Telekom | nur Klick, Adapter bekommt 202 | 1079 → **271** | Klick liest ~1200 Kombinationen, 271 kommen an |
| 1&1 | Adapter + Klick, 419 Zeilen **hergeleitet** | 541 → **4** | Markup geändert, Klick „#no-incentive nicht gefunden“, 17 Pflichtmodelle fehlen |
| Saturn/MediaMarkt | Tarifwelt-API (nur 24 Monate) | 166 → 159 | Gerätrate überall 0,00 (Regel 11), MediaMarkt-Suche 403 |

Die Seite füllt Lücken mit Werten bis drei Tage alt. Darum sieht 1&1 dort voll aus, obwohl heute nichts gemessen wurde.

**Gesamtkosten: drei Formeln, die sich widersprechen.** Die Seite rechnet mit `tco_kosten.kosten_ueber`. Historie, Regel 11 und die SIM-only-Referenz rechnen mit `tco_model.tco_24`. `tco_bindung` und `geraeteanteil` sind toter Code. Die Belegauswahl rechnet mit `kosten_ueber(b, 24)`. Bei allen 473 frischen 1&1-Bündeln mit 36 Monaten weichen die Formeln voneinander ab, etwa iPhone 16 128 GB, All-Net-Flat L: Seite 1539,66 €, Historie 2139,54 €. Das Feld `geraet_zuzahlung` bedeutet je nach Laufzeit Anzahlung oder Ablöse. Unbestätigter Versand zählt 0 €. Rabatte behandelt jeder Anbieter anders.

**Belege.** Der Klick-Lauf macht Screenshots und legt sie als GitHub-Releases ab (2406 Bilder). Die Seite zeigt höchstens ein Bild je Gerät, Anbieter und Tag und keines für reine HTTP-Zeilen (der größte Teil von Vodafone, Tarifwelt, Händler). Das S3-/Zeitstempel-Archiv (~1230 Zeilen) ist nicht angeschlossen.

**Läufe.** Kein Job-Timeout. Rot kommt vom Abdeckungswächter (Daten sind dann schon committet), von Rebase-Konflikten bei mehreren Läufen am selben Tag und vom Warten auf den Render-Deploy.

## Stand

### 1. Ein Weg je Anbieter

Gemessen am Geräte-Lauf 44728882384 (20.11.2026, Abrufe und Zeiten aus dem Log), am Klick-Lauf 44657948984 (`data/state/klick/*.json`) und am Bestand `data/state/geraete_tco.json` (Zeilen mit `abgerufen_am` 20.11.2026). Regel: Es bleibt der Weg, der mehr gemessene Zeilen in weniger Zeit liefert. Ein Weg fällt nur weg, wenn dadurch keine Zeile des 20.11. verloren geht.

| Anbieter | Preisweg | Zweiter Weg | Beleg 20.11.2026 |
|---|---|---|---|
| Vodafone | Adapter `vodafone_api` | Klick nur Beleg und Gegenprobe | 2385 von 2385 Zeilen aus dem Adapter (96 Abrufe). Klick: 437 Sätze, 0 ersetzt, 0 ohne Gegenstück |
| Telekom | Klick (12 Jobs, Seiten aus den Übersichtskacheln) | HTTP-Adapter `telekom_kategorie`: Barpreise ohne Vertrag (10 Geräte) und einzelne Bündel | 264 von 271 Zeilen Klick, 7 nur Adapter (Pixel 10a, Galaxy A56 EE). Adapter: 18 Abrufe in 151 s, zwei davon bekamen die Challenge-Seite |
| o2 | Adapter `o2_katalog` (seit 21.11.2026) | keiner, Klick-Jobs entfernt | Siehe unten. Lokaler Lauf 21.11.: 2233 Bündel aus 209 Abrufen in 545 s (190 gemessen, 2040 abgeleitet). Klick 21.11.: 523 Kombinationen in rund 24 700 s Jobzeit |
| congstar | **offen**: Klick-Werte, Adapter liefert jeden Schlüssel mit | – | Adapter: 920 Rohsätze in 110 s. Klick: 712 Sätze in 2177 s, alle mit Adapter-Gegenstück. Bestand: 624 Klick-, 181 Adapter-Zeilen |
| 1&1 | Klick (Tarifauswahl, #176) | keiner, Adapter entfernt | 4 Zeilen (Klick-Lauf vor #176 gestört) |
| Saturn/MediaMarkt | Tarifwelt-Stufe | keiner, Platzhalter-Adapter entfernt | 159 Zeilen, 204 Abrufe in 473 s |

Warum congstar offen bleibt:

- **congstar:** Nach der Regel bleibt der Adapter (mehr Zeilen, ein Zwanzigstel der Zeit, jede Klick-Zeile hat ein Adapter-Gegenstück). Die Umstellung ändert aber Werte und Belege von 624 Zeilen: sie tragen heute Klick-Werte mit Screenshot. Ob die Adapter-Werte gleich sind, zeigt erst ein Lauf mit Klick als reinem Beleg. Das lässt sich nicht offline nachweisen und gehört deshalb nicht in denselben Schritt.

**o2 (21.11.2026).** Belegt an den Klick-Ergebnissen der Nacht (Gerätelauf 44858465074, Klick-Lauf 44840854026) und an zwei lokalen Adapterläufen am selben Tag (ehrliche Kennung, robots.txt, 2 s Abstand):

- **Widerspruch Galaxy S25 Ultra 256 GB.** Der Klick las „…-titanium-silverblue-erneuert-details“ (Seitentitel „Samsung Galaxy S25 Ultra (gebraucht)“: 25 € Anzahlung, 36 × 24 €, „Gesamtpreis Gerät: 889,00 €“) und führte sie als Neuware; die Zusammenführung ersetzte damit die Neuware-Zeilen. Die Neuware-Seite zeigt 1 € und 36 × 30 € bzw. 24 × 45 €, „Gesamtpreis Gerät: 1.081,00 €“, wie der Adapter. Ursache: `klickliste_auto` nahm die Adresse eines erneuerten Bündels; jetzt nur Neuware.
- **Gemessen statt abgeleitet ist zu teuer.** Die Konfigurationsantwort nennt Rate, Anzahlung und Anschluss nur für den gewählten Tarif. Jeden Tarif zu wählen hieße rund 2 050 Abrufe statt rund 205, bei 3,9 s je Abruf in der Nacht rund 8 000 s, gegen 628 s Anteil und 3 000 s Sammelfrist aller Anbieter. Eine Antwort mit Tarifdetails für alle Tarife gibt o2 nicht aus (Katalog und `/e-shop/` nennen keine Tarifadresse). Die Ableitung bleibt: o2s Monatssumme je Tarif minus der gemessenen Gerätrate.
- **Die Ableitung stimmt.** 482 abgeleitete Sätze mit Klick-Messung desselben Schlüssels: Tarif, Rate und Anzahlung 482 gleich, Anschluss 439 gleich, 43 Lücke, 0 abweichend; 25 gemessene Sätze 25 gleich. Rate und Anzahlung hingen in 118 gemessenen Gerät-Speicher-Raten-Gruppen nie vom Tarif ab.
- **Zeilen.** Adapter allein 2233 Bündel, Adapter plus Klick 2241. Die 8 Zeilen nur mit Klick sind das Galaxy S25 Ultra 512 GB als Neuware aus der erneuerten Seite (o2 führt es nur erneuert, der Adapter hat es so). Vorher fehlten dem Adapter 18 weitere: Pixel 11 und Pixel 11 Pro XL (Gratis-Zugabe „mit Fitbit Charge 6“ als Zubehörbündel verworfen) und Redmi 17 (eigener Anschlusspreis 39,99 € hielt die Ableitung auf); beides ist behoben.
- **Anschlusspreis nachgemessen.** Ohne Klick wären 43 Sätze, deren Anschlusspreis der Klick gemessen hatte, die Lücke „Anschlusspreis“ (Fußnote über 0 € oder keine; beim Redmi 17 hebt die Seite den gewählten Tarif über seine Fußnote, dort belegt sie nichts). Die Gegenprobe vom 21.11. fand 65 solcher Lücken, deren Seite mit gewähltem Tarif den Betrag zeigt. Darum holt `o2_tief` nach der Vertiefung je offenem Satz die Antwort seines Tarifs (`o2_anschluss.nachmesse`), höchstens 600 s (`NACHMESSUNG_HOECHSTENS_S`, rund 150 Abrufe) und gegen die Frist; bestätigt sie Angebot, Tarif und Beträge, ist der Satz gemessen. Lokaler Lauf 21.11. ohne Höchstzeit: 568 offene Sätze, 568 Abrufe in 1 215 s (2,1 s je Abruf), alle 568 bestätigt (Tarif, Rate und Anzahlung wie abgeleitet; Anschluss 519 × 0,00 €, 242 × 39,99 € über alle gemessenen Sätze), danach keine Anschluss-Lücke mehr und alle 507 Klick-Vergleiche gleich. In der Nacht (3,9 s je Abruf) reichen 600 s für rund 150 der 568; alle bräuchten rund 2 200 s, mehr als die Sammelfrist hinter o2 frei lässt (am 21.11. rund 960 s). Ob die Frist dafür wächst, ist offen.
- **Belege.** o2-Zeilen tragen die Produktadresse mit Tarif und Raten; ein Screenshot-Job ist nicht nötig und brächte Klick-Werte wieder in die Zusammenführung.

### 2. Was entfernt ist

- Der 1&1-Adapter: `lies`, `ernte`, `lies_buendel`, die Nachlese `ergaenze_buendel` und `einsundeins_raten.py`. Es bleiben die Leser der Bereitstellungsgebühr und des Tarifnamens, die der Klick-Lauf braucht. 1&1 trägt jetzt `methode: klick`.
- Die Vorrangregel `klick_messtag.NUR_HEUTE`. Sie hat nur zwischen 1&1-Adapter und 1&1-Klick entschieden.
- Der Platzhalter `tarifwelt.lies`, der immer `[]` lieferte.
- Die ruhende Gerätestufe im Wochenlauf (`geraete_enabled: false` seit 10.08.2026): `geraete_budget`, `zusatzstufen._geraete` und sechs Kennzahlen, die immer 0 waren.
- Die fünf `scripts/lokallauf_*.py` (sie schrieben lokal in `data/`, harte Regel 1) mit dem Anbieter-Scope der SIM-only-Referenzen, den nur sie nutzten. Außerdem `scripts/spike_saturn_geraetepreis.py`.

Offline-Nachweis gegen den committeten Stand des 20.11. (Klick-Zusammenführung und TCO-Aufbau, mit und ohne Adaptersätze): Zeilen je Anbieter und Historie sind vorher und nachher gleich. Die gerenderte Website ist bis auf die Quellen-Seite (Methode und Hinweis bei 1&1) bytegleich.

### 3. Was bewusst bleibt

- **Telekom-HTTP-Adapter:** Er ist nicht tot. Er liefert täglich die Barpreise ohne Vertrag (10 Geräte) und am 20.11. sieben Bündel, die der Klick nicht hat.
- **Die Klick-Zusammenführung** (`analyze/klick_*`): Sie wird gebraucht, solange congstar und Telekom zwei Wege haben. Bei congstar gilt weiter die Preisgrenze (`ANBIETER_PREISGRENZE`).
- **Historie:** `data/state/geraete_tco_historie.jsonl` bleibt eingefroren, neue Messtage stehen im Tagesordner, `tco_historie` liest beides. Das ist eine Ablage und kein zweiter Weg; Daten werden nie gekürzt.

### 4. Übrige Punkte des Zielbilds

| Punkt | Stand |
|---|---|
| Soll gegen Ist je Kombination | offen |
| Eine Kostenformel | erledigt mit #175: `kosten_ueber` rechnet Seite, Historie, Export, Regel 11 und Belegwahl |
| Unabhängige Gegenprobe | Teil 1 in #177: zweiter Leser im Browser |
| Nachvollziehbarkeit je Preis | Teil 2 in #178: Beleg je Preis, Seite „Preisänderungen“ |
