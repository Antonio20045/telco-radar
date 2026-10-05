Stand: 2. Oktober 2026

# Repo-Umbau Telco Radar: Pakete

Grundlage ist das Konzept „Agenten-Entwicklungssystem für Telco Radar“. Sein Markdown-Export liegt unter `docs/archiv/umbau-konzept.md`. Paket 1 verdichtet ihn zu `docs/umbau/plan.md` und `docs/umbau/bausteine/`; danach verweisen alle Pakete nur noch auf diese Dateien und auf CLAUDE.md. Jedes Paket füllt genau eine Sitzung.

## Ziel

Der Umbau räumt nicht nur auf. Er baut ein Software-Engineering-System, das sehr guten Quellcode erzeugt und ihn dauerhaft so hält, auch wenn ihn Agenten schreiben. Qualität entsteht dabei durch Mechanik, nicht durch Anweisungstext: Ein lokaler Prüfleiter entscheidet per Exit-Code, Importverträge machen falsche Abhängigkeiten unschreibbar, Basislinien und Ausnahmelisten dürfen nur schrumpfen, Tests sind hermetisch und prüfen die gerenderte Seite gegen eine unabhängige Rechnung, und ein Prüfer zählt nur mit Reproduktion. Jede Änderung soll den Code danach messbar besser hinterlassen, und keine soll ihn still verschlechtern können. Erreicht ist das Ziel, wenn `make stand` alle zehn Schritte als erfüllt meldet, alle Ausnahmelisten leer sind und neue Funktionen nur noch über `tools/auftrag.py` entstehen.

Daraus folgt eine Regel für jede Sitzung: Zeigt sich eine Lehre, wird sie als Prüfung, Typ oder Vertrag festgeschrieben, nicht als weiterer Satz in CLAUDE.md. Ein Paket, das sein Fertig-Kriterium erfüllt, aber eine Regel nur in Text statt in Mechanik gegossen hat, ist nicht fertig.

## Sitzungsstart

Jede Paketsitzung beginnt mit: „Lies CLAUDE.md, docs/umbau/plan.md und outputs/umbau-fortschritt.md. Setze dann Paket N aus docs/umbau/pakete.md um. Beginne im Plan Mode.“ In Paket 1 entfallen die beiden Dateien, die es erst anlegt.

## Feste Regeln

1. Der Plan nennt Dateien, Messbefehle und die Rot-Probe, mit der eine neue Prüfung zeigt, dass sie anschlägt.
2. Opus führt, liest nur Auszüge (`grep`, Read mit `limit`) und schreibt keinen Produktcode. Haiku sucht und liest Logs (höchstens fünf Zeilen zurück), Sonnet baut, Opus baut bei TCO, Datenmodell, Stores, IDs und Migration. Ein frischer Opus-Prüfer sucht den Fehler, rechnet mindestens eine Erwartung selbst nach und meldet nur mit Reproduktion unter `/tmp/pruefer/`. Ab Paket 18 läuft jedes Paket als Auftrag über `tools/auftrag.py`.
3. Grün ist ein Exit-Code, nie eine Selbstauskunft. Bis Paket 10 gilt ein Lauf als grün, wenn nur Tests aus `pruef/rot-bekannt.txt` scheitern; die Liste darf nur schrumpfen.
4. Je Paket höchstens 400 hinzugefügte Zeilen in `src/`, `scripts/`, `tools/` (`git diff --numstat`, ohne Tests); Massenläufe sind eigene Pakete. Lead-Kontext unter 120k Token, `pipeline.py`, `report/html.py` und `geraete_*.py` nie ganz laden.
5. Bis Paket 13 keine neuen Funktionen, nur Fehlerbehebungen am Live-Betrieb.
6. Abschluss: drei Zeilen in `outputs/umbau-fortschritt.md` unter `## Paket N – erledigt` oder `## Paket N – gestoppt` (gebaut, gemessen mit Zahl, offen), `git pull --rebase origin main`, neu messen, `git add` nur mit Dateinamen, Commit auf `main`.
7. Zwei rote Runden am selben Punkt oder das Doppelte der Schätzung führen zu `outputs/umbau-notiz-N.md` und einer Frage an Antonio. Fehlt eine Voraussetzung außerhalb des Bereichs, endet das Paket mit einem neuen Paket N.a in der Fortschrittsdatei.
8. Die Zeitziele (etwa „volle Suite unter 4 min“) sind für Antonios Mac (M4 Pro) gerechnet. In der Cloud mit weniger Kernen entscheidet allein der Exit-Code; die gemessene Zeit wird nur notiert.

Der Geräteauftrag v4 ruht bis Paket 13. Vorgezogen werden P0-Punkt 3 (Paket 2) und `test_seiten_zahlen.py` auf Schnappschüssen (Paket 8). Tor P3 und P4 laufen nach Paket 17 als Einzelaufträge, die Neugestaltung ist Paket 26.

| Paket | Titel | hängt ab von | Dauer |
|---|---|---|---|
| 1 | Plan ins Repo, Aufräumen | – | 4 h |
| 2 | Python 3.11, roter Render | 1 | 6 h |
| 3 | ruff-Formatierlauf | 2 | 1 h |
| 4 | Zwei Fehler, Konstanten | 3 | 4 h |
| 5 | Leiter Stufen 1–3 | 4 | 6 h |
| 6 | Leiter Stufe 0, `make stand` | 5 | 6 h |
| 7 | Test-Infrastruktur | 6 | 6 h |
| 8 | Orakel auf Schnappschuss | 7 | 6 h |
| 9 | Bestandstests I | 7 | 6 h |
| 10 | Bestandstests II | 9 | 6 h |
| 11 | Fixtures, Abnahme Tests | 8, 10 | 6 h |
| 12 | Git-Hooks, Stempel | 11 | 4 h |
| 13 | Claude-Hooks, CLAUDE.md | 12 | 4 h |
| 14 | `auftrag.py` Kern | 13 | 6 h |
| 15 | Rollen und Prüfer | 14 | 6 h |
| 16 | Goldener Lauf | 13 | 8 h |
| 17 | mutmut, erster Auftrag | 15, 16 | 5 h |
| 18 | Kommentarwissen | 17 | 6 h |
| 19 | Kommentare löschen | 18 | 3 h |
| 20 | Promo-ID Entwurf | 19 | 5 h |
| 21 | Promo-ID Bau | 20 | 8 h |
| 22 | Adapterzyklus | 21 | 6 h |
| 23–25 | Lader und Geräteseite | 22 | je 8 h |
| 26 | Neugestaltung Geräteseite | 25 | 8 h je Abschnitt |
| 27–30 | Restliche Seiten | 26 | je 8 h |
| 31 | Farben | 30 | 6 h |
| 32–34 | `run` in Phasen | 31 | je 8 h |
| 35–37 | Uhr, Netzweg, Fehler | 34 | je 8 h |

Die Pakete 22–37 sind Skizzen. Vor ihrem Start formuliert eine eigene Sitzung das Paket gegen den dann aktuellen Code aus, schreibt es hier ein und baut nichts.

## Paket 1 – Plan ins Repo, Aufräumen

Der Markdown-Export des Konzepts liegt bereits unter `docs/archiv/umbau-konzept.md`. Der Lead liest ihn abschnittsweise und schreibt `docs/umbau/plan.md` (höchstens 12 KB): Zielbild, Regeln, Leiter-Stufen 0–5 mit Zeitzielen, Ausnahmelisten-Prinzip, Verträge mit allen 27 Kanten und ihrem Paket, Testregeln, Auftragsformat, Rollen, die zehn Schritte mit Fertig-Kriterien und die Zuordnung Schritt → Paket. Die Anhang-Bausteine kommen unverändert als inaktive Dateien nach `docs/umbau/bausteine/`. Dann räumt Sonnet nach Schritt 1 auf: `_to_delete/`, `push-live.sh`, `Push Live.command`, Stop-Hook und Regel 17 weg, `claude/` und erledigte `outputs/` nach `docs/archiv/`, gemergte Remote-Zweige gelöscht, nicht gemergte als Liste an Antonio. Ein serieller Volllauf schreibt die roten Tests nach `pruef/rot-bekannt.txt` (erwartet 16). Fertig, wenn `wc -c docs/umbau/plan.md` ≤ 12.288, `_to_delete` fehlt und `git ls-remote --heads origin` nur `main` und behaltene Zweige zeigt.

## Paket 2 – Python 3.11, roter Render

Sonnet legt `.python-version` (3.11), `make venv` und `requirements-dev.txt` an, setzt `python-version-file` in alle Workflows, löscht `deploy.yml`, stellt `ci.yml` auf manuell mit `timeout-minutes: 30`. Opus lässt `render_site` eine Liste benannter Ausfälle zurückgeben, zuerst aus `geraete_view.py:2163` und den fünf `except Exception` in `html.py`, sichtbar auf der Seite (Regel 9); der Render-Schritt wird dann rot. Der Render-Hook (`geraete.yml:316`, `radar.yml:239`) versucht dreimal und sucht danach das Tagesdatum im Live-HTML. Fertig, wenn im Wegwerf-Worktree mit kaputter Zeitreihe der Render-Schritt Exit ≠ 0 liefert, die Seite den Ausfall nennt und der nächste `geraete.yml`-Lauf das Tagesdatum live zeigt.

## Paket 3 – ruff-Formatierlauf

Nur Formatierung: `[tool.ruff]` mit `target-version = "py311"`, dann `ruff format src tests scripts` als eigener Commit, sein Hash in `.git-blame-ignore-revs`. Fertig, wenn `ruff format --check` grün ist, ein Skript für jede Datei gleiches `ast.dump` meldet und nichts außerhalb von `rot-bekannt.txt` scheitert.

## Paket 4 – Zwei Fehler, Konstanten

Sonnet behebt das Backspace in `collect/newsroom.py:117` und die vier Zero-Width-Spaces mit einem Test, der einen Sitemap-Link verwirft, zieht `STATUS_AKTIV` und `STATUS_VERMUTLICH` nach `geraete_model.py` und die Begriffe nach `analyze/begriffe.py` ohne LLM-Import und streicht die elf Kanten im Baustein. Fertig, wenn `ruff check --select PLE2510,PLE2515 src` leer ist, der Test gegen den Vorstand rot war und `lint-imports` `report-rechnet-nur` mit 16 Ausnahmen hält.

## Paket 5 – Leiter Stufen 1–3

Sonnet aktiviert `[tool.ruff.lint]`, `[tool.mypy]` und `.importlinter`, legt `pruef/ruff-basis.json` und `pruef/mypy-basis.txt` (je Datei und Code, ohne Zeilen) an und baut `scripts/pruefleiter.py --voll` mit Stufen 1–3 plus pytest. Die Leiter senkt Basen selbst, gibt bei Grün eine Zeile, bei Rot höchstens 60 aus und schreibt `.pruefleiter/letzter-lauf.log`. Fertig, wenn `make pruefen` grün ist und drei Rot-Proben scheitern: unbenutzter Import, neuer mypy-Fehler, Import von `collect` in `report`.

## Paket 6 – Leiter Stufe 0, `make stand`

Stufe 0: `pruef/riesendateien.txt` (44 Dateien), keine wachsende Basis- oder Ausnahmeliste gegen den letzten Commit, `continue-on-error` nur an benannten Stellen, AST-Prüfungen mit Basis (Dateizugriff in `report/`, 94 Uhraufrufe, Hex-Farben, 79 `BLE001`), `PLC2701` gegen `pruef/privat-basis.txt` (227). `scripts/stand.py` meldet je Schritt „erfüllt“ oder „offen, weil …“. Fertig, wenn eine neue Datei mit 401 Zeilen und eine von Hand erhöhte Basis rot werden.

## Paket 7 – Test-Infrastruktur

`tests/conftest.py` mit Audit-Hook gegen `data/` und `site/` (Altlasten in `pruef/tests-mit-bestand.txt`, nur schrumpfend), `pytest-socket`, Chromium je Worker, Uhr aus dem Schnappschussdatum, Marker und xdist; `scripts/schnappschuss.py` zieht `tests/fixtures/bestand/<datum>/` mit `_herkunft.json` aus einem Bot-Commit. Fertig, wenn ein neuer Test mit Zugriff auf `data/state` und einer mit Netzzugriff mit Regelmeldung scheitern und die Laufzeit von `make pruefen` notiert ist.

## Paket 8 – Orakel auf Schnappschuss

Sonnet stellt `tests/test_seiten_zahlen.py` (5.308 Zeilen, nur Auszüge) auf eine Session-Fixture um, die einmal aus dem Schnappschuss rendert, und verschiebt es nach `tests/orakel/`; der Vertrag `orakel` wird aktiv, die 145 Orakel bleiben. Fertig, wenn `rot-bekannt.txt` acht Einträge weniger hat und ein verfälschter Schnappschusswert in einer Kopie ein Orakel rot macht.

## Paket 9 – Bestandstests I

Die 22 Dateien mit `WURZEL/"data"` lesen aus dem Schnappschuss; Erwartungen wie 1.794,76 € werden aus ihm neu belegt, nie geraten. Fertig, wenn `grep -lE 'WURZEL\s*/\s*"data"' tests` leer ist und beide Listen kürzer sind.

## Paket 10 – Bestandstests II

Die übrigen der 48 Dateien folgen; `test_newsletter_seite` (211 s) rendert je Variante einmal. Fertig, wenn `tests-mit-bestand.txt` und `rot-bekannt.txt` gelöscht sind und `make pruefen` voll grün ist.

## Paket 11 – Fixtures, Abnahme Tests

Die 33 Fixtures ohne Herkunft werden durch echte Abrufe ersetzt oder mit ihren Tests gelöscht, die rund 52 Tests, die Code als Text lesen, gelöscht oder zu Verträgen, `test_claude_md_groesse.py` wird Stufe 0. Fertig, wenn `make pruefen` zehnmal in Folge grün ist, auf dem Mac unter 4 min bleibt (gerechnet 2,3) und ein Bot-Commit auf `data/state` kein Testergebnis ändert.

## Paket 12 – Git-Hooks, Stempel

`.githooks/` aus den Bausteinen, `make einrichten`, Stufe 4 mit direkter Importzuordnung, `-n 4` ab 10 s und 45-s-Kappe, Stufe 5 voll, Prüfstempel nach `.git/pruefleiter/gruen/`, `make stand` listet ungestempelte Commits. Fertig, wenn ein roter Test nicht pushbar ist, ein mit `git -c core.hooksPath=/dev/null` gepushter Commit als ungeprüft erscheint und pre-commit im Median unter 5 s bleibt.

## Paket 13 – Claude-Hooks, CLAUDE.md

Die vier Hooks unter `.claude/hooks/`, Stop mit `--schnell --hook` und Ende nach drei Exit 2, `hook_gezielte_tests.py` gelöscht, `commit-sicher` auf `make pruefen`, CLAUDE.md auf höchstens 100 Zeilen mit Ordner-CLAUDE.md in `collect/geraete/`, `analyze/`, `report/`, `.claude/settings.json` zuletzt. Fertig, wenn `--no-verify` scheitert, ein Read von `html.py` ohne `limit` blockiert wird, ein Stop mit rotem Lint weiterläuft und `make stand` Schritte 1–5 als erfüllt meldet.

## Paket 14 – `auftrag.py` Kern

`tools/auftrag.py` prüft das Format, legt `../telco-radar-wt/<id>` an, ruft `make venv`, urteilt über Exit-Codes, zählt zwei Runden bis zur Notiz, führt per `--ff-only` zusammen, misst auf `main` erneut, schreibt `outputs/auftraege/kosten.csv`. Fertig, wenn ein Ersatzagent den Weg bis zum Merge durchläuft, ein Auftrag ohne `wasDarfNiePassieren` nicht startet und ungestempelte Commits den Start sperren.

## Paket 15 – Rollen und Prüfer

Agentendateien für Test und Bau, `pruefer.md` aus dem Baustein, Rolle über `TELCO_ROLLE` und `--settings`; das Skript führt Reproduktionen aus, grün heißt verworfen. `diff-reviewer`, `seiten-pruefer` und Clean Code 10 entfallen. Fertig, wenn die Rolle `bau` keinen bestehenden Test ändern kann und ein Befund ohne Reproduktion verworfen wird.

## Paket 16 – Goldener Lauf

Opus baut Nähte in `pipeline.run` für Transport, LLM-Client und Uhr, mit `httpx.MockTransport` und LLM-Aufzeichnungen nach Hash; `make golden-aufnehmen` startet nur Antonio. Fertig, wenn `pytest -m golden` zweimal grün ist, der zweite Lauf „nichts Neues“ meldet, ein geänderter Prompt mit „LLM-Antwort für Stufe … fehlt“ scheitert und die 402-Variante den Ausfall sichtbar rendert.

## Paket 17 – mutmut, erster Auftrag

`tools/mutation.py` prüft nur geänderte Funktionen; scheitert die Probe, fällt die Prüfung weg. Erster echter Auftrag ist `versand.py:99` ohne Zeitzone. Fertig, wenn er vom roten Test bis zum Merge lief und die Probe eine Zeit oder einen Grund liefert.

## Paket 18 – Kommentarwissen

Je Ordner trägt Sonnet Wissen aus Kommentaren an die vier Orte aus plan.md, Workflow-Wissen nach `docs/betrieb.md`. Fertig, wenn `make pruefen` grün ist und die Übernahmen in `outputs/` stehen.

## Paket 19 – Kommentare löschen

Massenlauf ohne weitere Logik: `tools/kommentare_loeschen.py` mit libcst und AST-Vergleich, danach Kommentarregel in Stufe 0. Fertig, wenn jede Datei „Syntaxbaum unverändert“ meldet und die Prüfung ohne eingefrorenen Treffer grün ist.

## Paket 20 – Promo-ID Entwurf

Opus misst am Schnappschuss das zweite stabile Merkmal neben Marke und Zielseite (15 von 76 Gruppen teilen beides) und schreibt `T1.json` nach Baustein; der Testagent schreibt den Abnahmetest aus den 7 Paaren. Fertig, wenn der Schlüssel unter den 105 aktiven Angeboten keine Doppelung ergibt, Antonio ihn bestätigt hat und der Test mit `erwarteterFehler` rot ist.

## Paket 21 – Promo-ID Bau

T1 mit Lesemigration, danach T2 für `models.py:88`. Fertig, wenn die 12 Gruppen aus `outputs/auftraege/T1.json` je einen Eintrag ergeben, alle 330 Einträge unter neuer ID lesbar sind, der Titelrückfall fehlt und das Promo-Orakel grün ist.

## Pakete 22–31 – Umbau `report` (Skizze)

Jedes Paket ist ein Auftrag mit `art: umbau`: Der goldene Lauf bleibt byte-gleich, Riesendateien und `PLC2701`-Basis sinken, Tests ziehen auf den öffentlichen Eingang. Die Zahl nennt die verbleibenden Ausnahmen von `report-rechnet-nur`.

- **22:** `collect/geraete/basis.py` und `register.py`, `_preis` einmal; `adapter-unabhaengig` ohne Ausnahme.
- **23:** `laden/` mit `GeraeteSicht`, `geraete_view` verliert vier Kanten (12).
- **24:** `geraete_zeitreihe` ohne `tco_store`, Zyklus view–verlauf–zeitreihe–bewegung gelöst (11).
- **25:** `render_geraete(sicht, env)` ersetzt den Geräteteil von `render_site`.
- **26:** Neugestaltung als `art: verhalten` nach `outputs/strategie-geraete-v4-2026-09-20/plan.md`, PR #16 nur als Vorlage, je Abschnitt eine Sitzung; Orakel grün, Screenshots 1440 und 390 px von Antonio abgenommen.
- **27:** `PromoSicht`, Bildabruf nach `collect` über `collect.http` (7).
- **28:** `IndexSicht`, `html` ↔ `thema` gelöst, ohne `diff_curator` (6).
- **29:** Lieferzeit, Tarife, Wettbewerb, Differenzierung ohne `collect` (3).
- **30:** Restseiten; `render_site` unter 100 Zeilen.
- **31:** Hex-Basis null, `#e60000` nur in `anbieter_farben.py` und `:root`.

## Pakete 32–37 – Umbau `run` und Querschnitt (Skizze)

- **32–34:** Phasen aus `run.phases` als typisierte Funktionen (32 Sammeln bis Bündeln, 33 Vorsortieren und Bewerten, 34 Rest); fertig, wenn `run` eine Phasenliste unter 100 Zeilen ist.
- **35:** `jetzt` in UTC nur aus den zwei Einstiegspunkten, `DTZ` aktiv, Uhr-Basis null; über 400 Zeilen nach Ordnern teilen.
- **36:** `category_sweep.py:74`, `ct_log.py`, `newsroom.py` über `collect.http`, `LlmSitzung` statt Modulzustand, `schichten` ohne Ausnahme.
- **37:** `geraete_config` und `tarif_bezug` ohne `collect`, alle `ignore_imports` leer, `BLE001`-Basis höchstens 39, `make stand` meldet Schritt 10 erfüllt.
