"""Kopf einer Klick-Ergebnisdatei für die Bilanz der Zusammenführung.

Aus ``klick_zusammenfuehrung`` herausgelöst: Alter der Datei, der Grund, warum sie
nicht zählt, und, wenn sie zählt, ihre Rohsätze und Gerätepreise ohne Tarif.
"""

from __future__ import annotations

from datetime import date

from ..collect.geraete.klickergebnis import FRISCHEGRENZE_TAGE
from ..collect.geraete.klicklauf import LAUF_GELESEN, LAUF_GESTOERT
from ..geraete_model import Katalog
from .klick_teillauf import ausbeute_der_seiten

GRUND_NICHT_HEUTE = "Datei vom {datum}, nicht von heute"
GRUND_VERALTET = "Datei vom {datum}, älter als {tage} Tage"
GRUND_ZUKUNFT = "Datei vom {datum}, nach heute"
GRUND_DATUM = "Datum der Datei unlesbar: {datum!r}"


def alter_tage(datum: object, heute: str) -> int | None:
    """Tage von ``datum`` bis ``heute``; ``None``, wenn ``datum`` kein ISO-Datum ist."""
    try:
        return (date.fromisoformat(heute) - date.fromisoformat(str(datum))).days
    except ValueError:
        return None


def kopf_der_datei(
    daten: dict, katalog: Katalog, heute: str
) -> tuple[dict, list[dict], list[dict]]:
    """Kopf einer Ergebnisdatei für die Bilanz und, wenn verwendet, ihre Rohsätze und
    Gerätepreise ohne Tarif."""
    status = daten.get("laufstatus")
    datum = daten.get("datum")
    alter = alter_tage(datum, heute)
    eintrag = {
        "anbieter": daten.get("name"),
        "datum": datum,
        "alter_tage": alter,
        "laufstatus": status,
        "grund": daten.get("grund"),
        "ueberfaellig": list(daten.get("ueberfaellig") or []),
        "verwendet": False,
        "warum_nicht": None,
    }
    if alter is None:
        eintrag["warum_nicht"] = GRUND_DATUM.format(datum=datum)
    elif alter < 0:
        eintrag["warum_nicht"] = GRUND_ZUKUNFT.format(datum=datum)
    elif alter >= FRISCHEGRENZE_TAGE:
        grund = GRUND_VERALTET.format(datum=datum, tage=FRISCHEGRENZE_TAGE)
        eintrag["warum_nicht"] = grund
    elif alter > 0:
        eintrag["warum_nicht"] = GRUND_NICHT_HEUTE.format(datum=datum)
    elif status != LAUF_GELESEN:
        eintrag["warum_nicht"] = f"Lauf {status}: {daten.get('grund')}"
    teil = status == LAUF_GESTOERT and alter == 0
    if eintrag["warum_nicht"] is not None and not teil:
        return eintrag, [], []
    aus, felder = ausbeute_der_seiten(daten, katalog, teil)
    eintrag.update(aus.als_daten(), **felder)
    return eintrag, aus.rohsaetze, aus.ohne_tarif
