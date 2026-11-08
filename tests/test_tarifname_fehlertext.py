"""Ein Fehlertext der Anbieter-API ist kein Tarifname.

Befund 08.11.2026 (Prüfung PR 67): im Export stand bei o2 (Galaxy S26 Plus, 256 GB)
als Tarif `https://www.o2online.de/api/shop?type=tariff&...&scheme=https: javax.net.ssl.
SSLHandshakeException: Remote host terminated the handshake (24 Mon.)`. Die Antwort der
Schnittstelle trug die Ausnahme im Feld `displayValue`, der Sammler übernahm sie als
Namen. Die Regel gilt für jeden Anbieter an der gemeinsamen Stelle: ein solcher Satz
ist ungültig, erscheint nicht als Preiszeile und wird mit Grund gezählt.
"""

from __future__ import annotations

import json

import pytest

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tarifname import tarifname_fehlergrund
from telco_radar.tco_model import Buendel, SimOnlyReferenz

HEUTE = "2026-11-08"
FEHLERNAME = (
    "https://www.o2online.de/api/shop?type=tariff&portalId=o2shop:66240500:"
    "privatkunden:o2-mobile-ul-m-plus-2026-on&variantName=Name&scheme=https: "
    "javax.net.ssl.SSLHandshakeException: Remote host terminated the handshake "
    "(24 Mon.)"
)
SKU = "samsung-galaxy-s26-plus-256gb-cobalt-violet"


def _satz(name: str, anbieter: str = "o2") -> dict:
    return {
        "anbieter": anbieter,
        "tarif_name": name,
        "sku_id": SKU,
        "tarif_slug": "o2-mobile-unlimited-m",
        "tarif_monatlich": 19.99,
        "geraet_zuzahlung": 7.0,
        "geraet_monatsrate": 51.5,
        "laufzeit_monate": 24,
        "anschlusspreis": 0.0,
    }


def _bestand() -> Tarifbestand:
    return Tarifbestand(
        [
            {
                "tarif_id": "o2:o2-mobile-unlimited-m",
                "anbieter": "o2",
                "name": "O2 Mobile Unlimited M",
                "grundgebuehr": 24.99,
                "buendel_slug": "o2-mobile-unlimited-m",
            }
        ]
    )


@pytest.mark.parametrize(
    "name",
    [
        FEHLERNAME,
        "java.lang.NullPointerException",
        "Tarif http://example.org/x",
        "javax.net.ssl.SSLException",
        "Fehler: IOException beim Lesen",
        "Traceback (most recent call last)",
    ],
)
def test_fehlertext_hat_einen_grund(name):
    assert tarifname_fehlergrund(name)


@pytest.mark.parametrize(
    "name",
    [
        "O2 Mobile Unlimited M Plus (24 Mon.)",
        "MagentaMobil XL",
        "Vodafone GigaMobil S",
        "Red+ Data",
        "congstar Allnet Flat 10 GB",
    ],
)
def test_echter_tarifname_hat_keinen_grund(name):
    assert tarifname_fehlergrund(name) is None


def test_rohsatz_mit_fehlertext_wird_keine_preiszeile():
    bilanz = aus_rohsaetzen(
        [_satz(FEHLERNAME), _satz("O2 Mobile Unlimited M (24 Mon.)")],
        _bestand(),
        HEUTE,
    )
    assert [b.tarif_name for b in bilanz.buendel] == ["O2 Mobile Unlimited M (24 Mon.)"]
    assert bilanz.ungueltig == 1
    assert sum(bilanz.ungueltig_gruende.values()) == 1
    assert bilanz.verworfen == 1


def test_fehlertext_gilt_fuer_jeden_anbieter():
    bilanz = aus_rohsaetzen(
        [_satz("MagentaMobil S: java.io.IOException", anbieter="Telekom")],
        _bestand(),
        HEUTE,
    )
    assert bilanz.buendel == []
    assert bilanz.ungueltig == 1


def test_buendel_und_referenz_verweigern_den_namen():
    with pytest.raises(ValueError, match="Tarifname"):
        Buendel(anbieter="o2", tarif_name=FEHLERNAME, sku_id=SKU)
    with pytest.raises(ValueError, match="Tarifname"):
        SimOnlyReferenz(anbieter="o2", tarif_name=FEHLERNAME)


def test_bestandssatz_mit_fehlertext_wird_beim_lesen_verworfen(tmp_path):
    pfad = tmp_path / "geraete_tco.json"
    gut = {
        "id": "buendel--o2--x--o2-mobile-unlimited-m-24-mon--24m",
        "anbieter": "o2",
        "tarif_name": "O2 Mobile Unlimited M (24 Mon.)",
    }
    schlecht = {"id": "buendel--o2--x--fehler--24m", "anbieter": "o2"}
    schlecht["tarif_name"] = FEHLERNAME
    pfad.write_text(
        json.dumps({"updated": HEUTE, "buendel": [gut, schlecht], "sim_only": []}),
        encoding="utf-8",
    )
    db = TcoDB(pfad)
    assert [e["id"] for e in db.buendel()] == [gut["id"]]
    assert db.verworfene_namen == {"o2": 1}
