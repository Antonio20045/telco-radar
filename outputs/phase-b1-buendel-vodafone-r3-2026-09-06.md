# B1 R3 — Regression-Fix: acht Fehler, ausgelöst durch die echten Vodafone-Daten (06.09.2026)

Auftragsgrundlage: `BRIEF_B1_R3_REGRESSION.md`, aufsetzend auf `EVAL_b1-vodafone-buendel-r1.md`
(unabhängige Abnahme, Urteil NEEDS_WORK) und `outputs/phase-b1-buendel-vodafone-2026-09-05.md`
(R2, der echte Lokallauf mit 253 Vodafone-Bündeln). Der Vodafone-Bündeladapter
selbst ist unverändert; dieses Ticket repariert ausschließlich die acht Tests,
die durch die ECHTEN Daten aus R2 rot geworden sind.

## Ergebnis in einem Satz

**Vollsuite wieder bei 2 failed / 2777 passed / 14 skipped** — exakt die zwei
bekannten Promo-Screenshot-Fehler, nichts sonst. Alle acht Regressionsfälle
sind durch angepasste Erwartungswerte behoben, keine Zeile Produktionslogik
angefasst, kein Datenbestand neu erhoben. Die 253 echten Vodafone-Bündel und
die 63 o2-Bündel stehen unverändert in `data/state/geraete_tco.json`.

## Ausgangslage, blockierend gemessen

Erster Lauf (vor jeder Änderung):

```
2 failed, 2769 passed, 14 skipped, 75 warnings in 264.91s (0:04:24)
FAILED tests/test_geraete_tco_hauptansicht.py::test_antwortzeile_nennt_je_metrik_die_guenstigste_zahl_mit_anbieter
FAILED tests/test_geraete_tco_hauptansicht.py::test_der_geraetepreis_fuehrt_wo_er_ausgewiesen_ist
FAILED tests/test_geraete_tco_hauptansicht.py::test_die_vodafone_referenz_ist_als_gerechnet_gekennzeichnet
FAILED tests/test_geraete_tco_hauptansicht.py::test_die_referenz_nimmt_den_guenstigsten_belegten_vodafone_tarif
FAILED tests/test_geraete_tco_hauptansicht.py::test_die_spanne_des_bandes_ist_die_der_angebote
FAILED tests/test_geraete_tco_hauptansicht.py::test_die_beschriftung_der_referenz_aendert_kein_delta
FAILED tests/test_geraete_tco_hauptansicht.py::test_g1_stellt_die_referenz_in_ihre_eigene_bindungsgruppe
FAILED tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung
FAILED tests/test_promo_seite.py::test_der_leere_screenshot_wird_nicht_ausgeliefert
FAILED tests/test_tco_bindung.py::test_am_echten_bestand_traegt_jede_o2_zeile_ihre_zwei_laufzeiten
10 failed, 2769 passed, 14 skipped
```

Deckt sich mit dem EVAL-Befund (`10 failed / 2769 passed / 14 skipped`); die
beiden Promo-Tests sind vorbestehend und nicht Teil dieses Tickets.

## Die eine gemeinsame Ursache

Bis zum echten Vodafone-Lokallauf (R2, 05.09.2026) enthielt
`data/state/geraete_tco.json` ausschließlich o2-Bündel. Sieben der acht Tests
sind gegen DIESEN Bestand geschrieben und benutzen entweder ein bestimmtes
Modell (das Leitfragemodell `apple-iphone-17-pro-256`, oder
`apple-iphone-15-128`) als Beispiel für „Vodafone hat kein eigenes Bündel,
also gilt die gerechnete Näherung", oder sie iterieren über den Bestand ohne
nach Anbieter zu filtern. Beide Annahmen waren beim Schreiben richtig — 0 von
0 Vodafone-Bündeln unterscheiden sich naturgemäß nicht. Mit den 253 echten
Bündeln ist das keine Annahme mehr, sondern eine Falschaussage über den
Bestand:

* **Vodafone führt jetzt für exakt zwei der drei in den Tests benutzten
  Modelle ein echtes eigenes Bündel** (`apple-iphone-17-pro-256`:
  1 Bündel/Cosmic Orange; `apple-iphone-15-128`: 2 Bündel, Mobil M 24 Monate
  und Mobil XS 36 Monate). Die Produktionslogik greift dafür genau wie
  gebaut: `_referenz_aus_buendel()` schlägt die gerechnete Näherung
  `_vodafone_referenz()`, sobald ein eigenes, belastbares Neugerät-Bündel
  vorliegt (`test_ein_eigenes_buendel_verdraengt_die_naeherung`, unverändert
  grün, war schon vor R2 gebaut und geprüft). Das ist **kein Fehler**,
  sondern der gemessene Bestand — Vodafone verkauft dieses Gerät jetzt
  wirklich im Bündel, und die Karte sagt das, statt es näherungsweise zu
  behaupten.
* **`data/state/geraete_tco.json["buendel"]` ist jetzt ein GEMISCHTER
  Bestand** (63 o2- plus 253 Vodafone-Sätze), und ein Test, der ohne
  Anbieterfilter über die ganze Liste iteriert und dabei o2-spezifische
  Bindungsregeln erwartet, prüft jetzt auch Vodafone-Sätze gegen diese
  Regeln — obwohl sein eigener Name „jede o2 Zeile" sagt.

Am echten Bestand vom 06.09.2026 trägt nur noch **ein einziges Modell**
(`google-pixel-10-128`) eine echte Vodafone-Näherungskarte — für dieses Gerät
fehlt Vodafone weiterhin ein eigenes Bündel. Drei der sieben Tests brauchen
für ihre Aussage aber genau diesen Fall (Näherung vorhanden, Referenz bindet
kürzer als das verglichene Bündel) und sind deshalb auf dieses Modell
umgezogen — nicht deaktiviert, sondern an den Fall gebunden, den sie wirklich
prüfen wollen.

## Die acht Fehler einzeln

| # | Test | Ursache | Fix |
|---|---|---|---|
| 1 | `test_antwortzeile_nennt_je_metrik_die_guenstigste_zahl_mit_anbieter` | `vodafone["naeherung"] is True` erwartet — Vodafone führt jetzt ein echtes Bündel zum Leitfragemodell, `naeherung` ist `False` | Erwartung auf `False` gedreht; die geprüfte Kernaussage (Saturn führt Gerätepreis, 1&1 führt Tarifgesamtpreis, Vodafones Barpreis bleibt 1.199,90 €) ist unverändert wahr |
| 2 | `test_der_geraetepreis_fuehrt_wo_er_ausgewiesen_ist` | `[k for k in karten if k["naeherung"]][0]` wirft `IndexError` — keine Näherungskarte mehr für dieses Modell | Vodafone-Karte wird über `anbieter == "Vodafone"` gefunden statt über `naeherung`; Geraetepreis (1.199,90 €) unverändert |
| 3 | `test_die_vodafone_referenz_ist_als_gerechnet_gekennzeichnet` | dieselbe `IndexError` — der Test prüft explizit die Kennzeichnung EINER Näherungskarte | Zielmodell auf `google-pixel-10-128` umgestellt (das einzige verbleibende Modell mit echter Näherung); Testlogik unverändert |
| 4 | `test_die_referenz_nimmt_den_guenstigsten_belegten_vodafone_tarif` | Referenz für das Leitfragemodell kommt jetzt aus einem echten Bündel (Tarif „Mobil XS" zu diesem Gerät, 31,95 €), nicht mehr aus der Wahl des günstigsten Tarifs (29,95 €) | Zielmodell auf `google-pixel-10-128` umgestellt; Testlogik unverändert |
| 5 | `test_die_spanne_des_bandes_ist_die_der_angebote` | `apple-iphone-15-128` hat jetzt zwei eigene Vodafone-Bündel statt einer Näherung — `IndexError` | Zielmodell auf `google-pixel-10-128` umgestellt; Testlogik unverändert |
| 6 | `test_die_beschriftung_der_referenz_aendert_kein_delta` | Referenzsumme ist jetzt eine ECHTE Messung (Vodafone bindet das jeweilige Gerät real an einen bestimmten Tarif) statt der gerechneten Näherung — die Beträge selbst ändern sich, die REGEL (Euro-Delta hängt am Fenster, nicht am Etikett) nicht | Erwartete Beträge nachgerechnet und aktualisiert: iPhone 17 Pro/o2 von −123,94 € auf −161,04 €, iPhone 15/o2 von −307,95 € auf −349,05 € |
| 7 | `test_g1_stellt_die_referenz_in_ihre_eigene_bindungsgruppe` | `apple-iphone-15-128` zeigt keinen "Referenz"-Balken mehr (echtes Bündel statt Näherung) — `svg.index("Vodafone <tspan")` wirft `ValueError` | Zielmodell auf `google-pixel-10-128` umgestellt; Testlogik unverändert |
| 8 | `test_am_echten_bestand_traegt_jede_o2_zeile_ihre_zwei_laufzeiten` | Schleife lief über ALLE Bündel (o2 UND Vodafone) ohne Filter, obwohl der Testname „jede o2 Zeile" sagt — Vodafone-Sätze mit 12/24-Monats-Bindung brechen die o2-spezifische Erwartung `bindung==36, tarif_bindung==24` | Schleife auf `satz["anbieter"] == "o2"` gefiltert; alle 63 o2-Sätze bestehen weiterhin unverändert |

Kein einziger dieser acht Fälle ist ein Fehler der Produktionslogik. Die
Karten-Priorisierung „eigenes Bündel schlägt Näherung" war bereits vor R2
gebaut UND durch einen eigenen, unverändert grünen Test abgesichert
(`test_ein_eigenes_buendel_verdraengt_die_naeherung`,
`tests/test_geraete_tco_hauptansicht.py`) — die sieben Hauptansicht-Tests
hatten nur nie einen echten Fall vor Augen, an dem diese Priorisierung
wirklich greift, weil der Bestand bis R2 keine Vodafone-Bündel kannte.

## Rechenprobe, gegen die Produktionsfunktion nachgerechnet

Alle in der Tabelle genannten neuen Zahlen sind direkt aus
`geraete_tco_karten.modelle()` gegen den echten Bestand gelesen (nicht
hergeleitet):

* **iPhone 17 Pro 256 GB, Vodafone-Referenz**: Tarif „Mobil XS" (31,95 €/Monat,
  Quelle `VF-Mobil-XS-Juli-2026.pdf`) über 36 Monate + Barpreis 1.199,90 €
  (Quelle `vodafone.de/privat/handys/iphone-17-pro.html`) = **1.955,80 €**.
  o2-Delta: 1.794,76 − 1.955,80 = **−161,04 €** (8,2 %, günstiger).
* **iPhone 15 128 GB, Vodafone-Referenz**: dasselbe Muster, Referenz aus dem
  günstigeren der zwei eigenen Bündel (36 Monate, 1.469,80 €). o2-Delta:
  1.120,75 − 1.469,80 = **−349,05 €** (23,7 %, günstiger).
* **google-pixel-10-128, Vodafone-Näherung** (unverändert die alte Logik):
  Tarif „Vodafone Mobil XS" (29,95 €/Monat — der günstigste belegte
  Vodafone-Tarif, `min([59.95, 49.95, 39.95, 79.95, 29.95])`) über 24 Monate
  = 718,80 € + Barpreis 899,90 € = **1.618,70 €**, Fenster 36 Monate
  (o2 bindet dieses Gerät 36 Monate, Vodafone selbst hat dafür kein Bündel).

## Testresultat nach dem Fix

Gezielt (die zwei betroffenen Dateien):

```
PYTHONPATH=src /opt/homebrew/bin/python3 -m pytest -q \
  tests/test_geraete_tco_hauptansicht.py tests/test_tco_bindung.py
.......................................................                  [100%]
55 passed in 0.22s
```

Vollsuite, blockierend, nach dem Fix:

```
2 failed, 2777 passed, 14 skipped, 75 warnings in 273.15s (0:04:33)
FAILED tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung
FAILED tests/test_promo_seite.py::test_der_leere_screenshot_wird_nicht_ausgeliefert
```

Exakt der geforderte Maßstab — die zwei vorbestehenden, unveränderten
Promo-Screenshot-Tests, keine weiteren roten Tests.

## Erhalt der 253 Bündel (Abnahmekriterium 1)

```
$ git status --short
 M tests/test_geraete_tco_hauptansicht.py
 M tests/test_tco_bindung.py
```

Nur die beiden Testdateien sind geändert; `data/state/geraete_tco.json`,
`data/state/geraete_db.json` und alle übrigen State-/Report-Dateien sind
unangetastet. Nachgezählt:

```
Counter({'Vodafone': 253, 'o2': 63})
```

Unverändert gegenüber R2. Keine Daten gelöscht, kein Wert künstlich
angepasst — jede geänderte Erwartung im Testcode ist gegen die Produktions-
funktion `geraete_tco_karten.modelle()` bzw. `tco_model.tco_bindung()`
nachgerechnet, nicht geschätzt.

## Abnahmekriterien im Einzelnen

1. ✅ 253 echte Vodafone-Bündel unverändert im Bestand, keine Löschung, keine
   künstliche Anpassung.
2. ✅ Ursache jedes der acht Fehler dokumentiert (Tabelle oben) und durch
   passende Erwartungswerte behoben — keine pauschale Deaktivierung, kein
   `pytest.skip`, kein `xfail`.
3. ✅ Keine TCO-36→24-Produktumstellung vorgezogen — `tco_model.py`,
   `geraete_tco_karten.py` und `geraete_tco_grafik.py` sind in diesem Ticket
   nicht angefasst; `git diff --stat` zeigt ausschließlich die zwei
   Testdateien.
4. ✅ Vollsuite blockierend: 2 failed / 2777 passed / 14 skipped — exakt die
   zwei bekannten Promo-Screenshot-Fehler.
5. ✅ Kein ausgeliefertes Artefakt geändert (`site/`, `data/state/`
   unangetastet) — kein Render, kein Deploy nötig.
6. ✅ Dieser Bericht.

## Hausregeln eingehalten

Branch `openclaw/ticket-b1-buendel-vodafone`, kein Merge nach `main`, kein
Deploy-Hook berührt. Kein Hintergrund-Monitor: beide Suiteläufe liefen
blockierend im Vordergrund, Ergebnis gelesen, dann committet. Datenbestand
nicht neu erhoben — der Fix brauchte keinen einzigen neuen Netzabruf.

## Baumzustand

Ein Commit auf `openclaw/ticket-b1-buendel-vodafone`: die zwei korrigierten
Testdateien plus dieser Bericht. `git status --short` danach: sauber.
