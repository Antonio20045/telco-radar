# E4 — PM-6 vorbereitet: Fragmentwachstum messbar (18.09.2026)

Auftrag: Fragmentwachstum messbar machen, BEVOR es umkippt. Deckel NICHT
gebaut (Entscheidung 01.10., P5-Auftrag 4 / Premortem FM 3).

## Die Kernzahl, die keiner auf dem Schirm hatte

**Die 5-MB-Grenze des Zeitreihen-Fragments faellt laut Prognose am
2026-09-20 — also VOR dem 01.10.** Lineare Rechnung aus echten Messungen:
1.391 B/Messpaar x 427 Paare/Messtag = **580 KB/Messtag** Wachstum;
3.563.920 B heute → (5.000.000 − 3.563.920) / 580 KB ≈ 2,4 → 3 Messtage.
Wer den Deckel auf den 01.10. legt, entscheidet nach dem Umkippen.

Messzahlen am echten Bestand (6 Messtage, Stand 18.09.2026):

| Groesse | Wert |
|---|---|
| Messtage / Messpaare (Historie) | 6 / 2562 (435+403+403+435+394+492) |
| Rate | 427 Paare/Messtag (bestaetigt den Premortem-Wert) |
| geraete-zeitreihe.html | 3.563.920 B roh / 159.174 B gzip (4,5 %) |
| geraete-buendel.html | 1.541.789 B roh / 61.680 B gzip (4,0 %) |
| Bytes je Messpaar | 1.391 B — die Premortem-Schaetzung „~7 KB/Paar" war 5x zu hoch |
| Summe beider | 5.105.709 B — bereits ueber 5 MB; Grenze gilt deshalb JE Fragment |

Vorlage-Spruenge bleiben draussen (P1: +2,4 MB ueber Nacht ohne neuen
Messtag — Git-Historie 146f4b4→63e693c); die Prognose rechnet ab dem
letzten MESSTAG (nicht heute — Hausregel) und kalibriert bei jedem Aufruf
neu. Das Buendel-Fragment waechst mit MODELLTIEFEN, nicht mit Messtagen;
die Paar-Prognose trifft es nicht (steht so im Bericht).

## Gebaut

1. **`scripts/geraete_fragment_wachstum.py`** — Tabelle Messtag/Paare neu
   + kumulativ, Fragmentgroessen (B, gzip, B/Paar), Prognosetabelle
   (+1/+2/+3/+7/+14/+30/+60 Tage, Zeile `<-- GRENZE`), Grenz-Datum,
   Empfehlungsblock (Optionen A/N-Messtage-Deckel, B/Aufteilen je ModellxBand)
   als TEXT, kein Schalter. `--root/--heute/--grenze-mb`.
2. **`src/telco_radar/geraete_fragment.py`** — die EINE Quelle der drei
   Zahlen (Skript UND Pipeline lesen dieselben Funktionen; keine zweite
   Rechnung fuer dieselbe Zahl). `protokoll_zeile()` liefert die
   Laufzeile.
3. **Protokollzeile im Geraete-Lauf** (`geraete_pipeline.py`, Ende von
   `run_geraete_stage`, vor `return bilanz`): `Fragmentgroesse: 6 Messtage,
   2562 Messpaare, 4985 KB Fragmente` — einzeilig, independant von E2
   (dessen Ausfall-/Probe-Zeilen sitzen an anderer Stelle). Fehlt die
   Historie, bleibt die Zeile weg (kein Messpunkt 0/0/0); fehlen die
   Fragmente (Render laeuft ja erst NACH dem Pipeline-Schritt), stehen
   die Messzahlen ohne Fragment-KB — die Reihe reisst nicht.
4. **`tests/test_geraete_fragment_wachstum.py`** (7 Tests, gruen):
   Fixture tmp/ (3 Messtage x 10 Paare + Dublette, 30.000/500.000 B),
   Projektionsformel exakt (ceil: 427→497 Tage Fall, „genau auf der
   Grenze = gehalten", bereits-ueberschritten-Fall), CLI-Weg via
   Modulladung des Skripts, Determinismus (zwei Aufrufe byte-identisch,
   gzip mtime=0, heute=Parameter). KEIN Test gegen die echte site/ —
   er wuerde am 20.09. rot werden und die 01.10.-Entscheidung
   vorwegnehmen (Unterschied messen/kippen).

## Messungen / Nachtlauf

- `python3 scripts/geraete_fragment_wachstum.py` am echten Bestand: s.o.
- Tests: `7 passed`; together mit test_geraete_pipeline + Zeitreihe +
  seiten_zahlen: **271 passed**. Die roten in
  `tests/test_geraete_ausfall_alarm.py` sind E2s laufender Bau (zwei
  verschiedene Failures in zwei Laeufen, kein Bezug zu meinen Dateien).

## Offene Sorgen

- **20.09.:** Prognosetag. Der Lead sollte die Deckel-Entscheidung
  vorziehen oder bewusst ins Risiko nehmen — ab 21.09. liegt das
  Fragment ueber der Grenze (~580 KB/Tag weiter, 01.10. ≈ 11,9 MB).
- gzip liegt bei 4–5 % (SVG ist hochrepetitiv): die Grenze schuetzt
  Repo/Parsing, nicht die Leitung — im Bericht ausgewiesen, damit die
  Entscheidung weiss, was sie begrenzt.
- Die Rate beruht auf 6 Messtagen; Premortem wollte 14. Ab 01.10. steht
  die taegliche Protokollzeile dafuer bereit.
