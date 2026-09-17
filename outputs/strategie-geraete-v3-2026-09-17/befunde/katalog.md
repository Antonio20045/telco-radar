# Befund: Gerätekatalog + TCO-Liste (Recon, 17.09.2026)

Alle Zahlen an `site/geraete.html` (live = Repo, beide 1.406.611 Byte), `data/state/geraete_db.json` (updated 2026-09-17, 682 Listungen) und `data/state/geraete_tco.json` (792 Bündel / 45 SIM-only) gemessen.

## 1. Warum der Katalog „keinen Preis" zeigt

**Messung (gerenderte Seite, Reiter 4 `#gr-katalogtabelle`):** 566 Zeilen, davon **530 mit Preis** (`data-s-preis` gefüllt), **36 „ohne Preis"**, 0 Zuzahlung. Von den 12 ohne Deckel sichtbaren Standardzeilen haben 11 einen Preis (nur „Nothing Phone (3) · 1&1" ohne).

**Messung (heutige DB, `katalogzeilen()` nachgerechnet):** 636 sichtbare Listungen (aktiv 622 + vermutlich ausgelistet 14) → 636 Zeilen, **599 mit Preis, 37 ohne — alle 37 bei 1&1**. 644 der 682 Listungen tragen `preis_ohne_vertrag` (Optional-Feld `Listung.preis_ohne_vertrag`, `geraete_model.py:1033`). Differenz 566 vs. 636: Seite wurde um 12:59 aus einem älteren DB-Stand gerendert (im Einzelnen n. z.).

**Warum Antonios Eindruck trotzdem richtig ist — drei gemessene Gründe:**
1. **Die Tabelle ist LISTUNGS-Ebene, nicht Modell-Ebene.** 566 Zeilen zu nur **111 Modell-Blöcken** (Gerät+Speicher; Blockgrößen 1–24 Zeilen). Wer „was kostet das iPhone 17" will, sieht 24 Farb-/Anbieter-Zeilen, aber keinen Modell-Preis. Eine aggregierte Preis-Aussage je Modell existiert nur außerhalb des Katalogs.
2. **Jedes dritte Modell-Block enthält eine „ohne Preis"-Zeile:** 37 von 111 Blöcken (alle 1&1). Das Hersteller-Interleave verteilt die 1&1-Zeilen zwischen alle Blöcke — beim Scrollen begegnet einem „ohne Preis" ständig.
3. **Der 1&1-Preis existiert, wird aber nicht gezeigt:** alle 38 1&1-Listungen tragen `preis_mit_vertrag_ab` (z. B. 32,99 €) und `tarif_referenz`; die Vorlage (Zeilen 640–645) zeigt nur `z.preis`/`z.zuzahlung` — bewusste Regel (Preisarten nie mischen), aber die Zeile sagt „ohne Preis" statt „nur im Bündel, ab 32,99 €/Monat". Der Bündelsatz steht längst in `geraete_tco.json` (74 1&1-Bündel).

**Ehrliche Aggregation je Modell (Preis ist da, nur nicht gerechnet):**
- Repo-Präzedenz für „ab X €": `radar.ohne_vodafone[].ab_preis` (günstigster Anbieter MIT Namen, Modell-Ebene) und `geraete_vergleich` (je Modell+Speicher+Zustand eigener Preis, günstigster Wettbewerber mit Name, Δ absolut/%, `VERGLEICHBARE_ZUSTAENDE=('neu',)`).
- Empfehlung: **„ab X € bei Y"** = min über NEU-Listungen (`barpreise()` liefert je (sku, anbieter) Beleg mit Betrag+Quelllink+Datum), dazu Anbieterzahl; **Zustand im Schlüssel** (refurbished nie mit neu mischen — Hausregel B1). Spanne nennen, kein Mittelwert: 110 der 111 Blöcke haben ≥1 Barpreis; nur der Apple-Watch/AirPods-Rest (19 Blöcke) bzw. reine 1&1-Modelle brauchen den Leerzustand „kein Barpreis gemessen — nur im Bündel (ab Z €/Monat)".

## 2. TCO je Modell — Stand und Felder

**Zählung (`geraete_tco_view.aufbereiten` auf echtem State):** **97 Modelle** (device_id+Speicher) in der TCO-Ansicht, **alle 97 mit ≥1 belastbarer Karte**, **96 mit vergleichbarer Karte** (TCO-Leitzahl `gesamt`), **68 mit Vodafone-Referenz**. Bündel je Anbieter: Vodafone 473, congstar 128, 1&1 74, o2 72, Telekom 45. Schnittmenge Katalog↔TCO: **92 von 111 Katalog-Modellen haben TCO; 19 nur Katalog** (iPhone 16e, Pixel 10, AirPods, Watches, iPhone 18 Pro/Pro Max — die E4-Auto-Erkennung), **5 nur TCO** (Bündel ohne aktive Listung).

**Felder je Karte (`_karte`, alle schon gerechnet):** `gesamt` (TCO-Leitzahl), `laufzeit` (24/36 → Etikett TCO-24/TCO-36), `schnitt_monat` (Ø €/Monat), `gezahlt_nach_24`, `offen_nach_24`, `delta`/`delta_kurz` (zu Vodafone-Referenz), `anbieter`, `band`, `zustand`, `belastbar`/`vergleichbar`, `quelle_url`. Modell-Ebene: `spanne`, `laufzeiten`, `bundle_anbieter`, `referenz`, `titel`.

**TCO-Spalte je Modell ohne Raten:** „TCO-24 ab 1.573 € (congstar) · Ø 65,54 €/M." — alles aus min über vergleichbare Karten (Beispiel gemessen: Galaxy Z Fold8 256). Leerzustände benannt: „kein Bündel gemessen" (19 Modelle) und „keine Vodafone-Referenz" (29 Modelle) — `delta` nur wo `referenz` existiert, nie aus Näherung ohne Beleg.

## 3. Umschalter „Einzelgerätpreis ↔ TCO" in EINER Tabelle

**Vorschlag Spalten (Feldnamen aus dem Code):**
- Ansicht **Einzelgerätpreis** (Modell-Ebene): `titel`/`speicher` · ab-Preis (min `barpreise`, neu) · günstigster `anbieter` + Quelllink · Anbieterzahl · Spanne (nur wenn wesentlich)
- Ansicht **TCO**: `titel`/`speicher` · TCO-24 ab (`gesamt` min, vergleichbar) · `anbieter` des Besten · `schnitt_monat` · `delta_kurz` (nur mit `referenz`) · `band`
- Sortierung nach Rohwert wie heute (`data-s-*`); Zeile ohne TCO ohne Schlüssel, ans Ende (bestehende Regel, Vorlagenkommentar Zeile 588). Beide Ansichten teilen Schlüssel `modell_schluessel(device_id, speicher)`.

**Sortierung/Filter:** Marke/Speicher-Filter bleiben (aus `hersteller`/`speicher`). Anbieter-Filter nur in der Barpreis-Ansicht Listungs-scharf; in der TCO-Ansicht heißt „Anbieter" „bester Anbieter" — entweder Anzahl je Modell oder Filter über `bundle_anbieter`. **Zustandsfilter muss in der TCO-Ansicht auf `neu` fixieren** (Zustand ist im TCO-Kartenschlüssel; „erneuert" als Sieger war B1).

**Was bricht (nachgeschlagen):**
- `tests/test_geraete_seite.py` — 19 Stellen `katalogtabelle/katalogzeilen`; am härtesten: Spaltenkopf-Assert `kopf == ["Gerät","Farbe","Anbieter","Preis","Zustand","Verfügbar","Abgerufen"]` (~Zeile 776) und die Zeilenzahl-Asserts (457/484): **„Zeilen == `_bestand_ids()`" nagelt die Listungsebene fest** — bei Modell-Ebene neu zu schreiben (Zeilen == Modellzahl).
- Deckel-Logik `KATALOG_SICHTBAR=12`/`BLOCK_SICHTBAR=2` samt Block-/Interleave-Tests (`test_katalogzeilen_*`, 5 Stück) — entfallen oder werden Modell-scharf neu gebaut.
- `tests/test_geraete_leer_zustaende.py` (Katalog leer), `tests/test_geraete_reiter_browser.py` (Browser je Reiter), `pruefe_portal.py` Kriterium 11b (Reiterhöhe ≤ 3000 px) + `data-tafel`-Reihenfolge (Zeile ~704).
- NICHT brechen: `test_geraete_faden.py` / `test_geraete_o3_rollen.py` (nur Reiterliste, Reitername „Gerätekatalog" bleibt).
- Export: `geraete-aktuell.csv` (`aktuell_csv`) ist die Listungs-Tabelle als Export — E5-Regel „4/4 Zahlensektionen exportierbar": beide Ansichten exportieren (oder eine Modell-CSV fünft).

## 4. Dopplung Katalog ↔ Vergleichs-Reiter („Mischmasch", gemessen)

**Vier Modell-Zugänge auf EINER Seite:**
1. **Vergleich** (`tafel-tco`): Suchfeld mit Zähler „**88 Modelle**" (gerendert; heute 97) + **6 Geräte-Kacheln** (`zr.kacheln`: iPhone 17 Pro 256, Z Fold8 256, S26 Ultra 256, iPhone 17 Pro 512, iPhone 17 256, Pixel 11 256) + Zeitreihe + Bündel-Tabelle je Modell.
2. **Radar** (`tafel-radar`): „Alle Modelle nach Abweichung zu Vodafone" mit **321 Statuszeilen** (138 vergleichbar, 173 kein_buendel, 6 band_mismatch, 4 nicht_vergleichbar; plus 44/83 Aufklapperzeilen) — Modell-Liste mit Sprung in den VERGLEICH (nicht in den Katalog).
3. **Katalog**: 566 Listungszeilen / 111 Modell-Blöcke — dieselben Modelle, anderer Schlüssel (Listung statt Modell), ohne TCO.
4. **Preisverlauf**: eigene Modell-Wahl + Graph (Detail beim Preisverlauf-Agenten).

Drei verschiedene Modell-Mengen (88/97 · 111 · 321(=Modell×Band)) und zwei verschiedene Schlüssel auf derselben Seite — das ist der objektive Kern von „kein roter Faden". Katalog („Was wo im Regal steht") und Vergleich („Was kostet es über 24 Monate") beantworten verschiedene Fragen, präsentieren sich aber als zwei unverbundene Tabellenwelten. **Antonios Umschalter macht den Katalog zum EINEN Modell-Einstieg; Konsequenz:** Radar-Modellliste und Katalog-Modellansicht müssen denselben Schlüssel (`modell_schluessel`) und dieselbe Menge zeigen (oder die Radar-Liste springt in den Katalog statt in den Graph); die 6 Kacheln bleiben Schnelleingang, nicht zweite Liste.

## Stolperfallen für die Umsetzung (aus Repo-Regeln)

- Neue Zahl auf der Seite → `tests/test_seiten_zahlen.py` (Hausregel; dort fiel zuletzt „2454 Modelle" durch `get_text(" ")`-Trenner auf — Zahlen OHNE Trenner lesen).
- Zwei Preisarten nie mischen (`VERGLEICHBARE_ZUSTAENDE`, Bündelmonatspreis ≠ Barpreis); „ohne Preis" durch benannten Zustand ersetzen („nur im Bündel ab X €/Monat"), nie durch Raten.
- Deckel in Zeilen ist Stellvertreter für Pixel: nach Umbau Reiterhöhe 11b nachmessen.
- 1&1 hat 74 Bündel — die „ohne Preis"-Zeilen sind durch TCO-Anbindung heilbar, ohne den Barpreis zu erfinden.
