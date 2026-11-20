"""Klick-Tageslauf für 1&1: Seiten aus der Geräteübersicht (seit 20.11.2026).

Bis zum 20.11.2026 standen 42 Seiten von Hand in der Tagesdatei. Jetzt kommen sie aus
den Kacheln der Geräteübersicht ``https://mobile.1und1.de/smartphones`` in der
Ergebnisdatei des letzten Laufs (``klickliste_kacheln``), reihum auf die Einträge
``1und1`` und ``1und1-2``. Die Fixture ``einsundeins_smartphones_20261120.html`` sind
die 41 Kacheln dieses Tages; der Katalog des Schnappschusses kennt 39 davon (ohne
Xiaomi 18 Pro/Pro Max). Der Kanarienwert ist der Modellname in der Schreibweise der
Kachel (am 20.11.2026 an allen 41 Produktseiten gegen ``aria-label`` geprüft).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml
from bestand_pfad import WURZEL, lese_wurzel, verlinke_neben_data

from telco_radar.collect.geraete.klickraster import einsundeins_saetze
from telco_radar.collect.geraete.klickziele import (
    TAGESDATEI,
    ErkundungszielFehler,
    lade_ziele,
)

UEBERSICHT = "https://mobile.1und1.de/smartphones"
FIXTURE = WURZEL / "tests/fixtures/klickcrawler/einsundeins_smartphones_20261120.html"
MODELLE = {
    "apple-iphone-17-pro": "iPhone 17 Pro",
    "fairphone-6": "(Gen. 6)",
    "google-pixel-10a": "Pixel 10a",
    "samsung-galaxy-s26-plus": "Galaxy S26+",
    "xiaomi-redmi-17c": "REDMI 17C",
}


def _ziele(wurzel: Path) -> list:
    return [z for z in lade_ziele(wurzel, TAGESDATEI, hoechste=None) if z.name == "1&1"]


@pytest.fixture(scope="module")
def mit_uebersicht(tmp_path_factory) -> list:
    """Eine eigene Wurzel (``lese_wurzel`` ist geteilt und bleibt unverändert) mit dem
    Auto-Katalog des Schnappschusses und der Ergebnisdatei der Übersicht."""
    wurzel = tmp_path_factory.mktemp("wurzel")
    shutil.copytree(lese_wurzel() / "data", wurzel / "data")
    verlinke_neben_data(wurzel)
    saetze = einsundeins_saetze(FIXTURE.read_text(encoding="utf-8"), UEBERSICHT)
    daten = {
        "anbieter": "1und1",
        "name": "1&1",
        "datum": "2026-11-20",
        "seiten": [],
        "uebersichten": [
            {
                "adresse": UEBERSICHT,
                "status": "gelesen",
                "vollstaendig": True,
                "saetze": saetze,
            }
        ],
    }
    ordner = wurzel / "data" / "state" / "klick"
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "1und1.json").write_text(json.dumps(daten), encoding="utf-8")
    return _ziele(wurzel)


def test_seiten_aus_der_geraeteuebersicht_auf_zwei_eintraege(mit_uebersicht):
    seiten = [s for z in mit_uebersicht for s in z.seiten]

    assert [z.schluessel for z in mit_uebersicht] == ["1und1", "1und1-2"]
    assert [len(z.seiten) for z in mit_uebersicht] == [20, 19]
    assert {urlsplit(s.adresse).hostname for s in seiten} == {"mobile.1und1.de"}
    assert len({s.geraet for s in seiten}) == len(seiten) == 39
    assert {z.seitengrund for z in mit_uebersicht} == {None}


def test_modellname_der_kachel_ist_der_kanarienwert(mit_uebersicht):
    modelle = {s.geraet: s.modell for z in mit_uebersicht for s in z.seiten}

    assert {g: modelle[g] for g in MODELLE} == MODELLE


def test_gegenprobe_ohne_ergebnisdatei_keine_seite_mit_grund():
    ziele = _ziele(lese_wurzel())

    assert [len(z.seiten) for z in ziele] == [0, 0]
    assert all("keine Ergebnisdatei" in (z.seitengrund or "") for z in ziele)


@pytest.fixture
def wurzel(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    for name in (
        "geraete_quellen.yaml",
        "geraete_katalog.yaml",
        "klick_erkundung.yaml",
    ):
        shutil.copy(WURZEL / "config" / name, tmp_path / "config" / name)
    return tmp_path


def _setze_modell(wurzel: Path, wert: object) -> None:
    pfad = wurzel / "config" / "klick_erkundung.yaml"
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    daten["anbieter"][0]["seiten"][0]["modell"] = wert
    pfad.write_text(yaml.safe_dump(daten, allow_unicode=True), encoding="utf-8")


def test_modell_aus_der_erkundung_landet_im_seitenziel(wurzel):
    _setze_modell(wurzel, "Apple iPhone 17 Pro")

    ziele = lade_ziele(wurzel)

    assert ziele[0].seiten[0].modell == "Apple iPhone 17 Pro"
    assert ziele[0].seiten[1].modell != "Apple iPhone 17 Pro"


@pytest.mark.parametrize("wert", ["", "  ", None, 17])
def test_leeres_modell_ist_ein_fehler(wurzel, wert):
    _setze_modell(wurzel, wert)

    with pytest.raises(ErkundungszielFehler, match=r"seiten\[0\]: modell fehlt"):
        lade_ziele(wurzel)
