# Telco Radar — Übergabe für die nächste Session

Stand: 25. Juli 2026. Dieses Dokument ist eine praktische Projekt- und
Betriebsübergabe, kein Prompt. Es beschreibt Codezugriff, Architektur,
Quellenpflege, Tests, Deployment und bekannte Stolpersteine.

## 1. Zweck

Telco Radar ist ein automatisches Competitive-Intelligence-Briefing für die
Telco-Branche. Es beobachtet offizielle Presse- und Newsroom-Quellen von
Netzbetreibern in sechs Weltregionen sowie internationale Telco-Fachpresse.
Neue Meldungen werden gesammelt, dedupliziert, nach Region und Thema bewertet
und als deutschsprachiger Wochenbericht auf einer statischen Website
veröffentlicht.

Die Website richtet sich an Vodafone-Manager ohne technischen Hintergrund.
Texte sollen verständlich sein und wesentliche Aussagen mit Links zur
Originalquelle belegen. Die Differenzierungsseite sammelt konkrete Angebote,
Partnerschaften, Programme und Projekte jenseits von Netz, Tarif und Preis.

## 2. Repository und Seiten

- GitHub: https://github.com/Antonio20045/telco-radar
- Live: https://telco-radar.onrender.com
- Lokaler Klon: /Users/antonio/Documents/Codex/2026-07-22/v/work/telco-radar
- Vor Änderungen immer pwd, git status und git remote -v prüfen.
- Keine Chrome-Extension erforderlich; lokal mit Git, GitHub API, curl und
  den vorhandenen Skripten arbeiten.

Wichtige Live-Seiten:

- /bericht.html — aktueller Wochenbericht
- /protokoll.html — Lauf- und Qualitätsprotokoll
- /wettbewerber.html — Wettbewerberansichten
- /differenzierung.html — Differenzierungsradar
- /sources.html — Quellenübersicht
- /archive.html — Historie

## 3. Wichtige Dateien

| Datei oder Ordner | Zweck |
|---|---|
| config/watchlist.yaml | Betreiber, Regionen und offizielle Primärquellen |
| config/news_sources.yaml | internationale Telco-Fachpresse und RSS-Feeds |
| config/watchlist_extra.yaml | zusätzliche bzw. generierte Quellen |
| config/settings.yaml | Sprache, Modelle, Limits, HTTP und Pipeline-Verhalten |
| src/telco_radar/collect/ | RSS-, Newsroom-, JS- und JSON-Collector |
| src/telco_radar/analyze/ | Analysten, Editor, Wettbewerber, Differenzierung |
| src/telco_radar/pipeline.py | Ablauf von Collection bis Veröffentlichung |
| src/telco_radar/report/ | JSON/Markdown-Ausgabe und HTML-Rendering |
| scripts/validate_sources.py | Health-Check der konfigurierten Quellen |
| data/state/seen.tsv | Dedup-Gedächtnis bereits gesehener URLs (kompakt, ~22 Byte je Zeile) |
| data/state/quellen_register.json | Herkunft, Abnahmedatum, letzter Erfolg und Quarantäne je Quelle |
| data/state/reported_topics.jsonl | Editor-Gedächtnis bereits berichteter Themen |
| data/state/differentiation_db.json | Differenzierungszustand |
| data/state/differentiation.jsonl | Differenzierungs-Items und Laufhistorie |
| data/reports/ | archivierte Markdown- und JSON-Berichte |
| data/reports/differenzierung/ | archivierte Differenzierungsberichte |
| site/ | generierte statische Website; nicht per Hand bearbeiten |
| .github/workflows/radar.yml | Actions-Lauf, Commit und Render-Deploy |
| TELCO_RADAR_QUELLEN.md | ausführliche verifizierte Quellenliste |
| outputs/quellen-audit-2026-07-22.md | Quellen-Audit und Empfehlungen |
| config/promo_sources.yaml | Quellen fuer "Promo Uebersicht" (Deutschland) |
| src/telco_radar/promo_config.py | Loader fuer promo_sources.yaml |
| src/telco_radar/collect/promo_snapshot.py | Snapshot-Diff-Collector fuer Aktionsseiten |
| src/telco_radar/analyze/promo_store.py | SnapshotStore + PromoDB (State der Promo-Uebersicht) |
| src/telco_radar/analyze/promo_analyst.py | LLM-Extraktion von Angeboten aus Snapshots |
| src/telco_radar/analyze/promo_editor.py | Redaktion des woechentlichen Promo-Berichts |
| src/telco_radar/promo_pipeline.py | Pipeline-Stufe der Promo-Uebersicht |
| data/state/promo_snapshots.json | letzter Content-Hash je Anbieter (Diff-Erkennung) |
| data/state/promo_db.json | kuratierte, versionierte Promo-Datenbank |
| data/reports/promo/ | archivierte Promo-Wochenberichte |
| scripts/validate_promo_sources.py | Health-Check der Promo-Quellen |

## 4. Pipeline

    Quellen
      -> Collector: RSS, statischer Newsroom, JS-Newsroom, JSON-API
      -> Freshness- und Seen-Filter
      -> regionale Analysten, Wettbewerber und Kategorie-Sweep
      -> deutscher Editor-Bericht mit Topic-Memory
      -> Markdown, JSON und statische HTML-Seite
      -> Commit nach GitHub
      -> Render Deploy Hook

Die zentrale Delta-Logik sitzt im Seen-Store. Der LLM bekommt nur neue Items.
Die normalisierte URL erzeugt die Item-ID. Stabile Artikel-URLs sind deshalb
wichtiger als eine möglichst große Zahl an Quellen.

Der Editor erhält zusätzlich den Topic-Memory, damit bereits berichtete Themen
nicht jede Woche neu formuliert werden. Der Differenzierungszweig nutzt eigene
Curator-/Editor-Logik und soll konkrete Programme, Partnerschaften,
Produktinitiativen, Investitionen und Geschäftsmodelle finden.

## 5. Quellen und Collector

watchlist.yaml enthält Betreiber nach Region. Bevorzugt werden offizielle
RSS-/Atom-Feeds, JSON-APIs, statische Newsrooms und JS-Newsrooms über
Playwright. news_sources.yaml ist eine getrennte zweite Ebene mit
internationaler Telco-Fachpresse. Die Zuordnung zu Betreibern erfolgt über
Aliase und Wortgrenzen; mehrdeutige Begriffe wie spark, tim, globe oder orange
werden über Blocklisten vorsichtig behandelt.

Collector:

- rss.py: Feed lesen und Titel, URL, Datum und Text normalisieren.
- json_api.py: strukturierte offizielle APIs.
- newsroom.py: statische HTML-Newsrooms.
- newsroom_js.py: JS-gerenderte Newsrooms mit Playwright.
- http.py: HTTP-Abruf, User-Agent, Status und Timeouts.
- collect/__init__.py: Normalisierung, Tagging und Fehlerlogik.

Ein einzelner Timeout ist kein Grund, eine Quelle zu entfernen. Unterscheiden:

1. Temporär: Timeout, 5xx oder kurzzeitige leere Antwort; mehrfach prüfen.
2. JS-Problem: HTTP 200, aber keine Artikel im Roh-HTML; JS-Collector oder
   Feed suchen.
3. Bot-Schutz: 403, 307-Edge-Challenge oder Radware-Wall; als Referenz
   dokumentieren, nicht als funktionierende automatische Quelle ausgeben.
4. Inhaltlich schlecht: nur Navigation, Karriere, Investor-Archiv oder
   irrelevante Inhalte; enger selektieren, reparieren oder entfernen.

Die ausführliche Quellenliste steht in TELCO_RADAR_QUELLEN.md, das Audit in
outputs/quellen-audit-2026-07-22.md.

## 6. LLM-Konfiguration und der jüngste Fehler

Aktuelle Werte in config/settings.yaml:

- OpenAI-kompatibler Base-Endpunkt:
  https://integrate.api.nvidia.com/v1
- Analyst: deepseek-ai/deepseek-v4-flash
- Editor: deepseek-ai/deepseek-v4-pro
- max_items_per_region: 15
- llm_max_workers: 2
- publish_requires_editorial_briefing: false

Der API-Key steht nur als GitHub-Secret LLM_API_KEY mit Anthropic-Fallback
oder als lokale Umgebungsvariable. Niemals Schlüssel in diese Datei, Git,
Logs oder Chat-Ausgaben schreiben.

Die letzten Fehlversuche waren kein ungültiger Key. Der Provider antwortete
mit HTTP 503 ResourceExhausted und der Meldung, dass das lokale Worker-Limit
erreicht wurde. Danach liefen Editor-Anfragen in Read-Timeouts. Die Secret-
Presence-Prüfung war erfolgreich. Die alte Pipeline veröffentlichte bei
Editor-Fehlern gar nichts, deshalb blieb die Live-Seite auf dem letzten
erfolgreichen Bericht.

Commit f5bc432 reduziert parallele Last, Itemzahl und Retry-Zahl. Zusätzlich
veröffentlicht die Pipeline bei vorübergehender Editorial-Störung einen klar
gekennzeichneten, quellenverlinkten Fallback-Digest.

## 7. Actions, Push und Render

Workflow: .github/workflows/radar.yml

- Zeitplan: Dienstag und Freitag, 08:30 UTC.
- Manuell über GitHub Actions, Workflow Telco Radar Run, Run workflow.
- lookback_days ist standardmäßig 8.
- concurrency.group ist radar; laufende Läufe werden nicht automatisch
  abgebrochen.
- Job-Timeout: 35 Minuten.
- Nach Erfolg werden data/ und site/ committed und gepusht.
- Danach wird der Render Deploy Hook ausgelöst. Der Hook ist ein Secret.

Stand beim Erstellen dieser Datei:

- letzter Code-Commit: f5bc432, pipeline: survive provider resource exhaustion
- CI für diesen Commit: erfolgreich
- Deploy-Site-Workflow für diesen Commit: erfolgreich
- Radar-Lauf #33, ID 30152159637: in_progress, Pipeline-Schritt aktiv
- Solange #33 noch läuft, kann der Live-Bericht noch den 21. Juli anzeigen.
  Erst Bot-Commit plus Render-Deploy bestätigen den neuen Live-Stand.

### GitHub-Zugriff

Der aktuelle Mac-Setup liefert Credentials über den Git-Credential-Helper. Für
eine GitHub-API-Abfrage können sie nur in Shell-Variablen verwendet werden:

    cd /Users/antonio/Documents/Codex/2026-07-22/v/work/telco-radar
    cred="$(printf 'protocol=https\nhost=github.com\npath=Antonio20045/telco-radar.git\n\n' | git credential fill)"
    gh_user="$(printf '%s\n' "$cred" | sed -n 's/^username=//p')"
    gh_pass="$(printf '%s\n' "$cred" | sed -n 's/^password=//p')"
    curl -sS -u "$gh_user:$gh_pass" \
      -H 'Accept: application/vnd.github+json' \
      -H 'X-GitHub-Api-Version: 2022-11-28' \
      'https://api.github.com/repos/Antonio20045/telco-radar/actions/runs?per_page=10'
    unset cred gh_user gh_pass

Passwort- und Tokenwerte niemals ausgeben, mit set -x laufen lassen oder in
eine Datei schreiben. Falls der Helper leer ist, muss Antonio die GitHub-
Authentifizierung erneuern.

### Code ändern und pushen

    cd /Users/antonio/Documents/Codex/2026-07-22/v/work/telco-radar
    git status --short --branch
    git pull --rebase origin main
    # Dateien bearbeiten
    git diff --check
    PYTHONPATH=src pytest -q
    git add gezielte-dateien
    git commit -m "kurze beschreibung"
    git push origin main

Nach dem Push zuerst CI und Deploy-Site prüfen, dann den Radar-Lauf manuell
starten oder den Zeitplan abwarten. Bei gleichzeitigem Bot-Commit nicht
überschreiben: git pull --rebase origin main und den Push wiederholen.

## 8. Lokal testen

    cd /Users/antonio/Documents/Codex/2026-07-22/v/work/telco-radar
    PYTHONPATH=src pytest -q
    python scripts/validate_sources.py
    PYTHONPATH=src python -m telco_radar.pipeline --no-llm --root .

Aktuell bestehen 45 Tests. validate_sources.py braucht Netzwerk und kann bei
JS-/Bot-Quellen erwartbar EMPTY oder FAIL melden. HTTP-Status, Redirects,
Antwortlänge und Inhalt gemeinsam bewerten.

Ein vollständiger lokaler Pipeline-Lauf verändert data/state, data/reports
und site. Diese Artefakte nicht aus einem lokalen Testlauf committen. Für
Produktionsdaten ist GitHub Actions zuständig. Vor jedem Push git status prüfen.

## 9. Site und Differenzierung prüfen

Nach einem erfolgreichen Radar-Lauf:

1. git pull --rebase origin main ausführen.
2. Neuen data/reports/YYYY-MM-DD.md- und JSON-Satz prüfen.
3. seen.tsv, reported_topics.jsonl und die Differenzierungsdateien auf
   plausible Zunahmen prüfen.
4. In site/bericht.html und site/differenzierung.html Titel, Datum,
   Original-URLs und Quellenlinks stichprobenartig prüfen.
5. Live mit curl -L -sS https://telco-radar.onrender.com/bericht.html prüfen.
6. Den Live-Datumsstand anhand des ausgelieferten HTML-Inhalts bestätigen,
   nicht nur anhand von GitHub- oder Render-Status.

Keine HTML-Dateien in site per Hand reparieren. Änderungen gehören in
src/telco_radar/report, die Templates oder die Konfiguration.

Die Differenzierungslogik liegt in:

- src/telco_radar/report/differentiation.py
- src/telco_radar/analyze/diff_curator.py
- src/telco_radar/analyze/differentiation_editor.py
- src/telco_radar/analyze/category_sweep.py

Ein gutes Item beschreibt eine konkrete Initiative, etwa ein Programm, eine
Partnerschaft, eine Plattform, ein B2B-Angebot, eine Community-/Nachhaltigkeits-
Initiative oder ein neues Geschäftsmodell. Reine Netzabdeckung, Tarifpreise
und allgemeine Produktwerbung gehören nicht in diesen Zweig. Jede Karte
braucht einen echten Quelllink und darf keine erfundene Zusammenfassung
enthalten.

## 10. Stolpersteine

- seen.tsv ist das Dedup-Gedächtnis. Nicht löschen oder mit lokalen Testdaten
  überschreiben, sonst kann der nächste Lauf fälschlich null neue Meldungen
  melden.
- HTTP 200 kann trotzdem nur eine JS-Hülle bedeuten.
- 403/307-Bot-Schutz ist ein technisches Problem, kein Beweis für schlechte
  Inhalte. Als Referenz behalten, aber nicht als funktionierende Extraktion
  ausgeben.
- Archiv-, Kategorie- und Navigationsseiten sind keine Artikel. Selektoren
  müssen Titel, Artikel-URL, Datum und Text extrahieren.
- Fachpresse-Tagging arbeitet mit Aliasen und Wortgrenzen. Kurze mehrdeutige
  Namen nicht ohne Blockliste ergänzen.
- Keine konkurrierenden Actions-Läufe starten oder einen plausibel laufenden
  Lauf abbrechen.
- Render ist eine Static Site. GitHub Pages nicht wieder aktivieren.
- HTTP 401/403 bedeutet Authentifizierung/Autorisierung; 429/503/529 bedeutet
  meist Provider-Limit oder Überlastung. Timeout ist nicht automatisch ein
  falscher Schlüssel.

## 11. Nächste Schritte

1. Lauf #33 abschließen lassen und Bot-Commit, Render-Hook sowie Live-HTML
   prüfen.
2. Falls #33 fehlschlägt, den Actions-Pipeline-Log über das Artifact
   telco-radar-pipeline-log-<run_id> prüfen; nicht raten.
3. Quellen-Health-Check erneut ausführen und dauerhafte Fehler von temporären,
   JS- und Bot-Problemen trennen.
4. seen.tsv und aktuelle Reports gegen Links und Zusammenfassungen in site
   prüfen.
5. Erst danach weitere Quellen oder LLM-Parameter ändern.

## 12. Promo Übersicht (Deutschland, neuer zweiter Anwendungsfall)

Zweiter Anwendungsfall neben Marktrecherche (eigener Tab in der Kopfzeile,
eigene Subnav unter /promo/). Beobachtet Tarif-, Rabatt- und Kampagnen-
aktionen aller Telcos in Deutschland (Netzbetreiber + Discount-/Zweitmarken).
Ausfuehrliches Konzeptdokument (Premortem, Anforderungen, Quellenliste) liegt
im verknuepften Claude-Projekt unter `claude/promo-uebersicht-konzept.md`.

Warum ein eigener Zweig statt Wiederverwendung der bestehenden Presse-
Collector: Aktionsseiten sind Live-Snapshots ohne Historie (anders als
Presse-RSS, wo jeder Artikel ein diskretes, datiertes Signal ist). Deshalb:

- **Quellen:** config/promo_sources.yaml (hand-gepflegt, NICHT von
  scripts/build_sources.py generiert - andere Quellenart als watchlist.yaml).
  Health-Check: `python scripts/validate_promo_sources.py`.
- **Collector:** collect/promo_snapshot.py holt jede Aktionsseite (statisch
  oder per Playwright, je nach `kind` in der Config), extrahiert den
  sichtbaren Text und hasht ihn.
- **State:** analyze/promo_store.py - SnapshotStore (data/state/
  promo_snapshots.json, nur Hash je Anbieter fuer die Aenderungserkennung)
  und PromoDB (data/state/promo_db.json, kuratierte, versionierte Liste mit
  first_seen/last_verified/status - alte Eintraege werden bei Nicht-
  Bestaetigung als "evtl. ausgelaufen" markiert, NIE stillschweigend
  geloescht).
- **LLM-Schicht:** analyze/promo_analyst.py extrahiert konkrete Angebote NUR
  aus Snapshots, die sich seit dem letzten Lauf geaendert haben - erfindet
  nie einen Preis oder ein Enddatum. analyze/promo_editor.py schreibt daraus
  den Wochenbericht (validierte Markdown-Struktur, Quellenlink-Pflicht, keine
  Vodafone-Handlungsempfehlung), mit regelbasiertem Fallback ohne LLM.
- **Pipeline:** promo_pipeline.py wird aus pipeline.py aufgerufen (per
  `promo_enabled: true` in settings.yaml abschaltbar), in try/except - ein
  Fehler bricht den Hauptlauf nie ab. Seitenabruf laeuft nebenlaeufig
  (ThreadPoolExecutor, wie collect_all()).
- **Site:** report/promo.py (Anzeige-Vorbereitung) + Templates
  promo_index.html.j2/promo_quellen.html.j2, gerendert nach site/promo/. Die
  Kopfzeile (base.html.j2) unterscheidet jetzt per `usecase`-Variable
  zwischen Marktrecherche und Promo Uebersicht.
- **Vodafone selbst** ist in promo_sources.yaml mit `internal_reference:
  true` markiert - erscheint separat, zaehlt nicht als Wettbewerber.
- **Bekannte Grenzen (Stand Einfuehrung):** die meisten Marken-URLs sind
  recherchiert, aber NICHT einzeln per validate_promo_sources.py verifiziert;
  ein paar Discounter (mobilcom-debitel, PremiumSIM, simplytel) haben keine
  saubere feste Aktionsseite, sondern Tarifkataloge - beobachten, ob die
  Extraktion dort brauchbar bleibt. Deutsche Glasfaser ist bewusst als
  `kind: skip` markiert (keine bundesweite Aktionsseite, nur Ortsseiten).
- **Wichtig fuer Tests:** tests/test_pipeline.py's `project`-Fixture setzt
  `promo_enabled: false`, weil sie den ganzen config/-Ordner kopiert (inkl.
  promo_sources.yaml) und die "js"-Quellen dort echtes Playwright/Netzwerk
  brauchen, das die Fixture (nur httpx.get gemockt) nicht abdeckt. Beim
  Hinzufuegen weiterer Playwright-basierter Zweige immer pruefen, ob ein
  offline-Test versehentlich echtes Netzwerk anstoesst.
