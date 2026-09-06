# B1 R2 — Finisher: Vollsuite blockierend, dann der echte Lokallauf (05.09.2026)

Auftragsgrundlage: `BRIEF_B1_R2_FINISH.md`. Aufsetzend auf R1 (`8b13389`,
Auto-Rettung 19:03 Uhr), das den Vodafone-Adapter samt Buendel-Lesart und
Tarifnamen-Aufloesung gebaut, aber nie die Vollsuite gelaufen und den
Erhebungsschritt nie ausgefuehrt hat — R1 endete auf einer
Monitor-Wartepause. Diese Session hat aktiv gepollt (Prozess-Log +
`ps`/`kill -0` statt Notification-Wartestand) und beide fehlenden Schritte
nachgeholt.

## Ergebnis in einem Satz

**253 rechenbare Vodafone-Buendel** (vorher 0), Vollsuite wieder bei **2
failed / 2777 passed / 14 skipped** — die zwei vorbestehenden
Promo-Screenshot-Roten, nichts sonst — nachdem eine eigene, unbemerkte
Regression aus R1s Commit zurueckgesetzt wurde. Drei Commits, jeder Schritt
einzeln:

| Commit | Schritt |
|---|---|
| `26054b2` | Fix: R1s Betrag-Fallback (unnoetig fuer B1) zurueckgesetzt, o2-Test wieder gruen |
| `7bacfb9` | Der echte Lokallauf: 253 Vodafone-Buendel in `geraete_tco.json` |
| (dieser) | Bericht + Korrektur der veralteten Schaetzung in `config/geraete_quellen.yaml` |

---

## Schritt 1 — Vollsuite blockierend, aktiv gepollt

Erster Lauf (vor jeder Aenderung, reiner Bestandsaufnahme-Lauf):
**3 failed, 2776 passed, 14 skipped** (255,74s). Zwei der drei Roten waren
die erwarteten vorbestehenden Promo-Screenshot-Tests
(`test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung`,
`::test_der_leere_screenshot_wird_nicht_ausgeliefert`). Der dritte war
**neu und unerwartet**:
`test_geraete_buendel_o2.py::test_der_ganze_weg_an_der_echten_antwort`
(`assert len(bilanz.buendel) == 65` schlug mit `66` fehl).

**Ursache gefunden, nicht vermutet.** `git show 8b13389 --
src/telco_radar/analyze/tco_buendel.py` zeigt: R1 hat
`bestand.loese(anbieter, tarif_name, betrag=satz.get("tarif_monatlich"),
slug=...)` eingefuehrt — einen dritten Aufloesungsweg ueber den
Monatsbetrag, den kein einziger Vodafone-Test brauchte
(`test_geraete_buendel_vodafone.py` prueft ausschliesslich Guete `HOCH`).
In der o2-Testfixture hat der Promo-Tarif "O2 Mobile on Demand M" (ohne
"Plus") einen Monatsbetrag von 19,99 EUR, der **eindeutig** auf den
Bestandseintrag "o2:o2-mobile-on-demand-m" trifft — genau der Fall, den
die Testzeile "steht in keiner SIM-only-Kachel und loest deshalb nicht
auf" bewusst offen halten sollte. R1 hat das nie gesehen: die eigenen "20
gruenen Tests" waren nur die neue Vodafone-Testdatei, nie ein
Vollsuite-Lauf.

**Behoben durch Ruecknahme** (`26054b2`): die neun Zeilen (Kommentar +
`betrag=`-Parameter) entfernt, `bestand.loese()` wieder nur Name -> Slug.
`Tarifbestand.ueber_betrag()` selbst ist unveraendert und bleibt fuer
andere Aufrufer nutzbar — nur dieser eine, ungebrauchte Aufruf ist weg.
Gezielter Rerun bestaetigt: `tests/test_geraete_buendel_o2.py
tests/test_geraete_buendel_vodafone.py` -> **41 passed** (21 + 20).

**Vollsuite nach dem Fix, erneut blockierend gelaufen** (nicht auf die
Task-Notification gewartet — die kam beide Male sofort und meldete nur den
Start-Wrapper, nicht den echten Hintergrundprozess; ueberprueft per
`ps -p <PID> -o etime` und aktivem Log-Poll bis der Prozess wirklich
beendet war):

```
2 failed, 2777 passed, 14 skipped, 73 warnings in 249.42s (0:04:09)
FAILED tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung
FAILED tests/test_promo_seite.py::test_der_leere_screenshot_wird_nicht_ausgeliefert
```

Exakt der im Brief geforderte Massstab (2 failed / ~2777 passed / 14
skipped). Die zwei Roten sind vorbestehend (Promo-Bildpipeline, nicht Teil
dieses Tickets) und unveraendert.

---

## Schritt 2 — Der echte Lokallauf

**Aufbau:** ein Skript (`/tmp/lokal_vodafone_lauf.py`, nicht Teil des
Repos) ruft `geraete_pipeline.run_geraete_stage()` unveraendert auf und
verengt nur die Anbieterliste auf Vodafone (Monkeypatch von
`lade_quellen`), damit kein anderer der 22 Anbieter angefasst oder
gealtert wird. `http_cfg["user_agent"]` ist wortgleich der im Brief
geforderte ehrliche UA:

```
TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)
```

Kein Browser, kein Playwright — reiner `httpx`-GET ueber
`collect.http.fetch()`, wie im Produktivlauf. `api.vodafone.de/robots.txt`
antwortet HTTP 404 (keine robots.txt, also keine Regeln, wie im
Modulkopf von `vodafone.py` dokumentiert) — geprueft vor jedem Abruf durch
`RobotsWaechter`.

**Ablauf, gemessen (427,8s gesamt):**

1. Geraeteliste (`/glados/v2/hardware/v2`): 51 Geraete, HTTP 200.
2. Je Geraet die Detailnutzlast (`/glados/v2/hardware/v2/virtualItem/<id>`),
   2s Abstand: 51 Abrufe, alle HTTP 200. Daraus **149 Listungen** (0 neu —
   unveraendert seit dem letzten produktiven Lauf, deshalb bleibt
   `geraete_preise.jsonl` ohne Diff — ein unveraenderter Preis schreibt
   keine Zeile, das ist die Regel, nicht der Ausfall) und **596
   Buendel-Rohsaetze**.
3. Tarifnamen-Aufloesung (`loese_tarifnamen`, nach dem Sammeln, ein GET je
   eindeutiger `hardwareId`): **339 von 596 Hash-Vorkommen ueber die
   Schnittstelle aufgeloest** (56,9 %).
4. Abgleich gegen `data/state/tarife.jsonl` (10 Vodafone-Basistarife
   XS/S/M/L/XL, je mit/ohne "mit Smartphone"): **253 von 596 Rohsaetzen
   uebernommen** (42,5 %), **343 verworfen**.

```
Vodafone: 339 von 596 Buendel-Tarifnamen ueber die Tarifschnittstelle aufgeloest
Buendel: 343 Saetze ohne aufloesbaren Tarif verworfen - im Tarifbestand
  fehlen 260 Tarife, haeufigste: FamilyCard XL (77x), FamilyCard S (5x),
  FamilyCard M (4x), <Hash> (1x), ...
Tarif-Referenzen: 45 SIM-only-Referenzen aus 56 Tarifen
Buendel: 253 von 596 Rohsaetzen uebernommen (253 neu), 343 verworfen
```

**Vorher / Nachher** (`data/state/geraete_tco.json`):

| | Vorher | Nachher |
|---|---|---|
| Buendel gesamt | 63 (nur o2) | **316** |
| davon Vodafone | **0** | **253** |
| SIM-only-Referenzen | 45 | 45 (unveraendert — dieser Lauf ruehrt `tarife.jsonl` nicht an) |

`data/state/geraete_db.json`: Vodafone-Protokoll `laeufe` 13 -> 14,
`funde_gesamt` 1939 -> 2088 (normale Fortschreibung durch
`protokolliere_lauf`, kein struktureller Eingriff). Kollisionen: 0.
Unbekannte Titel: 21 (iPads, Tablets, GigaCube — ausserhalb des
Smartphone-Katalogs, nicht Teil dieses Auftrags).

### Tarifnamen-Aufloesungsquote im Detail

Die Quote aus R1s Modulkopf ("gut ein Drittel der Hashes loest auf") war
eine Stichprobe ueber 15 Geraete/30 Hashes und ist mit dem vollen Lauf
**ueberholt** — `config/geraete_quellen.yaml` ist entsprechend korrigiert:

- **API-Ebene** (`offerCoreHash` -> Klarname via
  `/glados/v2/tariff/v2/hardware`): 339 / 596 = **56,9 %**.
- **Endgueltige Uebernahme** (Name UND im lokal erfassten Tarifbestand):
  253 / 596 = **42,5 %**.
- Die Differenz (339 − 253 = 86) sind namentlich aufgeloeste, aber nicht
  erfasste Tarife — ganz ueberwiegend **FamilyCard**-Varianten
  (86 von 86: 77× FamilyCard XL, 5× FamilyCard S, 4× FamilyCard M). Das ist
  kein Aufloesungsfehler, sondern eine Bestandsluecke: `tarife.jsonl`
  fuehrt nur die zehn Basis-Endkundentarife XS bis XL, keine
  Familienkarten-Zusatzkarten. Wer die Quote weiter heben will, ergaenzt
  `config/tarif_quellen.yaml` um die FamilyCard-Produktinformationsblaetter
  — nicht den Aufloesungscode.
- Der Rest der 343 Verwerfungen sind Hashes, die die Tarifschnittstelle
  selbst nicht benennt (Kampagnen- oder auslaufende Tarife, wie im
  Modulkopf von `vodafone.py` dokumentiert) — je einzeln unter 1 %.

---

## Schritt 3 — Rechenprobe an drei Stichproben

Alle drei Proben sind **echte, in `geraete_tco.json` persistierte**
Datensaetze aus diesem Lauf, nachgerechnet mit dem Projekt-eigenen
`tco_model.tco_24()` (dieselbe Funktion, die `geraete.html` fuer jede
TCO-Karte aufruft) und zusaetzlich von Hand geprueft. Formel:
**Zuzahlung + Geraeteraten × min(Laufzeit, 24) + Tarif × 24 (+
Anschlusspreis) = Gesamt**.

### Probe 1 — iPhone 15 128 GB, Vodafone Mobil M, 24 Monate

Quelle: `https://www.vodafone.de/privat/handys/iphone-15.html`
(`virtualItemId=51`, `hardwareId=55846`, Komposition-Hash
`6CC1CBC9...A8877`, live gegen die Rohantwort nachgelesen).

| Posten | Wert |
|---|---|
| Zuzahlung | 1,00 € |
| Geraeterate | 29,25 €/Monat × 24 von 24 Monaten = 702,00 € |
| Tarif | 51,95 €/Monat × 24 Monate = 1246,80 € |
| Anschlusspreis | 0,00 € |
| **Gesamt** | **1949,80 €** (monatlich 81,24 €) |

Nachrechnung von Hand: `1,00 + 702,00 + 1246,80 + 0,00 = 1949,80` ✓ —
identisch mit `tco_24()`. **Zusaetzliche Gegenprobe gegen die rohe
API-Antwort** (die Identitaet, die der Adapter selbst zur Aufnahme
prueft): `tarif.month (51,95) + hardware.month (29,25) = 81,20`, und die
Rohantwort nennt fuer genau diese Periode
`totalMonthlyRatePrice.withoutDiscounts[0].gross = 81,2` — **exakt
gleich**.

### Probe 2 — iPhone 15 128 GB, Vodafone Mobil XS, 36 Monate

Selbe Quelle, Komposition-Hash `CDB6D6C9...033045`. Zeigt den Fall
Laufzeit > 24-Monats-Horizont (Restbetrag).

| Posten | Wert |
|---|---|
| Zuzahlung | 1,00 € |
| Geraeterate | 19,50 €/Monat × 24 von 36 Monaten = 468,00 € |
| Tarif | 31,95 €/Monat × 24 Monate = 766,80 € |
| Anschlusspreis | 0,00 € |
| **Gesamt** | **1235,80 €** (monatlich 51,49 €) |
| Restbetrag jenseits 24 Monate | 12 × 19,50 € = 234,00 € |

Von Hand: `1,00 + 468,00 + 766,80 + 0,00 = 1235,80` ✓. Gegenprobe gegen
die Rohantwort: `tarif.month (31,95) + hardware.month (19,50) = 51,45`,
Rohantwort `totalMonthlyRatePrice.withoutDiscounts[0].gross = 51,45`
(Periode Monat 1–24) — **exakt gleich**.

### Probe 3 — iPhone 16 128 GB, Vodafone Mobil S, 12 Monate

| Posten | Wert |
|---|---|
| Zuzahlung | 1,00 € |
| Geraeterate | 69,00 €/Monat × 12 von 12 Monaten = 828,00 € |
| Tarif | 41,95 €/Monat × 24 Monate = 1006,80 € |
| Anschlusspreis | 0,00 € |
| **Gesamt** | **1835,80 €** (monatlich 76,49 €) |

Von Hand: `1,00 + 828,00 + 1006,80 + 0,00 = 1835,80` ✓.

Alle drei Proben decken die drei im Bestand vorkommenden Laufzeiten ab
(12/24/36 Monate) sowie den Restbetrag-Fall; zwei sind zusaetzlich direkt
gegen die rohe API-Antwort verifiziert (nicht nur gegen den bereits
verarbeiteten Datensatz).

---

## Messgrenzen — ehrlich benannt, nicht umgangen

1. **149 Listungen, 0 neu.** Der Geraetebestand selbst hat sich seit dem
   letzten produktiven Lauf nicht veraendert — `geraete_preise.jsonl`
   traegt deshalb keine neue Zeile. Das ist die Regel dieses Projekts
   (ein unveraenderter Preis schreibt keinen Punkt), keine Luecke dieses
   Laufs.
2. **42,5 % Uebernahmequote ist eine Bestandsgrenze, keine Codegrenze.**
   Die groesste Einzelursache (86 von 343 Verwerfungen) sind
   FamilyCard-Tarife, die namentlich aufgeloest werden, aber nicht im
   erfassten Tarifbestand stehen. Wer die Quote heben will, erweitert
   `config/tarif_quellen.yaml`.
3. **`sim_only_referenzen` unveraendert (45).** Dieser Lauf hat bewusst nur
   Vodafone erhoben; der Tarifbestand selbst (`tarife.jsonl`) wird von
   einem anderen Sammler gepflegt und war hier nicht Teil des Auftrags.
4. **Die Regression war eigenstaendig entdeckt, nicht im Brief benannt.**
   Der Brief nannte "2 failed" als Massstab, ohne die Ursache zu kennen;
   diese Session hat den Unterschied zwischen dem tatsaechlichen ersten
   Lauf (3 failed) und dem Massstab aufgeklaert, statt ihn zu ignorieren
   oder den Test anzupassen.
5. **Wie R1 endete:** R1 hatte Code und 20 gruene Tests der neuen
   Testdatei, aber weder die Vollsuite noch den Erhebungsschritt gegen die
   echte API gelaufen — beides holt dieser Bericht nach.

---

## Baumzustand

`git status --short` nach allen drei Commits: sauber. Drei Commits auf
`openclaw/ticket-b1-buendel-vodafone`:

1. `26054b2` — Fix der R1-Regression (9 Zeilen entfernt)
2. `7bacfb9` — Lokallauf-Ergebnis (`geraete_db.json`, `geraete_tco.json`)
3. dieser Commit — Bericht + korrigierte Schaetzung in
   `config/geraete_quellen.yaml`

Kein Push nach `main`, kein Deploy-Hook beruehrt.
