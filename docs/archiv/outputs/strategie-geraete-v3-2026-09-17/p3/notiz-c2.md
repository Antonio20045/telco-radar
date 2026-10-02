# P3/C2 — Vorlage + Umschalter des Gerätekatalogs (17.09.2026)

Auftrag: P3 Bau-Auftrag 2+3 (Strategie Geraete v3) auf C1s Datenquelle
(`katalog_modelle`). Nur Vorlage/app.js/style.css angefasst — NICHT
committet, nichts unter data/state geschrieben.

## Geänderte Dateien

| Datei | Was |
|---|---|
| `src/telco_radar/report/templates/geraete.html.j2` | Reiter „Gerätekatalog" komplett auf MODELL-Ebene: EINE Tabelle (`gr-katalog-mod`), EIN Umschalter `gr-kansicht` (Einzelgerätpreis / Gesamtkosten (TCO-24), Bauform `gr-vknopf` wie Zeitraum-/Band-Schalter), Filter Marke/Speicher/Suche, Zeilen-Aufklapper mit Listungs-Details (C1-`zeilen`, `data-auf`-Mechanik wie Radar-Modellliste) |
| `src/telco_radar/report/templates/app.js` | NEU Umschalter-Block (Klasse `gr-katalog--tco` an der Tabelle, kein Reload, kein Rechnen, kein URL-Parameter, Default Barpreis). PLUS Sortier-Fix: NaN (leerer `data-s-*`) fällt jetzt in BEIDEN Richtungen ans Ende statt aufsteigend nach oben |
| `src/telco_radar/report/templates/style.css` | Spalten-Umschaltung (`.gr-sp--barpreis`/`.gr-sp--tco`), `gr-kansicht`, `gr-k-ab` (nowrap), `gr-k-anzahl`, `gr-k-band`, `gr-k-listungen` (13 px), `cursor:pointer` auf Modellzeilen; mobil unverändert Rollbehälter `.gr-alarm-scroll` + `.gr-alarm{min-width:700px}` |
| `outputs/.../p3/mess_c2_browser.py` + `screenshots/` | Abnahme-Skript + 6 Screenshots (1440/390 × barpreis/tco/tco-auf) |

## Messzahlen (echter Bestand, lokal gerendert, Chromium)

- **Umschalter-Anzahl im Reiter: 1** (2 Knöpfe, Default Einzelgerätpreis,
  `aria-pressed` toggelt, Umschalten ohne Reload nachgewiesen).
- **0× „ohne Preis"** im gerenderten Reiter (vorher 36×); 111 Modellzeilen
  (statt 566 Listungszeilen) + 111 Aufklappzeilen; 1× „nur im Bündel",
  19× „kein Bündel gemessen" (benannte Leerzustände, C1).
- **Preis sichtbar in BEIDEN Ansichten**, Stichprobe 5 Modelle:
  iPhone 17 Pro 256 (ab 1.179,00 € Saturn / TCO ab 1.093,00 € congstar) ·
  Fairphone 6 256 (539,00 € ALDI TALK / 772,75 € o2) · Pixel 11 256
  (991,00 € congstar / 1.060,75 € o2) · Nothing Phone (4a) Pro 128
  („nur im Bündel ab 25,99 €/Monat" 1&1 / TCO 803,66 € 1&1) ·
  Nothing Phone (4a) 128 (379,00 € o2 / „kein Bündel gemessen").
- **Kein Querscroll 390**: Seitenbreite 390 px in beiden Ansichten, auch
  mit „alle anzeigen" (Tabelle rollt im Behälter).
- **Reiterhöhe 11b: 1946 px** laut `pruefe_portal.py` (Grenze 3000);
  eigene Messung Standardansicht 1214 px. Deckel: 12 sichtbar → 111 per
  Knopf. **pruefe_portal: 18 bestanden / 0 durchgefallen.**
- Sortier-Fix nachgewiesen wirksam: Spannen-Spalte hat 62 leere
  `data-s-spanne` (wesentlich-Regel), TCO 19 leere — die sortieren jetzt
  unter die Zeilen mit Zahl (vorher: aufsteigend ganz nach oben, genau die
  Lücke, die der Kommentar von `test_die_spaltenkoepfe_sind_sortierbar`
  beschreibt).

## „Verfügbar"-Spalte (Auftrag 4)

Haupttabelle ist Modell-Ebene — Verfügbarkeit ist eine Listungs-Eigenschaft
und steht deshalb im Zeilen-Aufklapper, dort mit neuem Etikett
**„Bestand"** (vorher „Verfügbar"; 98 von 636 Listungen „keine Angabe").
Pille für „keine Angabe" jetzt `--unklar` (grau; der alte Klassenname
`--unbekannt` hatte keine CSS-Regel). NICHT gelöscht — P4 entscheidet
weiter. Nebenbei kartiert: `verfuegbarkeit` hat 4 Werte im Bestand
(lieferbar 503, unbekannt 98, nicht_lieferbar 33, vorbestellbar 2);
nicht_lieferbar/vorbestellbar bekommen Klartext statt Rohwert.

## Zwei Bugfixes neben dem Auftrag (je eine Zeile Ursache)

1. **Jinja-Undefined-Crash**: `z.buendel_monat` existiert nur an den
   37 1&1-Zeilen (C1 Schritt 4); `Undefined is not none` ist wahr und
   warf `euro()`-TypeError beim Rendern der zwei
   „an_echten_daten"-Browser-Tests (ERROR at setup). Zweig jetzt
   `is defined and is not none` — die beiden ERRORS sind weg.
2. **Sortierung wertloser Zeilen** (siehe oben): Mechanik-Fix in
   `sortiere()`, gilt für alle drei `.gr-alarm`-Tafeln — die Regel stand
   so schon immer in den Vorlagen-Kommentaren („fällt ans Ende"), app.js
   lieferte sie nie.

## Tests

`-k geraete`: **1411 passed / 14 failed / 6 skipped** (C1-Stand:
1422/3/6). Die 3 vorbestehenden Rot unangetastet: Galaxy Tab S11 Ultra
Auto-Katalog (`test_tablets_und_router_bleiben_draussen`), Nachtlauf-
Nullzeilen (`test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen`),
iPhone-18-Querlinks (`test_je_radar_gruppe_ein_querlink_mit_deep_link`).
**Die 11 neuen Rot sind der geplante C3-Umbau** (alle prüfen die ALTE
Listungs-Tafel): Zustandsfilter/Vorbelegung/B2-Deckel/B7-Ankernamen
(test_geraete_reiter_browser, 4) · Export-Bestand, Bestandszahl, flache
Tabelle, unbekannte Verfügbarkeit, abgeleiteter Zustand, Verfügbarkeits-
spalte, Spaltenköpfe-sortierbar (test_geraete_seite, 7).

## Übergaben an C3 / bewusst offen

1. **`geraete.katalogtabelle` bleibt im Python-Kontext** (ungerendert):
   es zu entfernen reißt ~19 Test-Stellen auf, die C3 im selben Zug
   neu schnürt (E5-Regel toter Code — der Wurf gehört in C3s Hand, nicht
   in meine Vorlage). Erst danach fällt `katalogzeilen()` selbst weg.
2. **`test_die_spaltenkoepfe_sind_sortierbar`** bleibt rot: Er verlangt
   einen WERT in JEDEM `data-s-*` JEDES Schlüssels — auf Modell-Ebene
   sind leere Spannen/TCO REGEL (benannte Leerzustände). Empfehlung:
   statischen Wert-Assert auf den Browser-Test umbauen („aufsteigend
   sortiert stehen Zeilen ohne Wert unten") — die Mechanik liefert das
   seit meinem Fix.
3. **Export-Knöpfe für die zwei Modell-CSVs** (`geraete.export.
   modell_barpreis`/`modell_tco`, C1) habe ich NICHT gebaut — mein
   Lead-Auftrag grenzte auf Vorlage+Umschalter ein. Die Daten liegen
   fertig im Kontext; E5 „alle Zahlensektionen exportierbar" ist auf der
   Seite bis dahin nicht sichtbar (Knopf-Zeile in der Kopfzeile ergänzen).
4. **Anbieter-Filter und Zustands-Filter entfallen** auf Modell-Ebene:
   ein Anbieter-Filter bräuchte Contains-Logik (ein Modell hat mehrere
   Händler — `grFilterleiste` vergleicht exakt), der Zustands-Filter ist
   durch C1s Aggregations-Regel ersetzt (Barpreise nur über NEU,
   erneuerte im Aufklapper). Die Textsuche findet Händlernamen (sie
   stehen im Zeilentext). C3/P4: falls der Anbieter-Filter zurück soll,
   braucht er eine eigene Filter-Art.
5. **46 Elemente mit Schrift < 12 px** im Reiter — alle vorbestehend aus
   dem Sortiments-Aufklapper (`gr-v-prozent` 10,5 px, `gr-v-datum`
   10 px, `gr-v-meta` 10,5 px, `rubrik-zahl` 11 px); keine davon neu.
   P4/Auftrag 5 (Text-Deckel) ist der Ort.

## Sorgen

- Screenshots liegen unter `p3/screenshots/` (6 Stück), waren in dieser
  Sandbox nicht ansehbar (Bilder laufen auf einen CDN-Upload statt ins
  Gespräch) — Prüfer bitte ansehen; die strukturelle Sichtprüfung
  (sichtbare Spaltenköpfe je Ansicht, Zeileninhalte, Schriftgrößen) steht
  im Transkript und ist grün.
- Der B7-Verlust (Anbietername der Modellzeile nicht mehr verlinkt; nur
  der Bestpreis-Händler trägt den Quelllink) ist eine C3/P4-Entscheidung:
  auf Modell-Ebene verlinkt der günstigste Händler; alle Händler-Links
  stehen im Aufklapper.
- `m.tco_leer` sagt bei 19 bündellosen Auto-Modellen (Watches, AirPods,
  iPhone-18-Kandidaten) „kein Bündel gemessen" — korrekt, aber P5-Auftrag 1
  (Sichtbarkeit auf beide Wege) ändert deren Sichtbarkeit nochmal.
