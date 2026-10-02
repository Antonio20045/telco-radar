# Bausteine (inaktiv)

Unveränderte Skizzen aus dem Anhang von `docs/archiv/umbau-konzept.md`. Keine Datei hier wirkt: Sie tragen absichtlich andere Namen und liegen außerhalb der Orte, die Werkzeuge lesen. Ein Paket kopiert einen Baustein an seinen Zielort und gilt erst als fertig, wenn eine Rot-Probe zeigt, dass er anschlägt. Abweichungen vom Baustein begründet das Paket in seinem Fortschrittseintrag.

| Datei | Zielort | Paket |
|---|---|---|
| `pyproject-werkzeug.toml` | `pyproject.toml` (Werkzeugteil) | 3, 5 |
| `importlinter.ini` | `.importlinter` | 4, 5, 8 |
| `pre-commit.sh` | `.githooks/pre-commit` | 12 |
| `pre-push.sh` | `.githooks/pre-push` | 12 |
| `makefile.mk` | `Makefile` | 2, 5, 6, 12, 16 |
| `claude-settings.json` | `.claude/settings.json` | 13 |
| `pruefer.md` | `.claude/agents/pruefer.md` | 15 |
| `auftrag-T1-promo-id.json` | `outputs/auftraege/T1.json` | 20 |

## Begleittext aus dem Konzept

Das sind Skizzen für die Schritte 3 bis 6, auf Telco Radar zugeschnitten und ohne Kommentare. Jeder Baustein gilt erst als aktiv, wenn eine Rot-Probe gezeigt hat, dass er anschlägt: ein absichtlicher Verstoß, der danach wieder entfernt wird.

### `pyproject.toml`, Werkzeugteil

Die Option `--dist worksteal` statt `loadgroup` ist Absicht, weil sonst eine einzelne Datei wie `test_newsletter_seite` mit 211 s die Laufzeit bestimmt (Abschnitt Zielzeit). Die Netzregel steht bewusst bei ruff und nicht bei import-linter: import-linter behandelt Standardbibliothek und Fremdpakete nur als ganze Pakete und könnte `urllib.request` nicht von `urllib.parse` trennen. ruff hat keine eingebaute Basislinie; `pruefleiter.py` vergleicht deshalb die JSON-Ausgabe je Datei und Regel mit `pruef/ruff-basis.json`, genau wie bei mypy. Die Entwicklungsabhängigkeiten (`ruff`, `mypy`, `import-linter`, `pytest-xdist`, `pytest-socket`, `mutmut`, `libcst`) stehen in `requirements-dev.txt` mit festen Versionen.

### import-linter-Verträge (`.importlinter`)

Die Ausnahmeliste von `report-rechnet-nur` ist vollständig und gegen den Klon geprüft: Ursprünglich waren es 27 Kanten; Paket 4 hat die elf aus Schritt 3 gestrichen, mit den verbleibenden 16 meldet `lint-imports` den Vertrag als gehalten. Die Reihenfolge entspricht dem Plan im Abschnitt „Verträge statt Sätze“: die drei Wurzelmodul-Kanten in Schritt 10, der Rest in Schritt 9. `wurzel-unten` ist heute von genau zwei Kanten gebrochen, die hier als Ausnahme stehen. Stufe 0 vergleicht die Länge aller `ignore_imports` mit dem letzten Commit. Der Vertrag „Kein Zyklus im Adapterpaket“ ergibt sich aus `adapter-unabhaengig` zusammen mit der Regel, dass `collect/geraete/__init__.py` nach dem Umbau keine Adapter mehr importiert; bis dahin steht dieser Import ebenfalls in den Ausnahmen.

### Git-Hooks (`.githooks/`) und `Makefile`

Die erste Datei ist `pre-commit`, die zweite `pre-push`. Beide sind absichtlich dünn: Die Logik steht nur in `pruefleiter.py`, damit Hook, Claude-Hook und Auftragsskript nie verschiedene Dinge prüfen.

`make venv` ist getrennt von `make einrichten`, weil `tools/auftrag.py` und der SessionStart-Hook in jedem neuen Worktree und jedem frischen Klon nur die Umgebung brauchen; die Git-Einstellungen gelten ohnehin für alle Worktrees eines Repos.

### `.claude/settings.json`

`sitzung.py` setzt `core.hooksPath`, prüft die Python-Version und schreibt eine Zeile mit dem Stand von `make stand`. `rolle.py` liest `TELCO_ROLLE` und den Zielpfad aus stdin und endet mit Exit 2 und einer Begründung, wenn die Rolle dort nicht schreiben darf; ohne gesetzte Rolle, also in deinen eigenen Sitzungen, lässt er alles durch, was die deny-Liste erlaubt. `nach_edit.py` ruft `ruff check` und `ruff format --check` auf die eine Datei und endet bei Befund mit Exit 2. `grosse_datei.py` blockiert ein Read ohne `limit` auf Dateien über 800 Zeilen. `git checkout --` und `git reset --hard` stehen in der deny-Liste, weil ein Prüfagent damit am 24. September ungesicherte Arbeit vernichtet hat.

### Prüfer-Agent (`.claude/agents/pruefer.md`)

### Beispielauftrag: Promo-ID ohne Titeltext

Das Feld `vorbild` zeigt auf `clustering.py`, weil dort die ID schon richtig aus der normalisierten URL entsteht. Der Fall `gleichzeitig` ist der Grund, warum die Zielseite allein als Schlüssel nicht reicht (15 von 76 Gruppen aktiver Angebote teilen sie); welches zweite Merkmal stabil ist, entscheidet der Entwurf vor diesem Auftrag.

`promo_pipeline.py` steht bewusst nicht unter den erwarteten Dateien. Es liegt außerhalb des Bereichs `analyze/`, benutzt nur `PromoDB` und nicht `entry_id` und muss sich deshalb nicht ändern. Braucht der Bauer doch eine Änderung dort, endet der Auftrag mit „Voraussetzung fehlt“.
