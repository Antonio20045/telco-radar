# P4b — Fix-Runde der drei offenen Re-Check-FAILs (18.09.2026)

Auftrag: genau die drei offenen FAILs aus `recheck.md` plus die zwei Reste
(Kachel-Zahlen im Leerzustand, Rot-Deckel als Messregel). Nichts committet,
kein `data/state` geschrieben, `site/` mit `cfg` gerendert.

## Ergebnis in Zahlen

| Messung | vorher (Re-Check) | nachher |
|---|---|---|
| Leerzustand Leitzahl `#gr-vleit` | `hidden:true`, `display:flex`, 81 px hoch („919,00 €") | `display:none`, 0 px — BEIDE Pfade (Suche „zzzz", Von-Datum 2027) |
| Kachel-Zahlen im Leerzustand (919/1.171/6/11) | stehen sichtbar | `display:none` — Leerzustand ist leer |
| Katalog initial vollrot eingefärbt | 12 (11× `a.gr-sprung` Vollrot + aktiver Knopf) | **1** (aktiver Knopf, roter RAND = Akzent) |
| Mobil 390×844, Vergleich: SVG-Top | 921 px (77 unter Falz 844) | **813 px** |
| Mobil: oberster Kurvenpunkt (Halo/Kreis) | ~954 px | **843 px** — sichtbar über der Falz |
| 11c (Telefon) | Antwort 838, Graphkopf 838 | **Antwort 787, Graphkopf 813** — beide ≤ 844 |
| Suite `-k geraete` | 1460 / 2 / 6 | **1462 / 2 / 6** (die 2 = die unangetasteten Vorbestehenden: Galaxy-Tab-S11-Ultra, Nachtlauf-Nullzeilen) |
| `pruefe_portal.py` | 21 / 0 / 0 | **21 / 0 / 0** |

Screenshots: `screenshots/p4b-leerzustand-1440.png`,
`p4b-katalog-initial-1440.png`, `p4b-vergleich-390.png` (alle drei im
Augenschein gegengelesen: leer heißt leer; Sprung-Links grau, ein roter
Rand-Knopf; „1.600 €"-Achsenlabel + farbiger Datenpunkt am Falzrand).

## FAIL 1 (S1): Leerzustand-Leitzahl — Fix an der Wurzel

Ursache: Die Browser-Vorgabe `[hidden]{display:none}` verliert gegen JEDE
Autoren-Regel mit `display` (Autor schlägt Browser, Ursprung schlägt
Spezifität nicht). Betroffen war nicht nur `.gr-leit{display:flex}`
(Leitzahl), sondern dieselbe Klasse auch `.gr-vkacheln{display:grid}`,
`.gr-vsteuer{display:flex}`, `.gr-vlegende{display:flex}` — die Kachel-Zahlen
stehen auf demselben Fehler.

Fix: eine globale Zeile im Stylesheet-Kopf (templates/style.css, direkt nach
dem Reset):

```css
[hidden]{display:none!important}
```

Sie deckt die FehlerKLASSE ab, nicht nur den gemeldeten Fall; die
bestehenden Einzel-Zeilen (`.gr-buendel[hidden]`, `.gr-zr-panel[hidden]`,
`.gr-zr-k-band[hidden]`, `.dossier-*[hidden]`) bleiben als Redundanz
stehen. Nebenwirkungen geprüft: Print-Styles heben kein hidden auf, es gibt
keine Übergänge auf `[hidden]`, und app.js misst an keinem hidden-Element
(kein getBoundingClientRect/offsetWidth darauf). Initial-hidden Elemente
(`#gr-vsteuer`, `#gr-vkacheln` …) blendet app.js beim Laden ohnehin ein —
kein sichtbarer Unterschied außer im Leerzustand.

Test gestärkt (Hausregel: ein Test, der die Zusicherung nicht wirklich
prüft, prüft nichts): `test_die_leitzahl_und_die_kacheln_schweigen_in_
beiden_leerzustaenden` (tests/test_geraete_reiter_browser.py) misst jetzt
computed `display` UND Boxhöhe statt des `hidden`-Attributs, an BEIDEN
Rückbau-Pfaden, und nimmt die Kacheln mit. Gegenprobe: mit deaktivierter
CSS-Zeile fällt er rot (ausgeführt).

## FAIL 2: Katalog-Rot 12 > 10 — Ursache war Spezifität, nicht Farbe

Die P4-Regel „grau, Rot erst im Hover" STAND im Stylesheet — wurde aber in
der Katalog-Tabelle geschlagen: `.src-table a{color:var(--red);…}` hat
Spezifität (0,1,1) gegen `.gr-sprung` (0,1,0). Die Radar-Tabelle trägt
`src-table` nicht, deshalb war die Regel dort wirksam und fix.md glaubte
sie gelte überall („Katalog 5" war mit keiner Messregel reproduzierbar —
genau der gemeldete Rest).

Fix (templates/style.css): Begleiter mit (0,2,1) nebst Hover-Gegenzug:

```css
.src-table a.gr-sprung,.src-table a.gr-ksprung{color:var(--ink-2);
  font-size:12px;font-weight:400;text-transform:none;letter-spacing:normal}
.src-table a.gr-sprung:hover,.src-table a.gr-ksprung:hover{color:var(--red);
  border-bottom-color:var(--red)}
```

Der zweite Rest — Rot-Deckel ALS MESSREGEL — ist genagelt in
`test_der_rotdeckel_des_katalogs_ist_eine_messregel` (Browser, echte
computed styles). Die Regel: eigenes Rot in Farbe ODER Fläche ODER Rand,
Farbwert aus `var(--red)` gelesen (Probe-Element, nichts hardcoded — sonst
driftet der Test mit einer Umbenennung der Konstanten), ohne SVG
(Vodafone-Datenfarbe), ohne template, nur gerenderte Elemente, Links
gezählt wie jedes Element, Deckel 10. Drei Schärflinge: Fixture-Wache
(≥ 1 Sprung-Link im Katalog, sonst messte der Entsättigungs-Assert leer),
Zähler-Gegenprobe (gestellt rotes Element muss gezählt werden — beweist,
dass der Zähler zählt), konkrete Assertion Sprung-Link ≠ Vollrot. Am
Vorher-Stand fällt der Test (ausgeführt: `rgb(230, 0, 0) != rgb(230, 0, 0)`
verletzt).

## FAIL 3: Mobil Kurve 921 px > Falz 844 — nachgemessen, nicht geraten

Was sitzt zwischen Reiterkopf und SVG (390×844, echter Bestand):
Seitenkopf 413 px (Seitenchrom) · Suchfeld+Tarifbänder 113 px ·
Kartenreihe 109 px (bereits EINE quer rollende Zeile — der Vorschlag des
Sicht-Prüfers „Kacheln zweispaltig oder quer" war längst umgesetzt) ·
Leitzahl 63 · Antwort-Satz 83 (4 Zeilen) · „So gerechnet" 12 · Messtag-Kopf
16 · **Legende 74 px (drei Zeilen, 840–915)** · SVG 921. Die 77 px unter
der Falz waren also die LEGENDE — fix.md nannte „~35–40 px" und war falsch.

Drei Hebel, alle mobil-only (`@media max-width:700px`), Desktop gemessen
unangetastet (Legende-Top 845 < SVG-Top 873):

1. **Legende unter das SVG** (`order` in `.gr-zr-graph` als Flex-Spalte —
   Markup bleibt das des genehmigten Prototyps; ihre „ab"-Werte braucht der
   Leser beim Lesen der Kurve, nicht davor).
2. **Straffung der Kette über dem Bild**: Leitzahl-Außenabstände und
   -Durchschuss, Antwort-Satz line-height 1.32→1.26, Messtag-Kopf,
   Karten-Innenabstände. Schriftgrößen unangetastet — Leitzahl 30 px >
   h1 28 px (Falz-Regel) und Kartenpreis ≥ 20 px (Messlatte) bleiben,
   beide Messlatte-Tests grün.
3. **Kopffreiraum der schmalen SVG-Variante**: `oben` 18 → 10
   viewBox-Einheiten (report/geraete_zeitreihe.py; breit unveraendert). Der
   12-Prozent-Maßstabs-Freiraum bleibt, der höchste Achsen-Wert braucht
   bei y+4 Basislinie rund 11 Einheiten und bleibt in der Fläche.

Nachher: SVG-Top 813, oberster Punkt 843 (sichtbar), erste Linie 853,
11c verbessert auf 787/813, kein Querscroll. Genagelt in
`test_am_telefon_beginnt_die_kurve_oberhalb_der_falz`
(test_geraete_zeitreihe_browser.py): misst SVG-Top UND min über
Punkt/Halo/Linie — 11c (nur Antwort und GraphKOPF) konnte diesen FAIL
nicht sehen. Gegenprobe: ohne die order-Zeile fällt der Test (881 > 844,
ausgeführt).

**Grenze, ehrlich benannt (Lead-Hinweis, keine offene Stelle):** Die
Falzlage ist inhaltsabhängig — der Antwort-Satz des Startgeräts bricht
heute in 4 Zeilen; eine fünfte Zeile (längerer Modellname/Band) kostete
~19 px und drückte die Kurve wieder unter die Falz. Die harte Abnahme
misst den gerenderten Stand, genau wie 11c es tut. Die erste LINIE beginnt
10 px unter dem Falzrand (der Pfad verbindet Punkte tiefer liegender
Preise; der oberste PUNKT der Bestwert-Serie steht darüber) — wer die
Linie selbst über der Falz will, müsste Antwort-Satz oder Kartenreihe
kürzen; das bricht 11c-Geist bzw. die Karten-Messlatte und ist nicht
gebaut.

## Sonstiges

- Messskripte der Runde: `../p4b/mess_ist_mobil.py`, `mess_karten.py`,
  `screenshots_p4b.py` (Screenshots zusätzlich in `../p4b/screenshots/`).
- Verändert: `templates/style.css`, `report/geraete_zeitreihe.py`,
  `tests/test_geraete_reiter_browser.py`,
  `tests/test_geraete_zeitreihe_browser.py` + gerendertes `site/`.
- Nicht angefasst: die zwei vorbestehenden Roten, Delta-Vorzeichen,
  PM-6/PM-7, 2c-Modellmengen (Lead-Liste aus fix.md steht weiter).
