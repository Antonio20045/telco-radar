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

Der Geräteauftrag v4 ruht bis Paket 13. Vorgezogen werden P0-Punkt 3 (Paket 2) und `test_seiten_zahlen.py` auf Schnappschüssen (Paket 8). Tor P3 und P4 laufen nach Paket 17 als Einzelaufträge, die Neugestaltung als Antonios Aufträge nach Paket 21.a.

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
| 21.a | Goldener Lauf für Verhaltensaufträge | 21 | 3 h |
| 21.b | Vertragsausnahmen senkt die Leiter | 21 | 2 h |
| 22 | Adapterzyklus | 21.b | 6 h |
| 23 | `GeraeteSicht` | 21.b | 8 h |
| 24 | Zeitreihe ohne Store | 21.b | 6 h |
| 25 | `render_geraete` | 23, 24 | 6 h |
| 26 | entfällt (Antonios Aufträge) | – | – |
| 27 | `PromoSicht`, Bildabruf | 21, 21.b | 8 h |
| 28 | `IndexSicht` | 21.b | 6 h |
| 29 | Lieferzeit, Tarife | 21.b | 6 h |
| 30 | Restseiten, `render_site` | 25, 27, 28, 29 | 8 h |
| 31 | Farben | – | 4 h |
| 32 | `run` Phasen I | 21 | 6 h |
| 33 | `run` Phasen II | 32 | 6 h |
| 34 | `run` Phasen III | 33 | 6 h |
| 35 | Uhr | 34 | 8 h |
| 36 | Netzweg, `LlmSitzung` | 21.b | 8 h |
| 37 | Wurzeln, `except`, Abschluss | 22, 30, 31, 35, 36 | 6 h |

Die Pakete 21.a bis 37 sind gegen den Code vom 5. Oktober 2026 ausformuliert; Reihenfolge und Begründung stehen unter „Reihenfolge ab Paket 21“. Pakete im selben Bereich laufen nie gleichzeitig.

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

## Reihenfolge ab Paket 21

Ausformuliert am 5. Oktober 2026 gegen `782cd86`. Zwei Messungen haben die Skizzen geändert: Der goldene Lauf vergleicht jede Seite byte-genau mit `tests/fixtures/golden/<tag>/erwartet.json` und läuft in `pruefleiter.py --voll`, also auch nach jedem Merge in `tools/auftrag.py`; ein Verhaltensauftrag, der eine Seite sichtbar ändert, endet deshalb heute mit „Leiter rot auf main“ und wird zurückgesetzt. Und `lint-imports` meldet eine Ausnahme, deren Import es nicht mehr gibt, als Fehler („No matches for ignored import …“), während `.importlinter` für Sitzungen gesperrt ist; jedes Paket, das eine Kante streicht, bliebe so rot. Daraus werden die Pakete 21.a und 21.b. Paket 26 ist kein Umbaupaket mehr: Die Neugestaltung der Geräteseite sind Antonios eigene Verhaltensaufträge, sobald 21.a steht. Damit fallen die Abhängigkeiten 27–30 ← 26, 31 ← 30 und 32–34 ← 31 weg.

Nötig, bevor Antonio Seitenänderungen über `tools/auftrag.py` bauen lässt:

1. **21** läuft und wird fertig gemacht, weil es `tools/auftrag*.py` ändert, worauf 21.a aufsetzt.
2. **21.a**, weil sonst kein Verhaltensauftrag mit sichtbarer Seitenänderung gemergt werden kann.
3. Kein Paket: Auf Antonios Mac einmal `make pruefen` auf dem aktuellen `main`, weil `tools/auftrag.py` nicht startet, solange `origin/main` Commits nach dem jüngsten Prüfstempel des Klons hat.

Kann später, mit Grund:

- **21.b**, Voraussetzung nur für Umbaupakete, die Kanten streichen; Antonios Aufträge streichen keine.
- **22, 36**, bauen außerhalb von `report/` und dürfen neben Antonios Aufträgen laufen (je ein Platz von `PARALLEL = 2`).
- **32–35**, ändern nur den Ablauf von `pipeline.run` bei byte-gleichen Seiten; außerhalb von `report/`, also ebenfalls neben Antonios Arbeit möglich.
- **23–25, 27–31**, bauen in `report/`, wo auch Antonios Seitenaufträge liegen; `tools/auftrag.py` sperrt überlappende Bereiche, und jeder Umbau dort verschiebt Code, den Antonio gerade ändert. Diese Pakete laufen nach Antonios Abgabe am 7. Oktober.
- **37**, Abschluss, braucht alle anderen.

Startreihenfolge: 21 → 21.a → 21.b → 22 und 36 parallel → 32 → 33 → 34 → 35; nach dem 7. Oktober 23 und 24 (in beliebiger Folge, nicht gleichzeitig) → 25; 27, 28, 29 einzeln nacheinander, 31 jederzeit dazwischen → 30 → 37.

## Paket 21.a – Goldener Lauf für Verhaltensaufträge

Direkt gebaut (Bereich `tools/` und `scripts/`, kein Auftrag). `scripts/golden_aufnehmen.py` bekommt `--seiten-neu ORDNER`: zwei Wiedergaben der bestehenden Aufnahme in frischen Prozessen mit Netzsperre wie bei `freigeben`, bei gleichen Seiten wird nur `erwartet.json` neu geschrieben, `http.jsonl.gz` und `llm.jsonl.gz` bleiben byte-gleich und der sha256 in `_herkunft.json` folgt. `tools/auftrag.py` ruft das bei `art: verhalten` im Worktree nach grüner Abnahme und vor der Leiter auf, nimmt `erwartet.json` und `_herkunft.json` in den Auftragscommit und schreibt die geänderten Seitenpfade ins Protokoll; bei `art: umbau` bleibt `erwartet.json` unberührt, eine Seitenabweichung macht den Umbau rot. Ein Aufnahmeband ändert nur `make golden-aufnehmen`. Fertig, wenn ein Ersatzauftrag `verhalten`, der einen Text auf `geraete.html` ändert, bis zum Merge läuft und das Protokoll genau diese Seite nennt, derselbe Diff als `umbau` mit „Leiter rot“ endet und eine von Hand geänderte Zeile in `erwartet.json` ohne passenden sha256 in Stufe 0 rot wird.

## Paket 21.b – Vertragsausnahmen senkt die Leiter

Direkt gebaut (`scripts/`). Stufe 3 liest aus `lint-imports` die Meldungen „No matches for ignored import …“, streicht genau diese Zeilen aus `ignore_imports` in `.importlinter` und prüft erneut, wie Stufe 1 und 2 ihre Basen senken; nie wird eine Zeile hinzugefügt, und Stufe 0 hält weiter jede neue Ausnahme rot. Weil Sitzungen `.importlinter` nicht bearbeiten dürfen, schreibt nur die Leiter die Datei; lehnt die Umgebung den Commit ab, steht der Befehl unter „Offen“, und die Leiter bleibt auf dem alten Stand trotzdem grün, weil sie selbst senkt. Fertig, wenn ein Test an einem Mini-Paket mit eigener `.importlinter` und einer verwaisten Ausnahme zeigt, dass Stufe 3 genau diese Zeile streicht und grün meldet, gegen den alten Stand rot war, und eine hinzugefügte Ausnahme in Stufe 0 weiter rot ist.

## Paket 22 – Adapterzyklus

Auftrag `umbau`, Bereich `src/telco_radar/collect/geraete/`. `Adapter`, `registriere`, `umgesetzte_methoden` und `GeraeteAbrufFehler` ziehen aus `collect/geraete/__init__.py` nach `basis.py`, `_registriere_anbieter_adapter` nach `register.py`; die sechs Adapter importieren nur noch `basis`, das Paket-`__init__` reicht die Namen für Bestandsimporte weiter. Die vier `_preis` (`vodafone.py:285`, `o2.py:105`, `congstar.py:436`, `telekom.py:532`) werden eine Funktion in `basis.py`; weichen sie ab, hält der Abnahmetest je Adapter das heutige Ergebnis für die Abweichung fest, bevor zusammengeführt wird. Fertig, wenn `adapter-unabhaengig` ohne `ignore_imports` gilt, `grep -rn "def _preis" src/telco_radar/collect/geraete` genau einen Treffer hat, `collect/geraete/__init__.py` in `pruef/riesendateien.txt` gesunken ist und die Gerätetests und der goldene Lauf grün sind.

## Paket 23 – `GeraeteSicht`

Zwei Aufträge `umbau`. Der erste (Bereich `src/telco_radar/laden/`) legt `laden/geraete.py` mit einer eingefrorenen Dataclass `GeraeteSicht` an, die alles enthält, was `geraete_view.aufbereiten` heute selbst aus `state_dir` liest (`geraete_preise.jsonl`, `geraete_tco.json`, `tarife.jsonl`, Gerätestore, Lebenszyklus) samt Lesefehlern als benannte Ausfälle. Der zweite (Bereich `src/telco_radar/report/`) stellt `aufbereiten(sicht, quellen, katalog, heute)` darauf um und zieht `lies_preis` aus `collect.geraete.strukturdaten` ins Laden. Die Kanten `geraete_view` → `analyze.tco_store`, `analyze.geraete_store`, `analyze.geraete_lifecycle`, `collect.geraete.strukturdaten` fallen. Fertig, wenn `report-rechnet-nur` diese vier Ausnahmen nicht mehr hat, `geraete_view.py` keinen Dateizugriff mehr hat (Wächterbasis gesunken), der goldene Lauf byte-gleich und das Geräte-Orakel grün ist.

## Paket 24 – Zeitreihe ohne Store, Zyklus gelöst

Auftrag `umbau`, Bereich `src/telco_radar/report/`; die reinen Funktionen `id_aus_satz` und `basis_aus_satz` ziehen vorher in einem Auftrag mit Bereich `src/telco_radar/tco_model.py` aus `analyze/tco_store.py` dorthin. Der Zyklus `geraete_view` → `geraete_zeitreihe` → `geraete_bewegung` → `geraete_view` löst sich, indem `geraete_bewegung` Katalog, Quellen und die Ansicht als Argument bekommt statt sie in der Funktion zu importieren (`geraete_bewegung.py:223`). Fachlich hängt 24 nicht an 23; beide bauen in `report/`, darum nacheinander. Fertig, wenn `report-rechnet-nur` die Kanten `geraete_zeitreihe` → `analyze.tco_store` und `geraete_bewegung` → `geraete_config` nicht mehr hat, der Abnahmetest mit `grimp` (kommt mit import-linter) zwischen `geraete_view`, `geraete_verlauf`, `geraete_zeitreihe` und `geraete_bewegung` keinen Importkreis mehr findet und der goldene Lauf byte-gleich ist.

## Paket 25 – `render_geraete`

Auftrag `umbau`, Bereich `src/telco_radar/report/`. Der Geräteteil von `render_site` (heute `html.py:1215–1253` und der Export ab `html.py:1706`) wird `report/geraete_seite.py` mit `render_geraete(sicht, env, site_dir) -> list[Ausfall]`; `render_site` lädt die Sicht einmal über `laden.geraete` und ruft nur noch diese Funktion. Damit fällt `html` → `geraete_config`. Fertig, wenn `render_site` um mindestens 80 Zeilen kürzer ist (Messung in `make stand`), `report-rechnet-nur` die Kante `html` → `geraete_config` nicht mehr hat, `html.py` in `riesendateien.txt` gesunken ist und der goldene Lauf byte-gleich ist.

## Paket 26 – entfällt als Umbaupaket

Die Neugestaltung der Geräteseite nach `outputs/strategie-geraete-v4-2026-09-20/plan.md` (PR #16 nur als Vorlage) sind Antonios eigene Aufträge `verhalten` nach Paket 21.a, je Abschnitt einer, abgenommen mit Screenshots 1440 und 390 px. Kein anderes Paket wartet darauf.

## Paket 27 – `PromoSicht`, Bildabruf nach `collect`

Drei Aufträge `umbau`. `promo_bilder.py` zieht nach `collect/promo_bilder.py` und holt über `collect.http` statt mit eigenem `httpx`; der Abrufteil aus `report/bilder.py` und `report/diff_bilder.py` (`og_bild`, `_hol`, `lade_und_lege_ab`) geht mit, im `report` bleiben nur Pfade und Auswahl. `laden/promo.py` liefert `PromoSicht`; `report/promo.py` bekommt `_same_offer` daraus statt aus `analyze.promo_store`. Hängt an 21, weil 21 die Promo-IDs in denselben Dateien ändert. Fertig, wenn `report-rechnet-nur` die Kanten `html` → `promo_bilder`, `bilder` → `httpx`, `diff_bilder` → `httpx`, `promo` → `analyze.promo_store` nicht mehr hat, `promo_bilder.py` unter `collect/` liegt, die `TID251`-Treffer in `pruef/ruff-basis.json` gesunken sind und Promo-Orakel und goldener Lauf grün sind.

## Paket 28 – `IndexSicht`

Auftrag `umbau`, Bereich `src/telco_radar/report/`, das Laden in einem Auftrag unter `laden/`. `DiffStore` liest `laden/index.py` und reicht eine `IndexSicht` an `render_site`; `_schlagzeile` zieht aus `html.py` in ein Modul, das `thema.py` ohne Rückimport aus `html` nutzt (`thema.py:91`). Fertig, wenn `report-rechnet-nur` die Kante `html` → `analyze.diff_curator` nicht mehr hat, `thema.py` `report.html` nicht mehr importiert und der goldene Lauf byte-gleich ist.

## Paket 29 – Lieferzeit, Tarife, Wettbewerb, Differenzierung

Aufträge `umbau` unter `laden/` und `report/`. `lieferzeit.json`, der Warenkorb (`collect.lieferzeit.lade_warenkorb`) und die Tarifdaten aus `collect.tarif_crawler` kommen über `laden/` als Sichten; `html.py` und `lieferzeit_view.py` lesen keine Datei und importieren kein `collect` mehr. Fertig, wenn `report-rechnet-nur` die Kanten `html` → `collect.lieferzeit`, `html` → `collect.tarif_crawler` und `lieferzeit_view` → `collect.lieferzeit` nicht mehr hat, also nur noch `geraete_view` → `tarif_bezug` übrig ist, und Orakel und goldener Lauf grün sind.

## Paket 30 – Restseiten, `render_site` unter 100 Zeilen

Aufträge `umbau`, Bereich `src/telco_radar/report/`. Jede verbleibende Seite wird eine Funktion `render_<seite>(sicht, env, site_dir) -> list[Ausfall]`; `render_site` lädt alle Sichten, ruft die Funktionen und sammelt die Ausfälle. Fertig, wenn `make stand` für `render_site` weniger als 100 Zeilen misst, die Wächterbasis „Dateizugriff in `report/`“ null ist, `html.py` nicht mehr in `riesendateien.txt` steht und der goldene Lauf byte-gleich ist.

## Paket 31 – Farben

Auftrag `umbau`, Bereich `src/telco_radar/report/`. Jede Hex-Farbe außerhalb von `anbieter_farben.py` und dem `:root` in `style.css` wird eine CSS-Variable oder eine benannte Konstante dort; `#e60000` steht nur noch an diesen zwei Stellen. Hängt an keinem Paket, nur nicht gleichzeitig mit einem anderen Auftrag in `report/`. Fertig, wenn `make stand` die Hex-Basis mit 0 meldet, der Wächter ohne Hex-Eintrag in `pruef/waechter-basis.txt` grün ist und der goldene Lauf byte-gleich ist (gleiche Farbwerte, nur anders notiert, sonst `verhalten` mit Screenshots).

## Paket 32 – `run` in Phasen I: Sammeln bis Bündeln

Direkt gebaut oder Auftrag mit Bereich `src/telco_radar/pipeline.py`, `art: umbau`. Die Abschnitte von `run` bis zur Phase „Bündeln“ werden typisierte Funktionen in `pipeline.py` mit einer eingefrorenen Dataclass je Übergabe; `run` ruft sie nacheinander und schreibt `run.phases` unverändert. `pipeline.py` wächst nicht. Fertig, wenn `run` mindestens 250 Zeilen kürzer ist, der goldene Lauf byte-gleich ist und `run.phases` im Berichts-JSON dieselben Namen in derselben Reihenfolge trägt.

## Paket 33 – `run` in Phasen II: Vorsortieren und Bewerten

Wie Paket 32 für die Phasen Vorsortieren und Bewerten, einschließlich der Ausfallpfade ohne LLM. Fertig, wenn `run` weitere 250 Zeilen kürzer ist, der goldene Lauf und seine 402-Variante grün sind.

## Paket 34 – `run` in Phasen III: Rest

Wie Paket 32 für Redaktion, Veröffentlichen und Bericht. Fertig, wenn `make stand` für `run` weniger als 100 Zeilen misst und der goldene Lauf byte-gleich ist.

## Paket 35 – Uhr nur aus den Einstiegspunkten

Direkt gebaut, mehrere Ordner. Die 30 Uhraufrufe außerhalb der Einstiegspunkte (zuletzt `collect/geraete/__init__.py` 4, `versand.py` 3, `analyze/geraete_lifecycle.py` 3, `report/diff_bilder.py` 2, `newsletter/` 4, je einer in 13 weiteren Dateien) bekommen `jetzt: datetime` (UTC) als Parameter aus `pipeline.run` über `naehte.Naehte` oder aus `run_geraete_stage`; `DTZ` bleibt aktiv. Über 400 Zeilen wird nach Ordnern auf mehrere Commits geteilt, jeder mit grüner Leiter. Fertig, wenn `make stand` die Uhraufrufe mit 0 meldet, die Uhr-Basis in `pruef/waechter-basis.txt` fehlt und der goldene Lauf byte-gleich ist.

## Paket 36 – Ein Netzweg, `LlmSitzung`, `schichten` ohne Ausnahme

Aufträge `umbau` je Ordner. `analyze/category_sweep.py:75` (`urllib.request`), `collect/ct_log.py:257` und `collect/newsroom.py` holen über `collect.http`; `ct_log` bekommt die LLM-Funktion als Parameter statt `analyze.llm` zu importieren (`ct_log.py:308`). Der veränderliche Modulzustand von `analyze/llm.py` (`TRANSPORT`, `CLIENT`, `_FALLBACKS`, `_VERBRAUCH`, `_PREISE`, `_BUDGET_USD`, `_DEAD_MODELS`) wird eine Klasse `LlmSitzung`, die `naehte.Naehte` trägt. `classify` und `_THEME_BY_KEY` ziehen aus `report/differentiation.py` nach `analyze/`, damit `diff_curator` nicht mehr in `report` greift. Fertig, wenn `schichten` ohne `ignore_imports` gilt, `ruff check --select TID251` außerhalb der vier erlaubten Dateien leer ist, `llm.py` auf Modulebene nur Konstanten und `log` hat und der goldene Lauf mit 402-Variante grün ist.

## Paket 37 – Wurzeln, breite `except`, Abschluss

`geraete_config.py:206` und `tarif_bezug.py:66` importieren nichts aus `collect` mehr (`autoerkennung` und `tarif_id` ziehen in Wurzelmodule oder werden übergeben); damit fallen die letzten Ausnahmen von `wurzel-unten` und `report-rechnet-nur`. Die breiten `except` sinken von 79 auf höchstens 39, jede Stelle wird eine benannte Ausnahme oder ein benannter Ausfall auf der Seite. Fertig, wenn alle `ignore_imports` in `.importlinter` leer sind, `make stand` die Schritte 9 und 10 als erfüllt meldet und keine Basis gelockert wurde.
