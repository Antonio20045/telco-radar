"""Ein Terabyte heißt in der Tarifwelt 1000 GB, im Katalog (SKU, Wächter,
Speicherprüfung) 1024 GB. Sonst entstünde eine eigene Speicherstufe, die kein
anderer Anbieter führt (Wächter `speicher_fehlt` bei o2), und die SKU wäre mit
keinem Gerät der Netzbetreiber vergleichbar.
"""

from __future__ import annotations

import json

from test_geraete_adapter_tarifwelt import LEITER, fixture_hole

from telco_radar.collect.geraete import tarifwelt_lauf


def _hole_mit_speicher(api_gb: int):
    hole, aufrufe = fixture_hole()

    def umgestellt(url, **kw):
        status, text = hole(url, **kw)
        if "/tariff?" in url:
            return status, text
        if "?" not in url:
            daten = json.loads(text)
            for v in daten["hardware"]["variants"] + daten["hardware"]["variantFilter"]:
                v["storage"] = api_gb
            return status, json.dumps(daten)
        return status, text.replace("256 GB", f"{api_gb} GB")

    return umgestellt, aufrufe


def test_ein_terabyte_der_tarifwelt_ist_im_sku_1024_gb():
    hole, aufrufe = _hole_mit_speicher(1000)
    lauf = tarifwelt_lauf.lies_modell(
        "apple-iphone-17", LEITER, hole, "2026-11-08", warte=lambda s: None
    )
    assert lauf.buendel, lauf.luecken
    assert all("-1024gb-" in b.sku_id for b in lauf.buendel)
    assert not any("1000gb" in b.sku_id for b in lauf.buendel)
    assert any("storage=1000" in u for u in aufrufe)


def test_gewoehnliche_speicherstufen_bleiben_unveraendert():
    hole, _ = _hole_mit_speicher(256)
    lauf = tarifwelt_lauf.lies_modell(
        "apple-iphone-17", LEITER, hole, "2026-11-08", warte=lambda s: None
    )
    assert lauf.buendel
    assert all("-256gb-" in b.sku_id for b in lauf.buendel)
