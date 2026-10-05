# Umbau-Plan Telco Radar

Verdichtung von `docs/archiv/umbau-konzept.md` (Messung auf `b7e2e5e`). Pakete: `docs/umbau/pakete.md`, Skizzen: `docs/umbau/bausteine/`. Bei Widerspruch gilt pakete.md.

## Zielbild

Qualität entsteht durch Mechanik, nicht durch Anweisungstext. Sechs Schichten nach Durchsetzungskraft: 1 Code und Struktur, 2 statische Prüfung (Leiter 0–3), 3 Tests (Leiter 4–5, Orakel, goldener Lauf, mutmut), 4 lokale Sperren (Git-Hooks, deny-Liste, Rollen-Hooks), 5 Prüfer mit Reproduktion, 6 Anweisungen (CLAUDE.md ≤ 100 Zeilen). 1–4 entscheidet die Maschine, 5–6 das Modell; Antonio entscheidet, was die Seite zeigt und ob eine Prüfung gelockert wird. Ziel erreicht, wenn `make stand` alle zehn Schritte als erfüllt meldet, alle Ausnahmelisten leer sind und neue Funktionen nur über `tools/auftrag.py` entstehen.

## Regeln

- Grün ist ein Exit-Code von `scripts/pruefleiter.py`, nie eine Selbstauskunft. Es gibt keinen zweiten Testweg.
- Eine Lehre wird Prüfung, Typ oder Vertrag, kein Satz in CLAUDE.md.
- Ein erfüllter Schritt wird eine Stufe-0-Prüfung und kann nicht still zurückfallen.
- Kein Ruleset, keine PR-Pflicht, keine Merge-Queue, keine Cron-Prüfläufe. Actions nur für Datenläufe, `ci.yml` manuell.
- Lokal ist nichts eine harte Grenze. Absicherung ist Erkennung: Nach jedem grünen Volllauf ein Stempel mit `git rev-parse HEAD^{tree}` unter `.git/pruefleiter/gruen/`; `make stand` und SessionStart melden Commits auf `origin/main` ohne Stempel, `tools/auftrag.py` startet dann nicht.
- Eine Python-Version: `.python-version` = 3.11, `python-version-file` in allen Workflows, ruff `target-version = "py311"`.
- `render_site` gibt die nicht gebauten Teile zurück; ist die Liste nicht leer, endet der Workflow-Schritt rot, die Seite nennt den Ausfall. Der Render-Hook versucht dreimal und sucht danach das Tagesdatum im Live-HTML.
- Kommentare: kein `#`-Kommentar außer `noqa: CODE`, `type: ignore[code]`, `pragma: no cover`; Docstrings nur an öffentlichen Namen, ein bis drei Sätze; nie Datum, Name, Phasenkürzel oder „CLAUDE.md §“. Wissen zieht in einen Test mit sprechendem Namen, eine benannte Konstante, die Commit-Nachricht oder `outputs/`; Workflow-Wissen nach `docs/betrieb.md`.
- IDs nie aus Titeltext. Die Uhr liest nur `pipeline.run` und `run_geraete_stage`, einmal, in UTC. Kein `except Exception` mit Leerwert: benannte Ausnahme oder benannter Ausfall auf der Seite.

## Prüfleiter

Billig vor teuer, Abbruch bei der ersten roten Stufe. Zeitziele für den M4 Pro.

| Stufe | Werkzeug | Prüft | Ziel |
|---|---|---|---|
| 0 Wächter | eigenes Skript | Riesendateien nur auf Schrumpfliste, CLAUDE.md ≤ 100 Zeilen, `continue-on-error`/`\|\| true` nur an benannten Stellen, kein Testzugriff auf `data/state`, keine gewachsene Basis, AST-Regeln, `PLC2701` gegen Basis | < 1 s |
| 1 Lint | `ruff check` | nur neue Befunde gegen `pruef/ruff-basis.json` | < 2 s |
| 2 Typen | `mypy` | Fehler je Datei und Code gegen `pruef/mypy-basis.txt` (237, ohne Zeilen) | 10–20 s |
| 3 Schichten | `lint-imports` | Verträge unten | < 3 s |
| 4 Betroffen | `pytest` | Tests, die ein geändertes Modul direkt importieren, ohne `browser`/`langsam`/`golden`; davon die schnellsten bis 8 s gemessener Testzeit (Fixture-Aufbau je Datei eingerechnet, geänderte Testdateien zuerst), den Rest prüft Stufe 5 im pre-push; ab 4 s Schätzung `-n 4`, Kappe 45 s ist Warnung | < 5 s |
| 5 Voll | `pytest -n auto --dist worksteal` | alles außer `netz` | < 4 min (gerechnet 2,3) |

Vorlagen, `style.css`, `app.js` ziehen Marker `seite` in Stufe 4; `config/`, `pyproject.toml`, `conftest.py` springen in Stufe 5. Ausgabe: Grün eine Zeile, Rot höchstens 60 (Stufe, Datei:Zeile, Erwartung, Ergebnis); volles Log in `.pruefleiter/letzter-lauf.log`, Zeiten in `.pruefleiter/zeiten.csv`. pre-commit = `--schnell` (0, 1, 4 auf vorgemerkten Dateien, Budget 30 s), pre-push = `--voll` und verlangt, dass HEAD `origin/main` enthält.

## Ausnahmelisten-Prinzip

Bestandsverstöße stehen unter `pruef/` oder in `ignore_imports`: `rot-bekannt.txt`, `ruff-basis.json`, `mypy-basis.txt`, `riesendateien.txt` (44 Dateien > 400 Zeilen, mit Zeilenzahl), `privat-basis.txt` (227 × `PLC2701`), `tests-mit-bestand.txt`, AST-Basen (Dateizugriff in `report/`, 94 Uhraufrufe, Hex-Farben, 79 × `BLE001`). Listen dürfen nur schrumpfen: Stufe 0 vergleicht mit dem letzten Commit, Senken schreibt die Leiter selbst, Erhöhen ist rot. Die Dateien stehen in der deny-Liste; lockern kann nur Antonio von Hand.

## Verträge

`.importlinter` (Baustein `importlinter.ini`) plus ruff `banned-api` für den Netzweg.

| Vertrag | Regel | Ausnahmen heute |
|---|---|---|
| `schichten` | `report` → `laden` → `analyze` → `collect` | `collect.ct_log`→`analyze.llm`, `analyze.diff_curator`→`report.differentiation` (36) |
| `wurzel-unten` | `models`, `tco_model`, `geraete_model`, `tarif_model`, `geraete_config`, `tarif_bezug` importieren keine Schicht | `geraete_config`→`collect.geraete.autoerkennung`, `tarif_bezug`→`collect.tarif_crawler` (37) |
| `report-rechnet-nur` | `report` importiert weder `collect` noch Stores, `diff_curator`, `httpx`, `requests` | 27 Kanten, unten |
| Ein Netzweg (ruff `TID251`) | `httpx`, `requests`, `urllib.request` nur in `collect/http.py`, `analyze/llm.py`, `newsletter/transport.py`, `versand.py` | `category_sweep.py:74`, `ct_log.py:256`, `newsroom.py`, `promo_bilder.py:359`, `bilder.py:385`, `diff_bilder.py:170` (27, 36) |
| `adapter-unabhaengig` | Geräteadapter importieren einander und das Paket-`__init__` nicht | Zyklus Paket ↔ 6 Adapter (22) |
| `orakel` | `tests/orakel` importiert aus `telco_radar` nur `report.html.render_site` | neu (8) |

Die 27 Kanten von `report-rechnet-nur` (ohne Präfix `telco_radar.`) je Paket, das sie streicht; in Klammern der Rest:

- Paket 4 (→ 16), Konstanten nach `analyze/begriffe.py`, Status nach `geraete_model`: `report.html`→`analyze.category_sweep`, `analyze.promo_ranker`, `analyze.promo_editor`, `analyze.highlight_topics`, `analyze.ctm`; `report.promo`→`analyze.promo_ranker`; `report.wettbewerb`→`analyze.promo_ranker`; `report.thema`→`analyze.highlight_topics`; `report.geraete_bereinigung`, `report.geraete_pruefung`, `report.geraete_vergleich`→`analyze.geraete_store`.
- Paket 23 (→ 12): `report.geraete_view`→`analyze.tco_store`, `analyze.geraete_store`, `analyze.geraete_lifecycle`, `collect.geraete.strukturdaten`.
- Paket 24 (→ 11): `report.geraete_zeitreihe`→`analyze.tco_store`.
- Paket 27 (→ 7): `report.html`→`promo_bilder`; `report.bilder`→`httpx`; `report.diff_bilder`→`httpx`; `report.promo`→`analyze.promo_store`.
- Paket 28 (→ 6): `report.html`→`analyze.diff_curator`.
- Paket 29 (→ 3): `report.html`→`collect.lieferzeit`, `collect.tarif_crawler`; `report.lieferzeit_view`→`collect.lieferzeit`.
- Paket 37 (→ 0): `report.html`→`geraete_config`; `report.geraete_bewegung`→`geraete_config`; `report.geraete_view`→`tarif_bezug`.

AST-Skript in Stufe 0: kein `open`, `read_text`, `write_text` in `report/`; kein `datetime.now`, `date.today`, `time.time` außerhalb von `pipeline.py`, `geraete_pipeline.py`, `collect/http.py`; Hex-Farben nur in `anbieter_farben.py` und im `:root` von `style.css`.

## Testregeln

- Hermetisch: Tests lesen `tests/fixtures/bestand/<datum>/` aus `scripts/schnappschuss.py` (mit `_herkunft.json`: Commit, Quelle, Filter, sha256), nie `data/` oder `site/`. Ein Audit-Hook (`sys.addaudithook`, aktiv per Variable) lässt solche Zugriffe scheitern; `pytest-socket` erlaubt nur `127.0.0.1`; Chromium routet nur zum lokalen Server. Uhr = Schnappschussdatum. Schnappschüsse werden nie geändert, nur ersetzt.
- Jede Fixture unter `tests/fixtures/` hat einen Herkunftseintrag mit passendem sha256 (Stufe 0); erfundene Fixtures werden ersetzt oder mit ihren Tests gelöscht.
- Marker: ohne (Logik < 1 s), `seite`, `browser` (über Fixture gesetzt), `langsam` (> 5 s, nur pre-push), `golden` (nur pre-push), `netz` (nie automatisch). Chromium einmal je Worker, Rendern je Variante einmal.
- Kein Test liest Code, Vorlagen, Workflows oder Doku als Text (auch nicht per `getsource`); die Regel dahinter wird Vertrag oder Verhaltenstest.
- Orakel in `tests/orakel/` rechnen jede zitierfähige Zahl unabhängig nach.
- Goldener Lauf: `pipeline.run` offline mit `httpx.MockTransport`, LLM-Aufzeichnungen nach Hash aus Stufe, Modell, Prompt und fester Uhr; prüft HTML und dass ein zweiter Lauf nichts Neues meldet. Fehlende Aufnahme scheitert mit Hinweis auf `make golden-aufnehmen`, das nur Antonio startet. Eine 402-Variante muss rendern und den Ausfall nennen.
- mutmut nur auf geänderten Funktionen und nur in `tools/auftrag.py`; scheitert die Probe, fällt die Prüfung weg.

## Auftragsformat

JSON nach Baustein `auftrag-T1-promo-id.json`: `id`, `art` (`umbau` lässt den goldenen Lauf byte-gleich, `verhalten` darf neu aufnehmen), `ziel`, `bereich` (Ordner unter `src/telco_radar/`), `erwarteteDateien`, `vorbild`, `seite`, `datenquelle` (Dateien, Bot-Commit, Schnappschuss), `abnahme`, `erwarteterFehler`, `abhaengigVon`, `migration`, `wasDarfNiePassieren` (Pflicht bei Schreiben oder Abruf). Ablauf: Abnahmetest zuerst und fachlich rot, dann bauen; nach zwei roten Runden Notiz `outputs/auftraege/<id>-notiz.md`; fehlende Voraussetzung beendet den Auftrag ohne Runde; Diff ≤ 400 Zeilen Produktcode; Worktree `../telco-radar-wt/<id>` mit `make venv`, Zweig nie gepusht, `merge --ff-only`, höchstens zwei parallel; Kosten nach `outputs/auftraege/kosten.csv`.

## Rollen

| Rolle | Modell | Schreibt | Liefert |
|---|---|---|---|
| Entwurf, Zerschneiden | Opus | `outputs/auftraege/` | Entwurf, Auftrags-JSON |
| Abnahmetest | Opus | `tests/` | roten Test mit erwartetem Fehler |
| Bauen TCO, Datenmodell, Stores, IDs, Migration | Opus | `src/` | Diff, Commit-Nachricht |
| Bauen Vorlagen, CSS, Adapter | Sonnet | `src/` | Diff, Commit-Nachricht |
| Prüfen | Opus | nur `/tmp/pruefer/` | Befunde mit Reproduktion |
| Suchen, Logs | Haiku | nichts | ≤ 5 Zeilen |
| Grün oder rot | kein Modell | – | Exit-Code |

Rolle per `TELCO_ROLLE` und `--settings`; `bau` darf unter `tests/` nur neue Dateien anlegen. Ein Prüferbefund ohne Reproduktion, die fachlich scheitert, wird verworfen. `diff-reviewer` und `seiten-pruefer` gehen in `pruefer` auf.

## Zehn Schritte

1. **Aufräumen** (P1): fertig, wenn `_to_delete` fehlt und `origin` nur `main` und behaltene Zweige hat.
2. **Workflows, Python** (P2): fertig, wenn ein kaputter Zeitreihen-Render im Wegwerf-Worktree Exit ≠ 0 liefert, die Seite den Ausfall nennt und `geraete.yml` das Tagesdatum live zeigt.
3. **Format, Werkzeuge, Basen** (P3–P6): fertig, wenn `ruff format --check` grün ist und vier Rot-Proben scheitern (unbenutzter Import, neuer mypy-Fehler, `collect` in `report`, neue Datei mit 401 Zeilen).
4. **Hermetische Tests** (P7–P11): fertig, wenn die volle Suite zehnmal in Folge grün ist, unter 4 min bleibt und ein Bot-Commit auf `data/state` kein Testergebnis ändert.
5. **Hooks, CLAUDE.md** (P12–P13): fertig, wenn ein roter Test nicht pushbar ist, `--no-verify` scheitert, ein Push mit `-c core.hooksPath=/dev/null` als ungeprüft gemeldet wird und ein Stop mit rotem Lint weiterläuft.
6. **Auftragsablauf** (P14–P17): fertig, wenn ein echter Auftrag vom roten Test bis zum Merge lief, jedes Grün ein vom Skript gelesener Exit-Code ist und die mutmut-Probe Zeit oder Grund liefert.
7. **Kommentarabbau** (P18–P19): fertig, wenn die Kommentarprüfung ohne Basis grün ist und jede Datei einen unveränderten Syntaxbaum meldet.
8. **Promo-IDs** (P20–P21): fertig, wenn T1-Gruppen je einen Eintrag ergeben, alle 330 Einträge unter neuer ID lesbar sind, `models.py:88` ohne Titelrückfall auskommt und das Promo-Orakel grün ist.
9. **Lader, `render_site`** (P22–P31): fertig, wenn `report-rechnet-nur` nur noch die drei Wurzelkanten hat, `promo_bilder.py` in `collect` liegt, die Hex-Basis null ist und `render_site` unter 100 Zeilen hat.
10. **`run`, Uhr, Fehler, Netzweg** (P32–P37): fertig, wenn `run` eine Phasenliste unter 100 Zeilen ist, Uhraufrufe nur in den zwei Einstiegspunkten stehen, `category_sweep.py` über `collect.http` geht, `llm.py` keinen veränderlichen Modulzustand hat, `wurzel-unten` ohne Ausnahme gilt und die `BLE001`-Basis halbiert ist.
