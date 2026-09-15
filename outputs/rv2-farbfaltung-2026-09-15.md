# RV-2 · Farbschreibweisen im Listing-Merge gefaltet

**Datum:** 15.09.2026 · **Branch:** `openclaw/ticket-rv2` · **Commits:** `e35456e`
(Fix) + `990b474` (Tests) + Berichtscommit (Basis `86800aa`) · **Status:** fertig,
wartet auf unabhängigen Evaluator-PASS. Nicht gemergt, nicht deployt;
`site/`, `data/` und alle Messbestände unangetastet (Arbeitsbaum: nur
`src/telco_radar/report/geraete_bereinigung.py` und
`tests/test_geraete_bereinigung.py` geändert; Alt/Neu-Renders nur unter `/tmp`).

Auftragsgrundlage: Ticket RV-2 zu Befund 2 aus REVIEW_2026-09-09.md (nicht im
Repo; wörtlich im Ticket). Pflichtlektüre CLAUDE.md gelesen, insbesondere
E1-Ehrlichkeitsregel und §6.

## 1. Symptom und Spezifikation — was gefaltet wurde und was nicht

**Der Befund (wortgleich):** „Farb-Dopplung ‚Tiefblau' vs. ‚tiefblau' (iPhone
17 Pro 256 GB, Saturn- und Telekom-Zeile) — der Erklärtext über der Tabelle
verspricht ‚zwei Schreibweisen derselben Leistung stehen als eine Zeile', die
Tabelle zeigt zwei; wirkt wie Datenfehler."

**Nachgemessen am Review-Commit `3a349bd`:** Die Tabelle zeigte adjazent
„Tiefblau Saturn↗" (1179,00 €) und „tiefblau Telekom↗" (1197,00 €). Das sind
**zwei Läden mit zwei Preisen** — zwei Zeilen, und die müssen zwei bleiben:
zwei Angebote verschiedener Läden zu einer Zeile zu falten löschte einen
wahren Preis; der Modulkopf des Merge-Layers hält genau das als seine Kardinal-
regel fest („Die Falle: eine echte Farbvariante ist kein Zwilling", 370 → 272
Zeilen, wenn man Farbe aus dem Schlüssel nimmt). Die Strategie legt dieselbe
Lesart fest: `docs/STRATEGIE_GERAETESEITE.md` P4 — „**‚Tiefblau' normalisieren
(RV-2)**".

**Was also der Fehler war:** Der Zwillings-Schlüssel faltet Groß/klein
längst (`farbschluessel` → `normalisiere`); die **Anzeige** tat es nicht. Am
sichtbaren Bestand (14.09.) standen **28 Farbschlüssel in zwei Schreibweisen**
da, u. a. `Tiefblau/tiefblau`, `Deep Blue/deep blue`, `Space Schwarz/space
schwarz`, `Glacier Blue/Glacier blue`, `Cosmic Orange/cosmic orange` — auf
jeder Ansicht, die aus dem Merge trinkt (Katalogtabelle, Export-CSV).

**Die Spezifikation, wie sie umgesetzt ist:** `_mit_einheitlicher_schreibweise()`
im Listing-Merge (`geraete_bereinigung.bereinige()`, Schritt 2 von dreien)
hebt je `normalisiere`-gefalteter Farbe **eine** Schreibweise auf alle Kopien
des Bestands: die **häufigste** gewinnt, bei Gleichstand die alphabetisch
kleinere — deterministisch, ohne jedes Datum (K-1-Lehre: keine Zeit- oder
Tagesabhängigkeit, reine String-Normalisierung). Damit wird der Erklärtext
wahr: **keine zwei Zeilen zeigen Schreibweisen, die nur Groß/klein auseinander
liegen** — die „Dopplung" im Sinne des Befunds ist aufgelöst. Die ZEILEN
derselben Farbe verschiedener Läden bleiben (siehe oben); dieselbe LISTUNG in
zwei Schreibweisen (gleicher Laden, gleiche Adresse, gleicher Preis) wird
nach wie vor vom Zwillings-Merge zu EINER Zeile zusammengefasst — das ist
seit `farbschluessel` so und jetzt gegen Regression genagelt.

Zwei bewusste Abgrenzungen:

| Gefaltet wird | Nicht gefaltet wird | Warum |
|---|---|---|
| Groß/klein, Umlaute, Trenner (`Deep Blue` = `deep blue`) | verschiedene Farben (`Deep Blue` ≠ `Tiefblau` ≠ `kosmisch orange`) | Faltung über `normalisiere`, nicht über Bedeutungsgleichheit |
| — | Kürzel (`pistachio bk` bleibt eigene Schreibweise neben `pistachio`) | `farbschluessel` streicht Kürzel für den Zwillings-Schlüssel (Doppelpreis-Erkennung); als ANZEIGE versteckte es die zweite o2-Listung, die es wirklich gibt |
| die Kopien des Merges | `data/state/geraete_db.json`, Quelldaten | eine andere Schreibweise im Store änderte die `sku_id`-Stabilität; gefaltet wird erst beim Merge (Abnahmekriterium 5) |

## 2. Was geändert wurde

| Stelle | Änderung |
|---|---|
| `report/geraete_bereinigung.py` · `bereinige()` | drei Schritte statt zwei: Zustandswort streichen → **Schreibweisen einen** → Zwillinge zusammenfassen. Reihenfolge trägt den Zwillings-Merge wie bisher |
| `report/geraete_bereinigung.py` · `_mit_einheitlicher_schreibweise()` (neu) | baut je `normalisiere`-Schlüssel die Häufigkeitstabelle der Schreibweisen, bestimmt den Vertreter `min((-häufigkeit, schreibweise))` und schreibt ihn in das Feld, aus dem die Anzeige kam (`farbe_normalisiert` bzw. `farbe_roh` — nie nach `farbe_normalisiert`, was nicht aus `farben.yaml` kommt) |
| `report/geraete_bereinigung.py` · `_anzeigefarbe()` (neu) | derselbe Ausdruck `farbe_normalisiert or farbe_roh` wie in `katalogzeilen()`, `geraete_vergleich._angebot()` und `geraete_export.aktuell_csv()` — die Faltung muss genau die Stelle erreichen, die alle Verbraucher lesen, sonst zeigt der Katalog eine Schreibweise und der Export die andere |
| Modulkopf | Befund 3 (RV-2) mit Messung und Begründung der Nicht-Zeilen-Faltung dokumentiert |
| `tests/test_geraete_bereinigung.py` | +7 Tests (Abschnitt „Die Schreibweisen-Faltung"), kein bestehender Test geändert, geschwächt oder entfernt |

Alle Ansichten trinken aus demselben Merge: Katalog-Tabelle, Export-CSV,
Vergleichs-Angebote — die Faltung wirkt überall, ohne dass eine Vorlage
angefasst wurde.

## 3. Abnahmekriterien — Belege

1. **Farbwerte case-insensitive gefaltet, Dopplung aufgelöst.** Sieben neue
   Tests; **gegen den unveraenderten Baum gemessen (Fix gestasht) fallen 3,
   bestehen 4** — die drei Roten sind die Faltungs-Tests (Review-Fall,
   echter Bestand, Katalogtabelle), die vier Bestehenden sind die
   Invarianten (Zusammenführungs-Regel, Gegenproben, Store-Schutz), die
   auch vorher galten und weiter gelten. Mit Fix: 7/7 grün.
   **Der konkrete Fall:** `test_der_katalog_zeigt_den_concrete_fall_mit_einer_
   schreibweise` stellt die Review-Lage exakt (iPhone 17 Pro 256 GB, Saturn
   „Tiefblau" UND Telekom „tiefblau", beide aktiv) und misst die Tabelle bis
   in die Farbspalte: beide Zeilen zeigen **eine** Schreibweise („Tiefblau"),
   beide Preise (1179/1197) bleiben stehen. Im Neu-Render des echten Bestands
   zeigen alle sichtbaren tiefblau-Zeilen (Telekom, Vodafone,
   mobilcom-debitel) „Tiefblau"; Saturns Zeile ist im heutigen Stand
   `ausgelistet` und steht (alt wie neu) nicht in der Tabelle — deshalb
   steht der Fall mit beiden Läden als Test, nicht als Render.
2. **Gegenprobentest alt rot / neu grün, zwei Tests.**
   `test_die_schreibweisen_variante_wird_zur_einen_zeile_zusammengefuehrt`
   (dieselbe Listung in zwei Schreibungen → EINE Zeile; die
   Zusammenführung trägt der Zwillings-Schlüssel, die Faltung sorgt für den
   einheitlichen Namen des Überlebenden) und
   `test_verschiedene_farben_werden_nicht_zusammengefaltet` („Tiefblau" /
   „Deep Blue" / „kosmisch orange" bleiben vier Zeilen in vier
   Schreibweisen). Dazu
   `test_die_faltung_greift_nicht_nach_kuerzeln` („pistachio bk" bleibt).
3. **Radar-/Katalog-Diffs zeigen nur erwartete Zusammenführungen.**
   Alt/Neu-Render mit identischer Datenbasis (`render_site(…, load_config)`,
   nur nach `/tmp`): **genau zwei Dateien differieren** — `geraete.html` und
   `exporte/geraete-aktuell.csv`; alle übrigen Dateien des Baums byte-
   identisch. Katalogtabelle: **564 Zeilen vorher wie nachher** (keine
   Zeile geht, keine kommt dazu); als Multiset über alle `data-s-*`-Felder
   **mit gefalteter Farbe sind beide Bäume identisch** — die Zeilen
   unterscheiden sich ausschließlich in der Farbschreibweise (98 → 70
   Schreibweisen; die 28 verschwundenen sind exakt die 28 gefalteten
   Schlüssel; Positionen können sich verschieben, weil die Farbe der
   Sortier-Tiebreak des Geräte-Blocks ist). CSV: 75 geänderte Zeilen, **alle
   nur in der Farbspalte** (z. B. `tiefblau→Tiefblau` 2×, `deep blue→Deep
   Blue` 3×, `Cobalt Violet→cobalt violet` 11× — Mehrheitsentscheid).
4. **Suite ohne neuen Rotanteil.** `PYTHONPATH=src pytest -q`, vollständig
   gespeichert in `outputs/rv2-farbfaltung-2026-09-15-suite.txt`:
   **2975 passed / 12 skipped / 1 failed** (362,7 s). Der eine Rot ist die
   bekannte, vorbestehende Pillow-Ausnahme
   `test_geraete_lifecycle.py::test_ein_simulierter_nachtlauf_erzeugt_keine_
   nullzeilen` — **am Basisbaum ohne meine Änderung nachgemessen: fällt
   genauso** (0,1 s). Basisvergleich: RV-3 meldete für dieselbe Basis
   `86800aa` 2968 passed + 4 neue; hier 2968 + 7 neue = 2975. Kein
   Promo-Screenshot-Rot in dieser Umgebung.
5. **Normalisierung im Merge-Layer, Messdaten unangetastet.** Der Diff
   berührt `geraete_bereinigung.py` (+ Testdatei), keine Datei unter
   `data/`, `config/`, `site/` (gerendert wurde nur nach `/tmp`),
   `geraete_db.json` unverändert. `test_die_faltung_laesst_eingabe_und_
   zeilenzahl_unangetastet` hält Eingabe-Dicts und Zeilenzahl fest;
   `test_die_eingabe_wird_nicht_veraendert` (bestehend) bleibt grün.

## 4. Messungen am echten Bestand (14.09., sichtbar = 564 Listungen)

- **Vorher:** 28 `normalisiere`-Schlüssel mit mehr als einer Schreibweise
  (vollständige Liste im Laufprotokoll der Recherche; darunter alle
  „Awesome-*"-Paare des Galaxy S26 FE, `blaugrün/Blaugrün`,
  `himmelblau/Himmelblau`, `jetblack/Jetblack`, `moonstone/Moonstone`).
- **Nachher:** 0. Zeilenzahl 564 → 564.
- Katalogtabelle: 98 → 70 unterschiedliche Farbschreibweisen.

## 5. Grenzen, bewusst so

- **Zwei Läden bleiben zwei Zeilen.** Wer den Befund wörtlich als
  „Saturn-Zeile und Telekom-Zeile werden eine Zeile" liest, dem ist mit
  Datenverlust gedient, nicht mit Wahrheit: 1179 € und 1197 € sind zwei
  Angebote; der Merge-Layer verbietet genau diese Zusammenfassung (Modulkopf,
  Messung 370 → 272). Aufgelöst ist die Dopplung der **Farbe** — das, was
  den Befund als „wirkt wie Datenfehler" tragfähig machte. Diese Entscheidung
  steht hier und im Modulkopf begründet; der Evaluator möge ihr folgen oder
  sie mit der Kardinalregel des Merge-Layers konfrontieren.
- **Der Vertreter ist die Mehrheitsschreibweise des jeweiligen Aufrufs.**
  `bereinige()` läuft zweimal (Bestand, belastbar); die Teilmengen können
  theoretisch verschiedene Mehrheiten haben — nur wenn die prüfbereinigte
  Menge gerade die einzigen Träger der Mehrheitsschreibweise verloren hat.
  Heute nicht beobachtet (beide Aufrufe falten identisch), aber keine
  garantierte Invariante über beide Aufrufe hinweg.
- **Keine neue Zeile im farben.yaml-Sinne kanonisiert:** unbekannte Farben
  bleiben unbekannt; die Arbeitsliste für `config/farben.yaml` (per K-1-
  bewusster Entscheidung des Repos vom 29.08.) nicht angerührt — eine neue
  Farbzuordnung wäre eine `sku_id`-Datenwanderung, kein Anzeige-Fix.
- **Render nicht im Browser angesehen** (Zeitbudget): die Farbspalte ist
  DOM-seitig belegt (`data-s-farbe`, Zelleninhalt, CSV-Spalte); Optik
  ändert sich nicht — dieselbe Spalte zeigt einen anderen String.

## 6. Suite-Beleg

Kurzfassung des `-q`-Laufs (vollständig in
`outputs/rv2-farbfaltung-2026-09-15-suite.txt`):

```
1 failed, 2975 passed, 12 skipped, 73 warnings in 362.71s (0:06:02)
FAILED tests/test_geraete_lifecycle.py::test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen
```
