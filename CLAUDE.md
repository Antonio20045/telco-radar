# Telco Radar — Arbeitsgrundlage für Claude-Sitzungen

## Pflege dieser Datei

- Höchstens 200 Zeilen und 20.000 Bytes; `tests/test_claude_md_groesse.py` erzwingt das.
- Hier stehen nur dauerhaft gültige Regeln, Befehle und Pfade.
- Sitzungsberichte, Messungen mit Datum, Phasenstände und Auftragstexte gehören nach `outputs/` oder `docs/`, nicht hierher.
- Wer etwas ergänzt, entfernt dafür etwas Veraltetes.
- Kommentare im Code, die auf „CLAUDE.md §N“ verweisen, meinen die alte Fassung. Sie steht in der Git-Historie (`git show f6dbf30:CLAUDE.md`) und wird bei Bedarf gezielt mit `grep` durchsucht, nie ganz geladen.

## Zweck

Telco Radar ist ein automatisches Competitive-Intelligence-System für Vodafone-Manager ohne Technik-Hintergrund. Es sammelt Meldungen von Netzbetreibern, Fachpresse und Themenquellen, erkennt über den Seen-Store nur wirklich neue Meldungen und lässt sie von LLM-Agenten bewerten. Daraus entsteht eine deutschsprachige statische Website mit Wochenbericht, Promo-Übersicht, Differenzierung und Geräteseite, bei der jede Aussage auf ihre Originalquelle verlinkt.

## Live-URLs und Betrieb

- Website: https://telco-radar.onrender.com (Render Static Site, Publish-Verzeichnis `site/`).
- Repo: https://github.com/Antonio20045/telco-radar (öffentlich).
- `radar.yml` läuft Mi und Fr 11:00 UTC sowie manuell, committet `data/` und `site/` und löst den Render-Deploy-Hook aus.
- `geraete.yml` läuft täglich 02:17 UTC und pflegt den Gerätestand.
- `ci.yml` führt bei jedem Push auf `main` und bei Pull Requests `pytest -q` aus.
- Ein Push auf `main` ist kein Deploy; erst Bot-Commit plus Render-Hook bringen einen neuen Live-Stand.
- Den Live-Stand bestätigt nur das ausgelieferte HTML (`curl -L -sS …/index.html`), nicht ein grüner Actions-Status.
- GitHub Pages bleibt aus.

## Befehle

```bash
export PYTHONPATH=src
python -m pytest -q                                   # ganze Suite (lang, 3000+ Tests)
python -m pytest -q tests/test_geraete_seite.py       # gezielt eine Datei
python -m pytest -q -k geraete                        # gezielt ein Themenbereich
python -m telco_radar.pipeline --no-llm --root .      # E2E ohne API-Key (verändert data/ und site/!)
python scripts/validate_sources.py                    # Quellen-Health, braucht Netz
python scripts/quellen_zaehlen.py                     # die einzige gültige Quellenzahl
python scripts/pruefe_portal.py                       # Abnahme der gerenderten Seiten im Browser
python scripts/schiess_screenshot.py --seite geraete.html   # Screenshots 1440 px und 390 px
```

Site ohne Crawl und ohne LLM in einen Wegwerfordner rendern (immer mit `cfg`, sonst entsteht still eine halbe Seite):

```bash
PYTHONPATH=src python -c "from pathlib import Path; from telco_radar.config import load_config; \
from telco_radar.report.html import render_site; render_site(Path('/tmp/site'), Path('data/reports'), load_config(Path('.')))"
```

## Dateikarte

| Pfad | Inhalt |
|---|---|
| `config/watchlist.yaml` | Betreiber je Region mit Primärquellen; wird direkt editiert, nie über `build_sources.py` |
| `config/news_sources.yaml` | Telco-Fachpresse, Tagging über Aliase und Wortgrenzen |
| `config/tech_sources.yaml` | Themenfelder (KI, Chips, Satellit, Regulierung …); keine Wettbewerber |
| `config/settings.yaml` | Modelle, Limits, HTTP, Zeitbudgets, Schalter der Pipeline |
| `config/promo_sources.yaml` | Aktionsseiten je Marke für die Promo-Übersicht |
| `config/geraete_quellen.yaml` | Anbieter des Geräteradars mit Methode und Grund je Zeile |
| `config/geraete_katalog.yaml` | Verfolgte Gerätemodelle; einzige Quelle der Geräte-IDs |
| `config/ctm_fokus.yaml` | Was „für uns wichtig“ heißt; steuert die Reihenfolge der Startseite |
| `src/telco_radar/pipeline.py` | Ablauf Sammeln → Delta → Analyse → Redaktion → Veröffentlichen |
| `src/telco_radar/collect/` | RSS-, Newsroom-, JS- und JSON-Collector, HTTP mit robots.txt |
| `src/telco_radar/dedupe.py` | Seen-Store und Frischefilter (Delta-Logik) |
| `src/telco_radar/analyze/` | Analysten, Editor, Wettbewerb, Differenzierung, CTM |
| `src/telco_radar/report/html.py` | `render_site()` für die ganze Website |
| `src/telco_radar/report/templates/` | Jinja-Vorlagen plus `style.css` und `app.js` (Vanilla JS) |
| `src/telco_radar/geraete_pipeline.py` | Tagesjob des Geräteradars |
| `src/telco_radar/tco_model.py` | Rechnung der Geräte-Leitzahl |
| `src/telco_radar/report/geraete_view.py` | Aufbereitung der Geräteseite |
| `data/state/seen.jsonl` | Dedup-Gedächtnis (v2, ein Hash je Zeile) |
| `data/state/geraete_tco.json` | Bündel und SIM-only-Referenzen für die Leitzahl |
| `data/reports/` | Berichte als `.md` und `.json` je Ausgabe |
| `site/` | Generierte Website; wird nur von Actions geschrieben |
| `scripts/pruefe_quellenvorschlag.py` | Abnahme-Check für neue Quellen; ohne PASS keine neue Quelle |
| `docs/clean-code-referenz.md` | Prüfkatalog für den `diff-reviewer`-Agenten |

## Harte Regeln

1. `site/` und `data/state/` werden nie von Hand bearbeitet. Änderungen gehören in `src/telco_radar/report/`, die Vorlagen oder `config/`.
2. `data/state/seen.jsonl` nie löschen, kürzen oder mit lokalen Testdaten überschreiben; sonst meldet der nächste Lauf null oder zu viele neue Meldungen.
3. State und Berichte aus lokalen Läufen (`data/state/`, `data/reports/`, `site/`) nie committen. Produktionsdaten entstehen nur in GitHub Actions.
4. Keine Secrets, Tokens oder Deploy-Hooks in Dateien, Logs, Commits oder Chat-Ausgaben. Sie liegen ausschließlich als GitHub-Secrets vor.
5. `git add` nur gezielt mit Dateinamen, nie `git add -A` oder `git add .`; vor jedem Commit `git status` prüfen.
6. Gearbeitet und gepusht wird auf `main`. Bei einem gleichzeitigen Bot-Commit `git pull --rebase origin main` und erneut pushen, nie force-pushen.
7. Bot-Schutz (403, 202-Challenge, Radware) wird nicht umgangen. Solche Quellen bleiben als Referenz dokumentiert. robots.txt inklusive Crawl-delay und Visit-time wird eingehalten, IDs werden nie hochgezählt.
8. Keine Bibliotheken oder Skripte von CDNs. JavaScript bleibt Vanilla in `app.js`, Grafiken rechnet der Server.
9. Alles muss ohne LLM rendern. Fällt eine LLM-Stufe aus, zeigt die Seite das sichtbar an, statt „nichts gefunden“ vorzutäuschen.
10. Jede Zahl auf einer Seite braucht einen Test, der sie gegen die Daten hält. Ein Test, dessen Lookup ins Leere läuft, ist grün und prüft nichts; Gegenproben sind Pflicht.
11. Tests hängen nie vom heutigen Datum ab; Fixtures setzen ihr Datum selbst.
12. Ein Zeitbudget rechnet gegen die Restzeit des Jobs. Wer `timeout-minutes` in `radar.yml` ändert, ändert `job_frist_sekunden` mit.
13. Konkurrierende Actions-Läufe werden nicht gestartet, laufende nicht abgebrochen.
14. 401/403 bedeutet Autorisierung, 402 fehlendes Guthaben, 429/503/529 Provider-Last. Ein Timeout ist kein falscher Schlüssel.
15. Actions laufen mit Python 3.11. Keine Syntax, die erst ab 3.12 geht (z. B. Zeilenumbrüche oder gleiche Anführungszeichen in f-String-Feldern). Ein Render, der lokal mit 3.12 klappt, kann in Actions still scheitern.
16. Ist ein Wert bei allen Anbietern gleich (etwa nur 36-Monats-Raten), ist das zuerst ein Verdacht auf eine Erfassungslücke. Vor jeder Aussage darüber an der Anbieterseite prüfen.
17. `wip(auto)`-Commits des Stop-Hooks werden nie gemergt, gerebased oder gepusht. Worktree-Branches werden nach dem Übernehmen der Änderungen gelöscht.

## Clean Code

1. Eine Zahl wird an genau einer Stelle berechnet (Gerätezahlen in `tco_model.py`). Seite, Export, Mail und `app.js` lesen dasselbe Feld; muss eine Rechnung in Python und JS existieren, hält ein Browser-Test beide zusammen.
2. IDs kommen aus stabilen Schlüsseln: Geräte aus dem Katalog, Meldungen und Cluster aus der normalisierten URL, nie aus Titeltext. Der Titel dient nur zum Finden des Katalogeintrags.
3. Ein fehlender Wert ist `None` und erscheint als benannte Lücke, nie als 0 und nie geraten. 0 steht nur, wo 0 eine Aussage ist („keine Mindestlaufzeit“, gemessene Restschuld 0,00 €); `x or None` ist deshalb verboten.
4. Ein nicht bestimmbarer Zustand heißt `unbekannt` und fällt aus Vergleichen heraus; er wird nie als `neu` angenommen. Felder mit Vorgabewert brauchen eine eigene Ausfallprüfung (`_ist_ausfall()`).
5. Scheitern ist kein leeres Ergebnis: Eine Stufe wirft eine benannte Ausnahme oder setzt ein `error`-Feld, nie `[]`. Kein `except` ohne Protokoll und ohne Weitergabe an die Seite (siehe Regel 9).
6. „Nicht gelesen“ ist nicht „leer“: Altern (`mark_stale`) und Ersetzen betreffen nur wirklich gelesene Seiten. Das gilt auch für einen wegen Visit-time übersprungenen Anbieter. Ein Deckel schneidet nach der Vorprüfung ab, nie den Scan selbst.
7. Prüfung und Anzeige teilen dieselbe Sichtbarkeits- und Auswahlmenge aus einer Definition; zwei `_SICHTBAR`-Listen sind ein Fehler.
8. Konfigurierbare Werte stehen in `config/*.yaml` und kommen über `load_config()`; Grenzen und Deckel sind benannte Konstanten im Modul, nie Zahlen in einer Vorlage.
9. Neues Verhalten braucht einen Test, der gegen den alten Stand rot wird. Wo Tests nicht greifen (Optik, Aussage einer Grafik), treten `pruefe_portal.py` und `schiess_screenshot.py` an ihre Stelle.
10. Vor jedem Commit läuft der Agent `diff-reviewer` mit `docs/clean-code-referenz.md` über den Diff. S1- und S2-Befunde blockieren den Commit, bis sie behoben sind.

## Fallstricke (gelernt)

**Betrieb und Deploy**
- Ein Push mit dem `GITHUB_TOKEN` aus einem Workflow startet keine weiteren Workflows. Jeder Workflow, der `site/` committet, ruft den Render-Hook selbst auf (wie `radar.yml` und `geraete.yml`).
- Render klont sofort; zwischen `git push` und Hook-Aufruf 15 s warten. Nach einem Push den Ausgang von `deploy.yml` prüfen, Gegenprobe ist `md5sum` der Live-Seite gegen `site/index.html`.
- Ein Job-Timeout erscheint in GitHub als „cancelled“, nicht als „failed“. Nebenstufen vor `render_site()` können so den ganzen Bericht kosten; lange Zweige bekommen eigene Jobs, und der Bestand wird vor dem Rendern committet.
- Laufzeit wird aus `run.phases` im Berichts-JSON beurteilt, nicht aus Faustzahlen. Das Pipeline-Log wird auch bei Erfolg als Artefakt abgelegt.
- In der Cloud-Sandbox erreicht Chromium das Netz nicht und Google Fonts laden nicht: `newsroom_js`-Quellen melden dort FAIL, gemessene Breiten gelten nur für die Rückfallschrift. Layout-Tests prüfen deshalb Eigenschaften (kein Überlauf bei verbreitertem Text), keine Pixelbreiten.
- Nach einem `--no-llm`-Lauf fällt `pruefe_portal.py` Kriterium 4 durch; vor dem Messen `git checkout -- site data`.

**Quellen und Sammeln**
- Der Abnahme-Check prüft Form, nicht Wert. Vor jedem Eintrag die YAML-Kommentare lesen, dort stehen bereits abgelehnte Quellen; geparste Quellen mit `--zweimal` messen.
- Börsen- und SEC-Filing-Feeds sind gesperrt, weil alle Meldungen denselben Titel tragen.
- Undatierte Meldungen sortieren ans Ende und werden nie gelesen. Bei jeder neuen Quelle `published` prüfen; `collect/rss.py` liest das Datum notfalls aus dem Link.
- HTTP 200 kann eine leere JS-Hülle sein. Zuerst den Endpunkt suchen (`__NEXT_DATA__`, `/wp-json/wp/v2/posts`, `?format=feed`), erst dann Playwright.
- HTTP 202 ist für `raise_for_status()` kein Fehler; eine Challenge-Seite liefert still null Links. Ein 403 ist nicht automatisch ein User-Agent-Filter: erst messen, dann bauen.
- `collect.http.fetch` wirft bei 404 und 403. Eine fehlende robots.txt (404) heißt „keine Regeln“, 403 heißt „nicht anfassen“. Die `*`-Gruppe ist nicht immer die strengste.
- `_JS_GLEICHZEITIG` bleibt bei 4, auch wenn `collect_max_workers` steigt. Die Sammelphase wird von der langsamsten Einzelquelle gedeckelt; dagegen hilft nur `_QUELLEN_FRIST`.
- Meldungen werden nie gekappt, nur parallelisiert: Scheitert ein Analysten-Stapel, kommen seine Meldungen als `_ungelesen` zurück und bleiben aus dem Seen-Store.
- Themenfelder gehören nicht in die Watchlist. Wer den Editor-Themenabschnitt ändert, ändert Prompt und `validate_editorial_briefing` gemeinsam.

**LLM**
- 402 wird nie wiederholt, sondern als `LLMModelUnavailable` an den nächsten Anbieter der Kette gegeben.
- Eine leere Antwort bedeutet meist ein zu kleines `max_tokens`, weil die Denkspur mitzählt. Untergrenze je Stufe sind 16000.
- Jede Stufe holt ihr Modell aus `_modelle_fuer_anbieter()`; wer einen Anbieter ergänzt, prüft alle Aufrufer.
- `_items_payload` in `analyze/agents.py` ist eine Positivliste; ein neues Feld am `Item` erreicht den Analysten erst, wenn es dort eingetragen ist.
- Stufen, deren Ergebnis an einer Karte hängt (z. B. Übersetzung), laufen auf den berichteten Meldungen (`berichtete_items()`), nicht auf `new_items`.
- Die Sprache wird nie auf der Überschrift erkannt, sondern auf Text ab 200 Zeichen. `py3langid.classify()` liefert eine Log-Wahrscheinlichkeit; Schwellen brauchen `norm_probs=True`.
- Ein Subagent, der einen Adapter baut, erfindet notfalls seine Fixture. Fixtures stammen aus gespeicherten echten Abrufen, und ein Prüfagent ist Pflicht.

**Tests und Abnahme**
- Sichtbarkeit und Farbe werden im Browser gemessen (computed `display`, Boxhöhe, computed color), nie am Attribut oder an der Klasse: eine `display`-Regel übersteuert `[hidden]`, und CSS-Spezifität schlägt die Absicht.
- Eine Rechnung, die im Browser läuft, wird im echten Chromium getestet, nicht in Python nachgebaut.
- Wer oberhalb der Falz etwas einfügt, prüft `pruefe_portal.py` Kriterium 1.
- Seitenhöhen werden strukturell begrenzt (Zeilendeckel im Modul, zugeklappte `<details>`), sonst kippt der Höhentest mit dem Datenbestand.
- Die Extraktionslogik arbeitet auf Text, nicht auf PDF; `pdftotext` ist ein externes Binary und gehört nicht in die Tests.

**Geräteradar**
- Der Zustand (neu, refurbished, B-Ware) ist eine Preisdimension in der `sku_id`; verglichen wird nur `neu`. o2 schreibt „(gebraucht)“ und „(erneuert)“.
- `generation` ist die Nummer innerhalb einer Baureihe; gezählt und gefiltert wird je (Hersteller, Baureihe) über `serie_aus_modell()`.
- Der niedrigste Preis ist der wahrscheinlichste Fehler. `report/geraete_pruefung.py` sortiert Selbstwidersprüche aus; Ausreißer gegen den Markt werden gemeldet, nicht gelöscht.
- Ein Modellzusatz hinter dem Katalogtreffer („Fold“, „FE“, „Edge“) verwirft die Zuordnung (`_MODELLZUSATZ`). Der Zubehörfilter braucht zwei Listen.
- Bei Netzbetreibern steht der Gerätepreis selten im naheliegenden Feld (Anzahlung gegen Gesamtpreis); Bündel aus Gerät plus Zubehör werden verworfen.
- Adapter liefern Quelllinks absolut; relative Adressen aus einer API-Nutzlast werden gegen die Website aufgelöst, nicht gegen die API.
- `laeufe` zählt nur vollständige Läufe, `termine` jeden Tag mit gesehenen Listungen. Jeder Anbieter bekommt `_MINDEST_JE_ANBIETER` Zeit.
- Eine Datenqualitätsheuristik schaltet nie die Navigation; die Veröffentlichungsschwelle rechnet gegen den Bestand.

## Geräteseite: Leitzahl (Ziel, noch nicht umgesetzt)

Soll-Definition der Leitzahl „Kosten über 24 Monate“:

> Kosten über 24 Monate = Anzahlung + 24 Monate Tarif + alle Geräteraten inklusive Restschuld nach Monat 24 + Anschlusspreis.

Erfasst werden alle angebotenen Ratenlaufzeiten, nicht nur eine: Telekom 6/12/24/36, o2 24/36, congstar 24/36, 1&1 „24+12“ mit Schlusszahlung, Vodafone 12/24/36. Die Laufzeit gehört in den Bündelschlüssel, sonst überschreiben sich die Varianten.

Das ist das Ziel, nicht der Ist-Stand von `tco_model.py` (`tco_24()`, `tco_bindung()`). Wer daran arbeitet, gleicht Code, Etiketten und Tests an diese Definition an und prüft, dass Rechenweg-Panel und Katalog dieselbe Zahl zeigen.

## Antonios Stil und Abnahme

- Wenig Text auf den Seiten. Keine Erklär-Unterzeilen unter Überschriften, Grafiken oder Zahlen.
- Laienverständliche deutsche Begriffe („Meldungen“, nicht „Signale“); die Website berichtet und berät nicht.
- Jede Aussage verlinkt auf die Originalquelle.
- Markenfarben der Anbieter verwenden; Vodafone-Rot ist Akzent, keine Fläche.
- Die wichtigste Zahl ist die größte Schrift ihres Bereichs.
- Abnahme heißt Screenshots (Desktop 1440 px und mobil 390 px), die tatsächlich angesehen wurden. Grüne Tests sind kein Nachweis, dass eine Seite gut aussieht oder stimmt.
- Autonom arbeiten, selbst verifizieren, Antonio nicht mit Rückfragen löchern.
- Alles bleibt kostenlos (GitHub Actions, Render Free).

## Weiterführende Dokumente

- `outputs/fortschritt-geraeteseite.md`: aktueller Arbeitsstand der Geräteseite.
- `TELCO_RADAR_QUELLEN.md`: verifizierte Quellenliste, erzeugt mit `scripts/build_quellen_doc.py`.
- `docs/archiv/`: abgeschlossene Aufträge, Strategien und das alte Handover.
