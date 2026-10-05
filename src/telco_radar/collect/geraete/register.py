"""Traegt die anbietereigenen Adapter ins Verzeichnis ein.

Nur dieses Modul kennt alle sechs Adapter. Sie selbst importieren aus dem
Paket nur `basis`, so bleiben sie voneinander unabhaengig (Vertrag
`adapter-unabhaengig` in `.importlinter`).
"""

from __future__ import annotations

from . import congstar, einsundeins, o2, saturn, telekom, vodafone
from .basis import Adapter, registriere


def registriere_anbieter_adapter() -> None:
    """Die anbietereigenen Adapter, jeder mit EIGENEM Methodennamen."""
    registriere(
        "vodafone_api",
        Adapter(
            name="vodafone_api",
            lies=vodafone.lies,
            ernte=vodafone.ernte,
            lies_buendel=vodafone.lies_buendel,
            loese_tarifnamen=vodafone.loese_tarifnamen,
        ),
    )
    registriere(
        "o2_katalog",
        Adapter(
            name="o2_katalog",
            lies=o2.lies,
            lies_buendel=o2.lies_buendel,
            vertiefe_buendel=o2.vertiefe_buendel,
            fuehre_zusammen=o2.fuehre_zusammen,
            direkt=True,
        ),
    )
    registriere(
        "congstar_next",
        Adapter(
            name="congstar_next",
            lies=congstar.lies,
            lies_buendel=congstar.lies_buendel,
        ),
    )
    registriere(
        "telekom_kategorie",
        Adapter(
            name="telekom_kategorie",
            lies=telekom.lies,
            lies_buendel=telekom.lies_buendel,
            direkt=True,
        ),
    )
    registriere(
        "einsundeins_buendel",
        Adapter(
            name="einsundeins_buendel",
            lies=einsundeins.lies,
            ernte=einsundeins.ernte,
            lies_buendel=einsundeins.lies_buendel,
            ergaenze_buendel=einsundeins.ergaenze_buendel,
        ),
    )
    registriere(
        "saturn_brand",
        Adapter(name="saturn_brand", lies=saturn.lies, direkt=True),
    )
