# Strategie „EINE Geräteseite" — Zielbild, Phasen E1–E6, Regeln

**Stand 16.09.2026. Anlass: Antonios Durchklicken des O1–O4-Live-Stands, wörtlich
und vollständig die Anforderung** („zwei Unterseiten ist absolute Scheiße … zu
viele Unterkommentare … erst runterscrollen, um den Graphen zu sehen … was soll
ich mit einem Balkendiagramm … Modell wählen, Tarifband wählen, Graph passt sich
an … nirgendwo ein Quell-Link … iPhone 18 Pro, wieso wird das nicht automatisch
gecrawlt … Suchfeld mit kleiner Vorschau statt Dropdown-Riesenliste … erst wenn
dir nichts mehr einfällt, bist du fertig"). Grundlagen: `AUFTRAG_GERAETE_EINE_SEITE.md`,
`docs/STRATEGIE_GERAETE_OPTIK.md` §7 (O1–O4 stehen live und bleiben Baustand),
Recherchen R1 (Vergleichsseiten, 12 Befunde), R2 (Bestandsmessung beider Seiten),
R3 (Automatik) — Ausfertigungen in `/tmp/strategie-geraete/`, Kernzahlen hier
im Text. Dieses Dokument ersetzt die Zwei-Seiten-Entscheidung §4.2 der
Optik-Strategie (Option A ist von Antonio kassiert); O1–O4-Ergebnisse
(Zeilengliederung, Lazy-Fragment `site/data/geraete-buendel.html`, Exporte,
Evaluationskette) bleiben Bestand und werden hier zusammengeführt.

**Revision 16.09.2026 (Abend):** nach drei Prüfberichten überarbeitet —
Clean-Code-Prüfer (BESTANDEN MIT AUFLAGEN), Deckungs-Prüfer (BESTANDEN MIT
AUFLAGEN), Pre-Mortem. Alle S1/S2-Befunde sind eingearbeitet, S3/S4 nach
Ermessen; die Pre-Mortem-Gegenmaßnahmen stehen als eigene Tafel (vor §10)
und jeweils in der betroffenen Phase. Zeile für Zeile im Änderungsprotokoll
am Ende dieses Dokuments.

**Antonios Worte sind die Mindestbedingungen, nicht die Aufgabenbeschreibung.**
Jede Phase geht über sie hinaus (§9). Und: die Abnahme macht grundsätzlich ein
unbeteiligter Agent (§7) — der Bauende hat bewiesen, dass er die eigene Arbeit
nicht unparteiisch sieht.

---

## 1. Zielbild in einem Absatz

**Es gibt genau EINE Geräteseite: `geraete.html`.** Sie ist in vier Tafeln
gegliedert — **Vergleich** (Hauptansicht, aktiv) · **Radar** (wo ist Vodafone
teurer) · **Verlauf** · **Katalog** —, und die Leitfrage *„Was kostet Gerät X
bei Anbieter Y mit Tarifband Z über 24 Monate — und gibt es diese Kombination
dort überhaupt?"* wird ohne einen Klick und ohne Scrollen beantwortet. Über der
Falz (1440×900 wie 390×844) stehen, in dieser Reihenfolge: schlanker Kopf mit
H1 und Datumzeile; das **Modell-Suchfeld** (Tippen „google pixel" genügt, eine
Vorschauliste mit ≤ 8 Treffern inkl. Speicherstufen erscheint, jeder Treffer
anklickbar — kein Dropdown, keine Riesenliste) neben der **Tarifband-Wahl**
(Klein · Mittel · Groß · ohne Band, je mit GB-Spanne); das **Antwort-Band im
Check24-Muster**: „Google Pixel 11 Pro · Band Mittel (20–49 GB): 6 von 7
Anbietern führen es · Ø 45,90–62,30 €/Monat · TCO-24 ab 1.098,60 €" — die
„7" ist der gemessene Bestandsstand (sie wächst mit jedem Anbieter-Adapter
und steht nie als Konstante im Code), und **jede Zahl des Antwort-Bands ist
reine Ableitung aus denselben Anbieterzeilen**, keine zweite Rechnung
(rot-vor-grün in E2); EIN
Rechenschaftssatz („so gerechnet: alle einmaligen und monatlichen Kosten über
die Bindung, minus Boni, geteilt durch die Laufzeit — jede Zeile verlinkt das
nächtlich gemessene Angebot"); dann die **Ergebnisliste**: je Anbieter EINE
Zeile mit Ø €/Monat als führender Zahl, dem Zwei-Zahlen-Muster „monatlich +
einmalig", einem Inline-Längenband, Δ zur Vodafone-Referenz, Beleg-Link und
Messtermin — fehlende Kombinationen stehen als **benannte Lücken-Zeilen** im
selben Rhythmus („1&1: kein Bündel in Mittel erhoben"), nicht als Legende am
Rand. Auf 1440 sind 3–4 Zeilen über der Falz, auf 390 mindestens die erste.
Kein Glossar, kein „Wie gerechnet?"-Block, kein Aufklapper oberhalb der ersten
Zeile. Der eigenständige Balkengraph als Antwort-Obergeschoss ist **ersetzt**
durch diese Liste (Begründung und Entscheidungsregel §4); die Radar-Inhalte
leben als zweite Tafel auf derselben Seite, `wettbewerbsradar.html` wird
Meta-Refresh-Weiterleitung. Neue Modelle (iPhone 18 Pro, iPhone Duo) legt der
nächtliche Lauf **selbst** im Katalog an (§5) — kein Handgriff im Code.

---

## 2. Deckungs-Tabelle: jeder Kritikpunkt → Phase

Kein Punkt aus Antonios Durchklicken und aus der Auftragsdatei bleibt ohne
Phase. Wortlaut sinngemäß verkürzt; „F-x" sind die in der Auftragsdatei
vergessen gegangenen Punkte aus dem Prompt dieser Strategie.

| # | Antonios Punkt (sinngemäß) | Phase |
|---|---|---|
| 1 | Zwei Unterseiten (Geräte + Wettbewerbsradar) — EINE Seite | **E3** (Radar wird Tafel; Alt-URL leitet weiter; Navigation 8 → 7) |
| 2 | „Begriffe erklärt" weg, „Wie gerechnet?" weg, Unterkommentare alle weg | **E2** (Vergleichsansicht: Glossar gelöscht, Wie-gerechnet → 1 Rechenschaftssatz), **E3** (Radar-Tafel: 260-px-Methoden-Intro → 1 Satz, Sektionserklärabsätze gestrichen) |
| 3 | Musste erst scrollen, um den Graphen zu sehen | **E2** (Antwort-Band + erste Zeilen über der Falz; 11c neu gefasst als Ergebnisfalz, §6) |
| 4 | Graph unverständlich — „was soll ich mit einem Balkendiagramm?" | **E1** (Form-Entscheidung am Entwurf, §4), **E2** (Bau der Ergebnisliste) |
| 5 | Modell oben wählen, dann Tarifband, Graph passt sich an | **E2** (Suchfeld + Band-Wahl steuern die Liste; Deep-Link `?modell=` bleibt) |
| 6 | Sehen, was jeder Anbieter für Tarif × Modell nimmt | **E2** (Ergebnisliste je Anbieter, Bündelzeilen je Anbieter expandierbar — O3-Lazy-Fragment bleibt) |
| 7 | Preis-Transparenz: kein Quell-Link an den Balkenwerten | **E2** (Beleg-Link + Messtermin auf JEDER Zeile; B3 des Auftrags) |
| 8 | Modellsuche als Suchfeld mit kleiner Live-Vorschau (GB-Angaben, klickbar vor vollständiger Eingabe), kein Dropdown | **E2** (F-C; ≤ 8 Treffer, ab 1–2 Zeichen) |
| 9 | „Warum ist nur auf iPhone 17 Pro eingestellt?" | **E2** (Suchfeld ersetzt den festen Selektor; zuletzt gewähltes Modell bleibt per Deep-Link adressierbar) |
| 10 | iPhone 18 Pro / iPhone Duo nicht automatisch gecrawlt — neue Modelle/Tarife ohne Code-Änderung | **E4** (F-D; Auto-Anlage aus strukturierten Live-Katalognamen, §5) |
| 11 | Leitfrage-Beispiel „Pixel 11 Pro bei Telekom mit mittlerem Tarif" | **E1** (Beispiel als Sichttest-Fall im Entwurf, ehrliche Lücke falls Bestand fehlt), **E2** (Band Mittel mit GB-Spanne, Median-GB als Voreinstellung) |
| 12 | Verfügbarkeit Modell × Band („iPhone 17 Pro mit kleinem Tarif?") | **E2** (benannte Lücken-Zeilen je Anbieter = P3 Bandabdeckung; B2 des Auftrags) |
| 13 | Recherche bei Vergleichsseiten (Check24 etc.), wie ein vernünftiges Layout aussieht | **E1** (R1 ist eingerechnet: Listen-/Check24-Muster, §4; keine Phase separat) |
| 14 | Kontrolle immer durch einen ANDEREN Agenten | **§7 Prozess** (unbeteiligter Screenshot-Agent + adversarieller Evaluator je Phase, festgeschrieben) |
| 15 | Über die Mindestbedingungen hinaus verbessern, bis nichts mehr einfällt | **§9** (10 eigene Verbesserungen, je Phase zugeordnet oder zur Freigabe) |
| 16 | Auftrag B1 Randbedingung: Alt-URL, Deep-Links, 88 Querlinks, Navigationstest, Kriterium-11-Quelle | **E3** (alles in dieser Phase, siehe Abnahmeliste) |
| 17 | Auftrag offene Punkte: Export-Knöpfe mobil, Alarm-Zeilen im Radar-Export, Test-Leer-Sicherungen | **E5** |
| 18 | „in einem Jahr benutzt keiner mehr die Unterseite — woran?" (Premortem) | **§7 Prozess** (Premortem-Frage fester Bestandteil jedes Evaluator-Laufs) |

---

## 3. Bau-Phasen E1–E6

Jede Phase ist eine eigene, workflow-fähige Einheit: eigener Branch, eigener
Evaluator, eigenes Ende mit grüner Suite. Der Prozess steht in §7 und gilt für
alle Phasen gleich; hier stehen Ziel, Bausteine, Abnahme, Tests, Risiko.

### E1 — Statischer Entwurf mit echten Zahlen + Einkäufer-Sichttest

**Ziel.** Das Zielbild aus §1 als statischer, klickbarer Prototyp in
`docs/entwuerfe/geraete-eine-seite-2026-09-16/` (Vorbild und bewährter Prozess:
`docs/entwuerfe/geraete-optik-2026-09-11/`), mit **echten Zahlen** aus
`data/state/geraete_db.json` + `geraete_tco.json` + `tarife.jsonl`. Der Entwurf
entscheidet die offenen Formfragen (§4) und wird von Antonio freigegeben, bevor
irgendetwas im `src/` angefasst wird — genau das hat bei O1–O4 funktioniert.

**Bausteine.**
- `entwurf.html`: Vergleichsansicht vollständig (Suchfeld-Prototyp mit
  Live-Vorschau über den echten 60-Geräte-Bestand, Band-Umschaltung,
  Antwort-Band, Rechenschaftssatz, Ergebnisliste mit Inline-Bändern, Δ,
  Beleg-Links, Lücken-Zeilen, expandierbare Bündelzeilen) plus Radar-Tafel als
  **Höhen-Wireframe** (Sektionen mit Ziel-Höhen aus §6, keine Vollausstattung)
  plus Verlauf/Katalog als Platzhalter-Reiter.
- **Pixel-11-Pro-Fall zuerst messen:** steht im Bestand ein Telekom-Bündel für
  „Google Pixel 11 Pro" × Band Mittel? (Telekom-Tagesdaten seit 15.09.) Wenn
  ja: als Beispielzeile in den Entwurf; wenn nein: die **ehrliche Lücken-Zeile**
  („Telekom: Datenstand fehlt – Quelle in Vorbereitung") in den Entwurf —
  Antonios Beispiel MUSS im Entwurf vorkommen, egal wie der Bestand aussieht.
- **Falz-Vorrechnung für BEIDE Ansichten (Abnahmekriterium):** der Wireframe
  trägt nicht nur die Radartafel-Summe, sondern auch die **390-Falz-Summe der
  Vergleichsansicht**: Aufstellung je Element (Nav, Kopf, Tab-Leiste,
  Suchfeld/Band, Antwort-Band, Rechenschaftssatz) bis Zeilenbeginn, Ziel
  ≤ 770 px, sodass die erste Anbieterzeile (~70 px) bei ≤ 844 px endet (11c).
  Die korrigierten Zielwerte stehen in §6; die alte Zielliste (834 px
  Vorlauf) riss die Falz-Grenze rechnerisch — der Widerspruch wäre sonst
  erst nach dem Bau in E2 aufgeflogen.
- **Drei bewusste Rest-Aufklapper als Wortlaut-Abweichung gekennzeichnet:**
  Antonio sagte „Die Unterkommentare, alle weg." Der Entwurf behält drei
  Reste — den 2-zeiligen Rechenschaftssatz, EINEN Fuß-Aufklapper „Maßstab &
  Datenlage" (26/79 px), die Rechenweg-Aufklapper je Bündelzeile —, jeder mit
  Messwert und Transparenz-Begründung (Antonios eigene „intransparent"-
  Kritik, R1/Check24-Standard). Diese drei Reste stehen im Entwurf
  AUSDRÜCKLICH als Abweichung von seinem Wortlaut und gehen mit in die
  Freigabe; nichts wird still behalten.
- Einkäufer-Sichttest durch eine frische Testerin (keine Vorkenntnisse,
  nichts gebaut): Leitfragen des Tests, jede mit Zeitmessung:
  1. „Was kostet ein Google Pixel 11 Pro bei der Telekom mit mittlerem Tarif?"
     — beantwortet in ≤ 12 s ohne Erklärung?
  2. „Kann man das iPhone 17 Pro mit einem kleinen Tarif finanzieren?" —
     beantwortet ohne Erklärung (das ist die Verfügbarkeitsfrage)?
  3. „Woher kommt die Zahl in der ersten Zeile?" — Beleg-Link in ≤ 10 s gefunden?
  4. „Finden Sie das günstigste Angebot über alle Anbieter" — ≤ 10 s?
  5. „Wo ist Vodafone gerade teurer als der Wettbewerb?" (Radar-Tafel) — ≤ 15 s?
- Screenshots 1440 + 390, Falz-Markierung; Palette durch den dataviz-Validator
  mit benanntem Maßstab — bestanden heißt: Kontrast jeder Etikett- und
  Bandsorte gegen den Untergrund ≥ 4,5:1 und ≤ 12 unterscheidbare Farbwerte
  auf der Seite (die Inline-Bänder skalieren in der Länge, sie wechseln
  nicht die Farbe). Ohne diese Zeile wäre „durch den Validator" nicht
  prüfbar.

**Abnahme (messbar).**
- Entwurf existiert, lokal über `python3 -m http.server` ansehbar, Band-Umschaltlogik
  funktioniert an mindestens Klein/Mittel/ohne Band.
- Sichttest protokolliert: 5 Fragen, 5 Zeiten, jede ≤ Zielzeit ODER der
  Entwurf wird nachgebessert, bis sie es ist.
- Pixel-11-Pro-Fall mit dem gemessenen Bestandsstand dokumentiert (Zahl oder
  Lücke, mit Dateinamen der Messung).
- **390-Falz-Summenrechnung der Vergleichsansicht** vorgelegt (Aufstellung je
  Element bis Zeilenbeginn, Summe ≤ 770 px; Vorlage §6). Ohne diese Rechnung
  gilt die E1-Abnahme als NICHT erfüllt — 11c (erste Zeile ≤ 844 px) wäre
  mit der alten Zielliste unerreichbar und rieße erst nach dem Bau.
- Höhen-Wireframe der Radar-Tafel trägt eine Summenrechnung, die ≤ 2.950 px
  (390) und ≤ 2.900 px (1440) ergibt — Vorlage ist die NEU gerechnete §6-
  Tabelle (Revision 16.09.: mobile Alarm-Sektion selbst Stellschraube,
  default-zugeklappt MIT Menge). Die alte §6-Rechnung summerte sich auf
  ≈ 4.980 px mobil und die Nachbesserregel brachte nur ~4.440 px; wer nach
  der alten Tabelle baut, reißt 11b. Sonst vor dem Bau nachdeckeln.
- **Antonios Freigabe — messbar gefasst:** Freigabe ist seine AUSDRÜCKLICHE
  Antwort (Zitat im Umsetzungsstand §10). Ohne Antwort: höchstens Entwurfs-
  Nachschärfung, KEIN Bau in `src/`. Eine Stillstands-/Wartefrist ist nur
  als ausdrücklich dokumentierte Regel zulässig (dann mit Datum in §10) —
  die frühere Klausel („nach Freigabeanfrage gilt der Stand") öffnete genau
  die Tür, die E1 begründet („ohne Freigabe gebaute Optik wurde kassiert"),
  nur dokumentiert.
- In der Freigabe ANTWORTEN lassen (nicht nur zeigen): die 4–6 Kacheln der
  häufigsten Geräte neben dem Suchfeld (§9 Nr. 8) und die drei Wortlaut-
  Abweichungen (Bausteine oben) — je ausdrücklich ja/nein.

**Rot-vor-grün.** Keine — E1 ändert keinen Produktionscode. Stattdessen: die
Sichttest-Fragen 1–5 werden als Namen der E2/E3-Abnahmetests übernommen (daran
hängen später die echten Tests).

**Risiken.** (a) Suchfeld-Prototyp verführt zu Überbau — nur die 8-Treffer-
Vorschau, keine Sortierung/Filter im Prototyp. (b) Entwurf verspricht Höhen,
die der echte Bestand (länge Modellnamen) sprengt — deshalb Radar-Tafel nur als
Wireframe und die 11b-Messung bleibt in E3 der Wahrheitszeuge. (c) Pixel-11-Pro-
Bestand fehlt — dann ist die Lücken-Zeile selbst der Abnahmefall (sie MUSS im
Entwurf stehen, damit Antonio sie freigibt).

### E2 — Hauptansicht: Suchfeld, Ergebnisliste, Belege, Lücken, Entrümpelung

**Ziel.** Die Vergleichsansicht wird nach dem freigegebenen Entwurf gebaut.
Damit erfüllt E2 die Punkte 2–9 und 11–12 der Deckungs-Tabelle für die
Hauptansicht und die komplette F-A-Entrümpelung der Vergleichstafel.

**Berührte Dateien/Module.**
- `src/telco_radar/report/templates/geraete.html.j2` (+ Teilvorlage für die
  Ergebnisliste), `templates/app.js` (Suchfeld-Autocomplete, Expander),
  `templates/style.css`.
- `src/telco_radar/report/geraete_view.py` (Aufbereitung Suchindex der Modelle
  aus Katalog + Bestand, Antwort-Band, Lücken-Gründe je Anbieter), evtl. neu
  `report/geraete_ergebnis.py`, wenn `geraete_view.py` zu groß wird (Clean-
  Code-Referenz: eine Klasse, ein Zweck).
- `src/telco_radar/report/geraete_tco_band.py` (Band-Daten, GB-Spannen je Band
  aus dem Bestand statt fester Labels).
- **Antwort-Band ist reine Ableitung:** die Aufbereitung rechnet Ø-Spanne,
  „ab"-Preis und „N von M" AUSSCHLIESSLICH aus derselben Zeilen-Liste, die
  die Ergebnisliste rendert — das Band führt keine eigene Rechnung und keine
  eigenen Zähler (CLAUDE.md: zwei Rechnungen für dieselbe Zahl sind zwei
  Zahlen); die Anbieterzahl „M" kommt aus dem gemessenen Bestand, nie aus
  einer Konstante.
- **Suchindex-Schwelle im CODE:** `MINDESTLISTUNGEN_FUER_AUSWAHL = 1` als
  benannte Konstante im serverseitigen Aufbereitungsmodul; JS konsumiert nur
  den fertigen Index (die JS-Drift-Falle aus CLAUDE.md — Index zählt anders
  als Matcher — ist in diesem Repo zweimal passiert). Ein Modell ohne
  Listung taugt nicht als wählbares Gerät.
- **Vorschau deterministisch sortieren:** bei mehr Treffern als 8 entscheiden
  nicht die ersten acht Listenplätze, sondern: Modelle mit aktuellen
  Listungen und größerer Bandabdeckung zuerst, Auslaufware ans Ende (der
  Index führt beide Daten). Sonst füllt der durch E4 wachsende Katalog die
  Vorschau mit Auslaufgeräten — „iphone" zeigte dann acht Altgeräte, und
  genau das neue Suchfeld wird zum Ärgernis.
- **Daumenregel-Zeile (§9 Nr. 4) als belegte Beobachtung:** Formulierung nach
  Finanztip ist eine Marktkonvention MIT Quelle, kein Imperativ am Leser; die
  Empfehlungsprüfung (`textwerkzeug.ohne_vodafone_rat`) bekommt dafür einen
  Testfall — sonst entscheidet der Bauende unter Zeitdruck und die nachträgliche
  Satz-Streichung ist die teure Variante (Falldokument `_strip_vodafone_advice`
  löschte ganze Absätze).
- **Lücken zur Kennzahl machen:** der nächtliche Lauf loggt je Modell × Band
  „N von M Anbietern führen es" ins Protokoll und meldet dauerhafte Lücken
  (dieselbe Kombination > 14 Tage ohne Satz) LAUT. Ein Fall, der über Wochen
  Lücke bleibt, wird zum DATEN-Auftrag (Adapter/Erhebung — bewusst außerhalb
  dieser Strategie, §8), nicht zur UI-Frage. Antonios Beispiel (Pixel 11 Pro
  × Telekom × Band Mittel) ist ein fester Live-Prüffall, dokumentiert mit dem
  Datum des nächsten liefernden Tageslaufs.
- Beleg-Links: `geraete_tco_karten.py` liefert je Bündel `Quelle` (steht heute
  im Rechenweg-Aufklapper und in `geraete-tco.csv`) — auf Zeilenebene heben.
- `scripts/pruefe_portal.py`: Kriterium 11c umbauen auf die erste
  Anbieterzeile der Ergebnisliste (neuer Selektor, §6).
- **Gelöscht:** Glossar-Abschnitt („Begriffe erklärt"), „Wiegerechnet?"-
  Block, Fußnoten-Zeile mit Glossar-Link, der Intro-Satz mit
  Schwesterseiten-Link (entfällt mit E3 von selbst — hier schon streichen,
  der Link stirbt in E3).

**Abnahme (messbar).**
- **11c neu** (an der echten Seite): auf 390×844 endet die erste Anbieterzeile
  der Ergebnisliste ≤ 844 px, Seite nicht breiter als 390 px; auf 1440×900
  enden mindestens 2 Zeilen ≤ 900 px; **kein** `<details>` und kein Erklärblock
  zwischen Band-Wahl und erster Zeile.
- Sichttest-Fragen 1–4 aus E1 als Browser-Tests reproduziert und grün
  (Fragen-XML oder URL-Parameter-basiert, Zielzeiten als DOM-Distanzen
  ausgedrückt: Beleg-Link derselben Zeile wie die Zahl) — und als DAUER-
  KRITERIUM angelegt: der nächtliche `geraete.yml`-Job, der ohnehin selbst
  rendert, misst die Ergebnisfalz am ECHTEN Bestand (11c-Selektor) und meldet
  Riss als FEHLER, nicht als Protokollzeile. Sonst wächst der E4-Katalog die
  erste Zahl unbemerkt unter die Falz, und „auf Anhieb" gilt nur am Bau-Tag.
- Suchfeld: Vorschau ab spätestens 2 eingegebenen Zeichen, ≤ 8 Treffer, jeder
  Treffer mit Modellname + Speicherstufen; Auswahl ohne vollständige Eingabe
  möglich (Klick auf Treffer Nr. 3 nach „pixel"); Deep-Link `?modell=` bleibt
  ausgewertet (O3-Verhalten erhalten, Test existiert — mitziehen) UND setzt
  jetzt auch das Band zustandssicher zurück (`?modell=…&band=…`).
- Antwort-Band und Liste stammen nachweisbar aus derselben Aufbereitung:
  Ø-Spanne == min/max der Zeilen, „ab" == Minimum, „N von M" == Zeilen plus
  benannte Lücken (Tests unten) — und die Kopfzahl „N von M" steht ab jetzt
  nächtlich im Protokoll (Baustein „Lücken zur Kennzahl machen").
- Jede Anbieterzeile trägt: Ø €/Monat (führend), „monatlich + einmalig",
  Inline-Band, Δ, genau EINen Beleg-Link (der des erhobenen Angebots; bei
  aggregiertem Balken Anker auf die Bündelzeilen darunter — B3 des Auftrags),
  Messtermin. Fehlende Anbieter: benannte Lücken-Zeile mit Grund
  („kein Bündel in Klein erhoben" / „verkauft nur ohne Band" / „Datenstand
  fehlt – Quelle in Vorbereitung").
- Glossar und „Wie gerechnet?" kommen im gerenderten HTML der Tafel
  **nicht mehr vor** (DOM-Abwesenheitstest).
- `pytest -q` komplett grün (außer den 3 vorbestehenden Roten), `pruefe_portal`
  17/1 (nur 8b vorbestehend), 11b für alle Tafeln < 3.000 px.

**Rot-vor-grün-Tests** (Auswahl, Namen konkret):
`tests/test_geraete_suchfeld.py`:
- `test_vorschau_ab_zwei_zeichen_und_hoechstens_acht_treffer`
- `test_jeder_treffer_traegt_modellname_und_speicherstufen`
- `test_auswahl_ohne_vollstaendige_eingabe_moeglich`
- `test_vorschau_ist_kein_dropdown_mit_allen_modellen` (zählt gerenderte
  Optionen im Ruhezustand: 0)
`tests/test_geraete_ergebnisliste.py`:
- `test_jede_zeile_traegt_genau_einen_beleglink_derselben_zeile`
- `test_fehlender_anbieter_steht_als_zeile_mit_grund` (3 Gründe getrennt)
- `test_oe_pro_monat_fuehrt_die_zeile` (DOM-Reihenfolge)
- `test_erste_zeile_endet_ueber_der_telefonfalz` (Browser, echte Seite)
- `test_glossar_und_wie_gerechnet_existieren_nicht_mehr`
- `test_zahl_der_zeilen_entspricht_der_bilanz` (Deckungsregel aus
  CLAUDE.md: Lookup-Länge asserted)
- `test_antwortband_rechnet_aus_den_zeilen` (Ø-Spanne == min/max der Zeilen,
  „ab" == Minimum, „N von M" == Zeilen + benannte Lücken — sonst wäre das
  Band eine zweite Rechnung für dieselben Zahlen)
- `test_antwortband_anbieterzahl_kommt_aus_dem_bestand` (eine Konstante „7"
  stünde still falsch da, sobald der nächste Anbieter-Adapter liefert)
- `test_kein_modell_ohne_listung_in_der_vorschau` (Schwelle aus der
  Modulkonstante, nicht aus dem Template)
- `test_deeplink_setzt_modell_und_band_zurueck` (`?modell=…&band=…`)
- `test_vorschau_sortiert_aktuelle_modelle_vor_auslaufware`

**Risiken.** (a) **Falz auf 390:** Nav allein ist 226 px — die alte
Kopfstruktur (Hero 227 + Tabs 38 + Filter 68 + Antwort 122) ließ die erste
Zeile erst bei ~810 px erscheinen. Der Entwurf muss Nav + Kopf + Tab-Leiste +
Suchfeld/Band + Antwort-Band + Rechenschaftssatz auf ≤ 770 px drücken
(korrigierte Zielwerte in §6; die alte Zielliste kam auf 834 px Vorlauf und
die Grenze wäre rechnerisch gerissen). Stellschrauben werden am ENTWURF
entschieden, nie im Bau: Nav-Kompaktmodus, Antwort-Band + Rechenschaftssatz
als EIN Block, Export-Knöpfe mobil unter die Falz, Untertitel weg (die
letzteren beiden haben Präzedenz aus O1/O4). Die E1-Abnahme erzwingt die
Vorrechnung vor dem Bau. (b) Suchfeld-Autocomplete ohne Framework —
Index klein halten (Modellnamen aus Katalog, ~60–90 Einträge), keine Fuzzy-
Suche, nur Präfix-/Wortanfang-Match, sonst Performance- und Verwirrungsrisiko.
(c) Beleg-Link bei zwei Bündeln je Anbieter: Anker-Lösung aus B3 bauen, nicht
den ersten Link nehmen. (d) Die Suchfeld-Vorschau darf den Bestand nicht
fehlen: Index aus Katalog **und** geraete_db (ein Modell ohne Listung taugt
nicht als wählbares Gerät — Schwelle: ≥ 1 Listung).

### E3 — Eine Seite: Radar-Tafel, Alt-URL, Navigation, Höhenbudget

**Ziel.** `wettbewerbsradar.html` hört auf zu existieren (als Inhalt); alle
seine Sektionen leben als Tafel „Radar" auf `geraete.html`. Punkt 1 und 16 der
Deckungs-Tabelle. Die Seite bleibt unter 11b (3.000 px je Tafel) — die
Rechnung dazu steht in §6 und muss hier am echten Bestand nachgemessen werden.

**Berührte Dateien/Module.**
- `src/telco_radar/report/wettbewerbsradar.py` (View-Aufbereitung bleibt;
  Ausgabe wandert in die Geräteseiten-Vorlage), `report/html.py`
  (`render_site`: keine eigene Radar-Datei mehr, stattdessen
  `_redirect_html()`-Weiterleitung `wettbewerbsradar.html` →
  `geraete.html#tafel-radar`; `wettbewerbsradar_verlinkt`-Global entfällt),
  `templates/base.html.j2` (Navigation 8 → 7: „Wettbewerbs-Radar" raus),
  `templates/geraete.html.j2` (neue Tafel; Tab-Leiste
  „Vergleich · Radar · Verlauf · Katalog").
- Die 88 Gerätegruppen der TCO-Sektion → **flache, sortierbare Abweichungs-
  tabelle** (Modell · Band · Wettbewerber-TCO · Vodafone-TCO · Δ € · Δ % ·
  Beleg), Deckel 12 sichtbar + „alle 321 Paare anzeigen"-Aufklapper. Die
  per-Modell-Tiefe liefert die Hauptansicht (Suchfeld!) — die Gruppenform ist
  auf der EINEN Seite doppelt.
- 88 Radar-Querlinks „Dieses Gerät im Vergleich" (aus O3) → In-page-Sprünge
  auf die Vergleichsansicht mit `?modell=`.
- **Gewicht und Lazy:** vier Tafeln auf EINER URL lassen das HTML mit dem
  Katalog wachsen (mobil brechen Ladezeiten). Die Neben-Tafeln (Radar,
  Verlauf, Katalog) werden nach dem Bündel-Fragment-Muster LAZY geladen —
  erst bei Tab-Wechsel (Muster: `site/data/geraete-buendel.html` aus O3);
  das Gewicht der gerenderten `geraete.html` wird Messzahl mit Obergrenze
  im nächtlichen Protokoll (Deckelwert aus Messung dokumentiert, Muster
  `UEBERSICHT_MAX_ZEILEN`). Sonst hält die Seite jede Höhengrenze und ist
  faktisch ein Tunnel, den niemand mehr öffnet.
- `tests/test_suche_page.py` (Navigationstest auf 7 Einträge),
  `scripts/pruefe_portal.py` Kriterium 11 (Alarmtabelle: Quelle von der
  Radar-Datei auf die Geräteseite umziehen), ggf. weitere Tests, die
  `wettbewerbsradar.html` referenzieren (`grep -rl wettbewerbsradar tests/`).
- Archiv-Berichte/`site/**`-Verweise auf die Alt-URL prüfen: Weiterleitung
  fängt alles; trotzdem `grep -rn "wettbewerbsradar" site/*.html` und die
  Weiterleitung für die großen Verbraucher verifizieren.

**Abnahme (messbar).**
- Navigation hat **7** Einträge (Test angepasst und grün); „Wettbewerbs-Radar"
  taucht in keiner Nav mehr auf; kein toter Link auf `wettbewerbsradar.html`
  (der Meta-Refresh-Zähler arbeitet).
- 11b: **alle vier** Tafeln der EINEN Seite < 3.000 px, an der echten Seite
  gemessen — Radar-Tafel Ziel ≤ 2.900 (1440) / ≤ 2.950 (390), Vorrechnung §6.
- Kriterium 11 (Alarmtabelle) liest von `geraete.html` und ist grün.
- Deep-Link `geraete.html?modell=<id>` funktioniert von allen ehemaligen
  Radar-Positionen (Stichprobe 5 Geräte im Browser-Test).
- Sichttest-Frage 5 („wo ist Vodafone teurer?") ≤ 15 s am echten Stand.
- Suite komplett grün, `pruefe_portal` 17/1 (8b vorbestehend).

**Rot-vor-grün-Tests.**
- `test_navigation_hat_sieben_eintraege` — ausgebaut aus der **5er-Fassung**
  (`test_navigation_hat_fuenf_eintraege`, `tests/test_suche_page.py:83`; sie
  rendert OHNE `cfg` → 5 Einträge; die live 8 entstehen über die Globals
  `geraete_verlinkt`/`wettbewerbsradar_verlinkt` in `base.html.j2`). Der neue
  Test muss MIT `cfg` beide Zustände halten: 7 Einträge inkl. „Geräte",
  „Wettbewerbs-Radar" weg — die falsche Herkunftsangabe („8er-Fassung")
  führt einen ausführenden Agenten zum falschen Ausgangspunkt.
- `test_alt_url_wettbewerbsradar_leitet_auf_geraete_weiter` (Meta-Refresh +
  sichtbarer Link, Muster `_redirect_html`).
- `test_keine_seite_verlinkt_auf_die_alte_radar_datei_als_inhalt`.
- `test_abweichungstabelle_zeigt_zwoelf_zeilen_und_den_aufklapper` samt
  Lookup-Assert GEGEN DIE BILANZ: `assert len(zeilen) == anzahl_aus_der_
aufbereitung` und `assert len(zugeordnet) == len(erwartet)`. Die Zahl 321
ist die R2-Messung vom September 2026 und gehört in den ABNAHMETEXT, nie in
den Testcode — E4 derselben Strategie legt neue Modelle an, die Paar-Zahl
wächst, und ein fester Wert meldete die nächste Datenänderung statt den
nächsten Umbau.
- `test_radar_tafel_unter_dreitausend_pixel` (Browser, echte Seite, 1440+390).
- `test_rang_eins_der_abweichung_steht_immer_unter_den_sichtbaren_zeilen`
  (Lookup gegen den Store; Δ-%-Sortierung aufsteigend ist unveränderliche
  Vorgabe — ein Deckel, der die stärkste Benachteiligung auf Rang 13+
  versteckt, widerlegt die Leseentscheidung des Radars; dieselbe Klasse wie
  der Zeilendeckel-Fall vom 29.08.).

**Risiken.** (a) **Das Höhenbudget ist das Kernrisiko** — IST mobil 20.398 px.
Gelingt nur mit flacher Abweichungstabelle + Deckeln nach der NEU gerechneten
§6-Tabelle (Revision 16.09.): Lifecycle UND Händler default-zugeklappt UND die
Alarm-Sektion MOBIL default-zugeklappt MIT Menge („alle 48 Alarme anzeigen";
desktop bleibt sie offen). Die frühere Nachbesserregel ohne die mobile
Alarm-Zuklappung brachte nur ~4.440 px und riss 11b rechnerisch — genau der
Widerspruch, den der Clean-Code-Prüfer gefunden hat. Falls die Summe am
echten Bestand trotzdem reißt: nächste Stellschraube ist die Zahl sichtbarer
Alarm-Zeilen mobil (12 → 8, Zeilenhöhe messbar dokumentiert) — NIE
Inhaltslöschung, keine Deckelzahl ohne Messung. (b) Die
Abweichungstabelle darf keine zweite Rechnung einführen: `wettbewerbsradar.
radar()` bleibt die eine Quelle der Δ %-Werte (Modulkopf verlangt das). (c)
Der Meta-Refresh ist kein 301 — bekannt (CLAUDE.md §5), akzeptiert. (d) Merge-
Konflikte mit dem nächtlichen `geraete.yml`-Bot-Commit möglich — vor dem Merge
origin/main ziehen (hat in O3 funktioniert).

### E4 — Auto-Erkennung neuer Modelle und Tarife (F-D)

**Ziel.** Der nächtliche Lauf legt neue Modelle **selbst** im Katalog an —
iPhone 18 Pro und Pro Max lagen am 15.09. strukturiert vor und wurden
verworfen; das ist der engste Engpass des ganzen Radars. Nach E4 gilt: ein
neues Modell wird **mit dem ERSTEN strukturierten Satz eines Live-Katalogs
angelegt** (Listung und Launch-Preishistorie entstehen sofort) und erscheint
**ab 2 Messtagen** ohne Code- oder Config-Änderung in der Auswahl. Die
frühere Formulierung „sobald zwei Anbieter es strukturiert listen" ist
GESTRICHEN: sie widersprach der eigenen Baustein-Regel („Listungen werden
SOFORT angelegt" — mit dem ersten Satz entsteht die Katalog-ID) und tauchte
in keinem Baustein und keinem Test auf. Ein falsch angelegtes Modell ist
teurer als ein fehlendes (Risiko d) — aber ein NICHT angelegtes verliert die
Launch-Preishistorie, und das ist der Engpass, wegen dem es E4 gibt. Soll
Antonio die 2-Anbieter-Schwelle dennoch vorziehen, ist sie als gegenteilige
Option mit eigenem rot-vor-grün-Fall auszuformulieren
(`test_ein_anbieter_legt_noch_nicht_an`) — Entscheidung liegt bei ihm.
Empfehlung aus R3 (Optionen a/b/c bewertet): **Option
b** — Anlage ausschließlich aus den strukturierten Modellnamen der Live-
Kataloge (Telekom `name`, o2 `description`, Vodafone `modell`, congstar/1&1
analog) mit Sichtbarkeits-Schwelle, **ergänzt um die Persistenz aus Option c**
(`data/state/geraete_unbekannt.jsonl` als Sicherheitsnetz und Arbeitsliste —
ist ohnehin offene Strategie-Aufgabe). Option a (Titel-Heuristik) wird NICHT
gebaut: sie wiederholt die verbotene ID-Falle (R3-Messung: 48 von 60 Geräten
in mehreren Titelschreibweisen; „iPhone 18" im Katalog hilft nachweislich
nicht gegen „iPhone 18 Pro", `_MODELLZUSATZ`).

**Bausteine.**
- Neu `src/telco_radar/analyze/geraete_katalog_auto.py` (oder eine Funktion in
  `geraete_pipeline.py`, wenn klein): nach dem Sammeln werden alle Rohsätze
  mit `erkenne_geraet() → None`, die aus einer Live-Katalog-Quelle mit
  Strukturfeldern kommen, gesammelt; Hersteller aus dem Namen geschält (über
  die Herstellerliste des Katalogs, keine eigene Heuristik); normalisiert
  (groß/klein, „5G" weg — `normalisiere`/`wortmarken` existieren);
  Kollisionsprüfung gegen den Bestand (`Katalog.__post_init__`-Wächter);
  Anlage als YAML-Eintrag mit `hersteller`, `modell`, `speicher` (aus
  Strukturfeld), `generation` NUR falls `serie_aus_modell` eindeutig, sonst
  leer (Serien-Falle Redmi 17/Note 17/17T), `marktstart`/`vorgaenger` leer,
  Marker `auto: <datum>` je Eintrag; Auto-Einträge werden NUR ans Dateiende
  angehängt (deterministisch, merge-freundlich).
- **Sichtbarkeits-Schwelle:** Listungen werden SOFORT angelegt (die
  Launch-Preishistorie ist der wertvollste Messpunkt — genau sie geht heute
  verloren); das Modell erscheint in der **Suchfeld-Vorschau und der
  Ergebnisliste erst ab 2 Messtagen** (kein Ein-Tages-Wackler; Schwelle aus
  R3). Sie steht als benannte Modulkonstante (`SICHTBAR_AB_MESTAGEN = 2`) —
  bewusste Entscheidung im Sinne der Repo-Konvention (`VORLAUF_TAGE`,
  `DIAGRAMM_AB_TERMINEN`): sie hängt an der Messlogik, nicht an
  Betreiberdaten, und gehört deshalb nicht nach `config/*.yaml`.
- **Zubehör-Negativliste:** der bestehende Zubehörfilter ist Titel-Heuristik
  (Wörter VOR dem Modellnamen) und greift bei strukturierten Namen nicht —
  dort steht das Zubehörwort HINTER dem Gerätenamen („Apple iPhone 17 Pro
  Silicone Case"). E4 führt eine Negativliste für Nicht-Gerät-Kategorien
  (Case, Hülle, Cover, Watch, Headset, Charger, …) als Anlage-Sperre. Ein
  falsch angelegter Eintrag erzeugt dauerhafte IDs, deren Entfernen sku_ids
  verschiebt (Datenwanderung, vgl. offene Galaxy-A17-5G-Falle). Rot-vor-grün
  mit einem ECHTEN strukturierten Zubehör-Namen aus dem Tageslauf-Output als
  Fixture. Dazu wird der Katalogkopf-Kommentar, der die Handpflege heute
  ausgerechnet mit Zubehör/Auslaufware begründet, mit umgeschrieben — er
  wäre nach der Automatik überholt.
- `unbekannte_titel` + neue Farb-Schreibweisen persistieren nach
  `data/state/geraete_unbekannt.jsonl` (Titel- und Farb-Sektion, dedupliziert,
  mit Anbieter und Datum) — die 90-Tage-Log-Retention ist heute der einzige
  Ort, an dem der Vorschlag existiert. **Persistenz ist Commit-Sache (S1):**
  der Runner ist ephemeral; `geraete.yml` committet heute gezielt genau vier
  State-Dateien (Workflow-Zeile ~130 ff., „Gezielt nur die vier Dateien
  dieser Stufe. Kein git add data/"). Ohne Erweiterung dieser Liste wäre die
  Datei nach dem Lauf weg, die Abnahme „existiert nach dem Lauf" nur
  innerhalb des Jobs grün (Fehlerklasse „Lookup ins Leere ist grün") und das
  „Sicherheitsnetz und Arbeitsliste" so flüchtig wie der Status quo. E4
  erweitert deshalb die gezielte git-add-Liste des STAND-Commits um
  `data/state/geraete_unbekannt.jsonl` als FÜNFTE Datei; der Katalog-Commit
  committet weiterhin NUR `config/geraete_katalog.yaml`. Die Abnahme prüft
  die COMMITTETE Datei im Repository, nicht den Job-Zustand.
- `geraete.yml`: Schritt „Katalog-Commit" — wenn der Lauf Auto-Einträge
  angelegt hat, committet er `config/geraete_katalog.yaml` mit Message
  „katalog: N Modelle automatisch angelegt (iPhone 18 Pro, …)". Bot-Commit,
  klar markiert, kein data/state-Mitcommitt darüber hinaus.
- **Tarife prüfen, nicht umbauen:** Kachel-/ldjson-Anbieter legen neue Tarife
  bereits automatisch an (R3 §4 — 24 `live_shop`-Sätze). Einzige harte Liste
  ist die Telekom-Dokument-Slugliste. Unteraufgabe mit Messung: kann
  `bevorzugt` zu einem Muster (`magentamobil-*`) werden, ohne den
  `max_dokumente`-Deckel zu sprengen? Wenn nein: bewusst offen (§8) — die
  Kachel-Lesart (`telekom_kacheln`) deckt die Telekom-Tarife bereits live.

**Sicherheitsregeln (CLAUDE.md-Fallstricke, alle gelten unvermindert).**
- `device_id`/`sku_id`/`listung_id` aus **normalisierten Feldern**, nie aus
  dem Produkttitel (`geraete_model.py:9–31`). Die Auto-Anlage gewinnt die ID
  aus dem strukturierten API-Namen des Anbieters, nicht aus einem Händler-
  Titel — und nur, weil der Anbieter selbst kanonisch ist.
- **Modellzusatz-Vollständigkeit:** der Anlagename muss die komplette
  Bezeichnung sein (inkl. „Pro Max"); der Zusatz-Wächter `_MODELLZUSATZ`
  bleibt unangetastet; rot-vor-grün mit dem Sägezahn-Fall.
- **Hersteller-Schälung** in EINE Richtung mit Test („Apple iPhone 18 Pro" →
  hersteller Apple, modell „iPhone 18 Pro"; ein zweiter Anbieter ohne
  Herstellerpräfix „iPhone 18 Pro 5G" muss auf dieselbe device_id falten).
- **Mensch schlägt Auto:** existierende Hand-Einträge werden nie verändert;
  bei Kollision (Auto will anlegen, was von Hand existiert) gewinnt der
  Hand-Eintrag, der Automatik-Lauf ergänzt höchstens `speicher`/`aliase`
  nicht einmal das: nur loggen.
- **Kein Datenverlust durch Anlage:** ein Angelegt-Werden darf niemals
  bestehende `sku_id` verschieben — der Wächter ist der Mehrdeutigkeits-
  Check; dazu ein Test am echten Bestand: nach dem Anlage-Lauf ist die Zahl
  der Listungen unverändert oder nur gewachsen.
- **Konsistenz-Check je Nacht:** jede neu angelegte device_id wird im
  selben Lauf gegen die Live-Namen BEIDER Live-Katalog-Quellen gegen-
  geprüft; eine Doppel-Anlage (zwei IDs, dasselbe Gerät — Telekom
  „iPhone 19 Pro 5G" vs. o2 „iPhone 19 Pro") meldet sich LAUT im Protokoll
  und geht auf die Arbeitsliste, statt still weiterzulaufen (Sägezahn-
  Gefahr; die Kanonisierung über Anbieter hinweg ist nicht garantiert).
  Die Reproduktion des 15.09.-Falls bleibt dauerhafter Regressionstest.

**Abnahme (messbar).**
- **Reproduktion des 15.09.-Falls:** der echte Telekom-Rohsatz „Apple iPhone
  18 Pro 256 GB polar" (aus dem Tageslauf-Output) legt als Fixture geführt
  einen Katalog-Eintrag `apple-iphone-18-pro` an, mit `speicher: [256]`,
  `marktstart: `leer; `erkenne_geraet('Apple iPhone 18 Pro 256 GB polar')`
  liefert danach das Gerät (dieser Test ist HEUTE rot — perfekt rot-vor-grün).
- Nach dem nächsten echten `geraete.yml`-Lauf: `grep "iPhone 18" config/
  geraete_katalog.yaml` trifft; `geraete_db.json` enthält Listungen; Protokoll
  zeile nennt „N Modelle automatisch angelegt". iPhone 18 Pro ist nach dem
  übernächsten Lauf in der Suchfeld-Vorschau wählbar (2 Messtage).
- ID-Stabilität: „iPhone 18 Pro 5G 256 GB" (zweiter Anbieter, andere
  Schreibweise) landet auf derselben device_id; „iPhone 18" und „iPhone 18
  Pro" bleiben zwei Geräte; „iPhone Duo" wird angelegt, sobald ein Live-
  Katalog es strukturiert führt (heute: nirgends — Lücke dokumentiert).
- `geraete_unbekannt.jsonl` existiert nach dem Lauf in der COMMITTETEN Form
  (git log zeigt die Datei im Stand-Commit der fünf Dateien) und enthält die
  Farbarbeitsliste (cream, frost, olive … vom 15.09.).
- Suite grün; kein Test der Katalog-Wächter fällt; `pruefe_portal` unverändert
  17/1.

**Rot-vor-grün-Tests.**
- `test_unbekannter_strukturierter_titel_legt_katalogeintrag_an` (heute rot).
- `test_zweite_schreibweise_landet_auf_gleicher_device_id`.
- `test_modellzusatz_erzeugt_getrennte_id` (Sägezahn-Gegenprobe).
- `test_autoeintrag_erscheint_erst_ab_zwei_messtagen_in_der_auswahl`.
- `test_menschlicher_katalogeintrag_schlaegt_auto` (Kollisionsfall).
- `test_unbekannte_titel_und_farben_persistieren`.
- `test_anlage_verschiebt_keine_bestehende_sku`.
- `test_strukturiertes_zubehoer_wird_nicht_angelegt` (echter Zubehör-Name
  aus dem Tageslauf-Output als Fixture — kein erfundener).
- `test_doppelanlage_gegen_die_live_namen_beider_quellen_wird_laut`
  (Protokoll-Meldung statt stiller Weiterlauf).

**Risiken.** (a) Katalog-Wachstum: Live-Kataloge führen Auslaufware — die
2-Messtage-Schwelle hält die UI sauber, der Katalog wächst trotzdem. Deckel:
nur Modelle mit Strukturfeld (kein Zubehör), nur aus Live-Katalog-Quellen;
Zubehörfilter der Adapter bleiben wirksam. Kataloggröße nach jedem Lauf loggen
(„Katalog: 83 → 85 Einträge"). (b) YAML-Konflikt Mensch/Auto: angehängte
Auto-Einträge + Marker; Merge-Konflikt nur, wenn ein Mensch dieselbe Zeile
pflegt — der Wächter greift vorher. (c) Der Katalog-Commit im Workflow ist ein
neuer Bot-Commit-Typ — Commit-Hygiene testen (nur die eine Datei). (d) Ein
falsch angelegtes Modell ist teurer als ein fehlendes: die Schwelle und der
Kollisionswächter sind die Dämme; der Evaluator prüft jede angelegte ID gegen
die Live-Namen beider Quellen.

### E5 — Rest-Tafeln, Exporte, Aufräumarbeiten

**Ziel.** Verlauf und Katalog an die neue Struktur anpassen, die offenen
Punkte des Auftrags schließen, Export- und Testschulden abbauen.

**Bausteine.**
- Verlaufs-/Katalogtafel: Titel und Einstiege an die Eine-Seite-Struktur;
  Katalog-Tafel bekommt dasselbe Suchfeld-Muster wie die Hauptansicht
  (Bestands-Suche über 568 Zeilen, gleiche Vorschau-Komponente, zweiter
  Konsument derselben Funktion — keine zweite Implementierung, JS-Falle aus
  CLAUDE.md „zwei Umsetzungen derselben Rechnung").
- Export-Knöpfe mobil neu bewerten (Auftrag: „der Export ist Antonios
  Werkzeug"): auf 390 unter der Falz EINE kompakte Export-Zeile (drei Links),
  die nicht mit dem Suchfeld um die Falz konkurriert.
- `wettbewerbsradar.csv` → heißt jetzt `geraete-radar.csv` (oder bleibt Name,
  Entscheidung am Entwurf) und bekommt die 48 Alarm-Zeilen dazu — deckt dann
  alle vier Zahlensektionen der EINEN Seite (O4-Evaluator S3).
- Test-Leer-Sicherungen: die fünf Zähler ohne in-sich-Leere-Sicherung (O4-
  Evaluator) bekommen je ihre `assert`-Zeile („SIM-only-Test grün bei leerem
  Bestand" soll unmöglich werden) — in E5 WIRKLICH einbauen, nicht nur
  einplanen (Pre-Mortem-Befund: mit den gekürzten Resten wäre keiner davon
  eingebaut worden, und ein toter Adapter stünde wochenlang als grüne
  Leer-Tafel live).
- **Substanz-Wächter im Renderpfad:** der Render vergleicht je Tafel die
  Zeilenzahl gegen den Store (O4-Maßstab „Zeilenzahl == Store") und schreibt
  bei Abweichung oder Unterschreiten einer Mindestmenge den Befund LAUT auf
  die Seite und ins Protokoll („gescheitert" vs. „gab es nicht" — eine
  gescheiterte Stufe muss sich bis auf die Seite melden, CLAUDE.md). Damit
  wird der stille Bot-Commit eines Leerzustands unmöglich, wenn ein Anbieter
  seine Schnittstelle ändert und ein Adapter null Sätze liefert.
- Aufräumen: verwaiste View-Felder, IDs und CSS-Klassen der alten
  Zwei-Seiten-Welt (`grep` nach `wettbewerbsradar` in src/ und templates/ muss
  nach E5 nur noch den Weiterleitungs- und Exportnamen finden).

**Abnahme (messbar).** Suite grün; `pruefe_portal` 17/1; 11b alle Tafeln;
Export: `geraete-tco.csv` + Radar-CSV sind unverändert exakt gegen ihre Stores
(O4-Maßstab: Zeilenzahl == Store), Radar-CSV deckt 4/4 Sektionen; Suchfeld-
Komponente von Hauptansicht und Katalog besteht denselben Test-Katalog;
kein toter Code der Alt-URL außer der Weiterleitung.

**Rot-vor-grün.** `test_radar_export_enthaelt_auch_die_alarmtabelle` (rot: nur
321+44 Zeilen), `test_katalogsuche_benutzt_dieselbe_vorschau_wie_der_vergleich`
(rot: Komponente existiert nicht), `test_keine_geraete_exportknöpfe_dupliziert`
(zählt, rot gegen Stand mit 2 Zeilen).

**Risiken.** Klein — aber: Umbenennen der Radar-CSV ist ein Link-Bruch für
jeden, der die URL gebookmarkt hat; alte URL als weitere Mini-Weiterleitung
(static sites können keine Header-Redirects — derselbe Meta-Refresh-Mechanismus
auf eine Export-Indexseite oder den neuen Namen NIEMALS still 404en lassen).

### E6 — Livegang und Live-Sichttest

**Ziel.** Die Eine-Seite ist live, per md5 gegencommittet, und Antonios
Beispiel ist am LIVESTAND beantwortet.

**Bausteine.** Render-Kommitt „Seite neu gebaut" (site/ umfassend: geraete,
redirect, exports, data-Fragmente), Push, `deploy.yml`-Ausgang prüfen (ein
Push allein ist kein Deploy — CLAUDE.md §6), md5-Gegenprobe live gegen
committet, CDN-Direktvergleich per Inhalts-Marker. Danach Live-Sichttest:
Suchfeld „pixel 11" → Band Mittel → Antwort lesen; „iPhone 18" in der Vorschau
(erst nach 2 Messtagen — wenn E4 frisch gemergt ist, ehrlich dokumentieren,
ab wann es auftaucht). Falls der Pixel-11-Pro × Telekom × Mittel-Fall im
Bestand fehlt: die Live-Lücken-Zeile als Nachweis führen, plus Datum, wann der
nächste Tageslauf ihn liefern kann.

**Abnahme.** deploy success; `md5(live/geraete.html) == md5(committed)`;
Live-Screenshots 1440+390 mit Falz-Overlay der ersten Zeile; Alt-URL leitet
live weiter; Protokoll des Live-Sichttests in `/tmp/` + eine Zeile im
Umsetzungsstand (§10 dieses Dokuments). E6 definiert zusätzlich den
**Betriebsmodus ohne Agenten-Orchestrierung** und hält ihn in §10 fest —
sonst lebt die Seite nur, solange jemand Agenten orchestriert: monatlich die
fünf Sichttest-Fragen live beantworten plus drei Protokollzeilen lesen
(Kataloggröße, Bestand, Auto-Anlage — alle drei werden bereits geloggt);
jede Phase so abschließen, dass eine fremde Session mit Strategie-Doc +
CLAUDE.md allein weiterarbeiten kann.

**Risiken.** CDN-Propagation (bekannt: Inhalts-Marker statt md5 wiederholen);
Nachtläufe committen site/ selbst — Reihenfolge: nach dem letzten Bot-Commit
mergen, dann eigener Render-Push.

**Reihenfolge-Begründung.** E1 zuerst, weil jede Formfrage (Graph, Falz,
Suchfeld, Radar-Kompression) am Entwurf entschieden und von Antonio freigegeben
werden muss — O1–O4 haben bewiesen, dass ohne Freigabe gebaute Optik
kassiert wird. E2 vor E3: die Hauptansicht ist der Skandalkern und definiert
die Tafelstruktur, in die E3 den Radar einsortiert; ein Radar-Umbau vor der
Hauptansicht würde zweimal gebaut. E4 nach E3: datenseitig unabhängig von der
Optik, aber erst auf der fertigen Eine-Seite sichtbar bewertbar — und pro
verstrichem Tag verliert die Launch-Preishistorie des iPhone 18 einen
Messpunkt (E4 so früh wie möglich NACH E3, nicht ans Ende). E5 sammelt
Reste bewusst ein, damit E2/E3 nicht an Nebenbedingungen hängen bleiben. E6
schließt ab, weil Live-Gegenprüfung und Antonios Beispiel zur Livesache
gehören.

**Revisions-Prüfung der Reihenfolge (16.09.): unverändert.** Neu gegeneinander
gehalten: E4s Abnahme „in der Suchfeld-Vorschau wählbar ab 2 Messtagen" setzt
die E2-Vorschau voraus — E4 kann deshalb nicht vor E2; E1 liefert mit den
beiden Falz-/Höhenrechnungen (Vergleichsansicht + Radartafel) jetzt die
Zahlen, an denen E2/E3 hängen, ohne E1 wäre E2 an 11c strukturell nicht
abnehmbar; E5s Substanz-Wächter braucht die fertigen Tafeln aus E2/E3. Die
Launch-Preishistorie spricht weiterhin für E4 so früh wie möglich NACH E3 —
an dieser Begründung ändert die Revision nichts.

---

## 4. Design-Regeln für den Graphen — benannte Form statt „besser machen"

**Befundlage (R1).** Keiner von neun untersuchten Anbietern (Check24, Verivox,
heise/TARIFFUXX, idealo, Finanztip, Telekom, o2, WhistleOut, Apple) zeigt
„Gerät × Anbieter × Tarif" als eigenständiges Diagramm. Der Standard ist die
**sortier- und filterbare Ergebnisliste** mit EINER gerechneten Leitzahl —
überall „Ø pro Monat = (alle einmaligen + monatlichen Kosten über 24 Monate −
Boni) ÷ 24" — plus einem 3–4-Sätze-Rechenschaftssatz direkt über der Liste
(Check24) und je Zeile einem Beleg-Link. Modellauswahl läuft bei allen über
Kacheln/Dialoge (nicht Tippen — Antonios Suchfeld-Forderung schlägt die
Recherche hier vor; der Radar-Katalog ist mit ~60–90 Modellen klein genug, um
BEIDES zu tragen: Suchfeld als Hauptweg + 4–6 Kacheln der häufigsten Geräte
als Nebeneingang, §9). Verfügbarkeit ist überall Filter plus stiller
Ausschluss — der Radar als Beobachter zeigt die Lücke als Zeile statt sie
verschwinden zu lassen. Apple beweist die kompakte Matrix (Anbieter × Modell,
eine Zahl je Zelle) als „auf Anhieb"-Form — das ist auf der EINEN Seite die
Radar-Tafel (flache Abweichungstabelle).

**Empfehlung: die Ergebnisliste ist die Antwort, kein eigenständiger Graph.**
Die Vergleichsansicht ersetzt den Balkengraphen durch die Liste aus §1. Die
einzige grafische Form, die bleibt, ist das **Inline-Längenband in der
Anbieterzeile** (ein schmaler horizontaler Balken unter/neben der gedruckten
Zahl): es erhält die „auf einen Blick"-Vergleichbarkeit, die Antonio will
(„einen Graphen, der sich an die Auswahl anpasst" — das Band skaliert mit
Band/Modell), ohne ein abstraktes Obergeschoss zu bauen, das keine Zeile
verlinkt. Das ist streng genommen ein „besser gemachter Balken" — aber als
Element DER ZEILE, in der die Zahl führt und der Beleg liegt, nicht als
eigenes Diagramm, über dem nichts klickbar ist. Genau das trennt es von dem,
was Antonio sah: sein Balken trug keine Links, nannte Fehlende nur en bloc in
einer Legende und war die einzige Zahl-Darstellung ohne Rechenschaft.

**Entscheidungsregel, ob eine Graph-Form (auch künftig, z. B. P5) zulässig
ist — alle fünf Bedingungen, keine Auswahl:**
1. **Die Leitzahl steht gedruckt am Element** (kein Wert nur im Tooltip —
   Touch hat kein Hover; das war O1-Lehre und gilt weiter).
2. **Jede visuelle Einheit trägt ihren Beleg-Link** (Balkenzeile/Punkt/Kante
   verlinkt das erhobene Angebot oder ankert ihre Zeile).
3. **Fehlende Werte erscheinen als benannte Zeilen**, nie als Stille oder
   Sammel-Legende.
4. **Keine Interaktion nötig**, um die Leitfrage zu beantworten; mobil ohne
   Querscroll (11c-Mechanik).
5. **Der Graph ergänzt die Liste, er ersetzt sie nicht** — die Liste ist
   immer zuerst lesbar, der Graph kommt in/unter derselben Zeile.

Was nach dieser Regel **verworfen** ist: der eigenständige Balkengraph als
Antwort-Obergeschoss (fällt durch 2 und 5), reine SVG-Scatterplots mit
Tooltip-Werten (fällt durch 1), jede Matrix mit „…"-Zellen (fällt durch 3).
Was zulässig bleibt: Inline-Bänder in Zeilen (E2), die flache Abweichungs-
tabelle mit Δ-Sparkline (E3, optional), und die P5-TCO-Zeitachse, sobald sie
diese fünf Regeln erfüllt (bewusst NICHT jetzt, §8).

**Zwei-Zahlen-Muster (Telekom/o2, R1 §6):** jede Zeile nennt „monatlich X € +
einmalig Y €" — der kleinste gemeinsame Nenner des Marktes. Ø €/Monat führt,
das Muster folgt, der Rechenweg-Aufklapper (O2, bleibt) vertieft.

**„Mittlerer Tarif" = GB-Stufe (R1 §5):** die Bänder tragen ihre GB-Spanne
aus dem Bestand („Mittel · 20–49 GB"); Voreinstellung = Median-GB des
Bestands, umschaltbar. Das ist die einzige Übersetzung von Antonios Wort
„mittlerer Tarif", die der Markt kennt.

---

## 5. Auto-Erkennung (F-D) — Empfehlung, Sicherheitsregeln, Sichtbarkeit

**Empfehlung: Option b + Persistenz aus c** (ausführlich in E4; Begründung
R1/R3-Kurzform): Die Live-Kataloge der Anbieter liefern täglich strukturierte,
kanonische Modellnamen inklusive Speicher und Farbe — Telekom lieferte
„Apple iPhone 18 Pro 256 GB polar" am 15.09. und der Radar warf es weg. Die
Auto-Anlage aus genau diesen Namen wiederholt den einzigen Vorgang, mit dem
der Katalog ohnehin wuchs (29.08.: 37 Einträge aus Live-Katalogen abgelesen,
Trefferquote 84 %) — ohne den Ables-Schritt. Option a (Titel-Heuristik) ist
verworfen: 80 % der Geräte werden in mehreren Titelschreibweisen geführt, der
erste gesehene Titel fixierte eine wackelnde ID — die eine Falle, gegen die
`geraete_model` gebaut ist. Option c allein ist der Status quo, der gerade
fehlgeschlagen hat (Protokoll-Zeile statt Ticket, Katalog 16 Tage ungepflegt
mitten im Launch-Fenster).

**Wie ein neues Modell HEUTE unsichtbar bleibt vs. nach E4:**

| Station | Heute | Nach E4 |
|---|---|---|
| Collector liefert strukturiert | ja (15.09. bewiesen) | ja |
| `erkenne_geraet()` | None → Rohsatz verworfen | None → Kandidat für Auto-Anlage |
| Protokoll | eine Log-Zeile, 90 Tage Retention | `geraete_unbekannt.jsonl` + Log |
| Katalog | wartet auf Handpflege | Eintrag automatisch (Marker `auto:`) |
| `geraete_db.json` | keine Listung | Listung + Launch-Preispunkt sofort |
| UI sichtbar | nie | ab 2 Messtagen in Suchfeld-Vorschau und Liste |
| Bündel-Zuordnung | „ohne-geraet" | über die angelegte Katalog-ID |

**Marktstart bleibt grundsätzlich null, bis belegt** (Katalogkopf-Regel: ein
geratenes Datum ist schlimmer als ein fehlendes; VERKAUFS- nicht Vorstellungs-
tag). Die Presse-Brücke (Highlight-Thema „iPhone-18-Event" → marktstart-
Beleg) ist eine spätere, eigene Entscheidung — hier nur als Idee notiert (§9).

**Tarif-Seite:** Kachel-/ldjson-Anbieter sind bereits vollautomatisch (24
`live_shop`-Sätze); einzige harte Liste ist die Telekom-Dokument-Slugliste
(Untermessung in E4: Muster statt Liste, wenn der `max_dokumente`-Deckel
hält; sonst bewusst offen). Das Geräte-Äquivalent der Slugliste war der
Katalog — E4 schließt genau diese Lücke.

---

## 6. Höhen- und Falz-Budget (aus R2, in Ziel-Höhen übersetzt)

**IST (R2, ausgelieferte Seiten).** `geraete.html` Default 2.844/3.820 px
(1440/390), Vergleichstafel: Hero 258/227, Filter 70/68, Antwort 105/122,
Graph-Sektion 404/475, **Bündel-Sektion 873/1.256**, Glossar 377/807, Meta-
Aufklapper zugeklappt 78/232 (aufgeklappt 1.447/2.628). `wettbewerbsradar.
html` 10.425/20.398 px: Methoden-Intro im Hero 532/572 (davon ~260/~340
Intro-Text), Alarm-Sektion 1.361/2.145, **88 TCO-Gruppen 5.416/11.244 (= 52/
55 % der Seite)**, Händler 935/2.121, Lifecycle 863/1.342, „Nicht erhebbar"
548/1.936. Zwischen Kopf und erster Balkenzeile auf geraete.html stehen heute
0 Aufklapper, aber ~600/640 px Meta vor der ersten Zahl — das ist Antonios
„erst runterscrollen" (gefühlt, weil Nav+Hero+Tabs+Filter+Antwort den Graph
an die Falzkante drücken; 1&1-Zeile angeschnitten).

**Was wegfällt (F-A), mit Messwert:** Glossar 377/807 px → **0** (gelöscht,
nicht verklappt — Antonio: „weg"). „Wie gerechnet?"-Block 26 zugeklappt →
**ersetzt durch einen 2-zeiligen Rechenschaftssatz (~48/72 px)** direkt über
der Liste. Massstab- und Datenlage-Aufklapper (52/132 zugeklappt) → **ein**
Fuß-Aufklapper „Maßstab & Datenlage" 26/79. Intro-Satz mit Schwesterseiten-
Link (Teil des Heros) → 0 (die Schwesterseite stirbt mit E3). Auf
wettbewerbsradar: Methoden-Intro ~260/340 px → 1 Satz + Fuß-Aufklapper; je
Sektion Erklärabsätze → 0 (Überschrift + Spaltenköpfe tragen die Aussage).

**Vergleichstafel Ziel-Budget (1440/390) — neu gerechnet (Revision 16.09.).**
Die frühere Summenzeile („≈ 1.850–2.100 / 2.700–2.950 px") passte nicht zur
Teilesumme der eigenen Liste (906/1.333 px) und wies fehlende Poste nicht
aus; ihre Einzelwerte (Vorlauf 834 px auf 390) rissen zudem die 11c-Falz-
Grenze rechnerisch. Korrigierte Aufstellung mit Falz-Nachweis:

| Posten | Ziel 1440 | Ziel 390 | Bemerkung |
|---|---|---|---|
| Nav | 118 | 226 | unverändert |
| Kopf (H1/Datum/Export-EINE-Zeile) | 120 | 150 | Untertitel weg (O1/O4-Präzedenz) |
| Tab-Leiste | 44 | 76 | |
| Suchfeld/Band | 110 | 120 | |
| Antwort-Band + Rechenschaftssatz | 128 | 100 | EIN Block, 2-zeilig |
| **Vorlauf bis Zeilenbeginn** | **520** | **672** | **Grenze 770 — geht auf** |
| Ergebnisliste 5–7 Zeilen à 60/70 | 360 | 420 | |
| Lücken-Zeilen (2–3 à Zeilenhöhe) | 140 | 160 | zählen zur Liste |
| Fuß-Aufklapper „Maßstab & Datenlage" | 26 | 79 | |
| Footer/Padding | 370 | 600 | (Analogie zur Radartafel-Zeile) |
| **Summe Vorgabestand** | **≈ 1.420** | **≈ 1.930** | **11b mit Luft** |

Damit ist 11c VORGERECHNET erfüllbar: 672 px Vorlauf + ~70 px erste Zeile
endet bei ~742 ≤ 844 px. Diese Rechnung ist E1-Abnahme („390-Falz-
Summenrechnung der Vergleichsansicht"); bei Riss entscheidet der ENTWURF
(Nav-Kompaktmodus, Antwort+Rechenschaft als EIN Block — eingerechnet —,
Export-Knöpfe mobil unter die Falz), nie der Bau. Die Luft zu 11b (3.000)
braucht P5 (ein Slot, ein Graph) später. Die Anbieterzeilen sind zugeklappt
expandierbar (Bündelzeilen darunter, O3-Lazy-Fragment); aufgeklappt wächst
die Seite, das ist eine Nutzerhandlung, kein Vorgabestand (11b misst den
Vorgabestand — so bleibt es).

**Radartafel Ziel-Budget (1440/390), Herleitung aus den IST-Blöcken:**

| Sektion | IST 1440/390 | Stellschraube | Ziel 1440/390 |
|---|---|---|---|
| Kopf (H1 + 1 Satz + Export) | 532/572 | Intro → 1 Satz, Knöpfe eine Zeile | ~180/260 |
| Preis-Alarme | 1.361/2.145 | bleibt (12 sichtbare Zeilen, Deckel besteht), Erklärabsatz weg | ~1.150/1.900 |
| TCO-Abweichung | 5.416/11.244 | 88 Gruppen → flache Tabelle, 12 sichtbar + Aufklapper | ~700/1.100 |
| Händler-Barpreis | 935/2.121 | Deckel 12 + Aufklapper (besteht) | ~600/1.000 |
| Bei Wettbewerbern gelistet | 187/287 | bleibt (zugeklappt) | 187/287 |
| Wochenkarte | 26/53 | bleibt (Summary) | 26/53 |
| Lifecycle | 863/1.342 | LIFECYCLE_SICHTBAR=6-Deckel (besteht) + Aufklapper | ~450/700 |
| Nicht erhebbar | 548/1.936 | zugeklappter Aufklapper | 26/79 |
| Nav/Footer/Padding | ~370/~600 | — | ~370/~600 |
| **Summe der Zielwerte** | 10.425/20.398 | | **≈ 3.690/4.980 → reißt 11b mobil** |

**Neu gerechnet (Revision 16.09.).** Die frühere Summenzeile behauptete
„≈ 3.700/6.000", während die eigenen Teilwerte mobil nur 4.980 ergeben —
und die Nachbesser-Regel (Lifecycle UND Händler default-zugeklappt,
Alarm-Filterzeile mobil zu) brachte mobil nur ~4.440 px. Es fehlten ~1.500
px zur 11b-Grenze (≤ 2.950), zu erreichen nur durch Inhaltslöschung oder
Deckelung nach Gefühl — beides verbietet dieser Plan selbst. Deshalb ist die
**mobile Alarm-Sektion selbst Stellschraube** (vom Clean-Code- und vom
Deckungs-Prüfer gefordert, vor E1 entschieden, nicht im Bau):

| Stellschraube (mobil 390) | vorher | nachher |
|---|---|---|
| Lifecycle default-zugeklappt | 700 | 79 |
| Händler default-zugeklappt | 1.000 | 79 |
| Alarm-Sektion default-zugeklappt MIT Menge („alle 48 Alarme anzeigen") | 1.900 | 79 |
| Alarm-Filterzeile | in 1.900 enthalten | in denselben Aufklapper |

Mobile Summe danach: 260 (Kopf) + 79 (Alarme) + 1.100 (TCO-Abweichung) +
79 (Händler) + 287 (Wettbewerber-Listung) + 53 (Wochenkarte) + 79
(Lifecycle) + 79 (nicht erhebbar) + 600 (Nav/Footer) ≈ **2.620 ≤ 2.950** —
die Rechnung geht auf. Desktop (1440) bleibt die Alarm-Sektion OFFEN
(~1.150): 180 + 1.150 + 700 + 187 + 26 + 79 + 79 + 26 + 370 ≈ **2.800 ≤
2.900**. Der erste Entwurfswert der Radartafel ist OBERGRENZE. Fällt eine
Grenze am echten Bestand trotzdem: nächste Stellschraube ist die Zahl
sichtbarer Alarm-Zeilen mobil (12 → 8) — NIE Inhaltslöschung. **Keine neue
harte Grenze ohne Messung:** alle Deckel-Zahlen dieser Tabelle sind
Vorschläge, die an der echten Seite nachzumessen sind (11b misst ohnehin je
Tafel); ein Deckel, der erst im Bau gemessen wird, bekommt seinen Wert aus
der Messung dokumentiert im Code (Muster: `UEBERSICHT_MAX_ZEILEN`-
Berechnung mit Zeilenhöhe × Ist-Höhe, CLAUDE.md).

**11c neu gefasst** (Prüfung in `scripts/pruefe_portal.py` mitziehen):
„Ergebnisfalz — auf 390×844 endet die **erste Anbieterzeile** der Ergebnis-
liste (`#tafel-vergleich` erste Zeile, Nachfolger von `.gr-bz`) bei ≤ 844 px;
zwischen Band-Wahl und erster Zeile steht kein `<details>` und kein Absatz;
die Seite ist nicht breiter als 390 px. Auf 1440×900 enden ≥ 2 Zeilen ≤ 900."
11b bleibt unverändert in der Mechanik (alle Tafeln < 3.000 px), bekommt aber
vier Tafeln statt drei als Pflichtmenge. Kriterium 11 (Alarmtabelle auffindbar)
zieht auf `geraete.html` um.

**Details-Zählregel (bleibt):** `<details>` über der Falz = 0 im Vorgabe-
zustand; gesamt im Hauptpfad der Vergleichstafel ≤ 8 (heute 12 sichtbare);
jeder Aufklapper muss MENGE tragen („alle 321 Paare anzeigen"), damit er
keine stillen Datenbank ist.

---

## 7. Prozess je Phase (fester Ablauf, kein Ermessen)

1. **Branch:** `claude/geraete-eineseite-<phase>` (E1..E6). Kein Bauen auf
   main; Merge erst nach grüner Abnahme.
2. **Rot-vor-grün zuerst:** die in der Phase benannten Tests werden ZUERST
   geschrieben und müssen am unangetasteten Stand fallen (Kontrolle gegen den
   Fixture-Fall: „prüfe im selben Test, dass der Fall ohne die Zusicherung
   wirklich eintritt"). Erst dann bauen.
3. **Kleine Commits, sobald grün** — zwei Agenten sind schon an API-Limits
   gestorben; uncommittet ist verloren. Commit-Hygiene: **kein `data/state`-,
   kein `data/reports`-Commit**; `site/` nur als EIN eigener „Seite neu
   gebaut"-Kommitt am Phasenende (Muster `bd3fbde`); der nächtliche Bot-Commit
   heilt live, sobald gemergt.
4. **Komplette Suite je Phasenende:** `pytest -q` (3054/3/14 ist die Basis;
   die 3 Roten sind vorbestehend und bleiben unangetastet) +
   `scripts/pruefe_portal.py` (17/1, nur 8b vorbestehend) mit 11/11b/11c in
   der je Phase gültigen Fassung (E2 ändert 11c, E3 ändert 11-Quelle und
   erweitert 11b auf vier Tafeln).
5. **Abnahme durch UNBETEILIGTE Agenten** (Antonios Regel, wörtlich): ein
   Screenshot-Agent mit frischem Kontext (nichts gebaut, bekommt nur die URL
   und die fünf Sichttest-Fragen) bewertet Verständlichkeit/Intuitivität;
   ein adversarieller Evaluator (bekommt die Begründung des Bauers NICHT)
   prüft gegen `docs/clean-code-referenz.md` (S1/S2 einzeln, S3/S4 gebündelt),
   die CLAUDE.md-Fallstricke des berührten Codes und beantwortet die
   **Premortem-Frage**: „Angenommen, in zwölf Monaten nutzt niemand die
   Geräteseite mehr — welche der heutigen Entscheidungen war die Ursache?"
   Berichte nach `/tmp/geraete-eineseite/<phase>/`.
6. **Screenshots SELBST ansehen** (1440+390, Falz-Overlay) — die Bauende
   Instanz sieht jedes Ergebnis mit eigenen Augen, bevor der Evaluator kommt
   (Antonios „Hoffe, du hast das nicht gemacht, sonst hast du keine
   Urteilsfähigkeit"). Betriebs-Fallstricke aus dem Auftrag übernehmen:
   eigener http.server auf unüblichem Port mit Marker-Gegenprobe, eindeutige
   Screenshot-Marken (`--marke <phase-datum>`), jeder Stand als eigener
   subprocess mit SEINEM `PYTHONPATH`, Selektor nie allein auf `.gr-a-zeile`
   (mehrdeutig).
7. **Navigation/Tests mitziehen:** jede Phase, die Struktur ändert, zieht
   `tests/test_suche_page.py`, Redirect-Tests und alle grep-Treffer auf
   berührte Dateinamen mit (Liste in E3/E5).
8. **Push-Disziplin:** Push-Freigabe steht (15.09.); nach JEDEM Push den
   `deploy.yml`-Ausgang prüfen und live per md5/Inhalts-Marker gegenprüfen.
   Der Job `geraete.yml` committet site/ selbst — Hooks bleiben drin.

---

## 8. Bewusst NICHT gebaut (mit Grund)

- **P5 TCO-Zeitachse** (vom Auftrag abgespalten, eigener Termin): ersetzt ab
  ≥ 3 Messtagen eine Darstellung im selben Slot — ein Slot, ein Graph. Sie
  muss die fünf Graph-Regeln (§4) erfüllen; die Eine-Seite-Struktur hält den
  Slot frei (Luft in 11b, §6).
- **E-S2: 1&1 per Playwright** — Datenerhebung, nicht Darstellung; eigener
  Auftrag (robots- und Besuchszeitregeln des Geräteradars gelten).
- **Neue Anbieter/Adapter** (Telekom-Bündel-Vertiefung, otelo-Bündel etc.) —
  der Bestand trägt die Eine-Seite bereits; mehr Anbieter verbreitern, bevor
  die Form steht, vergrößert nur die Tafeln. Die Auto-Anlage (E4) ist der
  einzige Datenzuwachs dieser Strategie.
- **Nachrichtenseite / Presse-Integration** — anderes Terrain, andere Pipeline.
- **Titel-Heuristik als Auto-Anlage (Option a)** — widerspricht der
  nicht verhandelbaren ID-Regel; 80 % Mehrfachschreibweisen machen sie zum
  Sägezahn-Generator (§5).
- **Chatbot/„Sophie"-Suche wie Check24** — kein Backend, die Static Site ist
  die Bedingung dafür, dass sie nie einschläft; die ≤-8-Treffer-Vorschau
  leistet den Dienst ohne Dienst.
- **Externe Vergleichszahlen (Check24/Verivox als Datenquelle)** — Belegzwang:
  jede Zahl dieser Seite kommt aus eigenem Messlauf mit Abrufdatum; Fremdzahl
  wäre ein Fremdkörper im Bericht.
- **Eine Riesen-Matrix „alle Geräte × alle Anbieter" als Hauptansicht** — die
  Leitfrage ist EIN Gerät; die Matrixform ist als flache Radar-Tabelle (E3)
  genau dort, wo die Querfrage hingeört. In der Hauptansicht wäre sie Höhe
  ohne Frage.
- **Dark-Mode, Frameworks (React/Vue), CDN-JS** — Design-Regeln der Website
  (§5 CLAUDE.md): Vanilla JS, Zeitungsausgabe, kein CDN.
- **Zweite Such-Implementierung für die Katalogtafel** — dieselbe Komponente,
  zweiter Konsument (E5); zwei Implementierungen driften (JS-Falle).
- **Telekom-Dokument-Slugliste dynamisieren, falls der `max_dokumente`-Deckel
  dabei reißt** — erst messen (E4-Unteraufgabe); eine Sprengung des Deckels
  wäre ID-Enumeration auf dem Pflichtdokument-Pfad nahe (§ 87b-UrhG-Grenze
  des Tarif-Sammlers).
- **Zur Ausschlussliste der Auftragsdatei („Katalog-Erweiterungen sind NICHT
  Teil dieses Auftrags"):** der Ausschluss meinte die MANUELLE Bestands-
  Pflege von Hand; die AUTOMATISCHE Anlage (E4) ist durch Antonios F-D
  gedeckt und überschreibt ihn bewusst. Hier festgehalten, damit keine
  künftige Session den Wortlaut-Konflikt als „E4 auslassen" liest.

---

## 9. Über die Mindestbedingungen hinaus (Antonios Erwartung)

Zehn eigene Verbesserungen aus R1/R2, je eine Zeile; **[Bau]** = in der Phase
gebaut, **[Freigabe]** = Antonio vorschlagen (berührt sein Nutzungsmodell).

1. **[Bau, E2]** Check24-Kopf über der Liste: „N von M Anbietern führen es ·
   Ø X–Y €/Monat · TCO-24 ab Z €" — Anzahl + Spanne vor jeder Interaktion;
   M ist Bestandsstand (kein fester Wert), N/M und Spanne reine Ableitung
   aus den Zeilen (E2-Tests, siehe Antwort-Band-Baustein).
2. **[Bau, E2]** Messtermin je Zeile sichtbar („gemessen 15.09., nächtlich")
   — WhistleOut-Äquivalent, aber belegbar: der Vertrauensvorteil des Radars
   gegenüber jedem Vermittler.
3. **[Bau, E2]** Zwei-Zahlen-Muster „monatlich + einmalig" je Zeile — der
   kleinste gemeinsame Nenner des gesamten Marktes (Telekom/o2-Muster).
4. **[Bau, E2]** Daumenregel-Zeile nach Finanztip — als **belegte Beobachtung
   mit Quelle, kein Imperativ am Leser** („Finanztip-Rechnung als Maßstab:
   Gerät ÷ Laufzeit; Bündel darüber liegen bei N von M Modellen im Markt-
   schnitt" + Quellenangabe), mit 36-Monats-Hinweis; die Empfehlungsprüfung
   (`ohne_vodafone_rat`) bekommt einen Testfall dafür — ein Ratschlag fällt
   sonst erst im Bau auf, und die nachträgliche Satz-Streichung ist die
   teure Variante (Falldokument `_strip_vodafone_advice` löschte ganze
   Absätze).
5. **[Bau, E2]** Deep-Link je Modell zustandssicher (`?modell=` + Band in der
   URL) — jedes Gerät so teil- und bookmarkbar wie eine Check24-Geräteseite.
6. **[Bau, E3]** Sortierbare Abweichungstabelle (Δ % aufsteigend — stärkste
   Benachteiligung zuerst, UNVERÄNDERLICHE Vorgabe, kein Umschalter) mit
   Excel-freundlichem Export-Link daneben; die Rang-1-Zeile des Stores
   steht IMMER unter den sichtbaren Zeilen (rot-vor-grün in E3) — ein
   Deckel, der die stärkste Abweichung versteckt, widerlegt die
   Leseentscheidung des Radars.
7. **[Bau, E4]** Farb-Arbeitsliste persistiert (`geraete_unbekannt.jsonl`) —
   neue Farbschreibweisen (cream, frost …) sind heute genauso flüchtig wie
   unbekannte Titel; dieselbe Lücke, dieselbe Heilung.
8. **[Freigabe, E1]** 4–6 Kacheln der häufigsten Geräte neben dem Suchfeld
   (R1 §4: Kein Vorbild hat Tippen als Hauptweg — die Kacheln fangen die
   „ich weiß noch nicht genau was"-Frage ab, das Suchfeld die Kennenden).
   Antonio entscheidet das AKTIV in der E1-Freigabe (mit dem Entwurf
   vorgelegt), nicht erst in E2.
9. **[Freigabe, E5]** SIM-only-Gegenzeile je Modell („Gerät + Tarif getrennt:
   Ø X €/Monat" aus dem Massstab-Bestand) — Verivox' Kernempfehlung, und der
   Radar hat die Daten bereits erhoben; macht die Bündel-Ersparnis auf einen
   Blick sichtbar.
10. **[Freigabe, später]** Presse-Brücke: Highlight-Thema eines Launch-Events
    („iPhone-18-Event", `event_datum` + Keywords stehen bereits im Store) als
    Belegquelle für `marktstart` und als Vorschlags-Badge „gerade gelauncht"
    in der Vorschau — verbindet die zwei Systeme, die heute nichts
    voneinander wissen (R3 §6), und würde Antonios „wieso sehe ich nichts vom
    neuen iPhone" auf der Nachrichtenseite wie auf der Geräteseite lösen.

---

## 9a. Pre-Mortem-Risiken und ihre Gegenmaßnahmen

Pre-Mortem vom 16.09.2026 („Angenommen, in zwölf Monaten nutzt niemand die
Geräteseite mehr — welche der heutigen Entscheidungen war die Ursache?").
Jede Gegenmaßnahme steht zusätzlich in der betroffenen Phase; die Premortem-
Frage bleibt fester Bestandteil jedes Evaluator-Laufs (§7 Nr. 5).

| # | Risiko | Gegenmaßnahme (verankert in) |
|---|---|---|
| 1 | **Die Seite antwortet überwiegend mit Lücken statt Zahlen:** Telekom liefert kaum Bündel, 1&1 nur ohne Band, das Antwort-Band steht monatelang bei „4 von 7 Anbietern führen es" | Kopfzahl „N von M" je Modell × Band nächtlich ins Protokoll loggen und schwellenprüfen (> 14 Tage Lücke = LAUT); ein Dauer-Lücken-Fall wird zum DATEN-Auftrag (Adapter/Erhebung, bewusst außerhalb dieser Strategie, §8), nicht zur UI-Frage; Antonios Beispiel (Pixel 11 Pro × Telekom × Mittel) ist fester Live-Prüffall mit Datum des nächsten liefernden Tageslaufs (E2-Baustein „Lücken zur Kennzahl machen") |
| 2 | **Auto-Anlage erzeugt doppelte device_ids** (Live-Kataloge kanonisieren nicht über Anbieter hinweg: „iPhone 19 Pro 5G" vs. „iPhone 19 Pro") — Sägezahn-Kurven, manuelles Aufräumen, dann still Abschaltung | Konsistenz-Check je Nacht gegen die Live-Namen BEIDER Quellen, LAUTE Protokoll-Meldung bei Doppel-ID statt stiller Weiterlauf; Reproduktion des 15.09.-Falls („Apple iPhone 18 Pro 256 GB polar" → genau ein Eintrag) bleibt dauerhafter Regressionstest; die 2-Messtage-Schwelle schließt erst die UI ab, wenn die IDs stimmen (E4-Sicherheitsregeln) |
| 3 | **Das „auf Anhieb" zerbricht am wachsenden Bestand:** 11c und der Sichttest werden nur bei E1/E2 gemessen; danach wächst der Katalog durch E4 und die erste Zahl rutscht unter die Falz, ohne dass ein Dauer-Kriterium läuft | 11c zum Dauerkriterium: der nächtliche `geraete.yml`-Job misst die Ergebnisfalz am ECHTEN Bestand und meldet Riss als FEHLER; die fünf Sichttest-Fragen als Browser-Tests am echten Stand und monatlich live beantwortet (E2-Abnahme, §10-Betriebsmodus) |
| 4 | **Die Höhen-Deckel der Radar-Tafel verstecken die stärkste Abweichung:** ohne strikte Δ-%-Sortierung steht die größte Benachteiligung auf Rang 13+ hinter dem Aufklapper, Sichttest-Frage 5 wird mit den falschen zwölf Zeilen beantwortet | Δ-%-Sortierung aufsteigend als unveränderliche Vorgabe (§9 Nr. 6) plus rot-vor-grün, dass die Rang-1-Zeile des Stores IMMER unter den sichtbaren Zeilen steht (Lookup-Längen-Assert gegen den Store); Deckelwerte nur aus Messung im Code dokumentiert (E3) |
| 5 | **Ein Baustein zerbricht am nächsten Datenstand und niemand merkt es:** Adapter liefert null Sätze, Bot-Commit rendert Leerzustände, Suite bleibt grün (Fixtures), die leere Tafel steht wochenlang live | Die fünf Test-Leer-Sicherungen (O4-Evaluator) in E5 WIRKLICH einbauen + Substanz-Wächter im Renderpfad: Zeilenzahl je Tafel gegen den Store abgleichen, bei Abweichung Befund LAUT auf Seite und Protokoll („gescheitert" vs. „gab es nicht") — kein stiller Bot-Commit eines Leerzustands (E5-Bausteine) |
| 6 | **Die EINE Seite wird zu schwer und zur Aufklapper-Wüste:** vier Tafeln auf einer URL, Gewicht wächst mit dem Katalog, Höhen-Deckel verlagern Inhalt in Aufklapper — die Seite hält jede Grenze und ist faktisch ein Tunnel | Lazy-Nachladen nach dem Bündel-Fragment-Muster für ALLE Neben-Tafeln (erst bei Tab-Wechsel); Gewicht der gerenderten `geraete.html` als Messzahl mit Obergrenze im nächtlichen Protokoll; E1-Höhen-Wireframe mit (nun aufgehender) Summenrechnung VOR dem Bau einhalten; Nachbesser-Regel „zuklappen statt löschen" vorher festgezurrt (E3-Baustein „Gewicht und Lazy", §6) |
| 7 | **Die Suchfeld-Vorschau zeigt Auslaufware statt aktueller Geräte:** bei 90 Treffern füllen alte Modelle die ≤ 8 Plätze, „iphone" zeigt acht Auslaufgeräte — genau das geforderte Suchfeld wird zum Ärgernis | Vorschau deterministisch sortieren: Modelle mit aktuellen Listungen und größerer Bandabdeckung zuerst, Auslaufware ans Ende (der Index führt beide Daten); die 4–6 Kacheln der häufigsten Geräte Antonio in der E1-Freigabe AKTIV zur Entscheidung vorlegen — der Kachel-Eingang fängt die „ich weiß noch nicht genau was"-Frage (E2-Baustein, §9 Nr. 8) |
| 8 | **Die Wartung stirbt mit dem Agenten-Orchestrierungsprozess:** nach E6 enden Bau UND Prüfungen; der Betrieb hält die Daten frisch, aber niemand sieht sie an — Adapter rosten still, der Umsetzungsstand veraltet | Betriebsmodus ohne Agenten in §10 verankert: monatlich die fünf Sichttest-Fragen live beantworten plus drei Protokollzeilen lesen (Kataloggröße, Bestand, Auto-Anlage — alle drei bereits geloggt); jede Phase so abschließen, dass eine fremde Session mit Strategie-Doc + CLAUDE.md allein weiterarbeiten kann; Premortem-Frage bleibt fester Teil jedes Evaluator-Laufs (E6, §7) |

---

## 10. Umsetzungsstand

(noch nichts gebaut — E1 ist der erste Auftrag. Nach jeder Phase hier eine
Zeile: Phase, Merge-Commit, Messwerte pytest/pruefe_portal/11b/11c, Evaluator-
Urteil, offene Reste. Ab E6 zusätzlich festgehalten: der **Betriebsmodus ohne
Agenten-Orchestrierung** — monatlich die fünf Sichttest-Fragen live
beantworten (Antonios Beispiel Pixel 11 Pro × Telekom × Band Mittel ist
dauerhaft einer davon) und drei Protokollzeilen lesen: Kataloggröße, Bestand,
Auto-Anlage; alle drei werden bereits geloggt. Wer nur diese Handgriffe macht,
merkt, wenn ein Adapter rostet — dafür braucht es keine Session.)

---

## Änderungsprotokoll (Revision, 2026-09-16)

Nach drei Prüfberichten überarbeitet: Clean-Code-Prüfer (BESTANDEN MIT
AUFLAGEN), Deckungs-Prüfer (BESTANDEN MIT AUFLAGEN), Pre-Mortem. Kein
S1/S2-Befund abgelehnt; S3/S4 nach Ermessen eingearbeitet.

| ID | Befund (Kurz) | Was geändert | Wo |
|---|---|---|---|
| CC-S1 | Persistenz `geraete_unbekannt.jsonl` widerspricht Commit-Regel; E4-Abnahme strukturell nicht erfüllbar | Stand-Commit in `geraete.yml` um die Datei als FÜNFTE erweitert; Katalog-Commit weiterhin nur `config/geraete_katalog.yaml`; Abnahme an der COMMITTETEN Datei | E4-Baustein + E4-Abnahme |
| CC-S2a | Radartafel mobil: Ziel-Höhenrechnung ging nicht auf (≈ 6.000 statt 4.980 Teilesumme; Nachbesserung nur ~4.440 px) | §6 neu gerechnet: mobile Alarm-Sektion selbst Stellschraube (default-zugeklappt MIT Menge), Summen 2.620 (390) / 2.800 (1440) — geht auf; E1/E3 verweisen auf die neue Rechnung | §6, E1-Abnahme, E3-Risiko (a) |
| CC-S2b / DP-S3 | Falz-Vorrechnung der Vergleichsansicht fehlte (11c mit alten Einzelwerten unerreichbar: 904 > 844) | E1-Abnahme um „390-Falz-Summenrechnung der Vergleichsansicht" ergänzt (≤ 770 px Vorlauf, Aufstellung je Element); §6-Vergleichstafel mit korrigierter Posten-Tabelle und Falz-Nachweis (672 + 70 = 742 ≤ 844); Summenzeile korrigiert (≈ 1.420/1.930 statt 1.850–2.100/2.700–2.950) | E1-Baustein/Abnahme, E2-Risiko (a), §6 |
| CC-S2c | Antwort-Band: die drei prominentesten Zahlen ohne Wahrheitstest und ohne „eine Quelle"-Regel; die „7" ein Bestandsstand | Ableitungsregel als Baustein (Band rechnet selbst nichts, M aus dem Bestand); zwei rot-vor-grün-Tests; §1-Formulierung ergänzt | §1, E2-Baustein/Abnahme/Tests, §9 Nr. 1 |
| CC-S2d | Anlage-Schwelle widersprüchlich („zwei Anbieter" gegen Ein-Anbieter-Anlage) | EINEN Regel gesetzt: Anlage ab erstem strukturierten Satz (Launch-Preishistorie), Sichtbarkeit ab 2 Messtagen; „zwei Anbieter" gestrichen, als gegenteilige Option mit eigenem Testfall (`test_ein_anbieter_legt_noch_nicht_an`) ausformuliert — Antonio entscheidet | E4-Ziel |
| CC-S2e | `assert len(...) == 321` fixiert Ist-Stand (Datenbombe, kollidiert mit E4) | Assert gegen View-/Store-Bilanz formuliert; 321 gehört in den Abnahmetext | E3-Rot-vor-grün |
| CC-S3a | Suchindex-Schwelle „≥ 1 Listung" ohne Ort und ohne Test | `MINDESTLISTUNGEN_FUER_AUSWAHL = 1` als benannte Konstante im serverseitigen Modul (JS konsumiert nur) + rot-vor-grün-Test | E2-Baustein + Tests |
| CC-S3b | Auto-Anlage gegen Zubehör: Titel-Filter genügt strukturierten Namen nicht; Katalogkopf-Kommentar wird überholt | Negativliste für Nicht-Gerät-Kategorien als E4-Baustein; rot-vor-grün mit echtem strukturierten Zubehör-Namen aus dem Tageslauf; Katalogkopf-Umschreibung in E4 aufgenommen | E4-Baustein + Tests |
| CC-S3c | Freigabe-Klausel unscharf („nach Freigabeanfrage gilt der Stand") | Messbar gefasst: Freigabe = Antonios ausdrückliche Antwort (Zitat in §10); ohne Antwort keine src/-Bauten; Wartefrist nur als dokumentierte Regel | E1-Abnahme |
| CC-S3d | Daumenregel-Zeile ist eine Handlungsempfehlung — Verhältnis zu den Empfehlungsregeln ungeklärt | Als belegte Beobachtung mit Quelle festgelegt (kein Imperativ); Testfall in die Empfehlungsprüfung aufgenommen | E2-Baustein, §9 Nr. 4 |
| CC-S4a | Deep-Link-Band-Parameter ohne rot-vor-grün-Testnamen | `test_deeplink_setzt_modell_und_band_zurueck` ergänzt | E2-Tests |
| CC-S4b | 2-Messtage-Schwelle: Modulkonstante statt config als bewusste Entscheidung notieren | Als `SICHTBAR_AB_MESTAGEN = 2` mit Repo-Konventions-Begründung notiert | E4-Baustein |
| CC-S4c | „Palette durch den dataviz-Validator" ohne prüfbares Kriterium | Maßstab benannt: Kontrast ≥ 4,5:1 je Etikett-/Bandsorte, ≤ 12 Farbwerte | E1-Baustein |
| DP-S4a | „Unterkommentare ALLE weg" — drei begründete Reste nicht als Wortlaut-Abweichung gekennzeichnet | Drei Reste (Rechenschaftssatz, Fuß-Aufklapper, Rechenweg-Aufklapper) im E1-Entwurf ausdrücklich als Abweichung vom Wortlaut zur Freigabe gekennzeichnet | E1-Baustein + Abnahme |
| DP-S4b | Auftrag-Ausschluss „Katalog-Erweiterungen" vs. E4 unaufgelöst | Zeile in §8: Ausschluss meinte manuelle Bestands-Pflege; E4 überschreibt bewusst über Antonios F-D | §8 |
| DP-S4c | Navigationstest-Herkunft falsch („8er-Fassung") | Korrigiert: 5er-Fassung (`test_navigation_hat_fuenf_eintraege`, ohne cfg); Zieltest muss mit cfg beide Zustände halten | E3-Rot-vor-grün |
| PM-1 | Seite antwortet mit Lücken statt Zahlen | „Lücken zur Kennzahl machen": nächtliches Logging + Schwellenprüfung, Dauer-Lücke → DATEN-Auftrag; Antonios Beispiel als fester Live-Prüffall | §9a Nr. 1, E2-Baustein |
| PM-2 | Auto-Anlage erzeugt doppelte device_ids | Konsistenz-Check je Nacht gegen Live-Namen beider Quellen, LAUT bei Doppel-ID; 15.09.-Reproduktion als Dauer-Regressionstest | §9a Nr. 2, E4-Sicherheitsregeln + Tests |
| PM-3 | „Auf Anhieb" zerbricht am wachsenden Bestand | 11c als Dauerkriterium im nächtlichen Job (Riss = Fehler); Sichttest-Fragen als Browser-Tests am echten Stand | §9a Nr. 3, E2-Abnahme |
| PM-4 | Höhen-Deckel verstecken die stärkste Abweichung | Δ-%-Sortierung unveränderlich + `test_rang_eins_…_unter_den_sichtbaren_zeilen` | §9a Nr. 4, E3-Tests, §9 Nr. 6 |
| PM-5 | Baustein zerbricht am nächsten Datenstand, Suite bleibt grün | Fünf Leer-Sicherungen WIRKLICH einbauen + Substanz-Wächter im Renderpfad (Zeilenzahl == Store, „gescheitert" vs. „gab es nicht") | §9a Nr. 5, E5-Bausteine |
| PM-6 | EINE Seite zu schwer / Aufklapper-Wüste | Lazy-Nachladen aller Neben-Tafeln, Seitengewicht als Messzahl mit Obergrenze im Protokoll, Wireframe-Summen vor Bau | §9a Nr. 6, E3-Baustein „Gewicht und Lazy" |
| PM-7 | Vorschau zeigt Auslaufware statt aktueller Geräte | Deterministische Vorschau-Sortierung (aktuelle Listungen + Bandabdeckung zuerst); Kacheln Antonio in E1-Freigabe aktiv vorlegen | §9a Nr. 7, E2-Baustein + Test, §9 Nr. 8 |
| PM-8 | Wartung stirbt mit dem Orchestrierungsprozess | Betriebsmodus ohne Agenten definiert (fünf Sichttest-Fragen live + drei Protokollzeilen) und in §10 verankert | §9a Nr. 8, E6-Abnahme, §10 |
