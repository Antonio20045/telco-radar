# P4/D4 — Falz und Steuergruppen: die ANTWORT ist die größte Zahl

Stand: 18.09.2026, nach Commit 6a37ceb (P3). Nicht committet, kein data/state
angefasst. Ein früherer D4-Durchlauf hatte den Großteil gebaut, aber keine
Notiz hinterlassen und zwei Rot stehengelassen; dieser Lauf hat verifiziert,
zwei Rot repariert, alle Messungen nachgemessen und die Screenshots erneuert.

## Was gebaut ist (Stand dieses Laufs, verifiziert)

1. **Export-Fußzeile** (`.gr-export-fuss`): 6 Knöpfe aus der Kopfzeile
   (vorher y=322/1440, y=372/390 — ÜBER der Reiter-Steuerung) als EINE Zeile
   ans Seitenende (nachher y=2609/1440, y=3002/390). Dieselben 6 Ziele
   (geraete-aktuell, -historie, -tco, wettbewerbsradar, modell-barpreis,
   modell-tco), Zeilenzahl neben dem Link. Rollt am Telefon in sich
   (overflow-x:auto), nie die Seite quer (≤ 391 px).
   **Fix dieses Laufs:** die Fußzeile hing im `hat_daten`-Zweig und wäre im
   Ganz-Leer-Fall still verschwunden — E5-Leersicherung „Export ohne Zeilen"
   verlangt die Null neben dem Link auch leer. Sie steht jetzt außerhalb des
   Gatters (fail-closed bleibt: ohne Dateiname keine Fußzeile).
2. **Leitzahlen** (`.gr-leit`/`.gr-leit-zahl`, Serif bold, clamp 30–60 px):
   - Vergleich: TCO-Delta über dem Antwort-Satz (`_leitzahl_html`, dieselbe
     Rechnung wie vorher im Satz; das Delta ist aus dem Satz gefallen — keine
     Zahl zweimal am selben Ort). Ohne Delta (Vodafone führt selbst / kein
     Bündel im Band) keine Zeile.
   - Radar: stärkste Abweichung aus `modelliste.zeilen[0]` (negativeste %,
     geraete_radar.py — kein zweiter Rechner).
   - Preisverlauf: aktueller Barpreis des gewählten Geräts (app.js, aus den
     ungefassten Rohpunkten derselben Reihen wie die Kacheln — günstigster
     Preis am letzten Messtag).
   - Katalog: bewusst ohne Leitzahl (Auftrag: ab-Preis der ersten Zeile in
     der Tabelle ist ok).
3. **Steuermenüs gestrafft**: Satz „ohne Zuordnung" unter die Bündel-Sektion
   gezogen (war Mini-Satz zwischen Kopf und Wahl-Leiste); Radar-Kopf von
   drei Sätzen auf einen gestrafft.

## Messungen (Playwright, Initialzustand, eigene Verifikation)

max fontSize im ersten Viewport (größte Zahl, Tafel):

| Reiter | vorher (1440) | nachher (1440) | nachher (390) |
|---|---|---|---|
| Vergleich | 21 px (Kartenpreis `<b>`) | **60 px** `.gr-leit-zahl` „466,80 €" | 30 px (H1 34 px bleibt Titel) |
| Radar | 25,5 px (H2-Titel!) | **60 px** „−55,5 %" | 30 px |
| Verlauf | 25,5 px (H2-Titel) | **60 px** „919,00 €" | 30 px |
| Katalog | 25,5 px (H2) | 25,5 px (ok, Tabelle) | 25,5 px |

Button-Reihen vor dem ersten Datenelement (nachher, beide Breiten):
Vergleich 1 (Suchfeld+Band = EINE Auswahlgruppe; Kacheln = erstes
Datenelement) · Radar 0 (EIN Satz vor der D1-Grafik, SVG beginnt y=662/1440)
· Verlauf 1 (Zeitraum) · Katalog 1 echte Steuer-Reihe (Umschalter; die
„zweite Reihe" der Zählung sind die Sortierknöpfe IM Tabellenkopf).
Vorher Vergleich: 2 Reihen/9 Buttons vor y=528.

Export-Position mobil 390: vorher y=372 (im Hero, über der Steuerung,
Suchfeld erst y=515) → nachher y=3002 (Seitenende, unter allem Inhalt).

390-Grenze der Leitzahl (gemessen, mess-390-leitzahl.json): Graphkopf bei
30 px = 840 von 844 px Falz (11c); 34 px = 844 (0 Luft), ab 35 px bricht 11c.
Textbreite längster Fall („1.499,00 €") = 131 px von 306 px Zeile — einzeilig,
kein Umbruch-Chaos. H1 bleibt auf dem Telefon der größte Text (34 px); die
Regel „Antwort = größte Schrift" ist auf 1440 voll, auf 390 bis auf den
Seitentitel erfüllt (kalibriert gegen Falz 11c — Titel verkleinern wäre
keine D4-Entscheidung).

## Tests

- `test_geraete_export_mobil_browser.py` (vorher-rot dokumentiert im
  Vorlauf: Assert „keine Export-Reihe im Kopf" → Fußzeile) — 5 grün.
- `test_geraete_o4_export.py` („Knopf … im Kopf der Tafel" → Fußzeile,
  `test_die_export_links_stehen_in_der_fusszeile` neu) — grün.
- **Repariert dieser Lauf:** `test_geraete_leer_zustaende.py::
  test_export_ohne_zeilen_nennt_die_null` (0 Links im Leerzustand — echter
  Bug des Fuß-Umzugs, s. o.) und `test_geraete_radar_tafel.py::
  test_der_tafelkopf_polt_nur_die_sektionen_mit_vorzeichen` (Wortlaut
  „Betrag ohne Vorzeichen" → „als Betrag"; Aussage bleibt: Alarme = Betrag,
  alle Alarm-Prozente positiv).
- Geräte-Suite (8 geänderte Dateien): 245 passed, 3 skipped, 1 failed =
  `test_geraete_o3_rollen.py::test_je_radar_gruppe_ein_querlink_mit_deep_link`
  — der benannte vorbestehende iPhone-18-Querlinks-Rot, nicht angefasst.

## Screenshots (harte Abnahme, angesehen)

`screenshots/d4-{vergleich,radar,verlauf,katalog}-{1440,390}.png` — Leitzahl
dominiert je Reiter, ein Satz/kein Satz vor der Grafik, Kurve im Viewport
(Verlauf 390), Export nur noch am Fuß. Bild-Analyse bestätigt: „466,80 €"
(1440) bzw. „919,00 €" (390 Verlauf) dominieren, kein Umbruch-Chaos.

## Bewusst offen

- H1 (34 px) > Leitzahl (30 px) auf 390 — Grenze der Falz 11c; Titel-
  Verkleinerung wäre eine Lead-/Antonio-Entscheidung.
- Radar 390: nach Reiter-Klick springt der Viewport (SVG top=0), Sätze dann
  nicht mehr über der Falz messbar — Struktur identisch zu 1440.
