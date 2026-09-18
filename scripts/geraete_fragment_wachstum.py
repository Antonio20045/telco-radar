#!/usr/bin/env python3
"""PM-6: Waechst das Geraete-Fragment gegen die 5-MB-Grenze - und wann?

Warum es dieses Skript gibt (STRATEGIE_GERAETE_V3.md P5 Auftrag 4,
Premortem FM 3): das Zeitreihen-Fragment `site/data/geraete-zeitreihe.html`
wächst mit jedem Messtag der Bündel-Historie, und der Premortem konnte am
17.09.2026 nur schätzen ("~7 KB je Paar", Wachstumsrate "n. z." - das
Fragment existierte einen Tag). Dieses Skript misst Bytes und gzip gegen
die Zahl der Messtage/Messpaare AUS DER HISTORIE und projiziert die
5-MB-Grenze. Es ist eine ENTSCHEIDUNGSGRUNDLAGE und setzt keinen Deckel -
die Deckel-Entscheidung ist dem 01.10.2026 vorbehalten (siehe die
Empfehlung am Ende des Outputs).

Was hier zusammenkommt (drei Quellen, ein Bericht):

  data/state/geraete_tco_historie.jsonl  Messtage + Messpaare je Tag
                                         (idempotent gelesen, wie die
                                         Datei geschrieben wird)
  site/data/geraete-zeitreihe.html       Bytes + gzip - waechst mit den
                                         MESSTAGEN (jeder (Anbieter x
                                         Messtag)-Punkt traegt Markup)
  site/data/geraete-buendel.html         Bytes + gzip - waechst mit den
                                         MODELLTIEFEN, nicht mit Messtagen;
                                         steht zur Summe dabei, hat aber
                                         eine andere Wachstumsachse

Die Prognose ist linear durch den Nullpunkt (bytes_je_paar x paare) mit
der gemessenen Paar-Rate je Messtag und der Annahme 1 Messtag/Tag. Sie
kennt Vorlage-Spruenge nicht (P1 legte ueber Nacht +2,4 MB zu, ohne dass
ein Messtag dazukam) - deshalb steht das Messdatum an jeder Zahl.

    python scripts/geraete_fragment_wachstum.py
    python scripts/geraete_fragment_wachstum.py --grenze-mb 8 \
        --heute 2026-10-01
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.geraete_fragment import (  # noqa: E402
    BUNDEL_NAME,
    GRENZE_BYTES,
    HORIZONT_TAGE,
    PROGNOSE_SCHRITTE,
    ZEITREIHE_NAME,
    fragment_groessen,
    lies_historie,
    prognose,
)

MB = 1024 * 1024

# ---------------------------------------------------------------------------
# Die Empfehlung ist TEXT, kein Schalter: die Deckel-Entscheidung traegt
# Antonio/der PM am 01.10. (14 Tage echte Messdaten). Sie steht hier im
# Quelltext, damit sie in jedem Output lesbar ist und nicht in einem
# Archiv-Dokument vergilbt. NICHTS davon ist gebaut.
# ---------------------------------------------------------------------------
EMPFEHLUNG = """\
Empfehlung (PM-6, Entscheidung 01.10.2026 - NICHT gebaut, dieses Skript setzt keinen Deckel):
  A) Zeitreihen-Fragment auf die letzten N Messtage begrenzen (z. B. N=30):
     aeltere Punkte bleiben in geraete_tco_historie.jsonl und im CSV-Export
     wahrheitsgemaess erhalten - der Deckel greift am LADEGUT, nicht an der
     Messung. N so waehlen, dass das Fragment unter der Grenze bleibt, und
     als Test verankern (ein Fragmentgroessen-Test existiert heute nicht,
     vergleich.md Befund 3).
  B) Alternativ: Fragment je (Modell x Band) aufteilen und erst beim
     Modellwechsel laden - dreht die Wachstumsachse vom Messtag auf die
     Zahl der Modelle, kostet aber einen zweiten Montagepunkt im Client.
  Erwartbar nach heutiger Messung: die Grenze faellt frueher als der 01.10. -
  bis dahin taeglich die Protokollzeile 'Fragmentgroesse:' lesen (drei
  Zahlen, seit P5 in jedem Geraete-Lauf); das Skript kalibriert die Rate
  bei jedem Aufruf neu."""


def _mb(b: float) -> str:
    return f"{b / MB:.2f} MB"


def _tag(tag: date) -> str:
    return tag.isoformat()


def bericht(root: Path, heute: date | None = None,
            grenze: int = GRENZE_BYTES) -> str:
    """Der ganze Bericht als Text - rein lesend, niemals schreibend.

    `heute` dient NUR der Stand-Zeile (Hausregel: date.today() nie
    ungeparametriert); die Prognose rechnet ab dem letzten MESSTAG, damit
    ein Feiertag ohne Lauf sie nicht altern laesst.
    """
    heute = heute or date.today()
    root = Path(root)
    bestand = lies_historie(root / "data" / "state" / "geraete_tco_historie.jsonl")
    fragmente = fragment_groessen(root / "site")
    zeilen: list[str] = []
    zeilen.append(
        f"PM-6 Fragmentwachstum Gerateseite - Stand {heute.isoformat()} "
        f"(Messgrundlage: geraete_tco_historie.jsonl, Fragmente vom letzten "
        f"Render)")
    zeilen.append("")

    # --- Messtage: die gemessene Reihe, aus der die Rate kommt.
    zeilen.append("Messtage (gemessen):")
    zeilen.append("  Datum        Paare neu   Paare kumulativ")
    kumulativ = 0
    for tag, neu in bestand.tage:
        kumulativ += neu
        zeilen.append(f"  {_tag(tag):<12}{neu:>10}{kumulativ:>16}")
    rate = bestand.rate_je_messtag()
    if rate is not None:
        zeilen.append(f"  Rate: {bestand.paare} Paare / {bestand.messtage} "
                      f"Messtage = {rate:.0f} Paare/Messtag "
                      f"(Annahme der Prognose: 1 Messtag/Tag)")
    else:
        zeilen.append("  Rate: unbestimmt - erst ab 2 Messtagen, die PM-6-"
                      "Regel will 14 Tage, bevor die Zahl entscheidet")
    zeilen.append("")

    # --- Fragmente: Bytes, gzip, Bytes je Messpaar.
    zeilen.append(f"Fragmente (gemessen):")
    by_name = {f.name: f for f in fragmente}
    zeitreihe = by_name.get(ZEITREIHE_NAME)
    for f in fragmente:
        je_paar = (f"  {f.bytes / bestand.paare:,.0f} B/Paar"
                   if bestand.paare and f.name == ZEITREIHE_NAME else "")
        zeilen.append(
            f"  {f.name:<28}{f.bytes:>10,} B  gzip {f.gzip_bytes:>9,} B "
            f"({f.ratio:.1%}){je_paar}")
    fehlen = [n for n in (ZEITREIHE_NAME, BUNDEL_NAME) if n not in by_name]
    if fehlen:
        zeilen.append(f"  FEHLEN (noch kein Render): {', '.join(fehlen)}")
    summe = sum(f.bytes for f in fragmente)
    summe_gzip = sum(f.gzip_bytes for f in fragmente)
    if fragmente:
        zeilen.append(f"  {'Summe':<28}{summe:>10,} B  gzip {summe_gzip:>9,} B")
    zeilen.append(
        f"  Grenze dieser Auswertung: {grenze:,} B ({grenze / MB:.0f} MB) "
        f"ROHBYTES je Fragment - gzip staucht das SVG auf ~4-5 %, die "
        f"Grenze schuetzt Repository und Browser-Parsing, nicht die Leitung")
    zeilen.append("")

    # --- Prognose: linear ab dem letzten Messtag, pro Fragment-Grenze.
    if not bestand.tage:
        zeilen.append("Prognose: keine Historie - nichts zu projizieren.")
        zeilen.append("")
        zeilen.append(EMPFEHLUNG)
        return "\n".join(zeilen)
    anker = bestand.anker
    assert anker is not None  # tage nicht leer, siehe Zweig oben
    if zeitreihe is None or rate is None or rate <= 0:
        zeilen.append("Prognose: unmoeglich - "
                      + ("kein Zeitreihen-Fragment auf Platt"
                         if zeitreihe is None else
                         "Rate unbestimmt (weniger als 2 Messtage)")
                      + ".")
        zeilen.append("")
        zeilen.append(EMPFEHLUNG)
        return "\n".join(zeilen)
    bytes_je_paar = zeitreihe.bytes / bestand.paare
    wachstum_pro_tag = bytes_je_paar * rate
    grenz_datum, tage_bis, drueber = prognose(
        bytes_je_paar, bestand.paare, rate, grenze, anker)
    zeilen.append(
        f"Prognose Zeitreihen-Fragment (linear, {bytes_je_paar:,.0f} B/Paar x "
        f"{rate:.0f} Paare/Messtag = {wachstum_pro_tag / 1024:,.0f} KB/Messtag,"
        f" ab letztem Messtag {_tag(anker)}):")
    zeilen.append("  Datum        Messpaare   Zeitreihe B     gzip B")
    schritte = sorted(set(PROGNOSE_SCHRITTE)
                      | ({tage_bis} if not drueber and tage_bis <= HORIZONT_TAGE
                         else set()))
    for tage in schritte:
        paare = bestand.paare + rate * tage
        b = bytes_je_paar * paare
        zeilen.append(f"  {_tag(anker + timedelta(days=tage)):<12}"
                      f"{paare:>12,.0f}{b:>14,.0f}{b * zeitreihe.ratio:>14,.0f}"
                      + ("   <-- GRENZE" if tage == tage_bis else ""))
    if drueber:
        zeilen.append(f"  Grenze ({grenze / MB:.0f} MB) ist BEREITS "
                      f"ueberschritten (Stand letzter Messtag {_tag(anker)}: "
                      f"{_mb(zeitreihe.bytes)}).")
    else:
        zeilen.append(f"  {grenze / MB:.0f}-MB-Grenze des Zeitreihen-Fragments "
                      f"erreicht am {_tag(grenz_datum)} "
                      f"(in {tage_bis} Messtagen).")
    buendel = by_name.get(BUNDEL_NAME)
    if buendel:
        # Das Buendel-Fragment waechst mit MODELLTIEFEN, nicht mit Messtagen:
        # die Paar-Prognose traf es nicht. Zu seinem heutigen Stand gegen
        # dieselbe Grenze gerechnet, nur damit die Summe ehrlich bleibt.
        if buendel.bytes > grenze:
            zeilen.append(f"  Buendel-Fragment: {_mb(buendel.bytes)} - Grenze "
                          f"bereits ueberschritten (waechst mit Modellen, "
                          f"nicht mit Messtagen).")
        else:
            rest = grenze - buendel.bytes
            zeilen.append(
                f"  Buendel-Fragment liegt mit {_mb(buendel.bytes)} unter der "
                f"Grenze ({_mb(rest)} Rest); es waechst mit Modellen, nicht "
                f"mit Messtagen - die Paar-Prognose trifft es nicht.")
    zeilen.append("")
    zeilen.append(EMPFEHLUNG)
    return "\n".join(zeilen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=".",
                        help="Repo-Wurzel (default: aktuelles Verzeichnis)")
    parser.add_argument("--heute", default=None, type=date.fromisoformat,
                        help="Stand-Zeile der Auswertung (default: heute; "
                             "die Prognose rechnet ab dem letzten Messtag)")
    parser.add_argument("--grenze-mb", default=None, type=float,
                        help="Grenze in MB ROHBYTES je Fragment (default: 5)")
    args = parser.parse_args(argv)
    grenze = int(args.grenze_mb * MB) if args.grenze_mb else GRENZE_BYTES
    print(bericht(Path(args.root), heute=args.heute, grenze=grenze))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
