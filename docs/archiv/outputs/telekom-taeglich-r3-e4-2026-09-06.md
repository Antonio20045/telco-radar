# Telekom-Tagesbetrieb, Runde 3 (E4) — Per-Anbieter-Absender, Lokallauf, Beleg (06.09.2026)

Auftragsgrundlage: `BRIEF_TELEKOM_TAEGLICH_R3_E4.md` (Workspace-Engineer).
Pflichtlektüre: `CLAUDE.md`, `outputs/telekom-taeglich-r2-beleg-2026-09-06.md`,
`outputs/beleg-telekom-lokallauf-2026-09-06.json` (Runde 2, auf dem separaten
Branch `openclaw/ticket-telekom-taeglich-20260906`), `config/geraete_quellen.yaml`,
`src/telco_radar/collect/http.py`.

## Ausgangslage — und warum diese Runde nicht auf R2 aufbaut

Dieser Ticket-Branch zweigt von `main` ab (`b7af10e`), nicht von R2s Branch.
R2s Welt (`scripts/lokallauf_telekom.py`, ein aktiver Telekom-Geraete-Adapter
`methode: telekom_kategorie`, `_ist_ehrliche_kennung` in `http.py`, ein
User-Agent-Override "Zeile 141" in `geraete_quellen.yaml`) existiert auf
`main` **nicht** — R2s Branch trug zusätzlich eine ganze Reihe unrelated
Feature-Commits (Geräteradar-Bündelerhebung B-1, F-5, f4a, …), die nie nach
`main` gemerged wurden. Ein Cherry-Pick von dort hätte fremde, unmerged
Anbieter-Arbeit mitgezogen — ein Verstoß gegen die Hausregel "keine fremden
Anbieter-Daten verändern". Diese Runde ist deshalb **gegen den echten
`main`-Stand neu gebaut**, mit R2s Bericht als Befund- und Musterquelle, nicht
als Codebasis.

Nachgemessen auf `main`: **Telekoms Geräteradar-Quelle ist `aktiv: false`**
(`config/geraete_quellen.yaml:278`, AWS-WAF/kein Preis ohne Vertrag lesbar) —
die einzige AKTIVE Telekom-Datenebene ist der Tarif-Sammler
(`config/tarif_quellen.yaml`). Diese Runde behandelt deshalb ausschließlich
T1 (Tarife); ein T2-Geräteanteil existiert auf `main` nicht und ist nicht
Teil dieses Auftrags.

`data/state/tarife.jsonl` trug vor diesem Lauf **null** Telekom-Zeilen (nur
o2) — Telekoms Tarifdaten sind mit diesem Lauf zum ersten Mal auf `main`
erhoben, nicht aktualisiert.

## Was gebaut wurde

### 1. Per-Anbieter-Override für Telekom (Kriterium 1)

`config/settings.yaml -> http.user_agent` ist die globale Chrome-Kennung für
alle 196 Quellen — sie zu ändern hätte jeden anderen Anbieter mitgetroffen
und ist unverändert geblieben. Stattdessen:

- `tarif_crawler.Quelle` bekommt ein neues Feld `user_agent: str | None`.
- `lade_quellen()` liest es aus `config/tarif_quellen.yaml`.
- `config/tarif_quellen.yaml`: **nur** der Telekom-Eintrag trägt
  `user_agent: "TelcoRadar/1.0 (+https://github.com/Antonio20045/telco-radar)"`.
  o2 (und jede künftige Quelle ohne das Feld) bleibt ohne Override.
- `sammle()` baut je Quelle `quelle_cfg = {**http_cfg, "user_agent": …}` und
  reicht **diese** Kopie an `hole()` durch — für die Einstiegsseite UND für
  jedes von ihr aus geholte Dokument. `http_cfg` selbst wird nie mutiert.

**Test, der das beweist** (`tests/test_tarif_crawler.py`):
- `test_echte_config_gibt_telekom_die_ehrliche_kennung` — gegen die ECHTE
  `config/tarif_quellen.yaml`: Telekom trägt einen mit `TelcoRadar/1.0`
  beginnenden Absender ohne "Chrome"/"Mozilla", jede andere Quelle `None`.
- `test_telekom_pfad_uebergibt_die_ehrliche_kennung_an_fetch` — ein
  stub-`hole()` zeichnet den `http_cfg` auf, den `sammle()` für die
  Einstiegsseite UND das Dokument tatsächlich übergibt; beide tragen den
  Override, die globale Basis-Konfiguration bleibt unangetastet
  (`basis_cfg["user_agent"]` unverändert nach dem Lauf).
- `test_quelle_ohne_user_agent_bekommt_die_globale_konfiguration` — o2 (bzw.
  jede Quelle ohne `user_agent:`) bekommt exakt dasselbe `http_cfg`-Objekt
  (`is basis_cfg`), kein untergeschobener Override.

### 2. `scripts/lokallauf_telekom.py` (Kriterium 2)

Neu gebaut (existiert auf `main` nicht), auf T1 beschränkt (siehe oben):
`tarif_crawler.sammle()` NUR für die Telekom-Quelle, umschlossen von einer
Hüllfunktion `_hole_mit_beleg`, die JEDEN echten Abruf protokolliert — URL,
Host, HTTP-Status, der tatsächlich **gesendete** `User-Agent` (aus
`resp.request.headers`, dem Objekt, das httpx nach dem echten Request
zurückgibt — nicht aus der Konfiguration, die ihn vorschreiben soll), sowie
explizit `transport="http-get"` und `browser=False` (reines `httpx.get`, kein
Playwright/Selenium/Headless-Browser). Keine Antwortkörper, Cookies oder
Zugangsdaten. `fetch()` selbst bleibt unverändert; die Instrumentierung ist
ausschließlich in diesem Skript aktiv.

Das Skript schreibt den Beleg nach
`outputs/beleg-telekom-lokallauf-<datum>.json` und prüft selbst, ob **alle**
Einträge mit `TelcoRadar/1.0` gesendet wurden — ein Befund wird als `ERROR`
protokolliert, nicht stillschweigend als Erfolg gemeldet.

## Messergebnis — ausgeführt, lokal, browserlos, einmal

Vorab-Messung direkt gegen telekom.de (nicht Teil des Laufs, nur Nachweis,
dass die ehrliche Kennung überhaupt durchkommt und kein Bot-Schutz umgangen
werden muss):

```
$ curl -sS --max-time 15 -o /dev/null -w "%{http_code}\n" \
    -A "TelcoRadar/1.0 (+https://github.com/Antonio20045/telco-radar)" \
    "https://www.telekom.de/produktinformationsblatt"
200
```

Lauf:

```
$ PYTHONPATH=src /opt/homebrew/bin/python3 scripts/lokallauf_telekom.py
...
T1-Bilanz: {'quellen': 1, 'einstiege': 1, 'verlinkt': 1114, 'geholt': 5,
  'gelesen': 5, 'quarantaene': 0, 'grundlinie': 5, 'unveraendert': 0,
  'geaendert': 0, 'kleingedruckt': 0, 'fehler': 0, 'meldungen': 0, …}
Laufzeitbeleg geschrieben: outputs/beleg-telekom-lokallauf-2026-09-06.json
  (6 Requests, alle_ehrlich=True)
Alle 6 Telekom-Requests bestaetigt mit ehrlichem TelcoRadar/1.0-Absender,
  reines HTTP-GET (kein Browser).
```

`outputs/beleg-telekom-lokallauf-2026-09-06.json`: **6 von 6 Requests**
(die Einstiegsseite `produktinformationsblatt` + 5 Dokumente), jeder mit
`transport="http-get"`, `browser=false`, HTTP-Status **200**, und
`user_agent` **exakt** `TelcoRadar/1.0 (+https://github.com/Antonio20045/telco-radar)`
— gelesen aus `resp.request.headers`, also der tatsächlich gesendeten
Kopfzeile, nicht aus der Konfiguration. Kein einziger Chrome-/Mozilla-UA im
Beleg, kein UA-Wechsel aufgetreten (keine 403/406). Der `_hole_mit_beleg`-
Wrapper zeichnet auch den Fehlerfall auf (`resp` aus der Exception), falls
ein künftiger Lauf doch auf einen Wechsel trifft.

Fünf Dokumente wurden gelesen: `magentamobil-basic-20240801` und **vier**
verschiedene `magentamobil-l-*`-Versionsstände (2017/2018/2022/2024) —
kein neuer Fehler dieser Runde, sondern eine vorbestehende Eigenart der
`bevorzugt:`-Sortierung in `config/tarif_quellen.yaml`: das Muster
`"magentamobil-l-2"` matcht als Teilstring JEDE mit `magentamobil-l-2`
beginnende Jahreszahl (2017, 2018, 2022, 2024), nicht nur "2024" — dadurch
verdrängen vier L-Versionsstände die M/S/XL-Slugs aus den fünf
`max_dokumente`-Plätzen. **Bewusst nicht behoben**: außerhalb des Auftrags
(betrifft die Dokumentenauswahl, nicht den Absender/Beleg), und eine
Korrektur der Sortierlogik ist eine Verhaltensänderung des Sammlers, keine
Beleg-Ergänzung.

## Kriterien-Abgleich

| # | Kriterium | Ergebnis |
|---|---|---|
| 1 | Per-Anbieter-Override für Telekom, `config/settings.yaml` unverändert, Test beweist die Übergabe an `fetch()` | **erfüllt** — `config/tarif_quellen.yaml` (nur Telekom), `tarif_crawler.sammle()` reicht `quelle_cfg` durch, drei neue Tests |
| 2 | `scripts/lokallauf_telekom.py` lokal, browserlos, einmal ausgeführt; versionierter, redigierter Beleg mit URL/Host/Status/gesendetem UA/`transport=http-get; browser=false` | **erfüllt** — `outputs/beleg-telekom-lokallauf-2026-09-06.json`, 6 Einträge |
| 3 | Jeder Belegdatensatz exakt `TelcoRadar/1.0` (Zusatz erlaubt), kein Chrome/Mozilla, jeder Request HTTP-GET und `browser=false` | **erfüllt** — 6 von 6, `alle_ehrlich: true` |
| 4 | Tagesdaten/Render/Bericht aktualisiert; `keyword-index.json` zurückgesetzt | **erfüllt** — `data/state/tarife.jsonl` (+5 Telekom-Grundlinienzeilen), `site/tarife.html` neu gerendert (Telekom jetzt in "Erfasst:", Positionskarte, Vollständigkeits-Kennzahlen); `site/data/keyword-index.json` mit `git checkout --` zurückgesetzt (nur die Datums-Zeitbombe hätte sich geändert) |
| 5 | Vollsuite einmal, nur die zwei bekannten Promo-Screenshot-Fehler zulässig | **erfüllt** — siehe unten |
| 6 | Nur Ticket-Branch, kein Merge/Deploy, Zwischencommits, sauberer Baum, Bericht unter diesem Pfad | eingehalten |

## Vollsuite

```
PYTHONPATH=src /opt/homebrew/bin/python3 -m pytest -q
...
FAILED tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung
FAILED tests/test_promo_seite.py::test_der_leere_screenshot_wird_nicht_ausgeliefert
2 failed, 2260 passed, 13 skipped in 140.09s
```

Genau die zwei bekannten, vorbestehenden Promo-Screenshot-Fehler (leere/
beschädigte Bilddateien unter `site/promo/images/`, dokumentiert seit dem
Handover-Eintrag vom 03.09.2026) — ohne jeden Bezug zu Telekom-Tarifdaten
oder dieser Änderung. Keine neuen roten Tests.

## Umfang der Änderung — nur Telekom, geprüft per Diff

| Datei | Geändert | Betrifft |
|---|---|---|
| `config/tarif_quellen.yaml` | `user_agent:`-Zeile ausschließlich beim Telekom-Eintrag | nur Telekom |
| `src/telco_radar/collect/tarif_crawler.py` | `Quelle.user_agent`, `lade_quellen()`, `quelle_cfg` in `sammle()` | Code, wirkt nur für Quellen mit gesetztem Feld (heute: nur Telekom) |
| `tests/test_tarif_crawler.py` | drei neue Tests | Test, kein Datensatz |
| `scripts/lokallauf_telekom.py` | neu | Skript, kein Datensatz |
| `outputs/beleg-telekom-lokallauf-2026-09-06.json` | neu | Beleg, nur Telekom-Requests |
| `data/state/tarife.jsonl` | +5 Zeilen, ausschließlich `anbieter: Telekom`; die drei vorhandenen o2-Zeilen unverändert (per Diff geprüft) | ausschließlich Telekom |
| `site/tarife.html` | neu gerendert; Diff zeigt nur Telekom-Inhalte plus die aggregierten Bilanz-Kennzahlen (3→8 Tarife, 1→2 Anbieter, 0→5 in der Karte, 3→8 mit Lücken) und den Satz "Erfasst: Telekom, o2." — kein einzelner o2-Wert geändert | Telekom + mechanisch fällige Summen |
| `site/data/keyword-index.json` | nur `stand` geändert (Datums-Zeitbombe) | mit `git checkout --` zurückgesetzt, nicht committet |

Kein HTTP-Request an eine Nicht-Telekom-Domain in diesem Lauf (Log geprüft:
ausschließlich `www.telekom.de`).

`config/geraete_quellen.yaml`: nicht verändert. Telekoms Eintrag dort bleibt
`aktiv: false` — außerhalb des Geltungsbereichs dieser Runde, siehe
"Ausgangslage" oben.

## Bewusst offen

1. **Die PM-Entscheidung zu `config/settings.yaml -> http.user_agent`
   bleibt aus** — unverändert Absicht dieser Runde (nur Telekom betroffen,
   nicht die globale Einstellung).
2. **Die `bevorzugt:`-Substring-Falle** in `config/tarif_quellen.yaml`
   (siehe Messergebnis oben) sorgt dafür, dass Telekoms Tarifbestand aktuell
   vier historische MagentaMobil-L-Versionsstände statt der beabsichtigten
   S/M/L/XL/Basic-Auswahl trägt. Nicht Teil dieses Auftrags; beim nächsten
   Tarif-bezogenen Ticket beheben (Muster auf `"magentamobil-l-2024"` o.ä.
   verschärfen).
3. **Telekoms Geräteradar bleibt `aktiv: false`** (AWS-WAF, kein Preis ohne
   Vertrag lesbar) — unverändert seit der letzten Messung, kein Teil dieses
   Auftrags.
4. **Ein allgemeiner, projektweiter Laufzeitbeleg** (für den Wochenlauf oder
   andere Anbieter) ist nicht gebaut; der Mechanismus ist ausschließlich in
   `lokallauf_telekom.py` aktiv.
5. **`scripts/pruefe_portal.py`** wurde in dieser Runde nicht ausgeführt
   (kein Abnahmekriterium dieses Auftrags).

## Commits

Zwei Commits auf `openclaw/ticket-telekom-taeglich-r3-e4`, kein Merge nach
`main`, kein Deploy, kein Push in dieser Runde.
