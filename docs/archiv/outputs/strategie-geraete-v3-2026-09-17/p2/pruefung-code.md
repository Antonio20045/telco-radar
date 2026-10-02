# P2 — CODE-Prüfung (adversarial), 17.09.2026

Gegenstand: Working Tree gegen HEAD `63e693c` (Stand nach P1). Grundlage:
`STRATEGIE_GERAETE_V3.md` §P2, `outputs/…/befunde/preisverlauf.md`,
`docs/clean-code-referenz.md`, Notizen B1–B3. Nichts kommittiert, nichts
unter `data/state` geschrieben.

**Ergebnis: 0 × S1, 0 × S2, 2 × S3, 3 × S4.** Die Phase hält ihren Auftrag.

## Verifikation (alles nachgemessen, nichts geglaubt)

| Prüfauftrag | Messung |
|---|---|
| Suite `-k geraete` | **3 failed / 1402 passed / 6 skipped** (195 s). Dieselben 3 am HEAD `63e693c` im temporären Worktree reproduziert → vorbestehend: `test_tablets_und_router_bleiben_draussen` (E4/P5-3), `test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen` (dokumentiert), `test_je_radar_gruppe_ein_querlink_mit_deep_link` (E4/P5-1) |
| Toter Code wirklich tot | `grep` nach `historienreihen`, `_reihenrang`, `MAX_REIHEN`, `_ereignisse`, `grafik.historie`, `tco.g2` über src/ + site/: nur Kommentare/Docstrings. **0 × `gr-g2` im gesamten site/**, `#gr-verlaufdaten` genau 1× |
| `geraete_verlauf.messtage` intakt | Diff der Datei: NUR Docstring (G2-Referenzen entfernt). `hat_daten/geraete/seit/messtermine/belastbar_ab_wochen/diagramm_ab_terminen/linien_abstand` unverändert (geraete_verlauf.py:392–409) |
| Export „Preishistorie" lebt | `site/exporte/geraete-historie.csv` vorhanden (193 KB, 17.09.); `historie_csv()` rechnet auf `punkte/eintraege`, nicht auf Gelöschtes; zugehörige Tests grün |
| Auto-Vorauswahl vs. URL/Band/Reiter | Eigener Chromium-Lauf (Port 8791): (A) Zeitreihe schreibt `?modell=apple-iphone-17-pro-256&band=klein` per replaceState — Verlauf zeigt trotzdem „iPhone 17 256 GB" = GERAETE[0] → **TR_ANKUNFT_SEARCH wirkt** (ohne den Fix gemessen: Feld zeigte die Zeitreihen-Vorgabe). (B) Bandwechsel „groß": Verlauf unberührt. (F) Reiter-Roundtrip erhält Zustand |
| Deep-Link | bekannte id wird gewählt; disjunkte id (`apple-iphone-16-plus-256`, 1 von 6 disjunkten) fällt still aufs erste, 1 SVG, kein pageerror |
| Leere Geräteliste | Vorlage-Gatter rendert „Für den Preisverlauf liegen noch keine Messreihen vor" und lässt `#gr-verlaufdaten` WEG; IIFE kehrt bei `!daten`/`!feld` (app.js:2217) und `!GERAETE.length` (2221) still zurück. Kein Crash-Pfad |
| P1-Regression | `geraete_zeitreihe.py` nicht im Diff; app.js-Diff berührt nur Dateikopf/`TR_ANKUNFT_SEARCH`, `satzFuer` und den neuen Auto-Vorauswahl-Block; `waehle(modell,band)` (1507) und beide `replaceState` (1532, 1713) unangetastet. Panel/Karten-Logik (`zrOeffneNach`, `zrMessungOeffnen`, `setzeKartenBand`) unverändert |
| site/ echt gerendert | `render_site(…, cfg)` neu: `site/geraete.html` **byte-identisch** (sha256 `72fb558417da5ba3…`), app.js/style.css ebenfalls |
| `pruefe_portal.py` | **18 bestanden / 0 durchgefallen / 0 nicht prüfbar**. Kriterium 11 neu: `#gr-verlaufdaten` ODER ehrlicher Leer-Satz, plus Rückkehr-Wächter gegen `svg.gr-g2` (gibt heute 0). Reiterhöhen: tco 2593, radar 2997, verlauf 1843, katalog 1941 px |
| Tests umgestellt, nicht abgeschwächt | Umgebaut wurden genau die Tests, deren Dokumentation die gekippte B4-Regel festhielt (`test_ohne_auswahl_steht_kein_diagramm_da` → `…_ohne_klick_…`, mit GEGENPROBE-Vorsatz: Fixture legt 6 Messtage, erster der Liste zeichnungsfähig — der Test misst SVG+≥4 Punkte, nicht einen Leerzustand). 12 gelöschte G2-Tests gehören zum gelöschten G2; der Render-Test prüft weiterhin `#gr-verlaufdaten` |

## Befunde

### S3-1 — Doppelter Wortlaut des Rückbau-Satzes, kein Zusammenhalts-Test
- **Datei:** `src/telco_radar/report/templates/geraete.html.j2:887` und `src/telco_radar/report/templates/app.js:2884`
- **Auslöser:** „Wählen Sie oben ein Gerät – dann steht hier sein Preisverlauf, …" steht ZWEIMAL im Code (Vorlage initial `hidden` + JS-Rückbau beim Suchfeld-Tippen). Die Browser-Tests prüfen nur die Sichtbarkeit von `#gr-vleer` (`test_geraete_reiter_browser.py:962, 1172`), nie den Wortlaut. Repo-Hausregel für doppelte Beschriftungen (Muster „Übersetzung lesen", CLAUDE.md §5): ein Test hält beide zusammen. Wer künftig den Satz an einer Stelle ändert, hat zwei Beschriftungen für denselben Zustand — die Fehlerklasse, gegen die der Muster-Test gebaut wurde.
- **Fix (eine Zeile):** Test ergänzen, der den gerenderten `#gr-vleer`-Text gegen den JS-String hält (Muster: `test_die_beschriftung_ist_an_beiden_orten_dieselbe`).

### S3-2 — Stiller Deep-Link-Fallback bei disjunkter Modell-ID
- **Datei:** `src/telco_radar/report/templates/app.js:2950–2959`
- **Auslöser:** Ein `?modell=`-Deep-Link auf eines der 6 Geräte, die in der Zeitreihe wählbar sind, aber NICHT in der Verlaufsliste stehen (gemessen: 88 Zeitreihen-IDs vs. 107 Verlaufs-IDs, 82 gemeinsam, 6 disjunkt — z. B. `apple-iphone-16-plus-256`), wählt im Verlauf still das erste Gerät. Die URL verspricht ein Gerät, der Vergleichs-Reiter zeigt es, der Verlaufs-Reiter ein anderes — zwei Reiter, zwei Geräte aus einem Link. Ist dokumentiert und strategiegedeckt („unbekannte id fällt still aufs erste", derselbe Grundsatz wie im Vergleichs-Reiter) — deshalb S3-Hinweis, kein Änderungsauftrag.
- **Fix (wenn gewünscht, eine Zeile):** im Rückbausatz nennen, dass das verlinkte Gerät keinen Verlauf hat, statt still zu wechseln — oder P5-Auftrag 1 („Sichtbarkeit beide Wege") mitnehmen.

### S4 (gebündelt)
- **S4** `src/telco_radar/report/geraete_tco_view.py:623` — Parameter `historie` in `aufbereiten()` nach G2-Fall unbenutzt (Kommentar 821–825 dokumentiert die Entscheidung). Fix: beim nächsten Aufrufer-Anlass streichen.
- **S4** `src/telco_radar/report/templates/app.js:12` — `var TR_ANKUNFT_SEARCH` implizit global. Bewusst am Dateikopf (muss vor der Zeitreihen-IIFE laufen), funktional korrekt; Stilhinweis.
- **S4** `src/telco_radar/report/templates/app.js:2804` — die dynamische Verlaufstabelle trägt `src-table gr-tabelle`, nicht `gr-ttab`, und fällt damit aus `test_jede_breite_tabelle_liegt_in_ihrem_rollbehaelter`; ihr Roll-Behälter ist `.gr-vtabelle{overflow-x:auto}` (style.css:2603, neu, weil die 376 px Mindestbreite die 390-px-Seite auf 418 px drückte). Optisch gemessen (Querscroll-Tests 390 px, grün; adversarial: kein Querscroll). Hinweis: wer die Roll-Regel verschärft, nimmt die Klasse mit oder erweitert den Test.

## Harte Regeln (CLAUDE.md) — alle PASS
Kein Hand-Edit an `site/` (frisch gerendert, byte-identisch), kein `seen.jsonl`/State-Konflikt (nichts gestaged, kein Commit), keine Secrets im Diff, keine Lauf-Artefakte jenseits des untracked `outputs/p2/` (wie in P1).
