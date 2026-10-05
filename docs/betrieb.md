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

## Geräte-Nachtlauf (`geraete.yml`, täglich 02:17 UTC)
- Läuft im Besuchsfenster zweier Händler (robots.txt `Visit-time` 0200–0800, medimax.de, ep.de); das Fenster gilt je Abruf mit der Uhr des Abrufs, auch für Nachbearbeitungs-Haken. Ein Anbieteranteil endet spätestens 10 s vor dem Fensterende.
- Zeitbudget: Standard 900 s, der Workflow übergibt `FRIST_TAGESLAUF` = 1500 s; jeder ausstehende Anbieter behält mindestens 120 s. mobilcom-debitel wird am Budget oft nicht fertig; Teilläufe zählen als Messtermin, nicht als Lauf.
- Der Bestand wird vor Bündel- und Referenzstufe gespeichert; ein Fehler danach kostet keinen Messtag (ein Messtag ist nicht nachholbar, ein Maßstab schon).
- Quellentod meldet der Lauf auf drei Wegen: Actions-Log, Quellenseite, Mail. Abdeckungsmail: kein Messtag im Bestand ist rot; Mailkanal ohne Secrets ist nur `::warning`; eingerichteter Kanal mit gescheiterter Zustellung ist rot.
- Die Geräteseite rendert täglich, `render_site` bekommt als `heute` aber den Tag des jüngsten Radar-Berichts; Frische-Bezug ist der spätere von Berichtstag und `updated` des Bündel-Stores.
- Abrufe gehen mit der Kennung `TelcoRadar/1.0`; ein Anbieter-Override gilt auch für robots.txt. Aus Actions antwortet die Telekom-Tarifseite mit einer 202-Challenge.

## Radar-Lauf (`radar.yml`)
- Job-Timeout 50 min, Kernlauf rund 27 min. Geräte-Stufe im Wochenlauf aus (`geraete_enabled: false`). Stufen nach dem Kernlauf (Übersetzung) rechnen ihr Budget gegen die Restzeit des Jobs abzüglich der Reserve fürs Veröffentlichen; eine angebrochene Reserve heißt: nicht anfangen.
- Sammelphase: harte Frist je Quelle 75 s (eine tote Quelle kostete ohne Frist über 300 s), höchstens 4 Headless-Browser gleichzeitig (Runner mit zwei Kernen), Host-Drosselung je Host.
- Zertifikate kommen aus dem `certifi`-Bündel, weil sich der Speicher des Runner-Images ohne Projektänderung ändert.
- Leeres LLM-Guthaben (402) darf ungelesene Meldungen nicht in den Seen-Store schreiben. Der Kostenzähler warnt nur; harte Grenze ist das Guthaben beim Anbieter. `LLM_API_KEY` gilt für alle OpenAI-kompatiblen Anbieter, der Anthropic-Schlüssel bleibt als Rückfall gesetzt.
- Der Versand läuft ganz zuletzt; Mail fest montags.

## Anmeldedienst und Newsletter
- Der Anmeldedienst ist ein eigener Render-Dienst neben der Static Site; jeder Formularaufruf ist cross-origin. Stimmt `SITE_BASE_URL` im Dienst nicht, fehlt `Access-Control-Allow-Origin` still und das Formular ist tot; `/gesund` zeigt die erlaubten Herkünfte. Bestätigungs- und Abmeldelinks zeigen auf den Dienst, nicht auf die Website.
- Die IP-Bremse des Dienstes ist nach jedem Spin-down leer; die 24-Stunden-Sperre je Adresse prüft `doi.yml` im Store. Die Bestätigungsseite antwortet sofort, `doi.yml` ist wiederholbar.
- Brevo: Tageslimit 300 (Wächter bei 280), 30 Mails je Minute; 429 und 5xx werden wiederholt, übrige 4xx nicht. Soft Bounces schalten nach fünf in Folge ab, Hard Bounce und Beschwerde sofort; der Bounce-Abgleich merkt sich den letzten Zeitpunkt.
- Der Versand schreibt und pusht den Plan vor der ersten Mail (Wiederanlauf nach Runner-Absturz) und gibt in Actions `::add-mask::` aus.
