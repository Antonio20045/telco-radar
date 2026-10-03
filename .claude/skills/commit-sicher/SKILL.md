---
name: commit-sicher
description: Committet die aktuelle Arbeit nach den Regeln dieses Repos, mit der vollen Prüfleiter davor.
disable-model-invocation: true
---

Führe in dieser Reihenfolge aus und brich bei jedem Fehler ab:

1. `git status --short --branch`: zeige, was sich geändert hat.
2. Liegen Dateien unter `site/` oder `data/` darin, STOPP: das sind Artefakte eines lokalen Laufs.
3. `make pruefen`: grün ist nur Exit 0. Bei Rot die gemeldete Stufe beheben, nie umgehen.
4. `git add` nur mit Dateinamen, nie `-A` oder `.`.
5. Commit mit einer Nachricht der Form `bereich: kurze beschreibung`.
6. `git pull --rebase origin main`, dann `git push origin HEAD:main`; der pre-push prüft erneut.
   Bei einem Netzfehler bis zu vier Versuche mit 2, 4, 8 und 16 s Pause.
7. Nenne den Commit-Hash und die Zeile zu Schritt 5 aus `make stand`.

$ARGUMENTS enthält, falls gesetzt, die gewünschte Commit-Nachricht.
