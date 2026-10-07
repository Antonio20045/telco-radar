"""Vodafones Online-Aktionspreis als Tarifphase (Datenkonzept Geräte Regel 3, §8).

Befund Antonio 07.10.2026, vodafone.de/privat/handys/iphone-17-pro.html, GigaMobil XS
mit 24 Raten: „pro Monat 73,45 €“, durchgestrichen 81,45 €. Der Bestand hatte 31,95 €
Tarif + 49,50 € Rate = 81,45 €. Weder 73,45 noch 81,45 steht in einer gespeicherten
Antwort; belegt sind beide Summanden: der Tarif mit und ohne Rabatt in der Tarifantwort
der Klick-Erkundung (`vodafone_tarif_hardware_iphone_17_pro_20261007.json`, Mobil XS,
36 Raten) und die 24er-Rate 49,50 € in der Detailantwort desselben Tages
(`vodafone_virtualitem_iphone_17_pro_20261007.json.gz`). Der Tarifrabatt hängt nicht an
der Ratenzahl (Pixel 11, 05.09.2026: Mobil XS mit 12, 24 und 36 Raten je 23,95 €).

`tarif_monatlich` ist der Tarifpreis in Monat 1 wie bei o2 und congstar (23,95 €),
`tarif_listenpreis` der ohne Rabatt (31,95 €). Wo ein Test eine Antwort verändert, steht
es am Test: Rabatt ohne Ende, Rabatt an einem anderen Posten, ein Rabatt kürzer als die
Bindung und ein bedingter Posten mit Betrag kommen in keiner Antwort vor.
"""

import copy
import gzip
import json
import logging
from pathlib import Path

from telco_radar.collect.geraete.vodafone import lies_buendel, loese_tarifnamen
from telco_radar.collect.geraete.vodafone_aktion import (
    BEDINGTE_POSTEN,
    NICHT_GELESEN,
    ist_bedingt,
)
from telco_radar.tarif_model import buendelphasen_aus
from telco_radar.tco_kosten import kosten_ueber, tarifpreis_im_monat
from telco_radar.tco_model import POSTEN_TARIF, Buendel

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_IPHONE_TARIFE = "vodafone_tarif_hardware_iphone_17_pro_20261007.json"
_IPHONE_DETAIL = "vodafone_virtualitem_iphone_17_pro_20261007.json.gz"
_PIXEL_TARIFE = "vodafone_tarif_hardware.json"
_IPHONE_HW = "57562"
_PIXEL_HW = "58060"
_SEITE = "https://www.vodafone.de/privat/handys/iphone-17-pro.html"


def _daten(datei: str) -> dict:
    return json.loads((_FIX / datei).read_text(encoding="utf-8"))


def _komposition(daten: dict, tarif: str, dauer) -> dict:
    """Die eine Komposition eines Tarifs mit `dauer` Raten (None im `sub`-Fall)."""
    [treffer] = [
        k
        for eintrag in daten["data"]
        for t in eintrag["tariffs"]
        if t["tariffName"] == tarif
        for atom in t["atomics"]
        for k in atom["prices"]["composition"]
        if k.get("financingDuration") == dauer
    ]
    return treffer


def _angebote(daten: dict, hwid: str) -> dict:
    """Die Sätze der Tarifantwort `daten` für Variante `hwid`, je (Tarif, Raten)."""
    text = json.dumps(daten)
    roh = [
        {
            "quelle": "vodafone_buendel",
            "sku": hwid,
            "titel": "iPhone 17 Pro",
            "url": _SEITE,
            "tarif_name": "",
            "tarif_slug": "vorschau",
        }
    ]
    loese_tarifnamen(lambda url, kopfzeilen: (200, text), {}, roh)
    return {(s["tarif_name"], s["laufzeit_monate"]): s for s in roh}


def _buendel(satz: dict) -> Buendel:
    return Buendel(
        sku_id="apple-iphone-17-pro-256gb-cosmic-orange",
        anbieter="Vodafone",
        tarif_name=satz["tarif_name"],
        tarif_monatlich=satz["tarif_monatlich"],
        geraet_zuzahlung=satz["geraet_zuzahlung"],
        geraet_monatsrate=satz["geraet_monatsrate"],
        laufzeit_monate=satz["laufzeit_monate"],
        anschlusspreis=satz["anschlusspreis"],
        tarif_phasen=buendelphasen_aus(satz.get("tarif_phasen")),
    )


def _xs_iphone(daten: dict | None = None) -> dict:
    return _angebote(daten or _daten(_IPHONE_TARIFE), _IPHONE_HW)[("Mobil XS", 36)]


def test_iphone_17_pro_mobil_xs_traegt_den_aktionspreis_mit_dauer():
    """Monat 1 zeigt den Aktionspreis, der Listenpreis steht daneben; die Geräterate
    bleibt wie gemessen: rabattiert ist der Tarif."""
    satz = _xs_iphone()
    phasen = satz.get("tarif_phasen")
    assert [(p["von_monat"], p["bis_monat"], p["betrag"]) for p in phasen] == [
        (1, 24, 23.95)
    ]
    assert "withDiscounts" in phasen[0]["beleg"]
    assert (
        satz["tarif_monatlich"],
        satz["tarif_listenpreis"],
        satz["geraet_monatsrate"],
    ) == (23.95, 31.95, 33.0)


def test_der_rabatt_ist_der_benannte_online_vorteil_der_antwort():
    daten = _daten(_IPHONE_TARIFE)
    [xs] = [
        t for e in daten["data"] for t in e["tariffs"] if t["tariffName"] == "Mobil XS"
    ]
    rabatte = {
        r["displayLabel"]: r["gross"] for r in xs["atomics"][0]["discount"]["monetary"]
    }
    vorteil = rabatte["24 Monate: 25 % Vorteil auf Tarifpreis ohne Hardwarezuzahlung"]
    satz = _xs_iphone(daten)
    assert round(satz["tarif_monatlich"] - satz["tarif_listenpreis"], 2) == vorteil
    assert vorteil == -8.0


def test_die_summen_der_seite_aus_den_gespeicherten_summanden():
    """73,45 € und 81,45 € (Screenshot, 24 Raten) aus Tarifphase und 24er-Rate."""
    detail = gzip.decompress((_FIX / _IPHONE_DETAIL).read_bytes()).decode("utf-8")
    [rate] = {
        s["geraet_monatsrate"]
        for s in lies_buendel(detail)
        if s["sku"] == _IPHONE_HW and s["laufzeit_monate"] == 24
    }
    satz = _xs_iphone()
    assert round(rate + satz["tarif_monatlich"], 2) == 73.45
    assert round(rate + satz["tarif_listenpreis"], 2) == 81.45


def test_die_kernzahl_rechnet_24_monate_aktionspreis():
    satz = _angebote(_daten(_PIXEL_TARIFE), _PIXEL_HW)[("Mobil XS", 24)]
    b = _buendel(satz)
    assert tarifpreis_im_monat(b, 1) == tarifpreis_im_monat(b, 24) == 23.95
    k = kosten_ueber(b)
    erwartet = satz["geraet_zuzahlung"] + 24 * (satz["geraet_monatsrate"] + 23.95)
    assert k.gesamt == round(erwartet + satz["anschlusspreis"], 2)
    assert k.luecken == []


def test_nach_der_bindung_bleibt_es_bei_der_luecke():
    """Ab Monat 25 nennt die Antwort nur die Geräterate - kein erfundener Tarifpreis."""
    b = _buendel(_xs_iphone())
    assert tarifpreis_im_monat(b, 25) is None
    assert f"{POSTEN_TARIF} Monat 25–36" in kosten_ueber(b).luecken


def test_zwoelf_raten_tragen_zwei_rabattphasen():
    """Mobil M, 12 Raten (Pixel 11, 05.09.): Ratenzahlungsrabatt endet mit Rate 12."""
    satz = _angebote(_daten(_PIXEL_TARIFE), _PIXEL_HW)[("Mobil M", 12)]
    assert [
        (p["von_monat"], p["bis_monat"], p["betrag"]) for p in satz["tarif_phasen"]
    ] == [
        (1, 12, 27.61),
        (13, 24, 30.61),
    ]
    assert (satz["tarif_monatlich"], satz["tarif_listenpreis"]) == (27.61, 51.95)


def test_kein_gespeicherter_rabatt_trifft_die_geraeterate():
    for datei in (_IPHONE_TARIFE, _PIXEL_TARIFE):
        for satz in _angebote(
            _daten(datei), _IPHONE_HW if "iphone" in datei else _PIXEL_HW
        ).values():
            assert satz["tarif_monatlich"] is not None, satz["tarif_name"]
    text = (_FIX / _IPHONE_TARIFE).read_text(encoding="utf-8")
    for k in (_komposition(json.loads(text), t, 36) for t in ("Mobil XS", "Mobil XL")):
        assert "withDiscounts" not in json.dumps(k["priceByComponent"]["hardware"])


def test_gegenprobe_ohne_rabatt_bleibt_der_satz_wie_gemessen():
    """FamilyCard L (05.09.) hat keinen Rabatt; XS ohne `withDiscounts` (im Test
    entfernt) ist derselbe Satz wie vorher, nur ohne Phase."""
    familycard = _angebote(_daten(_PIXEL_TARIFE), _PIXEL_HW)[("FamilyCard L", 24)]
    assert (
        familycard["tarif_monatlich"],
        familycard["tarif_listenpreis"],
        familycard["tarif_phasen"],
    ) == (59.99, 59.99, [])

    daten = _daten(_IPHONE_TARIFE)
    k = _komposition(daten, "Mobil XS", 36)
    del k["priceByComponent"]["tariff"]["priceByType"]["rate"]["month"]["withDiscounts"]
    ohne, mit = _xs_iphone(daten), _xs_iphone()
    assert (ohne["tarif_monatlich"], ohne["tarif_phasen"]) == (31.95, [])
    aktion = {f: mit[f] for f in ("tarif_monatlich", "tarif_phasen")}
    assert {**ohne, **aktion} == mit


def test_rabatt_ohne_dauer_ist_eine_luecke_keine_phase(caplog):
    """Im Test das Ende der Rabattphase entfernt."""
    daten = _daten(_IPHONE_TARIFE)
    k = _komposition(daten, "Mobil XS", 36)
    del k["priceByComponent"]["tariff"]["priceByType"]["rate"]["month"][
        "withDiscounts"
    ][0]["recurrenceEnd"]
    with caplog.at_level(logging.WARNING):
        satz = _xs_iphone(daten)
    assert (satz["tarif_monatlich"], satz["tarif_phasen"]) == (None, [])
    assert satz["tarif_listenpreis"] == 31.95
    assert "ohne belegte Dauer" in caplog.text
    assert POSTEN_TARIF in kosten_ueber(_buendel(satz)).luecken


def test_rabatt_den_die_gesamtrate_nicht_dem_tarif_zuordnet_ist_eine_luecke():
    """Im Test die Gesamtrate mit Rabatt auf die ohne Rabatt gesetzt."""
    daten = _daten(_IPHONE_TARIFE)
    k = _komposition(daten, "Mobil XS", 36)
    gesamt = k["totalMonthlyRatePrice"]
    gesamt["withDiscounts"] = copy.deepcopy(gesamt["withoutDiscounts"])
    satz = _xs_iphone(daten)
    assert (satz["tarif_monatlich"], satz["tarif_phasen"]) == (None, [])


def test_ein_kurzer_rabatt_endet_im_listenpreis():
    """Im Test Rabatt und Gesamtrate auf Monat 1-12 gekürzt: Monat 13-24 Listenpreis."""
    daten = _daten(_IPHONE_TARIFE)
    k = _komposition(daten, "Mobil XS", 36)
    monat = k["priceByComponent"]["tariff"]["priceByType"]["rate"]["month"]
    monat["withDiscounts"][0]["recurrenceEnd"] = 12
    erste = dict(k["totalMonthlyRatePrice"]["withDiscounts"][0], recurrenceEnd=12)
    mitte = dict(erste, recurrenceStart=13, recurrenceEnd=24, gross=64.95)
    rest = k["totalMonthlyRatePrice"]["withDiscounts"][1]
    k["totalMonthlyRatePrice"]["withDiscounts"] = [erste, mitte, rest]
    phasen = _xs_iphone(daten)["tarif_phasen"]
    assert [(p["von_monat"], p["bis_monat"], p["betrag"]) for p in phasen] == [
        (1, 12, 23.95),
        (13, 24, 31.95),
    ]
    assert "withoutDiscounts" in phasen[1]["beleg"]


_WECHSELBONUS = (
    "Wechselbonus: 5 € Rabatt pro Monat bei Rufnummernmitnahme, 12 Monate lang"
)


def _mit_posten(daten: dict, label: str, monat_1_12: float) -> dict:
    """Mobil XS (36 Raten) mit einem Posten −5 € in Monat 1–12, wie ihn die Antwort
    führen würde: im Rabattblock, in `withDiscounts` des Tarifs und der Gesamtrate."""
    [xs] = [
        t for e in daten["data"] for t in e["tariffs"] if t["tariffName"] == "Mobil XS"
    ]
    xs["atomics"][0]["discount"]["monetary"].append(
        {
            "gross": -5.0,
            "net": -4.2,
            "displayLabel": label,
            "discountId": "99999",
            "mandatory": False,
            "isFinancingDiscount": False,
        }
    )
    k = _komposition(daten, "Mobil XS", 36)
    monat = k["priceByComponent"]["tariff"]["priceByType"]["rate"]["month"]
    [phase] = monat["withDiscounts"]
    monat["withDiscounts"] = [
        dict(phase, recurrenceEnd=12, gross=monat_1_12),
        dict(phase, recurrenceStart=13),
    ]
    gesamt = k["totalMonthlyRatePrice"]["withDiscounts"]
    gesamt[:1] = [
        dict(gesamt[0], recurrenceEnd=12, gross=round(monat_1_12 + 33.0, 2)),
        dict(gesamt[0], recurrenceStart=13),
    ]
    return daten


def _spannen(satz: dict) -> list[tuple]:
    return [(p["von_monat"], p["bis_monat"], p["betrag"]) for p in satz["tarif_phasen"]]


def test_bedingter_wechselbonus_wird_keine_preisphase():
    """Prüferfall, im Test hinzugefügt: 5 € Wechselbonus in Monat 1–12 stehen in
    Rabattblock und `withDiscounts`. Er zählt nie; Monat 1–24 bleibt 23,95 €."""
    satz = _xs_iphone(_mit_posten(_daten(_IPHONE_TARIFE), _WECHSELBONUS, 18.95))
    assert _spannen(satz) == [(1, 24, 23.95)]
    assert satz["tarif_monatlich"] == 23.95
    assert "ohne bedingte Posten (Wechselbonus" in satz["tarif_phasen"][0]["beleg"]


def test_gegenprobe_derselbe_posten_ohne_bedingung_geht_ein():
    satz = _xs_iphone(
        _mit_posten(_daten(_IPHONE_TARIFE), "12 Monate: 5 € Online-Vorteil", 18.95)
    )
    assert _spannen(satz) == [(1, 12, 18.95), (13, 24, 23.95)]
    assert satz["tarif_monatlich"] == 18.95


def test_bedingter_posten_ohne_belegten_preis_ist_eine_luecke(caplog):
    """Im Test kostet Monat 1–12 17,95 €: weder 23,95 € noch 23,95 € minus 5 €
    Wechselbonus. Der Preis ohne Bedingung ist nicht belegt."""
    with caplog.at_level(logging.WARNING):
        satz = _xs_iphone(_mit_posten(_daten(_IPHONE_TARIFE), _WECHSELBONUS, 17.95))
    assert (satz["tarif_monatlich"], satz["tarif_listenpreis"]) == (None, 31.95)
    assert satz["tarif_phasen"] == []
    assert "Preis ohne Bedingung nicht belegt" in caplog.text


def test_die_vorschau_ohne_rabattposten_ist_eine_luecke(caplog):
    """Die Detailantwort nennt `withDiscounts`, aber keinen Posten: ob ein bedingter
    darin steckt, ist offen. Gegenprobe: dieselbe Stufe aus der Tarifantwort."""
    detail = gzip.decompress((_FIX / _IPHONE_DETAIL).read_bytes()).decode("utf-8")
    with caplog.at_level(logging.INFO):
        [xs] = [
            s
            for s in lies_buendel(detail)
            if s["sku"] == _IPHONE_HW and s["laufzeit_monate"] == 36
        ]
    assert (xs["tarif_monatlich"], xs["tarif_listenpreis"]) == (None, 31.95)
    assert xs["tarif_phasen"] == []
    assert NICHT_GELESEN in caplog.text
    assert _xs_iphone()["tarif_monatlich"] == 23.95


def test_kein_gespeicherter_posten_ist_bedingt():
    """Neukunden-Vorteil, Hardware-Bonus, Ratenzahlungsrabatt, Anschluss zählen; jeder
    Wortteil von `BEDINGTE_POSTEN` macht einen Posten bedingt."""
    for datei in (_IPHONE_TARIFE, _PIXEL_TARIFE):
        for e in _daten(datei)["data"]:
            for t in e["tariffs"]:
                for a in t["atomics"]:
                    for p in a["discount"]["monetary"]:
                        assert not ist_bedingt(p), p["displayLabel"]
    for wort in BEDINGTE_POSTEN:
        assert ist_bedingt({"displayLabel": f"10 € {wort.title()}-Rabatt"}), wort
