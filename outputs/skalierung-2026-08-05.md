# Skalierung auf 1000 Quellen — Stand nach Session 5

Auftrag: `AUFTRAG_SKALIERUNG_1000.md`. Dieser Text ist die Schlussliste aus
Abschnitt 8.10 — was wirklich erreicht wurde, was nicht, und mit welchen
Zahlen belegt.

**Kurzfassung: Die Architektur trägt jetzt 1000 Quellen. Die Quellen sind es
noch nicht — es sind 167 statt 130. Und der Grund dafür ist eine Messung,
keine fehlende Zeit.**

---

## 1. Was abgeliefert wurde

| Auftrag | Stand |
|---|---|
| 1. Sammel-Parallelität mit Host-Drosselung, gemessen | **fertig**, in GitHub Actions gemessen |
| 2. Zweistufige Redaktion mit Tests | **fertig**, 21 Tests, im Lauf #75 abgenommen |
| 3. Seen-Store für 200 000 Einträge/Jahr | **fertig**, Faktor 17,6, Bestand migriert |
| 4. Quellenregister + automatische Quarantäne | **fertig**, 14 Tests |
| 5. Trefferquote je Quelle über das Archiv | **fertig**, vor der ersten neuen Quelle |
| 6. Quellen in Wellen, jede mit echtem Actions-Lauf | **teilweise**: eine Welle, +29 Quellen, Diagnoselauf #74 + Volllauf #75 |
| 7. Kostenrechnung je Lauf und Monat | **fertig** |
| 8. `pytest -q` grün, Quellen-Doku neu | **fertig**, 410 Tests |
| 9. `CLAUDE.md` fortgeschrieben | **fertig** |
| 10. Ehrliche Schlussliste | dieser Text |

---

## 2. Die Trefferquote — die Kennzahl, die alles steuert

Gebaut **vor** der ersten neuen Quelle, wie der Auftrag es verlangt
(`scripts/quellen_trefferquote.py`, ausgewertet über 11 Läufe,
16.07.–04.08.2026).

Der wichtigste Teil ist der Nenner. Die naheliegende Rechnung
„bewertet / gesammelt" ergibt 1,9 % — und ist falsch: ein Newsroom liefert bei
jedem Abruf dieselben 30 Meldungen, ein Fachpresse-Feed jedes Mal andere.
Gegen „gesammelt" gerechnet misst die Kennzahl die Abrufhäufigkeit, nicht den
Wert. Richtig ist **bewertet / NEU**:

| | gesammelt | neu | bewertet | Trefferquote | im Bericht |
|---|---:|---:|---:|---:|---:|
| Fachpresse | 2 471 | 1 286 | 157 | **12,2 %** | 122 |
| Betreiber | 9 197 | 617 | 65 | **10,5 %** | 39 |
| Themenfelder | 466 | 65 | 7 | **10,8 %** | 2 |
| **gesamt** | **12 134** | **1 968** | **229** | **11,6 %** | **163** |

**Das bestätigt die Vorgabe des Auftrags, keine Mischung vorab festzulegen.**
Die drei Ebenen liegen bei der Trefferquote so eng beieinander wie schon bei
den Meldungen je Quelle. Es gibt weiterhin keinen Beleg, dass eine Kategorie
wertvoller wäre.

Ein Unterschied ist trotzdem sichtbar, und er betrifft nicht die Bewertung,
sondern den **Weg in den Bericht**: von den neuen Meldungen der Fachpresse
landen 9,5 % im Prosa-Wochenbericht, von denen der Betreiber 6,3 %. Fachpresse
schreibt bereits eingeordnet; eine Betreiber-Pressemitteilung muss der Analyst
erst einordnen. Für die Frage „wo ausbauen" ist das ein Hinweis, kein Beweis —
die Themenfelder haben mit 65 neuen Meldungen aus einem Lauf noch gar keine
belastbare Basis.

**Ballast, belegt:** 11 Quellen haben über 11 Läufe mindestens 10 neue
Meldungen geliefert, von denen **keine einzige** je bewertet wurde — Iliad
(40), stc (33), AIS (30), PLDT (21), Deutsche Telekom (19), Telstra (16),
OpenAI (14), Türk Telekom (13), Bouygues (12), Turkcell (12), Charter (10).
Weitere 50 Quellen sehen genauso aus, haben aber unter 10 neue Meldungen —
dort ist „nie bewertet" Zufall, kein Befund. Die Trennung steht so im Bericht,
damit niemand aus n=3 eine Entscheidung ableitet.

---

## 3. Die vier Engpässe

### 3.1 Sammelphase — gelöst, aber der Gewinn ist kleiner als er lokal aussah

Host-Drosselung in `collect/http.py` (`HostGate`): global viele Verbindungen,
je Host höchstens zwei gleichzeitig plus Mindestabstand. Das Gate sitzt in
`fetch()`, damit auch die Wiederholungen der Collectors zählen.

**Gemessen in GitHub Actions** (Diagnoselauf #74, 132 Quellen, das ist die
Umgebung, in der der Radar wirklich läuft):

| Worker | je Host | Wanduhr | Arbeit/Quelle | ok/leer/Fehler | 403 |
|---:|---:|---:|---:|---|---:|
| 8 | ohne | 62,5 s | 3,32 s | 124/5/3 | 2 |
| 64 | 2 (+0,5 s) | **39,7 s** | 7,79 s | 123/5/4 | 2 |

Hochgerechnet auf 1000 Quellen: **7,9 min → 5,0 min**. Beides unter dem
Timeout, die Drosselung spart trotzdem ein Drittel.

**Korrektur an der eigenen ersten Messung.** In der Sandbox ergab derselbe
Vergleich 185,6 s → 22,2 s, also Faktor 8,4. Diese Zahl war aufgeblasen: sie
hing fast vollständig an *einer* Quelle (Telecoms Tech News, 165 s von 186 s
in drei Leseversuche). Die belastbare Zahl ist die aus Actions.

**Der eigentliche Deckel ist die langsamste Einzelquelle.** Im Volllauf #75
brauchte die Sammelphase 303,7 s — und **302,6 s davon waren eine einzige
tote Quelle**: KT hat `timeout_seconds: 30` eingetragen (sein koreanischer
Endpunkt ist langsam zu erreichen), und die Retry-Leiter multipliziert das mit
zwei User-Agents und drei Versuchen. Gegen den langsamsten Einzelfall hilft
keine Parallelität. Jede Quelle hat deshalb jetzt eine harte Frist von 75 s;
das Timeout des einzelnen Versuchs bleibt unberührt — eine langsame, aber
lebende Quelle darf ihre 30 s haben, sie bekommt sie nur nicht sechsmal.

**Und ein Nebenbefund, der wichtiger ist als der Zeitgewinn:** bei 64 Workern
fiel Viettel mit `Page.goto: Timeout 16000ms exceeded` aus, das bei 8 Workern
durchlief. Nicht die Seite war langsamer — der Runner war voll. Ein
`newsroom_js`-Abruf ist eben *keine* reine Wartezeit, er startet einen
Chromium, und der Runner hat zwei Kerne. Headless-Renderings laufen deshalb
jetzt durch ein eigenes Limit von 4. Bei 1000 Quellen wäre das sonst der
nächste stille Ausfall gewesen.

### 3.2 Redaktion — zweistufig

`editor.synthesize_zweistufig()`:

1. **Bereichsredakteure**, einer je Region und je Themenfeld, parallel. Jeder
   sieht nur seinen Bereich, schreibt dessen fertigen Abschnitt plus eine
   Kurzfassung von 3–5 Sätzen. Die Abschnittslänge skaliert mit der Zahl der
   Meldungen, damit Europa nicht so viel Platz bekommt wie Ozeanien.
2. **Chefredaktion**: bekommt nur die Kurzfassungen und die fünf stärksten
   Meldungen je Bereich. Im Test wächst ihre Eingabe bei **zwölffacher**
   Meldungsmenge nicht einmal aufs Doppelte — sie hängt an der Zahl der
   Bereiche, genau wie der Auftrag es verlangt.

Die Bereichsabschnitte werden montiert, nicht neu geschrieben: sie stehen
zwischen „Die wichtigsten Signale" und „Muster der Woche", die Themenfelder
gemeinsam unter der bestehenden H2 „Technologie, Geräte & Regulierung" (je
Thema ein H3). `validate_editorial_briefing` prüft das montierte Ganze.

Zwei Ausfälle sind abgedeckt und getestet: ein einzelner Bereich scheitert →
Regelabschnitt mit allen Meldungen und Quellenlinks statt eines Lochs (die
Meldungen sind bewertet, der Seen-Store merkt sie als erledigt — sie kämen nie
wieder). Die Chefredaktion liefert eine unbrauchbare Gliederung → ein
Korrekturversuch, danach der Notfall-Digest.

Umschaltung über `editor_modus` (auto|einstufig|zweistufig) mit Schwelle bei
120 bewerteten Meldungen. Bewusst eine Schwelle: bei 36 bewerteten Meldungen
wie in Lauf #67 schreibt ein einzelner Aufruf den zusammenhängenderen Bericht
und kostet ein Zwölftel.

**Abgenommen im Lauf #75** (05.08.2026, `editor_modus` erzwungen
zweistufig): 167 Quellen, 426 neue Meldungen, 92 bewertet, **14
Bereichsredakteure plus Chefredaktion**, 24,8 min. Der montierte Bericht hielt
die Pflichtgliederung ein — Chefteil, dann sechs Regionsabschnitte, dann die
gemeinsame H2 „Technologie, Geräte & Regulierung" mit fünf H3-Themenfeldern,
zuletzt „Muster der Woche"; 2 877 Wörter. Die drei Bereiche ohne bewertete
Meldungen (Europa, Geräte, Netzausrüster) bekamen korrekt keinen Abschnitt.

### 3.3 Seen-Store — Faktor 17,6

Nur noch der Hash je Zeile: **17 statt ~300 Byte**, 588 KB → 33 KB.
Hochgerechnet auf 233 000 Einträge im Jahr **3,9 statt 68 MB** — auch nach
zehn Jahren unter GitHubs 100-MB-Limit.

Bewusst so und nicht über eine Altersgrenze, obwohl der Auftrag die als Option
nennt: undatierte Meldungen fallen nie aus dem Frischefenster (sie haben kein
Alter), eine Altersgrenze würde sie nach Ablauf ein zweites Mal in den Bericht
lassen. Die Kerngarantie bleibt damit unangetastet.

Das alte Format wird weiter gelesen. Die Migration prüft selbst nach und
bricht ab, wenn auch nur ein Hash fehlt — 1 968 vorher, 1 968 nachher,
Zeichen für Zeichen dieselbe Menge.

### 3.4 Kosten — kein Problem

`scripts/kostenrechnung.py`, gerechnet aus dem Laufprotokoll:

| Quellen | neu | bewertet | Redaktion | LLM-Aufrufe | je Lauf | je Monat | Stoßzeit |
|---:|---:|---:|---|---|---:|---:|---:|
| 130 | 124 | 36 | einstufig | 9 + 1 | 0,012 $ | 0,10 $ | 0,20 $ |
| 1000 | 954 | 277 | einstufig | 64 + 1 | 0,064 $ | 0,55 $ | 1,11 $ |
| 1000 | 954 | 277 | zweistufig | 64 + 17 | 0,084 $ | 0,73 $ | **1,45 $** |

Der Cron läuft um 08:30 UTC = 16:30 Peking, also mitten in DeepSeeks zweiter
Stoßzeit mit angekündigten Doppelpreisen — deshalb die letzte Spalte. Selbst
dort bleibt der Monat unter 1,50 $. **Der Engpass ist die Laufzeit, nicht das
Geld.**

---

## 4. Register und Quarantäne

Was ein Mensch bei der Abnahme weiß, steht in der YAML (`herkunft`,
`abgenommen`). Was der Betrieb misst, steht in
`data/state/quellen_register.json`: seit wann bekannt, wie viele Läufe,
Erfolge, letzter Erfolg, Länge der Fehlserie.

Quarantäne nach 6 Läufen ohne eine einzige Meldung — bei zwei Läufen die
Woche drei Wochen. Kein Löschen: die Quelle bleibt in der Konfiguration, steht
im Protokoll und bekommt alle 10 Läufe einen Bewährungsabruf; **ein einziger
Erfolg hebt die Quarantäne auf**. Ohne diesen Rückweg wäre die Quarantäne eine
Falle — Telecompetitor antwortet mal mit 403 und mal mit 200.

„status ok mit 0 Meldungen" zählt als Ausfall. Eine Quelle, die 200 antwortet
und nichts liefert, ist genauso tot wie eine mit 404.

---

## 5. Die Quellenwelle — und warum sie klein blieb

### Zahlen

| | Ziele | gefunden | Check bestanden | eingetragen |
|---|---:|---:|---:|---:|
| Zweitkanäle bestehender Firmen | 112 | 142 | 12 | **1** |
| Neue Firmen (`config/kandidaten_firmen.yaml`) | 338 | 171 | 62 | **28** |

**138 → 167 crawlbare Quellen.** Nach dem Eintragen zentral nachgeprüft:
167 Quellen, 149 ok / 4 leer / 14 Fehler, 2 723 Meldungen (vorher 2 101).

### Was die Welle über den Ausbau gelernt hat

**Der Zweitkanal-Brunnen ist leer.** Von 142 mechanisch gefundenen Kandidaten
bei bereits beobachteten Firmen blieb genau **einer** — der dritte Kanal von
O2 Telefónica Deutschland mit den regionalen Netzausbau-Meldungen, die in den
beiden Konzern-Feeds nicht vorkommen. Alles andere waren URL-Varianten
bestehender Quellen (`newsroom.arm.com/feed` neben `.../rss`), andere
Sprachausgaben derselben Meldungen (SK Telecom koreanisch neben englisch) oder
Marketing-Feeds ohne Nachrichtenwert. Der Auftrag nannte Zweitkanäle „den
billigsten Zugewinn" — das galt für Session 4, die ihn abgeschöpft hat.

**Der Ertrag liegt bei neuen Firmen, und dort bei der Fachpresse.** 19 der 29
neuen Quellen sind regionale und nicht-englische Fachpresse: teltarif und
Telecom Handel (deutsch), Univers Freebox (französisch), Xataka Móvil und
ADSLZone (spanisch), Corriere Comunicazioni (italienisch), TeleSíntese und
TeleSemana (portugiesisch/spanisch, Lateinamerika), dazu regionale englische
Titel für Indien, Asien, Afrika und Südafrika sowie TelecomTV, Telecoms.com,
Capacity Media, Broadband Communities, PolicyTracker und Ookla. Der Auftrag
nannte das die auffälligste Lücke im Bestand — sie ist geschlossen.

**Zwei neue Themenfelder, klein gestartet:** „Türme, Glasfaser &
Rechenzentren" (1 Quelle aus 18 gesuchten Firmen) und „MVNO, eSIM &
Plattformen" (4). Beide sind Versuche, keine Setzungen. Ob sie tragen,
entscheidet die Trefferquote nach den ersten Läufen.

### Was verworfen wurde, obwohl es den Check bestand

Von 62 bestandenen Kandidaten sind **34 nicht eingetragen** — der Check prüft
Form, nicht Wert. Die Begründungen stehen als Kommentar in den YAMLs, damit
sie niemand erneut vorschlägt:

- **Termin- und Formularfeeds**: `investors.att.com/rss/events-and-presentations`
  liefert sauber datierte Meldungen wie „Perpetual Preferred Stock, Series C
  Dividend Payment Date". Dieselbe Klasse wie die gesperrten SEC-EDGAR-Feeds.
- **Kampagnen-SKUs statt Überschriften**: TIM Brasil („DEFAULT_AGOSTO
  CarrosselStore - Migração - Pré para Controle_43,5GB_47,99 - CAPTIVE"),
  Turkcell („Defacto Kampanyası").
- **Falsche Behörde**: `gov.br/rss.xml` ist das ganze brasilianische
  Regierungsportal, nicht Anatel — erste Meldung im Abruf war ein
  Studienplatz-Auswahlverfahren.
- **Entwickler- und Konzern-Firehoses**: AWS „What's new" (40 Cloud-Meldungen
  je Abruf), Twilio-Entwicklerblog, Thales (Rüstung bis Chipkarte),
  `blog.google/rss` (alle Google-Themen, inklusive Büroeröffnungen).
- **Allgemeine IT- und Wirtschaftspresse**: golem.de, zdnet.fr,
  expansion.com — technisch einwandfrei, aber zu wenig Telekommunikation.
- **Doppelte Sprachausgaben**: SK Telecom koreanisch, True Corporation thai —
  dieselben Meldungen, die der Bericht dann zweimal führen würde.

### Warum nicht 1000

Um es mit Zahlen zu sagen statt mit Zeitmangel:

Aus 450 mechanischen Suchaufträgen (112 bestehende Firmen + 338 neue) sind
**313 Kandidaten** entstanden, davon **74 abnahmefähig** und **29 wertvoll**.
Das ist eine Ausbeute von **6,4 % je Suchauftrag**. Auf 1000 Quellen
hochgerechnet hieße das rund **13 000 weitere Suchaufträge** — also 13 000
recherchierte Firmen mit Domain.

Das ist machbar, aber es ist eine andere Aufgabe als diese Session: es braucht
eine Firmenliste dieser Größenordnung (die GSMA führt über 750 MNOs, dazu
Regulierer, Verbände, Zulieferer und regionale Fachpresse je Land), und die
entsteht nicht mechanisch aus der bestehenden Konfiguration. Die drei
häufigsten Ablehnungsgründe zeigen außerdem, wo die Grenze wirklich liegt:
**K4 keine frische Meldung (104), K5 keine echten Überschriften (70), K3 zu
wenig datiert (69)** — es fehlt nicht an Domains, es fehlt an Domains mit
einem maschinenlesbaren, datierten Nachrichtenkanal.

**Die Maschinerie dafür steht und ist auf Massenbetrieb ausgelegt:**
`finde_quellen.py --firmen` mit Wiederaufnahme, `pruefe_quellenvorschlag.py`
mit Ergebnis-Cache und Dubletten-Index. Der nächste Ausbau kostet
Firmenlisten, keine Werkzeuge.

---

## 6. Was der Ausbau an Fehlern aufgedeckt hat

Drei Dinge, die ohne diese Welle nicht aufgefallen wären:

1. **Der Dublettencheck lief nur für Kandidaten mit Betreiber.** Themenquellen
   tragen keinen — für sie lief er gar nicht. Im ersten Durchgang waren
   deshalb **15 von 34** „bestandenen" Kandidaten URL-Varianten bereits
   konfigurierter Quellen. Der Index ist jetzt nach Domain geschlüsselt.
2. **Der Überlappungswert rechnete gegen die Kandidatenmenge.** Eine Quelle,
   die eine bestehende vollständig *enthält*, sah dadurch neu aus
   (`libertyglobal.com/wp-json` mit 25 Meldungen enthält alle 10 des
   konfigurierten Feeds → 40 %, unauffällig). Jetzt gegen die kleinere Menge:
   100 %, also Dublette. Der Effekt auf die Welle: 34 → 19 → 12 bestandene
   Kandidaten.
3. **`news_sources.yaml` erzwang `kind="trade_press"`** und schickte damit
   jede Fachpressequelle durch den RSS-Parser. Solange alle Fachpresse RSS
   war, fiel das nicht auf. Capacity Media ist die erste mit JSON-API und
   scheiterte mit „unparseable feed".

Dazu die Korrektur an der eigenen Sammelphasen-Messung (Abschnitt 3.1) und das
Renderlimit für Headless-Browser.

---

## 7. Was als nächstes zu tun ist

In dieser Reihenfolge:

1. **Die europäische Fachpresse landet im Bereich „Global", nicht in
   „Europa".** Lauf #75 hat Europa mit **null** bewerteten Meldungen
   abgeschlossen, während „Global" 62 bekam — von 92 insgesamt. Der Grund ist
   kein Fehler, sondern eine Regel, die mit dieser Welle an ihre Grenze kommt:
   `tag_news_regions` ordnet eine Fachpresse-Meldung nur dann einer Region zu,
   wenn ein Betreibername aus der Watchlist in der Überschrift steht. Bei 14
   internationalen Feeds ging das; bei teltarif, Univers Freebox, ADSLZone und
   Corriere Comunicazioni ist die Heimatregion aber schon durch die Quelle
   bekannt. Eine Fachpressequelle sollte eine Vorgabe-Region tragen dürfen —
   sonst wird der Regionsteil des Berichts leerer, je mehr regionale Quellen
   dazukommen. **Das ist der wichtigste offene Punkt.**
2. **Zwei bis drei normale Läufe abwarten**, dann die Trefferquote neu
   auswerten. Erst dann steht je Kanal (nicht nur je Anzeigename) fest, was
   die 29 neuen Quellen taugen — insbesondere die zwei neuen Themenfelder mit
   je einer bzw. vier Quellen.
3. **Die belegten Ballast-Quellen aussortieren** (Abschnitt 2), sobald die
   Trefferquote sie über weitere Läufe bestätigt. Iliad, stc, AIS und PLDT
   liefern zusammen 124 neue Meldungen je Auswertungszeitraum, von denen keine
   je bewertet wurde.
4. **Die nächste Firmenliste bauen.** Der Engpass ist die Liste, nicht das
   Werkzeug. Lohnend nach der Ausbeute dieser Welle: regionale Fachpresse je
   Land (höchste Trefferquote, bester Fundanteil) und nationale
   Regulierungsbehörden (klar abgegrenzt, sauber datiert).

---

## 8. Zahlen dieser Session

- 138 → **167** crawlbare Quellen (+21 %)
- 2 101 → **2 723** gesammelte Meldungen je Lauf (+30 %)
- 6 → **8** Themenfelder, 14 → **33** Fachpresse-Feeds
- Seen-Store: 588 KB → **33 KB** (Faktor 17,6), 68 → **3,9 MB/Jahr**
- Sammelphase in Actions: 62,5 s → **39,7 s** bei 132 Quellen
- Kosten bei 1000 Quellen: **1,45 $/Monat** im teuersten Fall
- 321 → **410** Tests
- Volllauf #75 mit zweistufiger Redaktion: 426 neue Meldungen, 92 bewertet,
  14 Bereiche, 24,8 min (Job-Timeout 50 min)
