#!/usr/bin/env bash
# Doppelklick-Starter für push-live.sh. Öffnet Terminal, zeigt Git-Status,
# fragt nach einer Commit-Nachricht, committet und pusht.
cd "$(dirname "$0")"
./push-live.sh
echo
read -n 1 -s -r -p "Fertig — beliebige Taste zum Schließen ..."
echo
