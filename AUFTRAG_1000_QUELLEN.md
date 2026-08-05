# Auftrag für die nächste Session: jetzt wirklich 1000 Quellen

> Lies zuerst `CLAUDE.md` (Architektur, Zugänge, Fallstricke), dann
> `outputs/skalierung-2026-08-04.md` (was Session 5 gemessen hat), dann diesen
> Auftrag. `AUFTRAG_SKALIERUNG_1000.md` und `AUFTRAG_QUELLEN_AUSBAU.md` sind
> die Vorgänger — ihre Abnahmekriterien gelten unverändert weiter.
>
> Die Architektur ist fertig. Diese Session hat nur eine Aufgabe: **Quellen.**

---

## 1. Das Ziel, unmissverständlich

**1000 abgenommene, konfigurierte Quellen.** Heute sind es 228.

Nicht 300 mit einer guten Begründung, warum mehr nicht ging. Antonio hat
zweimal nachgefragt, ob wirklich alles ausgewertet wird — er will Breite, und
er will sie belegt. Wenn 1000 am Ende nicht erreichbar sind, muss das mit
Zahlen belegt sein und nicht mit Aufwand begründet.

**Die Rechnung, mit der du planen musst:** In Session 5 überlebten von 329
gefundenen Kandidaten 91 den Abnahme-Check **und** die Wertprüfung — 28 %. Die
naheliegenden Länder und Kategorien sind seither abgegrast, die Quote wird
also eher fallen. Für 772 weitere Quellen brauchst du realistisch **2 500 bis
3 500 geprüfte Kandidaten**. Das ist die eigentliche Arbeit dieser Session, und
sie ist mechanisierbar — der Apparat dafür steht.

## 2. Was schon steht (nicht neu bauen)

Alles gemessen an echten Actions-Läufen, nicht geschätzt:

| | Stand |
|---|---|
| Quellen | 228 (90 Betreiber / 70 Fachpresse / 49 Themenquellen in 8 Feldern) |
| Sammelphase | 223 Quellen in **117 s**, host-gedrosselt, Budget 90 s je Quelle |
| Analyse | 47 von 47 Stapeln erfolgreich, **0 ungelesen**, ein flacher Stapel-Pool |
| Redaktion | zweistufig; Chef-Prompt hängt an der Zahl der Bereiche, nicht der Meldungen |
| Seen-Store | 22 Byte je Eintrag, ~5 MB/Jahr bei 1000 Quellen |
| Kappungen | **keine** — `max_items_per_source: 250`, und jenseits davon liegt nachweislich nichts Frisches |
| Kosten | 0,17 $ je Lauf bei 1000 Quellen, 1,43 $ im Monat |
| Laufzeit | 28,4 min bei 223 Quellen und 6 339 gesammelten Meldungen (Timeout: 120 min) |

**Werkzeuge, die es schon gibt** — benutze sie, statt neue zu bauen:

```bash
python scripts/trefferquote.py --ab <datum>           # die Steuergröße
python scripts/finde_quellen.py --aus-watchlist --muster --out k.yaml
python scripts/pruefe_quellenvorschlag.py k.yaml --json e.json   # Cache, Resume, Index
python scripts/uebernehme_quellen.py e.json --herkunft "Welle 3" --probe
python scripts/mess_sammelphase.py --worker 48
python scripts/kostenrechnung.py --quellen 1000 --stosszeit
```

## 3. Der erste Schritt: neu messen, dann investieren

**Bevor du eine einzige Quelle suchst**, wertest du die Trefferquote neu aus.
Seit Lauf #68 ist sie über `source_url` exakt statt über den Quellennamen
geschätzt, und inzwischen liegen mehrere reguläre Läufe vor:

```bash
python scripts/trefferquote.py --ab 2026-08-05 --out outputs/trefferquote-<datum>.md
```

Stand am Ende von Session 5 (fünf Läufe desselben Tages, also ein erster
Befund und keine Saison):

| Ebene | Quellen | bewertet/Lauf | im Bericht/Lauf |
|---|---:|---:|---:|
| Betreiber | 140 | 0,08 | 0,06 |
| Themenfelder | 49 | 0,16 | 0,12 |
| Fachpresse | 70 | **1,99** | **0,53** |

Die Spitzenplätze belegten ausnahmslos die neu aufgenommenen Fachpressefeeds
(Golem Telekommunikation 5,0 Meldungen je Lauf im Bericht, Ariase 4,0,
MondoMobileWeb 4,0). **Wenn sich das bestätigt, investierst du entsprechend.
Wenn nicht, richtest du dich nach der neuen Messung** — nicht nach diesem
Absatz und nicht nach einem Bauchgefühl.

Nutze die Auswertung auch andersherum: die Liste der **Ballast-Kandidaten** am
Ende des Berichts zeigt Quellen, die über mehrere Läufe nichts beigetragen
haben. Bei 1000 Quellen ist Aufräumen genauso wichtig wie Zubauen.

## 4. Wo 772 weitere Quellen herkommen

Keine Quoten je Kategorie — die Mischung entscheidet die Messung aus
Abschnitt 3. Dies ist eine Landkarte, damit nichts vergessen wird, mit dem
Vermerk, was Session 5 bereits abgegrast hat.

**Ergiebig und noch lange nicht ausgeschöpft:**

- **Regionale und anderssprachige Fachpresse.** 70 Feeds aus 20 Ländern sind
  drin; es fehlen ~150 Länder. Besonders dünn: Zentralasien, Kaukasus,
  Balkan, Karibik, Zentralamerika, Westafrika ohne Nigeria/Ghana, Ozeanien
  ohne AU/NZ. Auch innerhalb starker Märkte gibt es je Land drei bis zehn
  Fachmedien, von denen erst eines bis zwei drin sind.
- **Rubrikenfeeds statt Gesamtfeeds.** Golem liefert als Ressortfeed
  Telekommunikation die beste Quote im ganzen Bestand — der Gesamtfeed wäre
  Rauschen gewesen. Prüfe bei jedem großen Medium, ob es einen Telko-Ressort-,
  Tag- oder Kategoriefeed gibt (`/tag/telekom/feed`, `?cat=`, `/rss/<ressort>`).
- **Zweit- und Drittkanäle der 90 Betreiber.** Erst 18 haben mehr als einen
  Kanal. Die Musterübertragung (`--muster`) hat 4 796 URLs probiert und 101
  Kandidaten gefunden; die produktiven Muster waren
  `<ir-host>/rss/news-releases.xml`, `/rss/pressrelease.aspx?T=1` und
  `/wp-json/wp/v2/posts`. **Ergänze die Musterliste** in `finde_quellen.py`
  um weitere, die du im Bestand findest, und lass sie erneut laufen.
- **Landesgesellschaften großer Konzerne.** Vodafone, Orange, Telefónica,
  Telekom, MTN, Airtel, América Móvil, Telenor, Veon, Axiata, e& haben je
  10–25 Ländergesellschaften mit eigenen Newsrooms. Das allein sind mehrere
  hundert Kandidaten.
- **Nationale Regulierungsbehörden.** 16 sind drin, es gibt ~190. Session 5
  hat viele als „kein Feed" abgeschrieben — prüfe die Liste in der Rückmeldung
  des Regulierungs-Agenten (`outputs/`), einige waren nur unter dem
  Projekt-User-Agent gesperrt und wären über `pruefe_quellenvorschlag.py`
  vielleicht doch erreichbar.
- **Neue Betreiber.** Die GSMA führt >750 MNOs, beobachtet werden 90.

**Abgegrast, hier lohnt wenig:** KI-Anbieter, große Chip- und Gerätehersteller,
die bekannten Netzausrüster. Was dort fehlt, fehlt aus einem Grund (JS-Seiten
ohne statischen Endpunkt).

## 5. Der Weg — in Wellen, und die Wellen müssen klein bleiben

**Das ist die wichtigste Planungsvorgabe dieses Auftrags.**

Der erste Lauf nach einer Welle ist der teuerste: alle neuen Quellen liefern
ihr volles Frischefenster auf einmal. Gemessen an Welle 1+2 (96 neue Quellen):
984 neue Meldungen, 72 Analysten-Stapel. Hochgerechnet auf eine Welle von 300
neuen Quellen wären das ~3 000 neue Meldungen und ~200 Stapel — bei 12
gleichzeitigen Aufrufen rund 70 Minuten allein für die Analyse. Das Timeout
liegt bei 120 Minuten.

**Also: Wellen von höchstens ~150 neuen Quellen, danach ein echter
Actions-Lauf, erst dann die nächste.** Fünf bis sechs Wellen bis 1000. Wenn
eine Welle den Lauf ins Timeout treibt, ist die Antwort nicht „kappen",
sondern die Welle in zwei Teile zu zerlegen — die zurückgehaltenen Meldungen
gehen nicht verloren, der nächste Lauf legt sie erneut vor (dreimal belegt).

Je Welle:

1. `finde_quellen.py --aus-watchlist --muster` (mechanisch, null Token)
2. Agent-Breitensuche je Kategorie, Ausgabe im Kandidatenformat. Session 5 hat
   sechs Agents parallel laufen lassen, das hat gut funktioniert — die
   Rückmeldungen mit den „kein Feed gefunden"-Listen sind wertvoll, hebe sie
   in `outputs/` auf, damit die nächste Runde nicht dieselben Sackgassen läuft.
3. **Die Gesamtliste** durch `pruefe_quellenvorschlag.py` — zentral, nicht je
   Agent. Der Cache macht Wiederholungen billig.
4. **Wertprüfung von Hand.** In Session 5 fielen dabei 84 von 175 formal
   bestandenen Quellen. Das ist die halbe Arbeit und nicht delegierbar.
5. `uebernehme_quellen.py`, erst mit `--probe`
6. Echter Actions-Lauf, auswerten, Trefferquote neu

## 6. Harte Regeln

- **Keine Quelle ohne PASS in `pruefe_quellenvorschlag.py`.** Ein Modell, das
  „ich habe es geprüft" sagt, zählt nicht.
- **Der Check prüft Form, nicht Wert.** Jede bestandene Quelle wird von Hand
  angesehen. Ablehnungsgründe aus Session 5, die sich wiederholen werden:
  Consumer-Gadget-Blogs, Enterprise-IT- und CIO-Presse, allgemeine
  Tech-Portale, Geschwisterseiten mit identischem Inhalt, IR-Feeds mit
  ausschließlich Quartalszahlen, Terminkalender, Newsletter-Archive.
- **KEINE Kappungen, nirgends.** `max_items_per_region: 0`,
  `editor_max_highlights: 0`, `http.max_items_per_source: 250`. Antonio hat
  das ausdrücklich zweimal eingefordert. Wenn eine Quelle an die 250 stößt,
  prüfe mit einem Abruf über 800, ob jenseits davon etwas im Frischefenster
  liegt — in Session 5 war das bei keiner der geprüften vier der Fall. Wenn
  doch: Grenze erhöhen, nicht achselzuckend stehen lassen.
- **Jede Quelle trägt `herkunft` und `abgenommen`.** `uebernehme_quellen.py`
  macht das von selbst; von Hand eingetragene Quellen auch.
- **`data/state/` und `data/reports/` nie aus lokalen Läufen committen.**
- **Nicht auf `main` pushen ohne Freigabe.** Branch:
  `claude/auftrag-1000-quellen-<suffix>`.

## 7. Fallstricke, die Session 5 teuer gelernt hat

Alle Punkte aus `CLAUDE.md` Abschnitt 6 gelten. Diese hier sind neu und
kosteten je einen halben Tag:

- **Ein leeres Modellergebnis sieht aus wie ein Rate-Limit und ist keins.**
  43 leere Antworten, kein einziger 429. `deepseek-v4-flash` ist ein
  Reasoning-Modell; sein Nachdenken zählt gegen `max_tokens`. Wenn Stapel
  reihenweise mit `Expecting value: line 1 column 1` scheitern: **Budget
  erhöhen**, nicht Parallelität senken. Analyst und Bereichsredaktion stehen
  bei 24 000, die Nebenstufen bei 12 000.
- **Ein formal erfolgreicher Lauf kann zur Hälfte ausgefallen sein.** Das
  Laufprotokoll wird bei jedem Lauf als Artefakt hochgeladen — **lies es**,
  bevor du eine Ursache vermutest. Ohne das wäre die falsche Diagnose
  stehengeblieben.
- **Modellnamen sind anbieterspezifisch.** Unter `llm_provider=deepseek` darf
  nirgends `openai_analyst_model` benutzt werden.
- **Der Abnahme-Check prüft Kandidaten auch gegeneinander** (Kriterium 7c) —
  vier von fünfzehn Treffern waren dieselbe Seite unter zwei Pfaden.
- **`uebernehme_quellen.py` schreibt YAML im Fluss-Stil**; Zeichenketten immer
  in Anführungszeichen, sonst beendet ein `?` in einer URL das Mapping. Das
  Sicherheitsnetz (neu laden, zählen, sonst Backup) hat das zweimal gefangen.
- **mfn.se beantwortet jeden Firmen-Slug mit einem gültigen, leeren Feed.**
  `finde_quellen.py` verlangt deshalb mindestens drei Einträge.
- **Ein Bereich kann alle anderen erdrücken.** 793 von 984 neuen Meldungen
  lagen in „Global" — jede Fachpressemeldung ohne Betreiber im Titel. Mit noch
  mehr Fachpresse wird das ausgeprägter. **Überlege, ob „Global" bei 1000
  Quellen aufgeteilt werden muss** (z. B. nach Sprache oder Weltregion der
  Quelle), sonst schreibt ein einziger Bereichsredakteur den halben Bericht.
  Das ist die einzige Architekturfrage, die dieser Auftrag offen lässt.

## 8. Abzuliefern

1. **Die Zahl.** Wie viele Quellen es geworden sind, mit `load_config` belegt.
2. Trefferquote vor dem Ausbau und nach jeder Welle, mit der Aussage, was sie
   für die jeweils nächste Welle bedeutet hat.
3. Je Welle ein echter Actions-Lauf, ausgewertet: Quellen ok/leer/fehlerhaft,
   gesammelte und neue Meldungen, Stapel erfolgreich/gescheitert, ungelesene
   Meldungen, Laufzeit je Phase — vor/nach im Vergleich.
4. **Belegen, dass nichts gekappt wird**: kein Stapel ungelesen, keine Quelle
   unbeabsichtigt an der 250er-Grenze.
5. Die verworfenen Quellen mit Ablehnungsgrund (wie
   `outputs/skalierung-2026-08-04.md` Abschnitt 4).
6. `pytest -q` grün, `python scripts/build_quellen_doc.py --validate` neu.
7. `CLAUDE.md` fortgeschrieben.
8. Eine ehrliche Schlussliste: erreichte Zahl, Mischung **mit Begründung aus
   der Messung**, blinde Flecken. **Lieber 700 belegte als 1000 behauptete** —
   aber diesmal ist 1000 das Ziel, nicht die Obergrenze des Ehrgeizes.

## 9. Ausdrücklich nicht

- Keine Kappung, an keiner Stelle der Pipeline.
- Keine Keyword-Nachrichtensuche als Quelle.
- Keine vorab festgelegte Mischung je Kategorie.
- Kein `newsroom_js` als Ersatz für „ich habe den statischen Endpunkt nicht
  gefunden" — es ist lokal nicht prüfbar und damit nicht abnehmbar.
- Keine Quelle eintragen, die nicht durch den Abnahme-Check gelaufen ist.
- Nicht die Architektur umbauen. Sie trägt; wenn etwas klemmt, ist es mit
  hoher Wahrscheinlichkeit ein Token-Budget oder ein Modellname.
