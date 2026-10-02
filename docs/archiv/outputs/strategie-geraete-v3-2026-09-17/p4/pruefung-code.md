# P4 — CODE-Prüfung (adversarial)

Basis: `git diff 6a37ceb` (Stand nach P3), Notizen `p4/notiz-*.md`,
STRATEGIE_GERAETE_V3 P4, befunde/design.md, docs/clean-code-referenz.md.
Nichts committet, nichts unter data/state geschrieben. Suite und Portal
wurden am stehenden Baum gemessen; Browser-Beweise über lokalen HTTP-Server
(`p4/pruef_mess_browser.py`, SVG-Stichprobe `p4/pruef_mess_svg.py`).

## Ergebnis

**S1: 0. S2: 1. S3/S4: gebündelt unten.**
Suite `-k geraete`: **1456 passed / 3 failed / 6 skipped** — die 3 sind exakt
die benannten Vorbestehenden (verifiziert am Fehlergrund: Galaxy Tab S11
Ultra `auto='2026-09-17'`-Erkennung, Nachtlauf-Nullzeilen, iPhone-18-
Querlinks). `pruefe_portal.py`: **20 bestanden / 1 durchgefallen** — Kriterium
13 „Vergleich 18 048 Z > 6000" ist der von D3 dokumentierte vorbestehende
Hebel (20 Tarif-Rechenweg-Aufklapper, Lead/P5), Radar 2743 Z und Katalog
230 Z grün; 11b Reiterhöhen 2845/2400/1943/1871 alle < 3000.

## S2 — Stale-Leitzahl im Verlaufs-Reiter (Browser bewiesen)

`src/telco_radar/report/templates/app.js` Z. 2624–2633 (Früh-Rückweg in
`zeichne()` bei leerem Zeitfenster) und Z. 3111–3129 (Suchfeld-Rückbau):
beide Pfade verstecken leer/bild/legende/tabelle/kacheln und rufen
`satzFuer(null, …)` — aber `#gr-vleit` (die Leitzahl, P4-Regel „die Antwort
ist die größte Zahl") wird nicht versteckt. Der `leit.hidden = true`-Zweig
(Z. 2690–2692) liegt NACH dem Früh-Rückweg und ist dort unerreichbar.

Gemessen am gerenderten site/ (Chromium, Initialzustand Leitzahl
„919,00 € / aktuell · congstar · 17.9."):

1. `#gr-vvon` auf 2027-01-01 → Leermeldung „Für diesen Zeitraum liegen keine
   Messpunkte vor." — **`#gr-vleit` bleibt sichtbar mit „919,00 €"**.
2. `#gr-vsuche` „zzzz" → „Kein Gerät gefunden." — **`#gr-vleit` bleibt
   sichtbar mit „919,00 €"**.

Fehlerszenario: Die größte Zahl der Tafel behauptet einen aktuellen Preis,
während die Tafel daneben sagt, dass es nichts gibt — genau der Widerspruch,
gegen den der Satz-Rückbau (`satzFuer(null, null, 0)`, zwei Zeilen tiefer,
derselbe Grund) gebaut wurde. Fix wäre eine Zeile je Pfad (`leit.hidden =
true`) oder das Verstecken im gemeinsamen `satzFuer`-Gegenzug. Kein Test
deckt den Leerzustand der Leitzahl (die D4-Tests messen den Normalfall).

## Prüfaufträge des Leads — einzeln beantwortet

**Vier dokumentierte Test-Kippungen:** alle vier real umgestellt, jede
kommentiert mit Vorher-rot; überwiegend STÄRKEND. (2a) `wr-bewegungen` →
`tafel-verlauf` in der ALT-Hash-Map (app.js Z. 875–879), verifiziert.
(2b) `#gr-sortiment`-Assert von `#tafel-katalog` auf `#tafel-radar`
gekippt UND der umgekehrte Dopplungsschutz (`…steht_nicht_zweite_mal…`)
verbietet jetzt den Katalog-Ort zusätzlich — Verschärfung, kein Verlust.
(D4 Export ×2) beide Tests fordern jetzt die FUSSZEILE statt des Kopfs und
verbieten die Hero-Platzierung; die Leersicherung
`test_export_ohne_zeilen_nennt_die_null` wurde im Bau rot und am Gatter
gefixt (Fußzeile steht außerhalb `hat_daten`). Einzige Wortlaut-Abschwächung
der Phase: „Betrag ohne Vorzeichen" → „als Betrag" in
`test_der_tafelkopf_polt_nur_die_sektionen_mit_vorzeichen` — in notiz-d4
offen dokumentiert, die Gegenprobe („alle Alarm-Prozente positiv") bleibt.
Kein weiterer still entschärfter Test gefunden (Volllektüre der geänderten
Testdateien; neue `tests/test_geraete_faden_schluessel.py` tragen allesamt
Vollständigkeits-Gegenproben nach CLAUDE.md-Regel — stark).

**Radar-SVG nur Server-Daten:** PASS. `grep wr-gr site/app.js` = 0 Treffer —
kein JS rechnet, afft oder verschiebt die Grafik an. Die beiden SVG-Varianten
stehen fertig im Markup (`svg.wr-gr--breit/--schmal`, Mediaquery).

**Balkenlängen-Stichprobe (3+ Modelle):** PASS, nach Korrektur eines eigenen
Parser-Bugs (erste Fassung paarte die falschen zwei €-Zahlen des `<title>`;
Titelformat ist `Modell: +Δ € (±p %) gegenüber Laden – VF a €, Laden b €`).
Nachgerechnet über alle 12 Pfade beider Varianten: Skala konstant
(breit 3,2356–3,2362 px/€, schmal 1,0537–1,0542 — Streuung 0,02 %,
Koordinatenrundung), `Länge/Skala` == Titel-Delta innerhalb ±0,02 €
(Spitze iPhone 16 +242,90 €: 786,0 px / 3,2359 = 242,90 €), Balkenbasis
exakt auf der Nulllinie (Abweichung 0,00 px), Spitzen-Balken konsistent mit
aria-label („groeßter Abstand +242,90 Euro bei iPhone 16").

**Rot-Deckel ≤ 10 je Tafel:** PASS. DOM-Proxy-Zählung
(`[class*='--spitze'], .gr-eigen`) je Tafel: tco 0 / radar 5 / verlauf 0 /
katalog 0 — alle ≤ 10; sichtbar nach Reiter-Aktivierung laut D1-Messung
genau 1 (der Spitzen-Balken). In `pruefe_portal.py` NICHT als eigenes
Kriterium messbar — gedeckt über `test_rot_ist_akzent_nicht_teppich`
(DOM-Proxy ≤ 10, existiert, grün). Deckel als Regel im Test, nicht im
Skript: akzeptabel, Skript-Messung wäre die härtere Nägelung.

**Leitzahl-Vergrößerung:** PASS mit Randnotiz. Keine neue Schrift
(`.gr-leit-zahl{font-family:var(--serif);font-weight:700}`, style.css
Z. ~3606–3624), clamp 30–60 px. 390: 30 px, längster Text „1.499,00 €"
131 px von 306 px Zeilenbreite — kein Überlauf, kein min-content-Problem
(D4-Messung); ab 35 px bräche Kriterium 11c — 30 px hat 4 px Luft.
Randnotiz (S3): der Begriff „aktuell" ist fensterrelativ — die Leitzahl
rechnet aus den gefilterten Rohpunkten, nach Verengung des Von/Bis-Fensters
nennt „aktuell" den letzten Messpunkt IM FENSTER (Label nennt immerhin
Anbieter und Datum dazu).

**Suite:** 1456/3/6 (s. o.). **pruefe_portal:** 20/1 (s. o.), 0 nicht
prüfbar.

## Prüfkatalog (docs/clean-code-referenz.md), Kategorie für Kategorie

- **P** (Produktionscode): PASS — kein toter Code im Diff (der P2-Ternär mit
  identischen Zweigen ist beseitigt), Leerzustände benannt (Ausnahme: der
  S2 oben). S4: `grafik(…, n=0)` → `gewaehlt[-1]` IndexError (latent;
  `radar()` ruft ohne `n`, Bestand hat ≥ 1 Zeile).
- **C** (Kommentare): PASS — Warum-Kommentare an allen heiklen Stellen
  (Früh-Rückweg, parameterweises replaceState, Deep-Link-Fixierung).
  S4: „groeßter" (ASCII-oe) im aria-label, geraete_radar.py:631 — das Portal
  schreibt sonst Umlaute; Screenreader lesen „groeßter" buchstabiert.
- **E** (Namen): PASS — `gr-ksprung` vs `gr-sprung` bewusst getrennt und
  kommentiert (ZR-Delegat würde sonst fremde Klicks fangen).
- **F/G** (Funktionen/Grenzen): PASS — `GRAFIK_MAX = 12` messbar begründet
  (402 px viewBox über der Falze); Deckel folgt dem Filter.
- **J** (Tests): PASS bis auf den S2 — kein Test gelöscht; Umstellungen
  begründet und stärkend (s. o.); neue Tests mit Gegenproben.
- **N** (Nutzwert): S2 ist der Nutzwerts-Verstoß der Phase (größte Zahl
  lügt im Leerfall).
- **T** (Konstanten einmalig): PASS — `AB_TERMINEN`/`ABSTAND` aus
  data-Attributen statt zweiter Kopie in JS.

## CLAUDE.md-Hartregeln

PASS, alle. `site/` wurde ausschließlich über `render_site(…, cfg)`
erzeugt (vier geänderte site/-Dateien reproduzierbar; kein Handgriff).
Kein `data/state/`, kein `data/reports/` im Diff. Modell-Schlüssel aus
Katalog-IDs, nie Titeltext (`test_…_modell_schluessel` mit Gegenprobe).
Keine Secrets, keine Lauf-Artefakte im Commit-Pfad (Prüfskripte liegen
untracked unter `outputs/…/p4/`).

## Randfälle / stille Verhaltensänderungen

- Leere Eingabe: Suchfeld < 2 Zeichen blendet Treffer aus (unchanged);
  Leerzustände der Tafeln benannt — außer dem S2 (Verlauf-Leitzahl).
- Netzwerkfehler: Fragment-Fetch (`geraete-zeitreihe.html`) fail-closed —
  alter Block bleibt stehen, offener Panel-Wunsch wird verworfen (PASS).
- Fremdformat: `JSON.parse` der Datenknoten in try/catch mit stiller
  Grundausstattung — Seite bleibt lesbar, Tafeln zeigen Server-HTML (PASS).
- Stille Änderung bestehender Funktionen: `waehle()`/Start schreiben die URL
  parameterweise statt neu aufzubauen — dokumentiert und der Grund des
  `?ansicht=`-Deep-Links (kein Verlust; bis P4 löschte der Neuaufbau
  Nachbar-Parameter — das war der Bug).
- `zr`-Feld fail-closed (None/leer ⇒ False, Unit-Test) — kein blinder Link.

## S3/S4 gebündelt

1. **S3** „aktuell"-Leitzahl fensterrelativ (app.js Z. 2661–2693) — s. o.;
   abgeschwächt durch Datum im Label.
2. **S4** ASCII „groeßter" im aria-label (geraete_radar.py:631).
3. **S4** `gewaehlt[-1]` latent IndexError bei `grafik(n=0)`
   (geraete_radar.py) — Produktion unerreichbar, künftiger Aufrufer crasht
   statt Leerzustand.
4. Rot-Deckel nur testgedeckt, nicht in `pruefe_portal.py` messbar
   (härtere Nägelung wäre ein Kriterium; jetziger Zustand akzeptabel).
