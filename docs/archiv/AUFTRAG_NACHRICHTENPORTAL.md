# Auftrag: aus der Seite ein echtes Nachrichtenportal machen

> Lies zuerst `CLAUDE.md` (Architektur, Zugänge, Fallstricke), dann diesen
> Text. **Dieser Text ist der Auftrag.** Er löst
> `PLAN_MARKTRECHERCHE_REDESIGN.md` ab, der abgearbeitet ist
> (`outputs/redesign-2026-08-06.md`).
>
> Stand: 6. August 2026, gemessen an der Ausgabe vom 6.8. (205 Quellen,
> 3376 gesammelt, 642 neu, 193 relevant) und am ausgelieferten `site/`.
> Live: https://telco-radar.onrender.com

---

## 0. Lies das zuerst: warum die letzte Session gescheitert ist

Antonio hat **fünfmal** gesagt, er will ein Nachrichtenportal im Sinn des
Wall Street Journal. Nach fünf Runden sagte er: *„Mir gefällt die Seite immer
noch überhaupt nicht."* Das lag nicht an fehlender Arbeit — es wurden sechs
Etappen ausgeliefert, 442 Tests laufen grün — sondern an drei Denkfehlern:

1. **Der Plan verbot das Ziel.** Die letzte Session schrieb sich selbst einen
   Plan, dessen Abschnitt 5 lautete „Die Cream-/Rot-Designsprache **bleibt**"
   und dessen Abschnitt 9 „keine dritte Designsprache" verbot. Im Pre-Mortem
   stand eine neue Designsprache sogar als *Fehlschlag-Szenario*. Danach
   wurde vier Etappen lang Korrektheit repariert, während der Auftrag Optik
   war. **Schreib keinen Plan, der das Ziel ausschließt.**
2. **Einzelne Symptome statt der Struktur.** Auf „sieht nicht aus wie eine
   Zeitung" folgte: Serifenschrift, dann Logo, dann Bilder, dann Schlagzeilen
   — jedes Mal ein Symptom, nie das Raster. Eine Zeitungsseite entsteht
   nicht aus Schriftart plus Bild, sondern aus einem **Raster mit
   Gewichtung**: eine Geschichte dominiert, drei sind mittel, zwanzig sind
   Zeilen. Genau das fehlt bis heute.
3. **Behauptet statt nachgemessen.** „Jetzt sind überall Bilder" — tatsächlich
   haben **31 von 193** Meldungen eins, und **18 der 31 sind zu klein und
   deshalb unscharf**. Beides hätte ein Blick auf die Zahlen gezeigt. Beide
   Messungen stehen unten; mach sie nach, bevor du etwas glaubst.

**Antonios Arbeitsweise, die du übernehmen solltest:** er schaut sich die
Seite an und benennt, was er sieht. Tu dasselbe, bevor du etwas änderst —
Screenshots gehen lokal (Abschnitt 6).

---

## 1. Das Ziel, konkret

„Wie das Wall Street Journal" heißt nicht Serifenschrift. Es heißt:

| Merkmal | heute | Ziel |
|---|---|---|
| **Gewichtung** | Aufmacher, dann drei gleich große Anreißer, dann eine flache Liste | mehrere Stufen: Aufmacher groß, 2–3 mittel, 4–6 klein, Rest als Zeile |
| **Raster** | eine Spalte + schmale Rail | echtes Mehrspaltenraster mit Trennlinien, Blöcke unterschiedlicher Breite |
| **Ressorts** | keine | Netz, Tarife, Satellit, Regulierung, Deutschland – mit Rubrikleiste, je Ressort ein eigener Block |
| **Bilder** | 31 von 193, oft 120×90 hochskaliert | mind. 120 von 193, nie hochskaliert |
| **Dichte** | viel Weißraum, wenig oberhalb der Falz | oberhalb der Falz gehören Aufmacher + 4–6 weitere Geschichten |
| **Meldungsseite** | 193 identische Zeilen untereinander | Ressort-Raster mit Karten unterschiedlicher Größe |

Wenn du unsicher bist, wie ein Element aussehen soll: die Referenz ist
wsj.com bzw. ft.com. Du darfst nicht dorthin navigieren, aber du weißt, wie
diese Seiten gebaut sind — Mehrspaltenraster, harte Trennlinien, Bild-Text-
Blöcke unterschiedlicher Gewichtung, Ressortleisten.

---

## 2. Befund mit Zahlen — nachgemessen am 06.08.2026

### 2.1 Bilder: der Deckel, nicht die Quellen

```
Meldungen der Ausgabe:              193
davon mit Bild:                      31   (16 %)
davon NIE auch nur versucht:        153   <-- der eigentliche Grund
```

`report/bilder.py` hat `max_bilder=40`. **153 Meldungen wurden nie
angefasst.** Antonios Beobachtung („ich drücke auf Sachen, wo Bilder sind,
aber bei uns ist nichts") ist damit exakt richtig.

Stichprobe von 25 der nie versuchten Meldungen:

```
og:image vorhanden   15   (60 %)
kein og:image         4   (16 %)
403 / 401             5   (20 %)
kein HTML             1   ( 4 %)
```

Hochgerechnet: **rund 91 weitere Meldungen hätten ein Bild.** Erreichbar sind
also grob **122 von 193** statt heute 31 — allein durch Anheben des Deckels.

### 2.2 Bilder: unscharf, weil Feed-Thumbnails bevorzugt werden

18 der 31 geladenen Bilder sind schmaler als 860 px und werden im Aufmacher
hochskaliert. Die schlimmsten Fälle:

```
 120x90    teltarif          <-- war der AUFMACHER der Ausgabe vom 6.8.
 220x138   Bitkom
 300x169   Mobile Time
 534x462   TELETIME
 649x365   Telecom Handel
```

Ursache: `hole_bilder()` nimmt **zuerst** `Item.image_url` aus dem Feed und
fragt `og:image` nur, wenn der Feed nichts liefert. Feeds tragen aber oft ein
`media:thumbnail` — also bewusst ein Vorschaubild. Das og:image derselben
Seite ist fast immer 1200×630.

**Die Reihenfolge ist falsch herum.** Richtig: beide Kandidaten holen, die
Maße prüfen (`Pillow` ist verfügbar), das größere nehmen, und alles unter
~800 px Breite für den Aufmacher ablehnen.

### 2.3 Meldungsseite: eine flache Liste

`site/meldungen.html` rendert 193 mal denselben Block: Bild links (210 px),
Überschrift, Beschreibung, Quelle. Keine Gruppierung, keine Gewichtung, keine
Ressorts. Antonio nennt das „extrem beschissenes Layout", und er hat recht —
das ist eine Datenbankausgabe, keine Zeitungsseite.

### 2.4 Was gut ist und bleiben soll

Nicht alles muss weg. Was funktioniert:

- **Die Schlagzeilen.** Der Analyst schreibt sie seit dem 6.8. selbst
  („o2 senkt Unlimited-Preis dauerhaft", „IHS-Aktionäre stimmen
  6,2-Milliarden-Dollar-Übernahme durch MTN zu"). 193 von 193 haben eine.
- **Die Typografie-Grundlage**: Source Serif 4 für Lesetext, Libre Franklin
  für Etiketten, Newsprint-Untergrund, Linien statt Kästen.
- **Der Zeitungskopf** mit Datumszeile und Rubrikleiste.
- **Die vier Seiten** (Diese Woche / Meldungen / Differenzierung / Quellen).
- **Die Wahrheitstests** (`tests/test_seiten_zahlen.py`). Sie haben in dieser
  Session dreimal echte Fehler gefangen. Nicht aufweichen.

---

## 3. Was zu bauen ist, in dieser Reihenfolge

### Schritt 1 — Bilder reparieren (Voraussetzung für alles andere)

Ohne Bilder wird kein Raster gut. Das ist der billigste große Hebel.

1. **Deckel weg.** `max_bilder` und `og_versuche` auf die volle Meldungszahl.
   Kosten: rund 190 HTTP-Abrufe je Lauf, nebenläufig ein bis zwei Minuten.
   Miss die Sammelphase vorher und nachher (`miss_sammelphase.py`).
2. **Größe entscheidet.** Feed-Bild UND og:image holen, mit `Pillow` messen,
   das größere behalten. Mindestbreite 800 px für den Aufmacher, 500 px für
   mittlere Blöcke, darunter nur noch als kleine Zeile oder gar nicht.
3. **Nebenläufig laden**, wie `collect_all()` es tut. 190 Abrufe seriell
   sprengen sonst die Laufzeit.
4. **`_MUELL`-Filter gegenprüfen.** Er wirft alles weg, dessen Pfad `logo`,
   `default-image` oder `share-image` enthält — bei manchen Systemen heißt so
   das echte Artikelbild. Miss, wie viele Kandidaten daran scheitern.
5. **Bei 403 aufgeben ist in Ordnung** (20 % der Fälle). Playwright wäre
   möglich, kostet aber Laufzeit — erst wenn 1–4 gemessen zu wenig bringen.

**Abnahme:** mindestens 110 von ~193 Meldungen mit Bild, **kein** Bild im
Aufmacher oder in der zweiten Reihe unter 800 px Breite. Beides mit einem
Skript belegen, nicht mit Augenschein.

### Schritt 2 — Titelseite als Raster mit Gewichtung

Heute: Aufmacher, drei gleich große Anreißer, dann der Fließtext. Das sind
zwei Gewichtsstufen. Eine Titelseite braucht vier:

```
┌──────────────────────────────┬───────────────┐
│ AUFMACHER                    │ WAS WICHTIG   │
│ Bild gross, Schlagzeile      │ IST           │
│ gross, Vorspann              │ 6-8 Zeilen,   │
├───────────────┬──────────────┤ nur Text,     │
│ ZWEITE        │ DRITTE       │ nummeriert    │
│ Bild mittel   │ Bild mittel  │               │
├───────────────┴──────────────┼───────────────┤
│ RESSORT: NETZ & TECHNIK      │ RESSORT:      │
│ 4 kleine Bloecke nebeneinand.│ REGULIERUNG   │
├──────────────────────────────┴───────────────┤
│ DER WOCHENBERICHT (Fliesstext, 2-spaltig)    │
└──────────────────────────────────────────────┘
```

Regeln:
- **Oberhalb der Falz mindestens 6 Geschichten.** Heute sind es vier.
- **Ressorts aus der vorhandenen `category`** der Meldungen
  (Produktlaunch, Tarif/Pricing, Netz/Technologie, Regulierung, M&A …) oder
  aus `region`. Beides liegt schon in jedem Highlight.
- **Der Wochenbericht rutscht nach unten.** Er ist das Herzstück
  (CLAUDE.md §8) und bleibt vollständig — aber eine Titelseite führt mit
  Nachrichten, nicht mit einem Essay.
- **Zweispaltiger Fließtext** für den Bericht auf breiten Schirmen
  (`columns: 2`), wie in jeder Zeitung.

### Schritt 3 — Meldungsseite als Ressortseite

Statt 193 identischer Zeilen:

- **Nach Ressort gruppiert**, jedes mit Rubrikleiste und Meldungszahl.
- **Innerhalb eines Ressorts gewichtet**: die erste Meldung groß mit Bild,
  die nächsten zwei mittel, der Rest als Zeile mit kleinem Bild.
- **Filterleiste bleibt** (funktioniert), aber sie filtert dann Ressorts.
- Dichte statt Luft: heute füllt eine Meldung ~150 px Höhe. Halbiere das für
  die kleinen.

### Schritt 4 — Dichte und Feinsatz

- Weißraum zwischen Rubriken, nicht zwischen Zeilen.
- Spaltenlinien (`border-right`) zwischen Blöcken statt Abstand.
- Zeilenhöhe im Fließtext auf ~1.5, Schriftgrad 17–18 px.
- Bildunterschriften klein, grotesk, direkt unter dem Bild.

---

## 4. Ausdrücklich nicht

- **Keinen Plan schreiben, der die Optik ausschließt.** Siehe Abschnitt 0.
- **Keine Platzhalterbilder, keine generierten Bilder, keine Symbolbilder.**
  Eine Meldung ohne Bild bleibt ohne Bild — der Satz muss das tragen.
- **Keine abgeschnittenen Überschriften.** `tests/test_seiten_zahlen.py`
  verbietet jede Überschrift, die auf „…" endet. Das war Antonios
  deutlichster Einzelvorwurf.
- **Keine neue Farbwelt.** Newsprint, Schwarz, Vodafone-Rot als Akzent. Rot
  ist keine Fläche.
- **Kein Dark-Mode.**
- **Die Promo Übersicht nicht anfassen** (eigener Anwendungsfall).
- **`data/state/` und `data/reports/` nicht aus lokalen Testläufen
  committen** — Ausnahme: Bilder unter `data/state/report_images/`, die
  gehören dazu.
- **Keine Zahl behaupten, die du nicht gemessen hast.** Genau daran ist diese
  Session gescheitert.

---

## 5. Abnahme

1. Screenshot der Titelseite in 1440 px Breite, und darauf sind **oberhalb
   der Falz mindestens sechs Geschichten** mit Schlagzeile erkennbar.
2. **≥ 110 von ~193 Meldungen** haben ein Bild, belegt mit einem Skript.
3. **Kein Bild** im Aufmacher oder in der zweiten Reihe ist schmaler als
   800 px, belegt mit einem Skript.
4. Die Meldungsseite ist nach Ressorts gruppiert und gewichtet; die erste
   Meldung ist ohne Scrollen sichtbar.
5. Keine Überschrift endet auf „…".
6. `PYTHONPATH=src pytest -q` grün.
7. Auf der Live-Site verifiziert (Abschnitt 6), nicht nur lokal.
8. Eine ehrliche Schlussliste in `outputs/`: was gebaut wurde, was gemessen
   wurde, was du nicht geschafft hast.

---

## 6. Wie du arbeitest

**Screenshots gehen lokal** — das ist der wichtigste Kniff dieser Session:

```bash
pip install -r requirements.txt --break-system-packages
export PYTHONPATH=src
python -m pytest -q

# Site aus den vorhandenen Daten rendern (kein Netz, kein LLM)
python -c "
from pathlib import Path
from telco_radar.config import load_config
from telco_radar.report.html import render_site
render_site(Path('/tmp/site'), Path('data/reports'), load_config(Path('.')))"

# Und ansehen: Chromium ist da, Playwright ist konfiguriert
python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page(viewport={"width":1440,"height":2400}, device_scale_factor=2)
    pg.goto("file:///tmp/site/index.html"); pg.wait_for_timeout(400)
    pg.screenshot(path="/tmp/titelseite.png"); b.close()
PY
```

Ohne Netz greifen die lokalen Rückfallschriften statt Source Serif 4 —
live sitzt der Satz enger. Nicht erschrecken.

**Live ausliefern:** Render publiziert von `main`. `deploy.yml` feuert bei
jedem Push auf `main`; die Seite steht 1–2 Minuten später. Ein Radar-Lauf
ist dafür **nicht** nötig — `site/` liegt fertig gerendert im Commit.

**Einen echten Lauf anstoßen** (GitHub Actions, `radar.yml`,
`workflow_dispatch`) nur, wenn du neue Daten brauchst. **Achtung:** der
Seen-Store hakt jede neue Meldung ab. Ein zweiter Lauf direkt danach findet
fast nichts und ersetzt eine gute Ausgabe durch eine dünne. Wenn du einen
laufenden Job wegen eines Fehlers abbrechen musst, tu das **vor** dem Ende —
gepusht wird erst zum Schluss, abgebrochen geht kein State verloren.

---

## 7. Fallstricke, die diese Session gekostet haben

- **Ein laufender Radar-Job rendert mit dem Code, der beim Start ausgecheckt
  wurde.** Läuft er nach einem Design-Push zu Ende, überschreibt er `site/`
  mit dem alten Design und dreht das Redesign live zurück. Vor einem Deploy
  prüfen, ob ein Job läuft.
- **Reasoning-Modelle: das Nachdenken zählt gegen `max_tokens`.** Reicht das
  Budget nur dafür, kommt eine leere oder mittendrin abgeschnittene Antwort —
  ohne Fehler des Anbieters. Editor: 32000, Wettbewerber: 12000. Wer eine
  neue LLM-Stufe baut, rechnet das ein.
- **Zwei von drei Wettbewerberprofilen sind im Lauf vom 6.8. daran
  gescheitert** und werden erst mit dem nächsten Lauf wieder da sein. Prüf
  das nach: `data/reports/*.json` → `competitors[].error`.
- **Ein Aufmacher, der aus einem kopierten Objekt stammt, lässt sich nicht
  über Objektidentität aus den Anreißern filtern.** Er stand dadurch zweimal
  auf der Titelseite. Über die URL ausschließen.
- **`_first_sentence` und ähnliche Kürzer erzeugen keine Überschriften.** Der
  Versuch, „SpaceX-Präsidentin Gwynne Shotwell sagt, Starlink Mobile werde
  direkt mit AT&T konkurrieren" an der ersten Kommagrenze zu kürzen, ergab
  „SpaceX-Präsidentin Gwynne Shotwell sagt". Überschriften schreibt der
  Analyst, sonst niemand.
- **Der Analyst lief lange auf dem billigen Modell** (`deepseek-v4-flash`),
  obwohl er Überschrift, Zusammenfassung und Einordnung **jeder** Meldung
  schreibt. Steht jetzt auf `deepseek-v4-pro`. Am Analysten wird nicht
  gespart — er bestimmt, was auf der Seite steht.

---

## 8. Der eine Satz, an dem du dich messen sollst

Antonio öffnet die Seite, sieht die obere Bildschirmhälfte und sagt
**nicht** „das erinnert nicht an ein Nachrichtenportal". Alles andere ist
Beiwerk.
