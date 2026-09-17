# Reiter „Vergleich" (TCO-Zeitreihe) — Recon A (Preis-Klick/Rechenweg) + B (vorgeschlagene Smartphones)

Stand 17.09.2026, alle Zahlen am echten Bestand gezählt (nur Leszugriff auf data/state).

## A) PREIS-KLICK → RECHENWEG

### Wie „Rechenweg" heute funktioniert (drei Stellen, keine je Messung)

1. **Der Preis ist nirgends klickbar.** Im Antwort-Satz (`#gr-zr-antwort`) ist die
   Zahl ein `<b>`; im SVG sind die Punkte `<circle>` ohne Handler — app.js hat
   keinen Klickpfad auf `.gr-zr-punkt` (gegreppt: 0 Treffer). Der Graph ist
   reine serverseitige Montage.
2. **„So gerechnet"** (`_rechnung_html`, geraete_zeitreihe.py:341) = EIN
   statischer Aufklapper-Satz je Paar: die Formel
   `TCO-24 = Zuzahlung + Anschlusspreis + 24 × Tarifgrundpreis + Geräteraten bis
   Monat 24` plus Beleg-Link des besten Angebots **mit dem Abrufdatum von
   HEUTE** (aus der Karte, nicht aus der Historie). Erklärt die Leitzahl, nicht
   die einzelne Messung — genau Antonios Lücke.
3. **Rechenweg je Anbieterzeile** (Bündel-Tabelle unter dem Graph,
   `_geraete_buendel.html.j2:171`): `<ul class="gr-tposten">` aus
   `k.bestandteile` = `tco_24(buendel)` über den **aktuellen Stand**
   (`geraete_tco.json`). Zeigt heute, nicht „von damals".

### Was je Messung in geraete_tco_historie.jsonl liegt

Felder je Zeile (alle 2562 Zeilen vollständig): `id` (buendel_id), `datum`
(Messtag), `tarif_id`, `tarif_id_guete`, `tarif_monatlich`,
`tarif_bindung_monate`, `buendel_monatlich` (1&1-Form), `geraet_zuzahlung`,
`geraet_monatsrate`, `laufzeit_monate`, `anschlusspreis`, `quelle_url`,
`abgerufen_am`, `zustand`, `gesamt` (eingefrorene Leitzahl).

**Der Rechenweg je Messung ist vollständig rekonstruierbar — nachgerechnet an
allen 2562 Zeilen: einfache Summe aus den Messfeldern ergibt exakt das
eingefrorene `gesamt` in 2562/2562 Fällen** (beide Preisformen; o2-Beispiel
12.09.: 37 + 39,99 + 24×14,99 + 24×19,00 = 892,75 ✓; 1&1: 420 + 39,90 +
24×49,99 = 1.659,66 ✓). `tco_24()` ist eine reine Funktion — die Postenliste
je Messung kann serverseitig aus der Zeile gebaut werden, ohne Modell, ohne
Runtime-Bibliothek. **Nicht in der Historie: Boni/Rabatte** (n. z. je Messung,
nur im heutigen Stand) und `geraeteanteil`.

### Zahlen zum Bestand

- 2562 Messzeilen, 720 Bündel-IDs, 6 Messtage (12.–17.09.; 394–492/Tag)
- Stand `geraete_tco.json`: 792 Bündel (Vodafone 473, congstar 128, 1&1 74,
  o2 72, Telekom 45), 235 SKUs
- Aufbereitung: 97 TCO-Modelle, 88 in der Wahl, **170 (Modell×Band)-Paare**,
  1285 Punkte in den Serien; Startzustand apple-iphone-17-pro-256/klein
- Fragment `site/data/geraete-zeitreihe.html`: 1,12 MB, 169 Blöcke, 160 mit
  SVG (je Paar 2 SVGs breit/schmal) — PM-6 ist die offene Obergrenze

### Umsetzungsvarianten „Klick auf Preis → Rechenweg dieser Messung"

Gemeinsame Basis aller Varianten: Posten **serverseitig** je Messung bauen
(Regel 1 des Moduls: keine Zahl im Client), Historie in `_serien` wird sowieso
gelesen — dort liegen die Zeilen je Bündel schon vor dem Günstigste-Schritt.

| Variante | Wie | Aufwand | Risiko |
|---|---|---|---|
| **V1: Aufklapp-Panel am Punkt** | Server hängt je Serie eine fertige Messungs-Tabelle (Posten, Summe, Beleg-Link, Datum) als `<template data-m="datum">` unter das SVG; Kreise bekommen `data-anb`/`data-m`; app.js setzt bei Klick auf Punkt ODER Preis im Antwort-Satz das fertige Template in ein Panel (reine Montage). Plus Posten-Balken (Breite = Anteil an `gesamt`, reine CSS-Balken, Werte fertig als Strings) | mittel (1 Modulfunktion + Fragment-Erweiterung + ~40 Zeilen JS) | Fragment wächst: grob +150–300 KB bei 1285 Messungen (~+15–27 %); PM-6 klären. SVG-Klick-Ziele sind klein (r=4,5) → Trefferfläche vergrößern (unsichtbarer Kreis r=12) |
| **V2: Rechenweg-String je Punkt (kompakt)** | Wie V1, aber je Messung nur EIN fertiger String je Punkt als `data-rech="37 € + 39,99 € + 24 × 14,99 € + 24 × 19,00 € = 892,75 €"` am Kreis; Panel zeigt String + Beleg-Link + Datum. Keine Tabelle je Messung im DOM | klein-mittel | weniger „aufbereitet" als Antonios „ein bisschen komplizierter" — er will Posten sichtbar gegliedert, nicht nur eine Zeile |
| **V3: ohne JS — `<details>` je Messung unter dem Graph** | Server rendert je Anbieter eine aufklappbare Messungsliste (Datum als summary) | klein | widerspricht Forderung 1 („keine Textzeilen"): wieder Zeilen statt dynamischem Panel; scrollt weg vom Punkt |

**Empfehlung aus Recon-Sicht: V1** — sie erfüllt „dynamisch je Messung,
aufbereitet, nicht nur Zeilen" am direktesten; das Panel kann zusätzlich die
Δ-Ansicht zeigen (Posten von Messung A vs. B, beide komplett in der Historie).
Vorsicht bei zwei Fallstricken: (a) im SVG sind Vodafone-Punkte oft die der
NÄHERUNG — die Näherung hat keine Historie-Zeile, das Panel braucht einen
benannten Leer-/Erklärungszustand; (b) `getBoundingClientRect` + scrollIntoView
für Panel unter dem Punkt am schmalen Bild (Endnamen-Kette belegt den rechten
Rand) — Panel unter dem Graph, nicht neben dem Punkt, ist die robustere Wahl.

## B) VORGESCHLAGENE SMARTPHONES (Kacheln + Suchvorschau)

### Entstehung (zwei getrennte Mechaniken)

1. **Kacheln** (`#gr-zr-kacheln`, geraete.html.j2:336): serverseitig aus
   `zr.kacheln` — Sortierung (Anbieterzahl, Punkte) über alle Bänder je Modell,
   max 6 (`KACHELN_MAX`), Name = Kurzname (+ GB-Stufe nur bei Zwillingen), Meta
   = „N Anbieter". Klick → `waehle(modell, null)`. Aktuell: iPhone 17 Pro 256
   (4), Z Fold8 256 (4), S26 Ultra 256/1024/512 (3), iPhone 17 256 (3).
2. **Suchfeld-Vorschau** (`#gr-zr-vorschau`, app.js:1296): ab 2 Zeichen,
   max 8 Treffer, Präfix-Match auf Titel-Wörtern; Eintrag = Titel +
   „N Anbieter · M Bänder". Der JSON-Knoten `#gr-zeitreihe-daten` trägt
   bewusst KEINE Beträge (Regel 1) — die Vorschau kann keinen Preis zeigen,
   ohne dass der Server ihn liefert.

### Prominenz (Chromium 1440×900, site/geraete.html)

| Element | top | Höhe |
|---|---|---|
| Reiterleiste | 402 px | 40 px |
| Wahl-Leiste (Suchfeld + Bänder) | 442 px | 86 px |
| **Kacheln** | **528 px** | **92 px** (6 Kacheln in 2 Zeilen à 34 px, Breite ~246 px je Kachel) |
| Antwort-Satz | 620 px | 69 px |
| Graph | 782 px | 497 px |

Die Kacheln stehen also weit oben (Fold bei 900 px: alles sichtbar) — Antonios
„übersieht man total schnell" ist ein **Design-Befund, kein Positionsbefund**:
einzeilige 14,5-px-Text-Chips mit Etikett „4 Anbieter", kein Preis, keine
Hierarchie, aktiver Zustand nur 1,5 px Rahmen. Auf dem Telefon rollen sie
waagerecht weg (overflow-x, style.css:3363).

### Was eine prominente Kartenlösung braucht (Felderverfügbarkeit)

- **Bilder: NEIN.** Katalog (`config/geraete_katalog.yaml`) und
  `geraete_model.py` kennen keinerlei Bild-Feld (grep bild/image/foto: 0
  Treffer) — Typografie/Preis/Bewegung bleiben die Mittel.
- **Vorhanden, serverseitig billig**: Kurz-/Vollname, Hersteller, Speicher;
  **Preis je Modell** (bestes `gesamt` + Ø/Monat aus `paare` — Kacheln werden
  in Python gebaut, Regel 1 bleibt gewahrt, solange der Preis im HTML steht
  und nicht im JSON-Knoten); **Bewegung** Δ erster→letzter Messung je Modell
  aus `_serien` (erste/letzte Werte je Anbieter liegen dort schon);
  **Anbieterfarben** (`ANB_FARBE`, 5 Marken-Punkte pro Karte möglich);
  `anbieter_zahl`, `band_zahl`.
- Vorschlags-Ranking ist bereits deterministisch (Bandabdeckung vor
  Auslaufware, PM-7) — eine Kartenlösung kann dasselbe Maß behalten und muss
  nur die Darstellung ändern, nicht die Auswahl.
- Grenze: `KACHELN_MAX=6` ist Obergrenze; mehr Karten = mehr Fragment/HTML,
  aber Kacheln stehen in der Hauptseite, nicht im Fragment — Volumen unkritisch.

## Test-Regeln zum Beachten

- Neue Zahlen (z. B. Preis auf Kachel, Posten im Panel) gehören in
  `tests/test_seiten_zahlen.py`; Kriterium 11/11c von `scripts/pruefe_portal.py`
  misst die Zeitreihe (Antwort-Satz über der Falz) — ein Panel am Punkt darf
  die Falz nicht drücken.
- Fragment-Wachstum (V1/V2) gegen PM-6 absichern; ein Test auf Fragment-Größe
  existiert bisher nicht (n. z. gefunden).
