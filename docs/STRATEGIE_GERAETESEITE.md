# Strategie Geräteseite — Ist-Stand und Phasenplan

**Stand 11.09.2026. Grundlage: Ist-Stand-Audit an HEAD `be42b4f` (= Live-Stand, byte-identisch
verifiziert). Methode: 4 parallele Auditoren (UX/Design, Datenqualität, TCO-Korrektheit,
Anforderungsabgleich) mit Screenshot- und Messpflicht, danach adversarielle Gegenprobe der
kritischsten Befunde durch unabhängige Prüfer (3 bestätigt, 1 widerlegt und korrigiert).
Befund-IDs (UX-n, DAT-n, TCO-n, S2A-n … RM-n) verweisen auf dieses Audit; Artefakte
(Messskripte, Screenshots, Beweisbündel) liegen unter `/tmp/audit-geraete-20260911/` (flüchtig —
für Abnahmen werden Vorher/Nachher-Screenshots neu geschossen). Maßgebliche Anforderung bleibt
`AUFTRAG_GERAETESEITE.md` (05.09.2026) im PM-Workspace.**

## 1. Kurzbild

Die Geräteseite ist **rechnerisch und datenseitig besser als ihr Ruf**: Die TCO-24-Rechnung ist
korrekt (8/8 Stichproben auf den Cent exakt, Eigenrechnung = Datenbestand = Anzeige), TCO-36 ist
vollständig beseitigt, die Bündelerhebung läuft für alle fünf Anbieter (589 Bündel gegenüber
63 o2-Bündeln am 05.09.), Werte sind innenkonsistent ohne Ausreißer, und der
Wettbewerbs-Radar (§2b) existiert als eigene Unterseite `wettbewerbsradar.html` mit korrekter
%-Leitzahl und Sortierung.

Warum die Seite dennoch „nicht funktioniert": **Die sichtbaren Zahlen antworten nicht auf die
Auswahl.** Die Tarifband-Auswahl steuert nur die SVG-Graphen; die Anbieterkarten — die einzigen
Stellen mit exakten Zahlen — zeigen weiterhin alle Bänder gemischt und unbeschriftet (UX-1,
gegeneprüft und bestätigt). Die exakten Werte im Graphen stecken nur im Hover-Tooltip, der am
Telefon gar nicht existiert (UX-5). Wer also Modell und Tarif wählt, sieht die Zahlen sich NICHT
ändern — genau die Wahrnehmung „TCO funktioniert gar nicht". Dazu kommen Verstecke (Radar-Versprechen
im Untertitel, unerreichbare Verlaufs-/Portfolio-Tafeln) und Zähl-Wirrwarr.

Die zweite, stillere Gefahr ist datenseitig: **Die tägliche Bündelerhebung überschreibt sich
selbst** — es wächst keine Preishistorie, obwohl täglich gemessen wird (DAT-2, bestätigt). Jeder
Tag ohne Fix ist ein dauerhaft verlorener Historienschritt für die §2a-Zeitachse.

## 2. Ist-Stand je Ebene

### 2.1 Anforderungen (AUFTRAG § für §)

| Auftrag | Status | Beleg (Kürzel) |
|---|---|---|
| §1 Zielgruppe Device-Einkauf | Maßstab angelegt, Orientierung schwach | UX-2k, UX-4 |
| §2a Graph Modell × Tarifniveau | **teilweise** — Kopplung steuert nur den Graphen, nicht die Karten; Zeitachse fehlt (Einpunkt) | S2A-1 ✓, UX-1 ✗, S2A-2 ✗ |
| §2b Wettbewerbs-Radar | **erfüllt** — `wettbewerbsradar.html`, %-Leitzahl mit Vorzeichen, Sortierung verifiziert; Untertitel auf geraete.html führt aber in die Irre | S2B-1 ✓, UX-2 (korrigiert) |
| §3 TCO-24-Definition | **erfüllt** — Formel inkl. Geräteraten (§3-Satz gedeckt), Restbeträge getrennt (487× „ab Monat 25"), Prämiengrößen außen vor; Ausnahme: 8 congstar-Karten mischen unter „Gerätepreis" eine Finanzierungssumme | TCO-4 ✓, S3-1 ✓, TCO-1 ✗ |
| §4 Katalogumfang | **erfüllt** — 60 Geräte, unverändert seit 05.09. | S4-1 ✓, DAT-9 ✓ |
| §5 Datenlage | Bündelabdeckung stark verbessert (589), aber: kein Band mit allen 5 Anbietern, keine Bündel-Historie, Telekom seit 09.09. stale, uvp weiterhin 0/715 | DAT-1 ✗, DAT-2 ✗, DAT-3 ✗, DAT-5 ✗ |
| §6 Reihenfolge | Schritt 1 (Bündelerhebung) gebaut und live; Schritte 2–4 erledigt; Schritt 5 (Optik) offen | S5-1 ✓, STR-1 ✓ |
| §7 Bänder | **im Code exakt** (≤20 / 21–60 / >60, Unbegrenzt außen); 17 Bündel an Tarifen ohne Volumen fallen ehrlich heraus | S7-1 ✓, S7-3 ✗ |
| §8 Anbieterkreis | **erfüllt** — Händler (freenet/mobilcom-debitel, Saturn, Medimax, EP) im Radar; Amazon/MediaMarkt/expert/Euronics unter „Nicht erhebbar" ausgewiesen | S8-1 ✓, S8-2 ✗ (niedrig) |

### 2.2 Frontend/UX (Screenshots: Desktop 1440 + Mobil 390, selbst angesehen)

- **UX-1 (hoch, gegenprüft):** Bandwahl wechselt nur die SVG-Panels (`app.js` `zeigePanel`
  schaltet `.gr-tband`). Die Kartenklappe zeigt bei jedem Band dieselben 22 Karten aller Bänder
  gemischt (1.093–2.658 €), ohne Band-/GB-Kennzeichnung, inklusive einer o2-Unlimited-Karte, die
  laut §7 außerhalb aller Bänder liegt. „TCO-24 je Anbieter in Tarifstufe X" ist aus den Karten
  nicht beantwortbar.
- **UX-5 (mittel):** Exakte Werte nur als SVG-Hover-Tooltip — am Telefon nicht abrufbar;
  Band-Chart liegt bei y=1141 px außerhalb des ersten Viewports.
- **UX-2 (hoch → nach Gegenprobe niedrig/mittel):** Untertitel „Wettbewerbs-Radar: alle Geräte
  nach Abweichung … sortiert" führt per Direktlink auf die existierende Radar-Seite (erfüllt 2b),
  aber die Formulierung verspricht die Übersicht auf dieser Seite; die eingebaute Barpreis-Alarmtabelle
  (48 Zeilen, 12 sichtbar, zwei Aufklapper tief) ist eine redundante Zweitansicht ohne TCO-Bezug.
- **UX-3 (mittel):** Tafeln „Verlauf" und „Portfolio" sind ohne Reiter-Knopf und ohne funktionierenden
  Deep-Link unerreichbar — die Lifecycle-Frage („wie lange bleiben ältere Modelle im Shop") hat
  keinen zugänglichen Ort.
- **UX-4 (mittel):** 88-Optionen-Dropdown nach Bündelanzahl sortiert (unsichtbares Kriterium);
  die angezeigte „– N Anbieter"-Zahl zählt Listungen, nicht Bündel-Anbieter — zwei verschiedene
  Zahlen für „Anbieter".
- **UX-6/7 (niedrig):** Mobil liegen die Kernzahlen bei ~80 % Scrolltiefe, Kartenklappe bläht auf
  11.141 px; im G0-Chart überlappen Serienbeschriftungen; Band-mittel-Chart auf einen Tag kollabiert
  (ehrlich zur Datenlage).
- **RM-1/RM-2/RM-3 (niedrig):** Zähl-Wirrwarr (RV-1), „Tiefblau/tiefblau" getrennt (RV-2), keine
  Begriffs-Legende TCO-24/Band/Vorzeichen (S-Q7); Seitenhöhe 3,87 MB.

### 2.3 Daten (data/state, Stand 11.09.)

- **Bestand:** 589 Bündel — Vodafone 338, congstar 72, o2 71, 1&1 63, Telekom 45.
  `geraet_zuzahlung` 589/589, `anschlusspreis` 589/589, `laufzeit_monate` 589/589 belegt.
- **DAT-1 (hoch, gegenprüft):** Kein Band hat alle fünf Anbieter. Klein: ohne o2 (0).
  Mittel: ohne Telekom (0) und 1&1 (0). Groß: ohne Vodafone (0 von 338!) und 1&1 (0).
  Ursachen sind Erhebungslücken, nicht Portfoliolücken — laut §7 hat jeder Anbieter in jedem
  Band mindestens einen Tarif: 1&1 erhebt nur EINEN Tarif (10 GB), Vodafone nur mobil-xs/s/m
  (18/35/60 GB), Telekom-Verteilung 6/12/20/80 GB, congstar nur 4–5 Geräte mit Bündeln
  (DAT-4: 32 gelistete congstar-Geräte ohne Bündel).
- **DAT-2 (hoch, gegenprüft und verschärft):** `geraete_tco.json` hält genau einen Satz je
  Bündel-ID und wird je Lauf komplett überschrieben (`tco_store.save()` per `write_text`).
  Belegt am Paar 10.09.→11.09.: zwei reale 1&1-Preisänderungen (Galaxy S26, +2 €/Monat,
  +20 € Zuzahlung) existieren nur noch im Git-Commit. Die §2a-TCO-Linie kann strukturell nicht
  wachsen (`geraete_tco_band._reihe()` baut Einzelpunkt). `abgerufen_am`-Verteilung heute:
  421× 11.09., 108× 06.09., 47× 09.09., 8× 08.09., 5× 04.09.
- **DAT-3 (mittel):** Telekom letzter Lauf 09.09. (Cron-Ausfälle, s. PM-BRIEFING); 123 von 589
  Bündeln nicht tagesfrisch.
- **DAT-5 (mittel):** `uvp` 0/715 und `zuzahlung` 0/715 auf Listing-Ebene — UVP als Referenzpreis
  fehlt weiterhin vollständig (Rabatt-Aussagen unmöglich).
- **DAT-7 (niedrig):** Anschlusspreis exakt 0,00 bei allen Vodafone- (338) und congstar-Bündeln
  (72) — plausibel als dauerhafte Erlasskampagne, aber ungeprüft und damit eine mögliche
  systematische TCO-Untertreibung dieser beiden Anbieter um ~40 €.
- **DAT-10 ✓:** Plausibilität sauber — TCO-24-Spanne 511,66–3.349,75 €, Median 1.633 €;
  kein x100-Fehler, kein Copy-Muster, keine negativen Werte.

### 2.4 TCO-Mathematik

- **Korrekt und normkonform:** `tco_model.tco_24()` = Zuzahlung + Tarif×24 +
  Geräterate×min(24, Laufzeit) + Anschlusspreis (1&1: Bündelmonatspreis×24 + Zuzahlung +
  Anschlusspreis). 8/8 Stichproben über 2 Modelle × 4 Anbieter exakt; Band-Panels, Ø/Monat (÷24)
  und Delta-Zeile richtig; TCO-36: 0 Vorkommen auf der Seite.
- **TCO-1 (mittel):** Auf 8 congstar-Karten (Galaxy S26 Ultra 1024) steht unter „Gerätepreis"
  die tarifabhängige Finanzierungssumme (1.285–1.645 € je Tarif) statt des reinen Gerätepreises
  — verstößt gegen §3 „zwei Zahlen, nie vermischt".
- **TCO-3 (niedrig):** `tco_bindung()` (TCO-36-Methodik) lebt als unbenutzter Bibliotheksteil
  mit 16 Tests weiter — Wiederverwendung würde die Vereinheitlichung rückgängig machen.
- **TCO-5 (niedrig):** Fehlende Posten (None) fallen still aus der Summe — künftig fehlende
  Anschlusspreise würden TCO still um ~40 € drücken; Rechenweg nennt „nicht gemessen".

## 3. Phasenplan

Grundsatz: erst Datenfundament und Kernantwort, dann Optik (Auftrag §6). P2 ist zeitkritisch
(jeder Tag ohne Historien-Fix verliert Daten dauerhaft); P1 ist der größte Nutzer-Nutzen. Beide
sind schichtengetrennt (Store vs. View) und können parallel laufen. Jede Phase wird als eigener
Lauf mit Screenshot-Selbstkontrolle abgenommen (1440 + 390, Vorher/Nachher); Abnahme über
`pytest -q` + `scripts/pruefe_portal.py` + angesehene Screenshots, nicht über Prozessstatus.

### P1 — Karten folgen der Auswahl; Kernantwort ohne Hover lesbar
**Löst:** UX-1, UX-5, TCO-1. **Auftrag:** §2a, §3.
- Anbieterkarten folgen der Bandwahl: gefiltert auf das gewählte Band (oder klar danach
  gruppiert/beschriftet mit GB-Angabe); Mischliste abgeschafft; o2-Unlimited-Karte als
  außerhalb der Bänder gekennzeichnet statt einsortiert.
- Exakte TCO-24-Werte ohne Hover sichtbar: Wertzahlen an/unter den Band-Charts oder in einer
  kompakten Wertetabelle je Band; mobil lesbar.
- „Gerätepreis"-Label auf den 8 congstar-Karten durch korrekte Trennung ersetzen
  (Finanzierungssumme vs. reiner Gerätepreis, §3).
- **Abnahme:** Für iPhone 17 Pro 256 + jedes Band steht die Leitantwort (TCO-24 je Anbieter)
  ohne Hover und ohne Scroll-Exzess auf dem Schirm; Kartenliste ändert sich nachvollziehbar bei
  Bandwechsel (Playwright-Behauptung + angesehene Screenshots); bestehende Tests grün,
  neue Tests für Karten-Band-Kopplung rot-vor-grün.

### P2 — Bündel-Preishistorie schreiben (zeitkritisch, klein)
**Löst:** DAT-2, S2A-2-Fundament, STR-3. **Auftrag:** §2a Zeitachse, §1 Leserfrage „wann senken
Wettbewerber Preise".
- `tco_store` schreibt zusätzlich eine Append-Historie je Bündel (jsonl: bündel_id, datum,
  Summanden, gesamt) statt nur den aktuellen Satz zu überschreiben; Seite liest weiterhin den
  aktuellen Stand, die Historie wächst im Hintergrund.
- Migration: heutige `geraete_tco.json` als Startpunkt; Vergangenheit aus den täglichen
  „Stand"-Commits (04.–11.09.) ist NICHT rückwirkend zu rekonstruieren — ehrlich ab Tag X beginnen.
- **Abnahme:** Nach zwei Läufen existieren zwei Messpunkte je Bündel im Historienfile
  (nachgewiesen an 3 Beispiel-Bündeln); Seite unverändert korrekt (Site-Diff leer außer
  Zeitstempel); Tests für Append/Idempotenz (gleicher Tag → kein Duplikat).

### P3 — Bandabdeckung und Aktualität schließen
**Löst:** DAT-1, DAT-3, DAT-4, S7-3, DAT-5 (Teil).
- Vodafone: Bündel für Groß-Band-Tarife erheben (mobil-l 120 GB existiert in `tarife.jsonl`).
- Telekom: Mittel-Band-Bündel erheben; Cron-Staleness beheben (betrieblich, s. PM-BRIEFING
  11.09.: LLM-idle-timeouts der PM-Session — Erhebungsläufe entkoppeln).
- congstar: Bündel auf mehr der 36 gelisteten Geräte ausweiten (32 aktuell ohne Bündel).
- 1&1: Tarif-Matrix erweitern — **hängt an offener Entscheidung E-S2** (nur per Playwright
  erreichbar; Empfehlung PM: verwerfen). Ohne E-S2-Entscheidung bleibt 1&1 = nur Klein-Band.
- Datenvolumen für 13 Tarifsätze ohne Volumen nacherheben (8 davon o2) — rückt 17 Bündel ins
  Bandraster (S7-3).
- **Abnahme:** Band-Matrix (klein/mittel/groß × Anbieter) hat je Band ≥ 4 Anbieter mit Bündeln
  oder nennt die Ausnahme mit Grund auf der Seite; Telekom-`abgerufen_am` tagesfrisch an 3
  aufeinanderfolgenden Tagen; UVP-Nacherhebung nur, wenn ein konkretes Folgeticket es braucht
  (Referenzpreise für Rabatt-Aussagen — sonst offen lassen).

### P4 — Orientierung, Lesbarkeit, ehrliche Beschriftung (die „Optik"-Phase, zuletzt)
**Löst:** UX-2-Rest, UX-3, UX-4, UX-6, UX-7, RM-1, RM-2, RM-3/S-Q7, S8-2, TCO-3.
- Untertitel ehrlich formulieren (Ein-Gerät-Vergleich + Link auf Radar-Seite); Barpreis-Alarmtabelle
  entfernen oder auf die Radar-Seite verschieben (Redundanz ohne TCO-Bezug).
- Verlaufs-/Portfolio-Tafeln wieder erreichbar (Reiter-Knöpfe oder Deep-Links reparieren).
- Dropdown nach erkennbarem Kriterium (Marke/Neuheit) sortieren; „N Anbieter"-Zahl auf eine
  Zählweise festlegen (RV-1); „Tiefblau" normalisieren (RV-2); Begriffs-Legende
  TCO-24/Band/Vorzeichen (S-Q7); Händlerkennzeichnung „freenet (mobilcom-debitel)" (S8-2);
  Mobil-Layout: Kernzahlen vor die gequetschten Charts; Chart-Beschriftungen entzerren.
- `tco_bindung()` entfernen oder als ausdrücklich nicht-normativen Bibliotheksteil
  dokumentieren (Entscheidung Klasse C).
- **Abnahme:** Ein Einkäufer findet in <30 s (a) TCO-Antwort für ein Gerät, (b) Radar-Seite,
  (c) Lifecycle-Ansicht — nachgewiesen durch Klickpfad-Protokoll + Screenshots; RV-1/RV-2
  prüffähig als Tests.

### P5 — Zeitachse in den Band-Graphen (folgt der Datenreife aus P2)
**Löst:** S2A-2, §2a „Linie über die Monate".
- Sobald P2 ≥ 3 Messtage je Bündel liefert: Band-Panels als echte Linien über die Zeit zeichnen;
  bis dahin Einpunkt ehrlich beschriftet lassen („Serie startet").
- **Abnahme:** Für ein Modell mit ≥ 3 Messtagen zeigt der Band-Graph eine echte Linie je
  Anbieter; Screenshots vor/nach; Zeitachse lügt nicht (keine interpolierten Phantompunkte).

## 4. Entscheidungen in diesem Dokument (Klasse C, revidierbar)

1. **Karten folgen der Bandwahl** (P1): Die §2a-Kopplung gilt für die ganze Vergleichsansicht,
   nicht nur die Grafik — die Karten sind der Zahlenort der Seite. Hergeleitet aus UX-1
   (bestätigt); keine dokumentierte Entscheidung für die heutige Mischliste gefunden.
2. **Historie als Append-Datei** (P2), Seite liest weiter den aktuellen Stand: kleinster Eingriff
   mit täglichem Ertrag.
3. **Keine rückwirkende Historien-Rekonstruktion** aus Git-Commits: ehrlicher Neustart ab
   Umstellung statt halbwahrer Zeitreihe.

## 5. Offene Punkte für Antonio (über ENTSCHEIDUNGEN.md/Seneca)

1. **E-S2 (besteht bereits):** 1&1-Vollmatrix nur per Playwright — bauen oder verwerfen?
   Ohne Verwerfungs-Entscheidung bleibt 1&1 dauerhaft ein Klein-Band-Anbieter (DAT-1).
2. **DAT-7-Verifikation:** Anschlusspreis 0,00 € bei Vodafone/congstar als Erlass bestätigen
   (einmalige Stichprobe gegen die Shops) oder als „nicht gemessen" führen? Betrifft ~40 €
   TCO-Genauigkeit bei zwei Anbietern.

## 6. Betrieb

- Telekom-Erhebung hängt an den abgebrochenen PM-Tagesläufen (10./11.09., LLM-idle-timeout) —
  P3 enthält die Entkopplung; bis dahin gilt Telekom-Datenstand = 09.09.
- Kleinere Rückstellungen (kein eigenes Ticket, bei Berührung mitlösen): Tooltip-Doppel-Escaping
  im Band-Panel (UX-Nebenbefund), ALDI-TALK-Alternierfolge (DAT-8), Waisen-Bündel ohne Listung
  (DAT-6).
