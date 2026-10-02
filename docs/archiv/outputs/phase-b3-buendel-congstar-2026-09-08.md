# B-3 — Bündelerhebung congstar: Gerät × Tarif (08.09.2026, Runde 2)

Auftragsgrundlage: `BRIEF_B3_BUENDEL_CONGSTAR.md` (Original) und
`BRIEF_B3_BUENDEL_CONGSTAR_R2.md` (Restauftrag nach Session-Abbruch).
Runde 1 hatte bis `41663ca` committet (Adapter `e9bb117` mit 20 neuen
Tests in `test_geraete_buendel_congstar.py`, 72 Bündelsätze `41663ca`
mit Beleg 58/58); der Kill traf mitten in der
Radar-Phase mit uncommittetem Diff. Diese Runde bewertet diesen Diff,
macht die letzten 20 % fertig und schließt ab.

## Ergebnis in einem Satz

**72 congstar-Bündelsätze** (9 Modelle × 8 PlanVarianten, vorher 0) im
Bestand neben Telekom 45 · Vodafone 338 · o2 63 (gesamt 518); der
Wettbewerbs-Radar führt congstar als **36 Vergleichspaare** über 9 Modelle
(alle günstiger als Vodafone, −3,1 % bis −49,8 %) — als Zweitmarke MIT
Karte und OHNE Platzhalter; Vollsuite **2 failed / 2854 passed /
14 skipped**, nur die zwei bekannten Promo-Screenshot-Roten.

## Der uncommittete Diff aus Runde 1 — bewertet (Auftrag 1)

**Urteil: kohärent und dem Original-Brief dienlich — behalten und
vollendet, nichts zurückgesetzt.** Der Diff erweitert
`report/wettbewerbsradar.py` um den Zweitmarken-Kreis:

| Baustein | Regel |
|---|---|
| `ZWEITMARKEN_MIT_BUENDEL = ("congstar",)` | Zweitmarken mit eigener Bündelerhebung — der Kreis, der Paare bilden KANN |
| `ALLE_WETTBEWERBER = NETZ_WETTBEWERBER + ZWEITMARKEN_MIT_BUENDEL` | Paarbildung und `_guenstigste_echte_karte_je_anbieter` rechnen über diesen Kreis |
| Zeile nur MIT Karte | congstar erscheint in einer Gruppe nur, wenn das Modell eine congstar-Karte hat (`hat_karte`); ohne Karte bleibt die Zeile GANZ aus — 55 `kein_buendel`-Platzhalter wären die Wand aus Lücken, gegen die die Regel gebaut wurde. Die drei Netzbetreiber stehen weiterhin IMMER da (auch `kein_buendel`) |

Damit ist Abnahmekriterium 3 des Original-Briefs erfüllt („Radar-Wirkung
sichtbar"). Drei Dinge haben in dieser Runde noch gefehlt, alle behoben:

1. **Der konstruierte Test fehlte.** Die geänderten Echtdaten-Tests prüfen
   die Regel am Bestand, aber kein konstruierte Fixture löst den Fall
   aus (Hausregel: „ein Fixture, das den Fall nicht auslöst, beweist
   nichts"). Neu: `test_zweitmarke_steht_nur_mit_karte_da` mit eigenem
   Bestand (`_zweitmarken_bestand`) über alle drei Lagen — Paar im
   gemeinsamen Band (M1), keine Zeile ohne Karte (M2), Zeile mit Zahl
   ohne VF-Basis (M4) — inklusive Gegenproben, dass die Fixture beide
   Fälle wirklich auslöst. **Gegen HEAD nachgewiesen durchfallend**
   (alte Modulfassung: congstar-Zeile fehlt → `len([]) == 0`).
2. **Ein Lookup ging ins Leere.** Der Echtdaten-Test las
   `g.get("karten")` — Radar-Gruppen tragen kein `karten`-Feld, also lief
   die congstar-Karten-Prüfung NIE (CLAUDE.md §6: „ein Test, dessen Lookup
   ins Leere geht, ist grün und prüft nichts"). Behoben über
   `echt["modelle"]` mit Zuordnungs-Gegenprobe (`assert all(zugeordnet)`).
3. **E1-Kennzeichnung fehlte auf der Radar-Seite.** congstar-Zeilen
   standen unter der Überschrift „Netzbetreiber – TCO über 24 Monate",
   während der Erklärsatz nur Telekom, 1&1 und o2 nannte — ein Manager
   hätte congstar als vierten Netzbetreiber gelesen. Der Erklärsatz
   nennt jetzt congstar ausdrücklich als **Zweitmarke im Telekom-Netz,
   kein eigener Netzbetreiber**, und sagt, warum die Zeile nur bei
   Geräten mit congstar-Bündel steht (R2-Hausregel: congstar =
   Telekom-Netz-Proxy, Kennzeichnung). Runde 1 hatte die Kennzeichnung
   nur in `geraete-quellen.html` angelegt; jetzt steht sie auch dort,
   wo die Zahlen stehen.

**Render-Kohärenz bestätigt:** `render_site(…, load_config(root))`
reproduzierte den Runde-1-Stand von `wettbewerbsradar.html`,
`geraete.html` und `geraete-quellen.html` **byte-identisch** (vor der
Vorlagenänderung gemessen) — der Kill hatte kein halbfertiges Artefakt
hinterlassen. Danach nur der E1-Satz hinzugekommen, sonst keinerlei
Byte-Änderung. `site/data/keyword-index.json` wurde vom Render NICHT
angefasst — kein Reset nötig.

## Recherchebefund — welche Quelle, und warum

Aus Runde 1 (Modulkopf von `src/telco_radar/collect/geraete/congstar.py`,
Abschnitt „DER BUENDELKATALOG", live bestätigt im Lauf mit Beleg):

1. **Nicht die Geräteseite.** Ihre Zahlweisen tragen nur die Hardware
   (`oneTime`/`recurring` als `DevicePrice`-Objekte); der Kauffluss mit
   Tarifwahl ist ein clientseitiger Konfigurator — für einen reinen
   HTTP-GET unlesbar. Und nicht das ld+json: dessen `price` ist der
   Einmalpreis im Bündel ohne Speichergröße (Befund vom 30.08., bleibt
   richtig).
2. **Die vier Tarifseiten sind der Bündelkatalog.**
   `/handytarife/allnet-flat-tarife/{xs,s,m,l}/` tragen die Kombinatorik
   Geraet × Tarif **serverseitig** im selben Next.js-Flight-Payload
   unter `prefetchedPlan.variants[]` — je PlanVariant Tarifpreis,
   Bereitstellungspreis, Pflichtblatt-Link und je Gerät die
   Ratenzahlweisen je Speicher/Farbe. Die vier Adressen nennt congstar
   selbst in `sitemap pages.xml`; keine geraten.
3. **Eine Postpaid-Seite `allnet-flat-xl` existiert nicht** (in pages.xml
   gemessen) — XL läuft nur als Pflichtblatt. Messgrenze, keine Lücke.
4. **Im Bündel gilt `discounted`, im Barpreis `listed`** — der
   Hardware-Nachlass entsteht laut Fußnote „Bei Abschluss der ANF M
   (24 Monate Laufzeit) … reduziert sich die monatliche Rate dauerhaft",
   also genau mit dem Abschluss, den ein Bündel IST. Umgekehrt beim
   Barpreis (dort wäre `discounted` die Falle, Abstand bis 252 €).
5. **Die Nachrechnung ist Bedingung:**
   `oneTime.discounted + 36 × recurring.discounted == total` — geht sie
   nicht auf, wird der Satz verworfen (sie gilt an allen Varianten der
   36-Monats-Zahlweise exakt).
6. **Zwei Zahlweisen, ein Satz:** je Variante stehen 24- und 36-Monats-
   Finanzierung (gleiches `total`) neben einer TRADE_IN-Weise. Erhoben
   ist die 36er — kongruent zu o2/Telekom (36 Raten bei 24 Monaten
   Tarifbindung), A5.5 setzt die längere als führend; die 24er rechnet
   sich aus demselben `total`.
7. **Die PIB-Nummern-Brücke** (`ergaenze_pib_slug`): congstar nummeriert
   PlanVariant und Pflichtblatt mit derselben Zahl (540 ↔
   `Produktinformationsblatt_540.pdf`). Ohne sie fielen vier der acht
   PlanVarianten sang- und klanglos unter „ohne auflösbaren Tarif" —
   die Seite nennt den S-Tarif „Allnet Flat S", das Blatt „Allnet Flat S
   mit GB+", und der SIM-only-Betrag steht für S und S Flex im Blatt
   (Namensbrücke mehrdeutig). **72 von 72 Sätzen mit Güte `hoch`**, null
   unauflösbar.

## Der Lauf (Runde 1, Beleg mitgeprüft)

`scripts/lokallauf_congstar.py` (B-2-Muster, T2-Haken): 113 s,
5 Einstiege → 52 Produktseiten + 4 Tarifseiten. Beleg
`outputs/beleg-congstar-geraete-2026-09-08.json`, in dieser Runde
nachgelesen: **58 Requests, `alle_ehrlich: true`**, jeder UA exakt
`TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)` (inklusive
robots.txt — provider-bezogene Wächter-Sicht aus B-2), jeder Status 200,
jeder `transport: http-get`, jeder `browser: false`.

Zwei Befunde aus Runde 1, im Commit festgehalten und hier nur referenziert:
der generische Ernte-Weg rief die Bündellesart anfangs auf ALLEN
Geräteseiten auf (die tragen kein `prefetchedPlan` → Wurf) — behoben durch
die Adapter-Flagge `buendel_auf_produktseite: false` für congstar,
Vodafone hält `True`; und eine Farbkollision (Galaxy S25 128 GB „navy"
hinter „blau") — bekannte Farb-Arbeitsliste, keine B-3-Altlast.

## Vorher / Nachher

| | Vorher (41663ca^, B-2-Stand) | Nachher |
|---|---|---|
| Bündel gesamt in `geraete_tco.json` | 446 | **518** |
| davon congstar | **0** | **72** (9 Modelle × 8 PlanVarianten; XS/S/M/L je Flex) |
| Auflösung `tarif_id` | — | 72/72 Güte `hoch` (PIB-Nummern-Brücke) |
| congstar im Wettbewerbs-Radar | nicht zeichenbar | **36 Paare**, alle `vergleichbar`, 9 Modelle × 4 (XS, XS Flex / Band Klein; S, S Flex / Band Mittel) |
| congstar in G1-Bandgrafiken | nur Barpreis-Punkte (seit 31.08.) | zusätzlich **TCO-24-Punkte** ab 08.09. |
| congstar-Kennzeichnung (E1) | nur `geraete-quellen.html` | + Erklärsatz auf `wettbewerbsradar.html` („Zweitmarke im Telekom-Netz, kein eigener Netzbetreiber") |
| Suite | 2/2832/14 (B-2-Basis) | **2 failed / 2854 passed / 14 skipped** |

## Die 36 Radar-Paare — Bandverteilung und warum M/L fehlen

Alle congstar-Paare entstehen in **zwei** Bändern: XS (15 GB) und XS Flex
in **Klein**, S (50 GB) und S Flex in **Mittel**. M (125 GB) und L
(200 GB) liegen in **Groß** — dort führt Vodafone keines der neun
Modelle mit vergleichbarer Karte, also entsteht nach der Bandregel (§7:
verglichen wird nur im gemeinsamen Band) kein Paar, und auch keine
Zeile (Zweitmarkenregel). Die Spanne der Paare: **−49,8 %** (S26 Ultra
256, Allnet Flat S, 1.093,00 € gegen VF 2.177,80 €) bis **−3,1 %**
(Z Fold8 512, XS Flex, 1.861,00 € gegen VF 1.919,80 €) — congstar ist in
jedem einzelnen Paar günstiger als Vodafone. Das ist die Marktlage eines
Discounters im Telekom-Netz, kein Rechenfehler; jede Zeile trägt Quelllink
und Abrufdatum.

## Rechenproben

Alle Beträge sind echte, in `geraete_tco.json` persistierte Sätze,
nachgerechnet mit `tco_model.tco_24()` und von Hand. Formel:
**Zuzahlung + Geräteraten × 24 (von 36) + Tarif × 24 + Anschlusspreis**.

### Probe 1 — iPhone 17 Pro 256 GB cosmic orange, Allnet Flat S

`1,00 + 24 × 28,50 + 24 × 20,00 + 0 = 1.165,00 €` (Ø 48,54 €/M.) —
`tco_24()` und Handrechnung exakt gleich; nach 24 Monaten offen
`12 × 28,50 = 342,00 €`. Die Ratenprobe des Adapters
(`oneTime + 36 × Rate == total`: `97 + 36 × 33,50 = 1.303` am iPhone 17
Pro 512) ist Bedingung des Speicherns, nicht Protokoll.

### Probe 2 — Galaxy S26 Ultra 256 GB cobalt violet, Allnet Flat XS Flex

`1,00 + 24 × 31,50 + 24 × 15,00 + 0 = 1.117,00 €` (Ø 46,54 €/M.), offen
`12 × 31,50 = 378,00 €`. Dasselbe Gerät im nicht-Flex-XS: Rate 29,50 statt
31,50 → `1.069,00 €` — der Flex-Aufschlag von 2 €/M. Gerät schlägt
durch, die Sätze bleiben getrennt (der Bestandsschlüssel ist SKU ×
Anbieter × Tarif).

### Probe 3 — Radar-Paar Galaxy S26 Ultra 256 GB, Allnet Flat XS

congstar `1.069,00 €` gegen Vodafone Mobil XS `1.547,80 €` im Band Klein:
`(1.069,00 − 1.547,80) / 1.547,80 = −30,9 %` — die Zahl, die auf
`wettbewerbsradar.html` steht. Gegenprobe iPhone 17 Pro 256 XS:
`(1.093,00 − 1.559,80) / 1.559,80 = −29,9 %` ✓.

## Vollsuite — zweimal gelaufen, gleiche Zahlen

Lauf 1 (nach Diff-Bewertung und Testergänzung): **2 failed /
2854 passed / 14 skipped** in 273 s. Lauf 2 (final, nach dem
E1-Vorlagensatz und Re-Render): **2 failed / 2854 passed / 14 skipped**
in 252 s. Die zwei Roten sind die bekannten vorbestehenden
Promo-Screenshot-Tests (`test_die_echten_screenshots_bestehen_die_pruefung`,
`test_der_leere_screenshot_wird_nicht_ausgeliefert`) — seit dem 03.09.
im Handover, nicht Teil dieses Auftrags. **Keine neuen Roten.** Die
Radar-Datei selbst: 22 Tests grün (21 aus Runde 1 + 1 neuer).

## Messgrenzen — ehrlich benannt

1. **Vier Tarifseiten sind alles, was es gibt.** 8 PlanVarianten ×
   lieferbare Geräte/Speicher = 72 Sätze; eine Postpaid-Seite XL
   existiert nicht (pages.xml, 08.09.) — XL läuft nur als Pflichtblatt.
2. **Ein Messtag (2026-09-08).** Bündel altern nicht (`upsert_buendel`
   frischt auf statt zu löschen — richtig); ein `mark_stale` für `TcoDB`
   fehlt weiterhin (bekannt offener Punkt seit Phase S 4b). Jede Zeile
   nennt ihr Abrufdatum.
3. **`tarif_bindung_monate` bleibt `null`.** Die Tarifseite trägt
   `minimumContractDuration` je PlanVariant, der Adapter trägt sie nicht
   in den Satz. Heute ohne Wirkung: `tco_bindung()` nimmt die längere
   Laufzeit, und die 36-Monats-Finanzierung führt die Karte ohnehin (für
   Flex wie nicht-Flex). Würde künftig ein Satz mit kürzerer Ratenlaufzeit
   als Tarifbindung erhoben, gehört das Feld nachgezogen.
4. **Boni und Rabatte bleiben benannte Lücke** (`tco_24().luecken`) —
   congstar rechnet mit laufenden Aktionen (M listed 25 €, im Bündel 24 €;
   Bereitstellungspreis geschenkt); die *eingeräumten* Rabatte stecken in
   `discounted`, weitere Boni sind bei keinem Anbieter strukturiert
   abrufbar. Die Lücke kürzt sich in Differenzen heraus
   (`_LUECKEN_OHNE_EINFLUSS_AUF_DIE_DIFFERENZ`).
5. **congstar führt nur 9 Modelle im Bündel** (4 Gerätefamilien ×
   Speicher). Auf 50 von 59 Radar-Gruppen steht deshalb bewusst KEINE
   congstar-Zeile — der Test nagelt beides fest (`0 < mit_congstar <
   len(gruppen)`): stünde sie überall, wäre es die Platzhalter-Wand;
   stünde sie nirgends, fehlte die Erhebung.
6. **`tarif_bindung` am Flex**: congstar Flex hat keine Mindestlaufzeit;
   `tco_24()` rechnet über den festen 24-Monats-Horizont (E2) — für
   Flex wie Bindung dieselbe ehrliche Comparabilität.
7. **Aus GitHub Actions nicht gemessen** — dieser Bestand lebt vom
   Lokallauf auf Antonios Mac (wie Telekom, B-2 Messgrenze 3).

## Commits auf `openclaw/ticket-b3-buendel-congstar`

| Commit | Schritt |
|---|---|
| `e9bb117` | (Runde 1) congstar-Bündeladapter, PIB-Nummern-Brücke, 20 Tests |
| `41663ca` | (Runde 1) 72 congstar-Bündelsätze, Beleg 58/58 ehrlich |
| `afa9e0f` | congstar als Zweitmarke im Radar — Modul, Tests vollendet, E1-Satz |
| `a112fd3` | Site gerendert (36 Paare, E1-Kennzeichnung) |
| (dieser) | Bericht (diese Datei) |

Kein `main`, kein Deploy, kein Render-Hook, kein `uv.lock`,
kein `git stash`.
