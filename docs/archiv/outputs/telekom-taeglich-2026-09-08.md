# Telekom-Tageslauf 08.09.2026

Auftrag: `BRIEF_TELEKOM_TAEGLICH_20260908.md`. Ziel: neuer, echter Messpunkt
für die Telekom-Tarif- und Geräte-Zeitreihe, ausschließlich per lokalem
HTTP-GET (`scripts/lokallauf_telekom.py`), mit Laufzeitbeleg für beide
Telekom-Tarifquellen.

## Durchführung

1. `PYTHONPATH=src python3 scripts/lokallauf_telekom.py --frist 180`
   (lokal auf `/opt/homebrew/bin/python3`, kein Playwright/Browser).
2. `render_site()` über `load_config(root)`.
3. `site/data/keyword-index.json` per `git checkout origin/main --
   site/data/keyword-index.json` exakt auf den `main`-Stand zurückgesetzt.
4. Vollsuite (`pytest -q`).

## Laufzeitbeleg (Kriterium 1)

`outputs/beleg-telekom-lokallauf-2026-09-08.json` — **11 Requests, alle mit
ehrlichem `TelcoRadar/1.0`-Absender** (`resp.request.headers`, nicht die
Konfiguration), reines `httpx`-GET, kein Browser (`transport="http-get",
browser=False`). Beide Pflichtquellen sind darin belegt:

| Quelle | Requests | Status | Beispiel-URL |
|---|---|---|---|
| Produktinformationsblätter (§1 TK-TransparenzV) | 9 | alle `200 OK` | `https://www.telekom.de/produktinformationsblatt/mobilfunk-magentamobil-s-20211121` |
| Shop-Tarifkacheln (`methode: telekom_kacheln`) | 1 | `200 OK` | `https://www.telekom.de/shop/tarife/handyvertrag` |
| Einstiegsseite Pflichtdokument-Verzeichnis | 1 | `200 OK` | `https://www.telekom.de/produktinformationsblatt` |

Host bei allen 11 Requests: `www.telekom.de`. `alle_ehrlich: true`.

## Messzahl (T1: Tarife)

Bilanz aus dem Lauf:

```
quellen: 2, einstiege: 2, verlinkt: 939, geholt: 10, gelesen: 14,
grundlinie: 0, unveraendert: 14, geaendert: 0, fehler: 0
```

Alle 14 gelesenen Telekom-Tarifsätze (9 Pflichtdokumente + 5 Live-Shop-Fassungen
aus den Shopkacheln) waren gegenüber dem Vorbestand **unverändert** — der neue
Messpunkt ist ein bestätigter Stand, kein Preiswechsel. Jeder Satz trägt
`abgerufen_am: 2026-09-08` und seine `dokument_url`/`fundstellen` als Beleg
(z. B. `telekom:magentamobil-s`: Grundgebühr 39,95 €, Beleg
`https://www.telekom.de/produktinformationsblatt/mobilfunk-magentamobil-s-20211121`,
Versionsstand 21.11.2021 aus dem Dokument selbst).

## Messzahl (T2: Geräte, ohne Laufzeitbeleg-Pflicht)

```
1 Anbieter (Telekom), 10 Listungen (0 neu), 0 Preispunkte, 0 gealtert,
Bestand 595, 1,7s
```

Die Telekom-Gerätekategorieseite lieferte einen HTTP-200-Rückfall
(`interaction_required`-Weiterleitung über `accounts.login.idm.telekom.com`,
am Ende `200 OK` auf `www.telekom.de/shop/geraete/...`) mit 10 unveränderten
Listungen — kein neuer Preispunkt, keine geschätzten Werte.

## Datenänderungen (Kriterium 2)

Ausschließlich durch den echten Lokallauf entstanden:

- `data/state/tarife.jsonl` — 14 Sätze mit `abgerufen_am: 2026-09-08`,
  Beleg-URL und Fundstellen aus dem Originaldokument.
- `data/state/geraete_db.json`, `data/state/geraete_tco.json` — Zeitreihe um
  den heutigen Telekom-Messtag ergänzt (0 Preisänderungen).

Keine geschätzten oder aus Vorbeständen kopierten Preise.

## Render + keyword-index (Kriterium 3)

`render_site()` gelaufen. `site/data/keyword-index.json` explizit auf den
Stand von `origin/main` zurückgesetzt:

```
git diff origin/main -- site/data/keyword-index.json
→ leer (0 Zeilen)
```

## Vollsuite (Kriterium 4)

```
2 failed, 2781 passed, 14 skipped, 73 warnings in 289.03s
```

Die zwei Fehlschläge sind **vorbestehend und unverändert**
(`tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung`,
`::test_der_leere_screenshot_wird_nicht_ausgeliefert`) — dieselben zwei roten
Tests wie in allen vorherigen Telekom-Tagesläufen laut Handover (CLAUDE.md
§5/§8a, Promo-Screenshot-Komplex, nicht Teil dieses Auftrags). **Keine neuen
roten Tests.**

## git status vor Commit

```
 M data/state/geraete_db.json
 M data/state/geraete_tco.json
 M data/state/tarife.jsonl
M  site/data/keyword-index.json   (auf main-Stand zurueckgesetzt, Diff null)
 M site/exporte/geraete-aktuell.csv
 M site/geraete.html
 M site/tarife.html
?? outputs/beleg-telekom-lokallauf-2026-09-08.json
```

Kein `uv.lock` im Arbeitsbaum. Keine Änderung an `main`, `config/settings.yaml`
oder fremden Dateien außerhalb dieses Laufs.

## Fazit

Neuer ehrlicher Messpunkt für den 08.09.2026 gesetzt: beide Telekom-Quellen
(Pflichtdokumente + Shopkacheln) mit vollständigem Laufzeitbeleg für
`TelcoRadar/1.0`-HTTP-GET, keine Preisänderung gegenüber dem Vorbestand,
Vollsuite ohne neue Regression, `keyword-index.json` exakt auf `main`.
Gepusht wird ausschließlich `openclaw/ticket-telekom-taeglich-20260908`;
kein Merge nach `main`, kein Deploy.
