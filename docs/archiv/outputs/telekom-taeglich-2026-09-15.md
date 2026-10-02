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
Bündel-Einstiege `…/smartphones?tariffId=MF_1777x` — dazu **10 Abrufe gegen
`1und1.de`/`mobile.1und1.de` (www: 2, mobile: 8). Diese Abrufe waren die
Scope-Verletzung des Laufs** — verursacht durch `sammle_simonly()` in
`run_geraete_stage()`, das seit dem 09.09. fester Bestandteil der Stage ist
und im Lokallauf ohne Anbieterbegrenzung lief (7 Tarifdetails,
„45 SIM-only-Referenzen aus 56 Tarifen"). Sie sind geschehen und bleiben
hier dokumentiert; bereinigt und behoben ist die Folge — siehe
„Nachbesserung Runde 2". Kein Konfigurations- oder Codeeingriff an anderen
Anbietern; der globale UA in `config/settings.yaml` ist unangetastet
(Per-Anbieter-Override nur Telekom, siehe Skript-Docstring).

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

> **Korrektur (Runde 2):** Die Zahl „45 SIM-only-Referenzen aus 56
> Tarifen" war die Protokollzeile der Stage — sie misst die ABGELEITETE
> Menge, nicht den berechtigten Schreibumfang dieses Laufs. Nach der
> Bereinigung tragen **10 Referenzen (Telekom)** heutige Daten; die
> übrigen **35 Fremd-Referenzen** (1&1 7, Vodafone 5, congstar 10,
> o2 13) wurden vom Lauf zu Unrecht neu datiert — 28 davon ohne jeden
> Abruf (reine Bestandsableitung), 7 (1&1) über 10 Abrufe gegen
> 1und1.de. Siehe „Nachbesserung Runde 2".

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

> **Korrektur (Runde 2):** Die Zeile `geraete_tco.json` galt ursprünglich
> „35 Bündel + Referenzen". Nach der Bereinigung zählt der Diff gegen
> `origin/main` **45 geänderte Einträge, alle Telekom**: 35 Bündel
> (`abgerufen_am`/`last_verified` 09.09.→15.09., dazu 30 `quelle_url` mit
> neuem `&forwardTradeInApplied=false`-Parameter) und 10 SIM-only-
> Referenzen. **Kein Nicht-Telekom-Eintrag ist mehr verändert** — die
> ursprünglich 35 Fremd-Änderungen sind auf den Basisstand
> (`9dd8d59`) zurückgesetzt.

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

Dazu in Runde 2 (Nachbesserungs-Artefakte, eigene Commits):

```
data/state/geraete_tco.json          (Bereinigung der 35 Fremd-Einträge)
scripts/lokallauf_telekom.py         (Scope + Lauf-Manifest)
src/telco_radar/analyze/tco_store.py (Anbieter-Scope am Referenz-Store)
src/telco_radar/geraete_pipeline.py  (referenz_anbieter-Parameter)
tests/test_geraete_pipeline.py, tests/test_tco_model.py (jeweils 1 neuer Test)
outputs/beleg-telekom-lokallauf-2026-09-15-run.json (nachgetragener Manifest)
outputs/telekom-taeglich-2026-09-15.md (dieser Bericht)
site/geraete.html                     (Neu-Render nach Bereinigung)
```

Vor dem Commit geprüft: Diff nur auf die genannten Pfade, Branch
`openclaw/ticket-telekom-taeglich-20260915` (Basis `origin/main`), Status
sonst sauber, kein `uv.lock`, kein Stash-Rest. Gepusht wird ausschließlich
dieser Branch; kein Merge nach `main`, kein Deploy, kein Hook-Curl.

## Nachbesserung Runde 2 (15.09.2026, nach der Abnahme)

Der Lauf bleibt **genau ein Messpunkt** — kein zweiter Abruf irgendeiner
Art ist erfolgt: beide Beleg-Dateien sind byte-identisch mit Commit
`316eb69` (SHA-256 im Lauf-Manifest, s. u.), es wurde ausschließlich
lokaler State, Code und der Bericht angefasst.

### Ursache — zwei Stellen in `run_geraete_stage()`

Der Schreibpfad des Telefons der Fremd-Änderungen (nachgegangen in
`src/telco_radar/geraete_pipeline.py` und `analyze/tco_store.py`):

1. **Der 1&1-Abruf:** `sammle_simonly(hole, heute)` (S-5, 09.09.) lief
   als fester Teil der Referenzstufe — ohne Anbieterbegrenzung. Das sind
   die 10 Requests gegen `www.1und1.de` (2) und `mobile.1und1.de` (8);
   sie lieferten 7 frische 1&1-Referenzen mit `abgerufen_am: 2026-09-15`.
2. **Das Neu-Datieren der Fremden:** die Referenzstufe leitet ihren
   Maßstab aus dem GESAMTEN `tarife.jsonl` ab (`aus_bestand(bestand)`,
   alle 56 Tarife) und `ersetze_referenzen(referenzen, heute)` frischt
   via `setze_referenzen()` **jeden** Eintrag mit `last_verified: heute`
   auf — auch die 28 (o2 13, congstar 10, Vodafone 5), deren Anbieter in
   diesem Lauf weder drankam noch abgerufen wurde. Kein Konfigurations-
   oder Codeeingriff — aber ein Schreibzug auf fremde Bestandsdaten.

Die Kopplung ist **Design**, nicht Versehen: die SIM-only-Referenzen sind
EIN global abgeleiteter Maßstab („Heute gibt es genau eine Quelle",
Doku in `tco_store.ersetze_referenzen`). Ein einfaches Wegfiltern der
Fremden aus der Ersetzungsmenge hätte sie **gelöscht** — der
`veraltet`-Zweig von `ersetze_referenzen` nimmt alles weg, was nicht in
der Menge steht. Deshalb wurde die Begrenzung als expliziter
Anbieter-Scope gebaut und nicht als Filter davor.

### Behoben — Ursache, nicht Symptom

| Stelle | Änderung |
|---|---|
| `analyze/tco_store.py` | `setze_referenzen`/`ersetze_referenzen` tragen einen optionalen `anbieter`-Scope (Menge von Anbieternamen): Fremde werden weder aufgefrischt noch datiert noch als veraltet entfernt. Default `None` = alle — der nächtliche Gesamtlauf (`geraete.yml`, `pipeline.py`) rechnet exakt wie bisher |
| `geraete_pipeline.py` | `run_geraete_stage(…, referenz_anbieter=None)`; bei gesetztem Scope ohne 1&1 wird `sammle_simonly()` **nicht aufgerufen** (kein Netz-Abruf bei Fremden) |
| `scripts/lokallauf_telekom.py` | ruft die Stage mit `referenz_anbieter={"Telekom"}`; schreibt zudem einen Lauf-Manifest (s. u.) |

Neue Tests (beide grün, Gegenprobe jeweils im selben Test):
`tests/test_geraete_pipeline.py::test_scoped_lauf_datiert_keine_fremdanbieter_und_ruft_sie_nicht_ab`
(Stage: 1&1-Eintrag bytegleich auf altem Stand, kein 1und1-Abruf im
Recorder; vorheriger Lauf ohne Scope datiert beide — beweist, dass der
Scope der Grund ist) und
`tests/test_tco_model.py::test_der_scope_veraendert_und_loescht_keine_fremdanbieter`
(Store: fremde Referenz bleibt bei Scoped-Ersetzung stehen, ohne Scope
wird dieselbe Menge sie löschen).

**Offen, bewusst nicht angefasst:** die drei weiteren Lokallauf-Skripte
(`lokallauf_congstar.py`, `lokallauf_saturn.py`, `lokallauf_einsundeins.py`)
haben denselben Schreibpfad und können denselben Befund erzeugen. Der Fix
ist generisch; die Umstellung der drei Skripte ist ein eigener Schritt
(je Skript eine Zeile plus Blick auf den jeweilig richtigen
Anbieternamen) und gehört nicht in diese Bereinigung.

### Revert-Umfang (Kriterium 2, Beleg)

`data/state/geraete_tco.json`: die **35 Fremd-Einträge** in `sim_only`
wurden auf den exakten Basisstand (`9dd8d59`) zurückgesetzt — die
Basis-Dicts, nicht Feldpflege. Zählung des Diffs `origin/main..HEAD`
nach Anbieter danach:

```
sim_only: geaendert=10  neu=0 weg=0 -> {'telekom': 10}
buendel:  geaendert=35  neu=0 weg=0 -> {'telekom': 35}
```

Telekom-Änderungen bleiben vollständig erhalten, einschließlich der
echten Preisbeobachtung (iPhone 17 256 GB violett, 948,60 → 1.096,20 €,
Preispunkt in `geraete_preise.jsonl` unberührt) und der 35
Bündel-Messungen. `updated: "2026-09-15"` bleibt stehen — Telekom wurde
heute tatsächlich geschrieben.

### „Genau einmal" belegbar (Kriterium 4)

Neu: `outputs/beleg-telekom-lokallauf-2026-09-15-run.json` — Run-ID
(UUID), Start-/Endzeit, Exit-Status, SHA-256 beider Beleg-Dateien,
`nachgetragen: true` mit Begründung. Ehrlich abgeleitet: Start/Ende sind
**null** — der Lauf von Runde 1 erfasste keine Zeitstempel, die einzige
exakte Kante ist Commit `316eb69` (AuthorDate 2026-09-15T04:46:36Z), der
nach Lauf, Render und Suite gesetzt wurde; jede genauere Angabe wäre
geraten. Künftige Läufe schreiben ihren Manifest selbst
(`_schreibe_manifest` im Skript, mit `exit_status` auch im Crash-Fall).

### Render und Suite nach der Bereinigung

- Neu gerendert mit `load_config(root)` (CLAUDE.md §7).
  `site/data/keyword-index.json`: **0 Zeilen Diff gegen `origin/main`**.
- Der Preismarker `1.096,20` steht weiterhin auf `site/geraete.html`
  (18 Vorkommen); die Bereinigung hat ihn nicht gekippt. Vom Neu-Rendern
  geändert wurde allein `site/geraete.html` (die SIM-only-Tabelle zeigt
  Abrufdaten).
- Vollsuite an HEAD und am unveränderten Basisbaum `9dd8d59`
  (Temp-Worktree):

```
Basis 9dd8d59: 1 failed, 2941 passed, 12 skipped in 351.02s
HEAD (Runde 2): 1 failed, 2943 passed, 12 skipped in 350.88s
               (Differenz +2 passed = die zwei neuen Scope-Tests)
```

  Der einzige Failed ist auf BEIDEN Bäumen derselbe Test mit demselben
  Fehlerbild:
  `tests/test_geraete_lifecycle.py::test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen`,
  `AssertionError: 52` (`assert len(unbewegt) >= 80`) — der im
  CLAUDE.md-Kontext bekannte, datenstandsbedingte vorbestehende Aussetzer,
  in Runde 1 am Basisbaum identisch nachgewiesen. **Die zwei
  Promo-Screenshot-Roten aus Runde 1 sind diesmal auf beiden Bäumen
  grün** (an HEAD nachgemessen: `3 passed, 20 deselected`). Warum sie in
  Runde 1 fielen und heute nicht mehr, ist von hier aus nicht rekonstruierbar —
  auf beiden Bäumen verhalten sie sich identisch, und zählen dürfen sie nach
  Auftrag nur als dokumentierte vorbestehende Rote. Kein neuer Roter kommt aus
  der Nachbesserung; die Bereinigung hat das Fehlerbild des Lifecycle-Tests
  nicht verändert.

## Fazit

Neuer, ehrlicher Messpunkt 15.09.2026 für beide Telekom-Zeitreihen gesetzt:
14 Tarifsätze bestätigt, eine echte Geräte-Preisänderung (iPhone 17, +15,6 %)
und zwei Auslistungen beobachtet, beides mit Beleg-URL aus demselben Lauf.
Beide Laufzeitbelege weisen alle 28 Requests als `TelcoRadar/1.0`-HTTP-GET
ohne Browser aus. Suite ohne neue Regression (der dritte Rote ist am Basisbaum
identisch reproduziert), `keyword-index.json` exakt auf Basis. Die Zeitreihe
ist damit nach den zwei kontingentbedingten Lücken wieder lückenlos
fortgeschrieben.

Runde 2 hat den Lauf auf seinen berechtigten Umfang zurückgeschnitten: Die
Messwerte selbst (Tarife, Preispunkt, Bündel, Auslistungen) bleiben — sie
sind Telekom-Beobachtungen aus diesem einen Lauf. Was weg ist, ist nur die
Kollateralschreiberei: 35 ohne Berechtigung neu datierte Fremd-Referenzen,
zurückgesetzt auf den Basisstand, plus die Ursache im Code behoben. Der
Messpunkt bleibt **genau einer** — kein zweiter Abruf, beide Belege
byte-identisch mit dem ersten Commit.
