# Schlussliste: Sanierung 2026-08-27

Auftragsgrundlage mit allen Befunden, Entscheidungen (inkl. Antonios zwei
Revisionen) und dem Messplan: **`claude/strategie-2026-08-27.md`**. Diese
Liste nennt nur, was gebaut wurde und wie es geprüft ist.

Endstand: **1876 passed, 2 skipped, 0 failed** (vorher 1818 vor
Integration, 1851 nach Integration). Quellen 207 → **196**
(`scripts/quellen_zaehlen.py`). `data/state/` und `site/` unangetastet.

## Pakete

| Paket | Kern | Neue/tragende Tests |
|---|---|---|
| P0 Resilienz+Kosten | `_dispatch` routet je Modell (claude-* → Anthropic), Key wird nicht mehr gelöscht, Ankerketten (Redaktion→sonnet-5, Mechanik→haiku), Kostenzähler je Modell inkl. Denkspur (`run.kosten`, transparenz.html), `llm_budget_usd: 1.50` als reine Warnschwelle, Batch 15→24 / max_tokens 26000 | `test_llm_anker_und_kosten.py` (21+), `test_analyst_budget.py` |
| E1-Vorsortierung | `analyze/vorsortierung.py`: flash sortiert eindeutig Irrelevantes vor dem pro-Analysten aus; CTM-Bypass, Fehler-Durchlass, Verworfenes = gesehen, Frist gegen Restzeit (`vorsortierung_frist_sekunden`), Schalter `vorsortierung_enabled`, 20er-Stichprobe in `run.vorsortierung` | `test_vorsortierung.py` (32+) |
| P1 Highlights | Spezifität (normierter Anteil statt Wortzahl) schlägt Gruppengröße; Antizipations-Pfad (≥3 Meldungen/≥2 Quellen, Deckel 3, nur künftige Termine ≤180 Tage); `event_datum` (Horizont 90 Tage) hält Themen bis Event+7 Tage | `test_highlight_themen.py` |
| P2 Relevanz | Rangschlüssel: Priorität führt, CTM bricht Gleichstand (auch `_flatten`); Clustering bündelt quellenübergreifende Dubletten (4× EE-Slicing → 1 Ereignis), disjunkte Akteursmengen bleiben getrennt; Analysten-Prompt mit Marktgewicht-Deckel und Endkunden-Gewichtung | `test_clustering.py`, `test_seiten_zahlen.py`, `test_analyst_prompt_kalibrierung.py` |
| P3 Übersetzung | `MUTTERSPRACHEN={"de"}` (Englisch wird übersetzt), Deckel 40→60 (settings), `SPRACHNAMEN` kennt en/de („aus dem Englischen") | `test_uebersetzung.py`, `test_uebersetzung_auswahl.py` |
| P4 Promo+Quellen | `gewichte()` gegen die echte Kartenzahl (keine Grid-Lücken bei 0..7 weiteren Karten), `stats.promo_*` mit neu/bestätigt getrennt (`UpsertBilanz`), Block nur bei gelaufener Stufe; 10 Ballast-Betreiber entkoppelt (sources raus, Referenz+Aliase bleiben) | `test_promo_view.py`, `test_promo_raster_browser.py` (Chromium), `test_promo_pipeline.py`, `test_ballastquellen.py` |

## Review (adversarisch, Opus) — 11 Befunde, alle behoben

Die drei schwersten: (1) Analyst erbte über den gleichen Modellnamen den
teuren sonnet-Anker → per-Aufruf-`ausweich` in `llm.complete`; (2) der
dritte Clustering-Pfad verschmolz zwei verschiedene Absender mit gleicher
Satzschablone (Zain/Batelco) → Pfad verengt, Seltenheits-Deckel
`max(3, min(40, n//8))`; (3) Antizipation ungedeckelt (39 Kandidaten,
95k-Zeichen-Nutzlast → abgeschnittene Agent-Antwort → null Themen) →
Deckel 3, Dichte-Sortierung, nur künftige Termine. Dazu: „aus dem EN" auf
jeder englischen Übersetzungsseite, „aktualisiert" zählte nur Neue,
Bedrock-Kette wurde vom Anker gekappt, Vorsortierung ohne
try/except+Frist, ein lügender Testname, zwei Tests ohne Datenbezug.

## Nicht in diesem Paket (bewusst)

Quellenausbau Consumer-Fachpresse (eigener Auftrag), Nachredigieren alter
Fallback-Berichte, CTM-Deckel jenseits E6. Der Merge nach `main` und der
Messplan (Strategie §4) gehören der nächsten Session — Prompt in
Strategie §7.
