# Übergabe Geräteseite: P2 abschließen, dann P3 und P4

Stand: 24.09.2026, Ende der Sitzung, die P0 live gebracht und P1 abgeschlossen hat.
Dieses Dokument liegt **auf main**. Vorgänger: `outputs/auftrag-geraeteseite-p1-p4.md`
(Zielbild P1–P4, gemessene Fundstellen), Plan `outputs/strategie-geraete-v4-2026-09-20/plan.md`,
Verlauf `outputs/fortschritt-geraeteseite.md`.

---

## Deine Rolle: Lean Lead

Du planst, entscheidest und **misst die Tore selbst** — an Screenshots, die du dir
ansiehst, und am ausgelieferten Live-HTML. Du baust keinen Produktionscode und liest
keine ganzen Dateien. Alles andere delegierst du:

| Aufgabe | wohin |
|---|---|
| „Wo passiert X?" | `repo-scout` — Datei:Zeile plus zwei Sätze |
| Bauen | `general-purpose` mit `model: "sonnet"`, ein Paket je Dateimenge |
| Adversarisch nachrechnen an der Seite | `seiten-pruefer` (einziger Schreiber von `tests/test_seiten_zahlen.py`) |
| Vor jedem Commit | `diff-reviewer` mit `model: "sonnet"` — S1/S2 blockieren |
| Logs von Actions-Läufen auswerten | `general-purpose`, `model: "sonnet"`, mit den GitHub-MCP-Tools |

Dein Kontext gehört dem Plan, den Torzahlen, den Entscheidungen und den Screenshots.
Delegiere Logauswertung (1.300 Zeilen) und Dateilektüre immer.

---

## Wo du anfängst

**main** (grün in CI, live deployt) trägt P0 und P1 vollständig sowie P2-D1 (Farben)
und P2-D4a (Erklärtexte). **Der Branch `claude/bold-sagan-5craam`** trägt darüber
einen einzigen WIP-Commit mit dem **ungeprüften** Rest von P2 (D2 Chart/Mobil, D3
Bündeltabelle, Abschlussrunde). Er ist bewusst nicht auf main: ein Review hat zwei
S1 gefunden, deren Behebung in diesem Commit steckt, aber noch nicht geprüft ist.

**Erster Schritt:**
```bash
git fetch origin && git log --oneline origin/main..origin/claude/bold-sagan-5craam
```
Dann den WIP-Commit durch `diff-reviewer` (sonnet) schicken, volle Suite, eigene
Screenshots (siehe P2-Tor unten), und erst dann nach main übernehmen
(`git merge --ff-only` bzw. cherry-pick; kein Force-Push auf main).

**Umgebung ist nach jedem Container-Neustart leer:**
```bash
python3.11 -m pip install --quiet -r requirements.txt   # sonst fehlt bs4 & Co.
export PYTHONPATH=src
find . -name __pycache__ -type d -not -path "./.git/*" -exec rm -rf {} +
python3.11 -m pytest -q          # ~12–15 min, zuletzt 3717+ grün
```
`/root/.local/bin/pytest` hat die Projektabhängigkeiten NICHT — immer `python3.11 -m pytest`.

---

## Gemessener Stand

| | Stand | Beleg |
|---|---|---|
| P0 Vertrauen | **live** | Live-HTML trägt das Tagesdatum; `MagentaMobil S · 30 GB` statt 6 GB; 583 Bündel-IDs mit Laufzeitsegment, 80 Gruppen mit zwei Laufzeiten (alle congstar) |
| P1 Betrieb | **live** | Cron 02:17 UTC, Visit-time je Abruf, Abdeckungswächter (Protokoll + Quellenseite), mobilcom-debitel am 23.09. erstmals vollständig, `ALARM_EROSION` |
| P1 in Produktion | gemessen | Lauf 53 (24.09.) meldete wörtlich „mobilcom-debitel: heute unvollständig erfasst – 92 Zeilen, am 23.09.2026 waren es 133 (31 % weniger)"; Quellenseite live „heute nicht gelesen" 4× |
| congstar-Budget | auf main | `sammelrang` trennt Crawl- von Anzeige-Reihenfolge; congstar war seit P1 verhungert (Medimax/EP crawlen jetzt in ihrem Fenster, ~6 min aus demselben Budget) |
| P2-D1 Farben | auf main | eine Quelle `report/anbieter_farben.py`; Telekom computed `rgb(226, 0, 116)` |
| P2-D4a Erklärtexte | auf main | 11 Lesehilfen → `geraete-quellen.html#methodik`; `pruefe_portal.py` 21/21 |
| P2-D2/D3/Abschluss | **WIP-Branch** | siehe unten |

**Telekom ist nicht reparierbar.** telekom.de antwortet uns **und GitHub Actions** mit
AWS-WAF-Challenge (HTTP 202, `x-amzn-waf-action: challenge`). Einen Laufzeit-Parameter
gibt es auf dem ausgelieferten Weg nicht (19 von 19 Einträgen 36 Monate, Beleg
`outputs/befund-telekom-laufzeit-2026-09-22.md`). Regel 7: nicht umgehen. Die Seite
zeigt ehrlich „kein aktueller Stand seit 15.09.2026". vodafone.de: 403 (Incapsula);
unsere Vodafone-Daten kommen über die API und laufen.

---

## P2 abschließen

Im WIP-Commit steckt (vom Bauer gemeldet, von dir zu prüfen):
- **D2 Chart:** Stufenlinie, Messlücken > `LUECKE_TAGE_SCHWELLE` (10 Tage) gepunktet,
  y-Achse 4–5 runde Werte, Achsenbruch bei < 10 % Spanne, X-Label ohne Überlapp
  (vorher mobil „12.913.914.915…"), Endlabels statt Legende, Markerformen.
- **D4b Mobil:** Alterungs-Abzeichen eine Box, aktiver Nav-Eintrag scrollt ins Bild,
  sechs Export-Knöpfe → ein `<details>` „Export ▾".
- **D3 Tabelle:** zwei congstar-Zahlweisen zugeklappt unterscheidbar („36 Raten ·
  Restschuld 366,00 €" / „24 Raten"), Zerlegungsbalken mit schraffierter Restschuld,
  Summe = Leitzahl; `.gr-bnd` trug vorher nie seine Anbieterfarbe.
- **Abschlussrunde, auf Sitzungsende abgebrochen** (sauber, kein Zwischenzustand):
  - **erledigt B:** jeder Anbieter bekommt ein Endlabel, auch Telekom mit nur einem
    Messpunkt (vorher auf dem Desktop unbeschriftet, weil die Legende ab 701 px weg ist).
  - **erledigt D:** bei zwei Zahlweisen zum selben Betrag gewinnt fest die kürzere, die
    andere bleibt als `weitere_laufzeiten` erhalten; der Rechenweg nennt „Zum selben
    Betrag auch über N Monate erhältlich" mit Restschuld (vorher verschwanden 366,00 €).
  - **erledigt, Teil von C3:** doppelte Start-Wertlabels links im Chart entfernt.
  - **OFFEN A (S1 aus dem Review, blockiert den Merge):** der Client-Chart im Reiter
    „Preisverlauf" (`app.js` `zeichne(g)`) zeichnet noch schräge durchgezogene Linien
    über Messlücken, der Server-Chart darüber Stufen und Punktierung — zwei Grafiken
    derselben Seite widersprechen sich. Schwelle `LUECKE_TAGE_SCHWELLE` aus Python an
    den Client geben (data-Attribut), nicht als zweite Zahl in JS; Browser-Test hält
    beide zusammen.
  - **OFFEN C1:** unter jeder Bündelzeile steht fett „congstar 496,80 € unter Vodafone"
    (`.gr-bnd-subjekt`), doppelt zur Δ-Spalte „−496,80 € · −25,4 %" und zur großen
    Antwortzahl oben. Entfernen; die „≈"-Regel bleibt an der Δ-Spalte getestet.
  - **OFFEN C4:** mobil (390 px) läuft das Endlabel „UNSER ANGEBOT" rechts aus dem
    Chart. Test: jedes Endlabel-Rechteck liegt im SVG-Rechteck.
  - **OFFEN C5:** mobil ist der Reiter „GERÄTEKATALOG" abgeschnitten („GERÄTEKATAL").
  - **OFFEN E:** Grenzfalltest `LUECKE_TAGE_SCHWELLE` bei 10 und 11 Tagen.
  - **NICHT UMSETZBAR C2** („Kosten über 24 Monate" in den Spaltenkopf): das Orakel
    verlangt es anders — `test_pruefer_kein_spaltenkopf_behauptet_24_ueber_einer_36_monats_zahl`
    und `test_pruefer_jede_leitzahl_der_seite_gegen_eine_eigene_rechnung`
    (`tests/test_seiten_zahlen.py` ~4670–4802): die Spalte mischt 24- und 36-Monats-
    Zeilen, also nennt der Kopf keine Monatszahl und jede Zeile behält ihr Etikett.
    Das ist richtig so; nicht erneut versuchen.
  - Gemessen im WIP-Stand: gezielte Tests 214 grün inkl. Orakel. **Volle Suite,
    `pruefe_portal.py` und Screenshots liefen für den letzten Schritt NICHT.**

**Tor P2 (du misst selbst):** `scripts/schiess_screenshot.py --site <tmp-render>
--seite geraete.html` plus Reiter „Preisverlauf", 1440 und 390 px, **ansehen**.
Kein Satz, der erklärt, wie man die Seite liest. Telekom in jedem Reiter magenta und
beschriftet. Nichts abgeschnitten. Fünf-Sekunden-Test: „Wie viel günstiger als
Vodafone ist das iPhone 17 Pro bei der Telekom, und seit wann?" — ehrliche Antwort
heute: ~29 € (1.927 € gegen 1.956 €), Stand 15.09., danach keine Daten.

---

## P3 — Vodafone-Tarifleiter und Aktionen

Ungebaut. Zielbild und Fundstellen im Auftragsdokument, Abschnitt P3:
- **E1** feste Bänder (≤20/21–60/>60 GB, `report/geraete_tco_band.py`) → Kategorien
  aus den Vodafone-Tarifen „mit Smartphone" (Stand 16.09.: XS 18 / S 35 / M 60 /
  L 120 / XL unbegrenzt); löst Punkt 9 (Δ im Block „Ohne Tarifband").
- **E2** Laufzeit-Filter, Standard 24 Monate (der Schlüssel existiert seit P0-B1).
- **E3** Aktionen als Felder mit Bedingung und Quelle. Vorlage ohne Netz:
  `tests/fixtures/geraete/congstar_produkt_iphone17.html.gz`, `TRADE_IN`-Discount
  (`amount: 3`, 36 Iterationen, `benefit {amount: 162, penaltyAmount: 81}`).
  Netz zu o2online.de, congstar.de, 1und1.de ist offen (200).
- **E4** Event-Kalender in `config/`, senkrechte Linien im Chart.
- **congstar-Tarifleiter ist veraltet:** `tarife.jsonl` Zeilen 31/32 („Allnet Flat XL
  mit Upgrade-Versprechen", 25 GB, 35 €, aus PIB 546/550) gibt es nicht; heute
  XS/S/M/L = 15/50/125/200 GB. Preise lädt congstar per JS nach — nicht belegt.

**Tor P3:** für drei Geräte je Vodafone-Kategorie das Gegenangebot von Telekom, o2,
1&1, congstar sichtbar, mit Quelle; mindestens eine Aktion gegen die Anbieterseite belegt.

## P4 — Push statt Pull

Wie im Auftragsdokument: wöchentlicher Block, ≤ 5 Zeilen, nur Bewegungen > 50 € oder
5 % gegenüber Vodafone, Deep-Link; Versand über das private Repo `telco-radar-inbox`
(Diff vorbereiten, Antonio benennen).

## Weitere offene Punkte

- **Punkt 4** (Aktionen belegen) geht in E3 auf. **Punkt 5**: `geraete_preise.jsonl`
  hat kein `laufzeit_monate`; o2 liefert eine 24-Monats-Finanzierung (95 Zeilen mit
  `ratenzahlung=24`), die Spalte „Gerät ohne Vertrag" (o2 1.315,00 €) kann eine
  Finanzierungssumme statt eines Barpreises sein. **Punkt 7**: gescheiterter
  Zeitreihen-Aufbau bleibt unsichtbar (Regel 9). **Punkt 10**: „Kosten über die
  Bündellaufzeit" heißt zweierlei (wettbewerbsradar.csv vs. geraete-tco.csv).
- **EP/Medimax nie vollständig:** Deckel `max_produkte: 20` (`config/geraete_quellen.yaml`
  ~290/317) liegt unter 45/43 Sitemap-Adressen. Vorbestehend.
- **Laufbudget-Puffer:** `--frist` 1500 → 1800 und `timeout-minutes` 40 → 60 in
  `.github/workflows/geraete.yml` — das Stagen der Workflow-Datei hat das
  Berechtigungssystem blockiert. congstar ist ohne das repariert. Ein Regel-12-Test
  (Frist + 60 + 480 + 300 s ≤ Timeout − 600 s) wurde dafür geschrieben und wieder
  herausgenommen, weil er mit dem heutigen Workflow fällt: rechnerisch 60 s Abstand,
  real ~7 min. Neu schreiben, sobald Antonio die Workflow-Änderung freigibt.
- **Mail-Secrets** (`SMTP_HOST` u. a.) fehlen im Repo. Antonio: „interessiert mich
  erstmal nicht". Fehlende Secrets sind eine gelbe Warnung, kein roter Lauf.
- **Cron-Verzug:** GitHub startet den 02:17-Lauf pauschal ~5 h 20 später (07:35–07:45),
  nicht wegen der vollen Stunde. Der Start liegt jetzt knapp im Fenster (bis 08:00).

---

## Leitplanken, in dieser Sitzung teuer bezahlt

1. **Erst abgleichen, dann messen, dann pushen.** Suite gemessen, danach auf einen
   Bot-Commit rebased, gepusht → main war rot. Reihenfolge: `git fetch`, Abgleich,
   Cache leeren, messen, pushen.
2. **Bot-Commits lösen keine CI aus.** Neue Produktionsdaten können main still rot
   machen: Tests, die den Bestand verankern (Orakel, `test_geraete_lifecycle`), fallen,
   sobald ein Fix wirkt. Nach jedem Bot-Lauf mit neuen Daten die Suite lokal fahren.
3. **`__pycache__` vor jeder Messung leeren.** Veraltete `.pyc` aus einer
   Agenten-Repokopie zeigten grüne Tests rot und machten eine Mutationsprobe wertlos.
   Agenten dürfen keine Repokopie im Scratchpad anlegen.
4. **Agenten niemals `git checkout/restore/stash/reset/apply` im Repo erlauben.** Ein
   Prüfagent hat mit `git checkout --` ungesicherte Arbeit in drei Dateien vernichtet.
   Vor jedem Review-Agenten ungesicherte Arbeit außerhalb sichern
   (`git diff > …/sicherung.patch` plus untracked als tar). Rot-Beweise über
   `git show HEAD:<pfad>` in eine Kopie, Mutationen über `cp` hin und zurück.
5. **Wochenlimit des großen Modells.** Ein Bau-Agent starb mittendrin an HTTP 429.
   Alle Agenten mit `model: "sonnet"` starten; das trägt die Arbeit gut.
6. **Parallel nur mit strikt getrennten Dateien.** Geteilte Dateien (`style.css`) nur
   als append-only-Block mit Marker. Sonst sequenziell.
7. **Screenshots finden, was Tests nicht finden.** Doppelte Differenz je Zeile,
   abgeschnittenes Endlabel, abgeschnittener Reiter — alles bei grüner Suite. Der Lead
   sieht sich die PNGs selbst an (Read-Tool zeigt Bilder).
8. **Schlüsse sind keine Messungen.** „Die SMTP-Secrets existieren, weil radar.yml sie
   benutzt" war falsch. Nur behaupten, was gemessen ist, und das auch so sagen.
9. **Prämissen prüfen, bevor gebaut wird.** Drei Auftragspunkte lösten sich beim
   Nachmessen auf (Telekom-Parameter existiert nicht; Punkt 2 und 6 waren nur nie
   gerendert). Ein Bau-Paket dafür hätte intakte Wege umgebaut.
10. **Reviews lohnen sich jede Runde.** Sie fanden u. a. einen Wächter, der nach 30 Tagen
    verstummt, einen Fix, der Erosion unsichtbarer machte als der Fehler davor, und eine
    Hauptzahl, die unter der Wesentlichkeitsschwelle Führerschaft behauptete.
11. **Antonio will keine Rückfragen**, außer bei echten Berechtigungsgrenzen. Er will die
    Seite fertig sehen; Betriebsdetails (Mails) sind nachrangig.
