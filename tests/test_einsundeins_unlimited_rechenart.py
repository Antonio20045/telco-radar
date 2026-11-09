"""1&1 Unlimited XL rechnet wie jede andere 1&1-Zeile im 24-Monats-Export.

Am Original gemessen (09.11.2026, Plan 24 + 12, iPhone 18 Pro 256 GB):
77,99 EUR im Monat, Bereitstellung 39,90 EUR, Ablöse 460 EUR. Die Rechnung
(24 x Bündelbetrag + Anschluss + Ablöse) ist die der übrigen 1&1-Tarife; die
Ablöse kommt immer aus der Messung des Geräts, nie aus einer Pauschale.
"""

from __future__ import annotations

import pytest

from telco_radar.report.geraete_laufzeit import raten_text
from telco_radar.tco_kosten import kosten_ueber
from telco_radar.tco_model import Buendel


def _buendel(monat: float, abloese: float, tarif: str) -> Buendel:
    return Buendel(
        sku_id="apple-iphone-18-pro-256gb-polar",
        anbieter="1&1",
        tarif_name=tarif,
        tarif_id="11:" + tarif.lower().replace("&", "-").replace(" ", "-"),
        buendel_monatlich=monat,
        geraet_zuzahlung=abloese,
        laufzeit_monate=36,
        anschlusspreis=39.90,
        abgerufen_am="2026-11-07",
    )


def test_iphone_18_pro_256_unlimited_xl_kostet_2371_66():
    k = kosten_ueber(_buendel(77.99, 460.0, "1&1 Unlimited XL"), 24)
    assert k.gesamt == pytest.approx(2371.66)
    assert pytest.approx(2371.66) == 24 * 77.99 + 39.90 + 460.0


def test_dieselbe_rechenart_wie_die_uebrigen_1und1_tarife():
    for tarif, monat, summe in [
        ("1&1 Unlimited on demand L", 67.99, 2131.66),
        ("1&1 All-Net-Flat M", 57.99, 1891.66),
    ]:
        assert kosten_ueber(_buendel(monat, 460.0, tarif), 24).gesamt == pytest.approx(
            summe
        )


def test_die_abloese_kommt_aus_der_messung_je_geraet_nicht_pauschal():
    """S26 Ultra 256: 1&1 nennt 400 EUR auf der Laufzeitseite und 460 EUR im
    Warenkorb. Der Export führt, was für das Gerät gemessen wurde (400)."""
    k400 = kosten_ueber(_buendel(77.99, 400.0, "1&1 Unlimited XL"), 24)
    k460 = kosten_ueber(_buendel(77.99, 460.0, "1&1 Unlimited XL"), 24)
    assert k400.gesamt == pytest.approx(2311.66)
    assert k460.gesamt - k400.gesamt == pytest.approx(60.0)


def test_das_etikett_ist_24_monate_plus_abloese():
    karte = {"raten_laufzeit": 36, "buendel_monatlich": 77.99}
    assert raten_text(karte) == "24 Monate + Ablöse"
