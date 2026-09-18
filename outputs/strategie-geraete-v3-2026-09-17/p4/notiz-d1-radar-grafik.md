# D1 — Die Radar-Tafel wird Grafik (P4, 18.09.2026)

Auftrag: „Wo sind wir teuer?" liest sich als Bild statt als 746-Zeilen-Wand.
Nicht committet, nichts unter data/state geschrieben. Chromion/Playwright
lokal; alle Zahlen unten selbst gemessen (Skript `mess_d1.py`, Screenshots
`screenshots/d1-*.png`).

## Was gebaut wurde

1. **Servergerendertes SVG** — `grafik()` / `_grafik_svg()` in
   `src/telco_radar/report/geraete_radar.py` (neu, mit `GRAFIK_MAX = 12`),
   zwei Varianten (`svg.wr-gr--breit/schmal`, Mediaquery zeigt genau eine —
   gemessen: 1440→breit, 390→schmal), CSS in `style.css` (`.wr-gr-*`).
   Balken je Modell(-Speicher) = **Delta zum Vodafone-Preis in Euro**,
   Nulllinie = Vodafone mit GENAU EINEM Etikett, Wert je Balken an der
   Spitze, `<title>` nennt beide Preise der Messung (Belegzwang).
   Barpreis-Ebene wie die Alarmtabelle: gelesen aus den fertigen
   `vergleich(ohne_vertrag)["zeilen"]` (nur vergleichbare Neugeräte) — keine
   zweite Preisrechnung; für „Vodafone günstiger"-Zeilen EINE Subtraktion
   (VF-Preis minus günstigsten der teureren), dokumentiert im Modulkopf.
   Farbe nach Richtung: Ink = VF teurer, Blau (--al-bestpreis) = VF
   günstiger, **Rot genau der größte Abstand** (Spitzen-Balken, `--spitze`).
   Palette validiert (Skill-Validator): #e60000/#2b5bd7 auf #f6f4ee —
   CVD ΔE 29,4 (protan) / 36,3 (tritan), Kontrast ≥ 3:1: PASS.
   Leerzustand benannt („Noch keine vergleichbaren Barpreise erhoben …").
2. **Beide großen Tabellen als Aufklapper unter der Grafik** (nichts
   gestrichen: alle Zeilen, Filter, Sortierung, „alle N anzeigen" im DOM —
   1285 `<tr>` vorher wie nachher). Alarm-Details im Leerzustand `open`
   (E5-Regel: Leersatz ist Aussage, kein Klickfall).
3. **Rot-Deckel** (CSS): `.wr-prozent--negativ` → `color:inherit` (Klasse
   bleibt als Semantik; Rot nur noch `--spitze` an genau einer Zeile),
   `.gr-a-unser--zurueck` → Ink, `.gr-pille--kritisch` → Ink-Fläche
   (schwerste der vier Pillen; Stufe liest das Wort), `.gr-chip--kritisch b`
   → Ink, `.gr-a-eigen` → Ink fett (Identität, kein Alarm), feste
   Filter-ETIKETTE eigene Klasse `.gr-filter--fest` (graue Fläche) —
   `--an` bleibt dem AKTIV-Zustand eines GESETZTEN Filters vorbehalten
   (Browser-Test dazu unberührt grün). Die 48–60× wiederholte Zeile
   **„Vodafone-Basis: …"** ist EINE Legende (`.wr-basis-legende`) über der
   Modell-Liste; der VF-Band-Betrag steht je Anbieter-Zeile selbst.
4. **2b im selben Zug**: Aufklapper „Bei Wettbewerbern gelistet, bei
   Vodafone nicht" (`#gr-sortiment`, Markup/ID unverändert) aus dem
   Katalog-Reiter **unter die Grafik** der Radar-Tafel verschoben
   (design.md §3c „Radar-Material im Katalog"); steht GENAU EINMAL.

## Messzahlen vorher → nachher (initialer Zustand, Reiter Radar)

| Messgröße | vorher | nachher |
|---|---|---|
| rot eingefärbte DATEN-Elemente sichtbar | **40** | **1** (der Spitzen-Balken) |
| Rot-Daten im DOM (ohne Link-Akzent) | 318 | 8 (Balken 2×, title 2×, Pille 1, Prozent 1, Lifecycle-Eigen 2) |
| Rot DOM gesamt (inkl. Links) | 811 | 501 (493 davon `a`/`gr-sprung` — Rot ist die LINK-Farbe der Site, CLAUDE.md §5 „Rot markiert Rubriken, Dringlichkeit und Links"; kein Daten-Rot) |
| Tabellenzeilen sichtbar ohne Klick | 63 | **7** (6 Händler-Zeilen + Kopf) |
| Tabellenzeilen im DOM | 1285 | 1285 (nichts gestrichen) |
| Tafelhöhe 1440 px | 2235 | **1653** |
| Tafelhöhe 390 px (mobil) | 3727 | **2575** |
| SVG in #tafel-radar | 0 | 2 im DOM, genau 1 sichtbar je Breite (gemessen) |
| `pruefe_portal.py` 11b (Reiterhöhen) | radar ~3216 (E3-Messung) | **radar 2400 px** < 3000 — BESTANDEN |

Die im Auftrag genannte Vorher-Höhe 4603 px war an meinem Baum nicht zu
reproduzieren (design.md maß am 17.09. 3784 px; ich messe 3727 px am
verschobenen Wochenkarten-Stand von 2a). Alternativlos sind die eigenen
Vorher-Messungen desselben Werkzeugs.

**N=12, messbar begründet:** 12 Reihen à 30 px + Kopf = 402 px SVG (gemessen
viewBox 1120×402) — Grafik samt Überschrift über der Falze eines 900-px-
Schirms, mobil (40 px/Reihe) unter 500 px. Kein inhaltlicher Bruch dahinter:
die Plätze 13–16 tragen +134,90 € bis +110,90 €, alle dieselbe Richtung —
N=12 kürzt Länge, nicht Aussage. Basis: 58 vergleichbare Zeilen; die Spitze
(größter Abstand ZUUNGUNSTEN Vodafones, iPhone 16 · 128 GB, +242,90 €) wird
bei der Auswahl erzwungen, damit Rot in Grafik und Tabelle dasselbe Modell
nennt. Gibt es keinen solchen Fall, gibt es keinen roten Balken.

## Tests umgestellt (bewusst, je Vorher-rot bewiesen am verschobenen Stand)

- `tests/test_wettbewerbsradar_alarme.py::…steht_im_geraetekatalog`
  (Assert auf `#tafel-katalog #gr-sortiment` → `#tafel-radar`) — die
  E3-Festnagelung kehrt, von Forderung 7 gedeckt; Vorher-rot in Docstring.
- `…::test_der_aufklapper_steht_nicht_zweite_mal_auf_dem_radar` —
  Umkehrung: Radar gefordert, Katalog verboten (Dopplungsschutz bleibt).
- `tests/test_geraete_seite.py::test_was_vodafone_nicht_fuehrt_…` —
  Eltern-Assert `#tafel-katalog` → `#tafel-radar`. Das ist der nachgefragte
  „Portfolio-Pin vom 03.09.": der war bereits E3-mäßig zum Katalog-Pin
  geworden (docstring lagen O2→E3); ein aktiver `#tafel-portfolio`-Pin
  existiert nicht mehr (greift nur noch als Verbot, `test_tafel_portfolio_
  ist_weg`, unberührt grün).
- `tests/test_geraete_seite.py::…filterleiste…` — `gr-filter--an` →
  `gr-filter--fest` für die zwei festen Etiketten (Rot-Deckel).
- `tests/test_geraete_radar_tafel.py` — `test_drei_sektionen…` (3→4 Köpfe,
  Grafik zuerst) und `…haendler_sektion_steht_nicht_mehr…` (Liste um
  `wr-grafik` ergänzt).
- Browser-Helper öffnen die neuen Aufklapper: `_radar_frisch`
  (`test_geraete_reiter_browser.py`) und `_radar_zeigen`
  (`test_geraete_radar_sprung_browser.py`) — Interaktionstests sonst
  blind gegen unsichtbare Zeilen.
- **Neu (4):** `test_die_radar_tafel_traegt_eine_balkengrafik`,
  `test_die_grafik_traegt_genau_einen_roten_balken`,
  `test_die_vodafone_basis_steht_als_eine_legende`,
  `test_rot_ist_akzent_nicht_teppich` (DOM-Proxy ≤ 10).

## Befunde nebenbei

- **Chromiumlüge bei `<details>`:** Inhalt geschlossener Details bekommt
  trotzdem Client-Rects (übersprungenes Layout) — `getClientRects`/
  `offsetParent` sind als Sichtbarkeitstest ungeeignet. Mein Messskript
  prüft deshalb per Vorfahren-Suchlauf + `checkVisibility()`.
- **Sibling-Rot, NICHT D1** (an deren Agenten gemeldet hier):
  `test_der_tafelkopf_polt_nur_die_sektionen_mit_vorzeichen` (D4 hat den
  Tafelkopf gestrafft, „Betrag ohne Vorzeichen" steht nicht mehr wörtlich),
  `test_geraete_leer_zustaende.py::test_export_ohne_zeilen_nennt_die_null`
  (D3 hat die Export-Knöpfe in die Fußzeile `.gr-export-fuss` verschoben,
  der Test sucht noch im Hero), `pruefe_portal` Kriterium 13
  „Vergleich 18 048 Z > 6000" (Auftrag 5, Text-Deckel).
- **Vorbestehende Rot nicht angefasst** (wie befohlen): Galaxy-Tab-S11-
  Ultra-Auto, Nachtlauf-Nullzeilen, iPhone-18-Querlinks.

## Bewusst / offen

- Der rote Spitzen-Balken ist im Moment der EINZIGE Balken mit
  Gegenrichtung — die 7 „Vodafone günstiger"-Zeilen des Bestands liegen
  unter dem |Δ€|-Deckel; der Code zeichnet sie (blau, links der Nulllinie),
  sobald sie die Top 12 erreichen.
- Tooltips als natives `<title>` (funktioniert überall, kein Framework);
  ein Hover-Panel wäre ein eigener Bau-Auftrag.
- Die Referenz-Zeile („Vodafone-Basis", inkl. Näherungs-Kennzeichnung) ist
  aus der Tafel — der VF-Band-Betrag je Zeile ist dieselbe Zahl, die die
  Abweichung gerechnet hat; die Näherungs-Kennzeichnung lebt im
  Vergleichs-Reiter (E2-Zeitreihe).
- Händler-Tabelle blieb sichtbar (6 Zeilen): der Auftrag stellt nur die
  Alarm-/Abweichungs-Tabelle als Aufklapper.
