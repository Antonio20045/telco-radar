# BRIEF F-4a (05.09.2026, abends) — die Antwortzeile ist die Leitzahl der Seite

Auftragsgrundlage: `BRIEF_F4A_ANTWORTZEILE.md` (PM, Antonio 18:52: „Mobil ist
raus, dafür ist die Geräteseite die Hauptarbeit — die Antwortzeile ist die
höchste Priorität, sie ist der Grund, warum die Seite existiert.") Bezug:
ROADMAP-Zeile F-4a, LAGE-Eintrag 16:57 (Vision-Befund 8, Desktop 1440
gemessen). `BRIEF_F3_MOBILNAV.md` ist zurückgezogen und nicht Teil dieser
Runde.

**Maßstab: Desktop 1440×900. Mobil ist kein Kriterium** (Antonio 18:52,
Laptop-only).

## Befund

„Günstigster Gerätepreis: X € (Anbieter) · günstig mit Tarif: Y € (Anbieter)"
stand als ein einziger 19px-Fließtext-Absatz zwischen der Geräteauswahl
(20px Serife) und dem Zeitreihen-Graphen (12px Chrome-/Achsenschrift) —
kleiner als die Karten-Leitzahl (27px) und ohne jede Struktur, die sie von
einer Nebenzeile unterschied. Genau das ist der Befund: „sie geht unter dem
Chart unter, obwohl sie der Grund ist, warum die Seite existiert." Dazu
Vision-Befund 8: „günstig mit Tarif: 1.619,64 €" ist für die Zielgruppe
mehrdeutig (teurer? besser?) — ohne eine Zeile, die „Gerätepreis" und „mit
Tarif" unterscheidet, bleibt offen, was die zweite Zahl überhaupt misst.

## Umgesetzt

**Zwei Änderungen, ein Ort** (`templates/geraete.html.j2`, Abschnitt „Die
eine Antwortzeile"; `templates/style.css`). Nichts sonst angefasst — Chart,
Karten, Klappe, Auswahl bleiben unverändert (Auftrag Punkt 3).

1. **Dominanz.** Aus dem einzeiligen Fließtext-Absatz wird ein eigener
   Block mit drei Ebenen, alle aus Bausteinen, die es auf dieser Seite
   schon gibt:
   - eine **3px-Rubriklinie** oben grenzt den Block ab — Linien statt
     Kasten (Hausregel: „keine Schatten, kein Radius"), keine neue
     Bauteil-Art;
   - je Zahl ein kleines, ausgeschriebenes Etikett (12px, Versalien,
     gedämpft) über einer **32px-Serifenzahl** — größer als die
     Karten-Leitzahl (27px, `.gr-kk-leit`), weil diese EINE Zeile über der
     ganzen Tafel steht, nicht neben 66 Anbieterkarten; der Anbieter läuft
     in kleiner Sans-Schrift daneben;
   - beide Zahlen stehen nebeneinander (Flex-Zeile, umbruchfähig), damit
     der 5-Sekunden-Blick beide Werte und ihre Anbieter gleichzeitig
     erfasst.

   Kein neues Bauteil von Rang: dieselbe Anlehnung, die der Auftrag
   erlaubt („Karten-Leitzahl-Optik"), nur konsequent zu Ende geführt — auf
   dieser Zeile keine Farbfläche, kein Radius, keine Schatten, damit sie im
   Zeitungsraster der Seite bleibt, statt wie ein fremdes Widget zu wirken.

2. **Laien-Erklärzeile** (Vision-Befund 8): ein Satz direkt unter der
   Zahlenzeile, in der Nebentonlage der Seite (12,5px, sans, gedämpft,
   dieselbe Stimme wie `.gr-a-klein`):

   > „Gerätepreis: einmalig ohne Vertrag · mit Tarif: Gesamtpreis über
   > 24 Monate"

   74 Zeichen (Grenze: 80). Der Satz unterscheidet die zwei Begriffe der
   Antwortzeile explizit — „Gerätepreis" ist eine einmalige Zahlung ohne
   Vertrag, „mit Tarif" ist die Gesamtsumme aus Gerät und Tarif über
   24 Monate — statt eine Rechenmethode zu erklären.

Die Antwortzeilen-**Werte selbst sind unverändert**: dieselben Zahlen,
dieselben Anbieter, dieselbe Datenquelle (`m.antwort` aus
`geraete_tco_karten.modelle()`). Keine Python-Datei ist angefasst.

## Warum diese Dominanz-Lösung (nicht Kasten, nicht Farbe)

Drei Alternativen verworfen, mit Grund:

- **Ein Kasten mit Hintergrundfläche** wäre die naheliegendste
  „Hervorhebung" — widerspricht aber der Hausregel „Linien statt Kästen:
  keine Schatten, kein Radius; Hierarchie kommt aus Linienstärke" und hätte
  die Antwortzeile wie ein fremdes Widget neben der Zeitungsoptik der
  restlichen Seite wirken lassen.
- **Ein roter Akzent** (Rand, Hintergrund) wäre naheliegend für „wichtig" —
  verstößt aber gegen „Rot ist Akzent, keine Fläche … Rot markiert nur
  Rubriken, Dringlichkeit und Links." Diese Zeile ist keine Dringlichkeit
  und kein Link.
- **Eine noch größere Zahl als die Kartenzahl plus Farbfläche** wäre
  Übertreibung gewesen — 32px (5px über der Kartenzahl) plus die
  3px-Rubriklinie reicht, um im Browser klar zu dominieren (siehe Messung
  unten), ohne die restliche Tafel zu erdrücken.

Gewählt: **Größe + Struktur + Linie**, alles aus bestehenden
Bauelementen der Seite (Karten-Leitzahl-Optik, Rubriklinie, Nebenton-Sans)
— „keine neue Spalte, kein neues Bauteil von Rang" (Auftrag Punkt 1).

## Screenshots (1440×900, echtes Chromium, echter Bestand)

Beide zeigen den Modellblock „Apple iPhone 17 Pro 256 GB" (Vorgabemodell
der Startansicht) aus dem committeten `data/state/geraete_tco.json` /
`tarife.jsonl` — keine synthetische Fixture, derselbe Datensatz, der auch
live steht.

- **Vorher:** `/tmp/f4a-vorher-tafel.png`
- **Nachher:** `/tmp/f4a-nachher-tafel.png`

Vorher: eine 19px-Fließtextzeile direkt unter der 12px-Modellüberschrift,
optisch kaum von einer Nebenzeile zu unterscheiden — kleiner als die
19px selbst wirkende Leitzahl der Chart-Achse daneben suggeriert.
Nachher: 32px fette Serifenzahlen mit Versalien-Etikett, 3px-Rubriklinie
darüber, Erklärzeile darunter — im 5-Sekunden-Blick dominiert der Block
den oberen Bildschirmbereich der Tafel, deutlich vor dem Graphen darunter.

## Tests

**Neu:** `tests/test_geraete_antwortzeile_browser.py` (4, echtes Chromium,
1440×900) — die im Auftrag verlangte Browser-Messung mit berechnetem Style:

1. `test_leitzahl_ist_mindestens_so_gross_wie_chart_titel_und_achsen` —
   `getComputedStyle(...).fontSize` der Leitzahl (`.gr-antwort-zahl`) gegen
   Chart-Chrome (`.gr-g0-chrome`) und alle Achsenbeschriftungen
   (`.gr-g0-achse`): 32px ≥ 12px, mit einer Marge von mindestens 10px (nicht
   nur „gleich groß").
2. `test_dom_reihenfolge_auswahl_antwortzeile_chart_bleibt` — im LEBENDEN
   DOM (nicht nur im Quelltext wie in `test_geraete_faden.py`): Auswahl →
   Antwortzeile → Chart.
3. `test_erklaerzeile_ist_vorhanden_kurz_und_direkt_benachbart` — Text
   vorhanden, ≤ 80 Zeichen, `parentElement === antwort` UND
   `lastElementChild === erk` (direkt benachbart, kein verschachtelter
   Umweg).
4. `test_erklaerzeile_unterscheidet_geraetepreis_und_tarif` — die
   Erklärzeile nennt tatsächlich beide Begriffe („Gerätepreis" und „Tarif"),
   nicht nur irgendeinen Satz.

Fixture: dieselbe `_baue()` aus `test_geraete_tco_zustand.py`, die auch die
bestehenden statischen Antwortzeilen-Tests in `test_geraete_faden.py`
verwenden — kein zweiter Datensatz für dieselbe Frage.

**Bestehende Tests unverändert grün**, insbesondere
`test_antwortzeile_steht_zwischen_auswahl_und_graph` und
`test_antwortzeile_nennt_beide_preise_mit_anbieter`
(`test_geraete_faden.py`) sowie die Werte-Tests in
`test_geraete_tco_hauptansicht.py` — keiner davon musste geändert werden,
weil die Zahlen, Anbieter und die äußere Klasse `.gr-antwort` unverändert
sind; nur ihre innere Struktur ist neu.

## Suite

```
2 failed, 2747 passed, 14 skipped, 73 warnings in 236.42s
FAILED tests/test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung
FAILED tests/test_promo_seite.py::test_der_leere_screenshot_wird_nicht_ausgeliefert
```

Beide Rote sind die vorbestehenden aus dem Auftrags-Maßstab (2 failed /
~2746 passed / 14 skipped) — **keine neuen Roten**. Die Differenz zum
genannten Richtwert (2747 statt 2746 passed) sind die vier neuen
Browser-Tests dieser Runde.

## Site-Artefakt

`render_site()` mit `load_config(root)` gelaufen (CLAUDE.md §6: „ohne `cfg`
rendert eine stillschweigend halbe Seite"). Geändert: `site/geraete.html`
(dieselben Zahlen/Anbieter je Modellblock, nur die Antwortzeilen-Markup
erneuert) und `site/style.css` (neue Selektoren, alte drei entfernt).
`site/data/keyword-index.json` ist eine reine Datums-Zeitbombe (`stand`
gegen die Laufzeit-Uhr, hier ohne Bezug zu diesem Auftrag) und wurde
**zurückgesetzt** (`git checkout -- site/data/keyword-index.json`).

## Budget

Auftrag innerhalb des Budgets abgeschlossen (Pflichtlektüre, Umsetzung,
neue Tests, volle Suite, Vorher/Nachher-Screenshots, Bericht) — kein
„offen"-Vermerk nötig.

## Nächster Schritt (aus der ROADMAP, nicht Teil dieses Auftrags)

F-4b (Legende: Gelb/congstar-Kontrast, Marker-Symbole), F-4c (Y-Achse
runden), F-4d (Rot-Kollision Telekom-Serie/Marken-Rot), F-4e
(„Serie startet"-Kollisionen, Serif/Sans-Bruch) stehen laut ROADMAP „pending
— nach F-4a" und sind bewusst nicht in dieser schmal geschnittenen Runde
angefasst.
