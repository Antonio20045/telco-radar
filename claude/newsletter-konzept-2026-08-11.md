# Newsletter — Konzept, Premortem und Umsetzungsplan

> **Nachtrag vom 11.08.2026, nach der Umsetzung.** Dieses Dokument ist die
> Auftragsgrundlage; es lag der Session als Nachricht vor und wird hier
> abgelegt, damit es nicht wieder fehlt — zweimal in diesem Projekt war die
> Grundlage eines Auftrags nicht im Repo auffindbar
> (`claude/site-review-und-feature-roadmap-2026-08-08.md`,
> `claude/nachbesserung-nach-erstem-durchgang-2026-08-08.md`).
>
> **Was beim Bauen anders entschieden wurde, steht in
> `outputs/newsletter-2026-08-11.md`.** Wer dieses Konzept liest, liest es
> zusammen mit jener Schlussliste; sie nennt sechs Abweichungen und ihre
> Gründe, darunter zwei Stellen, an denen das Konzept selbst falsch lag.
> Insbesondere Abschnitt 6/N3 (Vorlagenpfade) und 6/N5 (wo die Store-Logik
> lebt) sind dort korrigiert.

Planungsdokument, Stand 11. August 2026.
Übergabefertig für Claude Code: Alle Entscheidungen sind getroffen und stehen
in Abschnitt 1. Es gibt keine offenen Fragen mehr, die den Bau blockieren.
Aufbau: Abschnitt 1 sind die Festlegungen, 2–4 die Architektur, 5 das
Premortem, 6 die Arbeitspakete N1–N9 mit wörtlichen Aufträgen, 7 optionale
Ausbaustufen für später.

---

## 1. Festlegungen

Diese acht Punkte sind entschieden. Claude Code baut danach und stellt sie
nicht in Frage.

| # | Festlegung |
|---|---|
| 1 | **Relay: Brevo Free, über die HTTP-API**, aufgerufen aus GitHub Actions. 300 Mails pro Tag, dauerhaft kostenlos, keine Kreditkarte, kein Fremdlogo in der Mail. Unabhängig von privaten Google- oder Microsoft-Konten. |
| 2 | **Absender: `Telco Radar <antonio.fotiadis.francisco@gmail.com>`**, bei Brevo als Einzelabsender verifiziert. **Eine eigene Domain ist ausgeschlossen** — die Folgen stehen unten und in Risiko a. |
| 3 | **Anmeldung: offen für alle.** Keine Domain-Allowlist aktiv. Die Prüfung wird trotzdem gebaut und steht auf leer. |
| 4 | **Signup-Dienst: Render Free**, mit Aufweck-Trick über `GET /form-token`. Kein bezahlter Plan. |
| 5 | **Abmeldung:** sichtbarer Link in jeder Mail plus `List-Unsubscribe`-Header mit der `https://`-URL. **Kein `mailto:`, kein `List-Unsubscribe-Post` nach RFC 8058.** |
| 6 | **Abo-Speicher: privates GitHub-Repo**, verschlüsselt. Adressen niemals im öffentlichen Repo. |
| 7 | **Kadenz: der bestehende Di/Fr-Lauf.** Kein eigener Zeitplan, keine Wochenzusammenfassung in v1. |
| 8 | **Sprache: nur Deutsch.** |

### Warum diese Entscheidungen so fallen

**Zum Relay (1).** Ein Relay ist unvermeidbar: GitHub-Actions-Runner können
nicht direkt an die Mailserver der Empfänger liefern, weil Port 25 ausgehend
gesperrt ist, und eine IP ohne Sendehistorie stellt bei großen Anbietern
ohnehin praktisch nichts zu. Die Frage ist also nur, welches — und die Antwort
lautet: das einzige, das dauerhaft nichts kostet, keine Kreditkarte verlangt,
kein Fremdlogo in die Mail setzt und nicht an einem privaten Postfach hängt.

Der Stand im August 2026, nachgeprüft:

| Option | Bewertung |
|---|---|
| **Brevo Free** | 300 Mails/Tag, dauerhaft kostenlos, keine Kreditkarte, kein Brevo-Branding in der Mail, HTTP-API **und** SMTP. **Gewählt.** |
| Mailjet Free | 6.000/Monat bei 200/Tag, keine Kreditkarte — aber **Mailjet-Logo in jeder Mail**. Für ein Wettbewerbsbriefing an Manager unbrauchbar. |
| Gmail / Google Workspace | Kostenlos und mit 2.000/Tag großzügiger, hängt aber an einem privaten Konto. Bei Bounce-Problemen wird dieses Konto gesperrt — dann auch die normale Post. |
| Outlook.com / Microsoft-Konto | **Fällt aus.** App-Passwörter und Basic Auth für Privatkonten sind abgeschafft; SMTP aus einem Runner ist damit nicht mehr möglich. |
| SendGrid | **Fällt aus.** Der kostenlose Plan wurde eingestellt. |
| Resend | Free-Tier existiert, für echten Versand aber mit verifizierter **Domain** — also nicht domainfrei. |
| Amazon SES | Kreditkarte und Abrechnung pro Mail. Nicht „kostenlos". |

**Der Architekturgewinn der HTTP-API.** Brevo wird per HTTPS angesprochen, nicht
per SMTP. Damit fallen drei Baustellen auf einen Schlag weg: die
Render-Free-Portsperre auf 25/465/587 ist gegenstandslos, es braucht kein
App-Passwort und keine 2FA-Abhängigkeit, und der Versandcode ist ein
`requests.post` statt SMTP-Verbindungsverwaltung. Bounces holt man sich über
die Brevo-Events-API ab, statt ein Postfach per IMAP zu durchsuchen.

**Die ehrliche Schwachstelle, und sie ist bewusst in Kauf genommen.** Ohne
eigene Domain verifiziert man bei Brevo einen **Einzelabsender**. Brevo signiert
dann mit eigenem DKIM, im `From:` steht aber eine Gmail-Adresse — das
DMARC-Alignment fehlt. Brevo warnt beim Speichern selbst, dass Adressen
kostenloser Anbieter häufiger im Spam landen, und markiert den Absender im
Dashboard mit „Freemail-Domain wird nicht empfohlen". Eine eigene Domain ist
laut Vorgabe ausgeschlossen; damit ist das der dauerhafte Zustand, nicht ein
Übergang. **Was das praktisch heißt, steht in Risiko a — bitte vor dem
Pilotbetrieb lesen.**

**Warum keine Firmenadresse als Absender (geprüft am 11. August 2026).** Die
naheliegende Idee, `@vodafone.com` als Absender zu nehmen, ist technisch
ausgeschlossen:

```
_dmarc.vodafone.com → v=DMARC1; p=reject; pct=100
_dmarc.vodafone.de  → v=DMARC1; p=quarantine; sp=quarantine; pct=100
```

`p=reject` weist den Empfänger an, jede nicht autorisierte Mail dieser Domain
zu **verwerfen** — Brevo kann für vodafone.com weder DKIM signieren noch steht
es im SPF-Eintrag. Die Mails kämen also nirgends an. Zusätzlich gehen
DMARC-Fehlerberichte an zwei Monitoring-Adressen im Eintrag; Testversuche
würden dort als Spoofing der Domain auftauchen. Dasselbe gilt für den
Anzeigenamen: kein Markenname vor einer nicht zur Marke gehörenden Adresse.

Auch die meisten Freemail-Anbieter fallen aus demselben Grund aus. Gemessen am
11. August 2026: `web.de`, `gmx.de` und `googlemail.com` stehen auf
`p=quarantine` (landet im Spam), `mailbox.org` auf `p=reject`.
**`gmail.com` steht auf `p=none`** — deshalb diese Wahl: Die Mail wird nicht
abgewiesen, sie hat nur keine Ausrichtung.

**Zur Abmeldung (5).** Die Ein-Klick-Abmeldung nach RFC 8058 ist eine
Anforderung an **Bulk-Sender ab rund 5.000 Nachrichten pro Tag** an
Gmail-Konten. Dieser Verteiler erreicht das nie — bei 300 Mails Tageslimit
kann er es gar nicht. Der `List-Unsubscribe-Post` würde außerdem maschinell vom
Mailclient mit kurzem Timeout geschickt und in den Render-Kaltstart laufen: Er
schlüge still fehl, der Nutzer hielte sich für abgemeldet, und die nächste
Ausgabe käme trotzdem. Deshalb der Verzicht. Bleibt der sichtbare Link plus
`List-Unsubscribe` mit der `https://`-URL. Eine `mailto:`-Variante gibt es
nicht, weil es in dieser Architektur kein Postfach gibt, das sie auswerten
könnte.

**Zum Anzeigenamen (2).** Der Absender heißt im Klartext `Telco Radar` und
**nicht** `Vodafone` oder `Vodafone Insights`. Ein Markenname als Anzeigename
vor einer nicht zur Marke gehörenden Adresse ist genau das Muster, auf das
Konzern-Gateways als Display-Name-Spoofing anschlagen — und markenrechtlich
gilt dasselbe wie bei der Domain.

---

## 2. Was der Newsletter ist — und was nicht

Der Newsletter ist **kein vierter Anwendungsfall** neben Marktrecherche und
Promo Übersicht. Er ist ein **Ausspielkanal** für das, was die Pipeline ohnehin
erzeugt. Das ist die wichtigste Abgrenzung des Papiers, weil sie den teuersten
Fehler verhindert: einen zweiten redaktionellen Apparat zu bauen, der eigene
Texte schreibt und dann zwangsläufig irgendwann etwas anderes sagt als die
Website.

Drei Regeln, in der Umsetzung nicht verhandelbar:

- **Keine neuen Inhalte.** Die Mail enthält ausschließlich Textbausteine, die
  im Bericht schon stehen. Was in der Mail steht, steht wortgleich auf der
  Seite.
- **Kein Modellaufruf pro Empfänger.** Sonst kostet ein Verteiler mit 200
  Personen 200 Editor-Läufe, dauert länger als der Radar-Lauf selbst und
  erzeugt 200 leicht verschiedene Wahrheiten. Die Mail ist eine Auswahl- und
  Formatierungsaufgabe, keine Analyseaufgabe.
- **Die Mail ist ein Anreißer, nicht der Bericht.** Ziel jeder Ausgabe ist der
  Klick auf die Seite. Drei bis acht Einträge mit je zwei bis drei Sätzen und
  Direktlink, nicht der komplette Wochenbericht als HTML-Mail.

---

## 3. Architektur

### 3.1 Die Grundidee

Die statische Seite kann keine Formulare annehmen, und der Render-Free-Tier
kann keine Mail verschicken. Das sind die beiden Randbedingungen, aus denen
sich alles Weitere ergibt:

| Eigenschaft (Render Free) | Folge |
|---|---|
| SMTP-Ports 25/465/587 ausgehend gesperrt | Der Dienst kann keine Mail senden |
| Spin-down nach 15 Min, ~1 Min Aufwachzeit | Der erste Aufruf nach einer Pause hängt |
| Ephemeres Dateisystem, keine Persistent Disks | Keine Daten auf der Platte des Dienstes |
| Free Postgres: 1 GB, **verfällt nach 30 Tagen** | Kein Abo-Register in der Gratis-Datenbank |
| 750 Instanzstunden pro Monat | Ein Keep-alive-Ping würde das Kontingent allein aufbrauchen (ein Monat hat ~730 Std.) |

Daraus die tragende Konstruktionsidee: **Der Web-Dienst verschickt nie selbst
Mail und speichert nie selbst Daten. Er nimmt entgegen, prüft Signaturen und
reicht weiter. Versand und Speicherung passieren in GitHub Actions.**

Die Portsperre ist durch die Wahl der Brevo-HTTP-API zwar entschärft — HTTPS
ist nicht gesperrt, der Dienst *könnte* technisch senden. Er tut es trotzdem
nicht, aus zwei Gründen, die unabhängig von der Portfrage gelten: Der API-Key
soll nicht auf einer öffentlich erreichbaren Instanz liegen, und die
24-Stunden-Sperre pro Adresse braucht ohnehin den Store, den nur Actions
sehen.

### 3.2 Der Weg einer Anmeldung

```
Browser                Signup-Dienst              Privates Repo (Actions)
(Static Site)          (Render Free)              telco-radar-mail
   |                        |                           |
   |-- GET /form-token ---->| signierte Nonce           |
   |   (beim Seitenaufbau)  | (weckt nebenbei die       |
   |<-----------------------|  Instanz auf)             |
   |                        |                           |
   |-- POST /subscribe ---->|                           |
   |   E-Mail + Themen      | Honeypot, Nonce prüfen,   |
   |   + Nonce              | IP-Bremse, Adresssyntax   |
   |                        | HMAC-Token bilden         |
   |                        | (E-Mail + Themen + Zeit   |
   |                        |  + IP-/UA-Hash signiert,  |
   |                        |  NICHTS gespeichert)      |
   |                        |-- repository_dispatch --->|
   |                        |   type: send_doi          | 24-h-Sperre prüfen
   |<-- 202 "Mail kommt" ---|                           | DOI-Mail via Brevo-API
   |                                                    |
   |<========== Bestätigungsmail an den Nutzer =========|
   |                                                    |
   |-- GET /confirm/<token> |                           |
   |                        | HMAC + TTL (72 h) prüfen  |
   |                        |-- repository_dispatch --->| Abo in
   |                        |   type: confirm           | subscribers.jsonl
   |<-- Bestätigungsseite --|                           | + Einwilligungs-
   |                                                    |   protokoll
```

Der entscheidende Kniff steht in der Mitte: **Zwischen Anmeldung und
Bestätigung wird im Signup-Dienst nichts gespeichert.** Alle Angaben stecken
signiert im Token im Bestätigungslink — Adresse, Filter, Einwilligungs-
Textversion, Zeitstempel und die gepfefferten Hashes von IP und User-Agent.
Letztere müssen mitreisen, weil zum Zeitpunkt der Bestätigung die
Anmeldeanfrage nicht mehr existiert; ohne sie bliebe das Einwilligungsprotokoll
leer. Wer nie bestätigt, hinterlässt im Dienst keine Daten — die Frage nach der
Löschfrist für unbestätigte Anmeldungen erledigt sich damit.

Zwei Einschränkungen, damit die Aussage nicht mehr verspricht als sie hält:

- **Der Dienst bleibt ein Angriffsziel.** Er hält den HMAC-Schlüssel und ein
  GitHub-Token. Wer ihn übernimmt, kann keine bestehende Liste auslesen, aber
  gültige Bestätigungstoken fälschen. Daher die Rechteeinschränkung in 3.4.
- **Adressen laufen durch HTTP-Logs.** Ein Token in der Query-Zeichenkette
  landet in Render-Zugriffslogs, Browser-Historie und potenziell im `Referer`.
  Deshalb Token als **Pfadsegment** (`/confirm/<token>`),
  `Referrer-Policy: no-referrer`, und die Datenschutzerklärung nennt
  Render-Serverlogs als Verarbeitung.

**Das 24-Stunden-Limit pro Adresse liegt nicht im Signup-Dienst.** Ein
In-Memory-Zähler ist nach jedem Spin-down und jedem Deploy leer — der Schutz
gegen Mailbomben-Missbrauch wäre umgehbar, indem man 16 Minuten wartet. Die
Sperre gehört dorthin, wo Zustand existiert: Der `send_doi`-Workflow prüft
einen gepfefferten Adress-Hash gegen `store/doi_log.jsonl` und verwirft
stillschweigend, wenn dieselbe Adresse in 24 Stunden schon eine
Bestätigungsmail bekommen hat. Der IP-Zähler im Dienst bleibt als billige
erste Bremse, gilt aber nicht als Schutzmaßnahme.

Ebenso die Mindestzeit zwischen Formularaufbau und Absenden: Ein Zeitstempel
aus einer statischen Seite ist unsigniert und frei fälschbar. Stattdessen
liefert `GET /form-token` beim Seitenaufbau eine HMAC-signierte Nonce mit
Ausstellungszeit; `/subscribe` akzeptiert nur signierte Nonces. Nebeneffekt:
Dieser Aufruf weckt die Render-Instanz, während der Nutzer noch ausfüllt — der
Kaltstart fällt in der Praxis kaum auf.

### 3.3 Der Weg einer Ausgabe

```
radar.yml (öffentliches Repo)
   Pipeline -> Bericht + JSON -> Commit -> Render-Deploy
        |
        '-- repository_dispatch: report_ready (nur Datum + Commit-SHA)
                 |
                 v
        newsletter.yml (privates Repo)
                 |
        1. Bericht-JSON aus dem öffentlichen Repo laden (Datum + SHA)
        2. subscribers.jsonl entschlüsseln
        3. Segmente bilden (gleiche Filter = ein Rendering)
        4. Pro Segment HTML + Text rendern
        5. Sendeplan pushen, dann versenden mit Idempotenzprüfung
        6. Statuszeile ins öffentliche Protokoll zurückschreiben

        täglich, unabhängig davon:
        bounce_sync.yml -> Brevo-Events-API: Bounces und Beschwerden abholen
```

Der Versand läuft **als eigener Job in einem eigenen Repo**, nicht im
Pipeline-Job. Zwei Gründe: Der Radar-Lauf lag am 6. August bei 27,4 Minuten
gegen 35 Minuten Job-Timeout — dort gehört nichts mehr hinein. Und Abonnenten
gehören nicht in ein öffentliches Repository.

### 3.4 Warum ein zweites, privates Repository

Adressen von Abonnenten sind personenbezogene Daten. Im öffentlichen Repo
`Antonio20045/telco-radar` haben sie in keiner Form etwas zu suchen — auch
nicht verschlüsselt, auch nicht kurz, auch nicht im Payload eines
`repository_dispatch`. Ein Commit mit einer Adressliste ist über Git-Historie
und Forks dauerhaft öffentlich, und das ist ein meldepflichtiger Vorfall nach
Art. 33 DSGVO mit 72-Stunden-Frist, kein Bug, den man wegrebased.

Deshalb ein privates Repo `telco-radar-mail` mit Workflows, Templates,
Abo-Store und Sendeprotokoll. `subscribers.jsonl` liegt dort zusätzlich mit
`age`/SOPS verschlüsselt, der Schlüssel als Actions-Secret.

Für die Verbindung reicht es **nicht**, dem Signup-Dienst ein PAT mit
`contents: write` auf `telco-radar-mail` zu geben: Damit ließe sich
`scripts/send_digest.py` überschreiben — genau die Datei, die der Workflow
danach mit dem Entschlüsselungsschlüssel ausführt. Wer den Render-Dienst
übernimmt, hätte Codeausführung im Runner und den entschlüsselten Verteiler.

Zwei Absicherungen, die zweite ist die sauberere:

- **Branch-Protection** auf `main` von `telco-radar-mail`, sodass das PAT nicht
  pushen kann. `repository_dispatch` funktioniert weiter, weil es keine
  Dateioperation ist.
- **Ein drittes, leeres Repo `telco-radar-inbox`** als alleiniges
  Dispatch-Ziel. Das PAT gilt nur dort; ein Workflow reicht das Ereignis an
  `telco-radar-mail` weiter, mit einem Token, das nur in Actions liegt. Das
  Store-Repo ist von außen dann gar nicht erreichbar.

In keinem Workflow-Log darf je eine Adresse erscheinen — jede wird vor
Verwendung mit `::add-mask::` maskiert, Log-Ausgaben zählen Empfänger, statt
sie zu nennen.

### 3.5 Was das kostet

**Alles an v1 kostet null Euro.** Kein Posten hat einen Preis, keiner verlangt
eine Kreditkarte.

| Baustein | Kosten | Deckel |
|---|---|---|
| Domain | 0 € | keine nötig (Festlegung 2) |
| Relay (Brevo Free) | 0 € | **300 Mails pro Tag** |
| Signup-Dienst (Render Free) | 0 € | Spin-down nach 15 Min, 750 Instanzstd./Monat |
| Privates GitHub-Repo | 0 € | — |
| Actions-Minuten | 0 € | 2.000 Min./Monat für private Repos |

Zwei Deckel sind es wert, im Blick behalten zu werden. **Brevos 300 pro Tag**
ist die harte Grenze für die Verteilergröße: 300 Empfänger je Ausgabe, bei zwei
Ausgaben pro Woche an verschiedenen Tagen also 300 Abonnenten insgesamt. Wer
darüber hinauswill, zahlt entweder bei Brevo oder verteilt den Versand über
zwei Tage — beides steht in Abschnitt 7.

Die **Actions-Minuten** sind unkritisch, aber nicht null: Bei 200 Empfängern
und 30 Mails pro Minute dauert ein Versandlauf gut sieben Minuten, bei zwei
Läufen pro Woche rund 60 Minuten im Monat von 2.000. Über die HTTP-API sind
die Aufrufe zudem billiger als SMTP-Verbindungen.

**Zum Datenschutz:** GitHub (Microsoft, USA) speichert die Abonnentenliste,
Render (USA) verarbeitet Adresse und IP bei der Anmeldung, Brevo (Frankreich,
mit Infrastruktur in der EU) verarbeitet den Versand. Alle drei sind
Auftragsverarbeiter und brauchen AV-Vertrag, Nennung in der
Datenschutzerklärung und einen Eintrag im Verarbeitungsverzeichnis. Bei GitHub
und Render kommt ein Drittlandtransfer dazu; Brevo ist der einzige
EU-Verarbeiter in der Kette und insofern der unproblematischste — ein weiteres
Argument gegen ein US-Freemail-Konto als Relay.

---

## 4. Datenmodell und Filterlogik

### 4.1 Ein Abonnement

```json
{
  "id": "sub_01J9F...",
  "email": "vorname.nachname@example.com",
  "created_at": "2026-08-11T09:14:22Z",
  "confirmed_at": "2026-08-11T09:16:03Z",
  "consent": {
    "text_version": "2026-08-11",
    "text_hash": "sha256:...",
    "ip_hmac": "...",
    "user_agent_hmac": "...",
    "confirm_token_id": "..."
  },
  "filters": {
    "branches": ["marktrecherche", "promo"],
    "regions": ["europa", "nordamerika"],
    "competitors": ["telekom", "o2"],
    "categories": ["bundling", "b2b"],
    "keywords": [
      {"term": "Netzausbau", "mode": "word"},
      {"term": "Fixed Wireless Access", "mode": "phrase"}
    ]
  },
  "cadence": "jeder_lauf",
  "format": "kurz",
  "state": "active",
  "bounce": {"hard": 0, "soft": 0, "last": null}
}
```

Zwei Details, die leicht falsch gebaut werden:

- **Alle Hashes sind HMAC-SHA256 mit geheimem Pepper**, nicht blankes SHA-256.
  Ein SHA-256 über eine E-Mail-Adresse oder eine IPv4 ist per Brute Force in
  Minuten umkehrbar — das wäre keine Pseudonymisierung, sondern eine
  Formalität. Der Pepper liegt als Secret, nicht neben den Daten. Gilt auch für
  den Adress-Hash, der nach einer Abmeldung erhalten bleibt.
- **Die Anmeldewerte reisen im signierten Token mit** (siehe 3.2), sonst ist
  das Protokoll leer.

Der Wortlaut der Einwilligung wird über `text_version` + `text_hash` an eine
versionierte Datei `content/consent_texts/2026-08-11.md` gebunden — die
Aufsichtsbehörden verlangen den damaligen Wortlaut, nicht den heutigen.

### 4.2 Wie die vier Dimensionen zusammenwirken

Die Verknüpfungsregel ist der Punkt, an dem solche Filter üblicherweise
scheitern. Festlegung:

- **Zwischen** den Dimensionen gilt UND: Wer Europa und Bundling wählt, bekommt
  europäische Bundling-Meldungen — nicht alles aus Europa plus alles zu
  Bundling.
- **Innerhalb** einer Dimension gilt ODER: Europa oder Nordamerika.
- **Leer heißt „alles"**, nicht „nichts". Wer keine Region wählt, schließt
  Regionen nicht aus. Das ist die Erwartung fast aller Nutzer und muss im
  Formular trotzdem danebenstehen.
- **Stichwörter sind additiv, nicht einschränkend.** Ein Treffer auf ein
  eigenes Stichwort kommt in die Ausgabe, auch wenn er durch die anderen Filter
  gefallen wäre — und wird als solcher markiert („Ihr Stichwort:
  Netzausbau"). Sonst versteht niemand, warum ein Eintrag in der Mail steht.
  Diese eine Regel entscheidet, ob Stichwort-Abos als nützlich oder als kaputt
  empfunden werden.

### 4.3 Stichwörter, der gefährlichste Teil

Das Projekt kennt das Problem aus dem Fachpresse-Tagging: Kurze, mehrdeutige
Begriffe wie `spark`, `tim`, `globe` oder `orange` erzeugen ohne Wortgrenzen
und Blockliste massenhaft Falschtreffer. Bei nutzergepflegten Stichwörtern ist
die Lage schlechter, weil niemand die Liste kuratiert.

- Mindestens vier Zeichen. Keine Teilwort-Treffer. Wortgrenzen wie im
  bestehenden Alias-Matching, inklusive deutscher Komposita-Behandlung
  (`Netzausbau` soll in `Glasfaser-Netzausbau` treffen, `Netz` aber nicht in
  `Netzwerkkarte` untergehen).
- Maximal zehn Stichwörter pro Abo.
- Treffer nur in Titel und Zusammenfassung, nicht im Volltext.
  Volltext-Treffer sind fast immer Rauschen.
- **Vorschau vor dem Absenden:** „Ihr Stichwort hätte in den letzten 30 Tagen
  47 Meldungen getroffen", mit Warnung ab einem Schwellwert. Das ist die
  wirksamste Einzelmaßnahme gegen Abo-Müdigkeit, weil sie das Problem löst,
  bevor es Mails erzeugt.

Umsetzungshinweis, der sonst zu spät auffällt: Die Anmeldeseite ist statisch
und kann keinen Python-Code aufrufen, und der Signup-Dienst hat die
Berichtsarchive nicht. Die Zählung läuft **clientseitig gegen eine
Indexdatei**, die die Pipeline bei jedem Lauf mitschreibt:
`site/data/keyword-index.json` mit den normalisierten Tokens aus Titeln und
Zusammenfassungen der letzten 30 Tage samt Häufigkeiten. `preview_keyword` aus
N2 ist der Erzeuger dieses Index und die Testgrundlage — keine zur Laufzeit
aufgerufene Schnittstelle.

### 4.4 Segmente statt Empfänger

Zwei Personen mit identischen Filtern bekommen dieselbe Mail. Der Renderer
bildet einen `segment_hash` über den normalisierten Filtersatz (sortiert,
kleingeschrieben) und rendert **einmal pro Segment**. Aus 200 Abonnenten mit 12
Filterkombinationen werden 12 Renderings und 200 Zustellungen. Personalisiert
bleiben nur Kopfzeile und Abmelde-URL.

---

## 5. Premortem: August 2027, die Funktion existiert — und richtet Schaden an

Als Ursachenkette, jeweils mit der Anforderung, die das verhindert.

**a) Die Mails landen im Spam, und niemand merkt es.** Der Versand meldet
Erfolg, die Zustellung scheitert am Empfänger-Gateway. Der Fehler ist tückisch,
weil er sich wie Erfolg anfühlt — und er ist bei diesem Aufbau **das
wahrscheinlichste Problem überhaupt**: Brevo signiert mit eigenem DKIM, im
`From:` steht eine Gmail-Adresse, das DMARC-Alignment fehlt (siehe 1). Weil
eine eigene Domain ausgeschlossen ist, lässt sich das nicht reparieren,
sondern nur messen und einkalkulieren.

Die Zielgruppe sitzt hinter einem Konzern-Gateway, und Konzern-Gateways
behandeln nicht ausgerichtete Freemail-Absender mit Massenversandmuster
strenger als Gmail. Es ist gut möglich, dass ein relevanter Teil der Ausgaben
dort im Spam landet.

→ *Anforderung:* Anzeigename `Telco Radar`, kein Markenname. Vor dem ersten
echten Versand ein Testlauf an ein Freemail- **und** ein Unternehmenspostfach
mit Prüfung der Authentifizierungs-Header und der tatsächlichen Landung. Das
Ergebnis wird in `docs/mail-setup.md` festgehalten, **auch wenn es schlecht
ausfällt**. Landet die Mail im Firmenpostfach im Spam, ist das kein Bug,
sondern die dokumentierte Konsequenz der Absenderentscheidung — dann muss
entschieden werden, ob der Newsletter so überhaupt Sinn ergibt oder ob die
Empfänger einmalig gebeten werden, den Absender als vertrauenswürdig zu
markieren. Ab dem ersten Lauf Zustell-, Bounce- und Beschwerdequote im
Protokoll ausweisen; eine steigende Spam-Beschwerdequote deaktiviert das
Brevo-Free-Konto.

**b) Dieselbe Ausgabe geht zweimal raus.** Ein Actions-Re-Run, ein doppeltes
`repository_dispatch`, ein Retry nach Timeout — und 200 Manager bekommen den
Wochenbericht zum zweiten Mal. Der teuerste denkbare Fehler: nicht rückgängig
zu machen, kostet sofort Vertrauen.

→ *Anforderung:* Idempotenzschlüssel aus `report_date` + `segment_hash` +
`subscriber_id` in `send_log.jsonl`. Die naive Formulierung „nach jeder
Zustellung sofort schreiben" ist in einem Git-Store nicht umsetzbar: Ein Commit
plus Push je Empfänger wären 200 Pushes pro Lauf, ein rein lokaler
Schreibvorgang ist bei einem Runner-Absturz komplett verloren — und der
Wiederanlauf begeht genau den Fehler, den das Log verhindern soll. Deshalb
dreistufig:

1. **Vor dem Versand** wird ein deterministischer Sendeplan (alle
   Idempotenzschlüssel des Laufs, Status `geplant`) geschrieben und gepusht.
2. **Während des Versands** wird jede Zustellung einzeln per Contents-API mit
   `sha`-Vorbedingung ans Log angehängt — ein HTTP-Aufruf, kein Git-Push, und
   bei paralleler Änderung schlägt er fehl statt zu überschreiben.
3. **Bei Wiederanlauf** gilt: `geplant` ohne Zustellbestätigung wird erneut
   versucht, alles mit Bestätigung übersprungen. Der Zustand „gesendet,
   Log-Schreiben fehlgeschlagen" gilt als gesendet — im Zweifel lieber eine
   Mail zu wenig als eine zu viel.

Dazu zwei Punkte, die sonst still danebengehen: Alle Workflows, die den Store
anfassen (`doi`, `confirm`, `bounce_sync`, `newsletter`), brauchen dieselbe
`concurrency`-Gruppe mit `cancel-in-progress: false`. Und `git pull --rebase`
kann eine `age`-verschlüsselte Datei **nicht** zusammenführen — jeder
Ciphertext unterscheidet sich bei jedem Schreibvorgang vollständig, jeder
Konflikt ist ein Binärkonflikt. Konfliktbehandlung deshalb als Entschlüsseln →
auf JSONL-Zeilenebene zusammenführen → neu verschlüsseln.

**c) Adressen landen im öffentlichen Repo oder im Actions-Log.** Ein Commit,
ein `echo`, ein Debug-Ausdruck — und die Verteilerliste ist öffentlich und über
die Git-Historie dauerhaft nachvollziehbar.

→ *Anforderung:* Getrenntes privates Repo, verschlüsselter Store,
`::add-mask::` für jede Adresse, Log-Ausgaben zählen statt zu nennen. Ein
CI-Test prüft, dass keine Datei im öffentlichen Repo ein `@`-Adressmuster in
einer JSONL enthält.

**d) Das Anmeldeformular wird als Mailbombe missbraucht.** Ein offenes
Formular, das eine Mail an eine beliebige eingegebene Adresse auslöst, ist ein
Versandwerkzeug für Dritte — und das schlägt direkt auf die Absenderreputation
bei Brevo durch. Free-Konten werden bei auffälligem Sendeverhalten schnell und
ohne Vorwarnung deaktiviert; dazu frisst jede missbräuchliche
Bestätigungsmail vom 300er-Tageskontingent.

→ *Anforderung:* Honeypot-Feld, signierte Nonce statt Client-Zeitstempel,
IP-Bremse im Dienst und die harte 24-Stunden-Sperre pro Adresse im
`send_doi`-Workflow (siehe 3.2). Keinerlei Freitext des Absenders in der Mail.
Die Bestätigungsmail nennt die Herkunft der Anmeldung und den Satz „Wenn Sie
das nicht waren, ignorieren Sie diese Mail — es passiert dann nichts."

**e) Der Wettbewerb liest mit.** Bei offener Anmeldung (Festlegung 3) können
sich Telekom, O2 und 1&1 für das Briefing eintragen. Das ist keine Panne,
sondern die bewusst gewählte Funktion — die Seite ist ohnehin öffentlich und
die Mail nur Anreißer plus Link.

→ *Anforderung:* Die Domain-Allowlist wird trotzdem gebaut und steht auf leer.
Umschalten muss später eine Konfigurationszeile sein, kein Umbau. Und: In der
Mail steht nie mehr als auf der öffentlichen Seite.

**f) Die Einwilligungskette hält keiner Prüfung stand.** Double-Opt-in ist
gebaut, aber der Wortlaut der damaligen Einwilligung ist nicht rekonstruierbar,
die Zeitpunkte fehlen, oder unbestätigte Anmeldungen liegen unbegrenzt herum.
Verlangt wird eine freiwillig, informiert, bestimmt, unmissverständlich und
nachweisbar erteilte Einwilligung, eine neutrale Bestätigungsmail ohne Werbung
und ein Nachweis, der über eine bloße IP-Adresse hinausgeht.

→ *Anforderung:* Versionierte Einwilligungstexte mit Hash im Abo-Datensatz,
Zeitstempel für Anmeldung und Bestätigung, und der architektonische Trick aus
3.2: Unbestätigte Anmeldungen werden gar nicht erst gespeichert.

**g) Abmeldung funktioniert nicht oder zu langsam.** Nach Festlegung 5 gibt es
genau einen Weg: den sichtbaren Link, der auch im `List-Unsubscribe`-Header
steht. Sein Fallstrick ist der Render-Kaltstart — wer klickt, während der
Dienst schläft, wartet eine Minute oder sieht einen Fehler und hält sich
trotzdem für abgemeldet.

→ *Anforderung:* Der Link führt auf eine **statische** Seite, die sofort
bestätigt; die Verarbeitung läuft asynchron nach und ist gegen einen
schlafenden Dienst robust (Wiederholung im Hintergrund, klare Fehlermeldung
statt ewigem Spinner). Die Abmeldung setzt `state: unsubscribed` und löscht die
Adresse. Weil es nur diesen einen Weg gibt, muss er belastbar sein — er wird in
N9 ausdrücklich im kalten Zustand getestet.

**h) Der Newsletter erzieht zum Ignorieren.** Zweimal pro Woche eine Mail, in
der nichts steht, oder eine Stichwortmail mit 40 Treffern.

→ *Anforderung:* Leere Ausgaben werden **nicht** verschickt. Wer vier Wochen in
Folge nichts bekommen hätte, erhält einmal monatlich eine Zeile „In Ihren
Themen gab es seit dem … nichts Neues" mit Link zur Filteranpassung. Nach oben
gedeckelt auf acht Einträge je Ausgabe, sortiert nach dem vorhandenen
Wichtigkeits-Score. Dazu die Trefferzahl-Vorschau aus 4.3.

**i) Die Mail sieht in Outlook kaputt aus.** Im Browser-Preview perfekt, im
Firmen-Outlook zerlegt.

→ *Anforderung:* Tabellenlayout, Inline-CSS, keine Flexbox, kein Grid, keine
Web Fonts, keine Hintergrundbilder, maximal 600 Pixel Breite, jedes Bild mit
Alt-Text, Dark-Mode-tauglich, und eine vollwertige Text-Alternative — nicht ein
aus dem HTML gestripptes Fragment. Abnahme in Outlook, Gmail-Web und einem
Mobilclient, nicht im Browser.

**j) Bounces zerstören die Reputation — und Brevo sperrt das Konto.**
Ausgeschiedene Kollegen, Tippfehler, volle Postfächer. Transaktionsanbieter
reagieren auf schlechte Bounce- und Beschwerdequoten empfindlich und
deaktivieren Free-Konten schnell und ohne Vorwarnung. Der Vorteil gegenüber
einem privaten Postfach: Es trifft nur den Newsletter, nicht die eigene Post.

→ *Anforderung:* `bounce_sync.yml` fragt **täglich** die Brevo-Events-API ab
(Hard Bounce, Soft Bounce, Beschwerde/Spam-Markierung). Ein Hard Bounce oder
eine Beschwerde setzt sofort `state: bounced`, fünf Soft Bounces in Folge
ebenso. Die Zahlen gehören ins Protokoll, damit schleichender Verfall sichtbar
wird. Kein IMAP, kein Postfach — die API ist die Quelle.

**k) Die Mail widerspricht der Website.** Sobald jemand den Editor für die Mail
„etwas anders" formulieren lässt, gibt es zwei Wahrheiten.

→ *Anforderung:* Kein Modellaufruf im Versandpfad. Der Renderer liest und kürzt
ausschließlich Felder aus dem Bericht-JSON. Die Prüfung unterscheidet zwei
Textarten, sonst ist sie nicht erfüllbar: **Inhaltstragende Blöcke** (alles aus
`items[]` — Titel, Zusammenfassung, Quelle) müssen als Teilstring im
Bericht-JSON vorkommen. **Rahmentexte** (Anrede, Kopfzeile, Abmeldehinweis,
Impressumszeile, Stichwort-Markierung, Leermeldung) stehen naturgemäß nirgends
im Bericht und kommen aus einer versionierten `templates/mail/chrome.yaml`, die
der Test als Allowlist kennt.

**l) Der Versand hängt sich an den Radar-Lauf und bringt ihn um.** Der
Pipeline-Job lag am 6. August bei 27,4 von 35 Minuten. Ein gedrosselter Versand
an 200 Empfänger dauert allein rund sieben Minuten — im selben Job kippt das
den Lauf ins Timeout, und dann fällt nicht nur der Newsletter aus, sondern der
Bericht.

→ *Anforderung:* Getrennter Workflow, getrenntes Repo, ausgelöst per
`repository_dispatch` **nach** erfolgreichem Deploy. Ein fehlgeschlagener
Versand darf den Radar nie rot färben.

**m) Das 300er-Tageslimit wird still gerissen.** Das ist bei diesem Aufbau das
Limit, das als Erstes greift — nicht in ferner Zukunft, sondern beim 301.
Abonnenten. Ein Wiederanlauf, ein zweiter Lauf am selben Tag oder eine
Testausgabe zählen mit. Was dann passiert, ist der schlimmste Fall: Ein Teil
der Empfänger bekommt die Ausgabe, der Rest nicht — und zwar stumm.

→ *Anforderung:* Der Versand-Workflow zählt die geplanten Zustellungen **vor**
dem Start, addiert die bereits am selben Tag versendeten aus `send_log.jsonl`
und bricht mit klarer Meldung ab, wenn die Summe den konfigurierten Schwellwert
(Standard 280, mit Reserve unter den 300) überschreiten würde. Kein
Teilversand ohne Protokolleintrag. Der Abstand zum Limit steht in jeder
Statuszeile, damit sichtbar wird, wann der Verteiler an die Grenze wächst.

**n) Niemand pflegt es.** Nach acht Wochen prüft niemand mehr Zustellquote,
Bounces und Abmeldungen.

→ *Anforderung:* Der Versand schreibt eine Statuszeile ins bestehende
`protokoll.html` — Ausgabedatum, Segmente, Zustellungen, Fehler, Bounces,
Abmeldungen. Damit ist der Zustand dort sichtbar, wo ohnehin hingesehen wird,
und braucht kein eigenes Dashboard.

**o) Die Seite hat kein Impressum und keine Datenschutzerklärung.** Im
ausgelieferten HTML von `telco-radar.onrender.com` (geprüft am 11. August 2026)
gibt es zwar einen `<footer class="foot">`, aber darin kommt weder „Impressum"
noch „Datenschutz" vor. Sobald Adressen erhoben werden, sind die
Informationspflichten nach Art. 13 DSGVO fällig — Verantwortlicher, Zweck,
Rechtsgrundlage, Empfänger und Dienstleister, Speicherdauer, Betroffenenrechte,
Widerruf und Beschwerderecht — und der Newsletter selbst braucht
Absenderangaben.

→ *Anforderung:* Beides ist Teil des ersten Arbeitspakets und nicht optional.
Ohne diese Seiten geht kein Formular online.

---

## 6. Umsetzungsplan für Claude Code

Neun Arbeitspakete. N1 bis N3 sind ohne Netz und ohne Anmeldung testbar und
kommen zuerst; N4 bis N6 bauen die Infrastruktur; N7 bis N9 schalten frei.
Reihenfolge einhalten — insbesondere darf N7 (das öffentliche Formular) erst
live gehen, wenn N1 vollständig ist.

Jedes Paket ist einzeln testbar, mergebar und rücknehmbar. Vor jedem Paket
gilt die bestehende Hausregel: `pwd`, `git status`, `git remote -v` prüfen,
`git pull --rebase origin main`, und `PYTHONPATH=src pytest -q` muss vorher und
nachher grün sein.

---

### N1 — Vorbedingungen: Brevo-Konto und Rechtstexte

Wenig Python-Code, aber ohne dieses Paket ist alles Folgende wertlos.

**Neu:** `site/impressum.html` und `site/datenschutz.html` über die bestehende
Template-Schicht (nicht per Hand ins generierte `site/` schreiben),
`content/legal/`, `content/consent_texts/2026-08-11.md`, Fußbereich mit beiden
Links auf allen Seiten, `docs/mail-setup.md`.

**Bereits erledigt am 11. August 2026** — Claude Code muss das nicht wiederholen:

- Brevo-Konto im Free-Plan angelegt, Organisation `insights`, keine Kreditkarte.
  Kontingent bestätigt: **300 von 300 E-Mails**, Zähler setzt täglich zurück.
- Absender `Telco Radar <antonio.fotiadis.francisco@gmail.com>` angelegt und
  **verifiziert**. Anzeigename bewusst neutral, kein Markenname.
- API-Key `telco-radar-newsletter` erzeugt, gültig bis 11. August 2027, als
  GitHub-Secret `BREVO_API_KEY` hinterlegt.
- SMTP ist im Konto freigeschaltet (Server, Port, Login sichtbar); die
  Freischaltungshürde für Transaktionsversand besteht also nicht.

**Wichtig für den Betrieb:** Brevo-API-Keys verfallen **nach 90 Tagen ohne
Nutzung**, unabhängig vom Ablaufdatum. Bei zwei Läufen pro Woche unkritisch —
aber nach einer längeren Projektpause ist ein toter Key die erste Ursache, die
zu prüfen ist, bevor im Code gesucht wird. Gehört so in `docs/mail-setup.md`.

**Akzeptanzkriterien:**

- Der API-Key steht nirgends im Code, in keinem Log und in keiner Datei —
  ausschließlich als GitHub-Secret.
- Ein Testversand aus einem Wegwerf-Workflow über die Brevo-HTTP-API an ein
  Freemail- **und** ein Unternehmenspostfach ist dokumentiert: Wo ist die Mail
  gelandet, was steht in den Authentifizierungs-Headern. Landet sie beim
  Unternehmenspostfach im Spam, ist das in `docs/mail-setup.md` als bekannter
  Zustand festzuhalten, zusammen mit dem Hinweis auf Ausbaustufe A.
- Die Events-API ist erreichbar und liefert für den Testversand Ereignisse
  zurück (Grundlage für `bounce_sync.yml` in N6).
- Der Anzeigename ist `Telco Radar`. Kein Markenname im Anzeigenamen.
- Impressum und Datenschutzerklärung sind über den Fußbereich jeder Seite
  erreichbar und nennen Verantwortlichen, Zweck, Rechtsgrundlage
  (Einwilligung), Empfänger, Speicherdauer, Betroffenenrechte, Widerruf und
  Beschwerderecht.
- Als Empfänger sind **GitHub (Microsoft, USA)**, **Render (USA)** und
  **Brevo (Frankreich)** benannt; AV-Verträge und
  Verarbeitungsverzeichnis-Einträge sind eingeplant.
- Der Einwilligungstext liegt versioniert vor; sein SHA-256 ist reproduzierbar
  berechenbar.

---

### N2 — Abo-Datenmodell, Filter-Engine, Segmente

Reine Logik, kein Netz, kein Mailversand. Das Paket, das am gründlichsten
getestet werden muss, weil hier alle späteren Fehlermeldungen herkommen.

**Neu:** `src/telco_radar/newsletter/__init__.py`, `subscription.py`,
`filters.py`, `segments.py`, `config/newsletter.yaml`,
`tests/test_newsletter_filters.py`, `tests/test_newsletter_segments.py`,
`tests/fixtures/newsletter/`.

**Akzeptanzkriterien:**

- Die Verknüpfungsregeln aus 4.2 sind implementiert und je einzeln getestet:
  UND zwischen Dimensionen, ODER innerhalb, leer bedeutet „alles", Stichwörter
  additiv und im Ergebnis markiert.
- Stichwort-Matching mit Wortgrenzen, mindestens vier Zeichen, keine
  Teilwort-Treffer, deutsche Komposita berücksichtigt. Wiederverwendung der
  vorhandenen Alias-/Blocklisten-Logik statt einer zweiten Implementierung.
- Ein Test mit `spark`, `tim`, `globe`, `orange` belegt, dass keine
  Falschtreffer entstehen.
- `segment_hash` ist stabil gegenüber Reihenfolge und Groß-/Kleinschreibung.
- `preview_keyword(term, days)` liefert die Trefferzahl der letzten N Tage aus
  den archivierten Berichten und erzeugt `site/data/keyword-index.json` für die
  clientseitige Vorschau in N7.
- Deckelung auf acht Einträge je Ausgabe, sortiert nach dem vorhandenen
  Wichtigkeits-Score.
- Alle Tests laufen offline gegen Fixtures.

---

### N3 — Mail-Renderer

**Neu:** `src/telco_radar/newsletter/render.py`,
`templates/mail/digest.html.j2`, `templates/mail/digest.txt.j2`,
`templates/mail/chrome.yaml`, `src/telco_radar/newsletter/transport.py`,
`tests/test_newsletter_render.py`, `scripts/preview_newsletter.py`.

**Akzeptanzkriterien:**

- Aus Bericht-JSON und Filterergebnis entstehen HTML und Text.
- HTML: Tabellenlayout, Inline-CSS, kein Flexbox/Grid, keine Web Fonts, keine
  Hintergrundbilder, maximal 600 Pixel, Alt-Texte, Dark-Mode-tauglich.
- Die Textfassung ist eigenständig lesbar, kein gestripptes HTML.
- Jeder Eintrag verlinkt auf die Originalquelle **und** auf die passende Stelle
  im Webbericht.
- Der sichtbare Abmeldelink steht in jeder Ausgabe. Gesetzt wird
  `List-Unsubscribe` mit der **`https://`-URL**. Keine `mailto:`-Variante,
  **kein `List-Unsubscribe-Post`** — das ist Festlegung 5.
- **Kein Modellaufruf.** Ein Test belegt, dass jeder inhaltstragende
  Textbestandteil (alles aus `items[]`) als Teilstring im Bericht-JSON
  vorkommt. Rahmentexte stehen in `templates/mail/chrome.yaml` und sind dem
  Test als Allowlist bekannt.
- `transport.py` kapselt den Versand hinter `send(message) -> Result`, mit
  einer **Brevo-HTTP-Implementierung** und einer Dry-Run-Implementierung. Kein
  SMTP-Code. Die Brevo-Implementierung gibt die Message-ID zurück, damit
  `bounce_sync.yml` Ereignisse zuordnen kann, und behandelt 4xx (dauerhafter
  Fehler, Empfänger markieren) und 429/5xx (Wiederholung mit Backoff)
  unterschiedlich.
- `scripts/preview_newsletter.py` erzeugt drei Beispielausgaben (voller Filter,
  minimaler Filter, reiner Stichwort-Treffer) nach `outputs/mail-preview/`.

---

### N4 — Signup-Dienst

Kleiner FastAPI-Dienst für Render Free unter `service/signup/`. Er speichert
nichts und verschickt nichts.

**Neu:** `service/signup/app.py`, `tokens.py`, `ratelimit.py`, `render.yaml`,
`tests/test_signup_service.py`.

**Akzeptanzkriterien:**

- `GET /form-token`: HMAC-signierte Nonce mit Ausstellungszeit. Ersetzt den
  fälschbaren Client-Zeitstempel und weckt die Instanz.
- `POST /subscribe`: prüft Adresssyntax, Honeypot und Nonce (Mindest- und
  Höchstalter), bremst per IP-Zähler, bildet ein HMAC-signiertes Token über
  Adresse, Filter, Einwilligungs-Textversion, Zeitstempel **sowie gepfefferte
  Hashes von IP und User-Agent** und löst `repository_dispatch` vom Typ
  `send_doi` aus. Antwortet mit 202 und einer neutralen Meldung — **nie** mit
  einem Hinweis, ob die Adresse bekannt ist.
- `GET /confirm/<token>`: prüft Signatur und TTL (72 Stunden), löst `confirm`
  aus, zeigt eine Bestätigungsseite. Token als **Pfadsegment**, nicht in der
  Query, dazu `Referrer-Policy: no-referrer`.
- `GET /unsubscribe/<token>`: löst `unsubscribe` aus und zeigt sofort eine
  Bestätigung. **Kein POST-Endpunkt für RFC 8058** (Festlegung 5).
- Der Dienst persistiert **nichts** außer einem In-Memory-IP-Zähler. Ein Test
  belegt, dass kein Schreibzugriff aufs Dateisystem erfolgt.
- **Die 24-Stunden-Sperre pro Adresse wird hier NICHT umgesetzt** — sie liegt
  im `send_doi`-Workflow (N5).
- Antworten unter 200 ms bei warmem Dienst; das Frontend bekommt den 202 sofort
  und wartet nicht auf GitHub.
- Das GitHub-Token ist ein fein granulares PAT ausschließlich auf das leere
  Dispatch-Repo `telco-radar-inbox` (siehe 3.4), nicht auf den Store. Es steht
  nur in der Render-Umgebungsvariable.

---

### N5 — Privates Repo und Abo-Store

**Neu:** privates Repo `telco-radar-mail` mit
`.github/workflows/doi.yml` und `confirm.yml`,
`store/subscribers.jsonl.age`, `store/send_log.jsonl`, `store/doi_log.jsonl`,
`scripts/store.py`, `tests/`.

**Außerdem:** das leere Dispatch-Repo `telco-radar-inbox` mit
Weiterreich-Workflow (siehe 3.4).

**Akzeptanzkriterien:**

- `subscribers.jsonl` liegt mit `age` oder SOPS verschlüsselt im Repo; der
  Schlüssel ist ein Actions-Secret. Entschlüsselt existiert die Datei nur zur
  Laufzeit im Runner.
- **Konfliktbehandlung auf JSONL-Ebene, nicht per Git-Rebase.** Ein
  `age`-Ciphertext ändert sich bei jedem Schreibvorgang vollständig; jeder
  Konflikt wäre ein Binärkonflikt. Ablauf: entschlüsseln, auf Zeilenebene
  zusammenführen (Schlüssel `id`, jüngerer Zeitstempel gewinnt), neu
  verschlüsseln, committen.
- Alle Workflows, die den Store anfassen — `doi`, `confirm`, `bounce_sync` und
  `newsletter` — laufen in derselben `concurrency`-Gruppe mit
  `cancel-in-progress: false`. Ein Test startet zwei Bestätigungen gleichzeitig
  und belegt, dass keine verloren geht.
- **Die 24-Stunden-Sperre pro Adresse liegt hier**: `doi.yml` prüft einen
  gepfefferten Adress-Hash gegen `doi_log.jsonl` und verwirft stillschweigend,
  wenn dieselbe Adresse in 24 Stunden schon eine Bestätigungsmail bekam.
- Jede Adresse wird vor jeder Verwendung mit `::add-mask::` maskiert. Ein
  Prüfschritt testet die Logausgabe gegen ein `@`-Adressmuster.
- Das Einwilligungsprotokoll nach 4.1 wird vollständig geschrieben. **Alle
  Hashes sind HMAC-SHA256 mit geheimem Pepper** aus den Secrets.
- Eine Domain-Allowlist ist als Konfiguration vorgesehen (leer, siehe
  Festlegung 3) und wird beim `confirm` ausgewertet.
- Abmeldung setzt `state: unsubscribed` und **löscht die Adresse**, behält aber
  den gepfefferten Adress-Hash.
- Das PAT des Signup-Dienstes zeigt nur auf `telco-radar-inbox`. Auf `main` von
  `telco-radar-mail` liegt Branch-Protection.

---

### N6 — Versand und Bounce-Abgleich

**Neu (privates Repo):** `.github/workflows/newsletter.yml`,
`.github/workflows/bounce_sync.yml`, `scripts/send_digest.py`,
`scripts/bounce_sync.py`.

**Neu (öffentliches Repo):** ein `repository_dispatch`-Schritt am Ende von
`.github/workflows/radar.yml`, der nur Datum und Commit-SHA weitergibt.

**Akzeptanzkriterien:**

- `newsletter.yml` wird per `repository_dispatch` **nach** erfolgreichem Deploy
  ausgelöst. Ein Fehlschlag darf den Radar-Lauf nicht rot färben.
- Idempotenz dreistufig nach Risiko b: gepushter Sendeplan vor dem Versand,
  Anhängen ans `send_log.jsonl` per Contents-API mit `sha`-Vorbedingung nach
  jeder Zustellung, beim Wiederanlauf „im Zweifel überspringen". Ein Test
  simuliert einen Abbruch mitten im Versand und belegt, dass der Wiederanlauf
  nichts doppelt versendet.
- **Limit-Wächter:** Vor dem Start wird die Zahl geplanter Zustellungen
  gezählt **und die Zahl der am selben Tag bereits versendeten aus
  `send_log.jsonl` addiert**. Überschreitet die Summe den konfigurierten
  Schwellwert (Standard 280, Reserve unter Brevos 300), bricht der Lauf mit
  klarer Meldung ab — kein stiller Teilversand.
- Versandrate gedrosselt (Standard 30 Mails pro Minute, konfigurierbar), über
  die Brevo-HTTP-API mit wiederverwendeter HTTP-Session.
- Leere Ausgaben werden nicht verschickt. Wer vier Wochen in Folge leer wäre,
  bekommt einmal monatlich den Hinweis mit Link zur Filteranpassung.
- `bounce_sync.yml` läuft **täglich** per Cron und fragt die
  **Brevo-Events-API** ab: Hard Bounce oder Beschwerde setzt sofort
  `state: bounced`, fünf Soft Bounces in Folge ebenfalls. Zuordnung über die
  in `send_log.jsonl` gespeicherte Message-ID. Der zuletzt verarbeitete
  Zeitstempel wird festgehalten, damit Ereignisse nicht doppelt laufen. Kein
  IMAP, kein Postfach.
- Der Lauf schreibt eine Statuszeile ins öffentliche `protokoll.html`:
  Ausgabedatum, Segmente, Zustellungen, Fehler, Bounces, Abmeldungen —
  **Zahlen, keine Adressen**.
- Ein `dry_run`-Eingabeparameter rendert alles und versendet nichts.

---

### N7 — Anmeldeformular und Themenauswahl auf der Seite

**Erst starten, wenn N1 vollständig ist.**

**Neu:** Formularabschnitt im Seiten-Renderer, `site/newsletter.html`,
`site/newsletter-bestaetigt.html`, `site/newsletter-abgemeldet.html`,
JavaScript für Absenden und Stichwort-Vorschau.

**Akzeptanzkriterien:**

- Die vier Dimensionen sind auswählbar; neben jeder steht sichtbar, dass eine
  leere Auswahl „alles" bedeutet.
- Die Stichwort-Vorschau zählt **clientseitig gegen
  `site/data/keyword-index.json`** aus N2 und warnt oberhalb eines
  Schwellwerts.
- Der Einwilligungstext steht im Klartext neben einer **nicht
  vorausgewählten** Checkbox; er ist derselbe wie in
  `content/consent_texts/`.
- `GET /form-token` wird beim Seitenaufbau geholt, nicht erst beim Absenden —
  das weckt die Render-Instanz, während der Nutzer noch ausfüllt.
- Der Kaltstart ist trotzdem abgefangen: Nach dem Absenden sofort „Wird
  verarbeitet …", Timeout 90 Sekunden, danach verständliche Fehlermeldung mit
  Wiederholmöglichkeit. Kein hängender Spinner.
- Honeypot-Feld wird mitgeschickt.
- Bestätigungs- und Abmeldeseiten sind statisch und funktionieren auch, wenn
  der Signup-Dienst gerade nicht antwortet.
- Ohne JavaScript ist zumindest sichtbar, dass es den Newsletter gibt, mit
  Hinweis, dass die Anmeldung JavaScript braucht.

---

### N8 — Protokoll und Überwachung

**Neu:** Newsletter-Abschnitt in `protokoll.html` über
`src/telco_radar/report/`, `data/state/newsletter_stats.jsonl` (aggregiert,
ohne Personenbezug).

**Akzeptanzkriterien:**

- Je Ausgabe erscheinen im Protokoll: Datum, Segmente, Zustellungen, Fehler,
  Bounces, Abmeldungen, Neuanmeldungen — ausschließlich Zahlen.
- Zustellquote unter 95 Prozent oder mehr als drei Hard Bounces in einem Lauf
  erzeugen einen sichtbaren Warnhinweis.
- **Der Abstand zum 300er-Tageslimit wird in jeder Statuszeile ausgewiesen.**
  Ab 80 Prozent Auslastung ein Warnhinweis mit Verweis auf Ausbaustufe B —
  das ist die Grenze, die dieses Setup als Erstes erreicht.
- Ein CI-Test stellt sicher, dass in `newsletter_stats.jsonl` kein
  Adressmuster vorkommt.

---

### N9 — Pilot, dann Freischaltung

Kein neuer Code, sondern die Abnahme.

1. Zwei Wochen mit einer manuell eingetragenen Handvoll Adressen — das Formular
   ist noch nicht verlinkt. Vier Ausgaben, jede einzeln geprüft: Zustellung,
   Authentifizierungs-Header, Posteingang statt Spam, Darstellung in Outlook,
   Gmail-Web und einem Mobilclient, Abmeldelink, Linkziele.
2. Ein bewusst ausgelöster Doppelversand-Versuch (Workflow-Re-Run) muss
   nachweislich nichts wiederholen.
3. Eine Abmeldung über den sichtbaren Link durchspielen — und zwar nachdem der
   Signup-Dienst nachweislich mindestens 20 Minuten geschlafen hat. Das ist der
   einzige Abmeldeweg, also muss er im kalten Zustand funktionieren.
   Anschließend eine Adresse absichtlich hart bouncen lassen (Versand an eine
   erfundene Adresse) und prüfen, dass `bounce_sync.yml` sie am nächsten Tag
   auf `bounced` setzt.
4. Erst dann das Formular auf der Seite verlinken.
5. Nach vier Wochen offener Anmeldung: Zustellquote, Abmelderate,
   Stichwort-Rauschen und Abstand zum Tageslimit im Protokoll ansehen und
   Grenzwerte nachziehen.

---

## 7. Ausbaustufen für später

Bewusst **nicht** Teil von v1. Erst anfassen, wenn N1–N9 laufen.

**A — Eigene Absenderdomain (~10–20 € im Jahr). Derzeit ausgeschlossen.** Hier
nur festgehalten, weil es der einzige Weg ist, das DMARC-Alignment zu
reparieren — falls die Entscheidung irgendwann kippt, etwa weil der Testversand
aus N1 zeigt, dass die Ausgaben im Firmen-Spam landen. Bei Brevo wäre es
simpel: Domain registrieren → in Brevo als Absender hinzufügen → die drei
angezeigten DNS-Einträge (DKIM, SPF, DMARC) setzen → verifizieren → `From:`
umstellen → Testversand wiederholen. Ein halber Nachmittag.

Falls es dazu kommt: **kein Markenname.** „Vodafone" ist eine eingetragene
Marke; eine Registrierung außerhalb der Markeninhaberin ist je nach
Konstellation abmahnfähig oder ein DENIC-Streitfall. Markenfreie Alternativen,
die dasselbe leisten: `telco-radar.de`, `telco-insights.de`, `marktradar.de`.

**B — Über 300 Empfänger hinaus.** Zwei Wege, wenn der Verteiler das
Brevo-Tageslimit erreicht. Kostenlos: Der Versand verteilt sich über zwei
aufeinanderfolgende Tage, der Sendeplan aus N6 kann das ohne Umbau (er kennt
die Idempotenzschlüssel schon). Bezahlt: Brevos kleinster kostenpflichtiger
Plan hebt das Tageslimit auf. Der Wächter aus N6 und die Protokollzeile aus N8
sagen dir rechtzeitig, wann es so weit ist.

**C — Ein-Klick-Abmeldung nach RFC 8058.** Wird erst relevant, wenn der
Verteiler die Bulk-Sender-Schwelle von rund 5.000 Nachrichten pro Tag erreicht
— mit dem Free-Plan also nie. Setzt außerdem einen Endpunkt voraus, der nicht
spin-down-abhängig ist, also Render Starter (7 $/Monat).

**D — Wöchentliche Zusammenfassung statt jeder Lauf.** Ein zusätzlicher Wert
für `cadence`. Frühestens sinnvoll, wenn sich jemand über zwei Mails pro Woche
beschwert.

**E — Englische Fassung.** Filtermodell und Templates sind darauf vorbereitet,
solange die Textbausteine getrennt liegen. Braucht aber eine englische Fassung
des Berichts, nicht nur der Mail.

---

## 8. Quellen

Rechtliche Anforderungen:
[Die Compliance-Werkstatt zu Newsletter und DSGVO](https://www.diecompliancewerkstatt.de/newsletter-dsgvo/) ·
[Newsletter-Datenschutz, Pflichten 2026](https://www.windweiss.de/ratgeber/newsletter-datenschutz/) ·
[Double-Opt-in-Guide 2026](https://mail.e-publisher.de/blog/double-opt-in/)

Zustellbarkeit und Absenderanforderungen:
[Google, Email sender guidelines FAQ](https://support.google.com/a/answer/14229414?hl=en) ·
[Bulk-Sender-Anforderungen 2026 im Überblick](https://redsift.com/guides/bulk-email-sender-requirements)

Relay-Auswahl (Stand August 2026):
[Brevo Preispläne — Free: 300 Mails/Tag, dauerhaft, ohne Kreditkarte, ohne Branding](https://help.brevo.com/hc/en-us/articles/208589409-About-Brevo-s-pricing-plans) ·
[Brevo Transactional Email / API](https://www.brevo.com/products/transactional-email/) ·
[Mailjet Preise — Free: 6.000/Monat, 200/Tag, mit Mailjet-Logo](https://www.mailjet.com/pricing/) ·
[Twilio: Änderungen am kostenlosen SendGrid-Plan (eingestellt)](https://www.twilio.com/en-us/changelog/sendgrid-free-plan) ·
[Microsoft: Basic Auth / App-Passwörter für Privatkonten abgeschafft](https://support.microsoft.com/en-US/Support/known-issues/modern-authentication-methods-now-needed-to-continue-syncing-outlook-email-in-non-microsoft-email-ap) ·
[Gmail-Sendelimits in Google Workspace](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace)

Plattformgrenzen:
[Render, Deploy for Free — Ports 25/465/587, Spin-down, ephemeres Dateisystem, Free-Postgres-Ablauf](https://render.com/docs/free) ·
[SOPS und age in GitHub Actions](https://github.com/marketplace/actions/sops-exec)

Projektinterne Grundlagen: Projektübergabe „Telco Radar" (Stand 25. Juli 2026),
`claude/promo-uebersicht-konzept.md`,
`claude/site-review-und-feature-roadmap-2026-08-08.md` (Laufzeit 27,4 von 35
Minuten am 6. August 2026),
`claude/umsetzungsplan-claude-code-2026-08-08.md` (Format der Auftragstexte),
Live-Seite `telco-radar.onrender.com`, abgerufen am 11. August 2026
(Navigation, Fußbereich ohne Impressum und Datenschutz).
