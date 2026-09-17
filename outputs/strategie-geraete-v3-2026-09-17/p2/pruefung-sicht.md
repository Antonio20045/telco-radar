# P2 SICHT-Prüfung — Preisverlauf-Reiter /geraete.html (17.09.2026)

Prüfer: harter Sicht-Prüfer ohne Bau-Kontext. Urteilskriterium ist Antonios
Forderung wörtlich: kein Text vor der Graf, das Modell-Wähl-Erlebnis GANZ
OBEN, der feste Marktgraph gelöscht.

Methode: `python3 -m http.server 8767 --directory site`, Playwright/Chromium,
initialer Zustand nach Reiter-Klick ohne jeden weiteren Klick. Messskript:
`p2/pruef_sicht.py` (+ `/tmp/p2-falz.py` für die Falz-Nachmessung), Screenshots
`p2/screenshots/pruef-*.png` (1440 + 390, Reiter und Viewport, Modellwechsel).
Alle Zahlen unten sind selbst gemessen, keine aus den Bau-Notizen übernommen.

## Punkt 1 — Aufbau: PASS

Server lief (200), Reiter „Preisverlauf" über `nav.gr-reiter button` erreichbar,
jede Messung reproduzierbar. Kein Klick nötig außer dem Reiter-Wechsel selbst.

## Punkt 2 — „Wähler + Kurve ganz oben ohne Klick": **FAIL (nur 390), PASS auf 1440 mit Anmerkung**

Harte Messung (Dokument-Koordinaten, un-gescrollt, Viewport 900 bzw. 844):

| Element | 1440×900 | 390×844 |
|---|---|---|
| Reiterkopf (Panel-Top) | 476 | 476 |
| h2 | 476–526 (1 Zeile, 8 Wörter) | 512–641 (**2 Zeilen, 129 px hoch**) |
| **Suchfeld** `#gr-vsuche` | **566** (rel. 90), komplett sichtbar ✓ | **682** (rel. 205), komplett sichtbar ✓ |
| Zeitraum-Steuer | 622–653, komplett sichtbar | 734–847 (**reicht über die Falz**) |
| Kacheln | 669–743, sichtbar | 857–996 (unter der Falz) |
| **SVG-Anfang** `#gr-vbild svg` | **761** (rel. 285), 139 px sichtbar | **1008** (rel. 531), **0 px sichtbar** |
| erste Kurve (path) | 866 → **34 px Kurve im Viewport** | 1064 → unsichtbar |

- **Vor dem Suchfeld steht kein Satz und kein Gerüst** — nur die h2. Das ist
  Antonios Kernforderung und sie ist auf BEIDEN Breakpoints erfüllt.
- **1440:** Wähler-Erlebnis steht oben; Diagramm-Kopf ragt in die Falz, von der
  ersten Kurve sind 34 px sichtbar — man erkennt, dass eine Kurve läuft, aber
  das Kurvenbild selbst beginnt erst 34 px vor der Falz. Anmerkung, kein FAIL.
- **390:** Die Kurve liegt 164 px unter der Falz. Der erste Blick zeigt h2
  (zweizeilig!), Suchfeld, gestapelte Zeitraum-Steuer. Das
  „Modell-Wahl-GRAPHEN-Erlebnis" ist dort nur halb da (Wähler ja, Graph nein).

**Fix-Anweisung (390):** SVG-Top von 1008 auf ≤ 844 bringen (−164 px), ohne die
verbindliche Reihenfolge zu brechen: (a) h2 mobil kürzen/einzeilig —
„Barpreis-Verlauf" statt „Wie sich der Barpreis eines Geräts entwickelt hat"
(−60 px); (b) Kacheln mobil als 4er-Einzeile statt 2×2 (−70 px); (c) Von/Bis
hinter die Raster-Buttons in eine Zeile ziehen oder einen Aufklapper
(−40 px). Zwei der drei genügen. Danach 1440 nachmessen (Kurve rückt dort
ebenfalls über die Falz).

## Punkt 3 — G2 wirklich weg: PASS

- DOM im Reiter: `gr-g2`/`gr-g0`/`#gr-g2`/`#gr-g0-lager` **0 Knoten**;
  genau **1 SVG** (`svg_anzahl: 1`, 14 Punkte, 6 Linien — das des gewählten
  Geräts).
- Keine Rest-Legende, keine Waisen-Textblöcke: „Reihen mit Preis…",
  „Daten dieser Kurven", „iPhone 17 Pro und Pro Max", „Preisänderung",
  „ausgelassen" — alle **0 Treffer** im gerenderten Reiter-Text.
- Quelltext `site/geraete.html`: `gr-g2` 0, `gr-g0` 0. GANZES site/: 0 Dateien
  mit `gr-g2` (DOM-Ebene). 
- Rest (unsichtbar, kein FAIL): `site/style.css` trägt noch **18 tote
  `gr-g2`/`gr-g0`-Zeilen** — Aufräumen, siehe Punkt 7.

## Punkt 4 — Fließtext ohne Klick: PASS

Zählung wie design.md (sichtbare h2/p/figcaption/summary im Reiter):
**27 Wörter** (h2 8 · Legende 6 = Anbieternamen · Gerätesatz 12 ·
„DATENLAGE"-summary 1). Ziel < 60 klar erfüllt. Der 1813-Zeichen-Block unter
der Graf existiert nicht mehr; design.md-Regel 8 (p nach SVG ≤ 200 Zeichen)
ist erfüllt (Legende ~50 Z, Gerätesatz 66 Z). Der Bedien-Satz „Wählen Sie
oben ein Gerät…" ist initial `hidden` (gemessen: erst bei Eingabe ohne
Treffer sichtbar).

## Punkt 5 — Auto-Vorauswahl, Wechsel, Deep-Link: PASS

- Ohne Klick ist das erste Gerät der Liste gewählt („iPhone 17 256 GB",
  1 SVG, 14 Punkte — Diagramm steht sofort da).
- Modellwechsel über Suchfeld: „Galaxy A17" → 1 Treffer → Klick → Suchfeld
  „Galaxy A17 128 GB", Diagramm 12 Punkte — sauber gewechselt.
- Reiter-Wechsel Vergleich → Preisverlauf und zurück: Wahl **bleibt**
  („Galaxy A17 128 GB", 12 Punkte unverändert).
- Deep-Link `?modell=samsung-galaxy-a17-128` → genau dieses Modell gewählt;
  unbekannte id fällt still aufs erste Gerät zurück.
- **Anmerkung (kein FAIL):** Die URL wird bei Verlaufs-Modellwechsel NICHT
  aktualisiert — gemessen zeigt die URL weiter
  `?modell=apple-iphone-17-pro-256&band=klein` (Vorgabe der Zeitreihe), während
  der Verlauf „Galaxy A17 128 GB" zeigt. Wer die URL kopiert, teilt den
  Zustand eines anderen Modells. Siehe Punkt 7.

## Punkt 6 — Unruhe: PASS (deutlich ruhiger)

| Messung | Vorher (design.md) | Jetzt (gemessen) |
|---|---|---|
| Konzepte im Reiter | 2 (fester Marktgraph + Wähler) | 1 (nur Wähler) |
| Fließtext | 5 p, 2355 Z (1 Block 1813 Z) | 27 Wörter |
| Suchfeld-Position | 1176 px von 1581 | rel. 90 (1440) / 205 (390) |
| Aufklapper | — | 1 („Datenlage", `cursor:pointer` ✓) |
| sichtbare Buttons im Reiter | — | 3 (eine Gruppe) |
| Blockfolge | gemischt | 9 Blöcke, linear: h2 → Suchfeld → Steuer → Kacheln → Diagramm → Legende → Satz → Tabelle → Aufklapper |

Keine Doppel-Darstellung mehr, keine zweite Graph-Form. Der Reiter liest sich
als EINE Handlung: Gerät wählen, Kurve lesen.

## Punkt 7 — Was im Scope noch besser werden kann

1. **(Der FAIL aus Punkt 2)** Kurve auf 390 in den ersten Viewport — h2
   einzeilig, Kacheln 4er-Einzeile mobil, Von/Bis in eine Zeile.
2. **1440: Kurve klar über die Falz** — Kacheln neben die Zeitraum-Steuer in
   eine Reihe rücken (~74 px gewonnen; erste Kurve läge bei ~790 statt 866).
3. **URL beim Verlaufs-Modellwechsel schreiben** (z. B. `?modell=` im
   Verlaufs-Schlüsselraum oder `#tafel-verlauf` + Parameter) — sonst teilt die
   Adresszeile den Zustand des Zeitreihen-Reiters, nicht den sichtbaren.
4. **18 tote `gr-g2`/`gr-g0`-Zeilen aus `style.css` löschen** (unsichtbar,
   aber der nächste Entwickler sucht ihre Bedeutung).
5. **Rückbau-Satz** „Wählen Sie oben ein Gerät – dann steht hier sein
   Preisverlauf…" erklärt die Bedienung (Hausregel) — „Kein Gerät gefunden"
   reicht im Zwischenzustand.
6. **Zahl 11 (Messtermine) steht an zwei Orten untereinander** (Kachel und
   Gerätesatz) — straffen: die Kachel behält die Zahl, der Satz nennt nur den
   Zeitraum, oder umgekehrt.
7. **Toter Ternär** in der Trefferliste (`g.anbieter === 1 ? ' Anbieter' :
   ' Anbieter'` — beide Zweige identisch); either entfernen oder
   Singular-Behandlung streichen.

## Gesamttabelle

| # | Prüfpunkt | Urteil |
|---|---|---|
| 1 | Setup/Erreichbarkeit | PASS |
| 2 | Wähler+Kurve ganz oben ohne Klick | **FAIL auf 390** (Kurve 164 px unter Falz); PASS 1440 (Anmerkung: 34 px Kurve) |
| 3 | G2 restlos weg | PASS |
| 4 | Fließtext < 60 Wörter | PASS (27) |
| 5 | Auto-Vorauswahl/Wechsel/Deep-Link | PASS (Anmerkung URL-Sync) |
| 6 | Ruhiger geworden | PASS |

## Gesamturteil

**Nicht bestanden (durch=false)** — ein echter FAIL: Auf dem Telefon (390×844)
beginnt die Kurve 164 px unter der Falz; das „GANZ OBEN"-Gefühl, das Antonio
verlangt hat, endet dort beim Suchfeld. Alles andere sitzt: kein Text vor dem
Wähler, G2 restlos entfernt, 27 Wörter statt 2355 Zeichen, Wahl und Deep-Link
stabil. Desktop ist nah dran — mit Punkt 7.2 wäre die Kurve auch dort ganz im
ersten Blick.

— Sicht-Prüfer P2, 17.09.2026. Server beendet, nichts committet.
