# P5/E5 — CLAUDE.md-Übergabe zur Geräteseite auf EINEN Stand (Auftrag 5)

Auftrag: §5-Tabellenzeilen und §8a der Geräteseite konsolidieren (E2–E6 +
P1–P5), die 8 überholten Stellen aus `befunde/auto-doku.md` §3 dabei
mitnehmen, vier neue Fallstricke in §6, sonst wortgleich. Nur `CLAUDE.md`
geändert (git diff: **+131/−66 Zeilen, 1 Datei**); kein Test liest
CLAUDE.md (gegreppt — nur Kommentar-Referenzen). Nicht committet, nichts
unter `data/state` geschrieben.

## Was geändert wurde

| Stelle | Vorher | Nachher |
|---|---|---|
| §5 Seitentabelle | **5 Tabellenzeilen** zur Geräteseite (TCO-first 04.09. + „Stand DAVOR" + 29.08.×2 + 03.09.) | **EINE Zeile**, Stand 18.09.2026: vier Reiter Vergleich/Radar/Preisverlauf/Gerätekatalog mit den P1–P5-Regeln (Preis-Klick-Rechenweg, Balken-Grafik, Modell-Wähler oben + Wochenkarte, Modellebene + Umschalter Barpreis/TCO), Leitzahl = größte Schrift, Kriterien 13/14/15, Sprungkette über EINEN `modell_schluessel`, 6 Export-Knöpfe am Fuß, Fußlink `geraete-quellen.html` |
| §5 Positionskarten-Block | 32 Zeilen Beschreibung einer seither GELÖSCHTEN Karte (`geraete_karte.py`, seit 30.08. weg) + Regel-Tabelle | 11-Zeilen-Lehren-Absatz: Y-Achse gehört dem Preis, Preispunkte statt SKUs, Läden- nicht Marken-Zählung; Baugeschichte → `outputs/` und git |
| §5 Navigation (3 Stellen, auto-doku §3.2) | „FÜNF … plus Geräte, sobald die Schwelle nimmt" · „hat damit **sechs** Einträge" (Newsletter-Block) · Tabellen-Kopf „davon **fünf** in der Navigation (Stand 09.08.)" · „sechster Eintrag … im Moment AUS" | überall **Stand 18.09.2026: sieben**, nachgezählt; sechs/historisch gekennzeichnet, Mechanik-Absätze unangetastet |
| §5 Veröffentlichungsschwelle | „zwei Hersteller **in der Positionskarte**" | „zwei Hersteller **im Katalog**" (Schwelle zählt laut `geraete_view.py:1681` Hersteller über den Katalog; 3/20/20 bleiben) |
| §6 Fallstricke | — | **4 neue** (s. u.); alle bestehenden unberührt (gegreppt: „Sägezahn", „202", „Zustandsdimension", „robots" bleiben) |
| §8a Kopf | E2–E6 oben mit alter OFFEN-Liste | **Neue Zeile „Zuletzt erledigt (18.09.2026): Strategie Geraete v3 — P1–P5"** mit Phasen-Tabelle (Merges P1 `63e693c`, P2 `64a8f2a`, P3 `6a37ceb`, P4/P4b `f006660`, P5 Arbeitsbaum) + **neue OFFEN-Liste (7 Punkte)**; E2–E6-Block darunter, seine alte OFFEN-Liste durch 4-Zeilen-Brücke ersetzt, „0 Auto-Einträge"-Satz mit Korrektur-Klammer (16 Auto-Einträge, Bot-Commit 11:59 vor CLAUDE.md-Commit 13:05) |

## Neue OFFEN-Liste (Punkte 1–8)

URL-Sync im Verlauf (P2) · Rot-Deckel-Test nur Katalog (P4b) · PM-6-Deckel
**eilt: 5-MB-Grenze fällt rechnerisch am 20.09., Entscheidung 01.10. liegt
danach; 1.391 B/Paar statt „~7 KB"** (E4) · Telekom-202 = Antonios
Entscheidung (R3) · iPad-Anker-Wirkung nach nächstem Nachtlauf (E3,
284→281 Zeilen) · disjunkter Deep-Link (P2 S3-2) · Betrieb 3+1
Protokollzeilen + Tag-2-Sichttest · **8. S4-Rest Kosmetik (aus E5,
hierher gezogen — Closing des Prüfer-S4 am 18.09.: CLAUDE.md zeigt
keinen „E5-Schlussliste"-Zeiger mehr, sondern den internen Zeiger
„OFFEN-Punkt 8 dort"; dieser Punkt ist gemeint)**: Einheit in den
Export-Knopfbeschriftungen inkonsistent, 2 der 6 Leer-Tests wären an
`main` schon grün gewesen.

## Die 4 neuen Fallstricke (§6, je mit Datum und Messzahl)

1. `[hidden]` vs. `display:flex` — 81 px sichtbare Leer-Leitzahl; Tests
   messen SICHTBARKEIT (computed display + Boxhöhe), nie das Attribut.
2. Zähler mit leerem Lookup meldet „bestanden" (Rot „5" vs. real 12);
   Gegenprobe mit gestelltem Treffer; P4b-S1 = Assert auf `e.hidden`.
3. CSS-Spezifität: `.src-table a` schlug `.gr-sprung` (11 Vollrot-Links);
   Akzentfarbe erst als Regel, wenn der Test den rgb-Wert aus `var(--red)`
   misst.
4. Screenshots an den Lead: CDN-Link (Vision-Analyse nimmt nur
   Remote-URLs) + Messformel in derselben Übergabe.

## Selbst nachgemessen (nicht geglaubt)

- Navigation `site/geraete.html`: **7 Einträge** (Diese Woche, Meldungen,
  Differenzierung, Wettbewerb, Geräte, Quellen, Newsletter).
- Reiter im Template `geraete.html.j2` (Z. 160–168): **Vergleich**
  (aria-selected=true) · Radar · Preisverlauf · Gerätekatalog.
- Export-Knöpfe: **6** Links in `.gr-export-fuss` (Alle 636 / Historie 814
  / Bündel-TCO 837 / Radar 467 / Katalog Barpreis 116 / Katalog TCO 116
  Zeilen) — P4/notiz-d4: „6 Knöpfe aus der Kopfzeile in den Fuß" (mobil
  vorher y=372 im Hero).
- `pruefe_portal.py`: Kriterium **13** Fließtext-Deckel (Z. 1036), **14**
  kein Fließtextblock unter Grafiken (Z. 1055), **15** Klickbarkeit
  (Z. 395) — existieren wirklich.
- `[hidden]{display:none!important}` steht global in `style.css`
  (P4b-Kommentarkop bestätigt).
- Wochenkarte: `#wr-bewegungen` „Was diese Woche auffällt – letzte 14
  Tage (12 Bewegungen)" sitzt in `#tafel-verlauf` (P4/2a).
- Kein Test liest CLAUDE.md; TCO-first/G1/G2 kommen in §5 nicht mehr vor
  (§8a-Historie bleibt datiert stehen, wie der Auftrag es verlangt).

## Bewusste Grenzen

- Die Phase-R/R2/R3/6/6a-Blöcke in §8a blieben unangetastet (Historie,
  vom Auftrag nicht gefordert); sie tragen Daten und sind als Chronik
  lesbar.
- §8a-Phasen-Tabelle nennt P5 „(Arbeitsbaum, 18.09.)" — der Merge ist
  Lead-Sache; wenn er Commits erzeugt, die Zeile auf den SHA nachziehen.
- Suite nicht gelaufen: reine Dok-Änderung, kein Code berührt
  (`git diff` nur CLAUDE.md von mir; Fremdänderungen im Baum stammen aus
  den Parallel-Agenten E1–E4).
