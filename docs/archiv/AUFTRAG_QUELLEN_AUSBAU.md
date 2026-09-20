# Auftrag für die nächste Session: großer Quellen-Ausbau

> Dieser Text IST der Auftrag. Lies zuerst `CLAUDE.md` (Architektur, Zugänge,
> Fallstricke), dann diesen Auftrag. Er ist bewusst streng formuliert, weil die
> Quellen danach **stimmen sollen** — nicht in ein paar Tagen erneut
> nachgebessert werden.

---

## 1. Warum

Der Radar beobachtet 81 Netzbetreiber, aber **80 davon über genau eine
Website**. Von einer einzigen Seite alle relevanten Meldungen eines Konzerns zu
erwarten, ist unrealistisch: Presse-Newsroom, Investor Relations, Technik-Blog
und Landesgesellschaften veröffentlichen Unterschiedliches, und oft steht die
interessanteste Meldung genau nicht im Presseraum.

Zweitens ist der Blick zu eng. Was den Telco-Markt gerade verändert, kommt
zunehmend von außerhalb: KI-Anbieter, Geräte- und Chip-Hersteller,
Netzausrüster, Satellitenbetreiber, Regulierung.

**Ziel:** deutlich mehr Abdeckung, ohne einen einzigen unbrauchbaren Eintrag.

## 2. Ist-Zustand (gemessen am 04.08.2026, Lauf #66)

| | |
|---|---|
| Betreiber | 81 in 6 Regionen |
| Quellen je Betreiber | **80× genau eine**, 1× zwei |
| Quellenarten | 20 rss, 13 json_api, 33 newsroom, 11 newsroom_js, 5 official (nicht crawlbar) |
| Fachpresse | 14 Feeds (`config/news_sources.yaml`) |
| Letzter Lauf | 91 Quellen, 88 mit Inhalt, 1 leer (Telecom Argentina), 2 Fehler (Telecompetitor 403, Telecoms Tech News WAF-Captcha) |
| Anbieter | DeepSeek (`llm_provider: deepseek`), flash für Analysten, pro für Redaktion |

## 3. Was gebaut werden soll

### 3.1 Mehrere Quellen je Betreiber

Für **jeden** Betreiber prüfen, welche zusätzlichen eigenen Kanäle es gibt:

- Presse-/Newsroom (meist vorhanden — das ist die bestehende Quelle)
- **Investor Relations / Ad-hoc-Mitteilungen** — dort stehen Zahlen, Zukäufe,
  Strategiewechsel, oft Wochen vor der Pressemitteilung
- **Technik-/Netz-Blog** (z. B. „Netz-Update", „Engineering Blog")
- **Landesgesellschaften** bei Konzernen (Vodafone DE/UK/ES, Telefónica
  O2/Movistar/Vivo, Orange FR/PL/ES, …) — die berichten anderes als die Holding
- **Produkt-/Tarif-Newsroom**, wo getrennt geführt

Richtwert: **2–4 Quellen je Betreiber**. Kein Zwang zur Zahl — lieber zwei gute
als vier, von denen zwei nichts liefern. Für die fünf nicht crawlbaren
Betreiber (`type: official`: TIM, Cosmote, UScellular, Ooredoo, Maroc Telecom)
gilt: **jetzt ist die Gelegenheit**, einen erreichbaren Ersatzkanal zu finden
(IR-Seite, Konzernmutter, Landesableger, Wire-Service). Maroc Telecom, Cosmote
und UScellular sind laut Messung echte blinde Flecken — sie kommen in 1611
gesammelten Meldungen **kein einziges Mal** vor.

### 3.2 Neue Themenfelder

Neben den Betreibern sollen folgende Bereiche dazu. Jeweils die **offiziellen
eigenen Kanäle** (Blog/Newsroom/Feed), nicht Presse-über-sie:

- **KI-Anbieter:** OpenAI, Anthropic, Google DeepMind / Gemini, Meta AI,
  Mistral, xAI, DeepSeek, Alibaba Qwen, Microsoft AI, Nvidia
- **Geräte:** Apple, Samsung, Google (Pixel), Xiaomi, Honor, Motorola/Lenovo
- **Chips/Modems:** Qualcomm, MediaTek, Arm, Broadcom
- **Netzausrüster:** Ericsson, Nokia, Huawei, ZTE, Samsung Networks, Ciena
- **Satellit / NTN:** Starlink, AST SpaceMobile, Lynk, Eutelsat/OneWeb, Iridium
- **Regulierung & Verbände:** GSMA, EU-Kommission (DG CNECT), BNetzA, Ofcom,
  FCC, BEREC

Weitere Vorschläge sind erwünscht, wenn sie sich begründen lassen. Naheliegend:
Cloud-Hyperscaler (AWS/Azure/GCP Telecom-Blogs), eSIM-/MVNO-Plattformen,
Zahlungsdienste im Mobilfunk, Kabel-/Glasfaserverbände.

**Wichtige Designentscheidung, die du treffen und begründen musst:** Diese
Quellen sind keine „Betreiber". Sie brauchen einen eigenen Platz im Modell —
z. B. `config/tech_sources.yaml` analog zu `news_sources.yaml`, mit einem
Themen-Tag statt einer Region, plus Anzeige im Bericht und auf `sources.html`.
Nicht in die Betreiber-Watchlist quetschen: Region-Logik, Alias-Tagging und die
Rundlauf-Sortierung erwarten dort Betreiber. Prüfe, was `pipeline.py`,
`report/html.py` und die Templates dafür brauchen, und ändere es sauber mit.

## 4. Harte Abnahmekriterien — jede einzelne neue Quelle

Eine Quelle darf nur in die Konfiguration, wenn **alle** Punkte erfüllt sind.
Belegt heißt: mit echtem Abruf gemessen, nicht plausibel begründet.

1. **Abrufbar über den Projekt-Collector**, also
   `telco_radar.collect.collect_source(...)` — **nicht** über ein selbst
   geschriebenes Skript mit eigenem User-Agent, eigenen Headern oder eigenem
   Parser. In der letzten Session haben Agents Vorschläge als „verifiziert"
   gemeldet, die über den echten Collector 0 Items lieferten. Das ist der
   teuerste Fehler in diesem Projekt und darf sich nicht wiederholen.
2. **≥ 5 Meldungen** im Abruf.
3. **≥ 80 % davon mit erkanntem `published`-Datum.** Eine undatierte Meldung
   sortiert ans Ende und ist faktisch unsichtbar — prüfe `published`, nicht nur
   ob Items ankommen.
4. **≥ 1 Meldung im Frischefenster** (`lookback_days`, aktuell 8) ODER eine
   belegte Begründung, warum die Quelle trotzdem wertvoll ist (z. B. IR-Seite
   mit seltenen, aber gewichtigen Meldungen). Begründung gehört als Kommentar
   ins YAML.
5. **Titel sind echte Überschriften** — keine Navigationslabels („Mehr
   erfahren", „Presse"), keine Datumszeilen, keine Cookie-Banner-Texte. Stichprobe
   von 3 Titeln je Quelle ins Protokoll.
6. **Eigene Domain des Unternehmens.** Ausnahmen (Cision, Businesswire, mfn.se,
   GlobeNewswire) sind erlaubt, müssen aber im YAML kommentiert sein.
7. **Keine Dublette.** Gegen alle bestehenden Quellen prüfen, URL-normalisiert.
   Zwei Pfade derselben Seite mit demselben Inhalt sind eine Quelle, nicht zwei.
8. **Kein `newsroom_js`, wenn es anders geht.** Suche zuerst den darunter
   liegenden Endpunkt: `__NEXT_DATA__`, `/wp-json/wp/v2/posts`, `?format=feed`,
   `/api/...`, JSON in HTML-Attributen. In Session 2 waren 6 von 8 angeblich
   „JS-toten" Quellen in Wahrheit statisch abrufbar. `newsroom_js` ist in der
   Sandbox **nicht testbar** (kein Netz für Chromium) — eine solche Quelle
   kannst du also gar nicht abnehmen und musst sie als unbelegt kennzeichnen.

## 5. Vorgehen

Frei in der Wahl — dynamischer Workflow, Agent-Teams oder eine Mischung. Bindend
ist nur:

- **Token-effizient, hybrid.** Billiges Modell für Breitensuche, Abruf-Tests und
  mechanische Prüfungen; teures Modell nur für Bewertung, Zweifelsfälle und
  Synthese. Nicht alles auf dem großen Modell laufen lassen.
- **Verifikation ist eine eigene Stufe** und wird **nicht** von demselben Agent
  gemacht, der die Quelle vorgeschlagen hat. Vorschlagender Agent = Anwalt,
  prüfender Agent = Skeptiker mit dem Auftrag zu widerlegen.
- **Zentraler Abnahme-Check im Code, nicht im Modell.** Schreibe ein Skript
  (z. B. `scripts/pruefe_quellenvorschlag.py`), das eine vorgeschlagene Quelle
  durch `collect_source` schickt und die Kriterien aus Abschnitt 4 maschinell
  prüft. Nur was dort durchgeht, kommt in die Watchlist. Ein Modell, das „ich
  habe es geprüft" sagt, zählt nicht.
- **Erst sammeln, dann eintragen.** Kein Vorschlag geht direkt in die YAML.

## 6. Fallstricke (alle in früheren Sessions teuer gelernt)

- `config/watchlist.yaml` ist die **Wahrheitsquelle** und wird direkt editiert.
  `scripts/build_sources.py` ist gesperrt — es würde `item_selector`,
  `link_template`, `timeout_seconds`, `allow_short_titles` verlieren.
- **State nie lokal committen.** Nach lokalen Testläufen `data/state/` und
  `data/reports/` mit `git checkout --` verwerfen, sonst findet der
  Actions-Lauf „0 neue Items".
- **Sandbox:** aarch64, `pip --break-system-packages`, Bash-Aufrufe max ~45 s →
  lange Läufe im Hintergrund oder über GitHub Actions.
- **Kein Headless-Browser im Netz** (Proxy blockt Chromium). `newsroom_js`
  erscheint lokal immer als FAIL, läuft in Actions aber normal.
- **Seen-Store ist ein Einbahnschild.** Was hineingeht, kommt nie wieder. Seit
  Lauf #64 gibt es einen Schutz für komplett ausgefallene Regionen — verlass
  dich nicht darauf, sondern denk bei jeder Änderung an den Effekt auf `seen.jsonl`.
- Der GitHub-API-Zugriff läuft über die MCP-Werkzeuge; direkte `api.github.com`-
  Aufrufe sperrt der Proxy. **Secrets kann der Agent nicht setzen** — dafür
  Antonio bitten.

## 7. Was zusätzlich zu bedenken ist

- **Kosten und Laufzeit.** Mehr Quellen heißt mehr gesammelte Meldungen, damit
  mehr Analysten-Stapel. Aktuell ~1580 gesammelte Meldungen je Lauf bei 11,5 min
  Laufzeit; das Job-Timeout liegt bei 50 min. Schätze vorab, wie sich die
  geplante Zahl neuer Quellen auswirkt, und sag es in der Zusammenfassung. Falls
  es eng wird: lieber die Sammelparallelität erhöhen als eine Kappung einführen —
  **Kappungen sind ausdrücklich unerwünscht**, jede neue Meldung soll bewertet
  werden.
- **Erster Lauf nach dem Ausbau wird groß.** Alle neuen Quellen liefern ihr
  ganzes Frischefenster auf einmal. Das ist einmalig und in Ordnung, aber plane
  es ein.
- **Der Bericht muss lesbar bleiben.** Wenn KI- und Hardware-Meldungen dazukommen,
  darf der Wochenbericht nicht zur Linkliste werden. Überlege, ob die neuen
  Themenfelder einen eigenen Abschnitt bekommen (Editor-Prompt in
  `analyze/editor.py`, Pflicht-Überschriften werden validiert — beim Ändern
  Prompt **und** `validate_editorial_briefing` gemeinsam anpassen).

## 8. Abzuliefern

1. `config/watchlist.yaml` erweitert, jede neue Quelle mit deutschem
   Begründungs-Kommentar.
2. Neue Themenfelder als eigene Konfiguration + die dafür nötigen Code- und
   Template-Änderungen.
3. `scripts/pruefe_quellenvorschlag.py` (oder gleichwertig) plus Tests.
4. `python scripts/build_quellen_doc.py --validate` neu erzeugt.
5. `pytest -q` grün.
6. Ein echter Lauf über GitHub Actions, ausgewertet: Quellen ok/leer/fehlerhaft,
   gesammelte und neue Meldungen, Laufzeit — **vor/nach im Vergleich**.
7. `CLAUDE.md` fortgeschrieben.
8. Eine ehrliche Schlussliste: was **nicht** geklappt hat, welche Quelle
   verworfen wurde und warum, wo noch blinde Flecken sind. Lieber 40 belegte
   neue Quellen als 90 behauptete.

## 9. Ausdrücklich nicht

- Keine Keyword-Nachrichtensuche als Quelle (wurde bewusst entfernt: falsche
  Provenienz, Rauschen).
- Keine Quelle eintragen, die nicht durch den Abnahme-Check gelaufen ist.
- Keine Kappung von Meldungen einführen.
- `data/state/` und `data/reports/` nicht aus lokalen Läufen committen.
- Nicht auf `main` pushen ohne Freigabe — Entwicklung auf dem zugewiesenen Branch.
