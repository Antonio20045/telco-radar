# Newsletter — Schlussliste

11. August 2026. Grundlage: `claude/newsletter-konzept-2026-08-11.md`
(N1–N9). Gebaut sind **N1 bis N8 vollständig**; N9 ist die Abnahme und lässt
sich aus einer Sandbox nicht durchführen — was dafür zu tun ist, steht in
Abschnitt 4.

| | vorher | nachher |
|---|---|---|
| Tests | 1416 | **1647** (+231) |
| `pruefe_portal.py` | 15 / 0 / 0 | **16 / 0 / 0** |
| Crawlbare Quellen | 207 | 207 (unberührt) |
| Navigationseinträge | 5 | 5 — der sechste schaltet sich selbst (siehe 2.1) |

Sieben Commits, je Paket einer: `b4b8dac` (N1), `9fb7e19` (N2), `e885d9f`
(N3), `78d2972` (N4), `b409016` (N5+N6), `bb8821b` (N7+N8).

---

## 1. Was gebaut ist

| Paket | Kern | Dateien |
|---|---|---|
| **N1** | Impressum, Datenschutz, Einwilligungstexte, Mail-Setup | `content/legal/`, `content/consent_texts/`, `report/rechtstexte.py`, `docs/mail-setup.md`, `.github/workflows/mail_test.yml` |
| **N2** | Filter-Engine, Abo-Modell, Segmente | `newsletter/{config,filters,quelle,segments,subscription}.py`, `config/newsletter.yaml` |
| **N3** | Mail-Renderer und Transport | `newsletter/{render,transport}.py`, `templates/mail/`, `scripts/preview_newsletter.py` |
| **N4** | Signup-Dienst | `service/signup/{app,tokens,ratelimit}.py`, `render.yaml` |
| **N5** | Abo-Store, private Repos | `newsletter/store.py`, `scripts/newsletter/abo.py`, `mail_repo/` |
| **N6** | Versand, Idempotenz, Limit-Wächter, Bounces | `newsletter/versand.py`, `scripts/newsletter/{send_digest,bounce_sync}.py` |
| **N7** | Anmeldeformular, Stichwort-Vorschau | `report/newsletter_seite.py`, drei Vorlagen, `app.js` |
| **N8** | Protokoll auf der Quellenseite | `report/newsletter_protokoll.py`, `.github/workflows/newsletter_stats.yml` |

---

## 2. Die sechs Stellen, an denen anders gebaut wurde als geplant

### 2.1 Zwei Veröffentlichungsschwellen statt einer Reihenfolgeregel

Das Konzept sagt: „N7 darf erst live gehen, wenn N1 vollständig ist." Das ist
eine Anweisung an einen Menschen — und dieses Projekt hat teuer gelernt, was
damit passiert: Die Geräteseite stand am 10.08. fertig, geprüft und live und
war für jeden Leser unauffindbar, weil das Eintragen in die Navigation
Handarbeit blieb.

Gebaut ist deshalb eine **Mechanik**: `rechtstexte.vollstaendig()` rechnet, ob
Impressum und Datenschutzerklärung ohne offene Stelle sind;
`render_site()` setzt daraus das Jinja-Global `newsletter_verlinkt`.
Unterhalb der Schwelle wird die Seite gebaut, sagt sichtbar warum sie
gesperrt ist, hat einen abgeschalteten Absendeknopf und **keinen
Navigationseintrag**. Beide Zweige sind gemessen
(`tests/test_newsletter_seite.py`).

**Die ladungsfähige Anschrift fehlt.** Sie kann diese Codebasis nicht wissen —
sie steht als `{{ANSCHRIFT}}` im Text, erscheint auf der Seite als sichtbare
Lücke und hält die Schwelle geschlossen. **Das ist der eine Punkt, den nur ein
Mensch schließen kann**, wie `config/vodafone_hebel.yaml`. Zwei Zeilen in
`content/legal/impressum.md` und `datenschutz.md`, dann schaltet sich der
Newsletter selbst frei.

Die zweite Bedingung ist `newsletter_dienst_url` in `config/settings.yaml`
(leer ausgeliefert). Beide sind unabhängig.

### 2.2 Die Store-Logik bleibt im öffentlichen Repo

Das Konzept legt `scripts/store.py` und `scripts/send_digest.py` ins private
Repo. Gebaut ist es andersherum: **die Logik hier, die Daten dort.** Die
Workflows in `mail_repo/` enthalten keine Programmlogik; sie checken dieses
Repo aus und rufen `scripts/newsletter/*.py` auf.

Der Grund: im privaten Repo bräuchte der Store eine Kopie der Filter-Engine,
und eine Kopie driftet. Nach drei Monaten schickte die Mail etwas anderes, als
die Website zeigt — genau der Fehler, den „kein Modellaufruf im Versandpfad"
verhindern soll, nur eine Ebene tiefer. In diesem Repo liegt trotzdem keine
einzige Adresse; ein Test misst das über alle `*.jsonl`.

### 2.3 `versende()` sucht die Nachricht unter zwei Schlüsseln

Gerendert wird einmal je Segment — das ist der Sinn der Segmentierung. Die
Abmelde-URL trägt aber ein signiertes Token **je Abo**. Der Aufrufer legt die
personalisierte Fassung deshalb unter dem vollen Sendeschlüssel ab; wo es
nichts zu personalisieren gibt, reicht der Segmentschlüssel. Personalisiert
wird durch Ersetzen der Platzhalter-URL in HTML, Text und Header — nicht durch
erneutes Rendern.

### 2.4 `mail_test.yml` bleibt vorerst stehen

Das Konzept sagt „danach den Workflow wieder entfernen". Er kann in dieser
Session nicht gelaufen sein (kein Secret-Zugriff, keine realen Postfächer) —
ihn zu löschen hieße, das einzige Werkzeug für die entscheidende Messung
wegzuwerfen. Er steht als `workflow_dispatch`, und in `docs/mail-setup.md`
§4 steht, dass er nach dem Eintragen des Ergebnisses zu löschen ist.

### 2.5 Der Index der Stichwort-Vorschau hat einen eigenen Tokenizer

Siehe 3.2 — das ist ein Befund, keine Entwurfsentscheidung.

### 2.6 Der Newsletter-Abschnitt steht auf `transparenz.html`

Das Konzept nennt `protokoll.html`. Diese Datei ist seit dem Redesign eine
Weiterleitung; die Seite heißt `transparenz.html`.

---

## 3. Fünf Befunde, die erst beim Messen aufgetaucht sind

### 3.1 Der Satztrenner zerreißt deutsche Datumsangaben — im ganzen Projekt

**Gefunden beim Ansehen der ersten Mail-Vorschau.** Dort stand als ganzer
Satz: „Aktion gültig bis 12." Der Trenner `(?<=[.!?])\s+` sieht in
„12. September" ein Satzende — Punkt, Leerzeichen, Großbuchstabe.

Das ist ein **vorbestehender Fehler in `textwerkzeug.saetze()`** und trifft
damit nicht nur die Mail: `_strip_vodafone_advice` schneidet den Wochenbericht
mit derselben Funktion, und dort fällt dann eine Satzhälfte als vermeintlicher
Rat weg. An der Wurzel behoben, geschützt bewusst **nur vor einem
Monatsnamen** — „Die Zahl stieg auf 12. Vodafone reagierte." bleibt zwei
Sätze. Zwei Tests halten beide Fälle.

### 3.2 Browser und Python zählten verschieden — genau dafür war der Test da

Die Stichwort-Vorschau zählt clientseitig gegen `keyword-index.json`,
`vorschau()` zählt in Python gegen die Berichte. Gemessen im echten Chromium:

| Begriff | Browser | Python |
|---|---|---|
| `tarif` | 6 | **13** |

Der Index tokenisierte mit `textwerkzeug.wortmenge()`, das den Bindestrich
**innerhalb** eines Wortes zulässt („Tarif-Rabatt" = ein Wort). Der Matcher
behandelt ihn als **Wortgrenze**, damit „Netzausbau" in
„Glasfaser-Netzausbau" trifft. Die Vorschau hätte also die Hälfte
unterschlagen — und ein Test, der dieselbe Rechnung zweimal macht, wäre grün
geblieben. Der Index hat jetzt einen eigenen Tokenizer mit denselben Grenzen;
vier Begriffe werden im Browser gegen Python gehalten.

### 3.3 „Ihr Stichwort: Starlink" stand viermal untereinander

Stichworttreffer stehen hinter den Filtertreffern, gleiche Marken folgen also
zwangsläufig aufeinander. Viermal dieselbe Zeile erklärt nichts mehr, sie
trommelt. Jetzt nennt nur der erste einer Folge sein Stichwort — dieselbe
Hausregel wie auf der Website: eine Angabe steht je Ort genau einmal.

### 3.4 Der Newsletter-Abschnitt lag versehentlich in `{% if run %}`

Auf `transparenz.html` umschließt `{% if run %}` einen 200-Zeilen-Block. Der
neue Abschnitt landete darin und verschwand ohne Laufprotokoll — in
Produktion wäre das nie aufgefallen, weil es dort immer ein Laufprotokoll
gibt. Der Test ohne Bericht hat es gefunden.

### 3.5 Drei Tests hingen an der Wanduhr

Der letzte Testlauf dieser Session fiel über Mitternacht: 279 Sendeprotokoll-
Einträge trugen den 11. August, und am 12. zählte `heute_versendet()` sie zu
Recht nicht mehr mit — der Limit-Wächter griff nicht, und der Test fiel
durch, **ohne dass sich eine Zeile Code geändert hatte.** Derselbe Fehler
lauerte in zwei Vorschau-Tests: Sie messen die letzten 30 Tage gegen die
Berichte im Repo, und dreißig Tage nach dem letzten Lauf hätte ein frischer
Checkout dort null Meldungen gefunden.

Alle drei geben den Stichtag jetzt ausdrücklich mit — die Vorschau-Tests
leiten ihn aus der jüngsten Ausgabe ab. **Ein Test, dessen Ergebnis vom Datum
abhängt, meldet nicht den nächsten Umbau, sondern die nächste Mitternacht.**

**Alle drei Sichtprüfungen waren nötig:** Die Mail wurde im echten Chromium
auf 700 und 390 px fotografiert, die Anmeldeseite auf 1440 und 390 px. Aus
dem zweiten Blick kamen zwei weitere Mängel: Die Rubrikleisten liefen durch
ihre eigene Überschrift (ein `<legend>` sitzt per Voreinstellung **in** der
Rahmenlinie seines Fieldsets — die einzige Stelle im ganzen Stylesheet, an der
das vorkommt), und der Einwilligungstext trug die 78-Zeichen-Umbrüche der
Quelldatei quer zu einer 64-Zeichen-Spalte.

---

## 4. Was offen ist — und was davon nur ein Mensch schließen kann

### 4.1 Nur ein Mensch

1. **Die ladungsfähige Anschrift.** Zwei Zeilen in `content/legal/`. Solange
   sie fehlt, ist der Newsletter nicht verlinkt (2.1). *Der einzige Punkt,
   der das ganze Vorhaben blockiert.*
2. **Der Testversand (N1).** `.github/workflows/mail_test.yml` von Hand
   starten, dann `docs/mail-setup.md` §4 ausfüllen — **auch wenn das Ergebnis
   schlecht ist.** Die eine Zeile, auf die es ankommt: *landet die Mail im
   Firmenpostfach im Posteingang oder im Spam?* Ohne eigene Domain fehlt das
   DMARC-Alignment; das ist kein Bug, sondern der dauerhafte Zustand. Fällt
   die Antwort schlecht aus, steht die Frage an, ob der Newsletter für diese
   Zielgruppe trägt oder ob Ausbaustufe A (eigene Domain, ein halber
   Nachmittag) doch fällig wird.
3. **Die drei Repositories anlegen** nach `mail_repo/README.md`:
   `telco-radar-mail` (privat), `telco-radar-inbox` (privat, leer), dazu die
   Secrets. **`SIGNUP_TOKEN_KEY` und `SIGNUP_PEPPER` müssen im Render-Dienst
   und im privaten Repo identisch sein** — sonst fällt jedes
   Bestätigungstoken durch und die 24-Stunden-Sperre greift nie.
4. **Den Signup-Dienst auf Render anlegen** (`service/signup/render.yaml`),
   dann `newsletter_dienst_url` in `config/settings.yaml` eintragen.
5. **AV-Verträge** mit GitHub, Render und Brevo abschließen und die
   Verarbeitung ins Verzeichnis eintragen. Die Datenschutzerklärung nennt sie
   bereits.

### 4.2 Erst nach dem ersten echten Lauf prüfbar

- **Der Versand ist noch nie gegen die echte Brevo-API gelaufen.** Getestet
  ist er gegen einen nachgebauten Endpunkt: Message-ID, 4xx/429/5xx, 401. Was
  ein echtes Konto antwortet, steht danach in `docs/mail-setup.md` §5.
- **Die Events-API hat noch nie ein echtes Ereignis geliefert.** Ist die
  Zuordnung über die Message-ID falsch, meldet `bounce_sync` „nicht
  zuzuordnen" statt Rückläufern — die Zahl steht im Protokoll.
- **Die Zeile `Newsletter angestossen für …`** in `radar.yml`: Ohne
  `INBOX_DISPATCH_TOKEN` sagt sie das und tut nichts. Das ist der Zustand vor
  der Einrichtung, kein Fehler.
- **Die Mail ist noch in keinem echten Client gesehen worden.** Gemessen sind
  Chromium auf 700 und 390 px; N9 verlangt Outlook, Gmail-Web und einen
  Mobilclient. `outputs/mail-preview/` liegt bereit.

### 4.3 Die Abnahme (N9), in dieser Reihenfolge

1. Zwei Wochen mit einer Handvoll manuell eingetragener Adressen, Formular
   noch nicht verlinkt. Vier Ausgaben einzeln prüfen.
2. Einen Workflow-Re-Run auslösen. Er darf **nichts** wiederholen — der Test
   simuliert das, aber nicht gegen einen echten Runner-Absturz.
3. Abmelden, **nachdem der Dienst nachweislich 20 Minuten geschlafen hat.**
   Das ist der einzige Abmeldeweg. Dann absichtlich an eine erfundene Adresse
   senden und prüfen, dass `bounce_sync` sie am nächsten Tag auf `bounced`
   setzt.
4. Erst dann die Anschrift eintragen — damit schaltet sich das Formular frei.
5. Nach vier Wochen: Zustellquote, Abmelderate, Stichwort-Rauschen und
   Abstand zum Tageslimit im Protokoll ansehen und die Grenzwerte in
   `config/newsletter.yaml` nachziehen. **`vorschau_warnung_ab: 25` ist
   gegriffen, nicht gemessen.**

---

## 5. Die Zahlen dieser Session

**Trockenlauf gegen die echte Ausgabe vom 8. August** (zwei Testabos, ein
Filterabo und ein Stichwortabo):

```
Eintraege zur Auswahl: 142        Segmente: 2 mit Inhalt, 0 leer
Zugestellt: 2                     Abstand zum Tageslimit: 278
Wiederanlauf -> Zugestellt: 0, Uebersprungen: 2
```

**Drei Beispielmails** (`outputs/mail-preview/`): enger Filter 2 Einträge,
ohne Filter 8 (der Deckel), nur Stichwort 4 — alle vier über das Stichwort
hereingeholt und als solche markiert.

**Der Stichwort-Index**: 6908 Wörter aus 810 Meldungen der letzten 30 Tage,
120 KB.

**Neue Tests je Paket**: N1 16 · N2 72 · N3 32 · N4 36 · N5+N6 35 · N7+N8 36.

---

## 6. Fallstricke für die nächste Session

- **Die 24-Stunden-Sperre liegt im Workflow, nicht im Signup-Dienst.** Dessen
  IP-Zähler ist nach jedem Spin-down leer; wer die Sperre dort einbaut, baut
  sie an der einzigen Stelle ein, an der sie sicher nicht wirkt.
- **`git pull --rebase` kann `subscribers.jsonl.age` nicht zusammenführen.**
  Jeder Ciphertext ist bei jedem Schreibvorgang völlig anders, jeder Konflikt
  ein Binärkonflikt, und „ours" wirft die halbe Liste weg. Entschlüsseln → auf
  JSONL-Zeilenebene mischen → neu verschlüsseln.
- **Das Token des Signup-Dienstes zeigt NUR auf `telco-radar-inbox`.** Mit
  `contents: write` auf `telco-radar-mail` ließe sich `send_digest.py`
  überschreiben — genau die Datei, die der Workflow danach **mit dem
  Entschlüsselungsschlüssel** ausführt.
- **Der Zweck geht in die Signatur ein.** Ohne das wäre jede Nonce aus
  `/form-token` ein gültiges Bestätigungstoken, und der Angreifer bräuchte den
  Schlüssel gar nicht.
- **Brevo-Keys verfallen nach 90 Tagen ohne Nutzung**, unabhängig vom
  Ablaufdatum. Nach einer Projektpause ist HTTP 401 die erste Ursache, die zu
  prüfen ist — bevor jemand im Code sucht.
- **300 Mails am Tag ist die Verteilerobergrenze, keine ferne Grenze.** Sie
  wird beim 301. Abonnenten gerissen. Der Wächter zählt geplante **plus heute
  schon versendete**, sonst reißt ein Wiederanlauf sie.
- **Ein Test, der zwei Rechnungen vergleicht, muss beide Seiten wirklich
  ausführen.** 3.2 wäre grün geblieben, hätte der Test die Browser-Rechnung
  nachgebaut statt sie im Browser laufen zu lassen.
