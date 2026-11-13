"""Klick-Zusammenführung mit dem Beleg der Gerätelisten (Preisprüfung 11.10.2026).

``zusammenfuehren`` wie ``klick_zusammenfuehrung.zusammenfuehren``, dazu je Anbieter,
dessen Geräteliste heute ganz gelesen wurde (``GeraeteDB.lesezustand``), die Speicher
seiner aktiven Neugeräte (``klick_erfassung.angebotene_speicher``) aus dem Bestand
``ZUSTAND``, den der Gerätelauf vorher gespeichert hat. Ein Speicher, den die Liste
nicht führt, heißt auf der Seite „nicht im Angebot“, nicht „nicht erfasst“.
"""

from __future__ import annotations

from pathlib import Path

from ..geraete_model import Katalog
from .geraete_store import GELESEN, GeraeteDB
from .klick_erfassung import Angebot, angebotene_speicher
from .klick_nachholen import Nachholen, frischer_ordner
from .klick_zusammenfuehrung import Geraet, Zusammenfuehrung
from .klick_zusammenfuehrung import zusammenfuehren as _zusammenfuehren

ZUSTAND = Path("data") / "state" / "geraete_db.json"


def angebot_aus(db: GeraeteDB, heute: str) -> Angebot:
    """Je Anbieter mit heute ganz gelesener Geräteliste und Gerät die Speicher."""
    listungen = db.eintraege()
    namen = {str(x.get("anbieter")) for x in listungen}
    gelesen = {a for a in namen if db.lesezustand(a, heute) == GELESEN}
    return angebotene_speicher(listungen, gelesen, heute)


def zusammenfuehren(
    adapter: list[dict],
    ordner: Path | None,
    root: Path,
    katalog: Katalog,
    heute: str,
    geraet: Geraet,
    nachholen: Nachholen | None = None,
) -> Zusammenfuehrung:
    """``klick_zusammenfuehrung.zusammenfuehren`` mit ``Zusammenfuehrung.angebot``.

    Mit ``nachholen`` zuvor den Klick-Stand von origin holen, wenn der im Arbeitsbaum
    nicht vom Messtag ist (``klick_nachholen``); der Befund steht in der Bilanz.
    """
    with frischer_ordner(nachholen, ordner, root, heute) as frisch:
        zug = _zusammenfuehren(adapter, frisch or ordner, root, katalog, heute, geraet)
    if nachholen is not None and nachholen.bilanz and zug.bilanz is not None:
        zug.bilanz["nachholen"] = nachholen.bilanz
    if (root / ZUSTAND).is_file():
        zug.angebot = angebot_aus(GeraeteDB(root / ZUSTAND), heute)
    return zug
