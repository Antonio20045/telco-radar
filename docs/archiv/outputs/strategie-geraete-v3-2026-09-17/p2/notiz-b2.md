# P2 / B2 — Modell-Wähler als Hauptinhalt des Preisverlaufs (17.09.2026)

Auftrag: Reihenfolge h2 → Suchfeld → Zeitraum → Kacheln → Diagramm → Tabelle;
alles Erklärende in EINEN geschlossenen Aufklapper am Reiterende; Auto-Vorauswahl
des ersten Geräts (Deep-Link hat Vorrang); mobil 390 Suchfeld ohne Scroll.
Basis: Stand nach B1 (G2 gelöscht), Working Tree, kein Commit, kein data/state.

## Was geändert wurde

| Datei | Änderung |
|---|---|
| `templates/geraete.html.j2` | Erklär-Satz (31 W., Barpreis/TCO-Grenze) und globaler Stand-Satz (20 W.) aus dem sichtbaren Bereich in NEUEN geschlossenen `<details class="gr-vdatenlage">` „Datenlage" am Reiterende verschoben. `#gr-vleer` initial `hidden` (lebt weiter als Rückbau-Satz beim Suchfeld-Tippen). `#gr-vstand` initial `hidden`, nur noch `data-abterminen`/`data-abstand` (die zwei Schwellen, die app.js liest); `data-alle/seit/wochen` gestrichen (toter Code — globaler Satz steht jetzt statisch aus der Vorlage im Aufklapper). Reiter-Kommentar: B4-Regel als gekippt dokumentiert. |
| `templates/app.js` | (1) Auto-Vorauswahl am Ende der Verlaufs-IIFE: `waehle(startGeraet \|\| GERAETE[0])` — erstes Gerät der Liste (Sortierung nach `-messpunkte` bleibt). `?modell=` hat Vorrang, wenn die id in der Verlaufsliste liegt (Schlüsselraum identisch zur Zeitreihe: 82 der 88 erlaubten Zeitreihen-Modelle sind in der Liste); unbekannte id fällt still aufs erste. (2) NEU `var TR_ANKUNFT_SEARCH = location.search` am Dateikopf: Die Zeitreihen-Steuerung schreibt beim Laden ihr Vorgabe-`?modell=` per `history.replaceState` in die URL — ohne die Sicherung hätte die interne Zustandsspeicherung die Vorauswahl gekapert (gemessen: Feld zeigte „iPhone 17 Pro 256 GB" = Zeitreihen-Vorgabe; nach dem Fix „iPhone 17 256 GB" = GERAETE[0]). (3) `satzFuer()`: null-Fall versteckt den Satz (global lebt im Aufklapper), Nachsatz („Aussagen zu Preisverfall …") aus dem dynamischen Satz entfernt — er steht statisch im Aufklapper. |
| `templates/style.css` | `.gr-vdatenlage` (summary mit cursor:pointer, +/−-Marker, Rot als Akzent). `.gr-vtabelle{overflow-x:auto}` — NEU: Die Tabelle rollt in sich (Hausregel); vor P2 war sie im Ausgangszustand unsichtbar, mit Auto-Auswahl drückte ihre Zellen-Mindestbreite (376 px) die Telefonseite auf 418 px. Mobil-Straffung (≤760px): Abstände vor/zwischen Steuer und Kacheln, Kachel-Padding. |
| `tests/test_geraete_reiter_browser.py` | `test_ohne_auswahl_steht_kein_diagramm_da` → `test_ohne_klick_steht_das_diagramm_des_ersten_geraets_da` (initial 1 SVG, ≥ 4 Punkte, Suchfeld nennt Gerät, Leer-Satz weg). NEU `test_ein_deep_link_schlaegt_die_auto_vorauswahl` (bekannte id gewählt, unbekannte fällt still aufs erste; verlässt die Seite sauber — module-weite Fixture). |
| `tests/test_geraete_o3_rollen_browser.py` | `test_der_verlaufs_reiter_ist_erreichbar` auf Auto-Vorauswahl umgestellt: prüft Suchfeld == erstes Gerät der Liste + Tabelle steht (datenlagenrobust — die o3-Fixture liegt mit ihrem ersten Gerät UNTER der Diagramm-Schwelle, Gatter zeigt Kacheln+Tabelle statt SVG). |

## Messzahlen (echte Seite, Chromium)

| Messung | Vorher | Nachher |
|---|---|---|
| Suchfeld-Position (1440, Abstand Reiterkopf) | 1176 px von 1581 px Reiterhöhe (befunde/preisverlauf.md) | **90 px** (Diagramm beginnt bei 285 px) |
| Suchfeld auf 390×844 nach Reiter-Klick, ohne Scroll | (mit G2 unerreichbar weit unten) | **Oberkante 682 px, komplett sichtbar** — Messlatte erfüllt (vor Straffung 696) |
| Diagramm-Anfang auf 390 | — | 1008 px (164 px unter der Falz; dazwischen Zeitraum-Steuer + 2×2-Kacheln in verbindlicher Reihenfolge — Falz-Feinschliff ist P4) |
| Wortzahl im initialen Reiter (Zählung wie design.md: sichtbare h2/p/figcaption/summary) | 194 | **27** (h2 8, Legende 6, Gerätesatz 12, „Datenlage" 1) — Ziel < 60 |
| Initial gezeichnete Punkte (vorausgewähltes Gerät) | 0 (kein Diagramm ohne Klick) | **13** (iPhone 17 256 GB, 11 Messtermine, 6 Anbieter; ≥ 4 ✓) |
| Querscroll 390 (Verlaufs-Reiter) | 418 px | **390 px** (kein) |
| Reiterhöhe (pruefe_portal 11b) | 1581 px | 1843 px (Budget 3000; der Reiter ist voller, weil das Diagramm jetzt ohne Klick dasteht) |

## Abnahme

- `pruefe_portal.py`: **18 bestanden / 0 durchgefallen / 0 nicht prüfbar** (11: „die TCO-Zeitreihe steht in der Hauptansicht", 11c Graphfalz unberührt).
- Volle Suite: **3192 passed / 3 failed / 12 skipped**. Alle 3 Roten vorbestehend und NICHT aus diesem Auftrag: `test_geraete_lifecycle` (dokumentiert vorbestehend), `test_tablets_und_router_bleiben_draussen` (E4-Auto-Erkennung erkennt „Galaxy Tab S11 Ultra" — iPad/Tablet-Anker ist P5-Auftrag 3), `test_je_radar_gruppe_ein_querlink_mit_deep_link` (Radar-Querlinks auf iPhone-18-IDs, die der Zeitreihen-Selektor nicht kennt — Sichtbarkeit beide Wege ist P5-Auftrag 1).
- Screenshots (harte Abnahme, angesehen): `p2/screenshots/preisverlauf-1440.png`, `preisverlauf-390.png`, `preisverlauf-390-viewport.png` — Desktop zeigt exakt h2 → Suchfeld („iPhone 17 256 GB") → Zeitraum → Kacheln → 6-Kurven-Diagramm → Tabelle → „DATENLAGE"; Telefon ohne Querscroll, Suchfeld im ersten Viewport.
- Messtechnik: `p2/mess_390.py`, `p2/screenshots.py`, `p2/debug_wahl.py`.

## Fallstricke / Entscheidungen

- **replaceState-Kapriole:** Der Deep-Link-Vorrang wäre still ausgehebelt worden — die Zeitreihe setzt ihr `?modell=` beim Laden selbst in die URL. Gelesen wird jetzt die einmal gesicherte Ankunfts-Suche (`TR_ANKUNFT_SEARCH`), nicht `location.search`.
- **Diagramm-Anfang vs. Messlatte:** Der Auftrag nennt „Suchfeld + Diagramm-Anfang im ersten Viewport", messlatte ist das Suchfeld (erfüllt). Der Diagramm-Anfang bleibt 164 px unter der Falz, weil die verbindliche Reihenfolge Zeitraum + Kacheln davor stellt; bewusst nicht umsortiert.
- **Erstes Gerät = meistgemessenes:** wörtlich nach Auftrag `GERAETE[0]`, kein eigener Filter auf Diagramm-Fähigkeit — kippt die Messlage, zeigt der Reiter ehrlich Kacheln+Tabelle des meistgemessenen Geräts (so in der o3-Fixture der Fall).
