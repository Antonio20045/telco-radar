# Skalierung des Telco Radars — Zwischenstand 04.08.2026

Umsetzung von `AUFTRAG_SKALIERUNG_1000.md`. Alle Zahlen sind gemessen, nicht
geschätzt; wo etwas geschätzt ist, steht es dabei.

---

## 1. Die Kennzahl, die den Ausbau steuert

Vor der ersten neuen Quelle gebaut (`scripts/trefferquote.py`), ausgewertet
über das vorhandene Berichtsarchiv — sechs Läufe vom 25.07. bis 04.08.2026,
also nur solche unter der heutigen Architektur:

| Ebene | Quellen | gesammelt/Lauf | bewertet/Lauf | **im Bericht/Lauf** | Bewertungsquote |
|---|---:|---:|---:|---:|---:|
| Betreiber | 127 | 12,4 | 0,03 | **0,03** | 0,2 % |
| Themenfelder | 25 | 18,6 | 0,28 | **0,08** | 1,5 % |
| Fachpresse | 14 | 16,7 | 0,80 | **0,67** | 4,8 % |

Die bisher einzige Zahl je Quelle — „Meldungen je Lauf" — liegt in allen drei
Ebenen praktisch gleich (15,9 / 18,6 / 17,6 in Lauf #67). Genau deshalb war sie
als Steuergröße wertlos. Die Zahl, auf die es ankommt, ist die letzte Spalte:
**eine Fachpressequelle bringt rund 22-mal so viele Meldungen in den
Wochenbericht wie eine Betreiberquelle.**

Zwei Einschränkungen, die dazugehören:

- Betreiberquellen sind **nicht ersetzbar**. Sie liefern die Provenienz
  („Vodafone hat X angekündigt", Originalquelle), die Fachpresse liefert
  Auswahl. Der Radar braucht beides; die Messung sagt nur, wo zusätzliche
  Quellen mehr bringen.
- Die Zuordnung war in den Altdaten unscharf: eine bewertete Meldung ließ sich
  nur über den Quellennamen zuordnen, und der ist bei Betreibern der
  Firmenname. Seit Lauf #68 trägt jede Meldung `source_url`, also den Kanal —
  ab dann ist die Zuordnung exakt. 15 % der bewerteten Meldungen im
  Auswertungszeitraum waren gar keiner abgefragten Quelle zuzuordnen (Reste der
  2026 entfernten Keyword-Nachrichtensuche); die Auswertung weist sie
  gesondert aus, statt sie zu verschlucken.

---

## 2. Die vier Engpässe

### 2.1 Sammelphase — Parallelität mit Host-Drosselung

Die Host-Serialität liegt jetzt im **Ablaufplan** statt in einer Sperre: alle
Quellen eines Hosts bilden eine Gruppe, die ein Worker nacheinander abarbeitet
(größte Gruppe zuerst). Damit warten keine Threads an einer Sperre, während
andere Hosts unangetastet bleiben — der Fehler, den ein bloß größerer
Worker-Pool bei 1000 Quellen produziert hätte.

**Lokal, dieselben 132 Quellen, unmittelbar nacheinander gemessen**
(`scripts/mess_sammelphase.py`):

| | vorher (8 Worker, keine Drosselung) | nachher (48 Worker, 1 s Host-Abstand) |
|---|---:|---:|
| Wanduhr | 37,0 s | **18,8 s** |
| Wanduhr je Quelle | 0,28 s | **0,14 s** |
| effektive Nebenläufigkeit | 7,1× | **28,2×** |
| gefundene Meldungen | 2 101 | 2 118 |

**In GitHub Actions, echter Lauf:**

| | Lauf #67 (vorher) | Lauf #68 (nachher) |
|---|---:|---:|
| Quellen | 130 | 132 |
| Sammelphase | 324,9 s | **303,1 s** |
| Arbeitszeit je Quelle | 20,0 s·Worker | **9,2 s·Worker** |
| Gesamtlaufzeit | 1 314,8 s (21,9 min) | **908,9 s (15,1 min)** |

Die Wanduhr der Sammelphase sinkt in Actions nur wenig — und das ist der
eigentliche Befund: **sie hängt jetzt nicht mehr an der Zahl der Quellen,
sondern an der langsamsten einzelnen Quelle.** Der Median liegt bei 3,2 s je
Quelle, die Summe aller Abrufzeiten bei 1 212 s — aber KT (Korea) brauchte
allein 299,8 s, bis seine Verbindungsversuche aufgaben, und bestimmt damit
die Phase praktisch im Alleingang. Bei 1000 Quellen bleibt die Phase deshalb
in derselben Größenordnung, solange die Worker-Zahl mit der Zahl der Hosts
mitwächst.

Daraus folgt der nächste Hebel, der noch offen ist: ein **Gesamtbudget je
Quelle**. `collect/http.py` probiert zwei User-Agents mit je drei Versuchen und
zwei Backoff-Pausen; im schlimmsten Fall sind das sechs Timeouts plus 26 s
Warten. Eine einzige unerreichbare Quelle kostet damit fünf Minuten Wanduhr.

### 2.2 Redaktion — zweistufig

Bisher bekam **ein** Editor-Aufruf sämtliche bewerteten Meldungen. Bei 1000
Quellen wären das ~650 Meldungen und ~122k Token — im Kontextfenster, aber
inhaltlich Brei, und ein einziger Fehlschlag kostet den ganzen Wochenbericht.

Jetzt: **Bereichsredakteure** (ein Aufruf je Region und je Themenfeld,
parallel, auf dem günstigen Analysten-Modell) liefern Abschnitt, Kurzfassung
und ihre stärksten Meldungen. Die **Chefredaktion** sieht nur die
Kurzfassungen und Top-Meldungen und schreibt daraus den Kopf des Berichts; die
Bereichsabschnitte werden darunter montiert, nicht neu geschrieben.

Ein Test hält die entscheidende Eigenschaft fest: **5 oder 200 bewertete
Meldungen ergeben denselben Chef-Prompt.** Die Eingabe der zweiten Stufe hängt
an der Zahl der Bereiche, nicht an der Zahl der Meldungen.

Belegt im echten Lauf #68: `editor_used: true`, Gliederung vollständig
(Auf einen Blick / Das Wichtigste / Die wichtigsten Signale / vier
Regionsabschnitte / Themen-Klammer mit H3 / Muster der Woche).

Zwei Details, die den Unterschied zwischen „läuft" und „läuft zuverlässig"
ausmachen:

- Die Bereichsredakteure antworten in **vier Blöcken mit Trennmarken**, nicht
  in JSON. Mehrzeiliges Markdown in einem JSON-String ist die klassische
  Stelle, an der ein Modell den rohen Zeilenumbruch stehen lässt — und da alle
  Bereiche denselben Prompt bekommen, hätte das nicht einen Abschnitt gekostet,
  sondern alle.
- Fällt ein Bereichsredakteur trotzdem aus, tritt ein **deterministischer
  Abschnitt** aus denselben Meldungen an seine Stelle, mit allen Quellenlinks.
  Ein Bereich verschwindet nie stumm: seine Meldungen hat der Seen-Store
  bereits als erledigt vermerkt, sie kommen kein zweites Mal.

### 2.3 Seen-Store — vom Ablaufdatum befreit

| | vorher | nachher |
|---|---:|---:|
| je Eintrag | 306 Byte (id, URL, Titel, Quelle, ISO-Zeitstempel) | **22 Byte** (id, Tagesnummer) |
| Bestand (1 968 Einträge) | 588 KB | **43 KB** |
| Hochrechnung 1000 Quellen | ~67 MB/Jahr | **~5 MB/Jahr** |

GitHubs hartes Limit je Datei liegt bei 100 MB. Mit 18 Monaten Verfall pendelt
sich die Datei bei ~8 MB ein.

**Die Kerngarantie bleibt unangetastet**, und zwar nicht durch Vorsicht,
sondern durch Konstruktion: verfallen können nur **datierte** Einträge. Taucht
so eine Meldung nach 18 Monaten erneut auf einer Quellenseite auf, wirft der
Frischefilter sie wegen ihres Datums weg. Undatierte Einträge — die einzigen,
die der Frischefilter nicht abfangen kann — verfallen nie.

### 2.4 Kosten und Anbieter-Limits

`scripts/kostenrechnung.py`, DeepSeek-Preise Stand 08/2026. Der Cron läuft um
08:30 UTC, also 16:30 Pekinger Zeit — mitten in der zweiten Stoßzeit mit
doppelten Preisen. Deshalb ist die rechte Spalte der Regelfall:

| | Normalpreis | Stoßzeit (Regelfall) |
|---|---:|---:|
| 130 Quellen, je Lauf | 0,024 $ | **0,048 $** |
| 130 Quellen, je Monat | 0,21 $ | **0,41 $** |
| 1000 Quellen, je Lauf | 0,083 $ | **0,165 $** |
| 1000 Quellen, je Monat | 0,72 $ | **1,43 $** |
| 1000 Quellen, **Erstlauf nach einer Welle** | 1,04 $ | **2,07 $** |

**Kosten sind nicht der Engpass** — 1,43 $ im Monat bei 1000 Quellen. Der
Engpass ist der Erstlauf nach einer großen Welle: dort liefern alle neuen
Quellen ihr volles Frischefenster auf einmal, das sind hochgerechnet ~1 100
Analysten-Aufrufe. Bei den heute 12 gleichzeitigen LLM-Aufrufen sind das ~92
Runden; bei 20 s je Aufruf rund 30 Minuten allein für die Analyse. Dafür ist
das Job-Timeout auf 120 Minuten erhöht (GitHub erlaubt 360).

**Nicht gemessen: das Rate-Limit von DeepSeek.** Der Schlüssel liegt als
GitHub-Secret vor und ist aus der Sandbox nicht erreichbar; eine Messung wäre
nur über einen eigenen Actions-Lauf möglich gewesen. Lauf #68 lief mit 12
gleichzeitigen Aufrufen ohne einen einzigen 429 durch — mehr lässt sich
belegen nicht sagen. **Vor dem Hochdrehen der Parallelität ist das zu messen**,
nicht anzunehmen.

---

## 3. Quellenregister und Quarantäne

`data/state/quellen_register.json` führt je Quelle: Herkunft und Abnahmedatum
(gepflegt in der YAML), ersten Lauf, letzten Erfolg, Bilanz aus ok/leer/Fehler
und die Serie erfolgloser Läufe. Nach sechs Läufen am Stück ohne Inhalt wird
eine Quelle stillgelegt — sie wird nicht mehr abgerufen, steht aber weiter mit
Status `quarantaene` im Protokoll. Jeder zehnte Lauf ist ein Bewährungslauf;
liefert die Quelle wieder, wird die Quarantäne aufgehoben. Ohne diesen zweiten
Teil wäre ein zweiwöchiger Serverausfall beim Betreiber ein Todesurteil.

In Lauf #68 angelegt: 132 Quellen, 0 in Quarantäne (der Zähler beginnt bei
diesem Lauf).

---

## 4. Welle 1 — was wirklich dabei herauskam

| Stufe | Zahl |
|---|---:|
| Kandidaten aus sechs parallelen Breitensuchen | 196 |
| Kandidaten aus der mechanischen Musterübertragung (4 796 probierte URLs) | 101 |
| **gesamt geprüft** | **297** |
| Abnahme-Check bestanden | 141 von 262 (Stand erste Runde) |
| davon von Hand verworfen | 72 |
| **eingetragen** | **69** |

### Warum 72 Quellen von Hand geflogen sind

Der Check prüft Form, nicht Wert. Alle 72 haben ≥ 5 datierte Meldungen mit
echten Überschriften geliefert und trotzdem im Radar nichts zu suchen:

- **31 Consumer-Gadget- und allgemeine Tech-Portale.** Titelproben wie „Mini-PC
  bei AliExpress im Angebot", „Apple-Watch-Armband im Test", „Pfandflaschen
  jetzt auch an der Tankstelle".
- **23 Enterprise-IT-, CIO- und Channel-Medien.** Richtige Branche, falsche
  Leserschaft: Cloud-Sicherheit für MSPs statt Tarife und Netzausbau.
- **9 allgemeine Nachrichten- und Startup-Portale** mit gelegentlichem
  Telko-Anteil.
- **3 Geschwisterseiten mit identischem Inhalt** (Telecom Review ME/Africa/Asia
  lieferten dasselbe ITU-Interview; TelcoNews .asia und .com.au teilen sich
  laut Erhebung zwei von drei Titeln). Je eine reicht.
- **3 Betreiberkanäle ohne verwertbare Meldungen**: AT&Ts
  Termin-/Dividendenkalender, TIM Brasils Angebotscodes als „Titel", ein
  zweiter WOM-Kanal auf denselben Newsroom.
- **1 kompromittierter Feed**: TeleAnalysis (IN) lieferte indonesische
  Food-Blog-Einträge.

### Was dazugekommen ist

**56 Fachpressequellen**, davon 45 nicht englischsprachig — die auffälligste
Lücke im Bestand ist damit geschlossen. 20 Länder, 16 Sprachen: teltarif.de und
der Golem-Ressortfeed Telekommunikation (DE), Ariase / AlloForfait /
Univers Freebox / Freenews (FR), bandaancha.eu und Redes&Telecom (ES), CorCom
(IT), TELKO.in und Telepolis (PL), TELETIME / TeleSíntese / Convergência
Digital / Mobile Time (BR), DPL News und TeleSemana (LatAm), Connecting Africa
/ ITWeb / TechCentral (ZA), Ecofin Telecom (frankophones Afrika),
ET Telecom Policy und Communications Today (IN), ETNews-Ressortfeed
Telekommunikation und ITmedia Mobile (KR/JP) und weitere.

**8 Zweitkanäle bestehender Betreiber** (SK Telecom, SoftBank, O2 Telefónica
Deutschland, Virgin Media O2, MTN Group, Turkcell, Hrvatski Telekom, True) —
gefunden von der Musterübertragung, ohne einen einzigen Modellaufruf.

**5 neue Betreiber**: Liberty Global, Magenta Telekom, eir, Optimum, Dialog
Axiata.

### Was die Musterübertragung wirklich gebracht hat

4 796 probierte URLs über alle 85 Betreiber, 101 Kandidaten, davon **15
bestanden den Abnahme-Check, 11 blieben nach Handprüfung**. Das ist eine
Ausbeute von 0,2 % je probierter URL — aber es kostete null Token und rund 15
Minuten Rechenzeit. Der teuerste Fehlergrund war mit Abstand die
Inhaltsdublette (57 von 86 Ablehnungen): die meisten gefundenen Feeds waren
derselbe Newsroom unter einem anderen Pfad.

Zwei Muster haben sich als produktiv erwiesen und gehören in die nächste Runde:
`<ir-host>/rss/news-releases.xml` (Q4/GlobeNewswire-IR-Plattformen) und
`/wp-json/wp/v2/posts` (WordPress-Newsrooms ohne verlinkten Feed).

---

## 5. Ehrliche Einordnung: 1000 sind das nicht

Der Auftrag nennt 1000 Quellen als Ziel und sagt zugleich: „Lieber 600 belegte
als 1000 behauptete." Der Stand nach dieser Session ist **206 konfigurierte
Quellen** — von 132. Der Weg auf 1000 ist damit nicht gegangen, sondern
befahrbar gemacht: die vier Engpässe, an denen ein naives Verzehnfachen
gescheitert wäre, sind beseitigt und gemessen, und der Apparat (Suche →
zentraler Check → Übernahme → Register) läuft im Massenbetrieb.

Was der Zahl im Weg steht, ist nicht die Technik, sondern der Vorrat an
Quellen, die den Abnahme-Check **und** die Wertprüfung bestehen. Von 297
mechanisch und agentisch gefundenen Kandidaten blieben 69 übrig — eine Quote
von 23 %. Auf 1000 Quellen hochgerechnet hieße das rund 3 700 zu prüfende
Kandidaten. Das ist machbar, aber es ist Arbeit für mehrere Wellen, nicht für
eine Session.

### Wo blinde Flecken bleiben

- **China (Festland).** Kein Fachmedium mit Datumsangaben: c114.com.cn hat 14
  Ressortfeeds, aber kein einziges Datumsfeld — undatierte Meldungen sortieren
  ans Ende und sind faktisch unsichtbar.
- **Vietnam.** Der einzige Ressortfeed liefert 1 000 unsortierte Meldungen mit
  neuestem Eintrag vom April.
- **Niederlande.** Telecompaper antwortet auf allen Feed-Pfaden mit HTTP 200
  und null Meldungen; Connexie sperrt jeden Abruf.
- **Marokko und Ägypten.** Keine telko-fokussierte Fachpresse mit Feed
  gefunden — beides Vodafone-nahe Märkte.
- **Geräte-Hersteller.** Honor, OPPO, vivo, Nothing, HMD, TCL: alle
  JavaScript-gerendert ohne statischen Endpunkt.
- **Die fünf bot-geschützten Betreiber** (TIM, Cosmote, UScellular, Ooredoo,
  Maroc Telecom) sind weiter nicht crawlbar. Für Cosmote decken jetzt drei
  griechische Fachmedien einen Teil ab.

### Was als Nächstes zu tun ist

1. **Trefferquote nach zwei bis drei Läufen neu auswerten** — mit `source_url`
   ist sie ab Lauf #68 exakt, und erst dann lässt sich sagen, ob die 56 neuen
   Fachpressequellen die Erwartung einlösen.
2. **Gesamtbudget je Quelle** in der Sammelphase (siehe 2.1).
3. **DeepSeek-Rate-Limit messen**, bevor die Parallelität steigt.
4. Nächste Welle entlang der Kategorien, die sich in Schritt 1 als tragend
   erweisen — nicht entlang einer Vorabannahme.
