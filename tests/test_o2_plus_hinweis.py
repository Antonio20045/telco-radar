"""o2 „Plus“: die Zeile nennt „mit Zweitprodukt x € im Monat günstiger“.

Entscheidung Antonio (21.11.2026): im Vergleich zählt bei o2 der Tarif ohne „Plus“;
der Plus-Tarif zählt nicht und nennt seinen Abstand. x ist der Monatsbetrag (Rate plus
Tarif) des gleichnamigen Tarifs ohne „Plus“ minus den des Plus-Tarifs, desselben
Modells, derselben Ratenzahl, desselben Messtags (`report/geraete_plus.vorteil`).

Gegen echte Daten: die Konfigurationsantwort des Galaxy S26 256 GB vom 21.11.2026
(`o2_galaxy_s26_tarifoptionen_20261121.json.gz`) nennt je Tarif die Monatssumme
(`monthlyCharges`); der Abstand zwischen „on Demand M Plus“ und „on Demand M“ dort ist
das x der Zeile.
"""

from __future__ import annotations

import gzip
from pathlib import Path

from telco_radar.collect.geraete import o2
from telco_radar.report import geraete_plus, geraete_preisstand, geraete_tco_karten
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-21"
SKU = "samsung-galaxy-s26-256gb-schwarz"
PLUS = "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)"
OHNE = "O2 Mobile on Demand M mit 50 GB+ (24 Mon.)"
_FIX = Path(__file__).parent / "fixtures" / "geraete"


def _summen() -> tuple[float, float, float]:
    """(Geräterate, Monatssumme Plus, Monatssumme ohne Plus) aus der echten Antwort."""
    with gzip.open(_FIX / "o2_galaxy_s26_tarifoptionen_20261121.json.gz", "rt") as fh:
        pv = o2.lies_konfiguration(fh.read())
    summe = {
        o2._ohne_markup(o["displayValue"]): float(o["monthlyCharges"])
        for o in pv["tariff"]["tariffOptions"]
    }
    rate = o2._gemessen(pv)["rate"]
    return (
        rate,
        summe["O2 Mobile on Demand M Plus mit 50 GB+"],
        summe["O2 Mobile on Demand M mit 50 GB+"],
    )


def _b(anbieter, name, tarif, rate, tag=HEUTE, laufzeit=36, herleitung="") -> Buendel:
    return Buendel(
        sku_id=SKU,
        anbieter=anbieter,
        tarif_name=name,
        tarif_monatlich=tarif,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=rate,
        laufzeit_monate=laufzeit,
        anschlusspreis=0.0,
        quelle_url=f"https://example.org/{anbieter}/{name}",
        abgerufen_am=tag,
        zustand="neu",
        herleitung=herleitung,
    )


def _listung(anbieter: str) -> dict:
    return {
        "sku_id": SKU,
        "device_id": "samsung-galaxy-s26",
        "speicher_gb": 256,
        "anbieter": anbieter,
        "zustand": "neu",
        "farbe_normalisiert": "schwarz",
        "quelle_url": f"https://example.org/{anbieter}",
        "abgerufen_am": HEUTE,
    }


def _karten(*o2_buendel: Buendel) -> dict:
    alle = [_b("Vodafone", "GigaMobil M", 40.0, 33.5), *o2_buendel]
    erg = geraete_tco_karten.modelle(
        alle, [_listung("Vodafone"), _listung("o2")], [], {}, None, heute=HEUTE
    )
    return {k["tarif"]: k for k in erg["modelle"][0]["karten"] if k["anbieter"] == "o2"}


def test_hinweisbetrag_ist_der_abstand_der_seite():
    rate, plus, ohne = _summen()
    erwartet = round(ohne - plus, 2)
    assert erwartet == 8.5
    karten = _karten(
        _b("o2", PLUS, round(plus - rate, 2), rate),
        _b("o2", OHNE, round(ohne - rate, 2), rate),
    )
    k = karten[PLUS]
    assert k[geraete_plus.FELD] == erwartet
    zeile = geraete_preisstand.anzeige(k)
    assert zeile["luecke_kurz"] == "mit Zweitprodukt 8,50 € im Monat günstiger"
    assert "8,50 €" in zeile["leer_grund"]
    assert k["zaehlt"] is False
    assert karten[OHNE]["zaehlt"] is True
    assert geraete_plus.FELD not in karten[OHNE]


def test_gegenprobe_ohne_gegenstueck_kein_betrag():
    rate, plus, _ = _summen()
    k = _karten(_b("o2", PLUS, round(plus - rate, 2), rate))[PLUS]
    assert k[geraete_plus.FELD] is None
    zeile = geraete_preisstand.anzeige(k)
    assert zeile["luecke_kurz"] == "Rabatt nur mit Zweitprodukt"
    assert "€" not in zeile["luecke_kurz"]


def test_gegenprobe_anderer_messtag_oder_andere_raten_kein_betrag():
    rate, plus, ohne = _summen()
    gestern = _karten(
        _b("o2", PLUS, round(plus - rate, 2), rate),
        _b("o2", OHNE, round(ohne - rate, 2), rate, tag="2026-11-20"),
    )
    assert gestern[PLUS][geraete_plus.FELD] is None
    andere = geraete_plus.vorteil(
        {
            "anbieter": "o2",
            "tarif": PLUS,
            "rate": 1.0,
            "monatlich": 2.0,
            "raten_laufzeit": 24,
        },
        [
            {
                "anbieter": "o2",
                "tarif": OHNE,
                "rate": 1.0,
                "monatlich": 7.0,
                "raten_laufzeit": 36,
            }
        ],
    )
    assert andere is None


def test_geschaetztes_buendel_ohne_plus_zaehlt_nicht_gemessenes_zaehlt():
    rate, _, ohne = _summen()
    geschaetzt = _karten(
        _b("o2", OHNE, round(ohne - rate, 2), rate, herleitung=o2.HERLEITUNG_TARIFSUMME)
    )
    assert geschaetzt[OHNE]["zaehlt"] is False
    assert _karten(_b("o2", OHNE, round(ohne - rate, 2), rate))[OHNE]["zaehlt"] is True
