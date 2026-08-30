# `/geraete.html` — Nachbesserung nach dem Durchklicken

**30.08.2026, abends.** Auftragsgrundlage: Antonios Befundliste „Nachbesserung
/geraete.html — an der Live-Seite durchgeklickt am 30.08.2026" (fünf Befunde,
zwei kleinere Punkte).

Stand danach: **Tests 2147 → 2166**, `pruefe_portal.py` **17 bestanden /
0 durchgefallen**. Reiterhöhen unverändert unter 3000 px
(2949 / 2893 / 2184 / 2384).

---

## Der erste Befund war kein Rechenfehler, sondern ein Satzfehler

Auf der Seite stand:

```
o2                 2454 Modelle
Vodafone           2041 Modelle
mobilcom-debitel   1018 Modelle
ALDI TALK            22 Modelle
```

Bei 59 beobachteten Geräten. Antonio: „Das ist dieselbe Fehlerklasse wie
,267 Geräte neu im Regal' — nur eine Größenordnung schlimmer."

**Die Daten waren richtig.** `portfolio_tiefe` lieferte für o2 **24
Generationen und 54 Modelle**, beide korrekt und beide unter dem Bestand. Im
HTML stand:

```html
<span class="dz-balken-n">24<span class="rubrik-zusatz">54 Modelle</span></span>
```

Zwei Inline-Elemente ohne ein Zeichen dazwischen. `.dz-balken li` teilt sich
`1fr 74px 26px` — die 26 px sind für EINE Zahl gedacht, und das
`margin-left:auto` des `rubrik-zusatz` wirkt auf ein Inline-Element außerhalb
eines Flex-Kontexts nicht. Der Browser setzte „2454 Modelle". Und die
Generationenzahl, um die es in der Sektion überhaupt geht, war damit als
eigene Zahl nirgends zu lesen.

### Warum der Abnahmetest grün blieb

`test_keine_geraetezahl_auf_der_seite_ist_groesser_als_der_bestand` liest mit

```python
text = suppe.get_text(" ", strip=True)
```

Nachgemessen:

| Aufruf | Ergebnis |
|---|---|
| `get_text()` (wie der Browser) | `'2454 Modelle'` |
| `get_text(" ", strip=True)` | `'24 54 Modelle'` |

**Der Trenner, den der Test selbst einfügt, macht genau die Fehlerklasse
unsichtbar, gegen die er gebaut war.** Dazu kam, dass sein Muster nur
`(\d+)\s+Gerät` sucht — „Modelle" stand nie unter Beobachtung.

Der neue Test `test_zwei_zahlen_nebeneinander_tragen_ein_trennzeichen` liest
ohne Trenner, also so, wie ein Browser Inline-Text zusammensetzt.

Jetzt: **`24 Generationen · 54 Modelle`**, mit eigener Rasterspalte
(`.gr-tiefe li`), sichtbarem Mittelpunkt und `white-space:nowrap`.

**Nebenbefund derselben Klasse, beim Bauen entstanden und sofort behoben:** der
neue Sortierkopf las „UNTERSCHIED %€", weil zwei Knöpfe ohne Zeichen
nebeneinander standen. Dort steht jetzt derselbe Mittelpunkt.

---

## Die übrigen Befunde

| # | Was | Wo |
|---|---|---|
| 2 | **Unter vier Messterminen kein Diagramm.** Zwei Punkte ergeben eine Gerade, und eine Gerade durch zwei Punkte sieht aus wie ein Trend. Stattdessen Tabelle plus Satz | `geraete_verlauf.DIAGRAMM_AB_TERMINEN`, `app.js` |
| 2b | **Verdeckte Linien.** Liegen zwei Linien näher als 2 % der Preisspanne, wird die obenliegende gestrichelt gezeichnet und bekommt ein Etikett an ihrem Ende — beides auf ihrer **wahren Höhe** | `app.js` |
| 2c | **„Messpunkte" und „Messtermine" sind eine Zahl.** Beide zählen Messtage, und es steht immer nur eine davon gleichzeitig da | `geraete_verlauf`, `app.js` |
| 3 | **Verfügbarkeit** aus dem Alarm-Reiter (12 von 13 Zeilen sagten „unbekannt"), im Katalog geblieben, ein Wort je Zustand | `geraete.html.j2` |
| 4 | **Wochenkarte** unter vier Wochen Vorlauf: ein Satz, keine Tabelle | `geraete_view.VORLAUF_TAGE` |
| 5 | **Kopfdatum** ist das Abrufdatum: „Preise vom 30. August 2026" | `geraete.html.j2` |
| 6 | **Spaltenköpfe sortierbar**, in beiden Tabellen | `geraete.html.j2`, `app.js` |

---

## Vier Entscheidungen, die anders ausfielen als die naheliegende

**1. Die verdeckte Linie wird NICHT verschoben.** Antonio bot drei
Möglichkeiten an („gestrichelt, versetzt oder mit Endpunkt-Etikett"). Versetzt
fällt weg: die Y-Achse gehört dem Preis, und das ist die Lehre aus der
gelöschten Positionskarte, deren Etiketten bis zu 235 px neben ihrem Punkt
standen. Zwei Preise, die 90 Cent auseinanderliegen, sollen 90 Cent
auseinanderliegen. Also gestrichelt **und** Etikett, beides auf wahrer Höhe.

Am Pixelbild nachgemessen, mit dem nachgebauten Fall (Vodafone 1099,90 unter
mobilcom-debitel 1099,00, Achse 793–1100):

| Strichmuster | rote Pixel | blaue Pixel darunter |
|---|---|---|
| `7 5` (erster Anlauf) | 1205 | 197 |
| **`4 8` plus Ring statt Punkt** | 848 | **787** |

Mit `7 5` deckte die obenliegende Linie noch 58 % der Strecke ab, und ihr
gefüllter Punkt (r = 5) verdeckte den fremden (r = 4) an genau den Stellen, an
denen man den Preis abliest. Der Punkt der obenliegenden Linie ist deshalb
jetzt ein **Ring**.

**2. Ein Messtermin ist ein TAG, unabhängig vom Raster.** Die erste Fassung
zählte nach der Rasterung — beim Galaxy S25 128 GB standen damit „3
Messtermine", obwohl an vier Tagen gemessen wurde (zwei lagen in derselben
Kalenderwoche). Der Umschalter „Wöchentlich/Monatlich" hätte so die Zahl der
Messungen verändert, und im Quartalsraster hätte jedes Gerät genau einen
Termin gehabt. **Das Raster formt die Linie, es formt nicht die Datenlage.**

**3. Drei Lagen der Wochenkarte, nicht zwei.** Die erste Fassung warf „es gibt
überhaupt keinen früheren Stand" (`ohne_vorlauf`, erster/zweiter Lauf) und
„der Vorlauf ist kurz" (`kurzer_vorlauf`) zusammen — und schaffte damit den
Satz „es gibt noch keinen früheren Stand, gegen den sich vergleichen ließe"
ab, den B7 Punkt 3 ausdrücklich verlangt. **Ein bestehender Test hat das
gemeldet**, und er hatte recht.

**4. Der Zeilendeckel wird beim Sortieren neu vergeben.** `SICHTBAR_MAX`
begrenzt die Seitenhöhe strukturell; die sichtbaren zwölf sind die ersten
zwölf **der aktuellen Ordnung**. Bliebe `gr-a-rest` an den ursprünglichen
Zeilen kleben, zeigte eine Sortierung nach Euro die zwölf größten
PROZENTwerte, untereinander nach Euro geordnet — eine Rangliste, die es nicht
gibt, und der größte Euro-Abstand stünde nicht darunter. Live nachgemessen:
nach Prozent führt Galaxy A17 (41,3 % / 90,90 €), nach Euro Pixel 10 Pro
(27,9 % / 306,90 €).

---

## Zwei bestehende Tests sind angefasst worden, beide mit Grund

1. **`tests/test_geraete_reiter_browser.py`, Fixture.** Sie lief mit einer
   LEEREN Preishistorie: jede Listung hatte genau einen Messtag, den aus
   `last_verified`. Das reichte, solange jedes gewählte Gerät ein Diagramm
   bekam — mit dem Gatter standen vier Tests vor einem Leerzustand und maßen
   nicht mehr die Grafik, die sie prüfen. Die Fixture hat jetzt **vier
   Messtage**, davon zwei bewusst in derselben Kalenderwoche (daran hängt der
   Rastertest).
2. **`test_die_tabelle_zeigt_dieselben_anbieter_wie_das_diagramm`.** Er
   verengte das Fenster auf den letzten Tag — und damit fällt die Auswahl
   unters Gatter: kein Diagramm, folglich keine Legende, gegen die sich
   vergleichen ließe. Seine Zusicherung gilt weiter, sie lautet nur in zwei
   Lagen verschieden, und er prüft jetzt **beide**: mit Diagramm nennen
   Legende und Tabelle dieselben Anbieter, ohne Diagramm bleibt die Tabelle
   stehen und folgt weiter dem Filter (nachgeprüft am Datum in der letzten
   Spalte).

Sonst wurde kein Test angefasst.

---

## Ein Fund, der nicht auf der Liste stand

Die Sätze der Wochenkarte schrieben ihre Beträge mit `f"{wert:.2f} €"`, also
**„129.00 €" mit Dezimalpunkt**, während jede Tabelle derselben Seite
„129,00 €" zeigt. Solange die Sätze neben einer Tabelle standen, ging das
unter; seit die Karte unter kurzem Vorlauf NUR aus einem Satz besteht, ist es
die erste Zahl, die dort jemand liest. `geraete_view.euro()` setzt sie jetzt,
und der Zahlenwächter liest beide Schreibweisen über `lies_preis` — an dem,
was er durchlässt, ändert die Umstellung nichts.

Ebenso gefallen: die Spalte **„Veränderung"** im Preisverlauf erscheint nur
noch, wenn wenigstens ein Wert darin steht. Am Galaxy S25 standen drei Zeilen
mit drei Gedankenstrichen untereinander — dieselbe Regel, mit der „niemand
günstiger" aus der Alarmtabelle geflogen ist.

---

## OFFEN

1. **Die Datenlage bleibt dünn, und das Gatter macht sie jetzt sichtbar.** Von
   89 wählbaren Geräten haben **71 zwei, 15 drei und 3 vier** Messtermine —
   also zeigt der Preisverlauf für die meisten Geräte weiterhin eine Tabelle
   und keinen Verlauf. Das ist die ehrliche Auskunft und kein Mangel des
   Reiters; nach etwa zwei weiteren Wochen Nachtläufen kippt es von selbst.
   **Dann ansehen, ob die Linien taugen.**
2. **Die Überlappungsregel (2 % der Preisspanne) ist an EINEM nachgebauten
   Fall gemessen**, nicht an echten Daten — im Bestand gibt es heute kein
   Gerät mit vier Messterminen UND zwei Anbietern auf gleicher Höhe. Meldet
   die Seite später auffällig viele gestrichelte Linien, ist die Schwelle zu
   weit.
3. **`VORLAUF_TAGE` (28) schaltet sich beim Lauf um den 07.09. selbst um** —
   dann ist die Preishistorie vier Wochen alt, die Wochenkarte bekommt ihre
   Tabelle zurück, und „neu im Regal" meint wieder den Markt. **Danach die
   Karte ansehen:** stehen dort plausible Zahlen, oder zählt sie weiter fast
   den ganzen Bestand als neu?
4. **Der Zeilendeckel des Katalogs (`KATALOG_SICHTBAR`) ist beim Sortieren
   dieselbe Mechanik wie in der Alarmtabelle** — er wird neu vergeben. Weil
   die Katalogzeilen keinen Aufklapper haben, war das billig; wenn dort einer
   dazukommt, muss er mitwandern (`sortiere()` in `app.js` kann das bereits).
