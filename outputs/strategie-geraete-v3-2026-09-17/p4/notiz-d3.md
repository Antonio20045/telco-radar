# P4/D3 — Ruhe-Mechanik, die messbar ist (18.09.2026)

Auftrag: Text-Deckel in pruefe_portal.py, alle `<summary>` klickbar
(cursor + Caret), Bestand-Etikett konsequent, je Regel ein Test.
Antonios Rahmen: „Ich will keinen Text sehen. Alles so unruhig."

## 1. Text-Deckel — Kriterium 13/14 in `scripts/pruefe_portal.py`

**Messdefinition** (dokumentiert im Skript): Summe der
Leerraum-normalisierten Zeichen aller `<p>` EINER Tafel, **inklusive
Aufklapp-Text** (details, JS-Aufklappzeilen), **ohne nie sichtbare
`<template>`s**. Grund: FM 4 nennt den Preis-Klick den Härtetest — „gerät
er zum Textblock, ist FM 4 sofort zurück"; ein Deckel, der nur den ersten
Bildschirm misst, sähe genau diesen Rückschlag nicht. Nachmessung am
Vorher-Stand bestätigt: design.md (17.09.) zählte dieselbe Menge —
Vergleich 18 388 Z (ich: 18 100), Radar 8 359 Z (ich: 8 894).

**Deckel (wie beauftragt) und Messwerte nach dem Rendern:**

| Reiter | Deckel | Vorher (17.09./design.md) | Nachher gerendert | |
|---|---|---|---|---|
| Vergleich | 6000 | 18 388 Z | **18 048 Z — ROT** | Hebel unten |
| Radar | 6000 | 8 359 Z | **2 743 Z — GRÜN** | D1s Legende kappte ~6,1k (48× „Vodafone-Basis"-Zeile → 1 Legende) |
| Preisverlauf | 2500 | 2 355 Z (1 Block: 1813 Z) | 358 Z — GRÜN | 1813-Z-Block mit P2 gefallen |
| Katalog | 2500 | 618 Z | 230 Z — GRÜN | |

**Begründung der Grenzwerte:** Radar 6000 — nach der P4-Balkengrafik
liegt der Reiter bei 2 743 Z; ein Rückschlag auf Vor-P4-Prosa (8,4k)
kippt. Verlauf/Katalog 2500 — der gefallene 1813-Z-Datenblock ALLEIN
hätte den Verlaufs-Deckel zu drei Vierteln gefüllt; die Grenze verbeugt
einen zweiten solchen Block, lässt Bildunterschriften zu. Vergleich 6000 —
**bewusst rot bis zur Entscheidung des Leads/P5**: 16,5k der 18 048 Z
sitzen in den 20 Tarif-Rechenweg-Aufklappern (je ~500 Z „Gerechnet
über…" + Posten, Klassen .gr-basis--duenn/.gr-kk-*). Grün wird der
Reiter erst, wenn dieser Text dem P1-Panel-Weg als `<template>` folgt
(templates zählen nicht) oder gekürzt ist — der Deckel zeigt den Hebel,
das ist seine Aufgabe. Nicht von D3 umgebaut (P1 ist abgenommene Arbeit).

**Kriterium 14** — `<p>` direkt nach einem `<svg>` ≤ 200 Z
(`max_absatz_nach_svg`, nur initial Sichtbare): heute **0 Z** auf allen
vier Reitern (der 1813-Z-Fall ist mit P2 gefallen; das Kriterium ist der
Rückfallschutz). Nebenfunde beim Bau: `previous_element_sibling` ist unter
html.parser nach inline-`<svg>` **None**, obwohl `previous_siblings` das
svg führt — die Erkennung geht über `previous_siblings` (Kommentar im
Skript); die allererste Messung „0 überall" war bis dahin auch ein
Messfehler-Verdacht, die reparierte Funktion misst am echten Stand
ebenfalls 0.

## 2. Alle `<summary>` klickbar — Kriterium 15 + style.css

Vorher (eigene Browsermessung, initialer Zustand): **28 summaries, 20 mit
cursor:pointer, 3 mit Aufklappzeichen** (tco 22/19/0 · radar 3/0/0 ·
verlauf 2/1/1 · katalog 1/0/0). „So gerechnet" hatte cursor:auto.

Gebaut in `templates/style.css` (vor dem .gr-tdetail-Block, gescoped auf
`.gr-tafel`, alle vier Reiter inkl. P3-Zeilen-Aufklapper und Wochenkarte):
`cursor:pointer` + `list-style:none` + `::after "▾"`, `[open] → "▴"`;
`.gr-vdatenlage>summary` behält sein +/– (gleiche Spezifität, spätere
Regel gewinnt — im Browser-Test festgenagelt).

Nachher (pruefe_portal Kriterium 15 an site/geraete.html): **30
summaries, alle 30 mit Zeiger und Aufklappzeichen — BESTANDEN.**
Visuell gegengelesen: Screenshots `screenshots/d3-vergleich-carets-1440.png`
(Carets auf allen Anbieterzeilen) und `d3-radar-carets-1440.png`.
Andere Seiten unberührt (.mressort & Co. stehen außerhalb von .gr-tafel —
Gegenprobe im pytest).

## 3. Bestand-Spalte im Katalog (P3 hatte das Etikett umbenannt)

Etikett „Bestand" stand über Werten in Verfügbarkeits-Sprache, davon einer
großgeschrieben („Verfügbar") gegen drei kleingeschriebene. **Werte folgen
jetzt dem Etikett:** 503× „Verfügbar" → **„lieferbar"**; „keine Angabe" 98×,
„nicht lieferbar" 33×, „vorbestellbar" 2× unverändert; **0× „Verfügbar"**
im Katalog nachher (vorher 503). NICHT gelöscht, Spalte unverändert —
Antonio-Entscheidung bleibt P5 vorbehalten (Kommentar in der Vorlage).
Screenshot `d3-katalog-bestand-1440.png`, Vision-Gegenlesen: „lieferbar"/„keine
Angabe" korrekt.

## 4. Tests

`tests/test_geraete_textdeckel.py` — **12 passed**: Deckelfunktion gegen
Mini-HTML (zählt Aufklapp-Text MIT — der Härtetest ist die Regel; templates
nicht; Whitespace normalisiert; leere p nicht), svg-Folge-Erkennung (drei
Strukturen, versteckte zählen nicht, 200/201-Grenze), jeder der vier
Reiter hat einen Deckel, Browser-Tests gegen die echte style.css (pointer
+ Caret, .mressort-Eigenzeichen unangetastet, nacktes summary außerhalb
unberührt, .gr-vdatenlage behält „+").

## Offen / Parallel-Befunde (nicht D3)

- **Kriterium 13 Vergleich ROT** (18 048 > 6000): Hebel = 20
  Tarif-Rechenweg-Aufklapper à ~500 Z (16,5k Z). Lead/P5-Entscheidung:
  template-Weg oder Kürzung. D3 fasst P1-abgenommene Arbeit nicht an.
- **Kriterium 11c ROT** (mobil): Antwort-Satz 828 px ok, aber Graphkopf
  858 px > Falz 844 — 14 px über. Nicht durch D3 (Carets sind inline,
  kosten keine Höhe vor dem Graphkopf); D2/D4-Baustelle.
- Parallel-Rote in Nachbarsuite: `test_geraete_seite.py` 2×
  (Sortiments-Aufklapper-Reiter — P4/2b-Festnagelung, kehrt bewusst;
  Filter-Chips „Zustand/Preisart" — P3-Folge) und
  `test_geraete_reiter_browser.py` 13× (alle wr-alarme/Filter/Sortierung —
  D1s Radar-Baustelle; kein summary-Bezug in der Datei). Der dritte
  vorbestehende Rot (iPhone-18-Querlinks, o3_rollen:212) bestätigt.
- Zwischenstand: während der D3-Arbeit war `geraete_radar.py` kurzzeitig
  halbfertig (`haendler_zeilen` NameError, Radar-Tafel im Fehlerzustand);
  D1 hat das im Lauf behoben — alle Zahlen oben sind am intakten Stand
  gemessen (Kriterium 11: 50 Alarmzeilen BESTANDEN).
- p-nach-SVG-Kriterium ist ein Rückfallschutz (heute 0 Z) — es misst
  NUR serverseitig gerenderte Absätze; JS-gefüllte Knoten (Verlauf) sind
  initial `hidden` und zählen nicht. Grenze dokumentiert.
