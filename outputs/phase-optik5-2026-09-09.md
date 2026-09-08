# Phase Optik 5 — F-4b, F-4c, F-4d, F-4e, F-6 (09.09.2026)

**Auftragsgrundlage:** `BRIEF_OPTIK5.md` (PM, 09.09.2026 00:05; R2-Übergabe:
R1 run `c36f7a08` wurde nach 76 s vom OpenClaw-Restart getött, nichts zu
bergen). Basis: main `f7b44ad`, Branch `openclaw/ticket-optik5`.

**Umfang:** reiner View-/Template-Lauf. Keine Daten-Neuerhebung, kein
Adapter, keine Tarif-/TCO-Rechnung angefasst. Geänderte Dateien:
`report/geraete_tco_grafik.py` (nur `zeitreihe()` und neue Helfer),
`templates/geraete.html.j2` (nur Makro `haendlerkarte`), `templates/style.css`
(nur Graph-Regeln), `tests/test_geraete_zeitreihe.py` (4 Neu­kalibrierungen,
je begründet).

**Commits:** `13a1760` (F-6) · `f2f096d` (F-4b/c/d/e) · Site- und
Berichts-Commits (siehe `git log`).

---

## Die acht Abnahmekriterien, je mit Beleg

### 1. F-4b — Legende lesbar: Marker-SYMBOL je Serie

**Regel:** Jede Serie trägt ein unterscheidbares Symbol (Form), nicht nur
Farbe; congstar-Gelb ist auch ohne Farbunterscheidung sicher zuzuordnen.

**Umsetzung:** `geraete_tco_grafik.G0_SYMBOLE` — acht Formen je
Reihenposition (Kreis, Quadrat, Dreieck, Raute, Ring, Kreuz, Dreieck
runter, Sechseck), gezeichnet von `_symbol()`/`_symbol_form()`; die
Legende zeigt dieselbe Form per `<use href="#gr-sym-…">` aus `<defs>`
neben dem Namen (`_symbole_defs()`). Vodafone steht überall auf Position 0
(die Eigen-Reihe sortiert vor) und ist damit stets der Kreis — dieselbe
Ausnahmestellung wie beim Rot.

**Stelle im erzeugten HTML** (`site/geraete.html`, G0 des Default-Modells
`apple-iphone-17-pro-256`):

```
<use href="#gr-sym-kreis"    class="gr-g0-legendesymbol gr-anb--vodafone" …>
<use href="#gr-sym-quadrat"  class="gr-g0-legendesymbol gr-anb--saturn" …>
<use href="#gr-sym-dreieck"  class="gr-g0-legendesymbol gr-anb--telekom" …>
<use href="#gr-sym-raute"    class="gr-g0-legendesymbol gr-anb--congstar" …>
<use href="#gr-sym-ring"     class="gr-g0-legendesymbol gr-anb--mobilcom-debitel" …>
<use href="#gr-sym-kreuz"    class="gr-g0-legendesymbol gr-anb--o2" …>
```

**congstar = Raute** — auch ohne Farbsehen zuordnungssicher. Die
Symbol-Pixel sind im Screenshot einzeln nachgewiesen (je Symbol 24–78
Farbpixel an der Legendenposition, Werte im Session-Log).

**Bau­bedingungen (alle aus den Modultests bestellt, im Modulkopf
dokumentiert):** kein Symbol ist ein `<path>` (Linien-Pfad-Zählung), keins
trägt `transform` (Verbot gedrehter Text, Browser-Test), Position 0 bleibt
`<circle>`.

**Beleg:** `outputs/optik5-screenshots/02_g0_zeitreihe.png` (Desktop 1440).

### 2. F-4c — Y-Achse ehrlich gerundet

**Vorher (live `f7b44ad`, gemessen):** G0-Default `1163/1205/1247/1289/1331`,
Band Klein `1021/1173/1325/1477/1629`, Band Groß `1127/1412/1697/1982/2266`
— die vom PM zitierte Klasse (1329/1293/1256/1219/1183 steht in anderen
Modellen genauso).

**Umsetzung:** `_achsenmarken()` — größter „schöner" Schritt
(1/2/2,5/5/10 × Zehnerpotenz, Obergrenze Rohweite Spanne/4 +35 % Luft),
der mindestens vier Marken trägt; `_achsenformat()` kürzt auf so viele
Nachkommastellen, wie die Stufe braucht (kein Tausendertrenner, wie bisher).

**Nachher (gerendert, gemessen):**

| Graph | Ticks vorher | Ticks nachher |
|---|---|---|
| G0 iPhone 17 Pro 256 | 1163/1205/1247/1289/1331 | **1175/1200/1225/1250/1275/1300** |
| Band Klein | 1021/1173/1325/1477/1629 | **1100/1200/…/1600** |
| Band Mittel | 1041/1361/1680/2000/2319 | **1250/1500/…/2250** |
| Band Groß | 1127/1412/1697/1982/2266 | **1250/1500/…/2250** |

**Spannen-Annotation:** `_spanne_text()` schreibt die tatsächliche Spanne
der Ansicht (Achsenbereich inkl. Polster, auf zwei geltende Ziffern
gerundet, „~") als `class="gr-g0-spanne"` an den linken Bildrand ÜBER die
Zeichenfläche (y=12, Plot beginnt y=16) — außerhalb des Plotbereichs kann
sie mit keiner Datenlinie kollidieren. G0-Default: **„Spanne: ~170 €"**,
Band Klein ~610 €, Band Mittel ~1280 €, Band Groß ~1140 €. Damit liest sich
eine gezoomte Skala nicht dramatischer, als die Datenlage ist.

**Beleg:** Screenshot 02 (Ticks + Spanne) und 03; Tick-Listen oben.

### 3. F-4d — Rot-Kollision aufgelöst

**Messung vorab (browser, `getComputedStyle`):** Die Telekom-Serie war im
Stand `f7b44ad` bereits **#E20074 = Telekom-Magenta, brand-exakt** — Linie,
Punkte, Legende, Kartenname, in G0 UND Band-Graphen, live wie lokal
(style.css md5-identisch). Der Befund des PM („Serie umfärben,
Telekom-Magenta ist eh die Marke") geht auf einen Vision-Review zurück, der
#E20074 neben #E60000 als „rot" las — nachgemessen sind beide R≈228/G=0,
unterschieden NUR im Blauanteil (116 vs 0): bei gleicher Strichstärke
zwei Rot.

**Umsetzung (ohne die Marke zu verbiegen):**
- Telekom-Serie bleibt **brand-exakt `--anb:#e20074`** (unverändert,
  gemessen: `rgb(226, 0, 116)` an Linie und Punkt).
- Die **Eigen-Reihe (Vodafone) bekommt 3 px statt 2 px Strichstärke**
  (`gr-g0-linie--eigen`) — dieselbe Auszeichnung, die der interaktive
  Chart längst hat (`r.eigen ? 3 : 2` in `app.js`). Rot + Gewicht = „unser
  Angebot"; Magenta + 2 px = der Wettbewerb. Zusammen mit den
  Form-Symbolen (F-4b: Vodafone Kreis, Telekom Dreieck) ist die Zuordnung
  zweifach abgesichert.
- Messwerte im Browser ( diese Session): Vodafone-Linie `stroke-width: 3px`,
  `stroke: rgb(230, 0, 0)`; Telekom-Linie `2px`, Punkt-Fill `rgb(226, 0, 116)`;
  fremde Linien `2px`. Vodafone-Logo (`site/logo.png`): häufigster Farbwert
  `rgb(230, 0, 0)` — Rot bleibt die Farbe des eigenen Angebots, jetzt mit
  eigenem Gewicht.

**Beleg:** Screenshot 01 (Seite 1440×900, Vodafone-Logo sichtbar,
Vergleichs-Tab aktiv) + 02; Farbwerte oben.

### 4. F-4e — „Serie startet"-Annotationen

**Vorher (gemessen an den gerenderten Koordinaten):** Band-Graph Klein des
Default-Modells: 1&1-Annotation (961, 231,8) und congstar-Annotation
(961, 226,4) — **5,4 px Abstand** bei 12-px-Schrift: Überlappung; im G0
lagen zwei Annotationen mit <3 px über ihren eigenen Punkten.

**Umsetzung:**
- **Platzierung:** Die Annotationen werden gesammelt und ERST NACH allen
  Daten gezeichnet; jede Kandidatenbox (≈6,3 px/Zeichen) wird gegen
  Plotgrenzen, bereits platzierte Annotationen, alle Messpunkte (±7 px)
  und alle Linienstrecken (an 8-px-Schritten gesampelt) geprüft. Leiter:
  über dem Punkt → unter dem Punkt → weiter weg; Anker kippt wie bisher
  von der Bildhälfte. Passt nichts, gewinnt der Kandidat mit den
  wenigsten Verstößen.
- **Schrift:** `--sans-system` (neue Variable, `style.css` :root) — die
  Sans-Schrift des Systems ohne Webfont (Libre Franklin wird ohnehin nur
  in 600/700/800 geliefert, 12-px-Beschriftungen liefen auf dem Rückfall).
  Angewandt auf `.gr-g0-einzeln` (Serie-startet), `.gr-g0-spanne` (F-4c)
  und `.gr-g2-marker` — die G2-Pfeile erbten als EINZIGE Graph-Klasse
  gar keine Schriftregel und renderten in der Körperserife. Messwert im
  Browser: `"Helvetica Neue", "Liberation Sans", Helvetica, Arial,
  system-ui, sans-serif`.

**font-family-Stellen:** `style.css` — `:root { --sans-system: … }`
(neu), Regeln `.gr-g0-einzeln`, `.gr-g0-spanne`, `.gr-g2-marker`.

**Nachher:** 1&1 (961, 224,8) und congstar (961, 257,4) — **32,6 px
Abstand**, kollisionsfrei; im GO weichen die o2-Annotationen unter ihre
Punkte aus, weil oben der Plotrand steht. Screenshot 02 + 03.

### 5. F-6 — „Händler"-Dopplung weg

**Vorher:** 264 Händlerkarten, davon **253 mit Dopplung** (Badge
„Händler" im Kopf UND Satzbeginn „Händler — Beschaffung läuft seit …");
11 `haendlerpreiskarte`-Karten (Saturn mit Preis) hatten die Dopplung nie.

**Umsetzung:** Makro `haendlerkarte` in `geraete.html.j2` — Badge bleibt
(der etablierte Mechanismus, dieselbe Form wie „Referenzrechnung"/„unser
Angebot"), der Satz verliert nur den wiederholten Wortanfang:
„Beschaffung läuft seit 5. September 2026". Die Vermerk-Liste am
Zeitreihen-Block (`gr-g0-haendler-vermerk`) trägt KEIN Badge und behält
ihren „Händler —" (keine Karte, keine Dopplung).

**Nachher (grep-Zähler über `site/geraete.html`):** Dopplungsmuster
(Badge + „Händler —" in derselben Karte) **0×** — vorher 253×.

**Beleg:** Screenshot 04; Beispiel-Amazon-Karte im Berichtsverlauf.

### 6. Keine Zahl verändert — Diff-Gegenprobe

- `git diff f7b44ad --stat` (Quelle): `geraete_tco_grafik.py`,
  `geraete.html.j2`, `style.css`, `test_geraete_zeitreihe.py` — keine
  Daten-, Quellen- oder Rechenlogik.
- Gegen `f7b44ad:site/geraete.html` (automatischer Vergleich):
  **844 TCO-/Händlerkarten vorher wie nachher, ALLE Karten-Zahlen
  identisch** (Anbieter + jede €-Zahl je Karte);
  **5302 `data-`-Attribute (anbieter/laufzeit/gesamt/schnitt/einmalig/
  zustand) identisch** — Sortierung unverändert; **2113 externe Links
  identisch**.
- Stichproben: Telekom-TCO-Karte des Default-Modells **byte-identisch**;
  Amazon-Händlerkarte als EINZIGE Differenz genau der Händler-Text (F-6,
  erlaubte Kategorie). Alle übrigen site-Differenzen sind Legende/Achse/
  Annotation (Graphen) — die erlaubten Kategorien.

### 7. Suite grün

`pytest -q` am Endstand: **2880 passed / 0 failed / 12 skipped
(313,7 s)** — exakt die Baseline des Baumes. Kein Test geschwächt,
gelöscht oder übersprungen. Suite-Protokollzeile steht in
`outputs/optik5-suite.txt`.

**Vier Neu­kalibrierungen** in `tests/test_geraete_zeitreihe.py`, jede
begründet im Test selbst (Kategorie „Optik-Assertion", durch F-4b
obsolet geworden):
1. `test_die_19_tage_luecke_wird_nicht_ueberbrueckt`,
2. `test_drei_punkte_mit_luecke_ergeben_zwei_getrennte_laeufe`,
3. `test_genau_ein_messpunkt_erzeugt_keine_linie_im_ganzen_bild`
   — zählten Daten-Punkte als `<circle>`; Punkte sind seit F-4b
   Symbole (Kreis/Quadrat/Polygon). Gezählt wird jetzt das
   Klassen-Präfix `class="gr-g0-punkt ` (nur Daten-Punkte tragen es;
   Legenden-Symbole sind `<use>`, defs-Formen klassenlos). Gegen den
   ALTEN Stand fielen alle drei (Zählung 4/5/3 statt 2/3/1).
4. `test_es_werden_nur_die_gegebenen_preise_gezeichnet` — las den
   Linienpfad mit `split('d="')`; seit den Symbol-`<defs>` träfe das
   `id="gr-sym-kreis"`. Liest jetzt per Regex am `gr-g0-linie`-Element
   (gleiche Aussage: genau M und L).

### 8. Site gerendert + Bericht

`site/` frisch gerendert (`render_site(…, load_config(root))`, wie
`pipeline.py`) und committet; einzige weitere Render-Differenz war die
bekannte Datums-Zeitbombe `site/data/keyword-index.json` (`stand` gegen
`date.today()`), zurückgesetzt — nicht Teil dieses Auftrags (K-1 läuft
separat). Bericht: diese Datei. Screenshots:
`outputs/optik5-screenshots/` (01 Seite 1440×900 mit Vodafone-Logo,
02 G0-Zeitreihe, 03 Band-Graphen, 04 Händlerkarten).

---

## Messgrenzen

1. **Der Vision-Check der Session lief teils gegen einen Bild-Cache**
   (Analyse-Endpunkt lieferte für eine URL die Erstfassung aus). Alle
   Kriterien sind deshalb ZUSÄTZLICH im DOM/HTML und an Pixel-Positionen
   nachgemessen (Ticks, Symbol-Pixel je Legendenposition,
   `getComputedStyle` für Farben, Strichstärken und Schriften,
   Annotations-Koordinaten aus dem gerenderten SVG); die Beleg-Screenshots
   sind frisch erzeugt und per Pixel-Diff gegen den Vorher-Stand
   unterschieden (Diff-Box (26,4)–(1059,262), nicht leer).
2. **`_achsenformat` rundet 2,5er-Stufen auf eine Nachkommastelle**
   (z. B. flache Reihe: „999,0/999,2/999,5/999,8/1000,0" — Bankers-Runden
   einer 0,25-Marke). Nur im Grenzfall flacher Reihen sichtbar; Werte
   bleiben aufsteigend und eindeutig.
3. **F-4d ist eine Form-/Gewichts-Trennung, kein Farbübergang.** Die
   Telekom-Farbe war und ist brand-exakt #E20074 (gemessen, live wie
   lokal); wer eine ANDERE Farbwert-Änderung erwartet, findet sie nicht —
   der Kollision lösen Strichstärke (3 px eigen / 2 px Telekom) und
   Formsymbole (Kreis vs. Dreieck), ohne eine Marke zu verbiegen. Der
   Farbwert steht als Beleg hier im Bericht.
4. **Symbol-Zuordnung folgt der Reihenposition**, nicht dem Namen: ein
   Anbieter kann über zwei Modellen verschiedene Formen tragen (die Farbe
   bleibt provider-stabil). Innerhalb eines Graphen ist jede Serie
   eindeutig — das ist die Forderung des Kriteriums.
5. **Vollsuite browser-lastig (313,7 s)**; die vier Neu­kalibrierungen
   wurden einzeln gegen den alten Stand geprüft (alle fielen vor der
   Anpassung), sind also scharf.

## Offen / bewusst nicht gemacht

- `gr-anb--saturn` hat weiterhin keine eigene CSS-Farbe (grauer Rückfall
  #57534a) — kein Kriterium dieses Auftrags; ein Farbeintrag wäre eine
  Marken-Entscheidung (vgl. F-4d-Diskussion), kein Optik-Fix.
- G2 (`historie()`, Reiter „Preis- und TCO-Historie", über keinen Tab
  erreichbar) hat NICHT die neuen Achsenmarken/Symbole erhalten — der
  Auftrag nennt ausschließlich die Vergleichsansicht (G0/Band). Nur die
  G2-Pfeil-Schrift wurde auf System-Sans gehoben (F-4e: „Annotationen").
- Die Vermerk-Liste `gr-g0-haendler` behält „Händler —" (kein Badge dort,
  keine Dopplung; Kriterium betrifft Karten).
