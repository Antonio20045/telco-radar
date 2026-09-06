# Telekom-Lokallauf, Runde 2 — Laufzeitbeleg (06.09.2026)

Auftragsgrundlage: `BRIEF_TELEKOM_TAEGLICH_R2_BELEG.md` (Workspace-Engineer),
auf Basis von `EVAL_telekom-taeglich-20260906-r1.md` (Fremdabnahme,
`NEEDS_WORK`, gegen Commit `f1a96bf`). Pflichtlektüre: `CLAUDE.md`,
`outputs/telekom-taeglich-2026-09-06.md`, das EVAL-Dokument,
`scripts/lokallauf_telekom.py`.

## Auftrag der Runde 2

R1 behauptete "kein Impersoning, Absender bleibt der projektübliche
TelcoRadar/1.0-Client" — eine Aussage aus **Code-Plausibilität**, nicht aus
Messung. Der Evaluator hat das zu Recht zurückgewiesen: `fetch()` kann bei
403/406 die Kennung wechseln, und R1 hatte kein Request-/Response-Protokoll,
das das ausschließt. Diese Runde ergänzt genau das: einen kleinen,
datensparsamen, versionierten Laufzeitbeleg pro Telekom-Request, gemessen am
ECHTEN gesendeten `User-Agent` — nicht an der Konfiguration, die ihn
vorschreiben soll.

## Was ergänzt wurde

`scripts/lokallauf_telekom.py` bekommt zwei neue Hüllfunktionen,
`_hole_mit_beleg` (Response-Protokoll, fürs T1-Tarifsammeln) und
`_geraete_hole_mit_beleg` (`(status, text)`-Protokoll, für Robots-Wächter
UND Seitenabruf der Geräte-Stufe). Beide umschließen ausschließlich
`collect.http.fetch` — sie ändern an dessen Verhalten nichts, sie lesen nur
mit. Protokolliert wird je Request: `url`, `host`, `status`, der
tatsächlich **gesendete** `User-Agent` (aus `resp.request.headers`, dem
Objekt, das httpx nach dem echten Request zurückgibt — nicht aus
`http_cfg`), sowie explizit `transport: "http-get"` und `browser: false`
(reines `httpx.get`, kein Playwright/Selenium/Headless-Browser). Keine
Antwortkörper, keine Cookies, keine Zugangsdaten. `fetch()` selbst ist
unverändert; die Instrumentierung ist ausschließlich in diesem Skript aktiv
und betrifft keinen anderen Aufrufer im Projekt.

Der Lauf schreibt den Beleg nach `outputs/beleg-telekom-lokallauf-<datum>.json`
— versioniert im Repo, nicht unter `data/state/` (das wird nie committet).
Am Ende prüft das Skript selbst, ob **alle** Einträge mit einer ehrlichen
Kennung gesendet wurden (`_ist_ehrliche_kennung`, dieselbe Prüfung wie in
`fetch()`), und protokolliert das Ergebnis unübersehbar als `INFO` (Erfolg)
oder `ERROR` (Befund) — es gibt keinen Codepfad, der eine unehrliche Kennung
stillschweigend als Erfolg meldet.

## Messergebnis — und der Befund

```
$ PYTHONPATH=src /opt/homebrew/bin/python3 scripts/lokallauf_telekom.py --frist 180
...
ERROR lokallauf_telekom: BEFUND: 13 von 13 Telekom-Requests wurden NICHT mit
  TelcoRadar/1.0 gesendet (Browser-Imitation oder UA-Wechsel). Details in
  outputs/beleg-telekom-lokallauf-2026-09-06.json. Das ist ein Abnahme-Befund,
  kein Erfolg.
```

**Der Beleg widerlegt R1s Behauptung, er bestätigt sie nicht.** Alle 13
heutigen Telekom-Requests (10 Pflichtdokumente + 1 Kacheln-Seite +
`/robots.txt` + `/content/robots`-Redirect-Ziel + 1 Gerätekategorie-Seite)
wurden mit demselben `User-Agent` gesendet:

```
Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36
(KHTML, like Gecko) Chrome/126.0 Safari/537.36
```

— der Chrome-Browser-Kennung aus `config/settings.yaml:549`
(`http.user_agent`), **nicht** `TelcoRadar/1.0`. Alle 13 Requests
beantwortete telekom.de mit HTTP 200; es gab **kein einziges** 403/406 und
damit auch keinen beobachtbaren UA-Wechsel im Sinne von Abnahmekriterium 2
— aber nur, weil die Browser-Kennung von Anfang an die PRIMÄRE ist und nie
abgelehnt wurde. Der ehrliche `TelcoRadar/1.0`-Absender wurde bei keinem
einzigen der 13 Requests auch nur versucht.

### Ursache, gemessen am Code

`collect.http.fetch()`:

```python
primary = http_cfg.get("user_agent", BROWSER_UA)
fallback = BROWSER_UA if _ist_ehrliche_kennung(primary) else BOT_UA
uas = (primary, fallback)
```

`http_cfg` kommt in `lokallauf_telekom.py` unverändert aus
`cfg.settings.get("http", {})`, also aus `config/settings.yaml`. Dessen
`http.user_agent` ist die Chrome-Kennung — **das ist die globale
Voreinstellung für JEDEN Collector dieses Projekts**, nicht nur für Telekom.
`primary` ist damit die Chrome-Kennung, `_ist_ehrliche_kennung(primary)` ist
`False`, also wird `fallback = BOT_UA` (`TelcoRadar/1.0`). Die Reihenfolge
`uas = (primary, fallback)` probiert also **zuerst Chrome, erst bei
403/406 TelcoRadar/1.0** — das genaue Gegenteil der Annahme, mit der R1
gearbeitet hat.

Die Telekom-Quelle trägt in `config/geraete_quellen.yaml` (Zeile 384 ff.)
keinen `user_agent:`-Überschreiber; ein solcher existiert im Bestand genau
einmal, für einen anderen Anbieter (Zeile 141, `BRIEF_SATURN_ADAPTER_R2`).
`config/tarif_quellen.yaml` kennt den Mechanismus für Tarifquellen gar
nicht — `tarif_crawler.sammle()` hat keinen Pfad für einen
Quellen-eigenen `User-Agent`.

**Das ist kein neuer Fehler dieser Runde oder von R1** — es ist der
Zustand, den `CLAUDE.md` §8a (Ende von Phase S) bereits als offenen Punkt
führt: *„`config/settings.yaml → http.user_agent` ist weiterhin eine
Chrome-Kennung (Beobachtung aus Phase Q, PM-Entscheidung steht aus). Alle
Messungen dieser Phase sind mit `TelcoRadar/1.0` gemacht"* — der letzte
Halbsatz beschreibt frühere Läufe, die (vermutlich testweise) mit einer
anderen Konfiguration liefen, nicht den heute stehenden Code-Zustand. R1
hat diese offene Frage übersehen und stattdessen eine Aussage über den
Absender aus dem Wissen über `_hole_fabrik`/`fetch()` **geraten**, ohne sie
zu messen. Dieser Lauf holt das nach — mit einem eindeutigen, negativen
Ergebnis.

## Warum das NICHT in dieser Runde behoben wird

`http.user_agent` ist eine **globale** Einstellung in
`config/settings.yaml`, die für alle 196 Quellen dieses Projekts gilt, nicht
nur für Telekom. Sie zu ändern hieße, den Absender für JEDEN anderen
Anbieter mitzuändern — ein glatter Verstoß gegen die Vorgabe dieses
Auftrags, *„ohne Daten anderer Anbieter anzufassen"*, und außerdem genau
die *PM-Entscheidung*, die laut `CLAUDE.md` seit Phase Q **aussteht** und
nicht in einem Beleg-Ticket nebenbei getroffen werden soll. Ein
Telekom-spezifischer `user_agent:`-Überschreiber (wie ihn eine andere Quelle
schon trägt) wäre zwar im Rahmen von „nur Telekom anfassen" möglich — aber
er wäre eine **Verhaltensänderung**, keine Beleg-Ergänzung, und dieser
Auftrag verlangt ausdrücklich *„Ergänze ausschließlich die fehlenden
Laufzeitbelege"*. Diese Runde liefert deshalb ausschließlich die Messung,
keine Reparatur.

## Kriterien-Abgleich

| # | Kriterium | Ergebnis |
|---|---|---|
| 1 | Kleiner, datensparsamer, versionierter Laufzeitbeleg pro Request | **erfüllt** — `outputs/beleg-telekom-lokallauf-2026-09-06.json`, 13 Einträge, je URL/Host/Status/gesendeter UA/`transport=http-get`/`browser=false`, keine Fremdinhalte |
| 2 | Beleg bestätigt `TelcoRadar/1.0` für alle heutigen Abrufe | **NICHT erfüllt** — der Beleg zeigt das Gegenteil: 13 von 13 mit der Chrome-Kennung aus `config/settings.yaml`. Kein 403/406 aufgetreten (die Chrome-Kennung wurde nie abgelehnt), also kein UA-*Wechsel* im engeren Sinn — aber auch kein einziger Versuch mit der ehrlichen Kennung. Ehrlich berichtet statt als Erfolg ausgegeben |
| 3 | Reiner HTTP-GET, kein Playwright/Selenium/Headless-Browser | **erfüllt** — beide Stufen liefen ausschließlich über `httpx.get` (via `collect.http.fetch`), keine Browser-Engine im Pfad |
| 4 | Skript erneut lokal ausgeführt, danach `render_site()`, Vollsuite, Berichtsabschluss | siehe unten |
| 5 | Nur auf `openclaw/ticket-telekom-taeglich-20260906`, kein Merge/Deploy | eingehalten |

**Das Urteil dieser Runde bleibt NEEDS_WORK** in der Sache, die R1
behauptet hatte (ehrlicher Absender) — mit dem Unterschied, dass jetzt eine
Messung statt einer Vermutung vorliegt, und dass die Ursache eine
projektweite, dem PM bereits bekannte offene Entscheidung ist, keine
Telekom-spezifische Nachlässigkeit.

## Ausführung

```
PYTHONPATH=src /opt/homebrew/bin/python3 scripts/lokallauf_telekom.py --frist 180
```

T1-Bilanz: `2 Quellen, 939 verlinkt, 10 geholt, 14 gelesen, 0 Grundlinie,
14 unveraendert, 0 geaendert, 0 Quarantaene, 0 Fehler` — identisch zu R1
(derselbe Tag, dieselben 14 Sätze, keine Preisänderung).

T2-Bilanz: `1 Anbieter abgefragt, 10 Listungen (0 neu), 0 Preispunkte,
0 gealtert, Bestand 595, 1.7s` — ebenfalls unverändert gegenüber R1 bis auf
den zweiten Messpunkt desselben Tages (`Telekom.laeufe` 5→6,
`funde_gesamt` 50→60, per Zähler — kein Datenverlust, R1 und R2 sind zwei
unabhängig gemessene Läufe desselben Kalendertags).

## Umfang der Änderung — nur Telekom, geprüft per Diff

| Datei | Geändert | Betrifft |
|---|---|---|
| `scripts/lokallauf_telekom.py` | Beleg-Instrumentierung ergänzt | Code, kein Datensatz |
| `data/state/geraete_db.json` | `Telekom.laeufe`/`funde_gesamt`, 10 Listungen (nur `quelle_url`-Query, `letzter_check`) | ausschließlich `Telekom` |
| `data/state/tarife.jsonl` | unverändert (gleicher Tag, gleiche Werte wie R1) | — |
| `data/state/geraete_tco.json` | unverändert (keine neuen Tarifstände seit R1) | — |
| `outputs/beleg-telekom-lokallauf-2026-09-06.json` | neu | Beleg, nur Telekom-Requests |
| `site/geraete.html`, `site/exporte/geraete-aktuell.csv` | neu gerendert, nur Telekom-Zeilen/Werte geändert (der zufällige OAuth-`state`-Parameter in `quelle_url`) | ausschließlich `Telekom` |
| `site/data/keyword-index.json` | nur `stand` geändert (Datums-Zeitbombe, `CLAUDE.md` §6) | mit `git checkout --` zurückgesetzt |
| `site/tarife.html` | unverändert (Tarifdaten identisch zu R1) | — |

Kein HTTP-Request an eine Nicht-Telekom-Domain in diesem Lauf (Log
geprüft: ausschließlich `telekom.de`- und `accounts.login.idm.telekom.com`-
Aufrufe, letzteres der SSO-Redirect der Telekom-Shopseite selbst).

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

## Tests

```
2777 passed, 14 skipped, 2 failed in 248.03s
```

Dieselben zwei vorbestehenden roten Tests wie in R1
(`tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung`,
`::test_der_leere_screenshot_wird_nicht_ausgeliefert`) — Promo-Bildbestand,
ohne Bezug zu Telekom-Tarif-/Gerätedaten oder zu dieser Änderung. Keine
neuen Roten. `scripts/pruefe_portal.py` wurde in dieser Runde nicht erneut
ausgeführt (kein Abnahmekriterium dieser Runde; R1 hat es bereits gegen
denselben Datenstand gemessen — 16/17 bestanden, Kriterium 8b vorbestehend).

## Bewusst offen

1. **Die PM-Entscheidung zu `config/settings.yaml → http.user_agent`
   steht weiterhin aus** — jetzt mit einem harten Messbefund statt einer
   Beobachtung: der Chrome-UA ist nicht nur „weiterhin eine Chrome-Kennung",
   er wird für Telekom (und vermutlich für jede andere Quelle ohne
   Überschreiber) tatsächlich als PRIMÄRER, erfolgreicher Absender
   verwendet. Zwei Lösungswege stehen offen und sind NICHT Teil dieses
   Auftrags: (a) `http.user_agent` global auf `TelcoRadar/1.0` drehen —
   träfe alle 196 Quellen und bräuchte eine Health-Check-Runde wie beim
   letzten Ausbau; (b) ein Telekom-spezifischer `user_agent:`-Überschreiber
   in `config/geraete_quellen.yaml` nach dem Muster von Zeile 141, plus ein
   äquivalenter Mechanismus für `tarif_crawler.sammle()`, der heute nicht
   existiert.
2. **Der Beleg-Mechanismus ist nur in `lokallauf_telekom.py` aktiv.** Ein
   allgemeiner, projektweiter Laufzeitbeleg (für den Wochenlauf oder den
   nächtlichen Geräte-Job) ist nicht gebaut und war nicht Teil dieses
   Auftrags.
3. **Der `robots.txt`-Abruf trägt ebenfalls die Chrome-Kennung** — die
   robots-Prüfung selbst ist damit korrekt (Status 200/301, keine Sperre
   für den gelesenen Pfad), aber sie liest die Regeln unter einem anderen
   Absender, als sie am Ende für den Seitenabruf gilt (derselbe Absender,
   da beide denselben `hole` benutzen — hier also konsistent, aber nur
   weil beide dieselbe, nicht-ehrliche Kennung tragen).

## Commits

Ein Commit auf `openclaw/ticket-telekom-taeglich-20260906`, kein Merge nach
`main`, kein Deploy.
