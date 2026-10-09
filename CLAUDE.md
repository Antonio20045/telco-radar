# Telco Radar — Arbeitsgrundlage für Claude-Sitzungen

Höchstens 100 Zeilen, Ordner-CLAUDE.md unter `src/` höchstens 40; Stufe 0 erzwingt beides. Hier stehen nur dauerhaft gültige Regeln, Befehle und Pfade. Eine Lehre wird Prüfung, Typ oder Vertrag, kein neuer Satz. Fachwissen je Bereich steht in `src/telco_radar/collect/`, `collect/geraete/`, `analyze/` und `report/` (je `CLAUDE.md`). Kommentare mit „CLAUDE.md §N“ meinen `git show f6dbf30:CLAUDE.md` (nur mit `grep` durchsuchen).

## Zweck

Automatisches Competitive-Intelligence-System für Vodafone-Manager ohne Technik-Hintergrund: sammelt Meldungen von Netzbetreibern, Fachpresse und Themenquellen, erkennt über den Seen-Store nur wirklich neue, lässt sie von LLM-Agenten bewerten und baut eine deutschsprachige statische Website (Wochenbericht, Promo-Übersicht, Differenzierung, Geräteseite). Jede Aussage verlinkt auf ihre Originalquelle.

## Betrieb

- Website https://telco-radar.onrender.com (Render Static Site aus `site/`), Repo https://github.com/Antonio20045/telco-radar (öffentlich). GitHub Pages bleibt aus.
- `radar.yml` Mi und Fr 11:00 UTC und manuell, `geraete.yml` täglich 02:17 UTC; beide committen `data/` und `site/` und rufen den Render-Hook über `scripts/render_deploy.sh` (Ablauf in `docs/betrieb.md`). `ci.yml` nur von Hand.
- Ein Push auf `main` ist kein Deploy. Den Live-Stand bestätigt nur das ausgelieferte HTML (`curl -L -sS …/index.html`).
- Actions laufen mit Python 3.11 (`.python-version`): keine Syntax erst ab 3.12, etwa Zeilenumbrüche oder gleiche Anführungszeichen in f-String-Feldern.
- Ein Workflow-Push mit `GITHUB_TOKEN` startet keine weiteren Workflows. Ein Job-Timeout heißt in GitHub „cancelled“. Laufzeit steht in `run.phases` im Berichts-JSON.

## Befehle

```bash
make einrichten                  # venv, Playwright-Chromium und Git-Hooks (core.hooksPath .githooks)
make schnell                     # Leiter Stufen 0, 1, 4 auf den geänderten Dateien
make pruefen                     # volle Leiter 0–3 und 5; grün stempelt den Stand
make stand                       # zehn Umbauschritte: erfüllt oder offen, weil …
.venv/bin/python scripts/pruefleiter.py --statisch      # Stufen 0–3
.venv/bin/python tools/auftrag.py outputs/auftraege/<id>.json   # Auftrag vom roten Test bis zum Merge
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_geraete_seite.py
python -m telco_radar.pipeline --no-llm --root .        # E2E ohne Key, verändert data/ und site/
python scripts/quellen_zaehlen.py                       # die einzige gültige Quellenzahl
python scripts/pruefe_portal.py                         # Abnahme der gerenderten Seiten
python scripts/schiess_screenshot.py --seite geraete.html   # 1440 px und 390 px
```

Site ohne Crawl und LLM in einen Wegwerfordner (immer mit `cfg`, sonst entsteht still eine halbe Seite):

```bash
PYTHONPATH=src python -c "from pathlib import Path; from telco_radar.config import load_config; \
from telco_radar.report.html import render_site; render_site(Path('/tmp/site'), Path('data/reports'), load_config(Path('.')))"
```

## Prüfleiter und Hooks

- Grün ist der Exit-Code von `scripts/pruefleiter.py`, nie eine Selbstauskunft; es gibt keinen zweiten Testweg. pre-commit ruft `--schnell`, pre-push `--vor-push`, der Stop-Hook `--schnell` über `scripts/claude_hooks.py stop` (rot heißt weiterarbeiten, nach drei erzwungenen Fortsetzungen in Folge, höchstens zehn je Sitzung, endet sie mit `.pruefleiter/stop-befund.txt`).
- Basen und Ausnahmelisten unter `pruef/` und in `.importlinter` dürfen nur schrumpfen; die Leiter senkt sie selbst. Lockern kann nur Antonio von Hand.
- Auftragsagenten laufen als Rolle `test`, `bau` oder `pruefer` (`.claude/agents/`, `TELCO_ROLLE`, `--settings` aus `scripts/claude_rolle.py`); ein Prüferbefund zählt nur, wenn seine Reproduktion fachlich scheitert.
- Die Claude-Hooks stehen in `scripts/claude_hooks.py`: große Dateien nur mit `limit`, ruff nach jedem Edit, keine Befehle, die Git-Hooks abschalten.

## Dateikarte

| Pfad | Inhalt |
|---|---|
| `config/*.yaml` | Watchlist, Fachpresse, Themenfelder, Settings, Promo-, Gerätequellen und -katalog, CTM-Fokus; kommen über `load_config()` |
| `src/telco_radar/pipeline.py` | Sammeln → Delta → Analyse → Redaktion → Veröffentlichen |
| `src/telco_radar/collect/` | RSS-, Newsroom-, JS-, JSON-Collector, HTTP mit robots.txt |
| `src/telco_radar/dedupe.py` | Seen-Store und Frischefilter |
| `src/telco_radar/analyze/` | Analysten, Editor, Wettbewerb, Differenzierung, CTM |
| `src/telco_radar/report/` | `render_site()`, Vorlagen, `style.css`, `app.js` (Vanilla JS) |
| `src/telco_radar/geraete_pipeline.py`, `tco_model.py` | Tagesjob des Geräteradars, Rechnung der Geräte-Leitzahl |
| `data/state/`, `data/reports/`, `site/` | Bot-Daten aus Actions |
| `scripts/pruefleiter.py`, `scripts/stand.py` | Prüfleiter, Stand der Umbauschritte |
| `docs/umbau/plan.md`, `docs/umbau/pakete.md` | Umbauplan und Pakete; Fortschritt in `outputs/umbau-fortschritt.md` |

## Harte Regeln

1. `site/` und `data/` werden nie von Hand bearbeitet, nie gelöscht oder gekürzt (`seen.jsonl`!) und Daten aus lokalen Läufen nie committet. Produktionsdaten entstehen nur in Actions; nach einem lokalen Lauf `git restore site data`.
2. Keine Secrets, Tokens oder Deploy-Hooks in Dateien, Logs, Commits oder Chat-Ausgaben; sie liegen nur als GitHub-Secrets vor.
3. Gearbeitet und gepusht wird auf `main`, `git add` nur mit Dateinamen. Bei einem Bot-Commit `git pull --rebase origin main`, nie force-pushen.
4. Bot-Schutz (403, Captcha, Radware) wird nicht umgangen. Eine JavaScript-Prüfung (202) darf der echte Browser mit ehrlicher Kennung durchlaufen, ohne Tarnung, Proxy oder Captcha-Löser (Antonio, 08.10.2026). robots.txt samt Crawl-delay und Visit-time gilt, IDs werden nie hochgezählt.
5. Keine Bibliotheken oder Skripte von CDNs; JavaScript bleibt Vanilla in `app.js`, Grafiken rechnet der Server.
6. Alles rendert ohne LLM. Fällt eine Stufe aus, nennt die Seite den Ausfall, statt „nichts gefunden“ vorzutäuschen.
7. Jede Zahl auf einer Seite hat einen Test gegen die Daten, mit Gegenprobe. Tests hängen nie vom heutigen Datum ab.
8. Ein Zeitbudget rechnet gegen die Restzeit des Jobs (`timeout-minutes` und `job_frist_sekunden` gemeinsam).
9. Konkurrierende Actions-Läufe nicht starten, laufende nicht abbrechen.
10. 401/403 Autorisierung, 402 kein Guthaben, 429/503/529 Provider-Last; ein Timeout ist kein falscher Schlüssel.
11. Ist ein Wert bei allen Anbietern gleich, ist das zuerst eine Erfassungslücke; vor jeder Aussage an der Anbieterseite prüfen.

## Clean Code

1. Eine Zahl wird an genau einer Stelle berechnet; Seite, Export, Mail und `app.js` lesen dasselbe Feld.
2. IDs aus stabilen Schlüsseln (Katalog, normalisierte URL), nie aus Titeltext.
3. Ein fehlender Wert ist `None` und erscheint als benannte Lücke, nie als 0; `x or None` ist verboten.
4. Ein nicht bestimmbarer Zustand heißt `unbekannt` und fällt aus Vergleichen heraus.
5. Scheitern ist kein leeres Ergebnis: benannte Ausnahme oder `error`-Feld, kein `except` ohne Protokoll und Weitergabe an die Seite.
6. „Nicht gelesen“ ist nicht „leer“: Altern und Ersetzen nur für wirklich gelesene Seiten.
7. Prüfung und Anzeige teilen eine Definition der Sichtbarkeit; Grenzen sind benannte Konstanten im Modul.
8. Neues Verhalten braucht einen Test, der gegen den alten Stand rot wird; Optik prüfen `pruefe_portal.py` und Screenshots.

## Antonios Stil und Abnahme

- Wenig Text, keine Erklär-Unterzeilen; laienverständliche deutsche Begriffe („Meldungen“, nicht „Signale“). Die Website berichtet, sie berät nicht.
- Markenfarben der Anbieter; Vodafone-Rot ist Akzent, keine Fläche. Die wichtigste Zahl ist die größte Schrift ihres Bereichs.
- Abnahme heißt angesehene Screenshots (1440 px und 390 px); grüne Tests sind kein Nachweis, dass eine Seite gut aussieht.
- Autonom arbeiten, selbst verifizieren, Antonio nicht mit Rückfragen löchern. Alles bleibt kostenlos (Actions, Render Free).
