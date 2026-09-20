# Geräteseite v3 - Strategie (17.09.2026)

Grundlage: die sechs Befunddateien unter
`outputs/strategie-geraete-v3-2026-09-17/befunde/` — alle vorhanden. Jede Zahl
stammt aus einer davon (Quelle in Klammern), nichts ist vom Repo-Code
geschlossen. Unverändert: kein Commit, nichts unter `data/state` anfassen,
neue Zahlen in `tests/test_seiten_zahlen.py`, Screenshots als harte Abnahme.

## 1. Antonios Forderungen (die acht Punkte, wörtlich wie oben)

1. **DESIGN**: "immer noch ziemlich beschissen", "unintuitiv, nicht schön, macht keinen Spaß", "alles so unruhig, keine richtige Struktur", "super viele Erklärungen, die mir auf den Sack gehen", "Ich sehe hier nur Text. Ich will keinen verfickten Text sehen."
2. **VERGLEICH, Preis-Klick**: Klick auf den PREIS zeigt die Erklärung, wie der Preis zustande kommt — DYNAMISCH je Messung ("morgen ist das der Preis, dann steht da 70 Euro mal 24; übermorgen 65 mal 24"): der individuelle Rechenweg JEDER Messung per Klick auf den Preis, aufbereitet ("Dafür musste man nicht einfach nur Zeilen schreiben, ein bisschen komplizierter").
3. **VERGLEICH**: Die vorgeschlagenen Smartphones sind "ein unterkomischer Unterabschnitt, den man total schnell übersieht" → richtig geiles, prominentes Design, das Spaß macht zu benutzen.
4. **PREISVERLAUF**: Der erste Graph dort ist "mehr Text als Graf", zeigt offenbar nur hartkodiert iPhone 17 Pro / Pro Max, und ist doch genau dasselbe wie unten, wo man Modell aussucht und den Graphen sieht. Wenn kein tieferer Hintergrund: den oberen Graph LÖSCHEN und den unteren Modell-Wahl-Graphen GANZ NACH OBEN ziehen.
5. **GERÄTEKATALOG**: Überall steht "kein Preis". "Man sieht, dass es verfügbar ist, in welcher Farbe. Aber was bringt mir das ohne Preis?" Der Preis muss da stehen.
6. **TCO-LISTE**: Bei Total Cost of Ownership fehlt eine Liste der Modelle wie im Gerätekatalog. Lösung von Antonio: KEINE neue Unterseite, sondern im GERÄTEKATALOG einen Umschalter/Filter "Total Cost of Ownership oder Einzelgerätpreis" - EINE Tabelle für beide, mit Preis in beiden Ansichten.
7. **ROTHER FADEN**: "fehlt mir momentan komplett, so ein Mischmasch" - die Seite braucht eine klare Struktur/Story.
8. **AUTOMATIK**: Wenn ein neues Modell rauskommt (neues iPhone), muss es AUTOMATISCH erkannt und geführt werden, nichts manuell programmieren. Übergeordnetes Ziel: "so gut, dass man nie wieder was dran ändern muss."

Meta-Regeln: so einfach wie möglich; wenig Text; jede Agenten-Aufgabe klein
und einfach (kurze Kontexte); Premortem-Denken; Screenshots als harte Abnahme.

## 2. Ist-Zustand mit Zahlen (aus den Befunden)

**Vergleich (Hauptansicht):** Steuerung oben, Antwort unten — bis zur Falz
(900 px) liegen Logo, 4 Reiter, 3 Band-Buttons, 6 Modell-Chips; der
Antwort-Satz beginnt bei 620 px, die Kurve bei 782 px (design.md). 11
Schrift-Ebenen, 22 Aufklapper (20 sehen aus wie Tabellenzeilen: `cursor:auto`,
kein Chevron), 18 388 Zeichen Fließtext (design.md). **Der Preis ist nirgends
klickbar** — 0 Klick-Handler auf den 16 Zeitreihen-Kreisen; "So gerechnet"
ist EIN statischer Satz mit dem Abrufdatum von HEUTE, nicht je Messung
(vergleich.md). Die 6 Modell-Chips stehen bei y=528–570 px, 12-px-Text, ohne
Preis — "übersieht man total schnell" ist ein Design-Befund, kein
Positionsbefund (vergleich.md).

**Radar:** 746 Tabellenzeilen, **0 % Grafik**, 3784 px mobil (4,5 Bildschirme
reine Tabelle); **727 rot eingefärbte Elemente** — Rot ist Teppich, nicht
Akzent; 48× wiederholte Zeile "Vodafone-Basis: … €"; vier Sektionen mit 16
Filter-Buttons übereinander (design.md).

**Preisverlauf:** 6 sichtbare Textblöcke mit 194 Wörtern, davon ein
78-Wörter-Ereignissatz und ein 1813-Zeichen-Datenblock unter der Grafik
("mehr Text als Graf", wörtlich messbar). Der obere Graph (G2) zeichnet 5
Linien mit nur **2 echten Kurven**, alle von mobilcom-debitel (iPhone 17
Pro/Pro Max, +650/+400 € = größte Bewegungen des Bestands — nicht hartkodiert,
aber im Ergebnis eine Apple-Ansicht). Das Suchfeld des Wählers steht bei
1176 px von 1581 px Reiterhöhe. Alle 89 Geräte haben ≥ 2 Messtermine, 47
erreichen die Diagramm-Schwelle 4; meistgemessen: iPhone 17 256 GB (10
Termine, 6 Anbieter) (preisverlauf.md, design.md).

**Gerätekatalog:** 566 Listungszeilen zu **111 Modell-Blöcken** — Listungs-,
nicht Modell-Ebene; 530 Zeilen mit Preis, **36× "ohne Preis", alle 1&1**,
obwohl alle 38 1&1-Listungen `preis_mit_vertrag_ab` tragen und 74 1&1-Bündel
im TCO-Store liegen; 3 Preisformate in einer Spalte; Spalte "Verfügbar" mit
90× "keine Angabe" (katalog.md, design.md). **Der TCO-Umschalter fehlt
komplett** (0 Umschalter gemessen); die TCO-Daten dafür existieren: 97
Modelle, alle mit belastbarer Karte, 96 vergleichbar, 68 mit
Vodafone-Referenz (katalog.md).

**Roter Faden:** Vier Modell-Zugänge auf einer Seite mit drei verschiedenen
Modell-Mengen (88/97 · 111 · 321) und zwei Schlüsseln — der objektive Kern
des "Mischmasch" (katalog.md). Der Radar trägt eine eigene TCO-Tabelle
(dieselbe Frage wie der Vergleich), seine Wochenkarte ist
Preisverlauf-Material, der Katalog-Aufklapper "Bei Wettbewerbern gelistet"
ist Radar-Material (design.md).

**Automatik:** Die Kette "Launch → Store" GREIFT — 16 Auto-Einträge am
17.09. (u. a. iPhone 18 Pro/Pro Max), 105 iPhone-18-Bündel mit Messtag 1 im
Store (auto-doku.md). **Aber die Sichtbarkeit bricht**: 0 Vorkommen von
iPhone 18 auf der Seite und in allen Exporten, weil
`AUTO_SICHTBAR_AB_MESTAGEN = 2` nur den Bündelweg rechnet; 12 der 16
Auto-Einträge (Watches, Tabs, AirPods) haben keine Bündel und erscheinen
NIE. Telekom liefert in Actions nicht (HTTP-202, `letzter_lauf: 2026-09-15`),
Daten nur über lokalen Handlauf (auto-doku.md). Unbekannten-Liste: 284
Zeilen, davon 87 ALDI-Tarif-Rauschen (auto-doku.md).

**Größe:** Seite 1,40 MB + Zeitreihen-Fragment 1,13 MB + Bündel-Fragment
1,17 MB ≈ 3,7 MB; Historie wächst mit ~427 Zeilen/Tag; Wachstumsrate über
Zeit n. z. (premortem.md). Der Rechenweg je Messung ist vollständig
rekonstruierbar: 2562/2562 Historien-Zeilen ergeben exakt das eingefrorene
`gesamt` als reine Summe (vergleich.md).

## 3. Zielbild

Die Seite erzählt EINE Geschichte in vier Schritten, in Leserichtung:
**Vergleich** ("Was kostet das Gerät gesamt?") führt mit großen
Modell-Karten und EINER Kurve, deren jeder Preis und Punkt auf Klick die
Rechung dieser Messung öffnet; **Radar** ("Wo sind wir teuer?") zeigt die
Abweichung zu Vodafone als Balkenbild statt 746 Zeilen; **Preisverlauf**
("Wie entwickelt sich der Preis?") ist von oben an der eine
Modell-Wahl-Graph, ohne zweiten Graph darüber; **Gerätekatalog** ("Was gibt
es überhaupt?") ist EINE Tabelle auf Modell-Ebene mit Umschalter
Einzelgerätpreis/TCO — jede Zeile mit Preis. Vor dem ersten Datenelement
steht höchstens ein Satz und eine Auswahlgruppe, die größte Zahl eines
Reiters ist seine Antwort, Rot bleibt Akzent, neue Modelle erscheinen von
allein. So einfach wie möglich: danach wird an Inhalten gearbeitet, nie
wieder an der Struktur.

## 4. Phasen P1..P5 (4-6 Phasen)

**Zuordnung Forderung → Phase:** F1→P4 · F2→P1 · F3→P1 · F4→P2 · F5→P3 ·
F6→P3 · F7→P4 · F8→P5. CLAUDE.md-Konsolidierung = kleiner Teil von P5.

### P1 — Vergleich: Preis-Klick und prominente Modell-Karten (F2, F3)

**Ziel:** Der Vergleichs-Reiter führt mit großen Modell-Karten, und jede
Preiszahl sowie jeder Kurvenpunkt öffnet auf Klick die Rechung genau dieser
Messung.

**DIE EINE REGEL:** Jede Preiszahl und jeder Kurvenpunkt der Zeitreihe
öffnet denselben Rechenweg dieser EINEN Messung — als gesetzte Rechung
(Posten × Anzahl = Summe), serverseitig gebaut, nie im Client gerechnet.

**Bau-Aufträge:**
1. **Rechenweg je Messung serverseitig** (`report/geraete_zeitreihe.py`):
   aus der Historien-Zeile je Messung eine Postenliste bauen (Zuzahlung,
   Anschlusspreis, Tarif × Monate, Rate × Monate = `gesamt`; beide
   Preisformen, 2562/2562 nachgerechnet — reine Summe) und je Serie als
   `<template data-m="datum">` unter das SVG hängen (Variante V1 aus
   vergleich.md). NICHT: Boni/Geräteanteil erfinden (nicht in der Historie),
   keine Client-Rechnung, keine neue Unterseite.
2. **Klick-Panel** (`app.js`, `style.css`): Klick auf Kreis (unsichtbare
   Trefferfläche r=12) ODER auf die Preiszahl im Antwort-Satz setzt das
   fertige Template in EIN Panel unter dem Graph; Vodafone-Näherungspunkte
   (haben keine Historien-Zeile) bekommen einen benannten Leerzustand.
   NICHT: Panel neben dem Punkt (mobil instabil), kein tooltip-Framework,
   keine Zahl wird im JS zusammengesetzt.
3. **Modell-Karten statt Chips** (`geraete.html.j2` + `kacheln` in Python):
   die 6 Karten tragen ab-Preis (bestes `gesamt` + Ø €/Monat),
   Bewegungs-Δ (erster→letzter Messpunkt), Anbieter-Punkte in Hausfarben
   und eine deutliche aktive Markierung; Ranking-Maß bleibt (Anbieterzahl,
   Punkte — PM-7). NICHT: Bilder (Katalog hat kein Bildfeld, 0 Treffer —
   Typografie/Preis/Bewegung sind die Mittel), `KACHELN_MAX=6` bleibt,
   kein zweiter Auswahlmechanismus (Klick → `waehle(modell, null)` bleibt).
4. **Zahlen absichern**: neue Zahlen (Karten-Preis, Panel-Posten) in
   `tests/test_seiten_zahlen.py`; Suchvorschau darf fertige Preis-STRINGS
   vom Server anzeigen (Anzeige ≠ Rechnen). NICHT: bestehende
   Wahrheitstests brechen.

**Abnahme:** Browser-Test: Klick auf Punkt UND auf Preis → sichtbares
"×"-Muster mit den Werten genau dieser Messung (design.md Regel 6);
Screenshots 1440+390; Antwort-Satz bleibt über der Falz (pruefe_portal 11c);
Fragmentgröße davor/danach protokolliert (erwartet +150–300 kB bei 1285
Messungen, vergleich.md); 0 Rechenoperatoren im JS auf Zeitreihen-Zahlen.
Messlatte für die Modell-Karten (F3 "prominent"), per Playwright gezählt
wie design.md — sonst hat ein Prüfer für "prominent" keine Latte:
Preiszahl je Karte ≥ 20 px Schrift; aktive Karte deutlich markiert
(Rahmen ≥ 2 px oder Flächenänderung); alle 6 Karten im ersten Viewport
bei 1440 UND 390.

**Risiken + bewusst nicht:** Fragment wächst (PM-6) — Deckel-Entscheidung
erst in P5 mit echten Messdaten; SVG-Klickziele sind klein (r=4,5) —
unsichtbare große Kreise sind Pflicht. Bewusst nicht: Delta-Ansicht
Messung A vs. B im Panel (möglicher Zusatz nach Sichtung), Raten als
Barpreis ausweisen.

### P2 — Preisverlauf: G2 löschen, Wähler nach oben (F4)

**Ziel:** Ein Konzept im Reiter — der Modell-Wahl-Graph ist der Inhalt und
steht oben, der feste Graph existiert nicht mehr.

**DIE EINE REGEL:** Der Reiter zeigt ohne jede Vorauswahl ein Diagramm —
das erste Gerät der Liste ist automatisch gewählt, der obere Graph ist
gelöscht.

**Bau-Aufträge:**
1. **G2 löschen** (`geraete.html.j2` G2-Block; toter Code mit wegwerfen
   nach E5-Regel: `geraete_tco_grafik.historie/_ereignisse/_reihenrang/
   MAX_REIHEN` ~200 Zeilen, `geraete_tco_karten.historienreihen` ~45 Zeilen;
   Präzedenz `setzeG0`). 4 der 6 Textblöcke fallen mit. NICHT:
   `geraete_verlauf.messtage` anfassen (der Wähler nutzt es), Export
   "Preishistorie" bleibt (läuft über `geraete_export`).
2. **Wähler nach oben + Auto-Vorauswahl** (`app.js`): `gewaehlt = null` →
   erstes Gerät der Liste automatisch wählen (meistgemessenes iPhone 17
   256 GB steht durch Sortierung schon oben); Reihenfolge Suchfeld →
   Zeitraum → Kacheln → Diagramm → Tabelle direkt unter die h2; Erklär- und
   Stand-Satz fallen oder in einen Aufklapper. Das kippt bewusst die
   B4-Regel "ohne Auswahl kein Diagramm" — von F4 gedeckt.
3. **Tests anpassen**: 3 Browser-Tests, die den Leer-Satz "Wählen Sie oben
   ein Gerät" festschreiben (`test_geraete_reiter_browser.py:954,1125`,
   `test_geraete_o3_rollen_browser.py:361`), auf Auto-Vorauswahl umstellen;
   ~8 G2-Tests entfernen (bewusst; `test_geraete_verlauf.py`, 21 Tests,
   bleiben unberührt). `pruefe_portal.py` Kriterium 11: Bedingung bleibt
   erfüllt (`svg.gr-g2` ODER `#gr-verlaufdaten`), nur Name/Kommentar
   anpassen.

**Abnahme:** Initialer Zustand ohne Klick enthält EIN SVG mit ≥ 4
Messpunkten; 0 Vorkommen `gr-g2` in `site/`; Screenshots 1440+390 —
Suchfeld und Diagramm im ersten Viewport (heute: Suchfeld bei 1176 von
1581 px); Reiter-Wortzahl ohne Auswahl von 194 auf < 60 gesenkt (Zählung
wie design.md).

**Risiken + bewusst nicht:** Auto-Vorauswahl zeigt evtl. ein uninteressantes
Gerät, falls die Messlage kippt — Sortierung nach `-messpunkte` ist die
Regel. Bewusst nicht: G2-Information "größte Bewegung des Markts" retten —
sie steht vollständig im Ereignis-Satz und in der Radar-Tafel (preisverlauf.md).

### P3 — Gerätekatalog: Preis rein, TCO-Umschalter (F5, F6)

**Ziel:** Der Katalog ist EINE Tabelle auf Modell-Ebene, in zwei Ansichten
— Einzelgerätpreis und Total Cost of Ownership — und jede Zeile trägt einen
Preis.

**DIE EINE REGEL:** Keine Katalogzeile sagt "ohne Preis": jede Modellzeile
trägt einen Barpreis ("ab X € bei Y") oder den benannten Bündel-Zustand
("nur im Bündel, ab X €/Monat") — nie Raten als Barpreis.

**Bau-Aufträge:**
1. **Modell-Ebene mit ab-Preis** (`report/geraete_view.py`, `katalogzeilen`):
   111 Modellzeilen statt 566 Listungszeilen; "ab X € bei Y" = min über
   NEU-Listungen (`barpreise()` liefert Beleg mit Betrag, Link, Datum),
   dazu Anbieterzahl; Spanne nur wenn wesentlich; Zustand im Schlüssel,
   refurbished nie mit neu mischen (Hausregel B1). Die 37 1&1-Zeilen zeigen
   "nur im Bündel, ab X €/Monat" aus `geraete_tco.json` (74 Bündel liegen
   vor). NICHT: Mittelwerte, Listungs-Details löschen (kommen in den
   Zeilen-Aufklapper).
2. **Umschalter Einzelgerätpreis/TCO** (`geraete.html.j2` + `app.js`): EIN
   Umschalter über EINER Tabelle; TCO-Ansicht: TCO-24 ab (`gesamt` min,
   vergleichbar), bester Anbieter, Ø €/Monat, `delta_kurz` (nur mit
   `referenz`), Band; Zustandsfilter in der TCO-Ansicht auf `neu` fixiert;
   beide Ansichten teilen `modell_schluessel`; Sortierung nach Rohwert
   bleibt. Leerzustände benannt ("kein Bündel gemessen" — 19 Modelle).
3. **Tests neu schnüren**: `test_geraete_seite.py` (19 Stellen; Spaltenkopf-
   und Zeilenzahl-Asserts auf Modell-Ebene neu), Deckel-Logik
   (`KATALOG_SICHTBAR`/`BLOCK_SICHTBAR`) modell-scharf, neue Zahlen in
   `tests/test_seiten_zahlen.py` (Zahlen OHNE get_text-Trenner lesen).
   NICHT brechen: `test_geraete_faden.py`, `test_geraete_o3_rollen.py`
   (Reitername "Gerätekatalog" bleibt).
4. **Export beider Ansichten** (`report/geraete_export.py`): E5-Regel
   "4/4 exportierbar" bleibt erfüllt — `geraete-aktuell.csv` bleibt
   Listungs-Export, die Modell-Tabelle kommt als Ansichts-Export dazu
   (eine Datei je Ansicht, kein Formatmix).

**Abnahme:** 0× "ohne Preis" im gerenderten Katalog (heute 36×); ein
Preisformat je Spalte je Ansicht (Regex, heute 3 Formate);
Reiterhöhe ≤ 3000 px (pruefe_portal 11b) nachmessen; Screenshots 1440+390;
Umschalter ohne Reload, mobil ohne Querscroll.

**Risiken + bewusst nicht:** Größter Testumbau aller Phasen (Zeilen ==
`_bestand_ids()` nagelt Listungsebene fest) — deshalb eigener Prüfer-Lauf.
Bewusst nicht: 19 nur-Katalog-Modelle (AirPods, Watches, iPhone 16e)
künstlich auf TCO hochrechnen; neue Unterseite (Antonios ausdrückliche
Lösung ist der Umschalter).

### P4 — Ein Design-Durchlauf: Ruhe und roter Faden (F1, F7)

**Ziel:** Ein Durchlauf über die ganze Seite: die Antwort ist die größte
Zahl, ein Steuerblock vor den Daten, kein Reiter ohne Grafik, Rot ist
Akzent, jede Story steht an ihrem Ort.

**DIE EINE REGEL:** Die Antwort ist die größte Zahl — im ersten Viewport
jedes Reiters liegt die größte Schrift auf einer Preis- oder Leitzahl, nie
auf Navigation, Titel oder Erklärung.

**Bau-Aufträge:**
1. **Radar wird Grafik** (`report/` + Vorlage): servergerendertes SVG —
   Balken Δ je Modell (Top N) über der Tabelle, Tabelle bleibt als
   Aufklapper; Rot-Deckel ≤ 10 rot eingefärbte Elemente je Tafel (heute
   727); die 48× wiederholte "Vodafone-Basis"-Zeile wird EINE Legende.
   NICHT: Radar-Tabelle löschen (Detail bleibt Klick).
2. **Faden-Umordnungen** (nur Verschieben, nichts streichen) — DREI
   Einzel-Aufträge an drei Reitern, je ein eigener Bau- UND
   Prüfer-Agent (drei Kontexte, kein gemeinsamer Ort):
   - **2a Wochenkarte:** "Was diese Woche auffällt" (letzte 14 Tage) aus
     dem Radar in den Preisverlauf.
   - **2b Aufklapper:** "Bei Wettbewerbern gelistet, bei Vodafone nicht
     (29)" aus dem Katalog in den Radar.
   - **2c Sprungziele:** Radar-Liste und Katalog auf `modell_schluessel`
     vereinheitlicht (eine Modell-Menge statt 88/97·111·321 —
     katalog.md §4).
3. **Falz und Steuergruppen** (`geraete.html.j2`, `style.css`): vor dem
   ersten Datenelement je Reiter höchstens EIN Satz und EINE Auswahlgruppe
   (≤ 2 Button-Reihen); Export-Knöpfe aus dem Kopf in eine Zeile Fuß (mobil
   stehen sie heute gequetscht über der Steuerung); Leitzahl des Reiters
   wird die größte Schrift (Vergleich: das TCO-Delta, heute 13 px mitten im
   Satz — design.md).
4. **Klickbarkeit und Etiketten** (`style.css`, Vorlage): jedes `<summary>`
   mit `cursor:pointer` und Aufklappzeichen (22 Aufklapper im Vergleich, 20
   sehen aus wie Zeilen); "Verfügbar"-Spalte (90× "keine Angabe")
   aufräumen — Etikett an Feld anpassen oder Spalte fallen lassen.
5. **Text-Deckel in `pruefe_portal.py`** (FM 4): sichtbare Zeichen je
   Reiter gegen Deckel (Vergleich heute 18 388, Radar 8359 Z); zusätzlich
   `<p>` nach einem SVG ≤ 200 Zeichen (heute 1813). Neue Information wird
   erst als Graf/Interaktion entworfen, Text nur als Label.

**Tests (Inventur — die Verschiebungen machen vier benannte Tests rot;
bewusst umgestellt, Vorher-rot je Auftrag):**
- 2a Wochenkarte: `tests/test_geraete_seite.py:1148`
  (`test_alte_preisbewegung_steht_nicht_unter_diese_woche`) greift die
  Karte über `_radar()` an → auf die Preisverlauf-Tafel umstellen.
- 2b Aufklapper: `tests/test_wettbewerbsradar_alarme.py:213`
  (`test_bei_wettbewerbern_gelistet_steht_im_geraetekatalog`, Assert
  `#tafel-katalog #gr-sortiment` in Zeile 223) VERBIETET den Radar-Ort →
  Assert auf `#tafel-radar` umdrehen; die E3-Festnagelung auf den
  Katalog kehrt bewusst (F7 gedeckt).
- Auftrag 3 Export-Fuß: `tests/test_geraete_export_mobil_browser.py:157`
  ("keine Export-Reihe im Kopf") und `tests/test_geraete_o4_export.py:86`
  ("Knopf … steht im Kopf der Tafel") → beide auf Fußzeile umstellen.
NICHT brechen: alle übrigen Katalog-/Radar-Tests; neue Zahlen weiterhin
in `tests/test_seiten_zahlen.py`.

**Abnahme:** Playwright je Reiter: max(fontSize) im ersten Viewport liegt
auf einer Preis-/Leitzahl; ≤ 2 Button-Reihen vor dem ersten Datenelement;
`#tafel-radar svg` ≥ 1; ≤ 10 Rot-Elemente je Tafel; alle summary
`cursor:pointer`; Text-Deckel grün; Screenshots 1440+390 je Reiter (harte
Abnahme), mobil: Kurve im ersten Viewport des Vergleichs, Radar ohne
4,5-Bildschirm-Tabelle.

**Risiken + bewusst nicht:** Größtes Risiko ist Rückschlag in Textlast
(FM 4) — deshalb der Deckel im selben Zug. Bewusst nicht
(Antonio-Entscheidung, nicht gebaut): Radar-Tafel und Vergleichs-Tafel
verschmelzen (FM 6.2); Export-CSVs und Portfolio-Aufklapper entfernen;
`geraete-quellen.html` Fußlink entfernen (B1-Lehre).

### P5 — Automatik & Betrieb (F8, + CLAUDE.md-Konsolidierung)

**Ziel:** Ein neues Modell erscheint von selbst — vom Launch bis in Katalog,
Zeitreihe und Export, mit Alarm statt Stillheit.

**DIE EINE REGEL:** Sichtbarkeit folgt den Daten, nicht dem Weg — Bündel
ODER Listung genügt: ein Modell ist spätestens nach dem zweiten Nachtlauf
sichtbar und exportierbar, und "Auto: 0" an zwei aufeinanderfolgenden
Tagen ist ein Alarm, kein Normalzustand.

**Bau-Aufträge:**
1. **Sichtbarkeit auf beide Wege** (`report/geraete_zeitreihe.py:672–679`):
   `AUTO_SICHTBAR_AB_MESTAGEN` rechnet Bündel ODER Listung — Katalog ab
   erster Listung (Tag 1), Zeitreihe ab 2 Bündel-Messtagen; die 12
   bündellosen Auto-Modelle (Watches, Tabs, AirPods) bleiben aus der
   Zeitreihen-WAHL draußen (keine unsichtbaren Wahl-Einträge) und stehen im
   Katalog (FM 6.4). Test mit Fixture: Modell mit 1 Messtag Bündel →
   nach-regelkonformem Rendern sichtbar; iPhone 18 als Live-Fall.
2. **FM-2-Alarm** (`geraete_pipeline.py`/Protokoll): Ausfall-Schwelle
   "Anbieter liefert 7 Tage 0 Sätze" als Protokollzeile; Provider-Proben
   je Lauf (Existiert-Schwelle: liefern X % der erwarteten Sätze noch ihre
   Felder? Präzedenz Phase S: metric3+metric2 == monthlyPrice, 66/66).
   NICHT: Alarm per Mail/Teams bauen.
3. **Unbekannte entrauschen + Anker schließen** (`autoerkennung.py`):
   ALDI-Tarif-Titel aus `geraete_unbekannt.jsonl` filtern (87 von 284
   Zeilen sind Rauschen — die Liste ist der Frühindikator aus FM 1);
   iPad-Titel als Auto-Anker ergänzen (strukturierter Name mit
   Hersteller-Präfix Apple vorhanden — auto-doku.md). NICHT: Hand-Katalog
   pflegen (Hand schlägt Auto bleibt).
4. **PM-6 jetzt rechnen** (kleines Skript/Auswertung): ab 01.10. (14 Tage
   Messdaten) Fragmentgröße gegen Messtage auftragen, Deckel ableiten
   (z. B. nur letzte N Messtage im Fragment, Älteres bleibt im Export) und
   als Test verankern (ein Fragmentgrößen-Test existiert heute nicht,
   vergleich.md). Deckel VOR der ersten Megabyte-Überschreitung — auch die
   +150–300 kB aus P1 mit messen.
5. **CLAUDE.md konsolidieren** (klein, ein Agent): Geräteseite in §5/§8a
   auf EINEN Stand bringen (E2–E6 + P1–P5 dieser Strategie); die 8
   überholten Stellen aus auto-doku.md §3 (Reiter-Schichten, Nav-Zahl,
   "Telekom bleibt leer", Positionskarte-Existenz, G1/G2, Export-Stelle,
   "0 Auto-Einträge", Seitengröße). Fallstricke §6 (Sägezahn-ID, 202,
   Zustandsdimension, robots) bleiben unberührt.

**Abnahme:** Tag-2-Sichttest live: "iphone 18" suchen → Vorschau → Band →
Antwort-Satz → Deep-Link (E6-Standard); Protokollzeilen (Auto-Anlage,
Unbekannte, Fragmentgröße, Ausfall-Schwelle) im Log sichtbar;
Fragmentgrößen-Test grün; CLAUDE.md-Diff vom Lead gegengelesen.

**Risiken + bewusst nicht:** Strukturierte Namen können ihr Schema ändern
(FM 1b) — dagegen hilft nur der Unbekannten-Frühindikator, nicht mehr Code.
Bewusst nicht / Antonio-Entscheidung: Telekom-202-Umgehung (R3 in
`STRATEGY_GERAETE_TCO.md`) — kein Bau ohne seine Entscheidung; der
lokale `lokallauf_telekom.py` bleibt bis dahin dokumentierter Nebenpfad.

## 5. Reihenfolge & Abhängigkeiten

- **P1 → P2 → P3** sind inhaltlich unabhängig (P2 und P3 frei
  vertauschbar); alle drei vor P4, sonst läuft der Design-Durchlauf doppelt.
- **P4** braucht P1–P3 (Falz-, Faden- und Grafikregeln greifen auf die
  umgebauten Reitern; erst messen, dann durchsetzen).
- **P5**: Aufträge 1–3 nach P3 (Katalog-Sichtbarkeit hängt an der
  Modell-Ebene); FM-2-Alarm jederzeit möglich; PM-6-Deckel frühestens
  01.10. datenbasiert (14 Tage Wachstumsrate); CLAUDE.md als letzter
  Schritt. Der iPhone-18-Tag-2-Sichttest fällt am 18.09. ohnehin an —
  P5-Auftrag 1 soll ihn grün machen.
- Jede Phase: EIN Workflow, 3–6 kleine Bau-Agenten + je ein frischer
  Prüfer-Agent + Abnahme/Merge durch den Lead (Lean-Lead-Muster).

## 6. Betrieb danach

- **Monatlich live (Sichttest-Fragen):** "pixel 11"-Beispiel (E6-Standard)
  · "Wo ist Vodafone am teuersten?" · "Belege je Anbieter klickbar?" · die
  vier Reiter-Fragen je einen Satz · "mobil ohne Querscroll?" — plus zwei
  Zusatzfragen: "Steht das neueste Gerät drin?" und "Dauert der Laden am
  Telefon?" (FM 1/3).
- **Täglich 3+1 Protokollzeilen** als Frühindikatoren: Auto-Anlage,
  Unbekannte (entrauscht), Fragmentgröße, Ausfall-Schwelle (FM 2).
  `Auto: 0` zwei Tage in Folge bei bekanntem Launch = hinsehen.
- **Nach jedem bekannten Launch:** Tag-2-Sichttest ("iphone 19" suchen).
- **Auto-Regeln, unverändert:** Auslöser bleibt der strukturierte Name
  (nie der Titel), Hand schlägt Auto, unbekannte Farben werden bewahrt
  (SKU bleibt stabil), `marktstart`/`vorgaenger` bleiben leer am Auto-Eintrag.

## 7. Premortem-Schutz (dauerhafte Regeln aus premortem.md)

1. **FM 1 — Automatik bricht still:** Sichtbarkeit auf beide Wege (P5),
   Unbekannten-Liste entrauschen (P5), Telekom-202 als offene
   Antonio-Entscheidung geführt, Tag-2-Sichttest nach Launch (§6).
2. **FM 2 — Quellentod:** Ausfall-Schwelle + Provider-Proben JE Lauf als
   Protokollzeile (P5); `geraete-quellen.html` bleibt verlinkt (B1-Lehre).
3. **FM 3 — Größe:** PM-6-Deckel datenbasiert ab 01.10., als Test
   verankert, vor der ersten Megabyte-Überschreitung (P5).
4. **FM 4 — Text kriecht zurück:** Text-Deckel je Reiter in
   `pruefe_portal.py` (P4); Bau-Regel: neue Information erst als
   Graf/Interaktion, Text nur als Label; der Preis-Klick (P1) ist der
   Härtetest — gerät er zum Textblock, ist FM 4 sofort zurück.
5. **FM 5 — Wartung:** Reiterzahl bleibt 4; kein neuer Reiter/Modus ohne
   eine der drei Fragen (Gesamtkosten? Preisentwicklung? Markt).
   Streich-Kandidaten NUR als Antonio-Entscheidung: Radar-CSV nach
   6 Monaten Nichtnutzung; Export-Knöpfe, Portfolio, Quellen-Seite
   bleiben (nicht kritisiert).
6. **FM 6 — Simple-Audit:** oberer Preisverlauf-Graph gestrichen (F4,
   gedeckt); Umschalter ersetzt die TCO-Liste (F6, gedeckt);
   Radar/Vergleich-Verschmelzung = Antonio-Entscheidung; bündellose
   Auto-Modelle nur im Katalog.
7. **FM 7 — ehrliche Rest-Risiken:** Bot-Schutz/IP-Challenges,
   Angebotsstruktur-Änderungen an Fremdschlüsseln, neue Geräteklassen/
   Benennformen — nicht codebar weg, nur durch Beobachtung (FM-2-Alarm) und
   den monatlichen Rhythmus getragen. "Nie wieder ändern" gilt für die
   STRUKTUR; diese drei Stellen bleiben bewachte Ausnahmen.
