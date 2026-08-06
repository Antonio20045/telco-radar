# Lese- und Wahrnehmungspsychologie für den Telco-Radar-Bericht

Recherche-Grundlage für ein Redesign, Stand 2026-08-06. Ziel der Recherche:
die konkrete Beschwerde "man muss zu viel kognitiven Aufwand leisten, bevor
man überhaupt weiß, worum es in einem Artikel geht" mit Forschung
untermauern und daraus umsetzbare Regeln für die Explorer-Karten und den
Prosa-Bericht ableiten.

---

## 1. Eye-Tracking: Was zieht den Blick zuerst?

**Text schlägt Bild — auf Nachrichtenseiten, nicht generell.** Poynters
Eyetrack-III-Studie (2004, Blicklaufmessung auf echten Newsrooms) fand:
Fotos sind auf einer Nachrichten-Homepage in der Regel *nicht* der
Einstiegspunkt. Text dominiert sowohl bei der Reihenfolge als auch bei der
gesamten Betrachtungszeit. Dominante Überschriften ziehen den Blick zuerst
an — besonders oben links, oft auch oben rechts. Eine Überschrift bekommt im
Schnitt weniger als eine Sekunde Aufmerksamkeit; bei einer Liste von
Überschriften wird meist nur die linke Hälfte gelesen, der Rest wird
"amputiert" — die ersten zwei, drei Wörter müssen also bereits die Aussage
tragen.
[Poynter: Eyetrack III](https://www.poynter.org/archive/2004/eyetrack-iii-what-news-websites-look-like-through-readers-eyes/)

**Das F-Pattern** (Nielsen Norman Group, 2006, 232 Probanden mit
Eye-Tracker) beschreibt die dominante Scan-Bewegung auf Textseiten: ein
horizontaler Zug oben, ein kürzerer horizontaler Zug etwas weiter unten,
dann ein vertikaler Abstieg an der linken Kante. Praktische Folge: die
ersten zwei Absätze müssen die wichtigste Information tragen, und
Zwischenüberschriften/Aufzählungspunkte müssen mit dem informationstragenden
Wort beginnen, weil beim vertikalen Abstieg nur der linke Rand gescannt
wird. Eine Nacherhebung 2017 bestätigte das Muster nach elf Jahren
unverändert.
[NN/g: F-Shaped Pattern](https://www.nngroup.com/articles/f-shaped-pattern-reading-web-content-discovered/)

**Das Layer-Cake-Pattern** ist das Gegenstück für gut strukturierte Seiten
mit klar abgesetzten Zwischenüberschriften: Der Blick springt fast nur noch
auf die Überschriften/Zwischenüberschriften, mit vereinzelten Blicken in den
Fließtext dazwischen — im Blickpfad sichtbar als horizontale Streifen mit
Lücken dazwischen, wie bei einer Schichttorte. NN/g nennt es "neben dem
Wort-für-Wort-Lesen die effektivste Scan-Strategie" — Leser finden damit
fast immer, was sie suchen, *wenn* es auf der Seite steht. Voraussetzung:
Zwischenüberschriften müssen sich visuell klar vom Fließtext abheben (Größe,
Farbe, Schnitt), präzise und vorne-informativ formuliert sein, und das
Layout muss vorhersagbar/konsistent sein — unregelmäßige Layouts zwingen
zu mehr kognitiver Arbeit.
[NN/g: Layer-Cake Pattern](https://www.nngroup.com/articles/layer-cake-pattern-scanning/)

**Wie schnell fällt das Urteil "relevant/irrelevant"?** Lindgaard et al.
(2006, drei kontrollierte Experimente) zeigten, dass Menschen die visuelle
Attraktivität einer Webseite bereits nach **50 Millisekunden** Betrachtung
konsistent beurteilen — das Urteil bei 50 ms korrelierte hoch mit dem Urteil
bei 500 ms. Übertragen auf eine Artikelkarte heißt das: Layout, Bild und
Kontrastfarbe wirken, bevor überhaupt ein Wort gelesen wurde.
[Lindgaard et al. 2006, Behaviour & Information Technology](https://www.tandfonline.com/doi/abs/10.1080/01449290500330448)

---

## 2. Die Rolle von Bildern

**Picture-Superiority-Effekt:** Bilder werden laut Paivios
Dual-Coding-Theorie doppelt kodiert — als Bild *und* als Wort/Konzept —,
Text nur einfach. Das erklärt, warum Bilder besser erinnert werden als
reiner Text. NN/g benennt aber vier Bedingungen, unter denen der Effekt
überhaupt greift: das Bild muss lange genug betrachtet werden
(*discoverable*), es muss **konkret** statt abstrakt sein, ein
**vertrautes** Objekt zeigen, das sich leicht benennen lässt, und sich von
Nachbar-Bildern **unterscheiden**. 80 % der Betrachtungszeit einer Seite
entfallen laut derselben Quelle auf den Bereich oberhalb der Falz.
[NN/g: Picture-Superiority Effect](https://www.nngroup.com/articles/picture-superiority-effect/)

**Schlechte Bilder sind schlechter als keine Bilder.** NN/g hat in
separater Forschung zu dekorativen Bildern gezeigt: Nutzer ignorieren
"große, gefällige, rein dekorative Bilder" bewusst — vor allem, wenn sie
generisch und "wie Stockfotos" aussehen. Ein Bild ohne echten
Informationswert kostet Platz und Ladezeit, bringt aber keinen
Erinnerungs- oder Verständnisvorteil. Anders informationstragende Bilder
(Screenshots, Diagramme, Produktfotos, Logos, Portraits konkreter
Personen): die werden verarbeitet und helfen. Für einen B2B-Wettbewerbsradar
heißt das: ein generisches "Handy-in-Hand"-Stockfoto neben jeder Meldung ist
schlimmer als gar kein Bild — es kostet den Blick der ersten 50 ms, ohne
Information zu liefern, und trainiert den Leser, das Bildfeld generell zu
ignorieren ("Banner-Blindheit", siehe Abschnitt 6).
[NN/g: Decorative Images](https://www.nngroup.com/videos/decorative-images/)

---

## 3. Cognitive Load beim Scannen

**Chunking / Miller's Law:** George Millers klassische Arbeit (1956) zur
"magischen Zahl Sieben" wird in der UX-Praxis oft zitiert, ist aber laut
neuerer Forschung (Cowan) auf **etwa 4 ± 1 Chunks** zu revidieren, wenn man
für Chunking-Effekte kontrolliert. Die Chunk-*Größe* ist dabei fast egal —
entscheidend ist, dass verwandte Information zu einer Einheit gebündelt
wird. Für eine Artikelkarte bedeutet das eine harte Obergrenze: **eine
Karte sollte nicht mehr als etwa vier bis fünf eigenständige
Informationseinheiten** zeigen (z. B. Quelle, Zeit, Kernaussage, Warum-für-
Vodafone, Dringlichkeit) — jede weitere Einheit muss in eine der bestehenden
eingebettet werden, nicht als sechste addiert.
[NN/g: Chunking](https://www.nngroup.com/articles/chunking/)
[Laws of UX: Miller's Law](https://lawsofux.com/chunking/)

**Information Foraging Theory (Pirolli & Card, Xerox PARC, späte 1990er):**
Nutzer verhalten sich beim Navigieren wie Tiere bei der Nahrungssuche —
sie maximieren die *Rate* an gewonnener Information pro investierter Zeit,
nicht die absolute Menge. Die entscheidende Größe ist das **Information
Scent**: das (unvollständige) Signal über Wert und Relevanz einer Quelle,
das aus sichtbaren Hinweisreizen kommt — Titel, Bild, Linktext,
umgebender Kontext. Ist der "Duft" schwach oder widersprüchlich, brechen
Nutzer die Bewertung ab und wenden sich der nächsten Karte zu ("satisficing"
statt Optimieren). Für den Telco Radar folgt daraus: die Karte muss selbst
genug Scent tragen, dass die Managerin *ohne Klick* weiß, ob es für sie
relevant ist — Quelle, Betreiber/Themenfeld, Kernaussage und
Dringlichkeits-Signal müssen alle sichtbar sein, bevor überhaupt ein Klick
fällt.
[NN/g: Information Foraging](https://www.nngroup.com/articles/information-foraging/)
[Pirolli & Card, Original-Paper (PDF)](https://act-r.psy.cmu.edu/wordpress/wp-content/uploads/2012/12/280uir-1999-05-pirolli.pdf)

---

## 4. Headline-Verständlichkeit

Poynter (Abschnitt 1) belegt: nur die ersten paar Wörter werden beim
Scannen einer Liste tatsächlich gelesen. Daraus folgt zwingend: das
**Subjekt und die Kernaussage müssen an den Anfang**, nicht ans Ende eines
Nebensatzes. "Vodafone Italien senkt Prepaid-Tarife um 15 %" funktioniert,
"Nach monatelangen Verhandlungen: Vodafone Italien senkt..." nicht — der
entscheidende Fakt steht hinter dem Amputationspunkt.

Zur **Curiosity-Gap-Forschung**: eine Studie zu Clickbait und
Neugier-Lücken (Scacco/Bright u. a., zusammengefasst bei ScienceDirect)
zeigt, dass Curiosity-Gap-Headlines die Klickrate zwar kurzfristig heben
können, aber **nicht das Verständnis oder die langfristige Bindung** — und
wenn der Artikelinhalt die geweckte Erwartung nicht erfüllt, sinkt das
Vertrauen. Eine neuere Studie zu "headline concreteness" fand sogar einen
umgekehrten Effekt: zu abstrakte, auf Neugier zielende Headlines schneiden
bei der *Auswahlentscheidung* schlechter ab als konkrete. Für ein
Fachpublikum, das in Minuten scannt statt aus Unterhaltungsgründen klickt,
ist der Curiosity Gap also doppelt kontraproduktiv: er kostet Sekunden
(Entschlüsselungsaufwand) und bringt keinen Bindungsgewinn.
[ScienceDirect: Clickbait, relevance and the curiosity gap](https://www.sciencedirect.com/science/article/abs/pii/S0378216621000229)
[PMC: When curiosity gaps backfire](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11704130/)

---

## 5. Der Dek/Standfirst — die 1-2-Zeilen-Zusammenfassung

Ein Dek (US-Jargon) bzw. Standfirst (UK) ist die kurze, meist ein- bis
zweizeilige Erläuterung direkt unter der Headline, die den Kontext liefert,
den die Headline allein nicht tragen kann.

Axios' "Smart Brevity"-Format hat als Kernbaustein den Satz **"Why it
matters"** direkt nach der Headline. Die Begründung, mit der Axios das
vermarktet: Leser stellen sich beim ersten Blick auf eine Meldung zwei
Fragen — *Worum geht es? Ist das für mich relevant?* — und ein Format, das
diese beiden Antworten ganz vorne liefert, wird laut Axios' eigenen Zahlen
schneller verstanden und besser erinnert; das Unternehmen gibt eine
durchschnittliche Verkürzung der Lesezeit um 50 % bei gleichem
Informationsgehalt an. Diese Zahlen stammen aus Axios' eigenem Marketing-
/Trainingsmaterial (nicht aus einer unabhängigen Peer-Review-Studie) und
sollten entsprechend als Praxiserfahrung, nicht als akademischer Beleg
zitiert werden — die Grundlogik (Frage "worum geht's/warum wichtig" vorne
beantworten) deckt sich aber mit der Information-Scent-Forschung aus
Abschnitt 3.
[Axios/Journalism.co.uk: How Axios is reinventing text journalism](https://www.journalism.co.uk/how-axios-is-reinventing-text-journalism-with-smart-brevity/)
[Axios HQ: Smart Brevity 101 (PDF)](https://www.axioshq.com/hubfs/smart-brevity-101.pdf)

Unabhängig davon, methodisch sauberer belegt: Reuters-Institute-Forschung
(Digital News Report) identifiziert "die Nachricht wirkt nicht relevant für
mich" und "ich verstehe die Nachrichtenlage nicht" als zwei der
Hauptgründe für Nachrichtenvermeidung — unter 35-Jährige in UK vermeiden
News 4x häufiger aus Verständnisgründen als über 35-Jährige (12 % vs. 3 %).
Das stützt strukturell dieselbe Diagnose wie Antonios Beschwerde: fehlende
sofortige Einordnung ("warum ist das wichtig, und wichtig für wen") ist ein
harter Abbruchgrund, nicht nur ein Komfortmangel.
[Reuters Institute: People are turning away from the news](https://reutersinstitute.politics.ox.ac.uk/news/people-are-turning-away-news-heres-why-it-may-be-happening)

Zum Vielzitierten "80 % lesen die Headline, nur 20 % den Artikel" (oft auf
David Ogilvy zurückgeführt, in Kopie-Ratgebern als "Copyblogger-Zahl"
kursierend): Die Ursprungsquelle ist nicht sauber nachweisbar
(Marketing-Folklore, keine Studie mit Methodik). Als Illustration
brauchbar, nicht als belastbarer Beleg — im Bericht daher nicht als
Zahl zitieren, nur die Grundaussage (Headline + Dek tragen die Hauptlast der
Informationsübermittlung) übernehmen.

---

## 6. Relevanz-Signale: Farbe, Labels, Badges

**Banner-Blindheit** ist der Hauptgrund, warum reine Farbflächen/Badges
riskant sind: NN/g zeigt, dass Nutzer alles ignorieren, was wie Werbung
aussieht, an Werbung angrenzt oder an einer klassischen Werbeposition
sitzt — auch wenn es echter redaktioneller Inhalt ist. Das F-Pattern meidet
strukturell rechte Seitenspalten und Kopfbereiche, wo klassisch Werbung
sitzt. Folge fürs Redesign: ein Dringlichkeits-Badge darf nicht wie ein
Werbe-Sticker aussehen (kein Glanz-Icon, keine Ecke oben rechts, kein
"Sponsored"-Layout) — sonst wird er trainiert weggefiltert.
[NN/g: Banner Blindness Revisited](https://www.nngroup.com/articles/banner-blindness-old-and-new-findings/)

**Farbcodierung funktioniert, wenn sie auf ein etabliertes Schema
aufsetzt.** Ampel-Farbschemata (Rot/Gelb/Grün) sind in mehreren Domänen
(Ernährungskennzeichnung, Mensch-Maschine-Interaktion, Verkehrswarnungen)
nachweislich wirksamer als reiner Text oder reine Zahlen — sie verkürzen
Erkennungs- und Reaktionszeit messbar, weil die Bedeutung vor jeder
bewussten Verarbeitung kulturell bereits gelernt ist. Für den Telco Radar
heißt das: eine 1–5-Dringlichkeitsskala sollte sich in eine erkennbare
Ampel-/Wärme-Farblogik übersetzen (nicht nur eine Zahl in einem Kreis),
weil Farbe schneller verarbeitet wird als eine Zahl, die erst gelesen und
interpretiert werden muss.
[NCBI: Red for "Stop" — traffic-light labels](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7019506/)

Wichtige Einschränkung: Farbe allein darf nie der einzige Codierungskanal
sein (Rot-Grün-Sehschwäche, ~8 % der Männer) — Text-Label + Form/Icon +
Farbe zusammen, nie Farbe isoliert.

---

## 7. Deutschsprachige Besonderheiten

**Hamburger Verständlichkeitsmodell** (Langer, Schulz von Thun, Tausch,
frühe 1970er, bis heute Standardwerk der deutschen
Verständlichkeitsforschung): vier Dimensionen, auf einer Skala −2 bis +2
bewertet. Die zwei mit Abstand wichtigsten sind:
- **Einfachheit** — geläufige Wörter, kurze, geläufige Satzkonstruktionen,
  konkret statt abstrakt.
- **Gliederung/Ordnung** — erkennbare Struktur, logische Reihenfolge, roter
  Faden sichtbar.
Kürze/Prägnanz und "anregende Zusätze" (Beispiele, Bilder, wörtliche Rede)
wirken nur *zusätzlich* — ohne die ersten zwei Dimensionen bringen sie
nichts.
[Wortliga: Hamburger Verständlichkeitsmodell](https://wortliga.de/glossar/hamburger-verstaendlichkeitsmodell/)

**LIX (Läsbarhetsindex, Björnsson 1968)** funktioniert nachweislich auch
für Deutsch: LIX = durchschnittliche Satzlänge (Wörter/Satz) + Anteil
"langer" Wörter (> 6 Buchstaben) in Prozent. Niedrigerer Wert = besser
lesbar. Praktisch nutzbare Faustregeln aus verwandten
Verständlichkeitswerkzeugen: Sätze über 20 Wörtern und Wortgruppen über 12
Wörtern gelten als Warnschwelle.
[Psychometrica: LIX online berechnen](https://www.psychometrica.de/lix.html)
[FleschIndex.de: Lesbarkeitsindex-Übersicht](https://fleschindex.de/lesbarkeitsindex)

**Komposita sind das deutschspezifische Problem.** Verständlichkeitsforschung
zur Leichten Sprache belegt: die Fixationszeit beim Lesen steigt mit der
Wortlänge überproportional (nicht linear) — auch geübte Leser brauchen mit
wachsender Silbenzahl länger. Die Regelwerke der Leichten Sprache begegnen
dem, indem sie komplexe Komposita durch Bindestrich (Netzwerk Leichte
Sprache) oder Mediopunkt (Forschungsstelle Uni Hildesheim) in ihre
Bestandteile zerlegen, weil sichtbare Wortgrenzen die Blickerfassung
erleichtern. Für den Telco-Radar-Kontext (kein Leichte-Sprache-Text, aber
Laienpublikum) heißt das pragmatisch: Bandwurm-Komposita wie
"Netzausbaubeschleunigungsgesetz-Novelle" im Fließtext vermeiden oder beim
ersten Auftreten auflösen ("das Gesetz zum schnelleren Netzausbau"), statt
sie unkommentiert stehen zu lassen.
[Uni Hildesheim: Forschungsstand Leichte Sprache (PDF)](https://www.uni-hildesheim.de/media/fb3/uebersetzungswissenschaft/Leichte_Sprache_Seite/Publikationen/Antworten_zu_Leichter_Sprache__Forschungsstand/Forschung_gesamt.pdf)

---

## 8. Dark Mode & Lesbarkeit

Die Forschungslage ist differenzierter, als "Dark Mode ist schick" nahelegt:

- **Grundlagenforschung zur Displaypolarität** (Buchner & Baumgartner 2007;
  Piepenbrock et al. 2013, 169 Probanden über zwei Altersgruppen): **positive
  Polarität (dunkler Text auf hellem Grund) ist der negativen Polarität
  (heller Text auf dunklem Grund) beim Lesen konsistent überlegen** — bei
  jüngeren wie älteren Lesern, unabhängig von Umgebungslicht und Farbwahl.
  Erklärt wird der Effekt über die Pupillenreaktion: die größere Leuchtdichte
  heller Flächen verengt die Pupille, was ein schärferes Netzhautbild und
  damit bessere Detailwahrnehmung ergibt. In manchen Vergleichsstudien wird
  ein Rückgang der Lesegeschwindigkeit bei dunklem Hintergrund um bis zu
  26 % berichtet.
  [Piepenbrock et al. 2013 (PDF)](https://www.psychologie.hhu.de/fileadmin/redaktion/Oeffentliche_Medien/Fakultaeten/Mathematisch-Naturwissenschaftliche_Fakultaet/Psychologie/AAP/Publikationen/2013/Piepenbrock-2013-Positive_display_polarity_is_.pdf)
- **NN/g** fasst die Kontext-Abhängigkeit zusammen: in dunkler Umgebung
  reduziert Dark Mode Blendung, in heller Umgebung/Tageslicht führt Dark
  Mode zu "Washout" und Kontrastproblemen — entscheidend ist die Anpassung
  an das Umgebungslicht, nicht der Modus an sich.
  [NN/g: Dark Mode vs. Light Mode](https://www.nngroup.com/articles/dark-mode/)
- Zusätzlicher Faktor: bei 30–50 % der Erwachsenen mit Astigmatismus kann
  helle Schrift auf dunklem Grund als "ausblutend"/unscharf wahrgenommen
  werden ("halation"), was die Fokussierung zusätzlich erschwert.

**Einordnung für den Telco Radar:** Die Seite ist bewusst als
"Bloomberg-Terminal" positioniert (Dark Theme mit Light-Toggle, was laut
CLAUDE.md bereits vorhanden ist) — das ist eine legitime, gewollte
Markenentscheidung, kein Fehler. Die Forschung liefert aber zwei konkrete
Stellschrauben, die unabhängig vom generellen Farbschema gelten: (1) für
**längere Fließtext-Passagen** (Prosa-Wochenbericht) ist Kontrast und
Zeichenschärfe kritischer als für kurze Karten-Snippets — hier lohnt sich
ein geprüft hoher Kontrast und eine nicht zu dünne Schriftschnittwahl, um
den Polaritäts-Nachteil zu kompensieren; (2) der bereits vorhandene
Light-Toggle ist laut Forschungslage tatsächlich sinnvoll (Nutzer im hellen
Büro/Tageslicht sollten aktiv zu heller Darstellung wechseln können,
statt im Dark Mode zu verharren).

---

## 9. Anatomie eines Eintrags — abgeleitete Vorlage

Aus Abschnitt 1–8 ergibt sich diese Reihenfolge und Begründung pro Element
einer Explorer-Karte (und analog: eines Absatzes im Prosa-Bericht):

| # | Element | Zweck | Forschungsgrund |
|---|---|---|---|
| 1 | **Kontext-Icon/Farbfeld** (Region- oder Themen-Icon, kleine feste Fläche, keine Foto-Deko) | Sofortige Kategorisierung vor jedem Lesen ("worum geht's grob") | 50-ms-Ersteindruck (Lindgaard); Information Scent (Pirolli/Card) |
| 2 | **Dringlichkeits-Badge** (Farbe + Icon + Zahl, NIE nur Farbe) | "Ist das für mich wichtig?" beantworten, ohne Farbfehlsichtigkeit auszuschließen | Ampel-Farbcodierung (traffic-light research); Banner-Blindheit vermeiden durch redaktionelles statt werbeartiges Layout |
| 3 | **Betreiber/Quelle als Eyebrow-Zeile** (z. B. "VODAFONE ITALIEN · NEWSROOM") | Sofortige Einordnung "wer", bevor die Headline gelesen wird | F-Pattern: erste Fixation oben links; Information Scent |
| 4 | **Headline: Subjekt + Handlung + Zahl vorne, max. ~12 Wörter** | Amputationspunkt (nach 3–4 Wörtern) trägt bereits die Kernaussage | Poynter Eyetrack III: nur linke Hälfte der Headline wird gelesen |
| 5 | **Dek/"Warum wichtig für Vodafone" (1–2 Sätze, max. ~30 Wörter)** | Beantwortet sofort die Relevanzfrage, ohne Klick | Axios Smart Brevity; Reuters Institute (Verständnis als Abbruchgrund) |
| 6 | **Datum + Quellenlink** (klein, aber immer sichtbar) | Nachprüfbarkeit, ohne Aufmerksamkeit zu binden | Layer-Cake: Metadaten am Rand, nicht im Scan-Pfad |
| 7 | (nur bei Klick/Explorer-Detail) **Fließtext-Analyse mit Zwischenüberschriften** | Vertiefung für die, die weiterlesen wollen | Layer-Cake-Pattern; Chunking (max. 4–5 Infoeinheiten je Abschnitt) |

Kein Element aus Stockfoto-Bildern — wenn ein Bild verwendet wird
(Logo des Betreibers, ein Produktfoto, ein Netzwerk-Diagramm), muss es
*informationstragend* sein (Abschnitt 2), sonst schadet es mehr als ein
leeres Feld.

---

## 10. Checkliste: Regeln für Überschriften & Zusammenfassungen (Deutsch) — als LLM-Prompt-Regeln

```
HEADLINE (max. 12 Wörter):
- Subjekt zuerst, dann Handlung, dann Zahl/Ort. Nie mit Nebensatz, Datum
  oder "Nachdem..." beginnen.
- Konkretes Nomen statt Abstraktum: "Vodafone senkt Tarif" statt
  "Preisentwicklung bei Vodafone".
- Wenn eine Zahl im Artikel steckt (Prozent, Betrag, Anzahl Länder), gehört
  sie in die Headline, nicht nur in den Fließtext.
- Keine Bandwurm-Komposita ohne Not; wenn nötig, per Bindestrich in
  Bestandteile zerlegen ("Netzausbau-Beschleunigungsgesetz").
- KEIN Curiosity Gap ("Was Vodafone jetzt plant, überrascht") — das
  Fachpublikum liest zum Verstehen, nicht zum Unterhalten; ungedeckte
  Neugier kostet Vertrauen und bringt keinen Verständnisgewinn.
- Keine Superlative/Intensivierer ohne Beleg ("massiv", "revolutionär") —
  klassisches Clickbait-Signal, senkt Glaubwürdigkeit bei Fachpublikum.

DEK / "WARUM WICHTIG" (1–2 Sätze, max. 30 Wörter):
- Beantwortet explizit: Was ist passiert? Warum ist es für Vodafone
  relevant? (Beide Fragen, nicht nur eine.)
- Keine neuen Fachbegriffe ohne Erklärung in Klammer.
- Aktiv statt Passiv, wo möglich ("X kündigt Y an" statt "Y wurde von X
  angekündigt").
- Sätze unter 20 Wörtern, Wortgruppen unter 12 Wörtern (LIX-Faustregel).

ALLGEMEIN:
- Jede Aussage im Fließtext bekommt einen Quellenlink am Satzende oder
  Absatzende (Nachprüfbarkeit).
- Zwischenüberschriften im Fließtext beginnen mit dem informationstragenden
  Wort (nicht "Außerdem" oder "Zudem").
- Ein Abschnitt/eine Karte transportiert nicht mehr als 4-5 eigenständige
  Informationseinheiten (Quelle, Kernfakt, Grund, Dringlichkeit, Datum
  zählen bereits als 5).
```

---

## 11. Anti-Patterns (was vermeiden)

- **Generische Stockfotos** neben jeder Meldung — werden ignoriert
  (Banner-Blindheit) oder schlimmer: sie verbrauchen die 50-ms-
  Ersteindrucks-Chance ohne Informationsgewinn.
- **Curiosity-Gap-Headlines** ("Diese Entscheidung überrascht Experten") —
  für Fachpublikum kontraproduktiv, senkt Vertrauen ohne Verständnisgewinn.
- **Headline mit Nebensatz/Datum vorne** ("Am Dienstag teilte Vodafone
  mit, dass...") — der Amputationspunkt beim Scannen liegt vor der
  eigentlichen Aussage.
- **Badge/Label, das wie Werbung aussieht** (Glanzeffekt, obere rechte
  Ecke, "Sponsored"-ähnliches Layout) — wird durch gelernte
  Banner-Blindheit ignoriert, auch wenn es redaktioneller Inhalt ist.
- **Farbe als einziger Codierungskanal** für Dringlichkeit — schließt
  rot-grün-sehschwache Leser aus (~8 % der Männer) und ist zu schwach ohne
  Text/Icon-Verstärkung.
- **Mehr als ~5 Informationseinheiten pro Karte** — überschreitet die
  Chunking-Kapazität des Arbeitsgedächtnisses (Miller/Cowan), zwingt zu
  erneutem Scannen statt einmaligem Erfassen.
- **Bandwurm-Komposita unaufgelöst im Fließtext** — überproportional
  steigende Fixationszeit bei langen Wörtern, besonders relevant für ein
  explizit "laienverständliches" Zielformat.
- **Unregelmäßiges Karten-/Abschnittslayout** — bricht das Layer-Cake-
  Scanning, zwingt zu bewusster statt automatischer Verarbeitung.
- **Dunkler Fließtext-Hintergrund bei langen Prosa-Passagen ohne
  kompensierenden Kontrast/Schriftschnitt** — Polaritätsforschung zeigt
  messbaren Lesegeschwindigkeits-Nachteil bei negativer Polarität,
  besonders relevant für den mehrminütigen Prosa-Wochenbericht (im
  Unterschied zu kurzen Karten-Snippets).

---

## 12. Quellenliste

1. Poynter — Eyetrack III (2004): https://www.poynter.org/archive/2004/eyetrack-iii-what-news-websites-look-like-through-readers-eyes/
2. Nielsen Norman Group — F-Shaped Pattern (Original-Eyetracking-Studie, 2006, mit 2017er Nacherhebung): https://www.nngroup.com/articles/f-shaped-pattern-reading-web-content-discovered/
3. Nielsen Norman Group — Layer-Cake Pattern of Scanning: https://www.nngroup.com/articles/layer-cake-pattern-scanning/
4. Nielsen Norman Group — Eyetracking Study of Web Readers (Textanteil, der gelesen wird): https://www.nngroup.com/articles/eyetracking-study-of-web-readers/
5. Nielsen Norman Group — Picture-Superiority Effect: https://www.nngroup.com/articles/picture-superiority-effect/
6. Nielsen Norman Group — Decorative Images (Video/Studie): https://www.nngroup.com/videos/decorative-images/
7. Nielsen Norman Group — Chunking: https://www.nngroup.com/articles/chunking/
8. Nielsen Norman Group — Information Foraging: https://www.nngroup.com/articles/information-foraging/
9. Pirolli & Card — Information Foraging (Originalarbeit, PARC, PDF): https://act-r.psy.cmu.edu/wordpress/wp-content/uploads/2012/12/280uir-1999-05-pirolli.pdf
10. Nielsen Norman Group — Banner Blindness Revisited: https://www.nngroup.com/articles/banner-blindness-old-and-new-findings/
11. Lindgaard, Fernandes, Dudek, Brown (2006) — "Attention Web Designers: You Have 50 Milliseconds...", Behaviour & Information Technology 25(2): https://www.tandfonline.com/doi/abs/10.1080/01449290500330448
12. Axios/journalism.co.uk — How Axios is reinventing text journalism with Smart Brevity: https://www.journalism.co.uk/how-axios-is-reinventing-text-journalism-with-smart-brevity/
13. Axios HQ — Smart Brevity 101 (PDF): https://www.axioshq.com/hubfs/smart-brevity-101.pdf
14. ScienceDirect — "You won't believe what's in this paper! Clickbait, relevance and the curiosity gap": https://www.sciencedirect.com/science/article/abs/pii/S0378216621000229
15. PMC — "When curiosity gaps backfire: effects of headline concreteness": https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11704130/
16. Reuters Institute — "People are turning away from the news. Here's why it may be happening": https://reutersinstitute.politics.ox.ac.uk/news/people-are-turning-away-news-heres-why-it-may-be-happening
17. NCBI/PMC — "Red for 'Stop': Traffic-Light Nutrition Labels...": https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7019506/
18. Wortliga — Hamburger Verständlichkeitsmodell: https://wortliga.de/glossar/hamburger-verstaendlichkeitsmodell/
19. Psychometrica — LIX-Lesbarkeitsindex online berechnen: https://www.psychometrica.de/lix.html
20. FleschIndex.de — Lesbarkeitsindex-Formeln im Überblick: https://fleschindex.de/lesbarkeitsindex
21. Universität Hildesheim, Forschungsstelle Leichte Sprache — Forschungsstand-Übersicht (PDF): https://www.uni-hildesheim.de/media/fb3/uebersetzungswissenschaft/Leichte_Sprache_Seite/Publikationen/Antworten_zu_Leichter_Sprache__Forschungsstand/Forschung_gesamt.pdf
22. Piepenbrock, Mayr, Mund, Buchner (2013) — "Positive display polarity is advantageous for both younger and older adults" (PDF): https://www.psychologie.hhu.de/fileadmin/redaktion/Oeffentliche_Medien/Fakultaeten/Mathematisch-Naturwissenschaftliche_Fakultaet/Psychologie/AAP/Publikationen/2013/Piepenbrock-2013-Positive_display_polarity_is_.pdf
23. Nielsen Norman Group — Dark Mode vs. Light Mode: https://www.nngroup.com/articles/dark-mode/

*Hinweis zur Quellenlage:* Punkte 12/13 (Axios) sind Herstellerangaben aus
eigenem Trainingsmaterial, keine unabhängige Studie — als Praxisbeleg,
nicht als akademischer Nachweis zu werten. Alle übrigen Quellen sind
entweder akademisch (peer-reviewed) oder stammen aus der methodisch
transparenten NN/g-Eyetracking-Reihe bzw. dem Reuters Institute (Oxford).
