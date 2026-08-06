# Recherche: Informationsarchitektur & Layout von Nachrichtenportalen
### Grundlage für das Redesign von Telco Radar (weg vom Karten-Grid, hin zum Nachrichtenportal)

Stand: 2026-08-06. Recherchiert für die Startseite/Wochenbericht-Ansicht von
Telco Radar (statisch generiert: Jinja2 → HTML, Vanilla JS, kein CDN).

---

## 0. Kernbefund vorab

Das aktuelle Problem — "wirkt wie ein Dashboard" — ist kein Geschmacksfehler,
sondern ein strukturelles Muster-Problem. Dashboards und Nachrichtenseiten
lösen unterschiedliche Aufgaben und kodieren Wichtigkeit unterschiedlich:

- **Dashboard** (der heutige Stand: Karten-Grid + Charts + Split-View-Explorer):
  alle Kacheln sind ungefähr gleich groß, gleich gewichtet, nebeneinander
  „zum Selbst-Explorieren". Wichtigkeit wird höchstens über Farbe/Badges codiert,
  nicht über Fläche. Das ist beim Aufbau einer Werkzeug-Oberfläche richtig,
  bei einer wöchentlichen Redaktion aber falsch: der Leser muss selbst
  herausfinden, was wichtig ist.
- **Nachrichtenportal**: Wichtigkeit wird durch **Fläche, Position und
  Schriftgrad** vorentschieden — die Redaktion trifft die Auswahl, damit der
  Leser sie nicht treffen muss. Genau das fehlt Telco Radar heute: eine echte
  **Rangfolge**, sichtbar in Pixeln.

> "Larger articles or headlines are perceived as more important... articles
> positioned towards the top and left are considered more important because
> readers naturally scan from the top-left corner." — Analyse zu
> Homepage-Informationsarchitektur, vgl. auch die Nielsen-Norman-Guideline
> "Emphasize the highest priority tasks so that users have a clear starting
> point" ([nngroup.com](https://www.nngroup.com/articles/113-design-guidelines-homepage-usability/)).

Die gute Nachricht für Telco Radar: Das System hat bereits eine echte
Redaktion (Editor-Agent, Dringlichkeitsstufen 1–5, Bereichsredakteure +
Chefredaktion). Es fehlt nur die **visuelle Übersetzung** dieser Hierarchie.
Das ist informationsarchitektonisch die halbe Miete — die redaktionelle
Auswahl existiert schon, sie muss nur in Fläche/Position/Schriftgrad
übersetzt werden statt in gleichgroße Karten.

---

## 1. Wie sind die großen Portale strukturiert? (Zonen & Hierarchiestufen)

Die untersuchten Portale (WSJ, NYT, Guardian, BBC, Bloomberg, Axios, Spiegel,
FAZ) folgen alle demselben Grundmuster mit **vier erkennbaren
Hierarchiestufen**, nur mit unterschiedlicher Ausprägung:

**Stufe 1 — Der Aufmacher (Lead Story / Hero).** Eine einzige Geschichte,
deutlich größer als alle anderen: größtes Bild (oder bei textbasierten
Portalen wie Axios/Politico: größter Schriftgrad + eigener Absatz-Umfang),
größte Schlagzeilen-Type, meist mit Standfirst/Dek (1–2 erklärende Sätze
direkt unter der Headline). Steht allein oben links (Gutenberg-Prinzip:
Leser starten oben links).

**Stufe 2 — Zweitplatzierung (Second Lead / Secondary Package).** 2–4
Geschichten, sichtbar kleiner: kleineres oder gar kein Bild, kleinerer
Schriftgrad (typisch 60–75 % der Aufmacher-Größe), oft ohne Standfirst,
nur Kicker + Headline. Stehen visuell neben oder unter dem Aufmacher, nie
gleichrangig.

**Stufe 3 — Ressort-/Themenblöcke (Section Modules).** Modulare Blöcke,
jeweils mit eigenem Ressort-Titel als Kopfzeile (z. B. "Wirtschaft",
"Politik", "Tech"), darunter 3–6 reine Text-Links ohne oder mit sehr
kleinem Bild. Trennlinien oder Farbflächen grenzen die Module gegeneinander
ab (bei FAZ.NET z. B. "Topic-Module, in denen zusammengefasst wird, was
thematisch zusammengehört" — [bdzv.de](https://www.bdzv.de/service/presse/branchennachrichten/2024/frankfurter-allgemeine-zeitung-relauncht-ihr-nachrichtenportal-faznet)).

**Stufe 4 — Listen/Ticker (Most Read, In Brief, Zuletzt).** Reine
Text-Listen ohne Bilder, oft mit Rang-Nummer (1., 2., 3. …) statt Kicker,
meist in einer schmalen Randspalte oder ganz unten. Signalisiert
Popularität statt redaktioneller Wichtigkeit — bewusst ein anderer
Sortier-Mechanismus als der Rest der Seite.

Dazu kommt bei fast allen ein **Ticker/Statusband** ganz oben (bei Reuters
z. B. nur ein dezentes rotes "BREAKING"-Label statt Vollbanner) und eine
**Sektions-/Ressortleiste** direkt unter dem Header als horizontale
Navigation.

Konkrete Beobachtungen je Portal:

- **WSJ**: Editoriale Hierarchie ist laut eigener Aussage das
  Kernprinzip des gesamten Seitenaufbaus — Story-Strukturen werden
  kategorisiert, um Hierarchie auf allen Seitentypen konsistent zu halten.
  Farbpalette bewusst zurückhaltend gewählt (Mint, Himmelblau, Champagner),
  damit Farbe nicht mit Inhalt konkurriert. Mobile ist eine eigene
  Informationsauswahl, kein verkleinertes Desktop-Layout
  ([Poynter](https://www.poynter.org/archive/2002/behind-the-redesign-wsj/), [Cory Etzkorn](https://www.coryetzkorn.com/work/the-wall-street-journal), [Marketing Dive](https://www.marketingdive.com/ex/mobilemarketer/cms/news/media/14798.html)).
- **NYT**: Custom-Serif (Cheltenham) für Headlines, Georgia-Serif für
  Fließtext — Serifen signalisieren hier bewusst redaktionelle Autorität,
  nicht Nostalgie. Redesigns bündeln Inhalte in Blöcke je Ressort statt
  einer langen Liste ([Fast Company](https://www.fastcompany.com/90129186/why-you-may-not-even-notice-the-new-york-times-major-homepage-redesign)).
- **The Guardian**: eigene Schrift (Guardian Egyptian, Serife mit
  digitaler Schärfe), strikter Grid, Farbcodierung nach Inhaltstyp — ein
  gelber Hintergrund markiert Meinung/Opinion, ganz ohne Text-Label. Das
  ist ein direkt übertragbares Muster: **Farbe statt Label** zur
  Kategorisierung.
- **BBC News**: keine Randspalten ("Sidebar-frei"), volle Breite,
  Karten-Raster nur für Stufe 3/4, kein Werbe-Rauschen.
- **Bloomberg**: kompakte, mechanische serifenlose Schrift für hohe
  Informationsdichte, dunkles Theme als Standard im Finanzbereich
  (Terminal-Erbe), Navy/Lachs-Farbschema. Wichtig für Telco Radar: Bloomberg
  hat selbst erkannt, dass das reine Zwei-Ton-Terminal-Look **fürs Web zu
  hart** ist, und ist zu farbigen, redaktionell kuratierten Homepages
  übergegangen — "Bloomberg Realizes The Web Is Not A Terminal"
  ([TechCrunch](https://techcrunch.com/?p=173918), [Nieman Lab](https://www.niemanlab.org/2015/01/bloomberg-business-new-look-has-made-a-splash-but-dont-just-call-it-a-redesign/)). Das ist eine direkte Warnung für den
  aktuellen "Bloomberg-Terminal-Stil" von Telco Radar: das Terminal-Erbe
  eignet sich für Fließdaten, nicht für einen redigierten Wochenbericht.
- **Spiegel**: Relaunch vergrößerte die Seitenbreite (770→900px) zugunsten
  von großformatigen Bildern/16:9-Videos im Aufmacherbereich, führte
  Themenbündelung mit Farbclustern ein — jedes Ressort/Thema bekommt eine
  eigene Akzentfarbe ([designtagebuch.de](https://www.designtagebuch.de/relaunch-von-spiegel-online/)).
- **FAZ.NET**: reduziertes Design, gut lesbare Schrift, "multi-column
  layout... erlaubt Redakteuren, längere analytische Stücke prominent oben
  zu platzieren" — also **Textlänge selbst als Hierarchie-Signal** (lange
  Analysen bekommen breiteren Raum, keine Kachel) ([bdzv.de](https://www.bdzv.de/service/presse/branchennachrichten/2024/frankfurter-allgemeine-zeitung-relauncht-ihr-nachrichtenportal-faznet)).
- **Axios**: kein Bild-Hero, sondern textuelle Hierarchie: **Kicker in
  Blockfarbe** ("1 big thing", "State of play"), fetter Einstiegssatz,
  darunter strukturierte Bullet-Absätze ("Why it matters", "The big
  picture", "Go deeper"). Ein-Spalten-Layout pro Story, aber mehrere Storys
  vertikal gestapelt mit klaren Trennlinien. Kritiker merken an, dass die
  Bullet-Struktur nicht immer konsequent durchgehalten wird — als Vorbild
  für Telco Radar heißt das: **konsequent anwenden, nicht dekorativ**
  ([Tedium](https://tedium.co/2022/07/13/axios-smart-brevity-alt-story-form-critique/), [Axios](https://www.axios.com/smart-brevity)).
- **Politico Pro**: als B2B-Intelligence-Produkt sehr nah am Telco-Radar-Fall
  (Fachpublikum, kein breites Publikum). Kernformat: **E-Mail-Briefing mit
  "Blurbs" je Thema/Firma/Person, in Chunks indiziert** — keine Startseite im
  klassischen Sinn, sondern eine Kette kurzer, klar betitelter Blöcke, die
  man in 3–5 Minuten querlesen kann. Übertragbar: **jede Meldung bekommt eine
  Ein-Satz-Zusammenfassung, bevor man weiterliest** ([Algolia/Politico Case Study](https://www.algolia.com/customers/politico), [The Rebooting](https://therebooting.substack.com/p/politico-and-the-allure-of-the-prosumer)).
- **Semafor** (Semaform): das strukturell radikalste Muster. Jede
  Geschichte wird in **fünf klar betitelte, mit Icon markierte Abschnitte**
  zerlegt: **The News** (Fakten) → **[Reporter]'s View** (Einordnung) →
  **Room for Disagreement** (Gegenposition) → **The View From** (andere
  Perspektive) → **Notable** (Linkliste zu Weiterem). Ein
  Mini-Inhaltsverzeichnis am Artikelanfang erlaubt Sprung-Navigation
  ([Semafor](https://www.semafor.com/article/10/18/2022/what-is-a-semaform-anyway-and-why-should-you-care)). Für Telco Radar ist das fast 1:1 nutzbar: **Meldung →
  Was ist passiert (Fakten) → Warum das für Vodafone interessant ist
  (Einordnung, das leistet der Analyst-Agent schon!) → Dringlichkeit →
  Quelle.**
- **The Information**: zwei getrennte Feeds (Neueste / Meistgelesen) statt
  einer Mischliste, harter Paywall-Fokus auf E-Mail-Bindung, über 200 Seiten
  im letzten Redesign überarbeitet inkl. neuer Wortmarke
  ([The Information](https://www.theinformation.com/articles/our-new-look-for-the-next-era)). Für Telco Radar relevant: **zwei Sortierungen
  gleichzeitig anbieten** (chronologisch vs. nach Dringlichkeit) statt
  einer erzwungenen Reihenfolge.

---

## 2. Grid-Systeme & wie Aufmacher vs. Zweitplatzierung kodiert wird

Zeitungslayout ist seit Jahrzehnten **modular**: jede Geschichte ist ein
in sich geschlossener Kasten in einem Spaltenraster (klassisch 4–14
Spalten), Kästen lassen sich beliebig neu anordnen, ohne den Textfluss zu
brechen ([Smashing Magazine](https://www.smashingmagazine.com/2019/11/newspapers-teach-web-design/), [Fiveable Editorial Design Notes](https://fiveable.me/advanced-editorial-design/unit-8/newspaper-grid-structures/study-guide/6Rc2XECLdNLLHdmx)). Für digitale Portale heißt das
konkret CSS Grid mit **ungleich großen Zellen**, nicht ein gleichförmiges
Karten-Grid. Die Hierarchie wird über mindestens vier unabhängige,
gleichzeitig eingesetzte Signale kodiert — genau das fehlt einem reinen
Karten-Grid, wo praktisch nur ein Signal (Position in der Liste) übrig
bleibt:

| Signal | Aufmacher | Zweitplatzierung | Ressort-Zeile | Ticker/Liste |
|---|---|---|---|---|
| Bild-/Flächengröße | groß (bis zu halber Viewport) | mittel oder kein Bild | kein Bild | kein Bild |
| Schriftgrad Headline | größte Stufe der Skala | ca. 60–75 % davon | ca. 45–55 % davon | Fließtextgröße |
| Schriftschnitt | oft Serif, fett | Serif/Sans, halbfett | Sans, regulär | Sans, regulär |
| Whitespace um Element | viel (Luft signalisiert Wichtigkeit) | mittel | wenig | keins (dichte Liste) |
| Trennlinie | keine — steht frei | dünne Linie oder Kartenrand | Kopf-Regel über dem Block | nur Zeilen-Divider |
| Zusatzelemente | Standfirst/Dek, Byline, Zeitstempel | Kicker + Headline, evtl. Zeitstempel | nur Headline | nur Headline + Rang/Zeit |

Der zentrale Mechanismus heißt in der Fachliteratur **"Visual Hierarchy
through Size, Weight, Color, and Placement"** — Größe ist das stärkste
Signal, gefolgt von Position (oben-links > unten-rechts, Gutenberg-Prinzip)
([Fiveable](https://fiveable.me/editorial-design/unit-8/newspaper-layout-fundamentals/study-guide/ObFtrRuiCVJvMFt8)). Wichtig: Diese Signale wirken nur, wenn sie **selten
und konsequent** eingesetzt werden — ein Layout mit vielen "großen" Elementen
hat keine Hierarchie mehr. Genau das ist das Risiko eines Karten-Grids: alle
Karten kämpfen um dieselbe Aufmerksamkeit.

---

## 3. Benannte Design-Patterns (Referenzliste)

Direkt umsetzbare, benannte Patterns, sortiert nach Einsatzort:

- **Hero / Lead Well**: der oberste, große Aufmacher-Block. "Lead Well"
  bezeichnet speziell die Kombination aus großem Bild + Headline + Standfirst
  als eine visuell geschlossene Einheit.
- **Hero-plus-Grid**: eine Lead-Story oben, darunter ein Karten-Raster für
  Sekundäres — der heute meistgenutzte Hybrid zwischen "News River" und
  "Card Grid" ([Muffin Group](https://muffingroup.com/blog/news-website-design/)).
- **River (Nachrichtenfluss)**: eine einspaltige, chronologisch oder nach
  Priorität sortierte Liste von Kurz-Einträgen, jeder mit Kicker + Headline
  + 1-Zeiler, ohne Bildzwang. Gut für textlastige, faktenbasierte Inhalte
  (passt zu Telco Radar besser als ein Karten-Grid, weil Meldungen selten
  eigene Bilder haben).
- **Card Grid**: gleich große Kacheln nebeneinander — laut Recherche das
  Muster, das am ehesten "dashboardig" wirkt, weil es keine Rangfolge codiert;
  eher für Explorer/Archiv-Ansichten geeignet als für die Hauptseite.
- **Kicker / Overline / Dachzeile**: kurzes Label über der Headline (Rubrik,
  Themenfeld, Region) — bei Telco Radar ideal für "Region: Europa" oder
  "Thema: Netzausrüster" statt eines bunten Badges.
- **Standfirst / Dek / Vorspann**: 1–2 erklärende Sätze direkt unter der
  Headline, noch vor dem Fließtext — genau die Funktion, die "Warum ist das
  für Vodafone interessant?" aus dem Editor-Prompt heute schon liefert, aber
  bislang nicht typografisch hervorgehoben wird.
- **Byline-Zeile**: Autor/Quelle + Zeitstempel in einer Zeile, meist klein,
  grau, unter dem Standfirst. Bei Telco Radar: Quelle + "vor 3 Tagen" +
  Dringlichkeitsstufe könnten genau diese Zeile bilden.
- **Zeitstempel-Konvention "vor 3 Std."**: relative Zeitangaben für
  Aktualität, aber mit sichtbarem Tooltip/Titel-Attribut für das exakte
  Datum (Barrierefreiheit + Nachprüfbarkeit — passt zum Anspruch
  "jede Aussage mit Quellen-Link"). NN/g-Guideline: "Show the time content
  was last updated, not the generated current time" und "always include the
  time zone" ([NN/g](https://www.nngroup.com/articles/113-design-guidelines-homepage-usability/)).
- **Sektionsleiste / Ressortnavigation**: horizontale Leiste direkt unter dem
  Logo, listet Regionen/Themenfelder als Sprungmarken.
- **Sticky Navigation mit Hide-on-Scroll**: Header verschwindet beim
  Runterscrollen, erscheint beim Hochscrollen wieder — laut Recherche das
  auf News-Seiten dominante Muster, spart Bildschirmfläche ohne Orientierung
  zu verlieren.
- **Ticker/Statusband**: schmales Band ganz oben, entweder als
  Live-Schlagzeilen-Scroller (CNN-Stil, für Telco Radar zu unruhig) oder als
  **dezentes Label** (Reuters-Stil: nur ein rotes "NEU"-Tag neben der
  jeweils aktuellsten Meldung) — letzteres passt besser zu einem
  wöchentlichen statt Live-Format.
- **Most-Read / In-Brief-Liste**: reine Rang-Liste ohne Bilder, oft in einer
  schmalen rechten Spalte — bei Telco Radar denkbar als "Die 5 dringendsten
  Meldungen dieser Woche" (nutzt die vorhandene Dringlichkeitsstufe 1–5
  direkt als Sortierkriterium, ohne Popularität simulieren zu müssen, die
  es bei einem internen Bericht gar nicht gibt).
- **Farbe statt Label zur Kategorisierung** (Guardian-Muster): Regionen oder
  Themenfelder über eine dünne Akzentfarbe am Kartenrand/Kicker markieren
  statt über bunte Badges — reduziert visuelles Rauschen.
- **Semaform-Gliederung** (Semafor): pro Meldung feste Unterabschnitte mit
  Icon — für Telco Radar übersetzbar in **"Was ist passiert" / "Warum
  relevant für Vodafone" / "Dringlichkeit" / "Quelle"** als wiederkehrendes,
  scanbares Muster statt Fließtext-Absatz.
- **Smart-Brevity-Struktur** (Axios): fetter 1-Satz-Einstieg, dann
  Bullet-Block mit fester Vokabel ("Warum das wichtig ist:", "Der
  Zusammenhang:") — direkt für die Kurzfassungen der Bereichsredakteure
  nutzbar.

---

## 4. Was unterscheidet Nachrichtenportal von Dashboard? (konkret für Telco Radar)

| | Dashboard (heutiger Stand) | Nachrichtenportal (Zielbild) |
|---|---|---|
| Grundeinheit | Kachel/Karte, gleich groß | Artikel-Modul, unterschiedlich groß je Rang |
| Wichtigkeit codiert durch | Farbe/Badge/Position im Grid | Fläche + Position + Schriftgrad gleichzeitig |
| Leserichtung | Frei explorierend (wie ein Cockpit) | Vorgegeben: oben-links zuerst, Rest folgt |
| Ziel des Nutzers | Selbst filtern/suchen (Explorer, Charts) | Geführt werden: "was muss ich diese Woche wissen" |
| Textmenge pro Element | kurz (Kachel-Höhe begrenzt) | variabel: Aufmacher darf lang sein, Liste bleibt kurz |
| Whitespace | gleichmäßig zwischen allen Kacheln | ungleich verteilt — viel Luft nur um Wichtiges |

Der Explorer/Charts-Teil ist als **Werkzeug für Nachschlagen** weiterhin
sinnvoll — aber er gehört nach unten, als Anhang/Archiv-Funktion, nicht als
gleichwertige Zone neben dem Wochenbericht. Nachrichtenseiten trennen genau
so: redaktionell kuratierte Zonen oben, durchsuchbare/sortierbare Zonen
(„Most Read", Archiv, Suche) unten oder in einer Randspalte.

---

## 5. Typografie im Newsdesign

- **Line length / Measure**: 60–75 Zeichen pro Zeile für Fließtext gilt
  branchenweit als Zielkorridor (Material Design nennt 40–60 als Untergrenze
  für Bildschirm), umsetzbar mit `max-width: 68ch` auf dem Textcontainer
  ([Google Fonts Knowledge](https://fonts.google.com/knowledge/using_type/understanding_measure_line_length), [Pimp my Type](https://pimpmytype.com/line-length-line-height/)).
- **Serif vs. Sans**: Headlines dürfen bei großer Schriftgröße Serif sein
  (NYT: Cheltenham; Guardian: Guardian Egyptian) — Serifen wirken bei
  großem Schriftgrad autoritativ, ohne die Lesbarkeit zu belasten, die bei
  kleiner Schrift ein Problem wäre. Für Fließtext ist auf dem Bildschirm
  sowohl Serif als auch Sans üblich; entscheidend ist der Kontrast zur
  Headline-Schrift, nicht die Serife an sich.
  ([Google Fonts](https://fonts.google.com/knowledge/using_type/understanding_measure_line_length))
- **Zeilenhöhe**: längere Zeilen brauchen mehr Line-Height; 1,5 gilt als
  guter Kompromiss, hilft zusätzlich Lesern mit Sehschwäche/Legasthenie.
- **Schriftgrößen-Skala**: mindestens 4 klar unterscheidbare Stufen nötig
  (Aufmacher-Headline / Sekundär-Headline / Modul-Headline /
  Fließtext+Meta), siehe Tabelle in Abschnitt 2. Telco Radar nutzt aktuell
  Inter + IBM Plex Mono — das kann bleiben, aber die Stufenanzahl und
  -abstände sollten bewusst auf diese vier Ebenen gemappt werden.
- **Dark Mode**: Echte Portale bieten es an (NYT hat eigenes Dark-Mode-
  Farbtoken-System gebaut), aber mit Vorsicht: eine 2022-Studie fand einen
  Lesbarkeits-Rückgang von 14 % bei schlecht gemachtem Dark Mode; Empfehlung
  ist **off-white auf dunklem Grau statt reinweiß auf schwarz**, um Halation
  (Blooming-Effekt heller Schrift auf dunklem Grund) zu vermeiden
  ([Tenacity](https://tenacity.io/facts/how-poor-dark-mode-design-reduces-reading-comprehension-by-14-percent/), [Audrey Valbuena/NYT](https://audrey-valbuena.com/dark-mode-for-nyt-news-apps)). Telco Radar hat Dark als Standard mit
  Light-Toggle — das deckt sich mit dem Vorbild NYT, aber die Kontrastwerte
  sollten explizit gegen dieses 14-%-Risiko geprüft werden (kein reines
  #000/#fff, sondern gedämpfte Werte wie bereits im Vodafone-Rot-Farbschema
  vermutlich vorhanden).

---

## 6. Responsive: wie klappen diese Layouts auf Mobile zusammen?

- Grundregel überall: **Single-Column-Stack**, Reihenfolge = redaktionelle
  Priorität, nicht räumliche Nähe im Desktop-Layout. Der Aufmacher bleibt
  oben, Zweitplatzierungen folgen direkt darunter (nicht "rechte Spalte nach
  unten verschoben", sondern aktiv neu sortiert).
  ([Elegant Themes zu Flexbox-Reordering](https://www.elegantthemes.com/blog/divi-resources/part-5-of-mastering-flexbox-reordering-content-for-better-mobile-layouts))
- Bilder/Charts werden nicht verkleinert dargestellt, sondern **weggelassen
  oder durch eine Kompakt-Variante ersetzt** (z. B. Balkendiagramm statt
  aufwendigem SVG-Chart) — technisch simpel mit reinem CSS über
  `display:none`/`display:block` und Breakpoints umsetzbar, kein JS nötig.
- Sticky-Navigation wird auf Mobile meist zur reinen Logo-Zeile reduziert,
  Ressort-Leiste wandert ins Hamburger-Menü oder wird horizontal
  scrollbar.
- Die Ressort-/Modul-Blöcke (Stufe 3) werden zu eigenen, vertikal
  gestapelten Abschnitten mit Sprungmarken-Navigation (Anchor-Links) statt
  Nebeneinander.

---

## 7. Zonen-Vorschlag für die neue Telco-Radar-Startseite

```
┌──────────────────────────────────────────────────────────────────────┐
│ HEADER  Logo „Telco Radar“ · Ausgabe-Datum · [Archiv] [Quellen]       │
│ ┌────────────────────────────────────────────────────────────────┐   │
│ │ STATUSBAND (dezent, 1 Zeile): „Diese Woche: 12 neue Meldungen,   │   │
│ │ 3 mit Dringlichkeit 5 · Nächster Lauf: Di/Fr 08:30“              │   │
│ └────────────────────────────────────────────────────────────────┘   │
│ SEKTIONSLEISTE  Für Eilige · Executive Summary · Regionen · Themen ·  │
│                 Trends · Empfehlungen · Archiv           (sticky)    │
├──────────────────────────────────────────────────────────────────────┤
│ ZONE 1 — AUFMACHER (eine Meldung, Dringlichkeit 5, größte Fläche)     │
│  Kicker: „Region Europa · Netzausrüster“                              │
│  HEADLINE (groß, ggf. Serif)                                          │
│  Standfirst: „Warum das für Vodafone wichtig ist“ (1–2 Sätze,         │
│              direkt aus dem Analyst-Urteil)                           │
│  Byline-Zeile: Quelle · vor 2 Tagen · Dringlichkeit ●●●●●              │
├───────────────────────────────┬──────────────────────────────────────┤
│ ZONE 2 — ZWEITPLATZIERUNGEN    │ ZONE 2b — RANDSPALTE                 │
│  2–3 Meldungen, Dringlichkeit  │  „Die 5 dringendsten Meldungen“      │
│  4, kleinerer Schriftgrad,     │  reine Rang-Liste (Ziffer, Headline, │
│  Kicker + Headline + 1 Zeile   │  Region), kein Bild                  │
├──────────────────────────────────────────────────────────────────────┤
│ ZONE 3 — WOCHENBERICHT (Prosa, das Herzstück)                         │
│  Für Eilige → Executive Summary → Top-Signale → Regionen →            │
│  Trends & Muster → Handlungsempfehlungen                              │
│  Fließtext, max-width ~68ch, jede Aussage mit Quellen-Link             │
├──────────────────────────────────────────────────────────────────────┤
│ ZONE 4 — RESSORT-/REGIONS-MODULE (River, nicht Grid)                  │
│  Modul „Europa“   Modul „Nordamerika“   Modul „Asien“   … (Farb-       │
│  Akzent je Region statt Badge, je 3–5 Kicker+Headline-Zeilen)         │
│  Modul „Themenfelder“ separat darunter (eigener Redaktions-Abschnitt) │
├──────────────────────────────────────────────────────────────────────┤
│ ZONE 5 — EINORDNUNG (Charts als Beleg, nicht als Hauptinhalt)          │
│  kompakte SVG-Charts (Region/Thema/Dringlichkeit), klein, mit          │
│  1-Satz-Erklärung statt Vollbild-Dashboard                             │
├──────────────────────────────────────────────────────────────────────┤
│ ZONE 6 — EXPLORER/ARCHIV (Werkzeug-Zone, klar abgesetzt)               │
│  „Alle Meldungen durchsuchen“ — Split-View bleibt hier bestehen,       │
│  aber als Nachschlage-Anhang, nicht als zweite Startseite              │
├──────────────────────────────────────────────────────────────────────┤
│ FOOTER  Wie funktioniert dieser Bericht? · Quellen (167) · Über       │
└──────────────────────────────────────────────────────────────────────┘
```

Mobile-Reihenfolge: Header → Statusband → Aufmacher → Zweitplatzierungen
(Randspalte wandert direkt darunter, nicht seitlich) → Wochenbericht →
Ressort-Module (vertikal gestapelt, mit Sprungnavigation) → Charts
(kompakt) → Explorer → Footer. Keine Zone wird weggelassen, nur neu
sortiert und die Randspalte eingegliedert.

---

## 8. Das würde ich NICHT machen

- **Kein reines Karten-Grid mit gleich großen Kacheln als erste Zone.**
  Genau das erzeugt den heutigen "Dashboard"-Eindruck — es gibt kein
  visuelles Signal, welche der 10 Karten die wichtigste ist.
- **Keine Live-Ticker-Optik (CNN-Stil, durchlaufender Scroller).** Telco
  Radar ist ein zweiwöchentlicher Bericht, kein Live-Feed — ein
  durchlaufendes Breaking-News-Band würde Aktualität suggerieren, die nicht
  existiert, und wirkt für ein internes Tool overengineered.
- **Kein Bloomberg-Terminal-Zweiton-Look (grelles Gelb/Grün auf
  Schwarz) als Leitmotiv.** Bloomberg selbst hat das fürs Web verworfen
  ("The Web Is Not A Terminal") — die aktuelle CLAUDE.md nennt das Ziel
  "Bloomberg-Terminal-Stil", aber gemeint ist vermutlich die *seriöse,
  datengetriebene* Anmutung, nicht die harte Zweiton-Ästhetik. Für eine
  Managerin ohne Technik-Hintergrund ist das echte Bloomberg-Web-Design
  (redaktionell, farbig, mit Weißraum) das bessere Vorbild als das
  Terminal selbst.
- **Keine Badge-Farborgie zur Kategorisierung.** Viele bunte Badges
  (Region, Thema, Dringlichkeit, Quelle …) nebeneinander erzeugen visuelles
  Rauschen. Besser: eine einzige Akzentfarbe pro Region/Thema, konsequent
  am Kartenrand oder im Kicker.
- **Kein "alles above the fold zwingen".** Der Above-the-fold-Mythos ist
  laut aktueller UX-Forschung überholt — 57 % Aufmerksamkeit oben heißt
  nicht "alles muss oben Platz finden". Besser: der Aufmacher plus klare
  Scroll-Einladung (z. B. sichtbarer Anschnitt der nächsten Zone).
- **Keinen Explorer/Charts-Bereich gleichrangig neben den Wochenbericht
  stellen.** Das verwässert die Kernaussage der Seite selbst
  ("Prosa-Wochenbericht ist das Herzstück", CLAUDE.md Abschnitt 8) — Charts
  und Explorer gehören als Beleg/Werkzeug nach unten, nicht als
  gleichberechtigte Spalte daneben.
- **Keine willkürlich angewendeten Struktur-Label ("Why it matters" nur
  manchmal).** Kritik an Axios zeigt: Wenn ein Struktur-Pattern nicht
  konsequent für jede Meldung gilt, wirkt es dekorativ statt funktional. Wer
  ein Semaform-artiges Muster für Telco-Radar-Meldungen einführt (Was ist
  passiert / Warum relevant / Dringlichkeit / Quelle), muss es für **jede**
  Meldung durchhalten, nicht nur für den Aufmacher.
- **Keine reinen Popularitäts-Listen ("Meistgelesen") vortäuschen.** Telco
  Radar hat keine echten Leserzahlen (internes Tool, kleiner
  Nutzerkreis) — eine "Most Read"-Liste wäre Fake-Signal. Stattdessen die
  vorhandene Dringlichkeitsstufe 1–5 nutzen ("Die 5 dringendsten Meldungen"),
  das ist ein echtes, vorhandenes Signal.

---

## 9. Quellenliste

- Poynter, "Behind the Redesign: WSJ" — https://www.poynter.org/archive/2002/behind-the-redesign-wsj/
- Cory Etzkorn, WSJ-Portfolio-Case — https://www.coryetzkorn.com/work/the-wall-street-journal
- Marketing Dive, WSJ Mobile Redesign — https://www.marketingdive.com/ex/mobilemarketer/cms/news/media/14798.html
- Fast Company, NYT-Homepage-Redesign — https://www.fastcompany.com/90129186/why-you-may-not-even-notice-the-new-york-times-major-homepage-redesign
- Smashing Magazine, "What Newspapers Can Teach Us About Web Design" — https://www.smashingmagazine.com/2019/11/newspapers-teach-web-design/
- Fiveable, Newspaper Layout Fundamentals — https://fiveable.me/editorial-design/unit-8/newspaper-layout-fundamentals/study-guide/ObFtrRuiCVJvMFt8
- Fiveable, Newspaper Grid Structures — https://fiveable.me/advanced-editorial-design/unit-8/newspaper-grid-structures/study-guide/6Rc2XECLdNLLHdmx
- vizmasters (Substack), "What Newspapers Can Teach Us About Dashboard Design" — https://vizmasters.substack.com/p/what-newspapers-can-teach-us-about
- Nielsen Norman Group, "113 Design Guidelines for Homepage Usability" — https://www.nngroup.com/articles/113-design-guidelines-homepage-usability/
- Muffin Group, "News Website Design Examples That Redefine Journalism" — https://muffingroup.com/blog/news-website-design/
- Tedium, Axios Smart-Brevity-Kritik — https://tedium.co/2022/07/13/axios-smart-brevity-alt-story-form-critique/
- Axios, "Smart Brevity" — https://www.axios.com/smart-brevity
- Semafor, "What is a Semaform, anyway?" — https://www.semafor.com/article/10/18/2022/what-is-a-semaform-anyway-and-why-should-you-care
- Columbia Journalism Review, "Semaform and function" — https://www.cjr.org/the_media_today/semafor_launch_review.php
- The Information, "Our New Look for the Next Era" — https://www.theinformation.com/articles/our-new-look-for-the-next-era
- Simon Owens / Talking Biz News, "Inside The Information's paywall strategy" — https://simonowens.substack.com/p/inside-the-informations-paywall-strategy
- Algolia Case Study, POLITICO — https://www.algolia.com/customers/politico
- The Rebooting, "Politico and the allure of the prosumer model" — https://therebooting.substack.com/p/politico-and-the-allure-of-the-prosumer
- TechCrunch, "Bloomberg Realizes The Web Is Not A Terminal" — https://techcrunch.com/?p=173918
- Nieman Lab, Bloomberg-Business-Redesign — https://www.niemanlab.org/2015/01/bloomberg-business-new-look-has-made-a-splash-but-dont-just-call-it-a-redesign/
- designtagebuch.de, Relaunch von Spiegel Online — https://www.designtagebuch.de/relaunch-von-spiegel-online/
- BDZV, FAZ.NET-Relaunch — https://www.bdzv.de/service/presse/branchennachrichten/2024/frankfurter-allgemeine-zeitung-relauncht-ihr-nachrichtenportal-faznet
- Google Fonts Knowledge, "Understanding measure/line length" — https://fonts.google.com/knowledge/using_type/understanding_measure_line_length
- Pimp my Type, "Ideal line length & line height" — https://pimpmytype.com/line-length-line-height/
- Tenacity, "Poor Dark Mode Design Reduces Reading Comprehension" — https://tenacity.io/facts/how-poor-dark-mode-design-reduces-reading-comprehension-by-14-percent/
- Audrey Valbuena, "Dark Mode for NYT News Apps" — https://audrey-valbuena.com/dark-mode-for-nyt-news-apps
- Wikipedia, "Above the fold" — https://en.wikipedia.org/wiki/Above_the_fold
- bmon.co.uk, "Kicker, standfirst, and slug: what they mean" — https://www.bmon.co.uk/2026/05/kicker-standfirst-and-slug-what-they-mean/
- Elegant Themes, Mobile-Reordering mit Flexbox — https://www.elegantthemes.com/blog/divi-resources/part-5-of-mastering-flexbox-reordering-content-for-better-mobile-layouts

---

*Nächster Schritt: Diese Zonen-Struktur mit den bestehenden Templates in
`src/telco_radar/report/templates/` abgleichen (base/report.html.j2) und
prüfen, welche Daten aus `data/reports/*.json` bereits für Aufmacher/
Zweitplatzierung/Ressort-Module ausreichen (Dringlichkeit, Region,
Kurzfassung sind schon vorhanden) — die Umsetzung ist primär CSS/Grid- und
Template-Reihenfolge, kein neuer Datenbedarf.*
