# Recherche: Visuelle Anker für Telco Radar — ohne Bildbudget, ohne Rechtsrisiko

Stand: 06.08.2026. Diese Recherche beantwortet die Frage, wie Telco Radar zu
einer Optik kommt, bei der ein Element zuerst das Auge fängt und dann die
Headline trägt — ohne Fotoredaktion, ohne Bildagentur, ohne Rechtsstreit.

**Wichtiger Befund vorab, der die ganze Empfehlung prägt:** In der Aufgabe
war von einer „internen, nicht-öffentlichen Firmenseite" die Rede. Laut
Handover-Dokument ist `telco-radar.onrender.com` aber eine **frei im
Internet erreichbare Static Site ohne Login**. Rechtlich zählt das als
öffentliches Angebot — und deutsche Rechtsprechung lässt selbst echte
Intranets nicht automatisch als „nicht öffentlich" durchgehen, wenn die
Nutzer keine persönliche Bindung zum Betreiber haben (siehe Rechtsteil,
Quelle rechtambild.de). Die gesamte Risikoabwägung unten geht deshalb vom
worst case „öffentliche Website" aus, nicht vom besten Fall „Intranet".

---

## 1. Empfehlung in einem Satz

**Kein Fremdfoto, nirgends — stattdessen ein deterministisches, komplett
selbst erzeugtes Cover-System aus Kicker-Typografie, Regions-/Themenfarbe
und (wo vorhanden) dem Logo des genannten Betreibers.** Das liefert das
WSJ-Gefühl (Farbfläche + große Type + Wiedererkennungswert), kostet
praktisch nichts, wächst das Git-Repo nicht, hat keine Latenz, keine toten
Links und kein Urheberrechtsrisiko. Echte Artikelfotos (og:image) bleiben
eine spätere, klar gekennzeichnete Zusatzoption für ausgewählte Fälle — kein
Standardweg.

Begründung in Kürze: Telco Radar sammelt aus **167 fremden Quellen** und
veröffentlicht öffentlich. Jedes fremde Foto, das dabei kopiert oder auch
nur wiederholt eingebettet wird, ist eine Einzelfallprüfung von Urheber-
UND Presseverleger-Leistungsschutzrecht — bei einer vollautomatischen
Pipeline ohne Redaktion, die das prüfen könnte, ist das ein strukturelles
Risiko, kein Einzelfall-Risiko. Ein System, das *nie* ein fremdes Bild
braucht, hat dieses Risiko systematisch nicht.

---

## 2. Bilder aus der Quelle ziehen — technisch machbar, rechtlich das
   heikelste Feld

### 2.1 Technische Trefferquote

- **`<media:content>` / `<media:thumbnail>` (Media RSS)**: eine
  RSS-Erweiterung, kein Standard. Verbreitet bei Podcast- und
  Video-orientierten Feeds, bei klassischer Telko-Fachpresse und
  Betreiber-Newsrooms eher die Ausnahme als die Regel — belastbare
  quantitative Zahlen dazu gibt es öffentlich nicht, in der Praxis ist mit
  einer niedrigen zweistelligen Trefferquote über einen gemischten
  Feed-Bestand wie den 167 Quellen von Telco Radar zu rechnen.
- **`<enclosure>`**: ursprünglich für Podcast-Audio gedacht, bei
  Text-Newsfeeds selten mit Bildern belegt.
- **Open Graph `og:image` / `twitter:image`**: die verlässlichste Quelle,
  aber nur per zusätzlichem Abruf der Artikel-URL (ein GET auf die
  Zielseite, Meta-Tags im `<head>` parsen — kein Volltext-Scraping nötig).
  Praktisch jede moderne CMS-getriebene Newsroom- oder Presseseite setzt
  og:image, weil es für Social-Sharing-Vorschauen gebraucht wird — die
  Trefferquote dürfte deutlich über 70–80 % liegen, ist aber nicht
  garantiert und bekannte Fallstricke gibt es: viele CMS liefern als
  Fallback ein generisches Seiten-Logo statt eines Artikelbilds, was zu
  „jeder Artikel hat dasselbe Bild" führt, wenn man es ungeprüft übernimmt.
- **JSON-LD `NewsArticle.image`**: als Ergänzung zu og:image sinnvoll,
  gelegentlich die einzige Quelle bei Seiten, die auf klassisches Open
  Graph verzichten, aber Structured Data für Google News pflegen.
- Kein Suchergebnis lieferte belastbare, unabhängige Trefferquoten-Messungen
  für Nachrichtenseiten allgemein — die Zahlen oben sind aus Verbreitung
  von Open-Graph-Implementierung in der Praxis abgeleitet, nicht gemessen.

### 2.2 Rechtslage — der eigentliche Kern der Recherche

**Diese Zusammenfassung ist eine Recherche-Synthese, keine Rechtsberatung.**
Bei konkreter Umsetzung sollte das juristisch geprüft werden.

**a) Framing/Hotlinking vs. Kopieren — der entscheidende Unterschied.**
Der EuGH hat in **BestWater (C-348/13, 2014)** entschieden: Framing/Embedding
eines Werks, das der Rechteinhaber selbst frei zugänglich ins Netz gestellt
hat, ist in der Regel *keine* neue „öffentliche Wiedergabe" — solange kein
neues Publikum erschlossen und keine neue Technik verwendet wird. Das
Gegenstück ist **Córdoba/Renckhoff (C-161/17, 2018)**: Ein Foto vom
fremden Server herunterzuladen und auf dem eigenen Server neu
hochzuladen, ist dagegen eine **neue Wiedergabehandlung, die eine neue
Zustimmung des Urhebers braucht** — selbst wenn das Originalfoto frei
zugänglich war. Übertragen auf Telco Radar: Ein og:image *live* im Browser
des Lesers vom Originalserver laden (`<img src="https://quelle.de/bild.jpg">`)
bewegt sich in der BestWater-Logik. Ein og:image beim Pipeline-Lauf
herunterladen und als eigene Datei ins Git-Repo bzw. auf den eigenen
Static-Site-Server legen, ist exakt der Córdoba-Fall — **das braucht
Zustimmung, die es hier nie gibt.**

**Wichtig:** Reines `<img>`-Hotlinking ist trotz BestWater kein
Freibrief. Ein Urteil des LG München I hat Hotlinking auf ein Foto als
Verstoß gegen § 19a UrhG gewertet; die Abgrenzung zwischen „unschädlichem
Framing" und „schädlichem Hotlink" ist in der deutschen Instanzrechtsprechung
nicht sauber trennscharf. Praktisch heißt das: Hotlinking ist *weniger*
riskant als Kopieren, aber nicht risikofrei — dazu kommen technische
Nachteile (der Quell-Server kann das Bild jederzeit löschen oder per
Referrer-Sperre blockieren, „Hotlink Protection" ist auf vielen
Presseseiten aktiv).

**b) Vorschaubilder-Doktrin (BGH, drei Urteile 2010–2017) ist NICHT
1:1 übertragbar.** Der BGH hat Googles Bildersuche freigesprochen, weil
Rechteinhaber, die ihre Bilder ohne technische Schutzmaßnahmen frei ins
Netz stellen, mit der „ortsüblichen" Nutzung durch Suchmaschinen-Crawler
rechnen müssen (konkludente Einwilligung). Diese Doktrin ist aber explizit
auf die **Funktionsweise von Suchmaschinen** zugeschnitten (Indexierung
des gesamten Web, Opt-out über robots.txt als Branchenstandard). Ein
redaktionell kuratierter Wochenbericht, der aus 167 gezielt ausgewählten
Quellen zitiert, ist strukturell etwas anderes als ein Suchindex — ob ein
Gericht die konkludente Einwilligung hier anerkennen würde, ist offen und
in der Literatur umstritten. Darauf zu bauen wäre eine Wette, keine
gesicherte Grundlage.

**c) Presseverleger-Leistungsschutzrecht (§§ 87f–87k UrhG, Umsetzung der
DSM-Richtlinie Art. 15).** Das Recht schützt Presseveröffentlichungen bei
der Online-Nutzung durch „Diensteanbieter der Informationsgesellschaft"
— und es **umfasst ausdrücklich nicht nur Text**, sondern auch Grafiken,
Fotos und AV-Inhalte innerhalb der Presseveröffentlichung. Ausnahmen
bestehen für einzelne Wörter oder sehr kurze Auszüge (Snippet-Ausnahme)
sowie für Hyperlinks. Ein wöchentlicher Bericht, der aus dutzenden
Presseverlagen systematisch Bilder entnimmt, ist beinahe die
Paradebeschreibung dessen, wogegen dieses Recht 2019 geschaffen wurde
(damals primär gegen Google News und News-Aggregatoren gerichtet) — eine
zusätzliche Risikoebene *oberhalb* des normalen Urheberrechts einzelner
Fotografen.

**d) Zitatrecht (§ 51 UrhG) trägt hier nicht.** Ein Bildzitat ist nur
zulässig, wenn sich der eigene Text inhaltlich mit genau diesem Bild
auseinandersetzt — nicht, wenn ein Bild nur als visueller Aufhänger neben
einer thematisch verwandten, aber unabhängigen Meldung steht. Für eine
automatisierte Pipeline ohne inhaltliche Bildanalyse ist das keine
gangbare Rechtsgrundlage.

**e) Praktische Absicherung, falls trotzdem einzelne og:images genutzt
werden sollen:** Bildunterschrift mit klarer Quellenangabe UND Link zum
Original (das ist ohnehin Antonios Anforderung an Nachprüfbarkeit),
`<meta name="robots" content="noindex">` bzw. `X-Robots-Tag` auf den
betroffenen Seiten (verhindert, dass die Bilder selbst in Google-Bildersuche
& Co. auftauchen und die Reichweite der fremden Nutzung vergrößern), Bilder
klein halten (Thumbnail-Maßstab, nicht Hero-Vollbreite — das nähert sich
zumindest der Argumentationslinie der Vorschaubilder-Rechtsprechung an,
auch wenn diese nicht direkt einschlägig ist), niemals cachen/kopieren,
nur Hotlink, und ein Prozess, um auf Takedown-Anfragen sofort zu reagieren.
Das reduziert das Risiko, beseitigt es aber nicht.

---

## 3. KI-generierte Bilder — technisch trivial, redaktionell fragwürdig

Bildgenerierung ist mit Modellen wie Flux Schnell (~0,003 $/Bild) oder
GPT Image Mini (~0,005 $/Bild) bei rund 150 neuen Meldungen pro Lauf
finanziell irrelevant (unter 1 $/Woche). Das eigentliche Problem ist
inhaltlich: **AP, Reuters und dpa haben übereinstimmend Leitlinien, die KI
für publizierbare Nachrichtenbilder ausschließen oder streng
einschränken.** AP untersagt KI-generierte Bilder für den Nachrichtendienst
grundsätzlich; Reuters verlangt maximale Transparenz über Herkunft und
Erstellungsmethode; dpa lässt KI nur unter menschlicher Aufsicht zu und
macht rein KI-generierte Inhalte kenntlich. Der gemeinsame Kern: Ein Bild,
das ein reales Ereignis oder eine reale Person zeigt, darf nie KI-generiert
sein, weil es Leser über die Faktenlage täuscht — selbst wenn es „nur"
illustrativ gemeint ist. Bei Telco Radar wäre das der Normalfall (Meldung
über ein konkretes Ereignis bei einem konkreten Betreiber), nicht die
Ausnahme.

Vertretbar wäre KI-Bildgenerierung höchstens für **rein abstrakte
Themenbilder** ohne Bezug zu einer realen Person/einem realen Ereignis
(z. B. ein generisches „5G-Netz"-Sinnbild für den Themenfeld-Abschnitt) —
und selbst dann nur mit sichtbarer Kennzeichnung als Illustration. Der
Zusatzaufwand (Latenz in einer Pipeline, die schon bis zu 24 Minuten läuft,
Qualitätskontrolle gegen Halluzinationen wie falsche Flaggen oder erfundene
Bauwerke, ein weiterer Ausfallpunkt) steht in keinem Verhältnis zum Nutzen
gegenüber Option 3. **Empfehlung: vorerst nicht umsetzen.**

---

## 4. Bild-Ersatz ohne Foto — der wichtigste und sicherste Hebel

**Reale Vorbilder für konsequenten Foto-Verzicht bei textlastigen
B2B-Medien:** Stratechery (Ben Thompson) ist als reine Text-Analyse-
Publikation bekannt, die bewusst fast vollständig auf Artikelfotos
verzichtet und stattdessen auf Typografie und klare Struktur setzt (aus
eigener Kenntnis der Publikation angeführt; der direkte Seitenabruf war in
dieser Recherche technisch blockiert, sodass sich das nicht per Zitat
belegen ließ). Axios' „Smart Brevity"-Format zeigt den Gegenentwurf:
knappe Textblöcke mit klaren Bold-Markierungen („Why it matters"), Bilder
kommen vor, tragen aber nicht die Hauptlast — die Struktur trägt. Für Telco
Radar spricht das für: Struktur und Typografie zuerst, Bild höchstens als
Verstärkung.

Konkrete Bausteine, alle ohne Fremdrechte-Risiko:

- **Firmen-Logos als Anker.** Rechtlich der mit Abstand unkritischste
  Baustein: Ein Firmenlogo rein redaktionell/beschreibend zu zeigen, um
  über genau diese Firma zu berichten, ist markenrechtlich in der Regel
  unproblematisch (keine Verwechslungsgefahr, keine Nutzung „als Marke"
  für eigene Waren/Dienstleistungen) — solange es unverändert, klein und
  erkennbar im redaktionellen Kontext bleibt, nicht dekorativ als
  Endorsement-Fläche. Logos können zusätzlich urheberrechtlich geschützt
  sein, wenn sie eine gewisse gestalterische Schöpfungshöhe haben — bei
  einfachen Wort-/Bildmarken (die meisten Telco-Logos) meist nicht
  relevant. Bezugsquellen: **Clearbit Logo API ist seit Dezember 2025
  abgeschaltet** (HubSpot-Übernahme); Nachfolger sind Logo.dev
  (Drop-in-Ersatz, 500 000 Anfragen/Monat kostenlos) und Brandfetch.
  Für ein festes Set von 87 Betreibern ist aber ein **einmaliger,
  selbst gepflegter SVG-Bestand** sinnvoller als eine Live-API-Abhängigkeit:
  Quellen dafür sind **Simple Icons** (3 400+ Marken, CC0, aber nur
  Monochrom und nicht jeder Telco vertreten), **Wikimedia
  Commons/Wikidata** (Property P154 „logo image" — companies haben dort
  oft ihr offizielles Logo hinterlegt, Lizenzangabe pro Datei prüfen),
  und als letzter Fallback der **Google-Favicon-Dienst**
  (`google.com/s2/favicons?domain=...`) — inoffiziell, unsupported, aber
  praktisch für den Rest-Fall „Betreiber ohne gepflegtes Logo".
- **Typografische Cover** (der eigentliche Kern der Empfehlung): Kicker
  (Region oder Thema) + große, kurze Type (Kernbegriff aus der Headline)
  + Farbfläche nach Region/Dringlichkeit — dieselbe Farblogik, die die
  SVG-Charts im Bericht schon nutzen (`report/templates`), lässt sich
  hier wiederverwenden statt neu zu erfinden. Genau das WSJ-Gefühl
  „Farbe + große Type ⇒ Aufmerksamkeit ⇒ Ahnung des Themas" ohne ein
  einziges Fremdpixel.
- **Generative, deterministische Grafiken**: ein Hash aus Artikel-ID oder
  Titel erzeugt reproduzierbar denselben Farbverlauf/dasselbe Muster
  (Identicon-Prinzip, wie es GitHub für Avatare oder DiceBear für Icons
  nutzt) — 100 % Abdeckung garantiert, weil es nie „kein Ergebnis" geben
  kann, und dient als allerletzter Fallback, wenn weder Logo noch
  typografisches Cover greifen (z. B. bei Themenfeld-Meldungen ohne klar
  benannten Betreiber).
- **Icon-Systeme** je Kategorie (Netzausbau, Regulierung, M&A, Gerät …)
  als kleine ergänzende Bildmarke neben dem Cover — geringer Zusatzaufwand,
  hoher Wiedererkennungswert im Explorer.
- **Datenvisualisierung als Aufmacher**: Da das Archiv (`data/reports/*.json`)
  bereits Wochen zurückreicht, ließe sich z. B. eine Sparkline
  „Meldungen zu diesem Betreiber über die letzten Wochen" als Mini-Chart
  in die Kartenansicht einbauen — spannend, aber kein Tag-1-Feature.
- **Flaggen/Länder-Ausschnitte** für die Regionsebene: kleine,
  gemeinfreie SVG-Flaggenbibliotheken (z. B. das MIT-lizenzierte
  flag-icons-Projekt) sind rechtlich unkritisch, weil Nationalflaggen
  nicht urheberrechtlich schutzfähig sind.

---

## 5. Technik für die Static Site

- **Format:** Für alles selbst Erzeugte (Logos, typografische Cover,
  generative Muster) ist **SVG die richtige Wahl** — verlustfrei, wenige
  KB je Datei, kein Rasterformat-Konvertierungsbedarf, im Git-Repo
  unproblematisch klein (87 Logos × ~2–5 KB ≈ unter 500 KB insgesamt).
  Das passt zur bestehenden Repo-Disziplin (das Handover betont explizit
  die Verkleinerung des Seen-Stores von 300 auf 17 Byte je Eintrag) —
  konsequent wäre, **niemals Rasterbilder ins Repo zu committen.**
- **Falls doch Rasterbilder** (etwa ein einzelnes gecachtes og:image für
  einen Sonderfall): Pillow-Pipeline mit WebP, Qualität ~80, feste
  Maximalbreite (Kartenformat, kein Vollbild nötig) hält Dateigrößen klein;
  AVIF spart nochmal 15–20 %, kostet aber Encoding-Zeit und hat schlechtere
  Support-Breite — für kleine Kartenbilder ist der Unterschied
  vernachlässigbar, WebP reicht.
- **Lazy Loading**: natives `loading="lazy"` am `<img>`-Tag, kein
  JavaScript nötig.
- **Platzhalter/LQIP**: bei selbst erzeugten SVG-Covern überflüssig (SVG
  lädt praktisch sofort). Nur relevant, falls doch echte Fotos per Hotlink
  eingebunden würden — dann eine winzige Inline-SVG-Farbfläche (aus der
  dominanten Themenfarbe) als Platzhalter, bis das externe Bild lädt oder
  eben nicht lädt.
- **Fallback bei totem Bild:** Für jeden Hotlink-Fall braucht es eine
  `onerror`-Kaskade im HTML/JS (`<img onerror="...">`), die beim Laden
  eines toten externen Bildes automatisch auf das nächste Element der
  Fallback-Kette umschaltet — bei serverseitig generierten Elementen
  (Logo, Cover, Muster) entfällt dieses Problem komplett, weil es keine
  externe Abhängigkeit gibt, die zur Laufzeit sterben kann.
- **Validierung am Collect-Zeitpunkt:** Ein og:image-Kandidat sollte vor
  Aufnahme in die Fallback-Kette geprüft werden (HEAD-Request,
  `Content-Type: image/*`, Mindestgröße >1 KB) — sonst landen 1×1-Tracking-
  Pixel oder generische Fallback-Logos des CMS im Bericht, und am Ende hat
  jeder Artikel „zufällig" dasselbe Bild.

---

## 6. Fallback-Kette — konkrete Spezifikation

```
1. Manuelles Override (optional, YAML-Feld je Betreiber/Quelle)
2. Firmen-Logo des im Titel genannten Betreibers
   (eigener SVG-Bestand → Wikimedia/Wikidata P154 → Google-Favicon-Dienst)
   auf Farbfläche nach Region/Dringlichkeit
3. Typografisches Cover (Kicker = Region/Thema, große Type = Kernbegriff
   aus der Headline, Farbfläche wie unter 2.)
4. Deterministisches generatives Muster aus Hash(Artikel-ID)
   — garantiert 100 % Abdeckung, letzter Fallback
```

Bewusst **kein og:image-Schritt in der Standardkette.** Als optionale,
klar gekennzeichnete Zusatzfunktion (nicht Default) könnte og:image *vor*
Schritt 2 eingefügt werden — nur als Live-Hotlink, nie als Kopie, mit
Bildunterschrift+Link+noindex wie in Abschnitt 2.2e beschrieben, und nur
nachdem das validiert wurde (Abschnitt 5).

---

## 7. Aufwandsschätzung

| Baustein | Aufwand | Risiko |
|---|---|---|
| Typografisches Cover-System (Kicker+Type+Farbe) | ~1 Tag | keins |
| Generative deterministische Muster (Hash→SVG) | ~0,5 Tag | keins |
| Logo-Bestand (Simple Icons + Wikidata-Download + Favicon-Fallback) | ~2–3 Tage einmalig, danach Wartung bei neuen Quellen | sehr gering (Markenrecht bei rein redaktioneller Nutzung) |
| Flaggen für Regionen | ~0,5 Tag | keins |
| Sparkline/Datenviz als Aufmacher | ~1–2 Tage | keins, aber kein MVP |
| og:image-Pipeline (Fetch, Validierung, Fallback-Kaskade, noindex) | ~1–2 Tage | mittel–hoch, rechtlich ungeklärt |
| KI-Bildgenerierung pro Meldung | ~2–3 Tage + laufendes Risiko-Review | redaktionell fragwürdig, gegen Branchenleitlinien für reale Ereignisse |

**Empfohlene Reihenfolge:** typografisches Cover zuerst (größter visueller
Gewinn pro Aufwand), dann Logo-Bestand, dann generatives Muster als
Sicherheitsnetz. og:image und KI-Generierung zurückstellen.

---

## 8. Quellen

- [Media RSS Specification](https://www.rssboard.org/media-rss)
- [Media RSS – Wikipedia](https://en.wikipedia.org/wiki/Media_RSS)
- [EuGH BestWater C-348/13 – Zusammenfassung](https://www.ratgeberrecht.eu/urheberrecht-aktuell/eugh-framing-entscheidung-und-fotoklau.html)
- [LTO: EuGH zu Fotos im Netz – Linking, Framing, Upload (Córdoba/Renckhoff)](https://www.lto.de/recht/hintergruende/h/eugh-azc16117renckhoff-fotos-veroeffentlichen-upload-homepage)
- [Telemedicus: EuGH Córdoba/Renckhoff C-161/17](https://www.telemedicus.info/urteile/Urheberrecht/1755-EuGH-Az-C16117-CordobaRenckhoff.html)
- [heise: BGH – Googles Bildersuche verletzt Urheberrecht nicht (Vorschaubilder)](https://www.heise.de/news/BGH-Googles-Bildersuche-verletzt-Urheberrecht-nicht-3837840.html)
- [aufrecht.de: BGH Vorschaubilder I – Haftung von Suchmaschinen für Thumbnails](https://www.aufrecht.de/urteile/urheberrecht/bgh-vorschaubilder-i-die-frage-der-haftung-von-suchmaschinen-fuer-vorschaubilder-thumbnails)
- [dejure.org: § 87f UrhG – Begriffsbestimmungen](https://dejure.org/gesetze/UrhG/87f.html)
- [Wikipedia: Leistungsschutzrecht für Presseverleger](https://de.wikipedia.org/wiki/Leistungsschutzrecht_f%C3%BCr_Presseverleger)
- [Lexology: Das Leistungsschutzrecht gemäß Artikel 15 DSM-Richtlinie](https://www.lexology.com/library/detail.aspx?g=250b07f9-afc8-4aab-b4ad-e66fe2edfa6d)
- [drschwenke.de: Wann ist ein Bildzitat erlaubt? (§ 51 UrhG)](https://drschwenke.de/wann-ist-ein-bildzitat-erlaubt-anleitung-mit-beispielen-und-checkliste/)
- [rechtambild.de: Unlizenzierte Veröffentlichung eines Fotos im Intranet unzulässig](https://www.rechtambild.de/2018/01/unlizenzierte-veroeffentlichung-eines-fotos-im-intranet-unzulaessig/)
- [ferner-alsdorf.de: Öffentlich zugänglich machen im Urheberrecht](https://www.ferner-alsdorf.de/urheberrechtsverletzung-wann-liegt-ein-offentliches-zuganglich-machen-vor/)
- [it-recht-kanzlei.de: Haftung für Hyperlinks (inkl. Hotlinking, LG München I)](https://www.it-recht-kanzlei.de/uebersicht-haftung-fuer-hyperlinks.html)
- [matutis.de: Logos in Thumbnails und Vorschaubildern – was ist erlaubt?](https://matutis.de/logos-in-thumbnails-und-vorschaubildern-was-ist-erlaubt/)
- [urheberrecht.de: Urheberrecht bei Logo & Markenzeichen](https://www.urheberrecht.de/logo/)
- [Wikipedia: Wikipedia:Logos](https://en.wikipedia.org/wiki/Wikipedia:Logos)
- [Wikidata: Property:P154 (logo image)](https://www.wikidata.org/wiki/Property:P154)
- [GitHub: simple-icons/simple-icons](https://github.com/simple-icons/simple-icons)
- [Logo.dev: Clearbit Logo API Alternative & Migration](https://www.logo.dev/clearbit)
- [HubSpot Changelog: Upcoming Sunset of Clearbit's Free Logo API](https://developers.hubspot.com/changelog/upcoming-sunset-of-clearbits-free-logo-api)
- [Medialesson: Use a hidden Google API to load favicons](https://medium.com/medialesson/use-a-hidden-google-api-to-load-favicons-fa945d0ba442)
- [DiceBear: Identicon – SVG Identicon API](https://www.dicebear.com/styles/identicon/)
- [journalistsresource.org: Researchers compare AI policies at 52 news organizations](https://journalistsresource.org/home/generative-ai-policies-newsrooms/)
- [mediacopilot.ai: AP doubles down on human oversight in updated AI newsroom rules](https://mediacopilot.ai/ap-ai-newsroom-standards-update/)
- [Fortune: AP AI guidelines – no publishable content/images](https://fortune.com/2023/08/17/associated-press-ai-guidelines-no-publishable-content-images)
- [Mux: A clear look at blurry image placeholders on the web (LQIP/BlurHash)](https://www.mux.com/blog/blurry-image-placeholders-on-the-web)
- [CSS Wizardry: The Ultimate Low-Quality Image Placeholder Technique](https://csswizardry.com/2023/09/the-ultimate-lqip-lcp-technique/)
- [Flowygo: Pillow – optimize images with Python](https://flowygo.com/en/blog/pillow-optimize-images-with-python/)
- [Schema.org: NewsArticle](https://schema.org/NewsArticle) / [Schema.org: image](https://schema.org/image)
- [Codemzy: Hosting images for a static site without bloating your Git repository](https://www.codemzy.com/blog/hosting-image-files-without-bloating-git)
- [digitalapplied.com: AI Image Generation API Pricing – 12 Providers Compared (2026)](https://www.digitalapplied.com/blog/ai-image-generation-api-pricing-comparison-2026)
