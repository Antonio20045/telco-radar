# Suche und Differenzierung — Schlussliste, 08.08.2026

Antonios Auftrag, in seinen Worten:

> „Die Suchfunktion ist total bescheuert. Wenn ich was suche, werde ich auf die
> Unterseite Meldungen weitergeleitet … Das UI ist total beschissen. Ich
> verstehe nicht, warum ich da weitergeleitet werde. Wenn ich was suche, möchte
> ich das schön dargestellt haben. Alles zu diesem Thema mit Bildern. Nach
> richtiger Analyse … wenn ich suche zum Beispiel Telekom oder Perplexity, alle
> Meldungen super dargestellt, dass ich einen Überblick habe über die
> Entwicklung, auch über die Historie. Ich möchte auch die Meldungen nicht von
> diesem Band, sondern alle sehen, die mit diesem Thema zu tun hatten.“
>
> „Dann die Differenzierung. Es ist total unübersichtlich, sich das anzugucken.
> Keine Bilder, es ist schwer zu verstehen … viel schöner dargestellt, viel
> besser sein analytisch. Eigentlich hat es noch einen Bericht, und Bericht
> finde ich auch gut, aber nicht einfach so reinpasten, dieser eine lange
> Bereich … damit nicht so viel kognitive Arbeit darin besteht, erstmal zu
> verstehen, was die Differenzierung ist.“

Beides erledigt. **707 Tests, alle 14 Prüfungen von `scripts/pruefe_portal.py`
grün** (11 alte plus drei neue: 9, 9b, 10).

---

## 1. Die Suche: eine eigene Seite statt einer Weiterleitung

### Was der Befund war

Das Suchfeld der Topbar hatte `action="meldungen.html"`. Wer „Telekom" suchte,
landete auf einer Seite, die zuerst sieben Ressortkacheln, dann sieben
Ressortblöcke und dann das Archiv zeigt — **die Treffer standen in einer Karte
am Fuß dieser Seite, nach rund 2400 px**, als graue Textzeilen ohne Bild, in
Indexreihenfolge, ohne Zeitbezug.

Dazu drei Konstruktionsfehler in der Suchmaschine selbst:

| Fehler | Folge |
|---|---|
| Die Eingabe musste als **eine Zeichenkette** im Text vorkommen | „telekom perplexity" fand nichts — genau die Kombination, die den Anlass der Suche bildet |
| **Keine Rangfolge** | ein Treffer im Absender wog so viel wie einer im Fließtext |
| Der Index kannte **zwei von drei Bereichen** | die laufenden Promo-Aktionen einer Marke waren unauffindbar |

### Was jetzt steht

`suche.html` ist wieder eine echte Seite — und sie ist als **Dossier** gebaut,
nicht als Trefferliste. Der Name war seit dem 06.08.2026 eine Weiterleitung;
ein Lesezeichen darauf landet jetzt dort, wo es immer hinwollte.

| Abschnitt | Was er beantwortet |
|---|---|
| Kopf | Suchfeld (groß, Serife), darunter der Begriff als Überschrift und die Bilanz: *107 Treffer · von 15. Juni bis 7. August 2026 · 49 Quellen* |
| Der Überblick | **Verlauf** je Monat, **Wer** (häufigste Absender), **Worum** (Ressorts) — als Balken. Das ist „die Entwicklung", und sie steht **vor** der ersten Meldung |
| Bereichsfilter | *Alles 107 · Meldung 56 · Differenzierung 15 · Aktion 36* — die Zahl steht am Filter, sie ist der Grund ihn zu drücken |
| Aufmacher | der stärkste Treffer, groß, mit Bild |
| Chronik | alle übrigen **nach Monaten**, neueste zuerst, sechs Bildkarten je Monat, der Rest als Zeilen |

Gemessen an der Ausgabe vom 7.8.: „Telekom" → 107 Treffer aus drei Bereichen,
davon 11 mit Bild oberhalb der ersten Falz; „Perplexity" → 6 Treffer über zwei
Monate, alle aus der Differenzierungs-Bibliothek.

**Die Suchmaschine** (`app.js`, `TelcoSearch`) sucht jetzt wortweise mit
UND-Verknüpfung und vergibt eine Rangfolge: Treffer im Absender 8 Punkte, in
der Schlagzeile 5, sonst 2, plus die Dringlichkeit der Meldung. Die
Hervorhebung markiert jedes Wort — und **kürzt nichts mehr mit „…"**. Das war
ein offener Punkt aus der Vorsession (die Trefferkarten kürzten Überschriften
JS-seitig, im Widerspruch zur Schlagzeilen-Regel).

**Der Index** (`report/suchindex.py`, neu — vorher in `html.py`) trägt jetzt:

* die bewerteten Meldungen **aller** Ausgaben, mit `schlagzeile` statt
  `de_title` (der Rest des Portals zeigt genau diese Zeile — zwei
  Überschriften für dieselbe Meldung bemerkt man erst, wenn man beide Seiten
  nebeneinander legt),
* die Differenzierungs-Bibliothek,
* **die Promo-Aktionen** (neu), mit Sprungziel auf ihren Markenblock,
* je Eintrag **sein Bild**, mit fertigem Pfad — `images/…` bzw.
  `promo/images/…`, damit `app.js` nicht wissen muss, welche Gattung ihre
  Bilder woher bezieht.

1060 statt 804 Einträge, 314 davon mit Bild.

Auf der leeren Suchseite steht kein Satz, der zum Tippen auffordert, sondern
**„Meistgenannt im Archiv"** — zwölf Absender als Chips, gerechnet aus dem
Index. Die Promo-Aktionen zählen dabei nicht mit: sie sind 256 von 1060
Einträgen und alle deutsch, mitgezählt stünden dort winSIM und simplytel vor
AT&T und Reliance Jio.

Die Suchkarte am Fuß von `meldungen.html` ist weg, ebenso ihr CSS. Auf
`suche.html` selbst blendet `base.html.j2` das Topbar-Feld aus — zwei
Suchfelder auf einer Seite sind zwei Bedienelemente für eine Handlung.

---

## 2. Die Differenzierung: Bilder, Marktbild, Gewichtung

### Was der Befund war

77 gleich große Textkärtchen, **null Bilder**, 9060 px Seitenhöhe. Gleich große
Kärtchen sind eine Liste, keine Analyse: sie behaupten, dass alle 77 Beispiele
gleich wichtig sind, und überlassen das Sortieren dem Leser. Der Bericht lag
als ein zugeklappter Block am Seitenende — und er sagte **dasselbe noch
einmal**: sein Abschnitt „Konkrete Entwicklungen" war eine Aufzählung aller
Moves mit Inline-Links, also genau der Bestand, der zwei Bildschirme weiter
oben schon als Karten stand, in Absätzen von 2100 Zeichen.

### Was jetzt steht

**1. Jede Karte trägt ein Motiv.** `report/diff_bilder.py` (neu) beschafft die
Bilder in zwei Stufen: erst das Bild, das der Wochenbericht für dieselbe URL
schon geholt hat (kostet kein Netz), dann `og:image` der Originalseite.
Gemessen: **35 von 71 Beispielen** (5 geerbt, 30 per og:image). Was sich nicht
belegen lässt, bekommt eine **Schriftkachel** mit dem Absender — dieselbe Regel
wie auf der Promo Übersicht, nie ein leerer Kasten. Trägt die Kachel den
Absender, steht er nicht noch einmal in der Metazeile darunter.

Eigener Speicher `data/state/diff_images/` mit eigenem Index und eigenem
Aufräumen: `report_bilder.raeume_auf()` behält nur, was die letzten vier
Ausgaben referenzieren, ein Differenzierungs-Beispiel lebt aber Monate. Der
Index merkt sich auch den **Fehlversuch** (30 Tage), sonst fragte jeder Lauf
dieselben 36 Seiten erneut ab. `site/images/` spiegelt seitdem **beide**
Ordner.

**2. Das Marktbild steht vor den Beispielen** — gerechnet, ohne Modell:

| Spalte | Aussage |
|---|---|
| Welcher Hebel gezogen wird | Balken je Hebel: Entertainment 17, KI 12, Garantie 7 … |
| Wer am breitesten aufgestellt ist | gereiht nach der Zahl **verschiedener** Hebel — wer denselben achtmal zieht, fährt eine Kampagne; wer vier verschiedene zieht, eine Strategie. Deutsche Telekom mit 6 Hebeln vorn |
| Woher die Beispiele kommen | Nordamerika 24, Europa 18, Asien 15 … |

Das ist die Antwort auf „was machen die anderen", bevor man 71 Einzelbeispiele
liest.

**3. Jeder Hebel sagt in einem Satz, was er bedeutet.** Quelle ist `blurb` aus
`report/differentiation.py` — dieselbe Stelle, an der schon die Hebel-Farbe
steht, damit die Erklärung nicht an zwei Orten auseinanderläuft.

**4. Gewichtung statt Kachelwand.** Je Hebel: ein Aufmacher (Bild links, große
Schlagzeile rechts), eine Reihe Karten, dann Zeilen, der Rest in einem
Aufklapper. **Nur ein Beispiel mit Bild kann Aufmacher sein** — eine
Schriftkachel über 46 % Breite lässt daneben eine halbe Spalte leer, und genau
dieser Eindruck („da fehlen bei einigen die Bilder, das wirkt so richtig
scheiße") soll nicht wiederkommen. Gibt es keins, stehen alle Beispiele
gleichrangig im Raster — eine Stufe weniger ist ehrlicher als eine leere Stufe.
Ein Beispiel, das oben im Radar schon groß steht, führt seinen Hebel nicht auch
noch an.

**5. Der Bericht ist verteilt, nicht angehängt.** Der Redakteur
(`analyze/differentiation_editor.py`) schreibt eine neue Gliederung, und
`report/differenzierung_bericht.py` (neu) schneidet sie in die Teile, die die
Vorlage an drei Stellen einsetzt:

| Abschnitt | Wo er landet |
|---|---|
| `## Das Bild` | im Seitenkopf, als Einstieg |
| `## Muster` | als Band unter dem gerechneten Marktbild |
| `## Einordnung` (H3 je Hebel) | direkt über den Beispielen dieses Hebels |

`## Quellenbasis` fällt weg — sie führte jede Karte der Seite ein drittes Mal
auf. Prompt, `validate_briefing`, `build_digest` und die Zerlegung hängen an
**einer** Gliederung; der Notfall-Digest schreibt dieselbe, also ändert ein
Ausfall des Redakteurs den Ton der Seite, nicht ihren Aufbau. Neu in
`validate_briefing`: ein Absatz über 1200 Zeichen (ohne Links gerechnet) wird
abgelehnt — das ist der wahrscheinlichste Rückfall in die Aufzählung.

**Alte Berichte bleiben lesbar.** Findet die Zerlegung keinen der neuen
Abschnitte, steht der Bericht wie bisher zugeklappt am Ende. Kein Lauf muss
abgewartet werden, damit die Seite steht.

---

## 3. Abnahme

`scripts/pruefe_portal.py` misst jetzt über einen **lokalen HTTP-Server** statt
über `file://`. Der Grund ist das neue Kriterium 10: `fetch('search_index.json')`
ist unter `file://` von der Same-Origin-Regel gesperrt, die Suchseite bliebe
leer, und die Prüfung würde einen Fehler messen, den es nicht gibt.

```
  2.  Meldungen mit Bild: 107 von 138 (77 %, >= 57 %)              BESTANDEN
  2b. Bilder ohne gemessene Breite: 0                              BESTANDEN
  3.  Bilder in Aufmacher/zweiter Reihe: 3, davon unter 800 px: 0  BESTANDEN
  4.  Meldungsseite: 7 Ressorts, 138 gerendert, 138 Daten          BESTANDEN
  5.  Schlagzeilen geprueft: 378, abgeschnitten: 0                 BESTANDEN
  8.  Promo Uebersicht: 33 verschiedene Bilder (>= 10)             BESTANDEN
  8b. Leere Bilder ausgeliefert: 0                                 BESTANDEN
  8c. Karten ohne Motiv: 0 von 71                                  BESTANDEN
  9.  Differenzierung: 25 von 45 Karten mit Bild (55 %),
      0 ohne Motiv, 0 leere Kaesten                                BESTANDEN   ← neu
  9b. Marktbild gegen die Rubriken: 12 Hebel, 0 widersprechen      BESTANDEN   ← neu
  1.  Oberhalb der Falz: 10 Geschichten (>= 6)                     BESTANDEN
  6.  Groesste Hochskalierung: 0 px                                BESTANDEN
  7.  Letztes Ressort beginnt bei 680 px (< 900)                   BESTANDEN
 10.  Dossier „Deutsche": 40 Treffer, 3 Monate im Verlauf,
      11 Bilder, 0 Karten ohne Motiv, 0 abgeschnittene Zeilen      BESTANDEN   ← neu
```

Kriterium 10 misst im **Browser**, nicht im HTML: bis auf das Suchfeld entsteht
die Dossier-Seite in `app.js`, nachdem der Index geladen ist. Eine statische
Prüfung sähe nur leere Behälter — genau die Sorte Prüfung, die am 06.08.2026
sechs falsche Zahlen durchgelassen hat. Der Suchbegriff wird aus dem Index
gezogen, nicht fest verdrahtet: ein fester Begriff wäre irgendwann ein Test,
der nur noch belegt, dass diese Firma nicht mehr vorkommt.

**Tests: 707** (vorher 673). Neu: `test_diff_bilder.py` (8),
`test_differenzierung_bericht.py` (8), `test_search_index.py` neu geschrieben
(13 statt 3), fünf neue Wahrheitstests in `test_seiten_zahlen.py`.

---

## 4. Was offen bleibt

1. **Die Bildausbeute der Differenzierung hängt an fremden Seiten.** 35 von 71
   lokal über reines HTTP. In Actions kommt nichts dazu (der Abruf ist
   dasselbe HTTP), aber der Bestand wächst — **nach dem nächsten Lauf die
   Zeile `Differenzierungs-Bilder:` im Protokoll ansehen.**
2. **Der neue Differenzierungs-Redakteur ist noch nie gegen ein echtes Modell
   gelaufen.** Bis dahin steht der Bericht vom 7.8. in der alten Gliederung
   zugeklappt am Seitenende. **Nach dem nächsten Lauf prüfen**, ob die drei
   Abschnitte ankommen (dann verschwindet der Aufklapper) und ob die
   H3-Überschriften wirklich die Hebel-Namen tragen.
3. **Zwei Bibliothek-Einträge raten Vodafone etwas** („ein Pendant in
   MeinVodafone ist denkbar", „Vodafone hat keinen kostenlosen
   Premium-KI-Assistenten … wäre ein sofort verständliches Signal"). Das ist
   Bestand, kein Regress: `textwerkzeug.ohne_vodafone_rat` greift über
   Modalverben, und diese zwei Sätze kommen ohne aus. Auf der Suchseite fallen
   sie jetzt nur stärker auf, weil die Karten größer sind.
4. Die Differenzierungs-Seite ist 13 200 px hoch (vorher 9060). Sie trägt jetzt
   71 Beispiele **mit Bild** plus die Auswertung; die Aufklapper halten den
   Schwanz zurück. Wenn das zu lang bleibt, ist die nächste Stellschraube
   `ZEILEN_OFFEN`, nicht die Zahl der Karten.
