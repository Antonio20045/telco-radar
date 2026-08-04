# Telco Radar — Handover für die nächste Claude-Session

Stand: 2026-08-04, Ende Session 5 (Skalierung). Dieses Dokument enthält
alles, was eine neue Session braucht, um das Projekt zu verstehen, darauf
zuzugreifen und weiterzuarbeiten.

---

## 1. Was ist das & was ist das Ziel?

**Telco Radar** ist ein automatisches Competitive-Intelligence-System für
Antonios Kollegin bei **Vodafone**. Es beobachtet wöchentlich **drei
Signalebenen**, erkennt **nur wirklich neue** Meldungen, lässt sie von
Agents bewerten („Warum ist das für Vodafone interessant?", Dringlichkeit
1–5) und veröffentlicht einen deutschsprachigen Wochenbericht als Website:

1. **90 Netzbetreiber in 6 Regionen** (Europa, Nordamerika, Lateinamerika,
   Afrika & Naher Osten, Asien, Ozeanien) über **104 crawlbare Quellen** —
   achtzehn Betreiber haben mehr als einen eigenen Kanal (Presse-Newsroom
   **plus** Investor Relations, Technik-Blog oder Landesgesellschaft).
2. **70 Telco-Fachpresse-Feeds** (`config/news_sources.yaml`) aus 20 Ländern
   und 16 Sprachen. Seit Session 5 der größte Block — die Trefferquote je
   Quelle sagt, dass hier der Ertrag liegt (siehe Abschnitt 9).
3. **49 Themenquellen in 8 Themenfeldern** (`config/tech_sources.yaml`):
   KI-Anbieter, Geräte, Chips & Modems, Netzausrüster, Satellit & NTN,
   Regulierung & Verbände, Türme/Glasfaser/Rechenzentren sowie
   eSIM-/MVNO-/Kommunikationsplattformen. Das sind **keine Wettbewerber**,
   sondern die Unternehmen und Behörden, die den Rahmen setzen — eigener
   Analyst mit eigenem Prompt, eigener Abschnitt im Bericht.

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
1. COLLECT   Quellen nach HOST gruppiert; Gruppen parallel, innerhalb einer
             Gruppe nacheinander mit Mindestabstand → viel Parallelität ohne
             429/403. Stillgelegte Quellen (Quarantäne) werden übersprungen.
             (src/telco_radar/collect/: __init__.py::sammelplan, rss.py,
             newsroom.py, http.py)
2. DELTA     Seen-Store + Freshness-Filter → nur NEUE Items
             (src/telco_radar/dedupe.py; State: data/state/seen.tsv,
             ~22 Byte je Eintrag, datierte Einträge verfallen nach 18 Monaten)
3. ANALYZE   1 Analyst-Agent pro Region UND pro Themenfeld, Batches à 15
             Items (parallel, analyst_batch_workers), 8k Tokens.
             Themenfelder bekommen TECH_ANALYST_SYSTEM statt ANALYST_SYSTEM -
             ein Chiphersteller ist kein Wettbewerber.
             (src/telco_radar/analyze/agents.py; API direkt via httpx: llm.py)
4. EDIT      ZWEISTUFIG (seit dem Skalierungs-Auftrag):
             a) Bereichsredakteure - ein Aufruf je Region und je Themenfeld,
                parallel, auf dem Analysten-Modell. Liefern Abschnitt,
                Kurzfassung und ihre stärksten Meldungen in vier Blöcken
                mit Trennmarken (kein JSON: Markdown mit Zeilenumbrüchen
                in einem JSON-String bricht regelmäßig).
             b) Chefredaktion - sieht NUR Kurzfassungen und Top-Meldungen,
                schreibt Auf einen Blick / Das Wichtigste / Die wichtigsten
                Signale / Muster der Woche. Die Bereichsabschnitte werden
                darunter montiert, nicht neu geschrieben.
             Damit hängt der Chef-Prompt an der Zahl der BEREICHE, nicht an
             der Zahl der Meldungen. (analyze/editor.py)
5. PUBLISH   Markdown + JSON nach data/reports/, statische Site nach site/
             (report/html.py + templates/), Commit + Render-Hook
```

Wichtige Dateien:

| Pfad | Inhalt |
|---|---|
| `config/watchlist.yaml` | Regionen → Operator → Quellen. Operator OHNE sources = bot-geschützt, wird via Fachpresse-Tagging abgedeckt (Aliase!) |
| `config/news_sources.yaml` | Fachpresse-RSS (Mobile World Live, Light Reading, …) |
| `config/tech_sources.yaml` | **Themenfelder** (dritte Ebene), acht Stück: KI, Geräte, Chips, Netzausrüster, Satellit, Regulierung, Türme/Glasfaser/Rechenzentren, Plattformen. Themen-Tag statt Region; Schlüssel tragen das Präfix `thema:` |
| `config/watchlist_extra.yaml` | Neue Betreiber aus dem Ausbau. Wird nach Regionsschlüssel mit der Watchlist verschmolzen, damit die gepflegte Hauptdatei lesbar bleibt |
| `config/settings.yaml` | Sprache (de), Modell (`claude-sonnet-5`), Lookback (8 Tage), HTTP |
| `data/state/seen.tsv` | Dedup-Gedächtnis (Hash normalisierter URLs + Tagesnummer, ~22 Byte je Zeile) — git-versioniert. Datierte Einträge verfallen nach `seen_store_months` (18); undatierte NIE, weil der Frischefilter sie nicht abfangen kann |
| `data/state/quellen_register.json` | Je Quelle Herkunft, Abnahmedatum, erster Lauf, letzter Erfolg, Bilanz und Quarantänestand. Wird von der Pipeline fortgeschrieben |
| `scripts/trefferquote.py` | **Die Steuergröße des Ausbaus.** Wertet das Berichtsarchiv aus: je Quelle bewertete Meldungen, Relevanz ≥3/≥4, wie viele im Wochenbericht landen, wie oft sie leer/fehlerhaft war |
| `scripts/finde_quellen.py` | Mechanische Breitensuche im Massenbetrieb: `--aus-watchlist` macht jeden Betreiber zum Ziel, `--muster` überträgt die IR-/Plattform-Muster, die im Bestand nachweislich funktionieren |
| `scripts/uebernehme_quellen.py` | Trägt NUR bestandene Kandidaten ein und sortiert sie selbst in Watchlist / news_sources / tech_sources / watchlist_extra. Setzt bei Zahlenabweichung alles aus dem Backup zurück |
| `scripts/mess_sammelphase.py` | Sammelphase messen (Wanduhr, Sekunden je Quelle, langsamste Hosts) — für vorher/nachher beim Drehen an der Parallelität |
| `scripts/kostenrechnung.py` | Kosten je Lauf und Monat, für 130 bis 1000 Quellen, mit und ohne Pekinger Stoßzeit |
| `scripts/migriere_seen_store.py` | Einmalige Überführung des alten JSONL ins kompakte Format |
| `data/state/reported_topics.jsonl` | Bereits berichtete Themen (Editor-Memory) |
| `data/reports/YYYY-MM-DD.{md,json}` | Bericht als Prosa (md) + strukturiert (json: stats, regions→highlights) |
| `site/` | Generierte Website — wird von Actions committed, Render published sie (Publish Dir `site`, Build Command nur `echo`) |
| `src/telco_radar/report/templates/` | base/report/archive/sources.html.j2 + style.css + app.js |
| `scripts/validate_sources.py` | Health-Check aller Quellen: Status, Item-Zahl, wie viele datiert, **neuestes Datum**, **wie viele im Frischefenster** + Liste „liefert Inhalte, aber nichts Frisches" |
| `scripts/build_quellen_doc.py` | Erzeugt `TELCO_RADAR_QUELLEN.md` aus der Watchlist; mit `--validate` mit echten Abrufzahlen |
| `scripts/pruefe_quellenvorschlag.py` | **Abnahme-Check für neue Quellen.** Schickt jeden Vorschlag durch `collect_source` und prüft neun Kriterien maschinell. Ohne PASS hier kommt keine Quelle in die Config |
| `scripts/finde_quellen.py` | Mechanische Breitensuche: `rel=alternate` der Newsroom-Seiten + die Kandidatenpfade, die in dieser Branche wirklich vorkommen |
| `.github/workflows/radar.yml` | Cron Di + Fr 08:30 UTC + manuell; committet data/+site/, curlt Render-Hook (mit 15s sleep!) |
| `tests/` | pytest-Suite (Fixtures, kein Netz/LLM nötig) |

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
- **Die Sammelphase hängt an der langsamsten EINZELNEN Quelle**, nicht mehr an
  der Zahl der Quellen. In Lauf #68 lag der Median bei 3,2 s je Quelle und die
  Summe aller Abrufzeiten bei 1 212 s — aber KT allein brauchte 299,8 s, bis
  seine Verbindungsversuche aufgaben, und bestimmte damit die 303-s-Phase im
  Alleingang. `collect/http.py` probiert zwei User-Agents mit je drei
  Versuchen und zwei Backoff-Pausen; im schlimmsten Fall sind das sechs
  Timeouts plus 26 s Warten. **Mehr Worker helfen dagegen nicht** — ein
  Gesamtbudget je Quelle wäre der nächste Hebel.
- **Ein Modell, das mehrzeiliges Markdown in JSON schreiben soll, bricht.**
  Die Bereichsredakteure antworten deshalb in vier Blöcken mit Trennmarken.
  Wer das zurückdreht, riskiert nicht einen ausgefallenen Abschnitt, sondern
  alle: sie teilen sich denselben Prompt.
- **Der Abnahme-Check prüft Kandidaten auch GEGENEINANDER** (Kriterium 7c).
  Ohne das bestehen zwei Pfade derselben Seite beide — bei den 101
  mechanisch gefundenen Kandidaten waren das 4 von 15 Treffern.
- **`uebernehme_quellen.py` schreibt YAML im Fluss-Stil**, und dort beendet
  ein Fragezeichen in einer URL das Mapping. Zeichenketten deshalb immer in
  Anführungszeichen. Das Sicherheitsnetz (Konfiguration neu laden, zählen,
  sonst Backup zurückspielen) hat genau diesen Fehler zweimal abgefangen —
  es ist kein Zierrat.
- **Die Wertprüfung bleibt Handarbeit, und sie ist die halbe Arbeit.** In
  Welle 1 fielen 72 von 141 formal bestandenen Quellen: Gadget-Blogs,
  Enterprise-IT- und CIO-Presse, drei Geschwisterseiten mit identischem
  Inhalt, ein Feed mit fremdsprachigen Fremdinhalten. Die Ablehnungsgründe
  stehen in `outputs/skalierung-2026-08-04.md`.
- **Anthropic 529 (overloaded):** kommt vor; llm.py hat 5 Retries mit bis zu
  45s Backoff, Analysten-Batches werden übersprungen statt zu crashen, der
  Editor fällt notfalls auf einen Digest zurück. Ein Lauf dauerte deshalb
  schon mal 24 min — normal sind 7–8 min.
- **Push→Hook-Race:** Render klont sofort; der Workflow wartet 15s zwischen
  git push und Hook-Curl. Beim manuellen Nachdeployen dran denken.
- **Newsrooms:** Der Fetcher (collect/http.py) probiert Browser-UA und
  Bot-UA. Harte Fälle stehen als `type: official` in der Watchlist und werden
  nicht gecrawlt (Stand 08/2026 noch fünf: TIM, Cosmote, UScellular, Ooredoo,
  Maroc Telecom).
- **„Wird über Fachpresse-Tagging abgedeckt" stimmt nur teilweise.** Gemessen
  an 1611 gesammelten Meldungen wird AT&T 27-mal im Titel genannt, Ooredoo
  3-mal — **Maroc Telecom, Cosmote und UScellular kein einziges Mal**. Diese
  drei sind echte blinde Flecken, keine abgedeckten Quellen. UScellular hat
  seit der Übernahme durch T-Mobile keinen eigenen Newsroom mehr.
- **Neue Quellen NUR über `scripts/pruefe_quellenvorschlag.py`.** Das Skript
  schickt jeden Vorschlag durch `collect_source` — also genau den Pfad der
  Pipeline — und prüft neun Kriterien im Code. Ein Modell, das „ich habe es
  geprüft" sagt, zählt nicht: in Session 4 bestand von zwölf Vorschlägen einer
  Recherche-Runde genau **einer** die zentrale Nachprüfung. Wer Agents suchen
  lässt, muss die Gesamtliste am Ende selbst noch einmal durchlaufen lassen.
- **Der Check prüft Form, nicht Wert — die Bewertung bleibt Handarbeit.**
  Beispiele aus Session 4, die alle Kriterien bestanden und trotzdem
  verworfen wurden: der ESG-Kategorie-Feed von Telefónica (genau das
  Boilerplate, das der Analyst verwerfen soll), `corporate.comcast.com/rss`
  (hyperlokales Marketing — stand seit einer früheren Session sogar als
  Warnung im YAML-Kommentar, wurde vom Agent trotzdem erneut vorgeschlagen),
  der Blog von Hugging Face (40 Entwicklermeldungen je Abruf), die spanische
  CNMC (Wettbewerbs-, keine Telekom-Behörde). **Vor jedem Eintrag die
  bestehenden YAML-Kommentare lesen** — dort steht, was schon einmal
  abgelehnt wurde.
- **SEC EDGAR und Börsen-Filing-Feeds sind gesperrt.** Sie liefern technisch
  saubere, datierte Meldungen — aber alle mit demselben Titel („8-K -
  Current report", „Monthly Return - JUL 26"). Im Bericht stünden identische
  Zeilen. Dafür gibt es jetzt Kriterium 5b (unterscheidbare Titel).
- **Eine Quelle zweimal messen, wenn sie geparst wird.** `newswire.ca` bestand
  den Check mit 23 von 23 datierten Meldungen und lieferte beim nächsten Abruf
  30 Meldungen ganz **ohne** Datum — dasselbe Kartenlayout, einmal mit und
  einmal ohne Zeitstempel. Undatiert heißt unsichtbar. `--zweimal` fängt das
  ab; **Bell Canada hängt weiter an dieser Seite** und fällt deshalb
  unvorhersehbar aus dem Bericht (bce.ca liefert nur leere Next.js-Chunks).
- **Der Seen-Store-Schutz wirkt jetzt pro STAPEL, nicht pro Region.** Lauf #67
  hat die alte Luecke gezeigt: im Themenfeld KI-Anbieter scheiterten 2 von 3
  Analysten-Stapeln, bei Regulierung 1 von 2. Beide Bereiche galten als
  analysiert, weil je ein Stapel durchkam — rund 33 ungelesene Meldungen
  wanderten trotzdem in `seen.jsonl` und waeren dauerhaft weg gewesen. Mehr
  Quellen heisst mehr Stapel heisst mehr Teilausfaelle, deshalb meldet
  `analyze_region()` jetzt die Meldungen gescheiterter Stapel als
  `_ungelesen` zurueck und die Pipeline haelt sie aus dem Store.
- **Laufzeit: parallelisieren, nicht kappen.** Der Lauf vom 31.07. brauchte mit
  220 neuen Meldungen 49 von 50 zulässigen Minuten, weil jede Region ihre
  Stapel nacheinander abarbeitete. Stellschrauben sind `collect_max_workers`
  (8) und `analyst_batch_workers` (4, mal `llm_max_workers` 3 = max. 12
  gleichzeitige LLM-Aufrufe). Kappungen sind ausgeschlossen: der Seen-Store
  merkt sich jede neue Meldung als erledigt, egal ob ein Analyst sie gelesen
  hat.
- **Themenfelder gehören NICHT in die Watchlist.** Dort bekämen Nvidia oder
  die GSMA eine Region und einen Alias-Eintrag, und das Fachpresse-Tagging
  würde jede Meldung mit „Nvidia" im Titel einer Region zuschlagen. Sie leben
  in `config/tech_sources.yaml` und laufen unter `thema:<key>` als eigene
  Analysten. Wer den Editor-Themenabschnitt ändert, muss **Prompt und
  `validate_editorial_briefing` gemeinsam** anfassen — sie hängen am selben
  Schalter.
- **GitHub Pages ist AUS** (war Free-Plan-Problem bei privat, dann auf Render
  umgestellt). Nicht wieder aktivieren.
- **Sandbox:** aarch64; pip braucht `--break-system-packages`; Bash-Calls max
  45s → lange Läufe via GitHub Actions, Polling mit `gh run list`.
- **Kein Headless-Browser in der Sandbox:** Chromium startet zwar, kommt aber
  durch den Agent-Proxy nicht ins Netz (`ERR_CONNECTION_RESET`, auch mit
  `--proxy-server`). `newsroom_js`-Quellen sind lokal deshalb NICHT testbar —
  sie erscheinen in `validate_sources.py` als FAIL. In GitHub Actions laufen
  sie normal. Praktische Folge: bei einer JS-Quelle immer erst nach dem
  darunterliegenden Endpunkt suchen (`__NEXT_DATA__`, `/wp-json/wp/v2/posts`,
  `?format=feed`, JSON in HTML-Attributen). In Session 2 waren 6 von 8
  angeblich „JS-toten" Quellen in Wahrheit statisch abrufbar.
- **`scripts/build_sources.py` ist gesperrt:** Es würde `config/watchlist.yaml`
  überschreiben und dabei `item_selector`, `link_template`, `timeout_seconds`
  und `allow_short_titles` verlieren — Felder, die seine Tabelle `M` gar nicht
  kennt. Die **Watchlist wird direkt editiert**. Die Quellen-Doku erzeugt
  `scripts/build_quellen_doc.py --validate` (schreibt nichts nach `config/`).
- **Der Analyst sieht nur die ersten `max_items_per_region` Meldungen** (15).
  Im Lauf vom 31.07. waren 220 Meldungen neu und 70 wurden bewertet. Die
  Reihenfolge entscheidet also, was überhaupt gelesen wird: `pipeline.py`
  mischt die Quellen deshalb reihum (`_interleave_by_source`), und
  **undatierte Meldungen sortieren ans Ende**. Eine Quelle ohne erkanntes
  Datum ist damit faktisch unsichtbar — bei jeder neuen Quelle zuerst prüfen,
  ob `published` gesetzt ist, nicht nur ob Items ankommen.

## 7. Lokal arbeiten & testen

```bash
pip install -r requirements.txt --break-system-packages
export PYTHONPATH=src
pytest -q                                   # Tests, offline
python scripts/validate_sources.py          # Quellen-Health (Netz nötig)
python -m telco_radar.pipeline --no-llm     # E2E ohne API-Key

# Skalierungs-Werkzeuge (Session 5)
python scripts/trefferquote.py --ab 2026-07-25       # Steuergröße des Ausbaus
python scripts/mess_sammelphase.py --worker 48       # Sammelphase messen
python scripts/kostenrechnung.py                     # Kosten je Lauf/Monat
python scripts/finde_quellen.py --aus-watchlist --muster --out k.yaml
python scripts/pruefe_quellenvorschlag.py k.yaml --json e.json
python scripts/uebernehme_quellen.py e.json --probe   # zeigt, wohin es ginge
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

## 9. Stand der Skalierung (Session 5, 04.08.2026)

Der Auftrag `AUFTRAG_SKALIERUNG_1000.md` ist zur Hälfte abgearbeitet: **die
vier Engpässe sind beseitigt und gemessen, der Quellenausbau steht bei 206
statt 1000.** Die vollständige Auswertung mit allen Zahlen steht in
`outputs/skalierung-2026-08-04.md`; hier nur, was eine neue Session wissen muss:

- **Die Steuergröße ist die Trefferquote je Quelle**, nicht „Meldungen je
  Quelle". Gemessen über sechs Läufe bringt eine Fachpressequelle 0,67
  Meldungen je Lauf in den Wochenbericht, eine Betreiberquelle 0,03 — Faktor
  22. Deshalb bestand Welle 1 zu 80 % aus Fachpresse, davon 45 nicht
  englischsprachig. **Vor der nächsten Welle die Trefferquote neu auswerten**
  (`scripts/trefferquote.py --ab <datum>`); ab Lauf #68 ist sie über
  `source_url` exakt statt über den Quellennamen geschätzt.
- **Betreiberquellen bleiben trotzdem unverzichtbar** — sie liefern die
  Provenienz, die Fachpresse liefert die Auswahl. Die Messung sagt nur, wo
  ZUSÄTZLICHE Quellen mehr bringen.
- **Die Sammelphase hängt nicht mehr an der Zahl der Quellen, sondern an der
  langsamsten einzelnen Quelle.** Lauf #68: Median 3,2 s je Quelle, Summe
  1 212 s — aber KT allein 299,8 s, und damit war die Phase 303 s lang. Der
  nächste Hebel ist deshalb ein Gesamtbudget je Quelle, nicht mehr
  Parallelität.
- **Das DeepSeek-Rate-Limit ist nicht gemessen** (der Schlüssel liegt als
  Secret vor und ist aus der Sandbox nicht erreichbar). Lauf #68 lief mit 12
  gleichzeitigen Aufrufen ohne einen 429 durch — mehr ist nicht belegt. Vor
  dem Hochdrehen messen.
- **Kosten sind kein Engpass**: 0,17 $ je Lauf bei 1000 Quellen zur Pekinger
  Stoßzeit, 1,43 $ im Monat. Teuer wird nur der Erstlauf nach einer großen
  Welle (~2 $, ~1 100 Analysten-Aufrufe) — dafür steht das Job-Timeout auf 120
  Minuten.

### Der Weg für die nächste Welle

1. `scripts/finde_quellen.py --aus-watchlist --muster` (mechanisch, null Token)
2. Agent-Breitensuche je Kategorie, Ausgabe im Kandidatenformat
3. **Alles zusammen** durch `scripts/pruefe_quellenvorschlag.py` — die
   Gesamtliste zentral, nicht je Agent
4. Handprüfung der Bestandenen: in Welle 1 fielen dabei **72 von 141** Quellen,
   die jede Formprüfung bestanden hatten (Gadget-Blogs, Enterprise-IT-Presse,
   Geschwisterseiten mit identischem Inhalt)
5. `scripts/uebernehme_quellen.py` trägt ein, `--probe` zeigt vorher, wohin
6. Echter Actions-Lauf, danach Trefferquote neu auswerten

## 10. Der ursprüngliche Auftrag (Kontext, teilweise erledigt)

Liegt als `AUFTRAG_SKALIERUNG_1000.md` im Repo und ist der eigentliche
nächste Schritt. Kurzfassung der vier Engpässe, die VOR den Quellen kommen —
alle an Lauf #67 gemessen:

1. **Sammeln.** 20 s·Worker je Quelle. 1000 Quellen bei den heutigen 8 Workern
   sind 42 min, also allein schon über dem Job-Timeout. Braucht Parallelität
   *mit Host-Drosselung*, nicht nur mehr Worker.
2. **Redaktion.** Der Editor bekommt heute alle bewerteten Meldungen in EINEM
   Aufruf. Bei 1000 Quellen wären das ~650 Meldungen ≈ 122k Token — passt ins
   Kontextfenster und ergibt trotzdem Brei. Braucht zwei Stufen:
   Bereichsredakteure je Region/Thema, dann eine Chefredaktion, die nur deren
   Kurzfassungen sieht.
3. **Seen-Store.** ~308 Byte je Eintrag, git-versioniert, komplett in den
   Speicher geladen. Bei 1000 Quellen ~233 000 Einträge/Jahr ≈ 67 MB/Jahr;
   GitHubs Limit je Datei liegt bei 100 MB. Das ist ein Ablaufdatum.
4. **Kosten und Rate-Limits.** ~150 Analysten-Aufrufe je Lauf statt heute 14.
   Vor dem Hochdrehen der Parallelität das DeepSeek-Limit messen.

Und eine Regel, die im Auftrag steht, weil sie beim Schreiben fast falsch
gemacht worden wäre: **die Mischung der Quellen wird nicht vorab festgelegt.**
Kein Anteil Betreiber / Fachpresse / Regulierung. In Lauf #67 lag die Ausbeute
je Quelle in allen drei Ebenen praktisch gleich (15,9 / 17,6 / 18,6 Meldungen),
es gibt also keinerlei Beleg, dass eine Kategorie wertvoller wäre. Was fehlt,
ist die Trefferquote je Quelle — wie viele ihrer Meldungen ein Analyst
überhaupt bewertet und wie viele im Bericht landen. Die lässt sich aus dem
vorhandenen Berichtsarchiv auswerten und ist vor der ersten neuen Quelle zu
bauen; danach steuert sie den Ausbau.

## 10. Offene Ideen / Roadmap

- E-Mail-/Teams-Versand des Briefings nach jedem Lauf
- Firecrawl/Crawl4AI als Fetcher für JS-Newsrooms (AT&T, Singtel, Telia, …)
- Semantisches Dedup (Embeddings), um dieselbe Story aus mehreren Quellen zu mergen
- Tarif-/Preisseiten-Diffing als dritte Signalebene
- Trend-Charts über mehrere Wochen (Daten liegen ja als JSON-Archiv vor)
- Feedback der Vodafone-Kollegin einarbeiten (steht noch aus)
- Migration auf Vodafone-Infra, falls gewünscht (Runner braucht nur Python + HTTPS)
