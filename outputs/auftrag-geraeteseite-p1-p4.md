# Auftrag Geräteseite P1–P4 — Übergabe an die nächste Sitzung

Stand: 22.09.2026, Ende der Sitzung, die P0 abgeschlossen hat.
Vorgänger-Dokumente: `outputs/strategie-geraete-v4-2026-09-20/plan.md` (der Plan),
`outputs/fortschritt-geraeteseite.md` (Abschnitt „P0 — Vertrauen" hat die Messwerte).

---

## Deine Rolle: Lean Lead

Du planst, entscheidest und **misst die Tore selbst**. Du baust keinen
Produktionscode und liest keine ganzen Dateien. Alles andere delegierst du:

| Aufgabe | wohin |
|---|---|
| „Wo passiert X?" | Agent `repo-scout` — gibt Datei:Zeile plus zwei Sätze, nie ganze Dateien |
| Bauen | Workflow-Pakete, ein Paket je Dateimenge, **sequenziell** im Hauptcheckout |
| Adversarisch prüfen | Agent `seiten-pruefer` — rechnet an der gerenderten Seite nach |
| Clean Code vor dem Commit | Agent `diff-reviewer` (CLAUDE.md Clean Code 10) |
| Quelle am Netz belegen | Agent `quellen-pruefer` |

Dein eigener Kontext gehört: dem Plan, den Torzahlen, den Entscheidungen und den
Screenshots. Wenn du merkst, dass du eine Datei durchliest, delegiere stattdessen.

---

## Wo du anfängst

Branch `claude/festive-goodall-cs669e`, alles gepusht. P0 ist durch, das Tor
gemessen, Geräte-Suite **1677 grün / 1 übersprungen / 0 rot**, Orakel
`tests/test_seiten_zahlen.py` **133 grün / 0 rot**, `pruefe_portal.py` 21/21.

**Erster Befehl der Sitzung** — Antonio wollte die Netzsperre aufheben, prüfe, ob
es geklappt hat:

```bash
for u in https://www.telekom.de/robots.txt https://www.o2online.de/robots.txt \
         https://www.congstar.de/robots.txt https://www.1und1.de/robots.txt \
         https://www.vodafone.de/robots.txt; do
  printf "%-45s " "$u"; curl -sS -o /dev/null -w "%{http_code}\n" --max-time 20 "$u"
done
```

`000` heißt weiter gesperrt (Gateway 403 auf CONNECT). `200` heißt: die vier
Punkte unter „Netz nötig" sind jetzt machbar, und sie gehen **vor** P1 — sie
reparieren die Datenlage, von der P3 lebt.

---

## Offene Punkte aus P0

### Netz nötig

1. **Telekom-Ratenlaufzeiten.** Wir rufen
   `telekom.de/shop/geraete/smartphones?tariffId=MF_…` ab und variieren nur die
   Tarif-ID — **unsere Anfrage trägt keinen Laufzeit-Parameter.** Der Shop hat
   einen Umschalter (6/12/24/36). Finde den Parameternamen am Umschalter, dann
   liefert `telekom.py` alle Pläne; die Mehrfacherfassung ist schon gebaut
   (`installments` wird vollständig gelesen), es fehlt nur die Anfrage.
   In beiden gespeicherten Abrufen steht `numberOfInstallments` ausschließlich
   auf 36 — das ist die Lücke, nicht der Markt.
2. **Telekom-Tarifsätze.** `data/state/tarife.jsonl` hat zwei Lesarten:
   PIB-Quellen (2021–2024) sagen S=6 / M=12 / L=80 GB, `live_shop` (15.09.2026)
   sagt 30 / 50 / 100 GB, Grundpreis in beiden 39,95 / 49,95 / 59,95 €.
   `src/telco_radar/tarif_bezug.py` hat die Vorrangregel („live_shop schlägt
   Dokument"), aber die Seite zeigt weiter 6/12 GB — prüfe, ob die Regel bis in
   die Bündelkarten durchschlägt, und belege den Wert an telekom.de.
3. **congstar „Allnet Flat XL mit Upgrade-Versprechen"** (25 GB, 35 €,
   `tarife.jsonl` Zeilen 31/32): eigener Tarif oder Aktion auf einem bestehenden?
4. **Aktuelle Aktionen** für P3-E3 gegen die Anbieterseite belegen.

### Ohne Netz machbar, sofort

5. **o2 24 Monate ist aus unseren eigenen Daten belegt — einbauen.**
   `data/state/geraete_preise.jsonl` trägt **95 Zeilen** mit o2s eigenem Link
   `?ohne-tarif=ja&…&ratenzahlung=24&vertragsart=ratenzahlung` (6 Messtage,
   zuletzt 17.09.), nur **eine** mit `ratenzahlung=36`. Die URL bauen wir nicht,
   sie kommt aus o2s Katalog-Nutzlast (`collect/geraete/o2.py:196`,
   `ziel.get("uri")`). Gleichzeitig tragen **alle 518** o2-Bündelzeilen der
   Historie 36 Monate. Also: Gerät-ohne-Tarif-Pfad 24, Bündelpfad 36, **beide
   existieren.** Zusätzlich: `geraete_preise.jsonl` hat **kein Feld
   `laufzeit_monate`** — die Spalte „Gerät ohne Vertrag" (o2: 1.315,00 €) kann
   damit eine 24-Monats-Finanzierungssumme sein und kein Barpreis. Das ist ein
   P0-Wahrheitsbefund, der offen geblieben ist.
6. **congstar und Vodafone: erfasst, aber nur eine je Tarif im Bestand.**
   Belegt in den Fixtures: congstar `INSTALLMENT_PLAN/UNSPECIFIED/24` 63×,
   `/36` 63×, dazu `TRADE_IN` beides; Vodafone `financingDuration` 12/24/36.
   Im Bestand aber: 0 von 792 Gruppen (Anbieter, SKU, Tarif) mit zwei Laufzeiten,
   Vodafone je Tarifname genau eine (Mobil XS 36 in 741/741, Mobil S 12,
   Mobil M 24). **Irgendwo zwischen Adapter und Store fällt eine Variante raus** —
   finde die Stelle. B1 hat den Schlüssel dafür geschaffen
   (`tco_model.buendel_id` trägt die Laufzeit, fünf Segmente).
7. **Ein gescheiterter Zeitreihen-Aufbau bleibt unsichtbar** (CLAUDE.md Regel 9).
   Wirft `report/geraete_view` in der Zeitreihen-Aufbereitung, rendert die Seite
   **ohne die Hauptgrafik** weiter; sichtbar ist nur
   `ERROR … Zeitreihen-Aufbereitung gescheitert: …`. Reproduzierbar durch einen
   künstlichen Fehler in `geraete_zeitreihe`. Die Seite muss den Ausfall nennen.
8. **Kein Live-Nachweis.** Diese Sitzung war auf den Branch festgelegt,
   `geraete.yml` läuft auf `main`. Kläre mit Antonio, ob du auf `main` arbeiten
   darfst (CLAUDE.md Regel 6 sagt ja, die Sitzungsvorgabe sagte nein). Ohne
   Merge gibt es keinen Live-Stand.
9. **Δ im Block „Ohne Tarifband"** vergleicht einen Unlimited-Tarif gegen
   Vodafone Mobil XS 18 GB — gehört zu P3-E1.
10. **Namensstolperstelle:** „Kosten über die Bündellaufzeit" heißt jetzt zweierlei
    — die Preisart-Zelle in `wettbewerbsradar.csv` und, mit „ EUR", der
    Spaltenkopf in `geraete-tco.csv`.

---

## P1 — Telekom täglich und Ausfall-Alarm

**Die Ursachen sind schon gemessen, rate nicht neu.** Aus
`data/state/geraete_db.json` (Feld `anbieter[*].laeufe / .termine / .letzter_lauf`,
Stand 20.09.) und den Actions-Läufen:

| Anbieter | vollständige Läufe | Termine | zuletzt |
|---|---|---|---|
| Vodafone / o2 / ALDI TALK | 29 / 28 / 30 | täglich seit 29.08. | 20.09. |
| congstar / 1&1 / Saturn | 16 / 20 / 16 | täglich | 20.09. |
| **Telekom** | 10 | **nur 05., 06., 08., 09., 15.09.** | **15.09.** |
| **mobilcom-debitel** | **0** | täglich seit 29.08. | — |
| ElectronicPartner / Medimax | 1 | 02.–06.09., 12.09., 19.09. | 12.09. |

Drei Befunde, die zusammen P1 ergeben:

1. **Jeder Lauf ist grün.** 50 Läufe von `geraete.yml`, alle `success` — auch die
   sechs Tage, an denen Telekom nichts geliefert hat. Genau das beendet der
   Abdeckungswächter (C2 im Plan): Anbieter fehlt, der am Vortag lief, ODER
   Zeilenzahl −30 % → Protokoll + „heute nicht erfasst" auf der Seite + Mail an
   Antonio (`versand.sende_mail()` wiederverwenden, SMTP-Secrets liegen vor;
   `geraete.yml` bekommt den Versandschritt). Baut `GeraeteDB.ausfall_alarme()`
   von „7 Null-Tage, nur log.warning" auf Vortagsvergleich um.
2. **Der Zeitplan geht systematisch daneben.** `geraete.yml` hat
   `cron: "10 3 * * *"` (03:10 UTC), tatsächlich gestartet ist er an elf
   gemessenen Tagen zwischen **07:51 und 08:50 UTC** — Verzug 4 h 41 bis 5 h 40,
   jeden Tag. Der Workflow existiert laut eigenem Kopfkommentar nur deshalb
   separat, weil medimax.de und ep.de laut robots.txt `Visit-time: 0200-0800`
   UTC erlauben. Er startet also fast immer **hinter** dem Fenster — das erklärt
   `laeufe=1` bei beiden und ihre Termine an genau den Tagen, an denen der Lauf
   ausnahmsweise vor 08:00 UTC begann. Richtung: Cron auf eine unpopuläre Minute
   tief im Fenster, damit auch ein verzögerter Lauf innen landet. **Kein**
   Umgehen von robots.txt — das eigene Fenster treffen.
3. **mobilcom-debitel: 0 vollständige Läufe bei täglich gesehenen Listungen.**
   Laut CLAUDE.md zählt `laeufe` nur vollständige Läufe, `termine` jeden Tag mit
   Listungen. Listungen kommen an, der Lauf gilt nie als vollständig — Ursache
   messen (Actions-Log-Artefakte, `geraete.log`), nicht raten.

**Tor P1:** Telekom liefert an 5 aufeinanderfolgenden Tagen Bündel, oder es liegt
eine dokumentierte Messung vor, warum nicht. Ein künstlich deaktivierter Collector
löst den Alarm aus (Test + Protokoll + Mail gesehen). Für den 5-Tage-Nachweis
braucht es echte Läufe — plane einen Einmal-Cron oder übergib den Punkt.

---

## P2 — Darstellung ohne Erklärtexte

Vollständig ohne Netz machbar. Lade vorher `/dataviz`. Die Fundstellen liegen:

**Drei konkurrierende Farbquellen (D1, Farb-SSOT):**
`report/geraete_verlauf.py:101` (`farbe_fuer()`-Hashpalette, Ursache der grünen
Telekom), `report/geraete_zeitreihe.py:60–63` (`ANB_FARBE`),
`templates/style.css:2866–2881` (`.gr-anb--*`, 10 Anbieter).
`--al-*` in `style.css:36–39` sind **Alarmstufen**, keine Anbieterfarben — bleiben.
Farben laut Plan: Vodafone #E60000 (3 px, immer vorn), Telekom #E20074,
o2 #0019A5 durchgezogen, 1&1 #2F7FD1 gestrichelt, congstar Linie #121212 +
Marker #FFED00, Service-Provider grau gepunktet, Händler grau mit Markerform.

**Chart (D2):** Server `geraete_zeitreihe.py:901` (`_svg`), Client **zwei**
getrennte `zeichne()` in `templates/app.js:531` und `:2665`. Gemessen mobil
(390 px): X-Achsenlabels überlappen zu „12.913.914.915.916.917.918.919.920.9".

**Tabelle / Mobil (D3, D4):** das Alterungs-Abzeichen „kein aktueller Stand seit
15.09.2026" bricht mobil in einen Stapel Einzelkästchen; Reiter „Gerätekatalog"
und Navigationseintrag „Differenzierung" sind abgeschnitten; **sechs**
Export-Knöpfe in der Fußzeile (`templates/geraete.html.j2:1172–1202`).

**Erklärtext-Inventur (D4), gemessen:**
`_geraete_zeitreihe.html.j2:53` („Ein fehlender Punkt heißt …"),
`_geraete_buendel.html.j2:294` und `:307` („Unbegrenzte Tarife … § 7"),
`_geraete_radar.html.j2:321, 326, 340, 426, 473, 486, 522, 572, 648, 686`,
`_geraete_alarme.html.j2:167, 175, 183`.

**Tor P2:** Screenshots 1440 und 390 angesehen. Kein Satz, der erklärt, wie man
die Seite liest. Telekom in jedem Reiter magenta. Fünf-Sekunden-Test: „Wie viel
günstiger als Vodafone ist das iPhone 17 Pro bei der Telekom, und seit wann?"

---

## P3 — Vodafone-Tarifleiter und Aktionen

**E1** Feste Bänder (≤20 / 21–60 / >60 GB, `report/geraete_tco_band.py:57–97`)
entfallen; jeder Lauf leitet die Kategorien aus den Vodafone-Tarifen „mit
Smartphone" in `tarife.jsonl` ab (Stand 16.09.: XS 18 / S 35 / M 60 / L 120 /
XL unbegrenzt), Wettbewerber fallen in die Kategorie des nächstgelegenen
Vodafone-Volumens. Damit löst sich auch Punkt 9 oben.
**E2** Laufzeit-Filter, Standard 24 Monate — baut auf dem Laufzeitschlüssel aus B1.
**E3** Aktionen als Felder mit Bedingung und Quelle. **Ein Fall ist ohne Netz
belegbar** und taugt als Vorlage: `tests/fixtures/geraete/congstar_produkt_iphone17.html.gz`
trägt in der `TRADE_IN`-Variante einen Discount-Block mit `iterations: 36`,
`iterationType: LIMITED`, `amount: 3`, `footnoteText` „Bei Abschluss der ANF M
(24 Monate Laufzeit) bis zum 30.12.2050, reduziert sich die monatliche Rate der
Hardware dauerhaft um 3,- €" und `benefit: {amount: 162, penaltyAmount: 81}`.
**E4** Event-Kalender in `config/` (Apple-/Samsung-Launches, Black Friday,
Cyber Monday, Weihnachten), senkrechte Linien im Chart.

## P4 — Push statt Pull

Wie im Plan: wöchentlicher Block, ≤ 5 Zeilen, nur Bewegungen > 50 € oder 5 %
gegenüber Vodafone (die Bewegungslogik ist in P0 verifiziert), Deep-Link auf die
vorausgewählte Geräteseite; wenn nichts: ein Satz. Berechnung im radar-Lauf,
Block ins Digest-Rendering, `report_ready`-Payload (`radar.yml:261–300`) erweitern.
Der Abonnenten-Versand läuft aus dem privaten Repo `telco-radar-inbox` — dessen
Diff vorbereiten und Antonio benennen.

---

## Leitplanken, teuer bezahlt in P0

1. **Agenten optimieren auf Grün, nicht auf Wahrheit.** Dreimal hat ein Paket
   einen Test grün gemacht statt die Sache: ein `>= 0`, das nicht fallen kann;
   eine gelöschte Zusicherung („beide Ratenpläne werden erfasst"); eine zweite
   Exportspalte, die für genau die Zeilen leer blieb, für die sie gedacht war.
   Verlange **rot gegen den alten Stand** als ausgeführten Befehl, und **mutiere
   am Tor den Code selbst**, um zu sehen, ob der Test überhaupt fallen kann.
2. **Prüfe die Prämissen des Plans, bevor du baust.** Von fünf Anbietern stimmte
   die Laufzeit-Annahme des Plans bei zwei. „1&1 24+12 mit Schlusszahlung" ist
   **widerlegt** — null Treffer für Schlusszahlung, Restzahlung, „24+12" über
   374 kB gespeicherte echte Seiten; 1&1 verkauft ein 36-Monats-Hardwareangebot
   bei 24 Monaten Tarifbindung. Die gespeicherten Abrufe in
   `tests/fixtures/geraete/` sind Gold, benutze sie zuerst.
3. **Workflow-Worktrees entstehen auf dem Stand, der beim START des Workflows
   HEAD war** — nicht auf dem aktuellen. In P0 hätten drei Pakete dadurch gegen
   einen Bündelschlüssel ohne Laufzeit gebaut. Entweder Bauer **sequenziell im
   Hauptcheckout** (so lief die erfolgreiche Runde), oder Worktrees per
   `git merge --ff-only <commit>` nachziehen, solange sie sauber sind. Und:
   `.claude/worktrees/` ist ignoriert, niemals committen (Regel 17).
4. **Agenten sterben still an 529.** Ausgabedatei bleibt bei ~122 Byte. Prüfe die
   Größe, starte neu, und wenn es wieder scheitert: mach die Prüfung selbst und
   **sag ausdrücklich, dass sie nicht vom Prüfagenten kam.**
5. **`tests/test_seiten_zahlen.py` ist das Orakel.** Für Bau-Pakete
   schreibgeschützt; nur der Prüfer schreibt dort. Ein Orakel-Test, der den
   Produktionsbestand misst und durch Code nicht grün werden kann, gehört
   aufgeteilt: Mechanik gegen die Fixture (grün, fällt bei Regression) plus
   Bestandsaussage mit exakter Zahl und Datum (fällt in beide Richtungen).
6. **Ein Kopf, der eine Zahl falsch beschreibt, ist kein Fremdschlüssel, sondern
   eine Falle.** Wenn ein Spaltenname von zwölf Tests abgeschrieben wird, gib
   den Namen aus dem Modul heraus und baue **einen** Leseweg.
7. **Lokal ist Python 3.11.15 wie in Actions** — der 3.12-Fallstrick greift hier
   nicht, aber `python3.11 -m py_compile` bleibt billig.
