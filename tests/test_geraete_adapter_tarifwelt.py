"""Tarifwelt-Adapter (MediaMarkt/Saturn): Parser gegen echte Fixtures.

Die vier Fixtures (tests/fixtures/geraete/tarifwelt_mm_*.json, Herkunft in
_herkunft.json) sind echte Abrufe vom 08.11.2026 - keine erfundenen
Werte. Der Adapter ist `aktiv: false` (config/geraete_quellen.yaml): dieser
Test belegt, dass der Parser korrekt ist, nicht, dass die Quelle schon
crawlt.
"""

from pathlib import Path

from telco_radar.collect.geraete import tarifwelt

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "geraete"
_URL = "https://tarife-api2.mediamarkt.de/v1/productdetail/x/tariff"


def _tarifliste():
    text = (_FIXTURES / "tarifwelt_mm_tarifliste_iphone17_20261108.json").read_text()
    return tarifwelt.lies_tarifliste(text, _URL)


def test_lies_tarifliste_liefert_alle_25_rohen_eintraege():
    saetze = _tarifliste()
    assert len(saetze) == 25


def test_lies_tarifliste_erkennt_netz_je_satz():
    saetze = _tarifliste()
    netze = {s["netz"] for s in saetze}
    assert netze == {"o2", "freenet - Telekom", "freenet - Vodafone"}


def test_lies_tarifliste_markiert_doppelkarte_statt_zu_verwerfen():
    saetze = _tarifliste()
    doppel = [s for s in saetze if s["doppelkarte"]]
    assert len(doppel) == 1
    assert doppel[0]["netz"] == "o2"
    assert doppel[0]["datenvolumen_gb"] == 150.0


def test_ohne_doppelkarte_verwirft_genau_den_einen_satz():
    saetze = tarifwelt.ohne_doppelkarte(_tarifliste())
    assert len(saetze) == 24
    assert all(not s["doppelkarte"] for s in saetze)


def test_lies_tarifliste_konkreter_telekom_satz():
    saetze = _tarifliste()
    telekom_m = next(s for s in saetze if s["tarif_id"] == "680b5e98b1556e63a970b092")
    assert telekom_m["netz"] == "freenet - Telekom"
    assert telekom_m["datenvolumen_gb"] == 50.0
    assert telekom_m["grundgebuehr"] == 49.95
    assert telekom_m["einmalpreis_ab"] == 109.99
    assert telekom_m["doppelkarte"] is False
    assert telekom_m["quelle"] == "mediamarkt_tarifwelt"
    assert telekom_m["url"] == _URL


def test_lies_tarifliste_unlesbarer_text_ist_leer_statt_fehler():
    assert tarifwelt.lies_tarifliste("kein json", _URL) == []
    assert tarifwelt.lies_tarifliste("", _URL) == []
    assert tarifwelt.lies_tarifliste('{"keine": "liste"}', _URL) == []


def test_lies_liefert_keine_geraeteliste():
    assert tarifwelt.lies("irrelevant", _URL) == []


def test_waehle_je_band_naechstes_volumen_bei_gleichstand_das_groessere():
    saetze = [
        {"tarif_id": "a", "datenvolumen_gb": 40.0, "grundgebuehr": 30.0},
        {"tarif_id": "b", "datenvolumen_gb": 60.0, "grundgebuehr": 20.0},
        {"tarif_id": "c", "datenvolumen_gb": 10.0, "grundgebuehr": 15.0},
    ]
    gewaehlt = tarifwelt.waehle_je_band(saetze, (("mittel", 50.0),))
    assert gewaehlt["mittel"]["tarif_id"] == "b"


def test_waehle_je_band_gleich_nah_entscheidet_der_preis():
    saetze = [
        {"tarif_id": "teuer", "datenvolumen_gb": 40.0, "grundgebuehr": 50.0},
        {"tarif_id": "billig", "datenvolumen_gb": 60.0, "grundgebuehr": 20.0},
    ]
    gewaehlt = tarifwelt.waehle_je_band(saetze, (("mittel", 50.0),))
    assert gewaehlt["mittel"]["tarif_id"] == "billig"


def test_waehle_je_band_ohne_treffer_bleibt_band_aus():
    gewaehlt = tarifwelt.waehle_je_band([], (("mittel", 50.0),))
    assert gewaehlt == {}
