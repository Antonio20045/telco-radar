# RV-3 · Alterskennzeichnung der übernommenen Redaktion (E-3c)

**Datum:** 15.09.2026 · **Branch:** `openclaw/ticket-rv3` · **Commit:** `8dbbcee`
(Basis `86800aa`) · **Status:** fertig, wartet auf unabhängigen Evaluator-PASS.
Nicht gemergt, nicht gerendert (site/ unangetastet), nicht deployt.

Auftragsgrundlage: Ticket RV-3 zu E-3c (ENTSCHEIDUNGEN.md, 12.09.), Befund 1
aus REVIEW_2026-09-12.md, K-1-Lehre aus `reviews/EVAL_k1-testb4a.md`.

## Was gebaut wurde

Der Review vom 12.09. maß eine 15 Tage alte Redaktion hinter
„AUSGABE VOM 11. SEPTEMBER" — der Hinweis darunter nannte nur ein Datum
(„Stand: 28. August 2026") in Fließtextgröße und fiel „eher nicht auf".
E-3c entschied **Option 2**: der Block bekommt eine unübersehbare
Alterskennzeichnung, der Kopf behält das Render-Datum, verschweigt die
Ausnahme aber nicht (Option 1, die Absenkung des Kopfdatus, wurde
ausdrücklich verworfen).

| Stelle | Änderung |
|---|---|
| `report/html.py` · `_redaktion_ausfall_ctx` | rechnet `alter_tage` aus `report["date"]` gegen `redaktion_ausfall.stand` und liefert `alter_de` („14 Tage ohne Aktualisierung", Singular „1 Tag"). **Nie `date.today()`** — K-1-Lehre: eine Wanduhr-Rechnung verschiebt die Zahl bei jedem Rebuild, ohne dass sich der Inhalt ändert. Nicht berechenbares/unplausibles Alter (< 1 Tag, kaputtes Datum) lässt die Aussage aus (fail-closed), der Hinweis sagt dann wie bisher das Datum allein |
| `templates/meldungen.html.j2` | Kicker im Ausfall-Fall: „Ausgabe vom 11. September 2026 – Meldungen ohne Aktualisierung seit 28. August 2026" (Normalwoche byte-identisch zum alten Kicker). Hinweis führt mit `<strong class="ausfall-alter">14 Tage ohne Aktualisierung</strong>` |
| `templates/woche.html.j2` | dieselbe Führzeile an beiden Hinweis-Stellen (vor dem Aufmacher, im Wochenbericht-Kopf) **plus `<title>`** der Titelseite — gleiche Ausnahme, gleiche Sichtbarkeit, damit nicht zwei Stellen unterschiedlich alt aussehen |
| `templates/style.css` | `.ausfall-hinweis .ausfall-alter`: rote, großgeschriebene 14-px-Führzeile über dem Text (der Review-Befund war ausdrücklich auch optisch: „in normaler Fließtextgröße … fällt beim ersten Blick eher nicht auf"). Additive Regel, nur im Ausfall-Fall auf der Seite |
| `tests/test_redaktion_kontinuitaet.py` | +4 Tests (siehe unten). Kein bestehender Test geändert, geschwächt oder entfernt |

## Abnahmekriterien — Belege

1. **Alterskennzeichnung „X Tage ohne Aktualisierung"** —
   `test_ausfall_hinweis_nennt_das_alter_in_tagen`: Fixture stand=2026-08-28,
   Ausgabe=2026-09-11 (der Live-Befund des Reviews) → „14 Tage ohne
   Aktualisierung" auf index UND meldungen, als `.ausfall-alter` im Hinweis.
   **Vor dem Fix rot, danach grün** (gegenüber dem unveraenderten Baum
   gemessen: 3 der 4 neuen Tests fielen, der vierte prüft die Invariante
   „Normalwoche ohne Altersaussage" und bestand schon vorher — so gehört es).
2. **Kein Datum verschweigt das Alter mehr** —
   `test_kicker_und_kopf_machen_die_alters_ausnahme_sichtbar`: DOM-Messung
   (BeautifulSoup) hält Kopf- und Blockdatum gegeneinander: der Kicker nennt
   Render-Datum UND Meldungsstand („11. September" + „28. August"), der
   Hinweis darunter denselben Stand, der `<title>` der Titelseite ebenfalls.
3. **E-3b bleibt erhalten** — alle 15 bestehenden Tests in
   `test_redaktion_kontinuitaet.py` unangetastet und grün, darunter
   `test_titelseite_zeigt_die_uebernommene_redaktion_mit_stand` („Stand: …"
   weiterhin 2× auf index) und `test_meldungenseite_zeigt_die_
   uebernommene_redaktion_mit_stand` („Ausgabe vom 10. August 2026" bleibt).
   Suite bestätigt: 0 neue Rote.
4. **Tagesrechnung ohne Systemzeit** —
   `test_die_tagesrechnung_zaehlt_zwei_feste_daten_nicht_die_uhr`: zwei
   feste Paare (28.08.→11.09. = 14; 01.08.→02.08. = „1 Tag", Singular) plus
   fail-closed-Fall („kein-datum" → `alter_tage is None`). Reine
   Funktionsprüfung, keine Wanduhr im Spiel.
5. **Byte-Identität außerhalb des Ausfall-Bausteins** — Alt/Neu-Render über
   `data/reports/` (gleiche Datenbasis, gleicher Aufruf mit `load_config`):
   Unterschied NUR in `index.html`, `meldungen.html`, `style.css` und den
   drei Archivwochen MIT `redaktion_ausfall` (2026-09-04 → „7 Tage",
   2026-09-09 → „12 Tage", 2026-09-11 → „14 Tage"). Alle übrigen gerenderten
   Dateien byte-identisch. Die Diffs selbst zeigen ausschließlich Kicker-,
   Titel- und Hinweis-Stellen.
6. **Suite** — `PYTHONPATH=src pytest -q`: **2972 passed / 12 skipped /
   1 failed** (340 s). Der eine Rot ist die bekannte, vorbestehende
   Pillow-Ausnahme `test_geraete_lifecycle.py::test_ein_simulierter_
   nachtlauf_erzeugt_keine_nullzeilen`. Erwartet waren 2968 passed —
   die Differenz sind die 4 neuen Tests. Zusammenfassung gespeichert unter
   `outputs/rv3-altereskennzeichnung-2026-09-15-suite.txt` (die
   Kurzzusammenfassung des -q-Laufs; der Laufstart fiel mit dem letzten
   kosmetischen Template-Edit zusammen, deshalb zur Sicherheit die vier
   rendernden Dateien danach erneut gegen den finalen Stand gelaufen:
   137 passed). Ein vollständiger Nachlauf des Evaluators gegen `8dbbcee`
   ist der sauberere Beleg und wird erwartet.

## Grenzen, bewusst so

- **Optik nicht im Browser angesehen** (Sandbox/Zeitbudget): die
  Prominenz der Führzeile ist über CSS gesetzt und per DOM-Test
  (`ausfall-alter` im Hinweis) belegt, aber nicht gescreenshotet. Der
  unabhängige Evaluator sieht die Seite im Browser.
- **`pruefe_portal.py` nicht gelaufen** — der Auftrag verlangt es nicht;
  die Ausfall-Fälle liegen außerhalb seiner Normalwoche-Messungen. Kriterium
  1 (Falz) berührt die Änderung nicht: der Hinweis stand schon vorher vor
  dem Aufmacher, er ist nur um eine Zeile gewachsen.
- **Ein `<div>`-Kopf der Meldungsseite trägt weiterhin `<h1>Alle
  Meldungen</h1>`** ohne Datum — kein Datum, keine Falschauszeichnung.
- **Alt/Neu-Render** nutzt den echten `data/reports/`-Bestand; da die
  jüngste Ausgabe (2026-09-11) selbst eine Ausfall-Runde ist, deckt der
  echte Bestand sowohl Ausfall- als auch Normalwochen ab.
