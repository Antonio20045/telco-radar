# B-2 — Bündelerhebung Telekom: Gerät × Tarif (08.09.2026, abends)

Auftragsgrundlage: `BRIEF_B2_BUENDEL_TELEKOM.md`. Aufsetzend auf den
gesicherten Rettungsstand `88abc8e` (Auto-Commit 11:23 Uhr: Telekom-
Bündeladapter, 14 Tests grün, reale komprimierte Fixture). Der Adapter
war gebaut und getestet — dieser Bericht holt die Schritte nach, die der
Rettungsstand nicht mehr erreichte: den echten lokalen Lauf, den
Laufzeitbeleg, den Commit der Daten, das Rendering, die Vollsuite.

## Ergebnis in einem Satz

**45 Telekom-Bündelsätze** (5 MagentaMobil-Tarife × 9 Geräte, vorher 0)
im selben Bestand wie Vodafone (338) und o2 (63); Laufzeitbeleg
**7 von 7 Requests** mit `TelcoRadar/1.0`, `browser=false`; der
Wettbewerbs-Radar führt Telekom als **9 Vergleichspaare** (8 davon
teurer als Vodafone, das Xiaomi 17T Pro als einziges günstiger);
Vollsuite **2 failed / 2829 passed / 14 skipped** — nur die zwei
vorbestehenden Promo-Screenshot-Roten.

## Recherchebefund — welche Quelle, und warum

Die Recherche stammt aus der geretteten Session und ist im Modulkopf von
`src/telco_radar/collect/geraete/telekom.py` festgehalten; dieser Lauf
hat sie live bestätigt. Der Kern:

1. **Nicht die Produktseite, nicht das Produktinformationsblatt.** Die
   Produktseite trägt je Speicherstufe nur einen `deltaPrice` (Aufschlag
   ohne Grundbetrag, T2-Befund), und PIBs liefern keine Bündel-
   Kombinatorik — beide Prüfungen des Briefs (a) und (c) fallen negativ
   aus, wie vorhergesagt.
2. **Die Kategorieseite selbst ist der Bündelkatalog** (Prüfung (b),
   erweitert): `/shop/geraete/smartphones?tariffId=MF_<id>` liefert je
   Tarif eine komplette andere Preisstruktur — Zuzahlung, Geräterate
   und Ratengesamtbetrag sind je Tarif andere. Der Parameter steht in
   ihrem eigenen Pagination-Link, die fünf Werte (XS=MF_17779 …
   XL=MF_17803) nennt die Tarifübersicht im „Tarif auswählen"-Link je
   Kachel. **Nichts davon ist geraten** — dieselbe Regel wie bei o2.
3. **Der Tarifname steht in derselben Antwort** (`productList.
   selectedPlan.name`, mit `id` und typisierten Preisen für Anschluss-
   und Monatsgebühr) — deshalb braucht Telekom anders als Vodafone
   keinen zweiten Endpunkt und keinen `loese_tarifnamen`-Haken.
4. **Zwei Nachrechnungen sind Bedingung, nicht Protokoll** (beide im
   Adapter, beide an der echten Antwort geprüft): die Ratenprobe
   `upfront + n × Rate == totalPrice` und die Plan-Probe — der je-Gerät-
   Tarifpreis (`formattedPrices.recurringTariffPrice`) muss über seine
   Preis-ID zum `selectedPlan` gehören und im Betrag entsprechen. Eine
   Antwort ohne `selectedPlan` (die ohne-vertrag-Seite) wirft, statt ein
   leeres Ergebnis still durchzulassen.

Live-Messung dieses Laufs (19:04 Uhr): **alle fünf Buendel-Seiten HTTP
200, je 10 Einträge, davon 9 Geräte** (eine Werbekachel ohne `name`
fällt weg) — mit dem ehrlichen Absender, ohne Challenge.

## Der Lauf, mit zwei Befunden an sich selbst

**Aufbau:** `scripts/lokallauf_telekom.py` (der etablierte Tageslauf),
in dieser Runde um den T2-Laufzeitbeleg erweitert — derselbe
Protokollhaken wie bei T1 (`resp.request.headers`, `transport=http-get`,
`browser=false`), eigene Datei `beleg-telekom-geraete-<datum>.json`. Der
Haken sitzt um `telco_radar.collect.http.fetch` als Modul-Attribut und
wird nach der Stage zurückgenommen; reiner `httpx`-GET, kein Playwright.

| Lauf | Requests | Befund |
|---|---|---|
| 1. Lauf (19:00) | 7 | **1 von 7 unehrlich**: der robots.txt-Abruf ging mit der globalen Chrome-Kennung aus `settings.yaml` hinaus — alle sechs Seitenrequests waren ehrlich. Der Beleg hat das GEMELDET (`alle_ehrlich: false`), genau wofür er existiert |
| 2. Lauf (19:04) | 7 | **7 von 7 ehrlich** — `alle_ehrlich: true`, jeder Status 200, jeder UA exakt `TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)` |

Der Beleg enthält: 1× robots.txt (301 auf `/content/robots`, gefolgt,
200), 1× Kategorieseite ohne Vertrag, 5× `?tariffId=MF_…`. Versioniert
in `outputs/beleg-telekom-geraete-2026-09-08.json` (committet ist die
Fassung des zweiten Laufs).

**Beleg-Befund 1 — robots.txt trägt jetzt den Absender des Anbieters**
(`1d1c687`): Der robots-Abruf gehört zum Crawl DIESES Anbieters; ein
Anbieter mit `user_agent`-Override bekommt deshalb eine eigene,
provider-bezogene Waechter-Sicht in `sammle_anbieter`. Ohne Override
bleibt alles wie zuvor (die PM-Entscheidung zu `settings.yaml` steht
weiter aus, CLAUDE.md). Ein Saturn-Test hatte das alte Verhalten
ausdrücklich festgenagelt („robots.txt geht über die unveraenderte,
globale Konfiguration") — er hält jetzt das neue fest, mit Begründung.
Regressionstest in `test_geraete_buendel_telekom.py`
(`test_der_robots_abruf_traegt_den_absender_des_anbieters`).

**Beleg-Befund 2 — die Geraete-Aufbereitung riss komplett ab**
(`81b9087`): Das erste Rendering nach dem Lauf meldete
„Geraetedaten nicht aufbereitbar" — der Auffangboden des Renderers,
fünf leere Reiter, Navigationseintrag weg. Ursache: Die Telekom-SIM-only-
Referenz kommt aus der Shop-Kachel (`telekom:magentamobil-l#live_shop`
— die Dublettenregel in `tarif_referenzen.aus_bestand` lässt die Live-
Lesart vorn), das Bündel löst über den PIB-Namen auf den Eintrag ohne
Zusatz. `tco_model.geraeteanteil()` verglich die IDs starr und warf.
**Zwei Lesarten sind zwei Zeitreihen, aber EIN Tarif** — verglichen wird
jetzt die Zeitreihen-Basis, und nur der Preistyp-Zusatz `#live_shop`
fällt dabei weg. Ein HASH-Zusatz (zwei gleichnamige, verschiedene
Produkte, o2-home-l-Falle) trennt weiterhin — dafür gibt es eine
Gegenprobe im Test.

## Vorher / Nachher

| | Vorher (88abc8e) | Nachher |
|---|---|---|
| Bündel gesamt in `geraete_tco.json` | 401 (Vodafone 338, o2 63) | **446** |
| davon Telekom | **0** | **45** (je Tarif 9, Güte `hoch` über den PIB-Bestand) |
| Telekom-Beleglinks | — | je Satz ein tariffId-Tiefenlink (`/shop/geraet/…?tariffId=…`), `abgerufen_am: 2026-09-08` |
| SIM-only-Referenzen | 45 | 45 (unverändert — dieser Lauf ruht `tarife.jsonl` nicht an; T1 lief mit, 14 Dokumente unverändert) |
| Telekom im Wettbewerbs-Radar | nirgends zeichenbar | **9 Vergleichspaare** (Band Klein), 74× ehrlich `kein_buendel` bei Modellen ohne Telekom-Bündel |
| Telekom auf der TCO-Tafel | 59 Leerzustände | 9 Modelle mit je 5 belastbaren Karten, Rest leer mit Satz |
| Laufzeitbeleg T2 | gab es nicht | 7 Requests, 100 % ehrlich |

`geraete_db.json`: ausschließlich Telekom-Zeilen — `laeufe` 6→8 (zwei
Läufe heute), `funde_gesamt` 60→80, 0 neue Listungen, 0 Preispunkte,
0 gealtert; daneben sind die Beleglinks der 10 Bestandslistungen von
OAuth-Query-Rauschen bereinigt (`?autoLogin=true&error=…` entfällt —
die Kategorieadresse steht jetzt direkt in der Konfiguration). Kein
anderer Anbieter berührt (per Diff geprüft, auch `geraete-aktuell.csv`:
nur Telekom-Zeilen).

## Die 9 Vergleichspaare (RAD-1-Leitzahl, TCO-24 im gemeinsamen Band)

| Modell | Telekom | Vodafone | Abweichung |
|---|---|---|---|
| Xiaomi 17T Pro 512 GB | 1.237,35 € | 1.271,79 € | **−2,7 %** (einziger Fall: Telekom günstiger) |
| Samsung Galaxy Z Flip8 256 GB | 1.616,15 € | 1.499,80 € | +7,8 % |
| Google Pixel 11 256 GB | 1.342,95 € | 1.283,80 € | +4,6 % |
| Google Pixel 11 Pro XL 256 GB | 1.616,15 € | 1.571,80 € | +2,8 % |
| Samsung Galaxy Z Fold8 Ultra 256 GB | 2.264,15 € | 1.919,80 € | +17,9 % |
| Samsung Galaxy Z Fold8 256 GB | 2.108,95 € | 1.787,79 € | +18,0 % |
| Apple iPhone 17 Pro 256 GB | 1.570,55 € | 1.559,80 € | +0,7 % |
| Apple iPhone 17 256 GB | 1.416,95 € | 1.391,79 € | +1,8 % |
| Google Pixel 11 Pro 256 GB | 1.536,95 € | 1.439,80 € | +6,7 % |

Alle Paare im Band Klein — Telekom führt dasselbe Gerät in keinem
anderen gemeinsamen Band (MagentaMobil XL ist unbegrenzt und fällt aus
jedem Band, XS mit 20 GB landet in Mittel, wo Vodafone das Gerät nicht
gleichzeitig führt; beides benennt der Radar ehrlich statt zu mischen).

## Rechenproben

Alle Beträge sind echte, in `geraete_tco.json` persistierte Sätze,
nachgerechnet mit `tco_model.tco_24()` und von Hand. Formel:
**Zuzahlung + Geräteraten × min(24, Laufzeit) + Tarif × 24 +
Anschlusspreis**.

### Probe 1 — Google Pixel 11 Pro 256 GB olive, MagentaMobil S

Ratenprobe gegen die Quelle (Bedingung des Adapters):
`99,00 + 36 × 28,30 = 1.117,80 €` Ratengesamtbetrag — die Antwort nennt
denselben `totalPrice`, sonst wäre der Satz verworfen.

TCO-24: `99,00 + 24 × 28,30 + 24 × 39,95 + 39,95 = 1.776,95 €`
(Ø 74,04 €/M.) — `tco_24()` und Handrechnung exakt gleich; nach 24
Monaten offen: `12 × 28,30 = 339,60 €`.

### Probe 2 — Apple iPhone 17 Pro 256 GB tiefblau, MagentaMobil XL

`1,00 + 24 × 24,10 + 24 × 84,95 + 39,95 = 2.658,15 €`; offen
`12 × 24,10 = 289,20 €`. Der Fall zeigt die 1-€-Zuzahlung des XL-Bandes
(der teuerste Tarif subventioniert das Gerät am stärksten).

### Probe 3 — Radar-Paar Apple iPhone 17 Pro 256 GB

Telekoms günstigste Karte im Band Klein ist MagentaMobil XS
(29,95 €/M.): `99,00 + 24 × 30,50 + 24 × 29,95 + 39,95 = 1.570,55 €`.
Vodafone Mobil XS: `1.559,80 €`. Abweichung
`(1.570,55 − 1.559,80) / 1.559,80 = +0,7 %` — die Zahl, die auf
`wettbewerbsradar.html` steht.

## Vollsuite — ehrliche Basis, ehrliches Ergebnis

Die im Kontext genannte Basis („2811 passed / 3 failed") reproduced
am Rettungsstand **nicht**: nachgemessen im temporaeren Worktree an
`88abc8e` waren es **2824 passed / 4 failed / 14 skipped**. Die vier:

1. `test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung` — vorbestehend, bekannt
2. `test_promo_seite.py::test_der_leere_screenshot_wird_nicht_ausgeliefert` — vorbestehend, bekannt
3. `test_geraete_tco_hauptansicht.py::test_die_balkenlaenge_entspricht_dem_betrag` — **vor B-2 rot**: pixel-10-128 führt inzwischen zwei Vodafone-Bündel; die TCO24-1-Kalibrierung („je Anbieter genau eine Karte") war am Bestand vorbei
4. `test_geraete_adapter_telekom_1und1.py::test_telekom_landet_als_listung_…` — **vor B-2 rot**: der Rettungsstand selbst (5 neue `buendel`-Einstiege + `user_agent`-Override) brach den Test, ohne dass eine Session danach die Suite lief

**Ergebnis dieser Runde: 2 failed / 2829 passed / 14 skipped.** Beide
vorbestehenden Nicht-Promo-Roten sind repariert (Kalibrierung auf die
Regel statt auf eine Datenlage — der Balken-Test misst jetzt je
Balkenreihe gegen den auf der Reihe stehenden Betrag und überlebt jede
Kartenanzahl; der Listungstest hält den Einstieg auf den statischen
Zweig eng und seine Attrappe kennt das dritte `hole`-Argument). Zwei
weitere Tests, deren Telekom-Prämisse („0 Bündel") der neue Bestand
umstieß, sind auf beide Zustände umgestellt (belastbar mit Zahl UND
leer mit Satz — Lookup-Zeilen, sonst prüfte der Test nur einen).
**Keine neuen Roten.**

## Messgrenzen — ehrlich benannt

1. **Neun Geräte je Tarif sind alles, was die Seite liefert.** Die
   Kategorieseite trägt zehn Einträge, einer ist eine Werbekachel; mehr
   Bündel gibt es an dieser Adresse nicht. `max_produkte: 15` greift
   nicht. Der Telekom-Shop führt schlicht nur diese neun Smartphones
   in der Kategorie.
2. **Ein Messtag (2026-09-08).** Bündel altern nicht (`upsert_buendel`
   frischt auf) — ein `mark_stale` für `TcoDB` fehlt weiterhin
   (bekannt offener Punkt, Phase S 4b). Ein eingestelltes Bündel bliebe
   mit altem `last_verified` stehen; jede Zeile nennt ihr Abrufdatum.
3. **Aus GitHub Actions bleibt Telekom gesperrt** (202-Challenge,
   IP-basiert — gemessen 05./08.09.). Der Bestand lebt vom
   Lokallauf von Hand (`scripts/lokallauf_telekom.py`); dieser Commit
   hält den Stand fest, bis der nächste Lokallauf ihn auffrischt.
4. **Fünf unbekannte Farbschreibweisen** (cream, frost, olive, tiefblau,
   violet shadow — Protokollzeile des Laufs) sind die Arbeitsliste für
   `config/farben.yaml`. Eine spätere Kanonisierung ist eine
   Datenwanderung (sku_id ändert sich), bewusst nicht Teil dieses
   Auftrags.
5. **Der Slug ist gelegt, aber noch nicht geschlossen.** `tarif_slug`
   trägt die MF-ID (die Ordnung des Anbieters), die Kachel-Pipeline
   setzt noch kein `buendel_slug` — die Auflösung läuft heute über den
   Namen (Güte `hoch`, alle 45). Benennt die Telekom einen Tarif um, ist
   die Brücke schon da.
6. **MagentaMobil XL fällt aus jedem Band** (unbegrenzt) — seine
   Bündel stehen auf der TCO-Tafel, aber nicht im Bandgraph und nicht
   in den Radar-Paaren. Das ist die Bandregel (§7), keine Lücke.
7. **`keyword-index.json` war und blieb unverändert** — diesmal war
   kein Reset nötig (die R6/R7-Falle ist geprüft und trat nicht ein).

## Commits auf `openclaw/ticket-b2-buendel-telekom`

| Commit | Schritt |
|---|---|
| `5d18b8a` | T2-Laufzeitbeleg in `lokallauf_telekom.py` (gleicher Haken wie T1, eigene Datei) |
| `1d1c687` | robots.txt-Abruf trägt den Absender des Anbieters (Beleg-Befund 1/7) |
| `a4bf8b1` | 45 Telekom-Bündel erhoben, Beleg 7/7 ehrlich |
| `81b9087` | `geraeteanteil` kennt die live_shop-Zeitreihe als selben Tarif; vier Testkalibrierungen |
| `1d1bfb3` | Site gerendert (TCO-Tafel, G1, 9 Radar-Paare) |
| (dieser) | Bericht |

Kein `main`, kein Deploy-Hook, kein `uv.lock`.
