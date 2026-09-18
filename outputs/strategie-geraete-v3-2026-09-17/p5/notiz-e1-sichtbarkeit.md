# P5/E1 — Sichtbarkeit folgt den Daten, nicht dem Weg (Auftrag 1 + 2)

Auftrag: `AUTO_SICHTBAR_AB_MESTAGEN` rechnet bislang nur den Bündelweg —
Katalog ab erster Listung ODER erstem Bündel, Zeitreihen-Wahl ab 2
Bündel-Messtagen; die zwei vorbestehenden roten Tests lösen. Nicht
committet, nichts unter data/state geschrieben, alle Zahlen selbst
gemessen (Render + Suite + `pruefe_portal.py` am echten Bestand 17.09.).

## Die Regel, wie sie jetzt steht

| Ort | Schwelle | Wo gerechnet |
|---|---|---|
| KATALOG | erste Listung (Tag 1) **ODER** erstes Bündel | `geraete_view.katalog_modellzeilen` |
| Zeitreihen-WAHL (Suchindex, Kacheln, Paare) | 2 Bündel-Messtage (unverändert, E4) | `geraete_zeitreihe.aufbereiten` |
| Lücke am Modellnamen | „noch keine Zeitreihe" nur mit Bündel; ohne Bündel schweigt sie (TCO-Spalte sagt „kein Bündel gemessen" — eine Aussage je Ort) | `geraete.html.j2`, Feld `hat_buendel` |

## Was gebaut wurde (nur diese Dateien)

| Datei | Änderung |
|---|---|
| `report/geraete_view.py` | `_buendel_je_anbieter_modell` liefert ZUSÄTZLICH `modell_schluessel → {device_id, speicher}` für JEDES auflösbare Bündel (einmalige Auflösung, kein zweiter Weg). `katalog_modellzeilen`: synthetische Gruppen für Bündel-Modelle ohne Listung (Felder, die nur eine Listung füllt, bleiben ehrlich leer); Bündel-Angabe-Pool auch ohne zeilen (Schritt 5); Händler-Spalte zählt ohne Listung die Bündel-Anbieter („0 Händler" neben „nur im Bündel bei o2" widerspräche der eigenen Zelle); neues Feld `hat_buendel` |
| `report/geraete_zeitreihe.py` | Regel-Kommentare (Konstante + Wahl-Block) auf die Zweige-Ansicht der EINEN Regel gestellt — Funktionscode unverändert, die Wahl-Regel (2 Bündel-Messtage) galt schon |
| `templates/geraete.html.j2` | Katalog-Zeile: `{% elif m.hat_buendel %}` → „noch keine Zeitreihe" (dieselbe Aussage wie im Radar, P4b-Logik); Aufklapper-Zeile nur `{% if m.zeilen %}` (Bündel-Angebote stehen im Vergleichs-Reiter/Radar — keine Doppel-Darstellung); Klasse `gr-k--ohne-details` |
| `templates/_geraete_radar.html.j2` | Kommentar: „nicht im Katalog" ist seit P5 nur noch fail-closed-Rest, nicht mehr der Regelfall |
| `templates/style.css` | `.gr-k--ohne-details{cursor:auto}` — eine Zeile ohne Aufklapper zeigt keinen Zeiger |
| Tests | s. unten |

## Die zwei vorbestehenden ROTEN — Vorher-rot/nachher-grün

1. **`test_tablets_und_router_bleiben_draussen`** (Galaxy-Tab-S11-Ultra-
   Auto-Katalog-Eintrag, Stand-Commit-Fall) — prüfte die ALTE Regel
   „Der Katalog verfolgt Smartphones. Ein iPad in der Preiskarte würde
   die Preisachse strecken": begründet mit der PREISKARTE, die seit dem
   30.08. gelöscht ist. **Vorher rot**: `erkenne_geraet` erkannte das
   Tab S11 Ultra zu Recht (Auto-Eintrag im Stand-Commit), der Test
   verlangte None. **Umgestellt auf** `test_die_erkennung_folgt_dem_
   katalog_nicht_der_geraeteklasse`: WAS IM KATALOG STEHT, wird erkannt
   (Tab S11 Ultra, `auto` gesetzt); Router ohne Eintrag bleiben draußen;
   ein iPad-Titel fällt ohne Eintrag NICHT fuzzig auf ein iPhone
   („ipad" in device_id, wenn er je trifft). Die iPad-ANker-Lücke selbst
   ist bewusst NICHT gepinnt (P5-Auftrag 3).
2. **`test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen`** — keine
   Sichtbarkeits-, sondern eine Bestands-Zeitbombe: die Simulation nagelte
   den 31.08.2026 fest; mit jedem Preis, der sich seither bewegte, sank
   die Zahl der unbewegten Kandidaten unter die geforderten 80
   (**Vorher rot: 52 < 80**, ohne dass sich eine Zeile Code geändert
   hatte). **Reparatur an der Ursache**: der Horizont kommt jetzt aus den
   Daten (Tag nach dem jüngsten `last_verified` = der nächste Nachtlauf),
   Floors 50/25 unter beide gemessenen Lagen (18.09.: 85/52 am Rand
   2026-09-18; 325/216 einen Tag später, wenn die Vodafone-Kohorte vom
   29.08. die Schwelle kreuzt). Der zweite Guard stand auf der LAGE vom
   02.09. (`ohne_bewegung == 0 or verfaelle == []` — „nichts hat sich
   bewegt"), jetzt auf der REGEL: stillstehende Plätze sind GEZÄHLT
   (`ohne_bewegung >= 1`), nie Zeile. Der zweite Nutzer der Simulation
   (`test_ohne_vollstaendigen_lauf_wird_nichts_zugerechnet`) läuft auf
   denselben Horizont um — grün.

Dazu ein dritter Test der alten Regel fiel **von selbst** an der neuen
Regel (vor meiner Umbenennung rot gemessen):
`test_reines_buendel_ohne_listung_heisst_nicht_im_katalog` → jetzt
`…_steht_im_katalog`: Bündel ohne Listung HAT eine Katalog-Zeile (mit
„nur im Bündel", Beleg, und Radar-Sprung „im Katalog →" statt der alten
Lücke); Graph-Sprung bleibt fail-closed („noch keine Zeitreihe").

## Neu: `tests/test_geraete_sichtbarkeit_p5.py` (4 Tests)

- Bündel ohne Listung, 1 Messtag → **Katalog-Zeile** (`nur_buendel`,
  `buendel_monat` 45,00 € o2, `hat_buendel`, `zr=False`, Händler=
  Bündel-Anbieter); gerendert: „nur im Bündel … €/Monat … Beleg ↗",
  „noch keine Zeitreihe", KEINE Detailzeile (data-auf trifft ins Leere,
  `gr-k--ohne-details`), in KEINEM Wahl-Eingang.
- Dieselbe Fixture mit 2. Messtag → waehlbar (erlaubt + Suchindex),
  Katalog-Zeile trägt den lebenden Graph-Sprung — die Automatik von
  Forderung 8: zweiter Nachtlauf, von selbst drin.
- FM 6.4: Auto-Modell MIT Listung, OHNE Bündel → Katalog ja, Wahl nein,
  und die Lücke SCHWEIGT (ohne Bündel beginnt keine Reihe — die TCO-Spalte
  sagt „kein Bündel gemessen", dieselbe Aussage zweimal verboten).
- `_baue_mit_auto` (E4-Tests, bestehend) deckt Auto+Listung+Bündel<2
  Messtage weiter ab.

## LIVE-Fall iPhone 18 am echten Bestand (17.09., 105 Bündel / 58
Listungen / 1 Bündel-Messtag) — vorher → nachher

| Messgröße (echtes `site/`, 18.09. gerendert) | vorher | nachher |
|---|---|---|
| Katalog-Modellzeilen | 111 | **116** (+5 reine Bündel-Modelle: Pixel 11 Pro Fold 512, iPhone 16 Pro Max 256, Galaxy S24 Ultra 512, Z Fold8 Ultra 1024, iPhone 16 Plus 256 — die 5 „nicht im Katalog"-Zeilen des Radars von D2c) |
| iPhone 18 im Katalog | 10 Zeilen (über Listungen) | 10 Zeilen, **9 davon mit „noch keine Zeitreihe"** (die `-1`-Zeile hat kein Bündel → schweigt, TCO-Spalte „kein Bündel gemessen") |
| iPhone 18 in der Zeitreihen-Wahl | draußen, stumm | draußen **mit Grund** (Katalog-Zeile + alle 8 Radar-Zeilen nennen die Lücke) |
| Radar-Zeilen „nicht im Katalog" | 5 | **0** — alle 97 Zeilen springen „im Katalog →" |
| Exporte contain iPhone 18 | ja (58/105/49/10/10 Zeilen) | unverändert ja; **neu:** die 5 Bündel-Modelle in `geraete-modell-barpreis/-tco.csv` mit Monatspreis + Beleg-Link, Barpreis-Spalten ehrlich leer |
| Suite `-k geraete` | 1462 passed / **2 failed** | **1505 passed / 0 failed** / 6 skipped |
| Volle Suite (Sicherheitsnetz, kombiniert mit den Parallel-Agenten) | — | **3303 passed / 0 failed / 12 skipped** (432 s) |
| `pruefe_portal.py` | 21/0/0 | **21 bestanden / 0 durchgefallen** (Katalog-Reiter 1973 px < 3000, Fließtext Katalog 230 Z, Graphfalz 813 px) |

Die 12 bündellosen Auto-Modelle: die 7 mit Listung (Tab S11 Ultra,
Tab S10 FE, Tab A11+, AirPods 5, Buds Pro 2, Watch S12 GPS 42/46,
Xcover) stehen im Katalog, in keiner Wahl; die 5 ohne Listung UND ohne
Bündel (Watch Series 12/Ultra 4-Varianten) stehen nirgends — ohne Daten
keine Zeile, dieselbe Regel in der anderen Richtung.

## Bekannte Kanten (bewusst so)

1. **Unlesbarer Bündel-Store** (S2-1-Fallback): `hat_buendel` kommt dann
   aus den Listungs-Pseudo-Bündeln — eine 1&1-Zeile kann „noch keine
   Zeitreihe" (wahr: keine Messreihe lesbar) neben einer TCO-Spalte
   „kein Bündel gemessen" (derFallback-Kennung) tragen. Seltener
   Fehlermodus, beide Sätze bleiben einzeln wahr; nicht verschönert.
2. **Guard-Kante** `ohne_bewegung >= 1 or not unbewegt`: unbewegt zählt
   über `first_seen`, die Verfall-Gruppen über `erstpreis_am` — fallen
   die zwei Maße jemals auseinander, fällt der Test (dann nachsehen).
3. Die `apple-iphone-18-pro-1`-Zeile (Speicher „1 GB" aus der Listung)
   ist ein Datenproblem am Sammler, keine Sichtbarkeitsfrage — nicht
   angefasst (nicht mein Auftrag).

## Geteiltes Arbeitsbaum-Verzeichnis

`git diff` enthält NEBEN meinen Dateien Fremdänderungen aus parallelen
P5-Agenten (09:00–09:08): `collect/geraete/autoerkennung.py`, Adapter,
`geraete_pipeline.py`, `geraete_store.py`, `test_geraete_autoerkennung.py`
(Aufträge 2/3). Meine Dateien: `report/geraete_view.py`,
`report/geraete_zeitreihe.py` (nur Kommentare), `geraete.html.j2`,
`_geraete_radar.html.j2`, `style.css`, `site/geraete.html` +
`site/style.css` + `site/exporte/geraete-modell-*.csv` (gerendert), die
drei umgestellten Testdateien + die neue. Meine Suite- und
pruefe_portal-Läufe fanden gegen den kombinierten Baum statt.
