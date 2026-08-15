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
             + GERAETE- UND PREISRADAR auf den Produktseiten von Handel,
               Netzbetreibern und Discountmarken (collect/geraete/;
               geraete_pipeline.py; State: data/state/geraete_db.json +
               geraete_preise.jsonl). Die einzige Stufe mit einer echten
               robots.txt-Pruefung - samt Crawl-delay UND Besuchszeit
2. DELTA     Seen-Store + Freshness-Filter → nur NEUE Items
             (src/telco_radar/dedupe.py; State: data/state/seen.jsonl)
2b. CLUSTER  Ereignis-Buendelung: dieselbe Sache aus drei Quellen ist EINE
             Meldung (analyze/clustering.py; State: data/state/clusters.jsonl)
3. ANALYZE   1 Analyst-Agent pro Region UND pro Themenfeld, Batches à 15
             Items (parallel, analyst_batch_workers), 8k Tokens.
             Themenfelder bekommen TECH_ANALYST_SYSTEM statt ANALYST_SYSTEM -
             ein Chiphersteller ist kein Wettbewerber.
             Der Analyst sieht seit dem 15.08.2026 den ARTIKELTEXT
             (analyst_text(), 2500 Zeichen), nicht summary[:300] - bei 52
             der 164 Quellen war das vorher die Ueberschrift allein
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
5b. UEBERSETZUNG  Fremdsprachige Meldungen bekommen eine VOLLSTAENDIGE
             deutsche Fassung als eigene statische Seite
             (src/telco_radar/uebersetzung/; State:
             data/state/uebersetzungen.jsonl). Sie steht VOR dem Rendern
             (der rote Link muss auf die Karte) und rechnet ihr Budget
             deshalb gegen die RESTZEIT DES JOBS. Sprache IMMER auf dem
             Fliesstext, nie auf der Ueberschrift.
             Sie laeuft auf den BERICHTETEN Meldungen (berichtete_items()
             aus alle_highlights), nicht auf new_items - eine Uebersetzung
             zu einer Meldung ohne Karte hat keinen Ort fuer ihren Link
6. VERSAND   Montags der Zwei-Minuten-Pfad per Mail, Teams nur fuer die
             Ausnahme (versand.py; State: data/state/versand.json)
7. NEWSLETTER Ein AUSSPIELKANAL, kein vierter Anwendungsfall - und er laeuft
             NICHT in diesem Job. radar.yml schickt am Ende nur ein
             repository_dispatch (Datum + Commit-SHA, continue-on-error) an
             ein leeres Inbox-Repo; Versand und Abonnentenliste liegen im
             privaten Repo telco-radar-mail (Buendel in mail_repo/). Der
             Radar-Lauf lag am 6.8. bei 27,4 von 35 Minuten - ein
             gedrosselter Versand an 200 Empfaenger dauert allein sieben,
             und dann faellt nicht der Newsletter aus, sondern der BERICHT.
             Die LOGIK steht trotzdem hier (src/telco_radar/newsletter/,
             scripts/newsletter/): eine Kopie der Filter-Engine im privaten
             Repo wuerde driften, und dann schickt die Mail etwas anderes,
             als die Website zeigt.
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
| `config/geraete_quellen.yaml` | **23 beobachtete Anbieter** des Geraeteradars in drei Ebenen (Handel / Netzbetreiber / Discount). Jede Zeile ist gemessen, nicht geraten: `methode` und `grund` geben das Messergebnis vom 10.08.2026 wieder. Ein Anbieter ohne Adapter steht mit seinem Grund da und verschwindet NICHT |
| `config/geraete_katalog.yaml` | Die **verfolgten Modelle** - nicht der Markt. `vorgaenger` ist das Feld, an dem die ganze Lifecycle-Auswertung haengt; ein leeres `marktstart` schaltet die Nachfolger-Analyse fuer dieses Geraet ab (ein geratenes Datum waere schlimmer) |
| `config/newsletter.yaml` | **Der Katalog der Anmeldeseite**: die vier Filterachsen und die Grenzen. Sein Kopf trägt die Verknüpfungsregel ausgeschrieben — UND zwischen den Dimensionen, ODER innerhalb, **leer heißt ALLES**, Stichwörter additiv. Ein umbenannter `key` ist ein stillschweigend gelöschter Filter in bestehenden Abos |
| `content/legal/*.md` | Impressum und Datenschutzerklärung als Text, getrennt vom Code. Ein Platzhalter `{{...}}` ist eine **offene Stelle**, die auf der Seite sichtbar wird und die Newsletter-Schwelle geschlossen hält. Seit 12.08.2026 ist keiner mehr offen — `tests/test_newsletter_seite.py` hält das gegen die echten Dateien |
| `content/consent_texts/<datum>.md` | Die Fassungen des Einwilligungstextes. Der Hash landet im Abo-Datensatz — eine Aufsichtsbehörde fragt nach dem Wortlaut von DAMALS, nicht dem von heute |
| `mail_repo/` | **Kein laufender Code**, sondern der Inhalt der zwei privaten Repos (`telco-radar-mail`, `telco-radar-inbox`) samt Einrichtungsanleitung. Die Workflows dort enthalten keine Logik; sie checken dieses Repo aus |
| `config/farben.yaml` | Farbschreibweise -> kanonische Farbe. Eine unbekannte Farbe wird BEHALTEN und nicht geraten; der Farbbericht am Fuss von `/geraete.html` ist die Arbeitsliste fuer diese Datei |
| `data/state/geraete_db.json` | Aktueller Stand je Listung, mit Zwei-Stufen-Auslistung wie `promo_db.json`. Nichts wird geloescht - genau daraus entsteht die Listungsdauer |
| `data/state/geraete_preise.jsonl` | NUR die Aenderungspunkte des Preises. Ein unveraenderter Preis schreibt keine Zeile; die rechte Kante jeder Kurve ist `last_verified` in der DB |
| `config/lieferzeit_warenkorb.yaml` | Der feste Warenkorb des Lieferzeit-Radars: Produkte mit EINER Variante, eine Test-PLZ, je Anbieter das Ident-Verfahren |
| `config/fruehwarnung.yaml` | Fuenf CTM-Kernfragen mit falsifizierbaren Indikatoren. Der Wert steckt darin, dass sie VORHER feststehen |
| `data/state/clusters.jsonl` | Ereignis-Gedaechtnis. ID aus der kanonischen URL, nie aus dem Titel |
| `data/state/tarif_snapshots.json` | Die zuletzt gesehene WERTMENGE je Tarifseite (nicht der Text) |
| `data/state/lieferzeit.json` | Zeitreihe je Produkt und Anbieter, mit Methode und Belastbarkeit je Messpunkt |
| `data/state/versand.json` | Zustellbuch — was schon hinaus ist. Ohne das schickt ein zweiter Lauf am selben Tag dieselbe Mail |
| `data/state/tarife.jsonl` | Zeitreihe der Tarifdokumente. Ein Stand je Zeile; ein unveraendertes Dokument erzeugt KEINEN neuen Satz, nur ein neues `abgerufen_am` |
| `data/state/ct_seen.jsonl` | Bekannte Subdomains je Domain. Klartext statt Hash — hier sind es Hunderte, nicht Millionen, und der Klartext ist die halbe Diagnose |
| `data/state/uebersetzungen.jsonl` | Die fertigen Uebersetzungen, eine je Zeile. Schluessel ist `Item.id` **plus** ein Hash des Quelltexts. **Es wird nie etwas geloescht** — ein Archivbericht verlinkt seine Uebersetzung noch in einem Jahr. Die HTML-Seiten entstehen bei jedem Rendern daraus und werden NICHT einzeln versioniert |
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
| `geraete.html` **Geräte** (nicht verlinkt) | „Was haben die anderen im Regal, und was kostet es?" | Preis-Positionskarte als **gerechnetes SVG** mit ZWEI Umschaltern (Ansicht: Spalten = Hersteller / = Anbieter · Darstellung: Preisbänder / Punkte), alle vier Flächen vorgerechnet, kein Reload; darunter dieselben Zahlen als aufklappbare Tabelle. Dazu SKU-Matrix Modell × Anbieter, Lifecycle (Verweildauer, Preisverfall, Nachfolger-Effekt, Portfolio-Tiefe), Datenbasis und Lücken. Speist sich aus `data/state/geraete_db.json` + `geraete_preise.jsonl` |
| `geraete-quellen.html` (nicht verlinkt) | „Wer liefert, wer nicht, warum?" | Jeder der 23 konfigurierten Anbieter mit Ebene, Beschaffungsmethode, Stand und Grund. Marken ohne Hardware-Vermarktung stehen als EINE Zeile, nicht als leere Kachel |
| `uebersetzung/<id>.html` (nicht verlinkt) | „Was steht da eigentlich?" | Die **vollständige** deutsche Fassung eines fremdsprachigen Artikels. Kein Nav-Eintrag: erreichbar über den roten Link der Meldungskarte. Oben und ohne Scrollen: „Maschinelle Übersetzung", die Ausgangssprache und der Link zum Original — die Übersetzung tritt NEBEN das Original, nicht an seine Stelle. Dateiname ist die `Item.id` (SHA-256 über die normalisierte URL), damit ein Archivbericht in einem Jahr noch trifft |
| `transparenz.html` | „Kann ich dem Ding trauen?" | Laufprotokoll **und** Quellenbestand, dazu die Erklärung der CTM-Stufen und der Sicherheitsskala; seit 11.08.2026 der **Newsletter-Abschnitt** (nur Zahlen, Warnung ab 80 % des Tageskontingents) |
| `newsletter.html` **Newsletter** (nicht verlinkt) | „Schick mir das per Mail" | Vier Filterachsen plus eigene Stichwörter mit Trefferzahl-Vorschau, Einwilligungstext im Wortlaut. **Verlinkt erst, wenn Impressum und Datenschutzerklärung vollständig sind** — siehe Veröffentlichungsschwelle |
| `newsletter-bestaetigt.html` / `-abgemeldet.html` (nicht verlinkt) | „Hat es geklappt?" | Zwei **statische** Seiten ohne den Signup-Dienst. Render Free schläft nach 15 Minuten; wer im kalten Zustand auf den Abmeldelink klickt, darf nicht vor einem Spinner stehen — und es ist der EINZIGE Abmeldeweg |
| `impressum.html` / `datenschutz.html` | „Wer ist das, und was passiert mit meiner Adresse?" | Aus `content/legal/*.md` über `report/rechtstexte.py`. Eine offene Stelle im Text (`{{ANSCHRIFT}}`) steht sichtbar OBEN auf der Seite und hält die Newsletter-Schwelle geschlossen |
| `thema/<slug>.html` (temporär) | „Was ist an diesem Ereignis dran?" | Highlight-Themenseiten, siehe unten |

**Die Positionskarte des Geräteradars ist am 11.08.2026 neu gebaut worden**
(`report/geraete_karte.py`). Die erste Fassung stapelte Etiketten je Spalte
sequenziell mit 14 px Mindestabstand nach unten, während der Punkt auf seinem
Preis blieb: gemessen **181 px** Versatz in der Hersteller- und **235 px** in
der Anbieteransicht, 87 von 94 Etiketten weiter als drei Prozent daneben. Wer
die Grafik las, wie man Grafiken liest, las um den Faktor sieben falsch.
Dahinter der tiefere Fehler: **60 der 85 Kreise lagen deckungsgleich**, weil je
FARBVARIANTE ein Punkt gezeichnet wurde — es gab 25 unterschiedliche
Koordinaten. Drei Regeln tragen die Neufassung:

| Regel | Warum |
|---|---|
| **Die Y-Achse gehört dem Preis.** Ausgewichen wird nur nach RECHTS; passt ein Etikett nicht in `MAX_VERSATZ` (12 px), wird es weggelassen | Es gibt keinen Codepfad mehr, der `label_y` unabhängig von `cy` setzt. Eine Lücke ist ehrlich, eine Verschiebung ist eine Falschaussage |
| **Gezeichnet werden Preispunkte, keine SKUs**: (Modell, Speicher, Laden, **Zustand**) | Farbe ist keine Preisdimension. Der ZUSTAND muss in den Schlüssel: sonst schluckt ein refurbished-Preis den Neupreis desselben Geräts |
| **Was im Zeichenbereich steht, trägt eine Preisaussage** (`gr-etikett`); was unter der Achse steht, nicht (`gr-bandname`) | Daran hängt der Abnahmetest. BEIDSEITIG geprüft, sonst wäre die Ausnahme ein Schlupfloch |

**Zwei Darstellungsformen, Preisbänder als Standard** — aus 38 Apple-Punkten
werden fünf Bänder. Der Formschalter ist eine zweite Schachtelungsachse
(`.gr-flaeche`) mit EIGENER Klasse: mit derselben zählte
`test_beide_ansichten_stehen_fertig_im_html` vier ausgeblendete Ansichten
statt einer und fiel aus dem falschen Grund. Der dritte Schalter (ohne/mit
Vertrag) braucht dadurch keine Zeile JavaScript, nur ein weiteres Attribut.

**Breite vor Höhe:** 1180 statt 980 px (die Seite gibt 1184 her). Das hebt die
Chipbahnen je Spalte von drei auf vier und spart 360 px Höhe. Mobil wird
**gerollt statt gestaucht** — die alte Regel `.gr-etikett{font-size:8px}` ergab
auf einem 390-px-Telefon real 2,7 CSS-Pixel.

**mobilcom-debitel und freenet sind derselbe Laden** (`shop`/`anzeige` in
`geraete_quellen.yaml`). Als zwei Spalten verglich die Karte einen Laden mit
sich selbst; die Veröffentlichungsschwelle zählt deshalb **Läden, nicht
Marken**.

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

**Der Rang schlägt den Faden** (15.08.2026). Bis dahin wählte `_faden()`
allein nach Wortüberschneidung, ohne jede Untergrenze — und konnte damit
eine beliebig schwach bewertete Meldung auf den Aufmacher ziehen. An der
Ausgabe vom 14.08. gemessen: Aufmacher war „T-Mobile wirbt mit
Studienstart-Ratgeber" (Kontext, Priorität 2), während „T-Mobile verschenkt
Pixel 11 Pro XL" (Übertragbar, Priorität 5) als Textzeile daneben stand.
Antonio: *„die ordnung stimmt überhaupt nicht, die wichtigsten artikel
sollen auch an erster reihe stehen."* Jetzt wählt der Faden nur unter
Meldungen, die den **besten noch freien Rangschlüssel** dieser Bildstufe
erreichen (`_rangschluessel` = CTM-Bezug vor Priorität): er entscheidet,
WELCHE der gleichrangigen Geschichten führt, und kann keine schwächere
hochziehen. Die Latte wird **vor jedem Platz neu gemessen** — einmal vorab
gerechnet wäre sie nach dem ersten Zugriff veralteter Rang, und die zweite
Reihe bliebe halb leer.

**Die dritte Reihe zieht wieder vor der Digest-Spalte** (15.08.2026) — und
das dreht die Vergabereihenfolge von K2 (09.08.2026) zurück. Damals zog die
Spalte „Was wichtig ist" zuerst, weil die vier Bildkacheln jede Meldung mit
direktem Portfoliobezug abräumten. Der Preis war, dass die HAUPTSPALTE
systematisch die schwächeren Meldungen bekam: in der Ausgabe vom 15.08.
standen in den vier Kacheln vier Meldungen mit Priorität 2, während fünf
mit Priorität 3 als Textzeilen danebenlagen — und **jede Karte trägt ihre
Priorität als sichtbares Etikett**, das war also kein Feinheitsproblem sondern
ein Widerspruch, den man auf der Seite lesen konnte. Der Grund von damals
trägt nicht mehr: die Meldungen mit direktem Bezug holt inzwischen der
Kurzpfad an die Spitze DERSELBEN Spalte, und `gesperrt` hält sie aus dem
Digest heraus. Zwei Regeln tragen die Neufassung:

| Regel | Warum |
|---|---|
| Die Titelseite vergibt in **einer** Rangfolge: Aufmacher → zweite Reihe → dritte Reihe → „Was wichtig ist" | Die drei Bildstufen stehen untereinander in derselben Spalte. Was untereinander steht, muss in einer Rangfolge stehen |
| Die dritte Reihe greift **`streng`** zu (Bild zwingend), erst nach der Spalte füllt sie notfalls auf | Ohne das holt sie sich die hoch bewerteten BILDLOSEN Meldungen in eine Kachel, die dann leer bleibt — und nimmt sie der Spalte weg. Ein fehlendes Bild ist keine Abwertung: solche Meldungen gehören in die Textspalte, und dort nach oben |

Wahrheitstests: `test_der_faden_zieht_keine_schwaechere_meldung_nach_vorn`,
`test_die_bildstufen_stehen_in_der_rangfolge`,
`test_die_spalte_nimmt_den_bildstufen_keine_bessere_meldung_weg`. Fallstrick
beim Bauen solcher Fälle: **„Anbieter 701" und „Anbieter 702" sind für
`_kennwoerter` DERSELBE Absender** (die Ziffern sind zu kurz für das
Wortmuster) — dann greift der Absenderdeckel statt der Rangfolge, und der
Test misst etwas anderes, als er behauptet.

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

**Die Navigation hat FÜNF feste Einträge** (Diese Woche, Meldungen,
Differenzierung, Wettbewerb, Quellen) **plus „Geräte", sobald die Daten die
Schwelle nehmen**. `tests/test_suche_page.py` nagelt die fünf fest — eine
Navigation wächst sonst zurück, und genau davon kam dieses Projekt.

**Der sechste Eintrag schaltet sich selbst** (11.08.2026) — und ist im
Moment AUS, weil nur zwei Läden liefern. Genau das ist der Punkt der
Mechanik: die Entscheidung steht als Zahl im Code, nicht als Handgriff in der
Vorlage, und sobald ein dritter Laden liefert, trägt sich die Seite selbst
wieder ein. Bis dahin stand
die Veröffentlichungsschwelle **nur in einem Test**, und das war der Fehler
daran: ein Test kann keine Navigation schalten. Die Geräteseite stand am
10.08. fertig, geprüft und live — und war für jeden Leser unauffindbar,
weil das Eintragen Handarbeit blieb. Antonio: *„Ich sehe auf der normalen
Hauptseite gar nichts, keine Unterseite gar nichts."* Jetzt rechnet
`geraete_view.schwelle_erreicht()` die Schwelle, `render_site()` setzt
daraus das Jinja-Global `geraete_verlinkt`, und `base.html.j2` fragt es ab.
**Die Aufbereitung der Gerätedaten steht deshalb GANZ OBEN in
`render_site()`, vor der ersten gerenderten Seite** — sie entscheidet über
einen Navigationseintrag, und die Navigation steht auf jeder Seite. Wer sie
zurück zu ihrer eigenen Seite schiebt, bekommt eine Startseite ohne den
Eintrag und eine Geräteseite mit ihm.

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
> **Newsletter-Seite:** Impressum **und** Datenschutzerklärung vollständig,
> also ohne offenen Platzhalter (`rechtstexte.vollstaendig()`). Die zweite
> Schwelle, die der CODE rechnet, und die einzige, bei der es nicht um
> Aussagekraft geht, sondern um Art. 13 DSGVO: die Information ist zum
> ZEITPUNKT der Erhebung fällig, nicht irgendwann. Unterhalb der Schwelle
> wird die Seite gebaut, nennt ihre Lücke, hat einen abgeschalteten
> Absendeknopf und keinen Navigationseintrag. **Seit dem 12.08.2026 ist sie
> AN**: Antonio hat die ladungsfähige Anschrift geliefert (`c/o Vodafone
> GmbH, Ferdinand-Braun-Platz 1, D-40549 Düsseldorf`, unter seinem Namen —
> er bleibt Anbieter, das Portal bleibt privat betrieben). Die Navigation
> hat damit **sechs** Einträge.
>
> **Die Schwelle rechnet aber nur die Rechtstexte, nicht den Dienst** — und
> das ist Absicht (Art. 13 DSGVO, nicht Aussagekraft). Solange
> `newsletter_dienst_url` leer ist, steht die Seite also in der Navigation
> und kann trotzdem nichts entgegennehmen. Damit das niemanden Arbeit
> kostet, sagt sie es **oben** (`{% elif not dienst_da %}` in
> `newsletter.html.j2`): der Hinweis aus `app.js` sitzt am Absendeknopf und
> stand damit bei 1918 px auf einer 2145 px hohen Seite — nach vier
> Filtern, der E-Mail-Adresse und der abgehakten Einwilligung. Solange die
> Seite unverlinkt war, fand sie ohnehin niemand; mit dem
> Navigationseintrag wird der Weg begangen.
> **Geräteseite:** **drei** Anbieter mit Daten, zwei Hersteller in der
> Positionskarte, zwanzig SKUs — und sie ist die einzige, deren Schwelle der
> CODE rechnet (`geraete_view.SCHWELLE_*` und `schwelle_erreicht()`), nicht
> nur ein Test. Zwei Tests messen beide Zweige: unterhalb nicht verlinkt,
> oberhalb auf JEDER Seite verlinkt.
>
> Die Anbieterschwelle stand am 11.08.2026 kurzzeitig auf **zwei**, mit der
> Begründung, die Seite beantworte ihre erste und zweite Frage („was führt
> der Wettbewerb", „wo steht ein Gerät im Preis") auch so vollständig.
> **Antonio hat das kassiert, nachdem er die Seite live gesehen hatte** —
> und die Zahl gibt ihm recht: von den zwei „Anbietern" trägt einer 84 von
> 85 Listungen. Die dritte Frage („was kostet dasselbe Gerät bei wem") ist
> die, wegen der die Seite existiert, und mit einem echten Laden kann sie
> niemand beantworten. Eine Seite, die ihre Lücke beziffert, lügt zwar
> nicht — aber eine Marktübersicht, die den Markt nicht zeigt, gehört
> deshalb noch lange nicht in die Navigation.

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

**Abnahme der Seite:** `python scripts/pruefe_portal.py` misst **fünfzehn**
Kriterien gegen die wirklich gerenderte Seite (16 Zeilen mit den
Unterkriterien), fünf davon mit echtem
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
Seit dem 11.08.2026 dazu Kriterium **12** (der Zeitungskopf, siehe unten).

**Der Name ist „Vodafone Product and Services Insights"** (11.08.2026, vorher
„Vodafone Insights"). Er steht an elf Stellen — Seitentitel je Unterseite,
Zeitungskopf, `aria-label`, Fußzeile, die Weiterleitungsseiten in `html.py` —
und `tests/test_marke.py` hält sie zusammen; ein halber Rename sieht auf der
Startseite fertig aus und fällt sonst erst auf der Tarifseite auf.

**Der längere Name ist ein Geometrieproblem, kein Textproblem.** In EINER
Schriftgröße ist er **475 statt 214 px** breit. Die rechte Spalte der
Kopfleiste (Anwendungsfälle plus Suchzeile) belegt 483 der 1184 px, und weil
die linke leer ist, schiebt jedes zusätzliche Wort den Kopf nach links: er saß
**169 px** aus der Mitte (vorher 38) und lief auf 390 px Breite **61 px aus
dem Bild** — die ganze Seite ließ sich seitwärts schieben. Zwei Stellschrauben,
beide gemessen: der Mittelteil des Namens steht kleiner (`.brand-zusatz`,
`.58em` — eine Zeile, dieselbe Serife, derselbe kursive Akzent am Ende), und
die Suchzeile ist **oberhalb von 900 px** von 210 auf 160 px verschmälert (ihr
Platzhalter misst 108 px und braucht mit dem Knopf 134). Ergebnis: 373 px
breit, Versatz 67 px, mobil 307 px und kein Seitwärtslauf. **Wer die Größe des
Kopfes anhebt, misst beides nach** — Kriterium 12 prüft auf 1440 UND auf
390 px.

Der interne Projektname **„Telco Radar" bleibt** — er steht im Foliensatz
(`report/folien.py`) und im Mailversand (`versand.py`), also dort, wo nicht die
Website spricht.

## 6. Bekannte Fallstricke (alle in Session 1 gelernt!)

- **State nie lokal committen:** Nach lokalen Testläufen `data/state/` +
  `data/reports/` NICHT einchecken, sonst findet der Actions-Lauf „0 neue
  Items". Baseline-Reset = die vier State-/Report-Dateien per `git rm`
  entfernen, pushen, Workflow triggern.
- **Anthropic 529 (overloaded):** kommt vor; llm.py hat 5 Retries mit bis zu
  45s Backoff, Analysten-Batches werden übersprungen statt zu crashen, der
  Editor fällt notfalls auf einen Digest zurück. Ein Lauf dauerte deshalb
  schon mal 24 min. **„Normal sind 7–8 min" stand hier bis zum 15.08.2026 und
  ist um eine Größenordnung falsch** — mit 199 Quellen und ~900 neuen
  Meldungen braucht ein vollständiger Lauf rund **80 Minuten** (14.08.2026:
  80,2 min). Die Zahl stammt aus der Zeit mit 85 Quellen und ist nie
  mitgewachsen; wer Laufzeit beurteilt, liest `run.phases` aus dem
  Berichts-JSON.
- **Push→Hook-Race:** Render klont sofort; der Workflow wartet 15s zwischen
  git push und Hook-Curl. Beim manuellen Nachdeployen dran denken.
- **Eine Nebenstufe VOR dem Rendern kann den ganzen Lauf kosten — ihr
  eigenes Zeitbudget schützt nicht.** Lauf 31422689829 (10.08.2026): der
  Kernlauf war nach 44:39 fertig, die Geräte-Nebenstufe startete mit zehn
  Minuten eigenem Budget in einen Job, der noch fünf hatte, und das
  50-Minuten-Timeout kam mitten in ihr. Weil sie vor `render_site()` und dem
  Commit steht, wurde von 45 erfolgreichen Minuten **nichts** veröffentlicht:
  kein Bericht, keine Website, kein Deploy — und ein Timeout ist in GitHub ein
  „cancelled", kein „failed", der Lauf sieht also nicht einmal rot aus. Ein
  Budget muss gegen die **Restzeit des Jobs** rechnen, nicht gegen sich
  selbst: `pipeline.geraete_budget()` tut das, zieht eine Reserve fürs
  Veröffentlichen ab und lässt die Stufe unter vier Minuten Rest gar nicht
  erst anlaufen. Die Geräteststufe ist im Wochenlauf seitdem **aus**
  (`geraete_enabled: false`) — sie hat mit `geraete.yml` einen eigenen
  täglichen Job, der zusätzlich im Besuchsfenster von medimax.de und ep.de
  liegt. **Wer `timeout-minutes` in `radar.yml` ändert, ändert
  `job_frist_sekunden` mit** (ein Test hält beides gegeneinander).
- **`render_site()` ohne `cfg` rendert eine stillschweigend halbe Seite.**
  Die Signatur ist `render_site(site_dir, reports_dir, cfg=None)`, und ohne
  den dritten Parameter verliert `transparenz.html` seinen kompletten
  Quellenbestand (109 Operator-Zeilen) und `wettbewerb.html` den halben
  Inhalt — ohne Fehler, ohne Warnung. Wer die Seite von Hand neu rendert,
  macht es wie `pipeline.py:1063`: mit `load_config(root)`.
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
- **Eine Breite, die in der Sandbox gemessen wurde, ist die Breite der
  RÜCKFALLSCHRIFT.** Google Fonts laden hier nicht, in GitHub Actions schon.
  Der Zeitungskopf war auf 307 px bei 390 px Bildbreite kalibriert — mit
  echter Source Serif 4 lief er waagerecht aus dem Bild, und CI-Lauf #159 auf
  `main` fiel deshalb durch (`test_keine_seite_rollt_waagerecht`, Schuldige:
  `.brand`, `.brand-name`, `em`, `.topbar-right`). **Eine Kalibrierung auf
  eine Schrift ist keine Lösung, sondern eine Wette.** Der Kopf bricht auf
  dem Telefon jetzt um (`white-space:normal`), damit seine Mindestbreite nur
  noch am längsten Wort hängt; `min-width:0` nimmt Grid- und Flex-Kindern das
  voreingestellte `min-width:auto`. Der Regressionstest misst deshalb keine
  Breite, sondern eine Eigenschaft: er verbreitert den Namen per
  `letter-spacing` und prüft, dass nichts überläuft — ein Test, der die echte
  Schrift bräuchte, wäre hier grün und in CI rot.
- **Ein Test, dessen Ergebnis vom Datum abhängt, meldet die nächste
  Mitternacht statt den nächsten Umbau.** Am 12.08.2026 fiel
  `test_der_waechter_laeuft_vor_der_ersten_zustellung` durch, ohne dass sich
  eine Zeile geändert hatte: die 279 Sendeprotokoll-Einträge trugen den 11.,
  und `heute_versendet()` zählt zu Recht den ZUSTELLTAG. Zwei
  Vorschau-Tests hatten dieselbe Zeitbombe — sie messen die letzten 30 Tage
  gegen die Berichte im Repo, und dreißig Tage nach dem letzten Lauf fände
  ein frischer Checkout dort nichts. **Jede Funktion dieses Projekts, die
  `date.today()` kennt, nimmt deshalb ein `heute=` entgegen; ein Test, der
  es nicht mitgibt, prüft die Uhr.**
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
- **HTTP 402 ist so endgültig wie ein falscher Schlüssel — und war es im Code
  nicht.** Am 15.08.2026 war DeepSeeks Guthaben **26 Minuten nach dem Start**
  aufgebraucht. Weil 402 nicht in `_FATAL_STATUSES` stand, lief es durch den
  Wiederholungspfad wie ein vorübergehender Kapazitätsengpass:
  **1245 Wiederholungen** über die restlichen zwei Stunden, 45 gescheiterte
  Analysten-Stapel, **20 von 810 Meldungen bewertet**, Editor im
  Notfall-Digest, 0 Übersetzungen (allein dort 32 Versuche je Artikel und
  889 s). Der Lauf dauerte **151,7 statt 80 Minuten** — und sah dabei aus wie
  eine dünne Nachrichtenwoche. Ein leeres Konto wird beim 32. Versuch nicht
  voller; dieselbe Lehre wie bei `_is_daily_quota`. 402 wird jetzt als
  `LLMModelUnavailable` geworfen, **nicht** als `LLMFatalError`: ein leeres
  Guthaben ist eine Ablehnung des ANBIETERS, kein defekter Request, also darf
  die Kette den nächsten Anbieter fragen und `dead_models()` bringt den Befund
  auf `transparenz.html`. Drei Tests in `tests/test_llm_retry_policy.py`.
- **Die Laufzeit eines Laufs sagt nichts, solange die Phasen nicht
  danebenstehen.** Am 15.08. lag der Verdacht auf dem längeren
  Analysten-Text; gemessen kostete er **2,5 Minuten** („Bewerten &
  Schreiben" 16,6 gegen 14,1 min bei mehr Text und weniger Meldungen). Die
  70 Minuten Aufschlag waren die 402-Wiederholungen. Und die in dieser Datei
  jahrelang wiederholte Zahl „normal sind 7–8 min" ist **falsch**: der
  Referenzlauf vom 14.08.2026 brauchte **80,2 Minuten**. Wer Laufzeit
  beurteilt, liest `run.phases` aus dem Berichts-JSON, nicht diese Datei.
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
- **Die ID eines Geräts kommt aus dem KATALOG, nie aus dem Titel.** Händler
  benennen denselben Artikel ständig um („iPhone 17 Pro Max 256GB Titan" →
  „Apple iPhone 17 Pro Max 5G 256 GB Titannatur"). Aus einem Titel-Hash
  würden jede Woche neue Geräte, die Listungsdauer wäre immer eine Woche und
  der Preisverfall immer null. `geraete_model.py` benutzt den Titel
  ausschließlich, um den Katalogeintrag zu finden. Genau diese Falle steckt
  in `promo_store.entry_id()`, wo eine Fuzzy-Suche sie nachträglich abfängt.
- **Ein Modellzusatz hinter dem Katalogtreffer verwirft die Zuordnung.**
  „Google Pixel 10 Pro **Fold**" traf im ersten Anlauf den Eintrag „Pixel 10
  Pro". Beide stehen beim selben Händler und liegen 800 € auseinander — die
  Preishistorie schrieb in JEDEM Lauf zwei Änderungspunkte hin und zurück,
  eine dauerhafte Sägezahnkurve, die wie ein Preiskampf aussah. Dasselbe galt
  für „Galaxy S25 FE" und „Galaxy S25 Edge". Wer `_MODELLZUSATZ` anfasst,
  fasst diese Kurve an.
- **Ein Deckel, der eine Seite abschneidet, macht sie nicht „gelesen".**
  `max_produkte` kappte die Linkliste, die Einstiegsseite galt trotzdem als
  vollständig, und `mark_stale` alterte alles jenseits des Deckels. Live:
  freenets Sitemap liefert 83 Adressen zum konfigurierten Muster. Dieselbe
  Falle wie bei `promo_store.mark_stale/gepruefte_seiten`, nur an einer neuen
  Stelle — und das Protokoll sah dabei normal aus.
- **`verfuegbarkeit` ist nie None, also griff die Ausfallregel dort nie.** Ein
  Lauf, der die Verfügbarkeit nicht parsen konnte, schrieb für JEDE Listung
  eine Historienzeile: aus „lieferbar → unbekannt → lieferbar" wurde ein
  Lieferereignis, das es nie gab. Wer ein Feld mit Vorgabewert in die
  Änderungsprüfung aufnimmt, braucht `_ist_ausfall()` dafür.
- **Der Zubehörfilter braucht ZWEI Listen.** Eine einzige, breite verwarf
  echte Geräte: „iPhone 16 Pro Max 256GB, ohne Netzteil" (im deutschen Handel
  eine Pflichtangabe), „moto g85, 5000 mAh Akku", „Xiaomi 15 Ultra, 6,73 Zoll
  AMOLED Display". Wörter, die ein Gerät begleiten können, zählen nur VOR dem
  Modellnamen — so heißt ein Zubehörtitel („Ladekabel für iPhone 17"), während
  die Beigabe hinten steht.
- **`Visit-time` in einer robots.txt ist keine Feinheit.** medimax.de und
  ep.de erlauben Abrufe nur zwischen 02:00 und 08:00 UTC; der Wochenlauf
  startet 08:30. Wer nur `Disallow` prüft, hält sich für regelkonform und
  läuft trotzdem jedes Mal außerhalb des Fensters. Die zweite Hälfte der Regel
  steht nicht im Wächter, sondern beim Aufrufer: ein übersprungener Anbieter
  darf NICHT gealtert werden.
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
- **Eine Grafik ist erst fertig, wenn sie jemand ANGESEHEN hat.** Die
  Positionskarte des Geräteradars ging am 10.08.2026 mit Etiketten live, die
  bis zu 235 px neben ihrem Punkt standen — 87 von 94 weiter als drei Prozent
  daneben. Die Sitzung hatte Tests geschrieben, Daten geprüft und Quellen
  diagnostiziert; sie hatte das Ergebnis nur nie mit den Augen kontrolliert,
  und keiner der 44 Tests der Seite prüfte die AUSSAGE der Grafik. Dafür gibt
  es jetzt `scripts/schiess_screenshot.py` (rendert, fotografiert 1440 und
  390 px und **rechnet aus jeder Etikettenhöhe den Preis zurück**) und
  Kriterium 11 tut dasselbe. Es prüfte vorher nur „kein Etikett unter der
  Nulllinie" — der echte Fehler fand 181 px **darüber** statt.
- **Ein Subagent, der einen Adapter bauen soll, erfindet notfalls seine
  Fixture.** Am 11.08.2026 meldete ein Bau-Subagent einen fertigen
  Telekom-Adapter samt Fixture mit `application/ld+json` — auf der echten
  Seite stehen null Treffer dafür. Der adversarische Prüf-Subagent hat es
  aufgedeckt, und nur deshalb. **Wer Agenten Adapter bauen lässt, braucht die
  Prüfstufe zwingend**, und die Fixture muss aus einem GESPEICHERTEN echten
  Abruf stammen, nicht aus einer Beschreibung. Dasselbe gilt für Messwerte:
  auch der Prüfer nannte eine Zahl („Preis = 1289"), die sich nicht
  reproduzieren ließ — nachgemessen ist `totalDevicePriceWithDiscount` dort
  ein Schalter (`false`), kein Preis.
- **Ein `ld+json` auf der Seite heißt nicht, dass ein PRODUKT drinsteht.**
  Gemessen am 11.08.2026: o2 liefert `BreadcrumbList`, 1&1 `FAQPage`,
  `WebSite` und `Organization`, expert einen Block ganz ohne `@type`. Die
  Extraktionskaskade des Projekts gibt für alle drei null Sätze zurück. Wer
  `grep -c 'ld+json'` als Machbarkeitsprüfung nimmt, plant einen Adapter, der
  nichts findet.
- **Der Satztrenner zerbricht an deutschen Datumsangaben.** „Aktion gültig bis
  12. September" wurde zu „Aktion gültig bis 12." — Punkt, Leerzeichen,
  Großbuchstabe sieht wie ein Satzende aus. Behoben in
  `textwerkzeug._geschuetzt()`, aber der Fall zeigt die Klasse: `saetze()`
  trägt auch `_strip_vodafone_advice` im Wochenbericht, dort fällt dann eine
  Satzhälfte als vermeintlicher Rat weg. Geschützt wird **nur vor einem
  Monatsnamen** — „Die Zahl stieg auf 12. Vodafone reagierte." ist ein echtes
  Satzende, und eine Regel, die es verschluckt, wäre die teurere.
- **Zwei Rechnungen für dieselbe Zahl sind zwei Zahlen.** Die
  Stichwort-Vorschau zählt im BROWSER gegen `site/data/keyword-index.json`,
  `filters.vorschau()` zählt in Python. Am 11.08.2026 sagte der Browser für
  „tarif" 6 und Python 13: der Index tokenisierte mit
  `textwerkzeug.wortmenge()`, das den Bindestrich INNERHALB eines Wortes
  zulässt („Tarif-Rabatt" = ein Wort), während der Stichwort-Matcher ihn als
  Wortgrenze behandelt (damit „Netzausbau" in „Glasfaser-Netzausbau" trifft).
  Der Index hat deshalb einen eigenen Tokenizer. **Und der Test dagegen läuft
  im echten Chromium** — hätte er die Browser-Rechnung in Python nachgebaut,
  wäre er grün geblieben.
- **Die 24-Stunden-Sperre des Newsletters liegt im Workflow, nicht im
  Signup-Dienst.** Dessen IP-Zähler liegt im Arbeitsspeicher, und Render Free
  fährt die Instanz nach 15 Minuten herunter: nach jedem Spin-down und jedem
  Deploy ist er leer. Wer den Mailbomben-Schutz dort einbaut, baut ihn an der
  einzigen Stelle ein, an der er sicher nicht wirkt — man wartet sechzehn
  Minuten.
- **`git pull --rebase` kann eine `age`-verschlüsselte Datei nicht
  zusammenführen.** Jeder Ciphertext unterscheidet sich bei jedem
  Schreibvorgang vollständig; jeder Konflikt ist ein Binärkonflikt, und
  „ours" oder „theirs" wirft die halbe Abonnentenliste weg. Der Weg ist:
  entschlüsseln → auf JSONL-Zeilenebene zusammenführen → neu verschlüsseln.
  Bei gleichem Zeitstempel gewinnt der weiter fortgeschrittene Zustand, sonst
  hängt ein Widerruf davon ab, welcher Workflow zufällig zuerst gepusht hat.
- **Ein `<legend>` sitzt per Voreinstellung IN der Rahmenlinie seines
  Fieldsets.** Ein `border-top` auf dem Fieldset läuft deshalb durch die
  Überschrift hindurch — im ersten Screenshot der Anmeldeseite war jede
  Rubrik durchgestrichen. Die Rubrikleiste gehört an die Legende. Die einzige
  Stelle im ganzen Stylesheet, an der das vorkommt.
- **Eine Sprache raet man nicht auf der Ueberschrift.** Am 13.08.2026 ueber
  810 archivierte Meldungen gemessen ergab die Titelmessung 23,2 %
  fremdsprachig — und war Ausschuss: „AT&T, Ericsson demonstrate
  drone-sensing 5G capabilities" galt als franzoesisch, „CMA clears
  Paramount-WBD deal" als spanisch. Eine Ueberschrift ist kurz und besteht
  groesstenteils aus Eigennamen. Auf Titel PLUS echtem Teaser gemessen fiel
  derselbe Bestand auf 15,2 %, und ueber zwoelf per Artikelabruf gepruefte
  Faelle stimmte die Teasersprache in ALLEN zwoelf mit der des Volltexts
  ueberein. `uebersetzung/sprache.py` misst deshalb nur auf Text ab 200
  Zeichen und **enthaelt sich im Grenzfall**.
- **`py3langid.classify()` gibt eine LOG-Wahrscheinlichkeit zurueck**, keinen
  Anteil zwischen 0 und 1 (Werte wie -53 oder +5). Eine Schwelle `< 0.90`
  darauf ist sinnlos — sie laesst fast alles durch und verwirft gelegentlich
  alles, je nach Textlaenge. Nur `LanguageIdentifier.from_pickled_model(...,
  norm_probs=True)` liefert das Mass, das eine solche Schwelle meint.
- **Die Kappung `summary[:600]` war nie der Engpass.** Ueber 1329
  Feed-Eintraege gemessen sind nur 14,1 % der Teaser ueberhaupt laenger als
  600 Zeichen. Der Hebel, den bis zum 13.08.2026 niemand gezogen hatte, ist
  das nie gelesene Feld **`content:encoded`**: 45,2 % haben eins, 33,2 %
  tragen dort Volltext. Beide Feed-Wege zusammen decken 40,6 % — die
  restlichen **59,4 % gehen nur ueber den Abruf der Artikelseite**. Wer den
  Artikelabruf als „Rueckfall fuer die Minderheit" plant, plant den
  Hauptweg als Nebensache.
- **Eine Mindestlaenge fuer extrahierten Text gehoert in ZEICHEN, nicht in
  einen Faktor.** digi.no lieferte 141 Zeichen hinter einer Paywall gegen 45
  Zeichen Teaser — als Faktor gerechnet „3,1x laenger" und damit ein
  Treffer, absolut sind es zwei Saetze. Der Leser klickt einmal und nie
  wieder.
- **Eine Nebenstufe, die auf `new_items` läuft, arbeitet für den Papierkorb.**
  Der teuerste Fehler dieses Features, und er sah im Protokoll wie ein
  Erfolg aus. Die Übersetzungsstufe bekam alle neuen Meldungen (am
  14.08.2026: 944), in den Bericht kamen 58 — und **alle vier
  Übersetzungen des Laufs gehörten zu Meldungen, die in KEINEM Bericht
  stehen.** Vier fertige Seiten, vier Modellaufrufe, 415 Sekunden, und auf
  der Website nicht ein Link: der rote Link hängt an der KARTE einer
  Meldung, und eine Karte bekommt nur, was der Analyst behalten hat. Wer
  eine Stufe baut, deren Ergebnis auf einer Karte erscheint, füttert sie
  aus `alle_highlights` — `uebersetzung/stufe.berichtete_items()` tut das,
  in Berichtsreihenfolge und zurück auf das ITEM (das Highlight trägt die
  DEUTSCHE Zusammenfassung des Analysten; auf ihr messen Vorauswahl und
  Spracherkennung „deutsch", und es würde nie wieder etwas übersetzt).
- **Ein Deckel, der den SCAN abbricht, ist keine Begrenzung, sondern eine
  Auswahl nach Listenposition.** `_kandidaten` brach ab, sobald 40
  Kandidaten standen: `ueber_deckel: 887`. Weil eine Meldung ohne Text
  (52 der 164 Quellen liefern keinen Teaser) unbesehen als Kandidat gilt,
  gingen die 40 Plätze an textlose englische Newsroom-Meldungen — 40
  Abrufe, 35 Absagen, 4 Treffer. Jetzt wird ALLES vorgeprüft, dann
  geschnitten, und die erkannt fremdsprachigen stehen vor den
  unbestimmten. Dieselbe Fehlerklasse wie bei `max_produkte` im
  Geräteradar, nur eine Stufe weiter.
- **Eine Kartenvorlage, die ihre ganze Karte in einen Link wickelt, formt
  jeden Link DARIN mit.** `.mlead a,.mzwei a{display:flex;flex-direction:
  column}`, `.mz a{display:flex;gap:13px;padding:11px 0}` und
  `.stueck a{display:flex;flex-direction:column}` sind
  Nachfahren-Selektoren. Der rote Übersetzungslink steht innerhalb dieser
  Karten und hat sie mitgeerbt: Text und Pfeil wurden zwei Flex-Kinder und
  standen UNTEREINANDER — auf der Aufmacher-Karte 38 px hoch statt 14,
  Breite 663 statt 195, die Unterstreichung quer durch die Karte. Seit der
  Auslieferung des Features so live, und **in keinem HTML zu sehen**;
  gefunden erst durch eine Messung im Browser
  (`tests/test_uebersetzung_link_browser.py`). Wer einen Link in eine Karte
  setzt, setzt `display` ausdrücklich und holt `gap`/`padding` zurück.
- **Die Beschriftung eines Kartenlinks wird auf die SCHMALSTE Karte
  gemessen.** „Vollständige Übersetzung lesen" braucht 195 px; die vier
  kleinen Karten der dritten Reihe sind 170 px breit, dort stand der Satz
  zweizeilig. Deshalb heißt er „Übersetzung lesen" — das Versprechen der
  Vollständigkeit steht auf der Zielseite, nicht in einem Link, der dafür
  umbricht. Eine zweite, kürzere Fassung nur für die kleinen Karten wären
  zwei Beschriftungen für eine Handlung. Und der Text steht ZWEIMAL im
  Code (Jinja-Makro + `app.js` für den Explorer der Archivwochen) — ein
  Test hält beide zusammen.
- **`_items_payload` in `analyze/agents.py` ist eine POSITIVLISTE.** Sie baut
  die Nutzlast des Analysten Feld für Feld; ein neues Feld am `Item` landet
  dort NICHT automatisch. Genau daran hing der Befund unten: `volltext` lag
  seit dem 13.08.2026 am Item und wurde bis zum 15.08.2026 nie
  weitergegeben. Wer dem Analysten etwas zeigen will, trägt es dort ein.
- **Der Analyst sieht seit dem 15.08.2026 `analyst_text(item)`** — den
  längeren von Feed-Volltext und Teaser, gekappt bei
  `ANALYST_TEXT_ZEICHEN` (2500). Das Feld heißt `text`, nicht mehr
  `snippet`: unter dem alten Namen kappt es der nächste Leser wieder.
  Davor waren es `summary[:300]`, und **52 der 164 crawlbaren Quellen
  liefern gar kein `summary`** (41 `newsroom` + 11 `newsroom_js`;
  `parse_newsroom_html` setzt das Feld nicht, nur der Sonderpfad
  `_extract_datamodel_articles` tut es) — knapp ein Drittel des Bestands
  wurde also allein aus der ÜBERSCHRIFT bewertet, kategorisiert und im
  Wochenbericht beschrieben. Die Grenze ist eine **Eingabe**-Rechnung:
  15 Meldungen je Stapel × 2500 ≈ 10k Tokens, das Ausgabebudget (8000)
  bleibt unberührt. **Ein Artikelabruf gehört hier NICHT hinein** — die
  Nutzlast läuft über jede neue Meldung (am 14.08. waren das 944), das wäre
  eine zweite Sammelphase. Für die textlosen Newsroom-Quellen bleibt es
  deshalb beim Titel; der Prompt sagt dem Analysten ausdrücklich, dass
  `text` leer sein kann und er dann konservativ bewerten soll.
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

> **Zuletzt erledigt (15.08.2026, Antonio direkt): die Reihenfolge der
> Titelseite.** Antonio: *„mir gefällt überhaupt nicht die ordnung der
> artikel … wie kann es sein dass artikel mit priorität von 3 auf der
> titelseite landen, bei diese woche … die wichtigsten artikel sollen auch
> an erster reihe stehen. fixe das, stoße aber keinen neuen Lauf an, sorge
> nur dass alles live gemerged ist."* Stand danach: **1747 Tests** (vorher
> 1741), `pruefe_portal.py` **15 bestanden / 1 durchgefallen** — der eine
> Durchfaller (Kriterium 6, 14 px Hochskalierung auf `meldungen.html`) ist
> **vorbestehend** und gegen den unveränderten `site/`-Stand nachgemessen,
> er hat mit dieser Änderung nichts zu tun.
>
> Zwei unabhängige Fehler, beide in `_titelseite` (`report/html.py`),
> Einzelheiten in §5 unter „Der Rang schlägt den Faden":
>
> | # | Befund | Messung an der echten Ausgabe |
> |---|---|---|
> | 1 | **Der rote Faden hatte keine Untergrenze.** Er wählte allein nach Wortüberschneidung und konnte eine beliebig schwache Meldung auf den Aufmacher ziehen | Ausgabe 14.08.: Aufmacher „T-Mobile wirbt mit Studienstart-Ratgeber" (Kontext, Priorität 2) statt „1GLOBAL Reise-eSIM" (Übertragbar, Priorität 4) |
> | 2 | **Die Digest-Spalte zog vor der dritten Reihe** (K2, 09.08.) und ließ der Hauptspalte systematisch die schwächeren Meldungen | Ausgabe 15.08.: vier Bildkacheln mit Priorität 2, daneben fünf Priorität-3-Meldungen als Textzeilen. Nach der Änderung tragen die Kacheln die Dreier |
>
> **Der Lauf wurde wie verlangt nicht angestoßen** — `site/` ist aus den
> vorhandenen Berichten neu gerendert (`render_site` MIT `cfg`, siehe §6).
>
> **OFFEN daraus:**
> 1. **Die live sichtbare Ausgabe (15.08.) ist degeneriert.** Sie hat nur
>    20 bewertete Meldungen und keine über Priorität 3 — nicht wegen der
>    Reihenfolge, sondern weil in diesem Lauf DeepSeeks Guthaben nach
>    26 Minuten leer war (HTTP 402, siehe §6) und nur 20 von 810 Meldungen
>    bewertet wurden. Solange das Guthaben leer ist, führt die Titelseite
>    mit Priorität 3, egal wie gut sie sortiert. Das ist der eine Punkt,
>    den nur Antonio schließen kann.
> 2. **Die Regel ist an drei Ausgaben gemessen** (08.08., 14.08., 15.08.),
>    nicht an einem Lauf. Nach dem nächsten echten Lauf die Titelseite
>    ansehen: führt der Aufmacher weiterhin den besten Rang mit Bild?
> 3. **Kriterium 6** (`pruefe_portal.py`, 14 px Hochskalierung eines Bildes
>    auf `meldungen.html`) steht offen und ist nicht Teil dieses Auftrags.

> **Davor erledigt (15.08.2026, Antonio direkt): die Übersetzung sichtbar
> gemacht — sie war gebaut, getestet, live und vollständig unsichtbar.**
> Antonio: *„Ich sehe hier nirgendwo bei keiner einzigen Meldung … keinen
> Link, der mir dann zeigt, die übersetzte Quelle. Also es hat anscheinend
> überhaupt nicht funktioniert."* Er hatte recht, und zwar aus drei
> unabhängigen Gründen. Stand danach: **1741 Tests** (vorher 1716),
> `pruefe_portal.py` **16 bestanden / 0 durchgefallen**.
>
> | # | Befund | Messung |
> |---|---|---|
> | 1 | **Die Stufe lief auf `new_items` statt auf den berichteten Meldungen.** Der rote Link hängt an der KARTE einer Meldung; eine Karte bekommt nur, was der Analyst behalten hat | Lauf 14.08.: 944 neue Meldungen, 58 im Bericht, 4 Übersetzungen — **davon 0 zu einer berichteten Meldung**. 415 s Arbeit, 0 Links |
> | 2 | **Der Deckel brach den SCAN ab, nicht die Arbeit.** Textlose Meldungen gelten unbesehen als Kandidat und verbrannten die 40 Plätze | `ueber_deckel: 887` — 887 von 944 nie angesehen. 40 Abrufe → 35 Absagen → 4 Treffer |
> | 3 | **Der Analyst sah wirklich nur die Überschrift** — bei 52 der 164 Quellen. `volltext` lag seit dem 13.08. am Item, die Nutzlast gab ihn nie weiter | `summary[:300]`, und der Teaser ist im Median 206 Zeichen. 30 % der Feed-Einträge tragen Volltext (Median 2000 Zeichen, p90 5302) |
>
> **Gegen die echte Ausgabe vom 14.08. gemessen** (ohne Modell, nur Auswahl
> und Abruf): von 22 geprüften berichteten Meldungen bekommen **9** eine
> deutsche Fassung — 8× Polnisch (Telepolis), 2× Französisch (Univers
> Freebox), Italienisch (Corriere), Spanisch (Xataka). Vorher: keine davon.
> Mit gestubbtem Modell durchgerechnet: **11 Übersetzungen aus 58
> berichteten Meldungen, 11 rote Links auf `meldungen.html`.**
>
> **Zwei Anzeigefehler dazu, beide nur im BROWSER sichtbar** — kein
> statischer Test hätte sie gemeldet, und beide waren seit der Auslieferung
> live:
> 1. **Der Pfeil stand auf einer eigenen Zeile.** Die Kartenvorlagen wickeln
>    ihre Karte in einen Link und formen ihn als Flexbox; der rote Link steht
>    darin und erbte das. Aufmacher-Karte: 38 px hoch statt 14, 663 px breit
>    statt 195. Siehe §6.
> 2. **Auf der Startseite trug nur der Aufmacher den Link.** Er erschien dort
>    also genau dann, wenn die stärkste Meldung der Woche zufällig
>    fremdsprachig war — an der Ausgabe vom 14.08.: elf Übersetzungen, null
>    auf der Startseite, obwohl die polnischen und französischen Meldungen in
>    der zweiten und dritten Reihe standen. Jetzt an allen drei
>    Bildgewichtungen.
>
> Dabei ist die Beschriftung von „Vollständige Übersetzung lesen" auf
> **„Übersetzung lesen"** gekürzt — gemessen auf die schmalste Karte (170 px),
> nicht auf die breiteste. Der Text steht ZWEIMAL im Code (Makro + `app.js`);
> ein Test hält beide zusammen.
>
> Neu: `tests/test_uebersetzung_auswahl.py` (17) und
> `tests/test_uebersetzung_link_browser.py` (6, echtes Chromium). Gegen den
> alten Stand gemessen fallen **13 der 17** bzw. **3 der 6** durch; die
> übrigen prüfen Invarianten, die auch vorher galten.
>
> **Der Lauf danach (31884827147, `main`, 151,7 min) hat die Auswahl
> bestätigt und an einer ganz anderen Stelle etwas aufgedeckt.** Die
> Protokollzeile:
>
> ```
> Uebersetzung: 20 berichtete Meldungen -> 13 Kandidaten (erkannt
>   fremdsprachig insgesamt: 7, ueber dem Deckel 40: 0), Bestand 4
> Uebersetzung: 0 uebersetzt aus 20 berichteten Meldungen, 3 gescheitert,
>   7 ohne Abruf vorgefiltert, 889.8s [FRIST ERREICHT]
> ```
>
> **`angeboten: 20` statt 810, `ueber_deckel: 0`** — die zwei Fehler sind in
> Produktion behoben. Übersetzt wurde trotzdem nichts, und zwar aus einem
> Grund, der nichts mit dieser Stufe zu tun hat: **HTTP 402, DeepSeeks
> Guthaben war 26 Minuten nach dem Start aufgebraucht.** Derselbe Lauf hat
> deshalb auch nur 20 von 810 Meldungen bewertet und den Editor in den
> Notfall-Digest fallen lassen. Siehe §6 — 402 galt nicht als endgültig und
> wurde 1245-mal wiederholt.
>
> **OFFEN daraus:**
> 1. **Das DeepSeek-Guthaben ist leer.** Das ist der einzige Grund, warum
>    noch keine Übersetzung live steht, und nur Antonio kann es auffüllen.
>    Danach genügt ein `workflow_dispatch` auf `radar.yml`; die Auswahl ist
>    gemessen und funktioniert. Erwartung bei einer normalen Ausgabe:
>    10–25 Kandidaten, davon der größere Teil übersetzt.
> 2. **Die Stufe ist noch nie gegen ein antwortendes Modell gelaufen.** Alles
>    bisher Gemessene lief mit gestubbtem Übersetzer. Fällt beim nächsten Lauf
>    fast alles unter „zusammengefasst statt übersetzt", ist `MINDESTANTEIL`
>    zu scharf oder der Prompt zu schwach.
> 2. **Der Deckel (40) ist für eine große Ausgabe knapp.** Bei 58 berichteten
>    Meldungen greift er nach der Vorauswahl nicht; die Ausgabe vom 06.08.
>    hatte 193. Dann entscheidet die Berichtsreihenfolge, also die Relevanz —
>    das ist gewollt, aber nach einem großen Lauf gehört
>    `[DECKEL: n nicht angesehen]` im Protokoll nachgesehen.
> 3. **Der Zeitbedarf ist jetzt echt.** 11 Übersetzungen brauchten mit
>    gestubbtem Modell 49 s, die Abrufe also. Mit echten Modellaufrufen
>    kommen 3–5 Aufrufe je Artikel dazu; `uebersetzung_frist_sekunden` steht
>    auf 600. Fällt die Zeile mit `[FRIST ERREICHT]` auf, ist der Deckel oder
>    die Frist zu hoch angesetzt — nicht der Bericht darf leiden.
> 4. **Ob der längere Analysten-Text die Bewertungen verändert, ist nicht
>    gemessen.** Er kann nur besser werden (mehr Stoff statt Titel allein),
>    aber die Verteilung der Relevanzstufen und die Länge der Bericht-Sätze
>    gehören nach dem nächsten Lauf verglichen.
> 5. **`ctm_saetze: 0` bei `ctm_saetze_verworfen: 9`** — nebenbei aufgefallen,
>    NICHT Teil dieses Auftrags: der Prüflauf gegen den Originaltext hat am
>    14.08. jeden einzelnen Satz verworfen. Der Handover verlangt genau dafür
>    „fallen fast alle Sätze, stimmt der Prompt nicht". Der Prüftext ist
>    `title + summary` des Highlights; mit dem längeren Analysten-Text
>    könnten mehr Zahlen gedeckt sein. Erst nach dem nächsten Lauf beurteilen.

> **Davor erledigt (13.08.2026, Antonio direkt): die Volltext-Übersetzung
> fremdsprachiger Artikel.** Grundlage ist das Konzept „Volltext-Übersetzung
> fremdsprachiger Artikel" (13.08.2026). Stand danach: **1716 Tests** (vorher
> 1657), `pruefe_portal.py` **16 bestanden / 0 durchgefallen**. Der
> Phase-0-Befundbericht mit allen Messungen:
> `outputs/volltext-uebersetzung-phase0-2026-08-13.md`.
>
> **Phase 0 hat den Zuschnitt umgedreht.** Das Konzept plante den
> Artikelabruf als „Rückfallweg für die Minderheit". Gemessen über 1329
> Feed-Einträge aus 140 RSS-Quellen: die Kappung `[:600]` aufzuheben bringt
> **14,1 %**, das nie gelesene `content:encoded` bringt **33,2 %**, beide
> zusammen **40,6 %** — die restlichen **59,4 % gehen nur über den
> Artikelabruf**. Er ist der Hauptweg, nicht das Anhängsel.
>
> | Baustein | Wo | Die eine Regel, die ihn trägt |
> |---|---|---|
> | **Feed-Volltext** | `collect/rss.py` | `content:encoded` lesen, ungekappt, in ein EIGENES Feld. `summary` bleibt bei 600 — was der Analyst sieht, ist eine eigene Entscheidung (und **seit dem 15.08.2026 anders entschieden**: er bekommt den Volltext, siehe oben) |
> | **Spracherkennung** | `uebersetzung/sprache.py` | **Nie auf der Überschrift**, erst ab 200 Zeichen, und im Grenzfall wird verworfen statt geraten |
> | **Volltext holen** | `uebersetzung/volltext.py` | Mindestlänge in ZEICHEN, nicht als Faktor (digi.no: 141 Zeichen = „3,1× länger") |
> | **Übersetzen** | `uebersetzung/uebersetzer.py` | Vollständig, nicht zusammengefasst: unter 55 % der Originallänge fällt die Antwort durch. Absatzweise gebündelt, ein Absatz wird nie zerrissen |
> | **Speicher** | `uebersetzung/store.py` | Schlüssel = `Item.id` **plus** Texthash. **Es wird nie etwas gelöscht** — sonst tote Links im eigenen Archiv |
> | **Stufe** | `uebersetzung/stufe.py` | Budget gegen die **Restzeit des Jobs**, nicht gegen sich selbst — die Lehre aus Lauf 31422689829. Ein kaputter Artikel kostet nie den Bericht |
> | **Seite und Link** | `report/uebersetzung_view.py`, `_uebersetzung.html.j2` | Der Link zum Original bleibt **unverändert daneben stehen**. Der rote Link steht außerhalb des umschließenden `<a>` — ein Link im Link ist kein gültiges HTML |
>
> **Drei Fehler sind erst beim ANSEHEN der gerenderten Seite aufgefallen**,
> nicht in einem der Tests: „aus dem Spanisch" statt „aus dem Spanischen"
> (der Satz steht zweimal je Seite), sichtbarer Text in
> ASCII-Umschrift („Maschinelle Uebersetzung", „Absaetze") während der Rest
> des Portals Umlaute schreibt, und ein Pfeil, der mit dem `letter-spacing`
> der Zeile sichtbar vom Wort abstand. Alle drei behoben, die ersten zwei
> mit einem Test.
>
> **Der Link erscheint an allen drei Gewichtungen von `meldungen.html`**, am
> Aufmacher der Wochenseite und im Explorer der Archivwochen (dort über
> `app.js`, weil die Seite ihre Meldungen im Browser baut). Im ersten Anlauf
> hing er nur an der Zeilen-Gewichtung — dann wäre er je nach Dringlichkeit
> der Woche erschienen oder verschwunden.
>
> **Der Satz „am Aufmacher der Wochenseite" war die Lücke.** Nur dort hiess
> auf der Titelseite: fast nie. Seit dem 15.08.2026 tragen auch die zweite
> und die dritte Reihe den Link — siehe den Eintrag darüber.
>
> **OFFEN:**
> 1. **Die Stufe ist noch nie gegen ein echtes Modell gelaufen.** Nach dem
>    nächsten Actions-Lauf die Zeile `Uebersetzung:` im Protokoll lesen. Sie
>    nennt übersetzt / übersprungen / ohne Abruf vorgefiltert / gescheitert
>    **mit Gründen**. Fällt fast alles unter „zusammengefasst statt
>    übersetzt", ist `MINDESTANTEIL` zu scharf oder der Prompt zu schwach.
> 2. **Keine Übersetzung ist bisher von einem Menschen gelesen worden.** Die
>    Textprobe der Phase-0-Messung war sauberer Artikelanfang über fünf
>    Sprachen, aber das ist der EXTRAKT, nicht die Übersetzung. Premortem 2
>    verlangt eine Stichprobe von Hand, bevor es dauerhaft läuft.
> 3. **Soll der rote Link in den Newsletter?** Offene Frage aus dem Konzept,
>    bewusst nicht entschieden: die Mail hat die Regel „keine neuen Inhalte",
>    und ein Link auf eine Seite, die es zur Sendezeit noch nicht gab, wäre
>    ein Sonderfall, den der Treue-Test heute nicht kennt.
> 4. **Sollen die Analysten mehr sehen als die Überschrift?** 52 der 164
>    crawlbaren Quellen liefern ihnen heute nichts als den Titel (§6). Der
>    Volltextabruf stellt den Stoff bereit — ihn in die Prompts zu geben ist
>    eine eigene Entscheidung mit eigener Laufzeit- und Token-Rechnung.
> 5. **Der Platzbedarf ist gerechnet, nicht gemessen.** Rund 20–30
>    Übersetzungen je Ausgabe als JSONL-Zeilen; die HTML-Seiten entstehen
>    beim Rendern und werden nicht einzeln versioniert. Nach vier Wochen die
>    Dateigröße von `uebersetzungen.jsonl` nachsehen.

> **Davor erledigt (11.08.2026, Antonio direkt): der Newsletter, N1–N8.**
> Grundlage ist `claude/newsletter-konzept-2026-08-11.md` (liegt jetzt im
> Repo — zweimal war die Auftragsgrundlage vorher nicht auffindbar).
> Stand danach: **1647 Tests** (vorher 1416), `pruefe_portal.py`
> **16 bestanden / 0 durchgefallen / 0 übersprungen**. Vollständige
> Schlussliste mit allen Messungen: `outputs/newsletter-2026-08-11.md`.
>
> **Der Newsletter ist ein AUSSPIELKANAL, kein vierter Anwendungsfall.** Drei
> Regeln tragen ihn, alle drei im Test: keine neuen Inhalte (jeder
> inhaltstragende Block der Mail muss als Teilstring im Bericht-JSON stehen),
> kein Modellaufruf im Versandpfad, und die Mail ist ein Anreißer mit
> höchstens acht Einträgen — Ziel jeder Ausgabe ist der Klick auf die Seite.
>
> **Er schaltet sich selbst frei, und im Moment ist er AUS.**
> `rechtstexte.vollstaendig()` rechnet die Schwelle, `render_site()` setzt
> daraus `newsletter_verlinkt`. Ohne vollständiges Impressum steht die Seite
> da, sagt sichtbar warum sie gesperrt ist, hat einen abgeschalteten
> Absendeknopf und keinen Navigationseintrag — Art. 13 DSGVO verlangt die
> Information zum ZEITPUNKT der Erhebung. Dieselbe Mechanik wie bei
> „Geräte" und aus demselben Grund im CODE statt in einem Test.
>
> | Baustein | Wo | Die eine Regel, die ihn trägt |
> |---|---|---|
> | **Filter-Engine** | `newsletter/filters.py`, `config/newsletter.yaml` | UND zwischen den Dimensionen, ODER innerhalb, **leer heißt ALLES**, Stichwörter additiv und im Ergebnis begründet |
> | **Stichwörter** | dieselbe Datei | Im Fachpresse-Tagging hält eine gepflegte Blockliste gegen `spark`/`tim`/`globe` — hier tippt der Abonnent. Vier Zeichen Mindestlänge, Wortgrenzen, nur Titel und Zusammenfassung, Trefferzahl-Vorschau VOR dem Absenden |
> | **Segmente** | `newsletter/segments.py` | Der `segment_hash` ist die Hälfte des Idempotenzschlüssels. Ändert er sich ohne Änderung der Auswahl, hält ein Wiederanlauf seinen eigenen Sendeplan für einen fremden |
> | **Mail-Renderer** | `newsletter/render.py`, `templates/mail/` | Inhaltstragende Blöcke müssen im Bericht stehen, Rahmentexte kommen aus `chrome.yaml` — die Allowlist des Treue-Tests. Ohne diese Trennung ist der Test nicht erfüllbar |
> | **Signup-Dienst** | `service/signup/` | **Speichert nichts, verschickt nichts.** Alle Angaben reisen signiert im Bestätigungslink; wer nie bestätigt, hinterlässt keine Daten |
> | **Abo-Store** | `newsletter/store.py`, `mail_repo/` | Die Logik hier, die DATEN im privaten Repo. Eine Kopie der Filter-Engine dort würde driften |
> | **Versand** | `newsletter/versand.py` | Idempotenz dreistufig; „gesendet, Log-Schreiben fehlgeschlagen" gilt als GESENDET — im Zweifel eine Mail zu wenig |
> | **Limit-Wächter** | dieselbe Datei | 300/Tag ist die **Verteilerobergrenze**, nicht eine ferne Grenze. Gezählt wird geplant PLUS heute schon versendet |
> | **Protokoll** | `report/newsletter_protokoll.py` | Auf `transparenz.html`, nicht in einem eigenen Dashboard — nach acht Wochen geht dorthin niemand mehr. Nur Zahlen |
>
> **Vier Befunde, die erst beim Messen kamen** (Einzelheiten in der
> Schlussliste):
> 1. **Der Satztrenner zerreißt deutsche Datumsangaben.** „gültig bis
>    12. September" wurde zu „gültig bis 12." — ein VORBESTEHENDER Fehler in
>    `textwerkzeug.saetze()`, der damit auch `_strip_vodafone_advice` im
>    Wochenbericht trifft. An der Wurzel behoben, geschützt bewusst nur vor
>    einem Monatsnamen.
> 2. **Browser und Python zählten die Stichwort-Vorschau verschieden**
>    (`tarif`: 6 gegen 13). Der Index tokenisierte mit `wortmenge()`, das den
>    Bindestrich im Wort zulässt; der Matcher behandelt ihn als Grenze. Der
>    Index hat jetzt einen eigenen Tokenizer, und vier Begriffe werden im
>    echten Chromium gegen Python gehalten.
> 3. **„Ihr Stichwort: Starlink" stand viermal untereinander** — jetzt nennt
>    nur der erste einer Folge sein Stichwort.
> 4. Der Protokollabschnitt lag versehentlich in `{% if run %}` und wäre in
>    Produktion nie aufgefallen.
>
> **OFFEN:**
> 1. ~~**Die ladungsfähige Anschrift.**~~ **ERLEDIGT am 12.08.2026.**
>    `c/o Vodafone GmbH, Ferdinand-Braun-Platz 1, D-40549 Düsseldorf`, unter
>    Antonios Namen in beiden Rechtstexten. Die Schwelle steht auf `True`,
>    die Anmeldeseite ist verlinkt. **Sie kann trotzdem noch nichts
>    entgegennehmen** — dafür fehlt Punkt 3.
> 2. **Der Testversand.** `.github/workflows/mail_test.yml` von Hand starten,
>    dann `docs/mail-setup.md` §4 ausfüllen, **auch wenn es schlecht
>    ausfällt**. Die eine Zeile, auf die es ankommt: landet die Mail im
>    FIRMENpostfach im Posteingang oder im Spam? Ohne eigene Domain fehlt das
>    DMARC-Alignment; das ist der dauerhafte Zustand, kein Bug.
> 3. **Die drei Repositories und der Render-Dienst** nach
>    `mail_repo/README.md`. `SIGNUP_TOKEN_KEY` und `SIGNUP_PEPPER` müssen im
>    Dienst und im privaten Repo IDENTISCH sein.
> 4. **Der Versand ist noch nie gegen die echte Brevo-API gelaufen**, und die
>    Events-API hat noch nie ein echtes Ereignis geliefert.
> 5. **Die Mail ist in keinem echten Client gesehen worden.** Gemessen sind
>    Chromium auf 700 und 390 px; N9 verlangt Outlook, Gmail-Web und ein
>    Telefon. `outputs/mail-preview/` liegt bereit.

> **Davor erledigt (11.08.2026, Antonio direkt): die Nachbesserung nach der
> Evaluation der Geräteseite.** Die Grundlage war ein Evaluationsdokument zur
> ersten Lieferung. Stand danach: **1411 Tests** (vorher 1398),
> `pruefe_portal.py` **15 bestanden / 0 durchgefallen / 0 übersprungen**.
> Vollständige Schlussliste mit allen Messungen:
> `outputs/geraeteradar-nachbesserung-2026-08-11.md`.
>
> **Erledigt: P1 (Positionskarte) und P3 (Lifecycle, Wochenkarte).**
> Die Etiketten standen bis zu **235 px** neben ihrem Punkt, 87 von 94 weiter
> als drei Prozent daneben, und 60 von 85 Kreisen lagen deckungsgleich. Die
> Geometrie steht jetzt in `report/geraete_karte.py`; Einzelheiten in §5 unter
> „Die Positionskarte".
>
> **NICHT erledigt: P2 (Abdeckung von 2 auf 8 Anbieter).** Die Grundlage steht
> (Adapter-Registry mit Linkernte je Adapter, Bündelpreise mit Tarifreferenz),
> die acht Adapter fehlen. Der `ultracode`-Workflow hat dabei einen Befund
> geliefert, der wichtiger ist als der Ausfall selbst:
>
> - **Ein Bau-Subagent hat seine Fixture ERFUNDEN** — er behauptete ein
>   `application/ld+json` auf Telekoms Produktseite, wo live null Treffer
>   stehen. Der adversarische Prüf-Subagent hat es aufgedeckt. **Wer Agenten
>   Adapter bauen lässt, braucht die Prüfstufe zwingend** — und die Fixture
>   muss aus einem gespeicherten echten Abruf stammen, nicht aus einer
>   Beschreibung.
> - Nachgemessen fielen zwei Angaben, die bisher als gemessen galten:
>   Telekoms `productDetailsData` trägt je Speicherstufe nur `deltaPrice`
>   (Aufschlag ohne Grundbetrag), die absoluten Beträge sind `upfrontPrice` je
>   Ratenlaufzeit — also **Zuzahlungen**. o2, 1&1 und expert liefern zwar
>   ld+json, aber **kein Produktschema** (BreadcrumbList, FAQPage, bzw. ganz
>   ohne `@type`).
> - **Alle zwölf konfigurierten Einstiegsseiten antworten mit HTTP 200**, auch
>   MediaMarkt. Am Zugang scheitert nichts. Der billige Weg („nur
>   Konfiguration, kein Code") existiert nicht: jeder braucht seinen
>   Extraktor, und die Netzbetreiber-Ebene hängt an den Bündelpreisen.
>
> Alle diese Messungen stehen wörtlich in `config/geraete_quellen.yaml` und
> damit auf `/geraete-quellen.html`.

> **Davor erledigt (10.08.2026, Antonio direkt): das Geräte- und
> Preisradar.** Vier Bauabschnitte, alle umgesetzt. Stand danach:
> **1384 Tests** (vorher 1104), `pruefe_portal.py` 14 bestanden / 0
> durchgefallen / 1 übersprungen (das neue Kriterium 11 braucht Daten, die
> erst der erste Lauf bringt). Vollständige
> Schlussliste mit allen Messungen:
> `outputs/geraete-preisradar-2026-08-10.md`.
>
> Neu: `geraete_model.py` (Datenmodell und Geräteerkennung),
> `geraete_config.py`, `analyze/geraete_store.py` (Zwei-Stufen-Auslistung +
> Preishistorie), `collect/geraete/` (robots.txt, ld+json/Microdata, Shopify,
> Linkernte), `analyze/geraete_lifecycle.py`, `geraete_pipeline.py`,
> `report/geraete_view.py`, zwei Vorlagen, `.github/workflows/geraete.yml`.
>
> **Die Quellen sind gemessen, nicht geraten.** 22 Anbieter einzeln (plus
> Amazon, das aus Rechtsgründen gar nicht erst abgerufen wurde — 23 in der
> Konfiguration)
> abgerufen — robots.txt, Kategorie-/Sitemap-Seite, Produktseite, Preis per
> `json.loads`. Vier tragen einen Adapter (Medimax, ElectronicPartner,
> mobilcom-debitel/freenet, ALDI TALK); alle anderen stehen mit ihrem
> Messergebnis und ihrem Grund in der Konfiguration. Amazon ist wie im
> Auftrag verlangt als Adapter gebaut und **deaktiviert ausgeliefert**;
> Euronics antwortet auf jede Variante mit 403, auch auf die robots.txt
> selbst — dieselbe Lage wie bei Telecompetitor.
>
> **`diff-reviewer` lief zweimal und hat 17 + 19 Befunde gemeldet**, neun
> davon kritisch oder schwer — alle behoben, jeder mit einem Test, der gegen
> den alten Stand durchfällt. Die teuersten stehen als Fallstricke in §6; die
> vollständige Liste in der Schlussliste. Drei Beispiele, weil sie den Typ
> zeigen: „Pixel 10 Pro **Fold**" traf den Katalogeintrag „Pixel 10 Pro" und
> erzeugte eine dauerhafte 800-Euro-Sägezahnkurve; die Etiketten der
> Positionskarte wanderten bei voller Spalte unter die Nulllinie; und „Was
> diese Woche auffällt" hatte kein Zeitfenster, eine Änderung vom 9. März
> stand in der Augustausgabe.
>
> **Der erste echte Lauf ist am 10.08.2026 gelaufen** (Lauf 31419244686,
> `main`, 19 min, Commit `dbdcf14`). Er hat vier der sechs offenen Punkte
> beantwortet — und drei Mängel gezeigt, die nur mit echten Daten sichtbar
> werden. Alle drei sind behoben, jeder mit einem Test, der gegen den alten
> Stand durchfällt. Stand danach: **1390 Tests**, `pruefe_portal.py`
> **15 bestanden / 0 durchgefallen / 0 übersprungen**.
>
> ```
> Geraeteradar: 1 Anbieter abgefragt, 87 Listungen (85 neu), 85 Preispunkte,
>               0 gealtert, Bestand 85, 1154.9s
> ```
>
> | Punkt | Ergebnis |
> |---|---|
> | Besuchszeit-Wächter | **greift.** Medimax und ep.de: „ausserhalb der Besuchszeit laut robots.txt (02:00-08:00 UTC, Lauf um 18:29 UTC)", und **nicht gealtert** |
> | Kriterium 11 | **BESTANDEN** — aber erst nach der Reparatur unten. Mit echten Daten fiel es durch: 76 Etiketten unter der Nulllinie |
> | Bestand | 85 Listungen: mobilcom-debitel 84, ALDI TALK 1. Drei Hersteller (Apple 38, Google 22, Samsung 25), 11 Modelle, **alle Preise `ohne_vertrag`** — keine Bündelzahl ist durchgerutscht |
> | Veröffentlichungsschwelle | **nicht erreicht**: 2 Anbieter mit Daten (nötig 3). Hersteller (3) und SKUs (85) stehen. Die Seite bleibt deshalb aus der Navigation, der Test hält beides gegeneinander |
>
> **Die drei Mängel des ersten Laufs, alle behoben:**
>
> 1. **Der Deckel der Positionskarte deckelte die falsche Größe.** Die
>    Vorlage setzte `y="{{ p.ly + 3 }}"` — ein SVG-Text sitzt auf seiner
>    Grundlinie —, der Deckel rechnete aber gegen `ly`. Jedes gedeckelte
>    Etikett lag drei Pixel unter der Achse. Dazu zeichnete die Vorlage für
>    jeden gedeckelten Punkt ein **leeres** `<text class="gr-etikett">`, und
>    genau die zählte Kriterium 11: 76 Stück. Der Versatz liegt jetzt als
>    `label_y` im Modul (die Vorlage rechnet nichts nach), und ein Punkt
>    ohne Etikett zeichnet keinen Text mehr. Die Legende nennt jetzt **beide**
>    Ansichten — in der Anbieteransicht stehen 84 der 85 Listungen in einer
>    Spalte, dort bleiben die meisten Etiketten weg.
> 2. **„kein Einstieg lesbar" für einen Anbieter mit 84 Listungen.**
>    mobilcom-debitel stand so im Protokoll, und das Gegenteil war wahr: die
>    Einstiegsseite war lesbar, nur ihr Deckel (`max_produkte`) war erreicht.
>    Der Status „fehler" ist richtig (nichts darf altern) — der GRUND war es
>    nicht. Er nennt jetzt den Deckel bzw. „Einstieg gelesen, aber
>    unvollständig ausgewertet", und die Protokollzeile trägt die Zahlen
>    (`… -> fehler, 84 Listungen aus N Produktseiten`).
> 3. **`unbekannte_titel` stand nur in der Rückgabe.** Der nächtliche Lauf
>    gibt an niemanden zurück, sein einziger Kanal ist das Protokoll — die
>    Arbeitsliste war also genau da nicht auffindbar, wo diese Übergabe sie
>    zu lesen verlangt. Sie wird jetzt geloggt, mit der **echten Gesamtzahl**
>    neben der auf 25 gekürzten Liste.
>
> **Offen:**
> 1. **Der Katalog ist für die Discount-Ebene zu schmal.** ALDI TALK lieferte
>    27 abgerufene Produktseiten und genau EINE Listung (ein refurbished
>    iPhone 15). Der Rest sind Motorola moto g06/g17/g37/g67/g77/g86, Nubia,
>    OnePlus Nord, Crosscall, Sonim, Samsung A17 — Mittelklasse, die im
>    Katalog nicht steht. Nach dem nächsten Lauf die neue Zeile
>    „**N Titel ohne Katalogtreffer**" lesen und entscheiden: Katalog
>    verbreitern oder die Ebene bewusst schmal lassen.
> 2. **Die dritte Datenquelle fehlt für die Schwelle.** Medimax und ep.de
>    liefern nur im nächtlichen Lauf (03:10 UTC); der ist noch nie zur
>    geplanten Zeit gelaufen, sondern nur von Hand um 18:29 UTC. Nach dem
>    ersten echten Nachtlauf steht die Schwelle mit vier Anbietern.
> 3. **24 von 46 Katalogmodellen haben kein belegtes Marktstartdatum.** Für
>    sie gibt es keine Nachfolger-Analyse. Der eine Punkt, den nur ein Mensch
>    schließen kann — eine Zeile je Recherche.
> 4. **Die zwölf unbekannten Farbschreibweisen** aus dem Lauf sind die
>    Arbeitsliste für `config/farben.yaml`: Blueblack, Cobalt Violet, Cosmic
>    Orange, Frost, Indigo, Jade, Lemongrass, Moonstone, Nebelblau, Silver
>    Shadow (Enterprise Edition), Sky Blue, Tiefblau.

> **Davor erledigt (09.08.2026, Antonio direkt): Startseite und
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

- ~~E-Mail-/Teams-Versand~~ **gebaut am 08.08.2026** (`versand.py`) — Mail montags mit dem Zwei-Minuten-Pfad, Teams nur für die Ausnahme. Es fehlen nur noch die Secrets. **Nicht zu verwechseln mit dem Newsletter** (`src/telco_radar/newsletter/`, 11.08.2026): `versand.py` schickt EINE Mail an Antonio und seine Kollegin, der Newsletter einen gefilterten Anreißer an einen offenen Verteiler über Brevo.
- ~~Newsletter mit Themenauswahl~~ **gebaut am 11.08.2026**, N1–N8 (`outputs/newsletter-2026-08-11.md`). Offen ist die Abnahme (N9) und die Einrichtung des Signup-Dienstes. Die Anschrift steht seit 12.08.2026, die Anmeldeseite ist verlinkt.
- Firecrawl/Crawl4AI als Fetcher für JS-Newsrooms (AT&T, Singtel, Telia, …)
- Semantisches Dedup (Embeddings), um dieselbe Story aus mehreren Quellen zu mergen
- Tarif-/Preisseiten-Diffing als dritte Signalebene
- ~~Trend-Charts über mehrere Wochen~~ **gebaut am 08.08.2026** (`report/verlauf.py`, Abschnitt „Was wächst, was kippt" auf der Differenzierungs-Seite)
- Feedback der Vodafone-Kollegin einarbeiten (steht noch aus)
- Migration auf Vodafone-Infra, falls gewünscht (Runner braucht nur Python + HTTPS)
