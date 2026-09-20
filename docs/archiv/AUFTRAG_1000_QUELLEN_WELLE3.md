# Auftrag: endlich auf 1000 Quellen

> Lies zuerst `CLAUDE.md` (Architektur, Zugänge, Fallstricke), dann
> `outputs/skalierung-2026-08-05.md` (was Session 5 gemacht und gemessen hat),
> dann diesen Text. **Dieser Text ist der Auftrag.**
>
> Stand: 205 Quellen. `python scripts/quellen_zaehlen.py` sagt dir jederzeit
> die aktuelle Zahl — benutze **nur** diese, siehe Abschnitt 1.

---

## 0. Warum die letzten Sessions stecken geblieben sind

Session 4 kam auf 130, Session 5 auf 205. Beide haben nicht am Werkzeug
gescheitert, sondern an zwei Dingen, die jetzt beide benannt und behebbar
sind:

**Der Sucher ignoriert drei Viertel des Webs.** `scripts/finde_quellen.py`
akzeptiert nur RSS und JSON-APIs als Kandidaten. Moderne Konzernseiten haben
aber meist keinen Feed mehr. Von 604 mechanisch gesuchten Firmen in Session 5
brachten **418 (69 %) null Kandidaten** — und zwar nicht, weil die Domain
falsch war: Telenor Norwegen, Vodafone Italien, Orange Spanien, Free,
Fastweb, Deutsche Telekom und DNA Finnland antworten alle mit HTTP 200 und
haben funktionierende Presseseiten. Sie deklarieren nur keinen Feed.

Die Pipeline kann so etwas längst lesen: **52 der 205 Quellen (25 %) sind
HTML-Newsrooms ohne Feed** (`type: newsroom`). Die stammen ausnahmslos aus
Handarbeit früherer Sessions. Der Sucher kann diese Sorte gar nicht
vorschlagen. **Das ist der größte einzelne Hebel im ganzen Ausbau.**

**Eine Firma wurde als eine Quelle behandelt.** Das ist falsch und kostet den
Faktor, der zu 1000 fehlt. Siehe Abschnitt 3.

---

## 1. Die Zahl

Es gibt ab jetzt genau eine: **crawlbare Quellen** = Betreiberquellen +
Fachpresse + Themenquellen, also was ein Lauf wirklich abfragt.

```bash
python scripts/quellen_zaehlen.py            # aktueller Stand
python scripts/quellen_zaehlen.py --verlauf  # Entwicklung über alle Läufe
```

Das Skript gleicht die Konfiguration gegen `stats.sources_total` des letzten
Laufs ab. **Zähle nie mit `grep -c "url:"`** — das zählt die nicht crawlbaren
`official`-Referenzen mit. Genau daran ist Session 5 mit einer falschen Zahl
in den Bericht gelaufen.

Nicht mitgezählt: `official`-Referenzen (werden nie abgerufen) und die
Promo-Seiten (eigener Anwendungsfall, eigene Pipeline).

---

## 2. Ziel

**1000 crawlbare Quellen.** Von 205 aus sind das +795.

Die Regel aus dem alten Auftrag gilt weiter und wird nicht aufgeweicht:
**1000 unbrauchbare Quellen sind schlechter als 205 gute.** Jede einzelne
läuft durch `scripts/pruefe_quellenvorschlag.py`. Was den Check nicht besteht,
kommt nicht hinein — auch nicht „weil sonst die Zahl nicht erreicht wird".

Wenn 1000 am Ende nicht erreichbar sind, sag das **mit Zahlen** und sag, wo
die Grenze wirklich liegt. Antonio will einen funktionierenden Radar, keine
Zahl im Changelog. Aber: die beiden Hebel unten sind noch nicht gezogen, und
vor ihnen ist jede Aussage über eine Obergrenze verfrüht.

---

## 3. Der Hebel, den niemand gezogen hat: mehrere Seiten je Firma

Bisher galt stillschweigend „eine Firma = eine Quelle". Das ist der
Denkfehler, der die Rechnung kaputtmacht.

Eine Fachpresse-Site hat oft **Rubrik-Feeds**: `/category/5g/feed`,
`/category/regulation/feed`, `/category/iot/feed`. Ein Betreiber hat
**Presse-Newsroom, Investor Relations, Technik-Blog, Landesgesellschaft**.
Ein Regulierer hat **Pressemitteilungen, Konsultationen, Verfügungen**. Das
sind jeweils eigene Quellen mit eigenem Inhalt — und sie zählen einzeln.

Der Bestand belegt, dass das trägt: zehn Betreiber haben heute schon mehr als
einen Kanal, und O2 Telefónica Deutschland hat drei, deren Inhalte sich
nachweislich nicht überschneiden (der dritte liefert die regionalen
Netzausbau-Meldungen, die in den beiden Konzern-Feeds fehlen).

**Aber Vorsicht, und das ist die halbe Arbeit:** genau hier entstehen
Dubletten. Session 5 hat zunächst 15 von 34 „bestandenen" Kandidaten
eingetragen, die bloße URL-Varianten bereits konfigurierter Quellen waren
(`newsroom.arm.com/feed` neben `.../rss`, vier Schreibweisen desselben
Apple-Feeds). Der Abnahme-Check prüft das inzwischen über die Domain und
gegen die **kleinere** der beiden Meldungsmengen — eine Quelle, die eine
bestehende vollständig enthält, ist eine Dublette, keine zweite Quelle. Ein
Vergleich, der mangels lieferfähiger Vergleichsquelle nicht stattfinden kann,
gilt als Durchfaller.

Rechne einmal durch, was das bedeutet: bei durchschnittlich 2,5 brauchbaren
Kanälen je Firma braucht es für 795 neue Quellen rund **320 Firmen**, nicht
8 000.

---

## 4. Was zu bauen ist, bevor gesucht wird

### 4.1 Newsroom-Erkennung im Sucher (der große Hebel)

`scripts/finde_quellen.py` muss `newsroom`-Kandidaten vorschlagen können:

1. Presseseite finden (die Kandidatenpfade dafür stehen schon in
   `NEWSROOM_PFADE`).
2. Prüfen, ob die Seite eine **Artikelliste** ist: mehrere Links mit langen,
   verschiedenen Ankertexten, möglichst mit Datumsangaben daneben.
3. Den passenden `item_selector` ableiten — der Newsroom-Collector
   (`collect/newsroom.py`) nimmt einen CSS-Selektor für die Artikelkacheln.
   Schau dir an, wie die 41 bestehenden `newsroom`-Quellen konfiguriert sind;
   die Muster wiederholen sich stark.
4. Den Kandidaten mit `type: newsroom` und dem Selektor ausgeben.

**Der Abnahme-Check bleibt unverändert streng.** Er läuft ohnehin durch
`collect_source`, also den echten Pfad der Pipeline — wenn der Selektor nichts
taugt, fällt der Kandidat an Kriterium 2, 3 oder 5 durch. Du musst den Sucher
also nicht perfekt machen, nur großzügiger.

**Die 418 Firmen aus Session 5, die null Kandidaten brachten, sind die erste
Testmenge.** Sie stehen in `config/kandidaten_firmen.yaml` und im Cache unter
`/tmp` (weg) — die Firmenliste im Repo reicht. Wenn die Newsroom-Erkennung
daraus keine 100 Quellen macht, taugt sie nicht.

### 4.2 Datums-Parser erweitern

Zweitgrößter Verlust nach dem Sucher. In Welle 2 lieferten **82 Kandidaten
Meldungen und fielen nur am Datumsformat durch** (Kriterium 3), 88 an der
Überschriftenerkennung (Kriterium 5). Das sind Parser-Lücken, keine schlechten
Quellen. `collect/newsroom.py` kennt nur die dort eingetragenen Monatsnamen —
für polnische, tschechische, ungarische, türkische, indonesische oder
japanische Seiten reicht das nicht.

Miss vorher und nachher: wie viele der abgelehnten Kandidaten aus Session 5
bestehen nach der Erweiterung? Die Befunde liegen als JSON vor, wenn du sie
neu erzeugst.

### 4.3 Rubrik-Feeds systematisch abklopfen

Für jede Site, die schon eine Quelle stellt: `/category/<x>/feed`,
`/tag/<x>/feed`, `/rss/<rubrik>.xml`, `?cat=` durchprobieren. Das ist reine
Mechanik und kostet keine Recherche. Der Dublettencheck fängt ab, was zu stark
überlappt.

---

## 5. Der Workflow — ausdrücklich groß angelegt

Antonio will das explizit so: **viele Agents parallel.** Nutze das
Workflow-Werkzeug.

**Arbeitsteilung, und sie ist nicht verhandelbar:**

- **Sonnet-Agents recherchieren im Web**, welche Firmen und Seiten überhaupt
  in Frage kommen. Sie liefern **Name + Domain + kurze Begründung**, mehr
  nicht. Sie dürfen ausdrücklich Websuche benutzen — Session 5 hat die
  Firmenliste aus Modellwissen geschrieben, und das ist der Grund, warum sie
  bei 604 Firmen aufhörte statt bei 6 000. Lohnende Suchaufträge: Marktüber-
  sichten je Land („mobile operators in <Land>"), nationale Regulierungs-
  behörden, Fachpresse je Sprache, Verbände, Tower- und Glasfaserbetreiber,
  MVNO-Plattformen.
- **Ein Agent, der eine Quelle vorschlägt, darf sie nicht abnehmen.**
  Vorschlagender Agent = Anwalt, `pruefe_quellenvorschlag.py` = Skeptiker.
- **Die mechanische Suche und der Abnahme-Check laufen als Code, nicht als
  Agent.** Beide sind auf Massenbetrieb ausgelegt: `--cache` für
  Wiederaufnahme nach Abbruch, `--index` für die Dublettenprüfung ohne
  Live-Abrufe, Host-Drosselung eingeschaltet.
- **Am Ende die Gesamtliste noch einmal zentral durchlaufen lassen.**
  Agent-Meldungen über bestandene Prüfungen sind kein Beleg. In Session 4
  bestand von zwölf Agent-Vorschlägen genau einer die zentrale Nachprüfung.

**Die Wertprüfung bleibt Handarbeit und ist der Schritt, den man nicht
überspringen darf.** Der Check prüft Form, nicht Wert. Session 5 hat von 116
bestandenen Kandidaten nur 73 eingetragen. Verworfen wurden unter anderem:

- **Termin- und Formularfeeds**: `investors.att.com/rss/events-and-presentations`
  liefert sauber datierte Meldungen namens „Perpetual Preferred Stock,
  Series C Dividend Payment Date".
- **Kampagnen-SKUs statt Überschriften**: TIM Brasil („DEFAULT_AGOSTO
  CarrosselStore - Migração - Pré para Controle_43,5GB_47,99"), Turkcell
  („Defacto Kampanyası").
- **Falsche Behörde**: `gov.br/rss.xml` ist das ganze brasilianische
  Regierungsportal, nicht Anatel.
- **Allgemeine IT- und Verbraucherpresse**: Computerwoche („Die besten
  Android Launcher"), Silicon FR, Les Numériques, Frandroid, Der Standard,
  inside digital, Tuttoandroid.
- **Kommentar-Feeds**: `.../comments/feed` sind Leserkommentare, keine Artikel.

Die Begründungen stehen als Kommentar in den YAMLs. **Lies sie vor jedem
Eintrag** — sonst schlägt die nächste Runde dasselbe wieder vor.

---

## 6. In Wellen, mit echtem Lauf dazwischen

Nach jeder Welle von ~200 Quellen:

1. `python scripts/quellen_zaehlen.py` — die Zahl.
2. Einen echten Actions-Lauf. Für die reine Sammeldiagnose reicht
   `sources_only` (fasst weder State noch LLM an und misst die Sammelphase
   mit vorher/nachher). Für die Abnahme einer Welle braucht es einen Volllauf.
3. `python scripts/quellen_trefferquote.py` neu auswerten — **ab jetzt je
   KANAL**, weil das Laufprotokoll `new` und `source_url` mitführt. Das ist
   die Kennzahl, die den Ausbau steuert.
4. Ballast aussortieren, den die Trefferquote belegt.

**Der erste Lauf nach jeder Welle ist groß**: alle neuen Quellen liefern ihr
volles Frischefenster auf einmal. Lauf #75 hatte nach 35 neuen Quellen 426
neue Meldungen statt der üblichen ~120. Plane das ein und prüfe, ob der
Stapelschutz greift.

---

## 7. Was schon steht und nicht neu gebaut werden muss

| Werkzeug | Zweck |
|---|---|
| `scripts/quellen_zaehlen.py` | die eine Zahl |
| `scripts/finde_quellen.py` | mechanische Breitensuche, `--firmen`, `--aus-watchlist`, `--cache` |
| `scripts/pruefe_quellenvorschlag.py` | Abnahme, neun Kriterien, `--cache`, `--index` |
| `scripts/quellen_trefferquote.py` | bewertet / NEU je Quelle |
| `scripts/miss_sammelphase.py` | Sammelphase messen, `--vergleich` |
| `scripts/kostenrechnung.py` | Kosten je Lauf und Monat |
| `scripts/build_quellen_doc.py --validate` | Quellen-Doku |

Architektur: Host-Drosselung (64 Worker), harte Frist je Quelle (75 s),
eigenes Limit für Headless-Renderings (4), kompakter Seen-Store (17 statt
300 Byte), zweistufige Redaktion ab 120 bewerteten Meldungen (im Lauf #75
abgenommen), Quellenregister mit automatischer Quarantäne nach 6 leeren
Läufen und Bewährungsabruf alle 10.

Kosten sind kein Argument: 1000 Quellen kosten mit zweistufiger Redaktion
**1,45 $/Monat** im teuersten Fall.

---

## 8. Abzuliefern

1. Newsroom-Erkennung im Sucher, gemessen an den 418 Firmen aus Session 5,
   die bisher null Kandidaten brachten.
2. Erweiterter Datums-Parser, gemessen an den abgelehnten Kandidaten.
3. Rubrik- und Zweitkanal-Suche je bestehender Site.
4. Der Workflow mit Sonnet-Recherche, in Wellen, jede mit echtem Lauf.
5. Die Zahl nach jeder Welle aus `quellen_zaehlen.py`, nicht geschätzt.
6. Trefferquote je Kanal nach jeder Welle.
7. `pytest -q` grün, `build_quellen_doc.py --validate` neu erzeugt.
8. `CLAUDE.md` fortgeschrieben.
9. Eine ehrliche Schlussliste: wie viele es wirklich geworden sind, wie die
   Mischung aussieht und **warum sie so aussieht** (belegt mit der
   Trefferquote), was verworfen wurde und warum, wo blinde Flecken bleiben.

## 9. Ausdrücklich nicht

- Keine Quelle eintragen, die nicht durch `pruefe_quellenvorschlag.py`
  gelaufen ist.
- Keine Aufweichung der Abnahmekriterien, um die Zahl zu erreichen. Wenn du
  ein Kriterium für falsch hältst, ändere es **begründet und mit Messung** —
  nicht stillschweigend.
- Keine vorab festgelegte Mischung (Anteil Betreiber / Fachpresse /
  Regulierung). Über 11 Läufe liegen alle drei Ebenen bei der Trefferquote
  praktisch gleich (12,2 / 10,5 / 10,8 %). Was taugt, entscheidet die Messung.
- Keine Kappung von Meldungen (`max_items_per_region`,
  `editor_max_highlights` bleiben 0). Wer nicht bewertet wird, ist über den
  Seen-Store dauerhaft verloren.
- `data/state/` und `data/reports/` nicht aus lokalen Testläufen committen.
- Kein `newsroom_js` als Ersatz für „ich habe den statischen Endpunkt nicht
  gefunden" — lokal nicht prüfbar und damit nicht abnehmbar.
- **Zahlen nicht schätzen.** Jede Zahl im Bericht muss aus einem Skript oder
  einem Laufprotokoll kommen. Session 5 hat sich zweimal selbst verrechnet,
  und beide Fehler waren in sich stimmig genug, um nicht aufzufallen.
