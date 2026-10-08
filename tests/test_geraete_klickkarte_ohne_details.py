"""Telekom ohne ``/v2/details``: die geladene Seite liefert ihre Werte trotzdem.

``/v2/details`` kommt nur nach dem Klick auf einen anderen Speicher (Karte
``config/klickkarten/telekom.yaml``); bietet die Seite nur einen Speicher (Pixel 11,
Tageslauf 08.10.2026 Commit 19f92ac3: drei Befunde „keine Antwort mitgeschnitten“,
512 GB nicht angeboten), kommt sie nie. Echte Daten der Klick-Erkundung vom 07.10.2026
(Zweig klick-erkundung, Commit a9b45f5a, Seite 1 iPhone 17 Pro 256 GB vor jedem
Klick, Herkunft in ``tests/fixtures/geraete/_herkunft.json``):

- ``/v2/tariffs`` (mitschnitt-1.json Antwort 100) kommt beim Laden und nennt den
  gewählten Tarif mit Preis, Bereitstellung und Volumen;
- der gewählte Laufzeitknopf (bedienelemente-1.json Element 42) nennt im
  ``aria-label`` „26,90 € pro Monat für 36 Monate, zuzüglich 99 € Anzahlung“, sein
  Text „26,90 € mtl. x 36 +99 € Anzahlung“ ist die erste Lesung.

Kein Netz, kein Browser.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from telco_radar.collect.geraete.klickantwort import feldwert
from telco_radar.collect.geraete.klickecho import pruefe_echo, variante_aus
from telco_radar.collect.geraete.klickkarte import (
    KlickkartenFehler,
    klickkarte_aus_daten,
    lade_klickkarte,
)
from telco_radar.collect.geraete.klickquellen import LESUNG, Quellenleser
from telco_radar.collect.geraete.klicktext import Preiswerte
from telco_radar.tarif_model import Preisphase

WURZEL = Path(__file__).resolve().parents[1]
FIX = WURZEL / "tests" / "fixtures" / "geraete"
KARTE = lade_klickkarte(WURZEL / "config" / "klickkarten" / "telekom.yaml")
INVENTAR = json.loads(
    (FIX / "telekom_bedienelemente_iphone17pro_20261007.json").read_text("utf-8")
)
API = "https://www.telekom.de/shop/api/eshop/bff-de/productOfferings/v2/"
SEITE = "https://www.telekom.de/shop/geraet/apple/apple-iphone-17-pro/tiefblau-256-gb"
KNOPF = INVENTAR["elemente"]["42"]
PLATZ_256 = {"speicher": "256 GB", "tarif": "MagentaMobil M", "laufzeit": "36"}


class _Anfrage:
    method = "POST"
    post_data_buffer = None

    def all_headers(self):
        return {}


class _Antwort:
    status = 200
    status_text = "OK"
    request = _Anfrage()

    def __init__(self, url: str, datei: str) -> None:
        self.url = url
        self._roh = (FIX / datei).read_text("utf-8")

    def json(self):
        return json.loads(self._roh)

    def body(self):
        return self._roh.encode("utf-8")

    def all_headers(self):
        return {"content-type": "application/json"}


TARIFE = _Antwort(f"{API}tariffs", "telekom_tarife_iphone17pro_20261007.json")
DETAILS_512 = _Antwort(
    f"{API}details", "telekom_details_iphone17pro_512gb_20261007.json"
)


class _Mitschnitt:
    def __init__(self, *antworten: _Antwort) -> None:
        self._antworten = list(antworten)

    def antworten_seit(self, seit):
        return self._antworten[seit:]


class _Seite:
    url = SEITE


def _lies(*antworten, label=KNOPF["aria"]["aria-label"], **platz):
    leser = Quellenleser(_Seite(), KARTE, _Mitschnitt(*antworten))
    seitenwerte = {name: None for name in KARTE.seite}
    seitenwerte["laufzeit_gewaehlt"] = label
    return leser.lies(0, False, {**seitenwerte, **PLATZ_256, **platz}, 0)


def _textwerte() -> Preiswerte:
    """Die erste Lesung über die Textmuster der Karte (Fundorte wie im Inventar)."""
    muster = KARTE.textlesung.muster
    texte = {
        "rate": KNOPF["text"],
        "ratenzahl": KNOPF["text"],
        "anzahlung": KNOPF["text"],
        "anschluss": INVENTAR["gruppen"]["45"]["name"],
        "volumen_gb": INVENTAR["gruppen"]["43"]["name"],
        "tarifphasen": INVENTAR["preise"]["19"]["text"],
    }
    return Preiswerte(
        **{f: feldwert(f, muster[f].muster.search(t)[1]) for f, t in texte.items()}
    )


def test_ohne_details_liefern_seite_und_ladeantwort_alle_werte():
    zweite = _lies(TARIFE)
    assert zweite.befund is None
    werte = zweite.lesung.werte
    assert (werte.rate, werte.ratenzahl, werte.anzahlung) == (26.9, 36, 99.0)
    assert werte.tarifphasen == (Preisphase(1, None, 49.95),)
    assert (werte.anschluss, werte.volumen_gb) == (39.95, 50.0)
    assert zweite.lesung.variante == {"tarif": "MagentaMobil M"}
    assert zweite.kopie.methode == LESUNG
    assert "26,90 € pro Monat für 36 Monate" in zweite.kopie.koerper.decode("utf-8")


def test_echo_ohne_details_stimmt_statt_befund_ohne_antwort():
    gewaehlt = variante_aus("256 GB", "MagentaMobil M", "36")
    echo = pruefe_echo(gewaehlt, gewaehlt, _textwerte(), _lies(TARIFE).lesung)
    assert echo.stimmt, echo.befunde
    assert (echo.werte.rate, echo.werte.ratenzahl) == (26.9, 36)
    assert echo.luecken == ("tarifbindung",)


def test_andere_rate_im_label_ist_befund():
    """Gegenprobe: nennt das Label eine andere Rate als der Text, gilt sie nicht."""
    label = KNOPF["aria"]["aria-label"].replace("26,90", "27,90")
    gewaehlt = variante_aus("256 GB", "MagentaMobil M", "36")
    echo = pruefe_echo(
        gewaehlt, gewaehlt, _textwerte(), _lies(TARIFE, label=label).lesung
    )
    assert [b.feld for b in echo.befunde] == ["rate"]
    assert echo.werte.rate is None


def test_details_gehen_vor_und_bleiben_der_beleg():
    """Mit ``/v2/details`` stammen alle Werte aus ihr (512 GB, 199 € Anzahlung)."""
    zweite = _lies(TARIFE, DETAILS_512, speicher="512 GB", anzahlung_gewaehlt="199")
    assert (zweite.lesung.werte.rate, zweite.lesung.werte.anzahlung) == (30.8, 199.0)
    assert zweite.kopie.url == DETAILS_512.url
    assert zweite.lesung.variante == {"speicher": "512 GB", "tarif": "MagentaMobil M"}


def test_ohne_seitenwert_und_ohne_antwort_keine_lesung():
    zweite = _lies(label=None)
    assert zweite.lesung is None


def test_seitenwert_trifft_nur_den_gewaehlten_laufzeitknopf():
    suppe = BeautifulSoup('<div id="dyt_productViewDesktop"></div>', "html.parser")
    for nummer in ("42", "43", "44"):
        element = INVENTAR["elemente"][nummer]
        attribute = {**element["aria"], "class": " ".join(element["klassen"])}
        knopf = suppe.new_tag("button", attrs={**attribute, "role": "radio"})
        knopf["data-nummer"] = nummer
        suppe.div.append(knopf)
    wert = KARTE.seite["laufzeit_gewaehlt"]
    treffer = [t["data-nummer"] for t in suppe.select(wert.selektor)]
    assert treffer == ["42"]
    assert wert.attribut == "aria-label"


def test_seitenquelle_braucht_einen_benannten_seitenwert():
    daten = {
        "anbieter": "Beispiel",
        "knoepfe": {
            "speicher": {"selektor": "#s button"},
            "tarif": {"selektor": "#t button"},
            "laufzeit": {"selektor": "#l button"},
            "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
        },
        "zusammenfassung": {"selektor": "#preis"},
        "seite": {"speicher": {"selektor": "#s"}},
        "antwort": [{"seitenwerte": True, "pfade": {"rate": "unbekannt"}}],
        "kanarie": {"selektor": "#k", "enthaelt": "X"},
    }
    with pytest.raises(KlickkartenFehler, match=r"antwort\.0\.pfade\.rate"):
        klickkarte_aus_daten(daten, "Prüfkarte")
    daten["seite"]["unbekannt"] = {"selektor": "#r"}
    karte = klickkarte_aus_daten(daten, "Prüfkarte")
    assert karte.lesequellen[0].seitenwerte
