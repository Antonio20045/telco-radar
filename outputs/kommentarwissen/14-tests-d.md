# Kommentarwissen 14-tests-d

Stand: Commit aaa8b0d, 52 Dateien, 1542 Kommentarzeilen.

## Übernahmen in Code
- keine. Testdateien: Wissen steht als Begründung/Messwert im Protokoll; Umbenennungen und neue Tests nur bei Bedarf, hier im Zweifel weggelassen. `tests/conftest.py` und Hilfsmodule ohne test_-Präfix (`tests/browser_konsole.py`) nicht geändert, nur protokolliert.

## Für docs/betrieb.md
- Telekom-Erhebung: der T2-Laufzeitbeleg (`outputs/beleg-telekom-geraete-2026-09-08.json`) fand 1 von 7 Requests mit globaler Chrome-Kennung (robots.txt); seit B2 (08.09.2026) gehen robots.txt und Markenseiten-Abruf mit der ehrlichen Anbieter-Kennung; Anbieter ohne Override bleiben bei der globalen Kennung, PM-Entscheidung zu settings.yaml steht aus (Quelle `tests/test_geraete_adapter_saturn.py:463`).
- Saturn: R1 behauptete ehrliche Kennung `TelcoRadar/1.0`, tatsächlich ging die Chrome-Vortäuschung aus config/settings.yaml hinaus; Test misst die gesendete Kopfzeile auf httpx-Ebene (Quelle `tests/test_geraete_adapter_saturn.py:337`).
- Ein Lauf kostete am 27.08.2026 1,95 $; Antonio zahlt die API privat, deshalb gibt es die Kosten-Statistik je Stufe (Quelle `tests/orakel/test_seiten_inhalt.py:239`).
- Promo-Ausfall seit 14.08.2026 (LLM-Extraktion scheiterte an leerem API-Guthaben) stand bis 27.08.2026 in keiner Statistik, nur im Actions-Log; seitdem `promo_*`-Felder in `stats` (Quelle `tests/orakel/test_seiten_inhalt.py:304`).
- Live-Beobachtung 31.08.2026: 3 Messtage, längste Spanne 20 Tage, keine Lifecycle-Zeile; Handover §8a: nach etwa zwei weiteren Wochen Nachtläufen kippt es von selbst, dann Seite ansehen (Quelle `tests/test_geraete_lifecycle.py:1119`).
- Stapelgröße `BATCH_SIZE` wurde am 27.08.2026 von 15 auf 24 erhöht (Quelle `tests/test_pipeline.py:196`).
- Produktions-Konfiguration hat `crawl_newsrooms: false`; Promo-Stufe mit Playwright-Marken muss in Offline-Tests aus (Quelle `tests/test_pipeline.py:26-35`).

## Widersprüche
- keine

## Wissen je Datei

### `tests/browser_konsole.py`
- nichts übernommen: Hilfsmodul ohne test_-Präfix, nur protokolliert. Wissen: Konsolentypen `error` und `assert` zählen (Chromium meldet `console.assert(false,"x")` als type `assert`, bis 21.09.2026 stillschweigend verworfen); `warning`/`log` zählen nicht. Nur Netzfehler (`net::ERR_...` im Text) werden befreit, HTTP-Status im Klartext ("responded with a status of 400") ist ein Fehler der eigenen Seite. Erlaubte Fremdadressen = die, die `base.html.j2` bewusst von außen holt, bewusst kein Muster "alles mit https". Keine Herkunft heißt nicht "von außen". Kanalmarke an der Meldung, damit bei rotem Test sichtbar ist, ob die Konsole meckerte oder etwas warf.

### `tests/orakel/test_seiten_inhalt.py`
- Fixture (Zeile 55): 12 relevante Meldungen, 8 mit relevance >= 4, mehr als der Deckel von sechs auf der Signalliste in html.py; sonst sähe der Test die Kappung nicht.
- Große Fixture (65): Größenordnung einer echten Ausgabe (193 Meldungen am 06.08.2026), damit alle vier Gewichtsstufen der Titelseite und Ressortblöcke gefüllt sind.
- Bilder (84, 108, 127): jede zweite Meldung mit Bild, davon jede vierte zu klein für große Position. Bericht muss unter `data/reports/` liegen, weil render_site() den Bildordner über `reports_dir.parent.parent` herleitet; flach unter tmp_path zeigte es aufs gemeinsame pytest-Wurzelverzeichnis. Bilddateien müssen existieren, render_site() streicht `image`-Verweise ohne Datei (Archivwochen sonst leere Kästen, nachdem raeume_auf() Bilder löscht).
- Kosten (238): Antonio zahlt API privat; bis 27.08.2026 stand nirgends, was ein Lauf verbraucht, Lauf vom 27.08. 1,95 $, Stufe nicht erkennbar.
- Promo (303): E10b, 27.08.2026, Strategie 2026-08-27 B6: Promo-Ausfall seit 14.08.2026 stand in keiner Statistik.
- Gesamtzahl (464): seit 08.08.2026 kein Satz "138 Meldungen in 7 Ressorts" im Kopf mehr, nur verteilt an den Ressorts; muss aufgehen. Bis 07.08.2026 stand sie in einer Sprungleiste (Krücke einer zu langen Seite), davor doppelt (Chip und Link).
- Suche (489): wochenübergreifende Suche stand bis 08.08.2026 unten auf der Seite, ist jetzt eigene Seite `suche.html` (Dossier); Topbar-Formular führte auf die Seite, Treffer nach rund 2400 px. Antonio: "Ich verstehe nicht, warum ich da weitergeleitet werde."
- Quellenbilanz (722): Quarantäne zählt nicht als abgefragt (1 ok / 1 leer / 2 gescheitert), sonst sähe die Bilanz besser aus, je mehr Quellen aufgegeben wurden.
- Roter Faden (841): Antonio am 07.08.2026 "der rote Faden fehlt mir noch überall"; Titelseite sortierte nach Dringlichkeit, Bericht nach Urteil der Chefredaktion, beide führten mit anderer Geschichte; Kopplung jetzt gebaut. Test (870): Meldung, die ohne Faden Aufmacher würde, steht vorn in der Liste (`nimm` geht der Reihe nach).
- Nicht mehr getragen (926-968): Zahl "davon N zum sofortigen Ansehen" fiel am 08.08.2026 (steht an jeder Meldung als Priorität 5/5); Werte werden nicht mehr berechnet, Vorlagenzugriff wäre still leer statt laut falsch.
- Wettbewerbsseite (972): Zahlen "56 Meldungen seit 16. Juli 2026" und je Monatsgruppe sind Aggregate über alle Archivwochen; Chronik datiert auf Tag des einzigen Berichts, nicht heute.
- Themenseiten (1023): drei Zahlen (Meldungen zweimal, Quellen, Laufzeitbeginn) aus dem Themenspeicher, nicht der Wochenausgabe.
- Differenzierung (1119): seit 08.08.2026 nur noch eine Zahl, Beispiele je Hebel; alte Statuszeile "51 Beispiele in der Bibliothek · 12 von 12 Hebeln aktiv · 5 neu" ersatzlos weg (Antonio: Zahlenrauschen). Inhaltsfehler: Seite las nur `differentiation_db.json` (Web-Sweep), `differentiation.jsonl` (Kurator über Presse-Crawl) wurde wöchentlich gefüllt und nie angezeigt. Fixture (1272): zwei Presse-Einträge jünger als zehn Tage (Ausgabe 5.8., first_seen 4.8.), Sweep-Einträge vom 15.6.
- Umbau 08.08.2026 (1327): Antonio "total unübersichtlich, keine Bilder, es ist schwer zu verstehen ... viel besser sein analytisch".
- Beruhigungs-Durchgang A (1507): Antonio 08.08.2026 "Die Seite wirkt unruhig, weil überall so viele Kommentare sind"; jede gestrichene Floskel hat einen Test. "beim Anklicken" kam am 11.08.2026 auf der Geräteseite dazu (beschreibt Handlung statt Aussage); Seite fehlte vorher in der Liste. Stylesheet bewusst ohne Kommentare.
- CTM-Linse (1590): zweite Bewertungsachse (analyze/ctm.py) und Zwei-Minuten-Pfad sind Zahlen und Reihenfolgen auf der Seite, gehören in Seitentest, nicht Modultest. HIGHLIGHTS: 0-3 tragen Priorität 5, 4-7 die 4, 8-11 die 3. Ein Link im Link wäre ungültiges HTML, Belege außerhalb des Meldungslinks.

### `tests/test_anbieter_farben.py`
- nichts übernommen: nur Abschnittsüberschriften (bekannte Anbieter stabil; unbekannte als benannte Lücke, nie geraten; Stylesheet ein Platzhalter, ein erzeugter Block).

### `tests/test_archiv_dossier.py`
- Zeile 170: die vier Rangfolge-Tests nutzen winzige Korpora, dort steht der Suchbegriff in jedem Eintrag, IDF nahe null, Score unter `MIND_SCORE`. Am echten Bestand (737 Einträge) erreichen echte Fragen 6 bis 9 Punkte, Unsinnsfrage exakt 0. Schwelle wird deshalb ausgeschaltet und in `test_mind_score_ist_wirksam` und `test_frage_ohne_treffer_erfindet_nichts` geprüft.
- Rest: Abschnittsüberschriften (Python und Browser müssen dasselbe antworten).

### `tests/test_bilder.py`
- Zeile 105: Artikelseite absichtlich nicht hinterlegt, Abruf liefert 404, `kein_og` steht in der Bilanz.

### `tests/test_buendel_herleitung.py`
- Zeile 68: Gegenprobe, gemessen bleibt leer, nicht None und nicht geraten.

### `tests/test_dedupe.py`
- nichts übernommen: Kommentare erzählen den Code nach.

### `tests/test_effektivpreis.py`
- Zeile 76: Beispielrechnung 3x0 + 9x19,99 + 12x39,99 = 659,79 -> 27,49.
- Zeile 312: Unendlich kommt aus JSON nicht heil zurück (Extraktor setzt inf, json macht Infinity), deshalb direkt gesetzt.
- Zeile 403-427: Karte zählt anders als Tabelle: ohne Grundpreis kein Punkt (nicht belastbar) obwohl Volumen bekannt; ohne Volumen Zeile in Tabelle, kein Ort auf der Achse; ohne Anschlusspreis Punkt, aber Lücke gezählt. Cashback-Lücke tragen alle fünf, keine der vier Zahlen zählt sie, deshalb Satz im Hinweis.

### `tests/test_folien.py`
- Zeile 251: nicht auf Klartext der Headline prüfen, `_akzent()` setzt ein Wort in ein `<span>`.
- Zeile 279: Inter per Google Fonts ist in der Design-Spezifikation ausdrücklich vorgesehen, sonst nichts Fremdes im Deck.

### `tests/test_geraete_adapter_congstar.py`
- Zeile 43: vier Produktseiten mit vier Preisbeispielen aus dem Auftrag; `listed` ist richtig, `discounted` die Falle (siehe Modulkopf congstar.py). Fixture muss den `discounted`-Wert wirklich enthalten, sonst prüft der Test nichts; im Roh-HTML steht die JSON-Nutzlast escapt (`\"discounted\":757`).
- Zeile 89: Sitemap nur echte, verlinkte Adressen (§ 87b UrhG).
- Zeile 272: Geräte-ID kommt aus dem Katalog, nie aus dem Titel (Teil E).
- Zeile 336: Fixture-JSON innen compact, `_VARIANTE_START_RE` sucht `{"id":1,"gtin":"` wortwörtlich; außen ebenso (`_PUSH_RE`, Komma).
- Zeile 408: gescheiterter Abruf ist nicht "nichts gefunden". Zeile 547: kein einziger `discounted`-Wert unter den Bilanzpreisen.

### `tests/test_geraete_adapter_saturn.py`
- Zeile 69-130: Markenseite ohne Marktplatz-Mix, vier Saturn-eigene Preise; Marktplatz-Filter: teuerster Fremdanbieter Media-Reich GmbH (Spike-Tabelle), keiner der sieben bekannten Fremdanbieter-Preise darf durchrutschen, Reihenfolge darf Ergebnis nicht ändern.
- Zeile 177-193: Farbe strukturiert aus dem Titel gelesen, der generische Rückfall wäre hier leer ausgegangen (rechtfertigt die Sonderbehandlung).
- Zeile 294-343 (R2, EVAL_saturn-adapter-r1.md Befund 1, Schwere 1): R1 behauptete `TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)` in `collect.http.fetch`, tatsächlich ging als PRIMARY die volle Chrome-Vortäuschung aus config/settings.yaml:549 hinaus, weil der Adapter das globale `http_cfg` unverändert nutzte. Tests messen die wirklich gesendete Kopfzeile auf httpx-Ebene.
- Zeile 329: Start-Scope laut Auftrag alle Apple-iPhone-Serien des Katalogs.
- Zeile 463: robots.txt ging bis B2 (08.09.2026) mit globaler Chrome-Konfiguration hinaus (T2-Laufzeitbeleg Telekom, 1 von 7 Requests, `outputs/beleg-telekom-geraete-2026-09-08.json`; Beleg verlangt 100 %); Anbieter ohne Override bleiben global (PM-Entscheidung zu settings.yaml steht aus).

### `tests/test_geraete_adapter_telekom_1und1.py`
- Zeile 230: der eine Fall, der alte von neuer Auswahlregel trennt: 24-Monats-Plan teurer als echter 36er (99 + 24 × 46,00 = 1203,00 gegen 99 + 36 × 30,50 = 1197,00); "längste Laufzeit zuerst" wählte 1197,00, den niedrigeren Betrag. Synthetisch, kein echter Abruf trägt zwei Pläne.
- Zeile 268-394: übergangener Plan steht samt Regel im Protokoll, das nicht behauptet, er sei woanders erfasst (`lies_buendel` sieht die "ohne Vertrag"-Nutzlast nie, kein `selectedPlan`); beide Pläne rechnen auf, sonst wäre einer verworfen (anderer Zweig); Regel steht einmal in Rechenreihenfolge.
- Zeile 598: Telekom trägt seit B2 `user_agent`-Override, `hole()` bekommt ihn als drittes Argument (wie Saturn). 616: `direkt=True`, Kategorieseite ist Nutzlast, keine Produktseite nachgeladen.
- Zeile 766: 42 Kacheln, alle abgerufen, Deckel 45 greift nicht; einzige Lücke die 41 Stub-Seiten ohne Bündelkatalog (seit 29.09.2026 gezählt statt nur protokolliert). 790: `grund` ("warum nicht aktiv") entfällt, Messstand steht in `hinweis` auf der Quellenseite.

### `tests/test_geraete_buendel_kopf_zeitraum.py`
- Zeile 53: Fixture mit vier Anbietern in einem Band (Klein, Tarife unter 20 GB): congstar 1 + 24 x 10,00 + 24 x 24,99 = 840,76 EUR (24 Mon.); o2 1 + 24 x 18,00 + 24 x 24,99 = 1.032,76 EUR; 1&1 100 + 36 x 30,00 = 1.180,00 EUR (36 Mon.); Vodafone 1 + 24 x 26,00 + 24 x 24,99 = 1.224,76 EUR. Sortierung nach Betrag allein schöbe 1&1 zwischen o2 und Vodafone (Platz 3 von 4); 1&1 hat EINEN Monatsbetrag für Tarif und Gerät (§ 13.2).
- Zeile 291-309: Zeitraum als Attribut an der Zeile, gelesen statt gebaut; `data-laufzeit` taugt nicht als Gruppe, es ist die Tariflaufzeit der Rechnung und überall 24. Sortierung im Chromium: erst Zeitraum, dann Betrag darin; nichts wird gekappt. Zeile 480: kein Rückfall auf Konstante 24 im Markup, gemessene Ratenzahl (36 bleibt 36).

### `tests/test_geraete_buendel_telekom.py`
- Zeile 58: echte Werte der Fixture (MagentaMobil S, MF_17785, 08.09.2026). 148: 9 Einträge mit id, die Werbekachel trägt keine. 160: je-Gerät-Tarifpreis gehört zum `selectedPlan`. 233: Tarifname und -preis gleich für beide Pläne, nur Geräteseite unterscheidet sich. 277: kaputter Plan nicht still verschwunden.
- Zeile 427: Tarifname steht in derselben Antwort, Telekom braucht anders als Vodafone keinen Haken für Namensauflösung nach dem Sammeln. 470: jeder Abruf des Anbieters (robots.txt wie Bündelseite) mit demselben ehrlichen Absender.

### `tests/test_geraete_haendler_ohne_buendel.py`
- nichts übernommen: nur Abschnittsüberschriften (reine Funktion; ganzer Weg über `geraete_tco_view.aufbereiten()`).

### `tests/test_geraete_laufzeit_auf_der_seite.py`
- Zeile 251: dieselbe Zahl, die den Kartenschlüssel trägt, steht am Modell; eine zweite Definition wäre zweite Wahrheit. 259: Gegenprobe, ein congstar-Bündel gibt eine Zeile.
- Zeile 311-358: aufgeteilte Form (Tarif und Rate getrennt) trägt weiter 24 (Raten jenseits als Restschuld). Zeile ohne Zahlenwert: kein Δ-Präfix, kein Sortierschlüssel, fällt aus Rangfolge nach Δ; Satz steht als benannte Lücke im Rechenweg, nicht als lauter Delta-Satz in Alarmfarbe (`gr-kk-delta`).
- Zeile 404: Regel 9, Zeile zeigt den Ausfall statt "nichts gefunden" vorzutäuschen. Zeitreihe (485-717): unbekannte ID-Form und ungeratene Laufzeit; Gegenproben mit ID der heutigen Form und mit gemessener Laufzeit.

### `tests/test_geraete_leer_zustaende.py`
- Zeile 302: Satz nennt die Vergleichsmenge, die Tafel ist nicht leer, weil nichts gemessen wurde. 346: Gegenprobe am Bestand mit Zeilen, Leer-Satz versteckt (Filter-Satz). 380: sechs Export-Links, sechs verschiedene Dateien. 111: P3, zwei Modell-Exporte (je Ansicht eine Datei, eine Zeile je Modell).

### `tests/test_geraete_lifecycle.py`
- Zeile 16: Zuordnung einer Zeile zum Regalplatz hängt an der privaten Ableitung; wer sie im Test nachbaut, prüft seinen Nachbau.
- Zeile 128: Listungsdauer zählt bis zur letzten BESTÄTIGUNG, nicht bis zum Tag der Aufgabe im Store (sonst zählten die zwei Fehltreffer der Auslistungslogik mit).
- Zeile 230: Messbeginn nach dem Nachfolger gibt keine Basis. 238: 30 Tage nach 19.09. ist 19.10. erreicht, 60 und 90 nicht.
- Zeile 359: Schwelle der Lifecycle-Sektion, Evaluation 11.08.2026. Zeile 510: Messtermine kommen aus den Prüfterminen, nicht aus der Preishistorie (Diagnose G0, 28.08.2026).
- Zeile 620 (31.08.2026): Schwelle zählt je LISTUNG, nicht je Anbieter. Kommentar über `MIND_TERMINE_JE_GERAET` versprach seit 28.08.2026 "JE GERAET", `_oft_genug` las `termine_je_anbieter[eintrag["anbieter"]]`; ein lange beobachtetes Gerät schaltete den ganzen Anbieter frei (auch die elf seit gestern). Reproduktion: `test_die_termin_schwelle_zaehlt_je_listung_nicht_je_anbieter`, `test_ein_prueftermin_vor_der_ersten_sichtung_zaehlt_nicht_mit`.
- Zeile 866: Nachfolger-Effekt vollständig "Preis des Vorgängers 30/60/90 Tage nach Marktstart des Nachfolgers UND wie lange er danach im Regal bleibt"; zweiter Halbsatz ist die These der Fachabteilung und hängt am Preis nicht (Verweildauer).
- Zeile 1116: Wächter gegen den ECHTEN Bestand nagelt Lage vom 31.08.2026 fest: drei Messtage, längste Spanne 20 Tage, keine Lifecycle-Zeile. Fällt er durch, hat sich die Datenlage geändert, nicht der Code (Handover §8a: "nach etwa zwei weiteren Wochen Nachtläufen kippt es von selbst, dann ansehen").
- Zeile 1296-1331: Floors liegen unter BEIDEN gemessenen Lagen (18.09.: 85/52 am Rand 2026-09-18, 325/216 einen Tag später, wenn die Kohorte vom 29.08. die Schwelle kreuzt). Bis P5 verlangte der zweite Assert `ohne_bewegung == 0 or verfaelle == []`, das war die Lage vom 02.09. ("nichts bewegt seit 31.08."), keine Regel; am 18.09. 93 Gezählte neben 14 Zeilen ist Normalfall.
- Zeile 1489 (Nachbesserung 31.08.2026): drei Befunde eines simulierten Nachtlaufs an echten Daten: 85 Verweildauer-Zeilen mit 11 unterscheidbaren Texten, 85 Preisfälle mit "+0,0 %", einzige Nachfolger-Zeile ein Gebrauchtgerät. Regalplatz = Speicher; längste Variante steht absichtlich in der Mitte (sonst gewänne auch "erster/letzter"); Marktstart Nachfolger 2025-09-19; gemeinsam gerechnet läge Beginn 2024-08-01 vor Marktstart.
- Zeile 1769-1964: vier Regeln, die bis 31.08.2026 kein Test hielt: Preisbasis über (Gerät, Anbieter) gefiltert ließe Gebrauchtpreis gewinnen; Basis je Anbieter ("expert") und über Listungs-IDs; Fenster-Rand: Beleg 15.02. und 01.04. plus Prüftermine, einer exakt auf `first_seen`; einen Tag früher fällt die Zeile.

### `tests/test_geraete_o1_hauptgraph.py`
- Zeile 142: Proportionalität breite/gesamt weicht um weniger als einen Prozentpunkt ab (Rundung auf eine Dezimalstelle). 197: Format zwei Nachkommastellen, Tausenderpunkt = `euro`-Format des Portals, keine zweite Beschriftung. 231: o2-Bündel im Band XS plus erneuertes Telekom-Bündel: o2 trägt die Zeile, Telekom "nur erneuert" in der Lücke, 1&1 und Vodafone "kein Bündel". 280: P3-E1, Stufe Vodafone XS.

### `tests/test_geraete_o2_zeilen_browser.py`
- Zeile 45: O1-Lage plus unbegrenzte Zeile am Vorgabemodell (o2) und zweite Zeile Band XS (Telekom). 258: Zuwachs gegen O1 (27 Aufklapper) sind die Zeilen-Aufklapper; keine Karte trägt noch eigenen Rechenweg-Aufklapper. 323: E2, wählbare Modelle im Zeitreihen-Knoten. 469: Mobil 390, Tarif-Zelle liegt UNTER der Anbieter-Zelle (grid-areas), gemessen im Layout, nicht im DOM.

### `tests/test_geraete_o3_rollen_browser.py`
- Zeile 40: drei Modelle mit eigenen Bündeln (iPhone 17 Pro 256 Vorgabe: o2 klein, Vodafone klein Referenz, congstar mittel, o2 unbegrenzt; Galaxy S26 256: 1&1 klein; Pixel 11 256: congstar klein, o2 mittel), damit Zeilen mitwechseln.
- Zeile 221: Deep-Link-URL neu gebaut; seit E2 schreibt die Seite `?modell=&band=` zurück, Anhängen ließe den ERSTEN modell-Parameter gewinnen. 352: `localeCompare('de')` im Browser, alphabetisch (sonst Vodafone vor congstar; Python sorted misst anders). 383: Zeilen ohne Δ am Ende.
- Zeile 766-781: Luft über dem Modellnamen (spezifischere padding-Regel schluckte sie); 3-px-Balken darf Text nicht überdecken. 818: Bündelzeilen (`details.gr-bnd`) sind Tabellenzeilen; seit kürzeren Kopfzeilen (28.09.2026) rückt die erste Zeile an 1440 px in die Falz; gezählt werden Aufklapper für Erklärung/Datenlage. 682: Leitzahl der Kostenansicht trägt Spaltennamen, sonst läse sich "ab 1.459 €" wie Einzelgerätpreis.

### `tests/test_geraete_o4_export.py`
- Zeile 38-67: Spalten der Bündel-Zeilen, Auftrag O4 wortgleich; "Art" davor (Bündel und SIM-only), "Zustand" und "Bündel/Monat" dazu (erneuertes Gerät anderer Preis B1; 1&1 EIN Monatsbetrag, § 13.2). Leitzahl-Spalte heißt seit A1 "Kosten über 24 Monate". "SKU-ID" letzte Spalte wie in geraete-aktuell.csv; ohne sie kollabierten Vodafones Farbvarianten zu byte-identischen Zeilen (A4, 20.09.2026: 156 in der Live-Datei). P0-B-h4 (21.09.2026): "Leitzahl-Zeitraum Monate" aus `tco_model.Tco.leitzahl_monate`, für 74 Bündel (1&1, `buendel_monatlich`) 36 Monate; Spaltenkopf bleibt (Fremdschlüssel `tests/test_seiten_zahlen.py`). P0-B-z3 (22.09.2026): Zahl steht in EINER von ZWEI Spalten, "Kosten über 24 Monate EUR" wenn Zeitraum `TCO_HORIZONT` (24), sonst "Kosten über die Bündellaufzeit EUR"; kein Test schreibt Namen ab (Clean Code 7).
- Zeile 317-332: 1&1 führt denselben Tarif mit denselben Beträgen zu mehreren Geräten, alle Kandidaten rechnen dieselbe TCO. 462: Katalog bildet beide SKUs auf dasselbe Modell ab (live bei jeder Farbvariante). 486: SIM-only 39,99 EUR/Monat * 24 + 29,99 EUR Anschlusspreis = 989,75 EUR (alte Exportzahl ohne Anschlusspreis 959,76 EUR).
- Zeile 655: Alarmzeile eindeutig über (modell, speicher, prozent, wettbewerbspreis, unser preis); am echten Bestand teilen zwei Zeilen dieselbe Kombination, nur Gerät unterscheidet; Laden wird mitgeprüft. 690: Laden und Stufe namentlich wie Zelle der Seite (S3). 786: Export darf keine eigene Tabelle auf der Seite bauen. 793: P0-B-z3 vier Befunde des Prüfers, je ein Test gegen alten Stand; genau EINER der zwei Köpfe gefüllt.

### `tests/test_geraete_o4_verlauf.py`
- Zeile 55: E3-Fix, Reiter trägt genau EIN Barpreis-Bild-System (eigene Auswahl), kein G0-Block. 127: seit 28.09.2026 benennt der Reiter die Frage ("Ohne Vertrag"), zweite Überschrift "Barpreis-Verlauf" gefallen. 140: KURZ-Format der Datumsachse ("12.9."); Messtag-Zeile fiel 28.09.2026, erste Achsenbeschriftung nennt den Beginn.

### `tests/test_geraete_o4_verlauf_browser.py`
- Zeile 83: Barpreis ohne Bündel in einem Tarifband (Pixel 11 nur o2-Tarif ohne erhobenes Volumen), Fall des Deep-Link-Tests. 248: EIN Gerät für beide Reiter (28.09.2026, Antonio: "ich verstehe den Unterschied zwischen Vergleich und Preisverlauf nicht"); QA-Fall E3 bleibt ausgeschlossen, nur EIN Barpreis-Bild; Wahl im Reiter "Mit Tarif" gilt auch hier. 269: genau ein Bild oder benannter Satz bei zu wenigen Messterminen.

### `tests/test_geraete_preisform_raten.py`
- Zeile 47: gemessener Satz vom 03.09.2026, auf gelesene Felder gekürzt; `description` und `offerName` wörtlich, Angebotsname trägt Ratenzahl als Suffix `-24xhigh`. 432: seit P3/C3 heißt die Bauform `_katalog_zeile` (Aufklapper der Modellzeile), `katalogzeilen()` entfallen.

### `tests/test_geraete_tco_band_browser.py`
- Zeile 250: Band "L" ohne Bündel für das Modell ist DEAKTIVIERT (Angebot, nicht Existenz der Option), wie am alten select jetzt an Knöpfen. 282: Panels des alten Bands existieren nicht mehr, Graph ist EIN Zustand (A2).

### `tests/test_geraete_vergleich.py`
- Zeile 153: Meldung wird nicht zu "bei Vodafone nicht gelistet" umgedeutet: Vodafone führt das Gerät, nur ohne Beleg; falscher Satz über das eigene Regal ist teurer als fehlende Zeile (Selbstreview 29.08.2026). 298: Gegenprobe, derselbe o2-Preis als Neu wird gezählt. 380: W1.1 Gebrauchtware gehört nicht in Neupreis-Vergleich. 419: W2 Tabelle zeigt Befunde, kein Rundungsrauschen (0,90 EUR/0,1 % Rauschen; 15,90 EUR über absoluter Grenze; 39,90 EUR/3,3 % beides); `zeilen` bleibt Vollansicht, gekappt wird unten.

### `tests/test_geraete_verlauf_chart_mobil_browser.py`
- Zeile 73: Fixture identisch zu den 16 Messterminen des realen iPhone 17 256 GB (sechs Anbieter, zehn Termine je Reihe gemischt, 16 eindeutige Tage). 185: kein Bündel nötig, leeres TCO-Bündel hält das Gatter der Tafel 1 (Vergleich) aus dem Weg.

### `tests/test_geraete_wahrheit.py`
- Zeile 156: Farbe als Vergleichsschlüssel; ohne Rohschreibweise trägt kanonische Farbe weiter. 313: Gegenprobe zuerst, als Neugerät würde o2 gewinnen; erste Fassung des Tests lief in die CLAUDE.md-Falle (fragte nach "alle", Schlüssel existiert nicht). 435: Lockpreis in anderer Farbe fliegt an der Unmöglichkeitsgrenze.

### `tests/test_geraete_zeitreihe.py`
- Zeile 165: neu kalibriert 09.09.2026 (Optik-Schritt 5, F-4b): Datenpunkte sind Marken-Symbole, gezählt wird Klassenpräfix `gr-g0-punkt` (Legendensymbole `<use class="gr-g0-legendesymbol…">`, defs-Formen ohne Klasse); vorher `svg.count("<circle")`. 232: Spanne 1000-1300 mit 12 % Polster ergibt tief=964, hoch=1336, keine der fünf Marken auf glattem Hunderterwert. 284: BRIEF_FADEN 05.09.2026 Kriterium 5, Antonios QA-Befund 3: "Telekoms Einzel-Punkt im Zeitreihen-Graph liest sich als 'keine Werte' - die ehrliche Lücke sieht aus wie ein Defekt"; Einzelpunkt bekommt sichtbare Beschriftung. 350: vier Tage 10.08., 29.08., 03.09., 05.09. 399: Linienpfad per Regex am `gr-g0-linie`-Element, naives `split('d="')` traf seit Symbol-defs (`id="gr-sym-kreis"`) die id.

### `tests/test_geraete_zeitreihe_ansicht.py`
- Zeile 109: seit A1 rechnet die Zeitreihe jeden Punkt mit HEUTIGER Formel aus Rohfeldern neu (1 EUR Zuzahlung + 24x20 EUR Tarif + 24x Rate); Fixture schreibt jede Zeile mit eigener Rate, sonst kollabierte jede Serie auf einen Betrag. 317: Startzustand iPhone 17 Pro x klein (4 Anbieter, 9 Punkte); alte Vorgabe aus `geraete_tco_karten` zählt andere Rechnung; Gleichstand bricht aufsteigender Schlüssel. 351: o2 am 13.9. zwei Farbsätze 17 EUR (889,00) und 19 EUR (937,00), günstigstes gewinnt, verworfener Betrag nie als Label. 438: Name der Leitzahl "Kosten über 24 Monate" im Satz, Kürzel TCO-24 nirgends mehr. 478: Zahl und Richtung getrennt prüfen, Tag-Strip klebt `<b>`-Zahlende an Label ("€unter"), Lehre B6 30.08.2026. 490: Referenz-Zweig endete live auf ").."; Satzschlusspunkt genau EINMAL.
- Zeile 514 (E5): Satz nennt Hersteller aus Katalog (`_kurz_name` schnitt bei Xiaomi 17 den Hersteller ab, "Beim 17 im Band M"); Satz "Apple iPhone 17 Pro", Kachel kurz "iPhone 17 Pro". 565: Antonio 9b.7 "nichts heißt nicht einzeln": Telekom hat für iPhone gar kein Bündel. 595: B-Fix (Review 24.09.2026, S1) jeder Anbieter bekommt Endlabel, auch 1&1 mit einem Messtag.
- Zeile 954 (A2): führt am letzten Tag ein Anbieter, der am ersten fehlt, gibt es KEINE Bewegung (Produktionsfall congstar 1.009 EUR 12.9., 1&1 1.396 EUR 18.9. = 387 EUR Front-Differenz, null Preisänderung); Gleichstand bricht `ANBIETER_FOLGE` (o2 Position 3 vor 1&1 Position 4).
- Zeile 1060 (E4, Bau 2, PM-Vorgabe): Auto-Einträge in der WAHL erst ab 2 Messtagen (Bestätigung über zwei Nächte), Katalog-Reiter zeigt ab Tag 1; Hand-Eintrag mit einem Messtag bleibt wählbar (Galaxy S26, 2026-09-12).
- Zeile 1211 (P0-B-h3, 21.09.2026, Befund 3): EIN Graph, EIN Zeitraum. Beschriftung "Kosten über 24 Monate je Messtag und Anbieter" führte 1&1 mit rund 2.020 EUR als 36-Monats-Summe; auf einer Achse ist das eine längere Laufzeit. Zahl steht benannt im eigenen Eimer MIT Zeitraum (harte Regel 9, A2); zweiter Graph keine Lösung (Startansicht genau ein `svg.gr-zr`, `test_geraete_reiter_browser`). Kein Delta über zwei Zeiträume (vorher 1.433,80 - 1.299,54 = 134,26 EUR).
- Zeile 1472 (P1-Fix, Review 24.09.2026 Punkt D): Gleichstand zweier Ratenlaufzeiten (24 x 30 == 36 x 20 == 720 EUR, TCO-24 1.200,00 EUR) verliert zweite Zahlweise nicht still; kürzere Laufzeit gewinnt den Punkt (keine Restschuld nach `TCO_HORIZONT`).

### `tests/test_geraete_zeitreihe_browser.py`
- Zeile 83: `touch=True` (E2-F3), erst Kontext mit `has_touch` kann `tap()` senden. 453: Wahrheitstest zur QA-Zurückweisung E2-F1, 17.09.2026: Titel "Alle Bündel im Band M" und Zeilen meinen dasselbe Band; Zeilen ohne `data-band` sind §7-Gruppe "Ohne Tarifband". 533: E2, alter Modell-select ist weg, Modellwahl über Suchfeld (Enter wählt ersten Treffer). 558: P2/D2 Endlabels ersetzen auf breit die HTML-Legende, auf schmal bleibt sie wegen "ab/zuletzt"-Werten. 588: P2/D4b aktiver Navigationseintrag "Geräte" stand auf Telefon bei x=536-620 außerhalb 390 px, "Differenzierung" 20 px abgeschnitten; Messung in `test_navigation_aktiver_eintrag_browser.py`.
- Zeile 617 (C4, QA-Fix 24.09.2026): Endlabel ragt mobil (390 px) nicht aus dem SVG; Fix `geraete_zeitreihe._svg` hängt jedes Endlabel rechtsbündig an festes X (`ENDLABEL_RAND`) statt am Linienende. 693 (C5): "GERÄTEKATALOG" war mobil "GERÄTEKATAL"; `.gr-reiter button` `flex:0 0 auto`, `white-space:nowrap`, Leiste rollt (`overflow-x:auto`); im echten Chromium gemessen.

### `tests/test_geraete_zeitreihe_xtick_browser.py`
- Zeile 118: eine Rasterlinie je Messtag PLUS y-Rasterlinien, Untergrenze mindestens 12 vertikale Linien (x1==x2).

### `tests/test_geraete_zr_neu_hinweis_browser.py`
- Zeile 87: Suchfeld lebt im VERGLEICHs-Reiter; nach Sprungtest steht Katalog aktiv, `fill()` auf unsichtbares Feld läuft in Timeout, erst zurückschalten.

### `tests/test_llm_anker_und_kosten.py`
- Zeile 321: wirklich eigener Mechanik-Name behält eigenen, billigeren Anker, Kollision betrifft nur den geteilten Namen. 361: Kostenrechnung 2000 * 0,14/1M + 4000 * 0,28/1M. Zeile 434-438: 0,40 $ / 0,80 $ / 1,20 $. Rest Abschnittsüberschriften (Routing, Anker je Aufruf, Kostenzähler).

### `tests/test_llm_fallback.py`
- nichts übernommen: Kommentar erzählt Code nach (ein Fehlversuch auf PRO, danach direkt FLASH).

### `tests/test_llm_retry_policy.py`
- nichts übernommen: erzählt Code nach (503 sofort zurück; volles HTTP-Timeout verbrannt; 402 sofort zurück "billig"; Regel 10 CLAUDE.md).

### `tests/test_newsletter_render.py`
- Zeile 133-151: Treue-Test, Zeilen dürfen aus mehreren erlaubten Teilen bestehen; Abzug mit demselben Muster wie der Platzhalter, sonst bliebe "Ausgabe vom {datum}" als erfundener Satz. 330: Nummerierung, Absender in Klammern, Links auf eigener Zeile sind Merkmale, die ein HTML-Strip nicht hergibt.

### `tests/test_pipeline.py`
- Zeile 26: E2E-Test aktiviert Newsroom-Parser (Produktion `crawl_newsrooms: false`) und entfernt automatische Bing-Feeds/Fokus. 32: kopierte config/ bringt `config/promo_sources.yaml`; "js"-Marken laufen über Playwright (`collect/newsroom_js.py`), `fake_http` patcht nur `httpx.get`, daher Promo-Stufe aus, sonst echtes Netz. 78: Artikelseiten der Beispielquelle ohne og:image, sonst fragte `report/bilder.py` per eigenem httpx.Client im Netz. 87: neuestes Fixture-Item 14. Juli 2026, 8-Tage-Fenster wäre am 22.07. je nach Uhrzeit grenzwertig, deshalb Fixture stabil gehalten. 196: Zahl aus `BATCH_SIZE` gerechnet; Literal 37 bei Stapelgröße 15 zerbrach bei Erhöhung auf 24 am 27.08.2026. Rest englische Nacherzählung.

### `tests/test_promo_bilder.py`
- Zeile 162: stärkstes Angebot je Seite; a2 geht leer aus, sein Seitenmotiv ist an a1 vergeben. Rest Abschnittsüberschriften.

### `tests/test_promo_store.py`
- Zeile 175-198: bei erneuter Prüfung ohne frisches Bild (og:image verschwunden) oder ohne aufgelösten Deep-Link (LLM wählte keinen Kandidaten) darf das bekannte Bild/der Deep-Link nicht still verloren gehen; neues Bild/Deep-Link aktualisiert. Verlauf bleibt, nichts gelöscht.

### `tests/test_pruefe_promo_seite.py`
- Zeile 29: Fixture-Text erfüllt alle Formkriterien; Füllteil bewusst wortreich, Überlappungswert verweigert Auskunft bei unter `MIN_WOERTER_VERGLEICH` eigenen Wörtern (echte Aktionsseite mehrere hundert, ein viermal wiederholter Absatz nicht). 176: gleiches für Kriterium 7 (Eigenständigkeit).

### `tests/test_tarif_kacheln.py`
- Zeile 156: Satz vom 10.06.2026 trägt Feld `preistyp` nicht (gibt es seit 04.09.2026); Vorgabewert sorgt dafür, dass Bestandssatz beim Wiedereinlesen bleibt, was er war. 161: Blatt trägt Jahreszahl im Namen, Kachel nicht; `tarif_id` wirft sie weg, sonst zwei Tarife.

### `tests/test_tarif_ldjson.py`
- Zeile 101: "1&1 Unlimited XL" nennt in `description` keine GB-Zahl, dann steht dort nichts, nicht "unbegrenzt", nicht 0.

### `tests/test_tarif_telekom_kacheln.py`
- nichts übernommen: nur die Abschnittsüberschriften „Die gemessene Seite“ und „Gestellte Fälle“; die Trennung zwischen gemessener Fixture und gestellten Fällen ergibt sich aus den Testnamen.

### `tests/test_tco_bindung.py`
- Zeile 58: 0,00 + 1,00 + 24 x 19,99 (479,76) + 36 x 36,50 (1314,00); 68: 24 x 36,50, zwölf offene Geräteraten. 177: Abzug als eigener negativer Posten, Balkengrafik braucht ihn für Bonussegment. 198: 49,85 - 1249,00/36 = 15,16. 251: seit o2-Vertiefung (29.09.2026) liefert o2 24 UND 36 Raten; Bindung = gemessene Ratenlaufzeit, Restschuld nach Monat 24 = offene Raten, bei 24 Raten 0,00 EUR.

### `tests/test_tco_model.py`
- Zeile 55: Rechenbeispiel des Auftrags 1 EUR + 24 x 30 EUR = 721 EUR. 65: seit Phase 6 trägt Bündel Fremdschlüssel auf `data/state/tarife.jsonl`, ohne ihn nimmt `TcoDB` keinen Gerätepreis auf (Abnahmekriterium 3, Gegenprobe mit Schlüssel). 153: 29,99 x 24 = 719,76 | 1,00 | 30,00 x 24 = 720,00 | 39,99; 1480,75/24 kaufmännisch. 191: Zeitraum steht am Datensatz, jeder Leser nimmt ihn von hier (2.019,54/36); Gegenrechnung Ø x Zeitraum = Summe, eine Cent-Rundung je Monat erlaubt.
- Zeile 343: A1 (20.09.2026): Leitzahl "Kosten über 24 Monate" = Anzahlung + 24 Monate Tarif (phasengewichtet bei Preisphasen) + alle Geräteraten der eigenen Laufzeit + Anschlusspreis; vorher kappte `tco_24` Raten bei 24 (CHECK24-Vorwurf § 5.4 der Strategie, nur mit Ausweis daneben); Restschuld nach Monat 24 (z. B. 12 Raten à 30,50 €) ist in der Zahl und zusätzlich ausgewiesen (`restbetrag`); 1.459,00/24; 1 + 360 + 720 + 39,99; ohne Phasen gilt Tarifpreis flach.
- Zeile 502: 360 + 36 x 44,99 + 39,99; 24 x 19,99 + 39,99. 621-636: ohne IDs auf beiden Seiten Rückfall auf Namen; halb gefüllte Paarung ebenso (ID gegen nichts wäre immer ungleich und schaltete Geräteanteil still ab). 718: unmögliche Laufzeit wird benannt, nicht gerundet. 775-825: Ratenzahlung ohne Monatszahl kein Ratengeschäft; geratene Raten nicht in der Zahl: 20,00 x 24 + 0,00 + 39,99 = 519,99 EUR, 816,00 EUR geratene Raten NICHT darin; `tco_bindung` führt Zuzahlung der Bündelform nicht als Posten (eigener Befund), 1079,76 EUR geratener 24 Monate nicht darin. 887-892: vorhandene Segment-ID bleibt; fehlende Laufzeit am Altsatz benannt, nicht geraten; Form weder alt noch neu nicht erfunden. 948-969: Scoped-Ersetzung nur mit Telekom-Satz, o2-Referenz darf weder datiert noch entfernt werden; ohne Scope löscht dieselbe Menge den Fremden, Scope gehört in jeden Einzelanbieter-Lauf. 1141: IDs beider Bestände berühren sich nicht.

### `tests/test_trefferquote.py`
- nichts übernommen: nur Nacherzählung (1 von 2 neuen, 1 von 20 neuen; `# noqa: E402` bleibt).

### `tests/test_uebersetzung_seite.py`
- Zeile 86: Felder genau wie render_site() übergibt, handverlesene Liste liefe irgendwann gegen andere Vorlage. 209: Explorer steht auf den Archivwochen (`reports/<datum>.html`), nicht auf meldungen.html (dort HTML-Liste). 298: Rotwert nicht neu erfunden, aus Variable geholt; im Übersetzungsblock kein eigener Farbwert.

### `tests/test_volltext_feed.py`
- nichts übernommen: nur die Abschnittsüberschrift „Modell“ über den Modelltests.

### `tests/test_vorsortierung.py`
- Zeile 49: Mini-Lauf mit echter Konfiguration ohne Netz/Modell (wie E2E-Fixture in test_pipeline.py); `run.vorsortierung` nur am wirklich geschriebenen Bericht-JSON prüfbar, Teilzeichenketten-Prüfung auf Quelltext von `run()` bliebe grün, wenn das Feld verschwindet. 79: Nebenstufen aus, brauchen Netz/Playwright. 221: nach rechts offen, Liste enthält Wortstämme. 464: Verkettung aus pipeline.py, Vorsortierung meldet NICHTS als ungelesen, gescheiterter Analysten-Stapel schon; Aussortierter steht im Store und nicht mehr vor dem Analysten. 421: Bereich ohne Rest fällt aus Abbildung, sonst leere Überschrift im Bericht. 640-658: Frist: viel Luft eigene Obergrenze, wenig Luft Restzeit, zu wenig gar nicht anfangen, abgeschaltet bleibt abgeschaltet (Regel 8). 703: andere Stufen bekommen leere gültige Antwort (failsafe); geprüft wird das Feld im Bericht-JSON. Zeile 383 `# pragma: no cover` bleibt.
