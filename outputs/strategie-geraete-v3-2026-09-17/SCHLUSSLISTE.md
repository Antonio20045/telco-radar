# Geräteseite v3 — Schlussliste (17./18.09.2026)

Auftragsgrundlage: Antonios Forderungen vom 17.09.2026 (wörtlich in
`STRATEGIE_GERAETE_V3.md` §1). Orchestrierung: Strategie-Workflow → 5
Phasen-Workflows (+1 Nachfix), Lead nur Abnahme/Merge/Live-Beweis.

## Commits (alle deployed, je md5-live-bewiesen)

| Phase | Commit | Inhalt |
|---|---|---|
| Strategie | `63e693c` (mit P1) | `STRATEGIE_GERAETE_V3.md` P1–P5 + 6 Befunddateien, adversarial geprüft (3 FAILs → gefixt) |
| P1 Vergleich | `63e693c` | Rechenweg je Messung klickbar (Preis ODER Kurvenpunkt → Panel mit Posten-Balken; 1285 Messungen, Summe an allen 2562 Historien-Zeilen verifiziert, 0 Client-Rechnung) · 6 Modell-Karten (21-px-Preis, Δ, Anbieter-Punkte, aktive Markierung) |
| P2 Preisverlauf | `64a8f2a` | G2-Chart gelöscht (-347 Z. toter Code) · Modell-Wähler oben mit Auto-Vorauswahl (13 Punkte ohne Klick) · Reiter-Fließtext 187→27 Wörter |
| P3 Katalog | `6a37ceb` | 111 Modellzeilen statt 636 · 0× „ohne Preis" (vorher 36×) · 1&1 „nur im Bündel ab X €/Monat" · EIN Umschalter Barpreis/TCO ohne Reload · 2 Ansichts-CSVs |
| P4+P4b Design | `f006660` | Radar als Balken-Grafik (Rot 40→1 sichtbar, Tabelle im Aufklapper) · Leitzahl = größte Schrift (60/30 px) · Text-Deckel Kriterien 13/14/15 · EIN modell_schluessel (Sprünge 92/92 + 83/83) · `[hidden]`-Wurzelfix, Rot-Messregel, mobil Kurve unter Falz |
| P5 Automatik | `83e35d9` | Sichtbarkeit Bündel ODER Listung (iPhone 18 live im Katalog+Export) · 7-Tage-Ausfall-Alarm + Provider-Proben (Totaltod meldefähig) · Unbekannte entrauscht (87/284) · PM-6-Messskript (5-MB-Grenze fällt rechnerisch 20.09.) · CLAUDE.md konsolidiert |

## Endstand

- **Volle Suite: 3314 passed / 0 failed / 12 skipped** — die 3 Dauer-Roten sind
  gelöst (gerechtfertigt umgestellt, Vorher-rot je bewiesen). `pruefe_portal.py`
  **21/0/0** (drei neue Kriterien: Text-Deckel, p-nach-SVG, Aufklappzeichen).
- Fragment `geraete-zeitreihe.html` 1,13 → 3,56 MB (gzip 159 kB; 1.391 B/Paar
  gemessen — die „~7 kB"-Schätzung war 5× zu hoch). **Deckel-Entscheidung
  datenbasiert am 01.10.** (Skript liefert die Prognose).
- Arbeitsweise (Antonios Meta-Auftrag): Strategy-Workflow erzeugt Phasen; je
  Phase 3–5 Bau-Agenten → 2 frische Prüfer (diff-reviewer + kontextarmer
  Sicht-Prüfer mit Antonios Forderungen wörtlich) → Fix → Re-Check mit der
  Frage „Wie kann ich das innerhalb meines Scopes weiter verbessern?" als
  Fertig-Kriterium. Lead-Gegenprobe je Phase per Screenshot (Vision-Analyse
  als zweite, unabhängige Sicht).

## Offen (7 Punkte, Details CLAUDE.md §8a OFFEN)

URL-Sync beim Verlaufs-Wechsel · Rot-Deckel-Test nur Katalog · **PM-6-Deckel
(01.10., dringend: Grenze fällt rechnerisch 20.09.)** · Telekom-202 (Antonio-
Entscheidung R3) · iPad-Anker-Wirkung nach nächstem Nachtlauf prüfen ·
disjunkter Deep-Link · monatlicher Betriebssichttest (3+1 Protokollzeilen).
