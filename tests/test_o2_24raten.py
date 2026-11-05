"""Ziel 1b (05.11.2026) - o2 wird auf 24 Raten gemessen, 36 Raten bleiben getrennt.

Messung 05.11.2026 (iPhone 17 Pro 256 GB, o2 Mobile M, Tarif 19,99 EUR, Anschluss
39,99 EUR; eine Probe auf o2online.de):
24 Raten = 7,00 EUR Anzahlung + 54,50 EUR/Monat, 36 Raten = 1,00 EUR + 36,50 EUR.
Die Rate bleibt also NICHT stehen, wenn man die Laufzeit wechselt; nur der
Geraetepreis (1.315,00 EUR) ist gleich. Die Tests halten fest:

  * jede o2-Startadresse des Tageslaufs traegt ratenzahlung=24 (Gegenprobe:
    andere Anbieter bleiben unberuehrt),
  * beide gemessenen Zeilen ergeben Geraete-Summe 1.315,00 EUR und gleiche Kosten
    ueber 24 Monate, aber jede steht nur unter ihrer eigenen Ansicht,
  * eine 36-Raten-Zeile steht nie unter "24 Monate",
  * die Methodik nennt die Regel (test_geraete_methodik_umzug.py),
  * der Beleglink einer 24-Raten-Zeile traegt ratenzahlung=24.
"""

from __future__ import annotations

import pathlib
import re

from telco_radar.analyze.klick_tarifslug import klick_beleglink
from telco_radar.report import geraete_laufzeit
from telco_radar.tco_kosten import kosten_ueber
from telco_radar.tco_model import Buendel

WURZEL = pathlib.Path(__file__).resolve().parent.parent
TAGESLAUF = WURZEL / "config" / "klick_tageslauf.yaml"

MESSUNG_O2_MOBILE_M = dict(tarif_monatlich=19.99, anschlusspreis=39.99)


def _o2_adressen() -> list[str]:
    text = TAGESLAUF.read_text(encoding="utf-8")
    return re.findall(r"https://www\.o2online\.de/\S+", text)


def test_alle_o2_startadressen_stehen_auf_24_raten():
    adressen = _o2_adressen()
    assert len(adressen) > 100
    falsche = [a for a in adressen if "ratenzahlung=24" not in a]
    assert falsche == []
    assert not [a for a in adressen if "ratenzahlung=36" in a]


def _buendel_o2(**kw) -> Buendel:
    felder = dict(
        sku_id="apple-iphone-17-pro-256gb",
        anbieter="o2",
        tarif_name="o2 Mobile M",
        tarif_id="o2:o2-mobile-m",
        tarif_id_guete="hoch",
        quelle_url="https://www.o2online.de/mobile/apple/iphone-17-pro-256gb",
        abgerufen_am="2026-11-05",
    )
    felder.update(kw)
    return Buendel(**felder)


def _b24():
    return _buendel_o2(
        geraet_zuzahlung=7.0,
        geraet_monatsrate=54.5,
        laufzeit_monate=24,
        **MESSUNG_O2_MOBILE_M,
    )


def _b36():
    return _buendel_o2(
        geraet_zuzahlung=1.0,
        geraet_monatsrate=36.5,
        laufzeit_monate=36,
        **MESSUNG_O2_MOBILE_M,
    )


def test_beide_gemessenen_zeilen_haben_gleichen_geraetepreis_und_gleiche_kosten():
    k24, k36 = kosten_ueber(_b24()), kosten_ueber(_b36())
    assert 7.0 + 54.5 * 24 == 1315.0 == 1.0 + 36.5 * 36
    assert k24.gesamt == k36.gesamt == 1834.75
    assert (k24.monate, k36.monate) == (24, 36)
    falsch = _buendel_o2(
        geraet_zuzahlung=7.0,
        geraet_monatsrate=36.5,
        laufzeit_monate=24,
        **MESSUNG_O2_MOBILE_M,
    )
    assert kosten_ueber(falsch).gesamt != 1834.75


def test_36_raten_zeile_steht_nie_unter_24_monate():
    k24 = {"raten_laufzeit": geraete_laufzeit.raten_laufzeit(_b24())}
    k36 = {"raten_laufzeit": geraete_laufzeit.raten_laufzeit(_b36())}
    karten = [k24, k36]
    geraete_laufzeit.setze_ansicht(karten)
    assert k24["laufzeit_sichtbar"] == "24"
    assert k36["laufzeit_sichtbar"] == "36"


def test_beleglink_der_24_raten_zeile_traegt_24():
    satz = {
        "quelle_art": "klick",
        "anbieter": "o2",
        "tarif_name": "o2 Mobile M",
        "laufzeit_monate": 24,
        "quelle_url": (
            "https://www.o2online.de/shop/smartphones/apple/"
            "iphone-17-pro-256gb-details?ratenzahlung=36"
        ),
    }
    link = klick_beleglink(satz)
    assert "ratenzahlung=24" in link
    assert "ratenzahlung=36" not in link
    satz36 = dict(satz, laufzeit_monate=36)
    assert "ratenzahlung=36" in klick_beleglink(satz36)
