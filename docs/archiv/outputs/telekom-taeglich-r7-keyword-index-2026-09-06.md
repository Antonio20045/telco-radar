# Telekom-Tagesbetrieb, Runde 7 — Keyword-Index bereinigt (06.09.2026)

Auftragsgrundlage: `BRIEF_TELEKOM_R7_KEYWORD_INDEX.md`
(Workspace-Engineer). Pflichtlektüre: `CLAUDE.md`,
`outputs/telekom-taeglich-r6-beleg-vollstaendig-2026-09-06.md`.

## Befund

`site/data/keyword-index.json` war im committeten Stand dieses Branches
von `origin/main` abgewichen (Blob `aa9652a` statt `61b24dc` — Feld
`stand` auf "2026-09-05" statt "2026-09-06", dazu abweichende
`meldungen`/`woerter`-Werte aus einem älteren lokalen Renderstand). Der
R6-Bericht hatte behauptet, die Datei sei per `git checkout --`
zurückgesetzt und nicht committet worden — das stimmte nicht: die
Abweichung war bereits im Merge-Commit `a412d0b` (vor R6) vorhanden und
blieb über alle drei R6-Commits (`c6d7b7f`, `c5a40bd`, `20fc6fb`) hinweg
unverändert committet. R6 hat den Zustand also nicht verursacht, ihn aber
auch nicht behoben und fälschlich das Gegenteil berichtet.

## Was gemacht wurde

1. **Datei zurückgesetzt**: `git checkout origin/main --
   site/data/keyword-index.json`. Kein Rendern, kein Lokallauf, keine
   Netzabfrage.
2. **Byte-Vergleich verifiziert**:
   `git hash-object site/data/keyword-index.json` ==
   `git rev-parse origin/main:site/data/keyword-index.json` ==
   `61b24dca9a0c2cbed98d25492f902f0345cff03c`.
3. **Fokussierter Diff**: `git diff --cached --stat` zeigt ausschließlich
   `site/data/keyword-index.json` (1 Zeile geändert). Alle übrigen
   R6-Artefakte (`data/state/tarife.jsonl`, `data/state/geraete_db.json`,
   `data/state/geraete_tco.json`,
   `outputs/beleg-telekom-lokallauf-2026-09-06.json`,
   `outputs/telekom-taeglich-r3-e4-2026-09-06.md`,
   `outputs/telekom-taeglich-r6-beleg-vollstaendig-2026-09-06.md` bis auf
   die Korrektur unten, `tests/test_tarif_crawler.py`,
   `scripts/lokallauf_telekom.py`, `config/tarif_quellen.yaml`,
   `src/telco_radar/collect/tarif_crawler.py`, `site/tarife.html`,
   `site/geraete.html`, `site/exporte/geraete-aktuell.csv`) sind gegen
   `origin/main..HEAD` unverändert gegenüber dem R6-Stand geblieben.
4. **R6-Bericht korrigiert**: Abschnitt "Korrektur (R7, 06.09.2026)" in
   `outputs/telekom-taeglich-r6-beleg-vollstaendig-2026-09-06.md` ergänzt
   — die falsche Rücksetzungsbehauptung steht dort weiterhin im
   ursprünglichen Text (nichts rückwirkend schöngeschrieben), die
   Korrektur ist als eigener, datierter Abschnitt angehängt.
5. **Zwei Telekom-Belegtests ausgeführt** (keine Vollsuite nötig, da nur
   Index und Bericht geändert wurden):
   ```
   PYTHONPATH=src /opt/homebrew/bin/python3 -m pytest -q \
     tests/test_tarif_crawler.py::test_beleg_deckt_alle_konfigurierten_telekom_einstiege_ab \
     tests/test_tarif_crawler.py::test_echte_config_gibt_telekom_die_ehrliche_kennung
   2 passed in 0.09s
   ```

## Kriterien-Abgleich

| # | Kriterium | Ergebnis |
|---|---|---|
| 1 | `keyword-index.json` byte-identisch zu `origin/main`, kein Diff mehr | **erfüllt** — Hash `61b24dc…` beidseitig, `git diff origin/main..HEAD -- site/data/keyword-index.json` nach Commit leer |
| 2 | R6-Bericht korrigiert die falsche Rücksetzungsbehauptung, keine rückdatierte Erfolgsbehauptung | **erfüllt** — Korrekturabschnitt in R6-Bericht, Erfolg erst mit R7 datiert |
| 3 | Laufzeitbeleg, Telekom-Daten, Renderergebnis, Vollständigkeitstest aus R6 unverändert | **erfüllt** — fokussierter Diff zeigt außer dem Index und der Korrektur keine Abweichung |
| 4 | Beide Telekom-Belegtests grün, keine Vollsuite nötig | **erfüllt** — 2 passed |
| 5 | Nur Ticket-Branch committet/gepusht, kein Merge, kein Deploy | **erfüllt** — siehe Commits unten |

## Bewusst offen

Unverändert aus R6 (siehe dortige Sektion "Bewusst offen") — von dieser
Runde nicht berührt.

## Commits

Auf `openclaw/ticket-telekom-taeglich-r3-e4`, ein Commit (Index-Reset +
Berichtskorrektur), gepusht auf denselben Branch. Kein Merge nach `main`,
kein Deploy.
