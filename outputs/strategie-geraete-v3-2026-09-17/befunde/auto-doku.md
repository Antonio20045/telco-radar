# Befund: Auto-Erkennung (E4) + Doku-Zustand Geräteseite

Alle Zahlen am 17.09.2026, ~14:00 Ortszeit, gegen HEAD `9f5235d` gemessen.
Quelle der heutigen Laufdaten: Bot-Commit `1dd48d4` (17.09. 08:59 UTC, geraete.yml-Nachtlauf).

## 1. Stand Auto-Erkennung E4

**Mechanik (`autoerkennung.py`, 384 Zeilen):** Auslöser ist allein der
strukturierte Name am Rohsatz (`strukturierter_name`: Telekom `name` in
`telekom.py:292,436`, o2 `description` in `o2.py:183,353`, Vodafone `modelName`
in `vodafone.py:222,325`) — nie der Titel. Schälung: Hersteller-Präfix, sonst
Serien-Anker aus dem Katalog (eindeutige Baureihe → Hersteller); Speichersegment
(mit Einheit) und Funk-Anhängsel (5G/4G/LTE, E4-P1) fallen weg; ≥2 Wortmarken.
`generation` nur bei im Katalog bekannter Serie. `marktstart`/`vorgaenger`
bleiben leer. Kollisionswächter: Hand schlägt Auto (device_id + fuzzy
Stamm-Richtung, Modellzusatz-Falle). Persistenz: State
`geraete_katalog_auto.json`, gemerged in `lade_katalog` (`geraete_config.py:225`)
— auch der Renderer sieht Auto-Einträge.

**Heutiger Lauf (Korrektur zu CLAUDE.md „0 Auto-Einträge"):** Der Nachtlauf vom
17.09. hat **16 Auto-Einträge** angelegt, u. a. **iPhone 18 Pro, iPhone 18 Pro
Max** (je 256 GB), Galaxy Tab S11 Ultra/S10 FE/A11+, XCover7 Pro EE, Apple
Watch S12/Ultra 4/Series 12, AirPods 5, Pixel Buds Pro 2. Die CLAUDE.md-Aussage
(„kein iPhone-18-Titel kam an") ist **überholt** — sie beschreibt offenbar den
Stand während des Laufs; der Bot-Commit (11:59 Ortszeit) liegt vor dem
CLAUDE.md-Commit (13:05).

**Unbekannte (`geraete_unbekannt.jsonl`, 284 Zeilen):** 145 Titel, 139 Farben.
Anbieter: mobilcom-debitel 89, congstar 60, Vodafone 42, 1&1 29, o2 28, ALDI
TALK 28, Saturn 8. Top-Titel: ALDI-Talk-**Tarife** S/M/L (je 29x = 87 Zeilen —
keine Geräte, Rauschen in der Arbeitsliste), Vodafone iPad Pro 11/13 + iPad
(2025) und HMD Fusion X1 (Bündel-Titel), o2-Watch-Titel, 1&1-Doppelmarken
(„Samsung Samsung Galaxy…"). Top-Farben: Burgunder 94, Polar 40, Sky Blue 35,
Cream 30 — **das sind die iPhone-18-Farben**; sie laufen als „unbekannt", die
SKU bleibt trotzdem stabil (unbekannte Farben werden bewahrt). Auto-erkennbar
wären die iPad-/Watch-Titel (strukturierter Name, Hersteller-Präfix Apple) —
Watch-Modelle wurden heute tatsächlich auto-angelegt; die iPad-Titel sind die
genannten Anker-Lücken-Kandidaten.

**Kette „neues iPhone kommt automatisch rein" — Stand je Glied (gemessen):**

| Glied | Stand 17.09. |
|---|---|
| Strukturierter Name → Katalog auto | **greift** (16 Einträge heute, über Vodafone/congstar/1&1-Bündelnamen) |
| Katalog auto → Bündel | **greift**: 105 iPhone-18-Bündel in `geraete_tco.json` (Vodafone 49, congstar 48, 1&1 8), first_seen 17.09. |
| Bündel → Historie | **greift**: 105 Zeilen `geraete_tco_historie.jsonl` mit datum 2026-09-17 — **Tag 1 ist gespeichert** (der Telekom-15.09.-Fehler „Tag 1 nie gespeichert" ist im TCO-Weg behoben) |
| Sichtbarkeit | **BRICHT heute (by design)**: `AUTO_SICHTBAR_AB_MESTAGEN = 2` (`geraete_zeitreihe.py:672-679`) — heute 1 Messtag → iPhone 18 steht in **keinem** Reiter, **keinem** Export: 0 Vorkommen in `site/geraete.html`, `site/data/geraete-zeitreihe.html`, `geraete-buendel.html` und allen 4 CSVs (gemessen). Erst der Nachtlauf am 18.09. macht es sichtbar. |
| Listungen (Barpreis) | fehlt komplett: 0 iPhone-18-Listungen in DB/CSV (nur Bündel). o2-hwOnly liefert keine 18er (warum: n. z.) |
| Telekom | **Nicht in Actions**: unverändert HTTP-202-Challenge aus dem Actions-IP-Bereich (in `geraete_quellen.yaml` wörtlich dokumentiert); DB `letzter_lauf: 2026-09-15`. Telekom-Daten kommen nur über das **lokale** `scripts/lokallauf_telekom.py` (Commits „telekom: Tageslauf") — manueller Nebenpfad. |

## 2. iPhone-18-Live-Beweis (CLAUDE.md 8a OFFEN 1)

Ausständig, konkret:
1. **Ein weiterer Nachtlauf** (18.09.) → 2. Messtag → iPhone 18 erscheint in
   Zeitreihen-Wahl (169 `data-modell` heute im Fragment), Vergleichs-Tafel und
   Exporten. Dann Live-Sichttest analog E6: „iphone 18" suchen → Vorschau →
   Band → Antwort-Satz → Deep-Link `?modell=apple-iphone-18-…&band=…`.
2. **Telekom bleibt draußen** (202-Challenge): der E4-Belegfall lief
   ausschließlich lokal (15.09.). Solange `lokallauf_telekom.py` Handarbeit
   ist, ist die „Automatik" für den Anbieter Rang 1 manuell — größter
   Einzelhebel gegen Antonios „nie wieder was dran ändern". (Umgehungsfrage R3 in
   `STRATEGY_GERAETE_TCO.md` bleibt Antonios Entscheidung.)
3. **Arbeitsliste** = `geraete_unbekannt.jsonl` (Zahlen oben): iPad-Titel als
   nächste Anker-Lücken; ALDI-Tarif-Rauschen gehört gefiltert, nicht gepflegt.

## 3. CLAUDE.md: Widersprüche / überholte Schichten (nur Geräteseite)

Fallstricke (§6: Sägezahn-ID, 202-Challenge, Zustandsdimension, robots,
min-Auswahl) bleiben unberührt gültig — **nicht** streichen. Überholt:

1. **Reiterstruktur in 3 Schichten unmarkiert:** §5-Zeile „TCO-first seit
   04.09." nennt Reiter „TCO-Vergleich·Katalog·Preis-und-TCO-Historie·Portfolio"
   (Phase R); §8a Phase R/R2/R3 beschreiben nochmal ältere Formen; gültig ist
   E2/E3: Hauptansicht = TCO-Zeitreihe, Reiter = Vergleich·Radar·Preisverlauf·
   Gerätekatalog, `wettbewerbsradar.html` = Redirect, Nav 8→7 (7 n. z. selbst
   gezählt). §5 verweist mit „Einzelheiten in §8a" in alle Schichten.
2. **Navigation:** §5-Veröffentlichungsschwelle-Block endet bei „sechs
   Einträge" (Newsletter) — E3 sagt 7; älterer Block „fünf + Geräte" ebenso
   überholt.
3. **„Telekom bleibt leer bis Phase T"** (§8a Phase R OFFEN 1 + „59
   Leerzustände"): überholt — Telekom seit 04.09. angebunden
   (`telekom_kategorie`, 6 Einstiege), **45 Telekom-Bündel im Bestand**;
   richtig bleibt nur die 202-Grenze in Actions.
4. **Positionskarte-Absätze (§5, „am 11.08. neu gebaut" + Regel-Tabelle):**
   `geraete_karte.py` ist seit 30.08. **gelöscht**; nur die Tabellenzeile
   „Stand DAVOR" markiert das. Als Lehre behalten (Y-Achse-Regel), aber
   Existenz-Kontext fehlt.
5. **G1/G2-Beschreibungen (Phase R, Reiterhöhen 2090/1873/1872/1883):** durch
   E2 ersetzt (Zeitreihe Hauptansicht, Kriterien 11/11c umgestellt; E3:
   Barpreis-Reiter).
6. **Export-Stelle:** §5-Zeile „Vergleich und Export (29.08.): zwei Sektionen
   unter der Preisgrafik" — überholt durch E5 (vier Knöpfe in der Kopfzeile,
   4/4 Sektionen, `wettbewerbsradar.csv` behält Namen).
7. **„0 Auto-Einträge"** (§8a Fazit des ersten Laufs): überholt, s. oben — 16
   Einträge am 17.09., 11:59 UTC committet.
8. **Seitengröße:** „1,39 statt 0,91 MB" (Phase R OFFEN 4) — heute 1,36 MB
   HTML + Fragmente 1,07 MB (Zeitreihe) + 1,17 MB (Bündel). PM-6-Thema bleibt.

## 4. OFFEN 1–5 aus §8a, bewertet für „nie wieder ändern"

| # | Punkt | Bewertung |
|---|---|---|
| 1 | iPhone-18-Live-Beweis | **Kern.** Automatik ist bis Store bewiesen; Sichtbarkeit braucht 1 Lauf. Telekom-202 bleibt die größte Handarbeit (lokaler Tageslauf). |
| 2 | Sichtbarkeit rechnet nur gegen Bündelweg | **Relevant.** 12 der 16 heutigen Auto-Einträge (Watches, Tabs, AirPods, Buds) haben **keine** Bündel → erscheinen nie in der Zeitreihe; Barpreis-only-Modelle ebenso. Katalog-Reiter zeigt sie ab Tag 1 — aber nur mit Listung. |
| 3 | Fragment-Größe (PM-6) | **Relevant für Dauerbetrieb:** Zeitreihen-Fragment 1,07 MB, Bündel 1,17 MB, wächst je Messtag; ohne Deckel bricht „nie wieder ändern" an der Ladezeit. |
| 4 | S4-Rest (Export-Knopf-Einheiten, 2 Leer-Tests) | Kosmetik. |
| 5 | Monatliche Sichttests + 3 Protokollzeilen | Übergang: Sichtfragen gehören in `pruefe_portal.py`/Tests überführt; Protokollzeilen (Auto-Anlage, Unbekannte, Fragmentgröße) sind die Frühwarnindikatoren — mittlere Relevanz. |
