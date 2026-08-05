# Welle 3 — was die beiden Hebel wirklich gebracht haben

Beide Zahlen stammen aus einem Skript, keine ist geschätzt. Die Rohdaten
liegen daneben: `kandidaten_firmen_welle3.yaml` (Suchergebnis),
`messung_datumsparser.json` (Parser-Vergleich), `befund_*.json` (Abnahme).

---

## 1. Newsroom-Erkennung im Sucher

Gemessen an derselben Firmenliste, mit der Session 5 gearbeitet hat
(`config/kandidaten_firmen.yaml`, 338 Suchaufträge). Der Auftrag nennt als
Latte: „Wenn die Newsroom-Erkennung daraus keine 100 Quellen macht, taugt sie
nicht."

| | |
|---|---:|
| Suchaufträge (Firmen) | 338 |
| Firmen mit mindestens einem Kandidaten | **184 (54 %)** |
| Kandidaten gesamt | **257** |
| davon RSS/JSON-API — das konnte der Sucher vorher auch | 129 |
| davon `newsroom` — **das konnte er vorher gar nicht** | **128** |
| davon auf einem echten Pressepfad (kein Beifang) | 79 |
| **Firmen, die AUSSCHLIESSLICH über die Newsroom-Erkennung etwas liefern** | **106** |

Die Zahl, auf die es ankommt, ist die letzte: 106 Firmen, die vorher null
Kandidaten brachten, liefern jetzt einen. Der Sucher hat seine Ausbeute auf
derselben Firmenliste **verdoppelt** (129 → 257 Kandidaten).

Zur Einordnung: Session 5 kam auf dieser Ebene auf 31 % Firmen mit Kandidat
(604 gesucht, 418 mit null). Jetzt sind es 54 %.

Gefunden werden dabei genau die Seiten, die der Auftrag als Beispiel nennt —
`saladeprensa.vodafone.es`, `tdcbrands.dk/en/press`,
`t.ht.hr/en/press/press-releases`, `newsroom.ee.co.uk`,
`spolecnost.o2.cz/tiskove-centrum`, `grupapolsatplus.pl/pl/biuro-prasowe`.

---

## 2. Datums-Parser

Der Auftrag setzt ihn als zweitgrößten Hebel an, mit Verweis auf 82 Kandidaten
aus Welle 2, die *nur* am Datumsformat scheiterten.

Gemessen mit `scripts/miss_datumsparser.py` an den 128 newsroom-Kandidaten
dieser Welle. Jede Seite wird **einmal abgerufen und zweimal geparst** — einmal
mit den Tabellen von vor Welle 3, einmal mit den neuen. So misst der Vergleich
den Parser und nicht die Tagesform des Servers.

| | vorher | nachher |
|---|---:|---:|
| Kandidaten, die Kriterium 3 (≥ 80 % datiert) bestehen | 59 | **61** |
| datierte Meldungen insgesamt | 908 | **915** |
| durch die Erweiterung verloren | — | **0** |

**Der Gewinn ist 2 von 128, nicht 82.** Das ist die ehrliche Zahl, und sie ist
kleiner als erwartet.

Der Grund steckt in der Zusammensetzung der Messmenge, nicht im Parser: diese
Kandidaten stammen aus der bestehenden Firmenliste, und die ist überwiegend
west- und mitteleuropäisch. Deren Datumsformate konnte der alte Parser schon
lesen. Die neuen Tabellen decken Polnisch, Tschechisch, Ungarisch, Rumänisch,
Baltisch, Griechisch, Kyrillisch, Arabisch, Devanagari sowie CJK und
Vietnamesisch ab — für diese Sprachen gibt es bisher schlicht keine
Firmenliste, gegen die man messen könnte.

Zwei Schlüsse daraus, beide unbequem:

1. Die Erweiterung ist richtig und kostet nichts (0 verlorene Quellen, 40
   Tests), aber sie ist **kein Hebel für die Zahl**, solange die Firmenliste
   nicht sprachlich breiter wird. Erst die Recherche nach nicht-europäischen
   Firmen macht sie messbar wertvoll.
2. Die 82 aus Welle 2 waren offenbar eine andere Grundgesamtheit. Wer die Zahl
   erneut zitiert, sollte sie erst nachmessen — genau dafür gibt es jetzt
   `miss_datumsparser.py`.
