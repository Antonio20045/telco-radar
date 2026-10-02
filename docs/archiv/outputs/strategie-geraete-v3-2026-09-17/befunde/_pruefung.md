# Adversarische Prüfung: STRATEGIE_GERAETE_V3.md (17.09.2026)

Geprüft gegen die sechs Befunddateien, HEAD `9f5235d`, `site/`-Stand
17.09. 12:59. Eigene Nachmessungen unten; alles andere mit Quellenangabe.

**Ergebnis: 3 FAIL (Punkte 2, 3, 4) — nicht durch.** Die Mängel sind
Text-Lücken im Strategiedokument, je in Minuten fixbar; Substanz und
Zahlenbasis des Dokuments halten der Prüfung stand.

## 1. Forderungs-Deckung — **PASS**

| F | Forderung (Kern) | Phase | wörtlich? |
|---|---|---|---|
| 1 | Design/Ruhe/wenig Text | P4 (+P2/P3 löschen Text) | ja, Zitate ungeschönt |
| 2 | Preis-Klick = Rechenweg je Messung | P1 (Auftrag 1+2) | ja, „70×24"-Beispiel transportiert |
| 3 | vorgeschlagene Smartphones prominent | P1 (Auftrag 3) | ja |
| 4 | oberen Graph löschen, Wähler nach oben | P2 | ja, wörtlich |
| 5 | Katalog: Preis in jede Zeile | P3 (Auftrag 1) | ja |
| 6 | TCO-Umschalter IM Katalog, keine Unterseite | P3 (Auftrag 2) | ja, „keine neue Unterseite" steht |
| 7 | roter Faden | P4 (Auftrag 2) + Zielbild §3 | ja |
| 8 | Automatik, nie wieder ändern | P5 + §6/§7 | ja |

Keine Abschwächung, keine Weichformulierung; F6 explizit als Antonios Lösung
benannt. Anmerkung: F1 (der lauteste Schmerz) fällt als LETZTE inhaltliche
Phase an — Begründung (Design über fertige Struktur) trägt, aber der Lead
muss diese Reihenfolge gegenüber Antonio vertreten können.

## 2. Phasen klein genug? — **FAIL**

Aufträge je Phase: P1:4 · P2:3 · P3:4 · P4:5 · P5:5 — keine Phase > 6. ✓
Aber **P4 Auftrag 2 („Faden-Umordnungen") enthält mehr als eine klare
Aufgabe**: Wochenkarte Radar→Preisverlauf UND Aufklapper Katalog→Radar UND
Sprungziel-Vereinheitlichung über app.js — drei Handlungen an drei Reitern,
kein gemeinsamer Ort; ein Agent bräuchte drei Kontexte (Meta-Regel verletzt).
P4-1 (SVG + Rot-Deckel + Legende) ist dagegen EINE Aufgabe: derselbe Ort,
derselbe Zweck (Tafel liest sich als Bild).
**Fix:** P4 Auftrag 2 in drei Einzel-Aufträge teilen (Wochenkarte ·
Aufklapper · Sprungziele), jeder mit eigenem Prüfer.

## 3. Abnahmen messbar? — **FAIL**

P2, P3, P4, P5: durchgehend messbar (SVG-Zahl, Regex, ≤-Grenzen,
Playwright-Messwerte, Wortzahl, Protokollzeilen). ✓
**Ausnahme F3:** P1s Abnahme misst nur Panel-Klick, Falz (11c),
Fragmentgröße, JS-Operatoren — für die prominenten Modell-Karten (eine der
8 Forderungen, „richtig geiles Design") gibt es KEIN messbares Kriterium;
design.md Regel 1 (größte Schrift) greift erst in P4. Ein Prüfer-Agent hat
keine Messlatte für „prominent" und kann nur „sieht anders aus" prüfen.
**Fix:** In die P1-Abnahme Kartengrenzen aufnehmen (z. B. Preiszahl der
Karte ≥ 20 px, aktive Karte deutlich markiert [Rahmen ≥ 2 px oder Flächen-
änderung], alle 6 Karten im ersten Viewport bei 1440 UND 390 — gezählt per
Playwright wie design.md).

## 4. Repo-Regeln — **FAIL (ein Konfliktblock, sonst sauber)**

Sauber: kein Client-Rechnen (P1: „0 Rechenoperatoren im JS", Templates vom
Server); Preisarten nie mischen, Zustand im Schlüssel (P3); neue Zahlen →
`test_seiten_zahlen.py` OHNE get_text-Trenner (P1-4, P3-3); kein State-/site-
Commit; Veröffentlichungsschwellen unberührt; Telekom-202 als
Antonio-Entscheidung markiert; Test-Kippen in P2/P3 transparent begründet.
**Konflikt: P4 hat KEINE Test-Inventur, obwohl seine Verschiebungen vier
benannte Tests still rot machen** (selbst nachgelesen):
- `test_wettbewerbsradar_alarme.py::test_bei_wettbewerbern_gelistet_steht_im_geraetekatalog`
  fordert `#tafel-katalog #gr-sortiment` — ein Folge-Test VERBIETET den
  Aufklapper auf dem Radar; P4-Auftrag 2 verschiebt genau dorthin.
- `test_geraete_export_mobil_browser.py:157` („keine Export-Reihe im Kopf")
  und `test_geraete_o4_export.py:86` („Knopf … im Kopf der Tafel") bei
  P4-Auftrag 3 (Export-Knöpfe in den Fuß).
- `test_geraete_seite.py::test_alte_preisbewegung_steht_nicht_unter_diese_woche`
  greift die Wochenkarte über `_radar()` an — bricht bei Verschiebung in den
  Preisverlauf.
P2 und P3 führen diese Disziplin exakt vor (Test-Dateien + Zeilen +
NICHT-brechen-Liste); ausgerechnet die breiteste Phase hat keinen solchen
Absatz. Das ist die Fehlerklasse „grüner Lauf, rote Suite beim Lead-Merge".
**Fix:** P4 einen Test-Absatz geben, der diese vier Tests nennt und bewusst
umstellt (Vorher-rot-Vorhersage je Auftrag, wie P2 es vormacht).

## 5. Textlast (F1: „keinen Text sehen") — **PASS**

P1-Panel ist eine gesetzte Rechung (Posten × Anzahl = Summe), keine Sätze;
Variante V3 (Zeilen) ausdrücklich verworfen. P2/P4 löschen bzw. deckeln
Text; P3s Leerzustände sind Labels („kein Bündel gemessen"); P5 schreibt
nur Protokollzeilen und CLAUDE.md (Off-Page). FM 4 nennt den Preis-Klick
selbst als Härtetest. Keine Stelle verlangt neuen Fließtext auf der Seite.

## 6. Streichungen ohne Antonio-Deckung? — **PASS (eine Warnung)**

Gestrichen: G2 (F4 wörtlich), Textblöcke (F1), Ereignis-Satz (fällt mit G2;
Info lebt in der Radar-Tafel weiter — P4 baut sie zur Grafik um). Wochenkarte
und Aufklapper werden verschoben, nicht gestrichen (F7). Als „bewusst nicht"
markiert: Radar-Tabelle, Export-CSVs, Portfolio, Quellen-Fußlink; FM 5 führt
Streich-Kandidaten NUR als Antonio-Entscheidung. Warnung: P4-Auftrag 4 lässt
die „Verfügbar"-Spalte optional FALLEN — ohne Antonio-/Lead-Markierung; die
Option gehört als Entscheidung markiert (die 90× „keine Angabe" sind F1-
Rauschen, aber Antonio hat die Spalte nicht namentlich kritisiert). Die
Aufklapper-Verschiebung kehrt zudem eine dokumentierte E3-Test-Begründung um
— von F7 gedeckt, aber gehört in den P4-Test-Absatz (Punkt 4).

## 7. Betrieb / Premortem abgedeckt? — **PASS**

FM 1 → P5-1/3 + Tag-2-Sichttest + „Auto: 0 an 2 Tagen = Alarm" (§6); FM 2 →
P5-2 (Ausfall-Schwelle 7 Tage + Provider-Proben je Lauf); FM 3 → P5-4
(PM-6-Deckel ab 01.10. datenbasiert, als Test verankert; P1 protokolliert
Fragmentgröße davor/danach); FM 4 → P4-5 (Zeichen-Deckel in pruefe_portal +
Bau-Regel); FM 5/6/7 → §7 mit Antonio-Markierungen und Rest-Risiken ehrlich
(nicht codebar). Kein FM unversorgt.

## Eigene Nachmessungen (diese Prüfung)

| Messung | Ergebnis | Strategie sagt |
|---|---|---|
| `site/geraete.html` | 1 406 611 B | 1,40 MB ✓ |
| `site/data/geraete-zeitreihe.html` | 1 132 101 B | 1,13 MB ✓ |
| `site/data/geraete-buendel.html` | **1 258 158 B** | 1,17 MB (Befund-Messzeitpunkt; Fragment wächst täglich — belegt FM 3; Gesamtlast ≈ 3,8 MB) |
| „ohne Preis" in site/geraete.html | 36× | 36× ✓ |
| iPhone 18 in Seite, 2 Fragmenten, 4 CSVs | **0 Treffer** (8 Dateien) | 0 ✓ |
| `AUTO_SICHTBAR_AB_MESTAGEN` | `= 2`, Zeile 82 (Nutzung 679/686) | ✓ |
| `gr-g2` in site/ | 1 SVG vorhanden | ✓ (P2 löscht es) |
| Leersatz-/Leerzustand-Tests | 3 bestätigt: `reiter_browser.py:954,1125` prüfen `#gr-vleer` sichtbar + 0 SVG, `o3_rollen_browser.py:361` wörtlich | ✓ |
| „Vodafone-Basis" | heute **60×** | 48× (design.md-Messzeitpunkt; im P4-Umbau neu zählen) |

## Verdict

`durch = false`, `fails = 3` (Punkte 2, 3, 4). Alle drei Fixes sind
eine Zeile im Strategiedokument; danach steht einer Umsetzung nichts im Weg.

— Adversarialer Prüfer, 17.09.2026
