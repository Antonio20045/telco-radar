# Auftrag für die nächste Session: Skalierung auf 1000 Quellen

> Dieser Text IST der Auftrag. Lies zuerst `CLAUDE.md` (Architektur, Zugänge,
> Fallstricke), dann `AUFTRAG_QUELLEN_AUSBAU.md` (der vorherige Ausbau — seine
> Abnahmekriterien gelten unverändert weiter), dann diesen Auftrag.
>
> Er ist streng formuliert, weil hier zum ersten Mal etwas kaputtgehen kann,
> das bisher gehalten hat: die Pipeline läuft heute in 22 von 50 zulässigen
> Minuten. Ein naives Verzehnfachen der Quellen sprengt sie.

---

## 1. Ziel

**1000 abgenommene Quellen.** Heute sind es 130. Das ist ein Faktor 7,7.

Wichtig: Die Zahl ist das Ziel, nicht der Maßstab. **1000 unbrauchbare Quellen
sind schlechter als 130 gute**, weil jede tote Quelle Laufzeit kostet, jede
rauschende Quelle den Bericht verwässert und jede undatierte Quelle unsichtbar
bleibt. Die Abnahmekriterien aus `AUFTRAG_QUELLEN_AUSBAU.md` Abschnitt 4 plus
die beiden seither ergänzten (5b unterscheidbare Titel, 1b zweiter Abruf)
gelten für jede einzelne der 1000 Quellen.

## 2. Ist-Zustand — gemessen, nicht geschätzt (Lauf #67, 04.08.2026)

| | |
|---|---|
| Quellen | 130 (123 ok / 4 leer / 3 Fehler) |
| davon Betreiberquellen | 91 bei 85 Betreibern in 6 Regionen |
| davon Fachpresse | 14 |
| davon Themenquellen | 27 in 6 Themenfeldern (`config/tech_sources.yaml`) |
| Gesammelte Meldungen | 2 161 |
| Neue Meldungen | 124 → davon 36 bewertet (29 %) |
| **Laufzeit gesamt** | **1 314,8 s = 21,9 min** (Job-Timeout: 50 min) |
| davon Sammeln | 324,9 s bei `collect_max_workers: 8` |
| davon Bewerten & Schreiben | 447,2 s bei `llm_max_workers: 3` × `analyst_batch_workers: 4` |
| Anbieter | DeepSeek (`deepseek-v4-flash` Analysten, `deepseek-v4-pro` Redaktion) |
| `seen.jsonl` | 1 968 Einträge, 592 KB (~300 Byte je Eintrag) |

## 3. Die vier echten Engpässe — mit Rechnung

Diese vier Punkte sind der eigentliche Auftrag. Quellen zu finden ist die
leichte Hälfte.

### 3.1 Sammelphase — linear, aber falsch parametriert

324,9 s für 130 Quellen bei 8 Workern sind **20 Sekunden·Worker je Quelle**
(2,5 s Wanduhr je Quelle bei 8 Workern).

- 1000 Quellen bei 8 Workern → **~2 500 s = 41,7 min**. Allein das sprengt das
  50-Minuten-Timeout, bevor eine einzige Meldung bewertet ist.
- bei 48 Workern → ~417 s = 6,9 min
- bei 64 Workern → ~313 s = 5,2 min

Die Phase ist reine Wartezeit auf fremde Server, skaliert also fast linear.
**Aber:** viele gleichzeitige Verbindungen zum selben Host provozieren 429/403.
Bei 1000 Quellen liegen zwangsläufig mehrere Quellen auf derselben Domain
(`blog.google` hat heute schon drei). Gebraucht wird deshalb kein größerer
Worker-Pool allein, sondern **Parallelität mit Host-Drosselung**: global viele
Verbindungen, pro Host höchstens ein bis zwei gleichzeitig, plus ein kurzer
Mindestabstand zwischen zwei Abrufen derselben Domain.

### 3.2 Redaktion — der harte Bruch

**Das ist der Punkt, an dem die heutige Architektur endet.**

Heute bekommt der Editor in EINEM Aufruf alle bewerteten Meldungen
(`editor_max_highlights: 0`). Hochgerechnet:

- 1000 Quellen → ~16 600 gesammelte Meldungen je Lauf (16,6 je Quelle, gemessen)
- bei realistisch 12–15 % neu → **~2 250 neue Meldungen**
- bei der gemessenen Bewertungsquote von 29 % → **~650 bewertete Meldungen**
- bei ~750 Zeichen je bewerteter Meldung → **~477 KB ≈ 122 k Token Eingabe**

Das passt formal in das 1M-Kontextfenster von `deepseek-v4-pro` — und ist
trotzdem der falsche Weg. Ein Modell, das 650 Meldungen zu einem
1 900-Wörter-Bericht verdichten soll, produziert Brei; ein einziger
fehlgeschlagener Aufruf kostet den ganzen Wochenbericht; und die Latenz eines
120k-Token-Calls ist nach oben offen.

**Zu bauen ist eine zweistufige Redaktion:**

1. **Bereichsredakteure** (ein Agent je Region und je Themenfeld, also heute 12,
   später mehr): bekommen die bewerteten Meldungen IHRES Bereichs und
   schreiben daraus einen fertigen Bereichsabschnitt plus eine
   Kurzfassung von 3–5 Sätzen. Laufen parallel.
2. **Chefredaktion**: bekommt NUR die Kurzfassungen und die stärksten
   Meldungen je Bereich (nicht die Rohliste) und schreibt daraus „Auf einen
   Blick", „Das Wichtigste", „Die wichtigsten Signale" und „Muster der Woche".
   Die Bereichsabschnitte werden unter den Chefteil montiert, nicht neu
   geschrieben.

Damit hängt die Eingabelänge der Chefredaktion an der Zahl der BEREICHE, nicht
an der Zahl der Meldungen — und der Bericht bleibt lesbar, was die
ausdrückliche Anforderung von Antonios Kollegin ist.

Achtung beim Umbau: `validate_editorial_briefing()` prüft Pflicht-Überschriften
und muss **gemeinsam mit dem Prompt** angefasst werden. Der Themenabschnitt
hängt bereits an einem bedingten Schalter (`THEMEN_UEBERSCHRIFT`) — dieses
Muster fortführen, nicht ersetzen.

### 3.3 Seen-Store — läuft in eine Wand

`data/state/seen.jsonl` ist append-only, git-versioniert und wird bei jedem
Lauf **komplett in den Speicher geladen**. Je Eintrag stehen dort id, volle
URL, Titel, Quelle und Zeitstempel — ~300 Byte.

- heute: 1 968 Einträge, 592 KB
- bei 1000 Quellen: ~2 250 neue Einträge je Lauf × 2 Läufe/Woche
  = ~4 500/Woche = **~233 000/Jahr ≈ 67 MB/Jahr**
- GitHubs hartes Limit je Datei: **100 MB**. Dazu wächst das Repo bei jedem
  Lauf um den angehängten Block, weil git jede Version behält.

Das ist kein Komfortproblem, sondern ein Ablaufdatum. Zu lösen ist es, ohne die
Kerngarantie anzutasten (**was einmal berichtet wurde, kommt nie wieder**).
Denkbare Wege, begründet zu wählen:

- nur noch den Hash speichern statt URL/Titel/Quelle (~20 Byte statt 300)
- Einträge älter als N Monate verwerfen — vertretbar, weil das Frischefenster
  8 Tage beträgt und eine Meldung von vor einem Jahr ohnehin nie wieder
  eingesammelt wird
- kompaktes Format (SQLite oder sortierte Hash-Datei) statt JSONL
- Rotation in Jahresdateien

**Vorher gegenprüfen:** `SeenStore` wird auch von `dedupe.py`-Tests und vom
Stapelschutz benutzt. Und der Store ist die einzige Instanz, die verhindert,
dass der Bericht sich wiederholt — ein Fehler hier ist teurer als jede fehlende
Quelle.

### 3.4 Kosten und Anbieter-Limits

Heute ~14 Analysten-Aufrufe je Lauf. Bei 1000 Quellen:

- ~2 250 neue Meldungen / 15 je Stapel = **~150 Analysten-Aufrufe**
- plus 12+ Bereichsredakteure plus eine Chefredaktion
- bei 2 Läufen/Woche: ~300 Analysten-Aufrufe/Woche

`deepseek-v4-flash` kostet 0,14 $ ein / 0,28 $ aus je 1M Token (zu Pekinger
Stoßzeiten doppelt). **Rechne die Kosten je Lauf und je Monat aus und schreib
sie in die Zusammenfassung** — Antonio zahlt das privat, und das Projekt hat
den Anspruch, kostenlos bzw. sehr günstig zu bleiben.

Gleichzeitig ist die Parallelität nach oben nicht frei: 150 Stapel bei den
heutigen 12 gleichzeitigen Aufrufen sind ~13 Runden. **Miss das Rate-Limit von
DeepSeek, bevor du `llm_max_workers` × `analyst_batch_workers` hochdrehst** —
ein 429-Sturm macht den Lauf langsamer, nicht schneller. `llm.py` fängt 429/529
mit Backoff ab; gewonnen ist damit nichts.

**Das Job-Timeout darf steigen.** Es liegt bei 50 Minuten, GitHub erlaubt bis
zu 360. Das ist der billigste Hebel überhaupt — aber erst nachdem die Phasen
gemessen sind, nicht als Ersatz für Parallelität.

## 4. Woher 1000 Quellen kommen

**Die Mischung wird NICHT vorab festgelegt.** Kein Anteil, keine Quote, keine
Zielzahl je Kategorie. Wer vorher entscheidet, dass es „200 Betreiber und 80
Regulierer" sein sollen, hat die interessanteste Frage schon weggeworfen —
nämlich welche Art von Quelle für diesen Bericht tatsächlich etwas taugt.

Der Grund ist kein Prinzip, sondern eine Messung. In Lauf #67 lag die Ausbeute
je Quelle in allen drei Ebenen praktisch gleich:

| Ebene | Quellen | Meldungen | je Quelle |
|---|---|---|---|
| Betreiber (`operator`) | 91 | 1 448 | **15,9** |
| Themenfelder (`tech_watch`) | 25 | 466 | **18,6** |
| Fachpresse (`industry_news`) | 14 | 247 | **17,6** |

Es gibt also keinen Beleg dafür, dass Betreiberquellen wertvoller wären als
Fachpresse oder Themenquellen. Gut möglich, dass am Ende sehr viel Fachpresse
das Richtige ist — regional, mehrsprachig, dicht. Das entscheidet die Messung,
nicht der Auftrag.

### Was stattdessen zu tun ist: die Mischung messbar machen

Die Zahl „Meldungen je Quelle" sagt nur, wie viel eine Quelle liefert, nicht
wie viel davon taugt. Diese zweite Zahl gibt es heute nicht, und sie ist die
wichtigste Kennzahl des ganzen Ausbaus. **Bau sie zuerst.** Je Quelle über
mehrere Läufe hinweg:

- wie viele ihrer Meldungen ein Analyst überhaupt bewertet hat (Relevanz ≥ 2)
- wie viele davon Relevanz ≥ 3 bzw. ≥ 4 bekamen
- wie viele es in den Wochenbericht geschafft haben
- wie oft die Quelle leer war oder gescheitert ist

Die Daten dafür liegen schon vor: `data/reports/*.json` enthält je Highlight
`source` und `relevance`, das Laufprotokoll je Quelle `status` und `count`.
Es braucht also keinen neuen Sammelvorgang, nur eine Auswertung über das
Archiv — und danach eine Seite oder einen Report, der die Quellen nach
Trefferquote sortiert.

**Erst mit dieser Kennzahl wird der Ausbau steuerbar:** in Kategorien
investieren, die nachweislich liefern, und in Wellen nachsteuern statt vorab
zu quotieren.

### Suchinventar (Fundorte, ausdrücklich KEINE Quoten)

Eine Liste, wo man überhaupt suchen kann, damit keine Kategorie schlicht
vergessen wird. In welchem Verhältnis sie am Ende vertreten sind, ergibt die
Messung oben:

- Netzbetreiber weltweit (die GSMA führt >750 MNOs; heute beobachtet: 85)
- Zweit- und Drittkanäle bestehender Betreiber: Investor Relations,
  Technik-Blog, Landesgesellschaft, Produkt-Newsroom
- Fachpresse — international, **regional und anderssprachig**. Heute sind alle
  14 Feeds englischsprachig; das ist die auffälligste Lücke im Bestand.
- Nationale Regulierungsbehörden (heute 5)
- Netzausrüster und Zulieferer (heute 3)
- Geräte- und Chiphersteller (heute 9)
- Satellit / NTN (heute 1)
- Verbände, Normung, Foren: ETSI, ITU, 3GPP, O-RAN Alliance, TM Forum,
  nationale Verbände
- Tower-, Glasfaser- und Rechenzentrumsbetreiber
- MVNO- und eSIM-Plattformen
- Marktforschung und Analysten, soweit frei zugänglich

Wenn sich unterwegs zeigt, dass eine dieser Kategorien nichts bringt: streichen
und in der Schlussliste begründen. Wenn sich zeigt, dass eine andere trägt:
ausbauen, auch weit über jedes Bauchgefühl hinaus.

### Der billigste Zugewinn — unabhängig von der Mischung

Zwei Verfahren, die mechanisch funktionieren und kein Modell brauchen:

1. **Zweitkanäle bestehender Betreiber.** Erst 10 von 85 Betreibern haben mehr
   als einen eigenen Kanal. Hier ist kein einziger neuer Betreiber zu
   recherchieren — die Firmen stehen schon in der Watchlist.
2. **Muster übertragen.** Liegt ein Betreiber auf einer IR-Plattform, liegen
   Dutzende andere auf derselben. Bekannte Muster im Bestand:
   `q4web.com` bzw. `investor.<firma>.com/rss/pressrelease.aspx?T=1` (T-Mobile),
   `<ir-host>/rss/news-releases.xml` (Charter, Broadcom),
   `news.cision.com/<firma>` mit `item_selector: .card-item` (Telia, Ericsson),
   `irasia.com/.../rss.cgi?id=<firma>&t=p` (China Mobile/Telecom/Unicom),
   `/wp-json/wp/v2/posts?per_page=25` (WOM), `?format=feed&type=rss` (Joomla).
   Ein Muster auf 50 Firmen anzuwenden kostet 50 Abrufe und null Token.

`scripts/finde_quellen.py` macht genau das (`rel=alternate` plus
Kandidatenpfade), ist aber auf einzelne Ziele ausgelegt — bau es auf
Massenbetrieb um.

## 5. Harte Abnahmekriterien

Es gelten **unverändert** die neun Kriterien aus `AUFTRAG_QUELLEN_AUSBAU.md`
Abschnitt 4, umgesetzt in `scripts/pruefe_quellenvorschlag.py`. Zusätzlich:

10. **Der Abnahme-Check muss bei 1000 Kandidaten praktikabel bleiben.** Heute
    prüft er sequenziell mit 6 Workern und ruft für die Inhaltsdublette
    zusätzlich alle bestehenden Quellen desselben Betreibers ab. Bau ihn auf
    Massenbetrieb um: Wiederaufnahme nach Abbruch, Ergebnis-Cache, und die
    Dublettenprüfung gegen einen einmal aufgebauten Index statt gegen
    Live-Abrufe.
11. **`--zweimal` ist bei geparsten Seiten Pflicht, nicht optional.** Der
    newswire.ca-Fall (23/23 datiert, beim nächsten Abruf 30/0) wiederholt sich
    bei 1000 Quellen garantiert mehrfach.
12. **Jede Quelle trägt Herkunft und Datum.** Bei 130 Quellen reicht ein
    deutscher Kommentar je Eintrag. Bei 1000 nicht mehr: es braucht je Quelle
    maschinenlesbar, wann sie zuletzt erfolgreich geliefert hat und wann sie
    abgenommen wurde. Sonst weiß in sechs Monaten niemand mehr, welche der
    1000 Quellen eigentlich noch lebt.
13. **Automatische Quarantäne.** Eine Quelle, die in N aufeinanderfolgenden
    Läufen nichts oder nur Fehler liefert, wird automatisch stillgelegt und im
    Protokoll ausgewiesen. Ohne das verrottet die Konfiguration still.

## 6. Vorgehen

Frei in der Wahl, aber bindend:

- **Groß angelegter Workflow ist hier ausdrücklich erwünscht.** Das ist der
  Auftrag: viele Agents parallel für die Breitensuche, danach die
  mechanische Abnahme. Antonio hat das explizit so gewollt.
- **Erst Architektur, dann Quellen.** Wer 1000 Quellen einträgt, bevor
  Redaktion, Seen-Store und Sammel-Parallelität stehen, hat einen Radar
  gebaut, der ins Timeout läuft und einen unlesbaren Bericht schreibt. Die
  Reihenfolge ist: 3.1 → 3.3 → 3.2 → dann Quellen, in Wellen von je ~200 mit
  einem echten Actions-Lauf nach jeder Welle.
- **Token-effizient, hybrid.** Billiges Modell für Breitensuche und
  Abruf-Tests, teures Modell nur für Bewertung, Zweifelsfälle und Synthese.
- **Verifikation ist eine eigene Stufe** und wird nicht von demselben Agent
  gemacht, der die Quelle vorgeschlagen hat. Vorschlagender Agent = Anwalt,
  Prüfskript = Skeptiker.
- **Die Gesamtliste am Ende selbst noch einmal zentral durchlaufen lassen.**
  In Session 4 bestand von zwölf Vorschlägen einer Agent-Runde genau einer die
  zentrale Nachprüfung. Agent-Meldungen über bestandene Prüfungen sind kein
  Beleg.

## 7. Fallstricke

Alle Punkte aus `CLAUDE.md` Abschnitt 6 gelten weiter. Zusätzlich für diese
Größenordnung:

- **Der Check prüft Form, nicht Wert.** Bei 1000 Quellen wird niemand jede von
  Hand bewerten können — dafür ist die Trefferquote aus Abschnitt 4 da. Eine
  Quelle, deren Meldungen über mehrere Läufe nie im Bericht landen, ist
  Ballast, egal wie sauber sie den Abnahme-Check besteht.
- **Sprache.** Ab ~300 Quellen ist der englischsprachige Vorrat erschöpft. Der
  Analyst versteht andere Sprachen, aber der Datums-Parser in
  `collect/newsroom.py` kennt nur die Monatsnamen, die dort eingetragen sind.
  Vor der ersten nicht-lateinischen Quelle prüfen, ob `published` gesetzt wird.
- **Der erste Lauf nach jeder Welle ist groß.** Alle neuen Quellen liefern ihr
  volles Frischefenster auf einmal. Bei einer Welle von 200 Quellen sind das
  mehrere tausend Meldungen in einem Lauf. Plan das ein und schau, ob der
  Stapelschutz greift.
- **`site/` wird von der Pipeline erzeugt und mitcommittet.** Config- oder
  Template-Änderungen werden erst mit dem nächsten Lauf sichtbar; sonst
  `render_site()` einmal von Hand laufen lassen (ohne neu zu sammeln, sonst
  überschreibst du den letzten guten Bericht).
- **Render deployt automatisch bei Push auf `main`.** Der Deploy-Hook im
  Workflow ist zusätzlich, nicht notwendig.

## 8. Abzuliefern

1. Sammel-Parallelität mit Host-Drosselung, gemessen (Sekunden je Quelle vorher/nachher).
2. Zweistufige Redaktion (Bereichsredakteure + Chefredaktion), mit Tests, und
   `validate_editorial_briefing` mit angepasst.
3. Seen-Store, der 200 000 Einträge im Jahr verträgt, ohne die Kerngarantie
   aufzugeben — mit Migration des Bestands.
4. Quellenregister mit Herkunft, Abnahmedatum, letztem Erfolg; automatische
   Quarantäne toter Quellen.
5. Die Trefferquote je Quelle (Abschnitt 4), ausgewertet über das
   vorhandene Berichtsarchiv — vor der ersten neuen Quelle.
6. Der Weg zu 1000 Quellen in Wellen, jede Welle mit echtem Actions-Lauf und
   ausgewertet: Quellen ok/leer/fehlerhaft, gesammelte und neue Meldungen,
   Laufzeit je Phase, **vor/nach im Vergleich**. Nach jeder Welle die
   Trefferquote neu auswerten und die nächste Welle danach ausrichten.
7. Kostenrechnung je Lauf und je Monat.
8. `pytest -q` grün, `python scripts/build_quellen_doc.py --validate` neu erzeugt.
9. `CLAUDE.md` fortgeschrieben.
10. Eine ehrliche Schlussliste: wie viele Quellen es wirklich geworden sind,
   **wie die Mischung am Ende aussieht und warum sie so aussieht** (belegt mit
   der Trefferquote, nicht mit einer Vorabannahme), welche verworfen wurden und
   warum, wo blinde Flecken bleiben. **Lieber 600
   belegte als 1000 behauptete.** Wenn 1000 nicht sinnvoll erreichbar sind,
   sag das mit Zahlen — Antonio will einen funktionierenden Radar, keine
   Zahl im Changelog.

## 9. Ausdrücklich nicht

- Keine Kappung von Meldungen (`max_items_per_region`, `editor_max_highlights`
  bleiben bei 0). Wer nicht bewertet wird, ist über den Seen-Store dauerhaft
  verloren.
- Keine Keyword-Nachrichtensuche als Quelle.
- **Keine vorab festgelegte Mischung.** Nicht entscheiden, wie viel Prozent
  Betreiber, Fachpresse oder Regulierer es sein sollen. Gemessen an Lauf #67
  liefern alle drei Ebenen praktisch gleich viel je Quelle; welche davon
  wertvoll sind, weiss heute niemand. Das entscheidet die Trefferquote.
- Keine Quelle eintragen, die nicht durch den Abnahme-Check gelaufen ist.
- `data/state/` und `data/reports/` nicht aus lokalen Läufen committen.
- Kein `newsroom_js` als Ersatz für „ich habe den statischen Endpunkt nicht
  gefunden" — es ist lokal nicht prüfbar und damit nicht abnehmbar.
- Nicht auf `main` pushen ohne Freigabe — Entwicklung auf dem zugewiesenen
  Branch.
