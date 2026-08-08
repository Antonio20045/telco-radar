# Umsetzungsplan — Schlussliste

Stand: 08.08.2026. Auftrag: „diggah erledige alles, setze alle Phasen um."
Grundlage war der Umsetzungsplan mit Teil 1 (Einrichtung) und den Aufträgen
A1–A10.

**Ergebnis: 1080 Tests, alle 14 Prüfungen von `pruefe_portal.py` grün,
207 crawlbare Quellen.** Vorher: 870 Tests.

---

## Was gebaut wurde

| # | Auftrag | Stand | Tests |
|---|---|---|---|
| Teil 1 | Einrichtung | **neu** | — |
| A1 | Ereignis-Clustering | war schon da (`analyze/clustering.py`) | — |
| A2 | Quellen-Reparatur | war schon da (Browser-UA, `certifi`) | — |
| A3 | CT-Radar | **neu** | 44 |
| A4 | Tarif-Extraktor | **neu** | 44 |
| A5 | Tarif-Sammler und Historie | **neu** | 39 |
| A6 | Effektivpreis und Positionskarte | **neu** | 33 |
| A7 | CTM-Linse und Prüfschritt | war schon da (`analyze/ctm.py`, `faithfulness.py`) | — |
| A8 | Foliensatz-Export | **neu** | 27 |
| A9 | Kleingedruckt-Wächter | **neu** (fällt aus A5) | in A5 |
| A10 | Frag das Archiv | **neu**, aber anders als geplant | 23 |

A1, A2 und A7 waren am selben Tag von der Vorsession umgesetzt worden — der
Plan datiert vom 08.08., das Review-Dokument ebenfalls. Nachgemessen, nicht
angenommen: `analyze/clustering.py` mit `tests/test_clustering.py`,
Browser-UA in `settings.yaml:395`, `certifi` explizit in `http.py:66-74`,
`analyze/ctm.py` plus `analyze/faithfulness.py` plus `config/ctm_fokus.yaml`.

---

## Die zwei Dokumente, die fehlen

`claude/site-review-und-feature-roadmap-2026-08-08.md` und
`claude/neue-features-ideenkatalog-2026-08-08.md` sind **nicht im Repo** — es
gibt kein Verzeichnis `claude/`. Jeder Auftragstext verweist darauf, und dort
stehen laut Plan die Fixture-Fälle (A1) und die erwarteten Feldwerte (A4).

Gebaut wurde deshalb gegen **echte Dokumente statt gegen die Tabelle**: vier
Produktinformationsblätter, live geholt und als Fixture abgelegt. Die
URL-Muster aus dem Plan stimmen alle drei nicht mehr
(`telekom.de/produktinformationsblatt/<tarif>.pdf` → 404,
`content.1und1.de/pib/` → 403, der o2-S3-Pfad ist nicht mehr verlinkt). Die
echten Einstiegspunkte sind im Sammler konfiguriert.

---

## Die Befunde, die je einen Test tragen

### A3 — CT-Radar

* Gemessen gegen `congstar.de`: **79 Zertifikate, 48 DNS-Namen**, darunter
  `jamobil-news.congstar.de` und `pennymobil.congstarnews.de` — die
  Zweitmarken für Rewe und Penny. Beide waren über keine andere Ebene dieses
  Radars sichtbar.
* Der Rauschfilter vergleicht **labelweise, nicht als Teilkette**. Ein
  Teilkettenfilter mit „ns" hätte `news.congstar.de` verworfen, also genau
  die Meldung, die dem Radar seinen Wert gibt.
* Der Timeout großer Domains ist eine **eigene Fehlerklasse** und
  ausdrücklich kein leeres Ergebnis: als leeres Ergebnis gespeichert wäre die
  Grundlinie danach leer und der nächste Lauf meldete alle 47 Namen als neu.
* Erster Lauf in Actions: **15 Domains gelesen, 0 Funde, 0 Zeitüberschreitungen**
  — Grundlinie korrekt gelegt.

### A4 — Tarif-Extraktor

Vier echte Dokumente, alle vollständig korrekt ausgelesen:

| Dokument | Preis | Volumen | Laufzeit | Staffel |
|---|---|---|---|---|
| Telekom MagentaMobil Basic | 24,95 € | 5 GB | 24 Mon | 5 Stufen |
| Telekom MagentaMobil L | 59,95 € | 80 GB | 24 Mon | 5 Stufen |
| o2 Mobile Unlimited M Flex | 39,99 € | unbegrenzt | 0 (Flex) | — |
| o2 Home L Flex | 44,99 € | — | 0 (Flex) | — |

* Die **Gerätestaffel steht spaltenweise über drei Zeilen**. Verkettet und
  per Regex gelesen ergab sie „mit Premium- mit Premium- Smartphone" — zwei
  Spalten zu einer Überschrift verschmolzen. Ein harter Schnitt an der
  Zeichenposition zerschnitt dafür „Smartphone" zu „Smartphon"/„e". Trägt
  jetzt das **Wort** als kleinste Einheit, zugeordnet über seine Mitte.
* Die **Spaltenbreite wird gemessen, nicht geschwellt.** Mit fester Toleranz
  stand „Hardware" aus der Zeilenbeschriftung in einem Dokument 15 und im
  anderen 14 Zeichen von der ersten Spalte entfernt — je nach Schwelle sauber
  oder als „ohne Smartphone Hardware".
* Die **Grundgebühr ist der kleinste Wert der Staffel.** Der erste Wert der
  Zeile stimmt meistens und ist manchmal 40 € zu hoch.
* **Zwei Satzstellungen für die Kündigungsfrist.** Telekom stellt die Zahl
  hinter den Begriff, o2 davor („Frist von 1 Monat gekündigt") — die erste
  Fassung ließ bei beiden o2-Dokumenten das Feld leer.
* o2 setzt ein **U+200B** hinter „Keine Mindestlaufzeit". Unsichtbar, also
  unauffindbar, wenn man es nicht kennt.
* „Keine Mindestlaufzeit" ergibt **0, nicht None**: eine Aussage, kein
  fehlender Wert. Als None rechnete der Effektivpreis gegen 24 Monate, die es
  nicht gibt.

Die Logik arbeitet auf **Text, nicht auf PDF**. `pdftotext` ist ein externes
Binary; hängt die Extraktionslogik daran, fällt die halbe Suite aus, sobald
jemand sie woanders laufen lässt.

### A5 — Tarif-Sammler

* **Keine ID-Enumeration**, maschinell geprüft. `sammle()` führt Buch über
  jede abgerufene Adresse; `test_crawler_ruft_nur_verlinkte_adressen_ab`
  stellt eine erreichbare, aber nicht verlinkte Falle auf. **Im Livelauf war
  `nicht_verlinkt` leer.** Eine Regel, die nur im Kommentar steht, ist keine.
* Nebenbei ist es die einzige Methode, die funktioniert: beim Bau wurde
  `magentamobil-l-20250401` geraten — es gibt nur
  `magentamobil-data-l-20250401`.
* Der **Content-Type entscheidet, nicht die Dateiendung.** Die Telekom liefert
  ihre PIBs unter `/produktinformationsblatt/<slug>` ohne `.pdf`. Wer auf die
  Endung filtert, findet dort kein einziges Dokument.
* Die **`tarif_id` hängt nicht am Dokument.** Der Telekom-Slug trägt das
  Vermarktungsdatum; eine ID aus der Adresse hätte nie zwei Stände verbunden.
* Ein Feld, das der Extraktor diesmal nicht fand, ist ein **Ausfall, keine
  Änderung.** „80 GB → nicht angegeben" wäre die häufigste Falschmeldung.
* **Aus dem Livelauf:** o2 führt `o2-home-l-flex` und `o2-home-l-175-flex`
  als getrennte PDFs mit identischer Überschrift. Zwei Stände nacheinander
  sind eine Versionsfolge, zwei im selben Lauf sind zwei Produkte.

### A6 — Effektivpreis

* Der Testfall aus dem Auftrag ergibt **exakt 24,99 €**
  ((6 × 9,99 + 18 × 29,99) / 24).
* Der **Horizont ist fest auf 24 Monate**, auch für Flex-Tarife. Wer ihn je
  Tarif aus der Laufzeit nimmt, vergleicht zwei Rechnungen.
* **Immer drei Werte.** Eine Rangliste nach Effektivpreis allein wäre eine
  Rangliste der Drosselung.
* Eine fehlende Komponente ist eine **Lücke, keine Null.**
* Die Positionskarte ist ein **gerechnetes SVG** — kein CDN-JS, ohne Browser
  testbar. Unbegrenzte Tarife stehen nicht in der Wolke.
* Gegengerechnet: Vodafone Red M landet bei **26,66 €** — weder die
  beworbenen 9,99 € noch 29,99 €.

### A8 — Foliensatz

* Feste Vorlage, feste Platzhalter, **harte Zeichengrenzen aus der
  Design-Spezifikation** (dort als häufigste Korrekturursache benannt).
* Was nicht passt, wird an der Wortgrenze gekürzt. Läuft trotzdem etwas über,
  **wirft `baue()`** statt eine Folie auszuliefern, deren Überlauf erst im
  Termin auffällt.
* Die **Quellenfolie hat keinen Schalter**; ein Test prüft die Signatur.

### A10 — Frag das Archiv, anders als geplant

Der Plan sieht BM25 + Embeddings + Cross-Encoder + Synthese vor. Das braucht
einen **Dienst zur Laufzeit** — und die Website ist eine Static Site ohne
Backend, was die Bedingung dafür ist, dass sie nie einschläft (CLAUDE.md §6
führt RAG deshalb als bewusst nicht gebaut).

Gebaut ist die Zusage des Auftrags, und zwar **stärker**: die Antwort ist
extraktiv. Jede Zeile *ist* ein Archiveintrag. Ein Modell kann die Zusage
„jede Fußnote deckt ihre Aussage" nur einhalten, wenn ein Prüflauf sie
nachträglich erzwingt; eine extraktive Antwort **kann sie nicht verletzen**.

Was fehlt — die zusammenfassende Prosa — steht offen auf der Seite. Dafür
gibt es den Wochenbericht, und der läuft durch den Prüflauf.

Am echten Bestand gemessen (**737 Einträge**): echte Fragen erreichen 6 bis 9
Punkte, eine Unsinnsfrage exakt 0. Die Schwelle liegt bei 1,0.

---

## Zwei bewusste Abweichungen

1. **Die Navigation wächst auf sieben Einträge.** CLAUDE.md nagelt sie auf
   sechs fest, und ein Test hielt die Zahl. „Tarife" ist die erste Seite, die
   nicht aus Meldungen entsteht, sondern aus den einzigen Daten dieses
   Marktes, die rechtlich wahrheitsbewehrt sind. Die Begründung steht im
   Test, damit die achte Seite sich wieder rechtfertigen muss.
2. **`commit-sicher` pusht auf den aktuellen Branch**, nicht hartverdrahtet
   auf `main`. Der Plan schreibt `main`; die Sitzungen dieses Repos arbeiten
   auf `claude/…`-Branches, und ein festes `main` hätte Feature-Arbeit auf den
   Hauptzweig geschoben.

---

## Offen, erst nach dem nächsten Actions-Lauf prüfbar

1. **Die Telekom-Einstiegsseite antwortet httpx mit HTTP 202** (dokumentiert
   in CLAUDE.md §5). Im Livelauf lieferte sie deshalb null Links; nur die drei
   o2-Dokumente wurden gelesen. In Actions ist das Verhalten möglicherweise
   anders — im Protokoll die Zeile `Tarif-Sammler:` ansehen. Falls dort
   weiterhin nur o2 steht, braucht die Telekom-Quelle den JS-Collector.
2. **1&1 fehlt in `tarif_quellen.yaml`**, mit Grund: das Verzeichnis unter
   `hilfe-center.1und1.de` ist eine Next.js-Seite, im Quelltext stehen nur
   Chunk-Dateien. Braucht den JS-Collector, keinen geratenen Pfad.
3. **Der CT-Radar hat seine Grundlinie**, aber noch nie einen Fund gemeldet —
   das ist beim ersten Lauf richtig so. Ab dem zweiten Lauf im Protokoll die
   Zeile `CT-Radar:` ansehen: meldet er zweistellig viele Namen je Domain,
   ist der Rauschfilter zu grob; meldet er nie etwas, ist er zu scharf.
4. **Die Modellstufe des CT-Radars ist noch nie gegen ein echtes Modell
   gelaufen.** Sie darf wegnehmen, nicht hinzufügen; ein Aussetzer verwirft
   nichts.
5. **`tarife.html` steht mit drei Tarifen.** Die Positionskarte braucht
   mindestens drei Punkte für eine Ausgleichsgerade — mit den zwei
   o2-Tarifen aus dem Livelauf zeigt sie noch keine.
6. **Vodafone fehlt in der Tarif-Datenbank.** `vodafone.de/infofaxe` liefert
   HTTP 200, die Linkernte dort ist aber nicht gemessen. Ohne den eigenen
   Punkt zeigt die Positionskarte den Markt ohne uns.

## Nicht angefasst

`config/vodafone_hebel.yaml` ist weiterhin leer ausgeliefert — zwölf Hebel
auf `offen`. Das ist der eine Punkt, den nur ein Mensch schließen kann.
