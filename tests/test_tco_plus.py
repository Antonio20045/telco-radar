"""o2 „Plus“: der Abstand zum Tarif ohne Plus, an EINER Stelle (`tco_plus`).

Prüfung PR 207: der Betrag wird nicht in `report/` gerechnet, sondern im Gerätelauf als
Feld `plus_vorteil` am Plus-Bündel abgelegt; gepaart wird je Anbieter, SKU (Gerät,
Speicher, Farbe), Ratenzahl, Zustand und Messtag, mehrdeutig heißt kein Betrag.

Gegen echte Daten: die Antwort des Galaxy S26 256 GB vom 21.11.2026
(`o2_galaxy_s26_tarifoptionen_20261121.json.gz`) nennt je Tarif die Monatssumme
(`monthlyCharges`); 53,49 € (on Demand M) minus 44,99 € (on Demand M Plus) = 8,50 €.
"""

from __future__ import annotations

import gzip
from collections import Counter
from pathlib import Path

from telco_radar import tco_plus
from telco_radar.collect.geraete import o2
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-21"
SKU = "samsung-galaxy-s26-256gb-violett"
PLUS = "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)"
OHNE = "O2 Mobile on Demand M mit 50 GB+ (24 Mon.)"
_FIX = Path(__file__).parent / "fixtures" / "geraete"


def _seite() -> tuple[float, float, float]:
    with gzip.open(_FIX / "o2_galaxy_s26_tarifoptionen_20261121.json.gz", "rt") as fh:
        pv = o2.lies_konfiguration(fh.read())
    summe = {
        o2._ohne_markup(o["displayValue"]): float(o["monthlyCharges"])
        for o in pv["tariff"]["tariffOptions"]
    }
    return (
        o2._gemessen(pv)["rate"],
        summe["O2 Mobile on Demand M Plus mit 50 GB+"],
        summe["O2 Mobile on Demand M mit 50 GB+"],
    )


def _b(name: str, summe: float, rate: float, **mehr) -> Buendel:
    werte = dict(
        sku_id=SKU,
        anbieter="o2",
        tarif_name=name,
        tarif_monatlich=round(summe - rate, 2),
        geraet_zuzahlung=1.0,
        geraet_monatsrate=rate,
        laufzeit_monate=36,
        anschlusspreis=0.0,
        abgerufen_am=HEUTE,
        zustand="neu",
    )
    return Buendel(**{**werte, **mehr})


def _plus(saetze: list) -> Buendel:
    return next(b for b in saetze if "Plus" in b.tarif_name.split())


def test_abstand_ist_der_der_seite():
    rate, plus, ohne = _seite()
    z: Counter = Counter()
    aus = tco_plus.vermerke([_b(PLUS, plus, rate), _b(OHNE, ohne, rate)], z)
    assert _plus(aus).plus_vorteil == round(ohne - plus, 2) == 8.5
    assert next(b for b in aus if b.tarif_name == OHNE).plus_vorteil is None
    assert z == {"mit_betrag": 1}


def test_gegenprobe_anderer_speicher_oder_messtag_ist_kein_gegenstueck():
    rate, plus, ohne = _seite()
    for anders in (
        {"sku_id": "samsung-galaxy-s26-512gb-violett"},
        {"abgerufen_am": "2026-11-20"},
        {"laufzeit_monate": 24},
    ):
        z: Counter = Counter()
        aus = tco_plus.vermerke(
            [_b(PLUS, plus, rate), _b(OHNE, ohne, rate, **anders)], z
        )
        assert _plus(aus).plus_vorteil is None, anders
        assert z == {tco_plus.OHNE_GEGENSTUECK: 1}, anders


def test_mehrdeutiges_gegenstueck_heisst_kein_betrag():
    rate, plus, ohne = _seite()
    zwei = [_b(OHNE, ohne, rate), _b(OHNE, ohne + 1.0, rate, tarif_id="o2:anders")]
    z: Counter = Counter()
    aus = tco_plus.vermerke([_b(PLUS, plus, rate), *zwei], z)
    assert _plus(aus).plus_vorteil is None
    assert z == {tco_plus.MEHRDEUTIG: 1}


def test_nicht_positiver_abstand_heisst_kein_betrag():
    rate, plus, _ = _seite()
    z: Counter = Counter()
    aus = tco_plus.vermerke([_b(PLUS, plus, rate), _b(OHNE, plus, rate)], z)
    assert _plus(aus).plus_vorteil is None
    assert z == {tco_plus.NICHT_POSITIV: 1}


def test_der_geraetelauf_legt_den_abstand_am_buendel_ab(tmp_path):
    """`geraete_o2_anschluss.speichere` setzt das Feld vor dem Speichern; der Bestand
    trägt es (`tco_store._MESSFELDER`), die Seite liest nur das Feld."""
    from types import SimpleNamespace

    from telco_radar import geraete_o2_anschluss
    from telco_radar.analyze.tco_store import TcoDB
    from telco_radar.geraete_config import lade_quellen

    rate, plus, ohne = _seite()
    saetze = [
        _b(PLUS, plus, rate, tarif_id="o2:o2-mobile-on-demand-m-plus"),
        _b(OHNE, ohne, rate, tarif_id="o2:o2-mobile-on-demand-m"),
    ]
    tco = TcoDB(tmp_path / "geraete_tco.json")
    bilanz = SimpleNamespace(buendel=saetze)
    wurzel = Path(__file__).resolve().parents[1]
    geraete_o2_anschluss.speichere(bilanz, tco, lade_quellen(wurzel), None, None, HEUTE)
    assert tco.nach_id(saetze[0].id)["plus_vorteil"] == 8.5
    assert tco.nach_id(saetze[1].id)["plus_vorteil"] is None
