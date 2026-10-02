# Notiz E3 — UNBEKANNTE entrauschen + iPad-Anker (P5, FM 1)

Auftrag: `geraete_unbekannt.jsonl` muss Frühindikator bleiben — ALDI-Tarif-Rauschen
filtern, iPad/WATCH/AirPods als Auto-Anker. Alle Messzahlen gegen die echte Datei
vom 17.09.2026 (284 Zeilen) und den gemergten Katalog (99 Einträge, 16 auto).

## 1. Tarif-Rauschen — Regel im Code, Bereinigung macht der nächste Lauf

- **Muster erhoben, nicht geraten:** Das Rauschen sind exakt 3 Zeilen —
  `Tarif S` / `Tarif M` / `Tarif L`, alle ALDI TALK, `quelle: microdata`, je
  `haeufigkeit: 29` (Summe 87). „87 von 284 Zeilen" aus dem Auftrag = diese
  Vorkommen; die Datei fasst wiederkehrende Titel per Upsert, stehen tun sie
  als 3 Zeilen.
- **Regel (`ist_tarif_titel`):** Wort „Tarif" UND keine Ziffer im Titel.
  Gemessen gegen ALLE 145 echten Titel: **genau die 3 getroffen, 142 bleiben**.
  Alle 25 ALDI-Gerätetitel bleiben (z. B. „MOTOROLA moto g86 5G, 256 GB,
  Spellbound (XT2527-2)"); der einzige ziffernlose Gerätetitel des Bestands
  („Oakley Meta - HSTN Prizm Polarized (AI Glasses)") trägt kein „Tarif" und
  bleibt. Zusammengesetzte Tarifnamen („Tarifpaket M") bleiben bewusst stehen
  — Wortgrenze grenzt nicht, konservativ.
- **Wirkort:** `persistiere_unbekannte` filtert beim SCHREIBEN neue Tarif-Titel
  UND lässt bestehende Rausch-Zeilen beim Neuschreiben fallen. An einer Kopie
  der echten Datei gemessen: **284 → 281 Zeilen**, Tarif-Zeilen danach 0,
  Zählung unberührter Zeilen intakt (Burgunder 40 → 41 bei neuer Meldung).
  `data/state` selbst unangetastet (byte-identisch verifiziert) — **die
  Bereinigung der Live-Datei macht der nächste Nachtlauf**, dokumentiert in
  der Docstring. Protokollzeile je Filterlauf: „N Tarif-Titel … gefiltert".
- Nebenbei beobachtet, nicht angefasst: die Pipeline-Logzeile „N Titel ohne
  Katalogtreffer" kann „Tarif S" weiter nennen (Filter wirkt auf die Datei,
  wie im Auftrag). Falls gewünscht, eine Zeile für Lead/P5-1.

## 2. Familien-Anker für iPad / Watch / AirPods

- **Lücke gemessen:** Vodafone nennt iPads im `modelName` OHNE Hersteller-Präfix
  („iPad Pro 11 (2025)", „iPad (2025)", „iPad Pro 11 2024"); Serie „iPad"/"iPad
  Pro" in keinem Katalog-Eintrag → `schale` lief None (Anker-Lücke, auto-doku).
- **Regel (`_FESTE_FAMILIEN` + `_anker_treffer`):** Erstsegment der normalisierten
  Serie `ipad`/`watch`/`airpods` → Apple — Markennamen-Fakt, keine Raterei.
  Greift NUR, wenn der Katalog die Reihe gar nicht kennt: eindeutige Katalog-
  Zuordnung schlägt (auch anderer Hersteller, gemessen: Samsung „Watch 8" →
  Samsung), zweideutige bleibt Verwurf (None, fail closed). `schale` und
  `_generation` fragen dieselbe Stelle (keine zweite Anker-Wahrheit).
- **Messung am echten Katalog:** keine Serie mit Erstsegment ipad/watch/airpods
  außer Apple (watch-s/-series/-ultra, airpods → Apple, aus dem Auto-Bestand).
  Alle 3 echten iPad-Namen → `('Apple', Name)`; `lege_an` legt an mit
  `auto:`-Marker, `marktstart`/`vorgaenger` leer, `generation` 11 (Ziffer im
  Namen). E2E: der zusammengesetzte echte Titel „iPad Pro 11 (2025) 256 GB
  Silber" trifft danach `apple-ipad-pro-11-2025`.
- **Ehrlich geblieben:** „HMD Fusion X1" und „GigaCube 5G" (echte Titel) bleiben
  Anker-Lücken in der Arbeitsliste — nicht jede unbekannte Benennform wird ein
  Eintrag (Test nagelt es fest).
- **Hand schlägt Auto:** unverändert — Katalog-Vorrang gilt in beide Richtungen
  (eindeutig wie zweideutig), Kollisionswaechter unberührt.

## 3. Tests (echte Titel, nichts erfunden)

9 neue Tests in `tests/test_geraete_autoerkennung.py` (35/35 grün):
Einzelwerte, Nicht-Speichern, Bestands-Bereinigung beim nächsten Schreiben,
**Wahrheitsprobe über alle 145 echten Titel** (Fixture
`tests/fixtures/geraete/unbekannte_titel_2026-09-17.jsonl`,
145 Zeilen, sha256 in `_herkunft.json` registriert), iPad-Anlage, E2E-Titel,
Watch/AirPods, Katalog-Vorrang beide Richtungen, HMD/Router-Bleiben-Lücken.

## 4. Suite

- `tests/test_geraete_autoerkennung.py`: **35 passed** (26 alt unberührt + 9 neu).
- Geraete-Komplex (`-k "geraete or autoerkennung"`): **1499 passed / 2 failed /
  6 skipped**. Beide Rot vorbestehend, keine Kette von mir berührt:
  1. `test_geraete_lifecycle::test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen`
     — das dokumentierte Dauer-Rot (CLAUDE.md 8a), liest echten State.
  2. `test_geraete_adapter_netzbetreiber::test_tablets_und_router_bleiben_draussen`
     — fällt am **Samsung Galaxy Tab S11 Ultra** (Auto-Eintrag des 17.09.-
     State-Commits im echten Katalog), NICHT am iPad. Prämisse („Katalog
     verfolgt Smartphones") ist durch E4-Auto-Einträge überholt; FM 6.4 sagt
     Tabs/Watches in den Katalog → Konflikt gehört P5-Auftrag 1 / Lead, nicht
     E3 (habe ihn bewusst nicht gedreht).
- Kein `render_site`-Lauf: E3 ändert keine Seite (Sammel-Schicht + Tests).
- Parallel-Agenten im selben Baum (Ausfall-Alarm, Provider-Proben, Fragment)
  — deren Dateien unberührt gelassen.
