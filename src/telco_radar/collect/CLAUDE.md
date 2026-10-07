# Sammeln: Quellen, HTTP, Collector

- Neue Quellen nur mit PASS aus `scripts/pruefe_quellenvorschlag.py`; er prüft Form, nicht Wert. Vorher die YAML-Kommentare lesen (dort stehen abgelehnte Quellen), geparste Quellen mit `--zweimal` messen. Gültige Quellenzahl nur aus `scripts/quellen_zaehlen.py`, Liste in `TELCO_RADAR_QUELLEN.md` (`scripts/build_quellen_doc.py`).
- `config/watchlist.yaml` wird direkt editiert, nie über `build_sources.py`. Themenfelder gehören in `tech_sources.yaml`, nicht in die Watchlist.
- Börsen- und SEC-Filing-Feeds sind gesperrt: alle Meldungen tragen denselben Titel.
- Undatierte Meldungen sortieren ans Ende und werden nie gelesen. Bei jeder neuen Quelle `published` prüfen; `rss.py` liest das Datum notfalls aus dem Link.
- HTTP 200 kann eine leere JS-Hülle sein: zuerst den Endpunkt suchen (`__NEXT_DATA__`, `/wp-json/wp/v2/posts`, `?format=feed`), erst dann Playwright.
- HTTP 202 ist für `raise_for_status()` kein Fehler; eine Challenge-Seite liefert still null Links. Ein 403 ist nicht automatisch ein User-Agent-Filter: erst messen, dann bauen.
- `http.fetch` wirft bei 404 und 403. Fehlende robots.txt (404) heißt „keine Regeln“, 403 „nicht anfassen“, außer Skripte und Stylesheets im Klick-Crawler (401/403, Entscheidung Antonio 07.10.2026). Die `*`-Gruppe ist nicht immer die strengste.
- `_JS_GLEICHZEITIG` bleibt bei 4, auch wenn `collect_max_workers` steigt. Die Sammelphase deckelt die langsamste Quelle; dagegen hilft nur `_QUELLEN_FRIST`.
- In der Cloud-Sandbox erreicht Chromium das Netz nicht: `newsroom_js`-Quellen melden dort FAIL.
- Ein Subagent, der einen Adapter baut, erfindet notfalls seine Fixture. Fixtures stammen aus gespeicherten echten Abrufen mit Herkunftseintrag; ein Prüfagent ist Pflicht.
