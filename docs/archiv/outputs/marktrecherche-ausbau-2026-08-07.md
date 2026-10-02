# Schlussliste: Ausbau & Beruhigung der Marktrecherche (07.08.2026, Abendsession)

Antonios Auftrag, in seinen Worten: das Layout zugänglicher machen („man
erkennt den roten Faden, weiß direkt, worum es geht, wirkt nicht unruhig —
unruhig durch die vielen Kommentare"), Differenzierung neu („gefällt mir
überhaupt nicht"), Promo-Übersicht neu („total unübersichtlich"), dazu zwei
neue Fähigkeiten: temporäre Highlight-Seiten zu Ereignissen und eine
dauerhafte Wettbewerbsseite für Deutschland mit historischem Kontext.
Farbe und Schrift bleiben („das gefällt mir sehr").

Fünf Pakete, jedes ein eigener Commit auf `claude/market-research-layout-f79o7q`:

| Commit | Paket |
|---|---|
| `936236f` | Wettbewerbsseite mit Chronik |
| `cc93917` | Highlight-Themen (Agent + temporäre Seiten) |
| `dc0bc2a` | Differenzierung als Karten-Radar |
| `891652c` (+`6895c89` WIP) | Promo Übersicht: je Marke ein Block |
| `150be9e` | Beruhigung über alle Seiten |

## Die Zahlen

- Tests: **540 → 656** (fünf neue Testdateien: test_wettbewerb 24,
  test_highlight_themen 19, test_differenzierung_view 22+,
  test_textwerkzeug 20+, dazu Erweiterungen in test_seiten_zahlen).
- `scripts/pruefe_portal.py`: **11 bestanden, 0 durchgefallen** — nach jedem
  Paket einzeln nachgemessen. Kriterium 5 (keine abgeschnittene
  Schlagzeile) prüft jetzt auch wettbewerb.html, differenzierung.html und
  die Themenseiten; Kriterium 8c misst die neue Promo-Wahrheit (jede große
  Karte trägt ein Motiv, nirgends ein leerer Bildkasten).
- Differenzierung: **71 statt 51 Beispiele** sichtbar (Merge der zwei
  Speicher; die 20 Kurator-Einträge hatten null Überschneidung mit der
  Sweep-DB und waren nie gerendert worden).
- Startseite: 9 782 → 8 787 px (Deutschland-Fokus 1 220 → 225 px);
  Meldungsseite 2 676 → 2 504 px bei gleichem Inhalt.
- 31 von 71 Differenzierungs-Begründungen trugen Vodafone-Ratschläge —
  alle gefallen, die Befunde stehen; 0 Empfehlungssätze auf der Seite.

## Echte Fehler, die dabei gefunden wurden (über das Layout hinaus)

1. **Der Presse-Kurator schrieb ins Leere**: `differentiation.jsonl` wurde
   von keiner Vorlage gelesen — Wochen an kuratierten Beispielen unsichtbar.
2. **`background` auf `loading="lazy"`-Bildern** malte 31 von 36
   Promo-Motiven als graue Kästen, solange nicht gescrollt war — der
   „leere Bildkasten" war eine CSS-Fläche, kein Datenfehler.
3. **Ein Promo-Motiv stand doppelt** (unveränderte Seiten behalten ihre
   Bilder aus früheren Läufen; die Einmal-Vergabe in promo_bilder wirkt nur
   je Lauf). Entdopplung sitzt jetzt in der Anzeige.
4. **`_first_sentence` zerschnitt Abkürzungen ohne Leerzeichen** („u.a.",
   „z.B.") auf Archivseiten — behoben durch die gemeinsame Satztrennung in
   `textwerkzeug.py`.
5. **Der Promo-Leitsatz** endete mitten im Text, weil ein Markenname
   („winSIM") klein anfängt und der Satztrenner einen Großbuchstaben
   verlangte.

## Neue Bausteine

- `src/telco_radar/textwerkzeug.py` — gemeinsame Textrechnung (Slug,
  Wortmengen, 1/Häufigkeit, Satztrennung mit Abkürzungsschutz,
  Vodafone-Ratschlagsfilter in zwei Strengegraden). Roter Faden,
  Kandidatensuche, Wettbewerbs- und Differenzierungsseite rechnen jetzt
  mit denselben Funktionen.
- `src/telco_radar/analyze/highlight_topics.py` + `report/thema.py` +
  `thema.html.j2` — Highlight-Themen (Details CLAUDE.md §5).
- `src/telco_radar/report/wettbewerb.py` + `wettbewerb.html.j2` —
  Wettbewerbsseite (Details CLAUDE.md §5).
- `src/telco_radar/report/differenzierung_view.py` — Merge + Kartenmodell.

## Offen / nach dem nächsten Actions-Lauf prüfen

1. **Der Themen-Agent lief noch nie gegen ein echtes Modell.** Die
   deterministische Kandidatensuche ist am Bericht vom 07.08. gemessen
   (fand Samsung Fold8, Starlink, Bharti Airtel und eine zu verwerfende
   Firmen-Gruppe „Deutsche Telekom") — ob der Agent richtig benennt und
   verwirft, zeigt erst das Log des nächsten Laufs.
2. Die Treffer-Karten der Archivsuche kürzen Überschriften JS-seitig mit
   „…" (app.js) — widerspricht der Schlagzeilen-Regel, kleiner Auftrag.
3. Telefónica/O2-Chronik enthält Spanien/UK-Meldungen (Movistar, VMO2),
   weil die Aliase in `focus_competitors` so konfiguriert sind — falls
   Antonio strikt Deutschland will, ist das eine Config-Frage.
4. Semantische Dubletten (dieselbe Story aus zwei Quellen) stehen sichtbar
   in Chronik und Differenzierung — semantisches Dedup bleibt Roadmap §10.
