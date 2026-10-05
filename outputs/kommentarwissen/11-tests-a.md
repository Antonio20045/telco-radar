# Kommentarwissen 11-tests-a

Stand: Commit aaa8b0d, 49 Dateien, 1543 Kommentarzeilen.

## Übernahmen in Code
- keine (reine Testdateien: Kommentare erklären Fixtures, Gegenproben und Befundgeschichte; Testnamen nicht umbenannt, weil das Wissen Geschichte ist und kein Name es trüge; keine neuen Tests, weil die behaupteten Invarianten schon durch die kommentierten Tests geprüft werden).
- `tests/conftest.py` nur protokolliert, nicht geändert.

## Für docs/betrieb.md
- Lehre aus Actions-Lauf 31422689829: `geraete_tco.json` (Maßstab) wird NACH `db.save()` geschrieben, ein Messtag ist nicht nachholbar, ein Maßstab schon (Quelle `tests/test_geraete_pipeline.py:455-460`).
- Ein Baseline-Reset entfernt die vier State-Dateien per `git rm`; Tests dürfen darum nicht an `data/state/` hängen (Quelle `tests/test_tarif_bezug.py:24-28`).
- Der Abdeckungs-Wächter: Fall „Kanal nicht eingerichtet“ (P1/C2-Nachtrag, 24.09.2026) ist eine andere Fehlerklasse als „Zustellung scheitert“; die GitHub-Annotation steht auf stdout (Quelle `tests/test_geraete_abdeckung_mail.py:157-183`).
- Nach dem Fristrest rechnet die Übersetzungsstufe: 380 s bis zur Reserve ist weniger als die eigene Frist, angebrochene Reserve heißt gar nicht anfangen (Quelle `tests/test_uebersetzung.py:327-329`).

## Widersprüche
- keine gefunden (nicht jede Behauptung gegen den Quelltext geprüft).

## Wissen je Datei

### `tests/conftest.py`
- Zeile 58: Eine Bibliothek, die selbst Quelltext liest (Vorlagen rendern, Aufrufstapel), ist kein „Test liest Quelltext“; nur ihre Ladefunktionen reichen durch.
- Zeile 98: Chromium löst außer localhost keinen Namen auf und schickt Nicht-Lokales an einen toten Proxy; 127.0.0.1 umgeht den Proxy.
- Zeile 261-264: pytest im Kindprozess erbt die Variable des Elternlaufs; ein lokaler Proxy würde Abrufe über 127.0.0.1 an der Sperre vorbeiführen.

### `tests/golden/test_goldener_lauf.py`
- Zeile 66: Ohne LLM bleiben gescheiterte Stapel ungelesen und gelten nicht als gesehen; mit Antworten ist alles gelesen.

### `tests/test_ballastquellen.py`
- Zeile 21: Die Tabelle Name → vorher gemessene neue Meldungen stammt aus Strategie 2026-08-27, §2 E9.
- Zeile 39: Der Lookup muss treffen, sonst prüft der Test nichts (Lookup-ins-Leere-Falle, CLAUDE.md §6).

### `tests/test_category_sweep.py`
- nichts übernommen: nur Ablaufkommentare (gleiche URL erneut gesehen; nach wenigen Wochen sind alle Hebel dran).

### `tests/test_ct_log.py`
- Zeile 53: Die Antwort deckt auch Namen außerhalb der abgefragten Domain ab, das macht sie wertvoll (congstar betreibt congstarnews.de).
- Zeile 163: Der Timeout in `hole()` ist eine eigene Klasse, kein leeres Ergebnis.
- Zeile 350: telekom.de MUSS als groß markiert sein, sonst läuft jeder Lauf in einen vermeidbaren Timeout.

### `tests/test_diff_curator.py`
- Zeile 80: Im `--no-llm`-Modus (relevance None) wird trotzdem behalten, damit die Bibliothek nie leer bleibt.
- Zeile 107-137: neue Woche, neue Store-Instanz aus derselben Datei: alter Move überlebt, beide Wochen dauerhaft geschrieben, Bestand gedeckelt.

### `tests/test_differentiation_editor.py`
- Zeile 35: Alte Gliederung entfallen: „Konkrete Entwicklungen“ war die Aufzählung, die auf der Seite schon als Karten steht, „Quellenbasis“ führte dieselben Quellen ein drittes Mal auf.

### `tests/test_eine_seite_querlinks.py`
- Zeile 24: Verweis auf die Alt-URL zählt egal ob href/src/action, beliebige Anführungszeichen, Prefix (`../`, `/`), Suffix (`#anker`, `?query`); nur die Weiterleitungsdatei selbst darf und muss auf `geraete.html` zeigen.

### `tests/test_geraete_abdeckung.py`
- Zeile 39: Fixtures des Pipeline-Tests sind der kürzeste Weg zu einem Lauf mit echtem Store.
- Regeln 1-6 des Abdeckungs-Wächters: Ein Tag reicht; Schwelle; „nicht gelesen“ ist kein Ausfall; ohne Vortag kein Alarm und trotzdem kein „in Ordnung“; Bündel sind Zeilen (Telekom-Fall); Alarm ist Meldung, kein Griff (nichts wird gealtert).
- Zeile 513 (Regel 5, Befund S2-1): Ein einziger am Fenster abgewiesener Abruf setzte `bilanz.ausserhalb_besuchszeit`, der ganze Anbieter wurde NICHT_GELESEN, auch mit vier gelesenen Produktseiten und drei Listungen; der Wächter war für medimax und ep.de (hängen an ihrem Fenster) blind. „Gar nicht angefasst“ und „teilweise gelesen, Tür ging zu“ sind zwei Auskünfte.
- Zeile 610 (S2-2): `liefert` kommt aus dem Bestand; ein heute nicht erreichter Anbieter bekam grünen Punkt und „liefert“. Der dritte Seitenzustand „heute nicht gelesen“ kommt aus derselben Definition wie der Wächter (Lesezustand des Bezugstags).
- Zeile 856 (Regel 6, S2-B): Über 45 simulierte Tage (ein voller Tag, danach nur Teiltage) meldete der Wächter 29 Tage hintereinander denselben Befund mit je einer Mail; ab Teiltag 31 fiel der letzte volle Tag aus dem 30-Tage-Journal, keine Vergleichsbasis, dauerhaft kein Alarm; ein echter Totalausfall an Tag 45 löste nichts mehr aus. Soll: Wechsel an Tag 2, danach ein Wiederholungstag je Woche, nie länger als eine Woche still, Totalausfall an Tag 45 sofort.
- Zeile 942: Neuen Namen erst im Test importieren, ein ImportError beim Einsammeln wäre kein roter Test.
- Zeile 956 (S2-C): `Messtag.beobachtet` liest `zustand == GELESEN or zeilen > 0`; der zweite Zweig war ungeprüft, bei Streichung blieben alle 231 Geräte-Tests grün. Verglichen wird mit dem 02. (100 Zeilen), nicht dem 01. (50).

### `tests/test_geraete_abdeckung_mail.py`
- Fälle 1-4: kein Messtag (keine Mail); Alarm liegt vor (ohne `--trocken` geht die Mail wirklich hinaus; derselbe Satz in Protokoll, drei Kanäle, eine Wortform); Zustellung scheitert; Fall 3b Kanal nicht eingerichtet (P1/C2-Nachtrag 24.09.2026); Fall 4 Anbieter, den die Konfiguration nicht mehr kennt („Gespenst“), Alarm ist da, nur nicht für diesen Lauf.

### `tests/test_geraete_adapter_netzbetreiber.py`
- Zeile 81: Pflichtparameter müssen mit, sonst antwortet die Vodafone-Schnittstelle mit HTTP 400 und nennt das fehlende Feld.
- Zeile 93: Gemessen am echten Abruf: 999,90 EUR (256 GB), 1129,90 (512 GB); nicht die Bündelzahl (Liste führt dasselbe Gerät mit 1 EUR Anzahlung), die der Lockpreis-Wächter seit dem 10.08. raushält.
- Zeile 202: o2-Preis ist nachrechenbar: Anzahlung plus 24 Monatsraten.
- Zeile 271: 800-Euro-Sägezahn-Falle vom 10.08.2026, jetzt vierfach; „Pro Max“ darf nicht auf „Pro“ fallen (Xiaomi, Samsung ebenso).
- Zeile 317: Stand-Commit-Fall: Auto-Eintrag wird erkannt; Router bleiben draußen; ein iPad-Titel trifft nie fuzzig ein iPhone (iPad-Anker ist P5-Auftrag 3, Test pinnt die Lücke nicht fest).
- Zeile 341: Die zwei Schnittstellen verlangen Kopfzeilen, ohne sie 404 statt Daten.

### `tests/test_geraete_aktionen.py`
- Zeile 86: Bündelpreis bleibt der ohne Eintausch (33,50 × 36 + 97 = 1303), die Trade-in-Rate 26,00 steht nirgends im Satz.
- Zeile 103: Geschenkter Anschlusspreis steht als 0, nicht als 15 („eingerechnet“ = schon abgezogen).
- Zeile 236: Ein Lauf ohne die Aktion löscht sie. Zeile 268: einen Tag nach genanntem Ende ist der Grundpreisnachlass weg.

### `tests/test_geraete_alterungs_abzeichen_mobil_browser.py`
- Zeile 32: Bündel-Kopf einer alten o2-Zeile wortgetreu aus `render_site()` (Stand 24.09.2026) in der schmalen Spalte `.gr-bnd-an`.
- Zeile 99: QA-Fix 24.09.2026 (Punkt 7): Abzeichen dort `block` statt `inline-block`; entscheidend ist die Rechteckzahl (EIN Rahmen), „inline“ zeichnet je Zeile einen Rahmen (der gemeldete „Stapel Einzelkästchen“).

### `tests/test_geraete_buendel_o2.py`
- Zeile 154: Ohne den Treffer-Check ist die Schleife leer und `assert` nie ausgeführt.
- Zeile 189: Adresse unterscheidet sich von der produktiven nur im fehlenden `?hwOnly=true`.
- Zeile 305: `lies_buendel` setzt das Rabatt-Flag auf jedem echten o2-Rohsatz; seit P0-B-fix1 wertet die Stufe es nicht mehr aus: o2s -5 EUR sind kein bedingter Nachlass, sondern der Preis (Modulkopf `tco_buendel.py`).
- Zeile 453: 24 × 34,00 EUR Raten stehen in keinem Bestandteil; eine geratene Laufzeit hätte 816,00 EUR in die Summe geschrieben, darum benannte Lücke (Regel 9).
- Zeile 466: 66 von 66 Tarifen lösen auf; bis 29.09.2026 waren es 65, „O2 Mobile on Demand M“ (ohne „Plus“) trug keinen Kachel-Slug (Bündel-Slug = Tarif-ID der Kachel, `Tarifbestand._slug_ist_tarif_id`).

### `tests/test_geraete_buendel_vodafone.py`
- Zeile 243: Der `sub`-Fall hat keine separate Geräterate (Modulkopf). Zeile 287: Vertragsphasen enden bei 24, die Finanzierung nicht.
- Zeile 344: `totalMonthlyRatePrice` trägt bei 12 und 36 Monaten ZWEI Phasen; scharfe Gegenprobe: Phase 0 ohne Ende, Phase 1 Ende 24; wer nur Phase 0 liest, verliert das ganze Bündel.
- Zeile 472: Befund 29.09.2026 „Alle Tarife × alle Laufzeiten“; Bündel-ID trägt Tarif und Laufzeit; FamilyCard ist Zusatzkarte ohne eigenes Blatt im Bestand.
- Zeile 785: api.vodafone.de hat keine robots.txt. Zeile 415-420: ein GET je Gerät, 5 × 3 Mobil + 4 FamilyCard.

### `tests/test_geraete_buendel_zeilenkopf_d3.py`
- Zeile 84: Fixture-Vodafone deutlich teurer als congstar (Δ > 15 EUR UND > 3 %), damit `geraete_vergleich.WESENTLICH_*` greift.
- Zeile 189: `data-laufzeit` trägt die Tariflaufzeit (immer 24), die Ratenlaufzeit steht in `k.raten_laufzeit`.
- Zeile 365: Gegenprobe Orakeltest Regel 5: class bleibt `gr-bnd`. Zeile 435-466: Mutationsproben je Kernänderung.
- Zeile 474: REVIEW-FIX S2: Hauptzahl ignorierte die Wesentlichkeitsschwelle; eigene Fixture Samsung Galaxy S26 (Abstand 8,00 EUR gegen 1.921,00 EUR unter beiden Schwellen); zwei congstar-Zeilen mit gleicher Ratenzahl würden sich im Lookup `_congstar_zeilen` überschreiben.
- Zeile 603: REVIEW-FIX S3: `zerlegung_balken()` Truthiness statt `is not None`, kein 0,00-€-Phantomsegment.

### `tests/test_geraete_erosion.py`
- Zeile 94: Gemessener Fall: tote Adressen der Vornacht fallen aus der Sitemap, jede Nacht rund ein Viertel Verlust (24,4 / 23,5 / 23,1 / 25,0 / 20,0 % tot), jeder Einzelschritt unter 30 %; Soll: Befund spätestens in der dritten Nacht (noch 26 von 45 Seiten).
- Zeile 260 (S2-1): Einheit der Schwelle; solange der heile Tag im Fenster steht (Nächte 2-7) ist der Schwund 33 %; Nacht 9 sieht nur noch Tage 3-9 mit 30 Adressen. Stabile Lücke ist keine Erosion.

### `tests/test_geraete_faden.py`
- Kriterien 1-6 (G0 einzige Grafik je Modellblock; Antwortzeile zwischen Auswahl und Graph; Titelzeile siehe `test_geraete_rahmen.py`; Alarm-Kacheln seit 11.09.2026 (O2) auf dem Wettbewerbs-Radar, Tarifmaßstab hinter Aufklappung; E2: Maßstab im EINEN Fuß-Aufklapper „Maßstab & Datenlage“ (§3.1c); Einzel-Punkt-Anbieter; Reiterleiste E3 mit vier Tafeln auf einer Seite).

### `tests/test_geraete_fragment_wachstum.py`
- Zeile 69: Historie ersetzt bei zweitem Lauf desselben Tages, Zählung bildet das nach. Zeile 93: fehlende Datei ist leere Messung, kein Fehler. Zeile 126-133: Fragmentgrenze 40 Paare = 40.000 B → 1 Tag, aufrunden (34 Paare → 0,4 → 1 Tag), Tag genau auf Grenze gilt als gehalten.
- Zeile 191: Keine Historie: keine Zeile (0/0/0 wäre vorgetäuschter Messpunkt der PM-6-Reihe).

### `tests/test_geraete_methodik_umzug.py`
- Negativliste: entfernte Lesehilfen; Positivliste: Daten-Aussagen bleiben (z. B. `wr.grafik.basis` = len(alle) aus `grafik_zeilen()`, S1-Fix Review D4a; Kachel-Summe der Alarmtabelle; Händler-Sektion Saturn/iPhone 15; Leer-Satz bleibt im DOM; mind. ein Quellenlink mit Abrufdatum). Fußzeilen-Link muss auf den Methodik-Anker zeigen, sonst landet ein Handy-Leser auf der Quellenübersicht. P3-E1: Tarifleiter mit neuem Wortlaut.

### `tests/test_geraete_o2_zeilen.py`
- Zeile 52: Fixture „Ohne Tarifband“: unbegrenzte Tarife, Tarife ohne Volumen, Händler-Barpreis stehen als kompakte Gruppe unter der Band-Tabelle (§ 7), 1&1 ohne tarif_id (1&1-Tarife nicht im Tarifbestand).
- Zeile 405: P4-Fix (Sicht-Prüfung 18.09.): Inhalt im `<template>`-Pool, Test liest die Vorlage (`vorlage_text`), BS4 versteckt Template-Inhalt vor `get_text`.
- Zeile 482: Legende nennt die Lücke je Band, kein Satz je Anbieter (O1-Befund: 145 Einzelzeilen). Zeile 552: Amazon/Expert ohne Preis keine Zeile, seit E2 keine Einzelnennung (Antonio 9b.7). Alarmtabelle und „Bei Wettbewerbern gelistet“ sind weg (jetzt `wettbewerbsradar.html`, `tests/test_wettbewerbsradar_alarme.py`).

### `tests/test_geraete_pipeline.py`
- Zeile 361: HTTP 500 = „nicht gelesen“; mit 404 wäre es seit 22.09.2026 eine tote Adresse (benannte Lücke).
- Zeile 455: Maßstab aus dem Tarifbestand (Phase 6, 04.09.2026) steht NACH `db.save()` (Lauf 31422689829). Zeile 510: Festnetztarif ist kein Maßstab für ein Smartphone-Bündel.
- Zeile 599: `kind: buendel` landet in `geraete_tco.json`, nicht `geraete_db.json` (Bündelmonatspreis in Kassenpreisspalte war der Anlass des Vorhabens).
- Zeile 739: P0-B-fix1: B2b ersetzte einen Tag lang den gemessenen Bündeltarifpreis durch die SIM-only-Grundgebühr (19,99 EUR), Leitzahl aller 72 o2-Bündel stieg um 120,00 bis 276,00 EUR ohne Preisänderung; o2s -5 EUR sind der Preis (`analyze/tco_buendel.py`).
- Zeile 892: S-5 (09.09.2026) 1&1-SIM-only-Messung im Referenzblock; Collector selbst in `tests/test_tarif_einsundeins_simonly.py`. Zeile 1060: Lauf mit Scope Telekom darf keinen Abruf gegen 1und1.de senden; Fremde bleiben bytegleich.

### `tests/test_geraete_pruefung.py`
- Zeile 252 (W3): Keine Kennzahl größer als Zahl beobachteter Geräte; Beispiele: ein Gerät × drei Anbieter = drei Listungen, EIN Gerät; zwei Geräte × vier Anbieter × acht Farben = 64 Listungen, 2 Geräte.

### `tests/test_geraete_reiter_browser.py`
- Zeile 48: 20 Geräte, nicht 2, sonst greift `SICHTBAR_MAX` (15) nie und der „alle anzeigen“-Test überspringt sich selbst (Skip sieht wie Erfolg aus).
- Zeile 109: Fixture mit sechs Messtagen statt vier (`DIAGRAMM_AB_TERMINEN`); Medimax nur an den ersten zwei Tagen gesehen, damit beim Verengen ein Anbieter herausfällt (mobilcom-debitel lieferte ab 21.08. nicht mehr); `last_verified` muss zum letzten Messtag passen; 03. und 04.08. liegen bewusst in derselben Kalenderwoche (Rasterschalter ändert Messterminzahl nicht).
- Zeile 206: TCO-Bestand der Fixture (bis 04.09.2026 fehlte `geraete_tco.json`, zwei von drei Tabellen rendern sonst nicht); 14 Referenzen wegen `REFERENZEN_SICHTBAR` = 12; Tarifbestand `tarife.jsonl` gehört zur Fixture (Phase R, Bindung); Preisphase `bis_monat: 24` und ab 25 tragen „ab Monat 25“ (Katalog D); O1 (11.09.2026) `datenvolumen_gb` 10 + 10*i über alle drei Bänder.
- Zeile 330: Vier Messtage je Listung (30.08.2026); ein Verlauf wird erst ab `DIAGRAMM_AB_TERMINEN` gezeichnet (zwei Punkte sind eine Gerade, sieht wie Trend aus). Zeile 362: jeder Reiter unter drei Bildschirmen; keine Beschriftung kleiner (alte Grafik hatte 236 Texte, auf 390 px real 2,7 CSS-Pixel); Meta-Etiketten des genehmigten Prototyps bewusst 10-11 px (Antonios Graph-Entscheidung).
- Zeile 546: E2: Zeitreihe ist ein SVG; G0 gehört in den Verlaufs-Reiter, G1 ersatzlos gefallen; genau ein sichtbares Bild (breite und schmale Variante im DOM, Spezifitäts-Falle, siehe style.css). Zeile 570: O2 11.09.2026 Alarmtabelle auf Wettbewerbs-Radar gezogen.
- Zeile 662: 28.09.2026 Antonio: „ich verstehe den Unterschied zwischen Vergleich und Preisverlauf nicht“; Reiter heißen nach dem, was sie messen, die zwei Ein-Gerät-Reiter stehen nebeneinander.
- Zeile 815: E3 17.09.2026 „alle anzeigen“ zuerst; drei Sektionen teilen das Budget einer Tafel, Deckel bei 5 (vorher 12). Zeile 905: Klick toggelt, Aufklapper kann schon offen sein; Gegenprobe „wirklich offen“.
- Zeile 1037: Reiter 3 am 30.08.2026 nachgetragen, weil kein Test je in `#gr-vsuche` tippte. Zeile 1090 (P4b, Re-Check 18.09.2026): Sichtbarkeit messen, nicht `hidden`-Attribut (`.gr-leit{display:flex}` übersteuerte [hidden]); computed display UND Boxhöhe.
- Zeile 1254: Achse deutsch lesen, nicht `parseFloat` („1.099,00 €“ → 1,099); die Seite wurde einmal fälschlich angepasst, Reviewer meldete es: schwacher Testparser darf die Seite nicht bestimmen. Zeile 1316-1376: Legende und Tabelle nennen dieselben Anbieter bei vollem, verengtem (ein früher Anbieter fällt heraus) und Ein-Tag-Fenster; Gegenprobe an der Legende, nicht an der Tabelle.
- Zeile 1590: Nachbesserung 30.08.2026 im echten Chromium. Zeile 1665: kein Diagramm ohne Linie. Zeile 1775: Marke nahe, nicht exakt auf Höhe; Versatz früher bis 235 px (geloeschte Positionskarte), keine Überschneidung mit Punkt-Kreis.
- Zeile 2118: B5 (31.08.2026) Standardansicht nach Hersteller und Aktualität sortiert, Zustand neu, erste Bildschirmseite mindestens drei Hersteller; sieben Geräte je Hersteller, sonst fällt „Reihum entfernen“ nicht auf; `device_id()` aus `geraete_model` nutzen (Xiaomi/Redmi-Fall: „apple-modell-1“ nicht „apple-apple-modell-1“). Zeile 2276: „Erste Bildschirmseite“ gilt ab dem Reiter (Zeitungskopf braucht über 840 px, ohne Scroll passt keine Zeile, mit Scroll acht).
- Zeile 2372: Rot-Deckel P4b Re-Check 18.09.2026: `.src-table a{color:var(--red)}` (0-1-1) schlug `.gr-sprung` (0-1-0), elf Sprung-Links vollrot, 12 vollrote Elemente gegen fix.md „Katalog 5“; Farbwert aus der CSS-Konstante lesen. Zeile 2468: B2/B3 (31.08.2026) Deckel folgt der Sortierung, seit P3 nach Modellzeile. Zeile 2550-2635: B4/B5/B7 Quelllink im Anker; P3 Anbieterzelle im Zeilen-Aufklapper.
- Zeile 2716: P1 dritte Nachbesserung 31.08.2026: zwei synthetische Fixtures verfehlten den Fall zweimal, darum Messung gegen `data/state/geraete_db.json` und `config/geraete_katalog.yaml` (Modellzeilen, nicht Listungen: 24 Zeilen des iPhone 17 Pro bis P3). Zeile 2923: Attribut heißt `data-s-geraet`, `dataset.geraet` liest still null.
- Zeile 2998: Bestpreis-Stempel (04.09.2026, idealo-Muster): Kachel sagt wie tief, Stempel wann. Zeile 3195-3207: drei Tabellen (vierte G2 mit P2 17.09.2026 gefallen); dynamische Verlaufstabelle rollt in `#gr-vtabelle`.
- Zeile 3221: Phase R 04.09.2026 TCO-Hauptansicht im Browser; Balkenlänge G1 seit BRIEF_FADEN 05.09.2026 statisch in `test_geraete_tco_hauptansicht.py::test_die_balkenlaenge_entspricht_dem_betrag`; O2 11.09.2026 Karten sind Tabellenzeilen `.gr-bnd`. Zeile 3259: Seite modulweit geteilt, unter xdist ließ ein Test einen Reiter offen (auch auf main rot). Zeile 3385: `_umgebung` trägt den `?modell`-Deep-Link, als Basis wäre ein Phantompfad entstanden.

### `tests/test_geraete_robots.py`
- Zeile 149: MJ12bot ist komplett gesperrt, das darf uns nicht treffen. Zeile 181: Beim Wächter wird ausschließlich die robots.txt geholt, nicht die Seite; im Fenster derselbe Pfad erlaubt.

### `tests/test_geraete_stille_tage.py`
- Zeile 86: Gegenprobe: derselbe Anbieter mit einem Liefertag davor alarmiert. Zeile 206: ersetzter Tag zählt als EIN stiller Tag, `letzter_fund` (09-01) bleibt Anker; wieder eingelesener Tag sagt nichts über Adressen (benannte Lücke, keine 0).

### `tests/test_geraete_tco_historie.py`
- Zeile 145: Leitzahl steht fertig in der Zeile (P5 zeichnet die Reihe ohne Nachbau). Zeile 173: derselbe Tag mit korrigierten Werten aktualisiert die Zeile, sonst log die Reihe um die Zahl der Nachtläufe. Zeile 271-296: Stand ohne Historiendatei darf nicht werfen, Stand bleibt von heute.

### `tests/test_geraete_tco_terminologie.py`
- Zeile 71: o2-Leitzahl über 24 Monate Tarif, Geräteraten laufen 36; seit A1 stehen alle 36 in der Zahl (1 + 39,99 + 24 × 14,99 + 36 × 20,00 = 1.120,75 €), die 12 Raten nach Monat 24 zusätzlich als offener Betrag.
- Zeile 81: S-Q4 09.09.2026 „Gerechnet über 24 Monate Bindung“ war Widerspruch; Horizont heißt Horizont, „Bindung“ nur für Tarif und Raten. Zeile 103: E2 Graph-Titel gefallen, Etikett lebt im Antwort-Satz („Kosten über 24 Monate“), kein „TCO-36“. Zeile 126: O2 11.09.2026 Sortier-/Anbieterfilter entfallen (§4 Entscheidung 3, 4-7 Zeilen je Bandliste).
- Zeile 139: Kein „(0 %)“ auf TCO-Zeile (Zinssatz nicht gemessen); Prüfung gegen Vorlagentext (P4-Fix Template-Pool). Zeile 191: P0-B-fix2 Befund 3: Etikett nennt Zeitraum der Zahl (36 × 44,99 EUR für Tarif und Gerät = 36 Tarifmonate, nicht 24; „2.019,54 €“); offene Einmalzahlung als benannte Lücke, nicht 0,00.

### `tests/test_html_escaping.py`
- Zeile 76: Entscheidend ist, dass aus „onerror“ kein Tag wird, nicht dass die Zeichenfolge verschwindet; nicht auf `<img` prüfen (Seitenlogo ist ein img-Tag); Anführungszeichen escaped.

### `tests/test_lieferzeit.py`
- Zeile 182: Dauerhaft langsam ist kein Engpass; ohne Vorwert auch nicht (erster Messpunkt ist Grundlinie). Zeile 225: Behalten wird das Ende. Zeile 279: Originaltext wird immer mitgeführt (Beleg). Zeile 292: eine festgelegte Variante je Produkt, sonst vergleicht der Verlauf wechselnde Konfigurationen. Zeile 296: Ident-Verfahren je Anbieter bestimmt die effektive Wartezeit.

### `tests/test_llm_leere_antwort.py`
- Zeile 64: Meldung nennt die drei Dinge zum Handeln: nur gedacht, wie knapp das Budget war, was zu tun ist.

### `tests/test_luecken.py`
- nichts übernommen: nur Abschnittsüberschriften.

### `tests/test_navigation_aktiver_eintrag_browser.py`
- Zeile 27: Struktur der Rubrikleiste wortgetreu aus `base.html.j2` (fünf Einträge der Marktrecherche, „Geräte“ als aktiver letzter Eintrag, der gemeldete Fall).

### `tests/test_newsletter_protokoll.py`
- nichts übernommen: Überschriften und Rechenbeispiel (300 - 80 = 220 gebraucht → 73 %); Spaltenliste Ausgabe, Segmente, Zugestellt, Fehler, Rückläufer, Abmeldungen, Quote, Limit.

### `tests/test_newsletter_segments.py`
- Zeile 176: Derselbe Pepper ergibt denselben Hash, sonst wäre die 24-Stunden-Sperre wirkungslos. Zeile 357: Themenfeld hat keine Region, läuft unter „global“ wie weltweite Fachpresse.

### `tests/test_promo_editor.py`
- nichts übernommen: `# must not raise` erzählt den Code nach.

### `tests/test_promo_mehrseitig.py`
- Zeile 75: `kind` gilt je Seite, nicht je Marke (statische Unterseite unter JS-gerenderter Leitseite ist Normalfall). Zeile 127-149: zweite Seite derselben Marke erbt den alten Markenschlüssel nicht. Zeile 210: zweiter Fehltreffer in Folge beendet. Zeile 259: kein Duplikat in der Konfiguration (je Lauf ein LLM-Aufruf umsonst); Leitseite steht vorn. Zeile 312-340: Migration Markenschlüssel → Seitenschlüssel, `prune` entfernt den alten, zweiter Lauf meldet nichts als verändert.

### `tests/test_promo_raster_browser.py`
- Zeile 51: Toleranz zwischen Karten einer Reihe nicht null: Rückfallschrift der Sandbox und echte Source Serif 4 runden Zeilenhöhen verschieden; der gemeldete Fehler war 110 px groß. Zeile 117: ohne Durchscrollen bleiben `loading="lazy"`-Bilder ungeladen (`naturalWidth` 0).
- Zeile 200: Leere Rasterzellen bei genau einer bzw. drei weiteren Karten (27.08.2026 live gemessen: PremiumSIM, simplytel je 1 leere Spalte, ALDI TALK 1 leere Zelle unten rechts); `report/promo.gewichte()` rechnet seitdem gegen die tatsächliche Kartenzahl. Künstliche Blöcke statt `promo_db.json`.

### `tests/test_promo_seite.py`
- Zeile 48: Platz in der Anbieter-Rangfolge ordnet die Seite seit 08.08.2026 (`report/promo._rang`); Netzbetreiber vorn, eigene Marke am Ende. Zeile 120: `highlight_count` zählt hervorgehobene Karten (seit Markenraster jede sichtbare Aktion). Zeile 280: Titel genau einmal in der Zeile.
- Zeile 447: Schriftkacheln mit identischem Text („Wechsel- oder Altgeräteprämie“ ×4, je Markenblock) waren der zweite Befund; seit 08.08.2026 trägt jede Karte ohne Motiv eine Kachel, über 13 Blöcke hinweg tragen zwei Angebote zweier Anbieter beide „10 €“; als Fehler liest sich nur Wiederholung im Block.

### `tests/test_promo_view.py`
- Zeile 159: Bild hängt seit 07.08.2026 am Angebot, nicht an der Marke (bis zu acht Aktionen je Marke). Zeile 203: Je Wettbewerber eine Karte, die Auswahl der stärksten trifft `analyze/promo_ranker.py` (Score + Hysterese), Anzeige respektiert sie nur.
- Zeile 399: Antonio 08.08.2026: „Viele Karten sind Schriftkacheln mit identischem Text … sieht nach Fehler aus.“ Zeile 479: Querformat 800x419 = 1,91 bleibt eins. Zeile 486-500: Mechaniken-Balken zählen Marken, nicht Angebote; drei Aktionen einer Marke sind Kampagne, zwei Aktionen zweier Marken Trend (Wechselprämie vorn).
- Zeile 618: Gewichtung der Aufmacherkarte (16.08.2026) hängt an Motivbreite und Zahl übriger Karten, wird hier gerechnet, nicht in der Vorlage; zwei weitere Karten füllen sie vollständig (Spalte 3+4). Zeile 750: Entdopplung darf keine zwei Angebote zusammenwerfen (29.08.2026).

### `tests/test_redaktion_zweistufig.py`
- Zeile 149: Zwölfmal so viele Meldungen, aber die Eingabe wächst höchstens um die fünf stärksten je Bereich; Bereiche schlagen voll durch. Zeile 197: Themenfelder als H3, Regionen als H2. Zeile 301-312: Modus-Schalter: heutiger Lauf, 1000-Quellen-Lauf, Schwelle inklusive, fällt auf auto zurück.

### `tests/test_suche_page.py`
- Zeile 21: vier Seiten der Marktrecherche nach dem Redesign; `search_index.json` ist, was `app.js` lädt. Zeile 148: Rubrik heißt „Quellen“, „Transparenz“ war Behördendeutsch. Zeile 198-214: `suche.html` ist seit 08.08.2026 wieder echte Seite; Weiterleitung zeigt dorthin, Meta-Refresh plus Link ohne Refresh.

### `tests/test_tarif_bezug.py`
- Zeile 24: Messung vom 04.09.2026 als Fixture, nicht in `data/state/`, weil ein Baseline-Reset (CLAUDE.md § 6, vier State-Dateien `git rm`) sonst die Testdatei mitnähme. Zeile 30: genau EIN Test sieht den ausgelieferten Bestand (Abnahmekriterium Phase 6).
- Zeile 115: Weg über den Betrag: Güte `mittel`, nie `hoch`. Zeile 236 (B3, 21.09.2026): Telekom MagentaMobil S/M/L/XL stehen je zweimal (Pflichtdokument 2021-2024, Live-Shop-Kachel 15.09.2026; S 6 vs. 30 GB, M 12 vs. 50 GB, L 80 vs. 100 GB); `tarif_crawler.uebernimm_stand` gab dem zuerst gesehenen Preistyp den bare `tarif_id`, `report/geraete_view.py` reichte die rohe Zeitreihe durch, die Karte zeigte immer das Pflichtdokument. Rohe Zeitreihe bleibt vollständig, aktuelle Lesart unter bare Schlüssel.
- Zeile 558: Marke steht bei Telekom/congstar nur auf der Produktseite; `TcoDB.upsert_buendel` ohne `tarif_id` wirft, Phase 4 hätte keinen Bündelpreis speichern können. Zeile 646: dritter Weg Slug (04.09.2026), o2 nennt Bündel- anders als SIM-only-Tarif; „M“ und „M Plus“ nicht per Heuristik verbinden. Zeile 733: Geräteblatt P3 28.09.2026.

### `tests/test_tarif_crawler.py`
- Zeile 364: Falle: erreichbar, aber nicht verlinkt (enumerierender Crawler fände sie; IDs werden nie hochgezählt, CLAUDE.md Regel 4). Zeile 440: Drosselschwelle halbiert.
- Zeile 701: nachgetragen 04.09.2026: aus 1114 verlinkten Telekom-Dokumenten wurden fünf gewählt, vier davon derselbe Tarif in vier Vermarktungsständen, der älteste von 2017; ohne Beschriftung bleibt Seitenreihenfolge (bei congstar die einzige Ordnung, laufende Tarife oben); ohne Reihum stünden die nächsten acht S-Dokumente.
- Zeile 905: zweite Lesart: Einstiegsseite ist die Nutzlast (04.09.2026); `verlinkt` bleibt 0; Meldung nennt Quellenart (keine gesetzliche Wahrheitsbewehrung); o2 steht zweimal (Pflichtblätter und SIM-only-Kacheln), laut Konfigkopf erlaubt, sonst kein o2-Bündel im TCO-Bestand; zwei Lesarten sind zwei Zeitreihen, eigene Grundlinie ohne Änderungsmeldung.

### `tests/test_textwerkzeug.py`
- Zeile 19: Befund vom Review: Das Ratschlag-Muster steht nicht wörtlich in den alten `_ADVICE_PHRASES` („Vodafone prüfen könnte“ statt „Vodafone könnte“). Fallen muss: Rat an Vodafone auch ohne Verb („für Vodafone“), im Genitiv, in erster Person, im Telegrammstil (Adressat und Verb in zwei Teilsätzen); Befund vorn, Folgerung hinten: Befund bleibt; ohne Beobachtendes steht die Karte ohne Zweitzeile.
- Zeile 75: Bleiben muss: Beobachtungen ÜBER Vodafone-Gesellschaften (Regel trifft nur Ratschläge AN Vodafone), konjugierte Feststellungen (nur die Grundform wäre ein Rat), „MeinVodafone“ als Produktname, alles ohne Adressat.

### `tests/test_uebersetzung.py`
- Zeile 155: Gegenprobe: als Faktor gerechnet hätte der Fall bestanden. Zeile 240-246: Modell gibt nur Artikeltext zurück; ~1200 Zeichen ein Abschnitt, ~12 000 Zeichen mehrere. Zeile 327: 380 s bis zur Reserve ist weniger als die eigene Frist; angebrochene Reserve: gar nicht erst anfangen.

### `tests/test_verlauf.py`
- Zeile 80: dünner Monat steht im Gitter, trägt aber keine Bewegungsaussage. Zeile 112: Ausreißer liegt zwei Monate zurück; gegen Vormonat Ruhe, gegen den Durchschnitt der Rückstand sichtbar (ehrlichere Aussage).

### `tests/test_versand.py`
- nichts übernommen: Ablaufkommentare (Schwelle ja/nein, ein Montag).

### `tests/test_wettbewerbsradar.py`
- Zeile 92: P3-E1 Vodafone-Tarifleiter „mit Smartphone“ XS 18, M 60, L 100 GB; Stufen liegen, wo die festen Bänder lagen (10/12/18 GB XS, 40/60 GB M, 80/100 GB L); 80 GB liegt je 20 GB von M und L, Gleichstand zur größeren Stufe.
- Zeile 175-200: Fälle M1-M4 (M1 zwei VF-Bündel, o2 führt zwei Tarife in XS = zwei Karten im selben Band; RAD-1b jede gemeinsame Karte wird ein Paar; M2 nur Näherung, positive Abweichung; M3 zwei o2-Bündel in L, Band-Mismatch, günstigste Karte ist Belegzeile; M4 keine Basis, keine Abweichung, drei Zeilen). Zeile 449-536: congstar-Zeile je Karte, nicht je Marke.
- Zeile 577: Netzbetreiber ist kein Händler (§3 Zahlen nie vermischt). Zeile 689: vier nicht erhebbare Händler des §8 stehen wörtlich in der Konfiguration. Zeile 955: `.gr-a-zeile` ist mehrdeutig (Alarm- und Modell-Listenzeilen), Selektor im Kontext der Abweichungs-Sektion (Klassen-Falle). Zeile 1022: seit 28.09.2026 trägt Reiter „Übersicht“ den Weg selbst, doppelter Fußlink gefallen.
- Zeile 1204: nur eine vergleichbare (neues Gerät) VF-Karte eröffnet den Paar-Pfad. Zeile 1254 (P0-B-h3, 21.09.2026, Befund 1): Horizont-Tor im Radar; `_zeile_fuer_anbieter` und `_paar_zeile` bildeten `prozent` ohne Blick auf den Zeitraum; am Bestand vom 21.09.2026 trugen 26 Radarzeilen ein Vorzeichen für ein Angebot, dessen Bündelzeile „andere Laufzeit“ sagte (Pixel 11 512 GB: `data-s-prozent="-0.7"`, gesamt 1835.54 bei 1&1/36 Monate gegen 1847.8 Vodafone/24 Monate); zwölf Tarifmonate jenseits des Horizonts sind größer als das Delta. Regel: `tco_model.zeitraum_vergleichbar`, kein zweites Tor. Der Strich heißt „kein Angebot“ (A2), hier ist ein Angebot, die Zahl bleibt mit Beleg.
