# Geräteradar: Preiswahrheit, Kürzung, Kennzahlen (W1–W3)

Auftragsgrundlage: „Geräteradar — Evaluation vom 29. August 2026", Teil 2.
Stand danach: **2078 Tests** (vorher 1972), `pruefe_portal.py`
**16 bestanden / 0 durchgefallen**.

Alle Zahlen unten sind gemessen.

---

## 0. Drei Zahlen der Evaluation reproduzieren nicht

Vor dem Bauen wurde jeder Befund am ausgelieferten Export und an der
gerenderten Seite nachgemessen. Drei stimmen so nicht — und sie machen W1
kleiner, nicht anders.

| Behauptung | Gemessen |
|---|---|
| iPhone 16 128 GB · 697 € gewinnt falsch | **Falsch.** Die Zeile ist korrekt als `refurbished` erkannt, die Seite sagte „niemand günstiger (1 verglichen)". Der Refurbished-Filter im Vergleich **funktionierte** |
| 12 Doppelpreise | **5.** Zwei davon der Zustandsfehler, drei echte Farbpreise bei o2 (S26 cobalt violet 955 gegen schwarz 1009) |
| Speicherinversion S24 Ultra 512 GB = 745 € | **Keine.** Die 512-GB-Zeile ist korrekt `refurbished` („titanium black gebraucht"). Über den ganzen Bestand: **0 Inversionen**, sobald der Zustand im Schlüssel steht — was er bereits tat |

Bestätigt sind: Galaxy S25 128 GB (o2 577 € „grau erneuert" schlug Vodafone
849,90 €), 155 von 164 Punkten ohne Etikett, 65 Aufklapper, 18299 px
Seitenhöhe, und beide kaputten Kennzahlen.

---

## 1. Die Ursache war ein Wort

o2 kennzeichnet **dieselbe** Gebrauchtstrecke in zwei Schreibweisen:

```
'Apple iPhone 14 (gebraucht) 128 GB mitternacht erneuert'      -> refurbished
'Apple iPhone 14 Pro (erneuert) 128 GB space schwarz erneuert' -> neu   FEHLER
'Samsung Galaxy S25 (erneuert) 128 GB grau erneuert'           -> neu   FEHLER
```

`_ZUSTAENDE` kannte „gebraucht", nicht „erneuert". Acht von zehn
Gebrauchtgeräten waren richtig erkannt; die zwei mit „(erneuert)" liefen als
Neugerät mit — und genau die unterboten den Vodafone-Neupreis.

Zwei weitere tote Stellen derselben Liste: `"wie neu"` konnte **nie**
treffen (ein Zwei-Wort-String wurde gegen eine Menge einzelner Wortmarken
geprüft), `renewed` fehlte ganz.

### Was dagegen steht

| Regel | Wo |
|---|---|
| Der Zustand wird aus **allen** Signalen gelesen — Titel, Farbfeld, URL | `geraete_model.lies_listung` |
| Ein unklares Kennzeichen („neuwertig", „Retoure", „Open Box") ergibt `unbekannt` und wird **nicht** als neu angenommen | `_UNSICHER` |
| Vergleich, Preisgrafik und die Preisspanne der SKU-Matrix zeigen nur `neu`. Export und Variantenzeile zeigen alles, gekennzeichnet | `VERGLEICHBARE_ZUSTAENDE` |
| Das Zustandswort wird aus der Farbe gelöst, samt Klammerresten („Schwarz (gebraucht)" → „Schwarz") | `ohne_zustandswort` |
| `zustand` wird validiert wie `verfuegbarkeit` — ein Adapter mit „Neu" statt „neu" fiele sonst still und fail closed aus beiden Preisaussagen | `Listung.__post_init__` |

### Die Wirkung, an der echten Ausgabe

Galaxy S25 128 GB: **„o2 577,00 €, −272,90 €"** → **„niemand günstiger
(1 verglichen)"**. Die Falschaussage ist weg.

---

## 2. Das Netz darunter (W1.2)

`report/geraete_pruefung.py`, vor jedem Rendern. Vier Prüfungen:

| Prüfung | Was sie tut |
|---|---|
| **Zustand veraltet** | Rechnet den Zustand gegen den gespeicherten Rohtitel neu. Der Store trägt seine alten Werte bis zum nächsten Crawl — und ein Modell, das ein Anbieter **ausschließlich** gebraucht listet, fände sonst kein Netz. Keine Datenwanderung: der Store wird nicht angefasst |
| **Doppelpreis** | Dieselbe (Anbieter, Modell, Speicher, Zustand) mit zwei Preisen |
| **Speicherinversion** | Mehr Speicher, weniger Geld |
| **Ausreißer** | Mehr als 60 % vom Median |

**Nur was sich selbst widerspricht, wird aussortiert.** Ein Doppelpreis und
eine Speicherinversion sind Selbstwidersprüche — der Datensatz widerspricht
sich, und welche Zahl stimmt, sagt er nicht. Ein Ausreißer widerspricht dem
**Markt**: ein Discounter, der wirklich 60 % unter dem Median liegt, ist das
Signal, wegen dem diese Seite existiert. Er wird gemeldet, nicht gelöscht.

**Die 30-%-Schwelle ist kalibriert, nicht geraten.** Über den echten Bestand:

```
112,3 %  o2  iPhone 14 Pro  128 GB   577 -> 1225   Gebrauchtgerät   entfernt
 53,0 %  o2  Galaxy S25     128 GB   577 ->  883   Gebrauchtgerät   entfernt
 21,6 %  o2  Galaxy S26 FE  128 GB   667 ->  811   pistachio/bk     gezeigt
  9,6 %  o2  Galaxy S26 U.  256 GB  1315 -> 1441   Farbaufschlag    gezeigt
  5,7 %  o2  Galaxy S26     256 GB   955 -> 1009   Farbaufschlag    gezeigt
```

Eine Regel, die alle fünf verwirft, löscht drei wahre Preise. Der Bericht
steht auf `/geraete-quellen.html`: *343 Preiszeilen geprüft, 4 aus dem
Vergleich genommen, 7 Auffälligkeiten notiert.*

---

## 3. Die zwei kaputten Kennzahlen (W3)

| Vorher | Ursache | Jetzt |
|---|---|---|
| „**267** Geräte neu im Regal" bei 59 beobachteten | `len(neu_gelistet)` zählte **Listungen** | „59 Geräte neu im Regal" |
| „o2 führt **54** Generationen" bei 59 beobachteten | zählte verschiedene `device_id`, also **Modelle** | „24 Generationen · 54 Modelle" |

**Beim zweiten Anlauf fiel ein tieferer Fehler auf.** Die erste Fassung
zählte `(Hersteller, Generation)` — und `generation` ist die Nummer
**innerhalb einer Baureihe**, kein vergleichbarer Jahrgang:

```
Samsung  Galaxy A57        generation=57
Samsung  Galaxy S26 Ultra  generation=26
Samsung  Galaxy Z Fold8    generation= 8
```

Je Hersteller verglichen gewinnt die A-Reihe. Der Standard „nur aktuelle
Generation" zeigte deshalb **drei Galaxy A57 und keine einzige S26** — das
aktuelle Flaggschiff fehlte in der Standardansicht. Umgekehrt wären „Redmi
17", „Redmi Note 17" und „Xiaomi 17T" **eine** Generation gewesen.

`serie_aus_modell()` liest die Baureihe („Galaxy S26 Ultra" → „Galaxy S",
„Galaxy Z Fold8" → „Galaxy Z Fold", „Redmi Note 17 Pro" → „Redmi Note").
Gezählt und gefiltert wird seitdem je (Hersteller, Baureihe).

**Das hat nur das Ansehen der Grafik gezeigt** — alle Tests waren grün.

---

## 4. Die Seite auf ihre Aussage (W2)

**18299 px → 5211 px**, also von 20,3 auf **5,8 Bildschirme**.

| Schritt | Ersparnis |
|---|---|
| SKU-Matrix und die 65 Varianten-Aufklapper hinter je einen Aufklapper | 7721 px |
| Vergleichstabelle: nur Zeilen mit ≥ 3 % **oder** ≥ 15 € Abstand, höchstens 14; Vollansicht hinter Aufklapper | 2832 px |
| 17 Ausfallgründe hinter einen Aufklapper (vollständig auf der Quellenseite) | 1646 px |
| Chart-Höhe je **Form** synchronisiert statt über beide | 360 px |
| Lückenliste „bei Vodafone nicht gelistet" hinter Aufklapper | 474 px |
| Exportbeschreibung und Grafik-Vorspann zusammengezogen | 91 px |

**Nichts ist gelöscht** — alles ist eingeklappt oder steht auf der
Quellenseite. `tests/test_geraete_hoehe_browser.py` misst die Höhe an echtem
Chromium und prüft, dass kein Aufklapper offen steht: ein versehentliches
`open` macht die Seite wieder zwanzig Bildschirme lang, ohne dass sich eine
Zeile Inhalt ändert.

**Die Höhe ist strukturell begrenzt, nicht nur heute knapp unter der
Grenze.** `UEBERSICHT_MAX_ZEILEN = 14` ist gerechnet: eine Zeile misst 71 px,
die Seite steht bei 5211, die Grenze bei 5400. Ohne den Deckel hing die
Seitenhöhe am Datenbestand — zwei zusätzliche Zeilen hätten den Abnahmetest
gekippt, ohne dass sich eine Zeile Code ändert. Dieselbe Fehlerklasse wie die
Datums-Zeitbomben in CLAUDE.md §6, nur über den Bestand statt über die Uhr.

**ODER, nicht UND** bei der Vergleichsschwelle: bei einem 200-€-Gerät sind
15 € viel und 3 % wenig, bei einem 2000-€-Gerät umgekehrt.

### Die Grafik

| | vorher | jetzt |
|---|---|---|
| Bänder | 112 (Samsung 38, Apple 30) | 54, höchstens 12 je Spalte **in beiden Ansichten** |
| gezeichnete Punkte | 153 | 62 |
| Punkte je Ansicht | 160 gegen 164 | gleich |
| Etikettenquote der Punktform | 43 % | **68 %** (Anbieteransicht 79 %) |

**Gedeckelt wird je Hersteller UND je Laden, einmal für beide Ansichten.**
Jede der drei Bedingungen war einzeln schon einmal die falsche:

* Nur je Hersteller gedeckelt hielt die Herstelleransicht ihre zwölf,
  während in der Anbieteransicht sechs Hersteller in **derselben**
  Ladenspalte landeten — gemessen: o2 23 Bänder, Vodafone 21.
* Nur je Spalte gedeckelt behielten die zwei Ansichten **verschiedene**
  Geräte, und `pruefe_portal.py` Kriterium 11 fiel darauf durch.
* Fällt eine Spalte ganz heraus, wird die Legende falsch: ALDI TALK verlor
  seine zwei Listungen an Samsung, Nothing fiel bei zu engem Ladendeckel ganz
  aus der Herstelleransicht. Die Rettung **verdrängt** deshalb den
  schwächsten Eintrag, statt anzuhängen — angehängt stand Samsung mit 13
  Bändern da.

**Der Generationen-Filter steht bewusst nicht auf „nur aktuelle
Generation".** Kurz war er es, und zwei Messungen haben es kassiert: er
blendete ALDI TALKs einzige Listung aus und stellte damit eine beschriftete,
leere Ladenspalte unter eine Legende, die vier Anbieter nennt; und ohne
JavaScript las man „nur aktuelle Generation" über einer Grafik mit allen
Punkten. Das Aufräumen leistet die Kappung, und die fällt serverseitig.

## 5. Was `diff-reviewer` gefunden hat

Zwanzig Befunde über drei Durchgänge, alle behoben, jeder mit einem Test, der
gegen den alten Stand durchfällt. Die fünf teuersten:

1. **KRITISCH.** `lies_listung` stürzte mit `UnboundLocalError` ab, sobald
   ein Adapter eine leere Farbe lieferte — eingebaut von dieser Sitzung.
   Weder `_uebernimm` noch `sammle_anbieter` noch `geraete_pipeline` fangen
   das: **ein einziger Satz hätte den ganzen Nachtlauf beendet**, und ein
   Abbruch sieht in Actions aus wie ein Lauf, der nie lief.
2. **Die Veröffentlichungsschwelle hing an der Plausibilitätsprüfung.** Ein
   Anbieter mit weiten Farbpreisen hätte den Navigationseintrag „Geräte" auf
   **jeder** Seite verschwinden lassen, ohne Fehler und ohne Warnung.
3. **Die Obergrenze griff je Spalte gar nicht.** Gekappt wurde je Hersteller,
   gezählt je Spalte — in der Anbieteransicht trug o2 23 Bänder. Der eigene
   Test fiel nicht durch, weil seine Fixture **einen** Laden hatte.
4. **Der Anbieterfilter zählte Zeilen aus dem zugeklappten Aufklapper mit.**
   Sobald die Übersicht keine Fachhandels-Zeile enthält, die Vollansicht aber
   eine, stand der Leser vor einer leeren Tabelle mit Kopfzeile — genau der
   Fall, den `.gr-v-leer` abfangen soll.
5. **Drei falsche Zahlen auf der ausgelieferten Seite**: „153 Preispunkte aus
   348 Listungen" (gezeichnet wurden 339), der Prüfbericht zeigte die Zahl der
   **Befunde** statt der **Listungen**, und „57 weitere Modelle … stehen in
   der Tabelle darunter" war doppelt falsch (es sind Angebote, und sie stehen
   nur im CSV-Export).

**Und beim Gegenlesen der fertigen Seite fiel eine sechste auf, die kein
Review gemeldet hatte:** „**62 Geräte im Vergleich**" bei 59 beobachteten —
eine Zeile ist eine (Modell, Speicher)-Kombination, es sind 41 Geräte.
Dieselbe Fehlerklasse wie die 267, nur eine Sektion weiter. Der Test dagegen
prüft jetzt **die gerenderte Seite** statt zweier Funktionen, und seine
Fixture ist so gebaut, dass sie den Fall auslösen **kann** — gegengeprüft:
ohne die Korrektur fällt er durch.

## 6. Gegenprobe an der Quelle

Drei Zeilen der Vergleichstabelle gegen ihre Quell-URL geprüft:

| Zeile | Quelle sagt |
|---|---|
| o2 · Pixel 10 Pro 128 GB · 793,00 € | wörtlich `"(Gesamtpreis Gerät: 793,00 €)"`, Kategorie `hw-only_smartphone` |
| o2 · Galaxy S26 FE 128 GB · 667,00 € | `oneoff_cost 7,0 + 24 × 27,50 = 667,00` |
| Vodafone · Pixel 10 Pro 128 GB · 1099,90 € | `prices.hardware.priceByType.rate.onetime.gross = 1099.9` aus der eigenen Schnittstelle |

---

## 7. Offen

1. **Die rotierten Achsenbeschriftungen sind geblieben** — 54 statt 114, und
   nicht mehr in einem 200-px-Buchstabenstreifen. Das ist Geometrie, kein
   Versäumnis: ein waagerechter Modellname braucht rund 90 px, die
   Zeichenfläche gibt 1080 px her, also passen **zwölf Bänder insgesamt**,
   nicht zwölf je Spalte. Wer die Vorgabe „keine rotierten Achsenlabels"
   wörtlich will, entscheidet damit, dass die Grafik zwei Geräte je
   Hersteller zeigt — eine Produktentscheidung, keine Codezeile. Die Schrift
   ist 10 px, nicht darunter. **Die Punktform erfüllt das Kriterium
   inzwischen** (68 % bzw. 79 % beschriftet).
2. **„pistachio" und „pistachio bk" sind nicht geklärt.** Zwei o2-URLs,
   144 € Abstand, beide `hw-only`. Ob „bk" eine Farbe, ein Bündel oder ein
   Katalogfehler ist, sagt die Quelle nicht. Der Prüfer meldet den Fall auf
   der Quellenseite, statt dass der Vergleich blind das Minimum nimmt.
3. **W4 (Telekom, Ceconomy, expert, 1&1) ist nicht angefasst** — der Auftrag
   stellt ihn hinter W1–W3, und die stehen erst seit dieser Sitzung.
4. **Die zwei falsch gespeicherten o2-Zustände stehen bis zum nächsten
   nächtlichen Lauf so in `geraete_db.json`.** Sie sind aus Vergleich und
   Grafik draußen (zweifach: Zustandsprüfung und Doppelpreis-Netz), und der
   nächste Crawl schreibt sie richtig. **Danach nachsehen**, ob die
   Prüfbericht-Zeile `zustand_veraltet` auf 0 fällt.
5. **`geraete_katalog.yaml` trägt keine Baureihe.** `serie_aus_modell()`
   liest sie aus dem Modellnamen — 20 Fälle im Test, einschließlich der
   Rückfälle (führende Ziffer, kein Ziffernteil, Bindestrich). Ein Name ohne
   Ziffer ist seine eigene Reihe; wenn die Generationenzahl einmal springt,
   ist das die Stelle.
6. **Die Seite springt beim Umschalten Bänder↔Punkte um 360 px.** Das ist
   der Preis dafür, dass die Standardansicht nicht 360 px leere Fläche trägt;
   der häufigere Schalter (Hersteller↔Anbieter) springt nicht. Falls es
   stört, ist die Stellschraube die Höhensynchronisierung in
   `geraete_view._flaechen`.
7. **Nothing Phone (3) und (4a) gelten als zwei Jahrgänge derselben
   Baureihe.** Bei Nothing markiert das „a" eine Preisklasse, keinen
   Jahrgang. Folgenlos, solange der Generationen-Filter nicht Standard ist;
   wer ihn einschaltet, sieht hier zuerst nach.
