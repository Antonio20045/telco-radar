# P5-Fix — S2-1 (Totaltod der o2-Preisfelder), S3-1 (Rundung), S4-5 (Zeiger)

Auftrag: S2-1 aus `pruefung-code.md` beheben, dazu S3-1 und S4-5.
Nichts committet, nichts unter `data/state` geschrieben, `site/` nicht
neu gerendert (reine Protokoll-/Collector-Logik).

## S2-1 — Provider-Probe sieht den Totaltod des Preisblocks

**Vorgefundener Zustand:** Der Fix war im Arbeitsbaum bereits angelegt
(`o2.py` zählt Kandidaten ohne die `monatlich`-Bedingung; fehlendes
`monthlyPrice` → gescheiterte Probe der Ebene „monthlyPrice";
`melde_proben` druckt WARNING) — offen waren der Beweis an der ECHTEN
Antwort und die Dokumentation der Alarm-Arbeitsteilung. Das habe ich
ergänzt:

1. **Totaltod-Test auf der gespeicherten echten o2-Antwort**
   (`tests/test_geraete_provider_probe.py`): `o2_katalog_buendel.json.gz`
   (88 Einträge, 66 Bündel), in JEDEM Eintrag `price.monthlyPrice`
   entfernt → `proben == {"kandidaten": 66, "monthlyPrice": 66}`,
   `saetze == []`, WARNING „0 von 66 … (0 %) - gescheitert an: 66x
   monthlyPrice". Der bisherige Test nutzte konstruierte `_eintrag()`-
   Sätze — laut Auftrag „nie erfinden"; 1:1-Ersatz, Testzahl bleibt 9.
2. **„o2 liefert GAR keine Antwort"** (im Auftrag gefordert als
   Prüfung/Doku): Dieser Weg läuft über den 7-Tage-Ausfallalarm — auch
   die Listungen bleiben aus → `funde == 0` → Alarm. Gedeckt durch
   `test_geraete_ausfall_alarm.py::test_sieben_tage_null_funde_loesen_
   den_alarm_aus` (Funde 0 an 7 beobachteten Tagen → Alarmzeile). Die
   Arbeitsteilung steht jetzt als Abschnitt „ZWEI ALARME, ZWEI FÄLLE"
   im Modulkopf der Probendatei: Preisblock tot bei weiterlaufenden
   Listungen → NUR die Probe meldet (Funde > 0 hält den Ausfallalarm
   stumm); gar keine Antwort → Funde 0 → Ausfallalarm ab Tag 7.
   Der `melde_proben`-Docstring dokumentiert denselben Split.
3. **Buendelzeile** bleibt INFO „0 von 0" im Totaltod — bewusst nicht
   angehoben: mit der WARNING-Zeile der Probe („66x monthlyPrice") gibt
   es jetzt EINE eindeutige Meldung für den Fall; die Buendelzeile sagt
   weiterhin wahrheitsgemäß, dass kein Satz übernommen wurde.

## S3-1 — 199/200 ist keine Perfektion

`melde_proben` rundet ab (`int(100.0 * bestanden / erwartete)` statt
`round`): nur `bestanden == erwartete` heißt „100 %". Test
`test_ein_einzelfehler_ist_keine_perfektion`: 199/200 → „(99 %)" als
WARNING, „100 %" kommt nicht vor.

## S4-5 — Zeiger „E5-Schlussliste"

`grep -n "E5-Schlussliste" CLAUDE.md` → **0 Treffer** im heutigen Baum;
der Klammer-Text (CLAUDE.md:1845-1848) zeigt intern auf „OFFEN-Punkt 8
dort", und der P5-OFFEN-Punkt 8 existiert und trägt den Kosmetik-Punkt.
Der Zeiger war also bereits umgebogen; was fehlte, war der Punkt in der
E5-Notiz (dort stand die Liste mit 7 Punkten): ergänzt als Punkt 8 in
`notiz-e5-claude-md.md` (die kürzere der beiden Auftrags-Optionen).

## Messungen

- **Vorher-rot bewiesen** an einer tmp-Kopie des Baums (`/tmp/p5-vorher-1`,
  nie im Repo), in der die zwei Fix-Stellen auf den von der Prüfung
  zitierten Altzustand zurückgedreht wurden
  (`o2.py`: `if proben is not None and monatlich is not None:` ·
  `melde_proben`: `round`):
  `2 failed, 7 passed` — rot: `test_totaltod_des_referenzfeldes_…`
  (S2-1) und `test_ein_einzelfehler_ist_keine_perfektion` (S3-1);
  die übrigen 7 bleiben grün, die Tests messen also genau den Fix.
- **Nachher:** `tests/test_geraete_provider_probe.py` +
  `test_geraete_ausfall_alarm.py` → **23 passed**.
- **Suite:** `PYTHONPATH=src python3 -m pytest tests/ -q -k geraete` →
  **1516 passed, 6 skipped, 0 failed** (226,9 s) — keine neuen Roten.
  Die Differenz zur Prüfermessung (1505/6/0) stammt aus dem vorgefundenen
  Arbeitsbaum; meine Änderungen verschieben die Testzahl nicht (1:1-Ersatz
  einer Testfunktion, 9 collected vorher wie nachher).
- `git status --porcelain -- data/state data/reports` → leer.
