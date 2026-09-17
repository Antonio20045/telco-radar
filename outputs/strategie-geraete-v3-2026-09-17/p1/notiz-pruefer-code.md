# Notiz Prüfer CODE (P1), 17.09.2026

Adversarialle Code-Prüfung des fertigen P1-Stands (Working Tree gegen
HEAD 9f5235d). Nichts geändert, nichts committet, nichts unter
data/state geschrieben; site/ nicht neu gerendert (die Agenten-Renders
standen byte-stabil da, Sync site/ vs templates/ per diff -q geprüft:
identisch).

## Was ich nachgerechnet habe

1. **Posten x Faktor = Summe**: ALLE 2562 Zeilen der
   `data/state/geraete_tco_historie.jsonl` unabhängig nachgerechnet
   (0 Abweichungen, 0 Zeilen ohne Tarifposten) + 49 Template-Stichproben
   aus dem gerenderten Fragment gegen die JSONL (27 eindeutig, 22
   SKU-Dubletten mit identischer Zahlmenge). 1285 Templates == 1285
   Punkte == Hit-Kreise je Block. Posten-Schlüssel in `_rechung` exakt
   die f-Strings von `tco_24`.
2. **0 Rechenoperatoren im JS**: app.js-Diff komplett gelesen — nur
   Index-/indexOf-Logik und Attribut-Montage; Panel entsteht per
   `importNode` (Browser-Test prüft isEqualNode).
3. **Günstigste-Regel / Ranking**: strikt `<` unverändert; Kachel-Ranking
   (Anbieter vor Punkte, KACHELN_MAX=6) unverändert; `meta`-Feld nur
   Anzeige.
4. **Tests**: Diffs gelesen (Falztest umgestellt und SCHÄRFER: bottom
   <= 844 statt Höhe <= 96; Karten-Zahlen mit get_text OHNE Trenner;
   Panel-Zahlen gegen zweiten Aufbereitungs-Lauf mit Negativ-Gegenprobe).
   Suite `-k geraete`: **1402 passed / 3 failed / 6 skipped** — dieselben
   3 wie bei A4 (iPhone-18/Auto-Datenstand + Nachtlauf; Ursachen-Dateien
   nicht im Diff, A4 hat sie am HEAD-Worktree bewiesen, Fehler-IDs
   bestätigen die Diagnose).
5. **Randfälle**: fehlendes #gr-zr-panel / #gr-zr-gruppe (IIFE-Guard
   vorbestehend), Fragment-Fehlerfall (Panel bleibt — dokumentiert),
   Band ohne Messtag, unbegrenzte Tarife (kein Band — korrekt).

## Befunde (Details in pruefung-code.md)

0 S1, 0 S2. Fünf S3: (1) Panel-Labels 11 px unter der 12-px-Regel, von
beiden 12-px-Tests unerreichbar (Templates nicht im DOM, Panel erst nach
Klick); (2) Fallback-Kette zeigt bei fehlendem Template die Vodafone-
NÄHERUNG auch für fremde Anbieter-Messungen (dokumentiert in
schnittstelle-rechenweg.md, aber falsche Antwort im Fehlerfall);
(3) `zrEingaengeRuesten` stylt die erste Preiszahl bedingungslos klickbar
(tabindex/title), auch ohne Template — Bedienelement ohne Wirkung im
Randfall; (4) Karte mischt zwei Maße (ab-Preis über ALLE Bänder, Delta
aus dem Leit-Paar) ohne Kennzeichnung; (5) tmp_nachpruef/ (19 MB
Site-Snapshot, untracked, nicht in .gitignore). S4 gebündelt: 5-Arg-
Closure `_posten`, Modul wächst um dritten Belang, U+2212/ASCII-plus
gemischt in derselben Kartenzeile, `_euro0` half-even-Rundung,
Fragment +1,84 MB als Lead-/P5-Entscheidung (PM-6).

## Offene Sorgen

- Fragmentwachstum ist Faktor 6 über der Strategie-Erwartung — Zahl ist
  dreifach dokumentiert (A1, A4, hier bestätigt), Entscheidung PM-6/P5.
- A2s Sorge 1 (Preiszahl-Erkennung hängt am Antwort-Satz-Wortlaut) teile
  ich; Test hält es, Umbenennung bricht den Preis-Klick still.
