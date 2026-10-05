# Kommentarwissen 09-pipelines-wurzel

Stand: Commit aaa8b0d, 11 Dateien, 1030 Kommentarzeilen.

## Übernahmen in Code
- `src/telco_radar/promo_bilder.py`: Konstante `KANDIDATEN_JE_ANGEBOT` ersetzt `3` in `zuordnen` – bis zu drei Bildkandidaten je Angebot, weil der erste beim Abruf durchfallen kann.
- `src/telco_radar/textwerkzeug.py`: Konstante `MIND_ZIFFERN_BELEGPFLICHT` ersetzt `<= 1` (jetzt `< 2`) in `ungedeckte_zahl` – einstellige Zahlen brauchen keinen Beleg.
- `src/telco_radar/geraete_pipeline.py`: Konstante `UNBEKANNTE_TITEL_MAX` ersetzt `40` bei `unbekannte_titel` in der Bilanz – Liste gedeckelt, Zahl `unbekannte_titel_gesamt` nicht; zwei Kommentarzeilen dafür gestrichen (Datei bleibt bei 1017 Zeilen, Grenze 1018).

## Für docs/betrieb.md
- Lauf 31422689829 (10.08.2026): Kernlauf fertig 19:54:48 (44:39 nach Jobbeginn), Geräte-Stufe startete mit 10 min Budget in einen Job mit 5 min Rest, Job-Timeout 19:59:46; weil die Stufe vor Rendern und Commit steht, wurde nichts veröffentlicht. Lehre: Zeitbudget rechnet gegen die Restzeit des Jobs (`src/telco_radar/pipeline.py:1339`).
- Geräte-Stufe im Wochenlauf aus (`geraete_enabled: false`); eigener nächtlicher Job `geraete.yml` im Besuchsfenster zweier Händler (robots.txt: Abrufe nur 02:00–08:00) (`pipeline.py:1335`).
- Übersetzungsstufe steht vor dem Rendern und rechnet ihr Budget gegen Restzeit des Jobs abzüglich Reserve fürs Veröffentlichen (`pipeline.py:1648`).
- Der Kernlauf lag am 10.08.2026 bei rund 27 Minuten, im Fall oben bei 44:39 (`pipeline.py:1334`).
- Anbieter-Schlüssel: `LLM_API_KEY` ist der eine gemeinsame Schlüssel aller OpenAI-kompatiblen Anbieter (NVIDIA, DeepSeek); der Anthropic-Schlüssel bleibt immer gesetzt als Rettungsanker der Modellketten (E2 Strategie 27.08.2026). Sieben Läufe 15.–27.08.2026 ohne Wochenbericht, weil DeepSeek-Guthaben leer war und der Anker gelöscht wurde (`pipeline.py:84-172`).
- Lauf #64 (04.08.2026): Anthropic-Guthaben leer, jeder Analysten-Stapel HTTP 400, 223 ungelesene Meldungen wanderten trotzdem in den Seen-Store (`pipeline.py:1606`).
- Geräte-Nachtjob: Alarm bei Quellentod geht seit 22.09.2026 an drei Kanäle: Actions-Log, Quellenseite (`report/geraete_view.py`), Mail (`sende_alarm_mail`, Versandschritt in `geraete.yml`). Vorher 50 grüne Läufe, darunter sechs Tage ohne Telekom-Zeile (`geraete_pipeline.py:131`).
- Ein Fehler in der Bündel-/Referenzstufe darf den Geräte-Bestand nicht kosten, er ist da schon gespeichert; ein Messtag ist nicht nachholbar (Lauf 31422689829) (`geraete_pipeline.py:770`).
- `radar.yml`-Fortschreibung: Fragmentgröße der Zeitreihe als Protokollzeile; Deckel-Entscheidung am 01.10. braucht die Reihe (`geraete_pipeline.py:977`).
- Versand: Mail fest montags (`STANDARD_WOCHENTAG = 0`), Teams nur als Ausnahme und jede Meldung genau einmal; Versand ganz zuletzt und failsafe (`versand.py:52,375,396`; `pipeline.py:1733`).
- Zeitbudget Standard Geräte-Stufe 900 s, `geraete.yml` übergibt `FRIST_TAGESLAUF` = 1500 s; Stufe 0 hält beide Werte des Workflows daran (`geraete_pipeline.py:66`).

## Widersprüche
- `src/telco_radar/pipeline.py:1335`: „Der Tageslauf startet um 08:30 UTC“ – `radar.yml` läuft laut CLAUDE.md Mi und Fr 11:00 UTC, die Geräte-Stufe im Wochenlauf ist aus. Kommentar veraltet.
- `src/telco_radar/geraete_pipeline.py:67`: „Zehn Sekunden je Abruf“ steht an `FRIST_STANDARD = 900.0`, die Zahl gehört aber zum Abstand je Abruf (Crawl-Delay), nicht zur Konstante; kein Codefehler.

## Wissen je Datei

### `src/telco_radar/config.py`
- Quellenarten (Zeile 15-30): rss, json_api, newsroom, newsroom_js, official; jede Betreiberquelle zeigt auf die eigene offizielle Domain, Fachpresse ist eine eigene, gekennzeichnete zweite Ebene; `official` = verifizierter Verweis, nicht gecrawlt, mit Plan zur späteren Aktivierung.
- `THEME_PREFIX` (33): Pseudo-Regionsschlüssel `thema:`; Themenfeld bekommt eigenen Analysten, Alias-Tagging und Rundlauf-Sortierung fassen nur echte Regionsschlüssel an.
- `Source`-Felder (47-99): `json_api` URL aus Record-Feld per `str.format_map`; `headers` für öffentlichen Client-Key (Verizon, kein Geheimnis); `exclude_url_regex` gegen gespiegelte Zweitsprachen (`/news/es/`); `timeout` je Quelle, weil KT in 3 von 9 Läufen am globalen 20-s-Connect-Timeout scheiterte.
- `region` (67-81): Fachpresse ohne Betreiber in Überschrift fiele nach „Global“; Lauf #75 schloss EUROPA mit null bewerteten Meldungen ab, „Global“ bekam 62 von 92, seit Session 5 deutsche, französische, spanische, italienische, portugiesische Feeds (davor 14 englische). Betreibername in der Überschrift schlägt die Vorgabe (Verizon in deutschem Feed → Nordamerika).
- `thema` (83): Themenquellen haben keine Region und stehen deshalb in `tech_sources.yaml`, nicht in der Watchlist.
- Redaktionsangaben `herkunft`, `abgenommen` (87-94): bei 130 Quellen reichte YAML-Kommentar, bei 1000 nicht; Messwerte (seit wann bekannt, zuletzt geliefert) pflegt `data/state/quellen_register.json`.
- `kurzer_titel` (95-99): Opt-in senkt Titelmindestlänge von 25 auf 6 Zeichen (RNS-/Regulierungstabellen wie „Q1 Results“); bewusst kein allgemeines Aufweichen, sonst kämen Navigationstexte („About Us“) durch.
- Zeile 141-145: Themenfelder (KI-Anbieter, Geräte, Chips, Netzausrüster, Satellit, Regulierung), eigener Namensraum über `THEME_PREFIX`.
- Zeile 176: Zusatz-Betreiber liegen in eigener Datei, Merge nach Regionsschlüssel.
- `kind` Fachpresse (228-234): bis 08/2026 fest `trade_press`; Capacity Media (erste Fachpresse mit JSON-API) lief in den RSS-Parser: „unparseable feed: syntax error“. Der Typ gewinnt jetzt, `trade_press` bleibt Normalfall RSS.
- Region-Prüfung (256): unbekannte Vorgabe-Region wäre ein Analystenbereich mit Tippfehler als Name; deshalb laute Warnung.

### `src/telco_radar/dedupe.py`
- nichts übernommen: einziger Kommentar (Zeile 87) sagt, v1-Altbestand wird gelesen, nie geschrieben.

### `src/telco_radar/geraete_pipeline.py`
- `FRIST_STANDARD`/`FRIST_TAGESLAUF` (66): Voreinstellung; `geraete.yml` übergibt `FRIST_TAGESLAUF`; Stufe 0 hält beide Werte des Workflows daran. Zehn Sekunden Abstand je Abruf.
- `_hole_fabrik` (101-113): `user_agent` ist Per-Anbieter-Überschreiber (Entscheidung E-1: globales `http_cfg` aus `settings.yaml` bleibt für alle anderen unangetastet); der Statuscode ist die Auskunft (404 ≠ 403 ≠ kein Netz).
- Quellentod (121-136): Abdeckungswächter vergleicht Zeilen je Anbieter mit dem Vortag (`GeraeteDB.ausfall_alarme`); Provider-Probe zählt, wie viele erwartete Sätze ihre Feldebenen tragen (Präzedenz Phase S: metric3+metric2 == monthlyPrice, damals 66/66). Drei Kanäle seit 22.09.2026, ein Satz im Alarmobjekt.
- Zeile 200: „gar nicht angefasst“ = keine gelesene Einstiegsseite, keine Listung, kein Bündelsatz (alle drei, Telekom liefert nur Bündel).
- Zeile 315: Prozent wird abgerundet, nur exakt bestanden == erwartete heißt „100 %“ (199 von 200 nicht; S3 der P5-Codeprüfung).
- Robots-Wächter (377-398): ein Wächter je Anbieter, robots.txt einmal je Haken im Cache; robots-Abruf trägt den Absender des Anbieters (B2, 08.09.2026; 1&1 hat eigenen UA und einen Haken); `ua=user_agent` bindet den Wert dieses Durchlaufs, sonst läse die Lambda die Schleifenvariable. Haken-Abrufe tragen seit 29.09.2026 denselben Absender (1&1-Haken holt neun Seiten mehr, Tarifstufen).
- Zeile 464: `x or y` verboten: ein Test mit Laufbeginn auf Mitternacht UTC übergibt ein falsy datetime und bekäme still die echte Uhr; relevant, weil die Uhr je Abruf gegen das Besuchsfenster rechnet.
- Zeile 474: `lade_katalog` mergt Auto-Einträge aus dem STATE; Hand-Eintrag schlägt (gleiche `device_id` bleibt, Rest an Kollisionswächter).
- Zeile 506: Historienpunkt nur für, was die DB genommen hat. Bis 04.09.2026 schrieb die Schleife den verworfenen zweiten Satz derselben ID trotzdem: ALDI TALK „Galaxy A17 LTE + Starter Kit“ (129 EUR) und „Galaxy A17 5G“ (159 EUR) teilen eine Listungs-ID; 13 von 15 Pfeilen in G2 zeigten eine nie erfolgte Preisänderung (QA-Befund B2).
- Zeile 521: `db.kollisionen` gilt je Aufruf, deshalb über alle Anbieter sammeln.
- Buchführung (537-552): `laeufe` zählt nur vollständige Läufe (sonst würde ein Ausfall eine Marke zum SIM-only-Anbieter machen); Messtermine = jeder Tag mit gesehenen Listungen, auch Teillauf. mobilcom-debitel wurde am Zeitbudget nie fertig und fehlte in der Bilanz. Seit 22.09.2026 (P1/C2) wird jeder Anbieter ins Journal geschrieben; die alte Bedingung `vollstaendig or listungen` ließ den Ausfalltag spurlos.
- Zeile 575/581: Probenzähler leer, wenn Adapter keine kennt; Zahl der toten Adressen steht im Protokoll (Grund, warum ein Lauf mit Lücken vollständig heißt), dieselben zwei Werte wie im Bestand (Clean Code 7).
- Maßstab (595-628): `geraete_tco.json` gab es bis 04.09.2026 nicht (null Bündel, null Referenzen). Reihenfolge fest: Referenzen aus `tarife.jsonl`, dann Bündel (`kind: buendel`); ein Bündel ohne auflösbaren Tarif wird verworfen; ein `Tarifbestand`, einmal geladen. Berechnet im nächtlichen Lauf, nicht im Renderer (zwei Ableitungen = zwei Zahlen). B1 (05.09.2026): Vodafone nennt nur Hash statt Tarifname, gezielter Zweitabruf je Gerät (`vodafone.loese_tarifnamen`) hier, nicht im Adapter (`lies_buendel` bleibt netzfrei). S2-C (09.09.2026): Betrags-Haken `Adapter.ergaenze_buendel` (1&1-Bereitstellungsgebühr im Tarifdetails-Iframe) läuft nach dem Sammeln, vor `aus_rohsaetzen`.
- congstar-Brücke (641-652, B3, 08.09.2026): congstar nummeriert Tarif und Pflichtblatt gleich (PlanVariant 540 ↔ `Produktinformationsblatt_540.pdf`); ohne sie fielen vier von acht PlanVarianten unter „ohne auflösbaren Tarif“. Zur Laufzeit, nicht dauerhaft am Bestand; Zeitreihe in `tarife.jsonl` bleibt unberührt.
- Leere-Wächter (657-665): `Tarifbestand.aus_datei` liefert bei fehlender Datei einen leeren Bestand; `ersetze_referenzen` löschte sonst den ganzen Maßstab (Baseline-Reset, Merge-Konflikt, Wettlauf mit `radar.yml`). Gleiche Fehlerklasse wie `promo_store.mark_stale` ohne `gepruefte_seiten` (CLAUDE.md §6).
- 1&1-SIM-only (673-695, S-5, 09.09.2026): Messung von der SIM-only-Seite (`collect/tarif_einsundeins_simonly.py`) ersetzt für diesen Anbieter die Ableitung aus ld+json von `/handytarife` (Name und Grundgebühr, ohne Phase/Volumen/Anschlusspreis); schlechtere Lesart bleibt im Bestand (wie `_bevorzugt_live`). Bei Fehlschlag bleiben Bestandsreferenzen; Merge steht unter dem Leere-Wächter; Scope entscheidet über den Abruf (Befund Runde 2: 10 Requests an 1und1.de aus dem Telekom-Lauf vom 15.09.2026).
- Zeile 712 (Review B3, 09.09.2026): nur ersetzen, was die Messung auch misst; pauschaler Anbieter-Filter würde Tarife aus der Ersetzungsmenge nehmen, deren Bestandssätze `ersetze_referenzen` dann löscht. Zahl der Rückfälle steht im Protokoll.
- Zeile 742/754: Referenzen werden ERSETZT (abgeleitet, sonst wüchse der Bestand bei Umbenennung), Bündel AUFGEFRISCHT (Messung; Ausfall ≠ „gibt es nicht mehr“, wie `GeraeteDB`).
- Zeile 764/770: Bilanz erst nach `save()` (kann werfen); Fehler hier darf den schon gespeicherten Bestand nicht kosten.
- Zeile 780: Bündelzeile auch bei null: „0 von 0“ = kein Anbieter liefert Bündel, „0 von 63“ = Tarifbestand trägt ihre Tarife nicht.
- Zeile 796-808: Kollisionen als Katalog-Arbeitsliste; Auto-Katalog und unbekannte Titel/Farben sind STATE, vom Lauf geschrieben (`geraete.yml` committet), nie von Hand.
- `UNBEKANNTE_TITEL_MAX` (843, übernommen): Liste gedeckelt, Zahl nicht; sonst meldet ein Lauf mit 300 unerkannten Titeln genau 40 und sieht harmlos aus.
- Zeile 850-863: `rohbuendel` (geliefert) vs. `buendel` (mit Tarif im Bestand); Referenzen 0 bei gefülltem `tarife.jsonl` heißt Schreibversuch geworfen.
- Zeile 881/896: Zahlen in die Zeile (84 Listungen und trotzdem „fehler“ ist erklärbar, wenn das Protokoll die 84 nennt); eigene Zeile für tote Adressen auch bei Status „ok“, sonst wächst die Lücke still bis zur Schwelle.
- Zeile 912-934: Alarm und Probe greifen in nichts ein (Auslistung bleibt allein an `vollstaendig` gebunden); `nur` begrenzt auf diesen Lauf; `heute` wird übergeben, damit ein nachgereichter älterer Tag seine eigene Abdeckung beurteilt; Alarm in die Bilanz, nicht nur ins Log; Katalog-Arbeitsliste nur im Protokoll, weil der nächtliche Lauf an niemanden zurückgibt.
- Zeile 947: Modelle ohne Marktstartdatum (ohne sie keine Nachfolger-Analyse) und Vorgänger-Bezüge ohne Katalogmodell; standen bis 03.09.2026 in der Sektion „Datenbasis und Lücken“ auf `geraete.html`, Antonio hat die Sektion kassiert; Protokoll ist der Kanal.
- Zeile 977 (PM-6/P5 Auftrag 4, 18.09.2026): Fragmentgröße als einzeilige Protokollzeile (Messtage, Messpaare, Fragment-KB) aus derselben Funktion wie `scripts/geraete_fragment_wachstum.py`; Frühindikator aus Premortem FM 3; Deckel-Entscheidung am 01.10.; bewusst am Ende und nur lesend, Fragmente auf Platte stammen vom letzten Render; fehlt die Historie, bleibt die Zeile weg (kein 0/0/0).
- Zeile 59/1017: Import von `geraete_fragment` nur lesend; `# pragma: no cover` bleibt.

### `src/telco_radar/golden.py`
- `UMGEBUNG` (Zeile 37): alles, was der Lauf aus der Umgebung liest; die Wiedergabe setzt nur Schlüssel, die bei der Aufnahme da waren, mit Ersatzwert. Der Name der Konstante trägt das bereits.

### `src/telco_radar/pipeline.py`
- `_GERAETE_MINDESTBUDGET` (57): unter 240 s Restzeit lohnt die Geräte-Stufe nicht (ein Anbieter mit 10 s Abstand je Abruf braucht Minuten, halber Abruf ist kein gelesener Anbieter). Bereits benannt.
- `_VORSORTIERUNG_MINDESTBUDGET` (429): unter 60 s Restzeit keine Vorsortierung; spart Geld, keine Zeit, halber Durchlauf spart halben Anteil. Bereits benannt.
- LLM-Anbieter (84-172): OpenAI-Protokoll-Anbieter teilen EINEN Schlüssel `LLM_API_KEY`, nur einer aktiv; Basis-URL muss in `_waehle_anbieter` gesetzt werden (`llm.py` erkennt OpenAI-Zweig nur an Schlüssel UND Basis, sonst wählt es still anderen Anbieter), kein `setdefault`. Anthropic-Schlüssel bleibt als Rettungsanker (E2, 27.08.2026): `llm._dispatch` routet seit 27.08.2026 je Modell (`claude-*` → Anthropic); Tippfehler in der DeepSeek-URL lässt unbekannte Modell-ID auflaufen statt teurem Anbieter. Früheres Löschen kostete sieben Läufe 15.–27.08.2026.
- Zeile 132: gewählter Anbieter ohne Schlüssel lässt jede Stufe scheitern, einmal deutlich sagen.
- Zeile 189 (Bedrock): welche Claude-Modelle ein Konto aufrufen darf, ist je Konto und ändert sich ohne Ankündigung; deshalb Präferenzkette registrieren, der Lauf nimmt das beste antwortende.
- Zeile 199: nie Schlüssel eines anderen OpenAI-kompatiblen Anbieters lesen (zeigen auf inaktiven Endpunkt).
- `ANKER_REDAKTION`/`ANKER_MECHANIK` (230): beides Claude-IDs, von `llm._dispatch` an Anthropic geroutet, egal welcher Anbieter.
- Zeile 322: nie Anker hinter Anker (sonst Ausfall über Sonnet nach Haiku statt direkt ins richtige Modell, Redaktion würde klein).
- Zeile 361: Kostenwarnung ist nur Warnung, Lauf ist fertig; steht hier, damit die Zahl vor der Abrechnung auffällt.
- Zeile 573: Betreiber mit datiertem neuestem Eintrag zuerst, damit undatierte Seiten keine verifizierbar frische Meldung verdrängen.
- Zeile 603-614: Editor-Modell ist das große und verliert bei Überlast zuerst den Slot (Verbindung angenommen, nie ein Token); vier Stufen laufen darauf, ohne Ersatz brennt ein Ausfall das 4-fache Retry-Budget und das Job-Timeout tötet den Lauf vor dem Veröffentlichen; Analystenmodell als Ersatz, erst nach einem harten Fehler. Anker erst danach registrieren.
- Zeile 636: `max_items_per_region` 0/fehlend = keine Kappung.
- Zeile 651-733: Nebenstufen alle failsafe. Änderungsradar: wichtigste Preisbewegungen stehen nur auf der Tarifseite; Meldungen tragen eigene `id` (URL + Inhalt), sonst hielte der Seen-Store die zweite Preisänderung für berichtet. Lieferzeit-Radar: keine öffentliche Studie, Eigenwissen, eigener Speicher. Tarif-Sammler: Produktinformationsblätter nach § 1 TK-TransparenzV sind einzige rechtlich wahrheitsbewehrte Quelle, wöchentlich. CT-Radar: einzige Ebene VOR der Veröffentlichung, Meldungen sind Indizien; `use_llm` fällt später, hier zählt nur ob ein Backend erreichbar ist, ohne Modell läuft der Radar ohne Aussortierstufe.
- Zeile 761-773: Neue Meldungen je Quelle ins Laufprotokoll = Nenner der Trefferquote (`scripts/quellen_trefferquote.py`); „gesammelt“ taugt nicht (Newsroom liefert bei jedem Abruf dieselben 30). Quarantäne entscheidet an „hat geliefert“, erst nach der Delta-Schicht verbuchen.
- Ereignis-Cluster (794-835): Seen-Store dedupliziert URL, nicht Ereignis; Ausgabe vom 07.08.2026 hatte zwei Varianten derselben rumänischen Spamfilter-Ankündigung auf Platz 2 und 5. Sortierung vor Gruppierung nach Datum absteigend (frischeste führt). Bereits Berichtetes nur bei praktisch gleicher Überschrift innerhalb 72 Stunden (`clustering.SCHWELLE_SICHER`); „eine falsche Verbindung ist schlimmer als keine“. Beleg gilt nur als erledigt, wenn sein Vertreter gelesen wurde.
- Vorsortierung (863): am 27.08.2026 gingen 890 Ereignisse in den Analysten, 362 kamen heraus; Vorsortier-Modell schreibt je Aufruf ~8-9k Token Denkspur. Aussortiertes gilt als gelesen (bewusst verworfen), Sicherungen im Modulkopf von `analyze/vorsortierung.py`.
- Analyse (889-940): ausgefallene Regionen und gescheiterte Stapel nicht in den Seen-Store (Lauf #67: 2 von 3 Stapeln eines Themenfelds fielen aus, ~33 ungelesene Meldungen wanderten trotzdem hinein). Analysten parallel je Region (~6 Aufrufe, ~9x sequenziell → ~1-2x), zweite Ebene Stapel innerhalb der Region; Analystenanker je Aufruf, weil Modellname mit Redaktion geteilt (siehe `llm._kette`).
- Zeile 972: nur Themenfelder mit bewerteten Meldungen, sonst verlangt der Editor-Check eine Überschrift ohne Inhalt.
- Zeile 1079 (CTM-Linse): zweite Achse „für UNS wichtig?“, nach Analysten, vor Sortierung; Stufe 3 rechnet der Code aus `config/ctm_fokus.yaml`, Stufen 0-2 das Modell; Prüflauf gegen Originaltext, weil ein plausibel klingender Fehler das Risiko ist.
- Zeile 1132: Wettbewerber-Analyse zunächst mit Modell des aktiven Anbieters; seit c9c30f1 (DeepSeek, 04.08.2026) schickte sie „deepseek-ai/deepseek-v4-flash“ an den Endpunkt, der nur „deepseek-v4-flash“ kennt; alle drei Profile scheiterten in 0,6 s, Seite leer in Lauf #74 und #75. Seit 27.08.2026 Redaktionsmodell (Steckbrief ist Text, keine Mechanik).
- Zeile 1174-1189: Quellen-URL des Kanals an der Meldung (Newsroom und IR tragen denselben Anzeigenamen, sonst keine Trefferquote je Kanal); Feed-Bild kostet keinen Abruf; weitere Quellen desselben Ereignisses als Wichtigkeitsindikator an der Meldung.
- Bilder (1200): JEDE Meldung wird versucht; bis 06.08.2026 Deckel 40, 153 von 193 Meldungen wurden nie gefragt. Fehlschlag folgenlos (viele Fachpressen 403).
- Highlight-Themen (1220-1234): nach der Bilderphase, damit Themen Bilder mitbringen; Redaktionsmodell, weil der Themen-Agent ein Ereignis benennt und Firmen-Cluster verwirft (Urteil), wenige Aufrufe, Ergebnis ist eine ganze Seite.
- Kurator (1249-1259): Themenfelder bewusst außen vor; Differenzierungs-Bibliothek sammelt Moves, mit denen sich ein Betreiber abhebt, Chip-/Regulierungsmeldung taugt nie als Vorbild. Sweep (1285): rotierend Brave Search, Ergebnis in `data/state/differentiation_db.json`.
- Promo-Zweig (1301): zweiter Anwendungsfall per Snapshot-Diff statt Presse-RSS; per `promo_enabled` abschaltbar; failsafe.
- Geräte-Zweig (1330-1354): siehe „Für docs/betrieb.md“ (Lauf 31422689829).
- Differenzierungsbericht (1374): eigener Editorial-Schritt auf versionierter DB; ohne LLM quellengebundener Regelbericht.
- Differenzierungsbilder (1404): Seite zeigte bis 08.08.2026 77 Karten und null Bilder (Antonio: „Keine Bilder, es ist schwer zu verstehen.“); erst Wochenbericht-Bilder, dann og:image, damit `render_site()` offline bleibt; fehlendes Bild → Schriftkachel.
- Stats (1440-1477): `new` zählt Meldungen, `events` Ereignisse (Differenz = Mehrfachberichterstattung); `ctm_direkt` null ist Befund; `ct_zeitueberschreitung` eigen (certspotter-Nichtantwort ≠ keine neuen Namen); `tarif_kleingedruckt` eigen (Änderung ohne Preisbewegung); Geräteradar in `stats`, weil Promo-Zweig auf der Website unsichtbar ist; `geraete_gealtert` eigen.
- Laufprotokoll (1490-1536): Zwischenstand, Übersetzung trägt nach; Modelle, die der Anbieter mitten im Lauf nicht mehr bediente, sichtbar in `protokoll.html`; Modell-Anker je Primärmodell protokolliert; Stichprobe der Vorsortierung mit Gründen (Messauftrag aus Premortem); Quarantäne-Block, sonst bei 1000 Quellen nicht zu sehen.
- Redaktion ausgefallen (1548, E3B): 0 bewertete Meldungen → letzte gültige Redaktion übernommen, `stats`/`run_log` bleiben ehrlich; Grund unterscheidet ruhige Woche von Ausfall; `stats["bewertete"]` vor der Übernahme festhalten (sonst läse `transparenz.html` übernommene Meldungen als Ausbeute); `report/html.py` fällt für ältere Berichte auf Highlight-Zählung zurück (`n_bewertet`).
- Zeile 1593: P4, Bewegungsblock der Geräteseite im Berichts-JSON, Versand rendert nur daraus (`scripts/newsletter/send_digest.py`), Ausfall als `error`.
- Persistenz (1605-1638): Seen-Store ist Einbahnschild; Lauf #64 (04.08.2026) 223 ungelesene Meldungen verloren (siehe oben); Beleg haengt am Schicksal seines Vertreters; Ereignis-Speicher und Themengedächtnis merken nur Gelesenes.
- Übersetzung (1648-1677): läuft auf den BERICHTETEN Meldungen, nicht `new_items`; am 14.08.2026 944 neue Meldungen durch die Stufe, 58 im Bericht, alle vier Übersetzungen gehörten zu Meldungen ohne Bericht (415 s, null Links). Berichtsreihenfolge = Relevanz; Fremdsprachige vor Unbestimmten (`stufe._kandidaten`); Rückweg über URL aufs Item wegen Feed-Volltext und Original-Teaser (Highlight trägt deutsche Zusammenfassung).
- Zeile 1714/1725/1733: Kosten nach letzter Modellstufe und vor Rendern; erst aufräumen (Bildordner), dann `render_site`; Versand zuletzt und failsafe, Bilanz im Laufprotokoll.
- Zeile 573, 1020, 1123, 1163 u. a.: reine Nacherzählung oder Verweise; `# noqa: BLE001` bleiben.

### `src/telco_radar/promo_bilder.py`
- `BREITE` (76): 1280 = Aufmacher ~620 px bei 1440 px, Retina 1240; keine zweite kleinere Stufe wie bei der Marktrecherche, weil die Seite höchstens ein paar Dutzend Bilder zeigt (nicht 190).
- `MIND_BREITE` (82): 500, strenger als Marktrecherche (400); schmale Bilder sind hier fast immer Geräte-Freisteller oder Zahlungsart-Icons.
- Stoppwörter (90): bewusst kurz, Häufigkeitsgewichtung entwertet häufige ohnehin.
- `_MIND_GEWICHT` (129): 0.9; ein Wort einmal = 1.0, zwei Wörter je viermal = 0.5; Schwelle verlangt ein seltenes Wort oder mehrere halbwegs seltene. `_ZU_HAEUFIG` (134): 0.5 Anteil der Bildkontexte.
- `_MOTIV_MIND_BREITE` (138): 700, Stufe 4 Seitenmotiv; Breite 0 (Seite sagt nichts) fällt NICHT durch, große Bühnenbilder tragen oft keine width-Angabe (otelo.de: vier Kandidaten, alle ohne Angabe, alle 1920 px).
- Siegel-Filter (145): Testsiegel heißen nach Herausgeber („csm_tuev-saarland“, „csm_focus-money“), über alt-Text zu fassen; Müllfilter in `report/bilder.py` greift über URL. Pflichtgrafiken (155): am 16.08.2026 stand das EU-Energielabel eines Galaxy S26 als Motiv einer winSIM-Aktion (1200x2401); steht im Pfad, nicht im alt-Text.
- Zeile 208/290/304/310: Breitenangabe nur Tiebreaker, gemessen wird beim Download; ohne `page` bleibt es bei einem Motiv (Stand vor 08.08.2026); Dokumentreihenfolge statt Größe (Testsiegel unten, 1920 px breit); Vergebenes bleibt vergeben, sonst zwei gleiche Kacheln.
- Zeile 346: Logos/Zählpixel/Platzhalter HIER aussortieren, sonst verbraucht das Markenlogo den Kandidatenplatz (ALDI TALK: `aldilogo.png` stand vor dem Back2School-Motiv und gewann Stufe 4). Zeile 359: bei gleicher Güte gewinnt das höher bewertete Angebot.
- `KANDIDATEN_JE_ANGEBOT` (377, übernommen): erster Kandidat kann beim Abruf durchfallen (zu klein, 403, kaputt), zweiter Versuch billiger als leere Kachel.
- Zeile 418/435: unverändert und schon da → nichts tun (Abruf teuer, Motiv wechselt selten); `# noqa: BLE001` bleibt.

### `src/telco_radar/promo_config.py`
- Etikett Leitseite (35): „Übersicht“ = Seite, die der Anbieter selbst als Einstieg in seine Aktionen führt.
- `reach` (70): Achse C des Wichtigkeits-Scores (`analyze/promo_ranker.py`), Marktreichweite 1-3, eigenes Feld statt Tier-Ableitung (ALDI TALK erreicht mehr Menschen als reine Online-Zweitmarke, beide Tier 2); fehlt es, fällt `promo_ranker.reach_axis()` auf das Tier zurück.
- `rang` (76): Antonio am 08.08.2026: „die groessten Anbieter wie Telekom etc. an erster Stelle, soll also nach Wichtigkeit der Anbieter geordnet werden.“ Vorher Sortierung nach Score der stärksten Aktion (Rangliste der Angebote, nicht des Marktes): Otelo oben, Telekom auf Platz zehn, weil ihre JS-Seiten im Lauf nur zwei Angebote hergaben. Bewusst gepflegtes Feld, Marktgewicht steht in keiner Zahl; fehlt es, Rang aus tier und reach (`report/promo.RANG_UNGESETZT`), Marke fällt hinter jede gepflegte.
- `pages` (89): weitere Seiten einer Marke; Leitseite aus url/kind, vorangestellt; getrennt, damit Bestandseinträge ohne `pages:` unverändert laufen und `url` „die verlinkte Seite“ bleibt.
- Zeile 52/66/67: Seitenart static | js | skip; Mutter-/Markenfamilie. Nur Nacherzählung.

### `src/telco_radar/promo_pipeline.py`
- Zeile 127: Auftrag je SEITE, nicht je Marke; Nebenläufigkeit wirkt innerhalb einer Marke (fünf Seiten halten den Lauf nicht fünfmal so lange auf).
- Zeile 140: Bildkandidaten aus demselben Seitenaufruf wie Text/Links (vorher je Marke zweiter Chromium für Screenshot); auch für unveränderte Marken gesammelt, weil ein früheres Angebot noch ohne Bild stehen kann.
- Zeile 148: je Marke sammeln, was in DIESEM Lauf gelesen wurde; `mark_stale()` erst nach allen Seiten, sonst altert die erste Seite die Angebote der zweiten.
- Zeile 171-185: `og:image` zuletzt (schwächster Kandidat, meist Markenlogo, siehe `collect/promo_snapshot.extract_hero_image`, einziger bei Seite ohne `<img>`); Bildkandidaten aller Seiten in einem Topf (Übersicht zeigt Kachel, Detailseite den Text), `promo_bilder.zuordnen()` entscheidet über Anker und Textnähe; `page` hält Herkunft für Stufe 4.
- Zeile 195-209: reiner Markenschlüssel = Stand VOR 08.08.2026, zählt nur für Leitseite bis der neue Schlüssel einmal geschrieben ist; Stand IMMER unter dem Seitenschlüssel festhalten: bis Lauf #83 stand das hinter dem `continue`, 10 von 15 Leitseiten standen danach ohne Hash da und wären in jedem Lauf erneut durch die LLM-Extraktion gegangen; ein Schreibvorgang mehr ist kostenlos.
- Zeile 217: Extraktion ist Mechanik (Mechanikmodell), Promo-Redaktion (`promo_editor.synthesize`) bleibt auf dem Redaktionsmodell, wie `_mechanik_modell` in der Hauptpipeline.
- Zeile 238: gescheiterter Aufruf ≠ gescheiterte Seite; nicht in `gepruefte_seiten`, damit `mark_stale` Angebote nicht wegen API-Aussetzers Richtung „ausgelaufen“ schiebt. Zeile 262: Alterung nach allen Seiten einer Marke, nur gelesene.
- Zeile 281: Score über ALLE nicht ausgelaufenen Einträge, LLM-Achsen einmal je Angebotstext eingefroren (`promo_ranker.needs_judgement`); Fehler lässt Scores unverändert.
- Zeile 313: Kampagnenbilder nach der Bewertung (höher bewertetes Angebot bekommt doppelt belegtes Bild); Fehler je Marke einzeln gefangen, Karte ohne Bild ist eine Zeile.
- Zeile 382/396/406: gescheiterte Extraktionen einzeln benennen (nach Lauf #83 unklar, ob Telekom nichts lieferte oder die Extraktion scheiterte); Zahl beitragender Seiten (eine Seite mit Wochen 0 Angeboten ist Ballast); drei Zahlen fürs Laufprotokoll (`pipeline.py::stats`), Ausfall seit 14.08.2026 (Strategie 2026-08-27, B6) stand sonst nur im Actions-Log. `# noqa: BLE001` bleiben.

### `src/telco_radar/quellen_register.py`
- `QUARANTAENE_NACH_LAEUFEN` (41): 6 Läufe ohne Meldung = bei zwei Läufen die Woche drei Wochen; lang genug für Relaunch, Sommerpause, zeitweise Sperre, kurz genug gegen tote Quellen über ein halbes Jahr. Bereits benannt.
- Bewährungsabruf (48): 10 Läufe = rund fünf Wochen; bei 1000 Quellen nicht ins Gewicht. Bereits benannt.
- Zeile 61/64/75/169/190/195: Felder aus YAML (redaktionell) vs. gemessen; ein Erfolg genügt; stillgelegte Quellen zählen zur nächsten Probe. Nacherzählung.

### `src/telco_radar/textwerkzeug.py`
- `WORT_RE` (49): vier Zeichen Mindestlänge, kürzer fast nur Füllwörter („der“, „und“, „mit“), Häufigkeitsdeckel trägt sie ohnehin aus.
- Wortgrenzen (82-102): vier Nutzer (CTM-Linse, Frühwarn-Board, Wettbewerbsseite, Newsletter-Filter seit 11.08.2026) brauchen dieselbe Antwort. „Netzausbau“ muss in „Glasfaser-Netzausbau“ treffen (`(?<!\w)`), „Netz“ nicht in „Netzwerkkarte“ (`(?!\w)`), „spark“ nicht in „Sparkasse“, „globe“ nicht in „Globetrotter“, „orange“ nicht in „Orangensaft“. Bewusst keine Beugung: „Netzausbaus“ trifft nicht; optionale Endung `s|es|n|en` fängt Falschtreffer („Orange“+„n“); erst messen, dann verschärfen. `kein_punkt_davor` blendet Domainnamen aus (sonst „o2“ in „example.o2“).
- Beobachtend statt empfehlend (120-198): Abkürzungen mit Punkt (z. B.) schützen den Satztrenner; Klauseltrenner innerhalb eines Satzes; „Vodafone“ als eigenes Wort, Blick nach links hält „MeinVodafone“ heraus; Adressat auch das „Wir“ der Redaktion; nur Grundform der Verben („bündelt“ ist Feststellung, „bündeln“ Rat); „Vorlage für Vodafone: …“ raten ohne Verb (alle vier Fälle im Bestand vom 08.08.2026), bewusst NICHT „für Vodafone“ allein („für Vodafone entsteht Druck“ ist Folge); Telegrammstil endet auf Infinitiv; Trenner der Wettbewerber-Notiz ohne Doppelpunkt, mit freistehendem Bindestrich („Wi-Fi-7-Router“ bleibt).
- Ordinaldatum (187-198): „Gültig bis 12. September 2026“ wurde zu „Gültig bis 12.“ + „September 2026“; gemessen am 11.08.2026 in der Ausgabe vom 8. (Mail zeigte „Aktion gültig bis 12.“ als Satz), derselbe Schnitt trifft `_strip_vodafone_advice` im Wochenbericht. Geschützt nur vor Monatsnamen, nicht vor jedem Großbuchstaben („Die Zahl stieg auf 12. Vodafone reagierte.“ ist echtes Satzende).
- Zeile 261/307: Teilsatz ohne Anfang ergibt keinen Satz; nur der erste darf immer stehen, spätere müssen groß beginnen oder hinter Doppelpunkt stehen (Beispiel: „…ob ein Produkt – etwa über die Vodacom-Gruppe – schnell umsetzbar ist“ ließ die Mitte übrig); Telegrammstil-Rat verteilt Adressat und Verb auf zwei Teilsätze.
- `MIND_ZIFFERN_BELEGPFLICHT` (342, übernommen): Zahlen im Satz müssen belegt sein (Prozent, Preise, Volumen); einstellige bleiben außen vor („5G“, „die ersten drei“, Aufzählungen).
- Zeile 358: verglichen wird der reine Zahlenwert; „35 Euro“ deckt „34,95 Euro“ nicht ab, Abstand unter 1.0 zählt als gedeckt.

### `src/telco_radar/versand.py`
- `STANDARD_WOCHENTAG` (52): 0 = Montag; Montagfrüh plant jemand die Woche, eine Freitagsmail liest niemand mehr. Bereits benannt.
- `TEAMS_CTM`/`TEAMS_PRIORITAET` (56): Ausnahme-Schwelle für Teams, beide Bedingungen, nicht eine. Bereits benannt.
- Zeile 199: Befund, keine Lücke, wird als Befund geschrieben. Zeile 375/396: Mail feste Kadenz; Teams nur Ausnahme, jede Meldung genau einmal. Abschnittsüberschriften sonst ohne Inhalt.
