# P3-SICHT-Prüfung: Gerätekatalog mit Preis-Umschalter

**Datum:** 18.09.2026, gegen 01:00 · **Prüfer:** harter Sicht-Prüfer ohne Bau-Kontext
· **Gegenstand:** `site/geraete.html`, Reiter „Gerätekatalog" (P3, Strategie Geraete v3)
· **Methode:** echter Server (127.0.0.1:8768) + Playwright-Chromium, 1440×900 und
390×844; Vollmenge statisch im HTML nachgezählt; Screenshots unter
`outputs/strategie-geraete-v3-2026-09-17/p3/screenshots/` (7 Stück).

**Urteil: NICHT freigegeben (durch=false).** Kein FAIL gegen F5/F6 — aber drei
Wesentliche im eigenen Scope fallen mir noch ein (Sortier-Rest, Mehr-Button,
stummes „–" in der Delta-Spalte). Details unten.

---

## 1. Steht in JEDER Zeile ein Preis? — JA (Barpreis), benannt leer (TCO)

Vollmenge, statisch über alle 111 Modellzeilen des gerenderten HTML gezählt:

| Ansicht | mit Preis | benannter Leerzustand | „ohne Preis" |
|---|---|---|---|
| Einzelgerätpreis | **110** × „ab X € bei Händler ↗" + Datum | **1** × „nur im Bündel, ab 25,99 €/Monat · Beleg ↗" | **0** |
| Gesamtkosten (TCO-24) | **92** × „ab X € bei Y" | **19** × „kein Bündel gemessen" | **0** |

- Der String **„ohne Preis" kommt im ganzen Reiter 0-mal vor** — auch in den
  111 Aufklappern mit zusammen 636 Listungszeilen nicht (vorher: 36×, alle 1&1,
  deren Bündelpreis längst im Store lag). Der Aufklapper zeigt für diese
  Listungen „ab X €/Monat, Tarif, Beleg ↗".
- „Kein Preis gemessen" (der leere Zweig der Vorlage): 0-mal — er ist laut
  Bau-Regel heute unbesetzt, die Regel selbst bleibt laut.
- Im Browser (beide Breakpoints, gekappte Ansicht): 12/12 Zeilen mit Preis in
  der Barpreis-Ansicht, 11/12 mit TCO (1× „kein Bündel gemessen", Nothing
  Phone (4a) 128 GB).

**Bewertung F5:** erfüllt. Der Zustand „verfügbar, Farbe, aber kein Preis"
existiert nicht mehr — jede Modellzeile führt eine Zahl oder den benannten
Bündel-Zustand. Die 19 TCO-Leerzeilen sind eine ehrliche, benannte Datenlücke
(dieses Modell hat schlicht kein Bündel im Store), keine fehlende Anzeige;
in der Barpreis-Ansicht tragen dieselben Modelle ihren Preis. Antonio würde
die 17 % leeren TCO-Zellen sehen — mit Grundangabe, nicht stumm.

## 2. Umschalter — findbar, verständlich, ohne Reload; Sortierung mit Rest

- **Findbarkeit:** zwei Knöpfe in der bekannten `gr-vgruppe`-Bauform (aktiv
  rot), direkt unter der Filterreihe, im ersten Viewport sichtbar (1440:
  Reiterkopf y=442, Umschalter y=655 bei 900 px Höhe; 390: y=830, ohne
  Scrollen erreichbar). Beide Knöpfe auf 390 px **nebeneinander vollständig
  sichtbar**, kein Umbruch.
- **Verständlichkeit:** „Einzelgerätpreis" / „Gesamtkosten (TCO-24)" — die
  Worte treffen Antonios F6-Vokabular („Total Cost of Ownership oder halt
  Einzelgerätpreis"). Default ist Einzelgerätpreis (richtig: das ist die
  Frage dieses Reiters).
- **Wechsel ohne Reload:** bestätigt (Marker-Fenster bleibt gesetzt,
  DOM-Spalten blenden nur um). Beide Ansichten stehen serverseitig fertig
  im Markup — kein Client-Rechnen.
- **Filter bleiben beim Wechsel aktiv** (Marke=Samsung → 12 Zeilen in
  beiden Ansichten, Auswahl bleibt gesetzt).
- **ABER (Wesentliches 1):** Sortiert man in der Barpreis-Ansicht (z. B.
  Klick „Einzelgerätepreis", Pfeil ↓ erscheint) und schaltet dann auf TCO
  um, **bleibt die Sortierung an der jetzt unsichtbaren Spalte hängen**.
  Gemessen: TCO-Spalte danach 3.357,66 / 2.705,66 / 2.927,80 € — nicht
  monoton, die Liste wirkt unsortiert, und der Sortierpfeil ist weg (seine
  Kopfzelle ist ausgeblendet). Die Prüffrage „Bleibt die Sortierung
  sinnvoll?" ist für diesen Fall mit NEIN zu beantorten. Ein Klick auf
  „TCO-24" heilt es (dann sauber fallend, Wertlose ans Ende — P3-Regel
  greift), aber der Leser muss es wissen.
- Sortier-Richtung selbst: Erstklick Zahlenspalte = absteigend (teuerste
  oben), konsistent mit der Radar-Tafel; Zeilen ohne Zahl fallen in BEIDEN
  Richtungen ans Ende (verifiziert: TCO-Sortierung, unten drei × leer).

## 3. Liest sich die TCO-Ansicht als die fehlende TCO-Modell-Liste? — JA

Sichtbar im Screenshot (`pruef-1440-tco.png`, Analyse bestätigt): Spalten
**MODELL · TCO-24 · Ø €/MONAT · Δ ZU VODAFONE · BAND** — Zeile je Modell,
„ab 2.927,80 € bei o2 ↗, 17. September", darunter Monatspreis und Delta.
Das ist genau F6: *„eine Tabelle für beide Sachen"*, kein zweiter Seitentyp,
keine verschachtelte Spezialtabelle. Gleiche Zeilenhöhe, gleiche Bauform wie
die Barpreis-Ansicht; nur die Spalten wechseln.

Zwei Trübungen, beide Datenlage, keine davon darf versteckt werden:

- **Δ zu Vodafone: 57 von 111 Zeilen zeigen „–".** Davon 19 ohne Bündel und
  **38 mit TCO, aber ohne Referenz** (Beispiel „Nothing Phone (3) 256 GB":
  Vodafone listet das Gerät nicht → keine Referenz). **(Wesentliches 3):**
  das „–" ist stumm; der Grund steht laut Bau-Kommentar nur „im Reiter
  Vergleich". Wer hier steht, versteht die halb leere Spalte nicht.
- Band-Spalte: Klein 48 / Mittel 41 / Groß 3 / „–" 19. Die 19 sind dieselben
  bündellosen Modelle — konsistent.

Farb-Semantik geprüft: negatives Delta (−17,1 %) rot = `--al-kritisch`,
identisch zur Radar-Tafel (`_geraete_radar.html.j2`, gleiche Klasse für
prozent<0). Konsistent im Portal — rot heißt „Abweichung unter die
Vodafone-Referenz", nicht „schlechter Deal".

## 4. Zeilen-Aufklapper — erreichbar und lesbar

Klick auf die Modellzeile öffnet die Listungs-Tabelle (gleiche Mechanik wie
die Radar-Modellliste). Gemessen (beide Ansichten, beide Breakpoints):

- Köpfe: **Händler · Farbe · Preis · Zustand · Bestand · Abgerufen**.
  „Bestand" ersetzt „Verfügbar" — richtig, 98 von 636 Listungen sagen
  „keine Angabe", und das alte Wort versprach eine Lieferauskunft.
- Beispielzeile: „Vodafone ↗ · Burgunder · 3.099,90 € · neu · Verfügbar ·
  17. September 2026" — lesbar, jede Listung mit Beleg-Link.
- Visuell (Screenshot `pruef-1440-aufklapper.png`): Aufklappbereich grau
  unterlegt, mit oberer und unterer Rahmenlinie an die Elternzeile
  gebunden, Etikett „Listungen" links oben — eindeutig zuordnungbar, kein
  Overlay, verdrängt nichts. Kein horizontaler Scroll nötig (Tabelle
  1.156 px im 1.156-px-Container).
- Funktioniert auch in der TCO-Ansicht (geprüft).

## 5. Unruhe — RUHIGER als vorher; Reiterhöhe im Budget

| | vorher (Listungs-Tabelle) | jetzt (Modell-Ebene) |
|---|---|---|
| Zeilen | 566 gerenderte Listungszeilen zu 111 Modellen (Bestand 636) | **111 Modellzeilen**, Deckel 12 sichtbar, „alle 111 Zeilen zeigen" |
| „ohne Preis" | 36 | **0** |
| Dubletten | dasselbe Gerät als Farb-/Anbieter-Zeilen wiederholt | 1 Zeile je Modell, Farben/Zustände im Aufklapper |
| Pills in der Hauptzeile | Zustand + Verfügbarkeit je Zeile | **keine** — nur Preis, Händler, Spanne |

Reiterhöhe (gekappt): **1.464 px** (1440) / 1.855 px (390) — weit unter dem
3.000-px-Budget. Entfaltet (Nutzerhandlung): 7.290 / 8.442 px — zulässig,
weil explizit vom Leser geöffnet.

Rest-Unruhe, klein: der Einleitungssatz unter der Rubrik hat **33 Wörter**
(F1: „Ich will keinen Text sehen") — er erklärt beide Ansichten und ist die
seitenweit übliche Bauform, aber ein Halbsatz täte es auch. Im DOM liegen
1.272 Pills — alle in geschlossenen Aufklappern, sichtbar keine.

## 6. Mobil 390 — kein Querscroll, nutzbar

- `document.scrollWidth` = 390 = Viewport, **auch im entfalteten Zustand**
  und in beiden Ansichten. Kein Seitwärtslauf der Seite.
- Tabelle rollt in ihrem eigenen Container (`.gr-alarm-scroll`), Spalten
  nacheinander erreichbar, Schrift nicht gestaucht (Bildanalyse
  `pruef-390-tco.jpg`: Kopf und Zeilen lesbar, Zeilen einzeln erreichbar).
- Umschalter nebeneinander voll sichtbar und touch-bar (s. o.).

## 7. Wie weiter verbessern (innerhalb des Katalog-Scope)?

**Wesentliches, das mir noch einfällt (Grund für durch=false):**

1. **Sortierung beim Ansichtwechsel übernehmen.** Wechsel auf TCO sollte
   die aktive Sortierung auf „TCO-24" mappen (oder auf Server-Ordnung
   zurücksetzen). Gemessener Fall: nicht-monotone TCO-Liste, Sortierpfeil
   unsichtbar. Kleiner Codepfad in `app.js` (Ansicht-Handler kennt die
   Spalte), großer Verwirrungsgewinn.
2. **Mehr-Button ohne Zustandswechsel.** Nach dem Entfalten steht weiter
   „alle 111 Zeilen zeigen" da, ein zweiter Klick tut nichts
   (`gr-alarm--alle` bleibt gesetzt). Entweder Text wechseln („nur 12
   zeigen" + Toggle) oder den Button verschwinden lassen. Heute liest sich
   das als kaputt.
3. **Das stumme „–" in der Delta-Spalte benennen.** 38 Zeilen mit TCO ohne
   Referenz. Ein Kurzgrund an der Zelle („Referenz fehlt — Vodafone listet
   das Modell nicht", gern als `title`/Icon) erklärt die Halbleere an Ort
   und Stelle; der Verweis auf den Vergleichs-Reiter hilft niemandem, der
   hier steht.

**Kleineres:**

4. Spanne „–" bei Ein-Händler-Modellen (62 von 111 ohne wesentliche
   Spanne): „–" heißt hier „nur ein Preis", das könnte die Zelle selbst
   sagen.
5. Erklärsatz von 33 auf ~15 Wörter kürzen (F1-Geist): „Eine Zeile je
   Modell — links der günstigste Händler, rechts das günstigste Bündel
   über 24 Monate." Farbe/Zustand/Beleg unter der Zeile.
6. Auf 390 rollt die Tabelle waagerecht; ein klebriger Modell-Spaltenkopf
   (sticky) würde dem Leser die Orientierung beim Rollen erhalten —
   Nice-to-have, kein Fehler.
7. Die 19 „kein Bündel gemessen"-Zeilen in der Standard-Ordnung sammeln
   (sie stehen heute zwischen den Zeilen mit Zahl; bei Sortierung wandern
   sie korrekt ans Ende).

---

## Beweise

- Screenshots: `screenshots/pruef-1440-barpreis.png` · `pruef-1440-tco.png`
  · `pruef-1440-aufklapper.png` · `pruef-390-barpreis.png` ·
  `pruef-390-tco.png` · `pruef-1440-barpreis-alle.png` ·
  `pruef-390-barpreis-alle.png`
- Messskripte: `mess_sicht.py`, `mess_entfaltet.py` (im selben Ordner)
- Kernzahlen: 111 Modellzeilen (12 sichtbar, Deckel `KATALOG_SICHTBAR`=12);
  Barpreis 110/1/0; TCO 92/19; „ohne Preis" 0; Aufklapper 636 Listungszeilen;
  Reiterhöhe 1.464 px (1440, gekappt); kein Querscroll auf 390 in jedem
  Zustand; Wechsel ohne Reload; Filter überleben den Wechsel.
