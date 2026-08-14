# Volltext-Übersetzung fremdsprachiger Artikel — Schlussliste

Stand: 13. August 2026 · Phase 0 bis 3 umgesetzt
Branch: `claude/volltext-uebersetzung-artikel-4yz65m`

**1716 Tests** (vorher 1657) · `pruefe_portal.py` **16 bestanden, 0
durchgefallen** · Phase-0-Befundbericht:
`outputs/volltext-uebersetzung-phase0-2026-08-13.md`

---

## 1. Was Phase 0 am Zuschnitt geändert hat

Das Konzept plante den Artikelabruf als „Rückfallweg für die Minderheit"
und die Aufhebung der 600-Zeichen-Kappung als den eigentlichen Hebel.
**Beides war umgekehrt.** Gemessen über 1329 Feed-Einträge aus 140 wirklich
abgerufenen RSS-Quellen:

| Weg | Deckung | Kosten |
|---|---:|---|
| Kappung `[:600]` aufheben | 14,1 % | keine |
| `content:encoded` lesen (nie gelesenes Feld) | 33,2 % | keine |
| **beide Feed-Wege zusammen** | **40,6 %** | keine |
| **Artikelseite abrufen** | **59,4 %** | 1 HTTP-Abruf je Meldung |

Bei den fremdsprachigen Einträgen tragen nur 43 % ihren Volltext im Feed.
**Der teure Weg ist der Hauptweg** — deshalb hat er die meisten Sicherungen
bekommen und nicht die wenigsten.

Zweiter Befund mit Folgen: **auf der Überschrift gemessen ist jede
Spracherkennung Ausschuss.** Über 810 archivierte Meldungen ergab die
Titelmessung 23,2 % fremdsprachig, darunter „AT&T, Ericsson demonstrate
drone-sensing 5G capabilities" als Französisch. Auf Titel plus echtem
Teaser: 15,2 %, und über zwölf per Artikelabruf geprüfte Fälle stimmte die
Teasersprache in **allen zwölf** mit der des Volltexts überein.

---

## 2. Was gebaut wurde

| Baustein | Datei | Die eine Regel |
|---|---|---|
| Feld am Datenmodell | `models.py` | `volltext` + `sprache` **neben** `summary`, nicht statt |
| Feed-Volltext | `collect/rss.py` | `content:encoded` ungekappt; `summary` bleibt bei 600 |
| Spracherkennung | `uebersetzung/sprache.py` | nie auf dem Titel, ab 200 Zeichen, Grenzfall = verwerfen |
| Volltext holen | `uebersetzung/volltext.py` | Mindestlänge in **Zeichen**, über `collect/http.py` |
| Übersetzen | `uebersetzung/uebersetzer.py` | vollständig, absatzweise gebündelt, ≥ 55 % Originallänge |
| Speicher | `uebersetzung/store.py` | `Item.id` + Texthash, **nichts wird gelöscht** |
| Pipeline-Stufe | `uebersetzung/stufe.py` | Budget gegen die **Restzeit des Jobs** |
| Seite + Zuordnung | `report/uebersetzung_view.py` | die ID kommt aus `Item`, nicht aus einer zweiten Rechnung |
| Vorlagen | `uebersetzung.html.j2`, `_uebersetzung.html.j2` | Originallink bleibt, Link außerhalb des `<a>` |
| Stil | `style.css` | `var(--red)` — kein zweites Rot |
| Schalter | `config/settings.yaml` | vier Stellschrauben, Hauptschalter `uebersetzung_enabled` |

**Der Link erscheint** an allen drei Gewichtungen von `meldungen.html`, am
Aufmacher der Wochenseite und im Explorer der Archivwochen (dort über
`app.js`, weil die Seite ihre Meldungen im Browser baut). Im ersten Anlauf
hing er nur an der Zeilen-Gewichtung — dann wäre er je nach Dringlichkeit
der Woche erschienen oder verschwunden.

---

## 3. Die Premortem-Punkte, einzeln abgearbeitet

| # | Gefahr | Gegenmittel im Code |
|---|---|---|
| 1 | Übersetzung kürzer als der Teaser | `MINDESTLAENGE = 1200` **absolut** plus Faktor 1,5. Der echte Fall digi.no (141 Zeichen = „3,1× länger") steht als Test |
| 2 | Navigation und Cookie-Banner mitübersetzt | `trafilatura` mit `favor_precision=True`; über fünf Sprachen gemessen, Textproben im Phase-0-Bericht |
| 3 | Lauf wird langsamer und kippt | Budget gegen die Restzeit des Jobs, Deckel je Lauf, Fristprüfung vor **jedem** Artikel, alles failsafe |
| 4 | Spracherkennung liegt daneben | Erkennung auf dem Fließtext, `norm_probs=True`, Enthaltung im Grenzfall — mit den drei echten Fehltreffern als Test |
| 5 | zu wenige fremdsprachige Artikel | gemessen 15,2 %, also 20–30 je Ausgabe |
| 6 | tote Links im Archiv | Dateiname = `Item.id` über die **normalisierte** URL; es wird nie etwas gelöscht |
| 7 | aufgeblähtes Repository | Speicher ist **JSONL**, die HTML-Seiten entstehen beim Rendern |
| 8 | fachlich falsche Übersetzung | Eigennamen/Produktnamen/Kürzel bleiben stehen, Ton wie der Bericht — im Prompt |
| 9 | ein Verlag meldet sich | „Maschinelle Übersetzung" und Originallink stehen **oben**, nicht als Fußnote |

---

## 4. Was das Ansehen der Seite gefunden hat

Drei Fehler, die kein Test gemeldet hatte, weil alle drei die Zeichenkette
richtig und den Satz falsch hatten:

1. **„aus dem Spanisch"** statt „aus dem Spanischen" — der Satz steht
   zweimal je Seite. Behoben mit `sprachname_dativ()`: was auf `-isch`
   endet, bekommt ein `-en`; „aus dem Hindi" und „aus dem Thai" bleiben.
2. **Sichtbarer Text in ASCII-Umschrift** („Maschinelle Uebersetzung",
   „Absaetze", „geprueft") — der Rest des Portals schreibt Umlaute. Die
   Umschrift gilt in diesem Projekt für Kommentare, nicht für die Seite.
3. **Der Pfeil stand vom Wort ab**, weil er als Leerzeichen im `content`
   das `letter-spacing` der Zeile erbte.

Die ersten beiden sind jetzt Tests
(`test_die_sprache_steht_im_richtigen_fall`,
`test_die_seite_schreibt_deutsch_mit_umlauten`).

Gemessen mit echtem Chromium: **0 px waagerechter Überlauf** auf 1440 und
390 px.

---

## 5. Was beim Testen aufgefallen ist

- **Ein vorgefilterter Artikel wurde nirgends gezählt.** Die Vorauswahl
  verwirft deutsche und englische Meldungen ohne Abruf — richtig, aber die
  Bilanz meldete „0 übersetzt, 0 übersprungen" und ließ offen, ob nichts
  fremdsprachig war oder die Vorauswahl gar nicht lief. Jetzt steht
  `vorgefiltert` mit Gründen in der Protokollzeile.
- **Ein Test war grün und prüfte nichts.** Die Prüfung „Archivseiten
  verlinken mit `../`" lief über eine leere Liste, weil die Archivwochen
  ihre Meldungen über `app.js` bauen. Mit `assert treffer` fiel sie sofort
  durch — ersetzt durch drei Tests, die den statischen Fall, den
  JSON-Datensatz und die Pfadrechnung in `app.js` einzeln treffen.

---

## 6. Zwei Korrekturen am Konzept

**Leitplanke A war bereits erfüllt.** Das Konzept warnt, ein neues Feld
lande „ohne weiteres Zutun in den Analysten-Prompts". `_items_payload` baut
die Nutzlast Feld für Feld — eine Positivliste. Nebenbei: der Analyst sieht
`summary[:300]`, nicht 600.

**Die 600 Zeichen bleiben unbegründet, und zwar prüfbar.** Das Repo ist ein
flacher Klon (58 Commits); `git log -S` findet einen Commit und hält ihn für
die Ersteinführung der Datei. Braucht `git fetch --unshallow`. Nach den
Messungen ist die Frage aber gegenstandslos: `summary` wurde nicht angefasst.

---

## 7. Offen

1. **Die Stufe ist noch nie gegen ein echtes Modell gelaufen.** Nach dem
   nächsten Actions-Lauf die Zeile `Uebersetzung:` lesen — sie nennt
   übersetzt / übersprungen / vorgefiltert / gescheitert **mit Gründen**.
2. **Keine Übersetzung ist von einem Menschen gelesen worden.** Die
   Phase-0-Probe war der EXTRAKT, nicht die Übersetzung. Premortem 2
   verlangt eine Stichprobe von Hand.
3. **Newsletter:** soll der rote Link mitgehen? Bewusst nicht entschieden —
   die Mail hat die Regel „keine neuen Inhalte", und ein Link auf eine
   Seite, die es zur Sendezeit noch nicht gab, ist ein Sonderfall, den der
   Treue-Test heute nicht kennt.
4. **Analysten:** 52 der 164 crawlbaren Quellen liefern ihnen nur die
   Überschrift. Der Volltext liegt jetzt bereit — ihn in die Prompts zu
   geben ist eine eigene Entscheidung.
5. **Platzbedarf** ist gerechnet, nicht gemessen. Nach vier Wochen die
   Dateigröße von `uebersetzungen.jsonl` nachsehen.
