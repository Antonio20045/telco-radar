# BRIEF F-4a Runde 2 (05.09.2026, abends) — die Antwortzeile widerspricht sich nicht mehr

Auftragsgrundlage: `BRIEF_F4A_ANTWORTZEILE_R2.md`. Bezug: Runde 1
(`b602e5d`, `outputs/phase-f4a-antwortzeile-2026-09-05.md`) — Layout und
Erklärzeile der Antwortzeile bleiben unangetastet, diese Runde ist ein
reiner Datenschicht-Fix.

## Befund

„Günstigster Gerätepreis" behauptet das Minimum im Modellblock — und stimmte
gemessen nicht. Am echten Bestand (`data/state/geraete_preise.jsonl`) zeigte
„Apple iPhone 17 Pro 256 GB" die Antwortzeile **1.199,90 € (Vodafone)**,
während dieselbe Modelltafel eine Saturn-Händlerkarte mit **1.179,00 €**
trug — 20,90 € weniger, sichtbar in derselben Ansicht, ohne Klick.

## Ursache

Zwei getrennte Rechnungen für dieselbe Frage:

- `geraete_tco_karten.modelle()` bildete `antwort["geraetepreis"]` nur über
  `karten` — Anbieter mit einem echten Tarifbündel (Telekom, 1&1, o2,
  Vodafone plus dessen Näherungskarte). Amazon, Expert und Saturn führen nie
  ein Bündel und hatten deshalb nie eine Karte in dieser Menge.
- `geraete_tco_view.aufbereiten()` berechnete **separat**
  `modell["haendler_ohne_buendel"]` (die Saturn/Amazon/Expert-Preise für die
  Händlerkarte) — lief nach `modelle()`, sah aber `antwort` nie wieder an.

Reines Datenproblem: `templates/geraete.html.j2` gibt nur aus, was
`m.antwort` liefert, und wurde für diese Runde nicht angefasst.

## Umgesetzt

**Eine Rechnung statt zwei**, in `geraete_tco_karten.py`:

- `HAENDLER_OHNE_BUENDEL` (die drei Händler) und die Preisermittlung
  `_haendler_geraetepreise()` sind von `geraete_tco_view.py` nach
  `geraete_tco_karten.py` gezogen — dorthin, wo `antwort` entsteht.
  `geraete_tco_view.py` referenziert beide jetzt nur noch
  (`HAENDLER_OHNE_BUENDEL = geraete_tco_karten.HAENDLER_OHNE_BUENDEL`,
  `_haendler_ohne_buendel_preise = geraete_tco_karten._haendler_geraetepreise`)
  statt eine zweite Kopie zu führen — genau die Kopie war die Lücke.
- `modelle()` gruppiert `listungen` zusätzlich **je Modell**
  (`listungen_je_modell`, über `modell_schluessel(device_id, speicher_gb)`),
  nicht nur je Bündel-SKU — sonst wäre ein Händler ohne Bündel für diese
  Gruppierung unsichtbar geblieben, obwohl er auf derselben Tafel als
  Händlerkarte steht.
- Beim Bilden von `geraetepreise` (der Kandidatenliste fürs Minimum) werden
  die Händlerpreise dieses Modells als zusätzliche Kandidaten angehängt,
  bevor `min(...)` läuft. Reines Minimum, kein Vorzugsrecht — führt der
  Bündel-Anbieter, bleibt er stehen.
- **`tarif_gesamt`/`tarif_anbieter` unverändert.** Die Kandidatenmenge dafür
  bleibt `tarifangebote` (echte Bündel, keine Näherung) — Händler ohne
  Tarifbündel haben per Definition kein Tarifangebot und werden dort nicht
  einsortiert.
- Generisch: die Ergänzung hängt an keinem Modellnamen, sie greift für jedes
  Modell mit Einträgen in `listungen_je_modell`, auch für künftige
  Händler/Modelle in `HAENDLER_OHNE_BUENDEL`.

## Vorher/Nachher: Apple iPhone 17 Pro 256 GB

| | Vorher | Nachher |
|---|---|---|
| Antwortzeile „Günstigster Gerätepreis" | `1.199,90 € (Vodafone)` | `1.179,00 € (Saturn)` |
| Vodafone-Näherungskarte im selben Block | 1.199,90 € (führte die Antwort) | 1.199,90 € (bleibt gültige Kandidatin, führt nicht mehr) |
| „günstig mit Tarif" | unverändert: 1.619,64 € (1&1) | unverändert: 1.619,64 € (1&1) |

Am echten Bestand reproduziert (`karten.modelle(...)` gegen
`data/state/geraete_tco.json`, `geraete_db.json`, `tarife.jsonl`):

```
modell = _modell(bestand, "apple-iphone-17-pro-256")
antwort = modell["antwort"]
antwort["geraetepreis"]           == 1179.0
antwort["geraetepreis_anbieter"]  == "Saturn"
antwort["tarif_gesamt"]           == 1619.64
antwort["tarif_anbieter"]         == "1&1"
```

**Sechs weitere Modellblöcke ändern sich auf dieselbe Weise** (Saturn
unterbietet Vodafones Näherungskarte durchgängig, kein Einzelfall):

| Modell | Vorher | Nachher |
|---|---|---|
| Apple iPhone 16 128 GB | 849,90 € (Vodafone) | 839,99 € (Saturn) |
| Apple iPhone 16 Plus 128 GB | 949,90 € (Vodafone) | 939,99 € (Saturn) |
| Apple iPhone 16e 128 GB | 599,90 € (Vodafone) | 589,00 € (Saturn) |
| Apple iPhone 17 256 GB | 949,90 € (Vodafone) | 939,99 € (Saturn) |
| Apple iPhone 17e 256 GB | 699,90 € (Vodafone) | 699,00 € (Saturn) |
| Apple iPhone Air 256 GB | 949,90 € (Vodafone) | 909,00 € (Saturn) |

Alle anderen Modellblöcke (ohne Saturn-Unterbietung, z. B. Fairphone 6
256 GB) ändern sich nicht — belegt durch die Gegenprobe unten.

## Tests

`tests/test_geraete_tco_hauptansicht.py`, gegen den echten Bestand
(`data/state/geraete_tco.json`, `geraete_db.json`, `tarife.jsonl` in diesem
Worktree, keine Fixture):

- `test_antwortzeile_nennt_je_metrik_die_guenstigste_zahl_mit_anbieter` —
  die ALTE Zusicherung (`1.199,90 €`/„Vodafone") ist auf den korrigierten
  Wert (`1.179,0`/„Saturn") umgestellt, dazu die Gegenprobe, dass Vodafones
  Näherungskarte weiterhin `geraetepreis == 1199.90` trägt (sie bleibt eine
  gültige, nur nicht mehr führende Kandidatin) und ihr `naeherung`-Flag
  unverändert `True` ist.
- `test_antwortzeile_bezieht_haendler_ohne_buendel_ins_minimum_ein` (neu,
  generisch) — über ALLE Modelle: das Antwortzeilen-Minimum ist `<=` jedem
  erhobenen Amazon/Expert/Saturn-Gerätepreis desselben Modellblocks, mit
  Gegenprobe, dass die Schleife wirklich mindestens einen Händlerpreis
  geprüft hat (`geprueft > 0`) — sonst bewiese ein leerer Testlauf nichts.
- `test_antwortzeile_bleibt_unveraendert_ohne_haendlerpreise` (neu,
  Gegenprobe) — Fairphone 6 256 GB führt im Bestand keinen der drei
  Händler; die Antwortzeile bleibt exakt die günstigste Kartenauswahl wie
  vor der Erweiterung. Ohne diese Gegenprobe wäre nicht belegt, dass die
  Änderung gezielt ist statt ein globaler Eingriff.
- `test_der_geraetepreis_fuehrt_wo_er_ausgewiesen_ist`,
  `test_antwortzeile_der_tarifgewinner_ist_kein_naeherungsangebot` und die
  übrigen bestehenden Antwortzeilen-/Karten-Tests sind unverändert grün —
  R1s Zusicherungen zu Layout, Erklärzeile und „günstig mit Tarif" sind von
  dieser Änderung nicht berührt.

Zusätzlich, generisch über den ganzen Bestand geprüft (Abnahmekriterium 3):
in jedem Modellblock mit mindestens einem sichtbaren Gerätepreis ist
`antwort.geraetepreis` kleiner-gleich jedem einzeln sichtbaren
Gerätepreis in diesem Block, Bündelkarte wie Händlerkarte — das ist exakt
die Aussage von `test_antwortzeile_bezieht_haendler_ohne_buendel_ins_minimum_ein`.

## Suite

Fresh gemessen in diesem Worktree nach allen Änderungen dieser Runde:

```
2 failed, 2749 passed, 14 skipped, 73 warnings in 251.68s
FAILED tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung
FAILED tests/test_promo_seite.py::test_der_leere_screenshot_wird_nicht_ausgeliefert
```

Beide Rote sind die vorbestehenden, im Brief benannten Ausnahmen
(Promo-Screenshot-Prüfung) — unverändert gegenüber dem R1-Stand, nichts
Neues rot. Gegenüber der R1-Baseline (2 failed / 2747 passed / 14 skipped)
sind es netto **+2 passed**: eine bestehende Zusicherung korrigiert (kein
Zähler-Effekt), zwei neue Tests hinzugekommen.

## Site

`render_site(site, reports, load_config(root))` neu ausgeführt. Ergebnis:
**7 Modellblöcke** in `site/geraete.html` geändert (siehe Tabelle oben),
`site/style.css` **unverändert** (kein Layout-Eingriff, wie im Auftrag
verlangt). `site/data/keyword-index.json` trägt nur die tagesaktuelle
`stand`-Datumszeitbombe und ist auf den committeten Stand zurückgesetzt
(`git checkout -- site/data/keyword-index.json`).

## Commits auf `openclaw/ticket-f4a-antwortzeile`

1. `eb83713` — Datenfix in `geraete_tco_karten.py`/`geraete_tco_view.py`,
   Testkorrektur + zwei neue generische Tests in
   `tests/test_geraete_tco_hauptansicht.py`.
2. `8009d07` — `site/geraete.html` neu gerendert (7 Modellblöcke),
   `keyword-index.json` unangetastet gelassen (bereits auf committetem
   Stand).

Kein `main`, kein Deploy — nur der bestehende Branch weiter gepusht.

## Abnahme

| # | Kriterium | Status |
|---|---|---|
| 1 | `antwort.geraetepreis`/`geraetepreis_anbieter` beziehen Händlerpreise mit ein, `tarif_gesamt`/`tarif_anbieter` unverändert bündelbasiert | erfüllt |
| 2 | Apple iPhone 17 Pro 256 GB: `1.179,00 €` / „Saturn", am echten Bestand | erfüllt |
| 3 | Generische Regel testbelegt (Minimum ≤ jedem sichtbaren Gerätepreis) | erfüllt |
| 4 | R1s Dominanz-Layout und Erklärzeile unangetastet, bestehende R1-Tests grün (außer der einen bewusst korrigierten Zahl) | erfüllt |
| 5 | Suite ohne neue Rote außer den zwei vorbestehenden | erfüllt (2 failed / 2749 passed / 14 skipped) |
| 6 | Site-Artefakt committet, `keyword-index.json` zurückgesetzt, Bericht vorhanden | erfüllt |

Nichts offen aus dieser Runde.
