"""Klickliste aus dem Katalog: ein erkanntes neues Modell kommt ohne Handarbeit hinein.

Anlass: das iPhone Duo (bei fünf Anbietern gelistet) stand in keiner Klickliste und
bekam darum nie einen Einzelgerätepreis. Geprüft wird in einem Wegwerfordner mit
Kopien der echten Quellen und des Katalogs, einer kleinen Handliste und einem
Bestand, den der Test selbst schreibt (kein Datum, kein Netz).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from telco_radar.collect.geraete.klickliste_auto import (
    HOECHSTE_SEITEN_JE_ANBIETER,
    KlicklisteAutoFehler,
    leite_ab,
)
from telco_radar.collect.geraete.klickziele import (
    ErkundungszielFehler,
    lade_ziele,
)
from telco_radar.geraete_config import lade_katalog

WURZEL = Path(__file__).resolve().parents[1]
TAGESDATEI = Path("config") / "klick_tageslauf.yaml"
VF_DUO = "https://www.vodafone.de/privat/handys/iphone-duo.html"
VF_17_PRO = "https://www.vodafone.de/privat/handys/iphone-17-pro.html"
O2_DUO = (
    "https://www.o2online.de/e-shop/apple/apple-iphone-duo-{stufe}-nachthimmel-details"
    "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=24&tarif=o2-mobile-l"
)
EINS_UND_EINS_TARIFE = "https://mobile.1und1.de/smartphones-all-net-flat-l"


def _buendel(anbieter: str, sku: str, url: str, **mehr) -> dict:
    return {"anbieter": anbieter, "sku_id": sku, "quelle_url": url, **mehr}


@pytest.fixture
def wurzel(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("geraete_quellen.yaml", "geraete_katalog.yaml"):
        shutil.copy(WURZEL / "config" / name, tmp_path / "config" / name)
    hand = {
        "anbieter": [
            {
                "schluessel": "vodafone",
                "name": "Vodafone",
                "seiten": [
                    {
                        "geraet": "apple-iphone-17-pro",
                        "speicher_gb": 256,
                        "url": VF_17_PRO,
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
            {
                "schluessel": "1und1",
                "name": "1&1",
                "seiten": [
                    {
                        "geraet": "apple-iphone-17-pro",
                        "speicher_gb": 256,
                        "url": "https://mobile.1und1.de/iphone-17-pro",
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


def _auto_ziele(wurzel: Path) -> dict:
    ziele = lade_ziele(wurzel, TAGESDATEI, hoechste=None, auto=True)
    return {z.schluessel: z for z in ziele if z.schluessel.endswith("-auto")}


def test_erkanntes_modell_landet_in_der_klickliste(wurzel):
    _bestand(
        wurzel,
        [
            _buendel("Vodafone", "apple-iphone-duo-256gb-nachthimmel", VF_DUO),
            _buendel(
                "o2", "apple-iphone-duo-512gb-nachthimmel", O2_DUO.format(stufe="512gb")
            ),
            _buendel(
                "o2", "apple-iphone-duo-1024gb-nachthimmel", O2_DUO.format(stufe="1tb")
            ),
        ],
    )

    auto = _auto_ziele(wurzel)

    assert {s.geraet for s in auto["vodafone-auto"].seiten} == {"apple-iphone-duo"}
    assert auto["vodafone-auto"].seiten[0].adresse == VF_DUO
    assert [s.speicher_gb for s in auto["o2-auto"].seiten] == [512, 1024]
    assert auto["o2-auto"].karte == "o2"
    ohne = lade_ziele(wurzel, TAGESDATEI, hoechste=None)
    assert [z.schluessel for z in ohne] == ["vodafone", "o2", "1und1"]


def test_auto_erkanntes_modell_im_state_katalog_kommt_auch_hinein(wurzel):
    zusatz = {
        "geraete": [
            {
                "hersteller": "Google",
                "modell": "Pixel 12",
                "generation": 12,
                "speicher": [256],
                "auto": "2026-11-01",
            }
        ]
    }
    (wurzel / "data" / "state").mkdir(parents=True)
    (wurzel / "data/state/geraete_katalog_auto.json").write_text(
        json.dumps(zusatz), encoding="utf-8"
    )
    adresse = "https://www.vodafone.de/privat/handys/google-pixel-12.html"
    _bestand(wurzel, [_buendel("Vodafone", "google-pixel-12-256gb-schwarz", adresse)])

    auto = _auto_ziele(wurzel)

    assert [s.geraet for s in auto["vodafone-auto"].seiten] == ["google-pixel-12"]


def test_gegenprobe_was_schon_in_der_handliste_steht_kommt_nicht_doppelt(wurzel):
    _bestand(wurzel, [_buendel("Vodafone", "apple-iphone-17-pro-256gb-x", VF_17_PRO)])

    assert _auto_ziele(wurzel) == {}


def test_gegenprobe_tarifuebersicht_ist_keine_geraeteseite(wurzel):
    _bestand(
        wurzel,
        [_buendel("1&1", "apple-iphone-duo-256gb-sternenweiss", EINS_UND_EINS_TARIFE)],
    )

    assert _auto_ziele(wurzel) == {}


def test_gegenprobe_adresse_mit_anderer_speicherstufe_wird_verworfen(wurzel):
    _bestand(
        wurzel,
        [
            _buendel(
                "o2",
                "apple-iphone-duo-1024gb-sternenweiss",
                O2_DUO.format(stufe="256gb"),
            )
        ],
    )

    assert _auto_ziele(wurzel) == {}


def test_gegenprobe_kein_iphone_18_ohne_zusatz_aus_dem_nichts(wurzel):
    _bestand(wurzel, [_buendel("Vodafone", "apple-iphone-duo-256gb-x", VF_DUO)])

    katalog = lade_katalog(wurzel)
    seiten = leite_ab(wurzel, katalog, set())

    assert katalog.nach_id("apple-iphone-18") is None
    assert {s.geraet for s in seiten} == {"apple-iphone-duo"}


def test_gegenprobe_zubehoer_zaehlt_nicht_veraltete_buendel_schon(wurzel):
    """Zubehör liefert keine Seite. Ein veraltetes Bündel schon: es ist Quelle der
    Adresse, nur seine Preise zählen nicht (Prüfung PR 85, 10.11.2026)."""
    _bestand(
        wurzel,
        [
            _buendel(
                "Vodafone",
                "apple-airpods-pro-3-ohne-speicher-x",
                "https://www.vodafone.de/privat/handys/airpods-pro-3.html",
            ),
            _buendel(
                "Vodafone",
                "apple-iphone-duo-256gb-x",
                VF_DUO,
                pruefung="veraltet 16",
                abgerufen_am="2026-11-05",
            ),
        ],
    )

    seiten = _auto_ziele(wurzel)["vodafone-auto"].seiten

    assert [s.geraet for s in seiten] == ["apple-iphone-duo"]


def test_hoechstens_so_viele_seiten_je_anbieter(wurzel):
    stufen = [(256, "256gb"), (512, "512gb"), (1024, "1tb"), (2048, "2tb")]
    buendel = [
        _buendel(
            "o2", f"apple-iphone-duo-{gb}gb-nachthimmel", O2_DUO.format(stufe=text)
        )
        for gb, text in stufen
    ]
    _bestand(wurzel, buendel)
    gross = HOECHSTE_SEITEN_JE_ANBIETER
    assert len(_auto_ziele(wurzel)["o2-auto"].seiten) == len(stufen) <= gross

    katalog = lade_katalog(wurzel)
    viele = [
        _buendel(
            "Vodafone",
            f"apple-iphone-{n}-256gb-x",
            f"https://www.vodafone.de/privat/handys/iphone-{n}.html",
        )
        for n in (11, 12, 13, 14, 15, 16, 17, 18, 19, 20)
    ]
    _bestand(wurzel, viele)
    assert len(leite_ab(wurzel, katalog, set())) <= gross


def test_fehlender_bestand_ist_leer_kaputter_wirft(wurzel):
    assert _auto_ziele(wurzel) == {}

    pfad = wurzel / "data" / "state" / "geraete_tco.json"
    pfad.parent.mkdir(parents=True)
    pfad.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(KlicklisteAutoFehler):
        leite_ab(wurzel, lade_katalog(wurzel), set())
    with pytest.raises(ErkundungszielFehler):
        lade_ziele(wurzel, TAGESDATEI, hoechste=None, auto=True)
