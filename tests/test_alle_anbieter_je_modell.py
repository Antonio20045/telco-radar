"""Jeder große Anbieter steht bei jedem Gerät in der Bündelliste (Antonio 10.10.2026).

„Bietet das Gerät nicht an“ steht nur mit dem Beleg einer ganz gelesenen
Übersicht (`klick_erfassung`); ohne ihn heißt ein Anbieter ohne Bündel „Noch
nicht erfasst“. Eine Bündelzeile desselben Anbieters in derselben Ansicht
verdrängt seine Fehlzeile.
"""

from __future__ import annotations

from telco_radar.analyze.klick_erfassung import SATZ_NICHT_IM_ANGEBOT
from telco_radar.report.geraete_luecken import (
    NICHT_IM_ANGEBOT,
    NOCH_NICHT_ERFASST,
    fehlzeilen,
    ohne_tafelzeile,
    tafelzeilen,
)


def _luecke(anbieter: str, grund: str = "gar-kein-buendel", **mehr) -> dict:
    return {
        "anbieter": anbieter,
        "grund": grund,
        "monate": None,
        "alternativ": [],
        "gesperrt": [],
        "laufzeit": 24,
        "andere_laufzeiten": [],
        **mehr,
    }


def test_nicht_im_angebot_nur_mit_ganz_gelesener_uebersicht():
    erfassung = {
        "1&1": SATZ_NICHT_IM_ANGEBOT.format(anbieter="1&1", datum="10.10.2026"),
        "Telekom": "Telekom nicht erfasst: Seite sperrt automatisches Lesen "
        "(HTTP 202, 10.10.2026)",
    }
    zeilen = fehlzeilen(
        [_luecke("Telekom"), _luecke("1&1"), _luecke("congstar")], {}, 24, erfassung
    )
    kurz = {z["anbieter"]: z["kurz"] for z in zeilen}
    assert kurz == {
        "Telekom": NOCH_NICHT_ERFASST,
        "1&1": NICHT_IM_ANGEBOT,
        "congstar": NOCH_NICHT_ERFASST,
    }
    satz = {z["anbieter"]: z["satz"] for z in zeilen}
    assert satz["1&1"] == erfassung["1&1"]
    assert satz["Telekom"] == erfassung["Telekom"]
    assert "congstar" in satz["congstar"]


def test_gegenprobe_ein_sperrsatz_ist_kein_nicht_im_angebot():
    erfassung = {"o2": "o2 nicht erfasst: Lesen gestört (10.10.2026)"}
    (zeile,) = fehlzeilen([_luecke("o2")], {}, 24, erfassung)
    assert zeile["kurz"] == NOCH_NICHT_ERFASST


def test_alternative_baender_stehen_mit_betrag_an_der_zeile():
    lu = _luecke(
        "o2", "anderes-band", alternativ=[{"band": "l", "tco": 1234.5, "monate": 24}]
    )
    (zeile,) = fehlzeilen([lu], {"l": {"label": "L"}}, 24)
    assert zeile["kurz"] == "Nur in anderen Bändern: L 1.234,50 €"


def _paar(band: str, laufzeit: int, fehlen: list) -> dict:
    return {"modell": "m", "band": band, "laufzeit": laufzeit, "fehlen": fehlen}


def test_unter_alle_steht_nur_wer_in_keiner_laufzeit_eine_zeile_hat():
    telekom = fehlzeilen([_luecke("Telekom")], {}, 24)
    o2_nur_24 = fehlzeilen([_luecke("o2", "anderes-band")], {}, 24)
    paare = [
        _paar("m", 12, telekom),
        _paar("m", 24, telekom + o2_nur_24),
        _paar("m", 36, telekom),
    ]
    zeilen = tafelzeilen(paare)["m"]
    alle = [z for z in zeilen if z["laufzeit"] == "alle"]
    assert [z["anbieter"] for z in alle] == ["Telekom"]
    assert {(z["anbieter"], z["laufzeit"]) for z in zeilen} >= {
        ("Telekom", "12"),
        ("o2", "24"),
    }
    assert all(z["anb_farbe"] for z in zeilen)


def test_eine_buendelzeile_derselben_ansicht_verdraengt_die_fehlzeile():
    fehlen = [
        {"anbieter": "Telekom", "band": "m", "laufzeit": "24"},
        {"anbieter": "Telekom", "band": "m", "laufzeit": "36"},
        {"anbieter": "Telekom", "band": "m", "laufzeit": "alle"},
    ]
    tafel = [{"anbieter": "Telekom", "band": "m", "laufzeit_sichtbar": "36"}]
    rest = ohne_tafelzeile(fehlen, tafel)
    assert [z["laufzeit"] for z in rest] == ["24"]
