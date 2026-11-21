"""Eine Angebotszählung, die erst NACH dem Gerätelauf des Messtags ankommt.

Regelfall: ``angebot.yml`` zählt ab 23:05 UTC, der Gerätelauf desselben Messtags
(ab etwa 03:00 UTC) liest die Datei beim Einhängen (``geraete_nachtlauf``). Kommt
die Zählung später (verspäteter Lauf, Warten auf einen Klick-Lauf, Hand-Lauf), steigt
ein weiterer Gerätelauf mit „Heute schon gemessen?“ aus und läse sie nie. Dann hängt
der Ablage-Job von ``angebot.yml`` sie hier in die vorhandene Lauf-Datei des Messtags
ein: dieselbe Funktion (``einhaengen.haenge_ein``), dieselben Signale
(``geraete_nachtlauf.signale_fuer``), Bündel des Messtags aus dem Bestand. Gibt es
noch keine Lauf-Datei, passiert nichts (der Gerätelauf liest die Zählung selbst).
Die Seite zeigt den Nachtrag beim nächsten Seitenbau.

Aufruf (Ablage-Job)::

    PYTHONPATH=src python -m telco_radar.geraete_angebot_nachtrag --root . --datum <tag>
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

from . import geraete_lauf
from .geraete_angebot.einhaengen import haenge_ein
from .geraete_vollstaendigkeit import Signale


def trage_nach(
    state_dir: Path,
    datum: str,
    buendel: Iterable,
    signale: Signale,
    katalog,
    namen: dict | None = None,
) -> Path | None:
    """Hängt die Zählungen des Messtags in dessen Lauf-Datei ein; ``None``, wenn es
    keine Lauf-Datei gibt oder ihre Zählung gescheitert ist (dann bleibt sie, wie sie
    ist)."""
    lauf = geraete_lauf.lies(state_dir, datum)
    if lauf is None:
        return None
    voll = lauf.get("vollstaendigkeit")
    if not isinstance(voll, dict) or voll.get("fehler"):
        return None
    haenge_ein(voll, state_dir, datum, buendel, signale, katalog, namen)
    inhalt = {k: v for k, v in lauf.items() if k not in ("format", "datum")}
    return geraete_lauf.schreibe(state_dir, datum, inhalt)


def main(argv: list[str] | None = None) -> int:
    """Liest Bestand, Katalog und Lauf-Datei, trägt nach; 0 auch ohne Lauf-Datei."""
    from . import geraete_soll
    from .analyze.tco_store import TcoDB
    from .geraete_config import lade_katalog
    from .geraete_nachtlauf import signale_fuer

    p = argparse.ArgumentParser(description="Angebotszaehlung nachtragen")
    p.add_argument("--root", default=".")
    p.add_argument("--datum", required=True)
    args = p.parse_args(argv)
    root = Path(args.root)
    state = root / "data" / "state"
    try:
        lauf = geraete_lauf.lies(state, args.datum)
    except geraete_lauf.LaufDateiFehler as fehler:
        print(
            f"::warning::Lauf-Datei {args.datum} nicht lesbar, kein Nachtrag: {fehler}"
        )
        return 0
    if lauf is None:
        print(
            f"Keine Lauf-Datei für {args.datum}: "
            "der Gerätelauf liest die Zählung selbst."
        )
        return 0
    tco = TcoDB(state / "geraete_tco.json")
    katalog = lade_katalog(root)
    namen = {g.device_id: geraete_soll.anzeigename(g) for g in katalog.geraete}
    signale = signale_fuer(tco, dict(lauf.get("bilanz") or {}), args.datum)
    ziel = trage_nach(state, args.datum, list(tco.buendel()), signale, katalog, namen)
    print(
        f"Nachtrag: {ziel}"
        if ziel
        else "Kein Nachtrag (Zählung der Lauf-Datei gescheitert)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
