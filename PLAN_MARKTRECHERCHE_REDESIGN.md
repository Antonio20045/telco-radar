# Plan: Redesign der Marktrecherche

> Lies zuerst `CLAUDE.md` (Architektur, Zugänge, Fallstricke), dann diesen
> Text. Er betrifft **nur den Anwendungsfall Marktrecherche** — also
> `site/index.html`, `bericht.html`, `differenzierung.html`,
> `wettbewerber.html`, `protokoll.html`, `archive.html`, `sources.html`,
> `suche.html` und alles, was `report/html.py` dafür rendert. Die Promo
> Übersicht (`site/promo/`) ist ein eigener Anwendungsfall und bleibt
> unangetastet.
>
> Stand der Messungen: 6. August 2026, gegen den ausgelieferten `site/`-Stand
> und `data/reports/2026-08-05.json` (Lauf vom 5. August: 167 Quellen
> abgefragt, 2761 Meldungen gesammelt, 426 neu, 92 bewertet).
> Alle Zahlen in diesem Text sind gemessen, nicht geschätzt. Abschnitt 10
> enthält die Befehle, mit denen man sie nachrechnet.

> **NACHTRAG vom 06.08.2026, nach der Umsetzung.** Dieser Plan hat den
> falschen Schnitt gemacht. Er plant Korrektheit und Seitenarchitektur und
> **verbietet in Abschnitt 5 und 9 ausdrücklich die visuelle
> Neugestaltung** — im Pre-Mortem steht eine neue Designsprache sogar als
> Fehlschlag-Szenario. Genau die war gefragt: eine Zeitung im Sinn von WSJ,
> kein Dashboard. Deshalb gibt es jetzt eine **Etappe 4 (Abschnitt 4.5)**,
> und Abschnitt 5 ist entsprechend korrigiert. Etappen 0–3 gelten
> unverändert und sind umgesetzt; die Schlussliste steht in
> `outputs/redesign-2026-08-06.md`.
>
> **Lehre für den nächsten Plan:** „was ausdrücklich bleibt" ist der
> gefährlichste Abschnitt eines Plans. Er hält fest, was niemand hinterfragt
> hat — und wenn der Auftraggeber genau das ändern wollte, hat der Plan die
> Frage nie gestellt.

---

## 0. Kurzfassung

Die Marktrecherche hat kein Optikproblem. Sie hat drei Probleme, die eine
neue Optik nur besser aussehen lassen würde:

1. **Vier Zahlen auf der ausgelieferten Seite sind falsch**, und eine ganze
   Unterseite ist seit zwei Läufen leer, ohne dass es jemand gemerkt hat.
2. **Der Wochenbericht ist das Herzstück und liegt als 2863-Wort-Block ohne
   Einstieg da**, während die 92 Belege dahinter in einem zugeklappten
   `<details>` mit der Aufschrift „bei Bedarf öffnen" stehen.
3. **Sieben Unterseiten für eine Frage**, von denen drei reine
   Arbeitsnachweise sind und eine dauerhaft leer.

Die Reihenfolge des Umbaus ergibt sich daraus: **erst die Wahrheit, dann die
Struktur, dann die Optik.** Etappe 0 ist unabhängig von allem anderen und
sollte auch dann ausgeliefert werden, wenn der Rest des Plans liegen bleibt.

---

## 1. Befund — was heute wirklich ausgeliefert wird

### 1.1 Vier Zahlen stimmen nicht

| Wo | Was dort steht | Was stimmt | Ursache |
|---|---|---|---|
| `protokoll.html`, Kachel | **426** „neue Meldungen bewertet" | 426 waren *neu*, **92** wurden *bewertet* | Kachel liest `report.stats.new`, das Label sagt „bewertet" (`protokoll.html.j2:19`) |
| `bericht.html`, Überschrift | „**Alle** Signale dieser Woche" | zeigt **6** von 92 | `html.py:558` kappt auf `relevance >= 4` und dann `[:6]` |
| `wettbewerber.html` | „Für diesen Lauf liegt noch keine Wettbewerber-Detailanalyse vor. Sie entsteht beim nächsten Lauf" | Der Lauf **hat** stattgefunden und ist gescheitert | siehe 1.2 |
| `bericht.html`, Regionale Auswertung | Europa: **0** relevant | stimmt — aber die Seite erklärt nicht, dass das ein Tagging-Fehler ist, kein leerer Markt | `tag_news_regions`, siehe Abschnitt 6 |

Das ist die schwerste Kategorie. Eine Seite, die für Manager ohne
Technikhintergrund gebaut ist und die Nachprüfbarkeit ausdrücklich verspricht,
darf keine Zahl tragen, die etwas anderes bedeutet als ihr Label.

### 1.2 Die Wettbewerber-Seite ist seit dem 4. August leer

Nicht „noch nicht befüllt" — **kaputt**, und die Seite behauptet das Gegenteil.

```
2026-07-26  Deutsche Telekom 442 Zeichen / 6 Moves   Telefónica 546/6   1&1 571/6
2026-07-27  471/6   738/6   376/5
2026-07-28  638/6   656/8   490/6
2026-07-31  525/6   695/7   541/8
2026-08-04  0/0     0/0     0/0      <-- ab hier leer
2026-08-05  0/0     0/0     0/0
```

Das Laufprotokoll vom 5. August nennt den Grund fast wörtlich:

```
Wettbewerber-Analyse   0.6 s   3 Profile (0 Moves)
```

0,6 Sekunden für drei LLM-Aufrufe heißt: alle drei sind sofort gescheitert.
Die Zuordnung funktioniert weiterhin (16 / 16 / 11 gematchte Meldungen), es
bricht im Aufruf oder beim JSON-Parsen. `competitors.py:89` fängt den Fehler
mit `log.error` ab und gibt ein leeres Profil zurück, `pipeline.py:445` fängt
noch einmal ab — der Lauf gilt danach als erfolgreich, und die Seite erklärt
dem Leser, es liege am nächsten Lauf.

**Zweiter Befund derselben Seite:** `focus_competitors` in
`config/settings.yaml:297` sind Deutsche Telekom, Telefónica/O2 und 1&1 —
drei deutsche Anbieter, in einem Produkt, das laut
`scripts/quellen_zaehlen.py` 95 Betreiber in sechs Regionen beobachtet
(im Lauf vom 5. August waren es 87). Die Überschrift „Wettbewerber im Detail" verspricht etwas, das
diese Seite konstruktionsbedingt nie einlösen kann.

### 1.3 Der Bericht ist da, aber nicht lesbar gemacht

- `data/reports/2026-08-05.md`: **2863 Wörter**, elf `##`-Abschnitte.
- Auf `bericht.html` landet das als **ein** Prosablock in einer Karte. Kein
  Inhaltsverzeichnis, keine Ankerlinks, keine Sprungmarken.
- Der Abschnitt „Global" allein hat **926 Wörter** (32 % des Berichts) — Folge
  desselben Tagging-Problems wie in 1.1.
- Die Seite ist **120 KB**, davon **78,5 KB** eingebetteter Explorer-JSON,
  der nur gebraucht wird, wenn jemand das `<details>` aufklappt.

Für die Zielgruppe („Manager OHNE KI-/Technik-Hintergrund", CLAUDE.md §1) ist
das ein 12-Minuten-Text ohne Einstieg.

### 1.4 Der Nachweis fehlt genau dort, wo er versprochen wird

`suche.html` durchsucht `search_index.json`. Der Index enthält heute **452
Einträge**: 402 Bericht-Highlights aus **allen** archivierten Wochen plus 50
Einträge der Differenzierungs-Bibliothek.

Im Lauf vom 5. August wurden **2761 Meldungen gesammelt** und **92 bewertet**.
Der Index kennt nur die bewerteten. Wer nach einem Anbieter sucht, dessen
Meldung gesammelt, aber nie einem Analysten vorgelegt wurde, bekommt null
Treffer — und keinen Hinweis darauf, dass es die Meldung gibt.

Das ist kein Suchfehler, sondern eine Erwartungslücke: die Seite sagt „Alle
Bericht-Highlights aus jeder archivierten Woche". Genau das tut sie. Nur liest
niemand „Highlights" als „7 % dessen, was der Radar gesehen hat".

### 1.5 Toter Code im Renderer

Alles Folgende ist im Repo, läuft bei jedem Rendern mit und erscheint auf
keiner Seite:

| Was | Wo | Status |
|---|---|---|
| `_bar_chart_svg()` | `html.py:188` | definiert, **nie aufgerufen** |
| `sov`, `pricing`, `deals`, `risks`, `chances` | `html.py:354–453` | berechnet, in **keiner** Vorlage referenziert |
| `briefing_sections` | `html.py:572` | berechnet, in den Kontext gereicht, **keine** Vorlage nutzt es |
| `analyze/idea_radar.py` | Modul + `tests/test_idea_radar.py` | von Pipeline und Vorlagen **nie** aufgerufen |
| `_stats()` je Archivbericht | `html.py:570` | läuft für **jeden** Bericht, das Ergebnis wird nur für `i == 0` benutzt |
| `_strip_vodafone_advice()` | `html.py:308` | entfernt einen Abschnitt, den der heutige Editor **nicht mehr schreibt** (im 05.08.-Bericht kein „Handlungsempfehlungen") |

Das ist kein Schönheitsproblem: Wer `html.py` liest, um etwas zu ändern, muss
erst herausfinden, welche Hälfte davon überhaupt noch etwas bewirkt.

### 1.6 Die Übergabedoku beschreibt eine andere Website

`CLAUDE.md` §5 beschreibt die Berichtsseite als „Bloomberg-Terminal-Stil":
Dark-Theme mit Light-Toggle, Headline-Ticker, Erklär-Box, vier nummerierte
Abschnitte **01**–**04**, SVG-Charts.

Ausgeliefert wird das Gegenteil: warmer Cream-Canvas (`--bg:#faf8f5`), roter
Topbar, keine Charts, kein Ticker, keine Erklär-Box, **0** Vorkommen von
`prefers-color-scheme` in 649 Zeilen CSS. Der Kommentarkopf der CSS-Datei
nennt sie „Design-Modernisierung (Juli 2026)".

Beide Beschreibungen im Repo, beide behaupten den aktuellen Stand. Wer
CLAUDE.md §5 folgt, baut eine **dritte** Designsprache.

---

## 2. Diagnose: drei Ursachen, nicht siebzehn Fehler

**Ursache A — Es gibt keine Prüfung, die eine Zahl auf der Seite gegen die
Daten hält.** 37 Testdateien, davon berühren **zwei** `render_site()`
(`test_html_escaping.py`, `test_suche_page.py`), und beide prüfen Form, nicht
Inhalt. Deshalb konnte die Wettbewerber-Seite zwei Läufe lang leer sein und
`pytest -q` blieb grün.

**Ursache B — Die Seiten sind nach Datenherkunft geschnitten, nicht nach der
Frage des Lesers.** Übersicht und Bericht kommen aus derselben Berichtsdatei
und verlinken sich gegenseitig; Explorer, Suche und Archiv sind dreimal
dasselbe Bedürfnis („zeig mir die Einzelmeldung") an drei Orten; Protokoll und
Quellen sind zweimal dasselbe Versprechen („du kannst das nachprüfen").

**Ursache C — Nichts wurde je zurückgebaut.** Jede Session hat etwas
hinzugefügt. `_bar_chart_svg`, `sov`/`pricing`/`deals`, `idea_radar.py` und
`_strip_vodafone_advice` sind Rückstände von vier verschiedenen Ausbaustufen.

---

## 3. Zielbild: vier Seiten statt sieben

Geschnitten nach der Frage, die der Leser stellt:

| Frage | Seite | Was drin ist | Kommt heute von |
|---|---|---|---|
| „Was ist diese Woche passiert?" | **`index.html` — Diese Woche** | Leitmeldung, vier Kennzahlen, Kurzfazit, **der volle Prosabericht mit Sprungnavigation** | `index.html` + `bericht.html` |
| „Zeig mir die Einzelmeldung / such mir X" | **`meldungen.html` — Meldungen** | alle bewerteten Meldungen dieser Woche, filterbar, **plus** Suche über alle Wochen, **plus** Wochenarchiv | Explorer-`<details>` + `suche.html` + `archive.html` |
| „Womit heben sich Telkos ab?" | **`differenzierung.html`** | unverändert — eigene, persistente Bibliothek, eigene Frage | bleibt |
| „Kann ich dem Ding trauen?" | **`transparenz.html`** | Quellen je Region/Ebene **und** Laufprotokoll auf einer Seite | `sources.html` + `protokoll.html` |

**`wettbewerber.html` verschwindet aus der Navigation.** Nicht weil die Idee
schlecht ist, sondern weil eine Seite, die eine Deutschland-Auswahl als
„Wettbewerber im Detail" ausgibt und seit zwei Läufen leer ist, schlechter ist
als keine Seite. Entscheidungsregel:

- Wird der Fehler aus 1.2 in Etappe 0 behoben und liefert der nächste echte
  Lauf wieder Profile mit Text, wird daraus ein **Block „Deutschland-Fokus"
  auf der Wochenseite** — mit ehrlicher Überschrift.
- Wird er nicht behoben, fliegt der Navigationseintrag raus, bevor die neue
  Struktur ausgeliefert wird. Eine leere Seite im Menü ist keine Option.

Die Archivseiten je Woche (`site/reports/<datum>.html`) bleiben als
Direktlinkziel bestehen und benutzen dieselbe Vorlage wie die Wochenseite.

---

## 4. Umbau in vier Etappen

### Etappe 0 — Wahrheit herstellen (keine Optik, kein Layout)

Unabhängig vom Rest. Auch einzeln auslieferbar.

1. **Protokoll-Kachel korrigieren.** Zwei Zahlen statt einer: `N neu` und
   `M bewertet`. Wenn M deutlich kleiner ist als N, gehört ein Satz daneben,
   der erklärt warum — das ist kein Makel, sondern das Funktionsprinzip.
2. **„Alle Signale dieser Woche" wird wahr.** Entweder alle bewerteten
   Meldungen zeigen, oder die Überschrift auf das benennen, was sie zeigt
   („Die 6 dringendsten"). Kappung und Titel müssen zusammenpassen.
3. **Wettbewerber-Fehler diagnostizieren.** Der Log nennt ihn; er ist nicht
   zu raten. Ein Lauf mit `--no-llm` reicht dafür nicht, aber die
   Fehlermeldung steht im Actions-Log des Laufs #75 unter
   „Competitor analysis failed for …".
4. **Leerzustände dürfen nicht lügen.** Kein „entsteht beim nächsten Lauf",
   wenn der Lauf schon war. Wenn ein Zweig gescheitert ist, sagt die Seite
   das — mit Datum des Laufs.
5. **Wahrheitstests.** Neue Testdatei `tests/test_seiten_zahlen.py`: rendert
   eine Fixture-Site und prüft, dass die Kennzahlen auf den Seiten den
   Fixture-Daten entsprechen. Mindestens: Zahl der gezeigten Meldungen gegen
   `len(highlights)`, Protokoll-Kacheln gegen `stats`, und dass die
   Wettbewerber-Seite bei vorhandenen Profilen **nicht** den Leertext zeigt.
   Ohne diese Tests wiederholt sich 1.2 in vier Wochen.

### Etappe 1 — Seitenarchitektur

6. `meldungen.html` bauen: Explorer aus dem `<details>` befreien, Suche und
   Archiv dort integrieren. Der Explorer-JSON zieht von `bericht.html` hierher
   um — die Wochenseite verliert damit 78,5 KB.
7. `transparenz.html` bauen: `sources.html` und `protokoll.html`
   zusammenlegen. Reihenfolge: erst was beobachtet wird, dann was der letzte
   Lauf daraus gemacht hat.
8. Navigation von sieben auf vier Einträge, Weiterleitungen von den alten
   Dateinamen (die alten Links sind in Mails und Lesezeichen).
9. **Abnahmeliste je zusammengelegter Seite:** jeder Baustein der alten Seite
   bekommt eine Zeile mit seinem neuen Ort oder einer Begründung, warum er
   entfällt. Ohne diese Liste keine Zusammenlegung.

### Etappe 2 — Der Bericht wird lesbar

10. Wochenseite bekommt oben die 30-Sekunden-Schicht (Leitmeldung, vier
    Kennzahlen, Kurzfazit) und darunter den vollen Bericht.
11. **Sprungnavigation über die `##`-Abschnitte.** `_briefing_sections()`
    berechnet die Gliederung heute schon und wirft sie weg (1.5) — sie wird
    zum Inhaltsverzeichnis mit Ankern. Kein neuer Code, nur anschließen.
12. Jeder Abschnitt bekommt einen Anker (`#global`, `#asien`, …), damit man
    aus Mails direkt in einen Abschnitt verlinken kann.
13. Lesezeit und Abschnittszahl in der Kopfzeile des Berichts.

### Etappe 3 — Ballast und Konsistenz

14. Toter Code aus 1.5 raus: `_bar_chart_svg`, `sov`/`pricing`/`deals`/
    `risks`/`chances`, `_stats()`-Aufruf für Archivberichte (nur noch für den
    aktuellen), `_strip_vodafone_advice` mit Begründung im Kommentar behalten
    **oder** entfernen — aber nicht stillschweigend beides.
15. `analyze/idea_radar.py`: anschließen oder löschen. Ein Modul mit Tests,
    das nie aufgerufen wird, ist eine Falle für die nächste Session.
16. **`CLAUDE.md` §5 korrigieren.** Die ausgelieferte Designsprache gewinnt;
    der Bloomberg-Terminal-Absatz beschreibt eine Website, die es nicht mehr
    gibt.

---

### Etappe 4 — Visuelle Neugestaltung (nachgetragen)

Nicht Teil der ursprünglichen Fassung; siehe Nachtrag oben.

17. **Zeitungssatz statt Dashboard.** Serife (Source Serif 4) für alles, was
    gelesen wird; Grotesk (Libre Franklin) nur für Etiketten. Linien statt
    Kästen — keine Schatten, kein Radius. Rot ist Akzent, keine Fläche.
    Newsprint statt Weiß.
18. **Zeitungskopf**: mittiges Wortzeichen, Datumszeile (Ausgabe / Ressort /
    Quellenzahl), Rubrikleiste unter schwerer Linie.
19. **Titelseite als Titelseite**: Schlagzeile, Aufmacher, darunter
    zweispaltig — Fließtext mit Initial links, Rail mit Zahlen, dringendsten
    Signalen und Themenradar rechts. Spaltensatz für „Auf einen Blick",
    Druck-Stylesheet.
20. **Die Regel aus Abschnitt 5 wird damit aufgehoben** — nicht
    stillschweigend, sondern hier notiert.

## 5. Designregeln — was bleibt (korrigiert am 06.08.2026)

- ~~**Die Cream-/Rot-Designsprache aus `style.css` bleibt.**~~ **Aufgehoben
  am 06.08.2026.** Sie war genau das, was weg sollte. Es gilt jetzt die
  Zeitungsausgabe (Etappe 4); die Regeln dazu stehen im Kopf von
  `style.css` und in `CLAUDE.md` §5.
- **Der Prosabericht bleibt das Herzstück** (CLAUDE.md §8). Der Umbau macht
  ihn zugänglicher, er ersetzt ihn nicht durch Kacheln.
- **Jede Aussage behält ihren Quellenlink.** Nachprüfbarkeit war explizite
  Anforderung.
- **Keine Fachbegriffe ohne Erklärung**, deutsche Labels.
- **Kein CDN-JS, kein Framework.** Vanilla wie bisher.
- **`site/` wird nie von Hand bearbeitet.** Änderungen gehören in
  `report/templates/` und `report/html.py`.
- Dark-Mode ist **kein** Ziel dieses Plans. Er steht in CLAUDE.md §5 als
  Bestandsbeschreibung, ist aber nie gebaut worden (0 `prefers-color-scheme`).
  Wenn er gewünscht ist, gehört er in einen eigenen Auftrag.

---

## 6. Die Abhängigkeit, die dieser Plan nicht löst

**Die Vorgabe-Region für Fachpressequellen** (CLAUDE.md §9, Schritt 1) ist
nicht Teil dieses Umbaus — aber sie bestimmt, wie das Ergebnis aussieht.

Heute ordnet `tag_news_regions` eine Fachpresse-Meldung nur dann einer Region
zu, wenn ein Betreibername in der Überschrift steht. Ergebnis im Lauf vom
5. August: **Global 62 von 92 bewerteten Meldungen, Europa 0.**

Das hat zwei Konsequenzen für diesen Plan:

1. **Region darf kein Navigationselement erster Ordnung werden.** Ein
   Regionsfilter, der bei „Europa" leer läuft, ist schlechter als keiner.
2. **Die Sprungnavigation aus Etappe 2 macht das Ungleichgewicht sichtbar** —
   ein Inhaltsverzeichnis, in dem „Global" 926 Wörter hat und Europa gar
   nicht vorkommt, ist ein Befund, kein Darstellungsfehler. Das ist gewollt.
   Es soll auffallen.

---

## 7. Pre-Mortem

Angenommen, der Umbau ist fertig und war ein Fehlschlag. Warum?

1. **„Wir haben die Optik umgebaut und die Zahlen lügen weiter."**
   Wahrscheinlichster Fall. Gegenmittel: Etappe 0 zuerst, und sie darf nicht
   „mitgemacht" werden — sie wird eigens abgenommen.
2. **„Beim Zusammenlegen sind Inhalte verschwunden."** `sources.html` hat
   einen erklärenden Vorspann über drei Signalebenen, den außer dieser Seite
   niemand trägt. Gegenmittel: die Abnahmeliste aus Schritt 9.
3. **„Jemand hat CLAUDE.md §5 gelesen und eine dritte Designsprache
   gebaut."** Gegenmittel: Schritt 16 gehört in dieselbe Auslieferung wie der
   Umbau, nicht ans Ende.
   **Eingetreten, in der eigenen Umsetzung:** CLAUDE.md §5 wurde nach Etappe 3
   auf den Cream-Stand gezogen — und Etappe 4 hat genau den ersetzt. Die
   Doku beschrieb danach wieder eine Website, die es nicht gibt. Der
   Pre-Mortem war richtig, die Gegenmaßnahme (§5 zuletzt schreiben) falsch:
   **die Designbeschreibung gehört in denselben Commit wie die letzte
   Designänderung, nicht in den letzten Commit des Plans.**
4. **„Die Wochenseite ist jetzt riesig."** 120 KB Bericht plus 12 KB
   Übersicht klingt nach 132 KB. Es sind ~45 KB, weil der Explorer-JSON
   (78,5 KB) auf `meldungen.html` umzieht. **Diese Zahl ist nach dem Umbau
   nachzumessen**, nicht anzunehmen.
5. **„Der Suchindex ist zu groß geworden."** Heute 296 KB bei 452 Einträgen
   und 205 konfigurierten Quellen. Der Ausbau auf 1000 Quellen
   (`AUFTRAG_1000_QUELLEN_WELLE3.md`) vervielfacht das. Gegenmittel: **Grenze
   jetzt festlegen** — ab 1 MB wird der Index je Jahr geteilt und nachgeladen.
   Nicht jetzt bauen, aber jetzt entscheiden und in den Code schreiben.
6. **„Tests grün, Seite kaputt."** Genau das ist am 4. August passiert.
   Gegenmittel: Schritt 5.

---

## 8. Abnahme

Ohne diese Punkte ist der Umbau nicht fertig:

1. Keine Zahl auf einer Seite widerspricht der zugrundeliegenden
   Berichtsdatei. Belegt durch `tests/test_seiten_zahlen.py`, nicht durch
   Augenschein.
2. Die Wettbewerber-Frage ist entschieden: Profile sind wieder da **oder**
   der Navigationseintrag ist weg. Kein Zwischenzustand.
3. Vier Navigationseinträge. Alte URLs leiten weiter.
4. Die Wochenseite hat eine Sprungnavigation über alle `##`-Abschnitte des
   Berichts, jeder Abschnitt ist direkt verlinkbar.
5. Für jeden Baustein der drei aufgelösten Seiten gibt es eine Zeile mit
   neuem Ort oder Begründung für den Wegfall.
6. Der tote Code aus 1.5 ist entfernt oder angeschlossen — nichts bleibt in
   der Schwebe.
7. `CLAUDE.md` §5 beschreibt die Seite, die wirklich ausgeliefert wird.
8. `PYTHONPATH=src pytest -q` grün.
9. Seitengrößen vor/nach gemessen und im Abschlussbericht genannt.
10. Auf der Live-Site verifiziert, nicht nur lokal — der Push→Hook-Race
    braucht die 15 s Wartezeit (CLAUDE.md §6).

---

## 9. Ausdrücklich nicht

- **Keine Änderung an der Sammel-, Delta- oder Analyseschicht.** Dieser Plan
  betrifft `report/`, nicht `collect/` oder `analyze/`. Ausnahme: der
  Wettbewerber-Fehler aus 1.2, weil er eine Seite leer lässt.
- ~~**Keine dritte Designsprache**~~ — aufgehoben, siehe Etappe 4.
- **Kein Dark-Mode.** Gilt weiter, auch nach Etappe 4.
- **Keine neue Kappung von Meldungen.** Was nicht bewertet wird, ist über den
  Seen-Store dauerhaft verloren (CLAUDE.md §6). Die Anzeige darf kappen, die
  Pipeline nicht.
- **Kein Anfassen der Promo Übersicht.** Eigener Anwendungsfall, eigene
  Pipeline, eigener State.
- **`data/state/` und `data/reports/` nicht aus lokalen Testläufen
  committen** — sonst findet der nächste Actions-Lauf null neue Meldungen.
- **Keine Zahl schätzen.** Jede Zahl in der Abschlussmeldung kommt aus einem
  Skript, einer Berichtsdatei oder einem Laufprotokoll.

---

## 10. Nachmessen — die Befehle

Alle Zahlen dieses Plans sind so entstanden:

```bash
# Quellenstand (die einzige gültige Zahl)
PYTHONPATH=src python scripts/quellen_zaehlen.py

# Bewertete Meldungen je Region gegen stats.new des letzten Laufs
python3 -c "
import json; d=json.load(open('data/reports/2026-08-05.json'))
print('stats', d['stats'])
print({k: len(v.get('highlights') or []) for k,v in d['regions'].items()})
print('bewertet gesamt', sum(len(v.get('highlights') or []) for v in d['regions'].values()))"

# Wettbewerberprofile über die letzten Läufe (zeigt den Ausfall ab 04.08.)
python3 -c "
import json,glob
for f in sorted(glob.glob('data/reports/2*.json'))[-6:]:
    d=json.load(open(f))
    print(f[-15:], [(c['name'], len(c.get('summary') or ''), len(c.get('moves') or []))
                    for c in d.get('competitors') or []])"

# Was die Seite wirklich zeigt
grep -c 'class="signal-row"' site/bericht.html          # 6
grep -o '<b>[0-9]*</b><span>neue Meldungen bewertet</span>' site/protokoll.html

# Berichtslänge je Abschnitt
python3 -c "
import re; t=open('data/reports/2026-08-05.md',encoding='utf-8').read()
p=re.split(r'(?m)^## (.+)$',t)
[print(p[i], len(p[i+1].split())) for i in range(1,len(p),2)]"

# Suchindex
python3 -c "
import json,collections
i=json.load(open('site/search_index.json'))
print(len(i), collections.Counter(e['kind'] for e in i))"

# Toter Code gegenprüfen
grep -rn "_bar_chart_svg\|briefing_sections\|idea_radar" --include="*.py" --include="*.j2" src/
grep -rn "\.sov\|\.pricing\|\.deals\|\.risks\|\.chances" --include="*.j2" src/

# Seitengrößen vor/nach
du -h site/*.html site/search_index.json
```

---

## 11. Reihenfolge

1. **Etappe 0** — eigenständig, sofort auslieferbar, eigene Abnahme.
2. **Etappe 3, Schritt 16** (CLAUDE.md §5) — vor Etappe 1, damit niemand
   während des Umbaus der falschen Beschreibung folgt.
3. **Etappe 1**, dann **Etappe 2**.
4. **Etappe 3** zum Schluss, mit einem echten Lauf dazwischen.

Etappe 0 und Schritt 16 sind zusammen ein halber Tag und beheben die
Befunde, die dem Leser am meisten schaden. Alles danach ist Komfort.
