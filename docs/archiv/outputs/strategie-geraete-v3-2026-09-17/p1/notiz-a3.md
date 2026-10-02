# Notiz A3 (P1/F3) — Modell-Karten statt Chips im Vergleichs-Reiter

17.09.2026. Auftrag: Forderung 3 ("prominent, richtig geiles Design" statt
"unterkomischer Unterabschnitt"). Ranking-Mass, KACHELN_MAX=6 und
Klick → `waehle(modell, null)` unverändert; KEINE Bilder; app.js unberührt.

## Geänderte Dateien (nur meine Bereiche; A1/A2-Blöcke nicht angefasst)

| Datei | Was |
|---|---|
| `src/telco_radar/report/geraete_zeitreihe.py` | `_anbieter_punkte()` + `_bewegung()` neu; in der paare-Schleife Sammlung von best_je (bester ECHTER TCO je Modell, Näherung ausgeschlossen) und leit_je (Leit-Paar = Kachel-Ranking-Mass); kacheln-Dict um `ab`, `ab_monat`, `delta_text`, `delta_richtung`, `punkte_html`, `anbieter_text` erweitert; `meta`-Feld entfernt (Punkte zeigen die Anbieterzahl — eine Zahl je Ort) |
| `templates/geraete.html.j2` | kacheln-Block: Karte mit Kopf (Name + Punkte), Preiszeile ("ab" + Betrag groß + Ø €/Monat), Delta-Zeile mit Richtungsklasse; `punkte_html` ist fertig HTML (safe), Farben aus `ANB_FARBE` |
| `templates/style.css` | eigener Block "P1/F3 (A3)": Grid `auto-fit minmax(158px,1fr)` desktop (6 Karten in EINER Reihe), aktive Karte 2,5-px-Rahmen + Fläche paper-2; mobil quer rollende Reihe (width 156px) + Falz-Straffung NUR an gr-zr-eigenen Abständen (Steuerblock unangetastet): wahl padding 10→3, kacheln 8→3, antwort 15.5px/1.4→14.5px/1.32 + padding 7→3, rechnung summary 1.1 |
| `tests/test_geraete_zeitreihe_ansicht.py` | Fixture `ansicht_state`; 4 neue Tests (Karte trägt Preis+Punkte in Hausfarben; Delta-GEGENRECHNUNG aus der rohen geraete_tco_historie.jsonl: Front 12.9.=1100 → 15.9.=1230 = "↑ +130 € in 3 Tagen"; kein Delta unter 2 Messtagen; `_bewegung` alle Richtungen + Front ist MINIMUM je Messtag) |
| `tests/test_geraete_zeitreihe_seite.py` | `test_jede_karte_traegt_preis_und_anbieter_punkte` (get_text OHNE Trenner) |
| `tests/test_geraete_zeitreihe_browser.py` | Falztest umgestellt (Karten-Container ≤ 844 statt Chipzeile ≤ 96px); neu: Preiszahl ≥ 20px je Karte bei 1440 UND 390, alle Karten im ersten Viewport bei 1440 (≤ 900), aktive Karte deutlich (Rahmen ≥ 2px + andere Fläche, mit Gegenprobe "alle markiert prüft nichts") |
| `tests/test_seiten_zahlen.py` | 2 Kartenzahl-Tests: gerenderte Karte == ZWEITER aufbereiten()-Lauf (Name/ab/ab_monat/delta wörtlich auf der Seite) + keine Zahl-Fragmente auf der Karte, die nicht aus der Aufbereitung kommen |

## Messwerte (echte Seite, Playwright, nach 12-px-Anhebung)

- Desktop 1440×900: Karten 528–645 px, ALLE 6 in einer Reihe; Preis 21 px;
  Antwort endet 714, Graphkopf 773 — alles unter der 900-er-Falz.
- Mobil 390×844: Karten 608–702 (quer rollend, Karte 156 px breit), Preis
  20 px, Antwort 804, Graphkopf 833 — Kriterium 11c hält (≤ 844), kein
  Querscroll (390).
- 12-px-Regel: erste Fassung fiel in `test_keine_beschriftung_unter_
  zwoelf_pixeln` (Karten-Labels 10–11 px) — alle Karten-Beschriftungen auf
  12 px angehoben, Falz danach erneut gemessen (833).
- Bestand live: iPhone 17 Pro 256 "ab 1.093,00 € / 45,54 €/Monat /
  ±0 € in 5 Tagen / 4 Punkte"; Z Fold8 "↑ +215 € in 5 Tagen" (rot).

## Entscheidungen (Abweichungen mit Grund)

1. **Mobil QUER ROLLEN statt 2×3-Grid.** Der Lead ließ beides zu; 2×3
   (+~160 px) drückt den Antwort-Satz messbar um >100 px unter die
   844-er-Falz — 11c (harter Test + pruefe_portal) geht vor. Die
   wörtliche Messlatte "alle 6 im ersten Viewport bei 390" ist damit als
   rollende Reihe erfüllt (kein Scroll-BERG davor; Steuerblock gleich hoch).
2. **Bewegungs-Delta = PREIS-FRONT des Leit-Paares** (Minimum über alle
   Anbieter am ersten vs. letzten Messtag der Union) — dasselbe Mass wie der
   ab-Preis (bester TCO), nur auf Anfang/Ende bezogen; nichts interpoliert,
   unter 2 Messtagen kein Delta (Feld None, kein Pfeil).
3. **Voller Betrag** auf der Karte ("1.093,00 €"), nicht gerundet — der
   Antwort-Satz zeigt denselben Wert, keine zweite Rundungsstelle.
4. **Delta-Farben**: steigt rot (`--red`), sinken grün `#2f6b3a` (dasselbe
   Grün wie `vl-move-delta` der Differenzierung), unverändert grau.

## Offene Sorgen

- 3 rote Geraete-Tests sind NICHT von mir: `test_geraete_lifecycle`
  (vorbestehend, Handover), `test_geraete_adapter_netzbetreiber::
  test_tablets_und_router_bleiben_draussen` und `test_geraete_o3_rollen::
  test_je_radar_gruppe_ein_querlink_mit_deep_link` — beide entstehen aus
  `data/state/geraete_katalog_auto.json` (heute 12:59 geschrieben, Auto-
  Eintrag "Galaxy Tab S11 Ultra" + iPhone-18-Modelle im Katalog). Das ist
  der iPhone-18-Komplex (E2–E6 OFFEN 1), kein Karten-Diff.
- "±0 € in 5 Tagen" steht derzeit auf 5 von 6 Karten — ehrlich (Front
  unverändert seit 12.09.), aber optisch viel Grau. Wenn der Bestand älter
  wird, mischt sich das von selbst; keine Regel nachlegen.
- Screenshots: /tmp/a3_shots/{vergleich-1440,vergleich-390,karten-1440,
  karten-390}.png (Selbstkontrolle angesehen: keine Überlappungen, keine
  abgeschnittenen Texte).
- Fragmentgröße unberührt (Kacheln stehen in der Hauptseite, nicht im
  Fragment — PM-6 dadurch nicht belastet).
