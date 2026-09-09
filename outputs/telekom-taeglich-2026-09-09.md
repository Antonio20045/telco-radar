# Telekom-Tageslauf 09.09.2026

Auftrag: `BRIEF_TELEKOM_TAEGLICH_20260909.md`. Ziel: neuer, ehrlicher
Messpunkt für die Telekom-Tarif- und Geräte-Zeitreihe, ausschließlich per
lokalem HTTP-GET (`scripts/lokallauf_telekom.py`), mit Laufzeitbeleg für
beide Telekom-Tarifquellen.

## Durchführung

1. `PYTHONPATH=src /opt/homebrew/bin/python3 scripts/lokallauf_telekom.py
   --frist 180` (kein Playwright/Browser, reines httpx-GET).
2. `render_site()` über `load_config(root)`.
3. `site/data/keyword-index.json` per `git checkout origin/main --
   site/data/keyword-index.json` zurückgesetzt, Diff explizit null.
4. Vollsuite (`pytest -q`).

## Laufzeitbeleg (Kriterium 1)

`outputs/beleg-telekom-lokallauf-2026-09-09.json` — **11 Requests, alle
HTTP 200, alle mit tatsächlich gesendetem `TelcoRadar/1.0`-Absender**
(gemessen an `resp.request.headers`, nicht der Konfiguration), alle
`transport="http-get", browser=False`. `alle_ehrlich: true`. Beide
Pflichtquellen sind darin belegt:

| Quelle | Requests | Status | Beispiel-URL |
|---|---|---|---|
| Produktinformationsblätter (§1 TK-TransparenzV) | 10 | alle `200 OK` | `https://www.telekom.de/produktinformationsblatt/mobilfunk-magentamobil-s-20211121` |
| Shop-Tarifkacheln (`methode: telekom_kacheln`) | 1 | `200 OK` | `https://www.telekom.de/shop/tarife/handyvertrag` |

(Die 10 PIB-Requests sind 9 Dokumente + 1 Einstiegsseite des
Verzeichnisses; wie gestern.) Host bei allen 11 Requests:
`www.telekom.de`.

Dazu der separate Geräte-Beleg `outputs/beleg-telekom-geraete-2026-09-09.json`
— 7 Requests (robots, Kategorieseite, 5 Bündel-Einstiege), alle `200 OK`,
alle ehrlich (`alle_ehrlich: true`), derselbe Protokollhaken.

## Messzahl (T1: Tarife)

Bilanz aus dem Lauf:

```
quellen: 2, einstiege: 2, verlinkt: 939, geholt: 10, gelesen: 14,
grundlinie: 0, unveraendert: 14, geaendert: 0, fehler: 0
```

Alle 14 gelesenen Telekom-Tarifsätze (9 Pflichtdokumente + 5 Live-Shop-
Fassungen) gegenüber dem Vorbestand **unverändert** — der neue Messpunkt
ist ein bestätigter Stand, kein Preiswechsel. Jeder Satz trägt
`abgerufen_am: 2026-09-09` (nachgezählt: genau 14) und seine
`dokument_url`/Fundstellen als Beleg, z. B. `telekom:magentamobil-s`:
39,95 €, Beleg
`https://www.telekom.de/produktinformationsblatt/mobilfunk-magentamobil-s-20211121`;
die fünf Live-Sätze (XS/S/M/L/XL) gegen die Shop-Kachel
`https://www.telekom.de/shop/tarife/handyvertrag`.

## Messzahl (T2: Geräte, eigener Beleg)

```
1 Anbieter (Telekom), 10 Listungen (0 neu), 0 Preispunkte, 0 gealtert,
Bestand 598, 52,0s; Buendel: 45 von 45 uebernommen (0 neu),
45 SIM-only-Referenzen aus 56 Tarifen
```

Alle 10 Telekom-Listungen `last_verified: 2026-09-09` mit Preis und
Beleg-URL (Stichprobe):

| Gerät | Preis | Beleg |
|---|---|---|
| Apple iPhone 17 256 GB lavendel | 948,60 € | `…/shop/geraet/apple/apple-iphone-17/lavendel-256-gb…` |
| Google Pixel 11 Pro XL 256 GB obsidian | 1.397,80 € | `…/shop/geraet/google/google-pixel-11-pro-xl/obsidian-256-gb…` |
| Samsung Galaxy Z Fold8 Ultra 256 GB | 2.199,00 € | `…/shop/geraet/samsung/samsung-galaxy-z-fold8-ultra/violet-shadow-256-gb…` |

Kein neuer Preispunkt, keine geschätzten Werte — 0 Preisänderungen.

## Datenänderungen (Kriterium 2)

Ausschließlich durch den echten Lokallauf entstanden:

- `data/state/tarife.jsonl` — 14 Sätze mit `abgerufen_am: 2026-09-09`,
  Beleg-URL und Fundstellen aus dem Originaldokument.
- `data/state/geraete_db.json`, `data/state/geraete_tco.json` — Zeitreihe
  um den heutigen Telekom-Messtag ergänzt (0 Preisänderungen).

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
2 failed, 2884 passed, 14 skipped, 73 warnings in 244.45s
```

Die zwei Fehlschläge sind **vorbestehend und erlaubt**
(`tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung`,
`::test_der_leere_screenshot_wird_nicht_ausgeliefert`) — isoliert
nachgespielt, dieselben zwei wie im Tageslauf vom 08.09. **Keine anderen
roten Tests.**

Abweichung zur Basiszahl (2896 passed / 0 failed / 12 skipped): Diese
Umgebung sammelt 2898 Tests, die Basis offensichtlich 2908 — die Basis
wurde in einer anderen Umgebung gemessen (dort liefen die zwei
Promo-Screenshot-Tests grün, hier rot; 14 statt 12 Skips). Nachgewiesen,
dass davon nichts von diesem Lauf kommt: **Sammlung mit und ohne die
lokalen Änderungen identisch** (`git stash` → `pytest --collect-only`
→ 2898 → `git stash pop` → 2898). Die Differenz ist Umgebung, nicht
Änderung.

## git status vor Commit

```
 M data/state/geraete_db.json
 M data/state/geraete_tco.json
 M data/state/tarife.jsonl
 M site/exporte/geraete-aktuell.csv
 M site/geraete.html
 M site/tarife.html
 M site/wettbewerbsradar.html
?? outputs/beleg-telekom-geraete-2026-09-09.json
?? outputs/beleg-telekom-lokallauf-2026-09-09.json
?? outputs/telekom-taeglich-2026-09-09.md
```

`site/wettbewerbsradar.html` ist neu gegenüber gestern: die Seite nennt
das Abrufdatum der Telekom-Gerätebelege, das von 2026-09-08 auf
2026-09-09 gerollt ist (Preise und Prozente unverändert) — laufbedingt,
keine Inhaltssäderung.

Kein `uv.lock` im Arbeitsbaum. Keine Änderung an `main`,
`config/settings.yaml` oder fremden Dateien außerhalb dieses Laufs.

## Fazit

Neuer ehrlicher Messpunkt für den 09.09.2026 gesetzt: beide Telekom-
Tarifquellen (Pflichtdokumente + Shopkacheln) mit vollständigem
Laufzeitbeleg für `TelcoRadar/1.0`-HTTP-GET, dazu der Geräte-Beleg;
keine Preisänderung gegenüber dem Vorbestand, Vollsuite ohne neue
Regression, `keyword-index.json` exakt auf `main`. Gepusht wird
ausschließlich `openclaw/ticket-telekom-taeglich20260909`; kein Merge
nach `main`, kein Deploy.
