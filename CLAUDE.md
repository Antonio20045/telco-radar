# Telco Radar — Handover für die nächste Claude-Session

Stand: 2026-08-08, Ende der Session „Review-Umsetzung“. Dieses Dokument enthält
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

Gesamt: **207 crawlbare Quellen** (Stand 08.08.2026). Die Zahl bekommst du mit
`python scripts/quellen_zaehlen.py` — nie mit `grep -c "url:"` über die YAMLs.

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
             + AENDERUNGSRADAR auf 16 Tarifseiten (collect/aenderungen.py)
             + LIEFERZEIT-RADAR auf dem Warenkorb (collect/lieferzeit.py)
             + TARIF-SAMMLER auf den Pflichtdokumenten nach § 1
               TK-TransparenzV (collect/tarif_crawler.py + tarif_pdf.py;
               State: data/state/tarife.jsonl). NUR verlinkte Adressen -
               nie hochgezaehlte IDs
             + CT-RADAR auf Zertifikatslogs (collect/ct_log.py; State:
               data/state/ct_seen.jsonl). Die einzige Ebene, die VOR der
               Veroeffentlichung liegt - und die Meldungen sagen ihren
               Vorbehalt im eigenen Satz
2. DELTA     Seen-Store + Freshness-Filter → nur NEUE Items
             (src/telco_radar/dedupe.py; State: data/state/seen.jsonl)
2b. CLUSTER  Ereignis-Buendelung: dieselbe Sache aus drei Quellen ist EINE
             Meldung (analyze/clustering.py; State: data/state/clusters.jsonl)
3. ANALYZE   1 Analyst-Agent pro Region UND pro Themenfeld, Batches à 15
             Items (parallel, analyst_batch_workers), 8k Tokens.
             Themenfelder bekommen TECH_ANALYST_SYSTEM statt ANALYST_SYSTEM -
             ein Chiphersteller ist kein Wettbewerber.
             (src/telco_radar/analyze/agents.py; API direkt via httpx: llm.py)
3b. CTM      Zweite Bewertungsachse "ist das fuer UNS wichtig?" plus der
             Satz, was es fuers eigene Portfolio heisst - und der Prueflauf
             dieses Satzes gegen den Originaltext
             (analyze/ctm.py + analyze/faithfulness.py)
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
             + TARIFE: Effektivpreis und Positionskarte
               (report/effektivpreis.py + tarife_view.py)
             + FOLIEN: vier Folien je Ausgabe nach site/folien/
               (report/folien.py) - feste Vorlage, harte Zeichengrenzen
6. VERSAND   Montags der Zwei-Minuten-Pfad per Mail, Teams nur fuer die
             Ausnahme (versand.py; State: data/state/versand.json)
```

Wichtige Dateien:

| Pfad | Inhalt |
|---|---|
| `config/watchlist.yaml` | Regionen → Operator → Quellen. Operator OHNE sources = bot-geschützt, wird via Fachpresse-Tagging abgedeckt (Aliase!) |
| `config/news_sources.yaml` | Fachpresse-RSS (Mobile World Live, Light Reading, …) |
| `config/tech_sources.yaml` | **Themenfelder** (dritte Ebene): KI, Geräte, Chips, Netzausrüster, Satellit, Regulierung. Themen-Tag statt Region; Schlüssel tragen das Präfix `thema:` |
| `config/settings.yaml` | Sprache (de), Modell, Lookback (8 Tage), HTTP, Sammel-Parallelität + Host-Drosselung, Redaktionsmodus, Quarantäne-Schwelle |
| `config/promo_sources.yaml` | **Promo-Übersicht**: 15 Marken mit je einer Leitseite (`url`) und weiteren Seiten (`pages:`), zusammen 59 abgefragte Seiten. Endkunden-Aktionsseiten, KEINE Newsrooms — eigener Loader (`promo_config.py`), eigener Collector, eigener State |
| `scripts/finde_promo_seiten.py` | Sucht weitere Aktionsseiten je Marke (Linkernte auf den Bestandsseiten, dann Kandidatenpfade). Sagt WO nachzusehen ist, nicht was taugt |
| `scripts/pruefe_promo_seite.py` | **Abnahme-Check für Promo-Seiten.** Acht Kriterien im Code; Nr. 7 (Eigenständigkeit) vergleicht auch gegen die bereits angenommenen Kandidaten derselben Marke. Ohne PASS hier kommt keine Seite in die Config |
| `config/kandidaten_firmen.yaml` | Suchaufträge (Name + Domain) für `finde_quellen.py --firmen`. Sagt WO gesucht wird, nicht was wertvoll ist |
| `config/ctm_fokus.yaml` | **Der Zuschnitt des Teams**: Heimatmarkt-Marken, direkte Kategorien, Stichworte, Sicherheitsskala. Die eine Stelle, an der steht, was "fuer uns" heisst — wer sie aendert, aendert die Reihenfolge der Startseite |
| `config/vodafone_hebel.yaml` | Was WIR selbst haben, je Differenzierungs-Hebel. Drei Zustaende, `offen` ist der Standard; ein Eintrag ohne `stand` verfaellt. **"Wir haben das nicht" kommt NUR von hier, nie aus einer Modellvermutung** |
| `config/tarif_seiten.yaml` | 16 Dauertarif-Seiten fuer den Aenderungsradar. NICHT die Aktionsseiten — die stehen in `promo_sources.yaml` |
| `config/tarif_quellen.yaml` | **Einstiegsseiten der Tarif-Datenbank.** Es wird NUR abgerufen, was dort verlinkt ist — keine hochgezaehlten Blob-IDs. Nicht zu verwechseln mit `tarif_seiten.yaml` (Aenderungsradar auf HTML) |
| `config/ct_domains.yaml` | Domains des CT-Radars plus die Rauschmuster. Verglichen wird LABELWEISE, nie als Teilkette |
| `config/lieferzeit_warenkorb.yaml` | Der feste Warenkorb des Lieferzeit-Radars: Produkte mit EINER Variante, eine Test-PLZ, je Anbieter das Ident-Verfahren |
| `config/fruehwarnung.yaml` | Fuenf CTM-Kernfragen mit falsifizierbaren Indikatoren. Der Wert steckt darin, dass sie VORHER feststehen |
| `data/state/clusters.jsonl` | Ereignis-Gedaechtnis. ID aus der kanonischen URL, nie aus dem Titel |
| `data/state/tarif_snapshots.json` | Die zuletzt gesehene WERTMENGE je Tarifseite (nicht der Text) |
| `data/state/lieferzeit.json` | Zeitreihe je Produkt und Anbieter, mit Methode und Belastbarkeit je Messpunkt |
| `data/state/versand.json` | Zustellbuch — was schon hinaus ist. Ohne das schickt ein zweiter Lauf am selben Tag dieselbe Mail |
| `data/state/tarife.jsonl` | Zeitreihe der Tarifdokumente. Ein Stand je Zeile; ein unveraendertes Dokument erzeugt KEINEN neuen Satz, nur ein neues `abgerufen_am` |
| `data/state/ct_seen.jsonl` | Bekannte Subdomains je Domain. Klartext statt Hash — hier sind es Hunderte, nicht Millionen, und der Klartext ist die halbe Diagnose |
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

Eine sechste Stufe gab es bis zum 07.08.2026: sechs Ressortblöcke zwischen
Überblick und Bericht. Sie sind weg — dieselben Ressorts, dieselben
Überschriften, dieselbe Quelle standen einen Klick weiter auf
`meldungen.html`, dort vollständig. Antonio: „das ist doppelt gemoppelt."
Mit ihnen ist der Vorspann „Worum es diese Woche geht" gefallen (ein
Ausschnitt des Berichts, der zwei Bildschirme tiefer komplett steht) samt
`_briefing_lead()`. **Der rote Faden bleibt** — er ordnet die Seite weiter,
er wird nur nicht mehr abgeschrieben.

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

**Acht feste Seiten plus temporäre Themenseiten**, geschnitten nach der
Frage des Lesers — davon **fünf in der Navigation**; `suche.html`,
`lieferzeit.html` und `tarife.html` sind gebaut und über ihren direkten
Link erreichbar, aber nicht verlinkt (Stand 09.08.2026):

| Seite | Frage | Inhalt |
|---|---|---|
| `index.html` **Diese Woche** | „Was ist passiert?" | Aufmacher + zweite/dritte Reihe + rechte Spalte („In zwei Minuten", dann „Was wichtig ist" — beide nach `ctm_bezug` vor Priorität) + Themenradar, ggf. Fokusband auf aktive Themenseiten, **dann ohne Zwischenstück der volle Prosabericht** zweispaltig mit Sprungnavigation; Deutschland nur noch als Drei-Zeilen-Verweis auf die Wettbewerbsseite |
| `meldungen.html` **Meldungen** | „Zeig mir die Einzelmeldung" | **sieben Ressort-Übersichtskacheln ohne Scrollen**, darunter je Ressort ein `<details>` mit ALLEN Meldungen in drei Gewichtungen; Wochenarchiv. Die Volltextsuche stand hier bis zum 08.08.2026 am Seitenfuß — sie hat jetzt eine eigene Seite |
| `suche.html` **Dossier** | „Was weiß das Portal über mein Thema, und wie hat es sich entwickelt?" | Suchfeld, Bilanz (Treffer/Zeitraum/Quellen), Überblick (Verlauf je Monat, Absender, Ressorts), Aufmacher mit Bild, Chronik nach Monaten. Speist sich aus `search_index.json` — Meldungen ALLER Ausgaben **plus** Differenzierung **plus** Promo-Aktionen. Nicht in der Navigation: das Suchfeld der Topbar ist der Eingang |
| `differenzierung.html` | „Womit heben sich Telkos ab?" | Lage aus dem Bericht, **Marktbild** (Hebel-Balken, aktivste Anbieter, Regionen), „Neu auf dem Radar", dann je Hebel eine Rubrik mit Erklärsatz und GEWICHTETEN Karten mit Bild. Speist sich aus BEIDEN Speichern (Sweep-DB **und** Presse-Kurator, gemerged in `report/differenzierung_view.py`) |
| `wettbewerb.html` **Wettbewerb** | „Was machen Telekom, O2 und 1&1 — und wie passt das zu den Wochen davor?" | je Fokus-Wettbewerber: aktuelle Lage, laufende Promo-Aktionen seiner Marken (`group` in promo_sources), **Monats-Chronik** aller Moves+Meldungen aus dem gesamten Berichtsarchiv, per URL dedupliziert (`report/wettbewerb.py`, KEIN neuer State, keine LLM-Stufe — alles entsteht beim Rendern) |
| `lieferzeit.html` **Lieferzeiten** (nicht verlinkt) | „Wie lange lassen die anderen ihre Kunden warten?“ | Matrix Anbieter × Produkt aus einem FESTEN Warenkorb, je Zelle mit Originaltext, Methode, Belegstufe und Messzeitpunkt; darunter die Grenzen der Messung. Es gibt keine öffentliche Studie, gegen die jemand diese Zahlen prüfen könnte — also liefert die Seite ihre eigene Gegenprobe mit |
| `tarife.html` **Tarife** (nicht verlinkt) | „Was kostet was wirklich?" | Effektivpreis über 24 Monate (phasengewichtet), Preis je GB, Qualitätsmerkmale, dazu die Positionskarte als **gerechnetes SVG** mit Fair-Value-Linie. Speist sich aus `data/state/tarife.jsonl`, also aus den Produktinformationsblättern — der einzigen Quelle dieses Marktes, die rechtlich wahrheitsbewehrt ist. Die Vollständigkeitsangabe steht OBEN, nicht als Fußnote |
| `folien/<datum>.html` | „Ich brauche drei Folien für Montag" | Vier Folien im Vodafone-Design aus der Ausgabe. Feste Vorlage, feste Platzhalter, harte Zeichengrenzen; die Quellenfolie hat keinen Schalter. Kein Nav-Eintrag — verlinkt am **Fuß des Wochenberichts** (bis 09.08.2026 über der Titelseite; dort kostete die Zeile drei Geschichten oberhalb der Falz) |
| `transparenz.html` | „Kann ich dem Ding trauen?" | Laufprotokoll **und** Quellenbestand, dazu die Erklärung der CTM-Stufen und der Sicherheitsskala |
| `thema/<slug>.html` (temporär) | „Was ist an diesem Ereignis dran?" | Highlight-Themenseiten, siehe unten |

**Die Wettbewerbsseite ist am 08.08.2026 auf die halbe Höhe gebracht worden**
(6777 → 4169 px), weil Antonio drei Bildschirme scrollen musste, bevor der
zweite Wettbewerber begann. Vier Stellschrauben, keine streicht Inhalt: die
**Chronik steht zweispaltig** (eine Chronikzeile braucht keine 1180 px
Satzbreite), der **laufende Monat zeigt zwölf Meldungen** und hält den Rest
in einem `<details>` bereit (`_OFFEN_JE_MONAT`), die Einordnung unter der
Schlagzeile ist auf zwei Zeilen begrenzt, der Themenverlauf reicht drei statt
vier Ausgaben zurück. Der **Name trägt den Abschnitt** (`.wb-kopf`/`.wb-name`,
Serife 28–38 px, dieselbe Bauform wie `.pmarke-kopf`). Fallstrick der zwei
Spalten: die alte Regel „Tageszahl nur beim ersten Eintrag ihres Tages"
**zerreißt am Spaltenumbruch** — oben in Spalte zwei stünden Meldungen ohne
Datum. Jede Zeile trägt ihr Datum deshalb selbst („7.8.").

**Highlight-Themen** (07.08.2026): erkennt ein Ereignis, zu dem viele
Meldungen auftreten (Samsung-Fold-Launch, Starlink-Mobilfunknetz), und baut
dafür eine temporäre Seite im Titelseitensatz. Mechanik in
`analyze/highlight_topics.py`: deterministische Kandidatensuche (Gruppen ≥5
Meldungen aus ≥3 Quellen über gemeinsame seltene WORTPAARE — ein
Verwandtschafts-Graph über einzelne Wörter verband 129 von 138 Meldungen zu
einer Gruppe), dann ein eigener Themen-Agent, der benennt, beschreibt und
Firmen-Cluster („Deutsche Telekom" ist kein Ereignis) verwirft. Store:
`data/state/highlight_topics.json`; Zuordnung neuer Meldungen per
Suchwort-Match läuft auch OHNE Modell weiter, Themen ohne ≥2 neue Meldungen
altern über 4 Läufe und verschwinden (Seite wird gelöscht, `site/thema/`
SPIEGELT den Store); beendete Themen bleiben als Gedächtnis. Auffindbar nur
über das Fokusband der Startseite — bewusst kein Nav-Eintrag.

**Beruhigungsregeln** (07.08.2026, nach Antonios „unruhig durch
Kommentare"): kein Satz auf einer Seite erklärt ihre Bedienung („jede
Kachel zeigt …", „öffnen"), eine Zahl steht je Ort genau EINMAL, alle
Zählwerte tragen dieselbe Etikettklasse (`rubrik-zahl`/`rubrik-zusatz`
statt `count-badge`-Chips). `tests/test_seiten_zahlen.py` erzwingt beides
(`test_keine_seite_erklaert_ihre_eigene_bedienung`,
`test_zaehlwerte_tragen_ueberall_dieselbe_klasse`). „Beobachtend statt
empfehlend" gilt jetzt auf ALLEN Seiten satzteilgenau über
`textwerkzeug.py` (`ohne_vodafone_rat`/`ohne_vodafone_teil`) — Ratschläge
an Vodafone fallen (auch im Genitiv „Vorlage für Vodafones …"),
Beobachtungen über Vodafone-Gesellschaften bleiben.

**Der rote Faden** (Welle 2, 07.08.2026): die Titelseite folgt dem Bericht,
statt parallel zu ihm zu sortieren. `_fuehrende_saetze()` liest die
Aufzählung „Auf einen Blick" aus `briefing_md`, `_faden()` sucht zu jedem
Satz die belegende Meldung (gewichtet nach Wortseltenheit, 1/Häufigkeit —
gezählte Überschneidung allein ordnete „KI treibt Cyberkriminalität in
Afrika" einem Satz über MTN/IHS Towers zu), und `_titelseite()` besetzt
Aufmacher und zweite Reihe damit. Findet sich kein Beleg, bleibt es bei der
Dringlichkeitssortierung — **eine falsche Verbindung ist schlimmer als
keine.**

**Die Promo Übersicht** (`promo/index.html`) ist am 07.08.2026 **zweimal**
gebaut worden. Der erste Anlauf brachte Bilder auf die Seite, aber die
falschen; der zweite ist der, der steht. Antonio dazwischen: *„Das muss
eigentlich die ganze Übersicht, es muss alles neu gemacht werden."*

Zwei Dinge sind anders, und beide sitzen unter der Vorlage:

1. **Die Bilder kommen aus der Aktion, nicht von einem Screenshot.** Bis
   dahin lief je Marke ein eigener Chromium, klickte ein Cookie-Banner weg
   und schnitt 1280 × 720 aus dem Viewport. Zwei der 14 Aufnahmen zeigten
   trotzdem das Banner, eine war weiß, und als Kachel war keine lesbar — eine
   ganze Webseite auf Kachelbreite zeigt keine Aktion, sondern ein Muster.
   Jetzt liefert `collect/promo_snapshot.extract_image_candidates()` die
   Bilder, die die Aktionsseite selbst trägt, und **`promo_bilder.py` ordnet
   sie den einzelnen ANGEBOTEN zu** — in vier Stufen: Anker (das Bild steht
   im Tiefenlink des Angebots) → gleicher Pfad → seltene gemeinsame Wörter
   (1/Häufigkeit, dieselbe Rechnung wie beim roten Faden) → Seitenmotiv.
   Was sich nicht belegen lässt, bekommt **kein** Bild, sondern die Mechanik
   als Schriftkachel. Jedes Bild wird höchstens einmal vergeben.
   **Das Seitenmotiv (Stufe 4) geht nur an die stärkste Aktion einer Marke
   und sagt auf der Karte, dass es eins ist** („Motiv der Aktionsseite
   otelo.de") — es belegt, womit die Marke wirbt, nicht welches Angebot
   gemeint ist. Gemessen lokal über reines HTTP: 16 Bilder für 20 zugeordnete
   Angebote; in Actions kommt das JS-Rendering dazu.
2. **Eine Form statt vier.** Vorher standen Aufmacher, Beistellspalte,
   Markenraster und eine Zone grauer Kästen nebeneinander — wer zwei
   Anbieter vergleichen wollte, musste zwischen drei Darstellungen
   übersetzen. Jetzt: **je Wettbewerber genau eine Karte** (`.pkarte`) mit
   Motiv, Marke, Schlagzeile, einem Satz Beschreibung, Mechanik, Score und
   Frist — gleiche Felder an gleicher Stelle. Darüber die Marktlage als
   Balken („Was der Markt gerade fährt", zählt **Marken**, nicht Angebote),
   darunter je Marke ein Block mit allen weiteren Aktionen als Zeilen, die
   ein eigenes Motiv als 76-px-Vorschau tragen. Marken ohne bestätigte
   Aktion stehen als **eine Zeile**, nicht als fünf leere Kästen.

**Dritter Umbau am 07.08.2026 (Session „Ausbau & Beruhigung"), und er
ersetzt Punkt 2:** Antonio zur Karten-plus-Zeilenwand-Fassung: „total
unübersichtlich, nicht zugänglich, nicht schön." Die Trennung „stärkste
Aktion oben als Karte, alle 50 unten als dreispaltige Zeilenwand" war
wieder eine doppelte Darstellung. Jetzt: **je Marke EIN Block** —
Rubrikleiste (Markenname, Tier), stärkste Aktion groß, die übrigen als
gleiche Karten daneben, jede Aktion genau EINMAL auf der Seite. Kartenmeta
reduziert auf Mechanik-Chip, Frist, neu/ausgelaufen; der Score erscheint
nur noch als „wichtig"-Punkt bei Highlights, das Prüfdatum einmal im
Seitenfuß. Schriftkacheln tragen die konkrete Zahl des Angebots
(„20 GB · 6,99 €") statt viermal derselben Mechanik. Vier Bildfehler an
der Wurzel behoben, der wichtigste als Fallstrick: **ein
`background` auf einem `loading="lazy"`-`img` malt vor dem Scrollen einen
gefüllten Kasten** — 31 von 36 Bildern standen so als graue Fläche in
jedem Screenshot. Dazu: Motiv-Entdopplung in Seitenreihenfolge
(`_entdoppele_bilder()` in `report/promo.py` — `promo_bilder` kann das an
der Quelle nicht, weil unveränderte Seiten ihre Bilder aus früheren
Läufen behalten), Banner ab Seitenverhältnis 2,2 ungeschnitten
(`.pk-bild--banner`), kein Motiv über seine Dateibreite skaliert.

**Vierter Umbau am 08.08.2026, und er korrigiert eine ABSICHT des dritten.**
Antonio: *„da fehlen bei einigen Aktionen die Bilder, das wirkt so richtig
scheiße, außerdem will ich die größten Anbieter wie Telekom etc. an erster
Stelle haben … die Namen der Wettbewerber prominenter, zu dezent."* Gemessen:
**37 von 77 Karten hatten an der Motivstelle gar nichts.** Der dritte Umbau
hatte das ausdrücklich so gewollt („eine kleine Karte ohne belegtes Bild ist
eine reine TEXTkarte: das ist die Absicht, kein Mangel"), und
`pruefe_portal.py` Kriterium 8c hat die Absicht gedeckt, indem es nur die
großen Karten prüfte. Weil eine Rasterzeile so hoch ist wie ihre höchste
Karte, stand neben jedem Bild eine handbreite Lücke. Vier Änderungen
(Schlussliste `outputs/promo-und-wettbewerb-2026-08-08.md`):

1. **Jede Karte trägt ein Motiv** — Bild oder Schriftkachel. Die Kachel ist
   nicht der Notnagel für ein fehlendes Bild, sondern die zweite gültige Form
   einer Karte. Dazu `align-items:start` auf dem Raster: eine kurze Karte wird
   nicht auf fremde Höhe gedehnt, der Zwischenraum liegt ZWISCHEN den Karten.
   Kriterium 8c prüft jetzt **alle** Karten.
2. **Das Seitenmotiv (Stufe 4) rechnet je AKTIONSSEITE, nicht je Marke**
   (`promo_bilder._seitenmotive`). Das war die Rechnung von vorgestern: seit
   dem Mehrseiten-Umbau bringt jede der bis zu sieben Seiten ihr eigenes
   Bühnenbild mit — congstar liefert über vier Seiten 80 Kandidaten und bekam
   höchstens ein Motiv. Kandidaten tragen dafür `page`, Angebote ohne
   `source_url` hängen an der Leitseite (Konvention wie `mark_stale`). Über
   alle statisch abrufbaren Seiten gemessen: **41 → 49 von 77**.
3. **Die Blöcke stehen nach dem Rang des ANBIETERS** (`rang` in
   `config/promo_sources.yaml`, gepflegt statt gerechnet). Vorher sortierte
   der Score der stärksten Aktion — eine Rangliste der Angebote, keine des
   Marktes, und sie hing an einem Lauf: Otelo auf Platz eins, die Telekom auf
   Platz zehn, weil deren JS-Seiten an dem Tag zwei Angebote hergaben. Der
   Score ordnet weiterhin INNERHALB einer Marke.
4. **Der Markenname trägt den Block**: Serife, 26–34 px, Konzern als Etikett
   daneben (`.pmarke-kopf`). Als 11,5-px-Etikett war er kleiner gesetzt als
   jede Schlagzeile unter ihm.

Zwei Befunde nebenbei: `EUR` ohne Wortgrenze schnitt aus „1 Euro einmalig"
die Kachel „1 Eur", und **Lidl Connect zeigte dieselbe Aktion zweimal**
(„SMART Tarife" / „SMART-Tarife"). Die Dublettenerkennung des Stores greift
erst beim nächsten Upsert; was davor entstand, liegt doppelt in der Datenbank.
`_ohne_dubletten()` fasst solche Zwillinge **beim Rendern** zusammen — gleiche
Heuristik wie im Store, ohne die Datenbank anzufassen, und das Motiv der
Dublette erbt die bleibende Karte.

**Eine Marke, mehrere Aktionsseiten** (08.08.2026). Bis dahin hatte jede Marke
genau EINE URL — und das war die eigentliche Lücke: kein Anbieter zeigt seine
laufenden Aktionen auf einer Seite. Der Gerätedeal steht unter `/handys`, der
Wechselbonus unter `/wechselbonus`, die Prepaid-Aktion unter `/prepaid`. ALDI
TALKs `/wechselbonus` war nirgends erfasst; klarmobil war ausschließlich über
seine **Presseseite** beobachtet. Antonio: *„dass man wirklich alle
Promo-Aktionen von den einzelnen Unternehmen auf dem Schirm hat, dafür braucht
es wahrscheinlich mehr als eine Quelle pro Unternehmen."*

Jetzt: **15 Marken, 59 abgefragte Seiten** (vorher 15), davon 41 statisch
(vorher 5) — also lokal nachprüfbar und ohne Chromium-Start je Lauf.
`url`/`kind` bleiben die **Leitseite** (Markenlink auf der Übersicht, Rückfall
für ein Angebot ohne Tiefenlink), `pages:` nennt die weiteren. Schlussliste:
`outputs/promo-quellen-2026-08-08.md`.

Drei Stellen, an denen ein Fehler hier nicht auffällt, sondern **still
Angebote löscht** — alle drei in `tests/test_promo_mehrseitig.py` festgenagelt:

| Stelle | Regel |
|---|---|
| Snapshot-Schlüssel | Marke **+ URL** (`promo_store.snapshot_key`). Als reiner Markenschlüssel überschriebe jede Seite den Stand der zuletzt abgerufenen. Der alte Markenschlüssel gilt für die Leitseite **einmalig** weiter, sonst löste der erste Lauf nach der Umstellung eine LLM-Neuextraktion über alles aus. |
| `mark_stale()` | altert **nur Angebote der wirklich gelesenen Seiten** (`gepruefte_seiten`). Eine Marke mit fünf Seiten hat pro Lauf typischerweise EINE geänderte; ohne diese Einschränkung rückten die Angebote der vier unveränderten jedes Mal Richtung „ausgelaufen" — nach zwei Läufen wäre die halbe Marke weg, und das Protokoll sähe normal aus. Jeder Eintrag trägt dafür `source_url`; Bestandseinträge ohne eine hängen an der Leitseite. |
| `_MAX_ENTRIES_PER_PAGE` | gilt je **Seite**, nicht je Marke, und ist deshalb von 8 auf **6** gesenkt. O2 hat sieben Seiten; 7 × 8 wären 56 Zeilen unter einem Absender. |

**Neue Promo-Quellen NUR über `scripts/pruefe_promo_seite.py`** — dieselbe
Disziplin wie im Presse-Zweig, andere Kriterien (eine Aktionsseite hat kein
Datum, „wie viele Meldungen im Frischefenster" ist dort bedeutungslos). Acht
Kriterien im Code. Das entscheidende ist **Nr. 7, Eigenständigkeit**: es
vergleicht jeden Kandidaten auch gegen die bereits *angenommenen* Kandidaten
derselben Marke. Genau das hat gegriffen — congstars
`prepaid-allnet-s/m/l/xl/xs` sind fünf Seiten mit demselben Gerüst, vier
fielen durch; ohne diesen Vergleich hätten alle fünf bestanden, weil jede
einzelne sich vom *Bestand* unterscheidet. Gerechnet wird gegen die
**kleinere** Wortmenge (dieselbe Lehre wie Session 5). Kandidaten liefert
`scripts/finde_promo_seiten.py` (Linkernte auf den Bestandsseiten, dann
Kandidatenpfade): 109 Kandidaten → 67 bestanden → 44 nach Sichtung.

**telekom.de beantwortet jeden httpx-Abruf mit HTTP 202** und einer
2-KB-Challenge — auch mit Browser-UA, auch beim zweiten Versuch derselben
Session. `curl` bekommt dieselbe URL als 200 mit vollem Inhalt; es ist TLS-/
Client-Erkennung, keine Sperre gegen das Projekt. Die vier Telekom-Seiten sind
deshalb **nicht per Check abgenommen**, sondern per curl nachgemessen und als
`js` eingetragen. **Nach dem nächsten Actions-Lauf im Protokoll nachsehen, ob
sie Text geliefert haben** — dasselbe gilt für die drei
mobilcom-debitel-Seiten, deren Katalog rein JS-getrieben ist.

Wahrheitstests: `tests/test_promo_seite.py` (16) · `tests/test_promo_view.py`
(22) · `tests/test_promo_bilder.py` (17) · `tests/test_promo_mehrseitig.py`
(14) · `tests/test_pruefe_promo_seite.py` (23).

Dazu `reports/<datum>.html` je Archivwoche (dieselbe Vorlage wie die
Wochenseite, `show_explorer=True`) und die Promo Übersicht unter `promo/`.

**Was am 08.08.2026 dazugekommen ist (Umsetzung des Review-Dokuments).**
Sechs Bausteine, alle gerechnet und nicht geraten; Einzelheiten und die
Messungen dazu in `outputs/review-umsetzung-2026-08-08.md`:

| Baustein | Wo | Die eine Regel, die ihn trägt |
|---|---|---|
| **Ereignis-Bündelung** | `analyze/clustering.py` | Stern statt Kette: verglichen wird mit dem VERTRETER, nie transitiv. Das Betreiberfeld schlägt die Großschreibung (im Deutschen ist jedes Substantiv groß, „Tarif" sähe sonst wie ein Eigenname aus). Ein Beleg fällt mit seinem Vertreter aus dem Seen-Store |
| **CTM-Linse** | `analyze/ctm.py`, `config/ctm_fokus.yaml` | Stufe 3 rechnet der CODE (Heimatmarkt-Marke UND Endkundenthema). Das Modell darf sie weder wegnehmen noch sich selbst geben — sonst wäre die Achse wieder das, was sie ersetzt |
| **Prüflauf gegen den Originaltext** | `analyze/faithfulness.py` | **Fail closed.** Zahlen und Sicherheitswort prüft der Code, die Aussage das Modell; was nicht geprüft werden konnte, erscheint NICHT |
| **Zwei-Minuten-Pfad** | `woche.html.j2`, rechte Spalte über „Was wichtig ist" | Höchstens DREI Zeilen (seit 09.08.2026, vorher fünf über dem Aufmacher), je eine Zeile mit höchstens 20 Wörtern, ein Absender nur einmal, leer wenn es nichts gibt |
| **Frühwarn-Board** | `report/fruehwarnung.py` | Die Indikatoren stehen VORHER fest. „Ruhend" bleibt stehen — eine Frage, zu der seit Wochen nichts kommt, ist beantwortet. Es steht UNTER der Titelseite: mit dem Board davor fiel Kriterium 1 von `pruefe_portal.py` auf drei Geschichten oberhalb der Falz |
| **Verlauf, Lücken, Steckbrief** | `report/verlauf.py`, `report/luecken.py`, `report/wettbewerb.py` | Anteile statt Zahlen (eine wachsende Sammlung zeigt sonst immer „alles wächst"); ein weißer Fleck entsteht nur aus einem gepflegten „nein" MIT Datum |

Dazu die Spalte **„Neu seit der letzten Ausgabe"** (`report/seit.py`) neben der
Überschrift der drei Dauerseiten. Sie ersetzt eine einzelne Datumszeile in
einem sonst leeren Drittel — dem besten Platz der Seite. Höchstens drei
Zeilen, jede mit Sprungziel; gibt es nichts Neues, steht dort wieder nur der
Stand. Ein Test hält jedes Sprungziel gegen die IDs der Seite.

**Die Navigation hat FÜNF Einträge** (Diese Woche, Meldungen,
Differenzierung, Wettbewerb, Quellen). `tests/test_suche_page.py` nagelt die
Zahl fest — eine Navigation wächst sonst zurück, und genau davon kam dieses
Projekt.

Sieben waren es vom 08. bis zum 09.08.2026. „Lieferzeiten" und „Tarife"
kamen mit der Begründung dazu, sie beantworteten eine Frage, die sonst
niemand beantwortet — und sind wieder heraus, weil sie **die Frage selbst
nicht beantworten konnten**: die Tarifseite kennt zwei o2-Tarife und keinen
von Telekom, Vodafone oder 1&1, die Lieferzeitseite keinen der drei großen
Anbieter. Beide Seiten werden weiter gebaut und getestet und sind über
ihren direkten Link erreichbar; sie stehen nur nicht in der Navigation.

> **Die Veröffentlichungsschwelle.** Eine Seite, die eine Frage beantworten
> soll, geht erst in die Navigation, wenn sie die Frage beantworten kann.
> Bis dahin wird sie gebaut, getestet und ist über einen direkten Link
> erreichbar, aber nicht verlinkt.
> **Tarifseite:** mindestens drei Anbieter, zwölf Mobilfunktarife, ein
> Tarif mit echter Rabattphase.
> **Lieferzeitseite:** Telekom, o2 und 1&1 erfasst.

Die Regel ist der Preis für die Ausnahme, die am 08.08. zweimal gemacht
wurde. „Diese Seite beantwortet eine Frage, die keine andere beantwortet"
ist eine Aussage über den Zuschnitt, nicht über den Inhalt — und sie stimmt
auch dann, wenn die Seite leer ist. **Wer die sechste Seite anlegen will,
misst vorher die Schwelle nach und begründet sie im Test** — genau dafür
steht die Zahl hart.

**Die alten Dateinamen** (`bericht.html`, `archive.html`, `sources.html`,
`protokoll.html`, `wettbewerber.html`) existieren weiter als
**Weiterleitungen** — sie stehen in Lesezeichen und Mails. Render ist eine
Static Site, es gibt keine Serverregel für eine 301; die Weiterleitung ist
Meta-Refresh plus sichtbarer Link (`_redirect_html()` in `report/html.py`).
`suche.html` steht seit dem 08.08.2026 **nicht** mehr darunter — der Name ist
wieder eine echte Seite.

**Vorlagen:** `base` (Navigation, Topbar-Suche) · `woche` (Wochenseite und
Archivwoche) · `meldungen` · `suche` · `transparenz` · `differenzierung` ·
`_explorer` (Teilvorlage, an zwei Orten eingebunden) · `promo_index` ·
`promo_quellen`.

**Die Suche ist ein Dossier, keine Trefferliste** (08.08.2026). Bis dahin
zeigte das Topbar-Formular auf `meldungen.html`, und die Treffer standen als
graue Textzeilen am FUSS dieser Seite — nach rund 2400 px Ressortkacheln,
Ressortblöcken und Archiv. Antonio: *„Die Suchfunktion ist total bescheuert …
ich verstehe nicht, warum ich da weitergeleitet werde. Wenn ich suche, zum
Beispiel Telekom oder Perplexity, alle Meldungen super dargestellt, dass ich
einen Überblick habe über die Entwicklung, auch über die Historie."*

| Was | Wo |
|---|---|
| Index | `report/suchindex.py` (aus `html.py` herausgelöst). Drei Bereiche: Meldungen ALLER Ausgaben mit `schlagzeile` (nicht `de_title` — der Rest des Portals zeigt diese Zeile), Differenzierungs-Bibliothek, **Promo-Aktionen**. Je Eintrag sein Bild mit fertigem Pfad (`images/…` bzw. `promo/images/…`) |
| Maschine | `TelcoSearch` in `app.js`: **wortweise mit UND-Verknüpfung** (vorher musste die Eingabe als eine Zeichenkette vorkommen — „telekom perplexity" fand nichts) und mit Rangfolge (Absender 8, Schlagzeile 5, sonst 2, plus Dringlichkeit). Die Hervorhebung **kürzt nichts mehr mit „…"** |
| Seite | `suche.html` — Kopf mit Bilanz, „Der Überblick" (Verlauf je Monat, Wer, Worum als Balken), Bereichsfilter mit Zahl, Aufmacher mit Bild, Chronik nach Monaten (6 Bildkarten, Rest als Zeilen) |
| Leere Seite | „Meistgenannt im Archiv" — zwölf Absender als Chips, gerechnet. **Ohne die Promo-Aktionen**: sie sind 256 von 1060 Einträgen und alle deutsch, mitgezählt stünden winSIM und simplytel vor AT&T |

Fallstricke: der Markenanker der Promo-Übersicht wird in `suchindex.marken_anker()`
gerechnet und in `promo.py` gesetzt — laufen die zwei auseinander, springt die
Suche ins Leere (ein Test hält sie zusammen). Und auf `suche.html` blendet
`base.html.j2` das Topbar-Feld aus (`ohne_topbar_suche`): zwei Suchfelder auf
einer Seite sind zwei Bedienelemente für eine Handlung.

**Die Differenzierungs-Seite ist am 08.08.2026 zum zweiten Mal umgebaut worden.**
Der erste Anlauf (07.08.) hatte die drei Darstellungen auf eine Kartenform
reduziert; übrig blieb eine 9060 px hohe Wand aus 77 gleich großen Textkärtchen
**ohne ein einziges Bild**. Antonio: *„total unübersichtlich … keine Bilder, es
ist schwer zu verstehen … viel besser sein analytisch … Bericht finde ich auch
gut, aber nicht einfach so reinpasten, dieser eine lange Bereich."* Fünf
Änderungen:

1. **Jede Karte trägt ein Motiv** — Bild oder Schriftkachel mit dem Absender
   (`report/diff_bilder.py`: erst das Bild, das der Wochenbericht für dieselbe
   URL schon geholt hat, dann `og:image`; gemessen 35 von 71). Trägt die Kachel
   den Absender, steht er **nicht** noch einmal in der Metazeile darunter.
   Eigener Speicher `data/state/diff_images/` mit eigenem Index und eigenem
   Aufräumen: `report_bilder.raeume_auf()` behält nur, was die letzten vier
   Ausgaben referenzieren — ein Differenzierungs-Beispiel lebt Monate.
   `site/images/` spiegelt seitdem **beide** Ordner. Der Index merkt sich auch
   den Fehlversuch (30 Tage), sonst fragt jeder Lauf dieselben 36 Seiten neu.
2. **Das Marktbild steht vor den Beispielen** (gerechnet, kein Modell): welcher
   Hebel wie oft gezogen wird, wer am breitesten aufgestellt ist (gereiht nach
   der Zahl **verschiedener** Hebel — acht Beispiele in einem Hebel sind eine
   Kampagne, vier in vier eine Strategie), woher die Beispiele kommen.
3. **Jeder Hebel sagt in einem Satz, was er bedeutet** — `blurb` aus
   `report/differentiation.py`, also dieselbe Stelle wie die Hebel-Farbe.
4. **Gewichtung statt Kachelwand**: Aufmacher, eine Reihe Karten, Zeilen, Rest
   im Aufklapper. **Nur ein Beispiel MIT Bild kann Aufmacher sein** — eine
   Schriftkachel über 46 % Breite lässt daneben eine halbe Spalte leer. Gibt es
   keins, hat der Hebel keinen Aufmacher; eine Stufe weniger ist ehrlicher als
   eine leere Stufe. Ein Beispiel aus dem Radar führt seinen Hebel nicht auch
   noch an.
5. **Der Bericht wird VERTEILT**: `## Das Bild` in den Seitenkopf, `## Muster`
   als Band unter das Marktbild, `## Einordnung` (H3 je Hebel) über dessen
   Beispiele (`report/differenzierung_bericht.py`). `## Quellenbasis` fällt weg
   — sie führte jede Karte ein drittes Mal auf. **Prompt,
   `validate_briefing`, `build_digest` und die Zerlegung hängen an EINER
   Gliederung**; wer eine Überschrift ändert, ändert alle vier. Ein Bericht in
   der alten Gliederung steht weiterhin zugeklappt am Ende — kein Lauf muss
   abgewartet werden, damit die Seite steht.

Wahrheitstests: `tests/test_diff_bilder.py` (8) ·
`tests/test_differenzierung_bericht.py` (8) · `tests/test_search_index.py` (13)
· `tests/test_suche_page.py` (6) · fünf neue in `tests/test_seiten_zahlen.py`.

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

**Abnahme der Seite:** `python scripts/pruefe_portal.py` misst **vierzehn**
Kriterien gegen die wirklich gerenderte Seite, vier davon mit echtem
Chromium bei 1440 × 900 — unter anderem, ob **irgendein** Bild
hochskaliert dargestellt wird (auf allen drei Seiten, und die Prüfung
scrollt dafür durch, sonst misst sie die Lazy-Bilder gar nicht), ob alle
sieben Ressorts ohne Scrollen sichtbar sind, ob die Promo Übersicht
mindestens zehn echte Bilder zeigt und ob dort **keine Karte ohne Motiv**
steht.
Seit dem 08.08.2026 dazu Kriterium **9** (Differenzierung: Bildquote und
KEINE Karte ohne Motiv), **9b** (das Marktbild nennt dieselben Zahlen wie die
Rubriken darunter) und **10** (die Suchseite liefert zu einem echten Begriff
Treffer, einen Verlauf und bebilderte Karten).
**Gemessen wird seitdem über einen lokalen HTTP-Server, nicht über `file://`** —
`fetch('search_index.json')` ist unter `file://` von der Same-Origin-Regel
gesperrt, die Suchseite bliebe leer, und die Prüfung würde einen Fehler messen,
den es nicht gibt. Der Server bindet auf 127.0.0.1 und braucht kein Netz.
Kriterium 10 misst im BROWSER, nicht im HTML: bis auf das Suchfeld entsteht die
Dossier-Seite in `app.js`, eine statische Prüfung sähe nur leere Behälter.
Nichts an der Optik gilt als erledigt, bevor dieses Skript grün ist.
Kriterium 2 rechnet die **Quote** bebilderter Meldungen, keine absolute
Zahl — die alte Schwelle „≥ 110" war an einer Ausgabe mit 193 Meldungen
kalibriert und ließ eine kleinere Ausgabe mit besserer Quote durchfallen.

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
- **Ein Push auf `main` ist KEIN Deploy.** Am 06.08.2026 lief `deploy.yml` in
  die Actions-Warteschlange, bekam **nie einen Runner** (`runner_id: 0`,
  `started_at == created_at`) und wurde nach 15 Minuten abgebrochen. Der Code
  lag korrekt auf `main`, aber Render erfuhr nie davon und lieferte weiter die
  alte Fassung aus — aufgefallen erst, weil Antonio auf die Seite sah. **Nach
  jedem Push den AUSGANG von `deploy.yml` prüfen, nicht nur die Live-Seite
  pollen**; ein hängender Deploy und eine noch nicht fertige Auslieferung
  sehen von aussen gleich aus. Nachholen: Actions → „Deploy Site" → „Run
  workflow" auf `main`. Gegenprobe, dass live wirklich ankam, was geprüft
  wurde: `curl -sS https://telco-radar.onrender.com/index.html | md5sum`
  gegen `md5sum < site/index.html`.
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
- **Ein Test, dessen Lookup ins Leere geht, ist grün und prüft nichts.** Am
  09.08.2026 verglich ein neuer Test die Reihenfolge der Startseite gegen die
  Berichtsdatei — geschlüsselt auf `schlagzeile`. Das Feld gibt es dort nicht:
  die Datei kennt `headline` und `title`, die **Schlagzeile rechnet erst
  `_flatten()`**. Der Lookup traf 0 von 7 Zeilen, die Liste blieb leer, und
  `[] == sorted([])` ist wahr. Aufgefallen ist es erst, als jemand die
  geänderte Vergabereihenfolge zurückdrehte und der Test grün blieb.
  **Jeder Test, der zwei Datenquellen über einen Schlüssel verbindet, braucht
  eine Zeile `assert len(zugeordnet) == len(erwartet)`** — sonst meldet er den
  nächsten Feldumbau nicht, sondern verschweigt ihn. Dasselbe gilt für
  konstruierte Fälle: prüfe im selben Test, dass der Fall OHNE die Zusicherung
  wirklich eintritt. Ein Fixture, das die Dublette gar nicht auslöst, beweist
  nicht, dass die Sperre greift.
- **Ein zu kleines `max_tokens` sieht aus wie eine tote Quelle.** Läufe #83–85
  (07.08.2026): 15 von 19 gelesenen Promo-Seiten scheiterten mit
  `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` — also an einem
  **leeren** String. Dasselbe traf Promo-Bewertung, Kategorie-Sweep und
  Promo-Redaktion. Das Muster war eindeutig: es scheiterten genau die Stufen
  mit kleinem Budget (1800/2000/2200/3200), während Analyst (8000) und
  Redaktion (32000) durchliefen. Ursache: `chat_template_kwargs={"thinking":
  False}` schaltet die Denkspur **nur auf NVIDIAs NIM-Endpunkt** ab; der Lauf
  spricht aber gegen `api.deepseek.com`, wo der Parameter ignoriert wird —
  `deepseek-v4-pro` denkt trotzdem und ist mit dem Budget fertig, bevor die
  Antwort anfängt. Nach dem Hochziehen: Telekom hatte erstmals seit dem
  25.07. wieder aktive Angebote, die Promo-Redaktion lieferte wieder echten
  Text statt des Notfall-Digests, beitragende Seiten 9 → 16.
  **`llm.py` meldet eine leere Antwort jetzt beim Namen** (Modell,
  `finish_reason`, `max_tokens`, Länge der Denkspur) und wirft dafür einen
  `ValueError`, den der Retry-Wrapper bewusst NICHT fängt — ein zu kleines
  Budget wird beim vierten Versuch nicht größer. Wer eine Stufe ergänzt:
  8000 ist die Untergrenze, die sich bewährt hat.
- **Ein gescheiterter LLM-Aufruf darf nie wie „nichts gefunden" aussehen.**
  `extract_promos` gab für beides `[]` zurück; die Pipeline zählte die Seite
  als geprüft und ließ `mark_stale` über ihre Angebote laufen. Zwei Aussetzer
  in Folge, und eine noch laufende Aktion war als „ausgelaufen" verschwunden —
  dieselbe Lücke, die im Presse-Zweig der Seen-Store-Stapelschutz schließt.
  Jetzt fliegt ein `PromoExtractionError`, die Seite gilt als ungelesen.
- **Das Pipeline-Log wird auch bei ERFOLG als Artefakt abgelegt.** Nach Lauf
  #83 ließ sich nicht beantworten, warum Telekoms fünf Seiten nichts ergaben,
  weil das Log eines erfolgreichen Laufs verworfen wurde. Ein grüner Lauf kann
  eine halb tote Quelle verdecken.
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
- **Ein 403 ist nicht automatisch ein User-Agent-Filter.** Am 08.08.2026
  gegen die drei ausgefallenen Quellen gemessen: ISPreview UK und MediaNama
  antworten mit 200 — ihr Ausfall lag nicht am Absender. **Telecompetitor
  antwortet auf JEDE Variante mit 403**: voller Client-Hint-Satz, nackter
  Browser-UA, Googlebot-UA, HTTP/2, ohne Referer. Das ist eine Sperre gegen
  den IP-Bereich, und kein Kopfzeilentrick löst sie. Wer das nächste Mal
  „realistischere Header" als Lösung vorschlägt: erst messen, dann bauen.
- **Ein Feed ohne `pubDate` ist kein Sonderfall.** Der RSS-Feed der
  Bundesnetzagentur — der Regulierer des Marktes, um den es hier geht —
  trägt weder `pubDate` noch `dc:date`. Alle 50 Meldungen galten als
  undatiert, und undatiert heißt unsichtbar. `collect/rss.py` liest das
  Datum deshalb notfalls aus dem LINK (`/…/2026/20260806_…`); damit sind es
  10 von 10. Bewusst nur vierstellige Jahre und kein sechsstelliges Muster —
  das fände jede Artikelnummer.
- **JSON-LD trägt die Lieferzeit NICHT.** Der naheliegende und im Review
  empfohlene Weg (`schema.org/OfferShippingDetails`) ist im deutschen
  Telko-Handel nicht belegt: winSIM liefert ein sauberes `Product` samt
  `Offer`, aber ohne `shippingDetails` und ohne `deliveryTime`; otelo trägt
  seine Zustände in einem JavaScript-Wörterbuch mit Platzhaltern
  (`Lieferzeit ca. {DELIVERY_TIME} Tage`). Die Stufe steht trotzdem im Code —
  sie kostet nichts und greift ohne Änderung, sobald ein Shop sie nachrüstet.
- **Ein Diff auf einer Tarifseite braucht drei Sicherungen, sonst ist er
  Rauschen.** (1) Das Etikett eines Preises darf nur aus DERSELBEN Textzeile
  stammen — ohne die Blockgrenze las das Etikett von „19,99 €" die
  Nachbarkachel mit, und bloßes Umsortieren war eine Preisänderung. (2)
  Uhrzeiten, Datumsangaben, Sitzungsnummern und Zählerstände müssen raus,
  sonst meldet JEDER Abruf. (3) Unter zehn erkannten Werten gilt die Seite
  als JavaScript-gebaut: eine echte Preistabelle bringt 16 bis 54 Werte, eine
  JS-Seite drei aus dem Fließtext.
- **Eine neue Seite oberhalb der Falz kostet Titelseite.** Das Frühwarn-Board
  stand zuerst über dem Aufmacher; Kriterium 1 von `pruefe_portal.py` fiel
  damit von zehn auf **drei** Geschichten oberhalb der Falz. Wer oben etwas
  einfügt, prüft dieses Kriterium — es ist der einzige, der Platz misst.
- **Der Abnahme-Check prüft Form, nicht Wert — auch beim Deutschland-Paket.**
  Am 08.08.2026 bestanden Bundeskartellamt (allgemeine Wettbewerbsbehörde,
  im Abruf: Straßenreparatur-Kartell), der Ratgeberblog der Deutschen
  Glasfaser („Handy wird heiß"), Holafly (Reiseblog mit SEO-Inhalten) und
  Thales (Sammelfeed eines Rüstungskonzerns, „uncrewed vessels for ASW
  frigates") — alle vier wurden verworfen. **Vor jedem Eintrag die
  bestehenden YAML-Kommentare lesen**; dort steht, was schon abgelehnt wurde,
  jetzt einschließlich der Gründe dieser Runde.
- **„0 relevant" heißt nicht „Quellen fehlen".** Das Themenfeld „MVNO, eSIM &
  Plattformen" liest 8 Meldungen und behält 0. Nachgeprüft mit zwölf
  Firmensuchen und neun Kandidaten: es liegt nicht an fehlenden Quellen. Die
  konfigurierten sind ZULIEFERER-Feeds, und der Analyst bewertet ihre
  Produktmeldungen zu Recht unter Relevanz 2; die Endkundenbewegung findet in
  der Fachpresse statt, die schon im Bestand ist. Wer das Feld beleben will,
  braucht eine ANDERE Art Quelle, nicht mehr von dieser.
- **Was bewusst NICHT gebaut wird, und warum** (aus dem Review vom
  08.08.2026, damit die Ideen nicht in sechs Wochen wiederkommen):
  *Meta Ad Library* — der `ads_archive`-Endpunkt deckt programmatisch nur
  politische und die regulierten Sonderkategorien ab; normale Tarifwerbung
  ist über die API **nicht** abrufbar. *Google Ads Transparency Center* —
  keine öffentliche API, der BigQuery-Datensatz enthält ebenfalls nur
  politische Werbung. *Trustpilot* — Scraping in den Nutzungsbedingungen
  ausdrücklich untersagt, die API gilt nur fürs eigene Profil.
  *App-Store-Bewertungen fremder Apps* — dieselbe Grenze. *X-API* —
  vierstellig im Monat bei sinkender Relevanz. *Similarweb-artige
  Schätzungen* — geschätzt statt gemessen, ein Fremdkörper in einem Bericht,
  dessen Alleinstellungsmerkmal der Belegzwang ist. *Archiv-Dialog (RAG)* —
  braucht einen Dienst zur Laufzeit; die Website ist eine Static Site ohne
  Backend, und genau das ist die Bedingung dafür, dass sie nie einschläft.
- **Der Tarif-Sammler enumeriert NICHT, und das ist keine Vorsicht.** Es wird
  ausschliesslich abgerufen, was auf einer konfigurierten Seite als Link
  stand. Die o2-Dokumente liegen unter fortlaufenden Blob-IDs im S3-Bucket;
  sie durchzuzaehlen waere trivial und ist die Grenze, an der aus dem Abrufen
  oeffentlicher Pflichtdokumente das Leerraeumen einer fremden Datenbank wird
  (§ 87b UrhG). `sammle()` fuehrt darueber Buch, und
  `test_crawler_ruft_nur_verlinkte_adressen_ab` stellt eine erreichbare, aber
  nicht verlinkte Falle auf. Nebenbei ist es die einzige Methode, die
  funktioniert: geratene Slugs sind 404 (`magentamobil-l-20250401` gibt es
  nicht, nur `magentamobil-data-l-20250401`).
- **Bei Tarifdokumenten entscheidet der Content-Type, nicht die Endung.** Die
  Telekom liefert ihre Produktinformationsblaetter unter
  `/produktinformationsblatt/<slug>` — ohne `.pdf`, mit
  `Content-Type: application/pdf`. Wer auf die Endung filtert, findet dort
  kein einziges Dokument.
- **Die Spaltenzuordnung in einem PDF haengt am WORT, nicht an der Zeile und
  nicht am Zeichenschnitt.** Die Geraetepreisstaffel steht spaltenweise ueber
  drei Zeilen. Verkettet und per Regex gelesen ergibt sie „mit Premium- mit
  Premium- Smartphone" (zwei Spalten verschmolzen); hart an der
  Zeichenposition geschnitten zerreisst sie „Smartphone" zu „Smartphon"/„e".
  Und die Spaltenbreite wird GEMESSEN: mit fester Toleranz stand „Hardware"
  aus der Zeilenbeschriftung in einem Dokument 15 und im anderen 14 Zeichen
  von der ersten Spalte entfernt.
- **„Keine Mindestlaufzeit" ist 0, nicht None.** Eine Aussage, kein fehlender
  Wert — als None faellt der Tarif in die Quarantaene, und der Effektivpreis
  rechnet gegen 24 Monate, die es nicht gibt. Ebenso ist ein Feld, das der
  Extraktor diesmal NICHT fand, ein Ausfall und keine Aenderung: „80 GB →
  nicht angegeben" waere die haeufigste Falschmeldung dieses Radars.
- **Zwei Dokumente mit derselben Titelzeile im SELBEN Lauf sind zwei
  Produkte, nicht zwei Fassungen.** Live gemessen: o2 fuehrt
  `o2-home-l-flex` und `o2-home-l-175-flex` als getrennte PDFs, beide mit der
  Ueberschrift „O2 Home L 175/250/300 Flex". Ohne Unterscheidung meldete der
  Diff bei jedem Lauf abwechselnd hin und her.
- **Der CT-Rauschfilter vergleicht LABEL, nie Teilketten.** `news.congstar.de`
  enthaelt „ns"; ein Teilkettenfilter haette genau die Meldung verworfen, die
  dem Radar seinen Wert gibt (die Zweitmarken `jamobil` und `pennymobil`
  waren ueber keine andere Ebene sichtbar). Und der Timeout grosser Domains
  ist eine EIGENE Fehlerklasse: als leeres Ergebnis gespeichert waere die
  Grundlinie danach leer und der naechste Lauf meldete alles.
- **Der Effektivpreis rechnet phasengewichtet und gegen einen FESTEN
  Horizont.** „6 Monate 9,99 €, danach 29,99 €" ist 24,99 €. 24 Monate auch
  fuer Flex-Tarife — nicht weil die so lange laufen, sondern weil ein
  Anschlusspreis sich auf 24 Monate anders verteilt als auf einen. Und immer
  DREI Werte ausweisen: eine Rangliste nach Effektivpreis allein ist eine
  Rangliste der Drosselung.
- **Ein Archiv-Dialog bleibt extraktiv, solange es kein Backend gibt.** Die
  Antwort besteht aus den Eintraegen selbst; damit kann eine Fussnote nicht
  auf etwas zeigen, das die Aussage nicht deckt. Wer dort ein Modell
  einsetzt, braucht denselben Prueflauf wie `faithfulness.py` — und einen
  Dienst zur Laufzeit, den diese Static Site nicht hat. Die JS-Fassung in
  `app.js` ist eine ZWEITE Umsetzung derselben Rechnung; zwei Tests halten
  Konstanten und Stoppwoerter zusammen, sonst antwortet die Seite anders als
  der Test und beide sind fuer sich gruen.
- **`pdftotext` ist ein externes Binary.** Die Extraktionslogik arbeitet
  deshalb auf TEXT, nicht auf PDF, und wird gegen gespeicherte Textfixtures
  geprueft. Wer sie ans Binary bindet, verliert achtzig Tests, sobald jemand
  die Suite ohne poppler laufen laesst.
- **`pruefe_portal.py` Kriterium 4 faellt nach einem `--no-llm`-Lauf
  durch.** Ohne Analyst gibt es keine Kategorien, also kollabieren die sieben
  Ressorts auf zwei, und das Kriterium verlangt mindestens drei. Das ist kein
  Fehler der Seite — vor dem Messen den ausgelieferten `site/`-Stand
  wiederherstellen (`git checkout -- site data`).
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

> **Zuletzt erledigt (09.08.2026, Antonio direkt): Startseite und
> Navigation, K1–K3.** Grundlage war eine Prüfung der Live-Seite vom
> 8. August. Stand danach: **1104 Tests**, alle **14 Prüfungen von
> `pruefe_portal.py`** grün.
>
> | | Was | Messung |
> |---|---|---|
> | K1 | Kurzpfad zurückgebaut: höchstens drei Einträge, je eine Zeile mit ≤ 20 Wörtern, in der rechten Spalte statt über dem Aufmacher; Aufnahme nur mit `ctm_bezug` 3 oder Stufe 2 **mit einer konkreten Zahl aus der Quelle** | Unterkante der Aufmacher-Schlagzeile auf dem Telefon (390×844) von **1364 px auf 325 px** — vorher 520 px unterhalb der Falz; auf 1440×900 von 863 auf 298 px |
> | K2 | „Was wichtig ist" folgt derselben Achse wie der Kurzpfad | die zwei BREKO-Stellungnahmen von Platz 1+2 auf **4+5**, davor drei Meldungen mit direktem Portfoliobezug |
> | K3 | `tarife.html` und `lieferzeit.html` aus der Subnav (nicht gelöscht), Veröffentlichungsschwelle in §5 | Navigation **7 → 5** |
>
> **Der eigentliche Fund saß nicht in der Sortierung.** `_flatten` sortiert
> längst nach `ctm_bezug` vor Priorität — die Digest-Spalte widersprach dem
> Kurzpfad trotzdem, weil die **vier kleinen Bildkacheln vor ihr zugriffen**
> und dabei jede Stufe-3-Meldung abräumten. Der Eingriff steht deshalb in
> der Reihenfolge der Vergabe in `_titelseite`, nicht in einem `sorted()`.
>
> **Die Foliensatz-Zeile ist an den Fuß des Berichts gewandert** (die zweite
> der beiden Möglichkeiten aus K1). Als Abstand über der Titelseite hätte
> sie 18 px gekostet, und genau daran hing das Kriterium: **oberhalb der
> Falz 3 → 5 → 8 Geschichten** (vorher / Kurzpfad umgebaut / Zeile
> verschoben). Kriterium 1 von `pruefe_portal.py` war vor dieser Session
> **rot** — der Kurzpfad vom 08.08. hatte es von 10 auf 3 gedrückt, und der
> Handover-Eintrag „alle 14 grün" stimmte nicht mehr.
>
> **Zwei bestehende Tests sind geändert worden**, beide weil sie genau das
> Verhalten festhielten, das der Auftrag umkehrt:
> `test_zwei_minuten_steht_vor_dem_aufmacher` (Kasten über dem Aufmacher →
> jetzt `…_steht_in_der_spalte_ueber_was_wichtig_ist`) und
> `test_navigation_hat_sieben_eintraege` (→ `…_fuenf_…`). Sonst wurde kein
> Test angefasst.
>
> **Neu:** `tests/test_startseite_kurzpfad.py` (18) und
> `tests/test_falz_browser.py` (4, echtes Chromium auf 1440×900 und
> 390×844). Gegen den alten Stand gemessen fallen **19 der 22** durch. Die
> drei, die auch dort bestehen, sind erklärbar: einer ruft `zwei_minuten()`
> mit explizitem Deckel auf (die Seite deckt
> `test_hoechstens_drei_eintraege_mit_quellenlink` ab), einer prüft eine
> Invariante, die auf dieser Ausgabe auch vorher galt, und die
> Schreibtisch-Messung war vorher knapp bestanden (863 von 900 px) — gekippt
> ist nur das Telefon.
>
> **Der Kurzpfad-Zuschnitt liegt in `ctm.kurzpfad()`, nicht beim Aufrufer.**
> Erster Anlauf war, die Verschärfungen als abwählbare Parameter zu bauen,
> damit `versand.py` unverändert bleibt. Das hat eine dokumentierte
> Zusicherung gebrochen: die Mail verspricht „dieselbe Auswahl wie auf der
> Startseite", zeigte aber weiter fünf ungefilterte Zeilen — an der Ausgabe
> vom 8. August gemessen stand **genau eine der drei Seitenzeilen auch in
> der Mail**, und die Mail führte mit einem 22-Wort-Konjunktiv, den die
> Seite ausdrücklich nicht mehr zeigt. Jetzt holen beide denselben
> Zuschnitt aus einer Funktion. Die Parameter von `zwei_minuten()` bleiben
> abwählbar, aber **niemand wählt sie mehr einzeln**.
>
> **Kurzpfad und Digest-Spalte sperren sich gegenseitig.** Beide ziehen seit
> K2 aus derselben Sortierung und stehen untereinander in derselben Spalte;
> ohne Sperre steht die stärkste Meldung zweimal. `_titelseite(…,
> belegt=…)` hält sie aus „Was wichtig ist" heraus — **nur dort**, nicht von
> der ganzen Seite: der Aufmacher zeigt seinen Folgerungssatz absichtlich
> mit (`.ctm-satz`), und eine Vollsperre hätte der Meldung mit dem besten
> Satz den Aufmacher für immer verwehrt.
>
> **Was `zwei_minuten()` abweist, steht jetzt im Protokoll** (`Kurzpfad:`,
> mit Zahl je Grund). Ein leerer Kasten sagte sonst nur „nichts gefunden",
> und ob nichts kam oder zwanzig Sätze an der Wortgrenze hingen, wäre
> hinterher nicht mehr zu beantworten.
>
> **`ci.yml` installiert jetzt Chromium.** Ohne den Schritt übersprang sich
> der Browser-Test auf genau der Maschine, die Merges absichert — und ein
> Skip sieht im Protokoll aus wie ein Erfolg. Der Test sucht den Browser an
> beiden Orten (Sandbox `/opt/pw-browsers`, Runner `~/.cache/ms-playwright`).
>
> **Offen daraus, erst nach dem nächsten Actions-Lauf prüfbar:**
> 1. Die Aufnahmeregel ist gegen **eine** Ausgabe gemessen (8. August: 5 → 3
>    Einträge). Steht der Kasten mehrere Läufe leer, ist sie zu scharf —
>    dann im Protokoll nachsehen, wie viele Sätze überhaupt Stufe 3 tragen.
> 2. **Eine freistehende Ziffer neben einem Produktnamen zählt weiter als
>    Zahl.** „Redmi 17C 5G" fällt (am Buchstaben erkannt), „Redmi 17 5G"
>    nicht. Eine strengere Regel bräuchte eine Einheit neben der Zahl — das
>    wirft „249 Rupien" nicht, aber „500 Zloty Bonus" könnte kippen. Erst
>    messen, dann verschärfen.
> 3. Die zwei Seiten unter der Schwelle: sobald der Tarif-Sammler drei
>    Anbieter und zwölf Mobilfunktarife hat, gehören sie zurück in die
>    Navigation — die Zahlen stehen in §5.
>
> **Die Auftragsgrundlage fehlt im Repo.**
> `claude/nachbesserung-nach-erstem-durchgang-2026-08-08.md` gibt es nicht,
> und ein Verzeichnis `claude/` auch nicht — dasselbe wie beim
> Umsetzungsplan (siehe unten). Gearbeitet wurde gegen die Punkte, die
> Antonio in der Nachricht selbst ausgeschrieben hat.

> **Davor erledigt (08.08.2026, Antonio direkt): der Umsetzungsplan,
> Teil 1 und A1–A10.** Antonio hat den Plan übergeben („diggah erledige
> alles, setze alle Phasen um"). Stand danach: **1080 Tests**, alle **14
> Prüfungen von `pruefe_portal.py`** grün, **207 crawlbare Quellen**.
> Vollständige Liste mit allen Messungen:
> `outputs/umsetzungsplan-2026-08-08.md`.
>
> Neu gebaut: **CT-Radar** (A3), **Tarif-Extraktor** (A4), **Tarif-Sammler
> mit Historie** (A5), **Effektivpreis und Positionskarte** (A6),
> **Foliensatz-Export** (A8), **Kleingedruckt-Wächter** (A9), **Frag das
> Archiv** (A10), dazu die Einrichtung aus Teil 1 (`.claude/settings.json`
> mit Berechtigungen und Test-Hook, drei Subagenten, `commit-sicher`).
>
> **A1, A2 und A7 waren schon da** — der Plan und das Review datieren vom
> selben Tag wie die Vorsession, die sie umgesetzt hat. Nachgemessen:
> `analyze/clustering.py`, Browser-UA in `settings.yaml:395` plus `certifi`
> in `http.py:66`, `analyze/ctm.py` mit `faithfulness.py`.
>
> **Die zwei Grundlagendokumente des Plans fehlen im Repo**
> (`claude/site-review-und-feature-roadmap-2026-08-08.md` und
> `claude/neue-features-ideenkatalog-2026-08-08.md`; es gibt kein
> Verzeichnis `claude/`). Gebaut wurde deshalb gegen **echte Dokumente
> statt gegen die Tabellen** — alle drei URL-Muster aus dem Plan sind tot.
>
> **Zwei bewusste Abweichungen:** die Navigation hat jetzt **sieben**
> Einträge (Begründung steht im Test), und `commit-sicher` pusht auf den
> aktuellen Branch statt auf `main`.
>
> **Offen daraus, alles erst nach dem nächsten Actions-Lauf prüfbar:**
> 1. **`Tarif-Sammler:` im Protokoll.** Die Telekom-Einstiegsseite
>    antwortet httpx mit HTTP 202 (§5) und lieferte lokal null Links — nur
>    die drei o2-Dokumente kamen an. Steht dort weiterhin nur o2, braucht
>    die Telekom-Quelle den JS-Collector.
> 2. **`CT-Radar:` im Protokoll.** Die Grundlinie steht (15 Domains, 0
>    Funde — beim ersten Lauf richtig so). Ab dem zweiten Lauf gilt: meldet
>    er zweistellig viele Namen je Domain, ist der Rauschfilter zu grob;
>    meldet er nie etwas, ist er zu scharf. Seine Modellstufe ist noch nie
>    gegen ein echtes Modell gelaufen.
> 3. **Die Positionskarte braucht drei Punkte** für eine Ausgleichsgerade.
>    Mit den zwei o2-Tarifen aus dem Livelauf zeigt sie noch keine.
> 4. **Vodafone fehlt in der Tarif-Datenbank.** `vodafone.de/infofaxe`
>    liefert HTTP 200, die Linkernte dort ist nicht gemessen. Ohne den
>    eigenen Punkt zeigt die Positionskarte den Markt ohne uns.
> 5. **1&1 fehlt mit Grund**: das PIB-Verzeichnis ist eine Next.js-Seite
>    ohne statische Links. Braucht den JS-Collector, keinen geratenen Pfad.

> **Davor erledigt (08.08.2026, Antonio direkt): das Review-Dokument.**
> Antonio hat ein von der Vorsession erstelltes Review der Seite übergeben
> („Ich möchte, dass du an all den Punkten arbeitest … und zwar autonom")
> und ist gegangen. Umgesetzt sind **alle sechs Befunde aus Teil A und
> elf der dreizehn Roadmap-Punkte**; die vollständige Liste mit den Messungen
> steht in `outputs/review-umsetzung-2026-08-08.md`. Stand danach: **870
> Tests**, alle **14 Prüfungen von `pruefe_portal.py`** grün, **207 crawlbare
> Quellen**.
>
> Gebaut: Ereignis-Bündelung, CTM-Linse mit Konsequenzsatz und Prüflauf,
> Zwei-Minuten-Pfad, Quellen-Reparatur samt Deutschland-Paket,
> Änderungsradar auf 16 Tarifseiten, Lieferzeit-Radar mit eigener Seite,
> Lücken-Analyse, Push-Versand, Verlauf („was wächst, was kippt"),
> Frühwarn-Board, vollständiger Wettbewerber-Steckbrief, Mobil-Navigation
> und die Spalte „Neu seit der letzten Ausgabe".
>
> **Vier Punkte des Reviews haben sich beim Nachmessen als falsch erwiesen** —
> wer sie erneut liest, liest sie mit diesen Korrekturen:
> (1) Telecompetitor ist eine IP-Sperre, kein User-Agent-Filter;
> (2) `schema.org/OfferShippingDetails` liefert im deutschen Telko-Handel
> niemand, die Lieferzeit-Kaskade hängt am Text und am gerenderten DOM;
> (3) die Nullausbeute des MVNO-Themenfelds liegt nicht an fehlenden Quellen;
> (4) das Job-Timeout liegt längst bei 50 Minuten, nicht bei 35.
>
> **Nicht gebaut, mit Grund:** der Archiv-Dialog (RAG braucht einen Dienst
> zur Laufzeit — die Website ist eine Static Site ohne Backend, und genau das
> hält sie wach) und das Kundenstimme-Radar (für fremde Apps gibt es keinen
> zulässigen Zugang, dieselbe Grenze wie bei Trustpilot). Beides steht mit
> Begründung in §6.
>
> **Offen daraus, alles erst nach dem nächsten Actions-Lauf prüfbar:**
> 1. Der **Prüflauf gegen den Originaltext** ist noch nie gegen ein echtes
>    Modell gelaufen. Im Protokoll die Zeile `CTM-Linse:` ansehen: fallen
>    fast alle Sätze, stimmt der Prompt nicht; fällt keiner, ist die Prüfung
>    zu milde.
> 2. Die **Ereignis-Prüfung im Graubereich** (`Ereignis-Pruefung:`): legt das
>    Modell fast alles zusammen, ist die Schwelle zu tief.
> 3. Der **Versand** verschickt ohne die Secrets nichts und schreibt den
>    Grund ins Protokoll — das ist Absicht. Nötig sind `SMTP_HOST`,
>    `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`, `MAIL_TO` und
>    `TEAMS_WEBHOOK`. Trockenlauf:
>    `python -m telco_radar.versand --trocken --erzwinge --zeige`.
> 4. Die **JS-Seiten** von Änderungs- und Lieferzeit-Radar: in Actions
>    rendert Playwright, lokal nicht.
> 5. Die **Vorgabe-Region** (`region:` in `news_sources.yaml`): ob Europa,
>    Lateinamerika, Asien und Afrika jetzt eigene bewertete Meldungen haben.
> 6. **`config/vodafone_hebel.yaml` ist leer ausgeliefert** — zwölf Hebel auf
>    `offen`. Das ist Absicht (§5), aber es ist der eine Punkt, den nur ein
>    Mensch schließen kann: zwölf Zeilen darüber, was Vodafone selbst hat.
>    Solange sie leer ist, sagt die Seite ehrlich „noch nicht erfasst" und
>    behauptet keine Lücke.
>
> **Zuletzt erledigt (08.08.2026, Antonio direkt): Suchfunktion und
> Differenzierung.** Zwei Aufträge in einem: die Suche leitete auf
> `meldungen.html` weiter und zeigte ihre Treffer als graue Textzeilen am
> Seitenfuß („total bescheuert … ich verstehe nicht, warum ich da
> weitergeleitet werde"); die Differenzierung war eine 9060-px-Wand aus 77
> gleich großen Textkärtchen ohne ein einziges Bild („total unübersichtlich …
> viel besser sein analytisch"). Erledigt: `suche.html` als Dossier (Bilanz,
> Verlauf über die Monate, Aufmacher mit Bild, Chronik), Suchindex um die
> Promo-Aktionen und um Bilder erweitert, wortweise Suche mit Rangfolge;
> Differenzierung mit Bildern, Marktbild, Hebel-Erklärung, Gewichtung und
> einem VERTEILTEN statt angehängten Bericht. **707 Tests, alle vierzehn
> Prüfungen von `pruefe_portal.py` grün.** Einzelheiten in §5, Schlussliste
> `outputs/suche-und-differenzierung-2026-08-08.md`.
>
> **Offen daraus, beides erst nach dem nächsten Actions-Lauf prüfbar:**
> (1) die Zeile `Differenzierungs-Bilder:` im Protokoll — lokal bekommen 35
> von 71 Beispielen ein Motiv; (2) der Differenzierungs-Redakteur schreibt
> seit dieser Runde eine neue Gliederung (`## Das Bild` / `## Muster` /
> `## Einordnung`) und ist noch nie gegen ein echtes Modell gelaufen. Kommt
> sie an, verschwindet der zugeklappte Berichtsblock am Seitenende von selbst;
> kommt sie nicht an, steht dort weiter der alte Bericht — dann im Log nach
> `Differenzierungsbericht: Regelbericht` sehen.
>
> **Davor erledigt (08.08.2026): Promo-Seite und
> Wettbewerbsseite.** Fünf Punkte in einem Auftrag — fehlende Bilder auf der
> Promo Übersicht („das wirkt so richtig scheiße"), Reihenfolge nach
> Wichtigkeit der Anbieter, Namen der Wettbewerber prominenter (beide
> Seiten), Wettbewerbsseite kürzer. Alle erledigt, 673 Tests, alle elf
> Prüfungen von `pruefe_portal.py` grün. Einzelheiten in §5, Schlussliste
> `outputs/promo-und-wettbewerb-2026-08-08.md`.
>
> **Offen daraus:** nach dem nächsten Actions-Lauf die Zeile
> `Promo-Bilder:` im Protokoll ansehen — lokal (reines HTTP) bekommen 49 von
> 77 Angeboten ein Motiv, mit den JS-gerenderten Seiten sollten es mehr
> sein. Und: die Dubletten in `promo_db.json` werden nur beim Rendern
> zusammengefasst; sie an der Wurzel zu entfernen wäre eine Datenmigration
> über den Store, keine Anzeigefrage.
>
> **`AUFTRAG_PORTAL_WELLE2.md` ist abgearbeitet** (Schlussliste:
> `outputs/portal-welle2-2026-08-07.md`).
>
> **Danach, am 07.08.2026, zwei Aufträge von Antonio direkt** — beide
> erledigt, alle elf Prüfungen von `scripts/pruefe_portal.py` grün,
> 495 Tests:
>
> 1. **„Diese Woche"**: die sechs Ressortblöcke zwischen Überblick und
>    Bericht sind weg („doppelt gemoppelt" — dieselbe Gliederung steht
>    vollständig auf `meldungen.html`), ebenso der Vorspann „Worum es diese
>    Woche geht". Die Seite ist von 11 498 auf 9 782 px geschrumpft, keine
>    Meldung ist dabei verloren gegangen.
> 2. **Promo Übersicht neu gebaut** (siehe §5): Kampagnenmotive statt
>    Screenshots, je Angebot zugeordnet, und eine Kartenform statt vier
>    Darstellungen. Der Screenshot-Pfad
>    (`capture_hero_image`/`_dismiss_cookie_banner`) ist ersatzlos entfernt —
>    damit erledigt sich auch der offene Punkt „zwei Screenshots zeigen ein
>    Cookie-Banner", er kann nicht wiederkommen.
>
> **Am 08.08.2026 der dritte Auftrag von Antonio direkt: die Promo-Quellen in
> die Breite.** Nicht mehr Unternehmen ("das reicht an Unternehmen"), sondern
> mehr Quellen JE Unternehmen, damit wirklich jede laufende Aktion erfasst
> wird. Erledigt: 15 → 59 abgefragte Seiten, Schema/Pipeline/Store auf Seiten
> statt Marken umgestellt, zwei neue Werkzeuge (Sucher + Abnahme-Check), 532
> Tests, alle elf Prüfungen von `pruefe_portal.py` grün. Einzelheiten in §5
> unter "Eine Marke, mehrere Aktionsseiten"; Schlussliste
> `outputs/promo-quellen-2026-08-08.md`. **Offen daraus: nach dem nächsten
> Actions-Lauf prüfen, ob die vier Telekom- und drei
> mobilcom-debitel-Seiten dort Text liefern** — beide sind auf JS-Rendering
> angewiesen und lokal nicht abnehmbar.
>
> Offen daraus: **die Bildausbeute hängt am JS-Rendering.** Lokal (reines
> HTTP, Chromium kommt in der Sandbox nicht ins Netz) liefern Telekom,
> mobilcom-debitel und klarmobil null Bildkandidaten, Lidl Connects
> Bild-URLs antworten mit HTML. In Actions rendert Playwright diese Seiten;
> **nach dem nächsten Lauf gehört nachgesehen, wie viele Angebote dort ein
> Motiv bekommen** (`promo_bilder`-Zeile im Actions-Log).
>
> **`AUFTRAG_NACHRICHTENPORTAL.md` ist abgearbeitet**
> (Schlussliste: `outputs/nachrichtenportal-2026-08-06.md`). Alle acht
> Prüfungen von `scripts/pruefe_portal.py` sind grün, 458 Tests laufen, die
> Fassung ist live verifiziert (byte-identisch mit dem geprüften Commit).
> Offen bleibt daraus ein Punkt: der **Platzbedarf im Repo** — rund 17 MB
> Bilder je Lauf in zwei Kopien, hochgerechnet ~1,5 GB im Jahr in der
> git-Historie. Die Lösung wäre, den Zwischenspeicher abzuschaffen und
> `site/images/` als einzigen Ort zu führen; das dreht aber die Grenze
> „Pipeline-State ≠ Site-Ausgabe" um und ist eine Architekturentscheidung,
> keine Aufräumarbeit.
>
> **Am 07.08.2026 (abends) der große Ausbau-und-Beruhigungs-Auftrag von
> Antonio direkt** — fünf Pakete, alle erledigt (Schlussliste:
> `outputs/marktrecherche-ausbau-2026-08-07.md`, 656 Tests, alle elf
> Prüfungen von `pruefe_portal.py` grün, jedes Paket ein eigener Commit):
>
> 1. **Beruhigung**: kein Satz erklärt die Bedienung, eine Zahl je Ort,
>    einheitliche Etiketten (§5 „Beruhigungsregeln").
> 2. **Differenzierung neu** als Karten-Radar; dabei Merge der zwei
>    Speicher — 20 Kurator-Beispiele waren nie sichtbar gewesen (§5).
> 3. **Promo Übersicht dritter Umbau**: je Marke ein Block, vier
>    Bildfehler an der Wurzel (§5).
> 4. **Highlight-Themen**: Erkennungs-Agent + temporäre Seiten
>    `thema/<slug>.html` (§5). **Offen: der Themen-Agent ist noch nie
>    gegen ein echtes Modell gelaufen** — nach dem nächsten Actions-Lauf
>    im Log prüfen (`Highlight-Themen:`-Zeile), ob er Firmen-Cluster
>    („Deutsche Telekom") wirklich verwirft und die Titel taugen.
> 5. **Wettbewerbsseite** `wettbewerb.html` mit Monats-Chronik (§5).
>
> Offen aus dem Auftrag außerdem: die Treffer-Karten der Archivsuche
> kürzten Überschriften JS-seitig mit „…" (app.js, `TelcoSearch`) —
> **erledigt am 08.08.2026** im Zuge des Suchseiten-Umbaus: die Hervorhebung
> markiert jetzt jedes Suchwort und kürzt nichts mehr.
>
> **Als Nächstes** `AUFTRAG_1000_QUELLEN_WELLE3.md` (Quellenausbau) —
> beziehungsweise die vier Schritte aus §9 unten, deren erster (Vorgabe-Region
> für Fachpressequellen) unverändert offen ist.

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

1. ~~**Vorgabe-Region für Fachpressequellen.**~~ **ERLEDIGT am 08.08.2026.**
   Lauf #75 schloss Europa mit null bewerteten Meldungen ab, während „Global"
   62 von 92 bekam. `Source` trägt jetzt ein Feld `region`, 27 regionale
   Feeds sind zugeordnet (Europa 11, Asien 5, Lateinamerika 5, Afrika &
   Naher Osten 5, Nordamerika 1), und ein Betreibername in der Überschrift
   schlägt die Vorgabe weiterhin — eine Verizon-Meldung in einem deutschen
   Feed gehört nach Nordamerika. Eine Region, die es nicht gibt, wird beim
   Laden verworfen und gemeldet. **Nach dem nächsten Lauf nachsehen, ob die
   Regionsteile jetzt gefüllt sind.**
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

- ~~E-Mail-/Teams-Versand~~ **gebaut am 08.08.2026** (`versand.py`) — Mail montags mit dem Zwei-Minuten-Pfad, Teams nur für die Ausnahme. Es fehlen nur noch die Secrets.
- Firecrawl/Crawl4AI als Fetcher für JS-Newsrooms (AT&T, Singtel, Telia, …)
- Semantisches Dedup (Embeddings), um dieselbe Story aus mehreren Quellen zu mergen
- Tarif-/Preisseiten-Diffing als dritte Signalebene
- ~~Trend-Charts über mehrere Wochen~~ **gebaut am 08.08.2026** (`report/verlauf.py`, Abschnitt „Was wächst, was kippt" auf der Differenzierungs-Seite)
- Feedback der Vodafone-Kollegin einarbeiten (steht noch aus)
- Migration auf Vodafone-Infra, falls gewünscht (Runner braucht nur Python + HTTPS)
