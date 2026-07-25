#!/usr/bin/env bash
# push-live.sh — Ein Befehl: Code-Änderungen holen, committen, pushen.
#
# Bewusst NICHT automatisch mit eingecheckt: data/state/, data/reports/,
# site/. Das sind Produktionsdaten/State, die der GitHub-Actions-Lauf
# pflegt (siehe TELCO_RADAR_HANDOVER.md Abschnitt 8: "Ein vollständiger
# lokaler Pipeline-Lauf ... Diese Artefakte nicht aus einem lokalen
# Testlauf committen."). Liegen dort Änderungen, warnt das Skript nur und
# lässt sie unangetastet — so kann dieses Skript nie versehentlich das
# Dedup-Gedächtnis (seen.jsonl) oder den Live-Bericht kaputt committen.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "== Telco Radar: Commit & Push =="
echo "Repo: $REPO_DIR"
echo

# Verwaiste Lock-Datei entfernen (kann z.B. nach einem abgebrochenen
# Git-Vorgang übrig bleiben; unbedenklich, solange kein Git-Prozess läuft)
if [ -f .git/index.lock ]; then
  echo "Entferne verwaiste .git/index.lock ..."
  rm -f .git/index.lock
fi

echo "-> Hole aktuellen Stand vom Server (rebase) ..."
# --autostash: deine noch uncommitteten Änderungen (z.B. gerade erst
# eingespielte Dateien) werden vor dem Rebase automatisch geparkt und
# danach wiederhergestellt - ohne --autostash bricht "pull --rebase" mit
# "You have unstaged changes" ab, sobald irgendwas Uncommittetes im
# Arbeitsverzeichnis liegt.
git pull --rebase --autostash origin main

GUARDED=("data/state" "data/reports" "site")
GUARDED_DIRTY=""
for d in "${GUARDED[@]}"; do
  if [ -n "$(git status --porcelain -- "$d" 2>/dev/null)" ]; then
    GUARDED_DIRTY="$GUARDED_DIRTY $d"
  fi
done

CODE_CHANGES="$(git status --porcelain -- . ':!data/state' ':!data/reports' ':!site' 2>/dev/null)"

if [ -z "$CODE_CHANGES" ]; then
  if [ -n "$GUARDED_DIRTY" ]; then
    echo "Keine Code-Änderungen."
    echo "Hinweis: Änderungen in$GUARDED_DIRTY werden absichtlich ignoriert (Produktionsdaten)."
  else
    echo "Keine Änderungen. Fertig."
  fi
  exit 0
fi

echo
echo "-> Folgende Code-Änderungen werden committet:"
git status --short -- . ':!data/state' ':!data/reports' ':!site'
echo

if [ -n "$GUARDED_DIRTY" ]; then
  echo "Hinweis: Änderungen in$GUARDED_DIRTY werden NICHT mit committet"
  echo "(Produktionsdaten - siehe TELCO_RADAR_HANDOVER.md)."
  echo
fi

DEFAULT_MSG="Update $(date '+%Y-%m-%d %H:%M')"
read -r -p "Commit-Nachricht [$DEFAULT_MSG]: " MSG
MSG="${MSG:-$DEFAULT_MSG}"

git add -- . ':!data/state' ':!data/reports' ':!site'
git commit -m "$MSG"
git push origin main

echo
echo "-> Gepusht. CI/Deploy prüfen:"
echo "   https://github.com/Antonio20045/telco-radar/actions"

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo
  read -r -p "Radar-Lauf jetzt manuell starten, damit der neue Bericht live geht? [y/N] " RUN
  if [[ "$RUN" =~ ^[Yy]$ ]]; then
    gh workflow run "Telco Radar Run" --repo Antonio20045/telco-radar
    echo "Workflow gestartet. Status: gh run list --repo Antonio20045/telco-radar --limit 3"
  fi
else
  echo
  echo "Hinweis: Der Code ist jetzt auf GitHub, aber live wird er erst,"
  echo "wenn der Radar-Lauf läuft (Zeitplan Di/Fr 08:30 UTC, oder manuell:"
  echo "GitHub -> Actions -> 'Telco Radar Run' -> Run workflow)."
fi
