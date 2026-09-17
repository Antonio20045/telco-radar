# P2 — Re-Check (frisch und hart), 17.09.2026

Gegenstand: die Fix-Notiz `p2/fix.md` gegen `p2/pruefung-code.md` (0×S1, 0×S2,
2×S3, 3×S4) und `p2/pruefung-sicht.md` (1 FAIL auf 390). Alles selbst
nachgemessen (eigenes Skript, eigener 8767-Server, echtes Chromium); nichts
aus der Fix-Notiz geglaubt. Nichts kommittiert, nichts unter `data/state`
geschrieben, Server beendet.

## Der FAIL (Sicht Punkt 2, 390): BEHOBEN

| Messlatte des Sicht-Prüfers | Behauptet | Gemessen |
|---|---|---|
| SVG-Top ≤ Falz 844 | 832 (−12 Luft) | **832** ✓ |
| oberste Kurve (`.gr-vlinie`) im Viewport | — | **843 < 844** ✓ (1 px) |
| h2 einzeilig | „Barpreis-Verlauf", 50 px | top 506, Höhe **50** ✓ (vorher 129/2 Zeilen) |
| kein Querscroll | scrollWidth 390 | **390** ✓ |
| Kachelbeträge einzeilig | Test mit 919/1171 € | alle 4 Kacheln h=22 bei fs=20, **zeilen=1** ✓ |

Sicht 7.2 (1440): Kurve ab **746 px** im Viewport (Fix-Notiz sagte 832 — ich
messe die y-oberste Linie, noch mehr Luft), Falz 900. BEHOBEN.

Klicks am 8767-Server nachgestellt: Auto-Vorauswahl „iPhone 17 256 GB"
(1 SVG, 13 Punkte ≥ 4) · Suche „zzzzkeintreffer" → „**Kein Gerät gefunden.**"
sichtbar · „Galaxy A17" → 1 Treffer → Klick → 11 Punkte · Reiter-Roundtrip
tco→verlauf: Wahl und 11 Punkte bleiben · Deep-Link `?modell=
samsung-galaxy-a17-128` wählt genau dieses Modell; disjunkte ID
(`apple-iphone-16-plus-256`) fällt still aufs erste, kein Crash. Wortzahl
SICHTBAR (geschlossene `<details>` ausgenommen): **36 < 60** ✓. `gr-g2`
im DOM 0, im gesamten `site/` **0 Vorkommen**.

## S3/S4-Stichproben: alle BEHOBEN

- **S3-1:** `test_der_rueckbau_satz_steht_an_beiden_orten_gleich`
  (test_geraete_reiter_browser.py:1175) liest den Satz aus der VORLAGE und
  sucht ihn im app.js — keine dritte Kopie im Test. Scharf gebaut.
- **S4-1:** `historie` aus `geraete_tco_view.aufbereiten()`-Signatur
  (Zeile 621) und Aufrufer (geraete_view.py:1419) gestrichen; `tco_historie`
  (O4) ist ein echtes Feld, kein toter Parameter.
- **S4-3:** Rollbehälter-Test um `#gr-vtabelle` erweitert (Zeile 2308–2314).
- **S4 (TR_ANKUNFT_SEARCH global):** bewusst am Dateikopf mit Kommentar
  (app.js:12) — zutreffend, nicht angefasst. OK.
- **7.4 war wirklich ein Fehlalarm:** `gr-g2` steht in **0** Zeilen der
  style.css (src UND site). Die verbleibenden `gr-g0`-Zeilen stylen die
  lebende `geraete_tco_grafik.zeitreihe()` (Aufrufer
  `geraete_tco_band.py:485`) — löschen wäre ein Fehler gewesen. Die
  Gegenprobe des Fixers stimmt.
- **7.6:** `test_die_kachel_und_der_satz_nennen_dieselbe_zahl` existiert
  (Zeile 1301) und verbietet VERSCHIEDENE Zahlen — die heutige Dopplung ist
  derselbe Wert. Begründung des Fixers trägt.

## Verifikation der Behauptungen

| Behauptung (fix.md) | Messung |
|---|---|
| Suite `-k geraete`: 3 failed / 1405 passed / 6 skipped | **bestätigt** (190,8 s); alle 3 am sauberen HEAD `63e693c` im Worktree reproduziert → vorbestehend (E4/P5-1, E4/P5-3, dokumentierter Lifecycle-Test) |
| `pruefe_portal.py` 18/0/0, verlauf 1843→1809 | **bestätigt** (tco 2593, radar 2997, verlauf **1809**, katalog 1941; 11c grün) |
| `site/` frisch mit cfg gerendert | render_site erneut: geraete.html/app.js/style.css **byte-identisch** (sha256 `66c6229c…`) |
| toter G2-Code wirklich tot | `historienreihen/_reihenrang/MAX_REIHEN/_ereignisse` nur noch in Kommentern ✓ |

## Eigene Messfehler, aufgeklärt (keiner bleibt stehen)

Meine erste Messung meldete drei Schein-Alarme: falsche Selektoren
(`#gr-vliste`→`#gr-vtreffer`, `.gr-vkarte`→`.gr-vkachel`), Wortzählung inkl.
geschlossener `<details>` (66→36 sichtbar), und „erste Kurve" als erster
`path` der DOM-Reihenfolge statt y-Minimum (889→843). Alles mit korrigierter
Messung widerlegt.

## Reste (nicht gebaut — Antwort auf die Schlussfrage)

1. **390: die Kurve ist mit ~1 px technisch im Viewport, nicht erlebbar**
   (oberste Linie 843, Falz 844; Achsentext ab 838). Messlattentreu — aber
   der Graph-Körper beginnt fürs Auge erst beim ersten Scroll-Streich. Der
   größte Hebel liegt ÜBER dem Reiter: Auf 390 stehen vor dem Panel noch die
   Export-Knopf-Reihe und der (zweizeilige) Titel. P4-Auftrag 3 („Export-
   Knöpfe aus dem Kopf in den Fuß") holt genau diese Pixel → dort vermerken.
2. **URL-Sync bei Verlaufs-Modellwechsel (Sicht 7.3):** `?modell=` gehört
   dem Vergleichs-Reiter (`TR_ANKUNFT_SEARCH`); wer im Verlauf wählt und die
   URL teilt, teilt den Zustand eines anderen Reiters. Konzeptive
   Lead-Entscheidung (eigener Parameter/Fragment) — offen.
3. **Disjunkter Deep-Link fällt still aufs erste Gerät (S3-2):** dokumentiert;
   P5-Auftrag 1 (Sichtbarkeit beide Wege) ist der rechte Ort.
4. **Zahl „Messtermine" an Kachel UND Gerätesatz (Sicht 7.6):** derselbe
   Wert, bestehender Test erlaubt das bewusst. Straffen hieße, einen
   Wahrheitstest umzudrehen → nur als Antonio-/Lead-Entscheidung.

Keiner dieser Punkte ist ein offener FAIL der P2-Abnahme.

**Urteil: durch = true.**

— Re-Check-Prüfer P2, 17.09.2026
