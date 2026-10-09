"""Klick-Tageslauf für 1&1: alle 35 Geräte der Übersicht, die im Katalog stehen.

Jede Adresse steht wörtlich im Bestand (``geraete_db.json`` des Schnappschusses);
``modell`` je Seite ersetzt den Katalognamen im Kanarienwert, wo 1&1 das Gerät
anders nennt.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml
from bestand_pfad import WURZEL, ZUSTAND, lese_wurzel

from telco_radar.collect.geraete.klickziele import (
    TAGESDATEI,
    ErkundungszielFehler,
    lade_ziele,
)

ALTE_SEITEN = [
    ("apple-iphone-17-pro", "https://mobile.1und1.de/iphone-17-pro"),
    ("samsung-galaxy-s26", "https://mobile.1und1.de/samsung-galaxy-s26"),
    ("apple-iphone-17", "https://mobile.1und1.de/iphone-17"),
    ("apple-iphone-17-pro-max", "https://mobile.1und1.de/iphone-17-pro-max"),
    ("samsung-galaxy-s26-ultra", "https://mobile.1und1.de/samsung-galaxy-s26-ultra"),
    ("google-pixel-11", "https://mobile.1und1.de/google-pixel-11"),
]
ANBIETERNAMEN = {
    "fairphone-6": "Fairphone (Gen. 6)",
    "samsung-galaxy-s26-plus": "Samsung Galaxy S26+",
    "xiaomi-redmi-note-17": "Xiaomi REDMI Note 17 5G",
    "xiaomi-redmi-note-17-pro": "Xiaomi REDMI Note 17 Pro 5G",
    "xiaomi-redmi-note-17-pro-max": "Xiaomi REDMI Note 17 Pro Max 5G",
}


@pytest.fixture(scope="module")
def einsundeins():
    ziele = lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
    return {z.schluessel: z for z in ziele}["1und1"]


def _bestandsadressen() -> set[str]:
    db = json.loads((ZUSTAND / "geraete_db.json").read_text(encoding="utf-8"))
    return {
        e.get("quelle_url")
        for e in db["listungen"]
        if isinstance(e, dict) and e.get("quelle_url")
    }


def _nicht_im_bestand(adressen: list[str]) -> list[str]:
    bestand = _bestandsadressen()
    return [a for a in adressen if a not in bestand]


def test_1und1_liest_alle_35_geraete_der_uebersicht(einsundeins):
    seiten = einsundeins.seiten

    assert len(seiten) == 35
    assert {urlsplit(s.adresse).hostname for s in seiten} == {"mobile.1und1.de"}
    assert len({s.geraet for s in seiten}) == 35
    assert [(s.geraet, s.adresse) for s in seiten[:6]] == ALTE_SEITEN
    assert all(s.speicher_gb == 256 for s in seiten[:6])


def test_jede_1und1_adresse_steht_woertlich_im_bestand(einsundeins):
    adressen = [s.adresse for s in einsundeins.seiten]
    erfunden = "https://mobile.1und1.de/iphone-99-pro"

    assert _nicht_im_bestand(adressen) == []
    assert _nicht_im_bestand([*adressen, erfunden]) == [erfunden]


def test_anbietername_ersetzt_den_katalognamen_im_kanarienwert(einsundeins):
    modelle = {s.geraet: s.modell for s in einsundeins.seiten}

    assert {g: modelle[g] for g in ANBIETERNAMEN} == ANBIETERNAMEN
    assert modelle["apple-iphone-17-pro"] == "iPhone 17 Pro"
    assert modelle["google-pixel-10a"] == "Pixel 10a"


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
