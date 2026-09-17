# P2 — Fix-Notiz (17.09.2026, nach Code- und Sicht-Prüfung)

Grundlage: `p2/pruefung-code.md` (0×S1, 0×S2, 2×S3, 3×S4) und
`p2/pruefung-sicht.md` (1 FAIL auf 390). Alles Nachstehende selbst
nachgemessen (Messskript `p2/fix_mess.py`, Screenshots
`p2/screenshots/fix3-*-{viewport,kopf}.png`). Nichts kommittiert, nichts
unter `data/state` geschrieben; `site/` frisch mit `cfg` gerendert.

## Der FAIL (Sicht Punkt 2): Kurve auf 390 in den ersten Viewport — BEHOBEN

Messlatte des Prüfers: SVG-Oberkante ≤ Falz 844. Vorher 1008 px (+164),
nachher **832 px (−12 Luft)**. Hebel, alle gemessen:

| Hebel | Vorher | Nachher |
|---|---|---|
| h2 einzeilig: „Barpreis-Verlauf" statt „Wie sich der Barpreis eines Geräts entwickelt hat" | 129 px (2 Zeilen) | 50 px |
| Von/Bis als Einzeiler-Grid (`.gr-vzeit`, Inputs width:100 %) | Steuer 113 px | 72 px |
| Kacheln mobil kompakt | 139 px | 99 px |
| Margins mobil (verlauf 14, h2 12, suche/kopf 6) | — | −10 px |

Kein Querscroll (scrollWidth 390). Screenshots 390+1440 mit dem Auge
geprüft: Titel, Suchfeld, Buttons, Von/Bis-Zeile, 2×2-Kacheln komplett
einzeilig, Chart beginnt im Viewport.

## 7.2 (1440): Kurve klar über die Falz — BEHOBEN

Wrapper `.gr-vkopf` um Steuer + Kacheln (Vorlage + CSS): auf dem Schirm
stehen beide in EINER Reihe (Leserichtung Steuer → Kacheln bleibt, mobil
bricht der Wrapper um). Erste Kurve: 866 → **832 px** (68 px sichtbar,
Falz 900); SVG-Top 761 → 726. Stolperfalle dabei: `flex-basis:auto` maß
die content-Breite des Kachel-Grids und brach die Reihe trotzdem um —
`flex:1 1 0` + `min-width:min(480px,100 %)` (container-sicher, kein
Querscroll bei 560–600 px) löst es; Date-Inputs bekamen feste 138 px
(Chromium-Standard ~144 px je Feld trieb die Steuer auf 605 px).

## Neuer Befund, nur das AUGE gefunden: Kachelbetrag brach um

„1.171,00 €" in fett 24 px braucht ~110 px, die Kachel neben der Steuer
hat 109 px Inhalt — die Zahl brach, das „€" stand allein auf der Zeile
(Kachelhöhe 100 px; Screenshots fix-1440/390-kopf.png). Gefunden beim
Ansehen, NICHT von der Messung (regular gemessen: 103 px). Fix:
Kachelzahl 20 px (Desktop, ~92 px) bzw. 16 px in kompakter 2×2-Streckung
mobil. Die vom Prüfer vorgeschlagene 4er-Einzeile (87 px je Kachel) habe
ich nachgemessen und verworfen: selbst 14 px fett (~78 px) bricht an
75 px Inhalt, und die Labels brachen mit — 2×2 kompakt (99 px) ist
gleich hoch und hält Zahl UND Label einzeilig. Verankert in
`test_kein_kachelbetrag_bricht_um` (gestellte Daten 919/1171 €, beide
Viewports, prüft b-Höhe ≤ 1,6 × Schrift).

## Code-Prüfung (S3/S4)

- **S3-1 BEHOBEN:** Rückbau-Satz steht jetzt als „Kein Gerät gefunden."
  an beiden Stellen (Vorlage + `app.js`) — deckt zugleich Sicht 7.5 (der
  alte Sieben-Wort-Satz erklärte die Bedienung, Hausregel). Neuer Test
  `test_der_rueckbau_satz_steht_an_beiden_orten_gleich` hält beide
  zusammen (Muster: Übersetzungs-Link; Text aus der Vorlage extrahiert,
  keine dritte Kopie im Test).
- **S4-1 BEHOBEN:** toter Parameter `historie` aus
  `geraete_tco_view.aufbereiten()` gestrichen (Signatur, Aufrufer
  `geraete_view.py`, 2 Teststellen); `historie` in `geraete_view` hat
  weitere echte Leser (u. a. `geraete_verlauf.aufbereiten`) und bleibt.
- **S4-3 BEHOBEN:** `test_jede_breite_tabelle_liegt_in_ihrem_rollbehaelter`
  um die dynamische Verlaufstabelle erweitert (`#gr-vtabelle table` muss
  in `#gr-vtabelle` sitzen; ≥1 Tabelle durch Auto-Vorauswahl erzwungen).
- **S4 (app.js:12 `TR_ANKUNFT_SEARCH` global):** bewusst am Dateikopf
  (muss vor der Zeitreihen-IIFE laufen) — nicht angefasst.

## Sicht-Prüfung: was ich NICHT gemacht habe (Lead-Entscheidungen)

- **7.4 ist ein FEHLALARM, nachgemessen:** `gr-g2` steht in 0 Zeilen der
  style.css (fiel mit dem Block); die 18 Zeilen, die der Prüfer meint,
  sind `gr-g0` — sie stylen `geraete_tco_grafik.zeitreihe()`, die lebt
  (Aufrufer `geraete_tco_band.py:485`, 25 Testbezüge in tests/). Nichts
  gelöscht.
- **S3-2 (stiller Deep-Link-Fallback bei disjunkter Modell-ID):** vom
  Prüfer selbst als „kein Änderungsauftrag" eingestuft; P5-Auftrag 1
  (Sichtbarkeit beide Wege) ist der rechte Ort.
- **7.3 (URL bei Verlaufs-Modellwechsel schreiben):** der Schlüsselraum
  `?modell=` gehört der Zeitreihe des Vergleichs-Reiters (bewusst:
  `TR_ANKUNFT_SEARCH`). Der Verlauf braucht einen eigenen Parameter oder
  Fragment-Konvention — konzeptive Entscheidung → Lead.
- **7.6 (Zahl „Messtermine" an Kachel UND Gerätesatz):** nagelt
  `test_die_kachel_und_der_satz_nennen_dieselbe_zahl` fest — gebaut am
  30.08. gegen Antonios Befund „Kachel sagt 4, Satz 5" (zwei
  VERSCHIEDENE Zahlen). Die heutige Dopplung ist dieselbe, richtige Zahl;
  Straffen hieße, diesen Wahrheitstest bewusst umzudrehen → Lead.

## Messzahlen danach

- Suite `-k geraete`: **3 failed / 1405 passed / 6 skipped** — dieselben
  3 am sauberen HEAD `63e693c` (Worktree) reproduziert, vorbestehend:
  `test_tablets_und_router_bleiben_draussen` (E4/P5-3),
  `test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen`,
  `test_je_radar_gruppe_ein_querlink_mit_deep_link` (E4/P5-1).
  Neu: 3 Tests (Rückbau-Satz, Falz 390/1440, Kachelbetrag), 1 erweitert
  (Rollbehälter), 2 Aufrufstellen bereinigt (`historie=None`).
- `pruefe_portal.py`: **18 bestanden / 0 durchgefallen / 0 nicht
  prüfbar**; Reiterhöhen tco 2593, radar 2997, verlauf 1843→**1809**,
  katalog 1941 px; Kriterium 11c (Graphfalz Telefon) grün.

## Geänderte Dateien

`src/telco_radar/report/templates/{geraete.html.j2,app.js,style.css}` ·
`src/telco_radar/report/{geraete_tco_view.py,geraete_view.py}` ·
`tests/test_geraete_reiter_browser.py` ·
`tests/test_geraete_haendler_ohne_buendel.py` · `site/` (gerendert).
