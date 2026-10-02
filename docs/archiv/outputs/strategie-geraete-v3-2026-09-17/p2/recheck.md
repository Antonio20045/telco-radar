# P2 — Re-Check-Urteil (17.09.2026)

Prüfer: frischer Re-Check-Prüfer, hart. Grundlage: `p2/fix.md` gegen
`p2/pruefung-code.md` und `p2/pruefung-sicht.md`. Alles am gerenderten
`site/` nachgemessen (eigenes Skript, 8767-Server, echtes Chromium,
Screenshots 390+1440), nichts geglaubt. Nichts kommittiert, nichts unter
`data/state` geschrieben, Server beendet.

## Ergebnis: **durch = true**

| Prüfpunkt | Urteil |
|---|---|
| Sicht-FAIL 390 (Kurve unter der Falz) | **BEHOBEN** — SVG-Top 832 ≤ 844, oberste Linie 843 < 844, h2 50 px einzeilig, kein Querscroll (390), Kachelbeträge einzeilig |
| Sicht 7.2 (1440 Kurve über Falz) | **BEHOBEN** — Kurve ab 746 px (Falz 900) |
| S3-1 (Rückbau-Satz 2×, kein Test) | **BEHOBEN** — „Kein Gerät gefunden." an beiden Stellen, Zusammenhalts-Test liest aus der Vorlage |
| S4-1 (toter Parameter `historie`) | **BEHOBEN** — Signatur + Aufrufer bereinigt |
| S4-3 (Rollbehälter-Test) | **BEHOBEN** — um `#gr-vtabelle` erweitert |
| 7.4 „18 tote Zeilen style.css" | **FEHLALARM bestätigt** — `gr-g2` steht in 0 Zeilen; `gr-g0` stylen die lebende `zeitreihe()` (Aufrufer geraete_tco_band.py:485) |
| Klicks (Auto-Vorauswahl, Suche leer/Treffer, Roundtrip, Deep-Link inkl. disjunkt) | alle nachgestellt, stabil, kein Crash |
| Suite `-k geraete` | 3 failed / 1405 passed / 6 skipped — alle 3 am sauberen HEAD `63e693c` reproduziert → vorbestehend |
| `pruefe_portal.py` | 18/0/0; Reiterhöhen verlauf 1809; 11c grün |
| `site/` echt | render_site mit cfg → byte-identisch (sha256 `66c6229c…`) |

## Reste (notiert, nicht gebaut — Schlussfrage)

1. 390: Kurve mit ~1 px nur technisch im Viewport; der Hebel dafür
   (Export-Knopf-Reihe + Titel über dem Panel) gehört P4-Auftrag 3.
2. URL-Sync bei Verlaufs-Modellwechsel (Sicht 7.3) — konzeptive
   Lead-Entscheidung (Schlüsselraum `?modell=` gehört der Zeitreihe).
3. Disjunkter Deep-Link fällt still aufs erste Gerät (S3-2) — P5-Auftrag 1.
4. Zahl „Messtermine" an Kachel UND Satz (7.6) — derselbe Wert, Test erlaubt
   das bewusst; Straffen wäre eine Test-Umdrehung → Lead/Antonio.

Keine offenen FAILs, nichts Wesentliches im P2-Scope unvermerkt.
