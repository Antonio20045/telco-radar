# Phase GRAPH-1 — Gerät × Tarifniveau im Graphen (08.09.2026)

Auftragsgrundlage: `BRIEF_GRAPH1.md` (Workspace-Engineer) auf Basis von
`AUFTRAG_GERAETESEITE.md` §2a (Kopplung Gerät × Tarifniveau, Linie je
Anbieter) und §7 (Tarifbänder Klein/Mittel/Groß). Branch
`openclaw/ticket-graph1`, Basis `main` `6540b3b` (TCO-24-Norm). Zwei
Commits: `790c406` (Quelle, Vorlage, Tests), `5b4279c` (CSS-Klassenkonflikt
behoben, Site neu gerendert).

## Lösung — die eine Regel, die sie trägt

**Keine zweite Geometrie.** `geraete_tco_grafik.zeitreihe()` — die
bestehende G0-Funktion, die schon "ein Messpunkt bleibt ein Punkt" und
"Sammellücken bleiben leerer Raum" beherrscht — bekommt zwei neue,
optionale Parameter (`messgroesse`, `klasse`) und zeichnet damit sowohl G0
(Geräte-Barpreis) als auch den neuen Band-Graphen (TCO-24). Der neue
Baustein `report/geraete_tco_band.py` rechnet **keinen Euro**: er gruppiert
die schon fertigen Karten aus `geraete_tco_karten.modelle()`
(`k["gesamt"]` ist bereits `tco_24().gesamt`) nach Tarifband und baut
daraus Ein-Punkt-Reihen (`{"anbieter","farbe","eigen","punkte":[{"datum":
abgerufen_am, "preis": gesamt}]}`) — dasselbe Reihenformat, das
`geraete_verlauf._reihen` für G0 baut.

**Warum ein Punkt und keine Linie über Monate.** `analyze/tco_store.TcoDB`
führt bewusst **keine Preishistorie** für Bündel (Modulkopf dort: "Was hier
bewusst NICHT steht … keine Preishistorie"). Jeder Bündeldatensatz zeigt
eine Messung. Eine "Linie über die Monate" ist heute deshalb ehrlich genau
das, was G0 für einen einzelnen Messpunkt kennt: ein beschrifteter Punkt
("Serie startet"). Sobald ein zweiter Lauf Bündel liefert, trägt dieselbe
Funktion automatisch eine echte Linie — ohne eine Zeile Code hier zu
ändern. Diese Grenze stand schon vor GRAPH-1 im Repo
(`geraete_tco_karten.historienreihen`-Docstring: "Einen TCO-VERLAUF gibt es
hier noch nicht … eine Kurve daraus wäre interpoliert") und ist keine
Erfindung dieses Tickets.

**Platzierung.** Die Tarifband-Auswahl steht **neben** der Geräteauswahl
(Aufgabe 1, wörtlich): ein gemeinsames `<select id="gr-band">` mit drei
festen Optionen (Klein/Mittel/Groß, `data-vorgabe` auf das erste
verfügbare Band des Vorgabemodells) sitzt in derselben `.gr-msel--gross`-
Zeile wie `#gr-modell`. Welche der drei Optionen für das gerade gewählte
Gerät ein echtes Bündel trägt, steht als `data-baender="klein mittel"`
usw. an jeder `<option>` von `#gr-modell`; `app.js` deaktiviert die
übrigen Optionen (nicht entfernt — Aufgabe 1 verlangt "nur Bänder
anbieten, für die Bündel existieren" als **Angebot**, nicht als
DOM-Löschung). Der Graph selbst steht **unter** G0, als eigenes Element je
Modell (Aufgabe 2 lässt diese Wahl ausdrücklich offen) — dieselbe
Begründung wie überall auf dieser Seite: ein Graph, der bei jedem
Modellwechsel neu aufgebaut würde, wäre eine zweite Geometrie für dieselbe
Zahl.

## Die drei Bänder (§7), am echten Bestand vom 08.09.2026

`band_von_gb()` liest `datenvolumen_gb` aus `tarife.jsonl` — Klein bis
20 GB, Mittel 21–60 GB, Groß über 60 GB; fehlend (`None`) **und**
unbegrenzt (`Infinity`) fallen beide aus dem Raster (`None`), genau wie §7
es für beide Fälle einzeln vorschreibt.

## Datenlage — Vorher/Nachher

| | Vorher (GRAPH-1 nicht gebaut) | Nachher |
|---|---|---|
| Gerät × Tarifband auswählbar | nein | ja, neben der Geräteauswahl |
| TCO-24 je Anbieter im Band sichtbar | nein | ja, eine Linie/ein Punkt je Anbieter mit echtem Bündel |
| Fehlende Anbieter benannt | nein | ja, Muster wie die Händler-Lücken am G0-Block |

**82 Modelle mit mindestens einem Bündel** (`modelle_gesamt`), davon
**80 mit mindestens einem Band** (mind. 1 echtes Bündel mit
bestimmbarem Datenvolumen), **2 ohne jedes Band**
(`nothing-phone-4a-pro-128`, `samsung-galaxy-a27-128` — beide führen nur
ein 1&1-Bündel, und 1&1s Tarifname löst nie auf `datenvolumen_gb` auf,
siehe unten).

Bandverteilung über alle 82 Modelle (Anzahl Modelle, die dieses Band
zeigen): **Mittel 79 · Klein 59 · Groß 7**. Groß ist selten, weil nur o2
in diesem Bestand Tarife über 60 GB mit Gerät bündelt.

### Der Vorgabefall: iPhone 17 Pro 256 GB (`apple-iphone-17-pro-256`)

| Band | Linie(n) | Benannte Lücke |
|---|---|---|
| Klein (bis 20 GB) | Vodafone (Mobil XS, 18 GB, TCO-24 1.559,80 €) | Telekom, 1&1, o2, congstar |
| Mittel (21–60 GB) | Vodafone (Mobil S, 35 GB, TCO-24 2.195,80 €) | Telekom, 1&1, o2, congstar |
| Groß (über 60 GB) | o2 (Mobile L Plus, 150 GB, TCO-24 1.356,76 €) | Telekom, 1&1, Vodafone, congstar |

Jeder der fünf erwarteten Anbieter steht in jedem Band **genau einmal** —
entweder als Linie oder als benannte Lücke, nie beides, nie keins von
beidem (Testzusicherung in `test_geraete_tco_band.py`).

### Warum 1&1 nie eine Linie trägt

1&1 verkauft im erhobenen Bestand ausschließlich im Bündel
(`buendel_monatlich`, § 13.2) und trägt dafür **keinen auflösbaren
`tarif_id`** — sein Tarifname steht auf keiner Produktinformationsblatt-
Seite, die dieses Projekt liest. `tarif_baender()` kann ihm deshalb nie ein
Datenvolumen zuordnen, in KEINEM Band. Das ist keine Lücke dieses Tickets:
`AUFTRAG_GERAETESEITE.md` §7 selbst zählt 1&1 unter den fünf Anbietern,
für die "kein einziges Datenvolumen … bei allen Anbietern" vorkommt, und
1&1 ist bereits in der ursprünglichen Datenlage (§5) als Anbieter ohne
Bündel-Zuzahlungsstruktur benannt. Die Meldung an der Karte
("`1&1 führt für dieses Gerät kein Bündel in diesem Band`") ist damit
ehrlich, auch wenn sie strenggenommen für 1&1 in JEDEM Band gilt — eine
Sonderformulierung nur für diesen einen Anbieter wäre eine Ausnahme ohne
zusätzlichen Erkenntnisgewinn.

## Rechenprobe

iPhone 17 Pro 256 GB, o2, Band Groß, Tarif "O2 Mobile L Plus mit 150 GB+
(24 Mon.)": `TCO-24 = 1.356,76 €` — dieselbe Zahl, die auch die
Hauptansicht (TCO-Karten) für dasselbe Bündel zeigt (keine zweite
Rechnung, siehe Modulkopf `geraete_tco_band.py`).

## Abnahmekriterien (Aufgabe 5)

| # | Kriterium | Umsetzung | Test |
|---|---|---|---|
| a | Bandableitung aus echten `tarife.jsonl`-Datenvolumina, 3 Beispiele | `band_von_gb()` | `test_drei_echte_tarifsaetze_treffen_ihr_band` (o2 unbegrenzt→`None`, Vodafone 18 GB→klein, Vodafone 60 GB→mittel, o2 150 GB→gross) |
| b | Modell×Band zeigt genau die Anbieter mit Bündeln, iPhone-17-Pro-256 als Vorgabefall | `baender_fuer_modell()` | `test_vorgabefall_zeigt_genau_die_anbieter_mit_echten_buendeln` |
| c | Kein TCO-36 im gerenderten Artefakt | `zeitreihe(messgroesse="TCO-24")`, Y-Achse bleibt Euro über 24 Monate | `test_kein_tco36_in_keinem_bandgraphen` (jeder Bandgraph des ganzen echten Bestands) + `grep -c "TCO-36" site/geraete.html` = 0 |
| d | Leerzustand testbar | Modell ohne bestimmbares Band → leere Bandliste, Vorlage zeigt benannten Satz statt erfundener Linie | `test_leerzustand_modell_ohne_buendel_in_keinem_band` |
| e | Browser-Test: beide Auswahlen sichtbar und funktional (1440×900) | `#gr-modell` + `#gr-band` nebeneinander, Bandwechsel schaltet das richtige Panel | `test_geraete_tco_band_browser.py` (2 Tests, echtes Chromium) |

## Ein Fehler, den nur die Testsuite gezeigt hat

Die erste Fassung ließ den Band-Graphen dieselbe Wurzelklasse `gr-g0` wie
G0 tragen. Für Modelle **ohne** G0-Zeitreihe (`zr.hat_daten == False`, aber
mit mindestens einem Bandpanel) war das Bandpanel-SVG dann das **einzige**
`svg.gr-g0` im Block — und `svg.gr-g0`-Selektoren (sowohl in
`test_geraete_anbieterzaehlung.py` als auch potenziell in `app.js`) lasen
plötzlich die falsche Grafik. Fünf Tests fielen dadurch beim ersten
Suitenlauf durch. Behoben mit einem eigenen Parameter `klasse` an
`zeitreihe()` (Default `"gr-g0"`, Aufruf hier `"gr-tcoband"`) — die inneren
Geometrie-Klassen (`gr-g0-raster`, `gr-g0-linie`, …) bleiben gemeinsam, nur
die Wurzel unterscheidet sich. Dieselbe Fehlerklasse wie die
Anbieterzählung vom 05.09.2026: zwei verschiedene Dinge unter demselben
Namen.

## Testsuite

Baseline vor GRAPH-1 (nachgemessen per `git worktree` gegen `6540b3b`,
NICHT per `git stash`): **1 vorbestehender Fehlschlag außerhalb der
bekannten zwei Promo-Roten** —
`test_geraete_tco_hauptansicht.py::test_die_balkenlaenge_entspricht_dem_betrag`
schlägt bereits am unveränderten `main`-Stand fehl (Datenlage-Drift durch
parallel laufende Tickets: `google-pixel-10-128` führt am aktuellen
Bestand mehr als eine Vodafone-Karte, die der Test als "genau eine"
voraussetzt). Das ist **nicht** durch GRAPH-1 verursacht und wurde nicht
angefasst.

Nach GRAPH-1: **3 failed, 2793 passed, 14 skipped** (2 vorbestehende
Promo-Screenshot-Tests + der eine oben genannte, alle drei vor diesem
Ticket rot) — **0 neue Fehlschläge**, **9 neue Tests grün**
(`test_geraete_tco_band.py`: 7, `test_geraete_tco_band_browser.py`: 2).

## Site-Artefakte

`render_site(Path("site"), Path("data/reports"), load_config(root=Path(".")))`
zweimal aufgerufen (nach dem Klassenkonflikt-Fix erneut). Committet:
`site/geraete.html` (146 Bandpanels über 80 Modelle mit mindestens einem
Band), `site/style.css`, `site/app.js`. `site/geraete-quellen.html` zeigt
eine kleine, von GRAPH-1 unabhängige Korrektur (22→23 Saturn-Listungen,
527→528 geprüfte Preiszeilen) — reine Folge des vollständigen Neu-Renderns
gegen den aktuellen `data/state`-Stand, nicht durch diesen Code
verursacht. `site/data/keyword-index.json` war nach beiden Renderläufen
unverändert (kein Reset nötig).

## Lückenliste (bewusst offen)

1. **Echte Zeitreihen fehlen strukturell**, nicht nur an Daten — siehe
   oben. Sobald `TcoDB` (oder ein Nachfolgeticket) eine Bündelhistorie
   führt, trägt derselbe Code automatisch echte Linien.
2. **1&1 kann in keinem Band je eine Linie tragen**, solange sein
   Tarifname nicht auf ein Datenvolumen auflöst (siehe oben) — das ist
   eine Datenerhebungsfrage, keine Grafikfrage.
3. **Telekom und congstar liefern heute in keinem Modell ein echtes
   Bündel** — beide stehen in jedem Band als benannte Lücke, nie als
   Linie. Sobald ein Adapter dafür liefert, erscheinen sie automatisch
   (`ERWARTETE_ANBIETER` in `geraete_tco_band.py`).
4. **Der vorbestehende Fehlschlag** in
   `test_geraete_tco_hauptansicht.py` (siehe oben) ist nicht Teil dieses
   Tickets und bleibt offen für den nächsten, der die Datenlage von
   `google-pixel-10-128` anfasst.
