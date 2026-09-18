# P5 / E2: FM-2-Alarm — Quellentod darf nicht still bleiben

Auftrag 2 aus P5 (Strategie v3). Beide Meldungen sind reine Protokollzeilen:
kein Altern, kein Loesen, kein Mail/Teams (bewusst nicht gebaut), keine
Statistik-Seite.

## Wortlaut der neuen Protokollzeilen (gemessen, nicht geraten)

```
WARNING Geraeteradar-Ausfall: o2 liefert 7 Tage 0 Saetze (Quelle pruefen: geraete-quellen.html)
INFO    Geraeteradar-Probe: o2 liefert 66 von 66 erwarteten Saetzen noch ihre Felder (100 %)
WARNING Geraeteradar-Probe: o2 liefert 0 von 66 erwarteten Saetzen noch ihre Felder (0 %) - gescheitert an: 66x metric3+metric2
```

## Was gebaut wurde

| Baustein | Wo | Die eine Regel |
|---|---|---|
| Fund-Historie je Tag | `geraete_store.protokolliere_lauf` → `funde_nach_tag` | Gleicher Tag ersetzt seinen Eintrag (idempotent, TCO-Historie-Regel), Deckel 30 Tage (gemessen: 986 Byte je Anbieter im State-JSON, alle 10 Anbieter < 10 KB) |
| `stille_tage()` / `ausfall_alarme()` | `geraete_store.py`, `AUSFALL_TAGE = 7` | Gezaehlt werden BEOBACHTETE Tage (vollstaendiger Lauf ODER Funde), nie Kalendertage — ein uebersprungener Anbieter ist keine Aussage. Altbestand ohne `funde_nach_tag` wird aus `termine` nach `letzter_fund` ABGELEITET (per Definition Null-Tage), nicht geraten; ohne `letzter_fund` wird nichts abgeleitet |
| `melde_ausfall()` | `geraete_pipeline.py`, nach der Laufzusammenfassung | `nur=` begrenzt auf die Anbieter DIESES Laufs — ein dekonfigurierter Anbieter gibt keine Ewigkeitsmeldung. Gate: `funde_gesamt > 0` (nie geliefert = SIM-only-Fall, kein Quellentod) |
| Provider-Probe | `o2._buendelsatz(..., proben=)`, `Anbieterbilanz.proben`, Collector reicht durch | Die drei Phase-S-Proben zaehlen je Kandidat VOR jedem Verwurf (Zubehoer/tariflos zaehlen nicht). Ein wegfallender TYPISIERTER Betrag (activationFee, oneTimePrice) ist eine GESCHEITERTE Probe, kein ungeeigneter Kandidat — genau das Verschwinden soll gemeldet werden. 100 % = Info, darunter = Warning mit Feldebene und Zahl; ohne Kandidaten keine Zeile |
| `melde_proben()` | `geraete_pipeline.py` | fester Wortlaut, sonst nicht grepbar im Actions-Log |

Schnittstelle: alle fuenf `lies_buendel(text, url="", proben=None)` — nur o2
fuellt, die vier anderen ignorieren (dokumentiert im Adapter-Docstring).

## Messungen

- **Probe an der ECHTEN gespeicherten Antwort** (`tests/fixtures/geraete/o2_katalog_buendel.json.gz`, 88 Eintraege): `{"kandidaten": 66, "bestanden": 66}` — das 66/66 der Phase S reproduziert sich.
- **Realer Bestand (17.09., read-only)**: 0 Alarme heute; maximal 1 stiller Tag (Medimax, ElectronicPartner — letzter Fund 06.09., ein beobachteter Termin 12.09. danach). Korrekter Start: der Alarm misst, er spamt nicht.
- **Tests**: 21 neu (11 in `tests/test_geraete_ausfall_alarm.py`, 10 in `tests/test_geraete_provider_probe.py`), darunter Ende-zu-Ende mit `run_geraete_stage`: Alarm-Zeile im Protokoll nach 1 Fund-Tag + 7 Null-Tagen, `gealtert == 0` und beide Listungen noch im Store (Beweis: der Alarm loest nichts).
- **Suite `-k geraete`**: 1499 passed / 6 skipped / **2 failed — beide an sauberem HEAD (f006660) in einem separaten Worktree nachgewiesen, 0 neue**: `test_geraete_lifecycle::test_ein_simulierter_nachtlauf...` (bekannt, Nachtlauf-Test) und `test_geraete_adapter_netzbetreiber::test_tablets_und_router_bleiben_draussen` (rot seit der ersten Auto-Erkennung des echten Laufs vom 17.09. — "Galaxy Tab S11 Ultra" steht als auto-Eintrag im committeten State; Arbeitsliste des E-3-/E-4-Komplexes, nicht meine).

## Fuer den Lead

- `geraete_pipeline.py` wurde parallel von mir und dem PM-6-Agenten editiert (dessen `geraete_fragment`-Import + Fragmentgroessen-Zeile steht ueber meinen Helpern); beide Aenderungen stehen Seite an Seite, Suite gruen — beim Merge nichts davon zurueckdrehen.
- Erwartung ab Einsatz: die erste `funde_nach_tag`-Zeile schreibt der naechste Nachtlauf; bis dahin zaehlt die Altbestands-Ableitung (Termine nach letzter_fund) — an ihr gemessen: 0 Alarme.
- Bewusst offen: Proben gibt es heute nur fuer o2 (Phase-S-Praezedenz). Vodafone/Telekom/congstar/1&1 koennen dieselbe Schnittstelle nutzen, haben aber keine benannten Feld-Proben — nicht gebaut, weil nicht gemessen.
