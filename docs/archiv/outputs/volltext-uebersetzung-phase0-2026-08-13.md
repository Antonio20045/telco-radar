# Volltext-Übersetzung — Befundbericht Phase 0

Stand: 13. August 2026 · Gemessen, nicht geschätzt · **Keine Codeänderung an
der Pipeline.** Neu sind nur drei Messskripte unter `scripts/`.

Das Konzept (`claude/…`, von Antonio übergeben) verlangt: erst messen, dann so
wenig bauen wie möglich — und anhalten, bevor gebaut wird. Das ist hier
geschehen. Dieser Text ist die Grundlage für die Entscheidung über den
Zuschnitt der Phasen 1–3.

---

## Das Wichtigste in fünf Sätzen

1. **Die Kappung aufzuheben bringt fast nichts.** Nur 14,1 % der Teaser sind
   überhaupt länger als 600 Zeichen; echter Volltext steht dort in 9,7 %.
2. **Das ungelesene Feld `content:encoded` ist der große Hebel**: 45,2 % der
   Einträge haben eins, in 33,2 % steht Volltext.
3. **Zusammen deckt der Feed 40,6 % ab. Die restlichen 59,4 % gehen nur über
   den Abruf der Artikelseite** — der teure Weg ist also nicht vermeidbar,
   sondern der Normalfall.
4. **Fremdsprachig sind 15,2 %** der Einträge (202 von 1329), gemessen auf
   Titel plus echtem Teaser. Das sind rund **20–30 Meldungen je Lauf**.
5. **Der Artikelabruf funktioniert**: 12 von 12 fremdsprachigen Artikeln
   lieferten HTTP 200, 11 davon brauchbaren Fließtext — keine Sperre, keine
   Navigation im Extrakt.

---

## Messaufgabe 1 — Wie viele fremdsprachige Meldungen fallen an?

`scripts/miss_fremdsprachen.py`, gemessen über 15 Ausgaben, 810 Meldungen.

**Das Ergebnis dieser Messung ist unbrauchbar — und genau das ist ihr Wert.**

Im Berichts-JSON steht als einziges Feld in der Originalsprache das `title`.
`summary` ist bereits die deutsche Analystenfassung, `seen.jsonl` trägt seit
dem v2-Format nur Hashes. Das Archiv lässt also nur eine Messung auf der
**Überschrift** zu. Sie ergibt 23,2 % fremdsprachig — und ist falsch:

```
 it  Airtel Africa hires more investment banks for mobile money IPO
 fr  AT&T, Ericsson demonstrate drone-sensing 5G capabilities
 es  CMA clears Paramount-WBD deal
 fr  DT trials dual flying base stations
 it  Eurobites: CityFibre attacks Netomnia-Nexfibre deal (again)
 da  RCS Universal Profile 4.1: Stronger foundations for secure messaging
```

Alle sechs sind englisch. Eine Überschrift ist kurz und besteht großenteils
aus Eigennamen; darauf rät jede Spracherkennung.

> **Damit ist Premortem 4 belegt, bevor eine Zeile gebaut wurde.** Wer den
> roten Link an einer auf dem Titel geratenen Sprache aufhängt, zeigt ihn bei
> englischen Artikeln. Die Erkennung MUSS auf dem Fließtext laufen.

Die belastbare Zahl steht deshalb unter Messaufgabe 2.

---

## Messaufgabe 2 — Wie viel Text liefern die Feeds schon mit?

`scripts/miss_volltext_quellen.py --alle`, **140 RSS-Quellen wirklich
abgerufen, 1329 Einträge**, kein Modellaufruf, kein Schreiben nach
`data/state/`.

| Messung | Anzahl | Anteil |
|---|---:|---:|
| Teaser länger als die Kappung (> 600) | 187 | 14,1 % |
| Teaser ist selbst schon Volltext (≥ 1200) | 129 | 9,7 % |
| hat überhaupt ein `content:encoded` | 601 | 45,2 % |
| `content:encoded` ist Volltext (≥ 1200) | 441 | 33,2 % |
| **Volltext aus dem Feed (bestes Feld)** | **540** | **40,6 %** |
| **braucht den Abruf der Artikelseite** | **789** | **59,4 %** |

**Antonios Einwand war richtig gestellt, trifft aber das kleinere Ding.** Die
Kappung ist nicht der Engpass — sie schneidet bei 86 % der Einträge gar nichts
ab, weil der Teaser kürzer ist als 600 Zeichen. Der Hebel, den niemand gezogen
hat, ist das **nie gelesene Feld `content:encoded`**: es verdreifacht die
Ausbeute gegenüber dem reinen Aufheben der Kappung.

Aber auch beide Feed-Wege zusammen decken nur zwei von fünf Einträgen. **Der
Artikelabruf ist kein Rückfallweg für eine Minderheit, sondern der Hauptweg.**

### Sprachen (auf Titel plus echtem Teaser)

```
   en     1014   (76,3 %)        *  es   47      *  it   16
   de       99   ( 7,4 %)        *  pt   31      *  ro   11
   ?        14   ( 1,1 %)        *  fr   20      *  pl   10
                                 *  cs   20      *  tr   10, sv 10
```

**Fremdsprachig: 202 von 1329 = 15,2 %.** Bei 130–190 neuen Meldungen je Lauf
sind das grob **20–30 Übersetzungen je Ausgabe** — genug, dass die Funktion
sichtbar ist, und wenig genug, dass sie beherrschbar bleibt. Premortem 5 („es
gibt gar nicht so viele") ist damit ausgeräumt.

**Von den fremdsprachigen Einträgen tragen nur 43,1 % Volltext im Feed** —
für die Mehrheit führt kein Weg am Artikelabruf vorbei. Die französischen
Quellen zeigen das Muster besonders klar: zehn Einträge von Univers Freebox,
Teaser um 500 Zeichen, `content:encoded` durchweg leer.

---

## Messaufgabe 3 — Trägt eine Extraktionsbibliothek über die echten Seiten?

`scripts/miss_artikelabruf.py --fremd 12`, zwölf echte fremdsprachige Artikel
aus zwölf verschiedenen Quellen, je Quelle höchstens einer (sonst misst die
Stichprobe ein Layout statt zwölf).

| Quelle | Spr | HTTP | Teaser | Extrakt | Faktor |
|---|---|---:|---:|---:|---:|
| Univers Freebox | fr | 200 | 501 | 1672 | 3,3× |
| Xataka Móvil | es | 200 | 4335 | 4016 | 0,9× |
| ADSLZone | es | 200 | 2341 | 3212 | 1,4× |
| Corriere Comunicazioni | it | 200 | 417 | 13298 | 31,9× |
| TeleSíntese (BR) | pt | 200 | 253 | 2685 | 10,6× |
| TeleSemana (LatAm) | es | 200 | 15289 | 15277 | 1,0× |
| Telepolis (Polen) | pl | 200 | 923 | 2582 | 2,8× |
| Lupa (Tschechien) | cs | 200 | 349 | 2117 | 6,1× |
| digi.no (Norwegen) | nb | 200 | 45 | **141** | 3,1× |
| Mobile Time (Brasilien) | pt | 200 | 147 | 3855 | 26,2× |
| TELETIME (Brasilien) | pt | 200 | 360 | 1248 | 3,5× |
| DPL News (LatAm) | es | 200 | 139 | 1449 | 10,4× |

- **brauchbarer Fließtext (≥ 1200 Zeichen): 11 von 12**
- **nicht abrufbar (403/404): 0 von 12** — am Zugang scheitert nichts
- **mindestens doppelt so lang wie der Teaser: 9 von 12** (Premortem 1)
- **Sprache Teaser ≠ Sprache Volltext: 0 von 12** (Premortem 4)

Die Textproben sind echter Artikelanfang, keine Navigation, kein
Cookie-Banner — `trafilatura` mit `favor_precision=True` trägt über alle fünf
geprüften Sprachen. **Premortem 2 ist damit entschärft, aber nicht erledigt:**
zwölf Seiten sind eine Stichprobe, keine Garantie über 140 Quellen.

**Der eine Ausreißer trägt die wichtigste Lehre.** `digi.no` liefert 141
Zeichen — eine Paywall-Anrisszeile. Der Faktor 3,1× sieht gut aus, ist aber
gegen einen 45-Zeichen-Teaser gerechnet. **Eine Mindestlänge in absoluten
Zeichen ist Pflicht, ein Faktor allein genügt nicht.** Genau dieser Fall ist
Premortem 1: Antonio klickt, bekommt zwei Sätze, klickt nie wieder.

---

## Messaufgabe 4 — Struktur, gegengelesen

### Die Pipeline-Reihenfolge trägt Leitplanke B [BELEGT]

`pipeline.py`: `collect_all` (302) → `seen.filter_new` + `filter_fresh` (390)
→ `analyze_region` (509) → `seen.add` (1040). Zwischen Zeile 390 und 509 ist
Platz für den Volltextabruf, der nur neue, frische, fremdsprachige Meldungen
sieht. Wie im Konzept verlangt.

### Leitplanke A ist bereits erfüllt — die Sorge des Konzepts trifft nicht zu

Das Konzept warnt, ein neues Feld `volltext` lande „ohne weiteres Zutun in den
Analysten-Prompts". **Das ist nicht so.** `analyze/agents.py:172–181` baut die
Nutzlast Feld für Feld:

```python
rows.append({
    "title": item.title, "operator": …, "source": …, "date": …,
    "url": item.url, "snippet": item.summary[:300],
})
```

Das ist eine Positivliste. Ein neues Feld erscheint dort nur, wenn jemand es
einträgt. **Leitplanke A kostet keine Arbeit, sie muss nur nicht gebrochen
werden.**

Nebenbefund: **der Analyst sieht `summary[:300]`, nicht 600.** Die zweite,
strengere Kappung sitzt an der Stelle, an der das Prompt-Argument gilt — die
600 im Collector werden davon gar nicht getragen.

### Die 600 Zeichen bleiben unbegründet — und zwar prüfbar unbegründet

Der Auftrag verlangt, die Begründung im `git log` zu suchen. **Das ist in
dieser Sandbox nicht beantwortbar: das Repo ist ein flacher Klon** (58
Commits, `.git/shallow` vorhanden). `git log -S "summary[:600]"` findet genau
einen Commit (`d212f7c`, 08.08.2026) — und derselbe Commit gilt als
Ersteinführung der Datei. Das ist ein Artefakt der Klontiefe, keine Historie.

Wer die Frage beantworten will, braucht einen vollständigen Klon
(`git fetch --unshallow`). **Bis dahin gilt die Kappung als unbegründet, nicht
als begründet** — nach den Messungen oben ist das aber auch fast gegenstandslos:
sie aufzuheben bringt 14,1 %, und wenn der Volltext ohnehin in einem eigenen
Feld landet, muss `summary` gar nicht angefasst werden.

### §2.3 — Was die Analysten heute sehen [BELEGT, und es ist ein eigener Befund]

Die Vermutung des Konzepts stimmt. `parse_newsroom_html` setzt `summary` nicht;
nur der Sonderpfad `_extract_datamodel_articles` (Zeile 342) tut es.

| Quellentyp | Anzahl | Was der Analyst sieht |
|---|---:|---|
| `rss` | 97 (+43 als `trade_press`) | Titel + bis zu 300 Zeichen Teaser |
| `json_api` | 15 | Titel + Teaser |
| **`newsroom`** | **41** | **nur die Überschrift** |
| **`newsroom_js`** | **11** | **nur die Überschrift** |

**52 von 164 crawlbaren Quellen — knapp ein Drittel — liefern Meldungen, die
allein aus ihrer Überschrift bewertet, eingeordnet und im Wochenbericht
beschrieben werden.** Das ist unabhängig von diesem Feature ein
Qualitätsbefund, und es ist der Punkt, an dem ein Volltextabruf am meisten
brächte: nicht für die Übersetzung, sondern für den Bericht selbst.

Das ist aber, wie das Konzept richtig sagt, **eine eigene Entscheidung mit
eigenen Kosten** und darf kein Nebeneffekt sein. Sie steht unten als Frage 2.

### Nebenbefund [BELEGT]

`Item.from_dict` (`models.py:72–83`) übernimmt `image_url` nicht — ein aus
einem Dict wiederhergestelltes Item verliert sein Feed-Bild. Wie im Konzept
vorgesehen: **gemeldet, nicht nebenbei gefixt.** Phase 1 fasst die Methode
ohnehin an (`volltext`, `sprache`), dann gehört es dazu.

---

## Was daraus für den Zuschnitt folgt

Der Vorschlag des Konzepts, den Artikelabruf als „Rückfallweg für die
Minderheit" zu bauen, **trägt nach diesen Zahlen nicht**: 59,4 % aller und
56,9 % der fremdsprachigen Einträge brauchen ihn. Er ist der Hauptweg und
muss von Anfang an robust sein.

Umgekehrt ist der billige Teil billiger als gedacht: `content:encoded` ist
ein zusätzliches Feld im bestehenden Parser, kein neuer HTTP-Weg, und liefert
sofort ein Drittel.

**Vorgeschlagene Reihenfolge — zur Freigabe, nicht schon umgesetzt:**

1. **`content:encoded` lesen** und in ein neues, ungekapptes Feld `volltext`
   legen. `summary` bleibt bei 600, die Analysten-Prompts bleiben unangetastet.
   Kostet keinen einzigen zusätzlichen Abruf. Deckt 33 %.
2. **Spracherkennung auf `volltext or summary`, nie auf dem Titel.** Grenzfälle
   (schwacher Score, zu kurzer Text) gelten als unbekannt und bekommen keinen
   Link.
3. **Artikelabruf mit `trafilatura`** für neue, frische, fremdsprachige Items
   ohne Volltext — hinter dem Seen-Filter, über das vorhandene `collect/http.py`
   samt HostGate. Mit **absoluter Mindestlänge** (Vorschlag: 1200 Zeichen UND
   mindestens doppelter Teaser), sonst kein Link.
4. Erst danach Übersetzung, Seite, roter Link (Phase 2) und Deckelung (Phase 3).

Schritt 1 und 2 sind risikoarm und sofort messbar. Schritt 3 ist der, bei dem
sich entscheidet, ob das Feature trägt.

---

## Offene Fragen an Antonio

1. **Soll der rote Link auch im Newsletter erscheinen?** (Frage aus dem
   Konzept, unverändert offen.)
2. **Sollen die Analysten künftig mehr sehen als die Überschrift?** 52 der 164
   Quellen liefern ihnen heute nichts als den Titel. Der Volltextabruf aus
   Schritt 3 würde den Stoff bereitstellen — ihn in die Prompts zu geben ist
   aber eine eigene Entscheidung mit eigener Laufzeit- und Token-Rechnung, und
   sie gehört nicht als Nebeneffekt in dieses Feature.
3. **Obergrenze je Lauf?** Bei rund 20–30 Übersetzungen je Ausgabe und ~57 %
   davon mit zusätzlichem Abruf sind das grob 12–17 zusätzliche HTTP-Aufrufe
   und 20–30 Übersetzungsaufrufe. Das ist beherrschbar, aber es sollte eine
   Zahl in `settings.yaml` geben, auf die man sich verlassen kann.

---

## Die Skripte

| Skript | Was es misst | Netz | LLM |
|---|---|---|---|
| `scripts/miss_fremdsprachen.py` | Fremdsprachenanteil über das Berichtsarchiv (nur Titel — siehe Warnung im Modulkopf) | nein | nein |
| `scripts/miss_volltext_quellen.py` | Teaserlänge, `content:encoded`, Sprache je Feed; `--alle`, `--nur-fremd` | ja | nein |
| `scripts/miss_artikelabruf.py` | Artikelabruf + `trafilatura`-Extraktion; `--fremd N`, `--urls datei` | ja | nein |

`py3langid` und `trafilatura` sind für die Messung installiert worden und
stehen **noch nicht** in `requirements.txt` — das gehört in Phase 1, wenn
entschieden ist, dass sie bleiben.
