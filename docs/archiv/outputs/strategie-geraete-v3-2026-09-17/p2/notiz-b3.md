# P2 / B3 — Abschluss: Zahl zusammenhalten (17.09.2026)

Auftrag: die 3 Leer-Satz-Browser-Tests auf Auto-Vorauswahl, Kriterium 11
ent-G2-en, `pytest -k geraete` grün, site/ frisch rendern + Abnahme-Messwerte
+ Screenshots. Kein Commit, kein data/state, keine eigenen Design-Änderungen.

## Vorfundener Stand: B1+B2 hatten die Test-/Kriterium-Arbeit schon erledigt

Verifiziert statt neu gebaut — jede der drei Stellen:

| Stelle | Zustand | Nachweis |
|---|---|---|
| `test_geraete_reiter_browser.py:941` | `test_ohne_klick_steht_das_diagramm_des_ersten_geraets_da`: initial 1 SVG, >= 4 Punkte, Suchfeld nennt Gerät, `#gr-vleer` display:none | 4/4 Tests grün (Lauf unten) |
| `test_geraete_reiter_browser.py:1163` | `test_eine_neue_eingabe_raeumt_das_alte_diagramm_weg`: nutzt `#gr-vleer` legitim als RÜCKBAU-Zustand beim Suchfeld-Tippen ("zzzzgibtesnicht") — kein initialer Leer-Satz mehr | grün |
| `test_geraete_o3_rollen_browser.py:349` | `test_der_verlaufs_reiter_ist_erreichbar`: Suchfeld == erstes Gerät der Liste (`JSON.parse(#gr-verlaufdaten)[0].label`), Tabelle steht, datenlagenrobust (Leerzustand-Frühausstieg bleibt) | grün |

Mein einziger eigener Test-Eingriff: Docstring in `test_geraete_verlauf.py`
beschrieb die gekippte B4-Regel („ohne Auswahl kein Diagramm … misst der
Browser-Test") als lebendig — auf P2-Regel umgeschrieben (Auto-Vorauswahl,
B4 bewusst gekippt). 24/24 der Datei danach grün; nur Kommentar, keine Logik.

**Kriterium 11 (pruefe_portal.py)** war durch B1 schon korrekt umgebaut und
ist stärker als der Auftrag verlangte: Bedingung ist `#gr-verlaufdaten` ODER
der ehrliche Leerzustand („liegen noch keine Messreihen vor"), plus
Rückkehr-Wächter gegen `svg.gr-g2` (und gegen `#gr-g0-lager`). Der Befund
hatte die ALTE Bedingung falsch gelesen (`svg.gr-g2` ODER `#gr-verlaufdaten`)
— die hätte nach G2-Löschung ROT gemeldet (B1-Notiz). Kriteriumsname ist
„11. Geraeteradar", verspricht kein G2. 11c unberührt.

## Messwerte (frisch gerendert, `render_site(…, cfg)`, Chromium via Port 8766)

| Abnahme-Latte | Messung |
|---|---|
| 0 × `gr-g2` in `site/geraete.html` | **0** (`grep -c`); 0 im GESAMTEN site/, `#gr-verlaufdaten` 1× |
| Initial EIN SVG mit >= 4 Punkten | **1 SVG, 13 Punkte** (1440 und 390 identisch); Suchfeld „iPhone 17 256 GB", `#gr-vleer` unsichtbar |
| Wortzahl Reiter ohne Auswahl < 60 | **27** (H2 8, Legende 6, Gerätesatz 12, „Datenlage"-summary 1) |
| Querscroll 390 | keins (scrollWidth 390 == clientWidth) |
| Screenshots 1440+390 | `p2/screenshots/preisverlauf-{1440,390}{,-viewport}.png`, angesehen: Reiter öffnet mit h2 → Suchfeld (gefüllt) → Zeitraum → Kacheln → 6-Kurven-Diagramm → Tabelle → „DATENLAGE"; Telefon: Suchfeld komplett im ersten Viewport |
| pruefe_portal.py | **18 bestanden / 0 durchgefallen / 0 nicht prüfbar** (11: „die TCO-Zeitreihe steht in der Hauptansicht"; 11c: Antwort-Satz 805 px, Graphkopf 834 px, Falz 844) |

**Die 13 Punkte sind aufgeklärt, nicht geraten:** Datenbasis des ersten
Geräts (iPhone 17 256 GB, 6 Anbieter-Reihen) trägt **18 rohe Messpunkte**
über **11 Messtage**; das Standard-Raster `woche` fasst je 7-Tage-Fenster
zum jüngsten Punkt zusammen (`fassen()`, Schlüssel `floor(tagNr/7)`) —
nachgerechnet mit derselben Formel: **13**. Browser-Messung 13 ==
Nachrechnung 13. Das Raster formt die Linie, nicht die Datenlage (Hausregel;
„11 Messtermine" nennt der Satz darunter korrekt die ROH-Zahl).

## Suite: 3 failed, 1402 passed, 6 skipped (`pytest tests/ -q -k geraete`, 195 s)

Die 3 Roten sind vorbestehend — **am HEAD 63e693c (Stand nach P1) im
temporären Worktree nachgemessen: dieselben 3 rot**:

| Test | Grund (nicht B3-Thema) |
|---|---|
| `test_geraete_adapter_netzbetreiber.py::test_tablets_und_router_bleiben_draussen` | E4-Auto-Erkennung nimmt „Galaxy Tab S11 Ultra" auf — Tablet-Anker ist P5-Auftrag 3 |
| `test_geraete_lifecycle.py::test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen` | der dokumentierte vorbestehende Nachtlauf-Rote (seit E-Phasen durchgehend) |
| `test_geraete_o3_rollen.py::test_je_radar_gruppe_ein_querlink_mit_deep_link` | Radar-Querlinks auf iPhone-18-IDs, die der Zeitreihen-Selektor nicht kennt — Sichtbarkeit beide Wege ist P5-Auftrag 1 |

Die gezielten 3 Leer-Satz-Tests + Deep-Link-Test einzeln: **4 passed**.

## Messtechnik

`p2/abnahme_b3.py` (http.server fest auf 8766, Playwright misst SVG-/Punkt-/
Wortzahl/Querscroll je Viewport, Screenshots, Server im finally per
`shutdown()` beendet — Port danach frei nachgewiesen). Screenshots
überschreiben B2s gleichnamige mit dem frisch gerenderten Stand.
