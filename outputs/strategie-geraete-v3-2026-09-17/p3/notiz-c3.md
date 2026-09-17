# P3/C3 — der Testumbau auf Modellebene + Export-Knöpfe (18.09.2026)

Auftrag: P3 Bau-Auftrag 3 (Strategie Geraete v3) auf C1 (Datenmodell) und
C2 (Vorlage/Umschalter). Nicht committet, nichts unter data/state geschrieben.

## Geänderte Dateien

| Datei | Was |
|---|---|
| `src/telco_radar/report/geraete_view.py` | Kontext-Key `katalogtabelle` ENTFERNT (aufbereiten + leer); `katalogzeilen()` + `_interleave_je_hersteller` + `_katalog_bloecke` + `_interleave_je_anbieter_im_block` + `BLOCK_SICHTBAR` gelöscht (E5 toter Code — nichts rendert sie, `katalog_modellzeilen` nutzt `_katalog_zeile`/`_katalog_zeile_schluessel`/`_interleave_modelle_je_hersteller` direkt); Kommentare geglättet |
| `src/telco_radar/report/templates/geraete.html.j2` | ZWEI Export-Knöpfe „Katalog Barpreis (N)"/„Katalog TCO (N)" in der Kopfzeile — E5 „alle Zahlensektionen exportierbar" war ohne sie verletzt (C1/Übergabe 3: Daten lagen fertig im Kontext, Knöpfe fehlten) |
| `src/telco_radar/report/geraete_bereinigung.py` | nur Docstrings: Verweise von `katalogzeilen()` auf `_katalog_zeile()` umgebogen |
| `tests/test_geraete_seite.py` | 11 Stellen neu geschnürt: Export-Test (DOM-Modellzeilen + Aufklapperzahl == Export-Zeilen; Erwartung `_modell_schluessel_fixture()` statt `_bestand_ids`), Zahlen-Test (Rubrik/DOM/Aufklapper == MODELLZAHL, Export-Knopf == Listungszahl, `#gr-kmehr` fehlt unter dem Deckel), 5 `test_katalogzeilen_*` → `test_modellzeilen_*` (B6/B1/B5/B8/B9 eine Ebene höher), Modell-Tabelle (8 Köpfe, `> thead` gegen Aufklapper-Echo), Verfügbarkeit im Aufklapper (`gr-pille--unklar`), ABGELEITETER Zustand im Aufklapper (Zellen 2/4), Alarm-Test: „Bestand"-Etikett im Aufklapper statt „Verfügbar"-Spalte, Sortierbarkeit: Radar streng, Katalog Wert↔Zelle-Deckung |
| `tests/test_geraete_reiter_browser.py` | 4 geplante Roten geschnürt: Zustandsfilter → Ansichtsregler-Default (barpreis aktiv, 4/8 Zellen sichtbar), Vorbelegung == Modellzahl 28, B2 zwei Klicks auf `preis`, B3 Knopf verspricht Modellzahl; B7[tafel-katalog] auf Aufklapper-Anker + NEU Modellzeilen-Anker („bei X↗"); P1-Echtbestand-Gegenprobe über `katalog_modellzeilen`; P1-Blockdeckel → Deckel zählt Modelle; NEU NaN-Sortierung unten (beide Richtungen, C2-Empfehlung) |
| `tests/test_seiten_zahlen.py` | NEU `_geraete_katalog_site`-Fixture (1&1 ohne Barpreis MIT Bündel, Spanne, TCO) + 4 Tests: 0× „ohne Preis" (mit Gegenprobe, dass die Fixture den Fall aufspannt), Bündel-Zustand wortlich (Modellzeile + Aufklapperzeile + Beleg-Link), EIN Preisformat je Spalte je Ansicht (Regex, Monatsbetrag nur mit Kennwort), Modellzahl an allen Orten (OHNE get_text-Trenner) |
| `tests/test_geraete_export.py` | +3 Tests: Modellzahl statt Listungszahl je Modell-CSV, BOM/Semikolon/Dezimalkomma der zwei neuen Dateien, Leerfall ohne `modelle`-Argument |
| `tests/test_geraete_leer_zustaende.py` | `DATEIEN` um die zwei Modell-CSV erweitert (4→6), Erwartung aus `len(DATEIEN)` |
| `tests/test_geraete_export_mobil_browser.py` | 4→6 Knöpfe (Telefon: Reihe rollt weiter in sich, Desktop-Reihe unangetastet — beides gemessen grün) |
| `tests/test_geraete_preisform_raten.py`, `tests/test_geraete_zeitreihe_ansicht.py` | 2+1 Stellen: `katalogzeilen()`→`_katalog_zeile()`, `katalogtabelle`→`katalog_modelle` |
| `outputs/.../p3/mess_c3_screenshots.py` + `screenshots/c3-*.png` | Abnahme-Skript + 6 Screenshots |

## Messzahlen (echter Bestand, 18.09.2026)

- **`-k geraete`: 1427 passed / 3 failed / 6 skipped** — die 3 Roten sind
  exakt die vorbestehenden (Galaxy Tab S11 Ultra Auto-Katalog
  `test_tablets_und_router_bleiben_draussen`, Nachtlauf-Nullzeilen
  `test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen`, iPhone-18-
  Querlinks `test_je_radar_gruppe_ein_querlink_mit_deep_link`); am HEAD
  reproduziert, nicht angefasst. Vor C3: 1411/14/6 (C2-Stand), davor
  1422/3/6 (C1-Stand).
- **`tests/test_seiten_zahlen.py`: 101 passed** (vorher 97, +4 neue).
- **`tests/test_geraete_seite.py`: 83 passed / 4 skipped**, komplett grün.
- **`pruefe_portal.py`: 18 bestanden / 0 durchgefallen**; Reiterhöhen
  tco 2593 · radar 2997 · verlauf 1809 · **katalog 1946 px** (Grenze 3000).
- **Abnahme am gerenderten `site/geraete.html`**: **0× „ohne Preis"**
  (vorher 36×) · **111 Modellzeilen** + 111 Aufklapper + 636 Aufklapper-
  Listungszeilen (== `geraete-aktuell.csv`) · Rubrik-Zahl 111 · 1×
  „nur im Bündel" · 19× „kein Bündel gemessen" · **6 Export-Knöpfe**
  („Katalog Barpreis (111)", „Katalog TCO (111)") · **0 Beträge außerhalb
  des einen Formats** `d{1,3}(.d{3})*,dd €` je Spalte; Ø-Spalte
  einheitlich ohne „/Monat" (Einheit im Kopf).
- **Screenshots** (p3/screenshots/, Server 8768 gekillt): 1440+390 ×
  barpreis/tco/tco-auf, je visuell geprüft — Mobil rollt im Behälter
  (Seitenbreite 390 px, programmatisch gemessen), Aufklapper zeigt alle
  6 Listungs-Spalten, Umschalter-Aktivzustand rot.

## Fallstricke, die der Umbau gefunden hat

1. **`#gr-katalogtabelle thead th` trifft auch die Aufklapper-Tabellen**
   (html.parser hängt deren Kopfzeilen an denselben Selektor) — Kind-
   Selektor `> thead th` nötig; dasselbe für `tbody tr` (th-Zeile ohne
   td crasht `r.select_one("td").get_text()`).
2. **`getComputedStyle(zelle).display` bleibt `table-cell`, wenn nur ein
   VORFAHRE versteckt ist** — der Ansichts-Sichtbarkeits-Test misst
   `z.cells` der Modellzeile, nicht td-Selektoren quer über Aufklapper.
3. **Die 3 vorbestehenden Roten bleiben dokumentiert offen** (P5-Auftrag
   3 „Anker" ist der Ort für die Auto-Katalog-Fälle).

## Offene Sorgen / Übergaben

1. **Export-Knöpfe habe ich (C3) gebaut**, obwohl C2s Lead-Auftrag sie
   P4 zugedacht hatte — ohne sie war die E5-Regel „4/4 Zahlensektionen
   exportierbar" mit der NEUEN Zahlensektion Katalog verletzt (C1-Notiz
   Übergabe 3). Prüfer bitte gegenlesen: Beschriftung „Katalog
   Barpreis/TCO" passt zur Einheiten-Debatte (S4-Rest aus E5: „die
   Einheit in den Export-Knopfbeschriftungen ist inkonsistent").
2. **Nicht gebaut**: Anbieter-Filter auf Modellebene (braucht Contains-
   Logik, C2-Übergabe 4) — P4-Entscheidung; B7-Erbe „nur der Bestpreis-
   Händler verlinkt, alle Händler im Aufklapper" ebenfalls P4.
3. **`data-s-preis` bleibt bei nur-im-Bündel-Zeilen leer** (1 Zeile im
   echten Bestand) — bewusst: Preisarten nie mischen; die Zeile fällt
   beim Preissortieren ans Ende.
4. Screenshots aus C2 (`p3/screenshots/`, 6 Stück) sind von meinem
   Skript nicht angetastet; meine liegen als `c3-*` daneben.
