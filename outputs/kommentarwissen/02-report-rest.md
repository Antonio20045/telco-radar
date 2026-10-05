# Kommentarwissen 02-report-rest

Stand: Commit aaa8b0d, 23 Dateien, 1125 Kommentarzeilen.

## Übernahmen in Code
- `src/telco_radar/report/bilder.py`: Konstante `_MIND_BYTES_BILD` ersetzt `2_000` in `_hole_bild` (Download-Funktion) – unter 2000 Byte ist es ein Zählpixel oder kaputter Platzhalter; Kommentar zu `_MUELL` um 2 Zeilen gekürzt (Riesendatei-Grenze 470, jetzt 469).
- `src/telco_radar/report/effektivpreis.py`: Konstante `DROSSEL_UNBRAUCHBAR_KBIT` ersetzt `1000` im Vergleich `drossel_down < 1000` – unter 1 MBit/s gilt die Drossel als „vorbei“, nicht „langsamer“.
- `src/telco_radar/report/html.py`: Konstante `_CTM_BEZUG_ALTBERICHT` ersetzt `1` im Rückfall von `ctm_bezug` – Berichte vor dem 08.08.2026 tragen das Feld nicht, 1 („Kontext“) erhält die Reihenfolge einer Archivwoche statt 0; Kommentar entfernt.
- `src/telco_radar/report/html.py`: Konstante `_KUERZEN_MIND_ANTEIL` ersetzt `0.6` in der Kürzfunktion (Satzkürzen) – Wortgrenze nur, wenn sie hinter 60 % von `limit` liegt, sonst wäre die Zeile unbrauchbar kurz; Inline-Kommentar entfernt (Datei bleibt bei 2496 ≤ 2497 Zeilen).

## Für docs/betrieb.md
- keine

## Widersprüche
- `src/telco_radar/report/html.py:1623`: Kommentar spricht von „Vier Gewichtsstufen plus Ressortbloecke“; laut Kommentar bei Zeile 1009 sind die Ressortblöcke der Titelseite seit 07.08.2026 entfernt (stehen nur noch auf meldungen.html).

## Wissen je Datei

### `src/telco_radar/report/anbieter_farben.py`
- `STRICH_*`/Strichstärken (Zeile 68): Die eigene Linie (Vodafone) ist dicker, 3 px; Rot ist die Farbe des eigenen Angebots, mit gleicher Stärke läse sich Telekom-Magenta als zweite rote Linie.
- Strichmuster (74–82): genau vier benannte Arten; ab der fünften ist ein Muster nicht mehr erkennbar. „luecke“-Muster nur für die Lücke (sichtbar weniger Substanz).
- Lückenfarbe `#c2bcaf` (134–145): bewusst dritter Neutralton. Der Vorgänger-Entwurf übernahm den alten Händlerton `#8a8479` unrevidiert; mit dem `dataviz`-Validator ΔE 1,6 gegen Telekom unter Deuteranopie (Untergrenze 6,0). `#c2bcaf` ist der hellste Ton, der das Paket über die CVD-Zielschwelle 8,0 hebt (schwierigstes Paar danach GRAU_HAENDLER/LUECKE, ΔE 8,2 protan; Normalsicht-Schwelle 15 nahe). Deshalb trägt die Lücke zusätzlich eigenes Strichmuster und die Marker-Form „kreuz“.
- Unbekannter Anbieter (149): Stil wird nie geraten oder aus dem Namen gerechnet; `stil_fuer()` protokolliert jeden Fall.
- Stiltabelle (166–199): Schlüssel ist der kleingeschriebene Anbietername der Adapter. Marker so vergeben, dass kein Grau die Telekom-Form (Quadrat) trägt (Magenta/Grau zweitschwierigstes Paar, die FORM muss tragen); Kreuz gehört allein der Lücke. Zweitmarke congstar: Linie Schwarz, Marker Gelb mit schwarzem Rand (Gelb allein unsichtbar auf Papier). Service-Provider grau gepunktet (fremde Netze, keine eigene Marke). Händler grau durchgezogen, nur durch Markerform unterschieden; Saturn kam beim Rendern gegen den Bestand dazu (`anbieter_typ: handel` in `geraete_db.json`, wie Medimax), vorher stand es als Lücke da.
- Platzhalter im Stylesheet (257): fehlt er in `templates/style.css`, wurde ohne Anbieterfarben gerendert – sonst erst am Screenshot („alles grau“) sichtbar.

### `src/telco_radar/report/archiv_dossier.py`
- BM25-Konstanten (56): k1 = Gewicht von Mehrfachnennungen, b = Strafe für lange Dokumente; übliche Werte, wenig Einfluss, da Einträge kurz und ähnlich lang.
- Schwelle „unbeantwortet“ (62): an echten Fragen gegen das Archiv gemessen; Frage mit passendem seltenem Begriff liegt deutlich darüber, Frage ohne Bezug bleibt bei 0.
- Belegzahl (67): mehr als die Konstante wäre wieder eine Trefferliste statt einer Antwort.
- Stoppwörter (73): würden bei kurzen Einträgen die Rangfolge dominieren.
- Sortierung (308): absteigend nach Score, bei Gleichstand jüngere Meldung zuerst.

### `src/telco_radar/report/bilder.py`
- `_MAX_BYTES` (49): Rohdaten bis 6 MB, verkleinert wird danach.
- Parallelität (59): je Meldung bis zu drei Abrufe (Artikelseite + zwei Bilder); 12 gleichzeitig halten die Sammelzeit bei ~190 Meldungen bei etwa einer Minute, ohne eine Domain unter Dauerfeuer zu setzen.
- Zielbreiten (65–72): Aufmacher bei 1440 px rund 620 px breit, Retina 1240 px. Listenbild 800 statt 700: Rang-60-Meldung als Ressortaufmacher rund 380 px, Retina 760 – bei 700 wären Ressortaufmacher wieder hochskaliert.
- Schwellen (75–81): ab „groß genug“ lohnt der Abruf der Artikelseite nicht mehr (Feed-Bild reicht); darunter ist ein Bild als Bild wertlos (immer hochskaliert), lieber Textsatz. Mindestmaße = Abnahmekriterium 3.
- `_MUELL` (97–103): „share-image“ und „default-image“ standen bis 06.08.2026 in der Müllliste – Denkfehler, `og:image` IST das Share-Bild und mehrere CMS nennen die Datei so. Seit die Größe gemessen wird (1200x630 = Artikelbild, 60x60-Logo fällt durch `_MIND_BREITE`) braucht es den Verdacht nicht.
- Kopfbereich-Abruf (127): og:image steht im `<head>`, Artikelseiten sind teils mehrere MB groß.
- `_MIND_BYTES_BILD` (150): Zählpixel/kaputter Platzhalter.
- `ist_leer` (172–178): an den 15 Promo-Screenshots vom 07.08.2026 gemessen: telekom-deutschland.jpg Standardabweichung exakt 0,00, nächstflauer (otelo.jpg, dunkle Seite) 38,67 – kein Grenzfall, Schwelle unkritisch. Dateigröße ginge auch (6 KB gegen 58–114 KB), hängt aber an der JPEG-Qualität.
- Bildmodi (204, 240): Palette/Graustufe/CMYK bzw. PNG mit Alpha werden umgewandelt.
- `noqa BLE001`-Kommentare (168, 227, 291, 369, 411): ein kaputtes Bild kippt keinen Lauf.
- Altbild-Entfernung (305): ein Bild aus früherem Lauf muss vor dem neuen Versuch weg, sonst überlebt eine Meldung mit altem Dateinamen, auf den `raeume_auf()` beim nächsten Mal löscht – so entstanden am 06.08.2026 vier Meldungen mit `image`, aber ohne `image_w`.
- Cache (321): Kandidat aus früherem Lauf nicht erneut abrufen; Dateiname hängt an URL und Zielbreite.

### `src/telco_radar/report/diff_bilder.py`
- Zielbreite 800 (53): größte Position der Seite ist die Radar-Karte, bei 1440 px rund 380 px, Retina 760; 800 deckt es ab, ohne das Repo aufzublähen.
- Parallelität (57): Bestand Größenordnung 100, jeder Eintrag bis zu zwei Abrufe.
- Fehlversuch-Frist (61): danach darf eine Seite erneut gefragt werden, Redaktionssysteme bekommen `og:image` nachträglich.
- Reihenfolge (165): das Bild des Wochenberichts kostet kein Netz, immer zuerst.
- Aufräumen (210): nicht mehr zum Bestand gehörende Bilder fliegen aus Index UND Ordner, sonst wächst der Ordner mit jedem je gesehenen Beispiel.
- `noqa` (201): ein Bild kippt keinen Lauf.

### `src/telco_radar/report/differentiation.py`
- Ausschlüsse (28): Netz/Infrastruktur, B2B/Enterprise, Konzernfinanzen sind hart ausgeschlossen; Nutzer will Endkunden-Differenzierung, keinen 5G-/Broadband-Ausbau.
- Sortierung (745): relevanteste zuerst, Aktualität als Tiebreak, damit ein starker Move (z. B. Perplexity-Bundle, 5/5) auch nach Wochen in der gedeckelten Anzeige bleibt.

### `src/telco_radar/report/differenzierung_bericht.py`
- H2-Überschriften (36): vom Redakteur geschrieben, `analyze/differentiation_editor.validate_briefing` erzwingt sie; Änderung an beiden Stellen zugleich („ein Schalter, kein Paar“, wie beim Wochen-Editor).
- Ausschluss (43): aus einem alten Bericht wird eine Quellenliste nicht übernommen, die jede Karte der Seite ein zweites Mal aufführt.

### `src/telco_radar/report/differenzierung_view.py`
- Neu-Frist (77): zehn Tage, weil die Pipeline zweimal die Woche läuft – ein Fund bleibt über mindestens zwei Ausgaben sichtbar.
- Kartenzahl (82): drei, seit Karten ein Bild tragen und volle Breite haben; sechs Bildkarten wären wieder eine Kachelwand.
- Gewichtung je Hebel (85): Aufmacher, genau eine Reihe Karten, dann Zeilen. Mit fünf Karten war die Seite 15 100 px hoch; Bildkarten sind dreimal so hoch wie das frühere Textkärtchen.
- Sichtbar am Stück (91): größter Hebel hatte am 08.08.2026 17 Beispiele, als Kärtchen zwei Bildschirme hoch.
- Hebel-Erklärung (96): Quelle ist bewusst `DIFF_THEMES`; eine zweite Pflegestelle sagt nach dem dritten Hebel etwas anderes als die Klassifikation.
- Abkürzungsliste (105, 154): ohne sie endete „AT&T Guarantee … rund 50 Mio. Kunden ausgeweitet.“ nach „50 Mio.“ – drei von 51 Bestandssätzen. Einzelbuchstaben/Versalien sind Initialen („z.B.“, „U.S.“), kein Satzende.
- Rat vor Kürzen (191): erst den Rat streichen, dann kürzen – steht der Rat im ersten Satz, nähme die umgekehrte Reihenfolge den Befund mit.
- Presse-Zweig (198): verifiziert nicht nach, der Fund IST die Prüfung.
- Mehrfach-Absender (253): auf einer Kachel unlesbar, dort steht der erste und die Zahl der übrigen.
- Ohne Aufmacher (366): Karten rücken eine Reihe hoch, sechs statt fünf Karten, keine Lücke.
- Reihenfolge der Schritte (422): Etiketten, Radar-Karten, dann Gewichtung (die muss wissen, was oben schon groß steht).
- Ruhige Woche (434): Seite nicht „enthaupten“, oben die zuletzt nachgeprüften Beispiele, die Überschrift sagt es. Hebel ohne Beispiel steht nicht auf der Seite (451): „Noch keine bestätigten Beispiele“ war zwölfmal derselbe leere Kasten.

### `src/telco_radar/report/effektivpreis.py`
- Nenner (50): gemeinsamer Nenner jedes Vergleichs, siehe Modul-Docstring.
- Flag `gut` (60): True gut, False schlecht, None neutral.
- Drossel (104): unter 1 MBit/s ist die Verbindung für die meisten Anwendungen unbrauchbar – Unterschied zwischen „langsamer“ und „vorbei“, gehört neben den Preis (jetzt `DROSSEL_UNBRAUCHBAR_KBIT`).
- Mindestlaufzeit (123): S-Q4, Wort „Mindestlaufzeit“ statt „Bindung“ – die Seite rechnet über 24 Monate (Horizont), „N Monate Bindung“ wäre von derselben Zahl nicht zu unterscheiden; Wort steht auch im Abschnitt „Was diese Zahlen nicht können“.
- Lücken (158): fehlende Komponente wird als LÜCKE vermerkt, nicht als 0 – „nicht bekannt“ ≠ „kostenlos“.
- Abschnittstrenner (189): Fair-Value-Linie der Positionskarte.

### `src/telco_radar/report/folien.py`
- Budgets (44–54): aus DESIGN_SPEC.md Abschnitt 11 (Inhaltsbudgets): Cover-Titel 2 Zeilen bei 120 px, Kicker UPPERCASE eine Zeile, Content-Headline 60 px höchstens 2 Zeilen, Listenpunkt eine Zeile, „Was passiert ist“ drei Punkte, Fließtext/Lede je Block; mehr passt nicht auf eine Folie.
- „Was das für uns heißt“ (182): aus dem geprüften CTM-Satz (gegen Originaltext geprüft, `analyze/faithfulness.py`), sonst `why_it_matters`; nichts erfunden, gibt es beides nicht, bleibt die Folie kurz.
- Überlauf (334): `kuerze()` schließt ihn aus, aber Vertrauen ist keine Zusicherung – lieber hart abbrechen als eine im Termin unten herauslaufende Folie ausliefern.
- Folienstruktur (342–390): 1 Cover, 2 Was passiert ist, 3 Was das für uns heißt, 4 Quellen (Pflicht). Rest Abschnittstrenner.

### `src/telco_radar/report/fruehwarnung.py`
- Belege je Indikator (43): höchstens zwei; mehr macht aus dem Board eine zweite Meldungsliste.
- Marke (68): im Absenderfeld ODER im Text; Fachpressemeldungen über die Telekom tragen sie oft nur im Titel.
- Zustand der Frage (167): stärkster ihrer Indikatoren.
- Sortierung (178): aktive Fragen zuerst, ruhende zuletzt, aber ALLE bleiben stehen – eine Frage ohne Meldungen seit Wochen ist beantwortet, das soll man sehen.

### `src/telco_radar/report/html.py`
- Quellen entfernt (63): aus der Konfiguration entfernte Quellen verschmutzen historische Seiten nicht; Rohberichte bleiben für Prüfbarkeit, veraltete Highlights/Prosa werden beim Rendern unterdrückt.
- Autoescape (140): `"j2"` MUSS in der Endungsliste stehen, `select_autoescape()` sieht nur die letzte Endung, alle Vorlagen heißen `*.html.j2`; mit `["html"]` allein war Escaping überall aus (aufgefallen 04.08.2026, „Chips & Modems“ als rohes `&`). Ernst: Überschriften fremder Newsrooms/Feeds (h.de_title, h.url), rund 130 Absender. Vier absichtliche HTML-Stellen (briefing_html, diff_report_html, promo_report_html, explorer_json) tragen `| safe`.
- Eurofassung (159): eine für die ganze Seite; früher `'%.2f'|format(x)|replace('.', ',')` an einem Dutzend Stellen, ohne Tausenderpunkt („1794,76“ statt „1.794,76 EUR“).
- Anker/Dateiname (226): aus demselben Titel dasselbe; Rechnung steht in `textwerkzeug.py`.
- Berichtsdatum (312): S3c (Diff-Prüfung 21.09.2026): Datum steht im Stamm des Dateinamens (regex-geprüft), der .md-Fallback liest es genauso. Gültiges JSON ohne `date` (Rest eines abgebrochenen Schreibvorgangs) warf vorher die Geräteseite in den Notzustand und brach das Rendering am Archiv ab (`archive` liest `r["date"]` ungefangen).
- Branchen-Platzhalter im Betreiberfeld (369): „kein spezifischer Betreiber“/„Branche“ ist kein Absender, dann steht die verantwortende Quelle.
- Volle Überschrift/Ressort je Meldung (379, 382): Meldungsseite zeigt alle, Zuordnung nur an EINER Stelle.
- CTM-Linse (386): Altberichte vor 08.08.2026 ohne Feld erhalten 1 (`_CTM_BEZUG_ALTBERICHT`).
- Sortierschlüssel (395): wie Titelseite (`_rangschluessel`, Strategie E6, 27.08.2026): Priorität führt, CTM-Bezug bricht nur Gleichstand. Bis 27.08.2026 führte CTM-Bezug (Eingriff 08.08.2026, der „OpenAI macht ChatGPT gratis unbegrenzt“ über die Telekom-Flat für 34,95 Euro stellen sollte); das wendete sich am 27.08.2026 gegen den Leser, Begründung bei `_rangschluessel`.
- Ressorts (491–511): Zeitung hat Ressorts VOR der Nachrichtenlage; Zuordnung aus der `category` des Analysten, keine zweite Klassifizierung, kein LLM-Aufruf. Zwei Kategorien je Ressort Absicht („Produktlaunch“ + „Tarif/Pricing“ = „was kann ich kaufen und was kostet es“; ein Ressort mit fünf Meldungen ist keins). Einzige Ausnahme Satellit/NTN: sonst hätte „Netz/Technologie“ ein Viertel der Ausgabe (46 von 193 am 06.08.2026, darin 28 Satellitenmeldungen), ein Sammelbecken.
- Namenswörter (547): ohne die Liste fänden „T-Mobile US“ und „Mobile World Live“ denselben Namen.
- `_MAX_JE_ABSENDER` (585): Absenderdeckel oberhalb der Falz.
- `_WICHTIG_ZEILEN` (588): Digest-Spalte wird in zwei Schritten gefüllt; zwei Literale 7 liefen auseinander (acht oder sechs Zeilen).
- Roter Faden (621–640): Antonio 07.08.2026: „der rote Faden fehlt mir noch überall“. Titelseite führte mit anderer Geschichte als der Wochenbericht, weil beide unabhängig sortierten. Der Bericht beginnt mit „Auf einen Blick“ (drei Sätze); Aufmacher und zweite Reihe belegen diese Sätze in deren Reihenfolge – nachprüfbar. `_FADEN_KANDIDATEN` = 4: Aufmacher verlangt Bild ≥ 800 px; am 07.08.2026 führte der Bericht mit SpaceX, beste SpaceX-Meldung hatte 720 px, Titelseite führte mit der Telekom.
- Absender-Gruppen/Durchgänge (797–826): drei Durchgänge: 1 Bildanspruch UND Absenderdeckel, 2 nur Absenderdeckel (Vielfalt schlägt Bebilderung), 3 ohne beides (Position bleibt nie leer). `streng` lässt nur den ersten zu: wer aus Fadenkandidaten wählt, geht lieber leer aus als den Bildanspruch aufzugeben.
- Faden zuerst (895–913): seit 15.08.2026 schlägt der RANG den Faden: nur unter Meldungen, die den besten noch freien Rangschlüssel dieser Bildstufe erreichen; Faden wählt nur unter Gleichrangigen. Vorher Wortüberschneidung allein – an Ausgabe 14.08.2026 messbar falsch: Aufmacher „T-Mobile wirbt mit Studienstart-Ratgeber“ (Kontext, Priorität 2), während „T-Mobile verschenkt Pixel 11 Pro XL“ (Übertragbar, Priorität 5) als Textzeile stand. Antonio: „die wichtigsten artikel sollen auch an erster reihe stehen.“
- Zusammenfassung ungekürzt (933): bereits ein bis zwei Sätze, ein Schnitt machte einen Halbsatz.
- Latte je Platz neu (937): einmal vorab gerechnet veraltet sie nach dem ersten Zugriff, die Reihe bliebe halb leer.
- Dritte Reihe (956–986): seit 15.08.2026 wieder VOR der Digest-Spalte, nachdem sich die Spalte zugesagtes (K2, 09.08.2026) genommen hat. Stufen: 1 `wichtig` nimmt „Direkt für uns“, 2 `vier` füllt Bildkacheln aus der Rangfolge, 3 `wichtig` füllt auf, `vier` notfalls ohne Bild. Warum zurückgedreht: Spalte zuerst hieß, die Hauptspalte bekam die schwächeren Meldungen (15.08.2026: vier Kacheln Priorität 2, fünf Textzeilen Priorität 3). Warum Reservierung: 08.08.2026 räumten Bildkacheln jede Meldung mit direktem Portfoliobezug ab, „Was wichtig ist“ führte mit zwei BREKO-Stellungnahmen (Stufe 2). Kurzpfad als Ersatz abgelehnt: er nimmt nur geprüfte Folgerungssätze, die regelmäßig ausfallen (14.08.2026 verwarf der Prüflauf alle neun Sätze); über 17 Archivausgaben ist der Kurzpfad in 16 leer. Keine Reservierung vor Aufmacher/zweiter Reihe.
- `streng` dritte Reihe (996): sie ist BILDposition; ohne `streng` griffe der Rückfall auf bildlose Meldungen und nähme sie der Spalte weg.
- Ressortblöcke entfernt (1009): bis 07.08.2026 sechs Ressortblöcke (je Aufmacher + vier Zeilen) auf der Titelseite; dieselbe Gliederung steht vollständig auf der Meldungsseite (`_nach_ressort`).
- Messgrößen (1022, 1031): Zahl der Führungssätze oberhalb der Falz und Zahl der Schlagzeilen oberhalb der Falz werden in `tests/test_seiten_zahlen.py` gegen die gerenderten Elemente gehalten.
- Ressortaufmacher (1059): braucht großes Bild (≥ 500 px), gesucht unter den ersten fünf, damit Dringlichkeit nicht der Bebilderung geopfert wird; Begleiter (1065): bebilderte zuerst, sonst wäre die Kachel ein Inhaltsverzeichnis.
- Gekürzter Wert (1108): endet auf „…“, taugt nicht als Überschrift.
- `_SATZENDE` (1126): Punkt nur Satzende mit Buchstabe/schließender Klammer davor und Großbuchstabe dahinter; ohne erste Bedingung war „AST SpaceMobile hat am 5. August …“ nach vier Wörtern zu Ende (06.08.2026, Anriss der zweiten Reihe). Zweite Alternative: freistehender Punkt („ . “) ist immer Satzende; sonst verlor die Promo-Übersicht ihren Schnitt (Wochentext aus Angebotstiteln, nächster beginnt mit Ziffer, „1&1 Mobilfunk“).
- Kürzen (1165): Wortgrenze nur ab 60 % von `limit` (`_KUERZEN_MIND_ANTEIL`).
- `_briefing_lead()` entfernt (1242): stand bis 07.08.2026 (erster Satz „Was wichtig ist“, 360 Zeichen); zusammen mit seiner Anzeige entfernt – `briefing_lead` wurde schon einmal ein halbes Jahr unbemerkt berechnet, ohne dass eine Vorlage es las.
- Satzende vor Kleinschreibung (1250): `_SATZENDE` verlangt Großbuchstaben; Promo-Marken (winSIM, congstar, otelo, simplytel, mobilcom-debitel) schreiben sich klein. Am Promo-Bericht vom 07.08.2026 übersah die Regel das erste Satzende („… Eskalationsstufe erreicht. winSIM senkt …“) und lieferte 280 Zeichen mit „…“ als einzigen Vorspann.
- Abschnittstrenner/Themenradar (1317): Schlagwortthemen über Titel und Zusammenfassung.
- Suchindex (1357): Aufbau in `report/suchindex.py`; speist seit 08.08.2026 auch Promo-Aktionen, jeder Eintrag trägt sein Bild; Index ist die einzige Datei, die keine Seite ist (Browser liest sie), eine 1400-Zeilen-Datei ist falscher Ort für ein Datenformat.
- Foliensatz (1388): je Ausgabe neben dem Bericht, nicht in der Navigation – Datei zum Mitnehmen.
- Bildordner (1394–1412): `site/images/` SPIEGELT `data/state/report_images/` und `diff_images` (seit 08.08.2026). Bis 06.08.2026 wurde nur kopiert, nie gelöscht (`raeume_auf()` beschnitt den Zwischenspeicher); bei 9 Bildern je Lauf unauffällig, bei rund 130 wäre das Repo in einem Jahr um mehrere GB gewachsen. Zwei Speicher, weil `raeume_auf()` nur die Bilder der letzten vier Ausgaben behält, Differenzierungs-Beispiele aber Monate leben; Dateinamen sind Hashes der Bild-URL, Kollision wäre dieselbe Datei.
- Bildabgleich (1431): Berichtsdatei behält `image`-Verweise für immer, Bildordner nicht; ohne Abgleich leere Bildkästen in Archivwochen; beide Speicher, weil ein Differenzierungs-Beispiel sein Bild aus dem Bericht geerbt haben kann.
- Themen früh laden (1448): Titelseite verweist unter der dritten Reihe darauf; Seiten werden nach den Promos gerendert, ein Thema darf passende Aktionen zeigen.
- Entfernte Globals (1464): `ausgabe_datum`/`ausgabe_quellen` bis 07.08.2026 für die Datumszeile des Zeitungskopfs; Zeile weg (Antonio: „das ist unnötig“), also auch die Werte.
- Gerätedaten früh (1469): entscheiden über einen Navigationseintrag in `base.html.j2` (jede Seite); try/except nur um das Aufbereiten, nie das Rendern.
- `heute` Gerätealterung (1482): Berichtstag (radar.yml, Mi/Fr), nicht die Uhr; `geraete.yml` rendert täglich und fasst Berichte nicht an. Alterung der Bündel gegen den SPÄTEREN von Berichtstag und `updated` des Bündel-Stores (Prüfer-Befund 20.09.2026: Bericht 16.09., Stand 20.09., Telekom-Bündel vom 15.09. blieben frisch). `reports[0]` ist der jüngste Bericht; ohne Berichte bleibt `heute` leer (Kompatibilitätsmodus, nichts altert, `ist_frisch`); `.get` ist zweite Wand (S3c).
- Wettbewerbs-Radar (1508): RAD-1, 08.09.2026, AUFTRAG_GERAETESEITE.md §2b; rechnet hier wegen Navigation und Fußlink; Veröffentlichungsschwelle: Seite ohne vergleichbare Zeile kommt nicht in die Navigation. O3 (1518): Portfolio-Abschnitte (Lifecycle, Wochenkarte) als Radar-Sektionen.
- Rechtstexte früh (1543, 1551): Fußzeile steht auf JEDER Seite; Schwelle „Impressum vollständig“ entscheidet über Verlinkung des Anmeldeformulars; Newsletter braucht BEIDE Pflichtseiten vollständig, sonst Formular gebaut aber nicht verlinkt.
- Übersetzungen (1557): Zuordnung muss vor der ersten Woche stehen (Titelseite, Meldungsseite, jede Archivwoche lesen `h["uebersetzung"]`); nicht gefiltert, Speicher nie beschnitten, Archivwochen behalten ihren Link (Premortem 6, tote Archivlinks).
- Wochenvorlage (1598): eine Vorlage für aktuelle Woche und alle Archivwochen; bis 06.08.2026 zwei (uebersicht.html.j2 + report.html.j2) mit zwei Ladevorgängen für eine Frage.
- Wochenstand (1604): je Woche, woraus Wettbewerbsseite und Suchindex bauen; fällt ohnehin an, doppelt rechnen wäre der teuerste Teil (14 Wochen × `_flatten()`).
- Roter Link (1611): entsteht beim Rendern, nicht in der Berichtsdatei – Übersetzung kann nach der Ausgabe entstehen (Stufe hat eine Frist), Bericht wird nicht rückwirkend umgeschrieben.
- Kurzpfad-Reihenfolge (1629): VOR der Titelseite gewählt, damit sie ihn aussparen kann; seit 09.08.2026 in derselben Spalte, sonst steht dieselbe Meldung als Kurzpfad-Zeile 1 und erste Zeile „Was wichtig ist“; „doppelt gemoppelt“ hat Antonio am 07.08.2026 an den Ressortblöcken kassiert.
- Übernommene Redaktion (1648, 1667, 1727, 1853): E3B: trägt wörtlich dieselben Wettbewerber-Profile wie der Ursprung; Ausnahme, sonst stünde „dieselbe Woche“ zweimal im Themenverlauf. Highlights brauchen sie nicht (Chronik schlüsselt auf URL, wahres früheres Datum). Eine Runde ohne bewertete Meldung zeigt die letzte gültige Redaktion (`pipeline.py`), sonst None. Coverfolie zeigt Datum des Inhalts, Datei liegt unter dem Datum DIESER Ausgabe (Link am Berichtsfuß). E3B-R2: Hinweis nötig, sonst „Ausgabe vom 4. September“ über Meldungen vom 28.08.
- `_stats()` (1674): teuer, nur aktuelle Woche; bis 06.08.2026 lief es für jede Archivwoche und wurde verworfen.
- Zwei-Minuten-Pfad (1681): „Lesezeit ca. 16 Minuten“ ist das Ende der Nutzung; jede Zeile mit Konsequenz und Quellenlink, nur aus geprüften Folgerungssätzen; leer = Kasten fehlt (Befund, keine Lücke).
- Themenseiten/Archivwoche (1695–1713): nur die aktuelle Ausgabe verweist auf laufende Themen (`is_latest`). Frühwarn-Board braucht das ARCHIV, wird nach der Schleife nachgereicht (Startseite zweimal geschrieben, Millisekunden; Alternative 14 × `_flatten()`). Archivwoche trägt Meldungen selbst (kein meldungen.html; Suche verlinkt mit `?q=` hierher); `is_latest=False` auch für die neueste Woche, `reports/<datum>.html` ist immer Archiv-URL.
- Foliensatz-Fehler (1719): Überlauf wirft, kostet aber keine Ausgabe, daher protokolliert statt geworfen (`noqa` 1741).
- Differenzierung (1767–1833): zwei Speicher gemischt (`differentiation_db.json` = rotierender Web-Sweep; `differentiation.jsonl` = Kurator über den Presse-Crawl); bis 08.08.2026 nur der erste gerendert, der Kurator lief jede Woche und landete nirgends. Bericht wird ZERLEGT (Lage in Seitenkopf, Muster neben Marktbild, Einordnung je Hebel); nur alte Gliederung (bis 08.08.2026 „Konkrete Entwicklungen“ + „Quellenbasis“) landet als Block am Seitenende. Bilder aus dem Index (`diff_bilder.py`), `render_site()` fasst nie das Netz an; sie gehen IN `aufbereiten`, da die Gewichtung am Bild hängt. Seitenkopf: bis 08.08.2026 nur „Stand 7. August 2026“ im besten Platz (`seit.py`). Zeitachse aus `first_seen`, kein neuer Speicher; Gegenfrage nur gegen GEPFLEGTE Liste (`luecken.py`).
- Meldungen (1842): Belegebene an einem Ort, löst Explorer, suche.html, archive.html ab; Suche clientseitig (`app.js` lädt `search_index.json`). Gruppierung nach Ressort (1858): vorher 193 identische Zeilen.
- Promo (1868–1920): eigener Anwendungsfall (`promo_pipeline.py`, `config/promo_sources.yaml`, `data/state/promo_db.json`); fehlt der State, leere Übersicht. Kampagnenbilder (`promo_images/<hash>-1280.jpg`) werden nach `site/promo/images/` gespiegelt. Bis 07.08.2026 Screenshot je MARKE plus `ist_leer`-Prüfung; heute prüft `promo_bilder.py` beim Ablegen (Mindestbreite + `ist_leer`); hier nur noch Verweis entfernen, wenn Bilddatei fehlt. Ordner spiegelt, sonst behielte eine ausgelaufene Aktion ihr Bild.
- Themenseiten (1968–1987): Ordner spiegelt den Themenspeicher; beendetes Thema verliert Seite von selbst. Roter Link auch hier, Karten aus dem Themenspeicher statt `_flatten()` (Positivlisten-Falle wie `_items_payload`).
- Übersetzungsseiten (2004–2015): NICHT gespiegelt, Übersetzung gehört zur Meldung im Archiv; HTML entsteht bei JEDEM Rendern aus dem JSONL (Speicher ist das JSONL, nicht der Ordner), sonst schriebe eine Vorlagenänderung dreitausend Dateien in die git-Historie (Premortem 7).
- Suchindex/Dossier-Seite (2033): steht unten, weil der Index alle drei Bereiche trägt und Promo-Aktionen im Block davor entstehen; bis 08.08.2026 fehlte der dritte Bereich, Suche führte auf eine Seite mit Ressorts vor den Treffern (Antonio: „Ich verstehe nicht, warum ich da weitergeleitet werde“).
- Newsletter-Stichwortindex (2056): Trefferzahl-Vorschau („letzten 30 Tage 47 Meldungen“) ist die wirksamste Maßnahme gegen Abo-Müdigkeit; Seite statisch, Signup-Dienst hat die Archive nicht, daher zählt der Browser gegen die Datei, Pipeline schreibt sie bei jedem Lauf. `newsletter/filters.baue_stichwort_index()` ist Erzeuger UND Testgrundlage (Test hält jedes Wort gegen `vorschau()`).
- Anmeldeseite (2086, 2101): die beiden Abschlussseiten sind STATISCH ohne Signup-Dienst (Abmeldelink ist einziger Abmeldeweg, Render lässt die Instanz schlafen, sonst Minute Spinner). Zwei UNABHÄNGIGE Bedingungen sperren die Seite, Leser erfährt beide OBEN; Hinweis auf fehlenden Dienst kam bis 12.08.2026 nur aus `app.js`, am Fuß einer 2145 px hohen Seite.
- Wettbewerb (2149–2163): Antonio 08.08.2026: „nicht nur die Meldung dieser Woche, sondern über die Wochen und Monate …“; Seite entsteht komplett beim Rendern aus dem Archiv, kein State, kein LLM, wächst mit jedem Lauf. Differenzierungs-Hebel je Wettbewerber lagen bis 08.08.2026 nach THEMA sortiert eine Seite weiter.
- Lieferzeiten (2177): einzige Frage des Portals ohne Antwort anderswo (keine öffentliche Studie zu Lieferzeiten deutscher Anbieter); entsteht beim Rendern aus dem Speicher von `collect/lieferzeit.py`.
- Tarife (2203): erste Seite aus Pflichtdokumenten nach § 1 TK-TransparenzV statt Meldungen; Koordinaten werden hier gerechnet (kein CDN-JS, Darstellung ohne Browser testbar). `noqa` 2214: fehlende Config kippt keine Seite.
- Geräte-/Preisradar (2227–2262): zwei Seiten aus einem Datensatz (`geraete_db.json`, `geraete_preise.jsonl`), ohne Netz/Modell. NICHT in der Navigation (Veröffentlichungsschwelle), Schwelle beziffert in `tests/test_geraete_seite.py`. try/except nur um Aufbereitung: sonst lässt ein kaputter Eintrag beide Seiten verschwinden, `site/` behält die alte Fassung, und `pruefe_portal.py` meldet „nicht gerendert“ und endet trotzdem mit 0; gescheiterte Aufbereitung = Seite entsteht und SAGT, dass sie nichts zeigen kann. Gesamtexport VOR der Seite (Zeilenzahl/Größe aus geschriebenen Dateien). Export-Menge seit 31.08.2026 der BESTAND aus `aufbereiten` (`geraete_view.bestand_und_belastbar`); vorher eigener `status`-Filter, dann kurz die BELASTBARE Menge – beides falsch: einmal zwei Gebrauchtpreise mit `Zustand = neu`, einmal fehlten die zwei Zeilen des o2-Doppelpreises, auf die der Prüfbericht verweist.
- Export-Kommentare (2266–2337): O4 TCO-Zeilen und fertige Radar-Aufbereitung (Prozentzahlen aus derselben Rechnung wie der Reiter); P3 Modell-Tabelle als Ansichts-Export; `noqa` 2282: gescheiterter Export kostet die Seite nicht, verschwindet aber nicht still; Radar nennt Zeilenzahl/Größe SEINER Datei in der Kopfzeile. E3 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1d): EINE Seite, vier Reiter, eine Berechnung `radar()`. O3 (STRATEGIE_GERAETE_OPTIK §3, 15.09.2026): Bündel-Fragment (Zeilen aller Nicht-Vorgabemodelle, gleiches Makro wie Server-Block) hält die Seite bei ~1,1 MB mit 24 Aufklappern; Fragment am Bestand ~1,2 MB, 404 Zeilen, lädt beim ersten Modellwechsel, liegt unter `site/data/` als Ladegut. E2 (16.09.2026): `vorgabe` ist der ZEITREIHEN-Startzustand; Zeitreihen-Fragment je (Modell × Band) in eigener Datei, Bandwechsel lädt nur diesen Zustand statt 1,8 MB Zeilen; ALLE Paare stehen drin (eine Quelle für den Rückweg, S2-Falle).
- Transparenz (2351–2435): Laufprotokoll und Quellenbestand auf einer Seite („kann ich dem Ding trauen?“). Status „ok“, „empty“, „fail“, „quarantaene“ (`pipeline.py:249ff`); Zusammenfassung nennt den dritten „failed“ – bis 06.08.2026 zählte die Schleife nach „failed“ und fand nie einen (Lauf 05.08.: 6 gescheiterte Quellen, Seite meldete 0). Stillgelegte Quellen zählen nicht als „abgefragt“. Themenfelder (`config/tech_sources.yaml`) eigener Block. Zahl der „bewerteten Meldungen“ = nach Ausfiltern stillgelegter Quellen, NICHT `stats.new`; `stats.bewertete` (E3B, 05.09.2026) ist die Zahl DES LAUFS, auch bei übernommener Redaktion; ältere Berichte kennen es nicht (`None`, alte Rechnung). CTM-Linse erklärt sich nur hier, Sicherheitsskala aus derselben Datei wie der Prompt. Newsletter-Abschnitt: NUR Zahlen, nie Adressen; CI-Test prüft Statistikdatei gegen Adressmuster.
- Weiterleitungen (2475): alte Dateinamen stehen in Lesezeichen/Mails der Fachabteilung, 404 wäre die teuerste Art aufzuräumen. `suche.html` ist seit 08.08.2026 wieder echte Seite (Dossier-Suche); `wettbewerbsradar.html` seit E3 Schritt 3 (17.09.2026) dabei, Radar ist Reiter der Geräteseite (Hash, `app.js`).
- Übrige (Zeile 253, 1357-Trenner, 1379, 1501, 1535, 2501 u. a.): Abschnittstrenner, `noqa`-Marker, Nacherzählungen.

### `src/telco_radar/report/lieferzeit_view.py`
- Messpunkte (21): genug für einen Verlauf, wenig genug für eine Zeile.
- Sprung (77): aus derselben Reihe berechnet, damit die Seite nicht auf ein Feld angewiesen ist, das ein Lauf gesetzt haben muss.

### `src/telco_radar/report/luecken.py`
- Schwelle weißer Fleck (43): ab zwei verschiedenen Wettbewerbern; einer ist Einzelfall, zwei eine Bewegung.
- Datum (56): ohne Datum keine Aussage.
- Weißer Fleck (134): gepflegtes „nein“ gegen mehrere Wettbewerber, nie „offen“. Direktvergleich (142): was der genannte Wettbewerber je Hebel hat.
- Leerzustand (178): solange nichts erfasst ist, sagt die Seite das statt zwölf ungeprüfte weiße Flecken zu behaupten.

### `src/telco_radar/report/newsletter_protokoll.py`
- Gespiegelte Konstante (35): aus `versand.py` gespiegelt, damit die Seite das Versandmodul (lebt im Lauf, nicht im Renderer) nicht importiert; ein Test hält beide gegeneinander (zwei Zahlen = zwei Limits).
- Warnungen (144): die der JÜNGSTEN Ausgabe oben, ältere sind Geschichte (Tabelle).

### `src/telco_radar/report/newsletter_seite.py`
- Dimensionssatz (28): „Leer heißt alles“ ist die Erwartung fast aller Nutzer, aber nicht die der anderen – der Satz ist die Regel selbst, keine Bedienhilfe.
- Zeile 89: Abschnittstrenner „die zwei statischen Seiten“, nichts übernommen.

### `src/telco_radar/report/promo.py`
- Rang (53): Marke ohne gepflegten `rang` hinter jede gepflegte, dort nach Tier und Reichweite; neue Marke verschwindet nicht, drängelt nicht nach vorn.
- Kachelaussage (61–69): harte Aussage (Preis, Datenmenge, Bandbreite, Rabatt) auf der Schriftkachel („20 GB für 6,99 €“). Bis 08.08.2026 stand die MECHANIK („Wechsel- oder Altgeräteprämie“), vier Marken fahren dieselbe, vier identische Kacheln. Abschließende Grenze nötig: ohne sie schnitt „EUR“ aus „1 Euro einmalig“ ein „1 Eur“ (08.08.2026, Otelo-Karte).
- Trennstellen (75–84): Überschrift nur ABTRENNEN, nie mitten im Wort kürzen (Kachel trägt kein „…“, CLAUDE.md §5); Kern endet vor Näherbestimmung („Junge-Leute-Rabatt AUF Magenta Mobil Young 5G Tarife“), erst nach Zeichensetzung (Präposition schwächere Grenze). Länger wirkt die Kachel wie zweiter Absatz.
- Ganze Überschrift (144): taugt nicht als Kachel, steht zwei Zeilen tiefer nochmals; ein AUSSCHNITT hebt hervor.
- Banner (185): Seitenverhältnis 2,2 liegt über 16:9 (1,78) und unter dem flachsten echten Foto im Bestand vom 08.08.2026 (800x419 = 1,91); sonst würden gewöhnliche Querformate beschnitten. Banner (291): 1280x410-Motiv im 16:9-Kasten füllend schnitte die Aussagehälfte ab (simplytel: blaue Fläche, FRITZ!Box am Rand), wird vollständig gezeigt.
- Dublette (262): Motiv gehört derselben Aktion, fällt nicht weg. `kachel` ist Vorauswahl, `_entdoppele_kacheln()` entscheidet im Markenblock (283).
- „motiv“ (297): Bühnenbild der Aktionsseite, nicht das Bild GENAU dieses Angebots (`promo_bilder.zuordnen`); die Karte schreibt das dazu.
- Große Fläche (342–348): bei 1440 px 579 px breit, auf MacBook (2 Geräte-Pixel/CSS-Pixel) 1158 echte Pixel; ein 620-px-Motiv ist unscharf (Antonio, 16.08.2026). Darunter führt die Aktion den Block in der kleinen Fläche.
- Aufmacher zwei Rasterzeilen (350–355): braucht VIER volle Zellen daneben (2 Spalten × 2 Zeilen); mit drei blieb am 27.08.2026 die Zelle unten rechts leer (ALDI TALK, live gemessen); Lücke MITTEN im Raster ist das „kreuz und quer“.
- Schriftkachel (405): Text, in jeder Größe scharf; nur Rasterbild muss die Fläche füllen.
- Nur gecrawlte Quellen (470): `kind: static/js`; dokumentierte Sonderfälle (`kind: skip`, z. B. Deutsche Glasfaser) hätten fälschlich wie geprüft-leere Marke ausgesehen, stehen auf der Quellen-Unterseite.
- Sprungziel (500): Dossier-Treffer „Aktion“ verlinkt hierher; Link in `report/suchindex.py`, Anker hier, sonst springt die Suche ins Leere.
- Reihenfolge Blöcke (520–536): Wettbewerber mit sichtbarem Angebot zuerst, nach Anbieterrang, Vodafone-Referenzkarte zuletzt. Bis 08.08.2026 sortierte der Score der stärksten Aktion – Rangliste der Angebote, nicht des Marktes, hing an einem Lauf (Telekom Platz zehn, JS-Seiten gaben nur zwei Angebote, Otelo mit Freundschaftswerbung vorn). Score ordnet weiter INNERHALB einer Marke (`_sortierschluessel`) und trägt „wichtig“.
- Wahrheitstests (547, 564, 574): Kartenlisten sind Grundlage („jede sichtbare Aktion genau einmal“; Zählung unabhängig von Gruppierung); Zahl der Karten mit Kampagnenbild hängt am Abnahmekriterium (`scripts/pruefe_portal.py`) und wird in `tests/test_promo_seite.py` gegen die Daten gehalten. Erst Motive entdoppeln, dann Kacheln (551, 556): erste Runde kann einer Karte das Bild nehmen, sie wird Schriftkachel und darf die große Fläche wieder tragen.

### `src/telco_radar/report/rechtstexte.py`
- Platzhalter (43): geschweifte Klammern, damit er in gerendertem HTML wie in der Quelle auffällt; bewusst KEINE Jinja-Syntax (Dateien laufen nie durch Jinja, ein Jinja-ähnliches Muster lädt dazu ein).
- Offener Platzhalter (50): Leser soll sehen, dass etwas fehlt, nicht eine zufällig kurze Zeile.
- Überschrift (93): fällt weg, Vorlage setzt `<h1>`, `_md_to_html()` kennt `h1` nicht; Titel steht in SEITEN, zwei Orte wären zwei Titel.
- Zeile 135: Abschnittstrenner „Einwilligung“.

### `src/telco_radar/report/seit.py`
- Zeilenzahl (22): drei, steht neben einer Überschrift und darf nicht neben ihr herunterlaufen.
- Zählbasis (52): auf den ANGEBOTEN, nicht den Karten (`neu` und Status stempelt `prepare_promo_view`, Karte trägt nur Angezeigtes).

### `src/telco_radar/report/suchindex.py`
- Bereiche (34): drei, Reihenfolge = Filterleiste.
- Datum (76): der MELDUNG, nicht der Ausgabe; sonst vier Ereignisse eines Tages, die drei Wochen auseinanderliegen. Fehlt es, trägt der Ausgabetag; ohne Datum fällt der Eintrag aus dem Verlauf.
- Priorität 3 (102): Bibliothek bewertet nicht nach Dringlichkeit, 3 = „beobachten“, hält Beispiele in der Chronik zwischen dringenden und beiläufigen Meldungen.
- `why_it_matters` (169): interne Analystennotiz, gehört nicht in eine vom Browser geladene Datei.
- Sammelbezeichnungen (211): kein Absender, nach dem man sucht.

### `src/telco_radar/report/tarife_view.py`
- Zeichenfläche (55) und Hervorhebung (59): Karte beantwortet „wo stehen WIR“, nicht „wie sieht der Markt aus“.
- P3-E1 (104): zurückgezogener Tarif ist kein Tarif von heute.
- Live-Shop vs. Dokument (130, 165): Hinweis nur, wenn `_bevorzuge_live_shop()` ein Pflichtdokument gleicher Titelzeile zurückgestuft hat; bei beiden Lesarten bleiben Live-Sätze, jeder Dokument-Satz wird Referenz auf dem ERSTEN Live-Satz (zwei Dokument-Versionen alt/neu wären sonst zwei Referenzen auf derselben Zeile).
- Achsen (200): beginnen bei null – abgeschnittene Preisachse macht kleine Unterschiede riesig, keine Gestaltungsfrage. Gerade (217): nur zeichnen, wenn sie im Bild bleibt.
- Kopfdatum (283): Datum des NEUESTEN Tarifsatzes, nicht des letzten Wochenberichts (QA-Befund F3, Abnahmekriterium G7); am 04.09.2026 stand „Stand 2026-09-02“ über 44 Sätzen mit `abgerufen_am: 2026-09-04`. `heute` ist Rückfall ohne Abrufdatum.
- Bilanz (299): S-Q2, „in der Karte“ = bekanntes begrenztes Volumen UND rechenbarer Preis; „ohne Anschlusspreis“ zählt genau diese Lücke. Cashback-Lücke zählt NICHT (trägt JEDES Produktinformationsblatt, 52 von 52 – Eigenschaft der Dokumentenart), steht als Satz im Hinweis.

### `src/telco_radar/report/thema.py`
- Mindestbreite (26–35): gemessen an der gerenderten Seite bei 1440 px: Aufmacher 502 px, zweite Reihe 552–579 px; darunter hochskaliert (Befund 06.08.2026, Abnahmekriterium 6, `scripts/pruefe_portal.py`). Kleiner als die 800 px der Titelseite mit Absicht: Themenseite hat nur Meldungen eines Ereignisses, schmalere Positionen; Aufmacher ohne Bild ist schlechter als einer mit gerade tragendem Bild.
- Später Import (101): `report/html.py` baut diese Ansicht, Modulimport wäre ein Ring; `_schlagzeile()` ist die eine Stelle für die Überschrift (Regel 3 des Designbriefs).
- Quelle (111): Rückfall auf Domain wie `source_label` in `_flatten()`, sonst „Bild:“ ohne Namen.
- Aufmacher (123): breitestes Bild führt nur, wenn es die Position trägt, sonst die dringendste Meldung (Speicher bereits nach Dringlichkeit sortiert). Zweite Reihe (130): tragfähiges Bild zuerst, sonst zweimal nur Text neben dem Aufmacher.

### `src/telco_radar/report/verlauf.py`
- Monate (33): sechs = halbes Jahr, passt als Balkenreihe.
- Belastbarkeit (37): unter der Mindestzahl Aufnahmen im Monat ist der Anteil Rauschen; Monat steht im Verlauf, zählt nicht für „wächst/kippt“.
- Bewegung (42): Mindestverschiebung in Prozentpunkten, darunter dieselbe Lage in anderer Rundung.
- Ein Monat (81): kein Verlauf, lieber nichts als Linie mit einem Punkt.
- Vergleich (115): letzter belastbarer Monat gegen Durchschnitt der belastbaren davor; nur gegen den Vormonat macht jede Schwankung zur Nachricht.
- Vorbehalt (155): Seite nennt ihn statt ihn zu verschweigen.

### `src/telco_radar/report/wettbewerb.py`
- Aktionen je Wettbewerber (49): Rest vollständig auf der Promo-Übersicht.
- Themenverlauf (52): vier Wochen/Profile zeigen die Verschiebung („Ende Juli Router und Streaming, jetzt Glasfaser und Joyn“) ohne halbe Seite Etiketten.
- `_OFFEN_JE_MONAT` (57): Antonio 08.08.2026: „mach Wettbewerb das Layout besser, sodass man nicht so viel runterscrollen muss.“ Monat mit 30 Meldungen war 2600 px hoch, Seite mit drei Wettbewerbern 6777 px (sieben Bildschirmhöhen bis zum zweiten Wettbewerber). Zwölf Meldungen = sechs Zeilen in zwei Spalten; Rest einen Klick weiter, nichts fällt weg.
- Notiz ohne Ratschlag (107): Regel und Werkzeug in `textwerkzeug`; dieselbe Frage auf der Differenzierungs-Seite mit anderer Antwort.
- `tag` (194): Zeilenmarke („7.8.“); bis 08.08.2026 nur Tageszahl, bei Wiederholung ausgeblendet – ging bei EINER Spalte; in zwei Spalten zerreißt der Umbruch Gruppen (Meldungen ohne Datum oben in Spalte zwei), daher trägt jede Zeile ihr Datum.
- Offener Monat (238): zeigt Anfang, Rest bereit.
- Absendername am ANFANG (261): wie `_gehoert_dazu`; sonst zog Alias „Telekom“ auch „A1 Telekom Austria“ und „Turk Telekom“ ins Profil.
- `what` (281): Feld der Differenzierungs-Bibliothek („was dieser Anbieter tut“); `headline`/`summary` gibt es dort NICHT, ohne Zuordnung blieb die Beispielzeile leer, Hebel stand als nackte Zahl.
- Reihenfolge Meldung vor Move (340): Meldung trägt die deutsche Analysten-Schlagzeile, der Move die Originalüberschrift („DT has ‚not yet decided‘ on EU gigafactory bid“); für Leser ohne Technikhintergrund der Unterschied; Datum unberührt.
- Fehler (387): des JEWEILS letzten Laufs; Teilausfall darf nicht wie ruhiger Wettbewerber aussehen.
- Verlauf (405): neueste Woche zuerst, nur so weit zurück, wie eine Entwicklung ablesbar ist; oberste Zeile IST der aktuelle Stand, ein zweites Mal als Etiketten wäre doppelt. Chronik-Beginn (434): Datum der ÄLTESTEN Aufnahme, nicht Beobachtungsbeginn des Projekts.
- Offene Flanken (446): Hebel, die ein ANDERER Fokus-Wettbewerber zieht, dieser nicht; erst im Nachgang berechenbar; nur gegen Fokus-Wettbewerber, nicht gegen den Weltbestand („Telkomsel hat das auch“ ist im deutschen Markt keine Flanke).
- Seitenkopf (473): Ausgabetag der jüngsten Woche; „seit …“ und Zahl der Ausgaben wurden entfernt (jede Wettbewerber-Kopfzeile sagt es genauer, „56 Meldungen seit 16. Juli 2026“); was keine Vorlage liest, wird nicht berechnet. Ohne Promo-Konfiguration (479, `render_site()` ohne `cfg`) fehlt die Aktionsspalte statt „keine Aktion bestaetigt“ zu behaupten.

Nicht übernommene Konstanten (schon benannt oder nur Nacherzählung): alle Zahlen/Schwellen in `bilder`, `diff_bilder`, `differenzierung_view`, `fruehwarnung`, `luecken`, `promo`, `seit`, `thema`, `verlauf`, `wettbewerb` tragen bereits einen Namen.
