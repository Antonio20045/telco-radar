# Telekom-Lokallauf, täglich (06.09.2026)

Auftragsgrundlage: `BRIEF_TELEKOM_TAEGLICH_20260906.md` (Workspace-Engineer).
Pflichtlektüre: `CLAUDE.md`, `outputs/phase-t1-2026-09-05.md`,
`outputs/phase-t1-r2-2026-09-05.md`, `scripts/lokallauf_telekom.py`. Dieser
Lauf ist der erste **tägliche** Übergang des in Phase T1/T1-R2 gebauten
Skripts — keine Code-Änderung, reine Datenerhebung (E4 verbindlich: lokal,
robots-konform, kein Browser, keine UA-Impersonierung).

## Ausgangslage

Letzter belegter Telekom-Messpunkt: **2026-09-05** (Phase T1 + T1-R2, aus
demselben Rechner). 14 Telekom-Tarifsätze, 10 Telekom-Gerätelistungen im
Bestand, alle mit `abgerufen_am`/`last_verified: 2026-09-05`.

## Ausführung

```
PYTHONPATH=src /opt/homebrew/bin/python3 scripts/lokallauf_telekom.py --frist 180
```

Ohne Modifikation gegenüber Phase T1/T1-R2 ausgeführt. `robots.txt`
(`/content/robots`, via 301-Weiterleitung von `/robots.txt`) wurde vor dem
Geräte-Abruf wie dokumentiert gelesen; kein Impersoning, Absender bleibt der
projektübliche `TelcoRadar/1.0`-Client aus `config/settings.yaml`. Kein
Browser, kein JS-Rendering.

### T1 — Tarife

```
Tarif-Sammler: 2 Quellen, 939 verlinkt, 10 geholt, 14 gelesen,
  0 Grundlinie, 14 unveraendert, 0 geaendert, 0 Quarantaene, 0 Fehler
```

Alle 5 Live-Shop-Kacheln (XS/S/M/L/XL) und alle 9 Pflichtdokumente
(inkl. der vier Flex-Varianten und „Basic") wurden gelesen; **kein Preis hat
sich seit gestern geändert** — jeder der 14 Sätze bekommt trotzdem einen
neuen belegten Messpunkt (`abgerufen_am: 2026-09-06`, geprüft gegen
`data/state/tarife.jsonl`). Kein 202/Challenge, kein leeres Ergebnis, also
nichts zu erraten.

### T2 — Geräte

```
Geraeteradar: 1 Anbieter abgefragt, 10 Listungen (0 neu), 0 Preispunkte,
              0 gealtert, Bestand 595, 1.2s
```

Dieselben 10 Telekom-Listungen wie gestern, **kein Preis hat sich
geändert** (0 Preispunkte — `geraete_preise.jsonl` schreibt nur bei
Änderung), aber `last_verified`/`letzter_check` in `geraete_db.json`
stehen jetzt auf `2026-09-06` — der Bestand trägt damit einen zweiten,
unabhängig gemessenen Tag für dieselben 10 Geräte statt eines veraltenden
Einzelstands. `Telekom.laeufe` 4→5, `termine` um `2026-09-06` ergänzt.

Kein 202, kein leeres Ergebnis. Robots gelesen (`/content/robots`, 200),
keine Sperre für die abgefragten Pfade.

## Umfang der Änderung — nur Telekom

Verifiziert per Diff gegen den Vorstand (`git show HEAD:… ` vs. Arbeitsbaum):

| Datei | Geänderte Sätze | Anbieter der geänderten Sätze |
|---|---|---|
| `data/state/tarife.jsonl` | 14 Zeilen (Datum + `updated`) | ausschließlich `Telekom` |
| `data/state/geraete_db.json` | 10 Listungen + der Anbieter-Bilanzblock „Telekom" + globales `updated` | ausschließlich `Telekom` (keine neuen/entfernten Listungen bei anderen Anbietern) |
| `data/state/geraete_tco.json` | 0 Bündel geändert; 45 SIM-only-Referenzen mit gestempeltem `last_verified: 2026-09-06` | **alle 5 Anbieter** (Telekom 10, o2 13, congstar 10, 1&1 7, Vodafone 5) |

Der letzte Punkt ist **kein Verstoß gegen „nur Telekom-Quellen
aktualisieren"** — es wurde kein einziger HTTP-Request an eine
Nicht-Telekom-Domain gestellt (siehe Log: ausschließlich
`telekom.de`-Aufrufe). Es handelt sich um eine dokumentierte,
anbieterunabhängige Eigenschaft von `analyze/tarif_referenzen.aus_bestand()`
+ `TcoDB.ersetze_referenzen()` (`src/telco_radar/analyze/tco_store.py:207`):
die SIM-only-Referenztabelle ist **abgeleitet** und wird bei JEDEM Lauf der
Geräte-Stufe komplett aus dem gesamten `tarife.jsonl`-Bestand neu berechnet;
`setze_referenzen()` stempelt dabei jeden Eintrag mit dem `heute`-Datum des
Aufrufs, unabhängig davon, ob der zugrunde liegende Tarif an diesem Tag neu
gelesen wurde. Das ist dieselbe Mechanik, die schon in Phase T1/T1-R2 lief
— dort fiel es nicht auf, weil dort ohnehin nur ein Tagesdatum existierte.
Kein Bündel- oder TCO-Wert (`buendel`) hat sich geändert (0 von 0 Differenzen).

## Verifikation

```
$ python3 -c "
import json
for line in open('data/state/tarife.jsonl', encoding='utf-8'):
    d = json.loads(line)
    if d.get('anbieter') == 'Telekom':
        print(d['name'], d.get('preistyp'), d['grundgebuehr'], d['abgerufen_am'])
"
MagentaMobil S None 39.95 2026-09-06
MagentaMobil M None 49.95 2026-09-06
MagentaMobil L None 59.95 2026-09-06
MagentaMobil XL None 84.95 2026-09-06
MagentaMobil Basic None … 2026-09-06
MagentaMobil S Flex None … 2026-09-06
MagentaMobil M Flex None … 2026-09-06
MagentaMobil L Flex None … 2026-09-06
MagentaMobil XL Flex None … 2026-09-06
MagentaMobil XS live_shop 29.95 2026-09-06
MagentaMobil S live_shop 39.95 2026-09-06
MagentaMobil M live_shop 49.95 2026-09-06
MagentaMobil L live_shop 59.95 2026-09-06
MagentaMobil XL live_shop 84.95 2026-09-06
```

Alle Beträge unverändert gegenüber Phase T1/T1-R2 (29,95/39,95/49,95/
59,95/84,95 € für XS/S/M/L/XL) — dieselbe Quelle, derselbe Tag später
erneut gemessen, gleiches Ergebnis, neuer Beleg.

## Rendern

```
PYTHONPATH=src /opt/homebrew/bin/python3 -c "
from pathlib import Path
from telco_radar.config import load_config
from telco_radar.report.html import render_site
cfg = load_config(Path('.'))
render_site(Path('site'), Path('data/reports'), cfg)
"
```

Geänderte Artefakte: `site/geraete.html`, `site/tarife.html`,
`site/exporte/geraete-aktuell.csv` (nur die Telekom-Zeile bzw. Telekom-Werte
darin — per Diff geprüft, siehe oben). `site/data/keyword-index.json` hatte
ausschließlich das Feld `stand` geändert (reine Datums-Zeitbombe, siehe
CLAUDE.md §6) und wurde mit `git checkout --` zurückgesetzt.

`site/tarife.html`: Kopf jetzt „Stand 2026-09-06" (max. `abgerufen_am` über
den Gesamtbestand), die vier „Produktinformationsblatt (Referenz)"-Zweitlinks
tragen ebenfalls das neue Datum (dieselben vier Live-Shop-Zeilen wie in
Phase T1). `site/geraete.html`: die G0-Verlaufsgrafiken, die Telekom neben
anderen Anbietern zeigen, haben ihre Zeitachse um einen Tag (bis 06.09.)
verlängert und je einen zusätzlichen, WERTGLEICHEN Telekom-Messpunkt
bekommen — die anderen Anbieter-Linien in denselben Grafiken sind
unverändert (Stichprobe an vier SVGs geprüft: nur `gr-anb--telekom` bekam
einen neuen `<circle>`).

## Tests

```
2777 passed, 14 skipped, 2 failed in 259.19s
```

Die zwei Roten sind die bekannten, vorbestehenden Promo-Screenshot-Tests
(`tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung`,
`::test_der_leere_screenshot_wird_nicht_ausgeliefert`) — unverändert seit
mehreren vorherigen Sessions dokumentiert, betreffen ausschließlich
Promo-Bildbestand, keine Telekom-Tarif-/Gerätedaten. Keine neuen Roten
gegenüber der bekannten Baseline. `tests/test_folien.py` (das frühere
E-3/„leerer Wochenbericht"-Problem aus Phase R3) läuft inzwischen wieder
vollständig grün (27/27) — der Wochenbericht ist seit dem B-1-Merge nicht
mehr degeneriert.

`scripts/pruefe_portal.py`: **16 bestanden / 1 durchgefallen** — der eine
Durchfaller ist Kriterium **8b** (65 vorbestehende leere Promo-Bilddateien
unter `site/promo/images/`, identisch mit den zwei roten Tests oben,
unverändert seit vorherigen Sessions und ohne Bezug zu diesem Auftrag).

## Bewusst offen (unverändert aus Phase T1/T1-R2)

Siehe `outputs/phase-t1-2026-09-05.md` Abschnitt „Bewusst offen" — durch
diesen Lauf nicht berührt: Telekom-Bündel (Gerät+Tarif) bleiben unerhoben,
S-Q4 (Terminologie „Bindung") nicht angefasst, die vier Flex-Tarife und
„MagentaMobil Basic" bleiben PIB-only (in Runde 2 als gemessene Grenze der
Quelle belegt, keine Config-Kappung).

## Commits

Ein Commit auf diesem Ticket-Branch
(`openclaw/ticket-telekom-taeglich-20260906`), kein Merge nach `main`, kein
Deploy.
