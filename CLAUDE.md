# Telco Radar — Handover für die nächste Claude-Session

Stand: 2026-07-16, Ende Session 1. Dieses Dokument enthält alles, was eine
neue Session braucht, um das Projekt zu verstehen, darauf zuzugreifen und
weiterzuarbeiten.

---

## 1. Was ist das & was ist das Ziel?

**Telco Radar** ist ein automatisches Competitive-Intelligence-System für
Antonios Kollegin bei **Vodafone**. Es beobachtet wöchentlich die Presse-
Newsrooms von **59 Netzbetreibern in 6 Regionen** (Europa, Nordamerika,
Lateinamerika, Afrika & Naher Osten, Asien, Ozeanien) plus **6 internationale
Telco-Fachpresse-Feeds**, erkennt **nur wirklich neue** Meldungen, lässt sie
von Claude-Agents bewerten („Warum ist das für Vodafone interessant?",
Dringlichkeit 1–5) und veröffentlicht einen deutschsprachigen Wochenbericht
als Website.

**Kernprinzip:** Die Intelligenz sitzt in der Delta-Schicht (Seen-Store),
nicht in den Agents. LLM-Calls sehen nur neue Items → günstig, keine
Wiederholungen. Was letzte Woche berichtet wurde, kommt nie wieder
(Topic-Memory für den Editor).

**Zielgruppe der Website:** Manager OHNE KI-/Technik-Hintergrund. Kein Jargon
(nicht „Signale", sondern „Meldungen"), alles erklärt, jede Aussage mit Link
zur Originalquelle.

## 2. Live-URLs & Konten

| Was | Wo |
|---|---|
| Live-Website | https://telco-radar.onrender.com (Render **Static Site** → CDN, schläft nie, kostenlos) |
| GitHub-Repo | https://github.com/Antonio20045/telco-radar (public, Account **Antonio20045**) |
| GitHub Actions | Repo → Actions → Workflow „Telco Radar Run" |
| Render-Service | dashboard.render.com → Static Site **telco-radar** (Service-ID `srv-d9cil1vaqgkc73f7ugd0`) |

Antonio ist in Chrome bei **GitHub (Antonio20045)** und **Render** eingeloggt.
Render ist zusätzlich mit einem anderen GitHub-Account (jonas986) verknüpft —
deshalb wurde die Static Site über „Public Git Repository" (URL) angelegt,
nicht über die GitHub-App.

## 3. Zugriff aus einer neuen Session (wichtig!)

Die Sandbox hat **kein** gespeichertes GitHub-Token — es lebt nur eine
Session. So bekommst du neuen Schreibzugriff (hat in Session 1 funktioniert):

1. **Device-Flow manuell per curl** (NICHT `gh auth login` im Hintergrund —
   die Sandbox killt Hintergrundprozesse zwischen Bash-Aufrufen!):
   ```bash
   # Schritt A: Code holen (client_id = offizielle GitHub CLI)
   curl -sS -X POST https://github.com/login/device/code \
     -H "Accept: application/json" \
     -d "client_id=178c6fc778ccc68e1d6a" -d "scope=repo workflow"
   # → liefert device_code + user_code
   ```
2. **Chrome-Extension:** github.com/login/device öffnen, user_code eingeben,
   autorisieren. (2FA/Passkey muss Antonio selbst bestätigen — kurz fragen.)
3. ```bash
   # Schritt B: Token abholen (device_code aus Schritt A)
   curl -sS -X POST https://github.com/login/oauth/access_token \
     -H "Accept: application/json" \
     -d "client_id=178c6fc778ccc68e1d6a" \
     -d "device_code=<DEVICE_CODE>" \
     -d "grant_type=urn:ietf:params:oauth:grant-type:device_code"
   ```
4. Nutzung: `GH_TOKEN=<token> gh ...` für API/Workflows; für git-Push:
   ```bash
   git -c credential.helper='!f() { echo username=x-access-token; echo password=<TOKEN>; }; f' push
   ```
   (`gh auth login --with-token` scheitert an fehlendem read:org-Scope — egal,
   GH_TOKEN-Env reicht für alles.)
5. **gh CLI installieren:** Release-Tarball `linux_arm64` (Sandbox ist
   aarch64!) von github.com/cli/cli nach `~/bin/gh`.

**Render:** Deploy wird über einen **Deploy Hook** getriggert (liegt als
GitHub-Secret `RENDER_DEPLOY_HOOK`; einsehbar in Render → telco-radar →
Settings → Deploy Hook). Manuell: `curl -X POST "<hook-url>"`. Für alles
andere (Settings, Logs) das Render-Dashboard per Chrome bedienen.

## 4. Architektur & Repo-Struktur

Pipeline (läuft in GitHub Actions, `python -m telco_radar.pipeline`):

```
1. COLLECT   RSS- & Newsroom-Collector, parallel, fehlertolerant
             (src/telco_radar/collect/: rss.py, newsroom.py, http.py)
2. DELTA     Seen-Store + Freshness-Filter → nur NEUE Items
             (src/telco_radar/dedupe.py; State: data/state/seen.jsonl)
3. ANALYZE   1 Analyst-Agent pro Region, Batches à 15 Items, 8k Tokens
             (src/telco_radar/analyze/agents.py; API direkt via httpx: llm.py)
4. EDIT      Editor-Agent: deutscher Wochenbericht (20k Tokens!) +
             Topic-Memory gegen Wiederholungen (analyze/editor.py)
5. PUBLISH   Markdown + JSON nach data/reports/, statische Site nach site/
             (report/html.py + templates/), Commit + Render-Hook
```

Wichtige Dateien:

| Pfad | Inhalt |
|---|---|
| `config/watchlist.yaml` | Regionen → Operator → Quellen. Operator OHNE sources = bot-geschützt, wird via Fachpresse-Tagging abgedeckt (Aliase!) |
| `config/news_sources.yaml` | Fachpresse-RSS (Mobile World Live, Light Reading, …) |
| `config/settings.yaml` | Sprache (de), Modell (`claude-sonnet-5`), Lookback (8 Tage), HTTP |
| `data/state/seen.jsonl` | Dedup-Gedächtnis (Hash normalisierter URLs) — git-versioniert |
| `data/state/reported_topics.jsonl` | Bereits berichtete Themen (Editor-Memory) |
| `data/reports/YYYY-MM-DD.{md,json}` | Bericht als Prosa (md) + strukturiert (json: stats, regions→highlights) |
| `site/` | Generierte Website — wird von Actions committed, Render published sie (Publish Dir `site`, Build Command nur `echo`) |
| `src/telco_radar/report/templates/` | base/report/archive/sources.html.j2 + style.css + app.js |
| `scripts/validate_sources.py` | Health-Check aller Quellen (OK/EMPTY/FAIL) |
| `.github/workflows/radar.yml` | Cron Di + Fr 08:30 UTC + manuell; committet data/+site/, curlt Render-Hook (mit 15s sleep!) |
| `tests/` | 15 pytest-Tests (Fixtures, kein Netz/LLM nötig) |

**Secrets im Repo** (Settings → Actions): `ANTHROPIC` (Antonios API-Key —
der Workflow akzeptiert `ANTHROPIC_API_KEY` ODER `ANTHROPIC`) und
`RENDER_DEPLOY_HOOK`.

## 5. Website (v3, „Bloomberg-Terminal-Stil")

Dark-Theme (Light-Toggle), Inter + IBM Plex Mono, Vodafone-Rot `#e60000`.
Aufbau der Berichtsseite: Headline-**Ticker** → Hero + KPI-Leiste →
aufklappbare Erklär-Box („Wie funktioniert dieser Bericht?") →
**01** Top-Prioritäten-Karten → **02** Wochenbericht (Prosa; Struktur: Für
Eilige / Executive Summary / Top-Signale / Regionen / Trends & Muster /
Handlungsempfehlungen) → **03** SVG-Charts (Region/Thema/Dringlichkeit) →
**04** Split-View-Explorer (links Liste, rechts Detail; Suche, Filter,
Sortierung; Daten als eingebettetes JSON `#explorer-data`). Dazu archive.html
und sources.html. Alles Vanilla JS (app.js), kein Framework, kein CDN-JS.

## 6. Bekannte Fallstricke (alle in Session 1 gelernt!)

- **State nie lokal committen:** Nach lokalen Testläufen `data/state/` +
  `data/reports/` NICHT einchecken, sonst findet der Actions-Lauf „0 neue
  Items". Baseline-Reset = die vier State-/Report-Dateien per `git rm`
  entfernen, pushen, Workflow triggern.
- **Anthropic 529 (overloaded):** kommt vor; llm.py hat 5 Retries mit bis zu
  45s Backoff, Analysten-Batches werden übersprungen statt zu crashen, der
  Editor fällt notfalls auf einen Digest zurück. Ein Lauf dauerte deshalb
  schon mal 24 min — normal sind 7–8 min.
- **Push→Hook-Race:** Render klont sofort; der Workflow wartet 15s zwischen
  git push und Hook-Curl. Beim manuellen Nachdeployen dran denken.
- **Newsrooms:** ~17 Quellen sind JS-gerendert (EMPTY) oder bot-geschützt
  (403). Der Fetcher (collect/http.py) probiert Browser-UA und Bot-UA. Harte
  Fälle stehen ohne `sources` in der Watchlist und laufen über
  Fachpresse-Tagging (Wortgrenzen-Matching, Ambiguous-Blocklist in
  collect/__init__.py: „spark", „tim", „globe" …).
- **GitHub Pages ist AUS** (war Free-Plan-Problem bei privat, dann auf Render
  umgestellt). Nicht wieder aktivieren.
- **Sandbox:** aarch64; pip braucht `--break-system-packages`; Bash-Calls max
  45s → lange Läufe via GitHub Actions, Polling mit `gh run list`.

## 7. Lokal arbeiten & testen

```bash
pip install -r requirements.txt --break-system-packages
export PYTHONPATH=src
pytest -q                                   # 15 Tests, offline
python scripts/validate_sources.py          # Quellen-Health (Netz nötig)
python -m telco_radar.pipeline --no-llm     # E2E ohne API-Key
# Site nur neu rendern (ohne Crawl): render_site() aus report/html.py nutzen
```

## 8. Antonios Anforderungen / Stil (unbedingt beachten)

- Der **Prosa-Wochenbericht ist das Herzstück**, nicht Karten-Grids. Detail
  auf Klick (Explorer), Bloomberg-Terminal-Ästhetik gewünscht und gelobt.
- **Laienverständlich**: keine unerklärten Begriffe, deutsche Labels,
  Erklär-Box. Jede Aussage mit **Quellen-Link** (Nachprüfbarkeit war explizite
  Anforderung).
- **Autonom arbeiten**, Ergebnisse selbst per Chrome-Extension auf der
  Live-Site verifizieren und iterieren; Antonio nicht mit Rückfragen löchern.
- Website darf **nie einschlafen** (deshalb Static Site, kein Web Service).
- Kostenlos bleiben (GitHub Actions + Render Free).

## 9. Offene Ideen / Roadmap

- E-Mail-/Teams-Versand des Briefings nach jedem Lauf
- Firecrawl/Crawl4AI als Fetcher für JS-Newsrooms (AT&T, Singtel, Telia, …)
- Semantisches Dedup (Embeddings), um dieselbe Story aus mehreren Quellen zu mergen
- Tarif-/Preisseiten-Diffing als dritte Signalebene
- Trend-Charts über mehrere Wochen (Daten liegen ja als JSON-Archiv vor)
- Feedback der Vodafone-Kollegin einarbeiten (steht noch aus)
- Migration auf Vodafone-Infra, falls gewünscht (Runner braucht nur Python + HTTPS)
