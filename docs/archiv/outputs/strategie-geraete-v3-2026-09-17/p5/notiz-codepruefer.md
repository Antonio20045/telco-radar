# Notiz Code-Pruefer (P5) — adversariale Diff-Pruefung gegen HEAD f006660

Alle Zahlen selbst gemessen; nichts committet, nichts unter data/state
geschrieben (`git status --porcelain -- data/state data/reports` leer).

## Ergebnis in Zahlen

| Messung | Ergebnis |
|---|---|
| Suite `-k geraete` | **1505 passed / 0 failed / 6 skipped** (206 s) |
| Volle Suite `pytest -q` | **3303 passed / 0 failed / 12 skipped** (446,9 s) |
| 2 vorbestehende Rote am SAUBEREN HEAD f006660 (Worktree /tmp) | beide nachweislich rot: Lifecycle `assert 52 >= 80`; Tablets `Samsung Galaxy Tab S11 Ultra` (Auto-Eintrag 17.09.) — Konvertierungen gerechtfertigt, nicht still gestrichen |
| E2-Schwelle | `AUSFALL_TAGE = 7` (geraete_store.py:57), Test an GENAU 7 und an 6 Tagen |
| E3-Fixture | 145 Zeilen, sha256 `3a66c789…` stimmt mit `_herkunft.json` ueberein (Kopie der echten State-Datei) |
| E4 | `GRENZE_BYTES = 5_000_000` je Fragment, `heute=`-Parameter, byte-identische Wiederholung, EINE Protokollzeile |

## Befundlage

- **1x S2** (einzeln in pruefung-code.md): Provider-Probe blind fuer den
  Totaltod des o2-Buendel-Preisblocks — `o2.py:341` zaehlt nur Kandidaten
  MIT `monthlyPrice`; faellt das Feld ganz weg, bleibt `kandidaten == 0`
  → keine Zeile. Gleichzeitig zaehlt `geraete_pipeline.py:242` Bündel
  nie als Funde (`funde=len(bilanz.listungen)`), der 7-Tage-Ausfallalarm
  bleibt stumm, solange der hwOnly-Pfad Listungen liefert — und die
  Buendelzeile (:462) ist INFO „0 von 0". Die Docstring-Zusicherung
  :135-137 („dafuer sind die Buendel- und Ausfallzeile da") haelt der
  Code fuer genau dieses Szenario nicht. Praemortem FM-2-Wortlaut.
- S3/S4 gebuendelt (Prozent-Rundung 199/200 → „100 %", Testhelper-Flag
  `mit_listung`, 5 Parameter an `katalog_modellzeilen`, Zeiger
  „E5-Schlussliste" ohne Zieldatei).
- E1-E5 im Einzelnen PASS (Sprungziele, Schwelle, Filter gegen echte
  Titel, Determinismus, CLAUDE.md §6 unberuehrt + 4 neue Fallstricke).
