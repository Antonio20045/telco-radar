"""Telekom-Übersicht im Klick-Tageslauf (Pitch 4, Schnitt 2).

Der Klick-Tageslauf liest für die Telekom vor den Produktseiten die Smartphone-Übersicht
je Tarif (``uebersichten:`` in ``config/klick_tageslauf.yaml``) im echten Browser, über
dasselbe Tor und dieselbe Wache wie eine Produktseite, und gibt ``page.content()`` an
``telekom.lies_buendel``. ``klickrohsatz.ausbeute`` macht daraus Rohsätze der Quelle
``klick``. Die Übersicht ist die gespeicherte echte Antwort
``tests/fixtures/geraete/telekom_kategorie_buendel_magentamobil_s.html.gz``
(MagentaMobil S, 08.09.2026), ausgeliefert von einem lokalen Server auf 127.0.0.1;
fremde Hosts sperrt robots.txt im Test, es geht nichts ins Netz.
"""

from __future__ import annotations

import dataclasses
import gzip
from datetime import UTC, datetime

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import WURZEL
from klickserver import Antwort, html, klickserver

from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicklauf import (
    LAUF_GELESEN,
    LAUF_GESTOERT,
    Klicklauf,
    abruf_gestoert,
)
from telco_radar.collect.geraete.klickrohsatz import (
    LUECKE_GERAET,
    LUECKE_SEITE,
    QUELLE,
    ausbeute,
)
from telco_radar.collect.geraete.klicktageslauf import (
    GRUND_NACH_STOERUNG,
    MINDESTZEIT_SEITE_S,
    fahre,
)
from telco_radar.collect.geraete.klicktor import Hostschleuse
from telco_radar.collect.geraete.klickuebersicht import lies_uebersicht
from telco_radar.collect.geraete.klickziele import (
    TAGESDATEI,
    ErkundungszielFehler,
    lade_ziele,
)
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import lade_katalog

FIXTURE = (
    WURZEL / "tests/fixtures/geraete/telekom_kategorie_buendel_magentamobil_s.html.gz"
)
PFAD = "/shop/geraete/smartphones?tariffId=MF_17785"
JETZT = datetime(2026, 10, 9, 5, 0, tzinfo=UTC)
HEUTE = "2026-10-09"
OFFEN = "User-agent: *\nDisallow:\n"
ZU = "User-agent: *\nDisallow: /\n"
UEBERSICHT_M = "https://www.telekom.de/shop/geraete/smartphones?tariffId=MF_17791"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.fixture(scope="module")
def karte():
    return lade_klickkarte(WURZEL / "config" / "klickkarten" / "telekom.yaml")


@pytest.fixture(scope="module")
def telekom():
    ziele = lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
    return next(z for z in ziele if z.schluessel == "telekom")


def _robots(url: str) -> tuple[int, str]:
    """Nur der lokale Server ist offen; jeder fremde Host bleibt zu."""
    return 200, OFFEN if "127.0.0.1" in url else ZU


def _lies(chromium, karte, adresse: str) -> dict:
    waechter = RobotsWaechter(hole=_robots)
    schleuse = Hostschleuse(waechter, lambda: JETZT)
    return lies_uebersicht(
        chromium, adresse, karte, waechter, lambda: JETZT, schleuse=schleuse
    )


def _fixture_antwort(pfad: str) -> Antwort:
    if pfad == PFAD:
        return html(gzip.open(FIXTURE, "rb").read().decode("utf-8", "replace"))
    return html("", 404)


def test_uebersicht_im_browser_ergibt_rohsatz_pixel_11_pro(chromium, karte, katalog):
    with klickserver(_fixture_antwort) as server:
        ergebnis = _lies(chromium, karte, server.adresse(PFAD))
    assert ergebnis["status"] == LAUF_GELESEN, ergebnis["grund"]
    assert ergebnis["adresse"].endswith(PFAD)
    assert len(ergebnis["saetze"]) == 9
    assert ergebnis["beleg"] == {
        "seite": ergebnis["adresse"],
        "zeitpunkt": "2026-10-09T05:00:00Z",
    }
    daten = {
        "name": "Telekom",
        "datum": HEUTE,
        "seiten": [],
        "uebersichten": [ergebnis],
    }
    aus = ausbeute(daten, katalog)
    pixel = [
        s
        for s in aus.rohsaetze
        if s["device_id"] == "google-pixel-11-pro" and s["speicher_gb"] == 256
    ]
    assert len(pixel) == 1
    (satz,) = pixel
    assert satz["tarif_name"] == "MagentaMobil S"
    assert satz["laufzeit_monate"] == 36
    assert satz["geraet_zuzahlung"] == 99.0
    assert satz["geraet_monatsrate"] == 28.3
    assert satz["tarif_monatlich"] == 39.95
    assert satz["anschlusspreis"] == 39.95
    assert satz["quelle"] == satz["quelle_art"] == QUELLE
    assert satz["abgerufen_am"] == HEUTE
    assert "/shop/geraet/google/google-pixel-11-pro/" in satz["quelle_url"]
    assert satz["sku_id"].startswith("google-pixel-11-pro")


def test_seite_ohne_zustand_ist_leer_ohne_saetze(chromium, karte):
    with klickserver(lambda p: html("<html><body>Kein Zustand</body></html>")) as s:
        ergebnis = _lies(chromium, karte, s.adresse(PFAD))
    assert ergebnis["status"] == "leer"
    assert "__INITIAL_STATE__" in ergebnis["grund"]
    assert ergebnis["saetze"] == []


def _uebersicht(saetze: list[dict], status: str = LAUF_GELESEN) -> dict:
    return {
        "adresse": UEBERSICHT_M,
        "status": status,
        "grund": None,
        "saetze": saetze,
        "beleg": {"seite": UEBERSICHT_M, "zeitpunkt": "2026-10-09T05:00:00Z"},
    }


def _satz(titel: str, gb: int | None = 256) -> dict:
    return {
        "titel": titel,
        "speicher_gb": gb,
        "tarif_name": "MagentaMobil M",
        "tarif_slug": "MF_17791",
        "tarif_monatlich": 49.95,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 40.0,
        "anschlusspreis": 39.95,
        "laufzeit_monate": 36,
        "url": "https://www.telekom.de/shop/geraet/apple/apple-iphone-18-pro/x-256-gb",
    }


def test_auto_katalog_und_unbekannter_titel_als_luecke(katalog):
    saetze = [_satz("iPhone 18 Pro 256 GB kosmisch"), _satz("Beispielfon Z9 256 GB")]
    gestoert = _uebersicht([], LAUF_GESTOERT)
    daten = {
        "name": "Telekom",
        "datum": HEUTE,
        "seiten": [],
        "uebersichten": [_uebersicht(saetze), gestoert],
    }
    aus = ausbeute(daten, katalog)
    assert [s["device_id"] for s in aus.rohsaetze] == ["apple-iphone-18-pro"]
    assert aus.rohsaetze[0]["quelle_url"] == _satz("")["url"]
    assert aus.luecken[LUECKE_GERAET] == 1
    assert aus.luecken[LUECKE_SEITE] == 1


def test_tagesdatei_nennt_die_uebersicht_wortlich_aus_den_quellen(telekom):
    assert telekom.uebersichten[0] == UEBERSICHT_M


def test_zusammengesetzte_uebersicht_wird_abgelehnt(tmp_path):
    wurzel = lese_wurzel()
    (tmp_path / "config").mkdir()
    for name in ("geraete_quellen.yaml", "geraete_katalog.yaml"):
        (tmp_path / "config" / name).symlink_to(wurzel / "config" / name)
    text = (wurzel / TAGESDATEI).read_text(encoding="utf-8")
    falsch = text.replace(UEBERSICHT_M, UEBERSICHT_M + "&itemPerPage=96")
    (tmp_path / TAGESDATEI).write_text(falsch, encoding="utf-8")
    with pytest.raises(ErkundungszielFehler, match="uebersichten"):
        lade_ziele(tmp_path, TAGESDATEI, hoechste=None)


class _Uhr:
    def __init__(self) -> None:
        self.jetzt = 0.0

    def __call__(self) -> float:
        return self.jetzt


def test_uebersicht_vor_den_produktseiten_und_im_zeitbudget(telekom, karte):
    telekom = dataclasses.replace(telekom, uebersichten=(UEBERSICHT_M,))
    uhr = _Uhr()
    reihe: list[str] = []

    def lies(adresse: str, ende: float) -> dict:
        reihe.append(adresse)
        uhr.jetzt += 600
        return _uebersicht([_satz("iPhone 18 Pro 256 GB")])

    def crawle(seite, ende):
        reihe.append(seite.adresse)
        uhr.jetzt += 600
        return Klicklauf("Telekom", seite.adresse)

    ende = 600 + 600 + MINDESTZEIT_SEITE_S - 1
    daten = fahre(
        telekom,
        karte,
        "k",
        crawle,
        HEUTE,
        ende,
        gelesen={},
        uhr=uhr,
        schlafe=lambda s: None,
        lies_uebersicht=lies,
    )
    assert reihe[0] == UEBERSICHT_M
    assert len(reihe) == 2
    assert [u["status"] for u in daten["uebersichten"]] == [LAUF_GELESEN]
    assert (
        sum(s["status"] == "nicht_besucht" for s in daten["seiten"])
        == len(telekom.seiten) - 1
    )


def test_gestoerte_uebersicht_haelt_den_anbieter_an(telekom, karte):
    def lies(adresse: str, ende: float) -> dict:
        return {**_uebersicht([], LAUF_GESTOERT), "grund": abruf_gestoert(403)}

    def crawle(seite, ende):
        raise AssertionError("nach gestörter Übersicht keine Produktseite")

    daten = fahre(
        telekom,
        karte,
        "k",
        crawle,
        HEUTE,
        10**6,
        gelesen={},
        uhr=_Uhr(),
        schlafe=lambda s: None,
        lies_uebersicht=lies,
    )
    assert daten["laufstatus"] == LAUF_GESTOERT
    assert all(s["grund"].startswith(GRUND_NACH_STOERUNG) for s in daten["seiten"])


def test_leere_uebersicht_haelt_die_produktseiten_nicht_an(telekom, karte):
    """Klick-Tageslauf 09.10.2026: Übersicht ohne Gerät, danach blieb jede
    Produktseite ungelesen."""

    def lies(adresse: str, ende: float) -> dict:
        return {**_uebersicht([], "leer"), "grund": "Übersicht ohne Gerät"}

    besucht: list[str] = []

    def crawle(seite, ende):
        besucht.append(seite.adresse)
        return Klicklauf("Telekom", seite.adresse)

    daten = fahre(
        telekom,
        karte,
        "k",
        crawle,
        HEUTE,
        10**6,
        gelesen={},
        uhr=_Uhr(),
        schlafe=lambda s: None,
        lies_uebersicht=lies,
    )
    assert len(besucht) == len(telekom.seiten)
    assert all(u["status"] == "leer" for u in daten["uebersichten"])
