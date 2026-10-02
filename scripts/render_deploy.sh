#!/usr/bin/env bash
set -u
seite="${1:?Seite fehlt (z. B. index.html)}"
runden="${PRUEFE_RUNDEN:-10}"
pause="${PRUEFE_PAUSE:-15}"
frist="${CURL_FRIST:-10}"
basis="${LIVE_BASIS:-https://telco-radar.onrender.com}"
lokal="${LOKALE_SEITE:-site/$seite}"

if [ -z "${HOOK:-}" ]; then
  echo "RENDER_DEPLOY_HOOK nicht gesetzt - kein Deploy moeglich."; exit 1
fi
[ -f "$lokal" ] || { echo "Lokale Seite $lokal fehlt."; exit 1; }
soll=$(md5sum < "$lokal" | cut -d' ' -f1)
heute=$(date -u +%Y-%m-%d)
grep -q "$heute" "$lokal" || { echo "$lokal traegt $heute nicht."; exit 1; }

sleep "${HOOK_VORLAUF:-15}"
angenommen=0
for versuch in 1 2 3; do
  code=$(curl -s --max-time "$frist" -o /dev/null -w "%{http_code}" -X POST "$HOOK")
  if [ "$code" = "200" ] || [ "$code" = "201" ] || [ "$code" = "202" ]; then
    echo "Render deploy angenommen (HTTP $code)"; angenommen=1; break
  fi
  echo "Render-Hook HTTP $code (Versuch $versuch/3)"
  sleep "$pause"
done
[ "$angenommen" -eq 1 ] || { echo "Render-Hook dreimal abgelehnt."; exit 1; }

abruf=$(mktemp)
for runde in $(seq 1 "$runden"); do
  curl -L -sS --max-time "$frist" -o "$abruf" "$basis/$seite" || : > "$abruf"
  ist=$(md5sum < "$abruf" | cut -d' ' -f1)
  if [ "$ist" = "$soll" ] && grep -q "$heute" "$abruf"; then
    echo "Live: $seite ist der gebaute Stand und traegt $heute (Runde $runde)"; exit 0
  fi
  echo "Live: $seite noch nicht der gebaute Stand vom $heute (Runde $runde/$runden)"
  sleep "$pause"
done
echo "Live-Seite $seite zeigt den gebauten Stand vom $heute nicht - Deploy nicht bestaetigt."; exit 1
