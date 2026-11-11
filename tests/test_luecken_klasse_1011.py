"""Zwei Fehlerarten der Nachprüfung vom 10.11.2026 (PR 89, Telekom AirPods 5).

(1) „Bei Telekom nicht im Angebot (Übersicht ganz gelesen)“ stand bei den AirPods 5, die
der Telekom-Zubehörshop für 144 EUR lieferte: die gelesene Übersicht ist die Handyseite
und belegt nichts über Zubehör, Tablets oder Uhren. Der Satz gilt nur für Klassen, die
die Übersicht des Anbieters abdeckt (``uebersicht_klassen`` in der Config); sonst ist es
eine Messlücke („Noch nicht erfasst“).

(2) „nur mit 256 GB gelesen“ las sich wie eine Lücke (o2 iPhone Air 512 GB ist in einer
anderen Farbe bestellbar). Der Satz nennt die Messlücke: „noch nicht erfasst“.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.analyze.klick_erfassung import (
    SATZ_NICHT_IM_ANGEBOT,
    SATZ_SPEICHER,
    fuer_modell,
)
from telco_radar.analyze.klick_zusammenfuehrung import zusammenfuehren
from telco_radar.geraete_config import lade_katalog
from telco_radar.report.geraete_luecken import (
    NICHT_IM_ANGEBOT,
    NOCH_NICHT_ERFASST,
    fehlen_im_paar,
)

ROOT = Path(__file__).resolve().parent.parent
TAG = "2026-11-10"
AIRPODS, WATCH, TAB = "apple-airpods-5", "apple-watch-se-3", "samsung-galaxy-tab-a11"
BUDS, TELEFON, DUO = (
    "google-pixel-buds-pro-2",
    "apple-iphone-17-pro",
    "apple-iphone-duo",
)


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _telekom_datei() -> dict:
    """Eine ganz gelesene Übersicht, in der nur das iPhone 17 steht."""
    satz = {
        "titel": "Apple iPhone 17 256 GB",
        "speicher_gb": 256,
        "tarif_name": "MagentaMobil M",
        "tarif_slug": "MF_17791",
        "tarif_monatlich": 49.95,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 40.0,
        "anschlusspreis": 39.95,
        "laufzeit_monate": 36,
        "url": "https://www.telekom.de/shop/geraet/apple/apple-iphone-17/x-256-gb",
    }
    uebersicht = {
        "adresse": "https://www.telekom.de/shop/geraete/smartphones?tariffId=MF_17791",
        "status": "gelesen",
        "grund": None,
        "saetze": [satz],
        "seiten": [],
        "vollstaendig": True,
        "unvollstaendig": None,
    }
    return {
        "anbieter": "telekom",
        "name": "Telekom",
        "karte": "telekom.yaml",
        "datum": TAG,
        "format": 1,
        "laufstatus": "gelesen",
        "grund": None,
        "seiten": [],
        "uebersichten": [uebersicht],
    }


@pytest.fixture
def erfassung(katalog, tmp_path) -> dict[str, str]:
    """Der Weg der Produktion: Ergebnisdatei im Ordner, Klassen aus der Config."""
    (tmp_path / "telekom.json").write_text(json.dumps(_telekom_datei()), "utf-8")
    zug = zusammenfuehren([], tmp_path, ROOT, katalog, TAG, lambda sku: ("", None))
    return zug.erfassung


def test_smartphone_uebersicht_belegt_nichts_ueber_zubehoer(erfassung):
    """(1) Rot gegen den Stand davor: AirPods, Uhr und Tablet bekamen den Satz."""
    satz = SATZ_NICHT_IM_ANGEBOT.format(anbieter="Telekom", datum="10.11.2026")
    assert erfassung[f"Telekom|{TELEFON}"] == satz
    for nicht_telefon in (AIRPODS, BUDS, WATCH, TAB):
        assert f"Telekom|{nicht_telefon}" not in erfassung, nicht_telefon


def test_nicht_telefon_ist_in_der_zeile_noch_nicht_erfasst(erfassung):
    """Durch alle Schichten bis in die Zeile der Bündelliste."""

    def kurz(device_id: str) -> str:
        modell = {"id": "x", "device_id": device_id, "speicher": None, "karten": []}
        modell["erfassung"] = fuer_modell(erfassung, modell, TAG)
        satz = {"zeilen": [], "fremd": [], "gesperrt": []}
        zeilen = fehlen_im_paar(modell, satz, "m", 24, {}, 24)
        return {z["anbieter"]: z["kurz"] for z in zeilen}["Telekom"]

    assert kurz(TELEFON) == NICHT_IM_ANGEBOT
    assert kurz(AIRPODS) == NOCH_NICHT_ERFASST


def test_ohne_klassenangabe_deckt_die_uebersicht_nichts_ab(katalog, tmp_path):
    """Fail-closed: ein Anbieter ohne ``uebersicht_klassen`` bekommt keinen Satz."""
    (tmp_path / "telekom.json").write_text(json.dumps(_telekom_datei()), "utf-8")
    ohne = tmp_path / "ohne"
    ohne.mkdir()
    zug = zusammenfuehren([], tmp_path, ohne, katalog, TAG, lambda sku: ("", None))
    assert not any("nicht im Angebot" in satz for satz in zug.erfassung.values())


def test_config_nennt_die_klassen_der_uebersichten():
    from telco_radar import geraete_klasse as klasse
    from telco_radar.collect.geraete.klickziele import uebersicht_klassen

    klassen = uebersicht_klassen(ROOT)
    assert klassen == {
        "Telekom": frozenset({klasse.TELEFON}),
        "1&1": frozenset({klasse.TELEFON}),
    }
    assert all(k <= klasse.KLASSEN for k in klassen.values())


def test_klasse_folgt_aus_dem_namen_nicht_aus_dem_geraet(katalog):
    from telco_radar import geraete_klasse as klasse

    erwartet = {
        AIRPODS: klasse.AUDIO,
        BUDS: klasse.AUDIO,
        WATCH: klasse.UHR,
        TAB: klasse.TABLET,
        "apple-ipad-pro-11-2025": klasse.TABLET,
    }
    for device_id, art in erwartet.items():
        assert klasse.geraeteklasse(device_id) == art
    ids = {g.device_id for g in katalog.geraete}
    telefone = {i for i in ids if klasse.geraeteklasse(i) == klasse.TELEFON}
    assert {TELEFON, DUO, "google-pixel-11-pro-fold"} <= telefone
    assert not telefone & set(erwartet)
    assert len(telefone) > len(ids) // 2


def test_speichersatz_benennt_die_messluecke():
    """(2) Rot gegen den Stand davor: „nur mit 256 GB gelesen“."""
    satz = SATZ_SPEICHER.format(anbieter="o2", speicher="256 GB", datum="10.11.2026")
    assert satz == "Bei o2 noch nicht erfasst (gelesen: 256 GB, 10.11.2026)"
    assert "nur mit" not in satz


def test_speichersatz_in_der_zeile_ist_als_messluecke_erkennbar():
    satz = SATZ_SPEICHER.format(anbieter="o2", speicher="256 GB", datum="10.11.2026")
    modell = {"id": "x", "device_id": "apple-iphone-air", "speicher": 512, "karten": []}
    modell["erfassung"] = fuer_modell({"o2|apple-iphone-air": satz}, modell, TAG)
    zeilen = fehlen_im_paar(
        modell, {"zeilen": [], "fremd": [], "gesperrt": []}, "m", 24, {}, 24
    )
    (zeile,) = [z for z in zeilen if z["anbieter"] == "o2"]
    assert zeile["kurz"] == f"{NOCH_NICHT_ERFASST} (gelesen: 256 GB)"
    assert zeile["satz"] == satz
    assert zeile["kurz"].startswith(NOCH_NICHT_ERFASST)
