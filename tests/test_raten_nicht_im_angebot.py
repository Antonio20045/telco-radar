"""o2 und congstar bieten nur 24 und 36 Raten an (Preisprüfung 11.10.2026), 1&1 nur
„24 Monate + Ablöse“ (Abgleich der Live-Seite 11.10.2026: 77 Modelle mit „1&1 Mit 12
Raten nicht erfasst“)."""

from __future__ import annotations

import pytest

from telco_radar.report.geraete_luecken import fehlzeilen


def _luecke(anbieter: str, laufzeit: int) -> dict:
    return {
        "anbieter": anbieter,
        "grund": "nicht-erfasst",
        "monate": None,
        "alternativ": [],
        "gesperrt": [],
        "laufzeit": laufzeit,
        "andere_laufzeiten": [24, 36],
    }


@pytest.mark.parametrize("anbieter", ["o2", "congstar", "1&1"])
def test_zwoelf_raten_bei_o2_und_congstar_sind_nicht_im_angebot(anbieter):
    (zeile,) = fehlzeilen([_luecke(anbieter, 12)], {})
    assert zeile["kurz"] == "Mit 12 Raten nicht im Angebot"


@pytest.mark.parametrize(("anbieter", "laufzeit"), [("Telekom", 12), ("o2", 24)])
def test_gegenprobe_angebotene_laufzeit_bleibt_nicht_erfasst(anbieter, laufzeit):
    (zeile,) = fehlzeilen([_luecke(anbieter, laufzeit)], {})
    assert (
        zeile["kurz"] == f"Mit {laufzeit} Raten nicht erfasst (24 und 36 Raten erfasst)"
    )


def test_speicher_nicht_im_angebot_steht_kurz_an_der_zeile():
    from telco_radar.analyze.klick_erfassung import SATZ_SPEICHER_ANGEBOT

    satz = SATZ_SPEICHER_ANGEBOT.format(
        anbieter="o2", speicher="256 GB", datum="11.10.2026"
    )
    luecke = {**_luecke("o2", 24), "grund": "gar-kein-buendel"}
    (zeile,) = fehlzeilen([luecke], {}, erfassung={"o2": satz})
    assert (zeile["kurz"], zeile["satz"]) == ("Nur mit 256 GB im Angebot", satz)
