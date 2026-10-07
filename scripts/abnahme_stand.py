"""Stand der Abnahme der Geräteseite (Datenkonzept Geräte, Abschnitt 11), ohne Netz.

Liest ``data/state/geraete_tco.json``, die Goldliste ``config/geraete_goldliste.yaml``
und, falls vorhanden, das Probenprotokoll ``docs/abnahme/proben.jsonl``. Druckt je
Prüfpunkt Status, Zahl und Grund, je Anbieter die aufgelöste Goldliste und mit
``--tag`` die Stichprobe dieses Tages. Ohne ``--tag`` gilt der Tag des Bestands. Ein
Bericht: Exit 0 auch bei rot; 1 nur, wenn der Bestand nicht lesbar ist.

    PYTHONPATH=src .venv/bin/python scripts/abnahme_stand.py [--tag 2026-10-07]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from telco_radar.analyze import geraete_abnahme as abnahme
from telco_radar.analyze import geraete_goldliste as gold
from telco_radar.analyze.geraete_pruefkennzahlen import DATEI
from telco_radar.analyze.geraete_pruefstatus import satz_zaehlt
from telco_radar.geraete_config import lade_katalog
from telco_radar.report.geraete_tco_karten import geraet_aus_sku

WURZEL = Path(__file__).resolve().parents[1]
PROBEN = Path("docs") / "abnahme" / "proben.jsonl"
BREITE_PUNKT = 26
BREITE_STATUS = 7
BREITE_ZAHL = 11


def main(argv: list[str] | None = None) -> int:
    teil = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    teil.add_argument("--tag", type=_tag, help="Tag der Stichprobe, JJJJ-MM-TT")
    teil.add_argument(
        "--anzahl",
        type=int,
        default=abnahme.STICHPROBE_MIN,
        choices=range(abnahme.STICHPROBE_MIN, abnahme.STICHPROBE_MAX + 1),
        metavar=f"{abnahme.STICHPROBE_MIN}..{abnahme.STICHPROBE_MAX}",
    )
    teil.add_argument("--wurzel", type=Path, default=WURZEL)
    teil.add_argument("--proben", type=Path, default=PROBEN)
    args = teil.parse_args(argv)
    wurzel = args.wurzel
    pfad = wurzel / "data" / "state" / DATEI
    try:
        bestand = json.loads(pfad.read_text(encoding="utf-8"))
        buendel = [s for s in bestand["buendel"] if isinstance(s, dict)]
        tag = args.tag or str(bestand["updated"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Bestand {pfad} nicht lesbar: {exc!r}", file=sys.stderr)
        return 1
    proben_pfad = wurzel / args.proben
    try:
        proben = (
            abnahme.lies_proben(proben_pfad.read_text(encoding="utf-8"))
            if proben_pfad.exists()
            else None
        )
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Probenprotokoll {proben_pfad} nicht lesbar: {exc!r}", file=sys.stderr)
        return 1
    protokolle = sorted(p.name for p in wurzel.glob(abnahme.BEISPIEL_PROTOKOLLE))
    zaehlend = sum(satz_zaehlt(s, tag) for s in buendel)
    print(f"Abnahme Geräteseite, Tag {tag}: {len(buendel)} Bündel, {zaehlend} zählend")
    print()
    _tabelle(abnahme.stand(buendel, tag, proben, protokolle))
    print()
    _goldliste(wurzel, buendel, tag)
    if args.tag:
        print()
        _stichprobe(buendel, args.tag, args.anzahl)
    return 0


def _tag(text: str) -> str:
    return date.fromisoformat(text).isoformat()


def _tabelle(punkte: list[abnahme.Pruefpunkt]) -> None:
    breiten = (BREITE_PUNKT, BREITE_STATUS, BREITE_ZAHL)
    zeilen = [(("Prüfpunkt", "Status", "Zahl"), "Grund")]
    for p in punkte:
        zahl = "—" if p.zahl is None else f"{p.zahl} {p.einheit}".strip()
        zeilen.append(((p.name, p.status, zahl), p.grund))
    for zellen, grund in zeilen:
        zeile = "  ".join(t.ljust(b) for t, b in zip(zellen, breiten, strict=True))
        print(f"{zeile}  {grund}")


def _goldliste(wurzel: Path, buendel: list[dict], tag: str) -> None:
    try:
        eintraege = gold.lade_goldliste(wurzel)
    except gold.GoldlisteFehler as exc:
        print(f"Goldliste: {exc}")
        return
    katalog = lade_katalog(wurzel)
    aufgeloest = gold.goldliste_aufloesen(
        eintraege, buendel, lambda sku: geraet_aus_sku(sku, katalog)
    )
    gefunden = sum(a.buendel is not None for a in aufgeloest)
    print(f"Goldliste ({gold.GOLDLISTE}): {gefunden} von {len(aufgeloest)} gefunden")
    for anbieter in dict.fromkeys(a.eintrag.anbieter for a in aufgeloest):
        eigene = [a for a in aufgeloest if a.eintrag.anbieter == anbieter]
        treffer = sum(a.buendel is not None for a in eigene)
        print(f"{anbieter}: {treffer} von {len(eigene)} gefunden")
        for nummer, a in enumerate(eigene, start=1):
            e = a.eintrag
            if a.buendel is None:
                variante = (
                    f"{e.device_id} {e.speicher_gb} GB {e.farbe or 'jede Farbe'}, "
                    f"{e.tarif_name}, {e.laufzeit_monate} Raten"
                )
                befund = f"{a.befund} {', '.join(a.kandidaten)}".strip()
                print(f"  {nummer:2}  {variante}: {befund}")
                continue
            zaehlt = "zählt" if satz_zaehlt(a.buendel, tag) else "zählt nicht"
            stand = a.buendel.get("abgerufen_am")
            print(f"  {nummer:2}  {a.buendel.get('id')}: {zaehlt}, Stand {stand}")


def _stichprobe(buendel: list[dict], tag: str, anzahl: int) -> None:
    print(f"Stichprobe {tag}, je Anbieter {anzahl} zählende Bündel")
    for anbieter in sorted({str(s.get("anbieter") or "") for s in buendel} - {""}):
        gezogen = abnahme.stichprobe(buendel, anbieter, tag, anzahl)
        print(f"{anbieter}: {len(gezogen)}")
        for satz in gezogen:
            print(f"  {satz.get('id')}  {satz.get('quelle_url')}")


if __name__ == "__main__":
    sys.exit(main())
