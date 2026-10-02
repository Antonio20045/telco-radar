# Design-Gutachtung /geraete.html — der harte Blick

Basis: 8 Screenshots (Vergleich/Radar/Preisverlauf/Katalog, je 1440+390, alle
angesehen) + Live-Nachmessung 17.09. gegen `site/` (Playwright, initialer
Zustand, keine Filter). Alle Zahlen unten sind gezählt/gemessen.

## Gesamturteil

Antonio hat recht. Die Seite ist ein Datenfriedhof mit Zeitungsdekor: **die
Steuerung steht oben, die Antwort unten**. Im Vergleich-Reiter liegen bis zur
Falz (900 px) Logo, 4 Reiter, 3 Band-Buttons, 6 Modell-Chips und erst DANN
der eine Antwort-Satz (620 px) — die Kurve beginnt bei 782 px. Keine einzige
Preiszahl ist groß sichtbar, bevor man scrollt. Der Radar-Reiter ist 100 %
Tabelle (0 % Grafik, 746 Zeilen) mit **727 rot eingefärbten Elementen** — Rot
ist dort keine Akzentfarbe mehr, sondern Teppich. Das widerspricht der
eigenen Designregel „Rot ist Akzent, keine Fläche".

## Messwerte je Reiter (1440 / 390)

| Reiter | Höhe px | Grafikanteil | Tabellenzeilen | Aufklapper | Fließtext | Schriftgrößen*
|---|---|---|---|---|---|---|
| Vergleich | 1833 / 2194 | 27 % / 14 % | 58 | 22 | 177 P, ~242 Sätze, 18 388 Z | 11
| Radar | 2265 / 3784 | **0 %** / 0 % | **746** (94 Tabellen) | 4 | 99 P, ~112 Sätze, 8359 Z | 11
| Preisverlauf | 1013 / 1581 | 30 % / 67 % | 6 | 1 | 5 P, 2355 Z (1 Block: 1813 Z) | 5
| Katalog | 1209 / 1775 | **0 %** / 0 % | **567** | 1 | 5 P, 618 Z | 8

*distinkte fontSize/fontWeight-Kombinationen. Ein Zeitungslayout mit 11
Schrift-Ebenen in EINEM Reiter hat keine Hierarchie, es hat Rauschen.

## 1. Unruhe — die 3 schlimmsten Störer je Reiter

**Vergleich:** (1) Drei Button-Gruppen direkt untereinander (Reiterlei­ste,
Band, Modell-Chips) — gleiche 12-px-Optik, keine Hierarchie; die
„vorgeschlagenen Smartphones" sind Chip Nr. 14–19 des Bildschirms, kein
Einladungselement (Antonio-Punkt 3 bestätigt). (2) 22 `<details>`-Aufklapper,
von denen 20 wie Tabellenzeilen aussehen: `cursor:auto`, kein Chevron —
Klickbarkeit unsichtbar. (3) Drei Export-Buttons im Kopf + „SO GERECHNET" +
„Maßstab & Datenlage" + „41 weitere Tarife" = 6 verschiedene
Meta-Bedienelemente vor/premiär um die eigentliche Tabelle.

**Radar:** (1) 746 Tabellenzeilen ohne eine einzige Grafik — der Reiter ist
ein Excel-Export mit Überschriften. (2) 727 rote Elemente: Jede Abweichung
rot = keine Abweichung ist wichtig. (3) Vier Sektionen mit 16 Filter-Buttons
und 5 Chips übereinander; 48× wiederholte Zeile „Vodafone-Basis: … € TCO-24".

**Preisverlauf:** (1) Zwei Konzepte in einem Reiter: fester Graph oben,
Modell-Wahl unten (Suchfeld erst bei 1176 px von 1581). (2) Unter dem Graph
ein 1813-Zeichen-Fließblock, der die Kurvendaten als Text wiederholt —
Antonios „mehr Text als Graf" ist wörtlich messbar. (3) Erklärsätze vor
jedem Element („Die Kurve zeigt den Barpreis ohne Vertrag…").

**Katalog:** (1) 567 Zeilen, alle sichtbar (kein Deckel) — die Tabelle ist
die Seite. (2) Preisspalte mit drei Formaten in den ersten 6 Zeilen
(„1.179,00 €", „1.197,00 € in 36 Raten", „1.315,00 € in 24 Raten (0 %)") —
das erzeugt den Eindruck „kein richtiger Preis". (3) Spalte „Verfügbar"
enthält 90× „keine Angabe", 5× Anbieternamen („freenet.de ↗") und 1× „Beleg"
— Etikett und Feld passen nicht zusammen.

**Mobil (390):** Reiterleiste horizontal scrollbar; Radar = 3784 px reine
Tabelle (4,5 Bildschirme); Vergleichs-Grafik schrumpft auf 14 % Anteil; die
4 Export-Buttons stehen gequetscht über der Steuerung.

## 2. Text vs. Grafik — Streichkandidaten

Antonios „Ich sehe nur Text": Vergleich und Radar bestehen zu ~0 Grafik
(Radar) bzw. 27 % (Vergleich, wovon die Hälfte Legende ist). Fließtext, der
kein Preis/Label/Achsentext ist — alles Streich- oder Grafik-Kandidaten:

- Vergleich: „So gerechnet: TCO-24 = …" (203 Z) · „‚mit Tarif' = …" (93 Z) ·
  „Kein Bündel in diesem Band…" (49 Z) · „Gerechnet über 24 Monate – der
  Tarif bindet…" (329 Z) · je Tarifzeile 5–7 Halbsatz-Zeilen als
  Aufklapp-Inhalt (×20).
- Radar: Einleitung „Leitzahl ist die Abweichung…" (289 Z) · „Bei diesen
  Geräten liegt…" (198 Z) · „Gesamtkosten über 24 Monate… gerechnet gegen
  Vodafone…" (346 Z) · „56 Modelle … bei weiteren 4 führt kein
  beobachteter Anbieter…" (502 Z).
- Preisverlauf: Einleitungssatz (209 Z) · Datenblock (1813 Z!) ·
  „Preisverlauf wird seit dem 10. August erfasst…" (129 Z) · „Wählen Sie
  oben ein Gerät…" (91 Z — ein Satz, der die Bedienung erklärt, verstößt
  gegen die eigene Beruhigungsregel).
- Katalog: Einleitung (402 Z).

## 3. Roter Faden — wo die Story bricht

Sollte sein: „Was kostet es? → Wo sind wir teuer? → Wie entwickelt sich der
Preis? → Was haben wir im Regal?" Brüche: (a) Der Radar enthält eine eigene
TCO-24-Tabelle („jede Zeile ein Modell, gerechnet gegen Vodafone") — dieselbe
Leitzahl wie der Vergleich, nur länger; zwei Reiter konkurrieren um dieselbe
Frage. (b) Radars „Was diese Woche auffällt – letzte 14 Tage" ist ein
Preisverlauf-Thema und gehört in den Verlauf. (c) Katalogs Aufklapper „Bei
Wettbewerbern gelistet, bei Vodafone nicht (29)" ist Radar-Material im
Katalog. (d) Der Preisverlauf zeigt oben einen festen Graph über 5 Reihen —
laut SVG-Titel sind es iPhone 17 Pro (Max) 1024/2048 GB, alle bei
mobilcom-debitel: nicht hartkodiert im Code, aber im Ergebnis eine
Apple-Ansicht, und inhaltlich dasselbe wie die Modell-Wahl darunter.
Antonio-Punkt 4 (oberen Graph löschen, Modell-Wahl nach oben) ist die
richtige Konsequenz; die 5-Reihen-Regel (`MAX_REIHEN`) erzeugt den
falschen Eindruck.

## 4. Gefühl

Erster Eindruck 1440: eine Steuerzentrale — Buttons, Chips, Reiter, Exporte.
Zweiter: eine Tabelle, die erklärt, warum sie vorsichtig ist. Die wichtigste
Zahl („466,80 € unter der Vodafone-Referenz") steht in 13 px mitten in einem
Satz. Die größte Schrift auf dem Bildschirm ist die Kopfzeile
„Gerätepreise im Vergleich" — dekoriert die Frage, statt die Antwort zu
zeigen. Ein Manager nutzt das freiwillig nur, wenn die Antwort die Seite
beherrscht: Modell wählen → EINE große Zahl + EINE Kurve, alles andere
Klick. Mobil: erst recht — vor der ersten Kurve stehen 5 Steuer-Reihen.

## 5. Antonios Punkte 2–6, Beweislage

- **P2 Preis-Klick → Rechenweg:** Mechanik existiert (20 Tarif-<details>),
  aber (a) unsichtbar klickbar (cursor:auto, kein Chevron), (b) Inhalt =
  Halbsatz-Zeilen, keine Rechung je Messung. Zeitreihen-Punkte: 16 Kreise,
  0 klickbar, 0 Tooltip. Nicht erfüllt.
- **P3 Modell-Vorschlag prominent:** nicht erfüllt — 6 Chips in 12 px
  zwischen zwei anderen Button-Gruppen (Messung: y=528–570 px).
- **P4 oberer Graph löschen:** strukturell bestätigt (Suchfeld bei
  1176 px von 1581 px Reiterhöhe; fester Graph = 4–5 Apple-Kurven).
- **P5 Katalog-Preis:** „ohne Preis" exakt 36× von 572 — alle 1&1. Der
  Gesamteindruck „überall kein Preis" entsteht durch 3 Preisformate in
  einer Spalte + „keine Angabe"-Spalte daneben; im initialen 14-Zeilen-
  Blick (Screenshot) steht 1× „ohne Preis". Der wahre Mangel: keine
  TCO-Ansicht im Katalog (P6 nicht umgesetzt; nur Export-Link
  „BÜNDEL-TCO (715)").
- **P6 Umschalter Einzelpreis/TCO im Katalog:** fehlt (0 Umschalter
  gemessen).

## 6. Regeln (testbar)

1. **Die Antwort ist die größte Zahl:** Größte Schriftgröße oberhalb der
   Falz gehört zur Leitzahl des Reiters (TCO-Delta/Bestpreis), nie zur
   Navigation. Test: max(fontSize) im ersten Viewport liegt auf einer
   Preiszahl.
2. **Eine Steuergruppe oberhalb der Falz:** Vor dem ersten Datenelement
   stehen höchstens EIN Satz und EINE Auswahlgruppe; Reiterlei­ste und
   Export zählen nicht als Daten. Test: Zahl der <button>-Reihen über dem
   ersten SVG/der ersten Tabellenzeile ≤ 2.
3. **Kein Reiter ohne Grafik:** Jede Tafel zeigt ihre Leitzahl auch als
   Bild (Radar: Balken je Modell statt 746 Zeilen). Test: `#tafel-radar
   svg` ≥ 1.
4. **Rot bleibt Akzent:** ≤ 10 rot eingefärbte Elemente je Tafel.
   Test: Zähle Elemente mit Farbton ≈ 0° (derzeit Radar 727).
5. **Klickbares zeigt sich:** Jedes `<summary>` mit Inhalt hat
   `cursor:pointer` und ein Aufklapp-Zeichen. Test:
   getComputedStyle(summary).cursor === 'pointer' für alle.
6. **Preis-Klick öffnet die Rechung:** Jede Preiszahl und jeder
   Graph-Punkt führt auf dasselbe Rechenweg-Panel mit den Parametern
   genau dieser Messung, als Rechnung gesetzt („70,00 € × 24 = 1 680 €").
   Test: Klick auf Zelle/Punkt → sichtbares „×"-Muster mit den Werten der
   Zelle.
7. **Eine Preisspalte, ein Format:** In einer Spalte genau ein Preisformat;
   Ratenpreise nur als „Betrag × Laufzeit". Test: Regex über sichtbare
   Zellwerte je Spalte — 1 Match-Muster (derzeit 3).
8. **Kein Fließblock unter Grafiken:** `<p>` nach einem SVG ≤ 200 Zeichen;
   Kurvendaten gehören in Tooltip/Legende, nicht in Text. Test: max.
   Absatzlänge nach `<svg>` (derzeit 1813).

## Mobil-Ergänzung

390 px: Falz-Inhalt = Reiterlei­ste (scrollbar) + Titel + Band + Chips; die
Kurve erscheint erst nach ~2 Bildschirmen. Radar mobil ist unbenutzbar
(4,5 Bildschirme reine Tabelle). Erst Regeln 1–3 anwenden, dann mobil
nachmessen.

— Design-Prüfer, 17.09.2026. Zahlen: Playwright-Messung initialer Zustand;
Screenshot-Höhen (z. B. Vergleich 2565 px) enthielten einen offenen
Zustand/Deep-Link und sind nicht die Messbasis.
