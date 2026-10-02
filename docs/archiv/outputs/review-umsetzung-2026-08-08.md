# Schlussliste: Umsetzung des Review-Dokuments vom 8. August 2026

Grundlage ist das Review „Telco Radar — Review der bestehenden Seite und
Feature-Roadmap" (08.08.2026). Diese Liste sagt zu jedem Punkt, was gebaut
wurde, was gemessen wurde und was **nicht** gebaut wurde — mit Grund.

Stand am Ende: **870 Tests**, alle **14 Prüfungen von
`scripts/pruefe_portal.py`** grün, **207 crawlbare Quellen**.

---

## Teil A — die Befunde zur bestehenden Seite

| Befund | Ergebnis |
|---|---|
| **A1 Ereignis-Dubletten** (7 Cluster, 17 Meldungen auf 7) | **behoben** (K1). Über drei echte Ausgaben nachgemessen: der deterministische Vorfilter allein bündelt 2, 9 und 11 Meldungen, ohne einen falschen Treffer |
| **A2 fehlende CTM-Linse** | **behoben** (K2). Zweite Achse, Sortierung davor, Konsequenzsatz, Zwei-Minuten-Pfad, Prüflauf |
| **A3 Quellenlücken** | teils behoben, teils **widerlegt** — siehe unten |
| **A4 keine Zeitachse, kein Eigenbezug** | **behoben** (Verlauf + Lücken-Ansicht + „Neu seit der letzten Ausgabe") |
| **A5 Layout** | **behoben** (Mobil-Navigation, leere Hero-Spalte, Zwei-Minuten-Pfad statt 16 Minuten Lesezeit) |
| **A6 Betrieb** | teils erledigt, teils **war schon anders** — siehe unten |

### A3 im Einzelnen — was gemessen wurde

Das Review nennt drei 403-Quellen und vermutet einen User-Agent-Filter.
Nachgemessen:

* **ISPreview UK und MediaNama antworten mit 200** — aus dieser Umgebung, mit
  und ohne Client-Hints. Ihr Ausfall war nicht der User-Agent.
* **Telecompetitor antwortet auf JEDE Variante mit 403**: voller
  Client-Hint-Satz, nackter Browser-UA, Googlebot-UA, HTTP/2, ohne Referer.
  Das ist eine Sperre gegen den IP-Bereich. Kein Kopfzeilentrick löst sie;
  die Quarantäne mit Bewährungsabruf ist die richtige Antwort und steht
  bereits.
* **NTIA / `CERTIFICATE_VERIFY_FAILED`**: kein Problem der Quelle, sondern
  des Zertifikatsspeichers im Runner-Image. TLS prüft jetzt gegen `certifi`.

Der moderne Kopfzeilensatz ist trotzdem eingebaut (er kostet nichts), und
`Accept-Language` führt jetzt Deutsch — die Quellenliste ist seit Session 5
mehrsprachig, und eine inhaltsverhandelnde Seite gab bisher ihre englische
Fassung heraus.

**Die Deckelung** war real und ist behoben: die zehn ergiebigsten Quellen
lieferten exakt 40 Meldungen, also den Deckel und nicht ihren Bestand.
Jetzt 60, einstellbar.

**Das o2-RSS ist kein Quick Win** — die drei ergiebigen Rubriken stehen seit
Längerem in der Watchlist. Die vier weiteren Rubriken sind geprüft und
**durchgefallen**: sauber datiert, aber ohne eine einzige Meldung im
Frischefenster.

**Neu abgenommen:** Bundesnetzagentur (Pressemitteilungen) und BREKO. Die
BNetzA hat gefehlt, weil ihr Feed *weder* `pubDate` *noch* `dc:date` trägt —
alle 50 Meldungen galten als undatiert, und undatiert heißt unsichtbar. Seit
`collect/rss.py` das Datum notfalls aus dem **Link** liest
(`/Pressemitteilungen/DE/2026/20260806_…`), sind es 10 von 10.

**Bewusst nicht aufgenommen trotz bestandenem Check** (der prüft Form, nicht
Wert): Bundeskartellamt (allgemeine Wettbewerbsbehörde — dieselbe Begründung,
aus der in Session 4 die spanische CNMC fiel), Deutsche Glasfaser
(Ratgeberblog), Golem (stand schon als abgelehnt im YAML).

**Der MVNO-Befund ist widerlegt.** Das Review hält „8 gelesen, 0 relevant"
für unplausibel. Nachgeprüft: zwölf Firmen mechanisch gesucht, neun
Kandidaten geprüft, zwei bestanden den Check — und beide fielen an der
Wertfrage (Holafly ist ein Reiseblog mit SEO-Inhalten, Thales der Sammelfeed
eines Rüstungskonzerns). Die Nullausbeute liegt nicht an fehlenden Quellen:
die konfigurierten sind Zuliefererfeeds, und der Analyst bewertet ihre
Produktmeldungen zu Recht unter Relevanz 2. Die Endkundenbewegung findet in
der Fachpresse statt, und die steht bereits im Bestand. Alle durchgefallenen
Adressen stehen mit Grund im YAML.

### A6 — was schon anders war

Das Review nennt „27,4 Minuten bei 35 Minuten Job-Timeout". **Das Timeout
liegt seit Längerem bei 50 Minuten** (`radar.yml`), und `llm_max_workers`
steht auf 3, nicht auf 2. Der Druck ist damit geringer als beschrieben;
zusätzlich nimmt das Ereignis-Clustering Last aus der Analysestufe. An den
Nebenläufigkeiten wurde deshalb nichts gedreht — eine Erhöhung ohne
gemessenen Engpass handelt sich nur 429er ein.

---

## Teil B/C — die Roadmap

### Stufe 1

| # | Feature | Status |
|---|---|---|
| 1 | Ereignis-Clustering | **gebaut** — `analyze/clustering.py` |
| 2 | CTM-Relevanzlinse + Konsequenzsatz | **gebaut** — `analyze/ctm.py`, `analyze/faithfulness.py`, `config/ctm_fokus.yaml` |
| 3 | Quellen-Reparatur + Deutschland-Paket | **gebaut**, mit den Korrekturen oben |
| 4 | Zwei-Minuten-Pfad | **gebaut** — ganz oben auf der Startseite |

### Stufe 2

| # | Feature | Status |
|---|---|---|
| 5 | Lieferzeit-Radar | **gebaut** — `collect/lieferzeit.py`, eigene Seite |
| 6 | Tarif-Änderungsradar | **gebaut** — `collect/aenderungen.py`, 16 Seiten |
| 7 | Differenzierungs-Gap-Analyse | **gebaut** — `report/luecken.py` (Konfiguration bewusst leer, siehe unten) |
| 8 | Push-Digest | **gebaut** — `versand.py`, Mail montags + Teams nur für Ausnahmen |

### Stufe 3

| # | Feature | Status |
|---|---|---|
| 9 | Zeitreihen | **gebaut** — `report/verlauf.py`, Abschnitt „Was wächst, was kippt" |
| 10 | Archiv-Dialog (RAG) | **nicht gebaut** — Grund unten |
| 11 | Frühwarn-Board | **gebaut** — `report/fruehwarnung.py`, 5 Fragen, 12 Indikatoren |
| 12 | Wettbewerber-Steckbrief | **gebaut** — die fehlenden Teile (Hebel je Wettbewerber, offene Flanken) ergänzt |
| 13 | Kundenstimme-Radar | **nicht gebaut** — Grund unten |

---

## Die vier Messungen, die etwas anderes ergaben als erwartet

1. **JSON-LD trägt die Lieferzeit nicht.** Das Review setzt auf
   `OfferShippingDetails` als stabilste Stufe und lässt offen, ob die Shops
   es einbinden — „davon hängt der halbe Aufwand ab". Gemessen: winSIM
   liefert ein sauberes `Product` samt `Offer`, aber **ohne**
   `OfferShippingDetails` und ohne `deliveryTime`; otelo trägt seine Zustände
   in einem JavaScript-Wörterbuch mit Platzhaltern
   (`Lieferzeit ca. {DELIVERY_TIME} Tage`). Die Stufe bleibt im Code (sie
   kostet nichts und ist die richtige), die Arbeit liegt beim Text und beim
   gerenderten DOM.
2. **Telecompetitor ist eine IP-Sperre, kein UA-Filter** (siehe A3).
3. **Der MVNO-Befund ist widerlegt** (siehe A3).
4. **Nur 8 der 16 Tarifseiten liefern ihre Preise im HTML.** telekom.de
   antwortet mit dem bekannten HTTP-202-Challenge, congstar und Lidl Connect
   bauen ihre Tabelle per JavaScript auf. Daraus ist eine Regel geworden:
   unter zehn erkannten Werten gilt eine Seite als JS-gebaut und wird
   übersprungen — eine echte Preistabelle bringt 16 bis 54 Werte, eine
   JS-Seite drei aus dem Fließtext.

---

## Was bewusst nicht gebaut wurde

**Archiv-Dialog (RAG, #10).** Die Retrieval-Schicht braucht einen Dienst,
der zur Laufzeit ein Modell aufruft. Die Website ist eine Render **Static
Site** ohne Backend — das ist keine Sparmaßnahme, sondern die Bedingung
dafür, dass sie nie einschläft (CLAUDE.md §8). Ein Archiv-Dialog hieße
entweder einen Web Service (schläft ein, kostet) oder einen API-Schlüssel im
Browser (nicht vertretbar). Die Vorstufe steht: `search_index.json` trägt
seit dem 08.08. alle Ausgaben, die Differenzierung und die Promo-Aktionen,
und `suche.html` beantwortet „was weiß das Portal über mein Thema" bereits
als Dossier mit Verlauf. Der Dialog darüber ist eine
Architekturentscheidung, keine Programmieraufgabe.

**Kundenstimme-Radar (#13).** Das Review selbst nennt es „technisch machbar,
aber mit Vorbehalten". Für App-Store-Bewertungen gibt es keinen offiziellen
Zugang für **fremde** Apps; was bliebe, wäre Scraping gegen die
Nutzungsbedingungen der Stores — dieselbe Grenze, an der im Review schon
Trustpilot gescheitert ist. Nicht gebaut, und aus demselben Grund nicht als
„später" markiert.

**Die Vodafone-Hebel-Liste ist leer ausgeliefert.** `config/vodafone_hebel.yaml`
kennt alle zwölf Hebel, und alle stehen auf `offen`. Das ist die Anwendung
der eigenen Regel des Review-Dokuments: „Die Aussage ‚wir haben das nicht'
muss aus der gepflegten Liste kommen, nie aus einer LLM-Vermutung." Hier
kannte niemand das Vodafone-Portfolio belastbar, also steht dort nichts. Die
Seite funktioniert vollständig und sagt bei jedem Hebel ehrlich „noch nicht
erfasst" — sie behauptet keine Lücke, die niemand geprüft hat. Ausfüllen ist
zwölf Zeilen Handarbeit und der einzige Teil dieses Projekts, den kein
Crawler beantworten kann.

**Teil D wurde eingehalten.** Meta Ad Library, Google Ads Transparency
Center, Trustpilot, X-API, Reddit im großen Stil, Similarweb, Battlecards im
Vertriebssinn und ein Mehrfaktor-Score für Meldungen sind nicht gebaut — die
Begründungen des Review-Dokuments stehen jetzt in CLAUDE.md §6, damit die
Ideen nicht in sechs Wochen wiederkommen.

---

## Was nach dem nächsten Actions-Lauf zu prüfen ist

1. **Der Prüflauf gegen den Originaltext** (`analyze/faithfulness.py`) ist
   noch nie gegen ein echtes Modell gelaufen. Im Protokoll die Zeile
   `CTM-Linse:` ansehen: wie viele Folgerungssätze belegt sind und wie viele
   fallen. Fallen fast alle, stimmt etwas mit dem Prompt nicht; fällt keiner,
   ist die Prüfung zu milde.
2. **Die Ereignis-Prüfung im Graubereich** (`Ereignis-Pruefung:` im
   Protokoll): wie viele Zweifelsfälle gefragt und wie viele
   zusammengelegt wurden. Legt das Modell fast alles zusammen, ist die
   Schwelle zu tief.
3. **Der Versand.** Ohne die Secrets (`SMTP_HOST`, `MAIL_FROM`, `MAIL_TO`,
   `TEAMS_WEBHOOK`) schreibt der Lauf „FEHLER: … fehlen" ins Protokoll und
   verschickt nichts — das ist Absicht. Wer den Kanal will, legt die Secrets
   an; ein Trockenlauf geht mit
   `python -m telco_radar.versand --trocken --erzwinge --zeige`.
4. **Die vier telekom.de-Tarifseiten und die JS-Seiten des
   Lieferzeit-Radars.** In Actions rendert Playwright; lokal nicht. Im
   Protokoll `Aenderungsradar:` und `Lieferzeit-Radar:` ansehen.
5. **Die Vorgabe-Region** (`region:` in `news_sources.yaml`): ob Europa,
   Lateinamerika, Asien und Afrika jetzt eigene bewertete Meldungen haben,
   statt dass alles unter „Global" landet. Das war der erste der vier
   Schritte aus CLAUDE.md §9 und ist damit abgearbeitet.
