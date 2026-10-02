# P5 — LIVE-FALL-Prüfung: „Wenn ein neues iPhone rauskommt, muss es automatisch erkannt und geführt werden."

**Prüfer ohne Bau-Kontext.** Grundlage: der frisch gerenderte `site/`-Stand
(18.09.2026, 09:24) gegen den echten Bestand vom 17.09.2026 — 16 Auto-Katalog-
Einträge (2× iPhone 18), 58 iPhone-18-Listungen, 105 iPhone-18-Bündel
(30 SKUs, Messtag 1). Gemessen am echten Browser (Playwright/Chromium über
`http://127.0.0.1:8774`, Skript `pruef_live.py` + `pruef_live_2.py` in diesem
Ordner; Server nach Lauf gekillt, Port frei verifiziert) plus statische Prüfungen
am HTML/CSV/State. Suite `-k geraete` gelaufen.

**URTEIL: DURCH (durch=true). Keine offenen FAILs.** Der Live-Fall hält:
Ein Gerätestart ohne jede Handarbeit steht am nächsten Tag mit Preisen,
Quellen und TCO im Katalog und in allen Exporten; die Zeitreihe lässt es
regelkonform draußen, ohne tote Sprünge. Drei Reste (nicht FAILs) unten.

---

## 1. Gerätekatalog: iPhone 18 — BESTANDEN

Suche „iPhone 18" im Katalog-Suchfeld: **10 sichtbare Modellzeilen**
(2 Modelle × 5 Speicher-Stufen), **jede mit Preis ODER benanntem Zustand**:

| Zeile (data-modell) | Anzeige (Browser-Innentext, gekürzt) |
|---|---|
| apple-iphone-18-pro-256 | „noch keine Zeitreihe · ab 1.423,00 € bei congstar ↗ · 17. September 2026 · 3 · 1&1 · Vodafone · congstar · 1.423,00 € – 1.449,90 €" |
| apple-iphone-18-pro-512 | „noch keine Zeitreihe · ab 1.695,00 € bei congstar · 2 · Vodafone · congstar" |
| apple-iphone-18-pro-1024 | „noch keine Zeitreihe · ab 2.199,90 € bei Vodafone · ein Preis" |
| apple-iphone-18-pro-2048 | „noch keine Zeitreihe · ab 2.949,90 € bei Vodafone · ein Preis" |
| apple-iphone-18-pro-max-256/512/1024/2048 | analog (1.593,00 bis 3.099,90 €) |
| apple-iphone-18-pro-1 / -max-1 | „ab 2.193,00 € bei congstar · ein Preis" — **Phantom-Speicher „1 GB"** (s. Rest R1) |

- Alle 8 Zeilen mit Bündeln tragen den Hinweis **„noch keine Zeitreihe"** an
  der Modellzelle (die P5/E1-Regel: der Hinweis nur MIT Bündel, die TCO-Spalte
  sagt ihren eigenen Satz — eine Aussage je Ort).
- **Klick auf die Zeile iPhone 18 Pro 256:** Aufklapper `kz-102` öffnet mit
  Preisen (€ sichtbar) — kein toter Klick.
- **Gegenprobe fail-closed:** Die „ohne-details"-Zeile (Galaxy S24 Ultra 512,
  kein Bündel) öffnet bei Klick NICHTS (`offen_nach <= offen_vor`) — korrekt.

## 2. Exporte — BESTANDEN (grep, alle drei Dateien)

| Datei | iPhone-18-Zeilen | Bemerkung |
|---|---|---|
| `site/exporte/geraete-modell-barpreis.csv` | **10** | vollständige Preisspalten (Ab-Preis, Anbieter, Spanne, Quelle, 2026-09-17) |
| `site/exporte/geraete-modell-tco.csv` | **10** | TCO + Ø €/Monat + Δ zu Vodafone; die beiden „1-GB"-Zeilen und zwar **benannt**: „kein Bündel gemessen" |
| `site/exporte/geraete-aktuell.csv` | **58** | alle Listungen inkl. 1&1-„vorbestellbar"-Zeilen (Preis leer, Verfügbarkeit benannt) |
| `site/exporte/geraete-historie.csv` | 58 | erste Messpunkte mit dabei |

## 3. Zeitreihe/Wahl — BESTANDEN

- Wahl-Datenknoten `#gr-zeitreihe-daten`: **88 Modelle erlaubt, iPhone 18
  NICHT dabei** — korrekt, denn die Zeitreihe verlangt 2 Bündel-Messtage,
  iPhone 18 hat Messtag 1 (17.09.). Der Grund steht (P5/E1) **an der
  Katalogzeile** („noch keine Zeitreihe", 8× nachgewiesen).
- Browser: `#gr-zr-suche` „iphone 18" → **„kein Treffer"**, leere Vorschau.
  „watch", „airpods", „tab s11" → ebenfalls kein Treffer (korrekt).
- **Kein toter Sprunglink:** 174 `?modell=`-Links im HTML, **0 Ziele außerhalb
  der 88 erlaubten** (statisch vollständig geprüft); die 97 `a.gr-ksprung`-
  Links der Abweichungstafel ebenfalls. Kontrollklick „iphone 17" → Vorschau →
  Auswahl: Zeitreihe erscheint, Antwort-Satz „Beim Apple iPhone 17 im Band
  Klein … congstar … 949,00 € (TCO-24)", 2 SVG sichtbar.
- **Deep-Link `?modell=apple-iphone-18-pro-256`:** fällt still aufs
  Startgerät (iPhone 17 Pro) zurück — Antwort + SVG sichtbar, kein leerer/
  toter Zustand (dokumentiertes Verhalten, kein Bug).

## 4. Bündelose Auto-Modelle — BESTANDEN (9 von 14 sichtbar, 5 regelkonform draußen)

Der Bestand hat **14** nicht-iPhone Auto-Einträge (der Auftrag nannte 12).
Im Katalog sichtbar MIT Preis/Listung (Browser-Suche): Watch S12 GPS 42/46
(469/505 €, o2-Quelle), AirPods 5 (157 €), Galaxy Tab S11 Ultra (1.549,90 €),
Tab S10 FE, Tab A11+, Xcover7 Pro EE, Xcover 7 EE. **Nicht in der
Zeitreihen-Wahl** (Suche watch/airpods/tab s11 → kein Treffer) — korrekt.

**5 Auto-Einträge sind (regelkonform) nirgends sichtbar:** Watch Series 12
42/46/46 Milanese, Watch Ultra 4 Natur/Black. Beweis im State: **0 Listungen,
0 Bündel** für diese device_ids (DB kennt nur die zwei S12-GPS-Listungen von
o2). Nach der P5/E1-Regel („Sichtbarkeit = Listung ODER Bündel") ist
Unsichtbarkeit ohne jede Messung richtig — es entstünden sonst Phantom-Zeilen.
ABER: „Watch S12 GPS 46 mm" (o2-Schreibweise, mit Daten) und „Watch Series 12
46" (Auto-Eintrag, ohne Daten) sind **dieselbe Uhr in zwei Katalog-Einträgen**
— dasselbe Muster wie der E4-S1-Befund (Nennungs-Varianten → zwei device_ids).
Das ist Rest R2, kein FAIL der Sichtbarkeitsregel.

## 5. P4-Abnahme stabil (Stichprobe) — BESTANDEN

- **Kein Querscroll 390:** `document.scrollWidth == 390 == innerWidth`, auch
  nach Wechsel in den Katalog-Reiter (der kritische, tabellenlastige Fall).
- **Leitzahl größte Schrift:** `gr-leit-zahl` 60 px; die nächstgrößte
  sichtbare Schrift im Vergleichs-Reiter ist 21 px (Balkenzahlen). Klar erfüllt.
- **Katalog-Umschalter Barpreis/TCO:** Klick „Gesamtkosten (TCO-24)" wechselt
  die Spaltenköpfe (MODELL/EINZELGERÄTEPREIS/HÄNDLER/SPANNE →
  MODELL/TCO-24/Ø €/MONAT/Δ ZU VODAFONE/BAND), den Zeileninhalt
  (1.423,00 € → 1.375,00 € / 57,29 € / −352,79 € · −20,4 % / Klein) und
  `aria-pressed` (Einzelgerätpreis false, TCO true). Ohne Reload.

## 6. Suite — GRÜN

`pytest -q -k geraete`: **1505 passed, 6 skipped, 0 failed** (3:26 min).
Skips: 1× fastapi-Modul fehlt (Newsletter, vorbestehend), 1× datumsabhängiger
Raster-Skip („kein eigener Tiefpunkt in diesem Raster"), 4× „kein Chromium
gefunden" in `test_geraete_seite.py` — der Test-Suchpfad kennt das hiesige
Homebrew-Playwright nicht, obwohl Chromium läuft (vorbestehend, nicht P5).

## 7. Schlussfrage: Wie lässt sich Automatik-Sichtbarkeit WEITER verbessern?

**Reste (keine FAILs, alle im Scope Automatik-Sichtbarkeit):**

1. **R1 — Speicher-Parse „1 TB" → „1 GB" (Datenfehler, sichtbar).** congstar
   listet „iPhone 18 Pro 1 TB"; die Speichererkennung macht daraus
   `speicher_gb=1` → Phantom-Modellzeilen „Apple iPhone 18 Pro 1 GB"
   (`apple-iphone-18-pro-1`, `-max-1`) in Katalog UND beiden Modell-Exporten
   („iPhone 18 Pro 1 GB ab 2.193,00 €"). Für die Zielgruppe (Manager ohne
   Technik-Hintergrund) liest sich das als absurd kleines Gerät. Fix: TB-Einheit
   beim Speicher-Parsen auf ×1024 normalisieren (1024 existiert parallel als
   eigene Stufe aus Vodafone-Daten — dieselbe Realstufe, zwei IDs).
2. **R2 — Zwillings-Einträge im Auto-Katalog (E4-S1-Muster erneut).**
   „Watch S12 GPS 46 mm" vs. „Watch Series 12 46", „Watch Ultra 4 …" ×2,
   „Galaxy Xcover 7 EE" (325 €) neben „… EE 128" (253 €): dieselben Geräte in
   zwei device_ids. Heute folgenlos (5 davon ohne jede Listung → unsichtbar),
   aber sobald ein Betreiber die zweite Schreibweise liefert, landen die Daten
   auf einem zweiten Eintrag statt dem bestehenden — Preishistorie und
   Listungsdauer beginnen bei null. Fix-Richtung: Namens-Alias im
   Auto-Katalog-Vereiniger („S12" ≡ „Series 12"; Speicherlose IDs auf die
   Speicher-stufige ID falten), bevor der nächste Nachtlauf die Trennung
   zementiert.
3. **R3 — Kein Grundhinweis am Ort der Wahl.** Wer im Zeitreihen-Suchfeld
   „iphone 18" tippt, bekommt „kein Treffer" ohne ein Wort, warum. Der Grund
   steht (richtig, nach P5/E1) nur an der Katalogzeile. Minimallösung im
   Rahmen der Hausregeln (keine Bedien-Erklärung, keine zweite Aussage am
   Ort): eine Zeile „Neu seit 17. September — Katalog ansehen" NUR bei
   0 Treffern und Katalog-Treffer für denselben Begriff, sonst leer lassen.
4. **Beobachtung, kein Handlungsbedarf im Scope:** Der Deep-Link auf ein
   Modell ohne Zeitreihe fällt still aufs Startgerät zurück (dokumentiert).
   Wer einen Radar-/Katalog-Link auf iPhone 18 setzt, bevor dessen zweite
   Messung steht, landet still bei iPhone 17 Pro — die 174 `?modell=`-Links
   zeigen aber alle nur auf erlaubte Modelle, der Fall tritt heute nur bei
   handgebauten URLs ein.

**Fazit:** Der Automatismus trägt den Live-Fall. iPhone 18 wurde ohne
Handarbeit erkannt (16 Auto-Einträge vom 17.09.), geführt (Katalog mit
Preisen/Quellen/Datum, 58 Listungen + 105 Bündel im Bestand) und korrekt
gedrosselt (Zeitreihe erst ab Messtag 2, Grund benannt, kein toter Sprung).
durch=true.

---

*Skripte: `pruef_live.py`, `pruef_live_2.py` (Playwright + lokaler Server
8774, nach Lauf beendet). Statische Prüfungen: grep über
`site/exporte/*.csv`, JSON-Analyse von `data/state/geraete_db.json`,
`geraete_tco.json`, `geraete_katalog_auto.json`, Parse von
`#gr-zeitreihe-daten` und `site/data/geraete-zeitreihe.html`.*
