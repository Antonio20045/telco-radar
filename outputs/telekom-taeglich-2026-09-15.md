# Telekom-Tageslauf 15.09.2026

Auftrag: Tageslauf-Ticket `ticket-telekom-taeglich-20260915`. Ziel: neuer,
echter Messpunkt für die Telekom-Tarif- und Geräte-Zeitreihe nach dem letzten
erfolgreichen Messpunkt vom 09.09.2026 (die Versuche am 12./13.09. scheiterten
am Bau-Kontingent, ohne dass ein Abruf hinausging). Ausschließlich lokaler
Mac-Lauf über `scripts/lokallauf_telekom.py`, reines httpx-GET mit ehrlichem
Absender, kein Browser, kein Identitätswechsel.

## Durchführung

1. `PYTHONPATH=src /opt/homebrew/bin/python3 scripts/lokallauf_telekom.py
   --frist 180` — **genau einmal**, exakt der in `outputs/phase-t1-2026-09-05.md`
   und im Skript-Docstring dokumentierte Aufruf.
2. `render_site()` über `load_config(root)` (CLAUDE.md §7, „mit cfg").
3. `site/data/keyword-index.json` explizit per
   `git checkout origin/main -- site/data/keyword-index.json` zurückgesetzt.
4. Vollsuite `pytest -q`; dritten roten Test am unveränderten Basisbaum
   (`git stash`-Zyklus) nachgemessen.

## Laufbeleg (Kriterium 1)

`outputs/beleg-telekom-lokallauf-2026-09-15.json` — **11 Requests, alle
HTTP 200, alle mit tatsächlich gesendetem
`TelcoRadar/1.0 (+https://github.com/Antonio20045/telco-radar)`** (gemessen
an `resp.request.headers`, nicht der Konfiguration), alle
`transport="http-get", browser=false`, `alle_ehrlich: true`. Beide T1-Quellen
sind belegt:

| Quelle | Requests | Status | Beispiel-URL |
|---|---|---|---|
| Produktinformationsblätter (§ 1 TK-TransparenzV) | 10 (9 Dokumente + Verzeichnis) | alle `200 OK` | `https://www.telekom.de/produktinformationsblatt/mobilfunk-magentamobil-s-20211121` |
| Shop-Tarifkacheln (`methode: telekom_kacheln`) | 1 | `200 OK` | `https://www.telekom.de/shop/tarife/handyvertrag` |

Host bei allen 11 Requests: `www.telekom.de`.

Dazu der separate Geräte-Beleg `outputs/beleg-telekom-geraete-2026-09-15.json`
— **17 Requests, alle `200 OK`, alle ehrlich** (`alle_ehrlich: true`),
derselbe Protokollhaken: robots.txt (301→`/content/robots`, 200),
Geraetekategorie `…/shop/geraete/smartphones/ohne-vertrag`, fünf
Bündel-Einstiege `…/smartphones?tariffId=MF_1777x` — dazu 10 Abrufe gegen
`1und1.de`/`mobile.1und1.de`: die SIM-only-Referenzen, die
`run_geraete_stage()` als Teil der dokumentierten Stage seit dem 09.09.
mitliest (7 Tarifdetails, „45 SIM-only-Referenzen aus 56 Tarifen"). Kein
Konfigurations- oder Codeeingriff an anderen Anbietern; der globale UA in
`config/settings.yaml` ist unangetastet (Per-Anbieter-Override nur Telekom,
siehe Skript-Docstring).

## Messbilanz (Kriterium 2) — ausschließlich echte Beobachtungen

### T1: Tarife

```
quellen: 2, einstiege: 2, verlinkt: 939, geholt: 10, gelesen: 14,
grundlinie: 0, unveraendert: 14, geaendert: 0, fehler: 0
```

Alle **14 Telekom-Tarifsätze** (9 Pflichtdokumente + 5 Live-Shop-Fassungen
XS/S/M/L/XL) gegenüber dem Vorbestand **unverändert** — der Messpunkt ist ein
bestätigter Stand, kein Preiswechsel (29,95/39,95/49,95/59,95/84,95 €).
Nachgezählt: genau **14 Sätze mit `abgerufen_am: 2026-09-15`**, jeder mit
`dokument_url`/Fundstellen; die fünf Live-Sätze gegen die Shop-Kachel, die
neun Dokumente gegen ihre PIB-Adresse.

### T2: Geräte — eine echte Preisänderung, zwei Auslistungen

```
1 Anbieter (Telekom), 8 Listungen (0 neu), 1 Preispunkt, 2 gealtert,
Bestand 605, 66,2 s; Buendel: 35 von 35 Rohsaetzen uebernommen (0 neu),
45 SIM-only-Referenzen aus 56 Tarifen
```

| Beobachtung | Detail |
|---|---|
| **Preisänderung** | Apple iPhone 17 256 GB violett: **948,60 → 1096,20 €** (+147,60 €, +15,6 %). Vorheriger bestätigter Punkt dieser SKU in der Telekom-Reihe: 2026-09-05 (am 09.09. unverändert bestätigt). Neuer Punkt `datum: 2026-09-15` mit Beleg-URL (`…/shop/geraet/apple/apple-iphone-17/lavendel-256-gb…`) und `verfuegbarkeit: lieferbar` |
| **Auslistungen** (2, `vermutlich ausgelistet`, zuletzt 09.09. gesehen) | Apple iPhone 17 Pro Max 256 GB silber (1347,40 €) · Xiaomi 17T Pro 512 GB schwarz (875,80 €) |
| **Bündel** | 45 Telekom-Bündel im Bestand, **35 heute gemessen** (35 idempotente Historienzeilen `datum: 2026-09-15` in `geraete_tco_historie.jsonl`), 10 unverändert stehen geblieben — alle 10 hängen an genau den zwei Geräten obiger Auslistung/der Bündel-Ansichten (5× iPhone 17 violett, 5× Xiaomi 17T Pro): das iPhone 17 wird weiter hardware-only verkauft (neuer Barpreis), taucht aber nicht mehr in den Bündel-Einstiegen auf; nichts gelöscht, nichts geraten |
| **Arbeitslisten des Laufs** (nicht bearbeitet, nur protokolliert) | 2 Titel ohne Katalogtreffer: Apple iPhone 18 Pro 256 GB polar, iPhone 18 Pro Max 256 GB burgunder (neu im Telekom-Sortiment — Katalog-Ergänzung ist eigene Arbeit, gehört nicht zum Tageslauf) · 5 Farb-Schreibweisen für `config/farben.yaml`: cream, frost, olive, tiefblau, violet shadow |

Keine Schätzwerte, keine kopierten Preise: jede heutige Zahl trägt
`last_verified`/`abgerufen_am: 2026-09-15` und ihre Beleg-URL aus diesem
einen Lauf.

### State-Diff (Kriterium 2, Beleg)

```
 data/state/tarife.jsonl           | 28 +/- (14 Sätze: Datum auf 2026-09-15)
 data/state/geraete_preise.jsonl   |  +1 (der Preispunkt iPhone 17 violett)
 data/state/geraete_db.json        | 101 +/- (8× last_verified heute, 2× gealtert)
 data/state/geraete_tco.json       | 336 +/- (35 Bündel + Referenzen, Datum heute)
 data/state/geraete_tco_historie.jsonl | +35 (Messtag 2026-09-15, idempotent)
```

## Render + keyword-index (Kriterium 3)

`render_site(Path('site'), Path('data/reports'), load_config(Path('.')))`
gelaufen (mit `cfg`, CLAUDE.md §6-Fallstrick „ohne cfg rendert eine still
schweigend halbe Seite"). `site/data/keyword-index.json` anschließend
**explizit** gegen die Basis zurückgesetzt:

```
git checkout origin/main -- site/data/keyword-index.json
git diff origin/main -- site/data/keyword-index.json  → 0 Zeilen
```

Anmerkung zum Beleg: der Render hat die Datei diesmal gar nicht angetastet
(`"stand": "2026-09-11"` — der Stand hängt am letzten Bericht, nicht an
`today()`); der Reset wurde trotzdem ausgeführt und der leere Diff gemessen,
wie es das Kriterium verlangt.

## Vollsuite (Kriterium 4)

```
3 failed, 2929 passed, 14 skipped, 73 warnings in 288.93s
```

| Roter Test | Bewertung |
|---|---|
| `tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung` | vorbestehend, in CLAUDE.md dokumentiert — zulässig |
| `tests/test_promo_seite.py::test_der_leere_screenshot_wird_nicht_ausgeliefert` | vorbestehend, in CLAUDE.md dokumentiert — zulässig |
| `tests/test_geraete_lifecycle.py::test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen` | **vorbestehend am Basisbaum nachgewiesen**, siehe unten |

Der dritte Test war nicht in der dokumentierten Liste und wurde deshalb am
**unveränderten Basisbaum** nachgemessen (`git stash push` → Einzeltest →
`git stash pop`, danach `git stash list` = 0 Einträge, kein Rest):

- Basisbaum (origin/main): FAILED, `tests/test_geraete_lifecycle.py:963`,
  `AssertionError: 52` (`assert len(unbewegt) >= 80`)
- Mit heutigem Messtand: FAILED, **dieselbe Zeile, dieselbe Zahl 52**

Identisches Fehlerbild, keine Verschlechterung durch diesen Lauf: Der Test
liest den echten Bestand und fällt auf origin/main selbst — ein
datenstandsbedingter vorbestehender Aussetzer (der Bestand trägt heute
nur noch 52 unbewegte Kandidaten, der Test verlangt ≥ 80). Kein roter Test
kommt aus diesem Tageslauf.

## Änderungsumfang (Kriterium 5/6)

Genau die Tageslauf-Artefakte, nichts anderes:

```
data/state/tarife.jsonl, data/state/geraete_db.json,
data/state/geraete_preise.jsonl, data/state/geraete_tco.json,
data/state/geraete_tco_historie.jsonl,
site/geraete.html, site/tarife.html, site/wettbewerbsradar.html,
site/exporte/geraete-aktuell.csv, site/exporte/geraete-historie.csv,
outputs/beleg-telekom-lokallauf-2026-09-15.json,
outputs/beleg-telekom-geraete-2026-09-15.json,
outputs/telekom-taeglich-2026-09-15.md
```

Vor dem Commit geprüft: Diff nur auf die genannten Pfade, Branch
`openclaw/ticket-telekom-taeglich-20260915` (Basis `origin/main`), Status
sonst sauber, kein `uv.lock`, kein Stash-Rest. Gepusht wird ausschließlich
dieser Branch; kein Merge nach `main`, kein Deploy, kein Hook-Curl.

## Fazit

Neuer, ehrlicher Messpunkt 15.09.2026 für beide Telekom-Zeitreihen gesetzt:
14 Tarifsätze bestätigt, eine echte Geräte-Preisänderung (iPhone 17, +15,6 %)
und zwei Auslistungen beobachtet, beides mit Beleg-URL aus demselben Lauf.
Beide Laufzeitbelege weisen alle 28 Requests als `TelcoRadar/1.0`-HTTP-GET
ohne Browser aus. Suite ohne neue Regression (der dritte Rote ist am Basisbaum
identisch reproduziert), `keyword-index.json` exakt auf Basis. Die Zeitreihe
ist damit nach den zwei kontingentbedingten Lücken wieder lückenlos
fortgeschrieben.
