# Betrieb: Seitenaufbau, Exit-Codes, Deploy-Prüfung

## Seitenaufbau (`report.bauen`, `render_site`)
- `render_site()` liefert eine Liste von `Ausfall` (`teil`, `grund`). Leer = alles gebaut.
- `python -m telco_radar.report.bauen --root .` schreibt bei gebauter Seite `gerendert=true` in `GITHUB_OUTPUT`, druckt `AUSFALL <teil>: <grund>` auf stderr.
- Exit 0: alles gebaut. Exit 1: Ausfälle (Seite gebaut) oder Ausnahme (dann ohne `gerendert=true`).

## Pipeline-Exit-Codes (`telco_radar.pipeline`)
- 0 ok, 1 Pipeline gescheitert, 3 Pipeline fertig (State, Bericht, Seite, Versand), aber Teile der Seite fehlen.

## radar.yml
- „Run pipeline“ setzt bei Exit 3 `render_ausfall=true` und endet rot.
- „Commit“ und „Render-Hook“ laufen bei Erfolg oder `render_ausfall`; der Hook nur nach erfolgreichem Commit.
- Der Newsletter-Schritt läuft nur bei vollem Erfolg.

## geraete.yml
- „Render site“ ist rot bei Ausfällen; „Commit site“ und Hook laufen bei `gerendert=true`.
- Der Neuaufbau nach verlorenem Push-Rennen toleriert Exit 1 (Ausfälle), bricht nur ohne `gerendert=true` ab.

## Deploy-Prüfung (`scripts/render_deploy.sh <seite>`)
- Vorbedingung: die lokale, eben committete `site/<seite>` trägt das heutige UTC-Datum.
- Hook höchstens 3 Versuche (200/201/202 gelten als angenommen); dreimal abgelehnt ist rot.
- Danach 10 Runden à 15 s: Live-Seite (`curl -L`, je Abruf höchstens 10 s) muss byte-gleich (md5) mit der lokalen Seite sein und das Datum tragen. Sonst rot; ein älterer Stand mit demselben Datum zählt nicht.
- Schlimmster Fall rund 325 s, unter `veroeffentlichung_reserve_sekunden` (420). Kein `continue-on-error`.
- Ein Push mit `GITHUB_TOKEN` startet keinen Deploy; `deploy.yml` gibt es nicht mehr.

## CI
- `ci.yml` läuft nur von Hand (`workflow_dispatch`, 30 min); lokal `make venv`, Python aus `.python-version`.
