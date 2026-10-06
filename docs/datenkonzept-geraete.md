# Datenkonzept Geräteradar, Fassung 2

Stand 6. Oktober 2026, Code-Stand `d996e23`. Von Antonio freigegeben am 6. Oktober 2026. Umsetzung in der Reihenfolge von Abschnitt 13; Entscheidungen aus Abschnitt 14 nach Empfehlung (36er-Ansicht mit 36 Tarifmonaten, Aktionspreise als Preisphase, Boni nie, Amazon weglassen).

## 0. Was sich gegenüber Fassung 1 ändert

- **Ein Klick-Crawler für alle Anbieter (Abschnitt 8).** Statt je Anbieter eigener Wege zu den Zahlen klickt eine Maschine auf der Anbieterseite jede Kombination aus Speicher, Tarif und Laufzeit durch und liest danach die Preiszusammenfassung. Je Anbieter gibt es nur eine Klick-Karte. Ein Job je Anbieter, parallel.
- **Laufzeiten werden getrennt (Abschnitt 5).** Der Laufzeit-Umschalter existiert schon, blendet aber nur Zeilen aus. Sieger, Δ, Spanne und Grafik nehmen weiter das günstigste Bündel über alle Laufzeiten, und das Tor `gleicher_horizont` prüft die Rechenmonate statt der Ratenlaufzeit. Die sind bei getrennter Preisform immer 24, also gilt jedes 36-Raten-Bündel von o2, congstar, Vodafone und Telekom als „24“. Nur 1&1 fällt als „andere Laufzeit“ heraus.
- **Fertiger Crawler: gibt es nicht (Abschnitt 6).** Der Klick-Crawler wird aus fertigen Teilen gebaut, kein Umzug auf ein Framework.
- **Quellen korrigiert (Abschnitt 7).** Hauptquelle ist allein die Anbieterseite. TARIFFUXX ist nicht die einzige API, und ihre AGB verbieten das Umgestalten der Angebote. Die MediaMarkt-Sperre ist nicht belegt. Neu: Otto und notebooksbilliger als Barpreis-Feeds.
- **Aktionspreis ist kein Rabatt (Regel 3).** Ein Aktionspreis wird Preisphase mit Dauer, Boni mit Antrag bleiben draußen.
- **Neu: Abnahme (Abschnitt 11).** Was „alle Werte stimmen“ prüfbar heißt.

## 1. Ergebnis in drei Sätzen

Die Rechnung stimmt (5.401 von 5.401 Nachrechnungen gleich), falsch sind die Posten: abgeleitete statt gemessene Preise, Listen- gegen Aktionspreis, abgelaufene Aktionen, falsche Beleglinks, veraltete Anbieter. Dazu vergleicht die Seite Finanzierungen über 24 und 36 Monate miteinander, weil Sieger, Δ und Grafik die Laufzeit nicht beachten. Für die Beispielseite heißt das: die Kernaussage „o2 241,05 € unter Vodafone“ ist nicht belegt und kann sich mit den heute sichtbaren Preisen umdrehen.

## 2. Beispielseite iPhone 17 Pro 256 GB, Band XS, Zeile für Zeile

| Zeile auf der Seite | Befund | Ursache |
|---|---|---|
| o2, O2 Mobile S, 1.714,75 € | Tarifpreis 14,99 € nicht gemessen, sondern Monatssumme der Unlimited-M-Plus-Seite minus Geräterate. o2s Tarifseite nennt 19,99 €; damit 1.834,75 €. Geräterate 54,50 € heute nicht prüfbar (Rechner nur per JavaScript). Anschluss 39,99 € stimmt. | Herleitung (`o2.py:592`) |
| o2, Beleglink | Zeigt Farbe silber, 36 Raten, Tarif Unlimited M Plus, belegt keinen angezeigten Wert. Systemweit falsch bei 1.730 von 1.790 o2-Bündeln. | Zuordnung (`o2.py:647`, `:696`, `:542`) |
| Vodafone, Mobil XS, 1.955,80 € (Referenz) | Gerechnet mit 31,95 €. Die Seite zeigt 31,95 € Standard und 23,95 € Online-Angebot; mit Angebot 1.763,80 €. Volumen mit Smartphone laut Tarifseite 25 GB, nicht 15 GB. Anschluss 0 € ist eine Online-Aktion, der Rechtstext nennt 39,99 €; alle 2.590 Vodafone-Bündel haben 0 €. Gleiche Summe bei 12, 24 und 36 Raten. | Extraktion (`withoutDiscounts`), Regel 11 |
| Kernzahl „241,05 € o2 unter Vodafone“ | Beruht auf den zwei ungeprüften Werten oben. Mit 19,99 € bei o2 und 23,95 € bei Vodafone wäre o2 rund 71 € teurer. | Folge |
| 1&1 Unlimited on demand S, 1.839,54 € | Keine Gerätezuzahlung erfasst, obwohl dasselbe Gerät im ANF S 360 € kostet; gilt trotzdem als belastbar. 10 GB im Band 15 GB. 36 Monate Bündelpreis (Tarif inklusive), während die anderen nur 24 Tarifmonate rechnen. | Herleitung (`einsundeins.py:865`), Rechnung (`tco_model.py:877-889`) |
| 1&1 All-Net-Flat S, 2.019,54 € | 44,99 €/Monat bestätigt; 360 € Zuzahlung, 36 Monate und 10 GB stehen nicht im ausgelieferten HTML. | nicht prüfbar |
| congstar Allnet Flat XS, 1.459 € | Stand 28.09. Anschluss mit 0 € gerechnet, Aktion endete am 29.09., heute 15 €. Seite zeigt heute nur 512 GB. Trade-in 324 € (24 Mon.) gegen 234 € (36 Mon.) widersprüchlich. Platzhalter „gültig bis 30.12.2050“. | veraltet (`congstar.py:480`) |
| congstar Allnet Flat XS Flex, 1.585 € | Anschluss heute 35 € statt 0 €. | veraltet |
| Telekom MagentaMobil XS, 1.926,95 €, „24 Mon.“ | Werte vom 15.09., Abruf scheitert seit 23.09. Erfasst sind nur 36-Raten-Bündel; „24“ ist der Rechenzeitraum (24 Tarifmonate plus alle 36 Raten), nicht die Finanzierung. „Gerät ohne Vertrag 1.197 €“ ist eine Ratensumme; Telekom nennt 1.199 €. | Sammler defekt, Beschriftung |
| Spalte „Gerät ohne Vertrag“ bei o2 und congstar | 1.315 € und 1.099 € sind Ratensummen, kein Barpreis; congstars 1.099 € enthält einen tarifgebundenen Rabatt. | Darstellung |
| Saturn 1.179 € | stimmt. MediaMarkt 1.179 €, Otto ab 1.169,99 €, Apple 1.299 € fehlen. | Abdeckung |
| Verlaufsgrafik | 1&1-Linie (36 Monate) auf der 24-Monats-Achse; Beschriftung „Telekom“ steht neben der 1&1-Linie. | Darstellung |

## 3. Systemweite Fehler (alle 6.017 Bündel)

| Befund | Umfang | Art |
|---|---|---|
| Sieger, Spanne und Grafik nehmen das günstigste Bündel über alle Ratenlaufzeiten; das Tor prüft `leitzahl_monate` (bei getrennter Preisform immer 24) statt der Ratenlaufzeit | alle Modelle; laut Bestandsauswertung in 32 Paaren (Modell, Band) aus 20 Modellen ist der Sieger ein 36-Raten-Bündel | Rechnung |
| „Günstigstes Bündel“ und Spanne mischen 36- und 24-Monats-Summen | 8 Modelle mit falschem Sieger, 14 mit falscher Spannengrenze | Rechnung |
| `tarif_bindung_monate` wird nie gespeichert | 6.017 von 6.017 leer | Erfassung |
| Ratenlaufzeiten unvollständig: Telekom nur 36 erfasst, bietet 6, 12, 24, 36 an. 1&1 nur 36, passt zum Modell „24+12“, prüfen | 45 Telekom, 456 1&1 | Erfassungslücke (Regel 11) |
| 1&1-Bündel aus dem Tarifraster ohne Gerätezuzahlung, trotzdem „belastbar“; im Mittel fehlen 376 €, höchstens 990 € | 381 Sätze, 7 von 8 1&1-Siegern | Rechnung |
| o2-Tarifpreis abgeleitet statt gemessen; 660 davon unter dem SIM-only-Preis desselben Tarifs | 1.590 | Herleitung |
| o2-Beleglink auf andere Variante, Ratenzahl oder Tarif | 1.730 von 1.790 | Zuordnung |
| Telekom liefert seit 15.09. nichts; „Barpreis“ ist eine 36-Monats-Ratensumme | 45 Bündel, 10 Listungen | veraltet |
| Telekom-Tarife „mit Smartphone“ kosten je Gerätekategorie 10 bis 40 € mehr; ob der Sammler die richtige Stufe liest, ist ungeprüft | 45 | Extraktion, prüfen |
| congstar: abgelaufene Aktionen bleiben im Preis, nur der Hinweis verschwindet | 64 | veraltet |
| Tarifband nach nächstem Vodafone-Volumen, auch nach unten (1&1 10 GB → XS, Telekom 5 GB → XS) | 20 von 43 Tarifen, 13 nach unten | Zuordnung |
| Vodafone: Anschluss überall 0 €, Tarif überall genau 2 € über dem Pflichtblatt | 2.590 | Extraktion, prüfen |
| Rechenweg-Panel: 1&1 als „Kosten über 24 Monate“, englische Monatsnamen | 25 bzw. 215 Stellen | Darstellung |
| Abdeckung: Bündel nur von fünf Netzbetreibern; MediaMarkt, Otto fehlen, freenet nur Barpreise | — | Abdeckung |

Gut gelöst ist bereits: robots.txt mit Crawl-delay und Visit-time, Bündel älter als drei Tage nicht in Sieger und Δ, Trade-in nie eingerechnet, fehlende Posten als Lücke statt Null, Ratenlaufzeit steht in der Bündel-ID.

## 4. Zielbild: fünf Regeln

1. **Nur gemessene Werte zählen.** Ein Wert, der nicht nach dem Klick auf genau diese Variante (Gerät, Speicher, Tarif, Ratenlaufzeit) auf der Anbieterseite stand, ist eine Schätzung und geht nie in Sieger, Δ oder Kernzahl ein.
2. **Jeder Wert hat einen Beleg.** Jede Zahl trägt eine `beleg_id`: Screenshot nach dem Klick, mitgeschnittene Antwort, Zeitpunkt, Adresse. Der Beleglink führt zu genau der gemessenen Variante.
3. **Gerechnet wird der Preis, den die Bestellstrecke heute verlangt.** Ein Aktionspreis ist eine Preisphase mit Dauer („23,95 € für 24 Monate, danach 31,95 €“). Boni, die man beantragen oder an Bedingungen knüpfen muss (Cashback, Trade-in, Wechselbonus), gehen nie ein. Endet eine Aktion, ist der Datensatz veraltet, bis er neu gemessen ist.
4. **Nichts Unplausibles wird veröffentlicht.** Prüfregeln vor jeder Veröffentlichung; was durchfällt, erscheint als benannte Lücke.
5. **Verglichen wird nur gleiche Finanzierung.** Sieger, Δ, Spanne und Grafik gelten je Ratenlaufzeit (12, 24, 36) und über denselben Zeitraum. 24 Raten werden nie gegen 36 gestellt.

## 5. Laufzeiten 12, 24 und 36 trennen

### 5.1 Wie die Anbieter finanzieren

| Anbieter | Ratenlaufzeiten | Tarifbindung | Vertragsform | Nach Monat 24 | Erfasst |
|---|---|---|---|---|---|
| Telekom | 6, 12, 24, 36 | 24 | Ratenkauf getrennt vom Tarif | Raten laufen weiter, vorzeitig ablösen nicht möglich | nur 36 |
| Vodafone | 12, 24, 36 (seit 23.04.2025) | 24, Raten nur mit Tarif | getrennte Ratenvereinbarung (Openbank/Zinia) | Raten laufen weiter; Ratenrabatt gilt, solange Raten laufen; GigaMobil-Aktion nur 24 Monate | 12, 24, 36 |
| o2 | 24, 36 | 24 oder monatlich | „my Handy“, getrennt | Raten laufen weiter; Rabatte aus dem Handykauf gelten so lange wie die Raten | 24, 36 |
| 1&1 | „24+12“ | 24 kündbar, Vertrag 36 | ein Vertrag, ein Monatsbetrag | Kündigung nach 24 kostet eine Einmalzahlung je Gerät (Höhe für das iPhone unbelegt) | nur 36 |
| congstar | 24 bis 36 | 24 oder Flex | Ratenkauf getrennt (AGB 18.03.2026) | Raten laufen weiter (aus den AGB abgeleitet) | 24, 36 |
| freenet | Geräteanteil im Grundpreis, 24 | 24 | ein Vertrag | ob der Geräteanteil nach 24 wegfällt: unbelegt | keine Bündel |

Rechtlich: § 56 TKG begrenzt die Tarifbindung auf 24 Monate; ob ein getrennter 36-Monats-Ratenkauf beim selben Anbieter als Paket nach § 66 TKG ebenfalls darunter fällt, ist nicht entschieden. Die Anbieter lösen es so, dass der Tarif nach 24 Monaten kündbar ist und nur die Raten weiterlaufen.

### 5.2 Was die Seite heute macht

| Stelle | Verhalten |
|---|---|
| Große Zahl je Zeile | `tco_24` (`geraete_tco_karten.py:693, 747`): Tarif × 24 + alle Raten + Einmalkosten. Bei 1&1 Bündelbetrag × 36 (`tco_model.py:877-889`). |
| Auswahl je Zeile | eine Karte je (Anbieter, Tarif, Ratenlaufzeit); `laufzeit_wahl` zeigt die passende, bei Gleichstand die kürzere (`geraete_tco_karten.py:1342-1382`) |
| Sieger, Antwortsatz | günstigste Karte je Anbieter über alle Laufzeiten (`geraete_zeitreihe.py:240-266, 554-588`) |
| Δ je Zeile | Referenz ist die günstigste Vodafone-Karte über alle Bänder und Laufzeiten (`geraete_tco_karten.py:1503-1518`) |
| Tor | `gleicher_horizont` vergleicht `leitzahl_monate` (`geraete_tco_karten.py:1173-1192`, `tco_model.py:730-744`) |
| Grafik | je Tag kleinster Wert je Anbieter, bei Gleichstand kürzere Laufzeit (`geraete_zeitreihe.py:1116-1166`) |
| Umschalter | `.gr-bnd-lz` mit „alle“ (`_geraete_buendel.html.j2:421-430`), `laufzeitWahl` in `templates/app.js:1635-1679`: blendet nur Zeilen aus, kein URL-Parameter |
| `tco_bindung` | rechnet die längere der beiden Laufzeiten, aber den Tarif nur über seine Bindung (`tco_model.py:1170-1178`); steht nicht auf der Seite |

### 5.3 Kernzahl je Laufzeit

Je Ratenlaufzeit N gibt es eine eigene Ansicht. Gerechnet wird über den Zeitraum H = größerer Wert aus N und Tarifbindung:

```
Kosten über H Monate = Anzahlung + Anschluss
                     + N Geräteraten
                     + Tarif in jedem Monat 1 bis H zum Preis, der in diesem Monat gilt (Preisphasen)
  bei 1&1:           = Anzahlung + Anschluss + H × Bündelbetrag
```

| Ansicht | Anbieter mit Daten heute | Zeitraum H | Tarifmonate | Raten | Unterschied zu heute |
|---|---|---|---|---|---|
| 12 Monate | Vodafone | 24 | 24 | 12 | keiner |
| 24 Monate | Vodafone, o2, congstar (Telekom fehlt) | 24 | 24 | 24 | keiner |
| 36 Monate | Vodafone, o2, congstar, 1&1, Telekom | 36 | 36 | 36 | Tarif zählt 36 statt 24 Monate |

Warum der Tarif in der 36er-Ansicht 36 Monate zählt: 1&1 ist ein einziger Vertrag über 36 Monate und rechnet den Tarif ohnehin mit. Zählten die anderen nur 24 Tarifmonate, wäre 1&1 in jedem Vergleich um zwölf Monate Tarif benachteiligt. Voraussetzung sind die Tarifpreise der Monate 25 bis 36. Der Klick-Crawler liest sie aus den Preisdetails der Bestellstrecke („ab dem 25. Monat …“); bei o2 gilt der Rabatt so lange wie die Raten, bei Vodafone endet die GigaMobil-Aktion nach 24 Monaten. Nennt die Seite den Preis ab Monat 25 nicht, ist das Bündel eine Lücke und nicht im Sieger.

Zweitzahl ist Ø/Monat = Kosten ÷ H, immer mit „über H Monate“ beschriftet. Laufzeitübergreifend gibt es keinen Sieger.

**Alternative (Entscheidung 1):** Die 36er-Ansicht rechnet „Ausstieg nach 24 Monaten“: 24 Tarifmonate plus alle 36 Raten, also die heutige Zahl. Dann fehlt 1&1 so lange, bis die Einmalzahlung je Gerät gemessen ist, und die Zahl ist kein Preis für 36 Monate Mobilfunk. Empfehlung und Entscheidung: die Variante oben.

### 5.4 Seite

- Umschalter „12 | 24 | 36 Monate“ neben dem Band, Standard 24, im Link als `?laufzeit=24`. Gebaut nach dem Muster des Bandes: beim Laden lesen und gegen `erlaubt` prüfen (`app.js:1117-1133`), per `replaceState` zurückschreiben (`app.js:1750-1784`), vorgerendert je `modell::band::laufzeit` im Fragment `data/geraete-zeitreihe.html`.
- Der Umschalter steuert alles: Zeilen, Sieger, Antwortsatz, Δ, Spanne, Kacheln, Grafik, Rechenweg und Export. „alle“ zeigt die Zeilen nach Laufzeit gruppiert, ohne Sieger und ohne Δ.
- Δ zu Vodafone nur gegen die Vodafone-Karte mit gleichem Band und gleicher Laufzeit.
- Je Zeile steht „36 Raten · Tarif 24 Monate“; die große Zahl heißt „über 36 Monate“.
- Ein Anbieter ohne Bündel in dieser Laufzeit erscheint benannt: „bietet 12 Monate nicht an“ nur, wenn der Crawler die Option auf der Seite nicht gefunden hat; sonst „nicht erfasst“.
- Grafik: eine Linie je Anbieter in der gewählten Laufzeit, Achse H.

### 5.5 Datenmodell

| Feld | Inhalt | Quelle |
|---|---|---|
| `laufzeit_monate` | Ratenlaufzeit (bleibt, steht in der ID) | Klick, bestätigt durch die angezeigte Auswahl |
| `tarif_bindung_monate` | Mindestlaufzeit des Tarifs, Pflicht | Preiszusammenfassung der Bestellstrecke |
| `vertragsform` | `tarif_plus_ratenkauf`, `ein_vertrag` (1&1, freenet), `sofortkauf` | Klick-Karte des Anbieters |
| `tarif_phasen` | `[{von_monat, bis_monat, preis, beleg_id}]`, Aktion und Preis danach | Preisdetails der Bestellstrecke |
| `rabatt_gilt` | `fix_n_monate`, `solange_raten`, `solange_tarif` | Aktionsbedingungen auf der Seite |
| `einmalzahlung_bei_kuendigung` | 1&1, `[{ab_monat, betrag}]`, nur für die Alternative | Pflichtangaben auf der 1&1-Seite |
| `beleg_id`, `fundstellen` | je Posten: Stelle im sichtbaren Text und JSON-Pfad der Antwort | Klick-Crawler |

Eine Funktion `kosten_ueber(buendel, monate)` in `tco_model.py` ersetzt `tco_24` und `tco_bindung` (Clean Code 1). Weitere Stellen: `aus_rohsaetze` reicht `tarif_bindung_monate` durch (`analyze/tco_buendel.py:148-165`); `gleicher_horizont`, `_band_zeilen`, `karten_je_band` (`geraete_tco_band.py:291-325`), `_messungen` und die Δ-Referenz gruppieren zuerst nach Ratenlaufzeit.

Neue Tests, die gegen den heutigen Stand rot sind: Sieger der 24er-Ansicht hat 24 Raten; ein 36-Raten-Bündel erscheint nicht in der 24er-Ansicht; `?laufzeit=36` zeigt 1&1 mit Δ statt „andere Laufzeit“; Antwortsatz und Grafikachse nennen die Laufzeit; Telekom erscheint in der 24er-Ansicht als „nicht erfasst“.

## 6. Fertige Crawler: was es gibt und was wir nehmen

**Ergebnis:** Einen fertigen Crawler für Gerät+Tarif-Bündel in Deutschland gibt es nicht. Gesucht wurde auf GitHub (Codesuche über grep.app nach Shop-Pfaden und Tarifnamen der Anbieter), GitLab, Codeberg und im Apify-Store. Gefunden wurden nur Bezahldienstleister auf Anfrage (Actowiz, spider.cloud) und fremde Projekte (Brasilien, österreichischer Handel). Der Klick-Crawler aus Abschnitt 8 wird deshalb selbst gebaut, aber aus fertigen Teilen. Das Gerüst (robots.txt, Crawl-delay, Visit-time, Fristen) hat das Repo schon, ein Umzug auf Scrapy oder Crawlee bringt nichts.

| Baustein | Aufgabe im Klick-Crawler | Lizenz, Stand | Entscheidung |
|---|---|---|---|
| Playwright | klickt die Optionen, liest die Preiszusammenfassung, schneidet die Antwort beim Klick mit (`expect_response`), macht den Screenshot, speichert HAR; gespeicherte HAR-Dateien sind Tests ohne Netz (`route_from_har`) | Apache-2.0, 1.63 (15.09.2026), schon im Repo | nehmen, Kern |
| chompjs | eingebettete JS-Objekte (`__NEXT_DATA__`, Apollo-Cache) lesen | MIT, 1.4.1 | nehmen |
| extruct | JSON-LD der Händler (Barpreise) | BSD-3, 0.18 | nehmen |
| price-parser | Preistexte → Betrag; deutsche Tausenderpunkte mit eigenen Testfällen absichern | BSD-3, 0.5.1 | nehmen |
| pydantic v2 je Datensatz, pandera je Lauf | Prüfregeln; sammelt alle Fehler eines Laufs | MIT, 2.13 bzw. 0.34 | nehmen |
| warcio, har2warc | Archiv im Standardformat WARC (ISO 28500) | Apache-2.0 | später; Start mit HAR, Screenshot, Manifest |
| changedetection.io | Strukturwächter | Apache-2.0 | nein: braucht einen dauerhaft laufenden Server |
| Scrapy mit scrapy-playwright | Gerüst | BSD-3 | nein: Gerüst vorhanden; `ROBOTSTXT_OBEY` ist global aus, Browser-Anfragen laufen an der robots-Prüfung vorbei |
| Crawlee, Crawl4AI, Scrapling | Gerüst | Apache/BSD | nein: Tarnfunktionen ab Werk an oder eingebaut |
| Firecrawl | Scrape-API | AGPL | nein: selbst gehostet ohne Screenshots und Seitenaktionen, Cloud weicht auf Proxys aus |
| browser-use, ScrapeGraphAI | KI klickt bzw. liest | MIT | nein im Tageslauf: nicht jedes Mal dasselbe Ergebnis, kostet; höchstens einmal zum Entwurf einer Klick-Karte |
| Zyte API, Apify, Bright Data | fertige Scraper | kostenpflichtig | nein: kostenpflichtig, Residential-Proxys |

**Diese Schalter bleiben aus, falls eines der Werkzeuge doch genutzt wird** (sonst Verstoß gegen CLAUDE.md Regel 4): Crawl4AI `enable_stealth`, `magic`, `simulate_user`, `override_navigator`, `UndetectedAdapter`, Proxy-Liste mit Eskalation (`check_robots_txt` auf True); Crawlee Fingerprints und `ImpitHttpClient`; Scrapling `StealthyFetcher`, `solve_cloudflare`, `stealthy_headers`, `impersonate`, `google_search`; Firecrawl `proxy: auto`; Residential-Proxys in changedetection.io.

## 7. Datenquellen

Hauptquelle ist allein die Anbieterseite, gelesen vom Klick-Crawler. Alles andere ist Gegenprobe oder Barpreis-Anker.

| Quelle | Liefert | Kosten, Bedingungen | Eignung |
|---|---|---|---|
| Anbieterseiten (Bestellstrecke) | Bündel, Tarife, Aktionen, Preis nach der Aktion | frei | Hauptquelle |
| TARIFFUXX Partner-API | Tarif- und Bündeldaten; Feldliste nicht öffentlich | frei, nur für Gewerbe, kein Anspruch auf Zulassung; Weitergabe verboten, Angebote dürfen nicht umgestaltet werden; Anbieter ohne Provisionsvertrag fehlen; Pflege werktags | Gegenprobe, nach schriftlicher Klärung |
| communicationAds | Rechner für Tarif-Geräte-Bündel, „Rohdaten“-Schnittstelle; Feldumfang unbelegt; täglich gepflegt | frei für Publisher | Gegenprobe, Felder vorher klären |
| Awin: Otto, notebooksbilliger, Samsung | Produktfeeds mit Barpreis | frei, Partnerschaft je Händler | Barpreis-Anker und Gegenprobe |
| Produktinformationsblätter (Pflichtdokument) | Listenpreis, Mindestlaufzeit, Volumen; keine Gerätepreise, keine Aktionen; bei o2 per robots.txt gesperrt | frei | höchstens Gegenprobe |
| Awin Telco-Feed | Felder für Laufzeit, Monatspreis, Einmalpreis | — | nein: nur britische Händler, Vodafone DE nimmt keine neuen Partner |
| teltarif.de | einbindbare Tarif- und Gerätedatenbank | Konditionen auf Anfrage | offen |
| CHECK24, Verivox, Tarifcheck | nur Rechner, keine Rohdaten | — | nein |
| idealo, geizhals, billiger.de | keine Lese-API; robots.txt sperrt Kategorie- und Angebotspfade | — | nein |
| Amazon | PA-API seit 15.05.2026 aus; Nachfolger braucht 10 Verkäufe in 30 Tagen; Keepa ab 49 €/Monat | kostenpflichtig | nein (Entscheidung 5) |
| MediaMarkt | Sperre für Rechenzentrums-IPs nicht belegt (Kategorieseite lädt); Affiliate DE geschlossen | frei | prüfen, über die eigene robots-Schicht |
| Apple, Samsung Store | UVP | frei | Plausibilitätsanker |
| Diffbot | Seitenextraktion, 10.000 Credits/Monat, 5 Anfragen/min | frei bis Grenze | Gegenprobe |

## 8. Ein Klick-Crawler für alle Anbieter

Eine Maschine für alle Anbieter. Je Anbieter gibt es nur eine **Klick-Karte** (YAML unter `config/`): welche Knöpfe Speicher, Tarif und Laufzeit wählen, wo die Preiszusammenfassung steht, welche Antwort beim Klick mitgeschnitten wird, welcher Kanarienwert gilt. Ändert ein Anbieter seine Seite, ändert sich nur die Karte. Eine KI darf einen Kartenentwurf vorschlagen; im Tageslauf klickt sie nicht.

**Ablauf je Gerät und Anbieter:**

1. Produktseite öffnen (Adresse aus Katalog bzw. Einstiegen in `geraete_quellen.yaml`).
2. Alle Optionen lesen, die die Seite selbst anbietet: Speicher, Tarif, Ratenlaufzeit. Farben ändern den Preis meist nicht; je Modell einmal prüfen, sonst Standardfarbe.
3. Jede Kombination anklicken. Nach jedem Klick:
   - sichtbare Preiszusammenfassung lesen: Anzahlung, Rate, Ratenzahl, Tarifpreis mit Phasen („ab dem 25. Monat …“), Tarifbindung, Anschluss, Volumen;
   - die Antwort mitschneiden, die die Seite beim Klick lädt, und dieselben Werte daraus lesen;
   - Screenshot des Preisbereichs.
4. Ein Wert gilt nur, wenn sichtbarer Text und Antwort übereinstimmen und die Seite die gewählte Variante anzeigt (Echo). Sonst Befund statt Wert.
5. Bietet die Seite eine Option nicht an (etwa 12 Monate), wird das als „nicht angeboten“ gespeichert. Findet der Crawler die Knöpfe nicht, heißt es „nicht erfasst“.

**Menge:** je Gerät und Anbieter grob 40 bis 110 Kombinationen (iPhone 17 Pro: 3 Speicher × 6 bis 12 Tarife × 2 bis 3 Laufzeiten).

**Betrieb:**

- Ein Job je Anbieter, parallel (Matrix in `geraete.yml`), jeder mit eigenen 6 Stunden. Ein letzter Job führt die Ergebnisse zusammen und committet einmal. Actions-Minuten sind für das öffentliche Repo kostenlos.
- Die eigentliche Grenze ist der Abrufabstand je Domain (Crawl-delay, `rate_limit_sekunden`); bei 10 Sekunden sind es höchstens rund 8.600 Abrufe am Tag. Reicht das nicht für den ganzen Katalog, rotiert der Job: jede Variante spätestens alle drei Tage (Frischegrenze).
- robots.txt gilt für jede Adresse, die beim Klicken geladen wird; Antworten von gesperrten Pfaden werden verworfen (Vodafone `/privat/json/`, freenet `/api/` und `/shop/rest/`, o2 `/aktionen/` und `/postpaid/`).
- Challenge oder 403: Anbieter „Abruf gestört“, keine Umgehung (Regel 4).
- Strukturwächter: Anteil gefundener Knöpfe und Felder je Lauf; ein Sprung heißt „Abruf gestört“, nicht „nichts gefunden“.
- Kein LLM im Tageslauf.

**Hinweise für die Klick-Karten:**

| Anbieter | Worauf achten |
|---|---|
| o2 | Speicher- und Laufzeitschalter liest der Sammler schon; Tarifpreis ablesen statt herleiten; Beleglink auf genau diese Variante |
| Vodafone | Online-Aktionspreis mit Dauer und Preis danach statt `withoutDiscounts`; Anschluss aus den Pflichtangaben; Volumen „mit Smartphone“ |
| 1&1 | Geräteseite je Tarif (`?chosenTariff=` ist erlaubt); Zuzahlung, Laufzeit, Volumen, Einmalzahlung bei Kündigung nach 24 |
| Telekom | neu aufsetzen; alle Ratenlaufzeiten; Aufpreisstufe „mit Smartphone“ |
| congstar | Aktionsende; 256 GB; 24 und 36; Flex getrennt |
| freenet | Geräteanteil im Grundpreis als `ein_vertrag`; robots-Sperren beachten |

## 9. Prüfregeln vor jeder Veröffentlichung

Ergebnis je Datensatz: gültig, Quarantäne oder veraltet.

1. Anzahlung + Rate × Ratenzahl = Gerätesumme auf der Seite.
2. Gerätesumme zwischen 85 % und 130 % der UVP.
3. Tarif mit Gerät ≥ SIM-only-Preis desselben Tarifs (trifft heute 846 o2-Bündel).
4. Volumen passt zu Tarifname und Band; nie in ein Band mit mehr Volumen.
5. Preis steigt mit dem Speicher beim selben Anbieter, Tarif und Laufzeit.
6. Ratenlaufzeit ist 6, 12, 24 oder 36 und kommt aus dem Echo der Seite.
7. Tarifbindung vorhanden, sonst Lücke.
8. Preisphasen decken alle H Monate ab, sonst Lücke.
9. Sichtbarer Text und mitgeschnittene Antwort stimmen überein, sonst Befund.
10. Aktion mit Enddatum vor heute: veraltet. Platzhalter wie 2050 heißen „unbefristet“.
11. Ausreißer gegen den Vortag (mehr als 15 %) erst nach zweitem Abruf.
12. Gleicher Wert bei allen Bündeln eines Anbieters ist eine Erfassungslücke (CLAUDE.md Regel 11). Das gilt auch für Laufzeiten: fehlt eine Laufzeit bei allen Geräten eines Anbieters, ist das zuerst „nicht erfasst“.
13. Beleglink enthält dieselbe Variante.
14. Pflichtfelder vollständig (Zuzahlung, Rate, Ratenlaufzeit, Tarif, Tarifbindung, Anschluss).
15. Vergleiche nur bei gleicher Ratenlaufzeit und gleichem Zeitraum H.
16. Bündel älter als drei Tage nicht im Vergleich (gibt es schon).

Umsetzung mit pydantic und pandera in pytest. Kennzahlen je Anbieter und Lauf auf der Quellen-Seite: Abdeckung (je Laufzeit), Frische, Quarantänequote, Konfliktquote, Belegquote.

## 10. Nachweis

- **Beleg je Klick**: Screenshot des Preisbereichs als WebP, mitgeschnittene Antwort (HAR, nur die Preis-Endpunkte), Manifestzeile mit `beleg_id`, Zeitpunkt UTC, Adresse, HTTP-Status, SHA-256, den gelesenen Werten und ihren Fundstellen. Manifest täglich bei freetsa.org (RFC 3161) und OpenTimestamps stempeln.
- **Ablage** im privaten Bucket (Backblaze B2, Cloudflare R2 als Spiegel), Manifest im Repo. Für die 20 bis 50 wichtigsten Seiten zusätzlich Internet Archive (höchstens 5 Aufnahmen je Adresse und Tag). Aufbewahrung: Manifest dauerhaft; 90 Tage täglich Screenshot und Antwort; jede Wertänderung dauerhaft; danach ein Wochenbeleg. Größen in der ersten Woche messen.
- Die gespeicherten HAR-Dateien sind zugleich die Regressionstests des Crawlers (`route_from_har`, ohne Netz).
- Auf der Seite öffnet „Beleg“ eine interne Belegansicht mit Datum, Screenshot und Hash. Öffentlich stehen nur Zahl, Datum und Link zum Anbieter.

## 11. Abnahme: wann „die Werte stimmen“

Dass jede Zahl stimmt, lässt sich nicht statistisch beweisen. Prüfbar ist: Jede veröffentlichte Zahl stand zu einem belegten Zeitpunkt nach dem Klick auf genau diese Variante auf der Anbieterseite, und was sich nicht belegen lässt, steht nicht da. Abgenommen ist erst, wenn alle Punkte grün sind:

| Prüfung | Wie | Grenze |
|---|---|---|
| Jede Zahl hat einen Beleg | Seitenprüfung: kein Betrag in Sieger, Δ, Kernzahl oder Zeile ohne `beleg_id` mit Status gültig | 100 % |
| Wörtlich im Beleg | Test liest den archivierten Beleg neu und findet jeden Posten an seiner Fundstelle | 100 % |
| Variante stimmt | Echo der Seite gleich Datensatz; Beleglink enthält die Variante | 100 % |
| Laufzeit getrennt | kein Vergleich über Ratenlaufzeit oder Zeitraum hinweg; Tests aus 5.5 grün | 100 % |
| Stichprobe Mensch | je Anbieter feste Goldliste mit 10 Varianten (darunter die Beispielseite) plus 10 bis 20 Zufallswerte täglich, gegen die Anbieterseite mit Screenshot | 30 fehlerfreie Proben je Anbieter in Folge; jeder Fehler wird Regressionstest |
| Gegenprobe | wöchentlich gegen TARIFFUXX, communicationAds oder Diffbot, falls Zugang | Abweichungen geklärt oder als Lücke gezeigt |
| Beispielseite | iPhone 17 Pro 256 GB, Band XS, in jeder Laufzeit-Ansicht Zeile für Zeile am selben Tag gegen die Anbieterseiten abgeglichen, Protokoll unter `docs/` | alle Zeilen stimmen oder sind benannte Lücke |
| Optik | `pruefe_portal.py` und Screenshots 1440 px und 390 px angesehen | wie CLAUDE.md |

30 fehlerfreie Proben je Anbieter heißen: Fehlerquote mit 95 % Sicherheit unter 10 %. Restrisiko ist eine falsch gewählte Variante, die Echo und Fundstelle trotzdem besteht; die Stichprobe deckt genau diesen Fall ab.

## 12. Rechtliche Einordnung (keine Rechtsberatung)

- Preise auslesen ist grundsätzlich zulässig (BGH I ZR 224/12); die Grenze ist das Umgehen technischer Schutzmaßnahmen (CLAUDE.md Regel 4). robots.txt ist nach RFC 9309 keine Zugangsberechtigung, wird hier aber als Regel befolgt.
- Datenbankrecht (§ 87b UrhG): Risiko steigt mit Vollständigkeit und Öffentlichkeit; das vollständige Durchklicken aller Varianten erhöht es. Eine interne Seite ist weniger heikel.
- Text und Data Mining (§ 44b UrhG): maschinenlesbare Vorbehalte beachten; das Archiv braucht den Zweck „Nachweis“ und feste Löschfristen.
- Screenshots nur im privaten Bucket.
- TARIFFUXX: Die AGB verbieten Weitergabe und Umgestaltung der Angebote; ob eine eigene Gesamtkostenrechnung daraus erlaubt ist, vorher schriftlich klären. Anmeldung nur für Gewerbe.
- Offen: Die Website ist öffentlich. Für eine Vodafone-interne Nutzung wäre ein Zugangsschutz der sauberere Weg.

## 13. Umsetzung: Reihenfolge und Aufwand

Eine Sitzung = ein Paket mit Test, Prüfleiter und Commit.

| Schritt | Inhalt | Aufwand |
|---|---|---|
| 1. Notbremse | Nur gemessene, vollständige Werte in Sieger, Δ und Kernzahl; abgeleitete 1&1- und o2-Sätze als Schätzung aus Vergleichen raus; abgelaufene Aktion macht den Satz veraltet; Etiketten und Monatsnamen korrigiert | 1–2 |
| 2. Laufzeit in der Rechnung | `kosten_ueber`, Gruppierung nach Ratenlaufzeit in Sieger, Δ, Spanne, Grafik, Export; Tor auf Ratenlaufzeit; Tests aus 5.5 | 2 |
| 3. Laufzeit auf der Seite | Umschalter steuert alles, `?laufzeit=`, „nicht angeboten“ gegen „nicht erfasst“, Screenshots | 1–2 |
| 4. Klick-Crawler-Gerüst | Maschine, Format der Klick-Karte, Mitschnitt, Echo, Screenshot, ein Job je Anbieter, Rotation | 2–3 |
| 5. Klick-Karten je Anbieter | o2, Vodafone, 1&1, Telekom, congstar, freenet; je Karte Kanarienwert und Strukturwächter | 5–6 |
| 6. Beleg-Archiv | `beleg_id`, Fundstellen, Manifest, Stempel, Bucket, Belegansicht | 2 |
| 7. Prüfregeln | die 16 Regeln, Quarantäne, Kennzahlen | 2 |
| 8. Händler und Anker | Otto, Apple, Samsung, MediaMarkt prüfen | 1–2 |
| 9. Gegenprobe und Abnahme | Goldliste, tägliche Stichprobe, wöchentlicher Abgleich, Protokoll Beispielseite | 1–2 |

Insgesamt 17 bis 23 Sitzungen. Nach Schritt 3 vergleicht die Seite nur noch gleiche Finanzierung, zeigt aber Lücken; nach Schritt 5 ist sie für die Netzbetreiber vollständig; abgenommen nach Schritt 9.

## 14. Entscheidungen

1. **Kernzahl der 36er-Ansicht:** 36 Tarifmonate (entschieden nach Empfehlung, 1&1 vergleichbar).
2. **Aktionspreise als Preisphase einrechnen:** ja; Boni mit Antrag nie. Ändert Regel 3 in `tco_model.py`.
3. **Backblaze-B2-Konto** anlegen, Schlüssel als GitHub-Secret (kostenlos): nur Antonio, offen.
4. **TARIFFUXX und communicationAds:** Anmeldung braucht ein Gewerbe oder eine Firma; als Vodafone-Projekt vorher intern klären, wer sich anmeldet: nur Antonio, offen.
5. **Amazon** weglassen (entschieden nach Empfehlung).
6. **Zugangsschutz** für die Website, falls sie intern bleibt: nur Antonio, offen.

## 15. Offen und unbelegt

- Wie die Bestellstrecken von Vodafone, 1&1 und Telekom die Optionen technisch umschalten (je Anbieter beim Bau der Klick-Karte ermitteln).
- Ob jede Bestellstrecke den Tarifpreis ab Monat 25 nennt.
- Höhe der 1&1-Einmalzahlung bei Kündigung nach 24 Monaten für Smartphones.
- Ob der Telekom-Aufpreis „mit Smartphone“ nach 24 Monaten endet; Ratenlaufzeiten bei freenet und otelo.
- Feldumfang der Schnittstellen von TARIFFUXX und communicationAds.
- Ob § 66 TKG getrennte 36-Monats-Ratenkäufe erfasst.

## Quellen

Finanzierung: [Telekom Ratenkauf](https://www.telekom.de/shop/geraete/ratenkauf) · [Vodafone Ratenzahlung](https://www.vodafone.de/privat/handys-tablets-tarife/smartphone-ratenzahlung.html) · [Vodafone-Hilfe](https://www.vodafone.de/hilfe/geraet-in-raten-zahlen.html) · [o2 my Handy](https://www.o2online.de/vorteile/o2-myhandy/) · [1&1 „24+12“, Pressemitteilung](https://unternehmen.1und1.de/_Resources/Corporate/Persistent/0c81b17a6da0bcc058559b690dececd0d7c4009f/laengerer-vertragszeitraum-von-24-12-monaten-fuer-bundles-mit-smartphone-bei-1-1-geringere-monatliche-kosten-weiterhin-volle-flexibilitaet.pdf) · [congstar AGB Ratenkauf](https://www.congstar.de/fileadmin/files_congstar/documents/AGB/AGB_Ratenkauf.pdf) · [§ 56 TKG](https://gesetze.legal/bund/tkg/56) · [§ 66 TKG](https://lexmea.de/de/gesetz/tkg/66) · [Verivox-Analyse Preis ab Monat 25](https://www.it-daily.net/?p=93059)

Datenquellen: [TARIFFUXX Partnerprogramm](https://www.tariffuxx.de/partnerprogramm) · [TARIFFUXX AGB](https://www.tariffuxx.de/partner-agb) · [TARIFFUXX Pflegezeiten](https://www.tariffuxx.de/ueber-uns/facts) · [communicationAds](https://www.communicationads.net/en-gb/aboutus/) · [Awin Telco-Feldliste](https://help.awin.com/developers/docs/telco-data-feeds-mobile-phones-standard-fields.md) · [Awin Vodafone DE](https://ui.awin.com/merchant-profile/11331) · [Awin Otto](https://ui.awin.com/merchant-profile/14336) · [Awin notebooksbilliger](https://ui.awin.com/merchant-profile/11348) · [Samsung Partner](https://www.samsung.com/de/samsung-affiliate-partner) · [Amazon Creators API](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction) · [Diffbot](https://www.diffbot.com/pricing) · [teltarif-Einbindung](https://www.teltarif.de/intern/anpassung.html) · [BNetzA zu Produktinformationsblättern](https://www.bundesnetzagentur.de/SharedDocs/Downloads/DE/Sachgebiete/Telekommunikation/Unternehmen_Institutionen/Anbieterpflichten/Kundenschutz/Transparenzma%C3%9Fnahmen/anleitung_erstellung_muster-produktinformationsblaetter.html)

Werkzeuge und Betrieb: [Playwright Netzwerk](https://playwright.dev/python/docs/network) · [Playwright HAR](https://playwright.dev/python/docs/mock#mocking-with-har-files) · [chompjs](https://github.com/Nykakin/chompjs) · [extruct](https://pypi.org/project/extruct/) · [price-parser](https://pypi.org/project/price-parser/) · [pandera](https://pandera.readthedocs.io/en/stable/) · [GitHub Actions Limits](https://docs.github.com/en/actions/reference/limits) · [scrapy-playwright](https://github.com/scrapy-plugins/scrapy-playwright/blob/main/README.md) · [Crawl4AI Parameter](https://docs.crawl4ai.com/api/parameters/) · [Crawlee Blockieren](https://crawlee.dev/python/docs/guides/avoid-blocking) · [Firecrawl Self-Host](https://docs.firecrawl.dev/contributing/self-host) · [changedetection.io](https://github.com/dgtlmoon/changedetection.io) · [WACZ](https://specs.webrecorder.net/wacz/1.1.1/) · [FreeTSA](https://www.freetsa.org/index_en.php) · [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html)
