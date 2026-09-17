# P3/C1 — Katalog-Datenquelle auf Modellebene + Ansichts-Export (17.09.2026)

Auftrag: P3 Bau-Auftrag 1 + 4 (Strategie Geraete v3). NUR Python + Export —
Vorlage/Umschalter/JS baut C2, Tests schnürt C3. Nicht committet.

## Geänderte Dateien

| Datei | Was |
|---|---|
| `src/telco_radar/report/geraete_view.py` | `_katalog_zeile()` extrahiert (baut jetzt auch `sku_id` an die Zeile); NEU `katalog_modellzeilen()` + `_interleave_modelle_je_hersteller()` + `_buendel_je_anbieter_modell()` + `_tco_spalte()` + Konstanten `TCO_LEER_*`; `aufbereiten()` trägt `katalog_modelle` (Notzustand `leer()` ebenfalls) |
| `src/telco_radar/report/geraete_export.py` | NEU `modell_barpreis_csv()` / `modell_tco_csv()` + Spalten `SPALTEN_MODELL_*`; `schreibe_exporte(modelle=…)` schreibt 2 neue CSV; `leer()` erweitert |
| `src/telco_radar/report/html.py` | gibt `modelle=geraete["katalog_modelle"]` an `schreibe_exporte` durch |
| `tests/test_geraete_katalog_modelle.py` | NEU, 17 Tests ( additive — für C3/Prüfer) |

## Messzahlen (echter Bestand `data/state/`, 17.09.2026)

- **Modellzeilen vor/nach: 636 Listungszeilen → 111 Modellzeilen** (636 = Bestand;
  die gerenderte Seite zeigte 566 vom älteren DB-Stand, katalog.md S. 1).
- **0× „ohne Preis" in den Daten**: 0 Modellzeilen und 0 Aufklapper-Zeilen ohne
  Preisform (`ab_preis`/`zuzahlung`/`buendel_monat` alle leer = 0 Zeilen).
- **1&1-Zeilen mit Bündel-Angabe: 37 von 37** — alle 37 Listungen ohne Barpreis
  tragen `buendel_monat` + Beleg (Tarif, URL, Abrufdatum) aus dem Bündel-Store.
  Beleg-Stichprobe iPhone 17 256: 42,99 €/Monat, „1&1 All-Net-Flat S",
  mobile.1und1.de, 2026-09-17. Nur-im-Bündel-MODELLZEILE: 1 (Nothing Phone 4a
  Pro 128, ab 25,99 €/Monat von 1&1 — einziges Modell ohne jeden Barpreis).
- **B1-Gegenbeweis**: 9 refurbished Listungen im Bestand; bei 8 davon wäre der
  erneuerte Preis „ab"-Preis geworden (iPhone 14 128: 445 statt 721 € = −38 %).
  `barpreise()` (nur `VERGLEICHBARE_ZUSTAENDE`) hält alle draußen; die Zeilen
  bleiben im Aufklapper, mit Zustands-Etikett.
- **TCO je Modell**: 92 mit Zahl, 19 „kein Bündel gemessen", 54 mit `delta_kurz`
  (nur mit Referenz — 68 Modelle haben eine). „kein vergleichbares Bündel
  gemessen": 0 im Bestand (der eine Fall, Galaxy S24 Ultra 512, liegt in den 5
  nur-TCO-Modellen ohne Listung) — Zustand existiert und ist getestet.
- **Spanne (wesentlich, ODER-Verknüpfung 3 %/15 €)**: 49 von 111 Modellen.
  Beispiele: iPhone 17 Pro 256 [1179, 1449], Fairphone 6 [539, 599].
- **CSV**: `site/exporte/geraete-modell-barpreis.csv` 111 Zeilen (+Kopf),
  18 155 B; `geraete-modell-tco.csv` 111 Zeilen (+Kopf), 19 180 B. Beide UTF-8
  mit BOM, Semikolon, CRLF, Dezimalkomma (verifiziert). Barpreis-CSV: 0 Zeilen
  ohne Preisform, 0 Zeilen mit BEIDEN Preisformen, 1 nur-im-Bündel-Zeile.
  TCO-CSV: 19 Zeilen ohne Zahl, alle 19 mit Grund in der Statusspalte.
  `geraete-aktuell.csv` bleibt unangetastet (Listungs-Export, 636 Zeilen).
- **Selbsttest render_site (MIT cfg)**: läuft durch; `site/` danach byte-identisch
  zum committeten Stand — einzige Differenz: die 2 neuen (untracked) CSVs. C1
  ist zur ausgelieferten Seite rein additiv; C2 schaltet die Vorlage um.

## Tests

- Neue Datei `tests/test_geraete_katalog_modelle.py`: **17 passed** (ab-Preis mit
  Beleg, B1, nur-im-Bündel, Monatspreis-Summe tarifer+rate, Spanne-Schwelle,
  Schlüssel-Gleichheit, Deckel zählt Modelle, TCO-Wahl/Leerzustände,
  Export-Disziplin).
- `-k geraete` über die Suite: **1422 passed / 3 failed / 6 skipped** — die 3
  Roten sind exakt die dokumentierten vorbestehenden (Galaxy Tab S11 Ultra
  Auto-Katalog, Nachtlauf-Nullzeilen, iPhone-18-Querlinks); keine neuen.
- `tests/test_seiten_zahlen.py`: 97 passed.

## Feldliste `katalog_modelle` je Modellzeile (für C2)

`schluessel` (= `geraete_tco_karten.modell_schluessel`, geteilt mit TCO-Ansicht)
· `device_id modell hersteller titel generation serie segment speicher`
· Barpreis-Ansicht: `ab_preis ab_anbieter ab_beleg{betrag,quelle_url,abgerufen_am}`
  `anbieterzahl anbieter[] farben[] spanne[von,bis]` (spanne leer = unwesentlich)
· Bündel-Zustand: `nur_buendel buendel_monat buendel_anbieter buendel_tarif
  buendel_beleg{quelle_url,abgerufen_am}`
· TCO-Ansicht: `tco_ab tco_anbieter tco_monat tco_delta tco_delta_prozent
  tco_delta_kurz tco_band tco_beleg{quelle_url,abgerufen_am} tco_leer`
· Aufklapper: `zeilen[]` (Listungszeilen, Bauform `katalogzeilen` + `sku_id`;
  zeilen ohne Preis tragen `buendel_monat buendel_tarif buendel_url
  buendel_abgerufen_am`) · `listungen` (Zahl) · `zeilen_rest` (Deckel
  `KATALOG_SICHTBAR`=12 zählt MODELLE; `block_rest` entfällt auf dieser Ebene).
Ordnung: Modelle je Hersteller reihum (B5), im Hersteller nach Segment/Baureihe/
Generation (B1), Hersteller ohne Namen ans Ende (B9).

## Offene Sorgen / Übergaben

1. **`katalogtabelle` (Listungs-Ebene) bleibt im Kontext** — die heutige Vorlage
   rendert sie weiter; C2 ersetzt den Reiter-Körper durch `katalog_modelle`
   und wirft `katalogtabelle` dann mit weg (E5-Regel toter Code).
2. **`anbieterzahl` zählt Anbieter der Listungen** (Regal-Sicht, inkl. 1&1 ohne
   Barpreis) — bewusst EINE Zahl, Bedeutung im Docstring. Neue ZAHLEN auf der
   Seite gehören nach dem C2-Umbau in `tests/test_seiten_zahlen.py` (ohne
   get_text-Trenner lesen).
3. **Export-Knöpfe**: `geraete.export.modell_barpreis` / `.modell_tco` liegen
   fertig im Kontext (datei/zeilen/bytes) — die Knöpfe in der Kopfzeile baut C2,
   sonst ist E5 „4/4 exportierbar" auf der Seite nicht sichtbar (in den Daten
   sind es jetzt 6 Dateien).
4. **Beobachtung, nicht gefixt**: Auto-Modelle `apple-iphone-18-pro-1` /
   `-2048` (speicher_gb=1/2048 aus der E4-Auto-Erkennung) stehen als eigene
   Modellzeilen — dieselbe Klasse wie das vorbestehende Rot „Galaxy Tab S11
   Ultra Auto-Katalog", P5-Auftrag 3 (Anker) ist der Ort dafür.
5. Die Bündel-Angabe greift auf (Anbieter, Modell)-Ebene zu, nicht je SKU:
   22 der 37 1&1-Zeilen haben ihren eigenen SKU-Match im Store, 37 von 37 über
   das Modell. Das „ab" nennt den billigsten Bündel-Tarif des Modells beim
   selben Anbieter — mit dessen Beleg. 1&1-Listing-Feld und Store stimmen bei
   allen 22 SKU-Matches auf den Cent überein (nachgemessen).
