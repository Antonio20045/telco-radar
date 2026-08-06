# Eigenmessungen und Code-Befunde (Session 6, 06.08.2026)

Diese Datei enthält nur, was in dieser Session **selbst gemessen oder im Code
verifiziert** wurde — keine Rechercheergebnisse, keine Vermutungen.

---

## 1. Der wichtigste Befund: Die Website hat keine Überschriften

`report/html.py:162`

```python
h["de_title"] = _first_sentence(h.get("summary") or "", 150) or h.get("title") or ""
```

`de_title` ist das, was auf der Seite überall als Überschrift steht — in der
Hero-Karte, in der Signalliste, auf der Übersicht, im Explorer. Es ist **keine
Überschrift**, sondern der erste Satz der Analysten-Zusammenfassung, hart auf
150 Zeichen abgeschnitten.

Der Analyst (`analyze/agents.py`) liefert je Meldung:

| Feld | Inhalt | Sprache |
|---|---|---|
| `title` | Originaltitel, wörtlich übernommen | meist Englisch |
| `summary` | 1–2 Sätze „was genau passiert ist" | Deutsch |
| `why_it_matters` | 1–2 Sätze Vodafone-Winkel | Deutsch |
| `category`, `relevance`, `operator`, `url`, `source` | Metadaten | — |

Es gibt **kein Feld für eine deutsche Schlagzeile**. Deshalb liest sich die
Seite wie eine Liste angeschnittener Fließtextsätze. Ein Beispiel aus dem Lauf
vom 05.08.:

> „Der britische Glasfaser-Anbieter Hey! Broadband bringt drei neue
> 900-Megabit-pro-Sekunde-Bündel auf den Markt, alle mit den ersten sechs
> Monaten zum halben Preis."

Das ist ein korrekter Satz — aber als Schlagzeile ist er 30 Wörter zu lang und
das Subjekt versteckt sich hinter zwei Attributen. Genau das ist der
„kognitive Aufwand vor dem Verstehen", den Antonio beschreibt. Er entsteht
nicht im Layout, sondern eine Ebene früher: **es wurde nie eine Schlagzeile
erzeugt.**

Konsequenz für den Plan: Der Redesign muss beim Analysten-Prompt anfangen,
nicht beim CSS.

## 2. Bilder: gemessen, nicht geschätzt

Zwei Messungen auf den echten Meldungen der letzten vier Berichte.

### 2a. Liefert der Feed selbst ein Bild?

44 Fachpresse-Feeds abgefragt, 39 erreichbar:

| | Anteil |
|---|---|
| Feeds mit `media:content` / `media:thumbnail` / `enclosure` in >50 % der Items | **8 von 39 (21 %)** |
| Feeds mit irgendeinem `<img>` im Item-HTML | 15 von 39 (38 %) |

Der Feed-Weg allein reicht also nicht.

### 2b. Liefert die Artikelseite ein `og:image`?

79 Artikel-Abrufe über 29 Quellen:

| Ergebnis | Anteil |
|---|---|
| `og:image` / `twitter:image` gefunden | **66 %** (in einer zweiten Stichprobe über 70 Artikel: 73 %) |
| HTTP 403 (Bot-Abwehr) | 20 % |
| Kein og:image im HTML | 14 % |

**Und die entscheidende Zusatzfrage — sind die Bilder artikelspezifisch oder
immer dasselbe Share-Bild?** Für alle Quellen mit mindestens zwei Treffern:

| | Quellen |
|---|---|
| Jedes Bild anders (artikelspezifisch) | **18 von 19** |
| Immer dasselbe Bild (generische Share-Karte) | 0 |
| Gemischt | 1 |

Das war die Risikofrage, und sie ist positiv beantwortet. Einzelne
Konzern-Newsrooms (NTT, Charter) liefern zwar erkennbar generische
Share-Grafiken (`sns_share.png`, `Spectrum Logo_Social Share.jpg`) — die sind
maschinell erkennbar, weil dieselbe URL bei mehreren Meldungen derselben
Quelle wiederkehrt.

### 2c. Die beiden Wege ergänzen sich fast perfekt

Die Quellen, die den Artikelabruf mit 403 blocken, sind genau die, die ein
Bild schon im Feed mitliefern:

| Quelle | Artikelabruf | Bild im Feed |
|---|---|---|
| Telecoms.com | 403 | 100 % |
| Light Reading | 403 | 70 % |
| Mobile World Live | 403 | 0 % ← echte Lücke |
| Capacity Media | 403 | (kein Feed-Bild) |

Fallback-Kette `Feed-Bild → og:image → …` deckt damit deutlich mehr ab als
jeder Weg für sich. Die verbleibende Lücke sind die Fachpresse-Quellen hinter
Cloudflare ohne Feed-Bild.

### 2d. Was schon da ist (und übersehen wird)

Die Bild-Infrastruktur existiert bereits — für den Promo-Anwendungsfall:

- `collect/promo_snapshot.py::extract_hero_image()` — og:image/twitter:image-
  Extraktion mit Prioritätsliste, fertig getestet
- `collect/promo_snapshot.py::capture_hero_image()` — echter Screenshot per
  Playwright
- `promo_images.py` — Slug-Bildung, Cache-Pfade, git-versionierter Bildspeicher
- `report/promo.py` + `promo_index.html.j2` — Karten mit Bild und
  Farbkachel-Fallback

Für die Marktrecherche muss das **nicht neu gebaut, sondern übertragen**
werden. Das senkt den Aufwand des Bildthemas erheblich.

### 2e. Der Kostenpunkt, den man vorher klären muss: Repo-Größe

Die Promo-Screenshots liegen bei 70–120 KB je Bild, 1,2 MB für 13 Marken. Bei
~60 bebilderten Meldungen je Lauf und 2 Läufen pro Woche wären das rund
**12 MB pro Woche in git, ~600 MB pro Jahr** — bei aktuell 8,6 MB `.git`
insgesamt. Das ist die eine Stelle, an der das Bildthema kippen kann.
Gegenmittel gehören in den Plan (Größenlimit je Bild, WebP, Beschnitt auf
Kartenformat, Aufräumen nach N Wochen — nur der aktuelle Bericht braucht
Bilder in voller Zahl).

## 3. Weitere im Code verifizierte Befunde

**Die Seite hat keine Artikelseiten.** Jede Meldung verlinkt direkt nach
extern (`target="_blank"`). Es gibt keine seiteneigene Detailansicht außer dem
`<details>`-Explorer im Bericht. Ein Nachrichtenportal braucht eine Stufe
dazwischen — sonst hat jede Meldung genau eine Interaktion: weg von der Seite.

**Die Sortierung ist rein nach Dringlichkeit** (`html.py:164`,
`_flatten` sortiert nach `relevance` dann Datum). Ein Nachrichtenportal
gewichtet nach Wichtigkeit *und* Aktualität — und zeigt die Hierarchie
optisch, nicht als Zahlenbadge „4/5".

**Die Startseite ist ein Bento-Dashboard** (`uebersicht.html.j2`): Lead-Kachel
+ 4 KPI-Kacheln + Balkendiagramme + Mini-Panels. Das ist die Bauform, die
Antonio als „nicht intuitiv" beschreibt — sie zeigt Kennzahlen über die
Nachrichten, statt die Nachrichten zu zeigen.

**Google Fonts wird von einem externen CDN geladen** (`base.html.j2:8-10`).
Drei Punkte gegen den Ist-Zustand: es widerspricht dem eigenen Grundsatz „kein
CDN", es blockiert das Rendern, und bei einer Vodafone-internen Seite ist der
Abruf von `fonts.googleapis.com` datenschutzrechtlich der Punkt, an dem
üblicherweise jemand nachfragt. Schriften gehören lokal ins Repo.

**Die Regionszuordnung ist weiterhin kaputt** — im Lauf vom 05.08. bekam
Europa 0 bewertete Meldungen, „Global" 62 von 92. Das ist in CLAUDE.md als
offener Punkt 1 vermerkt und trifft das Redesign direkt: ein Nachrichtenportal
mit Ressorts braucht funktionierende Ressorts.

**Der Explorer versteckt sich hinter `<details>`** (`report.html.j2:66`) — der
Zugang zu allen Meldungen ist zugeklappt und heißt „bei Bedarf öffnen".

## 4. Was das für die Reihenfolge im Plan heißt

Die Beschwerde „ich weiß nicht, worum es geht, bevor ich Aufwand investiert
habe" hat drei Ursachen, und nur die dritte ist Layout:

1. Es gibt keine deutsche Schlagzeile (Prompt-/Datenebene)
2. Es gibt keinen visuellen Anker (Sammelebene: Bilder werden nie geholt)
3. Die Darstellung ist ein Dashboard, kein Blatt (Renderebene)

Ein Redesign, das nur bei 3 ansetzt, wird das Problem nicht lösen.
