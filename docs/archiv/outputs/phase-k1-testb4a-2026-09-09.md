# Phase K-1 + TEST-B4a — Abschlussbericht (2026-09-09)

Branch `openclaw/ticket-k1-testb4a`, Basis `main` `e1e71aa`. Vier Commits:
`b36a6b9` (k1: Fix + Determinismus-Test) · `934f4e0` (k1: Site-Render) ·
`5632b0e` (testb4a: Assertion) · Bericht (dieser). Kein Merge, kein Deploy.

## Kriterien

| # | Kriterium | Stand | Beleg |
|---|---|---|---|
| 1 | Ursache benannt (Datei:Zeile) | **ERFÜLLT** | unten, „Ursache“ |
| 2 | Determinismus-Fix + Test, Gegenprobe rot auf alt | **ERFÜLLT** | Test grün neu / rot alt (3 gegen 2) |
| 3 | Kein Zahlen-Drift durch den Fix | **ERFÜLLT mit benannter, begründeter Änderung** | unten, „Vorher/Nachher“ |
| 4 | Suite grün, nichts geschwächt | **ERFÜLLT** | 2881/0/12 (Baseline 2880/0/12, +1 Test) |
| 5 | Echte Assertion im B4a-Test | **ERFÜLLT** | `tests/test_geraete_buendel_einsundeins.py:252`, 14/14 der Datei grün |
| 6 | Gegenprobe B4a rot ohne Eigenschaft | **ERFÜLLT** | Sabotage `zustand="neu"` hart → rot; Restore per `git checkout` |
| 7 | Site + Bericht | **ERFÜLLT** | Site gerendert+committet (nur `keyword-index.json`), Suite-Zahlen + Bericht in `outputs/` |

## Ursache (Kriterium 1)

Der einzige Produktions-Aufruf des Index-Erzeugers übergab kein `heute=`:
`report/html.py:1761` →
`newsletter/filters.baue_stichwort_index(reports_dir, tage=_nl_tage)`.
Ohne das Argument fiel der Anker auf die **Wanduhr des Rebuild-Moments**
zurück — zweifach:

- Fensterung: `filters.py:305` (`_bericht_dateien`: `heute = heute or
  date.today()`, `grenze = heute − 30 Tage`, Vergleich gegen die Bericht-
  Stämme). Jedes nächtliche Rendern nach Mitternacht schob die Grenze ein
  Stück vor; die Berichtstage darunter fielen aus dem Fenster, ohne dass
  sich am Archiv etwas geändert hatte.
- `stand`: `filters.py:389` (alt) schrieb `(heute or date.today()).isoformat()`
  — das Rebuild-Datum, nicht einen Datenstand.

**Der 1716→1624-Fall (Ticket, R3-Release):** ein Rebuild nach Mitternacht
ließ die Berichte unter der neue Grenze heraus; deren Meldungen (92 im
Ticket-Fall) verschwanden aus `meldungen`. **Im heutigen Bestand war der
Drift schon passiert:** die committete Datei trug `stand: 2026-09-08` bei
jüngstem Bericht `2026-09-04` — die Wanduhr lag vier Tage hinter dem
Datenstand, das Fenster `[2026-08-09, …]` statt `[2026-08-05, …]`, die
Berichtstage 08-05 bis 08-08 (496 Meldungen) waren lautlos herausgefallen.
Nachgemessen: Anker 09-08 → 1241, Anker 09-04 → 1737.

## Fix (Kriterium 2)

`filters.py`: neuer `_neuester_bericht(reports_dir)` (Datum des jüngsten
Bericht-Stamms; `None` bei leerem/unlesbarem Archiv). `baue_stichwort_index`
ankert `heute` ohne Argument am jüngsten Bericht — Fenster **und** `stand`
hängen damit am Datenstand; das Fenster wandert nur, wenn ein neuer Bericht
dazukommt. Explizites `heute=` bleibt Overrides vorbehalten (alle
bestehenden Tests nutzen es unverändert weiter). Sammelschicht unberührt.

**Test:** `test_der_index_zaehlt_an_jedem_rebuild_tag_dieselbe_zahl`
(`tests/test_newsletter_filters.py`) klebt `filters.date.today()` auf zwei
Rebuild-Tage (2026-08-08 = Tag des jüngsten Berichts, 2026-09-06 = vier
Wochen später) und fordert **byte-identische** Index-Dicts gegen denselben
Bestand — plus `meldungen == 3` und `stand == "2026-08-08"` (die Zahl der
Datenlage, nicht eine zwischen zwei Wanduhren).

- Neu: **grün** (38/38 der Datei).
- Gegenprobe auf altem Stand (`git checkout` der Vorfassung, dann
  zurückgespielt): **rot** — `meldungen` 3 gegen 2, `stand` 2026-08-08
  gegen 2026-09-06. Exakt der Ticket-Mechanismus, an der Fixture
  reproduziert.

## Vorher/Nachher (Kriterium 3)

`render_site()` mit `load_config(root)`, unverändertes `data/reports/`.
`git diff --stat`: **genau eine Datei**, `site/data/keyword-index.json`
(1 Zeile). Alle übrigen Seiten byte-identisch.

| Feld | vorher | nachher | warum richtig |
|---|---|---|---|
| `stand` | 2026-09-08 | 2026-09-04 | 09-04 ist der jüngste Bericht = der Datenstand. Berichte 09-05…09-08 existieren nicht; 09-08 war die Wanduhr des letzten Rebuilds, kein Datenstand. |
| `meldungen` | 1241 | 1737 | Die 1241 waren das Drift-Artefakt selbst: das an der Wanduhr 09-08 hängende Fenster hatte 08-05…08-08 (496 Meldungen) verloren. Der Fix stellt das volle Fenster über dem unveränderten Archiv her; jeder Rebuild zu beliebiger Zeit liefert jetzt 1737. |
| `woerter` | 8.251 | 10.390 | Dieselben vier Berichtstage zählen wieder; die Browser-Vorschau der Anmeldeseite zählt gegen dieses Feld und sagte bisher die Treffer der vier Tage unterschlagen. |

Der Fix ändert also sichtbare Zahlen — benannt und begründet: es ist die
Rückgängigmachung des bereits eingetretenen Drifts, nicht ein neuer.
Suite- und Rendering-Pfad bleiben unberührt (Browser liest nur `woerter`,
`app.js:1283`).

## TEST-B4a (Kriterien 5, 6)

`test_der_zustand_kommt_als_neu_aus_dem_titelweg` hatte nur einen Docstring.
Jetzt echte Assertions auf dem vollen Weg (`sammle_anbieter` → `_mit_sku` →
`lies_listung`): die echte A57-Fixture, bei der **nur** der Farbschlüssel
der 128-GB-Zeile ein Kennzeichen trägt (`AWESOME_GRAY-128` →
`GRAU_ERNEUERT-128`; die Farbe ist bei o2 dieselbe Signalstelle für
„erneuert“), liefert:

```python
assert [b["zustand"] for b in bilanz.buendel] == ["refurbished", "neu"]
assert "refurbished" in bilanz.buendel[0]["sku_id"]
assert "refurbished" not in bilanz.buendel[1]["sku_id"]
```

Ein Lauf zeigt beide Richtungen: ohne Kennzeichen wird „neu“ **geleitet**
(Titelweg geerbt), mit Kennzeichen nicht — ein fester „neu“-Default fiele
rot. Die SKU-Assertion nagelt die Vergleichbarkeit der Tafelzeile fest
(QA-B1: `-refurbished`-Strecke der `sku_id`). Kein Lookup ins Leere: die
Listengleichheit scheitert auch an leerer Ausbeute.

- Neu: **grün** (14/14 der Datei).
- Gegenprobe: `_mit_sku` mit hartem `"zustand": "neu"` temporär sabotiert →
  **rot** (`['neu','neu']` statt `['refurbished','neu']`); danach
  `git checkout` — Restore nachgewiesen (Baum danach nur mit der Testdatei
  verändert).

## Suite (Kriterium 4)

`PYTHONPATH=src python3 -m pytest -q`, blockierend:
**2881 passed / 0 failed / 12 skipped** in 5:20 min.
Baseline 2880/0/12; Differenz +1 (der neue Determinismus-Test). Kein Test
geschwächt, gelöscht oder übersprungen. Belegdatei:
`outputs/phase-k1-testb4a-2026-09-09-suite.txt`.

## Messgrenzen / bewusst offen

- `_neuester_bericht` fällt bei leerem Archiv auf die Wanduhr zurück —
  `meldungen` bleibt dann deterministisch 0, nur `stand` trägt das
  Rebuild-Datum (kein Datenstand vorhanden). Im Bestand nicht relevant
  (26 Berichte).
- Der Determinismus-Test klebt `filters.date` global für den Modul-
  Namensraum; er prüft damit den Produktionspfad genau da, wo die alte
  Fassung las. `vorschau()` behält seinen Wanduhr-Default — es hat keinen
  Produktionsaufruf ohne `heute=`, und die bestehenden Tests geben es
  explizit mit.
- Die Fixture-Änderung im B4a-Test ist ein String-Replace gegen den
  Farbschlüssel `AWESOME_GRAY-128`; ändert 1&1 die Farbnamen, läuft der
  Replace ins Leere und der Test fällt rot (grün ist er nur, solange die
  sabotage-trächtige Zeile wirklich existiert) — die richtige Fehlerseite.
- Live-Verifikation und Evaluator-Abnahme ausdrücklich NICHT gemacht
  (kein Deploy, kein Push nach main; Auftrag des PM).
