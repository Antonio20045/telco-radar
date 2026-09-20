# Auftrag Geräteseite v4 — Plan (Lead, 20.09.2026)

Grundlage: Auftrag „TCO-Radar, das man im Meeting zitieren kann" (Antonio, 20.09.2026),
Live-Review der Geräteseite, Nachrechnung der 837 CSV-Zeilen, drei abgeschlossene
Repo-Erkundungen (Rechenkern, Collectoren/Betrieb, Darstellung/Tests).

Reihenfolge: **erst Vertrauen (P0), dann Telekom (P1), dann Darstellung (P2), dann
Vergleichssprache (P3), dann Push (P4).** Jede Phase: ein Dynamic Workflow (max. 10
Agenten, meist 8–9), danach prüfe ich das Tor selbst an der gerenderten Seite und am
Live-HTML. Freigabe zwischen den Phasen durch Antonio.

## Erkenntnisse der Erkundung, die den Auftrag korrigieren

1. **ALDI A17 ist kein ALDI-Problem.** Es gibt genau eine ALDI-Listung (5G). Der
   Scheinsprung 129→169 € entsteht durch einen o2-Farb-Leak: `farbe_roh: "5g schwarz"`
   landet im SKU-Slug → `o2--samsung-galaxy-a17-128gb-5g-schwarz` und
   `…-schwarz` sind zwei Töpfe desselben Geräts. Fix: Farbnormalisierung + 5G ins
   vorhandene `netz`-Feld; Sprungursache zusätzlich gegen `data/state/geraete_preise.jsonl` belegen.
2. **`--al-*` in `style.css:36–39` sind Alarmstufen** (kritisch/mittel/gering/bestpreis),
   keine Anbieterfarben — die bleiben. Anbieterfarben-SSOT ersetzt stattdessen:
   `geraete_verlauf.py:92–125` (Hash-Palette, Ursache der grünen Telekom),
   `geraete_zeitreihe.py:62–63` (`ANB_FARBE`), `style.css:2872–2881` (`.gr-anb--*`, 10 Anbieter).
3. **Rabatte:** o2 backt −5 € (19,99 statt 24,99 SIM-only) in den Bündelpreis
   (`o2.py:265–276`); die −15/−18 € sind 1&1 und sind eine *abgelehnte, unbewiesene
   Aufspaltung* (`einsundeins.py:146–155`) — sie werden kein Rabatt-Feld.
4. **Ausfall-Alarm existiert halb:** `GeraeteDB.ausfall_alarme()` mit `AUSFALL_TAGE=7`,
   nur `log.warning`, bewusst ohne Mail (`geraete_pipeline.py:107–115`). P1 baut darauf um.
5. **Vodafone `_periode0()`** (`vodafone.py:260–269`) nimmt nur Phase 0 — bei
   36-Monats-Finanzierung mit niedrigerer Rate ab Monat 24 ist das ein Messfehler,
   nicht nur eine fehlende Variante.
6. **Live-Stand:** Der Python-3.11-Renderfix (8133b02) ist auf main, aber noch durch
   keinen Actions-Lauf gegangen; Live-Seite = Stand 18.9. (verifiziert: Live-HTML ==
   lokales `site/geraete.html`).
7. **`_rechung`-Gegenprobe** (`geraete_zeitreihe.py:424–496`) prüft Postensumme gegen
   das *eingefrorene* `gesamt` der Historie — bricht bei Formelwechsel (P0-A1) und
   muss auf Gegenprobe gegen die eigene Nachrechnung umgestellt werden.

## Schritt 0 — Arbeitsumgebung

- [x] CLAUDE.md neu (179→180 Zeilen), Größenregel grün. Regel 17 ergänzt (wip(auto)
      nie mergen/rebasen/pushen; Worktree-Branches nach Übernehmen löschen) — Antonio, 20.09.
- [x] PostToolUse-Hook → `scripts/hook_gezielte_tests.py` (nur Fachtests zum Modul).
- [x] Stop-Hook `stop-hook-commit.sh` gelesen: wirkt nur in Worktrees, committet
      `wip(auto)`, pusht nie, Hauptcheckout no-op. → Behalten (Antonio), Absicherung
      über Regel 17.
- [x] `commit-sicher`: pusht auf den aktuellen Branch → auf `main` korrekt, keine Anpassung.
- [x] `.claude/agents/seiten-pruefer.md` angelegt (opus; Read, Grep, Glob, Bash).
      Auftrag: „Dieses Ergebnis ist angeblich fertig. Finde den Grund, warum es falsch
      ist. Rechne mindestens fünf Zahlen der gerenderten Seite unabhängig aus
      `data/state/geraete_tco_historie.jsonl` nach, mit eigener Rechnung, nicht mit dem
      Code des Bauers. Wenn du nichts findest, nenne die drei Stellen, an denen du am
      längsten gesucht hast." Ändert keinen Produktionscode; einziges Schreibrecht ist
      der Orakel-Test `tests/test_seiten_zahlen.py` (diff-reviewer-S2-Auflage, 20.09.).
- [x] `/workflow-authoring` geladen, Phasen-Workflow `p0-bau` gebaut und an Paket A1
      bewährt (Resume nach Hot-Load des Agenten). Bewährte Skripte wandern am Phasentor
      nach `.claude/workflows/`.
- [x] Live-Gegenprobe des Renderfixes: `geraete.yml` manuell getriggert — Lauf
      `35518497506` success, „Seite neu gebaut 2026-09-20" (`0e1a75d`), Live-HTML
      trägt „20. September". Bestätigt P0-Punkt 9.

## Phase P0 — Vertrauen (blockiert alles)

Zwei Workflows nacheinander (je <10 Agenten), ein gemeinsames Tor danach.

### Workflow P0-A „Rechnung und Anzeige" (9 Agenten)

Kein Verstehen-Agent: Die Fundstellen (datei:zeile) liegen aus der Erkundung bei und
gehen in jedes Bau-Paketet-Briefing.

| Paket | Modell | Inhalt |
|---|---|---|
| A1 Leitzahl | opus | `tco_model.tco_24()` neu: Anzahlung + 24 Mon. Tarif **phasengewichtet** (`effektivpreis.phasensumme`, `report/effektivpreis.py:77–101`) + alle Geräteraten bis Monat 24 + **Restschuld (Raten 25–36) in die Leitzahl** + Anschlusspreis. `restbetrag` bleibt ausgewiesenes Feld, geht in `gesamt` ein. Prüffall congstar XS · iPhone 17 Pro 256 GB = 1 + 24×15 + 36×30,50 + 0 = **1.459,00 €**. Anzeige überall: Karten, Rechenweg-Panel (`_rechnung_html`, Formel-Satz), Ranking, Δ, Zeitreihen-Labels („Kosten über 24 Monate"), Exporte lesen weiter `tco_24()` (Clean Code 1). Orakel: keine Leitzahl unter dem Barpreis desselben Anbieters ohne belegten Rabatt — Test gegen echten Bestand. Gegenprobe in `_rechung` auf eigene Nachrechnung umstellen (s. Erkenntnis 7). |
| A2 Bewegung/Δ/Referenz | sonnet | `_bewegung()` (`geraete_zeitreihe.py:958–988`): Delta nur je Anbieter über Messtage, an denen derselbe Anbieter liegt; fehlt ein Anbieter → keine Bewegungsanzeige („+387 €"-Klasse tot). `_delta`-Schwelle in `geraete_tco_karten.py`: unter 15 €/3 % „≈ +11 €", „—" nur für „kein Angebot". Unerklärte Katalog-Referenz iPhone 17 256 (−442,79 € gegen 1.391,79 €, Daten 1.487,80 €) aufklären und korrigieren. |
| A3 Altern | sonnet | Angebote > 3 Tage (benannte Konstante) fallen aus „ab"-Preis, Δ und Ranking; in der Tabelle ausgegraut mit Abrufdatum. `analyze/tco_store.py` (Kopf-Kommentar „keine Zwei-Stufen-Auslistung" wird geändert) + Auswahl/Anzeige aus einer Definition (Clean Code 7). |
| A4 Exporte | sonnet | `geraete_tco_view.py` / `geraete_export.py`: 156 Vodafone-Farb-Duplikate (Farbe fehlt als Spalte) → Farbe in den Export, Zeilen eindeutig; SIM-only-`tco24` schließt Anschlusspreis ein (Konsistenz zu `tco_24`, `geraete_tco_view.py:525`). |

Prüfen: je Paket 1 `seiten-pruefer` (opus), adversarisch, Schema
`{befunde:[{schwere,beleg,datei_zeile}], gesucht_aber_nichts_gefunden:[…]}`.
Der A1-Prüfer schreibt die **zweite, unabhängige Rechnung** als
`tests/test_seiten_zahlen.py`: liest die gerenderte Seite (über `render_site()` in
tmp, Vorbild `test_geraete_anbieterzaehlung.py:48–53`), nie die Python-Objekte.
Nachbessern: nur schwere ≥ hoch, max. 2 Runden, sonst Abbruch an den Lead.
Sichttor: 1 Agent (opus): `render_site()` mit echten `data/`, Screenshots 1440/390 px,
PNGs ansehen, 5 Zahlen gegen `data/state/` und CSV rechnen.

### Workflow P0-B „Laufzeiten und Datenlage" (8 Agenten + Lead-Einzeltat)

| Paket | Modell | Inhalt |
|---|---|---|
| B1 Laufzeit in den Bündelschlüssel | opus | `tco_model.buendel_id()` um Laufzeitsegment ergänzen. Historie-Kontinuität: alte `geraete_tco_historie.jsonl`-Zeilen bleiben zuordenbar (Zeitreißen vermeiden — Zuordnung über (SKU, Anbieter, Tarif) weiter möglich oder Lesemigration im Store). Tests auf id-Stabilität. |
| B2a Ratenlaufzeiten Telekom/congstar/Vodafone | sonnet | `telekom.py:236–257`: alle `installments` (6/12/24/36) statt `raten[0]`. `congstar.py`: `_RATENLAUFZEIT=36` (:390) → 24 **und** 36 (Header „ZWEI ZAHLWEISEN, EIN SAETZ" :149–162 wird Realität, hängt an B1). `vodafone.py`: 12/24/36 erfassen, `_periode0()` → alle Phasen (Erkenntnis 5). Fixtures aus gespeicherten echten Abrufen; Prüfagent ist Pflicht (CLAUDE.md, Subagent-Fallstrick). |
| B2b o2/1&1: Schlusszahlung, Rabatt-Basis, SKU-Fix | sonnet | o2: 24/36; `farbe_roh "5g schwarz"` → „schwarz", 5G ins `netz`-Feld (A17-SKU-Kollision, Scheinsprung 129→169 gegen `geraete_preise.jsonl` belegen). 1&1: „24+12"-Schlusszahlung als eigenes Feld, **zählt zur Leitzahl** (bei Kündigung nach 24 fällig). Rabatt-Basis einheitlich: gespeicherter Monatspreis = Preis ohne bedingte Rabatte; belegte bedingte Rabatte als Felder (Bedingung + Quelle) — die unbewiesene 1&1-Aufspaltung bleibt abgelehnt (Erkenntnis 3). |
| B3 Telekom-Tarifsätze | sonnet | Nach Beleg (s. Verstehen): aktuellen Satz führen (Volumen/Preis), alten stilllegen. `data/state/tarife.jsonl`: S 6 GB (PIB, Zeile 4) vs. S 30 GB (`#live_shop`, Zeile 55), M 12/50, L 80/100 — Regel, welche Quelle gewinnt; `_zeitreihen_basis` (`tco_model.py:600–612`) bleibt konsistent. congstar „XL mit Upgrade-Versprechen" (25 GB, Zeile 31/32) mit beurteilen. |

Verstehen: 1 `quellen-pruefer` (haiku) belegt die Telekom-Tarifsätze gegen telekom.de
(laut Shop S ab 34,95 €, Daten sagen 39,95 €) und die congstar-XL-Lage.
Lead-Einzeltat (kein Agent): `geraete.yml` — `continue-on-error` von „Render site"
und „Commit site" entfernen (State-Commit steht davor, der Messtag bleibt gesichert);
Begründung als Kommentar im Workflow. Gegenprobe im nächsten Lauf.

**Tor P0 (ich prüfe selbst):** iPhone 17 Pro 256, iPhone 17 256, Galaxy S26 Ultra 256,
Pixel 10 Pro in allen Bändern: Karte, Leitzahl und Tabellenzeile == unabhängige
Nachrechnung aus `geraete_tco_historie.jsonl` (`test_seiten_zahlen` grün gegen echten
Bestand). Keine Bewegungsanzeige ohne Preisänderung desselben Anbieters. Kein Wert
älter als 3 Tage ohne sichtbares Datum. Für drei Geräte je Anbieter alle Laufzeiten,
die die Produktseite anbietet, in den Daten. Danach: Push, `geraete.yml` manuell,
Live-Check (Datum + Tor-Zahlen im ausgelieferten HTML).

## Phase P1 — Telekom täglich und Ausfall-Alarm (6 Agenten)

- Verstehen (haiku): Ursache messen, nicht raten — `geraete_db.json`
  (`laeufe`/`termine`/`funde_nach_tag`), Actions-Logs/Artefakte, Statusgrund
  (ok|leer|fehler|frist|nicht_umgesetzt). Grenzen wie gehabt: normale Herkunft,
  robots.txt (Telekom: kein Crawl-delay, eigener `rate_limit_sekunden: 10`),
  keine Umgehung. Kommt eine Challenge: messen, dokumentieren, Antonio im Klartext.
- C1 Ursachenfix (sonnet) nach Messung.
- C2 Abdeckungswächter (sonnet): Anbieter fehlt, der am Vortag lief, ODER Zeilenzahl
  −30 % → Warnung ins Protokoll + „heute nicht erfasst" auf der Seite + Mail an
  Antonio (`versand.sende_mail()` wiederverwenden, SMTP-Secrets vorhanden; geraete.yml
  bekommt den Versandschritt). Baut `ausfall_alarme()` auf Vortag-Vergleich um.

**Tor P1:** Telekom liefert an 5 aufeinanderfolgenden Tagen Bündel oder es liegt eine
dokumentierte Messung vor, warum nicht. Ein künstlich deaktivierter Collector löst den
Alarm aus (Test + ich prüfe Protokoll/Mail). Einmal-Cron an Tag 5 zur Tor-Prüfung.

## Phase P2 — Darstellung ohne Erklärtexte (9 Agenten)

Vorher lade ich `/dataviz` (Chart- und Farbregeln). Zielbild steht im Auftrag
(Antwortzeile, Punktstreifen, Verlauf mit Event-Linien, Tabelle mit Zerlegungsbalken,
Barpreis/Katalog kompakt).

| Paket | Modell | Inhalt |
|---|---|---|
| D1 Farb-SSOT | sonnet | `ANBIETER_FARBE` an einer Stelle in Python, ausgegeben als CSS-Custom-Properties; alle Stellen lesen nur daraus. Weg: `farbe_fuer()`-Hashpalette, `ANB_FARBE`, handgeschriebene `.gr-anb--*`. Farben: Vodafone #E60000 (3 px, immer vorn), Telekom #E20074, o2 #0019A5 (durchgezogen), 1&1 #2F7FD1 (gestrichelt), congstar Linie #121212 + Marker #FFED00, Service-Provider grau gepunktet, Händler grau mit Markerform. `--al-*` (Alarmstufen) bleiben (Erkenntnis 2). Farbfehlsichtigkeits-Check. |
| D2 Chart | sonnet | Stufenlinie (Preise springen), y-Achse 4–5 runde Werte, Achsenbruch bei <10 % Spanne sichtbar, Messlücken gepunktet (nie schräal), Ein-Punkt-Anbieter nur Marker ohne Endlabel, Endlabels statt Legende, X-Labels ohne Überlapp, „Wöchentlich" aggregiert echt oder weg. Server (`_svg`) und Client (`app.js zeichne()`) aus einer Regel-/Datenquelle — Farben/Reihen kommen weiterhin fertig aus Python. |
| D3 Tabelle | sonnet | Zahlen rechtsbündig `tabular-nums`, Einheit im Spaltenkopf, nur horizontale Linien, 3-px-Streifen in Anbieterfarbe, ein Aufklapper je Zeile, Hauptzahl nennt das Subjekt („congstar 467 € unter Vodafone"), Zerlegungsbalken mit schraffierter Restschuld (aus P0-A1). |
| D4 Mobil/Export/Texte | sonnet | Nichts abgeschnitten, Reiter/Export erkennbar scrollbar, Tooltips als Bottom-Sheet, ein „Export ▾" statt sechs. Erklärtext-Inventur aus dem Auftrag löschen oder ins ⓘ-Popover an Spaltenköpfen; Methodik vollständig auf der Quellenseite, Geräteseite nur Fußzeilen-Link. Fundstellen liegen aus der Erkundung bei (u. a. `geraete.html.j2:84,405,602,1001`, `app.js:2654–2657`, `_geraete_buendel.html.j2:169`, `_geraete_radar.html.j2:319`). |

**Tor P2:** Screenshots 1440/390 angesehen. Kein Satz auf der Geräteseite, der erklärt,
wie man sie liest. Telekom in jedem Reiter magenta. Fünf-Sekunden-Test: „Wie viel
günstiger als Vodafone ist das iPhone 17 Pro bei der Telekom, und seit wann?"

## Phase P3 — Sprache der Abteilung, Aktionen sichtbar (9 Agenten)

| Paket | Modell | Inhalt |
|---|---|---|
| E1 Bänder dynamisch | opus | Feste Grenzen (≤20/21–60/>60 GB, `geraete_tco_band.py:57–97`) entfallen. Jeder Lauf leitet die Kategorien aus den Vodafone-Tarifen „mit Smartphone" in `tarife.jsonl` ab (Stand 16.9.: XS 18 / S 35 / M 60 / L 120 / XL unbegrenzt); Wettbewerber fallen in die Kategorie des nächstgelegenen Vodafone-Volumens. Umschalter „Mobil XS · 18 GB | S · 35 GB | …". Volumen/Geschwindigkeit als Spalte. Netzbetreiber/Discounter als Gruppen erkennbar. congstar-XL-Lage aus dem P0-Beleg übernehmen. |
| E2 Laufzeit-Filter | sonnet | Standard 24 Monate (Tarifbindung); Fairness bleibt durch Restschuld in der Leitzahl. Baut auf P0-B auf. |
| E3 Aktionen | sonnet | Wechselbonus, Online-Vorteil, Trade-in, Tarifrabatt aufs Gerät, erlassener Anschlusspreis als Felder mit Bedingung + Quelle; Überhang am Balken („bis −150 € mit Rufnummernmitnahme"), Marker im Verlauf. |
| E4 Event-Kalender | sonnet | `config/`-Datei mit Apple-/Samsung-Launches, Black Friday, Cyber Monday, Weihnachten; senkrechte Linien im Chart. |

**Tor P3:** Für drei Geräte ist je Vodafone-Tarifkategorie das Gegenangebot von
Telekom, o2, 1&1 und congstar sichtbar, mit Quelle. Mindestens eine aktuelle Aktion
erfasst und gegen die Anbieterseite belegt.

## Phase P4 — Push statt Pull (klein, ≤4 Agenten)

F1 (sonnet): wöchentlicher Block, ≤ 5 Zeilen, nur Bewegungen > 50 € oder 5 % gegenüber
Vodafone (aus der in P0 verifizierten Bewegungslogik), Deep-Link auf die vorausgewählte
Geräteseite; wenn nichts: ein Satz. Einbindung über die bestehende Infrastruktur:
Berechnung im radar-Lauf, Block ins Digest-Rendering, `report_ready`-Payload
(`radar.yml:261–300`) erweitern. Der Abonnenten-Versand läuft aus dem privaten Repo
`telco-radar-inbox` — dessen kleiner Anpassungs-Diff wird vorbereitet und Antonio
benannt (separater Zugriff).

**Tor P4:** Testversand an Antonio enthält nur Bewegungen, die in P0 als echt
nachgewiesen sind.

## Querschnitt (alle Phasen)

- **Modelle** wie im Auftrag: Lead/Prüfer/Formel = opus, Bauer = sonnet, Scout/Quellen = haiku.
- **Orakel-Tests** `tests/test_seiten_zahlen.py` wachsen je Phase; die zweite Rechnung
  schreibt immer der Prüfer, nie der Bauer. Fixtures nur aus gespeicherten echten Abrufen.
- **Gedächtnis:** `outputs/fortschritt-geraeteseite.md`, 3 Zeilen je Phase (gebaut /
  gemessen / offen). `/clear` nach jedem Phasentor.
- **Commits:** Merge der Worktree-Ergebnisse nur über gezielte Dateilisten; `wip(auto)`
  nie mergen/rebasen/pushen; Worktree-Branch danach löschen (Regel 17). Vor jedem
  Commit `diff-reviewer`. Keine lokalen `data/state/`, `site/`, `data/reports/`-Artefakte.
- **Live-Nachweis je Phase:** Push auf main → `geraete.yml` manuell → 15 s → Hook →
  `curl` Live-HTML → Datum + Tor-Zahlen im ausgelieferten HTML prüfen. Am Ende sage ich
  ausdrücklich, was live ist.
- **Python 3.11:** vor jedem Push geänderte Module mit `python3.11 -m py_compile`
  prüfen (lokal läuft 3.14; Regel 15). CI (3.11) läuft ohnehin.
- **Fristen:** B2 erhöht die Zeilenzahl je Anbieter — `_MINDEST_JE_ANBIETER`-Zeit und
  `--frist 1500` im Blick behalten (Regel 12/13).
