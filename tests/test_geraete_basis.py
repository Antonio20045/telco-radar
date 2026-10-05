"""Abnahme P22: was der Umzug nach collect/geraete/basis.py nicht aendern darf.

Geprueft wird nur ueber den oeffentlichen Eingang des Pakets
(`telco_radar.collect.geraete`: ADAPTER, Adapter, registriere,
umgesetzte_methoden, GeraeteAbrufFehler) und die dort registrierten
Lesefunktionen. Die Preislesung je Adapter wird an dem Feld beobachtet, das
sie unveraendert in den Rohsatz durchreicht.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys

import pytest

import telco_radar.collect.geraete as geraete

METHODEN_HEUTE = (
    "congstar_next",
    "einsundeins_buendel",
    "ldjson",
    "o2_katalog",
    "saturn_brand",
    "shopify",
    "telekom_kategorie",
    "vodafone_api",
)

PREISFAELLE = [
    pytest.param(5, 5.0, id="zahl"),
    pytest.param(12.34, 12.34, id="kommazahl"),
    pytest.param("5", 5.0, id="zahl-als-text"),
    pytest.param("12.34", 12.34, id="punkt-text"),
    pytest.param("4,99", None, id="komma-text"),
    pytest.param(None, None, id="none"),
    pytest.param("", None, id="leerer-text"),
    pytest.param([1], None, id="liste"),
    pytest.param({"betrag": 1}, None, id="dict"),
]


@pytest.fixture
def ohne_netz(monkeypatch):
    def gesperrt(*args, **kwargs):
        raise AssertionError("Netzzugriff beim Lesen eines Textes")

    monkeypatch.setattr(socket, "socket", gesperrt)
    monkeypatch.setattr(socket, "create_connection", gesperrt)
    monkeypatch.setattr(socket, "getaddrinfo", gesperrt)


def _vodafone_detail(wert) -> str:
    komposition = {
        "offerCoreHash": "h1",
        "financingDuration": 24,
        "totalMonthlyRatePrice": {
            "withoutDiscounts": [
                {"gross": 20, "recurrenceStart": 1, "recurrenceEnd": 24}
            ]
        },
        "priceByComponent": {
            "tariff": {
                "priceByType": {
                    "rate": {
                        "month": {"withoutDiscounts": {"gross": 20}},
                        "onetime": {"withoutDiscounts": {"gross": wert}},
                    }
                }
            }
        },
    }
    return json.dumps(
        {
            "data": {
                "modelName": "Testgeraet",
                "atomics": [
                    {"hardwareId": "hw1", "prices": {"composition": [komposition]}}
                ],
            }
        }
    )


def _telekom_seite(wert) -> str:
    zustand = {
        "productList": {
            "selectedPlan": {
                "id": "T1",
                "name": "Testtarif",
                "prices": [
                    {"priceType": "recurringFee", "actualValue": 20},
                    {"priceType": "activationFee", "actualValue": wert},
                ],
            },
            "data": [
                {
                    "id": "sku1",
                    "name": "Testgeraet",
                    "variantSlug": "schwarz-128-gb",
                    "price": {
                        "upfrontPrice": 1,
                        "installments": [
                            {
                                "numberOfInstallments": 36,
                                "recurringPrice": 10,
                                "totalPrice": 361,
                            }
                        ],
                    },
                    "formattedPrices": {
                        "recurringTariffPrice": {
                            "price": {"id": "T1-36", "actualValue": 20}
                        }
                    },
                }
            ],
        }
    }
    return (
        "<html><script>window.__INITIAL_STATE__ = "
        + json.dumps(zustand)
        + ";</script></html>"
    )


def _congstar_seite(wert) -> str:
    nutzlast = (
        '"prefetchedPlansWithDevicesPrices":'
        + json.dumps(
            [
                {
                    "variants": [
                        {
                            "id": 7,
                            "devices": [
                                {
                                    "variants": [
                                        {
                                            "id": 11,
                                            "prices": {
                                                "paymentVariants": [
                                                    {
                                                        "type": "INSTALLMENT_PLAN",
                                                        "subtype": "UNSPECIFIED",
                                                        "contractDuration": 24,
                                                        "oneTime": {"discounted": 1},
                                                        "recurring": {"discounted": 10},
                                                        "total": 241,
                                                    }
                                                ]
                                            },
                                        }
                                    ]
                                }
                            ],
                        }
                    ]
                }
            ]
        )
        + ',"prefetchedDevice":'
        + json.dumps(
            {
                "variants": [
                    {
                        "id": 11,
                        "title": "Testgeraet",
                        "memory": {"referenceGB": 128},
                        "condition": "NEW",
                    }
                ]
            }
        )
        + ',"prefetchedPlans":'
        + json.dumps(
            [
                {
                    "variants": [
                        {
                            "id": 7,
                            "title": "Testtarif",
                            "prices": {
                                "recurring": {"discounted": 10},
                                "activation": {"discounted": wert},
                            },
                        }
                    ]
                }
            ]
        )
    )
    fragment = json.dumps([1, nutzlast], separators=(",", ":"))
    return "<script>self.__next_f.push(" + fragment + ")</script>"


def _o2_katalog(wert) -> str:
    return json.dumps(
        {
            "hardware": [
                {
                    "description": "Testgeraet",
                    "offerName": "",
                    "externalId": "o2-1",
                    "price": {"totalPrice": wert},
                }
            ]
        }
    )


def _gelesener_preis(saetze: list[dict], feld: str):
    assert len(saetze) == 1, saetze
    return saetze[0][feld]


def test_umgesetzte_methoden_bleiben_dieselben():
    assert geraete.umgesetzte_methoden() == METHODEN_HEUTE
    assert tuple(sorted(geraete.ADAPTER)) == METHODEN_HEUTE
    for methode, adapter in geraete.ADAPTER.items():
        assert isinstance(adapter, geraete.Adapter)
        assert adapter.name == methode


def test_zweiter_import_registriert_nichts_doppelt():
    programm = (
        "import importlib\n"
        "import telco_radar.collect.geraete.vodafone\n"
        "import telco_radar.collect.geraete as g\n"
        "vorher = g.umgesetzte_methoden()\n"
        "for name in ('vodafone', 'o2', 'congstar', 'telekom', 'einsundeins',\n"
        "             'saturn'):\n"
        "    importlib.import_module('telco_radar.collect.geraete.' + name)\n"
        "import telco_radar.collect.geraete as g2\n"
        "assert g2 is g\n"
        "assert g.umgesetzte_methoden() == vorher, g.umgesetzte_methoden()\n"
        "importlib.reload(g)\n"
        "assert g.umgesetzte_methoden() == vorher, g.umgesetzte_methoden()\n"
        "assert len(g.ADAPTER) == len(set(g.ADAPTER))\n"
        "print(','.join(vorher))\n"
    )
    umgebung = dict(os.environ)
    umgebung["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    lauf = subprocess.run(
        [sys.executable, "-c", programm],
        capture_output=True,
        text=True,
        env=umgebung,
        timeout=120,
    )
    assert lauf.returncode == 0, lauf.stderr
    assert lauf.stdout.strip() == ",".join(METHODEN_HEUTE)


def test_registriere_traegt_ein_und_umgesetzte_methoden_sortiert(monkeypatch):
    monkeypatch.setitem(geraete.ADAPTER, "aaa_probe", None)
    probe = geraete.Adapter(name="aaa_probe", lies=lambda text, url="": [])
    geraete.registriere("aaa_probe", probe)
    geraete.registriere("aaa_probe", probe)
    erwartet = tuple(sorted((*METHODEN_HEUTE, "aaa_probe")))
    assert geraete.umgesetzte_methoden() == erwartet
    assert geraete.ADAPTER["aaa_probe"] is probe


def test_geraeteabruffehler_traegt_status():
    ohne = geraete.GeraeteAbrufFehler("weg")
    mit = geraete.GeraeteAbrufFehler("tot", status=404)
    assert ohne.status is None
    assert mit.status == 404
    assert str(mit) == "tot"
    assert isinstance(mit, RuntimeError)


FEHLERFAELLE = [
    pytest.param("vodafone_api", "lies", "", id="vodafone"),
    pytest.param("o2_katalog", "lies", "{}", id="o2"),
    pytest.param("telekom_kategorie", "lies", "<html></html>", id="telekom"),
    pytest.param("congstar_next", "lies", "<html></html>", id="congstar"),
    pytest.param(
        "einsundeins_buendel", "lies_buendel", "<html></html>", id="einsundeins"
    ),
    pytest.param("saturn_brand", "lies", "<html></html>", id="saturn"),
]


@pytest.mark.parametrize("methode,lesart,text", FEHLERFAELLE)
def test_jeder_adapter_wirft_dieselbe_klasse(ohne_netz, methode, lesart, text):
    lesen = getattr(geraete.ADAPTER[methode], lesart)
    with pytest.raises(geraete.GeraeteAbrufFehler) as fehler:
        lesen(text, "https://beispiel.invalid/")
    assert type(fehler.value) is geraete.GeraeteAbrufFehler
    assert fehler.value.status is None


def test_keine_zweite_klasse_gleichen_namens():
    for name in ("vodafone", "o2", "congstar", "telekom", "einsundeins", "saturn"):
        __import__(f"telco_radar.collect.geraete.{name}")
    gefunden = {
        modulname: modul.GeraeteAbrufFehler
        for modulname, modul in list(sys.modules.items())
        if modulname.startswith("telco_radar") and hasattr(modul, "GeraeteAbrufFehler")
    }
    assert "telco_radar.collect.geraete" in gefunden
    fremd = {
        modulname: klasse
        for modulname, klasse in gefunden.items()
        if klasse is not geraete.GeraeteAbrufFehler
    }
    assert fremd == {}


BUENDELSEITEN = [
    pytest.param("vodafone_api", _vodafone_detail, id="vodafone"),
    pytest.param("telekom_kategorie", _telekom_seite, id="telekom"),
    pytest.param("congstar_next", _congstar_seite, id="congstar"),
]


@pytest.mark.parametrize("methode,seite", BUENDELSEITEN)
@pytest.mark.parametrize("wert,erwartet", PREISFAELLE)
def test_preislesung_im_buendel(ohne_netz, methode, seite, wert, erwartet):
    lesen = geraete.ADAPTER[methode].lies_buendel
    saetze = lesen(seite(wert), "https://beispiel.invalid/x")
    gelesen = _gelesener_preis(saetze, "anschlusspreis")
    assert gelesen == erwartet
    if erwartet is None:
        assert gelesen is None


@pytest.mark.parametrize("wert,erwartet", PREISFAELLE)
def test_preislesung_o2(ohne_netz, wert, erwartet):
    lesen = geraete.ADAPTER["o2_katalog"].lies
    saetze = lesen(_o2_katalog(wert), "https://beispiel.invalid/x")
    if erwartet is None:
        assert saetze == []
    else:
        assert _gelesener_preis(saetze, "preis") == erwartet
