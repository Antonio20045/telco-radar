# Mail-Setup des Telco-Radar-Newsletters

Stand: 11. August 2026. Diese Datei beschreibt den Versandweg, seine harten
Grenzen und die eine Schwäche, die bewusst in Kauf genommen ist.

---

## 1. Der Versandweg in einem Satz

GitHub Actions ruft die **HTTP-API von Brevo** auf, Brevo stellt zu. Der
Signup-Dienst auf Render verschickt nie selbst eine Mail, und die Website
schon gar nicht — sie ist eine Static Site.

```
newsletter.yml (privates Repo)
   -> POST https://api.brevo.com/v3/smtp/email      (Header: api-key)
   -> Brevo stellt zu
   -> bounce_sync.yml holt taeglich GET /v3/smtp/statistics/events
```

**Kein SMTP.** Nicht als Fallback, nicht für Testzwecke. Der Grund ist nicht
Geschmack: Render Free sperrt ausgehend die Ports 25, 465 und 587, und ein
zweiter Versandweg wäre ein zweiter Ort, an dem Absenderdaten und Fehlerfälle
gepflegt werden müssten. HTTPS ist offen, und die API beantwortet dieselbe
Frage.

## 2. Was schon eingerichtet ist

Antonio hat das am 11. August 2026 erledigt. **Nichts davon neu anlegen.**

| Was | Stand |
|---|---|
| Brevo-Konto | Free-Plan, Organisation `insights`, keine Kreditkarte |
| Kontingent | **300 von 300 E-Mails pro Tag**, Zähler setzt täglich zurück |
| Absender | `Telco Radar <antonio.fotiadis.francisco@gmail.com>`, **verifiziert** |
| API-Key | `telco-radar-newsletter`, gültig bis 11.08.2027, liegt als GitHub-Secret `BREVO_API_KEY` in **beiden** Repositories: `telco-radar` (Testversand) und `telco-radar-mail` (Versand). Am 13.08.2026 nachgetragen — vorher stand er in keinem. |
| Versand | **Freigeschaltet am 13.08.2026.** Der erste Versuch bekam
`HTTP 403 permission_denied` ("SMTP account is not yet activated"), auch in
Brevos eigener Oberflaeche. Ursache: die Kontoregistrierung war bei Schritt
2 von 5 stehengeblieben, die Unternehmensanschrift fehlte. Nach dem
Nachtragen ging der Versand sofort. |
| **Absenderdomaene** | **Wird von Brevo ersetzt.** Im `From:` steht nicht
`@gmail.com`, sondern `antonio.fotiadis.francisco@11874756.brevosend.com`.
Brevo tut das bei nicht authentifizierten Domaenen automatisch. Folge fuer
3.3: SPF, DKIM und DMARC richten sich damit auf *Brevos* Domaene aus, sind
also technisch sauber — der Preis ist ein Absender, der nach Maschine
aussieht. Eine eigene Domain waere die einzige Abhilfe. |

**Der API-Key steht nirgends im Code, in keiner Datei und in keinem Log.**
Ausschließlich als Secret. Wer ihn braucht, holt ihn über
`${{ secrets.BREVO_API_KEY }}` in den Workflow.

## 3. Die drei Grenzen, die im Alltag zuerst weh tun

### 3.1 300 Mails pro Tag — das ist die Verteilerobergrenze

Das ist keine ferne Zahl, sondern die Grenze, die dieses Setup **als Erstes**
erreicht. Bei zwei Ausgaben pro Woche an verschiedenen Tagen sind das 300
Abonnenten insgesamt. Ein Wiederanlauf, eine Testausgabe und die
Bestätigungsmails von Neuanmeldungen zählen mit.

Deshalb rechnet `send_digest.py` **vor** dem Start: geplante Zustellungen plus
das, was heute laut `send_log.jsonl` schon draußen ist. Über dem Schwellwert
(Standard **280**, Reserve unter den 300) bricht der Lauf ab, statt die halbe
Liste zu bedienen und die andere Hälfte stumm zu übergehen. Der Abstand zum
Limit steht in jeder Statuszeile auf `transparenz.html`.

### 3.2 Der API-Key verfällt nach 90 Tagen ohne Nutzung

Unabhängig vom Ablaufdatum. Bei zwei Läufen pro Woche kann das nicht
passieren — **nach einer längeren Projektpause ist ein toter Key aber die
erste Ursache, die zu prüfen ist, bevor jemand im Code sucht.** Symptom: HTTP
401 auf jeden Aufruf, auch auf den harmlosesten.

Gegenprobe, die nichts verschickt:

```bash
curl -sS -H "api-key: $BREVO_API_KEY" https://api.brevo.com/v3/account | head -c 400
```

### 3.3 Der Absender ist nicht ausgerichtet — und das bleibt so

**Das ist die wichtigste Zeile dieser Datei.**

Ohne eigene Domain verifiziert man bei Brevo einen *Einzelabsender*. Brevo
signiert dann mit **eigenem** DKIM, im `From:` steht aber eine
Gmail-Adresse — die beiden Domains stimmen nicht überein, also fehlt das
**DMARC-Alignment**. Brevo weist im Dashboard selbst darauf hin
(„Freemail-Domain wird nicht empfohlen").

Eine eigene Domain ist ausgeschlossen (Festlegung 2 des Konzepts). Das ist
damit **der dauerhafte Zustand, kein zu behebender Fehler.** Wer beim nächsten
Zustellproblem anfängt, im Code zu suchen, sucht an der falschen Stelle.

Warum keine der naheliegenden Alternativen geht — gemessen am 11.08.2026:

```
_dmarc.vodafone.com  → v=DMARC1; p=reject;    (Mail wird verworfen)
_dmarc.vodafone.de   → v=DMARC1; p=quarantine
_dmarc.web.de        → p=quarantine
_dmarc.gmx.de        → p=quarantine
_dmarc.mailbox.org   → p=reject
_dmarc.gmail.com     → p=none                 ← deshalb diese Wahl
```

`gmail.com` auf `p=none` heißt: Die Mail wird nicht abgewiesen, sie hat nur
keine Ausrichtung. Bei `p=reject` käme sie nirgends an.

**Der Anzeigename ist `Telco Radar` und enthält keinen Markennamen.** Ein
Markenname vor einer nicht zur Marke gehörenden Adresse ist genau das Muster,
auf das Konzern-Gateways als Display-Name-Spoofing anschlagen — und
markenrechtlich gilt dasselbe wie bei der Domain.

## 4. Der Testversand — Lauf vom 13.08.2026

`.github/workflows/mail_test.yml` (Wegwerf, nur `workflow_dispatch`).
Lauf `31701576584`, 13.08.2026 14:45 MESZ.

| Was | Ergebnis |
|---|---|
| `POST /v3/smtp/email`, Freemail | **HTTP 201**, `202608131245.50237314179@smtp-relay.mailin.fr` |
| `POST /v3/smtp/email`, Firma | **HTTP 201**, `202608131245.37351269242@smtp-relay.mailin.fr` |
| Brevo-Log, Freemail | **Zugestellt** |
| Brevo-Log, Firma (`@vodafone.com`) | **Zugestellt** — das Konzern-Gateway hat *angenommen* |
| tatsaechlicher Absender | `antonio.fotiadis.francisco@11874756.brevosend.com` |
| `GET /v3/smtp/statistics/events` nach 30 s | HTTP 200, **0 Ereignisse** |

**Der Sichtbefund, den kein Log liefert** (Antonio, 13.08.2026):

| Frage | Antwort |
|---|---|
| Freemail-Postfach | **Posteingang** |
| **Firmenpostfach (`@vodafone.com`)** | **Posteingang** — nicht Spam |
| `Authentication-Results`-Zeile | nicht erfasst |

Damit ist die Frage beantwortet, die ueber das Vorhaben entschieden hat: das
Konzern-Gateway laesst diesen Versandweg in den Posteingang. Der Grund ist
mit hoher Wahrscheinlichkeit die Absenderersetzung aus Abschnitt 2 — weil
Brevo die Domaene durch `11874756.brevosend.com` austauscht, sind SPF, DKIM
und DMARC ausgerichtet. Die Befuerchtung aus 3.3 (nicht ausgerichteter
Freemail-Absender) trifft in dieser Konstellation nicht zu.

**Das ist eine Momentaufnahme, keine Garantie.** Sie gilt fuer eine einzelne
Mail ohne Verteiler-Historie. Reputation entsteht erst ueber Wochen, und ein
Konzern-Gateway bewertet Massenversandmuster spaeter strenger als einen
Einzelversand. Wenn Ausgaben spaeter im Spam landen, ist das kein Widerspruch
zu dieser Zeile.

Zu den 0 Ereignissen: die Events-API antwortete korrekt mit HTTP 200, die
Ereignisse standen wenige Minuten spaeter im Log. Die 30 Sekunden Wartezeit im
Workflow sind schlicht zu knapp. Fuer `bounce_sync.yml` ist das ohne Belang —
der laeuft taeglich, nicht sekundenaktuell.

`mail_test.yml` und `.github/scripts/mail_test.py` sind mit diesem Commit
**geloescht** — der Workflow nahm beliebige Empfaengeradressen entgegen und
hatte im Dauerbetrieb nichts zu suchen. Wer ihn wiederbraucht (etwa nach dem
Umzug auf eine eigene Domain), holt ihn aus der Git-Historie zurueck.

## 5. Fehlerbilder und ihre erste Ursache

| Symptom | Zuerst prüfen |
|---|---|
| HTTP 401 auf jeden Aufruf | Key nach 90 Tagen ohne Nutzung verfallen (3.2) |
| HTTP 400 `sender not valid` | Absender im Brevo-Konto nicht mehr verifiziert |
| HTTP 429 | Tageskontingent oder Ratengrenze — der Wächter hätte vorher greifen müssen (3.1) |
| Versand meldet Erfolg, niemand hat etwas | Spam-Ordner, dann 3.3 lesen |
| Hard Bounces steigen | `bounce_sync.yml`-Lauf und die Statuszeile auf `transparenz.html` |
| Konto plötzlich deaktiviert | Beschwerdequote — Free-Konten werden ohne Vorwarnung abgeschaltet |

## 6. Was der Versand NICHT tut

- **Kein Modellaufruf.** Die Mail besteht ausschließlich aus Textbausteinen,
  die schon im Bericht-JSON stehen. Ein Test hält jeden inhaltstragenden Block
  gegen die Quelle.
- **Keine Öffnungs- oder Klickmessung.** Keine Zählpixel, keine umgeschriebenen
  Links. Ausgewertet werden nur Summen je Ausgabe.
- **Kein `List-Unsubscribe-Post` nach RFC 8058.** Die Ein-Klick-Abmeldung ist
  eine Anforderung an Bulk-Sender ab rund 5.000 Nachrichten pro Tag; bei 300
  Mails Tageslimit ist sie unerreichbar. Sie würde außerdem maschinell mit
  kurzem Timeout in den Render-Kaltstart laufen und still fehlschlagen — der
  Nutzer hielte sich für abgemeldet, die nächste Ausgabe käme trotzdem.
  Gesetzt wird `List-Unsubscribe` mit der `https://`-URL, dazu der sichtbare
  Link in jeder Mail.
- **Kein `mailto:` im Abmelde-Header.** Es gibt in dieser Architektur kein
  Postfach, das ihn auswerten könnte.
