"""Tarifwelt-Adapter (MediaMarkt/Saturn): Parser gegen echte Fixtures.

Die vier Fixtures (tests/fixtures/geraete/tarifwelt_mm_*.json, Herkunft in
_herkunft.json) sind echte Abrufe vom 08.11.2026 - keine erfundenen
Werte. Der Adapter ist `aktiv: false` (config/geraete_quellen.yaml): dieser
Test belegt, dass der Parser korrekt ist, nicht, dass die Quelle schon
crawlt.
"""

import json
from pathlib import Path

from telco_radar.collect.geraete import tarifwelt
from telco_radar.tco_model import Buendel, kosten_ueber

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "geraete"
_URL = "https://tarife-api2.mediamarkt.de/v1/productdetail/x/tariff"


def _tarifliste():
    text = (_FIXTURES / "tarifwelt_mm_tarifliste_iphone17_20261108.json").read_text()
    return tarifwelt.lies_tarifliste(text, _URL)


def _produktdetail(dateiname: str) -> dict:
    text = (_FIXTURES / dateiname).read_text()
    satz = tarifwelt.lies_produktdetail(text, _URL)
    assert satz is not None, dateiname
    return satz


def _buendel_aus(satz: dict) -> Buendel:
    anbieter = tarifwelt.anbieter_zeile(satz["netz"])
    assert anbieter is not None, satz
    return Buendel(
        sku_id="test-sku",
        anbieter=anbieter,
        tarif_name=satz["tarif_name"] or satz["tarif_id"],
        tarif_id=satz["tarif_id"],
        tarif_monatlich=satz["grundgebuehr"],
        geraet_zuzahlung=satz["geraet_zuzahlung"],
        geraet_monatsrate=0.0,
        laufzeit_monate=satz["laufzeit_monate"],
        anschlusspreis=satz["anschlusspreis"],
        quelle_url=satz["url"],
    )


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


def test_tarife_mit_band_behaelt_alle_tarife_eines_bandes_nach_volumen_und_preis():
    saetze = [
        {"tarif_id": "a", "datenvolumen_gb": 40.0, "grundgebuehr": 30.0},
        {"tarif_id": "b", "datenvolumen_gb": 60.0, "grundgebuehr": 20.0},
        {"tarif_id": "c", "datenvolumen_gb": 40.0, "grundgebuehr": 25.0},
    ]
    gewaehlt = tarifwelt.tarife_mit_band(saetze, (("mittel", 50.0),))
    assert [s["tarif_id"] for s in gewaehlt] == ["c", "a", "b"]


def test_tarife_mit_band_nimmt_jede_tarif_id_nur_einmal():
    saetze = [
        {"tarif_id": "a", "datenvolumen_gb": 40.0, "grundgebuehr": 30.0},
        {"tarif_id": "a", "datenvolumen_gb": 40.0, "grundgebuehr": 30.0},
    ]
    assert len(tarifwelt.tarife_mit_band(saetze, (("mittel", 50.0),))) == 1


def test_tarife_mit_band_ohne_treffer_oder_ohne_volumen_bleibt_leer():
    assert tarifwelt.tarife_mit_band([], (("mittel", 50.0),)) == []
    ohne = [{"tarif_id": "x", "datenvolumen_gb": None, "grundgebuehr": 9.0}]
    assert tarifwelt.tarife_mit_band(ohne, (("mittel", 50.0),)) == []


def test_lies_produktdetail_centgenau_iphone17_telekom_magenta_m():
    satz = _produktdetail(
        "tarifwelt_mm_productdetail_iphone17_telekom_magenta_m_20261108.json"
    )
    assert satz["netz"] == "freenet - Telekom"
    assert satz["geraet_zuzahlung"] == 109.99
    assert satz["anschlusspreis"] == 39.99
    assert satz["grundgebuehr"] == 49.95
    assert satz["laufzeit_monate"] == 24
    assert satz["doppelkarte"] is False
    tco = kosten_ueber(_buendel_aus(satz))
    assert tco.gesamt == 1354.73


def test_lies_produktdetail_centgenau_galaxys26_standard():
    satz = _produktdetail("tarifwelt_mm_productdetail_galaxys26_standard_20261108.json")
    assert satz["netz"] == "freenet - Telekom"
    assert satz["geraet_zuzahlung"] == 29.0
    assert satz["anschlusspreis"] == 39.99
    assert satz["grundgebuehr"] == 29.99
    tco = kosten_ueber(_buendel_aus(satz))
    assert tco.gesamt == 794.70


def test_lies_produktdetail_o2_doppelkarte_zuzahlung_centgenau():
    satz = _produktdetail(
        "tarifwelt_mm_productdetail_iphone17_o2doppelkarte_20261108.json"
    )
    assert satz["netz"] == "o2"
    assert satz["doppelkarte"] is True
    assert satz["geraet_zuzahlung"] == 69.0
    assert satz["anschlusspreis"] == 39.99
    assert satz["grundgebuehr"] == 39.98


def test_lies_produktdetail_unlesbarer_text_ist_none_statt_fehler():
    assert tarifwelt.lies_produktdetail("kein json", _URL) is None
    assert tarifwelt.lies_produktdetail("", _URL) is None
    assert tarifwelt.lies_produktdetail('{"keine": "tariff"}', _URL) is None


def test_anbieter_zeile_bekannte_netze():
    assert tarifwelt.anbieter_zeile("o2") == "Saturn/MediaMarkt · o2-Netz"
    assert (
        tarifwelt.anbieter_zeile("freenet - Telekom")
        == "Saturn/MediaMarkt · Telekom-Netz"
    )
    assert (
        tarifwelt.anbieter_zeile("freenet - Vodafone")
        == "Saturn/MediaMarkt · Vodafone-Netz"
    )


def test_anbieter_zeile_unbekanntes_netz_ist_luecke():
    assert tarifwelt.anbieter_zeile("irgendwas") is None
    assert tarifwelt.anbieter_zeile(None) is None


def test_versandkosten_centgenau_gegen_die_fixtures():
    """Der Versand (5,95 EUR) steht zentral in versandkosten.yaml (Clean Code
    1), nicht in diesem Parser - hier die Gegenprobe gegen dieselben zwei
    Netze, die die Fixtures oben belegen, plus das Vodafone-Netz (Messung
    08.11.2026 an der Preisuebersicht)."""
    from telco_radar import versandkosten

    vorher = versandkosten._TABELLE
    versandkosten._TABELLE = None
    try:
        assert versandkosten.versand_fuer("Saturn/MediaMarkt · o2-Netz").betrag == 5.95
        assert (
            versandkosten.versand_fuer("Saturn/MediaMarkt · Telekom-Netz").betrag
            == 5.95
        )
        assert (
            versandkosten.versand_fuer("Saturn/MediaMarkt · Vodafone-Netz").betrag
            == 5.95
        )
    finally:
        versandkosten._TABELLE = vorher


LEITER = (
    ("xs", 15.0),
    ("s", 30.0),
    ("m", 60.0),
    ("l", 120.0),
    ("xl", float("inf")),
)


def test_unbegrenzt_ist_inf_nicht_luecke():
    liste = _tarifliste()
    unbegrenzt = [s for s in liste if "unlimited" in (s["tarif_name"] or "").lower()]
    assert unbegrenzt
    assert all(s["datenvolumen_gb"] == float("inf") for s in unbegrenzt)


def test_band_regel_ist_dieselbe_wie_im_bericht():
    """Sammeln und Bericht teilen EINE Regel (`band_regel.stufe_fuer`)."""
    from telco_radar.band_regel import stufe_fuer
    from telco_radar.report import geraete_tco_band as band

    leiter = tuple(
        band.Stufe(key=k, label=k, gb=g, tarif_id=k, name=k, grundgebuehr=1.0)
        for k, g in LEITER
    )
    for gb in (5, 15, 22.5, 45, 50, 90, 100, 160, 200, float("inf"), None):
        assert band.band_von_gb(gb, leiter) == stufe_fuer(gb, LEITER), gb


def test_alle_vergleichbaren_tarife_je_netz_ohne_doppelkarte_aktion_young():
    from telco_radar.collect.geraete import tarifwelt_lauf

    liste = _tarifliste()
    zusatz = [
        {
            "tarif_id": "aktion",
            "tarif_name": "Allnet Flat 50GB Aktion",
            "netz": "freenet - Telekom",
            "datenvolumen_gb": 50.0,
            "grundgebuehr": 9.99,
            "doppelkarte": False,
        },
        {
            "tarif_id": "young",
            "tarif_name": "Magenta Mobil M Young 5G",
            "netz": "freenet - Telekom",
            "datenvolumen_gb": 50.0,
            "grundgebuehr": 9.98,
            "doppelkarte": False,
        },
    ]
    gewaehlt = tarifwelt_lauf.vergleichbare_tarife(liste + zusatz, LEITER)
    ids = [s["tarif_id"] for s in gewaehlt]
    assert len(ids) == len(set(ids))
    assert "aktion" not in ids and "young" not in ids
    assert not any(s["doppelkarte"] for s in gewaehlt)
    telekom = [s for s in gewaehlt if s["netz"] == "freenet - Telekom"]
    assert len(telekom) > 3
    assert {29.99, 44.99} <= {s["grundgebuehr"] for s in telekom}
    assert "magenta-mobil-xl-5g" in {s["tarif_name"] for s in telekom}
    assert {s["netz"] for s in gewaehlt} == {
        "o2",
        "freenet - Telekom",
        "freenet - Vodafone",
    }
    vodafone = [s for s in gewaehlt if s["netz"] == "freenet - Vodafone"]
    assert 120.0 in {s["datenvolumen_gb"] for s in vodafone}


def test_tarif_ohne_band_der_leiter_bleibt_draussen_statt_geraten():
    from telco_radar.collect.geraete import tarifwelt_lauf

    nur_unbegrenzt = [
        {
            "tarif_id": "u",
            "tarif_name": "Unlimited",
            "netz": "o2",
            "datenvolumen_gb": float("inf"),
            "grundgebuehr": 30.0,
            "doppelkarte": False,
            "preiswechsel": False,
        }
    ]
    assert tarifwelt_lauf.vergleichbare_tarife(nur_unbegrenzt, LEITER[:4]) == []
    assert len(tarifwelt_lauf.vergleichbare_tarife(nur_unbegrenzt, LEITER)) == 1


class _Antwort(tuple):
    schutz = False

    def __new__(cls, status, text, schutz=False):
        self = super().__new__(cls, (status, text))
        self.schutz = schutz
        return self


def test_schutzantwort_bricht_den_ganzen_lauf_ab_ohne_wiederholung():
    import pytest

    from telco_radar.collect.geraete import tarifwelt_lauf
    from telco_radar.collect.geraete.basis import GeraeteAbrufFehler

    aufrufe: list[tuple[str, dict]] = []

    def hole(url, **kw):
        aufrufe.append((url, kw))
        return _Antwort(403, "Forbidden")

    with pytest.raises(GeraeteAbrufFehler) as fehler:
        tarifwelt_lauf.lies_modell(
            "apple-iphone-17", LEITER, hole, "2026-11-08", warte=lambda s: None
        )
    assert fehler.value.schutz is True
    assert len(aufrufe) == 1
    assert aufrufe[0][1]["einmalig"] is True
    assert aufrufe[0][1]["user_agent"] == tarifwelt_lauf.KENNUNG


def test_challenge_mit_schutzmerkmal_bricht_ebenfalls_ab():
    import pytest

    from telco_radar.collect.geraete import tarifwelt_lauf
    from telco_radar.collect.geraete.basis import GeraeteAbrufFehler

    zaehler = []

    def hole(url, **kw):
        zaehler.append(url)
        return _Antwort(503, "challenge", schutz=True)

    with pytest.raises(GeraeteAbrufFehler) as fehler:
        tarifwelt_lauf.lies_modell(
            "apple-iphone-17", LEITER, hole, "2026-11-08", warte=lambda s: None
        )
    assert fehler.value.schutz is True
    assert len(zaehler) == 1


def test_404_auf_einer_variante_ist_nur_diese_luecke():
    from telco_radar.collect.geraete import tarifwelt_lauf

    uebersicht = (_FIXTURES / _OFFERGRUPPE_IPHONE17).read_text()
    liste = (_FIXTURES / "tarifwelt_mm_tarifliste_iphone17_20261108.json").read_text()

    def hole(url, **kw):
        if "/tariff?" in url:
            return _Antwort(200, liste)
        if "tfi=" in url:
            return _Antwort(404, "nicht gefunden")
        return _Antwort(200, uebersicht)

    lauf = tarifwelt_lauf.lies_modell(
        "apple-iphone-17", LEITER, hole, "2026-11-08", warte=lambda s: None
    )
    assert lauf.buendel == []
    assert lauf.luecken and all("HTTP 404" in grund for _, grund in lauf.luecken)


_OFFERGRUPPE_IPHONE17 = (
    "tarifwelt_mm_productdetail_iphone17_o2doppelkarte_20261108.json"
)


_F = "tarifwelt_mm_"
_SCHALE = json.dumps({"offerId": "", "tariff": {"_id": ""}, "hardware": None})


def fixture_hole():
    """Antwortet wie die Schnittstelle, aus den gespeicherten Abrufen vom
    08.11.2026: Uebersicht, Tarifliste, zwei Tarife je Geraet. Jeder andere
    Tarif bekommt die leere Huelle, die die Schnittstelle fuer ein Geraet
    gibt, fuer das der Tarif nicht waehlbar ist."""
    detail = {
        (
            "iphone-17",
            "6a3e48fce8ef8ed1c9722b21",
        ): "detail_iphone17_256_telekom_allnet50",
        ("iphone-17", "6a1e946e959a3938fb86c58d"): "detail_iphone17_256_o2_unlimited_m",
        (
            "galaxy-s26",
            "6a3e48fce8ef8ed1c9722b21",
        ): "detail_galaxys26_256_telekom_allnet50",
        (
            "galaxy-s26",
            "694953fa6ea7f51cc6762f38",
        ): "detail_galaxys26_256_o2_mobile_m_promo",
    }
    uebersicht = {
        "iphone-17": "productdetail_iphone17_o2doppelkarte",
        "galaxy-s26": "productdetail_galaxys26_standard",
    }
    liste = {
        "68c2d649b31debf7ff0c86c4": "tarifliste_iphone17",
        "66868692b87d976eef0a0b7b": "tarifliste_galaxys26",
    }
    aufrufe: list[str] = []

    def lies_datei(name: str) -> str:
        return (_FIXTURES / f"{_F}{name}_20261108.json").read_text()

    def hole(url, **kw):
        aufrufe.append(url)
        rest = url.split("/v1/productdetail/")[1]
        if "/tariff?" in rest:
            return _Antwort(200, lies_datei(liste[rest.split("/")[0]]))
        if "?" not in rest:
            return _Antwort(200, lies_datei(uebersicht[rest]))
        slug, abfrage = rest.split("?")
        tfi = dict(p.split("=") for p in abfrage.split("&"))["tfi"]
        name = detail.get((slug, tfi))
        return _Antwort(200, lies_datei(name) if name else _SCHALE)

    return hole, aufrufe


def test_lauf_zwei_geraete_zwei_tarife_centgenau_gegen_die_fixtures():
    from telco_radar.collect.geraete import tarifwelt_lauf

    hole, aufrufe = fixture_hole()
    erwartet = {
        ("apple-iphone-17", "Saturn/MediaMarkt · Telekom-Netz"): (
            419.99,
            29.99,
            1185.69,
        ),
        ("apple-iphone-17", "Saturn/MediaMarkt · o2-Netz"): (369.99, 29.99, 1135.69),
        ("samsung-galaxy-s26", "Saturn/MediaMarkt · Telekom-Netz"): (
            159.99,
            29.99,
            925.69,
        ),
        ("samsung-galaxy-s26", "Saturn/MediaMarkt · o2-Netz"): (379.99, 19.99, 905.69),
    }
    gefunden = {}
    for modell in ("apple-iphone-17", "samsung-galaxy-s26"):
        lauf = tarifwelt_lauf.lies_modell(
            modell, LEITER, hole, "2026-11-08", warte=lambda s: None
        )
        for b in lauf.buendel:
            assert b.laufzeit_monate == 24
            assert b.anschlusspreis == 39.99
            assert b.sku_id.startswith(modell)
            gefunden[(modell, b.anbieter)] = (
                b.geraet_zuzahlung,
                b.tarif_monatlich,
                kosten_ueber(b).gesamt,
            )
    for schluessel, werte in erwartet.items():
        assert gefunden[schluessel] == werte, schluessel
    assert all("/pks" not in u and "checkout" not in u for u in aufrufe)


def test_lauf_nicht_waehlbare_tarife_sind_benannte_luecken_ein_abruf_je_tarif():
    from telco_radar.collect.geraete import tarifwelt_lauf

    hole, aufrufe = fixture_hole()
    lauf = tarifwelt_lauf.lies_modell(
        "samsung-galaxy-s26", LEITER, hole, "2026-11-08", warte=lambda s: None
    )
    tarife = {(b.anbieter, b.tarif_name) for b in lauf.buendel}
    assert ("Saturn/MediaMarkt · o2-Netz", "Mobile M Promo") in tarife
    leere = [grund for _, grund in lauf.luecken]
    assert leere and all("waehlbar" in g for g in leere)
    liste = tarifwelt.lies_tarifliste(
        (_FIXTURES / "tarifwelt_mm_tarifliste_galaxys26_20261108.json").read_text()
    )
    kandidaten = tarifwelt_lauf.vergleichbare_tarife(liste, LEITER)
    listen = [u for u in aufrufe if "/tariff?" in u]
    detail = [u for u in aufrufe if "tfi=" in u]
    assert len(aufrufe) == 1 + len(listen) + len(detail)
    assert len(detail) == len(listen) * len(kandidaten)
    assert len(detail) == len(set(detail))
    assert len(kandidaten) > 3
