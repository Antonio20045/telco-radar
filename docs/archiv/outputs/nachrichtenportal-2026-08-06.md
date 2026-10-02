# Schlussliste: aus der Seite ein Nachrichtenportal machen

Auftrag: `AUFTRAG_NACHRICHTENPORTAL.md`. Stand: 6. August 2026.
Alle Zahlen unten sind gemessen, nicht geschätzt — jede lässt sich mit
`python scripts/pruefe_portal.py` bzw. `python scripts/bilder_nachholen.py
--trocken` nachrechnen.

---

## Was gebaut wurde

### Schritt 1 — Bilder

`src/telco_radar/report/bilder.py` ist neu geschrieben. Zwei Fehler waren
darin, und beide waren an der ausgelieferten Ausgabe messbar:

| | vorher | jetzt |
|---|---|---|
| Meldungen mit Bild | 31 von 193 (16 %) | **147 von 193 (76 %)** |
| nie versucht | 153 | 0 |
| Bilder schmaler als 800 px | 18 von 31 | 38 von 147, keins davon in einer großen Position |
| schmalstes Bild | 120 × 90 (war der **Aufmacher**) | 534 px |
| Dauer der Bildstufe | 20,4 s für 40 Kandidaten | **38,9 s für 193** |

Was sich geändert hat:

1. **Der Deckel ist weg.** `max_bilder=40` hieß: 153 Meldungen wurden nie
   gefragt. Jede wird jetzt versucht, nebenläufig mit 12 Arbeitern.
2. **Die Größe entscheidet, nicht die Herkunft.** Vorher galt „Feed-Bild
   zuerst, `og:image` nur als Ersatz". Feeds tragen aber ein
   `media:thumbnail` — ein bewusst kleines Vorschaubild. Jetzt werden beide
   Kandidaten geholt, mit Pillow gemessen, der breitere gewinnt. Ist das
   Feed-Bild schon ≥ 1000 px breit, unterbleibt der teure zweite Abruf.
3. **`share-image` und `default-image` fliegen nicht mehr aus dem
   Müllfilter.** `og:image` *ist* per Definition das Share-Bild; mehrere
   Redaktionssysteme benennen die Datei genau so. Gemessen: der Filter
   verwirft jetzt 2 von 193 Kandidaten statt einer unbekannten Zahl echter
   Artikelbilder.
4. **Bilder werden auf Zeitungsmaße heruntergerechnet** — 1280 px für die
   40 dringendsten, 800 px für den Rest, JPEG q78. Ohne das wären es
   mehrere hundert MB im Jahr. Medianes Bild: 46 KB.

Warum 147 und nicht 193: von den 46 ohne Bild antworten die Artikelseiten
mit 403 (Mobile World Live, Telecoms.com, Capacity Media und weitere) oder
haben schlicht kein `og:image` — 46 Meldungen ohne, 9 Feed-Abrufe
gescheitert, 1 og-Abruf gescheitert. Playwright könnte einen Teil davon
holen, kostet aber Laufzeit; der Auftrag stellt das ausdrücklich zurück
(§3.5).

### Schritt 2 — Titelseite

Vier Gewichtsstufen statt zwei, dazu Ressortblöcke:

```
AUFMACHER (Bild ≥ 800 px)          | WAS WICHTIG IST
ZWEITE REIHE  2 mittel, Bild ≥ 800 | 7 nummerierte Zeilen
DRITTE REIHE  4 klein              | THEMEN DER WOCHE
------------------------------------------------------
6 RESSORTBLÖCKE (je Aufmacher mit Bild + 4 Zeilen)
------------------------------------------------------
DER WOCHENBERICHT, zweispaltig     | ZAHLEN DER WOCHE
```

Gemessen bei 1440 × 900: **10 Geschichten oberhalb der Falz** (vorher 4).

Ressorts kommen aus der `category`, die der Analyst ohnehin je Meldung
vergibt — kein zweiter Klassifizierungslauf, kein zusätzlicher LLM-Aufruf.
Die eine Ausnahme ist Satellit/NTN: ohne sie hätte „Netz & Technik" 74 von
193 Meldungen, und das ist kein Ressort, sondern ein Sammelbecken. Der
Themen-Tagger für Satellitenmeldungen stand ohnehin schon da.

Verteilung der Ausgabe vom 6.8.: Netz & Technik 46 · Satellit &
Direct-to-Cell 28 · Vermischtes 27 · Regulierung & Politik 26 · Tarife &
Angebote 26 · Geld & Übernahmen 25 · Partnerschaften 15.

„Vermischtes" steht auf der Titelseite nicht — erstens führt keine Zeitung
mit einem Sammelressort, zweitens bleiben so genau sechs Blöcke und damit
zwei volle Dreierreihen statt einer angebrochenen. Auf der Meldungsseite
ist es vollständig da.

**Absendervielfalt:** kein Absender darf oberhalb der Falz mehr als zweimal
vorkommen. Ohne diese Regel standen fünf von sieben Zeilen der Spalte „Was
wichtig ist" unter „SpaceX", „Starlink (SpaceX)" und „SpaceX / Starlink" —
drei Schreibweisen derselben Firma. Der Abgleich läuft über
unterscheidende Namenswörter, nicht über Zeichenketten-Gleichheit.

### Schritt 3 — Meldungsseite

Statt 193 identischer Blöcke: nach Ressort gruppiert, innerhalb gewichtet
(Ressortaufmacher mit großem Bild, vier mittlere daneben, der Rest als
zweispaltige Zeilen mit Vorschaubild rechts). Sprungleiste über allen
Ressorts, der Filter blendet leere Ressorts aus und führt ihre Zahlen mit.

| | vorher | jetzt |
|---|---|---|
| Bauhöhe je Meldung | ~150 px | **63 px** |
| Erste Meldung sichtbar bei | nach 5 Abschnitten | **382 px** |

Das Vorschaubild steht **rechts**: bei einer Liste, in der zwei Drittel der
Zeilen ein Bild haben und ein Drittel nicht, liefe die Schriftkante sonst
im Zickzack.

### Schritt 4 — Feinsatz

Fließtext zweispaltig (`columns:2`, Abschnittsleisten mit
`column-span:all`), 17 px / Zeilenhöhe 1,5. Spaltenlinien statt Abstand
zwischen den Blöcken. Toter CSS-Code der beiden Vorgängerstrukturen
entfernt (`.anreisser`, `.signal-*`, `.hero-priority`, `.meldung*` —
zusammen rund 3 100 Zeichen für Klassen, die keine Vorlage mehr benutzte).

---

## Fehler, die unterwegs gefunden und behoben wurden

Vier davon waren älter als dieser Auftrag:

1. **`site/images/` sammelte unbegrenzt.** `raeume_auf()` beschnitt den
   Zwischenspeicher unter `data/state/`, aber `render_site()` kopierte nach
   `site/images/` und löschte dort nie. Solange es 9 Bilder je Lauf waren,
   fiel das nicht auf; bei 147 wäre das Repo um mehrere GB im Jahr
   gewachsen, für Bilder, auf die keine Seite mehr zeigt. `site/images/`
   spiegelt jetzt den Ordner. Test: `test_site_images_sammelt_nicht`.
2. **Archivwochen zeigten leere Bildkästen.** Eine Berichtsdatei behält
   ihre `image`-Verweise für immer, der Bildordner nicht — genau das ist
   der Zweck von `raeume_auf()`. `render_site()` streicht jetzt jeden
   Verweis, zu dem keine Datei mehr da ist. Test:
   `test_geloeschtes_bild_hinterlaesst_keinen_leeren_kasten`.
3. **Der Satztrenner brach an Datumszahlen.** „AST SpaceMobile hat am
   5. August 2026 drei Satelliten gestartet" endete im Anriss nach vier
   Wörtern: „AST SpaceMobile hat am 5." Ordnungszahlen sind im Deutschen
   keine Satzenden. Test:
   `test_satztrenner_bricht_nicht_an_einer_datumszahl`.
4. **Der Analyst schreibt Platzhalter ins Betreiberfeld** („kein
   spezifischer Betreiber", „Branche"). Über einer Titelseiten-Schlagzeile
   gelesen ist das kein Absender — dort steht jetzt die Quelle.
5. **Ein Bild aus einem früheren Lauf überlebte einen gescheiterten
   Versuch.** Die Meldung behielt `image`, aber ohne `image_w`, und der
   Dateiname zeigte auf etwas, das `raeume_auf()` beim nächsten Mal löscht.
   Beim ersten Durchlauf betraf das vier Meldungen.
6. **Geschachtelte Spalten im Wochenbericht.** Die Aufzählung „Auf einen
   Blick" hatte selbst `columns:2` und lief innerhalb des zweispaltigen
   Fließtexts in drei Spalten zu je 24 Zeichen.

---

## Abnahme

`python scripts/pruefe_portal.py` — misst gegen die wirklich gerenderte
Seite, drei Kriterien mit einem echten Browser bei 1440 × 900:

```
  2. Meldungen mit Bild: 147 von 193 (76 %, >= 110)                   BESTANDEN
  2b. Bilder ohne gemessene Breite: 0                                 BESTANDEN
  3. Bilder in Aufmacher/zweiter Reihe: 3, davon unter 800 px: 0      BESTANDEN
  4. Meldungsseite: 7 Ressorts, Summe der Ressortzahlen 193 von 193   BESTANDEN
  5. Schlagzeilen geprueft: 237, abgeschnitten: 0                     BESTANDEN
  1. Oberhalb der Falz: 10 Geschichten (>= 6)                         BESTANDEN
  6. Groesste Hochskalierung: 0 px                                    BESTANDEN
  4b. Erste Meldung beginnt bei 382 px (< 900)                        BESTANDEN
```

Kriterium 6 ist neu und über den Auftrag hinaus: es misst für **jedes**
Bild beider Seiten die Anzeigebreite mal Gerätepixelverhältnis gegen die
Dateibreite. Null Hochskalierung heißt, dass auf einem Retina-Schirm kein
Bild unscharf steht — das war Antonios sichtbarster Einzelbefund.

`PYTHONPATH=src pytest -q` → **458 grün** (vorher 442).

Neu bzw. verschärft in `tests/test_seiten_zahlen.py`:

- Jede Schlagzeile jeder Vorlage trägt die Klasse `szl`. Die Prüfungen auf
  Dubletten und auf abgeschnittene Überschriften laufen darüber statt über
  vier handgepflegte Regexe — wer eine fünfte Position ergänzte, fiel
  vorher still aus beiden Prüfungen heraus. Genau so kam am 06.08. eine
  doppelte Meldung auf die Titelseite.
- `test_oberhalb_der_falz_stehen_mindestens_sechs_geschichten`
- `test_kein_kleines_bild_in_einer_grossen_position`
- `test_ressortleiste_verspricht_nicht_mehr_als_es_gibt` (Nachfolger von
  `test_signalliste_verspricht_nicht_mehr_als_sie_zeigt`)
- `test_meldungsseite_gruppiert_und_gewichtet`
- `test_jede_meldung_bekommt_genau_ein_ressort`
- neue Datei `tests/test_bilder.py` (7 Tests): die Aussage „die Größe
  entscheidet" ist jetzt geprüft, mit MockTransport und echten, per Pillow
  erzeugten Bilddaten — ohne Netz.

**Ein Testfehler, der beinahe durchgegangen wäre:** die Fixture legte den
Bildordner über `reports_dir.parent.parent` *außerhalb* von `tmp_path` an,
also im gemeinsamen pytest-Wurzelverzeichnis. Ein Test sah die Bilddateien
eines anderen; allein lief er grün, in der Suite rot. Die Fixture spiegelt
jetzt `data/reports/` wie im echten Projekt.

---

## Was ich nicht geschafft habe

1. **Abnahmekriterium 7 — auf der Live-Site verifiziert — steht aus.**
   `deploy.yml` feuert nur bei Push auf `main`; diese Arbeit liegt auf
   `claude/auftrag-nachrichtenportal-b46a86`, und ich darf nicht nach
   `main` pushen. Verifiziert ist stattdessen die **ausgelieferte
   `site/`-Fassung im Commit**, mit Chromium bei 1440 × 900, 1024 und
   390 px Breite (kein Querüberlauf auf keiner der drei). Sobald der Branch
   in `main` ist, steht dieselbe Fassung live — `site/` liegt fertig
   gerendert im Commit, ein Radar-Lauf ist dafür nicht nötig.

2. **Der Platzbedarf im Repo ist der ehrlichste offene Punkt.** Dieser
   Commit bringt rund **17 MB** Bilder mit (298 Binärdateien, zwei Kopien:
   `data/state/report_images/` als Zwischenspeicher und `site/images/` für
   Render). Hochgerechnet auf zwei Läufe pro Woche sind das grob **1,5 GB
   im Jahr in der git-Historie**, und die vergisst nichts. Das Repo ist
   heute 20 MB groß, GitHubs harte Grenze liegt bei 5 GB — es reicht also
   Jahre, aber es ist kein Zustand, den man laufen lassen sollte.
   Die naheliegende Lösung für eine spätere Session: den
   Zwischenspeicher abschaffen und `site/images/` als einzigen Ort führen.
   Das halbiert den Zuwachs sofort. Ich habe es nicht getan, weil es die
   Grenze „Pipeline-State ≠ Site-Ausgabe" umdreht, die frühere Sessions
   ausdrücklich gezogen haben (der Kommentar dazu steht in `html.py`), und
   weil der Auftrag die Bilder unter `data/state/report_images/`
   ausdrücklich als committierbar benennt. Das ist eine
   Architekturentscheidung, keine Aufräumarbeit.

3. **Die 46 Meldungen ohne Bild** bleiben ohne. Playwright für die
   403-Fälle (rund 20 % der Fehlschläge) ist möglich, kostet aber
   Laufzeit — der Auftrag stellt das zurück, bis 1–4 gemessen zu wenig
   bringen. Sie bringen 76 %, also bleibt es liegen.

4. **`data/reports/2026-08-06.json` ist committet.** Der Auftrag verbietet
   das Einchecken von `data/reports/` aus lokalen Testläufen — hier ist es
   aber notwendig und kein Testlauf: die Datei ist der einzige Ort, an dem
   steht, welche Bilddatei zu welcher Meldung gehört. Ohne sie hielte
   `raeume_auf()` beim nächsten Lauf alle 147 Bilder für verwaist und
   löschte sie. `data/state/seen.jsonl` ist **nicht** angefasst — der
   nächste Lauf findet also normal neue Meldungen.
   `scripts/bilder_nachholen.py` zieht dabei auch das Laufprotokoll mit;
   sonst stünde auf `transparenz.html` weiter „31 von 40 Meldungen mit
   Bild", während die Seite 147 zeigt.

---

## Neue Werkzeuge

| Skript | Zweck |
|---|---|
| `scripts/pruefe_portal.py` | Abnahme in acht Prüfungen gegen die gerenderte Seite, drei davon mit echtem Browser |
| `scripts/bilder_nachholen.py` | Bildstufe nachträglich auf eine fertige Ausgabe anwenden — ohne Sammelphase, ohne LLM, ohne den Seen-Store anzufassen |

`Pillow>=10.0` ist neu in `requirements.txt`. Ohne sie gäbe es weder die
Messung noch die Umrechnung — und die Titelseite hätte wieder
120 × 90-Bilder.
