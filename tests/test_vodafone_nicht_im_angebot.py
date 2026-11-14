"""„Bei Vodafone nicht im Angebot“ ohne Klick-Übersicht (A-SMVWHB, 14.11.2026).

Vodafone hat keine Klick-Übersicht (die Karte klickt nur Produktseiten), darum blieb
``SATZ_NICHT_IM_ANGEBOT`` für Vodafone immer leer, obwohl der Adapter-Lauf selbst
täglich die volle Geräteliste liest (``collect.geraete.vodafone.ernte``, Bestand in
``geraete_db.json``). ``nicht_im_angebot_aus_angebot`` zieht denselben Satz aus dem
``Angebot``, das ``angebotene_speicher`` (``klick_angebot.angebot_aus`` in der
Pipeline) aus einer heute GANZ gelesenen Adapterliste baut - kein neuer Abruf, nur
eine zweite Quelle für dieselbe Aussage.
"""

from __future__ import annotations

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.analyze.klick_erfassung import (
    SATZ_NICHT_IM_ANGEBOT,
    TRENNER,
    angebotene_speicher,
    nicht_im_angebot_aus_angebot,
)
from telco_radar.geraete_config import lade_katalog

HEUTE = "2026-11-13"
DATUM = "13.11.2026"
FEHLENDES_GERAET = "fairphone-6-plus"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _listung(anbieter: str, device_id: str, **anders) -> dict:
    return {
        "anbieter": anbieter,
        "device_id": device_id,
        "speicher_gb": 256,
        "status": "aktiv",
        "zustand": "neu",
        "last_verified": HEUTE,
        **anders,
    }


def test_vodafone_fehlendes_katalog_geraet_bekommt_beleg(katalog):
    """Die Geräteliste trägt ein Katalog-Gerät nicht: derselbe Satz wie bei einer
    ganz gelesenen Klick-Übersicht von 1&1/Telekom, nur ohne Übersicht."""
    angebot = {"Vodafone": {"apple-iphone-17-pro": {256}}}
    saetze = nicht_im_angebot_aus_angebot(angebot, katalog, HEUTE)
    schluessel = f"Vodafone{TRENNER}{FEHLENDES_GERAET}"
    assert saetze[schluessel] == SATZ_NICHT_IM_ANGEBOT.format(
        anbieter="Vodafone", datum=DATUM
    )
    assert f"Vodafone{TRENNER}apple-iphone-17-pro" not in saetze


def test_ohne_ganz_gelesene_liste_entsteht_kein_beleg(katalog):
    """Fehlt der Anbieter im Angebot (Lauf gestört, leer, unvollständig), bleibt
    jede Lücke eine Messlücke - lieber eine Lücke als ein falscher Beleg."""
    angebot: dict = {}
    assert nicht_im_angebot_aus_angebot(angebot, katalog, HEUTE) == {}


def test_nur_die_genannten_anbieter_werden_geprueft(katalog):
    """Telekom hat eine eigene Klick-Übersicht; diese Funktion rechnet nur für die
    übergebenen Anbieter ohne Übersicht, damit kein bestehender Mechanismus anders
    rechnet."""
    angebot = {"Telekom": {"apple-iphone-17-pro": {256}}}
    assert nicht_im_angebot_aus_angebot(angebot, katalog, HEUTE) == {}
    assert (
        nicht_im_angebot_aus_angebot(angebot, katalog, HEUTE, anbieter=("Telekom",))
        != {}
    )


def test_angebotene_speicher_steuert_den_beleg_ueber_denselben_lesezustand(katalog):
    """Gegenprobe über die echte Kette bis ``angebotene_speicher``
    (``klick_angebot.angebot_aus`` reicht ihr in der Pipeline genau die
    Anbieter mit ``GeraeteDB.lesezustand(...) == GELESEN`` als ``gelesen``
    weiter - dieselbe Definition wie bei den Abdeckungsalarmen, Clean Code
    7). Ein Anbieter, der dort NICHT als ganz gelesen gilt, kommt gar nicht
    erst in ``gelesen`` und bleibt darum ohne Beleg."""
    listungen = [
        _listung("Vodafone", "apple-iphone-17-pro"),
        _listung("Vodafone", "fairphone-6-plus", status="ausgelistet"),
    ]
    angebot_gelesen = angebotene_speicher(listungen, {"Vodafone"}, HEUTE)
    saetze = nicht_im_angebot_aus_angebot(angebot_gelesen, katalog, HEUTE)
    assert f"Vodafone{TRENNER}{FEHLENDES_GERAET}" in saetze

    angebot_nicht_gelesen = angebotene_speicher(listungen, set(), HEUTE)
    assert nicht_im_angebot_aus_angebot(angebot_nicht_gelesen, katalog, HEUTE) == {}
