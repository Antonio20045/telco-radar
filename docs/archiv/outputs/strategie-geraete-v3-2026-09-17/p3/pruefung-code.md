# P3 — Code-Prüfung (adversarial), 18.09.2026

Prüfer: diff-reviewer (Code-Schwerpunkt: der Testumbau). Basis: Arbeitsdiff
gegen HEAD `64a8f2a` (18 Dateien, uncommittet). Grundlagen: STRATEGIE_GERAETE_V3.md
§P3, outputs/.../befunde/katalog.md, docs/clean-code-referenz.md, CLAUDE.md-Hausregeln
(Zustand im Schlüssel, Preisarten nie mischen, keine Mittelwerte, Belegzwang).
Nichts committet, nichts unter data/state geschrieben.

## Suite (eigener Lauf)

`-k geraete`: **1427 passed / 3 failed / 6 skipped (196,7 s)** — die 3 Roten sind
exakt die dokumentierten vorbestehenden (am HEAD reproduziert, nicht angefasst):

1. `tests/test_geraete_adapter_netzbetreiber.py::test_tablets_und_router_bleiben_draussen`
   (Galaxy Tab S11 Ultra Auto-Katalog — P5-Auftrag 3 „Anker")
2. `tests/test_geraete_lifecycle.py::test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen`
3. `tests/test_geraete_o3_rollen.py::test_je_radar_gruppe_ein_querlink_mit_deep_link`
   (iPhone-18-Querlinks auf `apple-iphone-18-pro-*`)

Keine neuen Roten. `tests/test_seiten_zahlen.py`: 101 passed.

## Prüfkatalog (docs/clean-code-referenz.md), Kurzergebnis

| Kategorie | Ergebnis |
|---|---|
| P (Tests) | PASS — 17 neue Tests (`test_geraete_katalog_modelle.py`), +3 Export-Tests, +4 Zahlen-Tests, 11 Stellen in `test_geraete_seite.py` neu geschnürt; Gegenproben vorhanden (s. u.) |
| C (Komplexität) | FLAG S4 — `schreibe_exporte` 5 Parameter (`geraete_export.py:435`), `katalog_modellzeilen` 4 (`geraete_view.py:968`) — Grenzwertig, bewusst |
| E (Benennung) | PASS — `katalog_modellzeilen`, `_buendel_je_anbieter_modell`, `TCO_LEER_*` selbsterklärend |
| F (Funktionen) | FLAG S4 — dieselben zwei Signaturen; Rechenlogik bleibt in einer Funktion je Frage |
| G (Grenzen) | FLAG S2 — lesbar=False-Fall unten; sonst PASS |
| J (JS) | PASS — NaN-Sortierfix in `sortiere()` schließt die alte Lücke („fällt ans Ende" galt im Kommentar, nicht im Code), Test prüft beide Richtungen |
| N (Namenskonventionen) | PASS |
| T (Testqualität) | FLAG S4 — Privatkonsum `_katalog_zeile()`; `len(DATEIEN)`-Erwartung; sonst PASS |

## S1

Keine. Hartregeln geprüft: seen.jsonl nicht im Diff, keine Secrets, kein Commit,
keine data/state-Schreibung, `site/`-Sync per `render_site` MIT cfg byte-identisch
bewiesen (geraete.html, app.js, style.css, beide Modell-CSVs).

## S2 (einzeln)

**S2-1 — Der neue Katalog konsumiert `TcoDB.lesbar` nicht: im Unlesbar-Fall
fällt er auf „ohne Preis" zurück und verletzt damit DIE P3-Regel.**

- Datei: `src/telco_radar/report/geraete_view.py:1598-1599` (Aufruf
  `katalog_modellzeilen(bestand, katalog, …, tco_db.buendel())` — `buendel()`
  liefert bei `lesbar=False` still `[]`) und
  `src/telco_radar/report/templates/geraete.html.j2:750` (else-Zweig
  „ohne Preis", der verbotene Fallback) bzw. `:685` („kein Preis gemessen").
- Auslöser: `data/state/geraete_tco.json` unlesbar/korrupt (z. B. abgebrochener
  Schreibvorgang des Nachtlaufs).
- Messung (Simulation am echten Bestand, TcoDB unlesbar, `buendel=[]`):
  **37 Aufklapperzeilen „ohne Preis" + 1 Modellzeile „kein Preis gemessen"** —
  die Abnahme „0× ohne Preis" (im Normalbetrieb gemessen: 0) kippt im Fehlerfall.
  Die Bündel-Angaben stehen alle 37 in den 1&1-LISTUNGEN (`preis_mit_vertrag_ab`
  + `tarif_referenz`) und wären ohne den Store verfügbar.
- Fehlerklasse: B6 („kaputte Datei sieht aus wie leere Datenlage") — derselbe
  Schutz, den der TCO-Reiter hat (`lesbar` wird in `aufbereiten()` bei
  `geraete_view.py:1567` an `geraete_tco_view` übergeben und dort benannt),
  fehlt für die NEUE Konsumstelle. Dieselbe Klasse war Phase 6a ein S1
  („`TcoDB.lesbar` wurde weggeworfen").
- Einzeiliger Fix: in `aufbereiten()` die Bündel-Quelle konditional halten —
  `buendel = tco_db.buendel() if tco_db.lesbar else buendel_aus_listungen(bestand)`
  (aus `geraete_tco_karten`, S2-C-Dedupe greift nicht, da der Store leer ist) —
  oder den Leerzustand als „Bündel-Store unlesbar" benennen statt „ohne Preis".

## S3

Keine über den S2 hinaus.

## S4 (gebündelt)

1. `geraete_export.py:147-149` — CSV-Spalte „Tarifband" schreibt das Raw-Band
   (`klein`/`mittel`/`gross`) statt des Klartextes der Seite (Klein/Mittel/Groß).
   Konsistenz mit der Seitensprache, kein Zahlenfehler.
2. Export-Knopf-Beschriftungen: Einheit inkonsistent („Katalog Barpreis (111)"
   ohne Einheit, andere Knöpfe mit) — bekannter E5-S4-Rest, von C3 selbst
   zur Debatte gestellt.
3. `tests/test_geraete_preisform_raten.py` — Test konsumiert die private
   `_katalog_zeile()` (Unterstrich); eine dünne öffentliche Hülle wäre
   stabiler gegen Umbauten.
4. Neue Fixture `_geraete_katalog_site` in `tests/test_seiten_zahlen.py` ruft
   `render_site` OHNE `cfg` auf — CLAUDE.md-Falle („ohne cfg still halbe
   Seite"); für `geraete.html` benign (der Katalog braucht kein cfg), aber
   kopierbar in den falschen Kontext.
5. `tests/test_geraete_leer_zustaende.py` — Knopf-Zahl-Erwartung aus
   `len(DATEIEN)` statt hart; Sync hält der Assert (`len(links) == len(DATEIEN)`),
   die Zahl 6 steht nirgends ausgeschrieben (schwächer gegen stilles Schrumpfen
   von DATEIEN selbst).
6. `geraete_view._tco_spalte()` wählt `min(kandidaten, key=gesamt)` ohne
   laufzeit-Filter bei statischem „TCO-24"-Kopf — heute UNWIRKSAM, weil
   `karte["laufzeit"]` seit Ticket TCO24-1 die Konstante 24 ist (Bestand
   gemessen: {24: 506, None: 188}); ein Guard oder Kommentar hält den Fall,
   falls die Konstante je wieder variabel wird.

## Bestätigt (gemessen, kein Befund)

- **ab-Preis = min über NEU**: 3 Stichproben am echten Bestand korrekt —
  Pixel 10 Pro Fold 256 → 1.603,00 € o2 · Xiaomi 17T Pro 512 → 865,00 €
  congstar · iPhone Air 256 → 891,00 € congstar. `barpreise()` filtert
  `VERGLEICHBARE_ZUSTAENDE`; 9 refurbished Listungen bleiben draußen
  (iPhone 14 128 hätte sonst 445 statt 721 € „ab" gemacht) und stehen im
  Aufklapper mit Etikett — Zustand-im-Schlüssel PASS.
- **Preisarten nie mischen**: 1&1 „nur im Bündel" kommt aus
  `geraete_tco.json` (37/37 Listungen mit Beleg: Tarif, URL, Abrufdatum),
  keine Rate als Barpreis; `data-s-preis` bei nur-im-Bündel leer (bewusst,
  C3-Übergabe) — Zeile fällt beim Preissortieren ans Ende.
- **TCO-Spalte**: 111 Zeilen, 92 mit Zahl, 19× „kein Bündel gemessen",
  0× „kein vergleichbares Bündel gemessen"; `delta_kurz` 54, alle mit
  Referenz + Beleg, 0 ohne — vergleichbar-Filter PASS.
- **Testumbau scharf, nicht gelockert**: DOM-/Aufklapper-/Export-Zeilen
  alle == 111; `_b5_modellzahl()` = 28 ausgeschrieben mit Begründung gegen
  Listungszahlen (31); Lookup-Vollständigkeit als exakte Länge geprüft
  (Hausregel `len(zugeordnet) == len(erwartet)` erfüllt, u. a.
  `test_die_modell_exports_nennen_die_modellzahl`); P1-Echtbestand-Gegenprobe
  `assert groesster > halbe_sichtflaeche` spannt den Fall auf; NaN-Sortier-Test
  fordert `"" in lage["werte"]` (Fixture erzeugt den Fall wirklich); Modellzahl
  OHNE get_text-Trenner gelesen (30.08.-Falle).
- **Kein still entschärfter Wahrheitstest**: `git diff 64a8f2a --stat` für
  `test_geraete_faden.py`, `test_geraete_o3_rollen.py`, `test_geraete_o4_export.py`,
  `test_wettbewerbsradar_alarme.py` leer.
- **CSV-Disziplin**: beide Modell-CSVs UTF-8 mit BOM (`\xef\xbb\xbf`),
  Semikolon, CRLF, Dezimalkomma („1349,90"), Kopf == `SPALTEN_MODELL_*`,
  111 Datenzeilen == Modellzahl; `geraete-aktuell.csv` unangetastet (636).
- **E5 4/4**: jetzt 6 Export-Knöpfe (mobil rollt in sich, Desktop unangetastet,
  je gemessen grün) — ohne die zwei neuen wäre die Regel mit der neuen
  Zahlensektion Katalog verletzt gewesen.
- **site/ von Hand**: `render_site` MIT cfg → alle 5 geprüften Dateien
  byte-identisch zu `site/`; die committeten CSVs sind Render-Artefakte.
