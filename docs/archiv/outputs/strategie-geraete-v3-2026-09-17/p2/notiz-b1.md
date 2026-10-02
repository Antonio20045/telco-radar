# P2 / B1 — G2 gelöscht (toter Code mit weg, E5-Regel, Präzedenz setzeG0)

Auftrag: G2-Chart im Reiter „Preisverlauf" löschen inkl. totem Code;
`test_geraete_verlauf.py` unberührt lassen; Reiter-Gerüst (h2, Wähler,
Diagramm/Tabelle) bleibt für B2. Basis: `STRATEGIE_GERAETE_V3.md` P2,
`befunde/preisverlauf.md`. Stand: Suite **3191 bestanden / 12 skipped /
0 gefallen** (3 vorbestehende deselected, alle am HEAD nachgemessen:
Querlink-iPhone-18, Netzbetreiber-Tablets, Lifecycle-Nachtlauf);
`pruefe_portal.py` **18 bestanden / 0 durchgefallen**.

## Was fiel (Messzahlen, `git diff --numstat`)

| Datei | +/− | Inhalt |
|---|---|---|
| `report/geraete_tco_grafik.py` | +12 −298 | `historie`, `_ereignisse`, `_reihenrang`, `MAX_REIHEN`, `MIND_PUNKTE`, `G2_*`-Konstanten, ganzes SVG-Rendering. **`_tag` blieb** (12 Zeilen, nach oben gezogen): `zeitreihe`/`_tage_dieses_geraets` nutzen es (Zeilen 537/706) — grep vor dem Löschen, wie verlangt |
| `report/geraete_tco_karten.py` | +7 −51 | `historienreihen` (49 Zeilen) + `messtage`-Import (einziger Nutzer war die Funktion). Der Wähler rechnet `geraete_verlauf.reihen_fuer_listungen` + `messtage` — NICHT angefasst |
| `report/geraete_tco_view.py` | +6 −6 | `g2`-Berechnung, `"g2"`-Rückgabe, `leer()`-Eintrag. Signatur unverändert (`historie`-Param bleibt, dokumentiert) |
| `templates/geraete.html.j2` | +26 −98 | G2-Block (figure+figcaption, Ereignis-Satz, Tabelle „Daten dieser Kurven", G2-Leerzustand) + Macro `g2_ausgelassen`; P2-Kommentar an derselben Stelle (wie E3 bei G0) |
| `templates/style.css` (+ `site/style.css`) | +10 −21 je | 7 G2-Regeln (`.gr-g2-raster/-achse/-linie/-punkt/-marker/-legende`), `.gr-g2` aus 2 geteilten Selektoren, 4 Kommentare |
| Tests (8 Dateien) | −228 netto | siehe unten |

Netto Produktionscode (ohne Tests/Site): **−329 Python-Zeilen, −72 Vorlagen-Zeilen**.

## Die 4 Textblöcke, die nur G2 dienten

Befund-Zählung (sichtbarer Fließtext, ohne Tabellen/Aufklapper/SVG/JSON),
an `site/geraete.html` HEAD vs. neu gemessen — **187 → 73 Wörter**:

| Block | vorher | nachher |
|---|---|---|
| h2 „Wie sich der Barpreis…" | 8 W. | 8 W. (bleibt) |
| Erklär-Satz „Die Kurve zeigt den Barpreis…" | 31 W. | 31 W. (**B2**: fällt/Aufklapper) |
| figcaption „5 von 127 Reihen…" | 40 W. | **gefallen** |
| Ereignis-Satz „Erhöhungen und Senkungen…" | 74 W. | **gefallen** |
| `#gr-vleer` „Wählen Sie oben ein Gerät" | 15 W. | 15 W. (**B2**: Auto-Vorauswahl) |
| `#gr-vstand` „Preisverlauf wird seit… erfasst" | 19 W. | 19 W. (**B2**) |

(Der Befund nannte 194 W. — Datenlage wanderte; Struktur identisch.)
Strategie-Ziel „< 60" greift nach B1 allein noch nicht — die restlichen
73 W. sind B2s Auftrag (Erklär-/Stand-/Leer-Satz).

## Der „Datenblock unter der Grafik": gemessen statt geraten

Die Aufgabe nannte „1813 Zeichen" — kein Block misst das exakt. Messung:
`details#gr-g2-tabelle` („Daten dieser Kurven") ist mit **3237 Zeichen
gerendert** (1400 Zeichen Vorlage) der einzige Datenblock unter der Figur
und dient **ausschließlich G2** → komplett gefallen. Der JSON-Knoten
`#gr-verlaufdaten` (**117 156 Zeichen**) dient dem **Wähler** → blieb
(unverändert an alter Stelle).

## Tests

- **12 Tests vollständig entfernt**: `test_geraete_tco_hauptansicht.py`
  7 G2-Tests (zeichnet_nur/bleibt_leer/traegt_tabelle/bewegte_vor_flachen/
  ereignisse_grundmenge/rangfolge_echter_bestand/wochenraster) und
  `test_geraete_preis_mehrdeutig.py` 5 G2-Tests (historienreihen,
  kein_pfeil, laut_mehrdeutigen, mehrdeutigkeit_aus_reihe,
  bildunterschrift).
- **4 angepasst**: Slug-Test (C.3) auf `zeitreihe` umgezogen (gleiche
  `gr-anb--`-Klasse, Graph lebt); Render-Test „messluecke" auf
  `#gr-verlaufdaten` reduziert (Regel lebt im Wähler weiter);
  Rollbehälter-Browser-Test Tabellenzahl **4 → 3** (die vierte war die
  G2-Tabelle — fiel erst im Browser auf, Sperre zählt `table.gr-ttab`);
  o3_rollen (+browser): tote G2-Alternativen aus den „lebendig"-Bedingungen.
- **`test_geraete_verlauf.py` unberührt** (21/21 grün, im Lauf enthalten).

## pruefe_portal.py Kriterium 11 — der Befund las die Bedingung falsch

`befunde/preisverlauf.md` behauptete „Bedingung ist svg.gr-g2 ODER
#gr-verlaufdaten → bleibt grün". Falsch: die alte Bedingung meldete einen
**Mangel, wenn das G2-SVG FEHLT** (und verlaufdaten da ist) — gegen das
neue site/ nachgemessen: **wäre ROT geworden** („G2 fehlt im
Historie-Reiter"). Neu: Kriterium prüft `#gr-verlaufdaten` ODER den
Leerzustand „liegen noch keine Messreihen vor", plus
**Rückkehr-Wächter** wie beim G0-Block (kehrt `svg.gr-g2` zurück, ist die
Doppel-Darstellung zurück — Antonio F4).

## Übrige Messzahlen

- **`gr-g2` im gerenderten `site/`: 0** (geraete.html vorher 61, style.css
  vorher 10 Vorkommen); `#gr-verlaufdaten` steht 1×, h2/Wähler/Diagramm-/
  Tabellen-Gerüst unverändert.
- **Reiterhöhe (11b-Methodik, Klick auf Reiter, 1440×900): 1779 → 1248 px**
  (−531 px, −30 %). `pruefe_portal.py` 11b: „verlauf 1248 px", Budget 3000.
- Export „Preishistorie" unangetastet (`geraete_export`, Tests grün);
  `geraete_verlauf.messtage` unangetastet.
- Renderprobe: `render_site(…, cfg)` lief sauber durch.

## Für B2 (Anschlussstellen)

- Reiter startet jetzt direkt mit h2 → Erklär-Satz → Suchfeld. B2 zieht
  den Wähler hoch (`app.js` `gewaehlt = null` → erstes Gerät, iPhone 17
  256 GB steht laut Befund schon an Platz 1 der Sortierung) und kürzt
  Erklär-/Stand-/Leer-Satz (31+19+15 W.).
- 3 Browser-Tests nageln „Wählen Sie oben ein Gerät" fest (laut Strategie:
  `test_geraete_reiter_browser.py:954,1125`, `test_geraete_o3_rollen_browser.py:361`).
- Der P2-Kommentar in der Vorlage („G2 IST GEFALLEN") dokumentiert den Fall
  am Platz des Blocks — wie der E3-Kommentar für G0.

## Bewusst nicht angefasst

`test_geraete_seite.py:1396` „(G2)" — meint die Ausbaustufe-2-Sektion
„Wer ist günstiger als Vodafone?", nicht den Chart. CSS-Kommentar
`(G2, 28.08.2026)` bei ebendieser Sektion ebenso. `geraete_tco_view.
historie_lage` bleibt gerechnet (E3-Entscheidung, kein Vorlagen-Leser).
