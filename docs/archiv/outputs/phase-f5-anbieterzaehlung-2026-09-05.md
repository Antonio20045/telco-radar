# Phase F-5 R2 — Anbieter-Zählwiderspruch: Fertigstellung

Auftragsgrundlage: `BRIEF_F5_ANBIETERZAHLUNG_R2.md`. Der vorherige Lauf auf diesem Branch hatte
Code + Tests bereits fertig geliefert (Commit `b15ee89`, siehe `BRIEF_F5_ANBIETERZAHLUNG.md`),
war aber vor dem letzten Schritt (Site rendern, `keyword-index.json` zurücksetzen, Bericht)
abgebrochen. Dieser Lauf holt genau das nach — **kein Eingriff in die Code-/Testlogik aus
`b15ee89`**.

## Was gemacht wurde

1. `PYTHONPATH=src /opt/homebrew/bin/python3 -m pytest -q` laufen lassen (blockierend, voller
   Lauf, 238,97 s).
2. `render_site(site, reports, load_config(root))` gegen den echten Bestand
   (`data/reports/`, `data/state/`) ausgeführt.
3. `site/geraete.html` committet (Commit `7886a68`), `site/data/keyword-index.json` per
   `git checkout HEAD -- …` auf den committeten Stand zurückgesetzt (Diff dazu 0 Zeilen).
4. Diesen Bericht geschrieben.

Kein anderer Code wurde angefasst.

## Testlauf

```
2 failed, 2757 passed, 14 skipped, 73 warnings in 238.97s (0:03:58)
FAILED tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung
FAILED tests/test_promo_seite.py::test_der_leere_screenshot_wird_nicht_ausgeliefert
```

Beide Roten sind die vorbestehenden, im Ticket namentlich erwarteten Screenshot-Tests
(Promo-Zweig, unrelated). **Keine neuen Roten.** Die Zahl (2757 statt der im Brief
genannten „~2752") liegt am neu hinzugekommenen `tests/test_geraete_anbieterzaehlung.py`
aus `b15ee89` (6 Tests) plus normaler Bestandsentwicklung seit der Maßstabs-Schätzung —
kein Befund, nur eine genauere Zahl als die Schätzung im Ticket.

## Vorher/Nachher je Beispielmodell

Zahlen aus dem Dropdown-Label (`#gr-modell option`) und dem Chart-`aria-label`
(`svg.gr-g0`), verglichen zwischen dem Stand vor `b15ee89` (Commit `2dc8bc4`, letzter
Merge davor) und dem jetzt gerenderten `site/geraete.html`.

| Modell | Dropdown vorher | Dropdown/Chart nachher | Bemerkung |
|---|---|---|---|
| Apple iPhone 17 Pro 256 GB (Leitfrage) | 2 Anbieter | **6 Anbieter** (Dropdown == Chart) | aus der Commit-Beschreibung von `b15ee89` als „2 gegen 6" benannt — exakt reproduziert |
| Apple iPhone 16 128 GB | 2 Anbieter | **4 Anbieter** (Dropdown == Chart) | |
| Samsung Galaxy S25 128 GB | 2 Anbieter | **4 Anbieter** (Dropdown == Chart) | |

Vor der Änderung zählte das Dropdown ausschließlich TCO-Bündel-Anbieter (fast überall
„2", weil die meisten Modelle genau zwei Bündelpartner haben); der Chart darunter zählte
schon vorher die echten Preispunkte-Reihen. Nach der Änderung liest das Dropdown-Label
dasselbe Feld (`m.zeitreihe.anbieterzahl`), das auch das Chart-aria-label füllt — geprüft
über den ganzen Dropdown-Bestand (`test_jedes_modell_im_dropdown_stimmt_mit_seinem_
chart_ueberein`), nicht nur an den drei Beispielen.

### Der dritte Testfall: Modell ohne Zeitreihendaten

Der echte Bestand enthält tatsächlich drei Modelle ohne Chart (keine
Preispunkte-Reihe): `samsung-galaxy-s24-ultra-512`, `nothing-phone-4a-pro-128`,
`apple-iphone-16-pro-max-256`. An allen dreien zeigt sich derselbe Effekt:

| Modell | Dropdown vorher | Dropdown nachher | Chart |
|---|---|---|---|
| Samsung Galaxy S24 Ultra 512 GB | 1 Anbieter | **0 Anbieter** | kein Chart |
| Nothing Phone (4a) Pro 128 GB | 1 Anbieter | **0 Anbieter** | kein Chart |
| Apple iPhone 16 Pro Max 256 GB | 1 Anbieter | **0 Anbieter** | kein Chart |

Vorher behauptete das Dropdown „1 Anbieter" (die Zahl seines einen TCO-Bündels), obwohl
kein Chart und keine einzige Preispunkte-Reihe existiert — genau der Widerspruch, den das
Ticket unter Abnahmekriterium 3 (Testgruppe c) verlangt hatte zu schließen. Jetzt zeigt
das Dropdown den ehrlichen Leerzustand „0 Anbieter", identisch zum fehlenden Chart. Dieser
Fall ist bereits von `test_modell_ohne_zeitreihe_bleibt_ein_ehrlicher_leerzustand`
(konstruierte Fixture) UND von den drei realen Modellen oben (am echten Bestand,
nachgemessen in diesem Lauf) abgedeckt.

## Offene Fälle (aus `b15ee89` übernommen, unverändert)

Aus der Commit-Beschreibung von `b15ee89`, hier nur dokumentiert, nicht neu bewertet:

> Händler (Amazon/Expert/Saturn) sind laut PM-Text „kein Anbieter", stehen aber im Chart
> als eigene Reihe, sobald sie für ein Gerät einen Barpreis beitragen
> (`geraete_verlauf.reihen_fuer_listungen` filtert nicht nach `anbieter_typ`) — sie jetzt
> herauszurechnen würde Dropdown und Chart wieder auseinanderlaufen, weil der Chart per
> Auftrag unverändert bleibt („er ist die Referenz").

Keine dritte Zählweise wurde erfunden; der Fall bleibt als offene Frage stehen, wie im
R2-Auftrag vorgesehen.

## Abnahme gegen `BRIEF_F5_ANBIETERZAHLUNG_R2.md`

| # | Kriterium | Status |
|---|---|---|
| 1 | `pytest -q` blockierend, 2 failed / ~2752 passed / 14 skipped, keine neuen Roten | ✅ 2 failed / 2757 passed / 14 skipped |
| 2 | `render_site()` gegen echten Bestand, `site/geraete.html` zeigt neue Zählweise, committet | ✅ Commit `7886a68` |
| 3 | `keyword-index.json` auf `main`-Stand zurückgesetzt, Diff 0 Zeilen | ✅ `git checkout HEAD --` |
| 4 | Bericht mit Vorher/Nachher je Beispielmodell + offene Fälle | ✅ dieser Bericht |
| 5 | Kein Eingriff in Code-/Testlogik aus `b15ee89` | ✅ nichts außer Render + Report angefasst |

## Commits dieses Laufs

- `7886a68` — `geraete: F-5 - site neu gerendert (Anbieterzaehlung Dropdown/Chart)`
- (dieser Bericht, eigener Commit)

Branch `openclaw/ticket-f5-anbieterzaehlung`, nicht gemerged, kein Deploy — wie
vorgeschrieben.
