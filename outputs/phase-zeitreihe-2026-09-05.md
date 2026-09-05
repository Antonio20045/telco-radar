# Phase Zeitreihe — der Hauptgraph der Geräteseite wird eine Zeitreihe (05.09.2026)

Auftragsgrundlage: `BRIEF_ZEITREIHE.md` (Variante A, von Antonio gebilligt),
Pflichtlektüre `CLAUDE.md` §8a/8b, `entwurf_geraete_v2.html` (Stil-Referenz) und
`data/state/geraete_preise.jsonl`. Branch `openclaw/ticket-zeitreihe`, Worktree.
Zwei Commits, jeder Schritt einzeln:

| Commit | Schritt |
|---|---|
| `cb362be` | G0: der Zeitreihen-Block selbst — Datenaufbereitung, SVG-Geometrie, Einbindung in die Hauptansicht |
| `0041e81` | Tests für die vier Abnahmekriterien + Anpassung des vorbestehenden Browser-Tests auf zwei Pflichtgrafiken |

## Ergebnis in einem Satz

Jedes gewählte Gerät zeigt jetzt zuerst eine servergerenderte Zeitreihe
(„G0") — eine Linie je Anbieter, Gerätepreis über die Zeit, mit ehrlicher
Lücke statt einer erfundenen Verbindung —, und die bestehenden Balkenblöcke
(Karten + G1) stehen unverändert darunter. Suite: **2 failed / 2689 passed /
14 skipped** (Maßstab: 2 failed / ~2669 passed / 14 skipped — die zwei
Promo-Screenshot-Tests, vorbestehend, hier unverändert reproduziert; die
Differenz von +20 zum Maßstab sind die neuen Tests dieser Phase).

---

## Was gebaut wurde

| Baustein | Wo | Die eine Regel, die ihn trägt |
|---|---|---|
| `geraete_verlauf.reihen_fuer_listungen()` | `report/geraete_verlauf.py` | Neue, ÖFFENTLICHE Funktion — dieselbe Filterung wie `geraete_mit_verlauf` (nur Neugeräte mit Barpreis), aber ohne die Gruppierung nach (device_id, speicher): der Aufrufer übergibt schon eine auf EIN Gerät eingegrenzte Menge. Reiter 3 und der neue Zeitreihen-Block teilen sich damit `_punkte`/`_reihen` (Farbe, Vodafone-Vorrang, `MAX_LINIEN`), statt die Logik zweimal zu pflegen |
| `geraete_tco_grafik.zeitreihe()` (G0) | `report/geraete_tco_grafik.py` | Reine Geometrie, wie G1/G2: nimmt fertige Reihen entgegen, rechnet keinen Euro. Zwei Regeln tragen die Zeichnung: **(1)** eine Linie nur ab zwei Messpunkten, ein einzelner Punkt bleibt ein Punkt (`gr-g0-punkt--einzeln`); **(2)** eine Linie wird an jeder Lücke > `G0_LUECKE_TAGE` (7 Tage) in eigene Läufe zerlegt — „Linien enden und beginnen neu" statt einer interpolierten Verbindung. Der Schwellenwert ist dokumentiert begründet: die Sammlung läuft täglich, ein bestätigter Preis, der 2–5 Tage keine neue Zeile schreibt, ist normale Kadenz; eine Woche ganz ohne Bestätigung ist ein Ausfall der Sammlung |
| Chart-Chrome-Satz | ebd., Feld `chrome` | EIN fertiger String aus Python, nicht aus Datumsfiltern im Template — „Sammlung läuft · `N` Messtage · seit `DATUM`" (`N`/`DATUM` aus dem echten Tages-Set dieses Geräts). Kein zweiter Ort kann dadurch einen abweichenden Wortlaut erzeugen |
| Einbindung | `report/geraete_tco_view.py` | `aufbereiten()` gruppiert `eintraege` einmalig nach `modell_schluessel` (nicht je Modell neu über die ganze Liste), ruft `reihen_fuer_listungen()` + `zeitreihe()` und hängt das Ergebnis als `modell["zeitreihe"]` an — neben `modell["svg"]` (G1), nicht anstelle |
| Vorlage | `report/templates/geraete.html.j2` | Der Block steht direkt nach der Modell-Überschrift, VOR der Karten-/G1-Sektion (Kriterium 4: „darunter erhalten"). Ohne Daten ein einzelner Satz statt eines leeren Diagramms. Die Belege (Anbieter, Punkte, Zeitraum je Linie) stehen hinter einem eigenen `<details><summary>Wie gerechnet?</summary>` — dieselbe Bezeichnung wie in der gebilligten Skizze, aber ein eigener Aufklapper, weil der bestehende „Rechenweg" je Karte eine andere Sache belegt (die TCO-Rechnung, nicht die Zeitreihe) |
| CSS | `report/templates/style.css` | `.gr-g0*`-Klassen im Stil von G2 (Raster, Achse, Linie, Punkt, Legende); zusätzlich `.gr-g0-punkt--einzeln` (größerer Punkt, Rand in Papierfarbe) und `.gr-g0-luecke` (ruhiges, 5-%-Feld für die Sammellücke). `.gr-g0` in den bestehenden „kein Text unter 12 px auf dem Telefon rollen, nicht stauchen"-Regeln ergänzt |

## Die vier Abnahmekriterien, mit Beleg

**1. Zeitreihe als Hauptgraph.** `tests/test_geraete_zeitreihe.py`:
`test_ein_anbieter_mit_zwei_punkten_bekommt_eine_linie`,
`test_gemischte_reihen_zeigen_linie_und_punkt_nebeneinander` — ein Anbieter
mit genau einem Punkt bekommt nie ein `<path>`. Am echten Bestand (05.09.2026,
Modell `apple-iphone-17-pro-256`) gegengeprüft: 5 Anbieter (Vodafone, o2,
congstar, mobilcom-debitel, Telekom), 1&1 fällt korrekt heraus (kein
`preis_ohne_vertrag`, nur ein Bündelmonatspreis). `test_es_werden_nur_die_
gegebenen_preise_gezeichnet` hält fest, dass ein Pfad aus genau zwei
Koordinatenbefehlen (M/L) je zwei Punkten besteht — keine erfundene
Zwischenkoordinate.

**2. Ehrliche Achse.** X-Achse ist tagesgenau proportional zur echten
Kalenderzeit (`von`/`bis` = erster/letzter Messtag DIESES Geräts, dieselbe
Rechnung wie G2). Die 19-Tage-Lücke bleibt sichtbare Lücke auf zwei Wegen:
(a) keine Linie überspringt sie (`test_die_19_tage_luecke_wird_nicht_
ueberbrueckt`, `test_drei_punkte_mit_luecke_ergeben_zwei_getrennte_laeufe`),
(b) ein schwaches Schattenfeld markiert sie zusätzlich
(`test_die_luecke_bekommt_ein_sichtbares_feld`,
`test_keine_luecke_ohne_grossen_abstand`). Y-Achse: fünf Marken zwischen
echtem Minimum und Maximum plus 12 % Polster, gerundet — `test_die_achse_
traegt_den_echten_minimal_und_maximalpreis` hält fest, dass die Marken NICHT
auf einer Konstante landen, `test_zwei_verschiedene_geraete_ergeben_zwei_
verschiedene_achsen` beweist, dass es eine Rechnung und keine feste Tafel
ist. Am echten Bestand gegengeprüft (siehe unten): Marken 964/1057/1150/
1243/1336 € bei Eingabe 1000–1300 €.

**3. Ein Chart-Chrome-Satz.** `test_die_chrome_zeile_nennt_messtage_und_das_
erste_datum`, `test_die_chrome_zeile_beugt_bei_einem_messtag_richtig`
(„1 Messtag" statt „1 Messtage"), `test_die_chrome_zeile_ist_der_einzige_
satz_im_belegtext` (die Beleg-Zeilen tragen nur Anbieter/Punkte/Zeitraum,
kein Methodentext). Am echten Bestand: der Chrome-Satz der ersten acht
Modelle reicht von „seit 10.08.2026" (Geräte mit der frühen
mobilcom-debitel-Messung) bis „seit 29.08.2026" (Geräte ohne sie) — letzteres
ist wortgleich das Beispiel aus dem Auftrag, ohne dass ein Datum irgendwo
hartkodiert wurde.

**4. Die Balkenblöcke bleiben.** Kein Zeichen an `geraete_tco_karten.py`
(Karten), `geraete_tco_grafik.balken()` (G1) oder deren Vorlagen-Makro
`tcokarte()` geändert — nur ergänzt, davor eingefügt. Der vorbestehende
Browser-Test dafür (`test_die_startansicht_traegt_genau_die_pflichtgrafik`)
verlangte bislang GENAU eine sichtbare `<svg>` im Reiter; er ist umbenannt
und auf ZWEI umgestellt (`test_die_startansicht_traegt_genau_die_
pflichtgrafiken`, prüft explizit `svg.gr-g0` UND `svg.gr-g1`) — die einzige
Änderung an einem bestehenden Test in dieser Phase, mit Begründung im Test
selbst.

## Tests

20 neue Tests in `tests/test_geraete_zeitreihe.py` (Filterung vor der
Grafik, alle vier Abnahmekriterien einzeln, Chart-Chrome-Zeile, keine
erfundenen Zwischenpunkte), 1 bestehender Browser-Test angepasst (siehe
oben). Volle Suite, blockierend im Vordergrund:

```
2 failed, 2689 passed, 14 skipped, 73 warnings in 244.72s
```

Die zwei Fehlschläge (`tests/test_promo_seite.py::test_die_echten_
screenshots_bestehen_die_pruefung`,
`::test_der_leere_screenshot_wird_nicht_ausgeliefert`) sind der im Auftrag
benannte Maßstab — vorbestehend, unberührt, nicht Teil dieser Phase.

## Gegen den echten Bestand angesehen (nicht nur Fixtures)

`render_site()` einmal über `data/state`/`data/reports` laufen lassen (kein
neuer Lauf, nur Rendern des vorhandenen Standes) und das Ergebnis
ausgewertet:

- **56 von 56 gerenderten Modell-Blöcken** zeigen einen Zeitreihen-Block mit
  Daten (`gr-g0-chrome` 56-mal), 40 davon zusätzlich G1 (Modelle mit nur
  einem belastbaren Bündel bekommen kein G1 — C.1 —, aber immer noch die
  Zeitreihe, wenn ein Barpreis vorliegt).
- Modell `apple-iphone-17-pro-256` (die Leitfrage aus dem Lastenheft): 5
  Anbieter, Chrome-Satz „Sammlung läuft · 4 Messtage · seit 10.08.2026",
  mobilcom-debitels zwei Punkte (10.08./05.09.) sauber als zwei einzelne
  Punkte gezeichnet (0 `<path>`-Elemente für diesen Anbieter), genau EIN
  Lücken-Feld im Bild (zwischen 10.08. und 29.08. — die einzige Lücke > 7
  Tage im Tages-Set dieses Geräts).
- Kein `preis_ohne_vertrag` bei 1&1 (Bündel-only) → korrekt keine Zeile in
  der Zeitreihe, obwohl 1&1 in den Karten darunter mit seinem
  Bündelmonatspreis steht.

## Seitenhöhe (Kriterium „unter drei Bildschirmen", `pruefe_portal.py`
Kriterium 11b / `tests/test_geraete_reiter_browser.py::test_jeder_reiter_
bleibt_unter_drei_bildschirmen`)

Der vorbestehende Browser-Test lief unverändert GRÜN mit dem neuen Block
(kein Anfassen von `MAX_HOEHE = 3000` nötig). Ad-hoc nachgemessen (Grenze
testweise auf 1 px gesenkt, um die reale Zahl zu sehen, danach
zurückgesetzt — kein Diff im Repo): **2354 px** für `tafel-tco` gegen die
Fixture dieses Tests (5 Anbieterlinien, 4 Karten, G1). Die reale Seite hatte
laut Handover nach R3 **2241 px**; mit dem neuen Block (SVG 300 px +
Bildunterschrift + ein zugeklappter Aufklapper, zusammen rund 350–400 px)
liegt sie rechnerisch bei rund 2600–2650 px — unter dem Budget, aber mit
weniger Luft als vorher. **Nicht mit echtem Chromium gegen die volle
Live-Seite gemessen** (das hätte `scripts/pruefe_portal.py` gebraucht,
außerhalb des Zeitbudgets dieser Phase) — siehe „Offen" unten.

## Bewusste Entscheidungen, die der Auftrag offenließ

- **`G0_LUECKE_TAGE = 7`.** Der Auftrag nennt nur „die 19-Tage-Lücke"; sieben
  Tage trennen sie sauber von den kurzen Abständen der laufenden Sammlung
  (2–5 Tage zwischen Bestätigungspunkten, gemessen am echten Bestand) und
  ist im Modul begründet dokumentiert. Jede Schwelle zwischen 6 und 18 Tagen
  hätte am heutigen Bestand dasselbe Ergebnis produziert.
- **Lückenerkennung PRO LINIE, nicht geräteweit.** Eine Linie bricht an
  ihrem EIGENEN Abstand zwischen zwei Punkten — unabhängig davon, ob ein
  anderer Anbieter in der Zwischenzeit gemessen wurde. Das schattierte Feld
  im Bild ist dagegen geräteweit (Vereinigung aller Anbieter), damit die
  Lücke auch dann sichtbar ist, wenn zufällig kein Anbieter direkt daneben
  liegt.
- **„Seit" ist der ECHTE erste Messtag dieses Geräts**, nicht ein fester
  Kalendertag. Das Beispiel im Auftrag („seit 29.08.2026") reproduziert für
  Geräte ohne die frühe mobilcom-debitel-Messung exakt; Geräte mit ihr zeigen
  „seit 10.08.2026" — beides ist derselbe Satz mit einer echten, gerechneten
  Zahl statt eines Textbausteins.
- **Ein eigener Aufklapper „Wie gerechnet?"** statt einer Erweiterung des
  bestehenden Rechenwegs je Karte — die zwei belegen unterschiedliche Dinge
  (TCO-Zusammensetzung vs. Zeitreihen-Herkunft) und stehen an
  unterschiedlichen Stellen der Seite (je Karte vs. je Modell).

## Offen

1. **Keine Chromium-Messung der REALEN Live-Seite**, nur der Fixture aus
   `test_geraete_reiter_browser.py` (2354 px, deutlich unter 3000) und eine
   Überschlagsrechnung für den echten Bestand (siehe oben). Vor dem nächsten
   Deploy `scripts/pruefe_portal.py` Kriterium 11b gegen den frisch
   gerenderten `site/`-Stand laufen lassen und die Zahl hier nachtragen.
2. **Kein zweiter, echter Nachtlauf abgewartet** — alle Messungen sind gegen
   den Stand vom 05.09.2026 (606 Zeilen, 9 Messtage) gerechnet. Ob die
   7-Tage-Schwelle bei dichterer täglicher Bestätigung weiterhin sauber
   zwischen Kadenz und Ausfall trennt, zeigt sich erst über mehr Wochen.
3. **A5.5/E-2, CI/E-3, llm.py** wie im Auftrag verlangt nicht angefasst.
4. Nicht Teil dieser Phase: die zwei vorbestehenden Promo-Screenshot-Tests
   (siehe Maßstab).
