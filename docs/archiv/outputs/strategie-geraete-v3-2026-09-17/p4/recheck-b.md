# P4b-Re-Check-B — Urteil (18.09.2026)

Prüfer: frisch, hart, ohne Fix-Kontext. Basis: frisch mit `cfg` gerendertes
`site/` (Render bestätigt: `[hidden]{display:none!important}` Zeile 75 und
`.src-table a.gr-sprung` Zeile 3467 der ausgelieferten style.css), Server
8773, Playwright 1440/900 + 390×844 (dsf 2, is_mobile), Suite + Portal am
stehenden Baum. Screenshots und Messskript: `screenshots-recheck-b/`,
`mess_recheck_b.py` (dieses Verzeichnis). Nichts committet, kein
`data/state` geschrieben, Server gekillt.

## Ergebnis: **durch = JA**

Alle drei offenen FAILs aus `recheck.md` sind WIRKLICH zu — gemessen an
Sichtbarkeit (computed display + Boxhöhe), nicht an Attributen, an beiden
Pfaden, im DOM und im Augenschein. Keine Regel der P4-Abnahme gebrochen.

## FAIL 1 (S1) Leerzustand-Leitzahl: ZU

| Zustand | `#gr-vleit` | `#gr-vkacheln` | Leer-Satz |
|---|---|---|---|
| Kontrolle (Gerät gewählt) | flex, 81 px, „919,00 €" sichtbar | grid, 88 px | — |
| Suche „zzzz" | **none, 0 px** | **none, 0 px** | sichtbar, 22 px, „Kein Gerät gefunden." |
| Von-Datum 2027 | **none, 0 px** | **none, 0 px** | sichtbar, „Für diesen Zeitraum liegen keine Messpunkte vor." |

`#gr-vsteuer` und `#gr-vlegende` ebenfalls none/0 (Pfad A); der DOM-Resttext
„919,00 €" steht noch im Knoten, ist aber unsichtbar — genau richtig. Beide
Screenshots im Augenschein gegengelesen: leer heißt leer, keine Zahl behauptet
das vorherige Gerät. Der umgestellte Test misst computed display + Höhe an
beiden Pfaden MIT Gegenprobe am Ausgangszustand (Leitzahl/Kacheln müssen erst
DA sein) — 4/4 zielgerichtete Tests grün.

## FAIL 2 Katalog-Rot: ZU (12 → 1)

- 83 `a.gr-sprung` im Katalog, erster computed color **rgb(51,48,42)** (ink-grau)
  — die elf Vollrot-Links sind weg.
- Vollrot-Zählung initial (eigene Farbe/Fläche/Rand, ohne SVG/template,
  Zähler-Gegenprobe mit gestellt rotem Element bestanden): **Katalog 1**
  (aktiver Knopf „Einzelgerätpreis": Wash-Fläche rgb(253,240,238), roter Rand
  rgb(230,0,0), Text rgb(163,0,0) — Akzent, keine Fläche) · Radar 0 ·
  Preisverlauf 1 (aktiver Raster-Knopf) · Vergleich 2 echte (aktiver
  Band-Knopf, Delta-Chip „↑ +215 €") + 18 Marken-/Datenpunkte als HTML-Tiles
  (6× Vodafone-rot, Orange, Pink — Datenfarben, kein Befund). Deckel ≤ 10
  überall.
- Der neue Test `test_der_rotdeckel_des_katalogs_ist_eine_messregel` läuft
  grün und fängt einen Rückfall: Zähler mit Gegenprobe (gestellt rotes Element
  MUSS gezählt werden), Fixture-Wache (≥ 1 Sprung-Link), Assert
  Sprung-Farbe ≠ var(--red) UND Deckel ≤ 10. Ein Wieder-Einfärben der Links
  liefe in BEIDE Asserts. Der Zähler des Tests ist strenger als meine
  Messung (exakter `var(--red)`-Vergleich, „eigenes Rot" gegen Doppelzählung,
  Rand nur mit Breite > 0, ganze Tafel).

## FAIL 3 Mobil-Kurve: ZU (921 → 813)

390×844, Vergleichs-Reiter, sichtbares SVG (`svg.gr-zr--schmal`, 306×325):

| Messung | Wert | Falz 844 |
|---|---|---|
| SVG-Top | **813** | darüber |
| oberster Kurvenpunkt (Halo/Kreis) | **838** | darüber |
| erste Linie | 853 | 9 px darunter (deklarierte Grenze) |
| Antwort-Satz endet | 787 | darüber |
| Graphkopf endet | 813 | darüber |

11c **BESTANDEN** (787/813). Karten: 6 Kacheln in EINER quer rollenden Zeile
(Behälter scrollWidth 966), Seiten-scrollWidth 390 — kein Querscroll, Übergang
sauber. Screenshot im Augenschein: Kartenreihe, Leitzahl, Antwort-Satz, und
der Kurvenanfang mit farbigem Datenpunkt + „1.600 €"-Achsenlabel am Falzrand.
Neuer Test misst SVG-Top UND min über Punkt/Halo/Linie — genau das, was 11c
nicht sah; grün.

## P4-Abnahme gesamt (Stichproben, alle bestanden)

- **Falz-Font 1440:** max = Leitzahl 60 px auf 4/4 Reitern (Vergleich
  „466,80 €", Radar „−55,5 %", Verlauf „919,00 €" top 668, Katalog
  „157,00 €"); h1 58. Meine Erstmessung zeigte den Verlauf ohne 60-px-Zahl —
  Ursache war der Leerlauf in derselben Browser-Session (Wahl zurückgebaut);
  frisch gemessen steht sie.
- **Falz-Font 390:** Leitzahl 30 px > h1 28 px auf 4/4.
- **Button-Reihen:** ≤ 2 auf allen Reitern (1/0/0/0 nach Button-Zählung;
  Sicht-Methode inkl. Radios 2/0/1/1).
- **`#tafel-radar` svg:** 2, davon 1 groß sichtbar (1184×425).
- **Text-Deckel:** pruefe_portal 13 = Vergleich 992 Z / Radar 2618 /
  Verlauf 358 / Katalog 230 — grün; 14 (0 Z unter SVG) und 15 (30 summaries)
  grün.
- **Kein Querscroll 390:** 4/4 Reiter scrollWidth 390.
- 11b Reiterhöhen 2860/2291/1943/1973 < 3000.

## Suite und Portal

- `pytest -k geraete`: **1462 passed / 2 failed / 6 skipped** — die zwei Roten
  sind exakt die unangetasteten Vorbestehenden
  (`test_tablets_und_router_bleiben_draussen` = Galaxy-Tab-S11-Ultra,
  `test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen`).
- `pruefe_portal.py`: **21 bestanden / 0 durchgefallen / 0 nicht prüfbar**.

## Wie ich es innerhalb meines Scopes weiter verbessern würde

1. **Erste Linie 9 px unter der Falz** (853): der Pfast verbindet tiefer
   liegende Preise; wer die LINIE selbst über der Falz will, muss
   Antwort-Satz oder Kartenreihe opfern — 11c-Geist bzw. Karten-Messlatte.
   Bewusste Grenze, korrekt deklariert; keine Handlung nötig.
2. **Falz-Reserve null:** der Antwort-Satz bricht in 4 Zeilen; eine fünfte
   (längerer Modellname/Band) kostete ~19 px und drückte den Punkt wieder
   unter die Falz. Der Test fängt es — aber erst NACH dem Bruch. Härtere
   Option: mobil max. 3 Zeilen Antwort-Satz (Design-Entscheidung, nicht
   eine CSS-Zeile).
3. **Rot-Deckel genagelt nur für den Katalog.** Vergleich (2 echte), Radar
   (0), Verlauf (1) sind heute unauffällig, aber ohne eigenen Test — ein
   Rückfall dort bliebe still. Derselbe `_ROT_ZAEHLER` ließe sich je Reiter
   wiederverwenden.
4. **Messregel-Schlupfloch „ohne SVG":** die 18 Marken-/Datenpunkte der
   Kacheln sind HTML-Tiles (10×10 `<i>`), keine SVG — die Regel „ohne SVG =
   Vodafone-Datenfarbe zählt nicht" greift für sie nur per Klassenliste.
   Wer den Zähler verallgemeinert, zählt Datenfarben als Befund. Die Regel
   besser „ohne Datenfarben (Marke)" nennen.
5. **Delta-Leitzahl ohne Vorzeichen** („466,80 €" + Worte daneben) — alte,
   bewusst offene Anmerkung aus pruefung-sicht.
6. **Lead-Liste unverändert:** PM-6 Fragment 3,5 MB · PM-7 6 Kacheln = 3
   Modelle · 2c Modellmengen (87/97/111/132) — nicht Scope dieser Runde.

## Verfahren

Nichts committet, nichts gepusht, kein `data/state` geschrieben; Server 8773
nach den Messungen gekillt.
