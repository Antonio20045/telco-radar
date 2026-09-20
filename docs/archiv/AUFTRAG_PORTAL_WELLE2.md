# Auftrag: Ruhe, roter Faden, und die Promo Übersicht neu

> Lies zuerst `CLAUDE.md` (Architektur, Zugänge, Fallstricke), dann diesen
> Text. **Dieser Text ist der Auftrag.** Er löst
> `AUFTRAG_NACHRICHTENPORTAL.md` ab, der abgearbeitet ist
> (`outputs/nachrichtenportal-2026-08-06.md`).
>
> Stand: 7. August 2026, gemessen an der Ausgabe vom 6.8. (205 Quellen,
> 193 Meldungen, 147 davon mit Bild) und am ausgelieferten `site/`.
> Live: https://telco-radar.onrender.com

---

## 0. Wo du anfängst

Die letzte Session hat aus der Seite ein Nachrichtenportal gemacht: vier
Gewichtsstufen, sieben Ressorts, 31 → 147 Bilder, oberhalb der Falz 10
Geschichten statt 4. **Antonio hat das ausdrücklich gelobt** — „gefällt mir
schon deutlich, deutlich besser", „mit den Bildern klappt es ziemlich gut,
die sehen ziemlich gut aus". Das ist die Grundlage. **Reiß sie nicht ein.**

Was er im selben Atemzug benannt hat, steht unten als fünf Punkte. Vier
davon sind klein und eindeutig. Der fünfte — die Promo Übersicht — ist der
eigentliche Brocken.

**Die Arbeitsweise, die funktioniert hat, und die du übernimmst:** erst
messen, dann ändern, dann wieder messen. Jede Zahl in diesem Text ist
nachgerechnet und du kannst sie nachrechnen. Behaupte keine.

---

## 1. Die Datumszeile fliegt raus

Unter dem Zeitungskopf steht auf **jeder** Seite:

```
AUSGABE VOM 6. AUGUST 2026 · WETTBEWERBSBEOBACHTUNG · VODAFONE INTERN · 205 QUELLEN BEOBACHTET
```

Antonio: *„Lösch diese Zeile, das ist unnötig."* Sie steht in
`base.html.j2` als `<div class="dateline">`.

- Vorlage: `src/telco_radar/report/templates/base.html.j2`, Zeile 44–51
- CSS: `.dateline` in `style.css` (Zeilen 57, 104, 126, 881)
- Die Globals `ausgabe_datum` und `ausgabe_quellen` in `html.py`
  (`render_site()`) werden damit **tot** — mit entfernen, nicht liegen
  lassen. Diese Codebasis hat schon einmal sechs berechnete Werte
  mitgeschleppt, die keine Vorlage benutzte.
- **Kein Test hängt daran** (nachgeprüft: `grep -rn "dateline\|ausgabe_datum"
  tests/` ist leer). Der Ausgabetag steht weiterhin auf der Meldungsseite als
  Kicker über „Alle Meldungen" — den hat Antonio nicht kritisiert, der bleibt.

---

## 2. Der Filter neben „Alle Meldungen" fliegt raus

Antonio: *„macht diesen Filter weg. Neben alle Meldungen dieser Filter, das
ist unnötig."*

Gemeint ist das Suchfeld rechts neben der Überschrift „Alle Meldungen"
(`#meldung-filter`, `.meldungen-suche` im Kopf von `meldungen.html.j2`).

Mit zu entfernen, sonst bleibt toter Code liegen:

- `meldungen.html.j2`: der `<div class="meldungen-suche">`-Block im Kopf
  (Zeile 40–44) und `<p id="meldung-leer">`
- `app.js`: der ganze Filter-Block (der zuletzt umgebaute IIFE, der über
  `.mressort` läuft und leere Ressorts ausblendet)
- `style.css`: `.meldungen-kopf` wird dadurch einspaltig
- die `data-such`-Attribute auf `.mz`, `.mzwei` und `.mlead` — sie
  existierten **nur** für diesen Filter

**Die Volltextsuche über alle Wochen unten auf der Seite bleibt** (`#suche-input`,
`search_index.json`). Die ist ein anderer Anwendungsfall („wo war nochmal die
Meldung von vor drei Wochen") und funktioniert. Ebenso die Topbar-Suche.

---

## 3. Die Meldungsseite: weniger scrollen, mehr entdecken

Antonio: *„überleg dir mal, wie du noch alle Meldungen ein bisschen besser
das Layout machen kannst. Zum Beispiel, dass man die Kategorien sieht, dann
die wichtigsten Meldungen der Kategorie und wenn eins interessiert, kann man
draufdrücken und sieht dann alle Meldungen. Oder irgendwie so ähnlich. Weil
so muss man auch viel runterscrollen und viel entdecken bei den einzelnen
Kategorien."*

### Der Befund, gemessen

`site/meldungen.html` ist **12 249 px hoch**. Wo die Ressorts anfangen:

```
Netz & Technik                 339 px
Tarife & Angebote            2 686 px
Satellit & Direct-to-Cell    4 172 px
Regulierung & Politik        5 745 px
Geld & Übernahmen            7 231 px
Partnerschaften              8 609 px
Vermischtes                  9 580 px
```

Wer wissen will, was unter „Geld & Übernahmen" steht, scrollt **acht
Bildschirmhöhen**. Die Sprungleiste oben hilft, aber sie ist eine Krücke:
sie beweist, dass die Seite zu lang ist, statt sie kürzer zu machen.

### Was zu bauen ist

Antonios Vorschlag ist richtig: **erst die Ressorts als Übersicht, dann auf
Klick die Tiefe.** Konkret heißt das eine Seite, auf der man ohne Scrollen
alle sieben Ressorts sieht, jedes mit seinen zwei bis drei wichtigsten
Meldungen, und je Ressort einen Weg zu allen.

Zwei Bauarten sind vertretbar — **entscheide selbst, begründe es in der
Schlussliste**:

| | Vorteil | Preis |
|---|---|---|
| **Aufklappen** (`<details>` je Ressort, alles im HTML, per JS aufgedeckt) | eine Datei, Suche findet weiterhin alles, kein zweiter Ladevorgang | die Seite bleibt gross im Quelltext (~170 KB heute) |
| **Ressortseiten** (`ressort/netz.html` usw.) | jede Seite kurz, echte Adressen zum Teilen | 7 Dateien mehr, `render_site()` und der Suchindex müssen sie kennen |

**Was in beiden Fällen gelten muss:**

- Alle sieben Ressorts sind **ohne Scrollen** sichtbar (Messwert: die
  Oberkante des letzten Ressortblocks liegt bei 1440 × 900 unter 900 px).
- Je Ressort **2–3 Meldungen mit Bild und Schlagzeile**, nicht nur ein
  Etikett — sonst ist es ein Inhaltsverzeichnis, keine Übersicht.
- Der Weg zu „alle 46" ist **eine** Geste, nicht drei.
- Die Zahl neben dem Ressort stimmt mit der Datenlage überein
  (`test_ressortleiste_verspricht_nicht_mehr_als_es_gibt` hält das schon
  fest — **anpassen, nicht löschen**).
- **Keine Meldung verschwindet.** Heute stehen alle 193 auf der Seite; das
  ist die Belegebene, und Nachprüfbarkeit war Antonios ausdrückliche
  Anforderung (CLAUDE.md §8). `test_meldungsseite_zeigt_wirklich_alle_meldungen`
  zählt sie.

---

## 4. „Diese Woche": ruhiger, und ein roter Faden

Antonio: *„Was mir bei diese Woche gefällt, finde ich gut, dass du dann so
einen Überblick über alles machst. Aber da vielleicht auch so ein bisschen
ordentlicher das Layout und der Bericht auch so ein bisschen besser
geordnet. Das ist alles so ein bisschen unruhig und der rote Faden fehlt mir
noch überall."*

**Das ist der vageste Punkt des Auftrags und der, an dem du am ehesten
scheiterst, wenn du sofort loslegst. Miss zuerst, was „unruhig" konkret
ist.** Die Titelseite ist 12 690 px hoch, der Wochenbericht beginnt bei
2 777 px. Anhaltspunkte, die du prüfen (nicht ungeprüft umsetzen) solltest:

1. **Wie viele verschiedene Blocktypen stehen untereinander?** Aufmacher,
   zweite Reihe, dritte Reihe, „Was wichtig ist", Themenradar, sechs
   Ressortblöcke, Wochenbericht, Zahlen der Woche, Deutschland-Fokus,
   Auswertung je Bereich. Das sind zehn Formen auf einer Seite. Eine Zeitung
   hat drei bis vier. **Wo dieselbe Information zweimal in zwei Formen
   steht, fällt eine weg.**
2. **Der rote Faden fehlt buchstäblich:** die Titelseite führt mit Starlink,
   die Ressorts führen mit etwas anderem, der Wochenbericht führt mit einem
   dritten Thema. Der Editor schreibt bereits einen Abschnitt „Das
   Wichtigste" — **die Titelseite müsste ihm folgen, statt parallel zu ihm zu
   sortieren.** Sieh dir an, ob der Aufmacher aus dem gewählt werden kann,
   worüber der Bericht führt (`briefing_md`, erster Abschnitt nach „Auf einen
   Blick"). Das wäre der Faden.
3. **Der Bericht selbst ist nach Regionen gegliedert** (Global, Europa,
   Asien, …) — die Seite aber nach Ressorts. Zwei Ordnungen für dieselbe
   Woche. Prüfe, ob der Editor nach Ressorts schreiben kann; das ist eine
   Prompt-Änderung in `analyze/editor.py`, und **Prompt und
   `validate_editorial_briefing` hängen am selben Schalter** (CLAUDE.md §6).
4. **Was Antonio NICHT kritisiert hat und was bleibt:** die Bilder, die
   Gewichtung, die Typografie, dass es einen Überblick über alles gibt.

---

## 5. Die Promo Übersicht: komplett neu

Antonio: *„Promo-Übersicht ist richtig beschissen. Ganz neues Layout, hier
sind auch nirgendwo Bilder. Es ist beschissenes Layout, viel unnötiger Text."*

Diese Seite ist beim Nachrichtenportal-Umbau **absichtlich nicht angefasst**
worden (der Auftrag verbot es). Sie trägt deshalb noch die Struktur von vor
dem Redesign. Der Befund, gemessen am 07.08.2026:

```
Seitenhöhe                        5 794 px
sichtbarer Text                   3 184 Wörter
<img>-Elemente auf der Seite              2   (eins davon ist das Logo)
Promo-Screenshots auf der Platte         15   (alle 1280x720)
davon gerendert                           1
```

**Der schärfste Einzelbefund:** 15 Screenshots liegen unter
`data/state/promo_images/`, jeder 1280 × 720. Verwendet wird **genau einer**
(`telekom-deutschland.jpg`) — und ausgerechnet der ist mit **6 KB** ein
leerer Fehlschuss, während die anderen 14 zwischen 58 und 114 KB echten
Inhalt haben. Antonios „hier sind auch nirgendwo Bilder" ist damit exakt
richtig, und die Ursache ist nicht fehlendes Material, sondern die Vorlage:
`promo_index.html.j2` bindet ein Bild nur im Hero ein.

Die Kästen, aus denen die Seite besteht:

```
.promo-hero-card    769 x 722 px    1 Bild (das leere)
.promo-stat-card    385 x 722 px    0 Bilder  <- reiner Text, 722 px hoch
.promo-top-card     373 x 234 px    0 Bilder  (3 Stück)
.promo-card         373 x 1058 px   0 Bilder  (9 Stück, je eine Marke)
.promo-offer                                  (54 Stück)
```

Neun Textsäulen zu je 1058 px nebeneinander, ohne ein einziges Bild. Das ist
dieselbe Diagnose wie bei der alten Meldungsseite: eine Datenbankausgabe.

**Dazu ein echter Textfehler**, den du gleich mit erledigst: die Karte „Was
diese Woche auffällt" zeigt

> „ALDI TALK imoo Kinder-Smartwatch kaufen + 2 MovieChoice-Kinogutscheine
> **ALDI TALK – imoo Kinder-Smartwatch kaufen + 2 MovieChoice-Kinogutscheine .**"

— derselbe Angebotstitel zweimal hintereinander, mit einem freistehenden
Punkt am Ende. `_promo_lead()` in `html.py` schneidet den ersten Satz aus
einem Wochentext, der gar keine Sätze hat, sondern aneinandergereihte
Angebotstitel. Entweder der Promo-Editor schreibt Prosa, oder diese Karte
zeigt etwas anderes. **Nicht den Schnitt reparieren — die Quelle.**

### Was zu bauen ist

Dieselbe Designsprache wie die Marktrecherche (Newsprint, Serife, Linien
statt Kästen, Rot als Akzent) — sie ist gelobt worden und gilt für beide
Anwendungsfälle. Aber die **Frage** der Seite ist eine andere: nicht „was ist
passiert", sondern „wer wirbt gerade womit".

Anhaltspunkte:

- **Die 14 vorhandenen Screenshots benutzen.** Eine Aktion ohne Bild ist
  eine Zeile, eine mit Bild ist eine Kachel — dieselbe Gewichtungslogik wie
  auf der Titelseite, sie steht schon in `report/html.py` (`_titelseite`).
- **Der leere 6-KB-Screenshot darf nicht ausgeliefert werden.** Der
  Bild-Check aus `report/bilder.py` (`masse()`, `_MIND_BREITE`) kann das
  messen; ein Screenshot unter ~10 KB bei 1280 × 720 ist eine weiße Seite.
- **3 184 Wörter sind zu viel für eine Übersicht.** Was auf einen Blick
  beantwortet werden muss: welche Marke, welches Angebot, wie wichtig, bis
  wann, Link. Alles andere ist Tiefe und gehört hinter einen Klick.
- **Die Promo-Quellenseite (`promo/quellen.html`) bleibt** — sie ist die
  Belegebene und funktioniert.

Relevante Dateien: `report/templates/promo_index.html.j2` (185 Zeilen),
`report/promo.py` (235 Zeilen, `prepare_promo_view()`),
`promo_pipeline.py` (217 Zeilen), `config/promo_sources.yaml`,
`data/state/promo_db.json`, `data/state/promo_images/`.

**Wichtig:** die Promo Übersicht hat **keinen einzigen Wahrheitstest**. Die
Marktrecherche hat 458. Wenn du diese Seite neu baust, baust du auch ihre
Tests — jede Zahl, die dort steht (28 aktive Aktionen, 14 beobachtete
Wettbewerber, 3 über der Schwelle), gehört gegen die Daten geprüft, wie in
`tests/test_seiten_zahlen.py`.

---

## 6. Ausdrücklich nicht

- **Die Gewichtung, die Bilder und die Typografie der Marktrecherche nicht
  einreißen.** Sie sind gelobt worden. Was du dort anfasst, fasst du an,
  weil Punkt 3 oder 4 es verlangt — nicht, weil du es schöner findest.
- **Keine Platzhalterbilder, keine generierten Bilder, keine Symbolbilder.**
  Gilt unverändert. Ohne Bild bleibt ohne Bild.
- **Keine abgeschnittenen Überschriften.** `tests/test_seiten_zahlen.py`
  verbietet jede, die auf „…" endet, über die Klasse `szl`. **Jede neue
  Schlagzeile in jeder neuen Vorlage bekommt `szl`** — sonst fällt sie still
  aus drei Prüfungen heraus.
- **Keine neue Farbwelt, kein Dark-Mode.**
- **`data/state/seen.jsonl` nicht committen.** Bilder unter
  `data/state/report_images/` und `promo_images/` gehören dazu.
- **Keine Zahl behaupten, die du nicht gemessen hast.**

---

## 7. Abnahme

1. Die Datumszeile ist auf **keiner** Seite mehr da, und keine tote Variable
   ist zurückgeblieben.
2. Der Filter neben „Alle Meldungen" ist weg, samt `data-such`, `app.js`-Block
   und den CSS-Regeln, die nur ihm dienten.
3. Alle sieben Ressorts sind auf der Meldungsseite **ohne Scrollen** sichtbar
   (Messung bei 1440 × 900, mit einem Skript belegt), und alle 193 Meldungen
   sind weiterhin erreichbar.
4. Die Promo Übersicht zeigt **mindestens 10 der 15 vorhandenen Bilder**, der
   leere 6-KB-Screenshot ist nicht darunter, und die Karte „Was diese Woche
   auffällt" enthält keinen doppelten Titel mehr.
5. Die Promo Übersicht hat Wahrheitstests für jede Zahl, die sie zeigt.
6. `python scripts/pruefe_portal.py` bleibt grün (acht Prüfungen) — **erweitere
   es** um die neuen Kriterien 3 und 4, statt ein zweites Skript zu schreiben.
7. `PYTHONPATH=src pytest -q` grün.
8. Auf der Live-Site verifiziert (§8), nicht nur lokal.
9. Eine ehrliche Schlussliste in `outputs/`: was gebaut, was gemessen, was
   nicht geschafft.

---

## 8. Wie du arbeitest

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

# Ansehen: Chromium ist da, Playwright ist konfiguriert
python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page(viewport={"width":1440,"height":900})
    pg.goto("file:///tmp/site/index.html"); pg.wait_for_timeout(400)
    pg.screenshot(path="/tmp/titelseite.png"); b.close()
PY
```

Ohne Netz greifen die lokalen Rückfallschriften statt Source Serif 4 — live
sitzt der Satz enger. Nicht erschrecken.

**Live ausliefern — und hier der Fallstrick, der diese Session Zeit gekostet
hat:** Render publiziert von `main`, ausgelöst durch `deploy.yml`. Der
Workflow lief am 06.08. in die GitHub-Actions-Warteschlange, bekam **nie
einen Runner** (`runner_id: 0`, `started_at == created_at`) und wurde nach 15
Minuten abgebrochen. Der Code lag korrekt auf `main`, aber Render erfuhr nie
davon und lieferte tagelang die alte Fassung aus. Es fiel erst auf, weil
Antonio auf die Seite sah.

> **Nach jedem Push auf `main`: den Ausgang von `deploy.yml` prüfen, nicht
> nur die Live-Seite pollen.** Ein hängender Deploy und eine noch nicht
> fertige Auslieferung sehen von aussen gleich aus. Wenn er hängt: Actions →
> „Deploy Site" → „Run workflow" (`workflow_dispatch` auf `main`). Ein
> Radar-Lauf ist dafür nicht nötig, `site/` liegt fertig gerendert im Commit.

Zur Kontrolle, ob live wirklich ankam, was du geprüft hast:

```bash
curl -sS -o /tmp/live.html https://telco-radar.onrender.com/index.html
diff <(md5sum < site/index.html) <(md5sum < /tmp/live.html) && echo IDENTISCH
```

**Einen echten Radar-Lauf** (Actions, `radar.yml`, `workflow_dispatch`) nur
anstossen, wenn du neue Daten brauchst. Der Seen-Store hakt jede Meldung ab;
ein zweiter Lauf direkt danach findet fast nichts und ersetzt eine gute
Ausgabe durch eine dünne. **Und: ein laufender Radar-Job rendert mit dem
Code, der beim Start ausgecheckt wurde** — läuft er nach einem Design-Push zu
Ende, überschreibt er `site/` mit dem alten Design.

---

## 9. Der eine Satz, an dem du dich messen sollst

Antonio öffnet die Promo Übersicht und sagt **nicht** „das ist richtig
beschissen". Und auf „Diese Woche" findet er den roten Faden, ohne danach zu
suchen.
