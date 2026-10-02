# P3 — Notiz des Code-Prüfers (18.09.2026)

Adversarial-Prüfung des P3-Diffs (Arbeitsstand gegen `64a8f2a`), Schwerpunkt
Testumbau. Vollständiger Bericht: `p3/pruefung-code.md`.

## Ergebnis

- **Suite `-k geraete`: 1427 passed / 3 failed / 6 skipped** — die 3 Roten
  exakt die dokumentierten Vorbestehenden (Galaxy Tab S11 Ultra Auto-Katalog,
  Nachtlauf-Nullzeilen, iPhone-18-Querlinks). Keine neuen.
- **S1: 0. S2: 1. S3: 0. S4: 6 gebündelt.**

**Der S2:** `katalog_modellzeilen` bekommt `tco_db.buendel()` — bei unlesbarem
`geraete_tco.json` liefert das still `[]`, und der Katalog fällt auf
**37× „ohne Preis" + 1× „kein Preis gemessen"** zurück (Simulation am echten
Bestand). Genau DIE P3-Regel, im Normalbetrieb zu 0 gemessen, kippt im
Fehlerfall. Der TCO-Reiter benannt `lesbar`; die neue Konsumstelle nicht.
Fix in `aufbereiten()` (geraete_view.py:1598): bei `not tco_db.lesbar`
`buendel_aus_listungen(bestand)` — die 37 Bündel-Angaben stehen in den
1&1-Listungen selbst.

**S4 (gebündelt):** CSV „Tarifband" als Raw-Band (klein/mittel/gross) ·
Knopf-Einheiten inkonsistent (E5-Rest) · `schreibe_exporte` 5 Parameter ·
Test auf privates `_katalog_zeile()` · `_geraete_katalog_site`-Fixture ohne
cfg · `len(DATEIEN)` statt harter Zahl · `_tco_spalte` ohne laufzeit-Guard
(heute Konstante 24, gemessen {24: 506, None: 188}).

## Bestätigt (Messzahlen)

- ab-Preis min über NEU: Pixel 10 Pro Fold 256 → 1.603,00 € o2; Xiaomi 17T Pro
  512 → 865,00 € congstar; iPhone Air 256 → 891,00 € congstar. 9 refurbished
  draußen gehalten (iPhone 14: 445 statt 721 €).
- 1&1 „nur im Bündel" 37/37 mit Beleg aus geraete_tco.json; keine Rate als
  Barpreis.
- TCO: 92 mit Zahl / 19 „kein Bündel gemessen" / 0 „kein vergleichbares";
  delta_kurz 54, alle mit Referenz.
- Testumbau scharf: Zeilen == 111 an DOM, Aufklapper, Export, Deckel;
  `_b5_modellzahl()`=28 ausgeschrieben; Lookup-Vollständigkeit als exakte
  Länge; P1-Gegenprobe `groesster > halbe_sichtflaeche`; NaN-Fall in der
  Fixture wirklich vorhanden.
- `test_geraete_faden` / `test_geraete_o3_rollen` / o4 / wettbewerbsradar:
  diff-stat leer — nichts entschärft.
- CSV: BOM, Semikolon, CRLF, Dezimalkomma, 111 == Modellzahl.
  E5: 6 Knöpfe. site/-Sync: render_site MIT cfg → 5 Dateien byte-identisch.

## Hinweis für den Commit

`tests/test_geraete_katalog_modelle.py` (neu, 17 Tests) und
`site/exporte/geraete-modell-{barpreis,tco}.csv` sind untracked — beim
Commit mit `git add` erfassen (die CSVs entstehen bei jedem Render neu,
site/ wird aber committet).
