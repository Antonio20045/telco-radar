# B-4 — Bündelerhebung 1&1: Gerät × Tarif (08.09.2026, Runde 4)

Auftragsgrundlage: `BRIEF_B4_BUENDEL_EINSUNDEINS.md` (Original) und
`BRIEF_B4_BUENDEL_EINSUNDEINS_R4.md` (Restauftrag nach drei Infra-Abbrücken).
Runden 1–3 lieferten alle inhaltlichen Commits (`5ff6a1c`, `c069a84`,
`06c3b69`, `a76ac94`); Runde 3 wurde um 22:56 vom Gateway-Neustart erwischt,
bevor ein einziger Suite-/Berichts-Commit entstand — es gab nichts zu
übernehmen. Diese Runde (R4) leistet nur noch: Smoke-Check, Vollsuite,
Bericht, Push.

## Ergebnis in einem Satz

**61 1&1-Bündelsätze** (35 Gerätefamilien × Speicher, vorher 0) im Bestand
neben Vodafone 338 · Telekom 45 · congstar 72 · o2 63 (gesamt **579**); der
Wettbewerbs-Radar führt 1&1 als **50 Vergleichspaare im Band Klein** (alle
günstiger als Vodafone, −13,5 % bis −52,0 %), 38 weitere Gruppen sagen
ehrlich „kein Bündel erhoben"; Vollsuite **0 failed / 2880 passed /
12 skipped** — keine neuen Roten, die zwei bekannten Promo-Screenshot-Roten
der Basis sind in diesem Stand grün.

## Recherchebefund — hwdVariantsPrices-Straße und ?chosenTariff=

(Vollständiger Befund im Modulkopf von
`src/telco_radar/collect/geraete/einsundeins.py`; hier die vier Punkte,
die den Zugriff tragen.)

**1. Der Befund, der 1&1 ein Jahr draußen hielt, war die richtige Zahl mit
dem falschen Etikett.** Die Produktseite trägt ein sauberes
`application/ld+json` vom Typ `Product` — und `offers.price` ist NICHT der
Gerätepreis, sondern der **Monatspreis des Bündels** (gemessen 04.09. an
`mobile.1und1.de/iphone-17-pro`: „44,99 EUR" für „iPhone 17 Pro mit 1&1
All-Net-Flat S"). Als Barpreis gespeichert wäre das plausibel falsch; unter
TCO-first ist genau diese Zahl die Leitgröße. 1&1 verkauft Geräte NUR im
Tarifbund — `preis_ohne_vertrag` bleibt deshalb leer, weil es ihn nicht
gibt, nicht weil er fehlt.

**2. Die hwdVariantsPrices-Preiskarte ist der serverseitige Katalog.** Die
Gerät-×-Tarif-Kombinatorik über ALLE Tarife trägt die Seite nicht
serverseitig: `?chosenTariff=tariff-anf-m-mvl` liefert eine **byte-identische**
Antwort wie die Seite ohne Parameter (326 604 Bytes), und der verlinkte
Tarifdetails-Iframe ist eine 48-KB-JavaScript-Hülle ohne einen Preis — echte
Tarifwähler gibt es an dieser Quelle nur im Browser (Messgrenze, keine
Lücke). Was serverseitig da ist, ist `hwdVariantsPrices` als Inline-JS:
der Bündelmonatspreis des **Default-Tarifs über alle Farben und
Speichergrößen**, Werte in Cent. Schlüssel ohne `-bundle-`-Segment sind der
Tarifbund; die mit sind Zubehör-Bundles (AirPods) und werden über den
Schlüssel verworfen, nicht über den (höheren) Betrag. Tarifname steht in
derselben Antwort (`<span id="tariff-description">1&1 All-Net-Flat S</span>`),
seine Slug im eigenen Tarifdetails-Link, seine Laufzeit in
`window.currentHardwareOfferDuration` (überall 36).

**3. Der Tarifname löst auf den Tarifbestand auf.** Der aus der Quelle
gelesene Name trifft `/handytarife` als ld+json-Knoten; `tarif_bezug` löst
beide auf dieselbe ID (`11:1-1-all-net-flat-s`) — 61/61 Sätze Güte `hoch`.
Damit war der alte Vorbefund („1&1-tarif_id ohne Datenvolumen verhindert die
Band-Zuordnung") mit echten Daten gelöst statt nur benannt.

**4. Robots und Absender.** `mobile.1und1.de/robots.txt` sperrt für
`User-agent: *` die Verzeichnisse `/xml/`, `/static/`, `/modules/` und
Bestellstrecken; Produktseiten und `/smartphones` sind frei, der Parameter
`?chosenTariff=` ist ausdrücklich erlaubt. Absender `TelcoRadar/1.0`
(UA-Override geprüft und gesetzt), reiner HTTP-GET. Beleg
`outputs/beleg-einsundeins-geraete-2026-09-08.json`: **44/44 Requests
ehrlich** — je Request URL/Host, Status, tatsächlich gesendeter UA aus
`resp.request.headers`, `transport=http-get`, `browser=false`, inklusive
robots- Abrufen; `alle_ehrlich: true`.

## Der eine Monatsbetrag wird nicht aufgeteilt (§ 13.2)

Der Datalayer der Seite nennt eine Aufteilung — und **widerlegt sich
selbst**: Hardware-Rate 45,00 plus Tarif 14,99 ergäbe 59,99, das Bündel
kostet aber 44,99 (ld+json UND Preiskarte, beide 256 GB); die Differenz von
15,00 € (bei 512 GB: 18,00 €) ist ein unbenannter Nachlass, der nur im
Verbund gilt. Diese Zahlen in `geraet_monatsrate` und `tarif_monatlich` zu
schreiben hieße, eine Anbieteraufteilung zu behaupten, die der Anbieter
selbst nicht einhält. Alle 61 Sätze tragen deshalb `buendel_monatlich`,
`tarif_monatlich`/`geraet_monatsrate` bleiben null — `tco_model` erzwingt
diese Disziplin (`ValueError`, wenn ein Bündelmonatspreis neben Bestandteilen
stünde). TCO-24 = 24 × Betrag; die Karte zeigt zusätzlich die 36-Monats-
Laufzeit der Finanzierung.

## Vorher / Nachher

| | Vorher (83b1add, B-3-Stand) | Nachher (dieser Stand) |
|---|---|---|
| Bündel gesamt in `geraete_tco.json` | 518 | **579** |
| davon 1&1 | **0** | **61** (35 Familien × Speicher; je Speichergröße EIN Satz, erste Farbe vertritt — Dedupe-Regel wie congstar B-3) |
| Tarif je Satz | — | 61× „1&1 All-Net-Flat S", `tarif_id` 61/61 Güte `hoch` |
| 1&1 im Wettbewerbs-Radar | 0 Zeilen | **50 Paare** (`vergleichbar`, alle Band Klein) + 38 ehrliche „kein Bündel erhoben"-Zeilen |
| Quelle + Abrufdatum je Zeile | — | 61/61 (`quelle_url` mobile.1und1.de/…, `abgerufen_am` 2026-09-08) |
| Zustand | — | 61× `neu` |
| Suite | 2 failed / 2854 / 14 (B-3-Basis) | **0 failed / 2880 passed / 12 skipped** |

## Die 50 Radar-Paare — alle Band Klein, alle negativ

Nachgerechnet aus dem gerenderten `site/wettbewerbsradar.html`: 88
1&1-Zeilen gesamt, davon **50 mit Prozentwert** (Status `vergleichbar`,
Band-Verteilung: Klein 50 / Mittel 0 / Groß 0) und 38 mit „Für dieses Modell
ist bei 1&1 kein Bündel erhoben" — kein Platzhalter ohne Wahrheit, jede
Nicht-Zahl sagt ihren Grund. Die Spanne: **−13,5 % bis −52,0 %**, in jedem
einzelnen Paar ist 1&1 günstiger als Vodafone. Dass ausschließlich Band
Klein entsteht, ist Datenlage, nicht Filter: erhoben ist der Default-Tarif
All-Net-Flat S, und er löst aufs kleine Band auf. Der Erklärsatz der Seite
nennt 1&1 als Netzbetreiber („Telekom, 1&1 und o2 stehen darunter") — E1
erfüllt.

## Rechenproben

Alle Beträge echte, in `geraete_tco.json` persistierte Sätze (§ 13.2:
TCO-24 = 24 × `buendel_monatlich`; Laufzeitangabe 36 Monate Finanzierung).

### Probe 1 — iPhone 15 128 GB schwarz, All-Net-Flat S

`24 × 32,99 = 791,76 €` — genau die Zahl auf `wettbewerbsradar.html`
(neben „Klein · VF 1235.80 €", Beleg „mobile.1und1.de · 2026-09-08").

### Probe 2 — iPhone 15 256 GB schwarz, All-Net-Flat S

`24 × 36,99 = 887,76 €` — derselbe Tarif, eine Speicherstufe höher;
der Aufschlag schlägt ungeteilt durch, weil der Monatsbetrag das Bündel ist.

### Probe 3 — iPhone 16 128 GB blau, All-Net-Flat S

`24 × 37,99 = 911,76 €`.

### Probe 4 — Radar-Paar iPhone 15 128 GB (Seitenzahl gegen gerechnet)

`(791,76 − 1235,80) / 1235,80 = −35,9 %` — exakt der Wert, der in der
1&1-Zeile der Gruppe „Apple iPhone 15 128 GB" steht ✓.

## Vollsuite — zweimal gelaufen (Zahlen in `outputs/b4-suite-zahlen.txt`)

**Lauf 1: 2787 passed / 0 failed / 105 skipped** (268 s). Die 105 Skips
waren ein Umgebungsbefund, kein Bestandsbefund: das Python-Paket `playwright`
fehlt im CommandLineTools-Python dieses Worktrees („playwright fehlt",
69 Skips allein in `test_geraete_reiter_browser.py` in 0,16 s), die
Browser-Abdeckung fehlte damit vollständig — ein Skip sieht im Protokoll wie
ein Erfolg aus. Repariert (`playwright==1.60.0`, Chromium-Build 1223
nachgeladen, 92,4 MiB).

**Lauf 2: 2880 passed / 12 skipped / 0 failed** (294 s, EXIT 0) — mit
Browser-Abdeckung bestätigt (`test_geraete_reiter_browser.py` einzeln:
68 passed / 1 skipped in 31 s). Gegen die B-3-Basis (2 failed / 2854 /
14 skipped): **keine neuen Roten**; die zwei bekannten Promo-Screenshot-Roten
sind in diesem Stand grün (`test_promo_seite.py` einzeln: 23 passed) —
Besserstellung, keine Regression. Smoke-Check vorab:
`test_geraete_tco_band.py` + `test_wettbewerbsradar.py` **29 passed**.

## Messgrenzen — ehrlich benannt

1. **Nur der Default-Tarif ist erhoben.** Die Gerät-×-Tarif-Kombinatorik
   lädt nur im Browser nach (`?chosenTariff=` byte-identisch gemessen);
   alle 61 Sätze tragen „1&1 All-Net-Flat S". Andere Tarife (M, L, Unlimited)
   brauchen entweder JS-Rendering oder einen eigenen Spike — je Speichergröße
   drei Viertel der möglichen Sätze zu erfinden, ist die explizit
   abgelehnte Alternative (Adapter-Kopf).
2. **Nur Band Klein im Radar.** Folge aus 1: Mittel/Groß-Paare können nicht
   entstehen, solange kein größerer Tarif erhoben ist. Der Vorbefund
   „tarif_id ohne Datenvolumen" ist entfallen (61/61 `hoch`), die Grenze ist
   heute die Erhebung, nicht die Zuordnung.
3. **38 Radar-Gruppen ohne 1&1-Zahl** — 1&1 führt diese Modelle nicht im
   Bündel; die Zeilen sagen das mit Grund statt zu fehlen.
4. **Ein Messtag (2026-09-08).** Bündel altern nicht (`upsert_buendel`
   frischt auf statt zu löschen — richtig); ein `mark_stale` für `TcoDB`
   fehlt weiterhin (bekannt offener Punkt seit Phase S 4b, gilt für alle
   Anbieter). Jede Zeile nennt ihr Abrufdatum.
5. **`anschlusspreis` und `rabatte` bleiben ungesetzt** (61× null / 61×
   leer): die Preiskarte nennt weder ein separates Entgelt noch benannte
   Rabatte; der Nachlass im Datalayer ist unbenannt und wird deshalb nicht
   als `Rabatt` getragen (§13.2-Disziplin).
6. **`tarif_bindung_monate` bleibt null** — dieselbe Grenze wie B-3
   Messgrenze 3; `tco_bindung()` nimmt die längere Laufzeit, und die
   36-Monats-Finanzierung führt die Karte.
7. **Aus GitHub Actions nicht gemessen** — dieser Bestand lebt vom
   Lokallauf auf Antonios Mac (`scripts/lokallauf_einsundeins.py`, Muster
   B-2/B-3; Beleg 44/44 ehrlicher UA).

## Commits auf `openclaw/ticket-b4-buendel-1u1`

| Commit | Schritt |
|---|---|
| `5ff6a1c` | (Runde 1) 1&1-Bündellesart: Preiskarte `hwdVariantsPrices`, §13.2-Monatsbetrag ungeteilt, 14 Tests |
| `c069a84` | (Runde 2) 61 1&1-Bündelsätze erhoben, Beleg 44/44 ehrlich, UA-Override, Lokallauf-Skript |
| `06c3b69` | (Runde 2/3) Site gerendert: 50 Radar-Paare Band Klein, 61 TCO-Karten, E1-Hinweis |
| `a76ac94` | (Runde 3) Leerzustand-Test neu kalibriert (Fall am echten Tarifbestand konstruiert, beide Mutationen der Gegenprobe geprüft) |
| `850048e` | (Runde 4) Suite-Zahlen Lauf 1 gesichert (2787/0/105 + Playwright-Diagnose) |
| (nachfolgend) | Suite-Zahlen Lauf 2 (2880/0/12); dieser Bericht; Push |
