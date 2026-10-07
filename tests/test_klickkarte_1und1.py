"""Klick-Karte 1&1 gegen gespeicherte echte Seiten des Bestellwegs, ohne Browser.

1&1 nennt 24 oder „24+12“ Monate erst nach „Weiter zur Tarifauswahl“: zwei Kacheln
auf ``/flow2/mobile/ssc-private/tariffContractDuration`` (Klick-Erkundung 07.10.2026,
Zweig ``klick-erkundung``, Commit c8ce1f77, Seiten 3 und 4; Auszug
``einsundeins_bestellweg_laufzeit_20261007.json``). Die zweite Lesung sind die Globalen
der Produktseite (``hwdVariantsPrices``, ``hwdVariantsOneOffPaymentFees``), gelesen vor
dem Weiter; kein Mitschnitt hält das Dokument, Beleg ist die Produktseite iPhone 17 Pro
vom 08.09.2026 (``einsundeins_produktseite_iphone_17_pro.html.gz``). Ihre Werte 44,99 €
und 360 € sind dieselben, die die Kachel „24+12“ am 07.10. zeigte. Herkunft beider
Dateien in ``tests/fixtures/geraete/_herkunft.json``. Gegenproben: die Kachel 24 bleibt
Befund (die Globale nennt 36), 512 GB liest seinen eigenen Betrag, nie den eines
Zubehör-Bündels, und eine Farbe, die es nicht gibt, liest keinen.
"""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import pytest
from bs4 import BeautifulSoup

from telco_radar.collect.geraete.klickantwort import monate
from telco_radar.collect.geraete.klickecho import (
    feldwert,
    lies_antwort,
    pruefe_echo,
    variante_aus,
)
from telco_radar.collect.geraete.klickkartenprobe import GELADEN, lade_karte
from telco_radar.collect.geraete.klickstrecke import KAUFWORT
from telco_radar.collect.geraete.klicktext import Buendelwerte, Preiswerte

KARTEN = Path(__file__).resolve().parents[1] / "config" / "klickkarten"
FIXTURES = Path(__file__).parent / "fixtures" / "geraete"
SEITE = FIXTURES / "einsundeins_produktseite_iphone_17_pro.html.gz"
BESTELLWEG = FIXTURES / "einsundeins_bestellweg_laufzeit_20261007.json"
ADRESSE = "https://mobile.1und1.de/iphone-17-pro"
PREISE = re.compile(r"hwdVariantsPrices\s*=\s*\{(.*?)\};", re.S)
EINTRAG = re.compile(r"'([^']+)'\s*:\s*\[\s*(\d+)\s*,?\s*\]")
LAUFZEIT = re.compile(r"window\.currentHardwareOfferDuration\s*=\s*'(\d+)'")
EINMAL = re.compile(r"hwdVariantsOneOffPaymentFees\s*=\s*(\{.*?\})")
KACHEL = re.compile(
    r"^#tariff-cards-container > div:nth-of-type\(\d+\) > div:nth-of-type\(\d+\)"
)
STUFE = re.compile(r"([\w-]+):nth-of-type\((\d+)\)")
PLATZ = {"speicher": "256", "tarif": "tariff-anf-s-mvl", "farbe": "COSMIC_ORANGE"}


@pytest.fixture(scope="module")
def karte():
    lage = lade_karte(KARTEN, "1und1")
    assert (lage.status, lage.grund) == (GELADEN, None)
    return lage.karte


@pytest.fixture(scope="module")
def html() -> str:
    return gzip.decompress(SEITE.read_bytes()).decode("utf-8")


@pytest.fixture(scope="module")
def dom(html):
    return BeautifulSoup(html, "html.parser")


@pytest.fixture(scope="module")
def weg() -> dict:
    return json.loads(BESTELLWEG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def globale(html) -> dict:
    """Was die drei Globalen der Produktseite liefern."""
    preise = {k: [int(v)] for k, v in EINTRAG.findall(PREISE.search(html)[1])}
    return {
        "hwdVariantsPrices": preise,
        "hwdVariantsOneOffPaymentFees": json.loads(EINMAL.search(html)[1]),
        "currentHardwareOfferDuration": LAUFZEIT.search(html)[1],
    }


def _seitenwert(dom, karte, name: str) -> str | None:
    wert = karte.seite[name]
    element = dom.select_one(wert.selektor)
    roh = element.get(wert.attribut) if wert.attribut else element.get_text(" ")
    if wert.parameter is not None:
        roh = parse_qs(urlparse(urljoin(ADRESSE, roh)).query)[wert.parameter][0]
    return roh


def _kacheln(weg: dict, seite: int) -> list[tuple[str, str]]:
    """Je Kachel (Pfad der Kachel, data-linkid) aus dem Inventar der Folgeseite."""
    elemente = weg[f"seite_{seite}"]["bedienelemente"].values()
    return [
        (KACHEL.match(e["pfad"])[0], e["daten"]["data-linkid"])
        for e in elemente
        if e["tag"] == "add-to-cart-button"
    ]


def _kacheltext(weg: dict, seite: int, kachel: str) -> str:
    """Die Preis-Kandidaten einer Kachel, wie die Erkundung sie las."""
    preise = weg[f"seite_{seite}"]["preise"].values()
    return "\n".join(p["kontext"] for p in preise if p["pfad"].startswith(kachel))


def _textwerte(karte, text: str) -> Buendelwerte:
    werte = {}
    for feld, muster in karte.textlesung.muster.items():
        treffer = muster.muster.search(text)
        roh = None if treffer is None else "".join(treffer[1].split())
        werte[feld] = None if roh is None else feldwert(feld, roh)
    return Buendelwerte(**werte)


def _laufzeit(karte, linkid: str) -> str:
    return karte.knoepfe["laufzeit"].muster.search(linkid)[1]


def _echo(karte, globale, linkid: str, im_text: Buendelwerte):
    lesung = lies_antwort(globale, karte.antwort, None, PLATZ)
    variante = variante_aus("256", "tariff-anf-s-mvl", _laufzeit(karte, linkid))
    echo = pruefe_echo(
        variante,
        variante,
        Preiswerte(),
        lesung,
        buendel=im_text,
        entfallen=karte.entfallen,
    )
    return variante, lesung, echo


def test_selektoren_der_karte_treffen_die_produktseite(karte, dom):
    knoepfe = dom.select(karte.knoepfe["speicher"].selektor)
    werte = [k.select_one(karte.knoepfe["speicher"].wert_in)["value"] for k in knoepfe]
    gewaehlt = [k for k in knoepfe if k.select_one("input:checked") is not None]
    kanarie = dom.select_one(karte.kanarie.selektor)

    assert werte[:2] == ["256", "512"]
    assert len(gewaehlt) == 1
    assert "iPhone 17 Pro" in kanarie[karte.kanarie.attribut]
    assert len(dom.select(karte.vorbereitung[0].klick)) == 1
    assert {n: _seitenwert(dom, karte, n) for n in ("speicher", "tarif", "farbe")} == {
        "speicher": "256",
        "tarif": "tariff-anf-s-mvl",
        "farbe": "COSMIC_ORANGE",
    }


def _nachbau(knoepfe: dict) -> BeautifulSoup:
    """Ein DOM aus den Pfaden der Erkundung (``nth-of-type`` mit Platzhaltern davor);
    jeder Knopf trägt seine Klassen und seine Nummer im Inventar."""
    dom = BeautifulSoup('<div id="hwd-configuration-section"></div>', "html.parser")
    for nummer, knopf in knoepfe.items():
        ort = dom.div
        for teil in knopf["pfad"].split(" > ")[1:]:
            tag, stelle = STUFE.fullmatch(teil).groups()
            kinder = ort.find_all(tag, recursive=False)
            while len(kinder) < int(stelle):
                kinder.append(dom.new_tag(tag))
                ort.append(kinder[-1])
            ort = kinder[int(stelle) - 1]
        ort["class"], ort["data-nummer"] = knopf["klassen"], nummer
    return dom


def test_weiter_knopf_wie_in_der_erkundung(karte, weg):
    """Der Selektor der Karte trifft nur den sichtbaren Knopf; Gegenprobe: der
    Selektor der Erkundung trifft auch die Kopie in der Klebeleiste."""
    for seite, ausgang in ((3, 1), (4, 2)):
        index = weg[f"seite_{seite}"]["index"]
        knoepfe = weg[f"seite_{ausgang}"]["bedienelemente"]
        sichtbar = [n for n, k in knoepfe.items() if k["sichtbar"]]
        dom = _nachbau(knoepfe)

        assert index["weiter"]["geklickt"] == karte.weiter.text
        assert "/ssc-private/tariffContractDuration?" in index["endadresse"]
        assert {k["text"] for k in knoepfe.values()} == {karte.weiter.text}
        assert [k["data-nummer"] for k in dom.select(karte.weiter.selektor)] == sichtbar
        assert len(dom.select(index["weiter"]["selektor"])) == len(knoepfe) == 2
    assert KAUFWORT.search(karte.weiter.text) is None


def test_zwei_kacheln_mit_24_und_24_plus_12(karte, weg):
    for seite in (3, 4):
        kacheln = _kacheln(weg, seite)
        laufzeiten = [_laufzeit(karte, linkid) for _, linkid in kacheln]

        assert len({pfad for pfad, _ in kacheln}) == 2
        assert laufzeiten == ["24", "24+12"]
        assert [monate(w) for w in laufzeiten] == [24, 36]
    assert karte.knoepfe["laufzeit"].selektor == karte.textlesung.selektoren[0]
    assert karte.weiter.kacheln == "laufzeit"


def test_kachel_36_bestaetigt_buendel_und_einmalzahlung(karte, weg, globale):
    kachel, linkid = _kacheln(weg, 3)[1]
    im_text = _textwerte(karte, _kacheltext(weg, 3, kachel))

    variante, lesung, echo = _echo(karte, globale, linkid, im_text)

    assert variante.laufzeit == 36
    assert dict(lesung.variante) == {"laufzeit": 36}
    assert echo.stimmt, echo.befunde
    assert echo.buendel == Buendelwerte(buendelbetrag=44.99, einmalzahlung=360.0)
    assert "rate" not in echo.luecken


def test_galaxy_s26_kacheln_lesen_eigene_werte(karte, weg):
    kacheln = _kacheln(weg, 4)
    werte = [_textwerte(karte, _kacheltext(weg, 4, k)) for k, _ in kacheln]

    assert werte == [
        Buendelwerte(buendelbetrag=44.99),
        Buendelwerte(buendelbetrag=34.99, einmalzahlung=220.0),
    ]


def test_gegenprobe_kachel_24_bleibt_befund(karte, weg, globale):
    kachel, linkid = _kacheln(weg, 3)[0]
    im_text = _textwerte(karte, _kacheltext(weg, 3, kachel))

    variante, _, echo = _echo(karte, globale, linkid, im_text)

    assert variante.laufzeit == 24
    assert im_text == Buendelwerte(buendelbetrag=59.99)
    assert [(b.feld, b.grund) for b in echo.befunde] == [
        ("antwort.laufzeit", "Antwort nennt 36 statt 24")
    ]
    assert echo.buendel == Buendelwerte()


def test_gegenprobe_anderer_speicher_kein_buendel_keine_fremde_farbe(karte, globale):
    def werte(speicher: str, farbe: str) -> Buendelwerte:
        platz = {"speicher": speicher, "farbe": farbe}
        return lies_antwort(globale, karte.antwort, None, platz).buendel

    preise = globale["hwdVariantsPrices"]
    buendel = preise[
        "product-COSMIC_ORANGE-512-bundle-hw-apple-iphone-17-pro-30996563240e-WEISS-0"
    ]

    eigener = preise["product-COSMIC_ORANGE-512"][0]
    assert werte("512", "COSMIC_ORANGE").buendelbetrag == eigener / 100
    assert werte("512", "COSMIC_ORANGE").buendelbetrag != buendel[0] / 100
    assert werte("512", "COSMIC_ORANGE").einmalzahlung == 450.0
    assert werte("256", "VIOLETT") == Buendelwerte()
