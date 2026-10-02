# Schnittstelle Rechenweg-Panel (P1, A1 → A2)

Stand 17.09.2026. Bau-Agent A1 liefert die Rechung EINER Messung
serverseitig als fertige `<template>`-Blöcke; A2 (Klick-Panel in
app.js/style.css) montiert sie nur noch. Kein JS rechnet, formatiert
oder baut Zeichenketten — Regel 1 des Moduls
(`src/telco_radar/report/geraete_zeitreihe.py`).

## Wo die Teile stehen (je (Modell × Band)-Block, First Paint UND Fragment identisch)

```
section.gr-zr-graph
  ├─ .gr-zr-bild            beide SVG-Varianten (breit/schmal)
  │    └─ circle.gr-zr-punkt[data-anb][data-m]      sichtbarer Punkt (r 4,5/6)
  │    └─ circle.gr-zr-hit[data-anb][data-m]        unsichtbare Trefferfläche
  │                                                  r=12, fill=transparent,
  │                                                  liegt ÜBER dem Punkt
  ├─ … Hinweis / Lückensatz …
  └─ div.gr-zr-rechnungen[hidden]
       └─ template[data-anb='ANBIETER'][data-m='YYYY-MM-DD']   je Messung
       └─ template[data-anb='Vodafone'][data-m='naeherung']    optional, s. unten
```

- **`data-anb`** ist der Anbietername wie im SVG („Telekom", „Vodafone",
  „o2", „1&1", „congstar"); **`data-m`** der Messtag ISO („2026-09-12").
  Im Markup HTML-escaped („1&amp;1"), `getAttribute('data-anb')` liefert
  im DOM „1&1" — Selektor mit dem Rohwert bauen, nicht selbst escapen.
  Die Trefferfläche trägt dieselben Attribute wie ihr Punkt — Klick-
  Delegation auf `svg` reicht: `e.target.closest('circle[data-m]')`.
  Die Kreise gibt es in BEIDEN SVGs (das eine ist per CSS versteckt).
- **Der Container `.gr-zr-rechnungen` ist `hidden`** — er kostet keinen
  Platz. Nicht den Container selbst zeigen: die Blöcke gehören in EIN
  Panel (Strategie P1 Auftrag 2).

## Montage (Vorschlag, ~40 Zeilen)

```js
block.querySelector(
  "template[data-anb='" + anb + "'][data-m='" + m + "']")
  -> .content.cloneNode(true) -> in EIN Panel (.gr-zr-panel o. ä.) setzen
```

- Panel UNTER dem Graphen, nicht neben dem Punkt (mobil instabil —
  vergleich.md Fallstrick b).
- Fehlt das Template (sollte bei Kreisen nicht vorkommen): Fallback auf
  den Leerzustand `data-m='naeherung'`, falls vorhanden.
- Cursor/`tabindex`/`role` auf `.gr-zr-hit` sind A2s Teil (style.css/
  app.js); die Fläche selbst ist serverseitig da.

## Der Leerzustand (Vodafone-Näherung)

Paare, in denen Vodafone kein eigenes Bündel hat, tragen EINEN Block
`template[data-anb='Vodafone'][data-m='naeherung']` mit dem benannten
Leerzustand (Klasse `gr-zr-rech--leer`, Text: „Referenzrechnung, kein
Angebot … keine Messung je Messtag"). **Im heutigen Bestand kommt er
nicht vor** (Vodafone führt überall echte Bündel, 1484 Historien-Zeilen)
— die Klick-Zahl der Näherung im Antwort-Satz darf deshalb nicht still
ins Leere laufen: wenn kein Template zu (Anbieter, Messtag) existiert,
den Näherungs-Block nehmen, sonst einen eigenen Hinweis zeigen.

**Bekannte Grenze für A2:** Die PREISZAHL im Antwort-Satz nennt den
besten Stand von HEUTE (Karte, nicht Historie) — es gibt kein Template
zu „heute". Empfehlung: Klick auf die Preiszahl öffnet den Rechenweg des
LETZTEN Messtags desselben Anbieters (`templates.last` der Serie; die
Messtage sind ISO-sortiert, das letzte Template der Serie = jüngste
Messung). Das ist die gleiche Datenquelle wie der Punkt, keine zweite.

## ECHTES Beispiel-Markup

Kopiert aus dem gerenderten `site/data/geraete-zeitreihe.html`
(samsung-galaxy-s23-128 × mittel, o2 am 12.09.2026 — dieselbe Messung,
an der vergleich.md die Summe nachgerechnet hat):

**Punkt + Trefferfläche im SVG:**

```html
<circle class='gr-zr-punkt' cx='58.0' cy='224.5' r='4.5' fill='#0019a5' data-anb='o2' data-m='2026-09-12'/>
<circle class='gr-zr-hit' cx='58.0' cy='224.5' r='12' fill='transparent' data-anb='o2' data-m='2026-09-12'/>
```

**Template unter dem SVG (der Klick-Inhalt):**

```html
<div class='gr-zr-rechnungen' hidden><template data-anb='o2' data-m='2026-09-12'><div class='gr-zr-rech'><p class='gr-zr-rkopf'><strong>o2</strong> · Messung vom 12. September 2026</p><ul class='gr-zr-posten'><li class='gr-zr-posten'><span class='gr-zr-pn'>Gerätezuzahlung</span><span class='gr-zr-pr'>37,00 €</span></li><li class='gr-zr-posten'><span class='gr-zr-pn'>Anschlusspreis</span><span class='gr-zr-pr'>39,99 €</span></li><li class='gr-zr-posten'><span class='gr-zr-pn'>Tarif</span><span class='gr-zr-pr'>24 × 14,99 € <span class='gr-zr-pg'>= 359,76 €</span></span></li><li class='gr-zr-posten'><span class='gr-zr-pn'>Geräterate</span><span class='gr-zr-pr'>24 × 19,00 € <span class='gr-zr-pg'>= 456,00 €</span> <span class='gr-zr-pk'>24 von 36 Raten</span></span></li></ul><p class='gr-zr-rsumme'>= <b>892,75 €</b> <span class='gr-zr-plabel'>TCO-24</span></p><p class='gr-zr-rbeleg'>Beleg: <a href='https://www.o2online.de/e-shop/samsung/samsung-galaxy-s23-128gb-pink-details?ohne-tarif=nein&amp;zielgruppe=privatkunden&amp;ratenzahlung=36&amp;vertragsart=ratenzahlung&amp;tarif=o2-mobile-on-demand-m-plus' target='_blank' rel='noopener'>o2&nbsp;↗</a>, abgerufen 12.09.2026.</p></div></template></div>
```

**Die zusammen-Form (1&1, EIN Bündelmonatspreis, kein Tarif-/Rate-Posten):**

```html
<template data-anb='1&amp;1' data-m='2026-09-12'><div class='gr-zr-rech'><p class='gr-zr-rkopf'><strong>1&amp;1</strong> · Messung vom 12. September 2026</p><ul class='gr-zr-posten'><li class='gr-zr-posten'><span class='gr-zr-pn'>Gerätezuzahlung</span><span class='gr-zr-pr'>420,00 €</span></li><li class='gr-zr-posten'><span class='gr-zr-pn'>Anschlusspreis</span><span class='gr-zr-pr'>39,90 €</span></li><li class='gr-zr-posten'><span class='gr-zr-pn'>Bündelpreis (Tarif und Gerät zusammen)</span><span class='gr-zr-pr'>24 × 49,99 € <span class='gr-zr-pg'>= 1.199,76 €</span> <span class='gr-zr-pk'>24 von 36 Monaten</span></span></li></ul><p class='gr-zr-rsumme'>= <b>1.659,66 €</b> <span class='gr-zr-plabel'>TCO-24</span></p><p class='gr-zr-rbeleg'>Beleg: <a href='https://mobile.1und1.de/iphone-17-pro-max' target='_blank' rel='noopener'>1&amp;1&nbsp;↗</a>, abgerufen 12.09.2026.</p></div></template>
```

## CSS-Klassen für A2 (alle ungestaltet, style.css ist A2s)

| Klasse | Element | Inhalt |
|---|---|---|
| `gr-zr-rechnungen` | div, `hidden` | Container der Vorlagen |
| `gr-zr-rech` | div | EIN Messungs-Block (Klon-Ziel) |
| `gr-zr-rech--leer` | div | Leerzustand der Näherung |
| `gr-zr-rkopf` | p | Anbieter · Messung vom DATUM |
| `gr-zr-posten` | ul / li | Postenliste / EIN Posten |
| `gr-zr-pn` | span | Posten-Label („Geräterate") |
| `gr-zr-pr` | span | Rechenausdruck („24 × 19,00 € = 456,00 €") |
| `gr-zr-pg` | span | der „= BETRAG"-Teil des Ausdrucks |
| `gr-zr-pk` | span | Kappungs-Klammer („24 von 36 Raten") |
| `gr-zr-rsumme` | p | „= 892,75 € TCO-24" (b = die Zahl) |
| `gr-zr-plabel` | span | Etikett „TCO-24" |
| `gr-zr-rbeleg` | p | Beleg-Link + Abrufdatum |
| `gr-zr-hit` | circle | unsichtbare Trefferfläche im SVG (r=12) |

Abnahme dafür (Strategie P1): Klick auf Punkt UND auf Preis → sichtbares
„×"-Muster mit den Werten genau dieser Messung (design.md Regel 6);
0 Rechenoperatoren im JS auf Zeitreihen-Zahlen.

## Was es bewusst NICHT gibt

- Keine Boni-/Geräteanteil-Posten — die stehen nicht in der Historie
  (Auftrag: nichts erfinden, was nicht in der Zeile steht).
- Kein Restbetrag-Satz („nach 24 Monaten offen") im Panel — der steht an
  den Bündel-Karten; nachziehen wäre ein eigener kleiner Auftrag.
- Keine Delta-Ansicht Messung A vs. B (Strategie: bewusst nicht, evtl.
  Zusatz nach Sichtung).
