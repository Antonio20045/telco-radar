"""„Nur mit … im Angebot“ aus der Seite selbst (Preisprüfung 11.10.2026, Punkt f).

Klick-Lauf 12.10.2026: Telekom zeigt beim iPhone 17 Pro Max auf allen fünf Tarifseiten
den Knopf „2 TB“ gesperrt („Seite bietet speicher 2 TB nicht an“), beim Pixel 11 den
Knopf „512 GB“. Telekom hat keine gelesene Geräteliste; der Satz „im Angebot“ ist dann
nur belegt, wenn die Seite jeden nicht gelesenen Speicher gesperrt zeigt.
"""

from __future__ import annotations

from telco_radar.analyze.klick_erfassung import (
    SATZ_SPEICHER,
    SATZ_SPEICHER_ANGEBOT,
    je_anbieter_vereint,
    speicher_gelesen,
)
from telco_radar.analyze.klick_teillauf import speicher_seite


def _kombi(speicher: str, status: str) -> dict:
    return {"variante": {"speicher": speicher, "laufzeit": 24}, "status": status}


def _seite(*kombis: dict) -> dict:
    return {
        "geraet": "apple-iphone-17-pro-max",
        "status": "gelesen",
        "kombinationen": list(kombis),
    }


def _eintrag(seiten: list[dict]) -> dict:
    return {
        "anbieter": "Telekom",
        "datum": "2026-10-12",
        "alter_tage": 0,
        "speicher_gelesen": {"apple-iphone-17-pro-max": [256, 512, 1024]},
        "speicher_seite": speicher_seite(seiten),
    }


def _satz(vorlage: str) -> str:
    return vorlage.format(
        anbieter="Telekom", speicher="256 GB, 512 GB und 1 TB", datum="12.10.2026"
    )


def test_gesperrter_speicher_belegt_im_angebot():
    seite = _seite(
        _kombi("256 GB", "erfasst"),
        _kombi("1 TB", "erfasst"),
        _kombi("2 TB", "nicht_angeboten"),
    )
    (eintrag,) = je_anbieter_vereint([_eintrag([seite])])
    saetze = speicher_gelesen(eintrag)
    assert saetze["Telekom|apple-iphone-17-pro-max"] == _satz(SATZ_SPEICHER_ANGEBOT)


def test_gegenprobe_nicht_erfasster_speicher_bleibt_gelesen():
    seite = _seite(
        _kombi("256 GB", "erfasst"),
        _kombi("2 TB", "nicht_angeboten"),
        _kombi("2 TB", "nicht_erfasst"),
    )
    andere = {**_seite(_kombi("2 TB", "nicht_erfasst")), "status": "gelesen"}
    (eintrag,) = je_anbieter_vereint([_eintrag([seite]), _eintrag([andere])])
    saetze = speicher_gelesen(eintrag)
    assert saetze["Telekom|apple-iphone-17-pro-max"] == _satz(SATZ_SPEICHER)


def test_gegenprobe_ohne_gesperrten_speicher_kein_beleg():
    seite = _seite(_kombi("256 GB", "erfasst"))
    (eintrag,) = je_anbieter_vereint([_eintrag([seite])])
    saetze = speicher_gelesen(eintrag)
    assert saetze["Telekom|apple-iphone-17-pro-max"] == _satz(SATZ_SPEICHER)


def test_offener_speicher_der_spaeter_gelesen_ist_stoert_nicht():
    """Eine Laufzeit nicht erfasst, derselbe Speicher sonst gelesen: kein offener
    Speicher."""
    seite = _seite(
        _kombi("256 GB", "erfasst"),
        _kombi("512 GB", "nicht_erfasst"),
        _kombi("2 TB", "nicht_angeboten"),
    )
    (eintrag,) = je_anbieter_vereint([_eintrag([seite])])
    saetze = speicher_gelesen(eintrag)
    assert saetze["Telekom|apple-iphone-17-pro-max"] == _satz(SATZ_SPEICHER_ANGEBOT)
