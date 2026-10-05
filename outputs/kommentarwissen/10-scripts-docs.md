# Kommentarwissen 10-scripts-docs

Stand: Commit aaa8b0d, 50 Dateien, 1095 Kommentarzeilen.

## Übernahmen in Code
- `scripts/finde_quellen.py`: Konstanten `DROSSEL_PARALLEL_JE_HOST = 4` und `DROSSEL_PAUSE_SEKUNDEN = 0.15` ersetzen `configure_throttle(4, 0.15)` in `main` – Drosselung je Host; der Kommentar (zwei Zeilen, Begründung unten) wurde dafür gekürzt, Dateilänge bleibt 486.
- `scripts/kostenrechnung.py`: Konstante `ZIEL_BEREICHE = 16` ersetzt `ziel_bereiche = 16` in `main` – angenommene Zahl Themenbereiche beim Ausbau (Kommentar bleibt).

## Für docs/betrieb.md
- Der Cron der Tagesläufe lief 08:30 UTC = 16:30 Peking, mitten in DeepSeeks zweiter Stoßzeit (9–12 und 14–18 Uhr Peking, doppelte Preise angekündigt); Preise stehen daher mit und ohne Stoßzeit (Stand 08/2026) (Quelle `scripts/kostenrechnung.py:26`).
- GitHub-Actions-Annotation `::warning` auf stdout erscheint im Log und in der Job-Zusammenfassung, färbt den Schritt aber nicht rot; so meldet der Abdeckungsmail-Schritt „Mailkanal nicht eingerichtet“ (Quelle `scripts/geraete_abdeckung_mail.py:63`).
- Abdeckungsmail-Schritt: kein einziger Messtag im Bestand = Schritt rot (Ausfall, keine Entwarnung); Mailkanal nie versucht, weil Secrets im Repo fehlen = nur Warnung (P1/C2-Nachtrag 24.09.2026); eingerichteter Kanal, Zustellung scheitert = Ausnahme weiterreichen, Schritt rot (Quelle `scripts/geraete_abdeckung_mail.py:87,110,125`).
- Der Schritt läuft HINTER dem Lauf, der den Bestand schreibt (Quelle `scripts/geraete_abdeckung_mail.py:87`).
- Signup-Dienst: eigener Render-Dienst `telco-radar-signup.onrender.com`, Website `telco-radar.onrender.com` (Static Site) – jeder Formularaufruf ist cross-origin; CORS-Liste = `SITE_BASE_URL` plus bekannte Produktionsadresse; ist `SITE_BASE_URL` im Render-Dienst falsch/leer, greift die Freigabe still nicht (Preflight 200 ohne Kopf); `/gesund` gibt die Liste aus (Quelle `service/signup/app.py:127-157`).
- Signup-Dienst: Bestätigungs-/Abmeldelinks bauen auf die Adresse des DIENSTES, nicht der Website (`SITE_BASE_URL` war bis 13.08.2026 falsch → 404 in jeder Bestätigungsmail) (Quelle `service/signup/app.py:103`).
- IP-Bremse des Signup-Dienstes ist keine Schutzmaßnahme: Zähler ist nach jedem Render-Spin-down leer (Quelle `service/signup/app.py:320`).
- `doi.yml` prüft die 24-Stunden-Sperre über einen Kennwert, der auch außerhalb des Tokens mitreist; die Adresse geht per Datei, nicht per Kommandozeile (Prozessliste/Actions-Log) (Quelle `service/signup/app.py:396`, `scripts/newsletter/abo.py:304`).
- Dispatch-Weg: die Seite bestätigt sofort, auch wenn der Dispatch klemmt; der Workflow ist wiederholbar (Quelle `service/signup/app.py:448`). Klemmt der Weiterreichweg, wird das ehrlich gemeldet (`app.py:403`).
- Newsletter-Versand: Stufe 1 schreibt und pusht den Plan, BEVOR die erste Mail rausgeht (Wiederanlauf nach Runner-Absturz); Stufe 2 rendert/stellt zu, im echten Workflow per Contents-API mit `sha`-Vorbedingung (schlägt bei paralleler Änderung fehl); Wächter läuft schon in Stufe 1 (Quelle `scripts/newsletter/send_digest.py:113,126,176`).
- Newsletter: Abmelde-URL ist Route des Signup-Dienstes, nicht der Website (Quelle `scripts/newsletter/send_digest.py:294`).
- Bounce-Sync merkt sich den zuletzt verarbeiteten Zeitpunkt, sonst werden Soft Bounces doppelt gezählt (Quelle `scripts/newsletter/bounce_sync.py:111`).
- Zeichen-/Pipe-Falle der Leiter: eigene Prozessgruppe, damit bei Fristüberschreitung auch pytest-xdist-Worker sterben (Quelle `scripts/pruefleiter.py:362`).

## Widersprüche
- `scripts/build_sources.py:1140`: Kommentar sagt, die Tabelle M sei seit Juli 2026 veraltet und ein Lauf überschreibe `config/watchlist.yaml`; der Code am Dateiende läuft laut Kommentar weiterhin als Generator – Hinweis ist eine Warnung, kein Widerspruch zum Code, aber das Skript ist damit faktisch tot (Wahrheitsquelle ist `config/watchlist.yaml`).
- `scripts/finde_quellen.py:161`: Kommentar „nur als json_api melden, wenn mehrere Datensätze“ passt, aber `("json" in ct or True)` ist immer wahr – Content-Type wird nicht geprüft (vorhandener Ruff-Befund SIM222).

## Wissen je Datei

### `docs/archiv/outputs/strategie-geraete-v3-2026-09-17/p5/pruef_live.py`
- nichts übernommen: Archivskript, Kommentare gliedern Prüfabschnitte. Wissen: Der Katalog deckelt die Standardansicht, die Suche macht die Zeile sichtbar, der Klick-Test läuft deshalb MIT Suchfilter (Zeile 89); Zeilen ohne Details dürfen beim Klick nichts öffnen (107); Katalog-/Hash-Sprünge aufs TCO-Modell zeigen `?modell=<id>`, danach muss der Titel des gewählten Modells erscheinen, kein stiller Rückfall (205); Querscroll 390 auch im Katalog-Reiter prüfen, Tabellen sind der kritische Fall (235).

### `docs/archiv/outputs/strategie-geraete-v3-2026-09-17/p5/pruef_live_2.py`
- nichts übernommen: Archivskript. Wissen: Deep-Link auf Modell ohne Zeitreihe darf still zurückfallen, aber kein toter/leerer Zustand (Zeile 85).

### `docs/entwuerfe/geraete-eine-seite-2026-09-16/historie_sammeln.py`
- nichts übernommen: Entwurfsskript. Wissen: derselbe Stichtag wie `zahlen_sammeln.py` (41); sku_id→modell_id gruppiert wie die Karten des Entwurfs (49); tarif_id→Band mit Live-Logik, unbegrenzt/fehlend = kein Band (58); Historie je (Modell, Band, Anbieter, Datum) auf das Minimum gefaltet (66); Bestandszahlen in `zahlen.json` bleiben unangetastet (108).

### `docs/entwuerfe/geraete-eine-seite-2026-09-16/zahlen_sammeln.py`
- nichts übernommen: Entwurfsskript. Wissen: fünf Anbieter wie der Bestand (ANBIETER_REIHENFOLGE + congstar, ERWARTETE_ANBIETER), Netzbetreiber zuerst, Zweitmarke daneben, Discounter ans Ende (26); 1&1 nennt EINEN Monatsbetrag für Tarif+Gerät (§ 13.2) → `buendel_monatlich`, `monatlich` ist None (46); Leerkarten der vier Festanbieter und die Vodafone-Näherung tragen absichtlich keine sku_id (122); Sortierung wie `_zeilen_rang`: TCO-24 aufsteigend, Referenz durch Hervorhebung statt Position (182); das Delta ist das des BANDES, nicht der Modellkarte – die Karte verschweigt Abstände unter der Wesentlichkeitsschwelle (3 %/15 EUR, Hausregel), der Band-Graph nennt sie; gelesen aus `m["baender"]`, nichts neu gerechnet (187); PM-7: Vorschau-Sortierung deterministisch, aktuelle Modelle (Bandabdeckung, Anbieter mit Bündel) zuerst, Auslaufware ans Ende; Suchindex nach Bandabdeckung vor Anbieterzahl vor Alphabet, ≤ 8 Treffer in der Live-Vorschau (209,230); 88 Gruppen in der Abweichungstabelle, Δ % aufsteigend (257).

### `scripts/bilder_nachholen.py`
- nichts übernommen: Wissen: Das Laufprotokoll muss mitziehen, sonst steht auf transparenz.html „31 von 40 Meldungen mit Bild“, während die Seite 147 zeigt (Zeile 89).

### `scripts/build_quellen_doc.py`
- nichts übernommen: Wissen: Sandbox ohne Headless-Browser sagt nichts über die Quelle, in Actions läuft sie normal; als Fehler ins Dokument zu schreiben wäre falsch (59).

### `scripts/build_sources.py`
- nichts übernommen: Regionsüberschriften und Spaltenreihenfolge (`region, name, country, website, aliases, kind, crawl_url, press_url, note, plan`). Wissen: Tabelle M ist seit dem Reparatur-Durchgang Juli 2026 veraltet und kann `item_selector`, `link_template`, `timeout_seconds`, `allow_short_titles` nicht ausdrücken; ein Lauf würde `config/watchlist.yaml` überschreiben und geprüfte Reparaturen löschen – dort direkt editieren (1140).

### `scripts/finde_promo_seiten.py`
- nichts übernommen: Listen/Deckel schon benannt. Wissen: Pfadwörter sind das verlässlichere Signal als Linktext (Werbesprache vs. CMS-vergebene Pfade) (56); Linktext schwächer gewichtet, fängt Kampagnen-ID-Pfade (105); Ausschlusspfade (Rechtstexte/Service) tragen dieselben Werbewörter im Fließtext und würden den Check teuer beschäftigen (125); Kandidatenpfade für Stufe 2 nach Wahrscheinlichkeit gereiht, gemessen an 15 konfigurierten Seiten (/angebote, /aktionen, /handytarife, /deals) (139); Deckel je Marke und Stufe, weil jeder Kandidat einen vollen Prüfabruf kostet (167); sehr tiefe Pfade sind meist Produkt-Detailseiten (Tiefenlink, keine eigene Quelle) (201); Weiterleitung auf Startseite = Treffer ohne Inhalt (265); Art der Leitseite (JS) gilt für weitere Seiten derselben Marke (320).

### `scripts/finde_quellen.py`
- `HTTP_CFG` (Zeile 78): Kurze Zeitgrenze (8 s) mit Absicht: in Breitensuche sind die meisten Adressen 404; ein Timeout kostet das Sechsfache eines Treffers (zwei User-Agents × drei Versuche).
- Pfadlisten (84, 104, 123, 126): Reihenfolge = Trefferwahrscheinlichkeit, bewusst kurz, jeder Eintrag kostet einen Abruf je Ziel; Newsroom-Pfade nur für nackte Domains (bei `--firmen` ist nur „telenor.no“ bekannt).
- `main` (291): Nur die Wurzel, nicht geratene Newsroom-Pfade, weil rel=alternate fast jedes CMS im head trägt; dreizehn Ratepfade je Firma waren der Grund, warum ein Durchgang über 112 Betreiber nicht fertig wurde.
- `configure_throttle` (387, jetzt Konstanten): Ohne Drosselung schlagen bei 16 gleichzeitigen Zielen rund 200 Verbindungen los, mehrere auf denselben Server.
- Sicherung nach jedem Ziel (448): bei 800 Zielen ist Abbruch die Regel.
- Stufen (235–248): 1 Selbstangabe der Seiten, 2 übliche Pfade, 3 /feed & Co. an genannten Seitenpfaden.

### `scripts/geaenderte_tests.py`
- nichts übernommen (Leiterskript, nur protokolliert): pytest liest bestimmte Namen für die ganze Datei, geändert treffen sie jeden Test (23); eine reine Löschung (Menge 0) trifft Zeilen davor und danach (108); Hilfen mit geänderten Namen gelten als geändert bis zum Fixpunkt (128).

### `scripts/geraete_abdeckung_mail.py`
- nichts übernommen: Rückgabecodes bereits benannt (`RUECKGABECODES`). Wissen siehe „Für docs/betrieb.md“ (Zeilen 55–128); `nur`: aus der Konfiguration gefallener Anbieter wird nicht mehr beobachtet und löst keine Ewigkeitsmail aus (103); „50 Läufe grün, sechs Tage ohne Telekom-Zeile“ ist die Fehlerklasse, gegen die der Wächter gebaut ist (92).

### `scripts/geraete_abdeckungswaechter.py`
- nichts übernommen: Eine Annotation je Befund, sie steht oben auf der Laufseite (51).

### `scripts/geraete_fragment_wachstum.py`
- nichts übernommen: Wissen: Die Empfehlung ist TEXT, kein Schalter; die Deckel-Entscheidung tragen Antonio/der PM am 01.10. (14 Tage echte Messdaten), nichts davon ist gebaut (59–64); Prognose linear ab dem letzten Messtag je Fragment-Grenze (158); das Bündel-Fragment wächst mit MODELLTIEFEN, nicht mit Messtagen, die Paar-Prognose traf es nicht, deshalb Stand gegen dieselbe Grenze gerechnet (216).

### `scripts/golden_aufnehmen.py`
- nichts übernommen: Wissen: Wenige Quellen über `collect.http`, keine Stufe mit eigenem Netzweg; klein fürs Repo, groß genug, dass jede LLM-Stufe etwas bekommt (40).

### `scripts/heile_ausgefallene_redaktion.py`
- nichts übernommen: Wissen: Dieselben zwei Formulierungen wie `pipeline.py` (keine neuen Meldungen vs. gescheiterte Bewertung) (52); „bewertete“ ist dieselbe ehrliche Zahl, die die Pipeline seit 05.09.2026 vor der Übernahme in `stats.bewertete` festhält (html.py: `n_bewertet` auf transparenz.html); hier per Vorbedingung 0, das macht den Bericht erst zum Heilungskandidaten (116).

### `scripts/kostenrechnung.py`
- `PREISE` (26): Stand 08/2026, api-docs.deepseek.com; doppelte Preise zu Pekinger Stoßzeiten, Cron 08:30 UTC = 16:30 Peking, deshalb beides ausgewiesen.
- `ANALYST_JE_MELDUNG_TOKEN` (36–49): Seit 15.08.2026 trägt `text` bis `ANALYST_TEXT_ZEICHEN` (2500) statt 300 (Wert stand bei 120, rund fünffach zu niedrig). Messung 15.08.2026 über 267 Feed-Einträge: 30 % Feed-Volltext (Median 2000 Zeichen, auf 2500 gekappt), Rest Teaser (Median 206) → im Mittel rund 800 Zeichen je Meldung, bei 4 Zeichen je Token gut 200 plus Metafelder. Nur Eingaberechnung (billige Hälfte), Aufschlag bei 1000 Meldungen je Lauf einige Cent im Monat. Wer die Grenze in `agents.py` anhebt, zieht den Wert mit.
- Redaktion (84): Stufe 1 je Bereich nur SEINE Meldungen; Stufe 2 nur Kurzfassungen und fünf Meldungen je Bereich.
- `ZIEL_BEREICHE` (151): Mehr Quellen heißen nicht mehr Regionen, aber mehr Themenfelder; zwei neue Kategorien kamen dazu, 16 ist eine vorsichtige Annahme.

### `scripts/leiter_pytest.py`
- nichts übernommen (Leiterskript): Kanarien auf Bestand, Netz und Quelltext müssen an ihrer Regel aus `tests/conftest.py` scheitern, sonst ist die Sperre dort abgeschaltet (25).

### `scripts/llm_probe4.py`
- nichts übernommen: Wissen: Eine 200er Antwort ist nicht automatisch Erfolg, der Endpunkt liefert gelegentlich leere choices oder Fehlerstruktur mit 200 (54); Voll-Payload 6 Regionen, 15 Items, 300 Themen; gekürzt 6/8/60 (116).

### `scripts/lokallauf_congstar.py`
- nichts übernommen: Wissen: Der Haken wird VOR dem Patchen gebaut, seine Closure hält den ECHTEN fetch fest und das Patchen des Modul-Attributs kann ihn nicht auf sich selbst zeigen lassen (wie beim Telekom-Lauf) (146).

### `scripts/lokallauf_einsundeins.py`
- nichts übernommen: Wissen: Haken-Reihenfolge wie bei B2/B3 (145).

### `scripts/lokallauf_einsundeins_simonly.py`
- nichts übernommen: Wissen: Haken sitzt auf dem Modul-Attribut, BEVOR `_hole_fabrik` `from .collect.http import fetch` ausführt, sonst ginge der Abruf am Beleg vorbei (121). Vierte Kopie des Hakens (Review B6; Telekom, congstar, einsundeins tragen dieselbe) bewusst kopiert, kein gemeinsames Modul (kein gemeinsamer Importbasis, Umbau über drei fertige Aufträge); wer den Haken ändert, ändert alle vier Stellen (126). Beleg wird AUCH bei Absturz geschrieben, robots-Abrufe stehen dann schon in der Liste (158).

### `scripts/lokallauf_telekom.py`
- nichts übernommen: Wissen: Laufzeitbeleg T1 misst die tatsächlich gesendete Kennung an `resp.request.headers`; ehrlich = beginnt mit „TelcoRadar/1.0“, alles andere wird als Befund ausgewiesen (310); `referenz_anbieter={"Telekom"}`: der Lauf schreibt NUR Telekom in die SIM-only-Referenzen und ruft die 1&1-SIM-only-Messung nicht auf (Befund Runde 2, 15.09.2026: ohne Scope datierte der Lauf 35 Fremd-Referenzen neu und lud 1&1); Name aus dem Tarifbestand (tarife.jsonl), nicht aus geraete_quellen.yaml, beide „Telekom“ (333); Manifest gehört zu JEDEM Lauf, auch gescheitert (exit_status=1), Nachtrag von Hand wie Runde 2 für den Lauf 15.09.2026 soll nicht wieder nötig sein (366).

### `scripts/migriere_seen_store.py`
- nichts übernommen: Nachprüfung, die MENGE der Hashes muss identisch sein (nacherzählt).

### `scripts/miss_artikelabruf.py`
- nichts übernommen: Je Quelle höchstens einen Artikel, sonst misst die Stichprobe ein Layout (100).

### `scripts/miss_fremdsprachen.py`
- nichts übernommen: Nicht `h["summary"]`, das ist die deutsche Analystenfassung (67).

### `scripts/miss_sammelphase.py`
- nichts übernommen: Hochrechnung auf 1000 Quellen bei gleicher Arbeitszeit je Quelle und gleicher effektiver Parallelität (76).

### `scripts/miss_volltext_quellen.py`
- nichts übernommen: `VOLLTEXT_AB = 1200` bereits benannt; Kappung des Teasers steht bei 600, alles darunter ist kein Volltext (44); gezählt wird, was ein Weg wirklich einbringt: Volltext aus Feed, egal welches Feld (209).

### `scripts/newsletter/abo.py`
- nichts übernommen: Wissen: Kein Detail nach außen, ob Token abgelaufen oder gefälscht (63); Doppel-Opt-in schweigt, damit nicht erkennbar ist, ob eine Adresse gerade angeschrieben wurde (93); kein List-Unsubscribe in der Bestätigungsmail, es gibt noch kein Abo (116); Vermerk (24-Stunden-Sperre) nur bei Erfolg, sonst sperrt eine gescheiterte Mail die Adresse (135); Domain-Allowlist auch im Store ausgewertet, der Dienst ist austauschbar (197); doppelter Klick: kein Fehler, kein zweites Abo (211); Wortlaut der Einwilligung kommt aus dem Token, nicht der heutigen Datei (Behörde fragt nach dem Text von damals); geänderter Text macht den Nachweis nicht ungültig (Hash von damals), kommt nur ins Protokoll (216,222); schon abgemeldet = kein Fehler (284); Adresse über Datei, nicht Argument (304).

### `scripts/newsletter/bounce_sync.py`
- nichts übernommen: Wissen: message_id→abo_id aus dem Sendeprotokoll (69); Hard Bounce ist kein Widerruf, die Adresse fällt nicht weg (Fehlklassifizierung bleibt rücknehmbar) (104); zuletzt verarbeiteter Zeitpunkt, sonst wird ein Soft Bounce doppelt gezählt und schaltet eine lebende Adresse ab (111).

### `scripts/newsletter/send_digest.py`
- nichts übernommen: Wissen siehe „Für docs/betrieb.md“ (113–177, 294); Abmelde-URL je Empfänger verschieden, aber nur einmal je Segment gerendert, Personalisierung durch Ersetzen der Platzhalter-URL; `versende()` sucht erst den vollen Sendeschlüssel, dann den Segmentschlüssel (153); Test zeigt den Geräteblock immer (Bericht vor P4 trägt ihn nicht, gerechnet aus dem Geräte-Stand des Checkouts), auch freitags (226,232); Trockenlauf stellt nichts zu, das Log darf es nicht behaupten (268).

### `scripts/pruefe_portal.py`
- nichts übernommen: Schwellen sind bereits benannte Konstanten. Wissen je Kriterium:
- Falz 900 px konservativ (16:9-Notebook mit Browserleisten) (95).
- Kriterium 12 Zeitungskopf (100): Marke als EIN String, am 11.08.2026 stand sie an elf Stellen; zulässiger Versatz `_MAX_KOPF_VERSATZ` 90 px gemessen: Kopf saß vor der Umbenennung 38 px links (1440) und 68 px bei 1180; zweiter Fehlerfall 169 px. Name „Vodafone Product and Services Insights“ 373 statt 214 px breit, lief auf dem Telefon in der ersten Fassung 61 px aus dem Bild (646).
- Bebilderte Meldungen als Quote (110): bis 07.08.2026 absolut 110 (Ausgabe 6.8., 193 Meldungen = 57 %); Ausgabe 7.8. 107 von 138 = 77 % fiel fälschlich durch.
- Promo: mindestens 10 verschiedene Bilder (117), Stand 07.08.2026: 15 Screenshots, genau einer kam an, leer; seit Umbau Kampagnenmotive (`promo_bilder.py`).
- Differenzierung (124): Bestand 08.08.2026 35 von 71 Beispielen mit Bild (5 geerbt, 30 per og:image); Schwelle darunter, weil Ausbeute an fremden Seiten hängt; hart: KEINE Karte ohne Motiv. Befund 08.08.2026: 77 Karten, null Bilder, 9060 px Höhe (Antonio: „total unübersichtlich“) (881).
- Suchseite (130,210): häufigster Absender als Begriff; nur ein Wort, da Suche mit UND verknüpft („O2 / Telefónica Deutschland“ fände sonst nur sich selbst).
- Seitenhöhe je Reiter (218): „unter 3 Bildschirmen“, alte Seite 18.412 px.
- Fließtext-Deckel (223, P4/D3, 18.09.2026, FM 4 „Text kriecht zurück“, Antonio: „Ich will keinen Text sehen. Alles so unruhig.“): gezählt Text aller `<p>` EINER Tafel inklusive Aufklapptext, nie `<template>`-Inhalt (Rechenweg-Pool von P1). Kalibrierung am Befund 17.09. (design.md: Vergleich 18 388 Z, Radar 8 359 Z): Radar 6000 (fällt mit der P4-Balkengrafik, −6 300 Z, auf rund 2 600 Z), Preisverlauf 2500 (der gefallene 1813-Zeichen-Datenblock allein füllte drei Viertel), Katalog 2500 (Tabelle, 377 Z am 18.09.), Vergleich 6000 (trägt 18 100 Z, fast alles in 20 Rechenweg-Aufklappern à ~500 Z; wird grün erst, wenn der Text als `<template>` folgt oder gekürzt wird; Entscheidung beim Lead/P5).
- Textblock unter Grafiken (261): design.md Regel 8; 200 Zeichen = Bildunterschrift ja, Datenblock nein.
- E2 Falz Telefon (377, 16.09.2026): Antwort-Satz und Graphkopf (Messtag-Zeile) am ECHTEN Bestand gemessen, nicht an der Browsertest-Fixture; ohne Antwort-Satz entfällt die Messung ohne Mangel.
- Chromium-Suche (486): zwei feste Linux-Pfade, sonst Playwright selbst (`executable_path=None`); sonst würden auf einem Mac fünf Kriterien übersprungen (übersprungen sieht aus wie bestanden; gleiche Lehre wie Chromium-Schritt in `ci.yml`, 09.08.2026); Grund gehört in die Bilanz (509).
- Kriterium 6 gilt für beide Seiten, hochskaliertes Bild war Befund 06.08.2026; seit 08.08.2026 auch Differenzierungs- und Suchseite (550,557).
- Kriterium 7 (588): bis 07.08.2026 „erste Meldung vor der Falz“, Seite 12 249 px hoch, acht Bildschirme bis „Geld & Übernahmen“; jetzt Oberkante der LETZTEN Ressortkachel.
- Kriterium 10 (609): Suchseite im BROWSER messen, alles entsteht in `app.js` nach `search_index.json`; statische Prüfung saß am 06.08.2026 sechs falschen Zahlen auf.
- Kriterium 4 (770): Ressortzahl seit 08.08.2026 EINMAL je Kachel (Link „alle 29 Meldungen“), vorher zusätzlich als Chip.
- Kriterium 5 (788): seit 08.08.2026 auch Wettbewerbsseite (Chronik aus Meldung und Analysten-Move), temporäre Themenseiten (Themenspeicher, wochenalte Meldungen), Differenzierung (Presse-Zweig mit rohen Zusammenfassungen); seit 10.08.2026 Geräteseite (Sätze der Karte „Was diese Woche auffällt“ tragen `szl`; `_kurz()`-Etiketten in `.gr-etikett` kürzen bewusst mit „…“). Dieser Zuschnitt deckte am 08.08.2026 37 Karten ohne Motiv.
- Kriterium 8c (858): jede Karte ein Motiv; bis 08.08.2026 galten kleine Textkarten als Absicht, 37 von 77 Karten, Rasterzeile so hoch wie höchste Karte → Lücke neben jedem Bild. Antonio: „da fehlen bei einigen Aktionen die Bilder, das wirkt so richtig scheisse.“ Differenzierung: Zeilen (dritte Gewichtsstufe) tragen bewusst kein Motiv (894); 9b Auswertung steht VOR den Beispielen und nennt dieselben Zahlen (Fehlertyp 06.08.2026) (916).
- Kriterium 11 Geräteradar (940): Positionskarte am 30.08.2026 GELÖSCHT (59 Geräte × vier Anbieter, 114 senkrecht gedrehte Achsenbeschriftungen, 155 von 164 Punkten ohne Beschriftung); Kriterium prüft, dass sie WEG ist. E2 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1a, 16.09.2026): Hauptansicht ist die TCO-Zeitreihe (SVG, Y=EUR-Ticks, X=echte Messtage, je Anbieter Linie mit Punkt je Messung; Antonio: „Den Graphen finde ich gut.“); die drei Verbote (gedrehter Text, Schrift unter 12 px, „...“-Beschriftung) misst `tests/test_geraete_reiter_browser.py` und `tests/test_geraete_zeitreihe_browser.py` im Chromium. Kein „übersprungen“, Seite fehlt = Totalausfall (962, CLAUDE.md §6).
- E3 (978, §1d): vier Tafeln auf einer Seite (Vergleich, Radar, Preisverlauf, Gerätekatalog); Radar-Link in der Leiste verboten, Portfolio-Tafel (`#tafel-portfolio`) bleibt weg; 28.09.2026: die zwei Ein-Gerät-Reiter („Mit Tarif“, „Ohne Vertrag“) nebeneinander, danach Übersicht und Katalog.
- E2 (1008): Balkenform (O1) ersetzt, Reste `.gr-hgraph`, `.gr-bz`, `.gr-balkenliste` verboten. P2 (Antonio F4, 17.09.2026): G2 gefallen (zwei echte Kurven eines Anbieters unter fünf Linien, vier Textblöcke, „mehr Text als Graf“); Reiterinhalt ist der Wähler, sein Datenknoten oder ehrlicher Leerzustand (1033). E3-Fix (QA 17.09.2026): G0 aus dem Verlaufs-Reiter gefallen (zwei Barpreis-Grafiken desselben Geräts, Doppel-Darstellung) (1060).
- Pflichtzeile aus A5.2 (Antonios Leitfrage) seit O2 (11.09.2026) im Rechenweg-Aufklapper jeder Bündel-Zeile mit Zahl (1078); kein Mangel bei fehlendem Datensatz, Vorlage rendert nur bei `verlauf.hat_daten` (auf GEPRÜFTEN Einträgen) (1087); Strukturhälfte „Grafik ist WEG“ gilt auch ohne Daten, nicht überspringen (1113).
- Alarmtabelle: O2 (11.09.2026) auf dem Wettbewerbsradar, seit E3 Schritt 3 (17.09.2026) Reiter „Radar“ dieser Seite, Alt-URL Weiterleitung (1105). Belegzwang Quelle UND Abrufdatum; `.gr-a-datum` statt `.gr-a-klein` (zweite Klasse steht zweimal in der Zeile, Datumshälfte war wirkungslos) (1129). Aufklapper zeigt mehr als einen Anbieter (1143); vier Kacheln zählen genau die verglichenen Kombinationen (1153); `start` kann None sein, Durchfaller statt AttributeError (1162); Grund IN die Zeile, sonst ging er in gepufferter Ausgabe verloren (1179).
- Kriterien 13/14 (1192,1214): Deckel statisch am gerenderten HTML, dieselbe Zahl wie `tests/test_geraete_textdeckel.py`.

### `scripts/pruefe_promo_seite.py`
- nichts übernommen: Schwellen bereits benannt. Wissen: Mindesttext 500 Zeichen: kleinste der 15 Bestandsseiten rund 1400, Weiterleitungs-/Zustimmungsseite unter 300 (84); verschiedene Angebotssignale, nicht Treffer (Wort „Angebot“ vierzigmal im Menü) (90); Dublettenschwelle 0.6 = `promo_store._same_offer`, Umformulierungen lagen darüber, unabhängige Inhalte deutlich darunter (93); unter Mindestwortzahl ist der Überlappungswert Rauschen → Vergleich NICHT durchführbar = Durchfaller (Lehre Session 5) (98); Signale bewusst grob, deutsch, sortieren Markenprosa/Rechtstexte aus (104); Mobilfunk gegen Festnetz als Übergewicht, nicht Wortverbot (121); Allerweltswörter würden Überlappung hochziehen (135); Kriterium 7 gegen jede bestehende Seite UND angenommene Kandidaten, schlechtester Wert zählt (Geschwisterseiten prepaid-allnet-s/m/l/xl) (325); Marke ohne Seite = legitimer Erstfall, Marke mit nicht abrufbaren Seiten = Durchfaller (335); Kennzahlen statt Kriterien: 08.08.2026 streuten die 15 Bestandsseiten von 0 bis 16 verschiedenen Preisen (449); `kind: js` in Sandbox nicht prüfbar; „In Session 2 waren 6 von 8 angeblich JS-toten Quellen in Wahrheit statisch abrufbar“ (549); Bewertung sequentiell in Eingabereihenfolge (573).

### `scripts/pruefe_quellenvorschlag.py`
- nichts übernommen: Schwellen bereits Konstanten (aus AUFTRAG_QUELLEN_AUSBAU.md Abschnitt 4, bewusst nicht als CLI-Schalter). Wissen: Kriterium 5b Anteil verschiedener Titel, gemessen am SEC-EDGAR-Feed von AT&T: 40 datierte Meldungen, alle „8-K - Current report“ (76); Kriterium 7 Überdeckungskoeffizient |A∩B|/min(|A|,|B|): libertyglobal.com/wp-json liefert 25 Meldungen und enthält alle 10 aus libertyglobal.com/feed; gegen Kandidatenmenge 40 %, gegen die kleinere 100 % (83); Verbreitungsdienste als Fremddomain erlaubt (offizieller Kanal), Begründung trotzdem ins YAML (96); Navigationslabels, Rubrikzeilen, Cookie-Banner (114); sehr kurz UND wenige Wörter = Menüpunkt, Collector lässt das nur mit `allow_short_titles` durch (182); Kriterium 10 Index der bestehenden Meldungs-URLs einmal aufgebaut (sonst bei 1000 Kandidaten mehrere tausend Abrufe, Weg in 429/403), geschlüsselt nach DOMAIN statt Betreiber (Themenquellen ohne Betreiber liefen ungeprüft durch; erster Massendurchgang: 15 von 34 bestanden fälschlich, URL-Varianten wie newsroom.arm.com/feed neben /rss, apple.com/newsroom/rss-feed.rss/rss) (306); Kriterium 8 newsroom_js in Sandbox nicht prüfbar, also nicht abnehmbar (428); Kriterium 1b zweiter Abruf (04.08.2026: newswire.ca lieferte 23 von 23 datiert, dann 30 Meldungen ganz ohne Datum), nur für geparste Seiten und auf Wunsch (verdoppelt Abrufe) (501); Kriterium 7b: Domain mit konfigurierter, aber leerer Quelle = nicht geprüft = kein PASS (overons.kpn/nieuws/feed/en/feed/ rutschte so durch) (647); Betreiber-Website aus Watchlist für Kriterium 6 (683); Drosselung, sonst schlagen 24 gleichzeitige Prüfungen auf denselben Server ein und 429 würde als „Quelle taugt nichts“ protokolliert (816); Wiederaufnahme aus Cache (849); Zeile der Durchgefallenen-Gründe ist bei 1000 Kandidaten die einzige gelesene (914).

### `scripts/pruefleiter.py`
- nichts übernommen (Leiterskript, nur protokolliert): Präfixe gesperrter Umgebungsvariablen (PYTEST_ADDOPTS, PYTEST_PLUGINS, RUFF_*, MYPYPATH, PYTHON*, Farben, GIT_*) (60); Plugin zuerst, ein gleichnamiges Modul unter `src/` verdeckt es nicht (180); eigene Prozessgruppe, damit bei Frist auch xdist-Worker sterben, sonst hielten sie die Pipes offen (362); ein Enkel in eigener Sitzung hält die Pipe, Ausgabe verloren (381).

### `scripts/quellen_trefferquote.py`
- nichts übernommen: Wissen: `neu` kommt aus Laufprotokoll (ab Lauf #68) oder Altbestand des Seen-Stores; nur der erste Weg rechnet je Lauf und Kanal (64).

### `scripts/quellen_zaehlen.py`
- nichts übernommen: `| head` schließt die Pipe, Normalfall beim Nachschauen (174).

### `scripts/rescue_sources.py`
- nichts übernommen: Ausgabe in Originalreihenfolge für stabile Diffs.

### `scripts/schiess_screenshot.py`
- nichts übernommen: Wissen: Zwei Formate (1440/390) wie `tests/test_falz_browser.py` (49); Messung je FLÄCHE, Geometrie aus data-Attributen (erster Anlauf las sie aus dem Modul, Bandform hat anderen unteren Rand 148 statt 70 → ~20 % Scheinabweichung); Etikettengegenprobe entfiel am 30.08.2026 mit der Positionskarte (Import `geraete_karte` warf unbemerkt ImportError); Ersatz `tests/test_geraete_reiter_browser.py` (kein gedrehter Text, keine Schrift unter 12 px, keine „...“-Beschriftung); das Skript bleibt zum Fotografieren (109); Durchscrollen, sonst bleiben lazy geladene Bilder leer (182).

### `scripts/schnappschuss.py`
- nichts übernommen: Was `render_site` aus dem Bestand liest, ohne Bilder; Historie nur für vier Geräte (26).

### `scripts/sniff_xhr.py`
- nichts übernommen: Cookie-Consent-Buttons anklicken, falls sie XHRs blockieren (nacherzählt).

### `scripts/spike_saturn_geraetepreis.py`
- nichts übernommen (Spike): Wissen: robots.txt am 05.09.2026 gelesen (User-agent: *) sperrt exakt zwei GraphQL-Operationen; Liste ist die VOLLSTÄNDIGE Disallow-Liste der „*“-Gruppe, Block-Regex und Audit lesen aus derselben Liste (59); Eintrag MIT Ratenplan bevorzugt (vollständigere Fassung derselben Zahl) (270); Review-Befund 05.09.2026: passive Seitenlast löst Requests auf disallow’te Pfade aus (Cloudflare-Challenge-Skript, Chat-Ping /api/v1/msg, Tracking-Cookie /public/setCookie/), werden wie die Tabu-Operationen abgefangen (376); Route-Matcher auf „**/*“ löste unter Playwright 1.61 + Python 3.14 internen Fehler in `route.continue_()` aus, daher enger Regex aus derselben Disallow-Liste plus „graphql“ (392); GraphQL-Antworten unabhängig vom Resource-Type gezählt (417); Cookie-Banner neutral wegklicken (456); Netzruhe aktiv abwarten, 20-s-Fenster nicht erreicht = ECHTER Befund (471); Screenshot als Gegenprobe (487); Dubletten über (url, status) entfernt (504).

### `scripts/validate_promo_sources.py`
- nichts übernommen: Prüfung je SEITE, nicht je Marke (seit 08.08.2026 mehrere Seiten je Marke), sonst sähe eine Marke mit laufender Leitseite und drei toten Seiten gesund aus (51).

### `scripts/validate_sources.py`
- nichts übernommen: Themenquellen (`config/tech_sources.yaml`) gehören in denselben Gesundheits-Check, dritte Signalebene (67).

### `scripts/waechter.py`
- nichts übernommen (Leiterskript): Vergleich mit dem letzten lesbaren Wert, unlesbare Zwischenfassung versteckt keine Verschiebung (170); addopts nur verschärfend (strenge Marker/Konfiguration, Socket-Sperre bis lokale Adresse, Parallelität, Frist je Test) (309).

### `scripts/waechter_claude.py`
- nichts übernommen (Leiterskript): `env` könnte PATH/PYTHONPATH umbiegen (23); Sekunden je Unterbefehl, `make venv` im Sitzungsstart am längsten (25); erlaubte Aufrufer, danach Skriptpfad und Unterbefehl (27).

### `scripts/waechter_regeln.py`
- nichts übernommen (Leiterskript): Modul gleichen Namens wie das Leiter-Plugin verdeckt es auf dem Suchpfad (26); Wanduhren über Importe aufgelöst (`from time import time as t`) (63); Eingriffe in pytest/Leiter nur in Leiterdateien erlaubt, Zeichenkette zusammengesetzt, damit die Datei die Regel nicht selbst auslöst (78,87); pytest liest addopts aus `[tool.pytest.ini_options]` und `[tool.pytest]` (148).

### `scripts/waechter_tests.py`
- nichts übernommen (Leiterskript): Tests von Hermetik und Leiter legen selbst eine conftest.py an (39); Vorgabe für norecursedirs/python_files (46); Kanarie sammelt nur `-o python_files`, bleibt verborgen (51).

### `service/signup/app.py`
- nichts übernommen: Wissen siehe „Für docs/betrieb.md“ und: Dienst im selben Repo, eigener Prozess, Pfad macht `telco_radar.newsletter` importierbar ohne Installation (Render checkt das Repo aus) (53); neutrale Antwort gleich über alle Zweige (Honeypot, IP-Bremse, abgelehnte Nonce, Domainliste, Erfolg); bis 13.08.2026 stand „Wenn alles stimmt, ist eine Bestätigungsmail unterwegs“, der Vorbehalt wirkte wie Zweifel; nie die Antwort vom Ausgang abhängig machen (70); leeres Dispatch-Repo, nicht der Store (96); CORS (127): Preflight `OPTIONS /subscribe` → 405 und `GET /form-token` ohne `Access-Control-Allow-Origin`; gefunden 13.08.2026, als Antonio auf der fertigen Seite keine Anmeldemöglichkeit fand; TestClient erzwingt CORS nicht, der Test schickt deshalb `Origin` und prüft Antwortkopfzeilen; bewusst kein „*“; kein `allow_credentials=True` (keine Cookies/Auth-Header) (167); `Referrer-Policy: no-referrer`, sonst reist das Bestätigungstoken im Referer (190); Endpunkt-Reihenfolge: 1 Honeypot (erkennbare Ablehnung wäre Bauanleitung), 2 IP-Bremse, 3 signierte Nonce (Mindestalter 2 s), 4 Eingabeform als LISTE, 5 Einwilligung inkl. Fassung, 6 Domain-Allowlist (Stand leer, Festlegung 3, trotzdem ausgewertet, Abgewiesene bekommen neutrale Antwort), 7 Token (313–371); Kennwerte reisen mit, sonst steht beim Bestätigen die IP des Klicks im Protokoll statt der der Einwilligung (380); Seite bestätigt sofort, sonst zweiter Klick und zwei Abos (448).

### `service/signup/ratelimit.py`
- nichts übernommen: `max_absender=5000` bereits Parameter; Deckel gegen Speicherangriff (rotierende Proxy-Adressen reichen) (32); Fenster abgelaufene verwerfen, sonst fällt der älteste Rest mit, großzügige Bremse besser als nicht antwortende Instanz (53).

### `service/signup/tokens.py`
- nichts übernommen: Konstanten bereits benannt (`TTL_BESTAETIGUNG`, `NONCE_MIN`, `NONCE_MAX`, `ZUKUNFT_TOLERANZ_SEKUNDEN`). Wissen: Zweck-Präfix in der Schlüsselableitung, sonst wäre eine Nonce aus `/form-token` ein gültiges Bestätigungstoken (42); 72 Stunden: kürzer unhöflich (Freitagabend), länger macht abgefangenes Token unnötig lange brauchbar (50); Nonce mindestens 2 Sekunden, höchstens 2 Stunden alt (54); Zweck in die SIGNATUR, nicht nur die Nutzlast (80); Nutzlast aus der Zukunft = verstellte Uhr oder Ablaufangriff, eine Minute Toleranz (124).
