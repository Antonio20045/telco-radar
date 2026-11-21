"""1&1: drei Seiten, die im Nachtlauf 21.11.2026 „gestört (Seitenform)“ hießen.

Erkundung 21.11.2026 (Playwright-Chromium über das Tor des Projekts, Kennung
``TelcoRadar/1.0``, je Seite ein Abruf):

- ``/xiaomi-redmi-note-17-pro-5g``: Speicherkachel mit aria-label „Speicherauswahl
  Xiaomi REDMI Note 17 Pro 5G“, der Katalog nennt „Redmi Note 17 Pro“; die Seite hat
  dieselbe Form wie jede andere. Der Kanarienwert gilt ohne Unterschied der Groß- und
  Kleinschreibung (ebenso ``/xiaomi-redmi-17c-5g``).
- ``/iphone-16e``: 301 auf ``/iphone-17e?traceId=…`` (das iPhone 16e ist nicht mehr im
  Angebot). Dort fehlt der Kanarienwert zu Recht: die Seite ist ``leer``, keine andere
  Form; Gegenproben: gleicher Pfad, tieferer Pfad, fremder Host bleiben gestört.

Ohne Browser: ``Bedienung.pruefe_kanarie`` mit der echten Karte, einer Seite, die nur
eine Adresse hat, und einem Leser, der den gemessenen aria-label nennt.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.collect.geraete.klickbedienung import GRUND_AUSGELISTET, Bedienung
from telco_radar.collect.geraete.klickkartenprobe import GELADEN, lade_karte
from telco_radar.collect.geraete.klickwache import Abbruch
from telco_radar.geraete_config import lade_katalog

WURZEL = Path(__file__).resolve().parents[1]
HOST = "https://mobile.1und1.de"
REDMI_ARIA = "Speicherauswahl Xiaomi REDMI Note 17 Pro 5G"
REDMI_17C_ARIA = "Speicherauswahl Xiaomi REDMI 17C 5G"
IPHONE_17E_ARIA = "Speicherauswahl iPhone 17e"
UMLEITUNG_16E = f"{HOST}/iphone-17e?traceId=9c19f39b-397a-4175-99a5-62ff684d3240"


@pytest.fixture(scope="module")
def karte():
    lage = lade_karte(WURZEL / "config" / "klickkarten", "1und1")
    assert lage.status == GELADEN, lage.grund
    return lage.karte


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


class _Lauf:
    def __init__(self, adresse: str) -> None:
        self.adresse, self.stoerung = adresse, None


class _Wache:
    def __init__(self, adresse: str) -> None:
        self.lauf = _Lauf(adresse)

    def pruefe_tor(self) -> None:
        return None


class _Leser:
    def __init__(self, text: str) -> None:
        self.wert = text

    def text(self, ort, erwartet, attribut):
        assert attribut == "aria-label"
        return self.wert


class _Seite:
    def __init__(self, url: str) -> None:
        self.url = url

    def locator(self, selektor):
        return object()


def _pruefe(karte, angefordert: str, ende: str, aria: str, modell: str):
    bedienung = Bedienung(
        _Seite(ende), karte, _Wache(angefordert), _Leser(aria), modell
    )
    try:
        bedienung.pruefe_kanarie()
    except Abbruch as abbruch:
        return abbruch.status, abbruch.grund
    return "ok", None


@pytest.mark.parametrize(
    ("geraet", "pfad", "aria"),
    [
        ("xiaomi-redmi-note-17-pro", "/xiaomi-redmi-note-17-pro-5g", REDMI_ARIA),
        ("xiaomi-redmi-17c", "/xiaomi-redmi-17c-5g", REDMI_17C_ARIA),
    ],
)
def test_redmi_in_grossbuchstaben_besteht_den_kanarienwert(
    karte, katalog, geraet, pfad, aria
):
    modell = katalog.nach_id(geraet).modell
    assert modell.casefold() in aria.casefold() and modell not in aria

    assert _pruefe(karte, HOST + pfad, HOST + pfad, aria, modell) == ("ok", None)


def test_gegenprobe_anderes_modell_bleibt_gestoert(karte, katalog):
    modell = katalog.nach_id("xiaomi-redmi-note-17-pro").modell
    adresse = f"{HOST}/xiaomi-redmi-note-17-pro-5g"

    status, grund = _pruefe(karte, adresse, adresse, REDMI_17C_ARIA, modell)

    assert status == "gestoert"
    assert grund.startswith("Kanarienwert fehlt")


def test_umleitung_auf_ein_anderes_geraet_ist_leer(karte, katalog):
    modell = katalog.nach_id("apple-iphone-16e").modell

    status, grund = _pruefe(
        karte, f"{HOST}/iphone-16e", UMLEITUNG_16E, IPHONE_17E_ARIA, modell
    )

    assert status == "leer"
    assert grund == f"{GRUND_AUSGELISTET} {UMLEITUNG_16E}"


@pytest.mark.parametrize(
    "ende",
    [
        f"{HOST}/iphone-16e?traceId=1",
        f"{HOST}/flow2/mobile/ssc-private/tariffselect",
        "https://mobile.1und1.de.example.net/iphone-17e",
        "https://www.1und1.de/iphone-17e",
    ],
)
def test_gegenprobe_ohne_echte_umleitung_bleibt_gestoert(karte, katalog, ende):
    modell = katalog.nach_id("apple-iphone-16e").modell

    status, _ = _pruefe(karte, f"{HOST}/iphone-16e", ende, IPHONE_17E_ARIA, modell)

    assert status == "gestoert"
