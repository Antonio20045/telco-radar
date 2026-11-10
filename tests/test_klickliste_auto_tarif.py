"""Klickliste aus dem Katalog: bei Telekom gehört der Tarif zur Seite.

Befund 09.11.2026 (Original-Prüfung iPhone Duo): Telekom bietet das Duo mit 24 Raten in
allen fünf MagentaMobil-Stufen an, der Export hatte 24 Raten nur bei L. Ursache: die
abgeleitete Klickliste schlug je (Anbieter, Gerät, Stufe) genau eine Adresse vor, die
erste im Bestand, und das war die L-Seite. Eine Telekom-Produktseite zeigt aber nur den
Tarif ihrer Startadresse (``tariffId``); die übrigen vier Tarife kamen nur über die
Bündelübersicht, und die zeigt ausschließlich 36 Raten.

Die Fixture ``telekom_duo_bestand_0911.json`` ist der echte Auszug aus
``data/state/geraete_tco.json`` (Telekom, iPhone Duo, 36 Monate, Stand 09.11.2026):
L mit drei Stufen und nach dem Klicken veränderten Adressen, M, S, XL, XS mit 256 GB.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from telco_radar.collect.geraete.klickliste_auto import (
    HOECHSTE_SEITEN_JE_ANBIETER,
    leite_ab,
)
from telco_radar.collect.geraete.klickziele import lade_ziele
from telco_radar.geraete_config import lade_katalog

WURZEL = Path(__file__).resolve().parents[1]
FIXTURE = WURZEL / "tests" / "fixtures" / "klickliste" / "telekom_duo_bestand_0911.json"
TAGESDATEI = Path("config") / "klick_tageslauf.yaml"
TELEKOM_TARIFE = {
    "MF_17779": "XS",
    "MF_17785": "S",
    "MF_17791": "M",
    "MF_17797": "L",
    "MF_17803": "XL",
}
TELEKOM_SEITE = (
    "https://www.telekom.de/shop/geraet/apple/{geraet}/{variante}?tariffId={tarif}"
    "&categoryId=smartphones&forwardTradeInApplied=false"
)
O2_DUO = (
    "https://www.o2online.de/e-shop/apple/apple-iphone-duo-256gb-nachthimmel-details"
    "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=24&tarif={tarif}"
)


def _tarif_von(url: str) -> str:
    return parse_qs(urlsplit(url).query)["tariffId"][0]


@pytest.fixture
def wurzel(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("geraete_quellen.yaml", "geraete_katalog.yaml"):
        shutil.copy(WURZEL / "config" / name, tmp_path / "config" / name)
    hand = {
        "anbieter": [
            {
                "schluessel": "telekom",
                "name": "Telekom",
                "seiten": [
                    {
                        "geraet": "apple-iphone-17-pro",
                        "speicher_gb": 256,
                        "url": TELEKOM_SEITE.format(
                            geraet="apple-iphone-17-pro",
                            variante="tiefblau-256-gb",
                            tarif="MF_17791",
                        ),
                    }
                ],
            },
            {
                "schluessel": "o2",
                "name": "o2",
                "seiten": [
                    {
                        "geraet": "apple-iphone-17-pro",
                        "speicher_gb": 256,
                        "url": "https://www.o2online.de/e-shop/apple/apple-iphone-17-pro-256gb-x-details",
                    }
                ],
            },
        ]
    }
    (tmp_path / TAGESDATEI).write_text(yaml.safe_dump(hand), encoding="utf-8")
    return tmp_path


def _bestand(wurzel: Path, buendel: list[dict]) -> None:
    pfad = wurzel / "data" / "state" / "geraete_tco.json"
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps({"buendel": buendel}), encoding="utf-8")


def _echter_bestand() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["buendel"]


def test_telekom_duo_bekommt_je_tarif_eine_seite(wurzel):
    _bestand(wurzel, _echter_bestand())

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert {s.geraet for s in seiten} == {"apple-iphone-duo"}
    assert {_tarif_von(s.url) for s in seiten} == set(TELEKOM_TARIFE)
    assert len(seiten) == len(TELEKOM_TARIFE)
    assert {s.speicher_gb for s in seiten} == {256}


def test_ziele_der_klickliste_tragen_alle_fuenf_tarife(wurzel):
    _bestand(wurzel, _echter_bestand())

    ziele = lade_ziele(wurzel, TAGESDATEI, hoechste=None, auto=True)
    auto = {z.schluessel: z for z in ziele}["telekom-auto"]

    assert {_tarif_von(s.adresse) for s in auto.seiten} == set(TELEKOM_TARIFE)
    assert all(s.geraet == "apple-iphone-duo" for s in auto.seiten)


def test_jede_tarifseite_ist_die_kleinste_stufe_mit_ihrem_tarif(wurzel):
    _bestand(wurzel, _echter_bestand())

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    for seite in seiten:
        assert "nachthimmel-256-gb" in seite.url
        assert f"tariffId={_tarif_von(seite.url)}" in seite.url


def test_gegenprobe_ein_tarif_im_bestand_bleibt_eine_seite(wurzel):
    nur_l = [b for b in _echter_bestand() if "tariffId=MF_17797" in b["quelle_url"]]
    assert len(nur_l) == 4
    _bestand(wurzel, nur_l)

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert [(s.speicher_gb, _tarif_von(s.url)) for s in seiten] == [(256, "MF_17797")]


def test_gegenprobe_andere_anbieter_bleiben_eine_seite_je_stufe(wurzel):
    """o2 trägt den Tarif auch in der Adresse, die Liste bleibt dort unverändert."""
    _bestand(
        wurzel,
        [
            {
                "anbieter": "o2",
                "sku_id": "apple-iphone-duo-256gb-nachthimmel",
                "quelle_url": O2_DUO.format(tarif=tarif),
            }
            for tarif in ("o2-mobile-s", "o2-mobile-m", "o2-mobile-l")
        ],
    )

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert [(s.anbieter, s.geraet, s.speicher_gb) for s in seiten] == [
        ("o2", "apple-iphone-duo", 256)
    ]
    assert seiten[0].url == O2_DUO.format(tarif="o2-mobile-s")


def test_die_grenze_zaehlt_geraete_und_stufen_nicht_tarife(wurzel):
    """Fünf Tarifseiten eines Geräts belegen einen Platz, nicht fünf."""
    bestand = _echter_bestand()
    for n in range(11, 11 + HOECHSTE_SEITEN_JE_ANBIETER + 2):
        for tarif in TELEKOM_TARIFE:
            bestand.append(
                {
                    "anbieter": "Telekom",
                    "sku_id": f"apple-iphone-{n}-256gb-x",
                    "quelle_url": TELEKOM_SEITE.format(
                        geraet=f"apple-iphone-{n}", variante="x-256-gb", tarif=tarif
                    ),
                }
            )
    _bestand(wurzel, bestand)

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    plaetze = {(s.geraet, s.speicher_gb) for s in seiten}
    assert 0 < len(plaetze) <= HOECHSTE_SEITEN_JE_ANBIETER
    assert len(seiten) == len(plaetze) * len(TELEKOM_TARIFE)
    for geraet, stufe in plaetze:
        tarife = {
            _tarif_von(s.url)
            for s in seiten
            if (s.geraet, s.speicher_gb) == (geraet, stufe)
        }
        assert tarife == set(TELEKOM_TARIFE)
