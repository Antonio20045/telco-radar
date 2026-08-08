---
name: commit-sicher
description: Committet die aktuelle Arbeit nach den Regeln dieses Repos, mit allen Prüfungen davor.
disable-model-invocation: true
---

Führe in dieser Reihenfolge aus und brich bei jedem Fehler ab:

1. `git status --short --branch` — zeige mir, was sich geändert hat
2. Prüfe: Sind Dateien unter `site/`, `data/state/` oder `data/reports/`
   dabei? Falls ja, STOPP und frage nach. Das sind fast immer Artefakte
   eines lokalen Laufs und gehören nicht in den Commit.
3. `git diff --check`
4. `PYTHONPATH=src pytest -q`
5. `git add` nur der gezielt genannten Dateien. Niemals `-A` oder `.`
6. Commit mit einer Nachricht in der Form `bereich: kurze beschreibung`
7. Auf den AKTUELLEN Branch pushen, nicht blind auf `main`:
   ```bash
   BRANCH=$(git rev-parse --abbrev-ref HEAD)
   git pull --rebase origin "$BRANCH" 2>/dev/null || true
   git push -u origin "$BRANCH"
   ```
   Sitzungen dieses Repos arbeiten auf `claude/…`-Branches. Ein
   hartverdrahtetes `origin main` würde Feature-Arbeit auf den
   Hauptzweig schieben — deshalb wird der Branch gelesen, nicht geraten.
   Schlägt der Push mit einem Netzwerkfehler fehl: bis zu vier Versuche
   mit 2 s, 4 s, 8 s, 16 s Wartezeit.
8. Danach: Nenne mir den Commit-Hash und was als Nächstes zu prüfen ist.

$ARGUMENTS enthält, falls gesetzt, die gewünschte Commit-Nachricht.
