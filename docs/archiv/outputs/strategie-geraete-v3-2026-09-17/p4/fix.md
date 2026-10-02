# P4-Fix — Design/Ruhe/Faden (18.09.2026)

Auftrag: S1/S2 aus `pruefung-code.md` komplett, S3 nach Ermessen; FAILs aus
`pruefung-sicht.md` komplett, kleine Verbesserungsliste, Großes als
Lead-Entscheidung. Nicht committet, kein data/state geschrieben, `site/` mit
`cfg` gerendert.

## Ergebnis in Zahlen

| Messung | vorher | nachher |
|---|---|---|
| `pruefe_portal.py` | 20 bestanden / 1 durchgefallen | **21 / 0 / 0** |
| Kriterium 13 (Fließtext Vergleich) | 18 048 Z (Grenze 6000) | **992 Z** |
| Kriterium 11c (Graphkopf bei 390×844) | 840 px (FAIL-Richtung) | **838 px ≤ 844** |
| Rot eingefärbte Elemente je Tafel (ohne SVG-Datenpunkte) | 19/7/6/12 | **8/2/3/5** (alle ≤ 10) |
| Tote `gr-sprung`-Links (Radar) | 10 | **0** (10× „noch keine Zeitreihe") |
| Katalog-Sprünge | 83 (unverändert) | 83, 0 tot |
| „Keine Angabe"-Pillen (Katalog Bestand) | 166 | **0** (stilles „–") |
| Größte Schrift 1440, je Reiter | h2/h1 | **Leitzahl 60 px, 4/4 Reiter** |
| Größte Schrift 390, je Reiter | h1 34 px | **Leitzahl 30 px > h1 28 px, 4/4** |
| Suite `-k geraete` | — | **1460 passed / 2 failed / 6 skipped** |

## Was gefixt wurde

**S1 Faden (tote Sprünge).** Der Radar verlinkte Modelle außerhalb der
Zeitreihen-Wahlmenge — der Deep-Link fiel still aufs Vorgabegerät. Der
Sprung steht jetzt nur auf `daten.erlaubt` mit nicht-leeren Bändern
(`selectattr('1')`), jede Zeile außerhalb nennt die Lücke „noch keine
Zeitrereihe" (kein dritter Zustand). Messung: 0 tote Links, 10 benannte
Lücken; Katalog 83/0. Das WAR der vorbestehende Rot „iPhone-18-Querlinks"
(`test_je_radar_gruppe_ein_querlink_mit_deep_link`) — er ist dadurch grün,
letzter Assert auf die neue Regel umgestellt (im Test dokumentiert). Die
anderen zwei vorbestehenden Rot (Galaxy-Tab-S11-Ultra-`auto`,
Nachtlauf-Nullzeilen) sind unangetastet rot.

**S2 Leitzahl im Leerzustand.** Ohne gewähltes Gerät stand der Satz
„Kein Gerät gefunden." UNTER der stehengebliebenen Leitzahl. app.js
versteckt `#gr-vleit` jetzt im Frühzweig; der Gatter-Fall (kurze Reihe)
versteckt sie bewusst nicht. Neuer Browser-Test mit beiden Zuständen
und Gegenprobe.

**FM 4 / Kriterium 13 (Text-Deckel).** Der Rechenweg-Text der Bündel-Zeilen
zählte zum Fließtext-Deckel des Vergleichs-Reiters (18 048 von 6000 Z — das
einzige rote Portal-Kriterium). Inhalt je Zeile in
`<template class="gr-bnd-rw-vorlage">`, Montage ERST BEIM ÖFFNEN
(click-Delegat auf `summary` + toggle-Capture-Fallback, beide idempotent,
keine Client-Rechnung). Vergleich 18 048 → **992 Z**. Seite 19 + Fragment
487 Vorlagen. Browser-Test: Ziel serverseitig leer, Vorlage > 200 Z, Klick
montiert Posten; Öffnen bleibt netzwerkfrei (bestehender Test grün).

**P4-Regel „Die Antwort ist die größte Zahl".** 1440: Leitzahl 60 px auf
allen vier Reitern (Katalog neu: „157,00 €" Leitzahl nach der h2 statt
h2 als größte Schrift). 390: Leitzahl 30 px > h1 28 px — h1-Minimum
34 → 28 px (`clamp(28px,5.2vw,58px)`). Die zweizeiligen Kachelnamen
(kein Ellipsis mehr, Regel 2) trieben 11c auf 857 px; dritte
Straffungsrunde (Kachel-Paddings, Zeilenhöhen) holt sie auf 838 px.

**Rot-Deckel.** Aktive Knöpfe/Kacheln auf `--red-wash`/`--ink` statt
Vollrot („Rot ist Akzent, keine Fläche"), aktive Kachel Rahmen `--ink`,
Sprung-Links grau mit Rot erst im Hover. Gemessen ohne SVG-Datenpunkte
(das ist Vodafone-Datenfarbe): Vergleich 8 · Radar 2 · Verlauf 3 ·
Katalog 5.

**Kleine Verbesserungsliste (alles im Scope).** Achslabel als
`p.gr-achsenlabel` UNTER dem SVG, trägt jetzt auch die Alarm-Betrags-Regel
(< 200 Z; der Tafelkopf-p „Abweichung zu Vodafone in Prozent…" ist
gelöscht); Bestandszelle „–" bei unbekannter Verfügbarkeit statt 166×
„keine Angabe"-Pille; Kachelname ohne `text-overflow:ellipsis`;
`aria-label` „größter"; `grafik()`-Sicherung bei `n <= 0` (IndexError).

## Tests nachgezogen

Neu: `test_der_rechenweg_wird_erst_beim_oeffnen_montiert` (Browser),
`test_die_leitzahl_schweigt_in_beiden_leerzustaenden` (Browser),
`test_die_katalog_leitzahl_ist_der_guenstigste_zeilenpreis`
(seiten_zahlen, Zelle gegen Zelle),
`test_radar_graph_sprung_ohne_zeitreihe_nennt_die_luecke` (Faden).
Umgestellt auf den template-Pool: Helfer `vorlage_text` in
`test_geraete_tco_zustand.py` (BS4 ≥ 4.13 versteckt template-Inhalt vor
`get_text()` — `find_all(string=True)`; im Browser:
`tpl.content.textContent`), Leser in terminologie/glossar/o2_zeilen;
Browser-Öffnen über `summary.click()` statt `open = true`. `leer()` um
`katalog_ab_preis` ergänzt (Schlüsselparität). Suite insgesamt:
**1589 passed / 2 failed / 6 skipped** (geraete + seiten_zahlen +
wettbewerbsradar_alarme + eine_seite_querlinks + textdeckel).

## Bewusst NICHT gebaut (Lead-Entscheidung)

1. **2c Modellmengen** zwischen Wahl/Katalog/Radar vereinheitlichen —
   40 Namens-Schlüssel/Barpreis-Zeilen, Datenwanderung.
2. **Fragment `geraete-zeitreihe.html` 3,5 MB** (PM-6, P5).
3. **Kachel-Auswahlregel „6 Kacheln = 2 Modelle"** (PM-7).
4. **Bestand-Spalte ganz entfernen** (P5/Antonio — jetzt still „–").
5. **„aktuell" fensterrelativ** (durch Datum im Label abgeschwächt),
   **Vorzeichen** an der Delta-Leitzahl, **mobile KURVE komplett über der
   Falz** (Graphkopf ist über Falz, Kurvenlinien ~35–40 px darunter —
   Strukturfrage, nicht eine Regel).

## Screenshots

Acht Stück unter `screenshots-fix/fix-<reiter>-<breakpoint>.png`
(vergleich/radar/verlauf/katalog × 1440/390). Vorbehalt: Der Bild-Dienst
dieser Umgebung lehnt die Dateien ab (Fehler 1210) und Read zeigt Bilder
hier nur als Upload — ein Augenschein war technisch nicht möglich. Die
harte Abnahme tragen die DOM-Messungen im echten Chromium (Falz, Schrift-
größen, Rot-Zählung, Ellipsis, tote Links); die PNGs sind für den Lead
geschossen und abgelegt.
