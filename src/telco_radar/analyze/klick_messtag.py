"""Wer den Messtag eines Bündels bekommt: die heutige Messung oder der Klick-Wert.

Die Regel steht im Kopf von ``klick_zusammenfuehrung``; hier steht sie als Code.
``teile_nach_messtag`` teilt die heutigen Bündel in zwei Gruppen:

``bleiben``       das Bündel kommt in den Bestand und trägt den heutigen Messtag;
``gewichen``      es weicht einer frischen Klick-Messung im Bestand (``klick_vorrang``).

Vorrang hat eine Klick-Messung nur, solange ihr Anbieter im Klick-Tagesplan steht
(``geplant``). o2 und congstar stehen seit 21.11.2026 nicht mehr darin: ihre letzte
Klick-Messung im Bestand verdrängt die heutige Adaptermessung nicht, sonst fehlten
ihre Bündel bis zur Frischegrenze im Messtag. Die Preisgrenze, die bis dahin nur bei
congstar entschied, ob eine ältere Messung weicht (Befund 13.11.2026), ist mit
congstars Klick-Weg entfallen.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from ..collect.geraete.klickergebnis import FRISCHEGRENZE_TAGE
from ..collect.geraete.klickrohsatz import QUELLE, ZUSTAND_NEU, tarifschluessel
from ..tco_model import Buendel, laufzeit_in_monaten
from .klick_alter import alter_tage
from .klick_geschwister import Schluessel

Geraet = Callable[[str], tuple[str, int | None]]


@dataclass
class Aufteilung:
    """Die zwei Gruppen; ``gewichen`` je Eintrag ``(Bündel, Bestandseintrag)``."""

    bleiben: list[Buendel] = field(default_factory=list)
    gewichen: list[tuple] = field(default_factory=list)


def teile_nach_messtag(
    buendel: Iterable[Buendel],
    nach_id: Callable[[str], dict | None],
    heute: str,
    geplant: Iterable[str] | None = None,
) -> Aufteilung:
    """Die heutigen Bündel nach der Regel aus dem Modulkopf aufgeteilt.

    ``geplant`` sind die Anbieter des Klick-Tagesplans; ``None`` (Plan unbekannt)
    heißt: jeder Anbieter zählt als geplant.
    """
    plan = None if geplant is None else set(geplant)
    teile = Aufteilung()
    for satz in buendel:
        eintrag = nach_id(satz.id)
        im_plan = plan is None or satz.anbieter in plan
        alter = None if eintrag is None else klickalter(satz, eintrag, heute)
        if eintrag is None or alter is None or not im_plan:
            teile.bleiben.append(satz)
            continue
        teile.gewichen.append((satz, eintrag))
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


def klickalter(buendel: Buendel, eintrag: dict, heute: str) -> int | None:
    """Das Alter der frischen Klick-Messung im Bestandseintrag dieses Adapterbündels;
    ``None``, wenn es keine gibt oder sie ``FRISCHEGRENZE_TAGE`` erreicht hat."""
    if buendel.quelle_art == QUELLE or eintrag.get("quelle_art") != QUELLE:
        return None
    alter = alter_tage(eintrag.get("abgerufen_am"), heute)
    if alter is None or not 0 <= alter < FRISCHEGRENZE_TAGE:
        return None
    return alter
