"""Klick-Bündel, die ein späterer Klick-Lauf nicht mehr bestätigt.

Der Bestand löscht kein Bündel (``analyze/tco_store``); eine Messung des Klick-Crawlers
bleibt mit ihrem Datum stehen, bis sie altert. Eine falsch zugeordnete Kachel (Galaxy
A57 mit Galaxy Buds als 256 GB, Lauf vom 09.10.2026) stünde so tagelang als Preis da.

Überholt ist ein Klick-Bündel, wenn derselbe Anbieter danach per Klick-Crawler beides
wieder gelesen hat: dieselbe Geräteseite (ein jüngeres Klick-Bündel desselben Geräts in
derselben Speichergröße) und denselben Tarif (ein jüngeres Klick-Bündel dieses Tarifs) -
und das Bündel dabei nicht wieder vorkam. Fehlt einer der beiden Belege, war die Seite
vielleicht nur nicht gelesen; „nicht gelesen“ ist nicht „leer“, das Bündel bleibt.
Die Geräteseite zählt je Ratenzahl: Ein Bündel mit 24 Raten von einer Telekom-
Produktseite überholt erst ein jüngeres mit 24 Raten, nicht die Übersicht mit 36.
"""

from __future__ import annotations

import re

from ..tarif_model import QUELLE_KLICK

_GERAET_SPEICHER_RE = re.compile(r"^(.+?-\d+(?:gb|tb))(?:-|$)")


def _geraet_speicher(sku_id: object) -> str | None:
    treffer = _GERAET_SPEICHER_RE.match(str(sku_id or ""))
    return treffer.group(1) if treffer else None


def _juengster(tage: dict, schluessel: tuple, datum: str) -> None:
    if datum > tage.get(schluessel, ""):
        tage[schluessel] = datum


def _seite(eintrag: dict, geraet: str) -> tuple:
    return eintrag.get("anbieter"), geraet, eintrag.get("laufzeit_monate")


def ueberholt(eintraege: list[dict]) -> set[str]:
    """Die IDs der überholten Klick-Bündel (Regel im Modulkopf)."""
    klick = [
        e
        for e in eintraege
        if isinstance(e, dict)
        and e.get("quelle_art") == QUELLE_KLICK
        and e.get("abgerufen_am")
    ]
    je_geraet: dict = {}
    je_tarif: dict = {}
    for e in klick:
        datum = str(e["abgerufen_am"])
        geraet = _geraet_speicher(e.get("sku_id"))
        if geraet is not None:
            _juengster(je_geraet, _seite(e, geraet), datum)
        _juengster(je_tarif, (e.get("anbieter"), e.get("tarif_name")), datum)
    weg: set[str] = set()
    for e in klick:
        datum = str(e["abgerufen_am"])
        geraet = _geraet_speicher(e.get("sku_id"))
        if geraet is None:
            continue
        seite = je_geraet.get(_seite(e, geraet), "")
        tarif = je_tarif.get((e.get("anbieter"), e.get("tarif_name")), "")
        if seite > datum and tarif > datum:
            weg.add(str(e.get("id")))
    return weg


def ohne_ueberholte(eintraege: list[dict]) -> list[dict]:
    """Die Einträge ohne überholte Klick-Bündel, in ihrer Reihenfolge."""
    weg = ueberholt(eintraege)
    return [e for e in eintraege if not (isinstance(e, dict) and e.get("id") in weg)]
