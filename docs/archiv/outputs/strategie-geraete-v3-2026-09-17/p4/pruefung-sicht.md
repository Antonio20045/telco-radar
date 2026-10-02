# P4-Sichtprüfung (harter Prüfer, ohne Bau-Kontext) — 18.09.2026

Gegenstand: `site/geraete.html` (frisch gerendert), Server 127.0.0.1:8771,
Playwright Chromium. Breakpoints 1440x900 (dsf 1) und 390x844 (dsf 2).
Screenshots: `screenshots/pruef-<reiter>-<bp>.png` (8 Falzbilder) und
`pruef-<reiter>-1440-tafel.png` (4 Tafel-Vollausschnitte).
Rohmessung: `mess-p4.json`, Skript `mess_p4_sicht.py`.
Gegenprobe: `python3 scripts/pruefe_portal.py` → **20 bestanden / 1
durchgefallen / 0 nicht prüfbar** (der eine Durchfaller: Fließtext-Deckel
Vergleich).

Gesamturteil: **durch = NEIN.** Die Seite ist sichtbar ruhiger geworden
(Leitzahl-Falz, Radar-Grafik, Text fast weg, Exporte im Fuß), aber der rote
Faden bricht an einer harten Stelle (toter Sprung mit falscher Antwort), der
zentrale Text-Deckel des eigenen Kriteriums reißt (18 048 > 6 000), und die
Modell-Mengen sind noch drei Schlüsselräume statt einer Menge.

---

## 1. Falz / Leitzahl — 1440: 3 von 4 PASS, Katalog FAIL; 390: FAIL

Gemessen: max(fontSize) aller sichtbaren Textelemente im ersten Viewport
(scroll 0), je Reiter; Klassifizierung über Tag/Klasse/Text.

| Reiter | 1440 max | Element | Urteil |
|---|---|---|---|
| Vergleich | **60 px** `b.gr-leit-zahl` „466,80 €“ (top 610) — knapp über dem 58-px-h1 | Preis-Leitzahl | **PASS** |
| Radar | **60 px** `b.gr-leit-zahl` „−55,5 %“ (top 451) | Leitzahl | **PASS** |
| Preisverlauf | **60 px** `b.gr-leit-zahl` „919,00 €“ (top 668) | Preis-Leitzahl | **PASS** |
| Gerätekatalog | in der Tafel max **25,5 px h2** „Was wo im Regal steht“ (Überschrift!); größte Zahl der Tafel 16 px (Zeilenmodell) | Titel | **FAIL** |

390 px: auf ALLEN vier Reitern ist die größte Schrift der **h1** mit 34 px;
die Leitzahlen liegen bei 30 px. Die Regel „die Antwort ist die größte Zahl“
ist mobil nicht durchgehalten — knapp, aber eindeutig (34 > 30).

**Fix (Katalog):** Falz-Zeile über der Tabelle als Leitzahl, z. B.
„111 Modelle · Einzelgerätepreis ab 219,00 €“ in `gr-leit-zahl`-Größe —
der Katalog ist der einzige Reiter ohne Falz-Antwort.
**Fix (390):** Leitzahl mobil auf 34–36 px anheben oder `h1` mobil auf
28 px senken. Ein Wert genügt, aber er muss durchgängig sein — aktuell
gewinnt der Seitentitel auf jedem der vier Reiter.

Anmerkung Vergleich: Die 60-px-Leitzahl ist das **Delta** („466,80 € unter
der Vodafone-Referenz“), die Kacheln darunter zeigen Absolute Preise —
zwei Preisarten in einem Falz. Nicht falsch (der Satz der Leitzahl ordnet
ein), aber wer überfliegt, mischt „1.093,00 €“ (absolut) und „466,80 €“
(delta). Optional: Leitzahl-Zusatz „−“-Vorzeichen/den Worten „günstister
Abstand“ beibehalten, wie im Antwort-Satz vorhanden.

## 2. Steuerung — PASS

Button-Reihen (y-Cluster) vor dem ersten Datenelement, gemessen je Reiter:

| Reiter | Reihen vor Daten | Inhalt |
|---|---|---|
| Vergleich | 2 | Suchfeld (Input, keine Button-Reihe) → Bandreihe (Klein/Mittel/Groß, top 408) → 6 Modell-Kacheln (top ~500) — erste Antwort/Leitzahl ab top ~600, Kurve ab 858 |
| Radar | 0 | nur Leitzahl + Legende vor der Grafik |
| Preisverlauf | 1 | Raster (Wöchentlich/Monatlich/Quartal) |
| Katalog | 1 | Preisart-Umschalter (Einzelgerätpreis / Gesamtkosten TCO-24) |

≤ 2 überall — **PASS**. Export: **fünf** Download-Links in
`section.gr-export-fuss` („Alle exportieren (636 Zeilen)“, „Preishistorie
(814)“, „Bündel-TCO (837)“, „Radar (467)“, Modell-Barpreis), in JEDEM
Reiter unterhalb des letzten Datenelements (z. B. Vergleich: Export bei
2 609 px, Datenende 1 355 px) — **PASS**, keine Export-Reihe mehr im Kopf.

## 3. Radar — Bild: PASS; Rot-Zahlen: Vergleich/Katalog über Deckel

- **SVG sichtbar:** ja, 1 Grafik je Breakpoint (1440: 1184×425 Balkendiagramm
  „Abstand zum Vodafone-Preis“, 12 Modelle, Nulllinie „Vodafone“; 390:
  vertikale Variante 306×449). Die Tafel **wirkt als Bild**: Leitzahl
  „−55,5 %“ + Kontextsatz + Balkenwand + 4 Filter-Chips, Tabelle als
  Aufklapper. Screenshots `pruef-radar-1440/390.png` bestätigen das Auge.
- **Tafelhöhen:** initial 1 653 px (Radar), pruefe_portal 11b 2 400 px mit
  Aufklappern; alle vier Reiter < 3 000 px (2 845/2 400/1 943/1 871). Die
  4,5-Bildschirm-Tabelle ist weg — **PASS**.
- **Balken skaliert korrekt:** nachgerechnet am SVG: +242,90 € → 786,0 px,
  +238,90 € → 773,1 px (Verhältnis 1,0167 = Werteverhältnis; Nulllinie bei
  x=170). Der optische Eindruck „fast gleich lang“ ist echt, weil die Top-12
  zwischen +182,90 € und +242,90 € liegen — kein Skalierungsfehler.
- **Rot-Elemente je Tafel (initial sichtbar):** Radar **7** ≤ 10 PASS ·
  Preisverlauf 6 PASS · **Vergleich 19 > 10 FAIL** · **Katalog 12 > 10
  FAIL**. Zusammensetzung Vergleich: ~8 Anbieter-Markenpunkte (Vodafone-rot,
  `i`/`circle`), 1 aktiver Band-Knopf **mit roter Fläche**, 1 aktive Kachel
  (rote Umrandung), 1 Delta-Chip „↑ +215 € in 5 Tagen“. Katalog: 11×
  identische rote Sprung-Links „im Graph ansehen →“ + 1 aktiver Knopf (rote
  Fläche). Der Deckel war gegen Alarm-Rot-Massen (Vorher 727) gerichtet und
  ist dort erfüllt — aber die harte Zahl steht über 10, und Rot trägt jetzt
  **vier Bedeutungen** (Marke, aktiv, Delta, Link).

**Fix:** (a) aktive Zustände (Band-Knopf, Preisart-Umschalter) nicht als
rote **Fläche** — die Portal-Regel seit 06.08.2026 heißt „Rot ist Akzent,
keine Fläche“; aktive Knöpfe z. B. tinted `--red-wash` + rote Umrandung.
(b) Katalog-Sprunglinks entsättigen (Pfeil-Symbol rot, Wort grau) oder nur
Pfeil-Icon. (c) Danach Rot-Deckel mit definierter Messregel (Anbieterfarbe
ausgenommen) nachmessen — heute zählt meine Messung Markenpunkte mit, und
selbst dann stehen Vergleich 19/Katalog 12 über 10.

## 4. Text — sichtbar fast weg, aber der eigene Deckel reißt im Vergleich

Sichtbarer Fließtext (nur initial sichtbare `<p>`, ohne Aufklapp-Text):

| Reiter | sichtbar | Kriteriumszahl (inkl. Aufklapper, pruefe_portal 13) | Deckel | Urteil |
|---|---|---|---|---|
| Vergleich | 547 Z | **18 048 Z** | 6 000 | **FAIL (3-fach über)** |
| Radar | 791 Z | 2 743 Z | 6 000 | PASS |
| Preisverlauf | 114 Z | 358 Z | 2 500 | PASS |
| Katalog | 183 Z | 230 Z | 2 500 | PASS |

Der Vergleich trägt 22 `<details>` („So gerechnet“, 19 Tarif-Rechenwege,
„Maßstab & Datenlage“, „41 weitere Tarife anzeigen“), deren Aufklapp-Text
in der Kriteriumsmessung zählt — fast alles der 18 048 Z steckt dort
(je ~500 Z „Gerechnet über …“ plus Postenliste). pruefe_portal fällt
damit als EINZIGES Kriterium durch (20/1/0).

**Wo steht noch Text, der ein Label sein könnte:**
- Radar, `p.gr-erklaer` (156 Z, top 540): „Abweichung zu Vodafone in
  Prozent, mit Vorzeichen – negativ …“ — das ist eine **Achsenerklärung**
  und gehört als zweiteiligers Label unter/über die Grafik („Δ zu
  Vodafone · rot = teurer“), nicht als Absatz zwischen Leitzahl und SVG.
- Vergleich, Tarif-`summary`s sind gut („congstar Allnet Flat XS · 15 GB
  1.093,00 € TCO-24 −466,80 €“) — Zahlen statt Prosa, so soll es sein.

**Fix:** die 19 Rechenweg-Aufklapper auf den P1-Weg als `<template>`-Pool
legen (Montage erst per Klick — genau das hatte P1 für die Rechenwege der
Zeitreihe eingeführt) oder den Posten-Text auf eine Tabelle kürzen. Damit
fällt der Vergleich unter 6 000 Z und Kriterium 13 wird grün — der Deckel
ist der einzige rote Punkt der eigenen Abnahme.

## 5. Roter Faden — Reihenfolge PASS, Sprung bricht bei iPhone 18 (FAIL)

- **Reihenfolge:** Tabs stehen in der geforderten Ordnung (Vergleich →
  Radar → Preisverlauf → Katalog), und jeder Reiter beantwortet seine
  Frage mit einer Falz-Antwort (siehe 1.) — die Geschichte liest sich.
  Wochenkarte „Was diese Woche auffällt (12)“ steht im Preisverlauf
  (2a erfüllt), „Bei Wettbewerbern gelistet (29)“ im Radar (2b erfüllt).
- **Sprung funktioniert** für `a.gr-ksprung` (Radar → Katalog: Tab
  schaltet, Zielzeile trägt `gr-k-ziel`) und für `a.gr-sprung` Xiaomi 17
  512 (Radar → Vergleich: Antwort-Satz „Beim Xiaomi 17 im Band Mittel …
  o2 am günstigsten: 880,75 €“ — Modell und Band kommen richtig an).
- **ABER: 10 tote Graph-Sprünge, alle iPhone 18 Pro / Pro Max.** Die
  Radar-Tabelle verlinkt „im Graph ansehen“ auf 10 iPhone-18-Modelle, die
  die Zeitreihe (87 Modelle im Fragment) nicht kennt. Live gemessen: Klick
  auf „Apple iPhone 18 Pro 256 GB“ (Radar-Zeile „−38,9 % / −952,79 €“)
  schaltet auf den Vergleich und zeigt **„Beim Apple iPhone 17 Pro im Band
  Klein … congstar … 1.093,00 €“** — das vorherige Modell. Kein Fehler,
  keine Meldung, **falsche Antwort**. Das ist die schlimmste Art eines
  toten Sprungs, und es trifft ausgerechnet das Vorführgerät aus E4/E6.
- **EINE Modell-Menge (2c) ist nicht erreicht:** Zeitreihe 87 Modelle,
  Graph-Sprungziele 97, Katalog 111, Radartabelle 132 Schlüssel — davon
  40 Zeilen mit **Namens**-Schlüssel („Galaxy A37“, „iPhone 16“, …) statt
  Slug und **ohne jeden Sprung** (Barpreis-Abschnitt: Medimax, ALDI TALK,
  congstar …). 10 der 97 Graph-Sprünge haben kein Zeitreihen-Ziel (oben).
  Katalog-Sprünge sind sauber (92 von 92 im Katalog).
- **Dubletten:** die Alarm-Tabelle ist Radar-Details-Aufklapper, Chips 4
  Stück — keine Dublette zum Vergleich mehr. Die „Bestand“-Spalte im
  Katalog steht 166× auf „keine Angabe“ (ex-„Verfügbar“, Strategie-Vorher
  90×) — Strategie-Auftrag 4 („Etikett an Feld anpassen oder Spalte fallen
  lassen“) ist **nicht** erfüllt, sondern nur umbenannt und gewachsen.

**Fix (S1 für den Faden):** (a) Sprung fail-closed: kennt die Zeitreihe das
`data-modell` nicht, darf der Link nicht still auf das letzte Modell
umschalten — Link ausblenden oder sichtbar „noch keine Zeitreihe“ hinter
dem Gerätenamen. (b) Die 40 Barpreis-Zeilen der Radartabelle an den
gemeinsamen `modell_schluessel` hängen und auf den Katalog springen lassen
(der führt 40 dieser Geräte nicht — dann either Katalog ergänzen oder
Radartabelle auf die gemeinsame Menge kappen; das ist die 2c-Entscheidung,
nicht nur Kosmetik).

## 6. Mobil 390 — Querscroll PASS, Kurve im ersten Viewport knapp FAIL

- **Kein Querscroll:** alle vier Reiter `scrollWidth` 390 = Viewport. Die
  gemessenen Übersteher (`a.gr-knopf` bis right 1094) liegen in
  Tabellen-Rollbehältern — die Seite selbst rollt nicht seitwärts. PASS.
- **Kurve im ersten Viewport des Vergleichs:** SVG beginnt bei **top 922**
  bei einer Falz von 844 — die Kurve steht ~78 px unter der Falz; über ihr
  Seitenkopf (276 px), Tabs, Suchfeld, Band-Pills und **6 untereinander
  gestapelte Modell-Kacheln**. pruefe_portal 11c ist grün („Graphkopf
  840 ≤ 844“ — 4 px Spielraum), aber die sichtbare Kurvenlinie ist es
  nicht mehr. **KNAPP FAIL.**
- **Katalog mobil nutzbar:** erste Zeile top 823 (auf der Falz), Zeilen
  lesbar, Tabelle rollt in sich — PASS.

**Fix:** mobil die 6 Kacheln zweispaltig (3 Reihen statt 6) oder als
horizontale Scroll-Reihe — das holt die Kurve um 150–300 px nach oben und
deckt auch 11c mit Reserve ab.

## 7. Unruhe im Vergleichs-Reiter — nach Zahlen NICHT ruhiger

Gemessen (initial): **22 Aufklapper** (`details`; Vorher-Messung design.md:
22 — unverändert; davon 19 Tarifzeilen-Aufklapper, die Strategie sie
behalten will, seit P4 mit Aufklappzeichen: pruefe_portal 15 „30 summaries,
alle mit Zeiger“ — BESTANDEN), **1 Chip**, **11 Schrift-Ebenen** inkl.
60-px-Leitzahl/58-px-h1 (10 in der Tafel; Vorher 11 — praktisch
unverändert), Radar: 5 Chips, 147 Zeilen-Aufklapper (zu).

**Antwort auf „ruhiger als 22 Aufklapper / 11 Ebenen?“: NEIN nach den
Zahlen, JA nach dem Auge.** Die Beruhigung kam nicht durch weniger
Elemente, sondern durch Hierarchie: Leitzahl-Falz, eine Grafik je Reiter,
547 sichtbare Zeichen statt Prosa-Wänden, Exporte im Fuß. Die getippten
Metriken stehen aber unverändert da — wenn der Auftrag „ruhiger als 22/11“
wörtlich nimmt, ist das ein FAIL mit klarem Hebel (siehe 4 und 8.7).

## 8. Was ich innerhalb des Scopes Design/Ruhe/Faden weiter verbessern würde

1. **Tote Graph-Sprünge schließen (S1, Faden):** 10 iPhone-18-Links
   scheitern still und zeigen das falsche Modell — fail-closed bauen
   (siehe 5). Das ist der eine Punkt, der „Mischmasch“-Gefühl direkt
   produziert: Klick aufs Vorführgerät landet woanders.
2. **Fließtext-Deckel Vergleich einhalten (Kriterium 13 rot):** 19
   Rechenweg-`<details>` auf `<template>`-Pool umstellen — dann 18 048 →
   unter 6 000 Z und die eigene Abnahme ist komplett grün.
3. **EINE Modell-Menge (2c):** 87/97/111/132 plus 40 Namens-Schlüssel auf
   einen `modell_schluessel` mit einer Quelle; Radartabelle-Barpreiszeilen
   anspringbar machen oder ausblenden.
4. **Katalog-Leitzahl auf die Falz** („111 Modelle · ab 219,00 €“) — der
   einzige Reiter ohne Falz-Antwort.
5. **Mobil: Leitzahl größer als der h1** (34–36 px statt 30) — sonst ist
   die Falzregel auf dem Telefon auf allen vier Reitern verletzt.
6. **Mobil: Kurve im ersten Viewport des Vergleichs** — Kacheln
   zweispaltig/-horizontal (922 → < 844).
7. **Rot entzerren:** aktive Knöpfe ohne rote Fläche (Akzent-Regel),
   Katalog-Sprunglinks entsättigt, dann Rot-Deckel ≤ 10 mit definierter
   Messregel (Markenpunkte ausgenommen) nachmessen. Rot hat heute vier
   Bedeutungen — das ist die Kernquelle der Unruhe, die Antonio „so
   unruhig“ nennt.
8. **Kachelnamen:** drei der sechs Kacheln kürzen auf dasselbe
   „GALAXY S26 UL…“ (`text-overflow:ellipsis` schneidet den Speicher ab);
   Name und Speicher zweizeilig trennen. Dazu: 6 Kacheln = nur 2 Modelle
   in 5 Speichergrößen — „häufige Geräte“ sollten 6 verschiedene sein.
9. **Radar-Erklärabsatz (156 Z)** zum zweizeiligen Achslabel machen
   („Δ zu Vodafone in € · Balkenlänge = Abstand · rot = teurer“).
10. **„Bestand“-Spalte:** 166× „keine Angabe“ (ex-„Verfügbar“, Vorher 90)
    — Spalte aus dem sichtbaren Katalog fallen lassen, Stand nur im
    Zeilen-Aufklapper.
11. **Leitzahl vs. Kachel-Preise im Vergleich:** Leitzahl ist Delta,
    Kacheln absolut — Vorzeichen/Einheit („− 466,80 €“) in der Leitzahl
    selbst tragen, damit der Falz nicht zwei Preisarten mischt.
12. **Fragment-Größe (PM-6, Randnotiz im Scope Ladezeit):**
    `site/data/geraete-zeitreihe.html` ist 3,5 MB — auf dem Telefon spürbar
    vor dem ersten Kurvenbild; Messtag-Begrenzung/Deckel priorisieren.

---

## Anhang: gerenderte Rohwerte (Auszug)

- Tafelhöhen initial 1440: Vergleich 2 098 / Radar 1 653 / Verlauf 1 158 /
  Katalog 1 124 px; 11b (mit Aufklappern): 2 845/2 400/1 943/1 871 — alle
  < 3 000.
- Rot je Tafel: Vergleich 19, Radar 7, Verlauf 6, Katalog 12 (initial
  sichtbar, Marken-/Link-Rot inklusive).
- Schrift-Ebenen Vergleich: 60/21/19/17/15/13.5/13/12.5/12/10.5/10.
- Falz-Leitzahlen: Vergleich „466,80 €“ (60 px), Radar „−55,5 %“ (60 px),
  Verlauf „919,00 €“ (60 px); 390: Leitzahlen 30 px, h1 34 px.
- Modell-Mengen: Zeitreihe 87, Graph-Sprünge 97 (10 ohne Zeitreihen-Ziel:
  alle iPhone 18 Pro/Pro Max), Katalog-Sprünge 92 (0 ohne Katalogzeile),
  Katalog 111, Radartabelle 132 Schlüssel (40 Namens-Schlüssel ohne
  Sprung). Katalog ohne Radartabelle: 19 (bewusst, nur-Katalog-Modelle).
- Export-Fuß: 5 Links, je Reiter unterhalb des letzten Datenelements.
- Sprung-Tests live: ksprung Xiaomi 17 → Katalog `gr-k-ziel` OK; gsprung
  Xiaomi 17 → Vergleich „880,75 €“ OK; gsprung iPhone 18 Pro 256 →
  **falsche Antwort „iPhone 17 Pro / 1.093,00 €“**.

Server nach der Prüfung gekillt; nichts committet.
