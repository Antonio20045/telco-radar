# P2 / CODE-Prüfer — Notiz (17.09.2026)

Voller Bericht: `pruefung-code.md` (gleicher Ordner). **0 × S1, 0 × S2,
2 × S3, 3 × S4.**

- Suite `-k geraete`: 3 failed / 1402 passed / 6 skipped; alle 3 am HEAD
  `63e693c` im Worktree reproduziert (vorbestehend: E4-Tablet, Lifecycle-
  Nachtlauf, Radar-Querlink).
- Toter G2-Code nachweislich tot (0 × `gr-g2` im site/), `messtage` nur
  Docstring geändert, Export `geraete-historie.csv` intakt, P1-Logik im
  app.js unberührt, `site/geraete.html` byte-identisch mit frischem
  `render_site(…, cfg)` (sha256 72fb558417da5ba3…).
- `pruefe_portal.py` 18/0/0; adversarialer Chromium-Lauf (Port 8791)
  bestätigt Auto-Vorauswahl gegen replaceState-Kapriole (TR_ANKUNFT_SEARCH
  wirkt), Band-Unabhängigkeit, Deep-Link-Fallback, Rückbau, Leerliste.
- S3-1: Leer-Satz-Wortlaut doppelt (Vorlage:887 + app.js:2884), kein
  Zusammenhalts-Test. S3-2: stiller Deep-Link-Fallback bei 6 disjunkten
  IDs (dokumentiert, P5-1-Thema). S4: unbenutzter `historie`-Parameter,
  globale `var`, Verlaufstabelle außerhalb der gr-ttab-Roll-Testregel.
