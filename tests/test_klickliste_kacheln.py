"""Telekom-Produktseiten aus den Kacheln der Übersichten (20.11.2026), ohne Netz.

Befund 20.11.2026: Die feste Adresse ``apple-iphone-15/blau-128-gb`` leitete auf die
Markenübersicht um (iPhone 15 „nicht mehr angeboten“), obwohl die Übersicht das Gerät
als ``apple-iphone-15-erneuert/zufallsfarbe-128-gb`` führte; iPhone 14, Xiaomi 18 Pro
und 18 Pro Max hatten gar keine Seite. Die Fixture
``tests/fixtures/klickliste/telekom_uebersichten_20261120.json`` sind die echten fünf
Übersichten dieses Laufs (nur Titel, Speicher, Produktlink).
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml
from bestand_pfad import KACHELN, kachel_wurzel, lese_wurzel

from telco_radar.collect.geraete.klickergebnis import laufstatus
from telco_radar.collect.geraete.klickliste_kacheln import (
    seiten_aus_kacheln,
    verteile,
)
from telco_radar.collect.geraete.klickrohsatz import geraetepreis, rohsatz
from telco_radar.collect.geraete.klickziele import (
    TAGESDATEI,
    ErkundungszielFehler,
    lade_ziele,
)
from telco_radar.collect.geraete.telekom_liste import lies_listing
from telco_radar.geraete_config import lade_katalog
from telco_radar.geraete_model import Geraet, Katalog

WURZEL = Path(__file__).resolve().parents[1]
LISTING = WURZEL / "tests/fixtures/geraete/telekom_listing_rueckgabedeal_20261009.json"
TARIF_M = "MF_17791"
TARIFE = {"MF_17779", "MF_17785", "MF_17791", "MF_17797", "MF_17803"}
IPHONE_15 = "/shop/geraet/apple/apple-iphone-15-erneuert/zufallsfarbe-128-gb"
XIAOMI = {
    "xiaomi-18-pro": ("Xiaomi", "18 Pro", [256, 512]),
    "xiaomi-18-pro-max": ("Xiaomi", "18 Pro Max", [256, 512]),
}


@pytest.fixture(scope="module")
def daten() -> dict:
    return json.loads(KACHELN.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def katalog() -> Katalog:
    """Der Katalog des Schnappschusses (Oktober) und die zwei Xiaomi-Modelle, die
    seit November darin stehen."""
    alt = lade_katalog(lese_wurzel())
    neu = [Geraet(hersteller=h, modell=m, speicher=s) for h, m, s in XIAOMI.values()]
    assert [g.device_id for g in neu] == list(XIAOMI)
    return Katalog(geraete=[*alt.geraete, *neu])


def _tarif(url: str) -> str:
    return parse_qs(urlsplit(url).query)["tariffId"][0]


def test_iphone_15_kommt_mit_der_adresse_der_kachel(daten, katalog):
    seiten = seiten_aus_kacheln(daten, katalog).seiten
    iphone = [s for s in seiten if s["geraet"] == "apple-iphone-15"]

    assert {_tarif(s["url"]) for s in iphone} == TARIFE
    assert all(urlsplit(s["url"]).path == IPHONE_15 for s in iphone)
    assert {s["zustand"] for s in iphone} == {"refurbished"}
    assert {s["modell"] for s in iphone} == {"iPhone 15"}
    assert {s["speicher_gb"] for s in iphone} == {128}


def test_geraete_ohne_handliste_bekommen_je_tarif_eine_seite(daten, katalog):
    seiten = seiten_aus_kacheln(daten, katalog).seiten
    je_geraet: dict[str, set[str]] = {}
    for seite in seiten:
        je_geraet.setdefault(seite["geraet"], set()).add(_tarif(seite["url"]))

    for geraet in ("apple-iphone-14", "xiaomi-18-pro", "xiaomi-18-pro-max"):
        assert je_geraet[geraet] == TARIFE
    paare = [(s["url"].split("?")[0], _tarif(s["url"])) for s in seiten]
    assert len(paare) == len(set(paare))
    assert {s["zustand"] for s in seiten if s["geraet"] == "xiaomi-18-pro"} == {"neu"}


def test_unbekanntes_geraet_und_fremde_adresse_geben_keine_seite(daten, katalog):
    """iPhone 13 (Erneuert Basic) steht nicht im Katalog; eine Kachel ohne Produktlink
    (Adresse der Übersicht) ist keine Seite."""
    roh = copy.deepcopy(daten)
    (m,) = [u for u in roh["uebersichten"] if u["adresse"].endswith(TARIF_M)]
    m["saetze"].append({**m["saetze"][0], "url": m["adresse"]})

    seiten = seiten_aus_kacheln(roh, katalog).seiten

    assert not [s for s in seiten if "iphone-13" in s["url"]]
    assert all("/shop/geraet/" in s["url"] for s in seiten)


def test_nicht_gelesene_uebersicht_ist_luecke_nicht_leer(daten, katalog):
    roh = copy.deepcopy(daten)
    (m,) = [u for u in roh["uebersichten"] if u["adresse"].endswith(TARIF_M)]
    m.update(status="gestoert", grund="Abruf gestört (HTTP 403)")

    ergebnis = seiten_aus_kacheln(roh, katalog)

    assert ergebnis.luecken == [f"{m['adresse']}: Abruf gestört (HTTP 403)"]
    assert TARIF_M not in {_tarif(s["url"]) for s in ergebnis.seiten}
    assert ergebnis.seiten


def test_kachel_ohne_preis_liefert_ihre_seite(katalog):
    """Rechenprobe oder Rückgabedeal nehmen der Kachel den Satz, nicht die Seite."""
    url = "https://www.telekom.de/shop/geraet/google/google-pixel-10a/fog-128-gb"
    kachel = {"titel": "Google Pixel 10a 128 GB", "speicher_gb": 128}
    seite = {"liste": {"kacheln": [{**kachel, "url": f"{url}?tariffId=MF_17797"}]}}
    uebersicht = {"status": "gelesen", "saetze": [], "seiten": [seite]}

    (ergebnis,) = seiten_aus_kacheln({"uebersichten": [uebersicht]}, katalog).seiten

    assert ergebnis["geraet"] == "google-pixel-10a"
    assert ergebnis["url"] == f"{url}?tariffId=MF_17797"


def test_listing_nennt_jede_kachel_mit_produktlink_auch_mit_rueckgabedeal():
    echt = json.loads(LISTING.read_text(encoding="utf-8"))
    pfad = "/shop/geraet/apple/apple-iphone-17/lavendel-256-gb"
    seite = f'<a href="{pfad}?tariffId=MF_17791">Apple iPhone 17</a>'

    lesung = lies_listing([echt], seite, "https://www.telekom.de/shop/geraete")

    assert lesung.saetze == []
    assert lesung.kacheln == [
        {
            "titel": "Apple iPhone 17 256 GB",
            "speicher_gb": 256,
            "url": f"https://www.telekom.de{pfad}?tariffId=MF_17791",
        }
    ]


def test_verteile_reihum():
    assert verteile([1, 2, 3, 4, 5], 2) == [[1, 3, 5], [2, 4]]
    assert verteile([1], 3) == [[1], [], []]


def test_tagesdatei_verteilt_jede_kachelseite_genau_einmal(daten):
    ziele = lade_ziele(kachel_wurzel(), TAGESDATEI, hoechste=None, auto=True)
    telekom = [z for z in ziele if z.name == "Telekom"]

    assert [z.schluessel for z in telekom] == ["telekom"] + [
        f"telekom-{n}" for n in range(2, 12)
    ]
    adressen = [s.adresse for z in telekom for s in z.seiten]
    assert len(adressen) == len(set(adressen))
    kacheln = {s["url"] for u in daten["uebersichten"] for s in u["saetze"]}
    assert set(adressen) <= kacheln
    groessen = [len(z.seiten) for z in telekom]
    assert max(groessen) - min(groessen) <= 1
    assert all(z.seitengrund is None for z in telekom)


@pytest.fixture
def wurzel(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    for name in (
        "geraete_quellen.yaml",
        "geraete_katalog.yaml",
        "klick_tageslauf.yaml",
    ):
        shutil.copy(WURZEL / "config" / name, tmp_path / "config" / name)
    return tmp_path


def test_ohne_uebersicht_nennt_der_lauf_den_grund(wurzel):
    ziele = lade_ziele(wurzel, TAGESDATEI, hoechste=None)
    telekom = [z for z in ziele if z.name == "Telekom"]

    assert telekom and all(z.seiten == () for z in telekom)
    grund = telekom[0].seitengrund
    assert grund is not None
    assert "keine Seite aus der Übersicht telekom" in grund
    assert laufstatus([], grund) == ("nicht_gelesen", grund)


def test_seiten_und_kacheln_zugleich_sind_ein_fehler(wurzel):
    pfad = wurzel / TAGESDATEI
    roh = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    eintrag = next(e for e in roh["anbieter"] if e["schluessel"] == "telekom-2")
    eintrag["seiten"] = [
        {"geraet": "apple-iphone-17", "url": "https://www.telekom.de/x"}
    ]
    pfad.write_text(yaml.safe_dump(roh, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ErkundungszielFehler, match="zugleich"):
        lade_ziele(wurzel, TAGESDATEI, hoechste=None)


def _erfasst() -> dict:
    return {
        "status": "erfasst",
        "variante": {"speicher": "128 GB", "tarif": "MagentaMobil M", "laufzeit": 24},
        "werte": {"anzahlung": 1.0, "rate": 20.5, "ratenzahl": 24},
    }


@pytest.mark.parametrize(
    ("zustand", "sku", "einzelpreis"),
    [
        ("refurbished", "apple-iphone-15-128gb-ohne-farbe-refurbished", False),
        (None, "apple-iphone-15-128gb-ohne-farbe", True),
    ],
)
def test_zustand_der_seite_geht_in_den_rohsatz(katalog, zustand, sku, einzelpreis):
    seite = {"geraet": "apple-iphone-15", "adresse": "https://www.telekom.de/x"}
    if zustand is not None:
        seite["zustand"] = zustand
    daten = {"name": "Telekom", "datum": "2026-11-20"}

    satz = rohsatz(_erfasst(), seite, daten, katalog)

    assert isinstance(satz, dict)
    assert satz["sku_id"] == sku
    assert satz["zustand"] == (zustand or "neu")
    assert (geraetepreis(_erfasst(), seite, daten, katalog) is not None) is einzelpreis
