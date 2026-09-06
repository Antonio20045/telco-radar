# Saturn-Adapter — Produktivfassung (05.09.2026)

Auftragsgrundlage: `BRIEF_SATURN_ADAPTER.md` (Workspace-Engineer), folgt auf
den Spike vom selben Tag. Pflichtlektüre: `CLAUDE.md`,
`outputs/saturn-spike-2026-09-05.md` (§2 Struktur-Fund, §6 Empfehlung —
die Bauanleitung), `scripts/spike_saturn_geraetepreis.py` (statischer
Modus), `QUELLEN_MAP.md` §6 (Händler).

**Runde 2 (05.09.2026, spät): der UA-Befund von R1 ist behoben — siehe
Abschnitt „R2" am Ende dieser Datei.** Der Rest dieses Dokuments ist der
Bericht der ersten Runde, KORRIGIERT an der einen widerlegten Stelle (§1,
UA-Absatz) — nicht neu geschrieben, damit sichtbar bleibt, was R1 falsch
behauptet hat und was jetzt gilt.

## Ergebnis in einem Satz

Saturn liefert seit heute echte Gerätepreise per reinem HTTP-GET (kein
Playwright, robots-konform), mit einem geprüften Marktplatz-Filter — der
erste Produktivlauf hat **21 Listungen aus 6 von 17 konfigurierten
Markenseiten** erhoben, und mindestens ein Saturn-Preis steht jetzt sichtbar
in einer Händlerkarte auf `geraete.html`. **Korrektur aus R2: dieser Lauf
sendete dabei PRIMARY die Chrome-Kennung aus `config/settings.yaml:549`,
nicht die hier ursprünglich behauptete ehrliche Kennung — siehe §1 und den
R2-Abschnitt.** Die 21 Zeilen sind seither durch einen echten,
UA-belegten Lauf mit der ehrlichen Kennung ersetzt (R2, 22 Zeilen).

## 1. Der Sammler (Abnahmekriterium 1)

`src/telco_radar/collect/geraete/saturn.py`, Methode `saturn_brand`,
registriert `direkt=True` (die Markenseite IST ihre Nutzlast, keine
Produktseite wird nachgeladen — genau der Struktur-Fund des Spikes).

- **UA — WIDERLEGT in R1, KORRIGIERT in R2** (`EVAL_saturn-adapter-r1.md`
  Befund 1, Schwere 1). Diese Zeile behauptete ursprünglich, der Sammler
  sende `TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)`. Das war
  falsch: `collect.http.fetch` sendet ohne weitere Angabe PRIMARY das, was
  `http_cfg.get("user_agent", ...)` liefert — und das ist global
  `config/settings.yaml:549`, die volle Chrome-Vortäuschung. Der Adapter
  selbst tat nichts falsch (er ruft ausschließlich `saturn.lies(html, url)`
  auf fertigem HTML auf, kein eigener HTTP-Aufruf, kein Browser-Codepfad),
  aber die Nutzlast, auf der er arbeitete, kam mit der falschen Kennung
  herein. Da alle 17 Abrufe sofort 200 lieferten, wurde nicht einmal der
  ehrliche Fallback (`BOT_UA`) je gesendet — der Bericht beschrieb einen
  Codepfad, der in diesem Lauf nie erreicht wurde.
  **Seit R2 (siehe R2-Abschnitt unten) trägt `config/geraete_quellen.yaml`
  für Saturn einen PER-ANBIETER-UA-Überschreiber
  (`Anbieter.user_agent`), der genau die hier ursprünglich behauptete
  Kennung jetzt tatsächlich als Primary sendet — belegt mit einem Test auf
  der wirklich gesendeten Kopfzeile, nicht nur mit dieser Behauptung.**
- Kein Playwright im Produktionspfad — der Adapter ruft ausschließlich
  `saturn.lies(html, url)` auf reinem HTML auf, es gibt keinen
  Browser-Codepfad.
- **Extraktion über beide vom Auftrag genannten Strukturen derselben
  Antwort:**
  - `ld+json`-`ItemList` (wiederverwendet über
    `strukturdaten.produkte_aus_ldjson` — der generische Baum-Scan findet
    die verschachtelten `item`-Knoten einer `ItemList` ohne Sonderfall,
    kein eigener Regex nötig).
  - `window.__PRELOADED_STATE__` (Apollo-Cache): die einzige Quelle mit dem
    Marktplatz-Feld, siehe §2.
  - Die ld+json-Liste dient hier als **Gegenprobe**, nicht als zweite
    gleichwertige Preisquelle: jeder aus dem Apollo-Cache übernommene
    (Titel, Preis) muss sich dort wiederfinden. Bei allen bisher
    beobachteten Seiten war das lückenlos der Fall (kein einziger
    `log.warning`-Treffer in den Live-Läufen); eine Abweichung würde laut
    gemeldet, der Preis bliebe trotzdem in der Ausgabe — der Apollo-Cache
    ist die einzige Quelle mit dem Marktplatz-Feld, ihn deshalb zu
    verwerfen wäre die Gegenprobe wichtiger zu nehmen als den eigentlichen
    Pflichtfilter.
- **robots.txt eingehalten**: `/de/brand/…` ist nicht gesperrt; die zwei
  tabuisierten GraphQL-Operationen (`GetPaidBundles`/`GetFreeBundles`)
  werden nie aufgerufen — der reine HTTP-GET löst grundsätzlich keine
  GraphQL-Operation aus (Spike §5). Der generische `RobotsWaechter` prüft
  die Domain vor jedem Abruf wie bei jedem anderen Anbieter.
- **Farbe wird strukturiert aus dem Titel gelesen, nicht dem generischen
  Rückfall überlassen** (Regressionsbefund, siehe §4).

## 2. Der Marktplatz-Filter (Abnahmekriterium 2)

`isProductOfTypeMarketplace is False` — streng geprüft, ein fehlendes oder
unklares Feld (`None`) gilt NICHT als sicher (fail closed). Belegt mit
einem Test an einer echten Seite mit beiden Fällen nebeneinander:

```
tests/test_geraete_adapter_saturn.py::test_iphone17_lies_verwirft_alle_marktplatz_angebote
tests/test_geraete_adapter_saturn.py::test_iphone17_hat_zwoelf_gelistete_aber_nur_fuenf_saturn_eigene
tests/test_geraete_adapter_saturn.py::test_marktplatz_feld_fehlt_faellt_ebenfalls_durch
```

Auf `/de/brand/apple/iphone/iphone-17` (Fixture
`tests/fixtures/geraete/saturn_produkt_iphone17.html.gz`): **12 gelistete
Angebote, 7 davon Marktplatz-Drittanbieter** (technik-guenstiger 1.084,06 €,
Clevertronic 1.142,41 €, buyZOXS 1.319,37 €, Media-Reich GmbH 2.036,00 €,
Revalis 1.080–1.102 €) neben **5 Saturn-eigenen** Angeboten zu je 939,99 €.
Ohne den Filter wäre mindestens einer dieser Fremdpreise als Saturn-Preis in
den Bestand gelaufen.

Dedup (Spike §2b): dieselbe `product_id` kann unter zwei Apollo-Schlüsseln
liegen (mit/ohne Ratenplan-Unterauswahl); `_dedupe_by_product_id` behält den
vollständigeren Eintrag. Getestet in
`test_dedupe_behaelt_den_eintrag_mit_ratenplan`.

## 3. Zuordnung zum Katalog (Abnahmekriterium 3)

Farbvarianten desselben Modells+Speichers werden **alle geführt, nicht auf
ein Minimum verdichtet** — dieselbe Konvention wie jeder andere Adapter
dieses Zweigs (o2, Vodafone, congstar, Telekom): die Farbe ist Teil der
`sku_id`, jede Variante ist eine eigene, eigenständig belegte Listung. Ein
"Minimum je Modell" gäbe es nur, wenn zwei Angebote wirklich dieselbe SKU
träfen (dasselbe hat `_dedupe_by_product_id` bereits erledigt, s. o.).

Ergebnis des ersten Produktivlaufs (`data/state/geraete_preise.jsonl`, alle
mit `anbieter: saturn`, `preis_ohne_vertrag`, `quelle_url`, `datum:
2026-09-05`):

| Modell | Preis | Beleg |
|---|---|---|
| iPhone 16 Plus 128 GB Weiß/Schwarz | 939,99 € | `saturn.de/de/product/_apple-iphone-16-plus-…` |
| iPhone 16e 128 GB Schwarz | 589,00 € | `saturn.de/de/product/_apple-iphone-16e-…` |
| iPhone 17 256 GB (5 Farben) | 939,99 € | `saturn.de/de/product/_apple-iphone-17-5g-…` |
| iPhone 17 Pro 256 GB Tiefblau/Silber | **1.179,00 €** | `saturn.de/de/product/_apple-iphone-17-pro-5g-256-gb-tiefblau-dual-sim-3013587.html` |
| iPhone 17 Pro 1 TB Tiefblau | 1.589,00 € | s. o. |
| iPhone 17 Pro 512 GB Silber | 1.419,00 € | s. o. |
| iPhone Air 256 GB (3 Farben) | 909,00 € | `saturn.de/de/product/_apple-iphone-air-…` |
| iPhone Air 1 TB Himmelblau | 1.349,00 € | s. o. |
| iPhone 17e 256 GB Weiß/Hellrosa | 699,00 € | `saturn.de/de/product/_apple-iphone-17e-…` |
| iPhone 17e 512 GB Hellrosa | 949,00 € | s. o. |
| iPhone 17e 512 GB Weiß/Schwarz | 939,99 € | s. o. |

**21 Listungen insgesamt**, alle `zustand: neu`, alle `confidence: hoch`.
Die 1.179,00-€-Zeile ist die exakte Gegenprobe aus dem Spike (§1).

### Jede scheiternde/leere URL, ehrlich (Messgrenze statt Abruffehler)

Von den 17 konfigurierten Markenseiten liefern **11 strukturell
einwandfreie, aber ZU DIESEM ZEITPUNKT leere** Antworten (HTTP 200,
`window.__PRELOADED_STATE__` vorhanden und lesbar, aber keine einzige
Saturn-eigene `CofrPriceFeature`-Instanz):

| URL-Slug | Befund |
|---|---|
| `iphone-14`, `iphone-14-pro`, `iphone-14-pro-max` | 0 Angebote insgesamt — Saturn führt diese Modelle offenbar gar nicht mehr neu |
| `iphone-15`, `iphone-15-plus`, `iphone-15-pro-max` | 0 Angebote insgesamt |
| `iphone-15-pro` | 12 Angebote, **alle 12 Marktplatz** — kein Saturn-eigener Preis |
| `iphone-16-pro` | 12 Angebote, **alle 12 Marktplatz** |
| `iphone-16-plus`, `iphone-16-pro-max`, `iphone-17-pro-max` | 0 Angebote insgesamt (die Plus-Variante von iPhone 16 wird tatsächlich über die `iphone-16`-Seite mitgeführt, siehe unten) |

Kein einziger dieser elf Fälle ist ein Abruffehler — jede Seite antwortet
mit HTTP 200 und einer strukturell lesbaren Nutzlast (Fixture-Beleg für
zwei davon in `tests/fixtures/geraete/_herkunft.json`, alle 17 einzeln am
05.09.2026 mit `urllib`/`httpx` gemessen). Das ist eine Marktaussage
("Saturn verkauft dieses Modell aktuell nicht mehr neu" bzw. "nur über
Marktplatz-Drittanbieter"), keine Messgrenze der Technik.

**Ein Nebenbefund beim Messen:** die Markenseite `/de/brand/apple/iphone/
iphone-16` führt sowohl "iPhone 16" ALS AUCH "iPhone 16 Plus"-Varianten in
derselben Antwort (2 der 21 Listungen sind Plus-Varianten). Die separat
konfigurierte `iphone-16-plus`-Seite liefert dagegen leer. Das ist kein
Fehler des Adapters — beide URLs sind gültige, vom Betreiber geführte
Adressen, die Titel entscheiden über die Katalogzuordnung, nicht die
aufgerufene URL.

## 4. Ein Befund, der erst beim Ansehen der echten Daten auffiel

`geraete_model.farbe_aus_titel` (der generische Rückfall, den jeder
Adapter ohne eigenes Farbfeld nutzt) findet **"Weiß" in einem Titel nie**
— er vergleicht ASCII-gefaltete Schreibweisen ("weiss") gegen den
UNGEFALTETEN Titeltext, und `"weiss" != "Weiß"` als Zeichenkette. Ein Test
hat das an echten Daten gezeigt: von fünf Farbvarianten auf
`/de/brand/apple/iphone/iphone-17` wurde "Weiß" als einzige auf
`apple-iphone-17-256gb-ohne-farbe` statt auf die Farbe abgebildet.

Das ist ein vorbestehender, systemweiter Befund in `geraete_model.py`
(nicht neu und nicht Saturn-spezifisch — er würde jeden Adapter treffen,
der die Farbe dem Titel-Rückfall überlässt und dessen Titel "ß" trägt),
und er wurde **nicht dort** repariert: das ist gemeinsamer, stark
getesteter Code, und ihn zu ändern ist ein eigener Auftrag mit eigener
Nachmessung über alle bestehenden Adapter. Stattdessen liest `saturn.py`
die Farbe selbst aus einer festen Titelposition (zwischen der
Speicherangabe und einem optionalen SIM-Zusatz) und übergibt sie
STRUKTURIERT — dieselbe Rangfolge, die jeder Adapter mit eigenem Farbfeld
schon befolgt (Teil C1: strukturierte Daten schlagen Textextraktion).
`normalisiere_farbe` faltet danach korrekt, weil sie mit `normalisiere()`
arbeitet statt mit dem Titel-Regex. Getestet in
`test_farbe_mit_umlaut_wird_richtig_gelesen` (belegt beide Verhalten
nebeneinander: der generische Rückfall bleibt leer, der Adapter liest
richtig).

**Arbeitsliste für `config/farben.yaml`** (aus dem Lauf-Protokoll, unbekannte
Schreibweisen): Hellrosa, Himmelblau, Lichtgold, Nebelblau, Tiefblau,
Wolkenweiß. Keine davon verursacht eine falsche Zuordnung — eine unbekannte
Farbe bleibt sichtbar (`farbe_normalisiert: None`), sie wird nur nicht auf
eine Grundfarbe verdichtet.

## 5. Ein zweiter Befund, erst beim Ansehen der Live-Seite

Der erste gerenderte Stand zeigte für Modelle mit Saturn-Daten (z. B.
iPhone 17 Pro 256 GB) **gleichzeitig** eine echte Saturn-Linie im
Zeitreihen-Graph des TCO-Reiters UND den Satz "Saturn — Beschaffung läuft
seit 5. September 2026" in der Legende direkt darunter — zwei
widersprüchliche Antworten auf dieselbe Frage. Ursache: die Vorlage führte
Amazon/Expert/Saturn seit A-R3 hart codiert als "Händler ohne Tarifbündel,
Beschaffung läuft" (`haendlerkarte()`), unabhängig davon, ob inzwischen
echte Daten vorliegen.

Behoben in `report/geraete_tco_view.py`
(`HAENDLER_OHNE_BUENDEL`/`_haendler_ohne_buendel_preise`) und der Vorlage:
ein Händler ohne Tarifbündel bekommt für ein Modell die reale
Preiskarte (`haendlerpreiskarte`, neue Vorlage-Macro) und fällt aus der
"Beschaffung läuft"-Legende, SOBALD für dieses konkrete Modell ein
NEU-Preis erhoben ist — Amazon und Expert bleiben unverändert bei ihrer
Auskunft, solange sie keine Daten liefern. Eine einzige Zahl
(`modell["haendler_ohne_buendel"]`) entscheidet beide Stellen, damit sie
nicht auseinanderlaufen können. Live geprüft: iPhone 17 Pro 256 GB zeigt
jetzt die Saturn-Karte mit 1.179,00 € und Beleglink, iPhone 15 128 GB (ohne
Saturn-Daten) zeigt weiterhin unverändert die "Beschaffung läuft"-Karte.

Acht neue Tests in `tests/test_geraete_haendler_ohne_buendel.py` (reine
Funktion + End-to-End über `geraete_tco_view.aufbereiten()`).

**Bewusste Grenze:** die TCO-Tafel zeigt ein Modell überhaupt nur, wenn
mindestens EIN Tarifbündel eines Netzbetreibers dafür existiert
(`geraete_tco_karten.modelle()`, Dokstring: "Alle Modelle mit mindestens
einem Bündel"). Ein Modell, das AUSSCHLIESSLICH Saturn führt und kein
Netzbetreiber, bekommt deshalb weiterhin keinen Platz im TCO-Reiter — das
ist eine bestehende Architekturgrenze der TCO-Tafel (sie beantwortet "was
kostet es mit Tarif", nicht "was kostet das Gerät irgendwo"), keine Lücke
dieses Adapters. Der Gerätekatalog-Reiter (Katalogtabelle,
`data-s-anbieter="Saturn"`) und die Preishistorie zeigen jede Saturn-Listung
unabhängig davon, siehe §6.

## 6. Sichtprobe auf `site/geraete.html` (Abnahmekriterium 5)

Vier unabhängige Stellen zeigen jetzt echte Saturn-Preise:

1. **TCO-Reiter, Händlerkarte** — Modell "Apple iPhone 17 Pro 256 GB":
   `<article class="gr-kkarte gr-kkarte--haendler" data-anbieter="Saturn">
   … <b>Gerätepreis</b> <span>1.179,00 €</span> … Beleg Saturn</article>`,
   Link `https://www.saturn.de/de/product/_apple-iphone-17-pro-5g-256-gb-
   silber-dual-sim-3013585.html` (Silber, ebenfalls 1.179,00 €).
2. **TCO-Reiter, Zeitreihen-Legende**: `Saturn · 05.09.2026: 939,99 €` als
   Startpunkt einer neuen Serie (mehrere Modelle).
3. **Gerätekatalog-Reiter**: 21 Zeilen mit `data-s-anbieter="Saturn"`,
   Modellfilter "Saturn" wählbar.
4. **CSV-Exporte** (`site/exporte/geraete-aktuell.csv`,
   `geraete-historie.csv`): je 21 Saturn-Zeilen.

`site/geraete.html` und `site/geraete-quellen.html` sind committet.
`site/data/keyword-index.json` wurde nach jedem Rendern auf den committeten
Stand zurückgesetzt (`git checkout --`, Datums-Zeitbombe gegen
`date.today()`).

## 7. Suite (Abnahmekriterium 4)

```
2 failed, 2740 passed, 14 skipped
```

Dieselben zwei roten Tests wie im Maßstab des Briefs, unverändert und
vorbestehend:

```
FAILED tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung
FAILED tests/test_promo_seite.py::test_der_leere_screenshot_wird_nicht_ausgeliefert
```

2740 statt ~2717 bestandene Tests, weil 23 neue dazugekommen sind (15 in
`tests/test_geraete_adapter_saturn.py`, 8 in
`tests/test_geraete_haendler_ohne_buendel.py`). `scripts/pruefe_portal.py
--site site` zusätzlich gelaufen: **16 bestanden, 1 durchgefallen** (8b,
"Leere Bilder ausgeliefert" — vorbestehend und mit Saturn nicht verwandt,
siehe CLAUDE.md §6). Kriterium 11b (Reiterhöhen): `tco 2259, katalog 1873
px` — beide deutlich unter dem 3000-px-Budget, die neue Händlerkarte hat
den Rahmen nicht gesprengt.

## 8. `scripts/lokallauf_saturn.py` (Abnahmekriterium 7)

Nach dem Muster von `scripts/lokallauf_telekom.py`: fragt NUR den Anbieter
"Saturn" ab (alle 17 Markenseiten), rendert nichts, committet nichts.

```bash
PYTHONPATH=src /opt/homebrew/bin/python3 scripts/lokallauf_saturn.py --frist 600
```

Realer Lauf am 05.09.2026, 17:08–17:11 UTC (161,8 s): 17 Seiten, alle HTTP
200, 21 Listungen (21 neu), 0 gealtert, Bestand danach 594 Geräte-Listungen
insgesamt. Protokollzeile:

```
Geraeteradar: 1 Anbieter abgefragt, 21 Listungen (21 neu), 21 Preispunkte,
0 gealtert, Bestand 594, 161.8s
```

Nach dem Lauf von Hand rendern und committen (das Skript tut beides
bewusst nicht):

```bash
PYTHONPATH=src /opt/homebrew/bin/python3 -c "
from pathlib import Path
from telco_radar.config import load_config
from telco_radar.report.html import render_site
cfg = load_config(Path('.'))
render_site(Path('site'), Path('data/reports'), cfg)
"
git checkout -- site/data/keyword-index.json
```

## 9. Empfehlung: Wiederholungsrhythmus

**Täglich, im bestehenden Geräteradar-Nebenzweig (`.github/workflows/
geraete.yml`), nicht im Wochenlauf.** Begründung:

- Saturn ist ein Händler ohne Tarifbindung — seine Preise ändern sich
  unabhängig vom zweiwöchentlichen Wochenlauf-Rhythmus, genau wie die
  anderen `typ: handel`-Anbieter (Medimax, ElectronicPartner), die bereits
  im nächtlichen Geräte-Job laufen.
- **Zeitbudget:** 17 Seiten × 10 s Mindestabstand (Cloudflare-Vorsicht,
  keine gemessene Crawl-delay-Pflicht, aber ein Netzbetreiber-Host verdient
  dieselbe Zurückhaltung wie bei Telekom) + Antwortzeit ≈ 160–200 s. Das
  passt bequem in das bestehende 900-s-Budget des nächtlichen Laufs, auch
  neben den anderen ~20 konfigurierten Anbietern
  (`_MINDEST_JE_ANBIETER = 120 s` reserviert das automatisch).
- **Kein Besuchsfenster nötig** — anders als medimax.de/ep.de nennt
  Saturns robots.txt keine `Visit-time`, der Anbieter kann also auch im
  Wochenlauf-Zeitfenster laufen, sollte er später doch dorthin wandern;
  die Empfehlung für den nächtlichen Job ist reine Lastverteilung, keine
  robots-Pflicht.
- **Elf der 17 Seiten liefern heute leer** — das ist eine Marktaussage,
  keine Fehlfunktion (§3). Ein täglicher Rhythmus fängt trotzdem am
  schnellsten auf, sobald Saturn ein Modell wieder neu listet oder ein
  Marktplatz-Angebot durch ein Saturn-eigenes ersetzt wird.

## Offen

1. **Nur 6 von 17 Markenseiten liefern heute Daten** (§3). Das ist
   gemessen, nicht behoben — nach ein paar Läufen beobachten, ob sich das
   Bild ändert (Saturn könnte iPhone 14/15 wieder neu listen, oder die
   Marktplatz-Angebote zu iPhone 15 Pro/16 Pro könnten von einem
   Saturn-eigenen abgelöst werden).
2. **`geraete_model.farba_aus_titel`s Umlaut-Lücke ist vorbestehend und
   NICHT repariert** (§4) — sie betrifft potenziell jeden Adapter ohne
   eigenes Farbfeld. Ein eigener Auftrag, keine Nebenwirkung dieses Tickets.
3. **Weitere Marken (Samsung, Google, Xiaomi, …) sind nicht angebunden.**
   Der Auftrag begrenzt den Start-Scope auf die Apple-iPhone-Serien des
   Katalogs; das URL-Muster (`/de/brand/<hersteller>/<serie>/<modell>`)
   ist herstellerübergreifend gleich aufgebaut, aber jede weitere Marke
   braucht eine eigene Messung der Slug-Form (z. B. ob Samsungs Serie
   "galaxy-s26" oder "s26" heißt) — nicht Teil dieses Auftrags.
4. **`config/farben.yaml` fehlen sechs Schreibweisen** (§4) — reine
   Datenpflege, keine Korrektheitsfrage.
5. **Die TCO-Tafel zeigt kein Modell, das AUSSCHLIESSLICH Saturn führt**
   (§5) — bestehende Architekturgrenze der Tafel, bewusst nicht angefasst.

---

## R2 — die ehrliche Kennung als Primary, Daten neu erhoben (05.09.2026, spät)

Auftragsgrundlage: `BRIEF_SATURN_ADAPTER_R2.md` (Workspace-Engineer), folgt
auf `EVAL_saturn-adapter-r1.md` (Urteil **NEEDS_WORK**).

### Der Urteilsbezug

Der Evaluator hat R1 in genau einem Punkt widerlegt (Befund 1, Schwere 1):
„Die Erhebung lief mit Chrome-Impersonating-UA. E4-Verstoß im
Produktionspfad des Saturn-Adapters; die 21 committeten Preiszeilen stammen
aus diesen Abrufen." Eigene Ausführung des Evaluators
(`load_config()` + `http_cfg.get('user_agent', BROWSER_UA)`): Primary =
`config/settings.yaml:549`, volle Chrome-Vortäuschung, für alle 17
Saturn-Abrufe. Kriterien 2–7 (Marktplatz-Filter, Katalogzuordnung, Suite,
Artefakt, Lokallauf) waren BELEGT und sind von diesem Befund nicht
betroffen — R2 rührt ausschließlich den UA-Punkt an.

### Der Mechanismus: per-Anbieter-UA-Override

`settings.yaml` bleibt unverändert (Zeile 549 unangetastet — Entscheidung
E-1 liegt weiterhin bei Antonio, nicht bei diesem Ticket). Stattdessen ein
Überschreiber, der NUR Saturn betrifft:

| Wo | Was |
|---|---|
| `config/geraete_quellen.yaml`, Saturn-Eintrag | neues Feld `user_agent: "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"` |
| `geraete_config.Anbieter` | neues Feld `user_agent: str = ""`, geladen wie `kopfzeilen` — leer heißt „globales `http_cfg` gilt wie überall sonst" |
| `collect.geraete.sammle_anbieter` | reicht `anbieter.user_agent` NUR an `hole()` weiter, wenn der Anbieter ihn setzt — bestehende `hole(url)`/`hole(url, kopfzeilen=…)`-Testattrappen bleiben für jeden anderen Anbieter gültig |
| `geraete_pipeline._hole_fabrik` | baut aus dem Überschreiber ein EIGENES `http_cfg` NUR für diesen Aufruf (`{**http_cfg, "user_agent": user_agent}`); `fetch()` selbst wird unverändert aufgerufen, sieht also nichts Neues |
| `collect.http.fetch`/`_ist_ehrliche_kennung` | erkennt JEDE `TelcoRadar/1.0`-Kennung als ehrlich (Präfixvergleich statt Gleichheitsvergleich mit der einen alten `BOT_UA`-Zeichenkette) — sonst bekäme die neue Kennung Chrome-Client-Hints (Widerspruch in sich) und der Fallback wäre die alte `BOT_UA` statt `BROWSER_UA` |

Die robots.txt-Abrufe laufen bewusst weiter über das GLOBALE `http_cfg`
(dieselbe Bewusstheit wie beim bestehenden `kopfzeilen`-Mechanismus,
Modulkopf von `collect/geraete/__init__.py`) — die Gruppenzuordnung einer
robots.txt hängt an unserer erklärten Identität (`TelcoRadar/1.0`, siehe
`geraete_quellen.yaml`), nicht an der Kopfzeile des Abrufs, der die Datei
holt.

### Der Test, der den UA belegt (Abnahmekriterium 1)

Drei neue Tests in `tests/test_geraete_adapter_saturn.py`, alle auf der
WIRKLICH GESENDETEN httpx-Kopfzeile, nicht auf der Behauptung des Codes:

```
test_saturn_ua_ist_primary_auch_bei_globaler_chrome_konfiguration
test_ohne_per_anbieter_override_bleibt_das_globale_http_cfg_primary
test_saturn_anbieter_reicht_seine_ehrliche_kennung_bis_zur_kopfzeile
```

Der erste ist der R1-Fall wörtlich nachgebaut: `http_cfg = {"user_agent":
<Chrome-UA aus R1>}` (global, wie aus `config/settings.yaml`), `httpx.get`
gestubbt und die Kopfzeilen des einzigen Abrufs mitgeschnitten. Ergebnis:
`headers["User-Agent"] == "TelcoRadar/1.0
(+https://telco-radar.onrender.com/ueber)"` — als PRIMARY, ein 200er löst
keinen zweiten Versuch aus. Der zweite ist die Gegenprobe: OHNE Override
bleibt das globale `http_cfg` Primary (Fallback-Architektur unangetastet).
Der dritte fährt den ganzen Weg von der ausgelieferten Konfiguration bis
zur Kopfzeile, ohne Testattrappe dazwischen (`sammle_anbieter` mit dem
echten Saturn-Anbieter): robots.txt bekommt die globale Chrome-Kennung
(bewusst, s. o.), die Markenseite die ehrliche.

Zusätzlich hält `test_landet_als_listung_im_bestand` (überarbeitet) und
`test_die_ausgelieferte_konfiguration_haelt_was_der_hinweis_verspricht`
(ergänzt) die Wiring auf der Ebene von `sammle_anbieter` bzw. der
ausgelieferten Konfiguration fest.

### Die Daten neu erhoben (Abnahmekriterium 2)

`scripts/lokallauf_saturn.py --frist 600`, unverändert (das Skript
brauchte keine Änderung — der Überschreiber sitzt in der Konfiguration,
nicht im Skript), lokal am 05.09.2026, 18:17–18:19 UTC (161,2 s) erneut
gelaufen. Vorher: die 21 R1-Zeilen aus `geraete_db.json`/
`geraete_preise.jsonl` sowie der Saturn-Eintrag der Anbieter-Bilanz per
Hand entfernt (`GeraeteDB`/`Preishistorie`, keine Handbearbeitung der
JSON-Struktur — damit bleibt das Dateiformat exakt das, das die Klassen
selbst schreiben würden). Alle 17 konfigurierten Markenseiten antworteten
erneut mit HTTP 200 — **keine Zeile musste als Messgrenze entfernt
werden**, weil keine URL mit der ehrlichen Kennung scheiterte:

```
18:17:12 GET /robots.txt                200   18:18:32 GET .../iphone-16-plus     200
18:17:12 GET .../iphone-14              200   18:18:45 GET .../iphone-16-pro      200
18:17:22 GET .../iphone-14-pro          200   18:18:53 GET .../iphone-16-pro-max  200
18:17:32 GET .../iphone-14-pro-max      200   18:19:03 GET .../iphone-16e         200
18:17:42 GET .../iphone-15              200   18:19:13 GET .../iphone-17          200
18:17:52 GET .../iphone-15-plus         200   18:19:23 GET .../iphone-17-pro      200
18:18:03 GET .../iphone-15-pro          200   18:19:32 GET .../iphone-17-pro-max  200
18:18:12 GET .../iphone-15-pro-max      200   18:19:43 GET .../iphone-air         200
18:18:22 GET .../iphone-16              200   18:19:53 GET .../iphone-17e         200
```

(alle Zeitangaben UTC, 05.09.2026; Basis `https://www.saturn.de`, jeweils
gefolgt von der genannten `/de/brand/apple/iphone/...`-Adresse)

Protokollzeile:

```
Geraeteradar: 1 Anbieter abgefragt, 22 Listungen (22 neu), 22 Preispunkte,
0 gealtert, Bestand 595, 161.2s
```

**22 statt 21 Zeilen — beides ist ein ehrliches Ergebnis (Abnahmekriterium
2), keine Diskrepanz zu erklären:** dieselben **6 von 17** Markenseiten
liefern Saturn-eigene Preise (iPhone 16/16e/17/17 Pro/Air/17e, unverändert
gegenüber R1), und **alle 21 R1-Preise stimmen mit diesem Lauf exakt
überein** (gegengeprüft, siehe unten) — plus EINE neue Variante, die
zwischen dem R1- und dem R2-Lauf auf der `iphone-16`-Markenseite
hinzugekommen ist:

| Modell | Preis | Beleg |
|---|---|---|
| iPhone 16 128 GB Weiß **(neu seit R1)** | 839,99 € | `saturn.de/de/product/_apple-iphone-16-5g-128-gb-weiss-…` |
| iPhone 16 Plus 128 GB Weiß/Schwarz | 939,99 € | unverändert |
| iPhone 16e 128 GB Schwarz | 589,00 € | unverändert |
| iPhone 17 256 GB (5 Farben) | 939,99 € | unverändert |
| iPhone 17 Pro 256 GB Tiefblau/Silber | 1.179,00 € | unverändert |
| iPhone 17 Pro 1 TB Tiefblau | 1.589,00 € | unverändert |
| iPhone 17 Pro 512 GB Silber | 1.419,00 € | unverändert |
| iPhone Air 256 GB (3 Farben) | 909,00 € | unverändert |
| iPhone Air 1 TB Himmelblau | 1.349,00 € | unverändert |
| iPhone 17e 256 GB Weiß/Hellrosa | 699,00 € | unverändert |
| iPhone 17e 512 GB Hellrosa | 949,00 € | unverändert |
| iPhone 17e 512 GB Weiß/Schwarz | 939,99 € | unverändert |

Die elf strukturell leeren bzw. rein marktplatzgetragenen Markenseiten aus
§3 sind gegen zwei Stichproben (`iphone-15-pro`, `iphone-16-pro`) mit der
ehrlichen Kennung NACHGEMESSEN worden: unverändert 12 gelistete Angebote,
0 Saturn-eigene, 12 Marktplatz — dieselbe Marktaussage wie in R1, nicht
UA-abhängig.

`git diff` gegen den R1-Commit zeigt genau diesen Befund: 21 identische
Zeilen (Inhalt UND Position unverändert, weil `Preishistorie`/`GeraeteDB`
in derselben Reihenfolge neu schreiben) plus eine neue — kein
Preis hat sich zwischen den beiden Läufen verschoben.

### settings.yaml (Abnahmekriterium 3)

```
$ git diff f63691b -- config/settings.yaml   # f63691b = R1-Commit
(kein Ergebnis - die Datei ist unveraendert)
```

Zeile 549 trägt weiterhin die Chrome-Kennung; E-1 bleibt offen und bei
Antonio.

### Suite (Abnahmekriterium 4)

```
2 failed, 2743 passed, 14 skipped
```

Dieselben zwei vorbestehenden Roten wie im R1-Maßstab
(`tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung`,
`tests/test_promo_seite.py::test_der_leere_screenshot_wird_nicht_ausgeliefert`)
— unverändert, keine neuen. 2743 statt 2740, weil drei neue Tests
dazugekommen sind (siehe oben).

### Site-Artefakt (Abnahmekriterium 6)

`render_site()` erneut gegen den aktualisierten Bestand gelaufen,
`site/geraete.html` (und die abhängigen Seiten) neu committet;
`site/data/keyword-index.json` per `git checkout --` auf den committeten
Stand zurückgesetzt (Datums-Zeitbombe gegen `date.today()`, dieselbe
Regel wie in R1 §6).

### Offen (unverändert aus R1, durch R2 nicht berührt)

Siehe Abschnitt „Offen" oben, Punkte 1–5 — R2 hat an keinem davon etwas
geändert. Punkt 1 („nur 6 von 17 Markenseiten liefern heute Daten") gilt
mit R2 unverändert weiter; die 22. Zeile ist eine neue VARIANTE derselben
6 Seiten, keine siebte liefernde Seite.
