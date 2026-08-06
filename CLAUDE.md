# Telco Radar — Handover für die nächste Claude-Session

Stand: 2026-08-05, Ende Session 5 (Skalierung). Dieses Dokument enthält
alles, was eine neue Session braucht, um das Projekt zu verstehen, darauf
zuzugreifen und weiterzuarbeiten.

---

## 1. Was ist das & was ist das Ziel?

**Telco Radar** ist ein automatisches Competitive-Intelligence-System für
Antonios Kollegin bei **Vodafone**. Es beobachtet wöchentlich **drei
Signalebenen**, erkennt **nur wirklich neue** Meldungen, lässt sie von
Agents bewerten („Warum ist das für Vodafone interessant?", Dringlichkeit
1–5) und veröffentlicht einen deutschsprachigen Wochenbericht als Website:

1. **87 Netzbetreiber in 6 Regionen** (Europa, Nordamerika, Lateinamerika,
   Afrika & Naher Osten, Asien, Ozeanien) über **94 crawlbare Quellen**.
2. **33 Telco-Fachpresse-Feeds** (`config/news_sources.yaml`) — seit
   Session 5 auch auf Deutsch, Französisch, Spanisch, Italienisch und
   Portugiesisch sowie regional für Indien, Asien und Afrika. Bis dahin waren
   alle 14 Feeds englischsprachig; das war die auffälligste Lücke im Bestand.
3. **40 Themenquellen in 8 Themenfeldern** (`config/tech_sources.yaml`):
   KI-Anbieter, Geräte, Chips & Modems, Netzausrüster, Satellit & NTN,
   Regulierung & Verbände sowie seit Session 5 „Türme, Glasfaser &
   Rechenzentren" und „MVNO, eSIM & Plattformen". Das sind **keine
   Wettbewerber**, sondern die Unternehmen und Behörden, die den Rahmen
   setzen — eigener Analyst mit eigenem Prompt, eigener Abschnitt im Bericht.

Gesamt: **167 crawlbare Quellen** (Stand 05.08.2026).

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
3. ANALYZE   1 Analyst-Agent pro Region UND pro Themenfeld, Batches à 15
             Items (parallel, analyst_batch_workers), 8k Tokens.
             Themenfelder bekommen TECH_ANALYST_SYSTEM statt ANALYST_SYSTEM -
             ein Chiphersteller ist kein Wettbewerber.
             (src/telco_radar/analyze/agents.py; API direkt via httpx: llm.py)
4. EDIT      EIN- oder ZWEISTUFIG, je nach Menge (editor_modus, Schwelle
             editor_zweistufig_ab_meldungen = 120 bewertete Meldungen):
             einstufig  = ein Editor-Aufruf ueber alles (wie bisher)
             zweistufig = ein Bereichsredakteur je Region/Themenfeld
                          (parallel, sieht NUR seinen Bereich) + eine
                          Chefredaktion, die NUR deren Kurzfassungen und je
                          fuenf Meldungen sieht. Die Bereichsabschnitte
                          werden montiert, nicht neu geschrieben.
             Beides mit Topic-Memory gegen Wiederholungen (analyze/editor.py)
5. PUBLISH   Markdown + JSON nach data/reports/, statische Site nach site/
             (report/html.py + templates/), Commit + Render-Hook
```

Wichtige Dateien:

| Pfad | Inhalt |
|---|---|
| `config/watchlist.yaml` | Regionen → Operator → Quellen. Operator OHNE sources = bot-geschützt, wird via Fachpresse-Tagging abgedeckt (Aliase!) |
| `config/news_sources.yaml` | Fachpresse-RSS (Mobile World Live, Light Reading, …) |
| `config/tech_sources.yaml` | **Themenfelder** (dritte Ebene): KI, Geräte, Chips, Netzausrüster, Satellit, Regulierung. Themen-Tag statt Region; Schlüssel tragen das Präfix `thema:` |
| `config/settings.yaml` | Sprache (de), Modell, Lookback (8 Tage), HTTP, Sammel-Parallelität + Host-Drosselung, Redaktionsmodus, Quarantäne-Schwelle |
| `config/kandidaten_firmen.yaml` | Suchaufträge (Name + Domain) für `finde_quellen.py --firmen`. Sagt WO gesucht wird, nicht was wertvoll ist |
| `data/state/seen.jsonl` | Dedup-Gedächtnis. Seit 08/2026 **kompaktes v2-Format**: ein Hash je Zeile (17 statt ~300 Byte) |
| `data/state/quellen_register.json` | Je Quelle: Herkunft, Abnahmedatum, Läufe, Erfolge, letzter Erfolg, Fehlserie, Quarantäne |
| `data/state/reported_topics.jsonl` | Bereits berichtete Themen (Editor-Memory) |
| `data/reports/YYYY-MM-DD.{md,json}` | Bericht als Prosa (md) + strukturiert (json: stats, regions→highlights) |
| `site/` | Generierte Website — wird von Actions committed, Render published sie (Publish Dir `site`, Build Command nur `echo`) |
| `src/telco_radar/report/templates/` | base/woche/meldungen/transparenz/differenzierung + `_explorer` + style.css + app.js (siehe §5) |
| `scripts/validate_sources.py` | Health-Check aller Quellen: Status, Item-Zahl, wie viele datiert, **neuestes Datum**, **wie viele im Frischefenster** + Liste „liefert Inhalte, aber nichts Frisches" |
| `scripts/build_quellen_doc.py` | Erzeugt `TELCO_RADAR_QUELLEN.md` aus der Watchlist; mit `--validate` mit echten Abrufzahlen |
| `scripts/pruefe_quellenvorschlag.py` | **Abnahme-Check für neue Quellen.** Schickt jeden Vorschlag durch `collect_source` und prüft neun Kriterien maschinell. Ohne PASS hier kommt keine Quelle in die Config |
| `scripts/finde_quellen.py` | Mechanische Breitensuche in Stufen (`rel=alternate` zuerst, Kandidatenpfade nur wenn das leer blieb). Massenbetrieb: `--aus-watchlist`, `--firmen`, `--cache` |
| `scripts/quellen_trefferquote.py` | **Die Kennzahl, die den Ausbau steuert**: bewertet / NEU je Quelle, über das Berichtsarchiv |
| `scripts/miss_sammelphase.py` | Sammelphase messen (Wanduhr, Sekunden je Quelle, 429/403), `--vergleich` für vorher/nachher |
| `scripts/kostenrechnung.py` | Kosten je Lauf und Monat, hochgerechnet auf N Quellen |
| `scripts/migriere_seen_store.py` | Seen-Store v1 → v2, prüft selbst nach und bricht bei Hash-Verlust ab |
| `.github/workflows/radar.yml` | Cron Di + Fr 08:30 UTC + manuell; committet data/+site/, curlt Render-Hook (mit 15s sleep!) |
| `tests/` | pytest-Suite (Fixtures, kein Netz/LLM nötig) |

**Secrets im Repo** (Settings → Actions): `ANTHROPIC` (Antonios API-Key —
der Workflow akzeptiert `ANTHROPIC_API_KEY` ODER `ANTHROPIC`) und
`RENDER_DEPLOY_HOOK`.

## 5. Website (Stand 06.08.2026, nach dem Redesign)

> Hier stand bis zum 06.08.2026 eine Beschreibung („v3,
> Bloomberg-Terminal-Stil": Dark-Theme mit Light-Toggle, Headline-Ticker,
> Erklär-Box, vier nummerierte Abschnitte, SVG-Charts), die **keiner
> ausgelieferten Seite entsprach**. Die tatsächliche Designsprache stammt aus
> der „Design-Modernisierung Juli 2026" und ist hell. Wer der alten
> Beschreibung folgte, baute eine dritte Designsprache. Diese Fassung ist am
> ausgelieferten `site/` nachgemessen.

**Design: Zeitungsausgabe** (Etappe 4, 06.08.2026). Newsprint-Untergrund
(`--paper:#f6f4ee`), **Serife** (Source Serif 4) für alles, was gelesen wird,
**Grotesk** (Libre Franklin) nur für Etiketten — Rubriken, Datumszeile,
Navigation, Meta. **Linien statt Kästen**: keine Schatten, kein Radius;
Hierarchie kommt aus Linienstärke (3px Rubrikleiste, 1px Trenner, Haarlinie).
**Rot ist Akzent, keine Fläche** — die rote Kopfzeile ist weg, Rot markiert
nur Rubriken, Dringlichkeit und Links. Mittiger Zeitungskopf, darunter eine
Datumszeile (Ausgabe / Ressort / Quellenzahl). **Kein Dark-Mode**. Alles
Vanilla JS (`app.js`), kein Framework, kein CDN-JS (die zwei Schriften kommen
von Google Fonts, mit lokalen Rückfallschriften im CSS).

> Davor galt bis zum 06.08.2026 der helle Cream-Canvas mit rotem
> Sticky-Topbar, Inter und großen abgerundeten Karten
> („Design-Modernisierung Juli 2026"). Der Redesign-Plan hatte in seinem
> Abschnitt 5 ausdrücklich festgeschrieben, dass diese Designsprache
> **bleibt** — das war die falsche Vorgabe, und Antonio hat sie kassiert.
> **Wer den Plan liest, muss Abschnitt 5 und 9 dort zusammen mit diesem
> Absatz lesen.**

**Raster mit Gewichtung** (Nachrichtenportal-Umbau, 06.08.2026, Schlussliste
`outputs/nachrichtenportal-2026-08-06.md`). Bis dahin kannte die Titelseite
zwei Gewichtsstufen — Aufmacher plus drei gleich große Anreißer — und
Antonio sagte nach fünf Runden: *„Mir gefällt die Seite immer noch überhaupt
nicht."* Eine Zeitungsseite entsteht nicht aus Schriftart plus Bild, sondern
aus einem **Raster mit Gewichtung**. Jetzt:

| Stufe | Vorlage | Regel |
|---|---|---|
| Aufmacher | `.aufmacher` | 1 Meldung, Bild **≥ 800 px** |
| zweite Reihe | `.reihe-zwei .stueck-mittel` | 2 Meldungen, Bild ≥ 800 px |
| dritte Reihe | `.reihe-vier .stueck-klein` | 4 Meldungen, Bild beliebig |
| „Was wichtig ist" | `.front-wichtig` | 7 nummerierte Zeilen, **ohne** Bild |
| Ressortblöcke | `.ressort-raster` | 6 Ressorts, je Aufmacher + 4 Zeilen |

Ressorts kommen aus der `category` der Meldung (`RESSORTS` in `html.py`),
mit **einer** Ausnahme: Satellit/NTN wird über den Themen-Tagger
abgespalten, sonst hätte „Netz & Technik" ein Drittel der Ausgabe.
„Vermischtes" steht auf der Titelseite nicht. Kein Absender darf oberhalb
der Falz mehr als zweimal vorkommen — ohne diese Regel standen fünf von
sieben Zeilen unter drei Schreibweisen von „SpaceX".

**Jede Schlagzeile jeder Vorlage trägt die Klasse `szl`.** Daran hängen die
Wahrheitstests (keine Dublette, keine abgeschnittene Überschrift, Zahl der
Geschichten oberhalb der Falz). Wer eine Schlagzeile ergänzt und die Klasse
vergisst, fällt aus allen dreien heraus.

**Vier Seiten**, geschnitten nach der Frage des Lesers (vorher sieben, siehe
`PLAN_MARKTRECHERCHE_REDESIGN.md`):

| Seite | Frage | Inhalt |
|---|---|---|
| `index.html` **Diese Woche** | „Was ist passiert?" | Aufmacher + zweite/dritte Reihe + „Was wichtig ist" + Themenradar, dann 6 Ressortblöcke, dann **der volle Prosabericht zweispaltig mit Sprungnavigation**, Zahlen der Woche, Deutschland-Fokus, Auswertung je Bereich |
| `meldungen.html` **Meldungen** | „Zeig mir die Einzelmeldung" | alle Meldungen **nach Ressort gruppiert und innerhalb gewichtet** (Aufmacher / 4 mittlere / zweispaltige Zeilen), Ressort-Sprungleiste, Filter, Volltextsuche über alle Wochen (`search_index.json`), Wochenarchiv |
| `differenzierung.html` | „Womit heben sich Telkos ab?" | persistente, kuratierte Bibliothek (eigene Frage, eigener State) |
| `transparenz.html` | „Kann ich dem Ding trauen?" | Laufprotokoll **und** Quellenbestand |

Dazu `reports/<datum>.html` je Archivwoche (dieselbe Vorlage wie die
Wochenseite, `show_explorer=True`) und die Promo Übersicht unter `promo/`.

**Die alten Dateinamen** (`bericht.html`, `archive.html`, `sources.html`,
`protokoll.html`, `suche.html`, `wettbewerber.html`) existieren weiter als
**Weiterleitungen** — sie stehen in Lesezeichen und Mails. Render ist eine
Static Site, es gibt keine Serverregel für eine 301; die Weiterleitung ist
Meta-Refresh plus sichtbarer Link (`_redirect_html()` in `report/html.py`).

**Vorlagen:** `base` (Navigation, Topbar-Suche) · `woche` (Wochenseite und
Archivwoche) · `meldungen` · `transparenz` · `differenzierung` ·
`_explorer` (Teilvorlage, an zwei Orten eingebunden) · `promo_index` ·
`promo_quellen`.

**Bilder** (`report/bilder.py`, neu geschrieben am 06.08.2026): jede Meldung
wird versucht — kein Deckel —, und die **Größe entscheidet, nicht die
Herkunft. Feed-Bild UND `og:image` werden geholt, mit Pillow gemessen, das
breitere gewinnt.** Vorher galt „Feed zuerst", und Feeds tragen ein
`media:thumbnail`: 18 der 31 Bilder waren schmaler als 860 px, der Aufmacher
der Ausgabe vom 6.8. lag bei 120 × 90. Ergebnis jetzt: 147 von 193 (76 %),
38,9 s nebenläufig. Abgelegt wird als JPEG auf 1280 px (die 40
dringendsten) bzw. 800 px — sonst wäre das Repo mehrere hundert MB im Jahr
schwerer. **`site/images/` spiegelt den Bildordner, es sammelt nicht**, und
`render_site()` streicht jeden `image`-Verweis, zu dem keine Datei mehr da
ist (sonst zeigen Archivwochen leere Kästen, nachdem `raeume_auf()` ihre
Bilder gelöscht hat).

**Abnahme der Seite:** `python scripts/pruefe_portal.py` misst acht
Kriterien gegen die wirklich gerenderte Seite, drei davon mit echtem
Chromium bei 1440 × 900 — unter anderem, ob **irgendein** Bild
hochskaliert dargestellt wird. Nichts an der Optik gilt als erledigt, bevor
dieses Skript grün ist.

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
- **Der Abnahme-Check prüfte Dubletten nur für Kandidaten MIT Betreiber.**
  Themenquellen tragen keinen — für sie lief die Inhaltsprüfung gar nicht. Im
  ersten Massendurchgang der Session 5 waren deshalb **15 von 34 „bestandenen"
  Kandidaten** bloße URL-Varianten bereits konfigurierter Quellen
  (`newsroom.arm.com/feed` neben `.../rss`). Der Index ist jetzt nach DOMAIN
  geschlüsselt. Zweiter Fehler derselben Prüfung: der Überlappungswert rechnete
  gegen die Kandidatenmenge, eine Quelle die eine bestehende *enthält* sah
  dadurch neu aus. Jetzt gegen die kleinere Menge. Und ein Vergleich, der
  mangels lieferfähiger Vergleichsquelle gar nicht stattfinden konnte, gilt
  als Durchfaller — „nicht prüfbar" ist kein PASS.
- **Die Sandbox misst die Sammelphase falsch.** Dort ergab die Host-Drosselung
  185,6 s → 22,2 s (Faktor 8,4), in GitHub Actions 62,5 s → 39,7 s (Faktor
  1,6). Die Sandbox-Zahl hing fast vollständig an EINER langsamen Quelle.
  **Laufzeitzahlen gehören in einen `sources_only`-Diagnoselauf**, den der
  Workflow dafür ausführt (`miss_sammelphase.py --vergleich`) — er fasst weder
  State noch LLM an.
- **`newsroom_js` ist keine reine Wartezeit.** Jeder solche Abruf startet einen
  Chromium, und der Runner hat zwei Kerne. Im Diagnoselauf #74 fiel bei 64
  Workern Viettel mit „Page.goto: Timeout 16000ms exceeded" aus, das bei 8
  Workern durchlief. Headless-Renderings laufen deshalb durch ein eigenes
  Limit (`_JS_GLEICHZEITIG`, 4). Wer `collect_max_workers` erhöht, darf dieses
  Limit NICHT mitziehen.
- **`news_sources.yaml` konnte lange nur RSS.** Der Loader erzwang
  `kind="trade_press"`, und das schickt jede Quelle in den RSS-Parser. Solange
  jede Fachpresse ein Feed war, fiel das nicht auf; die erste mit JSON-API
  (Capacity Media) scheiterte mit „unparseable feed: syntax error". Behoben —
  der Typ gewinnt jetzt.
- **Zweitkanäle sind über den FEED-Sucher abgeschöpft, nicht als Idee.** In
  Session 5 blieb von 142 mechanisch gefundenen Kandidaten bei bereits
  beobachteten Firmen genau einer übrig — aber `finde_quellen.py` sucht nur
  Feeds. Presse-Newsroom plus Investor Relations plus Technik-Blog plus
  Rubrik-Feeds sind weiterhin der billigste Zugewinn, sie sind nur mechanisch
  noch nicht erreichbar.
- **`finde_quellen.py` ignoriert drei Viertel des Webs.** Es akzeptiert nur
  RSS und JSON-API als Kandidaten. Moderne Konzernseiten haben aber meist
  keinen Feed: von 604 gesuchten Firmen brachten in Session 5 **418 (69 %)
  null Kandidaten** — und zwar bei RICHTIGER Domain. Telenor Norwegen,
  Vodafone Italien, Orange Spanien, Free, Fastweb und Deutsche Telekom
  antworten alle mit HTTP 200 und haben Presseseiten, nur eben keinen Feed.
  Die Pipeline kann so etwas längst lesen (52 der 205 Quellen sind
  `type: newsroom`), der SUCHER kann es nur nicht vorschlagen. Das ist der
  größte offene Hebel im ganzen Ausbau.
- **Der Deckel der Sammelphase ist die LANGSAMSTE EINZELQUELLE.** Lauf #75:
  303,7 s Sammelphase, davon 302,6 s eine einzige tote Quelle (KT, mit
  `timeout_seconds: 30` mal zwei User-Agents mal drei Versuche plus Backoff).
  Gegen den langsamsten Einzelfall hilft keine Parallelität. Jede Quelle hat
  deshalb eine harte Frist (`_QUELLEN_FRIST`, 75 s) — sie bricht nur die
  WIEDERHOLUNGEN ab, das Timeout des einzelnen Versuchs bleibt.
- **Regionale Fachpresse landet im Bereich „Global", nicht in ihrer Region.**
  `tag_news_regions` ordnet eine Fachpresse-Meldung nur zu, wenn ein
  Betreibername in der Überschrift steht. Lauf #75 schloss Europa mit NULL
  bewerteten Meldungen ab, während Global 62 von 92 bekam. Mit 19 neuen
  regionalen Feeds ist das der wichtigste offene Punkt: eine Fachpressequelle
  müsste eine Vorgabe-Region tragen dürfen.
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
- **Eine Zahl auf der Seite ist erst wahr, wenn ein Test sie gegen die Daten
  hält.** Am 06.08.2026 wurden beim Aufmaß für den Redesign **sechs** falsche
  Werte gefunden, alle desselben Typs — ein Label und ein Feld, die nicht
  dasselbe meinen —, und alle waren an `pytest -q` vorbeigekommen, weil von
  37 Testdateien nur zwei `render_site()` aufriefen und beide nur die FORM
  prüfen: (1) „426 neue Meldungen bewertet" — 426 waren gelesen, 92 relevant;
  (2) „Alle Signale dieser Woche" über 6 von 92 Zeilen; (3) die
  Wettbewerber-Seite zwei Läufe lang leer und dabei behauptend, die Analyse
  komme beim nächsten Lauf; (4) das Laufprotokoll schreibt `status: "fail"`,
  die Zusammenfassung heißt `failed` — 6 gescheiterte Quellen wurden als 0
  gemeldet; (5) `_stats()` berechnete sechs Werte, die keine Vorlage nutzte;
  (6) `_strip_vodafone_advice` löschte ganze Absätze samt Fakten.
  **`tests/test_seiten_zahlen.py` ist die Gegenmaßnahme — jede neue Zahl auf
  einer Seite gehört dort hinein.**
- **Anbieter und Modell-ID laufen still auseinander.** Der Wettbewerber-Zweig
  holte sein Modell fest aus `openai_analyst_model`. Solange „openai" der
  einzige OpenAI-kompatible Anbieter war, stimmte das; seit DeepSeek
  (c9c30f1) ging eine unbekannte Modell-ID an den falschen Endpunkt, alle
  drei Profile scheiterten in 0,6 s, und der Lauf galt als erfolgreich. Jede
  Stufe holt ihr Modell jetzt aus `_modelle_fuer_anbieter()`. **Wer einen
  Anbieter ergänzt, prüft alle Aufrufer.**
- **Eine gescheiterte Stufe muss sich bis auf die Seite melden.** `log.error`
  reicht nicht — das Actions-Log liest niemand. Profile tragen deshalb ein
  `error`-Feld, und die Seite unterscheidet „gescheitert" von „gab es nicht".
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

## 8a. Der nächste Auftrag

> **`AUFTRAG_NACHRICHTENPORTAL.md` ist abgearbeitet**
> (Schlussliste: `outputs/nachrichtenportal-2026-08-06.md`). Alle acht
> Prüfungen von `scripts/pruefe_portal.py` sind grün, 458 Tests laufen.
> Offen aus diesem Auftrag bleiben zwei Punkte, beide dort begründet:
> die Verifikation auf der Live-Site (der Branch war noch nicht in `main`)
> und der **Platzbedarf im Repo** — rund 17 MB Bilder je Lauf in zwei
> Kopien, hochgerechnet ~1,5 GB im Jahr in der git-Historie. Die Lösung
> wäre, den Zwischenspeicher abzuschaffen und `site/images/` als einzigen
> Ort zu führen; das dreht aber die Grenze „Pipeline-State ≠ Site-Ausgabe"
> um und ist eine Architekturentscheidung, keine Aufräumarbeit.
>
> **Der nächste Auftrag ist damit `AUFTRAG_1000_QUELLEN_WELLE3.md`**
> (Quellenausbau) — beziehungsweise die vier Schritte aus §9 unten, deren
> erster (Vorgabe-Region für Fachpressequellen) unverändert offen ist.

## 9. Stand der Skalierung — und was als Nächstes kommt

> **Der nächste Auftrag steht in `AUFTRAG_1000_QUELLEN_WELLE3.md`.** Er
> benennt die zwei Hebel, die bisher niemand gezogen hat, und ist der Text,
> mit dem die nächste Session anfängt.

**Die aktuelle Zahl bekommst du mit `python scripts/quellen_zaehlen.py`.**
Sie ist die einzige, die zählt: crawlbare Quellen, also was ein Lauf wirklich
abfragt. Zähle NIE mit `grep -c "url:"` über die YAMLs — das zählt die nicht
crawlbaren `official`-Referenzen mit, und genau daran ist Session 5 mit einer
falschen Zahl in ihren eigenen Bericht gelaufen.


Der Auftrag `AUFTRAG_SKALIERUNG_1000.md` ist zur Hälfte erledigt. Die
Schlussliste mit allen Zahlen steht in `outputs/skalierung-2026-08-05.md`.

**Die Architektur trägt 1000 Quellen. Die Quellen sind es noch nicht:**

| Engpass | Stand |
|---|---|
| Sammeln | gelöst. Host-Drosselung + 64 Worker; in Actions 62,5 s → 39,7 s bei 132 Quellen, hochgerechnet 5 min für 1000 |
| Redaktion | gelöst und **abgenommen im Lauf #75**: 14 Bereichsredakteure + Chefredaktion, 92 bewertete Meldungen, 24,8 min, Gliederung korrekt montiert |
| Seen-Store | gelöst. 17 statt 300 Byte je Eintrag, 3,9 statt 68 MB/Jahr, Bestand verlustfrei migriert |
| Kosten | kein Problem: 1,45 $/Monat bei 1000 Quellen im teuersten Fall |
| Quellen | 130 → **167** (+37). Für 1000 fehlen Firmenlisten, keine Werkzeuge |

**Basislinie über die Sessions**, gezählt an `stats.sources_total` aus dem
Laufprotokoll (nicht geschätzt): 85 Quellen vor Session 4 → 130 danach
(+45, dritte Signalebene neu) → **167** nach Session 5 (+37). Wer die nächste
Session beginnt: diese Zahl steht in jedem `data/reports/*.json` unter
`stats.sources_total` — sie ist die einzige, die zählt, was ein Lauf wirklich
abgefragt hat. Ein `grep -c "url:"` über die YAMLs zählt die nicht crawlbaren
`official`-Referenzen mit und liegt deshalb zu hoch.

**Die Trefferquote steht** (`scripts/quellen_trefferquote.py`) und ist die
Kennzahl, an der der weitere Ausbau hängt. Über 11 Läufe gemessen:
Fachpresse 12,2 %, Betreiber 10,5 %, Themenfelder 10,8 % — die drei Ebenen
liegen weiterhin gleichauf, es gibt also **weiterhin keinen Beleg**, dass eine
Kategorie wertvoller wäre. Der Nenner ist dabei entscheidend: gerechnet wird
gegen die NEUEN Meldungen, nicht gegen die gesammelten. Gegen „gesammelt"
gerechnet misst die Kennzahl die Abrufhäufigkeit statt den Wert (1,9 % gegen
11,6 %).

**Die nächsten vier Schritte, in dieser Reihenfolge:**

1. **Vorgabe-Region für Fachpressequellen.** Lauf #75 schloss Europa mit null
   bewerteten Meldungen ab, während „Global" 62 von 92 bekam — die neuen
   deutschen, französischen, spanischen und italienischen Feeds landen dort,
   weil `tag_news_regions` nur nach Betreibernamen in der Überschrift tagt.
   Je mehr regionale Quellen dazukommen, desto leerer wird der Regionsteil.
2. Zwei bis drei normale Läufe abwarten, dann die Trefferquote neu auswerten —
   ab jetzt je KANAL, weil das Laufprotokoll `new` und `source_url` mitführt.
   Erst dann steht fest, was die 35 neuen Quellen und die zwei neuen
   Themenfelder taugen.
3. Die belegten Ballast-Quellen aussortieren. 11 Quellen haben über 11 Läufe
   mindestens 10 neue Meldungen geliefert, von denen KEINE je bewertet wurde
   (Iliad 40, stc 33, AIS 30, PLDT 21, Deutsche Telekom 19, …).
4. Die nächste Firmenliste bauen. Die Ausbeute dieser Session: 450
   Suchaufträge → 313 Kandidaten → 74 abnahmefähig → 35 wertvoll, also **7,8 %
   je Suchauftrag**. Für 1000 Quellen braucht es rund 10 700 weitere
   Suchaufträge. Lohnend nach dieser Messung: regionale Fachpresse je Land und
   nationale Regulierungsbehörden — beide sauber datiert und klar abgegrenzt.

**Die Regel aus dem Auftrag gilt unverändert: die Mischung wird NICHT vorab
festgelegt.** Kein Anteil Betreiber / Fachpresse / Regulierung. Was taugt,
entscheidet die Trefferquote nach den Läufen.

## 10. Offene Ideen / Roadmap

- E-Mail-/Teams-Versand des Briefings nach jedem Lauf
- Firecrawl/Crawl4AI als Fetcher für JS-Newsrooms (AT&T, Singtel, Telia, …)
- Semantisches Dedup (Embeddings), um dieselbe Story aus mehreren Quellen zu mergen
- Tarif-/Preisseiten-Diffing als dritte Signalebene
- Trend-Charts über mehrere Wochen (Daten liegen ja als JSON-Archiv vor)
- Feedback der Vodafone-Kollegin einarbeiten (steht noch aus)
- Migration auf Vodafone-Infra, falls gewünscht (Runner braucht nur Python + HTTPS)
