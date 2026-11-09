"""Die Stufe je Bündelzeile: die ihres Tarifs, bei Unbegrenzt nur mit Beleg.

``geraete_tco_band.tarif_baender`` ordnet jedem TARIF eine Stufe zu. Ein unbegrenzter
Tarif steht damit in der obersten Stufe XL (``band_regel.stufe_fuer``). Eine ZEILE
dieses Tarifs darf dort nur stehen, wenn ihr Preis trägt
(``band_regel.unbegrenzt_ohne_beleg``): Bündelpreis und Ablöse am Gerät gemessen
(``geraete_pruefstatus.ist_gemessen``, nicht aus einem Raster abgeleitet) und die
jüngste Messung ohne widersprüchliche zweite Angabe (``geraete_schwankung``). Jede
andere Zeile bleibt "Ohne Tarifband", ihr Preis bleibt sichtbar. Für endliche Tarife
ändert sich nichts.

Gilt für jeden Anbieter gleich; es gibt keine Verzweigung nach dem Namen. Karten,
Export, Radar und Zeitreihe lesen die Stufe über ``band_regel.band_fuer``.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..analyze.geraete_pruefstatus import ist_gemessen
from ..band_regel import Tarifbaender, unbegrenzt_ohne_beleg
from ..tco_model import Buendel
from . import geraete_tco_band


def _volumen(tarife: dict, tarif_id: str) -> float | None:
    """Das erhobene Datenvolumen des Tarifs (Plus-Fassung und Variante nach ``#``
    erben es vom Grundtarif)."""
    grund = tarif_id.split("#", 1)[0]
    for tid in (tarif_id, grund, grund.removesuffix("-plus")):
        if tid in tarife:
            return geraete_tco_band._zahl((tarife[tid] or {}).get("datenvolumen_gb"))
    return None


def zeilen_baender(
    tarife: dict,
    buendel: Iterable,
    schwankend: Iterable[str] | None,
    leiter=None,
) -> Tarifbaender:
    """Die Stufen der Tarife plus die Zeilen, die keine tragen.

    ``schwankend`` sind die IDs mit springenden Werten (``geraete_schwankung``);
    ``None`` heißt "Historie nicht gelesen": dann trägt keine Zeile eines
    unbegrenzten Tarifs eine Stufe."""
    baender = geraete_tco_band.tarif_baender(tarife, leiter)
    springend = None if schwankend is None else frozenset(schwankend)
    ohne: set[str] = set()
    for b in buendel:
        if not isinstance(b, Buendel) or baender.get(b.tarif_id or "") is None:
            continue
        bid = b.id
        belegt = (
            springend is not None
            and bid not in springend
            and ist_gemessen(b.herleitung, b.quelle_art)
        )
        if unbegrenzt_ohne_beleg(_volumen(tarife, b.tarif_id), belegt):
            ohne.add(bid)
    return Tarifbaender(baender, ohne)
