# P4-Re-Check — Notiz (18.09.2026, frischer Prüfer)

Gegenstand: `site/geraete.html` nach fix.md, frisch gerendert MIT `cfg`.
Server 127.0.0.1:8772, Playwright Chromium, 1440×900 (dsf 1) und 390×844
(dsf 2). Screenshots: `screenshots-recheck/` (9 Stück, inkl. S2-Beweis).
Rohmessung: `recheck-mess.json`, Skript `recheck_mess.py`. Nichts committet,
kein `data/state` geschrieben (git status geprüft).

## Nachgestellte Messungen aus pruefung-sicht.md

| Messung | vorher (pruefung-sicht) | nachher (dieser Lauf) | Urteil |
|---|---|---|---|
| max fontSize 1440 | Katalog FAIL (25,5 px h2) | 4/4 Reiter: 60 px `b.gr-leit-zahl` (tco 466,80 € / radar −55,5 % / verlauf 919,00 € / katalog 157,00 €) | **PASS** |
| max fontSize 390 | FAIL (h1 34 > 30) | 4/4 Reiter: max 30 px auf der Leitzahl | **PASS** |
| Button-Reihen vor Daten | PASS (2/0/1/1) | 2/0/1/1 (tco: Band + 6 Kacheln; erster Datenanker SVG top 873) | PASS |
| Rot je Tafel (definiert: Hue≈0, eigenes Rot, ohne SVG, initial sichtbar) | 19/7/6/12 | **9/6/2/12** | tco/radar/verlauf PASS, **Katalog FAIL (12 > 10)** |
| Text-Deckel (pruefe_portal 13) | 18 048 Z FAIL | 992 Z; Portal **21/0/0** | **PASS** |
| Tote gr-sprung (S1 Faden) | 10, falsche Antwort | **0 tote**; 87 Links = 87 Zeitreihen-Modelle (Fragment); iPhone-18-Zeilen: „im Katalog →" oder „noch keine Zeitreihe" (10×); lebender Sprung Xiaomi 17 → „o2 am günstigsten: 880,75 €" korrekt | **PASS** |
| „keine Angabe"-Pillen | 166 | 0 (stilles „–") | PASS |
| Kachel-Ellipsis | 3× „GALAXY S26 UL…" | 0 Punkte-Kürzung, Namen vollständig | PASS |
| Mobil Querscroll | PASS | scrollWidth = Viewport, 4/4 Reiter | PASS |
| Mobil Kurve erster Viewport | 922 px KNAPP FAIL | **921 px** (SVG 325 px hoch) — 77 px unter der Falz | **NICHT BEHOBEN** (fix.md: bewusst nicht gebaut, dort „~35–40 px" — nachgemessen 77) |

Tafelhöhen initial: 2113/1544/1158/1215 (1440), 2416/2455/1234/1577 (390);
11b: 2860/2291/1943/1962 — alle < 3000.

## S1/S2-Stichproben

**S1 (tote Sprünge): behoben.** Live-Klick-Beweise oben; Testumstellung in
`test_geraete_o3_rollen.py` ist STÄRKEND (Wahlmengen-Assert gegen
`#gr-zeitreihe-daten … erlaubt`, NEU Lücken-Assert „noch keine Zeitreihe"
je Zeile, beide mit Gegenprobe gegen leere Lookups, Vorher-rot im Docstring).
Der dritte vorbestehende Rot (iPhone-18-Querlinks) ist dadurch grün —
Ursachen-Fix des Prüfauftrags S1, dokumentiert, keine Abschwächung.

**S2 (Leitzahl-Leerzustand): Fix WIRKUNGSLOS — neuer S1.**
`<div class="gr-leit gr-vleit" id="gr-vleit" hidden>`, aber
`.gr-leit{display:flex}` (site/style.css:3642, Autoren-Regel) übersteuert
das Browser-`[hidden]` — dasselbe Muster, das das eigene Stylesheet an
Z. 2297 ff. und 3562 („Autorenregel schlägt das [hidden]") dokumentiert und
woanders per `…[hidden]{display:none}`-Zeile löst. Gemessen (beide Pfade):

- Suche „zzzz": `hidden: true`, `display: 'flex'`, rect 81 px hoch —
  **„919,00 € aktuell · congstar · 17.9." steht sichtbar über
  „Kein Gerät gefunden."** (Screenshot recheck-s2-leerzustand-1440.png)
- Von-Datum 2027-01-01: derselbe Befund („keine Messpunkte").

Der neue Browser-Test `test_die_leitzahl_schweigt_in_beiden_leerzustaenden`
assertet `e.hidden` — das **Attribut** statt Sichtbarkeit; er ist grün, obwohl
die Leitzahl sichtbar bleibt. Fix: `.gr-vleit[hidden]{display:none}`-Zeile
(Muster existiert) UND Test auf `getComputedStyle().display`/Sichtbarkeit
umstellen.

**Neu, Nachbar des S2:** Bei „zzzz" bleiben auch die vier Kachel-Zahlen
(919,00 € / 1.171,00 € / 6 / 11) des vorherigen Geräts unverändert stehen —
fünf gerätbezogene Zahlen behaupten ein Gerät, das nicht mehr gewählt ist.
(Vorher auch da, vom S2-Befund nicht umfasst.)

## Katalog-Rot im Detail (FAIL)

12 initial sichtbare Rot-Elemente: 1 aktiver Preisart-Knopf (Text dunkelrot
`rgb(163,0,0)` auf Wash `rgb(253,240,238)` — Fläche ok) + **11×
`a.gr-sprung` „im Graph ansehen →" in VOLLEM Rot `rgb(230,0,0)` initial**.
fix.md behauptet „Sprung-Links grau mit Rot erst im Hover" — für den Katalog
widerlegt (computed color initial). fix.md-Zahl „Katalog 5" ist mit keiner
Messregel reproduzierbar (eng 12, breit 12; selbst ohne den Knopf 11).
Vergleich zum Vergleichs-Reiter: Dort wurde die Regel umgesetzt (aktive
Knöpfe Wash, Vodafone-Etiketten dedupliziert 19→9). 11 identische rote Links
in einer Tafel sind genau das Muster, gegen das der Deckel gebaut wurde.

## Suite / Portal

- `pytest -k geraete`: **1460 passed / 2 failed / 6 skipped** — die 2 sind
  exakt `test_tablets_und_router_bleiben_draussen` (Galaxy Tab S11 Ultra)
  und `test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen` (Nachtlauf),
  beide unangetastet vorbestehend. Entspricht fix.md.
- Zusätzlich `test_seiten_zahlen` + `test_wettbewerbsradar_alarme`:
  113 passed.
- `scripts/pruefe_portal.py`: **21 bestanden / 0 / 0**. 13: 992/2618/358/230;
  14: 0 Z; 11b: 2860/2291/1943/1962; 11c: Graphkopf 838 ≤ 844; 15: 30
  summaries mit Zeiger+Zeichen.

## Augenschein

Vier Falzbilder + S2-Beweis angesehen (Bildmodell): Vergleich — Leitzahl
466,80 € dominiert deutlich über h1, ruhig, zwei Steuerreihen, Rot sparsam,
Grafikanfang bei 873 px im 900er-Viewport. Radar — Balken-Grafik sichtbar,
„−55,5 %" größte Schrift, Tabelle kollabiert. Mobil 390 — Leitzahl größtes
Element, Kurve erst nach Scroll (messbar 921 px). Antonios Rahmen („keinen
Text sehen, unruhig") ist nach Zahlen und Auge adressiert — der Rest sind
die vier offenen Punkte unten.
