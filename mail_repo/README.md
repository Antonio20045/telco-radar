# Bündel für die zwei privaten Repositories

Dieses Verzeichnis ist **kein laufender Code**, sondern der Inhalt zweier
Repositories, die noch angelegt werden müssen. Es liegt hier, weil es hier
entstanden und getestet ist — nicht, weil es hier hingehört.

```
mail_repo/.github/workflows/   →  Antonio20045/telco-radar-mail   (privat)
mail_repo/inbox/               →  Antonio20045/telco-radar-inbox  (privat, leer)
```

---

## Warum drei Repositories und nicht eines

**Adressen von Abonnenten sind personenbezogene Daten. Im öffentlichen Repo
haben sie in keiner Form etwas zu suchen** — auch nicht verschlüsselt, auch
nicht kurz, auch nicht im Payload eines `repository_dispatch`. Ein Commit mit
einer Adressliste ist über Git-Historie und Forks dauerhaft öffentlich, und
das ist ein meldepflichtiger Vorfall nach Art. 33 DSGVO mit
72-Stunden-Frist — kein Bug, den man wegrebased.

Das dritte Repo (`telco-radar-inbox`) ist der Teil, den man leicht für
Übervorsicht hält. Er ist es nicht:

> Der Signup-Dienst auf Render braucht ein GitHub-Token, um Ereignisse
> weiterzureichen. Ein Token mit `contents: write` auf `telco-radar-mail`
> könnte `scripts/…/send_digest.py` überschreiben — **genau die Datei, die
> der Workflow danach mit dem Entschlüsselungsschlüssel ausführt.** Wer den
> Render-Dienst übernimmt, hätte damit Codeausführung im Runner und den
> entschlüsselten Verteiler.

Deshalb: Das Token des Dienstes gilt **nur** für `telco-radar-inbox`, ein
leeres Repo ohne Daten. Ein Workflow dort reicht das Ereignis an
`telco-radar-mail` weiter, mit einem Token, das nur in Actions liegt.

## Warum die Logik im öffentlichen Repo bleibt

Die Workflows hier enthalten **keine Programmlogik**. Sie checken
`Antonio20045/telco-radar` aus und rufen dessen Skripte auf.

Die naheliegende Alternative — den Store im privaten Repo programmieren —
wäre falsch: dort bräuchte er eine Kopie der Filter-Engine, und eine Kopie
driftet. Nach drei Monaten schickte die Mail etwas anderes, als die Website
zeigt, und niemand könnte sagen, welche von beiden stimmt.

**Die Logik hier, die Daten dort.** In `telco-radar` liegt keine einzige
Adresse; ein Test misst das (`test_keine_jsonl_im_repo_enthaelt_ein_adressmuster`).

---

## Einrichtung

### 1. `telco-radar-inbox` (privat, leer)

Nur `inbox/.github/workflows/weiterreichen.yml` hineinkopieren.

Secret: `MAIL_REPO_TOKEN` — ein fein granulares PAT, dessen **Resource owner
`Antonio20045`** ist und das als **einziges** Repository `telco-radar-mail`
ausgewählt hat, mit **Repository permissions → Contents: Read and write**.

> **Es gibt keine Berechtigung namens `repository_dispatch`.** Bis zum
> 13.08.2026 stand genau das hier, und ein Token, das man danach baut, gibt
> es nicht — `POST /repos/{owner}/{repo}/dispatches` verlangt bei fein
> granularen Token **Contents: write**. Das ist kontraintuitiv (es wird
> nichts geschrieben), aber es ist die Regel.
>
> Die zwei Fehlerbilder auseinanderhalten:
> **`401 Bad credentials`** = der Wert des Secrets stimmt nicht (abgelaufen,
> beim Einfügen abgeschnitten, oder ein klassisches Token, das widerrufen
> wurde). **`403`** = der Wert stimmt, die Berechtigung fehlt. Nur beim
> zweiten hilft es, an den Häkchen zu drehen.

### 2. `telco-radar-mail` (privat)

`.github/workflows/*.yml` hineinkopieren, dazu ein leeres `store/`.

Branch-Protection auf `main`: Das PAT des Signup-Dienstes kann so auch dann
nicht pushen, wenn es doch einmal auf dieses Repo zeigt.
`repository_dispatch` funktioniert weiter — es ist keine Dateioperation.

**Secrets:**

| Name | Was |
|---|---|
| `AGE_SECRET_KEY` | Entschlüsselt `store/subscribers.jsonl.age`. Ohne ihn ist der Verteiler weg — **eine Kopie gehört in einen Passwortmanager, nicht nur hierhin.** |
| `SIGNUP_TOKEN_KEY` | HMAC-Schlüssel der Token. **Muss identisch sein mit dem im Render-Dienst**, sonst fällt jedes Bestätigungstoken durch. |
| `SIGNUP_PEPPER` | Pepper der Kennwerte. **Muss ebenfalls identisch sein** — sonst passt kein einziger Adress-Kennwert zusammen, und die 24-Stunden-Sperre greift nie. |
| `BREVO_API_KEY` | Derselbe Key wie im öffentlichen Repo. |
| `PUBLIC_REPO_TOKEN` | `contents: read` auf `Antonio20045/telco-radar` (falls das Repo je privat wird; für ein öffentliches Repo genügt der normale Checkout). |

**Variablen** (`vars`, keine Secrets): `SITE_BASE_URL`, `MAIL_FROM`,
`ERLAUBTE_DOMAINS` (leer = offen für alle, Festlegung 3).

### 3. Den ersten Store anlegen

```bash
age-keygen -o age.key                  # den öffentlichen Teil merken
printf '' > subscribers.jsonl
age -r <PUBLIC_KEY> -o store/subscribers.jsonl.age subscribers.jsonl
rm subscribers.jsonl                   # nie im Klartext committen
```

### 4. Den Deploy-Anstoß im öffentlichen Repo

`radar.yml` schickt am Ende ein `repository_dispatch` vom Typ `report_ready`
mit Datum und Commit-SHA. Der Schritt steht dort schon; er braucht das Secret
`INBOX_DISPATCH_TOKEN` und tut ohne es nichts (mit einer Zeile im Protokoll).

---

## Die drei Stellen, an denen ein Fehler hier still Abos löscht

1. **`git pull --rebase` kann eine `age`-verschlüsselte Datei nicht
   zusammenführen.** Jeder Ciphertext unterscheidet sich bei jedem
   Schreibvorgang vollständig; jeder Konflikt ist ein Binärkonflikt, und
   „ours" oder „theirs" wirft die halbe Liste weg. Deshalb überall:
   entschlüsseln → auf JSONL-Zeilenebene zusammenführen → neu verschlüsseln.
2. **Alle Workflows, die den Store anfassen, teilen sich eine
   `concurrency`-Gruppe mit `cancel-in-progress: false`.** Ein abgebrochener
   Bestätigungs-Workflow ist eine verlorene Anmeldung, die niemandem
   auffällt — der Nutzer hat auf der Seite „Angemeldet" gelesen.
3. **In keinem Log darf je eine Adresse stehen.** Jede wird vor der ersten
   Verwendung mit `::add-mask::` maskiert, und die Skripte geben Zahlen aus
   statt Adressen. Ein Actions-Log ist öffentlich, sobald das Repo es ist.

## Was hier bewusst NICHT steht

- **Kein Keep-alive-Ping** auf den Render-Dienst. Ein Monat hat rund 730
  Stunden, das Free-Kontingent 750 Instanzstunden — ein Dauerping bräuchte es
  allein auf und schaltete den Dienst genau dann ab, wenn jemand ihn braucht.
- **Kein `List-Unsubscribe-Post`** (RFC 8058). Siehe `docs/mail-setup.md` §6.
- **Kein IMAP-Postfach** für Bounces. Die Events-API ist die Quelle.
