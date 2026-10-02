# P1 — RE-CHECK-URTEIL (17.09.2026, abends)

Prüfer: Re-Check, frisch und hart. Methode: frischer `render_site`-Stand
(mit cfg, md5-Sync site/templates bestätigt), Server 127.0.0.1:8765,
Playwright/Chromium, echte Klicks/Taps an der ECHTEN Site (nicht Fixture),
1440×900 und 390×844. Suite + pruefe_portal gelaufen.

---

## 1. Sicht-FAILs aus pruefung-sicht.md — je Befund

| Befund | Messung (echte Site) | Urteil |
|---|---|---|
| **A1 Karten-Preis öffnet keinen Rechenweg** | Aktive Karte (iPhone 17 Pro · 256): Klick auf „1.093,00 €" → Panel „congstar · Messung vom 17. September 2026", Panel-Inhalt == Server-Template derselben Messung (`isEqualNode`-Norm), letzter Messtag der Serie. Fremde Karte (Z Fold8): wählt (aria-pressed true), URL `?modell=…&band=klein`, öffnet congstar/12.09., Panel == Template. Cursor pointer, Hover-Unterstreichung am Modellnamen | **BEHOBEN** |
| **A2 Panel „nur Zeilen" auf toter Halbleite** | Panel 780 px (Quittungsformat, rechts 532 px frei von 1440), je Postenzeile proportionaler Balken: Füllung trägt serverseitig `width:0.1%/0%/32.9%/67%` — nachgerechnet gegen congstar 17.09. (1,00/0,00/360,00/732,00 von 1.093,00 €): 0,09 %/0 %/32,94 %/66,97 % ✓. Browser setzt nur ein (keine Zahl entsteht im JS) | **BEHOBEN** |
| **A3 Restschuld fehlt** | Eigene Zeile unter der Summe: „danach noch offen: 12 × 48,50 € = 582,00 €" (nachgerechnet ✓; Zweitmessung 12 × 30,50 = 366,00 ✓); Klammer „24 von 36 Raten" im Posten, Summe „= 1.093,00 € TCO-24" | **BEHOBEN** |
| **A4 o2 in keiner Zeitreihe klickbar** | Bestätigt als DATENLAGE: o2 hat 262 Templates in 44 von 170 Blöcken — ausschließlich Band „mittel"; in 0 von 6 Karten-Modellen. NEU gemessen: der Lücken-Satz ist SICHTBAR („Kein Bündel in diesem Band: o2 (groß 1.356,76 €)") — o2s Fehlen ist benannt inkl. Preis aus dem Nachbarband, kein stummer Ausfall. S3-2-Kette an echtem o2-Paar bewiesen (iPhone 14 128 · mittel, 6 Messtage) | **LEAD-ENTSCHEIDUNG** (fix.md Optionen a/b/c; `band_von_gb` ist datierte Regel vom 05.09., P1 darf sie nicht still kippen) |
| **A5 Mobil: Belegzeile klebt an Kante** | Tap auf Punkt → Panel offen, Belegzeile endet bei 832,27 px (844 − 11,7), `padding-bottom:12px` + `scrollIntoView` aufs Panel; kein Querscroll (390) | **BEHOBEN** |
| **B1 Mobil: 6 Karten im Viewport verfehlt** | Messlatte bleibt verfehlt: Karten 608–700 als Wischreihe (scrollWidth 966 bei 306 sichtbar). Meine UNABHÄNGIGE Nachrechnung bestätigt den Konflikt aus fix.md: Antwort endet 804,6, Messtag-Zeile 834; ein 2×3-Grid (+≈205 px) schreibt die Antwort auf ≈1010 ≫ 844 und bricht 11c (harter Test + pruefe_portal). Bei KEINER Blockfolge sind „6 Karten im 390-Viewport" und 11c zugleich erfüllbar — auch Karten unter den Antwort-Satz löst nur die Reihenfolge, nicht die Messlatte | **LEAD-ENTSCHEIDUNG** (Optionen a/b/c in fix.md; Messlatte oder 11c oder Blockfolge — Regelentscheidung, nicht Agentenbau) |
| **B2 Karten reagieren nicht auf Bandwechsel** | Preise je Band verschieden (klein 1.573,00 / mittel 1.669,00 / groß 1.717,00 €), sichtbares `data-band` == gewähltem Band; je Band eigener Satz (zugleich Code-S3-4: ein Maßstab) | **BEHOBEN** |
| **B3 Zu flach / Markierung schwach** | Aktive Karte: `3px solid rgb(230,0,0)` + Fläche paper-2; Anbieter-Punkte 4×10 px in echten Hausfarben (#e20074/#e60000/#00589e/#f5a800) mit 1-px-Rand; Hover/Focus unterstreicht den Modellnamen; `aria-label „Anbieter mit Messung: …"` | **BEHOBEN** |
| **B4 Bewegungs-Delta flüstert** | „↑ +980 € in 3 Tagen" = 13,5 px / 700 / rot; „±0 € in 5 Tagen" = 12 px / grau | **BEHOBEN** |
| Verb. 11 Hover-Vorschau | `<title>` am Hit-Kreis, z. B. „Telekom · 15.9. · 2.697 € · erstmals gemessen" | gebaut |
| Verb. 12 Farbpunkt im Panel-Kopf | 10-px-Punkt, congstar → rgb(245,168,0) == Karten-/Legendenfarbe | gebaut |
| Verb. 13 Beleg rechts / × ≥ 28 px | Belegzeile rechtsbündig; ×-Knopf 32×32 px | gebaut |
| Verb. 14 Tab-Stops | nicht gebaut — Begründung (globaler Tab-Fluss-Umbau riskanter als der Nutzen; Punkte fokussierbar + Enter) nachvollziehbar | akzeptiert |
| Verb. 15 Einzelmesstag | Halo r=9,5 in Anbieterfarbe, steht VOR dem Hit-Kreis im DOM — Klick geht an die Trefferfläche, nichts blockiert | gebaut |

**F2: PASS. F3: PASS am Desktop (Messlatte 1440 erfüllt); mobil bleibt die
Messlatte verfehlt und ist Lead-Entscheidung (B1).** Unruhe/F1-Rahmen: keine
neuen Dauertextblöcke, keine Konsolenfehler, kein Querscroll.

## 2. S1/S2 aus pruefung-code.md

Es gab **0×S1, 0×S2** — nichts offen. S3 stichprobenartig verifiziert:

| S3 | Messung | Urteil |
|---|---|---|
| S3-1 Panel ≥ 12 px | Desktop im GEÖFFNETEN Panel: kein Element < 12 px (rkopf/pn 12,5). Vorbehalt: MOBIL setzt die Mediaquery rkopf/pn auf 11,5 px (P1-neu) — Rest R2, kein Abnahmebruch (mobil gilt dokumentiert die kleinere Zeitreihen-Stufe: messtage/hinweis stehen vor P1 auf 10 px) | behoben (Desktop bewiesen) |
| S3-2 Näherung nur für Vodafone | LIVE an echtem o2-Paar: alle o2-Templates aus dem DOM entfernt, Klick auf o2-Punkt 17.09. → „Zu dieser Messung steht kein Rechenweg bereit.", KEIN „Referenzrechnung" | behoben (echte Site, nicht nur Fixture-Test) |
| S3-3 Preiszahl bedingungslos klickbar | Code: Klasse/tabindex/title nur wenn `zrVorlagen(anb)` nicht leer — und wird im else-Zweig WEGGENOMMEN | behoben |
| S3-4 Karte zwei Maßstäbe | `karten_baender` je (Modell, Band): ab/Ø/Delta/Punkte aus DEMSELBEN Band (Code + Browser-Befund B2) | behoben |
| S3-5 tmp_nachpruef/ | `.gitignore:14`; `git status` zeigt es nicht mehr. Verzeichnis liegt noch auf Platte (Löschen wurde mangels Berechtigung abgelehnt) — fürs Commit unschädlich | behoben (Weg 2) |

0-Operatoren-Regel: über die P1-JS-Zeilen (985–1700) nur Array-Index
(`serie.length - 1`) und String-Montage — kein parseFloat/parseInt/Math auf
Zeitreihen-Zahlen. Suite: geänderte Dateien **201 passed**; `-k geraete`
**1413/3/6** (3 Rote vorbestehend, keine P1-Datei); **pruefe_portal 18/0/0**
(11c: Antwort 805, Graphkopf 834 ≤ 844). Fragment 3.555.755 B
(+2,42 MB über E2) — PM-6/P5, Zahl liegt beim Lead.

## 3. „Wie kann ich das innerhalb meines Scopes weiter verbessern?"

Reste — gefunden, bewusst NICHT gebaut (alle < 30 Zeilen, keiner bricht eine
Abnahme-Forderung):

- **R1 (F2, stärkster Rest): Der Preis im Lücken-Satz ist nicht klickbar.**
  „Kein Bündel in diesem Band: o2 (groß 1.356,76 €)" zeigt eine PREISZAHL,
  auf die Antonios Geste („wenn man auf den Preis drückt") ins Leere geht.
  Konsistenter Eingang: Klick → `waehle(modell, mittel)` + `zrOeffneNach`
  (Tunnel existiert seit A1) → o2-Rechenweg des Bandes, in dem o2 liegt.
  ~25 Zeilen (Attribut + Listener-Zweig) + Test.
- **R2 (2 Zeilen CSS): Panel mobil 11,5 px.** Der eigene neue 12-px-Test
  läuft nur am Desktop; die Mobile-Mediaquery setzt `.gr-zr-rkopf`/
  `.gr-zr-pn` auf 11,5 px. Nachbessern auf 12 px ist höhenmäßig unkritisch
  (Panel endet mobil bei 832).
- **R3 (1 Zeile): `_bewegung`-Docstring** sagt noch „des Leit-Paares
  (bandunabhängig)" — der Aufrufer liefert Band-Serien; Formulierungsrest.
- **R4: Halo trägt kein `data-anb`** — Deko ohne Verhalten; erst relevant,
  wenn je ein Hover/Titel am Halo gewünscht wird.
- **R5: Karten-Leerzustand „—" ohne Punkte-Indikator** (Sicht-Prüfer-
  Vorschlag) — minimaler Mehrwert gegen 2 Zeilen.
- **R6: Tab-Stops** (Verb. 14) — bewusste Fix-Entscheidung, bleibe dabei.

Nichts davon ist wesentlich für die Abnahme-Zeile der Strategie: Klick auf
Punkt UND Preis mit ×-Muster (bewiesen, auch am Karten-Preis), Screenshots
1440+390 (recheck-eigene unter `p1/screenshots/recheck-*.png`), Antwort-Satz
über der Falz (805/834), Fragmentgröße protokolliert (+588 kB / gesamt
+2,42 MB), 0 Rechenoperatoren — alles erfüllt und nachgemessen.

## Urteil

**DURCH = JA (im Agenten-Scope).**

- Alle behebbaren Sicht-FAILs (A1–A3, A5, B2–B4, Verb. 11/12/13/15) sind
  behoben und an der ECHTEN Site nachgeklickt und nachgerechnet.
- 0×S1, 0×S2; S3-1…S3-5 verifiziert, S3-2 zusätzlich live bewiesen.
- Suite 1413/3/6 (nur vorbestehende Rote), pruefe_portal 18/0/0.
- **B1 und A4 gehen als Lead-Entscheidungen an den Merge** — nicht als
  offene FAILs des Fix: B1 ist ein nachgerechnet unauflösbarer Konflikt
  zwischen zwei Regeln derselben Strategie (P1-Messlatte mobil vs. E2-11c
  Falzregel, harter Test); A4 steht auf der datierten Regel `band_von_gb`
  vom 05.09. Ohne Lead-Entscheidung bleibt die P1-Messlatte mobil formell
  verfehlt — das ist gewollt dokumentiert, nicht versteckt.
- Sechs Reste gelistet (R1–R6), alle klein; R1 ist der lohnendste
  Folgeschritt innerhalb P1-Scope.

Visuelle Endkontrolle: Die Screenshots liegen bei (`recheck-*.png`); die
Aussagen dieses Urteils stehen sämtlich auf Messungen (Computed Styles,
Bounding-Boxen, Template-Gleichheit), nicht auf Bildbetrachtung — der
hiesige Bildanalysedienst nahm die CDN-Links nicht an.

Server gekillt. Nichts committet, nichts unter `data/state` geschrieben.
