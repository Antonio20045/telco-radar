# P1 — Arbeitsnotiz Re-Check (17.09.2026, abends)

Re-Check-Prüfer, frisch und hart. Grundlage: `p1/fix.md` gegen
`p1/pruefung-sicht.md` + `p1/pruefung-code.md`. Nicht committet, nichts unter
`data/state` geschrieben (nur gelesen); `site/` einmal frisch mit `cfg`
gerendert (Hausregel), app.js/style.css danach byte-identisch mit
`templates/` (md5 geprüft).

## Was ich getan habe

1. **Site frisch gerendert** (immer mit cfg), Fragment 3.555.755 B —
   deckungsgleich mit fix.md.
2. **Server 127.0.0.1:8765** auf `site/`, Playwright/Chromium 1440×900 und
   390×844 (touch), echte Klicks/Taps gegen die ECHTE Site (nicht Fixture).
3. **Jeden Sicht-Befund nachgestellt** (Skripte /tmp/p1_recheck_{desktop,
   desktop2,mobil}.py): A1–A3, A5, B2–B4, Verb. 11/12/15, S3-1, S3-2
   (Fehlerinjektion an ECHTEM o2-Paar apple-iphone-14-128/mittel, 6 Messtage).
4. **Code-Stichproben**: zrOeffneNach-Wunsch, setzeKartenBand, S3-3-Logik,
   0-Operatoren-Suche über die P1-JS-Zeilen, karten_baender/S3-4 in
   geraete_zeitreihe.py, Halo-DOM-Reihenfolge im Fragment.
5. **Suite**: geänderte Dateien 201 passed; `-k geraete` 1413/3/6 (die 3
   Roten vorbestehend: Adapter-Tablets, Lifecycle-Nachtlauf,
   iPhone-18-Querlinks — keine P1-Datei im Spiel). **pruefe_portal.py:
   18/0/0**, 11c = Antwort 805 px, Graphkopf 834 px ≤ 844.
6. Eigene Beweis-Screenshots `p1/screenshots/recheck-*.png` (1440 Karten+Panel,
   Panel Band groß, 390 Panel).

## Eigene Messfehler auf dem Weg (dokumentiert, kein Befund)

- Balken: erst die SPUR gemessen (fast konstant, flex-Layout) — die Füllung
  `<i>` trägt serverseitig `width:32.9%` etc. Nachgemessen, korrekt.
- Karten-Punkte: falscher Selektor (Punkte tragen `gr-zr-k-punkte
  gr-zr-k-band` auf DEMSELBEN Element); korrekt: 4×10 px in Hausfarben.
- „Graphkopf 916": das SVG, nicht die Messtag-Zeile — 11c misst
  `.gr-zr-messtage` (834). Prüfe_portal bestätigt.

## Offene Sorgen (an den Lead)

1. **B1/A4 brauchen Lead-Entscheidungen** — fix.md hat Messwerte und je drei
   Optionen; meine unabhängige Nachrechnung BESTÄTIGT den B1-Konflikt
   (Karten 608–700 als Wischreihe, Antwort endet 804,6 — ein 2×3-Grid
   (+≈205 px) schreibt die Antwort auf ≈1010 ≫ 844 und bricht 11c, den
   harten Test). Die P1-Messlatte „alle 6 Karten im 390-Viewport" ist mit
   11c bei KEINER Blockfolge vereinbar (auch Karten-unter-den-Antwort-Satz
   löst sie nicht — die Wischreihe bleibt).
2. Fragmentgröße gesamt +2,42 MB über E2 — PM-6/P5-Entscheidung mit dieser
   Zahl fallen.
3. tmp_nachpruef/ existiert noch (in .gitignore Zeile 14; Löschen wurde
   mangels Berechtigung abgelehnt) — beim Commit unschädlich, aufräumen
   lohnt.

## Reste, die ich gefunden und NICHT gebaut habe (siehe recheck.md)

R1 Lücken-Preis klickbar (stärkster Rest), R2 Panel mobil 11,5 px,
R3 _bewegung-Docstring, R4 Halo ohne data-anb, R5 „—" ohne Punkte-Indikator,
R6 Tab-Stops (bewusste Fix-Entscheidung).

Server am Ende gekillt.
