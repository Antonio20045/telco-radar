# P5 — CODE-Pruefung (adversarial) gegen HEAD f006660

Arbeitsbaum 18.09.2026, kombiniert aus den Parallel-Agenten E1-E5.
Grundlage: `git diff f006660`, `docs/clean-code-referenz.md`,
STRATEGIE_GERAETE_V3.md Abschnitt P5, Notizen in `p5/`.
Nichts committet, nichts unter data/state geschrieben.

## Befunde, schwerste zuerst

### S2-1 — Provider-Probe ist blind fuer den Totaltod des o2-Preisblocks (FM-2 bleibt fuer den schlimmsten Fall offen)

**Dateien/Zeilen:**
- `src/telco_radar/collect/geraete/o2.py:341` — `if proben is not None and monatlich is not None:`
- `src/telco_radar/geraete_pipeline.py:242` — `funde=len(bilanz.listungen),`
- `src/telco_radar/geraete_pipeline.py:462` — `log.info("Buendel: %d von %d Rohsaetzen …`
- `src/telco_radar/geraete_pipeline.py:135-137` — Docstring-Zusicherung

**Fehlerszenario:** Entfernt o2 `monthlyPrice` KOMPLETT aus der
Katalogantwort (Umbau der Schnittstelle, nicht nur einzelner Felder),
dann ist `monatlich is None`, der Zaehlblock wird uebersprungen,
`kandidaten` bleibt 0 — und `melde_proben` druckt KEINE Zeile
(`if not erwartete: continue`). Gleichzeitig:

1. Der 7-Tage-Ausfallalarm bleibt stumm: `protokolliere_lauf` zaehlt
   `funde=len(bilanz.listungen)` — Bündel sind NIE Funde, und o2 liefert
   seine Listungen ueber den hwOnly-Pfad jede Nacht weiter. `stille_tage`
   sieht dauerhaft Funde > 0.
2. Die Buendelzeile ist INFO „Buendel: 0 von 0 Rohsaetzen uebernommen" —
   inhaltlich ununterscheidbar von „kein Anbieter liefert Bündel", und
   INFO statt WARNUNG.

Die Docstring („Ohne Kandidaten … steht keine Zeile — dafuer sind die
Buendel- und Ausfallzeile da") ist eine Zusicherung, die der Code fuer
genau dieses Szenario nicht einloest — derselbe Fehlerklasse-Typ, gegen
den der Praemortem-Fall FM-2 („Felder weg, Lauf bleibt gruen") gebaut
wurde. Gedeckt sind nur PARTIELLE Feldtode (metric3/metric5/metric4 weg
bei vorhandenem monthlyPrice — dafuer existieren Tests). Reparatur-Vorschlag:
Kandidaten zaehlen, sobald `proben is not None` (Referenzfeld fehlt =
gescheiterte Probe, nicht kein Kandidat), oder Bündelrohsaetze in die
Funde-Zahlung je Zweig nehmen. Schweregrad S2, weil der Ausfall ueber
Wochen unbemerkt bleibt und nur durch Lesen der Website auffiele.

### S3/S4 — gebuendelt

1. **S3** `geraete_pipeline.py` `melde_proben`: `prozent = round(100.0 *
   bestanden / erwartete)` — bei 199 von 200 besteht die Probe mit
   „100 %" als INFO-Zeile. Ein Einzelfehler wird als Perfektion
   gemeldet. (Grenzwertige Rundung, bewusste Entscheidung moeglich —
   aber nicht dokumentiert.)
2. **S3** `geraete_store.protokolliere_lauf`: gleicher Messtag ersetzt
   seine `funde_nach_tag`-Zeile (idempotent) — ein zweiter Lauf am
   selben Tag mit 0 Funden ueberschreibt den ersten mit Funden > 0 und
   laesst den Alarm frueher zuschlagen. Konservativ (in die sichere
   Richtung), getestet — als Kante benannt, kein Handlungsbedarf.
3. **S4** `report/geraete_view.py` `katalog_modellzeilen(...)` — 5
   Parameter (F1-Grenze 3); alle optional, Erweiterung einer
   bestehenden Signatur.
4. **S4** `tests/test_geraete_sichtbarkeit_p5.py` `_baue_buendel_modell(
   ..., mit_listung: bool)` — Flag-Argument am Testhelper (F3/G15);
   Test-only, zwei Lagen statt zweier Funktionen.
5. **S4** `CLAUDE.md:1845` — Zeiger „lebt in der E5-Schlussliste": eine
   Datei dieses Namens existiert nicht (E5 hat nur
   `notiz-e5-claude-md.md`, dort steht der Kosmetik-Punkt nicht).

## Pruefauftraege E1-E5 — einzeln

| Auftrag | Befund | Beleg |
|---|---|---|
| E1 Sichtbarkeit beide Wege | **PASS** | `tests/test_geraete_sichtbarkeit_p5.py`: 4 Tests, je Weg eine Fixture; Sprungziel: Luecke „noch keine Zeitreihe" nur mit `hat_buendel`, kein toter Link (`a.gr-sprung` absent, nicht in `erlaubt`/`suchindex` — beides assertiert) |
| E1 zwei vorbestehende Rote | **PASS (gerechtfertigt)** | Am sauberen HEAD f006660 im /tmp-Worktree beide rot reproduziert: Lifecycle `assert 52 >= 80` (Bestands-Zeitbombe, Horizont jetzt aus Daten), Tablets am Auto-Eintrag „Samsung Galaxy Tab S11 Ultra" vom 17.09. (Praemisse „Katalog nur Smartphones" durch E4-Auto-Eintraege ueberholt). Kein Test still geloescht; Umbauten tragen neue Namen und messen die neue Regel, mit dokumentierter Vorher-rot-Messung |
| E2 Schwelle 7 Tage | **PASS** | `AUSFALL_TAGE = 7` (`geraete_store.py:57`); Test an EXAKT 7 (Alarm) und 6 (kein Alarm); gezaehlte BEOBACHTETE Tage, nicht Kalendertage (Test: Luecke in der Historie zaehlt nicht); kein Mail/Teams — `melde_ausfall`/`melde_proben` nur log.warning/info |
| E2 Probe deterministisch | **PASS mit S2-1** | Zaehlung vor jeder Ablehnung, reine Feldvergleiche (`_gleich`), kein Zufall/Uhr; Blindheit nur im Totalfall (S2-1) |
| E3 Filter gegen ECHTE Titel | **PASS** | Fixture `unbekannte_titel_2026-09-17.jsonl`: 145 Zeilen, sha256 `3a66c789d39328fd…` identisch mit der Registrierung in `_herkunft.json` („alle 145 art=titel-Zeilen unveraendert", Stand 17.09.); Wahrheitsprobe: exakt „Tarif L/M/S" (ALDI TALK, haeufigkeit 87), 142 bleiben, Oakley Meta + motorola edge 70 bleiben |
| E3 data/state unberuehrt | **PASS** | `git status --porcelain -- data/state data/reports` leer; Tests schreiben nach tmp_path |
| E4 Skript deterministisch | **PASS** | `--heute`-Parameter (Test mit 2026-09-18/2026-09-13), Bericht byte-identisch bei Wiederhollauf (eigener Test), gzip mtime=0, EINE Protokollzeile, Grenze je Fragment nicht Summe (Test) |
| E5 CLAUDE.md | **PASS** | §6-Fallstricke unberuehrt („Saegeszahn"/„202"/„Zustandsdimension"/„robots" weiterhin vorhanden) + 4 neue; Konsolidierungen mit Messzahlen belegt (Navigation 7 nachgezaehlt am site/, Export-Knoepfe 6, Kriterium 13/14/15 existieren); OFFEN-Liste 7 Punkte, deckt die p1-p4-Nachpruefungen (PM-6-Falldatum 20.09. vor Entscheidung 01.10., iPad-Anker 284->281, disjunkter Deep-Link) |

## Pruefkatalog docs/clean-code-referenz.md — Kategorie fuer Kategorie

| Kategorie | Urteil |
|---|---|
| P1-P16 | **PASS** (Suite gruen, keine Duplizierung — EINE Regel je Ort durchgaengig, Konstanten benannt, Tests offline/unabhaengig, Ausnahmen mit Kontext); P7/P10/P11/P16 n. z. |
| C1-C5 | **PASS** — C2-Anteil an S2-1 (Docstring widerspricht Code im Totalfall), sonst keine ueberholten/auskommentierten Kommentare |
| E1-E2 | n. z. (keine Build-/CI-Konfig im Diff) |
| F1-F4 | F1: S4-Bund (5 Parameter, s. o.); F2/F3: PASS (F3-Anteil am Testhelper als S4 gebuendelt); F4: PASS (keine toten Funktionen — aufgerufene neue Helfer alle verdrahtet) |
| G1-G36 | **PASS** fuer die geprueften (G3 Grenzfaelle extensively getestet: genau 7 Tage, 6 Tage, leerer Store, unlesbarer Store; G4 keine deaktivierten Tests; G16/G25 alle Schwellen als benannte Konstanten; G26 Geld floats mit `_gleich`-Toleranz — Hausstandard); G21/G31 n. z. |
| N1-N7 | **PASS** (`melde_ausfall`/`melde_proben`/`ist_tarif_titel`/`_anker_treffer` deskriptiv) |
| T1-T8 | T1: S2-1 IST die Luecke (Totaltod-Szenario ungetestet); T4/T5 PASS (keine Ignores, Grenztests an 7/6 Tagen und an der 5-MB-Grenze); T2/T6/T7/T8 n. z. |

## Harte CLAUDE.md-Regeln

- site/ von Hand: **PASS** — Aenderungen an `site/geraete.html`,
  `site/style.css`, `site/exporte/*.csv` stammen aus `render_site()`
  (E1-Notiz dokumentiert Renderlauf), keine Hand-Editierung erkennbar.
- seen.jsonl / Titel-Hash-IDs: **PASS** — nicht beruehrt; Auto-Erkennung
  laeuft ueber strukturierte Katalognamen, nicht Titel-Hash.
- Secrets / Lauf-Artefakte: **PASS** — keine Secrets im Diff;
  `data/state`/`data/reports` unangetastet; nichts committet.

## Suite

- `PYTHONPATH=src python3 -m pytest -k geraete -q`:
  **1505 passed, 6 skipped, 0 failed** (206 s) — Ziel 0 failed erreicht.
- Volle Suite `pytest -q`: **3303 passed, 12 skipped, 0 failed**
  (446,9 s). Die 2 vorbestehenden Roten sind weg — als gerechtfertigte
  Konvertierungen (Vorher-rot am sauberen HEAD bewiesen), KEINE neuen
  Roten, keine skips zugelegt.

**Fazit:** 1x S2 (o2-Totaltod bleibt stumm — Zusicherung der Docstring
haelt nicht), 5x S3/S4 gebuendelt. E1-E5 einzeln sauber umgesetzt und
ueber die volle Suite abgesichert; merge-faehig nach Fix von S2-1 oder
mit expliziter Lead-Entscheidung, das Restrisiko zu tragen.
