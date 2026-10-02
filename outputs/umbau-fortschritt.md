# Umbau-Fortschritt

## Paket 1 – erledigt

- Gebaut: `docs/umbau/plan.md` und `docs/umbau/bausteine/` (8 Bausteine unverändert, inaktiv); `_to_delete/` (neu in `.gitignore`), `push-live.sh`, `Push Live.command`, Stop-Hook und Regel 17 entfernt; `claude/`, vier `docs/STRATEG*`-Dateien und 70 erledigte `outputs/` nach `docs/archiv/`; 7 gemergte Remote-Zweige weg (6 hat Antonio gelöscht, weil die Sitzung keine Zweige löschen darf; `claude/project-thread-bl75pd` fehlte schon). Commit `ea80e44`.
- Gemessen: `wc -c docs/umbau/plan.md` = 12.213 (≤ 12.288), `_to_delete` fehlt, `git ls-remote --heads origin` = 76 (`main` plus 75 nicht gemergte Zweige); serieller Volllauf auf `864074a` in der Cloud (4 vCPU, Python 3.11): 20 rot, 3.955 grün, 6 übersprungen, 2.008 s, alle 20 in `pruef/rot-bekannt.txt`.
- Offen: Antonio entscheidet je Zweig über die 75 nicht gemergten (43 `claude/*`, 32 `openclaw/*`, Liste mit letztem Commit in den Projektdateien unter `umbau/zweige-offen.md`); `rot-bekannt.txt` hat 20 statt der erwarteten 16 Einträge, weil `test_seiten_zahlen.py` am gewachsenen Bestand 12 statt 8 Fehlschläge hat; in Code-Kommentaren verweisen Pfade noch auf die archivierten Berichte (fällt mit Paket 19).
