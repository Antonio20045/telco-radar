"""Der Massstab des Reiters "Was kostet es": was der Tarif ALLEIN kostet.

Aus ``geraete_tco_view`` herausgelöst (dort darf die Datei nicht wachsen); die Ansicht
ruft ``referenztabelle`` weiter auf.
"""

from __future__ import annotations

from ..tarif_model import PREISTYP_LIVE_SHOP
from ..tco_model import SimOnlyReferenz, tco_24

EIGEN = "vodafone"


def _eigen(anbieter: str) -> bool:
    return (anbieter or "").strip().lower() == EIGEN


def referenztabelle(referenzen: list) -> list[dict]:
    """Der Massstab, den Phase 6 geliefert hat: was der Tarif ALLEIN kostet.

    Diese Zahl ist der Grund, warum ein effektiver Geraetepreis ueberhaupt
    rechenbar ist (`tco_model.SimOnlyReferenz`) - und sie steht in keiner
    Werbung. Meistens kommt sie aus dem Produktinformationsblatt nach § 1
    TK-TransparenzV, dem einzigen Dokument dieses Marktes, das rechtlich
    wahrheitsbewehrt ist - seit dem 05.09.2026 kann sie auch aus einer
    LIVE-Shop-Seite stammen (`Tarif.preistyp == "live_shop"`,
    `analyze/tarif_referenzen.py`). `quelle_ist_dokument` traegt das an die
    Vorlage weiter: nur ein Pflichtdokument heisst dort
    "Produktinformationsblatt", eine Shop-Seite heisst "Shop-Seite" - ein
    Beleglink, der das falsche Wort traegt, ist selbst eine Falschangabe.

    Sortiert wird der EIGENE Anbieter zuerst, dann nach Anbietername und
    Betrag - dieselbe Ordnung wie auf jeder anderen Tafel dieser Seite. Es
    ist ausdruecklich KEINE Rangliste nach Guenstigkeit: ein Tarif mit mehr
    Datenvolumen kostet zu Recht mehr, und diese Tafel rechnet das nicht
    heraus.
    """
    zeilen = []
    for r in referenzen:
        if not isinstance(r, SimOnlyReferenz) or r.tarif_sim_only_monatlich is None:
            continue
        kennzahl, allein = tco_24(r.als_buendel()), tco_24(r.als_buendel(False))
        zeilen.append(
            {
                "anbieter": r.anbieter,
                "eigen": _eigen(r.anbieter),
                "tarif": r.tarif_name,
                "tarif_id": r.tarif_id,
                "monatlich": r.tarif_sim_only_monatlich,
                "ueber_horizont": (kennzahl.gesamt if kennzahl.belastbar else None),
                "tarif_ueber_horizont": allein.gesamt if allein.belastbar else None,
                "leitzahl_monate": kennzahl.leitzahl_monate,
                "anschlusspreis": r.anschlusspreis,
                "quelle_url": r.quelle_url,
                "abgerufen_am": r.abgerufen_am,
                "quelle_ist_dokument": r.quelle_art != PREISTYP_LIVE_SHOP,
            }
        )
    return sorted(zeilen, key=lambda z: (not z["eigen"], z["anbieter"], z["monatlich"]))
