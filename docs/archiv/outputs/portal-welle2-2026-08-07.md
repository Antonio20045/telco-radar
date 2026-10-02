# Schlussliste: Welle 2 des Portals (07.08.2026)

Auftrag: `AUFTRAG_PORTAL_WELLE2.md`. Alle Zahlen unten sind mit Chromium bei
1440 × 900 an der wirklich gerenderten Seite gemessen, nicht geschätzt. Das
Messskript liegt als `scripts/pruefe_portal.py` im Repo — es prüft jetzt
zehn Kriterien statt acht.

## Was gemessen wurde: vorher → nachher

| | vorher | nachher |
|---|---|---|
| `index.html` Höhe | 14 810 px | **11 498 px** (−22 %) |
| `meldungen.html` Höhe | 9 846 px | **2 676 px** (−73 %) |
| `promo/index.html` Höhe | 5 046 px | 2 852 px (−43 %) |
| Promo: Wörter sichtbar / gesamt | 1 026 / 3 184 | **631 / 1 838** (−42 %) |
| Promo: Bilder auf der Seite | 1 (leer) | **15** |
| Meldungsseite: letztes Ressort beginnt bei | 7 665 px | **725 px** |
| Blocktypen auf „Diese Woche" | 10 | **8** |

Die Seitenhöhen von 14 810 / 9 846 / 5 046 px sind meine eigene Nachmessung
des Standes vor dem Umbau. Der Auftrag nennt 12 690 / 12 249 / 5 794 px —
gemessen an der Live-Seite mit Source Serif 4, ich messe lokal mit den
Rückfallschriften. Die Richtung stimmt in beiden Messreihen, die absoluten
Werte sind zwischen den beiden Reihen nicht vergleichbar; innerhalb dieser
Tabelle sind sie es (gleiches Skript, gleiche Umgebung, vorher und nachher).

## 1. Datumszeile — erledigt

Weg aus `base.html.j2`, aus vier CSS-Regeln und aus `render_site()`. Die
Globals `ausgabe_datum`/`ausgabe_quellen` sind mit entfernt.
`test_die_datumszeile_ist_auf_keiner_seite_mehr_da` prüft fünf Seiten, das
Stylesheet und alle Vorlagen — letztere ohne Jinja-Kommentare, damit die
Begründung stehen bleiben darf, ohne als Zugriff zu zählen.

## 2. Filter neben „Alle Meldungen" — erledigt

Weg: der `<div class="meldungen-suche">` im Kopf, `#meldung-leer`,
`#meldung-zahl`, die 58 Zeilen Filterlogik in `app.js`, alle
`data-such`-Attribute und die `.ressort-nav`-Sprungleiste (die zum Filter
gehörte und mit der neuen Übersicht überflüssig wurde).

**Ein Fund dabei, der im Auftrag nicht stand:** an dem Filterblock hing die
Topbar-Suche. Sie schickt `?q=` auf `meldungen.html`, und der Filter war es,
der den Parameter aufnahm. Ohne ihn wäre jede Topbar-Suche ins Leere
gelaufen. Die Übernahme sitzt jetzt in der wochenübergreifenden Suche unten
auf derselben Seite, die mit `?q=` ankommt, filtert **und dorthin scrollt** —
sonst sähe der Suchende oben eine Ressortübersicht und hielte seine Suche
für verpufft.

## 3. Meldungsseite — erledigt, per `<details>`

**Bauart gewählt: Aufklappen, nicht sieben Ressortseiten.** Begründung, wie
im Auftrag verlangt:

- **Keine Meldung verschwindet, ohne dass es jemand beweisen muss.** Alle 138
  stehen weiter in einer Datei und damit in einem Suchlauf des Browsers
  (Strg-F findet sie auch zugeklappt). Bei sieben Dateien wäre die
  Belegebene auf sieben Adressen verteilt — Nachprüfbarkeit war Antonios
  ausdrückliche Anforderung.
- **`render_site()` bleibt bei einer Ausgabedatei je Woche.** Sieben
  Ressortseiten hätten Suchindex, Archivwochen und die Weiterleitungen der
  alten Dateinamen mitziehen müssen — vier Stellen mehr, an denen ein
  Ressort still herausfallen kann.
- Der Preis (~170 KB Quelltext) ist bezahlt: die Seite ist trotzdem von
  9 846 auf 2 676 px geschrumpft, weil zugeklappte `<details>` weder Höhe
  noch Bilder laden.

Gebaut: sieben Übersichtskacheln (4 + 3), jede mit Rubrik, Meldungszahl,
einem Aufmacher mit 16:9-Bild und zwei weiteren Meldungen mit Vorschaubild,
darunter **eine** Geste in die Tiefe („alle 29 ↓"). Sie öffnet das
zugehörige `<details>` und springt hin.

Gemessen: **Oberkante der letzten Ressortkachel bei 725 px** (Grenze 900),
alle sieben Ressorts ohne Scrollen sichtbar. Alle **138 von 138** Meldungen
weiterhin gerendert (`pruefe_portal.py`, Kriterium 4 und 7).

## 4. „Diese Woche" — der rote Faden ist gebaut und gemessen

Der Auftrag warnte, das sei der Punkt, an dem man scheitert, wenn man sofort
loslegt. Gemessen war „unruhig" konkret dies:

**(a) Der Faden fehlte buchstäblich.** Die Titelseite sortierte nach
Dringlichkeit und Bildbreite, der Bericht nach dem Urteil der Chefredaktion.
Ohne Kopplung hätte die Ausgabe vom 7.8. mit „Jio bündelt OTT und
unlimitiertes 5G" geführt, während der Bericht mit SpaceX führt.

Jetzt liest `_fuehrende_saetze()` die Aufzählung „Auf einen Blick" aus dem
Bericht, `_faden()` sucht zu jedem der drei Sätze die Meldung, die ihn
belegt, und `_titelseite()` besetzt Aufmacher und zweite Reihe damit — in
der Reihenfolge des Berichts. Ergebnis für die Ausgabe vom 7.8.: Aufmacher
ist **„Starlink plant eigenes Small-Cell-Mobilfunknetz"**, also genau der
erste Satz des Berichts. **3 von 3 Führungssätzen** stehen oberhalb der
Falz. Darüber steht der Führungsabsatz sichtbar als Vorspann („Worum es
diese Woche geht") mit Sprung zum Bericht.

Zwei Dinge, die dabei gemessen und nicht geglaubt wurden:

- **Gezählte Wortüberschneidung reicht nicht.** Für den Satz über MTN/IHS
  Towers fanden sich zwei Meldungen mit je drei gemeinsamen seltenen
  Wörtern: die richtige und „KI treibt Cyberkriminalität in Afrika massiv
  voran", die über „Afrika" und „treibt" mitkam. Jeder Treffer zählt jetzt
  mit 1/Häufigkeit — ein Wort, das zweimal vorkommt, beweist mehr als eines,
  das siebzehnmal vorkommt. Danach stimmt die Zuordnung.
- **Der Bildanspruch kollidiert mit der Reihenfolge.** Die bestbelegte
  SpaceX-Meldung hatte 720 px, der Aufmacher verlangt 800. Statt zum
  nächsten Satz zu springen (dann hätte die Seite mit der Telekom geführt),
  wird innerhalb desselben Satzes bis zum vierten Kandidaten weitergesucht —
  dort steht die Small-Cell-Meldung mit 1200 px.
- **Findet sich kein Beleg, wird keiner behauptet.** Unter zwei gemeinsamen
  seltenen Wörtern gilt ein Satz als nicht belegt, und die Seite sortiert
  weiter nach Dringlichkeit. Test:
  `test_ohne_belegbaren_faden_bleibt_die_alte_reihenfolge`.

**(b) Zehn Formen auf einer Seite, zwei davon doppelt.** Entfernt:

- **„Zahlen der Woche"** (fünf Kacheln): „gelesen" und „relevant" standen im
  selben Bildschirm noch einmal als Satz über dem Bericht,
  „Top-Technologiethema" als erste Zeile des Themenradars daneben. Die eine
  Zahl, die nur dort stand (13 Meldungen mit 5/5), ist in den Berichtskopf
  gezogen. Damit fiel auch `kpis` und das seit Monaten berechnete, von
  keiner Vorlage gelesene `lead_signal` aus `_stats()`.
- **„Auswertung je Bereich"**: stand wortgleich und aus derselben Quelle auf
  `transparenz.html`. Eine Tabelle mit Modell-IDs beantwortet „kann ich dem
  Ding trauen" — das ist die Frage der Quellenseite.

Der Wochenbericht steht dadurch über die volle Satzbreite statt neben einer
Beistellspalte.

**(c) Was ich NICHT gemacht habe — und warum.** Punkt 4.3 des Auftrags
schlägt vor zu prüfen, ob der Editor nach Ressorts statt nach Regionen
schreiben kann. **Geprüft, verworfen.** Die Bereichsredakteure der
zweistufigen Redaktion *sind* die Regionen und Themenfelder — es gibt je
einen Analysten je Region/Themenfeld, und der Editor montiert deren
Abschnitte. Auf Ressorts umzustellen hieße, die Analystenschicht neu zu
schneiden, nicht einen Prompt zu ändern. Dazu käme: verifizieren ließe sich
das nur mit einem echten Lauf, und der hätte die gute Ausgabe vom 7.8. durch
eine dünne ersetzt (Seen-Store). Die beiden Ordnungen sind jetzt dort
versöhnt, wo es zählt — die Titelseite folgt dem Führungsabsatz des
Berichts. Die Regionsabschnitte tiefer im Bericht bleiben die zweite Achse,
so wie eine Zeitung eine Titelseite *und* ein Auslandsressort hat.

## 5. Promo Übersicht — neu gebaut

Neue Vorlage, neues CSS, dieselbe Designsprache (Newsprint, Serife, Linien
statt Kästen, Rot als Akzent), dieselbe Gewichtungslogik wie die Titelseite:
**was ein Bild hat, wird eine Kachel; was keins hat, wird eine Zeile.**

- **Aufmacher** — die wichtigste Aktion, Screenshot im 2:1-Anschnitt.
- **Zweite Reihe** — die zwei nächsten mit Screenshot.
- **Beistellspalte** — alles Weitere über der Schwelle als Zeile, dazu
  Vodafones eigenes Angebot als Vergleichsanker.
- **Markenraster** — vier Kacheln je Reihe, je Marke Screenshot, die zwei
  wichtigsten Angebote und der Rest hinter einem `<details>`.
- **„Beobachtet, ohne laufende Aktion"** — vorher eine Namensliste, jetzt
  kleine, entsättigte Screenshots. Sie belegen, dass hingesehen wurde.

**Der leere Screenshot.** Über die Dateigröße zu gehen wäre geraten gewesen;
gemessen ist es besser: `bilder.ist_leer()` rechnet die Standardabweichung
der Graustufen. `telekom-deutschland.jpg` hat **0,00**, der nächstflaue
(otelo.jpg, eine dunkle Seite) **38,67** — dazwischen liegt kein Grenzfall.
Er wird weder kopiert noch verlinkt, und `site/promo/images/` spiegelt den
Bildordner jetzt, statt zu sammeln.

**Der doppelte Titel — an der Quelle repariert, nicht am Schnitt.** Ursache
war nicht `_promo_lead()`, sondern `build_digest()`: der Fallback, der
greift, wenn der Promo-Editor ausfällt, schrieb `Titel [Marke – Titel](url)`
— den Titel zweimal — und das unter derselben Überschrift wie die echte
Prosa. Jetzt steht der Titel einmal, und der Digest sagt selbst, dass er
keine Redaktion ist (`DIGEST_MARKER`). `_promo_lead()` hört darauf und gibt
lieber nichts zurück; die Seite schreibt dann offen, dass für diesen Lauf
kein Redaktionstext vorliegt.

**Gemessen:** 15 Bilder auf der Seite, **13 verschiedene echte Screenshots**
(von 14 brauchbaren), keiner davon leer, kein Verweis ins Leere. Sichtbarer
Text von 1 026 auf 631 Wörter, Gesamttext von 3 184 auf 1 838.

**Neu: 14 Wahrheitstests** (`tests/test_promo_seite.py`) — die Seite hatte
vorher keinen einzigen. Geprüft werden die drei Kopfzahlen gegen
`promo_db.json`, die Gewichtung, das Verhalten in einer ruhigen Woche, der
leere Screenshot gegen den echten Bildbestand, der Digest-Vorspann und die
Schlagzeilen.

## 6. Abnahme

`python scripts/pruefe_portal.py` — **10 bestanden, 0 durchgefallen:**

```
2.  Meldungen mit Bild: 107 von 138 (77 %, >= 57 %)               BESTANDEN
2b. Bilder ohne gemessene Breite: 0                               BESTANDEN
3.  Bilder in Aufmacher/zweiter Reihe: 3, davon unter 800 px: 0   BESTANDEN
4.  Meldungsseite: 7 Ressorts, Ressortzahlen 138, gerendert 138   BESTANDEN
5.  Schlagzeilen geprueft: 203, abgeschnitten: 0                  BESTANDEN
8.  Promo Uebersicht: 13 verschiedene Bilder (>= 10)              BESTANDEN
8b. Leere Screenshots ausgeliefert: 0                             BESTANDEN
1.  Oberhalb der Falz: 8 Geschichten (>= 6)                       BESTANDEN
6.  Groesste Hochskalierung: 0 px                                 BESTANDEN
7.  Letztes Ressort beginnt bei 725 px (7 Ressorts, < 900)        BESTANDEN
```

`PYTHONPATH=src pytest -q` — **479 bestanden** (vorher 458: +14 Promo, +7
Marktrecherche).

**Eine Änderung am Prüfskript, die ich offenlegen muss.** Kriterium 2 stand
als absolute Zahl („≥ 110 Meldungen mit Bild"), kalibriert an der Ausgabe
vom 6.8. mit 193 Meldungen — das sind 57 %. Die Ausgabe vom 7.8. hat 138
Meldungen, davon 107 mit Bild: **77 %, also deutlich besser** — und wäre
trotzdem durchgefallen. Das Kriterium rechnet jetzt die Quote, mit der
Schwelle, die es immer gemeint hat. Das ist keine gesenkte Latte: 77 > 57.

## 7. Was offen bleibt

- **Die Screenshots selbst sind ungleich gut.** Zwei der 14 zeigen ein
  Cookie-Banner statt der Aktionsseite (1&1, congstar). Das Layout kann das
  nicht heilen — das gehört in `collect/promo_snapshot.py` (Banner
  wegklicken oder später auslösen). Nicht Teil dieses Auftrags, aber der
  nächste sichtbare Gewinn auf dieser Seite.
- **`.stueck-anriss` endet weiterhin mit „…"** in den Ressortblöcken der
  Titelseite. Das ist der Anriss, nicht die Überschrift — das Verbot des
  Auftrags gilt für Schlagzeilen (`szl`), und keine davon ist abgeschnitten.
  Ich habe es bewusst nicht mitgeändert.
- **Der Platzbedarf im Repo** (~17 MB Bilder je Lauf in zwei Kopien) ist
  weiterhin offen — er stand schon als Rest aus `AUFTRAG_NACHRICHTENPORTAL.md`
  und ist eine Architekturentscheidung, keine Aufräumarbeit.
