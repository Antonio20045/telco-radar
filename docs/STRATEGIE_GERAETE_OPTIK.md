# Strategie Optik Geräteseite — Zielbild und Bau-Phasen

**Stand 11.09.2026, abends. Anlass: Antonios Design-Kritik nach dem P1/P2-Live-Stand
(„Design total scheiße, unintuitiv; wieso zwei Graphen, es soll einen geben; eine Million
Unterkommentare; was macht die Unterseite Wettbewerbsradar; Historie sehen und exportieren").
Methode: Design-Workflow mit 3 Auditorinnen (Chart-Reduktion/Entrümpelung, Seitenarchitektur,
Historie/Export), statischem Entwurf mit echten Zahlen und frischem Einkäufer-Sichttest.
Dieses Dokument ersetzt die Skizze von Phase P4 in `STRATEGIE_GERAETESEITE.md` durch ein
konkretes, gesichtetes Zielbild; P3 (Bandabdeckung) und P5 (TCO-Zeitachse) bleiben unverändert.**

## 1. Gemessener Ist-Zustand (warum sich die Seite so anfühlt)

- **Zwei Charts, keiner beantwortet die Leitfrage:** Der obere Chart (G0, Barpreise ohne
  Vertrag, 6 Anbieterserien) besetzt den Prime-Platz; die eigentliche Antwort (Band-Panel
  TCO-24, 5 *andere* Anbieter) liegt darunter. Der G0-Titel behauptet „6-Monats-Vergleich,
  monatlich gemessen" bei real 5 Messtagen in einem Monat. Beide Charts sind 1180-px-SVGs,
  die am Telefon zu Querscroll-Boxen werden; Werte nur als Hover-Tooltip (am Touch nicht da).
- **602 Aufklapper** (418× Rechenweg, 88× „Wie gerechnet?", 88× Kartenklappe), 208
  Buttons/Selects, 145 „führt kein Bündel"-Einzelizeilen, 253× „Beschaffung läuft" doppelt
  pro Modell (Zeile + leere Karte), fünf parallele Zählsysteme („6 Anbieter" ≠ „11 von 21" ≠
  „(29)" ≠ „(418)" ≠ „561 Zeilen").
- **Verwirrung Unterseiten:** Titel/Untertitel von geraete.html klingen selbst wie
  Radar-Inhalte; die Radar-Seite (204 KB, sauber sortiert) hat keinen einzigen eingehenden
  Querverweis pro Gerät; tarife.html ist eine Waise ohne jeden eingehenden Link.
- **Verstecktes, das fertig gebaut ist:** Die Verlaufs-Tafel enthält bereits eine
  funktionierende Einzelgerät-Zeitreihe (89 Geräte, eine Linie je Anbieter, Zeitraumsteuerung,
  Playwright-verifiziert) — nur unerreichbar (kein Reiter-Knopf, toter Deep-Link). Beide
  CSV-Exporte sind tagesaktuell, aber nur auf geraete.html verlinkt (5 duplizierte
  Knopfpaare) und ohne die Kernzahl: TCO-24 je Modell×Anbieter×Band ist nicht exportierbar,
  obwohl alle Summanden in `geraete_tco.json` liegen; der Radar hat gar keinen Export.

## 2. Zielbild — der Entwurf

**Ablage:** `docs/entwuerfe/geraete-optik-2026-09-11/` — `entwurf.html` (statisch, echte
Zahlen, Band-Umschaltlogik) plus Screenshots (`entwurf-1440-top.png`, `entwurf-390-top.png`,
`hauptgraph-klein.png`, `verlauf-d.png`). Lokal ansehen:
`cd docs/entwuerfe/geraete-optik-2026-09-11 && python3 -m http.server 8777` →
`http://localhost:8777/entwurf.html`.

Von oben nach unten: Marke mit zwei Export-Knöpfen; H1 „Ein Gerät im Tarifvergleich" mit
ehrlichem Untertitel und benanntem Radar-Querlink; Reiter
**Vergleich | Wettbewerbs-Radar | Preisverlauf | Gerätekatalog**; zwei Selektoren (Gerät,
Tarifband als Segment-Schalter) und EINE Fußnote (Stand · Geräte · Bänder-Herkunft);
Modellkopf mit der zweiten, getrennten Zahl „Gerätepreis ohne Vertrag"; dann das Herzstück:

- **GENAU EIN Graph-Modul:** sortierte horizontale Balken „TCO-24 je Anbieter" für das
  gewählte Modell × Band, Cent-genau am Balken, Δ zur Vodafone-Referenz, Vodafone als
  Emphasis („unser Angebot"), fehlende Anbieter als EINE Legendenzeile. Über der Falz
  maximal EIN Aufklapper („Wie gerechnet?" mit Formel + Begriffslegende).
- Kompakte Gruppe „Ohne Tarifband" (Unbegrenzt, Händler-Barpreise) statt Mischkarten;
  Bündel als Tabellenzeilen mit je einem schmalen Rechenweg-Aufklapper.
- **Preisverlauf** wieder erreichbar: Barpreis-Punktplot je Anbieter + Wertetabelle, ehrlicher
  Hinweis „TCO-24-Historie wächst ab 12.09." — dieselbe Stelle, an der später die §2a-Linie entsteht.
- Mobil 390: Balkenzeilen gestapelt, Werte gedruckt, kein Querscroll.

**Einkäufer-Sichttest (frische Testerin, keine Vorkenntnisse):** Leitfrage „iPhone 17 Pro im
kleinsten Tarif — welcher Anbieter, was kostet es über 24 Monate?" in **~12 Sekunden, ohne
einen Klick** beantwortet (heute: 4 Interaktionen). Gelobt: eine Leitzahl, Lückentransparenz
unter dem Chart, verteidigbarer Rechenweg je Zeile, saubere Band-Umschaltung. Der Test nennt
Mockup-Grenzen, die der Bau lösen muss: echtes Modell-Umschalten für alle Geräte, TCO-Export,
eindeutige CSV-Beschriftung, sortierbare Tabelle.

## 3. Bau-Phasen (Ersetzung für P4)

Jede Phase: eigener Lauf mit Screenshot-Selbstkontrolle (Vorher/Nachher, 1440+390, selbst
angesehen), Browser-Tests rot-vor-grün, `pytest -q` komplett, `scripts/pruefe_portal.py`;
Abnahme gegen den Entwurf als Zielbild. Keine data/state-Commits.

**O1 — Eine-Graph-Hauptansicht.** Sortierte Balken TCO-24 mit Wertzahlen und Δ; G0 aus der
Vergleichsansicht heraus (wandert in O4 nach Verlauf); eine Legendenzeile für Fehlende;
eine Fußnote statt fünf Zählsysteme; „– N Anbieter"-Suffixe weg; falscher G0-Titel entfällt
mit. *Abnahme:* Leitantwort über der Falz ohne Klick, ohne Hover, ohne Querscroll (1440 und
390); ein Aufklapper über der Falz.

**O2 — Entrümpelung.** Karten als Tabellenzeilen (4 Kernspalten), je Zeile ein
Rechenweg-Aufklapper; „Beschaffung läuft"-Zeilen und leere Platzhalterkarten streichen;
145 Fehlend-Zeilen durch die Legendenzeile ersetzen; Alarmtabelle (48) und
„Bei Wettbewerbern gelistet (29)" von der Vergleichsansicht auf die Radar-Seite verschieben.
*Abnahme:* <details> über der Falz ≤ 1, gesamt deutlich unter 100 im Hauptpfad; Höhenmessung
11b weiter bestanden.

**O3 — Rollen und Navigation.** Untertitel ehrlich; Reiter „Vergleich | Wettbewerbs-Radar |
Preisverlauf | Gerätekatalog" (Radar = Link auf wettbewerbsradar.html); je Radar-Geräteblock
Querlink „Dieses Gerät im Vergleich"; Portfolio-Tafel als Abschnitte auf den Radar;
tarife.html erreichbar machen. *Abnahme:* Einkäufer-Sichttest wiederholt: Rollenfrage („wo
bin ich, wo ist der Radar") ohne Erklärung richtig; Sichttest-Verbesserungen umgesetzt
(Modell-Umschalten für alle 88 Geräte, sortierbare Tabelle).

**O4 — Verlauf und Export.** Verlaufs-Reiter zurück (bestehende Einzelgerät-Zeitreihe
nutzen, G0 dort integrieren); NEU `geraete-tco.csv` (eine Zeile je Bündel: Modell, Speicher,
Anbieter, Anbietertyp, Tarif, Band, Zuzahlung, Tarif/Monat, Geräterate, Laufzeit,
Anschlusspreis, TCO-24, abgerufen_am, Quelle + SIM-only-Zeilen) am bestehenden Ort
`geraete_export.py`; Export-Links einmal zentral in der Kopfzeile plus Radarseite (statt
5 Duplikate); Radar-Export (TCO + Händler-Barpreis in einer Datei, %-Spalte aus
wettbewerbsradar.py als weiterer Konsument derselben Rechnung). *Abnahme:* Export enthält
589 Bündel mit Band-Spalte; Kopfzeilen-Link von beiden Seiten; CSV-Konventionen (Semikolon,
BOM, Dezimalkomma) wie bestehende.

## 4. Entscheidungen in diesem Dokument (Klasse C, revidierbar)

1. **Ein Graph-Modul im Hauptbereich** (Balken statt Zeitreihe): die TCO-Historie wächst erst
   ab 12.09.; Balken lügen nicht über fehlende Messpunkte. Sobald ≥ 3 Messtage da sind,
   rückt die Zeitreihe (P5) in denselben Slot — ein Slot, ein Graph, nie zwei.
2. **Zwei Unterseiten bleiben** (Option A, auftragskonform §2): Radar = Portfolio-Übersicht
   („wo sind wir zu teuer"), Geräte = Einzelgerät-Tiefe. Option B (Zusammenlegung) verworfen:
   sie würde ~200 KB + 88 Blöcke auf die ohnehin überladene Seite laden, dem Radar die eigene
   URL nehmen und bedürfe einer neuen Entscheidung gegen den Auftragswortlaut. Fällt die
   Verwirrung nach Option A weiter, erneut vorlegen.
3. **Karten werden Tabellenzeilen:** auf 390 px ruhiger lesbar; Anbieter-Suche/-filter
   erübrigen sich bei 4–7 Zeilen je Bandliste.

## 5. Entscheidungen von Antonio (11.09.2026, abends)

1. **Entwurf FREIGEGEBEN** („ist okay"). Bau der Phasen O1–O4 als eigener Lauf in der
   Nachfolgesession; Übergabe-Prompt: `AUFTRAG_OPTIK_GERAETESEITE.md` (Repo-Wurzel).
2. **Portfolio-Abschnitte gehen auf die Radar-Seite** (empfohlene Option A angenommen);
   kein vierter Reiter auf der Geräteseite.

## 6. Artefakte und Beweise

- Entwurf + Screenshots: `docs/entwuerfe/geraete-optik-2026-09-11/` (statisch, echte Zahlen
  aus data/state, Band-Umschaltung Klein/Mittel/Groß funktionsfähig; Palette per
  dataviz-Validator geprüft).
- Audit-Artefakte (Falz-Screenshots, DOM-Messungen, Extraktion der unerreichbaren
  Verlaufs-Tafel, Sichttest-Blickpunkte): `/tmp/design-geraete-20260911/` (flüchtig).
- Verbindung zu bestehenden Plänen: ersetzt P4 aus `STRATEGIE_GERAETESEITE.md`; P3
  (Bandabdeckung) und P5 (TCO-Zeitachse) unverändert; UX-Befund-IDs UX-2/3/4/5/6/7 und
  RM-1/2/3 werden durch O1–O4 abgedeckt.

## 7. Umsetzungsstand

- **O1 FERTIG** (gemergt als `0546c6c`, 14.09.2026): Eine-Graph-Hauptansicht „TCO-24 je
  Anbieter" mit gedruckten Werten + Δ, Vodafone-Emphasis, Legendenzeile statt 145
  Fehlend-Zeilen, 88 Blöcke → 1 gewähltes Modell, HTML 3,9 → 1,5 MB, Falz-Kriterium 11c neu.
  Details im Merge-Commit; Evaluator 8/9 ohne S1/S2.
- **O2 FERTIG** (gemergt als `d140da6`, 15.09.2026): Bündelkarten → Tabellenzeilen
  (4 Kernspalten + je 1 Rechenweg-Aufklapper; Pflichtzeile, Belege, Abrufdatum erhalten,
  A6-Zählung testgesichert), Gruppe „Ohne Tarifband", Alarmtabelle (48 Zeilen, 4 Chips) und
  „Bei Wettbewerbern gelistet" (29) auf `wettbewerbsradar.html` umgezogen — Geräteseite ohne
  Reste (Container, JS, Strings). Gemessen: pytest 2987/3/14 (3 vorbestehende Pillow-Rote),
  pruefe_portal 17/1 (nur 8b vorbestehend), 11b 2400/1894 px, 11c Graphfalz 820 < 844,
  `<details>` gesamt 24 / 0 über der Falz (1440+390). Belege:
  `/tmp/optik-o1-o4/o2/` (baubericht.md, evaluator.md, rot-vor-gruen.txt, Screenshots).
  - Evaluator: **BESTANDEN MIT AUFLAGEN** (9/9 Kriterien, kein S1). Befunde:
    **S2** — Merge ohne `site/`-Neurender; committetes `site/geraete.html` ist noch der
    O1-Stand. Regel bleibt: Render-Kommits erst nach O4 oder auf Antonios Wunsch; der
    nächtliche `geraete.yml`-Cron heilt selbst — **nach Antonios Push live gegenprüfen**.
    **S3 → O3** — der Modell-Umschalter zeigt Bündel-ZEILEN nur fürs Vorgabegerät (19 von
    423); die alte „Alle Bündel als Tabelle" fiel in O2 ersatzlos weg. O3 muss den
    Modellwechsel für alle Geräte mit echten Zeilen schließen. **S4 → O3** —
    überzeichnender Template-Kommentar („des GEWÄHLTEN Modells"), tote View-Felder
    (`tabelle`/`zeilen`/`_delta`/`hat_tco`), ID-Rest `gr-karten-hinweis`; Radar mobil
    ~18.500 px ohne Höhengrenze (Beobachtung, O3/O4 im Blick).
  - O1-Restpunkte, an O3 übergeben: Wortlaut „führt kein Bündel" (`geraete_tco_band.py:388`,
    Entwurf sagt „fehlt"); zwei tote `or True`-Asserts (`test_geraete_vergleich.py:194`,
    `test_geraete_anbieterzaehlung.py:65`).
