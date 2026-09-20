# AUFTRAG: EINE Geräteseite BAUEN — Übergabe an die nächste Session

**Stand 16.09.2026, abends. Diese Datei LÖST `AUFTRAG_GERAETE_EINE_SEITE.md` ab.
Geschrieben nach drei Kritik-Runden von Antonio am selben Tag; sie enthält seinen
Wortlaut, alle Entscheidungen, den Beweisstand und den Prozess. Die nächste Session
beginnt HIER — nicht bei den älteren Aufträgen, nicht bei der Strategie (siehe §8).**

---

## 0. Die fünf Regeln zum Lesen dieser Datei

1. **Antonios Zitate sind Bauanweisung.** Wörtlich zitiert in §2 und §9. Wer eine
   Formulierung „interpretieren" will, liest zuerst die Do-Not-Liste (§4) — jede
   Fehlinterpretation vom 16.09. entstand dort, wo ein Punkt vage blieb.
2. **Was als GENEHMIGT markiert ist (§1), wird nicht neu verhandelt, nicht
   „verbessert", nicht durch Alternativen ersetzt.** Der Graph ist genehmigt.
   Das Suchfeld ist genehmigt. Kopf/Nav bleiben 1:1 die Live-Seite.
3. **Keine neuen Entwurfs-Zyklen.** Antonio: „Ich will jetzt nicht, dass du einen
   neuen Entwurf machst." Der Prototyp `docs/entwuerfe/geraete-eine-seite-2026-09-16/
   entwurf-v2.html` ist die Arbeitsgrundlage. Es wird GEBAUT (Echtbetrieb), und
   offene Sinn-Fragen (§2) werden im Bau mit Begründung entschieden — Antonio sieht
   das Ergebnis, nicht einen weiteren Vorschlag.
4. **Jede Zahl aus dem Bestand, jede Zahl mit Beleg.** Keine geschätzten,
   geglätteten oder erfundenen Werte. Der Bestand ist `data/state/` (nächtlicher
   Lauf ohne KI, täglich 03:10 UTC — läuft von selbst weiter, nichts anstoßen).
5. **Zweifel? Dann die Entscheidung, die RUHIGER ist.** Antonio: „Elegant ist, mit
   wenigen Akzenten viel zu erreichen." Weniger Sektionen, weniger Wörter, weniger
   Leisten — nie mehr.

---

## 1. GENEHMIGT — der Kern steht fest (16.09.2026)

### 1a. Der Graph ist die TCO-ZEITREIHE — Antonios Wortlaut

> „Ich will einen verfickten Graphen haben. Mit verfickten Punkten und
> Koordinatensystem. Ich gebe das Modell ein, ich gebe den Tarif ein und dann sehe
> ich, welche Anbieter zu welchem Preis das Modell verkauft — Total Cost of
> Ownership. Y-Achse ist Euro-Kosten. Und X-Achse ist das DATUM. Ich möchte dann
> genau die verschiedenen Messtage immer sehen. Damit ich dann auch sehen kann, an
> welchen Tag haben die die Preise runtergetan, an welchen Tagen haben sie das
> hochgemacht."

**Nach dem Ansehen:** „So hatte ich mir das auch tatsächlich vorgestellt.
Den Graphen finde ich gut."

Die umgesetzte, DOM-bewiesene Form (Prototyp entwurf-v2.html, Commit 2f40457):
- SVG-Koordinatensystem; **Y-Achse: TCO-24 in €** (Ticks „1.200 € / 1.400 € /
  1.600 €"); **X-Achse: Datum** — die ECHTEN Messtage als Ticks („12.9. … 15.9."),
  echte Datumsabstände, keine ordinale Achse.
- **Je Anbieter eine Linie mit einem Punkt je Messung**; Wert-Labels am letzten
  Punkt (groß) und ersten (klein); Vodafone rot mit Etikett „unser Angebot";
  Beleg-Link (↗ + Abrufdatum) am Linienende je Anbieter.
- **Nichts interpoliert:** hat ein Anbieter weniger Messtage (Telekom: 1 Punkt,
  dazu seit 15.9.), gibt es keine Linie — Lücken sind Informationen.
- Gesteuert von Suchfeld (Modell) + Band-Wahl (Klein/Mittel/Groß); Startzustand =
  das Modell×Band mit den meisten Anbietern/Punkten (aktuell iPhone 17 Pro 256 ·
  Klein: 4 Anbieter, 13 Punkte).
- Daten: `data/state/geraete_tco_historie.jsonl` (seit 12.09.2026, wächst jede
  Nacht; 4 Messtage 12.–15.9. im Stand dieses Auftrags) je (Modell,Band,Anbieter,
  Tag) → günstigstes Bündel → eingefrorene Leitzahl. Sammel-Skript des Prototyps:
  `docs/entwuerfe/geraete-eine-seite-2026-09-16/historie_sammeln.py` — die
  Produktiv-Abbildung gehört in den Server-Render (E2), kein Client-Rechnen.

### 1b. Das Suchfeld ist genehmigt

> „Was ganz gut ist: wie man hier die Sachen auswählen kann mit dem iPhone und mit
> der Vorschau, das war ja genau das was ich haben wollte."

Live-Vorschau ab 2 Zeichen, ≤8 Treffer, Modellname + GB-Stufen + Anbieterzahl,
klickbar vor vollständiger Eingabe, deterministisch sortiert (Bandabdeckung
vor Auslaufware). Kein Dropdown mit Riesenliste.

### 1c. Kopf, Navigation, Design = die Live-Seite, 1:1

> „Ich möchte, dass die verfickte Geräte-Unterseite im selben Stil ist wie die
> ganze andere Seite, von der Überschrift her. Warum hast du die Taskleiste
> verändert?"

Der Prototyp übernimmt `<head>`, Topbar, Nav, Hero, Footer und style.css
UNVERÄNDERT aus `site/geraete.html`. Das bleibt im Bau so: Die Geräteseite
erbt `base.html.j2` wie jede Seite — kein eigenes Design, keine eigene Nav.

### 1d. Struktur: EINE Seite mit REITERN

> „Wieso kannst du nicht einfach Geräte-Unterseite, darunter dann verschiedene
> Unterseiten/Reiter (Preisvergleich, …), eine Ansicht wo der Graph ist —
> statt dass man 30 Minuten scrollt."

Eine URL (`geraete.html`), darin vier Reiter: **Vergleich (Start, der Graph) ·
Radar · Preisverlauf · Gerätekatalog**. Die alte `wettbewerbsradar.html` hört auf
zu existieren → Meta-Refresh-Weiterleitung nach `_redirect_html()`-Muster
(steht als Musterdatei im Entwurfsordner). Navigation 8 → 7 Einträge;
`tests/test_suche_page.py` und `scripts/pruefe_portal.py` Kriterium 11 mitziehen.

---

## 2. Die offenen Sinn-Fragen — NICHT entfernen, SINN STIFTEN (16.09., abends, wörtlich)

> „Was ist jetzt Preisverlauf die Unterseite? Was hat die für einen Sinn? […]
> Gerätekatalog genau das gleiche. Was sind diese zwei Unterseiten? […] Und das
> heißt jetzt nicht, dass du die entfernen sollst, das heißt, dass du dafür sorgen
> sollst, dass sie einen Sinn haben."

> „Ich verstehe nicht, was bei Radar jetzt ist. Man sieht erstmal die Warnungen,
> Alarme, okay. Dann dahinter Abweichung — was soll das bedeuten? Setzt du das
> gleiche wie oben? Was ist denn Händler Gerätepreis? Das ist dann ohne
> Finanzierung oder was. Okay, ist vielleicht auch ganz interessant. Aber das
> sollte nicht auf so einem komischen unteren Abschnitt ganz unten sein, weil das
> ist was ganz anderes."

> „Ich musste auch eigentlich irgendwo sehen können, die ganzen Modelle irgendwo
> aufgelistet."

**Daraus folgen BAU-Anforderungen (in E2/E3 umsetzen, Entscheidungen im
Baubericht begründen — kein erneuter Abnahme-Entwurf):**

| # | Anforderung | Wo |
|---|---|---|
| S1 | **Jeder Reiter beantwortet EINE klar benannte Frage** in seinem Titel + einem Satz. Löst der Reiter dieselbe Frage wie ein anderer (Preisverlauf vs. der Zeitreihen-Graph der Startansicht!), wird er UMGEWIDMET oder zusammengeführt — mit Begründung. „Entfernen" ist keine Option. | E2/E3 |
| S2 | **Modell-Übersicht:** Die Abweichungstabelle des Radars (alle Modelle nach Δ zu Vodafone) IST die Modell-Liste — sie muss als solche erkennbar sein (klarer Titel wie „Alle Modelle nach Abweichung zu Vodafone", alle Zeilen, sortierbar, mit Sprung in den Graphen je Modell). | E3 |
| S3 | **Radar-Sektionen klar getrennt und richtig platziert:** Alarme (Barpreis ohne Vertrag, Warnstufen) / Abweichung TCO (die Modell-Liste, S2) / **Händler = Gerätepreis ohne Finanzierung als EIGENER, gleichwertiger Abschnitt — nicht „komisch ganz unten"**, mit einem Satz, was er misst. Jede Sektion erklärt in EINEM Satz ihre Frage; keine Sektion ohne erkennbaren Zweck. | E3 |
| S4 | Die vier Reiter erhalten eine **einheitliche Sprache**: dieselbe TCO-24-Definition, dasselbe Δ-Vorzeichen, derselbe Beleg-Stil (↗ + Datum). | E2–E5 |

---

## 3. Alle Entscheidungen Antonios (Chronologie, alles gesetzt)

1. **3 Rest-Aufklapper behalten** (16.09., zu den „Unterkommentare weg"-Forderungen):
   Rechenschaftssatz (eine Zeile unter dem Antwort-Satz), Rechenweg je Anbieterzeile,
   Fuß-Aufklapper „Maßstab & Datenlage". Alles andere an Erklärlast bleibt GELÖSCHT
   (Glossar „Begriffe erklärt" weg, „Wie gerechnet?" weg).
2. **Geräte-Kacheln neben dem Suchfeld: ja, bauen** (4–6 häufigste Geräte als
   Schnelleingang; mobil Falz nachmessen, 11c geht vor).
3. **Strikt nach Preis sortieren** („Vodafone steht, wo sein Preis steht" — Emphasis
   nur über rote Linie/Etikett). Gilt für jede Liste der Seite.
4. **Graph = TCO-Zeitreihe** (§1a) — ersetzt ALLE früheren Graph-Formen
   (Balkendiagramm-Querschnitte, Stapelbalken, Ergebnisliste als „Graph-Ersatz").
5. **Reiter Sinn stiften, nicht entfernen** (§2).
6. **Push-Freigabe steht** (15.09.): nach JEDEM Push `deploy.yml`-Ausgang prüfen und
   live per md5/Inhalts-Marker gegenprüfen (erste Messung nach Deploy kann durch
   CDN-Propagation durchlaufen). Alt-URL, Exporte, Render-Commit „Seite neu gebaut"
   am Ende (Muster `bd3fbde`).
7. **Auto-Erkennung neuer Modelle/Tarife** bleibt Auftrag (Phase E4):

   > „Es kann ja nicht sein, dass man, wenn ein Modell rausgekommen ist, ich das im
   > Code wieder was neues schreiben muss […]. Das muss automatisch erkennen und
   > automatisch richtig einschreiben."

   Beleg im Bestand: Der Telekom-Tageslauf vom 15.09. lieferte „iPhone 18 Pro
   256 GB polar" und „iPhone 18 Pro Max" strukturiert — protokolliert als „Titel
   ohne Katalogtreffer" und verworfen. E4 empfohlene Option: Auto-Anlage NUR aus
   strukturierten Live-Katalognamen (Telekom `name`, o2 `description`, Vodafone
   `modell`), Hersteller-Schälung, Kollisionswächter (Hand-Eintrag schlägt Auto),
   generation nur bei eindeutiger Serie, marktstart/vorgaenger leer, Marker
   `auto:<datum>`, Listungen SOFORT (Launch-Preishistorie), Sichtbarkeit ab
   2 Messtagen; Persistenz unbekannter Titel/Farben in
   `data/state/geraete_unbekannt.jsonl` (kommt MIT in den gezielten Stand-Commit
   von `geraete.yml` — S1-Befund des Strategie-Reviews). Titel-Heuristik (Option a)
   bleibt verworfen (ID-Stabilität, Sägezahn-Gefahr — CLAUDE.md-Katalog-ID-Regel).

---

## 4. Do-Not-Liste — jede Zeile aus einem echten Fehler vom 16.09.

1. **Kopf/Nav/Design niemals neu erfinden** — Live-Basis (base.html.j2/style.css).
2. **Keine Unterüberschriften/Unterkommentare/Abschnitte zwischen Kopf und Graph.**
   Eine Wahl-Leiste (Suchfeld+Band), ein Antwort-Satz, dann der Graph.
3. **Kein Meta auf der Lesefläche:** kein „Antonios Leitfrage", keine Falz-Rechnung,
   kein „Beispiel:", keine „Rest-Aufklapper"-Deklaration, kein „(Entwurf)".
   (Die Abteilung liest diese Seite.)
4. **Keine Endlosseite** — Reiter, kein 30-Minuten-Scroll; Radar-Inhalte gedeckelt
   (Aufklapper „alle N anzeigen"), Höhenbudget je Tafel < 3000 px (Kriterium 11b).
5. **Keine je-Anbieter-Lücken-Zeilen.** EIN Sammelsatz unter dem Graphen, fehlende
   Anbieter mit Namen, mit Alternativ-Bändern samt Betrag in Klammern
   („Telekom (klein 1.536,95 € · groß 2.067,75 €)").
6. **Keine Doppel-Darstellung** (keine Band-Matrix unter der Liste, keine zweite
   Tabelle für dieselbe Frage).
7. **Keine „fünf Tasklisten"** — max. Reiterleiste + EINE Wahl-Leiste.
8. **Ein Graph ist ein Graph:** Punkte + Koordinatensystem (Y=€, X=Datum). Keine
   Balkenquerschnitte, keine zweite Graph-Form neben der Zeitreihe.
9. **Jede Zahl mit Absender und Beleg** (↗ echte URL + Abrufdatum); Antwort-Satz
   löst „TCO-24" selbst auf („… über 24 Monate (TCO-24)").
10. **Zahlen nur aus dem Bestand** — Messtage zählen und ehrlich nennen
    („Messtage: 12.9. bis 15.9."), nichts glätten, nichts interpolieren.

---

## 5. Beweisstand des Prototyps (Arbeitsgrundlage)

- **Ordner:** `docs/entwuerfe/geraete-eine-seite-2026-09-16/` — `entwurf-v2.html`
  (serverfrei: zahlen inline in `#gr-zahlen`, läuft per file://-Doppelklick),
  `prototyp.js`, `style.css` (Live-Kopie), `zahlen.json` (+Feld `historie`),
  `zahlen_sammeln.py`, `historie_sammeln.py`, Screenshots `v2-final2-*`.
- **Commits auf main (docs-only, NICHT gepusht):** 29e8ee0 → d9f515e → 971f420 →
  3f31fea → 2f40457 (+ Strategie/Erstentwurf-Commits davor).
- **DOM-Beweise (von der Leitungs-Instanz SELBST gemessen, nicht nur Agenten):**
  13 Punkte, 3 Linien, 4 Beleg-Links; X-Ticks 12.9.–15.9., Y-Ticks 1.200–1.600 €;
  Antwort-Satz + Messtag-Zeile; 390 px scrollWidth=390 (kein Querscroll);
  0 JS-Fehler; Graph 548 px hoch (desktop), beginnt y≈697.
- **Sichttest-Historie:** zwei frische Einkäufer-Sichttests (v1) BESTANDEN;
  v2-Prüfung BESTANDEN (Nav pixelgleich gegen Live-Seite gemessen); gleichartige
  Prüfung nach E2 wiederholen.

## 6. Technische Randbedingungen (echt, alle passiert)

- **Kein dauerhafter http.server möglich** (wird bei Speicherknappheit gekillt):
  Lokale Ansichten serverfrei bauen (Daten inline) oder kurzlebig messen.
- **CDN-Cache-Falle bei Screenshots:** gleichnamige PNG-Uploads liefern Altbestand.
  Screenshots für die Prüfung IMMER unter neuen Dateinamen erzeugen; DOM-Messung
  ist der Primärbeleg, Bildanalyse der Zweitbeleg (Blick-Agent kann helles
  Ink-auf-Anthrazit fehllesen — DOM/Pixel zählt).
- **Fremde http.server laufen auf dem Rechner** (Ports 8777/8791/8871 können
  belegt sein): eigener Messserver auf unüblichem Port, Marker per curl gegen den
  EIGENEN Render, am Ende nur die eigene PID killen.
- Playwright/Chromium ist installiert und netzfähig; pytest: **3054 passed /
  3 failed / 14 skipped** auf main — die 3 Roten sind vorbestehend (2×
  test_promo_seite ohne Pillow, 1× test_geraete_lifecycle) und werden NICHT
  angefasst. `pruefe_portal.py` 17/1 (8b vorbestehend).
- **Höhen-/Falzkriterien mitziehen:** 11b (<3000 px je Tafel), 11c (erste
  Graphenzeile/Antwort über der 844er-Telefon-Falz — im Prototyp: Antwort-Satz +
  Graphkopf bei ~780 px). Kriterium 11 muss auf die EINE Seite umgestellt werden
  (Alarmtabelle zukünftig von geraete.html lesen).
- **Seen-Store-/State-Regeln:** kein Commit von `data/state/` oder `data/reports/`;
  `site/` nur als eigener „Seite neu gebaut"-Commit am Phasenende.
- Klassen-Falle: `.gr-a-zeile` ist im Radar MEHRDEUTIG (Katalog- UND Alarm-Zeilen)
  — Selektor nie allein auf die Klasse stützen.

---

## 7. Der Prozess der nächsten Session (Workflows, autonom bis live)

### 7.0 Die ROLLE der nächsten Session: LEAN LEAD (Antonios Vorgabe, 16.09.)

**Die Session ist eine Orchestrierungs-Instanz — kein Bauer.** Ihre Aufgabe:
dynamische Workflows erstellen und laufen lassen. Sie verändert selbst NICHTS.

| Die Session (Lean Lead) tut das | Sie tut NICHT das |
|---|---|
| Workflows entwerfen, starten, überwachen (Workflow-Tool; Agenten mit frischem Kontext je Aufgabe) | Selbst Code schreiben, Templates/Config editieren, Dateien umbauen |
| Aufgaben-Prompts präzise formulieren (mit §1/§3/§4/§9 als Quelle) | Ganze Dateien/Module in den eigenen Kontext lesen — Subagenten lesen und melden Resümee + Messwerte |
| Agenten-Berichte bewerten, S1/S2-Befunde an Fix-Agenten zurückweisen | Selbst reparieren, „nur schnell die eine Zeile" — diese eine Zeile gehört dem Bau-Agenten |
| Abnahme: KURZE eigene DOM-Stichproben (ein Playwright-15-Zeiler gegen die gerenderte Seite), Testsuite starten, Commit-Hygiene prüfen | Sich durch Codecdurchgänge/Reviews arbeiten — dafür gibt es die Prüf-Agenten |
| Phasen nacheinander autonom durchziehen bis live; Commits/Merges abnehmen; am Ende Antonio berichten | Rückfragen an Antonio, außer die Seite ist kaputt/unklar auf eine Weise, die bauen verhindert |

**Warum diese Rolle (Antonios Worte):** „Du sollst als Lean Lead arbeiten, damit
dein Kontext klein bleibt — an Subagenten delegieren und Workflows laufen lassen."
Und: „Zur Kontrolle sollte das immer ein anderer Agent machen, nicht du — ein
Agent, der nichts gebaut hat." Die Session, die alles selbst liest und baut,
verliert den Überblick (der 16.09. ist das Beweisstück: drei Fehlinterpretationen
in einem Tag); die Session, die nur orchestriert, behält Urteilsfähigkeit für die
Abnahmen — und die Übergabe an die übernächste Session bleibt klein.

**Praktische Leitplanken für den Lead-Betrieb:**
- Ein Workflow pro Phase (Muster unten). Agenten bekommen: präzisen Auftrag,
  Datei-Pfade, Regeln aus §4, und die Anweisung, Berichte kurz und mit Messwerten
  zu schreiben (Zahlen, px, Sekunden, Commit-Hashes — keine Romane).
- Prüf-Agenten starten IMMER mit frischem Kontext und OHNE die Begründung des
  Bauers; sie sehen Screenshots selbst an (neue Dateinamen, §6) und messen DOM.
- Der Lead misst nur punktuell selbst nach (Stichprobe, nicht Fläche) — genug,
  um Agenten-Meldungen zu verifizieren, wenig genug, um den Kontext klein zu
  halten.
- Phasenübergang erst, wenn Abnahme grün: Suite komplett, pruefe_portal,
  DOM-Stichprobe, Do-Not-Liste geprüft.

### Grundprinzip (Antonio, 16.09.): Pro Phase EIN Workflow

Der komplette Pipeline läuft — Bau → Prüfung → Fix → Abnahme — und die nächste
Session arbeitet die Phasen autonom durch, bis die Seite live ist. Antonio will
Ergebnisse sehen, nicht gefragt werden (Ausnahme: §3-Entscheidungen sind
getroffen; nur bei SINN-Entscheidungen der Reiter gilt: begründen und bauen).

**Workflow-Muster je Phase (etabliert am 16.09., funktioniert):**
1. **Bau-Agent:** eigener Branch `claude/<phase>` (Worktree), rot-vor-grün zuerst
   (Tests NENNEN und vorher rot zeigen), kleine thematische Commits, sobald grün.
2. **Prüf-Agent mit FRISCHEM Kontext** (hat nichts gebaut, bekommt keine
   Begründung des Bauers): sieht Screenshots selbst an (1440+390, neue Dateinamen),
   misst DOM-Stichproben gegen den Bestand, läuft die Leitfragen, prüft
   Do-Not-Liste (§4) und Nav-Gleichheit gegen die Live-Seite.
3. **Fix-Agent** (Bau-Kontext) arbeitet S1/S2-Befunde ZWINGEND ein.
4. **Abnahme durch die Leitungs-Instanz:** DOM-Beweise SELBST nachmessen (nicht
   nur Agenten melden lassen), kompletter `pytest -q`, `scripts/pruefe_portal.py`,
   Commit-Hygiene, dann Merge nach main.
5. **Phasen E1–E5 mergen; E6 (Livegang)** zuletzt: Render-Commit, Push,
   deploy.yml-Ausgang prüfen, live gegenprüfen, Live-Sichttest von Antonios
   Beispiel („pixel 11" tippen → Band Mittel → Antwort lesen).

**Die Phasen (angepasst an die Entscheidungen vom 16.09.):**

- **E2 — Hauptansicht produktiv:** Zeitreihen-Graph + Suchfeld + Band-Wahl +
  Antwort-Satz + Lücken-Satz + Rechenweg aus dem Prototyp in die echte
  Geräteseite überführen (serverseitig gerendert: Template `geraete.html.j2`,
  View in `src/telco_radar/report/`, Historie-Aufbereitung im Render —
  `historie_sammeln.py` als Vorlage; kein Client-Rechnen von Zahlen). 3 Rest-
  Aufklapper (§3.1), Geräte-Kacheln (§3.2), strikte Preissortierung (§3.3).
  Glossar/Wie-gerechnet endgültig weg; Fußnoten auf DIE EINE Zeile reduzieren.
  Kriterium 11c auf Zeitreihe umstellen; Deep-Link `?modell=&band=` bleibt.
  *Abnahme:* Leitfrage in ≤12 s ohne Erklärung; 11c; Suite grün; pruefe_portal.
- **E3 — Eine Seite + Sinn (§2):** Radar-Tafel auf geraete.html, NEU
  strukturiert nach S1–S4 (Alarme / Abweichung ALS Modell-Liste / Händler als
  eigener Abschnitt); Reiter-Fragen geklärt und benannt (Preisverlauf/Katalog
  umwidmen oder zusammenführen, mit Begründung im Baubericht); Alt-URL-
  Weiterleitung; Navigation 8→7; Tests + Kriterium 11 umziehen; 88 Querlinks →
  In-page-Sprünge. *Abnahme:* Jede Reiter-Frage in einem Satz; keine Sektion
  „ganz unten komisch"; 11b alle Tafeln; Sichttest-Frage „wo ist Vodafone
  teuersten" ≤15 s.
- **E4 — Auto-Erkennung** (§3.7): wie beschrieben; Reproduktion des
  15.09.-iPhone-18-Falls als rot-vor-grün-Fixture; geraete.yml bekommt den
  Katalog-Bot-Commit (nur `config/geraete_katalog.yaml` + `geraete_unbekannt.jsonl`
  in der gezielten git-add-Liste). *Abnahme:* nach dem nächsten echten Nachtlauf
  steht „iPhone 18" im Katalog und in der Vorschau (ab 2 Messtagen).
- **E5 — Rest:** Exporte zentral (Kopfzeile, auch mobil; Radar-CSV erweitert um
  die Alarm-Zeilen → 4/4 Zahlensektionen), fünf Test-Leer-Sicherungen
  (O4-Evaluator S3), toter Code der Zwei-Seiten-Welt weg (grep wettbewerbsradar
  in src/templates → nur Weiterleitung + Exportname).
- **E6 — Livegang:** wie oben beschrieben; danach Betrieb (monatlich die fünf
  Sichttest-Fragen live + drei Protokollzeilen — PM-8 der Strategie).

**Bewusst NICHT (unverändert aus der Strategie):** P5-TCO-Zeitachse als eigener
späterer Schritt IST HIERMIT EINGELÖST (der genehmigte Graph IST die Zeitachse;
wächst automatisch mit den Messtagen) · E-S2 1&1 per Playwright · neue
Anbieter/Adapter · Nachrichtenseite · Dark-Mode/JS-Frameworks/CDN-JS · externe
Vergleichszahlen · zweite Such-Implementierung für andere Tafeln (eine Komponente,
mehrere Konsumenten).

---

## 8. Verhältnis zu den älteren Dokumenten

- `AUFTRAG_GERAETE_EINE_SEITE.md` (16.09. morgens): **abgelöst** — seine B1/B2/B3
  sind aufgegangen in §1/§2/§4; die dortigen offenen Punkte (Test-Leer-Sicherungen,
  Export-Knöpfe mobil, Radar-Export-Name) stehen in E5.
- `docs/STRATEGIE_GERAETE_EINE_SEITE.md` (Workflow-Produkt vom 16.09.): **Rahmen
  für Phasenabfolgen, Details teils überholt** — ihr §4 („Ergebnisliste statt
  Balkendiagramm") und die P5-Vertagung sind durch Antonios Graph-Entscheidung
  (§1a) ersetzt; E-Phasen laut §7 dieser Datei. Die nächste Session ACTUALISIERT
  die Strategie als ersten Bau-Schritt (Änderungsprotokoll dranhängen), damit es
  eine Quelle der Wahrheit bleibt.
- `docs/STRATEGIE_GERAETE_OPTIK.md` §7 (O1–O4): Baugeschichte; die Zeilenstruktur
  (Bündel-Zeilen, Fragment-Infrastruktur `site/data/geraete-buendel.html`,
  Exporte) bleibt Bestand und wird weiterverwendet, wo sie die Zeitreihe ergänzt
  (Rechenweg je Anbieterzeile, „Maßstab & Datenlage").

---

## 9. Wortlaut-Archiv (unverkürzt, in chronologischer Reihenfolge)

### 9a. 16.09.2026, vormittags — Kritik am Live-Stand nach O1–O4 (Anlass alles dessen)

> „Keine Ahnung, was du gemacht hast. Es war auf jeden Fall nicht das, was ich
> wollte. Also erstens, wieso gibt es jetzt zwei Unterseiten: Geräte und
> Wettbewerbsradar? Das ist absolute Scheiße. Geräte, Wettbewerbsradar, eine
> Unterseite. Ich habe keinen Bock, hier 300 Unterseiten auf meiner Seite zu
> haben. Zweitens, das Layout ist absolute Scheiße. Hier sind absolut zu viele
> 100 Millionen Unterkommentare. Ich muss erstmal nach unten scrollen, weil du so
> viele Kommentare und Überschriften gemacht hast, dass man erst runterscrollen
> muss, um den eigentlichen Graphen zu sehen […] Ich will den Abschnitt Begriffe
> erklärt: weg. Wie gerechnet: weg. Die Unterkommentare, alle weg. Ich will
> verfickt nochmal sehen können, wie viel der jeweilige Anbieter für den
> jeweiligen Tarif, für das jeweilige Modell nimmt. […] Und was ist mit dem
> Graphen, den du gemacht hast — absolute Katastrophe. Hast du dir den eigentlich
> mal angeguckt? Der ist absolut unverständlich. […] Ich will das so haben, dass
> man wählt hier oben die Modelle aus, dann den Tarifband. Und dann möchte ich
> hier einen Graphen haben, der sich daran anpasst. […] Du hast mir irgendein
> Scheiß Balkendiagramm gemacht. Was soll ich mit einem verfickten
> Balkendiagramm? […] außerdem absolut intransparent, wie die Preise zustande
> kommen. Beim Graphen zum Beispiel. […] außerdem gibt es schon das iPhone 18 Pro
> mittlerweile, das iPhone Duo. Wieso wird das nicht automatisch gecrawlt? […]
> dass wenn neue Modelle oder neue Tarife veröffentlicht werden, dass man nicht
> hier das wieder im Quellcode rumbasteln muss. Das muss automatisch gehen. […]
> dann gefällt mir das Design zum Beispiel vom Auswählen der Modelle überhaupt
> nicht. Ich möchte nicht, dass man hier was auswählen kann, Modelle, sondern
> dass man hier was reinschreiben kann. Dass ich hier Google Pixel zum Beispiel
> einschreibe und dann sieht man so ein kleines Feld mit allen Google Pixeln […]
> mit Gigabyte und so weiter, was man dann automatisch klicken kann. […] aber ich
> möchte nicht draufklicken und dann eine riesige Liste von allen Modellen
> bekommen. […] zur Kontrolle sollte das immer ein anderer Agent machen, nicht
> du. Ein Agent, der nichts gebaut hat […] dessen einzige Aufgabe es ist,
> herauszufinden, wie verständlich, wie intuitiv, wie gut ist diese
> Geräteunterseite. […] das, was ich jetzt gesagt habe, sind die Mindestbedingungen
> […] Was ich dann von dir aber noch erwarte, ist, dass du dir überlegst, wie
> kann ich die Seite noch verbessern? Immer weiter. Und erst wenn dir nichts mehr
> einfällt, dann bist du fertig. […] Vielleicht macht der Strategie-Workflow
> erstmal eine Recherche bei verschiedenen Seiten, so Vergleichsseiten wie Check24
> etc. […] Darum geht es nämlich bei uns: wir möchten wissen, wie viel kostet es
> den Kunden bei der Telekom, ein Google Pixel 11 Pro zu finanzieren mit einem
> mittleren Tarif. […] hängt das nicht auch davon ab, welches Modell? Ein iPhone
17
> Pro, kann man das mit einem kleinen Tarif finanzieren? […] außerdem, wenn zum
> Beispiel hier am Anfang bei den Balken, da sieht man auch gar nicht, wie wir auf
> diese Werte gekommen sind. Man kann hier nirgendwo auf den Link drücken, auf
> eine Quelle. Also auch absolut intransparent."

### 9b. 16.09.2026, nachmittags — Kritik am ersten Entwurf (v1, sinngemäß verdichtet)

1. „Das ganze Design vorne und hinten nicht — eine Krankheit. Wieso hast du die
   Taskleiste verändert? Die Geräte-Unterseite soll im selben Stil sein wie die
   ganze andere Seite, von der Überschrift her."
2. „Eine Million Informationen auf kleinem Raum — immer noch ganz viele
   Unterkommentare, Unterüberschriften, Unterabschnitte. Unglaublich unruhig.
   Fünf verschiedene Tasklisten."
3. „Ich sehe auch keinen Graphen. Wo ist der verfickte Graph?"
4. „Wieso alles auf einer langen Seite? Geräte-Unterseite, darunter verschiedene
   Unterseiten/Reiter […] statt dass man 30 Minuten scrollt."
5. „Was gut ist: die Auswahl mit iPhone und Vorschau — genau das, was ich wollte."
6. „Alle drei Bänder im Überblick unten — was hat das für einen Sinn? Ich sehe
   das doch schon oben. Richtig behindert."
7. „Telekom, 1&1 ‚kein Bündel erhoben' — wenn es nichts gibt, dann brauchst du es
   nicht anzuzeigen von den jeweiligen Anbietern."
8. „‚Antonios Leitfrage' — erwartest du, dass ich das zulasse? Die ganze Abteilung
   sieht das. […] Du stellst das als eigenen Abschnitt dar — aber darum geht es auf
   der GANZEN Seite."
9. „Elegant ist, mit wenigen Akzenten viel zu erreichen. Du machst genau das
   Gegenteil: mit sehr vielen Akzenten erreichst du sehr wenig."

### 9c. 16.09.2026, abends — Graph-Klarstellung und Sinn-Fragen (Endstand)

> „Ein Graph. Weißt du, was ein Graph ist? Ein verfickter Graph. Mit verfickten
> Punkten und Koordinatensystem. Ich gebe das Modell ein, ich gebe den Tarif ein
> und dann sehe ich, welche Anbieter zu welchem Preis das Modell verkauft —
> Total Cost of Ownership. Y-Achse ist Euro-Kosten. Und X-Achse ist das Datum.
> Ich möchte dann genau die verschiedenen Messtage immer sehen. Damit ich dann
> auch sehen kann, an welchen Tag haben die die Preise runtergetan, an welchen
> Tagen haben sie das hochgemacht."

> „So hatte ich mir das auch tatsächlich vorgestellt. Den Graphen finde ich gut.
> Aber die drei anderen Seiten [Reiter] verstehe ich nicht, was dahinter ist. Und
> das heißt jetzt nicht, dass du die entfernen sollst — das heißt, dass du dafür
> sorgen sollst, dass sie einen Sinn haben. […] Beim Radar sieht man erstmal die
> Warnungen, Alarme, okay. Dann dahinter Abweichung — was soll das bedeuten? […]
> Was ist denn Händler Gerätepreis? Das ist dann ohne Finanzierung oder was.
> Okay, ist vielleicht auch ganz interessant. Aber das sollte nicht auf so einem
> komischen unteren Abschnitt ganz unten sein, weil das ist was ganz anderes. […
> Ich möchte] irgendwo sehen können, die ganzen Modelle irgendwo aufgelistet. […]
> Ich will jetzt nicht, dass du einen neuen Entwurf machst […] das soll jetzt
> direkt beim Workflows, bei den Phasen mitlaufen. […] Und jetzt diesen Entwurf
> endlich mal anfangen, wirklich zu arbeiten. Und die Workflows laufen lassen. […]
> Mach nicht denselben Fehler wie die letzte Session, die einen Prompt geschrieben
> hat, mit dem du nichts anfangen konntest und ich musste dir alles neu sagen."

---

**Ende der Übergabe. Die nächste Session beginnt bei §7 (Phasen) — mit §1 als
gesetztem Kern, §4 als Grenzzaun und §9 als Original-Ton.**
