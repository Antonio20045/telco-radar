# Auftrag: EINE Geräteseite — Wettbewerb auf Anhieb, belegte Zahlen

**Anlass: Antonios Durchklicken des Live-Stands am 16.09.2026 (O1–O4 waren gerade
ausgeliefert). Seine drei Befunde sind die Anforderung, im Wortlaut:**

1. *„Wieso gibt es jetzt zwei Unterseiten: Geräte und Wettbewerbsradar? Das ist
   absolute Scheiße. Geräte und [man] auf Anhieb direkt versteht, was die
   Wettbewerber machen."*
2. *„[Wir] möchten wissen, wie viel kostet es den Kunden bei der Telekom, ein
   Google Pixel 11 Pro zu finanzieren mit einem mittleren Tarif."* — dazu die
   Nebenbeobachtung: *„hängt das nicht auch davon ab, welches Modell? Ein
   iPhone 17 Pro, kann man das mit einem kleinen Tarif finanzieren? Ich weiß
   es nicht."* (Verfügbarkeit von Modell × Tarifband schwankt je Anbieter —
   das ist heute unsichtbar.)
3. *„Wenn zum Beispiel hier am Anfang bei den Balken, da sieht man auch gar
   nicht, wie wir auf diese Werte gekommen sind … Man kann hier nirgendwo auf
   den Link drücken, auf eine Quelle. Also auch absolut intransparent."*

## Was das heißt

### B1 — EINE Seite, nicht zwei (kassiert die Option A)

`docs/STRATEGIE_GERAETE_OPTIK.md` §4.2 hatte bewusst zwei Unterseiten
(Option A) gewählt und geschrieben: *„Fällt die Verwirrung nach Option A
weiter, erneut vorlegen."* Sie ist weiter gefallen — Antonio hat sie nach dem
Live-Ansehen kassiert. Es gibt künftig **eine** Seite (`geraete.html`), auf der
man **auf Anhieb** versteht, was die Wettbewerber machen. Was heute auf
`wettbewerbsradar.html` lebt (Alarmtabelle 48 Zeilen, „Bei Wettbewerbern
gelistet", Lifecycle-/Portfolio-Sektionen, Wochenkarte), wird in diese eine
Seite integriert — als Abschnitt/Ansicht/Reiter ist Designfrage, nicht Vorgabe.

Zu bedenmen (nicht als Argumente gegen die Zusammenlegung, sondern als
Randbedingungen):

- **Die Infrastruktur dafür existiert:** das Lazy-Fragment
  (`site/data/geraete-buendel.html`, 87 Container, geladen beim ersten
  Modellwechsel) zeigt, wie schwere Inhalte ohne Seitenaufladung nachkommen.
- **Höhenbudgets neu denken:** die Radar-Inhalte allein sind mobil ~20.400 px
  hoch; die Geräte-Reiter stehen unter 3000 px je Tafel (11b, aktuell tco
  2844 — nur 156 px Luft). Eine Zusammenlegung braucht eine Antwort auf die
  Gesamthöhe (Aufklapper, Deckel mit „alle anzeigen", gedeckelte Vorschau),
  keine neue harte Grenze ohne Messung.
- **Alt-URL:** `wettbewerbsradar.html` steht in Mails/Lesezeichen —
  Meta-Refresh-Weiterleitung nach dem Muster `_redirect_html()` in
  `report/html.py` (die alten Dateinamen der Website laufen genauso weiter).
- **Deep-Links und Querlinks bleiben funktionsfähig:** `?modell=` wird beim
  Laden ausgewertet (O3); die 88 Radar-Querlinks werden zu In-page-Sprüngen.
- `tests/test_suche_page.py` nagelt die Navigationseinträge fest, und
  `pruefe_portal.py` Kriterium 11 liest die Alarmtabelle bislang von der
  Radar-Datei — beides mitziehen.

### B2 — Die Leitfrage ist das Organisationsprinzip

*„Was kostet es den Kunden, Gerät X bei Anbieter Y mit Tarifband Z über 24
Monaten — und gibt es diese Kombination dort überhaupt?"* Das ist eine Frage
über **Anbieter × Modell × Band** — genau die Achsen, die der Bestand führt
(`geraete_tco.json`, Band-Spalte im Export). Zwei Forderungen daraus:

- **Verfügbarkeit sichtbar machen:** fehlt ein Anbieter in einem Band, muss
  die Seite sagen, DASS er fehlt — und idealerweise warum („kein Bündel in
  Klein erhoben" vs. „verkauft nur im Bündel ohne Band"). Das ist zugleich
  **P3 „Bandabdeckung"** aus der Strategie — Antonios Nebenbeobachtung ist
  der Anwendungsfall dafür. Die heutige Legendenzeile unter dem Graphen
  nennt Fehlende nur en bloc.
- **Antonios Beispiel durchspielen:** Google Pixel 11 Pro × Telekom × Mittel
  muss ohne Erklärung beantwortet sein. Telekom liefert seit dem Tageslauf
  (15.09.) Daten — prüfen, ob für DIESes Beispiel Bündel im Bestand stehen;
  wenn nicht, zeigt die Seite ihre Lücke ehrlich („Datenstand fehlt – Quelle
  in Vorbereitung" ist der etablierte Leerzustand).

### B3 — Jeder Balken trägt seinen Beleg

Der Balkengraph ist das Erste, was liest, wer die Seite öffnet — und heute
die einzige Stelle ohne Quelle. Zwei Forderungen:

- **Quelle je Balken:** jede Balkenzeile (je Anbieter) bekommt ihren Beleg-
  Link auf das erhobene Angebot des Anbieters (die Belege existieren — sie
  stehen je Bündelzeile im Rechenweg-Aufklapper und als `Quelle`-Spalte in
  `geraete-tco.csv`). Ein Balken ohne eigene Belegkombination (weil z. B.
  zwei Bündel aggregiert sind) verlinkt auf die zugehörigen Zeilen darunter
  (Anker).
- **Rechenweg sichtbar:** „Wie gerechnet?" erklärt heute die Formel einmal
  für alle — das bleibt, aber die Zuordnung Balken → Zeile(n) → Beleg muss
  ohne Erklärung auffindbar sein (Projektregel: **jede Zahl auf der Seite
  ist belegt**; der Redakteursgrundsatz der Nachrichten-Seite gilt hier
  genauso).

## Offene Punkte, die MIT diesem Auftrag gehören

- **P3 Bandabdeckung** — siehe B2; die Messdaten dafür stehen im Bestand.
- **Test-Leer-Sicherungen** (O4-Evaluator S3): fünf Zähler ohne in-sich-
  Leere-Sicherung (z. B. SIM-only-Test grün bei leerem Bestand) — je eine
  `assert`-Zeile, billig, beim Übernehmen der betroffenen Tests erledigen.
- **Export-Knöpfe mobil** (bewusst weggeblendet, Falz 810/844): bei der
  neuen Einseiten-Struktur neu bewerten — der Export ist Antonios Werkzeug,
  nicht Zier.
- **Alarm-Zeilen im Radar-Export** (O4-Evaluator S3: `wettbewerbsradar.csv`
  deckt 2 von 4 Zahlensektionen): nach B1 neu entscheiden, wie der Export
  der EINEN Seite heißt und was er enthält.

## NICHT Teil dieses Auftrags (später, eigene Termine)

- **P5 TCO-Zeitachse** (ersetzt ab ≥3 Messtagen die Balken im selben Slot —
  „ein Slot, ein Graph"; die Historie wächst seit 12.09. täglich).
- **E-S2: 1&1 per Playwright** (Datenerhebung, nicht Darstellung).
- Katalog-Erweiterungen, neue Anbieter, Nachrichtenseite.

## Stand, an den angeknüpft wird (nichts davon neu messen)

- O1–O4 sind **live** (Push `bd3fbde`, deploy success, live byte-identisch
  gegengeprüft), Evaluatoren: O2 9/9, O3 9/9 (1× S2 behoben), O4 9/9 ohne
  S1/S2. Belege: `/tmp/optik-o1-o4/o2…o4/` (Bauberichte, Evaluator-Berichte,
  rot-vor-grün). Umsetzungsstand: `docs/STRATEGIE_GERAETE_OPTIK.md` §7.
- Suite auf main: **3054 passed / 3 failed / 14 skipped** — die 3 Roten sind
  vorbestehend (2× test_promo_seite ohne Pillow, 1× test_geraete_lifecycle)
  und werden NICHT angefasst; `pruefe_portal` 17/1 (nur 8b vorbestehend).
- Die nächtliche Datensammlung (`geraete.yml`, täglich 03:10 UTC) läuft
  **komplett ohne KI** (Adapter-Extraktion; der Job hat keinen KI-Schlüssel)
  und rendert + deployt die Seite automatisch — ein Merge auf main ist am
  nächsten Morgen live.

## Prozess (bewährt aus O1–O4, einhalten)

1. Eigenen Worktree + Branch (`claude/…`), rot-vor-grün zuerst, kleine
   thematische Commits, sobald grün committen (zwei Agenten sind an API-
   Limits gestorben — uncommittet ist verloren).
2. Abnahme durch die leitende Instanz: Screenshots SELBST ansehen (1440+390),
   Zahl-Aussagen als DOM-Stichprobe nachmessen, kompletter pytest +
   `pruefe_portal` (11/11b/11c-Regeln mitziehen), Commit-Hygiene
   (kein `data/`, `site/` nur als eigener „Seite neu gebaut"-Kommitt nach
   Abschluss, Muster `bd3fbde`).
3. Adversarieller Evaluator mit frischem Kontext (bekommt die Begründung des
   Bauers nicht), Bericht nach `/tmp/`.
4. **Vor dem Bau ein ENTWURF, den Antonio freigibt** — die O-Phasen sind an
   einem statischen Entwurf mit echten Zahlen ausgerichtet worden
   (`docs/entwuerfe/geraete-optik-2026-09-11/entwurf.html`), und genau das
   hat funktioniert. Für B1 (eine Seite) gilt das erst recht: erst Entwurf +
   Einkäufer-Sichttest („Pixel 11 Pro bei Telekom, mittlerer Tarif — was
   zahlt der Kunde?" in ~12 s ohne Erklärung), dann Bau.
5. Push-Freigabe ist erteilt (Antonio, 15.09.); nach JEDEM Push
   `deploy.yml`-Ausgang prüfen (ein Push allein ist kein Deploy) und live
   per md5 gegencommitten — die erste Messung direkt nach dem Deploy läuft
   gern durch CDN-Propagation, dann Inhalts-Marker vergleichen.

## Betriebs-Fallstricke (aus dieser Session, alle echt passiert)

- **Fremde http.server laufen auf dem Rechner.** Eigener Messserver: unüblicher
  Port, VOR der Messung `curl -s URL | grep -c <marker>` gegen den EIGENEN
  Render, am Ende nur die eigene PID killen. Ein Chromium-Test lief mal
  unbemerkt gegen den Haupt-Checkout statt gegen den frischen Render.
- **Bildanzeige fällt gelegentlich aus** (CDN): DOM-Messungen als Primärbeleg,
  Screenshot-Dateien trotzdem eindeutig markieren (`--marke <phase-datum>`).
- **Zwei Stände in einem Screenshot-Durchlauf:** jeden Stand als eigener
  subprocess mit SEINEM `PYTHONPATH` rendern — sonst entstehen byte-identische
  „Vorher/Nachher"-Bilder (passiert, erkannt, verworfen).
- Radertest-Zeilen-Klasse `.gr-a-zeile` ist MEHRDEUTIG belegt (Katalog- UND
  Alarm-Zeilen) — Selektor nie allein auf die Klasse stützen.
