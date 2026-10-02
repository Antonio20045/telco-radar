# P1 / A4 — Abschluss: Render, Tests, Abnahmekriterien (notiz-a4)

Stand 17.09.2026, abends. Auftrag: die Zahl der Phase zusammenhalten.
Kein Commit, kein Push, nichts unter data/state geschrieben, kein
eigenes Design, kein neues Feature. Geändert habe ich NUR
`tests/test_seiten_zahlen.py` (+1 Test) — alles andere ist Messung.

## 1. Frischer Render und Größen (immer mit cfg)

| Datei | davor (HEAD 9f5235d) | danach (mein Render) | Delta |
|---|---|---|---|
| `site/data/geraete-zeitreihe.html` | 1 132 101 B | **2 968 207 B** | +1 836 106 B (+162 %) |
| davon gzip transportiert | 52 678 B | 124 568 B | +71 890 B |
| `site/geraete.html` | 1 406 611 B | 1 574 862 B | +168 251 B (+12,0 %) |

- Der „davor"-Wert 1 132 101 B aus der Prüfung stimmt exakt mit HEAD.
- Render ist deterministisch: Größen byte-identisch zur Arbeitskopie
  der Agenten vor meinem Render (A1-A3-Stand).
- **Die +1,84 MB übersteigen die Strategie-Erwartung (+150–300 kB) um
  Faktor ~6** (A1 dokumentierte dasselbe; Ursache 1285 Blöcke à ~1,05 kB).
  Kein Deckel gebaut — PM-6 ist laut Strategie P5s Entscheidung. gzip
  mildert (+72 kB transportiert), ersetzt aber keine Entscheidung.

## 2. Tests: geraete-Suite

`pytest tests/ -q -k geraete`: **1402 passed / 3 failed / 6 skipped**
(176 s). Alle 3 Roten am **unberührten HEAD nachgewiesen** (temporärer
Worktree `/tmp/a4_head_check` @ 9f5235d, danach entfernt — dort exakt
dieselben 3 failed):

| Test | Grund (belegt) |
|---|---|
| `test_geraete_adapter_netzbetreiber::test_tablets_und_router_bleiben_draussen` | Datenstand: Auto-Katalog-Eintrag „Galaxy Tab S11 Ultra" (`auto='2026-09-17'`) kam mit dem Stand-Commit `1dd48d4` (heute 08:59 UTC) in den Bestand; `config/geraete_katalog.yaml`, `data/state/geraete_katalog_auto.json` und `analyze/geraete_model.py` sind NICHT im P1-Diff |
| `test_geraete_lifecycle::test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen` | vorbestehend laut Übergabe E2–E6 („durchgehend"); Lifecycle-Code nicht im Diff |
| `test_geraete_o3_rollen::test_je_radar_gruppe_ein_querlink_mit_deep_link` | fehlende IDs sind ALLE `apple-iphone-18-*` — unter `AUTO_SICHTBAR_AB_MESTAGEN=2` nicht im Selektor = genau Strategie **P5 Auftrag 1** (bewusst nicht P1); A1 hatte zusätzlich stash-verifiziert |

## 3. Abnahmekriterien P1 (maschinell)

- **0 Rechenoperatoren auf Zeitreihen-Zahlen** (app.js-Template,
  Zeitreihen-Bereich 906–1470, gelesen): nur String-Konkatenation,
  Array-Index (`serie.length - 1`), Sequenzzähler (`++zrFolge`),
  `indexOf`-Vergleiche. `parseFloat`/`(kx - ky) * richt` stehen
  AUSSCHLIESSLICH in der sortierbaren Bündeltabelle (O2/C,
  „unveraendert", nicht im Diff — Rohwerte für Sortierung, keine
  Anzeige). Das Panel entsteht ausschließlich aus
  `template.content.cloneNode` — ERFÜLLT.
- **A2-Browser-Test (Klick-Panel)**: 8 passed.
- **pruefe_portal**: 18 bestanden / 0 durchgefallen / 0 n. p. —
  11 Zeitreihe in der Hauptansicht ✓, 11b Reiterhöhen tco 2590 /
  radar 2997 / verlauf 1779 / katalog 1941 px ✓, **11c: Antwort-Satz
  endet 804 px, Graphkopf 833 px, Falz 844 → bleibt über der Falz** ✓.
- **Messlatte Modell-Karten** (finaler Render, echtes DOM bei 1440):
  6 Karten in EINER Reihe (top 528), Preis 21 px (≥ 20), aktive Karte
  2-px-Rahmen gegen 1 px inaktive, 3–4 Anbieter-Punkte, kein
  „Anbieter"-Wort mehr. Mobil 390: scrollWidth 390 (kein Querscroll),
  Panel öffnet per Tap.

## 4. test_seiten_zahlen.py

- A3 hatte Karten-Preis eingetragen (2 Tests) ✓; **Panel-Posten
  fehlten** (A1 hatte sie bewusst nur in
  `test_geraete_zeitreihe_rechenweg.py`). Ergänzt:
  `test_die_panel_posten_kommen_aus_der_aufbereitung` — Wächter:
  First-Paint-Vorlagen == Startpaar (10/10), Fragment == Summe aller
  Paare (13/13); jede Zahl in First Paint UND Fragment wörtlich im
  zweiten Aufbereitungs-Lauf; Negativ-Gegenprobe (erfundener Betrag
  fällt durch). Suite: **97 passed**.
- erster Entwurf fiel am eigenen Wächter (10 vs 13): First Paint trägt
  NUR das Startpaar, das Fragment ALLE Paare — Test entsprechend
  zweigeteilt, das ist die Struktur, nicht ein Fehler.

## 5. Integration live (A1+A2+A3 kombiniert, finaler Render)

Echte site/ im Chromium (1440): Punkt-Klick → Panel sichtbar, Kopf
„Vodafone · Messung vom 12. September 2026", ×-Muster, **Panel ==
Template dieser Messung (isEqualNode: True)**; Preis-Klick öffnet;
**0 Konsolenfehler**. Screenshots: `/tmp/a4_shots/{vergleich-1440,
panel-offen-1440,vergleich-390}.png`.
Einschränkung: das Vision-Werkzeug beschrieb den 1440-Screenshot
falsch („alte Chips, 2 Reihen, ohne Preis") und warf einmal HTTP 400;
die DOM-Messung (6 Karten, 1 Zeile, 21 px, Punkte) ist die härtere
Gegenprobe und widerspricht der Bildbeschreibung klar. Lead sollte
beim finalen Abnehmen einen eigenen Blick auf die Screenshots werfen.

## Sorgen / offene Punkte

1. **Fragment +1,84 MB** — Entscheidung PM-6 liegt beim Lead/P5; meine
   Zahl ist die Messgrundlage (auch gzip-Wert notiert).
2. **3 vorbestehende Rot** (iPhone-18/Auto-Komplex + Nachtlauf) bleiben
   rot — P5 Auftrag 1 bzw. Datenpflege, nicht P1.
3. **site/ ist mein frischer Render** über dem Agenten-Stand
   (byte-stabil). Der Lead entscheidet den finalen Stand selbst.
4. Preiszahl-Erkennung hängt am Wortlaut des Antwort-Satzes (A2-Sorge
   1) — ungelöst, aber testgehalten.
