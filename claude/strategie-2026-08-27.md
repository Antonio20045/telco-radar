# Strategie 2026-08-27: Vom Mittelmaß zum Insights-Portal

Auftrag von Antonio (27.08.2026, direkt): Highlight-Seiten sind tot (Apple-Keynote
in zwei Wochen, keine Seite), Artikel uninteressant, Prioritäten falsch (Nufibre
vorn, iPhone 17 hinten), Übersetzungen fehlen, der Prosabericht fehlt („alle
Meldungen nur aufgelistet"), Promo-Übersicht unvollständig/unruhig — und der
Lauf vom 27.08. hat **1,95 $** gekostet, „absolut inakzeptabel".

Dieses Dokument konsolidiert die Befunde von fünf Diagnose-Agenten (alle
Messungen gegen Live-Site, Actions-Log Run 33066222198 und die Report-JSONs)
und legt die Umsetzungspakete fest.

---

## 1. Befunde — was wirklich kaputt ist

### B1: Seit dem 15.08. ist JEDER Lauf ohne Redaktion gelaufen (7 in Folge)

`editor_used=false` in allen Läufen 15.–27.08. Am 27.08.: Erster HTTP 402
„Insufficient Balance" um 11:51 UTC — 40 Minuten nach Start, mitten in der
Bereichsredaktion. Alles, was danach kommt, stirbt am leeren Konto:
Chefredaktion → Notfall-Digest (das ist die „Auflistung", die live steht),
Beleg-Prüfung, Kategorie-Sweep, **Promo-Extraktion (43×)**, **Übersetzung
(39×)**, **Themen-Agent (kam nie zum Zug)**.

Ein Fallback auf den vorhandenen Anthropic-Key existiert strukturell nicht:
`llm.py:_dispatch()` wählt das Backend **einmal pro Prozess**, und
`pipeline.py:138–144` **löscht ANTHROPIC_API_KEY aktiv aus der Umgebung**,
wenn `llm_provider: deepseek` gesetzt ist. Das Secret kommt im Workflow an
(radar.yml:159) und wird dann verworfen.

### B2: Die 1,95 $ sind fast vollständig der Analyst auf v4-pro

66 erfolgreiche Analysten-Batches (890 Ereignisse, 32 min) auf v4-pro mit
~8–9k Token Denkspur je Aufruf, die als Ausgabe abgerechnet wird. Die
Kostensenkung vom 18.08. (Mechanik auf flash) **funktioniert** (Clustering
lief nachweislich erfolgreich auf flash) — sie greift nur nicht am größten
Posten, denn Analyst und Redaktion blieben bewusst auf pro. Es gibt
**keinen echten Kostenzähler**: `llm.py` liest `usage` nur im Fehlerfall,
`scripts/kostenrechnung.py` ist eine Hochrechnung ohne Denkspur.

### B3: Die Apple-Keynote-Gruppe existiert — sie wird vom Rauschen verdrängt

Die deterministische Kandidatensuche findet über den 14-Tage-Korpus eine
saubere Apple-Event-Gruppe: `worte=['apple','iphone','september','ultra']`,
**10 Meldungen, 5 Quellen, 5 aus dem aktuellen Lauf** — alle Schwellen
erfüllt. Sie steht auf **Rang 17 von 116 Rohgruppen**, weil
`MAX_KANDIDATEN=6` nach **roher Gruppengröße** sortiert und sechs größere
Rausch-Cluster (Quartalszahlen „quartal/zweiten" n=32, „deutsche/telekom"
n=26, Regionalcluster) die Plätze belegen. Zweiter, unabhängiger Blocker:
selbst die vorgelegten 6 Kandidaten liefen ins tote Modell (B1).

### B4: Titelseite — der Rangschlüssel ist heute nicht der Engpass

Live-Aufmacher „Nufibre startet eSIM-Unlimited für 15 Pfund" (UK-Nische)
trägt `relevance 4–5, ctm_bezug 3`; „iPhone 17 weltweit meistverkauft"
trägt `relevance=4, ctm=2, category="Sonstiges"`, „Nothing Phone 3a /
Frankreich" `relevance=3`. Simulation über vier Rangvarianten: **keine**
bringt die beiden nach vorn — acht `relevance=5`-Meldungen sättigen alle
sieben Bildplätze, darunter **vier fast identische EE-Slicing-Artikel, die
die Ereignis-Bündelung nicht zusammengefasst hat**. Kernprobleme also:
(a) Cluster-Lücke bei Fachpresse-Dubletten, (b) Relevanz-Kalibrierung des
Analysten ohne Markt­gewicht des Absenders (Nufibre = Aufmacher,
iPhone-Weltmarktführung = „Sonstiges"), (c) roter Faden leer, weil der
Bericht ein Fallback ist (B1).

### B5: Englisch wird bewusst nicht übersetzt

`sprache.py:31: MUTTERSPRACHEN = {"de","en"}` — 143 der 163 vorgefilterten
Meldungen des 27.08. waren englisch und galten als „nicht fremdsprachig".
Für die Zielgruppe (Manager ohne sicheres Englisch) ist das falsch
geschnitten. Mit Englisch wären es ~226 statt 83 Kandidaten je Lauf — der
Deckel 40 und das Zeitbudget müssen mitwachsen. Es hat übrigens **nie**
ein Lauf übersetzt: 19.08. und 27.08. je 0 wegen `LLMModelUnavailable`,
21./25./26.08. `angeboten: 0` (degenerierte Läufe).

### B6: Promo-Datenbank seit 14.08. eingefroren

Alle 59 Seiten werden jeden Lauf abgerufen (13 Hash-Änderungen allein am
27.08.), aber `last_verified` steht bei allen Marken auf ≤14.08.: die
LLM-Extraktion (flash) stirbt seit zwei Wochen am leeren Konto, und der
Ausfall taucht in keiner Statistik auf (`stats` kennt kein `promo_*`-Feld).
Sortierung (Rang je Anbieter, Score innerhalb) ist korrekt umgesetzt.
Dazu ein echter Layout-Bug: Blöcke mit genau 1 oder 3 weiteren Karten
erzeugen leere Rasterzellen (PremiumSIM, simplytel, ALDI TALK). 21 % der
Karten sind strukturell bildlos (die vier bekannten Marken) — das ist
gemessen und nicht heilbar, die Schriftkachel ist dort der ehrliche
Regelfall. Nebenfund: Karteileiche „PŸUR" (8 Einträge) im Store, wird nie
gerendert.

### B7: Die bewerteten Meldungen sind zu 74 % B2B/Infra

Kategorien des 27.08.: Netz/Technologie 26 %, Regulierung 15 %, Sonstiges
14 %, Partnerschaft 9 %, Finanzen+M&A 10 % — Consumer-nah (Produktlaunch,
Tarif, Kampagne) nur 26 %. Dazu 10 Ballastquellen (PLDT 31, AIS 13, Türk
Telekom 10, du, Orange MEA, MTN, Airtel Africa, Liquid, Chunghwa, Swisscom)
mit **zusammen 105 neuen Meldungen und 0 je bewertet** über 23 Läufe. Die
wertvollsten Quellen sind durchweg Fachpresse (Light Reading 55, Telecoms
50, MWL 49, TelecomTalk 48 …).

---

## 2. Entscheidungen

| # | Entscheidung | Begründung / Rückweg |
|---|---|---|
| E1 | **Analyst bleibt auf v4-pro — die Token werden reduziert, nicht das Urteil.** (Revidiert 27.08. nach Antonios Einspruch gegen den Modellwechsel.) Vier Hebel: (a) **Vorsortierung auf flash** — heute bezahlt pro das Wegwerfen selbst (890 rein, 362 behalten); flash sortiert die offensichtlich Irrelevanten aus, pro bewertet nur die Kandidaten. Im Zweifel zu pro; Heimatmarkt-/CTM-Treffer umgehen die Vorsortierung. Von der Vorsortierung Aussortiertes gilt als gelesen; scheitert der flash-Aufruf, gehen die Meldungen ungefiltert zu pro (bzw. über den Stapelschutz in den nächsten Lauf). (b) **Batchgröße 15 → 24** — die ~8–9k Token Denkspur fallen je AUFRUF an, fast unabhängig von der Batchgröße; weniger Aufrufe = weniger Denkspur. max_tokens wächst mit (Lehre vom 18.08.). Die Denkspur selbst ist auf der direkten DeepSeek-API NICHT abschaltbar (der Parameter wirkt nur auf NVIDIAs Endpunkt, gemessen 07.08.). (c) E7 senkt die Ereigniszahl (Dubletten). (d) E9 Ballast. **Erwartung ehrlich gerechnet: ~1,3–1,6 $ je GESUNDEM Lauf** — die 1,95 $ vom 27.08. waren ein unvollständiger Lauf (ohne Chefredaktion, Beleg-Prüfung, Promo, Übersetzungen, Themen-Agent; vollständig wären es ~2,2–2,5 $ gewesen). Die 18.08.-Schätzung „0,30–0,60 $" ist an genau dieser Stelle gescheitert: geschätzt ohne Zähler, gemessen nie. Deshalb ist E3 (echter Zähler je Stufe) Voraussetzung — nach dem ersten gemessenen Lauf wird nachkalibriert. Tiefer als ~1,3 $ geht nur über Antonios Stellschrauben: Bereichsredakteure auf flash (−0,3–0,4 $) und/oder Umfangsdeckel. |
| E2 | **Anthropic wird Rettungsanker, nicht Ersatz.** | `_dispatch` routet künftig pro Modell (`claude-*` → Anthropic-API), der Key wird nicht mehr gelöscht, und die Modellketten enden in Claude-Modellen: Redaktion/Themen/Wettbewerber → `claude-sonnet-5`, Mechanik/Übersetzung/Analyst → `claude-haiku-4-5-20251001`. Der Anker greift NUR, wenn DeepSeek tot ist — im Normalfall kostet er 0 $. Nie wieder ein Lauf ohne Bericht. |
| E3 | **Echter Kostenzähler — er zählt NUR.** (Revidiert 27.08.: Antonio will keinen Lauf-Abbruch durch den Zähler.) `llm.py` summiert `usage` je Aufruf (inkl. Reasoning-Token) je Stufe; Summe und $-Schätzung landen im run-JSON und auf transparenz.html. `llm_budget_usd` (Vorgabe 1,50 $) ist eine reine **Warnschwelle**: Überschreitung erzeugt eine deutliche Protokoll- und Transparenz-Zeile, greift aber NIE in den Lauf ein — kein Batch wird gestoppt, nichts wird gekappt. Die harte Grenze bleibt das DeepSeek-Guthaben selbst; stirbt es, fängt der Anthropic-Anker (E2) die sichtbaren Stufen. |
| E4 | **Highlight-Kandidaten: Spezifität schlägt Größe; Antizipation als zweiter Pfad.** | Rausch-Bindewörter (Quartals-/Finanzvokabular, bloße Firmennamen) werden nachrangig sortiert; Gruppen mit Produktname+Ereignissprache steigen. Zweiter Erkennungspfad für **bevorstehende Ereignisse** (keynote/event/launch + Datumsbezug) mit niedrigerer Schwelle (≥3 Meldungen, ≥2 Quellen). Der Agent bekommt den Fall „bevorstehendes Ereignis" mit Zieldatum; das Thema altert erst ab Event-Datum + 7 Tage statt über den Zuwachs-Zähler. |
| E5 | **Englisch wird übersetzt.** | `MUTTERSPRACHEN = {"de"}`, Deckel 40 → 60 (settings), Priorisierung bleibt Berichtsreihenfolge, Zeitbudget bleibt gegen die Restzeit des Jobs. Übersetzungsmodell bleibt flash (Anker: haiku). Nicht jede Meldung wird eine Übersetzung bekommen — der Deckel schneidet nach Rang, das ist gewollt. |
| E6 | **Rangschlüssel: Priorität führt, CTM bricht Gleichstand.** | Die am 15.08. dokumentierte Stelle. Alleine hätte sie heute nichts geändert (B4) — zusammen mit E7/E8 stellt sie sicher, dass „wichtig" wieder „Priorität" heißt. Der Test `test_direkte_meldung_steht_vor_der_dringlicheren` wird mit Begründung umgekehrt. |
| E7 | **Cluster-Lücke schließen.** | Fachpresse-Dubletten desselben Ereignisses (4× EE-Slicing aus 4 Quellen) müssen EIN Ereignis werden. Kandidatenpaarung um quellenübergreifende Titel-Ähnlichkeit erweitern; Messlatte: die vier EE-Artikel des 27.08.-Korpus werden zu einem Ereignis gebündelt. |
| E8 | **Analysten-Prompt: Marktgewicht + Consumer-Fokus.** | Relevanz 5 verlangt künftig: großer Absender ODER unmittelbare Bedeutung für den deutschen/europäischen Endkundenmarkt. Nischenanbieter ohne Marktfolge sind gedeckelt. Globale Produkt-/Marktmeldungen (iPhone-Weltmarktführung) gehören in „Geräte", nicht „Sonstiges". |
| E9 | **10 Ballastquellen raus.** | 105 neue Meldungen, 0 bewertet über 23 Läufe — sie kosten Analystentoken (bei E1 weniger, aber nicht null). YAML-Kommentar dokumentiert Messung und Datum; Wiederaufnahme jederzeit möglich. Handover §9 Schritt 3 hat genau das vorgesehen. |
| E10 | **Promo: Grid-Bug fixen, Rest heilt E2.** | Leere Rasterzellen bei 1/3 weiteren Karten beheben. Die eingefrorene DB braucht keinen Code — sie braucht eine funktionierende Extraktion (E2) und einen sichtbaren Zähler (`stats.promo_*`, Teil von E3-Sichtbarkeit). PŸUR-Karteileiche bleibt im Store (wird nie gerendert), wird im Handover vermerkt. |

**Bewusst NICHT in diesem Paket:** neue Quellen suchen (braucht Netz-Massenläufe
über `pruefe_quellenvorschlag.py` — eigener Auftrag, B7 nennt die Richtung:
Consumer-Fachpresse DACH/EU), Nachredigieren alter Fallback-Berichte (der
nächste gesunde Lauf ersetzt die Live-Ausgabe ohnehin), Rangschlüssel-Deckel
für CTM-Stufen jenseits E6.

---

## 3. Premortem — woran das scheitern könnte

1. **Die Vorsortierung wirft eine wichtige Meldung weg.** Deshalb: flash
   verwirft nur eindeutige Fälle, im Zweifel geht die Meldung zu pro,
   CTM-/Heimatmarkt-Treffer umgehen die Stufe ganz, und die Protokollzeile
   nennt die Zahl der Aussortierten. Messauftrag: nach dem ersten gesunden
   Lauf stichprobenartig 20 Aussortierte lesen — ist eine dabei, die in den
   Bericht gehört hätte, wird die Schwelle konservativer.
2. **Der Anthropic-Anker wird teuer, wenn DeepSeek dauerhaft tot ist.** Der
   Anker deckt bewusst nur die Nach-Analyse-Stufen (wenige Dutzend Aufrufe);
   der Analyst fällt auf haiku (billigstes Claude-Modell). Der Kostenzähler
   (E3) weist Anker-Aufrufe getrennt aus.
3. **Antizipations-Pfad flutet die Themenseiten.** Schwellen bleiben hart
   (≥3 Meldungen, ≥2 Quellen, Ereignis- UND Datumssprache), der Agent
   verwirft weiterhin Firmen-Cluster, `MAX_KANDIDATEN` bleibt der Deckel —
   nur die Sortierung dahinter ändert sich. Wahrheitstest: die
   Quartalszahlen-Gruppe (n=32) darf NICHT vor der Apple-Gruppe stehen.
4. **402 mitten im Anker-Betrieb** (auch Anthropic kann 429/529 werfen).
   Fail-Verhalten bleibt wie heute: gefangene Exception, Fallback-Digest,
   Stapelschutz — nur eben zwei Anbieter tief statt einem.
5. **Der Zähler misst falsch** (Preistabelle veraltet). Die Tabelle steht
   in settings.yaml neben der Warnschwelle, beide an EINER Stelle; der
   Zähler schreibt Token UND $-Schätzung, sodass eine falsche Tabelle am
   Token-Ist auffällt. Da der Zähler nie eingreift, kostet ein Messfehler
   nur eine falsche Warnzeile, nie einen Lauf.
6. **Übersetzungsdeckel 60 sprengt die Laufzeit.** Das Zeitbudget rechnet
   weiter gegen die Restzeit des Jobs und bricht sauber ab; der Deckel
   schneidet nach Berichtsrang, die wichtigsten zuerst.

## 4. Messplan nach dem nächsten Actions-Lauf

1. `run.kosten` im Report-JSON: Gesamt im Rahmen 1,3–1,6 $? Größter
   Posten? Warnschwelle ausgelöst?
2. `editor_used=true`? Wenn DeepSeek wieder leer: kam der Anker (Anker-Feld
   im Kostenblock)?
3. `Highlight-Themen:`-Zeile: steht die Apple-Gruppe unter den Kandidaten,
   hat der Agent sie angelegt, trägt sie ein Event-Datum?
4. `Uebersetzung:`-Zeile: >0 übersetzt, englische dabei?
5. `stats.promo_*`: Extraktion gelaufen, `last_verified` bewegt sich?
6. Titelseite ansehen: führt die höchste Priorität, sind die EE-artigen
   Dubletten gebündelt?

## 5. Umsetzung

Fünf Arbeitspakete (P0=E1–E3, P1=E4, P2=E6–E8, P3=E5, P4=E9–E10), jeweils
mit Tests, die gegen den alten Stand durchfallen; volle Suite + Portal-Check
am Ende; Branch `claude/highlight-pages-system-43s1d3`.

## 6. Stand der Umsetzung & offene Entscheidungen (Stand 27.08., wird nachgeführt)

**Läuft gerade in der Session vom 27.08.:** Workflow über P0–P4 →
Integration (volle Testsuite) → adversarisches Review, danach ein
Revisionspaket (E1: Vorsortierung + Batch 24 statt Modellwechsel; E3:
Zähler warnt nur, kappt nie), dann geprüfter Push auf den Branch. **Wer
diese Strategie in einer neuen Session aufnimmt: zuerst den Branch-Stand
und dieses Kapitel lesen — NICHT bei null anfangen.** Ist der Branch noch
ohne Code-Commits, ist die Umsetzung abgebrochen worden und dieses Dokument
ist die Startgrundlage.

**Nur diese zwei Entscheidungen stehen aus, beide bei Antonio:**
1. **DeepSeek-Guthaben auffüllen** und auf der DeepSeek-Usage-Seite klären,
   wohin die Aufladungen seit dem 15.08. geflossen sind (teilt sich jemand
   den Key?). Ohne Guthaben trägt der Anthropic-Anker den ganzen Lauf —
   funktional in Ordnung, aber auf Antonios Anthropic-Key.
2. **Kostenrahmen bestätigen:** ~1,3–1,6 $ je Lauf (~11–13 $/Monat) mit pro
   überall. Alternativen auf Ansage: Bereichsredakteure auf flash
   (−0,3–0,4 $) oder Umfangsdeckel je Lauf.

**Bewusst offen für einen SPÄTEREN Auftrag:** Quellenausbau
Consumer-Fachpresse (B7 nennt die Richtung; braucht Netz-Massenläufe über
`scripts/pruefe_quellenvorschlag.py`).
