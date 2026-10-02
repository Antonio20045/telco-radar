# P1/A2 — das Klick-Panel (Rechenweg einer Messung), 17.09.2026

Auftrag: STRATEGIE_GERAETE_V3 §P1 Bau-Auftrag 2. Grundlage
`schnittstelle-rechenweg.md` (A1) — die Templates standen schon im
Fragment und im First Paint (1285 Messungen, verifiziert).

## Geänderte Dateien (nur diese)

| Datei | Was |
|---|---|
| `src/telco_radar/report/templates/geraete.html.j2` | GENAU EIN Container: `#gr-zr-panel` (hidden), P1/A2-comment-markiert, direkt nach dem Montagepunkt `#gr-zr-gruppe` (vor der Bündel-Sektion) |
| `src/telco_radar/report/templates/app.js` | Panel-Mechanik im Zeitreihen-IIFE (~200 Zeilen mit Kommentaren): Klick auf `.gr-zr-hit` ODER die erste `b.gr-zr-zahl` des Antwort-Satzes → `content.cloneNode` des Templates dieser Messung ins Panel; Toggle; Wechsel; Aktiv-Markierung in BEIDEN SVGs; Schließen bei Modell-/Bandwechsel; Enter/Space; ×-Knopf; `zrEingaengeRuesten()` (tabindex/role/aria-label/Cursor) nach jedem Blockwechsel + initial |
| `src/telco_radar/report/templates/style.css` | Panel + Postenliste + Summe + Beleg (Linien statt Kästen); `.gr-zr-hit{cursor:pointer}` + focus-Ring; aktiver Punkt `.gr-zr-aktiv`; klickbare Preiszahl `.gr-zr-zahl--klick` (gepunktete rote Unterlinie); mobil vier Abstriche im 700-px-Block |
| `tests/test_geraete_zeitreihe_panel_browser.py` | NEU, 8 Browser-Tests (tmp-Fixture aus `test_geraete_zeitreihe_ansicht._baue`, eigener HTTP-Server, echtes Chromium) |

Nicht angefasst: Kacheln/Karten (A3), `geraete_zeitreihe.py` (A1),
`data/state/` (nur gelesen). site/ habe ich für Selbsttests zweimal
komplett gerendert (immer mit `cfg`) — Lead entscheidet den Stand.

## Die 0-Operator-Regel (Abnahmekriterium)

Im JS wird keine Zahl gelesen, gerechnet, formatiert oder zusammengesetzt.
Das Panel entsteht ausschließlich aus `template.content.cloneNode(true)`.
Die einzigen im JS gebauten Zeichenketten: der statische Leer-Hinweis
„Zu dieser Messung steht kein Rechenweg bereit." (Fallback, wenn weder
Messungs- noch Näherungs-Template existiert), das „×" des Schließ-Knopfes
und aria-labels aus `data-anb`/`data-m` (Attribut-Montage, kein Formatieren).

## Die zwei Eingänge

- **Punkt-Klick** (Delegation auf `#gr-zr-gruppe`, überlebt Blockwechsel):
  `closest('circle.gr-zr-hit[data-m]')` → Template genau (anb, m).
- **Preis-Klick**: nur die ERSTE `gr-zr-zahl` des Satzes (Ø und Delta sind
  andere Aussagen). Anbieter-Erkennung NICHT per freiem Textparsing,
  sondern Abgleich des Textknotens vor der Zahl gegen die `data-anb`-
  Schlüssel des eigenen Blocks in den drei festen Satzformen von
  `_antwort_html` („X am günstigsten:", „führt X:", „führt nur X:").
  Geöffnet wird der LETZTE Messtag der Serie (DOM-last = jüngste, A1
  sortiert ISO) — zu „heute" gibt es kein Template (Schnittstellen-Empfehlung).

Fallback-Kette laut Schnittstelle: Template(anb, m) →
Template(Vodafone, 'naeherung') → statischer Hinweis. Letzterer trat im
Bestand nie auf (Vodafone überall mit eigener Historie).

## Messungen

- `pytest tests/test_geraete_zeitreihe_panel_browser.py -q`: **8 passed**.
  Kern: Panel-Inhalt == Template genau der geklickten (anb, m)-Kombination
  (zwei Darstellungen EINER Quelle); ×-Muster im Posten; Wächter: o2-Serie
  hat 3 Messtage, sonst wäre „genau diese" beliebig.
- Echte site/ im Chromium: Punkt-Klick Panel==Template **True**; Preis-Klick
  → congstar (der im Satz Genannte) · Messung vom 17.09. (letzter Messtag);
  Toggle schließt (hidden true); Wechsel wechselt; Enter auf fokussiertem
  Kreis öffnet; **0 Konsolenfehler**.
- Mobil 390 (Touch-Tap): Panel offen, `scrollWidth == 390` (kein Querscroll).
- Aktiv-Markierung: `getComputedStyle` = stroke **rgb(20,18,15) 2.8px** auf
  rotem Vodafone-Punkt (fill rgb(230,0,0)) — im Screenshot sichtbar
  bestätigt. ERSTER Versuch war Rot-auf-Rot (unsichtbar), das ist gemessen
  und geändert worden.
- `scripts/pruefe_portal.py`: **18 bestanden / 0 durchgefallen**, 11b
  (tco 2590 px) und 11c (Antwort-Satz 804 px, Falz 844) bestanden — das
  hidden-Panel kostet keinen Platz.
- Nachbarsuiten: zeitreihe/rechenweg/ansicht/seite **74 passed**;
  reiter/karten-band/o3-rollen **94 passed / 1 skipped**;
  seiten_zahlen/o2-zeilen-browser/leer_zustaende/tco_hauptansicht
  **154 passed**. (Ein zwischenzeitliches Rot in
  `test_keine_beschriftung_unter_zwoelf_pixeln` traf `gr-zr-k-name` =
  A3s Kachel-Baustelle mitten im Bau, lief danach grün; keine
  Panel-Klasse beteiligt.)

## Fallstricke, die der Test fangen musste

1. `scrollIntoView` auf ein `display:none`-SVG-Kind ist ein No-Op — der
   letzte Kreis im DOM gehört zum versteckten schmalen SVG. Gescrollt wird
   zum letzten Kreis MIT Fläche.
2. `elementFromPoint` außerhalb des Viewports liefert null — erst scrollen,
   dann Überlappung messen.
3. Hit-Flächen (r=12) überlappen bei dicht liegenden Serien (echter
   Bestand: Telekom/Vodafone 7,5 px auseinander am selben Tag); der Browser
   trifft den obersten Kreis. Tests klicken nur überlappungsfreie Kreise
   (`elementFromPoint === Kreis`), sonst messen sie einen anderen als den
   erwarteten.
4. A1s Fixture-Warnung „Posten ergeben 841, eingefroren ist 1300" ist
   Fixture-Kunst (Historie-gesamt ≠ Messfeld-Summe); das Panel zeigt die
   eingefrorene Zahl — A2 misst deshalb Panel gegen Template, nie gegen
   eine nachgerechnete Summe.

## Offene Sorgen

1. Die Preiszahl-Erkennung hängt am WORTLAUT von `_antwort_html` (drei
   feste Formen). Der Browser-Test hält sie fest, aber eine Umbenennung des
   Satzes bricht den Preis-Klick STILL (Punkt-Klick bleibt). Wer den Satz
   umformuliert, `zrAnbieterDerPreiszahl` mitdenken — oder ein `data-anb`
   an der ersten Zahl serverseitig setzen (wäre A1s Seite).
2. aria-label der Hit-Kreise nennt das ISO-Datum („Messung 2026-09-12"),
   bewusst nicht deutsch formatiert — Client formatiert nichts.
3. Der ×-Schließ-Knopf wird von JS erzeugt (statisch, kein Zahlbetrag);
   wer ihn serverseitig will, braucht eine Vorlagenentscheidung.
4. `scrollIntoView({block:'nearest'})` beim Öffnen verschiebt den Graph
   unter dem Cursor — der zweite Klick AUF DEN PUNKT trifft danach eine
   andere Stelle. Toggle über den Preis oder × ist unproblematisch; wer das
   beim Punkt stört, kann das Scrollen streichen (mobil war es der Grund).
5. Vorbestehend/parallel: `test_geraete_lifecycle` (Nachtlauf-Rot aus der
   Übergabe) nicht angefasst; site/ enthält A1+A3+meinen Stand gemischt.
