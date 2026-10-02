# P1 / A1 — Rechenweg je Messung, serverseitig (notiz-a1)

Stand 17.09.2026. Auftrag: aus der Historien-Zeile je Messung eine
POSTENLISTE bauen und als `<template data-m=...>` (Variante V1,
vergleich.md) unter das SVG hängen. Nichts in data/state geschrieben,
nicht committet, app.js/style.css/kacheln nicht angefasst.

## Geändert

| Datei | Was |
|---|---|
| `src/telco_radar/report/geraete_zeitreihe.py` | `_messungen()` (EINE Historie-Lesung, behält die GANZE Zeile je Punkt inkl. Stand-Bündel; Günstigste-Regel unverändert, strikt `<`), `_serien()` jetzt Ableitung daraus; `_rechung()` (Postenliste: Zuzahlung, Anschlusspreis, Tarif × 24, Rate × min(Laufzeit, 24); Beträge aus `tco_24().bestandteile` — EINE Rechnung, nur zerlegt), `_rechung_html()`, `_naeherung_html()` (Leerzustand), `_rechenwege_html()` (je Serie/Messung ein `<template data-anb data-m>`); SVG-Kreise tragen `data-anb`/`data-m` + unsichtbare Trefferfläche `gr-zr-hit` r=12 (NICHT `gr-zr-treffer` — die Klasse gehört der Suchvorschau); `aufbereiten()` liefert `rechenweg_html` je Paar + 2 Protokollzeilen |
| `src/telco_radar/report/templates/_geraete_zeitreihe.html.j2` | Container `div.gr-zr-rechnungen[hidden]` mit den Vorlagen ans Ende der `section.gr-zr-graph` (unter dem SVG; gilt für First Paint UND Fragment, dasselbe Makro) |
| `tests/test_geraete_zeitreihe_rechenweg.py` | NEU, 18 Tests |
| `outputs/strategie-geraete-v3-2026-09-17/p1/schnittstelle-rechenweg.md` | NEU: Format-Doku für A2 mit echtem Beispiel-Markup (aus dem gerenderten Fragment kopiert) + CSS-Klassen-Tabelle |

## Messzahlen

- **Summenformel verifiziert an ALLEN 2562 Historien-Zeilen**: `gesamt`
  = `tco_24` (Zuzahlung + Anschluss + Tarif × 24 + Rate × min(LZ, 24)
  bzw. zusammen-Form Bündel × min(LZ, 24)) — **2562/2562 exakt**,
  darunter beide echten Beispiele aus vergleich.md (o2 12.09.:
  37 + 39,99 + 24×14,99 + 24×19,00 = 892,75 ✓; 1&1: 420 + 39,90 +
  24×49,99 = 1.659,66 ✓). Bei der Aufbereitung: 1327 Messungen gerechnet,
  **0 Abweichungen** von der eingefrorenen Leitzahl.
- **1285 Templates für 1285 Punkte** in den Serien (1:1; je (Modell,
  Band, Anbieter, Tag) das günstigste Bündel — derselbe Punkt wie im SVG).
- **Näherungs-Leerzustände im echten Bestand: 0** (Vodafone führt in
  jedem Band eigene Bündel, 1484 Historien-Zeilen). Mechanismus gebaut
  und per Fixture getestet; der Leer-Satz ist wortgleich der
  Bündel-Karten-Hinweis (Test hält beide zusammen).
- **Fragmentgröße `site/data/geraete-zeitreihe.html`:**
  **vorher 1.132.101 B → nachher 2.968.207 B (+1.836.106 B, +162 %).**
  Die Erwartung der Strategie (+150–300 kB) ist damit **um Faktor ~6
  überschritten** — Ursache: 1285 Blöcke à ~1,05 kB (Kopf, 4 Posten,
  Summe, Beleg-URL) × Struktur-Overhead; die V1-Schätzung lag bei der
  Blockgröße falsch. Bereits gestraft (innere data-Duplikate weg,
  Belegdatum Kurzform): 3.031.788 → 2.968.207 B. **gzip transportiert
  nur 124.568 B (vorher 52.678 B, +71.890 B)** — die Blöcke sind
  hochrepetitiv. PM-6-Deckel ist bewusst P5 („Deckel-Entscheidung erst
  mit echten Messdaten") — diese Zahl ist die Messgrundlage dafür.
- **`site/geraete.html`:** 1.406.611 → 1.571.870 B (+165 kB, +11,8 %;
  First Paint trägt die Vorlagen des Startpaars).
- **pruefe_portal.py: 18 bestanden / 0 durchgefallen** — 11b
  Reiterhöhe tco 2565 px (< 3000), 11c Antwort-Satz endet bei 797 px
  (Falz 844), Graphkopf 837 px.
- **Tests:** neu 18 (alle grün); Zeitreihen-Suite komplett
  (`test_geraete_zeitreihe*`: 184 passed, 4 skipped); Umfeld
  (`test_geraete_seite`, `test_geraete_reiter_browser`, `o3_rollen`,
  `tco_zustand`, `leer_zustaende`, `faden`, Browser-Exporte): 216
  passed, 1 vorbestehendes Rot (s. Sorgen); `test_seiten_zahlen` +
  Querlinks + Leerzustände: 104 grün.

## Sorgen / offene Punkte

1. **Fragment +1,8 MB übersteigt die Strategie-Erwartung um Faktor 6**
   (Zahlen oben). Kein Deckel gebaut — das ist P5s Entscheidung (PM-6),
   und ein Deckel wäre eine Auswahl nach Listenposition (B1-Regel).
   Lead sollte die Zahl zur Kenntnis nehmen; gzip-Argument (+72 kB
   transportiert) mildert, ersetzt aber keine Entscheidung.
2. **Vorbestehendes Rot, nachgemessen am unberührten Baum (stash):**
   `test_geraete_o3_rollen.py::test_je_radar_gruppe_ein_querlink_mit_
   deep_link` — Radar-Links auf iPhone-18-Modelle, die unter
   `AUTO_SICHTBAR_AB_MESTAGEN = 2` nicht im Selektor stehen. Genau der
   Fall aus der Strategie (P5-Auftrag 1); nicht meine Baustelle.
3. **Preis-Klick auf die Antwort-Satz-Zahl** (A2): die Zahl nennt den
   Stand von HEUTE (Karte), Templates existieren nur zu Messtagen.
   Empfehlung dokumentiert (letzter Messtag derselben Serie); A2 muss
   es so bauen oder mit dem Lead klären.
4. **site/ ist komplett neu gerendert** (erlaubter Selbsttest mit cfg)
   — enthält dadurch auch Bestandsdatenstände, die neuer sind als HEAD
   (Bündel-Fragment, Exporte). Der Lead rendet final selbst; sonst
   entscheiden, ob dieser Stand bleibt.
5. test_seiten_zahlen.py nicht erweitert (Strategie P1 Auftrag 4 ist ein
   eigener Bau-Auftrag); meine Panel-Zahlen stehen stattdessen gegen die
   ECHTEN Historien-Zeilen in der neuen Testdatei festgenagelt.
