# Premortem Geräteseite — „September 2027: Antonio öffnet sie seit Monaten nicht (oder ärgert sich)"

Alle Zahlen am 17.09.2026 gegen HEAD `9f5235d` und den Nachtlauf-Bot-Commit `1dd48d4`
gemessen; Auftragskontext: Antonios 8 Forderungen vom 17.09. + Befund `auto-doku.md`.

**Eingangsmessungen:** Seite 1.396.222 B (sichtbarer Text ~158.430 Zeichen),
Zeitreihen-Fragment 1.132.101 B / 169 Modelle, Bündel-Fragment ~1,17 MB, „ohne Preis"
36× im Katalog; 16 Auto-Einträge + 105 iPhone-18-Bündel im Store, aber 0 Vorkommen
von iPhone 18 auf der Seite (Sichtbarkeit ab 2. Messtagen).

---

## FM 1 — Auto-Erkennung bricht still beim nächsten Launch

**Auslöser (wahrscheinlichste Kette zuerst):**
a) Telekom liefert in Actions gar nicht (HTTP-202, `letzter_lauf: 2026-09-15`) —
   für Anbieter Rang 1 ist die „Automatik" heute schon ein manueller lokaller Pfad.
b) Strukturierte Namen ändern das Schema (Vodafone `modelName` → neues Feld,
   o2 `description`-Format kippt, Bündel-Slug-Brücke `dimension59` verschwindet).
   Die E4-Schälung hängt an Wörtern; ein neuer Anhang („iPhone 19 Pro (USB-C)")
   fällt nach `geraete_unbekannt.jsonl`, die SKU bleibt stabil — still.
c) Zustand/Farbe wandert („Burgunder" 94×, „Polar" 40× heute unbekannt): kein
   Bruch, aber die Wiedererkennung über Farben verarmt.
d) Sichtbarkeit: `AUTO_SICHTBAR_AB_MESTAGEN = 2` — ein Modell ohne Bündel wird
   NIE angezeigt (12 der 16 heutigen Auto-Einträge: Watches, Tabs, AirPods).
   2027-Bild: „Das neue iPad steht nicht drin", obwohl der Store es hat.

**Frühindikator:** die drei Protokollzeilen (Auto-Anlage, Unbekannte,
Fragmentgröße): `Auto: 0` an aufeinanderfolgenden Tagen bei bekanntem Launch;
Unbekannte-Zahl springt (Basis heute 284). Heute bemerkt das nur, wer das Log liest.

**Vorbeugende Regel:** (1) Sichtbarkeitsregel auf BEIDE Wege rechnen (Bündel
ODER Listung — OFFEN 2 aus §8a), sonst bleiben Barpreis-Modelle unsichtbar.
(2) Telekom-202-Entscheidung (R3 in STRATEGY_GERAETE_TCO.md) fällt Antonios
Auftrag „nie wieder ändern" direkt — nicht vertagen. (3) Nach jedem bekannten
Launch ein Tag-2-Sichttest („iphone 19" suchen) — gehört in den Monatsrhythmus.

## FM 2 — Eine Datenquelle stirbt, und niemand merkt es

**Auslöser:** o2/Telekom/Vodafone-API ändert Nutzlast (Felder weg: `metric3`/
`metric2`-Aufteilung, `totalPrice`), oder robots.txt sperrt neu (o2-Sonderfall:
`/e-shop/` steht nur in der googlebot-Gruppe — eine Zeile mehr in `*` kaptt o2
komplett, regelkonform und ohne Fehler).

**Was die Seite dann zeigt:** „Datenstand fehlt"-Leerstand (dafür gebaut, E5)
bzw. wachsende Lücken in der Zeitreihe — Ausbleiben ist kein Fehlerzustand,
kein Test wird rot, `deploy.yml` bleibt grün.

**Frühindikator:** `geraete-quellen.html` (Fehler-/Stand-Spalte) und die
Probenregeln aus Phase S (`metric3+metric2 == monthlyPrice`, damals 66/66) —
aber nur, wenn jemand hingeschaut hat. Gesehen wird es frühestens beim
monatlichen Sichttest, das ist bis zu 30 Tage Blindheit.

**Vorbeugende Regel:** Provider-Proben nicht nur beim Anbau rechnen, sondern
jeden Lauf (Existiert-Schwelle: liefern X% der erwarteten Sätze die Felder
noch? — als Protokollzeile). Providerschwelle im Code existiert
(`schwelle_erreicht()`), eine Ausfall-Schwelle („Anbieter liefert 7 Tage
0 Sätze") existiert nicht — die wäre der billigste Alarm.

## FM 3 — Seite und Fragmente kippen an ihrer eigenen Größe

**Auslöser:** Fragment wächst mit Messtagen und Modellen (PM-6 offen).
Heute: ~3,7 MB Gesamtlast (HTML + 2 Fragmente) nach 6 Messtagen; Historie
wächst mit ~427 Zeilen/Tag (2562 über 12.–17.09., gemessen). Das Fragment
existiert erst seit heute — die Wachstumsrate über Zeit ist **n. z.**
(Git-Historie leer), die „~7 KB je Paar" sind bislang eine Schätzung.

**Frühindikator:** Ladezeit auf dem Telefon (Sichttest-Frage „mobil ohne
Querscroll" misst Breite, nicht Dauer); Protokollzeile Fragmentgröße. Kippt
erst jemandem auf, der mobil wartet — also Antonio selbst, im schlechtesten Moment.

**Vorbeugende Regel:** PM-6-Jetzt-rechnen: nach 14 Tagen Fragmentgröße gegen
Messtage auftragen (dann ist die Rate echt), Deckel ableiten (z. B. nur letzte
N Messtage im Fragment, Älteres aus CSV/Export). Deckel vor dem ersten
Megabyte-Überschreiten, nicht danach — dieselbe Fehlerklasse wie die
Seitenhöhen-Bombe (`UEBERSICHT_MAX_ZEILEN`, 30.08.).

## FM 4 — Die Textlastigkeit kriecht zurück

**Auslöser:** Jede neue Information wurde ein Satz (Antonio: „super viele
Erklärungen, die mir auf den Sack gehen", „Ich will keinen verfickten Text
sehen"). Heute ~158.430 sichtbare Zeichen auf EINER Seite; jeder neue
Zustand (Leer-Sicherungen aus E5, Lücken-Sätze) erzeugt per Muster Text,
weil Text der Billigste-Ausdruck ist. 2027-Bild: Die dynamische
Preis-Aufklärung (Forderung 2) wurde als Satzliste unter den Preis gehängt
statt als Rechenweg-Grafik — und der Ärgernis-Zustand vom 17.09. ist zurück.

**Frühindikator:** Nur Antonio selbst — kein Test misst Textmenge
(`test_keine_seite_erklaert_ihre_eigene_bedienung` deckt Bedien-Sätze, nicht
Erklär-Sätze). Der Frühindikator ist „Antonio schaut hin" = Zwang zur Nutzung
der Seite = Ziel verfehlt.

**Vorbeugende Regel:** Eine messbare Grenze in `pruefe_portal.py`: sichtbare
Zeichen je Reiter gegen Deckel (Höhenbudgets existieren schon — dasselbe
Instrument für Text). Und eine Bau-Regel im Review-Katalog: neue Information
erst als Graf/Interaktion entworfen, Text nur als Label. Der Preis-Klick
(Forderung 2) ist der Härtetest: gelingt er als Aufbereitung, ist das Muster
gebrochen; gerät er zum Textblock, wiederholt sich FM 4 sofort.

## FM 5 — Wartungsaufwand übersteigt den Wert einzelner Bausteine

Bewertung gegen Antonios drei Fragen (Gesamtkosten? Preisentwicklung? Markt?):

| Baustein | Kern/Neben | Begründung (kurz) |
|---|---|---|
| TCO-Zeitreihe (Hauptansicht) | **Kern** | Frage 1 („was kostet es gesamt") — Antonios Beispiel-Abfrage ist der Live-Beweis-Standard |
| Preisverlauf + Modell-Wahl | **Kern** | Frage 2 — Forderung 4 bestätigt: unterer Graph ist der Wert, oberer ist Duplikat |
| Radar-Tafel (Abweichungen, „günstiger als Vodafone") | **Kern** | Forderung 3: genau diese Tafel soll prominent werden; hängt an der Vodafone-Referenz-Näherung (pflegeleicht, aber erklärungsbedürftig) |
| Gerätekatalog | **Kern** | Frage 3 + Forderungen 5/6 (Preis rein, TCO-Umschalter dort) |
| Export-CSVs (4 Knöpfe) | Neben | Statisch, wartungsarm; Nutzen unbestätigt — nach 6 Monaten Nutzungslosigkeit kandidiert hier zuerst die Radar-CSV |
| Portfolio-Aufklapper | Neben | Kleine Sortiments-Aussage, billig im Unterhalt |
| geraete-quellen.html | Neben, aber Pflicht | Diagnose-Seite (FM 2 liest sie); Fußlink nicht entfernen (B1-Lehre) |

**Frühindikator:** Antonio nutzt einen Reiter nie („in einem Jahr benutzt ihn
niemand") — messbar wäre es nicht; sichtbar an Rückfragen, die den Reiter
umgehen. **Vorbeugende Regel:** Kein neuer Reiter/Modus ohne eine der drei
Fragen, die er beantwortet; Reiter-Zahl bleibt 4 (E3), Deckel im Test.

## FM 6 — „As simple as possible"-Audit (Vorschläge, Antonios Entscheidung)

1. **Oberen Preisverlauf-Graph löschen** (Forderung 4) — Duplikat des
   Modell-Wahl-Graphen, reiner Abbau.
2. **Radar-Tafel und Vergleichs-Tafel verschmelzen**, wenn Forderung 3 die
   „vorgeschlagenen Smartphones" ohnehin auf die Vergleichs-Seite holt — zwei
   Reiter, dieselbe Frage („wo ist es günstiger"), wären der Mischmasch
   (Forderung 7), nicht die Antwort.
3. **Umschalter TCO/Barpreis im Katalog** (Forderung 6) ersetzt die separate
   TCO-Liste — keine neue Unterseite, eine Tabelle. Konsequent gebaut heißt
   das: zwei Ansichten, EIN Datenpfad, EIN Test-Ort.
4. **12 der 16 Auto-Modelle (Watches/Tabs/AirPods) aus der Zeitreihen-Wahl
   fernhalten, solange sie keine Bündel haben** — keine unsichtbaren
   Wahl-Einträge; sie gehören nur in den Katalog.
5. **ALDI-Tarif-Titel aus der Unbekannten-Arbeitsliste filtern** (87 von 284
   Zeilen sind Tarif-Rauschen) — die Liste ist der Frühindikator aus FM 1,
   Rauschen macht sie taub.
Nicht anfassen: Export-Knöpfe, Portfolio, Quellen-Seite (nicht kritisiert;
B1-Lehre „gebaut und unauffindbar").

## FM 7 — „Nie wieder etwas ändern müssen": die drei ehrlichen Rest-Risiken

1. **Bot-Schutz/IP-Challenges** (Telekom 202 heute): kein Code beendet das;
   jede der drei APIs kann morgen so dastehen. Tragbar nur durch Beobachtung
   (FM-2-Alarm) und eine Antonio-Entscheidung über den Umgehungsweg.
2. **Angebotsstruktur-Änderungen** (Felder, Slugs, Tarif-Namen brechen die
   Fremdschlüssel `tarif_bezug`/Bündel-Brücken): Bruch ist still, nur
   Lauf-Proben merken es. Wird immer wieder vorkommen — Aufwand pro Fall
   klein, ABER nur wenn der Frühindikator existiert.
3. **Neue Geräteklassen/Benennformen** in der Schälung (Bündel-Titel,
   Doppelmarken, neue Anker-Lücken wie iPad heute): die Schälregeln altern
   langsam; das ist der einzige Punkt, der wirklich leichte Handarbeit bleibt.

**Minimaler Betriebs-Rhythmus, der sie trägt** (bestehende Instrumente, kein
Neubau außer dem FM-2-Alarm): monatlich die 5 Sichttest-Fragen live plus zwei
Zusatzfragen — „steht das neueste Gerät drin?", „dauert der Laden am Telefon?" —
und täglich die 3 Protokollzeilen (Auto-Anlage, Unbekannte, Fragmentgröße) als
Frühindikatoren. Tests und `pruefe_portal` laufen ohnehin.

---

**Kurzfassung:** Die Kette „Launch → Store" funktioniert (16 Auto-Einträge,
iPhone 18 gemessen). Brechen wird es 2027 an vier anderen Stellen: unsichtbare
Modelle (FM 1d), stille Quellentode (FM 2), Größe (FM 3), zurückkriechender
Text (FM 4). Drei davon haben heute keinen Alarm — und der Preis-Klick
(Forderung 2) entscheidet, ob FM 4 sofort wiederkommt.
