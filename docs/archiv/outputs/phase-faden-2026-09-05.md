# Phase Faden — eine Seite, eine Frage, ein Graph (05.09.2026)

Auftragsgrundlage: `BRIEF_FADEN.md` (workspace-engineer), aufbauend auf dem Konzept in
`/Users/antonio/.openclaw/workspace-vodafone/REVIEW_2026-09-05-nachmittag.md` (Abschnitt
„Konzept ‚Roter Faden‘"), Senecas Freigabe vom 05.09. nachmittags mit drei eingebauten
Auflagen (Titel sachlich statt Frage, Händler-Lücken mit Datum statt Versprechen,
Ampel-Kacheln erst hinter der Klappe). Branch `openclaw/ticket-faden`, Worktree.

## Ergebnis in einem Satz

Die Geräteseite beantwortet jetzt genau eine Frage — „Was kostet dieses Gerät?" —, in
dieser Reihenfolge: Titel, große Geräteauswahl, eine Antwortzeile mit Anbietern, der
Zeitreihen-Graph G0 als einzige Grafik, die Anbieterkarten, und alles Analytische
(Ampel-Kacheln, Preis-Alarm-Tabelle, Bündel-Tabelle, Tarif-Maßstab) hinter einer
einzigen „Details"-Aufklappung; die Reiterleiste trägt nur noch „Vergleich" und
„Gerätekatalog".

## Was gebaut wurde

| Baustein | Wo | Die eine Regel, die ihn trägt |
|---|---|---|
| **Titel** | `page-hero` H1 + `<title>` | „Gerätepreise im Vergleich" ersetzt die gescheiterte Frage-Überschrift „Dieses Gerät — wo kaufe ich es am günstigsten?" (Antonio: „Digga, spinnst du?" — umgangssprachlich, „ich" mehrdeutig) |
| **Geräteauswahl groß und sofort** | `.gr-msel--gross` (neue CSS-Klasse) | Serife 20 px statt Grotesk 14 px, mehr Innenabstand — sie steht direkt unter der Reiterleiste, nichts mehr davor (Ampel-Kacheln und „ohne Zuordnung"-Hinweis sind gewichen bzw. verschoben) |
| **Die eine Antwortzeile** | `geraete_tco_karten.modelle()` → `m["antwort"]`, gerendert in `.gr-antwort` | Zwei unabhängige Minima mit je eigenem Anbieter: der **Gerätepreis** zählt auch die Vodafone-Näherungskarte (ihr Barpreis ist real gemessen, nur ihr Bündel ist gerechnet), der **Tarif-Gesamtpreis** ausdrücklich NICHT (eine Referenzrechnung ist „kein Angebot", QA-Befund S3 vom 04.09.). Am echten Bestand exakt der Beispielsatz aus dem Auftrag: „Günstigster Gerätepreis: 1.199,90 € (Vodafone) · günstig mit Tarif: 1.619,64 € (1&1)" |
| **G0 als einzige Grafik** | `geraete.html.j2`, Block „G1 (der TCO-Balkenvergleich) wird bewusst NICHT mehr gerendert" | Der Aufruf `{% if m.svg %}…{% endif %}` ist aus der Vorlage gelöscht — **die Rechnung bleibt im Code** (`geraete_tco_grafik.balken()`, `m["svg"]`/`m["legende"]` werden in `geraete_tco_view.aufbereiten()` weiterhin gefüllt, nur nicht mehr aufgerufen) |
| **Serie-startet-Beschriftung** | `geraete_tco_grafik.zeitreihe()` | Ein einzelner Messpunkt bekommt einen sichtbaren `<text>` „Serie startet · 1. Messpunkt ⟨Datum⟩" statt nur einem Tooltip — Antonios QA-Befund 3 („Telekoms Einzel-Punkt liest sich als 'keine Werte'"). Die Ausrichtung hängt von der Bildhälfte ab (`text-anchor="end"`/`"start"`), sonst läuft die Beschriftung eines rechten Randpunkts in die Anbieter-Legende — beim ersten Rendern am echten Bestand gesehen und korrigiert, nicht vorhergesagt |
| **Händler-Lücken mit Datum** | `haendlerkarte(name, seit)`-Makro + `.gr-g0-haendler`-Legende | „Händler — Beschaffung läuft seit 5. September 2026" statt des nackten „Beschaffung läuft" — nennt den Start, kein erfundenes Lieferdatum. Eine Stelle setzt das Datum (`{% set haendler_seit = "2026-09-05" %}`), beide Verwendungsstellen lesen davon |
| **Eine Details-Aufklappung** | `<details id="gr-details">` in `geraete.html.j2` | Zieht die Ampel-Kacheln (`.gr-chips`) und drei Analysten-Tabellen (`#gr-alarme`, `#gr-tco-tabelle`, `#gr-massstab`) als verschachtelte `<details>` zusammen. Steht EINMAL, nicht je Modellblock — ihr Inhalt ist seitenweit (alle Geräte), nicht auf das gewählte Modell eingegrenzt, und weil je Auswahl nur EIN Modellblock sichtbar ist, steht sie effektiv dort, wo gerade gelesen wird. Die Anbieterkarten selbst bleiben AUSSERHALB — sie sind die Antwort, keine Analyse |
| **Reiterleiste auf zwei Knöpfe** | `.gr-reiter` | „Preis- und TCO-Historie" und „Portfolio" verlieren ihren `<button>`; ihre Tafeln (`#tafel-verlauf`, `#tafel-portfolio`) bleiben **unverändert im Dokument** — nicht gelöscht, nur nicht mehr verlinkt (PM entscheidet separat über ihr Schicksal) |

## Der Fallstrick, der erst beim Ansehen auffiel

Die erste Fassung der Einzelpunkt-Beschriftung stand mit `text-anchor="middle"` zentriert
über dem Punkt. Am echten Bestand gerendert und **angesehen** (nicht nur getestet) lief
sie bei jedem Punkt in der rechten Bildhälfte — und Einzelpunkte liegen oft dort, der
jüngste und einzige Messtag — zur Hälfte in die Anbieter-Legende hinein, die direkt
rechts neben der Zeichenfläche beginnt. Kein Test hätte das gemeldet: alle Zeitreihe-Tests
prüfen nur, DASS der Text im SVG steht, nicht WO. Die Ausrichtung hängt jetzt von der
Bildhälfte ab (rechte Hälfte → Text wächst nach links, linke Hälfte → nach rechts) und
bleibt damit innerhalb der Zeichenfläche.

## Die zweite Entscheidung, die erst am echten Bestand fiel

Der Auftrag nennt die Antwortzeile mit einem konkreten Beispiel
(„Günstigster Gerätepreis: 1.199,90 € Vodafone · günstig mit Tarif: 1.619,64 € 1&1"), aber
nicht die Regel dahinter. Die naheliegende erste Fassung nahm für BEIDE Zahlen dieselbe
Menge — nur echte, kaufbare Bündelangebote (`belastbar and not naeherung`) — und ergab am
Bestand „Günstigster Gerätepreis: 1.315,00 € (o2)", weil Vodafones Karte für dieses Gerät
eine Referenzrechnung ist, kein echtes Bündel. Das traf den Auftragssatz nicht. Die
richtige Lesart, am Beispielsatz nachgemessen: der **Gerätepreis** ist ein reiner
Barpreis und braucht kein eigenes Tarifbündel — Vodafones Barpreis ist real gemessen, nur
ihr Bündel ist gerechnet, also zählt ihre Karte hier mit. Der **Tarif-Gesamtpreis**
dagegen ist ein Angebot, das man wirklich kaufen kann — eine Näherungskarte („Referenzrechnung,
kein Angebot", QA-Befund S3 vom 04.09.2026) darf diese Zahl nicht führen. Beide Zahlen
haben deshalb verschiedene Vergleichsmengen, mit Absicht:
`geraete_tco_karten.modelle()` filtert den Gerätepreis über ALLE `vergleichbar`en Karten
(inklusive Näherung), den Tarif-Gesamtpreis nur über `angebote` (`belastbar and not
naeherung`). `tests/test_geraete_tco_hauptansicht.py::test_antwortzeile_der_tarifgewinner_ist_kein_naeherungsangebot`
hält das gegen den ganzen Bestand fest.

## Suite

**2 failed / 2717 passed / 14 skipped** — exakt der im Auftrag genannte Maßstab (2 failed
/ ~2698 passed / 14 skipped), die zwei roten Tests sind namentlich dieselben,
vorbestehenden (`test_promo_seite.py::test_die_echten_screenshots_bestehen_die_pruefung`,
`::test_der_leere_screenshot_wird_nicht_ausgeliefert`), unverändert reproduziert. Die
Differenz von +19 zum genannten „~2698" sind die neuen Tests dieser Phase:

- `tests/test_geraete_faden.py` (neu, 11 Tests): Antwortzeile-Position, G1-Abwesenheit,
  Details-Verschachtelung, Reiterleiste, Titel, Händler-Datum.
- `tests/test_geraete_zeitreihe.py` (+4): Einzelpunkt-Beschriftung, isolierter Punkt vs.
  verbundene Linie, gemischte Reihen.
- `tests/test_geraete_tco_hauptansicht.py` (+3): Antwortzeile-Gewinner am echten Bestand,
  Gegenprobe „kein Näherungsangebot gewinnt die Tarif-Zahl", die verschobene
  Balkenlängen-Zusicherung (siehe unten).
- `tests/test_geraete_rahmen.py` (Titel-Test umbenannt, nicht neu gezählt — er hielt bis
  heute die jetzt umgekehrte Entscheidung fest).

**Ein bestehender Browser-Test ist an die neue Struktur angepasst, nicht gelöscht:**
`test_die_balkenlaenge_entspricht_dem_betrag` prüfte G1s Balkenlänge am gerenderten
`svg.gr-g1` — das gibt es in dieser Ansicht nicht mehr. Da die Balkengeometrie
servergerechnet ist (`_skala()`), nicht CSS-Layout, ist der Test als **statischer** Test
nach `tests/test_geraete_tco_hauptansicht.py` gezogen und prüft `geraete_tco_grafik.balken()`
direkt — dieselbe Zusicherung, kein Browser mehr nötig.

**Zwölf Klick-Ziele in `tests/test_geraete_reiter_browser.py` mussten auf die entfernten
Reiter-Knöpfe reagieren.** Die Tafeln `tafel-verlauf` und `tafel-portfolio` sind
unverändert und weiterhin ausführlich getestet (Preisverlauf-Reiter, Lifecycle-Reiter) —
nur ihr Zugang per Klick ist weg. Ein neuer Helfer `_zeige_tafel(seite, id)` ersetzt den
Klick durch denselben DOM-Effekt, den `app.js`s `zeige()` auch hätte (`gr-tafel--aus`
umschalten), und ist an sieben Stellen eingesetzt (`_stelle_daten`, `_waehle_geraet`,
`_frisch`s Nachbarschaftstest, drei Parametrisierungen, ein Direktaufruf). `_frisch()`
öffnet jetzt zusätzlich `#gr-details` (die neue äußere Aufklappung) — ein `<details>`
versteckt seine Kinder transitiv per UA-Regel, ein offenes `#gr-alarme` blieb sonst
unsichtbar, solange sein neuer Elternknoten zu ist.

## Live gerendert und angesehen

`render_site()` gegen den echten Bestand (`data/state/`, `data/reports/`) gelaufen, per
Playwright auf 1440×1000 und 390×1200 fotografiert:

- **1440 px**: Titel, Reiterleiste (zwei Knöpfe), große Auswahl, Antwortzeile exakt wie im
  Auftragsbeispiel, G0 mit lesbaren Einzelpunkt-Beschriftungen (keine Legendenüberlappung
  mehr nach der Korrektur), vier Anbieterkarten, Händler-Karten mit Datum — alles ohne
  Klick sichtbar oberhalb der zugeklappten „Details".
- **„Details" geöffnet**: vier Ampel-Kacheln („16 Kritisch … 10 Bestpreis"), vier
  eingeklappte Tabellen-Aufklapper darunter — genau der Inhalt, der vorher offen im
  Lesefluss stand.
- **390 px**: kein waagerechtes Scrollen (automatisiert gehalten von
  `test_kein_reiter_rollt_auf_dem_telefon_waagerecht`, jetzt über beide ungeknopften
  Tafeln hinweg gemessen).

`scripts/pruefe_portal.py`: **16 bestanden / 1 durchgefallen** (Kriterium 8b, leere
Promo-Bilder — vorbestehend, siehe Handover-Eintrag zu R2/R3, nicht Teil dieses Auftrags).
Kriterium 11 (Geräteradar-Struktur) ist auf die neue Reiter- und Grafikzahl umgestellt und
BESTANDEN.

## Site-Artefakt

`render_site()` mit echtem `Config` (`load_config(root)`) gelaufen. Diff gegen den
committeten Stand: nur `site/geraete.html` und `site/style.css` — `site/data/keyword-index.json`
ist die bekannte Datums-Zeitbombe (`stand` gegen `date.today()`) und ist auf den
committeten Stand zurückgesetzt (`git checkout -- site/data/keyword-index.json`), wie es
der Handover für genau diese Datei vorschreibt.

## Was dieser Bau bewusst NICHT anfasst

- Die Startseite — eigener Schritt danach, laut Auftrag.
- G1-Balken-Code (`geraete_tco_grafik.balken()`, `legende()`) — Datenquelle bleibt, nur
  der Templateaufruf ist geloescht.
- Zeitreihen-Logik (G0, außer der Einzelpunkt-Beschriftung und ihrer Ausrichtung),
  Karten-Logik, Händler-Makro-Inhalt — Zustand wie live, nur die Datumszeile ergänzt.
- `#tafel-verlauf` und `#tafel-portfolio` selbst — unverändertes Markup, nur ungeknopft.

## Offen

1. **Die Existenz-Frage der Ampel-Kacheln ist PM-Sache**, nicht dieser Bau — sie stehen
   jetzt zugänglich hinter der Klappe, nicht gelöscht.
2. **Das Schicksal von „Preis- und TCO-Historie" und „Portfolio"** (eigene Seiten? ganz
   weg? zurück in die Leiste?) ist ausdrücklich nicht entschieden.
3. **`pruefe_portal.py` Kriterium 8b** (leere Promo-Bilder) bleibt offen, vorbestehend.
4. Nach diesem PASS folgt laut Hausregel der Produkt-Review des PM (Nutzerrolle,
   Screenshots) — erst dessen Ergebnis macht den Deploy zur Meldung.
