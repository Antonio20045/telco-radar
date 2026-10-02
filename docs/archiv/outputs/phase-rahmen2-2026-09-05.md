# BRIEF_RAHMEN2 (05.09.2026) — zwei Restbefunde von Seneca, abgeschlossen

Auftragsgrundlage: `BRIEF_RAHMEN2.md` (PM, 05.09.2026), zwei kleine
Restbefunde auf der Geräteseite nach dem Rahmen-Umzug (BRIEF_RAHMEN). Beide
behoben, sonst nichts angefasst.

## Befund 1: Gerätepreis statt TCO-Bündelzahl als Leitzahl

**Der Widerspruch:** die Überschrift fragt „Dieses Gerät — wo kaufe ich es
am günstigsten?", der Zeitreihen-Graph darüber zeigt Gerätepreise — die
Karten darunter führten mit der TCO-Bündelzahl (`TCO-36 1.619,64 €` /
`1.794,76 €` / `TCO-24 1.918,70 €`). A-R5 verlangt den reinen Gerätepreis
als Leitzahl, die Tarifsicht als zweite Größe.

**Umgesetzt** (`report/geraete_tco_karten.py`, neue Funktion
`_geraetepreis()`): dieselbe Regel wie im Zeitreihen-Graph — zuerst der
EIGENE Barpreis ohne Vertrag (ein fremder Marktpreis zählt nicht, das wäre
ein anderes Angebot), sonst bei einer o2-Ratenfinanzierung Zuzahlung plus
Ratensumme. Trägt keins von beiden etwas (1&1: ein Buendelmonatspreis für
Tarif und Gerät zusammen, § 13.2 — eine Aufteilung wäre unsere Erfindung),
bleibt die Karte ehrlich bei ihrer TCO-Zahl.

Gerechnet am Vorgabemodell (iPhone 17 Pro 256 GB, `data/state/geraete_tco.json`):

| Anbieter | Vorher (Leitzahl) | Nachher groß | Nachher klein |
|---|---|---|---|
| o2 | TCO-36 1.794,76 € | **1.315,00 €** (Zuzahlung+Ratensumme) | mit Tarif: TCO-36 1.794,76 € |
| Vodafone (Referenz) | TCO-24 1.918,70 € | **1.199,90 €** (eigener Barpreis) | mit Tarif: TCO-24 1.918,70 € |
| 1&1 | TCO-36 1.619,64 € | *(kein Geräteanteil ausgewiesen)* | TCO-36 1.619,64 € bleibt Leitzahl |
| Telekom | – (Leergrund) | unverändert (Leergrund) | – |

Über den ganzen Bestand: **91 Karten mit Geräteanteil** (jetzt mit
Gerätepreis-Leitzahl), **35 ohne** (Telekom-Leergründe + 1&1). Gegenprobe:
auf keiner Karte ist der Gerätepreis größer als ihre TCO — sonst wäre es
die falsche der zwei Zahlen.

**Kartenkopf** (`templates/geraete.html.j2`, `tcokarte`-Makro): mit
Gerätepreis führt `<b>Gerätepreis</b> <span>…</span>` groß, `mit Tarif:
<b>TCO-N</b> …` klein (`.gr-kk-zweit`), Ø/Monat rutscht auf eine dritte,
noch kleinere Zeile (neue Klasse `.gr-kk-omonat`, dieselbe Stimme wie
`.gr-kk-basis`). Ohne Gerätepreis bleibt die alte Form (TCO groß, Ø/Monat
klein) — unverändert für Telekom und 1&1.

**Die Vodafone-Referenzkarte trägt jetzt ebenfalls einen Gerätepreis**
(`ref["geraet_betrag"]`, ihr eigener Barpreis — einer der zwei gemessenen
Summanden, aus denen die Näherung ihre TCO rechnet). Kommt die Referenz
stattdessen aus einem echten Vodafone-Bündel (`_referenz_aus_buendel`),
übernimmt sie dessen bereits berechneten Gerätepreis — kein zweiter
Rechenweg für dieselbe Zahl.

**Die Tabelle „Alle Bündel als Tabelle"** (unter G1) trägt jetzt eine
eigene Spalte **„Gerätepreis"** vor der TCO-Spalte (`nicht ausgewiesen` als
benannte Lücke bei 1&1-Zeilen) — dieselbe Reihenfolge wie auf der Karte
darüber.

## Befund 2: doppelte „Wie gerechnet?"-Aufklappung

Die seitenweite Aufklappung `#gr-tco-wie` (über der Kennzahlenreihe/den
Preis-Alarm-Chips) ist **ersatzlos gestrichen**; die je Modell bestehende
Aufklappung unter dem Zeitreihen-Graph (Chart-Details, `zr.linien`) bleibt
unverändert — sie ist beim Graphen richtig platziert und trägt ihr eigenes
Thema (die Linien dieses Geräts), keine allgemeine Methodik.

Gemessen an der ausgelieferten Seite: `grep -c "gr-tco-wie"` → **0**,
`grep -c '<summary>Wie gerechnet?</summary>'` → **56** (eine je Modellblock
mit Zeitreihen-Daten; die übrigen ~3 der 59 Modelle haben noch keine
zweite Preismessung und zeigen dort ihren eigenen Leerzustand-Satz statt
der Aufklappung — kein Widerspruch zum „genau eine je Block", weil dort
gar kein Graph und damit auch kein „Wie gerechnet?" existiert).

## Tests

- `tests/test_geraete_tco_hauptansicht.py`: neuer Test
  `test_der_geraetepreis_fuehrt_wo_er_ausgewiesen_ist` gegen den ECHTEN
  Bestand (`data/state/geraete_tco.json` + `geraete_db.json` +
  `tarife.jsonl`) — prüft die drei Fälle (o2, Vodafone-Referenz, 1&1) und
  eine Gegenprobe über den ganzen Bestand (Gerätepreis nie größer als TCO,
  mindestens zwei echte Treffer).
- `tests/test_geraete_tco_terminologie.py`: zwei bestehende Tests an die
  neue Kartenform angepasst (`.gr-kk-leit b` == „Gerätepreis" statt
  „TCO-…", neue `.gr-kk-zweit`-Zeile „mit Tarif: …"; Tabellenkopf-Index auf
  die neue Spalte verschoben).
- `tests/test_geraete_rahmen.py`: `test_die_seitenueberschrift_traegt_
  genau_eine_wie_gerechnet_aufklappung` ersetzt durch
  `test_wie_gerechnet_steht_hoechstens_einmal_je_modellblock` (prüft
  `#gr-tco-wie` ist weg, jeder `.gr-tmodell`-Block trägt höchstens/genau
  eine „Wie gerechnet?"-Aufklappung, keine außerhalb der Modellblöcke);
  `test_der_waechter_prueft_wirklich_etwas` um die jetzt nicht mehr
  vorkommende Zusicherung zu „Gerechnet wird" gekürzt (der Satz stand nur
  im gestrichenen Block).

**Suite:** `PYTHONPATH=src /opt/homebrew/bin/python3 -m pytest -q` →
**2 failed / 2697 passed / 14 skipped** (235,6 s) — die zwei Fehlschläge
sind die vorbestehenden Promo-Screenshot-Tests
(`test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung`,
`::test_der_leere_screenshot_wird_nicht_ausgeliefert`), unverändert
gegenüber dem Maßstab aus dem Auftrag. Kein neuer roter Test.

## Site

`render_site(site, reports, load_config(root))` neu ausgeführt.
`git diff --stat`: `site/geraete.html` (911 Zeilen, alle Kartenblöcke und
die Tabelle betroffen — erwartet bei 59 Modellen), `site/style.css` (7
Zeilen, die neue `.gr-kk-omonat`-Regel). `site/data/keyword-index.json`
(reine Datums-Zeitbombe, `stand` gegen `date.today()`) mit `git checkout --`
zurückgesetzt, kein Inhalt geändert.

## Commits

1. `352dad8` — Code + Tests (beide Befunde).
2. `897a13c` — gerenderte Site.

Branch `openclaw/ticket-rahmen2`, nicht gemerged — PM merged nach
Evaluator-PASS. A5.5/E-2, CI und `llm.py` unberührt.

## R3 (05.09.2026, klein): die drei graphlosen Blöcke bekommen ihre Aufklappung

Auftragsgrundlage: `BRIEF_RAHMEN2_R3.md`. Der Evaluator fand 3 von 59
Modellblöcken **ohne** „Wie gerechnet?"-Aufklappung —
`samsung-galaxy-s24-ultra-512`, `nothing-phone-4a-pro-128`,
`apple-iphone-16-pro-max-256`. Ursache: die Aufklappung hing im Template
am Zeitreihen-Graph (`{% if zr.hat_daten %}`); diesen drei Geräten fehlt
jede Preishistorie (SKU ohne Listung, über den Katalog nachgetragen,
F-R2-3), also `zr.hat_daten == False`, also gar keine Aufklappung — obwohl
ihre Karten Zahlen tragen.

**Umgesetzt** (`templates/geraete.html.j2`): im `{% else %}`-Zweig des
Zeitreihen-Blocks bleibt der Platzhaltersatz „Für dieses Gerät liegt noch
keine Preishistorie vor …" unverändert stehen; zusätzlich steht **nach dem
`.gr-karten`-Block** (statt nach dem Graphen) eine zweite `{% if not
zr.hat_daten %}`-geschützte `details.gr-auf`-Aufklappung mit
`<summary>Wie gerechnet?</summary>`. Inhalt: eine Zeile je belastbarer
Karte dieses Blocks — Anbieter · Monate (die gerechnete Bindung, da es
noch keine gemessenen Preispunkte gibt) · Abrufdatum (`date_de`). Kein
CSS geändert — `gr-auf`/`gr-tposten` sind dieselben Klassen wie bei der
graphtragenden Fassung.

**Tests** (`tests/test_geraete_tco_zustand.py`, `tests/test_geraete_rahmen.py`):
die gemeinsame Fixture `_baue()` bekommt einen neuen, standardmäßig
ausgeschalteten Parameter `graphloses_modell` (kein bestehender Aufrufer
ändert sein Ergebnis). Eingeschaltet hängt sie ein zweites Buendel an
(`SKU_GRAPHLOS = apple-iphone-16-pro-max-256gb-schwarz` — derselbe Slug
wie einer der drei echten Fälle) **ohne** Listung in `geraete_db.json` und
**ohne** Preishistorie-Zeile — genau der reale Mechanismus (F-R2-3:
`geraet_aus_sku()` löst die SKU über den Katalog auf, `belastbar` hängt
nur an der Buendel-Rechnung, nicht an der Listung).
`test_wie_gerechnet_steht_hoechstens_einmal_je_modellblock` läuft jetzt
mit `graphloses_modell=True` — die Schleife über alle `.gr-tmodell`-Blöcke
prüft `== 1` seitdem für BEIDE Blockarten. Neuer Test
`test_ein_block_ohne_graph_traegt_trotzdem_eine_wie_gerechnet_aufklappung`:
sucht gezielt den graphlosen Block (`figure.gr-grafik--zeitreihe` fehlt),
prüft genau eine Aufklappung und dass sie NACH `.gr-karten` steht (nicht
davor, wie es beim Graphen der Fall wäre).

**Gegenprobe am echten Bestand:** `grep -c '<summary>Wie gerechnet?</summary>'`
→ **59** (vorher 56), `grep -c 'gr-grafik--zeitreihe'` → **56** unverändert.
Alle drei genannten SKUs einzeln mit BeautifulSoup nachgemessen: kein
Zeitreihen-Graph, genau eine Aufklappung, Position nach `.gr-karten`.

**Suite:** `PYTHONPATH=src /opt/homebrew/bin/python3 -m pytest -q` →
**2 failed / 2698 passed / 14 skipped** (245,1 s) — dieselben zwei
vorbestehenden Promo-Screenshot-Fehlschläge wie im Maßstab des Auftrags,
ein neuer grüner Test gegenüber dem Stand davor (2697 → 2698 passed).

**Site:** `render_site(site, reports, load_config(root))` neu ausgeführt.
`git diff --stat`: `site/geraete.html` (148 Zeilen, die drei betroffenen
Blöcke), `site/data/keyword-index.json` (reine Datums-Zeitbombe) mit
`git checkout --` zurückgesetzt. Kein `style.css`-Diff — es wurden nur
bestehende Klassen wiederverwendet.

**Commit:** ein fokussierter Commit (Template + Tests + Site) auf
`openclaw/ticket-rahmen2`, gepusht. Nicht gemerged — PM merged nach
Evaluator-PASS.
