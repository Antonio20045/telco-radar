"""Ausgelistete Telekom-Geräte: wann eine Seite ohne Kanarienwert ``leer`` heißt.

Ohne Browser und Netz: ``Bedienung.pruefe_kanarie`` läuft mit einer Seite, die nur eine
Adresse hat, auf der echten Karte aus ``config/klickkarten``. Der Kanarienwert fehlt auf
jeder Seite (der Leser nennt ein anderes Modell, wie die Markenübersicht der Telekom
vom 02.11.2026). ``leer`` gilt nur bei Umleitung, genauem Telekom-Host und dem Pfad
``/shop/geraete/smartphones/<marke>``; die Query zählt nicht. Die zwei Prüferfälle
(Fehlerseite mit Pfad im Query, fremder Host) und ihre Gegenproben stehen hier.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from telco_radar.collect.geraete.klickbedienung import (
    GRUND_AUSGELISTET,
    Bedienung,
    ist_ausgelistet,
)
from telco_radar.collect.geraete.klickkarte import Kanarie
from telco_radar.collect.geraete.klickkartenprobe import GELADEN, lade_karte
from telco_radar.collect.geraete.klickwache import Abbruch

WURZEL = Path(__file__).resolve().parents[1]
MODELL = "Apple iPhone 17 Pro"
TELEKOM = "https://www.telekom.de"
ANGEFORDERT = (
    f"{TELEKOM}/shop/geraet/motorola/edge-60-neo/schwarz-256-gb?tariffId=MF_17791"
)
UEBERSICHT = f"{TELEKOM}/shop/geraete/smartphones/motorola"


def karte(anbieter: str):
    lage = lade_karte(WURZEL / "config" / "klickkarten", anbieter)
    assert lage.status == GELADEN, lage.grund
    return lage.karte


class _Lauf:
    def __init__(self, adresse: str) -> None:
        self.adresse, self.stoerung = adresse, None


class _Wache:
    def __init__(self, adresse: str) -> None:
        self.lauf = _Lauf(adresse)

    def pruefe_tor(self) -> None:
        return None


class _Leser:
    def text(self, ort, erwartet, attribut):
        return "View energy label for Samsung Galaxy S26"


class _Seite:
    def __init__(self, url: str) -> None:
        self.url = url

    def locator(self, selektor):
        return object()


def lauf(anbieter: str, angefordert: str, endadresse: str):
    """Status und Grund des Kanarienwert-Tests; ``ok`` hieße bestanden."""
    bedienung = Bedienung(
        _Seite(endadresse),
        karte(anbieter),
        _Wache(angefordert),
        _Leser(),
        MODELL,
    )
    try:
        bedienung.pruefe_kanarie()
    except Abbruch as abbruch:
        return abbruch.status, abbruch.grund
    return "ok", None


def test_echte_umleitung_auf_die_markenuebersicht_ist_leer():
    status, grund = lauf("telekom", ANGEFORDERT, UEBERSICHT)
    assert status == "leer"
    assert grund == f"{GRUND_AUSGELISTET} {UEBERSICHT}"


def test_echte_umleitung_mit_query_und_schraegstrich_ist_leer():
    ende = f"{UEBERSICHT}/?tariffId=MF_17785"
    assert lauf("telekom", ANGEFORDERT, ende)[0] == "leer"


def test_host_in_anderer_schreibweise_ist_derselbe_host():
    ende = "https://WWW.Telekom.de:443/shop/geraete/smartphones/samsung"
    assert lauf("telekom", ANGEFORDERT, ende)[0] == "leer"


def test_fehlerseite_mit_pfad_im_query_ist_gestoert():
    """Prüfer: Login-Seite trägt den Rückweg als Parameter, das ist keine Auslistung."""
    ende = (
        "https://accounts.login.idm.telekom.com/auth"
        f"?redirect_uri={TELEKOM}/shop/geraete/smartphones/apple"
    )
    status, grund = lauf("telekom", ANGEFORDERT, ende)
    assert status == "gestoert", (status, grund)
    assert grund is not None and grund.startswith("Kanarienwert fehlt")


def test_query_treffer_auf_dem_telekom_host_ist_gestoert():
    ende = f"{TELEKOM}/fehler?zurueck=/shop/geraete/smartphones/apple"
    assert lauf("telekom", ANGEFORDERT, ende)[0] == "gestoert"


def test_fremder_host_ist_nicht_telekom():
    """Prüfer: gleicher Pfad auf einem fremden Host."""
    ende = "https://www.example-fremd.de/shop/geraete/smartphones/foo"
    assert lauf("telekom", ANGEFORDERT, ende)[0] == "gestoert"
    assert lauf("o2", ANGEFORDERT, ende)[0] == "gestoert"


def test_host_mit_telekom_als_anhang_ist_nicht_telekom():
    ende = "https://www.telekom.de.example.net/shop/geraete/smartphones/apple"
    assert lauf("telekom", ANGEFORDERT, ende)[0] == "gestoert"


@pytest.mark.parametrize(
    "pfad",
    [
        "/shop/geraete/smartphones",
        "/shop/geraete/smartphones/",
        "/shop/geraete/smartphones/apple/iphone",
        "/x/shop/geraete/smartphones/apple",
        "/shop/geraete/tablets/apple",
    ],
)
def test_anderer_pfad_ist_gestoert(pfad):
    assert lauf("telekom", ANGEFORDERT, f"{TELEKOM}{pfad}")[0] == "gestoert"


@pytest.mark.parametrize("anbieter", ["congstar", "o2", "vodafone", "1und1"])
def test_andere_karte_kennt_die_regel_nicht(anbieter):
    assert karte(anbieter).kanarie.ausgelistet_url is None
    assert lauf(anbieter, ANGEFORDERT, UEBERSICHT)[0] == "gestoert"


def test_ohne_umleitung_bleibt_die_uebersicht_gestoert():
    """Die angeforderte Adresse ist selbst die Übersicht: keine Auslistung."""
    direkt = f"{TELEKOM}/shop/geraete/smartphones/ohne-vertrag"
    assert lauf("telekom", direkt, direkt)[0] == "gestoert"
    mit_query = f"{direkt}?tariffId=MF_17785"
    assert lauf("telekom", direkt, mit_query)[0] == "gestoert"


def test_kanarienwert_vorhanden_ist_nie_leer():
    class _Treffer(_Leser):
        def text(self, ort, erwartet, attribut):
            return f"View energy label for {MODELL}"

    bedienung = Bedienung(
        _Seite(UEBERSICHT), karte("telekom"), _Wache(ANGEFORDERT), _Treffer(), MODELL
    )
    assert bedienung.pruefe_kanarie() is None


def test_telekom_karte_traegt_host_und_pfadmuster():
    regel = karte("telekom").kanarie.ausgelistet_url
    assert regel is not None
    assert regel.host == "www.telekom.de"
    assert regel.pfad.fullmatch("/shop/geraete/smartphones/samsung")


def test_ist_ausgelistet_ohne_regel_ist_falsch():
    kanarie = Kanarie(selektor="#k", enthaelt="x")
    assert not ist_ausgelistet(kanarie, ANGEFORDERT, UEBERSICHT)
