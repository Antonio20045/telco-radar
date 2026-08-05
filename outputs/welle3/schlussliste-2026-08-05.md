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
| nach Welle 3b — Newsroom-Suche über die Liste aus Session 5 | 249 |
| nach Welle 3c — Recherche: Regulierer und Fachpresse | 272 |
| nach Welle 3d — Recherche: gemischt | 284 |
| nach Lauf #77: sieben Rubrikfeeds wieder ausgebaut (403) | 277 |
| nach Welle 3e — Recherche: kleinere Betreiber | **285** |

**+80 Quellen, +39 %.** Das Ziel 1000 ist nicht erreicht. Abschnitt 5 rechnet
vor, wo die Grenze wirklich liegt — sie liegt nicht dort, wo der Auftrag sie
vermutet hat.

### Die Ausbeute je Welle

| Welle | Suchaufträge | Kandidaten | bestanden | eingetragen |
|---|---:|---:|---:|---:|
| 3a Rubrikfeeds | 249 Sites | 138 | 53 | 26 |
| 3b Firmenliste aus Session 5 | 338 | 257 | 48 | 11 |
| 3c Recherche: Regulierer + Fachpresse | 234 | 308 | 63 | 23 |
| 3d Recherche: gemischt | 226 | 318 | 46 | 12 |
| 3e Recherche: kleinere Betreiber | 444 | 341 | 24 | 8 |
| **gesamt** | **1 491** | **1 362** | **234** | **80** |

Der Abstand zwischen „bestanden" und „eingetragen" ist die Wertprüfung: von
234 formal einwandfreien Quellen sind 154 von Hand verworfen worden.

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
Kandidaten neu vorschlagbar, 25 davon bestehen den Abnahme-Check, 11 sind
eingetragen worden. **An Kandidaten ist die Latte gerissen, an eingetragenen
Quellen nicht.**

Das ist kein Fehler der Erkennung, sondern die Eigenart der Restmenge: Firmen
ohne Feed sind genau die, deren Presseseite auch sonst schwach ist. Über alle
fünf Wellen hat die Newsroom-Erkennung **248 Kandidaten** beigesteuert, die
der alte Sucher nie hätte vorschlagen können — davon sind 24 eingetragen
worden, also fast ein Drittel aller 80 neuen Quellen.

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
sonst die Rubriknavigation der Site. 138 Kandidaten → 53 bestanden → 33
eingetragen → **26 übrig**, nachdem Lauf #77 sieben davon als HTTP 403
entlarvt hat (Abschnitt 7). Häufigster Ablehnungsgrund im Check war
Kriterium 4 (84-mal): eine Rubrik, die seit acht Tagen nichts veröffentlicht
hat, trägt zum Wochenbericht nichts bei.

---

## 4. Was verworfen wurde — und warum das die halbe Arbeit ist

Der Check prüft Form, nicht Wert. Von **234 bestandenen Kandidaten sind 80
eingetragen** worden — 154 sind von Hand verworfen worden. Das ist der
zweite Deckel neben der Wanduhr, und er ist genauso hart.

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

Nach fünf Wellen ist die Zahl belastbarer als die Schätzung von vorhin. Die
Ausbeute hängt massiv an der SORTE der gesuchten Firmen:

| Sorte | eingetragen je Suchauftrag |
|---|---:|
| Regulierer und Fachpresse (Welle 3c) | **9,8 %** |
| gemischt (Welle 3d) | 5,3 % |
| bereits abgeerntete Liste (Welle 3b) | 3,3 % |
| kleinere Betreiber (Welle 3e) | **1,8 %** |

Damit die Rechnung für die fehlenden 715 Quellen, mit der BESTEN gemessenen
Sorte gerechnet:

```
715 Quellen / 0,098 je Suchauftrag   ≈  7 300 Suchaufträge
7 300 Firmen / 4,2 Firmen pro Minute ≈  1 740 Minuten ≈ 29 Stunden reine Suche
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

**Realistisch sind 60 bis 80 zusätzliche Quellen je Session** — das war in
dieser Session, mit fünf Wellen und rund 1 500 Suchaufträgen, auch das
Ergebnis. Von 285 aus sind das **neun bis zwölf weitere Sessions** bis 1000.

Das ist die ehrliche Antwort auf die Frage des Auftrags. Sie lässt sich mit
drei Stellschrauben verbessern, keine davon ist eine Abkürzung:

* **Nur noch Regulierer und Fachpresse je Land suchen** (9,8 % statt 1,8 %).
  Das allein halbiert den Aufwand gegenüber einer gemischten Liste.
* **Die Wertprüfung ist der zweite Deckel**: 154 von 234 bestandenen
  Kandidaten wurden von Hand verworfen. Ein Teil davon ließe sich
  maschinell erkennen — Kampagnen-SKUs, hyperlokale Ausbaumeldungen,
  Terminkalender und Anbieter-Blogs sind wiederkehrende Muster, keine
  Einzelfälle. Das wäre der nächste sinnvolle Werkzeugbau.
* **Mehrere Kanäle je Host gehen nach hinten los** (Abschnitt 7).

---

## 6. Was für die nächste Session bereitliegt

`config/kandidaten_firmen_welle3.yaml` — **882 Suchaufträge** aus der
Sonnet-Recherche, entdoppelt und gegen den Bestand abgeglichen. Die Agents
haben ausdrücklich Websuche benutzt statt aus dem Modellwissen zu schreiben;
genau daran ist Session 5 bei 604 Firmen hängengeblieben. Der Rohtext liegt
als `outputs/welle3/recherche_roh.txt` daneben.

**Diese Liste ist abgearbeitet** (Wellen 3c, 3d, 3e). Sie liegt als Beleg im
Repo, nicht als Vorrat — wer sie noch einmal durchsucht, bekommt Welle 3b
zurück, also fast nichts.

**Der nächste Schritt ist deshalb doch wieder Recherche — aber eine engere.**
Nach der Messung in Abschnitt 5 lohnen sich nationale Regulierungsbehörden
und Fachpresse je Land und Sprache (9,8 % Ausbeute), während kleinere
Betreiber sich nicht lohnen (1,8 %). Eine Recherche, die nur noch diese
beiden Sorten sucht, ist die billigste verfügbare Verbesserung.

Der erweiterte Datums-Parser hat in dieser Session seine Messmenge übrigens
bekommen: die Wellen 3c bis 3e enthielten polnische, ungarische, russische,
koreanische und arabische Seiten. Der Gewinn blieb trotzdem klein, weil diese
Seiten überwiegend RSS liefern — und RSS trägt sein Datum im Protokoll, nicht
im Text. **Der Parser hilft nur bei `newsroom`-Quellen.**

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
