"""Klick-Karte o2 (config/klickkarten/o2.yaml) gegen gespeicherte echte Antworten.

- o2_vertiefung_iphone17pro.json.gz (29.09.2026): Produktseite mit script#pageValue
  (Ausgangszustand) und 14 Konfigurationsantworten mit priceSummary.
- o2_konfiguration_20261007.json.gz (07.10.2026, Auszug aus der Klick-Erkundung):
  Variante und Volumen der Antworten nach Klicks auf Tarif und Laufzeit.
- Texte der Tabelle und der Tarifkacheln aus der Erkundung vom 07.10.2026, Commit
  f31d5543: ``TABELLE`` je Zeile der Kontext aus preise-1.json Nr. 42–50 (Zellen mit
  Tab getrennt), ``KACHEL_*`` aus bedienelemente-1.json El. 30, 32 und 36.

256 GB, 36 Monate, O2 Mobile Unlimited M Plus kostete an beiden Tagen dasselbe
(Gerät 36,50 €, Tarif 19,99 €, Anzahlung 1,00 €, Anschluss 0,00 €): Text vom 07.10. und
pageValue vom 29.09. müssen darum übereinstimmen. Das Volumen fehlt im gekürzten
pageValue (nur gelesene Felder); es steht im Auszug vom 07.10.

``TABELLE`` ist seit der Ursache-Probe 04.11.2026 (arbeit/o2-klick-0411/ursache.md)
kein table mehr: das Preiswidget ist <tef-mini-basket>, der Crawler liest
``innerText`` des ersten Treffers im DOM (die mobile Variante vor der sichtbaren
Desktop-Variante), ohne Zeilenumbrüche zwischen den Posten. Der Tarifknopf liest
seinen Wert seither ohne Muster aus aria-label; der volle Tarifname steht dort schon
ohne Preis (``test_tarifknopf_liest_ohne_muster_aus_aria_label``).
"""

from __future__ import annotations

import base64
import gzip
import json
import math
import re
from pathlib import Path

import pytest

from telco_radar.collect.geraete.klickantwort import lies_antwort
from telco_radar.collect.geraete.klickecho import (
    gleiche_option,
    pruefe_echo,
    variante_aus,
)
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klickoptionen import wert_nach_muster
from telco_radar.collect.geraete.klicktextleser import Textleser
from telco_radar.tarif_model import Preisphase

WURZEL = Path(__file__).parent.parent
_FIX = Path(__file__).parent / "fixtures" / "geraete"
KARTE = lade_klickkarte(WURZEL / "config" / "klickkarten" / "o2.yaml")
KONFIGURATION, SEITE = KARTE.lesequellen

TABELLE = (
    "Gerät monatlich:36,50\xa0€Ratenzahlung: 36 Monate"
    "Gesamtpreis Gerät: 1.315,00\xa0€"
    "Tarif monatlich:19,99\xa0€(Mindestlaufzeit 24 Monate):"
    "monatlich gesamt:56,49\xa0€56,49\xa0€"
    "Gerät Anzahlung:1,00\xa0€einmaliger Anschlusspreis0,00\xa0€39,99\xa0€"
    "Versandkosten:6,99\xa0€einmalig gesamt:7,99\xa0€7,99\xa0€In den Warenkorb"
)
KACHEL_M_PLUS = "O2 Mobile Unlimited M Plus mit 100 MBit/s mtl. 56,49 €"
KACHEL_L_PLUS = "O2 Mobile Unlimited L Plus mit 300 MBit/s mtl. 66,49 €"
KACHEL_150 = "O2 Mobile L Plus mit 150 GB+ mtl. 56,49 €"


def _vertiefung() -> dict[str, str]:
    datei = _FIX / "o2_vertiefung_iphone17pro.json.gz"
    return json.loads(gzip.decompress(datei.read_bytes()))["antworten"]


def _page_value() -> object:
    seite = next(r for r in _vertiefung().values() if r.startswith("<html"))
    roh = re.search(r'<script id="pageValue"[^>]*>(.*?)</script>', seite, re.S)
    assert roh is not None
    return json.loads(roh[1])


def _konfiguration(tarif: str, hardware: str) -> tuple[str, object]:
    for url, roh in _vertiefung().items():
        if "/rest/configuration/" not in url:
            continue
        kennung = url.rsplit("/", 1)[-1]
        klar = base64.b64decode(kennung + "=" * (-len(kennung) % 4)).decode()
        if f"privatkunden-{tarif};" in klar and f"privatkunden-{hardware};" in klar:
            return url, json.loads(roh)
    raise AssertionError(f"Konfiguration {hardware} {tarif} fehlt im Fixture")


class _Ort:
    """Ein Bereich mit festem Text, wie ihn ``Textleser`` liest."""

    def __init__(self, text: str | None) -> None:
        self._text = text

    def count(self) -> int:
        return 0 if self._text is None else 1

    @property
    def first(self) -> _Ort:
        return self

    def evaluate_all(self, _skript: str, attribut: str | None) -> str | None:
        assert attribut is None
        return self._text


class _Seite:
    def __init__(self, texte: dict[str, str]) -> None:
        self._texte = texte

    def locator(self, selektor: str) -> _Ort:
        return _Ort(self._texte.get(selektor))


def _textwerte(tabelle: str, kachel: str):
    volumen = KARTE.textlesung.muster["volumen_gb"].selektor
    leser = Textleser(_Seite({volumen: kachel}), KARTE, 200)
    werte, _, fundorte = leser.textwerte(tabelle)
    return werte, fundorte


def test_karte_laedt_mit_drei_geklickten_dimensionen_und_zwei_quellen():
    assert KARTE.anbieter == "o2"
    assert all(KARTE.knoepfe[d].selektor for d in ("speicher", "tarif", "laufzeit"))
    assert KONFIGURATION.url_muster.pattern.startswith("^https://www\\.o2online\\.de/")
    assert SEITE.skript == "script#pageValue"
    assert SEITE.start and not KONFIGURATION.start
    assert KARTE.kanarie.enthaelt in TABELLE


@pytest.mark.parametrize(
    ("text", "dimension", "wert"),
    [
        ("256 GB", "speicher", "256 GB"),
        ("24 Monate", "laufzeit", "24"),
    ],
)
def test_knopftext_ergibt_den_wert_der_antwort(text, dimension, wert):
    assert wert_nach_muster(text, KARTE.knoepfe[dimension].muster) == wert


def test_tarifknopf_liest_ohne_muster_aus_aria_label():
    """Seit der Ursache-Probe 04.11.2026 trägt das Label den vollen Tarifnamen ohne
    Preis im eigenen aria-label (arbeit/o2-klick-0411/ursache.md); kein Muster nötig."""
    assert KARTE.knoepfe["tarif"].wert_attribut == "aria-label"
    assert KARTE.knoepfe["tarif"].muster is None


def test_ausgangszustand_aus_page_value():
    lesung = lies_antwort(_page_value(), SEITE)

    w = lesung.werte
    assert (w.anzahlung, w.rate, w.ratenzahl) == (1.0, 36.5, 36)
    assert w.tarifphasen == (Preisphase(1, None, 19.99),)
    assert (w.tarifbindung, w.anschluss) == (24, 0.0)
    assert dict(lesung.variante) == {
        "speicher": "256 GB",
        "laufzeit": 36,
        "tarif": "O2 Mobile Unlimited M Plus mit 100 MBit/s",
    }


@pytest.mark.parametrize(
    ("hardware", "tarif", "erwartet"),
    [
        (
            "apple-iphone-17-pro-512gb-silber-24xhigh",
            "o2-mobile-unlimited-m-plus-online-hwv-24m-05-00",
            (7.0, 66.0, 24, (Preisphase(1, None, 19.99),), 0.0, "512 GB", 24),
        ),
        (
            "apple-iphone-17-pro-256gb-silber-36xhigh",
            "o2-mobile-special-online",
            (
                1.0,
                36.5,
                36,
                (Preisphase(1, 24, 14.99), Preisphase(25, None, 29.99)),
                0.0,
                "256 GB",
                36,
            ),
        ),
    ],
    ids=["512gb_24_monate", "special_mit_zwei_phasen"],
)
def test_konfiguration_nach_klick(hardware, tarif, erwartet):
    url, daten = _konfiguration(tarif, hardware)
    assert KONFIGURATION.passt(url)

    lesung = lies_antwort(daten, KONFIGURATION, url)

    w = lesung.werte
    gelesen = (w.anzahlung, w.rate, w.ratenzahl, w.tarifphasen, w.anschluss)
    assert (
        gelesen + (lesung.variante["speicher"], lesung.variante["laufzeit"]) == erwartet
    )
    assert w.tarifbindung == 24


def test_variante_und_volumen_nach_klicks_vom_7_oktober():
    datei = _FIX / "o2_konfiguration_20261007.json.gz"
    antworten = json.loads(gzip.decompress(datei.read_bytes()))["antworten"]

    gelesen = []
    for url, daten in antworten.items():
        assert KONFIGURATION.passt(url)
        lesung = lies_antwort(daten, KONFIGURATION, url)
        v = lesung.variante
        gelesen.append(
            (v["speicher"], v["laufzeit"], v["tarif"], lesung.werte.volumen_gb)
        )

    assert gelesen == [
        ("256 GB", 24, "O2 Mobile Unlimited L Plus mit 300 MBit/s", math.inf),
        ("256 GB", 24, "O2 Mobile Unlimited S Special Plus mit 15 MBit/s", math.inf),
        ("512 GB", 24, "O2 Mobile Unlimited L Plus mit 300 MBit/s", math.inf),
    ]
    assert gleiche_option(gelesen[0][2], "O2 Mobile Unlimited L Plus mit 300 MBit/s")
    assert _textwerte(TABELLE, KACHEL_L_PLUS)[0].volumen_gb == math.inf


def test_text_und_page_value_stimmen_ueberein():
    text, fundorte = _textwerte(TABELLE, KACHEL_M_PLUS)
    antwort = lies_antwort(_page_value(), SEITE)
    gewaehlt = variante_aus("256 GB", "O2 Mobile Unlimited M Plus mit 100 MBit/s", "36")

    echo = pruefe_echo(gewaehlt, gewaehlt, text, antwort, entfallen=("volumen_gb",))

    assert echo.befunde == ()
    assert echo.luecken == ()
    assert echo.werte.rate == 36.5
    assert echo.werte.tarifphasen == (Preisphase(1, None, 19.99),)
    assert fundorte["rate"][1] == "Gerät monatlich:36,50\xa0€"


def test_gegenprobe_andere_rate_im_text_ist_befund():
    text, _ = _textwerte(TABELLE.replace("36,50\xa0€", "43,50\xa0€"), KACHEL_M_PLUS)
    antwort = lies_antwort(_page_value(), SEITE)
    gewaehlt = variante_aus("256 GB", "O2 Mobile Unlimited M Plus mit 100 MBit/s", "36")

    echo = pruefe_echo(gewaehlt, gewaehlt, text, antwort, entfallen=("volumen_gb",))

    assert [b.feld for b in echo.befunde] == ["rate"]
    assert echo.werte.rate is None


def test_volumen_mit_gb_zahl_an_der_kachel():
    assert _textwerte(TABELLE, KACHEL_150)[0].volumen_gb == 150.0
