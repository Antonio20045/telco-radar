# Gerätepreise: Ist-Zustand und Stand (20.11.2026)

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
| o2 | **offen**: Adapter und Klick | – | Adapter: 2002 Rohsätze in 2094 s, davon 172 gemessen, 1830 abgeleitet. Klick: 724 erfasst in 24 730 s Jobzeit (4 Jobs, einer gestört). Bestand: 1402 Adapter- und 973 Klick-Zeilen, 103 Klick-Sätze ohne Adapter-Gegenstück |
| congstar | **offen**: Klick-Werte, Adapter liefert jeden Schlüssel mit | – | Adapter: 920 Rohsätze in 110 s. Klick: 712 Sätze in 2177 s, alle mit Adapter-Gegenstück. Bestand: 624 Klick-, 181 Adapter-Zeilen |
| 1&1 | Klick (Tarifauswahl, #176) | keiner, Adapter entfernt | 4 Zeilen (Klick-Lauf vor #176 gestört) |
| Saturn/MediaMarkt | Tarifwelt-Stufe | keiner, Platzhalter-Adapter entfernt | 159 Zeilen, 204 Abrufe in 473 s |

Warum o2 und congstar offen bleiben:

- **o2:** Keiner der beiden Wege deckt allein die Zeilen des 20.11. Der Adapter liefert mehr Zeilen in weniger Zeit, aber 1830 davon sind abgeleitet. Der Klick misst mehr Zeilen selbst (724 gegen 172) und liefert 103 Zeilen, die der Adapter nicht hat. Ohne einen der beiden fehlen Zeilen.
- **congstar:** Nach der Regel bleibt der Adapter (mehr Zeilen, ein Zwanzigstel der Zeit, jede Klick-Zeile hat ein Adapter-Gegenstück). Die Umstellung ändert aber Werte und Belege von 624 Zeilen: sie tragen heute Klick-Werte mit Screenshot. Ob die Adapter-Werte gleich sind, zeigt erst ein Lauf mit Klick als reinem Beleg. Das lässt sich nicht offline nachweisen und gehört deshalb nicht in denselben Schritt.

### 2. Was entfernt ist

- Der 1&1-Adapter: `lies`, `ernte`, `lies_buendel`, die Nachlese `ergaenze_buendel` und `einsundeins_raten.py`. Es bleiben die Leser der Bereitstellungsgebühr und des Tarifnamens, die der Klick-Lauf braucht. 1&1 trägt jetzt `methode: klick`.
- Die Vorrangregel `klick_messtag.NUR_HEUTE`. Sie hat nur zwischen 1&1-Adapter und 1&1-Klick entschieden.
- Der Platzhalter `tarifwelt.lies`, der immer `[]` lieferte.
- Die ruhende Gerätestufe im Wochenlauf (`geraete_enabled: false` seit 10.08.2026): `geraete_budget`, `zusatzstufen._geraete` und sechs Kennzahlen, die immer 0 waren.
- Die fünf `scripts/lokallauf_*.py` (sie schrieben lokal in `data/`, harte Regel 1) mit dem Anbieter-Scope der SIM-only-Referenzen, den nur sie nutzten. Außerdem `scripts/spike_saturn_geraetepreis.py`.

Offline-Nachweis gegen den committeten Stand des 20.11. (Klick-Zusammenführung und TCO-Aufbau, mit und ohne Adaptersätze): Zeilen je Anbieter und Historie sind vorher und nachher gleich. Die gerenderte Website ist bis auf die Quellen-Seite (Methode und Hinweis bei 1&1) bytegleich.

### 3. Was bewusst bleibt

- **Telekom-HTTP-Adapter:** Er ist nicht tot. Er liefert täglich die Barpreise ohne Vertrag (10 Geräte) und am 20.11. sieben Bündel, die der Klick nicht hat.
- **Die Klick-Zusammenführung** (`analyze/klick_*`): Sie wird gebraucht, solange o2, congstar und Telekom zwei Wege haben. Bei congstar gilt weiter die Preisgrenze (`ANBIETER_PREISGRENZE`).
- **Historie:** `data/state/geraete_tco_historie.jsonl` bleibt eingefroren, neue Messtage stehen im Tagesordner, `tco_historie` liest beides. Das ist eine Ablage und kein zweiter Weg; Daten werden nie gekürzt.

### 4. Übrige Punkte des Zielbilds

| Punkt | Stand |
|---|---|
| Soll gegen Ist je Kombination | offen |
| Eine Kostenformel | erledigt mit #175: `kosten_ueber` rechnet Seite, Historie, Export, Regel 11 und Belegwahl |
| Unabhängige Gegenprobe | Teil 1 in #177: zweiter Leser im Browser |
| Nachvollziehbarkeit je Preis | Teil 2 in #178: Beleg je Preis, Seite „Preisänderungen“ |
