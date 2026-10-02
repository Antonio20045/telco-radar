# P3-Fix — Befunde aus pruefung-code.md und pruefung-sicht.md

Datum: 18.09.2026, gegen HEAD `64a8f2a` + uncommitteten P3-Arbeitsdiff.
Nichts committet, nichts unter `data/state` geschrieben (git status data/ leer).

## Behoben

### S2-1 (Code) — unlesbarer Bündel-Store fiel auf „ohne Preis" zurück

- `geraete_view._buendel_aus_listungen()` (neu): Bündel-Sätze im Store-Format
  aus den LISTUNGEN (`preis_mit_vertrag_ab` + `tarif_referenz`, Beleg = 
  Quelllink der Listung). `aufbereiten()` hält den Katalog konditional:
  `tco_db.buendel() if tco_db.lesbar else _buendel_aus_listungen(bestand)`.
- Tests: Unit (`test_unlesbarer_store_fraegt_die_listungen_ab_s2_1`, 12 Feld-
  Asserts inkl. Beleg) + E2E an der Fixture (`test_der_katalog_uebersteht_
  einen_unlesbaren_tco_store`: Store kaputt schreiben, neu rendern →
  0× „ohne Preis", „nur im Bündel, ab 32,99 €/Monat" steht noch da).
- Simulation des Prüfers bestätigt: Vorher 37 Aufklapperzeilen „ohne Preis" +
  1 Modellzeile „kein Preis gemessen"; nach Fix 0.

### Sicht Wesentliches 1 — Sortierung hing nach Ansichtwechsel an unsichtbarer Spalte

- Vorher (live gemessen, `fix_mess_mehr.py`): nach „Einzelgerätepreis" (ab)
  sortiert + Wechsel auf TCO → aktiver Kopf unsichtbar, TCO-Werte
  3357,66 / 2705,66 / 2927,80 € — nicht monoton.
- Fix (`app.js`, zwei Blöcke): der Ansichts-Umschalter meldet `gr-ansicht`
  als Event; `grFilterleiste` mappt die Hauptpreisspalte
  (preis ↔ tco, Erstklick-Richtung) und stellt jede andere Sortierung
  (Händler/Spanne nur Barpreis, Ø/Delta nur TCO) auf die SERVER-Ordnung
  zurück (beim Laden gesicherte DOM-Reihenfolge; `data-vor`/`aria-sort`
  werden mit zurückgesetzt — kein Pfeil über einer toten Spalte).
- Nachher (live, `fix_mess_live.py`): Fall 1 aktive Spalte `tco`, sichtbar,
  monoton fallend 3357,66 → 2927,80 → 2705,66 → 2243,66 → 2051,80.
  Fall 2 (delta → Barpreis): 0 Pfeile, Ordnung == Server-Ordnung
  (iPhone 17 Pro / Fairphone 6 / Pixel 11 / Nothing Phone (3)).
- Browser-Test `test_p3_der_ansichtwechsel_nimmt_die_sortierung_mit` prüft
  beide Fälle. Fallstrick dabei gefunden und behoben: `dataset.geraet` liest
  `data-geraet`, das Attribut heißt `data-s-geraet` — der Ordnungsvergleich
  hätte zwei leere Listen verglichen („Test prüft nichts"-Falle); der Test
  assertet jetzt, dass die Namen wirklich ankommen.

### Sicht Wesentliches 3 — stummes „–" in der Delta-Spalte benannt

- Vorher: 57 von 111 Zeilen mit „–" (38 mit TCO ohne Referenz, 19 bündellos),
  Grund stand nur „im Reiter Vergleich".
- Nachher (Template): `{% elif m.tco_ab is not none %}` → sichtbares
  „keine Referenz" (gr-a-klein) + title „Vodafone listet dieses Modell
  nicht - deshalb ist kein Abstand berechenbar". Bündellose behalten „–",
  weil ihre TCO-Zelle den Grund schon nennt.
- Gerendert gezählt (BeautifulSoup, 111 Modellzeilen):
  **54 Wert + 38 „keine Referenz" + 19 stumm „–"** — exakt die
  Prüferverteilung. Test: `test_die_delta_spalte_benennt_ihren_leergrund`.

### Sicht Kleineres 4 — Spanne „–" bei Ein-Händler-Modellen

- Nachher: `anbieterzahl == 1` → „ein Preis" statt „–". Gerendert:
  **49 Spanne + 40 „ein Preis" + 22 „–"** (= 62 ohne wesentliche Spanne,
  konsistent mit dem Prüfer). Test:
  `test_ein_haendler_heisst_in_der_spanne_ein_preis` (mit Gegenprobe:
  Apple-Modell zeigt die echte Spanne „1.000,00 € – 1.100,00 €").

### Sicht Kleineres 5 — Erklärsatz 33 → 18 Wörter

- „Eine Zeile je Modell; der Umschalter darüber wählt Einzelgerätpreis oder
  Gesamtkosten über 24 Monate (TCO-24). Alle Listungen des Modells stehen
  unter der Zeile." (18 Wörter, vorher 33). Kein Test zitierte den alten Satz.

### S4-1 (Code) — Export „Tarifband" im Klartext

- `geraete_export.modell_tco_csv` schreibt jetzt `band_label(...)` (O4-Regel):
  gerenderte CSV **48 Klein / 41 Mittel / 3 Groß / 19 leer** (= bündellose,
  konsistent). Assert im Export-Test auf „Klein" umgestellt.

### S4-4 (Code) — render_site-ohne-cfg-Falle benannt

- Kommentar an der Fixture `_geraete_katalog_site`: bewusst ohne cfg, NUR
  hier zulässig, beim Kopieren in eine Welt mit watchlist/news_sources
  `load_config(root)` mitgeben (CLAUDE.md §6).

### S4-6 (Code) — Guard-Kommentar an `_tco_spalte`

- Kommentar an `min(kandidaten, ...)`: kein `laufzeit == 24`-Filter, weil
  `laufzeit` seit TCO24-1 Konstante 24 ist ({24: 506, None: 188}); wird sie
  wieder variabel, MUSS dort gefiltert werden.

## NICHT behoben — mit Begründung

### Sicht Wesentliches 2 — Mehr-Button ohne Zustandswechsel: NICHT REPRODUZIERBAR

- Eigene Browser-Messung am gerenderten site/ (1440, `fix_mess_mehr.py`):
  vor Klick sichtbar (computed display:block); nach Klick
  `absatz_hidden: true`, `sichtbar: false`, **computed display:none**,
  `gr-alarm--alle: true`. Der Button VERSCHWINDET korrekt (Option „Button
  verschwinden lassen" des Prüfers ist der seit C3 vorhandene Zustand);
  ein zweiter Klick ist gar nicht möglich. Keine CSS-Regel schlägt `[hidden]`
  (`.gr-erklaer` trägt kein display; geprüft style.css:1985). Der
  Prüferbefund trifft am aktuellen Stand nicht zu — kein Fix gebaut.
  Ein Toggle („nur 12 zeigen") wäre ein neues Bedienelement, kein Fix.

### S4-2 — Export-Knopf-Einheiten inkonsistent

- E5-Rest, von C3 selbst zur Debatte gestellt. Beschriftungs-Konsistenz über
  alle 6 Knöpfe ist Design (P4 „Klicken und Etiketten") → **Lead-Entscheidung**.

### S4-3 — Test konsumiert private `_katalog_zeile()`

- Bewusst gelassen: `_katalog_zeile` ist dokumentiert privat („zwei Kopien
  wären die Lücke"); eine öffentliche Hülle nur für den Test tauschte den
  Befund gegen eine zweite API. Bei Umbau der Zeile fällt der Test rot —
  genau das will er.

### S4-5 — `len(DATEIEN)` statt hart

- Der bestehende Assert vergleicht die MENGE exakt
  (`ziele == {f"exporte/{n}" for n in DATEIEN}`): schrumpft DATEIEN still,
  fällt der Mengenvergleich (die Seite liefert weiter alle Links). Ein
  zusätzliches `== 6` verdoppelte nur die Zahl. Keine Änderung.

### Sicht Kleineres 6 — klebriger Modell-Spaltenkopf mobil (sticky)

- Nice-to-have laut Prüfer, kein Fehler. CSS-Änderung an der Rolltabelle →
  **Lead-/P4-Entscheidung** (Design-Durchlauf „Ruhe und roter Faden").

### Sicht Kleineres 7 — die 19 „kein Bündel gemessen"-Zeilen sammeln

- Ordnungsfrage der Server-Ordnung (Interleave je Hersteller, B5) — P4
  Auftrag 2c verhandelt genau die Modell-Ordnungen neu (88/97·111·321).
  Vorab-Sammeln hier würde P4 entgegenlaufen → **Lead-Entscheidung**.

## Messzahlen (Zusammenfassung)

| | vorher | nachher |
|---|---|---|
| „ohne Preis" im Katalog (Normalbetrieb) | 0 | 0 |
| „ohne Preis" bei unleserlichem Store (Simulation) | 37+1 | **0** |
| Delta-Spalte: stumm / benannt | 57 / 0 | **19 / 38** (+ 54 Werte) |
| Spanne: „–" / Aussage | 62 / 49 | **22 / 49+40** |
| TCO-Werte nach Ansichtwechsel | nicht monoton | monoton fallend, Pfeil sichtbar |
| Export Tarifband | klein/mittel/gross (raw) | Klein/Mittel/Groß |
| Erklärsatz | 33 Wörter | 18 Wörter |
| Reiterhöhe Katalog (11b) | — | 1924 px (Budget 3000) |
| Mobil 390 | — | scrollWidth 390 = Viewport, kein Querscroll |

## Suite

- `-k geraete`: **1429 passed / 3 failed / 6 skipped** (vorher beim Prüfer
  1427/3/6). Die 3 Roten sind die dokumentierten vorbestehenden, am HEAD
  reproduziert, nicht angefasst:
  1. `test_geraete_adapter_netzbetreiber.py::test_tablets_und_router_bleiben_
     draussen` (Galaxy Tab S11 Ultra Auto-Katalog — P5-Auftrag 3 „Anker")
  2. `test_geraete_lifecycle.py::test_ein_simulierter_nachtlauf_erzeugt_
     keine_nullzeilen` (Nachtlauf-Nullzeilen)
  3. `test_geraete_o3_rollen.py::test_je_radar_gruppe_ein_querlink_mit_
     deep_link` (iPhone-18-Querlinks auf `apple-iphone-18-pro-*`)
- `tests/test_seiten_zahlen.py`: 104 passed (101 + 3 neue).
- Geänderte Dateien final: 248 passed / 1 skipped.
- `pruefe_portal.py`: **18 bestanden / 0 durchgefallen / 0 nicht prüfbar**
  (Katalog-Reiter 1924 px, 11c Graphfalz 834 px < 844).
- `site/` per `render_site(..., cfg)` neu gerendert; Screenshots:
  `screenshots/fix-1440-tco.png`, `fix-1440-barpreis.png`, `fix-390-tco.png`
  (angesehen: TCO absteigend sortiert mit sichtbarem Pfeil, „keine Referenz"
  in der Delta-Spalte lesbar, mobil rollt die Tabelle in ihrem Container).

## Geänderte Dateien

- `src/telco_radar/report/geraete_view.py` — `_buendel_aus_listungen`,
  konditionaler Katalog-Aufruf, S4-6-Kommentar
- `src/telco_radar/report/templates/geraete.html.j2` — Delta/„keine Referenz",
  Spanne/„ein Preis", Erklärsatz
- `src/telco_radar/report/templates/app.js` — `gr-ansicht`-Event +
  Sortier-Mitnahme/-Rückstellung
- `src/telco_radar/report/geraete_export.py` — Tarifband `band_label`
- `tests/test_geraete_katalog_modelle.py` — S2-1-Test, Tarifband-Assert
- `tests/test_seiten_zahlen.py` — Fixture (1&1 trägt `preis_mit_vertrag_ab`),
  3 neue Tests, cfg-Kommentar
- `tests/test_geraete_reiter_browser.py` — Sortier-Mitnahme-Test
- `site/` (gerendert: geraete.html, app.js, exporte/geraete-modell-tco.csv)
