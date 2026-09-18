# P4/2a — Wochenkarte „Was diese Woche auffällt" in den Reiter Preisverlauf

Auftrag (Strategie P4 Bau-Auftrag 2a): die Wochenkarte der Preisbewegungen
(letzte 14 Tage) aus der RADAR-Tafel in den REITER PREISVERLAUF verschieben —
nur Verschieben, nichts streichen, kein Umstylen. Begründung design.md §3b:
„Radars ‚Was diese Woche auffällt' ist ein Preisverlauf-Thema und gehört in
den Verlauf."

## Was geändert wurde

| Datei | Änderung |
|---|---|
| `src/telco_radar/report/templates/_geraete_radar.html.j2` | Sektion 4 (Wochenkarte) aus dem Makro `radar_tafel` herausgelöst und als eigenes Makro `wochenkarte(port)` definiert — Markup, Klassen, ID `#wr-bewegungen`, Gatter (`port.auffaellig.hat_daten`) unverändert. Kopfkommentar angepasst. |
| `src/telco_radar/report/templates/geraete.html.j2` | Import von `wochenkarte` dazu; Aufruf im Reiter Preisverlauf nach der Verlaufs-Tabelle / dem Datenlage-Aufklapper, am Reiterende. Bewusst AUSSERHALB des `hat_daten`-Gatters des Verlaufs (die Karte hing im Radar an keinem Verlaufs-Gatter und soll es auch hier nicht — im `else`-Zweig wüde sie im Verlaufs-Leerzustand still verschwinden). |
| `src/telco_radar/report/templates/app.js` | ALT-Hash-Map: `'wr-bewegungen': 'tafel-radar'` → `'tafel-verlauf'` (sonst schaltete ein `#wr-bewegungen`-Deep-Link den falschen Reiter auf). |
| `tests/test_geraete_seite.py` | Neuer Helper `_verlauf()` (Verlaufs-Tafel als eigene Suppe, dieselbe Bauform/Begründung wie `_radar`). 8 Tests auf ihn umgestellt (s. u.). |
| `tests/test_geraete_o3_rollen.py` | 2 Festnagelungen bewusst gedreht (s. u.). |

Kein Python-Datencode geändert — die Karte entsteht unverändert in
`geraete_view.py` (`_auffaellig`, `FENSTER_TAGE`), der Reiter liert
`radar.portfolio` (dieselbe EINE Berechnung wie die Radar-Tafel).

## Messungen

- **Karte vorher:** 1× in `#tafel-radar` (am gerenderten `site/geraete.html`
  gemessen). **Nachher:** 1× in `#tafel-verlauf`, **0 Dubletten**,
  Radar-Tafel trägt sie nicht mehr. Inhalt identisch: Summary
  „Was diese Woche auffällt – letzte 14 Tage (12 Bewegungen)", 7 Sätze,
  12 Bewegungszeilen, erster Satz wortgleich.
- **Lifecycle bleibt im Radar:** Beim ersten Edit fiel `#lifecycle` STILL
  aus dem Radar (`{% set port = wr.portfolio %}` stand im entfernten
  Sektions-4-Block; Sektion 5 las es mit) — am HEAD-Render gegen geprüft
  (lifecycle: True) und gefixt: das `set` steht jetzt an der Lifecycle-
  Sektion selbst, mit Warnkommentar. Nachher: Lifecycle True im Radar.
- **Reiterhöhen (Chromium 1440, `gr-tafel--aus` je einzeln entfernt):**
  Radar 2265 → 2235 px (−30, die zugeklappte Summare), Verlauf
  1043 → 1069 px (+26). Nur Verschieben, kein Umstylen.
- **`pruefe_portal.py`: 18 bestanden / 0 durchgefallen** (11b Reiterhöhen:
  tco 2593, radar 2967, verlauf 1839, katalog 1924; 11c Graphfalz ok).
- **Screenshot** (Karte geöffnet im Verlaufs-Reiter, 1440):
  `outputs/strategie-geraete-v3-2026-09-17/p4/wochenkarte_im_verlauf_1440.png`
  — Karte offen (12 Bewegungen, 7 Sätze), Sätze + Tabelle vollständig,
  Zeitungslayout (Serife, Linien), kein Rendering-Defekt. Angesehen.

## Vorher-rot → umgestellt → grün (Protokoll)

**Der vom Lead benannte Test** (`test_geraete_seite.py`,
`test_alte_preisbewegung_steht_nicht_unter_diese_woche`):

```
E       assert []
E        +  where [] = select('.gr-saetze li')
E        +    where select = <div ... id="tafel-radar" ...>.select
E        +      where <...> = _radar(PosixPath('.../test_alte_preisbewegung_steht_0/site'))
tests/test_geraete_seite.py:1213: AssertionError
```

Auf `_verlauf()` umgestellt → **1 passed**.

**Zusätzlich rot geworden (dem Lead nicht bekannt, dieselbe Karte, derselbe
Zugriff `_radar`) — alle bewusst auf `_verlauf()` umgestellt, alle grün:**

- `test_kein_satz_der_karte_nennt_eine_ungedeckte_zahl`
- `test_ohne_vorlauf_sagt_die_wochenkarte_was_sie_zeigt`
- `test_jede_zahl_der_wochenkarte_steht_so_im_datensatz`
- `test_die_geraeteseite_entsteht_ohne_jeden_netz_oder_modellaufruf`
  (Kommentar „steht auf dem RADAR" mit gedreht)
- `test_unter_vier_wochen_vorlauf_zeigt_die_wochenkarte_keine_tabelle`
- `test_ueber_vier_wochen_vorlauf_kommt_die_tabelle_zurueck`
- `test_die_wochenkarte_schreibt_preise_mit_komma`

**Festnagelungen in `test_geraete_o3_rollen.py` (verbaten den neuen Ort,
bewusst gedreht wie bei 2b in der Strategie):**

- `test_tafel_portfolio_ist_weg`: Assert `#wr-bewegungen` ∈ `#tafel-radar`
  → erwartet jetzt `#tafel-verlauf` (`#lifecycle` bleibt Radar).
- `test_was_diese_woche_auffaellt_steht_auf_dem_radar` →
  `test_was_diese_woche_auffaellt_steht_im_preisverlauf` (prüft die Karte
  in `#tafel-verlauf`).

## Nicht angefasst (vorbestehende Rot, per Lead)

- `test_geraete_o3_rollen.py::test_je_radar_gruppe_ein_querlink_mit_deep_link`
  (iPhone-18-Querlinks) — **am HEAD per `git stash` gegenprobe rot**
  (1 failed / 14 passed am HEAD; meine Änderungen betreffen weder
  `#wr-abweichung`-Links noch den Zeitreihen-Knoten).
- `test_geraete_lifecycle.py::test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen`
  (Nachtlauf-Nullzeilen).
- `test_geraete_adapter_netzbetreiber.py::test_tablets_und_router_bleiben_draussen`
  (Galaxy-Tab-S11-Ultra-Auto).

## Suite

- `test_geraete_seite.py` + `test_geraete_o3_rollen.py`: 97 passed /
  1 failed (nur iPhone-18, vorbestehend) / 4 skipped.
- Radar-/Reiter-/Browser-/Zahlen-/Export-Welle (18 Dateien, inkl.
  `test_seiten_zahlen`, `test_geraete_reiter_browser`,
  `test_geraete_o3_rollen_browser`, `test_geraete_export_mobil_browser`):
  174 + 339 passed, einziges Rot das vorbestehende Nachtlauf-Nullzeilen.
- **Volle Suite (`tests/`): 3226 passed / 3 failed / 12 skipped** (508,8 s).
  Die drei Rot sind EXAKT die vorbestehenden (Galaxy-Tab-S11-Ultra-Auto
  `test_tablets_und_router_bleiben_draussen`, Nachtlauf-Nullzeilen
  `test_ein_simulierter_nachtlauf_erzeugt_keine_nullzeilen`, iPhone-18-
  Querlinks `test_je_radar_gruppe_ein_querlink_mit_deep_link`) — keine
  anderen Tests gekippt.
