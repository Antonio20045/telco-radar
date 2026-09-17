# Befund Reiter „Preisverlauf" (geraete.html) — Recon, 17.09.2026

Messbasis: `site/geraete.html` (Stand E5, Commit `35b777e`), `data/state/geraete_preise.jsonl` + `geraete_db.json` (nur gelesen). Der Reiter hat zwei Bausteine: **G2** (servergerenderte Markt-Historie oben, `geraete_tco_grafik.historie`, `MAX_REIHEN = 5`) und den **Modell-Wähler** unten (`geraete_verlauf.aufbereiten` + `app.js`). Der dritte Graph (G0) ist mit dem E3-Fix vom 17.09. bereits gefallen — Kommentar in `geraete.html.j2:749`, in `site/` nicht mehr vorhanden (nachgezählt: 0 Vorkommen `gr-g0`).

## 1. Der „erste Graph" ist G2 — und er zeigt faktisch ZWEI Kurven

**Auswahlregel** (`geraete_tco_grafik.py:929,1028`): Reihen mit Bewegung vor flachen, größte Bewegung zuerst (`_reihenrang`), Deckel `MAX_REIHEN = 5`. Grundmenge: alle Reihen mit ≥ 2 eindeutigen Messtagen. **Eine G2-Reihe ist je LISTUNG (Farbe), nicht je (Modell, Anbieter)** (`geraete_tco_karten.historienreihen`, Schlüssel `listung_id`).

**Gezählt aus site/geraete.html (nicht aus dem Code geschlossen):**

| Messung | Zahl |
|---|---|
| SVG vorhanden | 1 (`svg.gr-g2`, viewBox 0 0 1180 300, 5,4 KB) |
| Gezeichnete Linien (`<path>`) | 5 |
| **Verschiedene Kurven darin** | **2** — 3× iPhone 17 Pro Max 2048 GB mobilcom-debitel (2.449 → 3.099 €, +650 €), 2× iPhone 17 Pro 1024 GB mobilcom-debitel (1.799 → 2.199 €, +400 €) |
| Anbieter im Bild | nur mobilcom-debitel (alle 5 Linien; SVG-Klassen bestätigen) |
| G2-Tabelle darunter | 5 Zeilen, davon 3 + 2 identische Dubletten |
| Grundmenge (Unterschrift) | „5 von 124 Reihen" |
| Grundmenge eigene Nachzählung | 127 (ohne Bereinigungsfilter des Views; Seiten-Zahl 124 = bereinigte Menge) |
| Bewegte Reihen | 123 von 127 (Historie schreibt nur Änderungspunkte → fast jede Reihe mit 2 Tagen ist bewegt; „Bewegung zuerst" selektiert hier faktisch nach **Größte Bewegung**) |

Antonios Eindruck „hartkodiert iPhone 17 Pro / Pro Max" ist also explained, nicht hartkodiert: +650 € und +400 € sind die größten Bewegungen des Bestands, und je Farblistung wird dieselbe Kurve mehrfach gezeichnet und belegt alle 5 Deckelplätze. Der Markt-Blick funktioniert so nicht — das Bild sagt weniger als der Satz darunter.

## 2. Text im Reiter (Ausgangszustand, ohne Auswahl)

6 sichtbare Textblöcke mit zusammen **194 Wörtern** (8+31+41+78+16+20), dazu Aufklapper „Daten dieser Kurven" (Tabelle):

1. `h2.rubrik`: „Wie sich der Barpreis eines Geräts entwickelt hat" (8 W.)
2. `p.gr-erklaer` ÜBER der Grafik: „Die Kurve zeigt den Barpreis ohne Vertrag, nicht die …" (31 W.)
3. `figcaption` (an der Grafik): „5 von 124 Reihen mit mindestens zwei eindeutigen Messpunkten …" (41 W.)
4. `p.gr-g2-ereignisse` UNTER der Grafik: „Erhöhungen und Senkungen im Messzeitraum, über alle 124 Reihen: … und 133 weitere." (78 W.!)
5. `p#gr-vleer`: „Wählen Sie oben ein Gerät – dann steht hier sein …" (16 W.)
6. `p#gr-vstand`: „Preisverlauf wird seit dem 10. August 2026 erfasst – 20 Messtermine …" (20 W.)

Blaock 4 ist der „mehr Text als Graf"-Treffer: 78 Wörter Ereignis-Aufzählung neben einer Grafik mit 2 echten Kurven. Nebenbefund: Der Satz nennt Ereignisse vom **16.09.**, die gezeichnete Achse endet am **11.09.** (Ereignisse rechnen über die Grundmenge, von/bis über die gezeichneten 5 Reihen — gewollt laut F-R2-1, liest sich aber als Widerspruch).

## 3. Dieselbe Aussage? Ja im Kern — Empfehlung: G2 löschen, Wähler nach oben

Beide zeigen den **Barpreis über Zeit** aus **derselben Datenquelle** (`geraete_verlauf.messtage` wird von `historie()` importiert; `reihen_fuer_listungen` ist der gemeinsame Weg). Unterschied: G2 = „markweiteste Bewegungen, Top 5 nach Größe, ohne Klick"; Wähler = „ein Gerät, alle Anbieter, Zeitraum (Woche/Monat/Quartal, Von/Bis), Kacheln, Tabelle". Der Markt-Blick von G2 ist in der heutigen Datenlage entwertet (2 Kurven, 1 Anbieter) und seine Information steht vollständig im Ereignis-Satz; „wo steht wer im Preis" beantwortet zudem die Radar-Tafel (Alarme/Abweichung). **Nichts geht verloren, wenn G2 fällt** — Präzedenz: G0 fiel am 17.09. mit derselben Begründung (Doppel-Darstellung §4.6/4.8), Antonios Forderung 4 deckt das Wort für Wort.

**Konsequenzen des Löschen + Hochziehens:**
- Vorlage `geraete.html.j2:780–853`: `figure.gr-grafik--g2`, figcaption, `g2_ausgelassen`, Ereignis-Satz, `details#gr-g2-tabelle` fallen; Reihenfolge „Suchfeld → Zeitraum → Kacheln → Diagramm → Tabelle" steht bereits als Regel im Reiter-Kommentar — der Wähler rückt nur hinter die h2.
- Code wird tot: `geraete_tco_grafik.historie/_ereignisse/_reihenrang/MAX_REIHEN` (~200 Zeilen) und `geraete_tco_karten.historienreihen` (~45 Zeilen) verlieren den Vorlagenleser → nach E5-Regel mit wegwerfen (Präzedenz `setzeG0`). `geraete_verlauf.messtage` bleibt (Wähler nutzt es).
- Tests berührt: `test_geraete_preis_mehrdeutig.py` (G2-Teile, ~5 Tests), `test_geraete_tco_hauptansicht.py` (3 G2-Tests). **Nicht** berührt: `test_geraete_verlauf.py` (21 Tests, alles Wähler-Rechnung), `test_geraete_o3_rollen.py` (bleibt grün: `#gr-verlaufdaten` genügt).
- `pruefe_portal.py` 11: Bedingung ist `svg.gr-g2` **ODER** `#gr-verlaufdaten` → bleibt grün, nur Kommentar/Name anpassen. Kriterium 11c misst `#tafel-tco` (Hauptansicht) — unberührt.
- Export „Preishistorie" (CSV) läuft über `geraete_export`, nicht über G2 — bleibt.

## 4. Was dem Wähler als Hauptinhalt im Weg steht

**Datenlage (aus dem Seiten-JSON `#gr-verlaufdaten`, 89 Geräte gezählt):** alle 89 haben ≥ 2 Messtermine; **47 von 89 (53 %) erreichen die Diagramm-Schwelle 4** (Verteilung: 2×26, 3×16, 4×19, 5×14, 6×6, 7×4, 8×2, 9×1, 10×1). Meistgemessen: iPhone 17 256 GB (10 Termine, 6 Anbieter) — steht durch Sortierung nach `-messpunkte` schon an erster Stelle der Trefferliste.

Hindernisse, alle klein:
1. **Keine Vorauswahl**: `app.js` initialisiert `gewaehlt = null` — der Reiter startet mit Satz statt Bild. Ohne Vorauswahl wäre der Reiter nach G2-Löschung im Ausgangszustand grafiklos (für 42/89 Geräte der Suche gilt dasselbe, selbst gewählt). Lösung: erstes Gerät der Liste automatisch wählen (1 Zeile) oder Deep-Link wie im Vergleichs-Reiter. Das kippt bewusst die B4-Regel „ohne Auswahl kein Diagramm" — von Antonios Forderung 4 gedeckt.
2. **3 Browser-Tests nageln den Leer-Satz fest** (`test_geraete_reiter_browser.py:954,1125`, `test_geraete_o3_rollen_browser.py:361` — „Wählen Sie oben ein Gerät" sichtbar) → mit Vorauswahl anpassen.
3. Erklär-Absatz (31 W.) und Stand-Satz (20 W.) müssen bei der Neuanordnung fallen oder in einen Aufklapper wandern — sonst bleibt der Reiter-„Mischmasch", den Antonio meint.
4. Kein Gewichtsproblem: der 105-KB-JSON-Knoten existiert schon; PM-6 (Fragmentgröße) betrifft die Zeitreihe, nicht diesen Reiter.

**Kurzfazit:** Forderung 4 ist billig umsetzbar und gut begründbar — G2 löschen (toter Code mit weg), Wähler mit Auto-Vorauswahl (iPhone 17 256 GB) an die Spitze, 4 der 6 Textblöcke fallen mit G2 von selbst.
