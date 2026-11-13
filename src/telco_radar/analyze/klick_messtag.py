"""Wer den Messtag eines Bündels bekommt: die heutige Messung oder der Klick-Wert.

Die Regel steht im Kopf von ``klick_zusammenfuehrung``; hier steht sie als Code.
``teile_nach_messtag`` teilt die heutigen Bündel in drei Gruppen:

``bleiben``       das Bündel kommt in den Bestand und trägt den heutigen Messtag;
``gewichen``      es weicht einer Klick-Messung im Bestand (``klick_vorrang``);
``widerspruch``   die Teilmenge von ``gewichen``, die einer ÄLTEREN Klick-Messung
                  weicht, weil sie ihr widerspricht - diese Fälle sind benannt
                  (``klick_alter.widerspruch_zeilen``), denn sie kosten einen
                  Messtag.

Verglichen wird mit der heutigen Klick-Lesung desselben Schlüssels (``gelesen``),
wenn es sie gibt - sie ist am selben Tag an derselben Seite gemessen und damit der
belastbarere Zeuge -, sonst mit dem Bestandseintrag selbst.

Die Preisgrenze gilt nur für ``ANBIETER_PREISGRENZE`` (Befund 13.11.2026 betraf nur
congstar): bei jedem anderen Anbieter weicht eine ältere, frische Klick-Messung
unverändert wie vor diesem Befund - unabhängig davon, ob sie widerspricht.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from ..collect.geraete.klickergebnis import FRISCHEGRENZE_TAGE
from ..collect.geraete.klickrohsatz import QUELLE, ZUSTAND_NEU, tarifschluessel
from ..tco_model import Buendel, laufzeit_in_monaten
from .klick_alter import alter_tage
from .klick_geschwister import Schluessel
from .klick_preisgrenze import PREISFELDER, widersprueche

Geraet = Callable[[str], tuple[str, int | None]]

ANBIETER_PREISGRENZE = "congstar"
"""Nur bei diesem Anbieter weicht eine ältere, frische Klick-Messung dem heutigen
Bündel nicht mehr unbedingt - sondern nur, wenn sie ihm widerspricht."""


@dataclass
class Aufteilung:
    """Die drei Gruppen; ``widerspruch`` je Eintrag ``(Bündel, Eintrag, Felder)``."""

    bleiben: list[Buendel] = field(default_factory=list)
    gewichen: list[tuple] = field(default_factory=list)
    widerspruch: list[tuple] = field(default_factory=list)


def teile_nach_messtag(
    buendel: Iterable[Buendel],
    nach_id: Callable[[str], dict | None],
    heute: str,
    gelesen: Callable[[Buendel], dict | None],
) -> Aufteilung:
    """Die heutigen Bündel nach der Regel aus dem Modulkopf aufgeteilt."""
    teile = Aufteilung()
    for satz in buendel:
        eintrag = nach_id(satz.id)
        alter = None if eintrag is None else klickalter(satz, eintrag, heute)
        if eintrag is None or alter is None:
            teile.bleiben.append(satz)
            continue
        if alter == 0 or satz.anbieter != ANBIETER_PREISGRENZE:
            teile.gewichen.append((satz, eintrag))
            continue
        gemessen = {feld: getattr(satz, feld, None) for feld in PREISFELDER}
        felder = widersprueche(gemessen, gelesen(satz) or eintrag)
        if not felder:
            teile.bleiben.append(satz)
            continue
        teile.gewichen.append((satz, eintrag))
        teile.widerspruch.append((satz, eintrag, felder))
    return teile


def adapterschluessel(satz: dict, geraet: Geraet) -> list[Schluessel]:
    """Je Tarifschreibweise (Name, Slug) ein Schlüssel; nur Geräte im Zustand neu."""
    if str(satz.get("zustand") or ZUSTAND_NEU) != ZUSTAND_NEU:
        return []
    device, speicher = geraet(str(satz.get("sku_id") or ""))
    if not device:
        return []
    speicher = satz.get("speicher_gb") if speicher is None else speicher
    laufzeit = laufzeit_in_monaten(satz.get("laufzeit_monate"))
    tarife = {tarifschluessel(satz.get(f)) for f in ("tarif_name", "tarif_slug")}
    anbieter = str(satz.get("anbieter"))
    return [(anbieter, device, speicher, t, laufzeit) for t in sorted(tarife) if t]


def lesung_zum_buendel(satz: Buendel, messung: dict, geraet: Geraet) -> dict | None:
    """Der heutige Klick-Satz zum Schlüssel dieses Bündels, wenn es ihn gibt."""
    roh = {
        "anbieter": satz.anbieter,
        "sku_id": satz.sku_id,
        "zustand": satz.zustand,
        "tarif_name": satz.tarif_name,
        "laufzeit_monate": satz.laufzeit_monate,
    }
    return next(
        (messung[s] for s in adapterschluessel(roh, geraet) if s in messung), None
    )


def klickalter(buendel: Buendel, eintrag: dict, heute: str) -> int | None:
    """Das Alter der frischen Klick-Messung im Bestandseintrag dieses Adapterbündels;
    ``None``, wenn es keine gibt oder sie ``FRISCHEGRENZE_TAGE`` erreicht hat."""
    if buendel.quelle_art == QUELLE or eintrag.get("quelle_art") != QUELLE:
        return None
    alter = alter_tage(eintrag.get("abgerufen_am"), heute)
    if alter is None or not 0 <= alter < FRISCHEGRENZE_TAGE:
        return None
    return alter
