"""Ohne Mindestlaufzeit (Bindung 0, congstar „monatlich kündbar“) zählt der Tarif 24
Vergleichsmonate (docs/geraete/gesamtkosten.md), auch bei weniger als 24 Raten und
ohne Gerät. Rot gegen den Stand vom 20.11.2026 vormittags: 12 Raten ergaben 12
Tarifmonate (365,99 statt 605,99 €), SIM-only die Lücke „Zeitraum“."""

import pytest

from telco_radar import versandkosten
from telco_radar.tco_model import Buendel, kosten_ueber, zeitraum


@pytest.fixture(autouse=True)
def _echter_versand(monkeypatch):
    monkeypatch.setattr(versandkosten, "_TABELLE", None)


def _congstar(**kw):
    basis = dict(
        anbieter="congstar",
        tarif_name="Allnet Flat M Flex",
        tarif_id="congstar:m-flex",
        tarif_id_guete="hoch",
        tarif_monatlich=20.0,
        tarif_bindung_monate=0,
        anschlusspreis=0.0,
        quelle_url="https://www.congstar.de/",
        abgerufen_am="2026-11-20",
    )
    basis.update(kw)
    return Buendel(**basis)


def test_bindung_null_mit_zwoelf_raten_zaehlt_24_tarifmonate():
    b = _congstar(
        sku_id="x-128", geraet_zuzahlung=1.0, geraet_monatsrate=10.0, laufzeit_monate=12
    )
    k = kosten_ueber(b)
    assert (k.monate, k.tarifmonate) == (24, 24)
    assert k.gesamt == round(1.0 + 24 * 20.0 + 12 * 10.0 + 4.99, 2) == 605.99


def test_bindung_null_mit_36_raten_bleibt_36_monate():
    b = _congstar(
        sku_id="x-128", geraet_zuzahlung=1.0, geraet_monatsrate=10.0, laufzeit_monate=36
    )
    assert zeitraum(b) == 36
    assert kosten_ueber(b).gesamt == round(1.0 + 24 * 20.0 + 36 * 10.0 + 4.99, 2)


def test_sim_only_ohne_mindestlaufzeit_zaehlt_24_vergleichsmonate():
    k = kosten_ueber(_congstar(sku_id=""))
    assert k.luecken == []
    assert (k.monate, k.gesamt) == (24, round(24 * 20.0 + 4.99, 2))
