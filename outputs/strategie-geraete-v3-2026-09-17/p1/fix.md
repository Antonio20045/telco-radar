# P1 — Fix-Notiz (Sicht-FAILs + Code-S3), 17.09.2026 abends

Fix-Agent der Phase P1. Grundlage: `p1/pruefung-sicht.md` (F2-Auflagen,
F3-FAILs, Verbesserungsliste) und `p1/pruefung-code.md` (0×S1, 0×S2, 5×S3,
5×S4). Kein Commit, kein Push, nichts unter `data/state` geschrieben (nur
gelesen); `site/` einmal final gerendert (immer mit `cfg`) — Lead entscheidet
den Stand. `tmp_nachpruef/` konnte NICHT gelöscht werden (`rm` verweigert) —
stattdessen in `.gitignore` aufgenommen (der zweite Weg des Prüfers; wirksam:
`git status` zeigt es nicht mehr).

## Je Befund: getan ODER Lead-Entscheidung

### Sicht F2-Auflagen

| Befund | Was getan |
|---|---|
| **A1 Karten-Preis öffnet keinen Rechenweg** | **GEBAUT — dritter Eingang.** Klick auf die Karten-Preiszahl bestellt Modell UND Band und hinterlässt einen Wunsch (`zrOeffneNach`), den der geladene Block bedient: Panel mit dem Rechenweg des Anbieters am `data-anb` des Band-Körpers (Serverangabe), letzter Messtag der Serie. Fremde Karte: wählt + öffnet (Wunsch überlebt den async. Ladevorgang; wird bei jedem anderen `waehle()` und im Fragment-Fehlerfall verworfen). Aktive Karte: öffnet direkt. Ohne Anbieter („—“) bleibt der gewöhnliche Wahl-Klick. Hover: gepunktete rote Unterstreichung NUR an der aktiven Karte mit Anbieter (CSS hängt an `[data-anb]`). 2 Browser-Tests, beide Wege |
| **A2 Panel „nur Zeilen“ auf toter Halbleite** | **GEBAUT — (a)+(b).** Panel auf 780 px begrenzt (Quittungsformat) UND je Postenzeile ein proportionale Balken (`width` = Anteil an `gesamt`, fertige Prozentangabe aus `_rechung_html`, Browser setzt nur ein). Gemessen an der echten Site: Rechnung 750 px in 780-px-Panel, 4 Balken; Screenshot `fix-vergleich-panel-1440.png` |
| **A3 Restschuld fehlt** | **GEBAUT.** Eigene Zeile „danach noch offen: 12 × 30,50 € = 366,00 €“ unter der Summe — serverseitig aus der Historie (`Rate × (Laufzeit−24)`, beide Preisformen; bei 24 Monaten keine Zeile). Klammer „24 von 36 Raten“ 11→13 px, „TCO-24“-Label 11→12 px (zugleich Code-S3-1). Nachgerechnet in Tests (o2 12×19,00=228,00; 1&1 12×49,99=599,88) |
| **A4 o2 in keiner Zeitreihe klickbar** | **LEAD-ENTSCHEIDUNG** (Messwerte unten, Abschnitt „Lead“) |
| **A5 Mobil: Belegzeile klebt an der Kante** | **GEBAUT.** `padding-bottom:12px` am Panel + `scrollIntoView(block:'nearest')` auf das PANEL (nicht die Rechnung — nur die Panel-Box trägt das Padding). Gemessen: belegBottom 832 statt 844, **12 px Luft** |

### Sicht F3-FAILs

| Befund | Was getan |
|---|---|
| **B1 Mobil: 6 Karten im Viewport verfehlt** | **LEAD-ENTSCHEIDUNG** (Messwerte unten — 11c und die Messlatte schließen einander bei dieser Blockfolge aus) |
| **B2 Karten reagieren nicht auf Bandwechsel** | **GEBAUT — bandgekoppelt.** Jede Karte trägt JE BAND eigene Spans (ab-Preis + Ø/Monat + Delta + Anbieter-Punkte, alles aus DEM Band — zugleich Code-S3-4 „ein Maßstab“); `setzeKartenBand()` blendet nur um (hidden, reine Attributmontage, Initial + Deep-Link + jeder `waehle()`). Band ohne echtes Angebot: „—“ mit Titel; Modell ohne das Band: Ersatz-Span „—“ (`data-band="__ohne"`), statt leer zu stehen. Browser-Test: Preis wechselt mit dem Band, Bandlage = gewähltes Band |
| **B3 Zu flach / aktive Markierung schwach** | **GEBAUT.** Aktive Karte: roter 3-px-Umriss (`var(--red)`) + Fläche `paper-2` (gemessen: `3px rgb(230,0,0)`); Hover/Focus: Unterstreichung des Modellnamens; Anbieter-Punkte 8→**10 px + 1 px Weißrand** |
| **B4 Bewegungs-Delta flüstert** | **GEBAUT.** steigt/sinkt: 13,5 px / Gewicht 700 farbig (rot/grün, gemessen `13.5px 700`); „±0 €“ bleibt grau 12 px. 11c rutschte um 2 px (846) → Karten-Paddings mobil um denselben Betrag gestrafft → **805/834 von 844** (Test + pruefe_portal grün) |

### Verbesserungsliste (klein + im Scope)

| Nr. | Was |
|---|---|
| 1–3, 5 (= A1–A3, A5) | gebaut (s. o.) |
| 4 (= A4), 6 (= B1) | Lead-Entscheidung (s. u.) |
| 7–10 (= B2–B4) | gebaut (s. o.) |
| 11 Hover-Vorschau | **gebaut:** `<title>` am Hit-Kreis („o2 · 12.9. · 893 €“, nativer Tooltip, fertige Zeichenkette vom Server); Test |
| 12 Panel-Titel-Farbpunkt | **gebaut:** 10-px-Punkt in ANB_FARBE im Kopf (congstar → gelb, gemessen); Test |
| 13 Belegzeile rechts, × ≥ 28 px | Belegzeile rechtsbündig (gebaut); ×-Knopf war bereits 30/32 px — erfüllt, nichts geändert |
| 14 Tab-Stops zum Punkt | **nicht gebaut** (Begründung: ein globaler Tab-Fluss-Umbau (Punkte vor Suchfeld/Bänder/Karten) ist riskanter als der Nutzen; Punkte sind fokussierbar + Enter-fähig; Reihenfolge folgt der Lesereihenfolge) |
| 15 Einzelmesstag „erstmals gemessen“ | **gebaut:** Halo-Ring (r=9,5, Anbieterfarbe) um Punkte einmessiger Serien + „· erstmals gemessen“ im title; verschwindet mit dem 2. Messtag (Test prüft beides) |

### Code-S3 (S1/S2: keine)

| Befund | Was getan |
|---|---|
| **S3-1 Panel-Schrift 11 px** | beide Klassen angehoben (13/12 px) + NEUER Browser-Test misst im GEÖFFNETEN Panel (die statischen Tests sahen Template-Inhalte nie) |
| **S3-2 Näherungs-Fallback für fremde Messungen** | Näherung nur noch bei `anb === 'Vodafone'`; fremde Punkte ohne Vorlage bekommen den ehrlichen Leer-Hinweis. Browser-Test mit Fehlerinjektion (alle o2-Templates aus dem DOM entfernt → Klick → Leer-Hinweis, NICHT „Referenzrechnung“) |
| **S3-3 Preiszahl bedingungslos klickbar** | Klasse/title/tabindex nur, wenn der genannte Anbieter Vorlagen hat — und werden beim Blockwechsel jetzt auch WEGGENOMMEN. Randfall (Satz-Anbieter ohne jede Vorlage) in der Fixture nicht konstruierbar; das stumme Klicken ist ohnehin durch S3-2 (Leer-Hinweis als Antwort) geschlossen |
| **S3-4 Karte mit zwei Maßstäben** | gelöst durch B2: ab-Preis, Delta und Punkte kommen JEDES aus demselben Band |
| **S3-5 tmp_nachpruef/** | Löschen verweigert (Berechtigung) → `.gitignore`-Eintrag mit Begründung; `git status` zeigt es nicht mehr |

### Code-S4: bewusst nicht angefasst (Closure-Args, Modulgröße, U+2212/ASCII,
Rundung) — keine Korrektheitsfragen.

## Messzahlen (alles nachgemessen)

- **Suite:** `pytest -k geraete` = **1413 passed / 3 failed / 6 skipped**
  (vor dem Fix 1402/3/6; +11 Tests von mir). Die 3 Roten sind EXAKT die
  vorbestehenden aus der Code-Prüfung (Galaxy-Tab-Auto-Datenstand,
  Nachtlauf-Lifecycle, iPhone-18-`AUTO_SICHTBAR` = P5 Auftrag 1) — keine
  neuen. `test_seiten_zahlen.py`: **97 passed**.
- **pruefe_portal.py: 18 bestanden / 0 durchgefallen / 0 n. p.**
  — 11b Reiterhöhen tco 2593 / radar 2997 / verlauf 1779 / katalog 1941;
  **11c: Antwort 805 px, Graphkopf 834 px (Falz 844)**.
- **Messlatte Desktop 1440:** 6 Karten in EINER Reihe (Ende 632 < 900),
  Preis 21 px, aktive Karte 3 px rot, Delta 13,5 px/700, Punkte 10 px+1 px.
- **Mobil 390:** kein Querscroll (390), Karten 608–703 (Wischreihe),
  Panel-Antipp messbar, Belegzeile 12 px über der Unterkante.
- **Fragmentgröße** `geraete-zeitreihe.html`: 2.968.207 → **3.555.755 B**
  (**+587.548 B / +19,8 %**; Balken, Restschuld, title, Farbpunkt je 1285
  Blöcke); **gzip 124.568 → 161.707 B (+37.139 B transportiert)**.
  PM-6-Deckel bleibt bewusst P5 — aber die Lead-Entscheidung sollte mit
  dieser Zahl fallen (gesamt jetzt +2,42 MB über E2-Stand, Faktor ~16 über
  der Strategie-Erwartung).
- **Screenshots:** `p1/screenshots/fix-{vergleich-panel-1440,
  vergleich-band-gross-1440, vergleich-390, panel-mobil-390}.png`.

## Lead-Entscheidungen (mit Messwerten)

1. **A4 — o2 in den Zeitreihen der prominenten Modelle.** Nachgemessen am
   Bestand: o2 IST in **45 von ~300 Serien-Paaren** (gleichauf mit congstar),
   aber nur in **1 von 19 Paaren der 6 Karten-Modelle** (Z Fold8 × mittel) —
   o2 führt die Flaggschiffe schlicht nicht im kleinen/großen Band als
   Bündel. Die Prüfer-Erklärung „Unlimited → kein Band" trifft nur auf
   **8 von 72** o2-Bündeln zu. „Unlimited = kein Band" ist eine DATIERTE
   Bewusst-Entscheidung (`geraete_tco_band.band_von_gb`, §7 vom 05.09.,
   gilt für Bandkarten UND Bündel-Zeilen der ganzen Seite) — P1 darf sie
   nicht still für den Graphen kippen, sonst zeigte der Band-Knopf „Groß“
   im Graph andere Bündel als in den Zeilen darunter. Optionen für den
   Lead: (a) Unlimited→„Groß“ seitenweit (bewusste Regel-Änderung, berührt
   Bandkarten/Werteliste), (b) bandlose o2-Reihe mit eigenem Label (neuer
   Paar-Typ + Band-Auswahl-Logik), (c) akzeptieren (Datenlage).
2. **B1 — „alle 6 Karten im ersten Viewport bei 390“.** Gemessen: Karten
   608–703 px (eine Reihe, 95 px), Antwort-Ende 805, Graphkopf 834.
   Das vom Prüfer vorgeschlagene 2×3-Grid macht die Karten ~300 px hoch
   (3 Reihen à ~95 px + Lücken) → Karten-Ende ~910, Antwort (steht UNTER
   den Karten) ~**1005 ≫ 844** — es bricht 11c (harter Test +
   pruefe_portal). Messlatte und 11c schließen einander bei der heutigen
   Blockfolge (Steuerung → Karten → Antwort → Graph) aus. Optionen:
   (a) Messlatte mobil als „ohne Scroll-Berg erreichbar“ (heutige
   Wischreihe — A3s Deutung, die der Lead damals zuließ), (b) Karten mobil
   unter den Graph stellen, (c) Steuerblock mobil straffen (berührt P4
   Auftrag 3 — Export-Knöpfe aus dem Kopf) und dann neu messen.

## Geänderte Dateien

| Datei | Was |
|---|---|
| `src/telco_radar/report/geraete_zeitreihe.py` | `_rechung()`: Restschuld (`offen`); `_rechung_html()`: Farbpunkt, Posten-Balken (Anteil an gesamt), Restschuld-Zeile; `_svg()`: `<title>` am Hit-Kreis, Halo bei einmessigen Serien; `aufbereiten()`: `karten_baender` je (Modell, Band) statt best_je/leit_je; Kacheln tragen `baender` |
| `src/telco_radar/report/templates/geraete.html.j2` | Karten-Block: Band-Spans (Punkte je Band, Preis+Delta je Band, `data-anb`), „—“-Leerzustände, Ersatz-Span `__ohne` |
| `src/telco_radar/report/templates/app.js` | `zrOeffneNach`-Wunsch (Karten-Preis, bedient nach Fragment-Load, verworfen bei Fehler/neuer Wahl); `setzeKartenBand()`; Karten-Listener mit Preis-Pfad; S3-2 (Näherung nur Vodafone); S3-3 (bedingte Preiszahl-Ausstattung, gesetzt UND entfernt); A5 (scroll aufs Panel) |
| `src/telco_radar/report/templates/style.css` | Panel: max-width 780, Balken (`.gr-zr-pbar`), `.gr-zr-rpunkt`, `.gr-zr-roffen`, Beleg rechts, padding-bottom; Karten: Band-Spans + `[hidden]` (specificity-sicher), aktive Karte rot 3 px, Punkte 10 px+Rand, Delta 13,5/700, klickbarer Karten-Preis; `.gr-zr-halo`; Mobil-Straffung (11c) |
| `.gitignore` | `tmp_nachpruef/` (S3-5) |
| `tests/test_geraete_zeitreihe_rechenweg.py` | +5 Tests (Balken, Restschuld beider Formen + 24-Monats-Fall, Farbpunkt, 12-px-Regel, title/Halo ein- und dreimessig) |
| `tests/test_geraete_zeitreihe_ansicht.py` | Karten-Tests auf Band-Struktur umgestellt (+Band-mittel-Gegenprobe: congstar 961 €, 1 Punkt, Delta −5) |
| `tests/test_geraete_zeitreihe_seite.py` | Kartentest auf Band-Spans/Leerzustand |
| `tests/test_geraete_zeitreihe_panel_browser.py` | +5 Browser-Tests (Karten-Preis aktiv + fremd, Bandwechsel stellt Karten um, S3-2-Fehlerinjektion, 12-px im geöffneten Panel) |
| `tests/test_seiten_zahlen.py` | Kartenzahl-Tests auf `baender` |
| `site/` | finaler Render mit `cfg` (app.js/style.css byte-identisch mit templates/) |

## Sorgen

1. **Fragment +588 kB** (Zahlen oben) — PM-6/P5; Lead sollte beim Merge die
   Gesamtzahl (+2,42 MB über E2) kennen.
2. **S3-3-Randfall** (Satz-Anbieter ohne Vorlage) ist Code-fix, aber in der
   Fixture nicht konstruierbar — kein eigener Test, nur Kommentar + S3-2
   fängt das Verhalten.
3. **A4/B1** brauchen Lead-Entscheidungen (s. o.) — ohne sie bleibt der
   Sicht-Prüfer-Befund „o2-F2-Versprechen“ bzw. „mobil Messlatte“ offen.
4. Der Karten-Preis-Klick einer FREMDEN Karte öffnet das Panel erst nach
   dem Fragment-Load (~300–700 ms) — bewusst (kein Race), aber spürbar.
