# Telco Radar

**Automatisiertes, weltweites Competitive-Intelligence-Briefing für die Telco-Branche.**

Telco Radar überwacht die Newsrooms von Mobilfunkanbietern auf allen Kontinenten plus die internationale Telco-Fachpresse, erkennt **nur wirklich neue** Meldungen, lässt sie von regionalen KI-Analysten bewerten und veröffentlicht wöchentlich ein Briefing mit Handlungsempfehlungen als statische Website (GitHub Pages).

## Architektur

```
 config/watchlist.yaml          config/news_sources.yaml
 (Telcos je Region)             (Telco-Fachpresse, RSS)
        │                              │
        ▼                              ▼
 ┌─────────────────────────────────────────────┐
 │  1. COLLECT   RSS- & Newsroom-Collector      │  parallel, fehlertolerant
 └─────────────────────┬───────────────────────┘
                       ▼
 ┌─────────────────────────────────────────────┐
 │  2. DELTA     Seen-Store (data/state/)       │  nur NEUE Items passieren
 │               + Freshness-Filter             │  (URL-Hash, git-versioniert)
 └─────────────────────┬───────────────────────┘
                       ▼
 ┌─────────────────────────────────────────────┐
 │  3. ANALYZE   1 Analyst-Agent pro Region     │  Relevanz 1–5, Kategorie,
 │               (Claude, nur über die Deltas)  │  "Warum relevant für uns"
 └─────────────────────┬───────────────────────┘
                       ▼
 ┌─────────────────────────────────────────────┐
 │  4. EDIT      Editor-Agent + Topic-Memory    │  synthetisiert Briefing,
 │               (reported_topics.jsonl)        │  wiederholt nie Berichtetes
 └─────────────────────┬───────────────────────┘
                       ▼
 ┌─────────────────────────────────────────────┐
 │  5. PUBLISH   Markdown-Archiv + HTML-Site    │  Render Static Site (CDN,
 └─────────────────────────────────────────────┘  schläft nie, kostenlos)
```

**Designprinzip:** Die Intelligenz sitzt in der Delta-Schicht, nicht in den Agents. LLM-Aufrufe sehen ausschließlich neue Items — das macht das System günstig, schnell und verhindert Wiederholungen zuverlässiger als jede Prompt-Anweisung.

## Quickstart (lokal)

```bash
pip install -r requirements.txt
export PYTHONPATH=src

# Tests
pytest -q

# Quellen prüfen (welche Newsrooms/Feeds liefern?)
python scripts/validate_sources.py

# Kompletter Lauf ohne KI-Analyse (Roh-Digest)
python -m telco_radar.pipeline --no-llm

# Kompletter Lauf mit KI-Analyse
export ANTHROPIC_API_KEY=sk-ant-...
python -m telco_radar.pipeline

# Ergebnis ansehen
open site/index.html
```

Der **erste Lauf** ist ein Baseline-Lauf: Alle Quellen werden eingelesen und als "gesehen" markiert. Ab dem zweiten Lauf enthalten Briefings nur noch Neues.

## Automatischer Betrieb (GitHub Actions + Render)

Der Workflow [`radar.yml`](.github/workflows/radar.yml) läuft **jeden Montag 05:00 UTC** (und manuell über *Actions → Telco Radar Run → Run workflow*):

1. Pipeline ausführen
2. State (`data/`) und generierte Website (`site/`) zurück ins Repo committen
3. Render-Deploy anstoßen (Deploy Hook)

Die Website läuft als **Render Static Site** (Publish Directory `site`, kein Build-Command nötig). Statische Sites liegen auf Renders CDN: **kein Spin-down, keine Kaltstarts, kostenlos.**

### Einmalige Einrichtung

1. **Secret setzen:** *Settings → Secrets and variables → Actions* → `ANTHROPIC_API_KEY` = dein Anthropic-API-Key. Ohne Key läuft alles trotzdem — es erscheint dann ein Roh-Digest statt des analysierten Briefings.
2. **Render:** Neue *Static Site* vom Repo (Branch `main`, Publish Directory `site`). Den *Deploy Hook* aus den Render-Settings als GitHub-Secret `RENDER_DEPLOY_HOOK` hinterlegen, damit jeder Radar-Lauf sofort deployt.

## Konfiguration

| Datei | Zweck |
|---|---|
| `config/watchlist.yaml` | Regionen → Operator → Quellen (Newsroom-URLs, RSS). Hier neue Telcos eintragen. |
| `config/news_sources.yaml` | Telco-Fachpresse (RSS). Zweite Signalebene; Items werden per Headline automatisch Operatoren/Regionen zugeordnet. |
| `config/settings.yaml` | Sprache, Modell, Lookback-Fenster, Limits. |

**Quelle hinzufügen:** URL in `watchlist.yaml` eintragen, dann `python scripts/validate_sources.py` laufen lassen. `EMPTY` bedeutet meist eine JavaScript-gerenderte Seite — dann besser den RSS-Feed des Operators suchen oder einen `item_selector` (CSS) angeben.

## Datenhaltung

| Pfad | Inhalt |
|---|---|
| `data/state/seen.jsonl` | Alle jemals gesehenen Item-IDs (Hash der normalisierten URL). **Das Dedup-Gedächtnis.** |
| `data/state/reported_topics.jsonl` | Bereits berichtete Themen — der Editor bekommt sie als "nicht wiederholen"-Kontext. |
| `data/reports/YYYY-MM-DD.md` | Archiv aller Briefings (Markdown). |
| `site/` | Generierte Website (nicht eingecheckt; wird von Actions deployt). |

Alles ist git-versioniert — jeder Lauf ist nachvollziehbar und reproduzierbar.

## Roadmap

- [ ] JS-gerenderte Newsrooms: optionale Integration von [Firecrawl](https://www.firecrawl.dev/) oder [Crawl4AI](https://github.com/unclecode/crawl4ai) als Fetcher
- [ ] Semantisches Dedup (Embeddings) zusätzlich zum URL-Hash, um dieselbe Story aus mehreren Quellen zusammenzuführen
- [ ] Tarif-/Preisseiten-Diffing als dritte Signalebene
- [ ] E-Mail-/Teams-Versand des Briefings
- [ ] Übernahme auf interne Infrastruktur (der Runner braucht nur Python + ausgehendes HTTPS)

## Kosten

GitHub Actions (public/private Repo, wöchentlicher Lauf) und GitHub Pages sind kostenlos. Einzige laufende Kosten: die Anthropic-API-Calls — bei wöchentlichem Lauf typischerweise wenige Cent bis Cent-Bruchteile pro Briefing, abhängig vom Nachrichtenaufkommen.
