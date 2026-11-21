"""Tarifwelt (Saturn/MediaMarkt): die Geraeterate ist eine Messung, keine Konstante.

Befund vom 21.11.2026 (regel11-2111): `tarifwelt_lauf` setzte
`geraet_monatsrate=0.0` fest und las `hardware.variants[0].monthlyPrice` nie.
Eine Rate in der Antwort fiele still weg, `kosten_ueber` liesse N x Rate aus.
Belegt mit der echten Antwort vom 08.11.2026 (iPhone 17 256 GB, Allnet 50,
Telekom-Netz, Rate 0) und ihrer Ableitung mit Rate 12,50 EUR (`_herkunft.json`).
"""

from __future__ import annotations

import json
from pathlib import Path

from test_geraete_adapter_tarifwelt import LEITER, fixture_hole

from telco_radar.collect.geraete import tarifwelt, tarifwelt_lauf
from telco_radar.tco_model import kosten_ueber

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "geraete"
ECHT = FIXTURES / "tarifwelt_mm_detail_iphone17_256_telekom_allnet50_20261108.json"
MIT_RATE = FIXTURES / (
    "tarifwelt_mm_detail_iphone17_256_telekom_allnet50_rate1250_abgeleitet"
    "_20261108.json"
)
TARIF = "6a3e48fce8ef8ed1c9722b21"
ANDERER_TARIF = "6a1e946e959a3938fb86c58d"


def _lauf(antwort_text: str | None = None, aendere=None):
    """`lies_modell` ueber die Fixtures; der Allnet-50-Tarif antwortet mit
    `antwort_text` oder der echten Antwort, auf die `aendere` angewandt wird."""
    hole, _ = fixture_hole()

    def neu(url, **kw):
        status, text = hole(url, **kw)
        if "/iphone-17?" in url and f"tfi={TARIF}" in url:
            if antwort_text is not None:
                return status, antwort_text
            if aendere is not None:
                daten = json.loads(text)
                aendere(daten)
                return status, json.dumps(daten)
        return status, text

    return tarifwelt_lauf.lies_modell(
        "apple-iphone-17", LEITER, neu, "2026-11-08", warte=lambda s: None
    )


def _buendel(lauf, tarif_id: str = TARIF):
    treffer = [
        b for b in lauf.buendel if b.tarif_id == f"mediamarkt_tarifwelt:{tarif_id}"
    ]
    assert len(treffer) <= 1
    return treffer[0] if treffer else None


def test_rate_aus_der_antwort_landet_im_buendel_und_in_den_gesamtkosten():
    lauf = _lauf(MIT_RATE.read_text(encoding="utf-8"))
    buendel = _buendel(lauf)
    assert buendel is not None, lauf.luecken
    assert buendel.geraet_monatsrate == 12.5
    assert buendel.laufzeit_monate == 24
    kosten = kosten_ueber(buendel)
    assert kosten.luecken == []
    assert kosten.posten["Geräteraten über 24 Monate"] == 300.0
    assert kosten.gesamt == 1485.69


def test_gegenprobe_rate_null_ist_ein_gelesener_wert_und_aendert_die_summe():
    satz = tarifwelt.lies_produktdetail(ECHT.read_text(encoding="utf-8"))
    assert satz is not None
    assert satz["geraet_monatsrate"] == 0.0
    buendel = _buendel(_lauf())
    assert buendel is not None
    assert buendel.geraet_monatsrate == 0.0
    kosten = kosten_ueber(buendel)
    assert kosten.posten["Geräteraten über 24 Monate"] == 0.0
    assert kosten.gesamt == 1185.69


def test_fehlende_rate_ist_eine_benannte_luecke_und_kein_buendel_mit_null():
    def ohne_rate(daten):
        del daten["hardware"]["variants"][0]["monthlyPrice"]

    satz_text = json.loads(ECHT.read_text(encoding="utf-8"))
    ohne_rate(satz_text)
    satz = tarifwelt.lies_produktdetail(json.dumps(satz_text))
    assert satz is not None
    assert "geraet_monatsrate" in satz
    assert satz["geraet_monatsrate"] is None

    lauf = _lauf(aendere=ohne_rate)
    assert _buendel(lauf) is None
    gruende = [g for v, g in lauf.luecken if "256 GB" in v and "Telekom" in v]
    assert any("geraet_monatsrate fehlt" in g for g in gruende), lauf.luecken
    assert _buendel(lauf, ANDERER_TARIF) is not None


def test_unlesbare_oder_negative_rate_ist_keine_zahl_und_wird_luecke():
    for roh, grund in (
        ("12,50", "geraet_monatsrate fehlt"),
        (True, "geraet_monatsrate fehlt"),
        (-1, "Geraeterate -1.0 negativ"),
    ):

        def setze(daten, wert=roh):
            daten["hardware"]["variants"][0]["monthlyPrice"] = wert

        lauf = _lauf(aendere=setze)
        assert _buendel(lauf) is None, roh
        assert any(grund in g for _, g in lauf.luecken), (roh, lauf.luecken)
