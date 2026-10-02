# P4/D2c — EINE Modell-Menge statt drei: der rote Faden zwischen den Reitern

Auftrag (Strategie P4 Bau-Auftrag 2c + P3-Rest): Radar-Liste und Katalog-Tabelle
auf `modell_schluessel` als EINEN Schlüssel stellen; Sprungkette
Radar → Katalog → Zeitreihe; `?ansicht=`-Deep-Link, wenn < 20 Zeilen. Nicht
committet, nichts unter data/state geschrieben. Alle Zahlen selbst am frisch
gerenderten `site/` gemessen (Messskripte `mess_d2c_kette.py`,
`screenshots_d2c.py` in diesem Ordner).

## Messzahlen: vorher → nachher

| Messgröße (echtes site/, 18.09. nach 6a37ceb) | vorher | nachher |
|---|---|---|
| Katalog-Modellzeilen mit `data-modell` | **0** | **111/111** (== Python-`schluessel`, Gegenprobe im Test) |
| Radar-Modellzeilen (Abweichungsliste) | 97, nur Graph-Sprung | 97, Graph- **und** Katalog-Sprung am selben `z.id` |
| Radar→Katalog-Links / davon ohne Ziel | – / – | **92 / 0** |
| Radar-Zeilen mit benannter Lücke „nicht im Katalog" | 0 (stumm) | **5** (reine Bündel-Modelle ohne Listung) |
| Katalog→Zeitreihe-Links / außerhalb Wahlmenge | – / – | **83 / 0** (alle in `daten.erlaubt`, nicht-leer) |
| Katalog-Modelle ohne Graph-Link | 111 (gar keiner da) | **28**, Grund in der TCO-Spalte benannt (kein Bündel / iPhone-18-Auto < 2 Messtage) |
| Modell-Mengen je Reiter | 88 · 97 · 111 (drei Listen) | **EINE Menge 116** (Vereinigung) + 2 benannte Reste: 5 nur Bündel, 28 nur Katalog |
| Schlüssel-Systeme | 2 (`modell_schluessel` vs. Listungs-/Titelebene im Katalog-Markup) | **1** (`modell_schluessel` als `data-modell` in Katalog, Radar und ZR-Wahl) |

Die „321 Schlüssel" des Auftrags (katalog.md §4) sind die Anbieter-Statuszeilen
der Detailzeilen — am Bestand von heute **372** (169 vergleichbar / 192
kein_buendel / 7 band_mismatch / 4 nicht_vergleichbar). Sie hängen am
Modell-Schlüssel ihrer Gruppe, sind kein drittes Schlüssel-System; die
Modell-Liste selbst trägt 97 Zeilen à einem Schlüssel.

## Die Sprungkette, am gerenderten site/ durchgeklickt (Server 8770, Chromium)

`mess_d2c_kette.py`, Ergebnis „KETTE OK", alles initial ohne Vorwissen:

1. **Radar→Katalog** (Klick „im Katalog →", 1. Zeile Xiaomi 17 512):
   Katalog-Reiter aktiv, Zielzeile sichtbar UND markiert (`.gr-k-ziel`).
1b. **Über aktiven Filter hinweg**: Marke „Google" gesetzt, Sprung auf
   iPhone 16e 128 → Filter vom Handler geleert, Zeile sichtbar.
1c. **Hinter den Deckel**: Sprung auf Zeile 51 von 111
   (samsung-galaxy-z-fold8-256) → „alle anzeigen" ausgelöst, Zeile sichtbar.
2. **Katalog→Zeitreihe** (Klick „im Graph ansehen →" derselben Zeile):
   Vergleichs-Reiter aktiv, URL `modell=apple-iphone-16e-128` (deep-link ==
   Versprechen), Suchfeld zeigt „Apple iPhone 16e 128 GB".
3. **`?ansicht=tco`**: beim Laden Tabelle `gr-katalog--tco` + Knopf
   `aria-pressed=true`; barpreis-Klick **löscht** den Parameter (Grundfrage
   bleibt die kurze URL); nach Modellwechsel steht
   `…?modell=…&band=klein&ansicht=tco` — **erhalten**.
4. 92 Katalog-Links, 0 ohne Zielzeile; 5 × „nicht im Katalog".

`?ansicht=` ist gebaut (**~16 Zeilen Kern**, unter der 20er-Grenze des
Auftrags): Lesen beim Laden + `urlAnsicht()` im Umschalter-Block. Dazu
mussten die **zwei** `replaceState`-Stellen des Zeitreihen-Blocks
(`waehle()` + Start) auf parameterweises Schreiben umgestellt werden — bis
P4 baute `waehle()` die URL komplett neu auf und löschte dabei jeden
Nachbar-Parameter (gemessen: ansicht weg nach erstem Band-Klick). Der
P3-Kommentar „bewusst kein URL-Parameter" ist mit dem Auftrag gedreht und
dokumentiert die Begründung.

## Was wo gebaut wurde

| Datei | Änderung |
|---|---|
| `report/geraete_view.py` | `katalog_modellzeilen(…, zr_erlaubt=None)`: Feld `zr` je Modellzeile — gelesen aus `geraete_zeitreihe.aufbereiten()["daten"]["erlaubt"]` (nicht-leer gefiltert), NICHT nachgerechnet; in `aufbereiten()` übergeben. Fail-closed: ohne Parameter `zr=False` (kein blinder Link). |
| `templates/_geraete_radar.html.j2` | `radar_tafel` setzt `katalog_ids` aus `geraete.katalog_modelle` (with-context, reine Montage); `modellzeile(…, katalog_ids=())`: Katalog-Link `gr-ksprung` (eigene Klasse! `gr-sprung` würde vom ZR-Delegaten gefangen) unter dem Modellnamen, sonst `<span>„nicht im Katalog"` |
| `templates/geraete.html.j2` | Katalog-Hauptzeile trägt `data-modell="{{ m.schluessel }}"`; unter dem Titel `gr-sprung`-Link „im Graph ansehen →" (bestehender Delegat tut die Arbeit, Deep-Link mit `m.tco_band`) — nur `{% if m.zr %}` |
| `templates/app.js` | (a) neuer IIFE: Klick-Delegat `a.gr-ksprung` — Reiter schalten, Filter leeren, Deckel (`#gr-kmehr`) öffnen, `.gr-k-ziel` markieren, scrollen; ohne Zielzeile Fallback über href `#katalog` (Hash-Map schaltet den Reiter auch nach Reload). (b) `?ansicht=` im Umschalter. (c) ZR-`replaceState` parameterweise (2 Stellen). |
| `templates/style.css` | `.gr-ksprung` teilt den `.gr-sprung`-Stil; Links je eigene Zeile unter Titel/Zelle (`.gr-a-modell`/`.gr-a-klein` sind bereits block); `.gr-k-ziel` = rote 2-px-Rahmenlinie oben+unten (Rot-Akzent-Regel: genau EINE markierte Zeile) |

## Tests

- **Neu `tests/test_geraete_faden_schluessel.py` (8 passed)**: Schlüssel im
  Markup == gerechneter `modell_schluessel` (Vollständigkeits-Gegenprobe,
  CLAUDE.md-Lookup-Falle); gemeinsamer Schlüsselraum Radar∩Katalog (Schnitt
  belegt UND Differenzfall belegt); jeder Radar-Katalog-Sprung trifft;
  Link+Lücke == Zeilenzahl (kein stummer dritter Zustand); reines
  Bündel-Modell (Fixture `graphloses_modell`) heißt „nicht im Katalog";
  Katalog-Graph-Sprung ⊆ Wahlmenge; Pixel 11 (Listung ohne Bündel) ohne
  Graph-Link; `zr` fail-closed + nur für die übergebene Menge (Unit).
- **Browser `tests/test_geraete_radar_sprung_browser.py` (+3, 6 passed)**:
  Katalog-Sprung legt Filter frei und markiert die Zeile (Fixture-Marke
  Samsung, Sprung auf Apple); Katalog-Graph-Sprung wählt das Modell;
  `?ansicht=` beim Laden / barpreis löscht / Bandwechsel erhält.
- **Suite `-k geraete`: 1456 passed / 3 failed / 6 skipped** — die 3 sind
  exakt die benannten Vorher-Roten (Galaxy-Tab-S11-Ultra-Auto,
  Nachtlauf-Nullzeilen, iPhone-18-Querlinks). Am iPhone-18-Rot verändert:
  nichts — er prüft `gr-sprung[href^='?modell=']` gegen `erlaubt`, meine
  Katalog-Links sind eine andere Klasse mit anderem href; seine Ursache
  (Auto-Modelle unter 2 Bündel-Messtagen) ist P5 Auftrag 1.
- **`pruefe_portal.py`: 20 bestanden / 1 durchgefallen** — Kriterium 13
  (Vergleich 18 048 Z > 6000) ist der von D3 dokumentierte vorbestehende
  Hebel (20 Tarif-Rechenweg-Aufklapper, Lead/P5-Entscheidung). Radar 2743 Z
  und Katalog 230 Z unverändert grün (meine Links/Lücken sind keine `<p>`).
  11b Reiterhöhen: tco 2845 / radar 2400 / verlauf 1943 / **katalog 1871**
  — alle < 3000 BESTANDEN (der Link kostet keine sichtbare Höhe: die
  Modell-Zeilen stehen hinter dem Deckel von 12).
- **Screenshots** `screenshots/d2c-{radar-links,katalog-link}-{1440,390}.png`,
  angesehen (Vision-Gegenlesen): je Radar-Zeile „im Katalog →" unterm
  Modellnamen UND „im Graph ansehen →" in der Graph-Spalte; im Katalog der
  Graph-Link unterm Titel, lesbar, kein Overlap; 390 kein Querscroll
  („im Katalog →" bricht zweizeilig, lesbar).
- Volle Suite als Sicherheitsnetz gelaufen (app.js berührt auch
  Such-/Falz-Seiten): Ergebnis steht unten im Anhang dieser Notiz.

## Bewusst offen / Rest (Lead-Entscheidungen)

1. **Die 28 Katalog-Modelle ohne Graph-Link** bleiben ohne Link — darunter
   ALLE iPhone-18-Auto-Modelle (Listung ab Tag 1, Zeitreihe erst ab 2
   Bündel-Messtagen). Genau das ist P5 Auftrag 1 (Sichtbarkeit Bündel ODER
   Listung); mein `zr`-Feld greift dann automatisch, keine zweite Stelle.
2. **Die 5 „nicht im Katalog"-Modelle** verschwinden von selbst, sobald ihre
   Listungen kommen — bis dahin ist die Lücke benannt, kein toter Link.
3. **`.gr-k-ziel` bleibt markiert** bis zum nächsten Sprung (kein
   Auto-Entfernen nach Zeit) — bewusst simpel, ein Timeout wäre eine zweite
   Mechanik für denselben Effekt.
4. Der Radar→Katalog-Sprung leert AKTIVE Filter komplett (nicht nur für die
   eine Zeile) — bewusst: der Filterzustand muss wieder sichtbar zur
   Tabelle passen (Filterleisten-Regel), sonst stünde „gefiltert" da ohne
   dass der Leser es der Tabelle ansieht.

## Anhang: volle Suite

**3253 passed / 3 failed / 12 skipped** (448 s). Die 3 Failed sind exakt die
benannten vorbestehenden Roten (Galaxy-Tab-S11-Ultra-Auto,
Nachtlauf-Nullzeilen, iPhone-18-Querlinks) — gegen 2a-Messung (3226 passed)
ist die Differenz meine neuen 8 + 3 Tests. app.js-Kontaktpunkte außerhalb
der Geräteseite (Suche, Falz, Startseite) alle grün.
