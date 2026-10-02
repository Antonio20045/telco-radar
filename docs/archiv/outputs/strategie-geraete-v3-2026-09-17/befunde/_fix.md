# Fix nach adversarieller Prüfung: STRATEGIE_GERAETE_V3.md (17.09.2026)

Die 3 FAILs aus `_pruefung.md` (Punkte 2, 3, 4) sind minimal umgesetzt;
PASS-Bereiche unangetastet. Alle vier Test-Zitate vorab selbst nachgelesen
(s. u.). Nicht committet, `data/state` und `site/` unberührt.

## Geänderte Abschnitte

1. **§4 P4 Bau-Auftrag 2** (FAIL 2): „Faden-Umordnungen" in DREI
   Einzel-Aufträge geteilt — 2a Wochenkarte (Radar→Preisverlauf) ·
   2b Aufklapper „Bei Wettbewerbern gelistet" (Katalog→Radar) ·
   2c Sprungziele auf `modell_schluessel` — je eigener Bau- UND
   Prüfer-Agent. Inhalte unverändert, nur geteilt.
2. **§4 P1 Abnahme** (FAIL 3): messbare Kartengrenzen für F3 ergänzt,
   per Playwright gezählt wie design.md — Preiszahl je Karte ≥ 20 px;
   aktive Karte deutlich markiert (Rahmen ≥ 2 px oder Flächenänderung);
   alle 6 Karten im ersten Viewport bei 1440 UND 390.
3. **§4 P4 neuer Test-Absatz** (FAIL 4, vor der Abnahme): Inventur der
   vier rot werdenden Tests mit Vorher-rot je Auftrag:
   `test_geraete_seite.py:1148` (2a, `_radar()`-Zugriff) ·
   `test_wettbewerbsradar_alarme.py:213`/Assert `:223` auf
   `#tafel-katalog #gr-sortiment` (2b, bewusst auf `#tafel-radar`
   umgedreht — E3-Festnagelung kehrt, von F7 gedeckt) ·
   `test_geraete_export_mobil_browser.py:157` +
   `test_geraete_o4_export.py:86` (Auftrag 3, Export-Knöpfe in den Fuß).

## Verifikation der Test-Zitate (selbst gelesen)

| Zitat | Geprüft |
|---|---|
| `test_wettbewerbsradar_alarme.py:213` | Funktion; Assert `#tafel-katalog #gr-sortiment` in Zeile 223 ✓ |
| `test_geraete_export_mobil_browser.py:157` | „keine Export-Reihe im Kopf der Seite" ✓ |
| `test_geraete_o4_export.py:86` | „Knopf des Radars steht im Kopf der Tafel." ✓ |
| `test_geraete_seite.py:1148` | Funktion; greift Karte über `_radar(site)` an ✓ |

## Selbstprüfung: Forderung→Phase nach dem Fix

Zuordnungszeile §4 unverändert: F1→P4 · F2→P1 · F3→P1 · F4→P2 · F5→P3 ·
F6→P3 · F7→P4 · F8→P5. Die Teilung 2a–2c bleibt innerhalb P4 (F7), die
neue P1-Abnahmemesslatte stärkt F3 in P1, der P4-Test-Absatz verschiebt
keine Phase. **Jede der acht Forderungen bleibt eindeutig einer Phase
zugeordnet.**
