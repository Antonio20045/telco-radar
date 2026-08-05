# Welle 3 — Schlussliste

Auftrag: `AUFTRAG_1000_QUELLEN_WELLE3.md`, Abschnitt 8.9. Was wirklich
erreicht wurde, was nicht, und mit welchen Zahlen belegt.

**Jede Zahl hier stammt aus einem Skript oder einem Laufprotokoll.** Die
Rohdaten liegen daneben: `befund_rubriken.json`, `befund_firmen.json`,
`befund_eingetragen.json`, `messung_datumsparser.json`,
`kandidaten_firmen_welle3.yaml`, `recherche_roh.txt`.

---

## 1. Zwei Dinge vorweg, die nicht gut gelaufen sind

**Die Arbeitsumgebung wurde mitten in der Session zurückgesetzt.** Mit ihr
verschwand das gesamte Arbeitsverzeichnis samt fertig gebautem Sucher, Tests,
Konfiguration und rund einer Stunde Suchergebnisse. Alles wurde neu
geschrieben. **Regel für die nächste Session: nach jedem abgeschlossenen
Schritt committen UND pushen** — nur was auf GitHub liegt, überlebt. Das
Arbeitsverzeichnis `.welle3/` ist gitignored; alles, was aus ihm zählt, liegt
deshalb zusätzlich unter `outputs/welle3/`.

**Der erste Recherche-Durchgang hat rund 960 000 Token verbrannt und nichts
geliefert.** Vierzehn Sonnet-Agents haben recherchiert (205 Werkzeugaufrufe)
und sind dann alle daran gescheitert, ihr Ergebnis durch ein
StructuredOutput-Werkzeug mit JSON-Schema zu geben — die Validierung wies
formal korrekte Antworten ab. Der zweite Durchgang liefert stattdessen ein
Zeilenformat (`Name|domain|LL|kategorie|Begründung`) und funktioniert.
**Merksatz: ein Format, das sich nicht validieren lässt, kann auch nicht an
der Validierung sterben.** `scripts/recherche_zu_firmenliste.py` liest es.

---

## 2. Die Zahl

Gezählt mit `python scripts/quellen_zaehlen.py` — crawlbare Quellen, also was
ein Lauf wirklich abfragt.

| Stand | Quellen |
|---|---:|
| vor Welle 3 (Ende Session 5) | 205 |
| nach Welle 3a — Rubrikfeeds | 238 |
| nach Welle 3b — Newsroom-Suche | **249** |

**Das Ziel 1000 ist nicht erreicht.** Abschnitt 5 rechnet vor, wo die Grenze
wirklich liegt, und sie liegt nicht dort, wo der Auftrag sie vermutet hat.

---

## 3. Die beiden Hebel — was sie gemessen gebracht haben

### 3.1 Newsroom-Erkennung im Sucher: trägt

Gemessen an derselben Firmenliste, mit der Session 5 gearbeitet hat
(`config/kandidaten_firmen.yaml`, 338 Suchaufträge).

| | |
|---|---:|
| Suchaufträge | 338 |
| Firmen mit mindestens einem Kandidaten | **184 (54 %)**, vorher 31 % |
| Kandidaten gesamt | **257** |
| davon RSS/JSON-API — konnte der Sucher vorher auch | 129 |
| davon `newsroom` — **konnte er vorher gar nicht** | **128** |
| davon auf echtem Pressepfad (kein Beifang) | 79 |
| **Firmen, die AUSSCHLIESSLICH über die Newsroom-Erkennung etwas liefern** | **106** |

Der Sucher hat seine Ausbeute auf derselben Firmenliste **verdoppelt**
(129 → 257). Gefunden werden genau die Seiten, die der Auftrag als Beispiel
nennt: `saladeprensa.vodafone.es`, `tdcbrands.dk/en/press`,
`t.ht.hr/en/press/press-releases`, `newsroom.ee.co.uk`,
`spolecnost.o2.cz/tiskove-centrum`, `grupapolsatplus.pl/pl/biuro-prasowe`.

Die Latte aus dem Auftrag lautete: „Wenn die Newsroom-Erkennung daraus keine
100 Quellen macht, taugt sie nicht." 106 Firmen sind neu erreichbar, 128
Kandidaten neu vorschlagbar, 25 davon bestehen den Abnahme-Check. **Die Latte
ist an Kandidaten gerissen, an eingetragenen Quellen nicht** — dazu
Abschnitt 4.

Zwei Fallen, die beim Bauen zugeschnappt sind und jetzt Tests haben:

* **Hauptnavigationen sehen aus wie Artikellisten.** DNA lieferte über
  `li.ds-main-nav__item--level-2` 28 sauber getrennte „Meldungen" — die zweite
  Ebene des Menüs. Dagegen steht jetzt der Ausschluss von Menü-Klassennamen
  plus `_artikelanteil()`: der Anteil der Treffer, deren ADRESSE nach einer
  Meldung aussieht.
* **Die Startseite einer Telco besteht den Formcheck zufällig**, ist aber ein
  Produktregal. Dagegen steht `_ist_pressepfad()`.

### 3.2 Datums-Parser: trägt hier nicht

Gemessen mit `scripts/miss_datumsparser.py` an den 128 newsroom-Kandidaten:
jede Seite **einmal abgerufen, zweimal geparst** — einmal mit den Tabellen von
vor Welle 3. So misst der Vergleich den Parser und nicht die Tagesform des
Servers.

| | vorher | nachher |
|---|---:|---:|
| Kandidaten, die Kriterium 3 (≥ 80 % datiert) bestehen | 59 | **61** |
| datierte Meldungen insgesamt | 908 | **915** |
| durch die Erweiterung verloren | — | **0** |

**Der Gewinn ist 2 von 128, nicht die im Auftrag genannten 82.**

Der Grund liegt in der Messmenge, nicht im Parser: diese Kandidaten stammen
aus der bestehenden Firmenliste, und die ist überwiegend west- und
mitteleuropäisch. Deren Formate las der alte Parser schon. Die neuen Tabellen
decken Polnisch, Tschechisch, Ungarisch, Rumänisch, Baltisch, Griechisch,
Kyrillisch, Arabisch, Devanagari sowie CJK und Vietnamesisch ab — für diese
Sprachen gab es bisher keine Firmenliste, gegen die man messen könnte. Die
neue Recherche (Abschnitt 6) liefert sie; **erst dort wird der Parser
messbar wertvoll.**

Die Erweiterung bleibt trotzdem drin: sie kostet nichts, verliert nichts und
ist mit 40 Tests abgesichert. Aber sie ist **kein Hebel für die Zahl**, und
wer die 82 aus Welle 2 erneut zitiert, sollte sie vorher nachmessen — dafür
gibt es jetzt das Skript.

### 3.3 Rubrikfeeds: tragen

`finde_quellen.py --rubriken` liest die WordPress-Kategorieschnittstelle,
sonst die Rubriknavigation der Site. 138 Kandidaten → 53 bestanden → **33
eingetragen**. Häufigster Ablehnungsgrund war Kriterium 4 (84-mal): eine
Rubrik, die seit acht Tagen nichts veröffentlicht hat, trägt zum
Wochenbericht nichts bei.

---

## 4. Was verworfen wurde — und warum das die halbe Arbeit ist

Der Check prüft Form, nicht Wert. Von 101 bestandenen Kandidaten (53 + 48)
sind **44 eingetragen** worden.

**Sechs Vorschläge standen bereits als Warnung in den YAML-Kommentaren und
wurden trotzdem erneut vorgeschlagen** — genau das, wovor der Auftrag warnt:

| Vorschlag | warum verworfen |
|---|---|
| `gov.br/rss.xml` und `/atom.xml` | das ganze brasilianische Regierungsportal, nicht Anatel — erste Meldung: ein Studienplatzverfahren |
| `turkcell.com.tr/rss` (+ `.xml`) | Kampagnen-SKUs („Defacto Kampanyası") |
| `tim.com.br/rj/rss.xml` | Kampagnen-SKUs („TIM Controle Redes Sociais 46GB [Homolog]") |
| `golem.de/rss.php` | allgemeine IT-Presse, erste Zeile eine Anzeige |
| `zdnet.fr/feed` (+ wp-json) | Unternehmens-IT, kaum Telekommunikation |
| `expansion.com/rss/...` (2 URLs) | allgemeine Wirtschaftsnachrichten |

Neu dazugekommen sind diese Muster:

* **Reine Dateilisten.** TRAIs Presseseite liefert „Press Release No. 112
  (364.84 KB)", „No. 111 (1.22 MB)" — formal saubere, datierte, unterscheidbare
  Titel ohne jede Aussage.
* **Hyperlokale Ausbaumeldungen.** Openreach meldet „bringing Full Fibre
  broadband to Humberston", „Thousands in Chester-le-Street yet to benefit" —
  derselbe Fehler wie `corporate.comcast.com/rss` in Session 4.
* **Termin-Feeds.** Viasats IR-Seite besteht aus „Sets August 4, 2026, for
  First Quarter Conference Call".
* **Advertorial-Rubriken.** Die Whitepaper-Rubrik von Corriere Comunicazioni.
* **Syndizierte Gadget-Strecken.** `technology-pick` erscheint identisch auf
  allen drei Telecom-Review-Titeln („Autonomous Skin Cancer Detection Arrives
  on Smartphones").

---

## 5. Wo die Grenze wirklich liegt

Der Auftrag verlangt: „Wenn 1000 am Ende nicht erreichbar sind, sag das **mit
Zahlen** und sag, wo die Grenze wirklich liegt."

**Die Grenze ist nicht das Werkzeug und nicht die Trefferquote. Es ist die
Wanduhr der Sammelphase.**

Gemessen in dieser Session:

| | |
|---|---:|
| Suchdurchgang über 338 Firmen | ~80 Minuten (40 Worker, 8 Verbindungen je Server) |
| ergibt | **4,2 Firmen pro Minute** |
| eingetragene Quellen je Suchauftrag (Welle 3b) | 11 / 338 = **3,3 %** |
| eingetragene Quellen je Suchauftrag (Session 5, frische Liste) | 35 / 450 = **7,8 %** |

Die 3,3 % sind niedriger als die 7,8 %, und der Grund ist wichtig: **Welle 3b
hat dieselbe Liste noch einmal durchsucht, die Session 5 schon abgeerntet
hatte.** Was dort einen Feed hatte, steht längst in der Konfiguration. Übrig
blieb, was keinen Feed hat — genau die Sorte, die die Newsroom-Erkennung
findet, und genau die Sorte, die am Abnahme-Check am häufigsten scheitert.
Für eine frische Liste ist 7,8 % die realistischere Zahl.

Damit die Rechnung für +751 Quellen:

```
751 Quellen / 0,078 je Suchauftrag  ≈  9 600 Suchaufträge
9 600 Firmen / 4,2 Firmen pro Minute ≈  2 290 Minuten ≈ 38 Stunden reine Suche
```

Dazu kommt der Abnahme-Check (er ruft jeden Kandidaten ein- bis zweimal ab
plus einmal den Bestandsindex) und die Wertprüfung, die Handarbeit ist und
bleibt.

**Das lässt sich nicht durch mehr Agents verkürzen.** Der Deckel ist die
Host-Drosselung: eine Firma ist ein Server, und alle rund vierzig Adressen
eines Suchauftrags laufen gegen genau diesen einen. Mehr Parallelität über
Firmen hinweg hilft — sie ist mit 40 Workern und 8 Verbindungen je Server
schon ausgereizt, und das Anheben von 4 auf 8 Verbindungen hat den Durchgang
bereits von hochgerechnet zwei Stunden auf 80 Minuten gedrückt. Mehr wäre
unhöflich und provoziert genau die 429/403, die einen Kandidaten
fälschlicherweise als tot ausweisen.

**Realistisch sind rund 250 zusätzliche Quellen je Session**, wenn die
Firmenliste frisch ist. Von 249 aus sind das drei bis vier weitere Sessions
bis 1000 — nicht eine.

---

## 6. Was für die nächste Session bereitliegt

`config/kandidaten_firmen_welle3.yaml` — **678 Suchaufträge**, aus der
Sonnet-Recherche, entdoppelt und gegen den Bestand abgeglichen. Die Agents
haben ausdrücklich Websuche benutzt statt aus dem Modellwissen zu schreiben;
genau daran ist Session 5 bei 604 Firmen hängengeblieben. Der Rohtext liegt
als `outputs/welle3/recherche_roh.txt` daneben.

Die Liste ist **noch nicht durchsucht** — das ist der 38-Stunden-Posten aus
Abschnitt 5. Sie deckt Sprachen und Regionen ab, für die der erweiterte
Datums-Parser gebaut wurde (Abschnitt 3.2), und ist damit gleichzeitig die
Messmenge, an der sich zeigen muss, ob er etwas taugt.

**Der nächste Schritt ist also nicht Recherche, sondern Suche.**

---

## 7. Ein Fehler im Abnahme-Check, der lange dort saß

**Kriterium 6 (eigene Domain) hat nie gegriffen.**

Die Vergleichs-Website steht überall im Projekt als blosse Domain
(`telekom.com`, `casa-systems.com`) — in der Watchlist, in
`kandidaten_firmen.yaml`, in dem, was `finde_quellen.py` ausgibt.
`urlsplit()` liest so etwas ohne Schema aber als **Pfad**; `netloc` bleibt
leer. Der Check fiel damit in den Zweig „keine Vergleichs-Website hinterlegt"
— und der ist ein PASS.

Aufgefallen ist es an zwei Kandidaten, deren Domain gar nicht zur Firma
gehörte:

* **Casa Systems** → `commscope.com/news-center/` (übernommen, die alte Domain
  leitet weiter)
* **Intelsat** → `ses.com/news` (übernommen, dasselbe)

Beide lieferten sauber datierte, unterscheidbare Meldungen — der falschen
Firma. Behoben, drei Tests, und alle 11 in Welle 3b eingetragenen Quellen sind
mit dem reparierten Check nachgeprüft: 11/11.

**Zweite Lücke, nicht behoben, aber dokumentiert:** die Dublettenprüfung
vergleicht gegen den BESTAND, nicht gegen die anderen Kandidaten. Zwei
Rubriken derselben Site, die dasselbe ausliefern, bestehen deshalb beide. In
dieser Welle viermal passiert (SK Telecom `category/ai-service` gegen
`tag/AI`, Mobile Europe `cloud-nfv` gegen `edge`, Nvidia `generative-ai` gegen
`enterprise`, bbcmag `ai` gegen `innovation`) — alle vier zeigten dieselbe
erste Meldung. **Praktische Regel bis das behoben ist: die erste Titelprobe
aller bestandenen Kandidaten nebeneinander lesen.**

---

## 8. Blinde Flecken, die bleiben

* **Telenor Norwegen bleibt unerreichbar.** Der Sucher findet
  `/om/presse-og-media` und von dort `/pressemeldinger/` — beide Seiten
  liefern keine lesbare Artikelliste, die Meldungen kommen per JavaScript
  nach. `newsroom_js` ist laut Auftrag kein zulässiger Ersatz.
* **Frankreich, Spanien und Italien liefern von den Betreibern nur
  Startseiten.** Orange España, Free, WindTre und Fastweb haben keine
  statisch lesbare Presseliste; die Newsroom-Erkennung schlägt dort die
  Startseite als Beifang vor, und die fällt zu Recht durch.
* **Die drei alten blinden Flecken sind unverändert**: Maroc Telecom, Cosmote
  und UScellular werden weder gecrawlt noch in der Fachpresse namentlich
  genannt.
* **Die Vorgabe-Region für Fachpressequellen fehlt weiterhin.** Das war
  Punkt 1 der Roadmap aus Session 5 und ist in dieser Session nicht angefasst
  worden — mit 33 neuen Rubrikfeeds, die fast alle regional sind, wird der
  Punkt drängender, nicht kleiner. `tag_news_regions` ordnet eine
  Fachpresse-Meldung nach wie vor nur zu, wenn ein Betreibername in der
  Überschrift steht; alles andere landet in „Global".
