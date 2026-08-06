# Plan: Die Marktrecherche wird ein Nachrichtenportal

**Auftrag für die nächste Session.** Stand 06.08.2026, Session 6.
Grundlage: fünf Internet-Recherchen (`outputs/recherche-*.md`) und eigene
Messungen an den echten Daten (`outputs/befunde-eigenmessung.md`).

---

## 0. Der Auftrag in Antonios Worten

> „Ich möchte es wirklich so haben wie ein Nachrichtenportal — Wall Street
> Journal, Spiegel, FAZ. Momentan ist das nicht intuitiv, es ist schwer zu
> lesen. Man muss einiges an kognitivem Aufwand leisten, bevor man überhaupt
> weiß, worum es in dem Artikel geht. Und das ist scheiße. Die
> Nachrichtenportale zeigen Bilder, man wird aufmerksam, man kann sich
> vorstellen, worum es geht, man liest die Überschrift, bam."

Dazu: temporäre Themenseiten für große Ereignisse (Samsung-/Apple-Launch),
die automatisch entstehen und wieder verschwinden. Der Prosa-Wochenbericht
bleibt, nur besser dargestellt.

---

## 0b. Getroffene Entscheidungen (06.08.2026, von Antonio)

Zwei Fragen standen offen, beide sind beantwortet. Sie gelten als gesetzt und
müssen in der nächsten Session nicht neu aufgemacht werden.

**Bilder: Hybrid.** Das eigene Cover-System wird gebaut (Logo →
typografisches Cover → generatives Muster, alles SVG, 100 % Abdeckung), und
darüber kommt der externe Bildkanal: echte Artikelbilder werden **live von
der Quelle geladen, nie heruntergeladen, nie ins Repo committet**. Jedes
externe Bild trägt eine Bildunterschrift mit Quellenname und Link,
`referrerpolicy="no-referrer"`, `loading="lazy"` und eine `onerror`-Kaskade
auf das eigene Cover. Der Schalter `bilder_modus` in `settings.yaml` bleibt
trotzdem verpflichtend — er ist die Rückfalloption, falls jemand im Haus
später anders entscheidet. Kapitel 3 gilt damit unverändert, nur ist Stufe 3b
nicht mehr optional.

**Umfang: Stufen 1 bis 4 am Stück.** Titelei, Ressorts, Cover-System und das
komplette neue Layout werden als ein Vorhaben umgesetzt, über mehrere
Sessions verteilt, statt in kleinen sichtbaren Schritten. Rund 6–8 Tage.
Konsequenz für die Arbeitsweise: Zwischenstände gehen trotzdem nach jedem
abgeschlossenen Teilschritt auf den Branch, damit ein Sessionabbruch nichts
kostet — nur die Live-Seite wechselt erst am Ende auf das neue Layout.

Reihenfolge innerhalb des Blocks bleibt wie in Kapitel 13: erst 1 und 2
(Textebene, ohne die alles andere wirkungslos ist), dann 3/3b (Bilder), dann
4 (Layout). Stufe 7 (Berichts-Schliff) läuft mit Stufe 1 mit, weil sie
denselben Prompt anfasst.

---

## 1. Diagnose: drei Ursachen, und nur eine davon ist Layout

Das Problem sitzt nicht dort, wo es weh tut. Gemessen im Code:

**Ursache 1 — es gibt gar keine Überschriften.** `report/html.py:162`:

```python
h["de_title"] = _first_sentence(h.get("summary") or "", 150) or h.get("title") or ""
```

Das, was auf der Seite überall als Überschrift steht, ist der erste Satz der
Analysten-Zusammenfassung, hart bei 150 Zeichen abgeschnitten. Der Analyst
(`analyze/agents.py`) liefert `title` (Originaltitel, meist Englisch),
`summary` (1–2 Sätze Deutsch) und `why_it_matters` — **kein Feld für eine
deutsche Schlagzeile**. Beispiel aus dem Lauf vom 05.08.:

> „Der britische Glasfaser-Anbieter Hey! Broadband bringt drei neue
> 900-Megabit-pro-Sekunde-Bündel auf den Markt, alle mit den ersten sechs
> Monaten zum halben Preis."

Korrekter Satz, unbrauchbare Schlagzeile: 30 Wörter, das Subjekt versteckt
hinter zwei Attributen. Genau hier entsteht der kognitive Aufwand. Die
Eye-Tracking-Forschung erklärt, warum das besonders teuer ist: beim Scannen
einer Überschriftenliste wird nur die **linke Hälfte** gelesen (F-Pattern,
NN/g), die ersten drei bis vier Wörter müssen die Aussage tragen. Bei diesem
Satz tragen die ersten vier Wörter „Der britische Glasfaser-Anbieter Hey!" —
also nichts.

**Ursache 2 — es gibt keinen visuellen Anker.** Die Seite hat null Bilder,
null Logos, null Farbcodierung je Ressort. Jede Meldung sieht aus wie jede
andere.

**Ursache 3 — die Darstellung ist ein Dashboard, kein Blatt.** Die Startseite
(`uebersicht.html.j2`) ist ein Bento-Raster aus Lead-Kachel, vier
KPI-Kacheln, Balkendiagrammen und Mini-Panels. Ein Karten-Grid kodiert
Wichtigkeit über genau ein Signal: die Position in der Liste. Ein
Nachrichtenportal kodiert sie über vier gleichzeitig — Fläche, Position,
Schriftgrad, Weißraum. Die Redaktion trifft dort die Auswahl, damit der Leser
sie nicht treffen muss.

**Ein Redesign, das nur bei Ursache 3 ansetzt, wird das Problem nicht lösen.**
Deshalb ist der Plan unten so sortiert: Text zuerst, dann Bild, dann Layout.

---

## 2. Ein Befund, der der Wunschvorstellung widerspricht

Antonios Modell ist: erst fällt das Bild auf, dann liest man die Überschrift.
Das stimmt für **Print**. Für Nachrichten-Websites ist es umgekehrt belegt:
Poynters Eyetrack III fand, dass online der **Text zuerst** den Blick zieht,
Bilder erst danach. Und der Picture-Superiority-Effekt gilt laut NN/g nur für
**konkrete, unterscheidbare, informationstragende** Bilder — generische
Stockfotos werden aktiv ignoriert und sind messbar schlechter als gar kein
Bild.

Das entwertet den Wunsch nicht, es präzisiert ihn: Bilder helfen bei der
**Kategorisierung** („worum geht's grob") und beim Aufbau von
Wiedererkennung, nicht als Ersatz für eine gute Schlagzeile. Das WSJ-Gefühl
entsteht aus **Bild plus Schlagzeile plus Vorspann als Einheit** — und die
Schlagzeile ist der Teil, der bei uns komplett fehlt. Der Plan liefert
beides, aber in dieser Reihenfolge.

---

## 3. Die Entscheidung, die vor dem ersten Commit fällt: Bilder

Hier gehen Wunsch und Recherche auseinander, deshalb steht das vorne.

### Was gemessen wurde (eigene Messung an echten Meldungen)

| Frage | Ergebnis |
|---|---|
| Liefert der RSS-Feed selbst ein Bild? | nur **8 von 39** Feeds zuverlässig (`media:content`/`enclosure`) |
| Liefert die Artikelseite ein `og:image`? | **66–73 %** über 149 Abrufe |
| Sind diese Bilder artikelspezifisch oder immer dasselbe Share-Bild? | **18 von 19** Quellen liefern je Artikel ein anderes Bild |
| Wo die Artikelabrufe scheitern (403), gibt es einen Ersatz? | ja — Telecoms.com 100 %, Light Reading 70 % Bild im Feed. Die beiden Wege ergänzen sich fast perfekt |

Technisch ist echtes Bildmaterial also verfügbar, und zwar in guter Qualität.

### Was die Rechtsrecherche sagt

Zusammengefasst aus `outputs/recherche-bilder.md` (Laien-Synthese, keine
Rechtsberatung):

- **Kopieren auf den eigenen Server ist der riskante Fall.** EuGH
  Córdoba/Renckhoff (C-161/17): ein frei zugängliches Foto herunterzuladen
  und neu hochzuladen ist eine neue Wiedergabehandlung und braucht neue
  Zustimmung. Ein Bild-Cache im Git-Repo ist exakt dieser Fall.
- **Einbetten vom Originalserver ist der mildere Fall.** EuGH BestWater
  (C-348/13): Framing/Embedding eines vom Rechteinhaber selbst frei ins Netz
  gestellten Werks ist in der Regel keine neue öffentliche Wiedergabe. Nicht
  risikofrei (LG München I hat Hotlinking anders gewertet), aber deutlich
  besser gestellt.
- **Zusatzebene Leistungsschutzrecht** (§§ 87f ff. UrhG / DSM Art. 15): es
  schützt ausdrücklich auch Bilder in Presseveröffentlichungen und wurde
  gegen News-Aggregatoren geschaffen.
- **Und ein Befund, der unabhängig von Bildern gilt:**
  `telco-radar.onrender.com` ist **öffentlich erreichbar**, ohne Login, mit
  Vodafone-Branding und Wettbewerbsanalysen darauf. `noindex` verhindert nur
  die Google-Indexierung, nicht den Zugriff. Das ist ein eigener Punkt, siehe
  Kapitel 12.

### Empfehlung: das Ausweichsystem zuerst bauen, das Fremdbild als Schalter

```
bilder_modus: "eigen"      # nur selbst erzeugte Cover — null Risiko
bilder_modus: "extern"     # zusätzlich og:image, per Hotlink, nie kopiert
```

Die Reihenfolge ist der Kern der Empfehlung:

1. **Zuerst** die vollständige, selbst erzeugte Fallback-Kette bauen (Logo →
   typografisches Cover → deterministisches Muster). Sie deckt **100 %** ab,
   kostet nichts, wächst das Repo nicht, hat keine toten Links und kein
   Rechtsrisiko. Die Seite funktioniert damit allein vollständig.
2. **Danach** den externen Bildkanal als eine Schicht darüber, aktivierbar
   über eine Zeile in `settings.yaml`: `og:image` wird beim Sammeln nur als
   **URL** erfasst und im Browser direkt von der Quelle geladen — nie
   heruntergeladen, nie ins Repo committet.

Damit ist die rechtliche Entscheidung eine Konfigurationszeile und kein
Umbau. Wenn Vodafone-Recht sagt „kein Fremdbild", bleibt eine vollständige,
gut aussehende Seite übrig. Wenn es „ok mit Quellenangabe" sagt, sieht sie
aus wie das WSJ.

Auflagen für den `extern`-Modus, alle im Code umzusetzen:
Bildunterschrift mit Quellenname **und** Link (ist ohnehin Antonios
Nachprüfbarkeits-Anforderung), Thumbnail-Größe statt Vollbild,
`referrerpolicy="no-referrer"`, `loading="lazy"`, `onerror`-Kaskade auf das
eigene Cover, `noindex` bleibt, und eine Notiz im Protokoll, wie viele Bilder
extern geladen wurden.

Was **nicht** empfohlen wird: KI-generierte Bilder. AP, Reuters und dpa
schließen KI-Bilder für reale Ereignisse aus — und reale Ereignisse sind bei
uns der Normalfall, nicht die Ausnahme.

**→ Diese Entscheidung braucht Antonios Ja, bevor Stufe 3 gebaut wird.**
Alles davor (Stufen 1 und 2) ist davon unabhängig.

---

## 4. Zielbild: wie die Seite aussehen soll

Vier Hierarchiestufen, wie bei jedem echten Portal — Aufmacher,
Zweitplatzierung, Ressortmodule, Liste:

```
┌────────────────────────────────────────────────────────────────────┐
│ KOPF   Vodafone Insights · Marktrecherche · Ausgabe 6. August 2026 │
│ RESSORTLEISTE  Bericht · Europa · Nordamerika · Asien · … · Themen │
├────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────┐  ┌──────────────────────────┐ │
│ │ AUFMACHER                        │  │ ZWEITPLATZIERUNG (2–3)   │ │
│ │ [Bild / Cover, 16:9]             │  │ ┌──────┐ Dachzeile       │ │
│ │ Dachzeile: EUROPA · NETZAUSBAU   │  │ │ Bild │ Schlagzeile     │ │
│ │ SCHLAGZEILE, groß, 1 Zeile       │  │ └──────┘ Dek, 1 Zeile    │ │
│ │ Dek: ein Satz, was passiert ist  │  │ ──────────────────────── │ │
│ │ Quelle · vor 2 Tagen · ●●●●●     │  │ … 2 weitere              │ │
│ └──────────────────────────────────┘  └──────────────────────────┘ │
├────────────────────────────────────────────────────────────────────┤
│ DER WOCHENBERICHT (Prosa, das Herzstück, max-width 68ch)            │
│  Auf einen Blick → Das Wichtigste → Die wichtigsten Signale →       │
│  Regionen → Themenfelder → Muster der Woche                        │
├────────────────────────────────────────────────────────────────────┤
│ RESSORTMODULE — je Region/Themenfeld ein Block mit Farbakzent       │
│  EUROPA ▌   NORDAMERIKA ▌   ASIEN ▌   …                            │
│  je 3–5 Zeilen: Dachzeile + Schlagzeile + Datum, kein Bildzwang     │
├────────────────────────────────────────────────────────────────────┤
│ THEMENSEITEN (falls aktive Ereignisse) — siehe Kapitel 10           │
├────────────────────────────────────────────────────────────────────┤
│ EINORDNUNG  kompakte Charts, klein, mit je einem erklärenden Satz   │
├────────────────────────────────────────────────────────────────────┤
│ ALLE MELDUNGEN  Explorer/Suche — Werkzeugzone, klar abgesetzt       │
└────────────────────────────────────────────────────────────────────┘
```

Mobil: dieselbe Reihenfolge einspaltig, die Zweitplatzierungen wandern unter
den Aufmacher (redaktionelle, nicht räumliche Reihenfolge).

Zwei Regeln, die das Ganze zusammenhalten:

- **Größe wirkt nur, wenn sie selten ist.** Genau ein Aufmacher, zwei bis
  drei Zweitplatzierungen. Alles andere ist Liste.
- **Ein Struktur-Muster gilt für jede Meldung oder für keine.** Die Kritik an
  Axios ist genau die: ein Gliederungsschema, das nur manchmal angewendet
  wird, wirkt dekorativ statt funktional.

---

## 5. Stufe 1 — Die Meldung bekommt eine Titelei

**Das ist die wichtigste Änderung des ganzen Umbaus.** Ohne sie bringt jedes
Layout nichts.

### Neue Felder im Analysten-Schema

`analyze/agents.py`, beide Prompts (`ANALYST_SYSTEM` und
`TECH_ANALYST_SYSTEM`), bekommen zusätzlich:

| Feld | Inhalt | max. Zeichen |
|---|---|---|
| `dachzeile` | sachliche Einordnung: Region oder Thema plus Stichwort, z. B. „Großbritannien · Glasfaser" | 30 |
| `schlagzeile` | deutsche Schlagzeile: Subjekt zuerst, Aktiv, Präsens, Zahl wenn vorhanden | 70 |
| `dek` | ein ergänzender Satz, der die Schlagzeile NICHT wiederholt | 160 |
| `summary` | bleibt: „Was ist passiert", Faktenkern | 280 |
| `why_it_matters` | bleibt: „Warum es zählt" | 320 |

Für das Beispiel oben hieße das:

> **GROSSBRITANNIEN · GLASFASER**
> **Hey! Broadband halbiert den Preis für sechs Monate**
> Der Anbieter startet drei Gigabit-Tarife mit 50 Prozent Rabatt im ersten
> Halbjahr — direkt in Vodafones Ausbaugebieten.

Das ist derselbe Inhalt, in 0,8 Sekunden statt in fünf erfassbar.

### Die Regeln kommen aus der Recherche, nicht aus dem Bauch

`outputs/recherche-schreibstil.md`, Abschnitt 2, enthält einen fertig
formulierten deutschen Prompt-Baustein (Überschriften / Dachzeile+Dek /
Meldungstext / Wochenbericht) samt Verbotsliste für Floskeln. Der wird
übernommen, nicht neu erfunden. `outputs/recherche-psychologie.md`,
Abschnitt 10, ergänzt die Scan-Regeln (erste vier Wörter tragen die Aussage,
kein Curiosity Gap, keine Bandwurm-Komposita).

### Maschinelle Abnahme

Neues Skript `scripts/pruefe_schreibstil.py` nach dem Muster von
`pruefe_quellenvorschlag.py` — im Projekt gilt die Regel „ein Modell, das
sagt, es habe geprüft, zählt nicht". Es prüft nach dem EDIT-Schritt:
Zeichenobergrenzen je Baustein, kein `!`/`?` in Schlagzeilen, kein finites
Verb am Anfang, Floskel-Regex, mittlere Satzlänge unter 20 Wörtern,
Wiener Sachtextformel (`textstat`) im Korridor Schulstufe 8–10, und ob das
Dek die Schlagzeile bloß wiederholt. Verstöße wandern als Warnung ins
Laufprotokoll, sie brechen den Lauf nicht ab.

### Rückwärtskompatibilität

Die zwölf bestehenden Berichte in `data/reports/*.json` haben diese Felder
nicht. `_flatten()` in `report/html.py` muss deshalb weiterhin auf die alte
Ableitung zurückfallen, wenn `schlagzeile` fehlt — das Archiv darf nicht
kaputtgehen.

### Aufwand
Rund ein Tag: Prompts, Schema-Durchreichung, `_flatten()`, Prüfskript, ein
`--no-llm`-Testlauf plus ein echter Lauf zur Kontrolle.

---

## 6. Stufe 2 — Ressorts, die tatsächlich gefüllt sind

Ein Nachrichtenportal mit Ressortmodulen braucht funktionierende Ressorts. Im
Lauf vom 05.08. bekam **Europa null bewertete Meldungen**, „Global" 62 von 92.

Ursache, verifiziert in `collect/__init__.py:220`: `tag_news_regions()`
ordnet eine Fachpresse-Meldung nur dann einer Region zu, wenn ein
Watchlist-Betreibername **in der Überschrift** steht. Ein Artikel von
teltarif über Congstar bleibt „global".

Fix, klein und längst überfällig (steht als offener Punkt 1 in `CLAUDE.md`):
`config/news_sources.yaml` bekommt ein optionales Feld `region:` je Quelle
(aktuell gibt es dort nur `name`, `type`, `url`, `herkunft`, `abgenommen`).
Der Loader in `config.py` reicht es durch, `tag_news_regions()` benutzt es
als Vorgabe und lässt den Betreiber-Treffer weiterhin gewinnen. Die 19
regionalen Feeds aus Session 5 (deutsch, französisch, spanisch, italienisch,
portugiesisch, Indien, Asien, Afrika) landen dann dort, wo sie hingehören.

**Aufwand: ein halber Tag.** Ohne diesen Fix hat das neue Layout leere
Ressortblöcke — und leere Ressorts sehen schlimmer aus als gar keine.

---

## 7. Stufe 3 — Visuelle Anker

### Die Fallback-Kette

```
0. og:image der Meldung          (nur wenn bilder_modus == "extern")
1. Logo des genannten Betreibers auf Ressort-Farbfläche
2. Typografisches Cover: Dachzeile klein + Kernbegriff groß auf Farbfläche
3. Deterministisches Muster aus hash(item.id)   ← garantiert 100 %
```

Schritt 1–3 werden als **SVG serverseitig erzeugt**, nicht als Rasterbild.
Das ist der Punkt, an dem das Repo-Wachstum entschieden wird: 87 Logos à
2–5 KB sind unter 500 KB, während gecachte Rasterbilder bei ~100 KB × 60
Meldungen × 2 Läufen/Woche auf **rund 600 MB im Jahr** hinauslaufen würden —
bei aktuell 8,6 MB `.git`. Regel für den Umbau: **niemals Rasterbilder
committen.**

### Was schon existiert und nur übertragen werden muss

Die Bild-Infrastruktur ist für den Promo-Anwendungsfall bereits gebaut:

- `collect/promo_snapshot.py::extract_hero_image()` — og:image/twitter:image
  mit Prioritätsliste, getestet
- `promo_images.py` — Slugs, Cache-Pfade
- `report/promo.py` + `promo_index.html.j2` — Karte mit Bild und
  Farbkachel-Fallback

Für die Marktrecherche wird das übernommen, nicht neu geschrieben.

### Logo-Bestand

Einmalig aufbauen, danach nur Pflege: Simple Icons (CC0) für die großen
Marken, Wikidata-Property P154 für den Rest, Google-Favicon-Dienst als
Nothelfer. Ablage `assets/logos/<slug>.svg`, Zuordnung über den
Betreiber-Slug aus der Watchlist. Rechtlich der unkritischste Baustein:
redaktionelle Nennung einer Firma mit ihrem Logo.

### Validierung beim Sammeln

Ein `og:image`-Kandidat wird nur akzeptiert nach HEAD-Prüfung
(`Content-Type: image/*`, größer als 1 KB) **und** nach dem
Wiederholungstest: liefert dieselbe Quelle für mehrere Meldungen dieselbe
Bild-URL, ist es eine generische Share-Grafik und wird verworfen. Das ist
kein theoretisches Risiko — NTT (`sns_share.png`) und Charter
(`Spectrum Logo_Social Share.jpg`) tun in der Messung genau das.

**Aufwand: 1 Tag Cover-System, 0,5 Tag Muster, 2–3 Tage Logo-Bestand,
1–2 Tage externer Bildkanal.**

---

## 8. Stufe 4 — Das neue Layout

Erst jetzt CSS und Templates.

### Templates

| Datei | Änderung |
|---|---|
| `templates/uebersicht.html.j2` | wird zur **Titelseite**: Aufmacher + Zweitplatzierungen + Bericht-Anriss + Ressortmodule. Das Bento-Raster fällt weg |
| `templates/report.html.j2` | Aufmacher-Block, Prosa auf 68ch, Ressortmodule, Charts nach unten, Explorer als klar abgesetzte Werkzeugzone |
| `templates/_meldung.html.j2` | **neu**: ein Makro für die Meldungs-Titelei in drei Größen (Aufmacher / Zweit / Zeile), damit das Muster überall identisch ist |
| `templates/style.css` | vier Schriftgrad-Stufen statt einer, Ressort-Farbakzente, Grid mit ungleichen Zellen |
| `templates/base.html.j2` | Ressortleiste; **Google-Fonts-Einbindung entfernen** (siehe Kapitel 12) |

### Typografie

Vier klar unterscheidbare Stufen: Aufmacher-Schlagzeile / Zweit-Schlagzeile
(60–75 %) / Modul-Schlagzeile (45–55 %) / Fließtext. Serif für große
Schlagzeilen ist branchenüblich (NYT Cheltenham, Guardian Egyptian) und
signalisiert Autorität — für den Fließtext bleibt Sans. Fließtext auf
`max-width: 68ch`, Zeilenhöhe 1,5.

Beim Theme bleibt es beim hellen Hintergrund: die Polaritätsforschung zeigt
einen messbaren Lesegeschwindigkeitsnachteil bei dunklem Grund, und der
mehrminütige Prosabericht ist genau der Fall, in dem das zählt. (Die
Beschreibung „Dark-Theme, Bloomberg-Terminal-Stil" in `CLAUDE.md` Abschnitt 5
ist ohnehin veraltet — die Seite ist längst hell mit Cream-Canvas.)

### Farbe statt Badge

Guardian-Muster: eine Akzentfarbe je Region/Themenfeld, konsequent im Kicker
und als linker Rand des Moduls. Keine Ansammlung bunter Badges. Die
Dringlichkeit bleibt sichtbar, aber **nie über Farbe allein** — Farbe plus
Zahl plus Text, wegen Rot-Grün-Sehschwäche.

### Was aus dem Weg geräumt wird

Der Explorer steckt heute in einem zugeklappten `<details>` mit der
Beschriftung „bei Bedarf öffnen". Er wird eine eigene, sichtbare Zone am
Seitenende — als Werkzeug, nicht als zweite Startseite.

**Aufwand: 2–3 Tage.**

---

## 9. Stufe 5 — Eine Meldung braucht ein Zuhause

Heute verlinkt jede Meldung direkt nach extern (`target="_blank"`). Damit hat
jede Meldung genau eine mögliche Interaktion: weg von der Seite. Ein
Nachrichtenportal braucht eine Stufe dazwischen.

Vorschlag: eine **Detailansicht ohne eigene Datei** — Klick auf eine Meldung
öffnet ein Panel mit Dachzeile, Schlagzeile, Dek, „Was ist passiert",
„Warum es zählt", Quelle, Datum, verwandten Meldungen derselben Story. Der
Explorer hat diese Split-View-Mechanik bereits (`app.js`), sie muss nur von
der ganzen Seite aus erreichbar sein und eine URL bekommen
(`#meldung-<id>`), damit man sie teilen kann.

Echte statische Einzelseiten je Meldung (`site/meldungen/<id>.html`) wären
die Alternative, kosten aber bei ~100 Meldungen pro Lauf schnell tausende
Dateien im Repo. **Empfehlung: Panel mit Anker-URL, keine Einzeldateien.**

**Aufwand: 1 Tag.**

---

## 10. Stufe 6 — Temporäre Themenseiten

Antonios Wunsch: Wenn ein großes Thema läuft — Samsung Unpacked, ein
Apple-Launch, ein Übernahmepoker — soll das automatisch erkannt werden, eine
eigene Unterseite mit allen Meldungen dazu entstehen, und wenn es vorbei ist,
verschwindet sie wieder.

Das ist machbar. Aber die Reihenfolge der Arbeit steht und fällt mit einem
Befund aus den echten Daten, der der Recherche-Empfehlung widerspricht.

### 10.1 Der Befund, der die Kalibrierung ändert

Die Recherche empfiehlt als Schwelle **≥5 bewertete Meldungen und ≥3
unabhängige Quell-Domains** im Zeitfenster. Ich habe das gegen die letzten
zwölf Berichte gerechnet. Ergebnis:

| Lauf | stärkster Kandidat | Meldungen | Quellen |
|---|---|---|---|
| 05.08. | Amazon (Leo/D2D-Antrag) | 4 | 4 |
| 05.08. | Free | 5 | 1 |
| 04.08. | SoftBank | 4 | 2 |
| 31.07. | Openreach | 3 | 3 |

**Mit der empfohlenen Schwelle hätte es in zwölf Läufen keine einzige
Themenseite gegeben.** Und ein zweiter Befund dazu: von 110 Themen, die in
irgendeinem Lauf mindestens zwei Meldungen hatten, waren **91 nur in genau
einem Lauf aktiv**. Themen, die sich über mehrere Läufe halten, heißen
Vodafone, Ericsson, Verizon, Airtel — also genau die Dauerbrenner, die
niemals eine Ereignisseite werden dürfen.

Der Grund ist nicht, dass es keine Ereignisse gibt. Der Grund ist die
**Bemessungsgrundlage**: Die Erkennung würde auf den 35–92 *bewerteten*
Meldungen laufen. Neu gesammelt werden aber 124–426 pro Lauf. Der Analyst
wirft drei Viertel weg, bevor irgendeine Häufung sichtbar werden kann — und
er wirft je Region getrennt weg, also genau quer zu einer Story, die sich
über mehrere Regionen zieht.

### 10.2 Die Voraussetzung, die vorher gebaut werden muss

**Die Ereigniserkennung muss auf der Ebene der NEUEN Meldungen laufen, nicht
auf den bewerteten.** Und dafür fehlt heute die Datenhaltung: Der Seen-Store
wurde in Session 5 auf das kompakte v2-Format umgestellt — **ein Hash je
Zeile, keine Titel, keine URLs, keine Quellen**:

```
# telco-radar seen-store v2 - ein Item-Hash je Zeile
@2026-07-17T12:20:46.955689+00:00
7a0a90bd7dba14dd
```

Es gibt im ganzen Projekt keinen Ort, an dem die gesammelten Meldungen mit
Titel über einen Lauf hinaus liegen. Ein Thema über drei Läufe zu verfolgen
ist damit heute **technisch unmöglich**.

Also zuerst: **ein rollierender Meldungsspeicher.**
`data/state/meldungen_fenster.jsonl` — je Zeile eine gesammelte Meldung mit
`id`, `titel`, `url`, `quelle`, `quelle_domain`, `datum`, `region`,
`bewertet` (ja/nein), `lauf`. Aufbewahrung 21 Tage, danach wird abgeschnitten.
Größenordnung: ~300 Meldungen × 2 Läufe/Woche × 3 Wochen ≈ 1800 Zeilen à
~250 Byte ≈ **450 KB**, rollierend, kein Wachstum. Das ist derselbe
Kompromiss, den `promo_db.json` (275 KB) schon fährt.

Der Seen-Store bleibt unangetastet — er macht die Delta-Erkennung, der neue
Speicher macht die Story-Erkennung. Zwei Aufgaben, zwei Dateien.

### 10.3 Erkennung: der Vorschlag, kalibriert

Zweistufig, wie in `outputs/recherche-eventseiten.md` empfohlen — die
Architektur der Empfehlung ist richtig, nur die Zahlen müssen an unsere
Datenlage:

**Schritt 1, mechanisch, kein LLM.** Über alle Meldungen der letzten drei
Läufe aus dem neuen Fensterspeicher:

- Kandidatenschlüssel über Titel-Wortüberlappung (normalisiert, Stoppwörter
  raus, Jaccard) plus bekannte Akteursnamen — das ist NewsBlurs Verfahren,
  das produktiv ohne Embeddings auskommt.
- **Schwelle (angepasst): ≥3 Meldungen UND ≥2 unabhängige Domains.** Nicht
  5/3. Gegen die gemessene Datenlage hätte 5/3 nie ausgelöst.
- **Relative Schwelle gegen Dauerbrenner:** Trefferdichte mindestens
  3× über dem 90-Tage-Schnitt desselben Begriffs. Ohne Historie greift nur
  die absolute Schwelle. Das ist das Prinzip „Geschwindigkeit statt Volumen",
  und es ist an unseren Daten belegt notwendig — sonst wird „Vodafone"
  (6 von 12 Läufen aktiv) zur Dauer-Ereignisseite.
- **Sperrliste** generischer Begriffe (`5G`, `6G`, `Glasfaser`, `KI`,
  `Netzausbau`, `Launch`, `Network`, `Broadband`, `Data`). In meiner Messung
  waren die Top-Kandidaten mehrerer Läufe genau solche Wörter — ohne
  Sperrliste besteht die erste Themenseite aus dem Wort „Launch".

**Schritt 2, ein LLM-Aufruf pro Lauf** (nicht pro Kandidat). Er bekommt alle
Kandidaten mit ihren Meldungen, dazu die Liste der bereits aktiven Stories,
und entscheidet je Kandidat: bestätigt ja/nein, Konfidenz, Titel, Kategorie,
Kurzfassung, `merge_mit` (bestehende Story fortsetzen statt neue anlegen),
beteiligte Akteure. Unter Konfidenz 0,6 wird nichts veröffentlicht — die
Story bleibt „entstehend" und wird im nächsten Lauf erneut geprüft. Das ist
dieselbe Haltung, die das Projekt bei Quellen fährt: „nicht sicher genug"
ist kein PASS.

Kosten: ein zusätzlicher Aufruf je Lauf, im Rahmen der bestehenden
1,45 $/Monat nicht messbar.

**Ereigniskalender als Vorwissen.** Eine kleine, handgepflegte
`config/ereignis_kalender.yaml` (MWC, IFA, CES, Apple-Keynote, Samsung
Unpacked) — eine gemeinsame maschinenlesbare Quelle dafür existiert nicht,
die Recherche hat gezielt danach gesucht. Im Fenster ±5 Tage um einen Termin
sinkt die Schwelle auf 2 Meldungen / 2 Quellen. **Ein Kalendereintrag allein
erzeugt nie eine Seite** — er senkt nur die Hürde. Genau für Antonios
Beispiel (Samsung-Launch) ist das der Mechanismus, der die Seite schon am
ersten Tag entstehen lässt statt drei Tage später.

### 10.4 Lebenszyklus

```
entstehend → aktiv → abklingend → archiviert
        ↘ verworfen ↙
```

| Zustand | Bedingung | Sichtbar |
|---|---|---|
| entstehend | Schwelle in einem Lauf erreicht, oder Kalenderanker | nein |
| aktiv | LLM bestätigt (≥0,6) und zweiter Lauf über Schwelle oder Kalenderanker | eigene Seite, in Navigation und auf der Titelseite |
| abklingend | 0–1 neue Meldungen im aktuellen Lauf | Seite bleibt, Hinweis „abklingend", raus von der Titelseite |
| archiviert | zwei Läufe in Folge ohne neue Meldung (≈1 Woche) | Seite bleibt unter derselben URL, eingefroren, Banner „Thema abgeschlossen", nur noch über das Archiv erreichbar |
| verworfen | LLM bestätigt über zwei Läufe nicht | nie sichtbar, nur im Protokoll |

**Die Seite verschwindet nie wirklich — sie friert ein.** Das ist die
Antwort auf „wenn der Launch vorbei ist, geht es weg": aus der Navigation
weg, aus der Titelseite weg, aber die URL bleibt für immer gültig. Alles
andere erzeugt tote Links in alten Wochenberichten, die auf die Story
verweisen. Vorbild sind die „Living Stories" von Google/NYT/Washington Post
(2009) — 75 % der Testnutzer bevorzugten dieses Format gegenüber
Artikellisten; das Projekt scheiterte am Werbemodell, das wir nicht haben.

### 10.5 Aufbau der Themenseite

`site/themen/<story_id>.html`, gebaut aus denselben Bausteinen wie der Rest
— **keine zweite Designsprache**:

1. Statuszeile: „Aktiv · seit 15. Januar · 14 Meldungen aus 6 Quellen ·
   zuletzt aktualisiert vor 2 Tagen"
2. „Was bisher geschah" — die LLM-Kurzfassung, drei Sätze, wird nur bei
   Statuswechsel neu geschrieben, nicht bei jedem Lauf
3. Zeitleiste aller Meldungen, neueste zuerst, in der Meldungs-Titelei aus
   Stufe 1 (Dachzeile/Schlagzeile/Dek)
4. Beteiligte Akteure als Chips
5. kleines Chart: Meldungen je Lauf (zeigt Auf- und Abschwung)
6. Quellenliste
7. Rückverweise auf die Wochenberichte, in denen das Thema vorkam

Auf der Titelseite erscheinen aktive Stories als eigener Block zwischen
Wochenbericht und Ressortmodulen — nicht als Ticker, sondern als das, was
sie sind: zwei bis drei laufende Themen mit einer Zeile Erklärung.

### 10.6 Vor dem Bauen: nachmessen

Bevor eine Zeile Produktivcode entsteht, ein Skript nach dem Muster der
bestehenden Messskripte: **`scripts/miss_stories.py`** spielt das Archiv
(`data/reports/*.json`) durch und beantwortet: Wie viele Stories hätte
Schwelle X/Y in den letzten zwölf Läufen erzeugt? Welche? Wie lange hätten
sie gelebt? Die Schwelle wird an dieser Ausgabe kalibriert, nicht am Bauch —
so wie in diesem Projekt auch die Sammelphase und die Trefferquote gemessen
statt geschätzt werden.

Solange dieses Skript nicht sagt „in zwölf Läufen wären 3–6 sinnvolle Stories
entstanden", ist das Feature nicht reif. Ein System, das alle vier Wochen
eine Seite über das Wort „Launch" baut, ist schlechter als keines.

### 10.7 Risiken

- **Zu wenige Ereignisse.** Das wahrscheinlichste Scheitern, siehe 10.1.
  Gegenmittel: Erkennung auf den neuen statt den bewerteten Meldungen,
  Schwelle 3/2, Kalendervorwissen, und die Messung aus 10.6 als Torwächter.
- **Falsch-positive.** Doppel-Gate aus mechanischer Schwelle und
  LLM-Bestätigung, plus Konfidenzuntergrenze.
- **Themen spalten oder verschmelzen sich.** Deshalb bekommt das LLM die
  aktiven Stories mit in den Prompt und darf `merge_mit` setzen — die
  Entscheidung fällt inhaltlich, nicht über Wortüberlappung.
- **Laufzeit.** Ein zusätzlicher LLM-Aufruf und etwas Rechnerei auf 1800
  Zeilen. Gegenüber 24,8 Minuten Redaktionszeit im Lauf #75 irrelevant.

### 10.8 Aufwand

| Teil | Aufwand |
|---|---|
| Rollierender Meldungsspeicher (Voraussetzung) | 0,5 Tag |
| `scripts/miss_stories.py` + Kalibrierung | 1 Tag |
| Erkennung (Vorfilter + LLM-Schritt + `stories.json`) | 1,5–2 Tage |
| Themenseite + Titelseiten-Block + Archivierung | 1,5 Tage |
| Ereigniskalender | 1 Stunde |

**Zusammen 4,5–5 Tage** — der größte Einzelposten des ganzen Plans. Deshalb
steht er hinten: Stufen 1, 2 und 4 verbessern die Seite für jeden Leser bei
jedem Lauf, die Themenseiten greifen nur, wenn gerade etwas Großes läuft.

---

## 11. Stufe 7 — Der Wochenbericht selbst

Der Prosabericht bleibt das Herzstück, bekommt aber dieselbe Behandlung wie
die Meldungen:

- **Nut Graf**: 3–5 Sätze direkt unter der Ausgaben-Überschrift, vor allen
  Abschnitten — „worum geht es diese Woche", bevor irgendein Unterabschnitt
  beginnt.
- Zwischenüberschriften beginnen mit dem informationstragenden Wort, nicht
  mit „Außerdem" oder „Zudem" (Layer-Cake-Scanning).
- Jede Tatsachenbehauptung behält ihren Quellenlink — bestehende
  Anforderung, wird jetzt maschinell geprüft.
- Die Floskel-Verbotsliste aus `outputs/recherche-schreibstil.md` kommt in
  den Editor-Prompt.

**Achtung, Fallstrick aus `CLAUDE.md`:** Prompt und
`validate_editorial_briefing()` (`analyze/editor.py:295`) hängen am selben
Schalter. Die Pflichtüberschriften sind aktuell „Auf einen Blick", „Das
Wichtigste", „Die wichtigsten Signale", „Muster der Woche". Wer den einen
ändert, ändert den anderen mit — sonst weigert sich die Pipeline zu
publizieren.

**Aufwand: 0,5 Tage.**

---

## 12. Was mir sonst aufgefallen ist

Nicht Teil des Auftrags, aber gefunden und der Erwähnung wert:

**a) Die Seite ist öffentlich.** `telco-radar.onrender.com` ist ohne Login
erreichbar, trägt „Vodafone Insights" im Kopf und enthält
Wettbewerbsbewertungen samt Handlungsempfehlungen. `noindex` hält nur
Suchmaschinen fern, nicht Menschen mit der URL. Das ist unabhängig von der
Bildfrage eine Entscheidung, die jemand bewusst treffen sollte — spätestens
bevor die Kollegin die URL im Haus weiterreicht. Optionen: so lassen (mit dem
Wissen), Zugangsschutz davorschalten, oder die
Vodafone-Handlungsempfehlungen weiter ausdünnen (`_strip_vodafone_advice()`
tut das heute schon teilweise).

**b) Google Fonts wird von einem externen CDN geladen** (`base.html.j2:8-10`).
Drei Gründe dagegen: es widerspricht dem eigenen Grundsatz „kein CDN", es
blockiert das Rendern, und der Abruf von `fonts.googleapis.com` überträgt die
IP jedes Lesers an Google — bei einer Vodafone-Seite der Punkt, an dem
üblicherweise jemand nachfragt. Schriften gehören als WOFF2 ins Repo,
Aufwand eine Stunde.

**c) Die Sortierung ist rein nach Dringlichkeit.** `_flatten()` sortiert nach
`relevance`, dann Datum. Ein Nachrichtenportal gewichtet Wichtigkeit **und**
Aktualität. Vorschlag für die Titelseite: Aufmacher nach Dringlichkeit, die
Ressortmodule chronologisch — und, wie The Information es macht, zwei
Sortierungen anbieten statt einer erzwungenen.

**d) Der Explorer zeigt `why_it_matters` nicht.** `render_site()` entfernt
das Feld aus den öffentlichen Daten (`public_h.pop("why_it_matters")`). Das
ist eine bewusste Entscheidung gewesen — aber es heißt, dass die
interessanteste Zeile jeder Meldung nur im Prosabericht auftaucht. Beim
Redesign bewusst neu entscheiden.

**e) Ballast-Quellen.** Aus `CLAUDE.md`: 11 Quellen haben über 11 Läufe
mindestens 10 neue Meldungen geliefert, von denen **keine einzige** je
bewertet wurde (Iliad 40, stc 33, AIS 30, PLDT 21, Deutsche Telekom 19).
Weniger Rauschen heißt bessere Auswahl heißt bessere Titelseite. Gehört nicht
in dieses Redesign, aber in den nächsten Quellenlauf.

---

## 13. Reihenfolge, Aufwand, Abnahme

| # | Stufe | Aufwand | Abhängig von | Abnahmekriterium |
|---|---|---|---|---|
| 1 | Titelei je Meldung (Prompts + Schema) | 1 Tag | — | Ein echter Lauf liefert für jede Meldung Dachzeile ≤30, Schlagzeile ≤70, Dek ≤160; `pruefe_schreibstil.py` meldet keine harten Verstöße |
| 2 | Ressorts reparieren (`region:` je Fachpressequelle) | 0,5 Tag | — | Europa hat im nächsten Lauf mehr als null bewertete Meldungen |
| 3 | Eigene Cover (Logo/Typo/Muster, SVG) | 2–4 Tage | — | Jede Meldung hat ein Cover, kein Rasterbild im Repo, `.git` wächst um <1 MB |
| 3b | Externer Bildkanal (`bilder_modus: extern`) | 1–2 Tage | 3 (entschieden, s. Kap. 0b) | Bild kommt live von der Quelle, Bildunterschrift mit Link, Ausfall fällt sauber auf das Cover zurück |
| 4 | Neues Layout (Templates + CSS) | 2–3 Tage | 1, 2, 3 | Ein Fremder erkennt in unter 5 Sekunden die wichtigste Meldung der Woche |
| 5 | Detailansicht mit Anker-URL | 1 Tag | 4 | Jede Meldung ist per Link direkt ansteuerbar |
| 6a | Rollierender Meldungsspeicher + `miss_stories.py` | 1,5 Tage | — | Das Skript beziffert, wie viele Stories welche Schwelle im Archiv erzeugt hätte |
| 6b | Themenseiten (Erkennung + Seite + Lebenszyklus) | 3–3,5 Tage | 1, 4, 6a | In zwölf Archivläufen wären 3–6 sinnvolle Stories entstanden, keine Dauerbrenner darunter |
| 7 | Wochenbericht-Schliff | 0,5 Tag | 1 | Nut Graf vorhanden, Floskelcheck sauber, `validate_editorial_briefing` passt |
| 8 | Schriften lokal, Fonts-CDN raus | 1 Std. | — | Keine externe Anfrage beim Seitenaufruf |

Realistisch sind das **zwei bis drei Sessions**, nicht eine. Die sinnvolle
erste Session ist **1 + 2 + 7**: sie ist unabhängig von jeder Entscheidung,
kostet anderthalb Tage und behebt bereits die Hauptursache der Beschwerde —
danach steht in jeder Liste eine echte Schlagzeile statt eines
abgeschnittenen Satzes.

---

## 14. Was bewusst NICHT gemacht wird

- **Kein durchlaufender Live-Ticker.** Der Bericht erscheint zweimal die
  Woche; ein Breaking-News-Band würde Aktualität vortäuschen.
- **Keine „Meistgelesen"-Liste.** Es gibt keine Leserzahlen. Ein erfundenes
  Signal ist schlechter als keins — die vorhandene Dringlichkeit tut es.
- **Kein Bloomberg-Terminal-Look.** Bloomberg selbst hat den fürs Web
  verworfen („The Web Is Not A Terminal"). Gemeint war ohnehin die seriöse,
  datengetriebene Anmutung, nicht die harte Zweiton-Ästhetik.
- **Keine KI-generierten Bilder** zu realen Ereignissen.
- **Keine Einzeldateien je Meldung** im Repo.
- **Kein Badge-Overload.** Eine Akzentfarbe je Ressort, sonst nichts.
- **`scripts/build_sources.py` bleibt gesperrt** — es würde die Watchlist
  überschreiben und Felder verlieren.

---

## 15. Die Rechercheunterlagen

| Datei | Inhalt |
|---|---|
| `outputs/recherche-layout.md` | Informationsarchitektur, vier Hierarchiestufen, Grid-Systeme, benannte Patterns, Zonenskizze, „nicht machen"-Liste, 29 Quellen |
| `outputs/recherche-psychologie.md` | Eye-Tracking, F-Pattern, Bildwirkung, Cognitive Load, Anatomie eines Eintrags, LLM-Regelcheckliste, 23 Quellen |
| `outputs/recherche-bilder.md` | Bildbeschaffung, Rechtslage (BestWater/Córdoba/LSR), Fallback-Kette, Aufwandstabelle, 27 Quellen |
| `outputs/recherche-schreibstil.md` | Schlagzeilenhandwerk, deutsche Titelei, Smart Brevity/Semaform, **fertiger Prompt-Baustein**, 12 maschinelle Checks, 32 Quellen |
| `outputs/recherche-eventseiten.md` | Ereigniserkennung (Burst Detection, Clustering, LLM-nativ), Story-Datenmodell, Lebenszyklus, Living Stories, Ereigniskalender, 22 Quellen |
| `outputs/befunde-eigenmessung.md` | Alle eigenen Messungen an echten Daten und die Code-Befunde |
